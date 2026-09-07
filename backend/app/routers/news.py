from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.news import NewsArticle, SavedNews
from app.services.news_fetcher import fetch_news

router = APIRouter(prefix="/api/v1", tags=["News"])

# Simple in-memory cache guard to avoid re-seeding on every concurrent request.
_seeding = False


def seed_if_empty(db: Session):
    """Populate news from real RSS feeds the first time news is requested."""
    global _seeding
    count = db.query(NewsArticle).count()
    if count > 0:
        return
    if _seeding:
        return
    _seeding = True
    try:
        from app.services.news_fetcher import fetch_news
        articles = fetch_news()
        added = 0
        for a in articles:
            ext = a.get("external_id")
            if not ext:
                continue
            exists = db.query(NewsArticle).filter(NewsArticle.external_id == ext).first()
            if exists:
                continue
            pub = a.get("published_at")
            if pub and getattr(pub, "tzinfo", None) is not None:
                pub = pub.replace(tzinfo=None)
            db.add(NewsArticle(
                external_id=ext,
                title=(a.get("title") or "")[:500],
                summary=a.get("summary"),
                content=a.get("content"),
                image_url=a.get("image_url"),
                source_name=(a.get("source_name") or "Unknown Source")[:200],
                source_url=a.get("source_url"),
                article_url=a.get("article_url"),
                author=a.get("author"),
                category=a.get("category") or "general",
                region=a.get("region"),
                is_breaking=bool(a.get("is_breaking")),
                published_at=pub,
            ))
            added += 1
        db.commit()
        print(f"[news] seeded {added} real articles from RSS feeds")
    except Exception as exc:
        db.rollback()
        print(f"[news] seed failed: {exc}")
    finally:
        _seeding = False


class NewsBookmarkRequest(BaseModel):
    news_id: str


def _article_dict(a):
    saved = getattr(a, '_is_saved', False)
    return {
        "id": a.id,
        "news_id": a.news_id,
        "external_id": a.external_id,
        "title": a.title,
        "summary": a.summary,
        "content": a.content,
        "image_url": a.image_url,
        "source_name": a.source_name,
        "source_url": a.source_url,
        "article_url": a.article_url,
        "author": a.author,
        "category": a.category,
        "region": a.region,
        "is_breaking": a.is_breaking if hasattr(a, 'is_breaking') else False,
        "published_at": str(a.published_at) if a.published_at else None,
        "fetched_at": str(a.fetched_at) if a.fetched_at else None,
        "is_saved": saved,
    }


@router.get("/news")
def list_news(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    category: Optional[str] = None,
    source: Optional[str] = None,
    query: Optional[str] = None,
    is_breaking: Optional[bool] = None,
    saved_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_if_empty(db)
    q = db.query(NewsArticle)

    if category and category != "all":
        q = q.filter(NewsArticle.category == category)
    if source and source != "all":
        q = q.filter(NewsArticle.source_name == source)
    if query:
        search = f"%{query}%"
        q = q.filter(
            (NewsArticle.title.ilike(search)) |
            (NewsArticle.summary.ilike(search)) |
            (NewsArticle.source_name.ilike(search))
        )
    if is_breaking is not None:
        q = q.filter(NewsArticle.is_breaking == is_breaking)

    if saved_only:
        saved_ids = db.query(SavedNews.news_id).filter(
            SavedNews.user_id == current_user.id
        ).subquery()
        q = q.filter(NewsArticle.id.in_(saved_ids))

    total = q.count()
    items = q.order_by(NewsArticle.published_at.desc().nullslast()).offset(
        (page - 1) * limit
    ).limit(limit).all()

    saved_ids_list = []
    if not saved_only:
        saved_ids_list = [s.news_id for s in db.query(SavedNews.news_id).filter(
            SavedNews.user_id == current_user.id
        ).all()]

    result_items = []
    for n in items:
        d = _article_dict(n)
        d["is_saved"] = n.id in saved_ids_list
        result_items.append(d)

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 0,
            "items": result_items,
        },
    }


@router.get("/news/sources")
def list_sources(db: Session = Depends(get_db)):
    sources = db.query(NewsArticle.source_name, func.count(NewsArticle.id)).group_by(
        NewsArticle.source_name
    ).order_by(func.count(NewsArticle.id).desc()).all()
    return {
        "status": "success",
        "data": [{"name": s[0], "count": s[1]} for s in sources if s[0]],
    }


@router.get("/news/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(NewsArticle.category, func.count(NewsArticle.id)).group_by(
        NewsArticle.category
    ).order_by(func.count(NewsArticle.id).desc()).all()
    return {
        "status": "success",
        "data": [{"name": c[0], "count": c[1]} for c in cats if c[0]],
    }


@router.get("/news/brief")
def farm_brief(db: Session = Depends(get_db)):
    seed_if_empty(db)
    items = db.query(NewsArticle).order_by(
        NewsArticle.published_at.desc().nullslast()
    ).limit(5).all()
    return {
        "status": "success",
        "data": [_article_dict(n) for n in items],
    }


@router.post("/news/refresh")
def refresh_news(db: Session = Depends(get_db)):
    """Re-fetch the latest real articles from RSS feeds and store new ones."""
    try:
        articles = fetch_news()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch news sources: {exc}")
    added = 0
    for a in articles:
        ext = a.get("external_id")
        if not ext:
            continue
        exists = db.query(NewsArticle).filter(NewsArticle.external_id == ext).first()
        if exists:
            continue
        pub = a.get("published_at")
        if pub and getattr(pub, "tzinfo", None) is not None:
            pub = pub.replace(tzinfo=None)
        db.add(NewsArticle(
            external_id=ext,
            title=(a.get("title") or "")[:500],
            summary=a.get("summary"),
            content=a.get("content"),
            image_url=a.get("image_url"),
            source_name=(a.get("source_name") or "Unknown Source")[:200],
            source_url=a.get("source_url"),
            article_url=a.get("article_url"),
            author=a.get("author"),
            category=a.get("category") or "general",
            region=a.get("region"),
            is_breaking=bool(a.get("is_breaking")),
            published_at=pub,
        ))
        added += 1
    db.commit()
    total = db.query(NewsArticle).count()
    return {
        "status": "success",
        "data": {
            "fetched": len(articles),
            "added": added,
            "total": total,
            "message": "News refreshed from live feeds",
        },
    }


@router.get("/news/{news_id}")
def get_news(
    news_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = db.query(NewsArticle).filter(NewsArticle.id == news_id).first()
    if not article:
        article = db.query(NewsArticle).filter(NewsArticle.news_id == news_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    is_saved = db.query(SavedNews).filter(
        SavedNews.user_id == current_user.id,
        SavedNews.news_id == article.id,
    ).first() is not None

    d = _article_dict(article)
    d["is_saved"] = is_saved
    return {"status": "success", "data": d}


@router.post("/news/{news_id}/bookmark")
def toggle_bookmark(
    news_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = db.query(NewsArticle).filter(NewsArticle.id == news_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    existing = db.query(SavedNews).filter(
        SavedNews.user_id == current_user.id,
        SavedNews.news_id == article.id,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"status": "success", "data": {"is_saved": False, "message": "News removed from saved"}}
    else:
        saved_id = generate_id("FA-SNV", db, SavedNews)
        saved = SavedNews(
            saved_id=saved_id,
            user_id=current_user.id,
            news_id=article.id,
        )
        db.add(saved)
        db.commit()
        return {"status": "success", "data": {"is_saved": True, "message": "News saved successfully"}}


@router.get("/news/saved/list")
def saved_news_list(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SavedNews).filter(SavedNews.user_id == current_user.id)
    total = q.count()
    items = q.order_by(SavedNews.created_at.desc()).offset(
        (page - 1) * limit
    ).limit(limit).all()

    result = []
    for s in items:
        if s.article:
            d = _article_dict(s.article)
            d["is_saved"] = True
            d["saved_at"] = str(s.created_at) if s.created_at else None
            result.append(d)

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": result,
        },
    }
