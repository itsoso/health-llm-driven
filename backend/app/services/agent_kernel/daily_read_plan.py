"""Server-owned daily read scope, shared by tool selection and authorization.

Only current-user retrospective questions and today's summary have defaults.
The plan never authorizes writes, arbitrary people or model-provided dates.
Advice is a separate goal; a trailing advice request cannot erase a read goal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from app.services.agent_kernel.health_semantics import (
    active_health_read_clause,
    authorization_behavior_digest,
    authorization_grammar_digest,
    authorization_module_behavior_names,
    health_read_cancelled,
    normalize_health_authorization_text,
)
from app.services.agent_query_window import resolve_calendar_query_window


# These are the currently date-exact data planes. A summary must disclose this
# scope rather than imply unqueried medication, genetics or activity are known.
DAILY_SUMMARY_DIMENSIONS = ("diet", "sleep")
_DAY = (r"昨晚|昨夜|昨天|昨日|前天|今天|今日|"
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日|号)?|"
        r"(?:本周|这周|上周)[一二三四五六日天]")
_QUESTION_RE = re.compile(
    rf"(?:我(?:的)?)?(?:{_DAY})"
    r"(?P<evening>晚上|夜里|夜间)?(?:的)?(?:我(?:的)?)?"
    r"(?:(?:(?P<sleep>睡眠|睡得|睡的|睡觉)(?:记录|数据|质量|情况)?|"
    r"(?:饮食|餐食)(?:记录|数据|情况)?)(?:怎么样|怎样|如何)|"
    r"(?:都)?吃(?:了|过)(?:些)?(?:什么|啥|哪些)(?:东西|食物)?)"
)
_SUMMARY_RE = re.compile(
    r"(?:(?:请)?(?:给我|帮我)?(?:做|做个|做一份)?(?:今天|今日)(?:的)?"
    r"(?:健康|身体状况|身体状态)?(?:总结|汇总)|"
    r"(?:请)?(?:给我|帮我)?(?:总结|汇总)(?:一下)?(?:我(?:的)?)?"
    r"(?:今天|今日)(?:的)?(?:健康情况|健康状况|身体状况|身体状态|情况)?)"
)
_ADVICE_SUFFIX_RE = re.compile(
    r"[，,。.!！?？；;]*(?:(?:并且|然后|并|再|也)(?:请)?)?"
    r"(?:(?:请)?(?:给我|给出|提供)(?:一些|一点|些|点)?(?:建议|意见)|"
    r"(?:今天)?(?:是否|能否)适合(?:锻炼|运动))"
    r"[，,。.!！?？；;]*$"
)


@dataclass(frozen=True)
class DailyReadPlan:
    dimensions: tuple[str, ...]
    start_date: str
    end_date: str
    timezone: str
    meal_type: str | None = None
    asks_advice: bool = False
    is_summary: bool = False

    def queries(self) -> tuple[dict[str, str], ...]:
        return tuple({"dimension": dimension, "start_date": self.start_date,
                      "end_date": self.end_date, "timezone": self.timezone}
                     for dimension in self.dimensions)

    def diet_list_args(self) -> dict[str, str | int] | None:
        if self.dimensions != ("diet",) or self.start_date != self.end_date:
            return None
        args = {"record_type": "diet", "operation": "list", "date": self.start_date}
        if self.meal_type:
            args["meal_type"] = self.meal_type
            args["limit"] = 100
        return args


def _daily_read_frame(text: str) -> tuple[str, tuple[str, ...], bool, bool, str | None] | None:
    if health_read_cancelled(text):
        return None
    normalized = re.sub(r"\s+", "", normalize_health_authorization_text(
        active_health_read_clause(text)))
    suffix = _ADVICE_SUFFIX_RE.search(normalized)
    core = normalized[:suffix.start()] if suffix else normalized
    core = core.strip("，,。.!！?？；;")
    question = _QUESTION_RE.fullmatch(core)
    if question:
        dimension = "sleep" if question.group("sleep") else "diet"
        meal = ("dinner" if dimension == "diet" and
                (question.group("evening") or re.search(r"昨晚|昨夜", core)) else None)
        return core, (dimension,), suffix is not None, False, meal
    if _SUMMARY_RE.fullmatch(core):
        return core, DAILY_SUMMARY_DIMENSIONS, suffix is not None, True, None
    return None


def daily_question_dimension(text: str) -> str | None:
    frame = _daily_read_frame(text)
    return frame[1][0] if frame and len(frame[1]) == 1 else None


def resolve_daily_read_plan(
    text: str, reference_now: datetime, *, timezone_name: str = "Asia/Shanghai",
) -> DailyReadPlan | None:
    """Bind one accepted read frame to an exact business day without model input."""
    frame = _daily_read_frame(text)
    if frame is None:
        return None
    core, dimensions, asks_advice, is_summary, meal = frame
    window = resolve_calendar_query_window(
        core, reference_now, dimensions[0], timezone_name=timezone_name)
    if window is None:
        return None
    return DailyReadPlan(dimensions=dimensions, **window, meal_type=meal,
                         asks_advice=asks_advice, is_summary=is_summary)


def daily_read_plan_contract_payload() -> dict[str, str]:
    return {
        "version": "daily-read-plan-v1",
        "grammar": authorization_grammar_digest(globals()),
        "behavior": authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)),
        "plan_methods": authorization_behavior_digest(
            {"queries": DailyReadPlan.queries, "diet_list_args": DailyReadPlan.diet_list_args},
            ("queries", "diet_list_args")),
    }
