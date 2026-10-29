"""Versioned public questions and owner-only graded attempt DTOs."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

QuestionId = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')]
Subject = Literal['英语', '数学', '逻辑']
PaperSubject = Literal['199', '204']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ExamQuestion(Strict):
    id: QuestionId
    version: Annotated[int, Field(strict=True, ge=1)]
    subject: Subject
    topic: Annotated[str, Field(min_length=1, max_length=200)]
    prompt: Annotated[str, Field(min_length=1, max_length=20000)]
    options: Annotated[list[Annotated[str, Field(min_length=1, max_length=4000)]], Field(min_length=2, max_length=8)]
    source: Annotated[str, Field(min_length=1, max_length=500)]
    difficulty: Annotated[str, Field(min_length=1, max_length=100)]
    paper_year: Annotated[int, Field(strict=True, ge=2000, le=2100)] | None = None
    paper_subject: PaperSubject | None = None
    question_number: Annotated[int, Field(strict=True, ge=1, le=100)] | None = None
    image_path: Annotated[str, Field(pattern=r'^/exam-papers/20\d{2}/199/q\d{2}\.webp$')] | None = None

    @model_validator(mode='after')
    def valid_paper_identity(self):
        identity = (self.paper_year, self.paper_subject, self.question_number)
        if any(value is not None for value in identity) and any(value is None for value in identity):
            raise ValueError('Incomplete real-paper identity')
        if self.image_path is not None and self.paper_subject != '199':
            raise ValueError('Only management questions use an original-paper image')
        return self

class CatalogQuestion(ExamQuestion):
    answer: Annotated[int, Field(strict=True, ge=0, le=7)]
    explanation: Annotated[str, Field(min_length=1, max_length=20000)]

    @model_validator(mode='after')
    def valid_answer(self):
        if self.answer >= len(self.options) or len(set(self.options)) != len(self.options):
            raise ValueError('Invalid reviewed question')
        return self

class Catalog(Strict):
    catalog_version: Annotated[str, Field(min_length=1, max_length=100)]
    questions: Annotated[list[CatalogQuestion], Field(min_length=1, max_length=10000)]

    @model_validator(mode='after')
    def unique_ids(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError('Duplicate question identity')
        return self

class ExamAttemptWrite(Strict):
    request_id: UUID
    question_id: QuestionId
    question_version: Annotated[int, Field(strict=True, ge=1)]
    choice_index: Annotated[int, Field(strict=True, ge=0, le=7)]
    elapsed_seconds: Annotated[int, Field(strict=True, ge=0, le=21600)]

class ExamAttempt(Strict):
    id: str
    question: ExamQuestion
    question_id: str
    question_version: int
    choice_index: int
    correct_index: int
    correct: bool
    explanation: str
    study_date: date
    answered_at: datetime | None
    elapsed_seconds: int | None
    source: Literal['submitted', 'legacy_first', 'legacy_latest']

class ExamHistory(Strict):
    items: list[ExamAttempt]
    total: int

class ExamProgress(Strict):
    question_id: str
    attempt_count: int
    latest_correct: bool
    ever_wrong: bool
    last_date: date
    next_review_date: date | None

class ExamPlanBlock(Strict):
    subject: str
    minutes: int
    instruction: str

class ExamPractice(Strict):
    catalog_version: str
    day: date
    today: date
    questions: list[ExamQuestion]
    progress: list[ExamProgress]
    queue: list[str]
    plan: list[ExamPlanBlock]
    total_minutes: int
    legacy_notice: str
