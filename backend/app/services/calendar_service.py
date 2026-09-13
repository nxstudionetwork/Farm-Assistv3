"""Calendar sync service.

Reads all source modules and creates / updates CalendarEvent rows so the
farmer's calendar always reflects the real state of the application.

Deduplication is by (farmer_id, source_type, source_id).  When a source
record changes its date, the existing calendar event is updated.  When a
source record is deleted / completed / cancelled, the calendar event status
is updated accordingly.
"""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.calendar import CalendarEvent
from app.models.crop import CropTask, CropCycle, FarmJournal
from app.models.community import Consultation
from app.models.service import ServiceRequest
from app.models.worker import WorkerBooking, EquipmentBooking
from app.models.marketplace import MarketplaceOrder
from app.models.government import SchemeApplication, InsurancePolicy
from app.models.learning import CourseEnrollment
from app.models.farm import Farm, FarmPlot
from app.models.emergency import EmergencyReport


def _parse_dt(date_str, time_str=None):
    """Parse a date string (YYYY-MM-DD) and optional time string (HH:MM) into a datetime."""
    if not date_str:
        return None
    ds = str(date_str).strip()[:10]
    if len(ds) < 10 or ds.count('-') != 2:
        return None
    try:
        if time_str:
            ts = str(time_str).strip()[:5]
            if len(ts) >= 5:
                return datetime.strptime(f"{ds} {ts}", "%Y-%m-%d %H:%M")
        return datetime.strptime(ds, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _get_or_create_event(db, farmer_id, source_type, source_id):
    """Find an existing event by dedup key or return None."""
    if not source_type or not source_id:
        return None
    return db.query(CalendarEvent).filter(
        CalendarEvent.farmer_id == farmer_id,
        CalendarEvent.source_type == source_type,
        CalendarEvent.source_id == str(source_id),
    ).first()


def _upsert_event(db, farmer_id, source_type, source_id, **kwargs):
    """Create or update a calendar event by dedup key."""
    existing = _get_or_create_event(db, farmer_id, source_type, source_id)
    if existing:
        for k, v in kwargs.items():
            if v is not None:
                setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
    else:
        from app.utils.auth import generate_id
        event = CalendarEvent(
            farmer_id=farmer_id,
            source_type=source_type,
            source_id=str(source_id),
            **{k: v for k, v in kwargs.items() if v is not None},
        )
        if not event.event_id:
            event.event_id = generate_id("FA-CAL", db, CalendarEvent)
        db.add(event)
        # Flush so the new event_id is visible to subsequent generate_id calls
        # (sessions use autoflush=False, otherwise consecutive inserts in one
        # transaction would collide on the same generated id).
        db.flush()
    return existing or event


def _farm_context(db, farm_id):
    """Return (farm_name, ...) for a farm_id."""
    if not farm_id:
        return {}
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if farm:
        return {"farm_id": farm.id, "farm_name": farm.farm_name}
    return {}


# ---------------------------------------------------------------------------
# Per-module sync functions
# ---------------------------------------------------------------------------

def sync_crop_tasks(db: Session, farmer_id: str) -> int:
    """Sync crop tasks → calendar events. Returns count of events touched."""
    # Find all crop cycles belonging to the farmer's farms
    farm_ids = [f.id for f in db.query(Farm.id).filter(Farm.user_id == farmer_id).all()]
    if not farm_ids:
        return 0
    cycles = db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all()
    cycle_ids = [c.id for c in cycles]
    if not cycle_ids:
        return 0
    tasks = db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).all()

    # Build cycle lookup for crop context
    cycle_map = {c.id: c for c in cycles}
    count = 0
    for t in tasks:
        if not t.due_date:
            continue
        start = _parse_dt(t.due_date, t.due_time)
        cycle = cycle_map.get(t.crop_cycle_id)
        crop_name = None
        if cycle and cycle.crop:
            crop_name = cycle.crop.name
        status_map = {"pending": "scheduled", "in_progress": "scheduled", "completed": "completed"}
        priority_map = {"low": "low", "medium": "normal", "high": "high"}

        ctx = _farm_context(db, cycle.farm_id if cycle else None)
        _upsert_event(db, farmer_id, "crop_task", t.task_id or t.id,
                      title=t.title or "Farm Task",
                      description=t.description,
                      event_type="task",
                      start_datetime=start,
                      all_day=(t.due_time is None),
                      status=status_map.get(t.status, "scheduled"),
                      priority=priority_map.get(t.priority, "normal"),
                      crop_name=crop_name,
                      source_page=f"tasks.html?task={t.task_id or t.id}",
                      **ctx)
        count += 1
    db.flush()
    return count


def sync_consultations(db: Session, farmer_id: str) -> int:
    """Sync expert consultations → calendar events."""
    consultations = db.query(Consultation).filter(
        Consultation.farmer_id == farmer_id
    ).all()
    count = 0
    for c in consultations:
        if not c.scheduled_date:
            continue
        start = _parse_dt(c.scheduled_date, c.scheduled_time)
        status_map = {"scheduled": "scheduled", "completed": "completed",
                      "cancelled": "cancelled", "pending": "scheduled"}
        expert_name = ""
        if c.expert:
            expert_name = c.expert.full_name or ""
        _upsert_event(db, farmer_id, "consultation", c.consultation_id or c.id,
                      title=c.topic or f"Expert Consultation{(' - ' + expert_name) if expert_name else ''}",
                      description=c.description,
                      event_type="consultation",
                      start_datetime=start,
                      all_day=(c.scheduled_time is None),
                      status=status_map.get(c.status, "scheduled"),
                      priority="normal",
                      farm_name=c.farm_name,
                      crop_name=c.crop_name,
                      source_page=f"expert.html?ref={c.consultation_id or c.id}")
        count += 1
    db.flush()
    return count


def sync_service_requests(db: Session, farmer_id: str) -> int:
    """Sync service requests → calendar events."""
    requests = db.query(ServiceRequest).filter(
        ServiceRequest.user_id == farmer_id
    ).all()
    count = 0
    for sr in requests:
        if not sr.preferred_date:
            continue
        start = sr.preferred_date  # already a DateTime
        if isinstance(start, str):
            start = _parse_dt(start, sr.preferred_time)
        status_map = {"pending": "scheduled", "confirmed": "scheduled",
                      "in_progress": "scheduled", "completed": "completed",
                      "cancelled": "cancelled"}
        _upsert_event(db, farmer_id, "service_request", sr.service_request_id or sr.id,
                      title=sr.service_name or "Service Request",
                      description=sr.description,
                      event_type="service",
                      start_datetime=start,
                      all_day=(sr.preferred_time is None),
                      status=status_map.get(sr.status, "scheduled"),
                      priority="normal" if sr.urgency == "normal" else (
                          "high" if sr.urgency == "urgent" else "normal"),
                      source_page=f"services.html?req={sr.service_request_id or sr.id}")
        count += 1
    db.flush()
    return count


def sync_worker_bookings(db: Session, farmer_id: str) -> int:
    """Sync worker bookings → calendar events."""
    bookings = db.query(WorkerBooking).filter(
        WorkerBooking.farmer_id == farmer_id
    ).all()
    count = 0
    for wb in bookings:
        if not wb.booking_date:
            continue
        start = _parse_dt(wb.booking_date, wb.start_time)
        status_map = {"pending": "scheduled", "confirmed": "scheduled",
                      "in_progress": "scheduled", "completed": "completed",
                      "cancelled": "cancelled"}
        worker_name = wb.worker.full_name if wb.worker else ""
        ctx = _farm_context(db, wb.farm_id)
        _upsert_event(db, farmer_id, "worker_booking", wb.booking_id or wb.id,
                      title=(wb.work_type or "Worker Booking") + (f" - {worker_name}" if worker_name else ""),
                      description=wb.notes,
                      event_type="worker",
                      start_datetime=start,
                      all_day=(wb.start_time is None),
                      status=status_map.get(wb.status, "scheduled"),
                      priority="normal",
                      **ctx)
        count += 1
    db.flush()
    return count


def sync_equipment_bookings(db: Session, farmer_id: str) -> int:
    """Sync equipment bookings → calendar events."""
    bookings = db.query(EquipmentBooking).filter(
        EquipmentBooking.farmer_id == farmer_id
    ).all()
    count = 0
    for eb in bookings:
        if not eb.booking_date:
            continue
        start = _parse_dt(eb.booking_date, eb.start_time)
        status_map = {"pending": "scheduled", "confirmed": "scheduled",
                      "completed": "completed", "cancelled": "cancelled"}
        equip_name = ""
        if hasattr(eb, 'equipment') and eb.equipment:
            equip_name = eb.equipment.name if eb.equipment else ""
        _upsert_event(db, farmer_id, "equipment_booking", eb.booking_id or eb.id,
                      title=(equip_name or "Equipment Booking"),
                      event_type="equipment",
                      start_datetime=start,
                      all_day=(eb.start_time is None),
                      status=status_map.get(eb.status, "scheduled"),
                      priority="normal",
                      source_page=f"tools.html?book={eb.booking_id or eb.id}")
        count += 1
    db.flush()
    return count


def sync_orders(db: Session, farmer_id: str) -> int:
    """Sync marketplace orders with estimated_delivery → calendar events."""
    orders = db.query(MarketplaceOrder).filter(
        MarketplaceOrder.user_id == farmer_id
    ).all()
    count = 0
    for o in orders:
        if not o.estimated_delivery:
            continue
        start = _parse_dt(o.estimated_delivery)
        if not start:
            continue
        status_map = {"pending": "scheduled", "confirmed": "scheduled",
                      "shipped": "scheduled", "delivered": "completed",
                      "cancelled": "cancelled"}
        _upsert_event(db, farmer_id, "order", o.order_id or o.id,
                      title=f"Order Delivery - {o.order_id or ''}",
                      description=f"Total: Rs.{o.total_amount}" if o.total_amount else None,
                      event_type="order",
                      start_datetime=start,
                      all_day=True,
                      status=status_map.get(o.status, "scheduled"),
                      priority="normal",
                      source_page=f"my-orders.html?order={o.order_id or o.id}")
        count += 1
    db.flush()
    return count


def sync_scheme_applications(db: Session, farmer_id: str) -> int:
    """Sync scheme applications → calendar events (on application date)."""
    apps = db.query(SchemeApplication).filter(
        SchemeApplication.farmer_id == farmer_id
    ).all()
    count = 0
    for sa in apps:
        start = None
        if sa.application_date:
            start = sa.application_date if isinstance(sa.application_date, datetime) else _parse_dt(sa.application_date)
        if not start:
            continue
        scheme_name = sa.scheme.name if sa.scheme else "Scheme Application"
        status_map = {"submitted": "scheduled", "under_review": "scheduled",
                      "approved": "completed", "rejected": "cancelled"}
        _upsert_event(db, farmer_id, "scheme_application", sa.application_id or sa.id,
                      title=f"Scheme: {scheme_name}",
                      description=sa.notes,
                      event_type="scheme",
                      start_datetime=start,
                      all_day=True,
                      status=status_map.get(sa.status, "scheduled"),
                      priority="normal",
                      source_page=f"schemes.html?app={sa.application_id or sa.id}")
        count += 1
    db.flush()
    return count


def sync_insurance_policies(db: Session, farmer_id: str) -> int:
    """Sync insurance policy renewal / premium due dates → calendar events."""
    policies = db.query(InsurancePolicy).filter(
        InsurancePolicy.user_id == farmer_id
    ).all()
    count = 0
    for p in policies:
        # Renewal date
        if p.renewal_date:
            start = _parse_dt(p.renewal_date)
            if start:
                status = "scheduled" if start > datetime.utcnow() else "overdue"
                _upsert_event(db, farmer_id, "insurance_renewal", f"renew-{p.policy_id or p.id}",
                              title=f"Insurance Renewal - {p.policy_type or 'Policy'}",
                              description=f"Provider: {p.provider}" if p.provider else None,
                              event_type="insurance",
                              start_datetime=start,
                              all_day=True,
                              status=status,
                              priority="high",
                              source_page=f"insurance.html?policy={p.policy_id or p.id}")
                count += 1

        # Premium due date
        if p.premium_due_date:
            start = _parse_dt(p.premium_due_date)
            if start:
                status = "scheduled" if start > datetime.utcnow() else "overdue"
                _upsert_event(db, farmer_id, "insurance_premium", f"premium-{p.policy_id or p.id}",
                              title=f"Premium Due - {p.policy_type or 'Policy'}",
                              description=f"Rs.{p.premium_due}" if p.premium_due else None,
                              event_type="insurance",
                              start_datetime=start,
                              all_day=True,
                              status=status,
                              priority="high",
                              source_page=f"insurance.html?policy={p.policy_id or p.id}")
                count += 1

        # End date
        if p.end_date:
            start = _parse_dt(p.end_date)
            if start:
                _upsert_event(db, farmer_id, "insurance_expiry", f"expiry-{p.policy_id or p.id}",
                              title=f"Policy Expiry - {p.policy_type or 'Policy'}",
                              event_type="insurance",
                              start_datetime=start,
                              all_day=True,
                              status="scheduled" if start > datetime.utcnow() else "overdue",
                              priority="high",
                              source_page=f"insurance.html?policy={p.policy_id or p.id}")
                count += 1

    db.flush()
    return count


def sync_crop_cycles(db: Session, farmer_id: str) -> int:
    """Sync crop cycle sowing / expected harvest dates → calendar events."""
    farm_ids = [f.id for f in db.query(Farm.id).filter(Farm.user_id == farmer_id).all()]
    if not farm_ids:
        return 0
    cycles = db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all()
    count = 0
    for c in cycles:
        crop_name = c.crop.name if c.crop else "Crop"
        ctx = _farm_context(db, c.farm_id)

        if c.sowing_date:
            start = _parse_dt(c.sowing_date)
            if start:
                _upsert_event(db, farmer_id, "crop_sowing", f"sow-{c.cycle_id or c.id}",
                              title=f"Sowing - {crop_name}",
                              event_type="crop_activity",
                              start_datetime=start,
                              all_day=True,
                              status="completed" if c.status == "completed" else "scheduled",
                              priority="normal",
                              crop_name=crop_name,
                              source_page=f"farm.html?cycle={c.cycle_id or c.id}",
                              **ctx)
                count += 1

        if c.expected_harvest_date:
            start = _parse_dt(c.expected_harvest_date)
            if start:
                _upsert_event(db, farmer_id, "crop_harvest", f"harvest-{c.cycle_id or c.id}",
                              title=f"Expected Harvest - {crop_name}",
                              event_type="crop_activity",
                              start_datetime=start,
                              all_day=True,
                              status="completed" if c.actual_harvest_date else (
                                  "completed" if start < datetime.utcnow() else "scheduled"
                              ),
                              priority="high",
                              crop_name=crop_name,
                              source_page=f"farm.html?cycle={c.cycle_id or c.id}",
                              **ctx)
                count += 1
    db.flush()
    return count


def sync_enrollments(db: Session, farmer_id: str) -> int:
    """Sync course enrollments → learning reminder events."""
    enrollments = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == farmer_id,
        CourseEnrollment.status.in_(["enrolled", "in_progress"]),
    ).all()
    count = 0
    for e in enrollments:
        start = e.enrolled_at or e.last_activity_at
        if not start:
            continue
        course_title = e.course.title if e.course else "Course"
        _upsert_event(db, farmer_id, "enrollment", e.enrollment_id or e.id,
                      title=f"Continue Learning - {course_title}",
                      description=f"Progress: {e.progress_percentage:.0f}%" if e.progress_percentage else None,
                      event_type="learning",
                      start_datetime=start,
                      all_day=True,
                      status="scheduled",
                      priority="low",
                      source_page=f"learning.html?enroll={e.enrollment_id or e.id}")
        count += 1
    db.flush()
    return count


def sync_emergency_reports(db: Session, farmer_id: str) -> int:
    """Sync emergency reports → calendar events (recorded on the report date)."""
    reports = db.query(EmergencyReport).filter(
        EmergencyReport.farmer_id == farmer_id
    ).all()
    count = 0
    for r in reports:
        start = r.created_at
        if not start:
            continue
        status_map = {"submitted": "scheduled", "acknowledged": "scheduled",
                      "resolved": "completed", "cancelled": "cancelled",
                      "closed": "completed"}
        parts = []
        severity = (r.urgency or "").strip()
        if severity:
            parts.append(f"Urgency: {severity}")
        if r.location:
            parts.append(f"Location: {r.location}")
        _upsert_event(db, farmer_id, "emergency_report", r.reference_id or r.id,
                      title=f"SOS - {r.emergency_type or 'Emergency'}",
                      description=" | ".join(parts) or None,
                      event_type="emergency",
                      start_datetime=start,
                      all_day=True,
                      status=status_map.get(r.status, "scheduled"),
                      priority="high",
                      source_page=f"emergency.html?report={r.reference_id or r.id}")
        count += 1
    db.flush()
    return count


def sync_farm_journal(db: Session, farmer_id: str) -> int:
    """Sync farm journal activities → calendar events."""
    entries = db.query(FarmJournal).filter(FarmJournal.user_id == farmer_id).all()
    count = 0
    for j in entries:
        start = j.entry_date
        if isinstance(start, str):
            start = _parse_dt(str(start)[:10])
        if not start:
            continue
        ctx = _farm_context(db, j.farm_id)
        plot_name = None
        if j.plot_id:
            plot = db.query(FarmPlot).filter(FarmPlot.id == j.plot_id).first()
            if plot:
                plot_name = plot.plot_name
        _upsert_event(db, farmer_id, "farm_journal", j.id,
                      title=j.activity or "Farm Activity",
                      description=j.notes,
                      event_type="farm_activity",
                      start_datetime=start,
                      all_day=True,
                      status="completed",
                      priority="normal",
                      plot_id=j.plot_id,
                      plot_name=plot_name,
                      source_page=f"farm.html?journal={j.id}",
                      **ctx)
        count += 1
    db.flush()
    return count


# ---------------------------------------------------------------------------
# Master sync
# ---------------------------------------------------------------------------

def sync_all_events(db: Session, farmer_id: str) -> dict:
    """Run all sync functions and return a summary."""
    summary = {}
    syncers = [
        ("crop_tasks", sync_crop_tasks),
        ("consultations", sync_consultations),
        ("service_requests", sync_service_requests),
        ("worker_bookings", sync_worker_bookings),
        ("equipment_bookings", sync_equipment_bookings),
        ("orders", sync_orders),
        ("scheme_applications", sync_scheme_applications),
        ("insurance_policies", sync_insurance_policies),
        ("crop_cycles", sync_crop_cycles),
        ("enrollments", sync_enrollments),
        ("farm_journal", sync_farm_journal),
        ("emergency_reports", sync_emergency_reports),
    ]
    for name, fn in syncers:
        try:
            summary[name] = fn(db, farmer_id)
        except Exception as e:
            summary[name] = f"error: {str(e)}"
    db.commit()
    return summary
