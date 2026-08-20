from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.marketplace import (
    ProductCategory, Product, MarketplaceOrder, OrderItem
)

router = APIRouter(prefix="/api/v1", tags=["Marketplace"])


class ProductCreate(BaseModel):
    name: str
    price: float = Field(gt=0)
    description: Optional[str] = None
    category_id: Optional[str] = None
    original_price: Optional[float] = None
    unit: str = "kg"
    stock_quantity: float = Field(default=0, ge=0)
    min_order_quantity: float = Field(default=1, ge=1)
    image_url: Optional[str] = None
    brand: Optional[str] = None


class OrderItemCreate(BaseModel):
    product_id: str
    quantity: float = Field(default=1, ge=1)


class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    delivery_address: Optional[str] = None
    delivery_name: Optional[str] = None
    delivery_phone: Optional[str] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: Optional[str] = Query("created_at", regex="^(price|rating|created_at|name)$"),
    sort_order: Optional[str] = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Product).filter(Product.is_active == True)
    if search:
        q = q.filter(
            Product.name.ilike(f"%{search}%")
            | Product.description.ilike(f"%{search}%")
            | Product.brand.ilike(f"%{search}%")
        )
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)

    sort_col = getattr(Product, sort_by, Product.created_at)
    if sort_order == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": p.id,
                    "product_id": p.product_id,
                    "name": p.name,
                    "description": p.description,
                    "price": p.price,
                    "original_price": p.original_price,
                    "unit": p.unit,
                    "stock_quantity": p.stock_quantity,
                    "image_url": p.image_url,
                    "brand": p.brand,
                    "rating": p.rating,
                    "total_reviews": p.total_reviews,
                    "category_id": p.category_id,
                    "seller_id": p.seller_id,
                }
                for p in items
            ],
        },
    }


@router.post("/products", status_code=201)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prod_id = generate_id("FA-PRD", db, Product)
    product = Product(
        product_id=prod_id,
        category_id=payload.category_id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        original_price=payload.original_price,
        unit=payload.unit,
        stock_quantity=payload.stock_quantity,
        min_order_quantity=payload.min_order_quantity,
        image_url=payload.image_url,
        brand=payload.brand,
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    return {
        "status": "success",
        "data": {
            "id": product.id,
            "product_id": product.product_id,
            "name": product.name,
            "price": product.price,
            "message": "Product created successfully",
        },
    }


@router.get("/products/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    cat = None
    if product.category_id:
        cat_obj = db.query(ProductCategory).filter(ProductCategory.id == product.category_id).first()
        if cat_obj:
            cat = {"id": cat_obj.id, "name": cat_obj.name, "slug": cat_obj.slug}

    return {
        "status": "success",
        "data": {
            "id": product.id,
            "product_id": product.product_id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "original_price": product.original_price,
            "unit": product.unit,
            "stock_quantity": product.stock_quantity,
            "min_order_quantity": product.min_order_quantity,
            "image_url": product.image_url,
            "images": product.images,
            "brand": product.brand,
            "rating": product.rating,
            "total_reviews": product.total_reviews,
            "is_active": product.is_active,
            "tags": product.tags,
            "category": cat,
            "created_at": str(product.created_at) if product.created_at else None,
        },
    }


@router.get("/product-categories")
def list_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cats = db.query(ProductCategory).all()
    return {
        "status": "success",
        "data": {
            "items": [
                {"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon, "parent_id": c.parent_id}
                for c in cats
            ]
        },
    }


@router.post("/orders", status_code=201)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    order_id = generate_id("FA-ORD", db, MarketplaceOrder)
    total_amount = 0.0
    order = MarketplaceOrder(
        order_id=order_id,
        user_id=current_user.id,
        total_amount=0,
        delivery_address=payload.delivery_address,
        delivery_name=payload.delivery_name or current_user.full_name,
        delivery_phone=payload.delivery_phone or current_user.phone_number,
        payment_method=payload.payment_method,
        notes=payload.notes,
        status="pending",
        payment_status="pending",
    )
    db.add(order)
    db.flush()

    order_items = []
    for item in payload.items:
        product_id = item.product_id
        quantity = item.quantity
        product = db.query(Product).filter(Product.product_id == product_id).first()
        if not product:
            continue
        unit_price = product.price
        item_total = unit_price * quantity
        total_amount += item_total

        oi = OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=item_total,
        )
        db.add(oi)
        order_items.append(oi)

        if product.stock_quantity >= quantity:
            product.stock_quantity -= quantity

    order.total_amount = total_amount
    db.commit()
    db.refresh(order)

    return {
        "status": "success",
        "data": {
            "id": order.id,
            "order_id": order.order_id,
            "total_amount": order.total_amount,
            "items_count": len(order_items),
            "status": order.status,
            "message": "Order placed successfully",
        },
    }


@router.get("/orders")
def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(MarketplaceOrder).filter(MarketplaceOrder.user_id == current_user.id)
    if status:
        q = q.filter(MarketplaceOrder.status == status)

    total = q.count()
    items = q.order_by(MarketplaceOrder.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": o.id,
                    "order_id": o.order_id,
                    "total_amount": o.total_amount,
                    "status": o.status,
                    "payment_status": o.payment_status,
                    "created_at": str(o.created_at) if o.created_at else None,
                }
                for o in items
            ],
        },
    }


@router.get("/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(MarketplaceOrder).filter(
        MarketplaceOrder.order_id == order_id,
        MarketplaceOrder.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    o_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()

    return {
        "status": "success",
        "data": {
            "id": order.id,
            "order_id": order.order_id,
            "total_amount": order.total_amount,
            "status": order.status,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "delivery_address": order.delivery_address,
            "delivery_name": order.delivery_name,
            "delivery_phone": order.delivery_phone,
            "notes": order.notes,
            "created_at": str(order.created_at) if order.created_at else None,
            "items": [
                {
                    "product_name": oi.product_name,
                    "quantity": oi.quantity,
                    "unit_price": oi.unit_price,
                    "total_price": oi.total_price,
                }
                for oi in o_items
            ],
        },
    }


@router.put("/orders/{order_id}")
def update_order(
    order_id: str,
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = db.query(MarketplaceOrder).filter(
        MarketplaceOrder.order_id == order_id,
        MarketplaceOrder.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if status:
        valid = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
        if status not in valid:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid)}")
        order.status = status
    if payment_status:
        valid_pay = ["pending", "paid", "failed", "refunded"]
        if payment_status not in valid_pay:
            raise HTTPException(status_code=400, detail=f"Invalid payment status. Must be one of: {', '.join(valid_pay)}")
        order.payment_status = payment_status
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)

    return {
        "status": "success",
        "data": {
            "id": order.id,
            "order_id": order.order_id,
            "status": order.status,
            "payment_status": order.payment_status,
            "message": "Order updated successfully",
        },
    }
