from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.utils.notification_helper import create_notification
from app.models.user import User
from app.models.finance import Transaction, Expense, Income
from app.models.farm import Farm

router = APIRouter(prefix="/api/v1", tags=["Finance"])


def _assert_farm_owned(db: Session, farm_id: Optional[str], current_user: User) -> None:
    """Ensure a supplied farm_id belongs to the current user before creating a record."""
    if farm_id:
        farm = (
            db.query(Farm)
            .filter(Farm.id == farm_id, Farm.user_id == current_user.id)
            .first()
        )
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")


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


class IncomeUpdate(BaseModel):
    category: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    source: Optional[str] = None
    description: Optional[str] = None
    buyer: Optional[str] = None
    payment_method: Optional[str] = None
    farm_id: Optional[str] = None
    income_date: Optional[str] = None


class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    vendor: Optional[str] = None
    payment_method: Optional[str] = None
    farm_id: Optional[str] = None
    receipt_url: Optional[str] = None
    expense_date: Optional[str] = None


def _income_to_dict(i: Income) -> dict:
    return {
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


def _expense_to_dict(e: Expense) -> dict:
    return {
        "id": e.id,
        "expense_id": e.expense_id,
        "category": e.category,
        "subcategory": e.subcategory,
        "amount": e.amount,
        "description": e.description,
        "vendor": e.vendor,
        "payment_method": e.payment_method,
        "receipt_url": e.receipt_url,
        "farm_id": e.farm_id,
        "expense_date": str(e.expense_date) if e.expense_date else None,
        "created_at": str(e.created_at) if e.created_at else None,
    }


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
    _assert_farm_owned(db, payload.farm_id, current_user)
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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Expense).filter(Expense.user_id == current_user.id)
    if farm_id:
        query = query.filter(Expense.farm_id == farm_id)
    if category:
        query = query.filter(Expense.category == category)
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            query = query.filter(func.coalesce(Expense.expense_date, Expense.created_at) >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            query = query.filter(func.coalesce(Expense.expense_date, Expense.created_at) <= ed)
        except ValueError:
            pass
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Expense.category.ilike(term),
                Expense.description.ilike(term),
                Expense.vendor.ilike(term),
                Expense.expense_id.ilike(term),
            )
        )

    total = query.count()
    items = query.order_by(Expense.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_expense_to_dict(e) for e in items],
        },
    }


@router.post("/expenses", status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_farm_owned(db, payload.farm_id, current_user)
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

    try:
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Expense Recorded",
            message=(
                f"₹{payload.amount:,.2f} recorded under {payload.category}. "
                f"Total expenses are kept in your financial summary."
            ),
            notification_type="finance",
            reference_id=expense.expense_id,
            reference_type="expense",
            icon="fa-arrow-down",
            action_url="wallet.html",
        )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "success",
        "message": "Expense created successfully",
        "data": _expense_to_dict(expense),
    }


@router.get("/expenses/{expense_id}")
def get_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = (
        db.query(Expense)
        .filter(
            Expense.expense_id == expense_id,
            Expense.user_id == current_user.id,
        )
        .first()
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"status": "success", "data": _expense_to_dict(expense)}


@router.put("/expenses/{expense_id}")
def update_expense(
    expense_id: str,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = (
        db.query(Expense)
        .filter(
            Expense.expense_id == expense_id,
            Expense.user_id == current_user.id,
        )
        .first()
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    _assert_farm_owned(db, payload.farm_id, current_user)

    updates = payload.model_dump(exclude_unset=True)
    date_val = updates.pop("expense_date", None)
    if date_val:
        try:
            expense.expense_date = datetime.fromisoformat(date_val)
        except ValueError:
            expense.expense_date = datetime.utcnow()

    for key, value in updates.items():
        if value is not None:
            setattr(expense, key, value)
    db.commit()
    db.refresh(expense)

    return {
        "status": "success",
        "message": "Expense updated successfully",
        "data": _expense_to_dict(expense),
    }


@router.delete("/expenses/{expense_id}")
def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = (
        db.query(Expense)
        .filter(
            Expense.expense_id == expense_id,
            Expense.user_id == current_user.id,
        )
        .first()
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()
    return {
        "status": "success",
        "message": "Expense deleted successfully",
        "data": {"expense_id": expense_id},
    }


@router.get("/income")
def list_income(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    farm_id: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Income).filter(Income.user_id == current_user.id)
    if farm_id:
        query = query.filter(Income.farm_id == farm_id)
    if category:
        query = query.filter(Income.category == category)
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            query = query.filter(func.coalesce(Income.income_date, Income.created_at) >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            query = query.filter(func.coalesce(Income.income_date, Income.created_at) <= ed)
        except ValueError:
            pass
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Income.category.ilike(term),
                Income.description.ilike(term),
                Income.source.ilike(term),
                Income.buyer.ilike(term),
                Income.income_id.ilike(term),
            )
        )

    total = query.count()
    items = query.order_by(Income.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_income_to_dict(i) for i in items],
        },
    }


@router.post("/income", status_code=201)
def create_income(
    payload: IncomeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_farm_owned(db, payload.farm_id, current_user)
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

    try:
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Income Recorded",
            message=(
                f"₹{payload.amount:,.2f} recorded under {payload.category}. "
                f"Total income is kept in your financial summary."
            ),
            notification_type="finance",
            reference_id=income.income_id,
            reference_type="income",
            icon="fa-arrow-up",
            action_url="wallet.html",
        )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "success",
        "message": "Income record created successfully",
        "data": _income_to_dict(income),
    }


@router.get("/income/{income_id}")
def get_income(
    income_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    income = (
        db.query(Income)
        .filter(
            Income.income_id == income_id,
            Income.user_id == current_user.id,
        )
        .first()
    )
    if not income:
        raise HTTPException(status_code=404, detail="Income record not found")
    return {"status": "success", "data": _income_to_dict(income)}


@router.put("/income/{income_id}")
def update_income(
    income_id: str,
    payload: IncomeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    income = (
        db.query(Income)
        .filter(
            Income.income_id == income_id,
            Income.user_id == current_user.id,
        )
        .first()
    )
    if not income:
        raise HTTPException(status_code=404, detail="Income record not found")

    _assert_farm_owned(db, payload.farm_id, current_user)

    updates = payload.model_dump(exclude_unset=True)
    date_val = updates.pop("income_date", None)
    if date_val:
        try:
            income.income_date = datetime.fromisoformat(date_val)
        except ValueError:
            income.income_date = datetime.utcnow()

    for key, value in updates.items():
        if value is not None:
            setattr(income, key, value)
    db.commit()
    db.refresh(income)

    return {
        "status": "success",
        "message": "Income record updated successfully",
        "data": _income_to_dict(income),
    }


@router.delete("/income/{income_id}")
def delete_income(
    income_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    income = (
        db.query(Income)
        .filter(
            Income.income_id == income_id,
            Income.user_id == current_user.id,
        )
        .first()
    )
    if not income:
        raise HTTPException(status_code=404, detail="Income record not found")
    db.delete(income)
    db.commit()
    return {
        "status": "success",
        "message": "Income record deleted successfully",
        "data": {"income_id": income_id},
    }


@router.get("/transactions/{transaction_id}")
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn = (
        db.query(Transaction)
        .filter(
            Transaction.transaction_id == transaction_id,
            Transaction.user_id == current_user.id,
        )
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "status": "success",
        "data": {
            "id": txn.id,
            "transaction_id": txn.transaction_id,
            "type": txn.type,
            "category": txn.category,
            "amount": txn.amount,
            "description": txn.description,
            "payment_method": txn.payment_method,
            "farm_id": txn.farm_id,
            "reference_id": txn.reference_id,
            "transaction_date": str(txn.transaction_date) if txn.transaction_date else None,
            "created_at": str(txn.created_at) if txn.created_at else None,
        },
    }




