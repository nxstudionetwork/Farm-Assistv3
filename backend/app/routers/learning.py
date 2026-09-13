from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User, FarmerProfile
from app.models.learning import (
    Course, CourseLesson, CourseEnrollment, LessonProgress, LearningQuestion,
)
from app.models.notification import Notification

router = APIRouter(prefix="/api/v1", tags=["Learning"])


class EnrollRequest(BaseModel):
    course_id: str


class LessonCompleteRequest(BaseModel):
    pass


class QuizAnswerItem(BaseModel):
    question_id: str
    answer_index: int


class QuizSubmitRequest(BaseModel):
    answers: list[QuizAnswerItem] = Field(default_factory=list)


def serialize_course(c, db=None, user_id=None, lesson_counts=None, enrollment_map=None, brief=False):
    enrolled = False
    enrollment_id = None
    if user_id and db:
        if enrollment_map is not None:
            eid = enrollment_map.get(c.id)
            if eid:
                enrolled = True
                enrollment_id = eid
        else:
            e = db.query(CourseEnrollment).filter(
                CourseEnrollment.user_id == user_id,
                CourseEnrollment.course_id == c.id
            ).first()
            if e:
                enrolled = True
                enrollment_id = e.enrollment_id

    if lesson_counts is not None:
        lessons_count = lesson_counts.get(c.id, c.total_lessons or 0)
    else:
        lessons_count = db.query(CourseLesson).filter(
            CourseLesson.course_id == c.id, CourseLesson.is_published == True
        ).count() if db else c.total_lessons or 0

    result = {
        "id": c.id,
        "course_id": c.course_id,
        "title": c.title,
        "description": c.description,
        "category": c.category,
        "level": c.level,
        "duration_weeks": c.duration_weeks,
        "language": c.language,
        "instructor": c.instructor,
        "image_url": c.image_url,
        "video_available": bool(c.video_url and c.video_url.strip()),
        "total_lessons": lessons_count,
        "is_published": c.is_published,
        "enrolled": enrolled,
        "enrollment_id": enrollment_id,
        "created_at": str(c.created_at) if c.created_at else None,
    }
    if not brief:
        result["video_url"] = c.video_url
        result["core_content"] = c.core_content
        result["tools_materials"] = c.tools_materials
        result["safety_tips"] = c.safety_tips
    return result


def serialize_lesson(l):
    return {
        "id": l.id,
        "lesson_id": l.lesson_id,
        "title": l.title,
        "description": l.description,
        "content": l.content,
        "content_type": l.content_type,
        "order_index": l.order_index,
        "duration_minutes": l.duration_minutes,
    }


def serialize_enrollment(e, db=None):
    course_title = ""
    course_public_id = None
    course_category = None
    course_level = None
    course_image = None
    video_available = False
    total_lessons = 0
    completed_lessons = 0
    current_lesson = None
    current_lesson_title = None

    if e.course:
        course_title = e.course.title
        course_public_id = e.course.course_id
        course_category = e.course.category
        course_level = e.course.level
        course_image = e.course.image_url
        video_available = bool(e.course.video_url and e.course.video_url.strip())
        total_lessons = db.query(CourseLesson).filter(
            CourseLesson.course_id == e.course_id,
            CourseLesson.is_published == True
        ).count() if db else 0

    if db and e.user_id:
        completed_lessons = db.query(LessonProgress).filter(
            LessonProgress.enrollment_id == e.id,
            LessonProgress.is_completed == True
        ).count()

    if e.current_lesson_id and db:
        cl = db.query(CourseLesson).filter(CourseLesson.id == e.current_lesson_id).first()
        if cl:
            current_lesson = cl.id
            current_lesson_title = cl.title

    return {
        "id": e.id,
        "enrollment_id": e.enrollment_id,
        "course_id": e.course_id,
        "course_public_id": course_public_id,
        "course_title": course_title,
        "course_category": course_category,
        "course_level": course_level,
        "course_image": course_image,
        "video_available": video_available,
        "status": e.status,
        "progress_percentage": round(e.progress_percentage or 0, 1),
        "current_lesson_id": current_lesson,
        "current_lesson_title": current_lesson_title,
        "total_lessons": total_lessons,
        "completed_lessons": completed_lessons,
        "enrolled_at": str(e.enrolled_at) if e.enrolled_at else None,
        "completed_at": str(e.completed_at) if e.completed_at else None,
        "last_activity_at": str(e.last_activity_at) if e.last_activity_at else None,
    }


@router.get("/courses")
def list_courses(
    search: Optional[str] = None,
    category: Optional[str] = None,
    level: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Course).filter(Course.is_published == True)
    if search:
        term = f"%{search}%"
        q = q.filter(
            Course.title.ilike(term)
            | Course.description.ilike(term)
            | Course.instructor.ilike(term)
            | Course.category.ilike(term)
        )
    if category:
        q = q.filter(Course.category == category)
    if level:
        q = q.filter(Course.level == level)

    courses = q.order_by(Course.created_at.desc()).all()

    # Batch the per-course lookups so the whole list costs a constant number
    # of queries instead of 2 per course (avoids N+1 lag on ~250 courses).
    lesson_counts = dict(
        db.query(CourseLesson.course_id, func.count())
        .filter(CourseLesson.is_published == True)
        .group_by(CourseLesson.course_id)
        .all()
    )
    course_ids = [c.id for c in courses]
    enrollment_map = {}
    if course_ids:
        enrollment_map = {
            row[0]: row[1]
            for row in db.query(CourseEnrollment.course_id, CourseEnrollment.enrollment_id)
            .filter(
                CourseEnrollment.user_id == current_user.id,
                CourseEnrollment.course_id.in_(course_ids),
            )
            .all()
        }

    return {
        "status": "success",
        "data": [
            serialize_course(c, db, current_user.id, lesson_counts, enrollment_map, brief=True)
            for c in courses
        ],
    }


@router.get("/courses/{course_id}")
def get_course(
    course_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(Course).filter(
        (Course.course_id == course_id) | (Course.id == course_id)
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")

    lessons = db.query(CourseLesson).filter(
        CourseLesson.course_id == c.id,
        CourseLesson.is_published == True
    ).order_by(CourseLesson.order_index).all()

    enrollment = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == current_user.id,
        CourseEnrollment.course_id == c.id
    ).first()

    completed_ids = []
    if enrollment:
        completed_ids = [
            lp.lesson_id for lp in db.query(LessonProgress).filter(
                LessonProgress.enrollment_id == enrollment.id,
                LessonProgress.is_completed == True
            ).all()
        ]

    # Small-test questions for the course (attached to the course's tutorial
    # lessons / core content). Simplifies to a single short test per course.
    questions = db.query(LearningQuestion).filter(
        LearningQuestion.course_id == c.id
    ).order_by(LearningQuestion.order_index).all()
    if not questions:
        # fall back to any questions attached to the course's lessons
        q2 = db.query(LearningQuestion).filter(
            LearningQuestion.tutorial_id.in_([l.id for l in lessons]) if lessons else False
        ).order_by(LearningQuestion.order_index).all()
        if q2:
            questions = q2

    return {
        "status": "success",
        "data": {
            **serialize_course(c, db, current_user.id),
            "lessons": [serialize_lesson(l) for l in lessons],
            "completed_lesson_ids": completed_ids,
            "questions": [
                {
                    "question_id": q.question_id or q.id,
                    "id": q.id,
                    "question": q.question,
                    "options": [q.option_1, q.option_2, q.option_3, q.option_4],
                    "correct_answer": q.correct_answer,
                    "explanation": q.explanation,
                } for q in questions
            ],
            "enrollment": serialize_enrollment(enrollment, db) if enrollment else None,
        },
    }


@router.post("/courses/enroll", status_code=201)
def enroll_course(
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(Course).filter(
        (Course.course_id == payload.course_id) | (Course.id == payload.course_id)
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")

    existing = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == current_user.id,
        CourseEnrollment.course_id == c.id
    ).first()
    if existing:
        return {
            "status": "success",
            "message": "Already enrolled",
            "data": serialize_enrollment(existing, db),
        }

    first_lesson = db.query(CourseLesson).filter(
        CourseLesson.course_id == c.id,
        CourseLesson.is_published == True
    ).order_by(CourseLesson.order_index).first()

    enrollment = CourseEnrollment(
        enrollment_id=generate_id("FA-ENR", db, CourseEnrollment),
        user_id=current_user.id,
        course_id=c.id,
        status="enrolled",
        progress_percentage=0.0,
        current_lesson_id=first_lesson.id if first_lesson else None,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)

    # Event-driven notification when a farmer enrolls in a course.
    try:
        notif_id = generate_id("FA-NOT", db, Notification)
        db.add(Notification(
            notification_id=notif_id,
            user_id=current_user.id,
            title="Course Enrolled",
            message=f"You enrolled in '{c.title}'. Happy learning!",
            notification_type="learning",
            reference_id=c.course_id or c.id,
            reference_type="course",
            icon="fa-graduation-cap",
            action_url="expert.html",
            is_read=False,
        ))
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "success",
        "message": "Enrolled successfully",
        "data": serialize_enrollment(enrollment, db),
    }


@router.get("/my-learning")
def my_learning(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == current_user.id
    )
    if status and status != "all":
        if status == "completed":
            q = q.filter(CourseEnrollment.status == "completed")
        else:
            q = q.filter(CourseEnrollment.status != "completed")

    enrollments = q.order_by(CourseEnrollment.last_activity_at.desc()).all()

    total_enrolled = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == current_user.id
    ).count()
    total_completed = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == current_user.id,
        CourseEnrollment.status == "completed"
    ).count()
    total_lessons_done = db.query(LessonProgress).filter(
        LessonProgress.user_id == current_user.id,
        LessonProgress.is_completed == True
    ).count()

    return {
        "status": "success",
        "data": {
            "enrollments": [serialize_enrollment(e, db) for e in enrollments],
            "stats": {
                "enrolled": total_enrolled,
                "completed": total_completed,
                "in_progress": total_enrolled - total_completed,
                "lessons_completed": total_lessons_done,
            },
        },
    }


@router.post("/enrollments/{enrollment_id}/complete-lesson/{lesson_id}")
def complete_lesson(
    enrollment_id: str,
    lesson_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enrollment = db.query(CourseEnrollment).filter(
        CourseEnrollment.enrollment_id == enrollment_id,
        CourseEnrollment.user_id == current_user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    lesson = db.query(CourseLesson).filter(
        (CourseLesson.lesson_id == lesson_id) | (CourseLesson.id == lesson_id),
        CourseLesson.course_id == enrollment.course_id,
    ).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    existing = db.query(LessonProgress).filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.lesson_id == lesson.id,
        LessonProgress.is_completed == True
    ).first()
    if existing:
        return {"status": "success", "message": "Already completed", "data": serialize_enrollment(enrollment, db)}

    progress = LessonProgress(
        enrollment_id=enrollment.id,
        lesson_id=lesson.id,
        user_id=current_user.id,
        is_completed=True,
        completed_at=datetime.utcnow(),
    )
    db.add(progress)
    db.flush()

    total_lessons = db.query(CourseLesson).filter(
        CourseLesson.course_id == enrollment.course_id,
        CourseLesson.is_published == True
    ).count()
    completed_count = db.query(LessonProgress).filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.is_completed == True
    ).count()

    pct = round((completed_count / total_lessons * 100), 1) if total_lessons > 0 else 0
    enrollment.progress_percentage = pct
    enrollment.last_activity_at = datetime.utcnow()

    all_lessons = db.query(CourseLesson).filter(
        CourseLesson.course_id == enrollment.course_id,
        CourseLesson.is_published == True
    ).order_by(CourseLesson.order_index).all()

    next_lesson = None
    for al in all_lessons:
        done = db.query(LessonProgress).filter(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == al.id,
            LessonProgress.is_completed == True
        ).first()
        if not done:
            next_lesson = al
            break

    if next_lesson:
        enrollment.current_lesson_id = next_lesson.id
    else:
        enrollment.status = "completed"
        enrollment.completed_at = datetime.utcnow()
        enrollment.progress_percentage = 100.0

    db.commit()
    db.refresh(enrollment)
    return {
        "status": "success",
        "message": "Lesson completed",
        "data": serialize_enrollment(enrollment, db),
    }


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cats = db.query(Course.category).filter(
        Course.is_published == True,
        Course.category.isnot(None)
    ).distinct().all()
    return {
        "status": "success",
        "data": [c[0] for c in cats if c[0]],
    }


# ==================== TUTORIALS + QUIZ ====================
# Tutorials reuse the existing course_lesson rows (learning units that live
# directly under a Course). Each tutorial has its own lesson content plus a
# small set of quiz questions. Progress is stored per user in lesson_progress.

def _get_or_create_enrollment(db, user_id, course):
    e = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == user_id,
        CourseEnrollment.course_id == course.id
    ).first()
    if e:
        return e
    first = db.query(CourseLesson).filter(
        CourseLesson.course_id == course.id,
        CourseLesson.is_published == True
    ).order_by(CourseLesson.order_index).first()
    e = CourseEnrollment(
        enrollment_id=generate_id("FA-ENR", db, CourseEnrollment),
        user_id=user_id,
        course_id=course.id,
        status="enrolled",
        progress_percentage=0.0,
        current_lesson_id=first.id if first else None,
    )
    db.add(e)
    db.flush()
    return e


def _find_progress(db, enrollment, lesson):
    return db.query(LessonProgress).filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.lesson_id == lesson.id,
    ).first()


def _serialize_tutorial(lesson, progress=None):
    return {
        "id": lesson.id,
        "tutorial_id": lesson.lesson_id,
        "course_id": lesson.course_id,
        "title": lesson.title,
        "description": lesson.description,
        "content": lesson.content,
        "content_type": lesson.content_type,
        "order_index": lesson.order_index,
        "duration_minutes": lesson.duration_minutes,
        "question_count": len(lesson.questions),
        "completed": bool(progress and progress.is_completed),
        "score": round(progress.score or 0, 1) if progress else 0,
        "attempts": progress.attempts if progress else 0,
        "status": ("completed" if (progress and progress.is_completed)
                   else ("in_progress" if progress else "not_started")),
        "started_at": str(progress.started_at) if progress and progress.started_at else None,
        "completed_at": str(progress.completed_at) if progress and progress.completed_at else None,
        "last_accessed_at": str(progress.last_accessed_at) if progress and progress.last_accessed_at else None,
    }


def _recompute_enrollment_progress(db, enrollment):
    published = db.query(CourseLesson).filter(
        CourseLesson.course_id == enrollment.course_id,
        CourseLesson.is_published == True
    ).order_by(CourseLesson.order_index).all()
    total = len(published)
    done_ids = {
        lp.lesson_id for lp in db.query(LessonProgress).filter(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.is_completed == True
        ).all()
    }
    done = sum(1 for l in published if l.id in done_ids)
    enrollment.progress_percentage = round((done / total) * 100, 1) if total else 0
    enrollment.last_activity_at = datetime.utcnow()

    next_lesson = next((l for l in published if l.id not in done_ids), None)
    if next_lesson:
        enrollment.current_lesson_id = next_lesson.id
        if enrollment.status != "enrolled":
            enrollment.status = "enrolled"
    else:
        enrollment.current_lesson_id = published[-1].id if published else None
        enrollment.status = "completed"
        enrollment.completed_at = enrollment.completed_at or datetime.utcnow()
    db.flush()
    return done, total


@router.get("/courses/{course_id}/tutorials")
def course_tutorials(
    course_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import math
    c = db.query(Course).filter(
        (Course.course_id == course_id) | (Course.id == course_id)
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")

    lessons = db.query(CourseLesson).filter(
        CourseLesson.course_id == c.id,
        CourseLesson.is_published == True
    ).order_by(CourseLesson.order_index).all()

    enrollment = _get_or_create_enrollment(db, current_user.id, c)
    progress_map = {
        lp.lesson_id: lp for lp in db.query(LessonProgress).filter(
            LessonProgress.enrollment_id == enrollment.id
        ).all()
    }

    tutorials = [
        _serialize_tutorial(l, progress_map.get(l.id)) for l in lessons
    ]
    completed = sum(1 for t in tutorials if t["completed"])
    total = len(tutorials)
    progress_pct = round((completed / total) * 100, 1) if total else 0
    remaining = max(total - completed, 0)

    return {
        "status": "success",
        "data": {
            "course": serialize_course(c, db, current_user.id),
            "tutorials": tutorials,
            "enrollment": serialize_enrollment(enrollment, db),
            "total_tutorials": total,
            "completed_tutorials": completed,
            "remaining_tutorials": remaining,
            "progress_percentage": progress_pct,
        },
    }


@router.get("/tutorials/{tutorial_id}")
def get_tutorial(
    tutorial_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lesson = db.query(CourseLesson).filter(
        (CourseLesson.lesson_id == tutorial_id) | (CourseLesson.id == tutorial_id)
    ).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Tutorial not found")

    course = db.query(Course).filter(Course.id == lesson.course_id).first()
    enrollment = _get_or_create_enrollment(db, current_user.id, course) if course else None

    progress = _find_progress(db, enrollment, lesson) if enrollment else None

    questions = db.query(LearningQuestion).filter(
        LearningQuestion.tutorial_id == lesson.id
    ).order_by(LearningQuestion.order_index).all()

    return {
        "status": "success",
        "data": {
            **_serialize_tutorial(lesson, progress),
            "course_title": course.title if course else "",
            "course_id": course.course_id if course else None,
            "total_tutorials": db.query(CourseLesson).filter(
                CourseLesson.course_id == lesson.course_id,
                CourseLesson.is_published == True
            ).count() if course else 0,
            "tutorial_index": lesson.order_index + 1,
            "questions": [
                {
                    "question_id": q.question_id,
                    "id": q.id,
                    "question": q.question,
                    "options": [q.option_1, q.option_2, q.option_3, q.option_4],
                    "explanation": q.explanation,
                } for q in questions
            ],
        },
    }


@router.post("/tutorials/{tutorial_id}/start")
def start_tutorial(
    tutorial_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lesson = db.query(CourseLesson).filter(
        (CourseLesson.lesson_id == tutorial_id) | (CourseLesson.id == tutorial_id)
    ).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Tutorial not found")
    course = db.query(Course).filter(Course.id == lesson.course_id).first()
    enrollment = _get_or_create_enrollment(db, current_user.id, course)

    progress = _find_progress(db, enrollment, lesson)
    if not progress:
        progress = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            user_id=current_user.id,
            course_id=course.id if course else None,
            is_completed=False,
            score=0.0,
            attempts=0,
            started_at=datetime.utcnow(),
            last_accessed_at=datetime.utcnow(),
        )
        db.add(progress)
    else:
        progress.last_accessed_at = datetime.utcnow()
        if not progress.started_at:
            progress.started_at = datetime.utcnow()
    db.commit()
    db.refresh(progress)
    return {
        "status": "success",
        "message": "Tutorial started",
        "data": _serialize_tutorial(lesson, progress),
    }


@router.post("/tutorials/{tutorial_id}/quiz/submit")
def submit_quiz(
    tutorial_id: str,
    payload: QuizSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lesson = db.query(CourseLesson).filter(
        (CourseLesson.lesson_id == tutorial_id) | (CourseLesson.id == tutorial_id)
    ).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Tutorial not found")
    course = db.query(Course).filter(Course.id == lesson.course_id).first()
    enrollment = _get_or_create_enrollment(db, current_user.id, course)

    questions = db.query(LearningQuestion).filter(
        LearningQuestion.tutorial_id == lesson.id
    ).order_by(LearningQuestion.order_index).all()
    if not questions:
        raise HTTPException(status_code=400, detail="No questions available for this tutorial")

    q_by_id = {
        (q.question_id or q.id): q for q in questions
    }
    answer_map = {}
    for item in payload.answers:
        q = q_by_id.get(item.question_id)
        if q is None:
            continue
        answer_map[q.id] = item.answer_index

    detail = []
    correct = 0
    for q in questions:
        chosen = answer_map.get(q.id)
        is_correct = chosen == q.correct_answer
        if is_correct:
            correct += 1
        detail.append({
            "question_id": q.question_id or q.id,
            "question": q.question,
            "user_answer": chosen,
            "correct_answer": q.correct_answer,
            "options": [q.option_1, q.option_2, q.option_3, q.option_4],
            "is_correct": is_correct,
            "explanation": q.explanation,
        })

    total = len(questions)
    score = round((correct / total) * 100, 1) if total else 0

    progress = _find_progress(db, enrollment, lesson)
    if not progress:
        progress = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            user_id=current_user.id,
            course_id=course.id if course else None,
            started_at=datetime.utcnow(),
            last_accessed_at=datetime.utcnow(),
        )
        db.add(progress)
    progress.attempts = (progress.attempts or 0) + 1
    progress.score = max(progress.score or 0, score)
    progress.is_completed = True
    progress.completed_at = progress.completed_at or datetime.utcnow()
    progress.last_accessed_at = datetime.utcnow()
    db.flush()

    _recompute_enrollment_progress(db, enrollment)
    db.commit()
    db.refresh(progress)

    return {
        "status": "success",
        "data": {
            "score": score,
            "correct": correct,
            "total": total,
            "passed": score >= 60.0,
            "better_than_before": score >= (progress.score or 0),
            "detail": detail,
            "tutorial": _serialize_tutorial(lesson, progress),
            "course_progress_percentage": enrollment.progress_percentage,
        },
    }


@router.post("/tutorials/{tutorial_id}/complete")
def complete_tutorial(
    tutorial_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lesson = db.query(CourseLesson).filter(
        (CourseLesson.lesson_id == tutorial_id) | (CourseLesson.id == tutorial_id)
    ).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Tutorial not found")
    course = db.query(Course).filter(Course.id == lesson.course_id).first()
    enrollment = _get_or_create_enrollment(db, current_user.id, course)

    progress = _find_progress(db, enrollment, lesson)
    if not progress:
        progress = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            user_id=current_user.id,
            course_id=course.id if course else None,
            started_at=datetime.utcnow(),
            last_accessed_at=datetime.utcnow(),
        )
        db.add(progress)
    progress.is_completed = True
    progress.completed_at = progress.completed_at or datetime.utcnow()
    progress.last_accessed_at = datetime.utcnow()
    db.flush()

    _recompute_enrollment_progress(db, enrollment)
    db.commit()
    db.refresh(progress)
    return {
        "status": "success",
        "message": "Tutorial completed",
        "data": _serialize_tutorial(lesson, progress),
    }


@router.get("/learning/progress")
def learning_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enrollments = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == current_user.id
    ).all()

    continue_learning = []
    recently_learned = []
    completed_course_ids = set()

    for e in enrollments:
        course = db.query(Course).filter(Course.id == e.course_id).first()
        if not course:
            continue
        pub = db.query(CourseLesson).filter(
            CourseLesson.course_id == e.course_id,
            CourseLesson.is_published == True
        ).order_by(CourseLesson.order_index).all()
        progress_map = {
            lp.lesson_id: lp for lp in db.query(LessonProgress).filter(
                LessonProgress.enrollment_id == e.id
            ).all()
        }
        tuts = [_serialize_tutorial(l, progress_map.get(l.id)) for l in pub]
        completed = sum(1 for t in tuts if t["completed"])
        total = len(tuts) or 1
        pct = round((completed / total) * 100, 1)
        if e.status == "completed":
            completed_course_ids.add(course.id)

        next_tutorial = next((t for t in tuts if not t["completed"]), None)
        if next_tutorial and e.status != "completed":
            continue_learning.append({
                "course_id": course.course_id,
                "course_title": course.title,
                "course_level": course.level,
                "progress_percentage": pct,
                "completed_tutorials": completed,
                "total_tutorials": len(tuts),
                "next_tutorial_id": next_tutorial["tutorial_id"],
                "next_tutorial_title": next_tutorial["title"],
                "next_order_index": next_tutorial["order_index"] + 1,
            })

        # recently completed tutorials for this course
        for t in tuts:
            if t["completed"] and t["completed_at"]:
                recently_learned.append({
                    "course_id": course.course_id,
                    "course_title": course.title,
                    "tutorial_id": t["tutorial_id"],
                    "tutorial_title": t["title"],
                    "score": t["score"],
                    "completed_at": t["completed_at"],
                })

    recently_learned.sort(key=lambda x: x["completed_at"] or "", reverse=True)
    continue_learning.sort(key=lambda x: x["progress_percentage"], reverse=True)

    enrolled_ids = {e.course_id for e in enrollments}

    # --- Preference-based recommendations ---
    # Score unpublished courses by how well they match the farmer's declared
    # crops and the categories they already engage with. Everything is driven
    # by real farmer profile data (no fake/arbitrary signals).
    preferred_crops = []
    profile = db.query(FarmerProfile).filter(
        FarmerProfile.user_id == current_user.id
    ).first()
    if profile and profile.preferred_crops:
        preferred_crops = [
            c.strip().lower() for c in profile.preferred_crops.split(",") if c.strip()
        ]

    category_weights = {}
    for e in enrollments:
        cat_course = db.query(Course).filter(Course.id == e.course_id).first()
        if cat_course and cat_course.category:
            category_weights[cat_course.category] = (
                category_weights.get(cat_course.category, 0) + 1
            )

    def _rec_score(course):
        score = 0
        if preferred_crops:
            hay = ((course.title or "") + " " + (course.description or "")).lower()
            for crop in preferred_crops:
                if crop and crop in hay:
                    score += 2
                    break
        if course.category in category_weights:
            score += category_weights[course.category]
        return score

    # Fetch in random order first, then stable-sort by score so equally-scored
    # candidates still vary between calls.
    candidates = [
        c for c in db.query(Course).filter(Course.is_published == True).order_by(
            func.random()
        ).limit(60).all()
        if c.id not in enrolled_ids
    ]
    candidates.sort(key=_rec_score, reverse=True)

    # Single batched count for every published lesson (avoids N+1 in the loop).
    lesson_counts = dict(
        db.query(CourseLesson.course_id, func.count())
        .filter(CourseLesson.is_published == True)
        .group_by(CourseLesson.course_id)
        .all()
    )

    recommended = []
    for c in candidates[:4]:
        recommended.append({
            "course_id": c.course_id,
            "title": c.title,
            "category": c.category,
            "level": c.level,
            "instructor": c.instructor,
            "image_url": c.image_url,
            "video_available": bool(c.video_url and c.video_url.strip()),
            "duration_weeks": c.duration_weeks,
            "total_tutorials": lesson_counts.get(c.id, 0),
        })

    completed_courses = db.query(CourseEnrollment).filter(
        CourseEnrollment.user_id == current_user.id,
        CourseEnrollment.status == "completed"
    ).count()
    total_enrolled = len(enrollments)

    return {
        "status": "success",
        "data": {
            "continue_learning": continue_learning,
            "recently_learned": recently_learned,
            "recommended": recommended,
            "stats": {
                "enrolled": total_enrolled,
                "completed_courses": completed_courses,
                "in_progress": total_enrolled - completed_courses,
            },
        },
    }
