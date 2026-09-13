"""Calendar reminder service.

Computes due reminder times from ``CalendarEvent.reminder_config`` and pushes
them through the existing Farm Assist notification system.

Deduplication uses ``(event_id, offset_seconds, reminder_datetime)`` stored in
``Notification.reference_id`` with ``reference_type="calendar_reminder"``, so:

* the same reminder is never created twice,
* rescheduling / date changes never re-fire the old reminder,
* cancelled / completed / deleted events never generate reminders.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.models.notification import Notification
from app.services.notification_service import create_notification

_EVENT_ICON = {
    "task": "fa-clipboard-check",
    "consultation": "fa-user-tie",
    "service": "fa-tools",
    "worker": "fa-users",
    "equipment": "fa-tractor",
    "order": "fa-shopping-bag",
    "scheme": "fa-landmark",
    "insurance": "fa-shield-halved",
    "crop_activity": "fa-seedling",
    "farm_activity": "fa-trowel",
    "learning": "fa-graduation-cap",
    "document": "fa-file-lines",
    "weather": "fa-cloud-sun",
    "manual": "fa-calendar-plus",
}


def _parse_config(config):
    """Parse reminder_config ("at_event,5m,15m,1h,1d") into timedelta offsets."""
    if not config:
        return []
    offsets = []
    for part in str(config).split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part == "at_event":
            offsets.append(timedelta(0))
        elif part.endswith("m") and part[:-1].isdigit():
            offsets.append(timedelta(minutes=int(part[:-1])))
        elif part.endswith("h") and part[:-1].isdigit():
            offsets.append(timedelta(hours=int(part[:-1])))
        elif part.endswith("d") and part[:-1].isdigit():
            offsets.append(timedelta(days=int(part[:-1])))
    return offsets


def _format_when(dt, now):
    """Human readable reminder time, e.g. 'Today at 9:00 AM'."""
    if not dt:
        return ""
    time = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == now.date():
        return f"Today at {time}"
    tomorrow = now.date() + timedelta(days=1)
    if dt.date() == tomorrow:
        return f"Tomorrow at {time}"
    return f"{dt.strftime('%A, %d %b')} at {time}"


def process_due_reminders(db: Session, farmer_id: str = None, now=None):
    """Create notifications for reminders that are due.

    Only future events (start >= now) with status not completed/cancelled are
    considered, so overdue/cancelled events never spam notifications.
    """
    now = now or datetime.utcnow()
    q = db.query(CalendarEvent).filter(
        CalendarEvent.reminder_config.isnot(None),
        CalendarEvent.reminder_config != "",
        CalendarEvent.status.notin_(["completed", "cancelled"]),
    )
    if farmer_id:
        q = q.filter(CalendarEvent.farmer_id == farmer_id)
    events = q.all()

    created = 0
    for ev in events:
        if not ev.start_datetime or ev.start_datetime < now:
            continue
        context = " • ".join(
            x for x in (ev.crop_name, ev.plot_name, ev.farm_name) if x
        ) or "Scheduled activity"
        for offset in _parse_config(ev.reminder_config):
            reminder_time = ev.start_datetime - offset
            if reminder_time > now:
                continue  # not due yet
            dedup_key = (
                f"{ev.event_id}|{int(offset.total_seconds())}|{reminder_time.isoformat()}"
            )
            exists = db.query(Notification).filter(
                Notification.user_id == ev.farmer_id,
                Notification.reference_type == "calendar_reminder",
                Notification.reference_id == dedup_key,
            ).first()
            if exists:
                continue
            create_notification(
                db,
                ev.farmer_id,
                title=f"Reminder: {ev.title}",
                message=f"{ev.title}\n{context}\n{_format_when(reminder_time, now)}",
                notification_type="calendar_reminder",
                reference_id=dedup_key,
                reference_type="calendar_reminder",
                icon=_EVENT_ICON.get(ev.event_type, "fa-bell"),
                action_url=ev.source_page,
            )
            created += 1
    return created