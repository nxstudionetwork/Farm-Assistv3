"""Tests for the scalable crop system: taxonomy, catalog, varieties, cycles.

The crop catalog is seeded once for the whole module (it is 129 crops and ~380
varieties) and every test in here reads or extends that state, so the suite stays
fast and deterministic.
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_farm_assist.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.routers.crops import router as crops_router
from app.database.connection import engine, Base, SessionLocal
from app.database.schema_upgrade import run_additive_migrations
from app.database.seed_crops import (
    CULTIVATION_METHODS,
    CROP_CATALOG,
    CROP_TAXONOMY,
    HYDROPONIC_FRIENDLY,
    _consolidate_duplicate_crops,
    seed_crops,
)
from app.models.crop import Crop, CropCategory, CropCycle, CropHealthCheck, CropVariety, CultivationMethod
from app.models.farm import Farm, FarmPlot
from app.models.user import User
from app.utils.auth import hash_password, create_access_token


def build_app() -> FastAPI:
    """Mount only the crop router.

    The crop system has no dependency on the other routers, so the suite builds
    its own app instead of importing the full application. That keeps these tests
    fast and independent of unrelated router modules.
    """
    test_app = FastAPI(title="crop-system-tests")
    test_app.include_router(crops_router, prefix="/api/v1")
    return test_app


client = TestClient(build_app())

# Build the schema once at import time. Several seeder modules are imported
# lazily, so creating tables from a fixture can race with them.
Base.metadata.create_all(bind=engine)
run_additive_migrations(os.environ["DATABASE_URL"])

#: Every agricultural domain the crop system has to cover.
REQUIRED_DOMAINS = {
    "Field Crops",
    "Horticulture",
    "Plantation",
    "Forestry",
}
REQUIRED_CATEGORIES = {
    "Cereals", "Pulses", "Oilseeds", "Fibre Crops", "Cash Crops", "Forage",
    "Vegetables", "Fruits", "Flowers", "Spices", "Medicinal", "Aromatic",
    "Nursery", "Plantation", "Tree Crops", "Silviculture",
}


def _wipe_rows() -> None:
    existing = set(inspect(engine).get_table_names())
    if not existing:
        return
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in existing:
                conn.execute(table.delete())
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")


@pytest.fixture(scope="module")
def catalog():
    """Seed the catalog once and return an open session for direct assertions."""
    _wipe_rows()
    db = SessionLocal()
    try:
        seed_crops(db)
        yield db
    finally:
        db.close()


_COUNTER = [0]


def _next_id() -> int:
    """Unique-per-test suffix so the users table's unique index never clashes."""
    _COUNTER[0] += 1
    return _COUNTER[0]


@pytest.fixture
def farmer(catalog):
    db = SessionLocal()
    user = User(
        full_name="Crop Tester",
        phone_number="9000000%03d" % _next_id(),
        email="crop.tester.%d@example.com" % _next_id(),
        password_hash=hash_password("pass123"),
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    try:
        yield user
    finally:
        db.close()


@pytest.fixture
def headers(farmer):
    token = create_access_token({"sub": farmer.id, "phone": farmer.phone_number})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def farm(headers):
    r = client.post(
        "/api/v1/farms",
        json={"farm_name": "Taxonomy Farm", "total_area": 3, "area_unit": "Acres"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ==================== catalog ====================


def test_taxonomy_covers_every_required_domain():
    domains = {row[1] for row in CROP_TAXONOMY}
    categories = {row[2] for row in CROP_TAXONOMY}
    assert REQUIRED_DOMAINS <= domains
    assert REQUIRED_CATEGORIES <= categories
    # Subcategory nodes keep leafy/root/tuber/gourd vegetables apart.
    subs = {row[3] for row in CROP_TAXONOMY if row[3]}
    assert {"Leafy", "Root", "Tuber", "Gourd", "Viticulture"} <= subs


def test_catalog_entries_are_complete_and_unique():
    codes = [s.code for s in CROP_CATALOG]
    names = [s.name.lower() for s in CROP_CATALOG]
    assert len(codes) == len(set(codes))
    assert len(names) == len(set(names))
    for spec in CROP_CATALOG:
        assert spec.scientific, spec.code
        assert spec.local_names, spec.code
        assert spec.varieties, spec.code
        assert spec.lifecycle, spec.code
        assert spec.life_cycle in {"annual", "perennial", "biennial", "seasonal", "multi_year"}


def test_seeded_catalog_is_complete(catalog):
    assert catalog.query(CropCategory).count() == len(CROP_TAXONOMY)
    assert catalog.query(CultivationMethod).count() == len(CULTIVATION_METHODS)

    active = catalog.query(Crop).filter(Crop.is_archived.is_(False)).all()
    catalogued = [c for c in active if c.is_catalog]
    assert len(catalogued) == len(CROP_CATALOG)

    # No duplicate display names survive consolidation.
    names = [c.name for c in active]
    assert len(names) == len(set(names))

    # Everything is classified and enriched.
    for crop in catalogued:
        assert crop.category_id, crop.name
        assert crop.lifecycle_stages, crop.name
        assert crop.suitable_cultivation_methods, crop.name
        assert [v for v in crop.varieties if v.is_active is not False], crop.name


def test_seeding_twice_changes_nothing(catalog):
    before = catalog.query(Crop).count()
    varieties = catalog.query(CropVariety).count()
    assert seed_crops(catalog) == 0
    assert catalog.query(Crop).count() == before
    assert catalog.query(CropVariety).count() == varieties


def test_existing_farmer_crops_are_classified_not_duplicated(catalog):
    """A pre-existing 'Paddy (Rice)' row is folded into the catalog row."""
    db = SessionLocal()
    try:
        farmer = User(
            full_name="Legacy Farmer",
            phone_number="9000000222",
            email="legacy@example.com",
            password_hash=hash_password("pass123"),
            is_verified=True,
            is_active=True,
        )
        db.add(farmer)
        db.commit()
        db.refresh(farmer)

        farm = Farm(farm_name="Legacy Farm", user_id=farmer.id, total_area=2, area_unit="Acres")
        db.add(farm)
        db.commit()
        db.refresh(farm)

        legacy = Crop(crop_id="FA-CRP-999999", name="Paddy (Rice)", variety="BPT 5204")
        db.add(legacy)
        db.commit()
        db.refresh(legacy)

        cycle = CropCycle(cycle_id="FA-CYC-999999", farm_id=farm.id, crop_id=legacy.id)
        db.add(cycle)
        db.commit()
        cycle_id = cycle.id
        legacy_id = legacy.id
        db.close()

        seed_crops(db)

        db = SessionLocal()
        try:
            merged = db.query(Crop).filter(Crop.name == "Rice", Crop.is_archived.is_(False)).all()
            assert len(merged) == 1
            assert merged[0].is_catalog
            # The farmer's cycle moved to the surviving row; nothing is deleted.
            moved = db.query(CropCycle).filter(CropCycle.id == cycle_id).first()
            assert moved is not None
            assert moved.crop_id == merged[0].id
            archived = db.query(Crop).filter(Crop.id == legacy_id).first()
            assert archived is not None and archived.is_archived
            # The farmer's variety travelled with the crop.
            assert "BPT 5204" in [v.name for v in merged[0].varieties]
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            db.query(Crop).filter(Crop.crop_id == "FA-CRP-999999").delete()
            db.query(CropCycle).filter(CropCycle.cycle_id == "FA-CYC-999999").delete()
            db.query(Farm).filter(Farm.farm_name == "Legacy Farm").delete()
            db.query(User).filter(User.phone_number == "9000000222").delete()
            db.commit()
        finally:
            db.close()


def test_hydroponics_flag_is_explicit(catalog):
    for crop in catalog.query(Crop).filter(Crop.is_archived.is_(False)).all():
        methods = crop.suitable_cultivation_methods or []
        if "hydroponic" in methods:
            assert crop.name.lower().split()[0] in HYDROPONIC_FRIENDLY or crop.crop_id in HYDROPONIC_FRIENDLY


# ==================== catalog API ====================


def test_list_crops_supports_search_and_filters(headers):
    r = client.get("/api/v1/crops", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert len(body["data"]) == body["meta"]["total"]
    assert all("is_archived" in c for c in body["data"])

    by_domain = client.get("/api/v1/crops?domain=Horticulture&page_size=500", headers=headers).json()
    assert by_domain["data"]
    assert all(c["domain"] == "Horticulture" for c in by_domain["data"])

    perennial = client.get("/api/v1/crops?life_cycle_type=perennial&page_size=500", headers=headers).json()
    assert perennial["data"]
    assert all(c["life_cycle_type"] == "perennial" for c in perennial["data"])

    hydro = client.get("/api/v1/crops?cultivation_method=hydroponic&page_size=500", headers=headers).json()
    assert {c["name"] for c in hydro["data"]} <= {"Tomato", "Lettuce", "Spinach", "Cucumber",
                                                  "Capsicum", "Brinjal", "Chilli"}

    leafy = client.get("/api/v1/crops?category_code=horticulture.leafy&page_size=500", headers=headers).json()
    assert {c["subcategory"] for c in leafy["data"]} == {"Leafy"}

    # A parent node also returns its subcategories.
    veggies = client.get("/api/v1/crops?category_code=horticulture.vegetables&page_size=500", headers=headers).json()
    assert len(veggies["data"]) > len(leafy["data"])

    # Search reaches the multilingual local name, not just the English name.
    local = client.get("/api/v1/crops?q=" + "%E0%B0%9F%E0%B0%AE%E0%B0%BE%E0%B0%9F%E0%B1%86", headers=headers).json()
    assert any(c["name"] == "Tomato" for c in local["data"])

    english = client.get("/api/v1/crops?q=grape", headers=headers).json()
    assert any(c["name"] == "Grapes" for c in english["data"])


def test_list_crops_paginates(headers):
    page1 = client.get("/api/v1/crops?page=1&page_size=10", headers=headers).json()
    page2 = client.get("/api/v1/crops?page=2&page_size=10", headers=headers).json()
    assert len(page1["data"]) == 10
    assert page1["meta"]["pages"] >= 2
    assert {c["id"] for c in page1["data"]} & {c["id"] for c in page2["data"]} == set()


def test_archived_crops_are_hidden_by_default(headers):
    db = SessionLocal()
    try:
        crop = db.query(Crop).filter(Crop.is_archived.is_(False)).first()
        crop_id = crop.id
        crop.is_archived = True
        db.commit()
    finally:
        db.close()

    visible = client.get("/api/v1/crops?page_size=500", headers=headers).json()["data"]
    assert crop_id not in {c["id"] for c in visible}

    with_archived = client.get("/api/v1/crops?include_archived=true&page_size=500", headers=headers).json()["data"]
    assert crop_id in {c["id"] for c in with_archived}

    db = SessionLocal()
    try:
        crop = db.query(Crop).filter(Crop.id == crop_id).first()
        crop.is_archived = False
        db.commit()
    finally:
        db.close()


def test_get_crop_by_id_and_code_includes_varieties(headers):
    listed = client.get("/api/v1/crops?q=Grapes", headers=headers).json()["data"]
    grape = next(c for c in listed if c["name"] == "Grapes")

    by_id = client.get(f"/api/v1/crops/{grape['id']}", headers=headers)
    assert by_id.status_code == 200
    detail = by_id.json()["data"]
    assert detail["lifecycle_stages"][0] == "Dormancy"
    assert detail["category_code"] == "horticulture.viticulture"
    assert any(v["name"] == "Thompson Seedless" for v in detail["varieties"])

    by_code = client.get(f"/api/v1/crops/{grape['crop_id']}", headers=headers)
    assert by_code.status_code == 200
    assert by_code.json()["data"]["id"] == grape["id"]

    assert client.get("/api/v1/crops/does-not-exist", headers=headers).status_code == 404


def test_crop_categories_endpoint_returns_tree_with_counts(headers):
    r = client.get("/api/v1/crops/categories", headers=headers)
    assert r.status_code == 200
    body = r.json()
    domains = {d["domain"] for d in body["domains"]}
    assert REQUIRED_DOMAINS <= domains
    grapes = [d for d in body["domains"] if d["domain"] == "Horticulture"][0]
    by_code = {c["code"]: c for c in grapes["categories"]}
    assert "horticulture.fruits" in by_code
    assert "horticulture.viticulture" in by_code
    assert by_code["horticulture.fruits"]["crop_count"] > 0
    assert by_code["horticulture.leafy"]["crop_count"] > 0
    # Only nodes that actually hold crops are returned unless asked otherwise.
    assert all(c["crop_count"] > 0 for c in body["data"] if not c["subcategory"])
    empty = client.get("/api/v1/crops/categories?include_empty=true", headers=headers).json()
    assert len(empty["data"]) > len(body["data"])


def test_cultivation_methods_endpoint(headers):
    r = client.get("/api/v1/crops/cultivation-methods", headers=headers)
    assert r.status_code == 200
    codes = {m["code"] for m in r.json()["data"]}
    assert {"open_field", "soil", "protected", "hydroponic", "orchard"} <= codes
    hydro = next(m for m in r.json()["data"] if m["code"] == "hydroponic")
    assert hydro["is_soil_based"] is False
    assert hydro["is_protected"] is True


def test_crop_endpoints_require_authentication():
    assert client.get("/api/v1/crops").status_code == 401
    assert client.get("/api/v1/crops/categories").status_code == 401
    assert client.get("/api/v1/crop-varieties").status_code == 401


# ==================== varieties ====================


def test_variety_crud(headers):
    r = client.post(
        "/api/v1/crops",
        json={"name": "Test Ridge Crop", "category": "Cereals", "season": "Kharif"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    crop = r.json()["data"]
    assert crop["is_catalog"] is False

    created = client.post(
        "/api/v1/crop-varieties",
        json={"crop_id": crop["id"], "name": "Test Variety 1", "is_hybrid": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    variety = created.json()["data"]
    assert variety["is_custom"] is True
    assert variety["crop_name"] == "Test Ridge Crop"

    duplicate = client.post(
        "/api/v1/crop-varieties",
        json={"crop_id": crop["id"], "name": "test variety 1"},
        headers=headers,
    )
    assert duplicate.status_code == 400

    updated = client.put(
        f"/api/v1/crop-varieties/{variety['id']}",
        json={"duration_days": 95},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["duration_days"] == 95

    listed = client.get(f"/api/v1/crop-varieties?crop_id={crop['id']}", headers=headers).json()
    assert [v["name"] for v in listed["data"]] == ["Test Variety 1"]

    deleted = client.delete(f"/api/v1/crop-varieties/{variety['id']}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/crops/{crop['id']}", headers=headers).json()["data"]["variety_count"] == 0


def test_variety_in_use_is_deactivated_not_deleted(headers, farm):
    rice = next(
        c for c in client.get("/api/v1/crops?q=Rice&page_size=500", headers=headers).json()["data"]
        if c["name"] == "Rice"
    )
    variety = client.get(f"/api/v1/crop-varieties?crop_id={rice['id']}", headers=headers).json()["data"][0]

    created = client.post(
        "/api/v1/crop-cycles",
        json={"farm_id": farm["id"], "crop_id": rice["id"], "variety_id": variety["id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    cycle_id = created.json()["data"]["cycle_id"]
    assert created.json()["data"]["variety_name"] == variety["name"]

    deleted = client.delete(f"/api/v1/crop-varieties/{variety['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deactivated"] is True

    still_there = client.get(
        f"/api/v1/crop-varieties?crop_id={rice['id']}&include_inactive=true", headers=headers
    ).json()["data"]
    assert variety["id"] in {v["id"] for v in still_there}

    cycle = client.get("/api/v1/crop-cycles", headers=headers).json()["data"]
    assert next(c for c in cycle if c["cycle_id"] == cycle_id)["variety_name"] == variety["name"]


# ==================== crop cycles ====================


def test_cycle_records_variety_and_cultivation_method(headers, farm):
    lettuce = next(
        c for c in client.get("/api/v1/crops?q=Lettuce", headers=headers).json()["data"]
        if c["name"] == "Lettuce"
    )
    variety = client.get(
        f"/api/v1/crop-varieties?crop_id={lettuce['id']}", headers=headers
    ).json()["data"][0]

    created = client.post(
        "/api/v1/crop-cycles",
        json={
            "farm_id": farm["id"],
            "crop_id": lettuce["id"],
            "variety": variety["name"],
            "cultivation_method": "hydroponic",
            "protected_structure": "polyhouse",
            "planting_material": "seedling",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    cycle = created.json()["data"]
    assert cycle["cultivation_method"] == "hydroponic"
    assert cycle["cultivation_method_name"] == "Hydroponic"
    assert cycle["protected_structure"] == "polyhouse"
    assert cycle["variety_name"] == variety["name"]
    # The crop's own lifecycle seeds the initial stage.
    assert cycle["current_stage"] in cycle["lifecycle_stages"]

    updated = client.put(
        f"/api/v1/crop-cycles/{cycle['cycle_id']}",
        json={"cultivation_method": "protected", "current_stage": "Harvest"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["cultivation_method"] == "protected"
    assert updated.json()["data"]["current_stage"] == "Harvest"


def test_cycle_rejects_incompatible_variety_method_and_stage(headers, farm):
    lettuce = next(
        c for c in client.get("/api/v1/crops?q=Lettuce", headers=headers).json()["data"]
        if c["name"] == "Lettuce"
    )
    maize = next(
        c for c in client.get("/api/v1/crops?q=Maize&page_size=500", headers=headers).json()["data"]
        if c["name"] == "Maize"
    )
    maize_variety = client.get(
        f"/api/v1/crop-varieties?crop_id={maize['id']}", headers=headers
    ).json()["data"][0]

    wrong_variety = client.post(
        "/api/v1/crop-cycles",
        json={"farm_id": farm["id"], "crop_id": lettuce["id"], "variety_id": maize_variety["id"]},
        headers=headers,
    )
    assert wrong_variety.status_code == 400
    assert "does not belong" in wrong_variety.json()["detail"]

    wrong_method = client.post(
        "/api/v1/crop-cycles",
        json={"farm_id": farm["id"], "crop_id": maize["id"], "cultivation_method": "hydroponic"},
        headers=headers,
    )
    assert wrong_method.status_code == 400
    assert "Supported methods" in wrong_method.json()["detail"]

    wrong_stage = client.post(
        "/api/v1/crop-cycles",
        json={"farm_id": farm["id"], "crop_id": lettuce["id"], "current_stage": "Ripening stage"},
        headers=headers,
    )
    assert wrong_stage.status_code == 400
    assert "Valid stages" in wrong_stage.json()["detail"]


def test_crop_cycles_are_scoped_to_the_farmer(headers, farm, farmer):
    rice = next(
        c for c in client.get("/api/v1/crops?q=Rice&page_size=500", headers=headers).json()["data"]
        if c["name"] == "Rice"
    )
    created = client.post(
        "/api/v1/crop-cycles",
        json={"farm_id": farm["id"], "crop_id": rice["id"]},
        headers=headers,
    ).json()["data"]

    db = SessionLocal()
    try:
        intruder = User(
            full_name="Other Farmer",
            phone_number="9000000333",
            email="other@example.com",
            password_hash=hash_password("pass123"),
            is_verified=True,
            is_active=True,
        )
        db.add(intruder)
        db.commit()
        db.refresh(intruder)
    finally:
        db.close()

    other_token = create_access_token({"sub": intruder.id, "phone": intruder.phone_number})
    other_headers = {"Authorization": f"Bearer {other_token}"}

    assert client.get("/api/v1/crop-cycles", headers=other_headers).json()["data"] == []
    assert client.put(
        f"/api/v1/crop-cycles/{created['cycle_id']}", json={"notes": "hack"}, headers=other_headers
    ).status_code == 403
    assert client.delete(
        f"/api/v1/crop-cycles/{created['cycle_id']}", headers=other_headers
    ).status_code == 403

    db = SessionLocal()
    try:
        db.query(User).filter(User.id == intruder.id).delete()
        db.commit()
    finally:
        db.close()


def test_task_suggestions_follow_the_crop_lifecycle(headers, farm):
    """A perennial crop gets its own stage-driven advice, not seedling tasks."""
    grape = next(
        c for c in client.get("/api/v1/crops?q=Grapes", headers=headers).json()["data"]
        if c["name"] == "Grapes"
    )
    created = client.post(
        "/api/v1/crop-cycles",
        json={"farm_id": farm["id"], "crop_id": grape["id"], "current_stage": "Dormancy"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    cycle_id = created.json()["data"]["cycle_id"]

    suggestions = client.get("/api/v1/crop-tasks/ai-suggest", headers=headers).json()["data"]["suggestions"]
    mine = [s for s in suggestions if s["crop_cycle_id"] == created.json()["data"]["id"]]
    assert mine, "expected suggestions for the grape cycle"
    assert any("prune" in s["title"].lower() for s in mine), [s["title"] for s in mine]
    assert all(s["growth_stage"] == "Dormancy" for s in mine if s["source"] == "crop_stage")

    generated = client.post("/api/v1/crop-tasks/generate", headers=headers)
    assert generated.status_code == 201, generated.text
    assert generated.json()["data"]["created_count"] > 0

    # Running it again does not duplicate the tasks.
    again = client.post("/api/v1/crop-tasks/generate", headers=headers).json()
    assert again["data"]["created_count"] == 0

    assert client.get("/api/v1/crop-cycles", headers=headers).json()["data"]
    assert cycle_id


def test_create_crop_mirrors_the_free_text_variety(headers):
    r = client.post(
        "/api/v1/crops",
        json={"name": "Heritage Millet", "variety": "Local Millet", "category": "Cereals"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    crop = r.json()["data"]
    assert crop["variety"] == "Local Millet"
    assert [v["name"] for v in crop["varieties"]] == ["Local Millet"]


def test_consolidation_re_points_health_checks(headers, farmer):
    """A health check recorded against a duplicate crop follows the kept row."""
    db = SessionLocal()
    try:
        farm = Farm(farm_name="Health Check Farm", user_id=farmer.id, total_area=1, area_unit="Acres")
        db.add(farm)
        db.commit()
        db.refresh(farm)

        keep = Crop(crop_id="FA-CRP-HC-1", name="Sorghum", variety="Local")
        dup = Crop(crop_id="FA-CRP-HC-2", name="Sorghum", variety="Local")
        db.add_all([keep, dup])
        db.commit()
        db.refresh(keep)
        db.refresh(dup)

        check = CropHealthCheck(
            check_id="FA-CHK-HC-1",
            user_id=farmer.id,
            farm_id=farm.id,
            crop_id=dup.id,
            stage="Flowering",
        )
        db.add(check)
        db.commit()
        dup_id, keep_id = dup.id, keep.id
        db.close()

        db = SessionLocal()
        try:
            _consolidate_duplicate_crops(db)
            active = [
                c for c in db.query(Crop)
                .filter(Crop.crop_id.in_(["FA-CRP-HC-1", "FA-CRP-HC-2"]))
                .all()
                if not c.is_archived
            ]
            # Exactly one row survives, and it is the one holding the activity.
            assert len(active) == 1
            assert active[0].crop_id == "FA-CRP-HC-2"
            moved = db.query(CropHealthCheck).filter(CropHealthCheck.check_id == "FA-CHK-HC-1").first()
            assert moved is not None
            assert moved.crop_id == active[0].id
            # Nothing was deleted.
            assert db.query(Crop).filter(
                Crop.crop_id.in_(["FA-CRP-HC-1", "FA-CRP-HC-2"])
            ).count() == 2
            # The merged crop kept one variety, not two copies of "Local".
            assert sorted(v.name for v in active[0].varieties) == ["Local"]
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            db.query(CropHealthCheck).filter(CropHealthCheck.check_id == "FA-CHK-HC-1").delete()
            db.query(Crop).filter(Crop.crop_id.in_(["FA-CRP-HC-1", "FA-CRP-HC-2"])).delete()
            db.query(Farm).filter(Farm.farm_name == "Health Check Farm").delete()
            db.commit()
        finally:
            db.close()
