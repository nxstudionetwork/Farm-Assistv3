"""Centralized notification helper for event-driven notifications.

Usage from any router:

    from app.utils.notification_helper import create_notification

    create_notification(
        db=db,
        user_id=current_user.id,
        title="Service Request Updated",
        message="Your irrigation service request was accepted.",
        notification_type="service",
        reference_id=sr.id,
        reference_type="service_request",
        icon="fa-wrench",
        action_url="services.html",
    )

The helper uses FA-NOT prefix for notification IDs (consistent with the router).
It does NOT call db.commit() -- the caller must commit as part of their transaction.
"""

from app.utils.auth import generate_id
from app.models.notification import Notification
from app.models.user import UserSettings


# Maps notification_type values used across the app to the user_settings
# preference column that controls them. Types not listed here are never gated.
NOTIFICATION_TYPE_SETTINGS = {
    "weather": "notif_weather",
    "crop_task": "notif_tasks",
    "task": "notif_tasks",
    "market": "notif_market",
    "order": "notif_market",
    "scheme": "notif_govt",
    "government": "notif_govt",
    "govt": "notif_govt",
    "message": "notif_messages",
    "chat": "notif_messages",
    "emergency": "notif_emergency",
}


def disabled_notification_types(settings_row):
    """Return the notification_type values the user has switched off."""
    if settings_row is None:
        return []
    disabled = set()
    for ntype, key in NOTIFICATION_TYPE_SETTINGS.items():
        if getattr(settings_row, key, None) is False:
            disabled.add(ntype)
    return list(disabled)


def notifications_enabled(db, user_id, notification_type):
    """Return False when the user disabled the category handled by this type."""
    key = NOTIFICATION_TYPE_SETTINGS.get((notification_type or "").lower())
    if not key:
        return True
    settings_row = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings_row is None:
        return True
    value = getattr(settings_row, key, None)
    return value if value is not None else True


def create_notification(
    db,
    user_id,
    title,
    message,
    notification_type="system",
    reference_id=None,
    reference_type=None,
    icon=None,
    action_url=None,
):
    if not user_id or not title or not message:
        return None

    # Honour the farmer's notification preferences: skip categories they disabled.
    if not notifications_enabled(db, user_id, notification_type):
        return None

    notif_id = generate_id("FA-NOT", db, Notification)
    notification = Notification(
        notification_id=notif_id,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        reference_id=reference_id,
        reference_type=reference_type,
        icon=icon,
        action_url=action_url,
    )
    db.add(notification)
    return notification