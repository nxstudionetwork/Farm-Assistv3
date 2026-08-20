from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.community import (
    CommunityPost, CommunityComment, CommunityLike, Expert, Consultation
)

router = APIRouter(prefix="/api/v1", tags=["Community & Experts"])


class PostCreate(BaseModel):
    content: str
    title: Optional[str] = None
    image_url: Optional[str] = None
    post_type: str = "text"


class CommentCreate(BaseModel):
    content: Optional[str] = None
    text: Optional[str] = None


class ConsultationCreate(BaseModel):
    expert_id: str
    topic: str
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None


@router.get("/posts")
def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    post_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CommunityPost).filter(CommunityPost.is_active == True)
    if search:
        q = q.filter(CommunityPost.content.ilike(f"%{search}%"))
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
                    "image_url": p.image_url,
                    "post_type": p.post_type,
                    "likes_count": p.likes_count,
                    "comments_count": p.comments_count,
                    "shares_count": p.shares_count,
                    "created_at": str(p.created_at) if p.created_at else None,
                    "author_name": users[p.user_id].full_name if p.user_id in users else "Farmer",
                    "author_image": users[p.user_id].profile_image if p.user_id in users else None,
                    "image": p.image_url,
                    "title": (p.content or "")[:80],
                }
                for p in items
            ],
        },
    }


@router.post("/posts", status_code=201)
def create_post(
    payload: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post_id = generate_id("FA-PST", db, CommunityPost)
    post = CommunityPost(
        post_id=post_id,
        user_id=current_user.id,
        content=payload.content,
        image_url=payload.image_url,
        post_type=payload.post_type,
        is_active=True,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return {
        "status": "success",
        "data": {
            "id": post.id,
            "post_id": post.post_id,
            "content": post.content,
            "message": "Post created successfully",
        },
    }


@router.get("/posts/{post_id}")
def get_post(post_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        post = db.query(CommunityPost).filter(CommunityPost.post_id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comments = db.query(CommunityComment).filter(CommunityComment.post_id == post.id).order_by(CommunityComment.created_at.desc()).all()
    is_liked = db.query(CommunityLike).filter(
        CommunityLike.post_id == post.id, CommunityLike.user_id == current_user.id
    ).first() is not None

    return {
        "status": "success",
        "data": {
            "id": post.id,
            "post_id": post.post_id,
            "user_id": post.user_id,
            "content": post.content,
            "image_url": post.image_url,
            "post_type": post.post_type,
            "likes_count": post.likes_count,
            "comments_count": post.comments_count,
            "shares_count": post.shares_count,
            "is_liked": is_liked,
            "created_at": str(post.created_at) if post.created_at else None,
            "comments": [
                {
                    "id": c.id,
                    "user_id": c.user_id,
                    "content": c.content,
                    "created_at": str(c.created_at) if c.created_at else None,
                }
                for c in comments
            ],
        },
    }


@router.post("/posts/{post_id}/comments", status_code=201)
def add_comment(
    post_id: str,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = payload.content or payload.text
    if not content:
        raise HTTPException(status_code=400, detail="Comment content is required")
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        post = db.query(CommunityPost).filter(CommunityPost.post_id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = CommunityComment(
        post_id=post.id,
        user_id=current_user.id,
        content=content,
    )
    db.add(comment)
    post.comments_count = (post.comments_count or 0) + 1
    db.commit()
    db.refresh(comment)

    return {
        "status": "success",
        "data": {
            "id": comment.id,
            "post_id": post.post_id,
            "content": comment.content,
            "message": "Comment added successfully",
        },
    }


@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        post = db.query(CommunityPost).filter(CommunityPost.post_id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = db.query(CommunityLike).filter(
        CommunityLike.post_id == post.id, CommunityLike.user_id == current_user.id
    ).first()

    if existing:
        db.delete(existing)
        post.likes_count = max((post.likes_count or 1) - 1, 0)
        liked = False
        message = "Post unliked"
    else:
        like = CommunityLike(post_id=post.id, user_id=current_user.id)
        db.add(like)
        post.likes_count = (post.likes_count or 0) + 1
        liked = True
        message = "Post liked"

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
            "items": [
                {
                    "id": e.id,
                    "expert_id": e.expert_id,
                    "full_name": e.full_name,
                    "speciality": e.speciality,
                    "qualification": e.qualification,
                    "experience_years": e.experience_years,
                    "consultation_fee": e.consultation_fee,
                    "rating": e.rating,
                    "total_consultations": e.total_consultations,
                    "is_available": e.is_available,
                    "location": e.location,
                    "languages": e.languages,
                    "profile_image": e.profile_image,
                }
                for e in items
            ],
        },
    }


@router.get("/experts/{expert_id}")
def get_expert(expert_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    expert = db.query(Expert).filter(Expert.id == expert_id).first()
    if not expert:
        expert = db.query(Expert).filter(Expert.expert_id == expert_id).first()
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
    expert = db.query(Expert).filter(Expert.id == payload.expert_id).first()
    if not expert:
        expert = db.query(Expert).filter(Expert.expert_id == payload.expert_id).first()
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")
    if not expert.is_available:
        raise HTTPException(status_code=400, detail="Expert is not available")

    con_id = generate_id("FA-CNS", db, Consultation)
    consultation = Consultation(
        consultation_id=con_id,
        farmer_id=current_user.id,
        expert_id=expert.id,
        topic=payload.topic,
        description=payload.description,
        scheduled_date=payload.scheduled_date,
        scheduled_time=payload.scheduled_time,
        status="scheduled",
    )
    db.add(consultation)
    expert.total_consultations = (expert.total_consultations or 0) + 1
    db.commit()
    db.refresh(consultation)

    return {
        "status": "success",
        "data": {
            "id": consultation.id,
            "consultation_id": consultation.consultation_id,
            "expert_name": expert.full_name,
            "topic": consultation.topic,
            "scheduled_date": consultation.scheduled_date,
            "scheduled_time": consultation.scheduled_time,
            "status": consultation.status,
            "fee": expert.consultation_fee,
            "message": "Consultation booked successfully",
        },
    }


@router.get("/consultations")
def list_consultations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Consultation).filter(Consultation.farmer_id == current_user.id)
    if status:
        q = q.filter(Consultation.status == status)

    total = q.count()
    items = q.order_by(Consultation.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": c.id,
                    "consultation_id": c.consultation_id,
                    "expert_id": c.expert_id,
                    "topic": c.topic,
                    "description": c.description,
                    "scheduled_date": c.scheduled_date,
                    "scheduled_time": c.scheduled_time,
                    "status": c.status,
                    "rating": c.rating,
                    "created_at": str(c.created_at) if c.created_at else None,
                }
                for c in items
            ],
        },
    }
