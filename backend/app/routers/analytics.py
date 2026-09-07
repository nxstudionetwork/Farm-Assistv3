from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.connection import get_db
from app.models.user import User, LoginHistory
from app.models.farm import Farm
from app.models.crop import Crop, CropCycle, CropTask
from app.models.finance import Transaction
from app.models.worker import WorkerBooking
from app.models.marketplace import MarketplaceOrder
from app.models.ai import AIConversation
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Analytics"])


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


@router.get("/analytics/farm-health", response_model=dict)
def farm_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compute a farm-health score (0-100) from the authenticated farmer's real data.

    The value is derived only from the logged-in farmer's own farms, crop cycles and
    crop tasks. It is never hardcoded and is isolated by the auth token.
    """
    farm_ids = [f[0] for f in db.query(Farm.id).filter(
        Farm.user_id == current_user.id, Farm.is_active == True
    ).all()]

    # Farm foundation (0-100)
    farm_score = 0.0
    if farm_ids:
        farms = db.query(Farm).filter(Farm.id.in_(farm_ids)).all()
        farm_score += 20.0  # registered farms present
        if len(farms) == len(farm_ids):
            farm_score += 20.0  # all registered farms are active
        if any(f.soil_type for f in farms):
            farm_score += 20.0
        if any(f.water_source for f in farms):
            farm_score += 20.0
        if any((f.total_area or 0) > 0 for f in farms):
            farm_score += 20.0

    # Crop activity (0-100)
    crop_score = 0.0
    cycles = []
    if farm_ids:
        cycles = db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all()
    if cycles:
        total = len(cycles)
        active = sum(1 for c in cycles if (c.status or "").lower() == "active")
        harvested = sum(1 for c in cycles if c.actual_harvest_date)
        crop_score += 40.0  # has registered crop cycles
        crop_score += 40.0 * (active / total)
        crop_score += 20.0 * (harvested / total)

    # Task completion (0-100) across the farmer's crop cycles
    task_score = 0.0
    cycle_ids = [c.id for c in cycles]
    tasks = []
    if cycle_ids:
        tasks = db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).all()
    if tasks:
        total = len(tasks)
        completed = sum(1 for t in tasks if (t.status or "").lower() == "completed")
        task_score = 100.0 * (completed / total)
    else:
        task_score = 50.0  # neutral: no tasks to complete

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
