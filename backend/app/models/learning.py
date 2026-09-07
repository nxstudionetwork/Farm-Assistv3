from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, ForeignKey, Text, Integer
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class Course(Base):
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    course_id = Column(String(20), unique=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    level = Column(String(20), default="beginner")
    duration_weeks = Column(Integer, nullable=True)
    language = Column(String(30), default="English")
    instructor = Column(String(200), nullable=True)
    image_url = Column(String(500), nullable=True)
    total_lessons = Column(Integer, default=0)
    is_published = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lessons = relationship("CourseLesson", back_populates="course", order_by="CourseLesson.order_index")
    enrollments = relationship("CourseEnrollment", back_populates="course")


class CourseLesson(Base):
    __tablename__ = "course_lessons"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    lesson_id = Column(String(20), unique=True, index=True)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    content_type = Column(String(20), default="text")
    order_index = Column(Integer, default=0)
    duration_minutes = Column(Integer, nullable=True)
    is_published = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="lessons")
    progress_records = relationship("LessonProgress", back_populates="lesson")
    questions = relationship(
        "LearningQuestion",
        back_populates="tutorial",
        order_by="LearningQuestion.order_index",
        cascade="all, delete-orphan",
    )


class LearningQuestion(Base):
    """A quiz question belonging to a tutorial (course_lesson)."""

    __tablename__ = "learning_questions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    question_id = Column(String(20), unique=True, index=True)
    tutorial_id = Column(String(36), ForeignKey("course_lessons.id"), nullable=False)
    course_id = Column(String(36), nullable=True)
    question = Column(Text, nullable=False)
    option_1 = Column(String(500), nullable=False)
    option_2 = Column(String(500), nullable=False)
    option_3 = Column(String(500), nullable=False)
    option_4 = Column(String(500), nullable=False)
    correct_answer = Column(Integer, nullable=False)
    explanation = Column(Text, nullable=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    tutorial = relationship("CourseLesson", back_populates="questions")


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    enrollment_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False)
    status = Column(String(20), default="enrolled")
    progress_percentage = Column(Float, default=0.0)
    current_lesson_id = Column(String(36), nullable=True)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="course_enrollments")
    course = relationship("Course", back_populates="enrollments")
    lesson_progress = relationship("LessonProgress", back_populates="enrollment")


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    enrollment_id = Column(String(36), ForeignKey("course_enrollments.id"), nullable=False)
    lesson_id = Column(String(36), ForeignKey("course_lessons.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    course_id = Column(String(36), nullable=True)
    is_completed = Column(Boolean, default=False)
    score = Column(Float, default=0.0)
    attempts = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_accessed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    enrollment = relationship("CourseEnrollment", back_populates="lesson_progress")
    lesson = relationship("CourseLesson", back_populates="progress_records")
