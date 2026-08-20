from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.finance import Transaction, Expense, Income

router = APIRouter(prefix="/api/v1", tags=["Finance"])


class TransactionCreate(BaseModel):
    type: str
    category: str
    amount: float = Field(gt=0)
    description: Optional[str] = None
    payment_method: Optional[str] = None
    farm_id: Optional[str] = None
    reference_id: Optional[str] = None
    transaction_date: Optional[str] = None


class ExpenseCreate(BaseModel):
    category: str
    amount: float = Field(gt=0)
    subcategory: Optional[str] = None
    description: Optional[str] = None
    vendor: Optional[str] = None
    payment_method: Optional[str] = None
    farm_id: Optional[str] = None
    receipt_url: Optional[str] = None
    expense_date: Optional[str] = None


class IncomeCreate(BaseModel):
    category: str
    amount: float = Field(gt=0)
    source: Optional[str] = None
    description: Optional[str] = None
    buyer: Optional[str] = None
    payment_method: Optional[str] = None
    farm_id: Optional[str] = None
    income_date: Optional[str] = None


@router.get("/finance/summary")
def get_finance_summary(
    farm_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    income_q = db.query(func.coalesce(func.sum(Income.amount), 0.0)).filter(
        Income.user_id == user_id
    )
    expense_q = db.query(func.coalesce(func.sum(Expense.amount), 0.0)).filter(
        Expense.user_id == user_id
    )
    txn_income_q = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == user_id, Transaction.type == "income"
    )
    txn_expense_q = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == user_id, Transaction.type == "expense"
    )

    if farm_id:
        income_q = income_q.filter(Income.farm_id == farm_id)
        expense_q = expense_q.filter(Expense.farm_id == farm_id)
        txn_income_q = txn_income_q.filter(Transaction.farm_id == farm_id)
        txn_expense_q = txn_expense_q.filter(Transaction.farm_id == farm_id)

    total_income = float(income_q.scalar() or txn_income_q.scalar() or 0)
    total_expenses = float(expense_q.scalar() or txn_expense_q.scalar() or 0)

    month_income = float(
        db.query(func.coalesce(func.sum(Income.amount), 0.0))
        .filter(Income.user_id == user_id, Income.created_at >= start_of_month)
        .scalar()
        or 0
    )
    month_expenses = float(
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.user_id == user_id, Expense.created_at >= start_of_month)
        .scalar()
        or 0
    )

    monthly_data = []
    cur = start_of_month
    for _ in range(12):
        m_start = cur
        if cur == start_of_month:
            m_end = now
        else:
            m_end = (cur + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        m_inc = float(
            db.query(func.coalesce(func.sum(Income.amount), 0.0))
            .filter(Income.user_id == user_id, Income.created_at >= m_start, Income.created_at < m_end)
            .scalar()
            or 0
        )
        m_exp = float(
            db.query(func.coalesce(func.sum(Expense.amount), 0.0))
            .filter(Expense.user_id == user_id, Expense.created_at >= m_start, Expense.created_at < m_end)
            .scalar()
            or 0
        )
        monthly_data.append({
            "month": m_start.strftime("%Y-%m"),
            "income": m_inc,
            "expenses": m_exp,
            "net": m_inc - m_exp,
        })
        cur = (cur - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    category_rows = (
        db.query(Income.category, func.coalesce(func.sum(Income.amount), 0.0))
        .filter(Income.user_id == user_id)
        .group_by(Income.category)
        .all()
    )
    crop_wise = [{"category": r[0], "amount": float(r[1])} for r in category_rows]

    return {
        "status": "success",
        "data": {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_profit": total_income - total_expenses,
            "monthly_income": month_income,
            "monthly_expenses": month_expenses,
            "monthly_net": month_income - month_expenses,
            "monthly_trend": monthly_data,
            "crop_wise": crop_wise,
        },
    }


@router.get("/transactions")
def list_transactions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    farm_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if type:
        q = q.filter(Transaction.type == type)
    if farm_id:
        q = q.filter(Transaction.farm_id == farm_id)
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            q = q.filter(Transaction.created_at >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            q = q.filter(Transaction.created_at <= ed)
        except ValueError:
            pass

    total = q.count()
    items = q.order_by(Transaction.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": t.id,
                    "transaction_id": t.transaction_id,
                    "type": t.type,
                    "category": t.category,
                    "amount": t.amount,
                    "description": t.description,
                    "payment_method": t.payment_method,
                    "farm_id": t.farm_id,
                    "transaction_date": str(t.transaction_date) if t.transaction_date else None,
                    "created_at": str(t.created_at) if t.created_at else None,
                }
                for t in items
            ],
        },
    }


@router.post("/transactions", status_code=201)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn_id = generate_id("FA-TXN", db, Transaction)
    txn_date = None
    if payload.transaction_date:
        try:
            txn_date = datetime.fromisoformat(payload.transaction_date)
        except ValueError:
            txn_date = datetime.utcnow()

    txn = Transaction(
        transaction_id=txn_id,
        user_id=current_user.id,
        farm_id=payload.farm_id,
        type=payload.type,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        payment_method=payload.payment_method,
        reference_id=payload.reference_id,
        transaction_date=txn_date or datetime.utcnow(),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    return {
        "status": "success",
        "data": {
            "id": txn.id,
            "transaction_id": txn.transaction_id,
            "type": txn.type,
            "category": txn.category,
            "amount": txn.amount,
            "description": txn.description,
            "message": "Transaction created successfully",
        },
    }


@router.get("/expenses")
def list_expenses(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    farm_id: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Expense).filter(Expense.user_id == current_user.id)
    if farm_id:
        q = q.filter(Expense.farm_id == farm_id)
    if category:
        q = q.filter(Expense.category == category)

    total = q.count()
    items = q.order_by(Expense.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": e.id,
                    "expense_id": e.expense_id,
                    "category": e.category,
                    "subcategory": e.subcategory,
                    "amount": e.amount,
                    "description": e.description,
                    "vendor": e.vendor,
                    "payment_method": e.payment_method,
                    "farm_id": e.farm_id,
                    "expense_date": str(e.expense_date) if e.expense_date else None,
                    "created_at": str(e.created_at) if e.created_at else None,
                }
                for e in items
            ],
        },
    }


@router.post("/expenses", status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp_id = generate_id("FA-EXP", db, Expense)
    exp_date = None
    if payload.expense_date:
        try:
            exp_date = datetime.fromisoformat(payload.expense_date)
        except ValueError:
            exp_date = datetime.utcnow()

    expense = Expense(
        expense_id=exp_id,
        user_id=current_user.id,
        farm_id=payload.farm_id,
        category=payload.category,
        subcategory=payload.subcategory,
        amount=payload.amount,
        description=payload.description,
        vendor=payload.vendor,
        payment_method=payload.payment_method,
        receipt_url=payload.receipt_url,
        expense_date=exp_date or datetime.utcnow(),
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    return {
        "status": "success",
        "data": {
            "id": expense.id,
            "expense_id": expense.expense_id,
            "category": expense.category,
            "amount": expense.amount,
            "message": "Expense created successfully",
        },
    }


@router.get("/income")
def list_income(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    farm_id: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Income).filter(Income.user_id == current_user.id)
    if farm_id:
        q = q.filter(Income.farm_id == farm_id)
    if category:
        q = q.filter(Income.category == category)

    total = q.count()
    items = q.order_by(Income.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": i.id,
                    "income_id": i.income_id,
                    "category": i.category,
                    "source": i.source,
                    "amount": i.amount,
                    "description": i.description,
                    "buyer": i.buyer,
                    "payment_method": i.payment_method,
                    "farm_id": i.farm_id,
                    "income_date": str(i.income_date) if i.income_date else None,
                    "created_at": str(i.created_at) if i.created_at else None,
                }
                for i in items
            ],
        },
    }


@router.post("/income", status_code=201)
def create_income(
    payload: IncomeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inc_id = generate_id("FA-INC", db, Income)
    inc_date = None
    if payload.income_date:
        try:
            inc_date = datetime.fromisoformat(payload.income_date)
        except ValueError:
            inc_date = datetime.utcnow()

    income = Income(
        income_id=inc_id,
        user_id=current_user.id,
        farm_id=payload.farm_id,
        category=payload.category,
        source=payload.source,
        amount=payload.amount,
        description=payload.description,
        buyer=payload.buyer,
        payment_method=payload.payment_method,
        income_date=inc_date or datetime.utcnow(),
    )
    db.add(income)
    db.commit()
    db.refresh(income)

    return {
        "status": "success",
        "data": {
            "id": income.id,
            "income_id": income.income_id,
            "category": income.category,
            "amount": income.amount,
            "message": "Income record created successfully",
        },
    }


# ------------------------------------------------------------------
# Digital Wallet (additive wallet endpoints backed by the existing
# Transaction model).
# ------------------------------------------------------------------

class WalletAddMoney(BaseModel):
    amount: float = Field(gt=0)
    payment_method: Optional[str] = "UPI"
    description: Optional[str] = None


class WalletTransfer(BaseModel):
    amount: float = Field(gt=0)
    recipient: Optional[str] = None
    recipient_upi: Optional[str] = None
    note: Optional[str] = None
    payment_method: Optional[str] = "UPI"


@router.get("/wallet/summary")
def wallet_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    credit = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == user_id, Transaction.type == "income")
        .scalar()
        or 0
    )
    debit = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == user_id, Transaction.type == "expense")
        .scalar()
        or 0
    )
    recent = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "balance": round(credit - debit, 2),
            "total_credits": round(credit, 2),
            "total_debits": round(debit, 2),
            "currency": "INR",
            "recent_transactions": [
                {
                    "id": t.id,
                    "transaction_id": t.transaction_id,
                    "type": t.type,
                    "category": t.category,
                    "amount": t.amount,
                    "description": t.description,
                    "payment_method": t.payment_method,
                    "transaction_date": str(t.transaction_date) if t.transaction_date else None,
                    "created_at": str(t.created_at) if t.created_at else None,
                }
                for t in recent
            ],
        },
    }


@router.post("/wallet/add-money", status_code=201)
def wallet_add_money(
    payload: WalletAddMoney,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn_id = generate_id("FA-TXN", db, Transaction)
    txn = Transaction(
        transaction_id=txn_id,
        user_id=current_user.id,
        type="income",
        category="Wallet Top-up",
        amount=payload.amount,
        description=payload.description or "Added money to digital wallet",
        payment_method=payload.payment_method or "UPI",
        transaction_date=datetime.utcnow(),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return {
        "status": "success",
        "message": "Money added to wallet successfully",
        "data": {
            "id": txn.id,
            "transaction_id": txn.transaction_id,
            "type": txn.type,
            "category": txn.category,
            "amount": txn.amount,
        },
    }


@router.post("/wallet/transfer", status_code=201)
def wallet_transfer(
    payload: WalletTransfer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    credit = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.type == "income",
        )
        .scalar()
        or 0
    )
    debit = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.type == "expense",
        )
        .scalar()
        or 0
    )
    if payload.amount > (credit - debit):
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    txn_id = generate_id("FA-TXN", db, Transaction)
    recipient = payload.recipient or (payload.recipient_upi or "UPI Account")
    txn = Transaction(
        transaction_id=txn_id,
        user_id=current_user.id,
        type="expense",
        category="Wallet Transfer",
        amount=payload.amount,
        description=(
            payload.note
            or f"Transferred {payload.amount:,.2f} to {recipient}"
        ),
        payment_method=payload.payment_method or "UPI",
        reference_id=payload.recipient_upi,
        transaction_date=datetime.utcnow(),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return {
        "status": "success",
        "message": "Transfer completed successfully",
        "data": {
            "id": txn.id,
            "transaction_id": txn.transaction_id,
            "type": txn.type,
            "category": txn.category,
            "amount": txn.amount,
            "recipient": recipient,
        },
    }
