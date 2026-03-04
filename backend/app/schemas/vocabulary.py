"""单词本相关 Schema"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class VocabularyWordResponse(BaseModel):
    id: int
    word: str
    phonetic_us: Optional[str] = None
    phonetic_uk: Optional[str] = None
    meanings: Optional[str] = None
    example_sentences: Optional[str] = None
    synonyms: Optional[str] = None
    antonyms: Optional[str] = None
    word_roots: Optional[str] = None
    notes: Optional[str] = None
    review_count: int = 0
    correct_count: int = 0
    mastery_level: int = 0
    last_reviewed_at: Optional[datetime] = None
    next_review_date: Optional[date] = None
    is_mastered: bool = False
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VocabularyListResponse(BaseModel):
    total: int
    words: List[VocabularyWordResponse]


class VocabularyReviewRequest(BaseModel):
    word_id: int
    is_correct: bool = Field(..., description="是否回答正确")
