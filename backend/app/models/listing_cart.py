from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Float, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.farm import gen_uuid


class ListingCart(Base):
    """Cart for farmer stock listings (MarketplaceListing).

    This is deliberately a separate table from MarketplaceCart because
    MarketplaceCartItem.product_id is a NOT NULL foreign key to products, while
    the Input Store "Stock" tab trades in MarketplaceListing rows. Keeping the
    two apart means the existing New/Product cart keeps working untouched.
    """

    __tablename__ = "listing_carts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship(
        "ListingCartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        order_by="ListingCartItem.created_at",
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_listing_cart_user"),
    )


class ListingCartItem(Base):
    __tablename__ = "listing_cart_items"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    cart_id = Column(String(36), ForeignKey("listing_carts.id"), nullable=False, index=True)
    listing_id = Column(String(36), ForeignKey("marketplace_listings.id"), nullable=False, index=True)
    quantity = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cart = relationship("ListingCart", back_populates="items")
    listing = relationship("MarketplaceListing")

    __table_args__ = (
        # One row per listing per cart, so "add to cart" can safely merge quantities.
        UniqueConstraint("cart_id", "listing_id", name="uq_listing_cart_item"),
    )


class ListingPurchaseKey(Base):
    """Database-enforced idempotency guard for Buy Now / cart checkout.

    The unique constraint is what actually prevents a double click (or a retry
    racing the first request) from creating two orders: the second insert raises
    an IntegrityError instead of silently succeeding.
    """

    __tablename__ = "listing_purchase_keys"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    buyer_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    idem_key = Column(String(80), nullable=False, index=True)
    sale_id = Column(String(36), ForeignKey("marketplace_sales.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("buyer_user_id", "idem_key", name="uq_listing_purchase_key"),
        Index("ix_listing_purchase_key_sale", "sale_id"),
    )
