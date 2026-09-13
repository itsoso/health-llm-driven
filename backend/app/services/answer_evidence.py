"""Deterministic, client-safe explanation of evidence used in one answer.

The compiler accepts only current-turn structured tool results or evidence already
selected by the Health Evidence runtime. It never reads model prose, prompts, or
arbitrary nested health payloads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import json
from typing import Any

from app.services.genui.table_builder import build_table_from_tool_call
from app.services.agent_query_window import DEFAULT_TIMEZONE
from app.services.agent_write_outcome import result_declares_explicit_failure
from app.utils.number_format import format_display_number


VERSION = "answer-evidence.v1"
MAX_BASIS_ITEMS = 4
MAX_LIMITATIONS = 3

_TOP_LEVEL_KEYS = frozenset({"version", "summary", "basis", "limitations"})
_BASIS_KEYS = frozenset({
    "id",
    "label",
    "observation",
    "context",
    "source",
    "purpose",
    "observed_at",
    "freshness",
    "confidence",
})
_LIMITATION_KEYS = frozenset({"id", "title", "detail", "handling"})
_FRESHNESS = frozenset({"current", "recent", "stale", "unknown"})
_CONFIDENCE = frozenset({"high", "medium", "low", "unknown"})

_DIMENSION_LABELS = {
    "activity": "步数",
    "steps": "步数",
    "heart_rate": "静息心率",
    "hrv": "HRV",
    "sleep": "睡眠",
    "body_battery": "身体电量",
    "stress": "压力",
    "spo2": "血氧",
    "weight": "体重",
    "blood_pressure": "血压",
    "water": "饮水",
    "diet": "饮食",
    "workout": "运动",
    "supplements": "补剂",
    "medication": "用药",
    "medical_exam": "化验",
    "wearable": "可穿戴数据",
    "lab": "化验",
    "genetic": "基因",
    "symptom": "症状",
}

_SOURCE_LABELS = {
    "garmin": "Garmin",
    "garmin-app": "Garmin",
    "apple-watch": "Apple Watch",
    "oura": "Oura",
    "ringconn": "RingConn",
    "manual": "手动记录",
    "health_query": "健康数据查询",
    "health_query_batch": "健康数据查询",
    "health_manage": "健康数据查询",
    "query_lab_indicators": "化验指标查询",
}


def _text(value: Any, *, limit: int = 180) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return None
    return normalized[:limit]


def _rendered_scalar_text(value: Any, *, limit: int) -> str | None:
    """Accept display text only when it cannot be a serialized container.

    Existing GenUI builders predate this projection and normalize every cell to
    ``str``.  Reject Python/JSON container markers here so a nested tool payload
    can never be mistaken for one user-facing scalar observation.
    """

    rendered = _text(value, limit=limit)
    if rendered is None:
        return None
    if rendered.startswith(("(", "[", "{")):
        return None
    if any(marker in rendered for marker in ("[", "]", "{", "}")):
        return None
    return rendered


def _scalar_observation(value: Any, unit: Any = None) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    if isinstance(value, (int, float)):
        rendered = format_display_number(value)
    else:
        rendered = _text(value, limit=80)
    if rendered is None or str(rendered).strip() == "":
        return None
    unit_text = _text(unit, limit=20)
    return f"{rendered} {unit_text}".strip() if unit_text else str(rendered)


def _purpose(label: str, category: str = "") -> str:
    normalized = f"{label} {category}".lower()
    if "hrv" in normalized:
        return (
            "用于评估恢复与活动承受度"
            if category
            else "用于评估恢复趋势"
        )
    if "训练准备" in normalized or "身体电量" in normalized:
        return "用于评估恢复与活动承受度"
    if "睡眠" in normalized or category == "sleep":
        return "用于评估睡眠与恢复状态"
    if "静息心率" in normalized or "heart_rate" in normalized:
        return "用于评估心率与恢复状态"
    if "血压" in normalized or "血氧" in normalized or "spo2" in normalized:
        return "用于核对当前生命体征"
    if "饮食" in normalized or "热量" in normalized or "蛋白" in normalized:
        return "用于核对本次饮食与营养摄入"
    if "化验" in normalized or category == "lab":
        return "用于核对近期化验信息"
    if "用药" in normalized or "补剂" in normalized:
        return "用于核对当前用药与补剂上下文"
    return "用于回答本轮问题"


def _table_rows(
    *,
    tool_index: int,
    tool_name: str,
    block: Mapping[str, Any],
) -> list[dict[str, str]]:
    title = _rendered_scalar_text(block.get("title"), limit=40) or "数据"
    columns = block.get("columns")
    rows = block.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    column_labels = {
        str(column.get("key") or ""): str(column.get("label") or "")
        for column in columns
        if isinstance(column, Mapping)
    }
    output: list[dict[str, str]] = []
    for row_index, raw_row in enumerate(rows, start=1):
        if not isinstance(raw_row, Mapping):
            continue
        context = None
        if _rendered_scalar_text(raw_row.get("metric"), limit=60):
            label = _rendered_scalar_text(raw_row.get("metric"), limit=60) or title
            observation = _rendered_scalar_text(raw_row.get("value"), limit=100)
            context = _rendered_scalar_text(raw_row.get("note"), limit=140)
        elif _rendered_scalar_text(raw_row.get("item"), limit=60):
            label = _rendered_scalar_text(raw_row.get("item"), limit=60) or title
            observation = _rendered_scalar_text(raw_row.get("value"), limit=100)
        else:
            date_value = _rendered_scalar_text(raw_row.get("date"), limit=40)
            label_base = title[:-2] if title.endswith("记录") else title
            label = f"{label_base} · {date_value}" if date_value else label_base
            observation_parts: list[str] = []
            unsafe_row = False
            for key, value in raw_row.items():
                if key == "date":
                    continue
                rendered = _rendered_scalar_text(value, limit=80)
                if _text(value, limit=80) and rendered is None:
                    unsafe_row = True
                    break
                if rendered:
                    observation_parts.append(
                        f"{column_labels.get(str(key), str(key))} {rendered}".strip()
                    )
            if unsafe_row:
                continue
            observation = " · ".join(observation_parts) or None
        if not observation:
            continue
        item = {
            "id": f"tool-{tool_index}-row-{row_index}",
            "label": label,
            "observation": observation,
            "source": _SOURCE_LABELS.get(tool_name, "本轮数据查询"),
            "purpose": _purpose(label),
        }
        if context:
            item["context"] = context
        output.append(item)
    return output


def _tool_limitation(
    *,
    tool_index: int,
    tool_name: str,
    args: Mapping[str, Any],
    result: Any,
) -> dict[str, str] | None:
    result_text = str(result or "").strip()
    payload: Any = None
    try:
        payload = json.loads(result_text)
    except (TypeError, ValueError):
        payload = None
    dimension = str(args.get("dimension") or "").strip().lower()
    label = _DIMENSION_LABELS.get(dimension, "健康")
    detail = None
    if result_text.startswith("Error"):
        detail = "本轮数据查询失败"
    elif isinstance(payload, Mapping):
        status = str(payload.get("status") or "").strip().lower()
        if tool_name == "health_query" and "window" in payload:
            from datetime import date
            from app.services.agent_query_window import parse_query_window

            try:
                window = parse_query_window(payload.get("window") or {})
                records = payload.get("records")
                if not isinstance(records, list) or payload.get("dimension") != dimension:
                    raise ValueError("calendar_result_invalid")
                for row in records:
                    if not isinstance(row, Mapping):
                        raise ValueError("calendar_row_invalid")
                    day = date.fromisoformat(str(row.get("record_date")))
                    if not window.start_date <= day <= window.end_date:
                        raise ValueError("calendar_row_outside_window")
            except ValueError:
                detail = "返回记录的目标日期或领域无法核验，未将其作为本轮依据"
            else:
                notes = []
                availability = payload.get("availability")
                if availability == "no_data":
                    notes.append("目标日期没有可用记录，未使用旧数据替代")
                elif availability == "partial":
                    notes.append("部分目标记录或指标缺失，缺失不代表异常")
                elif availability != "available":
                    notes.append("目标数据可用性无法核验")
                # Only fixed reason codes become client text; arbitrary metadata
                # and nested health payloads never enter the evidence whitelist.
                codes = payload.get("limitations")
                if isinstance(codes, list):
                    if "sync_status_unknown" in codes:
                        notes.append("设备同步状态未知")
                    if "daily_rows_not_full_episode_timestamps" in codes:
                        notes.append("日记录不能证明完整睡眠事件")
                if len(records) > MAX_BASIS_ITEMS:
                    notes.append("部分记录未在依据面板展开")
                if notes:
                    detail = f"{window.start_date.isoformat()} 至 {window.end_date.isoformat()}（{window.timezone}）：" + "；".join(notes)
        elif status in {"no_data", "empty", "unavailable", "failed", "error"}:
            detail = _text(payload.get("message"), limit=160) or "本轮没有可用数据"
        elif tool_name == "health_query_batch":
            queries = payload.get("queries")
            if isinstance(queries, list):
                failed = [
                    query for query in queries
                    if isinstance(query, Mapping)
                    and query.get("value") is None
                    and (query.get("error") or query.get("note"))
                ]
                if failed:
                    first = failed[0]
                    failed_dimension = str(first.get("dimension") or "").strip().lower()
                    label = _DIMENSION_LABELS.get(failed_dimension, label)
                    detail = _text(first.get("error") or first.get("note"), limit=160)
    if not detail:
        return None
    return {
        "id": f"tool-{tool_index}-limitation",
        "title": f"{label}数据不足",
        "detail": detail,
        "handling": "未将缺失数据推断为正常；本次回答采用保守表达",
    }


def _packet_basis(personal_packet: Any) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for item in getattr(personal_packet, "evidence", ()):
        observation = _scalar_observation(
            getattr(item, "value", None),
            getattr(item, "unit", None),
        )
        if not observation:
            continue
        label = _text(getattr(item, "label", None), limit=60)
        evidence_id = _text(getattr(item, "evidence_id", None), limit=100)
        if not label or not evidence_id:
            continue
        category = str(getattr(item, "category", "") or "").strip().lower()
        source_kind = str(getattr(item, "source_kind", "") or "").strip().lower()
        basis = {
            "id": evidence_id,
            "label": label,
            "observation": observation,
            "source": _SOURCE_LABELS.get(source_kind, source_kind or "个人健康记录"),
            "purpose": _purpose(label, category),
        }
        observed_at = _text(getattr(item, "observed_at", None), limit=80)
        freshness = str(getattr(item, "freshness", "") or "").strip().lower()
        confidence = str(getattr(item, "reliability", "") or "").strip().lower()
        if observed_at:
            basis["observed_at"] = observed_at
        if freshness in _FRESHNESS:
            basis["freshness"] = freshness
        if confidence in _CONFIDENCE:
            basis["confidence"] = confidence
        output.append(basis)
        if len(output) >= MAX_BASIS_ITEMS:
            break
    return output


def _packet_limitations(personal_packet: Any) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []

    for item in getattr(personal_packet, "evidence", ()):
        freshness = str(getattr(item, "freshness", "") or "").strip().lower()
        reliability = str(getattr(item, "reliability", "") or "").strip().lower()
        quality_notes: list[str] = []
        if freshness == "stale":
            quality_notes.append("数据时间较旧")
        if reliability == "low":
            quality_notes.append("可信度有限")
        if not quality_notes:
            continue
        evidence_id = _text(getattr(item, "evidence_id", None), limit=100)
        label = _text(getattr(item, "label", None), limit=60)
        if not evidence_id or not label:
            continue
        output.append({
            "id": f"{evidence_id}-quality",
            "title": f"{label}需谨慎解读",
            "detail": "，且".join(quality_notes),
            "handling": "未将该项作为当前确定状态；本次回答采用保守表达",
        })
        break

    for conflict in getattr(personal_packet, "conflicts", ()):
        if len(output) >= MAX_LIMITATIONS:
            return output
        conflict_id = _text(getattr(conflict, "conflict_id", None), limit=100)
        category = str(getattr(conflict, "category", "") or "").strip().lower()
        if not conflict_id:
            continue
        label = _DIMENSION_LABELS.get(category, category or "关键")
        output.append({
            "id": conflict_id,
            "title": (
                f"{label}存在冲突"
                if label.endswith("数据")
                else f"{label}数据存在冲突"
            ),
            "detail": "不同来源的记录不一致",
            "handling": "未将冲突数据合并为确定结论",
        })
        break

    for gap in getattr(personal_packet, "gaps", ()):
        if len(output) >= MAX_LIMITATIONS:
            return output
        gap_id = _text(getattr(gap, "gap_id", None), limit=100)
        category = str(getattr(gap, "category", "") or "").strip().lower()
        detail = _text(getattr(gap, "detail", None), limit=160)
        if not gap_id or not detail:
            continue
        label = _DIMENSION_LABELS.get(category, category or "关键")
        output.append({
            "id": gap_id,
            "title": f"{label}信息缺失",
            "detail": detail,
            "handling": "未将缺失信息推断为正常或不存在",
        })
    failed_count = len(tuple(getattr(personal_packet, "failed_partitions", ()) or ()))
    budget = getattr(personal_packet, "budget", None)
    truncated = bool(getattr(budget, "truncated", False))
    if len(output) < MAX_LIMITATIONS and (failed_count or truncated):
        detail_parts: list[str] = []
        if failed_count:
            detail_parts.append(f"有 {failed_count} 类数据未成功加载")
        if truncated:
            detail_parts.append("本轮依据已按相关性筛选")
        output.append({
            "id": "personal-context-availability",
            "title": "部分健康数据不可完整使用",
            "detail": "；".join(detail_parts),
            "handling": "未加载或未展示的数据不作为本轮结论依据",
        })
    return output


def _diet_list_calendar_projection(
    args: Mapping[str, Any], result: Any,
) -> tuple[dict[str, str], str] | None:
    """Adapt an executed dated diet read to the existing calendar projection.

    A list endpoint and a query endpoint describe the same evidence only when
    their actual rows match the requested date and meal. Writes never enter
    this adapter, and failed responses cannot lend their attached rows as facts.
    """
    if args.get("record_type") != "diet" or args.get("operation") != "list":
        return None
    try:
        requested_date = date.fromisoformat(args.get("date")).isoformat()
    except (TypeError, ValueError):
        return None
    meal_type = args.get("meal_type")
    if meal_type is not None and (
        not isinstance(meal_type, str)
        or meal_type not in {"breakfast", "lunch", "dinner", "snack", "extra"}
    ):
        return None
    projected_args = {"dimension": "diet", "start_date": requested_date,
                      "end_date": requested_date, "timezone": DEFAULT_TIMEZONE}
    try:
        payload = json.loads(result) if isinstance(result, str) else result
    except (TypeError, ValueError):
        payload = None
    if (
        result_declares_explicit_failure(result)
        or isinstance(result, str) and result.lstrip().startswith("Error")
        or isinstance(payload, Mapping) and (
            payload.get("status") in ("pending", "processing", "unavailable")
            or payload.get("availability") == "unavailable"
        )
    ):
        return projected_args, json.dumps({"status": "failed", "message": "本轮饮食记录查询失败"}, ensure_ascii=False)
    rows = payload if isinstance(payload, list) else next((
        payload[key] for key in ("records", "items", "data")
        if isinstance(payload, Mapping) and isinstance(payload.get(key), list)
    ), None)
    valid = isinstance(rows, list) and (
        not isinstance(payload, Mapping) or payload.get("record_type", "diet") == "diet"
    )
    if valid:
        valid = all(
            isinstance(row, Mapping)
            and row.get("record_date") == requested_date
            and (meal_type is None or row.get("meal_type") == meal_type)
            for row in rows
        )
    availability = payload.get("availability") if isinstance(payload, Mapping) else None
    if availability not in ("available", "partial", "no_data"):
        availability = "available" if valid and rows else "no_data"
    if availability == "no_data" and rows:
        valid = False
    projected_result = {
        "dimension": "diet",
        "window": {"start_date": requested_date, "end_date": requested_date, "timezone": DEFAULT_TIMEZONE},
        "records": rows if valid else None,
        "availability": availability,
    }
    return projected_args, json.dumps(projected_result, ensure_ascii=False)


_CALENDAR_DIMENSIONS = frozenset({"diet", "sleep", "workout", "supplements"})
_CALENDAR_SUCCESS = frozenset({"success", "completed", "complete", "ok", "succeeded"})


def _calendar_limitation(
    identifier: str, dimension: str, detail: str
) -> dict[str, str]:
    return {
        "id": identifier,
        "title": f"{_DIMENSION_LABELS.get(dimension, '健康')}数据不足",
        "detail": detail,
        "handling": "未将缺失或未核验数据作为确定依据",
    }


def _calendar_item_evidence(identifier: str, args: Mapping[str, Any], payload: Any):
    """Project one executed, exactly bounded result without trusting row prose."""
    from decimal import Decimal
    from app.services.agent_composed_read_completion import _validate
    from app.services.agent_daily_read_execution import (
        _summary_decimal,
        _summary_display,
    )
    from app.services.agent_query_window import parse_query_window

    dimension = args.get("dimension")
    invalid = (
        [],
        [
            _calendar_limitation(
                f"{identifier}-limitation",
                dimension if isinstance(dimension, str) else "",
                "返回记录的范围、来源或执行状态无法核验，未将其作为本轮依据",
            )
        ],
    )
    if not isinstance(dimension, str) or dimension not in _CALENDAR_DIMENSIONS:
        return invalid
    if result_declares_explicit_failure(payload):
        return [], [_calendar_limitation(
            f"{identifier}-limitation", dimension,
            "本轮数据查询失败，未将返回记录作为本轮依据",
        )]
    try:
        window = parse_query_window(args)
        canonical = {"dimension": dimension, **window.as_dict()}
        if "days" in args:
            if (
                type(args["days"]) is not int
                or args["days"] != (window.end_date - window.start_date).days + 1
            ):
                return invalid
            canonical["days"] = args["days"]
        if args != canonical or _validate(canonical, payload) is not None:
            return invalid
    except (TypeError, ValueError, KeyError):
        return invalid

    # Serialize only the projection consumed below, never private metadata or
    # arbitrary nested values attached to the actual result.
    fields = {"record_date", "food_name", "food_items", "meal_type", "calories", "protein",
              "total_sleep_duration", "deep_sleep_duration", "sleep_score"}
    projection = {
        "dimension": dimension, "window": window.as_dict(),
        "availability": payload["availability"], "limitations": payload.get("limitations", []),
        "records": [{k: v for k, v in row.items() if k in fields
                     and isinstance(v, (str, int, float)) and not isinstance(v, bool)}
                    for row in payload["records"]],
    }
    serialized = json.dumps(projection, ensure_ascii=False)
    limitation = _tool_limitation(
        tool_index=1, tool_name="health_query", args=args, result=serialized
    )
    limits = [{**limitation, "id": f"{identifier}-limitation"}] if limitation else []
    if dimension in {"diet", "sleep"}:
        block = build_table_from_tool_call("health_query", dict(args), serialized)
        rows = (
            _table_rows(tool_index=1, tool_name="health_query", block=block)
            if block
            else []
        )
        return (
            [
                {**row, "id": f"{identifier}-row-{i}"}
                for i, row in enumerate(rows[:MAX_BASIS_ITEMS], 1)
            ],
            limits,
        )

    rows = []
    for index, row in enumerate(payload["records"][:MAX_BASIS_ITEMS], 1):
        label = f"{_DIMENSION_LABELS[dimension]} · {row['record_date']}"
        observation = "实际服用记录 1 条"
        if dimension == "workout":
            seconds = _summary_decimal(row.get("duration_seconds"))
            minutes = (
                _summary_display(seconds / Decimal(60)) if seconds is not None else None
            )
            observation = (
                f"运动时长 {minutes} 分钟"
                if minutes is not None
                else "实际运动记录 1 条；时长未知"
            )
        rows.append(
            {
                "id": f"{identifier}-row-{index}",
                "label": label,
                "observation": observation,
                "source": "健康数据查询",
                "purpose": "用于核对实际服用记录"
                if dimension == "supplements"
                else "用于核对已记录运动",
            }
        )
    return rows, limits


def _calendar_batch_evidence(tool_index: int, args: Mapping[str, Any], payload: Any):
    """Match calendar results by frozen dimension; never fall back to legacy data."""
    identifier = f"tool-{tool_index}"
    invalid = (
        [],
        [
            _calendar_limitation(
                f"{identifier}-limitation",
                "",
                "本轮批量查询未完整返回可核验结果",
            )
        ],
    )
    queries = args.get("queries")
    if (
        set(args) != {"queries"}
        or not isinstance(queries, list)
        or not 1 <= len(queries) <= 4
        or any(
            not isinstance(q, Mapping) or not isinstance(q.get("dimension"), str)
            for q in queries
        )
        or len({q["dimension"] for q in queries}) != len(queries)
        or not isinstance(payload, Mapping)
        or not isinstance(payload.get("status"), str)
        or payload["status"] not in _CALENDAR_SUCCESS
        or result_declares_explicit_failure(payload)
        or not isinstance(payload.get("results"), list)
    ):
        return invalid
    results = payload["results"]
    per_query, limits = [], []
    for index, query in enumerate(queries, 1):
        matches = [
            r
            for r in results
            if isinstance(r, Mapping) and r.get("dimension") == query["dimension"]
        ]
        rows, notes = _calendar_item_evidence(
            f"{identifier}-item-{index}",
            query,
            matches[0] if len(matches) == 1 else None,
        )
        per_query.append(rows)
        limits.extend(notes)
    # Prefer one actual observation per requested domain before displaying a
    # second row, so the four-item display cap does not hide entire domains.
    basis = [
        rows[index]
        for index in range(MAX_BASIS_ITEMS)
        for rows in per_query
        if len(rows) > index
    ][:MAX_BASIS_ITEMS]
    if any(
        not isinstance(r, Mapping)
        or r.get("dimension") not in {q["dimension"] for q in queries}
        for r in results
    ):
        limits.append(
            _calendar_limitation(
                f"{identifier}-extra", "", "未使用请求范围之外的批量结果"
            )
        )
    return basis, limits[:MAX_LIMITATIONS]


def build_answer_evidence(
    *,
    tool_calls: Sequence[tuple[str, Mapping[str, Any] | None, Any]] = (),
    personal_packet: Any = None,
) -> dict[str, Any] | None:
    """Build one bounded projection from evidence actually selected this turn."""

    basis = _packet_basis(personal_packet) if personal_packet is not None else []
    limitations = (
        _packet_limitations(personal_packet) if personal_packet is not None else []
    )
    for tool_index, (tool_name, raw_args, result) in enumerate(tool_calls, start=1):
        if len(basis) >= MAX_BASIS_ITEMS and len(limitations) >= MAX_LIMITATIONS:
            break
        args = raw_args if isinstance(raw_args, Mapping) else {}
        projection_tool = tool_name
        if tool_name == "health_manage":
            projection = _diet_list_calendar_projection(args, result)
            if projection is None:
                continue
            args, result = projection
            projection_tool = "health_query"
        try:
            payload = json.loads(result) if isinstance(result, str) else result
        except (TypeError, ValueError):
            payload = None
        calendar_projection = None
        if projection_tool == "health_query_batch" and (
            isinstance(payload, Mapping)
            and "results" in payload
            or isinstance(args.get("queries"), list)
            and any(
                isinstance(q, Mapping) and ("start_date" in q or "end_date" in q)
                for q in args["queries"]
            )
        ):
            calendar_projection = _calendar_batch_evidence(tool_index, args, payload)
        elif projection_tool == "health_query" and (
            isinstance(payload, Mapping)
            and "window" in payload
            or "start_date" in args
            or "end_date" in args
        ):
            calendar_projection = _calendar_item_evidence(
                f"tool-{tool_index}", args, payload
            )
        if calendar_projection is not None:
            rows, notes = calendar_projection
            basis.extend(rows[: MAX_BASIS_ITEMS - len(basis)])
            limitations.extend(notes[: MAX_LIMITATIONS - len(limitations)])
            continue
        block = build_table_from_tool_call(projection_tool, dict(args), str(result or ""))
        if block is not None and len(basis) < MAX_BASIS_ITEMS:
            basis.extend(
                _table_rows(
                    tool_index=tool_index,
                    tool_name=tool_name,
                    block=block,
                )[: MAX_BASIS_ITEMS - len(basis)]
            )
        if len(limitations) < MAX_LIMITATIONS:
            limitation = _tool_limitation(
                tool_index=tool_index,
                tool_name=projection_tool,
                args=args,
                result=result,
            )
            if limitation:
                limitations.append(limitation)
    if not basis and not limitations:
        return None
    if basis and limitations:
        summary = f"本轮获得 {len(basis)} 条可核对数据，{len(limitations)} 项需注意"
    elif basis:
        summary = f"本轮获得 {len(basis)} 条可核对数据"
    else:
        summary = f"本轮有 {len(limitations)} 项数据限制"
    return {
        "version": VERSION,
        "summary": summary,
        "basis": basis,
        "limitations": limitations,
    }


def normalize_answer_evidence(value: Any) -> dict[str, Any] | None:
    """Validate an untrusted persisted/client projection without coercing objects."""

    if not isinstance(value, Mapping) or set(value) != _TOP_LEVEL_KEYS:
        return None
    if value.get("version") != VERSION:
        return None
    summary = _text(value.get("summary"), limit=120)
    basis = value.get("basis")
    limitations = value.get("limitations")
    if not summary or not isinstance(basis, list) or not isinstance(limitations, list):
        return None
    if len(basis) > MAX_BASIS_ITEMS or len(limitations) > MAX_LIMITATIONS:
        return None

    normalized_basis: list[dict[str, str]] = []
    for raw in basis:
        if not isinstance(raw, Mapping) or not set(raw).issubset(_BASIS_KEYS):
            return None
        required = {
            key: _text(raw.get(key), limit=180)
            for key in ("id", "label", "observation", "source")
        }
        if not all(required.values()):
            return None
        item = {key: value for key, value in required.items() if value is not None}
        for key in ("context", "purpose", "observed_at"):
            optional = _text(raw.get(key), limit=180)
            if optional:
                item[key] = optional
        for key, allowed in (("freshness", _FRESHNESS), ("confidence", _CONFIDENCE)):
            raw_enum = raw.get(key)
            if raw_enum is not None:
                enum_value = _text(raw_enum, limit=20)
                if enum_value not in allowed:
                    return None
                item[key] = enum_value
        normalized_basis.append(item)

    normalized_limitations: list[dict[str, str]] = []
    for raw in limitations:
        if not isinstance(raw, Mapping) or not set(raw).issubset(_LIMITATION_KEYS):
            return None
        required = {
            key: _text(raw.get(key), limit=180)
            for key in ("id", "title", "handling")
        }
        if not all(required.values()):
            return None
        item = {key: value for key, value in required.items() if value is not None}
        detail = _text(raw.get("detail"), limit=180)
        if detail:
            item["detail"] = detail
        normalized_limitations.append(item)

    return {
        "version": VERSION,
        "summary": summary,
        "basis": normalized_basis,
        "limitations": normalized_limitations,
    }


def answer_evidence_sha256(value: Any) -> str:
    """Bind one normalized projection to its persisted verification metadata."""

    normalized = normalize_answer_evidence(value)
    payload: Any = normalized if normalized is not None else value
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(encoded).hexdigest()
