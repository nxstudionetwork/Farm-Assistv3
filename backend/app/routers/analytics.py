"""Farm Intelligence Center - Analytics API.

Every value returned by these endpoints is derived from the authenticated
farmer's own records only. No mock data, no cross-user data, no personal
wallet money is mixed into farm finances. All ownership checks run server-side.
"""

import asyncio
import csv
import io
import random
import string
from datetime import datetime, timedelta
from html import escape as _esc
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User, LoginHistory
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, CropTask, FarmJournal, SoilRecord
from app.models.finance import Transaction, Expense, Income
from app.models.calendar import CalendarEvent
from app.models.government import InsurancePolicy
from app.models.market_price import MarketPrice
from app.models.report import FarmReport
from app.models.ai import AIConversation
from app.models.worker import WorkerBooking
from app.models.marketplace import MarketplaceOrder
from app.utils.auth import get_current_user
from app.services.weather_service import get_current_weather
from app.services.ai_service import chat_with_ai

router = APIRouter(prefix="/api/v1", tags=["Analytics"])

EXPENSE_CATEGORY_ORDER = [
    "Seeds", "Fertilizers", "Crop protection", "Labour", "Irrigation",
    "Equipment", "Transport", "Electricity", "Maintenance", "Other",
]

REPORT_TYPES = [
    "Farm Performance", "Crop", "Yield", "Financial", "Expense", "Income",
    "Season", "Farm Activity", "Complete Farm Report",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _r2(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _pct(part: Any, total: Any) -> Optional[float]:
    if total in (None, 0):
        return None
    try:
        return round((float(part or 0) / float(total)) * 100.0, 1)
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _acres(area: Any, unit: Optional[str] = None) -> float:
    if area is None:
        return 0.0
    u = (unit or "Acres").strip().lower()
    factor = 2.47105 if u in ("hectare", "hectares", "ha") else 1.0
    return round(float(area) * factor, 4)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _to_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _date_range(date_from: Optional[str] = None, date_to: Optional[str] = None):
    start = _to_date(date_from)
    end = _to_date(date_to)
    if end is None:
        end = datetime.utcnow()
    else:
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def _resolve_scope(db: Session, user: User, farm_id: Optional[str] = None,
                   plot_id: Optional[str] = None):
    """Farms/plots owned by the user, optionally narrowed by farm/plot id."""
    q = db.query(Farm).filter(Farm.user_id == user.id, Farm.is_active == True)
    if farm_id:
        q = q.filter(Farm.id == farm_id)
    farms = q.all()
    if farm_id and not farms:
        raise HTTPException(status_code=404, detail="Farm not found")
    farm_ids = [f.id for f in farms]
    plots = []
    if farm_ids:
        pq = db.query(FarmPlot).filter(FarmPlot.farm_id.in_(farm_ids))
        if plot_id:
            pq = pq.filter(FarmPlot.id == plot_id)
        plots = pq.all()
        if plot_id and not plots:
            raise HTTPException(status_code=404, detail="Plot not found")
    elif plot_id:
        raise HTTPException(status_code=404, detail="Plot not found")
    plot_ids = [p.id for p in plots]
    return farms, plots, farm_ids, plot_ids


def _report_code(db: Session, user: User) -> str:
    n = db.query(FarmReport).filter(FarmReport.user_id == user.id).count() + 1
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"RPT-{n:04d}-{suffix}"


def _sensors_in_scope(db: Session, user_id: str, farm_ids: List[str],
                      plot_ids: List[str]):
    from app.routers.sensors import Sensor
    q = db.query(Sensor).filter(Sensor.user_id == user_id)
    if farm_ids:
        q = q.filter(Sensor.farm_id.in_(farm_ids))
    sensors = q.all()
    if plot_ids:
        sensors = [s for s in sensors if s.plot_id in plot_ids or s.plot_id is None]
    return sensors


def _cycles_in_scope(db: Session, farm_ids: List[str], plot_ids: List[str],
                     date_from: Optional[str] = None, date_to: Optional[str] = None):
    q = db.query(CropCycle)
    if farm_ids:
        q = q.filter(CropCycle.farm_id.in_(farm_ids))
    elif not farm_ids and not plot_ids:
        return []
    if plot_ids:
        q = q.filter(CropCycle.plot_id.in_(plot_ids))
    cycles = q.all()
    return cycles


def _in_window(value: Optional[str], start: Optional[datetime],
               end: Optional[datetime]) -> bool:
    """True when an ISO date string falls inside [start, end]. Missing/unparseable
    values are kept so scope-level records are never silently dropped."""
    if not value:
        return True
    d = _to_date(value)
    if d is None:
        return True
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def _cycle_in_window(c: CropCycle, start: Optional[datetime],
                     end: Optional[datetime]) -> bool:
    """True when a crop cycle's recorded activity (sowing..harvest) overlaps
    [start, end]. Cycles with no known timing are kept for the scope."""
    s = _to_date(c.sowing_date)
    h = _to_date(c.actual_harvest_date or c.expected_harvest_date)
    if s is None and h is None:
        return True
    if s is not None and h is not None:
        if s <= end and h >= start:
            return True
        # fall back to any known date falling inside the window
        if start and s >= start and s <= end:
            return True
        if start and h >= start and h <= end:
            return True
        return False
    d = s or h
    if d is None:
        return True
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def _cycles_in_window(cycles: List[CropCycle], date_from: Optional[str] = None,
                      date_to: Optional[str] = None) -> List[CropCycle]:
    """Keep cycles whose activity overlaps the requested date window. When no
    window is given, the full scope set is returned unchanged."""
    if not date_from and not date_to:
        return cycles
    start, end = _date_range(date_from, date_to)
    return [c for c in cycles if _cycle_in_window(c, start, end)]


def _date_col_condition(col, start: Optional[datetime], end: Optional[datetime]):
    conds = []
    if start:
        conds.append(col >= start)
    if end:
        conds.append(col <= end)
    return and_(*conds) if conds else True


# --------------------------------------------------------------------------- #
# Legacy endpoints kept for backward compatibility
# --------------------------------------------------------------------------- #
@router.get("/analytics/dashboard", response_model=dict)
def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_count = db.query(Farm).filter(Farm.user_id == current_user.id, Farm.is_active == True).count()
    active_crops = db.query(CropCycle).join(Farm).filter(Farm.user_id == current_user.id, CropCycle.status == "active").count()
    transaction_count = db.query(Transaction).filter(Transaction.user_id == current_user.id).count()
    booking_count = db.query(WorkerBooking).filter(WorkerBooking.farmer_id == current_user.id).count()
    order_count = db.query(MarketplaceOrder).filter(MarketplaceOrder.user_id == current_user.id).count()
    recent_ai = db.query(AIConversation).filter(AIConversation.user_id == current_user.id).count()

    return {
        "status": "success",
        "data": {
            "farms": farm_count,
            "active_crops": active_crops,
            "transactions": transaction_count,
            "worker_bookings": booking_count,
            "orders": order_count,
            "ai_conversations": recent_ai,
        },
    }


@router.get("/analytics/usage", response_model=dict)
def usage_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    logins = db.query(LoginHistory).filter(LoginHistory.user_id == current_user.id, LoginHistory.login_time >= since).count()
    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id, Transaction.created_at >= since).count()
    ai_calls = db.query(AIConversation).filter(AIConversation.user_id == current_user.id, AIConversation.created_at >= since).count()
    return {"status": "success", "data": {"period_days": days, "logins": logins, "transactions": transactions, "ai_calls": ai_calls}}


@router.get("/analytics/farm-health", response_model=dict)
def farm_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compute a farm-health score (0-100) from the authenticated farmer's real data."""
    farm_ids = [f[0] for f in db.query(Farm.id).filter(
        Farm.user_id == current_user.id, Farm.is_active == True
    ).all()]

    farm_score = 0.0
    if farm_ids:
        farms = db.query(Farm).filter(Farm.id.in_(farm_ids)).all()
        farm_score += 20.0
        if len(farms) == len(farm_ids):
            farm_score += 20.0
        if any(f.soil_type for f in farms):
            farm_score += 20.0
        if any(f.water_source for f in farms):
            farm_score += 20.0
        if any((f.total_area or 0) > 0 for f in farms):
            farm_score += 20.0

    crop_score = 0.0
    cycles = db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all() if farm_ids else []
    if cycles:
        total = len(cycles)
        active = sum(1 for c in cycles if (c.status or "").lower() == "active")
        harvested = sum(1 for c in cycles if c.actual_harvest_date)
        crop_score += 40.0
        crop_score += 40.0 * (active / total)
        crop_score += 20.0 * (harvested / total)

    task_score = 0.0
    cycle_ids = [c.id for c in cycles]
    tasks = db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).all() if cycle_ids else []
    if tasks:
        total = len(tasks)
        completed = sum(1 for t in tasks if (t.status or "").lower() == "completed")
        task_score = 100.0 * (completed / total)
    else:
        task_score = 50.0

    score = (0.30 * farm_score) + (0.40 * crop_score) + (0.30 * task_score)
    health = int(round(max(0.0, min(100.0, score))))
    completed_tasks = sum(1 for t in tasks if (t.status or "").lower() == "completed")

    return {
        "status": "success",
        "data": {
            "health": health,
            "farms": len(farm_ids),
            "active_crops": sum(1 for c in cycles if (c.status or "").lower() == "active"),
            "total_crops": len(cycles),
            "completed_tasks": completed_tasks,
            "total_tasks": len(tasks),
        },
    }


# --------------------------------------------------------------------------- #
# Context (header + selectors)
# --------------------------------------------------------------------------- #
@router.get("/analytics/context", response_model=dict)
def analytics_context(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms = (
        db.query(Farm)
        .filter(Farm.user_id == current_user.id, Farm.is_active == True)
        .order_by(Farm.created_at.asc())
        .all()
    )
    data = {
        "farmer": {
            "name": current_user.full_name or "Farmer",
            "farmer_id": current_user.farmer_id or current_user.id,
        },
        "farms": [
            {
                "id": f.id,
                "farm_id": f.farm_id,
                "farm_name": f.farm_name,
                "district": f.district,
                "state": f.state,
                "total_area": f.total_area,
                "area_unit": f.area_unit or "Acres",
                "plots": [
                    {
                        "id": p.id,
                        "plot_id": p.plot_id,
                        "plot_name": p.plot_name,
                        "area": p.area,
                    }
                    for p in f.plots
                ],
            }
            for f in farms
        ],
        "single_farm": len(farms) == 1,
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
@router.get("/analytics/overview", response_model=dict)
def analytics_overview(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_window(_cycles_in_scope(db, farm_ids, plot_ids), date_from, date_to)
    cycle_ids = [c.id for c in cycles]
    start, end = _date_range(date_from, date_to)

    total_area = sum(_acres(f.total_area, f.area_unit) for f in farms)
    sensors = _sensors_in_scope(db, current_user.id, farm_ids, plot_ids)

    tasks = db.query(CropTask).filter(
        CropTask.crop_cycle_id.in_(cycle_ids)
    ).all() if cycle_ids else []
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if (t.status or "").lower() == "completed")
    overdue_tasks = sum(
        1 for t in tasks
        if (t.status or "").lower() not in ("completed", "cancelled")
        and t.due_date and t.due_date < datetime.utcnow().strftime("%Y-%m-%d")
    )

    income_date_cond = _date_col_condition(Income.income_date, start, end)
    expense_date_cond = _date_col_condition(Expense.expense_date, start, end)
    txn_date_cond = _date_col_condition(Transaction.transaction_date, start, end)
    income = _num(
        db.query(func.coalesce(func.sum(Income.amount), 0.0))
        .filter(Income.user_id == current_user.id)
        .filter(income_date_cond)
        .filter(Income.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    )
    txn_income = _num(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == current_user.id, Transaction.type == "income")
        .filter(txn_date_cond)
        .filter(Transaction.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    )
    expenses = _num(
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.user_id == current_user.id)
        .filter(expense_date_cond)
        .filter(Expense.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    )
    txn_expenses = _num(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == current_user.id, Transaction.type == "expense")
        .filter(txn_date_cond)
        .filter(Transaction.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    )
    total_income = _r2((income or 0) + (txn_income or 0))
    total_expenses = _r2((expenses or 0) + (txn_expenses or 0))
    net = _r2((total_income or 0) - (total_expenses or 0))

    active_cycles = sum(1 for c in cycles if (c.status or "").lower() == "active")
    harvested = sum(1 for c in cycles if c.actual_harvest_date)
    crop_names = sorted({c.crop.name for c in cycles if c.crop and c.crop.name})

    data = {
        "farms": len(farms),
        "plots": len(plots),
        "total_area_acres": _r2(total_area),
        "area_unit": "Acres",
        "cycles": len(cycles),
        "active_cycles": active_cycles,
        "harvested_cycles": harvested,
        "crop_names": crop_names,
        "sensors": len(sensors),
        "connected_sensors": sum(1 for s in sensors if getattr(s, "status", "connected") != "offline"),
        "tasks_total": total_tasks,
        "tasks_completed": completed_tasks,
        "tasks_completion_pct": _pct(completed_tasks, total_tasks),
        "tasks_overdue": overdue_tasks,
        "income": total_income,
        "expenses": total_expenses,
        "net_profit": net,
        "has_data": bool(farms or cycles),
        "period": {"from": date_from or None, "to": date_to or None},
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Performance score (transparent formula)
# --------------------------------------------------------------------------- #
@router.get("/analytics/performance", response_model=dict)
def analytics_performance(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_scope(db, farm_ids, plot_ids)
    cycle_ids = [c.id for c in cycles]
    tasks = db.query(CropTask).filter(
        CropTask.crop_cycle_id.in_(cycle_ids)
    ).all() if cycle_ids else []
    sensors = _sensors_in_scope(db, current_user.id, farm_ids, plot_ids)

    # Data foundation (25 pts): farms + their info completeness
    if farms:
        foundation_present = 0
        foundation_total = 0
        for f in farms:
            foundation_total += 5
            for attr in ("soil_type", "water_source", "total_area"):
                foundation_total += 5
                if getattr(f, attr, None):
                    foundation_present += 5
        foundation_score = 25.0 * (foundation_present / foundation_total) if foundation_total else 0.0
    else:
        foundation_score = 0.0

    # Crop activity (30 pts): cycles + activity balance
    crop_score = 0.0
    if cycles:
        total = len(cycles)
        active = sum(1 for c in cycles if (c.status or "").lower() == "active")
        harvested = sum(1 for c in cycles if c.actual_harvest_date)
        crop_score = 30.0 * (0.4 + 0.3 * (active / total) + 0.3 * (harvested / total))
        crop_score = min(crop_score, 30.0)

    # Task completion (20 pts)
    task_score = 0.0
    if tasks:
        completed = sum(1 for t in tasks if (t.status or "").lower() == "completed")
        task_score = 20.0 * (completed / len(tasks))

    # Financial health (15 pts): net profit is positive or income exists
    income = _num(
        db.query(func.coalesce(func.sum(Income.amount), 0.0))
        .filter(Income.user_id == current_user.id)
        .filter(Income.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    ) or 0
    expenses = _num(
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.user_id == current_user.id)
        .filter(Expense.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    ) or 0
    txn_income = _num(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == current_user.id, Transaction.type == "income")
        .filter(Transaction.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    ) or 0
    txn_expenses = _num(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == current_user.id, Transaction.type == "expense")
        .filter(Transaction.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    ) or 0
    total_income = income + txn_income
    total_expenses = expenses + txn_expenses
    if total_income > 0:
        financial_score = 15.0 if (total_income - total_expenses) >= 0 else 15.0 * (total_income / (total_income + total_expenses))
    elif total_expenses > 0:
        financial_score = 5.0
    else:
        financial_score = 0.0

    # Monitoring & planning (10 pts): sensors + calendar events
    plans_score = 0.0
    active_sensors = sum(1 for s in sensors if getattr(s, "status", "connected") != "offline")
    if active_sensors:
        plans_score += min(5.0, active_sensors * 2.5)
    events_q = db.query(CalendarEvent).filter(CalendarEvent.farmer_id == current_user.id)
    if farm_ids:
        events_q = events_q.filter(or_(CalendarEvent.farm_id.is_(None), CalendarEvent.farm_id.in_(farm_ids)))
    if events_q.count():
        plans_score += 5.0

    score = round(
        foundation_score + crop_score + task_score + financial_score + plans_score
    )

    sufficient = bool(cycles or tasks or total_income > 0)
    data = {
        "score": int(max(0, min(100, score))) if sufficient else None,
        "sufficient_data": sufficient,
        "components": {
            "foundation": _r2(foundation_score),
            "crop_activity": _r2(crop_score),
            "task_completion": _r2(task_score),
            "financial_health": _r2(financial_score),
            "monitoring_planning": _r2(plans_score),
        },
        "known": {
            "farms": len(farms),
            "cycles": len(cycles),
            "tasks": len(tasks),
            "sensors": len(sensors),
            "income_total": _r2(total_income),
            "expenses_total": _r2(total_expenses),
        },
        "formula": (
            "Score = Data foundation (25) + Crop activity (30) + Task completion (20) "
            "+ Financial health (15) + Monitoring & planning (10). "
            "It measures how complete and active your farm records are."
        ),
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Crop performance
# --------------------------------------------------------------------------- #
@router.get("/analytics/crops", response_model=dict)
def analytics_crops(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_window(_cycles_in_scope(db, farm_ids, plot_ids), date_from, date_to)
    farm_map = {f.id: f for f in farms}
    plot_map = {p.id: p for p in plots}

    farm_expense_total = _num(
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.user_id == current_user.id)
        .filter(Expense.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    ) or 0
    # Per-farm expense split for attribution to exactly one cycle.
    per_farm_expense: Dict[str, float] = {}
    for f in farms:
        exp = _num(
            db.query(func.coalesce(func.sum(Expense.amount), 0.0))
            .filter(Expense.user_id == current_user.id, Expense.farm_id == f.id)
            .scalar()
        )
        farm_cycle_count = db.query(CropCycle).filter(CropCycle.farm_id == f.id).count()
        per_farm_expense[f.id] = (exp or 0) / farm_cycle_count if farm_cycle_count else (exp or 0)

    rows = []
    for c in cycles:
        farm = farm_map.get(c.farm_id)
        plot = plot_map.get(c.plot_id)
        area = _acres(plot.area if plot and plot.area else farm.total_area if farm else None,
                      farm.area_unit if farm else None)
        yield_per_acre = _r2(_num(c.yield_quantity) / area) if area and c.yield_quantity is not None else None
        revenue = _num(c.revenue)
        allocated_expense = _r2(per_farm_expense.get(c.farm_id, 0))
        rows.append({
            "cycle_id": c.id,
            "crop_name": c.crop.name if c.crop else "Unknown crop",
            "variety": c.crop.variety if c.crop else None,
            "farm_name": farm.farm_name if farm else None,
            "plot_name": plot.plot_name if plot else None,
            "area_acres": _r2(area),
            "sowing_date": c.sowing_date,
            "expected_harvest_date": c.expected_harvest_date,
            "actual_harvest_date": c.actual_harvest_date,
            "current_stage": c.current_stage,
            "status": c.status,
            "yield_quantity": _num(c.yield_quantity),
            "yield_unit": c.yield_unit or "kg",
            "yield_per_acre": yield_per_acre,
            "revenue": _r2(revenue),
            "expenses": allocated_expense,
            "profit": _r2((revenue or 0) - (allocated_expense or 0)) if revenue is not None else None,
            "profit_per_acre": _r2((((revenue or 0) - (allocated_expense or 0)) / area)) if revenue is not None and area else None,
        })

    return {"status": "success", "data": {"crops": rows, "total": len(rows)}}


# --------------------------------------------------------------------------- #
# Yield analysis (expected vs actual, only real values)
# --------------------------------------------------------------------------- #
@router.get("/analytics/yield", response_model=dict)
def analytics_yield(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_window(_cycles_in_scope(db, farm_ids, plot_ids), date_from, date_to)
    farm_map = {f.id: f for f in farms}
    plot_map = {p.id: p for p in plots}

    benchmark_q = (
        db.query(CropCycle)
        .join(Farm)
        .filter(Farm.user_id == current_user.id, CropCycle.yield_quantity.isnot(None))
    )
    if farm_ids:
        benchmark_q = benchmark_q.filter(CropCycle.farm_id.in_(farm_ids))

    per_crop_sum: Dict[str, float] = {}
    per_crop_cnt: Dict[str, int] = {}
    for b in benchmark_q.all():
        key = b.crop.name if b.crop else None
        if not key:
            continue
        per_crop_sum[key] = per_crop_sum.get(key, 0) + (_num(b.yield_quantity) or 0)
        per_crop_cnt[key] = per_crop_cnt.get(key, 0) + 1

    series = []
    for c in cycles:
        if c.yield_quantity is None:
            series.append({
                "cycle_id": c.id,
                "crop_name": c.crop.name if c.crop else "Unknown crop",
                "farm_name": (farm_map.get(c.farm_id).farm_name if farm_map.get(c.farm_id) else None),
                "actual_harvest_date": c.actual_harvest_date,
                "expected_harvest_date": c.expected_harvest_date,
                "yield_quantity": None,
                "yield_unit": c.yield_unit or "kg",
                "yield_per_acre": None,
                "benchmark_per_acre": None,
                "deviation_pct": None,
            })
            continue
        farm = farm_map.get(c.farm_id)
        plot = plot_map.get(c.plot_id)
        area = _acres(plot.area if plot and plot.area else farm.total_area if farm else None,
                      farm.area_unit if farm else None)
        per_acre = (_num(c.yield_quantity) / area) if area else None
        key = c.crop.name if c.crop else None
        benchmark = (per_crop_sum.get(key, 0) / per_crop_cnt.get(key, 1)) if key else None
        deviation = _pct((_num(c.yield_quantity) - benchmark) if benchmark is not None else None, benchmark) if benchmark else None
        series.append({
            "cycle_id": c.id,
            "crop_name": c.crop.name if c.crop else "Unknown crop",
            "farm_name": (farm_map.get(c.farm_id).farm_name if farm_map.get(c.farm_id) else None),
            "actual_harvest_date": c.actual_harvest_date,
            "expected_harvest_date": c.expected_harvest_date,
            "yield_quantity": _num(c.yield_quantity),
            "yield_unit": c.yield_unit or "kg",
            "yield_per_acre": _r2(per_acre),
            "benchmark_per_acre": _r2(per_crop_sum.get(key, 0) / per_crop_cnt.get(key, 1)) if key and per_crop_cnt.get(key) else None,
            "deviation_pct": _r2(deviation),
        })

    return {"status": "success", "data": {
        "series": series,
        "total_with_yield": sum(1 for s in series if s["yield_quantity"] is not None),
        "note": "Compared against the average yield recorded for the same crop on your farms (actual recorded data only).",
    }}


# --------------------------------------------------------------------------- #
# Production analysis
# --------------------------------------------------------------------------- #
@router.get("/analytics/production", response_model=dict)
def analytics_production(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_window(_cycles_in_scope(db, farm_ids, plot_ids), date_from, date_to)

    monthly: Dict[str, Dict[str, Any]] = {}
    by_crop: Dict[str, Dict[str, Any]] = {}
    for c in cycles:
        if c.yield_quantity is None:
            continue
        if c.actual_harvest_date:
            month_key = c.actual_harvest_date[:7]
            label = month_key
        else:
            month_key = "planned"
            label = "Planned"
        entry = monthly.setdefault(month_key, {"key": month_key, "label": label, "total": 0.0, "unit": c.yield_unit or "kg"})
        entry["total"] += _num(c.yield_quantity) or 0
        crop_name = c.crop.name if c.crop else "Unknown crop"
        ce = by_crop.setdefault(crop_name, {"crop_name": crop_name, "total": 0.0, "unit": c.yield_unit or "kg", "count": 0})
        ce["total"] += _num(c.yield_quantity) or 0
        ce["count"] += 1

    for e in monthly.values():
        e["total"] = _r2(e["total"])
    for e in by_crop.values():
        e["total"] = _r2(e["total"])

    ordered = sorted(monthly.values(), key=lambda x: x["key"])
    return {"status": "success", "data": {
        "monthly": ordered,
        "by_crop": sorted(by_crop.values(), key=lambda x: x["total"] or 0, reverse=True),
        "note": "Derived from recorded harvests (actual_harvest_date) and yield_quantity only.",
    }}


# --------------------------------------------------------------------------- #
# Financial analysis (farm only - wallet excluded)
# --------------------------------------------------------------------------- #
@router.get("/analytics/financial", response_model=dict)
def analytics_financial(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    start, end = _date_range(date_from, date_to)

    def _filter_date(col):
        conds = []
        if start:
            conds.append(col >= start)
        if end:
            conds.append(col <= end)
        return and_(*conds) if conds else True

    income_cond = (
        Income.user_id == current_user.id,
        _filter_date(Income.income_date),
    )
    if farm_ids:
        income_cond = income_cond + (Income.farm_id.in_(farm_ids),)
    expense_cond = (
        Expense.user_id == current_user.id,
        _filter_date(Expense.expense_date),
    )
    if farm_ids:
        expense_cond = expense_cond + (Expense.farm_id.in_(farm_ids),)

    income_rows = db.query(Income).filter(*income_cond).all()
    expense_rows = db.query(Expense).filter(*expense_cond).all()

    income_by_cat: Dict[str, float] = {}
    expense_by_cat: Dict[str, float] = {}
    total_income = 0.0
    total_expenses = 0.0
    monthly_map: Dict[str, Dict[str, float]] = {}

    for i in income_rows:
        amount = _num(i.amount) or 0
        total_income += amount
        key = i.category or "Other"
        income_by_cat[key] = income_by_cat.get(key, 0) + amount
        if i.income_date:
            mkey = i.income_date.strftime("%Y-%m")
            monthly_map.setdefault(mkey, {"income": 0.0, "expenses": 0.0})["income"] += amount

    for e in expense_rows:
        amount = _num(e.amount) or 0
        total_expenses += amount
        key = e.category or "Other"
        expense_by_cat[key] = expense_by_cat.get(key, 0) + amount
        if e.expense_date:
            mkey = e.expense_date.strftime("%Y-%m")
            monthly_map.setdefault(mkey, {"income": 0.0, "expenses": 0.0})["expenses"] += amount

    # 12-month series
    series = []
    now = datetime.utcnow()
    for offset in range(11, -1, -1):
        anchor = now.replace(day=1) - timedelta(days=offset * 30)
        anchor = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        key = anchor.strftime("%Y-%m")
        row = monthly_map.get(key, {"income": 0.0, "expenses": 0.0})
        series.append({
            "month": anchor.strftime("%b %Y"),
            "key": key,
            "income": _r2(row["income"]),
            "expenses": _r2(row["expenses"]),
            "net": _r2(row["income"] - row["expenses"]),
        })

    income_cats = sorted(
        ({"category": k, "amount": _r2(v)} for k, v in income_by_cat.items()),
        key=lambda x: x["amount"] or 0, reverse=True,
    )
    expense_cats = sorted(
        ({"category": k, "amount": _r2(v)} for k, v in expense_by_cat.items()),
        key=lambda x: x["amount"] or 0, reverse=True,
    )

    total_area = sum(_acres(f.total_area, f.area_unit) for f in farms)
    net = _r2(total_income - total_expenses)
    data = {
        "income": _r2(total_income),
        "expenses": _r2(total_expenses),
        "net_profit": net,
        "profit_ratio_pct": _pct(net, total_income),
        "profit_per_acre": _r2((total_income - total_expenses) / total_area) if total_area else None,
        "monthly": series,
        "income_by_category": income_cats,
        "expense_by_category": expense_cats,
        "known_categories": EXPENSE_CATEGORY_ORDER,
        "note": "Farm finances only (Income/Expense records). Personal wallet transactions are excluded.",
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Tasks & farm activity
# --------------------------------------------------------------------------- #
@router.get("/analytics/tasks", response_model=dict)
def analytics_tasks(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_window(_cycles_in_scope(db, farm_ids, plot_ids), date_from, date_to)
    cycle_ids = [c.id for c in cycles]
    tasks = db.query(CropTask).filter(
        CropTask.crop_cycle_id.in_(cycle_ids)
    ).all() if cycle_ids else []
    cycle_map = {c.id: c for c in cycles}

    status_counts: Dict[str, int] = {}
    overdue = []
    recent = []
    for t in sorted(tasks, key=lambda x: x.due_date or "", reverse=True):
        st = (t.status or "pending").lower()
        status_counts[st] = status_counts.get(st, 0) + 1
        cyc = cycle_map.get(t.crop_cycle_id)
        recent.append({
            "task_id": t.id,
            "title": t.title,
            "category": t.category,
            "due_date": t.due_date,
            "status": st,
            "priority": t.priority,
            "crop_name": cyc.crop.name if cyc and cyc.crop else None,
            "farm_name": (farms and next((f.farm_name for f in farms if f.id == cyc.farm_id), None)) or None,
        })
        if st not in ("completed", "cancelled") and t.due_date and t.due_date < datetime.utcnow().strftime("%Y-%m-%d"):
            overdue.append(recent[-1])

    total = len(tasks)
    completed = status_counts.get("completed", 0)
    data = {
        "total": total,
        "by_status": status_counts,
        "completion_pct": _pct(completed, total),
        "overdue_count": len(overdue),
        "recent": recent[:30],
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Farm calendar analysis
# --------------------------------------------------------------------------- #
@router.get("/analytics/calendar", response_model=dict)
def analytics_calendar(
    farm_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(CalendarEvent).filter(CalendarEvent.farmer_id == current_user.id)
    if farm_id:
        q = q.filter(or_(CalendarEvent.farm_id.is_(None), CalendarEvent.farm_id == farm_id))
    start, end = _date_range(date_from, date_to)
    if start:
        q = q.filter(or_(CalendarEvent.start_datetime.is_(None), CalendarEvent.start_datetime >= start))
    if end:
        q = q.filter(or_(CalendarEvent.start_datetime.is_(None), CalendarEvent.start_datetime <= end))
    events = q.order_by(CalendarEvent.start_datetime.desc()).all()

    status_counts: Dict[str, int] = {}
    upcoming = []
    for e in events:
        st = (e.status or "scheduled").lower()
        status_counts[st] = status_counts.get(st, 0) + 1
        upcoming.append({
            "id": e.id,
            "title": e.title,
            "event_type": e.event_type,
            "status": st,
            "priority": e.priority,
            "farm_name": e.farm_name,
            "start": str(e.start_datetime) if e.start_datetime else None,
        })

    data = {
        "total": len(events),
        "by_status": status_counts,
        "events": upcoming[:25],
        "note": "From your farm calendar. 'Overdue' events are counted in the risk analysis.",
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Weather analysis
# --------------------------------------------------------------------------- #
@router.get("/analytics/weather", response_model=dict)
def analytics_weather(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    lat = lon = None
    target = None
    if plots:
        target = plots[0]
        lat, lon = target.latitude, target.longitude
    if lat is None and farms:
        target = farms[0]
        lat, lon = target.latitude, target.longitude

    weather = None
    if lat and lon:
        try:
            weather = asyncio.run(get_current_weather(float(lat), float(lon)))
        except Exception:
            weather = None

    location = None
    if target:
        if isinstance(target, FarmPlot):
            farm = db.query(Farm).get(target.farm_id) if target.farm_id else None
            location = (farm.farm_name if farm else None) or target.plot_name
        else:
            location = target.farm_name or target.district or None

    data = {
        "location": location,
        "current": weather,
        "history_available": False,
        "history_note": "Historical weather analysis is not available. Current conditions are shown from live weather data.",
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Market analysis for the farmer's crops
# --------------------------------------------------------------------------- #
@router.get("/analytics/market", response_model=dict)
def analytics_market(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_scope(db, farm_ids, plot_ids)

    crop_names = sorted({c.crop.name for c in cycles if c.crop and c.crop.name})
    if not crop_names:
        return {"status": "success", "data": {
            "crops": [], "crops_with_prices": 0,
            "note": "No crops recorded yet, so no market prices can be matched.",
        }}

    like_conds = [func.lower(MarketPrice.commodity) == name.lower() for name in crop_names]
    rows = (
        db.query(MarketPrice)
        .filter(or_(*like_conds))
        .order_by(MarketPrice.price_date.desc())
        .all()
    )
    best: Dict[str, MarketPrice] = {}
    for row in rows:
        key = row.commodity.lower()
        if key not in best or (row.price_date or "") > (best[key].price_date or ""):
            best[key] = row

    # chronological price history per commodity (for trend sparklines)
    trends: Dict[str, List[Dict[str, str]]] = {}
    history = sorted(rows, key=lambda r: (r.commodity.lower(), r.price_date or ""))
    for row in history:
        key = (row.commodity or "").lower()
        if not key:
            continue
        trends.setdefault(key, []).append({
            "date": row.price_date,
            "price": _r2(_num(row.modal_price)),
            "market": row.market,
        })
    for key in trends:
        if len(trends[key]) > 10:
            trends[key] = trends[key][-10:]

    def _commodity_stats(key: str) -> Dict[str, Any]:
        series = [r for r in history if (r.commodity or "").lower() == key]
        prices = [_num(r.modal_price) for r in series if _num(r.modal_price) is not None]
        highest = max(prices) if prices else None
        slim = [p for p in prices if p is not None]
        change_pct = None
        if len(slim) >= 2:
            latest = slim[-1]
            previous = slim[-2] or 0
            if previous:
                change_pct = round(((latest - previous) / previous) * 100.0, 1)
        return {
            "highest_price": _r2(highest),
            "price_change_pct": change_pct,
        }

    latest_date = max((r.price_date for r in rows if r.price_date), default=None)
    yield_by_crop: Dict[str, float] = {}
    unit_by_crop: Dict[str, str] = {}
    for c in cycles:
        if c.yield_quantity is None or not c.crop:
            continue
        name = c.crop.name
        yield_by_crop.setdefault(name, 0.0)
        yield_by_crop[name] += _num(c.yield_quantity) or 0
        unit_by_crop.setdefault(name, c.yield_unit or "kg")

    crops = []
    matched = 0
    for name in crop_names:
        key = name.lower()
        row = best.get(key)
        if not row:
            crops.append({
                "crop_name": name,
                "available": False,
                "modal_price": None,
                "unit": "Rs/Quintal",
                "market": None,
                "price_date": None,
                "trend": trends.get(key, []),
                "highest_price": None,
                "price_change_pct": None,
            })
            continue
        matched += 1
        modal = _num(row.modal_price)
        estimated = None
        yield_qty = yield_by_crop.get(name)
        if modal is not None and yield_qty:
            # field records are in kg by default; market unit is Rs per Quintal (100 kg)
            if (unit_by_crop.get(name) or "kg").lower() in ("quote", "quintal", "q"):
                estimated = _r2(yield_qty * modal)
            else:
                estimated = _r2((yield_qty / 100.0) * modal)
        stats = _commodity_stats(key)
        crops.append({
            "crop_name": name,
            "available": True,
            "commodity": row.commodity,
            "variety": row.variety,
            "modal_price": _r2(modal),
            "unit": row.unit or "Rs/Quintal",
            "market": row.market,
            "district": row.district,
            "state": row.state,
            "price_date": row.price_date,
            "trend": trends.get(key, []),
            "highest_price": stats["highest_price"],
            "price_change_pct": stats["price_change_pct"],
            "estimated_potential_revenue": estimated,
            "estimated_label": "Estimated potential revenue at today's market price",
        })

    return {"status": "success", "data": {
        "crops": crops,
        "crops_with_prices": matched,
        "latest_price_date": latest_date,
        "note": "Prices are live AGMARKNET market data. Yields come from your recorded harvests.",
    }}


# --------------------------------------------------------------------------- #
# Sustainability (only existing recorded data)
# --------------------------------------------------------------------------- #
@router.get("/analytics/sustainability", response_model=dict)
def analytics_sustainability(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)

    items = []
    if not farm_ids:
        return {"status": "success", "data": {
            "items": [], "notes": ["Add a farm to start tracking sustainable practices."],
        }}

    soil_rows = []
    if plot_ids:
        soil_rows = db.query(SoilRecord).filter(SoilRecord.plot_id.in_(plot_ids)).all()
    for s in soil_rows:
        items.append({
            "kind": "soil_test",
            "label": f"Soil test #{str(s.id)[:8]}",
            "detail": (
                f"pH {s.ph_level}" if s.ph_level is not None else "Tests run"
            ),
        })

    journal_rows = (
        db.query(FarmJournal)
        .filter(FarmJournal.user_id == current_user.id)
        .filter(FarmJournal.farm_id.in_(farm_ids) if farm_ids else True)
        .all()
    )
    for j in journal_rows[:10]:
        items.append({"kind": "activity", "label": j.activity, "detail": j.notes or ""})

    irrigation_practices = []
    for f in farms:
        if f.irrigation_method:
            irrigation_practices.append(f.irrigation_method)
        if f.water_source:
            irrigation_practices.append(f"water: {f.water_source}")
    if irrigation_practices:
        items.append({
            "kind": "irrigation",
            "label": "Irrigation practices",
            "detail": "; ".join(sorted(set(irrigation_practices))),
        })

    if not items:
        return {"status": "success", "data": {
            "items": [],
            "notes": [
                "Sustainability data is not available yet. "
                "Add soil tests, irrigation practices or farm journal activities to enable this analysis."
            ],
        }}
    return {"status": "success", "data": {"items": items, "notes": []}}


# --------------------------------------------------------------------------- #
# Farm risk analysis
# --------------------------------------------------------------------------- #
@router.get("/analytics/risks", response_model=dict)
def analytics_risks(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_scope(db, farm_ids, plot_ids)
    cycle_ids = [c.id for c in cycles]

    reasons: List[Dict[str, str]] = []

    tasks = db.query(CropTask).filter(
        CropTask.crop_cycle_id.in_(cycle_ids)
    ).all() if cycle_ids else []
    today = datetime.utcnow().strftime("%Y-%m-%d")
    overdue_tasks = [
        t for t in tasks
        if (t.status or "").lower() not in ("completed", "cancelled")
        and t.due_date and t.due_date < today
    ]
    if overdue_tasks:
        reasons.append({
            "severity": "Moderate",
            "text": f"{len(overdue_tasks)} task(s) are overdue and may delay current crop activity.",
        })

    from app.models.monitoring import MonitoringAlert
    alerts_q = db.query(MonitoringAlert).filter(
        MonitoringAlert.user_id == current_user.id,
        MonitoringAlert.status == "active",
    )
    if farm_ids:
        alerts_q = alerts_q.filter(MonitoringAlert.farm_id.in_(farm_ids))
    critical_alerts = [a for a in alerts_q.all() if a.severity == "critical"]
    warning_alerts = [a for a in alerts_q.all() if a.severity in ("warning", "info")]
    if critical_alerts:
        reasons.append({
            "severity": "High",
            "text": f"{len(critical_alerts)} critical sensor alert(s) are active and need attention.",
        })
    elif warning_alerts:
        reasons.append({
            "severity": "Moderate",
            "text": f"{len(warning_alerts)} sensor alert(s) are active.",
        })

    income = _num(
        db.query(func.coalesce(func.sum(Income.amount), 0.0))
        .filter(Income.user_id == current_user.id)
        .filter(Income.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    ) or 0
    expenses = _num(
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.user_id == current_user.id)
        .filter(Expense.farm_id.in_(farm_ids) if farm_ids else True)
        .scalar()
    ) or 0
    if income > 0 and expenses > income:
        reasons.append({
            "severity": "Moderate",
            "text": "Recorded expenses are higher than recorded income for this scope.",
        })
    elif not income and expenses:
        reasons.append({
            "severity": "Low",
            "text": "Expenses are recorded but no farm income is recorded yet.",
        })

    planned_today = [
        c for c in cycles
        if (c.status or "").lower() == "active"
        and c.expected_harvest_date and c.expected_harvest_date < today
        and not c.actual_harvest_date
    ]
    if planned_today:
        reasons.append({
            "severity": "Moderate",
            "text": f"{len(planned_today)} active crop cycle(s) passed their expected harvest date without a recorded harvest.",
        })

    # Weather risk (real forecast)
    lat = lon = None
    if plots:
        lat, lon = plots[0].latitude, plots[0].longitude
    if lat is None and farms:
        lat, lon = farms[0].latitude, farms[0].longitude
    if lat and lon:
        try:
            w = asyncio.run(get_current_weather(float(lat), float(lon)))
            temp = _num((w or {}).get("current", {}).get("temperature_2m")) if w else None
            if temp is not None and temp >= 38:
                reasons.append({"severity": "Moderate", "text": f"Current temperature is {temp:g}°C; heat stress risk for crops."})
        except Exception:
            pass

    order = {"Low": 0, "Moderate": 1, "High": 2, "Critical": 3}
    if not reasons:
        level = "Low"
        color = "green"
    else:
        worst = max(reasons, key=lambda r: order.get(r["severity"], 0))["severity"]
        level = worst
        color = {"Low": "green", "Moderate": "amber", "High": "orange", "Critical": "red"}.get(worst, "amber")

    data = {
        "level": level,
        "color": color,
        "counts": {
            "low": len([r for r in reasons if r["severity"] == "Low"]),
            "moderate": len([r for r in reasons if r["severity"] == "Moderate"]),
            "high": len([r for r in reasons if r["severity"] == "High"]),
            "critical": len([r for r in reasons if r["severity"] == "Critical"]),
        },
        "reasons": reasons,
        "note": "Risk is estimated from your recorded data only: overdue tasks, active sensor alerts, farm finances, delayed harvests and live weather.",
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Insurance
# --------------------------------------------------------------------------- #
@router.get("/analytics/insurance", response_model=dict)
def analytics_insurance(
    farm_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InsurancePolicy).filter(InsurancePolicy.user_id == current_user.id)
    if farm_id:
        q = q.filter(InsurancePolicy.farm_id == farm_id)
    policies = q.order_by(InsurancePolicy.created_at.desc()).all()

    if not policies:
        return {"status": "success", "data": {
            "available": False,
            "policies": [],
            "message": "You have no insurance policies yet. Protect your farm with an insurance plan.",
        }}

    total_coverage = sum(_num(p.coverage_amount or p.sum_insured) or 0 for p in policies)
    total_premium = sum(_num(p.premium_paid or p.premium) or 0 for p in policies)
    active = sum(1 for p in policies if (p.status or "").lower() == "active")

    return {"status": "success", "data": {
        "available": True,
        "count": len(policies),
        "active": active,
        "total_coverage": _r2(total_coverage),
        "total_premium_paid": _r2(total_premium),
        "policies": [
            {
                "policy_id": p.policy_id,
                "policy_type": p.policy_type,
                "status": p.status,
                "provider": p.provider,
                "coverage": _num(p.coverage_amount or p.sum_insured),
                "premium": _num(p.premium_paid or p.premium),
                "start_date": p.start_date,
                "end_date": p.end_date,
            }
            for p in policies
        ],
    }}


# --------------------------------------------------------------------------- #
# Data completeness
# --------------------------------------------------------------------------- #
@router.get("/analytics/completeness", response_model=dict)
def analytics_completeness(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_scope(db, farm_ids, plot_ids)
    cycle_ids = [c.id for c in cycles]

    sections = [
        {"key": "farms", "label": "Farm details", "present": bool(farms),
         "help": "Add Farm"},
        {"key": "crops", "label": "Crop cycles", "present": bool(cycles),
         "help": "Add Crop"},
        {"key": "tasks", "label": "Farm activity (tasks)", "present": bool(cycle_ids and db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).first()),
         "help": "Record Farm Activity"},
        {"key": "income", "label": "Income records", "present": bool(db.query(Income).filter(Income.user_id == current_user.id, Income.farm_id.in_(farm_ids) if farm_ids else True).first()),
         "help": "Record Income"},
        {"key": "expenses", "label": "Expense records", "present": bool(db.query(Expense).filter(Expense.user_id == current_user.id, Expense.farm_id.in_(farm_ids) if farm_ids else True).first()),
         "help": "Record Expense"},
        {"key": "yield", "label": "Harvest yield records", "present": bool(any(c.yield_quantity is not None for c in cycles)),
         "help": "Record Harvest"},
    ]
    soil_present = False
    if plot_ids:
        soil_present = bool(db.query(SoilRecord).filter(SoilRecord.plot_id.in_(plot_ids)).first())
    sections.append({"key": "soil", "label": "Soil tests", "present": soil_present, "help": "Add Soil Test"})
    sections.append({"key": "sensors", "label": "Connected sensors", "present": bool(_sensors_in_scope(db, current_user.id, farm_ids, plot_ids)), "help": "Add Sensor"})

    insurance_present = bool(
        db.query(InsurancePolicy)
        .filter(InsurancePolicy.user_id == current_user.id)
        .filter(InsurancePolicy.farm_id.in_(farm_ids) if farm_ids else True)
        .first()
    )
    sections.append({"key": "insurance", "label": "Insurance coverage", "present": insurance_present, "help": "Explore Insurance"})

    weather_present = any(
        (f.latitude is not None and f.longitude is not None) for f in farms
    ) or any(
        (p.latitude is not None and p.longitude is not None) for p in plots
    )
    sections.append({"key": "weather", "label": "Weather location", "present": weather_present, "help": "Set Farm Location"})

    crop_names = sorted({c.crop.name for c in cycles if c.crop and c.crop.name})
    market_present = False
    if crop_names:
        market_conds = [func.lower(MarketPrice.commodity) == name.lower() for name in crop_names]
        market_present = bool(db.query(MarketPrice).filter(or_(*market_conds)).first())
    sections.append({"key": "market", "label": "Market price data", "present": market_present, "help": "Market"})

    present = sum(1 for s in sections if s["present"])
    total = len(sections)

    data = {
        "percent": _pct(present, total),
        "present": present,
        "total": total,
        "sections": sections,
    }
    return {"status": "success", "data": data}


# --------------------------------------------------------------------------- #
# Smart insights (deterministic, data-backed only)
# --------------------------------------------------------------------------- #
@router.get("/analytics/insights", response_model=dict)
def analytics_insights(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_window(_cycles_in_scope(db, farm_ids, plot_ids), date_from, date_to)
    insights: List[Dict[str, Any]] = []

    if not farms and not cycles:
        return {"status": "success", "data": {
            "insights": [],
            "note": "Your farm analytics will appear here once you add your farm information.",
        }}

    # Crop season insight
    active = [c for c in cycles if (c.status or "").lower() == "active"]
    harvested = [c for c in cycles if c.actual_harvest_date]
    if cycles:
        insights.append({
            "type": "crops",
            "icon": "fas fa-seedling",
            "title": "Season overview",
            "detail": f"{len(active)} active and {len(harvested)} harvested crop cycle(s) are recorded across {len(farms)} farm(s).",
        })

    # Task progress insight
    cycle_ids = [c.id for c in cycles]
    tasks = db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).all() if cycle_ids else []
    if tasks:
        completed = sum(1 for t in tasks if (t.status or "").lower() == "completed")
        pct = _pct(completed, len(tasks))
        insights.append({
            "type": "tasks",
            "icon": "fas fa-list-check",
            "title": "Farm activity progress",
            "detail": f"{completed} of {len(tasks)} farm activities are complete ({pct}%).",
        })

    # Financial insight
    start, end = _date_range(date_from, date_to)
    _fin = lambda m: _num(db.query(func.coalesce(func.sum(m.amount), 0.0)).filter(m.user_id == current_user.id, m.farm_id.in_(farm_ids) if farm_ids else True).filter(_date_col_condition(m.expense_date if m is Expense else m.income_date, start, end)).scalar()) or 0
    income = _fin(Income)
    expenses = _fin(Expense)
    if income or expenses:
        net = income - expenses
        if net >= 0:
            insights.append({
                "type": "finance",
                "icon": "fas fa-wallet",
                "title": "Farm finances",
                "detail": f"Recorded income of ₹{income:,.0f} exceeds expenses of ₹{expenses:,.0f}, leaving a positive farm balance.",
            })
        else:
            insights.append({
                "type": "finance",
                "icon": "fas fa-wallet",
                "title": "Farm finances need review",
                "detail": f"Recorded expenses (₹{expenses:,.0f}) are higher than income (₹{income:,.0f}). Review spending for this period.",
            })

    # Expense change vs previous period of equal length
    if expenses and start and end and (end > start):
        span_days = (end - start).days
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=max(span_days, 0))
        prev_exp = _num(db.query(func.coalesce(func.sum(Expense.amount), 0.0)).filter(Expense.user_id == current_user.id, Expense.farm_id.in_(farm_ids) if farm_ids else True).filter(_date_col_condition(Expense.expense_date, prev_start, prev_end)).scalar()) or 0
        if prev_exp:
            change = round(((expenses - prev_exp) / prev_exp) * 100.0)
            if change > 5:
                insights.append({
                    "type": "finance",
                    "icon": "fas fa-arrow-up",
                    "title": "Spending increased",
                    "detail": f"Farm expenses rose {change}% compared with the previous period (₹{prev_exp:,.0f} → ₹{expenses:,.0f}). Review the largest cost items.",
                })
            elif change < -5:
                insights.append({
                    "type": "finance",
                    "icon": "fas fa-arrow-down",
                    "title": "Spending reduced",
                    "detail": f"Farm expenses fell {abs(change)}% compared with the previous period (₹{prev_exp:,.0f} → ₹{expenses:,.0f}). Keep up the good cost control.",
                })

    # Top expense category
    if expenses:
        cat_totals: Dict[str, float] = {}
        for cat in EXPENSE_CATEGORY_ORDER:
            cat_totals[cat] = 0.0
        exp_rows = db.query(Expense).filter(Expense.user_id == current_user.id, Expense.farm_id.in_(farm_ids) if farm_ids else True).filter(_date_col_condition(Expense.expense_date, start, end)).all()
        for e in exp_rows:
            key = e.category or "Other"
            cat_totals[key] = cat_totals.get(key, 0.0) + (_num(e.amount) or 0)
        top_cat = max(cat_totals.items(), key=lambda kv: kv[1])
        if top_cat[1] > 0:
            insights.append({
                "type": "expense",
                "icon": "fas fa-receipt",
                "title": "Top spending category",
                "detail": f"{top_cat[0] or 'Other'} is your highest expense category at ₹{top_cat[1]:,.0f} ({_pct(top_cat[1], expenses)}% of recorded spending).",
            })

    # Insurance renewals / expiries coming up
    now = datetime.utcnow()
    soon = now + timedelta(days=60)
    expiring = []
    for pol in db.query(InsurancePolicy).filter(InsurancePolicy.user_id == current_user.id, InsurancePolicy.farm_id.in_(farm_ids) if farm_ids else True).all():
        ed = _to_date(pol.end_date)
        if ed and now <= ed <= soon:
            expiring.append(pol)
    if expiring:
        names = ", ".join(sorted({(p.policy_type or "insurance") for p in expiring}))
        dates = ", ".join(sorted({p.end_date for p in expiring if p.end_date}))
        insights.append({
            "type": "insurance",
            "icon": "fas fa-shield-halved",
            "title": "Insurance renewals",
            "detail": f"{len(expiring)} insurance policy/policies are expiring soon ({names or 'n/a'}). Review renewal before {dates or 'the due date'}.",
        })

    # Market price movement
    crop_names = sorted({c.crop.name for c in cycles if c.crop and c.crop.name})
    if crop_names:
        market_conds = [func.lower(MarketPrice.commodity) == name.lower() for name in crop_names]
        mrows = db.query(MarketPrice).filter(or_(*market_conds)).order_by(MarketPrice.price_date.asc()).all()
        mseries: Dict[str, List[float]] = {}
        for r in mrows:
            key = (r.commodity or "").lower()
            p = _num(r.modal_price)
            if key and p is not None:
                mseries.setdefault(key, []).append(p)
        rises = []
        for key, series in mseries.items():
            if len(series) >= 2 and series[-2] and series[-1] > series[-2]:
                pct = round(((series[-1] - series[-2]) / series[-2]) * 100.0, 1)
                rises.append((key, series[-2], series[-1], pct))
        if rises:
            top, prev_p, latest_p, pct = max(rises, key=lambda r: r[3])
            crop_label = next((n for n in crop_names if n.lower() == top), top.title())
            insights.append({
                "type": "market",
                "icon": "fas fa-trend-up",
                "title": "Market prices rising",
                "detail": f"The quoted market price for {crop_label} rose {pct}% recently (₹{prev_p:,.0f} → ₹{latest_p:,.0f}). Consider timing your sale for better returns.",
            })

    # Production insight
    produced = sum(_num(c.yield_quantity) or 0 for c in cycles)
    if produced:
        insights.append({
            "type": "yield",
            "icon": "fas fa-weight-hanging",
            "title": "Recorded production",
            "detail": f"A total of {produced:,.0f} {cycles[0].yield_unit or 'kg'} of produce has been recorded from harvested cycles.",
        })

    # Task overdue insight
    today = datetime.utcnow().strftime("%Y-%m-%d")
    overdue = [
        t for t in tasks
        if (t.status or "").lower() not in ("completed", "cancelled")
        and t.due_date and t.due_date < today
    ] if tasks else []
    if overdue:
        insights.append({
            "type": "risk",
            "icon": "fas fa-triangle-exclamation",
            "title": "Overdue activities",
            "detail": f"{len(overdue)} farm activity/activities are overdue. Plan them soon to protect this season.",
        })

    if not insights:
        insights.append({
            "type": "empty",
            "icon": "fas fa-circle-info",
            "title": "Add more data",
            "detail": "Record crop cycles, farm activities, income and expenses to unlock smarter insights.",
        })

    return {"status": "success", "data": {"insights": insights}}


# --------------------------------------------------------------------------- #
# Livestock analysis (real records only, user-scoped - livestock has no farm id)
# --------------------------------------------------------------------------- #
@router.get("/analytics/livestock", response_model=dict)
def analytics_livestock(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.livestock import (
        Livestock, LivestockProductionRecord, LivestockExpenseRecord,
        LivestockVaccination, LivestockTreatment,
    )

    animals = (
        db.query(Livestock)
        .filter(Livestock.user_id == current_user.id)
        .order_by(Livestock.created_at.asc())
        .all()
    )
    total = len(animals)
    if total == 0:
        return {"status": "success", "data": {"present": False, "total": 0}}

    start, end = _date_range(date_from, date_to)
    by_type: Dict[str, int] = {}
    by_health: Dict[str, int] = {}
    for a in animals:
        by_type[a.animal_type or "other"] = by_type.get(a.animal_type or "other", 0) + 1
        by_health[a.health_status or "unknown"] = by_health.get(a.health_status or "unknown", 0) + 1

    animal_ids = [a.id for a in animals]

    prod_rows = [
        p for p in db.query(LivestockProductionRecord)
        .filter(LivestockProductionRecord.user_id == current_user.id)
        .all()
        if _in_window(p.record_date, start, end)
    ]
    prod_by_type: Dict[str, Dict[str, Any]] = {}
    prod_monthly: Dict[str, Dict[str, Any]] = {}
    for p in prod_rows:
        pt = p.product_type or "other"
        ent = prod_by_type.setdefault(pt, {"quantity": 0.0, "unit": p.unit or "units", "records": 0})
        ent["quantity"] += _num(p.quantity) or 0
        ent["records"] += 1
        mk = (p.record_date or "")[:7]
        ment = prod_monthly.setdefault(mk, {"key": mk, "total": 0.0})
        ment["total"] += _num(p.quantity) or 0

    exp_rows = [
        e for e in db.query(LivestockExpenseRecord)
        .filter(LivestockExpenseRecord.user_id == current_user.id)
        .all()
        if _in_window(e.expense_date, start, end)
    ]
    exp_total = sum(_num(e.amount) or 0 for e in exp_rows)
    exp_by_cat: Dict[str, float] = {}
    for e in exp_rows:
        c = e.category or "Other"
        exp_by_cat[c] = exp_by_cat.get(c, 0) + (_num(e.amount) or 0)

    vac_by_status: Dict[str, int] = {}
    for v in db.query(LivestockVaccination).filter(LivestockVaccination.user_id == current_user.id).all():
        s = v.status or "completed"
        vac_by_status[s] = vac_by_status.get(s, 0) + 1
    vac_total = sum(vac_by_status.values())
    vac_due = vac_by_status.get("due_soon", 0) + vac_by_status.get("overdue", 0)

    treatment_total = (
        db.query(LivestockTreatment)
        .filter(LivestockTreatment.user_id == current_user.id)
        .count()
    )

    return {
        "status": "success",
        "data": {
            "present": True,
            "total": total,
            "active": sum(1 for a in animals if a.is_active),
            "by_type": [{"key": k, "count": v} for k, v in sorted(by_type.items(), key=lambda x: -x[1])],
            "by_health": [{"key": k, "count": v} for k, v in sorted(by_health.items(), key=lambda x: -x[1])],
            "production": {
                "by_type": [
                    {"key": k, "quantity": _r2(v["quantity"]), "unit": v["unit"], "records": v["records"]}
                    for k, v in sorted(prod_by_type.items(), key=lambda x: -x[1]["quantity"])
                ],
                "monthly": sorted(prod_monthly.values(), key=lambda x: x["key"]),
                "total_quantity": _r2(sum(v["quantity"] for v in prod_by_type.values())),
                "records": len(prod_rows),
            },
            "expenses": {
                "total": _r2(exp_total),
                "records": len(exp_rows),
                "by_category": [
                    {"key": k, "amount": _r2(v)} for k, v in sorted(exp_by_cat.items(), key=lambda x: -x[1])
                ],
            },
            "vaccinations": {
                "total": vac_total,
                "by_status": [{"key": k, "count": v} for k, v in vac_by_status.items()],
                "due_total": vac_due,
            },
            "treatments": treatment_total,
            "animals": [
                {
                    "name": a.name,
                    "animal_type": a.animal_type,
                    "breed": a.breed,
                    "gender": a.gender,
                    "health_status": a.health_status,
                    "weight_kg": _r2(a.weight_kg),
                    "location": a.location,
                }
                for a in animals[:20]
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Marketplace analysis (farmer's sell-side only)
# --------------------------------------------------------------------------- #
@router.get("/analytics/marketplace", response_model=dict)
def analytics_marketplace(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.marketplace import (
        MarketplaceListing, MarketplaceSale, MarketplaceEnquiry,
    )

    listings = (
        db.query(MarketplaceListing)
        .filter(
            MarketplaceListing.user_id == current_user.id,
            MarketplaceListing.is_deleted == False,
        )
        .all()
    )
    total = len(listings)
    if total == 0:
        return {"status": "success", "data": {"present": False, "total": 0}}

    start, end = _date_range(date_from, date_to)
    status_map: Dict[str, int] = {}
    for l in listings:
        s = l.status or "active"
        status_map[s] = status_map.get(s, 0) + 1
    total_views = sum(l.total_views or 0 for l in listings)
    interested = sum(l.interested_count or 0 for l in listings)
    enquiry_total = (
        db.query(func.count(MarketplaceEnquiry.id))
        .join(MarketplaceListing, MarketplaceListing.id == MarketplaceEnquiry.listing_id)
        .filter(MarketplaceListing.user_id == current_user.id)
        .scalar()
    ) or 0

    sales = (
        db.query(MarketplaceSale)
        .join(MarketplaceListing, MarketplaceListing.id == MarketplaceSale.listing_id)
        .filter(MarketplaceListing.user_id == current_user.id)
        .all()
    )
    sales_in = [s for s in sales if _in_window(
        (s.sold_at or s.created_at).strftime("%Y-%m-%d") if (s.sold_at or s.created_at) else None,
        start, end,
    )]
    sale_rows = [s for s in sales_in if (s.status or "").lower() != "cancelled"]
    revenue = sum(_num(s.total_amount) or 0 for s in sale_rows)
    cat_sales: Dict[str, float] = {}
    monthly_sales: Dict[str, Dict[str, Any]] = {}
    for s in sale_rows:
        key = "Unknown"
        if s.listing and s.listing.category:
            key = s.listing.category.name or key
        cat_sales[key] = cat_sales.get(key, 0) + (_num(s.total_amount) or 0)
        when = s.sold_at or s.created_at
        if when:
            mk = when.strftime("%Y-%m")
            ent = monthly_sales.setdefault(mk, {"key": mk, "total": 0.0, "count": 0})
            ent["total"] += _num(s.total_amount) or 0
            ent["count"] += 1

    return {
        "status": "success",
        "data": {
            "present": True,
            "total": total,
            "active": status_map.get("active", 0),
            "status": [{"key": k, "count": v} for k, v in sorted(status_map.items(), key=lambda x: -x[1])],
            "total_views": total_views,
            "interested": interested,
            "enquiries": enquiry_total,
            "sales": {
                "count": len(sale_rows),
                "revenue": _r2(revenue),
                "by_category": [{"key": k, "amount": _r2(v)} for k, v in sorted(cat_sales.items(), key=lambda x: -x[1])],
                "monthly": sorted(monthly_sales.values(), key=lambda x: x["key"]),
            },
        },
    }


# --------------------------------------------------------------------------- #
# Sensors & monitoring analysis
# --------------------------------------------------------------------------- #
@router.get("/analytics/sensors", response_model=dict)
def analytics_sensors(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.routers.sensors import Sensor, SensorReading
    from app.models.monitoring import MonitoringAlert

    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    sensors = _sensors_in_scope(db, current_user.id, farm_ids, plot_ids)
    total = len(sensors)
    if total == 0:
        return {"status": "success", "data": {"present": False, "total": 0}}

    start, end = _date_range(date_from, date_to)
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    active = 0
    for s in sensors:
        by_type[s.sensor_type or "sensor"] = by_type.get(s.sensor_type or "sensor", 0) + 1
        st = s.status or "unknown"
        by_status[st] = by_status.get(st, 0) + 1
        if st in ("connected", "connecting"):
            active += 1

    sensor_ids = [s.id for s in sensors]
    reading_q = (
        db.query(SensorReading)
        .filter(SensorReading.sensor_id.in_(sensor_ids))
    )
    reading_q = reading_q.filter(_date_col_condition(SensorReading.recorded_at, start, end))
    rows = reading_q.order_by(SensorReading.recorded_at.asc()).all()

    per_metric: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m = per_metric.setdefault(r.reading_type, {"series": [], "unit": r.unit, "count": 0})
        m["series"].append({
            "recorded_at": r.recorded_at.strftime("%Y-%m-%dT%H:%M"),
            "value": _r2(r.value),
        })
        m["count"] += 1
    metrics = []
    for rtype, m in per_metric.items():
        series = m["series"]
        if len(series) > 40:
            step = max(1, len(series) // 40)
            series = series[::step]
            if series[-1] != m["series"][-1]:
                series.append(m["series"][-1])
        last = series[-1] if series else None
        metrics.append({
            "metric": rtype,
            "unit": m["unit"],
            "count": m["count"],
            "last_value": last["value"] if last else None,
            "last_recorded_at": last["recorded_at"] if last else None,
            "series": series,
        })

    alert_q = (
        db.query(MonitoringAlert)
        .filter(MonitoringAlert.user_id == current_user.id, MonitoringAlert.status == "active")
    )
    if farm_ids:
        alert_q = alert_q.filter(MonitoringAlert.farm_id.in_(farm_ids))
    alerts = alert_q.all()
    alert_critical = sum(1 for a in alerts if (a.severity or "") == "critical")

    return {
        "status": "success",
        "data": {
            "present": True,
            "total": total,
            "active": active,
            "offline": sum(1 for s in sensors if s.status in ("offline", "error", "disconnected", "never_connected")),
            "by_type": [{"key": k, "count": v} for k, v in sorted(by_type.items(), key=lambda x: -x[1])],
            "by_status": [{"key": k, "count": v} for k, v in sorted(by_status.items(), key=lambda x: -x[1])],
            "readings": {"count": len(rows), "metrics": metrics},
            "alerts": {"total": len(alerts), "critical": alert_critical},
        },
    }


# --------------------------------------------------------------------------- #
# Farm Analysis Summary - one-at-a-glance review across every domain
# --------------------------------------------------------------------------- #
@router.get("/analytics/summary", response_model=dict)
def analytics_summary(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.livestock import Livestock
    from app.models.marketplace import (
        MarketplaceListing, MarketplaceSale,
    )
    from app.routers.sensors import Sensor, SensorReading
    from app.models.monitoring import MonitoringAlert

    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    start, end = _date_range(date_from, date_to)

    cards = []

    if farms:
        total_area = sum(_acres(f.total_area, f.area_unit) for f in farms)
        cards.append({
            "icon": "fas fa-warehouse", "label": "Farms & Land",
            "value": f"{len(farms)}", "sub": f"{len(plots)} plot(s), {_r2(total_area)} acres",
            "present": True,
        })
    else:
        cards.append({"icon": "fas fa-warehouse", "label": "Farms & Land", "value": "0", "sub": "Register a farm to begin", "present": False})

    cycles = _cycles_in_scope(db, farm_ids, plot_ids)
    active = [c for c in cycles if (c.status or "").lower() == "active"]
    harvested = [c for c in cycles if c.actual_harvest_date]
    cards.append({
        "icon": "fas fa-seedling", "label": "Crops",
        "value": f"{len(active)}", "sub": f"{len(cycles)} cycles total, {len(harvested)} harvested",
        "present": bool(cycles),
    })

    cycles_w = _cycles_in_window(cycles, date_from, date_to)
    yield_total = sum(_num(c.yield_quantity) or 0 for c in cycles_w if c.yield_quantity)
    unit = next((c.yield_unit for c in cycles_w if c.yield_unit), "kg")
    yield_count = sum(1 for c in cycles_w if c.yield_quantity is not None)
    cards.append({
        "icon": "fas fa-weight-hanging", "label": "Harvest",
        "value": f"{_r2(yield_total):,g}" if yield_total else "0",
        "sub": f"{yield_count} cycle(s) with yield in {unit}",
        "present": bool(cycles_w),
    })

    income = _num(db.query(func.coalesce(func.sum(Income.amount), 0.0)).filter(
        Income.user_id == current_user.id, Income.farm_id.in_(farm_ids) if farm_ids else True).scalar()) or 0
    expenses = _num(db.query(func.coalesce(func.sum(Expense.amount), 0.0)).filter(
        Expense.user_id == current_user.id, Expense.farm_id.in_(farm_ids) if farm_ids else True).scalar()) or 0
    fin_present = bool(income or expenses)
    fin_net = _r2(income - expenses)
    cards.append({
        "icon": "fas fa-sack-dollar", "label": "Finances",
        "value": f"₹{fin_net:,.0f}" if fin_present else "--",
        "sub": f"Income ₹{_r2(income):,.0f} · Expenses ₹{_r2(expenses):,.0f}",
        "present": fin_present,
    })

    livestock_total = db.query(Livestock).filter(Livestock.user_id == current_user.id).count()
    cards.append({
        "icon": "fas fa-cow", "label": "Livestock",
        "value": f"{livestock_total}",
        "sub": "Animals in your herd",
        "present": livestock_total > 0,
    })

    listings = db.query(MarketplaceListing).filter(
        MarketplaceListing.user_id == current_user.id, MarketplaceListing.is_deleted == False).count()
    sauce = db.query(MarketplaceSale).join(
        MarketplaceListing, MarketplaceListing.id == MarketplaceSale.listing_id,
    ).filter(
        MarketplaceListing.user_id == current_user.id,
        MarketplaceSale.status != "cancelled",
    ).all()
    mkt_rev = sum(_num(s.total_amount) or 0 for s in sauce)
    cards.append({
        "icon": "fas fa-store", "label": "Marketplace",
        "value": f"{listings}", "sub": f"{len(sauce)} sale(s), ₹{_r2(mkt_rev):,.0f} earned",
        "present": bool(listings),
    })

    sensors = _sensors_in_scope(db, current_user.id, farm_ids, plot_ids)
    sensor_ids = [s.id for s in sensors]
    reading_count = 0
    if sensor_ids:
        rq = db.query(func.count(SensorReading.id)).filter(SensorReading.sensor_id.in_(sensor_ids))
        rq = rq.filter(_date_col_condition(SensorReading.recorded_at, start, end))
        reading_count = rq.scalar() or 0
    cards.append({
        "icon": "fas fa-microchip", "label": "Sensors & Monitoring",
        "value": f"{len(sensors)}", "sub": f"{reading_count} reading(s) in period",
        "present": bool(sensors),
    })

    alert_q = db.query(MonitoringAlert).filter(MonitoringAlert.user_id == current_user.id, MonitoringAlert.status == "active")
    if farm_ids:
        alert_q = alert_q.filter(MonitoringAlert.farm_id.in_(farm_ids))
    alerts = alert_q.count()
    cards.append({
        "icon": "fas fa-triangle-exclamation", "label": "Open Alerts",
        "value": f"{alerts}", "sub": "Active monitoring alerts",
        "present": alerts > 0,
    })

    tasks_q = db.query(CropTask).filter(CropTask.crop_cycle_id.in_([c.id for c in cycles])) if cycles else []
    tasks_all = tasks_q.all() if cycles else []
    tasks_w = [t for t in tasks_all if _in_window(t.due_date, start, end)] if tasks_all else []
    done = sum(1 for t in tasks_all if (t.status or "").lower() == "completed")
    cards.append({
        "icon": "fas fa-list-check", "label": "Farm Activities",
        "value": f"{done}/{len(tasks_all)}", "sub": "Tasks completed",
        "present": bool(tasks_all),
    })

    return {"status": "success", "data": {"cards": cards, "has_data": any(c["present"] for c in cards)}}


# --------------------------------------------------------------------------- #
# AI analysis - "Analyze My Farm"
# --------------------------------------------------------------------------- #
@router.get("/analytics/ai", response_model=dict)
async def analytics_ai(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)
    cycles = _cycles_in_scope(db, farm_ids, plot_ids)
    cycle_ids = [c.id for c in cycles]

    tasks = db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).all() if cycle_ids else []
    income = _num(db.query(func.coalesce(func.sum(Income.amount), 0.0)).filter(Income.user_id == current_user.id, Income.farm_id.in_(farm_ids) if farm_ids else True).scalar()) or 0
    expenses = _num(db.query(func.coalesce(func.sum(Expense.amount), 0.0)).filter(Expense.user_id == current_user.id, Expense.farm_id.in_(farm_ids) if farm_ids else True).scalar()) or 0

    known = []  # only facts actually present in the system
    if farms:
        known.append(f"{len(farms)} farm(s): " + ", ".join(f.farm_name for f in farms))
    else:
        known.append("No farm registered")
    if cycles:
        known.append(f"{len(cycles)} crop cycle(s)")
        for c in cycles[:8]:
            known.append(
                f"- {c.crop.name if c.crop else 'crop'} on {c.farm.farm_name if c.farm else 'farm'} "
                f"(sown {c.sowing_date or 'n/a'}, stage {c.current_stage or c.status or 'n/a'})"
            )
    if tasks:
        done = sum(1 for t in tasks if (t.status or "").lower() == "completed")
        known.append(f"{done}/{len(tasks)} farm activities completed")
    if income or expenses:
        known.append(f"Recorded income ₹{income:,.0f}, expenses ₹{expenses:,.0f}")

    unknown = []
    if not farms:
        unknown.append("No farm details (soil type, water source, irrigation method) are recorded.")
    if not cycles:
        unknown.append("No crop cycles are recorded, so crop-level analysis is limited.")
    if not tasks:
        unknown.append("No farm activities/tasks are recorded.")
    if not income and not expenses:
        unknown.append("No farm income or expense records exist for financial analysis.")

    summary_lines = [
        f"Farmer: {current_user.full_name}",
        "KNOWN DATA (real records only):",
    ] + known + (["UNKNOWN / MISSING DATA:"] + unknown if unknown else [])

    prompt = (
        "You are a farm intelligence analyst for Farm Assist. Using ONLY the real farm "
        "records shown below, provide: 1) Analysis - what the data says about the farm, "
        "2) Suggestions - practical, safe next steps (no pesticide/chemical dosage advice), "
        "3) What additional data would improve this analysis. Never invent numbers.\n\n"
        + "\n".join(summary_lines)
    )

    try:
        ai = await chat_with_ai(prompt)
        response = ai.get("response", "")
        model = ai.get("model", "local")
    except Exception:
        response = "Analysis temporarily unavailable. Please try again in a moment."
        model = "local"

    suggestions = []
    for line in (response or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(("2)", "- suggestion", "suggest:", "suggestion")):
            suggestions.append(stripped.lstrip("2) -:").strip())
    if not suggestions:
        suggestions = ["Keep your farm records updated so the analysis can be refined."]

    return {
        "status": "success",
        "data": {
            "known": known,
            "unknown": unknown,
            "analysis": response,
            "suggestions": suggestions,
            "model": model,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    }


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
class ReportCreate(BaseModel):
    report_type: str = Field(..., max_length=60)
    title: Optional[str] = Field(None, max_length=250)
    farm_id: Optional[str] = None
    plot_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    summary: Optional[str] = Field(None, max_length=2000)
    data: Optional[dict] = None


def _report_dict(r: FarmReport) -> dict:
    return {
        "id": r.id,
        "report_id": r.report_id,
        "report_type": r.report_type,
        "title": r.title,
        "farm_id": r.farm_id,
        "farm_name": r.farm_name,
        "plot_id": r.plot_id,
        "plot_name": r.plot_name,
        "date_from": r.date_from,
        "date_to": r.date_to,
        "summary": r.summary,
        "data": r.data_json,
        "created_at": str(r.created_at) if r.created_at else None,
    }


@router.get("/analytics/reports", response_model=dict)
def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reports = (
        db.query(FarmReport)
        .filter(FarmReport.user_id == current_user.id)
        .order_by(FarmReport.created_at.desc())
        .limit(100)
        .all()
    )
    return {"status": "success", "data": {"reports": [_report_dict(r) for r in reports]}}


@router.get("/analytics/reports/{report_id}", response_model=dict)
def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(FarmReport).filter(
        FarmReport.report_id == report_id,
        FarmReport.user_id == current_user.id,
    ).first()
    if not report:
        report = db.query(FarmReport).filter(
            FarmReport.id == report_id,
            FarmReport.user_id == current_user.id,
        ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"status": "success", "data": _report_dict(report)}


@router.post("/analytics/reports", status_code=201, response_model=dict)
def create_report(
    payload: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_name = None
    plot_name = None
    if payload.farm_id:
        farm = db.query(Farm).filter(
            Farm.id == payload.farm_id, Farm.user_id == current_user.id
        ).first()
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")
        farm_name = farm.farm_name
    if payload.plot_id and (payload.farm_id or True):
        plot_q = db.query(FarmPlot).filter(FarmPlot.id == payload.plot_id)
        plot = plot_q.first()
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        owner = db.query(Farm).filter(
            Farm.id == plot.farm_id, Farm.user_id == current_user.id
        ).first()
        if not owner:
            raise HTTPException(status_code=404, detail="Plot not found")
        plot_name = plot.plot_name

    title = payload.title or f"{payload.report_type} Report"
    report = FarmReport(
        report_id=_report_code(db, current_user),
        user_id=current_user.id,
        farm_id=payload.farm_id,
        farm_name=farm_name,
        plot_id=payload.plot_id,
        plot_name=plot_name,
        report_type=payload.report_type,
        title=title,
        date_from=payload.date_from,
        date_to=payload.date_to,
        summary=payload.summary,
        data_json=payload.data or {},
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"status": "success", "data": _report_dict(report)}


@router.delete("/analytics/reports/{report_id}", response_model=dict)
def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(FarmReport).filter(
        or_(FarmReport.report_id == report_id, FarmReport.id == report_id),
        FarmReport.user_id == current_user.id,
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"status": "success", "data": {"deleted": True}}


# --------------------------------------------------------------------------- #
# Report export (server-side HTML / CSV)
# --------------------------------------------------------------------------- #
_REPORT_SECTION_LABELS = {
    "overview": "Farm Overview",
    "performance": "Performance Score",
    "crops": "Crop Analysis",
    "yield": "Yield Analysis",
    "production": "Production Trend",
    "financial": "Financial Analysis",
    "tasks": "Farm Activities",
    "calendar": "Calendar Events",
    "weather": "Weather Conditions",
    "market": "Market Prices",
    "sustainability": "Sustainability",
    "risks": "Risk Analysis",
    "insurance": "Insurance Review",
    "livestock": "Livestock Analysis",
    "marketplace": "Marketplace Analysis",
    "sensors": "Sensors & Monitoring",
    "summary": "Farm Analysis Summary",
    "insights": "Smart Insights",
    "completeness": "Data Completeness",
}

_REPORT_SECTION_ORDER = [
    "overview", "performance", "crops", "yield", "production", "financial",
    "tasks", "calendar", "weather", "market", "sustainability", "risks",
    "insurance", "livestock", "marketplace", "sensors", "summary",
    "insights", "completeness",
]


def _find_user_report(db: Session, current_user: User, report_id: str) -> FarmReport:
    report = db.query(FarmReport).filter(
        or_(FarmReport.report_id == report_id, FarmReport.id == report_id),
        FarmReport.user_id == current_user.id,
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _esc_v(value: Any) -> str:
    if value is None:
        return '<span class="dim">—</span>'
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return _esc(str(value))


def _scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _kv_table_html(obj: Dict[str, Any]) -> str:
    rows = []
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            continue
        label = _esc(str(k).replace("_", " ").title())
        rows.append(f"<tr><th>{label}</th><td>{_esc_v(v)}</td></tr>")
    return '<table class="kv">' + "".join(rows) + "</table>" if rows else ""


def _list_table_html(lst: List[Any]) -> str:
    headers: List[str] = []
    for item in lst:
        if isinstance(item, dict):
            for k in item:
                if k not in headers and not isinstance(item[k], (dict, list)):
                    headers.append(k)
    if not headers:
        cells = "".join(f"<li>{_esc_v(i)}</li>" for i in lst)
        return f"<ul>{cells}</ul>" if cells else ""
    head = "".join(
        f"<th>{_esc(str(h).replace('_', ' ').title())}</th>" for h in headers
    )
    body = ""
    for item in lst:
        tds = "".join(f"<td>{_esc_v(item.get(h))}</td>" for h in headers)
        body += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _render_report_html(report: FarmReport) -> str:
    data = report.data_json or {}
    period = f"{report.date_from or '—'} to {report.date_to or 'today'}"
    scope_parts = []
    if report.farm_name:
        scope_parts.append(_esc(report.farm_name))
    if report.plot_name:
        scope_parts.append(_esc(report.plot_name))
    scope = " / ".join(scope_parts) if scope_parts else "All farms"

    sections_html = []
    included = []
    for key in _REPORT_SECTION_ORDER:
        if key not in data or data[key] is None:
            continue
        included.append(key)
        value = data[key]
        if isinstance(value, dict):
            body = _kv_table_html(value)
        elif isinstance(value, list):
            body = _list_table_html(value)
        else:
            body = f"<p>{_esc_v(value)}</p>"
        if not body.strip():
            continue
        sections_html.append(
            f'<section class="card"><h2>{_esc(_REPORT_SECTION_LABELS.get(key, key))}</h2>{body}</section>'
        )

    missing = [k for k in _REPORT_SECTION_ORDER if k not in included]
    missing_note = ""
    if missing:
        labels = ", ".join(_REPORT_SECTION_LABELS.get(k, k) for k in missing)
        missing_note = (
            '<p class="note">Some report sections could not be included because the '
            f'underlying data is not recorded yet: {_esc(labels)}.</p>'
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{_esc(report.title or 'Farm Report')}</title>
<style>
  body{{font-family:Arial,Helvetica,sans-serif;color:#1f2937;margin:0;padding:0;background:#f3f4f6}}
  .wrap{{max-width:900px;margin:0 auto;padding:24px}}
  header{{background:#166534;color:#fff;padding:20px 24px;border-radius:10px}}
  header h1{{margin:0 0 6px;font-size:22px}}
  header .sub{{opacity:.9;font-size:13px}}
  .card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 18px;margin:14px 0}}
  .card h2{{margin:0 0 12px;font-size:16px;color:#166534;border-bottom:1px solid #eef2f0;padding-bottom:8px}}
  table{{border-collapse:collapse;width:100%;font-size:13px}}
  table.kv th{{text-align:left;width:220px;color:#374151;font-weight:600;padding:5px 8px;vertical-align:top}}
  table.kv td{{padding:5px 8px}}
  table:not(.kv) th{{background:#f9fafb;text-align:left;padding:7px 8px;border-bottom:1px solid #e5e7eb;color:#374151}}
  table:not(.kv) td{{padding:6px 8px;border-bottom:1px solid #f3f4f6}}
  tr:nth-child(even) td{{background:#fafcfa}}
  .dim{{color:#9ca3af}} .note{{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;color:#92400e;font-size:13px}}
  .meta{{font-size:12px;color:#6b7280;margin-top:8px}}
</style></head><body><div class="wrap">
<header>
  <h1>{_esc(report.title or 'Farm Assist Intelligence Report')}</h1>
  <div class="sub">Farm Assist &middot; Intelligence Report &middot; {_esc(report.report_type)}</div>
  <div class="sub">Farm: {scope} &middot; Period: {_esc(period)}</div>
  <div class="sub">Report ID: {_esc(report.report_id or '')} &middot; Generated: {_esc(str(report.created_at) or datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'))}</div>
</header>
{''.join(sections_html)}
{missing_note}
<p class="meta">Prepared by Farm Assist Farm Intelligence Center from records belonging to this farmer account. Figures shown reflect only the data recorded in the app.</p>
</div></body></html>"""


def _flatten_csv(key: str, val: Any, out: List[tuple]):
    if isinstance(val, dict):
        for k, v in val.items():
            sub = f"{key} :: {str(k).replace('_', ' ').title()}"
            if isinstance(v, (dict, list)):
                _flatten_csv(sub, v, out)
            else:
                out.append((sub, _scalar_text(v)))
    elif isinstance(val, list):
        for i, item in enumerate(val):
            if isinstance(item, dict):
                for k, v in item.items():
                    sub = f"{key} [{i + 1}] :: {str(k).replace('_', ' ').title()}"
                    if isinstance(v, (dict, list)):
                        _flatten_csv(sub, v, out)
                    else:
                        out.append((sub, _scalar_text(v)))
            else:
                out.append((f"{key} [{i + 1}]", _scalar_text(item)))
    else:
        out.append((key, _scalar_text(val)))


def _render_report_csv(report: FarmReport) -> str:
    data = report.data_json or {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Field", "Value"])
    w.writerow(["Report Title", report.title or report.report_type])
    if report.report_id:
        w.writerow(["Report ID", report.report_id])
    if report.farm_name:
        w.writerow(["Farm", report.farm_name])
    if report.plot_name:
        w.writerow(["Plot", report.plot_name])
    w.writerow(["Report Type", report.report_type])
    w.writerow(["Period", f"{report.date_from or '—'} to {report.date_to or 'today'}"])
    w.writerow(["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")])
    if report.summary:
        w.writerow(["Summary", report.summary])
    for key in _REPORT_SECTION_ORDER:
        if key not in data or data[key] is None:
            continue
        w.writerow([])
        w.writerow([_REPORT_SECTION_LABELS.get(key, key) + " —"])
        rows: List[tuple] = []
        _flatten_csv(key, data[key], rows)
        for k, v in rows:
            w.writerow([k, v])
    return buf.getvalue()


@router.get("/analytics/reports/{report_id}/html", include_in_schema=False)
def export_report_html(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = _find_user_report(db, current_user, report_id)
    fname = f"{report.report_id or 'report'}.html"
    return Response(
        content=_render_report_html(report),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/analytics/reports/{report_id}/csv", include_in_schema=False)
def export_report_csv(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = _find_user_report(db, current_user, report_id)
    fname = f"{report.report_id or 'report'}.csv"
    return Response(
        content=_render_report_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )