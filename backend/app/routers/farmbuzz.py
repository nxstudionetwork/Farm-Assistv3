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
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_db
from app.utils.auth import get_current_user, get_optional_user, generate_id
from app.models.user import User, FarmerProfile
from app.models.notification import Notification
from app.models.farmbuzz import (
    FarmBuzzPost, FarmBuzzComment, FarmBuzzLike, FarmBuzzSave,
    FarmBuzzShare, FarmBuzzFollow, FarmBuzzHashtag, FarmBuzzTrend,
)

router = APIRouter(prefix="/api/v1/farmbuzz", tags=["FarmBuzz"])

CATEGORIES = {
    "Farming", "Crop", "Machinery", "Market", "Success Story",
    "Question", "Tip", "Community", "Other",
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


def _author_of(db: Session, user_id: str) -> dict:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return {"id": None, "farmer_id": None, "full_name": "Farmer", "profile_image": None}
    return {
        "id": u.id,
        "farmer_id": u.farmer_id,
        "full_name": u.full_name,
        "profile_image": u.profile_image,
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
    sort: str = Query("recent", pattern="^(recent|trending)$"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    q = db.query(FarmBuzzPost).filter(FarmBuzzPost.is_active == True)
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
    if sort == "trending":
        order = (
            FarmBuzzPost.likes_count + FarmBuzzPost.comments_count * 2
            + FarmBuzzPost.shares_count * 3 + FarmBuzzPost.views_count * 0.05
        ).desc()
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


@router.get("/posts/{post_id}")
def get_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    post = _resolve_post(db, post_id)
    post.views_count = (post.views_count or 0) + 1
    db.commit()

    comments = (
        db.query(FarmBuzzComment)
        .filter(FarmBuzzComment.post_id == post.id)
        .order_by(FarmBuzzComment.created_at.asc())
        .all()
    )
    comment_list = []
    for c in comments:
        comment_list.append({
            "id": c.id,
            "user_id": c.user_id,
            "content": c.content,
            "created_at": str(c.created_at) if c.created_at else None,
            "author": _author_of(db, c.user_id),
        })

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


@router.post("/posts/{post_id}/save")
def toggle_save(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
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


@router.post("/posts/{post_id}/share")
def share_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _resolve_post(db, post_id)
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
