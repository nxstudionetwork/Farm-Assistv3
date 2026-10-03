import asyncio
import json
import re
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_, case, func, cast, select, Text

from app.database.connection import get_db
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import (
    Crop,
    CropCategory,
    CropCycle,
    CropTask,
    CropVariety,
    CultivationMethod,
    FarmJournal,
)
from app.utils.auth import get_current_user, generate_id

TASK_STATUSES = ["pending", "in_progress", "completed"]
TASK_PRIORITIES = ["low", "medium", "high"]

#: Sorted last so a farmer's own row always stays visible next to its catalog row.
CROP_SORT = (Crop.is_catalog, Crop.name)

router = APIRouter(prefix="/api/v1", tags=["Crops"])


class CropCreateRequest(BaseModel):
    name: str
    variety: Optional[str] = None
    category: Optional[str] = None
    season: Optional[str] = None
    growth_duration_days: Optional[float] = None
    # --- scalable taxonomy (all optional, existing clients are unaffected) ---
    domain: Optional[str] = None
    subcategory: Optional[str] = None
    category_code: Optional[str] = None
    scientific_name: Optional[str] = None
    local_names: Optional[dict] = None
    life_cycle_type: Optional[str] = None
    suitable_seasons: Optional[str] = None
    suitable_climate: Optional[str] = None
    suitable_soil_types: Optional[str] = None
    water_requirement: Optional[str] = None
    harvest_type: Optional[str] = None
    production_unit: Optional[str] = None
    market_type: Optional[str] = None
    lifecycle_stages: Optional[List[str]] = None
    suitable_cultivation_methods: Optional[List[str]] = None


class CropUpdateRequest(BaseModel):
    name: Optional[str] = None
    variety: Optional[str] = None
    category: Optional[str] = None
    season: Optional[str] = None
    growth_duration_days: Optional[float] = None
    domain: Optional[str] = None
    subcategory: Optional[str] = None
    category_code: Optional[str] = None
    scientific_name: Optional[str] = None
    local_names: Optional[dict] = None
    life_cycle_type: Optional[str] = None
    suitable_seasons: Optional[str] = None
    suitable_climate: Optional[str] = None
    suitable_soil_types: Optional[str] = None
    water_requirement: Optional[str] = None
    harvest_type: Optional[str] = None
    production_unit: Optional[str] = None
    market_type: Optional[str] = None
    storage_notes: Optional[str] = None
    lifecycle_stages: Optional[List[str]] = None
    suitable_cultivation_methods: Optional[List[str]] = None
    is_archived: Optional[bool] = None


class CropVarietyCreateRequest(BaseModel):
    crop_id: str
    name: str = Field(min_length=1, max_length=150)
    local_name: Optional[str] = None
    is_hybrid: Optional[bool] = False
    duration_days: Optional[float] = None


class CropVarietyUpdateRequest(BaseModel):
    name: Optional[str] = None
    local_name: Optional[str] = None
    is_hybrid: Optional[bool] = None
    duration_days: Optional[float] = None
    is_active: Optional[bool] = None


class CropCycleCreateRequest(BaseModel):
    farm_id: str
    plot_id: Optional[str] = None
    crop_id: str
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    seed_quantity: Optional[float] = None
    seed_unit: Optional[str] = None
    fertilizer_usage: Optional[str] = None
    pesticide_usage: Optional[str] = None
    irrigation_schedule: Optional[str] = None
    notes: Optional[str] = None
    # --- variety / cultivation method -------------------------------------
    variety_id: Optional[str] = None
    variety: Optional[str] = None
    cultivation_method_id: Optional[str] = None
    cultivation_method: Optional[str] = None
    protected_structure: Optional[str] = None
    planting_material: Optional[str] = None
    current_stage: Optional[str] = None


class CropCycleUpdateRequest(BaseModel):
    plot_id: Optional[str] = None
    crop_id: Optional[str] = None
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    actual_harvest_date: Optional[str] = None
    current_stage: Optional[str] = None
    seed_quantity: Optional[float] = None
    seed_unit: Optional[str] = None
    fertilizer_usage: Optional[str] = None
    pesticide_usage: Optional[str] = None
    irrigation_schedule: Optional[str] = None
    yield_quantity: Optional[float] = None
    yield_unit: Optional[str] = None
    revenue: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    variety_id: Optional[str] = None
    variety: Optional[str] = None
    cultivation_method_id: Optional[str] = None
    cultivation_method: Optional[str] = None
    protected_structure: Optional[str] = None
    planting_material: Optional[str] = None


class CropTaskCreateRequest(BaseModel):
    crop_cycle_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: Optional[str] = "medium"
    source: Optional[str] = None
    growth_stage: Optional[str] = None


class CropTaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class JournalCreateRequest(BaseModel):
    farm_id: Optional[str] = None
    plot_id: Optional[str] = None
    activity: str
    notes: Optional[str] = None


def _variety_dict(variety: CropVariety) -> dict:
    return {
        "id": variety.id,
        "crop_id": variety.crop_id,
        "crop_name": variety.crop.name if variety.crop else None,
        "name": variety.name,
        "local_name": variety.local_name,
        "is_hybrid": bool(variety.is_hybrid),
        "duration_days": variety.duration_days,
        "is_custom": bool(variety.is_custom),
        "is_active": bool(variety.is_active) if variety.is_active is not None else True,
        "created_at": str(variety.created_at) if variety.created_at else None,
    }


def _method_dict(method: CultivationMethod) -> dict:
    return {
        "id": method.id,
        "code": method.code,
        "name": method.name,
        "is_soil_based": bool(method.is_soil_based),
        "is_protected": bool(method.is_protected),
        "description": method.description,
        "sort_order": method.sort_order,
    }


def _category_dict(node: CropCategory, crop_count: int = 0) -> dict:
    return {
        "id": node.id,
        "code": node.code,
        "domain": node.domain,
        "category": node.category,
        "subcategory": node.subcategory,
        "display_name": node.display_name or node.category or node.code,
        "description": node.description,
        "icon": node.icon,
        "sort_order": node.sort_order,
        "crop_count": crop_count,
        #: True when this node is a parent category whose crops are filed under
        #: its subcategories. Clients that filter locally need this to include
        #: the whole slice, matching the API's own ``category_code`` behaviour.
        "is_parent": node.subcategory is None,
    }


def _crop_dict(crop: Crop, include_varieties: bool = False) -> dict:
    """Serialise a crop.

    The original seven keys are unchanged so existing clients keep working; the
    taxonomy, lifecycle and cultivation metadata is additive.
    """
    varieties = [v for v in (crop.varieties or []) if v.is_active is not False]
    data = {
        "id": crop.id,
        "crop_id": crop.crop_id,
        "name": crop.name,
        "variety": crop.variety,
        "category": crop.category,
        "season": crop.season,
        "growth_duration_days": crop.growth_duration_days,
        # --- taxonomy --------------------------------------------------------
        "domain": crop.domain,
        "subcategory": crop.subcategory,
        "category_code": crop.category_ref.code if crop.category_ref else None,
        "category_name": crop.category_ref.display_name if crop.category_ref else None,
        # --- agronomy --------------------------------------------------------
        "scientific_name": crop.scientific_name,
        "local_names": crop.local_names or {},
        "life_cycle_type": crop.life_cycle_type,
        "suitable_seasons": crop.suitable_seasons,
        "suitable_climate": crop.suitable_climate,
        "suitable_soil_types": crop.suitable_soil_types,
        "water_requirement": crop.water_requirement,
        "harvest_type": crop.harvest_type,
        "production_unit": crop.production_unit,
        "market_type": crop.market_type,
        "storage_notes": crop.storage_notes,
        "lifecycle_stages": crop.lifecycle_stages or [],
        "suitable_cultivation_methods": crop.suitable_cultivation_methods or [],
        "hydroponic_targets": crop.hydroponic_targets,
        # --- bookkeeping -----------------------------------------------------
        "is_catalog": bool(crop.is_catalog),
        "is_archived": bool(crop.is_archived),
        "variety_count": len(varieties),
    }
    if include_varieties:
        data["varieties"] = [_variety_dict(v) for v in varieties]
    return data


def _cycle_dict(cycle: CropCycle) -> dict:
    crop = cycle.crop
    method = cycle.cultivation_method
    return {
        "id": cycle.id,
        "cycle_id": cycle.cycle_id,
        "farm_id": cycle.farm_id,
        "farm_name": cycle.farm.farm_name if cycle.farm else None,
        "plot_id": cycle.plot_id,
        "plot_name": cycle.plot.plot_name if cycle.plot else None,
        "crop_id": cycle.crop_id,
        "crop_name": crop.name if crop else None,
        "sowing_date": cycle.sowing_date,
        "expected_harvest_date": cycle.expected_harvest_date,
        "actual_harvest_date": cycle.actual_harvest_date,
        "current_stage": cycle.current_stage,
        "lifecycle_stages": (crop.lifecycle_stages or []) if crop else [],
        "seed_quantity": cycle.seed_quantity,
        "seed_unit": cycle.seed_unit,
        "fertilizer_usage": cycle.fertilizer_usage,
        "pesticide_usage": cycle.pesticide_usage,
        "irrigation_schedule": cycle.irrigation_schedule,
        "yield_quantity": cycle.yield_quantity,
        "yield_unit": cycle.yield_unit,
        "revenue": cycle.revenue,
        "notes": cycle.notes,
        "status": cycle.status,
        # --- variety / cultivation method -----------------------------------
        "variety_id": cycle.variety_id,
        "variety_name": cycle.variety.name if cycle.variety else None,
        "cultivation_method_id": cycle.cultivation_method_id,
        "cultivation_method": method.code if method else None,
        "cultivation_method_name": method.name if method else None,
        "protected_structure": cycle.protected_structure,
        "planting_material": cycle.planting_material,
        "created_at": str(cycle.created_at) if cycle.created_at else None,
    }


def _task_dict(task: CropTask) -> dict:
    cycle = task.crop_cycle
    return {
        "id": task.id,
        "task_id": task.task_id,
        "crop_cycle_id": task.crop_cycle_id,
        "cycle_id": cycle.cycle_id if cycle else None,
        "farm_id": cycle.farm_id if cycle else None,
        "farm_name": cycle.farm.farm_name if cycle and cycle.farm else None,
        "plot_id": cycle.plot_id if cycle else None,
        "plot_name": cycle.plot.plot_name if cycle and cycle.plot else None,
        "crop_id": cycle.crop_id if cycle else None,
        "crop_name": cycle.crop.name if cycle and cycle.crop else None,
        "title": task.title,
        "description": task.description,
        "category": task.category,
        "due_date": task.due_date,
        "due_time": task.due_time,
        "status": task.status,
        "priority": task.priority,
        "source": task.source,
        "growth_stage": task.growth_stage,
        "completed_at": str(task.completed_at) if task.completed_at else None,
        "created_at": str(task.created_at) if task.created_at else None,
    }


def _journal_dict(entry: FarmJournal) -> dict:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "farm_id": entry.farm_id,
        "plot_id": entry.plot_id,
        "activity": entry.activity,
        "notes": entry.notes,
        "entry_date": str(entry.entry_date) if entry.entry_date else None,
        "created_at": str(entry.created_at) if entry.created_at else None,
    }


def _get_user_farm_ids(db: Session, user_id: str) -> List[str]:
    farms = db.query(Farm.id).filter(Farm.user_id == user_id, Farm.is_active == True).all()
    return [f.id for f in farms]


def _verify_cycle_ownership(db: Session, cycle_id: str, user_id: str) -> CropCycle:
    cycle = db.query(CropCycle).filter(CropCycle.cycle_id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    farm = db.query(Farm).filter(Farm.id == cycle.farm_id, Farm.user_id == user_id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized")
    return cycle


def _find_crop(db: Session, crop_ref: str) -> Optional[Crop]:
    """Look a crop up by either its internal id or its public ``crop_id``.

    Every crop endpoint accepts both forms; resolving one way only is what let
    a cycle be created with the wrong crop (or fail outright) depending on which
    reference the client happened to hold.
    """
    if not crop_ref or not str(crop_ref).strip():
        return None
    ref = str(crop_ref).strip()
    return db.query(Crop).filter(or_(Crop.id == ref, Crop.crop_id == ref)).first()


def _resolve_category(db: Session, category_code: Optional[str]):
    if not category_code:
        return None
    node = db.query(CropCategory).filter(CropCategory.code == category_code).first()
    if not node:
        raise HTTPException(
            status_code=404,
            detail="Crop category '%s' not found" % category_code,
        )
    return node


def _resolve_variety(db: Session, crop: Crop, variety_id=None, variety_name=None):
    """Accept a variety id or a variety name and return the row to record.

    A name is only ever looked up inside the crop's own varieties, so two crops
    can share a variety name without being confused.
    """
    if variety_id:
        row = db.query(CropVariety).filter(CropVariety.id == variety_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Crop variety not found")
        if row.crop_id != crop.id:
            raise HTTPException(
                status_code=400,
                detail="Variety '%s' does not belong to crop '%s'" % (row.name, crop.name),
            )
        return row
    if variety_name and str(variety_name).strip():
        term = str(variety_name).strip()
        row = (
            db.query(CropVariety)
            .filter(
                CropVariety.crop_id == crop.id,
                func.lower(CropVariety.name) == term.lower(),
            )
            .first()
        )
        if not row:
            # An unknown name is a farmer's own variety, not an error.
            row = CropVariety(
                crop_id=crop.id,
                name=term,
                duration_days=crop.growth_duration_days,
                is_custom=True,
            )
            db.add(row)
            db.flush()
        return row
    return None


def _resolve_method(db: Session, crop: Crop, method_id=None, method_code=None):
    if method_id:
        method = db.query(CultivationMethod).filter(CultivationMethod.id == method_id).first()
        if not method:
            raise HTTPException(status_code=404, detail="Cultivation method not found")
    elif method_code and str(method_code).strip():
        method = (
            db.query(CultivationMethod)
            .filter(CultivationMethod.code == str(method_code).strip())
            .first()
        )
        if not method:
            raise HTTPException(
                status_code=404,
                detail="Cultivation method '%s' not found" % method_code,
            )
    else:
        return None

    supported = crop.suitable_cultivation_methods or []
    if supported and method.code not in supported:
        raise HTTPException(
            status_code=400,
            detail=(
                "'%s' is not normally grown as %s. Supported methods: %s"
                % (crop.name, method.name, ", ".join(supported))
            ),
        )
    return method


def _validate_stage(crop: Crop, stage: Optional[str]) -> Optional[str]:
    """Reject a lifecycle stage the crop does not have, with the valid list."""
    if not stage:
        return None
    stages = crop.lifecycle_stages or []
    if not stages:
        return stage
    if not any(str(stage).strip().lower() == str(s).strip().lower() for s in stages):
        raise HTTPException(
            status_code=400,
            detail=(
                "'%s' is not a lifecycle stage of %s. Valid stages: %s"
                % (stage, crop.name, ", ".join(stages))
            ),
        )
    return stage


def _json_search_patterns(value: str) -> List[str]:
    """LIKE patterns that can match a JSON text column for this search term.

    ``local_names`` is a JSON object written through ``json.dumps``, which
    escapes every non-ASCII character, so a Telugu name is on disk as
    ``\\u0c2f...``. Substring matching the raw text can therefore never find it.
    Databases that keep JSON as real UTF-8 (PostgreSQL) need the raw form
    instead, so both are searched and whichever one the column actually holds
    wins.
    """
    text_value = str(value).strip()
    patterns = ["%%%s%%" % text_value]
    escaped = json.dumps(text_value, ensure_ascii=True)[1:-1]
    if escaped != text_value:
        patterns.append("%%%s%%" % escaped)
    return patterns


@router.get("/crops", response_model=dict)
def list_crops(
    q: Optional[str] = None,
    domain: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    category_code: Optional[str] = None,
    life_cycle_type: Optional[str] = None,
    cultivation_method: Optional[str] = None,
    season: Optional[str] = None,
    include_archived: bool = False,
    include_varieties: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List crops from the shared catalog.

    ``data`` stays a plain array of crop objects so existing clients keep
    working; the new filters and the ``meta`` block are additive.
    """
    qry = db.query(Crop).options(selectinload(Crop.varieties), selectinload(Crop.category_ref))

    if not include_archived:
        qry = qry.filter(Crop.is_archived.is_(False))

    if q and str(q).strip():
        term = "%%%s%%" % str(q).strip()
        qry = qry.filter(
            or_(
                Crop.name.ilike(term),
                Crop.scientific_name.ilike(term),
                Crop.crop_id.ilike(term),
                Crop.market_type.ilike(term),
                Crop.variety.ilike(term),
                Crop.category.ilike(term),
                Crop.domain.ilike(term),
                Crop.subcategory.ilike(term),
                # ``local_names`` is a JSON object such as {"te": "టమాటో"}.
                # Casting to text lets the serialised value be substring
                # matched, which is what makes a Telugu/Hindi search reach the
                # crop instead of returning nothing. Without this the whole OR
                # above evaluated false for a local name and the search died.
                # Both the raw and the JSON-escaped spelling are tried, because
                # how the text is stored depends on the database.
                *[
                    cast(Crop.local_names, Text).ilike(pattern)
                    for pattern in _json_search_patterns(q)
                ],
                # A variety name is a row of its own, so a variety search has to
                # reach back to the crop that owns it.
                Crop.id.in_(
                    select(CropVariety.crop_id).where(CropVariety.name.ilike(term))
                ),
            )
        )
    if domain:
        qry = qry.filter(Crop.domain == domain)
    if category:
        qry = qry.filter(Crop.category == category)
    if subcategory:
        qry = qry.filter(Crop.subcategory == subcategory)
    if category_code:
        node = db.query(CropCategory).filter(CropCategory.code == category_code).first()
        if not node:
            return {"status": "success", "data": [], "meta": _empty_meta(page, page_size)}
        if node.subcategory:
            # A subcategory node is a specific slice, so only its own crops.
            node_ids = [node.id]
        else:
            # A parent node also returns the crops filed under its subcategories.
            node_ids = [
                c.id
                for c in db.query(CropCategory).filter(
                    CropCategory.domain == node.domain,
                    CropCategory.category == node.category,
                ).all()
            ]
        qry = qry.filter(Crop.category_id.in_(node_ids))
    if life_cycle_type:
        qry = qry.filter(Crop.life_cycle_type == life_cycle_type)
    if season:
        qry = qry.filter(Crop.suitable_seasons.ilike("%%%s%%" % str(season).strip()))
    if cultivation_method and str(cultivation_method).strip():
        # ``suitable_cultivation_methods`` is a JSON array, so it is matched as
        # a quoted token against the serialised value. Quoting both sides keeps
        # "soil" from matching "open_field". This has to happen in SQL: doing it
        # after the page window silently dropped matches and made `meta.total`
        # disagree with `data`.
        wanted = str(cultivation_method).strip()
        qry = qry.filter(
            cast(Crop.suitable_cultivation_methods, Text).ilike('%%"%s"%%' % wanted)
        )

    total = qry.count()
    rows = (
        qry.order_by(*CROP_SORT)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "status": "success",
        "data": [_crop_dict(c, include_varieties) for c in rows],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


def _empty_meta(page: int, page_size: int) -> dict:
    return {"page": page, "page_size": page_size, "total": 0, "pages": 0}


@router.get("/crops/categories", response_model=dict)
def list_crop_categories(
    q: Optional[str] = None,
    domain: Optional[str] = None,
    include_empty: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Taxonomy tree with crop counts, used to build grouped selectors."""
    counts = dict(
        db.query(Crop.category_id, func.count(Crop.id))
        .filter(Crop.is_archived.is_(False))
        .group_by(Crop.category_id)
        .all()
    )

    qry = db.query(CropCategory).filter(CropCategory.is_active.isnot(False))
    if domain:
        qry = qry.filter(CropCategory.domain == domain)

    nodes = qry.order_by(CropCategory.sort_order, CropCategory.category, CropCategory.subcategory).all()
    out = []
    for node in nodes:
        count = counts.get(node.id, 0)
        if not include_empty and not count and node.subcategory is None:
            continue
        if q and str(q).strip():
            needle = str(q).strip().lower()
            haystack = " ".join(
                str(x or "") for x in (node.code, node.display_name, node.category, node.subcategory)
            ).lower()
            if needle not in haystack:
                continue
        out.append(_category_dict(node, count))

    domains = []
    for name in sorted({n.domain for n in nodes if n.domain}):
        domain_nodes = [n for n in nodes if n.domain == name]
        domains.append(
            {
                "domain": name,
                "crop_count": sum(counts.get(n.id, 0) for n in domain_nodes),
                "categories": [
                    _category_dict(n, counts.get(n.id, 0))
                    for n in sorted(
                        domain_nodes,
                        key=lambda n: (n.category or "", n.sort_order or 0, n.subcategory or ""),
                    )
                ],
            }
        )

    return {"status": "success", "data": out, "domains": domains}


@router.get("/crops/cultivation-methods", response_model=dict)
def list_cultivation_methods(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    methods = (
        db.query(CultivationMethod)
        .filter(CultivationMethod.is_active.isnot(False))
        .order_by(CultivationMethod.sort_order, CultivationMethod.name)
        .all()
    )
    return {"status": "success", "data": [_method_dict(m) for m in methods]}


@router.get("/crops/{crop_ref}", response_model=dict)
def get_crop(
    crop_ref: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crop = (
        db.query(Crop)
        .options(selectinload(Crop.varieties), selectinload(Crop.category_ref))
        .filter(or_(Crop.id == crop_ref, Crop.crop_id == crop_ref))
        .first()
    )
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")
    return {"status": "success", "data": _crop_dict(crop, include_varieties=True)}


@router.post("/crops", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop(
    payload: CropCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = _resolve_category(db, payload.category_code)

    crop = Crop(
        crop_id=generate_id("FA-CRP", db, Crop),
        name=payload.name,
        variety=payload.variety,
        category=payload.category or (node.category if node else None),
        season=payload.season,
        growth_duration_days=payload.growth_duration_days,
        domain=payload.domain or (node.domain if node else None),
        subcategory=payload.subcategory or (node.subcategory if node else None),
        category_id=node.id if node else None,
        scientific_name=payload.scientific_name,
        local_names=payload.local_names,
        life_cycle_type=payload.life_cycle_type,
        suitable_seasons=payload.suitable_seasons or payload.season,
        suitable_climate=payload.suitable_climate,
        suitable_soil_types=payload.suitable_soil_types,
        water_requirement=payload.water_requirement,
        harvest_type=payload.harvest_type,
        production_unit=payload.production_unit,
        market_type=payload.market_type,
        lifecycle_stages=list(payload.lifecycle_stages) if payload.lifecycle_stages else None,
        suitable_cultivation_methods=(
            list(payload.suitable_cultivation_methods)
            if payload.suitable_cultivation_methods
            else None
        ),
        is_catalog=False,
    )
    db.add(crop)
    db.flush()

    # A free-text variety on create becomes a real variety row, so the farmer
    # never has to choose between the legacy column and the new table.
    if payload.variety and str(payload.variety).strip():
        db.add(
            CropVariety(
                crop_id=crop.id,
                name=str(payload.variety).strip(),
                duration_days=crop.growth_duration_days,
                is_custom=True,
            )
        )

    db.commit()
    db.refresh(crop)

    return {
        "status": "success",
        "message": "Crop created successfully",
        "data": _crop_dict(crop, include_varieties=True),
    }


@router.put("/crops/{crop_ref}", response_model=dict)
def update_crop(
    crop_ref: str,
    payload: CropUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crop = (
        db.query(Crop)
        .filter(or_(Crop.id == crop_ref, Crop.crop_id == crop_ref))
        .first()
    )
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    data = payload.model_dump(exclude_unset=True)
    category_code = data.pop("category_code", None)
    if category_code is not None:
        node = _resolve_category(db, category_code)
        crop.category_id = node.id if node else None
        crop.domain = node.domain if node else None
        crop.category = node.category if node else None
        crop.subcategory = node.subcategory if node else None

    for field, value in data.items():
        setattr(crop, field, value)

    db.commit()
    db.refresh(crop)

    return {
        "status": "success",
        "message": "Crop updated successfully",
        "data": _crop_dict(crop, include_varieties=True),
    }


# ==================== Varieties ====================


@router.get("/crop-varieties", response_model=dict)
def list_crop_varieties(
    crop_id: Optional[str] = None,
    q: Optional[str] = None,
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    qry = db.query(CropVariety).options(selectinload(CropVariety.crop))
    if crop_id:
        crop = (
            db.query(Crop)
            .filter(or_(Crop.id == crop_id, Crop.crop_id == crop_id))
            .first()
        )
        if not crop:
            raise HTTPException(status_code=404, detail="Crop not found")
        qry = qry.filter(CropVariety.crop_id == crop.id)
    if not include_inactive:
        qry = qry.filter(CropVariety.is_active.isnot(False))
    if q and str(q).strip():
        qry = qry.filter(CropVariety.name.ilike("%%%s%%" % str(q).strip()))

    total = qry.count()
    rows = (
        qry.order_by(CropVariety.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "status": "success",
        "data": [_variety_dict(v) for v in rows],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


@router.post("/crop-varieties", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop_variety(
    payload: CropVarietyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crop = (
        db.query(Crop)
        .filter(or_(Crop.id == payload.crop_id, Crop.crop_id == payload.crop_id))
        .first()
    )
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    name = str(payload.name).strip()
    existing = (
        db.query(CropVariety)
        .filter(CropVariety.crop_id == crop.id, func.lower(CropVariety.name) == name.lower())
        .first()
    )
    if existing:
        if existing.is_active is False:
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            return {
                "status": "success",
                "message": "Variety re-activated",
                "data": _variety_dict(existing),
            }
        raise HTTPException(
            status_code=400,
            detail="Variety '%s' already exists for %s" % (name, crop.name),
        )

    variety = CropVariety(
        crop_id=crop.id,
        name=name,
        local_name=payload.local_name,
        is_hybrid=bool(payload.is_hybrid),
        duration_days=payload.duration_days or crop.growth_duration_days,
        is_custom=True,
    )
    db.add(variety)
    db.commit()
    db.refresh(variety)

    return {
        "status": "success",
        "message": "Variety added successfully",
        "data": _variety_dict(variety),
    }


@router.put("/crop-varieties/{variety_id}", response_model=dict)
def update_crop_variety(
    variety_id: str,
    payload: CropVarietyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    variety = db.query(CropVariety).filter(CropVariety.id == variety_id).first()
    if not variety:
        raise HTTPException(status_code=404, detail="Variety not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(variety, field, value)

    db.commit()
    db.refresh(variety)

    return {
        "status": "success",
        "message": "Variety updated successfully",
        "data": _variety_dict(variety),
    }


@router.delete("/crop-varieties/{variety_id}", response_model=dict)
def delete_crop_variety(
    variety_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a variety.

    A variety used by a crop cycle is never removed, only deactivated, so an
    existing cycle keeps reporting the variety it was recorded with.
    """
    variety = db.query(CropVariety).filter(CropVariety.id == variety_id).first()
    if not variety:
        raise HTTPException(status_code=404, detail="Variety not found")

    in_use = db.query(CropCycle).filter(CropCycle.variety_id == variety.id).count()
    if in_use:
        variety.is_active = False
        db.commit()
        return {
            "status": "success",
            "message": (
                "Variety is used by %d crop cycle(s), so it was deactivated "
                "instead of deleted." % in_use
            ),
            "data": {"id": variety.id, "is_active": False, "deactivated": True},
        }

    db.delete(variety)
    db.commit()
    return {
        "status": "success",
        "message": "Variety deleted successfully",
        "data": {"id": variety_id, "deactivated": False},
    }


@router.get("/crop-cycles", response_model=dict)
def list_crop_cycles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_ids = _get_user_farm_ids(db, current_user.id)
    cycles = db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all()
    return {
        "status": "success",
        "data": [_cycle_dict(c) for c in cycles],
    }


@router.post("/crop-cycles", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop_cycle(
    payload: CropCycleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = db.query(Farm).filter(Farm.id == payload.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    crop = _find_crop(db, payload.crop_id)
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    if payload.plot_id:
        plot = db.query(FarmPlot).filter(FarmPlot.id == payload.plot_id, FarmPlot.farm_id == farm.id).first()
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found in this farm")

    variety = _resolve_variety(db, crop, payload.variety_id, payload.variety)
    method = _resolve_method(
        db, crop, payload.cultivation_method_id, payload.cultivation_method
    )
    stage = _validate_stage(crop, payload.current_stage)
    if not stage and crop.lifecycle_stages:
        stage = crop.lifecycle_stages[0]

    cycle_id = generate_id("FA-CYC", db, CropCycle)

    cycle = CropCycle(
        cycle_id=cycle_id,
        farm_id=payload.farm_id,
        plot_id=payload.plot_id,
        # The resolved row's internal id, not the caller's reference: a cycle
        # created with the public `crop_id` used to store that value in a
        # foreign key that points at `crops.id`.
        crop_id=crop.id,
        sowing_date=payload.sowing_date,
        expected_harvest_date=payload.expected_harvest_date,
        seed_quantity=payload.seed_quantity,
        seed_unit=payload.seed_unit,
        fertilizer_usage=payload.fertilizer_usage,
        pesticide_usage=payload.pesticide_usage,
        irrigation_schedule=payload.irrigation_schedule,
        notes=payload.notes,
        variety_id=variety.id if variety else None,
        cultivation_method_id=method.id if method else None,
        protected_structure=payload.protected_structure,
        planting_material=payload.planting_material,
        current_stage=stage,
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)

    return {
        "status": "success",
        "message": "Crop cycle created successfully",
        "data": _cycle_dict(cycle),
    }


@router.put("/crop-cycles/{cycle_id}", response_model=dict)
def update_crop_cycle(
    cycle_id: str,
    payload: CropCycleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = _verify_cycle_ownership(db, cycle_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] == "completed":
        cycle.actual_harvest_date = cycle.actual_harvest_date or datetime.utcnow().strftime("%Y-%m-%d")

    # Variety, method and stage are validated against the cycle's crop so a
    # cycle can never end up with, say, a rice variety on a grape crop.
    variety_id = update_data.pop("variety_id", None)
    variety_name = update_data.pop("variety", None)
    method_id = update_data.pop("cultivation_method_id", None)
    method_code = update_data.pop("cultivation_method", None)

    crop = None
    if "crop_id" in update_data and update_data["crop_id"] != cycle.crop_id:
        crop = _find_crop(db, update_data["crop_id"])
        if not crop:
            raise HTTPException(status_code=404, detail="Crop not found")
        update_data["crop_id"] = crop.id
    crop = crop or cycle.crop
    sent = payload.model_fields_set or set()

    if "variety_id" in sent or ("variety" in sent and str(variety_name or "").strip()):
        variety = _resolve_variety(db, crop, variety_id, variety_name)
        cycle.variety_id = variety.id if variety else None

    if "cultivation_method_id" in sent or ("cultivation_method" in sent and str(method_code or "").strip()):
        method = _resolve_method(db, crop, method_id, method_code)
        cycle.cultivation_method_id = method.id if method else None

    if "current_stage" in update_data:
        stage = _validate_stage(crop, update_data["current_stage"])
        update_data["current_stage"] = stage

    for field, value in update_data.items():
        setattr(cycle, field, value)

    db.commit()
    db.refresh(cycle)

    return {
        "status": "success",
        "message": "Crop cycle updated successfully",
        "data": _cycle_dict(cycle),
    }


@router.delete("/crop-cycles/{cycle_id}", response_model=dict)
def delete_crop_cycle(
    cycle_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = _verify_cycle_ownership(db, cycle_id, current_user.id)

    db.delete(cycle)
    db.commit()

    return {"status": "success", "message": "Crop cycle deleted successfully"}


@router.get("/crop-tasks", response_model=dict)
def list_crop_tasks(
    q: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(pending|in_progress|completed|overdue)$"),
    priority: Optional[str] = Query(None, pattern="^(low|medium|high)$"),
    category: Optional[str] = None,
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_ids = _get_user_farm_ids(db, current_user.id)
    if not farm_ids:
        return {"status": "success", "data": []}

    qry = (
        db.query(CropTask)
        .join(CropCycle, CropTask.crop_cycle_id == CropCycle.id)
        .join(Crop, CropCycle.crop_id == Crop.id)
        .join(Farm, CropCycle.farm_id == Farm.id)
        .outerjoin(FarmPlot, CropCycle.plot_id == FarmPlot.id)
        .filter(CropCycle.farm_id.in_(farm_ids))
    )

    if q:
        term = f"%{q.strip()}%"
        qry = qry.filter(
            or_(
                CropTask.title.ilike(term),
                CropTask.description.ilike(term),
                CropTask.category.ilike(term),
                CropTask.status.ilike(term),
                Crop.name.ilike(term),
                Farm.farm_name.ilike(term),
                FarmPlot.plot_name.ilike(term),
            )
        )

    if status:
        if status == "overdue":
            today = date.today().strftime("%Y-%m-%d")
            qry = qry.filter(
                CropTask.status != "completed",
                CropTask.due_date.isnot(None),
                CropTask.due_date < today,
            )
        else:
            qry = qry.filter(CropTask.status == status)

    if priority:
        qry = qry.filter(CropTask.priority == priority)

    if category:
        qry = qry.filter(CropTask.category.ilike(category))

    if farm_id:
        if farm_id not in farm_ids:
            return {"status": "success", "data": []}
        qry = qry.filter(CropCycle.farm_id == farm_id)

    if plot_id:
        owned_plot_ids = [
            row[0]
            for row in db.query(FarmPlot.id).filter(FarmPlot.farm_id.in_(farm_ids)).all()
        ]
        if plot_id not in owned_plot_ids:
            return {"status": "success", "data": []}
        qry = qry.filter(CropCycle.plot_id == plot_id)

    if crop:
        qry = qry.filter(Crop.name.ilike(f"%{crop.strip()}%"))

    tasks = qry.order_by(
        case((CropTask.status != "completed", 0), else_=1),
        func.coalesce(CropTask.due_date, "9999-12-31").asc(),
        case(
            (CropTask.priority == "high", 0),
            (CropTask.priority == "medium", 1),
            else_=2,
        ),
        CropTask.created_at.asc(),
    ).all()

    return {
        "status": "success",
        "data": [_task_dict(t) for t in tasks],
    }


@router.post("/crop-tasks", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop_task(
    payload: CropTaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.query(CropCycle).filter(CropCycle.id == payload.crop_cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")

    farm = db.query(Farm).filter(Farm.id == cycle.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized")

    task_id = generate_id("FA-TSK", db, CropTask)

    task = CropTask(
        task_id=task_id,
        crop_cycle_id=payload.crop_cycle_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        due_date=payload.due_date,
        due_time=payload.due_time,
        priority=payload.priority,
        source=payload.source or "manual",
        growth_stage=payload.growth_stage,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return {
        "status": "success",
        "message": "Task created successfully",
        "data": _task_dict(task),
    }


@router.put("/crop-tasks/{task_id}", response_model=dict)
def update_crop_task(
    task_id: str,
    payload: CropTaskUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(CropTask).filter(CropTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    cycle = db.query(CropCycle).filter(CropCycle.id == task.crop_cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    farm = db.query(Farm).filter(Farm.id == cycle.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] == "completed":
        task.completed_at = datetime.utcnow()
    elif "status" in update_data and update_data["status"] in ("pending", "in_progress"):
        task.completed_at = None

    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return {
        "status": "success",
        "message": "Task updated successfully",
        "data": _task_dict(task),
    }


@router.delete("/crop-tasks/{task_id}", response_model=dict)
def delete_crop_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(CropTask).filter(CropTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    cycle = db.query(CropCycle).filter(CropCycle.id == task.crop_cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    farm = db.query(Farm).filter(Farm.id == cycle.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized")

    db.delete(task)
    db.commit()

    return {"status": "success", "message": "Task deleted successfully"}


# ==================== AI TASK SUGGESTIONS ====================

def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _date_from_today(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


#: Generic fallbacks used only when a crop has no lifecycle of its own.
_GENERIC_STAGES = ["seedling", "vegetative", "flowering", "ripening", "harvest"]

#: How a crop's own lifecycle stage maps onto the shared agronomy buckets, so a
#: grape's "Bud break" still produces sensible nutrition and scouting advice.
_STAGE_BUCKET = {
    "nursery": "seedling", "sowing": "seedling", "germination": "seedling",
    "sprouting": "seedling", "establishment": "seedling", "planting": "seedling",
    "transplanting": "seedling", "juvenile growth": "seedling",
    "seedling": "seedling", "hardening": "seedling", "vegetative": "vegetative",
    "vegetative growth": "vegetative", "thinning": "vegetative",
    "tillering": "vegetative", "maintenance": "vegetative",
    "replanting": "vegetative", "squareing": "vegetative", "pod development": "vegetative",
    "root development": "vegetative", "tuber initiation": "vegetative",
    "dormancy": "dormant", "pruning": "dormant", "first cutting": "vegetative",
    "regrowth": "vegetative", "shoot growth": "vegetative", "bud break": "flowering",
    "flowering": "flowering", "flower bud initiation": "flowering",
    "flowering / bearing": "flowering",
    "flower cutting": "harvest", "loose flower harvest": "harvest",
    "fruit set": "flowering", "pod formation": "flowering",
    "grain filling": "ripening", "seed filling": "ripening",
    "tuber bulking": "ripening", "fruit development": "ripening",
    "berry development": "ripening", "rhizome / bulb development": "ripening",
    "maturity": "ripening", "ripening": "ripening", "bearing": "ripening",
    "harvest": "harvest", "post-harvest": "harvest",
    "repeat cycle": "harvest", "repeat cutting": "harvest",
    "ready for transplant / dispatch": "harvest",
}


def _stage_bucket(stage: str) -> str:
    return _STAGE_BUCKET.get((stage or "").strip().lower(), "vegetative")


def _cycle_stage(cycle: CropCycle, crop: Crop) -> str:
    """Work out the current lifecycle stage of a cycle.

    The crop's own ``lifecycle_stages`` list wins, so a perennial crop reports
    "Dormancy" or "Pruning" instead of being forced through a seedling-to-harvest
    sequence. Crops without a lifecycle fall back to elapsed days.
    """
    if cycle.current_stage:
        return cycle.current_stage.strip()
    # Parentheses matter here: `a or b if c else d` parses as `(a or b) if c
    # else d`, which threw away a real sowing_date whenever created_at was
    # missing. Sowing date first, creation date only as the fallback.
    sowing = cycle.sowing_date or (
        cycle.created_at.strftime("%Y-%m-%d") if cycle.created_at else None
    )
    if not sowing:
        stages = (crop.lifecycle_stages or []) if crop else []
        return stages[0] if stages else "vegetative"
    try:
        sd = date.fromisoformat(str(sowing)[:10])
        days = (date.today() - sd).days
    except Exception:
        stages = (crop.lifecycle_stages or []) if crop else []
        return stages[0] if stages else "vegetative"
    if days < 0:
        stages = (crop.lifecycle_stages or []) if crop else []
        return stages[0] if stages else "vegetative"

    duration = crop.growth_duration_days or 0
    if not duration or duration <= 0:
        if days < 40: return "seedling"
        if days < 80: return "vegetative"
        if days < 120: return "flowering"
        if days < 160: return "ripening"
        return "harvest"

    stages = crop.lifecycle_stages or _GENERIC_STAGES
    if len(stages) == 1:
        return stages[0]
    index = int(min(max(days / duration, 0.0), 0.999) * len(stages))
    return stages[index]


_STAGE_TASKS = {
    "seedling": [
        {"title": "Thin seedlings and check germination", "category": "Crop Care", "off": 3, "priority": "high",
         "desc_extra": "Remove weak seedlings so healthy plants get enough space and sunlight."},
    ],
    "dormant": [
        {"title": "Prune and sanitize the crop", "category": "Crop Care", "off": 5, "priority": "medium",
         "desc_extra": "Remove dead and diseased wood during dormancy and clean the tools between plants."},
        {"title": "Apply basal organic manure", "category": "Crop Care", "off": 10, "priority": "medium",
         "desc_extra": "Add well decomposed farmyard manure to each plant before the season restarts."},
        {"title": "Check irrigation lines and leaks", "category": "Irrigation", "off": 7, "priority": "low",
         "desc_extra": "Repair leaks now so the crop gets a full and even watering after bud break."},
    ],
    "vegetative": [
        {"title": "Apply nitrogen top dressing", "category": "Crop Care", "off": 7, "priority": "high",
         "desc_extra": "Split nitrogen in 2-3 doses for better growth during the vegetative stage."},
        {"title": "Weed the field", "category": "Farm Management", "off": 2, "priority": "medium",
         "desc_extra": "Weeds compete for water and nutrients. Remove them before they flower."},
        {"title": "Inspect irrigation lines and water the crop", "category": "Irrigation", "off": 1, "priority": "high",
         "desc_extra": "Check moisture in the soil and ensure the irrigation system is working."},
    ],
    "flowering": [
        {"title": "Irrigate during flowering stage", "category": "Irrigation", "off": 1, "priority": "high",
         "desc_extra": "Water stress at flowering directly reduces grain and fruit formation."},
        {"title": "Apply flowering-stage nutrients", "category": "Crop Care", "off": 5, "priority": "medium",
         "desc_extra": "A small balanced dose at flowering supports better filling of grains and fruits."},
        {"title": "Monitor pests and diseases", "category": "Pest & Disease", "off": 1, "priority": "high",
         "desc_extra": "Scout the field weekly and inspect under leaves for eggs, larvae or fungal spots."},
    ],
    "ripening": [
        {"title": "Reduce irrigation before harvest", "category": "Irrigation", "off": 4, "priority": "medium",
         "desc_extra": "Cut back water once grains/fruits start maturing to improve quality."},
        {"title": "Install bird scaring devices", "category": "Farm Management", "off": 2, "priority": "low",
         "desc_extra": "Protect the maturing crop from bird and animal damage near harvest."},
    ],
    "harvest": [
        {"title": "Harvest the mature crop", "category": "Harvesting", "off": 2, "priority": "high",
         "desc_extra": "Harvest at the right moisture level to get the best market price."},
        {"title": "Plan post-harvest drying and storage", "category": "Harvesting", "off": 6, "priority": "medium",
         "desc_extra": "Arrange drying shade and clean storage to avoid moisture and pest loss after harvest."},
    ],
}


def _mk_suggestion(title, category, off, priority, description, cycle, crop, source, reason, links=None, growth_stage=None):
    return {
        "crop_cycle_id": cycle.id,
        "title": title,
        "description": description,
        "category": category,
        "due_date": _date_from_today(off),
        "priority": priority,
        "source": source,
        "reason": reason,
        "growth_stage": growth_stage,
        "crop_id": crop.id if crop else None,
        "crop_name": crop.name if crop else None,
        "farm_id": cycle.farm_id,
        "farm_name": cycle.farm.farm_name if cycle.farm else None,
        "plot_id": cycle.plot_id,
        "plot_name": cycle.plot.plot_name if cycle.plot else None,
        "links": links or {},
    }


#: Template title -> how the crop name is woven in, so a suggestion reads
#: naturally for any crop instead of a hardcoded "Thin the Tomato seedlings".
_TITLE_PATTERNS = (
    ("irrigation lines", "Inspect irrigation and water the {crop}"),
    ("top dressing", "Apply nitrogen top dressing to {crop}"),
    ("flowering-stage nutrients", "Apply flowering-stage nutrients to {crop}"),
    ("Thin seedlings", "Thin {crop} seedlings and check germination"),
    ("Reduce irrigation", "Reduce irrigation to {crop} before harvest"),
    ("Install bird scaring", "Install bird scaring devices near {crop}"),
    ("Weed the field", "Weed the {crop} field"),
    ("Harvest the mature crop", "Harvest mature {crop}"),
    ("Plan post-harvest", "Plan post-harvest drying and storage for {crop}"),
    ("Prune and sanitize", "Prune and sanitize the {crop} plants"),
    ("basal organic manure", "Apply basal organic manure to the {crop}"),
    ("Check irrigation lines and leaks", "Check the {crop} irrigation lines for leaks"),
    ("Monitor pests and diseases", "Monitor {crop} for pests and diseases"),
    ("Irrigate during flowering stage", "Irrigate {crop} during the flowering stage"),
)


def _stage_suggestions(cycle: CropCycle, crop: Crop, stage: str) -> list:
    """Build tasks for a cycle from its crop's own lifecycle stage."""
    out = []
    crop_name = crop.name if crop else "your crop"
    bucket = _stage_bucket(stage)
    for tpl in _STAGE_TASKS.get(bucket, _STAGE_TASKS["vegetative"]):
        title = tpl["title"]
        for marker, template in _TITLE_PATTERNS:
            if marker in title:
                title = template.format(crop=crop_name)
                break
        description = (
            "AI suggestion for the " + str(stage).lower() + " stage of " + crop_name + "."
            + " " + tpl["desc_extra"]
            + (" Plot: " + cycle.plot.plot_name if cycle.plot else "")
        )
        out.append(_mk_suggestion(
            title, tpl["category"], tpl["off"], tpl["priority"], description,
            cycle, crop, "crop_stage",
            "Based on the current growth stage of " + crop_name,
            growth_stage=stage,
        ))
    return out


def _climate_suggestions(cycle: CropCycle, crop: Crop, weather: Optional[dict]) -> list:
    out = []
    if not weather:
        return out
    forecast = weather.get("forecast") or []
    today_rain = 0.0
    tomorrow_rain = 0.0
    highest_temp = float(weather.get("temperature") or 0)
    wind = float(weather.get("wind_speed") or 0)
    storm = False
    for i in range(min(2, len(forecast))):
        day = forecast[i]
        prec = float(day.get("precipitation") or 0)
        if i == 0:
            today_rain += prec
        else:
            tomorrow_rain += prec
    for day in forecast:
        if int(day.get("weather_code") or 0) >= 95 or "thunderstorm" in str(day.get("description") or "").lower():
            storm = True
        try:
            tmax = float(day.get("max_temp") or 0)
            if tmax > highest_temp:
                highest_temp = tmax
        except Exception:
            pass

    plot = cycle.plot.plot_name if cycle.plot else None
    if today_rain >= 3 or tomorrow_rain >= 3:
        out.append(_mk_suggestion(
            "Avoid fertilizer and pesticide application before rain" + (" (" + plot + ")" if plot else ""),
            "Pest & Disease", 0, "high",
            "Your 7-day forecast shows significant rain within the next 48 hours. "
            "Apply fertilizer or sprays only after the rain clears to avoid runoff and wastage.",
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    if storm:
        out.append(_mk_suggestion(
            "Secure crop area before the thunderstorm" + (" (" + plot + ")" if plot else ""),
            "Farm Management", 0, "high",
            "Thunderstorm conditions are forecast. Clear drainage channels, secure covers "
            "and avoid working in the field during the storm.",
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    if highest_temp >= 36 and today_rain < 1:
        out.append(_mk_suggestion(
            "Provide irrigation to prevent heat stress" + (" (" + plot + ")" if plot else ""),
            "Irrigation", 1, "high",
            "Temperatures are expected to reach {:.0f}°C with little rain. Irrigate early morning "
            "or evening to protect the crop from heat stress.".format(highest_temp),
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    if wind >= 35:
        out.append(_mk_suggestion(
            "Delay spraying until the wind slows down" + (" (" + plot + ")" if plot else ""),
            "Pest & Disease", 0, "medium",
            "Wind speed is high. Spraying now would drift the chemical away and waste it. "
            "Wait for a calm window, ideally early morning.",
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    return out


def _crop_health_suggestion(cycle: CropCycle, crop: Crop, stage: str) -> list:
    crop_name = crop.name if crop else "your crop"
    return [_mk_suggestion(
        "Run a crop health check on " + crop_name + (" (" + cycle.plot.plot_name + ")" if cycle.plot else ""),
        "Crop Care", 1, "medium",
        "Scan " + crop_name + " during the " + stage.replace("_", " ") + " stage for yellowing, spots, "
        "wilting or pest damage. Early detection saves the crop. Use the Crop Health tool for a quick check.",
        cycle, crop, "crop_health",
        "Regular crop health monitoring to catch problems early",
        links={"crop_health": "crop-health.html", "farm": "farm.html"},
    )]


def _collect_suggestions(db: Session, current_user: User) -> tuple:
    """Build data-driven task candidates for every active crop cycle.

    Returns ``(suggestions, weather)``. Suggestions are already deduplicated
    against the farmer's existing pending/in-progress tasks, so both the
    read-only AI panel and the persistent generator can share this.
    """
    farms = db.query(Farm).filter(Farm.user_id == current_user.id, Farm.is_active == True).all()
    farm_ids = [f.id for f in farms]
    if not farm_ids:
        return [], None

    cycles = (
        db.query(CropCycle)
        .filter(CropCycle.farm_id.in_(farm_ids), CropCycle.status.notin_(["completed", "harvested"]))
        .all()
    )
    if not cycles:
        return [], None

    from app.services.weather_service import get_current_weather

    existing_titles = {}
    pending = (
        db.query(CropTask)
        .join(CropCycle, CropTask.crop_cycle_id == CropCycle.id)
        .filter(CropCycle.farm_id.in_(farm_ids), CropTask.status.in_(["pending", "in_progress"]))
        .all()
    )
    for t in pending:
        existing_titles.setdefault(t.crop_cycle_id, set()).add(_norm_title(t.title))

    weather_cache = {}
    suggestions = []
    priority_order = {"high": 0, "medium": 1, "low": 2}

    for cycle in cycles:
        crop = cycle.crop
        farm = cycle.farm
        if not crop or not farm:
            continue
        plot = cycle.plot
        lat = (plot.latitude if plot and plot.latitude else None) or farm.latitude
        lon = (plot.longitude if plot and plot.longitude else None) or farm.longitude

        weather = None
        if lat and lon:
            wkey = (round(float(lat), 3), round(float(lon), 3))
            if wkey in weather_cache:
                weather = weather_cache[wkey]
            else:
                try:
                    weather = asyncio.run(get_current_weather(float(lat), float(lon)))
                except Exception:
                    weather = None
                weather_cache[wkey] = weather

        stage = _cycle_stage(cycle, crop)
        candidates = _stage_suggestions(cycle, crop, stage)
        candidates += _climate_suggestions(cycle, crop, weather)
        candidates += _crop_health_suggestion(cycle, crop, stage)

        for cand in candidates:
            key = _norm_title(cand["title"])
            if key in existing_titles.get(cycle.id, set()):
                continue
            existing_titles.setdefault(cycle.id, set()).add(key)
            suggestions.append(cand)

    suggestions.sort(key=lambda s: (priority_order.get(s["priority"], 3), s["due_date"]))

    weather_out = None
    wf = farms[0]
    lat0, lon0 = wf.latitude, wf.longitude
    if lat0 is None or lon0 is None:
        for cycle in cycles:
            p = cycle.plot
            if p and p.latitude and p.longitude:
                lat0, lon0 = p.latitude, p.longitude
                break
    wkey = None
    if lat0 is not None and lon0 is not None:
        wkey = (round(float(lat0), 3), round(float(lon0), 3))
    if wkey:
        weather_out = weather_cache.get(wkey)
        if weather_out is None:
            try:
                weather_out = asyncio.run(get_current_weather(float(lat0), float(lon0)))
            except Exception:
                weather_out = None
            weather_cache[wkey] = weather_out
        if weather_out:
            weather_out = dict(weather_out)
    if weather_out:
        weather_out["location"] = wf.district or wf.farm_name
        weather_out["soil_type"] = wf.soil_type

    return suggestions, weather_out


@router.get("/crop-tasks/ai-suggest", response_model=dict)
def suggest_ai_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suggestions, weather_out = _collect_suggestions(db, current_user)
    return {
        "status": "success",
        "data": {"weather": weather_out, "suggestions": suggestions[:12]},
    }


@router.post("/crop-tasks/generate", response_model=dict, status_code=status.HTTP_201_CREATED)
def generate_crop_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the data-driven suggestions as real tasks for this farmer.

    Tasks already present on a cycle (pending, in progress or completed) are
    skipped, so the endpoint is safe to call repeatedly.
    """
    suggestions, _weather = _collect_suggestions(db, current_user)

    created = []
    for cand in suggestions:
        cycle = db.query(CropCycle).filter(CropCycle.id == cand["crop_cycle_id"]).first()
        # The helper already scopes to owned farms; re-check so a cycle
        # belonging to another farmer can never be written to.
        if not cycle or cycle.farm is None or cycle.farm.user_id != current_user.id:
            continue
        task = CropTask(
            task_id=generate_id("FA-TSK", db, CropTask),
            crop_cycle_id=cycle.id,
            title=cand["title"],
            description=cand["description"],
            category=cand["category"],
            due_date=cand["due_date"],
            priority=cand["priority"],
            source=cand["source"],
            growth_stage=cand.get("growth_stage"),
            status="pending",
        )
        db.add(task)
        created.append(task)

    if created:
        db.commit()
        for task in created:
            db.refresh(task)

    return {
        "status": "success",
        "message": (
            "Generated {0} new task(s) from your farm data.".format(len(created))
            if created
            else "Your tasks are already up to date."
        ),
        "data": {
            "created_count": len(created),
            "tasks": [_task_dict(t) for t in created],
        },
    }


@router.post("/farm-journal", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_journal_entry(
    payload: JournalCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.farm_id:
        farm = db.query(Farm).filter(Farm.id == payload.farm_id, Farm.user_id == current_user.id).first()
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")

    if payload.plot_id:
        # Validate the plot belongs to one of the current user's farms
        owned_farm_ids = [
            row[0]
            for row in db.query(Farm.id).filter(Farm.user_id == current_user.id).all()
        ]
        plot = None
        if owned_farm_ids:
            plot = (
                db.query(FarmPlot)
                .filter(FarmPlot.id == payload.plot_id, FarmPlot.farm_id.in_(owned_farm_ids))
                .first()
            )
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        if payload.farm_id and plot.farm_id != farm.id:
            raise HTTPException(
                status_code=400, detail="Plot does not belong to the given farm"
            )

    entry = FarmJournal(
        user_id=current_user.id,
        farm_id=payload.farm_id,
        plot_id=payload.plot_id,
        activity=payload.activity,
        notes=payload.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "status": "success",
        "message": "Journal entry created successfully",
        "data": _journal_dict(entry),
    }


@router.get("/farm-journal", response_model=dict)
def list_journal_entries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = (
        db.query(FarmJournal)
        .filter(FarmJournal.user_id == current_user.id)
        .order_by(FarmJournal.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [_journal_dict(e) for e in entries],
    }
