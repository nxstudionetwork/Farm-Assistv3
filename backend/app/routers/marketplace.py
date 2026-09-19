from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id, verify_password
from app.models.user import User
from app.models.marketplace import (
    ProductCategory, Product, MarketplaceCart, MarketplaceCartItem, MarketplaceWishlist,
    MarketplaceOrder, OrderItem, DeliveryTracking, DeliveryContact, FarmerRecentlyViewed,
)
from app.models.wallet import Wallet, WalletTransaction

router = APIRouter(prefix="/api/v1", tags=["Marketplace"])

# Order lifecycle shared by the router, the storefront and the orders page.
ORDER_STATUS_LABELS = {
    "placed": "Placed",
    "processing": "Processing",
    "shipped": "Shipped",
    "out_for_delivery": "Out for Delivery",
    "received": "Received",
    "cancelled": "Cancelled",
}
# Display flow for the track timeline / orders page.
ORDER_STATUS_FLOW = ["placed", "processing", "shipped", "out_for_delivery", "received"]
# Maps statuses written by older builds to the current canonical set.
LEGACY_STATUS_MAP = {"pending": "placed", "confirmed": "processing", "delivered": "received"}
PAYMENT_METHOD_ALIASES = {"farm_assist_wallet": "wallet", "cash_on_delivery": "cod"}


def _norm_order_status(status: Optional[str]) -> str:
    st = (status or "").strip().lower()
    if st in LEGACY_STATUS_MAP:
        st = LEGACY_STATUS_MAP[st]
    if st not in ORDER_STATUS_LABELS:
        st = "placed"
    return st


def _status_payload(status: Optional[str]) -> dict:
    st = _norm_order_status(status)
    return {"status": st, "status_label": ORDER_STATUS_LABELS[st]}


def _payment_method_norm(method: Optional[str]) -> str:
    m = (method or "").strip().lower()
    if not m:
        m = "cod"
    if m in PAYMENT_METHOD_ALIASES:
        m = PAYMENT_METHOD_ALIASES[m]
    if m not in ("wallet", "cod"):
        raise HTTPException(
            status_code=400,
            detail="Invalid payment method. Use 'wallet' (Farm Assist Wallet) or 'cod' (Cash on Delivery).",
        )
    return m


def _cod_available_for_products(products: List[Product]) -> bool:
    return bool(products) and all(
        p.is_active
        and float(p.stock_quantity or 0) > 0
        and bool(getattr(p, "supports_cod", True))
        for p in products
    )


def _track(order: MarketplaceOrder, status: str, location: Optional[str] = None, notes: Optional[str] = None) -> DeliveryTracking:
    row = DeliveryTracking(
        order_id=order.id,
        status=_norm_order_status(status),
        location=location,
        notes=notes,
    )
    return row


def _default_estimate(days: int = 5) -> str:
    """Delivery estimate shown until the fulfilment provider sets a real one."""
    return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")


def _wallet_for_user(db: Session, user_id: str) -> Optional[Wallet]:
    return db.query(Wallet).filter(Wallet.user_id == user_id).first()


def _serialize_tracking(row: DeliveryTracking) -> dict:
    return {
        "status": _norm_order_status(row.status),
        "status_label": ORDER_STATUS_LABELS.get(_norm_order_status(row.status), row.status),
        "location": row.location,
        "notes": row.notes,
        "timestamp": str(row.timestamp) if row.timestamp else None,
    }


def _person_in_charge(order: MarketplaceOrder) -> Optional[dict]:
    contact: Optional[DeliveryContact] = order.contact
    if not contact:
        return None
    return {
        "name": contact.name,
        "role": contact.role,
        "company": contact.company,
        "phone": contact.phone,
        "email": contact.email,
        "availability_status": contact.availability_status,
    }


def _order_item_payload(oi: OrderItem) -> dict:
    product = oi.product
    return {
        "product_id": product.product_id if product else oi.product_id,
        "product_name": oi.product_name,
        "quantity": oi.quantity,
        "unit_price": oi.unit_price,
        "total_price": oi.total_price,
        "image_url": product.image_url if product else None,
    }


def _order_slim(order: MarketplaceOrder) -> dict:
    st = _norm_order_status(order.status)
    return {
        "id": order.id,
        "order_id": order.order_id,
        "total_amount": order.total_amount,
        "status": st,
        "status_label": ORDER_STATUS_LABELS[st],
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "estimated_delivery": order.estimated_delivery,
        "received_at": str(order.received_at) if order.received_at else None,
        "created_at": str(order.created_at) if order.created_at else None,
        "notes": order.notes,
        "summary": _order_first_item(order),
        "can_cancel": st not in ("received", "cancelled"),
        "can_reorder": st == "received",
    }


def _order_detail(order: MarketplaceOrder) -> dict:
    st = _norm_order_status(order.status)
    return {
        **_order_slim(order),
        "delivery_address": order.delivery_address,
        "delivery_name": order.delivery_name,
        "delivery_phone": order.delivery_phone,
        "cancelled_at": str(order.cancelled_at) if order.cancelled_at else None,
        "items": [_order_item_payload(oi) for oi in order.items],
        "tracking": [_serialize_tracking(t) for t in order.tracking],
        "expected_delivery": order.estimated_delivery,
        "reference_number": order.order_id,
        "company": order.contact.company if order.contact else None,
        "person_in_charge": _person_in_charge(order),
        "can_confirm_received": st in ("placed", "processing", "shipped", "out_for_delivery"),
    }


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
    quantity: int = Field(default=1, ge=1)


class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    delivery_address: Optional[str] = None
    delivery_name: Optional[str] = None
    delivery_phone: Optional[str] = None
    payment_method: Optional[str] = None
    wallet_pin: Optional[str] = None
    notes: Optional[str] = None


class CartItemPayload(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1)


def _product_payload(product: Product) -> dict:
    return {
        "id": product.id, "product_id": product.product_id, "name": product.name,
        "description": product.description, "price": product.price,
        "original_price": product.original_price, "unit": product.unit,
        "stock_quantity": product.stock_quantity, "min_order_quantity": product.min_order_quantity,
        "image_url": product.image_url, "images": product.images, "brand": product.brand,
        "rating": product.rating, "total_reviews": product.total_reviews,
        "category_id": product.category_id, "seller_id": product.seller_id, "tags": product.tags,
        "supports_cod": bool(getattr(product, "supports_cod", True)),
    }


def _cart_for_user(db: Session, user_id: str) -> MarketplaceCart:
    cart = db.query(MarketplaceCart).filter(MarketplaceCart.user_id == user_id).first()
    if not cart:
        cart = MarketplaceCart(user_id=user_id)
        db.add(cart)
        db.flush()
    return cart


def _cart_payload(cart: MarketplaceCart) -> dict:
    items = []
    cod_supported = True if cart.items else False
    for item in cart.items:
        product = item.product
        if not product or not product.is_active:
            cod_supported = False
            continue
        price = float(product.price or 0)
        items.append({"id": item.id, "quantity": item.quantity, "subtotal": round(price * item.quantity, 2), "product": _product_payload(product)})
        if float(product.stock_quantity or 0) <= 0 or not bool(getattr(product, "supports_cod", True)):
            cod_supported = False
    total = round(sum(i["subtotal"] for i in items), 2)
    return {"items": items, "total": total, "count": len(items), "cod_available": cod_supported}


@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: bool = False,
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
    if in_stock:
        q = q.filter(Product.stock_quantity > 0)

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
                _product_payload(p)
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


@router.get("/cart")
def get_cart(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": _cart_payload(_cart_for_user(db, current_user.id))}


@router.post("/cart")
def add_to_cart(payload: CartItemPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter((Product.id == payload.product_id) | (Product.product_id == payload.product_id), Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    cart = _cart_for_user(db, current_user.id)
    item = db.query(MarketplaceCartItem).filter(MarketplaceCartItem.cart_id == cart.id, MarketplaceCartItem.product_id == product.id).first()
    quantity = payload.quantity + (item.quantity if item else 0)
    if quantity > float(product.stock_quantity or 0):
        raise HTTPException(status_code=409, detail="Requested quantity is not available")
    if item:
        item.quantity = quantity
    else:
        db.add(MarketplaceCartItem(cart_id=cart.id, product_id=product.id, quantity=payload.quantity))
    db.commit()
    return {"status": "success", "data": _cart_payload(_cart_for_user(db, current_user.id))}


@router.patch("/cart/{item_id}")
def update_cart_item(item_id: str, payload: CartItemPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cart = _cart_for_user(db, current_user.id)
    item = db.query(MarketplaceCartItem).filter(MarketplaceCartItem.id == item_id, MarketplaceCartItem.cart_id == cart.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    if payload.quantity > float(item.product.stock_quantity or 0):
        raise HTTPException(status_code=409, detail="Requested quantity is not available")
    item.quantity = payload.quantity
    db.commit()
    return {"status": "success", "data": _cart_payload(_cart_for_user(db, current_user.id))}


@router.delete("/cart/{item_id}")
def remove_cart_item(item_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cart = _cart_for_user(db, current_user.id)
    item = db.query(MarketplaceCartItem).filter(MarketplaceCartItem.id == item_id, MarketplaceCartItem.cart_id == cart.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(item)
    db.commit()
    return {"status": "success", "data": _cart_payload(_cart_for_user(db, current_user.id))}


@router.get("/wishlist")
def get_wishlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.query(MarketplaceWishlist).filter(MarketplaceWishlist.user_id == current_user.id).order_by(MarketplaceWishlist.created_at.desc()).all()
    return {"status": "success", "data": {"items": [{"id": row.id, "product": _product_payload(row.product)} for row in rows if row.product and row.product.is_active]}}


@router.post("/wishlist/{product_id}", status_code=201)
def save_wishlist(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter((Product.id == product_id) | (Product.product_id == product_id), Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    saved = db.query(MarketplaceWishlist).filter(MarketplaceWishlist.user_id == current_user.id, MarketplaceWishlist.product_id == product.id).first()
    if not saved:
        db.add(MarketplaceWishlist(user_id=current_user.id, product_id=product.id))
        db.commit()
    return {"status": "success", "data": {"product_id": product.id}}


@router.delete("/wishlist/{product_id}")
def remove_wishlist(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter(
        (Product.id == product_id) | (Product.product_id == product_id)
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Saved product not found")
    saved = db.query(MarketplaceWishlist).filter(
        MarketplaceWishlist.user_id == current_user.id,
        MarketplaceWishlist.product_id == product.id,
    ).first()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved product not found")
    db.delete(saved)
    db.commit()
    return {"status": "success"}


@router.post("/products/{product_id}/view")
def record_product_view(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Record a real product view for the farmer's recently-viewed shelf."""
    product = db.query(Product).filter(
        (Product.id == product_id) | (Product.product_id == product_id),
        Product.is_active == True,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    row = db.query(FarmerRecentlyViewed).filter(
        FarmerRecentlyViewed.user_id == current_user.id,
        FarmerRecentlyViewed.product_id == product.id,
    ).first()
    if row:
        row.viewed_at = datetime.utcnow()
    else:
        db.add(FarmerRecentlyViewed(user_id=current_user.id, product_id=product.id))
    # Keep only the 40 most recent views per farmer.
    recent = db.query(FarmerRecentlyViewed.id).filter(
        FarmerRecentlyViewed.user_id == current_user.id
    ).order_by(FarmerRecentlyViewed.viewed_at.desc()).limit(40).all()
    keep_ids = [r[0] for r in recent]
    if keep_ids:
        old = db.query(FarmerRecentlyViewed).filter(
            FarmerRecentlyViewed.user_id == current_user.id,
            ~FarmerRecentlyViewed.id.in_(keep_ids),
        ).all()
        for stale in old:
            db.delete(stale)
    db.commit()
    return {"status": "success"}


@router.get("/products/recently-viewed")
def recently_viewed_products(
    limit: int = Query(12, ge=1, le=40),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(FarmerRecentlyViewed).filter(
        FarmerRecentlyViewed.user_id == current_user.id,
    ).order_by(FarmerRecentlyViewed.viewed_at.desc()).limit(limit).all()
    items = [
        _product_payload(r.product)
        for r in rows
        if r.product and r.product.is_active
    ]
    return {"status": "success", "data": {"total": len(items), "items": items}}


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

    method = _payment_method_norm(payload.payment_method)

    # Resolve + validate all line items up-front. The payable amount is always
    # recomputed from current DB prices — the frontend amount is never trusted.
    resolved: List[tuple] = []
    for item in payload.items:
        product = db.query(Product).filter(
            (Product.id == item.product_id) | (Product.product_id == item.product_id),
            Product.is_active == True,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")
        quantity = item.quantity
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid item quantity")
        if quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity must be greater than zero for {product.name}")
        available = float(product.stock_quantity or 0)
        if available < quantity:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock for {product.name}: requested {quantity}, available {available}",
            )
        resolved.append((product, quantity))

    total_amount = round(sum(float(p.price or 0) * q for p, q in resolved), 2)
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Order total must be greater than zero")

    # Pre-payment verification — nothing is written until every check passes.
    wallet = None
    if method == "wallet":
        wallet = _wallet_for_user(db, current_user.id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        if not wallet.is_active:
            raise HTTPException(status_code=403, detail="Wallet is inactive")
        if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
            raise HTTPException(status_code=403, detail="Complete wallet setup before paying")
        if not (payload.wallet_pin and verify_password(str(payload.wallet_pin).strip(), wallet.wallet_pin_hash)):
            raise HTTPException(status_code=401, detail="Invalid wallet PIN")
        if round(float(wallet.balance or 0), 2) < total_amount:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance")
    elif not _cod_available_for_products([p for p, _ in resolved]):
        raise HTTPException(status_code=400, detail="Cash on Delivery unavailable for this order.")

    try:
        order_id = generate_id("FA-ORD", db, MarketplaceOrder)
        order = MarketplaceOrder(
            order_id=order_id,
            user_id=current_user.id,
            total_amount=total_amount,
            delivery_address=payload.delivery_address,
            delivery_name=payload.delivery_name or current_user.full_name,
            delivery_phone=payload.delivery_phone or current_user.phone_number,
            payment_method=method,
            notes=payload.notes,
            status="placed",
            payment_status="paid" if method == "wallet" else "pending",
            estimated_delivery=_default_estimate(),
        )
        db.add(order)
        db.flush()

        for product, quantity in resolved:
            db.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=float(product.price or 0),
                total_price=round(float(product.price or 0) * quantity, 2),
            ))
            product.stock_quantity = round(float(product.stock_quantity or 0) - quantity, 4)

        db.add(_track(order, "placed", notes="Order placed successfully"))

        if method == "wallet":
            new_balance = round(float(wallet.balance or 0) - total_amount, 2)
            db.add(WalletTransaction(
                transaction_id=generate_id("FA-WTX", db, WalletTransaction),
                wallet_id=wallet.id,
                user_id=current_user.id,
                transaction_type="debit",
                amount=total_amount,
                balance_after=new_balance,
                description=f"Payment for order {order_id}",
                reference_id=order_id,
                payment_method="wallet_purchase",
                status="completed",
            ))
            wallet.balance = new_balance

        db.commit()
        db.refresh(order)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Order could not be created. Please try again.")

    return {
        "status": "success",
        "data": {
            "id": order.id,
            "order_id": order.order_id,
            "total_amount": order.total_amount,
            "items_count": len(order.items),
            "status": _norm_order_status(order.status),
            "status_label": ORDER_STATUS_LABELS[_norm_order_status(order.status)],
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "estimated_delivery": order.estimated_delivery,
            "message": "Payment successful — order placed" if method == "wallet" else "Order placed successfully",
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
            "items": [_order_slim(o) for o in items],
        },
    }


def _order_first_item(order):
    oi = order.items[0] if order.items else None
    if not oi:
        return {
            "product_name": None,
            "quantity": None,
            "unit_price": None,
            "image_url": None,
        }
    product = oi.product
    return {
        "product_name": oi.product_name,
        "quantity": oi.quantity,
        "unit_price": oi.unit_price,
        "image_url": product.image_url if product else None,
    }


@router.get("/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(MarketplaceOrder).filter(
        MarketplaceOrder.order_id == order_id,
        MarketplaceOrder.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {"status": "success", "data": _order_detail(order)}


@router.get("/orders/{order_id}/tracking")
def get_order_tracking(order_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(MarketplaceOrder).filter(
        MarketplaceOrder.order_id == order_id,
        MarketplaceOrder.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    rows = [_serialize_tracking(t) for t in order.tracking]
    st = _norm_order_status(order.status)
    return {
        "status": "success",
        "data": {
            "order_id": order.order_id,
            "current_status": st,
            "current_status_label": ORDER_STATUS_LABELS[st],
            "latest_update": rows[-1] if rows else None,
            "expected_delivery": order.estimated_delivery,
            "reference_number": order.order_id,
            "delivery_status": ORDER_STATUS_LABELS[st],
            "company": order.contact.company if order.contact else None,
            "person_in_charge": _person_in_charge(order),
            "tracking": rows,
        },
    }


@router.post("/orders/{order_id}/confirm-received")
def confirm_order_received(order_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(MarketplaceOrder).filter(
        MarketplaceOrder.order_id == order_id,
        MarketplaceOrder.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    st = _norm_order_status(order.status)
    if st in ("received", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Order is already {ORDER_STATUS_LABELS[st].lower()}.")

    now = datetime.utcnow()
    order.status = "received"
    order.received_at = now
    order.updated_at = now
    # COD payment is realised only at actual delivery/receipt.
    if (order.payment_method or "").lower() == "cod" and order.payment_status != "paid":
        order.payment_status = "paid"
    db.add(_track(order, "received", notes="Order delivered and received by farmer"))
    db.commit()
    db.refresh(order)

    return {
        "status": "success",
        "data": _order_detail(order),
        "message": "Order marked as Received. Thank you for shopping!",
    }


@router.post("/orders/{order_id}/reorder")
def reorder(order_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(MarketplaceOrder).filter(
        MarketplaceOrder.order_id == order_id,
        MarketplaceOrder.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    cart = _cart_for_user(db, current_user.id)
    added = []
    skipped = []
    for oi in order.items:
        product = oi.product
        if not product or not product.is_active:
            skipped.append({"product_name": oi.product_name or "Item", "reason": "No longer available"})
            continue
        available = float(product.stock_quantity or 0)
        if available <= 0:
            skipped.append({"product_name": oi.product_name or product.name, "reason": "Out of stock"})
            continue
        qty = round(min(float(oi.quantity or 1), available), 4)
        if qty <= 0:
            skipped.append({"product_name": oi.product_name or product.name, "reason": "Out of stock"})
            continue
        existing = db.query(MarketplaceCartItem).filter(
            MarketplaceCartItem.cart_id == cart.id,
            MarketplaceCartItem.product_id == product.id,
        ).first()
        if existing:
            combined = round(existing.quantity + qty, 4)
            existing.quantity = min(combined, available)
        else:
            db.add(MarketplaceCartItem(cart_id=cart.id, product_id=product.id, quantity=qty))
        added.append({
            "product_id": product.product_id,
            "product_name": oi.product_name or product.name,
            "quantity": qty,
            "current_price": product.price,
        })
    db.commit()
    return {
        "status": "success",
        "data": {
            "order_id": order.order_id,
            "added": added,
            "skipped": skipped,
            "cart": _cart_payload(_cart_for_user(db, current_user.id)),
        },
        "message": "Available items were added back to your cart." if added else "Nothing could be reordered right now.",
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

    now = datetime.utcnow()
    if status:
        st = _norm_order_status(status)
        if st == "cancelled" and _norm_order_status(order.status) not in ("received", "cancelled"):
            order.status = "cancelled"
            order.cancelled_at = now
            db.add(_track(order, "cancelled", notes="Order cancelled by farmer"))
            # A wallet-paid order is refunded when the farmer cancels it.
            if (order.payment_method or "").lower() == "wallet" and order.payment_status == "paid":
                wallet = _wallet_for_user(db, current_user.id)
                if wallet:
                    refund_amount = round(float(order.total_amount or 0), 2)
                    new_balance = round(float(wallet.balance or 0) + refund_amount, 2)
                    db.add(WalletTransaction(
                        transaction_id=generate_id("FA-WTX", db, WalletTransaction),
                        wallet_id=wallet.id,
                        user_id=current_user.id,
                        transaction_type="credit",
                        amount=refund_amount,
                        balance_after=new_balance,
                        description=f"Refund for cancelled order {order.order_id}",
                        reference_id=order.order_id,
                        payment_method="refund",
                        status="completed",
                    ))
                    wallet.balance = new_balance
                order.payment_status = "refunded"
        elif st == "cancelled":
            raise HTTPException(
                status_code=400,
                detail="This order has already been received or cancelled and cannot be cancelled.",
            )
        else:
            # Processing/shipped/out-for-delivery events are recorded by the
            # fulfilment provider as tracking events; a buyer cannot move their
            # own order forward or backward arbitrarily.
            raise HTTPException(
                status_code=403,
                detail="Buyers may only cancel an order. Fulfilment status updates are not permitted.",
            )
    if payment_status:
        valid_pay = ["pending", "paid", "failed", "refunded"]
        if payment_status not in valid_pay:
            raise HTTPException(status_code=400, detail=f"Invalid payment status. Must be one of: {', '.join(valid_pay)}")
        # Payment status must reflect a legitimate payment flow; a buyer cannot
        # self-mark an order as paid or refunded without an actual gateway.
        if payment_status in ("paid", "refunded"):
            raise HTTPException(
                status_code=403,
                detail="Payment confirmation is handled by the payment gateway.",
            )
        if payment_status in ("pending", "failed"):
            order.payment_status = payment_status
    order.updated_at = now
    db.commit()
    db.refresh(order)

    return {
        "status": "success",
        "data": {
            "id": order.id,
            "order_id": order.order_id,
            "status": _norm_order_status(order.status),
            "status_label": ORDER_STATUS_LABELS[_norm_order_status(order.status)],
            "payment_status": order.payment_status,
            "message": "Order cancelled — payment refunded to wallet" if order.status == "cancelled" and order.payment_status == "refunded" else "Order updated successfully",
        },
    }
