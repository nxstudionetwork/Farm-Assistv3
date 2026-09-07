"""Instagram/Reels-style recommendation engine for FarmBuzz Shorts.

Personalized + relevant + diverse + fresh. Internal scores are never
exposed to clients; endpoints return only the ranked items.
"""
import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.farmbuzz import (
    FarmBuzzComment,
    FarmBuzzFollow,
    FarmBuzzInteraction,
    FarmBuzzLike,
    FarmBuzzPost,
    FarmBuzzSave,
    FarmBuzzShare,
    FarmBuzzView,
)

ALLOWED_EVENTS = {
    "qualified_view", "watch", "complete", "skip", "replay",
    "like", "unlike", "save", "unsave", "comment", "share",
    "follow_author",
}

# Tunable weights — adjusted after testing, never shown to users.
W = {
    "like": 2.0,
    "save": 5.0,
    "comment": 3.0,
    "share": 3.0,
    "follow_author": 6.0,
    "complete": 4.0,
    "replay": 3.0,
    "qualified_view": 1.0,
    "watch": 0.5,
    "skip": -4.0,
    "unlike": -2.0,
    "unsave": -2.0,
    "category_affinity": 8.0,
    "hashtag_affinity": 4.0,
    "crop_match": 5.0,
    "followed_author": 10.0,
    "freshness": 10.0,
    "diversity_penalty": 3.0,
}


def _user_interest_profile(db: Session, user_id: Optional[str]) -> Dict:
    """Aggregate category/hashtag/author affinity from real interactions."""
    profile = {
        "categories": Counter(),
        "hashtags": Counter(),
        "authors": Counter(),
        "crops": Counter(),
        "total": 0,
    }
    if not user_id:
        return profile

    def bump(post: Optional[FarmBuzzPost], weight: float):
        if not post:
            return
        if post.category:
            profile["categories"][post.category] += weight
        for tag in post.hashtags or []:
            profile["hashtags"][str(tag).lower()] += weight
        if post.user_id:
            profile["authors"][post.user_id] += weight
        if post.crop:
            profile["crops"][str(post.crop).lower()] += weight
        profile["total"] += weight

    post_by_id: Dict[str, FarmBuzzPost] = {}

    def post_of(pid: str) -> Optional[FarmBuzzPost]:
        if pid not in post_by_id:
            post_by_id[pid] = db.query(FarmBuzzPost).filter(FarmBuzzPost.id == pid).first()
        return post_by_id[pid]

    for like in db.query(FarmBuzzLike).filter(FarmBuzzLike.user_id == user_id).all():
        bump(post_of(like.post_id), W["like"])
    for save in db.query(FarmBuzzSave).filter(FarmBuzzSave.user_id == user_id).all():
        bump(post_of(save.post_id), W["save"])
    for comment in db.query(FarmBuzzComment).filter(FarmBuzzComment.user_id == user_id).all():
        bump(post_of(comment.post_id), W["comment"])
    for share in db.query(FarmBuzzShare).filter(FarmBuzzShare.user_id == user_id).all():
        bump(post_of(share.post_id), W["share"])
    for view in db.query(FarmBuzzView).filter(FarmBuzzView.user_id == user_id).all():
        bump(post_of(view.post_id), W["qualified_view"])
    for inter in db.query(FarmBuzzInteraction).filter(FarmBuzzInteraction.user_id == user_id).all():
        bump(post_of(inter.post_id), W.get(inter.event_type, 0.3))
    return profile


def _freshness_score(created_at: Optional[datetime], now: datetime) -> float:
    if not created_at:
        return 0.0
    try:
        age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    except Exception:
        return 0.0
    return (30.0 / (30.0 + age_days)) * W["freshness"]


def _engagement_score(post: FarmBuzzPost) -> float:
    raw = (
        (post.likes_count or 0) * 1.0
        + (post.saves_count or 0) * 3.0
        + (post.comments_count or 0) * 2.0
        + (post.shares_count or 0) * 2.5
        + (post.views_count or 0) * 0.05
    )
    return math.log1p(max(0.0, raw)) * 3.0


def _score_post(
    db: Session,
    post: FarmBuzzPost,
    profile: Dict,
    followed_ids: set,
    user_crops: List[str],
    now: datetime,
) -> float:
    score = 0.0
    score += _engagement_score(post)
    score += _freshness_score(post.created_at, now)

    cat_w = profile["categories"].get(post.category or "", 0.0)
    if profile["total"] > 0:
        score += (cat_w / max(1.0, profile["total"])) * W["category_affinity"] * 10.0
    else:
        # Cold start: small boost to high-quality educational content.
        if (post.category or "") in {"Tip", "Educational", "Quick Knowledge", "Farming", "Crop"}:
            score += 1.0

    tags = {str(t).lower() for t in (post.hashtags or [])}
    if tags and profile["hashtags"]:
        overlap = sum(profile["hashtags"].get(t, 0.0) for t in tags)
        score += (overlap / max(1.0, profile["total"])) * W["hashtag_affinity"] * 10.0

    if post.user_id in followed_ids:
        score += W["followed_author"]

    crop = str(post.crop or "").lower().strip()
    if crop:
        if crop in {c.lower() for c in user_crops if c}:
            score += W["crop_match"]
        if profile["crops"].get(crop):
            score += min(4.0, profile["crops"][crop] * 0.4)

    return score


def _diversify(ranked: List[Tuple[FarmBuzzPost, float]]) -> List[FarmBuzzPost]:
    """Greedy pass: avoid >2 same-category items in a row."""
    out: List[FarmBuzzPost] = []
    remaining = ranked[:]
    last_cats: List[str] = []
    while remaining:
        picked = None
        for i, (post, score) in enumerate(remaining):
            cat = post.category or ""
            streak = sum(1 for c in reversed(last_cats[-2:]) if c == cat)
            if streak >= 2:
                continue
            picked = i
            break
        if picked is None:
            picked = 0
        post, _ = remaining.pop(picked)
        out.append(post)
        last_cats.append(post.category or "")
    return out


def rank_shorts(
    db: Session,
    user,
    candidates: List[FarmBuzzPost],
    user_crops: Optional[List[str]] = None,
) -> List[FarmBuzzPost]:
    now = datetime.utcnow()
    user_id = user.id if user is not None else None
    profile = _user_interest_profile(db, user_id)
    followed_ids: set = set()
    if user_id:
        rows = db.query(FarmBuzzFollow.following_id).filter(
            FarmBuzzFollow.follower_id == user_id
        ).all()
        followed_ids = {r[0] for r in rows}
    crops = user_crops or []
    scored = [
        (p, _score_post(db, p, profile, followed_ids, crops, now))
        for p in candidates
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    return _diversify(scored)
