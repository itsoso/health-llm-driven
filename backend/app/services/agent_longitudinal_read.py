"""Bounded recent personal analysis reads, with actual-event provenance.

Authorization is projected only from this turn's active request. Diagnosis
history is context, not a date override. Query args contain frozen dates;
execution never resolves a rolling window again or accepts a model owner.
"""

from __future__ import annotations

from datetime import timedelta
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.agent_kernel.health_semantics import (
    active_health_instruction_text,
    health_read_has_nonself_subject,
    _strip_exam_request_scaffolding,
)
from app.services.agent_query_window import (
    QueryWindow,
    resolve_calendar_query_window,
    _DATE_RE,
    _RELATIVE_RE,
    _WEEKDAY_RE,
    parse_query_window,
    read_calendar_health_query,
    MAX_CALENDAR_ROWS,
    _bounded_result,
    _serial,
)

_DOMAINS = {
    "diet": r"饮食|餐食|吃了什么",
    "sleep": r"睡眠|睡得|睡觉",
    "workout": r"运动|锻炼|训练",
    "supplements": r"补剂|营养补充剂",
}
_NEGATIVE = re.compile(
    r"不要|不用|无需|不必|不需要|未授权|不授权|不允许|(?<!分)别(?:再)?(?:查|读|调|获取|分析|看)|取消|停止|不(?:再|查|读取|调用|获取)|假如|假设|如果|举例|例句"
)
_MUTATION = re.compile(r"删除|撤销|写入|保存|添加|记下来|修改|更新|执行计划")
_RECENT = re.compile(r"(?:最近|近|过去)([0-9]+|[一二两三四五六七八九十]+)(天|日|周)")
_AMBIGUOUS_DATE = re.compile(
    r"\d{4}[-/年]|\d{1,2}月|(?<!\d)\d{1,2}[-/]\d{1,2}(?!\d)|"
    r"(?<![当目])(?:今|昨|前|明|后)(?:天|日|晚|夜)|"
    r"(?:周|星期|礼拜)[一二三四五六日天]|上周|本周|这周|下周|"
    r"上个月|本月|今年|去年|几天|几周|个月|半年|数月|几月|月前|至今|以来|截至|截止|全部|所有|完整历史"
)
_TOOL_READ = re.compile(
    r"查询|查看|读取|调取|查一下|调用[^。\n]*(?:工具|接口|模块|skills)|"
    r"发起[^。\n]*(?:HTTP|请求)|(?:MCP|Skills)的?调用",
    re.I,
)

# These clauses restrict a read; an unrecognized remainder must not disappear
# into the default recent window or a separate calendar clause.
_RESTRICTION_PREFIX = re.compile(
    r"(?:(?:只|仅)(?:查询|查看|读取|调取|查|看)|仅限|限定(?:范围)?(?:为|在)?|只限)(?:于)?\s*"
)


_DOMAIN_SCOPE = re.compile(
    r"(?:我|本人|自己)?的?(?:" + "|".join(_DOMAINS.values()) + r")(?:记录|数据)?"
    r"(?:\s*(?:以及|和|与|及|、)\s*(?:我|本人|自己)?的?(?:"
    + "|".join(_DOMAINS.values()) + r")(?:记录|数据)?)*"
)
# Subday records are not representable by this calendar-day adapter. These are
# temporal tokens, not allowed/disallowed request phrases or politeness forms.
_SUBDAY_SCOPE = re.compile(r"(?:今|昨|前|明|后)(?:早|晨|午)|上午|下午|中午|凌晨|清晨|早上|早晨|午后")
_RETROSPECTIVE_SCOPE = re.compile(r"(?:分析|复盘|总结).*(?:行动|健康情况|健康状态|一天|日程)")


def _diagnosis_background_clause(clause: str) -> bool:
    return bool(
        not _RESTRICTION_PREFIX.search(clause)
        and re.search(r"诊断|确诊|病史|既往|[一二两三四五六七八九十几\d]+个?多?月前", clause)
        and not re.search(
            r"查询|查看|读取|调取|调用|记录|分析|复盘|结合|" + "|".join(_DOMAINS.values()), clause,
        )
    )


def _number(text: str) -> int:
    if text.isdigit():
        return int(text)
    digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if "十" in text:
        if not re.fullmatch(r"[一二两三]?十[一二三四五六七八九]?", text):
            return 0
        first, last = text.split("十", 1)
        return (digits.get(first, 1) * 10) + digits.get(last, 0)
    return digits.get(text, 0)


def longitudinal_read_scope_requested(snapshot) -> bool:
    """Routing discriminator, never authorization; invalid requests cannot fall back.

    Callers can first honor an independently resolved explicit calendar scope.
    Otherwise this flag plus an unresolved longitudinal scope means clarification,
    not permission to substitute an older rolling-read default.
    """
    text = active_health_instruction_text(snapshot.envelope.text)
    return bool(
        _TOOL_READ.search(text)
        and re.search(r"分析|复盘|总结|建议|状况", text)
        and any(re.search(pattern, text) for pattern in _DOMAINS.values())
    )


def _restricted_read_text(snapshot, active: str) -> str | None:
    """Consume every independent restriction; return None for unknown scope.

    Accepted scope tokens come from the existing recent/calendar/domain grammar.
    Calendar matches must consume the entire scope, not merely find a day in it.
    This is a rejection boundary, not an alternative source of read authority.
    """
    if not any(re.search(pattern, active) for pattern in _DOMAINS.values()) and not _RETROSPECTIVE_SCOPE.search(active):
        return active
    clauses = re.split(r"[，,。；;！？!?\n]", active)
    normalized = []
    domain_limits = []
    requested_domains = {key for key, pattern in _DOMAINS.items() if re.search(pattern, active)}
    for clause in clauses:
        if not _diagnosis_background_clause(clause) and _SUBDAY_SCOPE.search(clause):
            return None
        prefix = _RESTRICTION_PREFIX.search(clause)
        if prefix is None:
            normalized.append(clause)
            continue
        body = clause[prefix.end():].strip()
        scope = re.sub(r"(?:并|再|然后)(?:分析|复盘|总结)(?:一下)?$", "", body)
        domains = {key for key, pattern in _DOMAINS.items() if re.search(pattern, scope)}
        residue = _DOMAIN_SCOPE.sub("", scope)
        residue = re.sub(r"(?:我|本人|自己)?的|记录|数据|\s", "", residue)
        if domains:
            domain_limits.append(domains)
        recent = _RECENT.fullmatch(residue)
        if recent is not None:
            days = _number(recent[1]) * (7 if recent[2] == "周" else 1)
            if not 1 <= days <= 31:
                return None
        elif residue in {"", "近期", "最近"}:
            if not domains:
                return None
        else:
            # Reuse calendar lexical tokens and the actual window validator.
            # Unknown subday/event-relative suffixes remain and fail closed.
            calendar_remainder = _WEEKDAY_RE.sub("", _RELATIVE_RE.sub("", _DATE_RE.sub("", residue)))
            if calendar_remainder not in {"", "到", "至", "~", "～"}:
                return None
            if resolve_calendar_query_window(
                residue, snapshot.context.current_time,
                "sleep" if domains == {"sleep"} else "diet",
                timezone_name=snapshot.context.timezone,
            ) is None:
                return None
        # Preserve pre-marker content: it may carry a subject or another read
        # request. Separating a scope declaration must not erase that authority.
        lead = clause[:prefix.start()].strip()
        if lead:
            lead_scope = _strip_exam_request_scaffolding(lead)
            if lead_scope not in {"", "你", "您"} and not re.fullmatch(
                r"(?:查询|读取|时间|日期|数据)?范围", lead_scope,
            ):
                # An unknown pre-marker subject must not be discarded when
                # the marker is no longer constrained to the clause start.
                return None
            normalized.append(lead)
        normalized.append(body)
    if any(not requested_domains <= limit for limit in domain_limits):
        return None
    return "。".join(normalized)


def longitudinal_read_restrictions_unresolved(snapshot) -> bool:
    """Reject unknown explicit limits before any rolling/calendar fallback."""
    active = active_health_instruction_text(snapshot.envelope.text)
    active = re.sub(
        r"“[^”]*”|「[^」]*」|『[^』]*』|\"[^\"\n]*\"|'[^'\n]*'|‘[^’]*’|`[^`]*`",
        "", active,
    )
    return _restricted_read_text(snapshot, active) is None


def _request(snapshot) -> tuple[str, int, bool] | None:
    owner = snapshot.context.user_id
    if (
        isinstance(owner, bool)
        or not isinstance(owner, int)
        or owner <= 0
        or snapshot.envelope.user_id != owner
    ):
        return None
    active = active_health_instruction_text(snapshot.envelope.text)
    active = re.sub(
        r"""“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"|'[^'\n]*'|‘[^’]*’|`[^`]*`""",
        "",
        active,
    )
    if (
        re.search(r"""[“”「」『』"'‘’`]""", active)
        or _NEGATIVE.search(active)
        or _MUTATION.search(active)
    ):
        return None
    if not re.search(r"我|本人", active) or re.search(
        r"朋友|他人|别人|同事|家人|妈妈|爸爸|父亲|母亲|妻子|丈夫|孩子|他们|她们|他的|她的",
        active,
    ):
        return None
    active = _restricted_read_text(snapshot, active)
    if active is None:
        return None
    # Identify subjects at each requested domain, including names without 的.
    # A beneficiary such as 给我建议 in another clause is not a record owner.
    targets = "|".join(_DOMAINS.values())
    for clause in re.split(r"[，,。；;！？!?\n、]|以及|和|与", active):
        domain = re.search(targets, clause)
        if domain is None:
            continue
        prefix = _RECENT.sub("", clause[: domain.start()])
        prefix = re.sub(
            r"请|要|分别|先|再|查询|查看|读取|调取|结合|分析|包括|针对|基于|"
            r"近期|最近|过去|日常|每天|实际|服用|在|的|里|内|\s",
            "",
            prefix,
        )
        if prefix not in {"", "我", "本人", "自己"}:
            return None
    # Use the shared owner parser on explicit query clauses, not the separate
    # diagnosis narrative (which can contain dates and clinical entity names).
    for clause in re.split(r"[，,。；;！？!?\n]", active):
        if re.search(
            r"查询|查看|读取|调取", clause
        ) and health_read_has_nonself_subject(clause):
            return None
    if not re.search(r"分析|复盘|总结|建议|状况", active):
        return None
    if not _TOOL_READ.search(active):
        return None
    # Only standalone diagnosis-history clauses may lose background dates.
    # A clause requesting records since diagnosis must remain and fail closed.
    clauses = re.split(r"[，,。；;\n]", active)
    relevant = [clause for clause in clauses if not _diagnosis_background_clause(clause)]
    request = "。".join(relevant)
    hits = list(_RECENT.finditer(request))
    if len(hits) > 1:
        return None
    days = 7
    if hits:
        hit = hits[0]
        days = _number(hit[1]) * (7 if hit[2] == "周" else 1)
    remainder = _RECENT.sub("", request)
    # Calendar scope can be expressed in a separate active clause. Leave it
    # to the exact calendar binder; never replace an explicit day with 7 days.
    if not 1 <= days <= 31 or _AMBIGUOUS_DATE.search(remainder):
        return None
    return request, days, not hits


def resolve_longitudinal_read_queries(snapshot) -> tuple[dict, ...] | None:
    request = _request(snapshot)
    if request is None:
        return None
    text, days, _ = request
    dimensions = [
        dimension for dimension, pattern in _DOMAINS.items() if re.search(pattern, text)
    ]
    if not dimensions:
        return None
    try:
        zone = ZoneInfo(snapshot.context.timezone)
        now = snapshot.context.current_time
        local = (
            now.replace(tzinfo=zone)
            if now.utcoffset() is None
            else now.astimezone(zone)
        )
        end = local.date()
        window = parse_query_window(
            {
                "start_date": (end - timedelta(days=days - 1)).isoformat(),
                "end_date": end.isoformat(),
                "timezone": snapshot.context.timezone,
            }
        )
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return None
    return tuple(
        {"dimension": dimension, "days": days, **window.as_dict()}
        for dimension in dimensions
    )


def longitudinal_read_limitations(snapshot) -> tuple[str, ...]:
    if resolve_longitudinal_read_queries(snapshot) is None:
        return ()
    text, _, defaulted = _request(snapshot)
    result = ["default_recent_7_days"] if defaulted else []
    if re.search(r"情绪|心情", text):
        result.append("mood_not_queried")
    if re.search(r"工作", text):
        result.append("work_not_queried")
    return tuple(result)


def _rows(db, model, day_column, owner: int, window: QueryWindow):
    rows = (
        db.query(model)
        .filter(
            model.user_id == owner,
            day_column >= window.start_date,
            day_column <= window.end_date,
        )
        .order_by(day_column, model.id)
        .limit(MAX_CALENDAR_ROWS + 1)
        .all()
    )
    if len(rows) > MAX_CALENDAR_ROWS:
        raise ValueError("longitudinal_query_result_limit_exceeded")
    return rows


def read_longitudinal_health_query(
    db, user_id: int, dimension: str, window: QueryWindow
) -> dict:
    """Read actual owned events; no plans, inferred adherence, or remote calls.

    Float precision is preserved in this data projection. The presentation
    layer must use number_format rather than rounding these evidence records.
    Independent recording surfaces may overlap; records are never summed as
    unique events or deduplicated by activity/supplement name.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("longitudinal_query_owner_required")
    window = parse_query_window(window.as_dict())
    if dimension in {"diet", "sleep"}:
        return read_calendar_health_query(db, user_id, dimension, window)
    if dimension not in {"workout", "supplements"}:
        raise ValueError("longitudinal_query_dimension_unsupported")
    from app.models.daily_health import WorkoutRecord, ExerciseRecord, SupplementIntake
    from app.models.supplement import SupplementDefinition, SupplementRecord

    records = []
    limitations = [
        "recorded_events_not_complete_history",
        "independent_sources_may_overlap",
        "missing_metric_is_unknown_not_zero",
    ]
    if dimension == "workout":
        for row in _rows(
            db, WorkoutRecord, WorkoutRecord.workout_date, user_id, window
        ):
            records.append(
                {
                    "id": row.id,
                    "record_kind": "workout_record",
                    "source_table": "workout_records",
                    "record_date": row.workout_date.isoformat(),
                    "workout_type": row.workout_type,
                    "duration_seconds": row.duration_seconds,
                    "distance_meters": row.distance_meters,
                    "calories": row.calories,
                    "avg_heart_rate": row.avg_heart_rate,
                }
            )
        for row in _rows(
            db, ExerciseRecord, ExerciseRecord.record_date, user_id, window
        ):
            records.append(
                {
                    "id": row.id,
                    "record_kind": "exercise_record",
                    "source_table": "exercise_records",
                    "record_date": row.record_date.isoformat(),
                    "workout_type": row.exercise_type,
                    "duration_seconds": row.duration_seconds
                    if row.duration_seconds is not None
                    else (row.duration * 60 if row.duration is not None else None),
                    "distance_meters": row.distance * 1000
                    if row.distance is not None
                    else None,
                    "calories": row.calories_burned,
                    "avg_heart_rate": None,
                }
            )
        source = "owned_actual_workout_records"
    else:
        for row in _rows(
            db, SupplementIntake, SupplementIntake.record_date, user_id, window
        ):
            records.append(
                {
                    "id": row.id,
                    "record_kind": "supplement_intake",
                    "source_table": "supplement_intakes",
                    "record_date": row.record_date.isoformat(),
                    "taken": True,
                    "supplement_name": row.supplement_name,
                    "dosage": row.dosage,
                    "unit": row.unit,
                    "intake_time": _serial(row.intake_time),
                }
            )
        # Both sides are owned; an invalid cross-owner FK must not expose names.
        taken = (
            db.query(SupplementRecord, SupplementDefinition.name)
            .join(
                SupplementDefinition,
                SupplementRecord.supplement_id == SupplementDefinition.id,
            )
            .filter(
                SupplementRecord.user_id == user_id,
                SupplementDefinition.user_id == user_id,
                SupplementRecord.taken.is_(True),
                SupplementRecord.record_date >= window.start_date,
                SupplementRecord.record_date <= window.end_date,
            )
            .order_by(SupplementRecord.record_date, SupplementRecord.id)
            .limit(MAX_CALENDAR_ROWS + 1)
            .all()
        )
        for row, name in taken:
            records.append(
                {
                    "id": row.id,
                    "record_kind": "supplement_taken_log",
                    "source_table": "supplement_records",
                    "record_date": row.record_date.isoformat(),
                    "taken": True,
                    "supplement_name": name,
                    "dosage": None,
                    "unit": None,
                    "intake_time": _serial(row.taken_time),
                }
            )
        source = "owned_actual_supplement_intake_logs"
        limitations.append("definition_dose_not_actual_intake_dose")
    if len(records) > MAX_CALENDAR_ROWS:
        raise ValueError("longitudinal_query_result_limit_exceeded")
    records.sort(key=lambda row: (row["record_date"], row["source_table"], row["id"]))
    return _bounded_result(
        {
            "dimension": dimension,
            "window": window.as_dict(),
            "records": records,
            "source_scope": source,
            "availability": "available" if records else "no_data",
            "limitations": limitations,
        }
    )


def longitudinal_read_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest,
        authorization_grammar_digest,
        authorization_module_behavior_names,
    )

    return {
        "version": "longitudinal-read.v1",
        "grammar": authorization_grammar_digest(globals()),
        "behavior": authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)
        ),
    }
