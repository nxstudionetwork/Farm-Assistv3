"""FarmBuzz API — agriculture-first social & entertainment module.

Provides posts, shorts, likes, comments, shares, saves, follows, hashtags,
trends, profiles, search and media upload for the FarmBuzz module. The public
read endpoints work without authentication so visitors can browse the feed;
mutations require an authenticated user.
"""
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_db
from app.utils.auth import get_current_user, get_optional_user, generate_id
from app.models.user import User, FarmerProfile
from app.models.notification import Notification
from app.models.farmbuzz import (
    FarmBuzzPost, FarmBuzzComment, FarmBuzzLike, FarmBuzzSave,
    FarmBuzzShare, FarmBuzzFollow, FarmBuzzHashtag, FarmBuzzTrend,
    FarmBuzzStory, FarmBuzzStoryViewer, FarmBuzzView, FarmBuzzReport,
    FarmBuzzInteraction,
)
from app.services.farmbuzz_recommender import ALLOWED_EVENTS, rank_shorts

router = APIRouter(prefix="/api/v1/farmbuzz", tags=["FarmBuzz"])

CATEGORIES = {
    # Core legacy categories (kept for backwards compatibility)
    "Farming", "Crop", "Crops", "Machinery", "Market", "Success Story",
    "Success Stories", "Question", "Tip", "Community", "Other",
    # Agriculture discovery categories
    "Farm Techniques", "Livestock", "Weather", "Organic Farming",
    "Technology", "Government", "Horticulture", "Irrigation", "Soil",
    "Dairy", "Poultry", "Sustainable Farming", "Finance",
    # Shorts rail categories (frontend SHORT_CATS)
    "Farmer Techniques", "Farmer Tricks", "Farming Scenes", "Farmer Life",
    "Farming Comedy", "Quick Knowledge", "Educational", "Expert Shorts",
}
CONTENT_TYPES = {"post", "short"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp"}
VIDEO_EXTS = {"mp4", "webm", "mov", "m4v"}
IMAGE_MAX_MB = 10
VIDEO_MAX_MB = 60

HASHTAG_RE = re.compile(r"#(\w+)")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class PostCreate(BaseModel):
    content_type: str = "post"
    title: Optional[str] = None
    caption: str = ""
    media_url: Optional[str] = None
    media_type: str = "text"
    thumbnail_url: Optional[str] = None
    location: Optional[str] = None
    crop: Optional[str] = None
    category: str = "Farming"
    hashtags: Optional[List[str]] = []
    tagged_users: Optional[List[str]] = []
    visibility: str = "public"


class PostUpdate(BaseModel):
    title: Optional[str] = None
    caption: Optional[str] = None
    location: Optional[str] = None
    crop: Optional[str] = None
    category: Optional[str] = None
    hashtags: Optional[List[str]] = None
    visibility: Optional[str] = None


class CommentCreate(BaseModel):
    content: str


class ReportCreate(BaseModel):
    reason: str = "Other"
    description: Optional[str] = None


class StoryCreate(BaseModel):
    media_url: Optional[str] = None
    media_type: str = "text"  # image | video | text
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    background_color: Optional[str] = None
    expires_in_hours: Optional[int] = 24


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    farm_location: Optional[str] = None
    crops: Optional[str] = None
    farming_type: Optional[str] = None
    profile_image: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_post(db: Session, post_id: str) -> FarmBuzzPost:
    post = db.query(FarmBuzzPost).filter(FarmBuzzPost.id == post_id).first()
    if not post:
        post = db.query(FarmBuzzPost).filter(FarmBuzzPost.post_id == post_id).first()
    if not post or not post.is_active:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def _can_view_post(db: Session, post: FarmBuzzPost, viewer: Optional[User]) -> bool:
    """Enforce post visibility: public for everyone; followers-only for author +
    followers; private only for the author."""
    if post.visibility == "public":
        return True
    if viewer is None:
        return False
    if post.user_id == viewer.id:
        return True
    if post.visibility == "followers":
        followed = (
            db.query(FarmBuzzFollow)
            .filter(
                FarmBuzzFollow.follower_id == viewer.id,
                FarmBuzzFollow.following_id == post.user_id,
            )
            .first()
        )
        return followed is not None
    return False


def _assert_can_view(db: Session, post: FarmBuzzPost, viewer: Optional[User]) -> None:
    if not _can_view_post(db, post, viewer):
        raise HTTPException(status_code=404, detail="Post not found")


def _author_of(db: Session, user_id: str) -> dict:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return {"id": None, "farmer_id": None, "full_name": "Farmer", "profile_image": None}
    return {
        "id": u.id,
        "farmer_id": u.farmer_id,
        "full_name": u.full_name,
        "profile_image": u.profile_image,
        "verified": bool(getattr(u, "is_verified", False)),
    }


def _post_to_dict(db: Session, post: FarmBuzzPost, current_user: Optional[User] = None) -> dict:
    is_liked = is_saved = is_followed = False
    if current_user:
        is_liked = (
            db.query(FarmBuzzLike)
            .filter(FarmBuzzLike.post_id == post.id, FarmBuzzLike.user_id == current_user.id)
            .first() is not None
        )
        is_saved = (
            db.query(FarmBuzzSave)
            .filter(FarmBuzzSave.post_id == post.id, FarmBuzzSave.user_id == current_user.id)
            .first() is not None
        )
        if current_user.id != post.user_id:
            is_followed = (
                db.query(FarmBuzzFollow)
                .filter(FarmBuzzFollow.follower_id == current_user.id, FarmBuzzFollow.following_id == post.user_id)
                .first() is not None
            )
    author = _author_of(db, post.user_id)
    return {
        "id": post.id,
        "post_id": post.post_id,
        "user_id": post.user_id,
        "content_type": post.content_type,
        "title": post.title,
        "caption": post.caption,
        "media_url": post.media_url,
        "media_type": post.media_type,
        "thumbnail_url": post.thumbnail_url,
        "location": post.location,
        "crop": post.crop,
        "category": post.category,
        "hashtags": post.hashtags or [],
        "visibility": post.visibility,
        "likes_count": post.likes_count or 0,
        "comments_count": post.comments_count or 0,
        "shares_count": post.shares_count or 0,
        "saves_count": post.saves_count or 0,
        "views_count": post.views_count or 0,
        "created_at": str(post.created_at) if post.created_at else None,
        "author": author,
        "is_liked": is_liked,
        "is_saved": is_saved,
        "is_followed": is_followed,
    }


def _sync_hashtags(db: Session, post: FarmBuzzPost, tags: List[str]) -> None:
    normalized = set()
    for raw in tags:
        tag = raw.strip().lstrip("#").lower()
        if tag and re.match(r"^[a-z0-9_]+$", tag):
            normalized.add(tag)
    for tag in normalized:
        row = db.query(FarmBuzzHashtag).filter(FarmBuzzHashtag.tag == tag).first()
        if row:
            row.post_count = (row.post_count or 0) + 1
        else:
            db.add(FarmBuzzHashtag(tag=tag, post_count=1))
    post.hashtags = sorted(normalized)


def _comment_to_dict(db: Session, comment: FarmBuzzComment, current_user: Optional[User] = None) -> dict:
    return {
        "id": comment.id,
        "user_id": comment.user_id,
        "post_id": comment.post_id,
        "content": comment.content,
        "created_at": str(comment.created_at) if comment.created_at else None,
        "author": _author_of(db, comment.user_id),
        "is_mine": bool(current_user and comment.user_id == current_user.id),
    }


def _story_to_dict(db: Session, story: FarmBuzzStory, current_user: Optional[User] = None) -> dict:
    return {
        "id": story.id,
        "story_id": story.story_id,
        "user_id": story.user_id,
        "author": _author_of(db, story.user_id),
        "media_url": story.media_url,
        "media_type": story.media_type,
        "thumbnail_url": story.thumbnail_url,
        "caption": story.caption,
        "background_color": story.background_color,
        "views_count": story.views_count or 0,
        "expires_at": str(story.expires_at) if story.expires_at else None,
        "created_at": str(story.created_at) if story.created_at else None,
        "is_mine": bool(current_user and story.user_id == current_user.id),
    }


def _resolve_story(db: Session, story_id: str) -> FarmBuzzStory:
    story = db.query(FarmBuzzStory).filter(FarmBuzzStory.id == story_id).first()
    if not story:
        story = db.query(FarmBuzzStory).filter(FarmBuzzStory.story_id == story_id).first()
    if not story or not story.is_active:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.expires_at and story.expires_at < datetime.utcnow():
        raise HTTPException(status_code=404, detail="Story expired")
    return story


def _notify(
    db: Session,
    user_id: str,
    title: str,
    message: str,
    ntype: str,
    ref_id: Optional[str] = None,
    ref_type: Optional[str] = None,
    icon: Optional[str] = None,
    action_url: str = "farmbuzz.html",
) -> None:
    if not user_id:
        return
    n_id = generate_id("FA-NTF", db, Notification)
    db.add(Notification(
        notification_id=n_id,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=ntype,
        reference_id=ref_id,
        reference_type=ref_type,
        icon=icon,
        action_url=action_url,
    ))


def _counts(db: Session, user_id: str) -> dict:
    followers = db.query(FarmBuzzFollow).filter(FarmBuzzFollow.following_id == user_id).count()
    following = db.query(FarmBuzzFollow).filter(FarmBuzzFollow.follower_id == user_id).count()
    posts_count = db.query(FarmBuzzPost).filter(
        FarmBuzzPost.user_id == user_id,
        FarmBuzzPost.is_active == True,
        FarmBuzzPost.content_type == "post",
    ).count()
    shorts_count = db.query(FarmBuzzPost).filter(
        FarmBuzzPost.user_id == user_id,
        FarmBuzzPost.is_active == True,
        FarmBuzzPost.content_type == "short",
    ).count()
    saved_count = db.query(FarmBuzzSave).filter(FarmBuzzSave.user_id == user_id).count()
    return {
        "followers_count": followers,
        "following_count": following,
        "posts_count": posts_count,
        "shorts_count": shorts_count,
        "saved_count": saved_count,
    }


def _profile_dict(db: Session, user: User, current_user: Optional[User] = None) -> dict:
    fp = user.farmer_profile
    counts = _counts(db, user.id)
    is_followed = False
    if current_user and current_user.id != user.id:
        is_followed = (
            db.query(FarmBuzzFollow)
            .filter(FarmBuzzFollow.follower_id == current_user.id, FarmBuzzFollow.following_id == user.id)
            .first() is not None
        )
    recent = (
        db.query(FarmBuzzPost)
        .filter(FarmBuzzPost.user_id == user.id, FarmBuzzPost.is_active == True)
        .order_by(FarmBuzzPost.created_at.desc())
        .limit(12)
        .all()
    )
    recent = [p for p in recent if _can_view_post(db, p, current_user)]
    return {
        "id": user.id,
        "farmer_id": user.farmer_id,
        "full_name": user.full_name,
        "profile_image": user.profile_image,
        "phone_number": user.phone_number if current_user and current_user.id == user.id else None,
        "bio": fp.bio if fp else None,
        "farm_location": fp.farm_location if fp else None,
        "crops": fp.preferred_crops if fp else None,
        "farming_type": fp.farming_type if fp else None,
        "irrigation_type": fp.irrigation_type if fp else None,
        "farming_experience": fp.farming_experience if fp else None,
        "is_followed": is_followed,
        "posts": [_post_to_dict(db, p, current_user) for p in recent],
        **_counts(db, user.id),
    }


def _seed_trends(db: Session) -> None:
    if db.query(FarmBuzzTrend).count() > 0:
        return
    defaults = [
        ("Low-cost drip irrigation saving 40% water across Andhra Pradesh", "agriculture", 128400, "fa-droplet"),
        ("Pink bollworm alert: install pheromone traps now", "tip", 96200, "fa-bug"),
        ("Farmers switch to zero-till wheat sowing for 20% cost savings", "posts", 88100, "fa-tractor"),
        ("eNAM digital mandi trading hits record volume this season", "agriculture", 75300, "fa-chart-line"),
        ("#OrganicChilli exports to Europe reach new high", "discussion", 68900, "fa-fire"),
        ("Community drones: shared spraying brings down costs to ₹300/acre", "shorts", 64100, "fa-drone"),
        ("Monsoon deficit watch: how farmers are adapting sowing windows", "agriculture", 59700, "fa-cloud-rain"),
        ("Paddy straw management toppers share their techniques", "tips", 54200, "fa-feather"),
    ]
    for i, (topic, category, score, icon) in enumerate(defaults, start=1):
        db.add(FarmBuzzTrend(
            trend_id=f"FA-TRN-{i:04d}",
            topic=topic,
            category=category,
            description=f"Trending across FarmBuzz — {category}",
            engagement_score=score,
            icon=icon,
            is_active=True,
        ))
    db.commit()


# ---------------------------------------------------------------------------
# Feed / posts
# ---------------------------------------------------------------------------
@router.get("/feed")
def get_feed(
    content_type: str = Query("all", pattern="^(all|post|short)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    category: Optional[str] = None,
    crop: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = Query("recent", pattern="^(recent|trending|recommended)$"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    q = db.query(FarmBuzzPost).filter(FarmBuzzPost.is_active == True)

    # Visibility filtering: public posts are visible to everyone. "followers"-only
    # posts are visible to the author and their followers. "private" posts are only
    # visible to the author.
    viewer_id = current_user.id if current_user else None
    if viewer_id:
        followers_of = (
            db.query(FarmBuzzFollow.following_id)
            .filter(FarmBuzzFollow.follower_id == viewer_id)
            .subquery()
        )
        # public OR own OR (followers-only AND author is followed)
        q = q.filter(
            or_(
                FarmBuzzPost.visibility == "public",
                FarmBuzzPost.user_id == viewer_id,
                and_(
                    FarmBuzzPost.visibility == "followers",
                    FarmBuzzPost.user_id.in_(followers_of),
                ),
            )
        )
    else:
        q = q.filter(FarmBuzzPost.visibility == "public")

    if content_type != "all":
        q = q.filter(FarmBuzzPost.content_type == content_type)
    if category and category.lower() != "all":
        q = q.filter(FarmBuzzPost.category == category)
    if crop and crop.lower() != "all":
        q = q.filter(FarmBuzzPost.crop.ilike(f"%{crop}%"))
    if search:
        q = q.filter(
            FarmBuzzPost.caption.ilike(f"%{search}%")
            | FarmBuzzPost.title.ilike(f"%{search}%")
            | FarmBuzzPost.location.ilike(f"%{search}%")
            | FarmBuzzPost.category.ilike(f"%{search}%")
        )

    total = q.count()
    if sort == "recommended":
        # Personalized ranking: score a bounded candidate pool in Python,
        # then paginate the ranked order (deterministic per request).
        pool = q.order_by(FarmBuzzPost.created_at.desc()).limit(500).all()
        crops: list = []
        try:
            fp = getattr(current_user, "farmer_profile", None) if current_user else None
            raw = getattr(fp, "preferred_crops", None) if fp else None
            if isinstance(raw, str) and raw.strip():
                crops = [c.strip() for c in raw.split(",") if c.strip()]
            elif isinstance(raw, list):
                crops = [str(c).strip() for c in raw if str(c).strip()]
        except Exception:
            crops = []
        ranked = rank_shorts(db, current_user, pool, crops)
        items = ranked[(page - 1) * limit: (page - 1) * limit + limit]
    elif sort == "trending":
        order = (
            FarmBuzzPost.likes_count + FarmBuzzPost.comments_count * 2
            + FarmBuzzPost.shares_count * 3 + FarmBuzzPost.views_count * 0.05
        ).desc()
        items = q.order_by(order).offset((page - 1) * limit).limit(limit).all()
    else:
        order = FarmBuzzPost.created_at.desc()
        items = q.order_by(order).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_post_to_dict(db, p, current_user) for p in items],
        },
    }


@router.get("/posts")
def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    return get_feed("post", page, limit, category, None, None, "recent", db, current_user)


@router.get("/shorts")
def list_shorts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    return get_feed("short", page, limit, category, None, None, "recent", db, current_user)


@router.get("/shorts/recommended")
def recommended_shorts(
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=50),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Personalized Shorts feed (Instagram/Reels-style discovery).

    Returns ranked shorts without exposing internal scores. Cold-start
    users (no history) receive popular + recent + diverse content.
    """
    return get_feed("short", page, limit, category, None, None, "recommended", db, current_user)


class InteractionEvent(BaseModel):
    event_type: str = "watch"
    watch_duration_ms: Optional[int] = 0
    completion_pct: Optional[int] = 0


@router.post("/posts/{post_id}/event", status_code=201)
def record_interaction_event(
    post_id: str,
    payload: InteractionEvent,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stores watch-behaviour signals for the recommendation engine.

    Callers should batch/debounce (e.g. send on threshold crossed, on
    completion, on skip) rather than on every playback tick.
    """
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    etype = (payload.event_type or "").strip().lower()
    if etype not in ALLOWED_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"event_type must be one of {sorted(ALLOWED_EVENTS)}",
        )
    try:
        duration = int(payload.watch_duration_ms or 0)
    except (TypeError, ValueError):
        duration = 0
    try:
        completion = int(payload.completion_pct or 0)
    except (TypeError, ValueError):
        completion = 0
    duration = max(0, min(duration, 3600000))
    completion = max(0, min(completion, 100))
    if post.user_id == current_user.id and etype in {"qualified_view", "watch", "complete", "skip", "replay"}:
        return {"status": "success", "data": {"post_id": post.post_id, "recorded": False}}
    db.add(FarmBuzzInteraction(
        post_id=post.id,
        user_id=current_user.id,
        event_type=etype,
        watch_duration_ms=duration,
        completion_pct=completion,
    ))
    db.commit()
    return {"status": "success", "data": {"post_id": post.post_id, "recorded": True}}


@router.get("/posts/{post_id}")
def get_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)

    comments = (
        db.query(FarmBuzzComment)
        .filter(FarmBuzzComment.post_id == post.id)
        .order_by(FarmBuzzComment.created_at.asc())
        .all()
    )
    comment_list = []
    for c in comments:
        comment_list.append(_comment_to_dict(db, c, current_user))

    data = _post_to_dict(db, post, current_user)
    data["comments"] = comment_list
    return {"status": "success", "data": data}


@router.post("/posts", status_code=201)
def create_post(
    payload: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="content_type must be 'post' or 'short'")
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CATEGORIES)}")
    if not payload.caption and not payload.title and not payload.media_url:
        raise HTTPException(status_code=400, detail="Add a caption, title or media to post")

    post_id = generate_id("FA-BZ", db, FarmBuzzPost)
    post = FarmBuzzPost(
        post_id=post_id,
        user_id=current_user.id,
        content_type=payload.content_type,
        title=payload.title,
        caption=payload.caption,
        media_url=payload.media_url,
        media_type=payload.media_type,
        thumbnail_url=payload.thumbnail_url,
        location=payload.location,
        crop=payload.crop,
        category=payload.category,
        tagged_users=payload.tagged_users or [],
        visibility=payload.visibility or "public",
        is_active=True,
    )
    hashtags = list(payload.hashtags or [])
    caption_tags = HASHTAG_RE.findall(payload.caption or "")
    hashtags.extend(caption_tags)
    db.add(post)
    db.flush()
    _sync_hashtags(db, post, hashtags)
    db.commit()
    db.refresh(post)

    return {
        "status": "success",
        "data": {
            **_post_to_dict(db, post, current_user),
            "message": "Published successfully",
        },
    }


@router.put("/posts/{post_id}")
def update_post(
    post_id: str,
    payload: PostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own posts")

    if payload.title is not None:
        post.title = payload.title
    if payload.caption is not None:
        post.caption = payload.caption
    if payload.location is not None:
        post.location = payload.location
    if payload.crop is not None:
        post.crop = payload.crop
    if payload.category is not None:
        if payload.category not in CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        post.category = payload.category
    if payload.visibility is not None:
        post.visibility = payload.visibility
    if payload.hashtags is not None:
        _sync_hashtags(db, post, payload.hashtags)
    db.commit()
    db.refresh(post)

    return {"status": "success", "data": {**_post_to_dict(db, post, current_user), "message": "Post updated"}}



@router.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own posts")
    post.is_active = False
    db.commit()
    return {"status": "success", "data": {"post_id": post.post_id, "message": "Post deleted"}}


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------
@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    existing = (
        db.query(FarmBuzzLike)
        .filter(FarmBuzzLike.post_id == post.id, FarmBuzzLike.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
        post.likes_count = max((post.likes_count or 1) - 1, 0)
        liked = False
        message = "Unliked"
    else:
        db.add(FarmBuzzLike(post_id=post.id, user_id=current_user.id))
        post.likes_count = (post.likes_count or 0) + 1
        liked = True
        message = "Liked"
        if post.user_id != current_user.id:
            _notify(
                db, post.user_id,
                f"{current_user.full_name} liked your post",
                post.title or "Your FarmBuzz post received a like.",
                "farmbuzz_like",
                ref_id=post.post_id, ref_type="farmbuzz_post",
                icon="fas fa-heart",
            )
    db.commit()
    db.refresh(post)
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_liked": liked, "likes_count": post.likes_count, "message": message},
    }


@router.delete("/posts/{post_id}/like")
def unlike_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotent unlike (DELETE alias for clients that prefer REST semantics)."""
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    existing = (
        db.query(FarmBuzzLike)
        .filter(FarmBuzzLike.post_id == post.id, FarmBuzzLike.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
        post.likes_count = max((post.likes_count or 1) - 1, 0)
        db.commit()
        db.refresh(post)
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_liked": False, "likes_count": post.likes_count or 0},
    }


@router.post("/posts/{post_id}/comment", status_code=201)
def add_comment(
    post_id: str,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment content is required")
    if len(content) > 1000:
        raise HTTPException(status_code=400, detail="Comment too long (max 1000 chars)")
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)

    comment = FarmBuzzComment(post_id=post.id, user_id=current_user.id, content=content)
    db.add(comment)
    post.comments_count = (post.comments_count or 0) + 1
    if post.user_id != current_user.id:
        _notify(
            db, post.user_id,
            f"{current_user.full_name} commented on your post",
            content[:120],
            "farmbuzz_comment",
            ref_id=post.post_id, ref_type="farmbuzz_post",
            icon="fas fa-comment",
        )
    db.commit()
    db.refresh(comment)

    return {
        "status": "success",
        "data": {
            "id": comment.id,
            "post_id": post.post_id,
            "content": comment.content,
            "created_at": str(comment.created_at) if comment.created_at else None,
            "author": _author_of(db, current_user.id),
            "message": "Comment added",
        },
    }


@router.get("/posts/{post_id}/comments")
def list_comments(
    post_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    q = db.query(FarmBuzzComment).filter(FarmBuzzComment.post_id == post.id)
    total = q.count()
    items = (
        q.order_by(FarmBuzzComment.created_at.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [_comment_to_dict(db, c, current_user) for c in items],
        },
    }


@router.delete("/posts/{post_id}/comments/{comment_id}")
def delete_comment(
    post_id: str,
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    comment = (
        db.query(FarmBuzzComment)
        .filter(FarmBuzzComment.id == comment_id, FarmBuzzComment.post_id == post.id)
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id and post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    db.delete(comment)
    post.comments_count = max((post.comments_count or 1) - 1, 0)
    db.commit()
    return {"status": "success", "data": {"comment_id": comment_id, "message": "Comment deleted"}}


@router.post("/posts/{post_id}/view")
def record_view(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Records a genuine view. Views are attributed once per authenticated
    viewer per post, so page loads and component re-renders never inflate the
    counter and duplicate requests cannot flood it."""
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    if current_user and current_user.id == post.user_id:
        return {
            "status": "success",
            "data": {"post_id": post.post_id, "is_new_view": False, "views_count": post.views_count or 0},
        }
    existing = None
    if current_user:
        existing = (
            db.query(FarmBuzzView)
            .filter(FarmBuzzView.post_id == post.id, FarmBuzzView.user_id == current_user.id)
            .first()
        )
    if not existing:
        if current_user:
            db.add(FarmBuzzView(post_id=post.id, user_id=current_user.id))
        post.views_count = (post.views_count or 0) + 1
        is_new = True
    else:
        is_new = False
    db.commit()
    db.refresh(post)
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_new_view": is_new, "views_count": post.views_count or 0},
    }


@router.post("/posts/{post_id}/report", status_code=201)
def report_post(
    post_id: str,
    payload: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    if post.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot report your own post")
    reason = (payload.reason or "").strip()[:120] or "Other"
    existing = (
        db.query(FarmBuzzReport)
        .filter(FarmBuzzReport.post_id == post.id, FarmBuzzReport.user_id == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="You have already reported this post")
    db.add(FarmBuzzReport(
        post_id=post.id,
        user_id=current_user.id,
        reason=reason,
        description=payload.description,
    ))
    db.commit()
    return {"status": "success", "data": {"post_id": post.post_id, "message": "Report submitted. Thank you for keeping FarmBuzz safe."}}


@router.post("/posts/{post_id}/save")
def toggle_save(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    existing = (
        db.query(FarmBuzzSave)
        .filter(FarmBuzzSave.post_id == post.id, FarmBuzzSave.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
        post.saves_count = max((post.saves_count or 1) - 1, 0)
        saved = False
        message = "Removed from saved"
    else:
        db.add(FarmBuzzSave(post_id=post.id, user_id=current_user.id))
        post.saves_count = (post.saves_count or 0) + 1
        saved = True
        message = "Saved"
    db.commit()
    db.refresh(post)
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_saved": saved, "saves_count": post.saves_count, "message": message},
    }


@router.delete("/posts/{post_id}/save")
def unsave_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotent unsave (DELETE alias for clients that prefer REST semantics)."""
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    existing = (
        db.query(FarmBuzzSave)
        .filter(FarmBuzzSave.post_id == post.id, FarmBuzzSave.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
        post.saves_count = max((post.saves_count or 1) - 1, 0)
        db.commit()
        db.refresh(post)
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_saved": False, "saves_count": post.saves_count or 0},
    }


@router.post("/posts/{post_id}/share")
def share_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
    _assert_can_view(db, post, current_user)
    db.add(FarmBuzzShare(post_id=post.id, user_id=current_user.id))
    post.shares_count = (post.shares_count or 0) + 1
    if post.user_id != current_user.id:
        _notify(
            db, post.user_id,
            f"{current_user.full_name} shared your post",
            post.title or "Your post was shared on FarmBuzz.",
            "farmbuzz_share",
            ref_id=post.post_id, ref_type="farmbuzz_post",
            icon="fas fa-share",
        )
    db.commit()
    db.refresh(post)
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "shares_count": post.shares_count, "message": "Shared"},
    }


@router.get("/saved")
def saved_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        db.query(FarmBuzzPost)
        .join(FarmBuzzSave, FarmBuzzSave.post_id == FarmBuzzPost.id)
        .filter(
            FarmBuzzSave.user_id == current_user.id,
            FarmBuzzPost.is_active == True,
        )
        .order_by(FarmBuzzSave.created_at.desc())
    )
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_post_to_dict(db, p, current_user) for p in items],
        },
    }


# ---------------------------------------------------------------------------
# Follows & profiles
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}/follow")
def toggle_follow(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        target = db.query(User).filter(User.farmer_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    existing = (
        db.query(FarmBuzzFollow)
        .filter(FarmBuzzFollow.follower_id == current_user.id, FarmBuzzFollow.following_id == target.id)
        .first()
    )
    if existing:
        db.delete(existing)
        following = False
        message = "Unfollowed"
    else:
        db.add(FarmBuzzFollow(follower_id=current_user.id, following_id=target.id))
        following = True
        message = "Following"
        _notify(
            db, target.id,
            f"{current_user.full_name} started following you",
            "Follow your farming journey on FarmBuzz.",
            "farmbuzz_follow",
            ref_id=target.id, ref_type="farmbuzz_user",
            icon="fas fa-user-plus",
            action_url="farmbuzz.html#self",
        )
    db.commit()
    return {"status": "success", "data": {"following": following, "message": message}}


@router.get("/profile")
def my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"status": "success", "data": _profile_dict(db, current_user, current_user)}


@router.get("/profile/{user_id}")
def view_profile(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = db.query(User).filter(User.farmer_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "success", "data": _profile_dict(db, user, current_user)}


@router.get("/users/{user_id}/profile")
def profile_by_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    return view_profile(user_id, db, current_user)


@router.put("/profile")
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fp = current_user.farmer_profile
    if not fp:
        fp = FarmerProfile(user_id=current_user.id)
        db.add(fp)

    if payload.display_name is not None and payload.display_name.strip():
        current_user.full_name = payload.display_name.strip()
    if payload.bio is not None:
        fp.bio = payload.bio
    if payload.farm_location is not None:
        fp.farm_location = payload.farm_location
    if payload.crops is not None:
        fp.preferred_crops = payload.crops
    if payload.farming_type is not None:
        fp.farming_type = payload.farming_type
    if payload.profile_image is not None:
        current_user.profile_image = payload.profile_image
    db.commit()
    return {"status": "success", "data": {**_profile_dict(db, current_user, current_user), "message": "Profile updated"}}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@router.get("/search")
def search(
    q: str = Query("", min_length=1),
    type: str = Query("all", pattern="^(all|post|short|farmer|hashtag)$"),
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    query = q.strip()
    result = {"query": query, "posts": [], "shorts": [], "farmers": [], "hashtags": []}

    if type in ("all", "post"):
        posts = (
            db.query(FarmBuzzPost)
            .filter(FarmBuzzPost.is_active == True, FarmBuzzPost.content_type == "post")
            .filter(
                FarmBuzzPost.caption.ilike(f"%{query}%")
                | FarmBuzzPost.title.ilike(f"%{query}%")
                | FarmBuzzPost.location.ilike(f"%{query}%")
                | FarmBuzzPost.crop.ilike(f"%{query}%")
            )
            .order_by(FarmBuzzPost.created_at.desc())
            .limit(limit)
            .all()
        )
        posts = [p for p in posts if _can_view_post(db, p, current_user)]
        result["posts"] = [_post_to_dict(db, p, current_user) for p in posts]

    if type in ("all", "short"):
        shorts = (
            db.query(FarmBuzzPost)
            .filter(FarmBuzzPost.is_active == True, FarmBuzzPost.content_type == "short")
            .filter(
                FarmBuzzPost.caption.ilike(f"%{query}%")
                | FarmBuzzPost.title.ilike(f"%{query}%")
                | FarmBuzzPost.crop.ilike(f"%{query}%")
            )
            .order_by(FarmBuzzPost.created_at.desc())
            .limit(limit)
            .all()
        )
        shorts = [s for s in shorts if _can_view_post(db, s, current_user)]
        result["shorts"] = [_post_to_dict(db, s, current_user) for s in shorts]

    if type in ("all", "farmer"):
        farmers = (
            db.query(User)
            .filter(
                User.full_name.ilike(f"%{query}%")
                | User.farmer_id.ilike(f"%{query}%")
            )
            .limit(limit)
            .all()
        )
        result["farmers"] = [
            {"id": u.id, "farmer_id": u.farmer_id, "full_name": u.full_name, "profile_image": u.profile_image}
            for u in farmers
        ]

    if type in ("all", "hashtag"):
        hashtags = (
            db.query(FarmBuzzHashtag)
            .filter(FarmBuzzHashtag.tag.ilike(f"%{query.lstrip('#')}%"))
            .order_by(FarmBuzzHashtag.post_count.desc())
            .limit(limit)
            .all()
        )
        result["hashtags"] = [{"tag": h.tag, "post_count": h.post_count} for h in hashtags]

    return {"status": "success", "data": result}


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------
@router.get("/trends")
def get_trends(
    category: Optional[str] = None,
    limit: int = Query(30, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    _seed_trends(db)
    q = db.query(FarmBuzzTrend).filter(FarmBuzzTrend.is_active == True)
    if category and category.lower() != "all":
        q = q.filter(FarmBuzzTrend.category == category.lower())
    items = q.order_by(FarmBuzzTrend.engagement_score.desc()).limit(limit).all()

    week_ago = datetime.utcnow() - timedelta(days=7)
    hot_posts = (
        db.query(FarmBuzzPost)
        .filter(
            FarmBuzzPost.is_active == True,
            FarmBuzzPost.created_at >= week_ago,
        )
        .order_by(
            (FarmBuzzPost.likes_count + FarmBuzzPost.comments_count * 2
             + FarmBuzzPost.shares_count * 3 + FarmBuzzPost.views_count * 0.05).desc()
        )
        .limit(10)
        .all()
    )
    hot_posts = [p for p in hot_posts if _can_view_post(db, p, current_user)]

    return {
        "status": "success",
        "data": {
            "trends": [
                {
                    "id": t.id,
                    "trend_id": t.trend_id,
                    "topic": t.topic,
                    "category": t.category,
                    "description": t.description,
                    "engagement_score": t.engagement_score,
                    "icon": t.icon,
                    "created_at": str(t.created_at) if t.created_at else None,
                }
                for t in items
            ],
            "hot_posts": [_post_to_dict(db, p, current_user) for p in hot_posts],
        },
    }


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------
@router.get("/stories")
def list_stories(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Active (unexpired) stories, newest first. Authors with no visible story
    are omitted; each returned story carries its own author metadata."""
    now = datetime.utcnow()
    q = db.query(FarmBuzzStory).filter(
        FarmBuzzStory.is_active == True,
        or_(FarmBuzzStory.expires_at.is_(None), FarmBuzzStory.expires_at >= now),
    )
    # A user's own expired-check; followers-only / private visibility is not
    # supported for stories (all public), but soft-deleted users are excluded.
    q = q.join(User).filter(User.is_active == True)
    items = q.order_by(FarmBuzzStory.created_at.desc()).all()
    return {
        "status": "success",
        "data": {
            "total": len(items),
            "items": [_story_to_dict(db, s, current_user) for s in items],
        },
    }


@router.post("/stories", status_code=201)
def create_story(
    payload: StoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media_type = (payload.media_type or "text").lower()
    if media_type not in {"image", "video", "text"}:
        raise HTTPException(status_code=400, detail="media_type must be image, video or text")
    if media_type != "text" and not payload.media_url:
        raise HTTPException(status_code=400, detail="media_url is required for image/video stories")
    if media_type == "text" and not (payload.caption or "").strip():
        raise HTTPException(status_code=400, detail="Add a caption to your text story")
    if payload.media_url and not str(payload.media_url).startswith("/api/v1/farmbuzz/media/"):
        raise HTTPException(status_code=400, detail="media_url must come from a FarmBuzz upload")

    expires_hours = payload.expires_in_hours or 24
    if not (1 <= expires_hours <= 168):
        raise HTTPException(status_code=400, detail="expires_in_hours must be between 1 and 168")

    story_id = generate_id("FA-ST", db, FarmBuzzStory)
    story = FarmBuzzStory(
        story_id=story_id,
        user_id=current_user.id,
        media_url=payload.media_url,
        media_type=media_type,
        thumbnail_url=payload.thumbnail_url,
        caption=payload.caption,
        background_color=payload.background_color,
        is_active=True,
        expires_at=datetime.utcnow() + timedelta(hours=expires_hours),
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return {
        "status": "success",
        "data": {**_story_to_dict(db, story, current_user), "message": "Story published"},
    }


@router.delete("/stories/{story_id}")
def delete_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story = _resolve_story(db, story_id)
    if story.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own stories")
    story.is_active = False
    db.commit()
    return {"status": "success", "data": {"story_id": story.story_id, "message": "Story deleted"}}


@router.post("/stories/{story_id}/view")
def view_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    story = _resolve_story(db, story_id)
    if current_user and current_user.id == story.user_id:
        return {
            "status": "success",
            "data": {"story_id": story.story_id, "is_new_view": False, "views_count": story.views_count or 0},
        }
    existing = None
    if current_user:
        existing = (
            db.query(FarmBuzzStoryViewer)
            .filter(FarmBuzzStoryViewer.story_id == story.id, FarmBuzzStoryViewer.user_id == current_user.id)
            .first()
        )
    if not existing:
        if current_user:
            db.add(FarmBuzzStoryViewer(story_id=story.id, user_id=current_user.id))
        story.views_count = (story.views_count or 0) + 1
        is_new = True
    else:
        is_new = False
    db.commit()
    db.refresh(story)
    return {
        "status": "success",
        "data": {"story_id": story.story_id, "is_new_view": is_new, "views_count": story.views_count or 0},
    }


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------
@router.post("/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    kind: str = Query("image", pattern="^(image|video)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filename = file.filename or "file"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content = await file.read()

    if kind == "image":
        if ext not in IMAGE_EXTS:
            raise HTTPException(status_code=400, detail=f"Unsupported image type. Allowed: {', '.join(sorted(IMAGE_EXTS))}")
        max_bytes = IMAGE_MAX_MB * 1024 * 1024
    else:
        if ext not in VIDEO_EXTS:
            raise HTTPException(status_code=400, detail=f"Unsupported video type. Allowed: {', '.join(sorted(VIDEO_EXTS))}")
        max_bytes = VIDEO_MAX_MB * 1024 * 1024

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max {IMAGE_MAX_MB if kind == 'image' else VIDEO_MAX_MB}MB for {kind}s",
        )

    storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
    year_month = datetime.utcnow().strftime("%Y/%m")
    save_dir = storage_root / "farmbuzz" / year_month
    save_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    with open(save_dir / unique_name, "wb") as f:
        f.write(content)

    relative = f"farmbuzz/{year_month}/{unique_name}"
    return {
        "status": "success",
        "data": {
            "file_name": filename,
            "content_type": file.content_type,
            "size_bytes": len(content),
            "size_mb": round(len(content) / (1024 * 1024), 2),
            "kind": kind,
            "url": f"/api/v1/farmbuzz/media/{relative}",
            "message": "Upload successful",
        },
    }


@router.get("/media/{file_path:path}")
def serve_media(file_path: str):
    storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
    full_path = (storage_root / file_path).resolve()
    if not str(full_path).startswith(str(storage_root) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if full_path.exists() and full_path.is_file():
        return FileResponse(full_path)
    raise HTTPException(status_code=404, detail="File not found")
