"""Private morning report projection; no executable content or credentials."""
from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field


class MorningReadingItem(BaseModel):
    report_id: UUID
    title: str = Field(min_length=1, max_length=300)
    generated_at: datetime
    reading_date: date


class MorningReadingList(BaseModel):
    items: list[MorningReadingItem]
    next_offset: int | None


class MorningReadingDetail(MorningReadingItem):
    content_text: str = Field(min_length=1, max_length=1_000_000)
