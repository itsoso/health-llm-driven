"""Unified Health Agent API — 统一健康助理端点

所有对话（记录、查询、分析、图片识别）统一走此入口。
旧外部网关已下线，所有对话统一走第一方 Agent。
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional, List


from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.llm.error_messages import safe_llm_error_message

logger = logging.getLogger(__name__)

# 2026-05-14 FIX-5 (G-W9 同模式): 客户端断开后 bg task 继续跑完 LLM/tool/写库.
# set 持 task 引用防 GC; done_callback 自动清理.
_BACKGROUND_AGENT_TASKS: set = set()
router = APIRouter()


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


def _answer_owns_its_visualization(answer_text: str, tools_used: list | None) -> bool:
    """本轮 LLM 是否已自带可视化 → 该压掉冗余的关键词单日快照卡。

    信号(任一命中):① 答案含 markdown 表格(≥2 表行 + 分隔行,如"睡眠与HRV对照"表);
    ② 本轮跑过 health_analysis(深分析,正文即多段分析)。
    这两种情况下快照卡(sleep/weight/bp…)只会与更好的正文重复且常错配窗口
    (founder 截图:问"上周睡眠不好吗", 却贴今晚单晚快照)。
    直接单指标速查(答案是一句话、无表)不命中 → 快照卡照常出(卡即答案)。
    """
    text = answer_text or ""
    if _MD_TABLE_SEP_RE.search(text) and len(_MD_TABLE_RE.findall(text)) >= 2:
        return True
    if isinstance(tools_used, list) and "health_analysis" in tools_used:
        return True
    return False


def _merge_card_descriptors(*groups: list | None) -> list:
    """Merge SSE card descriptors without duplicating identical payloads."""

    out: list = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for card in group:
            if not isinstance(card, dict) or not isinstance(card.get("type"), str):
                continue
            try:
                key = json.dumps(card, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                key = f"{card.get('type')}:{len(out)}"
            if key in seen:
                continue
            seen.add(key)
            out.append(card)
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
        meta["cards"] = cards_for_persistence(
            _merge_card_descriptors(meta.get("cards"), cards)
        )
        msg.meta = meta
        db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.debug("[agent.stream] persist done cards skipped: %s", e)
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
            replay_events.append({"event": "token", "data": {"content": existing_assistant.content}})
            done_data = dict(existing_assistant.meta or {})
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
            for img in v:
                if len(img.base64) > 10_000_000:
                    raise ValueError("单张图片太大，最大支持约 7.5MB")
        return v

    @field_validator("file_base64")
    @classmethod
    def check_file_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 15_000_000:  # ~11MB file
            raise ValueError("文件太大，最大支持约 11MB")
        return v


class ConversationTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        normalized = v.strip()
        if not normalized:
            raise ValueError("标题不能为空")
        return normalized


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

    # Normalize: merge single image_base64 and images array into one list
    all_images: List[dict] = []
    if req.images:
        all_images = [{"base64": img.base64, "type": img.type} for img in req.images]
    elif req.image_base64:
        all_images = [{"base64": req.image_base64, "type": req.image_type or "jpeg"}]

    from app.services.agent_executor import AgentExecutor

    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
    user_id = current_user.id
    msg_text = req.message.strip()
    conv_id = req.conversation_id
    images_local = all_images or None
    file_b64 = req.file_base64
    file_nm = req.file_name
    extra_ctx = req.extra_context
    chan = req.channel
    client_turn_id = req.client_turn_id

    # GenUI 短路: caps=genui-v1 + 图表意图 + 无图片/附件 → 确定性出 reva-ui block,
    # 跳过 AgentExecutor/LLM (R4: 数值只来自 DB)。命中即持久化消息并直接 SSE 回放。
    # 数据不足 / 任何异常 → genui_events=None, FALL THROUGH 到普通路径 (永不断聊天)。
    from app.api._client_caps import parse_client_caps

    caps = parse_client_caps(x_reva_client_caps)
    genui_events: Optional[list[dict]] = None
    if not has_images and not file_b64:
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

    async def generate():
        """G-W9 同模式 (FIX-5, 2026-05-14): bg task + asyncio.Queue.

        客户端断开 (App 后台 30s+ / 切走页面) → 这个 generator 抛 CancelledError /
        GeneratorExit 退出, 但 bg_task 继续跑到 LLM 完成 + 把 message 写库 + audit.
        用户回到 App 后, useFocusEffect/AppState 重新拉 conversation, 看到完整回复.
        """
        chunk_queue: asyncio.Queue = asyncio.Queue()

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
            run_id = f"run_{uuid.uuid4().hex[:16]}"
            usage_capture_token = begin_usage_capture()
            run_id_token = set_run_id(run_id)
            set_caller("agent.stream", user_id=user_id)
            try:
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
                ):
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
                        event.setdefault("data", {})["run_id"] = run_id
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
                                    recorded_intake_kinds,
                                )
                                existing = done_data.get("cards")
                                inline = extract_inline_card_blocks("".join(full_text_buf))
                                # 本轮已写入的摄入类记录 → 压制同 kind 的 query 派生草稿,
                                # 防「已记录+再确认」重复写入(油桃加餐双卡实锤)。
                                # 且只要 health_record 已接手(含待确认态):对话流拥有该
                                # 任务,草稿卡的"去 X 页记录"主按钮会把用户引离"说'是的'
                                # 即完成"的确认流(实锤:打卡替普瑞酮 → 确认问句与
                                # medication_draft 双路互搏;mac 上该按钮还曾是静默死键)。
                                suppress = recorded_intake_kinds(existing, inline)
                                if "health_record" in (done_data.get("tools_used") or []):
                                    suppress = set(suppress) | {
                                        "medication", "supplement", "diet",
                                    }
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
                                logger.debug(f"inline_cards 失败: {e}")
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
                    await chunk_queue.put(f"data: {json.dumps(event, ensure_ascii=False)}\n\n")
            except Exception as e:
                logger.error(f"Agent bg 流式异常: {e}", exc_info=True)
                err = {"event": "error", "data": {"message": safe_llm_error_message(e)}}
                try:
                    await chunk_queue.put(f"data: {json.dumps(err, ensure_ascii=False)}\n\n")
                except Exception:
                    pass
            finally:
                # sentinel: 通知 generator 结束
                try:
                    await chunk_queue.put(None)
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
                try:
                    bg_db.close()
                except Exception:
                    pass

        bg_task = asyncio.create_task(_bg())
        _BACKGROUND_AGENT_TASKS.add(bg_task)
        bg_task.add_done_callback(_BACKGROUND_AGENT_TASKS.discard)

        try:
            while True:
                item = await chunk_queue.get()
                if item is None:
                    break
                yield item
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开 — bg_task 不取消, 让它跑完写完消息.
            logger.info(
                f"[agent.stream] client disconnected user={user_id}, "
                f"bg task continues to finish LLM + write message"
            )
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

    all_images: List[dict] = []
    if req.images:
        all_images = [{"base64": img.base64, "type": img.type} for img in req.images]
    elif req.image_base64:
        all_images = [{"base64": req.image_base64, "type": req.image_type or "jpeg"}]

    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    # GenUI 能力协商 (与 /stream 同一解析口径): 客户端声明的 caps 透传给 executor,
    # metric_table 卡片只在声明 genui-table-v1 时发 (无 cap → 逐字节现状)。
    from app.api._client_caps import parse_client_caps

    send_caps = parse_client_caps(x_reva_client_caps)

    from app.services.agent_executor import AgentExecutor

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
        run_id = f"send_{uuid.uuid4().hex[:16]}"
        usage_capture_token = begin_usage_capture()
        run_id_token = set_run_id(run_id)
        set_caller("agent.send", user_id=current_user.id)
        try:
            executor = AgentExecutor(db)
            async for event in executor.run_stream(
                user_id=current_user.id,
                message=req.message.strip(),
                conversation_id=req.conversation_id,
                user_auth_token=user_token,
                images=all_images or None,
                file_base64=req.file_base64,
                file_name=req.file_name,
                extra_context=req.extra_context,
                channel=req.channel,
                client_turn_id=req.client_turn_id,
                client_caps=send_caps,
                client_time_context=(
                    req.client_time_context.model_dump(exclude_none=True)
                    if req.client_time_context else None
                ),
            ):
                if event.get("event") == "token":
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
                # 纯附加:老客户端不读 meta 不受影响。
                "meta": meta,
            }
        finally:
            try:
                end_usage_capture(usage_capture_token)
            except Exception:  # noqa: BLE001
                pass
            try:
                clear_run_id(run_id_token)
            except Exception:  # noqa: BLE001
                pass

    # Starter pregen serve (rank7): non-streaming twin of the /stream hook. An exact
    # match to a still-FRESH pregen'd starter returns its stored answer instantly
    # (fail-CLOSED on staleness → falls through to the live executor below). Text-only.
    from app.config import settings as _pregen_settings

    if (
        getattr(_pregen_settings, "starter_pregen_enabled", False)
        and not has_images
        and not req.file_base64
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
            return {
                "reply": _preply,
                "conversation_id": _pconv,
                "message_id": _pmsg,
                "mode": "agent",
                "elapsed_ms": 0,
                "meta": {"pregen_served": True},
            }

    agg_task = asyncio.create_task(_aggregate())

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
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.agent_conversation_service import AgentConversationService

    service = AgentConversationService(db)
    conv = service.get_conversation_detail(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    msgs = conv.messages
    total_messages = len(msgs)
    if days is not None:
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        msgs = [m for m in msgs if m.created_at and _msg_dt(m.created_at) >= cutoff]

    from app.services.chat_utils import refresh_chat_image_url_value

    return {
        "id": conv.id,
        "title": conv.title,
        "total_messages": total_messages,
        "mode": "agent",
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "image_url": refresh_chat_image_url_value(m.image_url, current_user.id),
                "rating": m.rating,
                "created_at": str(m.created_at),
                "meta": getattr(m, "meta", None),
            }
            for m in msgs
        ],
    }


def _msg_dt(value):
    """Normalize SQLite naive / PostgreSQL aware timestamps to aware UTC."""
    from datetime import datetime, timezone

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc) if value else datetime.now(timezone.utc)


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
