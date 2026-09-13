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
    normalize_health_authorization_text,
)
from app.services.agent_query_window import resolve_calendar_query_window
from app.services.agent_read_task_continuation import resolve_read_task_continuation

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


def _active(text: str) -> str:
    active = active_health_instruction_text(text)
    # Quoted examples cannot supply an owner, read act, domain, or date.
    active = re.sub(
        r"""“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"|'[^'\n]*'|‘[^’]*’|`[^`]*`""",
        "",
        active,
    )
    return normalize_health_authorization_text(active).strip()


def _owned_active(text: str) -> bool:
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


def has_owned_sync_instruction(text: str) -> bool:
    """An explicit refresh act is distinct from asking whether a job finished."""
    active = _active(text)
    if not _owned_active(active) or _MUTATION.search(active):
        return False
    if not re.search(r"garmin|佳明", active, re.I):
        return False
    clauses = re.split(r"[，,。；;！？!?\n]|然后|再分析|再看看", active)
    # The enqueue adapter currently supports its fixed current window only.
    # A date on the device target or sync command cannot be silently discarded;
    # a separate read clause keeps its independently bound historical date.
    if any(
        re.search(r"garmin|佳明|同步|刷新|拉取", clause, re.I)
        and _SYNC_TARGET_TIME.search(clause)
        for clause in clauses
    ):
        return False
    for clause in clauses:
        if not re.search(r"同步|刷新|拉取", clause):
            continue
        if re.search(
            r"是否|有没有|了吗|完了|完成|完没|状态|成功|需要|应该|怎么|如何|吗|没|好不好|已经|刚才|昨天|之前",
            clause,
        ):
            continue
        if re.search(r"同步|刷新|拉取", clause):
            return True
    return False


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
    if not _owned_active(text) or _MUTATION.search(text) or not _READ.search(text):
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
    if not _owned_active(text) or _MUTATION.search(text):
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
