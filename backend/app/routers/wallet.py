import random
import re
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.config import settings
from app.database.connection import get_db
from app.utils.auth import (
    get_current_user,
    generate_id,
    verify_password,
    hash_password,
    normalize_farmer_id,
)
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction, WalletBeneficiary, MoneyRequest, BankAccount
from app.models.notification import Notification
from app.models.finance import Income, Expense
from app.utils.notification_helper import create_notification

router = APIRouter(prefix="/api/v1", tags=["Digital Wallet"])


class WalletSetupRequest(BaseModel):
    wallet_pin: str
    confirm_pin: str


class AddMoneyRequest(BaseModel):
    amount: float
    payment_method: str = "bank_transfer"
    note: Optional[str] = None
    idempotency_key: Optional[str] = None


class TransferRequest(BaseModel):
    recipient_id: str
    amount: float
    note: Optional[str] = None
    wallet_pin: str
    idempotency_key: Optional[str] = None


class BeneficiaryRequest(BaseModel):
    beneficiary_farmer_id: Optional[str] = None
    beneficiary_name: str
    beneficiary_upi: Optional[str] = None
    beneficiary_phone: Optional[str] = None


class VerifyPinRequest(BaseModel):
    wallet_pin: str


class SearchUserRequest(BaseModel):
    query: str


class MoneyRequestCreate(BaseModel):
    recipient_id: str
    amount: float
    note: Optional[str] = None


class BankAccountAdd(BaseModel):
    bank_name: str
    account_holder_name: str
    account_number: str
    ifsc_code: str
    account_type: str = "savings"


class ChangePinRequest(BaseModel):
    current_pin: str
    new_pin: str
    confirm_pin: str


class WithdrawRequest(BaseModel):
    bank_account_id: str
    amount: float
    wallet_pin: str
    idempotency_key: Optional[str] = None


def _get_wallet(db: Session, user_id: str) -> Optional[Wallet]:
    return db.query(Wallet).filter(Wallet.user_id == user_id).first()


def _ensure_wallet(db: Session, user: User) -> Wallet:
    wallet = _get_wallet(db, user.id)
    if wallet:
        return wallet
    wallet = Wallet(
        wallet_id=generate_id("FA-WLT", db, Wallet),
        user_id=user.id,
        farmer_id=user.farmer_id or "",
        balance=0.0,
        wallet_pin_hash=None,
        is_active=True,
        is_setup_complete=False,
        upi_id=f"{(user.farmer_id or 'farmer').lower()}@farmassist",
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


def _wallet_to_dict(wallet: Wallet) -> dict:
    return {
        "wallet_id": wallet.wallet_id,
        "farmer_id": wallet.farmer_id,
        "balance": round(float(wallet.balance or 0), 2),
        "is_active": bool(wallet.is_active),
        "is_setup_complete": bool(wallet.is_setup_complete),
        "upi_id": wallet.upi_id,
        "limits": {
            "single_deposit": round(float(getattr(settings, "WALLET_MAX_SINGLE_DEPOSIT", 50000.0)), 2),
            "daily_deposit": round(float(getattr(settings, "WALLET_MAX_DAILY_DEPOSITS", 100000.0)), 2),
        },
        "created_at": str(wallet.created_at) if wallet.created_at else None,
    }


def _user_safe_info(user: User) -> dict:
    phone = user.phone_number or ""
    clean_phone = re.sub(r"\D", "", phone)
    if len(clean_phone) >= 10:
        masked_phone = clean_phone[-10:-7] + "****" + clean_phone[-2:]
    else:
        masked_phone = phone[:3] + "****" + phone[-2:] if len(phone) >= 5 else phone

    return {
        "id": user.id,
        "farmer_id": user.farmer_id,
        "full_name": user.full_name,
        "masked_phone": masked_phone,
        "profile_image": user.profile_image,
        "upi_id": f"{(user.farmer_id or '').lower()}@farmassist",
    }


def _txn_to_dict(txn: WalletTransaction, db: Optional[Session] = None) -> dict:
    data = {
        "transaction_id": txn.transaction_id,
        "transaction_type": txn.transaction_type,
        "amount": round(float(txn.amount or 0), 2),
        "balance_after": round(float(txn.balance_after or 0), 2),
        "description": txn.description,
        "reference_id": txn.reference_id,
        "payment_method": txn.payment_method or "wallet",
        "status": txn.status or "completed",
        "created_at": str(txn.created_at) if txn.created_at else None,
        "recipient_user_id": txn.recipient_user_id,
    }

    if db and txn.recipient_user_id:
        recipient = db.query(User).filter(User.id == txn.recipient_user_id).first()
        if recipient:
            data["counterparty_name"] = recipient.full_name
            data["counterparty_farmer_id"] = recipient.farmer_id
            data["counterparty_avatar"] = recipient.profile_image

    if db and txn.user_id and not data.get("counterparty_name"):
        sender = db.query(User).filter(User.id == txn.user_id).first()
        if sender:
            data["sender_name"] = sender.full_name
            data["sender_farmer_id"] = sender.farmer_id

    return data


def _beneficiary_to_dict(ben: WalletBeneficiary) -> dict:
    return {
        "beneficiary_id": ben.id,
        "beneficiary_name": ben.beneficiary_name,
        "beneficiary_farmer_id": ben.beneficiary_farmer_id,
        "beneficiary_upi": ben.beneficiary_upi,
        "beneficiary_phone": ben.beneficiary_phone,
        "beneficiary_user_id": ben.beneficiary_user_id,
        "created_at": str(ben.created_at) if ben.created_at else None,
    }


def _generate_reference() -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choices(string.digits, k=6))
    return f"WREF-{stamp}-{suffix}"


def _period_bounds(period, start_date, end_date):
    """Return (start, end) datetimes for a financial period. Either may be None."""
    now = datetime.utcnow()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == "custom":
        start = None
        end = None
        if start_date:
            try:
                start = datetime.fromisoformat(start_date)
            except ValueError:
                start = None
        if end_date:
            try:
                end = datetime.fromisoformat(end_date)
            except ValueError:
                end = None
        return start, end
    return None, None


def _apply_period(query, date_col, created_col, start, end):
    if start:
        query = query.filter(func.coalesce(date_col, created_col) >= start)
    if end:
        query = query.filter(func.coalesce(date_col, created_col) <= end)
    return query


def _resolve_recipient_user(db: Session, query_str: str) -> Optional[User]:
    q = (query_str or "").strip()
    if not q:
        return None

    # 1. Exact or normalized Farmer ID
    normalized_fid = normalize_farmer_id(q)
    if normalized_fid:
        user = db.query(User).filter(User.farmer_id == normalized_fid, User.is_active == True).first()
        if user:
            return user

    # 2. Check if UPI ID format: FA-AS-00000002@farmassist or similar
    if "@" in q:
        upi_part = q.split("@")[0].strip()
        normalized_upi = normalize_farmer_id(upi_part)
        if normalized_upi:
            user = db.query(User).filter(User.farmer_id == normalized_upi, User.is_active == True).first()
            if user:
                return user

    # 3. Clean numeric digits for phone search
    digits = re.sub(r"\D", "", q)
    if len(digits) >= 10:
        phone_10 = digits[-10:]
        user = db.query(User).filter(
            or_(
                User.phone_number == phone_10,
                User.phone_number == f"+91{phone_10}",
                User.phone_number == f"+91 {phone_10}",
                User.phone_number.like(f"%{phone_10}"),
            ),
            User.is_active == True,
        ).first()
        if user:
            return user

    # 4. User ID direct lookup
    user = db.query(User).filter(User.id == q, User.is_active == True).first()
    if user:
        return user

    # 5. Direct Farmer ID lookup (case-insensitive)
    user = db.query(User).filter(User.farmer_id.ilike(q), User.is_active == True).first()
    return user


# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/wallet")
def get_my_wallet(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = _ensure_wallet(db, current_user)
    return {"status": "success", "data": _wallet_to_dict(wallet)}


@router.post("/wallet/setup")
def setup_wallet(
    payload: WalletSetupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = _ensure_wallet(db, current_user)
    pin = (payload.wallet_pin or "").strip()
    confirm = (payload.confirm_pin or "").strip()

    if not pin.isdigit() or not (4 <= len(pin) <= 6):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wallet PIN must be 4-6 digits",
        )
    if pin != confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN and confirm PIN do not match",
        )

    wallet.wallet_pin_hash = hash_password(pin)
    wallet.is_setup_complete = True
    db.commit()
    db.refresh(wallet)

    return {
        "status": "success",
        "message": "Wallet PIN set successfully",
        "data": _wallet_to_dict(wallet),
    }


@router.post("/wallet/verify-pin")
def verify_wallet_pin(
    payload: VerifyPinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = _get_wallet(db, current_user.id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )
    if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wallet PIN has not been set up yet",
        )
    verified = verify_password((payload.wallet_pin or "").strip(), wallet.wallet_pin_hash)
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid wallet PIN",
        )
    return {"status": "success", "data": {"verified": True}}


@router.get("/wallet/summary")
def wallet_summary(
    period: Optional[str] = Query(None, pattern="^(today|week|month|year|custom)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = _ensure_wallet(db, current_user)

    total_credits = float(
        db.query(func.coalesce(func.sum(WalletTransaction.amount), 0.0))
        .filter(
            WalletTransaction.user_id == current_user.id,
            WalletTransaction.transaction_type == "credit",
            WalletTransaction.status == "completed",
        )
        .scalar()
        or 0
    )
    total_debits = float(
        db.query(func.coalesce(func.sum(WalletTransaction.amount), 0.0))
        .filter(
            WalletTransaction.user_id == current_user.id,
            WalletTransaction.transaction_type == "debit",
            WalletTransaction.status == "completed",
        )
        .scalar()
        or 0
    )
    wallet_txn_count = (
        db.query(func.count(WalletTransaction.id))
        .filter(WalletTransaction.user_id == current_user.id)
        .scalar()
        or 0
    )
    recent = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.user_id == current_user.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(10)
        .all()
    )

    start, end = _period_bounds(period, start_date, end_date)

    income_q = db.query(func.coalesce(func.sum(Income.amount), 0.0)).filter(
        Income.user_id == current_user.id
    )
    expense_q = db.query(func.coalesce(func.sum(Expense.amount), 0.0)).filter(
        Expense.user_id == current_user.id
    )
    income_count_q = db.query(func.count(Income.id)).filter(Income.user_id == current_user.id)
    expense_count_q = db.query(func.count(Expense.id)).filter(Expense.user_id == current_user.id)
    if start or end:
        income_q = _apply_period(income_q, Income.income_date, Income.created_at, start, end)
        expense_q = _apply_period(expense_q, Expense.expense_date, Expense.created_at, start, end)
        income_count_q = _apply_period(income_count_q, Income.income_date, Income.created_at, start, end)
        expense_count_q = _apply_period(expense_count_q, Expense.expense_date, Expense.created_at, start, end)

    total_income = round(float(income_q.scalar() or 0), 2)
    total_expenses = round(float(expense_q.scalar() or 0), 2)

    income_rows = (
        db.query(Income.category, func.coalesce(func.sum(Income.amount), 0.0))
        .filter(Income.user_id == current_user.id)
        .group_by(Income.category)
        .all()
    )
    if start or end:
        income_rows = _apply_period(
            db.query(Income.category, func.coalesce(func.sum(Income.amount), 0.0))
            .filter(Income.user_id == current_user.id)
            .group_by(Income.category),
            Income.income_date,
            Income.created_at,
            start,
            end,
        ).all()

    expense_rows = (
        db.query(Expense.category, func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.user_id == current_user.id)
        .group_by(Expense.category)
        .all()
    )
    if start or end:
        expense_rows = _apply_period(
            db.query(Expense.category, func.coalesce(func.sum(Expense.amount), 0.0))
            .filter(Expense.user_id == current_user.id)
            .group_by(Expense.category),
            Expense.expense_date,
            Expense.created_at,
            start,
            end,
        ).all()

    income_by_category = [{"category": r[0], "amount": round(float(r[1]), 2)} for r in income_rows]
    expense_by_category = [{"category": r[0], "amount": round(float(r[1]), 2)} for r in expense_rows]

    now = datetime.utcnow()
    month_keys = []
    y, m = now.year, now.month
    for _ in range(12):
        month_keys.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_keys.reverse()

    month_inc_rows = db.query(
        func.strftime("%Y-%m", func.coalesce(Income.income_date, Income.created_at)),
        func.coalesce(func.sum(Income.amount), 0.0),
    ).filter(Income.user_id == current_user.id)
    month_exp_rows = db.query(
        func.strftime("%Y-%m", func.coalesce(Expense.expense_date, Expense.created_at)),
        func.coalesce(func.sum(Expense.amount), 0.0),
    ).filter(Expense.user_id == current_user.id)
    # The cash-flow trend always spans the last 12 months, independent of the
    # selected finance period, so charts show a useful long-range picture.
    month_inc_rows = _apply_period(
        month_inc_rows,
        Income.income_date,
        Income.created_at,
        now - timedelta(days=365),
        None,
    ).group_by(func.strftime("%Y-%m", func.coalesce(Income.income_date, Income.created_at))).all()
    month_exp_rows = _apply_period(
        month_exp_rows,
        Expense.expense_date,
        Expense.created_at,
        now - timedelta(days=365),
        None,
    ).group_by(func.strftime("%Y-%m", func.coalesce(Expense.expense_date, Expense.created_at))).all()

    month_inc_map = {r[0]: round(float(r[1]), 2) for r in month_inc_rows}
    month_exp_map = {r[0]: round(float(r[1]), 2) for r in month_exp_rows}
    monthly_cashflow = []
    for key in month_keys:
        inc = month_inc_map.get(key, 0.0)
        exp = month_exp_map.get(key, 0.0)
        monthly_cashflow.append({
            "month": key,
            "income": inc,
            "expenses": exp,
            "net": round(inc - exp, 2),
        })

    data = _wallet_to_dict(wallet)
    data.update(
        {
            "period": period or "all",
            "period_start": str(start) if start else None,
            "period_end": str(end) if end else None,
            "total_credits": round(total_credits, 2),
            "total_debits": round(total_debits, 2),
            "wallet_transactions_count": wallet_txn_count,
            "recent_transactions": [_txn_to_dict(t, db) for t in recent],
            "income": {
                "total": total_income,
                "count": int(income_count_q.scalar() or 0),
                "by_category": income_by_category,
            },
            "expenses": {
                "total": total_expenses,
                "count": int(expense_count_q.scalar() or 0),
                "by_category": expense_by_category,
            },
            "net_profit": round(total_income - total_expenses, 2),
            "monthly_cashflow": monthly_cashflow,
        }
    )
    return {"status": "success", "data": data}


@router.post("/wallet/add-money")
def add_money(
    payload: AddMoneyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero",
        )

    # Enforce deposit caps
    max_single = getattr(settings, "WALLET_MAX_SINGLE_DEPOSIT", 50000.0)
    if amount > max_single:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Single deposit limited to ₹{max_single:,.2f}",
        )
    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_deposits = (
        db.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .filter(
            WalletTransaction.user_id == current_user.id,
            WalletTransaction.transaction_type == "credit",
            WalletTransaction.status == "completed",
            WalletTransaction.created_at >= day_start,
        )
        .scalar()
    ) or 0
    max_daily = getattr(settings, "WALLET_MAX_DAILY_DEPOSITS", 100000.0)
    if float(today_deposits) + amount > max_daily:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Daily deposit limit of ₹{max_daily:,.2f} reached",
        )

    wallet = _ensure_wallet(db, current_user)
    if not wallet.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wallet is inactive",
        )
    if not wallet.is_setup_complete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete wallet setup before adding money",
        )

    new_balance = round(float(wallet.balance or 0) + amount, 2)

    idem_key = (payload.idempotency_key or "").strip()
    if idem_key:
        existing = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == current_user.id,
                WalletTransaction.reference_id == idem_key,
                WalletTransaction.transaction_type == "credit",
                WalletTransaction.status == "completed",
            )
            .first()
        )
        if existing:
            return {
                "status": "success",
                "message": f"₹{amount:,.2f} added to wallet successfully",
                "data": {
                    "wallet": _wallet_to_dict(wallet),
                    "transaction": _txn_to_dict(existing, db),
                    "idempotent": True,
                },
            }

    reference_id = idem_key or _generate_reference()
    method_name = (payload.payment_method or "bank_transfer").replace("_", " ").title()
    txn = WalletTransaction(
        transaction_id=generate_id("FA-WTX", db, WalletTransaction),
        wallet_id=wallet.id,
        user_id=current_user.id,
        transaction_type="credit",
        amount=amount,
        balance_after=new_balance,
        description=payload.note or f"Added money via {method_name}",
        reference_id=reference_id,
        payment_method=payload.payment_method,
        status="completed",
    )
    wallet.balance = new_balance
    db.add(txn)
    db.commit()
    db.refresh(txn)
    db.refresh(wallet)

    # Event-driven notification for a confirmed credit transaction.
    try:
        notif_id = generate_id("FA-NOT", db, Notification)
        db.add(Notification(
            notification_id=notif_id,
            user_id=current_user.id,
            title="Money Added",
            message=(
                f"₹{amount:,.2f} has been added to your wallet. "
                f"New balance: ₹{new_balance:,.2f}. Ref: {reference_id}"
            ),
            notification_type="wallet",
            reference_id=txn.transaction_id,
            reference_type="transaction",
            icon="fa-wallet",
            action_url="wallet.html",
            is_read=False,
        ))
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "success",
        "message": f"₹{amount:,.2f} added to wallet successfully",
        "data": {
            "wallet": _wallet_to_dict(wallet),
            "transaction": _txn_to_dict(txn, db),
        },
    }


@router.post("/wallet/transfer")
def transfer_money(
    payload: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero",
        )

    wallet = _get_wallet(db, current_user.id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )
    if not wallet.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wallet is inactive",
        )
    if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete wallet setup before transferring money",
        )

    # Verify PIN
    if not verify_password((payload.wallet_pin or "").strip(), wallet.wallet_pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid wallet PIN",
        )

    # Check recipient
    recipient_user = _resolve_recipient_user(db, payload.recipient_id)
    if not recipient_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found",
        )

    if recipient_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer money to your own wallet",
        )

    idem_key = (payload.idempotency_key or "").strip()
    if idem_key:
        existing = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == current_user.id,
                WalletTransaction.reference_id == idem_key,
                WalletTransaction.transaction_type == "debit",
                WalletTransaction.status == "completed",
            )
            .first()
        )
        if existing:
            return {
                "status": "success",
                "message": f"Successfully sent ₹{amount:,.2f} to {recipient_user.full_name}",
                "data": {
                    "wallet": _wallet_to_dict(wallet),
                    "transaction": _txn_to_dict(existing, db),
                    "recipient": _user_safe_info(recipient_user),
                    "idempotent": True,
                },
            }

    # Check balance
    current_balance = round(float(wallet.balance or 0), 2)
    if current_balance < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient wallet balance",
        )

    recipient_wallet = _ensure_wallet(db, recipient_user)
    if not recipient_wallet.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipient wallet is inactive",
        )

    try:
        sender_new_balance = round(current_balance - amount, 2)
        recipient_new_balance = round(float(recipient_wallet.balance or 0) + amount, 2)
        reference_id = idem_key or _generate_reference()

        sender_desc = payload.note or f"Transfer to {recipient_user.full_name} ({recipient_user.farmer_id})"
        recipient_desc = payload.note or f"Received from {current_user.full_name} ({current_user.farmer_id})"

        debit_txn = WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=wallet.id,
            user_id=current_user.id,
            recipient_wallet_id=recipient_wallet.id,
            recipient_user_id=recipient_user.id,
            transaction_type="debit",
            amount=amount,
            balance_after=sender_new_balance,
            description=sender_desc,
            reference_id=reference_id,
            payment_method="wallet_transfer",
            status="completed",
        )
        db.add(debit_txn)
        db.flush()

        credit_txn = WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=recipient_wallet.id,
            user_id=recipient_user.id,
            recipient_wallet_id=wallet.id,
            recipient_user_id=current_user.id,
            transaction_type="credit",
            amount=amount,
            balance_after=recipient_new_balance,
            description=recipient_desc,
            reference_id=reference_id,
            payment_method="wallet_transfer",
            status="completed",
        )
        db.add(credit_txn)

        # Notify both parties as part of the same atomic transaction.
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Money Sent",
            message=(
                f"₹{amount:,.2f} sent to {recipient_user.full_name} "
                f"({recipient_user.farmer_id}). "
                f"New balance: ₹{sender_new_balance:,.2f}. Ref: {reference_id}"
            ),
            notification_type="wallet",
            reference_id=debit_txn.transaction_id,
            reference_type="transaction",
            icon="fa-wallet",
            action_url="wallet.html",
        )
        # Flush so generate_id for the second notification sees the first one
        # (IDs are assigned from the DB, and both must stay unique).
        db.flush()
        create_notification(
            db=db,
            user_id=recipient_user.id,
            title="Money Received",
            message=(
                f"₹{amount:,.2f} received from {current_user.full_name} "
                f"({current_user.farmer_id}). "
                f"New balance: ₹{recipient_new_balance:,.2f}. Ref: {reference_id}"
            ),
            notification_type="wallet",
            reference_id=credit_txn.transaction_id,
            reference_type="transaction",
            icon="fa-wallet",
            action_url="wallet.html",
        )

        wallet.balance = sender_new_balance
        recipient_wallet.balance = recipient_new_balance
        db.commit()
        db.refresh(debit_txn)
        db.refresh(credit_txn)
        db.refresh(wallet)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transfer failed, please try again",
        )

    return {
        "status": "success",
        "message": f"Successfully sent ₹{amount:,.2f} to {recipient_user.full_name}",
        "data": {
            "wallet": _wallet_to_dict(wallet),
            "transaction": _txn_to_dict(debit_txn, db),
            "recipient_transaction": _txn_to_dict(credit_txn, db),
            "recipient": _user_safe_info(recipient_user),
        },
    }


@router.get("/wallet/transactions")
def list_wallet_transactions(
    type: Optional[str] = Query(None, pattern="^(credit|debit)$"),
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(WalletTransaction).filter(
        WalletTransaction.user_id == current_user.id
    )
    if type:
        query = query.filter(WalletTransaction.transaction_type == type)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                WalletTransaction.description.ilike(term),
                WalletTransaction.reference_id.ilike(term),
                WalletTransaction.transaction_id.ilike(term),
            )
        )

    total = query.count()
    txns = (
        query.order_by(WalletTransaction.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": total,
            "limit": limit,
            "items": [_txn_to_dict(t, db) for t in txns],
        },
    }


@router.get("/wallet/transactions/{transaction_id}")
def get_wallet_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn = (
        db.query(WalletTransaction)
        .filter(
            WalletTransaction.transaction_id == transaction_id,
            WalletTransaction.user_id == current_user.id,
        )
        .first()
    )
    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    return {"status": "success", "data": _txn_to_dict(txn, db)}


@router.get("/wallet/beneficiaries")
def list_beneficiaries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    beneficiaries = (
        db.query(WalletBeneficiary)
        .filter(WalletBeneficiary.user_id == current_user.id)
        .order_by(WalletBeneficiary.created_at.desc())
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": len(beneficiaries),
            "items": [_beneficiary_to_dict(b) for b in beneficiaries],
        },
    }


@router.post("/wallet/beneficiaries")
def add_beneficiary(
    payload: BeneficiaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = (payload.beneficiary_name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Beneficiary name is required",
        )

    beneficiary_user_id = None
    stored_farmer_id = None
    if payload.beneficiary_farmer_id:
        normalized = normalize_farmer_id(payload.beneficiary_farmer_id)
        existing_user = (
            db.query(User).filter(User.farmer_id == normalized).first()
        )
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No farmer found with the given farmer ID",
            )
        beneficiary_user_id = existing_user.id
        stored_farmer_id = normalized

    beneficiary = WalletBeneficiary(
        user_id=current_user.id,
        beneficiary_user_id=beneficiary_user_id,
        beneficiary_name=name,
        beneficiary_farmer_id=stored_farmer_id,
        beneficiary_upi=payload.beneficiary_upi,
        beneficiary_phone=payload.beneficiary_phone,
    )
    db.add(beneficiary)
    db.commit()
    db.refresh(beneficiary)

    return {
        "status": "success",
        "message": "Beneficiary added successfully",
        "data": _beneficiary_to_dict(beneficiary),
    }


@router.delete("/wallet/beneficiaries/{beneficiary_id}")
def delete_beneficiary(
    beneficiary_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    beneficiary = (
        db.query(WalletBeneficiary)
        .filter(
            WalletBeneficiary.id == beneficiary_id,
            WalletBeneficiary.user_id == current_user.id,
        )
        .first()
    )
    if not beneficiary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Beneficiary not found",
        )
    db.delete(beneficiary)
    db.commit()
    return {
        "status": "success",
        "message": "Beneficiary deleted successfully",
        "data": {"beneficiary_id": beneficiary_id},
    }


@router.post("/wallet/search-user")
def search_recipient(
    payload: SearchUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query is required")

    user = _resolve_recipient_user(db, query)

    if not user:
        return {
            "status": "success",
            "data": {
                "found": False,
                "message": "No Farm Assist account found with this information.",
            },
        }

    if user.id == current_user.id:
        return {
            "status": "success",
            "data": {
                "found": False,
                "is_self": True,
                "message": "You cannot send money to your own wallet.",
            },
        }

    return {"status": "success", "data": {"found": True, "user": _user_safe_info(user)}}


@router.get("/wallet/money-requests")
def list_money_requests(
    type: Optional[str] = Query(None, pattern="^(sent|received)$"),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(MoneyRequest)
    if type == "sent":
        q = q.filter(MoneyRequest.receiver_user_id == current_user.id)
    elif type == "received":
        q = q.filter(MoneyRequest.sender_user_id == current_user.id)
    else:
        q = q.filter(
            (MoneyRequest.sender_user_id == current_user.id) |
            (MoneyRequest.receiver_user_id == current_user.id)
        )
    if status_filter:
        q = q.filter(MoneyRequest.status == status_filter)
    total = q.count()
    items = q.order_by(MoneyRequest.created_at.desc()).limit(limit).all()
    return {
        "status": "success",
        "data": {
            "total": total,
            "items": [_money_request_to_dict(r, db) for r in items],
        },
    }


def _money_request_to_dict(req: MoneyRequest, db: Optional[Session] = None) -> dict:
    data = {
        "request_id": req.request_id,
        "sender_user_id": req.sender_user_id,
        "receiver_user_id": req.receiver_user_id,
        "sender_farmer_id": req.sender_farmer_id,
        "receiver_farmer_id": req.receiver_farmer_id,
        "amount": round(float(req.amount or 0), 2),
        "note": req.note,
        "status": req.status,
        "reference_id": req.reference_id,
        "created_at": str(req.created_at) if req.created_at else None,
        "updated_at": str(req.updated_at) if req.updated_at else None,
    }

    if db:
        # Load sender and receiver info
        sender = db.query(User).filter(User.id == req.sender_user_id).first()
        receiver = db.query(User).filter(User.id == req.receiver_user_id).first()
        if sender:
            data["sender_name"] = sender.full_name
        if receiver:
            data["receiver_name"] = receiver.full_name

    return data


@router.post("/wallet/money-requests")
def create_money_request(
    payload: MoneyRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    recipient = _resolve_recipient_user(db, payload.recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    if recipient.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot request money from yourself")

    reference_id = _generate_reference()
    req = MoneyRequest(
        request_id=generate_id("FA-MRQ", db, MoneyRequest),
        sender_user_id=recipient.id,
        receiver_user_id=current_user.id,
        sender_farmer_id=recipient.farmer_id,
        receiver_farmer_id=current_user.farmer_id,
        amount=amount,
        note=payload.note,
        status="pending",
        reference_id=reference_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Notify recipient about the money request
    try:
        create_notification(
            db=db,
            user_id=recipient.id,
            title="Money Request Received",
            message=(
                f"{current_user.full_name} ({current_user.farmer_id}) has requested ₹{amount:,.2f} from you. "
                f"Note: {payload.note or 'No note provided'}. Ref: {reference_id}"
            ),
            notification_type="wallet",
            reference_id=req.request_id,
            reference_type="money_request",
            icon="fa-hand-holding-dollar",
            action_url="wallet.html",
        )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "success",
        "message": f"Money request of ₹{amount:,.2f} sent to {recipient.full_name}",
        "data": _money_request_to_dict(req),
    }


@router.post("/wallet/money-requests/{request_id}/accept")
def accept_money_request(
    request_id: str,
    payload: VerifyPinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(MoneyRequest).filter(
        MoneyRequest.request_id == request_id,
        MoneyRequest.sender_user_id == current_user.id,
        MoneyRequest.status == "pending",
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    wallet = _get_wallet(db, current_user.id)
    if not wallet or not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(status_code=403, detail="Complete wallet setup first")
    if not verify_password((payload.wallet_pin or "").strip(), wallet.wallet_pin_hash):
        raise HTTPException(status_code=401, detail="Invalid wallet PIN")

    amount = round(float(req.amount or 0), 2)
    current_balance = round(float(wallet.balance or 0), 2)
    if current_balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    receiver_user = db.query(User).filter(User.id == req.receiver_user_id).first()
    if not receiver_user:
        raise HTTPException(status_code=404, detail="Request creator not found")
    receiver_wallet = _ensure_wallet(db, receiver_user)

    try:
        sender_new = round(current_balance - amount, 2)
        receiver_new = round(float(receiver_wallet.balance or 0) + amount, 2)
        ref = _generate_reference()

        debit_txn = WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=wallet.id,
            user_id=current_user.id,
            recipient_wallet_id=receiver_wallet.id,
            recipient_user_id=receiver_user.id,
            transaction_type="debit",
            amount=amount,
            balance_after=sender_new,
            description=req.note or f"Money request accepted for {receiver_user.full_name}",
            reference_id=ref,
            payment_method="wallet_transfer",
            status="completed",
        )
        db.add(debit_txn)
        db.flush()

        credit_txn = WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=receiver_wallet.id,
            user_id=receiver_user.id,
            recipient_wallet_id=wallet.id,
            recipient_user_id=current_user.id,
            transaction_type="credit",
            amount=amount,
            balance_after=receiver_new,
            description=req.note or f"Money received from {current_user.full_name}",
            reference_id=ref,
            payment_method="wallet_transfer",
            status="completed",
        )
        db.add(credit_txn)
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Money Sent",
            message=(
                f"₹{amount:,.2f} paid to {receiver_user.full_name} "
                f"({receiver_user.farmer_id}) towards a money request. "
                f"New balance: ₹{sender_new:,.2f}. Ref: {ref}"
            ),
            notification_type="wallet",
            reference_id=debit_txn.transaction_id,
            reference_type="transaction",
            icon="fa-wallet",
            action_url="wallet.html",
        )
        db.flush()
        create_notification(
            db=db,
            user_id=receiver_user.id,
            title="Money Received",
            message=(
                f"₹{amount:,.2f} received from {current_user.full_name} "
                f"({current_user.farmer_id}) towards a money request. "
                f"New balance: ₹{receiver_new:,.2f}. Ref: {ref}"
            ),
            notification_type="wallet",
            reference_id=credit_txn.transaction_id,
            reference_type="transaction",
            icon="fa-wallet",
            action_url="wallet.html",
        )
        wallet.balance = sender_new
        receiver_wallet.balance = receiver_new
        req.status = "completed"
        db.commit()
        db.refresh(wallet)
        db.refresh(debit_txn)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaction failed")

    return {
        "status": "success",
        "message": f"Payment of ₹{amount:,.2f} completed",
        "data": {"wallet": _wallet_to_dict(wallet), "transaction": _txn_to_dict(debit_txn, db)},
    }


@router.post("/wallet/money-requests/{request_id}/decline")
def decline_money_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(MoneyRequest).filter(
        MoneyRequest.request_id == request_id,
        MoneyRequest.sender_user_id == current_user.id,
        MoneyRequest.status == "pending",
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = "declined"
    db.commit()

    # Notify the request creator that their request was declined
    try:
        create_notification(
            db=db,
            user_id=req.receiver_user_id,
            title="Money Request Declined",
            message=(
                f"Your money request of ₹{req.amount:,.2f} to {current_user.full_name} ({current_user.farmer_id}) has been declined."
            ),
            notification_type="wallet",
            reference_id=req.request_id,
            reference_type="money_request",
            icon="fa-hand-holding-dollar",
            action_url="wallet.html",
        )
        db.commit()
    except Exception:
        db.rollback()

    return {"status": "success", "message": "Request declined"}


@router.post("/wallet/money-requests/{request_id}/cancel")
def cancel_money_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(MoneyRequest).filter(
        MoneyRequest.request_id == request_id,
        MoneyRequest.receiver_user_id == current_user.id,
        MoneyRequest.status == "pending",
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = "cancelled"
    db.commit()
    return {"status": "success", "message": "Request cancelled"}


def _bank_account_to_dict(acc: BankAccount) -> dict:
    return {
        "account_id": acc.account_id,
        "bank_name": acc.bank_name,
        "account_holder_name": acc.account_holder_name,
        "masked_account_number": acc.masked_account_number,
        "ifsc_code": acc.ifsc_code,
        "account_type": acc.account_type,
        "verification_status": acc.verification_status,
        "is_primary": bool(acc.is_primary),
        "is_active": bool(acc.is_active),
        "created_at": str(acc.created_at) if acc.created_at else None,
    }


@router.get("/wallet/bank-accounts")
def list_bank_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accounts = db.query(BankAccount).filter(
        BankAccount.user_id == current_user.id,
        BankAccount.is_active == True,
    ).order_by(BankAccount.created_at.desc()).all()
    return {
        "status": "success",
        "data": {
            "total": len(accounts),
            "items": [_bank_account_to_dict(a) for a in accounts],
        },
    }


@router.post("/wallet/bank-accounts")
def add_bank_account(
    payload: BankAccountAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc_num = (payload.account_number or "").strip()
    if len(acc_num) < 8 or not acc_num.isdigit():
        raise HTTPException(status_code=400, detail="Invalid account number (must be digits)")
    masked = "XXXX XXXX " + acc_num[-4:]

    ifsc = (payload.ifsc_code or "").strip().upper()
    if len(ifsc) < 4:
        raise HTTPException(status_code=400, detail="Invalid IFSC code")

    holder = (payload.account_holder_name or "").strip()
    if not holder:
        raise HTTPException(status_code=400, detail="Account holder name is required")

    bank = (payload.bank_name or "").strip()
    if not bank:
        raise HTTPException(status_code=400, detail="Bank name is required")

    existing = db.query(BankAccount).filter(
        BankAccount.user_id == current_user.id,
        BankAccount.masked_account_number == masked,
        BankAccount.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This bank account is already linked")

    existing_count = db.query(BankAccount).filter(
        BankAccount.user_id == current_user.id,
        BankAccount.is_active == True,
    ).count()

    acc = BankAccount(
        account_id=generate_id("FA-BNK", db, BankAccount),
        user_id=current_user.id,
        bank_name=bank,
        account_holder_name=holder,
        masked_account_number=masked,
        ifsc_code=ifsc,
        account_type=payload.account_type or "savings",
        verification_status="verified",
        is_primary=existing_count == 0,
        is_active=True,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)

    try:
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Bank Account Linked",
            message=f"{bank} account ending {acc_num[-4:]} linked to your Digital Wallet.",
            notification_type="wallet",
            reference_id=acc.account_id,
            reference_type="bank_account",
            icon="fa-wallet",
            action_url="wallet.html",
        )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "success",
        "message": "Bank account linked successfully",
        "data": _bank_account_to_dict(acc),
    }


@router.post("/wallet/bank-accounts/{account_id}/default")
def set_default_bank_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = db.query(BankAccount).filter(
        BankAccount.account_id == account_id,
        BankAccount.user_id == current_user.id,
        BankAccount.is_active == True,
    ).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Bank account not found")

    db.query(BankAccount).filter(
        BankAccount.user_id == current_user.id,
        BankAccount.is_active == True,
    ).update({BankAccount.is_primary: False})
    acc.is_primary = True
    db.commit()
    db.refresh(acc)
    return {
        "status": "success",
        "message": "Default bank account updated",
        "data": _bank_account_to_dict(acc),
    }


@router.delete("/wallet/bank-accounts/{account_id}")
def remove_bank_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = db.query(BankAccount).filter(
        BankAccount.account_id == account_id,
        BankAccount.user_id == current_user.id,
        BankAccount.is_active == True,
    ).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Bank account not found")
    acc.is_active = False
    db.commit()

    try:
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Bank Account Unlinked",
            message=f"{acc.bank_name} account {acc.masked_account_number} removed from your Digital Wallet.",
            notification_type="wallet",
            reference_id=acc.account_id,
            reference_type="bank_account",
            icon="fa-wallet",
            action_url="wallet.html",
        )
        db.commit()
    except Exception:
        db.rollback()

    return {"status": "success", "message": "Bank account unlinked successfully"}


@router.post("/wallet/change-pin")
def change_wallet_pin(
    payload: ChangePinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = _get_wallet(db, current_user.id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(status_code=400, detail="Wallet PIN not set up yet")
    if not verify_password((payload.current_pin or "").strip(), wallet.wallet_pin_hash):
        raise HTTPException(status_code=401, detail="Current PIN is incorrect")

    new_pin = (payload.new_pin or "").strip()
    if not new_pin.isdigit() or not (4 <= len(new_pin) <= 6):
        raise HTTPException(status_code=400, detail="New PIN must be 4-6 digits")
    if new_pin != (payload.confirm_pin or "").strip():
        raise HTTPException(status_code=400, detail="New PIN and confirm PIN do not match")

    wallet.wallet_pin_hash = hash_password(new_pin)
    db.commit()
    return {"status": "success", "message": "Wallet PIN updated successfully"}


@router.get("/wallet/security-info")
def wallet_security_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = _get_wallet(db, current_user.id)
    recent_count = 0
    if wallet:
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_count = db.query(WalletTransaction).filter(
            WalletTransaction.user_id == current_user.id,
            WalletTransaction.created_at >= cutoff,
        ).count()

    return {
        "status": "success",
        "data": {
            "pin_set": bool(wallet and wallet.is_setup_complete and wallet.wallet_pin_hash),
            "wallet_active": bool(wallet and wallet.is_active),
            "last_30_days_activity": recent_count,
            "upi_id": wallet.upi_id if wallet else None,
            "farmer_id": current_user.farmer_id,
        },
    }


@router.post("/wallet/withdraw")
def withdraw_money(
    payload: WithdrawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero",
        )

    wallet = _get_wallet(db, current_user.id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )
    if not wallet.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wallet is inactive",
        )
    if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete wallet setup before withdrawing money",
        )

    # Verify PIN
    if not verify_password((payload.wallet_pin or "").strip(), wallet.wallet_pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid wallet PIN",
        )

    # Check bank account
    bank_account = db.query(BankAccount).filter(
        BankAccount.account_id == payload.bank_account_id,
        BankAccount.user_id == current_user.id,
        BankAccount.is_active == True,
    ).first()
    if not bank_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank account not found",
        )

    # Check balance
    current_balance = round(float(wallet.balance or 0), 2)
    if current_balance < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient wallet balance",
        )

    # Idempotency check
    idem_key = (payload.idempotency_key or "").strip()
    if idem_key:
        existing = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == current_user.id,
                WalletTransaction.reference_id == idem_key,
                WalletTransaction.transaction_type == "debit",
                WalletTransaction.status == "completed",
            )
            .first()
        )
        if existing:
            return {
                "status": "success",
                "message": f"₹{amount:,.2f} withdrawal request processed successfully",
                "data": {
                    "wallet": _wallet_to_dict(wallet),
                    "transaction": _txn_to_dict(existing, db),
                    "idempotent": True,
                },
            }

    try:
        new_balance = round(current_balance - amount, 2)
        reference_id = idem_key or _generate_reference()

        # Create withdrawal transaction
        txn = WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=wallet.id,
            user_id=current_user.id,
            transaction_type="debit",
            amount=amount,
            balance_after=new_balance,
            description=f"Withdrawal to {bank_account.bank_name} account {bank_account.masked_account_number}",
            reference_id=reference_id,
            payment_method="bank_withdrawal",
            status="completed",
        )
        db.add(txn)
        
        # Update wallet balance
        wallet.balance = new_balance
        
        # Create notification
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Money Withdrawn",
            message=(
                f"₹{amount:,.2f} has been withdrawn from your wallet to {bank_account.bank_name} account. "
                f"New balance: ₹{new_balance:,.2f}. Ref: {reference_id}"
            ),
            notification_type="wallet",
            reference_id=txn.transaction_id,
            reference_type="transaction",
            icon="fa-wallet",
            action_url="wallet.html",
        )
        
        db.commit()
        db.refresh(txn)
        db.refresh(wallet)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Withdrawal failed, please try again",
        )

    return {
        "status": "success",
        "message": f"₹{amount:,.2f} withdrawn successfully",
        "data": {
            "wallet": _wallet_to_dict(wallet),
            "transaction": _txn_to_dict(txn, db),
            "bank_account": _bank_account_to_dict(bank_account),
        },
    }
