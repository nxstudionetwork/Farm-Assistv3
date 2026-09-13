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
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


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


def generate_farmer_id(db: Session) -> str:
    last = db.query(func.max(User.farmer_id)).filter(
        User.farmer_id.like('FA-AS-%')
    ).scalar()

    num = 1
    if last:
        try:
            candidate = str(last).strip().upper()
            if candidate.startswith('FA-AS-'):
                candidate = candidate.replace('FA-AS-', '', 1)
            digits = re.sub(r"\D", "", candidate)
            if digits:
                num = int(digits) + 1
        except (ValueError, TypeError):
            num = 1
    return f"FA-AS-{str(num).zfill(8)}"


ID_COLUMN_MAP: Dict[str, str] = {
    "Farm": "farm_id",
    "FarmPlot": "plot_id",
    "FarmDocument": "document_id",
    "Crop": "crop_id",
    "CropCycle": "cycle_id",
    "CropTask": "task_id",
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
}


def generate_id(prefix: str, db: Session, model_class) -> str:
    model_name = model_class.__name__
    col_name = ID_COLUMN_MAP.get(model_name)
    if not col_name:
        col_name = f"{model_name.lower()}_id"
    col = getattr(model_class, col_name, None)
    if col is None:
        return f"{prefix}-{str(1).zfill(6)}"
    try:
        rows = db.query(col).filter(col.like(f'{prefix}-%')).all()
    except Exception:
        rows = []
    nums = []
    for row in rows:
        value = row[0] if not isinstance(row, (str,)) else row
        if value:
            try:
                part = str(value).split('-')[-1]
                if part.isdigit():
                    nums.append(int(part))
            except (ValueError, IndexError):
                continue
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
    return user


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
