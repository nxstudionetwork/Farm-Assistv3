import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Iterable, List, Type
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func, text

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


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #
# The role is always read back from the database via ``get_current_user``. It is
# deliberately never taken from a JWT claim, a query string, a form field or
# anything the browser can edit, so editing the token or the URL cannot change
# what an account is allowed to reach.
ROLE_FARMER = "farmer"
ROLE_CUSTOMER = "customer"
VALID_ROLES = (ROLE_FARMER, ROLE_CUSTOMER)

# Farmer ID and Customer ID live in different namespaces with different
# shapes, so a value typed into the wrong login form is recognisable and can be
# answered with a useful message instead of a generic "not found".
FARMER_ID_RE = re.compile(r"^FA-AS-\d+$")
CUSTOMER_ID_RE = re.compile(r"^FA-CS-\d+$")


def normalise_role(value: Optional[str]) -> Optional[str]:
    """Return a canonical role, or None when the value names no known role."""
    if value is None:
        return None
    role = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return role if role in VALID_ROLES else None


def user_role(user: Optional[User]) -> str:
    """The effective role of a user row.

    Rows created before the customer role existed carry no explicit role, so
    they are treated as farmers: that is what every one of them already was,
    and defaulting the other way would lock legacy accounts out of their own
    farm.
    """
    if user is None:
        return ""
    role = normalise_role(getattr(user, "role", None))
    return role or ROLE_FARMER


def is_customer(user: Optional[User]) -> bool:
    return user_role(user) == ROLE_CUSTOMER


def is_farmer(user: Optional[User]) -> bool:
    return user_role(user) == ROLE_FARMER


def require_roles(*roles: str) -> Type:
    """Build a dependency that authenticates *and* enforces an account role.

    ``get_current_user`` alone proves who is calling; this additionally proves
    what they are allowed to call. Because the role is read from the users
    table on every request, a customer cannot reach a farmer-only endpoint by
    editing the URL or replaying a token, and a farmer cannot reach
    customer-only endpoints either.
    """
    wanted = tuple(normalise_role(r) or r for r in roles)
    descriptions = ", ".join(f"a {r} account" for r in wanted)

    async def _role_dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if user_role(current_user) not in wanted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires {descriptions}.",
            )
        return current_user

    return _role_dependency


# --------------------------------------------------------------------------- #
# Customer ID
# --------------------------------------------------------------------------- #
CUSTOMER_ID_PREFIX = "FA-CS-"
CUSTOMER_ID_WIDTH = 6
CUSTOMER_ID_SCOPE = "customer_id"
SEQUENCE_SCOPE_CUSTOMER_ID = CUSTOMER_ID_SCOPE


def normalize_customer_id(raw_id: Optional[str]) -> str:
    """Return the canonical ``FA-CS-######`` form of ``raw_id``.

    Returns an empty string when the input cannot be a customer ID at all,
    which lets callers tell "malformed" apart from "well formed but unknown"
    and answer each with the right message.

    A customer typing the bare number ("1234"), a differently-cased prefix
    ("fa-cs-1234") or stray spaces ("FA - CS - 1234") is accepted, because that
    is a formatting slip rather than a wrong identity. Whitespace is removed
    outright since it can never change which account is meant. Anything with a
    non-numeric remainder -- including a Farmer ID -- is rejected.
    """
    if raw_id is None:
        return ""
    # Strip every space before comparing: "FA - CS - 1" and "FA-CS-1" can only
    # ever refer to the same account, so there is nothing to disambiguate.
    text = re.sub(r"\s+", "", str(raw_id)).upper()
    if not text:
        return ""

    if text.startswith(CUSTOMER_ID_PREFIX):
        remainder = text[len(CUSTOMER_ID_PREFIX):]
    else:
        remainder = text

    if not remainder.isdigit():
        return ""

    digits = remainder.lstrip("0") or "0"
    if len(digits) > CUSTOMER_ID_WIDTH:
        return ""
    return f"{CUSTOMER_ID_PREFIX}{digits.zfill(CUSTOMER_ID_WIDTH)}"


def is_customer_id_shape(raw_id: Optional[str]) -> bool:
    """True only for a strictly formatted ``FA-CS-######``."""
    return bool(CUSTOMER_ID_RE.match(str(raw_id or "").strip().upper()))


def allocate_sequence_value(db: Session, scope: str) -> int:
    """Atomically bump the ``scope`` counter and return its new value.

    The read, the increment and the result all happen inside a single
    statement, so two callers racing for the same number are serialised by the
    database on the counter row rather than by luck in Python. That holds for
    simultaneous registrations, retried requests and several server processes
    pointed at one database.

    Engines without ``RETURNING`` (SQLite older than 3.35) take the second
    path. The ``UPDATE ... last_value = last_value + 1`` is the atomic part
    there; reading the row back in the same transaction returns our own value.
    """
    now = datetime.utcnow()
    upsert_returning = text(
        "INSERT INTO id_sequences (scope, last_value, updated_at) "
        "VALUES (:scope, 1, :now) "
        "ON CONFLICT(scope) DO UPDATE SET "
        "last_value = id_sequences.last_value + 1, updated_at = :now "
        "RETURNING last_value"
    )
    try:
        row = db.execute(upsert_returning, {"scope": scope, "now": now}).first()
        if row is not None:
            return int(row[0])
    except Exception:
        # No RETURNING support (or no table yet). Start a clean transaction and
        # fall through to the update-then-read path.
        db.rollback()

    db.execute(
        text(
            "INSERT INTO id_sequences (scope, last_value) VALUES (:scope, 0) "
            "ON CONFLICT(scope) DO NOTHING"
        ),
        {"scope": scope},
    )
    db.execute(
        text("UPDATE id_sequences SET last_value = last_value + 1 WHERE scope = :scope"),
        {"scope": scope},
    )
    row = db.execute(
        text("SELECT last_value FROM id_sequences WHERE scope = :scope"),
        {"scope": scope},
    ).first()
    if row is None:
        raise RuntimeError(f"Unable to allocate a value from sequence '{scope}'")
    return int(row[0])


def seed_sequence_from_max(db: Session, scope: str, table: str, column: str, prefix: str) -> None:
    """Raise the ``scope`` counter to the highest value already stored.

    Called before the first allocation so that a database which somehow
    already holds customer rows (a restore from backup, a partial import) never
    re-issues an ID that is taken. It only ever moves the counter forward, so
    running it on every registration is harmless.
    """
    best = 0
    try:
        for value in db.execute(
            text(f"SELECT {column} FROM {table} WHERE {column} LIKE :prefix"),
            {"prefix": f"{prefix}%"},
        ):
            digits = re.sub(r"\D", "", str(value[0] or ""))
            if digits:
                best = max(best, int(digits))
    except Exception:
        db.rollback()
        return

    if best <= 0:
        return
    try:
        db.execute(
            text(
                "INSERT INTO id_sequences (scope, last_value) VALUES (:scope, :value) "
                "ON CONFLICT(scope) DO UPDATE SET "
                "last_value = CASE WHEN id_sequences.last_value < :value "
                "THEN :value ELSE id_sequences.last_value END"
            ),
            {"scope": scope, "value": best},
        )
    except Exception:
        db.rollback()


def generate_customer_id(db: Session) -> str:
    """Allocate the next unused ``FA-CS-######`` Customer ID.

    The six-digit section comes from the ``id_sequences`` table, never from the
    frontend, a random source or a timestamp. Uniqueness is therefore a
    property of the database rather than of the request that happened to arrive
    first, and the unique index on ``customers.customer_id`` is the final
    authority if anything ever goes wrong anyway.
    """
    seed_sequence_from_max(db, SEQUENCE_SCOPE_CUSTOMER_ID, "customers", "customer_id", CUSTOMER_ID_PREFIX)
    value = allocate_sequence_value(db, SEQUENCE_SCOPE_CUSTOMER_ID)
    return f"{CUSTOMER_ID_PREFIX}{value:0{CUSTOMER_ID_WIDTH}d}"


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
    # Customer-side tables. Without these, generate_id() cannot find the column,
    # silently falls back to "always return 000001" and the second row to be
    # created collides with the unique index on the first.
    "CustomerPointsEntry": "entry_id",
    "CustomerPlant": "plant_id",
    "CustomerSettings": "id",
    "Customer": "customer_id",
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


# Ready-made role gates. ``get_current_farmer`` and ``get_current_customer``
# authenticate the bearer token, load the user from the database and then check
# the role stored on that row -- in that order, and always against the database
# rather than against anything the caller supplied.
get_current_farmer = require_roles(ROLE_FARMER)
get_current_customer = require_roles(ROLE_CUSTOMER)


def assert_role_matches_selection(user: Optional[User], selected_role: Optional[str]) -> None:
    """Reject a login attempt made through the wrong role's form.

    The login page offers a Farmer form and a Customer form. Whichever one the
    person used is sent along, and it has to match the account that was
    actually found. Without this, a Farmer ID typed into the Customer form would
    authenticate a farmer and drop them on the wrong dashboard.
    """
    wanted = normalise_role(selected_role)
    if not wanted or user is None:
        return
    actual = user_role(user)
    if actual == wanted:
        return
    if actual == ROLE_FARMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This ID belongs to a Farmer account. Please use Farmer Login.",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This ID belongs to a Customer account. Please use Customer Login.",
    )
