from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func
import re
from datetime import datetime

from app.database.connection import get_db
from app.models.user import User, UserAddress, FarmerProfile, LoginHistory, UserSettings, UserSession
from app.models.farm import Farm, FarmPlot
from app.models.document import UserDocument
from app.schemas.auth import UserResponse
from app.utils.auth import get_current_user
from app.integrations.file_storage import FileStorageService

router = APIRouter(prefix="/api/v1", tags=["Users"])


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    profile_image: Optional[str] = None
    preferred_language: Optional[str] = None
    farming_experience: Optional[str] = None
    preferred_crops: Optional[str] = None
    aadhaar_number: Optional[str] = None
    pan_number: Optional[str] = None
    irrigation_type: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Name must be at least 2 characters")
            if len(v) > 200:
                raise ValueError("Name must be at most 200 characters")
            if not re.match(r"^[A-Za-z\s.'\-]+$", v):
                raise ValueError("Name can only contain letters, spaces, periods, hyphens, and apostrophes")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is not None:
            v = v.strip().lower()
            if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", v):
                raise ValueError("Please enter a valid email address")
        return v


class AddressRequest(BaseModel):
    address_line: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@router.get("/users/profile", response_model=dict)
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    address = db.query(UserAddress).filter(UserAddress.user_id == current_user.id, UserAddress.is_primary == True).first()
    farmer_profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == current_user.id).first()

    profile_data = UserResponse.model_validate(current_user).model_dump()

    if address:
        profile_data["address"] = {
            "address_line": address.address_line,
            "village": address.village,
            "mandal": address.mandal,
            "district": address.district,
            "state": address.state,
            "country": address.country,
            "pincode": address.pincode,
            "latitude": address.latitude,
            "longitude": address.longitude,
        }

    if farmer_profile:
        profile_data["farmer_profile"] = {
            "farmer_id": farmer_profile.farmer_id,
            "date_of_birth": farmer_profile.date_of_birth,
            "gender": farmer_profile.gender,
            "occupation": farmer_profile.occupation,
            "farming_experience": farmer_profile.farming_experience,
            "preferred_crops": farmer_profile.preferred_crops,
            "aadhaar_number": farmer_profile.aadhaar_number,
            "pan_number": farmer_profile.pan_number,
            "irrigation_type": farmer_profile.irrigation_type,
        }

    return {"status": "success", "data": profile_data}


@router.put("/users/profile", response_model=dict)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.email is not None:
        existing = db.query(User).filter(func.lower(User.email) == payload.email.lower(), User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = payload.email
    sent = payload.model_dump(exclude_unset=True)
    if "profile_image" in sent:
        current_user.profile_image = (payload.profile_image or "").strip() or None
    if payload.preferred_language is not None:
        current_user.preferred_language = payload.preferred_language

    farmer_profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == current_user.id).first()
    if not farmer_profile:
        farmer_profile = FarmerProfile(user_id=current_user.id, farmer_id=current_user.farmer_id, occupation="Farmer")
        db.add(farmer_profile)
        db.flush()
    if payload.farming_experience is not None:
        farmer_profile.farming_experience = payload.farming_experience
    if payload.preferred_crops is not None:
        farmer_profile.preferred_crops = payload.preferred_crops
    if payload.aadhaar_number is not None:
        farmer_profile.aadhaar_number = payload.aadhaar_number
    if payload.pan_number is not None:
        farmer_profile.pan_number = payload.pan_number
    if payload.irrigation_type is not None:
        farmer_profile.irrigation_type = payload.irrigation_type

    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": "Profile updated successfully",
        "data": UserResponse.model_validate(current_user).model_dump(),
    }


@router.put("/users/address", response_model=dict)
def create_or_update_address(
    payload: AddressRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    address = db.query(UserAddress).filter(
        UserAddress.user_id == current_user.id, UserAddress.is_primary == True
    ).first()

    if address:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(address, field, value)
    else:
        address = UserAddress(
            user_id=current_user.id,
            is_primary=True,
            **payload.model_dump(exclude_unset=True),
        )
        db.add(address)

    db.commit()
    db.refresh(address)

    return {
        "status": "success",
        "message": "Address updated successfully",
        "data": {
            "address_line": address.address_line,
            "village": address.village,
            "mandal": address.mandal,
            "district": address.district,
            "state": address.state,
            "country": address.country,
            "pincode": address.pincode,
            "latitude": address.latitude,
            "longitude": address.longitude,
        },
    }


@router.post("/users/profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    import io
    data_uri = "data:" + (file.content_type or "image/png") + ";base64," + __import__("base64").b64encode(content).decode()
    try:
        result = FileStorageService.save_base64_image(data_uri, "profile-pictures")
        file_url = FileStorageService.get_file_url(result["path"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    current_user.profile_image = file_url
    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": "Profile picture updated",
        "data": {"profile_image": file_url},
    }


@router.get("/users/stats")
def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms = db.query(Farm).filter(Farm.user_id == current_user.id, Farm.is_active == True).all()
    farm_count = len(farms)

    total_acres = 0.0
    for farm in farms:
        area = farm.total_area or 0
        unit = (farm.area_unit or "Acres").lower()
        if "hectare" in unit:
            total_acres += area * 2.47105
        elif "acre" in unit:
            total_acres += area
        elif "bigha" in unit:
            total_acres += area * 0.67
        else:
            total_acres += area

    doc_count = db.query(func.count(UserDocument.id)).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.is_deleted == False,
    ).scalar() or 0

    return {
        "status": "success",
        "data": {
            "farm_count": farm_count,
            "total_acres": round(total_acres, 1),
            "document_count": doc_count,
        },
    }


@router.get("/users/activity")
def get_recent_activity(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activities = []

    logins = db.query(LoginHistory).filter(
        LoginHistory.user_id == current_user.id
    ).order_by(LoginHistory.login_time.desc()).limit(5).all()
    for login in logins:
        device_str = ""
        if login.device:
            device_str = login.device
        if login.browser:
            device_str += (" on " + login.browser) if device_str else login.browser
        activities.append({
            "type": "login",
            "icon": "fa-right-to-bracket",
            "icon_class": "info",
            "description": "Logged in" + (" from " + device_str if device_str else ""),
            "timestamp": str(login.login_time) if login.login_time else None,
        })

    docs = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.is_deleted == False,
    ).order_by(UserDocument.created_at.desc()).limit(5).all()
    for doc in docs:
        activities.append({
            "type": "document",
            "icon": "fa-file-arrow-up",
            "icon_class": "",
            "description": "Uploaded document: " + (doc.document_name or "Unnamed"),
            "timestamp": str(doc.created_at) if doc.created_at else None,
        })

    from app.models.wallet import Wallet, WalletTransaction
    wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).first()
    if wallet:
        wallet_txns = db.query(WalletTransaction).filter(
            WalletTransaction.wallet_id == wallet.id
        ).order_by(WalletTransaction.created_at.desc()).limit(5).all()
        for wt in wallet_txns:
            is_credit = wt.transaction_type == "credit"
            activities.append({
                "type": "wallet",
                "icon": "fa-indian-rupee-sign",
                "icon_class": "" if is_credit else "warn",
                "description": ("Received" if is_credit else "Sent") + " " + str(wt.amount) + " via wallet",
                "timestamp": str(wt.created_at) if wt.created_at else None,
            })

    activities.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return {"status": "success", "data": activities[:limit]}


def _ts_parts(value):
    """Split a datetime (or None) into ISO timestamp + date + time strings."""
    if not value:
        return None, None, None, None
    if isinstance(value, datetime):
        iso = value.isoformat()
        date_str = value.strftime("%Y-%m-%d")
        time_str = value.strftime("%I:%M %p")
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            iso = dt.isoformat()
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%I:%M %p")
        except Exception:
            return str(value), None, None, None
    return iso, date_str, time_str, value


def _status_label(status):
    """Title-case a status code for friendly display."""
    if not status:
        return "Pending"
    return " ".join(w.capitalize() for w in str(status).replace("_", " ").split())


@router.get("/users/requests-timeline")
def get_requests_timeline(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate the authenticated farmer's real activity/request history
    (orders, service requests, worker/equipment bookings, consultations and
    feedback) into a single, newest-first timeline.

    Every record is strictly scoped to ``current_user`` (farmer ownership).
    """
    from app.models.marketplace import MarketplaceOrder
    from app.models.service import ServiceRequest
    from app.models.worker import WorkerBooking, EquipmentBooking, Equipment
    from app.models.community import Consultation
    from app.models.feedback import Feedback

    uid = current_user.id
    items = []

    # Marketplace orders
    orders = db.query(MarketplaceOrder).filter(MarketplaceOrder.user_id == uid).all()
    for o in orders:
        iso, date_str, time_str, _ = _ts_parts(o.created_at)
        items.append({
            "kind": "order",
            "type": "Order Placed",
            "title": o.order_id or "Order",
            "subtitle": "Marketplace order",
            "reference": o.order_id,
            "status": o.status or "pending",
            "status_label": _status_label(o.status),
            "amount": o.total_amount,
            "timestamp": iso,
            "date": date_str,
            "time": time_str,
            "description": "Order " + (o.order_id or "") + " - " + _status_label(o.status),
            "source_page": "marketplace.html",
        })

    # Service requests
    service_reqs = db.query(ServiceRequest).filter(ServiceRequest.user_id == uid).all()
    for s in service_reqs:
        iso, date_str, time_str, _ = _ts_parts(s.created_at)
        items.append({
            "kind": "service_request",
            "type": "Service Requested",
            "title": s.service_name or "Service request",
            "subtitle": s.service_category or "Agricultural service",
            "reference": s.service_request_id,
            "status": s.status or "pending",
            "status_label": _status_label(s.status),
            "amount": None,
            "timestamp": iso,
            "date": date_str,
            "time": time_str,
            "description": (s.description or s.service_name or "Service requested"),
            "source_page": "services.html",
        })

    # Worker bookings
    worker_bookings = db.query(WorkerBooking).filter(WorkerBooking.farmer_id == uid).all()
    for b in worker_bookings:
        iso, date_str, time_str, _ = _ts_parts(b.created_at)
        worker_name = b.worker.full_name if b.worker else None
        items.append({
            "kind": "worker_booking",
            "type": "Worker Booked",
            "title": b.work_type or "Farm worker booking",
            "subtitle": worker_name or "Worker booking",
            "reference": b.booking_id,
            "status": b.status or "pending",
            "status_label": _status_label(b.status),
            "amount": b.total_cost,
            "timestamp": iso,
            "date": date_str,
            "time": time_str,
            "description": "Worker booking for " + (b.booking_date or "scheduled date") + (
                " - " + worker_name if worker_name else ""),
            "source_page": "workers.html",
        })

    # Equipment bookings
    equipment_bookings = db.query(EquipmentBooking).filter(EquipmentBooking.farmer_id == uid).all()
    for b in equipment_bookings:
        iso, date_str, time_str, _ = _ts_parts(b.created_at)
        equip_name = None
        equip = db.query(Equipment).filter(Equipment.id == b.equipment_id).first()
        if equip:
            equip_name = equip.name
        items.append({
            "kind": "equipment_booking",
            "type": "Equipment Booked",
            "title": equip_name or "Equipment booking",
            "subtitle": "Equipment hire",
            "reference": b.booking_id,
            "status": b.status or "pending",
            "status_label": _status_label(b.status),
            "amount": b.total_cost,
            "timestamp": iso,
            "date": date_str,
            "time": time_str,
            "description": "Equipment booking for " + (b.booking_date or "scheduled date"),
            "source_page": "equipment.html",
        })

    # Consultations
    consultations = db.query(Consultation).filter(Consultation.farmer_id == uid).all()
    for c in consultations:
        iso, date_str, time_str, _ = _ts_parts(c.created_at)
        expert_name = c.expert.full_name if c.expert else "Expert"
        items.append({
            "kind": "consultation",
            "type": "Consultation Booked",
            "title": c.topic or c.consultation_type or "Expert consultation",
            "subtitle": expert_name + (" - " + c.consultation_type if c.consultation_type else ""),
            "reference": c.consultation_id,
            "status": c.status or "scheduled",
            "status_label": _status_label(c.status),
            "amount": None,
            "timestamp": iso,
            "date": date_str,
            "time": time_str,
            "description": "Scheduled for " + (c.scheduled_date or "TBD") + (
                " " + c.scheduled_time if c.scheduled_time else ""),
            "source_page": "expert.html",
        })

    # Feedback
    feedbacks = db.query(Feedback).filter(Feedback.user_id == uid).all()
    for f in feedbacks:
        iso, date_str, time_str, _ = _ts_parts(f.created_at)
        items.append({
            "kind": "feedback",
            "type": "Feedback Submitted",
            "title": "Feedback" + (" (" + f.feedback_type + ")" if f.feedback_type else ""),
            "subtitle": f.category or "Feedback",
            "reference": f.feedback_id,
            "status": f.status or "new",
            "status_label": _status_label(f.status),
            "amount": None,
            "rating": f.rating,
            "timestamp": iso,
            "date": date_str,
            "time": time_str,
            "description": f.message or f.related_page or "Feedback submitted",
            "related_page": f.related_page,
            "admin_reply": f.admin_reply,
            "source_page": "feedback.html",
        })

    # Sort newest-first by actual timestamp
    items.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    if not limit or limit <= 0:
        limit = 100
    items = items[:limit]

    return {
        "status": "success",
        "data": {
            "farmer_id": current_user.farmer_id,
            "total": len(items),
            "items": items,
        },
    }


@router.get("/users/farms")
def get_user_farms(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms = db.query(Farm).filter(Farm.user_id == current_user.id, Farm.is_active == True).all()
    items = []
    for f in farms:
        items.append({
            "id": f.id,
            "farm_id": f.farm_id,
            "farm_name": f.farm_name,
            "total_area": f.total_area,
            "area_unit": f.area_unit,
            "village": f.village,
            "mandal": f.mandal,
            "district": f.district,
            "state": f.state,
            "farm_type": f.farm_type,
        })
    return {"status": "success", "data": items}


class UserSettingsRequest(BaseModel):
    notif_weather: Optional[bool] = None
    notif_tasks: Optional[bool] = None
    notif_market: Optional[bool] = None
    notif_messages: Optional[bool] = None
    notif_govt: Optional[bool] = None
    notif_emergency: Optional[bool] = None
    privacy_location: Optional[bool] = None
    privacy_profile: Optional[bool] = None
    perm_analytics: Optional[bool] = None
    perm_crop_data: Optional[bool] = None
    perm_market: Optional[bool] = None
    units: Optional[str] = None
    voice_enabled: Optional[bool] = None
    weekly_summary: Optional[bool] = None
    ai_recommendations: Optional[bool] = None
    ai_voice_replies: Optional[bool] = None
    ai_detail: Optional[str] = None
    ai_training: Optional[bool] = None
    farm_default_crop: Optional[str] = None
    farm_land_size: Optional[float] = None
    farm_soil_type: Optional[str] = None
    farm_irrigation: Optional[str] = None


def _get_or_create_settings(db: Session, user_id: str) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)
        db.flush()
    return settings


def _settings_to_dict(s: UserSettings) -> dict:
    return {
        "notif_weather": s.notif_weather,
        "notif_tasks": s.notif_tasks,
        "notif_market": s.notif_market,
        "notif_messages": s.notif_messages,
        "notif_govt": s.notif_govt,
        "notif_emergency": s.notif_emergency,
        "privacy_location": s.privacy_location,
        "privacy_profile": s.privacy_profile,
        "perm_analytics": s.perm_analytics,
        "perm_crop_data": s.perm_crop_data,
        "perm_market": s.perm_market,
        "units": s.units,
        "voice_enabled": s.voice_enabled,
        "weekly_summary": s.weekly_summary,
        "ai_recommendations": s.ai_recommendations,
        "ai_voice_replies": s.ai_voice_replies,
        "ai_detail": s.ai_detail,
        "ai_training": s.ai_training,
        "farm_default_crop": s.farm_default_crop,
        "farm_land_size": s.farm_land_size,
        "farm_soil_type": s.farm_soil_type,
        "farm_irrigation": s.farm_irrigation,
    }


@router.get("/users/settings")
def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_or_create_settings(db, current_user.id)
    db.commit()
    return {"status": "success", "data": _settings_to_dict(s)}


@router.put("/users/settings")
def update_user_settings(
    payload: UserSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_or_create_settings(db, current_user.id)
    updates = payload.model_dump(exclude_unset=True)
    for key, val in updates.items():
        setattr(s, key, val)
    db.commit()
    db.refresh(s)
    return {"status": "success", "message": "Settings saved", "data": _settings_to_dict(s)}


@router.get("/users/sessions")
def get_user_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sessions = db.query(LoginHistory).filter(
        LoginHistory.user_id == current_user.id
    ).order_by(LoginHistory.login_time.desc()).limit(10).all()
    items = []
    for sess in sessions:
        device_str = sess.device or "Unknown Device"
        browser_str = sess.browser or ""
        items.append({
            "id": sess.id,
            "device": device_str,
            "browser": browser_str,
            "ip_address": sess.ip_address,
            "login_time": str(sess.login_time) if sess.login_time else None,
            "login_status": sess.login_status,
        })
    return {"status": "success", "data": items}


@router.post("/users/logout-all-devices")
def logout_all_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Close every other active session belonging to the current user."""
    # Keep the most recent open session (this device) and close the rest.
    open_sessions = (
        db.query(LoginHistory)
        .filter(LoginHistory.user_id == current_user.id, LoginHistory.logout_time.is_(None))
        .order_by(LoginHistory.login_time.desc())
        .all()
    )
    closed = 0
    for idx, entry in enumerate(open_sessions):
        if idx == 0:
            continue  # current/most-recent session stays open
        entry.logout_time = datetime.utcnow()
        closed += 1

    db.query(UserSession).filter(UserSession.user_id == current_user.id).delete()

    db.commit()
    return {
        "status": "success",
        "message": "Logged out all other devices",
        "data": {"closed_sessions": closed},
    }


@router.put("/users/language")
def update_language(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lang = (payload.get("language") or "en").strip()
    valid = ["en", "hi", "mr", "ta", "te", "bn", "gu"]
    if lang not in valid:
        raise HTTPException(status_code=400, detail="Invalid language code")
    current_user.preferred_language = lang
    db.commit()
    return {"status": "success", "message": "Language updated", "data": {"language": lang}}


@router.get("/users/export")
def export_user_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export the current farmer's data as a JSON document for download."""
    settings = _get_or_create_settings(db, current_user.id)
    db.flush()

    farms = db.query(Farm).filter(Farm.user_id == current_user.id).all()
    farm_items = []
    for f in farms:
        farm_items.append({
            "farm_id": f.farm_id,
            "farm_name": f.farm_name,
            "total_area": f.total_area,
            "area_unit": f.area_unit,
            "village": f.village,
            "mandal": f.mandal,
            "district": f.district,
            "state": f.state,
            "farm_type": f.farm_type,
            "soil_type": getattr(f, "soil_type", None),
        })

    sessions = db.query(LoginHistory).filter(
        LoginHistory.user_id == current_user.id
    ).order_by(LoginHistory.login_time.desc()).limit(20).all()
    session_items = [{
        "login_time": str(s.login_time) if s.login_time else None,
        "logout_time": str(s.logout_time) if s.logout_time else None,
        "device": s.device,
        "browser": s.browser,
        "ip_address": s.ip_address,
        "login_status": s.login_status,
    } for s in sessions]

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "farmer": {
            "farmer_id": current_user.farmer_id,
            "full_name": current_user.full_name,
            "phone_number": current_user.phone_number,
            "email": current_user.email,
            "preferred_language": current_user.preferred_language,
            "role": current_user.role,
            "is_verified": current_user.is_verified,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "settings": _settings_to_dict(settings),
        "farms": farm_items,
        "recent_sessions": session_items,
        "statistics": {
            "farm_count": len(farm_items),
            "session_count": len(session_items),
        },
    }
    return {"status": "success", "message": "Data export prepared", "data": payload}


@router.post("/users/delete-account")
def delete_account(
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the current account.

    Requires explicit confirmation from the caller (force=true). The account is
    soft-deactivated so it can no longer log in, and directly owned records are
    removed so the deletion is effective immediately.
    """
    force = bool(payload and payload.get("force"))
    if not force:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Sending force=true permanently deletes your account.",
        )
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="This account is already deactivated")

    current_user.is_active = False

    db.query(UserSettings).filter(UserSettings.user_id == current_user.id).delete()

    from app.models.notification import Notification
    db.query(Notification).filter(Notification.user_id == current_user.id).delete()

    from app.models.support import SupportTicket
    db.query(SupportTicket).filter(SupportTicket.user_id == current_user.id).delete()

    open_login = db.query(LoginHistory).filter(
        LoginHistory.user_id == current_user.id, LoginHistory.logout_time.is_(None)
    ).all()
    for entry in open_login:
        entry.logout_time = datetime.utcnow()

    db.query(UserSession).filter(UserSession.user_id == current_user.id).delete()

    db.commit()
    return {"status": "success", "message": "Account deleted successfully"}
