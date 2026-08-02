"""Unified Health Agent API — 统一健康助理端点

所有对话（记录、查询、分析、图片识别）统一走此入口。
旧外部网关已下线，所有对话统一走第一方 Agent。
"""
import asyncio
import base64
import json
import logging
import math
import time
import uuid
from typing import Optional, List


from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.llm.error_messages import safe_llm_error_message
from app.services.secure_upload import (
    UploadContentInvalid,
    UploadTooLarge,
    decode_base64_limited,
    decode_utf8_text,
    validate_image_bytes,
    validate_pdf_bytes,
)

logger = logging.getLogger(__name__)

# 2026-05-14 FIX-5 (G-W9 同模式): 客户端断开后 bg task 继续跑完 LLM/tool/写库.
# set 持 task 引用防 GC; done_callback 自动清理.
_BACKGROUND_AGENT_TASKS: set = set()
_BACKGROUND_AGENT_TASKS_BY_RUN: dict[str, set[asyncio.Task]] = {}
router = APIRouter()


class AgentTurnStatusResponse(BaseModel):
    client_turn_id: str
    run_id: str | None = None
    status: str
    request_persisted: bool
    response_persisted: bool
    conversation_id: int | None = None
    retryable: bool
    error_code: str | None = None


class _BoundedSSEBridge:
    """Bound live transport memory without cancelling the durable Agent turn."""

    def __init__(self, *, max_chunks: int):
        if type(max_chunks) is not int or not 1 <= max_chunks <= 2048:
            raise ValueError("invalid_stream_queue_max_chunks")
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_chunks)
        self._attached = True

    @property
    def buffered_chunks(self) -> int:
        return self._queue.qsize()

    async def publish(self, item: str | None) -> bool:
        while self._attached:
            try:
                await asyncio.wait_for(self._queue.put(item), timeout=0.05)
                return True
            except TimeoutError:
                continue
        return False

    async def get(self) -> str | None:
        return await self._queue.get()

    def detach(self) -> None:
        self._attached = False


# 防双发短期缓存: (user_id, msg_hash) → expiry_ts
# 用于检测客户端 silence_timer + onSpeechEnd 偶发同一 message 短时间内发 2 次的情况.
# 不持久化, 进程内即可; 多 worker 各自一份没关系 (同一连接通常落同一 worker).
_RECENT_DUP_CACHE: dict[tuple[int, str], float] = {}
_DUP_WINDOW_SECONDS = 3.0
_MAX_THINKING_STEPS = 8
_THINKING_STEPS_KIND = "safe_progress_summary"
_TOOL_THOUGHT_LABELS = {
    "health_query": "健康数据",
    "health_record": "记录信息",
    "health_manage": "健康记录",
}


def _tool_thought_label(tool_name: str | None) -> str:
    tool = (tool_name or "").strip()
    if not tool:
        return "相关数据"
    if tool in _TOOL_THOUGHT_LABELS:
        return _TOOL_THOUGHT_LABELS[tool]
    if "weather" in tool or "environment" in tool:
        return "环境数据"
    if "calendar" in tool:
        return "日程上下文"
    if "medical" in tool or "exam" in tool or "lab" in tool:
        return "体检数据"
    if "genetic" in tool:
        return "基因数据"
    if "supplement" in tool:
        return "补剂数据"
    if "diet" in tool:
        return "饮食数据"
    if "sleep" in tool:
        return "睡眠数据"
    return "相关数据"


def _status_stage_thought(stage: str | None, detail: str | None = None, round: int | None = None) -> str | None:
    s = (stage or "").strip()
    trimmed_detail = (detail or "").strip()
    if s == "vision":
        return "识别图片中"
    if s == "thinking":
        return "整理思路" if isinstance(round, int) and round >= 2 else "正在思考"
    if s == "tool":
        return f"正在{trimmed_detail}" if trimmed_detail else "调用工具中"
    if s == "synthesis":
        return "整理回复中"
    return None


def _thought_step_from_agent_event(event: dict | None) -> str | None:
    """Map SSE events to safe user-facing progress summaries.

    These are not model chain-of-thought: they are coarse transport/tool/status
    labels that the mobile client already displays live.
    """
    if not isinstance(event, dict):
        return None
    name = event.get("event")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if name == "agent_start":
        return "正在理解你的问题"
    if name == "tool_call":
        return f"读取{_tool_thought_label(data.get('tool'))}"
    if name == "tool_result":
        label = _tool_thought_label(data.get("tool"))
        return f"已取得{label}" if data.get("success") else f"{label}暂时不可用"
    if name == "status":
        return _status_stage_thought(data.get("stage"), data.get("detail"), data.get("round"))
    return None


def _append_thinking_step(current: list[str] | None, next_step: str | None) -> list[str]:
    normalized = (next_step or "").strip()
    existing = [str(s).strip() for s in (current or []) if str(s).strip()]
    if not normalized or normalized in existing:
        return existing[-_MAX_THINKING_STEPS:]
    return [*existing, normalized][-_MAX_THINKING_STEPS:]


def _normalize_thinking_steps(steps: list | None) -> list[str]:
    out: list[str] = []
    for step in steps or []:
        normalized = str(step or "").strip()
        if normalized and normalized not in out:
            out.append(normalized)
    return out[-_MAX_THINKING_STEPS:]


_MD_TABLE_RE = __import__("re").compile(r"^\s*\|.*\|.*\|\s*$", __import__("re").MULTILINE)
_MD_TABLE_SEP_RE = __import__("re").compile(r"^\s*\|?\s*:?-{2,}", __import__("re").MULTILINE)
_REVA_UI_FENCE_RE = __import__("re").compile(
    r"^[ \t]*```reva-ui[ \t]*\r?\n(?P<payload>.*?)(?:\r?\n)^[ \t]*```[ \t]*$",
    __import__("re").MULTILINE | __import__("re").DOTALL,
)
_DETERMINISTIC_REVA_UI_DATA_TYPES = {
    "diet_daily_summary",
    "medication_list",
    "sleep_summary",
}
_DETERMINISTIC_REVA_UI_COMPONENTS = {
    "line_chart",
    "metric_empty_state",
    "metric_line_chart",
}


def _mobile_cell_text(value: object) -> str:
    """Match the non-empty values accepted by Mobile's metricTable.cellText."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return str(value) if math.isfinite(value) else ""
        except OverflowError:
            return ""
    return ""


def _is_client_renderable_reva_ui(descriptor: dict) -> bool:
    """Conservative subset of the Mobile reva-ui parser contract."""
    if type(descriptor.get("v")) is not int or descriptor["v"] != 1:
        return False

    card_type = descriptor.get("type")
    if card_type in _DETERMINISTIC_REVA_UI_DATA_TYPES:
        return isinstance(descriptor.get("data"), dict)
    if card_type == "metric_table":
        columns = descriptor.get("columns")
        rows = descriptor.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list) or not rows:
            return False
        valid_keys: list[str] = []
        seen_keys: set[str] = set()
        for column in columns:
            if not isinstance(column, dict):
                continue
            key = _mobile_cell_text(column.get("key"))
            label = _mobile_cell_text(column.get("label"))
            if not key or not label or key in seen_keys:
                continue
            valid_keys.append(key)
            seen_keys.add(key)
            if len(valid_keys) >= 4:
                break
        if len(valid_keys) < 2:
            return False
        return any(
            isinstance(row, dict)
            and any(_mobile_cell_text(row.get(key)) for key in valid_keys)
            for row in rows
        )
    return descriptor.get("component") in _DETERMINISTIC_REVA_UI_COMPONENTS


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _answer_owns_its_visualization(answer_text: str, tools_used: list | None) -> bool:
    """本轮 LLM 是否已自带可视化 → 该压掉冗余的关键词单日快照卡。

    信号(任一命中):① 答案含 markdown 表格(≥2 表行 + 分隔行,如"睡眠与HRV对照"表);
    ② 本轮跑过 health_analysis(深分析,正文即多段分析);③ 答案含闭合且
    JSON 可解析、客户端可渲染的确定性 reva-ui 可视化。
    这些情况下快照卡(sleep/weight/bp…)只会与更好的正文重复且常错配窗口
    (founder 截图:问"上周睡眠不好吗", 却贴今晚单晚快照)。
    直接单指标速查(答案是一句话、无表)不命中 → 快照卡照常出(卡即答案)。
    """
    text = answer_text or ""
    if _MD_TABLE_SEP_RE.search(text) and len(_MD_TABLE_RE.findall(text)) >= 2:
        return True
    if isinstance(tools_used, list) and "health_analysis" in tools_used:
        return True
    for match in _REVA_UI_FENCE_RE.finditer(text):
        try:
            descriptor = json.loads(
                match.group("payload"),
                parse_constant=_reject_nonstandard_json_constant,
            )
        except (TypeError, ValueError):
            continue
        if isinstance(descriptor, dict) and _is_client_renderable_reva_ui(descriptor):
            return True
    return False


def _merge_card_descriptors(*groups: list | None) -> list:
    """Merge SSE cards, updating a stable card instead of duplicating it."""

    out: list = []
    positions: dict[str, int] = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for card in group:
            if not isinstance(card, dict) or not isinstance(card.get("type"), str):
                continue
            data = card.get("data")
            card_id = data.get("card_id") if isinstance(data, dict) else None
            if isinstance(card_id, str) and card_id.strip():
                key = f"{card['type']}:{card_id.strip()}"
            else:
                try:
                    key = json.dumps(card, sort_keys=True, ensure_ascii=False, default=str)
                except Exception:
                    key = f"{card.get('type')}:{len(out)}"
            position = positions.get(key)
            if position is None:
                positions[key] = len(out)
                out.append(card)
            else:
                out[position] = card
    return out


def _done_event_may_expose_cards(data: dict | None) -> bool:
    """Action cards are valid only for a durable, completed assistant turn."""
    if not isinstance(data, dict):
        return False
    return (
        data.get("request_persisted") is not False
        and data.get("completion_status") == "complete"
        and isinstance(data.get("message_id"), int)
    )


def _pending_intake_suppressions(data: dict | None) -> set[str]:
    """Map server-owned pending write kinds to conflicting legacy draft cards."""
    if not isinstance(data, dict):
        return set()
    kinds = data.get("pending_write_intent_kinds")
    if not isinstance(kinds, list):
        return set()
    suppress: set[str] = set()
    if "medication_intake_batch" in kinds:
        suppress.add("medication")
    return suppress


def _verified_intake_suppressions(data: dict | None) -> set[str]:
    """Suppress an intake projection only after durable receipt verification."""
    if not isinstance(data, dict):
        return set()
    receipts = data.get("write_receipts")
    if not isinstance(receipts, list):
        return set()
    kind_by_resource_type = {
        "diet_record": "diet",
        "medication_log": "medication",
        "supplement_log": "supplement",
    }
    return {
        kind
        for receipt in receipts
        if isinstance(receipt, dict)
        and receipt.get("verified") is True
        and receipt.get("status") == "verified"
        and (kind := kind_by_resource_type.get(receipt.get("resource_type")))
    }


def _persist_done_cards(db: Session, message_id: int | None, cards: list) -> bool:
    """Persist cards appended by the API wrapper into AgentMessage.meta.

    AgentExecutor already writes its own metadata before yielding `done`. The
    route wrapper may append inline/query cards afterwards, so it must patch the
    same assistant message or history reload will lose cards that were visible
    during the live stream.
    """

    if not message_id or not cards:
        return False
    try:
        from app.models.agent_conversation import AgentMessage
        from app.services.dynamic_card_persistence import cards_for_persistence

        msg = db.query(AgentMessage).filter(AgentMessage.id == message_id).first()
        if not msg:
            return False
        meta = dict(msg.meta or {})
        meta["cards"] = _merge_card_descriptors(
            cards_for_persistence(meta.get("cards") or []),
            cards_for_persistence(cards),
        )
        msg.meta = meta
        db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.debug(
            "[agent.stream] persist done cards skipped message_id=%s error_type=%s",
            message_id,
            type(e).__name__,
        )
        return False


def _persist_done_llm_usage(db: Session, message_id: int | None, usage: dict | None) -> None:
    """Persist per-answer token/cost profile into AgentMessage.meta."""

    if not message_id or not isinstance(usage, dict) or not usage:
        return
    try:
        from app.models.agent_conversation import AgentMessage

        msg = db.query(AgentMessage).filter(AgentMessage.id == message_id).first()
        if not msg:
            return
        meta = dict(msg.meta or {})
        meta["llm_usage"] = usage
        msg.meta = meta
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("[agent.stream] persist llm usage skipped: %s", e)


def _persist_done_thinking_steps(db: Session, message_id: int | None, steps: list | None) -> None:
    """Persist safe progress summaries into AgentMessage.meta for history restore."""

    normalized = _normalize_thinking_steps(steps)
    if not message_id or not normalized:
        return
    try:
        from app.models.agent_conversation import AgentMessage

        msg = db.query(AgentMessage).filter(AgentMessage.id == message_id).first()
        if not msg:
            return
        meta = dict(msg.meta or {})
        meta["thinking_steps"] = normalized
        meta["thinking_steps_kind"] = _THINKING_STEPS_KIND
        msg.meta = meta
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("[agent.stream] persist thinking steps skipped: %s", e)


def _check_recent_dup(user_id: int, message: str) -> bool:
    """同一 user 同一 message 在 3s 内重复 → 返回 True (拒绝).

    幅匹配: 取 message strip + 前 200 字 (语音转写常见). 不区分 conversation_id —
    用户多 tab 同一句话可能 fire 2 次, 同样应该拒.
    """
    import time
    now = time.time()
    key = (user_id, (message or "").strip()[:200])

    # 清理过期
    if len(_RECENT_DUP_CACHE) > 256:
        for k, exp in list(_RECENT_DUP_CACHE.items()):
            if exp < now:
                _RECENT_DUP_CACHE.pop(k, None)

    expiry = _RECENT_DUP_CACHE.get(key)
    if expiry and expiry > now:
        logger.warning(
            f"[agent.stream] dup msg rejected user={user_id} msg={key[1][:40]!r}"
        )
        return True

    _RECENT_DUP_CACHE[key] = now + _DUP_WINDOW_SECONDS
    return False


def _dispatch_life_event_extraction(db, user_id, conversation_id, assistant_message_id) -> None:
    """转后异步接缝: 回合完成后入队, 从本回合用户消息抽生活事件写时间线。

    镜像 memory 抽取先例 (系统侧派生写, 不经 LLM 工具自由写)。以助手消息 id 锚定
    紧邻的 user 消息 (id 更小)。enqueue 失败旁路, 绝不阻断用户对话 (mirror live_run)。
    """
    if not conversation_id or not assistant_message_id:
        return
    try:
        from app.models.agent_conversation import AgentMessage

        row = (
            db.query(AgentMessage.id)
            .filter(
                AgentMessage.conversation_id == conversation_id,
                AgentMessage.role == "user",
                AgentMessage.id < assistant_message_id,
            )
            .order_by(AgentMessage.id.desc())
            .first()
        )
        if row is None:
            return
        from app.tasks.life_event_extraction import extract_life_events

        extract_life_events.delay(int(user_id), int(row[0]))
    except Exception as e:  # noqa: BLE001 — 入队失败不影响主链路
        logger.warning(f"[life_event] enqueue extraction failed (bypass): {e}")


# ---------------------------------------------------------------------------
# GenUI 短路 (reva-ui chart components) — 与 orchestrator 同一确定性 builder。
#
# 背景: Mac/mobile 统一聊天走本文件的 `agent_stream`, 但历史上只有
# orchestrator 端点接了 GenUI 协商。charting query ("绘制我最近半年的HRV曲线")
# 带 genui-v1 cap 落到这里会走 LLM 吐 ASCII/文本, 不出图。
#
# 铁律 (R4): 图表数值全部来自 chart_builder 的 DB 查询, 本路径绝不调用 LLM。
# 数据不足: 新端 (genui-components-v1) 返回 metric_empty_state; 旧端继续 fall through。
# 异常 → 返回 None, 调用方 FALL THROUGH 到普通 AgentExecutor 路径。
# ---------------------------------------------------------------------------

GENUI_CAP = "genui-v1"
GENUI_COMPONENTS_CAP = "genui-components-v1"

_GENUI_METRIC_LABEL = {
    "hrv": "HRV",
    "resting_hr": "静息心率",
    "stress": "压力",
    "sleep": "睡眠时长",
    "sleep_score": "睡眠评分",
    "steps": "步数",
    "body_battery": "身体电量",
    "weight": "体重",
    "bp_systolic": "收缩压",
    "bp_diastolic": "舒张压",
    "waist": "腰围",
    "body_fat": "体脂率",
    "blood_glucose": "血糖",
    "spo2": "血氧",
}
_GENUI_RANGE_LABEL = {"7d": "最近一周", "1m": "近一个月", "3m": "近三个月", "6m": "近半年"}


def _maybe_genui_chart_events(
    db: Session,
    user_id: int,
    message: str,
    conversation_id: int | None,
    caps: list[str],
    client_turn_id: str | None = None,
) -> Optional[tuple[list[dict], int, int]]:
    """确定性构建 reva-ui 图表组件, 持久化 assistant 消息, 返回要 emit 的 SSE 事件。

    返回 (events, conversation_id, message_id) 命中时; 否则 None (调用方走普通路径)。
    - caps 缺 genui-v1 / 非图表意图 / 数据不足 → None。
    - events 复用 `agent_stream` 现有 shape: token (data.content 含 ```reva-ui block)
      + done ({conversation_id, message_id, elapsed_ms, mode})。
    - assistant 消息写入与普通路径同一 durable store (AgentConversationService), 含 reva-ui
      文本 → 历史/恢复可见, message_id 真实。
    """
    if GENUI_CAP not in (caps or []):
        return None

    from app.services.genui import (
        build_empty_state,
        build_line_chart,
        build_intra_curve,
        build_multi_metric_chart,
        detect_chart_requests,
        detect_intra_curve_request,
        render_reva_ui_block,
    )

    # 单窗(昼/夜)intra 曲线优先 (血氧/HRV/心率/呼吸/压力/血糖/睡眠)。bug 修: 「昨晚/今天X」
    # 曾被误判成近半年月度趋势。命中即走逐点分支, 不再 fall through 到区间趋势检测。
    intra = detect_intra_curve_request(message)
    if intra is not None:
        _intra_metric, _intra_window = intra
        block = build_intra_curve(db, user_id, _intra_metric, _intra_window)
        if block is None:
            # 诚实兜底: 该窗无该指标逐点采样 → 不回退月度趋势, 走普通 LLM 路径 (永不答非所问)。
            return None
        intro = f"{block.get('title', '曲线')}（数据来自你的设备，逐点采样）："
        full_reply = f"{intro}\n\n{render_reva_ui_block(block)}"
    else:
        detected = detect_chart_requests(message)
        if not detected:
            return None

        rng = detected[0][1]
        range_label = _GENUI_RANGE_LABEL.get(rng, rng)
        component = "metric_line_chart" if GENUI_COMPONENTS_CAP in (caps or []) else "line_chart"

        if len(detected) >= 2:
            # 多指标叠加: 一张 line_chart 叠多条 metric 7 日滚动均值对比线 (无 LLM)。
            metrics = [m for m, _ in detected]
            block = build_multi_metric_chart(db, user_id, metrics, range=rng, component=component)
            if block is None:
                # 可用 metric < 1 → fall through (返回 None), 走普通路径 (永不断聊天)。
                return None
            note = block.get("data_note", "")
            intro = (
                f"近{range_label}多指标趋势对比（数据来自你的设备，{note}）："
                if note
                else f"近{range_label}多指标趋势对比（数据来自你的设备）："
            )
            full_reply = f"{intro}\n\n{render_reva_ui_block(block)}"
        else:
            metric, _rng = detected[0]
            block = build_line_chart(db, user_id, metric, range=rng, component=component)
            if block is None:
                if GENUI_COMPONENTS_CAP not in (caps or []):
                    # 旧端只声明 line_chart, 不认识空状态组件, 保持历史回退行为。
                    return None
                block = build_empty_state(metric, range=rng)
                if block is None:
                    return None

            metric_label = _GENUI_METRIC_LABEL.get(metric, metric)
            note = block.get("data_note", "")
            # 确定性模板叙事 (无 LLM); 图表数值只来自 block。
            if block.get("component") == "metric_empty_state":
                intro = f"{range_label}{metric_label}暂无足够数据："
            else:
                intro = (
                    f"{range_label}{metric_label}趋势（数据来自你的设备，{note}）："
                    if note
                    else f"{range_label}{metric_label}趋势（数据来自你的设备）："
                )
            full_reply = f"{intro}\n\n{render_reva_ui_block(block)}"

    # 持久化: 与 AgentExecutor.run_stream 相同的 AgentConversationService 会话/消息存储。
    from app.services.agent_conversation_service import AgentConversationService

    svc = AgentConversationService(db)
    def _replay(existing_user, existing_assistant=None):
        replay_events = [{"event": "request_persisted", "data": {
            "conversation_id": existing_user.conversation_id,
            "user_message_id": existing_user.id,
            "client_turn_id": client_turn_id,
            "replayed": True,
        }}]
        if existing_assistant and (existing_assistant.meta or {}).get("client_turn_finalized"):
            from app.services.health_evidence.delivery import (
                project_persisted_health_messages,
            )

            projected = project_persisted_health_messages(
                (existing_user, existing_assistant)
            )[-1]
            if projected.content:
                replay_events.append({
                    "event": "token",
                    "data": {"content": projected.content},
                })
            done_data = projected.meta
            done_data.update({
                "conversation_id": existing_assistant.conversation_id,
                "message_id": existing_assistant.id,
                "completion_status": done_data.get("completion_status") or "complete",
                "client_turn_id": client_turn_id,
                "replayed": True,
            })
            replay_events.append({"event": "done", "data": done_data})
            return replay_events, existing_user.conversation_id, existing_assistant.id
        replay_events.append({"event": "done", "data": {
            "conversation_id": existing_user.conversation_id,
            "message_id": None,
            "completion_status": "interrupted",
            "client_turn_id": client_turn_id,
            "replayed": True,
        }})
        return replay_events, existing_user.conversation_id, 0

    claimed_turn = False
    existing_user = None
    if client_turn_id:
        existing_user = svc.find_user_message_by_client_turn(user_id, client_turn_id)
        existing_assistant = svc.find_assistant_message_by_client_turn(user_id, client_turn_id)
        if (
            existing_user
            and existing_assistant
            and (existing_assistant.meta or {}).get("client_turn_finalized")
        ):
            return _replay(existing_user, existing_assistant)
        claimed_turn = svc.try_acquire_client_turn_execution(user_id, client_turn_id)
        if not claimed_turn:
            # Let AgentExecutor's async durable-turn wrapper wait/reclaim/replay.
            # Returning an interrupted done here used to look like an ACK even
            # when no user row had been committed yet.
            return None

    try:
        recovered = False
        if client_turn_id:
            db.expire_all()
            existing_user = svc.find_user_message_by_client_turn(user_id, client_turn_id)
            existing_assistant = svc.find_assistant_message_by_client_turn(user_id, client_turn_id)
            if (
                existing_user
                and existing_assistant
                and (existing_assistant.meta or {}).get("client_turn_finalized")
            ):
                return _replay(existing_user, existing_assistant)
            if existing_user:
                svc.discard_unfinalized_assistant_by_client_turn(user_id, client_turn_id)
                recovered = True

        if existing_user:
            conv = svc.get_or_create_conversation(
                user_id,
                existing_user.conversation_id,
                title=message,
            )
            user_msg = existing_user
        else:
            conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)
            user_msg, _ = svc.save_user_message_once(
                conv.id,
                user_id,
                message,
                client_turn_id=client_turn_id,
                meta={"client_turn_id": client_turn_id} if client_turn_id else None,
            )

        thinking_steps = ["正在理解你的问题", "整理回复中"]
        assistant_meta = {
            "mode": "agent",
            "genui": True,
            "sources_used": ["设备数据"],
            "thinking_steps": thinking_steps,
            "thinking_steps_kind": _THINKING_STEPS_KIND,
            "completion_status": "complete",
            "client_turn_finalized": True,
            **({"client_turn_id": client_turn_id} if client_turn_id else {}),
        }
        ai_msg = svc.save_message(
            conv.id,
            "assistant",
            full_reply,
            meta=assistant_meta,
            client_turn_id=client_turn_id,
            client_turn_user_id=user_id,
        )

        events = [
            {
                "event": "request_persisted",
                "data": {
                    "conversation_id": conv.id,
                    "user_message_id": user_msg.id,
                    "client_turn_id": client_turn_id,
                    "recovered": recovered,
                },
            },
            {"event": "agent_start", "data": {"message": "正在绘制图表…", "conversation_id": conv.id}},
            {"event": "token", "data": {"content": full_reply}},
            {
                "event": "done",
                "data": {
                    "conversation_id": conv.id,
                    "message_id": ai_msg.id,
                    "elapsed_ms": 0,
                    "mode": "agent",
                    "genui": True,
                    "thinking_steps": thinking_steps,
                    "completion_status": "complete",
                    "client_turn_id": client_turn_id,
                    "client_turn_finalized": True,
                },
            },
        ]
        return events, conv.id, ai_msg.id
    finally:
        if claimed_turn and client_turn_id:
            svc.release_client_turn_execution(user_id, client_turn_id)


class ImageItem(BaseModel):
    base64: str
    type: str = "jpeg"


class ClientTimeContext(BaseModel):
    # 客户端看到的本地时间；只做 prompt 辅助，不作为写库安全时间源。
    client_now_iso: Optional[str] = Field(default=None, max_length=80)
    timezone: Optional[str] = Field(default=None, max_length=64)
    timezone_offset_minutes: Optional[int] = Field(default=None, ge=-14 * 60, le=14 * 60)
    locale: Optional[str] = Field(default=None, max_length=32)


class AgentRequest(BaseModel):
    message: str = Field(max_length=10000)
    conversation_id: Optional[int] = None
    image_base64: Optional[str] = None
    image_type: Optional[str] = None
    images: Optional[List[ImageItem]] = None
    file_base64: Optional[str] = None
    file_name: Optional[str] = None
    # 入口 deeplink 携带的结构化上下文 (JSON string), 注入到 LLM prompt 不展示给用户.
    # 例: SNP 详情页点"详细聊饮食方案" → context 带当前页正展示的食材条目.
    extra_context: Optional[str] = Field(default=None, max_length=4000)
    # 输入通道(传输层声明,typed=打字 / voice=语音转写 / siri):症状类记录的
    # 确认策略依赖它 —— typed 免二次确认,语音/未声明 fail-closed 保留确认。
    channel: Optional[str] = Field(default=None, max_length=16)
    # 客户端生成的单轮幂等/恢复标识。只用于绑定本轮持久化消息，不包含用户内容。
    client_turn_id: Optional[str] = Field(
        default=None,
        max_length=80,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    client_time_context: Optional[ClientTimeContext] = None

    @field_validator("image_base64")
    @classmethod
    def check_image_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 10_000_000:
            raise ValueError("图片太大，最大支持约 7.5MB")
        return v

    @field_validator("images")
    @classmethod
    def check_images(cls, v: Optional[List]) -> Optional[List]:
        if v and len(v) > 9:
            raise ValueError("最多支持 9 张图片")
        if v:
            total_encoded_bytes = 0
            for img in v:
                if len(img.base64) > 10_000_000:
                    raise ValueError("单张图片太大，最大支持约 7.5MB")
                total_encoded_bytes += len(img.base64)
            if total_encoded_bytes > 30_000_000:
                raise ValueError("图片总大小过大，最多支持约 22MB")
        return v

    @field_validator("file_base64")
    @classmethod
    def check_file_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 15_000_000:  # ~11MB file
            raise ValueError("文件太大，最大支持约 11MB")
        return v


_AGENT_IMAGE_MAX_BYTES = 7_500_000
_AGENT_FILE_MAX_BYTES = 11_000_000
_AGENT_TEXT_FILE_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml",
}


def _validate_agent_attachments(
    req: AgentRequest,
) -> tuple[list[dict], str | None, str | None]:
    """Validate and normalize attachments before reserving Agent capacity."""
    raw_images: list[tuple[str, str]] = []
    if req.images:
        raw_images = [(img.base64, img.type) for img in req.images]
    elif req.image_base64:
        raw_images = [(req.image_base64, req.image_type or "jpeg")]

    images: list[dict] = []
    for encoded, declared_type in raw_images:
        data = decode_base64_limited(encoded, max_bytes=_AGENT_IMAGE_MAX_BYTES)
        detected_type = validate_image_bytes(
            data,
            declared_extension=declared_type,
        )
        images.append({
            "base64": base64.b64encode(data).decode("ascii"),
            "type": detected_type,
        })

    file_base64: str | None = None
    file_name = (req.file_name or "").strip() or None
    if req.file_base64:
        if not file_name:
            raise UploadContentInvalid("附件必须包含文件名")
        suffix = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        data = decode_base64_limited(req.file_base64, max_bytes=_AGENT_FILE_MAX_BYTES)
        if suffix == ".pdf":
            validate_pdf_bytes(data)
        elif suffix in _AGENT_TEXT_FILE_EXTENSIONS:
            decode_utf8_text(data, label="附件")
        else:
            raise UploadContentInvalid("附件仅支持 PDF、TXT、Markdown、CSV、JSON 和日志文本")
        file_base64 = base64.b64encode(data).decode("ascii")
    elif file_name:
        raise UploadContentInvalid("附件内容为空")

    return images, file_base64, file_name


def _validated_agent_attachments_or_400(
    req: AgentRequest,
) -> tuple[list[dict], str | None, str | None]:
    try:
        return _validate_agent_attachments(req)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ConversationTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        normalized = v.strip()
        if not normalized:
            raise ValueError("标题不能为空")
        return normalized


def _admit_agent_runtime(
    db: Session,
    *,
    run_id: str,
    attempt_id: str,
    user_id: int,
    conversation_id: int | None,
    client_turn_id: str | None,
    origin: str,
):
    """Return canonical identity, lifecycle ownership and admission disposition."""
    from app.services.agent_runtime_facade import admit_agent_runtime

    return admit_agent_runtime(
        db,
        run_id=run_id,
        attempt_id=attempt_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_turn_id=client_turn_id,
        origin=origin,
    )


def _reserve_agent_capacity(db: Session, *, user_id: int, origin: str) -> str:
    """Reserve one paid Agent execution slot before starting the provider call."""
    from app.services.agent_capacity import AgentCapacityController, AgentCapacityExceeded

    try:
        lease = AgentCapacityController(db).acquire(
            user_id=user_id,
            origin=origin,
        )
        return lease.lease_id
    except AgentCapacityExceeded as exc:
        if exc.scope == "user":
            detail = "你已有请求正在处理，请等待完成后再试"
        else:
            detail = "小巴当前请求较多，请稍后再试"
        raise HTTPException(status_code=429, detail=detail) from exc


def _release_agent_capacity_safely(
    db: Session,
    *,
    lease_id: str,
    user_id: int,
) -> None:
    """Release capacity without hiding a failed cleanup until lease expiry."""
    from app.services.agent_capacity import AgentCapacityController

    try:
        # Tool failures can leave the request session in an aborted transaction.
        # All Agent writes commit their own receipts, so rollback here only clears
        # unusable transaction state before the content-free lease release.
        db.rollback()
        if not AgentCapacityController(db).release(lease_id, user_id=user_id):
            logger.error(
                "[agent.capacity] lease release missed user=%s lease=%s",
                user_id,
                lease_id,
            )
    except Exception as exc:  # lease expiry remains the crash-recovery boundary
        logger.error(
            "[agent.capacity] lease release failed user=%s lease=%s error=%s",
            user_id,
            lease_id,
            type(exc).__name__,
            exc_info=True,
        )


def _register_agent_runtime_task(run_id: str, task: asyncio.Task) -> None:
    tasks = _BACKGROUND_AGENT_TASKS_BY_RUN.setdefault(run_id, set())
    tasks.add(task)

    def _discard(done_task: asyncio.Task) -> None:
        registered = _BACKGROUND_AGENT_TASKS_BY_RUN.get(run_id)
        if registered is None:
            return
        registered.discard(done_task)
        if not registered:
            _BACKGROUND_AGENT_TASKS_BY_RUN.pop(run_id, None)

    task.add_done_callback(_discard)


def _cancel_agent_runtime_task(run_id: str) -> bool:
    cancelled = False
    for task in tuple(_BACKGROUND_AGENT_TASKS_BY_RUN.get(run_id, ())):
        if task.done():
            continue
        task.get_loop().call_soon_threadsafe(task.cancel)
        cancelled = True
    return cancelled


async def _agent_runtime_heartbeat(
    context,
    *,
    managed: bool,
    worker_id: str,
    owner_task: asyncio.Task,
    initial_lease_deadline: float,
) -> None:
    from app.services.agent_runtime_lease import agent_runtime_heartbeat

    await agent_runtime_heartbeat(
        context,
        managed=managed,
        worker_id=worker_id,
        owner_task=owner_task,
        initial_lease_deadline=initial_lease_deadline,
    )


async def _stop_agent_runtime_heartbeat(
    heartbeat_task: asyncio.Task,
    *,
    run_id: str,
) -> None:
    from app.services.agent_runtime_lease import stop_agent_runtime_heartbeat

    await stop_agent_runtime_heartbeat(heartbeat_task, run_id=run_id)


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_runtime_run(
    run_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.agent_runtime import AgentRuntimeCoordinator, AgentRuntimeError
    from app.services.agent_runtime_rollout import runtime_control_enabled

    if not runtime_control_enabled():
        raise HTTPException(status_code=404, detail="Run 不存在")
    try:
        result = AgentRuntimeCoordinator(db).request_cancel(
            current_user.id,
            run_id,
        )
    except AgentRuntimeError as exc:
        raise HTTPException(status_code=404, detail="Run 不存在") from exc
    if result.status == "cancellation_requested":
        _cancel_agent_runtime_task(run_id)
    return {"run_id": result.run_id, "status": result.status}


@router.get(
    "/turns/{client_turn_id}/status",
    response_model=AgentTurnStatusResponse,
)
async def get_agent_turn_status(
    response: Response,
    client_turn_id: str = Path(min_length=1, max_length=112),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Reconcile an interrupted transport using content-free control metadata."""
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_runtime import AgentRuntimeCoordinator

    response.headers["Cache-Control"] = "no-store"

    runtime = AgentRuntimeCoordinator(db)
    conversations = AgentConversationService(db)
    run = runtime.get_run_by_client_turn(current_user.id, client_turn_id)
    source = conversations.find_user_message_by_client_turn(
        current_user.id,
        client_turn_id,
    )
    assistant = conversations.find_assistant_message_by_client_turn(
        current_user.id,
        client_turn_id,
    )
    if run is None and source is None:
        raise HTTPException(
            status_code=404,
            detail="回合不存在",
            headers={"Cache-Control": "no-store"},
        )

    conversation_id = (
        source.conversation_id
        if source is not None
        else run.conversation_id if run is not None else None
    )
    # A client-turn user row is claimed before private images finish uploading.
    # Only Runtime binding happens after the executor emits request_persisted,
    # so row existence alone must never acknowledge a photo turn.
    request_persisted = bool(
        run is not None and run.source_message_id is not None
    )
    response_persisted = bool(
        assistant is not None
        and (assistant.meta or {}).get("client_turn_finalized") is True
    ) or bool(
        run is not None and run.assistant_message_id is not None
    )
    return {
        "client_turn_id": client_turn_id,
        "run_id": run.run_id if run is not None else None,
        "status": (
            run.status
            if run is not None
            else "succeeded" if response_persisted else "running"
        ),
        "request_persisted": request_persisted,
        "response_persisted": response_persisted,
        "conversation_id": conversation_id,
        "retryable": bool(run.retryable) if run is not None else False,
        "error_code": run.error_code if run is not None else None,
    }


@router.get("/runs/{run_id}")
async def get_agent_runtime_run(
    run_id: str,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.agent_runtime import AgentRuntimeCoordinator, AgentRuntimeError
    from app.services.agent_runtime_rollout import runtime_control_enabled

    if not runtime_control_enabled():
        raise HTTPException(status_code=404, detail="Run 不存在")
    runtime = AgentRuntimeCoordinator(db)
    try:
        run = runtime.get_run(current_user.id, run_id)
        events = runtime.list_events_after(
            current_user.id,
            run_id,
            after_sequence=after,
            limit=limit,
        )
    except AgentRuntimeError as exc:
        raise HTTPException(status_code=404, detail="Run 不存在") from exc
    next_after = events[-1].sequence_no if events else after
    return {
        "run_id": run.run_id,
        "attempt_id": run.current_attempt_id,
        "status": run.status,
        "retryable": bool(run.retryable),
        "error_code": run.error_code,
        "next_after": next_after,
        "events": [
            {
                "sequence_no": event.sequence_no,
                "event_name": event.event_name,
                "payload": dict(event.payload),
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


def _agent_runtime_replay_events(db: Session, context) -> list[dict] | None:
    """Build a deterministic replay without starting another Executor."""
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.services.health_evidence.delivery import (
        project_persisted_health_messages,
    )

    run = AgentRuntimeCoordinator(db).get_run(context.user_id, context.run_id)
    if run.assistant_message_id is None:
        return None
    assistant = (
        db.query(AgentMessage)
        .join(
            AgentConversation,
            AgentConversation.id == AgentMessage.conversation_id,
        )
        .filter(
            AgentMessage.id == run.assistant_message_id,
            AgentConversation.user_id == context.user_id,
        )
        .first()
    )
    if assistant is None:
        return None
    source = None
    if run.source_message_id is not None:
        source = (
            db.query(AgentMessage)
            .join(
                AgentConversation,
                AgentConversation.id == AgentMessage.conversation_id,
            )
            .filter(
                AgentMessage.id == run.source_message_id,
                AgentConversation.user_id == context.user_id,
            )
            .first()
        )

    replay_delivery = project_persisted_health_messages(
        (source, assistant) if source is not None else (assistant,)
    )[-1]

    events: list[dict] = []
    if source is not None:
        events.append(
            {
                "event": "request_persisted",
                "data": {
                    "conversation_id": source.conversation_id,
                    "user_message_id": source.id,
                    "client_turn_id": context.client_turn_id,
                    "replayed": True,
                    "run_id": context.run_id,
                    "attempt_id": context.attempt_id,
                },
            }
        )
    if replay_delivery.content:
        events.append(
            {
                "event": "token",
                "data": {"content": replay_delivery.content},
            }
        )
    done_data = replay_delivery.meta
    done_data.update(
        {
            "conversation_id": assistant.conversation_id,
            "message_id": assistant.id,
            "completion_status": done_data.get("completion_status") or "complete",
            "client_turn_id": context.client_turn_id,
            "replayed": True,
            "run_id": context.run_id,
            "attempt_id": context.attempt_id,
        }
    )
    events.append({"event": "done", "data": done_data})
    return events


def _agent_runtime_replay_send_response(db: Session, context) -> dict | None:
    events = _agent_runtime_replay_events(db, context)
    if events is None:
        return None
    reply = "".join(
        str((event.get("data") or {}).get("content") or "")
        for event in events
        if event.get("event") == "token"
    )
    done_data = next(
        (
            event.get("data")
            for event in events
            if event.get("event") == "done" and isinstance(event.get("data"), dict)
        ),
        {},
    )
    from app.services.agent_send_meta import build_send_meta

    meta = build_send_meta(done_data, None)
    meta["replayed"] = True
    if done_data.get("health_evidence_replay_sanitized") is True:
        meta["health_evidence_replay_sanitized"] = True
    return {
        "reply": reply,
        "conversation_id": done_data.get("conversation_id"),
        "message_id": done_data.get("message_id"),
        "mode": "agent",
        "elapsed_ms": done_data.get("elapsed_ms"),
        "run_id": context.run_id,
        "attempt_id": context.attempt_id,
        "meta": meta,
    }


def _mark_agent_runtime_running(
    db: Session,
    context,
    *,
    managed: bool,
    worker_id: str | None = None,
) -> float | None:
    if not managed:
        return None
    from app.config import settings
    from app.services.agent_runtime import ACTIVE_RUN_STATUSES, AgentRuntimeCoordinator

    runtime = AgentRuntimeCoordinator(db)
    run = runtime.get_run(context.user_id, context.run_id)
    lease_seconds = int(
        getattr(settings, "agent_runtime_lease_seconds", 90) or 90
    )
    lease_started = time.monotonic()
    if run.status == "queued":
        runtime.mark_running(
            context,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
    elif run.status not in ACTIVE_RUN_STATUSES:
        # A duplicate request may be replaying an already finalized logical Run.
        return None
    return lease_started + lease_seconds


def _finalize_agent_runtime(
    db: Session,
    context,
    *,
    managed: bool,
    done_data: dict,
    source_message_id: int | None,
) -> None:
    if not managed:
        return
    from app.services.agent_runtime import AgentRuntimeCoordinator

    AgentRuntimeCoordinator(db).finalize_executor_done(
        context,
        done_data,
        source_message_id=source_message_id,
    )


def _bind_agent_runtime_request(
    db: Session,
    context,
    *,
    managed: bool,
    event_data: dict,
) -> int | None:
    """Bind a newly created conversation before answer generation continues."""
    source_message_id = event_data.get("user_message_id")
    conversation_id = event_data.get("conversation_id")
    if not isinstance(source_message_id, int):
        return None
    if managed and isinstance(conversation_id, int):
        from app.services.agent_runtime import AgentRuntimeCoordinator

        AgentRuntimeCoordinator(db).bind_messages(
            context,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            assistant_message_id=None,
        )
    return source_message_id


def _fail_agent_runtime(
    db: Session,
    context,
    *,
    managed: bool,
    error_code: str,
    retryable: bool = False,
) -> None:
    if not managed:
        return
    from app.services.agent_runtime import AgentRuntimeCoordinator

    runtime = AgentRuntimeCoordinator(db)
    if retryable:
        runtime.complete(
            context,
            status="failed",
            error_code=error_code,
            retryable=True,
        )
    else:
        runtime.fail_active(context, error_code=error_code)


def _fail_agent_runtime_safely(
    db: Session,
    context,
    *,
    managed: bool,
    error_code: str,
    retryable: bool = False,
) -> None:
    """Close an active Run even when the request session needs recovery."""
    if not managed:
        return
    try:
        _fail_agent_runtime(
            db,
            context,
            managed=True,
            error_code=error_code,
            retryable=retryable,
        )
        return
    except Exception:
        logger.exception(
            "Agent Runtime failure settlement needs fresh session: run_id=%s",
            context.run_id,
        )
    try:
        db.rollback()
    except Exception:
        logger.exception(
            "Agent Runtime failure settlement rollback failed: run_id=%s",
            context.run_id,
        )
    try:
        from sqlalchemy.orm import sessionmaker

        cleanup_session = sessionmaker(
            bind=db.get_bind(),
            autocommit=False,
            autoflush=False,
        )()
        try:
            _fail_agent_runtime(
                cleanup_session,
                context,
                managed=True,
                error_code=error_code,
                retryable=retryable,
            )
        finally:
            cleanup_session.close()
    except Exception:
        logger.exception(
            "Agent Runtime failure settlement failed: run_id=%s",
            context.run_id,
        )


def _interrupt_agent_runtime(db: Session, context, *, managed: bool) -> None:
    if not managed:
        return
    from app.services.agent_runtime import AgentRuntimeCoordinator

    AgentRuntimeCoordinator(db).interrupt_active(context)


def _finalize_agent_runtime_events(
    db: Session,
    context,
    *,
    managed: bool,
    events: list[dict],
) -> None:
    """Attach canonical identity and close a deterministic shortcut Run."""
    source_message_id = None
    done_data = None
    for event in events:
        if event.get("event") not in {"request_persisted", "done"}:
            continue
        data = event.setdefault("data", {})
        if not isinstance(data, dict):
            continue
        data.setdefault("run_id", context.run_id)
        data.setdefault("attempt_id", context.attempt_id)
        if event.get("event") == "request_persisted" and isinstance(
            data.get("user_message_id"), int
        ):
            source_message_id = data["user_message_id"]
        elif event.get("event") == "done":
            done_data = data

    try:
        _mark_agent_runtime_running(db, context, managed=managed)
        if done_data is None:
            raise RuntimeError("shortcut_missing_done")
        _finalize_agent_runtime(
            db,
            context,
            managed=managed,
            done_data=done_data,
            source_message_id=source_message_id,
        )
    except Exception:
        _fail_agent_runtime_safely(
            db,
            context,
            managed=managed,
            error_code="shortcut_finalize_failed",
        )
        raise


@router.post("/stream", summary="统一健康助理流式对话")
async def agent_stream(
    request: Request,
    req: AgentRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    x_reva_client_caps: str | None = Header(default=None),
):
    """统一健康 Agent — 记录 + 查询 + 分析 + 图片识别

    SSE 事件类型：
    - agent_start: Agent 开始
    - tool_call: 正在调用工具 {tool, args, round}
    - tool_result: 工具返回 {tool, success, preview}
    - token: 文本内容（思考过程或最终回答）
    - done: 完成 {conversation_id, message_id, elapsed_ms, mode}
    - error: 错误
    """
    has_images = bool(req.image_base64 or req.images)
    if not req.message.strip() and not has_images and not req.file_base64:
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 防双发 (用户反馈批 4): 客户端 silence_timer + onSpeechEnd 偶发同一 message 发 2 次
    # 后端用 in-memory 短期缓存 (3s 窗) 拒同一用户重复 message, 避免 LLM 重试浪费 + 撞 OpenAI proxy 限流.
    # 不持久化也 OK — 短期防护即可.
    _reject = not req.client_turn_id and _check_recent_dup(current_user.id, req.message)
    if _reject:
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍候。（同一消息 3 秒内已发送）",
        )

    all_images, file_b64, file_nm = _validated_agent_attachments_or_400(req)

    from app.services.agent_executor import AgentExecutor

    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
    user_id = current_user.id
    msg_text = req.message.strip()
    conv_id = req.conversation_id
    images_local = all_images or None
    extra_ctx = req.extra_context
    chan = req.channel
    client_turn_id = req.client_turn_id
    from app.config import settings as _agent_settings
    from app.services.health_evidence.delivery import (
        requires_live_health_executor,
    )

    live_health_executor_required = requires_live_health_executor(
        msg_text,
        enabled=bool(
            getattr(
                _agent_settings,
                "health_evidence_runtime_enabled",
                False,
            )
        ),
        extra_context=extra_ctx,
    )

    stream_run_id = f"run_{uuid.uuid4().hex[:16]}"
    stream_attempt_id = f"attempt_{uuid.uuid4().hex[:16]}"
    try:
        runtime_context, runtime_managed, runtime_disposition = _admit_agent_runtime(
            db,
            run_id=stream_run_id,
            attempt_id=stream_attempt_id,
            user_id=user_id,
            conversation_id=conv_id,
            client_turn_id=client_turn_id,
            origin="agent_stream",
        )
    except Exception as exc:
        from app.services.agent_runtime import ConversationAccessError, RunBusyError

        if isinstance(exc, RunBusyError):
            raise HTTPException(
                status_code=409,
                detail="上一条消息仍在处理，请稍后重试",
            ) from exc
        if isinstance(exc, ConversationAccessError):
            raise HTTPException(status_code=404, detail="对话不存在") from exc
        raise
    if runtime_disposition == "observe":
        raise HTTPException(
            status_code=409,
            detail="该消息仍在处理中，请稍后重试",
        )
    if runtime_disposition == "replay":
        replay_events = _agent_runtime_replay_events(db, runtime_context)
        if replay_events is None:
            raise HTTPException(
                status_code=409,
                detail="该消息已有处理状态，请刷新对话",
            )

        async def runtime_replay_generate():
            for event in replay_events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            runtime_replay_generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # GenUI 短路: caps=genui-v1 + 图表意图 + 无图片/附件 → 确定性出 reva-ui block,
    # 跳过 AgentExecutor/LLM (R4: 数值只来自 DB)。命中即持久化消息并直接 SSE 回放。
    # 数据不足 / 任何异常 → genui_events=None, FALL THROUGH 到普通路径 (永不断聊天)。
    from app.api._client_caps import parse_client_caps

    caps = parse_client_caps(x_reva_client_caps)
    genui_events: Optional[list[dict]] = None
    if (
        not live_health_executor_required
        and not has_images
        and not file_b64
    ):
        try:
            hit = _maybe_genui_chart_events(
                db,
                user_id,
                msg_text,
                conv_id,
                caps,
                client_turn_id=client_turn_id,
            )
            if hit is not None:
                genui_events, _conv, _mid = hit
                logger.info(
                    "[agent.stream] GenUI short-circuit hit user=%s conv=%s msg_id=%s",
                    user_id, _conv, _mid,
                )
        except Exception as e:  # noqa: BLE001
            # 失败软着陆: 不破坏聊天, 回退普通路径。
            logger.warning("[agent.stream] GenUI short-circuit failed, fall through: %s", e)
            try:
                db.rollback()
            except Exception:
                pass
            genui_events = None

    if genui_events is not None:
        _finalize_agent_runtime_events(
            db,
            runtime_context,
            managed=runtime_managed,
            events=genui_events,
        )

        async def genui_generate():
            for event in genui_events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            genui_generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Starter pregen serve (rank7): if this message EXACTLY matches a still-FRESH
    # pre-generated starter answer, replay it as SSE instead of running a live
    # ~30-40s turn. try_serve is fail-CLOSED on any staleness (recomputes
    # signals_hash, checks TTL) → None falls through to the live path below. Only
    # runs when the flag is on and there are no attachments (starters are text).
    from app.config import settings as _pregen_settings

    if (
        getattr(_pregen_settings, "starter_pregen_enabled", False)
        and not live_health_executor_required
        and not has_images
        and not file_b64
    ):
        pregen_hit = None
        try:
            from app.services import starter_pregen

            pregen_hit = starter_pregen.try_serve(
                db, user_id, msg_text,
                conversation_id=conv_id, client_turn_id=client_turn_id,
            )
        except Exception as e:  # noqa: BLE001 — never break chat; fall through to live
            logger.warning("[agent.stream] pregen serve failed, fall through: %s", e)
            pregen_hit = None
        if pregen_hit is not None:
            pregen_events, _pc, _pm, _pr = pregen_hit
            logger.info(
                "[agent.stream] pregen serve hit user=%s conv=%s msg_id=%s", user_id, _pc, _pm,
            )
            _finalize_agent_runtime_events(
                db,
                runtime_context,
                managed=runtime_managed,
                events=pregen_events,
            )

            async def pregen_generate():
                for event in pregen_events:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                pregen_generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

    try:
        capacity_lease_id = _reserve_agent_capacity(
            db,
            user_id=user_id,
            origin="agent_stream",
        )
    except Exception:
        _fail_agent_runtime_safely(
            db,
            runtime_context,
            managed=runtime_managed,
            error_code="capacity_unavailable",
            retryable=True,
        )
        raise

    async def generate():
        """G-W9 同模式 (FIX-5, 2026-05-14): bg task + asyncio.Queue.

        客户端断开 (App 后台 30s+ / 切走页面) → 这个 generator 抛 CancelledError /
        GeneratorExit 退出, 但 bg_task 继续跑到 LLM 完成 + 把 message 写库 + audit.
        用户回到 App 后, useFocusEffect/AppState 重新拉 conversation, 看到完整回复.
        """
        from app.config import settings as runtime_settings

        stream_bridge = _BoundedSSEBridge(
            max_chunks=int(
                getattr(
                    runtime_settings,
                    "agent_runtime_stream_queue_max_chunks",
                    128,
                )
                or 128
            )
        )

        async def _bg():
            # 独立 db session — 主 request 的 db 在客户端断开时会被 close
            from app.database import SessionLocal as _SessionLocal
            from app.services.llm.usage_tracker import (
                begin_usage_capture,
                clear_run_id,
                end_usage_capture,
                set_caller,
                set_run_id,
                summarize_usage_capture,
            )
            bg_db = _SessionLocal()
            usage_capture_token = begin_usage_capture()
            run_id_token = set_run_id(runtime_context.run_id)
            set_caller(
                "agent.stream",
                user_id=user_id,
                is_admin=bool(current_user.is_admin),
            )
            source_message_id = None
            runtime_finalized = False
            worker_id = f"worker_{uuid.uuid4().hex[:24]}"
            heartbeat_task = None
            try:
                initial_lease_deadline = _mark_agent_runtime_running(
                    bg_db,
                    runtime_context,
                    managed=runtime_managed,
                    worker_id=worker_id,
                )
                owner_task = asyncio.current_task()
                if owner_task is not None and runtime_managed:
                    if initial_lease_deadline is None:
                        raise RuntimeError("agent_runtime_missing_lease_deadline")
                    heartbeat_task = asyncio.create_task(
                        _agent_runtime_heartbeat(
                            runtime_context,
                            managed=True,
                            worker_id=worker_id,
                            owner_task=owner_task,
                            initial_lease_deadline=initial_lease_deadline,
                        )
                    )
                executor_bg = AgentExecutor(bg_db)
                # 累积 LLM 流式输出, done 时扫描 fenced ```menu_share 块 (L1 分享菜单)
                full_text_buf: list = []
                thinking_steps: list[str] = []
                async for event in executor_bg.run_stream(
                    user_id=user_id,
                    message=msg_text,
                    conversation_id=conv_id,
                    user_auth_token=user_token,
                    images=images_local,
                    file_base64=file_b64,
                    file_name=file_nm,
                    extra_context=extra_ctx,
                    channel=chan,
                    client_turn_id=client_turn_id,
                    client_caps=caps,
                    client_time_context=(
                        req.client_time_context.model_dump(exclude_none=True)
                        if req.client_time_context else None
                    ),
                    run_id=runtime_context.run_id,
                    attempt_id=runtime_context.attempt_id,
                    runtime_managed=runtime_managed,
                    runtime_write_block_reason=(
                        runtime_context.control_reason
                        if runtime_context.control_reason
                        in {"circuit_paused", "circuit_unavailable"}
                        else None
                    ),
                ):
                    if event.get("event") == "request_persisted":
                        persisted_data = event.get("data")
                        if isinstance(persisted_data, dict):
                            source_message_id = _bind_agent_runtime_request(
                                bg_db,
                                runtime_context,
                                managed=runtime_managed,
                                event_data=persisted_data,
                            )
                    if event.get("event") == "token":
                        tc = event.get("data", {}).get("content")
                        if isinstance(tc, str):
                            full_text_buf.append(tc)
                    thinking_steps = _append_thinking_step(
                        thinking_steps,
                        _thought_step_from_agent_event(event),
                    )
                    # 在 done 事件里附加动态卡片, 失败静默
                    if event.get("event") == "done":
                        event.setdefault("data", {})["run_id"] = runtime_context.run_id
                        event.setdefault("data", {})["attempt_id"] = runtime_context.attempt_id
                        if thinking_steps:
                            event.setdefault("data", {})["thinking_steps"] = thinking_steps
                        done_data = event.setdefault("data", {})
                        if not _done_event_may_expose_cards(done_data):
                            done_data.pop("cards", None)
                        else:
                            try:
                                from app.services.inline_cards import (
                                    build_cards,
                                    extract_inline_card_blocks,
                                    represented_intake_kinds,
                                )
                                existing = done_data.get("cards")
                                inline = extract_inline_card_blocks("".join(full_text_buf))
                                # 本轮已写入的摄入类记录 → 压制同 kind 的 query 派生草稿,
                                # 防「已记录+再确认」重复写入(油桃加餐双卡实锤)。
                                # 且只要 health_record 已接手(含待确认态):对话流拥有该
                                # 任务,草稿卡的"去 X 页记录"主按钮会把用户引离"说'是的'
                                # 即完成"的确认流(实锤:打卡替普瑞酮 → 确认问句与
                                # medication_draft 双路互搏;mac 上该按钮还曾是静默死键)。
                                suppress = represented_intake_kinds(existing, inline)
                                suppress = set(suppress) | _pending_intake_suppressions(
                                    done_data
                                )
                                suppress = set(suppress) | _verified_intake_suppressions(
                                    done_data
                                )
                                # 分析轮(LLM 正文已自带表格/多段分析)压掉冗余单日快照卡
                                suppress_snapshots = _answer_owns_its_visualization(
                                    "".join(full_text_buf),
                                    done_data.get("tools_used"),
                                )
                                cards = build_cards(
                                    bg_db,
                                    user_id,
                                    msg_text,
                                    suppress_intake_kinds=suppress,
                                    suppress_snapshot_cards=suppress_snapshots,
                                )
                                # LLM 主动输出的卡片优先，其次保留 AgentExecutor 已写入的
                                # system-KB evidence，再追加 query 派生卡片。历史恢复依赖
                                # message.meta.cards，所以合并后回写同一 assistant message。
                                merged = _merge_card_descriptors(inline, existing, cards)
                                if merged:
                                    persisted = _persist_done_cards(
                                        bg_db,
                                        done_data.get("message_id"),
                                        merged,
                                    )
                                    if persisted:
                                        done_data["cards"] = merged
                                    else:
                                        done_data.pop("cards", None)
                            except Exception as e:
                                logger.debug(
                                    "inline_cards 失败 user_id=%s message_id=%s error_type=%s",
                                    user_id,
                                    done_data.get("message_id"),
                                    type(e).__name__,
                                )
                        try:
                            usage = summarize_usage_capture()
                            if usage:
                                event.setdefault("data", {})["llm_usage"] = usage
                                _persist_done_llm_usage(
                                    bg_db,
                                    event.get("data", {}).get("message_id"),
                                    usage,
                                )
                        except Exception as e:  # noqa: BLE001
                            logger.debug("[agent.stream] attach llm usage skipped: %s", e)
                        try:
                            _persist_done_thinking_steps(
                                bg_db,
                                event.get("data", {}).get("message_id"),
                                thinking_steps,
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.debug("[agent.stream] attach thinking steps skipped: %s", e)
                        # 转后异步: 从本回合用户消息抽生活事件时间线 (旁路, 客户端断开也已跑到这)。
                        _dispatch_life_event_extraction(
                            bg_db,
                            user_id,
                            event.get("data", {}).get("conversation_id"),
                            event.get("data", {}).get("message_id"),
                        )
                        _finalize_agent_runtime(
                            bg_db,
                            runtime_context,
                            managed=runtime_managed,
                            done_data=event.get("data", {}),
                            source_message_id=source_message_id,
                        )
                        runtime_finalized = True
                    await stream_bridge.publish(
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    )
                if not runtime_finalized:
                    _fail_agent_runtime_safely(
                        bg_db,
                        runtime_context,
                        managed=runtime_managed,
                        error_code="executor_missing_done",
                    )
            except asyncio.CancelledError:
                _interrupt_agent_runtime(
                    bg_db,
                    runtime_context,
                    managed=runtime_managed,
                )
                raise
            except Exception as e:
                _fail_agent_runtime_safely(
                    bg_db,
                    runtime_context,
                    managed=runtime_managed,
                    error_code="executor_exception",
                )
                logger.error(
                    "Agent bg 流式异常 user_id=%s run_id=%s error_type=%s",
                    user_id,
                    runtime_context.run_id,
                    type(e).__name__,
                )
                err = {"event": "error", "data": {"message": safe_llm_error_message(e)}}
                try:
                    await stream_bridge.publish(
                        f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
                    )
                except Exception:
                    pass
            finally:
                if heartbeat_task is not None:
                    await _stop_agent_runtime_heartbeat(
                        heartbeat_task,
                        run_id=runtime_context.run_id,
                    )
                # sentinel: 通知 generator 结束
                try:
                    await stream_bridge.publish(None)
                except Exception:
                    pass
                try:
                    end_usage_capture(usage_capture_token)
                except Exception:
                    pass
                try:
                    clear_run_id(run_id_token)
                except Exception:
                    pass
                _release_agent_capacity_safely(
                    bg_db,
                    lease_id=capacity_lease_id,
                    user_id=user_id,
                )
                try:
                    bg_db.close()
                except Exception:
                    pass

        bg_task = asyncio.create_task(_bg())
        _BACKGROUND_AGENT_TASKS.add(bg_task)
        _register_agent_runtime_task(runtime_context.run_id, bg_task)
        bg_task.add_done_callback(_BACKGROUND_AGENT_TASKS.discard)

        try:
            while True:
                item = await stream_bridge.get()
                if item is None:
                    break
                yield item
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开 — bg_task 不取消, 让它跑完写完消息.
            logger.info(
                f"[agent.stream] client disconnected user={user_id}, "
                f"bg task continues to finish LLM + write message"
            )
            stream_bridge.detach()
            raise

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# /send 保活流式聚合(2026-07-06):重量级深分析单回合可远超 60s,而 main.py 的
# asyncio.wait_for 只计到 response start —— 非流式 JSON 要到回合结束才发出 start,
# 必被杀成 504(评测实锤:补剂互作全查 / 胃溃疡根因多源推理)。
# 修法:快窗内完成仍走历史非流式路径(错误保持 4xx/5xx);超窗切 chunked 响应,
# 周期吐一个空格(RFC 8259 合法 JSON 前导空白)同时重置三层 idle 计时器 ——
# 服务端 wait_for(response start 已发出)、nginx proxy_read_timeout(每次读重置,
# 配 X-Accel-Buffering: no 不缓冲)、客户端 urllib/URLSession(socket idle 语义)。
# 缓冲整个 body 再 json.loads 的客户端零契约变化。教训:有效超时=min(服务端,客户端),
# 保活字节是唯一同时重置两端的方式(见 memory: llm-import-timeout-three-caps)。
AGENT_SEND_KEEPALIVE_SECONDS = 10.0
# 保底硬上限:流式豁免不能让真卡死的回合永远吊着 worker(main.py LONG_REQUEST_PATHS
# 同款顾虑)。超限 → 取消回合 + in-body error,fail-loud。
AGENT_SEND_HARD_CAP_SECONDS = 300.0


class _AgentTurnError(Exception):
    """Agent 回合级失败(error 事件 / 未返回 done)。携带已过 safe_llm_error_message 的安全文案。"""


def _send_error_envelope(message: str) -> dict:
    """流已开始(200 已发出)后的错误载体:形状与成功响应一致 + error 字段。"""
    return {
        "reply": "",
        "conversation_id": None,
        "message_id": None,
        "mode": "agent",
        "elapsed_ms": None,
        "error": message,
    }


@router.post("/send", summary="统一健康助理非流式对话")
async def agent_send(
    request: Request,
    req: AgentRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    x_reva_client_caps: str | None = Header(default=None),
):
    """Non-streaming wrapper for clients that cannot consume SSE reliably.

    This endpoint intentionally reuses the first-party AgentExecutor instead of
    any external gateway. It collects token events into one reply and returns
    the durable conversation/message ids written by the executor.

    长回合(> AGENT_SEND_KEEPALIVE_SECONDS)返回 chunked JSON:前导空白是保活
    字节,末尾才是完整 JSON 对象。流一旦开始,状态码已定格 200,错误改为
    body.error 字段(消费方判 error 非空 = 失败)。快回合行为与历史完全一致。
    """

    has_images = bool(req.image_base64 or req.images)
    if not req.message.strip() and not has_images and not req.file_base64:
        raise HTTPException(status_code=400, detail="消息不能为空")

    if not req.client_turn_id and _check_recent_dup(current_user.id, req.message):
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍候。（同一消息 3 秒内已发送）",
        )

    all_images, file_b64, file_nm = _validated_agent_attachments_or_400(req)

    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    # GenUI 能力协商 (与 /stream 同一解析口径): 客户端声明的 caps 透传给 executor,
    # metric_table 卡片只在声明 genui-table-v1 时发 (无 cap → 逐字节现状)。
    from app.api._client_caps import parse_client_caps

    send_caps = parse_client_caps(x_reva_client_caps)
    from app.config import settings as _send_settings
    from app.services.health_evidence.delivery import (
        requires_live_health_executor,
    )

    live_health_executor_required = requires_live_health_executor(
        req.message.strip(),
        enabled=bool(
            getattr(
                _send_settings,
                "health_evidence_runtime_enabled",
                False,
            )
        ),
        extra_context=req.extra_context,
    )

    from app.services.agent_executor import AgentExecutor

    send_run_id = f"send_{uuid.uuid4().hex[:16]}"
    send_attempt_id = f"attempt_{uuid.uuid4().hex[:16]}"
    try:
        runtime_context, runtime_managed, runtime_disposition = _admit_agent_runtime(
            db,
            run_id=send_run_id,
            attempt_id=send_attempt_id,
            user_id=current_user.id,
            conversation_id=req.conversation_id,
            client_turn_id=req.client_turn_id,
            origin="agent_send",
        )
    except Exception as exc:
        from app.services.agent_runtime import ConversationAccessError, RunBusyError

        if isinstance(exc, RunBusyError):
            raise HTTPException(
                status_code=409,
                detail="上一条消息仍在处理，请稍后重试",
            ) from exc
        if isinstance(exc, ConversationAccessError):
            raise HTTPException(status_code=404, detail="对话不存在") from exc
        raise
    if runtime_disposition == "observe":
        raise HTTPException(
            status_code=409,
            detail="该消息仍在处理中，请稍后重试",
        )
    if runtime_disposition == "replay":
        replay_response = _agent_runtime_replay_send_response(db, runtime_context)
        if replay_response is None:
            raise HTTPException(
                status_code=409,
                detail="该消息已有处理状态，请刷新对话",
            )
        return replay_response

    async def _aggregate() -> dict:
        # 可观测性 (P4): 在 usage capture 上下文内跑 executor,回合结束汇总 token/cost。
        # 与 /stream bg 路径同模式 —— 没这层 summarize_usage_capture() 恒为 None,
        # 评测就永远记不到 model/cost。fail-soft:capture 出问题绝不打死回合。
        from app.services.agent_send_meta import build_send_meta
        from app.services.llm.usage_tracker import (
            begin_usage_capture,
            clear_run_id,
            end_usage_capture,
            set_caller,
            set_run_id,
            summarize_usage_capture,
        )

        reply_parts: list[str] = []
        done_data: dict = {}
        source_message_id = None
        usage_capture_token = begin_usage_capture()
        run_id_token = set_run_id(runtime_context.run_id)
        set_caller(
            "agent.send",
            user_id=current_user.id,
            is_admin=bool(current_user.is_admin),
        )
        worker_id = f"worker_{uuid.uuid4().hex[:24]}"
        heartbeat_task = None
        try:
            initial_lease_deadline = _mark_agent_runtime_running(
                db,
                runtime_context,
                managed=runtime_managed,
                worker_id=worker_id,
            )
            owner_task = asyncio.current_task()
            if owner_task is not None and runtime_managed:
                if initial_lease_deadline is None:
                    raise RuntimeError("agent_runtime_missing_lease_deadline")
                heartbeat_task = asyncio.create_task(
                    _agent_runtime_heartbeat(
                        runtime_context,
                        managed=True,
                        worker_id=worker_id,
                        owner_task=owner_task,
                        initial_lease_deadline=initial_lease_deadline,
                    )
                )
            executor = AgentExecutor(db)
            async for event in executor.run_stream(
                user_id=current_user.id,
                message=req.message.strip(),
                conversation_id=req.conversation_id,
                user_auth_token=user_token,
                images=all_images or None,
                file_base64=file_b64,
                file_name=file_nm,
                extra_context=req.extra_context,
                channel=req.channel,
                client_turn_id=req.client_turn_id,
                client_caps=send_caps,
                client_time_context=(
                    req.client_time_context.model_dump(exclude_none=True)
                    if req.client_time_context else None
                ),
                run_id=runtime_context.run_id,
                attempt_id=runtime_context.attempt_id,
                runtime_managed=runtime_managed,
                runtime_write_block_reason=(
                    runtime_context.control_reason
                    if runtime_context.control_reason
                    in {"circuit_paused", "circuit_unavailable"}
                    else None
                ),
            ):
                if event.get("event") == "request_persisted":
                    persisted_data = event.get("data")
                    if isinstance(persisted_data, dict):
                        source_message_id = _bind_agent_runtime_request(
                            db,
                            runtime_context,
                            managed=runtime_managed,
                            event_data=persisted_data,
                        )
                elif event.get("event") == "token":
                    content = event.get("data", {}).get("content")
                    if isinstance(content, str):
                        reply_parts.append(content)
                elif event.get("event") == "done":
                    data = event.get("data")
                    if isinstance(data, dict):
                        done_data = data
                elif event.get("event") == "error":
                    data = event.get("data") if isinstance(event.get("data"), dict) else {}
                    raise _AgentTurnError(safe_llm_error_message(data.get("message")))
            if not done_data:
                raise _AgentTurnError("Agent 未返回完成状态")
            done_data.setdefault("run_id", runtime_context.run_id)
            done_data.setdefault("attempt_id", runtime_context.attempt_id)
            _finalize_agent_runtime(
                db,
                runtime_context,
                managed=runtime_managed,
                done_data=done_data,
                source_message_id=source_message_id,
            )
            if done_data.get("request_persisted") is False:
                raise HTTPException(
                    status_code=503,
                    detail="Agent 请求未被持久化，请重试",
                )
            if done_data.get("completion_status") == "interrupted":
                raise HTTPException(
                    status_code=503,
                    detail="Agent 请求已保存但尚未完成，请稍后重试",
                )

            # summarize 必须在 capture 上下文仍活着时取(end 之后 contextvar 被重置)。
            usage_summary = None
            try:
                usage_summary = summarize_usage_capture()
            except Exception:  # noqa: BLE001 — 可观测性附加项,失败不影响回合
                usage_summary = None
            meta = build_send_meta(done_data, usage_summary)

            # 转后异步: 从本回合用户消息抽生活事件时间线 (旁路, 失败不影响返回)。
            _dispatch_life_event_extraction(
                db,
                current_user.id,
                done_data.get("conversation_id"),
                done_data.get("message_id"),
            )

            return {
                "reply": "".join(reply_parts),
                "conversation_id": done_data.get("conversation_id"),
                "message_id": done_data.get("message_id"),
                "mode": "agent",
                "elapsed_ms": done_data.get("elapsed_ms"),
                "run_id": runtime_context.run_id,
                "attempt_id": runtime_context.attempt_id,
                # 纯附加:老客户端不读 meta 不受影响。
                "meta": meta,
            }
        except asyncio.CancelledError:
            _interrupt_agent_runtime(
                db,
                runtime_context,
                managed=runtime_managed,
            )
            raise
        except Exception:
            _fail_agent_runtime_safely(
                db,
                runtime_context,
                managed=runtime_managed,
                error_code="executor_exception",
            )
            raise
        finally:
            if heartbeat_task is not None:
                await _stop_agent_runtime_heartbeat(
                    heartbeat_task,
                    run_id=runtime_context.run_id,
                )
            try:
                end_usage_capture(usage_capture_token)
            except Exception:  # noqa: BLE001
                pass
            try:
                clear_run_id(run_id_token)
            except Exception:  # noqa: BLE001
                pass
            _release_agent_capacity_safely(
                db,
                lease_id=capacity_lease_id,
                user_id=current_user.id,
            )

    # Starter pregen serve (rank7): non-streaming twin of the /stream hook. An exact
    # match to a still-FRESH pregen'd starter returns its stored answer instantly
    # (fail-CLOSED on staleness → falls through to the live executor below). Text-only.
    from app.config import settings as _pregen_settings

    if (
        getattr(_pregen_settings, "starter_pregen_enabled", False)
        and not live_health_executor_required
        and not has_images
        and not file_b64
    ):
        try:
            from app.services import starter_pregen

            pregen_hit = starter_pregen.try_serve(
                db, current_user.id, req.message.strip(),
                conversation_id=req.conversation_id, client_turn_id=req.client_turn_id,
            )
        except Exception as e:  # noqa: BLE001 — never break /send; fall through to live
            logger.warning("[agent.send] pregen serve failed, fall through: %s", e)
            pregen_hit = None
        if pregen_hit is not None:
            _pe, _pconv, _pmsg, _preply = pregen_hit
            logger.info(
                "[agent.send] pregen serve hit user=%s conv=%s msg_id=%s",
                current_user.id, _pconv, _pmsg,
            )
            _finalize_agent_runtime_events(
                db,
                runtime_context,
                managed=runtime_managed,
                events=_pe,
            )
            return {
                "reply": _preply,
                "conversation_id": _pconv,
                "message_id": _pmsg,
                "mode": "agent",
                "elapsed_ms": 0,
                "run_id": runtime_context.run_id,
                "attempt_id": runtime_context.attempt_id,
                "meta": {"pregen_served": True},
            }

    try:
        capacity_lease_id = _reserve_agent_capacity(
            db,
            user_id=current_user.id,
            origin="agent_send",
        )
    except Exception:
        _fail_agent_runtime_safely(
            db,
            runtime_context,
            managed=runtime_managed,
            error_code="capacity_unavailable",
            retryable=True,
        )
        raise
    agg_task = asyncio.create_task(_aggregate())
    _register_agent_runtime_task(runtime_context.run_id, agg_task)

    # 快窗:绝大多数回合在这里完成,走历史非流式路径 + 原状态码语义。
    finished, _ = await asyncio.wait({agg_task}, timeout=AGENT_SEND_KEEPALIVE_SECONDS)
    if finished:
        try:
            return agg_task.result()
        except _AgentTurnError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("[agent.send] failed: %s", e)
            raise HTTPException(status_code=500, detail=safe_llm_error_message(str(e))) from e

    started_at = time.monotonic()

    async def _keepalive_body():
        try:
            while True:
                if time.monotonic() - started_at > AGENT_SEND_HARD_CAP_SECONDS:
                    logger.error(
                        "[agent.send] turn exceeded hard cap %.0fs, cancelling",
                        AGENT_SEND_HARD_CAP_SECONDS,
                    )
                    agg_task.cancel()
                    try:
                        await agg_task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001 — 只等 unwind 完成
                        pass
                    yield json.dumps(
                        _send_error_envelope("请求处理超时，请稍后重试"),
                        ensure_ascii=False,
                    )
                    return
                done_set, _ = await asyncio.wait(
                    {agg_task}, timeout=AGENT_SEND_KEEPALIVE_SECONDS
                )
                if not done_set:
                    yield " "  # JSON 合法前导空白 → 三层 idle 计时器全部重置
                    continue
                try:
                    payload = agg_task.result()
                except _AgentTurnError as e:
                    payload = _send_error_envelope(str(e))
                except HTTPException as e:
                    payload = _send_error_envelope(str(e.detail))
                except Exception as e:  # noqa: BLE001
                    logger.exception("[agent.send] streaming turn failed: %s", e)
                    payload = _send_error_envelope(safe_llm_error_message(str(e)))
                yield json.dumps(payload, ensure_ascii=False)
                return
        finally:
            if not agg_task.done():
                # 客户端断开:与历史行为一致(整请求被杀),取消回合,
                # 不留孤儿任务占用请求级 db session。
                agg_task.cancel()
                try:
                    await agg_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    return StreamingResponse(
        _keepalive_body(),
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache",
            # nginx 不缓冲:保活字节必须实时到达客户端才能重置其 idle 计时器
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", summary="统一健康助理对话列表")
async def list_conversations(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, description="分页偏移(翻页用)"),
    title_like: Optional[str] = Query(None, description="按标题模糊过滤(旧参数,仅标题)"),
    search: Optional[str] = Query(None, description="按标题和消息内容搜索"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """List current user's Agent conversations (paginated).

    返回 {items, total, limit, offset} —— 前端历史记录用 offset 做上一页/下一页翻页。
    `search` 同时匹配标题与消息正文;`title_like` 保留旧的仅标题过滤。
    AgentExecutor persists conversations through AgentConversationService so mobile/web
    can resume interrupted streams from the same durable message store.
    """
    from sqlalchemy import func
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_conversation_service import AgentConversationService

    service = AgentConversationService(db)
    total = service.count_conversations(current_user.id, title_like=title_like, search=search)
    convs = service.get_conversations(
        current_user.id, limit, title_like=title_like, offset=offset, search=search
    )
    conv_ids = [c.id for c in convs]
    last_msgs = {}
    if conv_ids:
        subq = (
            db.query(
                AgentMessage.conversation_id,
                func.max(AgentMessage.id).label("max_id"),
            )
            .filter(
                AgentMessage.conversation_id.in_(conv_ids),
                AgentMessage.role == "user",
            )
            .group_by(AgentMessage.conversation_id)
            .subquery()
        )
        rows = (
            db.query(AgentMessage.conversation_id, AgentMessage.content)
            .join(subq, AgentMessage.id == subq.c.max_id)
            .all()
        )
        last_msgs = {r[0]: (r[1] or "")[:80] for r in rows}

    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "last_message": last_msgs.get(c.id),
                "created_at": str(c.created_at),
                "updated_at": str(c.updated_at),
                "mode": "agent",
            }
            for c in convs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/conversations/{conversation_id}", summary="统一健康助理对话详情")
async def get_conversation(
    conversation_id: int,
    days: Optional[int] = Query(None, ge=1, le=365, description="只返回最近 N 天的消息"),
    limit: Optional[int] = Query(None, ge=1, le=200, description="按消息 ID 取最近一页"),
    before_message_id: Optional[int] = Query(None, ge=1, description="只返回此消息 ID 之前的数据"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.models.agent_conversation import AgentConversation, AgentMessage

    conv = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    total_messages = (
        db.query(func.count(AgentMessage.id))
        .filter(AgentMessage.conversation_id == conversation_id)
        .scalar()
        or 0
    )
    message_query = db.query(AgentMessage).filter(
        AgentMessage.conversation_id == conversation_id,
    )
    if days is not None:
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        message_query = message_query.filter(AgentMessage.created_at >= cutoff)
    if before_message_id is not None:
        message_query = message_query.filter(AgentMessage.id < before_message_id)

    has_more = False
    if limit is not None:
        descending = (
            message_query
            .order_by(AgentMessage.id.desc())
            .limit(limit + 1)
            .all()
        )
        has_more = len(descending) > limit
        msgs = list(reversed(descending[:limit]))
    else:
        msgs = message_query.order_by(AgentMessage.id.asc()).all()

    from app.services.chat_utils import refresh_chat_image_url_value
    from app.services.dynamic_card_persistence import message_metas_for_delivery

    delivered_metas = message_metas_for_delivery(
        db,
        [getattr(message, "meta", None) for message in msgs],
        current_user.id,
    )

    from app.services.health_evidence.delivery import (
        project_persisted_health_messages,
    )

    initial_source_query = None
    if msgs and msgs[0].role == "assistant":
        previous_user = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.conversation_id == conversation_id,
                AgentMessage.role == "user",
                AgentMessage.id < msgs[0].id,
            )
            .order_by(AgentMessage.id.desc())
            .first()
        )
        if previous_user is not None:
            initial_source_query = str(previous_user.content or "")

    projected_messages = project_persisted_health_messages(
        [
            {
                "role": message.role,
                "content": message.content,
                "meta": delivered_metas[index],
            }
            for index, message in enumerate(msgs)
        ],
        initial_source_query=initial_source_query,
    )
    delivered_messages = []
    for message, projection in zip(
        msgs,
        projected_messages,
        strict=True,
    ):
        delivered_messages.append(
            {
                "id": message.id,
                "role": message.role,
                "content": projection.content,
                "image_url": refresh_chat_image_url_value(
                    message.image_url,
                    current_user.id,
                ),
                "rating": message.rating,
                "created_at": str(message.created_at),
                "meta": projection.meta,
            }
        )

    return {
        "id": conv.id,
        "title": conv.title,
        "total_messages": total_messages,
        "has_more": has_more,
        "oldest_message_id": msgs[0].id if msgs else None,
        "mode": "agent",
        "messages": delivered_messages,
    }

@router.delete("/conversations/{conversation_id}", summary="删除统一健康助理对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.agent_conversation_service import AgentConversationService

    service = AgentConversationService(db)
    ok = service.delete_conversation(current_user.id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}


@router.patch("/conversations/{conversation_id}", summary="重命名统一健康助理对话")
async def update_conversation_title(
    conversation_id: int,
    body: ConversationTitleUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.agent_conversation_service import AgentConversationService

    service = AgentConversationService(db)
    try:
        conv = service.update_conversation_title(current_user.id, conversation_id, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "updated_at": str(conv.updated_at),
        "mode": "agent",
    }


@router.post("/messages/{message_id}/rate", summary="评价统一健康助理消息")
async def rate_agent_message(
    message_id: int,
    payload: dict,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    rating = payload.get("rating")
    if rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating must be 1 or -1")

    from app.models.agent_conversation import AgentConversation, AgentMessage

    msg = (
        db.query(AgentMessage)
        .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
        .filter(
            AgentMessage.id == message_id,
            AgentConversation.user_id == current_user.id,
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在")
    msg.rating = None if msg.rating == rating else rating
    db.commit()
    return {"ok": True, "rating": msg.rating}


@router.get("/conversation-opener", summary="Chat 起手未读续接 — AI 主动开场白")
def conversation_opener(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    返回 AI 主动续接上次话题的开场白. 前端 chat tab mount 时拉这个,
    用来替代/前置 SUGGESTIONS chip.

    Returns:
        - 200 OK: 有 opener 信号 — { opener: { text, source, source_id?, quick_replies, deep_link?, priority } }
        - 200 OK: 无信号 — { opener: null }  (前端退化到默认 SUGGESTIONS)

    Never raises — 错误时返回 { opener: null }, 静默退化, 不影响 chat 启动.
    """
    from dataclasses import asdict
    from app.services.conversation_opener import compute_conversation_opener

    try:
        opener = compute_conversation_opener(db, current_user.id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[conversation_opener] endpoint bypass: {e}")
        opener = None

    return {"opener": asdict(opener) if opener else None}


@router.get("/conversation-starters", summary="新对话页 prompts — 动态建议 chip")
def conversation_starters(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return dynamic prompt chips for the new-chat empty state.

    This endpoint is fail-soft: it never raises (except auth) and falls back to
    stable defaults on any internal error.

    Cold-start (C1 contract): a zero-signal user additionally gets a top-level
    `onboarding: true` and a synthesized `opener` whose `quick_replies` carry an
    `action` (photo_meal / record_weight / connect_device) for local navigation.
    Established users get neither field change (opener from the normal channel,
    no `onboarding` key) — additive and backward-compatible.

    LLM polish (progressive enhancement, flag `starter_llm_polish_enabled`):
    the RULES compute the chips; a cheap LLM optionally rewrites the wording and
    a deterministic verify gate rejects anything invented (fail-safe = rule text).
    On a cache hit we serve the polished text; on a miss we serve the RULE text
    immediately and warm the cache in a background task. Each suggestion carries
    an additive `polished: bool` so adoption is eyeball-able in logs. Flag off /
    redis down / provider error → byte-identical to the pure-rules behavior.
    """
    from dataclasses import asdict
    from app.config import settings
    from app.services.conversation_opener import (
        compute_conversation_opener,
        synthesize_cold_start_opener,
    )
    from app.services.conversation_starters import (
        compute_conversation_suggestion_cards,
        is_cold_start_user,
    )

    # Cold-start (zero-signal) users get a synthetic onboarding opener + a
    # top-level `onboarding: true` flag. The determination reuses the SAME
    # zero-signal check as the onboarding chip branch (is_cold_start_user →
    # _collect_signals + _has_any_user_signal), so the flag can never disagree
    # with the chips the client renders. Established users: flag absent, opener
    # comes from the normal signal channel — byte-identical to prior behavior.
    cold_start = is_cold_start_user(db, current_user.id)

    opener = None
    if cold_start:
        opener = synthesize_cold_start_opener()
    else:
        try:
            opener = compute_conversation_opener(db, current_user.id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[conversation_starters] opener bypass: {e}")

    # Structured cards carry the generator `key` so the client can attribute
    # impressions/clicks per generator (CTR). Clients tolerate the legacy
    # plain-string shape too (see conversationOpener.ts / ai-assistant page).
    cards = compute_conversation_suggestion_cards(db, current_user.id, limit=4)

    suggestions = _resolve_starter_suggestions(
        cards, current_user.id, background_tasks, settings
    )

    # Starter answer pre-generation (rank7): off the response path, pre-warm the
    # top-N SERVED chips' answers so a later tap serves instantly. Deduped + budget
    # capped inside enqueue_pregen; default-off. The served suggestion TEXT (polished
    # if polish is on) is exactly what the client will send on tap. Fail-soft.
    if getattr(settings, "starter_pregen_enabled", False) and not cold_start:
        try:
            from app.services.starter_pregen_producer import enqueue_pregen

            auth_header = request.headers.get("authorization", "")
            starter_token = (
                auth_header[7:] if auth_header.startswith("Bearer ") else None
            )
            enqueue_pregen(
                background_tasks,
                db,
                current_user.id,
                [s.get("text", "") for s in suggestions],
                starter_token,
            )
        except Exception as e:  # noqa: BLE001 — pregen scheduling must never break starters
            logger.warning(f"[conversation_starters] pregen enqueue bypass: {e}")

    payload = {
        "opener": asdict(opener) if opener else None,
        "suggestions": suggestions,
    }
    # Additive top-level field: only present (and True) for cold-start users so
    # legacy clients that don't read it are unaffected.
    if cold_start:
        payload["onboarding"] = True
    return payload


def _resolve_starter_suggestions(cards, user_id, background_tasks, settings) -> list[dict]:
    """Apply LLM-polish overlay to rule cards, fail-safe to pure rule text.

    Returns the suggestion dicts. Every path is fail-soft: any error, a disabled
    flag, or an unavailable Redis all yield the byte-identical pure-rules shape
    (text/key/priority + polished=False).
    """
    rule_dicts = [
        {"text": c.text, "key": c.key, "priority": c.priority, "polished": False}
        for c in cards
    ]

    if not getattr(settings, "starter_llm_polish_enabled", True):
        return rule_dicts

    try:
        from app.services import starter_polish

        sig_hash = starter_polish.signals_hash(cards)
        cached = starter_polish.read_cached_polish(user_id, sig_hash)
        if cached:
            # Cache hit: serve polished. Map polished text back onto the current
            # rule cards by key so priority/ordering stay rule-authoritative, and
            # any brand-new key (e.g. synthesis) is appended.
            return _merge_cached_polish(cards, cached)

        # Cache miss: serve rule text NOW; warm the cache off the response path.
        background_tasks.add_task(
            starter_polish.warm_polish_cache, user_id, list(cards), sig_hash
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[conversation_starters] polish overlay bypass: {e}")

    return rule_dicts


def _merge_cached_polish(cards, cached: list) -> list[dict]:
    """Overlay cached polished text onto the current rule cards.

    Rule cards remain the source of truth for the display slot count. For each
    rule card, if the cache has a polished entry for its key, serve the polished
    text (+ polished flag); otherwise serve rule text. A cached synthesis item
    can replace the lowest-priority rule card only when it is more salient.
    """
    by_key = {}
    synthesis_entries = []
    for entry in cached:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "")
        if key == "synthesis" or entry.get("synthesis"):
            synthesis_entries.append(entry)
        else:
            by_key.setdefault(key, entry)

    out: list[dict] = []
    for c in cards:
        hit = by_key.get(c.key)
        if hit and hit.get("text"):
            out.append(
                {
                    "text": str(hit["text"]),
                    "key": c.key,
                    "priority": c.priority,
                    "polished": bool(hit.get("polished")),
                }
            )
        else:
            out.append(
                {"text": c.text, "key": c.key, "priority": c.priority, "polished": False}
            )

    synthesis_card = None
    for syn in synthesis_entries[:1]:  # at most one synthesis
        if syn.get("text"):
            synthesis_card = {
                "text": str(syn["text"]),
                "key": "synthesis",
                "priority": int(syn.get("priority") or 0),
                "polished": True,
                "synthesis": True,
                "combines": list(syn.get("combines") or []),
            }

    if synthesis_card and out:
        source_keys = set(synthesis_card["combines"])
        replaceable_indices = [
            index for index, item in enumerate(out) if item["key"] not in source_keys
        ]
        lowest_index = min(
            replaceable_indices,
            key=lambda index: (int(out[index]["priority"]), -index),
            default=None,
        )
        if (
            lowest_index is not None
            and synthesis_card["priority"] > out[lowest_index]["priority"]
        ):
            out[lowest_index] = synthesis_card

    out.sort(key=lambda item: int(item["priority"]), reverse=True)
    return out[:len(cards)]


@router.get("/tools", summary="列出可用工具")
def list_agent_tools(
    current_user: User = Depends(get_current_user_required),
):
    """列出 Agent 可调用的所有工具"""
    from app.services.tool_schema_registry import get_health_tools
    tools = get_health_tools()
    return {
        "tools": tools,
        "count": len(tools),
        "model": "Hermes-3 (OpenAI-compatible)",
    }


@router.get("/tasks", summary="统一任务账本 — 小巴的任务(五源只读聚合)")
def agent_tasks(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Slice 4 v1:write_intents / desktop_jobs / agenda / heartbeat / recipes
    五源只读聚合成统一 shape ``{kind, title, status, when, source}``。
    单源失败计入 ``failed_sources``(fail-loud,不整包 500);取消/重试留 v2。"""
    from app.services.task_ledger_service import build_ledger
    return build_ledger(current_user.id, db)


# ──────────────────── 程序性记忆/配方 (Harness Slice 3) ────────────────────
# 配方 = 确定性重放的工具序列;触发短语精确匹配;每步确认门原样生效。
# 见 app/services/procedure_recipe_service.py 模块 docstring 的四条不变量。


class RecipeStepPayload(BaseModel):
    tool: str
    args_template: dict


class RecipeCreatePayload(BaseModel):
    # 上限与 service 常量对齐(name 100 / phrases 5 / steps 10),错误信息一致。
    # created_from_conversation_id 不收:手建配方无来源对话;
    # save-from-conversation 端点会在 ownership 校验后正确回填(安全评审次要项)。
    name: str = Field(..., max_length=100)
    trigger_phrases: List[str] = Field(..., min_length=1, max_length=5)
    steps: List[RecipeStepPayload] = Field(..., min_length=1, max_length=10)


class RecipeSaveFromConversationPayload(BaseModel):
    name: str = Field(..., max_length=100)
    trigger_phrases: List[str] = Field(..., min_length=1, max_length=5)


@router.post("/recipes", summary="创建程序性配方")
def create_agent_recipe(
    payload: RecipeCreatePayload,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services import procedure_recipe_service as recipe_svc

    try:
        recipe = recipe_svc.create_recipe(
            db,
            current_user.id,
            name=payload.name,
            trigger_phrases=payload.trigger_phrases,
            steps=[step.model_dump() for step in payload.steps],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return recipe_svc.serialize(recipe)


@router.get("/recipes", summary="列出我的程序性配方")
def list_agent_recipes(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services import procedure_recipe_service as recipe_svc

    recipes = recipe_svc.list_recipes(db, current_user.id)
    return {"recipes": [recipe_svc.serialize(r) for r in recipes], "count": len(recipes)}


@router.delete("/recipes/{recipe_id}", summary="删除程序性配方")
def delete_agent_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services import procedure_recipe_service as recipe_svc

    if not recipe_svc.delete_recipe(db, current_user.id, recipe_id):
        raise HTTPException(status_code=404, detail="配方不存在")
    return {"deleted": True, "id": recipe_id}


@router.post(
    "/recipes/{conversation_id}/save-from-conversation",
    summary="从对话最近一轮工具序列存配方",
)
def save_agent_recipe_from_conversation(
    conversation_id: int,
    payload: RecipeSaveFromConversationPayload,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """从该对话最近一条带 recipe_candidate 的助手消息反推工具序列存为配方。

    候选步骤由 agent_executor 在「一轮完成 ≥2 个写类工具」时落到 message.meta
    (已剥 confirmed + 日期模板化);这里**不重放对话、不经 LLM**,只是把已
    持久化的确定性序列命名保存。归属校验 fail-closed:别人的对话 → 404。
    """
    from app.services import procedure_recipe_service as recipe_svc

    candidate = recipe_svc.recipe_candidate_from_conversation(
        db, current_user.id, conversation_id
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="该对话没有可保存的配方候选")
    try:
        recipe = recipe_svc.create_recipe(
            db,
            current_user.id,
            name=payload.name,
            trigger_phrases=payload.trigger_phrases,
            steps=candidate["steps"],
            created_from_conversation_id=conversation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return recipe_svc.serialize(recipe)
