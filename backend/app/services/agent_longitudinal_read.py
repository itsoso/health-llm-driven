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
    _health_read_entity_expression,
    _strip_current_user_owner,
    resolve_illness_entity,
    has_positive_health_read_verb,
    ANALYZED_MATERIAL_QUOTE_PAIRS,
    _analyzed_material_end,
)
from app.services.agent_query_window import (
    QueryWindow,
    resolve_calendar_query_window,
    _DATE_RE,
    _RELATIVE_RE,
    _WEEKDAY_RE,
    _WEEK_RE,
    parse_query_window,
    read_calendar_health_query,
    MAX_CALENDAR_ROWS,
    _bounded_result,
    _serial,
)

_DOMAINS = {
    "diet": r"饮食|餐食|吃了什么",
    "sleep": r"睡眠血氧|睡眠|睡得|睡觉",
    "spo2": r"血氧|[Ss][Pp][Oo]2",
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
    r"(?:(?:只|仅)(?:查询|查看|读取|调取|分析|复盘|总结|查|看)|仅限|限定(?:范围)?(?:为|在)?|只限)(?:于)?\s*"
)


_DOMAIN_ITEM_PREFIX = r"(?:我|本人|自己)?(?:的|日常|每天|实际|在|服用|近期|最近)*"
_DOMAIN_ITEM_SUFFIX = r"(?:的|记录|数据|状态|情况|等等)*"
_DOMAIN_ITEM = _DOMAIN_ITEM_PREFIX + r"(?:" + "|".join(_DOMAINS.values()) + r")" + _DOMAIN_ITEM_SUFFIX
_DOMAIN_SCOPE = re.compile(_DOMAIN_ITEM + r"(?:(?:以及|和|与|及|、)" + _DOMAIN_ITEM + r")*")
_CONTEXT_DOMAIN_ITEM = _DOMAIN_ITEM_PREFIX + r"(?:" + "|".join(_DOMAINS.values()) + r"|情绪|心情|工作)" + _DOMAIN_ITEM_SUFFIX
_CONTEXT_DOMAIN_SCOPE = re.compile(r"(?:以及|和|与|及)?" + _CONTEXT_DOMAIN_ITEM + r"(?:(?:以及|和|与|及|、)" + _CONTEXT_DOMAIN_ITEM + r")*")
_ANALYSIS_GOAL = (
    r"(?:(?:并且|然后|并|再|也|来|这样才能)(?:请)?)?"
    r"(?:(?:依据|基于)(?:真实|已有|这些|上述|以上)(?:数据|记录))?"
    r"(?:(?:分析|复盘|总结)(?:一下)?(?:(?:我(?:的)?)?(?:当前|现在)?(?:的)?(?:状况|情况|状态))?|"
    r"(?:给|给到|给出|提供)(?:我)?(?:一些|一点|些|点|精准的|你的)?(?:建议|意见))"
)
_ANALYSIS_GOAL_RE = re.compile(_ANALYSIS_GOAL)
_METHOD_CLAUSE_RE = re.compile(
    r"(?:要|请|先|再|然后|分别|去|或者|或|的|对应|相关|各个|各|模块|"
    r"工具|接口|HTTP|MCP|Skills|调用|发起|请求|查询|读取|已有|记录|数据|\s)+", re.I,
)
# Subday records are not representable by this calendar-day adapter. These are
# temporal tokens, not allowed/disallowed request phrases or politeness forms.
_SUBDAY_SCOPE = re.compile(r"(?:今|昨|前|明|后)(?:早|晨|午)|上午|下午|中午|凌晨|清晨|早上|早晨|午后")
_RETROSPECTIVE_SCOPE = re.compile(r"(?:分析|复盘|总结).*(?:行动|健康情况|健康状态|一天|日程)")


def _diagnosis_background_clause(clause: str) -> bool:
    """A historical diagnosis assertion is context; a date alone is not."""
    past = r"[一二两三四五六七八九十几\d]+个?多?月前"
    assertion = re.fullmatch(
        r"(?:我|本人)(?:的)?(?P<subject>.+?)(?:其实)?是(?:" + past + r")(?:的)?(?:事情|事)?", clause,
    )
    if assertion:
        subject = assertion["subject"]
        return subject in {"既往诊断", "诊断", "病史"} or resolve_illness_entity(subject).status == "exact"
    diagnosis = re.fullmatch(
        r"(?:我|本人)(?:在)?(?:" + past + r")(?:被)?(?:确诊|诊断)(?:为|了)?(?P<entity>.+)", clause,
    )
    return bool(diagnosis and resolve_illness_entity(diagnosis["entity"]).status == "exact")


def _diagnosis_context_goal(clause: str) -> bool:
    """A complete request to interpret diagnosis timing contains no read filter."""
    goal = re.fullmatch(
        r"(?:你)?(?:要|请)?基于(?P<context>.+?)(?:来)?(?:判断|推断)(?:我)?(?:当前|现在)(?:的)?状况",
        clause,
    )
    if not goal:
        return False
    context = goal["context"].replace("的", "")
    if context == "诊断时间":
        return True
    return context.endswith("诊断时间") and resolve_illness_entity(context[:-4]).status == "exact"


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


def _record_domains(text: str) -> set[str]:
    """A clinical entity containing a record-domain word is still an illness."""
    domains = set()
    for clause in re.split(r"[，,。；;！？!?\n]", text):
        entity, _ = _strip_current_user_owner(_health_read_entity_expression(clause))
        if resolve_illness_entity(entity).status == "exact":
            continue
        domains.update(key for key, pattern in _DOMAINS.items() if re.search(pattern, clause))
        if '睡眠血氧' in clause:
            domains.add('spo2')
    return domains


def _consumed_sync_clause(active: str, clause: str) -> bool:
    """Only a known sync act/status with no leftover constraint is ancillary."""
    if not re.search(r"佳明|garmin|同步|刷新|拉取", clause, re.I):
        return False
    from app.services.agent_kernel.read_task_scope import has_owned_sync_instruction
    command = has_owned_sync_instruction(active)
    status = bool(re.search(r"同步.*(?:吗|完成|状态)|(?:是否|有没有).*同步", clause))
    if not (command or status):
        return False
    rest = re.sub(r"garmin|佳明|同步|刷新|拉取", "", clause, flags=re.I)
    rest = _strip_exam_request_scaffolding(rest)
    return bool(re.fullmatch(
        r"(?:我|我的|的|数据|一下|主动|触发|说说|是否|有没有|完成|完了|好了|状态|成功|吗|了|\s)*", rest,
    ))


def _legacy_scope_residue(scope: str) -> str | None:
    """Reuse exact registered read entities, retaining every non-entity token."""
    from app.services.agent_kernel.capability_policy import (
        _illness_query_entities, _query_entity_known_dimensions,
    )
    entities = _illness_query_entities("查询" + scope)
    if not entities or any(len(_query_entity_known_dimensions(entity)) != 1 for entity in entities):
        return None
    rest = scope
    for entity in entities:
        # Positional qualifiers are scope, even if a legacy entity parser can
        # associate them with a health dimension. Never erase their spelling.
        if (_DATE_RE.search(entity) or _RELATIVE_RE.search(entity)
                or _RECENT.search(entity) or _SUBDAY_SCOPE.search(entity)
                or re.search(r"之前|之后|以前|以后|前|后", entity)):
            return None
        rest, count = re.subn(re.escape(entity), "", rest, count=1, flags=re.I)
        if count != 1:
            return None
    return re.sub(r"的|记录|数据|历史|病史|和|与|及|、|\s", "", rest)


def _legacy_comparison_scope(active: str) -> bool:
    """Recognize a fully consumed existing multi-window comparison frame.

    This only delegates to the original batch binder; that binder still checks
    every proposed child window, dimension and comparison operation.
    """
    from app.services.agent_kernel.capability_policy import (
        _query_scope_text, _illness_query_entities, _query_entity_known_dimensions,
        _explicit_query_windows, _HISTORY_QUERY_MULTI_ENTITY_RE,
        _HISTORY_QUERY_LEADING_VERB_RE, _HISTORY_QUERY_TRAILING_VERB_RE,
    )
    text = _query_scope_text(active)
    if _RESTRICTION_PREFIX.search(text):
        return False
    entities = _illness_query_entities(text)
    windows = _explicit_query_windows(text)
    if len(entities) < 2 or not windows or any(
        len(_query_entity_known_dimensions(entity)) != 1 for entity in entities
    ):
        return False
    residue = text
    for start, end, _days in reversed(windows):
        residue = residue[:start] + residue[end:]
    for entity in entities:
        # Exact entity removal must leave all unrepresented filters intact.
        residue, count = re.subn(re.escape(entity), "", residue, count=1, flags=re.I)
        if count != 1:
            return False
    residue = _strip_exam_request_scaffolding(residue)
    residue = _HISTORY_QUERY_LEADING_VERB_RE.sub("", residue)
    residue = _HISTORY_QUERY_TRAILING_VERB_RE.sub("", residue)
    residue = _HISTORY_QUERY_MULTI_ENTITY_RE.sub("", residue)
    residue = _strip_exam_request_scaffolding(residue)
    residue = _HISTORY_QUERY_LEADING_VERB_RE.sub("", residue)
    residue = _HISTORY_QUERY_TRAILING_VERB_RE.sub("", residue)
    return bool(re.fullmatch(r"(?:的|一下|比较|倍数|几倍|比例|比率|ratio|之比|占比|占多少|\s)*", residue, re.I))


def _complete_read_background(clause: str) -> bool:
    """Only affirmative narrative predicates can remove a clause from scope."""
    if _RESTRICTION_PREFIX.search(clause) or re.search(r"范围|时段|时限|要求|条件|限制", clause):
        return False
    if re.fullmatch(r"(?:这|以下|上面)?是?(?:一个|一段)?示例(?:文本|内容)?", clause):
        return True
    if _diagnosis_background_clause(clause):
        return True
    if re.fullmatch(r"(?:有人|医生|他|她)(?:说|提到|表示)", clause):
        return True  # Empty reporting introduction after quoted material removal.
    return bool(
        re.search(r"(?:我|本人)", clause)
        and re.search(r"(?:感觉|感到|比较|有点|不太|很|挺|已经|正在).+", clause)
        and not re.search(r"要|想|希望|需要|应该|应当|取|限定|之前|之后|以前|以后|前|后", clause)
    )


def _has_read_clause(clause: str) -> bool:
    # The shared scaffold parser consumes command prefixes. Searching the
    # whole clause for 查/比较 would turn 检查之前 or 工作比较忙 into read acts.
    core = _strip_exam_request_scaffolding(clause)
    consumed = clause[:len(clause) - len(core)] if core != clause else ""
    return bool(_TOOL_READ.search(clause) or has_positive_health_read_verb(consumed))


def _read_projection_parts(active: str) -> list[tuple[str, bool]]:
    """Select request/scope clauses positively; retain narrative for the model only."""
    parts = []
    listing = False
    domain_words = "|".join(_DOMAINS.values()) + "|情绪|心情|工作"
    list_item = (
        r"(?:我|本人|自己)?(?:的|日常|每天|实际|在|服用|近期|最近)*"
        r"(?:" + domain_words + r")(?:的|记录|数据|状态|情况|等等)*"
    )
    nominal_list = re.compile(r"(?:以及|和|与|及)?" + list_item + r"(?:(?:、|以及|和|与|及)" + list_item + r")*")
    for clause in re.split(r"[，,。；;！？!?\n]", active):
        clause = clause.strip()
        if not clause:
            continue
        if _consumed_sync_clause(active, clause):
            continue
        from app.services.utterance_intent_classifier import _is_plan_draft_request
        if _is_plan_draft_request(clause) and not _has_read_clause(clause):
            # A separate answer-generation task supplies no read scope. The
            # original write/owner gates remain authoritative on the full turn.
            continue
        explicit = bool(_has_read_clause(clause) or _RESTRICTION_PREFIX.search(clause)
                        or _RETROSPECTIVE_SCOPE.search(clause))
        domain_request = bool(
            re.search(r"结合|包括|针对|基于|分析|复盘|总结", clause)
            and re.search(domain_words, clause)
        )
        if explicit or domain_request:
            parts.append((clause, False))
            listing = domain_request
        elif listing and nominal_list.fullmatch(clause):
            parts.append((clause, False))
        elif (_ANALYSIS_GOAL_RE.fullmatch(clause) or _METHOD_CLAUSE_RE.fullmatch(clause)
              or _diagnosis_context_goal(clause)):
            parts.append((clause, False))
            listing = False
        elif _complete_read_background(clause):
            listing = False
        else:
            # Unknown nominal fragments are restrictions, not ignorable
            # context. A failed full consumption cannot become default 7 days.
            parts.append((clause, True))
            listing = False
    return parts


def _consume_read_scope(snapshot, scope: str, domains: set[str]) -> bool:
    """Consume a complete date/recent/domain expression, never a date substring."""
    deep_read = bool(re.search(r"分析|复盘|总结|建议|状况", snapshot.envelope.text))
    residue = (_CONTEXT_DOMAIN_SCOPE if deep_read else _DOMAIN_SCOPE).sub("", scope)
    residue = re.sub(r"(?:我|本人|自己)?的|记录|数据|\s", "", residue)
    if not deep_read:
        from app.services.agent_kernel.capability_policy import _query_window_days
        legacy = _legacy_scope_residue(scope)
        if legacy is not None and (not legacy or _query_window_days(legacy) is not None):
            return True
    recent = _RECENT.fullmatch(residue)
    if recent is not None:
        days = _number(recent[1]) * (7 if recent[2] == "周" else 1)
        return 1 <= days <= 31
    if residue in {"", "近期", "最近"}:
        return bool(domains)
    calendar_remainder = _WEEK_RE.sub("", _WEEKDAY_RE.sub("", _RELATIVE_RE.sub("", _DATE_RE.sub("", residue))))
    night = bool(re.search(r"昨晚|昨夜", residue))
    if calendar_remainder not in {"", "到", "至", "~", "～"}:
        # Only the existing sleep calendar adapter represents this qualifier:
        # sleep belongs to its wake date. Diet night reads need a meal binder.
        if domains != {"sleep"} or not re.fullmatch(r"(?:晚上|夜晚|晚间|夜间|晚|夜)", calendar_remainder):
            return False
    if night and domains != {"sleep"}:
        return False
    return resolve_calendar_query_window(
        residue, snapshot.context.current_time,
        "sleep" if domains == {"sleep"} else "diet",
        timezone_name=snapshot.context.timezone,
    ) is not None


def _query_object_scope(clause: str) -> str:
    """Return the entire query object; every leftover modifier needs binding.

    This deliberately has no temporal keyword trigger. Object-internal,
    parenthesized and postposed filters remain part of the object, including
    qualifiers after a word such as records or an analysis verb.
    """
    scope = re.sub(r"(?:并|再|然后)(?:请)?" + _ANALYSIS_GOAL + r"$", "", clause)
    scope = _strip_exam_request_scaffolding(scope)
    scope = re.sub(r"^(?:先|再|然后)?(?:分析|复盘|总结|结合|包括|针对|基于)(?:一下)?", "", scope)
    scope = re.sub(r"^(?:我|本人|自己)(?:的)?", "", scope)
    if _RETROSPECTIVE_SCOPE.search(clause):
        scope = re.sub(r"行动|健康情况|健康状态|一天|日程", "", scope)
    return scope


def _restricted_read_text(snapshot, active: str) -> str | None:
    if not _record_domains(active) and not _RETROSPECTIVE_SCOPE.search(active):
        return active
    if re.search(r"[“”「」『』\"'‘’`]", active):
        # An attached quotation is an unresolved object or scope, not empty
        # syntax that can be discarded to manufacture default read authority.
        return None
    # These checks still run in the original policy. The read projection must
    # neither replace their owner error nor reinterpret an observation as a task.
    if (not has_positive_health_read_verb(active) and not _TOOL_READ.search(active)
            and not re.search(r"分析|复盘|总结|建议|状况", active)
            and not _RESTRICTION_PREFIX.search(active)):
        return active
    from app.services.agent_kernel.capability_policy import (
        project_diet_manage_list_to_turn, _query_text_known_dimension, _FULL_DAY_DIET_QUERY_RE,
    )
    diet = project_diet_manage_list_to_turn(snapshot)
    if diet is not None and not diet.get("meal_type") and _FULL_DAY_DIET_QUERY_RE.search(active):
        return active
    known = _query_text_known_dimension(active)
    if known is not None and known not in _DOMAINS:
        actual_read = _health_read_entity_expression(active)
        if not _record_domains(actual_read):
            return active
    if _legacy_comparison_scope(active):
        return active
    from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan
    if resolve_daily_read_plan(active, snapshot.context.current_time, timezone_name=snapshot.context.timezone) is not None:
        return active
    clauses = _read_projection_parts(active)
    projected = "。".join(clause for clause, _ in clauses)
    requested_domains = _record_domains(projected)
    if not requested_domains and _RETROSPECTIVE_SCOPE.search(projected):
        requested_domains = {"diet", "sleep"}
    normalized = []
    domain_limits = []
    for clause, is_scope in clauses:
        marker = _RESTRICTION_PREFIX.search(clause)
        if marker is None and re.search(r"只|仅", clause):
            # Unknown restrictive grammar must survive command scaffolding.
            # It is not permission to keep an earlier broader domain/window.
            return None
        if marker:
            body = clause[marker.end():].strip()
            scope = re.sub(r"(?:并|再|然后)(?:分析|复盘|总结)(?:一下)?$", "", body)
            domains = _record_domains(scope)
            if domains:
                domain_limits.append(domains)
            if not _consume_read_scope(snapshot, scope, domains or requested_domains):
                return None
            lead = clause[:marker.start()].strip()
            if lead:
                lead_scope = _strip_exam_request_scaffolding(lead)
                if lead_scope not in {"", "你", "您"} and not re.fullmatch(r"(?:查询|读取|时间|日期|数据)?范围", lead_scope):
                    return None
                normalized.append(lead)
            normalized.append(body)
            continue
        if is_scope:
            if not _consume_read_scope(snapshot, clause, requested_domains):
                return None
        else:
            # Domain-free method/advice clauses are auxiliary only when their
            # complete grammar is recognized, never from a keyword hit.
            if (_ANALYSIS_GOAL_RE.fullmatch(clause) or _METHOD_CLAUSE_RE.fullmatch(clause)
                    or _diagnosis_context_goal(clause)):
                normalized.append(clause)
                continue
            temporal = _query_object_scope(clause)
            if temporal is not None:
                exact_question = resolve_daily_read_plan(
                    _strip_exam_request_scaffolding(clause), snapshot.context.current_time,
                    timezone_name=snapshot.context.timezone,
                )
                if exact_question is None and not _consume_read_scope(snapshot, temporal, requested_domains):
                    return None
        normalized.append(clause)
    if any(not requested_domains <= limit for limit in domain_limits):
        return None
    return "。".join(normalized)


def project_active_quote_roles(active: str) -> str | None:
    """Preserve quote positions; only independent reported material is context.

    Inline quoted owners/objects/filters stay intact for complete consumption.
    The shared material scanner keeps punctuation inside quotes from creating
    new active clauses. Quoted bodies never become executable instructions.
    """
    pairs = {**ANALYZED_MATERIAL_QUOTE_PAIRS, "'": "'", "`": "`"}
    if not any(char in active for char in pairs):
        return active
    clauses = []
    raw = []
    outside = []
    quoted = False
    had_quote = False

    def finish_clause(separator=""):
        nonlocal raw, outside, quoted
        body = "".join(raw).strip()
        shape = "".join(outside).strip()
        independent = quoted and re.fullmatch(
            r"(?:(?:有人|医生|他|她)(?:说|提到|表示)[:：]?)?"
            r"\ufffc(?:(?:以及|和|与|、)\ufffc)*", shape,
        )
        if body and not independent:
            clauses.append(body + separator)
        raw, outside, quoted = [], [], False

    index = 0
    while index < len(active):
        char = active[index]
        # Apostrophes inside a Latin name are not quoted material delimiters.
        apostrophe = char == "'" and index > 0 and index + 1 < len(active) and (
            active[index - 1].isascii() and active[index - 1].isalpha()
            and active[index + 1].isascii() and active[index + 1].isalpha()
        )
        if char in pairs and not apostrophe:
            if char in ANALYZED_MATERIAL_QUOTE_PAIRS:
                end = _analyzed_material_end(active, index)
            else:
                match = re.search(r"(?<!\\)" + re.escape(char), active[index + 1:])
                end = index + 2 + match.start() if match else len(active)
            if end <= index + 1 or active[end - 1] != pairs[char]:
                return None
            raw.append(active[index:end])
            outside.append("\ufffc")
            quoted = had_quote = True
            index = end
            continue
        if char in "，,。；;！？!?\n":
            finish_clause(char)
        else:
            raw.append(char)
            outside.append(char)
        index += 1
    finish_clause()
    projected = "".join(clauses).strip()
    return None if had_quote and not projected else projected


def longitudinal_read_projection_text(snapshot, *, text_override: str | None = None) -> str | None:
    """Server-only read projection; callers must retain original authority checks.

    text_override is an already narrowed server input (e.g. removed plan clauses),
    never model-authored authority. None means unsupported scope, not no request.
    """
    source_text = snapshot.envelope.text if text_override is None else text_override
    from app.services.agent_kernel.health_semantics import active_health_read_authority_text

    # The role projector intentionally drops independent quoted material, but
    # an inline material span attached to the requested owner/object must first
    # fail the stricter read-authority boundary instead of becoming empty syntax.
    if not active_health_read_authority_text(source_text):
        return None
    active = active_health_instruction_text(source_text)
    active = project_active_quote_roles(active)
    if active is None:
        return None
    return _restricted_read_text(snapshot, active)


def longitudinal_read_restrictions_unresolved(snapshot) -> bool:
    """The same projection gates both rolling and calendar fallback consumers."""
    return longitudinal_read_projection_text(snapshot) is None


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
    active = project_active_quote_roles(active)
    if active is None:
        return None
    if (
        re.search(r"""[“”「」『』"'‘’`]""", active)
        or _NEGATIVE.search(active)
        or _MUTATION.search(active)
    ):
        return None
    # A direct analysis of an explicitly bounded recent record window also
    # requests a read (e.g. 分析最近一周的睡眠血氧). Keep the historical
    # explicit-owner/tool requirements for other longitudinal speech acts.
    from app.services.agent_kernel.read_task_scope import _owned_active
    bounded_analysis = bool(
        _owned_active(active)
        and any(
            re.match(r"^(?:请)?(?:分析|复盘|总结)(?:一下)?", clause.strip())
            and _RECENT.search(clause)
            and _record_domains(clause)
            for clause in re.split(r"[，,。；;！？!?\n]", active)
        )
    )
    if (not re.search(r"我|本人", active) and not bounded_analysis) or re.search(
        r"朋友|他人|别人|同事|家人|妈妈|爸爸|父亲|母亲|妻子|丈夫|孩子|他们|她们|他的|她的",
        active,
    ):
        return None
    active = longitudinal_read_projection_text(snapshot)
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
    if not _TOOL_READ.search(active) and not bounded_analysis:
        return None
    request = active
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
    if dimension in {"diet", "sleep", "spo2"}:
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
