import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Type
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.database.connection import get_db
from app.models.user import User, UserSession

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[int] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def normalize_phone(raw: Optional[str]) -> str:
    """Return the digits-only form of a phone/contact string."""
    if not raw:
        return ""
    return re.sub(r"\D", "", str(raw))


def phone_lookup_candidates(raw: Optional[str]) -> list:
    """Phone variants to match stored user records.

    Handles the country-code ambiguity: the UI strips everything to a bare
    10-digit number while seed data may store ``+919876543210``. Returns a
    deduped list of plausible stored forms (bare, ``91``-prefixed, ``+91``,
    ``0091``) so logins/OTPs work no matter which form was saved.
    """
    digits = normalize_phone(raw)
    if not digits:
        return []
    if len(digits) == 12 and digits.startswith("91"):
        bare = digits[2:]
    elif len(digits) == 10:
        bare = digits
    else:
        bare = digits[-10:] if len(digits) > 10 else digits
    candidates = {digits, bare}
    if len(bare) == 10:
        candidates.add("91" + bare)
        candidates.add("+91" + bare)
        candidates.add("0091" + bare)
        candidates.add("+91 " + bare)
    return [c for c in candidates if c]


def normalize_farmer_id(raw_id: Optional[str], prefix: str = "FA-AS-") -> str:
    if raw_id is None:
        return ""
    text = str(raw_id).strip().upper()
    if not text:
        return ""

    prefix_upper = prefix.upper()
    if text.startswith(prefix_upper):
        remainder = text[len(prefix_upper):]
        digits = re.sub(r"\D", "", remainder)
        if digits:
            return f"{prefix_upper}{digits.zfill(8)}"
        return f"{prefix_upper}{remainder.strip().zfill(8)}" if remainder.strip() else prefix_upper

    digits = re.sub(r"\D", "", text)
    if digits:
        return f"{prefix_upper}{digits.zfill(8)}"

    return text


FARMER_ID_PREFIX = "FA-AS-"
FARMER_ID_WIDTH = 8
_ID_ALLOCATION_ATTEMPTS = 64


def generate_farmer_id(db: Session) -> str:
    """
    Allocate the next unused 8-digit Farmer ID.

    The obvious ``MAX(farmer_id) + 1`` is unsafe twice over: it is a
    read-modify-write race, so two concurrent registrations can be handed the
    same ID and one of them dies on the unique constraint, and a lexicographic
    MAX over a VARCHAR breaks the moment the counter outgrows its width.

    Instead the numeric part is parsed into a real integer and the candidate is
    verified to be free, considering rows already pending in this session as
    well as committed ones. The database unique index remains the final
    authority; this just makes the common case deterministic and retryable.
    """
    used = set()
    for value in db.query(User.farmer_id).filter(
        User.farmer_id.like(f"{FARMER_ID_PREFIX}%")
    ).all():
        digits = re.sub(r"\D", "", str(value or ""))
        if digits:
            used.add(int(digits))

    num = max(used) + 1 if used else 1
    for _ in range(_ID_ALLOCATION_ATTEMPTS):
        candidate = f"{FARMER_ID_PREFIX}{num:0{FARMER_ID_WIDTH}d}"
        if num not in used:
            return candidate
        num += 1
    raise RuntimeError("Unable to allocate a unique Farmer ID")


ID_COLUMN_MAP: Dict[str, str] = {
    "Farm": "farm_id",
    "FarmPlot": "plot_id",
    "FarmDocument": "document_id",
    "Crop": "crop_id",
    "CropCycle": "cycle_id",
    "CropTask": "task_id",
    "CropHealthCheck": "check_id",
    "Transaction": "transaction_id",
    "Expense": "expense_id",
    "Income": "income_id",
    "Budget": "id",
    "Loan": "loan_id",
    "ServiceRequest": "service_request_id",
    "Worker": "worker_id",
    "WorkerBooking": "booking_id",
    "WorkerPayment": "id",
    "WorkerReview": "id",
    "Equipment": "equipment_id",
    "EquipmentBooking": "booking_id",
    "Seller": "seller_id",
    "Product": "product_id",
    "MarketplaceOrder": "order_id",
    "Payment": "payment_id",
    "DeliveryTracking": "id",
    "GovernmentScheme": "scheme_id",
    "SchemeApplication": "application_id",
    "SchemeDocument": "id",
    "InsurancePolicy": "policy_id",
    "InsuranceClaim": "claim_id",
    "CommunityPost": "post_id",
    "CommunityComment": "id",
    "CommunityLike": "id",
    "CommunitySave": "id",
    "CommunityAnswer": "answer_id",
    "CommunityGroup": "community_id",
    "CommunityGroupMember": "id",
    "CommunityReport": "report_id",
    "Expert": "expert_id",
    "Consultation": "consultation_id",
    "FarmBuzzPost": "post_id",
    "FarmBuzzComment": "id",
    "FarmBuzzLike": "id",
    "FarmBuzzSave": "id",
    "FarmBuzzShare": "id",
    "FarmBuzzFollow": "id",
    "FarmBuzzHashtag": "id",
    "FarmBuzzTrend": "trend_id",
    "FarmBuzzStory": "story_id",
    "FarmBuzzStoryViewer": "id",
    "FarmBuzzView": "id",
    "FarmBuzzReport": "id",
    "FarmBuzzInteraction": "id",
    "Notification": "notification_id",
    "AIConversation": "id",
    "AIRecommendation": "id",
    "MarketplaceListing": "listing_id",
    "MarketplaceSale": "sale_id",
    "MarketplaceRentalRequest": "request_id",
    "MarketplaceBuyerRecommendation": "recommendation_id",
    "WeatherCache": "id",
    "Conversation": "conversation_id",
    "ConversationParticipant": "id",
    "Message": "message_id",
    "MessageReaction": "id",
    "Contact": "id",
    "MessageAttachment": "attachment_id",
    "SupportTicket": "ticket_id",
    "Feedback": "feedback_id",
    "Wallet": "wallet_id",
    "WalletTransaction": "transaction_id",
    "WalletBeneficiary": "id",
    "BankAccount": "account_id",
    "MoneyRequest": "request_id",
    "UserDocument": "document_id",
    "CourseEnrollment": "enrollment_id",
    "NewsArticle": "news_id",
    "SavedNews": "saved_id",
    "MarketPrice": "price_id",
    "MarketDataSync": "id",
    "MarketWatchlist": "watch_id",
    "MarketPriceAlert": "alert_id",
    "AgriculturalLoanProduct": "product_id",
    "SavedAgriculturalLoan": "id",
    "AgriculturalLoanApplication": "application_id",
    "AgriculturalLoanDocument": "id",
    "AgriculturalFarmerLoan": "farmer_loan_id",
    "AgriculturalLoanRepayment": "repayment_id",
    "AgriculturalLoanEligibility": "id",
    "InsuranceProduct": "insurance_id",
    "SavedInsurance": "id",
    "InsuranceApplication": "application_id",
    "InsuranceApplicationDocument": "id",
    "InsurancePayment": "payment_id",
    "InsuranceClaimDocument": "id",
    "CalendarEvent": "event_id",
    "Livestock": "animal_id",
    "LivestockHealthRecord": "record_id",
    "LivestockVaccination": "vacc_id",
    "LivestockTreatment": "treatment_id",
    "LivestockFeedingRecord": "feed_id",
    "LivestockBreedingRecord": "breeding_id",
    "LivestockWeightRecord": "weight_id",
    "LivestockProductionRecord": "production_id",
    "LivestockExpenseRecord": "expense_id",
    "HydroponicUnit": "unit_id",
    "HydroponicCrop": "cycle_id",
    "HydroponicWaterLog": "log_id",
    "HydroponicHealthRecord": "record_id",
    "HydroponicProductionRecord": "production_id",
}


def generate_id(prefix: str, db: Session, model_class) -> str:
    model_name = model_class.__name__
    col_name = ID_COLUMN_MAP.get(model_name)
    if not col_name:
        col_name = f"{model_name.lower()}_id"
    col = getattr(model_class, col_name, None)
    if col is None:
        return f"{prefix}-{str(1).zfill(6)}"
    nums = set()
    try:
        rows = db.query(col).filter(col.like(f'{prefix}-%')).all()
    except Exception:
        rows = []
    for row in rows:
        value = row[0] if not isinstance(row, (str,)) else row
        if value:
            try:
                part = str(value).split('-')[-1]
                if part.isdigit():
                    nums.add(int(part))
            except (ValueError, IndexError):
                continue
    # Include ids from objects already added to this session but not yet
    # flushed, otherwise two pending rows can be assigned the same id and a
    # UNIQUE constraint fails at commit time.
    try:
        for _obj in list(db.new):
            _value = getattr(_obj, col_name, None)
            if _value:
                _part = str(_value).split('-')[-1]
                if _part.isdigit():
                    nums.add(int(_part))
    except Exception:
        pass
    num = (max(nums) + 1) if nums else 1
    return f"{prefix}-{str(num).zfill(6)}"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    # Honour logout. A JWT is valid until it expires, so without this check a
    # token captured before logout keeps working for the full 8h lifetime.
    # Sessions that were never registered in user_sessions (older tokens issued
    # before session tracking existed) are still honoured.
    jti = payload.get("jti")
    if jti:
        session = db.query(UserSession).filter(UserSession.token_jti == jti).first()
        if session and session.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked. Please sign in again.",
            )
    return user


def revoke_session_by_jti(db: Session, token: str) -> bool:
    """Mark the session behind ``token`` as revoked. Returns True if a live
    session was found. Safe to call twice and with an already-invalid token."""
    payload = decode_token(token)
    jti = payload.get("jti") if payload else None
    if not jti:
        return False
    session = db.query(UserSession).filter(UserSession.token_jti == jti).first()
    if not session or session.revoked_at is not None:
        return False
    session.revoked_at = datetime.utcnow()
    db.commit()
    return True


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
