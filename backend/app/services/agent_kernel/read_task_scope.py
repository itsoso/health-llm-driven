"""Composable owned read scope; never grants writes or model-authored dates.

Speech-act and subject checks are separate from domain/time projection. The
model chooses subqueries inside this scope; tool adapters use the same binder.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from zoneinfo import ZoneInfo

from app.services.agent_kernel.health_semantics import (
    active_health_instruction_text,
    health_read_has_nonself_subject,
    health_read_cancelled,
    has_positive_health_read_verb,
    normalize_health_authorization_text,
)
from app.services.agent_query_window import resolve_calendar_query_window
from app.services.agent_read_task_continuation import resolve_read_task_continuation
from app.services.write_intent_scope import _TRAILING_REVOCATION_CLAUSE_RE

_READ = re.compile(
    r"查询|查看|看一下|看看|获取|分析|复盘|总结|怎么样|怎样|如何|什么|啥"
)
_NON_AUTHORIZING = re.compile(
    r"假如|假设|假想|如果|举例|例句|我在想|不要|不用|无需|别|不(?:再|分析|复盘|总结|查询|查看|同步|刷新|拉取)|取消|停止"
)
_NONSELF = re.compile(
    r"别人|他人|其他人|朋友|同事|妈妈|爸爸|母亲|父亲|家人|妻子|丈夫|女儿|儿子|她的|他的|他们|她们"
)
_MUTATION = re.compile(
    r"删除|撤销|写入|保存|记下来|添加|加入|列入|记录(?:一下|体重|血压|饮水|饮食|睡眠)|修改|更新|执行计划"
)
_DOMAINS = {
    "sleep": re.compile(r"睡眠|睡得|睡的|睡觉"),
    "diet": re.compile(r"饮食|餐食|早餐|午餐|晚餐|吃了(?:什么|啥)|吃过(?:什么|啥)"),
}
_RETROSPECTIVE = re.compile(r"(?:分析|复盘|总结).*(?:行动|健康情况|健康状态|一天|日程)")
_SYNC_TARGET_TIME = re.compile(
    r"昨天|昨日|昨晚|昨夜|前天|今天|今日|明天|后天|最近|过去|历史|"
    r"上周|本周|这周|下周|上个月|本月|去年|今年|\d{4}[-/年]|"
    r"[0-9一二两三四五六七八九十]+\s*(?:天|日|周|月|年)"
)


def _active(text: str) -> str | None:
    # Reuse the pure quote-role projection rather than deleting operands. The
    # full read-scope projector calls this sync binder, so it is not used here.
    from app.services.agent_longitudinal_read import project_active_quote_roles

    active = project_active_quote_roles(active_health_instruction_text(text))
    if active is None:
        return None
    return normalize_health_authorization_text(active).strip()


def _owned_active(text: str | None) -> bool:
    if (
        not text
        or _NON_AUTHORIZING.search(text)
        or _NONSELF.search(text)
        or re.search(r"""[“”「」『』"'‘’`]""", text)
    ):
        return False
    for clause in re.split(r"[，,。；;！？!?\n]|然后", text):
        device = re.search(r"garmin|佳明", clause, re.I)
        if device:
            # Device ownership is checked on its subject span, not by the
            # illness-name parser (which mistakes 佳明 for a person's name).
            prefix = clause[: device.start()]
            residue = re.sub(
                r"请你|麻烦|帮我|给我|获取|同步|刷新|拉取|一下|我的|主动|触发|请|把|我|的|先|再|\s",
                "",
                prefix,
            )
            if residue:
                return False
            # The device is not an owner. Inspect the suffix too, projecting
            # its generic data noun into a health target for the shared parser.
            suffix = re.sub(r"^(?:里|中|上)(?:的)?", "", clause[device.end() :].strip())
            if health_read_has_nonself_subject("查询" + suffix.replace("数据", "睡眠")):
                return False
            continue
        subject_text = re.sub(
            r"^(?:先|再|然后|接着)?(?:分析|复盘|总结)", "查询", clause.strip()
        )
        # Generic retrospective targets are not clinical entities, but their
        # owner must satisfy the same shared check as an explicit sleep read.
        subject_text = re.sub(r"行动|健康情况|健康状态|一天|日程", "睡眠", subject_text)
        if subject_text and health_read_has_nonself_subject(subject_text):
            return False
    return True


def _complete_sync_clause(clause: str, has_target: bool) -> tuple[bool, bool] | None:
    """Normalize only complete known aliases, then use the existing binder."""
    from app.services.agent_kernel.capability_policy import _explicit_owned_garmin_sync

    clause = re.sub(r"^(?:先|再|然后)", "", clause)
    if _explicit_owned_garmin_sync(clause):
        return True, True
    # These are the already supported prefix/postfix spoken action forms.
    # Every character belongs to the command; modifiers are never removed.
    polite = r"(?:请你?|麻烦)?(?:帮我|给我)?"
    owned = r"(?:我的?)?(?:garmin|佳明)(?:的)?(?:数据)?"
    prefix = re.fullmatch(
        rf"{polite}(?:同步|刷新|拉取)(?:一下)?(?P<target>{owned})", clause, re.I,
    )
    postfix = re.fullmatch(
        rf"{polite}(?:把)?(?P<target>{owned})(?:同步|刷新|拉取)(?:一下)?", clause, re.I,
    )
    alias = prefix or postfix
    if alias:
        target = alias['target']
        if not target.endswith("数据"):
            target += "数据"
        if _explicit_owned_garmin_sync("同步" + target):
            return True, True
    if _explicit_owned_garmin_sync(clause + "，同步一下"):
        return True, False  # A target declaration alone does not enqueue.
    if has_target and _explicit_owned_garmin_sync("获取佳明数据，" + clause):
        return True, True
    return None


def _independent_sync_read_clause(clause: str) -> bool:
    """Recognize complete ancillary read roles without the recursive projector.

    This establishes only that the clause is independent of the sync target.
    The actual read still binds its dates and owner through its normal policy.
    """
    from app.services.agent_kernel.daily_read_plan import _daily_read_frame, _SYNC_STATUS_SUFFIX_RE
    from app.services.agent_kernel.health_semantics import _strip_exam_request_scaffolding
    from app.services.agent_longitudinal_read import (
        _ANALYSIS_GOAL_RE, _DOMAIN_SCOPE, _has_read_clause, _query_object_scope,
        _record_domains, _RECENT,
    )
    from app.services.agent_query_window import _DATE_RE, _RELATIVE_RE, _WEEKDAY_RE

    if _SYNC_STATUS_SUFFIX_RE.fullmatch("，" + clause) or _ANALYSIS_GOAL_RE.fullmatch(clause):
        return True
    core = _strip_exam_request_scaffolding(clause)
    if _daily_read_frame(core) is not None:
        return True
    if not (_has_read_clause(clause) or re.match(r"(?:先|再)?(?:分析|复盘|总结)", clause)):
        return False
    if health_read_cancelled(clause):
        return True  # A cancelled independent read cannot reopen sync authority.
    if not _record_domains(clause):
        return False
    scope = _query_object_scope(clause)
    scope = _DOMAIN_SCOPE.sub("", scope)
    scope = re.sub(r"的|记录|数据|\s", "", scope)
    return bool(
        scope in {"", "近期", "最近"}
        or _RECENT.fullmatch(scope)
        or _DATE_RE.fullmatch(scope)
        or _RELATIVE_RE.fullmatch(scope)
        or _WEEKDAY_RE.fullmatch(scope)
    )


def has_owned_sync_instruction(text: str) -> bool:
    """Consume the whole owned sync act; unknown clauses never grant a job."""
    active = _active(text)
    if active is None or not _owned_active(active) or _MUTATION.search(active):
        return False
    active = re.sub(r"\s+", "", active)
    clauses = re.split(r"[，,。；;！？!?\n]|然后|(?=再(?:分析|看看))", active)
    authorized = False
    has_target = False
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        sync = re.search(r"同步|刷新|拉取", clause)
        if _TRAILING_REVOCATION_CLAUSE_RE.fullmatch(clause) or (
            not has_positive_health_read_verb(clause) and health_read_cancelled(clause)
        ):
            authorized = False
            continue
        if sync is not None and (health_read_cancelled(clause) or any(
            _TRAILING_REVOCATION_CLAUSE_RE.fullmatch(clause[offset:])
            for offset in range(sync.end(), len(clause))
        )):
            authorized = False
            continue
        command = _complete_sync_clause(clause, has_target)
        if command is not None:
            has_target, starts_sync = command
            if starts_sync:
                authorized = True
            continue
        if _independent_sync_read_clause(clause):
            continue
        return False
    return authorized


@dataclass(frozen=True)
class OwnedReadScope:
    queries: tuple[dict[str, str | int], ...]
    limitations: tuple[str, ...] = ()

    def query(self, dimension: str) -> dict[str, str | int] | None:
        return next(
            (dict(q) for q in self.queries if q["dimension"] == dimension), None
        )


def resolve_owned_read_scope(snapshot) -> OwnedReadScope | None:
    """Bind expressed domains to a server-resolved calendar window.

    This supplements the meal-specific/daily-summary binder. Multiple different
    dates or unclear subjects still require clarification; proposal args cannot
    manufacture scope. The longitudinal resolver separately attests bounded
    recent windows and discloses default duration and unsupported coverage.
    """
    continuation = resolve_read_task_continuation(snapshot)
    if continuation is not None:
        if not continuation["queries"]:
            return None
        return OwnedReadScope(
            tuple(dict(query) for query in continuation["queries"]),
            tuple(continuation["limitations"]),
        )
    from app.services.agent_longitudinal_read import (
        resolve_longitudinal_read_queries, longitudinal_read_limitations,
        longitudinal_read_restrictions_unresolved, longitudinal_read_projection_text,
    )
    if longitudinal_read_restrictions_unresolved(snapshot):
        return None
    longitudinal = resolve_longitudinal_read_queries(snapshot)
    if longitudinal is not None:
        return OwnedReadScope(longitudinal, longitudinal_read_limitations(snapshot))
    text = _active(snapshot.envelope.text)
    if text is None or not _owned_active(text) or _MUTATION.search(text) or not _READ.search(text):
        return None
    # Prospective diet/medical advice does not implicitly authorize history.
    if re.search(r"应该|该吃|吃什么药|吃什么补剂|吃了什么药|吃了什么补剂", text):
        return None
    plan_draft = "计划" in text or "草稿" in text
    if plan_draft:
        # A draft's subject/date describe the generated answer, not permission
        # to inspect history. Only an independent explicit read can bind it.
        clauses = re.split(r"[，,。；;！？!?\n]|然后", text)
        text = "，".join(
            clause
            for clause in clauses
            if not re.search(r"计划|草稿", clause) and _READ.search(clause)
        )
    # Parse the same scoped request used by the longitudinal binder. The
    # original owner/cancellation checks and draft exclusion remain above.
    text = longitudinal_read_projection_text(snapshot, text_override=text)
    if text is None:
        return None
    dimensions = tuple(d for d, pattern in _DOMAINS.items() if pattern.search(text))
    broad = bool(_RETROSPECTIVE.search(text)) and not plan_draft
    if not dimensions and broad:
        dimensions = ("diet", "sleep")
    if not dimensions:
        return None
    queries = []
    for dimension in dimensions:
        window = resolve_calendar_query_window(
            text,
            snapshot.context.current_time,
            dimension,
            timezone_name=snapshot.context.timezone,
        )
        if window is None:
            return None
        queries.append({"dimension": dimension, **window})
    return OwnedReadScope(tuple(queries), ("scope_diet_sleep_only",) if broad else ())


def resolve_sync_status_query(snapshot) -> dict[str, str] | None:
    continuation = resolve_read_task_continuation(snapshot)
    if continuation is not None:
        if not continuation["sync_status"]:
            return None
        if continuation.get("sync_window"):
            return {"dimension": "garmin", **continuation["sync_window"]}
        sleep = next(
            (
                query
                for query in continuation["queries"]
                if query["dimension"] == "sleep"
            ),
            None,
        )
        return {**sleep, "dimension": "garmin"} if sleep else None
    text = _active(snapshot.envelope.text)
    if text is None or not _owned_active(text) or _MUTATION.search(text):
        return None
    if not re.search(r"garmin|佳明", text, re.I) or not re.search(
        r"同步|刷新|拉取", text
    ):
        return None
    scope = resolve_owned_read_scope(snapshot)
    sleep = scope.query("sleep") if scope is not None else None
    status_requested = bool(
        re.search(r"完了|完成|完没|状态|成功|有没有|是否|了吗", text)
    )
    if sleep and (
        status_requested or has_owned_sync_instruction(snapshot.envelope.text)
    ):
        return {**sleep, "dimension": "garmin"}
    if not status_requested and not has_owned_sync_instruction(snapshot.envelope.text):
        return None
    # A failed domain/date binding is not permission to substitute today's row.
    if any(pattern.search(text) for pattern in _DOMAINS.values()) or re.search(
        r"天|日|晚|夜|周|月|年|最近|过去|\d", text
    ):
        return None
    now = snapshot.context.current_time
    zone = ZoneInfo(snapshot.context.timezone)
    today = (
        (now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone))
        .date()
        .isoformat()
    )
    return {
        "dimension": "garmin",
        "start_date": today,
        "end_date": today,
        "timezone": snapshot.context.timezone,
    }


def read_task_scope_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest,
        authorization_grammar_digest,
        authorization_module_behavior_names,
    )

    return {
        "version": "read-task-scope-v1",
        "grammar": authorization_grammar_digest(globals()),
        "behavior": authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)
        ),
    }
