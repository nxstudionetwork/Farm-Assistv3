"""
Patch script: populate every community group that has zero posts with
realistic demo content so the communities subform never looks empty.

Reuses the same CONTENT_KIT, DEMO_FARMERS, and sentence pools from
seed_community_demo so the style is indistinguishable.

Run:  python -m app.database.seed_empty_groups
"""

import random
import sys
from datetime import datetime, timedelta

from app.database.connection import SessionLocal
from app.models.community import (
    CommunityAnswer, CommunityComment, CommunityGroup, CommunityGroupMember,
    CommunityLike, CommunityPost, CommunitySave,
)
from app.models.user import User
from sqlalchemy import func

# ── content pools (identical to seed_community_demo) ─────────────────────

GENERIC_SENTENCES = [
    "Anyone else facing the same issue this season?",
    "What has worked for you on your farm?",
    "Sharing this so nobody makes the mistake I did.",
    "Local agriculture officers suggested this last week.",
    "I learnt this in the KVK training session.",
    "The fertilizer shop owner recommended this, but I want real farmer feedback.",
    "Has anyone tried this with good results?",
    "Cost per acre came down noticeably after this.",
    "Looking for experiences from farmers in a similar climate.",
    "Happy to share details if anyone needs them.",
    "This is my second year trying this approach.",
    "The mandi price this week made it worth it.",
    "My father taught me this method, and it still works.",
    "Open to suggestions before I commit to it fully.",
    "Also tried a small demo on one acre before scaling up.",
    "Please share your observations if you have tried this.",
    "Wrote this after a field day in our block.",
    "Consultants advised keeping close records, and it helps.",
    "Started with neighbours who saw good results last year.",
    "Will update with progress photos later this month.",
]

GENERIC_OPENERS = [
    "Here is what I observed on my farm:",
    "Just sharing a small experience:",
    "A quick question from the field:",
    "Thought this might help fellow farmers:",
    "My experience so far:",
    "Practical tip from the ground:",
    "Learnt something new yesterday:",
    "Want to compare notes on this:",
    "From my last season's record:",
]

GENERIC_CLOSERS = [
    "Looking forward to your views.",
    "Suggestions are most welcome.",
    "Hope this helps someone.",
    "Your feedback would mean a lot.",
    "Would love to hear local experiences.",
    "Happy farming everyone.",
]

COMMENT_POOL = [
    "Good to know, thank you!",
    "Tried this and it works.",
    "Can you share the source?",
    "This is a common issue here too.",
    "Thanks for the detailed share.",
    "We used a slightly different method.",
    "Any risk of overdoing it?",
    "Noted for this season.",
    "We faced the same last year, compost helped.",
    "Our block officer recommends exactly this.",
    "Great point, sharing with our group.",
    "Will try on a small plot first.",
]

ANSWER_POOL = [
    "We follow the same practice and it helps.",
    "Try reducing the dose by half first.",
    "Consult the local extension officer for this.",
    "This worked well in our sandy loam soil.",
    "Combine it with proper drainage.",
    "Many farmers in our cluster got good results.",
    "Monitor for a week after applying.",
    "Timing it with the rainfall forecast worked for us.",
]

LOCATIONS = [
    "Krishna District, AP", "Guntur District, AP", "Thanjavur, TN",
    "Karnal, Haryana", "Ludhiana, Punjab", "Amritsar, Punjab",
    "Nagpur, Maharashtra", "Anand, Gujarat", "Rajkot, Gujarat",
    "Indore, MP", "Warangal, Telangana", "Mysuru, Karnataka",
    "Patna, Bihar", "Jaipur, Rajasthan", "Coimbatore, TN",
    "Kottayam, Kerala", "Kurnool, AP", "Sangli, Maharashtra",
]

# ── per-category content kits (subset we need for the legacy groups) ─────

CONTENT_KIT = {
    "Horticulture": {
        "titles": [
            "Mango flowering management - tips needed", "Banana bunch weight improvement ideas",
            "Pomegranate cracking - causes and control?", "Guava propagation by grafting questions",
            "Fruit drop problem in litchi, please help", "Coconut nutrition and fertilizer schedule",
            "Dragon fruit support system that works", "Marigold as intercrop with vegetables",
            "Orchard pruning cycle advice", "Flower picking time for better vase life",
            "Kiwi farming feasibility in our climate", "Papaya varieties for tropical regions",
        ],
        "crops": ["mango", "banana", "pomegranate", "guava", "litchi", "papaya", "coconut", "dragon fruit"],
        "tags": ["horticulture", "orchard", "fruits", "flower"],
        "sentences": [
            "We used potassium sprays at flowering for mango fruit setting.",
            "Fruit thinning in pomegranate improved average fruit size.",
            "Banana bunch cover with non-woven bags protected the fingers.",
            "Regular basin mulching conserved moisture around guava trees.",
            "Litchi fruit drop reduced when we controlled leaf miner early.",
            "Coconut needs one round of organic manure and two of chemical.",
            "Dragon fruit poles spaced well apart with drip works nicely.",
            "Marigold rows between vegetables attracted pollinators.",
            "Pruning after harvest encouraged new flowering wood.",
            "Flowers cut in the early morning lasted two days longer.",
            "A foliar spray of urea at fruit set gave bigger mangoes.",
            "We raised the papaya bed to prevent waterlogging damage.",
        ],
    },
    "Livestock": {
        "titles": [
            "Milk yield improvement through feeding", "Best fodder crops for year-round green feed",
            "Calf care tips after birth", "Poultry vaccination schedule questions",
            "Goat rearing income and care", "Buffalo breeding: AI vs natural?",
            "Managing mastitis in dairy animals", "Silage making from maize fodder",
            "Desi vs crossbred cow for small farm", "Clean milk production practices",
            "Feed cost reduction for 10-cow dairy", "Vaccination calendar for sheep flocks",
        ],
        "crops": ["cattle", "buffalo", "goat", "poultry", "fodder"],
        "tags": ["livestock", "dairy", "poultry", "fodder", "goat"],
        "sentences": [
            "Balanced feed with mineral mixture improved milk fat.",
            "Napier grass cut every 45 days feeds the stock well.",
            "Colostrum fed in the first hour built calf immunity.",
            "We follow the vaccination calendar without missing a dose.",
            "Kid care in the first week decided the goat project's success.",
            "AI records helped us plan calving dates better.",
            "Clean udder hygiene reduced mastitis cases sharply.",
            "Maize silage stored well lasted the dry season.",
            "Desi cows are easier to manage on limited feed.",
            "Free-range poultry supplements the kitchen income nicely.",
            "Urea-molasses blocks kept cattle healthy through summer.",
            "Shed ventilation reduced pneumonia in our poultry batch.",
        ],
    },
    "Technology": {
        "titles": [
            "Drone spraying experience and cost", "Soil moisture sensors - do they pay off?",
            "Best apps for farm record keeping", "Precision agriculture on a small farm",
            "Solar fencing for field protection", "AI disease detection photos - reliability?",
            "Digital mandi platforms comparison", "Automated irrigation controller setup",
            "Using spreadsheets for crop budget", "Smart spray schedule apps",
            "Weather station on the farm setup", "GPS for tractor guidance on slopes",
        ],
        "crops": ["drones", "sensor", "app", "fencing"],
        "tags": ["technology", "agritech", "drone", "sensors"],
        "sentences": [
            "Drone spraying in cotton saved time and chemical evenly.",
            "Two soil sensors guide our irrigation decisions now.",
            "The farm record app warns when expenses cross budget.",
            "Precision seeding with variable rate saved seed.",
            "Solar fencing protected the fields from stray cattle.",
            "We use photo-based disease detection as a second opinion.",
            "Digital mandi bids opened better markets for our produce.",
            "An automated timer runs drip cycles when we are away.",
            "A simple budget sheet made each crop profitable to track.",
            "GPS mapping of plots helps with planning and insurance.",
            "The weather station on our farm sent a frost alert last week.",
            "We connected the motor starter to a timer and saved daily visits.",
        ],
    },
    "Markets": {
        "titles": [
            "Best time to sell paddy in the season?", "e-NAM experience - higher price or not?",
            "Direct selling to buyers vs mandi", "How to check daily mandi rates quickly?",
            "Grading and cleaning for premium price", "Export rules for chilli and spices",
            "Contract farming pitfalls to avoid", "Cold storage and selling later - worth it?",
            "FPO collective selling benefits", "Price forecasts for next season crops",
            "Local market vs long-distance buyer trade-offs", "Transport cost for bulk produce",
        ],
        "crops": ["mandi", "e-NAM", "onion", "chilli"],
        "tags": ["markets", "mandi", "prices", "enam", "selling"],
        "sentences": [
            "Selling through the FPO gave us a better pooled price.",
            "e-NAM bidding pushed the price above the local mandi.",
            "Grading before auction improved our realisation.",
            "Small market arrivals usually mean firm prices.",
            "We check the official mandi app every morning.",
            "Storing in the cooperative cold store paid off after two weeks.",
            "Quality certificate helped us tap the export buyer.",
            "Long-distance buyers pay for proper packing.",
            "Contract farming needs a clear, written weight and price basis.",
            "Watching arrivals across three mandis informs our selling day.",
            "Transport cost eats 8% of the onion sale in our block.",
            "After grading, our chilli fetched 400 more per quintal.",
        ],
    },
}

# Map each legacy group name to a kit
GROUP_KIT_MAP = {
    "Horticulture": "Horticulture",
    "Livestock & Dairy": "Livestock",
    "Farm Technology": "Technology",
    "Market & Prices": "Markets",
}

POSTS_PER_EMPTY_GROUP = 12
POSTS_PER_CATEGORY = POSTS_PER_EMPTY_GROUP


def _pick(pool, rnd):
    return rnd.choice(pool)


def _sample(pool, k, rnd):
    if k >= len(pool):
        return list(pool)
    return rnd.sample(pool, k)


def _content_sentences(category, rnd):
    kit = CONTENT_KIT[category]
    parts = []
    if rnd.random() < 0.4:
        parts.append(_pick(GENERIC_OPENERS, rnd))
    parts.extend(_sample(kit["sentences"], rnd.randint(3, 4), rnd))
    parts.extend(_sample(GENERIC_SENTENCES, rnd.randint(1, 2), rnd))
    if rnd.random() < 0.5:
        parts.append(_pick(GENERIC_CLOSERS, rnd))
    rnd.shuffle(parts)
    return parts[:7]


def _make_title(kit, rnd):
    t = _pick(kit["titles"], rnd)
    return t.replace("{crop}", _pick(kit["crops"], rnd))


def _timestamp(rnd):
    days = int(rnd.expovariate(1.0 / 45.0))
    days = min(days, 180)
    hours = rnd.randint(5, 20)
    minutes = rnd.randint(0, 59)
    ago = timedelta(days=days, hours=24 - (hours % 24), minutes=minutes)
    return datetime.utcnow() - ago


def _next_seq(db, model, column_name, prefix):
    highest = 0
    for (val,) in db.query(getattr(model, column_name)).filter(
        getattr(model, column_name).like(f"{prefix}-%")
    ).all():
        try:
            digit = str(val).split("-")[-1]
            highest = max(highest, int(digit))
        except (TypeError, ValueError):
            continue
    return highest + 1


def seed_empty_groups(session):
    """Find every group with zero posts and populate with realistic demo content."""
    rnd = random.Random(42)

    # demo farmers to author posts
    demo_users = session.query(User).filter(User.is_demo == True).all()
    if not demo_users:
        print("No demo farmers found — run seed_community_demo first.")
        return

    # groups with zero active posts
    group_ids_with_posts = {
        row[0] for row in
        session.query(CommunityPost.community_id)
        .filter(CommunityPost.is_active == True, CommunityPost.community_id.isnot(None))
        .distinct().all()
    }
    empty_groups = session.query(CommunityGroup).filter(
        ~CommunityGroup.id.in_(group_ids_with_posts)
    ).all()

    if not empty_groups:
        print("All groups already have posts.")
        return

    post_seq = _next_seq(session, CommunityPost, "post_id", "FA-PST")
    answer_seq = _next_seq(session, CommunityAnswer, "answer_id", "FA-ANS")
    total_posts = 0
    total_comments = 0
    total_answers = 0
    total_likes = 0
    total_saves = 0

    for g in empty_groups:
        kit_key = GROUP_KIT_MAP.get(g.name)
        if not kit_key:
            # Fallback: try matching by category
            kit_key = g.category if g.category in CONTENT_KIT else None
        if not kit_key:
            print(f"  Skip {g.name} (no content kit)")
            continue

        kit = CONTENT_KIT[kit_key]
        group_comments = 0
        group_answers = 0
        group_likes = 0
        group_saves = 0

        for _ in range(POSTS_PER_EMPTY_GROUP):
            rtype = rnd.random()
            if rtype < 0.36:
                post_type = "question"
                has_title = True
            elif rtype < 0.62:
                post_type = "discussion"
                has_title = False
            elif rtype < 0.82:
                post_type = "experience"
                has_title = rnd.random() < 0.4
            else:
                post_type = "advice"
                has_title = False

            author = _pick(demo_users, rnd)
            created = _timestamp(rnd)
            sentences = _content_sentences(kit_key, rnd)
            content = " ".join(sentences)
            tags = _sample(kit["tags"], rnd.randint(0, 2), rnd)
            if tags:
                content += " " + " ".join("#" + t for t in tags)
            crop = _pick(kit["crops"], rnd) if rnd.random() < 0.55 else None
            location = _pick(LOCATIONS, rnd) if rnd.random() < 0.6 else None

            image_url = None
            if rnd.random() < 0.16:
                seed = f"fa{str(crop or 'farm').replace(' ', '')[:6]}{total_posts}"
                image_url = f"https://picsum.photos/seed/{seed}/720/460"

            title = _make_title(kit, rnd) if has_title else None
            if post_type == "question" and title and title[-1] != "?":
                title = title.rstrip(".") + "?"

            post = CommunityPost(
                post_id=f"FA-PST-{post_seq:08d}",
                user_id=author.id,
                community_id=g.id,
                title=title,
                content=content,
                category=g.category or "General",
                crop=crop,
                location=location,
                image_url=image_url,
                media_type="image" if image_url else "text",
                post_type=post_type,
                is_active=True,
                is_demo=True,
                created_at=created,
                updated_at=created,
            )
            session.add(post)
            session.flush()
            post_seq += 1
            total_posts += 1

            # likes
            n_likes = rnd.randint(1, 5)
            likers = _sample(demo_users, n_likes, rnd)
            for liker in likers:
                session.add(CommunityLike(
                    post_id=post.id, user_id=liker.id,
                    is_demo=True, created_at=created,
                ))
            post.likes_count = n_likes + rnd.randint(0, 24)
            group_likes += post.likes_count
            total_likes += post.likes_count

            # comments
            if rnd.random() < 0.6:
                n_comments = rnd.randint(1, 5)
                commenters = _sample(demo_users, n_comments, rnd)
                for cus in commenters:
                    session.add(CommunityComment(
                        post_id=post.id, user_id=cus.id,
                        content=_pick(COMMENT_POOL, rnd),
                        is_demo=True,
                        created_at=created + timedelta(minutes=rnd.randint(2, 300)),
                    ))
                post.comments_count = n_comments
                group_comments += n_comments
                total_comments += n_comments

            # answers for questions
            if post_type == "question" and rnd.random() < 0.8:
                n_answers = rnd.randint(1, 3)
                for au in _sample(demo_users, n_answers, rnd):
                    session.add(CommunityAnswer(
                        answer_id=f"FA-ANS-{answer_seq:08d}",
                        post_id=post.id,
                        user_id=au.id,
                        content=_pick(ANSWER_POOL, rnd),
                        is_best_answer=rnd.random() < 0.25,
                        is_demo=True,
                        created_at=created + timedelta(hours=rnd.randint(1, 72)),
                    ))
                    answer_seq += 1
                    group_answers += 1
                    total_answers += 1

            # saves
            if rnd.random() < 0.18:
                session.add(CommunitySave(
                    post_id=post.id, user_id=_pick(demo_users, rnd).id,
                    is_demo=True, created_at=created,
                ))
                post.saves_count = 1
                group_saves += 1
                total_saves += 1
            else:
                post.saves_count = 0

            post.shares_count = rnd.randint(0, 18)

        # memberships (same pattern as main seeder)
        existing_member_ids = {
            uid for (uid,) in session.query(CommunityGroupMember.user_id)
            .filter(CommunityGroupMember.community_id == g.id).all()
        }
        new_members = 0
        for u in _sample(demo_users, rnd.randint(12, 30), rnd):
            if u.id not in existing_member_ids:
                session.add(CommunityGroupMember(
                    community_id=g.id, user_id=u.id,
                    joined_at=_timestamp(rnd),
                ))
                new_members += 1

        print(
            f"  {g.name}: +{POSTS_PER_EMPTY_GROUP} posts, "
            f"{group_comments} comments, {group_answers} answers, "
            f"{group_likes} likes, +{new_members} members"
        )

    session.commit()
    print(
        f"\nTotal: {total_posts} posts, {total_comments} comments, "
        f"{total_answers} answers, {total_likes} likes, "
        f"{total_saves} saves"
    )


if __name__ == "__main__":
    session = SessionLocal()
    try:
        seed_empty_groups(session)
    finally:
        session.close()
