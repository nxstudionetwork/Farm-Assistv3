"""
Seed the news_articles table from real RSS feeds.

Run standalone:  python -m app.database.seed_news
Feeds are fetched over the network; only real articles are stored.
"""

import sys
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal, engine, Base
from app.models import NewsArticle  # registers table
from app.services.news_fetcher import fetch_news


def _upsert_articles(db: Session, articles) -> dict:
    """Insert any articles whose external_id is not already stored."""
    added = 0
    skipped = 0
    for a in articles:
        ext = a.get("external_id")
        if not ext:
            skipped += 1
            continue
        exists = db.query(NewsArticle).filter(NewsArticle.external_id == ext).first()
        if exists:
            # keep existing copy fresh without duplicating
            skipped += 1
            continue

        pub = a.get("published_at")
        if isinstance(pub, str):
            try:
                pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                pub = None
        if pub and pub.tzinfo is not None:
            pub = pub.replace(tzinfo=None)

        article = NewsArticle(
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
        )
        db.add(article)
        added += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"added": added, "skipped": skipped}


def seed(limit_per_run: int = 500) -> dict:
    import time
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        articles = fetch_news()
        if not articles:
            return {"status": "no_sources", "articles_fetched": 0, "added": 0, "skipped": 0}
        result = _upsert_articles(db, articles)
        result["articles_fetched"] = len(articles)
        result["status"] = "ok"
        if len(articles) > limit_per_run:
            # leave additional rows for a later run; not critical
            pass
        return result
    finally:
        db.close()


if __name__ == "__main__":
    try:
        result = seed()
        print(result)
        print(f"Total articles now: {SessionLocal().query(NewsArticle).count()}")
    except Exception as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        raise
