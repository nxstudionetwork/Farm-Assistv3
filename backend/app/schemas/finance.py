from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel


class TransactionCreate(BaseModel):
    farm_id: Optional[str] = None
    type: str
    category: str
    amount: float
    description: Optional[str] = None
    payment_method: Optional[str] = None
    transaction_date: Optional[datetime] = None


class TransactionResponse(BaseModel):
    id: str
    transaction_id: Optional[str] = None
    user_id: str
    farm_id: Optional[str] = None
    type: str
    category: str
    amount: float
    description: Optional[str] = None
    payment_method: Optional[str] = None
    transaction_date: Optional[datetime] = None
    reference_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExpenseCreate(BaseModel):
    farm_id: Optional[str] = None
    category: str
    subcategory: Optional[str] = None
    amount: float
    description: Optional[str] = None
    vendor: Optional[str] = None
    payment_method: Optional[str] = None
    expense_date: Optional[datetime] = None


class ExpenseResponse(BaseModel):
    id: str
    expense_id: Optional[str] = None
    user_id: str
    farm_id: Optional[str] = None
    category: str
    subcategory: Optional[str] = None
    amount: float
    description: Optional[str] = None
    vendor: Optional[str] = None
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    expense_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IncomeCreate(BaseModel):
    farm_id: Optional[str] = None
    category: str
    source: Optional[str] = None
    amount: float
    description: Optional[str] = None
    buyer: Optional[str] = None
    payment_method: Optional[str] = None
    income_date: Optional[datetime] = None


class IncomeResponse(BaseModel):
    id: str
    income_id: Optional[str] = None
    user_id: str
    farm_id: Optional[str] = None
    category: str
    source: Optional[str] = None
    amount: float
    description: Optional[str] = None
    buyer: Optional[str] = None
    payment_method: Optional[str] = None
    income_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FinanceSummary(BaseModel):
    total_income: float = 0.0
    total_expenses: float = 0.0
    net_profit: float = 0.0
    monthly_income: float = 0.0
    monthly_expenses: float = 0.0
    crop_wise_profit: Optional[Dict[str, float]] = None
