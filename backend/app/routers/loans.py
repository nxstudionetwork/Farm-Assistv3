from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database.connection import get_db
from app.models.finance import Loan
from app.models.user import User
from app.utils.auth import get_current_user, generate_id

router = APIRouter(prefix="/api/v1", tags=["Loans"])


class LoanCreateRequest(BaseModel):
    bank_name: Optional[str] = None
    loan_amount: float
    interest_rate: Optional[float] = None
    tenure_months: Optional[int] = None
    emi_amount: Optional[float] = None
    loan_type: Optional[str] = None
    purpose: Optional[str] = None


class LoanUpdateRequest(BaseModel):
    status: Optional[str] = None
    outstanding_amount: Optional[float] = None
    emi_amount: Optional[float] = None


@router.get("/loans", response_model=dict)
def list_loans(
    status: Optional[str] = None,
    loan_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Loan).filter(Loan.user_id == current_user.id)
    if status:
        query = query.filter(Loan.status == status)
    total = query.count()
    loans = query.order_by(Loan.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "status": "success",
        "data": [{
            "loan_id": l.loan_id,
            "bank_name": l.bank_name,
            "loan_amount": l.loan_amount,
            "interest_rate": l.interest_rate,
            "tenure_months": l.tenure_months,
            "emi_amount": l.emi_amount,
            "outstanding_amount": l.outstanding_amount,
            "status": l.status,
            "start_date": l.start_date.isoformat() if l.start_date else None,
            "created_at": l.created_at.isoformat(),
        } for l in loans],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/loans", response_model=dict, status_code=201)
def create_loan(
    payload: LoanCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = Loan(
        user_id=current_user.id,
        bank_name=payload.bank_name,
        loan_amount=payload.loan_amount,
        interest_rate=payload.interest_rate,
        tenure_months=payload.tenure_months,
        emi_amount=payload.emi_amount,
        outstanding_amount=payload.loan_amount,
        status="active",
        start_date=datetime.utcnow(),
    )
    db.add(loan)
    db.flush()
    loan.loan_id = generate_id("FA-LOAN", db, Loan)
    db.commit()
    db.refresh(loan)
    return {"status": "success", "message": "Loan created", "data": {"loan_id": loan.loan_id}}


@router.put("/loans/{loan_id}", response_model=dict)
def update_loan(
    loan_id: str,
    payload: LoanUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id, Loan.user_id == current_user.id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if payload.status:
        loan.status = payload.status
    if payload.outstanding_amount is not None:
        loan.outstanding_amount = payload.outstanding_amount
    if payload.emi_amount is not None:
        loan.emi_amount = payload.emi_amount
    db.commit()
    return {"status": "success", "message": "Loan updated"}


@router.get("/loans/summary", response_model=dict)
def loan_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loans = db.query(Loan).filter(Loan.user_id == current_user.id).all()
    total_borrowed = sum(l.loan_amount for l in loans)
    total_outstanding = sum(l.outstanding_amount or 0 for l in loans)
    active_loans = sum(1 for l in loans if l.status == "active")
    return {
        "status": "success",
        "data": {
            "total_loans": len(loans),
            "active_loans": active_loans,
            "total_borrowed": total_borrowed,
            "total_outstanding": total_outstanding,
            "monthly_emi": sum(l.emi_amount or 0 for l in loans if l.status == "active"),
        },
    }
