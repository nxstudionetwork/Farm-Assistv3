import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Float, Integer, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.base import Base


def generate_uuid():
    return str(uuid.uuid4())


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    wallet_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    farmer_id = Column(String(20), index=True, nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    wallet_pin_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_setup_complete = Column(Boolean, default=False)
    upi_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet", foreign_keys="[WalletTransaction.wallet_id]", order_by="WalletTransaction.created_at.desc()")

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_wallet_user"),
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    transaction_id = Column(String(20), unique=True, index=True)
    wallet_id = Column(String(36), ForeignKey("wallets.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    recipient_wallet_id = Column(String(36), ForeignKey("wallets.id"), nullable=True)
    recipient_user_id = Column(String(36), nullable=True)
    transaction_type = Column(String(30), nullable=False)
    amount = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    reference_id = Column(String(100), nullable=True)
    payment_method = Column(String(50), nullable=True)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime, default=datetime.utcnow)

    wallet = relationship("Wallet", foreign_keys=[wallet_id], back_populates="transactions")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_wallet_txn_user_date", "user_id", "created_at"),
    )


class WalletBeneficiary(Base):
    __tablename__ = "wallet_beneficiaries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    beneficiary_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    beneficiary_name = Column(String(200), nullable=False)
    beneficiary_farmer_id = Column(String(20), nullable=True)
    beneficiary_upi = Column(String(100), nullable=True)
    beneficiary_phone = Column(String(15), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    beneficiary = relationship("User", foreign_keys=[beneficiary_user_id])


class MoneyRequest(Base):
    __tablename__ = "money_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    request_id = Column(String(20), unique=True, index=True)
    sender_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    receiver_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    sender_farmer_id = Column(String(20), nullable=True)
    receiver_farmer_id = Column(String(20), nullable=True)
    amount = Column(Float, nullable=False)
    note = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    reference_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sender = relationship("User", foreign_keys=[sender_user_id])
    receiver = relationship("User", foreign_keys=[receiver_user_id])


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    account_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    bank_name = Column(String(200), nullable=True)
    account_holder_name = Column(String(200), nullable=True)
    masked_account_number = Column(String(20), nullable=True)
    ifsc_code = Column(String(20), nullable=True)
    account_type = Column(String(30), default="savings")
    verification_status = Column(String(20), default="pending")
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="bank_accounts")
