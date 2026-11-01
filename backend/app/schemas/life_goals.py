"""Minimal current planning context for owner-authorized read clients."""
from datetime import date, datetime
from typing import Literal
from pydantic import Field
from app.schemas.life_navigation import Typed, Text, Revision, Strategy, Track


class CurrentQuarter(Typed):
    key: str
    strategy: Text = ''
    decomposition: Text = ''
    plan: Text = ''


class CurrentWeek(Typed):
    start: date
    tracks: list[Track] = Field(default_factory=list, max_length=5)


class LifeGoalsContext(Typed):
    schema_version: Literal['life_navigation.goals.v1'] = 'life_navigation.goals.v1'
    owner_id: int
    local_date: date
    timezone: str
    revision: Revision
    updated_at: datetime | None
    strategy: Strategy
    quarter: CurrentQuarter
    week: CurrentWeek
    missing_horizons: list[Literal['life', 'annual', 'quarterly', 'monthly', 'weekly']]
