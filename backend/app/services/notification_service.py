from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.models.farm import gen_uuid


def create_notification(
    db: Session,
    user_id: str,
    title: str,
    message: str,
    notification_type: str,
    reference_id: str = None,
    reference_type: str = None,
    icon: str = None,
    action_url: str = None,
):
    notification = Notification(
        notification_id=f"FA-NOT-{str(uuid.uuid4())[:8].upper()}",
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
    db.commit()
    return notification


def create_crop_task_notification(db: Session, user_id: str, task_title: str, due_date: str):
    return create_notification(
        db, user_id,
        title="Crop Task Reminder",
        message=f"Upcoming task: {task_title} due on {due_date}",
        notification_type="crop_task",
        icon="fa-seedling",
    )


def create_weather_alert(db: Session, user_id: str, alert_message: str):
    return create_notification(
        db, user_id,
        title="Weather Alert",
        message=alert_message,
        notification_type="weather",
        icon="fa-cloud-sun",
    )


def create_order_notification(db: Session, user_id: str, order_id: str, status: str):
    return create_notification(
        db, user_id,
        title="Order Update",
        message=f"Your order {order_id} has been {status}",
        notification_type="order",
        reference_id=order_id,
        reference_type="order",
        icon="fa-shopping-cart",
    )


def create_payment_notification(db: Session, user_id: str, amount: float, status: str):
    return create_notification(
        db, user_id,
        title="Payment Update",
        message=f"Payment of ₹{amount:,.0f} has been {status}",
        notification_type="payment",
        icon="fa-rupee-sign",
    )


def create_scheme_notification(db: Session, user_id: str, scheme_name: str, status: str):
    return create_notification(
        db, user_id,
        title="Scheme Application Update",
        message=f"Your application for {scheme_name} is {status}",
        notification_type="scheme",
        icon="fa-landmark",
    )
