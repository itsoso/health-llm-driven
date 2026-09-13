"""Ephemeral completion projection from owner-bound reads, never model prose.

The caller supplies the scope resolved from this authenticated turn and actual
ToolExecutionResults. This module neither authorizes reads nor verifies user
identity; the scoped dispatcher does that. Sync job receipts are not read data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.services.agent_daily_read_execution import _summary_decimal, _summary_display
from app.services.agent_kernel.read_task_scope import OwnedReadScope
from app.services.agent_kernel.types import ToolExecutionResult
from app.services.agent_query_window import parse_query_window
from app.services.agent_write_outcome import result_declares_explicit_failure
from app.services.genui.table_builder import load_tool_result_json
from app.utils.number_format import format_display_number

_LABELS = {"diet": "饮食", "sleep": "睡眠", "workout": "运动", "supplements": "补剂"}
_ACTUAL_SOURCES = {
    "workout": ("owned_actual_workout_records", {"workout_record", "exercise_record"}),
    "supplements": (
        "owned_actual_supplement_intake_logs",
        {"supplement_intake", "supplement_taken_log"},
    ),
}
_TERMINAL = {"success", "completed", "complete", "ok", "succeeded"}


@dataclass(frozen=True)
class ComposedReadCompletion:
    goals: tuple[dict, ...]
    missing_dimensions: tuple[str, ...]
    trusted_fact_summary: str
    complete: bool


def _payload(content):
    return load_tool_result_json(content) if isinstance(content, str) else content


def _terminal(payload: dict) -> bool:
    return not result_declares_explicit_failure(payload) and (
        "status" not in payload
        or (isinstance(payload["status"], str) and payload["status"] in _TERMINAL)
    )


def _validate(bound: dict, payload) -> str | None:
    if not isinstance(payload, dict) or not _terminal(payload):
        return "query_result_unavailable"
    if payload.get("dimension") != bound["dimension"] or payload.get("window") != {
        k: bound[k] for k in ("start_date", "end_date", "timezone")
    }:
        return "query_result_scope_conflict"
    if (
        payload.get("truncated")
        or payload.get("has_more")
        or payload.get("next_cursor")
    ):
        return "query_result_truncated"
    actual_source = _ACTUAL_SOURCES.get(bound["dimension"])
    if actual_source and payload.get("source_scope") != actual_source[0]:
        return "query_result_source_conflict"
    rows = payload.get("records")
    availability = payload.get("availability")
    limitations = payload.get("limitations", [])
    if (
        not isinstance(limitations, list)
        or any(not isinstance(v, str) for v in limitations)
        or not isinstance(rows, list)
        or not isinstance(availability, str)
        or availability not in {"available", "partial", "no_data"}
        or (not rows) != (availability == "no_data")
    ):
        return "query_result_unavailable"
    for row in rows:
        if not isinstance(row, dict):
            return "query_result_unavailable"
        if actual_source and (
            not isinstance(row.get("record_kind"), str)
            or row["record_kind"] not in actual_source[1]
        ):
            return "query_result_source_conflict"
        if bound["dimension"] == "supplements" and row.get("taken") is not True:
            return "query_result_source_conflict"
        try:
            day = date.fromisoformat(str(row.get("record_date"))).isoformat()
        except ValueError:
            return "query_result_scope_conflict"
        if not bound["start_date"] <= day <= bound["end_date"]:
            return "query_result_scope_conflict"
    return None


def _facts(dimension: str, payload: dict) -> str:
    """Reuse the daily summary's finite numeric projection, omit raw text fields."""
    label, rows = _LABELS[dimension], payload["records"]
    if not rows:
        absence = {
            "diet": "，不代表没有进食。",
            "sleep": "，不能据此判断睡眠情况。",
            "workout": "，不能据此断定没有运动。",
            "supplements": "，不能据此断定没有服用补剂。",
        }
        return f"{label}：目标日期没有可用记录" + absence[dimension]
    count = format_display_number(len(rows))
    if dimension == "diet":
        text = f"饮食：已记录{count}条。"
        known = [
            v
            for row in rows
            if (v := _summary_decimal(row.get("calories"))) is not None
        ]
        total = _summary_display(sum(known, Decimal(0))) if known else None
        if total is None:
            text += "缺少可汇总的有效热量读数，无法给出已记录热量合计。"
        elif len(known) == len(rows):
            text += f"已记录热量合计{total}千卡。"
        else:
            text += (
                f"已知热量小计{total}千卡；另{format_display_number(len(rows) - len(known))}"
                "条缺少有效热量读数，无法给出完整合计。"
            )
    elif dimension == "supplements":
        text = f"补剂：实际服用记录{count}条；定义、计划与当前启停状态不代表实际摄入。"
    elif dimension == "workout":
        text = f"运动：已记录{count}条。"
        known = [
            v
            for row in rows
            if (v := _summary_decimal(row.get("duration_seconds"))) is not None
        ]
        minutes = (
            _summary_display(sum(known, Decimal(0)) / Decimal(60)) if known else None
        )
        if minutes is None:
            text += "缺少可汇总的有效时长读数，无法给出已记录运动时长合计。"
        elif len(known) == len(rows):
            text += f"已记录运动时长合计{minutes}分钟。"
        else:
            text += (
                f"已知运动时长小计{minutes}分钟；另"
                f"{format_display_number(len(rows) - len(known))}条缺少有效时长，"
                "无法给出完整合计。"
            )
        text += "已记录运动不代表全部活动。"
    elif len(rows) != 1:
        text = f"睡眠：查询到{count}条记录，未合并为单一读数，请查看明细。"
    else:
        duration = _summary_decimal(rows[0].get("total_sleep_duration"))
        score = _summary_decimal(rows[0].get("sleep_score"))
        hours = (
            _summary_display(duration / Decimal(60)) if duration is not None else None
        )
        points = _summary_display(score) if score is not None else None
        text = "睡眠：" + (
            f"时长{hours}小时" if hours is not None else "时长缺少有效读数"
        )
        text += (
            "；"
            + (f"评分{points}" if points is not None else "评分缺少有效读数")
            + "。"
        )
    if payload["availability"] == "partial":
        text += "部分日期或指标缺失，不能视为完整数据。"
    if dimension == "sleep":
        text += "按醒来日期归属；每日记录不能证明完整睡眠区间。"
        if "sync_status_unknown" in (payload.get("limitations") or []):
            text += "同步状态未知。"
    return text


def read_scope_synthesis_instructions(scope) -> str:
    if not any("days" in query for query in scope.queries):
        return ""
    return (
        "\n[实际记录分析的证据边界]\n"
        "回答先给能由本轮记录支持的结论，再按已查领域各用一两句说明，最后给最多三条下一步。"
        "普通复盘控制在800字以内；用户明确要求详细报告时才展开。"
        "短续问只补充新的结论和依据，不重写上一轮报告、不反复展开同一批数值。"
        "未要求日程时不生成分时段行动表；先把当前问题完整回答，再结束。"
        "先区分实际查到的记录、未知项目与一般建议。病史时间是用户背景，"
        "不能据此断言已经痊愈、仍在患病或当前恢复程度。"
        "记录热量和时长只能称为已记录合计，不能当作全天实际摄入或全部活动。"
        "不同来源内容相似不证明是同一次事件；无共同事件标识，不得自行去重或构造实际时长上下界。"
        "数值相同不能证明是模板、占位或未称量；缺少记录不能推出没有做，更不能据此要求补吃一餐。"
        "餐次名称和当前时刻不证明该餐未发生，也不证明误录或预录。"
        "指标缺失只能说明未覆盖，不能推出恢复差、营养不足或据此制定训练禁令。"
        "没有本轮可核验的医嘱，不新增补剂、剂量、服用时点或治疗方案。"
        "个人目标必须有明确来源，不虚构目标。情绪和工作未查询是本次读取能力未覆盖，"
        "不要声称用户未授权，更不要承诺尚未提供的读取能力。"
        "给出与现有记录相称的一般健康管理建议；不足以作个体判断时，说明还缺哪项证据。"
    )


def read_scope_notices(scope) -> tuple[str, ...]:
    """One disclosure source for the prompt, final answer, and trusted facts."""
    lines = []
    if "scope_diet_sleep_only" in scope.limitations:
        lines.append("本次复盘仅覆盖饮食与睡眠记录；活动等其他健康领域未覆盖。")
    if "default_recent_7_days" in scope.limitations:
        lines.append(
            "未指定复盘范围，本次默认查询最近7天；背景中提到的日期不作为查询起点。"
        )
    if (
        "mood_not_queried" in scope.limitations
        or "unsupported_mood_work_context" in scope.limitations
    ):
        lines.append("情绪背景未查询结构化记录，不能据此判断情绪趋势或归因。")
    if (
        "work_not_queried" in scope.limitations
        or "unsupported_mood_work_context" in scope.limitations
    ):
        lines.append("工作背景未查询结构化记录，不能据此判断工作状态或归因。")
    return tuple(lines)


def evaluate_composed_read_completion(
    scope: OwnedReadScope,
    executions: Iterable[ToolExecutionResult],
) -> ComposedReadCompletion:
    """Attest each domain independently; a real matching retry can recover it.

    Only exact canonical health_query arguments or a batch of those arguments
    are admitted. Batch items match by dimension, never position. Keep an
    already verified read when an unrelated/later failed attempt is observed.
    """
    bounds = {}
    for query in scope.queries:
        dimension = query.get("dimension")
        try:
            parsed_window = parse_query_window(query)
            window = parsed_window.as_dict()
        except (ValueError, TypeError) as exc:
            raise ValueError("composed_read_scope_invalid") from exc
        canonical = {"dimension": dimension, **window}
        if "days" in query:
            days = query["days"]
            if (
                type(days) is not int
                or days != (parsed_window.end_date - parsed_window.start_date).days + 1
            ):
                raise ValueError("composed_read_scope_invalid")
            canonical["days"] = days
        if dimension not in _LABELS or dimension in bounds or query != canonical:
            raise ValueError("composed_read_scope_invalid")
        bounds[dimension] = dict(query)
    if not bounds:
        raise ValueError("composed_read_scope_invalid")
    goals = {
        d: {
            "goal_id": d,
            "kind": "query",
            "status": "failed",
            "evidence_kind": "",
            "reason_code": "query_not_executed",
            "query": dict(bounds[d]),
        }
        for d in bounds
    }
    verified = {}
    for execution in executions:
        decision = execution.decision
        if decision is None or decision.action != "allow":
            continue
        name, args = decision.normalized_tool_name, decision.normalized_args
        if name != execution.tool_name or not isinstance(args, dict):
            continue
        content = _payload(execution.content)
        if name == "health_query":
            candidates = [(args, content)]
        elif name == "health_query_batch":
            if (
                set(args) != {"queries"}
                or not isinstance(args["queries"], list)
                or not isinstance(content, dict)
                or not _terminal(content)
                or content.get("status") not in _TERMINAL
                or not isinstance(content.get("results"), list)
            ):
                continue
            queries, results = args["queries"], content["results"]
            if any(not isinstance(q, dict) for q in queries) or len(
                {q.get("dimension") for q in queries}
            ) != len(queries):
                continue
            candidates = []
            for query in queries:
                matches = [
                    r
                    for r in results
                    if isinstance(r, dict)
                    and r.get("dimension") == query.get("dimension")
                ]
                candidates.append((query, matches[0] if len(matches) == 1 else None))
        else:
            continue
        for query, payload in candidates:
            dimension = query.get("dimension")
            if (
                dimension not in bounds
                or query != bounds[dimension]
                or ("days" in query and type(query["days"]) is not int)
            ):
                continue
            reason = _validate(bounds[dimension], payload)
            if reason is None:
                verified[dimension] = payload
                goals[dimension] = {
                    "goal_id": dimension,
                    "kind": "query",
                    "status": "verified",
                    "evidence_kind": "read_result",
                    "reason_code": "query_verified",
                    "availability": payload["availability"],
                    "query": dict(bounds[dimension]),
                }
            elif dimension not in verified:
                goals[dimension]["reason_code"] = reason
    missing = tuple(d for d in bounds if d not in verified)
    lines = list(read_scope_notices(scope))
    if "diet" in bounds:
        lines.append("已记录饮食不代表全天完整摄入，未记录不等于没有发生。")
    for dimension, query in bounds.items():
        day = (
            query["start_date"]
            if query["start_date"] == query["end_date"]
            else f"{query['start_date']}至{query['end_date']}"
        )
        lines.append(f"查询范围：{_LABELS[dimension]}，{day}，{query['timezone']}。")
        lines.append(
            _facts(dimension, verified[dimension])
            if dimension in verified
            else f"{_LABELS[dimension]}：本轮查询未完成，暂不汇总。"
        )
    return ComposedReadCompletion(
        tuple(goals.values()), missing, "\n\n".join(lines), not missing
    )
