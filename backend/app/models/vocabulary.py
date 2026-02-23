"""英语单词学习模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base


class VocabularyWord(Base):
    """用户的单词本"""
    __tablename__ = "vocabulary_words"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    word = Column(String(100), nullable=False)
    phonetic_us = Column(String(200), nullable=True)
    phonetic_uk = Column(String(200), nullable=True)
    meanings = Column(Text, nullable=True)           # JSON: [{"pos":"v.","def":"放弃"}]
    example_sentences = Column(Text, nullable=True)  # JSON: [{"en":"...","zh":"..."}]
    synonyms = Column(Text, nullable=True)
    antonyms = Column(Text, nullable=True)
    word_roots = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    review_count = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    mastery_level = Column(Integer, default=0)       # 0-5
    last_reviewed_at = Column(DateTime, nullable=True)
    next_review_date = Column(Date, nullable=True)
    is_mastered = Column(Boolean, default=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    __table_args__ = (
        Index('idx_vocab_user_word', 'user_id', 'word', unique=True),
        Index('idx_vocab_user_review', 'user_id', 'is_mastered', 'next_review_date'),
    )
