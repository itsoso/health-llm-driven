"""Deterministic, client-safe explanation of evidence used in one answer.

The compiler accepts only current-turn structured tool results or evidence already
selected by the Health Evidence runtime. It never reads model prose, prompts, or
arbitrary nested health payloads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Any

from app.services.genui.table_builder import build_table_from_tool_call
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
        if status in {"no_data", "empty", "unavailable", "failed", "error"}:
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
        block = build_table_from_tool_call(tool_name, dict(args), str(result or ""))
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
                tool_name=tool_name,
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
