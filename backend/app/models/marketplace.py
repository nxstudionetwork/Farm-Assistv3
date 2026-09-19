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
    supports_cod = Column(Boolean, default=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("ProductCategory")
    seller = relationship("Seller")
    order_items = relationship("OrderItem", back_populates="product")
    crops = relationship(
        "ProductCrop",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    equipment_metadata = relationship(
        "EquipmentMetadata",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )


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
    received_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    tracking = relationship("DeliveryTracking", back_populates="order", cascade="all, delete-orphan", order_by="DeliveryTracking.timestamp")
    contact = relationship("DeliveryContact", back_populates="order", cascade="all, delete-orphan", uselist=False)


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


class ProductCrop(Base):
    """Crop suitability mapping for marketplace/input-store products.

    A product can be relevant to several crops (seed packet intended for
    paddy, fertiliser suitable for maize and cotton, etc.). This keeps crop
    filtering and farm recommendations relational instead of embedding crop
    lists inside the JSON ``tags`` blob.
    """

    __tablename__ = "product_crops"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    crop_name = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="crops")

    __table_args__ = (UniqueConstraint("product_id", "crop_name", name="uq_product_crop"),)


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
    order_id = Column(String(36), ForeignKey("marketplace_orders.id"), nullable=False, index=True)
    status = Column(String(50), nullable=False)
    location = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    order = relationship("MarketplaceOrder", back_populates="tracking")


class DeliveryContact(Base):
    """Responsible person assigned by the company/delivery partner for an order.

    Populated only with real data supplied by the fulfilment provider. When no
    contact has been assigned (the common case), the API returns ``null`` and the
    UI shows ``Person in charge has not been assigned yet.``
    """

    __tablename__ = "delivery_contacts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(String(36), ForeignKey("marketplace_orders.id"), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=True)
    role = Column(String(100), nullable=True)
    company = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    availability_status = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("MarketplaceOrder", back_populates="contact")


class EquipmentMetadata(Base):
    __tablename__ = "equipment_metadata"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    product_id = Column(String(36), ForeignKey("products.id"), unique=True, nullable=False, index=True)
    equipment_type = Column(String(100), nullable=True, index=True)
    power_source = Column(String(50), nullable=True)
    material = Column(String(100), nullable=True)
    weight = Column(String(50), nullable=True)
    dimensions = Column(String(100), nullable=True)
    warranty = Column(String(100), nullable=True)
    suitable_use = Column(String(100), nullable=True, index=True)
    operating_width = Column(String(50), nullable=True)
    capacity = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)
    condition = Column(String(30), nullable=True)
    delivery_available = Column(Boolean, nullable=True)
    pickup_available = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="equipment_metadata")


class FarmerRecentlyViewed(Base):
    __tablename__ = "farmer_recently_viewed"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    viewed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    user = relationship("User")
    product = relationship("Product")

    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_recently_viewed_product"),)


# ============================================================================
# Marketplace - Seller (Farmer Selling Platform)
# ============================================================================
# These entities power the farmer's SELLING side of the Marketplace. They reuse
# the existing users table for ownership, the messages system for buyer
# enquiries (via conversation_id) and the existing storage service for photo
# uploads. They intentionally live OUTSIDE the ``products`` catalogue so that
# the Input Store (BUY side, product catalogue) and the Marketplace (SELL side,
# farmer listings) stay two completely different domains on the same backend.
# ----------------------------------------------------------------------------


class MarketplaceCategory(Base):
    """Sellable categories for farmer listings (crops/produce + farm items)."""

    __tablename__ = "marketplace_categories"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, index=True)
    group = Column(String(20), nullable=False)  # produce | items
    icon = Column(String(50), nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MarketplaceListing(Base):
    """A farmer's sellable listing (crops, produce, tools, equipment, ...)."""

    __tablename__ = "marketplace_listings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    listing_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("marketplace_categories.id"), nullable=True, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    quantity = Column(Float, default=1)
    unit = Column(String(20), default="kg")
    price = Column(Float, nullable=False)
    pricing_type = Column(String(20), default="fixed")  # fixed | negotiable

    location = Column(String(200), nullable=True)
    availability = Column(String(60), nullable=True)
    harvest_date = Column(String(20), nullable=True)
    quality_grade = Column(String(60), nullable=True)

    condition_type = Column(String(20), nullable=True)  # new | used
    condition_detail = Column(Text, nullable=True)
    age_year = Column(String(60), nullable=True)
    brand = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    usage_details = Column(Text, nullable=True)

    contact_method = Column(String(60), nullable=True)  # phone | whatsapp | in-app
    notes = Column(Text, nullable=True)

    status = Column(String(20), default="active", index=True)  # active | pending | sold | paused | expired | cancelled
    sold_quantity = Column(Float, default=0)
    sold_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    total_views = Column(Integer, default=0)
    interested_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("MarketplaceCategory")
    images = relationship(
        "MarketplaceListingImage",
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="MarketplaceListingImage.sort_order",
        lazy="selectin",
    )
    enquiries = relationship("MarketplaceEnquiry", back_populates="listing", cascade="all, delete-orphan")
    sales = relationship("MarketplaceSale", back_populates="listing", cascade="all, delete-orphan")


class MarketplaceListingImage(Base):
    __tablename__ = "marketplace_listing_images"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    listing_id = Column(String(36), ForeignKey("marketplace_listings.id"), nullable=False, index=True)
    image_url = Column(String(500), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    listing = relationship("MarketplaceListing", back_populates="images")


class MarketplaceEnquiry(Base):
    """A buyer enquiry linked to an existing Messages conversation."""

    __tablename__ = "marketplace_enquiries"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    listing_id = Column(String(36), ForeignKey("marketplace_listings.id"), nullable=False, index=True)
    buyer_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    buyer_name = Column(String(200), nullable=True)
    buyer_phone = Column(String(20), nullable=True)
    message = Column(Text, nullable=False)
    requested_quantity = Column(Float, nullable=True)
    offered_price = Column(Float, nullable=True)
    status = Column(String(20), default="new", index=True)  # new | replied | negotiating | accepted | closed | rejected
    conversation_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    listing = relationship("MarketplaceListing", back_populates="enquiries")
    buyer = relationship("User", foreign_keys=[buyer_user_id])


class MarketplaceBuyerRecommendation(Base):
    """A seller recommends a potential buyer (persisted per seller-buyer pair).

    The "Potential Buyers" strip on the seller dashboard lets farmers promote
    buyers they trust. Storing the pair (seller, buyer) makes the
    recommendation durable and toggleable without any messaging side-effects.
    """

    __tablename__ = "marketplace_buyer_recommendations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    recommendation_id = Column(String(20), unique=True, index=True)
    seller_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    buyer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    seller = relationship("User", foreign_keys=[seller_id])
    buyer = relationship("User", foreign_keys=[buyer_id])

    __table_args__ = (
        UniqueConstraint("seller_id", "buyer_id", name="uq_marketplace_buyer_recommendation_seller_buyer"),
    )


class MarketplaceSale(Base):
    """A completed or in-progress sale of a farmer's listing."""

    __tablename__ = "marketplace_sales"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    sale_id = Column(String(20), unique=True, index=True)
    listing_id = Column(String(36), ForeignKey("marketplace_listings.id"), nullable=False, index=True)
    buyer_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    buyer_name = Column(String(200), nullable=True)
    buyer_phone = Column(String(20), nullable=True)

    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)

    status = Column(String(20), default="pending", index=True)  # pending | confirmed | completed | cancelled
    payment_status = Column(String(20), default="pending")  # pending | paid | partial
    delivery_status = Column(String(20), default="pending")  # pending | pickup | delivered
    notes = Column(Text, nullable=True)

    sold_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    listing = relationship("MarketplaceListing", back_populates="sales")
    buyer = relationship("User", foreign_keys=[buyer_user_id])


class MarketplaceSellerSettings(Base):
    """Marketplace preferences persisted per farmer (1:1 with users.id).

    These settings control how the farmer's selling hub behaves: whether the
    farmer is available as a buyer, whether buyer enquiries are accepted, how
    contact/location details are shown and what the default visibility should
    be for newly created listings. Every value lives in the database so the
    state survives logins and browser changes - localStorage is never the
    source of truth.
    """

    __tablename__ = "marketplace_seller_settings"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    available_as_buyer = Column(Boolean, default=False, nullable=False)
    allow_buyer_enquiries = Column(Boolean, default=True, nullable=False)
    show_contact_to_buyers = Column(Boolean, default=True, nullable=False)
    receive_enquiry_notifications = Column(Boolean, default=True, nullable=False)
    show_location_to_buyers = Column(Boolean, default=True, nullable=False)
    allow_negotiation = Column(Boolean, default=True, nullable=False)
    default_listing_visibility = Column(String(20), default="active", nullable=False)  # active | pending
    notify_when_sold = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

