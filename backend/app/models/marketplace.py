from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Text, JSON, Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, index=True)
    icon = Column(String(50), nullable=True)
    parent_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Seller(Base):
    __tablename__ = "sellers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    seller_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    shop_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(200), nullable=True)
    rating = Column(Float, default=0.0)
    total_sales = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    product_id = Column(String(20), unique=True, index=True)
    seller_id = Column(String(36), ForeignKey("sellers.id"), nullable=True)
    category_id = Column(String(36), ForeignKey("product_categories.id"), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)
    unit = Column(String(20), default="kg")
    stock_quantity = Column(Float, default=0)
    min_order_quantity = Column(Float, default=1)
    image_url = Column(String(500), nullable=True)
    images = Column(JSON, nullable=True)
    brand = Column(String(100), nullable=True)
    rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("ProductCategory")
    seller = relationship("Seller")
    order_items = relationship("OrderItem", back_populates="product")


class MarketplaceCart(Base):
    __tablename__ = "marketplace_carts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = relationship("MarketplaceCartItem", back_populates="cart", cascade="all, delete-orphan")


class MarketplaceCartItem(Base):
    __tablename__ = "marketplace_cart_items"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    cart_id = Column(String(36), ForeignKey("marketplace_carts.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Float, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cart = relationship("MarketplaceCart", back_populates="items")
    product = relationship("Product")


class MarketplaceWishlist(Base):
    __tablename__ = "marketplace_wishlist"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    product = relationship("Product")

    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_marketplace_wishlist_user_product"),)


class MarketplaceOrder(Base):
    __tablename__ = "marketplace_orders"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String(20), default="pending")
    payment_status = Column(String(20), default="pending")
    payment_method = Column(String(50), nullable=True)
    delivery_address = Column(Text, nullable=True)
    delivery_name = Column(String(200), nullable=True)
    delivery_phone = Column(String(15), nullable=True)
    estimated_delivery = Column(String(10), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(String(36), ForeignKey("marketplace_orders.id"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    product_name = Column(String(200), nullable=True)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("MarketplaceOrder", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    payment_id = Column(String(20), unique=True, index=True)
    order_id = Column(String(36), ForeignKey("marketplace_orders.id"), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(50), nullable=True)
    status = Column(String(20), default="pending")
    transaction_ref = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeliveryTracking(Base):
    __tablename__ = "delivery_tracking"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(String(36), ForeignKey("marketplace_orders.id"), nullable=False)
    status = Column(String(50), nullable=False)
    location = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
