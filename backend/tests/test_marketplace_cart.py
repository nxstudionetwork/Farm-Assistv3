import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_marketplace_cart.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.models.marketplace import Product
from app.models.user import User
from app.utils.auth import create_access_token, hash_password


client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def user(session, suffix):
    value = User(
        farmer_id=f"FA-MK-{suffix:08d}", full_name=f"Farmer {suffix}",
        phone_number=f"90000{suffix:05d}", email=f"market{suffix}@example.test",
        password_hash=hash_password("pass123"), is_active=True,
    )
    session.add(value)
    session.commit()
    session.refresh(value)
    return value


def headers(value):
    return {"Authorization": "Bearer " + create_access_token({"sub": value.id, "phone": value.phone_number})}


def test_cart_and_wishlist_are_user_scoped_and_stock_checked():
    session = SessionLocal()
    try:
        first, second = user(session, 1), user(session, 2)
        product = Product(product_id="FA-PRD-MK-1", name="Real database product", price=250, stock_quantity=2, is_active=True)
        session.add(product)
        session.commit()
        session.refresh(product)

        add = client.post("/api/v1/cart", headers=headers(first), json={"product_id": product.id, "quantity": 1})
        assert add.status_code == 200
        assert add.json()["data"]["total"] == 250
        assert client.get("/api/v1/cart", headers=headers(second)).json()["data"]["items"] == []

        too_many = client.patch("/api/v1/cart/" + add.json()["data"]["items"][0]["id"], headers=headers(first), json={"product_id": product.id, "quantity": 3})
        assert too_many.status_code == 409

        assert client.post("/api/v1/wishlist/" + product.id, headers=headers(first)).status_code == 201
        assert len(client.get("/api/v1/wishlist", headers=headers(first)).json()["data"]["items"]) == 1
        assert client.get("/api/v1/wishlist", headers=headers(second)).json()["data"]["items"] == []
    finally:
        session.close()
