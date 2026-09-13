import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.technique import Technique, TechniqueBookmark
from app.database.seed_techniques import seed_techniques

router = APIRouter(prefix="/api/v1", tags=["Techniques"])


def parse_list_field(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except Exception:
        return [s.strip() for s in str(val).split("|") if s.strip()]


def serialize_technique(t, db=None, user_id=None):
    bookmarked = False
    if user_id and db:
        bk = db.query(TechniqueBookmark).filter(
            TechniqueBookmark.user_id == user_id,
            TechniqueBookmark.technique_id == t.id
        ).first()
        bookmarked = bk is not None

    bookmark_count = 0
    if db:
        bookmark_count = db.query(func.count(TechniqueBookmark.id)).filter(
            TechniqueBookmark.technique_id == t.id
        ).scalar() or 0

    return {
        "id": t.id,
        "technique_id": t.technique_id,
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "crop": t.crop,
        "season": t.season,
        "difficulty": t.difficulty,
        "duration": t.duration,
        "cost_level": t.cost_level,
        "water_requirement": t.water_requirement,
        "is_organic": t.is_organic,
        "materials": parse_list_field(t.materials),
        "steps": parse_list_field(t.steps),
        "tips": t.tips,
        "benefits": parse_list_field(t.benefits),
        "precautions": parse_list_field(t.precautions),
        "common_mistakes": parse_list_field(t.common_mistakes),
        "suitable_soil": t.suitable_soil,
        "icon": t.icon,
        "color": t.color,
        "image_url": t.image_url,
        "is_published": t.is_published,
        "views_count": t.views_count or 0,
        "bookmark_count": bookmark_count,
        "bookmarked": bookmarked,
        "created_at": str(t.created_at) if t.created_at else None,
    }


@router.get("/techniques")
def list_techniques(
    search: Optional[str] = None,
    category: Optional[str] = None,
    crop: Optional[str] = None,
    season: Optional[str] = None,
    difficulty: Optional[str] = None,
    is_organic: Optional[bool] = None,
    bookmarked_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_techniques(db)
    q = db.query(Technique).filter(Technique.is_published == True)

    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Technique.title.ilike(term),
                Technique.description.ilike(term),
                Technique.category.ilike(term),
                Technique.crop.ilike(term),
                Technique.materials.ilike(term),
                Technique.benefits.ilike(term),
            )
        )

    if category:
        q = q.filter(Technique.category == category)
    if crop:
        q = q.filter(Technique.crop.ilike(f"%{crop}%"))
    if season:
        q = q.filter(Technique.season == season)
    if difficulty:
        q = q.filter(Technique.difficulty == difficulty)
    if is_organic is not None:
        q = q.filter(Technique.is_organic == is_organic)

    if bookmarked_only:
        bookmarked_ids = [
            b.technique_id for b in db.query(TechniqueBookmark).filter(
                TechniqueBookmark.user_id == current_user.id
            ).all()
        ]
        q = q.filter(Technique.id.in_(bookmarked_ids))

    techniques = q.order_by(Technique.views_count.desc().nullslast(), Technique.created_at.desc()).all()

    return {
        "status": "success",
        "data": [serialize_technique(t, db, current_user.id) for t in techniques],
    }


@router.get("/techniques/{technique_id}")
def get_technique(
    technique_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_techniques(db)
    t = db.query(Technique).filter(
        (Technique.technique_id == technique_id) | (Technique.id == technique_id)
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Technique not found")

    t.views_count = (t.views_count or 0) + 1
    db.commit()
    db.refresh(t)

    data = serialize_technique(t, db, current_user.id)

    related = db.query(Technique).filter(
        Technique.is_published == True,
        Technique.id != t.id,
        or_(
            Technique.category == t.category,
            Technique.crop == t.crop,
        )
    ).limit(4).all()
    data["related"] = [serialize_technique(r, db, current_user.id) for r in related]

    return {"status": "success", "data": data}


@router.get("/techniques/categories/all")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_techniques(db)
    cats = db.query(Technique.category).filter(
        Technique.is_published == True,
        Technique.category.isnot(None)
    ).distinct().all()
    return {"status": "success", "data": [c[0] for c in cats if c[0]]}


@router.get("/techniques/crops/all")
def list_crops(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_techniques(db)
    crops = db.query(Technique.crop).filter(
        Technique.is_published == True,
        Technique.crop.isnot(None)
    ).distinct().all()
    return {"status": "success", "data": [c[0] for c in crops if c[0]]}


@router.post("/techniques/{technique_id}/bookmark")
def bookmark_technique(
    technique_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_techniques(db)
    t = db.query(Technique).filter(
        (Technique.technique_id == technique_id) | (Technique.id == technique_id)
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Technique not found")

    existing = db.query(TechniqueBookmark).filter(
        TechniqueBookmark.user_id == current_user.id,
        TechniqueBookmark.technique_id == t.id
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"status": "success", "message": "Bookmark removed", "data": {"bookmarked": False}}

    bookmark = TechniqueBookmark(
        user_id=current_user.id,
        technique_id=t.id,
    )
    db.add(bookmark)
    db.commit()
    return {"status": "success", "message": "Technique bookmarked", "data": {"bookmarked": True}}


@router.get("/techniques/bookmarks/list")
def list_bookmarks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_techniques(db)
    bookmarks = db.query(TechniqueBookmark).filter(
        TechniqueBookmark.user_id == current_user.id
    ).order_by(TechniqueBookmark.created_at.desc()).all()

    techniques = []
    for b in bookmarks:
        t = db.query(Technique).filter(Technique.id == b.technique_id).first()
        if t:
            data = serialize_technique(t, db, current_user.id)
            data["bookmarked_at"] = str(b.created_at) if b.created_at else None
            techniques.append(data)

    return {"status": "success", "data": techniques}
