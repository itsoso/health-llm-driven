"""Closed current-user Garmin sync with running or last-night sleep review.

Background distance never creates a workout. Queue acceptance never attests to
completion, and selection of an existing row never proves this sync succeeded.
"""
from dataclasses import dataclass
from datetime import datetime
import re
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class GarminWorkoutReviewScope:
    reported_distance_km: float | None = None
    dimension: str = 'workout'

    def query_args(self, reference_now: datetime, timezone: str) -> dict:
        if reference_now.utcoffset() is None:
            raise ValueError('garmin_review_reference_time_required')
        day = reference_now.astimezone(ZoneInfo(timezone)).date().isoformat()
        return {'dimension': 'workout', 'start_date': day, 'end_date': day, 'timezone': timezone}


_SYNC = re.compile(r'(?:请|请你|帮我|请帮我)?同步(?:一下)?(?:我的?)?(?:佳明|Garmin)(?:的)?数据', re.I)
_READ = re.compile(r'(?:获取(?:到)?|查看)(?:一下)?(?:我的?)?最新(?:一次)?(?:的)?运动(?:的)?(?:记录|数据)')
_BACKGROUND = re.compile(r'我(?:今天|刚才|刚|已经)?(?:跑了(?P<distance>[0-9]+(?:\.[0-9]+)?|[一二三四五六七八九十])(?:公里|千米)|跑步了)')
_ANALYSIS = re.compile(r'(?:请|请你|帮我)?分析(?:一下)?(?:我)?刚才(?:(?:的|这次)?跑步|跑的情况怎么样)')
_ADVICE = re.compile(r'(?:并|并且|再)?给我(?:一些|点)?建议')


def resolve_garmin_workout_review_scope(text: str) -> GarminWorkoutReviewScope | None:
    # Do not erase quoted operands or modifiers: each byte must belong to a
    # known role. Rejected requests retain the existing ordinary policy.
    normalized = re.sub(r'\s+', '', str(text or '')).strip('。.!！')
    clauses = [part for part in re.split(r'[，,。；;]|然后|(?=并给我|并且给我)', normalized) if part]
    if len(clauses) not in {4, 5} or not _SYNC.fullmatch(clauses[0]) or not _READ.fullmatch(clauses[1]):
        return None
    distance = None
    if len(clauses) == 5:
        background = _BACKGROUND.fullmatch(clauses[2])
        if background is None:
            return None
        if background['distance'] is not None:
            spoken = background['distance']
            distance = float('一二三四五六七八九十'.index(spoken) + 1) if spoken in '一二三四五六七八九十' else float(spoken)
            if not 0 < distance <= 500:
                return None
    if not _ANALYSIS.fullmatch(clauses[-2]) or not _ADVICE.fullmatch(clauses[-1]):
        return None
    return GarminWorkoutReviewScope(distance)


@dataclass(frozen=True)
class GarminSleepReviewScope:
    dimension: str = 'sleep'

    def query_args(self, reference_now: datetime, timezone: str) -> dict:
        if reference_now.utcoffset() is None:
            raise ValueError('garmin_review_reference_time_required')
        # Overnight sleep belongs to the wake date in the authenticated timezone.
        day = reference_now.astimezone(ZoneInfo(timezone)).date().isoformat()
        return {'dimension': 'sleep', 'start_date': day, 'end_date': day, 'timezone': timezone}


_SLEEP_SYNC = r'(?:请帮我|请你|请|帮我)?(?:同步|更新|刷新)(?:一下)?(?:我的?)?(?:佳明|garmin)的?数据'
_LAST_NIGHT = r'(?:我(?:的)?)?(?:昨晚|昨天晚上)(?:我(?:的)?)?'
_SLEEP_READ = (r'(?:请帮我|请你|请|帮我)?(?:查看|看看|查询|分析)(?:一下)?' + _LAST_NIGHT
               + r'的?睡眠(?:情况|数据|记录)?|'
               + _LAST_NIGHT + r'(?:睡得(?:怎么样|怎样|如何)|的?睡眠(?:情况)?(?:怎么样|怎样|如何))')
_CLAUSE_JOIN = r'(?:[\s，,。；;！？!?]+|然后)'
_SLEEP_THEN_SYNC = re.compile(r'(?:' + _SLEEP_READ + r')' + _CLAUSE_JOIN + _SLEEP_SYNC + r'[。.!！\s]*', re.I)
_SYNC_THEN_SLEEP = re.compile(_SLEEP_SYNC + _CLAUSE_JOIN + r'(?:' + _SLEEP_READ + r')[。.!！?？\s]*', re.I)


def resolve_garmin_review_scope(text: str) -> GarminWorkoutReviewScope | GarminSleepReviewScope | None:
    text = str(text or '').strip()
    # Full-match both clauses. Quotes, other owners, cancellation, status
    # questions, future scheduling and additional actions cannot grant a job.
    if _SLEEP_THEN_SYNC.fullmatch(text) or _SYNC_THEN_SLEEP.fullmatch(text):
        return GarminSleepReviewScope()
    return resolve_garmin_workout_review_scope(text)


def garmin_workout_review_scope_contract_payload() -> dict:
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest,
        authorization_module_behavior_names,
    )
    methods = {
        'sleep_query_args': GarminSleepReviewScope.query_args,
        'workout_query_args': GarminWorkoutReviewScope.query_args,
    }
    return {"version": "garmin-review-v2",
            "grammar": authorization_grammar_digest(globals()),
            "date_binding": authorization_behavior_digest(methods, tuple(methods)),
            "behavior": authorization_behavior_digest(globals(), authorization_module_behavior_names(globals(), __name__))}
