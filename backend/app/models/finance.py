from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    transaction_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    type = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    payment_method = Column(String(50), nullable=True)
    transaction_date = Column(DateTime, nullable=True)
    reference_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="transactions")
    farm = relationship("Farm", back_populates="transactions")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    expense_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    category = Column(String(50), nullable=False)
    subcategory = Column(String(50), nullable=True)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    vendor = Column(String(200), nullable=True)
    payment_method = Column(String(50), nullable=True)
    receipt_url = Column(String(500), nullable=True)
    expense_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Income(Base):
    __tablename__ = "income_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    income_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    category = Column(String(50), nullable=False)
    source = Column(String(200), nullable=True)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    buyer = Column(String(200), nullable=True)
    payment_method = Column(String(50), nullable=True)
    income_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    category = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    period = Column(String(20), default="monthly")
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Loan(Base):
    __tablename__ = "loans"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    loan_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    bank_name = Column(String(200), nullable=True)
    loan_amount = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=True)
    tenure_months = Column(Integer, nullable=True)
    emi_amount = Column(Float, nullable=True)
    outstanding_amount = Column(Float, nullable=True)
    status = Column(String(20), default="active")
    start_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
