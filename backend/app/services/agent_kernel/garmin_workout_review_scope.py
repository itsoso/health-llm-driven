"""One closed current-user Garmin sync and today's latest running review.

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


def garmin_workout_review_scope_contract_payload() -> dict:
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest,
        authorization_module_behavior_names,
    )
    return {"version": "garmin-workout-review-v1",
            "grammar": authorization_grammar_digest(globals()),
            "behavior": authorization_behavior_digest(globals(), authorization_module_behavior_names(globals(), __name__))}
