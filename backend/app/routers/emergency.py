import asyncio
import uuid
import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database.connection import get_db
from app.models.emergency import EmergencyReport
from app.utils.auth import get_current_user
from app.services.notification_service import create_notification as create_db_notification
from app.integrations.notifications import SMSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Emergency"])

VALID_URGENCIES = {"immediate", "within_24_hours", "within_2_days"}
VALID_EMERGENCY_TYPES = {
    "Pest Control", "Crop Disease", "Flood / Storm", "Equipment Failure",
    "Crop / Farm Fire", "Severe Weather", "Livestock Emergency",
}


def _gen_reference_id(db: Session) -> str:
    last = (
        db.query(EmergencyReport)
        .filter(EmergencyReport.reference_id.isnot(None))
        .order_by(desc(EmergencyReport.created_at))
        .first()
    )
    num = 1
    if last and last.reference_id:
        try:
            num = int(last.reference_id.split("-")[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    return f"ER-{num:06d}"


def _report_dict(r: EmergencyReport) -> dict:
    return {
        "id": r.id,
        "reference_id": r.reference_id,
        "farmer_id": r.farmer_id,
        "emergency_type": r.emergency_type,
        "urgency": r.urgency,
        "location": r.location,
        "latitude": r.latitude,
        "longitude": r.longitude,
        "contact_phone": r.contact_phone,
        "reference_name": r.reference_name,
        "message": r.message,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _validate_report(payload: dict) -> None:
    emergency_type = (payload.get("emergency_type") or "").strip()
    urgency = (payload.get("urgency") or "").strip().lower()
    location = (payload.get("location") or "").strip()
    contact_phone = (payload.get("contact_phone") or "").strip()
    reference_name = (payload.get("reference_name") or "").strip()
    message = (payload.get("message") or "").strip()

    if not emergency_type:
        raise HTTPException(status_code=400, detail="Emergency type is required")
    if emergency_type not in VALID_EMERGENCY_TYPES:
        raise HTTPException(status_code=400, detail="Invalid emergency type")
    if not urgency:
        raise HTTPException(status_code=400, detail="Urgency is required")
    if urgency not in VALID_URGENCIES:
        raise HTTPException(status_code=400, detail="Invalid urgency level")
    if not location:
        raise HTTPException(status_code=400, detail="Location is required")
    if not contact_phone:
        raise HTTPException(status_code=400, detail="Contact phone is required")
    if not re.fullmatch(r"\d{10}", contact_phone):
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit phone number.")
    if not reference_name or not re.fullmatch(r"[^\W\d_][\w\s.'-]*", reference_name, re.UNICODE):
        raise HTTPException(status_code=400, detail="Name is required")
    if len(location) > 300:
        raise HTTPException(status_code=400, detail="Location is too long")
    if len(reference_name) > 200:
        raise HTTPException(status_code=400, detail="Name is too long")
    if len(message) > 5000:
        raise HTTPException(status_code=400, detail="Message is too long")
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=400, detail="Both location coordinates are required")
    if latitude is not None and (not isinstance(latitude, (int, float)) or not -90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="Invalid latitude")
    if longitude is not None and (not isinstance(longitude, (int, float)) or not -180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid longitude")


@router.post("/emergency/reports", status_code=201)
def create_emergency_report(payload: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _validate_report(payload)

    emergency_type = (payload.get("emergency_type") or "").strip()
    location = (payload.get("location") or "").strip()
    contact_phone = (payload.get("contact_phone") or "").strip()
    urgency = (payload.get("urgency") or "").strip().lower()

    # Idempotency guard: reject an identical report from the same farmer within 60s
    # to protect against accidental duplicate taps / rapid double submissions.
    cutoff = datetime.utcnow() - timedelta(seconds=60)
    dup = (
        db.query(EmergencyReport)
        .filter(
            EmergencyReport.farmer_id == current_user.id,
            EmergencyReport.emergency_type == emergency_type,
            EmergencyReport.location == location,
            EmergencyReport.contact_phone == contact_phone,
            EmergencyReport.urgency == urgency,
            EmergencyReport.created_at >= cutoff,
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=429, detail="A matching emergency report was just submitted. Please wait a moment before trying again.")

    report = EmergencyReport(
        id=str(uuid.uuid4()),
        reference_id=_gen_reference_id(db),
        farmer_id=current_user.id,
        emergency_type=emergency_type,
        urgency=urgency,
        location=location,
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        contact_phone=contact_phone,
        reference_name=(payload.get("reference_name") or "").strip(),
        message=(payload.get("message") or "").strip() or None,
        status="submitted",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # In-app notification tied to the authenticated farmer (not global).
    try:
        create_db_notification(
            db=db,
            user_id=current_user.id,
            title="Emergency Report Received",
            message=f"Your {emergency_type} emergency report was successfully received (Ref {report.reference_id}). We will reach you soon.",
            notification_type="emergency",
            reference_id=report.id,
            reference_type="emergency_report",
            icon="fa-triangle-exclamation",
            action_url="emergency.html",
        )
    except Exception as e:  # notification must never block report success
        logger.warning(f"Failed to create emergency notification: {e}")

    # SMS attempt. Only report success if the provider is actually configured.
    sms_status = "not_configured"
    try:
        sent = asyncio.run(
            SMSService.send_sms(
                contact_phone,
                f"Farm Assist: Your emergency report ({report.reference_id}) has been received. We will reach you soon.",
            )
        )
        sms_status = "sent" if sent else "not_configured"
    except Exception as e:
        logger.warning(f"Emergency SMS attempt failed for {contact_phone}: {e}")
        sms_status = "failed"

    result = _report_dict(report)
    result["notification_created"] = True
    result["sms_status"] = sms_status
    return {"status": "success", "data": result}


@router.get("/emergency/reports")
def list_emergency_reports(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    reports = (
        db.query(EmergencyReport)
        .filter(EmergencyReport.farmer_id == current_user.id)
        .order_by(desc(EmergencyReport.created_at))
        .all()
    )
    return {
        "status": "success",
        "data": {
            "reports": [_report_dict(r) for r in reports],
            "total": len(reports),
        },
    }


@router.get("/emergency/reports/{report_id}")
def get_emergency_report(report_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    report = (
        db.query(EmergencyReport)
        .filter(EmergencyReport.id == report_id, EmergencyReport.farmer_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Emergency report not found")
    return {"status": "success", "data": _report_dict(report)}
