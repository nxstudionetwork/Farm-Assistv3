"""Worker booking lifecycle + status logic (single source of truth).

The booking lifecycle is enforced here, never re-derived on the frontend:

    pending / confirmed  ->  in_progress  ->  completed
                          ->  cancelled (explicit action only)
    pending / confirmed / in_progress  ->  missed (automatic, when the
                                           scheduled time passes without
                                           completion)

Rules enforced by this module:

* ``cancelled`` is a terminal state reached ONLY through an explicit,
  authorized cancellation action. A booking whose date/time simply passes is
  NEVER marked cancelled.
* ``missed`` is the automatic outcome for a scheduled booking whose service
  window passed without completion. Completed and explicitly cancelled
  bookings are never modified by the auto-overdue process.
* Every status change is recorded in ``worker_booking_status_history`` so the
  reason behind the current status is always explainable.
* The clock is ``datetime.utcnow()`` (naive UTC), consistent with the rest of
  the application.
"""

from datetime import datetime, timedelta
from typing import Optional

from app.models.farm import gen_uuid
from app.models.worker import (
    WorkerBooking,
    WorkerBookingStatusHistory,
)
from app.utils.notification_helper import create_notification

#: Statuses that are still "live" (the service window has not yet concluded).
ACTIVE_STATUSES = ("pending", "confirmed", "in_progress")

#: Terminal statuses; nothing may leave them.
TERMINAL_STATUSES = ("completed", "cancelled", "missed")

#: Valid transitions. An empty tuple means the status is terminal.
#: ``pending`` -> ``confirmed`` is the manual (unpaid) confirmation path;
#: paid bookings are created directly as "confirmed".
#: ``missed`` -> ``completed`` is a recovery path: a farmer may later confirm
#: that the work actually happened, fixing a wrongly auto-missed booking.
TRANSITIONS = {
    "pending": ("confirmed", "in_progress", "cancelled"),
    "confirmed": ("in_progress", "cancelled"),
    "in_progress": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
    "missed": ("completed",),
}

STATUS_DISPLAY_LABELS = {
    "pending": "Pending",
    "confirmed": "Upcoming",
    "in_progress": "In Progress",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "missed": "Missed",
}


def now_utc() -> datetime:
    return datetime.utcnow()


def parse_booking_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def parse_booking_time(value):
    """Parse 'HH:MM' -> datetime.time. Returns None when missing/invalid."""
    if not value:
        return None
    parts = str(value).strip().split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return datetime.strptime(f"{h:02d}:{m:02d}", "%H:%M").time()
    except (ValueError, TypeError, IndexError):
        return None


def scheduled_window_end(booking: WorkerBooking) -> Optional[datetime]:
    """Return the end of the booking's scheduled service window (naive UTC).

    * end date = booking_date + duration_days - 1
    * end time = end_time, falling back to start_time
    * with no time at all the whole final day is the window (23:59:59)
    * unparseable date -> None (never auto-swept)
    """
    start_date = parse_booking_date(booking.booking_date)
    if start_date is None:
        return None
    days = int(booking.duration_days or 1)
    end_date = start_date + timedelta(days=max(days, 1) - 1)
    t = parse_booking_time(booking.end_time or booking.start_time)
    if t is None:
        return datetime.combine(end_date, datetime.strptime("23:59:59", "%H:%M:%S").time())
    return datetime.combine(end_date, t)


def scheduled_window_start(booking: WorkerBooking) -> Optional[datetime]:
    """Start of the service window (booking_date + start_time or 00:00)."""
    start_date = parse_booking_date(booking.booking_date)
    if start_date is None:
        return None
    t = parse_booking_time(booking.start_time)
    if t is None:
        return datetime.combine(start_date, datetime.strptime("00:00:00", "%H:%M:%S").time())
    return datetime.combine(start_date, t)


def record_status_history(
    db,
    booking: WorkerBooking,
    new_status: str,
    previous_status: Optional[str] = None,
    note: Optional[str] = None,
    changed_by: str = "farmer",
) -> WorkerBookingStatusHistory:
    entry = WorkerBookingStatusHistory(
        id=gen_uuid(),
        booking_id=booking.id,
        previous_status=previous_status if previous_status is not None else booking.status,
        new_status=new_status,
        note=note,
        changed_by=changed_by,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    return entry


def _notify(db, user_id, booking_id, title, message, icon, action_url="workers.html"):
    create_notification(
        db=db,
        user_id=user_id,
        title=title,
        message=message,
        notification_type="task",
        reference_id=booking_id,
        reference_type="worker_booking",
        icon=icon,
        action_url=action_url,
    )


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, ())


def mark_missed(db, booking: WorkerBooking, now: Optional[datetime] = None) -> bool:
    """Auto-close a booking whose service window passed without completion.

    Only touches live bookings (pending/confirmed/in_progress). Completed and
    explicitly cancelled bookings are left untouched, as is anything already
    missed. Returns True when the booking was changed.
    """
    if booking.status not in ACTIVE_STATUSES:
        return False
    now = now or now_utc()
    window_end = scheduled_window_end(booking)
    if window_end is None or window_end >= now:
        return False

    previous = booking.status
    booking.status = "missed"
    booking.missed_at = now
    booking.updated_at = now
    record_status_history(
        db,
        booking,
        new_status="missed",
        previous_status=previous,
        note="Scheduled time passed without the service being completed.",
        changed_by="system",
    )
    _notify(
        db,
        booking.farmer_id,
        booking.id,
        "Worker Booking Missed",
        f"Booking {booking.booking_id} was scheduled for {booking.booking_date}"
        + (f" at {booking.start_time or booking.end_time}" if (booking.start_time or booking.end_time) else "")
        + " but was not completed. Marked as missed.",
        "fa-calendar-times",
    )
    return True


def run_overdue_sweep(db, now: Optional[datetime] = None) -> dict:
    """Find live bookings whose scheduled time passed and mark them missed.

    Idempotent: bookings already missed/completed/cancelled are not touched,
    so repeated sweeps never rewrite the same rows.
    """
    now = now or now_utc()
    changed = 0
    inspected = 0
    bookings = (
        db.query(WorkerBooking)
        .filter(WorkerBooking.status.in_(ACTIVE_STATUSES))
        .all()
    )
    for b in bookings:
        inspected += 1
        if mark_missed(db, b, now=now):
            changed += 1
    if changed:
        db.commit()
    return {"inspected": inspected, "missed": changed}


def apply_status_transition(
    db,
    booking: WorkerBooking,
    new_status: str,
    *,
    changed_by: str = "farmer",
    note: Optional[str] = None,
    cancel_reason: Optional[str] = None,
    notification_message: Optional[str] = None,
    now: Optional[datetime] = None,
) -> WorkerBooking:
    """Apply a validated status transition and record history.

    Raises ValueError with a user-friendly message on invalid transitions.
    The caller is responsible for committing and any side effects (refunds).
    ``notification_message`` overrides the default notification body.
    """
    now = now or now_utc()
    previous = booking.status

    if new_status not in TRANSITIONS:
        raise ValueError(f"Invalid status '{new_status}'.")

    if not can_transition(previous, new_status):
        if previous in TERMINAL_STATUSES:
            raise ValueError(
                f"This booking is already {STATUS_DISPLAY_LABELS.get(previous, previous)} and cannot be changed."
            )
        raise ValueError(
            f"Cannot change status from '{STATUS_DISPLAY_LABELS.get(previous, previous)}' to "
            f"'{STATUS_DISPLAY_LABELS.get(new_status, new_status)}'."
        )

    if new_status == "in_progress":
        window_start = scheduled_window_start(booking)
        if window_start is not None and window_start > now:
            raise ValueError(
                "The work cannot be started before its scheduled date/time. "
                f"It is scheduled for {booking.booking_date}"
                + (f" at {booking.start_time}" if booking.start_time else ".")
            )
        if previous == "pending":
            # Starting a pending unpaid booking implies it is accepted.
            booking.status = "confirmed"
            booking.updated_at = now
            record_status_history(
                db,
                booking,
                new_status="confirmed",
                previous_status=previous,
                note="Booking accepted by the farmer.",
                changed_by=changed_by,
            )
        booking.status = "in_progress"
        booking.started_at = now
        booking.updated_at = now
        record_status_history(
            db,
            booking,
            new_status="in_progress",
            previous_status=booking.status if booking.status != "in_progress" else previous,
            note=note or "Work on the job has started.",
            changed_by=changed_by,
        )
        _notify(
            db,
            booking.farmer_id,
            booking.id,
            "Worker Booking Started",
            notification_message or f"Work on booking {booking.booking_id} has started.",
            "fa-play-circle",
        )
        return booking

    if new_status == "completed":
        booking.status = "completed"
        booking.completed_at = now
        booking.updated_at = now
        if previous == "missed":
            note = note or "The work was completed after the booking was marked as missed."
            booking.missed_at = None
        record_status_history(
            db,
            booking,
            new_status="completed",
            previous_status=previous,
            note=note or "The work was completed.",
            changed_by=changed_by,
        )
        _notify(
            db,
            booking.farmer_id,
            booking.id,
            "Worker Booking Completed",
            notification_message or f"Booking {booking.booking_id} has been completed. You can now leave a review.",
            "fa-check-circle",
        )
        return booking

    if new_status == "confirmed":
        booking.status = "confirmed"
        booking.updated_at = now
        record_status_history(
            db,
            booking,
            new_status="confirmed",
            previous_status=previous,
            note=note or "Booking confirmed.",
            changed_by=changed_by,
        )
        _notify(
            db,
            booking.farmer_id,
            booking.id,
            "Booking Confirmed",
            notification_message or f"Booking {booking.booking_id} has been confirmed.",
            "fa-calendar-check",
        )
        return booking

    if new_status == "cancelled":
        booking.status = "cancelled"
        booking.cancelled_at = now
        booking.cancelled_by = changed_by
        booking.cancel_reason = cancel_reason or note
        booking.updated_at = now
        record_status_history(
            db,
            booking,
            new_status="cancelled",
            previous_status=previous,
            note=cancel_reason or note or "Booking cancelled.",
            changed_by=changed_by,
        )
        _notify(
            db,
            booking.farmer_id,
            booking.id,
            "Worker Booking Cancelled",
            notification_message or f"Booking {booking.booking_id} has been cancelled.",
            "fa-calendar-times",
        )
        return booking

    # Should not be reachable given TRANSITIONS.
    raise ValueError(f"Cannot change status from '{previous}' to '{new_status}'.")