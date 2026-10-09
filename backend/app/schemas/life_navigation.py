"""Bounded private planning DTOs; no health records, credentials or AI inputs."""
import json
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(max_length=4000)]
Minutes = Annotated[int, Field(strict=True, ge=0, le=1440)]
Revision = Annotated[int, Field(strict=True, ge=0)]
TrackId = Literal['main', 'aux1', 'aux2', 'important', 'misc']

class Typed(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Strategy(Typed):
    vision: Text = ''
    annual_goal: Text = ''
    primary_question: Text = ''

class Quarter(Typed):
    review: Text = ''
    strategy: Text = ''
    decomposition: Text = ''
    plan: Text = ''
    risk: Text = ''

class Track(Typed):
    id: TrackId
    title: Text = ''
    criterion: Text = ''
    strategy_link: Text = ''
    next_step: Text = ''

class Task(Typed):
    id: UUID
    date: date
    role: Literal['main', 'auxiliary', 'other'] = 'other'
    track_id: TrackId = 'misc'
    slot: Literal['morning', 'afternoon', 'evening', 'flexible'] = 'flexible'
    title: Text = ''
    criterion: Text = ''
    estimated_minutes: Minutes | None = None
    actual_minutes: Minutes | None = None
    status: Literal['planned', 'doing', 'done', 'skipped'] = 'planned'
    result: Text = ''
    root_cause: Text = ''
    improvement: Text = ''

class Note(Typed):
    valuable: Text = ''
    beautiful: Text = ''
    mistake: Text = ''
    learning: Text = ''

class Review(Typed):
    summary: Text = ''
    gap: Text = ''
    learning: Text = ''
    next_week: Text = ''

class Archive(Typed):
    id: UUID
    created_at: datetime
    title: Annotated[str, Field(max_length=200)] = ''
    body: Annotated[str, Field(max_length=20000)] = ''
    source_revision: Revision

    @model_validator(mode='after')
    def aware_timestamp(self):
        if self.created_at.tzinfo is None:
            raise ValueError('归档时间必须含时区')
        return self

class Week(Typed):
    tracks: list[Track] = Field(default_factory=list, max_length=5)
    tasks: list[Task] = Field(default_factory=list, max_length=100)
    notes: dict[str, Note] = Field(default_factory=dict, max_length=7)
    review: Review = Field(default_factory=Review)
    archives: list[Archive] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def unique_items(self):
        if len({t.id for t in self.tracks}) != len(self.tracks):
            raise ValueError('主线编号不可重复')
        if len({a.id for a in self.archives}) != len(self.archives):
            raise ValueError('归档编号不可重复')
        return self

class Opportunity(Typed):
    id: UUID
    category: Literal['macro', 'industry', 'people', 'customer']
    insight: Text = ''
    evidence: Text = ''
    personal_fit: Text = ''
    assumption: Text = ''
    next_step: Text = ''
    success_criteria: Text = ''
    risk_limit: Text = ''
    review_date: date | None = None
    result: Text = ''
    evidence_level: Literal['unknown', 'hypothesis', 'signal', 'supported'] = 'unknown'
    fit: Literal['unknown', 'low', 'medium', 'high'] = 'unknown'

class Focus(Typed):
    phase: Literal['idle', 'focus', 'rest', 'paused'] = 'idle'
    focus_minutes: Annotated[int, Field(strict=True, ge=1, le=180)] = 25
    rest_minutes: Annotated[int, Field(strict=True, ge=1, le=60)] = 5
    rounds: Annotated[int, Field(strict=True, ge=1, le=12)] = 4
    current_round: Annotated[int, Field(strict=True, ge=1, le=12)] = 1
    deadline: datetime | None = None
    remaining_seconds: Annotated[int, Field(strict=True, ge=0, le=10800)] | None = None
    paused_phase: Literal['focus', 'rest'] | None = None
    task_id: UUID | None = None

    @model_validator(mode='after')
    def timer_state(self):
        if self.current_round > self.rounds:
            raise ValueError('计时轮次超出范围')
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError('计时截止时间必须含时区')
        if self.phase in {'focus', 'rest'}:
            if self.deadline is None or self.remaining_seconds is not None or self.paused_phase is not None:
                raise ValueError('活动计时状态不一致')
        elif self.phase == 'paused':
            if self.deadline is not None or self.remaining_seconds is None or self.paused_phase is None:
                raise ValueError('暂停计时状态不一致')
        elif self.deadline is not None or self.remaining_seconds is not None or self.paused_phase is not None:
            raise ValueError('空闲计时状态不一致')
        return self

class LifeData(Typed):
    strategy: Strategy = Field(default_factory=Strategy)
    quarters: dict[str, Quarter] = Field(default_factory=dict, max_length=100)
    weeks: dict[str, Week] = Field(default_factory=dict, max_length=200)
    opportunities: list[Opportunity] = Field(default_factory=list, max_length=100)
    focus: Focus = Field(default_factory=Focus)

    @model_validator(mode='after')
    def scoped_records(self):
        import re
        for key in self.quarters:
            if not re.fullmatch(r'[1-9][0-9]{3}-Q[1-4]', key):
                raise ValueError('季度编号无效')
        tasks = set()
        for key, week in self.weeks.items():
            try:
                start = date.fromisoformat(key)
            except ValueError as exc:
                raise ValueError('周编号无效') from exc
            if start.isoformat() != key or start.weekday() != 0:
                raise ValueError('周编号必须是周一日期')
            end = start + timedelta(days=6)
            for task in week.tasks:
                if task.id in tasks:
                    raise ValueError('任务编号必须全局唯一')
                tasks.add(task.id)
                if not start <= task.date <= end:
                    raise ValueError('任务日期不在所属周')
            for day in week.notes:
                try:
                    local_day = date.fromisoformat(day)
                except ValueError as exc:
                    raise ValueError('日记录日期无效') from exc
                if local_day.isoformat() != day or not start <= local_day <= end:
                    raise ValueError('日记录不在所属周')
        if len({o.id for o in self.opportunities}) != len(self.opportunities):
            raise ValueError('机会编号不可重复')
        if self.focus.task_id is not None and self.focus.task_id not in tasks:
            raise ValueError('计时任务不存在')
        if len(json.dumps(self.model_dump(mode='json'), ensure_ascii=False).encode()) > 256 * 1024:
            raise ValueError('规划正文超过大小限制')
        return self

class LifeWorkspace(Typed):
    schema_version: Literal['life_navigation.v1'] = 'life_navigation.v1'
    revision: Revision = 0
    data: LifeData = Field(default_factory=LifeData)
    updated_at: datetime | None = None

    @model_validator(mode='after')
    def timestamp_matches_revision(self):
        if self.revision == 0 and self.updated_at is not None:
            raise ValueError('空白规划不可携带保存时间')
        if self.revision > 0 and (self.updated_at is None or self.updated_at.tzinfo is None):
            raise ValueError('保存时间必须含时区')
        return self

class LifeHistory(Typed):
    revision: Annotated[int, Field(strict=True, ge=1)]
    data: LifeData
    updated_at: datetime

    @model_validator(mode='after')
    def aware_timestamp(self):
        if self.updated_at.tzinfo is None:
            raise ValueError('版本时间必须含时区')
        return self

class LifeWorkspaceWrite(Typed):
    expected_revision: Revision
    data: LifeData

class LifeRevisionRequest(Typed):
    expected_revision: Revision

class LifeBackup(Typed):
    schema_version: Literal['life_navigation.backup.v1'] = 'life_navigation.backup.v1'
    workspace: LifeWorkspace
    history: list[LifeHistory] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def valid_history(self):
        revisions = [v.revision for v in self.history]
        if revisions != sorted(set(revisions)) or any(v > self.workspace.revision for v in revisions):
            raise ValueError('备份版本历史无效')
        if len(json.dumps(self.model_dump(mode='json'), ensure_ascii=False).encode()) > 6 * 1024 * 1024:
            raise ValueError('备份超过大小限制')
        return self

class LifeImport(Typed):
    expected_revision: Revision
    backup: LifeBackup
