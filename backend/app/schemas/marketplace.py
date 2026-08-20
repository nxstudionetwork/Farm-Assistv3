from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    original_price: Optional[float] = None
    unit: Optional[str] = None
    stock_quantity: Optional[float] = None
    min_order_quantity: Optional[float] = None
    image_url: Optional[str] = None
    brand: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None


class ProductResponse(BaseModel):
    id: str
    product_id: Optional[str] = None
    seller_id: Optional[str] = None
    category_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    price: float
    original_price: Optional[float] = None
    unit: Optional[str] = None
    stock_quantity: Optional[float] = None
    min_order_quantity: Optional[float] = None
    image_url: Optional[str] = None
    images: Optional[Any] = None
    brand: Optional[str] = None
    rating: Optional[float] = None
    total_reviews: Optional[int] = None
    is_active: Optional[bool] = None
    tags: Optional[Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrderItemCreate(BaseModel):
    product_id: str
    quantity: float


class OrderItemResponse(BaseModel):
    id: str
    order_id: str
    product_id: str
    product_name: Optional[str] = None
    quantity: float
    unit_price: float
    total_price: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MarketplaceOrderCreate(BaseModel):
    items: List[OrderItemCreate]
    delivery_address: Optional[str] = None
    delivery_name: Optional[str] = None
    delivery_phone: Optional[str] = None
    notes: Optional[str] = None
    payment_method: Optional[str] = None


class MarketplaceOrderResponse(BaseModel):
    id: str
    order_id: Optional[str] = None
    user_id: str
    total_amount: float
    status: Optional[str] = None
    payment_status: Optional[str] = None
    payment_method: Optional[str] = None
    delivery_address: Optional[str] = None
    delivery_name: Optional[str] = None
    delivery_phone: Optional[str] = None
    estimated_delivery: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    items: Optional[List[OrderItemResponse]] = None

    class Config:
        from_attributes = True
