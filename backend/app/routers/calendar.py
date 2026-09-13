"""Calendar router — central calendar for Farm Assist.

Endpoints for listing, creating, updating, deleting calendar events and
triggering sync from source modules.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, func, and_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.calendar import CalendarEvent
from app.models.farm import Farm, FarmPlot
from app.models.crop import CropCycle
from app.services.calendar_service import sync_all_events
from app.services.reminder_service import process_due_reminders

router = APIRouter(prefix="/api/v1/calendar", tags=["Calendar"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_type: str = "manual"
    start_datetime: Optional[str] = None  # ISO format
    end_datetime: Optional[str] = None
    all_day: bool = False
    priority: str = "normal"
    farm_id: Optional[str] = None
    farm_name: Optional[str] = None
    plot_id: Optional[str] = None
    plot_name: Optional[str] = None
    crop_id: Optional[str] = None
    crop_name: Optional[str] = None
    reminder_config: Optional[str] = None
    recurrence: Optional[str] = None


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None
    all_day: Optional[bool] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    farm_id: Optional[str] = None
    farm_name: Optional[str] = None
    plot_id: Optional[str] = None
    plot_name: Optional[str] = None
    crop_id: Optional[str] = None
    crop_name: Optional[str] = None
    reminder_config: Optional[str] = None
    recurrence: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso(s):
    """Parse an ISO datetime string to a naive datetime (UTC-normalized)."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _event_dict(e):
    """Serialize a CalendarEvent to a dict."""
    return {
        "id": e.id,
        "event_id": e.event_id,
        "farmer_id": e.farmer_id,
        "title": e.title,
        "description": e.description,
        "event_type": e.event_type,
        "start_datetime": e.start_datetime.isoformat() if e.start_datetime else None,
        "end_datetime": e.end_datetime.isoformat() if e.end_datetime else None,
        "all_day": e.all_day,
        "status": e.status,
        "priority": e.priority,
        "farm_id": e.farm_id,
        "farm_name": e.farm_name,
        "plot_id": e.plot_id,
        "plot_name": e.plot_name,
        "crop_id": e.crop_id,
        "crop_name": e.crop_name,
        "source_type": e.source_type,
        "source_id": e.source_id,
        "source_page": e.source_page,
        "reminder_config": e.reminder_config,
        "reminder_fired": e.reminder_fired,
        "recurrence": e.recurrence,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _step_months(dt, n):
    """Return dt advanced by n months, clamping the day to the target month."""
    y = dt.year + (dt.month - 1 + n) // 12
    m = (dt.month - 1 + n) % 12 + 1
    import calendar as _cal
    day = min(dt.day, _cal.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)


def _expand_recurrences(rows, window_start, window_end, limit=400):
    """Expand recurring manual events into individual occurrences in a window.

    Occurrences are generated in memory only — no duplicate database rows are
    created. ``rows`` is the already-serialized list of event dicts; events
    with a recurrence that does not fall inside the window are returned as-is.
    """
    out = []
    for ev in rows:
        if not ev.get("recurrence") or not ev.get("start_datetime"):
            out.append(ev)
            continue
        if ev.get("source_type") not in (None, "", "manual"):
            out.append(ev)
            continue
        try:
            start = datetime.fromisoformat(ev["start_datetime"])
        except (ValueError, TypeError):
            out.append(ev)
            continue

        if ev["recurrence"] == "daily":
            step_fn = lambda dt: dt + timedelta(days=1)
        elif ev["recurrence"] == "weekly":
            step_fn = lambda dt: dt + timedelta(days=7)
        elif ev["recurrence"] == "monthly":
            step_fn = lambda dt: _step_months(dt, 1)
        else:
            out.append(ev)
            continue

        if not window_start or not window_end:
            out.append(ev)
            continue

        # Bring the original occurrence's series forward to the window start.
        series = start
        sentinel = 0
        while series < window_start and sentinel < 5000:
            series = step_fn(series)
            sentinel += 1

        added = 0
        emit_original = window_start <= start <= window_end
        while series <= window_end and added < limit:
            if series == start:
                if emit_original:
                    out.append(ev)
            else:
                occ = dict(ev)
                occ["start_datetime"] = series.isoformat()
                # Keep the original id so clicks resolve to the source event;
                # suffix event_id only to make occurrences distinguishable.
                occ["event_id"] = f"{ev.get('event_id')}#{series.strftime('%Y%m%d%H%M')}"
                occ["recurrence"] = None  # occurrences are concrete
                out.append(occ)
            series = step_fn(series)
            added += 1
        if added == 0 and not (window_start <= start <= window_end):
            # series never landed in window and no occurrence was emitted
            pass
    return out


def _apply_filters(q, farmer_id, start_date, end_date, event_type, status,
                    priority, farm_id, crop_name, source_type, search,
                    plot_id=None):
    """Apply query filters to a CalendarEvent query."""
    q = q.filter(CalendarEvent.farmer_id == farmer_id)

    if start_date:
        sd = _parse_iso(start_date)
        if sd:
            q = q.filter(CalendarEvent.start_datetime >= sd)
    if end_date:
        ed = _parse_iso(end_date)
        if ed:
            # A bare date (YYYY-MM-DD) should include the entire day
            if len(end_date.strip()) <= 10:
                ed = ed.replace(hour=23, minute=59, second=59, microsecond=999999)
            q = q.filter(CalendarEvent.start_datetime <= ed)
    if event_type:
        types = [t.strip() for t in event_type.split(",") if t.strip()]
        if types:
            q = q.filter(CalendarEvent.event_type.in_(types))
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            q = q.filter(CalendarEvent.status.in_(statuses))
    if priority:
        q = q.filter(CalendarEvent.priority == priority)
    if farm_id:
        q = q.filter(CalendarEvent.farm_id == farm_id)
    if plot_id:
        q = q.filter(CalendarEvent.plot_id == plot_id)
    if crop_name:
        q = q.filter(CalendarEvent.crop_name.ilike(f"%{crop_name}%"))
    if source_type:
        q = q.filter(CalendarEvent.source_type == source_type)
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(or_(
            CalendarEvent.title.ilike(term),
            CalendarEvent.description.ilike(term),
            CalendarEvent.farm_name.ilike(term),
            CalendarEvent.plot_name.ilike(term),
            CalendarEvent.crop_name.ilike(term),
        ))
    return q


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/events")
def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_name: Optional[str] = None,
    source_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CalendarEvent)
    q = _apply_filters(q, current_user.id, start_date, end_date, event_type,
                       status, priority, farm_id, crop_name, source_type, search,
                       plot_id=plot_id)
    total = q.count()
    rows = q.order_by(CalendarEvent.start_datetime.asc().nullslast()).offset(
        (page - 1) * limit
    ).limit(limit).all()
    items = [_event_dict(e) for e in rows]

    # Expand recurring manual events into concrete occurrences inside the
    # requested window (in-memory only).
    if (start_date or end_date) and rows:
        items = _expand_recurrences(
            items, _parse_iso(start_date), _parse_iso(end_date)
        )

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 0,
            "items": items,
        },
    }


@router.get("/today")
def today_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return events for today."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    items = db.query(CalendarEvent).filter(
        CalendarEvent.farmer_id == current_user.id,
        CalendarEvent.start_datetime >= today_start,
        CalendarEvent.start_datetime < today_end,
    ).order_by(CalendarEvent.start_datetime.asc()).all()

    # Also include overdue events (past date, not completed/cancelled)
    overdue = db.query(CalendarEvent).filter(
        CalendarEvent.farmer_id == current_user.id,
        CalendarEvent.start_datetime < today_start,
        CalendarEvent.status.notin_(["completed", "cancelled"]),
    ).order_by(CalendarEvent.start_datetime.desc()).limit(10).all()

    return {
        "status": "success",
        "data": {
            "today": [_event_dict(e) for e in items],
            "overdue": [_event_dict(e) for e in overdue],
        },
    }


@router.get("/upcoming")
def upcoming_events(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the next N upcoming events from today onwards."""
    now = datetime.utcnow()
    items = db.query(CalendarEvent).filter(
        CalendarEvent.farmer_id == current_user.id,
        CalendarEvent.start_datetime >= now,
        CalendarEvent.status.notin_(["completed", "cancelled"]),
    ).order_by(CalendarEvent.start_datetime.asc()).limit(limit).all()
    return {
        "status": "success",
        "data": {
            "items": [_event_dict(e) for e in items],
        },
    }


@router.get("/filters")
def get_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return available filter options derived from the farmer's real data."""
    # Farms
    farms = db.query(Farm).filter(Farm.user_id == current_user.id).all()
    farm_list = [{"id": f.id, "name": f.farm_name} for f in farms]

    # Plots belonging to the farmer's farms
    farm_ids = [f.id for f in farms]
    plots = []
    if farm_ids:
        rows = db.query(FarmPlot).filter(FarmPlot.farm_id.in_(farm_ids)).all()
        plots = [{"id": p.id, "farm_id": p.farm_id, "name": p.plot_name} for p in rows]

    # Crop names from crop cycles
    crop_names = []
    if farm_ids:
        rows = db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all()
        seen = set()
        for c in rows:
            name = c.crop.name if c.crop else None
            if name and name not in seen:
                seen.add(name)
                crop_names.append(name)

    # Event types and statuses from existing events
    types = [r[0] for r in db.query(CalendarEvent.event_type).filter(
        CalendarEvent.farmer_id == current_user.id
    ).distinct().all() if r[0]]
    statuses = [r[0] for r in db.query(CalendarEvent.status).filter(
        CalendarEvent.farmer_id == current_user.id
    ).distinct().all() if r[0]]

    return {
        "status": "success",
        "data": {
            "farms": farm_list,
            "plots": plots,
            "crop_names": sorted(crop_names),
            "event_types": sorted(types),
            "statuses": sorted(statuses),
            "priorities": ["low", "normal", "high", "urgent"],
            "source_types": [
                "crop_task", "consultation", "service_request", "worker_booking",
                "equipment_booking", "order", "scheme_application",
                "insurance_renewal", "insurance_premium", "insurance_expiry",
                "crop_sowing", "crop_harvest", "enrollment", "farm_journal",
                "manual",
            ],
        },
    }


@router.get("/events/{event_id}")
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single calendar event by ID or event_id."""
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.farmer_id == current_user.id,
    ).first()
    if not event:
        event = db.query(CalendarEvent).filter(
            CalendarEvent.event_id == event_id,
            CalendarEvent.farmer_id == current_user.id,
        ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    return {"status": "success", "data": _event_dict(event)}


@router.post("/events", status_code=201)
def create_event(
    body: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a manual calendar event."""
    event = CalendarEvent(
        farmer_id=current_user.id,
        title=body.title,
        description=body.description,
        event_type=body.event_type or "manual",
        start_datetime=_parse_iso(body.start_datetime),
        end_datetime=_parse_iso(body.end_datetime),
        all_day=body.all_day,
        status="scheduled",
        priority=body.priority or "normal",
        farm_id=body.farm_id,
        farm_name=body.farm_name,
        plot_id=body.plot_id,
        plot_name=body.plot_name,
        crop_id=body.crop_id,
        crop_name=body.crop_name,
        reminder_config=body.reminder_config,
        recurrence=body.recurrence,
    )
    event.event_id = generate_id("FA-CAL", db, CalendarEvent)
    db.add(event)
    db.commit()
    db.refresh(event)
    return {
        "status": "success",
        "data": _event_dict(event),
    }


@router.put("/events/{event_id}")
def update_event(
    event_id: str,
    body: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a calendar event."""
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.farmer_id == current_user.id,
    ).first()
    if not event:
        event = db.query(CalendarEvent).filter(
            CalendarEvent.event_id == event_id,
            CalendarEvent.farmer_id == current_user.id,
        ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    for field, val in body.dict(exclude_unset=True).items():
        if field in ("start_datetime", "end_datetime"):
            setattr(event, field, _parse_iso(val) if val else None)
        else:
            setattr(event, field, val)
    event.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(event)
    return {"status": "success", "data": _event_dict(event)}


@router.delete("/events/{event_id}")
def delete_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a calendar event. Only manual events can be fully deleted."""
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.farmer_id == current_user.id,
    ).first()
    if not event:
        event = db.query(CalendarEvent).filter(
            CalendarEvent.event_id == event_id,
            CalendarEvent.farmer_id == current_user.id,
        ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    # Auto-synced events: mark as cancelled rather than deleting
    if event.source_type and event.source_type != "manual":
        event.status = "cancelled"
        event.updated_at = datetime.utcnow()
        db.commit()
    else:
        db.delete(event)
        db.commit()

    return {"status": "success", "data": {"message": "Event deleted"}}


@router.post("/sync")
def sync_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a full sync from all source modules into calendar events.

    Also processes any reminders that have become due, pushing them into the
    Farm Assist notification system.
    """
    summary = sync_all_events(db, current_user.id)
    total = sum(v for v in summary.values() if isinstance(v, int))
    reminders = process_due_reminders(db, current_user.id)
    return {
        "status": "success",
        "data": {
            "synced_events": total,
            "reminders_sent": reminders,
            "details": summary,
        },
    }


@router.post("/reminders/process")
def process_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process due reminders for the current farmer and return count created."""
    created = process_due_reminders(db, current_user.id)
    return {
        "status": "success",
        "data": {"reminders_sent": created},
    }
