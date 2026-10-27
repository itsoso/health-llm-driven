"""Immutable owner-scoped study submissions, independent of workspace replacement."""
from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from app.database import Base

class ExamAttemptRecord(Base):
    __tablename__ = 'life_exam_attempts'
    sequence = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(36), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    request_id = Column(String(36), nullable=False)
    question_id = Column(String(64), nullable=False)
    question_version = Column(Integer, nullable=False)
    choice_index = Column(Integer, nullable=False)
    correct_index = Column(Integer, nullable=False)
    correct = Column(Boolean, nullable=False)
    elapsed_seconds = Column(Integer, nullable=False)
    study_date = Column(Date, nullable=False)
    answered_at = Column(DateTime(timezone=True), nullable=False)
    question_snapshot = Column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint('user_id', 'request_id', name='uq_life_exam_owner_request'),
        CheckConstraint('question_version >= 1', name='ck_life_exam_version'),
        CheckConstraint('choice_index BETWEEN 0 AND 7 AND correct_index BETWEEN 0 AND 7', name='ck_life_exam_choices'),
        CheckConstraint('elapsed_seconds BETWEEN 0 AND 21600', name='ck_life_exam_elapsed'),
        CheckConstraint('correct = (choice_index = correct_index)', name='ck_life_exam_grade'),
        Index('ix_life_exam_owner_question_sequence', 'user_id', 'question_id', 'sequence'),
        Index('ix_life_exam_owner_date_sequence', 'user_id', 'study_date', 'sequence'),
    )
