import threading
from datetime import datetime, time as dtime, date as ddate, timedelta
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.utils.notification_helper import create_notification
from app.models.user import User, FarmerProfile
from app.models.farm import Farm
from app.models.notification import Notification
from app.models.community import (
    CommunityPost, CommunityComment, CommunityLike, CommunitySave, CommunityAnswer,
    CommunityGroup, CommunityGroupMember, CommunityReport, Expert, Consultation
)
# The follow relationship already exists in Farm Buzz; Community reads it rather
# than creating a second, parallel follow system.
from app.models.farmbuzz import FarmBuzzFollow

router = APIRouter(prefix="/api/v1", tags=["Community & Experts"])

# Booking availability window. Slots are offered between SLOT_START_HOUR and
# SLOT_END_HOUR in SLOT_MINUTES increments.
SLOT_START_HOUR = 9
SLOT_END_HOUR = 17
SLOT_MINUTES = 30

# Consultations holding a slot so it cannot be re-booked.
BOOKED_STATUSES = ("scheduled", "requested", "confirmed", "in_progress")

_booking_lock = threading.Lock()

# Accepted community categories (frontend mirrors this list).
CATEGORIES = [
    "All", "Crops", "Rice", "Vegetables", "Horticulture", "Soil",
    "Irrigation", "Pest & Disease", "Organic Farming", "Livestock",
    "Farm Machinery", "Markets", "Government Schemes", "Weather",
    "Technology", "Sustainability", "General",
]
DEFAULT_CATEGORY = "General"

# Accepted post types ("text" is the column default on pre-existing rows).
POST_TYPES = ("discussion", "question", "experience", "advice", "text")


def _normalize_post_type(value) -> str:
    ptype = (value or "").strip().lower()
    if ptype not in POST_TYPES:
        raise HTTPException(status_code=400, detail="Invalid post type")
    return ptype


# ---------------------------------------------------------------- Pydantic
class PostCreate(BaseModel):
    content: str
    title: Optional[str] = None
    category: Optional[str] = None
    crop: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None
    post_type: Optional[str] = "text"
    community_id: Optional[str] = None


class PostUpdate(BaseModel):
    content: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    crop: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None
    post_type: Optional[str] = None


class CommentCreate(BaseModel):
    content: Optional[str] = None
    text: Optional[str] = None
    parent_comment_id: Optional[str] = None


class AnswerCreate(BaseModel):
    content: str


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None


class ReportCreate(BaseModel):
    post_id: Optional[str] = None
    comment_id: Optional[str] = None
    reason: str
    description: Optional[str] = None


class ConsultationCreate(BaseModel):
    expert_id: str
    topic: str
    description: Optional[str] = None
    consultation_type: Optional[str] = None
    consultation_method: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    farm_id: Optional[str] = None
    farm_name: Optional[str] = None
    crop_id: Optional[str] = None
    crop_name: Optional[str] = None


class ConsultationUpdate(BaseModel):
    status: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    cancel_reason: Optional[str] = None
    notes: Optional[str] = None


class ConsultationReview(BaseModel):
    rating: float
    feedback: Optional[str] = None


# ---------------------------------------------------------------- Helpers
def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_slot_time(value: Optional[str]):
    if not value:
        return None
    text = str(value).strip().upper()
    try:
        tm = datetime.strptime(text, "%I:%M %p")
    except ValueError:
        try:
            tm = datetime.strptime(text, "%H:%M")
        except ValueError:
            return None
    return tm.hour * 60 + tm.minute


def _now_minutes():
    now = datetime.now()
    return now.hour * 60 + now.minute


def _slot_minutes_to_label(minutes):
    hour = minutes // 60
    minute = minutes % 60
    mer = "AM" if hour < 12 else "PM"
    h12 = hour % 12
    if h12 == 0:
        h12 = 12
    return f"{h12:02d}:{minute:02d} {mer}"


def _slot_labels():
    start_minutes = SLOT_START_HOUR * 60
    end_minutes = SLOT_END_HOUR * 60
    labels = []
    for minutes in range(start_minutes, end_minutes + 1, SLOT_MINUTES):
        labels.append(_slot_minutes_to_label(minutes))
    return labels


def _format_slot_time(value):
    minutes = _parse_slot_time(value)
    if minutes is None:
        return None
    return _slot_minutes_to_label(minutes)


def _lookup_expert(db: Session, expert_id: str):
    expert = db.query(Expert).filter(Expert.id == expert_id).first()
    if not expert:
        expert = db.query(Expert).filter(Expert.expert_id == expert_id).first()
    return expert


def _available_slots(db: Session, expert: Expert, target_date, exclude_id: Optional[str] = None):
    q = db.query(Consultation).filter(
        Consultation.expert_id == expert.id,
        Consultation.scheduled_date == target_date.isoformat(),
        Consultation.status.in_(BOOKED_STATUSES),
    )
    if exclude_id:
        q = q.filter(Consultation.id != exclude_id)
    taken = set()
    for c in q.all():
        label = _format_slot_time(c.scheduled_time)
        if label:
            taken.add(label)

    today = ddate.today()
    now_minutes = _now_minutes()
    available = []
    for label in _slot_labels():
        if label in taken:
            continue
        minutes = _parse_slot_time(label)
        if target_date == today and minutes is not None and minutes <= now_minutes:
            continue
        available.append(label)
    return available


def _find_slot_conflict(db: Session, expert: Expert, target_date, target_time,
                        exclude_id: Optional[str] = None):
    label = _format_slot_time(target_time)
    if not label:
        return None
    q = db.query(Consultation).filter(
        Consultation.expert_id == expert.id,
        Consultation.scheduled_date == target_date.isoformat(),
        Consultation.status.in_(BOOKED_STATUSES),
    )
    if exclude_id:
        q = q.filter(Consultation.id != exclude_id)
    for c in q.all():
        if _format_slot_time(c.scheduled_time) == label:
            return c
    return None


def _expert_dict(e: Expert) -> dict:
    return {
        "id": e.id,
        "expert_id": e.expert_id,
        "full_name": e.full_name,
        "speciality": e.speciality,
        "qualification": e.qualification,
        "experience_years": e.experience_years,
        "bio": e.bio,
        "consultation_fee": e.consultation_fee,
        "fee": e.consultation_fee,
        "rating": e.rating,
        "total_consultations": e.total_consultations,
        "is_available": e.is_available,
        "location": e.location,
        "languages": e.languages,
        "profile_image": e.profile_image,
    }


def _consultation_dict(c: Consultation, expert: Optional[Expert] = None) -> dict:
    name = expert.full_name if expert else "Unknown"
    spec = expert.speciality if expert else ""
    return {
        "id": c.id,
        "consultation_id": c.consultation_id,
        "reference_id": c.consultation_id,
        "expert_id": expert.id if expert else None,
        "expert_name": name,
        "expert_speciality": spec,
        "expert_qualification": expert.qualification if expert else "",
        "expert_experience": expert.experience_years if expert else None,
        "expert_rating": expert.rating if expert else 0,
        "expert_fee": expert.consultation_fee if expert else 0,
        "expert_location": expert.location if expert else "",
        "expert_profile_image": expert.profile_image if expert else None,
        "expert_languages": expert.languages if expert else [],
        "expert_is_available": expert.is_available if expert else None,
        "farmer_id": c.farmer_id,
        "topic": c.topic,
        "description": c.description,
        "consultation_type": c.consultation_type,
        "consultation_method": c.consultation_method,
        "scheduled_date": c.scheduled_date,
        "scheduled_time": c.scheduled_time,
        "farm_id": c.farm_id,
        "farm_name": c.farm_name,
        "crop_id": c.crop_id,
        "crop_name": c.crop_name,
        "status": c.status,
        "meeting_reference": c.meeting_reference,
        "meeting_location": c.meeting_location,
        "rating": c.rating,
        "feedback": c.feedback,
        "cancel_reason": c.cancel_reason,
        "notes": c.notes,
        "created_at": str(c.created_at) if c.created_at else None,
        "completed_at": str(c.completed_at) if c.completed_at else None,
        "cancelled_at": str(c.cancelled_at) if c.cancelled_at else None,
    }


def _normalize_category(cat):
    if not cat:
        return DEFAULT_CATEGORY
    cat = str(cat).strip()
    if not cat or cat.lower() == "all":
        return DEFAULT_CATEGORY
    return cat


def _find_post(db: Session, post_id: str):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        post = db.query(CommunityPost).filter(CommunityPost.post_id == post_id).first()
    return post


def _find_comment(db: Session, comment_id: str):
    return db.query(CommunityComment).filter(CommunityComment.id == comment_id).first()


def _find_group(db: Session, group_id: str):
    group = db.query(CommunityGroup).filter(CommunityGroup.id == group_id).first()
    if not group:
        group = db.query(CommunityGroup).filter(CommunityGroup.community_id == group_id).first()
    return group


def _public_user(db: Session, user: Optional[User]) -> dict:
    """Only public profile info. Never phone/email/private farmer id."""
    if not user:
        return None
    profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == user.id).first()
    return {
        "id": user.id,
        "full_name": user.full_name,
        "profile_image": user.profile_image,
        "bio": profile.bio if profile else None,
        "farm_location": profile.farm_location if profile else None,
        "farming_type": profile.farming_type if profile else None,
        "is_verified": user.is_verified,
    }


def _post_dict(db: Session, p: CommunityPost, current_user: User) -> dict:
    author = db.query(User).filter(User.id == p.user_id).first() if p.user_id else None
    is_liked = db.query(CommunityLike).filter(
        CommunityLike.post_id == p.id, CommunityLike.user_id == current_user.id
    ).first() is not None
    is_saved = db.query(CommunitySave).filter(
        CommunitySave.post_id == p.id, CommunitySave.user_id == current_user.id
    ).first() is not None
    group = db.query(CommunityGroup).filter(CommunityGroup.id == p.community_id).first() if p.community_id else None
    answer_count = db.query(CommunityAnswer).filter(CommunityAnswer.post_id == p.id).count()
    return {
        "id": p.id,
        "post_id": p.post_id,
        "user_id": p.user_id,
        "community_id": p.community_id,
        "community_name": group.name if group else None,
        "title": p.title,
        "content": p.content,
        "category": p.category or DEFAULT_CATEGORY,
        "crop": p.crop,
        "location": p.location,
        "image_url": p.image_url,
        "image": p.image_url,
        "media_type": p.media_type or "text",
        "post_type": p.post_type or "text",
        "likes_count": p.likes_count or 0,
        "comments_count": p.comments_count or 0,
        "shares_count": p.shares_count or 0,
        "saves_count": p.saves_count or 0,
        "answer_count": answer_count,
        "is_liked": is_liked,
        "is_saved": is_saved,
        "is_owner": p.user_id == current_user.id,
        "created_at": str(p.created_at) if p.created_at else None,
        "author": _public_user(db, author),
        "author_name": author.full_name if author else "Farmer",
        "author_image": author.profile_image if author else None,
    }


def _posts_payload(db: Session, posts, current_user: User) -> list:
    """Serialize many posts with batched lookups instead of per-post queries."""
    if not posts:
        return []

    author_ids = {p.user_id for p in posts if p.user_id}
    group_ids = {p.community_id for p in posts if p.community_id}
    post_ids = [p.id for p in posts]

    authors = {u.id: u for u in db.query(User).filter(User.id.in_(author_ids)).all()} if author_ids else {}
    profiles = {}
    if author_ids:
        for fp in db.query(FarmerProfile).filter(FarmerProfile.user_id.in_(author_ids)).all():
            profiles[fp.user_id] = fp
    groups = (
        {g.id: g for g in db.query(CommunityGroup).filter(CommunityGroup.id.in_(group_ids)).all()}
        if group_ids else {}
    )

    liked_ids = {
        row[0] for row in db.query(CommunityLike.post_id).filter(
            CommunityLike.post_id.in_(post_ids), CommunityLike.user_id == current_user.id
        ).all()
    }
    saved_ids = {
        row[0] for row in db.query(CommunitySave.post_id).filter(
            CommunitySave.post_id.in_(post_ids), CommunitySave.user_id == current_user.id
        ).all()
    }
    answer_counts = dict(
        db.query(CommunityAnswer.post_id, func.count(CommunityAnswer.id))
        .filter(CommunityAnswer.post_id.in_(post_ids))
        .group_by(CommunityAnswer.post_id)
        .all()
    )

    def public_user(user):
        if not user:
            return None
        profile = profiles.get(user.id)
        return {
            "id": user.id,
            "full_name": user.full_name,
            "profile_image": user.profile_image,
            "bio": profile.bio if profile else None,
            "farm_location": profile.farm_location if profile else None,
            "farming_type": profile.farming_type if profile else None,
            "is_verified": user.is_verified,
        }

    payload = []
    for p in posts:
        author = authors.get(p.user_id)
        group = groups.get(p.community_id) if p.community_id else None
        payload.append({
            "id": p.id,
            "post_id": p.post_id,
            "user_id": p.user_id,
            "community_id": p.community_id,
            "community_name": group.name if group else None,
            "title": p.title,
            "content": p.content,
            "category": p.category or DEFAULT_CATEGORY,
            "crop": p.crop,
            "location": p.location,
            "image_url": p.image_url,
            "image": p.image_url,
            "media_type": p.media_type or "text",
            "post_type": p.post_type or "text",
            "likes_count": p.likes_count or 0,
            "comments_count": p.comments_count or 0,
            "shares_count": p.shares_count or 0,
            "saves_count": p.saves_count or 0,
            "answer_count": answer_counts.get(p.id, 0),
            "is_liked": p.id in liked_ids,
            "is_saved": p.id in saved_ids,
            "is_owner": p.user_id == current_user.id,
            "created_at": str(p.created_at) if p.created_at else None,
            "author": public_user(author),
            "author_name": author.full_name if author else "Farmer",
            "author_image": author.profile_image if author else None,
        })
    return payload


def _comments_payload(db: Session, comments, current_user: User) -> list:
    """Serialize comments (and their parents for reply context) in batch."""
    if not comments:
        return []
    user_ids = {c.user_id for c in comments if c.user_id}
    parent_ids = {c.parent_comment_id for c in comments if c.parent_comment_id}
    parents = {}
    if parent_ids:
        for pc in db.query(CommunityComment).filter(CommunityComment.id.in_(parent_ids)).all():
            parents[pc.id] = pc
            if pc.user_id:
                user_ids.add(pc.user_id)
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    result = []
    for c in comments:
        author = users.get(c.user_id)
        parent = parents.get(c.parent_comment_id) if c.parent_comment_id else None
        parent_author = users.get(parent.user_id) if parent else None
        result.append({
            "id": c.id,
            "user_id": c.user_id,
            "parent_comment_id": c.parent_comment_id,
            "reply_to_name": parent_author.full_name if parent_author else None,
            "content": c.content,
            "author_name": author.full_name if author else "Farmer",
            "author_image": author.profile_image if author else None,
            "is_owner": c.user_id == current_user.id,
            "created_at": str(c.created_at) if c.created_at else None,
        })
    return result


def _answers_payload(db: Session, answers, post: CommunityPost, current_user: User) -> list:
    """Serialize answers with batched author lookup."""
    if not answers:
        return []
    user_ids = {a.user_id for a in answers if a.user_id}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    can_mark_best = post.user_id == current_user.id

    return [
        {
            "id": a.id,
            "answer_id": a.answer_id,
            "post_id": a.post_id,
            "user_id": a.user_id,
            "content": a.content,
            "is_best_answer": bool(a.is_best_answer),
            "author_name": users[a.user_id].full_name if a.user_id in users else "Farmer",
            "author_image": users[a.user_id].profile_image if a.user_id in users else None,
            "is_owner": a.user_id == current_user.id,
            "can_mark_best": can_mark_best,
            "created_at": str(a.created_at) if a.created_at else None,
        }
        for a in answers
    ]


def _notify(db: Session, user_id, title, message, icon, post: CommunityPost,
            reference_type: str = "community_post"):
    """Queue a community notification. create_notification does not commit, so
    this stays inside the caller's transaction."""
    if not user_id:
        return
    create_notification(
        db=db,
        user_id=user_id,
        title=title,
        message=message,
        notification_type="community",
        reference_id=post.post_id,
        reference_type=reference_type,
        icon=icon,
        action_url=f"community.html?post={post.post_id}",
    )


# ---------------------------------------------------------------- Community Posts

@router.get("/communities/feed")
def community_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    search: Optional[str] = None,
    category: Optional[str] = None,
    community_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated community feed with optional search + category filter."""
    q = db.query(CommunityPost).filter(CommunityPost.is_active == True)
    if search:
        term = f"%{search.strip()}%"
        q = q.outerjoin(User, User.id == CommunityPost.user_id).filter(
            (CommunityPost.content.ilike(term))
            | (CommunityPost.title.ilike(term))
            | (CommunityPost.category.ilike(term))
            | (CommunityPost.crop.ilike(term))
            | (CommunityPost.location.ilike(term))
            | (User.full_name.ilike(term))
        )
    if category and category.lower() != "all":
        q = q.filter(CommunityPost.category == _normalize_category(category))
    if community_id:
        group = _find_group(db, community_id)
        if group:
            q = q.filter(CommunityPost.community_id == group.id)
        else:
            return {"status": "success", "data": {"total": 0, "page": page, "limit": limit, "total_pages": 0, "items": []}}

    total = q.count()
    items = (
        q.order_by(CommunityPost.created_at.desc(), CommunityPost.id.desc())
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
            "total_pages": (total + limit - 1) // limit,
            "items": _posts_payload(db, items, current_user),
        },
    }


@router.get("/posts")
def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    post_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backward-compatible list posts endpoint (used by older frontends)."""
    q = db.query(CommunityPost).filter(CommunityPost.is_active == True)
    if search:
        term = f"%{search}%"
        q = q.filter(CommunityPost.content.ilike(term) | CommunityPost.title.ilike(term))
    if post_type:
        q = q.filter(CommunityPost.post_type == post_type)

    total = q.count()
    items = q.order_by(CommunityPost.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    user_ids = {p.user_id for p in items if p.user_id}
    users = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            users[u.id] = u

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
                    "post_id": p.post_id,
                    "user_id": p.user_id,
                    "content": p.content,
                    "title": p.title or (p.content or "")[:80],
                    "image_url": p.image_url,
                    "post_type": p.post_type,
                    "likes_count": p.likes_count,
                    "comments_count": p.comments_count,
                    "shares_count": p.shares_count,
                    "created_at": str(p.created_at) if p.created_at else None,
                    "author_name": users[p.user_id].full_name if p.user_id in users else "Farmer",
                    "author_image": users[p.user_id].profile_image if p.user_id in users else None,
                    "image": p.image_url,
                }
                for p in items
            ],
        },
    }


@router.get("/communities/categories")
def community_categories():
    """Return the list of supported community categories (All + real ones)."""
    return {"status": "success", "data": list(CATEGORIES)}


@router.post("/posts", status_code=201)
def create_post(
    payload: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Post content is required")
    if len(content) < 2:
        raise HTTPException(status_code=400, detail="Post content is too short")

    category = _normalize_category(payload.category)

    community_id = None
    if payload.community_id:
        group = _find_group(db, payload.community_id)
        if not group:
            raise HTTPException(status_code=404, detail="Community not found")
        community_id = group.id

    post_id = generate_id("FA-PST", db, CommunityPost)
    post = CommunityPost(
        post_id=post_id,
        user_id=current_user.id,
        community_id=community_id,
        title=(payload.title or "").strip() or None,
        content=content,
        category=category,
        crop=(payload.crop or "").strip() or None,
        location=(payload.location or "").strip() or None,
        image_url=payload.image_url,
        media_type="image" if payload.image_url else "text",
        post_type=_normalize_post_type(payload.post_type or "text"),
        is_active=True,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return {
        "status": "success",
        "message": "Post created successfully",
        "data": _posts_payload(db, [post], current_user)[0],
    }


@router.get("/posts/{post_id}")
def get_post(post_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comments = db.query(CommunityComment).filter(
        CommunityComment.post_id == post.id
    ).order_by(CommunityComment.created_at.asc()).all()

    answers = db.query(CommunityAnswer).filter(
        CommunityAnswer.post_id == post.id
    ).order_by(CommunityAnswer.is_best_answer.desc(), CommunityAnswer.created_at.asc()).all()

    data = _post_dict(db, post, current_user)
    data["comments"] = _comments_payload(db, comments, current_user)
    data["answers"] = _answers_payload(db, answers, post, current_user)
    return {"status": "success", "data": data}


@router.patch("/posts/{post_id}")
def update_post(
    post_id: str,
    payload: PostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own posts")

    if payload.content is not None:
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="Post content is required")
        post.content = content
    if payload.title is not None:
        post.title = payload.title.strip() or None
    if payload.category is not None:
        post.category = _normalize_category(payload.category)
    if payload.crop is not None:
        post.crop = payload.crop.strip() or None
    if payload.location is not None:
        post.location = payload.location.strip() or None
    if payload.image_url is not None:
        post.image_url = payload.image_url
        post.media_type = "image" if payload.image_url else "text"
    if payload.post_type is not None:
        post.post_type = _normalize_post_type(payload.post_type)

    db.commit()
    db.refresh(post)
    return {
        "status": "success",
        "message": "Post updated",
        "data": _posts_payload(db, [post], current_user)[0],
    }


@router.delete("/posts/{post_id}")
def delete_post(post_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own posts")
    db.delete(post)
    db.commit()
    return {"status": "success", "message": "Post deleted"}


# ---------------------------------------------------------------- Comments
@router.get("/posts/{post_id}/comments")
def list_post_comments(post_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comments = db.query(CommunityComment).filter(
        CommunityComment.post_id == post.id
    ).order_by(CommunityComment.created_at.asc()).all()
    return {"status": "success", "data": _comments_payload(db, comments, current_user)}


@router.post("/posts/{post_id}/comments", status_code=201)
def add_comment(
    post_id: str,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = (payload.content or payload.text or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment content is required")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="Comment is too long (max 2000 characters)")

    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    parent = None
    if payload.parent_comment_id:
        parent = db.query(CommunityComment).filter(
            CommunityComment.id == payload.parent_comment_id,
            CommunityComment.post_id == post.id,
        ).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Invalid parent comment")
        # Keep threads one level deep so replies always render under a top-level comment.
        if parent.parent_comment_id:
            parent = db.query(CommunityComment).filter(
                CommunityComment.id == parent.parent_comment_id
            ).first() or parent

    comment = CommunityComment(
        post_id=post.id,
        user_id=current_user.id,
        parent_comment_id=parent.id if parent else None,
        content=content,
    )
    db.add(comment)
    post.comments_count = (post.comments_count or 0) + 1

    # Notify the post author, and separately the author of the comment being
    # replied to. Both are skipped when they are the person writing the comment.
    if parent is not None and parent.user_id != current_user.id:
        _notify(db, parent.user_id, "New Reply",
                f"{current_user.full_name} replied to your comment.",
                "fa-reply", post, reference_type="community_comment")
    if post.user_id != current_user.id and post.user_id != (parent.user_id if parent else None):
        _notify(db, post.user_id, "New Comment",
                f"{current_user.full_name} commented on your community post.",
                "fa-comment", post)

    db.commit()
    db.refresh(comment)

    return {
        "status": "success",
        "message": "Comment added successfully",
        "data": _comments_payload(db, [comment], current_user)[0],
    }


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = _find_comment(db, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")

    post = db.query(CommunityPost).filter(CommunityPost.id == comment.post_id).first()
    # Deleting a parent cascades to its replies, so count every row being removed.
    removed = 1 + db.query(CommunityComment).filter(
        CommunityComment.parent_comment_id == comment.id
    ).count()

    db.delete(comment)
    if post:
        post.comments_count = max((post.comments_count or removed) - removed, 0)
    db.commit()
    return {"status": "success", "message": "Comment deleted"}


# ---------------------------------------------------------------- Likes
@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = db.query(CommunityLike).filter(
        CommunityLike.post_id == post.id, CommunityLike.user_id == current_user.id
    ).first()

    if existing:
        db.delete(existing)
        liked = False
        message = "Post unliked"
    else:
        db.add(CommunityLike(post_id=post.id, user_id=current_user.id))
        liked = True
        message = "Post liked"
        if post.user_id != current_user.id:
            _notify(db, post.user_id, "New Like",
                    f"{current_user.full_name} liked your community post.",
                    "fa-heart", post)

    db.flush()
    # Derive the counter from the relationship rows so it can never drift.
    post.likes_count = db.query(func.count(CommunityLike.id)).filter(
        CommunityLike.post_id == post.id
    ).scalar() or 0
    db.commit()
    db.refresh(post)

    return {
        "status": "success",
        "data": {
            "post_id": post.post_id,
            "is_liked": liked,
            "likes_count": post.likes_count,
            "message": message,
        },
    }


@router.delete("/posts/{post_id}/like")
def remove_like(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotent unlike: unliking a post you never liked is not an error."""
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    db.query(CommunityLike).filter(
        CommunityLike.post_id == post.id, CommunityLike.user_id == current_user.id
    ).delete(synchronize_session=False)
    db.flush()
    post.likes_count = db.query(func.count(CommunityLike.id)).filter(
        CommunityLike.post_id == post.id
    ).scalar() or 0
    db.commit()

    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_liked": False, "likes_count": post.likes_count, "message": "Post unliked"},
    }


# ---------------------------------------------------------------- Save / Bookmark
@router.post("/posts/{post_id}/save")
def save_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = db.query(CommunitySave).filter(
        CommunitySave.post_id == post.id, CommunitySave.user_id == current_user.id
    ).first()

    if existing:
        db.delete(existing)
        saved = False
        message = "Post removed from saved"
    else:
        db.add(CommunitySave(post_id=post.id, user_id=current_user.id))
        saved = True
        message = "Post saved"

    db.flush()
    post.saves_count = db.query(func.count(CommunitySave.id)).filter(
        CommunitySave.post_id == post.id
    ).scalar() or 0
    db.commit()
    db.refresh(post)
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_saved": saved, "saves_count": post.saves_count, "message": message},
    }


@router.delete("/posts/{post_id}/save")
def remove_save(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotent unsave: only ever removes the authenticated farmer's own save."""
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    db.query(CommunitySave).filter(
        CommunitySave.post_id == post.id, CommunitySave.user_id == current_user.id
    ).delete(synchronize_session=False)
    db.flush()
    post.saves_count = db.query(func.count(CommunitySave.id)).filter(
        CommunitySave.post_id == post.id
    ).scalar() or 0
    db.commit()

    return {
        "status": "success",
        "data": {"post_id": post.post_id, "is_saved": False, "saves_count": post.saves_count, "message": "Post removed from saved"},
    }


@router.get("/posts/saved/list")
def list_saved_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = db.query(CommunityPost).join(
        CommunitySave, CommunitySave.post_id == CommunityPost.id
    ).filter(
        CommunitySave.user_id == current_user.id,
        CommunityPost.is_active == True,
    )
    total = base.count()
    posts = (
        base.order_by(CommunitySave.created_at.desc())
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
            "total_pages": (total + limit - 1) // limit,
            "items": _posts_payload(db, posts, current_user),
        },
    }


# ---------------------------------------------------------------- Answers
@router.post("/posts/{post_id}/answers", status_code=201)
def add_answer(
    post_id: str,
    payload: AnswerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Answer content is required")
    if len(content) > 5000:
        raise HTTPException(status_code=400, detail="Answer is too long (max 5000 characters)")
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if (post.post_type or "text") != "question":
        raise HTTPException(status_code=400, detail="Answers can only be added to question posts")

    answer_id = generate_id("FA-ANS", db, CommunityAnswer)
    answer = CommunityAnswer(
        answer_id=answer_id,
        post_id=post.id,
        user_id=current_user.id,
        content=content,
    )
    db.add(answer)

    if post.user_id != current_user.id:
        _notify(db, post.user_id, "New Answer",
                f"{current_user.full_name} answered your question.",
                "fa-reply", post, reference_type="community_answer")

    db.commit()
    db.refresh(answer)

    return {
        "status": "success",
        "message": "Answer posted successfully",
        "data": _answers_payload(db, [answer], post, current_user)[0],
    }


@router.post("/posts/{post_id}/answers/{answer_id}/best")
def mark_best_answer(
    post_id: str,
    answer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the question author can mark the best answer")

    answer = db.query(CommunityAnswer).filter(CommunityAnswer.id == answer_id).first()
    if not answer:
        answer = db.query(CommunityAnswer).filter(CommunityAnswer.answer_id == answer_id).first()
    if not answer or answer.post_id != post.id:
        raise HTTPException(status_code=404, detail="Answer not found")

    if answer.is_best_answer:
        answer.is_best_answer = False
        message = "Best answer removed"
    else:
        db.query(CommunityAnswer).filter(
            CommunityAnswer.post_id == post.id
        ).update({CommunityAnswer.is_best_answer: False})
        answer.is_best_answer = True
        message = "Marked as best answer"
        if answer.user_id != current_user.id:
            _notify(db, answer.user_id, "Best Answer",
                    f"Your answer was marked as the best answer by {current_user.full_name}.",
                    "fa-crown", post, reference_type="community_best_answer")

    db.commit()

    answers = db.query(CommunityAnswer).filter(
        CommunityAnswer.post_id == post.id
    ).order_by(CommunityAnswer.is_best_answer.desc(), CommunityAnswer.created_at.asc()).all()

    return {
        "status": "success",
        "message": message,
        "data": {
            "is_best_answer": answer.is_best_answer,
            "answers": _answers_payload(db, answers, post, current_user),
        },
    }


# ---------------------------------------------------------------- Groups / Communities


@router.get("/communities/groups")
def list_groups(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CommunityGroup)
    if category and category.lower() != "all":
        q = q.filter(CommunityGroup.category == _normalize_category(category))
    if search:
        term = f"%{search}%"
        q = q.filter(CommunityGroup.name.ilike(term) | CommunityGroup.description.ilike(term))

    total = q.count()
    groups = q.order_by(CommunityGroup.name.asc()).offset((page - 1) * limit).limit(limit).all()

    joined_ids = {
        m.community_id for m in db.query(CommunityGroupMember).filter(
            CommunityGroupMember.user_id == current_user.id
        ).all()
    }

    result = []
    for g in groups:
        member_count = db.query(CommunityGroupMember).filter(
            CommunityGroupMember.community_id == g.id
        ).count()
        result.append({
            "id": g.id,
            "community_id": g.community_id,
            "name": g.name,
            "description": g.description,
            "category": g.category or DEFAULT_CATEGORY,
            "icon": g.icon,
            "color": g.color,
            "member_count": member_count,
            "is_joined": g.id in joined_ids,
        })

    return {"status": "success", "data": {"total": total, "page": page, "limit": limit, "items": result}}


@router.get("/communities/groups/{group_id}")
def get_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _find_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Community not found")

    member_count = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.community_id == group.id
    ).count()
    is_joined = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.community_id == group.id,
        CommunityGroupMember.user_id == current_user.id,
    ).first() is not None

    return {
        "status": "success",
        "data": {
            "id": group.id,
            "community_id": group.community_id,
            "name": group.name,
            "description": group.description,
            "category": group.category or DEFAULT_CATEGORY,
            "icon": group.icon,
            "color": group.color,
            "member_count": member_count,
            "is_joined": is_joined,
            "created_at": str(group.created_at) if group.created_at else None,
        },
    }


@router.post("/communities/groups", status_code=201)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Community name is required")
    existing = db.query(CommunityGroup).filter(CommunityGroup.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A community with this name already exists")

    group_id = generate_id("FA-GRP", db, CommunityGroup)
    group = CommunityGroup(
        community_id=group_id,
        name=name,
        description=payload.description,
        category=_normalize_category(payload.category),
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return {"status": "success", "message": "Community created", "data": {"id": group.id, "community_id": group.community_id, "name": group.name}}


@router.post("/communities/groups/{group_id}/join")
def join_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _find_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Community not found")
    existing = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.community_id == group.id,
        CommunityGroupMember.user_id == current_user.id,
    ).first()
    if existing:
        return {"status": "success", "message": "Already a member", "data": {"is_joined": True}}
    db.add(CommunityGroupMember(community_id=group.id, user_id=current_user.id))
    db.commit()
    return {"status": "success", "message": "Joined community", "data": {"is_joined": True}}


@router.post("/communities/groups/{group_id}/leave")
def leave_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _find_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Community not found")
    existing = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.community_id == group.id,
        CommunityGroupMember.user_id == current_user.id,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
    return {"status": "success", "message": "Left community", "data": {"is_joined": False}}


@router.get("/communities/my-groups")
def my_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    memberships = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.user_id == current_user.id
    ).order_by(CommunityGroupMember.joined_at.desc()).all()

    result = []
    for m in memberships:
        g = db.query(CommunityGroup).filter(CommunityGroup.id == m.community_id).first()
        if g:
            member_count = db.query(CommunityGroupMember).filter(
                CommunityGroupMember.community_id == g.id
            ).count()
            result.append({
                "id": g.id,
                "community_id": g.community_id,
                "name": g.name,
                "description": g.description,
                "category": g.category or DEFAULT_CATEGORY,
                "icon": g.icon,
                "color": g.color,
                "member_count": member_count,
                "is_joined": True,
            })
    return {"status": "success", "data": {"items": result}}


@router.get("/communities/my-activity")
def my_activity(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The authenticated farmer's own community posts and engagement totals.

    Every count is scoped to current_user.id so one farmer can never read
    another farmer's activity through this endpoint.
    """
    uid = current_user.id

    base = db.query(CommunityPost).filter(
        CommunityPost.user_id == uid,
        CommunityPost.is_active == True,
    )
    total = base.count()
    posts = base.order_by(
        CommunityPost.created_at.desc(), CommunityPost.id.desc()
    ).offset((page - 1) * limit).limit(limit).all()

    own_post_ids = [p.id for p in db.query(CommunityPost.id).filter(
        CommunityPost.user_id == uid, CommunityPost.is_active == True
    ).all()]

    likes_received = db.query(func.count(CommunityLike.id)).filter(
        CommunityLike.post_id.in_(own_post_ids)
    ).scalar() or 0

    best_answers_received = db.query(func.count(CommunityAnswer.id)).filter(
        CommunityAnswer.post_id.in_(own_post_ids),
        CommunityAnswer.is_best_answer == True,
    ).scalar() or 0

    stats = {
        "posts": total,
        "questions": db.query(func.count(CommunityPost.id)).filter(
            CommunityPost.user_id == uid,
            CommunityPost.post_type == "question",
            CommunityPost.is_active == True,
        ).scalar() or 0,
        "answers_given": db.query(func.count(CommunityAnswer.id)).filter(
            CommunityAnswer.user_id == uid
        ).scalar() or 0,
        "comments_given": db.query(func.count(CommunityComment.id)).filter(
            CommunityComment.user_id == uid
        ).scalar() or 0,
        "best_answers_received": best_answers_received,
        "likes_received": likes_received,
        "saved_posts": db.query(func.count(CommunitySave.id)).filter(
            CommunitySave.user_id == uid
        ).scalar() or 0,
        "communities_joined": db.query(func.count(CommunityGroupMember.id)).filter(
            CommunityGroupMember.user_id == uid
        ).scalar() or 0,
    }

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total else 0,
            "stats": stats,
            "items": _posts_payload(db, posts, current_user),
        },
    }


# ---------------------------------------------------------------- Reports
@router.post("/report", status_code=201)
def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A report reason is required")
    if not payload.post_id and not payload.comment_id:
        raise HTTPException(status_code=400, detail="Post or comment to report is required")

    post = None
    if payload.post_id:
        post = _find_post(db, payload.post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
    if payload.comment_id and not _find_comment(db, payload.comment_id):
        raise HTTPException(status_code=404, detail="Comment not found")

    report_id = generate_id("FA-RPT", db, CommunityReport)
    report = CommunityReport(
        report_id=report_id,
        reporter_id=current_user.id,
        post_id=post.id if post else None,
        comment_id=payload.comment_id,
        reason=reason,
        description=payload.description,
        status="pending",
    )
    db.add(report)
    db.commit()
    return {"status": "success", "message": "Report submitted successfully", "data": {"report_id": report.report_id}}


# ---------------------------------------------------------------- Farmers
@router.get("/farmers/{farmer_id}/profile")
def get_farmer_public_profile(
    farmer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == farmer_id).first()
    if not user:
        user = db.query(User).filter(User.farmer_id == farmer_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Farmer not found")

    member_count = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.user_id == user.id
    ).count()
    posts_query = db.query(CommunityPost).filter(
        CommunityPost.user_id == user.id, CommunityPost.is_active == True
    )
    posts_count = posts_query.count()
    posts = posts_query.order_by(CommunityPost.created_at.desc()).limit(20).all()

    data = _public_user(db, user)
    data["communities_joined"] = member_count
    data["posts_count"] = posts_count
    data["is_self"] = user.id == current_user.id
    data["is_following"] = db.query(FarmBuzzFollow).filter(
        FarmBuzzFollow.follower_id == current_user.id,
        FarmBuzzFollow.following_id == user.id,
    ).first() is not None
    data["followers_count"] = db.query(FarmBuzzFollow).filter(
        FarmBuzzFollow.following_id == user.id
    ).count()
    data["posts"] = _posts_payload(db, posts, current_user)
    return {"status": "success", "data": data}


# ---------------------------------------------------------------- Share
@router.post("/posts/{post_id}/share")
def share_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = _find_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    post.shares_count = (post.shares_count or 0) + 1
    db.commit()
    return {
        "status": "success",
        "data": {"post_id": post.post_id, "shares_count": post.shares_count},
    }


# ---------------------------------------------------------------- Experts (unchanged)
@router.get("/experts")
def list_experts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    speciality: Optional[str] = None,
    is_available: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Expert)
    if is_available is not None:
        q = q.filter(Expert.is_available == is_available)
    if speciality:
        q = q.filter(Expert.speciality.ilike(f"%{speciality}%"))
    if search:
        q = q.filter(
            Expert.full_name.ilike(f"%{search}%")
            | Expert.speciality.ilike(f"%{search}%")
            | Expert.bio.ilike(f"%{search}%")
        )

    total = q.count()
    items = q.order_by(Expert.rating.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_expert_dict(e) for e in items],
        },
    }


@router.get("/experts/{expert_id}/slots")
def get_expert_slots(
    expert_id: str,
    date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expert = _lookup_expert(db, expert_id)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")

    target = _parse_date(date)
    if not target:
        raise HTTPException(status_code=400, detail="A valid appointment date is required (YYYY-MM-DD)")
    if target < ddate.today():
        raise HTTPException(status_code=400, detail="Appointment date cannot be in the past")

    slots = _available_slots(db, expert, target) if expert.is_available else []

    return {
        "status": "success",
        "data": {
            "expert_id": expert.id,
            "expert_name": expert.full_name,
            "expert_speciality": expert.speciality,
            "date": target.isoformat(),
            "is_available": expert.is_available,
            "slots": slots,
        },
    }


@router.get("/experts/{expert_id}")
def get_expert(expert_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    expert = _lookup_expert(db, expert_id)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")

    return {
        "status": "success",
        "data": {
            "id": expert.id,
            "expert_id": expert.expert_id,
            "full_name": expert.full_name,
            "speciality": expert.speciality,
            "qualification": expert.qualification,
            "experience_years": expert.experience_years,
            "bio": expert.bio,
            "consultation_fee": expert.consultation_fee,
            "rating": expert.rating,
            "total_consultations": expert.total_consultations,
            "is_available": expert.is_available,
            "location": expert.location,
            "languages": expert.languages,
            "profile_image": expert.profile_image,
        },
    }


@router.post("/consultations", status_code=201)
def book_consultation(
    payload: ConsultationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expert = _lookup_expert(db, payload.expert_id)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")
    if not expert.is_available:
        raise HTTPException(status_code=400, detail="Expert is not currently available")

    topic = (payload.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="A consultation topic is required")
    if len(topic) < 3:
        raise HTTPException(status_code=400, detail="Topic must be at least 3 characters")

    target = _parse_date(payload.scheduled_date)
    if not target:
        raise HTTPException(status_code=400, detail="A valid appointment date is required (YYYY-MM-DD)")
    if target < ddate.today():
        raise HTTPException(status_code=400, detail="Appointment date cannot be in the past")

    slot_label = _format_slot_time(payload.scheduled_time)
    if not slot_label:
        raise HTTPException(status_code=400, detail="A valid appointment time is required")
    if target == ddate.today():
        now_minutes = _now_minutes()
        slot_minutes = _parse_slot_time(slot_label)
        if slot_minutes is not None and slot_minutes <= now_minutes:
            raise HTTPException(status_code=400, detail="Please select a future time slot")

    farm_name = payload.farm_name
    if payload.farm_id:
        farm = db.query(Farm).filter(
            Farm.id == payload.farm_id, Farm.user_id == current_user.id
        ).first()
        if not farm:
            raise HTTPException(status_code=400, detail="Selected farm is not valid")
        farm_name = farm.farm_name or farm_name

    with _booking_lock:
        if _find_slot_conflict(db, expert, target, slot_label):
            raise HTTPException(
                status_code=409,
                detail="This time slot is no longer available. Please choose another time.",
            )

        con_id = generate_id("FA-CNS", db, Consultation)
        consultation = Consultation(
            consultation_id=con_id,
            farmer_id=current_user.id,
            expert_id=expert.id,
            topic=topic,
            description=payload.description,
            consultation_type=payload.consultation_type,
            consultation_method=payload.consultation_method,
            scheduled_date=target.isoformat(),
            scheduled_time=slot_label,
            farm_id=payload.farm_id,
            farm_name=farm_name,
            crop_id=payload.crop_id,
            crop_name=payload.crop_name,
            status="scheduled",
        )
        db.add(consultation)
        expert.total_consultations = (expert.total_consultations or 0) + 1
        db.commit()

    db.refresh(consultation)
    data = _consultation_dict(consultation, expert)
    data["message"] = "Appointment booked successfully"

    try:
        notif_id = generate_id("FA-NOT", db, Notification)
        db.add(Notification(
            notification_id=notif_id,
            user_id=current_user.id,
            title="Appointment Confirmed",
            message=(
                f"Your consultation with {expert.full_name} is booked for "
                f"{consultation.scheduled_date} at {consultation.scheduled_time}. "
                f"Ref: {con_id}"
            ),
            notification_type="consultation",
            reference_id=con_id,
            reference_type="consultation",
            icon="fa-user-doctor",
            action_url=f"expert.html?ref={con_id}",
            is_read=False,
        ))
        db.commit()
    except Exception:
        db.rollback()

    return {"status": "success", "data": data}


@router.get("/consultations")
def list_consultations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Consultation).filter(Consultation.farmer_id == current_user.id)
    if status:
        q = q.filter(Consultation.status == status)
    if search:
        q = q.join(Expert, Consultation.expert_id == Expert.id).filter(
            (Expert.full_name.ilike(f"%{search}%"))
            | (Consultation.topic.ilike(f"%{search}%"))
            | (Consultation.consultation_type.ilike(f"%{search}%"))
        )

    total = q.count()
    items = q.order_by(Consultation.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    result = []
    for c in items:
        expert = db.query(Expert).filter(Expert.id == c.expert_id).first()
        result.append(_consultation_dict(c, expert))

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": result,
        },
    }


@router.get("/consultations/{consultation_id}")
def get_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        consultation = db.query(Consultation).filter(Consultation.consultation_id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    if consultation.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    expert = db.query(Expert).filter(Expert.id == consultation.expert_id).first()

    return {
        "status": "success",
        "data": _consultation_dict(consultation, expert),
    }


@router.patch("/consultations/{consultation_id}")
def update_consultation(
    consultation_id: str,
    payload: ConsultationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        consultation = db.query(Consultation).filter(Consultation.consultation_id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    if consultation.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    now = datetime.utcnow()

    if payload.status is not None:
        valid_transitions = {
            "scheduled": ["cancelled", "confirmed"],
            "requested": ["cancelled", "confirmed"],
            "confirmed": ["cancelled", "in_progress"],
            "in_progress": ["completed"],
        }
        current = consultation.status
        if current in valid_transitions and payload.status not in valid_transitions[current]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change status from '{current}' to '{payload.status}'",
            )
        consultation.status = payload.status
        if payload.status == "cancelled":
            consultation.cancelled_at = now
            if payload.cancel_reason:
                consultation.cancel_reason = payload.cancel_reason
        elif payload.status == "completed":
            consultation.completed_at = now

    if payload.scheduled_date is not None or payload.scheduled_time is not None:
        if consultation.status in ("completed", "cancelled"):
            raise HTTPException(
                status_code=400,
                detail="Cannot reschedule a completed or cancelled appointment",
            )
        new_date = _parse_date(
            payload.scheduled_date if payload.scheduled_date is not None else consultation.scheduled_date
        )
        if not new_date:
            raise HTTPException(status_code=400, detail="A valid appointment date is required (YYYY-MM-DD)")
        if new_date < ddate.today():
            raise HTTPException(status_code=400, detail="Appointment date cannot be in the past")

        new_slot = _format_slot_time(
            payload.scheduled_time if payload.scheduled_time is not None else consultation.scheduled_time
        )
        if not new_slot:
            raise HTTPException(status_code=400, detail="A valid appointment time is required")
        if new_date == ddate.today():
            now_minutes = _now_minutes()
            slot_minutes = _parse_slot_time(new_slot)
            if slot_minutes is not None and slot_minutes <= now_minutes:
                raise HTTPException(status_code=400, detail="Please select a future time slot")

        expert_ref = db.query(Expert).filter(Expert.id == consultation.expert_id).first()
        if not expert_ref:
            raise HTTPException(status_code=404, detail="Expert not found")
        with _booking_lock:
            if _find_slot_conflict(db, expert_ref, new_date, new_slot, exclude_id=consultation.id):
                raise HTTPException(
                    status_code=409,
                    detail="This time slot is no longer available. Please choose another time.",
                )
        consultation.scheduled_date = new_date.isoformat()
        consultation.scheduled_time = new_slot

    if payload.notes is not None:
        consultation.notes = payload.notes

    db.commit()
    db.refresh(consultation)

    expert = db.query(Expert).filter(Expert.id == consultation.expert_id).first()

    return {
        "status": "success",
        "data": _consultation_dict(consultation, expert),
    }


@router.post("/consultations/{consultation_id}/review")
def review_consultation(
    consultation_id: str,
    payload: ConsultationReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        consultation = db.query(Consultation).filter(Consultation.consultation_id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    if consultation.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if consultation.status != "completed":
        raise HTTPException(status_code=400, detail="Can only review completed consultations")
    if consultation.rating is not None:
        raise HTTPException(status_code=400, detail="Already reviewed")

    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    consultation.rating = payload.rating
    consultation.feedback = payload.feedback
    db.commit()

    expert = db.query(Expert).filter(Expert.id == consultation.expert_id).first()
    if expert:
        avg = db.query(func.avg(Consultation.rating)).filter(
            Consultation.expert_id == expert.id,
            Consultation.rating.isnot(None),
        ).scalar()
        if avg is not None:
            expert.rating = round(float(avg), 1)
            db.commit()

    return {
        "status": "success",
        "data": {
            "rating": consultation.rating,
            "feedback": consultation.feedback,
            "message": "Review submitted successfully",
        },
    }
