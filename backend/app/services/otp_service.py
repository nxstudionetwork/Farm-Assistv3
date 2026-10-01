"""
One-time-password issuing and delivery.

An OTP is a credential. Whoever completes verification with a valid code for an
existing account is handed an access token, so the code itself is the sensitive
value in this module.

Rules enforced here:

* Codes come from :mod:`secrets`, never :mod:`random`.
* The plaintext code is never persisted, never logged and never returned to a
  client. Only a bcrypt hash is stored (via the shared password hasher).
* Delivery happens through a real SMS/email provider. If no channel is
  configured and delivery is required, issuing fails loudly instead of
  reporting a success that never arrived.
* Request and verify attempts are rate limited per destination and per record.
* The single development escape hatch is gated on an explicit opt-in *and* a
  development environment, and is refused outright in production.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.notifications import EmailService, SMSService
from app.models.user import OTPVerification
from app.utils.auth import hash_password

logger = logging.getLogger(__name__)

# Number of digits in a generated code. 6 digits keeps the online guessing space
# small while remaining typeable on a phone keypad; the per-record attempt cap
# and the send rate limit are what actually bound the attack.
OTP_DIGITS = 6

CHANNEL_PHONE = "phone"
CHANNEL_EMAIL = "email"


class OTPError(Exception):
    """Raised when an OTP cannot be issued. The message is safe to show."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_development() -> bool:
    return settings.APP_ENV.strip().lower() in ("development", "dev", "local")


def dev_echo_allowed() -> bool:
    """
    Whether the OTP may be echoed back to the client for local development.

    Requires both the explicit opt-in and a development environment, so a
    misconfigured production deploy cannot leak codes through a stray
    ``OTP_DEV_ECHO_ENABLED=true``.
    """
    return bool(settings.OTP_DEV_ECHO_ENABLED) and is_development()


def generate_otp_code() -> str:
    """Cryptographically secure numeric code. Never logged or stored raw."""
    upper = 10 ** OTP_DIGITS
    return f"{secrets.randbelow(upper):0{OTP_DIGITS}d}"


def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 4:
        return "****"
    return f"{phone[:2]}****{phone[-2:]}"


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "****"
    local, _, domain = email.partition("@")
    head = local[:1] if local else ""
    return f"{head}***@{domain}"


def mask_destination(channel: str, destination: str) -> str:
    if not destination:
        return ""
    return _mask_email(destination) if channel == CHANNEL_EMAIL else _mask_phone(destination)


def _channel_available(channel: str) -> bool:
    if channel == CHANNEL_PHONE:
        return bool(settings.SMS_PROVIDER_ENABLED and settings.SMS_API_KEY)
    if channel == CHANNEL_EMAIL:
        return bool(settings.EMAIL_PROVIDER_ENABLED and settings.SMTP_HOST)
    return False


def available_channels() -> Tuple[bool, bool]:
    return _channel_available(CHANNEL_PHONE), _channel_available(CHANNEL_EMAIL)


def _enforce_send_rate_limits(db: Session, channel: str, destination: str) -> None:
    """Throttle OTP generation per destination.

    Bounds both guessing (few codes in circulation at once) and SMS/email
    abuse against a destination that did not ask for it.
    """
    now = datetime.utcnow()
    column = OTPVerification.phone if channel == CHANNEL_PHONE else OTPVerification.email
    recent = (
        db.query(OTPVerification)
        .filter(
            column == destination,
            OTPVerification.created_at >= now - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS),
        )
        .order_by(OTPVerification.created_at.desc())
        .first()
    )
    if recent is not None:
        raise OTPError(
            f"Please wait {settings.OTP_RESEND_COOLDOWN_SECONDS} seconds before requesting another code.",
            status_code=429,
        )

    last_hour = (
        db.query(func.count(OTPVerification.id))
        .filter(
            column == destination,
            OTPVerification.created_at >= now - timedelta(hours=1),
        )
        .scalar()
        or 0
    )
    if last_hour >= settings.OTP_MAX_SENDS_PER_HOUR:
        raise OTPError("Too many codes requested. Please try again later.", status_code=429)


def _deliver(channel: str, destination: str, code: str) -> bool:
    """
    Send the code through the real provider.

    Wrapped so a sync FastAPI endpoint can drive the existing async providers.
    """
    import asyncio

    async def _run() -> bool:
        try:
            if channel == CHANNEL_PHONE:
                return bool(await SMSService.send_otp_sms(destination, code))
            if channel == CHANNEL_EMAIL:
                return bool(await EmailService.send_otp_email(destination, code))
        except Exception as exc:  # pragma: no cover - provider failure path
            # Never interpolate the code or the full destination into the log.
            logger.error("OTP delivery failed via %s provider: %s", channel, exc.__class__.__name__)
        return False

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())
    # Already inside an event loop: hand off to a private loop in a worker
    # thread rather than failing the request.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result()


def issue_otp(
    db: Session,
    *,
    channel: str,
    destination: str,
    user_id: Optional[str] = None,
) -> dict:
    """
    Generate, persist and deliver an OTP.

    Returns a JSON-safe dict for the API response. The plaintext code appears
    only when the development escape hatch is explicitly enabled; it is never
    logged, and the persisted record holds a hash only.
    """
    if channel not in (CHANNEL_PHONE, CHANNEL_EMAIL):
        raise OTPError("Unsupported verification channel", status_code=400)
    if not destination:
        raise OTPError("A destination is required for this channel", status_code=400)

    if not dev_echo_allowed() and not _channel_available(channel):
        if settings.OTP_REQUIRE_DELIVERY:
            raise OTPError(
                "We couldn't send a verification code right now. Please try again later.",
                status_code=503,
            )
        logger.warning(
            "OTP issued without delivery: %s provider is not configured (OTP_REQUIRE_DELIVERY is off)",
            channel,
        )

    _enforce_send_rate_limits(db, channel, destination)

    code = generate_otp_code()
    record = OTPVerification(
        user_id=user_id,
        phone=destination if channel == CHANNEL_PHONE else "",
        email=destination if channel == CHANNEL_EMAIL else None,
        otp_hash=hash_password(code),
        expires_at=datetime.utcnow() + timedelta(seconds=settings.OTP_TTL_SECONDS),
    )
    db.add(record)
    db.commit()

    if not dev_echo_allowed():
        delivered = _deliver(channel, destination, code)
        if not delivered and settings.OTP_REQUIRE_DELIVERY:
            # The record is already stored; mark it consumed so a code the user
            # never received cannot be used, and fail the request honestly.
            db.delete(record)
            db.commit()
            raise OTPError(
                "We couldn't send a verification code right now. Please try again later.",
                status_code=503,
            )
        # Audit without the secret: which channel, which masked destination.
        logger.info("OTP issued for %s %s (record %s)", channel, mask_destination(channel, destination), record.id)

    response = {
        "status": "success",
        "message": "Verification code sent",
        "channel": channel,
        "masked": mask_destination(channel, destination),
        "expires_in_seconds": settings.OTP_TTL_SECONDS,
        "max_attempts": settings.OTP_MAX_VERIFY_ATTEMPTS,
    }
    if dev_echo_allowed():
        response["debug_otp"] = code
        response["debug_mode"] = True
    return response


def consume_otp(
    db: Session,
    *,
    channel: str,
    destination: str,
    code: str,
) -> OTPVerification:
    """
    Validate a submitted code and mark the record used.

    Bounded by the per-record attempt cap, the expiry, and the per-destination
    send rate limit.
    """
    column = OTPVerification.phone if channel == CHANNEL_PHONE else OTPVerification.email
    record = (
        db.query(OTPVerification)
        .filter(
            column == destination,
            OTPVerification.verified_at.is_(None),
            OTPVerification.expires_at > datetime.utcnow(),
        )
        .order_by(OTPVerification.created_at.desc())
        .first()
    )
    if record is None:
        raise OTPError("That code is invalid or has expired. Please request a new one.")

    if record.attempts >= settings.OTP_MAX_VERIFY_ATTEMPTS:
        raise OTPError("Too many incorrect attempts. Please request a new code.", status_code=429)

    record.attempts += 1
    from app.utils.auth import verify_password

    if not verify_password(code, record.otp_hash):
        db.commit()
        # Deliberately identical to the expiry message: distinguishing them
        # would confirm that a code existed for this destination.
        raise OTPError("That code is invalid or has expired. Please request a new one.")

    record.verified_at = datetime.utcnow()
    return record
