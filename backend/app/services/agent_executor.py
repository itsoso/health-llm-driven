"""统一健康 Agent 执行器 — 结构化工具调用 + 多步推理循环

所有对话（记录、查询、分析、图片识别）统一走此入口。

流程：
  1. 注入健康上下文 + tool schemas
  2. 调用 LLM（OpenAI 兼容）
  3. 解析 tool_call → 执行 Health API
  4. 将 tool_result 返回模型 → 循环直到无更多 tool_call
  5. 最终回答通过 SSE 流式输出
"""
import ast
import asyncio
import base64
from dataclasses import replace
import hashlib
import json
import logging
import math
import re
import time
from datetime import UTC, date, datetime, time as datetime_time, timezone, timedelta
from typing import AsyncGenerator, Collection, Dict, Any, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.tool_schema_registry import (
    ANALYSIS_TURN_TOOL_NAMES,
    FAST_READ_TURN_TOOL_NAMES,
    FAST_TURN_TOOL_NAMES,
    get_health_tools,
)
from app.services.lab_plausibility import annotate_if_implausible
from app.services.llm.error_messages import safe_llm_error_message, safe_tool_error_message
from app.services.health_query_dimensions import normalize_health_query_args
from app.services.post_record_quality import (
    build_diet_adjust_action,
    build_post_record_quality_response,
    combine_post_record_quality_responses,
)
from app.services.agent_turn_recovery import (
    is_data_insufficiency_response,
    is_model_scope_refusal,
    is_safety_boundary_refusal,
    should_buffer_recovery_response,
    should_retry_tool_failure,
)
from app.services.agent_turn_outcome import classify_agent_turn_outcome
from app.services.agent_turn_retry import (
    RetryableTurnRecovery,
    build_retry_source_action_if_safe,
    materialize_retryable_turn_images,
    resolve_retryable_turn_recovery,
    restore_retryable_turn_recovery,
)
from app.services.agent_write_outcome import (
    classify_explicit_write_execution,
    classify_write_execution,
    is_legacy_local_write_rejection,
    local_write_rejection,
    result_declares_explicit_failure,
    write_result_declares_non_success,
)
from app.services.dynamic_card_persistence import cards_for_persistence
from app.services.utterance_intent_classifier import classify_agent_utterance
from app.utils.number_format import format_card_numbers
from app.services.agent_kernel.context import (
    build_turn_snapshot,
    format_turn_time_context_prompt,
)
from app.services.agent_kernel.actionable_context import (
    format_actionable_context_prompt,
)
from app.services.agent_kernel.goal_spec import (
    compile_goal_spec,
    format_goal_contract_prompt,
)
from app.services.agent_kernel.postconditions import verify_goal_postconditions
from app.services.agent_kernel.events import AgentEventBus
from app.services.agent_kernel.tool_registry import (
    HEALTH_MANAGE_RECEIPT_RESOURCE_TYPE_BY_RECORD_TYPE,
    HEALTH_RECORD_RECEIPT_RESOURCE_TYPE_BY_RECORD_TYPE,
    UnknownToolAction,
    classify_tool_effect,
    expected_receipt_resource_type,
    get_tool_spec,
    is_registered_receipt_resource_type,
    is_valid_receipt_resource_id,
    list_tool_specs,
    requires_verified_receipt,
)
from app.services.agent_kernel.types import (
    CapabilityDecision,
    GoalSpec,
    ToolExecutionRequest,
    TurnSnapshot,
)

logger = logging.getLogger(__name__)


def _sha12(text: str) -> str:
    """sha256 的前 12 hex (可观测性用短指纹, 非安全哈希)。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _kernel_media_metadata(
    images: Optional[Sequence[dict[str, Any]]],
    *,
    has_file: bool,
    file_name: Optional[str],
) -> tuple[dict[str, Any], ...]:
    """Keep attachment identity in the turn envelope without retaining payload bytes."""
    items = [
        {
            "kind": "image",
            "index": index,
            "type": str(image.get("type") or "jpeg"),
        }
        for index, image in enumerate(images or ())
        if isinstance(image, dict)
    ]
    if has_file:
        items.append({
            "kind": "file",
            "name": str(file_name or "attachment")[:160],
        })
    return tuple(items)


def _stringify_message_content(content: Any) -> str:
    """把一条消息的 content 稳定序列化成字符串 (字符串原样;list/dict → 排序 JSON)。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        return str(content)


def _prompt_prefix_signature(messages: List[Dict]) -> Dict[str, Any]:
    """内容无泄漏的前缀可观测性 (Phase-2 rank3 第0步)。

    对本次 LLM 调用取:
      - system_hash: 所有 system 消息 content 拼接的 sha12;
      - prefix_hash: **最后一条 user 之前**的 messages 序列 (含角色/工具调用) 的 sha12
        —— 这段是 provider 前缀缓存想命中的稳定前缀 (turn 内容落在最后一条 user 尾部);
      - prefix_chars / total_chars / approx_tokens: token-ish 长度。
    只出 hash 不出内容, 用来从 journalctl 量测跨轮/跨回合前缀分歧, 给显式缓存 (rank3)
    定 marker 布局。纯函数, 可单测。"""
    system_blob = "\n".join(
        _stringify_message_content(m.get("content"))
        for m in messages
        if m.get("role") == "system"
    )
    last_user_idx = -1
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            last_user_idx = i
    prefix_msgs = messages[:last_user_idx] if last_user_idx >= 0 else list(messages)
    prefix_blob = json.dumps(prefix_msgs, ensure_ascii=False, sort_keys=True, default=str)
    total_chars = sum(
        len(_stringify_message_content(m.get("content"))) for m in messages
    )
    return {
        "system_hash": _sha12(system_blob),
        "prefix_hash": _sha12(prefix_blob),
        "prefix_chars": len(prefix_blob),
        "total_chars": total_chars,
        "approx_tokens": total_chars // 4,
    }


MAX_TOOL_ROUNDS = 8

# 整轮快路由(_fast_route_simple_turn)的**逃生门**:弱模型转不出来就别让它转满 MAX_TOOL_ROUNDS。
# 生产实锤(2026-07-17, founder user=3):全天最慢的 4 个回合**全是最简单的记录、全在快路由上**,
# 全部 rounds=9(= 打满 MAX_TOOL_ROUNDS 后还多一轮收尾):
#   「记录刚才打了一个喷嚏。」total=203s · 「今天我吃了那些胃药。」total=140s
# 分布:qwen3.6-flash p50=8.9s(快路由的真收益,别撤)但 p90=41s / **max=203s**,
# 比强模型(qwen3.7-max)的 max=119s 还差 1.7 倍 —— 问题只在**尾部**,故只砍尾部。
# 语义:用掉这么多轮还没收敛 = 弱模型这题做不出来,换强模型跑完剩下的轮,别陪它空转。
FAST_ROUTE_ESCALATE_AFTER_ROUNDS = 2

# Wave 2(2026-07-14):慢工具执行的心跳 + per-tool 超时预算。
# 病灶:慢工具(health_analysis 走 orchestrator、knowledge_search 走 ChromaDB 等)内联
# await 期间 SSE 流零事件 → nginx idle read-timeout 可掐断连接 + 用户看冻结转圈。
# 对策:执行期间每 _TOOL_HEARTBEAT_INTERVAL_S 吐一个 status 心跳(保活 + 进度可见),
# 并施加 per-tool 超时(< 客户端 xhr 300s;写工具 <2s 完成不会触及)。超时 → fail-loud
# 结果串(绝不 hang/静默)。默认 90s 与 httpx 客户端超时对齐(避免过早取消写);
# health_analysis 走进程内 orchestrator(自有 120s wait_for),给 135s 让内层先 fail-loud。
_TOOL_HEARTBEAT_INTERVAL_S = 5.0
_TOOL_TIMEOUT_DEFAULT_S = 90.0
_TOOL_TIMEOUT_OVERRIDES: Dict[str, float] = {
    spec.name: spec.timeout_seconds
    for spec in list_tool_specs()
    if spec.timeout_seconds != _TOOL_TIMEOUT_DEFAULT_S
}

# 最终用户回复的 token 上限。健康养护/操作清单类回复常 >4000 token,
# 旧值 4000 会把 Opus 4.7 的长回复硬截断(用户需手动点"继续")。
# Opus 4.7 / GPT-5.5 / Gemini 3.1 均支持远高于此, 8000 覆盖绝大多数长方案。
ANSWER_MAX_TOKENS = 8000
# 快路由回合 (简单记录/查询) 的答案 token 上限。简单回合的答案 (已记录/几步/多少毫升)
# 从不需要 8000, 长尾解码本身就是延迟的一部分 —— 只对 fast-routed turn 收紧到 2000,
# 其它一切 (建议/分析/复盘/长方案) 仍用 ANSWER_MAX_TOKENS。
FAST_ROUTE_ANSWER_MAX_TOKENS = 2000
CLIENT_TURN_REPLAY_WAIT_SECONDS = 5.0
INTERRUPTED_COMPLETION_NOTICE = "\n\n[回复因长度限制中断，请让我接着上文继续。]"
AGENT_MODEL = "NousResearch/Hermes-3-Llama-3.1-8B"
BEIJING_TZ = timezone(timedelta(hours=8))


def _weekday_cn(dt: datetime) -> str:
    names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
    return names[dt.weekday()]


def _period_cn(hour: int) -> str:
    if 5 <= hour < 9:
        return "早晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚上"
    return "夜间"


def _user_timezone_label(tz: timezone) -> str:
    key = getattr(tz, "key", None)
    if isinstance(key, str) and key:
        return key
    try:
        if tz.utcoffset(datetime.now(UTC)) == timedelta(hours=8):
            return "Asia/Shanghai"
    except Exception:  # noqa: BLE001
        pass
    return str(tz)


def _build_turn_time_context_prompt(
    db: Session,
    user_id: int,
    *,
    client_time_context: Optional[Dict[str, Any]] = None,
    now_utc: Optional[datetime] = None,
) -> str:
    """Build deterministic current-time context for one Agent turn.

    This is turn-scoped, not system-prompt-scoped: exact timestamps change on
    every request, so injecting them into the final user message preserves the
    stable provider prefix while preventing the model from guessing "now".
    """

    snapshot = build_turn_snapshot(
        db,
        user_id=user_id,
        channel="chat",
        text="",
        client_time_context=client_time_context,
        now_utc=now_utc,
    )
    return format_turn_time_context_prompt(
        snapshot.context,
        client_time_context=client_time_context,
    )


def _truncate_for_display(text: str) -> str:
    """把给 LLM 当上下文的长文本做"显示截断"(list 取前 10 / dict 内 list 各取前 10 /
    兜底字符截断)。

    **单一真源**:HTTP 读路径(`_api_get`)与 D1 进程内读路径共用此函数,保证两路截断行为
    逐字节一致 —— D1 迁移是纯 transport 变更,LLM 所见绝不因换传输而漂移。≤3000 字符原样返回。
    """
    if len(text) <= 3000:
        return text
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and len(parsed) > 10:
            parsed = parsed[:10]
            return json.dumps(parsed, ensure_ascii=False, default=str) + "\n...(仅显示前10条)"
        elif isinstance(parsed, dict):
            for k, v in parsed.items():
                if isinstance(v, list) and len(v) > 10:
                    parsed[k] = v[:10]
            truncated = json.dumps(parsed, ensure_ascii=False, default=str)
            if len(truncated) > 4000:
                truncated = truncated[:4000] + "...}"
            return truncated
    except Exception:  # noqa: BLE001 — 非 JSON / 解析失败 → 字符截断兜底
        pass
    return text[:3000] + "\n...(数据已截断)"
COMPACT_EMPTY_RETRY_SYSTEM_CHAR_LIMIT = 760
SAFETY_CARD_BOUNDARY = "这不是诊断；如出现急性不适或持续症状，请及时就医。"
SAFETY_WARNING_MARKER = "\n\n⚠️ 安全提示:"


# ──── 多模型综合分析 (参考 browser-llm-driven / LangBridge 平台) ────
# 商用三强 panel: lead 跑一遍带工具的完整回合 (查询/记录只执行一次, 不重写),
# 另两个在同一上下文上各出独立分析, 再由 lead 模型综合成一份报告。
MULTI_MODEL_PANEL: list[tuple[str, str]] = [
    ("claude-opus-4.7", "Claude Opus 4.7"),
    ("gpt-5.5", "GPT-5.5"),
    ("gemini-3.1-pro", "Gemini 3.1 Pro"),
]
MULTI_MODEL_LEAD_ID = "claude-opus-4.7"
MULTI_MODEL_SYNTH_ID = "claude-opus-4.7"
MULTI_MODEL_MAX_LEAD_ROUNDS = 6


def _extract_multi_model_flag(extra_context: Optional[str]) -> bool:
    """Mac「默认 3 个」模式在 extra_context 里带 {"multi_model": true}。"""
    if not extra_context:
        return False
    try:
        payload = json.loads(extra_context)
    except Exception:
        return False
    return bool(isinstance(payload, dict) and payload.get("multi_model"))


def _is_diet_photo_auto_save_turn(extra_context: Optional[str], *, has_images: bool) -> bool:
    """识别 Mobile 明确发起的拍照记餐动作，允许识别后直接保存。"""
    if not has_images or not extra_context:
        return False
    try:
        payload = json.loads(extra_context)
    except Exception:
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("source") == "mobile_chat_meal_photo"
        and payload.get("intent") == "diet_photo_record"
    )


def _gathered_data_context(messages: List[Dict[str, Any]], limit: int = 6000) -> str:
    """从 lead 回合的 messages 里抽出工具结果文本, 作为给其它模型的共享数据上下文。"""
    chunks: list[str] = []
    for m in messages:
        if m.get("role") == "tool" and m.get("content"):
            chunks.append(str(m["content"]).strip())
    return "\n\n".join(c for c in chunks if c)[:limit]


def _build_multi_model_synthesis_prompt(question: str, analyses: List[tuple[str, str]]) -> str:
    """综合 prompt: 把各模型的独立分析合成一份「共识 / 各家补充 / 分歧」报告。"""
    blocks = "\n\n".join(
        f"【{label}】\n{(text or '').strip()}"
        for label, text in analyses
        if text and text.strip()
    )
    return (
        f"用户的健康问题：{question}\n\n"
        f"以下是多个模型对该问题各自独立给出的分析：\n\n{blocks}\n\n"
        "请综合这几份分析，输出一份结构化中文报告：\n"
        "1. **共识结论** —— 几方一致认同的要点；\n"
        "2. **各模型补充** —— 每个模型独有且有价值的观点（标注来自哪个模型）；\n"
        "3. **分歧与不确定性** —— 观点不一致或证据不足之处，说明你更倾向哪种及理由。\n"
        "只基于上述分析与已知健康数据，不要编造数据。"
    )


def _extract_model_id_from_extra_context(extra_context: Optional[str]) -> Optional[str]:
    """Return a safe per-request model id from Mac/mobile extra context."""

    if not extra_context:
        return None
    try:
        payload = json.loads(extra_context)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    model_id = payload.get("model_id")
    if not isinstance(model_id, str):
        return None
    model_id = model_id.strip()
    if not model_id:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,120}", model_id):
        return None
    try:
        from app.services.llm import model_registry

        if model_registry.get_model(model_id):
            return model_id
        for entry in model_registry.MODELS:
            if entry.model == model_id:
                return entry.id
    except Exception:  # noqa: BLE001
        pass
    return model_id


def _extract_desktop_response_instruction(extra_context: Optional[str]) -> Optional[str]:
    """Return explicit desktop response formatting instructions from extra context."""

    if not extra_context:
        return None
    try:
        payload = json.loads(extra_context)
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("client") != "mac":
        return None
    instruction = payload.get("desktop_markdown_response_instruction")
    if not isinstance(instruction, str):
        return None
    instruction = instruction.strip()
    if not instruction:
        return None
    return instruction[:1200]


def _extract_database_verification_instruction(extra_context: Optional[str]) -> Optional[str]:
    """Return a hard turn instruction for mobile contexts that require DB verification."""

    if not extra_context:
        return None
    try:
        payload = json.loads(extra_context)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    verification = payload.get("database_verification")
    if not isinstance(verification, dict) or verification.get("required") is not True:
        return None
    if verification.get("query_scope") != "daily_diet_records":
        return None
    if verification.get("totals_source") != "database":
        return None

    raw_date = verification.get("date")
    date_text = raw_date.strip() if isinstance(raw_date, str) else ""
    if date_text and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        date_text = ""

    raw_record_id = verification.get("verify_record_id")
    try:
        record_id = int(raw_record_id)
    except (TypeError, ValueError):
        record_id = 0
    if record_id <= 0:
        return None

    missing_instruction = verification.get("missing_record_instruction")
    if not isinstance(missing_instruction, str) or not missing_instruction.strip():
        missing_instruction = "如果数据库里查不到该记录，明确提示同步失败，不要根据入口上下文猜测。"
    missing_instruction = missing_instruction.strip()[:300]

    date_clause = f"，日期限定为 {date_text}" if date_text else ""
    return (
        "## 数据库校验要求（最高优先级）\n"
        "本回合来自饮食确认后的复盘入口。回答前必须先调用 "
        "health_query(dimension='diet') 查询数据库中的饮食记录"
        f"{date_clause}，并核对结果里是否包含 diet_record id={record_id}。\n"
        "- 不要使用入口上下文里的 totals、meals 或 cached totals 作为全天饮食/热量依据；\n"
        "- 全天热量、餐次列表和下一餐建议只能基于 health_query 返回的数据库结果；\n"
        f"- {missing_instruction}"
    )


def _format_diet_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _build_database_verification_snapshot(
    db: Session,
    user_id: int,
    extra_context: Optional[str],
) -> Optional[str]:
    """Build deterministic DB facts for post-confirm diet review turns."""

    if not extra_context:
        return None
    try:
        payload = json.loads(extra_context)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    verification = payload.get("database_verification")
    if not isinstance(verification, dict) or verification.get("required") is not True:
        return None
    if verification.get("query_scope") != "daily_diet_records":
        return None
    if verification.get("totals_source") != "database":
        return None

    raw_date = verification.get("date")
    if not isinstance(raw_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date.strip()):
        return None
    target_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date()

    try:
        verify_record_id = int(verification.get("verify_record_id"))
    except (TypeError, ValueError):
        return None
    if verify_record_id <= 0:
        return None

    from app.models.daily_health import DietRecord

    records = (
        db.query(DietRecord)
        .filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == target_date,
        )
        .order_by(DietRecord.created_at, DietRecord.id)
        .all()
    )
    total_calories = sum(record.calories or 0 for record in records)
    total_protein = sum(record.protein or 0 for record in records)
    total_carbs = sum(record.carbs or 0 for record in records)
    total_fat = sum(record.fat or 0 for record in records)
    total_fiber = sum(record.fiber or 0 for record in records)
    record_found = any(record.id == verify_record_id for record in records)
    meal_lines = [
        (
            f"- id={record.id} | {record.meal_type or '-'} | "
            f"{(record.food_items or record.food_name or '').strip() or '-'} | "
            f"{_format_diet_number(record.calories)} kcal | "
            f"P {_format_diet_number(record.protein)}g / "
            f"C {_format_diet_number(record.carbs)}g / "
            f"F {_format_diet_number(record.fat)}g"
        )
        for record in records[:20]
    ]
    if not meal_lines:
        meal_lines.append("- 当日数据库没有饮食记录")

    missing_note = (
        "\n- ⚠️ 同步失败: 数据库中未找到本次确认记录。请直接告诉用户同步失败，"
        "不要根据入口上下文或页面缓存回答已保存。"
        if not record_found else ""
    )
    return (
        "## 已读取数据库饮食记录（确定性快照）\n"
        f"日期: {target_date.isoformat()}\n"
        f"verify_record_id={verify_record_id} 存在: {'yes' if record_found else 'no'}\n"
        f"餐次数量: {len(records)}\n"
        "数据库汇总: "
        f"总热量 {_format_diet_number(total_calories)} kcal; "
        f"蛋白质 {_format_diet_number(total_protein)} g; "
        f"碳水 {_format_diet_number(total_carbs)} g; "
        f"脂肪 {_format_diet_number(total_fat)} g; "
        f"膳食纤维 {_format_diet_number(total_fiber)} g\n"
        "数据库餐次:\n"
        + "\n".join(meal_lines)
        + missing_note
    )


# ── 意图专属 prompt 块门控(2026-07-11 token 优化 #5)─────────────────────
# menu_share(739 chars)只在餐食/菜单类问题有用;基因解读规则(356 chars)只在
# 基因/补剂类回合有用 —— 二者曾无条件每轮全发(占空用户 full prompt 20%)。
# fail-open:intent_query 缺失(如多模型路径未传)→ 照旧全发,行为零变化。
# 二者均非安全块(安全/R4/worldview 恒发,不进任何门控)。
_MENU_INTENT_RE = re.compile(
    r"吃啥|吃什么|吃点什么|怎么吃|菜单|食谱|餐食|餐单|早餐|午餐|晚餐|加餐|三餐|夜宵|带饭|做什么菜"
)
# 补剂/保健品也放行:补剂建议是基因解读的主要相邻流(FADS1/优势基因误判风险在此)。
_GENE_INTENT_RE = re.compile(
    r"基因|遗传|SNP|位点|rs\d+|甲基化|MTHFR|APOE|FADS|COMT|CYP|SLCO|补剂|保健品|鱼油|维生素",
    re.IGNORECASE,
)


def _wants_menu_share_block(intent_query: Optional[str]) -> bool:
    if intent_query is None:
        return True
    return bool(_MENU_INTENT_RE.search(intent_query))


def _wants_gene_rules_block(intent_query: Optional[str]) -> bool:
    if intent_query is None:
        return True
    return bool(_GENE_INTENT_RE.search(intent_query))


_GENE_RULES_PROMPT_BLOCK = (
    "## 基因解读规则（必须遵守）",
    "- 标记为[优势]的基因是保护性基因，不要误判为需要干预的风险基因",
    "- FADS1 TT = 东亚高效转化型，植物源Omega-3转化能力强，是优势基因",
    "- SOD2 AA(Ala/Ala) = MnSOD线粒体转运效率高，是优势基因",
    "- GPX1 GG = 谷胱甘肽过氧化物酶活性正常，不需要额外干预",
    "- ⚠️用药安全基因必须优先展示和警告（CYP2D6慢代谢→止痛药危险、SLCO1B1 CT→他汀肌病风险）",
    "- 补剂推荐必须交叉参考体检历史（肾结石→维D/钙谨慎、肝功异常→某些补剂禁忌）",
    "- 补剂剂量不能简单按mg数比较不同剂型（如MitoQ 5mg ≈ 线粒体内CoQ10 200-500mg）",
    "- 补剂受法规限制剂量时（如钾99mg/粒），优先推荐饮食策略而非加量",
    "",
)

_MENU_SHARE_PROMPT_BLOCK = (
    "## 菜单输出 (可分享卡片)",
    "用户问'今晚吃啥/明天早餐/给我个晚餐建议/三餐怎么吃'类问题时,",
    "在正常文字回复**之外**, 额外附一段 fenced JSON 代码块, 标识为 menu_share,",
    "前端会自动渲染成可分享给家人的卡片 (微信/朋友圈分享):",
    "",
    "```menu_share",
    "{",
    '  "title": "今晚晚餐建议",',
    '  "reason": "晚上控碳, 蛋白 50g+ 帮助 HRV 恢复",',
    '  "items": [',
    '    {"name": "鸡胸肉", "qty": "200g", "kcal": 220, "protein": 46},',
    '    {"name": "糙米饭", "qty": "150g", "kcal": 175, "carbs": 38},',
    '    {"name": "西兰花", "qty": "200g", "kcal": 70, "fiber": 5}',
    "  ],",
    '  "totals": {"kcal": 465, "protein": 52, "carbs": 48, "fat": 12},',
    '  "shopping_list": ["鸡胸肉 200g", "糙米 1 杯", "西兰花 1 颗"]',
    "}",
    "```",
    "",
    "约束:",
    "- title 必填 8 字以内 (如'今晚晚餐建议'/'明天早餐')",
    "- items 必填 3-6 个食材, 每项 name 必填, qty/kcal 尽量给",
    "- totals 给当餐总和, shopping_list 是给家人买菜的清单",
    "- 只在用户明确要餐食/菜单建议时输出, 普通营养咨询不要输出",
    "- JSON 必须 valid, 不要 trailing comma, 不要注释",
    "",
)


def _project_orchestrator_result(result: str) -> str:
    """把 /orchestrator/chat 的完整 JSON 投影成二次合成真正需要的精简形。

    2026-07-11 token 优化 #3(实测):完整返回 15,755 chars,其中 findings[] 的
    per-specialist raw/富字段占 93%,而 agent 二次合成只需要 synthesis + 每个
    specialist 的一句话概括。投影后 ~2,400 chars(-84%),同时降低弱模型把大段
    JSON 回显进正文的风险。审计/前端要看全量走 orchestrator 自己的端点,不经
    LLM 上下文。

    保留契约字段:perf(round loop 4270 行透传给 done 事件)、synthesis 原文
    (已过 advice_guard/R4)、intent、used_specialists。fail-open:解析失败
    原样返回(宁可多花 token 不丢内容)。
    """
    try:
        data = json.loads(result) if isinstance(result, str) else None
        if not isinstance(data, dict) or "synthesis" not in data:
            return result
        compact_findings = []
        for f in data.get("findings") or []:
            if not isinstance(f, dict):
                continue
            item = {
                "specialist": f.get("specialist_name"),
                "category": f.get("category"),
                "summary": f.get("summary"),
            }
            # 各 specialist 结构化 findings 只保留高信号小字段(severity/标题/行动),
            # 丢 raw / 数值明细(synthesis 已消化过它们)。
            compact_items = []
            for fi in (f.get("findings") or [])[:5]:
                if not isinstance(fi, dict):
                    continue
                kept = {
                    k: fi[k]
                    for k in ("severity", "level", "title", "name", "action", "suggestion")
                    if k in fi and isinstance(fi[k], (str, int, float))
                }
                if kept:
                    compact_items.append(kept)
            if compact_items:
                item["items"] = compact_items
            compact_findings.append(item)
        projected = {
            "synthesis": data.get("synthesis"),
            "intent": data.get("intent"),
            "used_specialists": data.get("used_specialists"),
            "findings": compact_findings,
        }
        if data.get("perf") is not None:
            projected["perf"] = data.get("perf")
        return json.dumps(projected, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — 投影失败宁可原样返回,不丢内容
        return result


def _completion_status_from_finish_reason(finish_reason: Optional[str]) -> str:
    """Map provider finish_reason to a small client-facing completion status."""
    if finish_reason == "length":
        return "interrupted"
    if finish_reason == "error":
        return "error"
    if finish_reason in ("stop", "tool_calls", "function_call"):
        return "complete"
    if not finish_reason:
        return "unknown"
    return "complete"


def _append_interrupted_notice(text: str, finish_reason: Optional[str]) -> str:
    if _completion_status_from_finish_reason(finish_reason) != "interrupted":
        return text
    if INTERRUPTED_COMPLETION_NOTICE.strip() in text:
        return text
    return f"{text.rstrip()}{INTERRUPTED_COMPLETION_NOTICE}"


def _normalize_health_query_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """容错归一 health_query 参数:别名参数名→dimension、别名值→规范 dimension、time_range→days。

    纯函数(可单测)。不认识的值原样保留(交给下游 endpoint 映射/兜底)。
    """
    return normalize_health_query_args(args)


def _infer_record_type_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """Infer health_record ``record_type`` from a *naked* record data dict.

    Some models (e.g. glm-5) ignore the tool schema and print the record's raw
    ``data`` (``{"record_date":...,"meal_type":"breakfast","food_items":...}``)
    as visible text — no ``name`` wrapper, no ``record_type``. That both leaks
    JSON to the user AND skips the write. We detect the shape by field signals
    (mirrors ``_friendly_record_confirmation``) so the caller can recover it into
    a real health_record call. Returns None when there's no confident signal —
    caller must still avoid leaking the JSON.
    """
    def has(key: str) -> bool:
        return payload.get(key) not in (None, "", [])

    # A management payload describes an operation on an existing record, not a
    # new record's data. Treating it as a naked diet record can create a
    # duplicate after an update/list tool call is printed as text.
    if (
        payload.get("record_type")
        and str(payload.get("operation") or "").strip().lower()
        in {"list", "update", "delete"}
    ):
        return None
    if has("food_items") or payload.get("meal_type"):
        return "diet"
    if has("systolic") and has("diastolic"):
        return "blood_pressure"
    if has("exercise_type"):
        return "exercise"
    if has("amount") and "drink_type" in payload:
        return "water"
    if has("description") and ("body_part" in payload or "severity" in payload):
        return "symptom"
    if has("weight"):
        return "weight"
    return None


# 括号 + Python 调用签名格式的内联工具调用:`[工具调用: name(args)]` / `[tool_call: name(args)]`。
# 弱模型(尤其经代理的)会把工具调用吐成这种自然语言标记而非结构化 tool_calls,
# 中英文冒号都见过、方括号有时缺。标记词中英文都见过(工具调用/调用工具/tool_call/
# function_call)—— 实测 Claude-Opus-4.7 经代理时吐 `[tool_call: health_record(...)]`(英文),
# 旧正则只认中文 → 既没恢复执行(记录没真写库=假装成功)又没剥离(裸 JSON 泄漏给用户)。
# 捕获 name + 括号内全部参数串,留给 `_parse_bracket_tool_args` 解析。`re.S` 让参数串可跨行。
_BRACKET_MARKER = r"(?:工具调用|调用工具|tool_call|function_call|tool call)"
# 参数串用贪婪 `.*` 抓到最后一个 `)`:食物名等带内嵌括号(如 "面条(约100g生重)")时,
# 非贪婪会在第一个 `)` 截断 → data 丢字段。贪婪 + `_split_top_level_commas` 深度跟踪能正确切。
_BRACKET_TOOL_CALL_RE = re.compile(
    rf"\[?\s*{_BRACKET_MARKER}\s*[:：]\s*(\w+)\s*\((.*)\)\s*\]?",
    re.S | re.I,
)
# 即便最终没解析出参数,也绝不能把裸标记泄漏给用户(类比 mac 端剥离 [claim:xxx])。
# 用于最终输出兜底剥离。比上面宽松:name 可缺、括号内随意(贪婪到最后一个 `)`)。
_BRACKET_TOOL_CALL_STRIP_RE = re.compile(
    rf"\[?\s*{_BRACKET_MARKER}\s*[:：].*\)\s*\]?",
    re.S | re.I,
)

# 模型偶发只吐裸 Python 风格函数签名,没有 `[工具调用:]` 标记。仅允许**整条内容**匹配且
# name 在注册工具表内时恢复;散文/教程/代码片段里的同名签名一律不执行。
_BARE_TOOL_CALL_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\((.*)\)\s*$", re.S)


def _starts_like_bare_registered_tool_call(content: str, tools: Optional[List[Dict]]) -> bool:
    """Detect a registered bare call before the closing parenthesis arrives in a stream."""
    candidate = (content or "").lstrip()
    if not candidate or "\n" in candidate:
        return False
    allowed = {
        str((tool.get("function") or {}).get("name") or "")
        for tool in (tools or [])
        if isinstance(tool, dict)
    }
    token = re.match(r"[A-Za-z_]\w*", candidate)
    if not token:
        return False
    current_name = token.group(0)
    tail = candidate[len(current_name):].lstrip()
    if tail.startswith("("):
        return current_name in allowed
    # Do not hide an ordinary English response merely because its first token is
    # `h`/`health`. Registry tool names use snake_case, so waiting for the
    # underscore still suppresses the machine call before its arguments.
    return not tail and "_" in current_name and any(
        name and name.startswith(current_name) for name in allowed
    )

# XML/`<invoke>` 格式的内联工具调用。实测 MiniMax 经代理时把工具调用吐成 Anthropic 风格
# 的 XML 标记而非结构化 tool_calls(生产实锤 2026-07-05):
#   <invoke name="health_query">
#   <parameter name="dimension">diet</parameter>
#   <parameter name="days">7</parameter>
#   </invoke>
#   </minimax:tool_call>
# 括号/JSON 两张网都漏这个格式 → 工具没执行(零数据)+ 原始 XML 语法泄漏给用户。
# 客户端还见过同一 invoke 重复两次、`</minimax:tool_call>` 悬空无开标签的变体。
# `_INVOKE_BLOCK_RE` 抓 name + 内部 <parameter> 序列;`_INVOKE_PARAM_RE` 逐个抽参数键值。
# 剥离用 `_INVOKE_STRIP_RE`(整块 <invoke>…</invoke>)+ `_MINIMAX_TAG_STRIP_RE`(孤立开/闭标签)。
_INVOKE_BLOCK_RE = re.compile(
    r"<invoke\s+name\s*=\s*[\"']([^\"']+)[\"']\s*>(.*?)</invoke\s*>",
    re.S | re.I,
)
_INVOKE_PARAM_RE = re.compile(
    r"<parameter\s+name\s*=\s*[\"']([^\"']+)[\"']\s*>(.*?)</parameter\s*>",
    re.S | re.I,
)
_INVOKE_STRIP_RE = re.compile(r"<invoke\b.*?</invoke\s*>", re.S | re.I)
# 悬空 `<minimax:tool_call>` / `</minimax:tool_call>`(含无开标签的孤立闭标签)也一并剥掉。
_MINIMAX_TAG_STRIP_RE = re.compile(r"</?\s*minimax:tool_call\s*>", re.I)

# 通用 `<tool>` 伪标签工具调用泄漏(qwen 系经代理偶发)。既非 `<invoke>` 也非
# `<minimax:tool_call>`,上面两张网都漏。生产实锤(founder 截图 2026-07-14,mac app,
# qwen3.7-max/qwen3.6-flash 工具轮),原文一字未改:
#   <tool> {"name": "health_manage", "arguments": {"record_type<tool> {"name<tool> {"name":health_manage(record_type='diet', operation='list', date='today', meal_type='breakfast')
# 特征:一个或多个 `<tool>`/`<tool_call>`/`<function_call>` 伪标签,与残缺/嵌套的 JSON
# (`{"name":`)或函数签名(`name(args)`)交织,全程只有机器语法(无自然语言散文)。
# well-formed 的 `<tool>{"name":...}` 已被 `_extract_inline_tool_call` 的 JSON 扫描恢复成真
# tool_call(先执行,content 置空),这里只处理**无法恢复**的残缺 blob 的**展示剥离**
# ——三层防御的展示兜底层,不是唯一防线(见 `_is_botched_text_tool_call` 的重提示层 +
# `_force_no_tools_synthesis` 的 fast 丢弃层)。
# 安全边界(测试锁死):
#   · 门控——`<tool>` 标签后必须**紧跟**工具调用形状(`{` / 另一个 tool 标签 / `name(`),
#     否则整段不动 → 保护文档里的 `<tool>example</tool>`;`<toolbar>`/`<toolkit>` 因
#     `\btool\b` 词边界天然不匹配。
#   · fenced ```` ``` ```` 块 / 行内 `` `code` `` span 里的 `<tool>`(即便形如工具调用)不剥
#     —— 由调用方 `_apply_outside_code_spans` / `_search_outside_code_spans` 外科豁免(镜像
#     `_leaks_tool_result_json` 的 fenced 豁免;区外真泄漏照剥。见测试 code_fence_* / inline_code_*)。
#   · JSON 对象体止于 `}` / 嵌套 `{`(→ 收在配平括号处,外层循环重入)/ `<` / CJK(`一-鿿`);
#     签名片段止于 `)` / `<` / CJK → **绝不吞后续英文或中文散文**(CJK 见 blob_then_prose_suffix,
#     英文见 blob_then_english_suffix);带引号字符串(值可含中文)整体消费。
#   · 各分支首字符互斥(`<` / `{` / 字母 / 标点集)→ 无灾难性回溯(ReDoS smoke 已验)。
_TOOL_TAG_ATOM = r"<\s*/?\s*(?:tool|tool_call|function_call)\b[^>{]{0,200}>?"
_TOOL_LEAK_QSTR = r"(?:\"[^\"<]*\"|'[^'<]*')"  # 引号串(CJK 安全,止于 `<`)
_TOOL_LEAK_TAIL = (
    r"(?:"
    + _TOOL_TAG_ATOM                                               # 更多 tool 伪标签
    + r"|\{(?:" + _TOOL_LEAK_QSTR + r"|[^{}<一-鿿])*"      # JSON 对象体(止于 }/嵌套{/`<`/CJK;} 处收尾→不吞尾随英文散文)
    + r"|[A-Za-z_][\w.]*\s*\((?:" + _TOOL_LEAK_QSTR + r"|[^)<一-鿿])*\)?"  # name(args) 签名
    + r"|[\s\"'`:,}\]=]"                                           # 零散 JSON 标点/空白
    + r")*"
)
_GENERIC_TOOL_TAG_LEAK_RE = re.compile(
    _TOOL_TAG_ATOM + r"\s*"
    + r"(?=\{|" + _TOOL_TAG_ATOM + r"|[A-Za-z_][\w.]*\s*\()"        # 门控:标签后是工具调用形状才算泄漏
    + _TOOL_LEAK_TAIL,
    re.I,
)
# 便宜预检:整段是否可能含 `<tool>`-家族泄漏(供 strip / botched 检测短路)。`<tool` 覆盖
# `<tool`/`<tool_call`,`<function_call` 单列。词边界靠上面的正则,这里只做粗筛。
def _maybe_generic_tool_tag(text: str) -> bool:
    low = (text or "").lower()
    return "<tool" in low or "<function_call" in low


# fenced ``` 块 + 行内 `code` span —— 里面的 `<tool>` 是文档/示例(讲解工具语法、贴 KB
# 片段),即便形如工具调用也**绝不**当泄漏剥。镜像 `_leaks_tool_result_json` 的 fenced 豁免,
# 但保持外科手术:只豁免代码区,区外的真泄漏照剥(见 Finding 1)。围栏块非贪婪且含闭合围栏
# → 天然防止 `_GENERIC_TOOL_TAG_LEAK_RE` "吃穿"闭合 ``` 继续吞后文散文。
_CODE_SPAN_RE = re.compile(
    r"```.*?```"        # 围栏代码块(非贪婪,含语言标注 + 闭合围栏)
    r"|``[^`]+``"       # 行内双反引号 span
    r"|`[^`\n]+`",      # 行内单反引号 span(不跨行)
    re.S,
)

# 少数代理模型会把 function calling 降级成 Python 伪代码:
# `<tool_code>print(health_record(...))</tool_code>`。完整块可在严格白名单下恢复;
# 残缺块只用于重试/展示剥离,绝不执行任意 Python。
_TOOL_CODE_BLOCK_RE = re.compile(
    r"<\s*tool_code\b[^>]*>(.*?)<\s*/\s*tool_code\s*>",
    re.I | re.S,
)
_TOOL_CODE_LEAK_RE = re.compile(
    r"<\s*tool_code\b[^>]*>.*?(?:<\s*/\s*tool_code\s*>|\Z)",
    re.I | re.S,
)


def _apply_outside_code_spans(fn, text: str) -> str:
    """只在代码区(fenced ``` / 行内 `code`)**之外**的片段跑 `fn`,代码区原样保留。"""
    if "`" not in text:
        return fn(text)
    out: List[str] = []
    last = 0
    for m in _CODE_SPAN_RE.finditer(text):
        out.append(fn(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(fn(text[last:]))
    return "".join(out)


def _search_outside_code_spans(regex: "re.Pattern", text: str) -> bool:
    """`regex` 是否在代码区外命中(代码区内的命中视为文档/示例,不算泄漏)。"""
    if "`" not in text:
        return bool(regex.search(text))
    last = 0
    for m in _CODE_SPAN_RE.finditer(text):
        if regex.search(text[last:m.start()]):
            return True
        last = m.end()
    return bool(regex.search(text[last:]))


def _matches_outside_code_spans(regex: "re.Pattern", text: str) -> List[re.Match]:
    """Return regex matches outside fenced/inline Markdown code spans."""
    if "`" not in text:
        return list(regex.finditer(text))
    matches: List[re.Match] = []
    last = 0
    for code in _CODE_SPAN_RE.finditer(text):
        matches.extend(regex.finditer(text[last:code.start()]))
        last = code.end()
    matches.extend(regex.finditer(text[last:]))
    return matches


# 流式期前缀检测:`<invoke` / `<minimax:tool_call` / `<tool` / `<tool_call` / `<function_call`
# 一出现就抑制 live 下发(逐 token 泄漏兜底 —— founder 截图正是逐 token live 泄漏)。
_XML_TOOLCALL_PREFIX_RE = re.compile(
    r"<\s*(?:invoke\b|/?\s*minimax:tool_call\b|/?\s*tool_code\b|/?\s*tool\b|/?\s*tool_call\b|/?\s*function_call\b)",
    re.I,
)

# `call {`/`<call:`/`{name:`/`{"name":` 行首前导(qwen 系经代理把工具调用写成文本的新畸形,
# founder 2026-07-14「列出饮食记录」→ `call {name: health_query, arguments:…}` 嵌套)。流式期
# 一出现行首前导就抑制 live 下发, 避免逐 token 泄漏(最终由 _strip_botched_text_tool_leak 定稿剥净)。
_TEXTCALL_LEAK_PREFIX_RE = re.compile(
    r"^\s*[<＜]?\s*(?:call\s*[{:]|<\s*call\b|\{\s*\"?name\"?\s*:)",
    re.I,
)

# Markdown 清单式工具调用:`Tool calls:\n- health_query`(无括号、无参数)。实测
# Claude-Opus-4.7 经 langbridge 代理时**偶发**(多数仍结构化)把工具调用降级成这种文本 —
# 既没结构化 tool_calls(没真执行=零数据)又把 "Tool calls:" 标记泄漏给用户。
# 区别于上面括号格式:那种带参数可解析回 tool_call;这种**没参数**,只能重提示模型用
# 结构化 function calling 重试(代理本身支持,见日志大量 has_tool_calls=True)。
# 流式期前缀检测(无需冒号)→ 一出现就抑制 live 下发,避免逐 token 泄漏。
_TEXT_TOOLCALL_PREFIX_RE = re.compile(r"(?i)\btool[\s_]?calls?\b")
# 落地判定(需冒号 + 命名了已注册工具):比前缀严,降低误伤正常回复。
_TEXT_TOOLCALL_HEADER_RE = re.compile(r"(?i)(?:\btool[\s_]?calls?\b|工具调用|要调用的工具)\s*[:：]")
# 最终输出兜底剥离:把 "Tool calls:" 起到结尾的清单段去掉(没轮次重试时不泄漏)。
_TEXT_TOOLCALL_STRIP_RE = re.compile(
    r"(?im)\n*\s*(?:\btool[\s_]?calls?\b|工具调用|要调用的工具)\s*[:：].*\Z",
    re.S,
)


def _is_botched_text_tool_call(content: Optional[str], tools: Optional[List[Dict]]) -> bool:
    """模型把工具调用写成了**文本**而非结构化 tool_calls(两种形态,都命名了已注册工具)。

    (a) Markdown 清单式:`Tool calls:` / `工具调用:` 标题 + 工具名(无参数可解析);
    (b) 残缺 `<tool>`/`<tool_call>`/`<function_call>` 伪标签泄漏(founder 截图 2026-07-14)——
        `_extract_inline_tool_call` 恢复失败的畸形 blob(`_GENERIC_TOOL_TAG_LEAK_RE` 命中)。
    仅在 `_extract_inline_tool_call`(可解析格式)已返回 None 后调用 —— 两种都解析不出参数,
    只能重提示模型用结构化 function calling 重试(拿真数据 > 空转);轮次用尽由展示层
    `_strip_xml_tool_markers` 兜底剥离,绝不泄漏。
    """
    if not content:
        return False
    allowed = {t.get("function", {}).get("name") for t in (tools or [])}
    names_in_content = [n for n in allowed if n and n in content]
    if not names_in_content:
        return False
    # (a) 无参数清单式标题 + 已注册工具名。
    if _TEXT_TOOLCALL_HEADER_RE.search(content):
        return True
    # (b) 畸形 `<tool>` 伪标签 blob(门控确保是工具调用形状;fenced/行内代码里的 `<tool>` 是
    #     文档/示例,由 `_search_outside_code_spans` 豁免 → 不误当成"该重试的工具调用")。
    if _maybe_generic_tool_tag(content) and _search_outside_code_spans(_GENERIC_TOOL_TAG_LEAK_RE, content):
        return True
    # (c) `<tool_code>` Python 伪调用。完整且安全的形态会在此函数之前被恢复;
    # 走到这里说明语法残缺/越权,应要求模型重试结构化调用并禁止原文外泄。
    if "<tool_code" in content.lower() and _search_outside_code_spans(
        _TOOL_CODE_LEAK_RE, content
    ):
        return True
    return False


def _strip_text_tool_call(content: str) -> str:
    """剥掉 "Tool calls: ..." 文本清单段,避免泄漏给用户(重试用尽时的兜底)。"""
    return _TEXT_TOOLCALL_STRIP_RE.sub("", content or "").strip()


def _split_top_level_commas(s: str) -> List[str]:
    """Split on commas that are not nested inside (), [], {} or quotes.

    Bracket-format args look like ``type=lab_results, keywords=["a","b"], days=7``:
    naive ``split(",")`` would shatter the JSON array. This honours one level of
    bracket/brace/paren nesting and single/double quoted strings.
    """
    parts: List[str] = []
    depth = 0
    quote: Optional[str] = None
    buf: list[str] = []
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _coerce_bracket_value(raw: str) -> Any:
    """Best-effort coerce one bracket-format arg value into a Python value.

    Handles JSON arrays/objects (``["a","b"]``), quoted strings (``"LDL"``),
    numbers (``7`` / ``7.5``), booleans, and bare identifiers (``lab_results``).
    Unparseable values fall back to the stripped raw string (never raise) — the
    caller skips truly empty values.
    """
    val = raw.strip()
    if not val:
        return None
    # JSON-shaped(数组/对象)优先精确解析,失败再退化。
    if val[0] in "[{":
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            pass
        # 容错:模型常吐无引号 key 的 dict(`{meal_type: "snack", calories: 530}`)+ 弯引号。
        # 先归一引号,再给裸 key 补引号,重试 —— 救 health_record 的 data={...} payload
        # (否则 data 退化成原始字符串 → 记录存不对 / 丢字段)。
        try:
            fixed = _normalize_json_quotes(val)
            fixed = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', fixed)
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError):
            pass
    # 带引号的字符串。
    if len(val) >= 2 and val[0] in "'\"" and val[-1] == val[0]:
        return val[1:-1]
    low = val.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    # 数字。
    try:
        if re.fullmatch(r"-?\d+", val):
            return int(val)
        if re.fullmatch(r"-?\d*\.\d+", val):
            return float(val)
    except ValueError:
        pass
    # 裸标识符(type=lab_results)→ 原样字符串。
    return val


def _parse_bracket_tool_args(arg_str: str) -> Dict[str, Any]:
    """Parse ``key=value, key=value`` from the bracket tool-call signature.

    Tolerant: unparseable / valueless fragments are skipped; at minimum returns
    the keys it could read. Positional (no ``=``) fragments are ignored — our
    tool schemas are all keyword args.
    """
    args: Dict[str, Any] = {}
    for frag in _split_top_level_commas(arg_str):
        frag = frag.strip()
        if not frag or "=" not in frag:
            continue
        key, _, value = frag.partition("=")
        key = key.strip()
        if not key:
            continue
        coerced = _coerce_bracket_value(value)
        if coerced is None and value.strip().lower() not in ("null", "none"):
            # 真的解析不出(空值)→ 跳过这个参数,但不影响其它参数与 name 恢复。
            continue
        args[key] = coerced
    return args


def _extract_bracket_tool_call(raw: str, allowed: set) -> Optional[Dict[str, Any]]:
    """Recover ``[工具调用: name(args)]`` bracket-format calls.

    Returns a standard tool_call dict when ``name`` is registered, recovering
    whatever args parse cleanly (健壮容错: parse failures drop the arg, not the
    call). Returns None when no bracket marker matches or the name isn't allowed.
    """
    for m in _BRACKET_TOOL_CALL_RE.finditer(raw):
        name = m.group(1)
        if name not in allowed:
            continue
        args = _parse_bracket_tool_args(m.group(2) or "")
        return {
            "id": "inline_tool_call_0",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        }
    return None


def _extract_bare_tool_call(raw: str, allowed: set) -> Optional[Dict[str, Any]]:
    match = _BARE_TOOL_CALL_RE.fullmatch(raw or "")
    if not match or match.group(1) not in allowed:
        return None
    return {
        "id": "inline_tool_call_0",
        "type": "function",
        "function": {
            "name": match.group(1),
            "arguments": json.dumps(
                _parse_bracket_tool_args(match.group(2) or ""),
                ensure_ascii=False,
            ),
        },
    }


def _is_json_literal(value: Any) -> bool:
    """Whether an ``ast.literal_eval`` result is JSON-compatible and inert."""
    if isinstance(value, float):
        return math.isfinite(value)
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_literal(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_literal(item)
            for key, item in value.items()
        )
    return False


def _has_explicit_text_record_intent(user_message: Optional[str]) -> bool:
    """Authorize recovered textual health_record calls only for explicit writes.

    否定守卫同样在此把关:用户说「别记/记在心里」时,即便弱模型把 health_record 吐成文本,
    也不授权其恢复执行(否则绕过 fast-path 门,仍会对「别记录」写库+谎报)。
    """
    return _has_explicit_record_write_intent(user_message)


def _extract_tool_code_call(
    raw: str,
    allowed: set,
    *,
    user_message: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Recover a strict `<tool_code>print(tool(key=literal))</tool_code>` call.

    This is a protocol-repair parser, not a Python evaluator. It accepts one
    registered function call, an optional one-argument ``print`` wrapper, no
    positional or ``**`` arguments, and JSON-compatible literal values only.
    Text-recovered writes additionally require explicit user record intent.
    """
    for match in _matches_outside_code_spans(_TOOL_CODE_BLOCK_RE, raw or ""):
        body = (match.group(1) or "").strip()
        if not body:
            continue
        try:
            expression = ast.parse(body, mode="eval").body
        except (SyntaxError, ValueError):
            continue

        if (
            isinstance(expression, ast.Call)
            and isinstance(expression.func, ast.Name)
            and expression.func.id == "print"
            and len(expression.args) == 1
            and not expression.keywords
        ):
            expression = expression.args[0]

        if (
            not isinstance(expression, ast.Call)
            or not isinstance(expression.func, ast.Name)
            or expression.func.id not in allowed
            or expression.args
        ):
            continue

        name = expression.func.id
        if name == "health_record" and not _has_explicit_text_record_intent(user_message):
            continue

        args: Dict[str, Any] = {}
        valid = True
        for keyword in expression.keywords:
            if keyword.arg is None or keyword.arg in args:
                valid = False
                break
            try:
                value = ast.literal_eval(keyword.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                valid = False
                break
            if not _is_json_literal(value):
                valid = False
                break
            args[keyword.arg] = value
        if not valid:
            continue

        return {
            "id": "inline_tool_call_0",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        }
    return None


def _strip_bracket_tool_markers(text: str) -> str:
    """Strip naked ``[工具调用: ...]`` markers from final user-visible output.

    Mirrors the mac-side ``[claim:xxx]`` scrub: even when args don't parse, the
    raw marker must never reach the user.
    """
    if not text:
        return text
    # 中英文标记任一存在才尝试(便宜预检);英文标记小写比对。
    low = text.lower()
    if not any(k in low for k in ("工具调用", "调用工具", "tool_call", "function_call", "tool call")):
        return text
    return _BRACKET_TOOL_CALL_STRIP_RE.sub("", text).strip()


def _coerce_param_by_schema(value: str, param_schema: Optional[Dict[str, Any]]) -> Any:
    """按注册工具 JSON schema 的声明类型 coerce 单个 <parameter> 原始字符串值。

    XML 参数值天然是字符串;声明 integer/number/boolean 时按声明类型转换
    (镜像括号格式分支的数值/布尔 coercion),schema 缺失或声明 string/无法解析时
    回退到内容形状推断(`_coerce_bracket_value`,处理 JSON 数组/对象/裸数字等)。
    """
    val = (value or "").strip()
    declared = (param_schema or {}).get("type") if isinstance(param_schema, dict) else None
    if declared in ("integer", "number"):
        try:
            if declared == "integer" and re.fullmatch(r"-?\d+", val):
                return int(val)
            return int(val) if declared == "integer" else float(val)
        except ValueError:
            pass  # 声明是数值但值不是 → 回退内容推断,不丢参数
    elif declared == "boolean":
        low = val.lower()
        if low in ("true", "false"):
            return low == "true"
    # 声明 string / object / array / 缺失 / 数值解析失败 → 内容形状推断兜底。
    return _coerce_bracket_value(val)


def _extract_xml_tool_call(raw: str, tools: Optional[List[Dict]], allowed: set) -> Optional[Dict[str, Any]]:
    """Recover ``<invoke name="X"><parameter name="k">v</parameter>…</invoke>`` XML calls.

    MiniMax 经代理时把工具调用吐成 Anthropic 风格 XML(生产实锤 2026-07-05),既没结构化
    tool_calls 又把原始标记泄漏给用户。解析第一个 <invoke> 块:name 必须在注册表内(否则
    不吞,保持可见——镜像 bracket/menu_share 守卫);<parameter> 值按工具 JSON schema 声明
    类型做数值/布尔 coercion。多个 invoke 只取第一个并 log 总数(与现有单调用恢复语义一致)。
    """
    matches = _INVOKE_BLOCK_RE.findall(raw)
    if not matches:
        return None
    # 按注册工具名建 param schema 索引,做类型 coercion。
    schema_by_tool: Dict[str, Dict[str, Any]] = {}
    for t in tools or []:
        fn = t.get("function", {}) if isinstance(t, dict) else {}
        nm = fn.get("name")
        if nm:
            props = (fn.get("parameters") or {}).get("properties") or {}
            schema_by_tool[nm] = props if isinstance(props, dict) else {}
    total = len(matches)
    for name, body in matches:
        if name not in allowed:
            # 未注册工具名不吞:保持可见,避免把用户主动写的类似标记误当调用吞掉。
            continue
        props = schema_by_tool.get(name, {})
        args: Dict[str, Any] = {}
        for pkey, pval in _INVOKE_PARAM_RE.findall(body):
            pkey = (pkey or "").strip()
            if not pkey:
                continue
            args[pkey] = _coerce_param_by_schema(pval, props.get(pkey))
        if total > 1:
            logger.warning(
                "[agent_executor] XML <invoke> 恢复:检出 %d 个 invoke,取第一个已注册的 %s",
                total, name,
            )
        return {
            "id": "inline_tool_call_0",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
        }
    return None


# `<tool>funcname {args_json}</tool>` 形态:函数名在标签体、参数是紧跟的**独立** JSON(无 "name"
# 键)。qwen 系经代理偶发(founder 2026-07-14 实测「列出喝水记录」→ 泄漏
# `<tool>health_query {"dimension":"water"}</tool>` 且**未执行** → 无水数据)。既有三条恢复路径都
# 不认:JSON 路径要 payload 带 "name",bracket 要 `(`,invoke 要 `<invoke name=`。
_TOOL_TAG_NAME_RE = re.compile(
    r"<\s*(?:tool|tool_call|function_call)\s*>\s*([A-Za-z_]\w*)",
    re.IGNORECASE,
)


def _extract_tool_tag_call(raw: str, allowed: set) -> Optional[Dict[str, Any]]:
    """恢复 `<tool>funcname {args_json}</tool>`(函数名在标签体 + 紧跟独立参数 JSON)。

    name 必须在注册表内(否则不吞,保持可见,镜像 invoke/bracket 守卫)。用 raw_decode 从名后
    紧邻的 `{` 取平衡 JSON(支持嵌套);参数解析不出 → None,交给 botched 层走重提示/剥离,
    绝不硬塞空参执行错工具。恢复成功 → 调用真执行(有数据)且不泄漏。
    """
    m = _TOOL_TAG_NAME_RE.search(raw or "")
    if not m or m.group(1) not in allowed:
        return None
    brace = raw.find("{", m.end())
    if brace == -1 or brace > m.end() + 3:  # `{` 必须紧跟函数名(容忍几个空白)
        return None
    try:
        args, _ = json.JSONDecoder().raw_decode(raw[brace:])
    except json.JSONDecodeError:
        try:
            args = json.loads(_normalize_json_quotes(raw[brace:]))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    if not isinstance(args, dict):
        return None
    return {
        "id": "inline_tool_call_0",
        "type": "function",
        "function": {"name": m.group(1), "arguments": json.dumps(args, ensure_ascii=False)},
    }


def _strip_xml_tool_markers(text: str) -> str:
    """Strip ``<invoke>…</invoke>`` / ``<minimax:tool_call>`` / 通用 ``<tool>`` 家族工具语法。

    重试用尽 / name 不在白名单 / 参数解析失败时的兜底:任何情况都不能把原始工具语法
    (含悬空无开标签的 ``</minimax:tool_call>``、以及畸形 ``<tool>`` 伪标签 blob)留在
    用户可见正文里。镜像 ``_strip_bracket_tool_markers`` 的便宜预检 + 剥离。
    """
    if not text:
        return text
    low = text.lower()
    if (
        "<invoke" not in low
        and "minimax:tool_call" not in low
        and "<tool_code" not in low
        and not _maybe_generic_tool_tag(text)
    ):
        return text
    stripped = text
    if "<tool_code" in low:
        stripped = _apply_outside_code_spans(
            lambda seg: _TOOL_CODE_LEAK_RE.sub("", seg), stripped
        )
    stripped = _INVOKE_STRIP_RE.sub("", stripped)
    stripped = _MINIMAX_TAG_STRIP_RE.sub("", stripped)
    # 通用 `<tool>`/`<tool_call>`/`<function_call>` 伪标签泄漏(残缺/嵌套 JSON+签名混合,
    # 恢复不出结构化调用)—— 展示兜底剥离(founder 截图 2026-07-14)。`_GENERIC_TOOL_TAG_LEAK_RE`
    # 的门控确保只吃工具调用形状,不误伤文档里的 `<tool>example</tool>`;`_apply_outside_code_spans`
    # 再把 fenced ``` 块 / 行内 `code` span 整体豁免(讲解工具语法的示例不被 mangle,Finding 1)。
    # 负例见 tests/test_generic_tool_tag_leak.py。剥净后若空 → 交给下方空回复重试链。
    if _maybe_generic_tool_tag(stripped):
        stripped = _apply_outside_code_spans(
            lambda seg: _GENERIC_TOOL_TAG_LEAK_RE.sub("", seg), stripped
        )
    return stripped.strip()


# GenUI metric_table (rank1): 这些只读数据查询工具的结果可确定性打成表格卡片。
# 其余工具结果不建表 (fail-open 回散文)。
_GENUI_TABLE_TOOLS = frozenset({"health_query", "health_query_batch", "query_lab_indicators"})


def _strip_reva_ui_from_llm_text(text: str) -> str:
    """剥掉 LLM 生成文本里伪造的 ```reva-ui``` 图表 block (确定性护栏, 防御纵深)。

    reva-ui block 只能由确定性 genui 短路产出; LLM 编的 block 数值全是假的 (R4 违规)。
    单一真源在 `app.services.genui.strip_reva_ui_blocks`。仅作用于 LLM 生成文本 ——
    短路自身产出的 block 走独立更早返回路径, 不经过此处。"""
    from app.services.genui import strip_reva_ui_blocks

    return strip_reva_ui_blocks(text)


_SCOPE_REFUSAL_STRIP_ENABLED = True

# 弱模型幻觉出的"自我设限"开场白(全仓非硬编码; prompt 压不住变体, founder 2026-07-14 两版:
# "我仅负责健康数据的记录与查询,无法提供健康分析与建议…" / "我是健康记录工具路由器,无法为您
# 提供健康分析和长建议…")。确定性剥掉。极特异: 首句须**同时**含(记录|查询|路由器|工具)+
# (无法|不能|不提供|不做)+(分析|建议)三要素 → 不误伤 R4 合法免责("请咨询医生"不含此组合)、
# 也不误伤真·超范围婉拒。可选吃掉紧随的"如需…/请问您…"招呼句。
# 开场必须是**角色/职责**自限(是…路由器/工具、只/仅负责),不是能力限制(只能查询最近7天):
# `我(是…路由器/工具/助理 | [只仅]负责)` —— 排除"我只能查询…无法分析更早的"这类合法数据范围说明。
_SCOPE_REFUSAL_PREAMBLE_RE = re.compile(
    r"^\s*[<＜]?\s*"
    r"(?:抱歉[，,]?\s*)?"
    r"我(?:是[^。！？!?\n]{0,12}(?:路由器|工具|助理)|[只仅]负责)"
    r"[^。！？!?\n]*?(?:记录|查询|路由器|工具)"
    r"[^。！？!?\n]*?(?:无法|不能|不提供|不做)"
    r"[^。！？!?\n]*?(?:分析|建议)[^。！？!?\n]*[。！？!?]"
    r"(?:\s*(?:如需|请问您|需要记录|如有)[^。！？!?\n]*[。！？!?])?"
    r"\s*"
)


def _strip_scope_refusal_preamble(text: str) -> str:
    """剥掉弱模型幻觉的"我只/是负责记录查询、无法分析"自我设限开场白。

    人格恰恰相反(记录+查询+分析都归它), 这句永远是错的。极特异正则(三要素同句)→ 不误伤
    合法免责/婉拒。剥后为空 → 返回原文(极端兜底, 不吞掉整条回复)。也顺带吃掉杂散前缀 `<`。
    """
    if not _SCOPE_REFUSAL_STRIP_ENABLED or not text:
        return text
    stripped = _SCOPE_REFUSAL_PREAMBLE_RE.sub("", text, count=1)
    return stripped if stripped.strip() else text


_TEXTCALL_LEAK_STRIP_ENABLED = True

# 通用"工具调用写成文本"泄漏标记(分隔符无关): call{ / <call: / <tool>/<function_call> /
# {name: / {"name": / arguments: / dimension: / [工具调用:。既有 <tool> 族 strip/recover 只认
# <tool>{...},不认 founder 2026-07-14「列出饮食记录」的 `call {name: health_query, arguments:
# {dimension:…}}` 嵌套畸形。qwen 系经代理这类畸形层出不穷 → 用"标记+注册工具名"的通用检测,
# 覆盖未来新格式,而非逐格式点补。
_TOOL_CALL_SYNTAX_RE = re.compile(
    # 只用**强** marker(call{/<call:/<tool>/{name:/arguments:);去掉弱 marker dimension:/工具调用
    # (它们易与"模型自我解释工具"的元散文共现 → 误伤; 安全评审 fix-forward)。founder 的畸形串
    # 含 call{+{name:+arguments: 三个强 marker, 仍稳命中。
    r"(<?\s*call\s*[:{]|<\s*(?:tool|function|invoke)(?:_call)?\b|\{\s*\"?name\"?\s*:"
    r"|\barguments\s*[:=])"
)
_REGISTERED_TOOL_NAMES_CACHE: Optional[frozenset] = None


def _registered_tool_names() -> frozenset:
    global _REGISTERED_TOOL_NAMES_CACHE
    if _REGISTERED_TOOL_NAMES_CACHE is None:
        try:
            from app.services.tool_schema_registry import get_health_tools
            _REGISTERED_TOOL_NAMES_CACHE = frozenset(
                (t.get("function") or {}).get("name")
                for t in get_health_tools()
                if (t.get("function") or {}).get("name")
            )
        except Exception:  # noqa: BLE001
            _REGISTERED_TOOL_NAMES_CACHE = frozenset({
                "health_query", "health_query_batch", "health_manage", "health_record",
                "query_lab_indicators", "knowledge_search", "health_analysis",
            })
    return _REGISTERED_TOOL_NAMES_CACHE


def _strip_botched_text_tool_leak(text: str) -> str:
    """剥掉弱模型把工具调用写成**文本**的畸形前导泄漏(任意分隔符)。

    仅剥**前导块**(到首个空行/```围栏/结尾),且该块必须**同时**含 调用语法标记 + 注册工具名
    → 不误伤讨论工具名的散文(散文一般无 call{/arguments: 语法)。剥后为空 → 返回原文(不吞整条)。
    已执行的工具结果(reva-ui 卡/表)在泄漏块之后,原样保留 —— 泄漏只是模型多吐的文本。
    """
    if not _TEXTCALL_LEAK_STRIP_ENABLED or not text:
        return text
    m = re.match(r"\s*([\s\S]*?)(?=\n\s*\n|```|\Z)", text)
    if not m:
        return text
    head = m.group(1)
    if not head.strip() or not _TOOL_CALL_SYNTAX_RE.search(head):
        return text
    if not any(n in head for n in _registered_tool_names()):
        return text
    rest = text[m.end():].lstrip()
    return rest if rest.strip() else text


def _placeholder_reva_ui_in_history(text: str) -> str:
    """把历史助手消息里的 ```reva-ui``` block 换成占位符, 再喂回 LLM (防模仿)。

    单一真源在 `app.services.genui.placeholder_reva_ui_blocks`。"""
    from app.services.genui import placeholder_reva_ui_blocks

    return placeholder_reva_ui_blocks(text)


_BARE_JSON_START_RE = re.compile(r'^\{\s*"\w+"\s*:')


def _looks_like_bare_tool_json(text: str) -> bool:
    """整条最终回复其实是裸 JSON(工具参数或后端返回的记录),不是给用户看的人话。

    弱模型(如 deepseek-v4-pro)记录后会把工具结果/参数 JSON 当最终回复回显:
    `{"id":231,"user_id":3,...,"reps":20}` / `{"record_date":...,"meal_type":...}`
    (用户截图)。这类应被工具结果合成的"已记录…"替换,绝不裸露给用户。

    判定保守:去 ```json fence 后,以 `{"key":` 开头(截断也算)或能整体解析成
    dict/list 才算;调用方再 gate"本轮确有工具结果"才替换,避免误伤用户主动要的 JSON。
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s).rstrip("`").strip()
    if not s:
        return False
    if _BARE_JSON_START_RE.match(s):
        return True  # 含截断的 `{"k":...` —— 强裸 JSON 信号
    if s[0] in "{[":
        try:
            return isinstance(json.loads(s), (dict, list))
        except json.JSONDecodeError:
            return False
    return False


# ── 泄漏工具结果 JSON 检测(锚定字段白名单,非"任何 JSON")────────────────────
# 弱模型(qwen3.7-max)在 QUERY 回答里会先写一句人话再把工具结果原始 JSON 数组
# 粘进正文,例:`让我查一下今天的饮食记录…[{"record_date":"2026-07-01","meal_type":
# "breakfast",...}]`。_looks_like_bare_tool_json 只认"整条就是裸 JSON",这种"短前言
# + 内嵌数组"漏过。这里做锚定检测:只有当内嵌 JSON 的键与**已知工具结果字段白名单**
# 相交才判为泄漏 —— 绝不对任意 JSON、也绝不对用户主动要的 ```json / ```reva-ui /
# ```menu_share 代码块(app 会渲染)动手。纪律见 memory「anchored allowlist 非子串」。
#
# 白名单只收工具 result payload 里真实出现的字段名(记录/查询回来的),不收 menu_share
# / reva-ui 的字段(title/items/reason 等),否则会误伤用户要的菜单/图表块。
_TOOL_RESULT_FIELD_ALLOWLIST: frozenset = frozenset({
    "record_date", "meal_type", "food_items", "food_id", "food_name",
    "calories", "protein", "carbs", "fat", "fiber", "alcohol_units",
    "systolic", "diastolic", "glucose_mg_dl", "spo2_min", "spo2",
    "hrv", "resting_hr", "body_battery", "stress", "readiness",
    "occurred_at", "taken_time", "remind_at", "recurrence",
    "body_part", "severity", "mood_score", "weight", "reps",
    "exercise_type", "drink_type", "reference_low", "reference_high",
    "is_abnormal", "user_id",
})
# 需要至少这么多个白名单字段命中,才算"泄漏工具结果"。单字段(如正文里恰好有个
# {"weight": 72})可能是用户主动贴的合法 JSON;要求 ≥2 个白名单字段同现,把误伤
# 压到极低,同时真泄漏(一条 record 至少 5-8 个字段)必然命中。
_TOOL_RESULT_MIN_FIELD_HITS = 2
# 前言最多这么长 —— 真泄漏是"一句短语就开始 dump"(如"让我查一下今天的饮食记录…"
# ≈13 字);一整句分析(≈60+ 字)后才嵌 JSON 属于灰区,宁可漏判也不误伤合法分析,
# 故把上限收到 40:覆盖真泄漏的短前言,拒绝"长分析 + 尾部小 JSON"。
_LEAK_PREAMBLE_MAX_CHARS = 40


def _json_keys_hit_allowlist(payload: Any) -> int:
    """payload(dict 或 list[dict])里命中工具结果字段白名单的**去重**键数。"""
    keys: set = set()

    def _collect(obj: Any) -> None:
        if isinstance(obj, dict):
            keys.update(k for k in obj.keys() if isinstance(k, str))
        elif isinstance(obj, list):
            for item in obj[:8]:  # 采样前几项即可,数组同构
                _collect(item)

    _collect(payload)
    return len(keys & _TOOL_RESULT_FIELD_ALLOWLIST)


def _leaks_tool_result_json(text: str) -> bool:
    """回复里(在一小段前言后)内嵌了一段工具结果原始 JSON 数组/对象 → 判定为泄漏。

    锚定判定,故意保守以避免误伤:
      1. **有任何 fenced 代码块 → 直接不判泄漏**(用户主动要的 ```json、app 渲染的
         ```reva-ui / ```menu_share 都在此豁免;弱模型裸泄漏从不带围栏)。
      2. 从文本里扫第一个 `[` 或 `{`,要求它出现在前 _LEAK_PREAMBLE_MAX_CHARS 内
         (真泄漏是"一句人话就开始 dump",长篇分析里偶提字段名不触发)。
      3. 该处能解析出 JSON 数组/对象,且键与工具结果字段白名单相交 ≥ 阈值。
    只提到字段名的普通散文(无 JSON 括号结构)永不触发。
    """
    s = (text or "").strip()
    if not s:
        return False
    # (1) 任何 fenced 块 → 豁免。用户要 JSON/代码,或 app 渲染的 reva-ui/menu_share。
    if "```" in s:
        return False
    # (2) 第一个 JSON 结构起点必须在短前言内。
    lb = s.find("[")
    ob = s.find("{")
    candidates = [i for i in (lb, ob) if i != -1]
    if not candidates:
        return False
    start = min(candidates)
    if start > _LEAK_PREAMBLE_MAX_CHARS:
        return False
    # (3) 从起点解析 JSON,键命中白名单 ≥ 阈值 → 泄漏。用宽松解析救弯引号/截断。
    tail = s[start:]
    payload = None
    try:
        payload, _ = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError:
        try:
            payload = _loads_lenient(tail)
        except json.JSONDecodeError:
            payload = None
    if payload is None:
        return False
    return _json_keys_hit_allowlist(payload) >= _TOOL_RESULT_MIN_FIELD_HITS


# 流式期"泄漏正在形成"的早停:JSON 还没吐完、raw_decode 尚不能解析,但已能看出
# 是在 dump 工具结果。锚定到**带引号 + 冒号的白名单字段键**(如 `"record_date":`),
# 散文永不会写出 `"record_date":` 这种形态 → 误伤趋近于零。命中即抑制,把逐 token
# 泄漏压到最多一两个 delta(JSON 结构刚起、字段名刚现)。fenced 块一律豁免。
_QUOTED_ALLOWLIST_KEY_RE = re.compile(
    r'["“]('
    + "|".join(re.escape(k) for k in sorted(_TOOL_RESULT_FIELD_ALLOWLIST))
    + r')["”]\s*[:：]'
)


def _streaming_leak_forming(text: str) -> bool:
    """流式增量文本里,泄漏工具结果 JSON 是否已在形成(供逐 delta 早停抑制)。

    比 _leaks_tool_result_json 更早触发(不要求整段 JSON 可解析),但同样锚定:
    必须(1)无 fenced 围栏(否则是用户/渲染意图);(2)短前言内已起 JSON 结构;
    (3)已出现 ≥ _TOOL_RESULT_MIN_FIELD_HITS 个"带引号+冒号的白名单字段键"。
    三者同时满足才抑制 —— 单个孤立键(用户可能主动贴的 {"calories":500})不触发。
    """
    s = (text or "").strip()
    if not s or "```" in s:
        return False
    lb = s.find("[")
    ob = s.find("{")
    candidates = [i for i in (lb, ob) if i != -1]
    if not candidates or min(candidates) > _LEAK_PREAMBLE_MAX_CHARS:
        return False
    start = min(candidates)
    hits = {m.group(1) for m in _QUOTED_ALLOWLIST_KEY_RE.finditer(s[start:])}
    # `[{` 数组套对象 = 工具结果列表的签名(没人未围栏手贴这种形态):首个白名单键
    # 一出现就得停,等凑满 2 个键时前面的 delta 已经漏出去了(流式不可撤回)。
    # 裸对象 `{...}` 维持 ≥2 键 —— 用户主动贴的 {"calories":500} 不能误伤。
    if re.match(r"\[\s*\{", s[start:]):
        return len(hits) >= 1
    return len(hits) >= _TOOL_RESULT_MIN_FIELD_HITS


# ──── 思考流可视化 (qwen reasoning_content → thinking status 事件) ────
# 合成/答案轮首个可见 token 之前有 ~20-34s 纯 reasoning 死气 (探针实证:
# scripts/probe_qwen_thinking_budget.py —— 首个 reasoning delta @ ~1.7s,
# 首个可见 content @ ~35.8s)。把 reasoning_content 增量节流成既有 thinking status
# 事件, 让那段死气变成活的思考进度。reasoning 文本绝不进 full_reply/messages/持久化答案。
_REASONING_STATUS_MIN_INTERVAL_S = 1.5   # 两次思考 status 的最小时间间隔
_REASONING_STATUS_MIN_CHARS = 120        # 两次之间最少新增 reasoning 字符数 (whichever later)
_REASONING_SNIPPET_MAX_CHARS = 60        # detail 片段字符上限, 超出取尾部 + 前缀省略号
# markdown 记号 / 列表符 / 方括号 —— 清成平实一行进度文案。
_REASONING_SNIPPET_STRIP_RE = re.compile(r"[#*`>_~\-\[\]]+")


def _clean_reasoning_snippet(text: str) -> str:
    """把累积的 reasoning_content 清成一个短的 live 思考片段 (thinking status 的 detail)。

    strip markdown 记号/换行, 折叠空白, 取**尾部** ~60 字 (模型当前思考位置);
    截断则前缀省略号。纯 UI 死气填充的一次性快照 —— 绝不进入答案或持久化。
    """
    s = _REASONING_SNIPPET_STRIP_RE.sub(" ", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    if len(s) > _REASONING_SNIPPET_MAX_CHARS:
        return "…" + s[-_REASONING_SNIPPET_MAX_CHARS:]
    return s


def _natural_language_from_tool_results(messages: List[Dict[str, Any]]) -> str:
    """QUERY 泄漏兜底:把工具结果转成一句中性人话,绝不裸露 JSON。

    与 _fast_record_reply_from_tool_results 的区别:那条是记录场景("已记录…"),
    这条是查询场景。优先用 tool result 自带的 message/summary;没有则给一句让模型
    重述的通用兜底(调用方随后走空回复重试链,让模型用自然语言重答)。
    """
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        content = str(message.get("content") or "").strip()
        if not content or content.startswith("Error"):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            msg = payload.get("message") or payload.get("summary")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
        # 有工具结果但无现成人话字段 → 交给空回复重试链让模型自然语言重答。
        return ""
    return ""


def _resolve_synthesis_passthrough_mode() -> str:
    """读 settings.orchestrator_synthesis_passthrough,fail-closed 归一到 {off,shadow,on}。

    任何未知/拼错的 env 值(以及缺失)→ 'off',绝不因配置漂移意外改变用户可见行为。
    """
    mode = (getattr(settings, "orchestrator_synthesis_passthrough", "off") or "off")
    mode = str(mode).strip().lower()
    return mode if mode in ("shadow", "on") else "off"


def _apply_passthrough_outbound_guards(
    text: str, messages: List[Dict[str, Any]]
) -> str:
    """把二次合成出站路径上的确定性护栏,同样施加到深分析 passthrough 文本上。

    rank7 passthrough 跳过了 agent 第二次合成轮 —— 那条 else 分支里对 final_text 施加的
    marker strip / leak 抑制护栏就被绕过了(降级/兜底路径逃 R4 是已知雷)。本函数复用**同一批**
    谓词/剥离器,保证 passthrough 文本与二次合成答案受同一条链约束:
      1. `_strip_bracket_tool_markers` —— 裸 ``[工具调用: ...]`` 标记;
      2. `_strip_xml_tool_markers` —— ``<invoke>…</invoke>`` / ``<minimax:tool_call>``;
      3. 裸工具结果 JSON(整条)→ 用工具结果里现成人话兜底;
      4. 短前言 + 内嵌工具结果 JSON 数组(`_leaks_tool_result_json`)→ 同样兜底。
    orchestrator 的 synthesis 本是已过 R4/advice_guard 的散文,正常不会命中任何一条 ——
    这些护栏是防御纵深,不是热路径。fenced ```menu_share/```reva-ui 块被 leak 谓词豁免,
    原样保留给消费层(api/agent.py)提取(与二次合成答案行为一致)。post-loop 的
    `_strip_reva_ui_from_llm_text` 与消费层 menu_share 提取/thinking_steps 对两条路径一视同仁,
    不在此重复。
    """
    stripped = _strip_bracket_tool_markers(text)
    if stripped != text:
        text = stripped
    stripped_xml = _strip_xml_tool_markers(text)
    if stripped_xml != text:
        text = stripped_xml
    if _looks_like_bare_tool_json(text):
        text = _natural_language_from_tool_results(messages) or (
            "已查到相关数据,但这轮没能整理成回答;请再问一次或换个问法。"
        )
    elif _leaks_tool_result_json(text):
        text = _natural_language_from_tool_results(messages) or (
            "已查到相关数据,但这轮没能整理成回答;请再问一次或换个问法。"
        )
    return text


_SMART_DOUBLE_QUOTES = "“”„‟″＂"  # “ ” „ ‟ ″ ＂
_SMART_SINGLE_QUOTES = "‘’‚‛′＇"  # ‘ ’ ‚ ‛ ′ ＇
_QUOTE_NORMALIZE_TABLE = str.maketrans(
    {ord(c): '"' for c in _SMART_DOUBLE_QUOTES} | {ord(c): "'" for c in _SMART_SINGLE_QUOTES}
)


def _normalize_json_quotes(s: str) -> str:
    """把弯引号/全角引号归一为直引号,救弱模型(如 glm-5.1)吐的非法 JSON。

    只作为标准 json.loads 失败后的兜底:已经解析失败说明这些引号是被当作分隔符
    (bug),归一后重试严格更优,不会误伤合法 JSON 字符串里的引号(那种情况标准
    解析本就成功,不会走到这)。
    """
    return s.translate(_QUOTE_NORMALIZE_TABLE)


def _repair_truncated_json(s: str) -> str:
    """Best-effort 修复被截断的 JSON — 弱模型/网关常把 tool call 的 arguments 截断,
    停在缺尾 ``}`` ``]`` 或断在字符串/逗号处。

    实测案例(glm-5.1 记"打喷嚏一次"):
    ``{"record_type":"rhinitis","data":{"sneezing":1,"congestion":0,"runny_nose":0}``
    外层 ``}`` 缺失 → json.loads 失败 → "参数解析失败" 裸露给用户、记录丢失。

    扫描时按栈跟踪未闭合的 ``{`` ``[`` 与字符串状态,在末尾补未闭合字符串、去掉结尾
    多余逗号、按栈逆序补 closer。只在标准 + 引号归一解析都失败后兜底:无法修复时原样
    返回(调用方仍失败 → 报错给 LLM 重试,不假装成功)。
    """
    s = s.strip()
    if not s:
        return s
    stack: List[str] = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
    if not stack and not in_string:
        return s  # 没有未闭合结构 → 截断不在结构层,修不了,原样返回
    repaired = s + ('"' if in_string else "")
    repaired = re.sub(r",\s*$", "", repaired.rstrip())  # 去尾逗号(补 closer 前)
    closers = {"{": "}", "[": "]"}
    repaired += "".join(closers[opener] for opener in reversed(stack))
    return repaired


def _trim_extra_trailing_json_closers(s: str) -> str:
    """Drop unmatched closing braces appended by a weak tool-call decoder."""
    stack: List[str] = []
    in_string = False
    escape = False
    for index, ch in enumerate(s):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
            continue
        if ch in "}]":
            expected = "{" if ch == "}" else "["
            if stack and stack[-1] == expected:
                stack.pop()
            else:
                return s[:index].rstrip()
    return s


def _loads_lenient(raw: str) -> Any:
    """标准 → 引号归一 → 截断修复 → 归一+修复,逐级兜底解析弱模型 JSON。

    任何一级成功即返回;全失败抛最后一个 JSONDecodeError(调用方决定如何处理)。
    """
    normalized_quotes = _normalize_json_quotes(raw)
    trimmed = _trim_extra_trailing_json_closers(raw)
    trimmed_normalized = _trim_extra_trailing_json_closers(normalized_quotes)
    candidates = (
        raw,
        normalized_quotes,
        trimmed,
        trimmed_normalized,
        _repair_truncated_json(raw),
        _repair_truncated_json(normalized_quotes),
        _repair_truncated_json(trimmed),
        _repair_truncated_json(trimmed_normalized),
    )
    last_err: Optional[json.JSONDecodeError] = None
    seen: set = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            return json.loads(cand)
        except json.JSONDecodeError as e:
            last_err = e
    raise last_err if last_err else json.JSONDecodeError("empty", raw or "", 0)


def _parse_tool_arguments_for_telemetry(args_raw: Any) -> dict[str, Any]:
    """Recover normalized argument shape for receipt detection without logging it."""
    if isinstance(args_raw, dict):
        return args_raw
    if not isinstance(args_raw, str):
        return {}
    try:
        parsed = json.loads(args_raw)
    except json.JSONDecodeError:
        try:
            parsed = _loads_lenient(args_raw)
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _text_tool_call_write_is_authorized(
    call: Dict[str, Any],
    user_message: Optional[str],
) -> bool:
    """Require the shared semantic frame before recovering a manage write.

    Text recovery is only a protocol parser.  It must not carry its own keyword
    authorization logic; ToolGateway remains the final execution boundary.
    """
    function = call.get("function") or {}
    if function.get("name") != "health_manage":
        return True
    try:
        args = json.loads(function.get("arguments") or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    operation = str(args.get("operation") or "").strip().lower()
    if operation in {"delete", "update"}:
        intent = classify_agent_utterance(user_message)
        return intent.primary == "mutate" and intent.operation == operation
    return True


def _extract_inline_tool_call(
    text: str,
    tools: List[Dict],
    *,
    user_message: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Recover tool calls emitted as visible JSON text by weaker gateways/models.

    Some commercial proxy models ignore OpenAI `tools` semantics and print a
    payload like {"name":"health_manage","parameters":{...}} inside content.
    Treat any JSON object whose name matches our registered tools as a tool
    call, even when surrounded by human text — weaker models often emit the
    call JSON first and then a prose confirmation/analysis (the JSON must not
    leak to the user, and the tool must actually run). Ordinary JSON snippets
    such as menu_share stay user-visible: their name is not a registered tool,
    so the `name not in allowed` guard below skips them.

    Also recovers the bracket signature format some models emit instead of JSON:
    ``[工具调用: health_query(type=lab_results, keywords=["Hcy"], days=7)]``
    (中英文冒号 + 可选方括号 + Python 调用风格参数).

    Also recovers the XML/`<invoke>` format MiniMax emits via the proxy:
    ``<invoke name="health_query"><parameter name="dimension">diet</parameter>…</invoke>``
    (Anthropic-style tags, possibly wrapped in ``<minimax:tool_call>``).
    """
    raw = (text or "").strip()
    if not raw:
        return None

    allowed = {t.get("function", {}).get("name") for t in tools or []}

    def _authorized(call: Dict[str, Any]) -> bool:
        return _text_tool_call_write_is_authorized(call, user_message)

    # Python 风格 `<tool_code>print(tool(...))</tool_code>` 先走严格 AST 白名单恢复。
    # 只读取语法树字面量,绝不 eval/exec;health_record 还需用户明确记录意图。
    tool_code = _extract_tool_code_call(raw, allowed, user_message=user_message)
    if tool_code is not None:
        return tool_code if _authorized(tool_code) else None

    # XML/`<invoke>` 格式先尝试:它以 `<` 开头,与 JSON(`{`)/括号(`(`)路径互不干扰。
    xml = _extract_xml_tool_call(raw, tools, allowed)
    if xml is not None:
        return xml if _authorized(xml) else None

    # `<tool>funcname {args}</tool>` 形态(函数名在标签体 + 独立参数 JSON):既有三路都不认,
    # 恢复后真执行、不泄漏(founder 2026-07-14「列出喝水记录」根因)。
    tag_call = _extract_tool_tag_call(raw, allowed)
    if tag_call is not None:
        return tag_call if _authorized(tag_call) else None

    # 括号格式先于 JSON 尝试:它含 `(` 不含起始 `{`,与 JSON 路径互不干扰。
    bracket = _extract_bracket_tool_call(raw, allowed)
    if bracket is not None:
        return bracket if _authorized(bracket) else None

    bare = _extract_bare_tool_call(raw, allowed)
    if bare is not None:
        return bare if _authorized(bare) else None

    def _payload_to_tool_call(payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        fn = payload.get("function") if isinstance(payload.get("function"), dict) else None
        name = (
            payload.get("name")
            or payload.get("tool")
            or payload.get("tool_name")  # 弱模型常吐 {"tool_name":"health_record","arguments":{…}}
            or payload.get("tool_code")
            or (fn or {}).get("name")
        )
        if name not in allowed:
            # Weak models sometimes print health_manage's arguments without a
            # name wrapper. Recover the management operation before attempting
            # naked health_record inference, otherwise meal_type misclassifies a
            # read/update as a new diet write.
            operation = str(payload.get("operation") or "").strip().lower()
            if (
                "health_manage" in allowed
                and payload.get("record_type")
                and operation in {"list", "update", "delete"}
            ):
                return {
                    "id": "inline_tool_call_0",
                    "type": "function",
                    "function": {
                        "name": "health_manage",
                        "arguments": json.dumps(payload, ensure_ascii=False),
                    },
                }
            # 模型可能直接吐 record 的裸 data(无 name 包装,无 record_type)。
            # 按字段推断 record_type → 包成 health_record 调用,既写库又不泄漏 JSON。
            # **仅在用户明确表达记录意图时**才把裸对象猜成写入 —— 否则只读问句("我体重多少")
            # 模型回显 {"weight":72.5,…} 会被误当 health_record 写入 → 幽灵/重复记录。
            # 镜像 <tool_code> 路径(_extract_tool_code_call)对 health_record 的同一意图门。
            if "health_record" in allowed and _has_explicit_text_record_intent(user_message):
                inferred = _infer_record_type_from_payload(payload)
                if inferred:
                    return {
                        "id": "inline_tool_call_0",
                        "type": "function",
                        "function": {
                            "name": "health_record",
                            "arguments": json.dumps(
                                {"record_type": inferred, "data": payload},
                                ensure_ascii=False,
                            ),
                        },
                    }
            return None

        # 参数容器键因模型而异:OpenAI 风格 parameters/arguments、Anthropic 风格
        # input、口语化 params/args。实测 Claude-Opus-4.7(langbridge)吐
        # {"tool":"health_query","params":{...}} —— 只认 parameters/arguments 会把
        # args 丢成 {},下游 dimension 默认 comprehensive → 拿睡眠数据答 MRI 问题。
        args: Any = None
        for container_key in ("parameters", "params", "arguments", "input", "tool_input", "args"):
            if container_key in payload:
                args = payload[container_key]
                break
        if args is None:
            args = (fn or {}).get("arguments")
        if args is None:
            # 平铺 sibling 参数:{"tool_name":"health_query","dimension":"diet","days":7}
            # (无参数容器)。此前落回 {} → dimension 丢 → 默认 comprehensive 答错题。
            # 把非元数据键当 args。
            _meta = {"name", "tool", "tool_name", "tool_code", "function",
                     "parameters", "params", "arguments", "input", "tool_input", "args"}
            _siblings = {k: v for k, v in payload.items() if k not in _meta}
            args = _siblings if _siblings else {}
        if isinstance(args, str):
            try:
                args = _loads_lenient(args)  # 弯/全角引号 + 截断兜底
            except json.JSONDecodeError:
                return None
        if not isinstance(args, dict):
            return None
        return {
            "id": "inline_tool_call_0",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
        }

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            payload, end = decoder.raw_decode(raw[idx:])
        except json.JSONDecodeError:
            continue
        call = _payload_to_tool_call(payload)
        if call is not None:
            return call if _authorized(call) else None

    # 兜底:整段就是一个被截断的 tool-call JSON(raw_decode 对每个 `{` 都失败)。
    # 从第一个 `{` 起做截断修复再解析一次 —— 救 glm-5.1 吐到一半被切断的调用。
    first = raw.find("{")
    if first != -1:
        try:
            payload = _loads_lenient(raw[first:])
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            call = _payload_to_tool_call(payload)
            return call if call is not None and _authorized(call) else None
    return None


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return response.get("content") or ""
    return str(response or "")


def _extract_markdown_section(text: str, title: str) -> str:
    pattern = rf"(?:^|\n)## {re.escape(title)}\n(?P<body>.*?)(?=\n## |\Z)"
    match = re.search(pattern, text or "", flags=re.S)
    if not match:
        return ""
    body = match.group("body").strip()
    return f"## {title}\n{body}" if body else ""


def _clip_context(text: str, limit: int) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n..."


def _build_compact_empty_retry_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a short no-tools retry prompt for gateways that empty-answer long contexts."""
    system_content = next(
        (str(m.get("content") or "") for m in messages if m.get("role") == "system"),
        "",
    )
    sections: list[str] = []
    section_limits = {
        "入口动作处理结果": 180,
        "入口上下文 (用户正在看的具体方案)": 220,
        "用户健康档案": 520,
        "系统知识库相关条目": 220,
    }
    for title, limit in section_limits.items():
        section = _extract_markdown_section(system_content, title)
        if section:
            sections.append(_clip_context(section, limit))

    if not sections and system_content:
        sections.append(_clip_context(system_content, 520))

    compact_system_parts = [
        "你是用户的 AI 健康助理。请用中文直接回答本轮问题。",
        "必须基于已提供的健康上下文做判断；不要编造未给出的数据。",
        "输出应简洁、可执行；涉及诊断、治疗或用药时提醒咨询医生。",
    ]
    if sections:
        compact_system_parts.extend(["", "## 压缩上下文", "\n\n".join(sections)])

    default_user_prompt = "请直接给出完整中文回答。"
    skipped_retry_text = "上一轮没有生成任何用户可见回复"
    user_messages = [
        m for m in messages
        if m.get("role") == "user"
        and skipped_retry_text not in str(m.get("content") or "")
    ]
    last_user = user_messages[-1] if user_messages else {"role": "user", "content": default_user_prompt}
    compact_system_content = _clip_context(
        "\n".join(compact_system_parts),
        COMPACT_EMPTY_RETRY_SYSTEM_CHAR_LIMIT,
    )
    compact_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": compact_system_content}
    ]

    last_content = last_user.get("content")
    if isinstance(last_content, list):
        compact_messages.append({"role": "user", "content": last_content})
    else:
        compact_messages.append({
            "role": "user",
            "content": str(last_content or default_user_prompt).strip(),
        })
    return compact_messages


def _fallback_text_from_tool_results(
    messages: List[Dict[str, Any]],
    *,
    has_verified_write: bool = False,
) -> str:
    """Use the latest successful tool result when the model fails synthesis.

    诚实不变量(turn 6334 同病根的第三个宣称面):"已完成记录/已完成操作"只允许在
    本轮产生了**可验证写入回执**(调用点按 write_receipts 传 has_verified_write)时
    出现。纯查询/分析回合走到空回复重试链时,工具结果里有 food_items/id 不代表
    写过任何东西 —— 无回执一律查询味口径("查到：…");没有人话可展示(id-only 字典、
    结构化残片/manage-list 数组)就返回空串交回重试链,链有界(compact retry →
    fallback provider → 硬兜底文案),不会重试风暴。默认 False = fail-closed:
    新调用点忘了传参也绝不凭空宣称写入。

    数据泄漏护栏(双模):结构化残片(首字符 { / [)任何模式都不回显给用户 ——
    有回执退中性"已完成记录。",无回执退空串;"已完成操作：…"只承载人话文本。

    C3(Wave 2):所有工具结果都是 "Error:*"(查询服务 500/超时等)时,此前 skip 掉
    全部错误 → 返回空串 → 上层通用"没拿到有效模型回复",把真失败盖成 silent-green。
    改为:见过错误且无任何可展示人话时,返回规范化诚实失败(不泄漏原始 error 文本)。
    """
    saw_error = False
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue

        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if content.startswith("Error"):
            # C3(Wave 2):记下"有工具失败了",但不在这里回显原始 error 文本(可能含
            # 上游 resp.text 内部细节)—— 用于末尾决定返回规范化诚实失败还是空串。
            saw_error = True
            continue

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict):
            tool_message = payload.get("message")
            if isinstance(tool_message, str) and tool_message.strip():
                return tool_message.strip()

            for key in ("food_items", "summary", "preview"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    if has_verified_write:
                        return f"已完成记录：{value.strip()}"
                    return f"查到：{value.strip()}"

            if payload.get("id") or payload.get("record_id"):
                # 只读回合返回的 id 字典没有可展示的人话字段 —— 绝不因"结果里有
                # id"就宣称写入,交回重试链让模型重答。
                return "已完成记录。" if has_verified_write else ""

        preview = content.replace("\n", " ").strip()
        if preview:
            if preview[0] in "{[":
                # 结构化残片(含 manage-list 的记录数组)对用户既不可读又泄漏
                # 工具结果 —— 真写入回合退中性确认(与 id-only 字典分支同口径),
                # 查询回合不展示,交回重试链。两个模式都绝不回显裸 JSON。
                return "已完成记录。" if has_verified_write else ""
            if has_verified_write:
                return f"已完成操作：{preview[:120]}"
            return f"查到：{preview[:120]}"

    # C3(Wave 2):无任何可展示人话。若过程中有工具失败,fail-loud 一句诚实失败,
    # 而不是空串(空串会被上层兜成通用"没拿到有效模型回复",遮盖真因)。
    if saw_error:
        return "抱歉，刚才有一步没有成功，我没能拿到完整结果。请稍后再试一次，或者换个说法告诉我。"
    return ""


_QUESTION_TAIL_RE = re.compile(
    r"[?？]|要不要|是否|需不需要|要记录吗|记录吗|对吗|是吗|好吗|可以吗|吗\s*[?？]?\s*$|呢\s*[?？]?\s*$"
)


def _assistant_turn_is_question(text: str) -> bool:
    """上一轮助手是否在向用户提问(需用户下一轮回答来消歧)。只看结尾一段,避免长分析正文里
    偶含「吗」误判。用于 fast-record 折叠门:非提问的上一轮(分析/陈述)不折进,防上下文串味
    (founder 2026-07-17「麦当劳店记录喷嚏」根因)。"""
    s = (text or "").strip()
    if not s:
        return False
    return bool(_QUESTION_TAIL_RE.search(s[-80:]))


def _reminder_delivery_status_tail(delivery_status: Any) -> str:
    """Translate reminder delivery capability into an honest user-facing tail.

    Reminder creation is verifiable server-side. Watch display is currently via
    `/watch/summary`, not a confirmed APNs/watchOS delivery receipt.
    """
    if not isinstance(delivery_status, dict):
        return ""

    parts: List[str] = []
    iphone = delivery_status.get("iphone_notification")
    if isinstance(iphone, dict):
        if iphone.get("delivery_confirmed") is True:
            parts.append("手机提醒已确认")
        elif str(iphone.get("status") or "").strip() == "will_attempt_when_due":
            parts.append("手机到点会尝试提醒")

    watch = delivery_status.get("watch")
    if isinstance(watch, dict):
        if watch.get("delivery_confirmed") is True:
            if str(watch.get("receipt_type") or "") == "watch_summary_visible":
                parts.append("手表已刷新到这条提醒")
            else:
                parts.append("已确认送达手表")
        elif (
            str(watch.get("route") or "").strip() == "watch_summary_due_item"
            or str(watch.get("status") or "").strip() == "visible_when_watch_summary_refreshes"
        ):
            parts.append("手表刷新今日摘要后可执行（未确认已送达手表）")

    if not parts and delivery_status.get("agent_claim") == "created_not_device_delivered":
        parts.append("提醒已创建（未确认已送达手表）")

    return f"；{'；'.join(parts)}" if parts else ""


def _extract_reminder_delivery_status_from_result(result: Any) -> Optional[Dict[str, Any]]:
    if isinstance(result, dict):
        payload = result
    elif isinstance(result, str):
        try:
            payload = json.loads(result)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    else:
        return None
    if not isinstance(payload, dict):
        return None
    delivery_status = payload.get("delivery_status")
    return delivery_status if isinstance(delivery_status, dict) else None


def _should_force_record_tool_choice(
    prefer_fast_record: bool,
    original_messages: List[Dict[str, Any]],
    pass_tools: Optional[List[Dict[str, Any]]],
    supports_forced_tool_choice: bool,
) -> bool:
    """R2 门控(纯函数, battery 可测): 高置信记录轮的**首个**工具轮才 force tool_choice。

    四个条件全真才 force:
    - prefer_fast_record: 确定性记录意图门(已排除疑问句/删改/分析)已命中;
    - 首轮: **原始 messages**(跨轮累积 tool 结果的那份, 非 _messages_for_round 压缩版
      ——fast-record 压缩版恒为 [system,user], 判不出轮次; 安全评审 2026-07-17 抓出)
      里无 tool 结果消息 —— 后续轮再 force 会造成无限工具循环;
    - pass_tools 里确实有 health_record(被工具子集裁掉时 force 一个不存在的工具=400);
    - ModelEntry.supports_forced_tool_choice=True(真网探针验证过的模型, registry flag,
      与 supports_thinking_budget 同款纪律; 不用模型名子串——安全评审抓出的口径不一)。
    """
    if not prefer_fast_record:
        return False
    if any(m.get("role") == "tool" for m in original_messages or []):
        return False
    if not any(
        (t.get("function") or {}).get("name") == "health_record"
        for t in (pass_tools or [])
    ):
        return False
    return bool(supports_forced_tool_choice)


def _build_fast_record_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact prompt for pure record/CRUD turns.

    Pure logging should not send the full Twin, knowledge base, and long chat
    history to a reasoning model. Tool extraction only needs the latest user
    request plus strict routing instructions.

    **但跟进式记录必须保留紧邻的上一条助手回合**:助手刚问「要不要记录鼻炎症状(打喷嚏/流鼻涕)?」
    用户答「记录」时,若只把最新一条用户消息「记录」发给模型,它**无从知道记什么** → 重新泛问
    「什么症状?」(实测 bug:上下文丢失)。故保留最后一条非空 assistant 回合(截断保持 compact),
    其余长历史/Twin/KB 仍剔除。
    """

    default_user_prompt = "请记录这条健康数据。"
    user_messages = [m for m in messages if m.get("role") == "user"]
    last_user = user_messages[-1] if user_messages else {"role": "user", "content": default_user_prompt}
    user_content = last_user.get("content") or default_user_prompt

    # 紧邻最新用户消息之前的最后一条非空 assistant 回合 —— 跟进式记录的消歧上下文。
    # **折进 user 消息**(而非单独发一条 assistant):fast-record 走弱/代理模型(qwen/deepseek
    # via tokenplan),[system, assistant, user] 这种 assistant 先于任何 user 的序列易被严格
    # OpenAI 兼容适配器拒;折进单条 user 保持 [system, user] 稳态,且对弱模型更显式。
    last_assistant = next(
        (
            m for m in reversed(messages)
            if m.get("role") == "assistant" and str(m.get("content") or "").strip()
        ),
        None,
    )
    # **只在上一轮助手确实在提问时才折进它做消歧** —— 否则上一轮是分析/陈述(如刚分析完
    # 麦当劳那餐)时,把它折进一条自足的新记录("记录刚才打了一个喷嚏")会串味,让模型
    # 幻觉出「麦当劳店记录打了喷嚏」(founder 2026-07-17 实测)。跟进确认(助手问「要不要
    # 记录鼻炎症状?」→ 用户答「记录」)仍照旧折入,消歧不丢。
    if last_assistant:
        prior = str(last_assistant.get("content") or "").strip()
        if _assistant_turn_is_question(prior):
            user_content = f"[上一轮助手问我:{prior[:400]}]\n我的回复:{user_content}"

    return [
        {
            "role": "system",
            "content": (
                "你是健康记录工具路由器。用户要求记录、新增、修改、删除健康数据时，"
                "必须调用 health_record 或 health_manage 工具。不要做健康分析，"
                "不要输出长建议。若用户提到多条记录，尽量一次性发起多个 tool_call；"
                "信息不足时只用一句中文追问。"
                "查询今天/全天饮食、吃了什么、摄入热量或营养时，必须调用 "
                "health_query(dimension='diet')；如果同一句还问全天热量消耗、步数或活动，"
                "再调用 health_query(dimension='activity', days=1)。"
                "修改/调整饮食记录时，先用 health_manage(record_type='diet', operation='list') 查候选；"
                "用户明确说早餐/午餐/晚餐/加餐时，list 必须带 date=今天 和 meal_type，"
                "例如晚餐用 meal_type='dinner'，不能拿加餐或其他餐次直接更新。"
                "执行 update 时，若用户明确餐次，data.meal_type 也要保留对应英文枚举。"
                "**若用户的回复是对上一轮助手提问的简短确认/回应**(消息里带「[上一轮助手问我:…]」"
                "且回复是「记录」「好」「嗯」之类),结合上一轮助手的提问判断要记录什么,不要重新泛问。"
            ),
        },
        {"role": "user", "content": user_content},
    ]


def _build_lite_tool_round_messages(
    lite_system: str, messages: List[Dict[str, Any]]
) -> Optional[List[Dict[str, Any]]]:
    """Compact prompt for the **fast-routed tool-decision round** (task_tiered_routing).

    生产实测: advice/query 回合的**首个工具决策轮**已 fast-route 到 qwen3.6-flash,
    但仍背着 ~14k-token 全量栈 (full system prompt 含 8 个分析 blob + 最后一条 user
    里折进的 KB 证据 + 15 轮历史 + 18KB tool schema), flash 白付 6-8s prefill。
    该轮只需从用户消息 + 最近上下文里**挑一个工具、填参数** —— 不需要分析 blob / KB。
    把**这一轮**换成 lite 栈: 专用的工具决策 system prompt（人格、时间、最小写入边界，
    无分析 blob / 无 KB / 无画像）+ 只保留最新 user 消息
    (调用方在 KB/turn-context 折进最后一条 user **之前**快照, 故 KB 天然缺席),
    并把紧邻的上一条非空 assistant 折进 user 做消歧上下文。

    合成/答案轮 (工具后, round_tools=[]) 与快路由失守时仍走**全量栈** —— 面向用户的
    医疗正文永远来自强/显式模型的完整上下文 (见 _messages_for_round / 调用点)。

    **跟进式回复必须保留紧邻的上一条助手回合** (见 _build_fast_record_messages 同款教训
    [[feedback_fast_path_drops_followup_context]]): 助手刚问「要不要帮你分析今天的咖啡因?」
    用户答「好, 顺便看看会不会超标」时, 只发最新 user 消息, 模型无从消歧。折进 user 消息
    (而非发裸 assistant): fast 工具模型走弱代理 (qwen via tokenplan), [system, assistant,
    user] 序列易被严格 OpenAI 兼容适配器拒;折进单条 user 保持 [system, user] 稳态。

    返回 None = 无法安全构建 lite (如最新 user 是多模态 list content) → 调用方 fail-open
    到全量栈, 绝不丢上下文。
    """
    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        return None
    user_content = user_messages[-1].get("content")
    # 多模态 (图片直传) 的 list content 不做字符串折叠 —— fail-open 到全量栈, 由调用方处理。
    if not isinstance(user_content, str):
        return None

    # 紧邻最新用户消息之前的最后一条非空 assistant 回合 —— 跟进式消歧上下文 (截断保持 compact)。
    last_assistant = next(
        (
            m for m in reversed(messages)
            if m.get("role") == "assistant" and str(m.get("content") or "").strip()
        ),
        None,
    )
    if last_assistant:
        prior = str(last_assistant.get("content") or "").strip()[:400]
        user_content = f"[上一轮助手问我：{prior}]\n我的回复：{user_content}"

    return [
        {"role": "system", "content": lite_system},
        {"role": "user", "content": user_content},
    ]


def _friendly_record_confirmation(record: Dict[str, Any]) -> str:
    """Turn a created-record JSON (which has no ``message`` field — it's the raw
    API response) into a short human line, so the fast-record reply never dumps
    raw JSON at the user. Falls back to a generic '已记录' for unknown shapes."""

    def s(key: str) -> Optional[Any]:
        value = record.get(key)
        return value if value not in (None, "", []) else None

    # symptom (/symptoms): body_part + description
    # 症状已免确认前置(直接写) → 回显里给撤销出口,替代原先的"是这样吗?"。
    # 回显必须带记录号:撤销回合走快路由,上下文只剩这行回显 —— 没有 id,
    # 模型删不了(对抗评审实测撤销死环:list 结果又被误读成"已记录 N 条")。
    if s("description") is not None and ("body_part" in record or "severity" in record):
        rid = record.get("id")
        rid_part = f"记录号 {rid},说「撤销」可删除" if rid else "说「撤销」可删除"
        return f"已记录症状：{record.get('description')}（{rid_part}）"
    # blood pressure
    if s("systolic") is not None and s("diastolic") is not None:
        return f"已记录血压 {record.get('systolic')}/{record.get('diastolic')} mmHg"
    # diet
    if s("food_items") is not None:
        return f"已记录饮食：{record.get('food_items')}"
    # weight
    if s("weight") is not None:
        return f"已记录体重 {record.get('weight')} kg"
    # exercise
    if s("exercise_type") is not None:
        reps = s("reps")
        return f"已记录运动：{record.get('exercise_type')}" + (f" {reps} 次" if reps else "")
    # blood glucose (CGM)
    if s("glucose_mg_dl") is not None:
        return f"已记录血糖 {record.get('glucose_mg_dl')} mg/dL"
    # mood
    if s("mood_score") is not None:
        return f"已记录心情 {record.get('mood_score')}/5"  # mood_score 量表 1-5(models/mood.py),非 /10
    # water
    if s("amount") is not None and "drink_type" in record:
        return f"已记录饮水 {record.get('amount')}ml"
    # reminder (/reminders/me)
    if s("title") is not None and ("remind_at" in record or "recurrence" in record):
        recurrence = str(record.get("recurrence") or "").strip().lower()
        prefix = "已设置每日提醒" if recurrence == "daily" else "已设置提醒"
        return f"{prefix}：{record.get('title')}{_reminder_delivery_status_tail(record.get('delivery_status'))}"
    # illness episode
    if s("illness_name") is not None or (s("name") is not None and "start_date" in record):
        return f"已记录：{record.get('illness_name') or record.get('name')}"
    return "✅ 已记录"


# A4: 每回合系统知识库证据卡 memo 的未命中哨兵 (区别于 None = "算过, 无卡")。
_TURN_CARD_UNSET = object()

_WRITE_RECEIPT_TOOL_NAMES = {
    spec.name for spec in list_tool_specs() if spec.receipt_required
}

# Read-only-turn allowlist (starter answer pre-generation · rank7). A pregen turn
# runs the FULL pipeline but must never mutate user data — starter chips are
# analysis/query prompts, never records. Enforcement is fail-CLOSED: only tools on
# this allowlist (plus specialist analysis tools, checked separately) may execute
# in a read-only turn; ANY other tool name (health_record/health_manage/
# intervention_cycle/upload_*/manage_plan/supplement_guide/unknown/future) is
# blocked at the single _execute_tool dispatch choke, so a new write tool is
# denied by default rather than needing to be added to a denylist.
_READ_ONLY_TURN_ALLOWED_TOOLS = {
    spec.name for spec in list_tool_specs() if spec.effect == "read"
}
_WRITE_RESULT_FAILURE_MARKERS = (
    "Error:",
    "[NEEDS_CONFIRMATION]",
    "暂时没成功",
    "没成功",
    "记录失败",
    "未找到",
)
# These errors are produced by the local argument/policy gates before an
# external write endpoint is invoked. They must not be presented as a write
# that may already have happened.
_UNVERIFIED_WRITE_USER_MESSAGE = (
    "本次记录请求的状态暂时无法确认，我不能确认是否已经完成；可能已提交但尚未拿到回执。"
    "为避免重复写入，我没有自动重试；请先查询现有记录，确认缺失后再补录。"
)

_RECEIPT_TYPE_LABELS = {
    "exercise_record": "运动",
    "sleep_record": "睡眠",
    "diet_record": "饮食",
    "water": "饮水",
    "weight_record": "体重",
    "blood_pressure_record": "血压",
    "medication_log": "用药",
    "supplement_log": "补剂",
    "aigc_media_confirmation": "小巴创作草稿",
    "aigc_media_job": "小巴创作",
    "mood_record": "心情",
    "health_checkin": "鼻炎打卡",
    "smart_reminder": "提醒",
    "user_directive": "健康约束",
}


def _unverified_write_message(verified_receipts: Optional[List[Dict[str, Any]]] = None) -> str:
    """部分成功时如实点名已写入项,只对失败项说「无法确认」。

    一刀切否定会让用户以为全部丢失(2026-07-13 实锤:『中午睡了60分钟 走路10分钟』
    走路已写入 exercise#262,睡眠 422 失败,回复却宣称整单无回执 → founder 报
    「没有写入到我的活动」)。诚实 = 既不谎报成功,也不抹掉真实成功。"""
    if not verified_receipts:
        return _UNVERIFIED_WRITE_USER_MESSAGE
    labels: List[str] = []
    for r in verified_receipts[:4]:
        if not isinstance(r, dict):
            continue
        rt = str(r.get("resource_type") or "").strip()
        rid = r.get("resource_id")
        label = _RECEIPT_TYPE_LABELS.get(rt, rt or "记录")
        labels.append(f"{label}(#{rid})" if rid else label)
    if not labels:
        return _UNVERIFIED_WRITE_USER_MESSAGE
    return (
        f"已确认写入:{'、'.join(labels)}。"
        "但另有一项记录请求的状态暂时无法确认,我不能确认它是否已经完成,"
        "可能已提交但尚未拿到回执;"
        "为避免重复写入,我没有自动重试,请先查询该项现有记录,确认缺失后再补录。"
    )


class _UnverifiedWriteResult(RuntimeError):
    pass


class _SimpleRecordTerminal(RuntimeError):
    """Stop a model panel once a typed simple-record outcome is known."""

    def __init__(self, message: str, *, satisfied: bool) -> None:
        super().__init__(message)
        self.message = message
        self.satisfied = satisfied


def _write_result_is_pre_dispatch_validation_error(result: Any) -> bool:
    """Hide only argument/validation rejections the same model turn can repair."""
    outcome = classify_write_execution(result)
    if (
        outcome.status == "rejected"
        and outcome.dispatch_started is False
        and outcome.error_code
        in {
            "diet_nutrition_incomplete",
            "tool_arguments_invalid",
            "tool_validation_failed",
        }
    ):
        return True

    # Compatibility for older adapters that still return prose instead of the
    # structured local_write_rejection contract. Policy/capability denials are
    # terminal and must remain visible; only argument gaps are recoverable in
    # the same model turn.
    if not isinstance(result, str):
        return False
    text = result.strip()
    return (
        text.startswith("Error:")
        and not text.startswith("Error: API 返回 ")
        and any(
            marker in text
            for marker in (
                "参数解析失败",
                "参数无效",
                "必须提供",
                "需要提供",
                "缺少",
            )
        )
    )


def _pre_dispatch_validation_user_message(result: Any) -> str:
    """Turn a recoverable local rejection into a safe terminal explanation."""
    payload: Dict[str, Any] = {}
    if isinstance(result, dict):
        payload = result
    elif isinstance(result, str) and result.strip().startswith("{"):
        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed

    message = str(payload.get("message") or "").strip()
    guidance = str(payload.get("recovery_guidance") or "").strip()
    error_code = str(payload.get("error_code") or "").strip()
    if not message and error_code == "diet_nutrition_incomplete":
        message = (
            "饮食记录缺少完整营养估算，需要提供 calories (>0)、"
            "protein、carbs、fat、fiber。"
        )
    if not message and isinstance(result, str):
        message = result.strip().removeprefix("Error:").strip()
    if not message:
        message = "记录参数不完整。"

    reply = f"这次没有写入：{message}"
    if guidance and guidance not in message:
        reply = f"{reply} {guidance}"
    return reply


_UNVERIFIED_WRITE_SUCCESS_CLAIMS = (
    "已记录",
    "已经记录",
    "记录好了",
    "记录成功",
    "已保存",
    "已经保存",
    "保存好了",
    "保存成功",
    "已写入",
    "写入成功",
    "已更新",
    "已经更新",
    "更新好了",
    "更新成功",
    "已修改",
    "修改成功",
    "已删除",
    "删除成功",
    "已同步",
    "同步成功",
    "已创建",
    "创建成功",
    "操作已完成",
)
_UNVERIFIED_WRITE_CLAUSE_SPLIT_RE = re.compile(
    r"(?:[，,。！？!?；;\n]|但是|但|不过|然而|并且|且|同时|另外|此外|然后)"
)
_UNVERIFIED_WRITE_NEGATION_TERMS = (
    "尚未",
    "还没有",
    "还没",
    "没有",
    "未能",
    "没能",
    "无法",
    "不能",
    "不确定",
    "未确认",
)
_UNVERIFIED_WRITE_POST_NEGATION_TERMS = (
    "并不准确",
    "并非事实",
    "不准确",
    "不代表",
    "不等于",
    "无法确认",
    "不能确认",
    "尚未确认",
    "仍待确认",
    "存疑",
)


def _claims_unverified_write_success(text: Any) -> bool:
    """Detect a model success claim that cannot replace a verified receipt."""
    normalized = "".join(str(text or "").split()).lower()
    if not normalized:
        return False
    for clause in _UNVERIFIED_WRITE_CLAUSE_SPLIT_RE.split(normalized):
        for claim in _UNVERIFIED_WRITE_SUCCESS_CLAIMS:
            start = clause.find(claim)
            while start >= 0:
                prefix = clause[:start]
                suffix = clause[start + len(claim):]
                negated_before = any(
                    term in prefix
                    for term in _UNVERIFIED_WRITE_NEGATION_TERMS
                )
                negated_after = any(
                    term in suffix[:16]
                    for term in _UNVERIFIED_WRITE_POST_NEGATION_TERMS
                )
                if not negated_before and not negated_after:
                    return True
                start = clause.find(claim, start + len(claim))
    return False


_RESOURCE_TYPE_BY_RECORD_TYPE = dict(
    HEALTH_RECORD_RECEIPT_RESOURCE_TYPE_BY_RECORD_TYPE
)

_HEALTH_MANAGE_RESOURCE_TYPE_BY_RECORD_TYPE = dict(
    HEALTH_MANAGE_RECEIPT_RESOURCE_TYPE_BY_RECORD_TYPE
)

_MANAGE_PLAN_RESOURCE_TYPE_BY_ACTION = {
    "generate_weekly": "smart_plan",
    "complete_item": "smart_plan_item",
    "save_to_card": "action_card",
}

_FIXED_RECEIPT_RESOURCE_TYPE_BY_TOOL = {
    "draft_aigc_media": "aigc_media_confirmation",
    "intervention_cycle": "intervention_cycle",
    "user_directive": "user_directive",
    "upload_genetic_txt": "genetic_profile",
    "upload_medical_exam_text": "medical_exam",
}


def _result_payload_sources(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Return every supported producer envelope used to verify a write result."""
    sources = [payload]
    sources.extend(
        nested
        for container_name in ("resource", "record", "data", "result")
        if isinstance((nested := payload.get(container_name)), dict)
    )
    return sources


def _write_result_payload(
    result: Any,
    *,
    allow_pending: bool = False,
    allowed_statuses: Collection[str] = (),
) -> Optional[Dict[str, Any]]:
    if isinstance(result, dict):
        payload = result
    elif isinstance(result, str):
        text = result.strip()
        if not text or any(marker in text for marker in _WRITE_RESULT_FAILURE_MARKERS):
            return None
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    else:
        return None
    if not isinstance(payload, dict):
        return None
    verification_sources = _result_payload_sources(payload)
    if any(
        "verified" in source and source.get("verified") is not True
        for source in verification_sources
    ):
        return None
    if any(
        write_result_declares_non_success(
            source,
            allow_pending=allow_pending,
            allowed_statuses=allowed_statuses,
        )
        for source in verification_sources
    ):
        return None
    if any(
        marker in str(source.get("message") or "")
        for source in verification_sources
        for marker in _WRITE_RESULT_FAILURE_MARKERS
    ):
        return None
    return payload


def _result_with_resource_type(result: Any, resource_type: str) -> Any:
    """Attach receipt identity when an endpoint response has id but no resource_type."""
    if not isinstance(result, str):
        return result
    try:
        payload = json.loads(result)
    except (json.JSONDecodeError, TypeError, ValueError):
        return result
    if not isinstance(payload, dict):
        return result
    payload.setdefault("resource_type", resource_type)
    return json.dumps(payload, ensure_ascii=False)


_SLEEP_START_EVENT_RE = re.compile(
    r"(?:准备|开始|要|打算|现在|刚刚|刚才|记录).{0,8}(?:睡觉|睡眠|入睡|上床)"
    r"|(?:睡觉|睡眠|入睡|上床).{0,8}(?:开始|准备|了|啦)"
)
_PAST_SLEEP_EVENT_RE = re.compile(r"(?:昨晚|昨夜|昨天|前天|上周|上个月|之前)")


def _looks_like_sleep_start_event(user_message: Any, data: Any) -> bool:
    """Current sleep-start utterances are life events, not complete sleep records."""
    parts = [str(user_message or "")]
    if isinstance(data, dict):
        for key in ("title", "name", "event", "notes", "description"):
            value = data.get(key)
            if value not in (None, ""):
                parts.append(str(value))
    text = " ".join(part.strip() for part in parts if part and str(part).strip())
    if not text or _PAST_SLEEP_EVENT_RE.search(text):
        return False
    return bool(_SLEEP_START_EVENT_RE.search(text))


def _write_checkpoint_status_after_dispatch(
    result: Any,
    receipt: Optional[Dict[str, Any]],
) -> str:
    """Return the durable status from the structured write outcome."""
    return classify_write_execution(result, receipt=receipt).status


def _write_outcome_event_fields(
    result: Any,
    receipt: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Expose the write state machine without asking clients to parse prose."""
    outcome = classify_write_execution(result, receipt=receipt)
    return {
        "write_outcome": outcome.status,
        "dispatch_started": outcome.dispatch_started,
        "resubmit_safe": bool(
            outcome.dispatch_started is False
            and outcome.status in {"rejected", "failed"}
        ),
        "error_code": outcome.error_code,
    }


def _write_operation_fingerprint(
    tool_name: str,
    parsed_args: Dict[str, Any],
) -> str:
    from app.services.agent_runtime_identity import runtime_hmac_digest

    return runtime_hmac_digest(
        "write-operation-fingerprint-v1",
        tool_name,
        parsed_args,
    )


def _runtime_write_operation_fingerprint(
    tool_name: str,
    parsed_args: Dict[str, Any],
    *,
    default_record_date: str | None = None,
) -> str:
    """Canonical business identity for Runtime write deduplication.

    This is deliberately separate from the turn-local checkpoint fingerprint:
    confirmation fields still matter to the conversation flow, but they must
    not create a second durable write identity for the same business action.
    """
    canonical_args = dict(parsed_args)
    if tool_name == "health_record":
        record_type = (
            canonical_args.get("record_type")
            or canonical_args.get("type")
            or canonical_args.get("kind")
        )
        normalized_record_type = ""
        if record_type not in (None, ""):
            normalized_record_type = _normalize_fast_record_kind(
                record_type
            )
            canonical_args["record_type"] = normalized_record_type
        canonical_args.pop("type", None)
        canonical_args.pop("kind", None)
        if normalized_record_type == "diet":
            canonical_args = {
                "record_type": "diet",
                "data": _normalize_diet_create_data(
                    canonical_args,
                    default_record_date=default_record_date,
                ),
            }
    elif tool_name == "intervention_cycle":
        action = str(canonical_args.get("action") or "").strip().lower()
        canonical_args["action"] = "cancel" if action == "delete" else action
        canonical_args.pop("confirm", None)
        canonical_args.pop("confirmed", None)
    elif tool_name == "health_manage":
        operation = str(canonical_args.get("operation") or "").strip().lower()
        if operation:
            canonical_args["operation"] = operation
        canonical_args.pop("confirm", None)
        canonical_args.pop("confirmed", None)
    return _write_operation_fingerprint(tool_name, canonical_args)


_DIET_CREATE_TOP_LEVEL_FIELDS = (
    "meal_type",
    "meal_time",
    "food_items",
    "food_id",
    "source",
    "calories",
    "protein",
    "carbs",
    "fat",
    "fiber",
    "alcohol_units",
    "notes",
    "ai_recognized",
    "ai_confidence",
    "ai_raw_result",
    "health_tips",
    "image_base64",
    "image_type",
    "photo_draft_token",
)


def _normalize_diet_create_data(
    parsed_args: Dict[str, Any],
    *,
    default_record_date: str | None = None,
) -> Dict[str, Any]:
    """Build the canonical diet payload shared by Runtime identity and dispatch."""
    args = dict(parsed_args or {})
    raw_data = args.get("data")
    if isinstance(raw_data, dict):
        data = dict(raw_data)
    elif isinstance(raw_data, str):
        try:
            decoded = json.loads(raw_data)
        except (json.JSONDecodeError, ValueError, TypeError):
            decoded = None
        data = dict(decoded) if isinstance(decoded, dict) else {}
    else:
        data = {}

    for field in _DIET_CREATE_TOP_LEVEL_FIELDS:
        if data.get(field) in (None, "", []) and args.get(field) not in (
            None,
            "",
            [],
        ):
            data[field] = args[field]

    raw_record_date = (
        data.get("record_date")
        or args.get("record_date")
        or args.get("date")
        or default_record_date
    )
    if raw_record_date not in (None, "", []):
        try:
            if isinstance(raw_record_date, datetime):
                canonical_date = raw_record_date.date()
            elif isinstance(raw_record_date, date):
                canonical_date = raw_record_date
            else:
                canonical_date = date.fromisoformat(
                    str(raw_record_date).strip()[:10]
                )
            data["record_date"] = canonical_date.isoformat()
        except (TypeError, ValueError):
            data["record_date"] = str(raw_record_date).strip()

    raw_meal_type = data.get("meal_type")
    if raw_meal_type in (None, "", []):
        data["meal_type"] = "snack"
    else:
        data["meal_type"] = (
            _normalize_diet_meal_type(raw_meal_type)
            or str(raw_meal_type).strip().lower()
        )

    raw_meal_time = data.get("meal_time")
    if raw_meal_time not in (None, "", []):
        try:
            meal_time_text = str(raw_meal_time).strip()
            single_digit_hour = re.fullmatch(r"(\d):(.*)", meal_time_text)
            if single_digit_hour:
                meal_time_text = (
                    f"0{single_digit_hour.group(1)}:{single_digit_hour.group(2)}"
                )
            parsed_time = (
                raw_meal_time
                if isinstance(raw_meal_time, datetime_time)
                else datetime_time.fromisoformat(meal_time_text)
            )
            # Diet API persists only wall-clock hour and minute.
            data["meal_time"] = parsed_time.strftime("%H:%M")
        except (TypeError, ValueError):
            data["meal_time"] = str(raw_meal_time).strip()

    if isinstance(data.get("food_items"), list):
        data["food_items"] = ", ".join(
            item.get("name", str(item)) if isinstance(item, dict) else str(item)
            for item in data["food_items"]
        )
    elif not data.get("food_items"):
        data["food_items"] = data.get("description", data.get("notes", ""))
    # Conversation authorization fields are never part of DietRecord.  Strip
    # them before fingerprinting and dispatch so a model retry cannot turn an
    # equivalent business write into a new Runtime identity.
    for control_field in (
        "confirm",
        "confirmed",
        "_fast_record_requires_confirmation",
    ):
        data.pop(control_field, None)
    return data


def _runtime_write_operation_identity(
    tool_name: str,
    parsed_args: Dict[str, Any],
    *,
    default_record_date: str | None = None,
) -> tuple[
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[str],
]:
    """Return an opaque, order-independent business target for safe retries.

    A Runtime retry may cause the model to reorder calls or recompute mutable
    values. We only bridge those argument changes when the target is explicit:
    a record id for mutations, or a photo token / normalized meal-item target
    for a diet create. Other writes fall back to exact-fingerprint matching and
    are rejected if a retry introduces a new, unprovable side effect.
    """
    from app.services.agent_runtime_identity import runtime_hmac_digest

    args = dict(parsed_args or {})
    record_type = _normalize_fast_record_kind(
        args.get("record_type") or args.get("type") or args.get("kind") or ""
    )
    action = str(args.get("operation") or args.get("action") or "").strip().lower()
    if tool_name == "intervention_cycle" and action == "delete":
        action = "cancel"

    target_id = next(
        (
            str(args[key]).strip()
            for key in (
                "record_id",
                "event_id",
                "log_id",
                "cycle_id",
                "item_id",
                "plan_id",
                "card_id",
                "exam_id",
                "id",
            )
            if args.get(key) not in (None, "", False)
        ),
        None,
    )
    identity: Optional[Dict[str, str]] = None
    scope_identity: Optional[Dict[str, str]] = None
    discriminator_kind: Optional[str] = None
    discriminator_identity: Optional[Mapping[str, str] | str] = None
    if target_id:
        identity = {
            "tool": tool_name,
            "action": action,
            "record_type": record_type,
            "target_id": target_id,
        }
    elif tool_name == "health_record" and record_type == "diet":
        data = _normalize_diet_create_data(
            args,
            default_record_date=default_record_date,
        )
        photo_token = str(data.get("photo_draft_token") or "").strip()
        record_date = str(data.get("record_date") or "").strip()
        meal_type = str(data.get("meal_type") or "").strip()
        food_items = str(data.get("food_items") or "")
        normalized_food_items = re.sub(
            r"[\s,，、;；/|]+",
            "",
            food_items,
        ).casefold()
        meal_time = str(data.get("meal_time") or "").strip()
        # Scope is the normalized business slot, not model-generated food
        # wording. A missing date is filled from this Turn's reference time at
        # the call site, matching the eventual write adapter.
        scope_identity = {
            "tool": tool_name,
            "record_type": record_type,
            **(
                {"record_date": record_date, "meal_type": meal_type}
                if record_date and meal_type
                else {}
            ),
        }
        if photo_token:
            identity = {
                "tool": tool_name,
                "record_type": record_type,
                "photo_token": photo_token,
            }
            discriminator_kind = "photo_token"
            discriminator_identity = photo_token
        elif record_date and meal_type and normalized_food_items:
            identity = {
                "tool": tool_name,
                "record_type": record_type,
                "record_date": record_date,
                "meal_type": meal_type,
                "item_identity": runtime_hmac_digest(
                    "diet-item-identity-v1",
                    normalized_food_items,
                ),
            }
            if meal_time:
                identity["meal_time"] = meal_time
        if not photo_token and record_date and meal_type:
            if meal_time:
                discriminator_kind = "meal_time"
                discriminator_identity = meal_time
    if identity is None and scope_identity is None:
        return None, None, None, None

    def opaque(prefix: str, value: Mapping[str, str] | str) -> str:
        return f"{prefix}:" + runtime_hmac_digest(
            f"write-logical-{prefix}-v1",
            value,
        )

    return (
        opaque("target", identity) if identity is not None else None,
        opaque("scope", scope_identity) if scope_identity is not None else None,
        discriminator_kind,
        (
            opaque("discriminator", discriminator_identity)
            if discriminator_identity is not None
            else None
        ),
    )


def _runtime_write_logical_operation_key(
    tool_name: str,
    parsed_args: Dict[str, Any],
) -> Optional[str]:
    return _runtime_write_operation_identity(tool_name, parsed_args)[0]


def _recoverable_write_operation_key(
    tool_name: str,
    parsed_args: Dict[str, Any],
    *,
    default_record_date: str | None = None,
) -> str:
    """Stable key for one logical write while the model repairs its arguments.

    Exact argument fingerprints cannot correlate a rejected draft with a
    corrected retry because the corrected fields necessarily change. Prefer a
    durable target identity, then the narrow business scope, and finally a
    record-type/action scope. This prevents an unrelated successful write from
    clearing another operation's unresolved rejection.
    """
    from app.services.agent_runtime_identity import runtime_hmac_digest

    target_key, scope_key, _kind, _discriminator = (
        _runtime_write_operation_identity(
            tool_name,
            parsed_args,
            default_record_date=default_record_date,
        )
    )
    if target_key:
        return target_key
    if scope_key:
        return scope_key

    record_type = _normalize_fast_record_kind(
        parsed_args.get("record_type")
        or parsed_args.get("type")
        or parsed_args.get("kind")
        or ""
    )
    action = str(
        parsed_args.get("operation")
        or parsed_args.get("action")
        or "create"
    ).strip().lower()
    raw_data = parsed_args.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else dict(parsed_args)
    discriminator_fields = {
        "blood_pressure": ("systolic", "diastolic"),
        "bp": ("systolic", "diastolic"),
        "exercise": ("exercise_type", "activity_type", "duration", "distance"),
        "mood": ("mood", "score"),
        "sleep": ("record_date", "date", "sleep_quality"),
        "symptom": ("description", "symptom", "name", "title"),
        "waist": ("waist", "value"),
        "water": ("amount", "amount_ml", "ml"),
        "weight": ("weight", "value"),
    }.get(record_type, ())
    discriminator = {
        field: str(data[field]).strip().casefold()
        for field in discriminator_fields
        if data.get(field) not in (None, "", [])
    }
    if discriminator:
        return "rejection-target:" + runtime_hmac_digest(
            "recoverable-write-rejection-target-v1",
            {
                "tool": tool_name,
                "record_type": record_type,
                "action": action,
                "discriminator": discriminator,
            },
        )
    return _recoverable_write_scope_key(
        tool_name,
        parsed_args,
    )


def _recoverable_write_scope_key(
    tool_name: str,
    parsed_args: Dict[str, Any],
) -> str:
    """Return the stable coarse slot shared by a rejected draft and its repair."""
    from app.services.agent_runtime_identity import runtime_hmac_digest

    record_type = _normalize_fast_record_kind(
        parsed_args.get("record_type")
        or parsed_args.get("type")
        or parsed_args.get("kind")
        or ""
    )
    action = str(
        parsed_args.get("operation")
        or parsed_args.get("action")
        or "create"
    ).strip().lower()
    return "rejection-scope:" + runtime_hmac_digest(
        "recoverable-write-rejection-scope-v1",
        {
            "tool": tool_name,
            "record_type": record_type,
            "action": action,
        },
    )


def _goal_binds_recoverable_write(
    goal: Optional[GoalSpec],
    tool_name: str,
    parsed_args: Dict[str, Any],
) -> bool:
    """Allow coarse repair matching only for one explicit write target.

    Attachment-backed diet turns cannot become ``simple_health_record`` goals:
    the server must let the model read the label before it can build the
    nutrition payload. They still compile to one bounded ``diet/create`` goal,
    so a later verified estimate is allowed to repair an older validation
    rejection for that meal. Multi-meal and cross-domain turns stay isolated.
    """
    if (
        goal is None
        or goal.operation != "create"
        or tool_name != "health_record"
    ):
        return False
    record_type = _normalize_fast_record_kind(
        parsed_args.get("record_type")
        or parsed_args.get("type")
        or parsed_args.get("kind")
        or ""
    )
    if (
        goal.kind == "simple_health_record"
        and record_type
        and record_type == str(goal.target_record_type or "").strip().lower()
    ):
        return True
    return bool(
        goal.kind == "write"
        and goal.domain == "diet"
        and record_type == "diet"
        and len(goal.target_meal_types) <= 1
    )


def _clear_repaired_write_rejections(
    pending: dict[str, tuple[str, str]],
    rounds: dict[str, int],
    scopes: dict[str, str],
    *,
    operation_key: str,
    scope_key: str,
    current_round: int,
    allow_scope_repair: bool,
) -> None:
    """Clear an older validation rejection repaired by a verified write.

    A model may refine the target text while filling missing fields, for
    example ``坚果 20g`` -> ``品牌每日坚果 20g``.  Those calls have different
    target hashes but still belong to one bounded create goal. Scope repair is
    therefore limited to older rounds of that explicit single-target goal;
    same-round and multi-target writes remain independent.
    """
    pending.pop(operation_key, None)
    rounds.pop(operation_key, None)
    scopes.pop(operation_key, None)
    if not allow_scope_repair:
        return

    repaired_keys = [
        key
        for key, rejection_scope in scopes.items()
        if rejection_scope == scope_key
        and rounds.get(key, current_round) < current_round
    ]
    for key in repaired_keys:
        pending.pop(key, None)
        rounds.pop(key, None)
        scopes.pop(key, None)


def _summarize_recoverable_write_rejections(
    pending: Mapping[str, tuple[str, str]],
) -> tuple[Optional[str], Optional[str]]:
    if not pending:
        return None, None
    unique_items = list(pending.values())
    if len(unique_items) == 1:
        return unique_items[0]

    details = []
    for index, (message, _code) in enumerate(unique_items, start=1):
        detail = message.removeprefix("这次没有写入：").strip()
        details.append(f"{index}. {detail}")
    summary = (
        f"这次有 {len(unique_items)} 项没有写入：\n"
        + "\n".join(details)
    )
    summary_code = (
        "diet_nutrition_incomplete"
        if any(
            code == "diet_nutrition_incomplete"
            for _message, code in unique_items
        )
        else unique_items[-1][1]
    )
    return summary, summary_code


def _write_rejection_with_receipt_context(
    rejection: str,
    write_receipts: Sequence[Mapping[str, Any]],
) -> str:
    if not write_receipts:
        return rejection
    return (
        f"另有 {len(write_receipts)} 项记录已完成并取得回执。\n\n"
        f"{rejection}"
    )


# 只读工具回合级去重(founder 2026-07-14「列出喝水记录」→ health_query 空转 7 次 70s 根因)。
# 镜像写工具的 fingerprint replay,但只对**只读**工具(写工具重复要走确认链,绝不盲去重)。
_READ_DEDUP_ENABLED = True


def _read_operation_fingerprint(tool_name: str, parsed_args: Dict[str, Any]) -> str:
    """只读工具去重指纹。health_query/batch 先归一(维度别名 / time_range→days),避免
    "同义不同字面"漏判;归一失败退回原参(fail-open,宁多跑一次别漏数据)。"""
    if tool_name in ("health_query", "health_query_batch"):
        try:
            parsed_args = _normalize_health_query_args(parsed_args)
        except Exception:  # noqa: BLE001
            pass
    return _write_operation_fingerprint(tool_name, parsed_args)


def _tool_call_is_read_only(tool_name: str, parsed_args: Dict[str, Any]) -> bool:
    """Classify mixed read/write tools by operation instead of only by name."""
    try:
        return classify_tool_effect(tool_name, parsed_args) == "read"
    except (UnknownToolAction, RuntimeError):
        return False


def _is_seen_readonly_call(tc: Dict[str, Any], seen_read_fps: Dict[str, Any]) -> bool:
    """本轮 tool_call 是否是"本回合已跑过"的只读调用(收敛护栏用: 全是则强制进合成停 loop)。"""
    fn = tc.get("function") or {}
    name = fn.get("name")
    raw = fn.get("arguments")
    try:
        args = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not _tool_call_is_read_only(name, args):
        return False
    return _read_operation_fingerprint(name, args) in seen_read_fps


def _receipt_resource_identity(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    id_keys = (
        "id",
        "resource_id",
        "record_id",
        "event_id",
        "log_id",
        "cycle_id",
        "exam_id",
    )

    def read_ids(source: Dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in id_keys:
            value = source.get(key)
            if isinstance(value, bool) or value in (None, ""):
                continue
            normalized = str(value).strip()
            if normalized:
                values.append(normalized)
        return values

    resource_ids = read_ids(payload)
    resource_types = [
        normalized
        for value in (payload.get("resource_type"),)
        if (normalized := str(value or "").strip())
    ]
    for container_name in ("resource", "record", "data", "result"):
        nested = payload.get(container_name)
        if not isinstance(nested, dict):
            continue
        resource_ids.extend(read_ids(nested))
        nested_type = nested.get("resource_type")
        if container_name == "resource" and not nested_type:
            nested_type = nested.get("type")
        normalized_type = str(nested_type or "").strip()
        if normalized_type:
            resource_types.append(normalized_type)

    unique_ids = list(dict.fromkeys(resource_ids))
    unique_types = list(dict.fromkeys(resource_types))
    if len(unique_ids) > 1 or len(unique_types) > 1:
        return None, None
    return (
        unique_types[0] if unique_types else None,
        unique_ids[0] if unique_ids else None,
    )


def _receipt_target_date(
    payload: Dict[str, Any],
    args: Dict[str, Any],
) -> tuple[Optional[str], bool]:
    """Return one agreed ISO-like target date; reject contradictory aliases."""
    values: list[str] = []
    for source in (payload, args):
        for container in _result_payload_sources(source):
            for key in ("date", "record_date"):
                value = container.get(key)
                if value in (None, ""):
                    continue
                normalized = str(value).strip()
                if normalized:
                    values.append(normalized)
    unique = list(dict.fromkeys(values))
    if len(unique) > 1:
        return None, True
    return (unique[0] if unique else None), False


def _write_receipt_from_tool_result(
    tool_name: str,
    receipt_context: Any,
    result: Any,
) -> Optional[Dict[str, Any]]:
    """Build a persistence receipt from structured tool output only."""
    if tool_name not in _WRITE_RECEIPT_TOOL_NAMES:
        return None
    if isinstance(receipt_context, Mapping):
        args = dict(receipt_context)
    else:
        args = {"record_type": receipt_context}
    normalized_record_type = str(
        args.get("record_type") or args.get("type") or ""
    ).strip().lower()
    normalized_action = str(args.get("action") or "").strip().lower()
    if tool_name in {"health_record", "health_manage"}:
        expected_resource_type = expected_receipt_resource_type(tool_name, args)
    elif tool_name == "manage_plan":
        expected_resource_type = _MANAGE_PLAN_RESOURCE_TYPE_BY_ACTION.get(
            normalized_action
        )
    else:
        expected_resource_type = _FIXED_RECEIPT_RESOURCE_TYPE_BY_TOOL.get(
            tool_name
        )
    if not expected_resource_type:
        return None
    payload = _write_result_payload(
        result,
        allow_pending=(
            tool_name == "health_record"
            and normalized_record_type == "reminder"
        ),
        allowed_statuses=(
            {"pending_user_confirmation"}
            if tool_name == "draft_aigc_media"
            else set()
        ),
    )
    if payload is None:
        return None
    # "准备开始睡觉" uses health_record(sleep) as the conversational
    # capability but persists a life-event anchor, not a completed sleep row.
    # The endpoint response shape is deterministic even when legacy responses
    # omit resource_type, so infer the narrower registered receipt type here.
    if (
        tool_name == "health_record"
        and normalized_record_type == "sleep"
        and payload.get("occurred_at")
        and payload.get("title")
    ):
        expected_resource_type = "health_episode"
    result_resource_type, resource_id = _receipt_resource_identity(payload)
    if not resource_id:
        return None
    if result_resource_type and result_resource_type != expected_resource_type:
        return None
    resource_type = expected_resource_type
    if not is_registered_receipt_resource_type(tool_name, resource_type):
        return None
    if not is_valid_receipt_resource_id(tool_name, resource_id):
        return None
    target_date, target_date_conflict = _receipt_target_date(payload, args)
    if target_date_conflict:
        return None
    completed_at = (
        payload.get("completed_at")
        or payload.get("updated_at")
        or payload.get("created_at")
        or datetime.now(UTC).isoformat()
    )
    operation_id = str(
        payload.get("operation_id")
        or f"{tool_name}:{resource_type}:{resource_id}"
    )
    receipt = {
        "operation_id": operation_id,
        "status": "verified",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "completed_at": str(completed_at),
        "verified": True,
    }
    if target_date:
        receipt["date"] = target_date
    return receipt


def _write_tool_completed(tool_name: str, args: Any, result: Any) -> bool:
    try:
        parsed_args = json.loads(args) if isinstance(args, str) else dict(args or {})
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed_args = {}
    if not _write_tool_attempted(tool_name, parsed_args):
        return False
    if isinstance(result, str):
        text = result.strip()
        if not text or any(marker in text for marker in _WRITE_RESULT_FAILURE_MARKERS):
            return False
        try:
            json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            # A write without structured identity cannot be verified. Treat legacy
            # prose as incomplete so old clients and telemetry also fail closed.
            return False
    return _write_receipt_from_tool_result(tool_name, parsed_args, result) is not None


# health_record 的 record_type 里，个别是**触发动作**而非写记录 —— 它们没有
# resource id，不产写回执，绝不能进写诚实闸(否则真成功 / MFA 失败 / 未绑定都会被
# 误判成"未取得可验证写入回执"，把真因盖掉、还驱动无谓重试)。garmin_sync = 异步
# 同步 job，是这类的第一个成员。匹配 record_type 与 type 双键(模型两种都吐过)。
_NON_WRITE_RECORD_TYPES: frozenset[str] = get_tool_spec(
    "health_record"
).receipt_exempt_record_types


# Apple 健康(HealthKit)数据只能由 iPhone 上的 App 在前台读取后**上传**到后端 ——
# 后端物理上无法主动"拉取"HealthKit。弱模型会把"同步 apple healthkit"塌缩成
# record_type='garmin_sync',触发 Garmin 同步、并让 LLM 谎报"后台正在拉取 Apple
# Health"(结构性 honesty 违规:该动作不可能为真)。命中此意图 → 返回确定性真话指引,
# 绝不入队 garmin sync、绝不谎称后台拉取。锚在用户原话(非模型参数),不受弱模型塌缩影响。
_HEALTHKIT_SYNC_RE = re.compile(
    r"(healthkit|health\s*kit|apple\s*health|苹果\s*健康|苹果健康数据)", re.I
)


def _is_healthkit_sync_intent(text: Optional[str]) -> bool:
    """用户原话是否明确指向 Apple 健康/HealthKit 同步(而非 Garmin/通用同步)。"""
    return bool(text) and bool(_HEALTHKIT_SYNC_RE.search(text))


def _write_tool_attempted(tool_name: str, args: Any) -> bool:
    """Return whether this invocation crossed a write boundary, even if it failed."""
    try:
        parsed_args = json.loads(args) if isinstance(args, str) else dict(args or {})
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed_args = {}
    try:
        return requires_verified_receipt(tool_name, parsed_args)
    except (UnknownToolAction, RuntimeError):
        return False


def _safety_warning_suffix_from_tool_results(messages: List[Dict[str, Any]]) -> str:
    """收集 tool results 里的 '⚠️ 安全提示' 文本段(写后安全评估 :2763 追加的)。

    post_record_quality 的新回复模板从 record args/画像组装,不看 tool result ——
    曾把安全文本从用户可见回复中整体丢掉(老客户端不渲染 safety 卡,文本是唯一
    载体;CI test_agent_stream_keeps_safety_text_visible_for_old_clients 抓出)。
    加层不减层:无论哪个模板产出 final_text,安全后缀都必须强制携带。
    """
    warnings: list[str] = []
    for message in messages:
        if message.get("role") != "tool":
            continue
        content = str(message.get("content") or "")
        marker_idx = content.find(SAFETY_WARNING_MARKER)
        if marker_idx >= 0:
            segment = content[marker_idx:].strip()
            if segment and segment not in warnings:
                warnings.append(segment)
    return "\n\n".join(warnings)


def _recover_tool_result_payload(content: str) -> Any:
    """严格 json.loads 失败后,尽力把工具结果 content 救回成 list/dict。

    _api_get 的返回不保证严格可解析(它自己在 docstring 里写明"可能被字符截断,
    不可直接 json.loads"):list/dict 会被加尾注("...(仅显示前10条)"/"...(数据已截断)")
    或硬字符截断。这些是**结构化工具结果**,不是人话纯文本 —— 不救回就会掉进裸 dump。

    逐级救:
      (1) 从第一个 `[`/`{` 起 raw_decode —— 吃掉尾部杂质,救回合法 JSON 前缀
          (Path A:合法数组 + "...(仅显示前10条)" 尾注)。
      (2) _loads_lenient —— 救弯/全角引号 + 可修复的截断(与 leak 护栏同一解析器)。
    仍救不回(如硬截断到半个 token)返回 None,调用方走锚定 leak 探测兜底。
    """
    s = (content or "").strip()
    if not s:
        return None
    lb = s.find("[")
    ob = s.find("{")
    starts = [i for i in (lb, ob) if i != -1]
    if starts:
        start = min(starts)
        try:
            payload, _ = json.JSONDecoder().raw_decode(s[start:])
            if isinstance(payload, (list, dict)):
                return payload
        except json.JSONDecodeError:
            pass
    try:
        payload = _loads_lenient(s)
        if isinstance(payload, (list, dict)):
            return payload
    except json.JSONDecodeError:
        pass
    return None


def _fast_record_reply_from_tool_results(messages: List[Dict[str, Any]]) -> str:
    """Build a final user-visible reply directly from record tool results."""

    replies: list[str] = []
    for message in messages:
        if message.get("role") != "tool":
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        safety_warning = ""
        marker_idx = content.find(SAFETY_WARNING_MARKER)
        if marker_idx >= 0:
            safety_warning = content[marker_idx:].strip()
            content = content[:marker_idx].strip()

        def append_safety_warning() -> None:
            if safety_warning:
                replies.append(safety_warning)

        if content.startswith("[NEEDS_CONFIRMATION]"):
            prompt = content.replace("[NEEDS_CONFIRMATION]", "", 1).strip()
            prompt = prompt.split("请向用户", 1)[0].strip()
            if prompt.endswith("."):
                prompt = prompt[:-1].strip()
            replies.append(f"{prompt}。是这样吗？")
            append_safety_warning()
            continue
        if content.startswith("Error"):
            replies.append(content)
            append_safety_warning()
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = None
        if payload is None:
            # 严格 json.loads 失败,但 _api_get 会给 list/dict 加尾注
            # ("...(仅显示前10条)" / "...(数据已截断)") 或硬字符截断 —— 这些都不是
            # "人话纯文本",而是**结构化工具结果**。先按泄漏护栏用的宽松/前缀解析救回,
            # 让它落进下面 dict/list 分支给出「查到 N 条」/友好确认,绝不裸 dump。
            # (raw_decode 吃掉尾部杂质救回合法前缀;_loads_lenient 救弯引号+可修复的截断。)
            payload = _recover_tool_result_payload(content)
        if isinstance(payload, dict):
            tool_message = payload.get("message")
            if isinstance(tool_message, str) and tool_message.strip():
                replies.append(tool_message.strip())
                append_safety_warning()
                continue
            # Created-record JSON with no `message` — synthesize a human line
            # instead of dumping raw JSON (the user complaint).
            replies.append(_friendly_record_confirmation(payload))
            append_safety_warning()
            continue
        if isinstance(payload, list):
            # 数组结果来自 health_manage list(查 ID/查记录)——绝不能说"已记录 N 条":
            # 对抗评审实测,用户说"撤销"、模型转去 list 查 ID,却被答复"✅已记录 2 条"
            # = 假写入宣称。当前没有任何 health_record 创建路径返回数组。
            if not payload:
                replies.append("没有找到相关记录")
            else:
                ids = [str(it.get("id")) for it in payload if isinstance(it, dict) and it.get("id")]
                id_part = f"（记录号: {', '.join(ids[:5])}）" if ids else ""
                replies.append(f"查到 {len(payload)} 条记录{id_part}")
            append_safety_warning()
            continue
        # 到这里 payload 仍非 dict/list(连宽松/前缀解析都救不回,如硬字符截断到半个
        # token 的 `[{"…"calories":`)。若 content 长得就是一段工具结果原始 JSON dump,
        # **绝不**裸 dump[:160](founder 复现:那正是泄漏的来源)——改吐一句非空中性人话。
        # 非空是承重的(memory:空兜底→重试风暴→更多泄漏)。真人话纯文本(无 JSON 结构)
        # 仍原样透出。三层锚定,fail-closed 收口:
        #   (1) _leaks_tool_result_json —— 整段可宽松解析的 dump;
        #   (2) _streaming_leak_forming —— `[{"<白名单键>":` 数组签名(救截断到半 token 的);
        #   (3) 结构起手 —— 去空白后以 `{`/`[` 开头 = 未救回的结构化载荷。补 (1)(2) 的洞:
        #       裸对象 `{"food_items":` 截断在**单个**白名单键后,(1)(2) 都判不出((2) 对
        #       非 `[{` 的裸对象要求 ≥2 键),但真人话工具结果永远以中文/字母起手
        #       (已更新记录 / 你今天喝了… / 没有找到…),绝不以裸 `{`/`[` 开头 → 不误伤。
        stripped = content.lstrip()
        looks_structured = bool(stripped) and stripped[0] in "{["
        if _leaks_tool_result_json(content) or _streaming_leak_forming(content) or looks_structured:
            # 中性、不预设意图:旧文案"请再说一次要改哪一条"是记录**修改**味,对分析/查询
            # 语境是废话(2026-07-13 turn 6334 violation #2)。这里只表达"这条结果没整理出来",
            # 绝不谎称已写入,也不假设用户在改记录。
            replies.append("这条结果暂时没能整理成文字。")
            append_safety_warning()
            continue
        # Plain-text tool result (already human-readable) — show as-is.
        replies.append(content.replace("\n", " ")[:160])
        append_safety_warning()

    deduped: list[str] = []
    for reply in replies:
        if reply and reply not in deduped:
            deduped.append(reply)
    return "\n".join(deduped).strip()


def _pending_confirmation_reply_from_tool_results(
    messages: List[Dict[str, Any]],
) -> str:
    """Render only intentional confirmation pauses from a mixed transcript."""
    pending_messages = [
        message
        for message in messages
        if message.get("role") == "tool"
        and str(message.get("content") or "").lstrip().startswith(
            "[NEEDS_CONFIRMATION]"
        )
    ]
    return _fast_record_reply_from_tool_results(pending_messages)


def _auto_confirm_fast_record_args(
    tool_name: str,
    func_args: Any,
    channel: Optional[str] = None,
    user_message: Optional[str] = None,
) -> Any:
    """Skip the two-turn confirmation gate for pure fast-record requests.

    分级 + 分通道(channel 来自**客户端传输层声明**,绝不信 LLM 工具参数——
    对抗评审证伪过 arg-based 守卫:tool schema 无 source 字段,模型是该字段
    唯一可能作者=不可信):
    - AUTO 集(water/diet/...):任何通道直接写。
    - symptom/rhinitis: typed 免确认; voice 下仅对明确的症状陈述免确认;
      Siri/未声明通道(旧客户端、Siri 单轮无屏无法撤销)fail-closed 保留确认。
    - NEVER 集(medication/dose/financial/...)与 unknown kind:恒确认(fail-closed)。
    """

    if tool_name != "health_record":
        return func_args
    try:
        args = _loads_lenient(func_args) if isinstance(func_args, str) else dict(func_args or {})
    except Exception:
        return func_args

    kind = _fast_record_kind(args)
    clear_voice_symptom = bool(
        kind in {"symptom", "rhinitis"}
        and channel == "voice"
        and _extract_clear_symptom_record(user_message)
    )
    requires_confirmation = (
        kind not in _FAST_RECORD_AUTO_CONFIRM_KINDS
        or kind in _FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS
        or (
            kind in _TYPED_ONLY_AUTO_CONFIRM_KINDS
            and channel != "typed"
            and not clear_voice_symptom
        )
    )
    if requires_confirmation:
        data = args.get("data")
        args.pop("confirmed", None)
        args.pop("confirm", None)
        if isinstance(data, str):
            try:
                data = json.loads(data)
                args["data"] = data
            except (json.JSONDecodeError, ValueError):
                data = None
        if isinstance(data, dict):
            data.pop("confirmed", None)
            data.pop("confirm", None)
        args["_fast_record_requires_confirmation"] = True
        if kind:
            args["record_type"] = kind
        if isinstance(func_args, str):
            return json.dumps(args, ensure_ascii=False)
        return args

    data = args.get("data")
    if not isinstance(data, dict):
        data = {}
        args["data"] = data
    args["record_type"] = kind
    args["confirmed"] = True
    data["confirmed"] = True
    if isinstance(func_args, str):
        return json.dumps(args, ensure_ascii=False)
    return args


_FAST_RECORD_AUTO_CONFIRM_KINDS = {
    "water",
    "weight",
    "bp",
    "blood_pressure",
    "diet",
    "exercise",
    "reminder",
    "supplement",
    "waist",
    "sleep",
    "excretion",
    "goal",
    # symptom/rhinitis:确认后置(回显+可撤销)替代确认前置 —— 记录可逆、
    # 非医疗级(≠用药/剂量),写错方向顶多 over-alarm(安全方向);缺
    # body_part/description 会 fail-loud 自然追问,不是复述式确认。
    # 每条症状都二次询问被用户明确否决(2026-07-02)。
    "symptom",
    "rhinitis",
    # event(生活事件账本):founder 2026-07-13 裁决 AUTO·全通道 —— 非医疗、
    # L0、纯时间打点,写错顶多时间锚偏(可删重记);undo 通路=
    # health_manage(delete event {id}) → DELETE /episodes/life-event/{id}。
    "event",
    # garmin_sync(触发同步动作,非写记录):founder 2026-07-14 裁决 AUTO ——
    # 幂等读拉、无用户可见突变、可安全重复,不是不可逆写。执行走专属异步分支
    # (_trigger_garmin_sync:本地 precondition fail-loud → Celery enqueue → 乐观 ack),
    # 不经此快路由 confirm 门(无 garmin_sync 关键词分类器);登记于此仅为镜像
    # agent_ops_registry 的 confirm=auto,并让任何路径达此 kind 时免确认前置。
    "garmin_sync",
    # remember(档案属性/个人事实):typed_only —— 可逆(memory 有 dismiss soft-delete)、
    # 非医疗(结构化医疗/化验/基因/用药已被 _remember_structured_medical_redirect 服务端硬闸
    # 挡在 remember 外)。加入 AUTO 集满足不变量 typed_only ⊆ AUTO(否则 typed 通道也恒确认 →
    # fast 模式确认死循环,见 safety review IMPORTANT-3)。
    "remember",
}
# 症状类打字通道免确认;语音通道只有在原话是明确症状陈述时免确认,
# 其它语音/siri/未声明通道仍保留确认前置(转写失真 + Siri 单轮无法撤销)。
# channel 由客户端传输层声明(AgentRequest.channel),绝不读 LLM
# 工具参数——对抗评审证伪过 arg-based 守卫(schema 无 source 字段,模型是该
# 字段唯一可能作者=不可信=生产死代码)。
_TYPED_ONLY_AUTO_CONFIRM_KINDS = {"symptom", "rhinitis", "goal", "remember"}


# 医疗级/不可逆/资金类:永远确认前置。unknown kind 也走确认(fail-closed,
# 见 _auto_confirm_fast_record_args:不在 AUTO 集即要求确认)。
_FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS = {
    "adherence",
    "dose",
    "dosage",
    "drug",
    "financial",
    "finance",
    "illness",
    "medication",
    "medicine",
    "payment",
    "prescription",
}
_FAST_RECORD_KIND_ALIASES = {
    "bp": "blood_pressure",
    "blood-pressure": "blood_pressure",
    "bloodpressure": "blood_pressure",
    "life_event": "event",
    "life-event": "event",
}
def _normalize_fast_record_kind(raw: Any) -> str:
    kind = str(raw or "").strip().lower()
    return _FAST_RECORD_KIND_ALIASES.get(kind, kind)


def _fast_record_kind(args: dict) -> str:
    data = args.get("data")
    candidates = [
        args.get("record_type"),
        args.get("type"),
        args.get("kind"),
    ]
    if isinstance(data, dict):
        candidates.extend([
            data.get("record_type"),
            data.get("type"),
            data.get("kind"),
        ])
    for raw in candidates:
        if raw is not None:
            return _normalize_fast_record_kind(raw)
    return ""


def _parse_time_only_to_next_beijing(
    raw: Any,
    *,
    reference_now: Optional[datetime] = None,
) -> Optional[str]:
    """Normalize a time-only reminder relative to the frozen turn clock."""
    effective_tz = (reference_now.tzinfo if reference_now is not None else None) or BEIJING_TZ
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw if raw.tzinfo else raw.replace(tzinfo=effective_tz)
        return dt.astimezone(effective_tz).isoformat(timespec="seconds")

    s = str(raw).strip()
    if not s:
        return None

    # Full ISO datetime: keep it, adding the frozen user timezone when omitted.
    try:
        if re.search(r"\d{4}-\d{2}-\d{2}", s):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=effective_tz)
            return dt.astimezone(effective_tz).isoformat(timespec="seconds")
    except ValueError:
        pass

    compact = (
        s.lower()
        .replace("：", ":")
        .replace("点半", ":30")
        .replace("点", ":")
        .replace("时", ":")
        .replace("分", "")
        .strip()
        .rstrip(":")
    )
    m = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", compact)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if hour > 23 or minute > 59:
        return None

    now = reference_now or datetime.now(BEIJING_TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now + timedelta(minutes=1):
        target += timedelta(days=1)
    return target.isoformat(timespec="seconds")


def _normalize_recurrence(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if re.search(r"daily|每天|每日|天天|every\s*day", s):
        return "daily"
    if re.search(r"weekdays|工作日", s):
        return "weekdays"
    if s.startswith("weekly"):
        return s
    if re.search(r"每周|weekly|星期|周[一二三四五六日天]", s):
        return "weekly"
    return s


_REMINDER_WINDOW_RE = re.compile(
    r"(?P<start>\d{1,2}(?::\d{1,2}|：\d{1,2}|点半|点\d{0,2}分?|时\d{0,2}分?)?)"
    r"\s*(?:到|至|[-~～—])\s*"
    r"(?P<end>\d{1,2}(?::\d{1,2}|：\d{1,2}|点半|点\d{0,2}分?|时\d{0,2}分?)?)"
)
_REMINDER_INTERVAL_RE = re.compile(
    r"(?:每隔|每)\s*(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>小时|钟头|hours?|hrs?|h|分钟|minutes?|mins?|min|m)",
    re.IGNORECASE,
)


def _interval_minutes_from_reminder_context(text: str) -> Optional[int]:
    matches = list(_REMINDER_INTERVAL_RE.finditer(text or ""))
    if not matches:
        return None
    match = matches[-1]
    value = float(match.group("value"))
    unit = match.group("unit").lower()
    minutes = round(value * 60) if unit in {"小时", "钟头", "hour", "hours", "hr", "hrs", "h"} else round(value)
    return minutes if 15 <= minutes <= 720 else None


def _enrich_reminder_window_from_turn(
    data: dict,
    *,
    user_message: str,
    recent_messages: list[dict],
    reference_now: Optional[datetime] = None,
) -> dict:
    """Recover an explicit follow-up window without inventing its interval."""
    out = dict(data or {})
    if all(out.get(key) not in (None, "") for key in (
        "start_time", "end_time", "interval_minutes",
    )):
        return out

    window_match = _REMINDER_WINDOW_RE.search(user_message or "")
    if not window_match:
        return out
    start = _parse_time_only_to_next_beijing(
        window_match.group("start"), reference_now=reference_now,
    )
    end = _parse_time_only_to_next_beijing(
        window_match.group("end"), reference_now=reference_now,
    )
    if not start or not end:
        return out

    context = "\n".join(
        str(message.get("content") or "")
        for message in recent_messages[-6:]
        if isinstance(message, dict)
    )
    interval_minutes = out.get("interval_minutes")
    if interval_minutes in (None, ""):
        interval_minutes = _interval_minutes_from_reminder_context(
            f"{context}\n{user_message}"
        )

    out["start_time"] = start
    out["end_time"] = end
    if interval_minutes not in (None, ""):
        out["interval_minutes"] = interval_minutes
    out.pop("remind_at", None)
    logger.info(
        "[health_record] recovered explicit reminder window interval_present=%s",
        interval_minutes not in (None, ""),
    )
    return out


def _normalize_reminder_record_data(
    data: dict,
    *,
    reference_now: Optional[datetime] = None,
) -> dict:
    """Make LLM reminder args match /reminders/me without inventing reminders."""
    out = dict(data or {})
    title = (
        out.get("title")
        or out.get("label")
        or out.get("name")
        or out.get("message")
        or "健康提醒"
    )
    out["title"] = str(title).strip()[:200] or "健康提醒"
    out["message"] = str(
        out.get("message")
        or out.get("description")
        or out.get("note")
        or out["title"]
    ).strip()[:500]
    priority = str(out.get("priority") or "normal").strip().lower()
    out["priority"] = priority if priority in {"low", "normal", "high", "urgent"} else "normal"

    recurrence = _normalize_recurrence(
        out.get("recurrence") or out.get("repeat") or out.get("frequency")
    )
    if recurrence:
        out["recurrence"] = recurrence

    remind_at = _parse_time_only_to_next_beijing(
        out.get("remind_at")
        or out.get("alarm_time")
        or out.get("reminder_time")
        or out.get("time")
        or out.get("at"),
        reference_now=reference_now,
    )
    if remind_at:
        out["remind_at"] = remind_at

    def normalize_clock(raw: Any) -> Optional[str]:
        parsed = _parse_time_only_to_next_beijing(raw, reference_now=reference_now)
        if not parsed:
            return None
        try:
            return datetime.fromisoformat(parsed).astimezone(
                reference_now.tzinfo if reference_now is not None else BEIJING_TZ
            ).strftime("%H:%M")
        except (TypeError, ValueError):
            return None

    start_time = normalize_clock(
        out.get("start_time") or out.get("window_start") or out.get("from_time")
    )
    end_time = normalize_clock(
        out.get("end_time") or out.get("window_end") or out.get("to_time")
    )
    if start_time:
        out["start_time"] = start_time
    if end_time:
        out["end_time"] = end_time

    raw_interval = out.get("interval_minutes")
    if raw_interval in (None, "") and out.get("interval_hours") not in (None, ""):
        try:
            raw_interval = float(out["interval_hours"]) * 60
        except (TypeError, ValueError):
            raw_interval = None
    if isinstance(raw_interval, str):
        interval_text = raw_interval.strip().lower()
        interval_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(小时|hour|hours|h)", interval_text)
        if interval_match:
            raw_interval = float(interval_match.group(1)) * 60
        else:
            minute_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(分钟|minute|minutes|min|m)?", interval_text)
            raw_interval = float(minute_match.group(1)) if minute_match else None
    if raw_interval not in (None, ""):
        try:
            interval_minutes = int(round(float(raw_interval)))
        except (TypeError, ValueError):
            interval_minutes = 0
        if 15 <= interval_minutes <= 720:
            out["interval_minutes"] = interval_minutes

    for key in (
        "alarm_time", "reminder_time", "time", "at", "repeat", "frequency",
        "confirmed", "confirm", "window_start", "from_time", "window_end",
        "to_time", "interval_hours",
    ):
        out.pop(key, None)
    return out


def _merge_agent_card_descriptors(*groups: list | None) -> list[dict]:
    out: list[dict] = []
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
                # A later descriptor is a fresher projection of the same
                # durable card (for example after a second meal photo attaches).
                out[position] = card
    return out


_MEAL_TYPE_ZH = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}

_MEAL_TYPE_ALIASES = {
    "breakfast": "breakfast",
    "早餐": "breakfast",
    "早饭": "breakfast",
    "上午": "breakfast",
    "早上": "breakfast",
    "lunch": "lunch",
    "午餐": "lunch",
    "午饭": "lunch",
    "中餐": "lunch",
    "中饭": "lunch",
    "中午": "lunch",
    "dinner": "dinner",
    "晚餐": "dinner",
    "晚饭": "dinner",
    "正餐晚": "dinner",
    "supper": "dinner",
    "晚上": "dinner",
    "snack": "snack",
    "extra": "extra",
    "加餐": "snack",
    "零食": "snack",
    "点心": "snack",
    "夜宵": "snack",
    "其他": "extra",
}


_MEDICAL_REPORT_IMAGE_KEYWORDS = (
    "体检",
    "报告",
    "化验",
    "检验",
    "检查单",
    "化验单",
    "胃镜",
    "肠镜",
    "内镜",
    "超声",
    "b超",
    "心电",
    "病理",
    "影像",
    "ct",
    "mri",
    "血常规",
    "生化",
    "血脂",
    "指标",
)


def _looks_like_medical_report_image_context(text: str) -> bool:
    """Only route images through medical OCR when the user explicitly asks for reports."""
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in _MEDICAL_REPORT_IMAGE_KEYWORDS)


def _medical_report_analysis_requested(text: str, *, persisted: bool) -> bool:
    """Separate a record-only command from a request that also needs interpretation."""
    normalized = (text or "").strip().lower()
    if not persisted:
        return True
    return bool(
        re.search(
            r"(分析|解读|看看|看一下|严重|有问题|正常|异常|建议|怎么办|"
            r"意味着|说明|是什么|如何|为什么|吗|？|\?)",
            normalized,
        )
    )


def _record_intent_needs_detail_message(record_text: str) -> str:
    """fast-record 被路由但 0 工具执行 = **没有发生任何写入尝试**(模型没吐出有效记录调用,
    通常因为内容太笼统,如"记录饮食"没说吃了什么)。

    诚实双约束:① 绝不谎报成功(honesty 硬闸,与旧行为一致);② 也不该谎称"没有成功写入
    数据库"—— 什么都没写过、根本没到端点,说"写库失败"会误导用户以为发生了 DB 错误
    (founder 2026-07-14 实测:'记录饮食' 被误报写库失败)。如实说"还没记下来"+ 请补具体。"""
    text = (record_text or "").strip()
    # 例子跨多领域(饮食/饮水/体测/档案属性/血压), 不再只给饮食/运动 —— 否则记鞋码却被要求
    # 补早餐(founder 2026-07-17 实测)。档案属性/个人事实(鞋码/衣码/喜好)现在走 remember,
    # 一般不会落到这里; 落到这里的多是真·笼统输入。
    hint = "(比如「午饭鳕鱼50g」「喝水300ml」「体重71.4kg」「鞋码42.5」「血压120/80」)"
    if text:
        return (
            f"我看你想记录「{text}」,但还没记下来 —— 我得能对上一个记录项才能存下。"
            f"你想记的是哪类、值是多少?{hint}补一句,或点确认记录。"
        )
    return f"我看你想记一条,但还没记下来 —— 你想记什么、值是多少?{hint}"


def _destructive_or_sync_not_performed_message(message: str) -> str:
    """破坏性(删/改/撤销)或同步意图被路由但 0 工具执行 = 动作**未执行**。

    honesty(与 record 版同源、加层不减层):破坏性/同步意图从 fast 路径排除后(留强模型),
    若强模型这一轮既没调起对应工具、又没被写回执诚实闸接住(0 工具 = 从未尝试),必须如实
    说"没执行成功、数据无改动",绝不谎报已删/已改/已同步。写回执诚实闸只管**尝试过**的写
    (count≥1);这条补上**从未尝试**(count==0)的破坏性/同步意图缺口。"""
    return (
        "这次我没有执行成功 —— 没有调起对应的删除/修改/同步动作,你的数据没有任何改动。"
        "请再说清楚一点(比如要删哪一条、改成什么),我重试。"
    )


_REMEMBER_BP_RE = re.compile(r"\d{2,3}\s*/\s*\d{2,3}")
_REMEMBER_DOSE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ug|iu|ml)\b", re.IGNORECASE)
_REMEMBER_RS_RE = re.compile(r"\brs\d{3,}\b", re.IGNORECASE)
# 用药:给药动词(服用/用药类)。**不含** '在吃'(多是饮食偏好, 如"在吃素")—— 具体药名靠
# drug_lexicon.contains_drug_name(专名, 不含泛称'药' → 不误伤 药剂师/药企/医药代表)。
_REMEMBER_MED_KW = ("服用", "在服", "正在服", "长期服", "用药", "在用药", "处方", "吃药", "在用", "正在用")
_REMEMBER_GENE_KW = ("基因", "基因型", "genotype", "snp", "等位", "纯合", "杂合", "变异位点", "突变")
# 化验:CJK 词作子串安全;短英文缩写(psa/tsh/…)必须词边界, 否则 ca**psa**icin 误命中。
_REMEMBER_LAB_CJK = (
    "血压", "血糖", "血脂", "胆固醇", "甘油三酯", "尿酸", "糖化", "转氨酶", "肝功", "肾功",
    "肌酐", "白细胞", "红细胞", "血红蛋白", "白蛋白", "胆红素", "甲状腺", "化验", "检验值", "指标值",
)
_REMEMBER_LAB_EN_RE = re.compile(r"\b(?:hba1c|a1c|egfr|ldl|hdl|tsh|psa)\b", re.IGNORECASE)


def _fold_fullwidth(s: str) -> str:
    """全角 → 半角(斜杠/数字/字母),防 150／95(U+FF0F)这类全角标点绕过形状正则。"""
    out = []
    for ch in s:
        o = ord(ch)
        if o == 0xFF0F:                       # 全角斜杠 ／
            out.append("/")
        elif 0xFF10 <= o <= 0xFF19 or 0xFF21 <= o <= 0xFF5A:  # 全角数字/字母
            out.append(chr(o - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def _remember_structured_medical_redirect(
    predicate: Any, object_value: Any, object_unit: Any = None
) -> Optional[str]:
    """BLOCKING backstop(safety review 2026-07-17 + 复审加固):remember 绝不能记结构化医疗/
    化验/基因/用药数据 —— 那些喂 Safety Guardian(读结构化 Twin 分区,**不读** memory_facts)
    且走加密/RLS 路径。软指引挡不住(本仓库裁决:LLM 自动动作闸=服务端硬闸)。命中 → fail-loud
    redirect,绝不写 memory_fact 绕过安全。全角归一 + 扫 pred+val+unit 全 blob(闭 fail-open);
    专名/给药动词/词边界(收 over-alarm, 良性 职业/饮食偏好/卡号/喜好 放行)。"""
    from app.services import drug_lexicon  # 懒导入避免循环
    blob = _fold_fullwidth(f"{predicate or ''} {object_value or ''} {object_unit or ''}")
    low = blob.lower()
    # 用药/剂量:具体药名(专名, 非泛称'药')+ 剂量形状 + 给药动词
    if (drug_lexicon.contains_drug_name(blob)
            or _REMEMBER_DOSE_RE.search(blob)
            or any(k in blob for k in _REMEMBER_MED_KW)):
        return local_write_rejection(
            "remember_medication_redirect",
            message="这像用药或剂量，不能保存为普通记忆。",
            recovery_guidance=(
                '请改用 health_record(record_type="medication")，'
                "以保留用药安全校验。"
            ),
        )
    # 基因:词表 OR rs 位点(rs\d{3,} 无歧义)。C282Y/星等位 只在基因上下文才算(避免误伤
    # 流水号 A2024B / 评分 *5)—— 基因上下文由 _REMEMBER_GENE_KW 覆盖,故无需独立形状正则。
    if any(k in low for k in _REMEMBER_GENE_KW) or _REMEMBER_RS_RE.search(blob):
        return local_write_rejection(
            "remember_genetic_redirect",
            message="基因或基因型数据不能保存为普通记忆。",
            recovery_guidance="请改用基因档案上传路径完成独立授权和加密隔离。",
        )
    # 血压/化验:BP 形状(扫全 blob, 含 unit)OR CJK 化验词 OR 英文化验缩写(词边界)
    if (_REMEMBER_BP_RE.search(blob)
            or any(k in blob for k in _REMEMBER_LAB_CJK)
            or _REMEMBER_LAB_EN_RE.search(blob)):
        return local_write_rejection(
            "remember_clinical_data_redirect",
            message="血压或化验指标不能保存为普通记忆。",
            recovery_guidance=(
                "请改用 blood_pressure 结构化记录或化验上传路径，"
                "以保留健康安全校验。"
            ),
        )
    return None


def _normalize_diet_meal_type(value: Any) -> Optional[str]:
    if value in (None, "", []):
        return None
    key = str(value).strip().lower()
    return _MEAL_TYPE_ALIASES.get(key)


_DIET_DELETE_WORD_RE = re.compile(r"(删除|删掉|删了|移除|去掉|撤销|清掉|delete|remove)", re.I)
_DIET_DELETE_LATEST_RE = re.compile(
    r"(最后|最新|刚才|刚刚|刚记录|上一)(?:的)?(?:一条|一份|一顿|一餐|这条|这顿|这餐)?",
    re.I,
)
_WRITE_NEGATED_RE = re.compile(
    r"(?:不要|别|不想|无需|不需要|不能|不可|禁止|避免|先别|暂不)\s*.{0,10}"
    r"(?:删除|删掉|删了|移除|去掉|撤销|清掉|修改|更新|调整)",
    re.I,
)
_WRITE_HOW_TO_RE = re.compile(
    r"(?:如何|怎么|怎样|是否)\s*.{0,10}"
    r"(?:删除|删掉|移除|去掉|撤销|清掉|修改|更新|调整)",
    re.I,
)
_UPDATE_WORD_RE = re.compile(r"(修改|改成|改为|更新|调整|更正|修正|edit|update)", re.I)


def _write_request_is_negated_or_instructional(message: str) -> bool:
    text = (message or "").strip()
    return bool(_WRITE_NEGATED_RE.search(text) or _WRITE_HOW_TO_RE.search(text))


def _has_explicit_delete_intent(message: str) -> bool:
    text = (message or "").strip()
    return bool(
        text
        and _DIET_DELETE_WORD_RE.search(text)
        and not _write_request_is_negated_or_instructional(text)
    )


def _has_explicit_update_intent(message: str) -> bool:
    text = (message or "").strip()
    return bool(
        text
        and _UPDATE_WORD_RE.search(text)
        and not _write_request_is_negated_or_instructional(text)
    )


_DIET_CORRECTION_MEAL_RE = re.compile(
    "|".join(
        re.escape(alias)
        for alias in sorted(
            (
                alias
                for alias, normalized in _MEAL_TYPE_ALIASES.items()
                if normalized in {"breakfast", "lunch", "dinner", "snack"}
            ),
            key=len,
            reverse=True,
        )
    ),
    re.I,
)
_DIET_CORRECTION_PREFIX_RE = re.compile(
    r"^(?:(?:记录|内容)\s*)?"
    r"(?:修改成|修改为|更正为|更新为|调整为|改成|改为|修改|更正|更新|调整|改)?"
    r"\s*(?:成|为)?\s*[:：,，;；\-—]*\s*",
    re.I,
)
_DIET_CORRECTION_REPLACEMENT_RE = re.compile(
    r"(?:修改成|修改为|更正为|更新为|调整为|改成|改为)(?P<replacement>.+)$",
    re.I,
)
_DIET_NON_FOOD_FIELD_RE = re.compile(
    r"^(?:的)?(?:热量|卡路里|蛋白质?|碳水|脂肪|膳食纤维|纤维|时间|餐时|份量|重量)",
    re.I,
)
_DIET_PARTIAL_CORRECTION_SIGNAL_RE = re.compile(
    r"(?:没吃那么多|没有吃那么多|没全吃|没有全吃|没吃完|没有吃完|"
    r"实际.{0,8}只吃|只吃了?|只有吃了?)",
    re.I,
)
_DIET_PARTIAL_CORRECTION_QUESTION_RE = re.compile(
    r"[?？]|会不会|要不要|是否|行不行|可以吗|怎么办|怎么吃|吃多少",
    re.I,
)
_DIET_PARTIAL_CORRECTION_NEGATION_RE = re.compile(
    r"(?:不要|别|不该|不能|不可|避免).{0,10}(?:只吃|吃.{0,4}(?:一半|半份|分之))",
    re.I,
)
_DIET_PARTIAL_FRACTIONS = {
    "一半": 0.5,
    "半份": 0.5,
    "三分之一": 1 / 3,
    "三分之二": 2 / 3,
    "四分之一": 0.25,
    "四分之三": 0.75,
    "五分之一": 0.2,
    "五分之二": 0.4,
    "五分之三": 0.6,
    "五分之四": 0.8,
}
_CONTEXTUAL_MEAL_PORTION_RE = re.compile(
    r"(?:吃了|吃掉了|实际吃了|只吃了?)\s*"
    r"(?P<fraction>三分之一|三分之二|四分之一|四分之三|"
    r"五分之一|五分之二|五分之三|五分之四|一半|半份|"
    r"\d+\s*/\s*\d+)",
    re.I,
)
_CONTEXTUAL_MEAL_WHOLE_PORTION_RE = re.compile(
    r"(?:这|整|本)(?:一)?(?:餐|顿|份|盘)|(?:这|整)些|只吃",
    re.I,
)
_DIET_SCALABLE_NUTRIENT_FIELDS = (
    "calories",
    "protein",
    "carbs",
    "fat",
    "fiber",
    "alcohol_units",
)
_MESSAGE_DATE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}|day before yesterday|yesterday|today|"
    r"前天|昨天|昨日|今天|今日|本日|当天|当日)",
    re.I,
)


def _partial_meal_consumed_fraction(text: str) -> Optional[float]:
    signal_match = _DIET_PARTIAL_CORRECTION_SIGNAL_RE.search(text)
    if (
        signal_match is None
        or _DIET_PARTIAL_CORRECTION_QUESTION_RE.search(text)
        or _DIET_PARTIAL_CORRECTION_NEGATION_RE.search(text)
    ):
        return None
    for phrase, fraction in _DIET_PARTIAL_FRACTIONS.items():
        if text.find(phrase, signal_match.start()) >= 0:
            return fraction
    return None


def _contextual_meal_consumed_fraction(
    text: str,
) -> Optional[tuple[float, str]]:
    """Parse a whole-meal portion from the message accompanying a food photo.

    This is intentionally narrower than generic diet correction parsing.  A
    sentence such as ``吃了三分之一的蛋糕`` describes one food and must not
    scale every item in the image.  We only accept an explicit whole-meal
    reference (``这餐``/``这份``) or the unambiguous ``只吃`` form.
    """
    normalized = " ".join((text or "").strip().split())
    if (
        not normalized
        or not _CONTEXTUAL_MEAL_WHOLE_PORTION_RE.search(normalized)
        or _DIET_PARTIAL_CORRECTION_QUESTION_RE.search(normalized)
        or _DIET_PARTIAL_CORRECTION_NEGATION_RE.search(normalized)
    ):
        return None
    match = _CONTEXTUAL_MEAL_PORTION_RE.search(normalized)
    if match is None:
        return None
    # ``三分之一的蛋糕`` is an item-level portion, not a whole-meal ratio.
    if normalized[match.end():].lstrip().startswith("的"):
        return None
    token = re.sub(r"\s+", "", match.group("fraction"))
    fraction = _DIET_PARTIAL_FRACTIONS.get(token)
    if fraction is None and "/" in token:
        numerator_text, denominator_text = token.split("/", 1)
        try:
            numerator = int(numerator_text)
            denominator = int(denominator_text)
        except ValueError:
            return None
        if numerator <= 0 or denominator <= 0 or numerator >= denominator:
            return None
        fraction = numerator / denominator
    if fraction is None or not math.isfinite(fraction) or not 0 < fraction < 1:
        return None
    return float(fraction), token


def _scale_food_recognition_for_consumed_fraction(
    result: Mapping[str, Any],
    *,
    fraction: float,
    label: str,
) -> Dict[str, Any]:
    """Scale one sanitized vision estimate to the amount actually consumed."""
    scaled = dict(result)
    foods: list[dict[str, Any]] = []
    for raw_food in result.get("foods") or []:
        if not isinstance(raw_food, dict):
            continue
        food = dict(raw_food)
        for field in (*_DIET_SCALABLE_NUTRIENT_FIELDS, "quantity_grams"):
            value = food.get(field)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
            ):
                food[field] = float(value) * fraction
        foods.append(food)
    scaled["foods"] = foods
    scaled["consumed_fraction"] = fraction
    scaled["consumed_fraction_label"] = label
    return scaled


def _parse_explicit_diet_correction(
    message: str,
    *,
    reference_now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Extract a concrete meal correction from the user's own words.

    Accepted forms are deliberately narrow: either an explicit replacement, or
    a factual partial-meal correction with a named meal and concrete consumed
    fraction. Ambiguous requests stay on the read-only lookup path rather than
    risking a duplicate or editing the wrong record.
    """
    text = " ".join((message or "").strip().split())
    meal_match = _DIET_CORRECTION_MEAL_RE.search(text)
    if not meal_match:
        return None
    meal_type = _normalize_diet_meal_type(meal_match.group(0))
    if not meal_type:
        return None

    date_match = _MESSAGE_DATE_RE.search(text)
    target_date = _normalize_relative_date(
        date_match.group(0) if date_match else "today",
        reference_now=reference_now,
    )
    if not target_date:
        return None

    consumed_fraction = _partial_meal_consumed_fraction(text)
    if consumed_fraction is not None:
        return {
            "date": target_date,
            "meal_type": meal_type,
            "consumed_fraction": consumed_fraction,
        }

    if not _has_explicit_update_intent(text):
        return None

    raw_replacement = text[meal_match.end():].strip()
    if _DIET_NON_FOOD_FIELD_RE.search(raw_replacement):
        return None
    nested_update = _DIET_CORRECTION_REPLACEMENT_RE.search(raw_replacement)
    if nested_update:
        replacement = nested_update.group("replacement")
    else:
        replacement = _DIET_CORRECTION_PREFIX_RE.sub(
            "", raw_replacement, count=1,
        )
    replacement = replacement.strip(" \t\r\n:：,，;；。")
    if not replacement or replacement in {"一下", "记录", "内容"}:
        return None

    return {
        "date": target_date,
        "meal_type": meal_type,
        "food_items": replacement,
    }


def _diet_correction_update_data(
    correction: Mapping[str, Any],
    existing_record: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    meal_type = correction.get("meal_type")
    replacement = correction.get("food_items")
    if replacement:
        return {
            "meal_type": meal_type,
            "food_items": replacement,
        }

    fraction = correction.get("consumed_fraction")
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool):
        return None
    fraction = float(fraction)
    if not math.isfinite(fraction) or not 0 < fraction < 1:
        return None

    update_data: Dict[str, Any] = {"meal_type": meal_type}
    for field in _DIET_SCALABLE_NUTRIENT_FIELDS:
        value = existing_record.get(field)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ):
            update_data[field] = float(value) * fraction
    return update_data if len(update_data) > 1 else None


def _build_deterministic_diet_correction_tool_call(
    message: Any,
    *,
    write_receipts: Sequence[dict[str, Any]],
    has_attachment: bool = False,
    reference_now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Build one safe lookup when a partial-meal correction got no tool call."""
    if write_receipts or has_attachment:
        return None
    correction = _parse_explicit_diet_correction(
        str(message or ""),
        reference_now=reference_now,
    )
    if not correction or correction.get("consumed_fraction") is None:
        return None
    arguments = {
        "record_type": "diet",
        "operation": "list",
        "date": correction["date"],
        "meal_type": correction["meal_type"],
        "limit": 20,
    }
    return {
        "id": f"diet-correction-{_sha12(str(message or ''))}",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _build_deterministic_goal_lookup_tool_call(
    goal: Optional[GoalSpec],
    *,
    write_receipts: Sequence[dict[str, Any]],
    has_attachment: bool = False,
) -> Optional[Dict[str, Any]]:
    """Start a typed recalculation task with the required authoritative lookup."""
    if (
        goal is None
        or goal.kind != "diet_recalculate_update"
        or not goal.requires_lookup
        or write_receipts
        or has_attachment
        or not goal.target_date
    ):
        return None
    arguments = {
        "record_type": "diet",
        "operation": "list",
        "date": goal.target_date,
        "limit": 20,
    }
    return {
        "id": f"goal-lookup-{_sha12(repr(goal))}",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _build_goal_verification_tool_call(
    goal: Optional[GoalSpec],
    *,
    write_receipts: Sequence[dict[str, Any]],
    already_attempted: bool,
) -> Optional[Dict[str, Any]]:
    """Read the target scope back only after every intended update has a receipt."""
    if (
        goal is None
        or goal.kind != "diet_recalculate_update"
        or not goal.requires_verification
        or already_attempted
        or not goal.target_date
        or len(write_receipts) < len(goal.target_meal_types)
    ):
        return None
    arguments = {
        "record_type": "diet",
        "operation": "list",
        "date": goal.target_date,
        "limit": 20,
    }
    return {
        "id": f"goal-verify-{_sha12(repr(goal))}",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _normalize_goal_guarded_tool_calls(
    tool_calls: List[Dict[str, Any]],
    goal: Optional[GoalSpec],
    *,
    lookup_completed: bool = False,
    allowed_record_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Fail closed when a model violates the current task's mutation contract."""
    if goal is None:
        return tool_calls
    prohibited = {
        str(operation).strip().lower()
        for operation in goal.prohibited_operations
        if str(operation).strip()
    }
    if prohibited:
        contract_safe_calls: list[dict[str, Any]] = []
        fully_read_only = {"create", "update", "delete"}.issubset(prohibited)
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = str(function.get("name") or "")
            try:
                args = (
                    json.loads(function.get("arguments"))
                    if isinstance(function.get("arguments"), str)
                    else dict(function.get("arguments") or {})
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                args = {}
            attempted_write = _write_tool_attempted(name, args)
            is_read_only_call = _tool_call_is_read_only(name, args)
            operation = str(
                args.get("operation") or args.get("action") or ""
            ).strip().lower()
            # health_record always crosses a side-effect boundary. Some action
            # record types (for example garmin_sync) intentionally do not
            # require a persistence receipt, but that does not make them safe
            # in a read-only turn.
            attempted_mutation = attempted_write or name == "health_record"
            if name == "health_record":
                operation = "create"
            record_type = str(args.get("record_type") or "").strip().lower()
            violates_contract = (
                (fully_read_only and not is_read_only_call)
                or (
                    attempted_mutation
                    and (
                        not operation
                        or operation in prohibited
                    )
                )
            )
            if (
                goal.kind == "diet_recalculate_update"
                and attempted_mutation
                and record_type != "diet"
            ):
                violates_contract = True
            # The recalculation path deliberately converts an unsafe create
            # request for the diet domain into its required read-only lookup
            # below. Cross-domain writes must never inherit that exception.
            is_diet_create_recovery = (
                goal.kind == "diet_recalculate_update"
                and record_type == "diet"
                and operation == "create"
            )
            if is_diet_create_recovery:
                violates_contract = False
            if violates_contract:
                logger.warning(
                    "[agent_executor] goal contract blocked prohibited mutation "
                    "kind=%s tool=%s operation=%s",
                    goal.kind,
                    name,
                    operation or "unknown",
                )
                continue
            contract_safe_calls.append(tool_call)
        tool_calls = contract_safe_calls
    if goal.kind == "simple_health_record":
        authoritative_args = _simple_record_goal_arguments(goal)
        normalized: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = str(function.get("name") or "")
            try:
                args = (
                    json.loads(function.get("arguments"))
                    if isinstance(function.get("arguments"), str)
                    else dict(function.get("arguments") or {})
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                args = {}
            is_write = (
                name == "health_record"
                or (
                    name in _WRITE_RECEIPT_TOOL_NAMES
                    and _write_tool_attempted(name, args)
                )
            )
            if not is_write:
                normalized.append(tool_call)
                continue
            if authoritative_args is None:
                logger.error(
                    "[agent_executor] blocked model write for invalid simple goal "
                    "tool=%s target_record_type=%s",
                    name,
                    goal.target_record_type,
                )
                continue
            guarded_args = authoritative_args
            if name == "health_record" and goal.target_record_type == "diet":
                guarded_args = _merge_equivalent_diet_model_estimates(
                    goal,
                    model_args=args,
                    authoritative_args=authoritative_args,
                )
            if name != "health_record" or args != guarded_args:
                logger.warning(
                    "[agent_executor] simple goal canonicalized model write "
                    "tool=%s target_record_type=%s",
                    name,
                    goal.target_record_type,
                )
            normalized.append({
                **tool_call,
                "function": {
                    **function,
                    "name": "health_record",
                    "arguments": json.dumps(
                        guarded_args,
                        ensure_ascii=False,
                    ),
                },
            })
        return normalized
    if goal.kind != "diet_recalculate_update":
        return tool_calls
    lookup_args = {
        "record_type": "diet",
        "operation": "list",
        "date": goal.target_date,
        "limit": 20,
    }
    normalized: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        function = tool_call.get("function") or {}
        name = function.get("name")
        try:
            args = (
                json.loads(function.get("arguments"))
                if isinstance(function.get("arguments"), str)
                else dict(function.get("arguments") or {})
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            normalized.append(tool_call)
            continue
        is_diet_create = (
            args.get("record_type") == "diet"
            and (
                name == "health_record"
                or args.get("operation") == "create"
            )
        )
        record_id = args.get("record_id") or args.get("id")
        is_unresolved_diet_update = (
            name == "health_manage"
            and args.get("record_type") == "diet"
            and args.get("operation") == "update"
            and (
                not lookup_completed
                or record_id in (None, "")
                or (
                    allowed_record_ids is not None
                    and str(record_id) not in allowed_record_ids
                )
            )
        )
        if not is_diet_create and not is_unresolved_diet_update:
            normalized.append(tool_call)
            continue
        logger.warning(
            "[agent_executor] goal contract blocked unsafe diet mutation "
            "tool=%s operation=%s",
            name,
            args.get("operation") or "create",
        )
        normalized.append({
            **tool_call,
            "function": {
                **function,
                "name": "health_manage",
                "arguments": json.dumps(lookup_args, ensure_ascii=False),
            },
        })
    return normalized


def _goal_guard_rejected_writes(
    proposed_calls: Sequence[Dict[str, Any]],
    guarded_calls: Sequence[Dict[str, Any]],
) -> List[tuple[str, Dict[str, Any]]]:
    """Return write calls removed by the goal guard without retaining health data."""
    retained_call_ids = {
        str(call.get("id"))
        for call in guarded_calls
        if call.get("id") not in (None, "")
    }
    retained_objects = {id(call) for call in guarded_calls}
    rejected: list[tuple[str, Dict[str, Any]]] = []
    for call in proposed_calls:
        call_id = call.get("id")
        if (
            id(call) in retained_objects
            or (
                call_id not in (None, "")
                and str(call_id) in retained_call_ids
            )
        ):
            continue
        function = call.get("function") or {}
        tool_name = str(function.get("name") or "")
        try:
            parsed_args = (
                json.loads(function.get("arguments"))
                if isinstance(function.get("arguments"), str)
                else dict(function.get("arguments") or {})
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed_args = {}
        if tool_name == "health_record" or _write_tool_attempted(
            tool_name,
            parsed_args,
        ):
            rejected.append((tool_name, parsed_args))
    return rejected


_GOAL_GUARD_RECOVERY_PROMPT = (
    "刚才选择的写入操作不符合本回合目标，系统已经拒绝执行。"
    "请不要调用任何工具，直接回答用户原本的问题；"
    "不得声称已经记录、修改或删除任何数据，也不要向用户暴露内部工具或策略。"
)


def _goal_target_record_ids(
    goal: Optional[GoalSpec],
    result: Any,
) -> set[str]:
    """Resolve target IDs only when every requested meal has one unique row."""
    record_ids, _, _ = _goal_target_record_resolution(goal, result)
    return record_ids


def _goal_target_record_resolution(
    goal: Optional[GoalSpec],
    result: Any,
) -> tuple[set[str], tuple[str, ...], tuple[str, ...]]:
    """Return safe IDs plus missing and ambiguous target meals."""
    if goal is None or goal.kind != "diet_recalculate_update":
        return set(), (), ()
    parsed = result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (TypeError, ValueError, json.JSONDecodeError):
            return set(), tuple(goal.target_meal_types), ()
    rows: list[dict[str, Any]] = []
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
    elif isinstance(parsed, dict):
        for key in ("items", "records", "data", "results"):
            nested = parsed.get(key)
            if isinstance(nested, list):
                rows = [row for row in nested if isinstance(row, dict)]
                break
    target_meals = set(goal.target_meal_types)
    ids_by_meal: dict[str, set[str]] = {
        meal_type: set()
        for meal_type in target_meals
    }
    for row in rows:
        meal_type = str(row.get("meal_type") or "").strip().lower()
        record_id = row.get("id") or row.get("record_id")
        if meal_type in ids_by_meal and record_id not in (None, ""):
            ids_by_meal[meal_type].add(str(record_id))
    missing = tuple(sorted(
        meal_type
        for meal_type in target_meals
        if not ids_by_meal[meal_type]
    ))
    ambiguous = tuple(sorted(
        meal_type
        for meal_type in target_meals
        if len(ids_by_meal[meal_type]) > 1
    ))
    if missing or ambiguous:
        return set(), missing, ambiguous
    return {
        next(iter(ids_by_meal[meal_type]))
        for meal_type in target_meals
    }, (), ()


def _goal_lookup_resolution_prompt(
    goal: Optional[GoalSpec],
    result: Any,
) -> str:
    """Give the model a deterministic stop condition for unsafe target lookup."""
    if isinstance(result, str):
        try:
            json.loads(result)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
    elif not isinstance(result, (list, dict)):
        return ""
    _, missing, ambiguous = _goal_target_record_resolution(goal, result)
    if not missing and not ambiguous:
        return ""
    labels = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
    }
    details: list[str] = []
    if missing:
        details.append(
            "未找到" + "、".join(labels.get(item, item) for item in missing)
        )
    if ambiguous:
        details.append(
            "存在多条" + "、".join(labels.get(item, item) for item in ambiguous)
        )
    return (
        "\n\n[系统任务约束] 目标记录无法唯一确定（"
        + "；".join(details)
        + "）。禁止继续写入或宣称完成；请用简洁中文说明具体餐次，并请用户选择或补充。"
    )


def _is_explicit_latest_diet_delete(message: str) -> bool:
    text = (message or "").strip()
    return bool(
        text
        and _has_explicit_delete_intent(text)
        and _DIET_DELETE_LATEST_RE.search(text)
        and re.search(r"(餐|饮食|记录|重复|刚才|刚刚)", text)
    )


# 相对日期词 → 相对今天的天数偏移 (lower() 后匹配; 中文不受 lower 影响)。
_RELATIVE_DATE_OFFSETS = {
    "today": 0, "今天": 0, "今日": 0, "本日": 0, "当天": 0, "当日": 0, "now": 0,
    "yesterday": -1, "昨天": -1, "昨日": -1,
    "前天": -2, "day before yesterday": -2,
    "tomorrow": 1, "明天": 1, "明日": 1,
}


def _normalize_relative_date(
    value: Any,
    *,
    reference_now: Optional[datetime] = None,
) -> Optional[str]:
    """把 date 参数归一成 ISO date 串 (YYYY-MM-DD)。

    LLM 常传相对词 'today'/'昨天' 或 date/datetime 对象; 但端点把 date 当真日期解析, 传字面
    'today' → 422 date_from_datetime_parsing (founder 实测「修改早餐」失败根因)。
    - date/datetime → isoformat 日期。
    - 相对词(today/昨天/前天/明天…) → 按北京时区今天折算。
    - 已是合法 ISO 日期(可带时间) → 取日期部分。
    - 解析不出 → None (调用方据此**不带**该日期过滤, 列近期而非 422 报错; 诚实降级)。
    """
    from datetime import date as _d
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, _d):
        return value.isoformat()
    s = str(value).strip().lower()
    if not s:
        return None
    if s in _RELATIVE_DATE_OFFSETS:
        today = (reference_now or datetime.now(BEIJING_TZ)).date()
        return (today + timedelta(days=_RELATIVE_DATE_OFFSETS[s])).isoformat()
    try:
        return _d.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def _summarize_record_data(
    kind: str,
    record_data: Any,
    *,
    delivery_status: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a clean human summary from the structured args the model wrote.

    `record_data` is the tool's `data` argument — structured and reliable — so it
    is a far safer source for the card than re-parsing the tool result string.
    Returns "" when nothing presentable can be built (caller suppresses the card).
    """
    if not isinstance(record_data, dict):
        return ""
    if kind == "diet":
        food = str(record_data.get("food_items") or record_data.get("food") or "").strip()
        meal = _MEAL_TYPE_ZH.get(_normalize_diet_meal_type(record_data.get("meal_type")) or "", "")
        if food:
            return f"已记录{meal + '：' if meal else '饮食 '}{food}"
    elif kind == "water":
        amt = record_data.get("amount") or record_data.get("amount_ml")
        if amt:
            return f"已记录饮水 {amt}ml"
    elif kind == "weight":
        w = record_data.get("weight") or record_data.get("weight_kg")
        if w:
            return f"已记录体重 {w}kg"
    elif kind == "blood_pressure":
        s = record_data.get("systolic")
        d = record_data.get("diastolic")
        if s and d:
            return f"已记录血压 {s}/{d}"
    elif kind == "reminder":
        title = str(record_data.get("title") or record_data.get("message") or "").strip()
        recurrence = str(record_data.get("recurrence") or "").strip().lower()
        if title:
            return (
                f"{'已设置每日提醒' if recurrence == 'daily' else '已设置提醒'}：{title}"
                f"{_reminder_delivery_status_tail(delivery_status)}"
            )
    return ""


def _health_record_card_descriptor(
    record_type: Any,
    record_data: Any,
    result: str,
    *,
    write_verified: Optional[bool] = None,
) -> Optional[dict]:
    """Build a deterministic chat card from a completed health_record tool.

    This is intentionally not model-generated UI. It mirrors the actual tool
    result so streaming cards cannot introduce new medical claims.
    """

    explicit_outcome = classify_explicit_write_execution(result)
    if (
        write_verified is False
        or not result
        or result.startswith("Error")
        or result.startswith("[NEEDS_CONFIRMATION]")
        or bool(
            write_verified is not True
            and explicit_outcome
            and explicit_outcome.status != "verified"
        )
    ):
        return None
    kind = _normalize_fast_record_kind(record_type)
    if kind not in {
        "water",
        "weight",
        "blood_pressure",
        "diet",
        "exercise",
        "supplement",
        "checkin",
        "reminder",
    }:
        return None

    # 1) Prefer the tool's own human "message".
    detail = ""
    parsed_is_json = False
    try:
        payload = json.loads(result)
        parsed_is_json = True
        if isinstance(payload, dict):
            detail = str(payload.get("message") or "").strip()
    except Exception:
        parsed_is_json = False
        payload = None
    delivery_status = (
        payload.get("delivery_status")
        if kind == "reminder" and isinstance(payload, dict) else None
    )
    delivery_tail = _reminder_delivery_status_tail(delivery_status)
    if (
        detail
        and delivery_tail
        and "未确认已送达手表" not in detail
        and "已确认送达手表" not in detail
    ):
        detail = f"{detail}{delivery_tail}"
    # 2) No usable message → synthesize from the structured args (never raw JSON).
    if not detail:
        detail = _summarize_record_data(
            kind,
            record_data,
            delivery_status=delivery_status if isinstance(delivery_status, dict) else None,
        )
    # 3) Plain-text result (not JSON) → first line is safe. A JSON blob is NOT:
    #    dumping it leaks `{"record_date":...,"food_items":...}` into the card.
    if not detail and not parsed_is_json:
        detail = str(result).splitlines()[0].strip()
    if not detail:
        return None
    detail = re.sub(r"\s+", " ", detail)
    if len(detail) > 120:
        detail = detail[:117].rstrip() + "..."

    return {
        "type": "record",
        "data": {
            "type": kind,
            "detail": detail,
        },
    }


def _is_contextual_meal_photo_replay_result(result: Any) -> bool:
    """True when health_record(diet) only replays an already-saved meal photo."""
    try:
        payload = json.loads(result) if isinstance(result, str) else result
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    operation_id = str(payload.get("operation_id") or "")
    return (
        operation_id.startswith("contextual_meal_photo:")
        and str(payload.get("resource_type") or "") == "diet_record"
    )


def _number_or_none(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                return None
    return None


def _short_food_label(value: Any, limit: int = 34) -> str:
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("name") or item.get("food") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                parts.append(text)
        raw = "、".join(parts)
    else:
        raw = str(value or "").strip()
    raw = re.sub(r"\s+", " ", raw).strip(" ,，、")
    if len(raw) > limit:
        return raw[:limit].rstrip(" ,，、") + "…"
    return raw


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word and word in text for word in words)


def _macro_summary(record_data: dict) -> str:
    parts: list[str] = []
    kcal = _number_or_none(record_data.get("calories") or record_data.get("kcal"))
    protein = _number_or_none(record_data.get("protein"))
    carbs = _number_or_none(record_data.get("carbs") or record_data.get("carbohydrates"))
    fat = _number_or_none(record_data.get("fat"))
    if kcal is not None:
        parts.append(f"{kcal:.0f} kcal")
    if protein is not None:
        parts.append(f"蛋白 {protein:.0f}g")
    if carbs is not None:
        parts.append(f"碳水 {carbs:.0f}g")
    if fat is not None:
        parts.append(f"脂肪 {fat:.0f}g")
    return " · ".join(parts)


def _diet_personal_cautions(record_data: dict, personal_context: str) -> list[str]:
    food_text = str(record_data.get("food_items") or record_data.get("food") or "")
    context = personal_context or ""
    combined = f"{food_text}\n{context}"
    cautions: list[str] = []
    if _has_any(context, ("胃溃疡", "胃炎", "胃病", "反流", "GERD", "消化道")) and _has_any(
        food_text,
        ("柠檬", "酸", "维C", "维生素C", "姜黄", "咖啡", "酒", "辣", "冰", "冷"),
    ):
        cautions.append("胃溃疡记录在案，冷饮/酸性饮品可能刺激胃，建议观察耐受。")
    if _has_any(context, ("糖尿病", "血糖", "糖耐量", "胰岛素抵抗")):
        carbs = _number_or_none(record_data.get("carbs") or record_data.get("carbohydrates"))
        if carbs is not None and carbs >= 80:
            cautions.append("控糖背景下这餐碳水偏高，餐后可轻走 10-15 分钟并关注血糖。")
    if _has_any(context, ("高血压", "血压")) and _has_any(combined, ("咸", "盐", "酱", "汤", "腌", "外卖")):
        cautions.append("有血压管理目标时，留意这餐钠盐和汤汁摄入。")
    allergy_match = re.search(r"过敏/禁忌[:：]\s*([^\n]+)", context)
    if allergy_match:
        allergy_text = allergy_match.group(1)
        for item in re.split(r"[,，、/]\s*", allergy_text):
            item = item.strip()
            if item and item in food_text:
                cautions.append(f"你的禁忌里包含「{item}」，请确认这餐没有误食。")
                break
    return cautions[:2]


def _diet_primary_judgement(record_data: dict) -> str:
    protein = _number_or_none(record_data.get("protein"))
    kcal = _number_or_none(record_data.get("calories") or record_data.get("kcal"))
    if protein is not None and protein >= 25:
        if kcal is not None:
            return f"蛋白质到位（{protein:.0f}g），热量约 {kcal:.0f} kcal。"
        return f"蛋白质到位（{protein:.0f}g）。"
    if protein is not None:
        return f"蛋白偏低（{protein:.0f}g），下一餐需要补足。"
    if kcal is not None:
        return f"热量约 {kcal:.0f} kcal，营养估算已写入。"
    return "这餐已经进入今日饮食账本。"


def _diet_next_action(record_data: dict, personal_context: str) -> str:
    protein = _number_or_none(record_data.get("protein"))
    context = personal_context or ""
    if _has_any(context, ("胃溃疡", "胃炎", "胃病", "反流", "GERD")):
        return "晚餐优先 35-45g 蛋白，少油少刺激，饮品尽量温和。"
    if protein is not None and protein < 25:
        return "下一餐优先补 30-40g 蛋白，比如鱼/鸡胸/豆腐加蔬菜。"
    return "下一餐继续补足蛋白和蔬菜，避免把热量集中到夜间。"


def _exercise_record_summary(record_data: dict) -> tuple[str, str]:
    exercise = str(
        record_data.get("exercise_type")
        or record_data.get("type")
        or record_data.get("name")
        or "运动"
    ).strip()
    reps = _number_or_none(record_data.get("reps"))
    sets = _number_or_none(record_data.get("sets"))
    duration = _number_or_none(record_data.get("duration") or record_data.get("minutes"))
    bits: list[str] = []
    if sets is not None:
        bits.append(f"{sets:.0f}组")
    if reps is not None:
        bits.append(f"{reps:.0f}次")
    if duration is not None:
        bits.append(f"{duration:.0f}分钟")
    detail = " · ".join(bits) if bits else "已完成"
    return exercise, detail


def _post_record_quality_response(
    record_type: Any,
    record_data: Any,
    result: str = "",
    personal_context: str = "",
    *,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
    write_verified: Optional[bool] = None,
) -> Optional[dict]:
    """Compatibility wrapper; implementation lives in post_record_quality.py."""
    return build_post_record_quality_response(
        record_type,
        record_data,
        result=result,
        personal_context=personal_context,
        db=db,
        user_id=user_id,
        write_verified=write_verified,
    )


def _safety_alert_value(alert: Any, key: str, default: Any = None) -> Any:
    if isinstance(alert, dict):
        return alert.get(key, default)
    return getattr(alert, key, default)


def _safety_alert_severity_label(raw: Any) -> str:
    if isinstance(raw, dict):
        raw = raw.get("label") or raw.get("value")
    label = getattr(raw, "label", None)
    if isinstance(label, str) and label:
        return label.strip().lower()
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        return normalized if normalized in {"info", "low", "medium", "high", "critical"} else "info"
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return "info"
    if value >= 4:
        return "critical"
    if value >= 3:
        return "high"
    if value >= 2:
        return "medium"
    if value >= 1:
        return "low"
    return "info"


def _safety_alert_card_descriptor(alert: Any) -> Optional[dict]:
    """Translate a deterministic SafetyGuardian alert into a conservative UI card."""

    title = str(_safety_alert_value(alert, "title", "") or "").strip() or "安全提醒"
    summary = str(_safety_alert_value(alert, "message", "") or "").strip()
    severity = _safety_alert_severity_label(_safety_alert_value(alert, "severity"))

    raw_action = _safety_alert_value(alert, "action")
    if isinstance(raw_action, list):
        recommendations = [str(item).strip() for item in raw_action if str(item).strip()]
    elif raw_action:
        recommendations = [str(raw_action).strip()]
    else:
        recommendations = []

    data = {
        "title": title,
        "severity": severity,
        "summary": summary,
        "recommendations": recommendations[:3],
        "boundary": SAFETY_CARD_BOUNDARY,
        "requires_medical_attention": bool(
            _safety_alert_value(alert, "requires_medical_attention", False)
        ) or severity == "critical",
    }
    for key in ("rule_id", "category"):
        value = _safety_alert_value(alert, key)
        if value not in (None, ""):
            data[key] = str(value)

    return {"type": "safety", "data": data}


def _health_record_confirmation_preview(rtype: str, args: dict, data: dict) -> str:
    label = {
        "diet": "饮食",
        "illness": "疾病/不适周期",
        "medication": "用药",
        "mood": "心情",
        "reminder": "提醒",
        "rhinitis": "鼻炎症状",
        "supplement_group": "补剂批量打卡",
        "symptom": "症状",
    }.get(rtype, f"{rtype} 记录")

    name = (
        data.get("description") or data.get("food_items") or data.get("medication_name") or data.get("name")
        or data.get("illness_name") or data.get("title") or args.get("name")
    )
    if name:
        if rtype == "medication":
            actual_dosage = (
                data.get("actual_dosage")
                or args.get("actual_dosage")
                or data.get("dose")
                or args.get("dose")
            )
            if actual_dosage:
                return f"{label}: {name}，本次服量 {actual_dosage}"
        return f"{label}: {name}"
    return label


_SYMPTOM_BODY_PART_ALIASES = {
    "眼": "eye",
    "眼睛": "eye",
    "眼部": "eye",
    "呼吸道": "respiratory",
    "鼻": "respiratory",
    "鼻部": "respiratory",
    "喉咙": "respiratory",
    "嗓子": "respiratory",
    "皮肤": "skin",
    "头": "head",
    "头部": "head",
    "消化道": "digestive",
    "胃": "digestive",
    "腹部": "digestive",
    "腰": "musculoskeletal",
    "腰部": "musculoskeletal",
    "背": "musculoskeletal",
    "背部": "musculoskeletal",
    "颈": "musculoskeletal",
    "颈部": "musculoskeletal",
    "肩": "musculoskeletal",
    "肩部": "musculoskeletal",
    "膝": "musculoskeletal",
    "膝盖": "musculoskeletal",
    "关节": "musculoskeletal",
}
_SYMPTOM_BODY_PART_MARKERS = (
    ("eye", ("眼痒", "眼痛", "眼红", "眼睛")),
    ("respiratory", (
        "咳嗽", "咳痰", "嗓子", "喉咙", "鼻塞", "流鼻涕", "打喷嚏", "喷嚏", "呼吸",
    )),
    ("skin", ("皮疹", "起疹", "皮肤", "瘙痒", "湿疹")),
    ("digestive", ("胃痛", "胃疼", "腹痛", "腹胀", "肚子痛", "恶心", "呕吐")),
    ("head", ("头痛", "头疼", "头晕", "眩晕")),
    ("musculoskeletal", (
        "腰痛", "腰疼", "腰酸", "后腰", "下腰", "背痛", "背疼", "颈痛", "颈疼",
        "肩痛", "肩疼", "膝痛", "膝疼", "膝盖", "关节痛", "肌肉痛",
    )),
)

_SYMPTOM_NEGATION_MARKERS = (
    "没有",
    "没",
    "不",
    "无",
    "未",
    "否认",
    "不再",
    "好了",
    "缓解",
    "消失",
    "排除",
)
_SYMPTOM_QUESTION_MARKERS = (
    "怎么办",
    "怎么处理",
    "如何处理",
    "为什么",
    "是否",
    "是不是",
    "要不要",
    "能不能",
    "需要吗",
    "该不该",
    "能否",
    "可否",
    "可不可以",
    "吗",
    "呢",
    "？",
    "?",
)
_SYMPTOM_NON_SELF_MARKERS = (
    "朋友",
    "家人",
    "我爸",
    "我妈",
    "爸爸",
    "妈妈",
    "父亲",
    "母亲",
    "孩子",
    "他人",
    "别人",
    "同事",
    "同学",
    "邻居",
    "室友",
    "老婆",
    "妻子",
    "老公",
    "丈夫",
    "儿子",
    "女儿",
    "哥哥",
    "姐姐",
    "弟弟",
    "妹妹",
    "爷爷",
    "奶奶",
    "外公",
    "外婆",
    "叔叔",
    "阿姨",
    "患者",
    "病人",
    "医生说",
    "报告",
    "检查提示",
    "病历",
    "附件",
    "图片",
    "照片",
)


def _symptom_text_has_non_self_reference(normalized: str) -> bool:
    if any(marker in normalized for marker in _SYMPTOM_NON_SELF_MARKERS):
        return True
    symptom_markers = tuple(
        marker
        for _, markers in _SYMPTOM_BODY_PART_MARKERS
        for marker in markers
    )
    # 在同一分句内检查完整主体上下文。固定长度窗口会漏掉“他今天早上在
    # 办公室连续打了一个喷嚏”这类自然表达；分句边界又能避免把“我说我
    # 打喷嚏”中的“说”误判成第三方主体。
    clauses = re.split(
        r"[，,。！？!?；;：:、\n]|然后|而且|但是|不过|并且|以及|同时|后来|之后|再加上|另外",
        normalized,
    )
    non_self_subject_re = re.compile(
        r"(?:他|她|他们|她们|我爸|我妈|我父亲|我母亲|爸爸|妈妈|朋友|同事|家人|患者|病人)"
    )
    # 只取“小王/小李”这类常见称呼的两字主体；限制贪婪长度，避免把
    # “小王打喷嚏”整体吞掉后错过后面的动作词。
    name_re = re.compile(r"小[\u4e00-\u9fff]{1,2}")
    for clause in clauses:
        if not clause:
            continue
        symptom_indexes = [
            index
            for marker in symptom_markers
            for index in [clause.find(marker)]
            if index >= 0
        ]
        if not symptom_indexes:
            continue
        first_symptom_index = min(symptom_indexes)
        if any(
            match.start() < first_symptom_index
            for match in non_self_subject_re.finditer(clause)
        ):
            return True
        # 小王等姓名需要后续确实出现动作词,避免把“小腿疼”识别成第三方。
        for match in name_re.finditer(clause[:first_symptom_index]):
            # 症状标记本身可能包含动作词(例如“打喷嚏”),所以窗口要包含
            # 标记开头,否则“小王打喷嚏”会因动作词恰好位于边界而漏检。
            suffix = clause[match.end():first_symptom_index + 4]
            if re.search(r"(?:有|出现|打|说|疼|痛|痒|胀|咳|流)", suffix):
                return True
    return False


def _symptom_text_is_current_self_observation(normalized: str) -> bool:
    """Reject negated or third-party/report symptom mentions before auto-write."""
    if any(marker in normalized for marker in _SYMPTOM_QUESTION_MARKERS):
        return False
    if _symptom_text_has_non_self_reference(normalized):
        return False
    symptom_markers = tuple(
        marker
        for _, markers in _SYMPTOM_BODY_PART_MARKERS
        for marker in markers
    ) + ("症状", "不适", "难受", "不舒服")
    for symptom_marker in symptom_markers:
        start = 0
        while True:
            index = normalized.find(symptom_marker, start)
            if index < 0:
                break
            window = normalized[max(0, index - 8): index + len(symptom_marker) + 8]
            preceding = normalized[max(0, index - 8):index]
            if any(
                negation in window
                for negation in _SYMPTOM_NEGATION_MARKERS
                if negation != "不"
            ) or "不" in preceding:
                return False
            start = index + len(symptom_marker)
    return True


def _normalize_symptom_body_part(data: Dict[str, Any]) -> None:
    """Normalize explicit Chinese symptom locations without inventing unknown ones.

    Weak models occasionally emit ``description`` but omit the enum ``body_part``.
    Only high-signal aliases are filled; an unrecognized description remains invalid
    and is handled by the existing API validation instead of being guessed.
    """
    raw_part = str(data.get("body_part") or "").strip().lower()
    if raw_part in {
        "eye", "respiratory", "skin", "digestive", "musculoskeletal", "head", "general", "other",
    }:
        return
    if raw_part in _SYMPTOM_BODY_PART_ALIASES:
        data["body_part"] = _SYMPTOM_BODY_PART_ALIASES[raw_part]
        return
    if raw_part:
        return
    description = str(data.get("description") or "").strip()
    if not description:
        return
    for body_part, markers in _SYMPTOM_BODY_PART_MARKERS:
        if any(marker in description for marker in markers):
            data["body_part"] = body_part
            return


def _extract_clear_symptom_record(message: Any) -> Optional[Dict[str, str]]:
    """Extract a high-confidence current symptom from the user's own sentence.

    This is deliberately narrower than medical interpretation: it only maps an
    explicit symptom statement to the existing ``/symptoms`` schema.  Questions
    such as ``腰疼怎么办`` stay on the advice path and are never converted into
    a write.  The original wording is retained as the description for auditability.
    """
    raw = str(message or "").strip()
    if not raw:
        return None
    intent = classify_agent_utterance(raw)
    if not (
        intent.primary == "write"
        and intent.operation == "create"
        and intent.domain == "symptom"
        and intent.is_write
    ):
        return None

    normalized = "".join(raw.split()).lower()
    if not _symptom_text_is_current_self_observation(normalized):
        return None
    for body_part, markers in _SYMPTOM_BODY_PART_MARKERS:
        if any(marker in normalized for marker in markers):
            return {
                "body_part": body_part,
                "description": raw.strip("。！？!?；;，, ")[:500],
            }

    # A clear but non-localized statement can still be stored as a general
    # symptom; the user can refine the body part later from the record card.
    if "症状" in normalized or any(
        marker in normalized for marker in ("不适", "难受", "不舒服")
    ):
        return {
            "body_part": "general",
            "description": raw.strip("。！？!?；;，, ")[:500],
        }
    return None


_RHINITIS_COUNT_RE = re.compile(
    r"(?:打|连打|连续打)(?:了)?(?P<count>\d+|零|一|两|二|三|四|五|六|七|八|九|十)(?:个|次)?喷嚏"
)
_RHINITIS_SEVERITY_RE = re.compile(
    r"[^，,。！？!?；;：:、]{0,3}(?:程度|等级|级别)?(?:是|为)?"
    r"(?P<severity>[0-3])(?:级|分)"
)
_RHINITIS_CN_NUMBERS = {
    "零": 0,
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _extract_clear_rhinitis_record(message: Any) -> Optional[Dict[str, int]]:
    """Extract explicit rhinitis fields from the current user turn only.

    The model may choose ``record_type=rhinitis`` but it is never trusted to
    decide the count or severity. This helper is deliberately narrow: a
    current self-observation must contain ``喷嚏``/``鼻塞``/``流鼻涕`` and pass
    the same question, negation, attachment, and third-party checks as symptoms.
    """
    symptom = _extract_clear_symptom_record(message)
    if not symptom or symptom.get("body_part") != "respiratory":
        return None
    normalized = "".join(str(message or "").split()).lower()
    data: Dict[str, int] = {}
    if "喷嚏" in normalized:
        match = _RHINITIS_COUNT_RE.search(normalized)
        raw_count = match.group("count") if match else "一"
        count = _RHINITIS_CN_NUMBERS.get(raw_count)
        if count is None:
            count = int(raw_count)
        if count > 0:
            data["sneezing"] = count
    if "鼻塞" in normalized:
        marker_end = normalized.find("鼻塞") + len("鼻塞")
        suffix = normalized[marker_end:marker_end + 12].lstrip("，,。！？!?；;：:、")
        match = _RHINITIS_SEVERITY_RE.search(suffix)
        data["congestion"] = int(match.group("severity")) if match else 1
    if "流鼻涕" in normalized or "流涕" in normalized:
        marker = "流鼻涕" if "流鼻涕" in normalized else "流涕"
        marker_end = normalized.find(marker) + len(marker)
        suffix = normalized[marker_end:marker_end + 12].lstrip("，,。！？!?；;：:、")
        match = _RHINITIS_SEVERITY_RE.search(suffix)
        data["runny_nose"] = int(match.group("severity")) if match else 1
    return data or None


def _recover_clear_symptom_args(args: Any, message: Any) -> Any:
    """Fill only missing symptom fields from an unambiguous user statement."""
    if not isinstance(args, dict):
        return args
    extracted = _extract_clear_symptom_record(message)
    if not extracted:
        return args

    rtype = _fast_record_kind(args)
    if rtype not in ("", "symptom"):
        return args
    args["record_type"] = "symptom"
    data = args.get("data")
    if not isinstance(data, dict):
        data = {}
        args["data"] = data
    for key, value in extracted.items():
        if data.get(key) in (None, ""):
            data[key] = value
    return args


def _build_deterministic_symptom_tool_call(
    message: Any,
    *,
    write_receipts: Sequence[dict[str, Any]],
    has_attachment: bool = False,
) -> Optional[Dict[str, Any]]:
    """Build one write call when a clear symptom was answered without a tool.

    The fast-record path already classifies a declarative symptom as a write, but
    a weak model can still return prose or only run a read tool. In that case the
    user's own sentence is the only trusted payload we need: it is normalized by
    the same narrow extractor used by malformed-call recovery, then sent through
    the normal health_record validator, gateway, write checkpoint, and receipt
    path. Questions remain on the advice path, and an existing receipt prevents a
    second write.
    """
    if write_receipts or has_attachment:
        return None
    extracted = _extract_clear_symptom_record(message)
    if not extracted:
        return None
    description = extracted["description"]
    return {
        "id": f"deterministic-symptom-{_sha12(description)}",
        "type": "function",
        "function": {
            "name": "health_record",
            "arguments": json.dumps(
                {
                    "record_type": "symptom",
                    "data": extracted,
                },
                ensure_ascii=False,
            ),
        },
    }


def _build_deterministic_simple_record_tool_call(
    goal: Optional[GoalSpec],
    *,
    write_receipts: Sequence[dict[str, Any]],
    has_attachment: bool = False,
) -> Optional[Dict[str, Any]]:
    """Recover one narrow server-owned write from a typed task contract."""
    if (
        goal is None
        or goal.kind != "simple_health_record"
        or goal.operation != "create"
        or write_receipts
        or has_attachment
    ):
        return None
    arguments = _simple_record_goal_arguments(goal)
    if arguments is None:
        return None
    return {
        "id": f"deterministic-simple-record-{_sha12(repr(arguments))}",
        "type": "function",
        "function": {
            "name": "health_record",
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _simple_record_goal_arguments(
    goal: Optional[GoalSpec],
) -> Optional[Dict[str, Any]]:
    """Build the only write payload authorized by a simple-record goal."""
    if goal is None or goal.kind != "simple_health_record":
        return None
    values = dict(goal.target_values)
    if goal.target_record_type == "water":
        try:
            amount_ml = int(values["amount_ml"])
            canonical_date = date.fromisoformat(
                str(goal.target_date or "").strip()
            ).isoformat()
        except (KeyError, TypeError, ValueError):
            return None
        if not 1 <= amount_ml <= 5000:
            return None
        return {
            "record_type": "water",
            "data": {
                "amount": amount_ml,
                "record_date": canonical_date,
            },
        }
    if goal.target_record_type == "symptom":
        body_part = str(values.get("body_part") or "").strip()
        description = str(values.get("description") or "").strip()
        if (
            body_part not in {
                "eye",
                "respiratory",
                "skin",
                "digestive",
                "musculoskeletal",
                "head",
                "general",
                "other",
            }
            or not description
        ):
            return None
        return {
            "record_type": "symptom",
            "data": {
                "body_part": body_part,
                "description": description[:500],
            },
        }
    if goal.target_record_type == "diet":
        meal_type = str(values.get("meal_type") or "").strip().lower()
        food_items = str(values.get("food_items") or "").strip()
        record_date = str(goal.target_date or "").strip()
        if (
            meal_type not in {"breakfast", "lunch", "dinner", "snack"}
            or not food_items
        ):
            return None
        try:
            canonical_date = date.fromisoformat(record_date).isoformat()
        except (TypeError, ValueError):
            return None
        return {
            "record_type": "diet",
            "data": {
                "record_date": canonical_date,
                "meal_type": meal_type,
                "food_items": food_items[:1000],
                "source": "agent_text",
            },
        }
    return None


def _merge_equivalent_diet_model_estimates(
    goal: GoalSpec,
    *,
    model_args: Dict[str, Any],
    authoritative_args: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep estimates only when the model preserved the user-owned meal."""
    authoritative_data = dict(authoritative_args.get("data") or {})
    model_record_type = _normalize_fast_record_kind(
        model_args.get("record_type")
        or model_args.get("type")
        or model_args.get("kind")
        or ""
    )
    if model_record_type != "diet":
        return authoritative_args

    model_data = _normalize_diet_create_data(
        model_args,
        default_record_date=goal.target_date,
    )
    nutrient_fact_patterns = {
        "calories": re.compile(
            r"(?:(?:热量|卡路里)\s*[:：]?\s*)?"
            r"(?P<value>\d+(?:\.\d+)?)\s*(?:千卡|kcal|大卡)",
            re.IGNORECASE,
        ),
        "protein": re.compile(
            r"蛋白质\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:克|g)",
            re.IGNORECASE,
        ),
        "carbs": re.compile(
            r"碳水(?:化合物)?\s*[:：]?\s*"
            r"(?P<value>\d+(?:\.\d+)?)\s*(?:克|g)",
            re.IGNORECASE,
        ),
        "fat": re.compile(
            r"脂肪\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:克|g)",
            re.IGNORECASE,
        ),
        "fiber": re.compile(
            r"膳食纤维\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:克|g)",
            re.IGNORECASE,
        ),
    }

    def extract_user_nutrition(value: Any) -> dict[str, float]:
        text = str(value or "")
        result: dict[str, float] = {}
        for field, pattern in nutrient_fact_patterns.items():
            match = pattern.search(text)
            if match is not None:
                result[field] = float(match.group("value"))
        return result

    def strip_user_nutrition(value: Any) -> str:
        text = str(value or "")
        for pattern in nutrient_fact_patterns.values():
            text = pattern.sub("", text)
        return text.strip(" \t\r\n,，、;；。.!！:：")

    user_nutrition = extract_user_nutrition(
        authoritative_data.get("food_items")
    )
    for field, user_value in user_nutrition.items():
        model_value = model_data.get(field)
        if (
            not isinstance(model_value, (int, float))
            or isinstance(model_value, bool)
            or not math.isfinite(float(model_value))
            or not math.isclose(
                float(model_value),
                user_value,
                rel_tol=1e-6,
                abs_tol=1e-6,
            )
        ):
            return authoritative_args

    quantity_number = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百半]+)"
    quantity_unit = r"(?:毫升|ml|克|g|碗|杯|份|个|只|枚|颗|片|块|根|条)"
    leading_quantity_re = re.compile(
        rf"^(?P<number>{quantity_number})(?P<unit>{quantity_unit})"
        r"(?P<food>.+)$",
        re.IGNORECASE,
    )
    trailing_quantity_re = re.compile(
        rf"^(?P<food>.+?)(?P<number>{quantity_number})"
        rf"(?P<unit>{quantity_unit})$",
        re.IGNORECASE,
    )

    def flat_food_identity(value: Any) -> str:
        return re.sub(
            r"[\s,，、。.!！;；:：]+",
            "",
            str(value or ""),
        ).casefold()

    def conjunction_food_identity(value: Any) -> str:
        normalized = flat_food_identity(value)
        return re.sub(
            r"(?<=[\u4e00-\u9fff])(?:和|与)(?=[\u4e00-\u9fff])",
            "",
            normalized,
        )

    def normalized_quantity(value: str) -> str:
        raw = value.casefold()
        try:
            return str(float(raw)).removesuffix(".0")
        except ValueError:
            pass
        if raw == "半":
            return "0.5"
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
        if raw == "十":
            return "10"
        if "十" in raw:
            tens, ones = raw.split("十", 1)
            value_int = digits.get(tens, 1) * 10 + digits.get(ones, 0)
            return str(value_int)
        if raw in digits:
            return str(digits[raw])
        return raw

    def food_parts(value: Any) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [
                str(item).strip()
                for item in value
                if str(item).strip()
            ]
        raw = str(value or "").strip()
        if not raw:
            return []
        parts = [
            part.strip()
            for part in re.split(r"[,，、;；/|]+", raw)
            if part.strip()
        ]
        if len(parts) != 1:
            return parts

        # ASR and weak models often omit separators:
        # "一个包子一个茶叶蛋一碗粥". Split only at explicit quantity-unit
        # boundaries, so food names themselves remain authoritative.
        marker_re = re.compile(
            rf"(?={quantity_number}{quantity_unit})",
            re.IGNORECASE,
        )
        starts = [match.start() for match in marker_re.finditer(raw)]
        if len(starts) > 1 and starts[0] == 0:
            return [
                raw[start:end].strip()
                for start, end in zip(starts, starts[1:] + [len(raw)])
                if raw[start:end].strip()
            ]
        return parts

    def canonical_food_identity(value: Any) -> tuple[str, ...]:
        canonical: list[str] = []
        unit_aliases = {"只": "个", "枚": "个", "颗": "个"}
        lexicalized_quantity_dishes = {"三杯鸡", "一碗香"}
        beverage_terms = (
            "水",
            "牛奶",
            "奶",
            "豆浆",
            "咖啡",
            "茶",
            "果汁",
            "酸奶",
            "酒",
            "饮料",
        )
        for raw_part in food_parts(value):
            part = re.sub(r"[\s。.!！:：]+", "", raw_part).casefold()
            if part in lexicalized_quantity_dishes:
                canonical.append(part)
                continue
            match = leading_quantity_re.fullmatch(part)
            if match is None:
                match = trailing_quantity_re.fullmatch(part)
            if match is None:
                canonical.append(part)
                continue
            food = re.sub(
                r"[\s。.!！:：]+",
                "",
                match.group("food"),
            ).casefold()
            unit = match.group("unit").casefold()
            if unit == "杯" and not any(term in food for term in beverage_terms):
                canonical.append(part)
                continue
            canonical.append(
                f"{food}#{normalized_quantity(match.group('number'))}"
                f"{unit_aliases.get(unit, unit)}"
            )
        return tuple(sorted(canonical))

    authoritative_food_items = strip_user_nutrition(
        authoritative_data.get("food_items")
    )
    direct_food_matches = (
        flat_food_identity(model_data.get("food_items"))
        == flat_food_identity(authoritative_food_items)
        or canonical_food_identity(model_data.get("food_items"))
        == canonical_food_identity(authoritative_food_items)
    )
    conjunction_food_matches = bool(user_nutrition) and (
        conjunction_food_identity(model_data.get("food_items"))
        == conjunction_food_identity(authoritative_food_items)
    )
    food_matches = direct_food_matches or conjunction_food_matches
    if (
        str(model_data.get("meal_type") or "").strip().lower()
        != str(authoritative_data.get("meal_type") or "").strip().lower()
        or not food_matches
    ):
        return authoritative_args

    merged_data = dict(authoritative_data)
    merged_data["food_items"] = (
        str(model_data["food_items"]).strip()[:1000]
        if direct_food_matches
        else authoritative_food_items[:1000]
    )
    for field in (
        "calories",
        "protein",
        "carbs",
        "fat",
        "fiber",
        "alcohol_units",
        "health_tips",
    ):
        if model_data.get(field) not in (None, "", []):
            merged_data[field] = model_data[field]
    return {
        "record_type": "diet",
        "data": merged_data,
    }


def _simple_record_goal_completion_text(goal: GoalSpec) -> str:
    """Render a verified simple-record result without another model call."""
    values = dict(goal.target_values)
    if goal.target_record_type == "water":
        return f"已记录饮水 {values.get('amount_ml')}ml"
    if goal.target_record_type == "symptom":
        return f"已记录症状：{values.get('description')}"
    if goal.target_record_type == "diet":
        meal_label = {
            "breakfast": "早餐",
            "lunch": "午餐",
            "dinner": "晚餐",
            "snack": "加餐",
        }.get(str(values.get("meal_type") or ""), "饮食")
        return f"已记录{meal_label}。"
    return "记录已完成。"


def _symptom_write_authorized_by_current_turn(
    message: Any,
    recent_messages: Any,
) -> bool:
    """Whether the current turn authorizes a symptom write."""
    return _symptom_write_authorization(message, recent_messages) is not None


def _symptom_write_authorization(
    message: Any,
    recent_messages: Any,
) -> Optional[Dict[str, str]]:
    """Return the exact symptom payload explicitly stated in this turn, if any.

    A standalone confirmation is intentionally not an authorization source: a
    conversational transcript cannot safely bind it to one pending symptom. The
    caller must ask the user to repeat the symptom in the current turn instead.
    """
    del recent_messages
    raw = str(message or "").strip()
    if not raw:
        return None
    current_record = _extract_clear_symptom_record(raw)
    if current_record:
        return current_record
    return None


def _apply_authorized_symptom_payload(
    args: Any,
    authorization: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Replace model-authored symptom fields with the current-turn payload."""
    if not isinstance(args, dict):
        return None
    data = {
        "body_part": authorization["body_part"],
        "description": authorization["description"],
    }
    authorized_args: Dict[str, Any] = {"record_type": "symptom", "data": data}
    # This flag is injected by the server-side channel gate. Preserve only the
    # fail-closed True value while replacing all model-authored health fields.
    if args.get("_fast_record_requires_confirmation") is True:
        authorized_args["_fast_record_requires_confirmation"] = True
    return authorized_args


def _apply_authorized_rhinitis_payload(
    args: Any,
    authorization: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    """Replace all model-authored rhinitis values with current-turn values."""
    if not isinstance(args, dict) or not authorization:
        return None
    authorized_args: Dict[str, Any] = {
        "record_type": "rhinitis",
        "data": dict(authorization),
    }
    if args.get("_fast_record_requires_confirmation") is True:
        authorized_args["_fast_record_requires_confirmation"] = True
    return authorized_args


def _prepare_health_record_args_for_validation(
    tool_name: str,
    args: Any,
    *,
    reference_now: Optional[datetime] = None,
) -> Any:
    if tool_name != "health_record" or not isinstance(args, dict):
        return args

    rtype = _fast_record_kind(args)
    if rtype:
        args["record_type"] = rtype

    data = args.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
            args["data"] = data
        except (json.JSONDecodeError, ValueError):
            data = None
    if not isinstance(data, dict):
        return args

    if rtype == "exercise" and not data.get("exercise_type"):
        fallback_type = data.get("type") or data.get("name") or args.get("exercise_type")
        if fallback_type:
            data["exercise_type"] = fallback_type

    if rtype == "symptom":
        _normalize_symptom_body_part(data)

    # 相对日期字面量归一 (record_date/start_date/end_date): 弱模型把 '昨天'/'前天' 当字面
    # 塞进 data。health_query/health_manage 早在工具边界过 _normalize_relative_date, 但 record
    # 创建路径漏了 —— 结果 diet/sleep 等 record_date='昨天' 被 _validate_date 静默吞成今天
    # (违反 fail-loud), illness/goal 的 start_date='前天' 原样发出 → 端点 date 解析 422。
    # 这里在校验前折成真 ISO 日期; 解析不出(返回 None)才留给下游默认, 不覆盖。
    for _dk in ("record_date", "start_date", "end_date"):
        if data.get(_dk):
            _iso = _normalize_relative_date(data[_dk], reference_now=reference_now)
            if _iso:
                data[_dk] = _iso

    return args


def _apply_server_health_record_provenance(
    tool_name: str,
    args: Any,
    *,
    execution_source: str,
    has_attachment: bool,
    diet_photo_auto_save: bool,
    contextual_diet_recorded: bool,
    user_message: str,
) -> Any:
    """Replace model-authored diet provenance with server-known turn provenance."""
    if (
        tool_name != "health_record"
        or not isinstance(args, dict)
        or _fast_record_kind(args) != "diet"
    ):
        return args

    data = args.get("data")
    if not isinstance(data, dict):
        return args

    if execution_source == "procedure_recipe_replay":
        if data.get("source") == "agent_text":
            data["source"] = "procedure_recipe"
        return args

    if execution_source != "structured_or_recovered":
        return args

    if contextual_diet_recorded:
        # Contextual capture already persisted the authoritative meal. This
        # redundant model call must reach _exec_health_record so it can replay
        # that verified receipt instead of failing nutrition validation.
        data["source"] = "contextual_diet_replay"
    elif has_attachment or diet_photo_auto_save:
        # Auto-save intent proves an attachment turn even on legacy clients
        # that omitted the explicit has_attachment flag. If capture failed,
        # the fallback still has to provide complete estimated nutrition.
        data["source"] = "agent_attachment"
    elif str(user_message or "").strip():
        data["source"] = "agent_text"
    return args


# 2026-05-14 #4 可解释性 — tool 名 → 中文标签
# 用户在 chat bubble 看到 "AI 用了什么数据" 时, 能看懂 (不是 raw tool name).
_TOOL_TO_SOURCE_LABEL = {
    "health_query": "健康数据查询 (Garmin/化验/补剂)",
    "health_record": "今天打卡记录",
    "health_manage": "健康记录管理 (查询/修改/删除)",
    "query_lab_indicators": "化验/体征指标历史",
    "exam_query": "化验单详情",
    "indicator_history": "指标历史趋势",
    "knowledge_search": "得到 wiki 知识库",
    "garmin_sync": "Garmin 实时同步",
}


def _source_labels_from_system_prompt(system_content: str) -> list[str]:
    """Return deterministic source labels for structured context actually injected."""
    if not system_content:
        return []
    labels: list[str] = []
    if (
        re.search(r"(?m)^## 用户记忆\s*$", system_content)
        or re.search(r"(?m)^用户历史记忆\s*[:：]\s*$", system_content)
    ):
        labels.append("用户记忆")
    return labels


# 工具 → 思考过程 status 事件里展示的**短**中文名 (mac 端"正在……"胶囊)。
# 与 _TOOL_TO_SOURCE_LABEL (数据源溯源, 更长) 独立: 这里要短、动词化。
# 未映射的工具 → 原始名 (见 _tool_status_label)。
_TOOL_TO_STATUS_LABEL = {
    "health_query": "查询健康数据",
    "health_query_batch": "批量查询健康数据",
    "health_record": "写入记录",
    "health_manage": "管理记录",
    "health_analysis": "深度分析",
    "knowledge_search": "检索知识库",
    "realtime_search": "联网搜索",
}


def _tool_status_label(func_name: Optional[str]) -> str:
    """工具名 → 思考过程 status 事件的短中文标签; 未知工具回退原始名。"""
    if not func_name:
        return "工具"
    return _TOOL_TO_STATUS_LABEL.get(func_name, func_name)


# 2026-07-05 P0-1: 流式进度事件 (accepted/tool/synthesis)。
# 工具名 → **完整的人话动词短语** (给 progress status 事件的 label 字段, 客户端
# 直接展示成一行"正在……")。与 _TOOL_TO_STATUS_LABEL (更短、给旧 status.detail 通道)
# 独立: 这里覆盖 tool_schema_registry 的全部工具名 + specialist_tools 的分析工具,
# 未映射的一律兜底"正在处理…"(见 _tool_progress_label)。工具粒度不区分饮水/步数
# (health_record 覆盖所有记录), 短语按工具语义写。
_TOOL_PROGRESS_LABEL = {
    # 核心工具 (tool_schema_registry.HEALTH_TOOLS)
    "health_query": "查看健康数据…",
    "health_query_batch": "汇总健康数据…",
    "health_record": "正在记录…",
    "health_manage": "整理健康记录…",
    "health_analysis": "深度分析中…",
    "environment_check": "查看天气与环境…",
    "supplement_guide": "查阅补剂方案…",
    "upload_genetic_txt": "导入基因数据…",
    "query_genetic_profile": "查阅基因数据…",
    "upload_medical_exam_text": "录入体检报告…",
    "query_lab_indicators": "查看化验指标…",
    "intervention_cycle": "整理干预周期…",
    "knowledge_search": "检索知识库…",
    "realtime_search": "联网搜索中…",
    "manage_plan": "整理健康计划…",
    "draft_aigc_media": "正在准备创作草稿…",
    # specialist 分析工具 (specialist_tools.specialist_tool_schemas, flag 开时才注册)
    "analyze_recovery": "评估恢复状态…",
    "analyze_fuel": "分析营养方案…",
    "analyze_movement": "评估训练负荷…",
    "analyze_mental": "评估心理状态…",
    "analyze_hypertension": "分析血压情况…",
    "analyze_metabolic": "分析代谢指标…",
    "analyze_rhinitis": "评估鼻炎症状…",
    "analyze_longitudinal": "分析长期趋势…",
    "analyze_longevity": "解读表型年龄…",
}
_TOOL_PROGRESS_FALLBACK = "正在处理…"


def _tool_progress_label(func_name: Optional[str]) -> str:
    """工具名 → 进度事件 label (完整人话动词短语); 未映射一律兜底"正在处理…"。"""
    if not func_name:
        return _TOOL_PROGRESS_FALLBACK
    return _TOOL_PROGRESS_LABEL.get(func_name, _TOOL_PROGRESS_FALLBACK)


def _is_reminder_schedule_continuation(
    message: str,
    recent_messages: Any,
) -> bool:
    """Return True only for a timing reply to a pending reminder question."""
    text = "".join(str(message or "").split()).lower()
    if not text or not any(char.isdigit() for char in text):
        return False
    if not any(marker in text for marker in ("点", ":", "到", "至", "-", "~")):
        return False
    if not isinstance(recent_messages, list):
        return False
    assistant_context = " ".join(
        str(item.get("content") or "")
        for item in recent_messages
        if isinstance(item, dict) and item.get("role") == "assistant"
    ).lower()
    return any(marker in assistant_context for marker in ("提醒", "闹钟", "提醒时间", "开始和结束", "时间段"))


def _query_only_health_manage_scope(
    message: Optional[str],
    *,
    reference_now: Optional[datetime] = None,
) -> Optional[Dict[str, str]]:
    """Return deterministic list filters for an explicit read-only request."""
    intent = classify_agent_utterance(message, reference_now=reference_now)
    if intent.primary != "read" or intent.domain != "diet":
        return None
    return dict(intent.scope)


def _has_explicit_record_write_intent(message: Optional[str]) -> bool:
    """Whether the user's '记录' means writing, not naming existing records."""
    intent = classify_agent_utterance(message)
    return intent.primary == "write" and intent.is_write


def _has_fast_record_write_intent(message: Optional[str]) -> bool:
    """Fast-record is only for clear writes; query nouns stay on the read path."""
    intent = classify_agent_utterance(message)
    return (
        intent.primary == "write"
        and intent.is_write
        and not intent.requires_reliable_tool_model
    )


_BEIJING_DATE_LABEL_RE = re.compile(
    r"(?P<prefix>北京时间\s*)(?P<year>\d{4}年)?\d{1,2}月\d{1,2}日"
)


def _ground_query_response_date_labels(
    text: str,
    message: str,
    *,
    reference_now: Optional[datetime] = None,
) -> str:
    """Ground Beijing date labels for an explicit read-only relative-date query."""
    scope = _query_only_health_manage_scope(message, reference_now=reference_now)
    target_date = (scope or {}).get("date")
    if not target_date or not text:
        return text
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return text

    def _replacement(match: re.Match[str]) -> str:
        year = f"{target.year}年" if match.group("year") else ""
        return f"{match.group('prefix')}{year}{target.month}月{target.day}日"

    return _BEIJING_DATE_LABEL_RE.sub(_replacement, text)


def _model_tool_result_content(
    tool_name: str,
    args: Dict[str, Any],
    result: str,
    *,
    reference_now: Optional[datetime] = None,
    timezone_label: str = "Asia/Shanghai",
) -> str:
    """Add deterministic query scope to the model-only tool result."""
    record_type = str(args.get("record_type") or args.get("type") or "").strip().lower()
    if tool_name == "health_record" and record_type == "reminder":
        delivery_status = _extract_reminder_delivery_status_from_result(result)
        if delivery_status:
            return (
                f"{result}\n\n"
                "[系统递送边界]\n"
                f"delivery_status.agent_claim={delivery_status.get('agent_claim') or ''}。"
                "提醒创建已完成,但这不是手表送达回执。"
                "回复用户时可以说:手机到点会尝试提醒；手表刷新今日摘要后可执行"
                "（未确认已送达手表）。"
                "除非 delivery_status.watch.delivery_confirmed=true,不得说已发送到手表、"
                "已同步到手表或已送达到手表。"
            )
    if (
        tool_name != "health_manage"
        or args.get("record_type") != "diet"
        or args.get("operation") != "list"
    ):
        return result
    target_date = _normalize_relative_date(
        args.get("date"),
        reference_now=reference_now,
    )
    if not target_date:
        return result
    return (
        "[系统查询口径]\n"
        f"时区: {timezone_label}\n"
        f"查询日期: {target_date}\n"
        "回答中如写日期，只能使用该查询日期，不得沿用历史消息中的日期。\n"
        f"[查询结果]\n{result}"
    )

def _needs_reliable_tool_model(message: Optional[str]) -> bool:
    """破坏性(删/改/撤销)或同步意图 → 工具决策必须用强模型(fast 模型不可靠,生产实证)。

    先排除**分析/建议**语境:"综合分析…我该怎么**调整**""**更新**一下认知"里的 调整/更新/修改
    是建议动词、不是记录级删改,不该被判成破坏性(否则误伤分析轮的工具决策快路由)。分析类
    本就走强模型答正文,工具决策轮该保留既有 fast 优化。真正的记录级删改("删除早餐""修改
    早餐内容")不含分析词,不受影响。"""
    return classify_agent_utterance(message).requires_reliable_tool_model


def _is_fast_eligible_turn(
    message: str,
    *,
    has_images: bool,
    has_file: bool,
) -> bool:
    """本回合是否可以路由到 FAST 模型 (延迟优化)。

    fast-eligible = 无图片/附件 且 (记录意图 或 简单查询意图) 且 **不是** 建议/分析/
    复盘/综合类回合。建议/分析类要用户的质量模型 (qwen3.7-plus), 简单记录/查询才走快模型。

    保守优先: 拿不准 (既非记录也非简单查询, 或命中 advice) → False = 用质量模型。
    宁可慢而对, 不要快而错。
    """
    if has_images or has_file:
        return False
    intent = classify_agent_utterance(message)
    if intent.primary == "advice":
        return False
    # 破坏性/同步意图 → 必须强模型做工具决策(弱 fast 不可靠),整轮不降 fast。
    if intent.requires_reliable_tool_model:
        return False
    # 否定("别记/记在心里")→ 全模型自行裁量地更可靠(弱 fast 模型只靠 tool-schema 软指令
    # 拒记,不稳)。整轮不降 fast,让强模型稳妥地"不记 + 不谎报已记"(2026-07-17 生产实测:
    # 否定轮被降到 qwen3.6-flash,虽本次正确拒记,但 health_record 仍在工具集里,软护栏不牢)。
    if intent.reason == "negated_write":
        return False
    if intent.primary == "write" and intent.is_write:
        return True
    return intent.primary == "read" and intent.domain != "unknown"


def _fast_turn_tool_names_for_message(message: Optional[str]) -> tuple:
    """Expose write tools only to semantic write turns."""
    intent = classify_agent_utterance(message)
    if intent.primary == "read" and not intent.is_write:
        return FAST_READ_TURN_TOOL_NAMES
    return FAST_TURN_TOOL_NAMES


_AIGC_MEDIA_DRAFT_TOOL_NAMES: tuple[str, ...] = ("draft_aigc_media",)
_AIGC_MEDIA_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "活动",
        re.compile(r"活动|运动|训练|步数|[0-9０-９]+\s*步|跑步|步行|骑行|游泳|消耗"),
    ),
    ("饮食", re.compile(r"饮食|早餐|午餐|晚餐|加餐|餐食|热量|蛋白质|碳水|脂肪|kcal", re.IGNORECASE)),
    ("睡眠", re.compile(r"睡眠|入睡|深睡|清醒|起床|睡眠分")),
    ("补水", re.compile(r"补水|饮水|喝水|水分")),
    ("用药提醒", re.compile(r"用药|服药|吃药|药物提醒")),
    ("健康计划", re.compile(r"健康计划|行动计划|今日计划|明日计划")),
)


def _aigc_media_content_preview(*, kind: str, prompt: str) -> Dict[str, Any]:
    """Project an allowlisted category summary without exposing prompt details."""
    source = str(prompt or "")
    topics = [
        label
        for label, pattern in _AIGC_MEDIA_TOPIC_PATTERNS
        if pattern.search(source)
    ][:3]
    medium = "短视频" if kind in {"text_to_video", "image_to_video"} else "图片"
    if not topics:
        return {
            "content_summary": f"根据本轮创作描述生成健康行动{medium}",
            "content_topics": [],
        }
    topic_text = (
        topics[0]
        if len(topics) == 1
        else f"{topics[0]}和{topics[1]}"
        if len(topics) == 2
        else f"{'、'.join(topics[:-1])}和{topics[-1]}"
    )
    return {
        "content_summary": f"围绕{topic_text}生成健康行动{medium}",
        "content_topics": topics,
    }


def _is_explicit_aigc_media_draft_turn(message: Optional[str]) -> bool:
    """Return whether this turn must create a user-confirmed AIGC draft."""
    intent = classify_agent_utterance(message)
    return (
        intent.primary == "write"
        and intent.is_write
        and intent.domain == "aigc_media"
        and intent.operation == "create"
    )


def _tool_names_for_turn(
    message: Optional[str],
    *,
    fast_route: bool,
    analysis_subset: bool,
) -> tuple[str, ...] | None:
    """Select the least-privilege tool set for a semantically typed turn."""
    if _is_explicit_aigc_media_draft_turn(message):
        # A photo used as a video first frame is not a diet record candidate.
        # Keep the tool decision closed to the confirmation-only draft boundary.
        return _AIGC_MEDIA_DRAFT_TOOL_NAMES
    if fast_route:
        return _fast_turn_tool_names_for_message(message)
    if analysis_subset:
        return ANALYSIS_TURN_TOOL_NAMES
    return None


def _is_analysis_only_turn(message: str, *, has_images: bool, has_file: bool) -> bool:
    """R5:本回合是否纯分析/知识轮(可裁到只读工具子集)。

    纯分析 = 无图/附件 且 命中分析/建议意图 且 **无**记录/破坏性/同步意图。
    保守优先:只要沾一点写意图(记录/删改/同步)就返回 False,发全集(升级护栏是兜底不是常态)。
    与 fast 简单轮互斥(fast 已有自己的 big-3 子集;调用点再排除)。
    """
    if has_images or has_file:
        return False
    intent = classify_agent_utterance(message)
    if intent.primary != "advice":
        return False
    # 有记录意图(吃了/喝了/记录…)→ 可能要写,不裁 —— 留全集。
    if intent.is_write:
        return False
    # 破坏性/同步(删/改/撤销/同步)→ 要写,不裁。
    if intent.requires_reliable_tool_model:
        return False
    return True


def _tool_subset_withheld_upgrade(
    tool_calls: List[Dict[str, Any]],
    sent_tools: List[Dict[str, Any]],
    *,
    live_text_already_sent: bool,
) -> tuple:
    """工具子集守卫决策(纯函数,fast + R5 analysis 共用,可单测)。

    返回 (withheld_names, action):
    - action='none'  : 模型请求的工具都在已发子集里(或幻觉工具全集也没有)→ 照常执行;
    - action='rerun' : 有「全集里真有但被子集扣下」的工具,且本轮未 live 发正文 → 升级回全集重跑;
    - action='fallthrough': 同上但本轮已 live 流式正文(analysis 轮)→ 不重跑(避免双发),
      放行让被扣工具按名执行(dispatch 按 name,不受已发子集限制;写门/R4 草稿确认仍生效)。

    只对「全集真有、被子集扣下」升级;幻觉工具名(全集也没有)不算 withheld,走原未知工具路径。
    """
    sent = {(t.get("function") or {}).get("name") for t in sent_tools}
    full = {(t.get("function") or {}).get("name") for t in get_health_tools()}
    withheld = [
        name
        for name in ((tc.get("function") or {}).get("name") for tc in tool_calls)
        if name not in sent and name in full
    ]
    if not withheld:
        return [], "none"
    return withheld, ("fallthrough" if live_text_already_sent else "rerun")


def _should_force_explicit_aigc_media_tool_choice(
    message: Optional[str],
    original_messages: List[Dict[str, Any]],
    pass_tools: Optional[List[Dict[str, Any]]],
    supports_forced_tool_choice: bool,
) -> bool:
    """Force the confirmation-only AIGC draft on a verified first tool round."""
    if not _is_explicit_aigc_media_draft_turn(message):
        return False
    if any(item.get("role") == "tool" for item in original_messages or []):
        return False
    names = {
        (tool.get("function") or {}).get("name")
        for tool in (pass_tools or [])
    }
    return names == {"draft_aigc_media"} and bool(supports_forced_tool_choice)


def _allow_twin_evidence_fallback(message: str) -> bool:
    """Whether to attach system-KB evidence from the user's Twin.

    Explicit entity mentions are handled before this function. The fallback is
    only for advice/analysis turns such as "我最近应该怎么补叶酸"; pure CRUD or
    logging turns like "记录晚餐..." should not surface a generic MTHFR/9p21
    card just because the user's Twin happens to match a reviewed claim.
    """

    text = (message or "").strip()
    if not text:
        return False
    intent = classify_agent_utterance(text)
    if intent.is_write and intent.primary != "advice":
        return False
    return intent.primary == "advice"


_BLOOD_PRESSURE_INDICATOR_ALIASES = {
    "血压",
    "bp",
    "blood pressure",
    "blood_pressure",
    "收缩压",
    "舒张压",
    "sbp",
    "dbp",
    "systolic",
    "diastolic",
}


def _is_blood_pressure_indicator_name(name: str) -> bool:
    normalized = re.sub(r"\s+", " ", (name or "").strip().lower())
    return normalized in _BLOOD_PRESSURE_INDICATOR_ALIASES


def _blood_pressure_indicator_item(record: Any) -> dict:
    systolic = getattr(record, "systolic", None)
    diastolic = getattr(record, "diastolic", None)
    category = getattr(record, "category", None)
    record_date = getattr(record, "record_date", None)
    measured_at = getattr(record, "measured_at", None)
    return {
        "source": "blood_pressure_records",
        "record_id": getattr(record, "id", None),
        "name": "血压",
        "name_en": "BP",
        "metric_key": "blood_pressure",
        "value": f"{systolic}/{diastolic}" if systolic is not None and diastolic is not None else None,
        "unit": "mmHg",
        "systolic": systolic,
        "diastolic": diastolic,
        "pulse": getattr(record, "pulse", None),
        "category": category,
        "record_date": record_date.isoformat() if record_date else None,
        "measured_at": measured_at.isoformat() if measured_at else None,
        "is_abnormal": category not in (None, "正常"),
        "components": [
            {"name": "收缩压", "name_en": "SBP", "value": systolic, "unit": "mmHg"},
            {"name": "舒张压", "name_en": "DBP", "value": diastolic, "unit": "mmHg"},
        ],
    }


def _inspect_user_data_sources(db, user_id: int) -> list:
    """快速 SQL count 用户哪些数据可用. 用于 chat done event 的 sources_used.

    返回中文标签列表, 顺序按重要性. 出错全部 swallow (旁路).
    """
    sources: list = []
    try:
        from app.models.daily_health import GarminData
        cutoff = datetime.now(UTC).date() - timedelta(days=14)
        if db.query(GarminData.id).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= cutoff,
        ).first():
            sources.append("Garmin 数据 (14 天 HRV/睡眠/RHR)")
    except Exception:
        pass

    try:
        from app.models.medical_exam import MedicalExam
        cnt = db.query(MedicalExam.id).filter(MedicalExam.user_id == user_id).count()
        if cnt:
            sources.append(f"化验报告 ({cnt} 次)")
    except Exception:
        pass

    try:
        from app.models.genetic_data import GeneticVariant
        gv = db.query(GeneticVariant.gene_name).filter(
            GeneticVariant.user_id == user_id
        ).limit(3).all()
        if gv:
            names = ', '.join(set(r[0] for r in gv if r[0]))
            sources.append(f"基因 ({names}{'...' if len(gv) >= 3 else ''})")
    except Exception:
        pass

    try:
        from app.models.medication import Medication
        med = db.query(Medication.name).filter(
            Medication.user_id == user_id,
            Medication.is_active == True,  # noqa: E712
        ).limit(2).all()
        if med:
            names = ', '.join(r[0] for r in med if r[0])
            sources.append(f"在服药物 ({names})")
    except Exception:
        pass

    try:
        from datetime import date as _date, timedelta as _timedelta
        from app.models.supplement import SupplementDefinition, SupplementRecord
        sup = db.query(SupplementDefinition.id).filter(
            SupplementDefinition.user_id == user_id,
            SupplementDefinition.is_active == True,  # noqa: E712
        ).count()
        if sup:
            # 在服(近14天有打卡)≠ 在库(is_active 定义数):标签也别混("当前
            # 补剂 24 种"曾被 LLM 当成当前摄入负担)。
            taking = (
                db.query(SupplementRecord.supplement_id)
                .filter(
                    SupplementRecord.user_id == user_id,
                    SupplementRecord.record_date >= _date.today() - _timedelta(days=13),
                    SupplementRecord.taken == True,  # noqa: E712
                )
                .distinct()
                .count()
            )
            sources.append(f"在服补剂 ({taking} 种, 库 {sup} 种)")
    except Exception:
        pass

    try:
        from app.models.user_profile import UserProfile
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile and getattr(profile, "primary_goal", None):
            goal_label = {
                "weight_loss": "减肥", "glucose": "降糖", "blood_pressure": "降压",
                "sleep": "改善睡眠", "hrv": "提升 HRV", "rhinitis": "管理鼻炎",
                "general": "总体健康",
            }.get(profile.primary_goal, profile.primary_goal)
            sources.append(f"主目标: {goal_label}")
    except Exception:
        pass

    return sources


_NEEDS_SKILL_RE = re.compile(
    r"记录|打卡|吃了|喝了|服药|补剂|体重|血压|洗鼻|喷嚏|"
    r"早餐|午餐|晚餐|加餐|夜宵|早饭|午饭|晚饭|"
    r"固化到|钉到首页|保存到首页|加到计划|"
    r"大卡|kcal|热量.*记|记.*热量"
)

def _needs_skill(msg: str) -> bool:
    return bool(_NEEDS_SKILL_RE.search(msg))


def _attach_images_to_last_user_message(
    messages: List[Dict[str, Any]], message: str, images: List[dict]
) -> None:
    """Attach chat images to the latest user message in OpenAI vision format."""

    user_msg_content: list = [{"type": "text", "text": message}]
    for img in images:
        image_type = img.get("type", "jpeg")
        user_msg_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/{image_type};base64,{img['base64']}"},
        })
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            messages[i]["content"] = user_msg_content
            break


def _strip_untrusted_write_authorization(args: Any) -> Any:
    """Remove every model-writable field that could be mistaken for consent."""
    if not isinstance(args, dict):
        return args
    args.pop("confirmed", None)
    args.pop("confirm", None)
    args.pop("_trusted_server_write_authorized", None)
    data = args.get("data")
    if isinstance(data, dict):
        data.pop("confirmed", None)
        data.pop("confirm", None)
        data.pop("_trusted_server_write_authorized", None)
    return args


def _confirm_or_describe(
    args: dict,
    data: dict,
    *,
    preview: str,
    authorized: bool = False,
) -> str | None:
    """L8 (Karpathy "verification is the bottleneck"):
    高确定性 health_record 写库前强制 LLM 复述给用户确认.

    模型参数里的 confirmed/confirm 永远不是授权来源。是否允许写入只能由调用方
    根据当前回合的确定性用户意图或服务端绑定的确认事件传入 ``authorized``。

    Args:
        args: tool_call 顶层参数
        data: args.data (会被 mutate — 剥掉 confirmed 字段防 DB schema 不识别)
        preview: 给 LLM 复述的"我准备记录: ..." 部分

    Returns:
        非 None: 当前不写库, 直接 return 这个字符串
        None  : 已确认, 调用方继续写库流程
    """
    args.pop("confirmed", None)
    args.pop("confirm", None)
    data.pop("confirmed", None)
    data.pop("confirm", None)
    if authorized:
        return None
    return (
        f"[NEEDS_CONFIRMATION] 我准备记录: {preview}. "
        "当前请求没有绑定到可验证的用户写入意图，未执行。"
        "请让用户在一条新消息中完整复述要记录的内容。"
    )


_MEDICATION_BATCH_CONFIRM_PHRASES = frozenset({
    "确认", "确认记录", "是的", "对", "没错",
})
_MEDICATION_BATCH_DISMISS_PHRASES = frozenset({
    "取消", "取消记录", "不记录", "不用了", "别记了",
})


def _normalized_medication_batch_control_phrase(text: str) -> str:
    normalized = re.sub(r"\s+", "", str(text or "").strip())
    return normalized.rstrip("。.!！")


def _medication_batch_control_action(text: str) -> Optional[str]:
    normalized = _normalized_medication_batch_control_phrase(text)
    if normalized in _MEDICATION_BATCH_CONFIRM_PHRASES:
        return "confirm"
    if normalized in _MEDICATION_BATCH_DISMISS_PHRASES:
        return "dismiss"
    return None


def _medication_batch_turn_bypasses_multi_model(text: str) -> bool:
    """Keep deterministic intake statements outside model panels.

    A bare control word such as ``对`` is only a medication confirmation when
    there is a valid immediately pending server plan.  Treating it as globally
    special would silently disable a user-requested model panel for unrelated
    conversation turns.
    """
    try:
        from app.services.medication_intake_batch import parse_medication_intake_batch

        return parse_medication_intake_batch(text) is not None
    except Exception as error:  # noqa: BLE001 — routing probe must not break chat
        logger.warning(
            "[medication_batch] deterministic routing probe failed error_type=%s",
            type(error).__name__,
        )
        return False


def _guidance_shadow_probe(user_id: int, answer_text: str) -> None:
    """[guidance-probe] 主对话答案跑 R4 guidance 红线 —— **纯影子, 只打 log**。

    背景: diet_prescription_red_line(CRITICAL)/movement_imperative_red_line 只扫
    twin.acute.pending_guidance_texts, builder 永不填充、agent_executor 零调用 →
    这条确定性 R4 规则在最大流量出口(主对话)上全程是暗的。

    为什么只打 log(不写审计/不进 meta/不追加提示/不改正文):
    - 现有饮食正则在**开放域**主对话实测 9/15 误命中(回显用户自己的记录/目标、转述
      医嘱与 KB、甚至提问句)。原护栏是在**餐食确定性模板**域调的, 外推到开放域即噪声源。
    - 写审计行会把真实 safety 评估挤出 /safety/audit 默认 20 条窗口 = 审计面 under-alarm
      (违反加层不减层); 且审计写入的 rollback 会回滚本轮尚未落库的助手消息。
    故先量分布, 再决定收紧正则 / 是否开拦截。**本函数不关闭那个 R4 洞, 只是给它装仪表。**

    用 evaluate_guidance_rules(纯求值, 无 db/无审计)而非 run_guidance_rules(带审计写入)。
    fail-soft: 影子层绝不打死回合; 但异常仍 log(不静默绿, 免这层自己变成新的藏身处)。
    """
    if not answer_text or not answer_text.strip():
        return
    try:
        from app.services.meal_analysis import evaluate_guidance_rules

        alerts = evaluate_guidance_rules(user_id, answer_text)
        if not alerts:
            return
        logger.warning(
            "[guidance-probe] 主对话答案命中 R4 guidance 红线 %d 条 user=%s rules=%s matched=%s",
            len(alerts),
            user_id,
            [a.get("rule_id") for a in alerts],
            [((a.get("data_citation") or {}).get("matched") or [])[:4] for a in alerts],
        )
    except Exception as e:  # noqa: BLE001 — 影子探针绝不断回合, 但不静默
        logger.warning("[guidance-probe] 影子扫描失败(不影响本回合): %s", e)


def _citation_anchor_shadow_meta(db, user_id: int, answer_text: str) -> Optional[Dict[str, Any]]:
    """P1 数字锚定核验(shadow)。核验最终答案里引用的个人数值能否锚定到 Twin,
    只观测不干预:返回一个可放进 done.meta 的 additive 摘要 dict(客户端不读不炸)。

    观测层铁律:**绝不打死回合**。任何异常吞掉并 log warning,把失败计数暴露到日志
    (failed_count),不做静默 —— "捕获后静默返回" 是违规。开关关或答案为空返回 None。

    Returns:
        {total, anchored, unanchored_count, anchored_ratio, failed_count} 或 None。
        unanchored 明细只进日志(可能含数值上下文),done.meta 只带计数,不外泄片段。
    """
    from app.config import settings

    if not getattr(settings, "citation_anchor_shadow", False):
        return None
    if not answer_text or not answer_text.strip():
        return None

    failed_count = 0
    try:
        from app.twin.builder import build_twin
        from app.services.citation_anchor import anchor_report

        twin = build_twin(db, user_id, use_cache=True)
        report = anchor_report(answer_text, twin)
    except Exception as e:  # noqa: BLE001 — 观测层不打死回合, 但吞点必须计数+告警(非静默)
        failed_count += 1
        logger.warning(
            "[citation_anchor] shadow eval failed user=%s failed_count=%s err=%s",
            user_id, failed_count, e,
        )
        return {
            "total": 0,
            "anchored": 0,
            "unanchored_count": 0,
            "anchored_ratio": None,
            "failed_count": failed_count,
        }

    unanchored = report.get("unanchored") or []
    try:
        logger.info(
            "[citation_anchor] user=%s ratio=%s anchored=%s/%s unanchored=%s",
            user_id,
            report.get("anchored_ratio"),
            report.get("anchored"),
            report.get("total"),
            len(unanchored),
        )
        # unanchored 明细(值 + 上下文片段)只进日志, 供 shadow 期人工核样本;
        # 上限 5 条防日志膨胀。
        for u in unanchored[:5]:
            logger.info(
                "[citation_anchor]   unanchored user=%s value=%s ctx=%r",
                user_id, u.get("value"), (u.get("context_snippet") or "")[:60],
            )
    except Exception:  # noqa: BLE001 — 连日志都不能打死回合
        failed_count += 1

    return {
        "total": report.get("total", 0),
        "anchored": report.get("anchored", 0),
        "unanchored_count": len(unanchored),
        "anchored_ratio": report.get("anchored_ratio"),
        "failed_count": failed_count,
    }


class AgentExecutor:
    """统一健康 Agent 执行器"""

    def __init__(self, db: Session):
        self.db = db
        self._current_user_id: Optional[int] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._request_model_id: Optional[str] = None
        self._turn_channel: Optional[str] = None
        self._current_turn_user_message = ""
        self._current_turn_recent_messages: list[dict] = []
        self._current_turn_source_message_id: Optional[int] = None
        self._current_turn_media_source_message_id: Optional[int] = None
        self._current_turn_conversation_id: Optional[int] = None
        self._current_turn_image_urls: list[str] = []
        self._current_turn_has_attachment = False
        self._turn_aigc_media_cards: list[dict] = []
        self._turn_contextual_diet_receipts: list[dict] = []
        self._turn_contextual_diet_cards: list[dict] = []
        self._turn_attachment_write_receipts: list[dict] = []
        self._turn_contextual_diet_record_id: Optional[int] = None
        self._turn_contextual_diet_consumed_fraction: Optional[float] = None
        self._turn_pending_write_intent_ids: list[int] = []
        self._turn_pending_write_intent_kinds: list[str] = []
        self._turn_medication_tool_intent_id: Optional[int] = None
        self._turn_medication_tool_preflight_error: Optional[str] = None
        self._turn_medication_tool_confirmation_card: Optional[dict[str, Any]] = None
        self._multi_model_turn = False
        self._diet_photo_auto_save = False
        self._prefer_fast_record_model = False
        # 本回合是否被 fast-route 到快模型 (简单记录/查询)。仅用于把答案 max_tokens
        # 从 ANSWER_MAX_TOKENS 收紧到 FAST_ROUTE_ANSWER_MAX_TOKENS —— 见 _answer_max_tokens。
        self._fast_route_simple_turn = False
        # 本**轮**是否被工具决策轮快路由到 fast 模型 (task_tiered_routing, 见
        # _maybe_fast_route_tool_round)。仅在带 tools 的轮为 True, 每轮入口重置。
        # 作用: 该轮的模型输出**只**当作工具决策 —— content 不 live 下发; 若该轮
        # 直接答文本 (无 tool_calls), 丢弃并强制在**强模型**上重合成 (安全不变量:
        # 面向用户的医疗正文绝不来自 fast 模型)。
        self._tool_round_fast_routed = False
        # fast-routed 工具决策轮专用的 lite 消息栈 (由 _run_stream_impl 在组装 full messages
        # 时快照; 见 _build_lite_tool_round_messages)。仅当**本轮**被 fast-route
        # (_tool_round_fast_routed=True) 时, _messages_for_round 才用它替换全量栈 —— 合成/
        # 答案轮与快路由失守时仍走全量栈。None = 本回合不构建 (flag 关 / 整轮已 fast / 多模态)。
        self._lite_tool_round_messages: Optional[List[Dict[str, Any]]] = None
        # 本轮之前是否已执行过任何工具 (旁路 tool_executed_count>0 给 _resolve_chat_provider)。
        # 默认路径下合成轮仍带 tools, 靠这个把"首个工具决策轮"与"工具后合成轮"分开:
        # 只有**尚无工具执行**时才把带 tools 的轮降 fast; 一旦跑过工具, 后续 (合成) 轮留强模型。
        self._turn_any_tool_executed = False
        # A3: fast 工具决策轮直接答文本被丢弃后, 置位 → 强制下一轮为**无 tools 的合成轮**,
        # 复用主循环的流式路径在强/显式模型上重合成 (tokens 逐 delta 下发, 消除 ttft=total
        # 空洞)。round_tools=[] → pass_tools falsy → 不再快路由 → 落在强/显式模型。
        self._force_no_tools_synthesis = False
        # A4: 每回合系统知识库证据卡 memo —— pre-round-1 算一次, done 复用, 避免同回合
        # 第二次 build_twin 全量重建 (拖慢 done/receipts 与 /send 回复)。若回合内发生写操作
        # (_turn_twin_write_occurred), done 侧强制重算一次以反映写后 Twin。
        self._turn_evidence_card: Any = _TURN_CARD_UNSET
        self._turn_evidence_card_key: Optional[tuple] = None
        self._turn_twin_write_occurred = False
        self._turn_diet_correction_unresolved_reason = None
        self._last_provider_model_name: Optional[str] = None
        self._request_model_tool_fallback_used = False
        self._model_fallback_reasons: List[str] = []
        self._tool_model_names: List[str] = []
        # F3a 回合内 provider 死亡备忘: 同一次 run 里, selected provider 首次失败后
        # 记住其 model_id, 后续轮不再重建/重试它 (省掉每轮 ~19s 的死等), 直接走稳定
        # 回退选择。每回合入口重置。model_id=None (默认 provider, 无注册 id) 不可记忆。
        # 分两级:
        #   _dead_provider_model_ids       — 在**无工具轮**(合成/纯文本)失败 = 彻底死,
        #                                    所有后续轮都不再选它。
        #   _tool_dead_provider_model_ids  — 只在**工具轮**失败 (如商用网关不做非流式
        #                                    tool-calling) = 仅工具轮不再选它; 无工具的
        #                                    最终合成轮仍可用它 (Opus 合成质量不丢)。
        self._dead_provider_model_ids: set[str] = set()
        self._tool_dead_provider_model_ids: set[str] = set()
        # _resolve_chat_provider 最近一次解析出的 effective model_id, 供非流式桥
        # (_call_llm_stream 判断 supports_streaming) 与死亡备忘复用。2-tuple 返回契约
        # 不变 (既有 test 依赖), 用实例属性旁路传递。
        self._last_effective_model_id: Optional[str] = None
        # 本回合是否调用过 health_analysis(深度分析/orchestrator/安全裁决)。合成轮思考
        # 封顶 (SYNTHESIS_THINKING_BUDGET) fail-closed 跳过这类回合——深度分析可能确实
        # 需要长思考, 不该被封顶。每回合入口重置。
        self._turn_invoked_deep_analysis = False
        self._current_turn_source_message_id = None
        self._current_turn_media_source_message_id = None
        self._current_turn_conversation_id = None
        self._current_turn_image_urls = []
        self._current_turn_has_attachment = False
        self._turn_aigc_media_cards = []
        # Read-only turn (starter answer pre-generation · rank7). When True, the
        # single tool-dispatch choke (_execute_tool) blocks any tool NOT on
        # _READ_ONLY_TURN_ALLOWED_TOOLS (fail-closed) and raises
        # _read_only_turn_write_attempted so the pregen orchestrator can ABORT and
        # store nothing. Default False = zero behavior change for live turns.
        self._read_only_turn = False
        self._read_only_turn_write_attempted = False
        # XiaoBa Agent Kernel state. A turn snapshots intent, timezone and current
        # time exactly once; every later tool call consumes this immutable state.
        self._agent_kernel_snapshot: Optional[TurnSnapshot] = None
        self._agent_kernel_event_bus: Optional[AgentEventBus] = None
        self._agent_kernel_turn_finished = False
        self._agent_kernel_last_decision: Optional[CapabilityDecision] = None
        self._agent_kernel_capability_block_reasons: List[str] = []
        self._agent_kernel_recovered_capability_block_reasons: List[str] = []
        self._agent_kernel_tool_failure_tools: List[str] = []
        self._agent_kernel_pending_confirmation_tools: List[str] = []
        self._agent_kernel_tool_retry_count = 0
        self._runtime_run_id: Optional[str] = None
        self._runtime_attempt_id: Optional[str] = None
        self._runtime_managed = False
        self._runtime_write_block_reason: Optional[str] = None

    def _start_agent_kernel_turn(
        self,
        *,
        user_id: int,
        message: str,
        channel: Optional[str],
        client_caps: Optional[List[str]] = None,
        client_time_context: Optional[Dict[str, Any]] = None,
        media: Optional[Sequence[dict[str, Any]]] = None,
        client_turn_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> TurnSnapshot:
        """Freeze a complete kernel snapshot before any model or tool work."""
        resolved_channel = str(channel or "chat").strip() or "chat"
        self._agent_kernel_snapshot = build_turn_snapshot(
            self.db,
            user_id=user_id,
            channel=resolved_channel,
            text=message or "",
            client_capabilities={cap: True for cap in (client_caps or [])},
            client_time_context=client_time_context,
            media=media,
            client_turn_id=client_turn_id,
            run_id=run_id,
            policy_mode=settings.agent_kernel_policy_mode,
        )
        self._agent_kernel_event_bus = AgentEventBus(self._agent_kernel_snapshot)
        self._agent_kernel_turn_finished = False
        self._agent_kernel_last_decision = None
        self._agent_kernel_capability_block_reasons = []
        self._agent_kernel_recovered_capability_block_reasons = []
        self._agent_kernel_tool_failure_tools = []
        self._agent_kernel_pending_confirmation_tools = []
        self._agent_kernel_tool_retry_count = 0
        self._agent_kernel_event_bus.turn_started()
        self._agent_kernel_event_bus.intent_decided()
        return self._refine_agent_kernel_continuation(self._agent_kernel_snapshot)

    def _attach_runtime_identity(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Add canonical control-plane IDs without changing event semantics."""
        if event.get("event") not in {"request_persisted", "done"}:
            return event
        data = event.setdefault("data", {})
        if not isinstance(data, dict):
            return event
        if self._runtime_run_id:
            data.setdefault("run_id", self._runtime_run_id)
        if self._runtime_attempt_id:
            data.setdefault("attempt_id", self._runtime_attempt_id)
        return event

    def _bind_agent_kernel_source_message(self, source_message_id: Optional[int]) -> None:
        """Bind the durable user-message id before any model/tool work begins."""
        snapshot = self._agent_kernel_snapshot
        if snapshot is None or source_message_id is None:
            return
        source_id = str(source_message_id)
        if snapshot.envelope.source_message_id == source_id:
            return
        envelope = replace(snapshot.envelope, source_message_id=source_id)
        bound = replace(snapshot, envelope=envelope)
        self._agent_kernel_snapshot = bound
        if self._agent_kernel_event_bus is not None:
            self._agent_kernel_event_bus.snapshot = bound

    def _bind_agent_kernel_actionable_references(
        self,
        references: Sequence[Any],
    ) -> None:
        """Rebind visible structured objects after the conversation is resolved."""
        snapshot = self._agent_kernel_snapshot
        if snapshot is None:
            return
        normalized = tuple(references or ())
        goal = compile_goal_spec(
            envelope=snapshot.envelope,
            context=snapshot.context,
            intent=snapshot.intent,
            actionable_references=normalized,
        )
        rebound = replace(
            snapshot,
            actionable_references=normalized,
            goal=goal,
        )
        self._agent_kernel_snapshot = rebound
        if self._agent_kernel_event_bus is not None:
            self._agent_kernel_event_bus.rebind_snapshot(
                rebound,
                reason="actionable_context_resolved",
            )

    def _ensure_agent_kernel_turn(self, *, channel: Optional[str] = None) -> TurnSnapshot:
        """Support non-chat adapters while keeping the same single-turn contract."""
        user_id = self._current_user_id
        if user_id is None:
            raise RuntimeError("Agent Kernel requires a user_id before tool execution")
        message = getattr(self, "_current_turn_user_message", "") or ""
        snapshot = self._agent_kernel_snapshot
        resolved_channel = str(
            channel
            or self._turn_channel
            or (snapshot.context.channel if snapshot is not None else "chat")
        ).strip() or "chat"
        if (
            snapshot is None
            or snapshot.context.user_id != user_id
            or snapshot.envelope.text != message
            or snapshot.context.channel != resolved_channel
        ):
            return self._start_agent_kernel_turn(
                user_id=user_id,
                message=message,
                channel=resolved_channel,
            )
        return self._refine_agent_kernel_continuation(snapshot)

    def _refine_agent_kernel_continuation(self, snapshot: TurnSnapshot) -> TurnSnapshot:
        """Turn an explicit follow-up schedule into a typed continuation write.

        A reply such as ``9点到20点`` is intentionally ambiguous in isolation.
        It becomes a write only when the immediately preceding assistant turn
        asked for reminder timing.  This is deterministic conversation state,
        not a keyword authorization bypass; ToolGateway still evaluates the
        resulting tool request and confirmation/receipt rules.
        """
        if (
            snapshot.intent.primary != "unknown"
            or not _is_reminder_schedule_continuation(
                snapshot.envelope.text,
                getattr(self, "_current_turn_recent_messages", []),
            )
        ):
            return snapshot
        refined_intent = replace(
            snapshot.intent,
            primary="write",
            domain="reminder",
            operation="create",
            confidence=0.86,
            evidence=(*snapshot.intent.evidence, "continuation:reminder_schedule"),
            ambiguity=tuple(flag for flag in snapshot.intent.ambiguity if flag != "low_confidence"),
            is_write=True,
        )
        refined_goal = compile_goal_spec(
            envelope=snapshot.envelope,
            context=snapshot.context,
            intent=refined_intent,
            actionable_references=snapshot.actionable_references,
        )
        refined = replace(
            snapshot,
            intent=refined_intent,
            goal=refined_goal,
        )
        self._agent_kernel_snapshot = refined
        if self._agent_kernel_event_bus is not None:
            self._agent_kernel_event_bus.rebind_snapshot(
                refined,
                reason="reminder_schedule_continuation",
            )
        return refined

    def _finish_agent_kernel_turn(self, *, status: str) -> None:
        if self._agent_kernel_event_bus is None or self._agent_kernel_turn_finished:
            return
        self._agent_kernel_event_bus.turn_ended(status=status)
        self._agent_kernel_turn_finished = True

    def _agent_kernel_trace_summary(self, *, status: Optional[str] = None) -> dict[str, Any]:
        bus = self._agent_kernel_event_bus
        if bus is None:
            return {}
        return bus.trace_summary(status=status)

    def _agent_kernel_reference_now(self) -> datetime:
        snapshot = self._agent_kernel_snapshot
        return snapshot.context.current_time if snapshot is not None else datetime.now(BEIJING_TZ)

    def _agent_kernel_time_context(
        self,
        client_time_context: Optional[Dict[str, Any]],
    ) -> str:
        snapshot = self._ensure_agent_kernel_turn()
        return format_turn_time_context_prompt(
            snapshot.context,
            client_time_context=snapshot.envelope.client_time_context,
        )

    def _agent_kernel_record_tool_result(
        self,
        tool_name: str,
        args: Any,
        result: str,
    ) -> str:
        """Emit outcome metadata only; health payload stays out of telemetry."""
        bus = self._agent_kernel_event_bus
        if bus is None:
            return result
        parsed_args = args if isinstance(args, dict) else {}
        decision = self._agent_kernel_last_decision
        result_text = str(result or "").lstrip()
        snapshot = self._agent_kernel_snapshot
        policy_blocked = bool(
            decision is not None
            and decision.action == "block"
            and snapshot is not None
            and snapshot.policy_mode == "enforce"
        )
        receipt = None
        if decision is not None and decision.receipt_required:
            receipt = _write_receipt_from_tool_result(
                tool_name,
                parsed_args,
                result,
            )
        explicit_failure = (
            receipt is None and result_declares_explicit_failure(result)
        )
        if result_text.startswith("[NEEDS_CONFIRMATION]"):
            if tool_name not in self._agent_kernel_pending_confirmation_tools:
                self._agent_kernel_pending_confirmation_tools.append(tool_name)
        elif (
            result_text.startswith("Error:") or explicit_failure
        ) and not policy_blocked:
            if tool_name not in self._agent_kernel_tool_failure_tools:
                self._agent_kernel_tool_failure_tools.append(tool_name)
        elif not policy_blocked and tool_name in self._agent_kernel_tool_failure_tools:
            # 同一工具后续重试成功时，只保留未恢复的失败，避免把成功回合计入拒答率。
            self._agent_kernel_tool_failure_tools.remove(tool_name)
        write_outcome = (
            classify_write_execution(result, receipt=receipt)
            if decision is not None and decision.receipt_required
            else None
        )
        if (
            policy_blocked
            and snapshot is not None
            and not snapshot.intent.is_write
            and decision is not None
        ):
            self._force_no_tools_synthesis = True
            if (
                decision.reason
                not in self._agent_kernel_recovered_capability_block_reasons
            ):
                self._agent_kernel_recovered_capability_block_reasons.append(
                    decision.reason
                )
        bus.tool_result(
            tool_name=tool_name,
            success=(
                not policy_blocked
                and not result_text.startswith("Error:")
                and not explicit_failure
                and (
                    write_outcome is None
                    or write_outcome.status == "verified"
                )
            ),
            receipt=receipt,
        )
        return result

    def _display_model_name_for_id(self, model_id: Optional[str]) -> Optional[str]:
        if not model_id:
            return None
        try:
            from app.services.llm.model_registry import get_model

            entry = get_model(model_id)
            return entry.model if entry else model_id
        except Exception:  # noqa: BLE001
            return model_id

    def _record_model_fallback_reason(self, reason: str) -> None:
        if reason and reason not in self._model_fallback_reasons:
            self._model_fallback_reasons.append(reason)

    def _record_tool_model_name(self, model_name: Optional[str]) -> None:
        if model_name and model_name not in self._tool_model_names:
            self._tool_model_names.append(model_name)

    def _answer_max_tokens(self) -> int:
        """本回合答案生成的 max_tokens。fast-routed 简单回合收紧到
        FAST_ROUTE_ANSWER_MAX_TOKENS (简单答案的长尾解码是延迟的一部分);
        其它一切回合仍用 ANSWER_MAX_TOKENS。"""
        return (
            FAST_ROUTE_ANSWER_MAX_TOKENS
            if self._fast_route_simple_turn
            else ANSWER_MAX_TOKENS
        )

    @staticmethod
    def _should_replay_finalized_assistant(
        assistant: Any,
        source_message: Any = None,
    ) -> bool:
        """Replay only durable results; let retryable no-write failures run again.

        A finalized assistant row is normally the idempotency anchor.  But a
        model/policy failure with no write checkpoint is retryable: replaying it
        forever makes a client reconnect show the same stale error and prevents
        the user from recovering the turn.  Any write receipt or unresolved
        write checkpoint on either the assistant or source user message keeps
        the fail-closed replay behavior.
        """
        raw_assistant_meta = getattr(assistant, "meta", None)
        if not isinstance(raw_assistant_meta, dict):
            # Missing/malformed metadata cannot prove that an old finalized
            # turn was write-free. Replay the durable row instead of rerunning.
            return True
        assistant_meta = raw_assistant_meta
        if not assistant_meta:
            return True
        if source_message is None:
            return True
        is_partial = assistant_meta.get("client_turn_finalized") is False
        if not is_partial and assistant_meta.get("client_turn_finalized") is not True:
            # Non-empty legacy metadata without a finalization marker is not
            # evidence of a write-free failure; keep the durable replay path.
            return True
        raw_source_meta = getattr(source_message, "meta", None)
        if raw_source_meta is not None and not isinstance(raw_source_meta, dict):
            return True
        source_meta = raw_source_meta if isinstance(raw_source_meta, dict) else None

        def has_write_checkpoint_or_ambiguity(
            meta: dict[str, Any],
            *,
            allow_empty_receipts: bool = False,
        ) -> bool:
            """Treat all write metadata other than assistant's empty receipts as a barrier."""
            for key in meta:
                if not key.startswith("write_"):
                    continue
                if allow_empty_receipts and key == "write_receipts":
                    receipts = meta[key]
                    if isinstance(receipts, list) and not receipts:
                        continue
                return True
            return False

        # Current finalized assistant rows always carry an explicit list of
        # verified receipts. Missing or malformed data is legacy/ambiguous and
        # must remain fail-closed rather than being re-executed.
        if not is_partial and not isinstance(assistant_meta.get("write_receipts"), list):
            return True
        if has_write_checkpoint_or_ambiguity(
            assistant_meta,
            allow_empty_receipts=not is_partial,
        ):
            return True
        if source_meta is not None and has_write_checkpoint_or_ambiguity(source_meta):
            return True

        # An explicitly partial row is safe to take over only after both sides
        # have passed the write-metadata barrier above.
        if is_partial:
            return False

        outcome = assistant_meta.get("turn_outcome") or {}
        if isinstance(outcome, dict) and outcome:
            # A policy/tool failure can benefit from retrying the same durable
            # request.  ``action_not_executed`` is different: the model never
            # attempted a write, so the same request should remain replayable
            # until the client sends a new, clarified turn.
            if outcome.get("retryable") is True and outcome.get("category") in {
                "tool_blocked", "tool_failed", "execution_error", "no_answer",
            }:
                return False
            return True
        # Legacy rows without the explicit current-version no-write marker stay
        # on the durable replay path. A missing checkpoint is not proof that a
        # previous worker never reached an external write.
        return True

    async def _replay_client_turn(
        self,
        svc,
        user_id: int,
        user_message,
        client_turn_id: str,
    ) -> AsyncGenerator[Dict, None]:
        """Replay a claimed client turn without running its tools a second time."""
        yield {"event": "request_persisted", "data": {
            "conversation_id": user_message.conversation_id,
            "user_message_id": user_message.id,
            "client_turn_id": client_turn_id,
            "replayed": True,
        }}
        assistant = svc.find_assistant_message_by_client_turn(user_id, client_turn_id)
        if assistant is not None and not self._should_replay_finalized_assistant(
            assistant,
            user_message,
        ):
            assistant = None
        deadline = time.monotonic() + CLIENT_TURN_REPLAY_WAIT_SECONDS
        while assistant is None and time.monotonic() < deadline:
            yield self._status_event("accepted", detail="同一请求仍在处理中")
            await asyncio.sleep(0.25)
            self.db.expire_all()
            assistant = svc.find_assistant_message_by_client_turn(user_id, client_turn_id)
            if assistant is not None and not self._should_replay_finalized_assistant(
                assistant,
                user_message,
            ):
                assistant = None
        if assistant is None:
            yield {"event": "done", "data": {
                "conversation_id": user_message.conversation_id,
                "message_id": None,
                "completion_status": "interrupted",
                "client_turn_id": client_turn_id,
                "replayed": True,
            }}
            return
        from app.services.health_evidence.delivery import (
            project_persisted_health_messages,
        )

        replay_delivery = project_persisted_health_messages(
            (user_message, assistant)
        )[-1]
        replay_content = replay_delivery.content
        if replay_content:
            yield {"event": "token", "data": {"content": replay_content}}
        done_data = replay_delivery.meta
        done_data.update({
            "conversation_id": assistant.conversation_id,
            "message_id": assistant.id,
            "completion_status": done_data.get("completion_status") or "complete",
            "client_turn_id": client_turn_id,
            "replayed": True,
        })
        yield {"event": "done", "data": done_data}

    def _persist_turn_write_state(
        self,
        user_message,
        *,
        status: str,
        tool_name: str,
        parsed_args: Dict[str, Any],
        receipt: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Checkpoint a write boundary on the durable user turn.

        Only a fingerprint is stored, never raw health arguments. The in-flight
        checkpoint is committed before the external write is invoked, so a
        replacement worker can fail closed instead of repeating the write.
        """
        fingerprint = _write_operation_fingerprint(tool_name, parsed_args)
        meta = dict(user_message.meta or {})
        existing_receipts = [
            dict(item)
            for item in (meta.get("write_receipts") or [])
            if isinstance(item, dict)
        ]
        if receipt and not any(
            item.get("operation_id") == receipt.get("operation_id")
            for item in existing_receipts
        ):
            existing_receipts.append(dict(receipt))
        meta["write_state"] = {
            "status": status,
            "tool": tool_name,
            "fingerprint": fingerprint,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        operations = dict(meta.get("write_operations") or {})
        operation = dict(operations.get(fingerprint) or {})
        operation.update({
            "status": status,
            "tool": tool_name,
            "updated_at": meta["write_state"]["updated_at"],
        })
        if receipt:
            operation["receipt_operation_id"] = receipt.get("operation_id")
        operations[fingerprint] = operation
        meta["write_operations"] = operations
        meta["write_receipts"] = existing_receipts
        user_message.meta = meta
        try:
            self.db.commit()
            self.db.refresh(user_message)
        except Exception as error:
            self.db.rollback()
            raise RuntimeError("write_checkpoint_persistence_failed") from error

    def _persist_turn_expected_writes(
        self,
        user_message,
        expected_writes: List[tuple[str, Dict[str, Any]]],
    ) -> None:
        """Seal every write in one model response before dispatching any tool."""
        if not expected_writes:
            return
        meta = dict(user_message.meta or {})
        operations = dict(meta.get("write_operations") or {})
        write_plan = dict(meta.get("write_plan") or {})
        planned_fingerprints = {
            str(fingerprint)
            for fingerprint in (write_plan.get("fingerprints") or [])
            if fingerprint
        }
        updated_at = datetime.now(UTC).isoformat()
        for tool_name, parsed_args in expected_writes:
            fingerprint = _write_operation_fingerprint(tool_name, parsed_args)
            planned_fingerprints.add(fingerprint)
            if fingerprint not in operations:
                operations[fingerprint] = {
                    "status": "planned",
                    "tool": tool_name,
                    "updated_at": updated_at,
                }
        meta["write_operations"] = operations
        meta["write_plan"] = {
            "fingerprints": sorted(planned_fingerprints),
            "sealed": True,
            "updated_at": updated_at,
        }
        user_message.meta = meta
        try:
            self.db.commit()
            self.db.refresh(user_message)
        except Exception as error:
            self.db.rollback()
            raise RuntimeError("write_plan_persistence_failed") from error

    def _persist_current_turn_write_dispatch_started(
        self,
        *,
        tool_name: str,
        parsed_args: Dict[str, Any],
    ) -> None:
        """Persist in-flight only after policy approval and before dispatch.

        Direct surfaces without a durable Agent message still rely on the
        runtime operation ledger. Chat turns additionally checkpoint their
        source message so process recovery cannot repeat a side effect.
        """
        source_message_id = self._current_turn_source_message_id
        if source_message_id is None:
            return
        from app.models.agent_conversation import AgentConversation, AgentMessage

        query = (
            self.db.query(AgentMessage)
            .join(
                AgentConversation,
                AgentConversation.id == AgentMessage.conversation_id,
            )
            .filter(
                AgentMessage.id == int(source_message_id),
                AgentMessage.role == "user",
            )
        )
        if self._current_user_id is not None:
            query = query.filter(AgentConversation.user_id == self._current_user_id)
        user_message = query.one_or_none()
        if user_message is None:
            raise RuntimeError("write_source_message_not_found")
        self._persist_turn_write_state(
            user_message,
            status="in_flight",
            tool_name=tool_name,
            parsed_args=parsed_args,
        )

    async def _recover_client_turn_write_checkpoint(
        self,
        svc,
        user_id: int,
        user_message,
        client_turn_id: str,
    ) -> AsyncGenerator[Dict, None]:
        """Finalize an orphaned write turn without executing its tools again."""
        meta = dict(user_message.meta or {})
        write_state = dict(meta.get("write_state") or {})
        receipts = [
            dict(item)
            for item in (meta.get("write_receipts") or [])
            if isinstance(item, dict) and item.get("verified") is True
        ]
        raw_operations = meta.get("write_operations") or {}
        if not isinstance(raw_operations, dict):
            raw_operations = {}
        operations = {
            str(fingerprint): dict(operation)
            for fingerprint, operation in raw_operations.items()
            if isinstance(operation, dict)
        }
        write_plan = meta.get("write_plan") or {}
        if not isinstance(write_plan, dict):
            write_plan = {}
        planned_fingerprints = [
            str(fingerprint)
            for fingerprint in (write_plan.get("fingerprints") or [])
            if fingerprint
        ]
        receipt_ids = {
            str(item.get("operation_id"))
            for item in receipts
            if item.get("operation_id")
        }
        if write_plan.get("sealed") is True and planned_fingerprints:
            def operation_verified(fingerprint: str) -> bool:
                operation = operations.get(fingerprint) or {}
                return (
                    operation.get("status") == "verified"
                    and str(operation.get("receipt_operation_id") or "") in receipt_ids
                )

            fully_verified = all(operation_verified(fingerprint) for fingerprint in planned_fingerprints)
            all_resolved = all(
                fingerprint in operations
                and (
                    operation_verified(fingerprint)
                    or operations[fingerprint].get("status") in {"rejected", "failed"}
                )
                for fingerprint in planned_fingerprints
            )
            partially_verified = bool(receipts) or any(
                operation.get("status") == "verified"
                for operation in operations.values()
            )
        elif operations:
            # A legacy checkpoint has no durable proof of the complete write
            # set returned by the model. Even one verified operation may have
            # been followed by another write that crashed before checkpoint.
            fully_verified = False
            partially_verified = bool(receipts) or any(
                operation.get("status") == "verified"
                for operation in operations.values()
            )
        else:
            fully_verified = False
            partially_verified = bool(receipts) or write_state.get("status") == "verified"
        if fully_verified:
            content = "写入已完成，已从持久化回执恢复本轮结果，没有重复执行写入。"
            completion_status = "complete"
            recovery_reason = "write_checkpoint_verified"
        elif write_plan.get("sealed") is True and planned_fingerprints and all_resolved:
            rejected_count = sum(
                1
                for fingerprint in planned_fingerprints
                if operations.get(fingerprint, {}).get("status") in {"rejected", "failed"}
            )
            verified_part = (
                f"已确认 {len(receipts)} 项写入不会重复执行。"
                if receipts
                else "本轮没有写入项获得回执。"
            )
            content = (
                f"写入状态已恢复：{verified_part}"
                f"另有 {rejected_count} 项因参数校验或需要确认而未执行，结果不是未知状态。"
                "请补充信息或确认后再提交。"
            )
            completion_status = "error"
            recovery_reason = "write_checkpoint_rejected"
        elif partially_verified:
            content = (
                "本轮已有部分写入获得回执，但中断时另一次写入状态未知。"
                "为避免重复写入，我没有自动重试；请先查询现有记录后再决定是否补录。"
            )
            completion_status = "error"
            recovery_reason = "write_checkpoint_partially_verified"
        else:
            content = (
                "上一次处理在写入过程中中断，结果状态未知。为避免重复写入，"
                "我没有自动重试；请先查询现有记录，确认后再补录。"
            )
            completion_status = "error"
            recovery_reason = "write_checkpoint_uncertain"

        assistant_meta = {
            "mode": "agent",
            "completion_status": completion_status,
            "write_receipts": receipts,
            "write_recovery": recovery_reason,
            "client_turn_finalized": True,
            "client_turn_id": client_turn_id,
        }
        assistant = svc.save_message(
            user_message.conversation_id,
            "assistant",
            content,
            meta=assistant_meta,
            client_turn_id=client_turn_id,
            client_turn_user_id=user_id,
        )
        yield {"event": "request_persisted", "data": {
            "conversation_id": user_message.conversation_id,
            "user_message_id": user_message.id,
            "client_turn_id": client_turn_id,
            "recovered": True,
        }}
        yield {"event": "token", "data": {"content": content}}
        yield {"event": "done", "data": {
            **assistant_meta,
            "conversation_id": assistant.conversation_id,
            "message_id": assistant.id,
        }}

    def _resolved_answer_model_is_non_streaming(self) -> bool:
        """本回合答案是否由一个**结构性非流式**模型生成 (整段一次返回, ttft≈total)。

        解析口径与 _resolve_chat_provider 一致: 优先 _request_model_id (mac/桌面显式选/
        fast-route 填充), 否则用户画像/admin 全局默认模型 (_user_effective_model_id)。
        命中注册表 entry 且 supports_streaming=False 才返回 True。

        **fail-soft, 任何不确定都返回 False (不发提示, mac 走正常 token 滚动)**:
        解析不出 model_id、未注册、读库异常 —— 一律当作可流式, 宁可少提示也不误导。
        """
        try:
            from app.services.llm.model_registry import get_model

            model_id = self._request_model_id or self._user_effective_model_id()
            if not model_id:
                return False
            entry = get_model(model_id)
            if entry is None:
                return False
            return not entry.supports_streaming
        except Exception:  # noqa: BLE001 — 观测性提示绝不能断主链路
            return False

    @staticmethod
    def _status_event(
        stage: str,
        *,
        detail: Optional[str] = None,
        round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """构造真实思考过程 status SSE 事件 (mac 端据此显示"正在……",替代按时长猜)。

        契约 (mac client 精确对齐):
            {"event": "status", "data": {"stage": <str>, "detail": <str|None>, "round": <int|None>}}

        纯埋点、纯附加: 未知 event 客户端会 tolerate。调用点须 fail-soft 包裹
        (镜像 perf_pre_llm), 任何构造/emit 异常绝不断主链路。
        """
        return {"event": "status", "data": {"stage": stage, "detail": detail, "round": round}}

    @staticmethod
    def _progress_event(
        stage: str,
        *,
        round: Optional[int] = None,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构造 P0-1 流式进度事件 (flat 契约, 与既有 _status_event 独立、纯附加)。

        契约 (两端一字不差):
            {"type":"status","stage":"accepted"}                    — 流一打开立刻发
            {"type":"status","stage":"tool","round":N,"label":"…"}  — 每轮工具执行前发
            {"type":"status","stage":"synthesis"}                   — 最终答案开始生成前发

        故意 flat (顶层 type/stage/label, 无 data 包裹): 与既有 {"event":"status",
        "data":{...}} 家族区分, 客户端可只订阅其一。round/label 仅 tool 阶段带。
        纯附加、fail-soft: 未知事件四端消费者都 tolerate (mobile chat.ts 落 undefined /
        frontend evt.event??evt.type 落 status 分支 / mac default→nil)。
        """
        evt: Dict[str, Any] = {"type": "status", "stage": stage}
        if round is not None:
            evt["round"] = round
        if label is not None:
            evt["label"] = label
        return evt

    async def _run_multi_model_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int],
        user_auth_token: Optional[str],
        extra_context: Optional[str],
        client_turn_id: Optional[str] = None,
        recovered_user_message: Any = None,
        client_time_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """多模型综合分析 (商用三强 panel)。

        lead (Claude Opus 4.7) 跑一遍带工具的完整回合 —— 查询/记录只执行一次,
        不会被 panel 重复写库; GPT-5.5 + Gemini 3.1 Pro 在 lead 取到的同一份数据
        上下文上各自独立分析 (并发, 不带工具); 最后由 Claude Opus 4.7 综合成一份
        「共识 / 各家补充 / 分歧」报告。单次保存一条 assistant 消息 (综合结果)。
        """
        import asyncio as _asyncio
        from app.services.llm.usage_tracker import set_caller
        from app.services.llm.factory import create_provider_for_model_id

        set_caller("agent_executor.multi_model", user_id=user_id)
        # A model panel has no confirmation-card terminal contract. Mark this
        # path so a lead-model medication call cannot commit a hidden plan.
        self._multi_model_turn = True
        start_time = time.time()
        # 该路径的准入门是 `not images and not file_base64`(见 run_stream 调用点),故本回合
        # 恒无图片;request_persisted 事件已不再引用 saved_image_urls(消费引用已被移除),
        # 故此前 Wave 2 顺手加的 `saved_image_urls = []` 兜底已成 dead code,一并清掉。
        self._current_user_id = user_id
        self._prefer_fast_record_model = False
        self._last_provider_model_name = None
        self._model_fallback_reasons = []
        self._tool_model_names = []
        self._dead_provider_model_ids = set()
        self._tool_dead_provider_model_ids = set()
        self._last_effective_model_id = None
        self._current_turn_user_message = message or ""
        self._ensure_agent_kernel_turn()
        sources_used: list = ["多模型综合 (Claude Opus 4.7 · GPT-5.5 · Gemini 3.1 Pro)"]
        write_receipts: list[Dict[str, Any]] = []
        write_results_by_fingerprint: dict[str, str] = {}
        model_label = "Claude Opus 4.7 + GPT-5.5 + Gemini 3.1 Pro (综合)"

        from app.services.agent_conversation_service import AgentConversationService
        svc = AgentConversationService(self.db)
        if recovered_user_message is not None:
            conv = svc.get_or_create_conversation(
                user_id,
                recovered_user_message.conversation_id,
                title=message,
            )
            user_msg = recovered_user_message
        else:
            conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)
            user_msg, _ = svc.save_user_message_once(
                conv.id,
                user_id,
                message,
                client_turn_id=client_turn_id,
                meta={"client_turn_id": client_turn_id} if client_turn_id else None,
            )

        yield {"event": "request_persisted", "data": {
            "conversation_id": conv.id,
            "user_message_id": user_msg.id,
            "client_turn_id": client_turn_id,
            "recovered": recovered_user_message is not None,
        }}
        self._current_turn_source_message_id = int(user_msg.id)
        self._current_turn_conversation_id = int(conv.id)
        self._current_turn_image_urls = []
        self._bind_agent_kernel_source_message(user_msg.id)
        try:
            self._bind_agent_kernel_actionable_references(
                svc.build_actionable_references(conv.id)
            )
        except Exception as exc:  # noqa: BLE001 - context loss must not abort the turn
            logger.warning(
                "[agent_executor] multi-model actionable context projection failed "
                "conversation=%s error=%s",
                conv.id,
                exc,
            )

        yield {"event": "agent_start", "data": {"message": "多模型综合分析中…", "conversation_id": conv.id}}

        system_content = self._build_system_prompt(user_id, conv.id, user_auth_token)
        turn_time_context = self._agent_kernel_time_context(client_time_context)
        multi_model_context = [
            turn_time_context,
            format_actionable_context_prompt(
                self._agent_kernel_snapshot.actionable_references
                if self._agent_kernel_snapshot is not None else ()
            ),
            format_goal_contract_prompt(
                self._agent_kernel_snapshot.goal
                if self._agent_kernel_snapshot is not None else None
            ),
        ]
        multi_model_context_text = "\n\n".join(
            part for part in multi_model_context if part
        )
        message_with_time_context = (
            "[系统附注 — 本回合参考上下文,非用户输入]\n"
            f"{multi_model_context_text}\n"
            f"[用户消息]\n{message}"
        )
        tools = get_health_tools()
        full_reply = ""
        completion_status = "complete"

        def _progress(tool: str, text: str) -> Dict:
            return {"event": "tool_result", "data": {"tool": tool, "success": True, "preview": text, "result": text}}

        self._http_client = httpx.AsyncClient(timeout=90.0)
        try:
            # 1) Lead 回合 (带工具, Claude Opus 4.7)
            yield _progress("多模型·主分析", "Claude Opus 4.7 正在查数据/记录并分析…")
            self._request_model_id = MULTI_MODEL_LEAD_ID
            lead_messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": message_with_time_context},
            ]
            lead_text = ""
            pending_recoverable_write_rejections: dict[
                str, tuple[str, str]
            ] = {}
            pending_recoverable_write_rejection_rounds: dict[str, int] = {}
            pending_recoverable_write_rejection_scopes: dict[str, str] = {}
            last_recoverable_write_rejection: Optional[str] = None
            last_recoverable_write_rejection_code: Optional[str] = None
            deterministic_diet_correction_fallback_attempted = False
            deterministic_simple_record_fallback_attempted = False
            deterministic_goal_lookup_attempted = False
            goal_verification_attempted = False
            receipt_goal_evaluated = False
            goal_verification_result: Any = None
            goal_lookup_completed = False
            goal_allowed_record_ids: set[str] = set()
            lead_force_no_tools_synthesis = False
            for _round in range(MULTI_MODEL_MAX_LEAD_ROUNDS):
                resp = await self._call_llm(
                    lead_messages,
                    [] if lead_force_no_tools_synthesis else tools,
                )
                tool_calls = resp.get("tool_calls") if isinstance(resp, dict) else None
                content = ((resp.get("content") if isinstance(resp, dict) else str(resp)) or "")
                if not tool_calls:
                    recovered = _extract_inline_tool_call(
                        content,
                        tools,
                        user_message=message,
                    )
                    if recovered:
                        tool_calls = [recovered]
                        content = ""
                # 文本式工具调用(Tool calls:\n- xxx)无参数可解析 → 重提示结构化重试。
                if not tool_calls and _is_botched_text_tool_call(content, tools):
                    if _round < MULTI_MODEL_MAX_LEAD_ROUNDS - 1:
                        logger.warning(
                            "[agent_executor] 文本式工具调用(多模型路), 重提示重试. chars=%s",
                            len(content),
                        )
                        lead_messages.append({"role": "assistant", "content": content})
                        lead_messages.append({"role": "user", "content": (
                            "你刚才把工具调用写成了文本(例如 \"Tool calls:\\n- health_query\"),"
                            "并没有真正调用工具。请立刻用结构化 function calling 真正调用所需工具并带正确参数"
                            "(例如查看补剂库用 health_query 且 dimension=\"supplements\")。"
                        )})
                        continue
                    content = _strip_text_tool_call(content)
                if (
                    not tool_calls
                    and not deterministic_simple_record_fallback_attempted
                ):
                    deterministic_simple_record_call = (
                        _build_deterministic_simple_record_tool_call(
                            (
                                self._agent_kernel_snapshot.goal
                                if self._agent_kernel_snapshot is not None else None
                            ),
                            write_receipts=write_receipts,
                        )
                    )
                    if deterministic_simple_record_call:
                        deterministic_simple_record_fallback_attempted = True
                        tool_calls = [deterministic_simple_record_call]
                        content = ""
                        logger.info(
                            "[agent_executor] deterministic simple record fallback "
                            "user=%s record_type=%s",
                            user_id,
                            (
                                self._agent_kernel_snapshot.goal.target_record_type
                                if self._agent_kernel_snapshot is not None
                                and self._agent_kernel_snapshot.goal is not None
                                else "unknown"
                            ),
                        )
                if (
                    not tool_calls
                    and not deterministic_goal_lookup_attempted
                ):
                    deterministic_goal_call = _build_deterministic_goal_lookup_tool_call(
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        write_receipts=write_receipts,
                    )
                    if deterministic_goal_call:
                        deterministic_goal_lookup_attempted = True
                        tool_calls = [deterministic_goal_call]
                        content = ""
                if not tool_calls:
                    verification_call = _build_goal_verification_tool_call(
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        write_receipts=write_receipts,
                        already_attempted=goal_verification_attempted,
                    )
                    if verification_call:
                        goal_verification_attempted = True
                        tool_calls = [verification_call]
                        content = ""
                if (
                    not tool_calls
                    and not deterministic_diet_correction_fallback_attempted
                ):
                    deterministic_diet_call = (
                        _build_deterministic_diet_correction_tool_call(
                            message,
                            write_receipts=write_receipts,
                            reference_now=self._agent_kernel_reference_now(),
                        )
                    )
                    if deterministic_diet_call:
                        deterministic_diet_correction_fallback_attempted = True
                        tool_calls = [deterministic_diet_call]
                        content = ""
                        logger.info(
                            "[agent_executor] deterministic diet correction fallback "
                            "user=%s message_chars=%s",
                            user_id,
                            len(message or ""),
                        )
                if (
                    not tool_calls
                    and goal_verification_attempted
                    and goal_verification_result is not None
                ):
                    postcondition = verify_goal_postconditions(
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        write_receipts=write_receipts,
                        verification_result=goal_verification_result,
                    )
                    if self._agent_kernel_event_bus is not None:
                        self._agent_kernel_event_bus.goal_evaluated(
                            satisfied=postcondition.satisfied,
                            verified_target_count=len(
                                postcondition.verified_resource_ids
                            ),
                            reason=postcondition.reason,
                        )
                    if not postcondition.satisfied:
                        content = (
                            "更新操作已执行，但读回核验未覆盖全部目标餐次，"
                            "因此本轮不能确认已经全部完成。请重试，系统会继续核对现有记录。"
                        )
                goal = (
                    self._agent_kernel_snapshot.goal
                    if self._agent_kernel_snapshot is not None else None
                )
                if (
                    not tool_calls
                    and not receipt_goal_evaluated
                    and deterministic_simple_record_fallback_attempted
                    and goal is not None
                    and goal.kind == "simple_health_record"
                ):
                    receipt_goal_evaluated = True
                    postcondition = verify_goal_postconditions(
                        goal,
                        write_receipts=write_receipts,
                        verification_result=None,
                    )
                    if self._agent_kernel_event_bus is not None:
                        self._agent_kernel_event_bus.goal_evaluated(
                            satisfied=postcondition.satisfied,
                            verified_target_count=len(
                                postcondition.verified_resource_ids
                            ),
                            reason=postcondition.reason,
                        )
                    terminal_completed = postcondition.satisfied
                    if postcondition.satisfied:
                        terminal_text = _simple_record_goal_completion_text(goal)
                    elif last_recoverable_write_rejection:
                        rejection_is_terminal = bool(
                            last_recoverable_write_rejection_code
                            == "diet_nutrition_incomplete"
                            or _claims_unverified_write_success(content)
                            or not content.strip()
                        )
                        if rejection_is_terminal:
                            terminal_text = _write_rejection_with_receipt_context(
                                last_recoverable_write_rejection,
                                write_receipts,
                            )
                        else:
                            terminal_text = _write_rejection_with_receipt_context(
                                content,
                                write_receipts,
                            )
                            terminal_completed = True
                    else:
                        terminal_text = (
                            "记录请求已执行，但没有取得与目标类型一致的可验证回执，"
                            "因此本轮不能确认已经完成。请重试。"
                        )
                    raise _SimpleRecordTerminal(
                        terminal_text,
                        satisfied=terminal_completed,
                    )
                if tool_calls:
                    proposed_tool_calls = list(tool_calls)
                    tool_calls = self._normalize_query_only_health_manage_tool_calls(
                        tool_calls,
                    )
                    tool_calls = await self._normalize_latest_diet_delete_tool_calls(
                        tool_calls,
                        user_auth_token,
                    )
                    tool_calls = await self._normalize_explicit_diet_update_tool_calls(
                        tool_calls,
                        user_auth_token,
                    )
                    tool_calls = _normalize_goal_guarded_tool_calls(
                        tool_calls,
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        lookup_completed=goal_lookup_completed,
                        allowed_record_ids=goal_allowed_record_ids,
                    )
                    rejected_goal_writes = _goal_guard_rejected_writes(
                        proposed_tool_calls,
                        tool_calls,
                    )
                    for rejected_tool_name, rejected_args in rejected_goal_writes:
                        self._persist_turn_write_state(
                            user_msg,
                            status="rejected",
                            tool_name=rejected_tool_name,
                            parsed_args=rejected_args,
                        )
                    if proposed_tool_calls and not tool_calls:
                        logger.warning(
                            "[agent_executor] all multi-model lead tool calls were "
                            "blocked by the goal contract; recovering with a "
                            "text-only lead answer user=%s rejected_writes=%s",
                            user_id,
                            len(rejected_goal_writes),
                        )
                        if content.strip():
                            lead_messages.append({
                                "role": "assistant",
                                "content": content,
                            })
                        lead_messages.append({
                            "role": "user",
                            "content": _GOAL_GUARD_RECOVERY_PROMPT,
                        })
                        lead_force_no_tools_synthesis = True
                        continue
                    self._prepare_medication_tool_plan(tool_calls)
                    planned_writes: List[tuple[str, Dict[str, Any]]] = []
                    for tc in tool_calls:
                        fn = tc["function"]["name"]
                        fa = tc["function"]["arguments"]
                        try:
                            parsed_args = (
                                json.loads(fa)
                                if isinstance(fa, str)
                                else dict(fa or {})
                            )
                        except (json.JSONDecodeError, TypeError, ValueError):
                            parsed_args = {}
                        if (
                            fn in _WRITE_RECEIPT_TOOL_NAMES
                            and _write_tool_attempted(fn, parsed_args)
                        ):
                            planned_writes.append((fn, parsed_args))
                    self._persist_turn_expected_writes(user_msg, planned_writes)
                    lead_messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        fn = tc["function"]["name"]
                        fa = tc["function"]["arguments"]
                        try:
                            parsed_args = json.loads(fa) if isinstance(fa, str) else dict(fa or {})
                        except (json.JSONDecodeError, TypeError, ValueError):
                            parsed_args = {}
                        write_attempted = (
                            fn in _WRITE_RECEIPT_TOOL_NAMES
                            and _write_tool_attempted(fn, parsed_args)
                        )
                        write_fingerprint = (
                            _write_operation_fingerprint(fn, parsed_args)
                            if write_attempted else None
                        )
                        recoverable_write_key = (
                            _recoverable_write_operation_key(
                                fn,
                                parsed_args,
                                default_record_date=(
                                    self._agent_kernel_reference_now()
                                    .date()
                                    .isoformat()
                                ),
                            )
                            if write_attempted else None
                        )
                        replayed_write = bool(
                            write_fingerprint
                            and write_fingerprint in write_results_by_fingerprint
                        )
                        if replayed_write:
                            result = write_results_by_fingerprint[write_fingerprint]
                        else:
                            # Wave 2: 心跳 + per-tool 超时(同主路径)。
                            result = None
                            async for _hb_kind, _hb_val in self._run_tool_with_progress(
                                fn, fa, user_auth_token, _tool_progress_label(fn),
                            ):
                                if _hb_kind == "heartbeat":
                                    yield _hb_val
                                else:
                                    result = _hb_val
                            if write_fingerprint:
                                write_results_by_fingerprint[write_fingerprint] = result
                        if (
                            fn == "health_manage"
                            and parsed_args.get("record_type") == "diet"
                            and parsed_args.get("operation") == "list"
                            and not str(result or "").startswith("Error")
                        ):
                            goal_lookup_completed = True
                            goal_allowed_record_ids = _goal_target_record_ids(
                                (
                                    self._agent_kernel_snapshot.goal
                                    if self._agent_kernel_snapshot is not None else None
                                ),
                                result,
                            )
                            if str(tc.get("id") or "").startswith("goal-verify-"):
                                goal_verification_result = result
                        tool_content = _model_tool_result_content(
                            fn,
                            parsed_args,
                            result,
                            reference_now=self._agent_kernel_reference_now(),
                            timezone_label=self._ensure_agent_kernel_turn().context.timezone,
                        )
                        if (
                            fn == "health_manage"
                            and parsed_args.get("record_type") == "diet"
                            and parsed_args.get("operation") == "list"
                        ):
                            tool_content += _goal_lookup_resolution_prompt(
                                (
                                    self._agent_kernel_snapshot.goal
                                    if self._agent_kernel_snapshot is not None else None
                                ),
                                result,
                            )
                        lead_messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": tool_content,
                        })
                        lbl = _TOOL_TO_SOURCE_LABEL.get(fn)
                        if lbl and lbl not in sources_used:
                            sources_used.append(lbl)
                        tool_event_data = {
                            "tool": fn,
                            "success": not result.startswith("Error"),
                            "preview": result[:200],
                            "result": result,
                        }
                        if replayed_write:
                            tool_event_data["replayed"] = True
                        if fn in _WRITE_RECEIPT_TOOL_NAMES:
                            write_completed = _write_tool_completed(fn, parsed_args, result)
                            tool_event_data["write_attempted"] = write_attempted
                            tool_event_data["write_completed"] = write_completed
                            if write_attempted and not write_completed:
                                tool_event_data["success"] = False
                            if write_completed:
                                receipt = _write_receipt_from_tool_result(
                                    fn,
                                    parsed_args,
                                    result,
                                )
                                if receipt:
                                    tool_event_data["receipt"] = receipt
                                    if not any(
                                        item.get("operation_id") == receipt.get("operation_id")
                                        for item in write_receipts
                                    ):
                                        write_receipts.append(receipt)
                            else:
                                receipt = None
                            tool_event_data.update(
                                _write_outcome_event_fields(result, receipt)
                            )
                            if write_attempted and not replayed_write:
                                checkpoint_status = _write_checkpoint_status_after_dispatch(
                                    result,
                                    receipt,
                                )
                                self._persist_turn_write_state(
                                    user_msg,
                                    status=checkpoint_status,
                                    tool_name=fn,
                                    parsed_args=parsed_args,
                                    receipt=receipt,
                                )
                        transient_local_rejection = bool(
                            write_attempted
                            and _write_result_is_pre_dispatch_validation_error(result)
                        )
                        if transient_local_rejection:
                            assert recoverable_write_key is not None
                            pending_recoverable_write_rejections.pop(
                                recoverable_write_key,
                                None,
                            )
                            pending_recoverable_write_rejections[
                                recoverable_write_key
                            ] = (
                                _pre_dispatch_validation_user_message(result),
                                classify_write_execution(result).error_code,
                            )
                            pending_recoverable_write_rejection_rounds[
                                recoverable_write_key
                            ] = _round
                            pending_recoverable_write_rejection_scopes[
                                recoverable_write_key
                            ] = _recoverable_write_scope_key(
                                fn,
                                parsed_args,
                            )
                        elif write_attempted and write_completed:
                            assert recoverable_write_key is not None
                            recoverable_scope_key = (
                                _recoverable_write_scope_key(fn, parsed_args)
                            )
                            _clear_repaired_write_rejections(
                                pending_recoverable_write_rejections,
                                pending_recoverable_write_rejection_rounds,
                                pending_recoverable_write_rejection_scopes,
                                operation_key=recoverable_write_key,
                                scope_key=recoverable_scope_key,
                                current_round=_round,
                                allow_scope_repair=(
                                    _goal_binds_recoverable_write(
                                        (
                                            self._agent_kernel_snapshot.goal
                                            if self._agent_kernel_snapshot
                                            is not None
                                            else None
                                        ),
                                        fn,
                                        parsed_args,
                                    )
                                ),
                            )
                        (
                            last_recoverable_write_rejection,
                            last_recoverable_write_rejection_code,
                        ) = _summarize_recoverable_write_rejections(
                            pending_recoverable_write_rejections
                        )
                        if not transient_local_rejection:
                            yield {"event": "tool_result", "data": tool_event_data}
                        if (
                            write_attempted
                            and checkpoint_status == "uncertain"
                        ):
                            raise _UnverifiedWriteResult()
                    continue
                # 兜底:内联标记(括号 / XML `<invoke>`)未恢复成 tool_call(name 不在白名单等)时,
                # 绝不能把裸工具语法当 lead 分析落进 final_text / 喂给下游多方分析。cheap-precheck no-op。
                content = _strip_bracket_tool_markers(content)
                content = _strip_xml_tool_markers(content)
                lead_text = content
                break

            if last_recoverable_write_rejection:
                rejection_is_terminal = bool(
                    last_recoverable_write_rejection_code
                    == "diet_nutrition_incomplete"
                    or _claims_unverified_write_success(lead_text)
                    or not lead_text.strip()
                )
                terminal_text = (
                    _write_rejection_with_receipt_context(
                        last_recoverable_write_rejection,
                        write_receipts,
                    )
                    if rejection_is_terminal
                    else _write_rejection_with_receipt_context(
                        lead_text,
                        write_receipts,
                    )
                )
                raise _SimpleRecordTerminal(
                    terminal_text,
                    satisfied=not rejection_is_terminal,
                )

            data_ctx = _gathered_data_context(lead_messages)

            # 2) 两路独立分析 (GPT-5.5 + Gemini, 并发, 不带工具)
            yield _progress("多模型·多方", "GPT-5.5、Gemini 3.1 Pro 正在各自分析…")
            persp_system = (
                "你是资深健康分析师。基于给定的用户健康数据，独立、简洁地分析用户的问题"
                "（300-600 字）。只用给定数据，不要编造；没有数据时给出审慎的一般性建议。"
            )
            persp_user = (
                f"{turn_time_context}\n\n用户问题：{message}\n\n已查到的用户健康数据：\n"
                f"{data_ctx or '（本次未取到额外数据）'}\n\n请给出你的独立分析。"
            )
            persp_messages = [
                {"role": "system", "content": persp_system},
                {"role": "user", "content": persp_user},
            ]

            async def _perspective(model_id: str) -> str:
                try:
                    p = create_provider_for_model_id(model_id)
                    r = await p.chat(messages=persp_messages, model=None, temperature=0.4,
                                     max_tokens=4000, stream=False, return_metadata=True)
                    return (r.get("content") if isinstance(r, dict) else str(r)) or ""
                except Exception as e:  # noqa: BLE001
                    logger.warning("[multi_model] perspective %s failed: %s", model_id, e)
                    return ""

            gpt_text, gemini_text = await _asyncio.gather(
                _perspective("gpt-5.5"), _perspective("gemini-3.1-pro")
            )

            # 3) 综合 (Claude Opus 4.7)
            yield _progress("多模型·综合", "综合三方观点…")
            analyses = [("Claude Opus 4.7", lead_text), ("GPT-5.5", gpt_text), ("Gemini 3.1 Pro", gemini_text)]
            synth_messages = [
                {"role": "system", "content": "你是健康分析综合专家，把多个模型的分析整合成一份清晰、专业、可执行的中文报告。"},
                {"role": "user", "content": _build_multi_model_synthesis_prompt(message, analyses)},
            ]
            try:
                synth_provider = create_provider_for_model_id(MULTI_MODEL_SYNTH_ID)
                synth_resp = await synth_provider.chat(messages=synth_messages, model=None, temperature=0.3,
                                                       max_tokens=ANSWER_MAX_TOKENS, stream=False, return_metadata=True)
                final_text = (synth_resp.get("content") if isinstance(synth_resp, dict) else str(synth_resp)) or ""
            except Exception as e:  # noqa: BLE001
                logger.error("[multi_model] synthesis failed: %s", e)
                completion_status = "error"
                final_text = lead_text or "多模型综合分析未能生成最终结论，请重试或改用单模型。"

            if not final_text.strip():
                final_text = lead_text or "多模型综合分析未能生成最终结论，请重试。"
            final_text = _ground_query_response_date_labels(
                final_text,
                message,
                reference_now=self._agent_kernel_reference_now(),
            )
            for i in range(0, len(final_text), 24):
                yield {"event": "token", "data": {"content": final_text[i:i + 24]}}
            full_reply = final_text
        except _SimpleRecordTerminal as terminal:
            completion_status = "complete" if terminal.satisfied else "error"
            full_reply = terminal.message
            for i in range(0, len(full_reply), 24):
                yield {
                    "event": "token",
                    "data": {"content": full_reply[i:i + 24]},
                }
        except _UnverifiedWriteResult:
            completion_status = "error"
            full_reply = _UNVERIFIED_WRITE_USER_MESSAGE
            for i in range(0, len(full_reply), 24):
                yield {"event": "token", "data": {"content": full_reply[i:i + 24]}}
        except Exception as e:  # noqa: BLE001
            logger.error(
                "多模型综合执行异常 user=%s error_type=%s",
                user_id,
                type(e).__name__,
            )
            completion_status = "error"
            full_reply = "多模型综合分析遇到问题，请稍后重试。"
            yield {"event": "token", "data": {"content": full_reply}}
        finally:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

        # 确定性护栏 (R4): 多模型综合是 LLM 生成文本 → 剥掉任何伪造的 reva-ui block。
        full_reply = _strip_reva_ui_from_llm_text(full_reply)
        full_reply = _strip_botched_text_tool_leak(full_reply)
        full_reply = _strip_scope_refusal_preamble(full_reply)
        full_reply = _ground_query_response_date_labels(
            full_reply,
            message,
            reference_now=self._agent_kernel_reference_now(),
        )
        ai_msg = svc.save_message(
            conv.id,
            "assistant",
            full_reply,
            client_turn_id=client_turn_id,
            client_turn_user_id=user_id,
        )
        conv.updated_at = datetime.now(UTC)
        elapsed_ms = int((time.time() - start_time) * 1000)
        # P1 数字锚定核验(shadow, additive; fail-soft 见 helper)。
        citation_anchor = _citation_anchor_shadow_meta(
            self.db,
            user_id,
            full_reply,
        )
        kernel_trace = self._agent_kernel_trace_summary(status=completion_status)
        try:
            ai_msg.meta = {
                "elapsed_ms": elapsed_ms,
                "model": model_label,
                "selected_model": model_label,
                "answer_model": model_label,
                "tool_models": [],
                "fallback_reasons": [],
                "sources_used": sources_used,
                "mode": "multi_model",
                **({"citation_anchor": citation_anchor} if citation_anchor else {}),
                **({"kernel_trace": kernel_trace} if kernel_trace else {}),
                "write_receipts": write_receipts,
                "completion_status": completion_status,
                "client_turn_finalized": True,
                **({"client_turn_id": client_turn_id} if client_turn_id else {}),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[multi_model] write meta 失败 user=%s error_type=%s",
                user_id,
                type(e).__name__,
            )
        self.db.commit()

        yield {"event": "done", "data": {
            "conversation_id": conv.id,
            "message_id": ai_msg.id,
            "elapsed_ms": elapsed_ms,
            "model": model_label,
            "selected_model": model_label,
            "answer_model": model_label,
            "tool_models": [],
            "fallback_reasons": [],
            "sources_used": sources_used,
            "mode": "multi_model",
            **({"citation_anchor": citation_anchor} if citation_anchor else {}),
            **({"kernel_trace": kernel_trace} if kernel_trace else {}),
            "write_receipts": write_receipts,
            "completion_status": completion_status,
            "client_turn_finalized": True,
            **({"client_turn_id": client_turn_id} if client_turn_id else {}),
        }}

    async def run_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        user_auth_token: Optional[str] = None,
        images: Optional[List[dict]] = None,
        file_base64: Optional[str] = None,
        file_name: Optional[str] = None,
        extra_context: Optional[str] = None,
        channel: Optional[str] = None,
        client_turn_id: Optional[str] = None,
        client_caps: Optional[List[str]] = None,
        client_time_context: Optional[Dict[str, Any]] = None,
        read_only_tools: bool = False,
        run_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        runtime_managed: bool = False,
        runtime_write_block_reason: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """Run one durable client turn, taking over an ACKed turn after worker loss.

        read_only_tools: starter answer pre-generation (rank7). When True, write
        tools are refused at the dispatch choke (fail-closed) — the pregen turn
        runs the same synthesis pipeline but can never mutate user data.
        """
        self._runtime_run_id = run_id
        self._runtime_attempt_id = attempt_id
        self._runtime_managed = bool(runtime_managed)
        self._runtime_write_block_reason = runtime_write_block_reason
        yield self._progress_event("accepted")
        self._current_user_id = user_id
        self._current_turn_user_message = message or ""
        self._current_turn_recent_messages = []
        self._current_turn_has_attachment = bool(images or file_base64)
        self._turn_pending_write_intent_ids = []
        self._turn_pending_write_intent_kinds = []
        self._turn_medication_tool_intent_id = None
        self._turn_medication_tool_preflight_error = None
        self._turn_medication_tool_confirmation_card = None
        self._multi_model_turn = False
        kernel_completion_status = "interrupted"
        recovered_user_message = None
        claimed_turn = False
        turn_service = None

        if client_turn_id:
            from app.services.agent_conversation_service import AgentConversationService

            turn_service = AgentConversationService(self.db)
            existing_turn = turn_service.find_user_message_by_client_turn(user_id, client_turn_id)
            assistant = turn_service.find_assistant_message_by_client_turn(user_id, client_turn_id)
            if (
                existing_turn is not None
                and assistant is not None
                and self._should_replay_finalized_assistant(assistant, existing_turn)
            ):
                async for replay_event in self._replay_client_turn(
                    turn_service, user_id, existing_turn, client_turn_id,
                ):
                    yield self._attach_runtime_identity(replay_event)
                self._finish_agent_kernel_turn(status="replayed")
                return

            claimed_turn = turn_service.try_acquire_client_turn_execution(
                user_id,
                client_turn_id,
            )
            if not claimed_turn:
                deadline = time.monotonic() + CLIENT_TURN_REPLAY_WAIT_SECONDS
                while not claimed_turn and time.monotonic() < deadline:
                    self.db.expire_all()
                    existing_turn = turn_service.find_user_message_by_client_turn(
                        user_id,
                        client_turn_id,
                    )
                    if existing_turn is not None:
                        break
                    claimed_turn = turn_service.try_acquire_client_turn_execution(
                        user_id,
                        client_turn_id,
                    )
                    if claimed_turn:
                        break
                    await asyncio.sleep(0.05)
                if existing_turn is not None:
                    async for replay_event in self._replay_client_turn(
                        turn_service, user_id, existing_turn, client_turn_id,
                    ):
                        yield self._attach_runtime_identity(replay_event)
                    self._finish_agent_kernel_turn(status="replayed")
                    return
                if not claimed_turn:
                    yield self._attach_runtime_identity({"event": "done", "data": {
                        "conversation_id": conversation_id,
                        "message_id": None,
                        "completion_status": "interrupted",
                        "client_turn_id": client_turn_id,
                        "replayed": True,
                        "request_persisted": False,
                    }})
                    self._finish_agent_kernel_turn(status="interrupted")
                    return

            try:
                self.db.expire_all()
                existing_turn = turn_service.find_user_message_by_client_turn(
                    user_id,
                    client_turn_id,
                )
                assistant = turn_service.find_assistant_message_by_client_turn(
                    user_id,
                    client_turn_id,
                )
                if (
                    existing_turn is not None
                    and assistant is not None
                    and self._should_replay_finalized_assistant(assistant, existing_turn)
                ):
                    async for replay_event in self._replay_client_turn(
                        turn_service, user_id, existing_turn, client_turn_id,
                    ):
                        yield self._attach_runtime_identity(replay_event)
                    turn_service.release_client_turn_execution(user_id, client_turn_id)
                    claimed_turn = False
                    self._finish_agent_kernel_turn(status="replayed")
                    return
                if existing_turn is not None:
                    turn_service.discard_unfinalized_assistant_by_client_turn(
                        user_id,
                        client_turn_id,
                    )
                    recovered_user_message = existing_turn
            except BaseException:
                if claimed_turn:
                    turn_service.release_client_turn_execution(user_id, client_turn_id)
                    claimed_turn = False
                self._finish_agent_kernel_turn(status="failed")
                raise

        try:
            retry_recovery: RetryableTurnRecovery | None = None
            if recovered_user_message is not None:
                retry_recovery = restore_retryable_turn_recovery(
                    self.db,
                    user_id=user_id,
                    user_message=recovered_user_message,
                )
            elif not images and not file_base64:
                retry_recovery = resolve_retryable_turn_recovery(
                    self.db,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    confirmation_text=message,
                )

            display_message = message or ""
            effective_message = display_message
            effective_images = images
            persist_images = images
            if retry_recovery is not None:
                effective_message = retry_recovery.message
                persist_images = []
                try:
                    effective_images = materialize_retryable_turn_images(
                        retry_recovery,
                        user_id=user_id,
                    )
                except (OSError, ValueError):
                    self._start_agent_kernel_turn(
                        user_id=user_id,
                        message=effective_message,
                        channel=channel,
                        client_caps=client_caps,
                        client_time_context=client_time_context,
                        media=(),
                        client_turn_id=client_turn_id,
                        run_id=run_id,
                    )
                    kernel_completion_status = "error"
                    notice = "原请求中的图片暂时无法读取，请重新选择图片后发送。"
                    yield {"event": "token", "data": {"content": notice}}
                    yield self._attach_runtime_identity({
                        "event": "done",
                        "data": {
                            "conversation_id": conversation_id,
                            "message_id": None,
                            "completion_status": "error",
                            "client_turn_id": client_turn_id,
                            "request_persisted": False,
                            "recovery_error": "retry_source_image_unavailable",
                        },
                    })
                    return

            self._current_turn_user_message = effective_message
            self._current_turn_has_attachment = bool(
                effective_images or file_base64
            )
            self._start_agent_kernel_turn(
                user_id=user_id,
                message=effective_message,
                channel=channel,
                client_caps=client_caps,
                client_time_context=client_time_context,
                media=_kernel_media_metadata(
                    effective_images,
                    has_file=bool(file_base64),
                    file_name=file_name,
                ),
                client_turn_id=client_turn_id,
                run_id=run_id,
            )

            if recovered_user_message is not None:
                recovered_meta = dict(recovered_user_message.meta or {})
                recovered_write_state = dict(recovered_meta.get("write_state") or {})
                recovered_write_operations = recovered_meta.get("write_operations") or {}
                recovered_operation_blocks_retry = (
                    isinstance(recovered_write_operations, dict)
                    and any(
                        isinstance(operation, dict)
                        and operation.get("status") in {
                            "in_flight", "uncertain", "verified",
                        }
                        for operation in recovered_write_operations.values()
                    )
                )
                recovered_receipts = recovered_meta.get("write_receipts") or []
                # A medication tool can commit a source-bound pending plan and
                # then lose its worker before the generic write checkpoint is
                # finalized.  That state is neither an unknown write nor safe
                # to rerun through the model.  Let the deterministic batch
                # resolver below recover and re-render the exact frozen plan.
                recovered_medication_plan = self._source_bound_medication_intent(
                    user_id=user_id,
                    conversation_id=int(recovered_user_message.conversation_id),
                    source_message_id=int(recovered_user_message.id),
                )
                if (
                    recovered_medication_plan is None
                    and (
                        recovered_write_state.get("status") in {
                            "in_flight", "uncertain", "verified",
                        }
                        or recovered_operation_blocks_retry
                        or bool(recovered_receipts)
                    )
                ):
                    async for event in self._recover_client_turn_write_checkpoint(
                        turn_service,
                        user_id,
                        recovered_user_message,
                        client_turn_id,
                    ):
                        yield self._attach_runtime_identity(event)
                    return
            async for event in self._run_stream_impl(
                user_id=user_id,
                message=effective_message,
                conversation_id=conversation_id,
                user_auth_token=user_auth_token,
                images=effective_images,
                file_base64=file_base64,
                file_name=file_name,
                extra_context=extra_context,
                channel=channel,
                client_turn_id=client_turn_id,
                recovered_user_message=recovered_user_message,
                client_caps=client_caps,
                client_time_context=client_time_context,
                read_only_tools=read_only_tools,
                display_message=display_message,
                persist_images=persist_images,
                retry_recovery=retry_recovery,
            ):
                if event.get("event") == "done":
                    kernel_completion_status = str(
                        (event.get("data") or {}).get("completion_status") or "complete"
                    )
                yield self._attach_runtime_identity(event)
        finally:
            if claimed_turn and turn_service is not None and client_turn_id:
                turn_service.release_client_turn_execution(user_id, client_turn_id)
            self._finish_agent_kernel_turn(status=kernel_completion_status)

    async def _run_stream_impl(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        user_auth_token: Optional[str] = None,
        images: Optional[List[dict]] = None,
        file_base64: Optional[str] = None,
        file_name: Optional[str] = None,
        extra_context: Optional[str] = None,
        channel: Optional[str] = None,
        client_turn_id: Optional[str] = None,
        recovered_user_message: Any = None,
        client_caps: Optional[List[str]] = None,
        client_time_context: Optional[Dict[str, Any]] = None,
        read_only_tools: bool = False,
        display_message: Optional[str] = None,
        persist_images: Optional[List[dict]] = None,
        retry_recovery: RetryableTurnRecovery | None = None,
    ) -> AsyncGenerator[Dict, None]:
        """运行 Agent 循环，SSE 流式输出"""
        from app.services.llm.usage_tracker import set_caller
        set_caller("agent_executor.run_stream", user_id=user_id)
        # 输入通道(客户端传输层声明,typed/voice/siri):症状类记录的确认策略依赖它。
        # 非法/未声明一律 None → fail-closed(症状保留确认)。
        self._turn_channel = channel if channel in ("typed", "voice", "siri") else None
        self._current_user_id = user_id
        self._current_turn_user_message = message or ""
        self._turn_contextual_diet_receipts = []
        self._turn_contextual_diet_cards = []
        self._turn_attachment_write_receipts = []
        self._turn_contextual_diet_record_id = None
        self._turn_contextual_diet_consumed_fraction = None
        self._ensure_agent_kernel_turn(channel=channel)
        # Backend-owned health evidence runtime. Clinical semantics are compiled
        # before any client-specific presentation or model routing so Mobile/Mac
        # cannot diverge. A health answer is buffered until deterministic verify.
        health_evidence_turn = None
        health_verification = None
        health_evidence_manifest: Optional[Dict[str, Any]] = None
        health_continuation_attempted = False
        if getattr(settings, "health_evidence_runtime_enabled", False):
            from app.services import health_evidence as _health_evidence
            from app.services.health_evidence.continuation import (
                parse_health_evidence_continuation,
                resolve_health_evidence_continuation_query,
            )

            continuation_parse = parse_health_evidence_continuation(extra_context)
            health_continuation_attempted = continuation_parse.attempted
            clinical_query = resolve_health_evidence_continuation_query(
                self.db,
                user_id=user_id,
                parsed=continuation_parse,
                fallback_query=message,
            )
            health_intent = _health_evidence.classify_health_intent(
                clinical_query,
                client=channel,
            )
            if health_intent.requires_authority:
                try:
                    health_evidence_turn = (
                        _health_evidence.build_health_evidence_turn(
                            self.db,
                            user_id=user_id,
                            query=clinical_query,
                            intent=health_intent,
                            now=self._agent_kernel_reference_now(),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - never fall back to legacy advice
                    logger.exception(
                        "[health_evidence] turn compilation failed user=%s "
                        "error_type=%s",
                        user_id,
                        type(exc).__name__,
                    )
                    from app.twin.schema import HealthTwin, TwinMeta

                    health_evidence_turn = (
                        _health_evidence.compile_health_evidence_turn(
                            twin=HealthTwin(
                                meta=TwinMeta(
                                    user_id=user_id,
                                    generated_at=self._agent_kernel_reference_now(),
                                    failed_partitions=[
                                        "acute",
                                        "medication",
                                        "safety_profile",
                                        "chronic",
                                    ],
                                )
                            ),
                            intent=health_intent,
                            authority_results=(),
                            now=self._agent_kernel_reference_now(),
                        )
                    )
        health_advice_buffered = health_evidence_turn is not None
        deterministic_health_release = bool(
            health_evidence_turn is not None
            and health_evidence_turn.sufficiency != "sufficient"
        )
        # GenUI metric_table (rank1): 客户端声明 genui-table-v1 且未被 kill-switch 关闭时,
        # 工具结果确定性打成表格卡片 (合成后追加 fence)。正文仍按问题完整回答，避免
        # 把卡片优化误变成用户可见的 500 字硬截断。
        # 无 cap / flag 关 → 逐字节现状 (不追踪、不注入、不追加)。fail-open。
        from app.services.genui import GENUI_TABLE_CAP as _GENUI_TABLE_CAP
        genui_table_on = (
            getattr(settings, "genui_table_enabled", True)
            and _GENUI_TABLE_CAP in (client_caps or [])
        )
        # 汇总类卡结构化 v1:客户端声明 genui-diet-summary-v1 时,health_query(diet) 结果
        # 走结构化 diet_summary 卡(而非通用 metric_table)。cap 是主门控(客户端暗置时不发)。
        from app.services.genui import GENUI_DIET_SUMMARY_CAP as _GENUI_DIET_SUMMARY_CAP
        genui_diet_summary_on = (
            getattr(settings, "genui_diet_summary_enabled", True)
            and _GENUI_DIET_SUMMARY_CAP in (client_caps or [])
        )
        # 汇总类卡结构化 v1(睡眠):客户端声明 genui-sleep-summary-v1 时,health_query(sleep)
        # 走结构化 sleep_summary 卡(而非通用 metric_table)。cap 主门控,与 diet 同机制。
        from app.services.genui import GENUI_SLEEP_SUMMARY_CAP as _GENUI_SLEEP_SUMMARY_CAP
        genui_sleep_summary_on = (
            getattr(settings, "genui_sleep_summary_enabled", True)
            and _GENUI_SLEEP_SUMMARY_CAP in (client_caps or [])
        )
        # 汇总类卡结构化 v1(用药):客户端声明 genui-medication-list-v1 时,health_query(medication)
        # 走结构化 medication_list 卡(而非通用 metric_table)。cap 主门控,与 diet/sleep 同机制。
        from app.services.genui import GENUI_MEDICATION_LIST_CAP as _GENUI_MEDICATION_LIST_CAP
        genui_medication_list_on = (
            getattr(settings, "genui_medication_list_enabled", True)
            and _GENUI_MEDICATION_LIST_CAP in (client_caps or [])
        )
        # 本回合已执行的只读数据查询工具 (name, args, result) —— 供合成后确定性建表。
        genui_tool_calls: List[Tuple[str, Optional[dict], str]] = []
        # 多模型综合分析 (商用三强 panel)。仅纯文本分析回合走此路径;
        # 带图片/附件时回退普通单模型路径 (panel 是文本综合, 不处理多模态)。
        if (
            _extract_multi_model_flag(extra_context)
            and not health_advice_buffered
            and not images
            and not file_base64
            and not (
                _medication_batch_turn_bypasses_multi_model(message)
                or (
                    _medication_batch_control_action(message) is not None
                    and self._has_pending_medication_confirmation_for_route(
                        user_id=user_id,
                        conversation_id=conversation_id,
                    )
                )
            )
            and not _has_fast_record_write_intent(message or "")
        ):
            async for evt in self._run_multi_model_stream(
                user_id,
                message,
                conversation_id,
                user_auth_token,
                extra_context,
                client_turn_id,
                recovered_user_message,
                client_time_context,
            ):
                yield evt
            return

        start_time = time.time()
        self._current_user_id = user_id
        self._diet_photo_auto_save = _is_diet_photo_auto_save_turn(
            extra_context,
            has_images=bool(images),
        )
        self._request_model_id = (
            str(getattr(settings, "health_evidence_model_id", "") or "").strip()
            if health_advice_buffered
            else _extract_model_id_from_extra_context(extra_context)
        ) or None
        self._request_model_tool_fallback_used = False
        self._fast_route_simple_turn = False
        self._analysis_turn_subset = False  # R5:纯分析轮只读工具子集(flag 门控,下方设定)
        self._tool_round_fast_routed = False
        self._lite_tool_round_messages = None
        self._turn_any_tool_executed = False
        self._force_no_tools_synthesis = False
        self._turn_evidence_card = _TURN_CARD_UNSET
        self._turn_evidence_card_key = None
        self._turn_twin_write_occurred = False
        self._model_fallback_reasons = []
        self._tool_model_names = []
        self._dead_provider_model_ids = set()
        self._tool_dead_provider_model_ids = set()
        self._last_effective_model_id = None
        self._turn_invoked_deep_analysis = False
        # Read-only pregen turn (rank7): reset per-turn. When set, _execute_tool
        # fail-closed-blocks any non-allowlisted tool and flags a write attempt so
        # the pregen orchestrator discards the answer instead of serving it.
        self._read_only_turn = bool(read_only_tools)
        self._read_only_turn_write_attempted = False
        self._current_turn_user_message = message or ""
        self._prefer_fast_record_model = (
            health_evidence_turn is None
            and not images
            and not file_base64
            and _has_fast_record_write_intent(message or "")
        )
        partial_diet_correction_requested = bool(
            (
                _parse_explicit_diet_correction(
                    message or "",
                    reference_now=self._agent_kernel_reference_now(),
                )
                or {}
            ).get("consumed_fraction")
        )
        write_action_requested = bool(
            self._prefer_fast_record_model
            or partial_diet_correction_requested
            or _needs_reliable_tool_model(message or "")
        )
        # 合成轮关思考门(2026-07-17, founder「列出胃药」实测合成轮 qwen3.7-max 思考 23–47s):
        # reasoning 模型(qwen3.7-max)的思考阶段对**简单查询/列表**是纯浪费。判据复用
        # _is_fast_eligible_turn(记录或简单查询意图, 且**非**建议/分析)—— 与快路由同一分类,
        # 但**独立于模型选择**: 用户显式选了 qwen3.7-max(尊重其选择, 仍用该模型)也在合成轮
        # 关思考。分析/建议/深度分析回合(此判据 False, 或本轮调 health_analysis)保留完整思考,
        # 规避全局思考封顶伤分析质量被 A/B 否决的老坑。探针实证 TTFT ~36s→~1.6s。
        self._turn_synthesis_skip_thinking = _is_fast_eligible_turn(
            message or "", has_images=bool(images), has_file=bool(file_base64)
        )
        # 2026-07-02: FAST-MODEL 路由 — 简单记录/查询回合走最快的可靠工具调用模型,
        # 建议/分析/复盘等仍用用户偏好的质量模型 (qwen3.7-plus)。
        # 只替换"默认"模型: 用户在 UI 显式选了模型 (_request_model_id 已由 extra_context
        # 填充) 时**绝不**覆盖, 尊重显式选择。安全 (确定性 SafetyGuardian) 与模型无关。
        # 可观测性: 复用 _request_model_id → provider 路由, [perf.agent] log 与 done.meta
        # 会自动显示快模型。
        if self._request_model_id is None and _is_fast_eligible_turn(
            message or "", has_images=bool(images), has_file=bool(file_base64)
        ):
            try:
                from app.services.llm.model_registry import pick_fast_tool_model_id

                fast_id = pick_fast_tool_model_id()
                if fast_id:
                    self._request_model_id = fast_id
                    self._fast_route_simple_turn = True
                    self._record_model_fallback_reason("fast_route_simple_turn")
                    logger.info(
                        "[agent_executor] fast-route simple turn user=%s model=%s "
                        "message_chars=%s",
                        user_id, fast_id, len(message or ""),
                    )
            except Exception as e:  # noqa: BLE001 — 快路由失败绝不断主链路, 退回默认模型
                logger.warning("[agent_executor] fast-route failed, keep default: %s", e)
        # R5 分析轮只读工具子集(flag 门控,默认关=零行为)。纯分析/知识轮不裁模型(仍用质量
        # 模型答正文),只裁**工具集** → 首轮只发只读工具,省 health_record/manage/upload schema。
        # 与 fast 简单轮互斥(fast 已有 big-3 子集)。模型要写 → 下方 withheld-upgrade 升级回全集。
        if (
            getattr(settings, "analysis_turn_tool_subset", False)
            and not self._fast_route_simple_turn
            and _is_analysis_only_turn(
                message or "", has_images=bool(images), has_file=bool(file_base64)
            )
        ):
            self._analysis_turn_subset = True
            self._record_model_fallback_reason("analysis_turn_tool_subset")
        self._last_provider_model_name = None
        # 可解释性: 记录本次回答用到的数据源. 必须在 system prompt / inspection 前初始化.
        sources_used: list = []

        # 2026-07-01: PURE-MEASUREMENT 阶段级性能埋点 (镜像 orchestrator.py [perf.orchestrator]).
        # 目标: 找 pre-first-token 阶段瓶颈 + 驱动 mac 端 waterfall。**绝不改任何行为**。
        # fail-soft: 每个计时点用 _pre_stage() 包起来, 计时异常不影响主流程 (返回 0)。
        pre_stages: Dict[str, int] = {
            "conv_ms": 0, "opener_ms": 0, "system_prompt_ms": 0,
            "kb_ms": 0, "inspect_ms": 0, "history_ms": 0, "vision_ms": 0,
        }

        def _pre_stage(_t0: float) -> int:
            """time.time() delta → int ms, 永不抛 (计时 bug 不能断流)。"""
            try:
                return int((time.time() - _t0) * 1000)
            except Exception:  # noqa: BLE001
                return 0

        # 1. 获取或创建会话（第一方 Agent 对话管理）
        _t_stage = time.time()
        from app.services.agent_conversation_service import AgentConversationService
        svc = AgentConversationService(self.db)
        conv = svc.get_or_create_conversation(
            user_id,
            (
                recovered_user_message.conversation_id
                if recovered_user_message is not None
                else conversation_id
            ),
            title=message,
        )
        stored_message = (
            display_message if display_message is not None else message
        )
        stored_images = images if persist_images is None else persist_images
        turn_user_meta: Dict[str, Any] = {}
        if client_turn_id:
            turn_user_meta["client_turn_id"] = client_turn_id
        if retry_recovery is not None:
            turn_user_meta["retry_source"] = retry_recovery.user_message_meta()

        # 先 claim 用户消息，再落图片。这样 DB claim 失败时不会产生孤儿文件；
        # worker 在 ACK 前退出时，新 worker 也能沿同一 turn 继续补齐图片。
        user_content = stored_message
        if stored_images:
            user_content += f"\n[附图: {len(stored_images)}张]"
        if file_base64 and file_name:
            user_content += f"\n[附件: {file_name}]"

        created_user_message = False
        if recovered_user_message is not None:
            user_msg = recovered_user_message
        else:
            user_msg, created_user_message = svc.save_user_message_once(
                conv.id,
                user_id,
                user_content,
                client_turn_id=client_turn_id,
                image_url=None,
                meta=turn_user_meta or None,
            )

        saved_image_urls: List[str] = []
        if user_msg.image_url:
            try:
                parsed_image_urls = json.loads(user_msg.image_url)
                if isinstance(parsed_image_urls, list):
                    saved_image_urls = [
                        str(url) for url in parsed_image_urls if isinstance(url, str) and url
                    ]
                elif isinstance(parsed_image_urls, str) and parsed_image_urls:
                    saved_image_urls = [parsed_image_urls]
            except (json.JSONDecodeError, TypeError):
                if isinstance(user_msg.image_url, str) and user_msg.image_url:
                    saved_image_urls = [user_msg.image_url]

        new_image_urls: List[str] = []
        if stored_images:
            try:
                for index, img in enumerate(
                    stored_images[len(saved_image_urls):],
                    start=len(saved_image_urls),
                ):
                    object_key = None
                    if client_turn_id:
                        object_key = hashlib.sha256(
                            f"{int(user_id)}:{client_turn_id}:{index}".encode()
                        ).hexdigest()
                    url = self._upload_chat_image(
                        img["base64"],
                        img.get("type", "jpeg"),
                        user_id,
                        object_key,
                    )
                    if not url:
                        raise RuntimeError("chat_image_persistence_failed")
                    saved_image_urls.append(url)
                    new_image_urls.append(url)
            except Exception as error:
                from app.services.chat_utils import delete_chat_image

                for saved_url in new_image_urls:
                    try:
                        delete_chat_image(saved_url, user_id)
                    except Exception:
                        logger.warning("Failed to clean partial chat image upload", exc_info=True)
                if created_user_message:
                    try:
                        self.db.delete(user_msg)
                        self.db.commit()
                    except Exception:
                        self.db.rollback()
                        logger.error("Failed to roll back image turn claim", exc_info=True)
                raise RuntimeError("chat_image_persistence_failed") from error
        image_url_value = json.dumps(saved_image_urls) if saved_image_urls else None
        try:
            if image_url_value or user_msg.image_url:
                updated_user_msg = svc.update_user_message_after_image_upload(
                    user_id,
                    user_msg.id,
                    content=user_content,
                    image_url=image_url_value or user_msg.image_url,
                    meta=(
                        turn_user_meta or None
                    ),
                )
                if updated_user_msg is None:
                    raise RuntimeError("chat_image_message_missing")
                user_msg = updated_user_msg
            else:
                user_msg.content = user_content
                user_msg.meta = {
                    **(user_msg.meta or {}),
                    **turn_user_meta,
                }
                self.db.commit()
                self.db.refresh(user_msg)
        except Exception:
            self.db.rollback()
            from app.services.chat_utils import delete_chat_image

            for saved_url in new_image_urls:
                try:
                    delete_chat_image(saved_url, user_id)
                except Exception:
                    logger.warning("Failed to clean uncommitted chat image", exc_info=True)
            if created_user_message:
                try:
                    claimed = self.db.get(type(user_msg), user_msg.id)
                    if claimed is not None:
                        self.db.delete(claimed)
                        self.db.commit()
                except Exception:
                    self.db.rollback()
                    logger.error("Failed to remove uncommitted image turn", exc_info=True)
            raise
        pre_stages["conv_ms"] = _pre_stage(_t_stage)

        yield {"event": "request_persisted", "data": {
            "conversation_id": conv.id,
            "user_message_id": user_msg.id,
            "client_turn_id": client_turn_id,
            "image_urls": saved_image_urls,
            "recovered": recovered_user_message is not None,
        }}

        self._current_turn_source_message_id = int(user_msg.id)
        self._current_turn_media_source_message_id = (
            int(retry_recovery.source_message_id)
            if retry_recovery is not None
            else int(user_msg.id)
        )
        self._current_turn_conversation_id = int(conv.id)
        self._current_turn_image_urls = (
            list(retry_recovery.image_urls)
            if retry_recovery is not None
            else list(saved_image_urls)
        )
        self._bind_agent_kernel_source_message(user_msg.id)
        try:
            self._bind_agent_kernel_actionable_references(
                svc.build_actionable_references(conv.id)
            )
        except Exception as exc:  # noqa: BLE001 - context loss must not abort the turn
            logger.warning(
                "[agent_executor] actionable context projection failed "
                "conversation=%s error=%s",
                conv.id,
                exc,
            )

        # Multi-medication intake is a server-owned two-turn transaction:
        # source-bound proposal now, strict immediate confirmation next turn.
        # It runs after the durable user ACK but before recipes, prompts, or any
        # model call.  Read-only pregeneration is never allowed to propose or
        # execute a health write.
        if (
            health_evidence_turn is None
            and not read_only_tools
            and not images
            and not file_base64
        ):
            medication_batch_result = self._resolve_medication_batch_turn(
                user_id=user_id,
                conversation_id=conv.id,
                user_message=user_msg,
                message=message,
            )
            if medication_batch_result is not None:
                async for evt in self._run_medication_batch_result(
                    medication_batch_result,
                    svc=svc,
                    conv=conv,
                    user_id=user_id,
                    client_turn_id=client_turn_id,
                    start_time=start_time,
                ):
                    yield evt
                return

        # ── Slice 3 程序性配方: 触发短语精确匹配 (先于 fast-path/LLM)。
        # strip 后等值才命中 (不做模糊匹配, 控误触发); 命中 → 确定性逐步重放,
        # 每步确认策略沿用该 kind 既有 confirm tier (typed_only/never_auto 原样
        # 生效, 配方不绕任何确认门)。匹配失败/异常绝不断主链路 (fail-soft 回
        # 正常 LLM 路径, 但记 warning 可观测)。
        if (
            health_evidence_turn is None
            and not images
            and not file_base64
        ):
            matched_recipe = None
            try:
                from app.services.procedure_recipe_service import match_trigger

                matched_recipe = match_trigger(self.db, user_id, message)
            except Exception as e:  # noqa: BLE001 — 匹配层失败回退 LLM, 不吞成静默
                logger.warning("[agent_executor] recipe match_trigger failed: %s", e)
            if matched_recipe is not None:
                async for evt in self._run_recipe_replay(
                    matched_recipe,
                    svc,
                    conv,
                    user_msg,
                    user_id,
                    user_auth_token,
                    client_turn_id,
                    start_time,
                ):
                    yield evt
                return

        _t_stage = time.time()
        opener_quick_reply_note = None
        try:
            from app.services.opener_quick_reply import apply_opener_quick_reply_context

            opener_quick_reply_note = apply_opener_quick_reply_context(
                self.db,
                user_id=user_id,
                message=message,
                extra_context=extra_context,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[agent_executor] opener quick reply context failed: {e}")
        pre_stages["opener_ms"] = _pre_stage(_t_stage)

        # 2. 构建 system prompt（复用健康上下文）
        # fast-routed 简单回合走 lite prompt: 剥掉分析 blob (基因/世界观/肝/血常规/疗程/
        # 干预/效应/记忆), 只留核心人格 + R4 边界 + 防回显 + 记录参数指引 + 基础画像。
        # 非快路由回合 lite=False → prompt 逐字节不变。
        _t_stage = time.time()
        system_content = self._build_system_prompt(
            user_id, conv.id, user_auth_token, lite=self._fast_route_simple_turn,
            intent_query=message,
            health_evidence_runtime=health_advice_buffered,
        )
        for source_label in _source_labels_from_system_prompt(system_content):
            if source_label not in sources_used:
                sources_used.append(source_label)
        pre_stages["system_prompt_ms"] = _pre_stage(_t_stage)
        if self._fast_route_simple_turn:
            # 可观测性: 记录 lite prompt 的实际字符数, 用来看 prefill 削减 (对比 full)。
            logger.info(
                "[agent_executor] fast-route lite system prompt user=%s chars=%d",
                user_id, len(system_content),
            )
        # ── turn-scoped 上下文(2026-07-11 token 优化 #6:前缀缓存排布)────────
        # 这四块(入口动作/桌面格式/入口上下文/KB 证据)逐回合变化,曾拼在 system
        # 尾部 → system 每回合字节不同,拆掉 provider 前缀缓存(生产实测基线命中率
        # 29.2%)。改为注入**最后一条 user 消息**:前缀 = system+tools+旧历史 保持
        # 字节稳定,turn 内容落在增长尾部,天然不破坏前缀匹配。块文本逐字保留。
        turn_context_parts: List[str] = []
        turn_context_parts.append(self._agent_kernel_time_context(client_time_context))
        if health_evidence_turn is not None:
            # Clinical envelope precedes every surface-format instruction. Clients
            # may alter presentation, never risk semantics or admitted evidence.
            turn_context_parts.append(health_evidence_turn.private_prompt())
        actionable_context = format_actionable_context_prompt(
            (self._agent_kernel_snapshot.actionable_references or ())
            if self._agent_kernel_snapshot is not None
            else ()
        )
        if actionable_context:
            turn_context_parts.append(actionable_context)
        goal_contract = format_goal_contract_prompt(
            self._agent_kernel_snapshot.goal
            if self._agent_kernel_snapshot is not None else None
        )
        if goal_contract:
            turn_context_parts.append(goal_contract)
        if opener_quick_reply_note:
            turn_context_parts.append(
                "## 入口动作处理结果\n"
                f"{opener_quick_reply_note}\n"
                "请先用一句话确认这次验证/反馈已经接上了对应行动卡片，再给出下一步。"
            )
            if "ActionCard" not in sources_used:
                sources_used.append("ActionCard")
        if genui_table_on or genui_diet_summary_on or genui_sleep_summary_on or genui_medication_list_on:
            # GenUI metric_table (rank1): 客户端声明 genui-table-v1 → 数据由后端确定性
            # 表格卡片直接呈现。diet_daily_summary 卡同理(cap 开时 diet 查询走结构化卡)。
            # 正文按问题完整回答，只需避免逐行重复。**服务端硬门**: 即便旧客户端
            # 仍在 extra_context 里塞 mac "最高优先级要求生成大 markdown 表", 声明了 cap 就
            # 以本契约为准并**覆盖**那条指令 —— 否则旧指令会一边索要 4000 字表格、一边又声明
            # cap, 也不能同时要求两种互相冲突的展示格式。
            turn_context_parts.append(
                "## 数据回答格式要求（最高优先级）\n"
                "本回合若涉及健康数据查询，系统已用表格卡片把数值直接呈现给用户。因此：\n"
                "- **正文按问题完整回答**：结论先行，按需展开背景、证据、风险、边界和行动，不因卡片存在而截断；\n"
                "- **结构清晰**：先给 2-3 条关键要点，再给必要的解读与可执行行动建议；\n"
                "- **绝不逐行复述表格中的数值行**（用户已在卡片里看到），只做解读、趋势、对比与行动指引；\n"
                "- **安全例外**：异常或需立即分流的数值（如血压严重升高、血氧过低、血糖过高或过低、"
                "化验危急值等）**必须在正文中明确说出具体数值**并给出对应行动建议，不受上面"
                "\"不复述表格数值\"约束；是否异常/危急以系统安全提示（⚠️ 安全提示）与卡片中的"
                "分级/异常标注为准，不要给系统标注为正常的数值自行加危急判断；\n"
                "- 不确定性与安全边界照常表达。"
            )
        else:
            desktop_response_instruction = _extract_desktop_response_instruction(extra_context)
            if desktop_response_instruction:
                turn_context_parts.append(
                    "## 桌面端回复格式要求\n"
                    f"{desktop_response_instruction}\n"
                    "这是桌面端展示的最高优先级格式要求；除非用户明确要求纯文本，否则必须遵守。"
                )
        database_verification_instruction = _extract_database_verification_instruction(extra_context)
        if database_verification_instruction:
            turn_context_parts.append(database_verification_instruction)
            try:
                database_verification_snapshot = _build_database_verification_snapshot(
                    self.db, user_id, extra_context
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[agent_executor] database verification snapshot failed: %s", e)
                database_verification_snapshot = None
            if database_verification_snapshot:
                turn_context_parts.append(database_verification_snapshot)
        # 入口 deeplink 携带的结构化上下文 — 用户在 SNP/饮食/运动等页点"详细聊"时,
        # 把当前页正展示的具体方案条目透传过来, 让 LLM 不重新猜, 在已有方案上深化.
        if (
            extra_context
            and extra_context.strip()
            and health_evidence_turn is None
            and not health_continuation_attempted
        ):
            turn_context_parts.append(
                "## 入口上下文 (用户正在看的具体方案)\n"
                "用户从下面这个上下文点过来跟你详细聊, 请在**这些已展示的具体条目**上深化, "
                "不要重新生成方案; 引用条目名称时跟用户已看见的一致.\n"
                f"```\n{extra_context.strip()[:4000]}\n```"
            )
        _t_stage = time.time()
        # fast-routed 简单回合跳过系统知识库检索: KB claim 是给分析/解读用的依据,
        # 对「今天喝了多少水」无用, 且检索本身占 pre-first-token 壁钟 (kb_ms)。
        system_kb_context = (
            "" if self._fast_route_simple_turn or health_advice_buffered
            else self._build_system_knowledge_prompt_context(user_id, message)
        )
        pre_stages["kb_ms"] = _pre_stage(_t_stage)
        if system_kb_context:
            turn_context_parts.append(system_kb_context)
            if "系统知识库" not in sources_used:
                sources_used.append("系统知识库")
        # 2026-05-14: 用户数据源 inspection — 不依赖 system_prompt 实际用了什么,
        # 直接 SQL count 用户哪些表有数据, 给"AI 用了什么数据"chip 用.
        _t_stage = time.time()
        if health_evidence_turn is not None:
            # Truthful projection: list only evidence actually selected this turn,
            # never every populated user table.
            health_preview = health_evidence_turn.public_manifest()
            sources_used = list(
                dict.fromkeys(
                    str(item.get("organization") or "").strip()
                    for item in health_preview.get("authority_sources", [])
                    if str(item.get("organization") or "").strip()
                )
            )
            context_categories = [
                str(item).strip()
                for item in health_preview.get("context_categories_used", [])
                if str(item).strip()
            ]
            if context_categories:
                sources_used.append(
                    "个人健康上下文：" + "、".join(context_categories)
                )
        else:
            try:
                sources_used.extend(_inspect_user_data_sources(self.db, user_id))
            except Exception as e:
                logger.warning(f"[sources_used] inspect failed: {e}")
        pre_stages["inspect_ms"] = _pre_stage(_t_stage)

        # 3. 构建对话历史
        _t_stage = time.time()
        messages = svc.build_messages(conv.id, limit=15)
        recent_messages = messages
        if (
            recent_messages
            and isinstance(recent_messages[-1], dict)
            and recent_messages[-1].get("role") == "user"
            and recent_messages[-1].get("content") == user_content
        ):
            recent_messages = recent_messages[:-1]
        self._current_turn_recent_messages = [
            dict(item) for item in recent_messages[-6:] if isinstance(item, dict)
        ]
        if retry_recovery is not None:
            for history_message in reversed(messages):
                if history_message.get("role") == "user":
                    history_message["content"] = message
                    break
        # 确定性护栏 (R4): 历史里助手消息带过 ```reva-ui``` 图表 block —— 若原样喂回
        # LLM, 它会**模仿**这个格式并**编造**图表数据 (实测: 编 "Apple Watch + Garmin +
        # RingConn 多源合并")。把历史助手消息里的 block 换成占位符, LLM 无从模仿。
        # (确定性短路自身产出的 block 走独立更早返回的路径, 不经此处 → 不受影响。)
        for _m in messages:
            if _m.get("role") == "assistant" and _m.get("content"):
                _m["content"] = _placeholder_reva_ui_in_history(_m["content"])
        messages.insert(0, {"role": "system", "content": system_content})
        pre_stages["history_ms"] = _pre_stage(_t_stage)

        # 如果有图片：明确的普通图片可直传商用多模态模型；食物语境和
        # Mobile 的默认纯图片提示必须先走结构化识别，避免 provider 选择
        # 绕过饮食清洗、校准与写入边界。
        _t_stage = time.time()
        vision_description = None
        if images:
            should_preprocess_images = self._should_preprocess_attached_images(user_id, message)
            if should_preprocess_images:
                # 真实思考过程: 图片/视觉预处理 (4–20s 的 vision_ms 块) 即将开始。
                # 仅在会真的跑独立 vision 预处理时发 (原图直传多模态模型时无此阶段)。
                yield self._status_event("vision", detail=None)
                if _looks_like_medical_report_image_context(message):
                    snapshot = self._ensure_agent_kernel_turn()
                    persist_medical_report = bool(
                        snapshot.intent.primary in {"write", "mutate"}
                        and snapshot.intent.is_write
                    )
                    vision_description = await self._try_import_medical_report_images(
                        user_id,
                        images,
                        persist=persist_medical_report,
                    )
                if not vision_description:
                    vision_description = await self._analyze_image_with_vision(message, images)

            if vision_description:
                enriched_message = f"{message}\n\n[图片识别结果]: {vision_description}"
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i]["content"] = enriched_message
                        break
                logger.info("[Vision] 图片识别完成 chars=%s", len(vision_description))
            else:
                _attach_images_to_last_user_message(messages, message, images)
        pre_stages["vision_ms"] = _pre_stage(_t_stage) if images else 0
        if self._turn_attachment_write_receipts:
            turn_context_parts.append(
                "## 附件写入结果\n"
                "本回合的医疗报告图片已保存并取得持久化回执；OCR 文字仍待用户核对。"
                "不要再次调用 upload_medical_exam_text 写入同一份报告；"
                "用户要求分析时，请基于图片识别结果直接回答。"
            )

        # ── fast-routed 工具决策轮的 lite 消息栈 (2026-07-12 token 优化: 首个工具决策轮
        # 已 fast-route 到 qwen3.6-flash, 但仍背 ~14k-token 全量栈 → flash 白付 6-8s prefill)。
        # **必须在 turn-context(KB 证据)折进最后一条 user 之前**快照 —— 此刻最后一条 user
        # 只含用户原话(或 vision 增强), KB 天然缺席; 用 lite system prompt(无分析 blob)+
        # 折进紧邻 assistant 做消歧。仅当**首个工具决策轮**真 fast-route 时才被消费(见
        # _messages_for_round); 合成/答案轮与快路由失守时仍走下面组装的全量 messages。
        # 只对可能命中快路由的回合构建(flag 开 + 非整轮快路由): _fast_route_simple_turn /
        # _prefer_fast_record_model 已把整轮(含合成)降 fast, _maybe_fast_route_tool_round
        # 对它们恒返回 None → 无需 lite 栈。fail-open: 构建失败/多模态 → None → 全量栈。
        if (
            getattr(settings, "task_tiered_routing", False)
            and not self._fast_route_simple_turn
            and not self._prefer_fast_record_model
        ):
            try:
                lite_system = self._build_tool_decision_system_prompt()
                self._lite_tool_round_messages = _build_lite_tool_round_messages(
                    lite_system, messages,
                )
            except Exception as e:  # noqa: BLE001 — lite 栈构建失败绝不断主链路, 退回全量栈
                logger.warning(
                    "[agent_executor] lite tool-round messages build failed, keep full: %s", e
                )
                self._lite_tool_round_messages = None

        # turn-scoped 上下文注入最后一条 user 消息(#6,必须在 vision 重写之后,
        # 否则会被 enriched_message 覆盖)。上下文在前、用户原话在后(recency 保持
        # 问题主导);标注来源=系统,防止模型当成用户自述。
        if turn_context_parts:
            _turn_ctx = "\n\n".join(turn_context_parts)
            _injected = False
            for _i in range(len(messages) - 1, -1, -1):
                if messages[_i].get("role") == "user":
                    _existing = messages[_i].get("content")
                    if isinstance(_existing, str):
                        messages[_i]["content"] = (
                            f"[系统附注 — 本回合参考上下文,非用户输入]\n{_turn_ctx}\n"
                            f"[用户消息]\n{_existing}"
                        )
                        _injected = True
                    break
            if not _injected:
                # 兜底:带图多段 content 或无 user 消息 → 退回旧行为拼 system 尾,
                # 宁可损失缓存也绝不丢上下文(fail-open)。
                messages[0]["content"] = f"{messages[0]['content']}\n\n{_turn_ctx}"

        # pre_llm_ms: system-prompt 组装 + KB 检索 + history + vision 到本点的总壁钟。
        # 直接取 start_time delta (最准, 不受漏计阶段影响)。fail-soft。
        try:
            pre_llm_ms = int((time.time() - start_time) * 1000)
        except Exception:  # noqa: BLE001
            pre_llm_ms = 0

        # 4. 工具定义(2026-07-11 token 优化 #2)
        # fast 简单回合(记录/简单查询)只发固定 big-3 白名单:实测工具 prefill
        # 18,064→~6,700 chars(-62%),且缩短 flash 模型 prefill 时延。固定子集
        # 保前缀字节稳定(不拆 provider 前缀缓存)。模型若吐出子集外工具名 →
        # 下面 round loop 里升级回全集重跑该轮(fail-open,绝不静默丢调用)。
        turn_tool_names = _tool_names_for_turn(
            message,
            fast_route=self._fast_route_simple_turn,
            analysis_subset=self._analysis_turn_subset,
        )
        if turn_tool_names is not None:
            tools = get_health_tools(subset=list(turn_tool_names))
        else:
            tools = get_health_tools()
        if health_advice_buffered:
            # The compiler has already selected the frozen personal packet and
            # admitted reviewed authority claims. Synthesis receives no tools:
            # it cannot widen evidence, mutate health state, or fall into a weak
            # tool-decision round before producing the answer.
            tools = []
        if self._turn_attachment_write_receipts:
            blocked_attachment_write_tools = {"upload_medical_exam_text"}
            tools = [
                tool
                for tool in tools
                if (tool.get("function") or {}).get("name")
                not in blocked_attachment_write_tools
            ]
        # 任一真实子集(fast big-3 或 analysis 只读)激活 → 走 withheld-upgrade。
        # health evidence 不是“可升级子集”：它是强制零工具的临床边界。
        tool_subset_active = turn_tool_names is not None

        # 5. Agent 循环
        full_reply = ""
        streamed_cards: list[dict] = []
        post_record_qualities: list[dict] = []
        yield {
            "event": "agent_start",
            "data": {
                "message": "小巴正在分析...",
                # 让客户端在 done 之前就知道本轮会话 ID。
                # 新会话首次发送后如果用户切走页面，回来可以按这个 ID 拉取后端后台任务落库的最终回复。
                "conversation_id": conv.id,
            },
        }

        # 2026-07-01: pre-LLM 阶段计时 SSE (纯埋点, mac 端解析未知 event 会 tolerate)。
        # 在进入 round loop 前发, 客户端可据此先画出 first-token 前的 waterfall。
        yield {
            "event": "perf_pre_llm",
            "data": {
                "pre_llm_ms": pre_llm_ms,
                "stages": dict(pre_stages),
            },
        }

        # 2026-05-13: 计时 + 模型名可观测性 — 每轮 LLM 耗时积累到 done 事件
        llm_rounds_ms: list = []
        model_name: Optional[str] = None
        final_finish_reason: Optional[str] = None
        # 2026-07-01: TTFT + per-round split + orchestrator-as-tool 计时 (纯埋点)。
        first_token_at: Optional[float] = None  # 第一个 token yield 给客户端的时刻
        rounds: List[Dict[str, Any]] = []  # 每轮 {llm_gen_ms, tool_exec_ms, tools:[...]}
        orchestrator_tool_ms: Optional[int] = None  # health_analysis(type=orchestrator) 壁钟
        orchestrator_perf: Optional[Any] = None  # /orchestrator/chat 若回传 perf 则透传
        # rank7 深分析短路二次合成(passthrough,ships-off,见 config.orchestrator_synthesis_passthrough)。
        # 关时全零开销(capture 受 mode!='off' 门控);shadow 记 meta 不改行为;on 单工具回合短路。
        passthrough_mode = _resolve_synthesis_passthrough_mode()
        passthrough_orch_text: Optional[str] = None   # orchestrator 自产 synthesis(已过 R4)
        passthrough_orch_calls = 0                     # 本回合捕获到 synthesis 的 orchestrator 次数
        passthrough_synthesis_round_ms: Optional[int] = None  # shadow: 二次合成轮壁钟(=可省时延)
        passthrough_taken = False                      # on: 本回合是否真短路了二次合成
        # 后置校验: record 意图的 turn 必须真的执行了写工具。0 次 = 模型可能只是
        # 嘴上说"已记录"却没调工具(弱模型把 tool-call 当正文吐出 → 静默丢数据)。
        tool_executed_count = 0
        deterministic_symptom_fallback_attempted = False
        deterministic_diet_correction_fallback_attempted = False
        deterministic_simple_record_fallback_attempted = False
        deterministic_goal_lookup_attempted = False
        goal_verification_attempted = False
        receipt_goal_evaluated = False
        goal_verification_result: Any = None
        goal_lookup_completed = False
        goal_allowed_record_ids: set[str] = set()
        # 本轮 agent 实际调用过的工具/Skill 名, 去重、按首次调用顺序。供 mac/mobile
        # 展示"调用了哪些 Skills"。与 sources_used (引用了哪些数据源) 独立。
        tools_used: List[str] = []
        write_receipts: List[Dict[str, Any]] = []
        write_receipts.extend(self._turn_contextual_diet_receipts)
        write_receipts.extend(self._turn_attachment_write_receipts)
        if self._turn_attachment_write_receipts:
            tools_used.append("medical_report_ocr")
        write_results_by_fingerprint: Dict[str, tuple[str, str]] = {}
        # 只读工具回合级去重(同名+同参已跑过 → 复用结果, 不重复真执行)。回合级 local, 自然重置。
        read_results_by_fingerprint: Dict[str, tuple[str, str]] = {}
        unverified_write_operations: Dict[str, str] = {}
        pending_recoverable_write_rejections: dict[
            str, tuple[str, str]
        ] = {}
        pending_recoverable_write_rejection_rounds: dict[str, int] = {}
        pending_recoverable_write_rejection_scopes: dict[str, str] = {}
        last_recoverable_write_rejection: Optional[str] = None
        last_recoverable_write_rejection_code: Optional[str] = None
        # Slice 3 配方候选: 本轮**成功完成**的 health_record 写步骤 (sanitize 掉
        # 一次性确认标志 + 日期模板化)。≥2 步时 done 附 save_recipe 描述符
        # (仅描述符, 移动端渲染"存为配方"入口; 存不存由用户点)。
        recipe_candidate_steps: List[Dict[str, Any]] = []

        # 诚实的非流式 UX: 若本回合答案模型结构性非流式 (langbridge 商用模型, 上游无 SSE,
        # 整段一次返回), mac 端「正在思考…」的 token 滚动是误导 —— 在每轮 LLM 调用前多发一条
        # thinking 状态, 带 detail「整段生成, 需等待完整回答」, mac 会原样显示该 detail。
        # 流式模型 detail 恒为 None (不发此附加事件), mac 走正常滚动。fail-soft (解析异常=不发)。
        answer_model_non_streaming = self._resolved_answer_model_is_non_streaming()

        # A2 (plan rank4) 自纠开关: 若合成轮被置空 tools 后模型其实还想再调工具
        # (下面 botched 文本式工具调用被识别), 置位 → 本回合后续轮重新带上工具。
        # 正确性 > 省 token: 多轮链式工具回合 (orchestrator 后还想 knowledge_search 等) 不被裁掉。
        keep_tools_after_synthesis_miss = False
        # 可恢复的模型拒答/数据缺口只允许一次恢复，避免重问循环或放宽安全边界。
        model_recovery_attempted = False
        self._http_client = httpx.AsyncClient(timeout=90.0)
        try:
            for round_idx in range(MAX_TOOL_ROUNDS):
                if deterministic_health_release:
                    # Sufficiency is a pre-synthesis policy decision. Clarify,
                    # high/emergency, and authority-miss turns are rendered by
                    # the deterministic verifier, so waiting for a model whose
                    # prose will be discarded only adds latency and cost.
                    full_reply = "本轮由确定性健康策略直接生成。"
                    final_finish_reason = "stop"
                    break
                # 快路由逃生门(见 FAST_ROUTE_ESCALATE_AFTER_ROUNDS 常量注释):整轮快路由用掉
                # N 轮仍未收敛 → 换回强模型跑完剩下的轮。恢复 _request_model_id=None 即回到
                # 快路由介入**前**的默认路由(admin global / user pref)—— 因为快路由本就只在
                # _request_model_id is None 时才接管(:5735),故这是精确还原、不是新路由。
                # 只作用于**整轮**快路由:显式选模型(_request_model_id 由 extra_context 填)
                # 与工具轮快路由(_tool_round_fast_routed,每轮自行判定)都不受影响。
                # 加层不减层:换模型后既有的安全/R4/诚实门原样生效(它们与模型无关)。
                if (
                    self._fast_route_simple_turn
                    and round_idx >= FAST_ROUTE_ESCALATE_AFTER_ROUNDS
                ):
                    self._fast_route_simple_turn = False
                    self._request_model_id = None
                    self._record_model_fallback_reason("fast_route_simple_turn_escalated")
                    logger.warning(
                        "[agent_executor] 快路由 %d 轮未收敛 → 升级强模型 "
                        "user=%s message_chars=%s",
                        round_idx,
                        user_id,
                        len(message or ""),
                    )
                # 真流式调用 LLM：content delta 实时 yield 给客户端,同时累积 tool_calls。
                # _call_llm_stream 内部已做 provider 路由 + failover (镜像 _call_llm)。
                # round_tools = 本轮**发给模型**的工具; _detect_tools = 扫描模型**输出**用的
                # 完整词表 (A2 把合成轮 round_tools 置空只是不再重发 18KB schema, 输出侧的
                # 文本式/内联工具调用抑制词表不能跟着消失 —— 见 _detect_tools 用法)。
                if self._force_no_tools_synthesis:
                    # A3: fast 工具轮直接答文本被丢弃 → 本轮强制无 tools 合成 (强/显式模型),
                    # 走主循环流式路径重合成 (tokens 逐 delta 下发)。
                    round_tools = []
                elif self._should_synthesize_with_requested_model_after_tools(tool_executed_count):
                    # 既有: 显式选的不可靠工具模型, 工具后由它自己产出最终答案 (不重发 tools)。
                    round_tools = []
                elif tool_executed_count > 0 and not keep_tools_after_synthesis_miss:
                    # A2: 上一轮已执行过工具 → 本轮实际是合成轮, 对**所有**模型置空 tools,
                    # 省 ~5k tokens/轮 prefill (18,064-char schema)。2+-round 回合 = 55% 的回合。
                    round_tools = []
                else:
                    round_tools = tools
                # 扫描输出的工具词表: round_tools 非空则用它, 否则回退本回合完整 tools
                # (合成轮词表稳定, 默认路径历来带非空 tools, 这层保护逐字节不变)。
                _detect_tools = round_tools or tools
                # 真实思考过程: 本轮 LLM prefill/decide 等待即将开始 (TTFT 主来源)。
                # synthesis = 前面轮已执行过工具 且 本轮不再带工具 (模型正在写最终答案);
                # 否则 thinking (还在决策/可能再调工具)。纯附加、fail-soft (dict 构造不会抛)。
                if tool_executed_count > 0 and not round_tools:
                    yield self._status_event("synthesis", round=round_idx + 1)
                    # 2026-07-05 P0-1: 进度事件 (flat 契约) —— 最终回答开始生成前发。
                    # 命中条件与既有 synthesis status 一致: 前面轮已跑过工具且本轮不带工具。
                    yield self._progress_event("synthesis")
                else:
                    yield self._status_event("thinking", round=round_idx + 1)
                # 非流式模型: 多发一条带 detail 的 thinking 状态 (整段生成需等待)。
                if answer_model_non_streaming:
                    yield self._status_event(
                        "thinking",
                        detail="该模型整段生成,需等待完整回答",
                        round=round_idx + 1,
                    )
                # rank7 passthrough(on): 本轮是二次合成轮(前面已跑工具、本轮不带 tools),且本回合
                # 唯一实质工具就是那一次 orchestrator health_analysis —— 直接把它已过 R4 的 synthesis
                # 过同一条出站护栏后流式下发,跳过第二次强模型合成。fail-closed:tool_executed_count>1
                # (还需融合记录/查询/二次分析的回合)或非 orchestrator → 落到下面正常二次合成分支。
                if (
                    passthrough_mode == "on"
                    and not round_tools
                    and tool_executed_count == 1
                    and passthrough_orch_calls == 1
                    and passthrough_orch_text
                ):
                    passthrough_final = _apply_passthrough_outbound_guards(
                        passthrough_orch_text, messages
                    )
                    if passthrough_final.strip():
                        if first_token_at is None:
                            first_token_at = time.time()
                        # 内层调用整段一次返回 → 切成 20-char token 让端逐块渲染
                        # (镜像既有非流式兜底口径 4827/5024)。
                        if not health_advice_buffered:
                            for i in range(0, len(passthrough_final), 20):
                                yield {
                                    "event": "token",
                                    "data": {
                                        "content": passthrough_final[i:i + 20]
                                    },
                                }
                        full_reply += passthrough_final
                        passthrough_taken = True
                        # 透传答案是一段完整回答(非待决工具调用)→ finish_reason 与二次合成
                        # 答案路径对齐为 'stop'(completion_status → complete),不留 round1 的
                        # 'tool_calls' 陈值。
                        final_finish_reason = "stop"
                        rounds.append({"llm_gen_ms": 0, "tool_exec_ms": 0, "tools": []})
                        break
                    # 护栏把文本清空(异常)→ 不短路, 落到正常二次合成兜底(下方 else 分支)。
                _round_start = time.time()
                streamed_text = ""
                # 思考流可视化 (qwen reasoning_content): 本轮首个可见 token 之前, 把
                # reasoning 增量节流成 thinking status 事件填死气。纯 UI, 绝不进答案/持久化。
                reasoning_buf = ""
                reasoning_last_emit_at = _round_start
                reasoning_last_emit_len = 0
                streamed_tool_calls: List[Dict[str, Any]] = []
                stream_finish_reason: Optional[str] = None
                streamed_to_client = False
                # 每轮入口重置工具决策轮快路由标记; _call_llm_stream → _resolve_chat_provider
                # → _maybe_fast_route_tool_round 会在本轮命中时置 True (仅带 tools 的轮可能命中)。
                self._tool_round_fast_routed = False
                # 弱模型会把 tool-call JSON 当正文吐出(无结构化 tool_calls)。一旦累积
                # 文本可被 _extract_inline_tool_call 识别成工具调用,立刻停止 live 下发
                # 并撤回已发标记 —— 这段 JSON 后面会被恢复成真正的 tool_call (content 置空),
                # 绝不能泄漏给用户。结构化 tool_calls 的正常模型不受影响。
                inline_suppressed = False
                recoverable_response_buffered = False
                async for evt in self._call_llm_stream(messages, round_tools):
                    etype = evt.get("type")
                    if etype == "content":
                        delta = evt.get("text") or ""
                        if not delta:
                            continue
                        streamed_text += delta
                        if (
                            not recoverable_response_buffered
                            and should_buffer_recovery_response(streamed_text)
                        ):
                            # 先不把可能需要恢复的道歉式拒答发到客户端。
                            recoverable_response_buffered = True
                        if (
                            not inline_suppressed
                            and not streamed_tool_calls
                            and _detect_tools
                            and (
                                _extract_inline_tool_call(
                                    streamed_text,
                                    _detect_tools,
                                    user_message=message,
                                )
                                # 括号标记 `[工具调用: ...` 可能正在逐 token 形成,`)` 还没到
                                # → 上面的精确解析此刻 match 不到。一旦看到标记前缀就提前抑制,
                                # 避免裸标记被逐 delta 泄漏(即便最终参数解析不出也不外漏)。
                                or "工具调用" in streamed_text
                                # Markdown 清单式 "Tool calls:" 同样抑制(英文标记)。
                                or _TEXT_TOOLCALL_PREFIX_RE.search(streamed_text)
                                # XML `<invoke ...` / `<minimax:tool_call>` 逐 token 形成中,
                                # `</invoke>` 闭标签还没到 → 精确解析 match 不到。见到前缀即抑制。
                                or _XML_TOOLCALL_PREFIX_RE.search(streamed_text)
                                # call{ / <call: / {name: 行首前导(qwen 畸形文本工具调用泄漏)
                                or _TEXTCALL_LEAK_PREFIX_RE.search(streamed_text)
                                # 裸 `health_manage(` 在闭括号到达前也要从首 token 抑制。
                                or _starts_like_bare_registered_tool_call(streamed_text, _detect_tools)
                            )
                        ):
                            # 检测到内联工具调用(JSON 或括号标记) → 进入抑制模式,本轮不再 live 下发。
                            inline_suppressed = True
                            streamed_to_client = False
                        # 合成轮(round_tools 空)弱模型把工具结果原始 JSON 数组粘进 QUERY 回答
                        # (`让我查一下…[{"record_date":...,"meal_type":...}]`)。上面那条 gate 在
                        # round_tools 上,合成轮跳过它 → 这里独立、不依赖 round_tools 做锚定检测。
                        # 用"泄漏正在形成"的早停版本(不等整段 JSON 可解析):一见到 JSON 结构起
                        # + 带引号冒号的白名单字段键就抑制,把逐 token 泄漏压到最多一两个 delta。
                        # 锚定到真实字段名(非"任何 JSON"),且遇 fenced 块直接豁免,详见谓词。
                        if (
                            not inline_suppressed
                            and not streamed_tool_calls
                            and _streaming_leak_forming(streamed_text)
                        ):
                            inline_suppressed = True
                            streamed_to_client = False
                        # 记录意图整轮快路由 + 尚无工具执行: content 绝不 live 下发。
                        # 生产实锤(2026-07-17, user=3 ×2/24h): 弱模型对「麦当劳店记录打了一个
                        # 喷嚏。」直接吐出「✅ **症状已记录**:打喷嚏(上午 09:21)」却**一个工具都没调**
                        # (它调的是只读 health_query) → 用户看到绿对勾, 不会重记, 那条症状永久丢失。
                        # :7228 的诚实覆盖(final_text=_record_intent_needs_detail_message +
                        # streamed_to_client=False)本身是对的, 但它跑在 token 已经 yield 出去之后 ——
                        # 只改了落库消息, **救不回已经流到屏幕上的字**。故必须在下发前就抑制:
                        # 工具真跑过(tool_executed_count>0)之后的轮照常 live 流(那时"已记录"才是真的)。
                        # 与上面 _tool_round_fast_routed 同一范式(先抑制、后按真实结果补发)。
                        _record_claim_unverified = bool(
                            self._prefer_fast_record_model and not write_receipts
                        )
                        _diet_correction_claim_unverified = (
                            partial_diet_correction_requested
                            and not write_receipts
                        )
                        # Mutation turns remain buffered for the whole model round.
                        # A later tool call in the same turn may still fail even
                        # after an earlier write produced a verified receipt.
                        _mutation_claim_unverified = write_action_requested
                        # 工具决策轮快路由 (fast 模型): 本轮输出只当工具决策, content 绝不
                        # live 下发 —— 若最终是直接答文本 (无 tool_calls), 会被丢弃并在强模型
                        # 重合成 (安全不变量: 面向用户的医疗正文绝不来自 fast 模型)。
                        if (
                            not inline_suppressed
                            and not health_advice_buffered
                            and not self._tool_round_fast_routed
                            and not _record_claim_unverified
                            and not _diet_correction_claim_unverified
                            and not _mutation_claim_unverified
                            and not recoverable_response_buffered
                        ):
                            streamed_to_client = True
                            # 2026-07-01: TTFT — 第一个真正下发给客户端的 token 时刻 (纯埋点)。
                            if first_token_at is None:
                                first_token_at = time.time()
                            # 真流式:逐 delta 即时下发,不再切 20-char 假块。
                            yield {"event": "token", "data": {"content": delta}}
                    elif etype == "reasoning":
                        # 思考流可视化: 把 qwen 的 reasoning_content 增量节流成既有
                        # thinking status 事件, 填掉首个可见 token 前的死气。
                        # reasoning 文本绝不进 streamed_text/full_reply/messages/持久化答案 ——
                        # 只塞进 status 事件的 detail (客户端已有的 live 思考通道)。
                        # 门控 (全部满足才发一条):
                        #   1. 本轮尚未产出任何可见 content —— 答案流一开始就交棒停发;
                        #   2. 非 fast 工具决策轮 —— fast 模型内部文本不外 surface (安全不变量);
                        #   3. 距上次发 ≥ 间隔 且 新增 reasoning ≥ 字符阈值 (whichever later);
                        #   4. 累积 reasoning 未形成工具结果 JSON 泄漏 (复用 _streaming_leak_forming);
                        #   5. 清洗后片段非空。
                        if (
                            health_advice_buffered
                            or streamed_text
                            or self._tool_round_fast_routed
                        ):
                            continue
                        rdelta = evt.get("text") or ""
                        if not rdelta:
                            continue
                        reasoning_buf += rdelta
                        _now = time.time()
                        if (
                            (_now - reasoning_last_emit_at) >= _REASONING_STATUS_MIN_INTERVAL_S
                            and (len(reasoning_buf) - reasoning_last_emit_len)
                            >= _REASONING_STATUS_MIN_CHARS
                            and not _streaming_leak_forming(reasoning_buf)
                        ):
                            _snippet = _clean_reasoning_snippet(reasoning_buf)
                            if _snippet:
                                reasoning_last_emit_at = _now
                                reasoning_last_emit_len = len(reasoning_buf)
                                yield self._status_event(
                                    "thinking", detail=_snippet, round=round_idx + 1
                                )
                    elif etype == "tool_calls":
                        streamed_tool_calls = evt.get("tool_calls") or []
                    elif etype == "finish":
                        stream_finish_reason = evt.get("finish_reason")
                # 把流式结果整理成与 _call_llm 等价的 response dict, 复用后续既有逻辑
                # (inline tool 恢复 / tool 执行 / 空回复重试)。
                response: Any = {
                    "content": streamed_text,
                    "finish_reason": stream_finish_reason,
                }
                if streamed_tool_calls:
                    response["tool_calls"] = streamed_tool_calls
                final_finish_reason = stream_finish_reason or final_finish_reason
                _round_llm_gen_ms = int((time.time() - _round_start) * 1000)
                llm_rounds_ms.append(_round_llm_gen_ms)
                # 2026-07-01: per-round split — 本轮 LLM 生成耗时 (纯埋点)。tool_exec_ms /
                # tools 在下面工具执行块填充; 无工具调用的最终答案轮 tool_exec_ms=0。
                _round_tool_exec_ms = 0
                _round_tool_names: List[str] = []
                if model_name is None:
                    if self._last_provider_model_name:
                        model_name = self._last_provider_model_name
                    else:
                        try:
                            # 2026-05-14: 显示给前端看的 model name 也走用户偏好
                            # (之前 bug: get_llm_provider() 是全局, 用户切了仍显示 MiniMax)
                            if self._request_model_id:
                                from app.services.llm.model_registry import get_model
                                entry = get_model(self._request_model_id)
                                model_name = entry.model if entry else self._request_model_id
                            elif self._current_user_id:
                                from app.services.llm.factory import create_provider_for_user
                                p = create_provider_for_user(self._current_user_id, self.db)
                                model_name = getattr(p, "model", None) or getattr(p, "default_model", None) or getattr(p, "provider_name", None)
                            else:
                                from app.services.llm.factory import get_llm_provider
                                p = get_llm_provider()
                                model_name = getattr(p, "model", None) or getattr(p, "default_model", None) or getattr(p, "provider_name", None)
                        except Exception:
                            pass
                response_is_dict = isinstance(response, dict)
                response_tool_calls = response.get("tool_calls") if response_is_dict else None
                response_content = response.get("content") if response_is_dict else None
                logger.info(
                    "LLM response type=%s is_dict=%s has_tool_calls=%s "
                    "tool_call_count=%s content_chars=%s",
                    type(response).__name__,
                    response_is_dict,
                    bool(response_tool_calls),
                    len(response_tool_calls) if isinstance(response_tool_calls, list) else 0,
                    len(str(response_content or "")),
                )

                if (
                    health_advice_buffered
                    and isinstance(response, dict)
                    and response.get("tool_calls")
                ):
                    # A provider can hallucinate structured calls even when sent
                    # tools=[]. Health synthesis is a sealed evidence envelope:
                    # never upgrade to the full tool set and never execute a
                    # model-authored read/write call.
                    logger.warning(
                        "[health_evidence] discarded model tool calls user=%s count=%s",
                        user_id,
                        len(response.get("tool_calls") or []),
                    )
                    response = {
                        **response,
                        "content": "本轮模型未生成可发布的健康回答。",
                        "tool_calls": [],
                        "finish_reason": "stop",
                    }

                if isinstance(response, dict) and not response.get("tool_calls"):
                    _resp_content = response.get("content") or ""
                    # 数据完整性硬门:**数组形工具结果回显**(`[{` + 白名单字段键)绝不参与
                    # inline 工具调用恢复 —— 查询结果 record 形字段会被误认成 health_record
                    # 写意图,把用户已有记录重复写一遍(测试实测:泄漏回显被恢复成
                    # health_record ×7)。写意图 payload 是单对象({"record_type":...}),
                    # 工具结果是数组,形态可区分;只挡数组形,合法弱模型写恢复不受影响。
                    _is_result_echo = bool(
                        re.search(r"\[\s*\{", _resp_content)
                        and _QUOTED_ALLOWLIST_KEY_RE.search(_resp_content)
                    )
                    inline_tool_call = (
                        None if _is_result_echo
                        else _extract_inline_tool_call(
                            _resp_content,
                            _detect_tools,
                            user_message=message,
                        )
                    )
                    if inline_tool_call:
                        logger.warning(
                            "[agent_executor] recovered inline tool JSON as tool_call: %s",
                            inline_tool_call["function"]["name"],
                        )
                        response = {
                            **response,
                            "content": "",
                            "finish_reason": "tool_calls",
                            "tool_calls": [inline_tool_call],
                        }

                # 模型把工具调用写成 Markdown 文本(`Tool calls:\n- health_query`)、无结构化调用
                # 也无参数可解析 → 不能当最终答案(否则零数据 + 泄漏标记)。本代理大多数时候能正确
                # 结构化(日志大量 has_tool_calls=True),只是偶发降级 → 重提示一次让它用结构化重试。
                if (
                    isinstance(response, dict)
                    and not response.get("tool_calls")
                    and _is_botched_text_tool_call(response.get("content") or "", _detect_tools)
                ):
                    botched = response.get("content") or ""
                    if round_idx < MAX_TOOL_ROUNDS - 1:
                        if not round_tools:
                            # A2 自纠: 本轮已被 A2/合成条件置空 tools, 但模型仍想调工具
                            # (文本式)。重开工具, 让重提示轮真能结构化调用 (否则重提示后
                            # 仍无 tools = 空转)。正确性 > 省 token。
                            keep_tools_after_synthesis_miss = True
                        logger.warning(
                            "[agent_executor] 文本式工具调用未结构化, 重提示重试 "
                            "(round %d). chars=%s",
                            round_idx + 1,
                            len(botched),
                        )
                        messages.append({"role": "assistant", "content": botched})
                        messages.append({"role": "user", "content": (
                            "你刚才把工具调用写成了文本(例如 \"Tool calls:\\n- health_query\"),"
                            "并没有真正调用工具,所以没有任何数据返回。请立刻用结构化 function calling "
                            "真正调用所需工具并带上正确参数(例如查看补剂库用 health_query 且 "
                            "dimension=\"supplements\"),不要再输出 \"Tool calls:\" 这类文本。"
                        )})
                        continue  # 进入下一轮,模型用结构化 tool_calls 重试
                    # 轮次用尽仍是文本式 → 剥掉标记避免泄漏(用户至少不看到裸 "Tool calls:")。
                    response = {**response, "content": _strip_text_tool_call(botched)}

                # 确定性症状写入兜底:当前用户句子已经被分类为明确症状陈述,
                # 但模型只返回文字/只读查询时,不能把这条症状降级成“还没记下来”。
                # 合成一个最小 health_record 调用,仍沿用下方完整的 validator、
                # ToolGateway、write_state、receipt 和安全检查;只尝试一次,避免
                # 上游返回异常时产生重复写入。问题句(如“腰疼怎么办”)不会命中
                # _extract_clear_symptom_record,仍保持建议路径。
                if (
                    not health_advice_buffered
                    and isinstance(response, dict)
                    and not response.get("tool_calls")
                    and not deterministic_simple_record_fallback_attempted
                ):
                    deterministic_simple_record_call = (
                        _build_deterministic_simple_record_tool_call(
                            (
                                self._agent_kernel_snapshot.goal
                                if self._agent_kernel_snapshot is not None else None
                            ),
                            write_receipts=write_receipts,
                            has_attachment=bool(images or file_base64),
                        )
                    )
                    if deterministic_simple_record_call:
                        deterministic_simple_record_fallback_attempted = True
                        response = {
                            **response,
                            "content": "",
                            "finish_reason": "tool_calls",
                            "tool_calls": [deterministic_simple_record_call],
                        }
                        logger.info(
                            "[agent_executor] deterministic simple record fallback "
                            "user=%s record_type=%s",
                            user_id,
                            (
                                self._agent_kernel_snapshot.goal.target_record_type
                                if self._agent_kernel_snapshot is not None
                                and self._agent_kernel_snapshot.goal is not None
                                else "unknown"
                            ),
                        )

                if (
                    not health_advice_buffered
                    and isinstance(response, dict)
                    and not response.get("tool_calls")
                    and not deterministic_goal_lookup_attempted
                ):
                    deterministic_goal_call = _build_deterministic_goal_lookup_tool_call(
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        write_receipts=write_receipts,
                        has_attachment=bool(images or file_base64),
                    )
                    if deterministic_goal_call:
                        deterministic_goal_lookup_attempted = True
                        response = {
                            **response,
                            "content": "",
                            "finish_reason": "tool_calls",
                            "tool_calls": [deterministic_goal_call],
                        }

                if (
                    not health_advice_buffered
                    and isinstance(response, dict)
                    and not response.get("tool_calls")
                ):
                    verification_call = _build_goal_verification_tool_call(
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        write_receipts=write_receipts,
                        already_attempted=goal_verification_attempted,
                    )
                    if verification_call:
                        goal_verification_attempted = True
                        response = {
                            **response,
                            "content": "",
                            "finish_reason": "tool_calls",
                            "tool_calls": [verification_call],
                        }

                if (
                    not health_advice_buffered
                    and isinstance(response, dict)
                    and not response.get("tool_calls")
                    and not deterministic_diet_correction_fallback_attempted
                ):
                    deterministic_diet_call = (
                        _build_deterministic_diet_correction_tool_call(
                            message,
                            write_receipts=write_receipts,
                            has_attachment=bool(images or file_base64),
                            reference_now=self._agent_kernel_reference_now(),
                        )
                    )
                    if deterministic_diet_call:
                        deterministic_diet_correction_fallback_attempted = True
                        response = {
                            **response,
                            "content": "",
                            "finish_reason": "tool_calls",
                            "tool_calls": [deterministic_diet_call],
                        }
                        logger.info(
                            "[agent_executor] deterministic diet correction fallback "
                            "user=%s message_chars=%s",
                            user_id,
                            len(message or ""),
                        )

                if (
                    isinstance(response, dict)
                    and not response.get("tool_calls")
                    and goal_verification_attempted
                    and goal_verification_result is not None
                ):
                    postcondition = verify_goal_postconditions(
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        write_receipts=write_receipts,
                        verification_result=goal_verification_result,
                    )
                    if self._agent_kernel_event_bus is not None:
                        self._agent_kernel_event_bus.goal_evaluated(
                            satisfied=postcondition.satisfied,
                            verified_target_count=len(
                                postcondition.verified_resource_ids
                            ),
                            reason=postcondition.reason,
                        )
                    if not postcondition.satisfied:
                        response = {
                            **response,
                            "content": (
                                "更新操作已执行，但读回核验未覆盖全部目标餐次，"
                                "因此本轮不能确认已经全部完成。请重试，系统会继续核对现有记录。"
                            ),
                        }

                goal = (
                    self._agent_kernel_snapshot.goal
                    if self._agent_kernel_snapshot is not None else None
                )
                if (
                    isinstance(response, dict)
                    and not response.get("tool_calls")
                    and not receipt_goal_evaluated
                    and goal is not None
                    and goal.kind == "simple_health_record"
                    and write_receipts
                ):
                    receipt_goal_evaluated = True
                    postcondition = verify_goal_postconditions(
                        goal,
                        write_receipts=write_receipts,
                        verification_result=None,
                    )
                    if self._agent_kernel_event_bus is not None:
                        self._agent_kernel_event_bus.goal_evaluated(
                            satisfied=postcondition.satisfied,
                            verified_target_count=len(
                                postcondition.verified_resource_ids
                            ),
                            reason=postcondition.reason,
                        )
                    if not postcondition.satisfied:
                        response = {
                            **response,
                            "content": (
                                "记录请求已执行，但没有取得与目标类型一致的可验证回执，"
                                "因此本轮不能确认已经完成。请重试。"
                            ),
                        }

                if (
                    not health_advice_buffered
                    and isinstance(response, dict)
                    and not response.get("tool_calls")
                    and not deterministic_symptom_fallback_attempted
                ):
                    deterministic_symptom_call = _build_deterministic_symptom_tool_call(
                        message,
                        write_receipts=write_receipts,
                        has_attachment=bool(images or file_base64),
                    )
                    if deterministic_symptom_call:
                        deterministic_symptom_fallback_attempted = True
                        response = {
                            **response,
                            "content": "",
                            "finish_reason": "tool_calls",
                            "tool_calls": [deterministic_symptom_call],
                        }
                        logger.info(
                            "[agent_executor] deterministic symptom write fallback "
                            "user=%s message_chars=%s",
                            user_id,
                            len(message or ""),
                        )

                # ──── 工具决策轮快路由安全兜底: fast 模型直接答文本时丢弃, 强模型重合成 ────
                # 到这里所有 tool-call 恢复 (结构化 / inline JSON / 文本式重试) 都已尝试完。
                # 若本轮是 fast 工具决策轮却仍**没有** tool_calls 而是产出了用户可见正文,
                # 那是 fast 模型在直接回答医疗问题 —— 安全不变量禁止 (面向用户医疗正文绝不
                # 来自 fast 模型)。该 content 已被上面的下发门控抑制 (从未 live 发出)。
                # A3 (2026-07-12): 不再清空 content 落到**非流式**空回复重试链 (ttft≈total 空洞:
                # 生产 turn 5960 ttft 39.5s ≈ total) —— 改为置 _force_no_tools_synthesis + continue,
                # 让主循环下一轮以**无 tools 合成轮**在强/显式模型上流式重合成 (round_tools=[] →
                # pass_tools falsy → 不再快路由; _tool_round_fast_routed 在轮首重置 → tokens 不被
                # 抑制; 主循环既有 leak 抑制照旧生效)。fast 正文从未进 messages/full_reply。
                if (
                    self._tool_round_fast_routed
                    and isinstance(response, dict)
                    and not response.get("tool_calls")
                    and (response.get("content") or "").strip()
                ):
                    logger.info(
                        "[agent_executor] fast tool-round answered directly (no tool_call); "
                        "discarding fast-model text, streaming re-synthesis on strong/selected model."
                    )
                    self._record_model_fallback_reason("fast_tool_round_direct_answer_resynthesized")
                    # 记本 fast 轮的 per-round split (纯埋点, 无工具执行)。
                    rounds.append({
                        "llm_gen_ms": _round_llm_gen_ms,
                        "tool_exec_ms": 0,
                        "tools": [],
                    })
                    self._force_no_tools_synthesis = True
                    continue

                # 检查是否有 tool_call
                if isinstance(response, dict) and response.get("tool_calls"):
                    self._record_tool_model_name(self._last_provider_model_name or model_name)
                    tool_calls = response["tool_calls"]
                    proposed_tool_calls = list(tool_calls)
                    text_content = response.get("content") or ""

                    # 工具子集守卫(token 优化 #2 fast + R5 analysis):模型想调的工具不在
                    # 已发子集(意图误判/幻觉工具名/分析轮要写)→ 升级回全集重跑本轮。fail-open:
                    # 绝不因裁剪静默丢调用或喂"未知工具"错误。
                    if tool_subset_active:
                        # 双发防护:fast 轮正文被 _tool_round_fast_routed 抑制(未 live 下发)→ 重跑安全;
                        # analysis 轮正文 live 流式,本轮已发可见正文再重跑会双发 → fallthrough 不重跑。
                        _withheld, _action = _tool_subset_withheld_upgrade(
                            tool_calls, tools,
                            live_text_already_sent=(
                                bool(streamed_text.strip())
                                and not self._tool_round_fast_routed
                            ),
                        )
                        if _action == "fallthrough":
                            logger.warning(
                                "[agent_executor] 工具子集升级但本轮已 live 流式正文,"
                                "放行不重跑避免双发 (模型请求: %s)", _withheld,
                            )
                            tool_subset_active = False  # 本轮后不再守卫,被扣工具按 name 执行
                        elif _action == "rerun":
                            logger.info(
                                "[agent_executor] 工具子集升级回全集重跑本轮 (模型请求: %s)",
                                _withheld,
                            )
                            tools = get_health_tools()
                            if self._turn_attachment_write_receipts:
                                tools = [
                                    tool
                                    for tool in tools
                                    if (tool.get("function") or {}).get("name")
                                    != "upload_medical_exam_text"
                                ]
                            tool_subset_active = False
                            self._record_model_fallback_reason("tool_subset_upgraded_full_tools")
                            continue

                    tool_calls = self._normalize_query_only_health_manage_tool_calls(
                        tool_calls,
                    )
                    tool_calls = await self._normalize_latest_diet_delete_tool_calls(
                        tool_calls,
                        user_auth_token,
                    )
                    tool_calls = await self._normalize_explicit_diet_update_tool_calls(
                        tool_calls,
                        user_auth_token,
                    )
                    tool_calls = _normalize_goal_guarded_tool_calls(
                        tool_calls,
                        (
                            self._agent_kernel_snapshot.goal
                            if self._agent_kernel_snapshot is not None else None
                        ),
                        lookup_completed=goal_lookup_completed,
                        allowed_record_ids=goal_allowed_record_ids,
                    )
                    rejected_goal_writes = _goal_guard_rejected_writes(
                        proposed_tool_calls,
                        tool_calls,
                    )
                    for rejected_tool_name, rejected_args in rejected_goal_writes:
                        self._persist_turn_write_state(
                            user_msg,
                            status="rejected",
                            tool_name=rejected_tool_name,
                            parsed_args=rejected_args,
                        )
                    if proposed_tool_calls and not tool_calls:
                        logger.warning(
                            "[agent_executor] all model tool calls were blocked by "
                            "the goal contract; recovering with a text-only answer "
                            "user=%s rejected_writes=%s",
                            user_id,
                            len(rejected_goal_writes),
                        )
                        if text_content.strip():
                            messages.append({
                                "role": "assistant",
                                "content": text_content,
                            })
                        messages.append({
                            "role": "user",
                            "content": _GOAL_GUARD_RECOVERY_PROMPT,
                        })
                        rounds.append({
                            "llm_gen_ms": _round_llm_gen_ms,
                            "tool_exec_ms": 0,
                            "tools": [],
                        })
                        self._force_no_tools_synthesis = True
                        keep_tools_after_synthesis_miss = False
                        continue

                    self._prepare_medication_tool_plan(tool_calls)

                    planned_writes: List[tuple[str, Dict[str, Any]]] = []
                    for tc in tool_calls:
                        planned_name = tc["function"]["name"]
                        planned_args = tc["function"]["arguments"]
                        if self._prefer_fast_record_model:
                            planned_args = _auto_confirm_fast_record_args(
                                planned_name,
                                planned_args,
                                channel=self._turn_channel,
                                user_message=self._current_turn_user_message,
                            )
                        parsed_planned_args = _parse_tool_arguments_for_telemetry(planned_args)
                        parsed_planned_args = _recover_clear_symptom_args(
                            parsed_planned_args,
                            self._current_turn_user_message,
                        )
                        if (
                            planned_name in _WRITE_RECEIPT_TOOL_NAMES
                            and _write_tool_attempted(
                                planned_name,
                                parsed_planned_args,
                            )
                        ):
                            planned_writes.append(
                                (planned_name, parsed_planned_args)
                            )
                    self._persist_turn_expected_writes(user_msg, planned_writes)

                    # 只读收敛护栏: 若本轮 tool_calls **全是**"本回合已跑过"的只读调用(模型空转
                    # 重发同参 health_query 等)→ 本轮复用结果后强制进合成轮, 停住 loop(否则会
                    # 一直空转到 MAX_TOOL_ROUNDS)。用**执行前**的 read_results_by_fingerprint 判定。
                    planned_reads_all_seen = (
                        _READ_DEDUP_ENABLED
                        and bool(tool_calls)
                        and all(
                            _is_seen_readonly_call(tc, read_results_by_fingerprint)
                            for tc in tool_calls
                        )
                    )

                    # 思考过程: 真流式下已逐 delta 下发过, 这里只补 full_reply,
                    # 不重复 yield token (避免客户端看到双份)。inline-recovery 路径
                    # 会把 content 置空 → text_content 为空也不发。
                    # fast 工具决策轮: 该轮 content (工具调用前的 preamble) 也来自 fast 模型,
                    # 不下发、不计入 full_reply —— 最终医疗正文由后续合成轮的强模型产出。
                    if (
                        text_content
                        and not self._tool_round_fast_routed
                        and not write_action_requested
                    ):
                        if not streamed_to_client and not health_advice_buffered:
                            yield {"event": "token", "data": {"content": text_content}}
                        full_reply += text_content

                    # 追加 assistant message（含 tool_calls）
                    messages.append({
                        "role": "assistant",
                        "content": text_content,
                        "tool_calls": tool_calls,
                    })

                    # 执行每个工具
                    # 2026-07-01: per-round tool_exec 壁钟起点 (纯埋点, 串行执行的墙钟)。
                    _round_tool_start = time.time()
                    for tc in tool_calls:
                        func_name = tc["function"]["name"]
                        func_args = tc["function"]["arguments"]
                        # 收集工具名 (去重、按首次调用顺序) 供 done/meta 的 tools_used。
                        if func_name and func_name not in tools_used:
                            tools_used.append(func_name)
                        if func_name:
                            _round_tool_names.append(func_name)
                        if self._prefer_fast_record_model:
                            func_args = _auto_confirm_fast_record_args(
                                func_name,
                                func_args,
                                channel=self._turn_channel,
                                user_message=self._current_turn_user_message,
                            )
                        parsed_tool_args = _parse_tool_arguments_for_telemetry(func_args)
                        parsed_tool_args = _recover_clear_symptom_args(
                            parsed_tool_args,
                            self._current_turn_user_message,
                        )
                        write_attempted = (
                            func_name in _WRITE_RECEIPT_TOOL_NAMES
                            and _write_tool_attempted(func_name, parsed_tool_args)
                        )
                        write_fingerprint = (
                            _write_operation_fingerprint(func_name, parsed_tool_args)
                            if write_attempted else None
                        )
                        runtime_write_fingerprint = (
                            _runtime_write_operation_fingerprint(
                                func_name,
                                parsed_tool_args,
                                default_record_date=(
                                    self._agent_kernel_reference_now().strftime("%Y-%m-%d")
                                ),
                            )
                            if write_attempted else None
                        )
                        recoverable_write_key = (
                            _recoverable_write_operation_key(
                                func_name,
                                parsed_tool_args,
                                default_record_date=(
                                    self._agent_kernel_reference_now()
                                    .date()
                                    .isoformat()
                                ),
                            )
                            if write_attempted else None
                        )
                        replayed_write = bool(
                            write_fingerprint
                            and write_fingerprint in write_results_by_fingerprint
                        )
                        # 只读去重: 只对只读工具(与写集天然不相交, belt-and-suspenders 再排一次写集)。
                        read_attempted = (
                            _READ_DEDUP_ENABLED
                            and _tool_call_is_read_only(
                                func_name,
                                parsed_tool_args,
                            )
                        )
                        read_fingerprint = (
                            _read_operation_fingerprint(func_name, parsed_tool_args)
                            if read_attempted else None
                        )
                        replayed_read = bool(
                            read_fingerprint
                            and read_fingerprint in read_results_by_fingerprint
                        )
                        tool_id = tc["id"]

                        # 通知前端正在执行工具
                        yield {
                            "event": "tool_call",
                            "data": {
                                "tool": func_name,
                                "args": func_args if isinstance(func_args, str) else json.dumps(func_args, ensure_ascii=False),
                                "round": round_idx + 1,
                            },
                        }
                        # 真实思考过程: 本工具即将在串行循环里执行 (short 中文名给"正在……"胶囊)。
                        # 纯附加、fail-soft (dict 构造不会抛)。与上面 tool_call (带 args, UI 用)
                        # 独立: status 走思考过程可视化通道, 客户端可只订阅其一。
                        yield self._status_event(
                            "tool", detail=_tool_status_label(func_name), round=round_idx + 1
                        )
                        # 2026-07-05 P0-1: 进度事件 (flat 契约) —— 每轮工具执行前发,
                        # label 来自确定性映射表 (完整人话动词短语)。纯附加。
                        yield self._progress_event(
                            "tool", round=round_idx + 1, label=_tool_progress_label(func_name)
                        )
                        # 2026-05-14: tool_call 加进 sources_used
                        _tool_label = _TOOL_TO_SOURCE_LABEL.get(func_name)
                        if _tool_label and _tool_label not in sources_used:
                            sources_used.append(_tool_label)

                        # 执行工具
                        # 2026-07-01: 若本工具是 health_analysis(type=orchestrator) → 捕获其
                        # 单工具壁钟给 orchestrator_tool_ms; best-effort 从 result JSON 透传 perf。
                        _is_orch_tool = (
                            func_name == "health_analysis"
                            and parsed_tool_args.get("analysis_type") == "orchestrator"
                        )
                        if write_attempted and not replayed_write:
                            # A4: 本回合发生 Twin-mutating 写 (health_record/health_manage/
                            # intervention_cycle) → done 侧 KB 证据卡强制重算 (反映写后 Twin,
                            # 不复用 pre-round-1 memo)。保守: 即便写最终软失败也重算 (无害多一次)。
                            self._turn_twin_write_occurred = True
                        _tool_call_start = time.time()
                        if replayed_write:
                            result, result_for_record_card = (
                                write_results_by_fingerprint[write_fingerprint]
                            )
                        elif replayed_read:
                            # 同名+同参只读调用本回合已跑过 → 复用结果, 不重复真执行(省空转)。
                            result, result_for_record_card = (
                                read_results_by_fingerprint[read_fingerprint]
                            )
                        else:
                            # Wave 2: 心跳 + per-tool 超时(慢工具不再冻结转圈/被 nginx 掐断)。
                            result = None
                            async for _hb_kind, _hb_val in self._run_tool_with_progress(
                                func_name, func_args, user_auth_token,
                                _tool_progress_label(func_name),
                            ):
                                if _hb_kind == "heartbeat":
                                    yield _hb_val
                                else:
                                    result = _hb_val
                            result_for_record_card = result
                        if _is_orch_tool:
                            try:
                                orchestrator_tool_ms = int((time.time() - _tool_call_start) * 1000)
                            except Exception:  # noqa: BLE001
                                orchestrator_tool_ms = None
                            try:
                                _orch_json = json.loads(result) if isinstance(result, str) else None
                                if isinstance(_orch_json, dict):
                                    if _orch_json.get("perf") is not None:
                                        orchestrator_perf = _orch_json.get("perf")
                                    # rank7: 捕获 orchestrator 自产 synthesis(已过 _safety_wrap/R4)
                                    # 供 shadow 记录 / on 短路。仅在 flag 非 off 时捕获(off 零开销)。
                                    if passthrough_mode != "off":
                                        _synth = _orch_json.get("synthesis")
                                        if isinstance(_synth, str) and _synth.strip():
                                            passthrough_orch_text = _synth
                                            passthrough_orch_calls += 1
                            except Exception:  # noqa: BLE001
                                pass
                        safety_cards: list[dict] = []
                        if not replayed_write and not replayed_read:
                            tool_executed_count += 1
                            # 旁路给 _maybe_fast_route_tool_round: 一旦跑过工具, 后续 (合成) 轮
                            # 即便仍带 tools 也不再降 fast (留在强模型产出医疗正文)。
                            self._turn_any_tool_executed = True

                        # 写操作成功后内联安全检查。
                        # 注意: 软失败(如"未找到…"/"暂时没成功")不含 "Error" 字样, 旧逻辑会把
                        # 无关的安全告警拼到一条失败回复上(截图里"未找到活跃药物 ⚠️夜间血氧…"),
                        # 故显式排除软失败。
                        _soft_fail = any(m in result for m in ("未找到", "暂时没成功", "没成功", "记录失败"))
                        if (
                            not replayed_write
                            and
                            # 写后内联安全筛查覆盖**所有**写工具(health_record/health_manage/
                            # intervention_cycle), 不只 health_record。此前按 func_name=="health_record"
                            # 判定 →「把刚才那条血压改成 190/120」走 health_manage(update) 漏筛
                            # (under-alarm: 严重血压读数零告警)。_write_tool_completed 精确判"确有可
                            # 验证写回执"(operation=list / 读操作不触发), 与配方重放路径 any_write 同源。
                            _write_tool_completed(func_name, parsed_tool_args, result)
                            and "Error" not in result
                            and not result.startswith("[NEEDS_CONFIRMATION]")
                            and not _soft_fail
                        ):
                            try:
                                from app.twin.builder import build_twin
                                from app.agents.safety_guardian import evaluate_safety
                                twin = build_twin(self.db, user_id, use_cache=True)
                                report = evaluate_safety(twin)
                                critical = [a for a in report.alerts if int(a.severity) >= 3]
                                if critical:
                                    alert_msgs = "; ".join(a.title for a in critical[:3])
                                    safety_cards = [
                                        card for card in (
                                            _safety_alert_card_descriptor(a)
                                            for a in critical[:3]
                                        )
                                        if card
                                    ]
                                    result += f"\n\n⚠️ 安全提示: {alert_msgs}"
                            except Exception as e:
                                # 安全筛查是记录后的确定性护栏 —— 它抛错绝不能静默"已记录"放行
                                # (否则刚记的血压危象/卒中症状零告警)。fail-loud:ERROR + 兜底提醒。
                                logger.error("Safety check after write failed: %s", e, exc_info=True)
                                result += (
                                    "\n\n⚠️ 安全提示: 记录已保存,但自动安全筛查暂未完成。"
                                    "如你此刻有明显不适、或刚记录的数值明显异常,请及时就医。"
                                )
                        if write_fingerprint and not replayed_write:
                            write_results_by_fingerprint[write_fingerprint] = (
                                result,
                                result_for_record_card,
                            )
                            # 回合内写后失效读缓存: 写→同参"列出"应含该写, 不复用写前陈旧读
                            # (安全评审 fast-follow; 自然顺序是先写后读=新鲜, 此处兜住 read→write→read)。
                            read_results_by_fingerprint.clear()
                        if read_fingerprint and not replayed_read:
                            read_results_by_fingerprint[read_fingerprint] = (
                                result,
                                result_for_record_card,
                            )
                        if (
                            func_name == "health_manage"
                            and parsed_tool_args.get("record_type") == "diet"
                            and parsed_tool_args.get("operation") == "list"
                            and not str(result or "").startswith("Error")
                        ):
                            goal_lookup_completed = True
                            goal_allowed_record_ids = _goal_target_record_ids(
                                (
                                    self._agent_kernel_snapshot.goal
                                    if self._agent_kernel_snapshot is not None else None
                                ),
                                result,
                            )
                            if str(tc.get("id") or "").startswith("goal-verify-"):
                                goal_verification_result = result

                        # 追加 tool_result 到 messages
                        tool_content = _model_tool_result_content(
                            func_name,
                            parsed_tool_args,
                            result,
                            reference_now=self._agent_kernel_reference_now(),
                            timezone_label=self._ensure_agent_kernel_turn().context.timezone,
                        )
                        if (
                            func_name == "health_manage"
                            and parsed_tool_args.get("record_type") == "diet"
                            and parsed_tool_args.get("operation") == "list"
                        ):
                            tool_content += _goal_lookup_resolution_prompt(
                                (
                                    self._agent_kernel_snapshot.goal
                                    if self._agent_kernel_snapshot is not None else None
                                ),
                                result,
                            )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": tool_content,
                        })

                        # GenUI metric_table (rank1): 记下只读数据查询工具的
                        # (name, args, result), 合成后确定性建表/卡 (零 LLM)。声明
                        # genui-table-v1 或 genui-diet-summary-v1 任一即追踪 (无 cap → 零开销)。
                        if (genui_table_on or genui_diet_summary_on or genui_sleep_summary_on or genui_medication_list_on) and func_name in _GENUI_TABLE_TOOLS and not replayed_read:
                            genui_tool_calls.append((func_name, parsed_tool_args, result))

                        # tool_result 事件给前端用. health_record 时附 args 让前端能识别
                        # 是哪种 record + 提取关键内容显示 summary 卡 (I Phase 2).
                        tool_event_data = {
                            "tool": func_name,
                            "success": not result.startswith("Error"),
                            "preview": result[:200],
                            "result": result,
                        }
                        if replayed_write:
                            tool_event_data["replayed"] = True
                        if func_name in _WRITE_RECEIPT_TOOL_NAMES:
                            write_completed = _write_tool_completed(
                                func_name,
                                parsed_tool_args,
                                result_for_record_card,
                            )
                            tool_event_data["write_attempted"] = write_attempted
                            tool_event_data["write_completed"] = write_completed
                            if write_attempted and not write_completed:
                                tool_event_data["success"] = False
                            if write_completed and func_name == "health_record" and not replayed_write:
                                # Slice 3: 收集配方候选步骤 (只收成功写入的;
                                # sanitize 剥 confirmed — 一次性确认绝不进模板)。
                                try:
                                    from app.services import procedure_recipe_service as _recipe_svc
                                    recipe_candidate_steps.append({
                                        "tool": func_name,
                                        "args_template": _recipe_svc.template_step_args(
                                            _recipe_svc.sanitize_step_args(parsed_tool_args)
                                        ),
                                    })
                                except Exception as e:  # noqa: BLE001 — 候选收集失败不影响写主链路
                                    logger.warning(f"[agent_executor] recipe candidate 收集失败: {e}")
                            if write_completed:
                                receipt = _write_receipt_from_tool_result(
                                    func_name,
                                    parsed_tool_args,
                                    result_for_record_card,
                                )
                                if receipt:
                                    tool_event_data["receipt"] = receipt
                                    if not any(
                                        item.get("operation_id") == receipt.get("operation_id")
                                        for item in write_receipts
                                    ):
                                        write_receipts.append(receipt)
                            else:
                                receipt = None
                            tool_event_data.update(
                                _write_outcome_event_fields(
                                    result_for_record_card,
                                    receipt,
                                )
                            )
                            if write_attempted and not replayed_write:
                                checkpoint_status = _write_checkpoint_status_after_dispatch(
                                    result_for_record_card,
                                    receipt,
                                )
                                self._persist_turn_write_state(
                                    user_msg,
                                    status=checkpoint_status,
                                    tool_name=func_name,
                                    parsed_args=parsed_tool_args,
                                    receipt=receipt,
                                )
                                if runtime_write_fingerprint:
                                    if checkpoint_status == "uncertain":
                                        unverified_write_operations[
                                            runtime_write_fingerprint
                                        ] = func_name
                                    elif checkpoint_status == "verified":
                                        unverified_write_operations.pop(
                                            runtime_write_fingerprint,
                                            None,
                                        )
                        record_card = None
                        quality_cards: list[dict] = []
                        transient_local_rejection = bool(
                            write_attempted
                            and _write_result_is_pre_dispatch_validation_error(
                                result_for_record_card
                            )
                        )
                        if transient_local_rejection:
                            assert recoverable_write_key is not None
                            pending_recoverable_write_rejections.pop(
                                recoverable_write_key,
                                None,
                            )
                            pending_recoverable_write_rejections[
                                recoverable_write_key
                            ] = (
                                _pre_dispatch_validation_user_message(
                                    result_for_record_card
                                ),
                                classify_write_execution(
                                    result_for_record_card
                                ).error_code,
                            )
                            pending_recoverable_write_rejection_rounds[
                                recoverable_write_key
                            ] = round_idx
                            pending_recoverable_write_rejection_scopes[
                                recoverable_write_key
                            ] = _recoverable_write_scope_key(
                                func_name,
                                parsed_tool_args,
                            )
                        elif write_attempted and write_completed:
                            assert recoverable_write_key is not None
                            recoverable_scope_key = (
                                _recoverable_write_scope_key(
                                    func_name,
                                    parsed_tool_args,
                                )
                            )
                            _clear_repaired_write_rejections(
                                pending_recoverable_write_rejections,
                                pending_recoverable_write_rejection_rounds,
                                pending_recoverable_write_rejection_scopes,
                                operation_key=recoverable_write_key,
                                scope_key=recoverable_scope_key,
                                current_round=round_idx,
                                allow_scope_repair=(
                                    _goal_binds_recoverable_write(
                                        (
                                            self._agent_kernel_snapshot.goal
                                            if self._agent_kernel_snapshot
                                            is not None
                                            else None
                                        ),
                                        func_name,
                                        parsed_tool_args,
                                    )
                                ),
                            )
                        (
                            last_recoverable_write_rejection,
                            last_recoverable_write_rejection_code,
                        ) = _summarize_recoverable_write_rejections(
                            pending_recoverable_write_rejections
                        )
                        suppress_contextual_diet_replay_card = (
                            func_name == "health_record"
                            and bool(self._turn_contextual_diet_cards)
                            and _is_contextual_meal_photo_replay_result(result_for_record_card)
                        )
                        if (
                            func_name == "health_record"
                            and not replayed_write
                            and not transient_local_rejection
                            and not suppress_contextual_diet_replay_card
                        ):
                            try:
                                tool_event_data["record_type"] = (
                                    parsed_tool_args.get("record_type")
                                    or parsed_tool_args.get("type")
                                )
                                tool_event_data["record_data"] = parsed_tool_args.get("data") or {}
                                quality_response = _post_record_quality_response(
                                    tool_event_data["record_type"],
                                    tool_event_data["record_data"],
                                    result_for_record_card,
                                    personal_context=system_content,
                                    db=self.db,
                                    user_id=user_id,
                                    write_verified=bool(
                                        receipt and receipt.get("verified") is True
                                    ),
                                )
                                if quality_response:
                                    post_record_qualities.append(quality_response)
                                    quality_cards = [
                                        card for card in quality_response.get("cards", [])
                                        if isinstance(card, dict)
                                    ]
                                else:
                                    record_card = _health_record_card_descriptor(
                                        tool_event_data["record_type"],
                                        tool_event_data["record_data"],
                                        result_for_record_card,
                                        write_verified=bool(
                                            receipt and receipt.get("verified") is True
                                        ),
                                    )
                            except Exception:
                                pass

                        if not transient_local_rejection:
                            yield {
                                "event": "tool_result",
                                "data": tool_event_data,
                            }
                        for quality_card in quality_cards:
                            before = len(streamed_cards)
                            streamed_cards = _merge_agent_card_descriptors(streamed_cards, [quality_card])
                            if len(streamed_cards) > before:
                                yield {
                                    "event": "card",
                                    "data": {
                                        "anchor": "post_record_quality",
                                        "descriptor": quality_card,
                                    },
                                }
                        if record_card:
                            before = len(streamed_cards)
                            streamed_cards = _merge_agent_card_descriptors(streamed_cards, [record_card])
                            if len(streamed_cards) > before:
                                yield {
                                    "event": "card",
                                    "data": {
                                        "anchor": "tool_result",
                                        "descriptor": record_card,
                                    },
                                }
                        for safety_card in safety_cards:
                            before = len(streamed_cards)
                            streamed_cards = _merge_agent_card_descriptors(streamed_cards, [safety_card])
                            if len(streamed_cards) > before:
                                yield {
                                    "event": "card",
                                    "data": {
                                        "anchor": "safety_alert",
                                        "descriptor": safety_card,
                                    },
                                }

                    medication_confirmation_card = getattr(
                        self,
                        "_turn_medication_tool_confirmation_card",
                        None,
                    )
                    if medication_confirmation_card is not None:
                        streamed_cards = _merge_agent_card_descriptors(
                            streamed_cards,
                            [medication_confirmation_card],
                        )
                        # This card authorizes a health write. Deliver it only
                        # in final ``done.cards``, after the completed assistant
                        # checkpoint is committed. Streaming it here would let
                        # a fast client click an authorization the server cannot
                        # yet prove was fully presented.

                    # 2026-07-01: 关闭本轮 tool_exec 壁钟 + 记录 per-round split (纯埋点)。
                    try:
                        _round_tool_exec_ms = int((time.time() - _round_tool_start) * 1000)
                    except Exception:  # noqa: BLE001
                        _round_tool_exec_ms = 0
                    rounds.append({
                        "llm_gen_ms": _round_llm_gen_ms,
                        "tool_exec_ms": _round_tool_exec_ms,
                        "tools": list(_round_tool_names),
                    })

                    if unverified_write_operations:
                        final_finish_reason = "error"
                        # 部分成功要点名(write_receipts=本轮已验证写入),不一刀切否定
                        _unverified_msg = _unverified_write_message(write_receipts)
                        if not health_advice_buffered:
                            for i in range(0, len(_unverified_msg), 20):
                                yield {
                                    "event": "token",
                                    "data": {
                                        "content": _unverified_msg[i:i + 20]
                                    },
                                }
                        full_reply += _unverified_msg
                        break

                    # ``NEEDS_CONFIRMATION`` is an intentional manual-confirm
                    # terminal state, not a failed/no-tool write.  Finish from
                    # the observed tool results now instead of asking another
                    # model round to reinterpret (or overwrite) that state.
                    pure_pending_confirmation = bool(
                        self._agent_kernel_pending_confirmation_tools
                        and not self._agent_kernel_tool_failure_tools
                        and not self._agent_kernel_capability_block_reasons
                    )
                    if self._prefer_fast_record_model and pure_pending_confirmation:
                        pending_text = _pending_confirmation_reply_from_tool_results(
                            messages
                        )
                        if pending_text:
                            if write_receipts:
                                pending_text = (
                                    f"另有 {len(write_receipts)} 项记录已完成并取得回执。\n\n"
                                    f"{pending_text}"
                                )
                            if not health_advice_buffered:
                                for i in range(0, len(pending_text), 20):
                                    chunk = pending_text[i:i + 20]
                                    yield {
                                        "event": "token",
                                        "data": {"content": chunk},
                                    }
                            full_reply += pending_text
                            final_finish_reason = "stop"
                            break

                    # 硬门(诚实不变量):确定性"已记录…"回复只允许在本轮产生了**可验证的写入回执**
                    # (write_receipts,由 _write_tool_attempted / _write_receipt_from_tool_result 判定)
                    # 后出现。名字级判断(工具名 ∈ {health_record, health_manage})会把 health_manage
                    # 的 list/query(读,用来找记录 ID)误判为写 —— 2026-07-13 prod turn 6334 实锤:
                    # 分析问句「从 HRV 记录…推断胃溃疡根因」曾被旧关键词路由误判为记录意图，
                    # 本轮只调 health_query×5 + health_manage(list),
                    # 无任何写入(write_receipts=[]),却吐出假"✅ 已记录"+记录味兜底("请再说一次要改哪一条")。
                    # 上面 unverified_write_operations 已先行拦掉"尝试写但无回执"的情形,故走到这里时
                    # write_receipts 非空 ⟺ 本轮确有可验证写入。无回执 → fall through 到 continue,
                    # 让下一轮 LLM 用工具结果作答(合成/查询直出),绝不谎报写入。
                    _round_executed_write_tool = any(
                        t in ("health_record", "health_manage") for t in _round_tool_names
                    )
                    _turn_had_verified_write = bool(write_receipts)
                    if (
                        self._prefer_fast_record_model
                        and _turn_had_verified_write
                        and not last_recoverable_write_rejection
                    ):
                        combined_post_record_quality = combine_post_record_quality_responses(post_record_qualities)
                        final_text = (
                            str(combined_post_record_quality.get("reply") or "").strip()
                            if combined_post_record_quality else ""
                        )
                        if not final_text:
                            final_text = _fast_record_reply_from_tool_results(messages)
                        # 安全文本强制携带(加层不减层):quality 模板不看 tool result,
                        # 曾把写后安全评估的 '⚠️ 安全提示' 从回复里整体丢掉 —— 老客户端
                        # 不渲染 safety 卡,这行文本是其唯一载体。
                        safety_suffix = _safety_warning_suffix_from_tool_results(messages)
                        if safety_suffix and safety_suffix not in final_text:
                            final_text = f"{final_text}\n\n{safety_suffix}" if final_text else safety_suffix
                        if final_text:
                            if not health_advice_buffered:
                                for i in range(0, len(final_text), 20):
                                    chunk = final_text[i:i + 20]
                                    yield {
                                        "event": "token",
                                        "data": {"content": chunk},
                                    }
                            full_reply += final_text
                            break

                    # 确定性查询直出 (Phase-2 rank2, flag 门控, ships-OFF): 镜像上面记录路径的
                    # "确定性回复 + 跳过合成轮 break"。只对 fast-route 的**只读**查询回合 (非记录):
                    # 本轮无写工具、执行过工具, 且本回合所有 health_query 结果都能被 top-5 维度
                    # 格式化器覆盖 (且无安全告警后缀) → 从真实 tool result 渲染人话读数并 break,
                    # 跳过强模型合成轮。任一未覆盖维度/写工具/安全后缀 → 短路返回 None,
                    # fall-open 落到下方 continue 走正常合成 (fail-open: 宁可慢而对)。
                    if (
                        settings.deterministic_query_reply
                        and self._fast_route_simple_turn
                        and not self._prefer_fast_record_model
                        and not _round_executed_write_tool
                        and tool_executed_count > 0
                    ):
                        from app.services import query_readouts

                        deterministic_query_text = query_readouts.deterministic_query_reply(messages)
                        if deterministic_query_text:
                            if not health_advice_buffered:
                                for i in range(0, len(deterministic_query_text), 20):
                                    chunk = deterministic_query_text[i:i + 20]
                                    yield {
                                        "event": "token",
                                        "data": {"content": chunk},
                                    }
                            full_reply += deterministic_query_text
                            # 最终答案路径 → finish_reason 对齐 'stop' (completion_status → complete),
                            # 不留工具轮的 'tool_calls' 陈值 (镜像 rank7 passthrough 收尾)。
                            final_finish_reason = "stop"
                            break

                    # 只读收敛护栏: 本轮全是"已跑过"的只读调用(纯空转重发)→ 强制下轮进合成轮,
                    # 停住 loop(_force_no_tools_synthesis 在轮首最先判, 压过 keep_tools_after_synthesis_miss)。
                    if planned_reads_all_seen:
                        self._force_no_tools_synthesis = True

                    if (
                        round_idx == MAX_TOOL_ROUNDS - 1
                        and last_recoverable_write_rejection
                    ):
                        final_finish_reason = "error"
                        terminal_rejection = _write_rejection_with_receipt_context(
                            last_recoverable_write_rejection,
                            write_receipts,
                        )
                        if not health_advice_buffered:
                            for i in range(
                                0,
                                len(terminal_rejection),
                                20,
                            ):
                                yield {
                                    "event": "token",
                                    "data": {
                                        "content": terminal_rejection[i:i + 20]
                                    },
                                }
                        full_reply += terminal_rejection
                        break

                    # 继续循环让模型处理 tool_result
                    continue

                else:
                    # 纯文本回复 — 最终答案。本轮 content 已在上面逐 delta 真流式
                    # 下发给客户端 (streamed_to_client)。这里只补 interrupted notice
                    # 后缀 + full_reply,不再切 20-char 假块重发。
                    if self._last_provider_model_name:
                        # done.model 表示最终用户可见答案的模型。工具门控 fallback
                        # 只负责拿数据,不能覆盖用户手动选择模型的最终归属。
                        model_name = self._last_provider_model_name
                    if isinstance(response, str):
                        # 已经是完整文本（理论上流式路径不会进这里,保险留着）
                        final_text = response
                        streamed_to_client = False
                    else:
                        final_text = response.get("content") or ""
                        final_text = _append_interrupted_notice(final_text, response.get("finish_reason"))
                    # 兜底:括号工具标记没能恢复成 tool_call(name 不在白名单/参数解析失败)时,
                    # 也绝不能把裸 `[工具调用: ...]` 留在用户可见正文里。剥离后若空,走下方空回复重试链。
                    stripped = _strip_bracket_tool_markers(final_text)
                    if stripped != final_text:
                        final_text = stripped
                        streamed_to_client = False
                    # 同理:XML `<invoke>…</invoke>` 块 / 孤立 `<minimax:tool_call>` 标记(MiniMax 经代理)
                    # 没能恢复成 tool_call 时,绝不能把裸 XML 语法留给用户。剥离后若空走空回复重试链。
                    stripped_xml = _strip_xml_tool_markers(final_text)
                    if stripped_xml != final_text:
                        final_text = stripped_xml
                        streamed_to_client = False
                    # 兜底:弱模型(如 deepseek-v4-pro)把工具结果/参数裸 JSON 当最终回复
                    # 回显(用户截图:记录后正文是 {"id":231,...} / {"record_date":...})。
                    # 整条是裸 JSON 且本轮确有工具结果 → 用工具结果合成"已记录…",绝不裸露。
                    if _looks_like_bare_tool_json(final_text):
                        # 按本轮兜底口径:**可验证写入回执**(write_receipts)才允许合成"已记录…";
                        # 只读回合(含 health_manage 的 list/query)→ 查询味自然语言,绝不谎报"✅ 已记录"。
                        # 名字级 tools_used ∋ health_manage 会把查 ID 的 list 误判为写(同 turn 6334 病根)。
                        if write_receipts:
                            synthesized = _fast_record_reply_from_tool_results(messages)
                        else:
                            # 查询回合:绝不谎报"已记录"。工具结果无现成人话字段时给
                            # 非空中性兜底 —— 空串会触发空回复重试链,弱模型每轮重放
                            # 同样的裸 JSON,越试漏得越多(测试实测)。
                            synthesized = _natural_language_from_tool_results(messages) or (
                                "已查到相关数据,但这轮没能整理成回答;请再问一次或换个问法。"
                            )
                        if synthesized.strip():
                            final_text = synthesized
                            streamed_to_client = False
                    # QUERY 泄漏:短前言 + 内嵌工具结果 JSON 数组(qwen3.7-max:`让我查一下…
                    # [{"record_date":...,"meal_type":...}]`)。_looks_like_bare_tool_json 只认
                    # "整条即 JSON",这种带前言的漏过 → 锚定检测命中就必须清掉,绝不落库/回显。
                    # 流式期已被上面的 suppressor 拦下(streamed_to_client 应已 False),这里做
                    # 落库侧兜底:优先用工具结果里现成人话;没有则清空,交给下方空回复重试链让
                    # 模型用自然语言重答。写回 final_text 保证 message.meta / reload 也是干净的。
                    elif _leaks_tool_result_json(final_text):
                        streamed_to_client = False
                        # 非空兜底:空串会走空回复重试链,弱模型每轮重放同样的泄漏,
                        # 越试漏得越多(测试实测:前言 ×7 + 最终不可用)。宁可一句
                        # 中性话术收尾,也不给重试风暴机会。
                        final_text = _natural_language_from_tool_results(messages) or (
                            "已查到相关数据,但这轮没能整理成回答;请再问一次或换个问法。"
                        )
                    if (
                        not model_recovery_attempted
                        and is_model_scope_refusal(final_text)
                    ):
                        model_recovery_attempted = True
                        recovered_text = await self._recover_model_scope_refusal(messages)
                        if recovered_text:
                            final_text = recovered_text
                            streamed_to_client = False
                            self._record_model_fallback_reason("model_scope_refusal_recovered")
                    if (
                        not model_recovery_attempted
                        and is_data_insufficiency_response(final_text)
                    ):
                        model_recovery_attempted = True
                        recovered_text = await self._recover_data_insufficiency(messages)
                        if recovered_text:
                            final_text = recovered_text
                            streamed_to_client = False
                            self._record_model_fallback_reason("data_insufficiency_recovered")
                    if not final_text.strip():
                        # 空回复 → 走非流式重试链 (这些是新生成文本,需要 emit)。
                        streamed_to_client = False
                        messages.append({
                            "role": "user",
                            "content": (
                                "上一轮没有生成任何用户可见回复。请不要调用工具，"
                                "直接用中文给出完整回答。"
                            ),
                        })
                        _round_start = time.time()
                        retry_response = await self._call_llm(messages, [])
                        if isinstance(retry_response, dict):
                            final_finish_reason = retry_response.get("finish_reason") or final_finish_reason
                        llm_rounds_ms.append(int((time.time() - _round_start) * 1000))
                        final_text = _response_text(retry_response)
                        if isinstance(retry_response, dict):
                            final_text = _append_interrupted_notice(final_text, retry_response.get("finish_reason"))
                        if not final_text.strip():
                            # 诚实不变量:兜底的"已完成记录/操作"口径只在本轮有可验证
                            # 写入回执时允许;查询/分析回合(write_receipts 空)用查询味。
                            final_text = _fallback_text_from_tool_results(
                                messages, has_verified_write=bool(write_receipts),
                            )
                        if not final_text.strip():
                            compact_messages = _build_compact_empty_retry_messages(messages)
                            logger.warning(
                                "[agent_executor] empty LLM reply after retry; compacting context "
                                "from chars=%s to chars=%s",
                                len(str(messages[0].get("content") or "")) if messages else 0,
                                len(str(compact_messages[0].get("content") or "")),
                            )
                            _round_start = time.time()
                            compact_response = await self._call_llm(compact_messages, [])
                            if isinstance(compact_response, dict):
                                final_finish_reason = compact_response.get("finish_reason") or final_finish_reason
                            llm_rounds_ms.append(int((time.time() - _round_start) * 1000))
                            final_text = _response_text(compact_response)
                            if isinstance(compact_response, dict):
                                final_text = _append_interrupted_notice(
                                    final_text,
                                    compact_response.get("finish_reason"),
                                )
                        if not final_text.strip():
                            logger.warning(
                                "[agent_executor] compact retry also empty; using stable fallback provider"
                            )
                            _round_start = time.time()
                            fallback_response = await self._call_llm_fallback_provider(
                                _build_compact_empty_retry_messages(messages)
                            )
                            if isinstance(fallback_response, dict):
                                final_finish_reason = (
                                    fallback_response.get("finish_reason")
                                    or final_finish_reason
                                )
                            llm_rounds_ms.append(int((time.time() - _round_start) * 1000))
                            final_text = _response_text(fallback_response)
                            if isinstance(fallback_response, dict):
                                final_text = _append_interrupted_notice(
                                    final_text,
                                    fallback_response.get("finish_reason"),
                                )
                        if not final_text.strip():
                            final_text = "我这次没有收到模型的有效回复，请稍后重试或切换模型。"
                    pure_pending_confirmation = bool(
                        self._agent_kernel_pending_confirmation_tools
                        and not self._agent_kernel_tool_failure_tools
                        and not self._agent_kernel_capability_block_reasons
                    )
                    if (
                        last_recoverable_write_rejection
                        and (
                            last_recoverable_write_rejection_code
                            == "diet_nutrition_incomplete"
                            or _claims_unverified_write_success(final_text)
                        )
                    ):
                        final_text = _write_rejection_with_receipt_context(
                            last_recoverable_write_rejection,
                            write_receipts,
                        )
                        final_finish_reason = "error"
                        streamed_to_client = False
                    elif last_recoverable_write_rejection and write_receipts:
                        final_text = _write_rejection_with_receipt_context(
                            final_text,
                            write_receipts,
                        )
                        streamed_to_client = False
                    elif pure_pending_confirmation:
                        pending_text = _pending_confirmation_reply_from_tool_results(
                            messages
                        )
                        if pending_text:
                            if write_receipts:
                                pending_text = (
                                    f"另有 {len(write_receipts)} 项记录已完成并取得回执。\n\n"
                                    f"{pending_text}"
                                )
                            final_text = pending_text
                            streamed_to_client = False
                    elif self._prefer_fast_record_model and not write_receipts:
                        final_text = _record_intent_needs_detail_message(message)
                        streamed_to_client = False
                    elif (
                        partial_diet_correction_requested
                        and not write_receipts
                        and self._turn_diet_correction_unresolved_reason
                    ):
                        if self._turn_diet_correction_unresolved_reason == "ambiguous_target":
                            final_text = (
                                "我找到多条符合日期和餐次的饮食记录，暂时没有修改。"
                                "请选择具体哪一条后再提交修正。"
                            )
                        else:
                            final_text = (
                                "我找到了对应餐次，但现有记录缺少可缩放的营养数据，"
                                "暂时没有修改。请补充实际吃了什么或具体热量。"
                            )
                        streamed_to_client = False
                    elif _needs_reliable_tool_model(message or "") and tool_executed_count == 0:
                        # 破坏性/同步意图但 0 工具执行 = 动作未执行 → 诚实覆盖(加层不减层)。
                        final_text = _destructive_or_sync_not_performed_message(message)
                        streamed_to_client = False
                    if (
                        not health_advice_buffered
                        and streamed_to_client
                        and final_text.startswith(streamed_text)
                    ):
                        # 正文已实时下发,只补 interrupted notice 等未流式的后缀。
                        tail = final_text[len(streamed_text):]
                        if tail:
                            if first_token_at is None:
                                first_token_at = time.time()
                            yield {"event": "token", "data": {"content": tail}}
                    elif not health_advice_buffered:
                        # 重试/兜底产生的新文本 (非流式来源) → 一次性下发。
                        if final_text:
                            if first_token_at is None:
                                first_token_at = time.time()
                            yield {"event": "token", "data": {"content": final_text}}
                    full_reply += final_text
                    # rank7 shadow: 本轮就是被短路的目标(单次 orchestrator 深分析回合的二次合成)——
                    # 记下这次二次合成轮壁钟 = passthrough 可省的时延。shadow 下行为不变(照跑),只观测。
                    if (
                        passthrough_mode == "shadow"
                        and tool_executed_count == 1
                        and passthrough_orch_calls == 1
                        and passthrough_orch_text
                    ):
                        passthrough_synthesis_round_ms = _round_llm_gen_ms
                    # 2026-07-01: 无工具的最终答案轮 — per-round split (tool_exec_ms=0)。
                    rounds.append({
                        "llm_gen_ms": _round_llm_gen_ms,
                        "tool_exec_ms": 0,
                        "tools": [],
                    })
                    break

            else:
                # 达到工具轮次上限后，不要把半成品直接返回给用户。
                # DeepSeek 这类模型更容易连续拆分工具查询；上限命中时强制做一次
                # no-tools synthesis，用已有 tool_result 汇总成最终答案。
                # 2026-07-05 P0-1: 进度事件 (flat 契约) —— 强制合成也是"最终回答开始生成",
                # 命中 accepted→tool*→synthesis→done 契约的轮次耗尽分支。纯附加。
                yield self._progress_event("synthesis")
                messages.append({
                    "role": "user",
                    "content": (
                        "工具查询轮次已经用完。请停止继续调用工具，"
                        "只基于上文已经返回的健康数据、体检/基因/知识库结果，"
                        "给出完整的最终分析和可执行建议。"
                    ),
                })
                _round_start = time.time()
                response = await self._call_llm(messages, [])
                if self._last_provider_model_name:
                    model_name = self._last_provider_model_name
                if isinstance(response, dict):
                    final_finish_reason = response.get("finish_reason") or final_finish_reason
                llm_rounds_ms.append(int((time.time() - _round_start) * 1000))
                if isinstance(response, str):
                    final_text = response
                elif isinstance(response, dict):
                    final_text = response.get("content") or ""
                    final_text = _append_interrupted_notice(final_text, response.get("finish_reason"))
                    if not final_text and response.get("tool_calls"):
                        final_text = (
                            "我已经完成了多轮数据查询，但模型仍尝试继续调用工具。"
                            "请缩小问题范围，或稍后使用更强模型重新分析。"
                        )
                else:
                    final_text = str(response or "")

                if not final_text.strip():
                    final_text = (
                        "我已经完成了多轮数据查询，但没有生成足够明确的最终结论。"
                        "请缩小问题范围，或稍后使用更强模型重新分析。"
                    )
                if not health_advice_buffered:
                    for i in range(0, len(final_text), 20):
                        chunk = final_text[i:i + 20]
                        yield {"event": "token", "data": {"content": chunk}}
                full_reply += final_text

        except Exception as e:
            logger.error(
                "Agent 执行异常 user=%s error_type=%s",
                user_id,
                type(e).__name__,
            )
            if self._turn_attachment_write_receipts and vision_description:
                asks_for_analysis = _medical_report_analysis_requested(
                    message,
                    persisted=True,
                )
                if asks_for_analysis:
                    error_msg = (
                        "报告已保存，OCR 识别文字也已保留但尚待核对；"
                        "本次个性化解读服务暂时不可用。"
                        "请稍后重试分析，系统不会重复保存这份报告。\n\n"
                        f"{vision_description}"
                    )
                else:
                    error_msg = (
                        "报告已保存并取得持久化回执；OCR 内容尚待核对。\n\n"
                        f"{vision_description}"
                    )
                    final_finish_reason = "stop"
            else:
                error_msg = safe_llm_error_message(e)
            if not health_advice_buffered:
                yield {"event": "token", "data": {"content": error_msg}}
            full_reply = error_msg
            if final_finish_reason != "stop":
                final_finish_reason = "error"
        finally:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

        # 6. 保存回复
        # 确定性护栏 (R4, 防御纵深): full_reply 是 LLM 生成文本 —— 剥掉任何伪造的
        # reva-ui 图表 block (数值只能来自确定性 genui 短路; 短路走独立路径不经此处)。
        full_reply = _strip_reva_ui_from_llm_text(full_reply)
        full_reply = _strip_botched_text_tool_leak(full_reply)
        full_reply = _strip_scope_refusal_preamble(full_reply)
        full_reply = _ground_query_response_date_labels(
            full_reply,
            message,
            reference_now=self._agent_kernel_reference_now(),
        )
        record_intent_no_tool = bool(
            health_evidence_turn is None
            and self._prefer_fast_record_model
            and not write_receipts
            and not self._agent_kernel_pending_confirmation_tools
            and not last_recoverable_write_rejection
        )
        # 破坏性/同步意图从 fast-record 集排除后(留强模型),其 0-工具 缺口在此补上,
        # 与 record_intent_no_tool 加层不减层(不与之重叠:record 集已被上面判掉)。
        destructive_or_sync_no_tool = bool(
            health_evidence_turn is None
            and not record_intent_no_tool
            and _needs_reliable_tool_model(message or "")
            and tool_executed_count == 0
        )
        if record_intent_no_tool:
            fail_closed_reply = _record_intent_needs_detail_message(message)
            if full_reply.strip() != fail_closed_reply:
                full_reply = fail_closed_reply
            logger.warning(
                "[agent_executor] RECORD INTENT but 0 tools executed — possible silent "
                "data loss (model may have claimed success without writing). "
                "user=%s message_chars=%s",
                user_id,
                len(message or ""),
            )
        elif destructive_or_sync_no_tool:
            fail_closed_reply = _destructive_or_sync_not_performed_message(message)
            if full_reply.strip() != fail_closed_reply:
                full_reply = fail_closed_reply
            logger.warning(
                "[agent_executor] DESTRUCTIVE/SYNC INTENT but 0 tools executed — action "
                "not performed (model may have claimed 已删/已改/已同步 without acting). "
                "user=%s message_chars=%s",
                user_id,
                len(message or ""),
            )
        if health_evidence_turn is not None:
            # This is the only release point for model-authored health advice.
            # Every earlier token path is buffered; only deterministic verifier
            # output may be persisted or sent to any client.
            try:
                health_verification = health_evidence_turn.verify(full_reply)
            except Exception as exc:  # noqa: BLE001 - fail closed, never leak candidate
                logger.exception(
                    "[health_evidence] final verifier failed user=%s error_type=%s",
                    user_id,
                    type(exc).__name__,
                )
                health_verification = (
                    health_evidence_turn.verifier_failure()
                )
            full_reply = health_verification.text
            health_evidence_manifest = health_evidence_turn.public_manifest(
                verification=health_verification,
            )
            sources_used = list(
                dict.fromkeys(
                    str(item.get("organization") or "").strip()
                    for item in health_evidence_manifest.get(
                        "authority_sources",
                        [],
                    )
                    if str(item.get("organization") or "").strip()
                )
            )
            context_categories = [
                str(item).strip()
                for item in health_evidence_manifest.get(
                    "context_categories_used",
                    [],
                )
                if str(item).strip()
            ]
            if context_categories:
                sources_used.append(
                    "个人健康上下文：" + "、".join(context_categories)
                )
            if first_token_at is None:
                first_token_at = time.time()
            for i in range(0, len(full_reply), 24):
                yield {
                    "event": "token",
                    "data": {"content": full_reply[i:i + 24]},
                }
        # [guidance-probe · 2026-07-17] 主对话 R4 guidance 红线的**纯影子测量**(只打 log)。
        # 现状(对抗评审揪出): diet_prescription_red_line(CRITICAL) / movement_imperative_red_line
        # 只扫 twin.acute.pending_guidance_texts, 而 builder 永不填充、agent_executor 零调用
        # → 这条确定性 R4 规则在**最大流量出口(主对话)上全程是暗的**。
        # 但实测: 现有饮食正则在开放域主对话 9/15 误命中(回显用户自己的记录/目标、转述医嘱/KB、
        # 甚至提问句), 直接上 alert/审计会 (a) 把真实 safety 评估挤出 /safety/audit 默认窗口
        # = 审计面 under-alarm, (b) 审计写入的 rollback 会回滚本轮还没落库的助手消息。
        # 故本切片**只打 log**: 不写审计行、不进 meta、不追加提示、不碰 db session、不改正文。
        # 目的 = 先量出真实分布(真处方 vs 转述/回显噪声), 再决定是否收紧正则/开拦截。
        # 位置: 在 GenUI fence 追加**之前**扫散文 —— 确定性卡片行(如 `| 每日摄入 | 50 克 |`)
        # 会命中 _PRESCRIPTIVE_QTY, 不该算进噪声分母。(LLM 自写的 markdown 表仍会命中 = 已知噪声。)
        # 时机: 此处 token 已全部下发, 不影响 TTFT。
        _guidance_shadow_probe(user_id, full_reply)

        # GenUI metric_table (rank1): 合成完成后, 把本回合只读数据查询结果确定性打成
        # reva-ui 表格卡片, 追加到答案末尾 (镜像图表 "叙事在前、卡片在后" 的顺序)。
        # 数值全部来自工具结果具名字段 (R4); 在 _strip_reva_ui_from_llm_text **之后**追加
        # → 确定性 fence 不会被防伪造剥离器吃掉。fail-open: 无表/任何异常 → 逐字节现状。
        if (
            not health_advice_buffered
            and genui_tool_calls
            and (
                genui_table_on
                or genui_diet_summary_on
                or genui_sleep_summary_on
                or genui_medication_list_on
            )
        ):
            try:
                from app.services.genui import (
                    build_tables_from_tool_calls,
                    render_metric_table_block,
                    build_diet_daily_summary,
                    render_diet_summary_block,
                    build_sleep_summary,
                    render_sleep_summary_block,
                    build_medication_list,
                    render_medication_list_block,
                    load_tool_result_json,
                )
                _fences: List[str] = []
                _table_calls: List[Tuple[str, Optional[dict], str]] = []
                for _fn, _args, _res in genui_tool_calls:
                    # health_query(diet) 且 cap 开 → 结构化 diet_summary 卡(而非通用表)。
                    # 用与 metric_table 同一宽松 JSON 解析真源(剥截断尾注),两路不漂移。
                    # dimension 归一化 .strip().lower() 与 metric_table dispatcher 对齐 ——
                    # 弱模型吐 'Diet'/' diet '/'DIET' 时不会静默降级回通用表。
                    _is_diet = (
                        _fn == "health_query"
                        and str((_args or {}).get("dimension") or "").strip().lower() == "diet"
                    )
                    if _is_diet and genui_diet_summary_on:
                        _summary = load_tool_result_json(_res)
                        # v1:只喂饮食汇总本身。water/weight_kg 暂不透传(read_daily_diet
                        # 结果无此字段)→ 卡片按契约优雅降级(不显饮水条、蛋白只报克数);
                        # 二者是后续增量(接今日饮水快照 + 用户体重),composer 侧已支持。
                        _desc = (
                            build_diet_daily_summary(_summary)
                            if isinstance(_summary, dict) else None
                        )
                        if _desc:
                            _fences.append(render_diet_summary_block(_desc))
                            continue  # diet 走结构化卡,不再落 metric_table
                    # health_query(sleep) 且 cap 开 → 结构化 sleep_summary 卡(与 diet 同机制)。
                    _is_sleep = (
                        _fn == "health_query"
                        and str((_args or {}).get("dimension") or "").strip().lower() == "sleep"
                    )
                    if _is_sleep and genui_sleep_summary_on:
                        _analysis = load_tool_result_json(_res)
                        _sdesc = (
                            build_sleep_summary(_analysis)
                            if isinstance(_analysis, dict) else None
                        )
                        if _sdesc:
                            _fences.append(render_sleep_summary_block(_sdesc))
                            continue  # sleep 走结构化卡,不再落 metric_table
                    # health_query(medication) 且 cap 开 → 结构化 medication_list 卡。
                    # 与 diet/sleep 的差异:该端点返回**数组**(不是 dict),故这里判 list。
                    _is_medication = (
                        _fn == "health_query"
                        and str((_args or {}).get("dimension") or "").strip().lower() == "medication"
                    )
                    if _is_medication and genui_medication_list_on:
                        _meds = load_tool_result_json(_res)
                        _mdesc = (
                            build_medication_list(_meds)
                            if isinstance(_meds, list) else None
                        )
                        if _mdesc:
                            _fences.append(render_medication_list_block(_mdesc))
                            continue  # medication 走结构化卡,不再落 metric_table
                    _table_calls.append((_fn, _args, _res))
                if genui_table_on and _table_calls:
                    for _tbl in build_tables_from_tool_calls(_table_calls):
                        _fences.append(render_metric_table_block(_tbl))
                for _fence in _fences:
                    _chunk = f"\n\n{_fence}" if full_reply.strip() else _fence
                    if first_token_at is None:
                        first_token_at = time.time()
                    yield {"event": "token", "data": {"content": _chunk}}
                    full_reply += _chunk
            except Exception as e:  # noqa: BLE001 — 建卡/建表/emit 失败绝不断回合
                logger.warning(
                    "[agent_executor] GenUI card/table build/emit failed: %s", e
                )
        ai_msg = svc.save_message(
            conv.id,
            "assistant",
            full_reply,
            client_turn_id=client_turn_id,
            client_turn_user_id=user_id,
        )
        conv.updated_at = datetime.now(UTC)

        elapsed_ms = int((time.time() - start_time) * 1000)
        llm_ms_total = sum(llm_rounds_ms)

        # 2026-07-01: 汇总 perf (纯埋点)。fail-soft — 任何计时缺失用 None/0, 绝不断流。
        try:
            llm_ttft_ms: Optional[int] = (
                int((first_token_at - start_time) * 1000) if first_token_at else None
            )
        except Exception:  # noqa: BLE001
            llm_ttft_ms = None
        perf = {
            "total_ms": elapsed_ms,
            "pre_llm_ms": pre_llm_ms,
            "pre_llm_stages": dict(pre_stages),
            "llm_ttft_ms": llm_ttft_ms,
            "llm_full_ms": llm_ms_total,
            "rounds": rounds,
            "orchestrator_tool_ms": orchestrator_tool_ms,
            "orchestrator_perf": orchestrator_perf,
        }
        # 单行 grep 日志 (镜像 orchestrator.py [perf.orchestrator])。
        try:
            logger.info(
                "[perf.agent] user=%s total=%sms pre_llm=%sms ttft=%sms llm=%sms rounds=%s model=%s",
                user_id, elapsed_ms, pre_llm_ms, llm_ttft_ms, llm_ms_total,
                len(llm_rounds_ms), model_name,
            )
        except Exception:  # noqa: BLE001
            pass

        completion_status = _completion_status_from_finish_reason(final_finish_reason)
        recovered_capability_blocks = (
            set(self._agent_kernel_recovered_capability_block_reasons)
            if completion_status == "complete" and full_reply.strip()
            else set()
        )
        turn_outcome = classify_agent_turn_outcome(
            completion_status=completion_status,
            final_text=full_reply,
            capability_block_reasons=[
                reason
                for reason in self._agent_kernel_capability_block_reasons
                if reason not in recovered_capability_blocks
            ],
            tool_failure_tools=self._agent_kernel_tool_failure_tools,
            pending_confirmation_tools=self._agent_kernel_pending_confirmation_tools,
            write_receipts=write_receipts,
            record_intent_no_tool=record_intent_no_tool,
            destructive_or_sync_no_tool=destructive_or_sync_no_tool,
            write_reconciliation_required=bool(unverified_write_operations),
        )
        kernel_snapshot = self._agent_kernel_snapshot
        health_write_requested = bool(
            kernel_snapshot is not None
            and kernel_snapshot.intent.is_write
            and kernel_snapshot.intent.domain != "aigc_media"
        )
        recovery_action = build_retry_source_action_if_safe(
            source_message=user_msg,
            turn_outcome=turn_outcome,
            write_receipts=write_receipts,
            health_write_requested=health_write_requested,
            root_source_message_id=(
                retry_recovery.root_source_message_id
                if retry_recovery is not None
                else int(user_msg.id)
            ),
        )
        answer_model = model_name
        selected_model = self._display_model_name_for_id(self._request_model_id) or answer_model
        tool_models = list(self._tool_model_names)
        fallback_reasons = list(self._model_fallback_reasons)
        evidence_cards = []
        if completion_status == "complete" and health_evidence_turn is None:
            try:
                evidence_card = self._build_system_knowledge_evidence_card(user_id, message)
                if evidence_card:
                    evidence_cards.append(evidence_card)
                    before = len(streamed_cards)
                    streamed_cards = _merge_agent_card_descriptors(streamed_cards, [evidence_card])
                    if len(streamed_cards) > before:
                        yield {
                            "event": "card",
                            "data": {
                                "anchor": "system_knowledge_evidence",
                                "descriptor": evidence_card,
                            },
                        }
                    if "系统知识库" not in sources_used:
                        sources_used.append("系统知识库")
            except Exception as e:
                logger.warning(f"[agent_executor] system knowledge evidence card failed: {e}")
        response_cards = (
            _merge_agent_card_descriptors(
                self._turn_contextual_diet_cards,
                streamed_cards,
                evidence_cards,
            )
            if completion_status == "complete"
            else []
        )
        if completion_status == "complete" and self._turn_aigc_media_cards:
            response_cards = _merge_agent_card_descriptors(
                self._turn_aigc_media_cards,
                response_cards,
            )
        if (
            health_evidence_turn is not None
            and health_evidence_manifest is not None
        ):
            health_card = health_evidence_turn.card_descriptor(
                verification=health_verification,
            )
            response_cards = _merge_agent_card_descriptors(
                response_cards,
                [health_card],
            )
            yield {
                "event": "card",
                "data": {
                    "anchor": "health_evidence",
                    "descriptor": health_card,
                },
            }

        # Slice 3: 一轮完成 ≥2 个写类工具 → done 附 save_recipe 描述符 (仅描述符,
        # 移动端渲染"存为配方"入口)。候选步骤持久化到 message.meta.recipe_candidate,
        # save-from-conversation 端点从这里反推 —— 不重放对话、不经 LLM。
        recipe_candidate_meta: Optional[Dict[str, Any]] = None
        if completion_status == "complete" and len(recipe_candidate_steps) >= 2:
            try:
                from app.services import procedure_recipe_service as _recipe_svc

                recipe_candidate_meta = {
                    "steps": recipe_candidate_steps,
                    "step_count": len(recipe_candidate_steps),
                }
                save_recipe_card = {
                    "type": "save_recipe",
                    "data": {
                        "conversation_id": conv.id,
                        "step_count": len(recipe_candidate_steps),
                        "steps_preview": [
                            _recipe_svc.step_label(step)
                            for step in recipe_candidate_steps
                        ],
                    },
                    "actions": [],
                }
                response_cards = _merge_agent_card_descriptors(
                    response_cards, [save_recipe_card]
                )
                yield {
                    "event": "card",
                    "data": {
                        "anchor": "save_recipe",
                        "descriptor": save_recipe_card,
                    },
                }
            except Exception as e:  # noqa: BLE001 — 配方入口失败不影响回合收尾
                logger.warning(f"[agent_executor] save_recipe 描述符构建失败: {e}")
                recipe_candidate_meta = None

        # 后置校验 (#3 护栏): record 意图的 turn 却 0 次工具执行时,前面已改写为
        # 用户可见的 fail-closed 文案;这里继续把标记写入 meta/done 供监控使用。

        # P1 数字锚定核验(shadow): 观测最终答案里的个人数值能否锚定到 Twin。additive
        # 摘要进 meta + done, 客户端不读不炸。内部全 fail-soft, 绝不打死回合。
        citation_anchor = (
            None
            if health_evidence_turn is not None
            else _citation_anchor_shadow_meta(self.db, user_id, full_reply)
        )
        kernel_trace = self._agent_kernel_trace_summary(status=completion_status)

        # rank7: passthrough 观测/标记进 meta(offline judge 读)。shadow 落 would-be
        # passthrough 文本(截 4000 char)+ 两侧壁钟;on 落一个轻量 taken 标记。
        shadow_passthrough_meta: Optional[Dict[str, Any]] = None
        if (
            passthrough_mode == "shadow"
            and passthrough_synthesis_round_ms is not None
            and passthrough_orch_text
        ):
            shadow_passthrough_meta = {
                "orchestrator_text": passthrough_orch_text[:4000],
                "orchestrator_ms": orchestrator_tool_ms,
                "final_text_ms": passthrough_synthesis_round_ms,
            }
        synthesis_passthrough_meta: Optional[Dict[str, Any]] = None
        if passthrough_taken:
            synthesis_passthrough_meta = {
                "taken": True,
                "orchestrator_ms": orchestrator_tool_ms,
            }

        # 2026-05-14 FIX-7: 把性能 + 可解释性写到 message.meta, 用户回来 reload 能恢复 footer
        try:
            ai_msg.meta = {
                "elapsed_ms": elapsed_ms,
                "llm_ms": llm_ms_total,
                "llm_rounds": len(llm_rounds_ms),
                "llm_rounds_ms": llm_rounds_ms,
                "model": model_name,
                "selected_model": selected_model,
                "answer_model": answer_model,
                "tool_models": tool_models,
                "fallback_reasons": fallback_reasons,
                "sources_used": sources_used,
                "tools_used": tools_used,
                "write_receipts": write_receipts,
                "pending_write_intent_ids": self._turn_pending_write_intent_ids,
                "pending_write_intent_kinds": self._turn_pending_write_intent_kinds,
                "cards": cards_for_persistence(response_cards),
                "finish_reason": final_finish_reason,
                "completion_status": completion_status,
                "record_intent_no_tool": record_intent_no_tool,
                "turn_outcome": turn_outcome,
                **(
                    {
                        "health_evidence_manifest": health_evidence_manifest,
                        "health_evidence_verification": (
                            health_verification.public_dict(
                                manifest=health_evidence_manifest,
                            )
                            if health_verification is not None
                            else None
                        ),
                    }
                    if health_evidence_manifest is not None
                    else {}
                ),
                **(
                    {"recovery_action": recovery_action}
                    if recovery_action is not None
                    else {}
                ),
                "recovery": {
                    "tool_retry_count": self._agent_kernel_tool_retry_count,
                },
                "perf": perf,
                **({"kernel_trace": kernel_trace} if kernel_trace else {}),
                **({"citation_anchor": citation_anchor} if citation_anchor else {}),
                **({"recipe_candidate": recipe_candidate_meta} if recipe_candidate_meta else {}),
                **({"shadow_passthrough": shadow_passthrough_meta} if shadow_passthrough_meta else {}),
                **({"synthesis_passthrough": synthesis_passthrough_meta} if synthesis_passthrough_meta else {}),
                "client_turn_finalized": True,
                **({"client_turn_id": client_turn_id} if client_turn_id else {}),
            }
        except Exception as e:
            logger.warning(
                "[agent_executor] write meta 失败 user=%s error_type=%s",
                user_id,
                type(e).__name__,
            )
        self.db.commit()

        yield {
            "event": "done",
            "data": {
                "conversation_id": conv.id,
                "message_id": ai_msg.id,
                "elapsed_ms": elapsed_ms,
                "llm_ms": llm_ms_total,
                "llm_rounds": len(llm_rounds_ms),
                "llm_rounds_ms": llm_rounds_ms,
                "model": model_name,
                "selected_model": selected_model,
                "answer_model": answer_model,
                "tool_models": tool_models,
                "fallback_reasons": fallback_reasons,
                "sources_used": sources_used,
                "tools_used": tools_used,
                "write_receipts": write_receipts,
                "pending_write_intent_ids": self._turn_pending_write_intent_ids,
                "pending_write_intent_kinds": self._turn_pending_write_intent_kinds,
                "mode": "agent",
                "cards": response_cards,
                "finish_reason": final_finish_reason,
                "completion_status": completion_status,
                "record_intent_no_tool": record_intent_no_tool,
                "turn_outcome": turn_outcome,
                **(
                    {
                        "health_evidence_manifest": health_evidence_manifest,
                        "health_evidence_verification": (
                            health_verification.public_dict(
                                manifest=health_evidence_manifest,
                            )
                            if health_verification is not None
                            else None
                        ),
                    }
                    if health_evidence_manifest is not None
                    else {}
                ),
                **(
                    {"recovery_action": recovery_action}
                    if recovery_action is not None
                    else {}
                ),
                "recovery": {
                    "tool_retry_count": self._agent_kernel_tool_retry_count,
                },
                "perf": perf,
                **({"kernel_trace": kernel_trace} if kernel_trace else {}),
                **({"citation_anchor": citation_anchor} if citation_anchor else {}),
                **({"synthesis_passthrough": synthesis_passthrough_meta} if synthesis_passthrough_meta else {}),
                "client_turn_finalized": True,
                **({"client_turn_id": client_turn_id} if client_turn_id else {}),
            },
        }

    def _source_bound_medication_intent(
        self,
        *,
        user_id: int,
        conversation_id: int,
        source_message_id: int,
    ) -> Any:
        """Return an integrity-checked batch plan owned by one durable turn."""
        from app.models.write_intent import WriteIntent
        from app.services.medication_intake_batch import (
            WRITE_INTENT_KIND,
            validate_medication_intake_intent,
        )

        intent = (
            self.db.query(WriteIntent)
            .filter(
                WriteIntent.user_id == user_id,
                WriteIntent.kind == WRITE_INTENT_KIND,
                WriteIntent.target_type == "agent_message",
                WriteIntent.target_id == source_message_id,
            )
            .order_by(WriteIntent.id.desc())
            .first()
        )
        if intent is None:
            return None
        try:
            payload, _ = validate_medication_intake_intent(
                self.db,
                intent,
                require_unexpired=False,
            )
        except Exception as error:  # noqa: BLE001 — malformed plan is unusable
            logger.error(
                "[medication_batch] source plan validation failed "
                "intent=%s user=%s error_type=%s",
                intent.id,
                user_id,
                type(error).__name__,
            )
            return None
        if (
            payload.get("conversation_id") != conversation_id
            or payload.get("source_message_id") != source_message_id
        ):
            return None
        return intent

    def _has_pending_medication_confirmation_for_route(
        self,
        *,
        user_id: int,
        conversation_id: Optional[int],
    ) -> bool:
        """Read-only routing probe for an immediately pending chat card."""
        if conversation_id is None:
            return False
        from app.models.agent_conversation import AgentMessage
        from app.models.write_intent import WriteIntent
        from app.services.medication_intake_batch import WRITE_INTENT_KIND

        latest = (
            self.db.query(AgentMessage)
            .filter(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.id.desc())
            .first()
        )
        if latest is None or latest.role != "assistant" or not isinstance(latest.meta, dict):
            return False
        if (
            latest.meta.get("client_turn_finalized") is not True
            or latest.meta.get("completion_status") != "complete"
        ):
            return False
        raw_ids = latest.meta.get("pending_write_intent_ids")
        raw_kinds = latest.meta.get("pending_write_intent_kinds")
        if not isinstance(raw_ids, list) or len(raw_ids) != 1:
            return False
        if raw_kinds != [WRITE_INTENT_KIND]:
            return False
        try:
            intent_id = int(raw_ids[0])
        except (TypeError, ValueError):
            return False
        intent = (
            self.db.query(WriteIntent)
            .filter(
                WriteIntent.id == intent_id,
                WriteIntent.user_id == user_id,
                WriteIntent.kind == WRITE_INTENT_KIND,
                WriteIntent.status == "pending",
            )
            .first()
        )
        if intent is None or intent.target_id is None:
            return False
        source_bound = self._source_bound_medication_intent(
            user_id=user_id,
            conversation_id=int(conversation_id),
            source_message_id=int(intent.target_id),
        )
        if source_bound is None:
            return False
        from app.services.write_intent_service import (
            medication_batch_plan_was_presented,
        )

        return medication_batch_plan_was_presented(self.db, source_bound)

    def _immediately_pending_medication_intent(
        self,
        *,
        user_id: int,
        conversation_id: int,
        current_user_message: Any,
        action: str,
    ) -> Any:
        """Resolve only a pending plan named by the immediately prior assistant.

        Looking up the latest *assistant* is unsafe because it can jump over an
        intervening user message.  We first inspect the immediately prior row,
        then verify that its immediately prior row is the plan's source user
        message.  Assistant metadata is an index only; ownership, status,
        source binding, and the cryptographic plan hash are revalidated here.
        """
        from app.models.agent_conversation import AgentMessage
        from app.models.write_intent import WriteIntent
        from app.services.medication_intake_batch import (
            WRITE_INTENT_KIND,
            validate_medication_intake_intent,
        )

        prior = (
            self.db.query(AgentMessage)
            .filter(
                AgentMessage.conversation_id == conversation_id,
                AgentMessage.id < current_user_message.id,
            )
            .order_by(AgentMessage.id.desc())
            .first()
        )
        if prior is None or prior.role != "assistant" or not isinstance(prior.meta, dict):
            return None
        meta = prior.meta
        if (
            meta.get("client_turn_finalized") is not True
            or meta.get("completion_status") != "complete"
        ):
            return None
        raw_ids = meta.get("pending_write_intent_ids")
        raw_kinds = meta.get("pending_write_intent_kinds")
        terminal_decision = meta.get("medication_batch_decision")
        terminal_status: Optional[str] = None
        if (
            isinstance(raw_ids, list)
            and len(raw_ids) == 1
            and raw_kinds == [WRITE_INTENT_KIND]
        ):
            try:
                intent_id = int(raw_ids[0])
            except (TypeError, ValueError):
                return None
        elif isinstance(terminal_decision, dict):
            terminal_status = str(terminal_decision.get("status") or "")
            if terminal_status not in {"executed", "dismissed", "expired"}:
                return None
            try:
                intent_id = int(terminal_decision.get("intent_id"))
            except (TypeError, ValueError):
                return None
        else:
            return None
        intent = (
            self.db.query(WriteIntent)
            .filter(
                WriteIntent.id == intent_id,
                WriteIntent.user_id == user_id,
                WriteIntent.kind == WRITE_INTENT_KIND,
                WriteIntent.target_type == "agent_message",
            )
            .first()
        )
        allowed_statuses = {"pending", "executed", "dismissed"}
        if intent is None or intent.status not in allowed_statuses:
            return None
        if terminal_status is not None:
            durable_terminal = str(
                getattr(intent, "decision_status", None) or intent.status
            )
            if durable_terminal != terminal_status:
                return None
        if intent.status == "pending":
            from app.services.write_intent_service import (
                medication_batch_plan_was_presented,
            )

            if not medication_batch_plan_was_presented(self.db, intent):
                return None
        source = (
            self.db.query(AgentMessage)
            .filter(
                AgentMessage.conversation_id == conversation_id,
                AgentMessage.id < prior.id,
            )
            .order_by(AgentMessage.id.desc())
            .first()
        )
        if (
            source is None
            or source.role != "user"
            or source.id != intent.target_id
        ):
            return None
        try:
            # Expiry is enforced by the atomic confirm operation below.  The
            # lookup must still resolve an expired plan so the deterministic
            # path can mark it terminal and tell the user what happened,
            # instead of falling through to an LLM turn.
            payload, _ = validate_medication_intake_intent(
                self.db,
                intent,
                require_unexpired=False,
            )
        except Exception as error:  # noqa: BLE001 — malformed plans never authorize a write
            logger.error(
                "[medication_batch] pending intent validation failed "
                "intent=%s user=%s error_type=%s",
                intent.id,
                user_id,
                type(error).__name__,
            )
            return None
        if (
            payload.get("conversation_id") != conversation_id
            or payload.get("source_message_id") != source.id
        ):
            return None
        return intent

    @staticmethod
    def _medication_batch_items_text(payload: Mapping[str, Any]) -> str:
        parts: list[str] = []
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("medication_name") or "").strip()
            dosage = str(item.get("actual_dosage") or "").strip()
            strength = str(item.get("observed_strength") or "").strip()
            if name and dosage:
                parts.append(
                    f"{name} {strength} × {dosage}"
                    if strength
                    else f"{name} {dosage}"
                )
        return "、".join(parts)

    @staticmethod
    def _medication_batch_safety_followup(
        alerts: Any,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Render the safety result produced inside the confirmation transaction.

        The shared service is the only evaluator.  Text confirmation and card
        clicks therefore surface exactly the same result, without rebuilding a
        Twin after commit or silently losing an incomplete-precheck advisory.
        """
        if not isinstance(alerts, list):
            alerts = []
        relevant: list[dict[str, Any]] = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            raw_severity = alert.get("severity")
            if isinstance(raw_severity, dict):
                raw_severity = raw_severity.get("value")
            try:
                severity = int(raw_severity)
            except (TypeError, ValueError):
                severity = 0
            if severity >= 3:
                relevant.append(alert)
        if not relevant:
            return "", []

        titles = "; ".join(
            str(alert.get("title") or "用药安全提醒").strip()
            for alert in relevant
        )
        incomplete = any(
            alert.get("rule_id") == "medication.safety_precheck_incomplete"
            for alert in relevant
        )
        suffix = f"\n\n⚠️ 安全提示: {titles}"
        if incomplete:
            suffix += (
                "。自动安全筛查未完整完成，这不代表当前用药组合安全；"
                "新增或调整用药前请咨询医生或药师。"
            )
        cards = [
            card
            for card in (
                _safety_alert_card_descriptor(alert) for alert in relevant
            )
            if card
        ]
        return suffix, cards

    def _medication_batch_terminal_result(
        self,
        *,
        intent: Any,
        payload: Mapping[str, Any],
        decision: Mapping[str, Any],
        recovery: bool = False,
    ) -> Dict[str, Any]:
        """Render only the service-owned logical terminal outcome."""
        from app.services.medication_intake_batch import WRITE_INTENT_KIND

        physical_status = str(decision.get("status") or "")
        decision_status = str(
            decision.get("decision_status") or physical_status
        )
        receipts = list(decision.get("write_receipts") or [])
        safety_alerts = list(decision.get("safety_alerts") or [])
        item_text = self._medication_batch_items_text(payload)
        expected_count = len(payload.get("items") or [])
        intent_id = int(intent.id)

        if decision_status == "executed" and physical_status == "executed":
            if len(receipts) != expected_count:
                return {
                    "intent_id": intent_id,
                    "decision_status": "executed",
                    "action": "confirm_reconciliation_required",
                    "reply": (
                        "这组用药确认已进入已执行状态，但逐项回执暂时无法核验。"
                        "为避免重复记录，请不要再次提交；请先查看用药记录。"
                    ),
                    "write_receipts": [],
                    "safety_alerts": [],
                    "pending_ids": [],
                    "pending_kinds": [],
                    "cards": [],
                    "completion_status": "error",
                    "tool_failures": [WRITE_INTENT_KIND],
                }
            safety_suffix, safety_cards = self._medication_batch_safety_followup(
                safety_alerts
            )
            return {
                "intent_id": intent_id,
                "decision_status": "executed",
                "action": "confirmed_recovery" if recovery else "confirmed",
                "reply": (
                    f"{'已核验' if recovery else '已记录'}本次服药："
                    f"{item_text}，共{len(receipts)}条。{safety_suffix}"
                ),
                "write_receipts": receipts,
                "safety_alerts": safety_alerts,
                "pending_ids": [],
                "pending_kinds": [],
                "cards": safety_cards,
                "completion_status": "complete",
                "tool_failures": [],
            }

        if (
            decision_status == "dismissed"
            and physical_status == "dismissed"
            and not receipts
        ):
            return {
                "intent_id": intent_id,
                "decision_status": "dismissed",
                "action": "dismissed_recovery" if recovery else "dismissed",
                "reply": f"已取消这组用药记录，没有写入：{item_text}。",
                "write_receipts": [],
                "safety_alerts": [],
                "pending_ids": [],
                "pending_kinds": [],
                "cards": [],
                "completion_status": "complete",
                "tool_failures": [],
            }

        if (
            decision_status == "expired"
            and physical_status == "dismissed"
            and not receipts
        ):
            return {
                "intent_id": intent_id,
                "decision_status": "expired",
                "action": "expired_recovery" if recovery else "expired",
                "reply": (
                    "这组用药确认已过期，没有写入。"
                    "请重新发送完整药名和本次实际服量。"
                ),
                "write_receipts": [],
                "safety_alerts": [],
                "pending_ids": [],
                "pending_kinds": [],
                "cards": [],
                "completion_status": "error",
                "tool_failures": [WRITE_INTENT_KIND],
            }

        logger.error(
            "[medication_batch] contradictory terminal result "
            "intent=%s physical=%s logical=%s receipts=%s",
            intent_id,
            physical_status,
            decision_status,
            len(receipts),
        )
        return {
            "intent_id": intent_id,
            "decision_status": None,
            "action": "terminal_reconciliation_required",
            "reply": (
                "这组用药记录的最终状态暂时无法核验。"
                "为避免重复写入，请不要再次提交；请先查看用药记录。"
            ),
            "write_receipts": [],
            "safety_alerts": [],
            "pending_ids": [],
            "pending_kinds": [],
            "cards": [],
            "completion_status": "error",
            "tool_failures": [WRITE_INTENT_KIND],
        }

    @staticmethod
    def _medication_batch_confirmation_card(
        intent: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build the itemized, owner-scoped manual-confirm card for chat."""
        from app.services.atomic_capability_registry import (
            attach_action_policy_metadata,
        )

        item_text = AgentExecutor._medication_batch_items_text(payload)
        taken_at = f"{payload.get('taken_date')} {payload.get('taken_time')}"
        actions = attach_action_policy_metadata("medication_draft", [
            {
                "id": f"medication-batch-confirm:{intent.id}",
                "label": "确认记录",
                "action": "write_intent.confirm",
                "endpoint": f"/write-intents/{intent.id}/confirm",
                "payload": {"write_intent_id": intent.id},
                "style": "primary",
                "requires_manual_confirm": True,
                "confirmation": {
                    "title": f"确认记录 {item_text}？",
                    "detail": (
                        f"将按 {taken_at} 一次写入 "
                        f"{len(payload.get('items') or [])} 条本次服药事实；"
                        "不会创建服药频次或提醒。"
                    ),
                    "confirm_label": "确认记录",
                    "cancel_label": "再看看",
                },
            },
            {
                "id": f"medication-batch-dismiss:{intent.id}",
                "label": "取消",
                "action": "write_intent.dismiss",
                "endpoint": f"/write-intents/{intent.id}/dismiss",
                "payload": {"write_intent_id": intent.id},
                "style": "secondary",
                "requires_manual_confirm": True,
            },
        ])
        return {
            "type": "medication_draft",
            "data": {
                # Kept for v1 clients and capability validation; itemized
                # clients render ``items`` below.
                "medication_name": item_text,
                "write_intent_id": int(intent.id),
                "plan_sha256": payload.get("plan_sha256"),
                "items": list(payload.get("items") or []),
                "taken_at": taken_at,
                "source": "chat",
                "boundary": (
                    "确认后只记录这次已服事实；若药名尚未登记，只建立停用状态的"
                    "基础条目用于关联本次记录，不推断处方频次，也不创建提醒。"
                ),
            },
            "actions": actions,
        }

    def _resolve_medication_batch_turn(
        self,
        *,
        user_id: int,
        conversation_id: int,
        user_message: Any,
        message: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolve proposal/confirm/dismiss without trusting model-generated flags."""
        from app.models.medication import Medication
        from app.services import write_intent_service
        from app.services.medication_intake_batch import (
            ExpiredMedicationIntakePlan,
            WRITE_INTENT_KIND,
            parse_medication_intake_batch,
            propose_medication_intake_batch,
            validate_medication_intake_intent,
        )

        action = _medication_batch_control_action(message)
        if action:
            intent = self._immediately_pending_medication_intent(
                user_id=user_id,
                conversation_id=conversation_id,
                current_user_message=user_message,
                action=action,
            )
            if intent is None:
                return None
            payload = intent.payload or {}
            intent_id = int(intent.id)
            try:
                decision = (
                    write_intent_service.dismiss(self.db, user_id, intent_id)
                    if action == "dismiss"
                    else write_intent_service.confirm(self.db, user_id, intent_id)
                )
                return self._medication_batch_terminal_result(
                    intent=intent,
                    payload=payload,
                    decision=decision,
                )
            except ExpiredMedicationIntakePlan:
                # The service atomically rolls back all health writes and marks
                # the logical expiry durable. Replay that exact result instead
                # of rebuilding it from the physical dismissed state.
                self.db.rollback()
                replayed = write_intent_service.confirm(
                    self.db, user_id, intent_id
                )
                return self._medication_batch_terminal_result(
                    intent=intent,
                    payload=payload,
                    decision=replayed,
                    recovery=True,
                )
            except Exception as error:  # noqa: BLE001 — honest failure; plan remains retryable
                logger.error(
                    "[medication_batch] terminal action failed "
                    "intent=%s user=%s error_type=%s",
                    intent_id,
                    user_id,
                    type(error).__name__,
                )
                self.db.rollback()
                # A failure after the service committed must never be reported
                # as "not written".  Reconcile durable state first.
                from app.models.write_intent import WriteIntent

                persisted = (
                    self.db.query(WriteIntent)
                    .filter(
                        WriteIntent.id == intent_id,
                        WriteIntent.user_id == user_id,
                        WriteIntent.kind == WRITE_INTENT_KIND,
                    )
                    .first()
                )
                if persisted is not None and persisted.status in {
                    "executed", "dismissed"
                }:
                    try:
                        replayed = write_intent_service.confirm(
                            self.db, user_id, persisted.id
                        )
                        return self._medication_batch_terminal_result(
                            intent=persisted,
                            payload=persisted.payload or payload,
                            decision=replayed,
                            recovery=True,
                        )
                    except Exception as reconciliation_error:  # noqa: BLE001
                        logger.error(
                            "[medication_batch] terminal reconciliation failed "
                            "intent=%s user=%s error_type=%s",
                            intent_id,
                            user_id,
                            type(reconciliation_error).__name__,
                        )
                    return {
                        "intent_id": intent_id,
                        "decision_status": None,
                        "action": "confirm_reconciliation_required",
                        "reply": (
                            "这组用药记录已有终态，但当前无法完整核验。"
                            "为避免重复记录，请不要再次提交；请先查看用药记录。"
                        ),
                        "write_receipts": [],
                        "pending_ids": [],
                        "pending_kinds": [],
                        "cards": [],
                        "completion_status": "error",
                        "tool_failures": [WRITE_INTENT_KIND],
                    }
                if action == "dismiss":
                    return {
                        "intent_id": intent_id,
                        "decision_status": None,
                        "action": "dismiss_failed",
                        "reply": (
                            "这组用药记录的取消未完成：服务端暂时无法确认取消结果。"
                            "你可以回复“取消”重试；在取消成功前，这组记录仍未写入。"
                        ),
                        "write_receipts": [],
                        "pending_ids": [intent_id],
                        "pending_kinds": [WRITE_INTENT_KIND],
                        "cards": [],
                        "completion_status": "error",
                        "tool_failures": [WRITE_INTENT_KIND],
                    }
                return {
                    "intent_id": intent_id,
                    "decision_status": None,
                    "action": "confirm_failed",
                    "reply": (
                        "这组用药记录没有写入：服务端未能完成整批确认。"
                        "你可以直接回复“确认”重试，或重新发送完整药名和本次服量。"
                    ),
                    "write_receipts": [],
                    "pending_ids": [intent_id],
                    "pending_kinds": [WRITE_INTENT_KIND],
                    "cards": [],
                    "completion_status": "error",
                    "tool_failures": [WRITE_INTENT_KIND],
                }

        # A worker can die after the model-owned proposal was committed but
        # before the assistant preview/checkpoint was finalized.  Recover that
        # exact source-bound plan before parsing or invoking any model again.
        intent = self._source_bound_medication_intent(
            user_id=user_id,
            conversation_id=conversation_id,
            source_message_id=int(user_message.id),
        )
        if intent is None:
            known_names = [
                row[0]
                for row in self.db.query(Medication.name)
                .filter(Medication.user_id == user_id)
                .all()
                if row[0]
            ]
            draft = parse_medication_intake_batch(message, known_names=known_names)
            if draft is None:
                return None
            try:
                intent = propose_medication_intake_batch(
                    self.db,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    source_message_id=user_message.id,
                    text=message,
                    reference_now=self._agent_kernel_reference_now(),
                )
            except Exception as error:  # noqa: BLE001 — recognized write must fail visibly
                logger.error(
                    "[medication_batch] proposal failed "
                    "user=%s source=%s error_type=%s",
                    user_id,
                    user_message.id,
                    type(error).__name__,
                )
                self.db.rollback()
                return {
                    "action": "proposal_failed",
                    "reply": (
                        "这组用药记录尚未建立确认计划，因此没有写入。"
                        "请稍后重试；如果仍失败，请逐项发送药名和本次服量。"
                    ),
                    "write_receipts": [],
                    "pending_ids": [],
                    "pending_kinds": [],
                    "cards": [],
                    "completion_status": "error",
                    "tool_failures": [WRITE_INTENT_KIND],
                }
        if intent is None:
            return None
        payload = intent.payload or {}
        item_text = self._medication_batch_items_text(payload)
        if intent.status in {"executed", "dismissed"}:
            terminal = write_intent_service.confirm(
                self.db, user_id, intent.id
            )
            return self._medication_batch_terminal_result(
                intent=intent,
                payload=payload,
                decision=terminal,
                recovery=True,
            )
        try:
            validate_medication_intake_intent(
                self.db,
                intent,
                require_unexpired=True,
            )
        except ExpiredMedicationIntakePlan:
            terminal = write_intent_service.expire_medication_batch(
                self.db, user_id, intent.id
            )
            return self._medication_batch_terminal_result(
                intent=intent,
                payload=payload,
                decision=terminal,
            )
        taken_at = f"{payload.get('taken_date')} {payload.get('taken_time')}"
        confirmation_card = self._medication_batch_confirmation_card(intent, payload)
        return {
            "action": "proposal",
            "reply": (
                f"请确认记录本次服药：{item_text}（{taken_at}）。"
                "回复“确认”后，我会一次写入全部记录；若药名尚未登记，只建立"
                "停用状态的基础条目用于关联本次事实，不推断处方频次，也不创建提醒；"
                "未确认前不会写入。"
            ),
            "write_receipts": [],
            "pending_ids": [intent.id],
            "pending_kinds": [WRITE_INTENT_KIND],
            "cards": [confirmation_card],
            "completion_status": "complete",
            "tool_failures": [],
        }

    async def _run_medication_batch_result(
        self,
        result: Dict[str, Any],
        *,
        svc: Any,
        conv: Any,
        user_id: int,
        client_turn_id: Optional[str],
        start_time: float,
    ) -> AsyncGenerator[Dict, None]:
        """Persist and stream one deterministic medication confirmation result."""
        from app.services.medication_intake_batch import WRITE_INTENT_KIND

        pending_ids = list(result.get("pending_ids") or [])
        pending_kinds = list(result.get("pending_kinds") or [])
        receipts = list(result.get("write_receipts") or [])
        safety_alerts = list(result.get("safety_alerts") or [])
        cards = list(result.get("cards") or [])
        completion_status = str(result.get("completion_status") or "complete")
        full_reply = str(result.get("reply") or "")
        self._turn_pending_write_intent_ids = pending_ids
        self._turn_pending_write_intent_kinds = pending_kinds

        turn_outcome = classify_agent_turn_outcome(
            completion_status=completion_status,
            final_text=full_reply,
            tool_failure_tools=result.get("tool_failures") or [],
            pending_confirmation_tools=(
                [WRITE_INTENT_KIND]
                if result.get("action") == "proposal"
                else []
            ),
            write_receipts=receipts,
            record_intent_no_tool=False,
        )
        elapsed_ms = int((time.time() - start_time) * 1000)
        kernel_trace = self._agent_kernel_trace_summary(status=completion_status)
        decision_status = result.get("decision_status")
        intent_id = result.get("intent_id")
        medication_batch_decision = None
        if decision_status in {"executed", "dismissed", "expired"}:
            try:
                normalized_intent_id = int(intent_id)
            except (TypeError, ValueError):
                normalized_intent_id = 0
            if normalized_intent_id > 0:
                medication_batch_decision = {
                    "intent_id": normalized_intent_id,
                    "status": decision_status,
                    "write_receipts": receipts,
                    "safety_alerts": safety_alerts,
                }
        meta_payload: Dict[str, Any] = {
            "elapsed_ms": elapsed_ms,
            "llm_ms": 0,
            "llm_rounds": 0,
            "llm_rounds_ms": [],
            "model": None,
            "selected_model": None,
            "answer_model": None,
            "tool_models": [],
            "fallback_reasons": [],
            "sources_used": ["服务端用药确认计划"],
            "tools_used": [],
            "write_receipts": receipts,
            "safety_alerts": safety_alerts,
            "pending_write_intent_ids": pending_ids,
            "pending_write_intent_kinds": pending_kinds,
            "cards": cards_for_persistence(cards),
            "finish_reason": "stop" if completion_status == "complete" else "error",
            "completion_status": completion_status,
            "record_intent_no_tool": False,
            "turn_outcome": turn_outcome,
            "mode": "medication_intake_batch",
            "kernel_trace": kernel_trace,
            "client_turn_finalized": True,
            **(
                {"medication_batch_decision": medication_batch_decision}
                if medication_batch_decision is not None
                else {}
            ),
            **({"client_turn_id": client_turn_id} if client_turn_id else {}),
        }
        conv.updated_at = datetime.now(UTC)
        assistant = svc.save_message(
            conv.id,
            "assistant",
            full_reply,
            meta=meta_payload,
            client_turn_id=client_turn_id,
            client_turn_user_id=user_id,
        )
        # Actionable output comes only after the exact itemized plan is durable.
        # The request_persisted event already ACKed the user's input, so this
        # short checkpoint does not weaken request durability.
        yield {
            "event": "agent_start",
            "data": {
                "message": (
                    "正在确认并记录用药..."
                    if result.get("action") in {"confirmed", "confirmed_recovery"}
                    else "正在核对用药记录..."
                ),
                "conversation_id": conv.id,
            },
        }
        if full_reply:
            yield {"event": "token", "data": {"content": full_reply}}
        for card in cards:
            yield {
                "event": "card",
                "data": {
                    "anchor": (
                        "medication_confirmation"
                        if card.get("type") == "medication_draft"
                        else "safety_alert"
                    ),
                    "descriptor": card,
                },
            }
        yield {
            "event": "done",
            "data": {
                **meta_payload,
                "conversation_id": conv.id,
                "message_id": assistant.id,
            },
        }

    async def _run_recipe_replay(
        self,
        recipe,
        svc,
        conv,
        user_msg,
        user_id: int,
        user_auth_token: Optional[str],
        client_turn_id: Optional[str],
        start_time: float,
    ) -> AsyncGenerator[Dict, None]:
        """Slice 3: 配方确定性重放 — 存好的工具序列逐步执行, 零 LLM。

        R4 不变量 (与直接调用完全一致, 见 procedure_recipe_service.replay):
        - 每步过 _auto_confirm_fast_record_args 同一确认门 (AUTO/typed_only/
          never_auto 原样生效); never_auto kind 重放返回 [NEEDS_CONFIRMATION]
          且**不写库**, 回复里如实告知 —— 绝不静默注入 confirmed。
        - args_template 只做确定性填充 ({{today}} → 当天), 无 LLM 改参。
        - 写步骤沿用主路径的 write checkpoint (in_flight → dispatch 状态),
          replacement worker 不会重复写。
        """
        from app.services import procedure_recipe_service as recipe_svc

        yield {"event": "agent_start", "data": {
            "message": f"按配方「{recipe.name}」执行...",
            "conversation_id": conv.id,
        }}

        tools_used: List[str] = []
        write_receipts: List[Dict[str, Any]] = []
        step_lines: List[str] = []
        record_cards: list[dict] = []
        needs_confirmation_labels: List[str] = []
        any_write_completed = False
        step_meta: List[Dict[str, Any]] = []

        self._http_client = httpx.AsyncClient(timeout=90.0)
        try:
            async for outcome in recipe_svc.replay(
                recipe, self,
                user_auth_token=user_auth_token,
                channel=self._turn_channel,
            ):
                tool = outcome.get("tool") or ""
                args = outcome.get("args") or {}
                index = outcome.get("step_index")
                if outcome.get("phase") == "start":
                    if tool and tool not in tools_used:
                        tools_used.append(tool)
                    yield {"event": "tool_call", "data": {
                        "tool": tool,
                        "args": json.dumps(args, ensure_ascii=False),
                        "round": 1,
                    }}
                    yield self._status_event(
                        "tool", detail=_tool_status_label(tool), round=1
                    )
                    yield self._progress_event(
                        "tool", round=1, label=_tool_progress_label(tool)
                    )
                    continue

                # phase == "result"
                result = outcome.get("result") or ""
                needs_confirmation = bool(outcome.get("needs_confirmation"))
                step_failed = bool(outcome.get("error"))
                label = recipe_svc.step_label({"tool": tool, "args_template": args})
                write_attempted = _write_tool_attempted(tool, args)
                write_completed = _write_tool_completed(tool, args, result)
                receipt = None
                if write_completed:
                    any_write_completed = True
                    receipt = _write_receipt_from_tool_result(
                        tool,
                        args,
                        result,
                    )
                    if receipt and not any(
                        item.get("operation_id") == receipt.get("operation_id")
                        for item in write_receipts
                    ):
                        write_receipts.append(receipt)
                    card = _health_record_card_descriptor(
                        args.get("record_type") or args.get("type"),
                        args.get("data") or {},
                        result,
                        write_verified=bool(
                            receipt and receipt.get("verified") is True
                        ),
                    )
                    if card:
                        record_cards.append(card)
                if write_attempted:
                    self._persist_turn_write_state(
                        user_msg,
                        status=_write_checkpoint_status_after_dispatch(result, receipt),
                        tool_name=tool,
                        parsed_args=args,
                        receipt=receipt,
                    )

                tool_event_data: Dict[str, Any] = {
                    "tool": tool,
                    "success": not result.startswith("Error"),
                    "preview": result[:200],
                    "result": result,
                    "write_attempted": write_attempted,
                    "write_completed": write_completed,
                    "recipe_step": index,
                }
                if receipt:
                    tool_event_data["receipt"] = receipt
                if write_attempted and not write_completed:
                    tool_event_data["success"] = False
                yield {"event": "tool_result", "data": tool_event_data}

                if needs_confirmation:
                    needs_confirmation_labels.append(label)
                    step_lines.append(f"⏸ 第{index}步 {label} — 需要你确认后才能写入")
                elif step_failed or (write_attempted and not write_completed):
                    step_lines.append(f"❌ 第{index}步 {label} — 没有成功写入")
                else:
                    step_lines.append(f"✅ 第{index}步 {label} — 已记录")
                step_meta.append({
                    "step_index": index,
                    "tool": tool,
                    "needs_confirmation": needs_confirmation,
                    "write_completed": write_completed,
                })
        except Exception as e:  # noqa: BLE001 — 重放异常 fail-loud 呈现, 不装成功
            logger.error(f"[agent_executor] recipe replay failed: {e}", exc_info=True)
            step_lines.append("❌ 配方执行中断: 出现内部错误, 未完成的步骤没有写入")
        finally:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

        # 写后安全检查 (与主路径同源: 确定性 SafetyGuardian, 与模型无关)
        safety_suffix = ""
        safety_cards: list[dict] = []
        if any_write_completed:
            try:
                from app.twin.builder import build_twin
                from app.agents.safety_guardian import evaluate_safety

                twin = build_twin(self.db, user_id, use_cache=True)
                report = evaluate_safety(twin)
                critical = [a for a in report.alerts if int(a.severity) >= 3]
                if critical:
                    alert_msgs = "; ".join(a.title for a in critical[:3])
                    safety_suffix = f"\n\n⚠️ 安全提示: {alert_msgs}"
                    safety_cards = [
                        card for card in (
                            _safety_alert_card_descriptor(a) for a in critical[:3]
                        )
                        if card
                    ]
            except Exception as e:  # noqa: BLE001
                # fail-loud:安全筛查抛错不静默放行(同写后主路径)。
                logger.error("Safety check after recipe replay failed: %s", e, exc_info=True)
                safety_suffix = (
                    "\n\n⚠️ 安全提示: 记录已保存,但自动安全筛查暂未完成。"
                    "如你此刻有明显不适、或刚记录的数值明显异常,请及时就医。"
                )

        reply_parts = [f"按配方「{recipe.name}」执行了 {len(step_lines)} 步:"]
        reply_parts.extend(step_lines)
        if needs_confirmation_labels:
            reply_parts.append(
                "需要确认的步骤没有写入。想补上的话, 请把那条记录单独发给我确认一次。"
            )
        full_reply = "\n".join(reply_parts) + safety_suffix

        try:
            recipe_svc.increment_use_count(self.db, recipe)
        except Exception as e:  # noqa: BLE001 — 计数失败不打死回合, 但可观测
            logger.warning(f"[agent_executor] recipe use_count 更新失败: {e}")

        yield {"event": "token", "data": {"content": full_reply}}

        ai_msg = svc.save_message(
            conv.id,
            "assistant",
            full_reply,
            client_turn_id=client_turn_id,
            client_turn_user_id=user_id,
        )
        conv.updated_at = datetime.now(UTC)
        elapsed_ms = int((time.time() - start_time) * 1000)
        response_cards = _merge_agent_card_descriptors(record_cards, safety_cards)
        kernel_trace = self._agent_kernel_trace_summary(status="complete")
        meta_payload: Dict[str, Any] = {
            "elapsed_ms": elapsed_ms,
            "llm_ms": 0,
            "llm_rounds": 0,
            "llm_rounds_ms": [],
            "model": None,
            "mode": "recipe_replay",
            "recipe": {"id": recipe.id, "name": recipe.name},
            "recipe_steps": step_meta,
            "sources_used": ["程序性配方"],
            "tools_used": tools_used,
            "write_receipts": write_receipts,
            "kernel_trace": kernel_trace,
            "cards": response_cards,
            "completion_status": "complete",
            "client_turn_finalized": True,
            **({"client_turn_id": client_turn_id} if client_turn_id else {}),
        }
        try:
            ai_msg.meta = meta_payload
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[agent_executor] recipe replay meta 写入失败: {e}")
        self.db.commit()

        yield {"event": "done", "data": {
            "conversation_id": conv.id,
            "message_id": ai_msg.id,
            **meta_payload,
        }}

    @staticmethod
    def _upload_chat_image(
        image_base64: str,
        image_type: str,
        user_id: int,
        object_key: str | None = None,
    ) -> str:
        from app.services.chat_utils import upload_chat_image
        return upload_chat_image(
            image_base64,
            user_id,
            image_type,
            object_key=object_key,
        )

    def _should_send_raw_images_to_primary_model(self, user_id: int) -> bool:
        """Return True when the active chat model should receive image parts directly."""

        try:
            from app.models.user_profile import UserProfile
            from app.services.llm.model_registry import get_active_model_id, get_model

            model_id = self._request_model_id
            profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not model_id and profile:
                model_id = getattr(profile, "llm_model_id", None)
            model_id = model_id or get_active_model_id()
            if not model_id:
                return False
            entry = get_model(model_id)
            return bool(
                entry
                and entry.provider == "langbridge-proxy"
                and str(entry.model).startswith("commercial/")
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Vision] primary model image capability check skipped: {e}")
            return False

    def _should_preprocess_attached_images(self, user_id: int, message: str) -> bool:
        """Keep food-photo sanitation/calibration ahead of every primary model.

        Commercial multimodal models may receive general images directly, but
        diet writes require the same deterministic structured path as every
        other provider so provider choice cannot change persistence accuracy.
        """
        intent = classify_agent_utterance(
            message,
            reference_now=self._agent_kernel_reference_now(),
        )
        if _is_explicit_aigc_media_draft_turn(message):
            # The AIGC service binds the uploaded image to its confirmation
            # record. Running food recognition here could turn an unrelated
            # photo into a diet candidate before that isolated flow begins.
            return False
        return (
            not self._should_send_raw_images_to_primary_model(user_id)
            or not (message or "").strip()
            or intent.domain == "diet"
            or self._is_default_image_analysis_prompt(message)
            or intent.is_write
        )

    def _build_tool_decision_system_prompt(self) -> str:
        """Build the compact, grounded prompt for a tool-selection-only round.

        Fast tool rounds never produce user-facing health content. They only
        select tools, so the full fast answer prompt would waste prefill budget
        without improving the later synthesis answer.
        """
        current_time = self._agent_kernel_reference_now().isoformat(timespec="seconds")
        return "\n".join((
            "你是用户的 AI 健康助理。本轮只负责选择并调用工具，不直接回答用户。",
            f"当前用户本地时间：{current_time}。相对时间必须以此为准，不得猜测。",
            "需要查询真实数据时调用 health_query；没有工具结果时不得编造数据。",
            "只有用户明确要求新增记录时才调用 health_record；修改或删除已有记录才调用 health_manage。",
            "纯查询、历史记录作为分析依据、或健康建议不得触发写入。",
            "工具调用后由后续模型生成面向用户的解释与安全建议。",
        ))

    def _build_system_prompt(
        self, user_id: int, conv_id: int, user_auth_token: Optional[str],
        lite: bool = False, intent_query: Optional[str] = None,
        health_evidence_runtime: bool = False,
    ) -> str:
        """构建统一 Agent 的 system prompt。

        lite=True (fast-routed 简单记录/查询回合): 只保留核心人格 + 行为准则
        (R4 医疗边界 / 绝不复述工具原始 JSON 的防回显规则 / 记录参数的 worked-example
        与单位默认指引 —— 弱快模型丢量参会把「饮水2000」记成默认值, 这段必须留) +
        build_lite_health_context (基础画像) + 自我标识。**跳过**所有分析 blob:基因规则库、
        原研药建议、健康世界观、肝脏趋势、血常规趋势、用药疗程、干预闭环、效应估计、记忆 ——
        这些是分析用的重 prefill, 对「今天喝了多少水」纯噪音且拉长首字延迟。
        lite=False (分析/建议/复盘等一切非快路由回合): 行为 100% 不变 (逐字节等同旧实现)。"""
        parts = [
            "你是用户的 AI 健康助理。你可以通过工具调用获取、记录和分析用户的健康数据。",
            "你是唯一的对话入口——用户的所有健康相关请求（记录数据、查询指标、深度分析、图片识别）都由你处理。",
            (
                "每轮用户消息前会附带系统生成的本轮时间信息。"
                "解析今天、昨天、前天、明天、昨晚、刚才、几点提醒、起床或入睡建议时，"
                "必须以其中的用户本地当前时间为唯一基准；若本轮时间信息缺失，不得猜测当前日期或时间。"
                "不得沿用历史消息中的旧日期或旧时间。"
            ),
            "",
            "## 工作方式",
            "1. 分析用户请求，决定需要调用哪些工具",
            "2. 调用工具获取或记录数据",
            "3. 基于返回的数据进行分析和推理",
            "4. 给出有据可依的建议",
            "5. 复合意图时在一次对话中同时处理（如'记一下吃了鱼油，看看对基因有什么影响' → 先记录后查询）",
            "",
            "## 数据记录规则",
            "- **核心原则：所有记录操作必须调用 health_record 工具才算完成。绝对不能口头说'已记录'而不调用工具。**",
            "- **必须使用系统提供的结构化工具调用；禁止输出 `<tool_code>`、`print(...)`、Python 代码或其他伪代码来表示调用。伪代码不会被视为完成记录。**",
            "- **新增记录**调用 health_record；**修改/删除已有记录**必须调用 health_manage。不要说'没有删除功能'。",
            "- 用户要删除重复记录时: 先 health_manage(list) 或 health_query(diet) 查候选 ID；如果用户已明确 ID, 直接 health_manage(delete)。",
            "- 用户说'删除这一餐'、'撤销这顿'、'我刚才不小心删除了'、'把晚餐删掉/恢复'时,这是管理已有饮食记录,绝不能把这句话作为 diet.food_items 新增一条晚餐;先查候选记录并确认。",
            "- 饮水、补剂打卡：直接执行，不需确认",
            "- 血压、血糖、体重：执行后复述确认数值（'已记录血压 138/92'）",
            "- 用户说'吃了/服用了XX'：若包含药名、药物剂型(胶囊/缓释片/颗粒/口服液等)、mg/毫克、处方/用药语境 → record_type=medication；补剂/保健品名(鱼油/维C/B族等) → record_type=supplement；明确食物或餐次 → record_type=diet",
            "- 用户说'早上的药都吃了' → record_type=supplement_group, timing=morning",
            "- 用户明确要设置提醒/闹钟/每天几点提醒,且已给出时间 → 调用 health_record(record_type=reminder, data={title,message,remind_at,recurrence})。每日提醒用 recurrence=daily; remind_at 必须是带 +08:00 的 ISO 时间; 只有 HH:MM 时按下一次北京时间生成。不能回复“系统接口限制”或让用户自己去手机/手表设置。",
            "- 用户要在时间窗内循环提醒(如 9:00 到 20:00 每 1.5 小时) → 一次调用 health_record(record_type=reminder, data={title,message,start_time,end_time,interval_minutes,recurrence}); 不要降级成单个开始时点。",
            "- 如果上一轮已在问提醒时段,用户只回复'9点到20点'或'10:30'这类时间,要继承上一轮的任务标题、内容和间隔,直接创建 reminder; 不要丢失上下文或重复询问。",
            "- 模糊数量：'几杯水' → 追问具体杯数再记录；'130多' → 追问具体数值",
            "- 时间归属：'昨天' → 记到昨天日期；'刚才' → 当前时间；未说明 → 今天",
            "- 用户只陈述'准备开始睡觉/开始睡眠/上床睡觉/准备入睡'这类当前开始睡眠事件 → 调用 health_record(record_type=event, data={title:'准备开始睡觉', occurred_at:'刚才或用户给出的时间'}); 不要用 record_type=sleep。record_type=sleep 只用于事后完整睡眠补录,必须有 bedtime、wake_time、sleep_quality。",
            "- 上述状态陈述若同时请求建议、分析或提问时，只回答问题，不自动记录；除非用户另外明确说“记录”“记一下”或“打卡”。例如'我准备睡觉了，给我一些建议'是建议请求，不调用 health_record。",
            "- 图片：用户发食物照片时，先用你的视觉能力识别图片中的食物名称和份量，然后调用 health_record(type=diet, data={meal_type, food_items, calories, protein, carbs, fat, fiber, record_date}) 记录。必须在 data 中填写完整的 food_items 字符串，不能传空 data。",
            "- **饮食记录必须包含热量和营养估算：识别食物后，根据食物种类和常见份量估算总热量(kcal)、蛋白质(g)、碳水(g)、脂肪(g)、膳食纤维(g)，填入 data.calories/protein/carbs/fat/fiber 字段一起保存。不要记完再问用户'要不要算热量'。**",
            "- **重要：调用 health_record 时 data 参数必须包含具体内容，不能为空对象 {}。如果你不确定内容，先问用户再记录。**",
            "- 用户明确要求制作健康行动相关图片、封面或 3-15 秒短视频时，可以使用 draft_aigc_media 创建确认草稿。它不会发送任何内容给百炼；确认卡片必须由用户亲自点击，后端才会向百炼发送草稿绑定的提示词和图生模式下当前消息的图片，并可能消耗 TokenPlan Credits 或产生费用。不能以文字中的“确认”代替卡片点击，也不能声称已经生成。",
            "- draft_aigc_media 成功后只需简短说明‘创作草稿已准备，请在创作卡片中确认’；不要引用‘上方/下方卡片’，不要重复费用、状态或操作说明，卡片会自行展示并持续更新任务状态。",
            "- 图生图片/图生视频只能用当前消息中附带的第一张图；没有图时请用户重新上传。生成完成前只能说“生成中”，不能把任务已接受说成“已生成”。",
            "- AIGC 内容只用于健康行动沟通（如饮食建议封面、晨间拉伸提示、补水提醒短视频）。不得生成医疗诊断、疗效承诺、处方或公开暴露个人健康隐私的素材。",
            "",
            "## 分析规则",
            "- 简单查询（'今天步数多少'）→ health_query",
            "- 用户问'昨天/最近上传的记录/报告/体检/检查'时,不要默认查综合可穿戴数据;优先调用 health_query(dimension='medical_exam', uploaded_days=1/7)。若包含 MRI/核磁/CT/X光/B超/胃镜/影像/膝关节 等关键词,同时传 keyword。",
            "- 用户问 MRI/核磁/CT/X光/B超/胃镜/影像报告时,调用 health_query(dimension='medical_exam', keyword='用户原词');不要说没看到报告,除非工具明确返回未找到。",
            "- 趋势分析（'最近睡眠怎么样'）→ health_analysis",
            "- 跨领域复杂问题（'我的补剂方案合理吗'、'从基因角度看我该怎么调整'）→ health_analysis(type=orchestrator, question=...)",
            "",
            "## 行为准则",
            "- 数据驱动：引用具体数据，不要泛泛而谈",
            "- 主动分析：不仅回答问题，还要发现潜在问题",
            "- 取数请求（列出/查询/显示/看一下…记录）：直接调 health_query 如实列出结果（含逐条时间/数值），你的职责本就涵盖记录、查询与分析——绝不要用「我只负责记录与查询」「无法提供分析/建议」这类自我设限开场白（医疗边界只按下方 R4，不用自我声明）。",
            "- 中文回复：简洁实用，给出可执行的建议",
            "- 严重异常（HRV持续偏低、SpO2<92%、血压异常）→ 建议就医",
            "- 涉及药物的建议：附加'请咨询医生'免责声明",
            "",
            # 意图门控(token 优化 #5):命中/未知才发,与旧行为逐字节一致
            *(_GENE_RULES_PROMPT_BLOCK if _wants_gene_rules_block(intent_query) else ()),
            *(_MENU_SHARE_PROMPT_BLOCK if _wants_menu_share_block(intent_query) else ()),
            "## 安全与边界 (R4 — 必须严格遵守)",
            (
                "- 本轮权威医学证据已由健康证据运行时完成检索、准入和注入；"
                "不得再次调用 knowledge_search 替换或扩张证据，只能使用本轮已审定 claim。"
                if health_evidence_runtime
                else
                "- 解读异常指标/给健康建议时,先调用 knowledge_search 取依据;"
                "无命中就如实说明依据来自通用知识,**绝不编造引用或具体研究**。"
            ),
            "- **不得把补剂/保健品作为针对某指标异常的治疗或\"护X\"方案推荐**(例:不得说\"姜黄素/NAC 护肝\")。补剂相关一律表述为\"是否需要请医生评估\";任何剂量数字必须注明\"须医生确认\"。",
            "- 任何把指标改善归因于某项干预(如\"ALT 下降=某方案有效\")**必须标注\"相关性,非因果\"**,不得下因果结论。",
            "- **不得对结构性发现下\"无需处理/不用管\"的临床判断**;改为\"通常定期随访,以医生意见为准\"。",
            "- 若工具结果带有『数据合理性提示』(或 _data_plausibility_warning 字段),先把该数值当作疑似录入错误、提示用户核实原始报告,核实前不要据此下结论;**若用户确认数值属实,仍须按其严重程度正常处置(例如危急值建议就医)**,不得因『疑似错误』而忽略一个可能真实的危急值。",
            "- 不做诊断;不下诊断标签(如不直接断言\"代谢综合征\",用\"…的风险信号\"并建议就医确认)。",
            "- 不要说\"你的诊断非常准确\"。用户自述疼痛/功能问题时,改为\"你的描述提示可能存在某种模式,需要结合医生/康复师评估\";训练建议只作为健康管理/康复辅助动作,不是诊断或治疗处方。",
            "- **绝对不要把工具返回的原始 JSON / 数组 / 字段名(如 record_date、meal_type、food_items、`[{...}]`)复述或粘贴进回复。工具结果只供你阅读,必须用自然语言概括给用户**(例:今天只有早餐记录,没有午餐;而不是把 `[{\"record_date\":...,\"meal_type\":\"breakfast\",...}]` 贴出来)。",
        ]

        # 注入 ak-kbase gene_knowledge 高优先级警示规则（PM/缺陷/纯合风险）
        # lite 回合跳过: 分析用的基因规则库对「记录喝水/多少水」是纯 prefill 噪音。
        if not lite and not health_evidence_runtime:
            try:
                from app.services.gene_rules_registry import get_registry
                gene_section = get_registry().system_prompt_section(user_phenotypes=None)
                if gene_section:
                    parts.append("\n" + gene_section)
            except Exception:
                pass

        # 健康证据运行时已经从一份冻结 Twin 编译了 query-specific packet；
        # 不再叠加旧版泛化档案，避免重复、冲突和“表里有就声称用过”。
        if not health_evidence_runtime:
            try:
                from app.services.health_context_lite_service import (
                    build_lite_health_context, _get_time_period,
                )
                # P2 意图分级: intent_query 存在时按纯知识 vs 个人判读裁剪个人上下文预算;
                # None (默认 / 多模型综合入口) → 全量注入, 零回归。
                health_ctx = build_lite_health_context(self.db, user_id, intent=intent_query)
                if health_ctx:
                    parts.append("\n## 用户健康档案")
                    parts.append(health_ctx)

                _, period = _get_time_period()
                parts.append(f"\n当前时段: {period}")
            except Exception as e:
                logger.warning(f"Agent 健康上下文注入失败: {e}")

        # ──── 分析 blob (仅 full 回合注入) ────
        # 下面这一组都是给分析/建议/复盘用的重上下文: 原研药建议、健康世界观、肝脏/血常规
        # 趋势、用药疗程、干预闭环、N-of-1 效应估计、对话记忆。fast-routed 简单记录/查询回合
        # (lite=True) 全部跳过 —— 对「记录喝水」「今天喝了多少水」无用, 只增加 prefill 与噪音。
        if not lite and not health_evidence_runtime:
            # 注入原研药可换建议(基于在用药;已采纳/忽略的已被抑制,不会重复推荐)
            try:
                from app.services.originator_recommendations import originator_recs_prompt_blob
                blob = originator_recs_prompt_blob(self.db, user_id)
                if blob:
                    parts.append("\n" + blob)
            except Exception as e:
                logger.warning(f"Agent 原研药建议注入失败: {e}")

            # 注入健康世界观(四定律 + 四层 + 症状级转诊红线)—— 统一建议哲学
            try:
                from app.services.health_worldview import worldview_prompt_blob
                parts.append("\n" + worldview_prompt_blob(include_triage=True))
            except Exception as e:
                logger.warning(f"Agent 世界观注入失败: {e}")

            # 注入肝脏趋势(消费历史肝酶;FIB-4/脂肪肝风险提示,非诊断)
            try:
                from app.services.liver_health import liver_prompt_blob
                from app.models.user import User as _User
                from datetime import date as _date
                _u = self.db.query(_User).filter(_User.id == user_id).first()
                _age = None
                if _u and _u.birth_date:
                    _t = _date.today()
                    _age = float(_t.year - _u.birth_date.year -
                                 ((_t.month, _t.day) < (_u.birth_date.month, _u.birth_date.day)))
                blob = liver_prompt_blob(self.db, user_id, age=_age)
                if blob:
                    parts.append("\n" + blob)
            except Exception as e:
                logger.warning(f"Agent 肝脏趋势注入失败: {e}")

            # 注入血常规趋势(消费历史 CBC;红细胞系同向偏高/中性-淋巴倒置提示,非诊断)
            try:
                from app.services.blood_routine import blood_routine_prompt_blob
                from app.models.user import User as _User
                _u = self.db.query(_User).filter(_User.id == user_id).first()
                _sex = _u.gender if _u else None
                blob = blood_routine_prompt_blob(self.db, user_id, sex=_sex)
                if blob:
                    parts.append("\n" + blob)
            except Exception as e:
                logger.warning(f"Agent 血常规趋势注入失败: {e}")

            # 注入用药疗程提醒(即将结束的疗程 + 建议复查;胃溃疡 PPI 疗程等)
            try:
                from app.services.medication_course_service import course_prompt_blob
                blob = course_prompt_blob(self.db, user_id)
                if blob:
                    parts.append("\n" + blob)
            except Exception as e:
                logger.warning(f"Agent 疗程提醒注入失败: {e}")

            # 注入干预闭环主动提议(有异常代谢杠杆 + 无 active 周期 → 可提议开 N-of-1 周期)
            try:
                from app.services.intervention_cycle_service import intervention_proposal_prompt_blob
                blob = intervention_proposal_prompt_blob(self.db, user_id)
                if blob:
                    parts.append("\n" + blob)
            except Exception as e:
                logger.warning(f"Agent 干预闭环提议注入失败: {e}")

            # 注入 N-of-1 干预效应估计(active/近期周期 + 复查数据 → 个人化效应后验)。
            # 无周期/无复查 → 空串不注入(Phase 1, effect_estimator)。
            try:
                from app.services.effect_estimator import effect_estimate_prompt_blob
                blob = effect_estimate_prompt_blob(self.db, user_id)
                if blob:
                    parts.append("\n" + blob)
            except Exception as e:
                logger.warning(f"Agent 干预效应估计注入失败: {e}")

            # 记忆已由 build_lite_health_context(lite/full 都调,见 health_context_lite_service
            # 的「用户历史记忆」段)注入一次,自带 "用户历史记忆:" 标签 —— 此处曾重复注入 limit=5,
            # 造成同一批记忆进 prompt 两遍 + 一次冗余 DB 往返。去重(零信息损失,记忆仍在)。

        # 告诉 LLM 自己是哪个模型 — 用户问 "你是什么模型" 时如实答
        try:
            from app.services.llm.model_registry import get_active_model_id, get_model
            from app.config import settings as _settings
            active_id = get_active_model_id()
            if active_id:
                entry = get_model(active_id)
                if entry:
                    model_label = f"{entry.label} ({entry.model})"
                else:
                    model_label = active_id
            else:
                # 回落到 settings 默认
                provider = _settings.llm_provider
                if provider == "openai":
                    model_label = f"OpenAI {_settings.openai_model}"
                elif provider == "tokenplan":
                    model_label = f"Aliyun TokenPlan {_settings.tokenplan_model}"
                else:
                    model_label = provider
            parts.append(
                "\n## 自我标识\n"
                f"- 你当前由 **{model_label}** 驱动。\n"
                "- 用户若问'你是什么模型'/'你用的是哪家 AI'/'底层模型版本'之类问题, 如实回答上面的 model_label.\n"
                "- 不要自称是 ChatGPT / Claude / 其他 — 以用户 admin 切换的为准."
            )
        except Exception:
            pass

        return "\n".join(parts)

    def _build_system_knowledge_prompt_context(self, user_id: int, message: str) -> str:
        """Render message-scoped system KB matches for the active chat turn.

        Mobile private chat uses `/agent/stream`, not the orchestrator synthesis
        path. Evidence cards emitted at `done` time are useful for UI, but too
        late for the LLM to ground its answer. This prompt block keeps the same
        reviewed KB source as the card and injects only bounded summaries.
        """

        evidence_card = self._build_system_knowledge_evidence_card(user_id, message)
        if not evidence_card:
            return ""
        return self._render_system_knowledge_evidence_card_for_prompt(evidence_card)

    def _build_system_knowledge_evidence_card(self, user_id: int, message: str) -> dict | None:
        """Per-turn memoized system-KB evidence card (A4, plan rank9).

        The card was computed twice per turn — pre-round-1 (prompt grounding) and
        again at `done` (UI card) — each potentially triggering a full
        build_twin(use_cache=False) rebuild that delays `done`/receipts and
        `/send` replies. Memoize per (user_id, message): pre-round-1 computes and
        caches; `done` reuses it. If a Twin-mutating write happened this turn
        (_turn_twin_write_occurred), the cache is bypassed so the done-time card
        reflects the post-write Twin (rebuilt once). The compute path keeps
        use_cache=False, so the rebuild-on-write is always fresh regardless of
        which write endpoints invalidate the Twin cache — see
        _compute_system_knowledge_evidence_card.
        """
        key = (user_id, message)
        if (
            self._turn_evidence_card is not _TURN_CARD_UNSET
            and self._turn_evidence_card_key == key
            and not self._turn_twin_write_occurred
        ):
            return self._turn_evidence_card
        card = self._compute_system_knowledge_evidence_card(user_id, message)
        self._turn_evidence_card = card
        self._turn_evidence_card_key = key
        return card

    def _compute_system_knowledge_evidence_card(self, user_id: int, message: str) -> dict | None:
        """Compute the system-KB evidence card for this chat turn (no memo).

        Prefer explicit message mentions so direct gene questions produce the
        most relevant card. If the message has no explicit entity, fall back to
        the user's Twin so the same KB evidence is visible in mobile metadata,
        not only hidden inside the prompt.
        """

        try:
            from app.services.system_knowledge_service import (
                build_evidence_card_for_twin,
                build_evidence_card_for_message,
                system_kb_twin_payload_from_health_twin,
            )

            evidence_card = build_evidence_card_for_message(self.db, message)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[agent_executor] system KB prompt lookup skipped: {e}")
            return None

        if evidence_card:
            return evidence_card

        if not _allow_twin_evidence_fallback(message):
            return None

        try:
            from app.twin.builder import build_twin

            # Chat prompt grounding must reflect the latest imported labs/genes.
            # Cached Twin can be stale immediately after upload/import (those
            # endpoints do not all invalidate the Twin cache), and then the
            # system KB evidence block silently disappears. A4 keeps use_cache=
            # False here on purpose (the common health_record POST endpoints —
            # water/weight/BP/diet/supplement — do NOT invalidate the Twin cache,
            # so use_cache=True would serve a stale pre-write Twin). The A4 perf
            # win comes from the per-turn memo above (dedup the double build), not
            # from a cache flip; correctness is unconditional.
            twin = build_twin(self.db, user_id, use_cache=False)
            return build_evidence_card_for_twin(
                self.db,
                system_kb_twin_payload_from_health_twin(twin),
                message=message,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[agent_executor] system KB twin card lookup skipped: {e}")
            return None

    @staticmethod
    def _render_system_knowledge_evidence_card_for_prompt(evidence_card: dict) -> str:
        from app.services.system_knowledge_service import CLAIM_BOUNDARY

        data = evidence_card.get("data") or {}
        entity = data.get("entity") or {}
        claims = data.get("claims") or []
        if not claims:
            return ""

        lines = [
            "## 系统知识库相关条目",
            "下面是系统级 LLM Wiki V2 的已审核知识条目。回答本轮问题时必须优先使用这些条目，"
            "并保留不确定性边界；不要把它们扩写成诊断、治疗或处方。",
            "如果输出具体饮食/补剂/运动建议，必须显式标注所依据的 claim_id；"
            "没有足够 evidence_refs 时要写明“模型推断”。",
        ]
        if entity:
            title = entity.get("title") or entity.get("entity_id") or entity.get("doc_id")
            summary = entity.get("summary")
            line = f"- 实体: {title} ({entity.get('doc_id')})"
            if summary:
                line += f": {summary}"
            lines.append(line)

        for claim in claims[:3]:
            sources = ", ".join(claim.get("sources") or [])
            confidence = claim.get("confidence")
            confidence_text = f"{confidence:.2f}" if isinstance(confidence, float) else "n/a"
            line = (
                f"- Claim: {claim.get('title') or claim.get('doc_id')} "
                f"[{claim.get('evidence_level') or '?'} conf={confidence_text}] "
                f"({claim.get('doc_id')})"
            )
            summary = claim.get("summary")
            if summary:
                line += f": {summary}"
            if sources:
                line += f" 来源: {sources}"
            lines.append(line)

        lines.append(f"边界: {data.get('claim_boundary') or CLAIM_BOUNDARY}")
        rendered = "\n".join(lines)
        if len(rendered) <= 1500:
            return rendered
        return rendered[:1497].rstrip() + "..."

    def _resolve_chat_provider(self, tools: Optional[List[Dict]]):
        """解析本次回合应使用的 provider + 是否传 tools。

        被 _call_llm (非流式) 和 _call_llm_stream (流式) 共用,确保两条路径的
        provider 路由完全一致 (fast-record / request-model / user-pref
        tool-stripping)。返回 (provider, pass_tools)。

        副作用: 把本次解析出的 effective model_id 记到 self._last_effective_model_id
        (2-tuple 返回契约不变, 既有 test 依赖)。供非流式桥 / 死亡备忘复用。
        """
        provider = None
        # 本回合最终会用到的 model_id (仅在能确定时填), 供工具能力门控判定。
        effective_model_id: Optional[str] = None

        # F3a 回合内 provider 死亡备忘: 若本回合首选的 request/偏好 model 在同一次 run
        # 里已经失败过, 不再重建它 (省掉每轮 ~19s 死等), 直接走稳定回退选择。
        # 彻底死 (无工具轮也失败) → 全跳; 仅工具轮死 → 只有本轮带工具时跳。
        request_model_dead = bool(
            self._request_model_id
            and (
                self._request_model_id in self._dead_provider_model_ids
                or (
                    bool(tools)
                    and self._request_model_id in self._tool_dead_provider_model_ids
                )
            )
        )

        # Mac/桌面端手动路由: extra_context.model_id 是 model_registry 里的 id,
        # 只影响本次请求, 不改 user_profile 持久偏好.
        if provider is None and self._request_model_id and not request_model_dead:
            try:
                from app.services.llm.factory import create_provider_for_model_id
                provider = create_provider_for_model_id(self._request_model_id)
                effective_model_id = self._request_model_id
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "[agent_executor] request model override %s unavailable, fallback: %s",
                    self._request_model_id,
                    e,
                )
                provider = None

        if request_model_dead:
            # 首选模型本回合已死: 记一条日志, 直接落到稳定回退 (工具轮走可靠工具模型)。
            logger.info(
                "[agent_executor] 本回合跳过已失败 provider=%s (dead), 走稳定回退",
                self._request_model_id,
            )
            self._record_model_fallback_reason("selected_provider_dead_this_turn")
            provider = self._stable_fallback_provider(bool(tools))
            # effective_model_id 保持 None: 稳定回退已自带工具门控, 下方 gate 不再重复。
            self._last_effective_model_id = None
            return provider, tools

        # 回退到默认 provider — 不传 model, 让 provider 用 init 时的默认
        # 2026-05-13: 用户级 LLM 偏好 — 优先读 user_profile.llm_model_id
        if provider is None and self._current_user_id:
            from app.services.llm.factory import create_provider_for_user
            provider = create_provider_for_user(self._current_user_id, self.db)
            effective_model_id = self._user_effective_model_id()
        elif provider is None:
            from app.services.llm.factory import get_llm_provider
            provider = get_llm_provider()
            from app.services.llm.model_registry import get_active_model_id
            effective_model_id = get_active_model_id()

        # Some OpenAI-compatible gateways treat an explicit empty tools array as
        # a tool-mode request and can return content="" with finish_reason="stop".
        pass_tools = tools

        # ──── 工具决策轮快路由 (延迟优化, flag 门控, fail-closed) ────
        # 只把**工具决策轮** (本回合带 tools) 降到一个 fast + reliable_tool_calling 模型;
        # 合成/答案轮 (round_tools=[] → pass_tools falsy) 恒不命中, 仍由质量模型生成医疗正文。
        # 生产实测: 「我胃还有点痛,怎么办?」的 tool 轮 34s (qwen3.7-max reasoning) 主导时延,
        # 但该轮只需吐一个 health_record 结构化 tool_call —— 不需要重推理模型。
        # 该分支只改**默认/偏好模型**路径 (无显式 UI 选模型), 且 fail-closed:命中新档一律
        # 换成 reliable_tool_calling 的 fast 模型, 无则维持现状。命中后 effective_model_id
        # 更新为该 fast 模型, 下方工具门控/非流式判定据此运作。
        if pass_tools:
            fast_tool = self._maybe_fast_route_tool_round(effective_model_id)
            if fast_tool is not None:
                provider, effective_model_id = fast_tool

        # ──── 工具调用能力门控 (从源头减少弱模型吐坏工具调用; #147/#161 兜底解析仍在) ────
        # 仅当本回合确实要传 tools 且已确定的 effective_model 不可靠时, 才换一个可靠模型。
        # 拿不准 (effective_model_id=None / 未注册) → 保守不动, 依赖兜底解析。
        # fast-record 只压缩 prompt / 自动确认, 不再偷偷切模型。为避免用户显式选择的
        # 模型又被工具门控改掉, 该路径继续依赖 #147/#161 的兜底解析。
        if pass_tools and not self._prefer_fast_record_model:
            gated = self._gate_tool_provider(effective_model_id)
            if gated is not None:
                provider, effective_model_id = gated

        self._last_effective_model_id = effective_model_id
        return provider, pass_tools

    def _maybe_fast_route_tool_round(self, effective_model_id: Optional[str]):
        """工具决策轮 → fast + reliable_tool_calling 模型 (flag 门控, fail-closed)。

        命中时返回 (fast_provider, fast_model_id);不命中 → None (维持现状,零变更)。

        触发条件 (全部满足):
          1. settings.task_tiered_routing 开 (flag off → 恒 None = 逐字节现状);
          2. 非既有整轮快路由 (_prefer_fast_record_model / _fast_route_simple_turn):
             那两条已把整轮 (含合成) 降到 fast, 不再叠加;
          3. task_routing 里 "tool_routing" 档确被授权降 fast (单一真源不变量);
          4. 存在一个 fast 档的 reliable_tool_calling=True 可用模型。
        任一不满足 → None。这样 fast 模型吐坏工具调用时, 既有 tool-turn failover +
        #147/#161 三层兜底解析仍是安全网 (被换后的 fast 模型走同一 _call_llm/_stream 路径)。

        A1 (2026-07-12, 生产 190/231 回合此前零路由): 显式 UI 选模型 (_request_model_id)
        **不再豁免**本快路由。工具决策轮是不可见的内部决策 (mac/mobile 分别显示 回答/工具
        两个模型), 「选择器显示什么就用什么」只约束**面向用户的答案轮**, 不约束工具轮。
        安全边界仍由 _turn_any_tool_executed 门守住: 只有**首个工具决策轮** (尚无工具执行)
        才降 fast; 一旦跑过工具, 后续合成/答案轮恒返回 None → 落在显式选定的强模型上产出
        医疗正文。fast 轮若直接答文本 → 既有丢弃+强模型重合成兜底 (面向用户正文绝不来自 fast)。
        """
        from app.config import settings

        if not getattr(settings, "task_tiered_routing", False):
            return None
        # 不叠加既有整轮快路由 (那两条已把含合成的整轮降 fast)。显式 UI 选模型不在此
        # 豁免 —— 只有下面 _turn_any_tool_executed 门放行的**首个工具决策轮**会被降 fast,
        # 答案轮由该门 + round_tools=[] 保证仍落在显式模型上。
        if self._prefer_fast_record_model or self._fast_route_simple_turn:
            return None
        # 破坏性(删/改/撤销)/ 同步意图 → 工具决策留强模型(弱 fast 不可靠,生产实证:
        # 「帮我同步」「删除早餐」被降 fast 后反复失败;强模型 23:19 同句 status=complete)。
        # 这是 sync 簇的实际失败路径(「同步」不在 record/query 意图正则里 → 只经此工具轮快路由)。
        if _needs_reliable_tool_model(getattr(self, "_current_turn_user_message", "")):
            return None
        # 否定("别记/记在心里")→ 工具决策留强模型(与整轮快路由同门):弱 fast 只靠 tool-schema
        # 软指令拒记不稳,强模型更可靠地"不记 + 不谎报已记"。三条 fast 路径统一排除的第三条。
        if classify_agent_utterance(
            getattr(self, "_current_turn_user_message", "") or ""
        ).reason == "negated_write":
            return None
        # 只降**首个工具决策轮**: 默认路径下合成轮仍带 tools, 一旦跑过工具就留强模型
        # (安全: 工具后那一轮多半是写医疗正文的合成轮)。首轮直接答文本→安全兜底丢弃重合成。
        if self._turn_any_tool_executed:
            return None
        try:
            from app.services.llm.task_routing import _FAST_ELIGIBLE_TIERS
            from app.services.llm.model_registry import (
                pick_reliable_tool_model_id,
                get_model,
            )
        except Exception:  # noqa: BLE001 — 快路由不可用绝不断主链路
            return None
        # 单一真源不变量:该内部档必须被显式授权降 fast, 否则不走 (防有人偷偷去授权后此处失守)。
        if "tool_routing" not in _FAST_ELIGIBLE_TIERS:
            return None
        # 具体模型必须 reliable_tool_calling=True (tool 轮几乎必调工具, 不会调工具的快模型
        # 会静默丢数据) 且真是 fast 档。pick_reliable_tool_model_id(near="fast") 优先 fast 档
        # 的可靠模型;拿到后再核 speed_tier=="fast", 不是则视为无可用 fast → 维持现状。
        try:
            fast_id = pick_reliable_tool_model_id(near_speed_tier="fast")
        except Exception:  # noqa: BLE001
            return None
        if not fast_id or fast_id == effective_model_id:
            return None
        entry = get_model(fast_id)
        if entry is None or entry.speed_tier != "fast" or not entry.reliable_tool_calling:
            # 无 fast 档可靠模型 (只回退到 balanced/reasoning) → 不做快路由, fail-open 现状。
            return None
        try:
            from app.services.llm.factory import create_provider_for_model_id
            provider = create_provider_for_model_id(fast_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[agent_executor] tool-round fast route %s unavailable, keep default: %s",
                fast_id, e,
            )
            return None
        # 标记本轮为 fast 工具决策轮: 调用方 (run_stream 主循环) 据此
        # (a) 不 live 下发该轮 content; (b) 该轮无 tool_calls 直接答文本时丢弃并在强模型重合成。
        self._tool_round_fast_routed = True
        self._record_model_fallback_reason("tool_round_fast_routed")
        logger.info(
            "[agent_executor] tool-round fast route: %s -> %s (user=%s)",
            effective_model_id, fast_id, self._current_user_id,
        )
        return provider, fast_id

    def _user_effective_model_id(self) -> Optional[str]:
        """复算 create_provider_for_user 选中的 model_id (admin global / user pref),
        仅用于工具门控判定; 读不到则 None (不门控)。不重复建 provider。"""
        if not self._current_user_id:
            return None
        try:
            from app.models.user_profile import UserProfile
            profile = (
                self.db.query(UserProfile)
                .filter(UserProfile.user_id == self._current_user_id)
                .first()
            )
            pref = getattr(profile, "llm_model_id", None) if profile else None
            if pref:
                return pref
        except Exception:  # noqa: BLE001 — 门控判定不应让主链路崩, 读失败=不门控
            return None
        from app.services.llm.model_registry import get_active_model_id
        return get_active_model_id()

    def _should_synthesize_with_requested_model_after_tools(self, tool_executed_count: int) -> bool:
        """After fallback tool calls, let the user's manual model own the final answer."""

        if tool_executed_count <= 0 or not self._request_model_id or self._prefer_fast_record_model:
            return False
        if self._request_model_tool_fallback_used:
            return True
        try:
            from app.services.llm.model_registry import is_reliable_tool_caller

            return not is_reliable_tool_caller(self._request_model_id)
        except Exception:  # noqa: BLE001
            return False

    def _gate_tool_provider(self, effective_model_id: Optional[str]):
        """Return a reliable tool provider and its model ID, or ``None``.

        无可回退的可靠+可用模型 (配置缺失) → 返回 None, 维持现状 (依赖兜底解析)。
        """
        from app.services.llm.model_registry import (
            is_reliable_tool_caller,
            pick_reliable_tool_model_id,
            get_model,
        )
        if is_reliable_tool_caller(effective_model_id):
            return None
        entry = get_model(effective_model_id) if effective_model_id else None
        near = entry.speed_tier if entry else None
        fallback_id = pick_reliable_tool_model_id(near_speed_tier=near)
        if not fallback_id or fallback_id == effective_model_id:
            logger.warning(
                "[agent_executor] tool task on unreliable model %s but no reliable "
                "fallback available; relying on defensive tool-call parsing",
                effective_model_id,
            )
            return None
        try:
            from app.services.llm.factory import create_provider_for_model_id
            provider = create_provider_for_model_id(fallback_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[agent_executor] reliable fallback %s unavailable, keep %s: %s",
                fallback_id, effective_model_id, e,
            )
            return None
        logger.info(
            "[agent_executor] tool task on unreliable model %s -> fallback to %s (user=%s)",
            effective_model_id, fallback_id, self._current_user_id,
        )
        if effective_model_id == self._request_model_id:
            self._record_model_fallback_reason("selected_model_tool_unreliable")
        else:
            self._record_model_fallback_reason("preferred_model_tool_unreliable")
        return provider, fallback_id

    def _remember_dead_provider(self, tool_specific: bool) -> None:
        """F3a: 把本轮刚失败的 selected provider 的 model_id 记入回合内死亡备忘。

        只记 request_model_id (mac/桌面显式选/fast-route 填充的注册 id) 或本次解析出的
        effective_model_id。默认 provider (无注册 id, effective=None) 无法记忆 — 但它
        本就是稳定回退目标, 不会陷入"每轮重试昂贵网关"的循环, 无需记。

        tool_specific=True: 失败只发生在工具轮 (如商用网关不实现非流式 tool-calling),
            仅记入 _tool_dead —— 之后的工具轮跳过它, 但无工具的合成轮仍可用它。
        tool_specific=False: 无工具轮也失败 = 彻底死, 记入 _dead —— 所有后续轮跳过。
        """
        target = (
            self._tool_dead_provider_model_ids
            if tool_specific
            else self._dead_provider_model_ids
        )
        for mid in (self._request_model_id, self._last_effective_model_id):
            if mid:
                target.add(mid)

    def _stable_fallback_provider(self, pass_tools: bool, failed_provider=None):
        """选定 provider 失败/已死时用的稳定回退 provider — failover 单一真源。

        F2: 本轮**带工具**时, 回退目标必须经同一可靠工具模型选择逻辑
        (复用 pick_reliable_tool_model_id + create_provider_for_model_id), 不许落到
        MiniMax/glm 家族弱工具模型 (生产事故: 默认 tokenplan = MiniMax-M2.5 吐 XML
        文本工具调用)。无可靠模型可用时才回默认 tokenplan 并 log。
        已知失败 provider 时, 工具轮和非工具轮都必须离开该故障域；例如 TokenPlan
        月额度耗尽后, 切换另一个 TokenPlan model id 仍会失败。无法识别失败域时,
        非工具轮维持既有行为 (默认 tokenplan provider)。

        始终 fail-open 到"有一个可用 provider": 可靠模型不可用 → 默认 tokenplan;
        默认 tokenplan 也建不了 → 全局单例 provider。任何一步都不把回合打死。
        """
        from app.services.llm.factory import create_llm_provider, get_llm_provider
        from app.services.llm.pii_scrub import wrap_provider_pii_scrub
        from app.services.llm.usage_tracker import wrap_provider

        failed_provider_name = str(
            getattr(failed_provider, "provider_name", "") or ""
        ).strip()
        excluded_providers = {failed_provider_name} if failed_provider_name else set()

        # A fallback must leave the failed provider's failure domain. TokenPlan
        # model IDs share one account quota, so switching qwen IDs is not a
        # meaningful recovery from a TokenPlan quota failure.
        if pass_tools or excluded_providers:
            from app.services.llm.model_registry import pick_reliable_tool_model_id
            fallback_id = pick_reliable_tool_model_id(
                exclude_providers=excluded_providers,
            )
            if fallback_id:
                try:
                    from app.services.llm.factory import create_provider_for_model_id
                    provider = create_provider_for_model_id(fallback_id)
                    self._last_provider_model_name = (
                        getattr(provider, "model", None) or fallback_id
                    )
                    logger.info(
                        "[agent_executor] failover provider=%s -> model=%s",
                        failed_provider_name or "unknown", fallback_id,
                    )
                    return provider
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "[agent_executor] reliable failover model %s unavailable, "
                        "falling back to default tokenplan: %s",
                        fallback_id, e,
                    )
            else:
                logger.warning(
                    "[agent_executor] no cross-provider reliable fallback available "
                    "failed_provider=%s; falling back to default provider",
                    failed_provider_name or "unknown",
                )

        try:
            provider = wrap_provider_pii_scrub(wrap_provider(create_llm_provider("tokenplan")))
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent_executor] tokenplan fallback unavailable: %s", e)
            provider = get_llm_provider()
        self._last_provider_model_name = getattr(provider, "model", None) or "tokenplan(fallback)"
        return provider

    def _messages_for_round(self, messages: List[Dict]) -> List[Dict]:
        """本轮实际发给 LLM 的消息栈 (在 _resolve_chat_provider 之后调用)。

        三条路径, 互斥、优先级从上到下:
          1. _prefer_fast_record_model (整轮记录快路由) → _build_fast_record_messages (现状不变);
          2. **本轮**被工具决策轮快路由 (_tool_round_fast_routed=True) 且已备好 lite 栈 →
             用 lite 栈 (省 ~14k→<4k prefill; 见 _build_lite_tool_round_messages)。该分支与
             (1) 互斥: _maybe_fast_route_tool_round 在 _prefer_fast_record_model 时恒返回 None,
             故 _tool_round_fast_routed 不会与 _prefer_fast_record_model 同真;
          3. 否则 → 全量栈 (合成/答案轮、非快路由轮、快路由失守时全走这条 = 逐字节现状)。

        _tool_round_fast_routed 由 _resolve_chat_provider→_maybe_fast_route_tool_round 每轮设置,
        并在主循环轮首重置 → 合成/答案轮 (round_tools=[] → 不触发快路由) 恒走全量栈。
        """
        if self._prefer_fast_record_model:
            return _build_fast_record_messages(messages)
        if self._tool_round_fast_routed and self._lite_tool_round_messages is not None:
            return self._lite_tool_round_messages
        return messages

    def _log_prompt_prefix_signature(self, round_messages: List[Dict], provider: Any) -> None:
        """每次 LLM 调用记一行前缀指纹 (Phase-2 rank3 第0步, 仅观测, 绝不断业务)。"""
        try:
            sig = _prompt_prefix_signature(round_messages)
            model_name = (
                getattr(provider, "model", None)
                or getattr(provider, "provider_name", None)
                or "unknown"
            )
            logger.info(
                "[agent_executor] llm_prefix model=%s sys_hash=%s prefix_hash=%s "
                "prefix_chars=%d total_chars=%d approx_tokens=%d",
                model_name, sig["system_hash"], sig["prefix_hash"],
                sig["prefix_chars"], sig["total_chars"], sig["approx_tokens"],
            )
        except Exception:  # noqa: BLE001 — 观测层绝不断业务
            pass

    async def _call_llm(
        self, messages: List[Dict], tools: List[Dict],
    ) -> Any:
        """调用 LLM（优先走配置的 agent 端点，回退到默认 provider）"""
        agent_base = settings.agent_base_url
        agent_key = settings.agent_api_key

        # agent_model 仅当 AGENT_BASE_URL 显式配置时才用 (走 _call_llm_direct).
        # 否则走默认 provider 路径, model=None 让 provider 用自己 init 时的默认 model
        # (如 TokenPlan 用 settings.tokenplan_model = MiniMax-M2.5).
        # 旧逻辑用 settings.llm_model (gpt-4o-mini) 当 fallback model 名,
        # 直接发给 TokenPlan → Model not exist.
        if agent_base and agent_key:
            model = settings.agent_model or settings.llm_model
            return await self._call_llm_direct(messages, tools, model, agent_base, agent_key)

        provider, pass_tools = self._resolve_chat_provider(tools)
        # 消息栈选择 (fast-record 压缩 / fast 工具决策轮 lite / 全量) — 见 _messages_for_round。
        # 必须在 _resolve_chat_provider 之后 (它设置 _tool_round_fast_routed)。
        round_messages = self._messages_for_round(messages)
        self._log_prompt_prefix_signature(round_messages, provider)
        chat_kwargs = {
            "messages": round_messages,
            "model": None,
            "temperature": 0.3,
            "max_tokens": ANSWER_MAX_TOKENS,
            "stream": False,
            "return_metadata": True,
        }
        if pass_tools:
            chat_kwargs["tools"] = pass_tools
            # 并行工具调用(rank5, ships-OFF): 仅当携带 tools 时才带该参数(无 tools 带会
            # SDK 报错);flag 关时 payload 逐字节不变。
            if getattr(settings, "llm_parallel_tool_calls", False):
                chat_kwargs["parallel_tool_calls"] = True
        # 显式上下文缓存(rank3, ships-OFF): 工具决策轮 + 合成轮都受益(工具轮写 system 缓存、
        # 合成轮命中), 故不分 tools 无条件门控。flag 关 / 模型未验证时不设 kwarg = 逐字节不变。
        self._maybe_apply_prompt_cache_markers(chat_kwargs)
        self._last_provider_model_name = (
            getattr(provider, "model", None)
            or getattr(provider, "default_model", None)
            or getattr(provider, "provider_name", None)
        )
        # R2 force tool_choice 不接这里: 记录路径全走 run_stream → _call_llm_stream
        # (/agent/stream 与 /agent/send 都是), 本非流式方法的调用点(multi_model/无 tools)
        # 四条件恒不可能同真 —— 安全评审 2026-07-17 抓出死接线, 已挪到 _call_llm_stream。
        try:
            return await provider.chat(**chat_kwargs)
        except Exception as e:  # noqa: BLE001
            # 选定 provider 报错 → 回退到稳定的 tool-capable provider。
            # 典型场景:langbridge 商用网关(GPT-5.5 等)的浏览器适配器只支持流式,
            # 不实现非流式 tool-calling chat() → 返回 500 "adapter has no chat() method"。
            # 不回退的话用户一选商用模型整个 agent 就不可用。二次失败再抛给上层兜底。
            # F2: pass_tools 时回退目标经可靠工具模型选择 (_stable_fallback_provider),
            # 不再无脑落到默认 tokenplan(MiniMax 弱工具模型)。
            logger.warning(
                "[agent_executor] 选定 provider chat() 失败,回退稳定 provider: %s", e
            )
            self._remember_dead_provider(tool_specific=bool(pass_tools))
            if pass_tools and self._request_model_id:
                self._request_model_tool_fallback_used = True
                self._record_model_fallback_reason("selected_model_tool_chat_failed")
            fb = self._stable_fallback_provider(
                bool(pass_tools),
                failed_provider=provider,
            )
            return await fb.chat(**chat_kwargs)

    async def _call_llm_stream(
        self, messages: List[Dict], tools: List[Dict],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式调用 LLM，实时 yield 结构化事件 (content / tool_calls / finish)。

        事件 schema 与 provider.chat_stream 一致:
        - {"type": "content", "text": <delta>}
        - {"type": "tool_calls", "tool_calls": [...openai-format...]}
        - {"type": "finish", "finish_reason": <reason>}

        provider 路由复用 _resolve_chat_provider (与非流式 _call_llm 一致)。
        AGENT_BASE_URL 直连分支不支持结构化流式 tool-calling → 降级到非流式
        _call_llm 并把结果转成等价事件 (生产现状 agent_base 未配,不走此分支)。
        Streaming failover: provider 流式报错时回退 tokenplan,镜像 _call_llm
        (df3ae2d8)。已 yield 过 content 后再报错则优雅收尾,不重复回退 (避免双发)。
        """
        agent_base = settings.agent_base_url
        agent_key = settings.agent_api_key
        if agent_base and agent_key:
            # 直连网关只实现非流式 tool-calling → 退化为单次调用 + 一次性 content。
            model = settings.agent_model or settings.llm_model
            result = await self._call_llm_direct(messages, tools, model, agent_base, agent_key)
            async for evt in self._result_to_stream_events(result):
                yield evt
            return

        provider, pass_tools = self._resolve_chat_provider(tools)
        # 消息栈选择 (fast-record 压缩 / fast 工具决策轮 lite / 全量) — 见 _messages_for_round。
        # 必须在 _resolve_chat_provider 之后 (它设置 _tool_round_fast_routed)。
        round_messages = self._messages_for_round(messages)
        self._log_prompt_prefix_signature(round_messages, provider)
        stream_kwargs: Dict[str, Any] = {
            "messages": round_messages,
            "model": None,
            "temperature": 0.3,
            # fast-routed 简单回合把答案 token 收紧到 2000 (长尾解码是延迟一部分),
            # 其它回合保持 8000。见 _answer_max_tokens。
            "max_tokens": self._answer_max_tokens(),
        }
        if pass_tools:
            stream_kwargs["tools"] = pass_tools
            # 并行工具调用(rank5, ships-OFF): 仅当携带 tools 时才带(无 tools 带会 SDK
            # 报错);flag 关时 payload 逐字节不变。
            if getattr(settings, "llm_parallel_tool_calls", False):
                stream_kwargs["parallel_tool_calls"] = True
            # R2(ships-OFF): 高置信记录轮**首个**工具轮 force tool_choice=health_record
            # + 关思考(恒成对: qwen thinking 模式下 tool_choice=object 400 ——
            # probe_tool_choice_strict.py 实测)。首轮判据打**原始 messages**(跨轮累积
            # tool 结果), 模型门控走 ModelEntry.supports_forced_tool_choice registry flag。
            # flag 关 / 模型未验证 / 非首轮 = 不设 kwarg, payload 逐字节不变。
            self._maybe_force_record_tool_choice(stream_kwargs, messages)
            self._maybe_force_explicit_aigc_media_tool_choice(stream_kwargs, messages)
        else:
            # 合成/答案轮(无 tools): 可选给 qwen 思考阶段封顶(flag 门控, fail-closed)。
            # 只在这里调=天然只碰无工具的合成轮, 绝不碰工具决策轮。
            self._maybe_apply_synthesis_thinking_budget(stream_kwargs)
        # 显式上下文缓存(rank3, ships-OFF): 工具轮写 system 缓存、合成轮命中 → 两类轮都受益,
        # 故不分 tools 无条件门控。flag 关 / 模型未验证时不设 kwarg = payload 逐字节不变。
        self._maybe_apply_prompt_cache_markers(stream_kwargs)
        self._last_provider_model_name = (
            getattr(provider, "model", None)
            or getattr(provider, "default_model", None)
            or getattr(provider, "provider_name", None)
        )

        # F3b 非流式桥: 若本回合 effective model 结构性非流式 (langbridge 商用模型经
        # 万擎公网, 网关无 SSE, ttft≈total), 不再白等流式超时 —— 直接走非流式 chat()
        # 并以单块产出适配回流式事件。工具能力门控已把不可靠工具模型换掉, 剩下的非流式
        # 模型 (Opus/GPT-5.5/Gemini) 是可靠工具模型, 由它自己拿最终答案质量。
        # chat() 失败 (如网关适配器不实现非流式 tool-calling) 走同一 failover。
        if self._effective_model_is_non_streaming():
            try:
                result = await self._call_llm_nonstream_for_bridge(provider, stream_kwargs, pass_tools)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "[agent_executor] 非流式桥 chat() 失败,回退稳定 provider: %s", e
                )
                self._remember_dead_provider(tool_specific=bool(pass_tools))
                if pass_tools and self._request_model_id:
                    self._request_model_tool_fallback_used = True
                    self._record_model_fallback_reason("selected_model_tool_bridge_failed")
                async for evt in self._stream_via_stable_fallback(
                    stream_kwargs,
                    pass_tools,
                    failed_provider=provider,
                ):
                    yield evt
                return
            async for evt in self._result_to_stream_events(result):
                yield evt
            return

        emitted_content = False
        try:
            async for evt in provider.chat_stream(**stream_kwargs):
                if isinstance(evt, dict) and evt.get("type") == "content" and evt.get("text"):
                    emitted_content = True
                yield evt
        except Exception as e:  # noqa: BLE001
            if emitted_content:
                # 已经向用户发出部分内容 → 不能再切 provider 重发 (会重复)。
                # 优雅收尾: 记日志 + 发一个带 error finish_reason 的事件让上层感知。
                logger.warning(
                    "[agent_executor] 流式中途报错 (已发部分内容),优雅收尾: %s", e
                )
                yield {"type": "finish", "finish_reason": "error"}
                return
            # 流开始前/未发任何内容就报错 → 回退稳定 provider (F2: 带工具时经可靠工具模型)。
            logger.warning(
                "[agent_executor] 选定 provider chat_stream() 失败,回退稳定 provider: %s", e
            )
            self._remember_dead_provider(tool_specific=bool(pass_tools))
            if pass_tools and self._request_model_id:
                self._request_model_tool_fallback_used = True
                self._record_model_fallback_reason("selected_model_tool_stream_failed")
            async for evt in self._stream_via_stable_fallback(
                stream_kwargs,
                pass_tools,
                failed_provider=provider,
            ):
                yield evt

    def _maybe_force_record_tool_choice(
        self, stream_kwargs: Dict[str, Any], original_messages: List[Dict[str, Any]]
    ) -> None:
        """R2: 高置信记录轮首个工具轮 → stream_kwargs 注入 named tool_choice + 关思考。

        全部条件(flag + _should_force_record_tool_choice 四条件)才注入, 否则零行为变更。
        模型门控走 ModelEntry.supports_forced_tool_choice(真网探针验证过才 True,
        与 supports_thinking_budget 同款 registry 纪律)。fail-soft: 判定异常不注入。
        """
        try:
            if not getattr(settings, "llm_force_record_tool_choice", False):
                return
            model_id = self._last_effective_model_id
            if not model_id:
                return
            from app.services.llm.model_registry import get_model
            entry = get_model(model_id)
            supports = bool(entry and getattr(entry, "supports_forced_tool_choice", False))
            if _should_force_record_tool_choice(
                self._prefer_fast_record_model,
                original_messages,
                stream_kwargs.get("tools"),
                supports,
            ):
                stream_kwargs["tool_choice"] = {
                    "type": "function", "function": {"name": "health_record"},
                }
                stream_kwargs["enable_thinking"] = False
                # 真网验证锚点(复审 GO 附带条件): 翻 flag 后 journalctl grep 此行,
                # 确认 force 在生产真实触发(而非 flag 开了却 under-fire 空转)。
                logger.info(
                    "[agent_executor] R2 force tool_choice applied model=%s", model_id
                )
        except Exception:  # noqa: BLE001
            return

    def _maybe_force_explicit_aigc_media_tool_choice(
        self, stream_kwargs: Dict[str, Any], original_messages: List[Dict[str, Any]]
    ) -> None:
        """Force an explicit, confirmation-only AIGC draft on supported models."""
        try:
            model_id = self._last_effective_model_id
            if not model_id:
                return
            from app.services.llm.model_registry import get_model

            entry = get_model(model_id)
            supports = bool(entry and getattr(entry, "supports_forced_tool_choice", False))
            if _should_force_explicit_aigc_media_tool_choice(
                self._current_turn_user_message,
                original_messages,
                stream_kwargs.get("tools"),
                supports,
            ):
                stream_kwargs["tool_choice"] = {
                    "type": "function", "function": {"name": "draft_aigc_media"},
                }
                stream_kwargs["enable_thinking"] = False
                logger.info(
                    "[agent_executor] force AIGC draft tool_choice applied model=%s", model_id
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "[agent_executor] unable to apply explicit AIGC draft tool choice",
                exc_info=True,
            )

    def _maybe_apply_synthesis_thinking_budget(self, stream_kwargs: Dict[str, Any]) -> None:
        """合成/答案轮 → 给 qwen 思考阶段封顶(flag 门控, fail-closed)。

        只在满足**全部**条件时给 stream_kwargs 注入 thinking_budget(否则 = 零行为变更):
          1. settings.synthesis_thinking_budget > 0(默认 0 = 关);
          2. 本回合 effective model 的 ModelEntry.supports_thinking_budget=True
             (仅探针验证过该参数的 qwen 模型;未验证模型不传, 免端点 400 打死合成轮);
          3. 本回合**未**调用 health_analysis(深度分析/安全裁决可能确实需要长思考 →
             fail-closed 跳过, 保留完整思考)。
        调用点已保证只在无 tools 的合成/答案轮触发, 故绝不碰工具决策轮。命中时
        OpenAIProvider._apply_thinking_controls 把 thinking_budget 折进 extra_body。
        fail-soft: 任何判定异常都不注入(=现状), 绝不断合成链路。
        """
        try:
            from app.config import settings

            # 深度分析/安全裁决可能真需长思考 → fail-closed 保留完整思考(两条路径共用前置)。
            if self._turn_invoked_deep_analysis:
                return
            model_id = self._last_effective_model_id
            if not model_id:
                return
            from app.services.llm.model_registry import get_model

            entry = get_model(model_id)
            if entry is None or not getattr(entry, "supports_thinking_budget", False):
                return
            # (A) 简单查询/列表回合 → 合成轮直接关思考(探针实证 TTFT ~36s→~1.6s)。
            # 只对 _is_fast_eligible_turn 判定的简单回合(已排除建议/分析)生效, 分析轮不碰 →
            # 规避全局思考封顶伤分析质量的 A/B 否决。尊重用户模型选择, 只去无谓的思考阶段。
            if getattr(self, "_turn_synthesis_skip_thinking", False):
                stream_kwargs["enable_thinking"] = False
                logger.info(
                    "[agent_executor] 简单查询合成轮关思考 model=%s user=%s",
                    model_id, self._current_user_id,
                )
                return
            # (B) 全局思考封顶(flag 门控, 默认 0=关; 命中即含分析轮, 慎开)。
            budget = int(getattr(settings, "synthesis_thinking_budget", 0) or 0)
            if budget <= 0:
                return
            stream_kwargs["thinking_budget"] = budget
            logger.info(
                "[agent_executor] 合成轮思考封顶 model=%s thinking_budget=%d",
                model_id,
                budget,
            )
        except Exception:  # noqa: BLE001 — 延迟优化绝不断主链路
            return

    def _maybe_apply_prompt_cache_markers(self, call_kwargs: Dict[str, Any]) -> None:
        """DashScope 显式上下文缓存(Phase-2 rank3, flag 门控, fail-closed)。

        只在满足**全部**条件时给 call_kwargs 打显式缓存信号(否则 = 零行为变更, payload
        逐字节不变):
          1. settings.llm_explicit_prompt_cache(默认 False = 关);
          2. 本回合 effective model 的 ModelEntry.supports_explicit_cache=True
             (仅**真网络探针**验证过 cache_control 命中 + usage.cached_tokens 透传的
             DashScope 模型;未验证模型不打标, 免端点拒/忽略无效断点)。
        命中时只设 `prompt_cache_markers=True`(默认布局 = system + history_prefix 两断点);
        真正的 cache_control 注入由 provider 侧 _maybe_mark_prompt_cache 按 role/position
        在 append-only 边界完成(见 openai_provider + services/llm/prompt_cache.py)。
        fail-soft: 任何判定异常都不打标(=现状), 绝不断链路。"""
        try:
            from app.config import settings

            if not getattr(settings, "llm_explicit_prompt_cache", False):
                return
            model_id = self._last_effective_model_id
            if not model_id:
                return
            from app.services.llm.model_registry import get_model

            entry = get_model(model_id)
            if entry is None or not getattr(entry, "supports_explicit_cache", False):
                return
            call_kwargs["prompt_cache_markers"] = True
            logger.info(
                "[agent_executor] 显式上下文缓存标记 model=%s (system+history_prefix 断点)",
                model_id,
            )
        except Exception:  # noqa: BLE001 — 延迟优化绝不断主链路
            return

    def _effective_model_is_non_streaming(self) -> bool:
        """本回合 _resolve_chat_provider 解析出的 effective model 是否结构性非流式。

        fail-soft: model_id 解析不出 / 未注册 / 读库异常 → False (走正常流式), 宁可
        少走桥也不误判。工具门控把 provider 换成别的可靠模型时 (effective 是不可靠工具
        模型), 该判定基于 effective_model_id, 门控后 provider 已换 — 但被换掉的不可靠
        模型都是 tokenplan 流式模型, supports_streaming=True, 不会误进桥。非流式模型
        (Opus/GPT-5.5/Gemini) 恒为可靠工具模型, 门控不会换它, effective 即真实 provider。
        """
        try:
            from app.services.llm.model_registry import get_model
            model_id = self._last_effective_model_id
            if not model_id:
                return False
            entry = get_model(model_id)
            if entry is None:
                return False
            return not entry.supports_streaming
        except Exception:  # noqa: BLE001 — 路由判定绝不断主链路
            return False

    @staticmethod
    async def _call_llm_nonstream_for_bridge(provider, stream_kwargs: Dict[str, Any], pass_tools) -> Any:
        """非流式桥: 用 stream_kwargs 组一次非流式 chat() 调用, 返回整块结果。

        **刻意重建 kwargs 只挑五键, 不透传 tool_choice/enable_thinking/parallel_tool_calls**
        —— 桥服务的是非流式商用模型(Opus/GPT/Gemini, 未过 force 探针), R2 force kwargs
        在此被丢弃是结构性 fail-safe(安全复审 2026-07-17 依赖此行为, 改成透传须回炉评审)。
        """
        chat_kwargs = {
            "messages": stream_kwargs["messages"],
            "model": stream_kwargs.get("model"),
            "temperature": stream_kwargs.get("temperature", 0.3),
            "max_tokens": stream_kwargs.get("max_tokens", ANSWER_MAX_TOKENS),
            "stream": False,
            "return_metadata": True,
        }
        if pass_tools:
            chat_kwargs["tools"] = pass_tools
        return await provider.chat(**chat_kwargs)

    async def _stream_via_stable_fallback(
        self, stream_kwargs: Dict[str, Any], pass_tools, failed_provider=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """把稳定回退 provider 的产出适配成流式事件。

        回退目标 (F2: 带工具走可靠工具模型) 若非流式则用 chat() 单块产出, 否则真流式。
        fail-open: 回退 provider 再失败也要产出一个 finish 事件让上层收尾, 不把回合打死。
        """
        # R2 fail-open: force kwargs(tool_choice+关思考)可能就是主 provider 失败原因,
        # 且回退目标未必过探针验证 —— 回退前剥除, 绝不让 force 把整轮打死。
        stream_kwargs.pop("tool_choice", None)
        stream_kwargs.pop("enable_thinking", None)
        fb = self._stable_fallback_provider(
            bool(pass_tools),
            failed_provider=failed_provider,
        )
        fb_non_streaming = self._provider_is_non_streaming(fb)
        try:
            if fb_non_streaming:
                result = await self._call_llm_nonstream_for_bridge(fb, stream_kwargs, pass_tools)
                async for evt in self._result_to_stream_events(result):
                    yield evt
            else:
                async for evt in fb.chat_stream(**stream_kwargs):
                    yield evt
        except Exception as e:  # noqa: BLE001
            # 回退也失败: 绝不把回合打死 — 发一个 error finish, 上层空回复重试链接管。
            logger.warning("[agent_executor] 稳定回退 provider 也失败: %s", e)
            yield {"type": "finish", "finish_reason": "error"}

    @staticmethod
    def _provider_is_non_streaming(provider) -> bool:
        """按 provider.model 反查注册表判断是否结构性非流式。fail-soft → False。"""
        try:
            from app.services.llm.model_registry import MODELS
            model_name = getattr(provider, "model", None)
            if not model_name:
                return False
            for entry in MODELS:
                if entry.model == model_name:
                    return not entry.supports_streaming
            return False
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    async def _result_to_stream_events(result: Any) -> AsyncGenerator[Dict[str, Any], None]:
        """把非流式 chat() 结果 (str 或 dict) 转成等价的结构化流式事件。"""
        if isinstance(result, dict):
            content = result.get("content") or ""
            if content:
                yield {"type": "content", "text": content}
            tool_calls = result.get("tool_calls")
            if tool_calls:
                yield {"type": "tool_calls", "tool_calls": tool_calls}
            yield {"type": "finish", "finish_reason": result.get("finish_reason")}
        else:
            text = str(result or "")
            if text:
                yield {"type": "content", "text": text}
            yield {"type": "finish", "finish_reason": "stop"}

    async def _recover_model_scope_refusal(self, messages: List[Dict]) -> str:
        """Re-ask once when the model incorrectly narrows the Agent's scope.

        The original tool results and safety instructions remain in ``messages``;
        the extra instruction only corrects the model's capability framing. A
        second refusal is discarded so this recovery cannot loop or weaken the
        medical safety boundary.
        """
        recovery_messages = list(messages)
        recovery_messages.append(
            {
                "role": "user",
                "content": (
                    "上一轮回答把本 Agent 的能力范围误判为只能记录。请直接回答用户原问题："
                    "可以基于上文已有数据进行分析、解释和下一步建议；不要给出诊断、处方或停药指令。"
                    "如果关键数据缺失，明确指出缺什么，只提出一个最小澄清问题。"
                    "不要再次说明只能记录或只能查询。"
                ),
            }
        )
        try:
            response = await self._call_llm_fallback_provider(recovery_messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[agent recovery] model scope refusal fallback failed: %s",
                type(exc).__name__,
            )
            return ""
        text = _response_text(response).strip()
        return "" if is_model_scope_refusal(text) or is_safety_boundary_refusal(text) else text

    async def _recover_data_insufficiency(self, messages: List[Dict]) -> str:
        """Turn a bare data-gap answer into a useful, honest next step once."""
        recovery_messages = list(messages)
        recovery_messages.append(
            {
                "role": "user",
                "content": (
                    "上一轮把数据不足直接当成了拒答。请重新回答用户原问题：只使用上文已有数据，"
                    "不要编造任何读数、记录或结论；如果确实缺数据，明确指出缺少的最小数据，"
                    "并只提出一个最小澄清问题。若可以给出不依赖缺失数据的通用下一步，请直接给出。"
                    "不要给出诊断、处方或停药指令，也不要以‘无法帮助’或‘只能记录’结束。"
                ),
            }
        )
        try:
            response = await self._call_llm_fallback_provider(recovery_messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[agent recovery] data insufficiency fallback failed: %s",
                type(exc).__name__,
            )
            return ""
        text = _response_text(response).strip()
        if (
            is_data_insufficiency_response(text)
            or is_model_scope_refusal(text)
            or is_safety_boundary_refusal(text)
        ):
            return ""
        return text

    async def _call_llm_fallback_provider(self, messages: List[Dict]) -> Any:
        """Use the stable global provider when a selected gateway keeps empty-answering."""
        from app.services.llm.factory import create_llm_provider, get_llm_provider
        from app.services.llm.pii_scrub import wrap_provider_pii_scrub
        from app.services.llm.usage_tracker import wrap_provider

        try:
            provider = wrap_provider_pii_scrub(wrap_provider(create_llm_provider("tokenplan")))
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent_executor] tokenplan fallback unavailable: %s", e)
            provider = get_llm_provider()
        return await provider.chat(
            messages=messages,
            model=None,
            temperature=0.3,
            max_tokens=ANSWER_MAX_TOKENS,
            stream=False,
            return_metadata=True,
        )

    async def _call_llm_direct(
        self, messages: List[Dict], tools: List[Dict],
        model: str, base_url: str, api_key: str,
    ) -> Any:
        """直接调用 OpenAI 兼容的 chatCompletions 端点，含 429 重试"""
        import asyncio as _asyncio

        url = f"{base_url.rstrip('/')}/chat/completions"

        has_image = any(
            isinstance(m.get("content"), list) and any(c.get("type") == "image_url" for c in m["content"])
            for m in messages if isinstance(m, dict)
        )
        logger.info(f"[_call_llm_direct] model={model}, base_url={base_url[:50]}, has_image={has_image}, msg_count={len(messages)}")
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": ANSWER_MAX_TOKENS,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t["function"]} if "function" in t else t for t in tools]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        max_retries = 3
        deadline = time.time() + 90
        client = self._http_client or httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0))
        for attempt in range(max_retries):
            if time.time() > deadline:
                raise RuntimeError("AI 服务响应超时，请稍后再试")
            t0 = time.time()
            try:
                logger.info(f"[_call_llm_direct] attempt={attempt+1} POST start")
                resp = await client.post(url, headers=headers, json=payload)
                latency_ms = int((time.time() - t0) * 1000)
                logger.info(f"[_call_llm_direct] attempt={attempt+1} POST done in {latency_ms/1000:.1f}s status={resp.status_code}")
                # 结构化 perf 指标 (machine-parseable, 用于 admin 看板汇总):
                # metric: llm_call provider=<base_url主机> model=<model> latency_ms=<n> status=<n> attempt=<n>
                try:
                    from urllib.parse import urlparse
                    host = urlparse(base_url).netloc
                except Exception:
                    host = base_url[:30]
                logger.info(
                    f"metric: llm_call provider={host} model={model} "
                    f"latency_ms={latency_ms} status={resp.status_code} attempt={attempt+1}"
                )
                if resp.status_code == 429:
                    wait = min(2 * (2 ** attempt), 10)  # 2s, 4s, 8s
                    logger.warning(f"LLM API 429 限流，第{attempt+1}/{max_retries}次重试，等待{wait}s")
                    await _asyncio.sleep(wait)
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(f"LLM API 返回 {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                break
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    wait = min(2 * (2 ** attempt), 8)
                    logger.warning(f"LLM API 超时/连接错误({type(e).__name__})，第{attempt+1}/{max_retries}次重试，等待{wait}s")
                    await _asyncio.sleep(wait)
                    continue
                raise
        else:
            raise RuntimeError("AI 服务暂时繁忙，请稍后再试")

        choice = data.get("choices", [{}])[0]
        finish_reason = choice.get("finish_reason")
        msg = choice.get("message", {})

        # 解析 tool_calls
        if msg.get("tool_calls"):
            return {
                "content": msg.get("content") or "",
                "finish_reason": finish_reason,
                "tool_calls": [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"].get("arguments", "{}"),
                        },
                    }
                    for i, tc in enumerate(msg["tool_calls"])
                ],
            }
        return {
            "content": msg.get("content") or "",
            "finish_reason": finish_reason,
        }

    async def _analyze_image_with_vision(self, user_message: str, images: List[dict]) -> Optional[str]:
        """用 vision 模型预分析图片内容，返回文字描述"""
        structured_food = await self._analyze_food_images_with_structured_vision(user_message, images)
        if structured_food:
            return structured_food

        if not settings.llm_vision_base_url or not settings.llm_vision_api_key:
            return None

        vision_model = settings.llm_vision_model or "qwen-vl-max"
        vision_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": (
                "你是普通图片内容分析助手。客观描述图片中的主要对象、文字和场景。"
                "不要估算食物热量或宏量营养，不要生成任何健康数据写入参数；"
                "餐食的结构化识别由独立且可校准的链路负责。用简洁中文回复。"
            )},
            {"role": "user", "content": [
                {"type": "text", "text": user_message or "请识别这张图片中的食物"},
            ]},
        ]
        for img in images:
            vision_messages[1]["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/{img.get('type', 'jpeg')};base64,{img['base64']}"},
            })

        try:
            url = f"{settings.llm_vision_base_url.rstrip('/')}/chat/completions"
            payload = {
                "model": vision_model,
                "messages": vision_messages,
                "temperature": 0.3,
                "max_tokens": 500,
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.llm_vision_api_key}",
            }
            client = self._http_client or httpx.AsyncClient(timeout=60.0)
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                description = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not description:
                    return None
                return f"普通图片描述（非结构化，不得据此写入饮食记录）: {description}"
            else:
                logger.warning(
                    "[Vision] 图片分析失败: HTTP %s response_chars=%s",
                    resp.status_code,
                    len(resp.text or ""),
                )
                return None
        except Exception as e:
            logger.warning(f"[Vision] 图片分析异常: {e}")
            return None

    async def _analyze_food_images_with_structured_vision(self, user_message: str, images: List[dict]) -> Optional[str]:
        """Prefer strict food-recognition JSON over free-form vision prose for diet photos."""
        if not images:
            return None
        if len(images) > 3:
            return (
                "本轮包含超过 3 张图片。为避免静默漏记，本次没有写入饮食；"
                "请拆成两次发送，每次最多 3 张同一餐照片。"
            )
        try:
            from app.services.ai.food_recognition import (
                apply_user_stated_amount_to_nutrition_label,
                food_recognition_service,
                merge_food_recognition_results,
                sanitize_food_recognition_result,
            )
            from app.services.food_nutrition_lookup import calibrate_recognized_foods

            recognized_results: List[Dict[str, Any]] = []
            errors: List[str] = []
            unique_image_indexes: List[int] = []
            image_classifications: Dict[int, str] = {}
            seen_image_hashes: set[str] = set()
            for image_index, img in enumerate(images[:3]):
                encoded = str(img.get("base64") or "")
                digest = hashlib.sha256(encoded.encode("ascii", errors="ignore")).hexdigest()
                if digest in seen_image_hashes:
                    continue
                seen_image_hashes.add(digest)
                unique_image_indexes.append(image_index)
                result = await food_recognition_service.recognize_food_from_base64(
                    encoded,
                    image_type=img.get("type", "jpeg"),
                )
                result = sanitize_food_recognition_result(result)
                if result.get("success") and result.get("foods"):
                    result = apply_user_stated_amount_to_nutrition_label(
                        result,
                        user_message,
                    )
                    if result.get("nutrition_label_requires_amount"):
                        errors.append(
                            "已识别营养成分表，但还需要明确实际食用重量。"
                        )
                        image_classifications[image_index] = "food"
                        continue
                    result = sanitize_food_recognition_result(result)
                    image_classifications[image_index] = "food"
                    calibrate_recognized_foods(self.db, result["foods"])
                    result = sanitize_food_recognition_result(result)
                    consumed_fraction = _contextual_meal_consumed_fraction(
                        user_message
                    )
                    if consumed_fraction is not None:
                        fraction, label = consumed_fraction
                        result = _scale_food_recognition_for_consumed_fraction(
                            result,
                            fraction=fraction,
                            label=label,
                        )
                        result = sanitize_food_recognition_result(result)
                        result["consumed_fraction"] = fraction
                        result["consumed_fraction_label"] = label
                    recognized_results.append(result)
                else:
                    error = str(result.get("error") or "图片识别未完成")
                    errors.append(error)
                    image_classifications[image_index] = (
                        "non_food"
                        if self._food_recognition_found_no_food([error])
                        else "unknown"
                    )
            if recognized_results:
                merged_result = merge_food_recognition_results(recognized_results)
                merged_result["source_image_count"] = len(unique_image_indexes)
                failed_image_indexes = [
                    image_index
                    for image_index in unique_image_indexes
                    if image_classifications.get(image_index) != "food"
                ]
                if failed_image_indexes:
                    merged_result["multi_photo_incomplete"] = True
                    merged_result["failed_image_indexes"] = failed_image_indexes
                capture = self._capture_contextual_meal_photos(
                    user_message,
                    merged_result,
                    image_indexes=unique_image_indexes,
                    image_classifications=image_classifications,
                )
                return self._format_food_recognition_for_agent(
                    user_message,
                    merged_result,
                    contextual_capture=capture,
                )
            if errors and self._looks_like_food_photo_context(user_message):
                if not self._food_recognition_found_no_food(errors):
                    if any("实际食用重量" in error for error in errors):
                        return (
                            "已读取图片中的营养成分表，但还缺少实际食用重量。"
                            "本次没有写入饮食记录；请补充你实际吃了多少克。"
                        )
                    return (
                        "本轮餐食图片识别未完整完成，因此没有写入饮食记录。"
                        "请稍后重试，或补充食物名称和份量后再确认。"
                    )
            if self._looks_like_food_photo_context(user_message) and self._food_recognition_found_no_food(errors):
                return (
                    "结构化餐食识别结果: 图片中未识别到可记录的食物。"
                    "不要把截图里的营养卡、按钮、输入框或界面文字当作 food_items。"
                    "请让用户重新拍摄餐食本身, 或补充真实食物名称和份量。"
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("[Vision] structured food recognition failed, fallback to generic vision: %s", e)
        return None

    @staticmethod
    def _food_recognition_found_no_food(errors: List[str]) -> bool:
        joined = " ".join(errors)
        return bool(re.search(r"未识别到(?:可记录的)?食物|重新拍摄餐食|不是食物|not food", joined, re.I))

    def _capture_contextual_meal_photo(
        self,
        user_message: str,
        vision_result: Dict[str, Any],
        *,
        image_index: int,
    ) -> Any | None:
        return self._capture_contextual_meal_photos(
            user_message,
            vision_result,
            image_indexes=[image_index],
        )

    def _capture_contextual_meal_photos(
        self,
        user_message: str,
        vision_result: Dict[str, Any],
        *,
        image_indexes: List[int],
        image_classifications: Dict[int, str] | None = None,
    ) -> Any | None:
        """Persist a qualified chat food photo before the answer model runs.

        This boundary only receives typed semantic intent plus sanitized vision
        output.  It never scans raw text for a recording keyword.
        """
        user_id = self._current_user_id
        source_message_id = (
            self._current_turn_media_source_message_id
            or self._current_turn_source_message_id
        )
        if user_id is None or source_message_id is None:
            vision_result["contextual_capture_failed"] = True
            return None
        normalized_indexes = sorted(set(image_indexes))
        if not normalized_indexes or any(
            image_index < 0 or image_index >= len(self._current_turn_image_urls)
            for image_index in normalized_indexes
        ):
            vision_result["contextual_capture_failed"] = True
            return None

        from app.services.contextual_meal_photo_policy import (
            MealPhotoCandidate,
            MealPhotoSemanticIntent,
            decide_contextual_meal_photo,
        )
        from app.services.contextual_meal_photo_service import (
            ContextualMealPhotoCapture,
            ContextualMealPhotoService,
            ContextualMealPhotoServiceError,
        )
        from app.services.utterance_intent_classifier import classify_agent_utterance
        from app.utils.timezone import DEFAULT_TIMEZONE_NAME, resolve_timezone_name

        reference_now = self._agent_kernel_reference_now()
        intent = classify_agent_utterance(user_message, reference_now=reference_now)
        if intent.primary in {"read", "advice"}:
            semantic_intent = MealPhotoSemanticIntent.ANALYZE_ONLY
        elif intent.is_write:
            semantic_intent = MealPhotoSemanticIntent.EXPLICIT_CAPTURE
        else:
            # A user-submitted image with no analysis/question intent is an
            # implicit capture candidate. The policy still requires meal time,
            # confidence, food classification and idempotency clearance.
            semantic_intent = MealPhotoSemanticIntent.IMPLICIT_CAPTURE

        timezone_name = DEFAULT_TIMEZONE_NAME
        try:
            from app.models.user_profile import UserProfile

            profile = (
                self.db.query(UserProfile.manual_timezone, UserProfile.detected_timezone, UserProfile.timezone)
                .filter(UserProfile.user_id == user_id)
                .first()
            )
            if profile is not None:
                timezone_name, _ = resolve_timezone_name(profile[0], profile[1], profile[2])
        except Exception as exc:  # noqa: BLE001 - retain default policy timezone, surface in logs
            logger.warning(
                "[contextual_meal_photo] timezone resolution failed user_id=%s error=%s",
                user_id,
                exc,
            )

        foods = vision_result.get("foods") if isinstance(vision_result.get("foods"), list) else []
        confidences: list[float] = []
        confidence_complete = bool(foods)
        for food in foods:
            value = food.get("confidence") if isinstance(food, dict) else None
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                confidence_complete = False
                continue
            confidences.append(float(value))
        confidence = (
            min(confidences)
            if confidence_complete and len(confidences) == len(foods)
            else None
        )
        if (
            vision_result.get("multi_photo_conflict")
            or vision_result.get("multi_photo_incomplete")
        ):
            confidence = 0.0
        decision = decide_contextual_meal_photo(MealPhotoCandidate(
            origin="chat",
            semantic_intent=semantic_intent,
            classification="food" if vision_result.get("success") and foods else "non_food",
            recognition_confidence=confidence,
            reference_now=reference_now,
            timezone_name=timezone_name,
            idempotency_clear=True,
        ))
        if decision.decision == "analyze_only":
            return None

        try:
            result = ContextualMealPhotoService(self.db).capture_session([
                ContextualMealPhotoCapture(
                    user_id=user_id,
                    source_message_id=source_message_id,
                    source_image_url=self._current_turn_image_urls[image_index],
                    source_image_index=image_index,
                    decision=decision,
                    vision_result=vision_result,
                    classification=(
                        (image_classifications or {}).get(image_index, "food")
                    ),
                )
                for image_index in normalized_indexes
            ])
        except ContextualMealPhotoServiceError as exc:
            vision_result["contextual_capture_failed"] = True
            logger.warning(
                "[contextual_meal_photo] capture rejected user_id=%s source_message_id=%s reason=%s",
                user_id,
                source_message_id,
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001 - never claim a record after a failed write
            vision_result["contextual_capture_failed"] = True
            logger.error(
                "[contextual_meal_photo] capture failed user_id=%s source_message_id=%s error=%s",
                user_id,
                source_message_id,
                exc,
                exc_info=True,
            )
            return None

        if result.record is not None:
            self._turn_contextual_diet_record_id = result.record.id
            consumed_fraction = vision_result.get("consumed_fraction")
            if (
                isinstance(consumed_fraction, (int, float))
                and not isinstance(consumed_fraction, bool)
                and math.isfinite(float(consumed_fraction))
                and 0 < float(consumed_fraction) < 1
            ):
                self._turn_contextual_diet_consumed_fraction = float(
                    consumed_fraction
                )
            receipt = {
                "operation_id": f"contextual_meal_photo:{result.record.id}",
                "status": "verified",
                "resource_type": "diet_record",
                "resource_id": str(result.record.id),
                "date": result.record.record_date.isoformat(),
                "verified": True,
            }
            if receipt not in self._turn_contextual_diet_receipts:
                self._turn_contextual_diet_receipts.append(receipt)
            # ``write_receipts`` are an audit contract, not a user-facing UI
            # contract. Emit the same portable meal-photo card used for manual
            # confirmation so Web, Mobile and Mac all show a deterministic
            # receipt immediately and after conversation reload.
            self._upsert_turn_contextual_diet_card(
                self._contextual_diet_recorded_card(result),
            )
            self._invalidate_twin_after_mutation()
        elif result.photo_draft is not None:
            self._upsert_turn_contextual_diet_card(
                self._contextual_diet_confirmation_card(result),
            )
        return result

    def _upsert_turn_contextual_diet_card(self, card: Dict[str, Any]) -> None:
        self._turn_contextual_diet_cards = _merge_agent_card_descriptors(
            self._turn_contextual_diet_cards,
            [card],
        )

    def _contextual_diet_recorded_card(self, result: Any) -> Dict[str, Any]:
        """Build an owner-scoped, durable visual receipt for an auto-save."""
        from app.utils.diet_image_url import diet_response_image_url

        record = result.record
        assets = tuple(result.photo_assets or ())
        if not assets and result.photo_asset is not None:
            assets = (result.photo_asset,)
        if record is None or not assets:
            raise ValueError("contextual_diet_recorded_card_missing_receipt")
        photo_asset_ids = [asset.id for asset in assets]
        photo_urls = [
            diet_response_image_url(asset.storage_key, asset.user_id)
            for asset in assets
        ]
        record_data = {
            "meal_type": record.meal_type,
            "food_items": record.food_items,
            "calories": record.calories,
            "protein": record.protein,
            "carbs": record.carbs,
            "fat": record.fat,
        }
        capture_session_id = self._contextual_diet_capture_session_id(assets)
        return {
            "type": "diet_draft",
            "data": format_card_numbers({
                "card_id": f"diet-capture:{capture_session_id}",
                "capture_session_id": capture_session_id,
                "recorded": True,
                "record_id": record.id,
                "record_date": record.record_date.isoformat(),
                "meal_type": record.meal_type,
                "food_items": record.food_items,
                "calories": record.calories,
                "protein": record.protein,
                "carbs": record.carbs,
                "fat": record.fat,
                "fiber": record.fiber,
                "confidence": record.ai_confidence,
                "source": "chat_photo",
                "photo_asset_id": photo_asset_ids[0],
                "photo_asset_ids": photo_asset_ids,
                "photo_url": photo_urls[0],
                "photo_urls": photo_urls,
                "media_stage": "attached",
                "receipt_message": "已保存到今日饮食，餐食照片已关联到这条记录。",
                "boundary": "营养为图像估算；可在饮食记录中继续修正。",
            }),
            "actions": [build_diet_adjust_action(record.id, record_data)],
        }

    def _contextual_diet_confirmation_card(self, result: Any) -> Dict[str, Any]:
        """Build the current-chat confirmation card from an owner-bound draft."""
        from app.services.atomic_capability_registry import attach_action_policy_metadata
        from app.utils.diet_image_url import diet_response_image_url

        draft = result.photo_draft
        assets = tuple(result.photo_assets or ())
        if not assets and result.photo_asset is not None:
            assets = (result.photo_asset,)
        if draft is None or not assets:
            raise ValueError("contextual_diet_confirmation_missing_draft")
        photo_asset_ids = [asset.id for asset in assets]
        photo_urls = [
            diet_response_image_url(asset.storage_key, asset.user_id)
            for asset in assets
        ]
        recognition = draft.recognition_result if isinstance(draft.recognition_result, dict) else {}
        capture_session_id = self._contextual_diet_capture_session_id(assets)
        record = {
            key: recognition[key]
            for key in (
                "record_date", "meal_type", "food_items", "calories", "protein",
                "carbs", "fat", "fiber", "ai_recognized", "ai_confidence",
                "ai_raw_result", "health_tips", "source",
            )
            if recognition.get(key) is not None
        }
        record["source"] = "chat_photo"
        record["photo_draft_token"] = draft.token
        actions = attach_action_policy_metadata("diet_draft", [{
            "id": f"confirm-contextual-diet:{draft.token}",
            "label": "确认记录",
            "action": "diet_record.create",
            "endpoint": "/diet/records",
            "requires_manual_confirm": True,
            "payload": {"record": record},
            "style": "primary",
            "confirmation": {
                "title": "记录这顿餐食？",
                "detail": "确认后会带着这张照片写入今日饮食记录。",
                "confirm_label": "确认记录",
                "cancel_label": "再看看",
            },
        }])
        return {
            "type": "diet_draft",
            # This data is rendered directly by every client. Format only the
            # display descriptor; the action above retains its raw nutrition
            # values for the eventual write request.
            "data": format_card_numbers({
                **record,
                "card_id": f"diet-capture:{capture_session_id}",
                "capture_session_id": capture_session_id,
                "confidence": recognition.get("ai_confidence"),
                "source": "chat_photo",
                "photo_asset_id": photo_asset_ids[0],
                "photo_asset_ids": photo_asset_ids,
                "photo_url": photo_urls[0],
                "photo_urls": photo_urls,
                "media_stage": "pending_confirmation",
                "photo_draft_token": draft.token,
                "auto_save_fallback": bool(result.fallback_from_auto),
                "boundary": (
                    "自动保存未完成；这张照片已保留为确认草稿，确认后才写入今日饮食记录。"
                    if result.fallback_from_auto
                    else "营养为图像估算；确认后才写入今日饮食记录。"
                ),
            }),
            "actions": actions,
        }

    @staticmethod
    def _contextual_diet_capture_session_id(assets: tuple[Any, ...]) -> str:
        source_message_ids = {
            int(asset.origin_message_id)
            for asset in assets
            if asset.origin_message_id is not None
        }
        if len(source_message_ids) != 1:
            raise ValueError("contextual_diet_capture_session_identity_invalid")
        return f"meal-photo:{next(iter(source_message_ids))}"

    def _format_food_recognition_for_agent(
        self,
        user_message: str,
        result: Dict[str, Any],
        *,
        contextual_capture: Any | None = None,
    ) -> str:
        if contextual_capture is not None:
            meal_type = contextual_capture.decision.meal_type
        else:
            meal_type = self._meal_type_for_reference_time()
        foods: List[str] = []
        recognized_foods: List[Dict[str, Any]] = []
        confidences: List[float] = []
        for food in result.get("foods") or []:
            if not isinstance(food, dict):
                continue
            name = str(food.get("name") or "").strip()
            if not name:
                continue
            quantity = str(food.get("quantity") or "").strip()
            kcal = food.get("calories")
            parts = [name]
            if quantity:
                parts.append(quantity)
            if isinstance(kcal, (int, float)):
                parts.append(f"约{round(float(kcal))}kcal")
            foods.append(" ".join(parts))
            recognized_foods.append({
                key: food[key]
                for key in (
                    "name", "quantity", "quantity_grams", "label_basis_grams",
                    "calories", "protein", "carbs", "fat", "fiber",
                    "confidence", "food_id", "source", "nutrition_basis",
                )
                if food.get(key) is not None
            })
            confidence = food.get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
        totals = {
            "calories": result.get("total_calories"),
            "protein": result.get("total_protein"),
            "carbs": result.get("total_carbs"),
            "fat": result.get("total_fat"),
            "fiber": result.get("total_fiber"),
        }
        total_text = ", ".join(
            f"{key}={value}"
            for key, value in totals.items()
            if isinstance(value, (int, float))
        )
        record_data: Dict[str, Any] = {
            "meal_type": meal_type,
            "food_items": " + ".join(
                " ".join(
                    part for part in (
                        str(food.get("name") or "").strip(),
                        str(food.get("quantity") or "").strip(),
                    )
                    if part
                )
                for food in recognized_foods
            ),
            **{
                key: value
                for key, value in totals.items()
                if isinstance(value, (int, float))
            },
            "ai_recognized": 1,
            "ai_raw_result": {
                "recognition_version": "food_table_calibration_v1",
                "foods": recognized_foods,
            },
        }
        if confidences:
            record_data["ai_confidence"] = round(sum(confidences) / len(confidences), 3)
        sources = {str(food.get("source")) for food in recognized_foods if food.get("source")}
        if len(sources) == 1:
            record_data["source"] = next(iter(sources))
        elif sources:
            record_data["source"] = "mixed"
        if len(recognized_foods) == 1 and recognized_foods[0].get("food_id"):
            record_data["food_id"] = recognized_foods[0]["food_id"]

        record_json = json.dumps(record_data, ensure_ascii=False)
        semantic_intent = classify_agent_utterance(
            user_message,
            reference_now=self._agent_kernel_reference_now(),
        )
        consumed_fraction_label = str(
            result.get("consumed_fraction_label") or ""
        ).strip()
        if consumed_fraction_label:
            record_data["food_items"] = (
                f"{record_data['food_items']}"
                f"（按实际食用{consumed_fraction_label}计）"
            )
        if semantic_intent.primary in {"read", "advice"}:
            capture_instruction = (
                "本轮仅用于分析或查询，严禁调用 health_record；"
                "只解释识别结果、不确定性和可选建议。"
            )
        elif result.get("contextual_capture_failed"):
            capture_instruction = (
                "图片资产与饮食记录的原子保存没有完成；严禁调用 health_record "
                "或 health_manage 补写无图记录，也不得声称已经保存。"
                "请明确告知用户图片草稿仍需重试。"
            )
        elif contextual_capture is not None and contextual_capture.record is not None:
            if consumed_fraction_label:
                capture_instruction = (
                    "系统已取得可验证的饮食写入回执，"
                    f"份量已在首次写入中按{consumed_fraction_label}修正；"
                    "不要再次调用 health_record 或 health_manage 写入，"
                    "只解释本餐估算和下一步建议。"
                )
            else:
                capture_instruction = (
                    "系统已取得可验证的饮食写入回执；不要再次调用 health_record，"
                    "只解释本餐估算、如何修正以及下一步建议。"
                )
        elif contextual_capture is not None and contextual_capture.photo_draft is not None:
            capture_instruction = (
                "系统已保存这张图片为当前对话的饮食确认草稿；不要再次调用 health_record，"
                "请让用户在当前卡片核对并确认。"
            )
        else:
            capture_instruction = (
                "如果用户意图是记录饮食, 请调用 health_record(record_type='diet', "
                "data=准确写入参数), 仅按用户明确修正的内容改动。"
            )
        return (
            "结构化餐食识别结果: "
            f"meal_type={meal_type}; foods={' + '.join(foods)}; totals({total_text}). "
            f"准确写入参数: {record_json}。"
            f"{capture_instruction}"
            "food_items 只能使用真实食物名称和份量, 绝对不要包含营养卡、保存并确认、今日饮食等界面文案。"
        )

    def _meal_type_for_reference_time(self) -> str:
        hour = self._agent_kernel_reference_now().hour
        if 5 <= hour < 11:
            return "breakfast"
        if 11 <= hour < 15:
            return "lunch"
        if 17 <= hour < 22:
            return "dinner"
        return "snack"

    @staticmethod
    def _looks_like_food_photo_context(user_message: str) -> bool:
        text = user_message or ""
        if not text.strip():
            return True
        return bool(re.search(
            r"食物|饮食|餐|饭|吃|营养成分|热量|卡路里|"
            r"蛋白|碳水|脂肪|kcal|calorie",
            text,
            re.I,
        ))

    @staticmethod
    def _is_default_image_analysis_prompt(user_message: str) -> bool:
        ignored = frozenset("。.!！?？")
        normalized = "".join(
            character
            for character in (user_message or "").lower()
            if not character.isspace() and character not in ignored
        )
        return normalized in {
            "请分析这些图片",
            "请分析这张图片",
            "分析这些图片",
            "分析这张图片",
        }

    async def _try_import_medical_report_images(
        self,
        user_id: int,
        images: List[dict],
        *,
        persist: bool = False,
    ) -> Optional[str]:
        """Recognize report images and persist only under explicit write intent.

        A verified receipt confirms database persistence, not OCR correctness.
        OCR-derived content remains clearly marked as unverified until the user
        reviews it. Analysis-only turns never cross the write boundary.
        """
        if not images:
            return None
        try:
            from sqlalchemy.exc import IntegrityError

            from app.models.medical_exam import MedicalExam
            from app.services.ai.medical_report_ocr import recognize_medical_report
            from app.services.data_collection.medical_exam_import import (
                MedicalExamImportService,
            )
            from app.twin.cache import invalidate_twin

            recognized: list[tuple[Optional[MedicalExam], dict, list[dict], str]] = []
            created_any = False
            message_date = _normalize_relative_date(
                classify_agent_utterance(
                    self._current_turn_user_message,
                    reference_now=self._agent_kernel_reference_now(),
                ).scope.get("date"),
                reference_now=self._agent_kernel_reference_now(),
            )
            for img in images:
                result = await recognize_medical_report(
                    img["base64"],
                    image_type=img.get("type", "jpeg"),
                )
                if not isinstance(result, dict) or result.get("error"):
                    continue
                items = result.get("items") or []
                conclusion = str(result.get("conclusion") or "").strip()
                if len(items) < 2 and not conclusion:
                    continue

                encoded_image = str(img.get("base64") or "").split(",", 1)[-1]
                try:
                    fingerprint_bytes = base64.b64decode(
                        encoded_image,
                        validate=True,
                    )
                except (ValueError, base64.binascii.Error):
                    fingerprint_bytes = encoded_image.encode(
                        "ascii",
                        errors="ignore",
                    )
                image_fingerprint = hashlib.sha256(fingerprint_bytes).hexdigest()
                exam: Optional[MedicalExam] = None
                if persist:
                    exam = (
                        self.db.query(MedicalExam)
                        .filter(
                            MedicalExam.user_id == user_id,
                            MedicalExam.source_fingerprint == image_fingerprint,
                        )
                        .order_by(MedicalExam.id.desc())
                        .first()
                    )
                    if exam is None:
                        # Backward-compatible lookup for records created before
                        # source_fingerprint became a dedicated unique column.
                        fingerprint_marker = f"[image_sha256:{image_fingerprint}]"
                        exam = (
                            self.db.query(MedicalExam)
                            .filter(
                                MedicalExam.user_id == user_id,
                                MedicalExam.notes.contains(fingerprint_marker),
                            )
                            .order_by(MedicalExam.id.desc())
                            .first()
                        )
                    if exam is None:
                        normalized_report_date = _normalize_relative_date(
                            result.get("report_date"),
                            reference_now=self._agent_kernel_reference_now(),
                        )
                        # An explicit user date is authoritative for this write.
                        resolved_exam_date = (
                            message_date
                            or normalized_report_date
                            or self._agent_kernel_reference_now().date().isoformat()
                        )
                        try:
                            exam = MedicalExamImportService.import_from_items(
                                self.db,
                                user_id=user_id,
                                items_data=items,
                                exam_date=datetime.strptime(
                                    resolved_exam_date,
                                    "%Y-%m-%d",
                                ).date(),
                                exam_type=result.get("report_type") or "medical_report",
                                hospital_name=result.get("institution"),
                                notes="从聊天图片 OCR 导入，内容待用户核对",
                                source="agent_image_ocr",
                                overall_assessment=conclusion or None,
                                # Structured conclusions are model-generated and
                                # must not be promoted to a verified health field.
                                conclusions=None,
                                source_fingerprint=image_fingerprint,
                            )
                            created_any = True
                        except IntegrityError:
                            # The unique (user, fingerprint) index makes
                            # concurrent retries converge on one canonical row.
                            self.db.rollback()
                            exam = (
                                self.db.query(MedicalExam)
                                .filter(
                                    MedicalExam.user_id == user_id,
                                    MedicalExam.source_fingerprint
                                    == image_fingerprint,
                                )
                                .one()
                            )

                    receipt = {
                        "operation_id": (
                            f"medical-report-image:{image_fingerprint[:32]}"
                        ),
                        "status": "verified",
                        "resource_type": "medical_exam",
                        "resource_id": str(exam.id),
                        "verified": True,
                        "verification_scope": "persistence_only",
                        "content_verified": False,
                    }
                    if receipt not in self._turn_attachment_write_receipts:
                        self._turn_attachment_write_receipts.append(receipt)
                recognized.append((exam, result, items, image_fingerprint))

            if not recognized:
                return None

            if created_any:
                self._turn_twin_write_occurred = True
                try:
                    invalidate_twin(user_id)
                except Exception:
                    pass

            def _is_numeric(item: dict) -> bool:
                value = item.get("value")
                if value is None:
                    return False
                try:
                    float(value)
                    return True
                except (ValueError, TypeError):
                    return False

            total_numeric = sum(
                1
                for _exam, _result, report_items, _fingerprint in recognized
                for item in report_items
                if _is_numeric(item)
            )
            abnormal_items = [
                item
                for _exam, _result, report_items, _fingerprint in recognized
                for item in report_items
                if item.get("is_abnormal") and _is_numeric(item)
            ]
            narrative_texts = [
                str(result.get("conclusion") or "").strip()
                for _exam, result, _items, _fingerprint in recognized
                if str(result.get("conclusion") or "").strip()
            ]

            parts: list[str] = []
            if total_numeric:
                parts.append(
                    (
                        f"已从图片中识别 {total_numeric} 项化验指标并写入系统。"
                        if persist
                        else f"已从图片中识别 {total_numeric} 项化验指标。"
                    )
                )
            if narrative_texts:
                joined = "\n".join(narrative_texts)
                echoed = (
                    joined
                    if len(joined) <= 800
                    else f"{joined[:800]}……(OCR 文字过长已截断)"
                )
                parts.append(f"OCR 识别文字（待核对）：\n{echoed}")
            if not parts:
                parts.append("已识别图片中的医疗报告。")
            if persist:
                exam_ids = ", ".join(
                    str(exam.id)
                    for exam, _result, _items, _fingerprint in recognized
                    if exam is not None
                )
                parts.append(f"报告已保存，记录 ID: {exam_ids}；OCR 内容尚未核对。")
            else:
                parts.append("本次仅用于分析，尚未保存。")
            if abnormal_items:
                abnormal_text = "；".join(
                    (
                        f"{item.get('name') or item.get('item_name') or item.get('name_en')} "
                        f"{item.get('value')} {item.get('unit') or ''}"
                    ).strip()
                    for item in abnormal_items[:8]
                )
                parts.append(f"OCR 标记的数值异常（待核对）：{abnormal_text}。")
            return "\n".join(parts)
        except Exception:
            logger.warning(
                "[Vision] medical report processing failed user=%s",
                user_id,
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def _normalize_query_only_health_manage_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Keep explicit diet queries read-only and resolve relative dates locally."""
        scope = _query_only_health_manage_scope(
            getattr(self, "_current_turn_user_message", ""),
            reference_now=self._agent_kernel_reference_now(),
        )
        if scope is None:
            return tool_calls

        def _list_args_from_scope(args: Dict[str, Any]) -> Dict[str, Any]:
            list_args: Dict[str, Any] = {
                "record_type": "diet",
                "operation": "list",
            }
            target_date = scope.get("date")
            if target_date:
                list_args["date"] = target_date
            elif args.get("operation") == "list":
                model_date = _normalize_relative_date(
                    args.get("date"),
                    reference_now=self._agent_kernel_reference_now(),
                )
                if model_date:
                    list_args["date"] = model_date
            if scope.get("meal_type"):
                list_args["meal_type"] = scope["meal_type"]
            elif args.get("operation") == "list":
                model_meal_type = _normalize_diet_meal_type(args.get("meal_type"))
                if model_meal_type:
                    list_args["meal_type"] = model_meal_type
            limit = args.get("limit")
            if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
                list_args["limit"] = limit
            return list_args

        normalized: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            tool_name = function.get("name")
            raw_args = function.get("arguments")
            try:
                args = (
                    json.loads(raw_args)
                    if isinstance(raw_args, str)
                    else dict(raw_args or {})
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                normalized.append(tool_call)
                continue

            if tool_name == "health_record":
                list_args = _list_args_from_scope({})
                logger.warning(
                    "[agent_executor] query-only model write normalized to diet list: "
                    "tool=%s record_type=%s",
                    tool_name,
                    args.get("record_type") or args.get("type"),
                )
                normalized.append({
                    **tool_call,
                    "function": {
                        **function,
                        "name": "health_manage",
                        "arguments": json.dumps(list_args, ensure_ascii=False),
                    },
                })
                continue

            if tool_name != "health_manage" or args.get("record_type") != "diet":
                normalized.append(tool_call)
                continue

            list_args = _list_args_from_scope(args)
            if args != list_args:
                logger.warning(
                    "[agent_executor] query-only health_manage normalized to list: "
                    "operation=%s date=%s -> date=%s",
                    args.get("operation"),
                    args.get("date"),
                    list_args.get("date"),
                )
            normalized.append({
                **tool_call,
                "function": {
                    **function,
                    "arguments": json.dumps(list_args, ensure_ascii=False),
                },
            })
        return normalized

    async def _normalize_latest_diet_delete_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        user_auth_token: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Resolve an explicit latest-meal delete to an exact ID before write tracking.

        The preflight is read-only and uses untruncated JSON. A failed lookup leaves
        the original call untouched so the validator rejects its missing ID. A list
        call is never upgraded into a mutation.
        """
        normalized: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            if function.get("name") != "health_manage":
                normalized.append(tool_call)
                continue
            raw_args = function.get("arguments")
            try:
                args = (
                    json.loads(raw_args)
                    if isinstance(raw_args, str)
                    else dict(raw_args or {})
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                normalized.append(tool_call)
                continue
            if (
                args.get("record_type") != "diet"
                or args.get("operation") != "delete"
                or args.get("record_id") not in (None, "", False)
                or not _is_explicit_latest_diet_delete(
                    getattr(self, "_current_turn_user_message", "")
                )
            ):
                normalized.append(tool_call)
                continue

            query: Dict[str, Any] = {"limit": 1}
            target_date = _normalize_relative_date(
                args.get("date"),
                reference_now=self._agent_kernel_reference_now(),
            )
            target_meal_type = _normalize_diet_meal_type(args.get("meal_type"))
            if target_date:
                query["start_date"] = target_date
                query["end_date"] = target_date
            if target_meal_type:
                query["meal_type"] = target_meal_type
            base_url = settings.health_api_base_url or "http://localhost:8000/api/v1"
            headers = (
                {"Authorization": f"Bearer {user_auth_token}"}
                if user_auth_token else {}
            )
            records, error = await self._api_get_json(
                f"{base_url}/diet/records/me?{urlencode(query)}",
                headers,
            )
            latest = records[0] if isinstance(records, list) and records else None
            record_id = (
                latest.get("id") or latest.get("record_id")
                if isinstance(latest, dict) else None
            )
            if error or record_id in (None, "", False):
                logger.warning(
                    "[health_manage] latest diet delete preflight failed user=%s error=%s",
                    self._current_user_id,
                    error or "record_not_found",
                )
                normalized.append(tool_call)
                continue

            resolved_args = dict(args)
            resolved_args["record_id"] = record_id
            normalized.append({
                **tool_call,
                "function": {
                    **function,
                    "arguments": json.dumps(resolved_args, ensure_ascii=False),
                },
            })
        return normalized

    async def _normalize_explicit_diet_update_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        user_auth_token: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Resolve a concrete meal correction to one existing record and update it.

        The target date, meal and replacement food are parsed from the user's
        message, never from model-authored arguments. Exactly one server-side
        candidate is required. Zero or multiple candidates are converted to a
        read-only lookup so a model mistake cannot create a duplicate or edit an
        arbitrary meal.
        """
        correction = _parse_explicit_diet_correction(
            getattr(self, "_current_turn_user_message", ""),
            reference_now=self._agent_kernel_reference_now(),
        )
        if not correction:
            return tool_calls

        base_url = settings.health_api_base_url or "http://localhost:8000/api/v1"
        headers = (
            {"Authorization": f"Bearer {user_auth_token}"}
            if user_auth_token else {}
        )
        query = {
            "limit": 20,
            "start_date": correction["date"],
            "end_date": correction["date"],
            "meal_type": correction["meal_type"],
        }
        records: Any = None
        lookup_error: Optional[str] = None
        lookup_done = False

        async def _lookup_records() -> tuple[Any, Optional[str]]:
            nonlocal records, lookup_error, lookup_done
            if not lookup_done:
                records, lookup_error = await self._api_get_json(
                    f"{base_url}/diet/records/me?{urlencode(query)}",
                    headers,
                )
                lookup_done = True
            return records, lookup_error

        normalized: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            tool_name = function.get("name")
            raw_args = function.get("arguments")
            try:
                args = (
                    json.loads(raw_args)
                    if isinstance(raw_args, str)
                    else dict(raw_args or {})
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                normalized.append(tool_call)
                continue

            is_diet_manage = (
                tool_name == "health_manage"
                and args.get("record_type") == "diet"
                and args.get("operation") in {"list", "update"}
            )
            is_diet_create = (
                tool_name == "health_record"
                and args.get("record_type") == "diet"
            )
            if not is_diet_manage and not is_diet_create:
                normalized.append(tool_call)
                continue

            candidates, error = await _lookup_records()
            candidate_rows = [
                row for row in (candidates if isinstance(candidates, list) else [])
                if isinstance(row, dict)
                and (row.get("id") or row.get("record_id")) not in (None, "", False)
            ]
            update_data = (
                _diet_correction_update_data(correction, candidate_rows[0])
                if not error and len(candidate_rows) == 1
                else None
            )
            if update_data is not None:
                record_id = candidate_rows[0].get("id") or candidate_rows[0].get("record_id")
                resolved_args = {
                    "record_type": "diet",
                    "operation": "update",
                    "record_id": record_id,
                    "data": update_data,
                }
                logger.info(
                    "[health_manage] resolved explicit diet correction user=%s record_id=%s meal=%s",
                    self._current_user_id,
                    record_id,
                    correction["meal_type"],
                )
            else:
                resolved_args = {
                    "record_type": "diet",
                    "operation": "list",
                    "date": correction["date"],
                    "meal_type": correction["meal_type"],
                    "limit": 20,
                }
                logger.warning(
                    "[health_manage] diet correction target unresolved user=%s meal=%s candidates=%s error=%s",
                    self._current_user_id,
                    correction["meal_type"],
                    len(candidate_rows),
                    error or (
                        "record_has_no_scalable_nutrition"
                        if len(candidate_rows) == 1
                        else "ambiguous_target"
                    ),
                )
                self._turn_diet_correction_unresolved_reason = (
                    "record_has_no_scalable_nutrition"
                    if len(candidate_rows) == 1
                    else "ambiguous_target"
                )

            normalized.append({
                **tool_call,
                "function": {
                    **function,
                    "name": "health_manage",
                    "arguments": json.dumps(resolved_args, ensure_ascii=False),
                },
            })
        return normalized

    async def _run_tool_with_progress(
        self,
        func_name: str,
        func_args: Any,
        user_auth_token: Optional[str],
        progress_label: str,
    ):
        """执行工具,期间周期性吐 status 心跳(保活 + 进度可见),并施加 per-tool 超时预算。

        Wave 2(2026-07-14):慢工具内联 await 期间 SSE 流零事件 → 连接可被 nginx idle
        read-timeout 掐断 + 用户看冻结转圈。本 helper 把工具跑进 task,每
        _TOOL_HEARTBEAT_INTERVAL_S 让出一次 status 心跳;超过 per-tool 预算 → 取消 task 并
        返回 fail-loud 结果串(绝不 hang/静默)。

        yields ('heartbeat', <status event dict>) 若干,最后**恰好一个** ('result', <str>)。
        契约:无论成功/超时/异常,末尾必产出一个 ('result', str),调用方据此赋值 result。
        finally 里取消未完成 task,保证消费方提前关闭生成器(客户端断连)时不泄漏。
        """
        retry_attempt = 0
        while True:
            timeout_s = _TOOL_TIMEOUT_OVERRIDES.get(func_name, _TOOL_TIMEOUT_DEFAULT_S)
            task = asyncio.create_task(
                self._execute_tool(func_name, func_args, user_auth_token)
            )
            waited = 0.0
            result = ""
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=_TOOL_HEARTBEAT_INTERVAL_S)
                    if task.done():
                        break
                    waited += _TOOL_HEARTBEAT_INTERVAL_S
                    if waited >= timeout_s:
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):  # noqa: BLE001
                            pass
                        logger.warning(
                            f"[tool timeout] {func_name} 超过 {timeout_s:.0f}s 被中止"
                        )
                        result = (
                            f"Error: {progress_label}耗时过长(超过 {int(timeout_s)} 秒),"
                            "已中止。请稍后重试。"
                        )
                        break
                    # 心跳 status(与既有 stage=tool 契约同源:客户端显示进度 label + 保活)
                    yield (
                        "heartbeat",
                        {
                            "event": "status",
                            "data": {
                                "stage": "tool",
                                "label": progress_label,
                                "detail": "running",
                            },
                        },
                    )
                if not result:
                    try:
                        result = task.result()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "[tool exec] failed tool=%s error_type=%s",
                            func_name,
                            type(e).__name__,
                        )
                        result = f"Error: {progress_label}执行失败,请稍后重试。"
            finally:
                if not task.done():
                    task.cancel()

            if should_retry_tool_failure(func_name, result, attempt=retry_attempt):
                retry_attempt += 1
                self._agent_kernel_tool_retry_count += 1
                logger.warning(
                    "[tool recovery] retrying transient read failure tool=%s attempt=%d",
                    func_name,
                    retry_attempt,
                )
                yield (
                    "heartbeat",
                    {
                        "event": "status",
                        "data": {
                            "stage": "tool",
                            "label": progress_label,
                            "detail": "retrying",
                        },
                    },
                )
                continue

            yield ("result", result)
            return

    async def _execute_tool(
        self,
        tool_name: str,
        args_raw: Any,
        user_token: Optional[str],
        *,
        source: str = "structured_or_recovered",
    ) -> str:
        """Kernel-instrumented tool boundary used by every executable surface."""
        self._ensure_agent_kernel_turn()
        self._agent_kernel_last_decision = None
        if self._agent_kernel_event_bus is not None:
            self._agent_kernel_event_bus.tool_requested(
                ToolExecutionRequest(
                    tool_name=tool_name,
                    arguments=args_raw,
                    source=source,
                )
            )
        result = await self._execute_tool_impl(
            tool_name, args_raw, user_token, source=source
        )
        return self._agent_kernel_record_tool_result(
            tool_name,
            _parse_tool_arguments_for_telemetry(args_raw),
            result,
        )

    async def _execute_recipe_step(
        self, tool_name: str, args_raw: Any, user_token: Optional[str]
    ) -> str:
        """Execute a server-stored recipe step under its narrow policy source."""
        return await self._execute_tool(
            tool_name,
            args_raw,
            user_token,
            source="procedure_recipe_replay",
        )

    async def _execute_tool_impl(
        self,
        tool_name: str,
        args_raw: Any,
        user_token: Optional[str],
        *,
        source: str = "structured_or_recovered",
    ) -> str:
        """执行工具调用，返回结果文本"""
        try:
            if isinstance(args_raw, str):
                args = json.loads(args_raw)
            else:
                args = args_raw
        except json.JSONDecodeError:
            # 弱模型(如 glm-5.1)常吐弯引号/全角引号或被截断的 JSON → 标准解析失败。
            # 逐级兜底(引号归一 / 截断修复)后重试;仍失败才把错误返回给 LLM
            # (它会重试),不裸露给用户。
            if isinstance(args_raw, str):
                try:
                    args = _loads_lenient(args_raw)
                except json.JSONDecodeError:
                    recovered = _extract_clear_symptom_record(
                        getattr(self, "_current_turn_user_message", "")
                    )
                    if tool_name == "health_record" and recovered:
                        logger.warning(
                            "[_execute_tool] recovered malformed symptom args from clear user statement"
                        )
                        args = {
                            "record_type": "symptom",
                            "data": recovered,
                        }
                    else:
                        logger.warning(
                            "[_execute_tool] %s args 解析失败(含引号归一+截断修复后) "
                            "argument_chars=%s",
                            tool_name,
                            len(args_raw),
                        )
                        return local_write_rejection(
                            "tool_arguments_invalid",
                            message="工具参数无法解析。",
                            recovery_guidance="请重新生成完整的结构化参数。",
                        )
            else:
                return local_write_rejection(
                    "tool_arguments_invalid",
                    message="工具参数无法解析。",
                    recovery_guidance="请重新生成完整的结构化参数。",
                )

        trusted_recipe_authorized = False
        if tool_name == "health_record" and isinstance(args, dict):
            if source == "procedure_recipe_replay":
                # Recipe replay has already passed the server-side confirmation
                # tier in procedure_recipe_service.  AUTO steps arrive without
                # this marker; typed-only/never-auto steps carry it and must not
                # inherit authorization from either model flags or the generic
                # recipe trigger intent.
                trusted_recipe_authorized = bool(
                    args.get("_fast_record_requires_confirmation") is not True
                )
            _strip_untrusted_write_authorization(args)

        if self._runtime_write_block_reason:
            from app.services.agent_kernel.tool_registry import classify_tool_effect

            try:
                runtime_effect = classify_tool_effect(tool_name, args)
            except Exception:
                logger.exception(
                    "Runtime control unavailable and tool effect classification failed: "
                    "tool=%s reason=%s",
                    tool_name,
                    self._runtime_write_block_reason,
                )
                return json.dumps(
                    {
                        "status": "failed",
                        "success": False,
                        "error_code": "runtime_control_unavailable",
                        "dispatch_started": False,
                    },
                    ensure_ascii=False,
                )
            if runtime_effect == "write":
                logger.warning(
                    "Runtime control unavailable; blocked dynamic write before dispatch: "
                    "tool=%s reason=%s",
                    tool_name,
                    self._runtime_write_block_reason,
                )
                return json.dumps(
                    {
                        "status": "failed",
                        "success": False,
                        "error_code": "runtime_control_unavailable",
                        "dispatch_started": False,
                    },
                    ensure_ascii=False,
                )

        # === 统一 tool_call 守门 (所有 6 个工具必过) ===
        # 日期/数值/枚举/引用 ID 存在性/越权 / 必填 — 触发 coerce 只 log,
        # 必填缺失或越权才返回 error 给 LLM (它会重试).
        from app.services.llm.tool_validator import validate_tool_call
        args = _recover_clear_symptom_args(
            args,
            getattr(self, "_current_turn_user_message", ""),
        )
        symptom_authorization = _symptom_write_authorization(
            getattr(self, "_current_turn_user_message", ""),
            getattr(self, "_current_turn_recent_messages", []),
        )
        rhinitis_authorization = _extract_clear_rhinitis_record(
            getattr(self, "_current_turn_user_message", "")
        )
        if (
            tool_name == "health_record"
            and isinstance(args, dict)
            and _fast_record_kind(args) == "rhinitis"
            and getattr(self, "_current_turn_has_attachment", False)
        ):
            logger.warning(
                "[_execute_tool] blocked rhinitis write on attachment turn user=%s",
                self._current_user_id,
            )
            return local_write_rejection(
                "rhinitis_attachment_not_supported",
                message="带附件的消息不能自动写入鼻炎症状记录。",
                recovery_guidance=(
                    "请在不带附件的新消息中直接复述要记录的本人喷嚏、"
                    "鼻塞或流鼻涕情况。"
                ),
            )
        if (
            tool_name == "health_record"
            and isinstance(args, dict)
            and _fast_record_kind(args) == "rhinitis"
            and rhinitis_authorization is None
        ):
            logger.warning(
                "[_execute_tool] blocked rhinitis write without current-turn authorization "
                "user=%s message_chars=%s",
                self._current_user_id,
                len(getattr(self, "_current_turn_user_message", "") or ""),
            )
            return local_write_rejection(
                "rhinitis_write_not_authorized",
                message="当前消息不是明确的本人鼻炎症状记录请求。",
                recovery_guidance="请直接说出当前的喷嚏、鼻塞或流鼻涕情况。",
            )
        if (
            tool_name == "health_record"
            and isinstance(args, dict)
            and _fast_record_kind(args) == "rhinitis"
        ):
            authorized_args = _apply_authorized_rhinitis_payload(
                args,
                rhinitis_authorization,
            )
            if authorized_args is None:
                return local_write_rejection(
                    "rhinitis_payload_invalid",
                    message="鼻炎症状记录参数无效。",
                    recovery_guidance="请直接复述当前要记录的本人症状。",
                )
            args = authorized_args
        if (
            tool_name == "health_record"
            and isinstance(args, dict)
            and _fast_record_kind(args) == "symptom"
            and getattr(self, "_current_turn_has_attachment", False)
        ):
            logger.warning(
                "[_execute_tool] blocked symptom write on attachment turn user=%s",
                self._current_user_id,
            )
            return local_write_rejection(
                "symptom_attachment_not_supported",
                message="带附件的消息不能自动写入症状记录。",
                recovery_guidance="请在不带附件的新消息中直接复述要记录的本人症状。",
            )
        if (
            tool_name == "health_record"
            and isinstance(args, dict)
            and _fast_record_kind(args) == "symptom"
            and symptom_authorization is None
        ):
            logger.warning(
                "[_execute_tool] blocked symptom write without current-turn authorization "
                "user=%s message_chars=%s",
                self._current_user_id,
                len(getattr(self, "_current_turn_user_message", "") or ""),
            )
            return local_write_rejection(
                "symptom_write_not_authorized",
                message="当前消息不是明确的本人症状记录请求。",
                recovery_guidance="请直接说出当前要记录的本人症状。",
            )
        if (
            tool_name == "health_record"
            and isinstance(args, dict)
            and _fast_record_kind(args) == "symptom"
        ):
            authorized_args = _apply_authorized_symptom_payload(
                args,
                symptom_authorization,
            )
            if authorized_args is None:
                return local_write_rejection(
                    "symptom_payload_invalid",
                    message="症状记录参数无效。",
                    recovery_guidance="请直接复述当前要记录的本人症状。",
                )
            args = authorized_args
        args = _prepare_health_record_args_for_validation(
            tool_name,
            args,
            reference_now=self._agent_kernel_reference_now(),
        )
        args = _apply_server_health_record_provenance(
            tool_name,
            args,
            execution_source=source,
            has_attachment=bool(
                getattr(self, "_current_turn_has_attachment", False)
            ),
            diet_photo_auto_save=bool(
                getattr(self, "_diet_photo_auto_save", False)
            ),
            contextual_diet_recorded=bool(
                getattr(self, "_turn_contextual_diet_record_id", None)
                is not None
            ),
            user_message=str(
                getattr(self, "_current_turn_user_message", "") or ""
            ),
        )
        v = validate_tool_call(
            tool_name,
            args,
            db=self.db,
            user_id=self._current_user_id,
            reference_now=self._agent_kernel_reference_now(),
        )
        if v["error"]:
            return local_write_rejection(
                str(v.get("error_code") or "tool_validation_failed"),
                message=str(v["error"]).removeprefix("Error:").strip(),
                recovery_guidance="请修正参数后重新提交。",
            )
        args = v["data"]
        if tool_name == "health_record" and trusted_recipe_authorized:
            args["_trusted_server_write_authorized"] = True

        # === Read-only pregen guard (rank7) — fail-CLOSED single choke ===
        # In a starter-answer pre-generation turn ONLY read-only analysis tools may
        # run. Any tool not on the allowlist (write tools, uploads, unknown, future)
        # is refused HERE, before any _exec_* runs, so no user data is ever mutated
        # during pregen. We flag the attempt so the orchestrator aborts pregen and
        # stores nothing (starter chips are analysis prompts — a write attempt means
        # the answer must not be pre-served; the tap falls through to a live turn).
        if getattr(self, "_read_only_turn", False):
            if not _tool_call_is_read_only(tool_name, args):
                self._read_only_turn_write_attempted = True
                logger.warning(
                    "[agent_executor] read-only pregen turn blocked non-read tool=%s user=%s",
                    tool_name, self._current_user_id,
                )
                return local_write_rejection(
                    "read_only_write_blocked",
                    message="只读预生成回合不执行写入或变更操作。",
                )

        try:
            from app.services.agent_kernel.tool_gateway import (
                ToolGateway,
                ToolPreflightError,
            )

            snapshot = self._ensure_agent_kernel_turn()
            gateway_result = await ToolGateway(snapshot).execute(
                ToolExecutionRequest(
                    tool_name=tool_name,
                    arguments=args,
                    source=source,
                ),
                lambda request: self._dispatch_tool_request(request, user_token),
                on_decision=lambda decision: (
                    self._agent_kernel_record_capability_decision(
                        tool_name,
                        decision,
                    )
                ),
            )
            return str(gateway_result.content)
        except ToolPreflightError as exc:
            if "policy_check_failed" not in self._agent_kernel_capability_block_reasons:
                self._agent_kernel_capability_block_reasons.append("policy_check_failed")
            logger.error(
                "[agent_kernel] gateway failed tool=%s user=%s error_type=%s",
                tool_name,
                self._current_user_id,
                type(exc).__name__,
            )
            return local_write_rejection(
                "policy_check_failed",
                message="工具调用策略检查失败，已阻止执行。",
                recovery_guidance="请稍后重试；本次没有派发写入。",
            )

    async def _dispatch_tool_request(
        self,
        request: ToolExecutionRequest,
        user_token: Optional[str],
    ) -> str:
        """Dispatch one policy-approved request through its registered adapter."""
        runtime_operation = None
        runtime_coordinator = None
        runtime_context = None

        def finalize_uncertain_operation() -> None:
            if (
                runtime_operation is None
                or runtime_coordinator is None
                or runtime_context is None
            ):
                return
            try:
                runtime_coordinator.finalize_tool_operation(
                    runtime_context,
                    operation_id=runtime_operation.operation_id,
                    status="reconciliation_required",
                    error_code="write_uncertain",
                )
            except Exception as finalize_exc:  # noqa: BLE001
                logger.error(
                    "Runtime tool operation finalize failed operation=%s error_type=%s",
                    runtime_operation.operation_id,
                    type(finalize_exc).__name__,
                )

        try:
            from app.services.agent_kernel.tool_registry import get_tool_spec

            spec = get_tool_spec(request.tool_name)
            args = request.arguments if isinstance(request.arguments, dict) else {}
            expected_resource_type = spec.reconciliation_resource_type(args)
            if (
                self._runtime_managed
                and self._runtime_run_id
                and self._runtime_attempt_id
                and self._current_user_id is not None
                and spec.requires_verified_receipt(args)
            ):
                from app.services.agent_runtime import (
                    AgentRuntimeCoordinator,
                    RunContext,
                )

                runtime_coordinator = AgentRuntimeCoordinator(self.db)
                runtime_context = RunContext(
                    run_id=self._runtime_run_id,
                    attempt_id=self._runtime_attempt_id,
                    user_id=self._current_user_id,
                    conversation_id=None,
                    client_turn_id=None,
                    input_seq=None,
                    origin="executor",
                )
                operation_fingerprint = _runtime_write_operation_fingerprint(
                    request.tool_name,
                    args,
                    default_record_date=(
                        self._agent_kernel_reference_now().strftime("%Y-%m-%d")
                    ),
                )
                (
                    logical_operation_key,
                    logical_operation_scope_key,
                    logical_operation_discriminator_kind,
                    logical_operation_discriminator_key,
                ) = _runtime_write_operation_identity(
                    request.tool_name,
                    args,
                    default_record_date=(
                        self._agent_kernel_reference_now().strftime("%Y-%m-%d")
                    ),
                )
                runtime_operation = runtime_coordinator.claim_tool_operation(
                    runtime_context,
                    tool_name=request.tool_name,
                    effect_class="write",
                    operation_fingerprint=operation_fingerprint,
                    expected_resource_type=expected_resource_type,
                    logical_operation_key=logical_operation_key,
                    logical_operation_scope_key=logical_operation_scope_key,
                    logical_operation_discriminator_kind=(
                        logical_operation_discriminator_kind
                    ),
                    logical_operation_discriminator_key=(
                        logical_operation_discriminator_key
                    ),
                )
                if runtime_operation.disposition == "replay":
                    return json.dumps(
                        {
                            "status": "verified",
                            "success": True,
                            "operation_id": runtime_operation.operation_id,
                            "resource_type": runtime_operation.resource_type,
                            "resource_id": runtime_operation.resource_id,
                            "replayed": True,
                        },
                        ensure_ascii=False,
                    )
                if runtime_operation.disposition == "reconcile":
                    return json.dumps(
                        {
                            "status": "uncertain",
                            "dispatch_started": True,
                            "error_code": runtime_operation.error_code
                            or "write_uncertain",
                        },
                        ensure_ascii=False,
                    )
                if runtime_operation.disposition == "reject":
                    return json.dumps(
                        {
                            "status": "failed",
                            "success": False,
                            "dispatch_started": False,
                            "error_code": runtime_operation.error_code
                            or "retry_plan_mismatch",
                        },
                        ensure_ascii=False,
                    )

            if spec.requires_verified_receipt(args):
                self._persist_current_turn_write_dispatch_started(
                    tool_name=request.tool_name,
                    parsed_args=args,
                )

            if spec.adapter_kind == "specialist":
                from app.services.specialist_tools import run_specialist_tool

                return await asyncio.to_thread(
                    run_specialist_tool,
                    self.db,
                    self._current_user_id,
                    request.tool_name,
                )
            if spec.executor_method is None:
                raise RuntimeError("tool_adapter_missing")
            if spec.marks_deep_analysis:
                self._turn_invoked_deep_analysis = True
            handler = getattr(self, spec.executor_method)
            handler_args = args
            if (
                runtime_operation is not None
                and request.tool_name == "upload_medical_exam_text"
            ):
                handler_args = {
                    **args,
                    "_runtime_operation_id": runtime_operation.operation_id,
                }
            if spec.call_style == "http":
                base_url = (
                    settings.health_api_base_url
                    or "http://localhost:8000/api/v1"
                )
                headers = (
                    {"Authorization": f"Bearer {user_token}"}
                    if user_token
                    else {}
                )
                if (
                    runtime_operation is not None
                    and expected_resource_type is not None
                ):
                    headers["Idempotency-Key"] = runtime_operation.operation_id
                result = await handler(base_url, headers, handler_args)
            else:
                result = await handler(handler_args)
            result = (
                annotate_if_implausible(result)
                if spec.annotate_implausible
                else result
            )
            if (
                runtime_operation is not None
                and runtime_coordinator is not None
                and runtime_context is not None
            ):
                receipt = _write_receipt_from_tool_result(
                    request.tool_name,
                    args,
                    result,
                )
                outcome = classify_write_execution(result, receipt=receipt)
                if is_legacy_local_write_rejection(result):
                    logger.warning(
                        "legacy local write rejection contract tool=%s",
                        request.tool_name,
                    )
                if outcome.status == "verified" and receipt is not None:
                    runtime_coordinator.finalize_tool_operation(
                        runtime_context,
                        operation_id=runtime_operation.operation_id,
                        status="succeeded",
                        resource_type=str(receipt.get("resource_type") or ""),
                        resource_id=str(receipt.get("resource_id") or ""),
                    )
                elif outcome.status in {"rejected", "failed"} and (
                    outcome.dispatch_started is False
                ):
                    runtime_coordinator.finalize_tool_operation(
                        runtime_context,
                        operation_id=runtime_operation.operation_id,
                        status="failed",
                        error_code="tool_rejected",
                    )
                else:
                    runtime_coordinator.finalize_tool_operation(
                        runtime_context,
                        operation_id=runtime_operation.operation_id,
                        status="reconciliation_required",
                        error_code=(
                            "missing_receipt"
                            if outcome.error_code == "missing_receipt"
                            else "write_uncertain"
                        ),
                    )
            return result
        except asyncio.CancelledError:
            # Cancellation may arrive after an external write crossed its
            # dispatch boundary. Persist uncertainty before propagating the
            # cancellation so a replacement worker cannot repeat the write.
            finalize_uncertain_operation()
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "tool execution failed tool=%s error_type=%s operation=%s run=%s",
                request.tool_name,
                type(exc).__name__,
                (
                    runtime_operation.operation_id
                    if runtime_operation is not None
                    else None
                ),
                self._runtime_run_id,
            )
            finalize_uncertain_operation()
            return f"Error: {safe_tool_error_message(request.tool_name, exc)}"

    def _agent_kernel_record_capability_decision(
        self,
        requested_tool_name: str,
        decision: CapabilityDecision,
    ) -> None:
        self._agent_kernel_last_decision = decision
        if self._agent_kernel_event_bus is not None:
            self._agent_kernel_event_bus.capability_decided(
                tool_name=decision.normalized_tool_name or requested_tool_name,
                action=decision.action,
                reason=decision.reason,
            )
        snapshot = self._ensure_agent_kernel_turn()
        if decision.action != "block" or snapshot.policy_mode != "enforce":
            return
        if decision.reason not in self._agent_kernel_capability_block_reasons:
            self._agent_kernel_capability_block_reasons.append(decision.reason)
        logger.warning(
            "[agent_kernel] blocked tool=%s user=%s reason=%s intent=%s/%s/%s",
            requested_tool_name,
            self._current_user_id,
            decision.reason,
            snapshot.intent.primary,
            snapshot.intent.domain,
            snapshot.intent.operation,
        )

    async def _exec_knowledge_search(self, args: dict) -> str:
        """检索已审定 System KB v2, fail-honest, 不静默返回空。

        common ``knowledge_search`` 是用户可见医学依据的运行时边界,只允许
        owner-reviewed System KB 结论。得到/Dedao 素材只可参与离线选题、改写与审核,
        不得作为 raw runtime fallback;否则 reviewed KB 的未命中/故障会被伪装成有依据。
        """
        query = (args.get("query") or "").strip()
        if not query:
            return "Error: knowledge_search 需要 query 参数"
        from app.services.retrieval_guard import guard_retrieval_query

        guarded_query = guard_retrieval_query(query)
        query = guarded_query.query

        n = args.get("n_results", 5)
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 5
        n = max(1, min(8, n))

        # 已审定 System KB v2 claims (通用 reviewed 结论, 非个性化)。
        kb_results: list[dict] = []
        kb_errored = False
        try:
            from app.services.system_knowledge_service import search_knowledge as kb_search
            kb_payload = kb_search(self.db, query, limit=n)
            kb_results = (kb_payload or {}).get("results") or []
        except Exception as e:  # noqa: BLE001 — fail honest, 不冒充未命中
            logger.warning(f"[knowledge_search] System KB 检索失败: {e}")
            kb_results = []
            kb_errored = True

        if not kb_results:
            if kb_errored:
                return (
                    "已审定知识库检索失败(暂不可用),"
                    "请基于已有信息谨慎作答,勿编造依据或引用。"
                )
            return (
                f"已审定知识库未命中『{query}』相关条目(该主题可能未收录)。"
                "请如实说明缺少本系统已审定依据,勿编造引用。"
            )

        kb_lines = [
            "【已审定知识库(owner-reviewed,通用结论,需结合个人情况,非诊断)】",
            "(以下为已审定的通用医学结论,非针对当前用户的个性化判断;"
            "个性化证据见 Twin evidence card。仅供参考,不替代医生,不得据此开处方/给剂量)",
            "以下条目按主题相关性召回,未经『是否适用于本用户』判定;"
            "若与本用户实际指标/基因/用药不符,以 Twin evidence card 为准并忽略本条。",
        ]
        for i, r in enumerate(kb_results, 1):
            doc = (r.get("document") or {}) if isinstance(r, dict) else {}
            title = (doc.get("title") or "").strip()
            snippet = (doc.get("summary") or doc.get("body") or "").strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + "…"
            evidence = (doc.get("evidence_level") or "").strip()
            label = title or doc.get("doc_id") or "结论"
            head = f"{i}. [{label}]"
            if evidence:
                head += f"(证据等级 {evidence})"
            kb_lines.append(f"{head} {snippet}")
        return "\n".join(kb_lines)

    async def _exec_realtime_search(self, args: dict) -> str:
        """实时联网检索(阿里云 IQS)给 chat/体检分析路径做最新指南/时效事实接地。

        隐私: 只把模型给的 query 传给 IQS, **绝不**注入 Twin/PII —— 比 orchestrator
        (送原始用户问句)更克制, 保持这一点, 不要用用户数据丰富 query。
        fail-honest: 失败/未启用/无命中各有诚实措辞, 绝不静默冒充成功。
        """
        query = (args.get("query") or "").strip()
        if not query:
            return "Error: realtime_search 需要 query 参数"

        from app.services.iqs_search import fetch_realtime_evidence
        try:
            block = await fetch_realtime_evidence(query)
        except Exception as e:  # noqa: BLE001 — fail honest, 不冒充成功
            logger.warning(f"[realtime_search] IQS 检索失败: {e}")
            return "实时检索暂不可用,请基于已有信息谨慎作答,勿编造依据。"

        if not block:
            return (
                "实时检索未返回结果(可能未启用或无命中);"
                "请如实说明依据来自通用知识,勿编造引用。"
            )
        return (
            "以下为实时联网检索结果(仅供参考,不替代医生,"
            "不得据此开处方/给剂量;须结合用户个人情况):\n"
            + block
        )

    async def _exec_health_query(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康数据查询"""
        args = _normalize_health_query_args(args)
        dim = args.get("dimension", "comprehensive")
        days = args.get("days", 7)
        indicator = args.get("indicator", "")
        keyword = args.get("keyword") or args.get("keywords") or args.get("query") or ""
        if isinstance(keyword, list):
            keyword = " ".join(str(x) for x in keyword if x)
        uploaded_since = args.get("uploaded_since") or args.get("created_since") or ""
        uploaded_days = args.get("uploaded_days") or args.get("created_days")
        today = self._agent_kernel_reference_now().strftime("%Y-%m-%d")

        def with_blood_pressure_safety(result: str) -> str:
            if dim != "blood_pressure":
                return result
            from app.utils.blood_pressure_classify import append_severe_bp_reading_warning

            return append_severe_bp_reading_warning(result)

        # Canonical 归一读层 (docs/design-canonical-read-layer.md): 已迁维度直读
        # service/repo 层 (与 Twin 同源, 不截断), 未迁维度返回 None → 回退旧 _api_get.
        #   - medical_exam: 读归一化 MedicalIndicator (与 Twin fetch_latest_labs 同源)
        #   - 可穿戴 daily (activity/heart_rate/hrv/body_battery/stress/wearable/garmin):
        #     读 GarminData + device_source_priority 多源合并 (与 Twin 的
        #     MultiSourceIntegrationService 同源), 不再各别名各走一次 /garmin-analysis/me HTTP.
        from app.services import health_read

        canonical = health_read.canonical_read(
            self.db,
            self._current_user_id,
            dim,
            days=days,
            indicator=indicator,
            keyword=str(keyword or ""),
            uploaded_since=str(uploaded_since or ""),
            uploaded_days=uploaded_days,
        )
        if canonical is not None:
            return with_blood_pressure_safety(canonical)

        # D1(garmin-sync 治理 Wave 3):已迁移到进程内直读的维度 → 绕 localhost 回环。
        # flag 关 → inproc 返回 None,落到下面旧 HTTP endpoint_map 路径(逐 release 可回退)。
        if getattr(settings, "reads_in_process", True):
            inproc = await self._read_health_query_dim_in_process(
                dim, days=days, indicator=indicator
            )
            if inproc is not None:
                return with_blood_pressure_safety(inproc)

        endpoint_map = {
            "comprehensive": f"/garmin-analysis/me/comprehensive?days={days}",
            "sleep": f"/garmin-analysis/me/sleep?days={days}",
            "heart_rate": f"/garmin-analysis/me/heart-rate?days={days}",
            "hrv": f"/garmin-analysis/me/hrv?days={days}",
            "activity": f"/garmin-analysis/me/activity?days={days}",
            "spo2": "/spo2/me/latest-night",
            "spo2_sleep_correlation": f"/spo2/me/sleep-correlation?days={days}",
            "body_battery": f"/garmin-analysis/me/body-battery?days={days}",
            # stress 没有独立分析端点; garmin 日行含 stress_level, 按天数取行。
            "stress": f"/daily-health/garmin/me?limit={days}",
            "weight": "/weight/records/me?limit=10",
            "blood_pressure": "/blood-pressure/records/me?limit=10",
            "supplements": f"/supplements/me/stats?days={days}",
            # water 与 diet 同型: 只有 /me/date/{record_date}, 无 /me/today。
            "water": f"/water/records/me/date/{today}",
            # diet 没有 /me/today 端点, 只有 /me/date/{record_date}; 用 today() 拼路径.
            "diet": f"/diet/records/me/date/{today}",
            # exercise 既包含 ExerciseRecord (手动录入的锻炼如俯卧撑/瑜伽),
            # 也要包含 WorkoutRecord (Garmin 同步的跑步/骑行等). LLM 问"昨天跑步"
            # 时应该拿到完整的运动数据.
            # /workout/me?days=N 是 WorkoutRecord, 含跑步/骑行/hiit/...
            # /exercise/me?days=N 是 ExerciseRecord (手动录入)
            # 默认用 workout (真实运动数据); 用户说"我做了 20 个俯卧撑"那种才走 exercise
            "exercise": f"/workout/me?days={days}",
            # 生活事件时间线(情景账本):行程/落地/送达等带 occurred_at+精度
            "events": f"/episodes/me/life-events?days={days}",
            "workout": f"/workout/me?days={days}",
            "manual_exercise": f"/daily-health/exercise/me?days={days}",
            # medical_exam 维度在上面已短路到 MedicalIndicator 表, 不经过此 map.
            "genetic": "/genetic/variants/me",
            "genetic_cognitive": "/genetic/profile/me/cognitive",
            "genetic_personality": "/genetic/profile/me/personality",
            "genetic_comprehensive": "/genetic/profile/me/comprehensive",
            "medication": "/medication/medications/me",
        }

        # 未知 dimension 绝不静默回退 comprehensive:实测 Claude 传 type=medical_records
        # 问膝关节 MRI,被默认成 Garmin 睡眠/心率 → 模型诚实答"没找到 MRI"(假阴)。
        # fail-loud 列合法值,模型下一轮自纠(1 轮换正确数据,优于静默错数据)。
        path = endpoint_map.get(dim)
        if path is None:
            valid_dims = ", ".join(sorted(endpoint_map))
            return (
                f"Error: 未知 dimension '{dim}'。合法值: {valid_dims}。"
                f"请重新调用 health_query 并从中选择(体检/化验/影像报告 → medical_exam)。"
            )

        # 如果查的是基因指标，从结果中过滤特定指标
        # 走 _api_get_json 拿完整数据 (基因常 >3000 字符, 文本版会被截断导致过滤失效)
        if indicator and dim == "genetic":
            parsed, err = await self._api_get_json(f"{base}{path}", headers)
            if not err:
                try:
                    items = parsed if isinstance(parsed, list) else (parsed.get("data", []) if isinstance(parsed, dict) else [])
                    matched = []
                    for v in items:
                        gene = str(v.get("gene_name", "") or v.get("gene", "")).upper()
                        if indicator.upper() in gene:
                            matched.append(v)
                    if matched:
                        return json.dumps(matched, ensure_ascii=False, default=str)
                except Exception:
                    pass

        return with_blood_pressure_safety(await self._api_get(f"{base}{path}", headers))

    async def _read_health_query_dim_in_process(
        self, dim: str, *, days, indicator: str
    ) -> Optional[str]:
        """D1: health_query 已迁移到进程内直读的维度 → 返回截断后文本;未迁移 → None(回退 HTTP)。

        每个维度经 `_read_in_process`(fresh SessionLocal + 线程池)调 `agent_read_tools` 里的
        对应 reader,再统一过 `_truncate_for_display`(与旧 HTTP `_api_get` 同一截断真源)。
        新增维度时只在此加分支 + 写 golden-master parity 测试。
        """
        from app.services import agent_read_tools as art
        from app.services import agent_read_tools_analysis as arta

        uid = self._current_user_id
        if dim == "weight":
            raw = await self._read_in_process(art.read_weight, uid, limit=10)
        elif dim == "blood_pressure":
            raw = await self._read_in_process(art.read_blood_pressure, uid, limit=10)
        elif dim == "water":
            raw = await self._read_in_process(art.read_daily_water, uid)
        elif dim == "diet":
            raw = await self._read_in_process(art.read_daily_diet, uid)
        elif dim in ("workout", "exercise"):
            # 两个 dim 旧端点都是 /workout/me?days=N(WorkoutRecord)。
            raw = await self._read_in_process(art.read_workouts, uid, days=days)
        elif dim == "manual_exercise":
            raw = await self._read_in_process(art.read_manual_exercises, uid, days=days)
        elif dim == "events":
            raw = await self._read_in_process(art.read_life_events, uid, days=days)
        elif dim == "supplements":
            raw = await self._read_in_process(art.read_supplement_stats, uid, days=days)
        # 增量 B2(Tier-5 敏感): genetic 变异位点。user_id + active-profile 双重隔离;
        # indicator 传入按 gene_name 过滤(镜像旧 genetic+indicator 特殊路径)。flag 关时落回
        # 下面 endpoint_map + 旧特殊路径 HTTP。
        elif dim == "genetic":
            raw = await self._read_in_process(art.read_genetic_variants, uid, indicator=indicator)
        # 增量 B1(非敏感确定性分析维度): comprehensive/sleep 复用 GarminAnalysisService,
        # spo2 两维复刻 app/api/spo2.py 确定性算法(见 agent_read_tools_analysis)。
        elif dim == "comprehensive":
            raw = await self._read_in_process(arta.read_comprehensive_analysis, uid, days=days)
        elif dim == "sleep":
            raw = await self._read_in_process(arta.read_sleep_analysis, uid, days=days)
        elif dim == "spo2":
            raw = await self._read_in_process(arta.read_latest_night_spo2, uid)
        elif dim == "spo2_sleep_correlation":
            raw = await self._read_in_process(arta.read_spo2_sleep_correlation, uid, days=days)
        else:
            return None
        return _truncate_for_display(raw)

    async def _exec_health_query_batch(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """声明式批查询: 一次执行多条只读子查询 + 聚合 (Slice 1, 零代码执行)。

        薄接线 —— 校验/聚合/对比逻辑全在 services/health_query_batch.py (纯函数,
        单测覆盖)。这里只注入数据面 fetch: 可穿戴日指标走 GarminData 多源合并
        (复用既有取数, 产出数值序列), 其余维度复用 _exec_health_query 的紧凑原文。
        """
        from app.services import health_query_batch as hqb

        async def _fetch(dimension: str, days: int) -> hqb.BatchFetchResult:
            if dimension in hqb.SERIES_DIMENSIONS:
                series, unit, raw = hqb.build_wearable_series(
                    self.db, self._current_user_id, dimension, days
                )
                return hqb.BatchFetchResult(
                    series=series, unit=unit, raw=raw, aggregatable=True
                )
            # 非数值序列维度: 复用既有 health_query 数据面取紧凑原文, 不重写取数。
            raw = await self._exec_health_query(
                base, headers, {"dimension": dimension, "days": days}
            )
            return hqb.BatchFetchResult(series=[], raw=raw, aggregatable=False)

        return await hqb.execute_batch(args, _fetch)

    @staticmethod
    def _medication_item_from_health_record_args(
        args: Mapping[str, Any],
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Extract one observed intake proposal without trusting confirmation flags."""
        rtype = _normalize_fast_record_kind(
            args.get("record_type") or args.get("type") or ""
        )
        if rtype != "medication":
            return None, None
        raw_data = args.get("data", {})
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError, ValueError):
                raw_data = {}
        data = raw_data if isinstance(raw_data, dict) else {}
        med_name = str(
            data.get("medication_name")
            or data.get("name")
            or args.get("medication_name")
            or args.get("name")
            or ""
        ).strip()
        actual_dosage = str(
            data.get("actual_dosage")
            or args.get("actual_dosage")
            or data.get("dose")
            or args.get("dose")
            or ""
        ).strip()
        legacy_dosage = str(
            data.get("dosage") or args.get("dosage") or ""
        ).strip()
        if not actual_dosage and re.fullmatch(
            r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半])"
            r"(?:粒|片|袋|支|丸|颗|滴|喷|毫升|ml|单位|iu|u)",
            legacy_dosage,
            flags=re.IGNORECASE,
        ):
            actual_dosage = legacy_dosage
        if not med_name:
            return None, "需要提供药物名称（medication_name）"
        if not actual_dosage:
            return None, (
                "medication 记录必须提供本次实际服量 actual_dosage"
                "（例如 1粒/2片），不能从药品规格或处方默认值推断。"
            )
        observed_strength = str(
            data.get("observed_strength")
            or args.get("observed_strength")
            or data.get("strength")
            or args.get("strength")
            or (
                legacy_dosage
                if legacy_dosage and legacy_dosage != actual_dosage
                else ""
            )
        ).strip()
        return {
            "medication_name": med_name,
            "actual_dosage": actual_dosage,
            "observed_strength": observed_strength or None,
        }, None

    def _prepare_medication_tool_plan(
        self,
        tool_calls: Sequence[Mapping[str, Any]],
    ) -> None:
        """Seal all medication calls in one model response as one immutable plan.

        This happens before dispatching the first tool call, so neither the
        model loop nor a concurrent retry can expose a one-item preview and
        later mutate it into a different multi-item authorization.
        """
        items: list[dict[str, Any]] = []
        has_medication_call = False
        for tool_call in tool_calls:
            function = tool_call.get("function")
            if not isinstance(function, Mapping):
                continue
            if function.get("name") != "health_record":
                continue
            parsed_args = _parse_tool_arguments_for_telemetry(
                function.get("arguments")
            )
            item, error = self._medication_item_from_health_record_args(parsed_args)
            if item is None and error is None:
                continue
            has_medication_call = True
            if error is not None:
                self._turn_medication_tool_preflight_error = error
                return
            items.append(item)
        if not has_medication_call:
            return
        self._turn_medication_tool_preflight_error = None
        if getattr(self, "_read_only_turn", False):
            self._read_only_turn_write_attempted = True
            self._turn_medication_tool_preflight_error = (
                "只读预生成回合不建立用药确认计划"
            )
            return
        if getattr(self, "_multi_model_turn", False):
            self._turn_medication_tool_preflight_error = (
                "多模型分析回合不建立用药确认计划；请单独发送用药记录"
            )
            return
        if not items:
            self._turn_medication_tool_preflight_error = (
                "用药工具调用没有可确认的逐项服量"
            )
            return
        if not (
            self._current_user_id is not None
            and self._current_turn_conversation_id is not None
            and self._current_turn_source_message_id is not None
        ):
            self._turn_medication_tool_preflight_error = (
                "缺少服务端会话或来源消息，无法建立用药确认计划"
            )
            return
        try:
            from app.services.medication_intake_batch import (
                WRITE_INTENT_KIND,
                propose_medication_intake_items,
            )

            intent = propose_medication_intake_items(
                self.db,
                user_id=self._current_user_id,
                conversation_id=self._current_turn_conversation_id,
                source_message_id=self._current_turn_source_message_id,
                items=items,
                reference_now=self._agent_kernel_reference_now(),
                allow_merge_pending=False,
            )
            self._turn_medication_tool_intent_id = int(intent.id)
            self._turn_medication_tool_confirmation_card = (
                self._medication_batch_confirmation_card(
                    intent,
                    intent.payload or {},
                )
            )
            if intent.id not in self._turn_pending_write_intent_ids:
                self._turn_pending_write_intent_ids.append(intent.id)
            if WRITE_INTENT_KIND not in self._turn_pending_write_intent_kinds:
                self._turn_pending_write_intent_kinds.append(WRITE_INTENT_KIND)
        except Exception as error:  # noqa: BLE001 — no plan means no write
            logger.error(
                "[medication_batch] tool preflight failed "
                "user=%s source=%s error_type=%s",
                self._current_user_id,
                self._current_turn_source_message_id,
                type(error).__name__,
            )
            self.db.rollback()
            self._turn_medication_tool_preflight_error = (
                "服务端未能封存完整的用药确认计划"
            )


    def _contextual_diet_replay_result(
        self,
        *,
        requested_record_id: Any = None,
    ) -> str | None:
        """Return the verified receipt for a meal already saved in this turn.

        Contextual photo capture is the sole writer for its turn.  Models may
        still emit a redundant create/update call after seeing the structured
        vision summary, or may select an older record after listing history.
        Replaying the first write's receipt keeps the turn idempotent and
        prevents a stale record from being mutated.
        """
        contextual_record_id = self._turn_contextual_diet_record_id
        if contextual_record_id is None:
            return None

        from app.models.daily_health import DietRecord

        existing = (
            self.db.query(DietRecord)
            .filter(
                DietRecord.id == contextual_record_id,
                DietRecord.user_id == self._current_user_id,
            )
            .first()
        )
        if existing is None:
            return None

        requested = str(requested_record_id or "").strip()
        if requested and requested != str(existing.id):
            logger.warning(
                "[contextual_meal_photo] suppressed stale same-turn diet update "
                "user=%s contextual_record_id=%s requested_record_id=%s",
                self._current_user_id,
                existing.id,
                requested,
            )
        else:
            logger.info(
                "[contextual_meal_photo] replayed verified same-turn receipt "
                "user=%s record_id=%s",
                self._current_user_id,
                existing.id,
            )

        payload = {
            "id": existing.id,
            "record_id": existing.id,
            "resource_type": "diet_record",
            "record_date": existing.record_date.isoformat(),
            "operation_id": f"contextual_meal_photo:{existing.id}",
            "status": "recorded",
            "replayed": True,
        }
        if self._turn_contextual_diet_consumed_fraction is not None:
            payload["portion_adjustment_applied"] = True
        return json.dumps(payload, ensure_ascii=False)

    async def _exec_user_directive(self, args: dict) -> str:
        """Persist a prevalidated user constraint with a verifiable receipt."""
        text = str(args.get("text") or "").strip()
        source = str(args.get("source") or "user_self").strip()[:40]
        source_message_id = str(args.get("source_message_id") or "").strip() or None
        if len(text) < 4:
            return json.dumps(
                {
                    "status": "rejected",
                    "success": False,
                    "dispatch_started": False,
                    "error_code": "directive_text_too_short",
                },
                ensure_ascii=False,
            )
        from app.services.directive_parser import parse_and_store_async

        ids = await parse_and_store_async(
            self.db,
            int(self._current_user_id),
            text,
            source=source,
            source_message_id=source_message_id,
        )
        if not ids:
            return json.dumps(
                {
                    "status": "rejected",
                    "success": False,
                    "dispatch_started": False,
                    "error_code": "directive_not_recognized",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "verified",
                "success": True,
                "resource_type": "user_directive",
                "resource_id": str(ids[0]),
                "resource_ids": [str(item) for item in ids],
                "count": len(ids),
            },
            ensure_ascii=False,
        )

    async def _exec_health_record(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康数据记录"""
        model_claimed_confirmation = bool(
            args.get("confirmed") is True
            or args.get("confirm") is True
            or (
                isinstance(args.get("data"), dict)
                and (
                    args["data"].get("confirmed") is True
                    or args["data"].get("confirm") is True
                )
            )
        )
        trusted_server_authorized = bool(
            args.pop("_trusted_server_write_authorized", False)
        )
        _strip_untrusted_write_authorization(args)
        snapshot = self._agent_kernel_snapshot
        current_turn_authorized = bool(
            snapshot is not None
            and snapshot.context.user_id == self._current_user_id
            and snapshot.intent.primary == "write"
            and snapshot.intent.operation == "create"
            and snapshot.intent.is_write
            and args.get("_fast_record_requires_confirmation") is not True
        )
        write_authorized = trusted_server_authorized or current_turn_authorized

        # 别名容错:模型常把 record_type 写成 type(实测 health_record(type=diet, data={...}))。
        rtype = _normalize_fast_record_kind(args.get("record_type") or args.get("type") or "")
        data = args.get("data", {})
        # data 偶尔被吐成 JSON 字符串(coerce 退化)→ 尽力解析回 dict。
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                data = {}
        today = self._agent_kernel_reference_now().strftime("%Y-%m-%d")
        if rtype == "diet":
            data = _normalize_diet_create_data(
                args,
                default_record_date=today,
            )

        # A contextual meal photo may already have been persisted before the
        # model receives its structured vision summary.  A model retry must
        # receive the same verified record, never create a second meal.
        if rtype == "diet" and self._turn_contextual_diet_record_id is not None:
            replay = self._contextual_diet_replay_result()
            if replay is not None:
                return replay
            return "Error: 本轮图片记录未取得可验证回执，未创建新的饮食记录。"

        # Mobile 相机入口是用户已经明确点击“拍照记餐”发起的动作，不再创建
        # 二次确认草稿。仍剥掉仅供 Agent 内部使用的确认标记，避免把控制字段
        # 透传给 DietRecord API；真实是否保存由下方 API 回执决定。
        if rtype == "diet" and self._diet_photo_auto_save:
            args.pop("confirmed", None)
            args.pop("confirm", None)
            data.pop("confirmed", None)
            data.pop("confirm", None)

        # R4 authorization boundary: a model-generated boolean is not evidence
        # of user consent.  Medication confirmation is now a source-bound
        # server WriteIntent consumed by the deterministic pre-LLM turn above;
        # this legacy tool path can only propose/describe, never authorize.
        if rtype == "medication" and model_claimed_confirmation:
            logger.warning(
                "[R4-block] ignored model-controlled confirmation kind=%s "
                "prefer_fast=%s user=%s message_chars=%s",
                rtype,
                self._prefer_fast_record_model,
                self._current_user_id,
                len(getattr(self, "_current_turn_user_message", "") or ""),
            )
        if rtype == "medication":
            args.pop("confirmed", None)
            args.pop("confirm", None)
            data.pop("confirmed", None)
            data.pop("confirm", None)

            medication_item, medication_error = (
                self._medication_item_from_health_record_args(args)
            )
            if medication_error is not None or medication_item is None:
                return json.dumps(
                    {
                        "status": "rejected",
                        "success": False,
                        "dispatch_started": False,
                        "error_code": "medication_arguments_invalid",
                        "message": medication_error or "用药参数无效",
                    },
                    ensure_ascii=False,
                )
            med_name = medication_item["medication_name"]
            actual_dosage = medication_item["actual_dosage"]
            observed_strength = medication_item.get("observed_strength")

            preflight_error = getattr(
                self,
                "_turn_medication_tool_preflight_error",
                None,
            )
            if preflight_error:
                return json.dumps(
                    {
                        "status": "rejected",
                        "success": False,
                        "dispatch_started": False,
                        "error_code": "medication_plan_preflight_failed",
                        "message": (
                            "用药确认计划未能建立，本次没有写入。"
                            f"{preflight_error}；"
                            "请重新发送完整药名和本次实际服量。"
                        ),
                    },
                    ensure_ascii=False,
                )

            intent = None
            if not (
                self._current_user_id is not None
                and self._current_turn_conversation_id is not None
                and self._current_turn_source_message_id is not None
            ):
                return json.dumps(
                    {
                        "status": "rejected",
                        "success": False,
                        "dispatch_started": False,
                        "error_code": "medication_plan_context_missing",
                        "message": (
                            "用药确认计划未能建立，本次没有写入。"
                            "请在聊天中重新发送药名和本次实际服量。"
                        ),
                    },
                    ensure_ascii=False,
                )
            try:
                from app.services.medication_intake_batch import (
                    WRITE_INTENT_KIND,
                    propose_medication_intake_items,
                )

                # When the model returned several medication calls, preflight
                # already froze all of them in one immutable plan.  Re-entering
                # with this single item only verifies that it is a subset of
                # that plan; it cannot mutate the published authorization.
                intent = propose_medication_intake_items(
                    self.db,
                    user_id=self._current_user_id,
                    conversation_id=self._current_turn_conversation_id,
                    source_message_id=self._current_turn_source_message_id,
                    items=[{
                        "medication_name": med_name,
                        "actual_dosage": actual_dosage,
                        "observed_strength": observed_strength,
                    }],
                    reference_now=self._agent_kernel_reference_now(),
                    allow_merge_pending=False,
                )
                preflight_intent_id = getattr(
                    self,
                    "_turn_medication_tool_intent_id",
                    None,
                )
                if (
                    preflight_intent_id is not None
                    and int(intent.id) != int(preflight_intent_id)
                ):
                    raise RuntimeError("medication tool preflight intent mismatch")
                if intent.id not in self._turn_pending_write_intent_ids:
                    self._turn_pending_write_intent_ids.append(intent.id)
                if WRITE_INTENT_KIND not in self._turn_pending_write_intent_kinds:
                    self._turn_pending_write_intent_kinds.append(WRITE_INTENT_KIND)
            except Exception as error:  # noqa: BLE001 — no plan means no write
                logger.error(
                    "[medication_batch] tool proposal failed "
                    "user=%s source=%s error_type=%s",
                    self._current_user_id,
                    self._current_turn_source_message_id,
                    type(error).__name__,
                )
                self.db.rollback()
                return json.dumps(
                    {
                        "status": "rejected",
                        "success": False,
                        "dispatch_started": False,
                        "error_code": "medication_plan_proposal_failed",
                        "message": (
                            "用药确认计划未能建立，本次没有写入。"
                            "请重新发送药名和本次实际服量。"
                        ),
                    },
                    ensure_ascii=False,
                )
            preview = (
                f"用药: {med_name} {observed_strength}，本次服量 {actual_dosage}"
                if observed_strength
                else f"用药: {med_name}，本次服量 {actual_dosage}"
            )
            intent_note = f"（确认计划 {intent.id}）" if intent is not None else ""
            return (
                f"[NEEDS_CONFIRMATION] 我准备记录: {preview}{intent_note}. "
                "请向用户复述；只有服务端待确认计划被用户明确确认后才会写入。"
            )

        # medication 是医疗级写入:无论快/慢路径恒确认前置。快路径由 gate 置 flag;
        # 真正跨轮授权只由上面的 server-owned WriteIntent 路径消费；这里即使模型
        # 重放 confirmed=true 也已被剥离，因此只能返回 NEEDS_CONFIRMATION。
        if args.pop("_fast_record_requires_confirmation", False) or rtype == "medication":
            check = _confirm_or_describe(
                args,
                data,
                preview=_health_record_confirmation_preview(rtype, args, data),
                authorized=write_authorized,
            )
            if check:
                return check

        # water: 必须显式提供 amount, 不再悄悄默认 250ml.
        # 之前 LLM 在回答健康问题时偶发误调 health_record(water) 不带 amount,
        # 静默默认 250 → 用户看到莫名打卡. 现在: 没传 amount 直接 Error;
        # 传了也走 confirm gate, 跟 weight/blood_pressure 一致.
        if rtype == "water":
            amount = data.get("amount") or args.get("amount")
            if amount is None:
                return local_write_rejection(
                    "water_amount_missing",
                    message="饮水记录缺少毫升数。",
                    recovery_guidance="请先确认喝了多少 ml，再重新记录。",
                )
            try:
                amount_int = int(amount)
            except (ValueError, TypeError):
                return local_write_rejection(
                    "water_amount_invalid",
                    message="饮水量必须是整数毫升。",
                    recovery_guidance="请提供 1 到 5000 之间的整数毫升数。",
                )
            if amount_int <= 0 or amount_int > 5000:
                return local_write_rejection(
                    "water_amount_out_of_range",
                    message="饮水量超出可记录范围。",
                    recovery_guidance="请提供 1 到 5000 之间的整数毫升数。",
                )
            data["amount"] = amount_int
            check = _confirm_or_describe(
                args, data,
                preview=f"喝水 {amount_int}ml" + (f", {data['drink_type']}" if data.get("drink_type") else ""),
                authorized=write_authorized,
            )
            if check:
                return check
            from app.services.water_service import create_water_intake

            recorded_at = self._agent_kernel_reference_now()
            raw_record_date = str(data.get("record_date") or "").strip()
            if raw_record_date:
                try:
                    target_record_date = date.fromisoformat(raw_record_date)
                except ValueError:
                    return local_write_rejection(
                        "water_record_date_invalid",
                        message="饮水记录日期无效。",
                        recovery_guidance="请使用 YYYY-MM-DD 或今天、昨天等明确日期。",
                    )
                recorded_at = recorded_at.replace(
                    year=target_record_date.year,
                    month=target_record_date.month,
                    day=target_record_date.day,
                )
            record = create_water_intake(
                self.db,
                user_id=self._current_user_id,
                amount_ml=amount_int,
                drink_type=data.get("drink_type") or "水",
                recorded_at=recorded_at,
            )
            return json.dumps(
                {
                    "id": record.id,
                    "record_id": record.id,
                    "resource_type": "water_record",
                    "record_date": record.record_date.isoformat(),
                    "status": "verified",
                    "success": True,
                    "message": f"已记录饮水 {amount_int}ml",
                    "undo_path": f"water/records/{record.id}",
                    "created_at": (
                        record.created_at.isoformat()
                        if record.created_at is not None
                        else self._agent_kernel_reference_now().isoformat()
                    ),
                },
                ensure_ascii=False,
            )

        # 补全 diet 必填字段
        if rtype == "diet":
            if not data.get("food_items"):
                return local_write_rejection(
                    "diet_food_items_missing",
                    message="饮食记录缺少食物内容。",
                    recovery_guidance="请补充本餐吃了什么后重新记录。",
                )

        # 补全 weight 必填字段
        if rtype == "weight":
            data.setdefault("record_date", today)
            # LLM 常把 weight 直接放在顶层 args 而不是 args.data (参数 schema 歧义)
            # 兜底: 顶层有就挪到 data
            for src in ("weight", "value", "weight_kg", "体重"):
                if src in args and "weight" not in data:
                    data["weight"] = args[src]
                    break
            if "weight" not in data and "value" in data:
                data["weight"] = data.pop("value")
            if "weight" not in data and "weight_kg" in data:
                data["weight"] = data.pop("weight_kg")
            if "weight" not in data:
                return local_write_rejection(
                    "weight_value_missing",
                    message="体重记录缺少 kg 数值。",
                    recovery_guidance="请补充体重数值后重新记录。",
                )

            # L8 (Karpathy "verification is the bottleneck"): 高确定性数值, 写错没法静默修正
            check = _confirm_or_describe(
                args, data,
                preview=f"体重 {data['weight']} kg, 日期 {data.get('record_date', today)}",
                authorized=write_authorized,
            )
            if check:
                return check

        # 补全 blood_pressure 必填字段
        if rtype == "blood_pressure":
            data.setdefault("record_date", today)
            sys_v = data.get("systolic")
            dia_v = data.get("diastolic")
            # 顶层 args 兜底 (LLM 偶尔放错位置)
            if sys_v is None and args.get("systolic") is not None:
                data["systolic"] = sys_v = args["systolic"]
            if dia_v is None and args.get("diastolic") is not None:
                data["diastolic"] = dia_v = args["diastolic"]
            if sys_v is None or dia_v is None:
                return local_write_rejection(
                    "blood_pressure_values_missing",
                    message="血压记录需要同时提供收缩压和舒张压。",
                    recovery_guidance="请补充完整的血压读数后重新记录。",
                )
            # L8: 血压数值高/低风险大, 必须先确认
            check = _confirm_or_describe(
                args, data,
                preview=f"血压 {sys_v}/{dia_v}, 日期 {data.get('record_date', today)}",
                authorized=write_authorized,
            )
            if check:
                return check

        # illness 急性症状记录 — 影响疾病追踪, 必须先确认
        if rtype == "illness":
            data.setdefault("start_date", today)
            name = data.get("name") or data.get("illness_name") or args.get("name") or args.get("illness_name")
            if not name:
                return local_write_rejection(
                    "illness_name_missing",
                    message="疾病记录缺少名称。",
                    recovery_guidance="请说明要记录的疾病或不适名称。",
                )
            data["name"] = name
            sev = data.get("severity") or args.get("severity")
            if sev is not None:
                data["severity"] = sev
            preview_bits = [f"生病: {name}"]
            if sev is not None:
                preview_bits.append(f"严重度 {sev}")
            preview_bits.append(f"开始 {data.get('start_date')}")
            check = _confirm_or_describe(
                args,
                data,
                preview=", ".join(preview_bits),
                authorized=write_authorized,
            )
            if check:
                return check

        # 补全 exercise 必填字段 + LLM 常见字段别名映射
        if rtype == "exercise":
            data.setdefault("record_date", today)
            # LLM 可能用 count/次数/repetitions 代替 reps
            for src in ("count", "repetitions", "次数"):
                if src in data and "reps" not in data:
                    data["reps"] = data.pop(src)
            # LLM 可能用 duration_minutes / minutes 代替 duration
            for src in ("duration_minutes", "minutes", "分钟"):
                if src in data and "duration" not in data:
                    data["duration"] = data.pop(src)
            # exercise_type 必填, 若缺失从 type / name 回退
            if not data.get("exercise_type"):
                data["exercise_type"] = data.get("type") or data.get("name") or "其他"

        # waist: 手动腰围记录。代谢闭环里腰围是关键指标,不能只靠 UI 手填。
        if rtype == "waist":
            data.setdefault("record_date", today)
            for src in ("waist_cm", "waist", "value", "腰围"):
                if src in args and "waist_cm" not in data:
                    data["waist_cm"] = args[src]
                    break
                if src in data and src != "waist_cm" and "waist_cm" not in data:
                    data["waist_cm"] = data.pop(src)
                    break
            if "waist_cm" not in data:
                return local_write_rejection(
                    "waist_value_missing",
                    message="腰围记录缺少厘米数。",
                    recovery_guidance="请补充腰围厘米数后重新记录。",
                )

        # sleep: 手动睡眠补录。不要代猜入睡/醒来时间;缺字段 fail-loud 让模型追问。
        if rtype == "sleep":
            data.setdefault("record_date", today)
            if "quality" in data and "sleep_quality" not in data:
                data["sleep_quality"] = data.pop("quality")
            missing = [
                field for field in ("bedtime", "wake_time", "sleep_quality")
                if data.get(field) in (None, "")
            ]
            if missing:
                if _looks_like_sleep_start_event(
                    getattr(self, "_current_turn_user_message", ""),
                    data,
                ):
                    title = str(
                        data.get("title")
                        or data.get("name")
                        or data.get("event")
                        or "准备开始睡觉"
                    ).strip()
                    payload: Dict[str, Any] = {"title": title[:80] or "准备开始睡觉"}
                    occurred_at = (
                        data.get("occurred_at")
                        or data.get("bedtime")
                        or data.get("time")
                    )
                    if occurred_at not in (None, ""):
                        payload["occurred_at"] = str(occurred_at)[:64]
                    notes = data.get("notes") or data.get("description")
                    if notes not in (None, ""):
                        payload["notes"] = str(notes)[:500]
                    result = await self._api_post(
                        f"{base}/episodes/life-event", headers, payload
                    )
                    return _result_with_resource_type(result, "health_episode")
                return local_write_rejection(
                    "sleep_fields_missing",
                    message=f"睡眠记录缺少字段：{', '.join(missing)}。",
                    recovery_guidance=(
                        "请补充入睡时间、醒来时间和 1 到 5 分的睡眠质量。"
                    ),
                )

        # excretion: 排便/排尿记录。type 是下游统计的关键,缺失时明确追问。
        if rtype == "excretion":
            data.setdefault("record_date", today)
            type_map = {
                "大便": "bowel", "排便": "bowel", "便便": "bowel", "stool": "bowel",
                "小便": "urine", "排尿": "urine", "尿": "urine", "pee": "urine",
            }
            raw_type = data.get("type") or data.get("excretion_type") or args.get("type")
            if raw_type in type_map:
                raw_type = type_map[raw_type]
            if raw_type not in ("bowel", "urine"):
                return local_write_rejection(
                    "excretion_type_missing",
                    message="排泄记录未说明是排便还是排尿。",
                    recovery_guidance="请先确认记录类型后重试。",
                )
            data["type"] = raw_type

        if rtype == "reminder":
            data = _enrich_reminder_window_from_turn(
                data,
                user_message=getattr(self, "_current_turn_user_message", ""),
                recent_messages=getattr(self, "_current_turn_recent_messages", []),
                reference_now=self._agent_kernel_reference_now(),
            )
            data = _normalize_reminder_record_data(
                data,
                reference_now=self._agent_kernel_reference_now(),
            )
            has_window_field = any(
                data.get(key) not in (None, "")
                for key in ("start_time", "end_time", "interval_minutes")
            )
            if has_window_field and not all(
                data.get(key) not in (None, "")
                for key in ("start_time", "end_time", "interval_minutes")
            ):
                return local_write_rejection(
                    "reminder_window_incomplete",
                    message="时间窗提醒缺少开始、结束或间隔设置。",
                    recovery_guidance="请补充完整时段与提醒间隔后重试。",
                )
            args["data"] = data

        if rtype == "goal":
            data.setdefault("start_date", today)
            title = data.get("title") or data.get("name") or args.get("title")
            if not title:
                return local_write_rejection(
                    "goal_title_missing",
                    message="目标记录缺少标题。",
                    recovery_guidance="请说明要建立的目标后重新记录。",
                )
            data["title"] = str(title).strip()

            if "target" in data and "target_value" not in data:
                data["target_value"] = data.pop("target")
            if "unit" in data and "target_unit" not in data:
                data["target_unit"] = data.pop("unit")
            if "period" in data and "goal_period" not in data:
                data["goal_period"] = data.pop("period")
            if "type" in data and "goal_type" not in data:
                data["goal_type"] = data.pop("type")
            if isinstance(data.get("implementation_steps"), list):
                data["implementation_steps"] = "\n".join(
                    f"{idx + 1}. {step}" for idx, step in enumerate(data["implementation_steps"])
                )

            goal_type_map = {
                "饮食": "diet",
                "吃饭": "diet",
                "运动": "exercise",
                "锻炼": "exercise",
                "睡眠": "sleep",
                "喝水": "water",
                "饮水": "water",
                "补剂": "supplement",
                "户外": "outdoor",
                "体重": "weight",
                "腰围": "weight",
                "其他": "other",
            }
            goal_period_map = {
                "每天": "daily",
                "每日": "daily",
                "日": "daily",
                "每周": "weekly",
                "周": "weekly",
                "每月": "monthly",
                "月": "monthly",
                "每年": "yearly",
                "年": "yearly",
            }
            allowed_goal_types = {"diet", "exercise", "sleep", "water", "supplement", "outdoor", "weight", "other"}
            allowed_goal_periods = {"daily", "weekly", "monthly", "yearly"}
            raw_goal_type = str(data.get("goal_type") or "other").strip()
            raw_goal_period = str(data.get("goal_period") or "daily").strip()
            data["goal_type"] = goal_type_map.get(raw_goal_type, raw_goal_type).lower()
            data["goal_period"] = goal_period_map.get(raw_goal_period, raw_goal_period).lower()
            if data["goal_type"] not in allowed_goal_types:
                data["goal_type"] = "other"
            if data["goal_period"] not in allowed_goal_periods:
                data["goal_period"] = "daily"
            data.setdefault("status", "active")
            data.setdefault("priority", 5)

        # rhinitis: 鼻炎每日打卡 → upsert 当天 HealthCheckin(单条/日滚动),不再每次
        # mint 一条 illness_episode "鼻炎发作"。旧设计每次打卡建新 episode → 无界堆积
        # active(实测 36 条卡死),且 RhinitisSpecialist / rhinitis_trend 读的是
        # HealthCheckin(rhinitis_today),根本收不到 chat 打卡 —— 打卡既堆噪声又喂不到分析。
        # HealthCheckin 按 checkin_date upsert(sneeze_times 按 time 合并,不覆盖当日其它
        # 打卡字段;只在 value 非 None 时 setattr),是鼻炎打卡的规范单日存储。
        if rtype == "rhinitis":
            sneezing = int(data.get("sneezing", 0) or 0)
            congestion = int(data.get("congestion", 0) or 0)
            runny_nose = int(data.get("runny_nose", 0) or 0)
            parts = []
            if sneezing:
                parts.append(f"喷嚏 {sneezing} 次")
            if congestion:
                parts.append(f"鼻塞 {congestion}/3")     # 0-3 级(schema/validator 统一), 非 0-10
            if runny_nose:
                parts.append(f"流涕 {runny_nose}/3")      # 0-3 级, 非计数('次'会被读成流涕次数)
            # 详情走 sneeze_times(合并追加,保留 congestion/runny_nose),不动 notes(避免
            # 覆盖当日其它打卡备注)。sneeze_count 取本次报的今日累计次数(端点 setattr 覆盖)。
            entry: Dict[str, Any] = {
                "time": self._agent_kernel_reference_now().strftime("%H:%M"),
                "count": sneezing,
                "summary": "、".join(parts) or (data.get("notes") or "鼻炎打卡"),
            }
            if congestion:
                entry["congestion"] = congestion
            if runny_nose:
                entry["runny_nose"] = runny_nose
            # sneeze_count 不在此设 —— 端点从合并后的 sneeze_times 单调派生(单一真源,
            # 防"增量口语"经 last-writer-wins 把当天累计写小)。entry.count = 本次新增次数。
            payload: Dict[str, Any] = {
                "checkin_date": data.get("record_date") or today,
                "sneeze_times": [entry],
            }
            return await self._api_post(f"{base}/checkin/", headers, payload)

        # remember: 无结构化类型的个人属性/事实(鞋码/衣码/喜好/习惯/生日昵称等)→ 写
        # MemoryFact 三元组(可召回)。补齐"档案属性"缺口 —— 此前小巴会主动说"补充进档案"
        # 却无工具可写, 用户给了值也 0 工具调用 → 落进饮食味的兜底话术(founder 2026-07-17
        # 实测:鞋码 42.5 记不下来还被要求补早餐)。subject 默认"用户", tier=semantic(稳定属性)。
        if rtype == "remember":
            predicate = (
                data.get("predicate") or data.get("attribute")
                or data.get("key") or data.get("name")
            )
            object_value = data.get("object_value")
            if object_value is None:
                object_value = data.get("value")
            if not predicate or object_value in (None, ""):
                return local_write_rejection(
                    "memory_attribute_missing",
                    message="个人档案记录需要属性名和值。",
                    recovery_guidance="请补充要记住的属性及其具体值。",
                )
            # 硬闸:结构化医疗/化验/基因/用药数据绝不走 memory_fact(会绕过 Safety Guardian +
            # 加密/RLS)。命中 → fail-loud redirect 到对应结构化记录(服务端硬闸,非软指引)。
            _redirect = _remember_structured_medical_redirect(
                predicate, object_value, data.get("object_unit") or data.get("unit"))
            if _redirect:
                return _redirect
            payload = {
                "tier": "semantic",
                "subject": (data.get("subject") or "用户"),
                "predicate": str(predicate),
                "object_value": str(object_value),
                "object_unit": (data.get("object_unit") or data.get("unit") or None),
                "confidence": 0.9,  # 用户明说 → 高置信
                "is_sensitive": bool(data.get("is_sensitive", False)),
            }
            return await self._api_post(f"{base}/memory-facts", headers, payload)

        # supplement_group: 按时段批量打卡
        if rtype == "supplement_group":
            timing = data.get("timing", "morning")
            result = await self._api_post(
                f"{base}/nfc/tap", headers,
                {"action": "supplement_group", "timing": timing}
            )
            logger.info(f"[health_record] supplement_group timing={timing}")
            return result

        # supplement: 按名称匹配补剂打卡
        if rtype == "supplement":
            name = data.get("supplement_name", data.get("name", ""))
            if name:
                # 查找匹配的补剂定义 (走 _api_get_json: 拿干净可解析数据, 不被字符截断)
                supps, err = await self._api_get_json(f"{base}/supplements/me/definitions", headers)
                if err:
                    logger.warning(f"[health_record] supplement lookup 失败: {err}")
                    return f"补剂记录暂时没成功(查询补剂列表时{err}),你可以稍后再试一次。"
                supps = supps if isinstance(supps, list) else (supps.get("data", []) if isinstance(supps, dict) else [])
                matched = next((s for s in supps if s.get("is_active") and name.lower() in s.get("name", "").lower()), None)
                if matched:
                    return await self._api_post(
                        f"{base}/nfc/tap", headers,
                        {"action": "supplement", "supplement_id": matched["id"]}
                    )
                # 没匹配到活跃补剂 → 自动建档再打卡(镜像 medication 先例,见下方 :4646)。
                # 旧行为报"未找到"把用户推去手动页面 —— 拍照/口述识别出的新补剂
                # (实测:正官庄红参液)记录直接失败。建档可逆(补剂管理页可停用/删),
                # 且新条目进入 DSI 安全规则覆盖面(加层不减层,只增覆盖)。
                create_payload = {"name": name}
                for k in ("dosage", "timing", "category", "description"):
                    if data.get(k):
                        create_payload[k] = data[k]
                created, cerr = await self._api_post_json(
                    f"{base}/supplements/definitions", headers, create_payload
                )
                if cerr or not isinstance(created, dict) or not created.get("id"):
                    logger.warning(f"[health_record] supplement 自动建档失败: {cerr}")
                    return f"补剂记录暂时没成功(自动建档 '{name}' 时{cerr or '未知错误'}),你可以稍后再试一次。"
                tap_result = await self._api_post(
                    f"{base}/nfc/tap", headers,
                    {"action": "supplement", "supplement_id": created["id"]}
                )
                if tap_result.startswith("Error"):
                    return f"已把「{name}」加入补剂库(补剂号 {created['id']}),但今日打卡没成功({tap_result})。"
                # 2026-07-12 生产实锤:此处曾只回 {"message": ...} 无任何 id → 回执身份
                # 提取不到 → 整轮被诚实门判「不可确认」(四笔全成功仍报无回执,还诱导重试)。
                # 回执必须带可验证身份:透传 tap 的 record_id + resource_type。
                tap_record_id = None
                try:
                    tap_record_id = (json.loads(tap_result) or {}).get("record_id")
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning(
                        "[health_record] supplement tap 响应不可解析 chars=%s",
                        len(tap_result),
                    )
                return json.dumps(
                    {
                        "message": f"已把「{name}」加入补剂库并完成今日打卡（补剂号 {created['id']}，说「撤销」可移除）",
                        "id": tap_record_id,
                        "record_id": tap_record_id,
                        "resource_type": "supplement_log",
                        "supplement_definition_id": created["id"],
                        "status": "recorded",
                    },
                    ensure_ascii=False,
                )
            return local_write_rejection(
                "supplement_name_missing",
                message="补剂记录缺少补剂名称。",
                recovery_guidance="请补充补剂名称后重新记录。",
            )

        # medication: 用药记录
        if rtype == "medication":
            med_name = data.get("medication_name", data.get("name", ""))
            if not med_name:
                return local_write_rejection(
                    "medication_name_missing",
                    message="用药记录缺少药物名称。",
                    recovery_guidance="请补充药物名称和本次实际服量。",
                )
            # 查找 medication_id (走 _api_get_json: 拿干净可解析数据, 不被字符截断)
            meds, err = await self._api_get_json(f"{base}/medication/medications/me", headers)
            if err:
                logger.warning(f"[health_record] medication lookup 失败: {err}")
                return f"用药记录暂时没成功(查询药物列表时{err}),你可以稍后再试一次。"
            meds = meds if isinstance(meds, list) else (meds.get("data", []) if isinstance(meds, dict) else [])
            matched = next((m for m in meds if m.get("is_active") and med_name.lower() in m.get("name", "").lower()), None)
            # 没匹配到活跃药物 → 自动登记 (短程/临时用药如抗生素, 用户不会预先建档), 再记录服用。
            # 旧行为是直接报"未找到活跃药物"并放弃, 导致"吃了两粒阿奇霉素"这类记录失败。
            if not matched:
                create_payload = {"name": med_name}
                for k in ("dosage", "frequency", "category", "purpose"):
                    if data.get(k):
                        create_payload[k] = data[k]
                created, cerr = await self._api_post_json(f"{base}/medication/medications", headers, create_payload)
                if cerr or not isinstance(created, dict) or not created.get("id"):
                    logger.warning(f"[health_record] medication 自动登记失败: {cerr}")
                    return f"用药记录暂时没成功(自动登记 '{med_name}' 时{cerr or '未知错误'}),你可以稍后再试一次。"
                matched = created
            # 归一到列语义 "HH:MM"(2026-07-12 生产实锤:此处默认值曾是带微秒+时区的
            # 完整 ISO → 溢出 varchar → 500 → 无写回执,确认流看似失灵)。
            # 解析不了的脏输入回退"现在",fail-soft 但记 warning(写入本身不该因时刻串死)。
            from app.services.medication_service import normalize_taken_time
            try:
                taken_time = normalize_taken_time(data.get("taken_time"))
            except ValueError:
                logger.warning("[health_record] taken_time 无法解析,回退当前时刻: %r", data.get("taken_time"))
                taken_time = None
            if not taken_time:
                taken_time = self._agent_kernel_reference_now().strftime("%H:%M")
            return await self._api_post(
                f"{base}/medication/logs", headers,
                {"medication_id": matched["id"], "taken_time": taken_time, "status": "taken"}
            )

        if rtype == "event":
            # 生活事件 → HealthEpisode 情景账本(2026-07-12):行程/落地/送达等
            # 带发生时间落库,时间线总结读结构化 occurred_at 而不是猜。
            # occurred_at 传用户原话("下午"/"刚才"/"21:07"),折算在后端确定性代码。
            # life_event 是别名(_FAST_RECORD_KIND_ALIASES),canonical 名只有 event。
            title = str(data.get("title") or data.get("name") or data.get("event") or "").strip()
            if not title:
                return local_write_rejection(
                    "event_title_missing",
                    message="事件记录缺少标题。",
                    recovery_guidance="请说明发生了什么事件后重新记录。",
                )
            payload = {"title": title[:80]}
            if data.get("occurred_at"):
                payload["occurred_at"] = str(data["occurred_at"])[:64]
            if data.get("notes"):
                payload["notes"] = str(data["notes"])[:500]
            result = await self._api_post(f"{base}/episodes/life-event", headers, payload)
            return _result_with_resource_type(result, "health_episode")

        if rtype == "illness":
            payload = dict(data)
            if "name" not in payload and payload.get("illness_name"):
                payload["name"] = payload.pop("illness_name")
            payload.setdefault("start_date", self._agent_kernel_reference_now().date().isoformat())
            payload.setdefault("status", "active")
            if not payload.get("name"):
                return local_write_rejection(
                    "illness_name_missing",
                    message="疾病记录缺少名称。",
                    recovery_guidance="请说明要记录的疾病或不适名称。",
                )
            return await self._api_post(f"{base}/illness/episodes", headers, payload)

        # garmin_sync 不是写记录,是一个长跑的 ingest **job**。绝不走内联阻塞路径
        # (旧实现:record_map 里同步 POST /data-collection/garmin/me/sync → 端点
        # 里同步 def 拉 Garmin,10–90s 冻死 event loop、全程无进度 → 手机永久转圈)。
        # 新执行模型:本地 precondition fail-loud → Celery enqueue → 乐观 ack 立即返回。
        if rtype == "garmin_sync":
            # HealthKit(Apple 健康)不是 Garmin,后端拉不了 —— 弱模型把两者都塌缩成
            # garmin_sync。命中 Apple 健康意图 → 返回真话指引(打开 App 前台上传),
            # 绝不入队 Garmin 同步、绝不谎称"后台正在拉取 Apple Health"。
            if _is_healthkit_sync_intent(getattr(self, "_current_turn_user_message", "")):
                # 条件化措辞(safety 评审):前台同步对未授权/未连接用户会静默 skip,
                # 所以不能无条件承诺"会上传"。已连接→打开 App 自动传;未连接→先去连接。
                return (
                    "Apple 健康(HealthKit)的数据是由你 iPhone 上的 App 在前台读取后上传的,"
                    "后端没法主动去拉取。如果你已经在设置里连接了 Apple 健康,打开 App 在前台"
                    "停留几秒,它会自动把最新数据上传上来;如果还没连接,先到「设置 → 设备」"
                    "连接 Apple 健康。传好之后我就能用这些数据帮你查看和分析了。"
                )
            return await self._trigger_garmin_sync()

        record_map = {
            "weight": ("/weight/records", "POST", data),
            "blood_pressure": ("/blood-pressure/records", "POST", data),
            "exercise": ("/daily-health/exercise", "POST", data),
            "diet": ("/diet/records", "POST", data),
            "supplement": ("/supplements/records", "POST", data),
            "waist": ("/waist/records", "POST", data),
            "sleep": ("/sleep/records", "POST", data),
            "excretion": ("/excretion/records", "POST", data),
            # rhinitis 走 special case (见上方 rtype=="rhinitis" 分支), 不在 record_map 里
            "mood": ("/mood/records", "POST", data),
            "reminder": (
                "/reminders/me/window"
                if all(data.get(key) not in (None, "") for key in (
                    "start_time", "end_time", "interval_minutes",
                ))
                else "/reminders/me",
                "POST",
                data,
            ),
            "goal": ("/goals/", "POST", data),
        }

        # symptom: 通用身体症状 (眼痒/嗓子疼 ...). 不再需要 profile_id (新 /symptoms 表,
        # 2026-05-08 改, 替换旧 disease_tracking.SymptomLog 路径 — 那路径强行要 profile_id,
        # 用户体验差, 已废弃. 鼻炎打卡走 record_type="rhinitis".
        if rtype == "symptom":
            body_part = data.get("body_part")
            description = data.get("description")
            if not body_part:
                return local_write_rejection(
                    "symptom_body_part_missing",
                    message="症状记录缺少身体部位。",
                    recovery_guidance="请说明症状发生在哪个部位。",
                )
            if not description:
                return local_write_rejection(
                    "symptom_description_missing",
                    message="症状记录缺少具体描述。",
                    recovery_guidance="请描述具体的不适后重新记录。",
                )
            # provenance 按真实通道打标(SymptomCreate 只收 manual|voice|siri):
            # typed 聊天=manual;siri=siri;其余(语音/未声明)=voice。此前硬编码
            # voice 把打字记录也标成语音,污染任何依赖 source 的下游区分。
            payload = dict(data)
            channel = getattr(self, "_turn_channel", None)
            default_source = "manual" if channel == "typed" else ("siri" if channel == "siri" else "voice")
            if payload.get("source") not in ("manual", "voice", "siri"):
                payload["source"] = default_source
            return await self._api_post(f"{base}/symptoms", headers, payload)

        if rtype in record_map:
            path, method, payload = record_map[rtype]
            if method == "POST":
                result = await self._api_post(f"{base}{path}", headers, payload)
                logger.info(
                    "[health_record] type=%s result_chars=%s",
                    rtype,
                    len(str(result or "")),
                )
                return result
        return local_write_rejection(
            "record_type_unsupported",
            message="当前记录类型不受支持。",
            recovery_guidance="请改用受支持的健康记录类型。",
        )

    async def _trigger_garmin_sync(self) -> str:
        """触发 Garmin 数据同步 —— 异步 job 模型(不阻塞对话回合)。

        founder 2026-07-14 裁决:同步是幂等读拉、无用户可见突变,agent 可 auto 执行
        (不违反 R4),但必须三护栏:① 未绑定/MFA/禁用 → 本地 precondition fail-loud
        明确指引(绝不空转/谎报);② 不内联阻塞(Celery enqueue,回合立即返回);
        ③ MFA 降级为指引、不自动重试。

        precondition 全是本地 DB 读(无网络);满足则把真同步交给 Celery worker,
        乐观 ack 立即返回;worker 完成后重生今日简报,失败时推送告知(fail-loud)。
        返回**串**(_exec_health_record 契约),作为 tool 结果交给 LLM 复述。
        """
        user_id = self._current_user_id
        if not user_id:
            return "无法确定当前用户身份,暂时不能发起同步,请稍后重试。"

        from app.models.user import GarminCredential

        credential = (
            self.db.query(GarminCredential)
            .filter(GarminCredential.user_id == user_id)
            .first()
        )
        # ── 护栏①:precondition fail-loud(本地 DB,无网络,绝不空转/谎报)──
        if not credential:
            return ("你还没有绑定 Garmin 账号,所以我无法同步手表数据。"
                    "请到「设置 → 设备」绑定 Garmin 账号,之后我就能帮你同步。")
        if not credential.sync_enabled:
            return ("你的 Garmin 同步在设置里是关闭状态。"
                    "到「设置 → 设备」打开同步后,我就能帮你拉取最新数据。")
        if not credential.credentials_valid:
            return ("你的 Garmin 登录凭据已失效(可能改过密码),无法同步。"
                    "请到「设置 → 设备」重新绑定账号。")
        if getattr(credential, "requires_mfa", False):
            # ── 护栏③:MFA 降级为指引,不自动重试 ──
            return ("你的 Garmin 账号开启了两步验证(MFA),暂时无法自动同步。"
                    "你可以在手机 Garmin Connect App 里手动刷新一次,"
                    "或到「设置 → 设备」完成一次验证后再让我同步。")

        # ── 护栏②:不内联阻塞;交给 Celery worker,乐观 ack 立即返回 ──
        try:
            from app.tasks.garmin_sync import sync_user_garmin_data
            sync_user_garmin_data.delay(user_id, days=1, notify_on_failure=True)
        except Exception as e:  # 入队失败(如 broker 不可用)也 fail-loud,不谎报成功
            logger.warning(f"[garmin_sync] enqueue 失败 user={user_id}: {e}")
            return ("同步服务暂时不可用,没能发起后台同步。"
                    "请稍后重试,或到「设置 → 设备」手动同步。")

        logger.info(f"[garmin_sync] enqueued background sync user={user_id}")
        return ("已经在后台开始同步你的 Garmin 数据了,通常一分钟内完成。"
                "同步好之后我会用最新数据刷新今日概览;万一没成功,我也会告诉你。")

    async def _exec_health_manage(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行已存在健康记录的查询/修改/删除.

        新增记录继续走 health_record；这里专门承接对话里的 CRUD 管理动作，
        避免 LLM 查到 ID 后无法真正删除或修改。
        """
        record_type = args.get("record_type")
        operation = args.get("operation")
        record_id = args.get("record_id")
        data = args.get("data") or {}
        if (
            record_type == "diet"
            and operation == "update"
            and self._turn_contextual_diet_record_id is not None
        ):
            replay = self._contextual_diet_replay_result(
                requested_record_id=record_id,
            )
            if replay is not None:
                return replay
            return (
                "Error: 本轮图片记录未取得可验证回执，"
                "未执行第二次饮食修改。"
            )
        # LLM 常传字面 'today'/'昨天'; 端点要真日期, 传 'today' → 422。归一成 ISO 日期,
        # 解析不出则不带日期过滤(列近期), 绝不把相对词当 start_date 发出去。
        target_date = _normalize_relative_date(
            args.get("date"),
            reference_now=self._agent_kernel_reference_now(),
        )
        target_meal_type = _normalize_diet_meal_type(args.get("meal_type") or data.get("meal_type"))
        if record_type == "diet" and target_meal_type:
            data["meal_type"] = target_meal_type
        # illness update: data.end_date 常是 '昨天'/'yesterday' 相对词。IllnessEpisodePatch
        # 的 end_date: date 收到相对词字面 → 422; 与顶层 args["date"] 一样在工具边界折算 ISO
        # (founder 实测「舌尖溃疡昨天好了」需 end_date=昨天)。折不出的相对词删掉该字段,降级
        # 到后端默认(status=resolved 自动补 end_date=today), 绝不把相对词原样发出去触发 422
        # → 写入回执守卫误报「无回执」。(IllnessEpisodePatch 只有 end_date, 无 start_date;
        # start_date 只在 create 路径有意义, 已在 _prepare_health_record_args_for_validation 里
        # 对 record_date/start_date/end_date 统一归一, 此处 manage 路径只补 end_date。)
        if record_type == "illness" and isinstance(data, dict) and data.get("end_date") not in (None, ""):
            _normalized_end = _normalize_relative_date(
                data.get("end_date"),
                reference_now=self._agent_kernel_reference_now(),
            )
            if _normalized_end:
                data["end_date"] = _normalized_end
            else:
                data.pop("end_date", None)
        try:
            limit = int(args.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 100))
        diet_query: dict[str, Any] = {"limit": limit}
        if target_date:
            diet_query["start_date"] = target_date
            diet_query["end_date"] = target_date
        if target_meal_type:
            diet_query["meal_type"] = target_meal_type

        list_paths = {
            "diet": f"/diet/records/me?{urlencode(diet_query)}",
            "water": "/water/records/me?limit=20",
            "weight": "/weight/records/me?limit=20",
            "waist": "/waist/records/me?limit=20",
            "blood_pressure": "/blood-pressure/records/me?limit=20",
            "sleep": "/sleep/records/me?limit=20",
            "mood": "/mood/records/me?limit=20",
            "excretion": "/excretion/records/me?limit=20",
            "exercise": "/daily-health/exercise/me?days=7",
            "illness": "/illness/episodes/all",
            "symptom": "/symptoms/me?limit=20",
            "medication": "/medication/medications/me?active_only=false",
            "medication_log": "/medication/today/me",
            "supplement": "/supplements/me/records?limit=20",
            "supplement_definition": "/supplements/me/definitions?active_only=false",
            "reminder": "/reminders/me?status=all&limit=50",
            "goal": "/goals/me",
            "medical_exam": f"/medical-exams/me/reports?limit={limit}",
            "event": "/episodes/me/life-events?days=30",
            "rhinitis": "/checkin/me/history?days=30",
        }
        record_paths = {
            "diet": "/diet/records/{id}",
            "water": "/water/records/{id}",
            "weight": "/weight/records/{id}",
            "waist": "/waist/records/{id}",
            "blood_pressure": "/blood-pressure/records/{id}",
            "sleep": "/sleep/records/{id}",
            "mood": "/mood/records/{id}",
            "excretion": "/excretion/records/{id}",
            "exercise": "/daily-health/exercise/{id}",
            "illness": "/illness/episodes/{id}",
            "symptom": "/symptoms/{id}",
            "medication": "/medication/medications/{id}",
            "medication_log": "/medication/logs/{id}",
            "supplement": "/supplements/records/{id}",
            "supplement_definition": "/supplements/definitions/{id}",
            "reminder": "/reminders/{id}",
            "goal": "/goals/{id}",
            # event 只开 list/delete(undo 通路);update 不开——occurred_at 由
            # 确定性代码折算,改动走删除后重记(registry update 格 gap 挂账)。
            "event": "/episodes/life-event/{id}",
            "rhinitis": "/checkin/{id}/rhinitis/latest",
        }
        update_supported = {
            "diet", "water", "weight", "waist", "blood_pressure",
            "sleep", "mood", "excretion", "illness", "medication",
            "supplement", "supplement_definition", "exercise", "symptom", "medication_log",
            "reminder", "goal",
        }
        path_tmpl = record_paths.get(record_type)

        async def _delete_record_by_id(resolved_record_id: Any) -> str:
            if not path_tmpl:
                return local_write_rejection(
                    "record_type_not_manageable",
                    message="当前记录类型不支持修改或删除。",
                )
            delete_path = path_tmpl.format(id=resolved_record_id)
            result = await self._api_delete(f"{base}{delete_path}", headers)
            if str(result).startswith("Error:"):
                return result
            if result:
                try:
                    payload = json.loads(result)
                except (json.JSONDecodeError, TypeError, ValueError):
                    payload = {"message": str(result)}
                if not isinstance(payload, dict) or _write_result_payload(payload) is None:
                    return result
            else:
                payload = {"message": "删除成功"}
            payload.setdefault("record_id", resolved_record_id)
            payload.setdefault("id", resolved_record_id)
            normalized_record_type = str(record_type or "").strip().lower()
            resource_type = _HEALTH_MANAGE_RESOURCE_TYPE_BY_RECORD_TYPE.get(
                normalized_record_type
            )
            if resource_type:
                payload.setdefault("resource_type", resource_type)
            self._invalidate_twin_after_mutation()
            return json.dumps(payload, ensure_ascii=False)

        if operation == "list":
            path = list_paths.get(record_type)
            if not path:
                return local_write_rejection(
                    "record_type_query_unsupported",
                    message="当前记录类型不支持查询。",
                )
            return await self._api_get(f"{base}{path}", headers)

        if not path_tmpl:
            return local_write_rejection(
                "record_type_not_manageable",
                message="当前记录类型不支持修改或删除。",
            )
        if not record_id:
            return local_write_rejection(
                "record_id_missing",
                message="修改或删除缺少记录 ID。",
                recovery_guidance="请先查询候选记录并确认要操作的记录。",
            )
        path = path_tmpl.format(id=record_id)

        if operation == "delete":
            return await _delete_record_by_id(record_id)

        if operation == "update":
            if record_type not in update_supported:
                return local_write_rejection(
                    "record_type_update_unsupported",
                    message="当前记录类型暂不支持修改。",
                    recovery_guidance="可以确认后删除原记录并重新记录。",
                )
            result = await self._api_put(f"{base}{path}", headers, data)
            self._invalidate_twin_after_mutation()
            if record_type == "diet" and not str(result).startswith("Error:"):
                try:
                    payload = json.loads(result)
                except (json.JSONDecodeError, TypeError, ValueError):
                    payload = None
                if isinstance(payload, dict):
                    meal_label = _MEAL_TYPE_ZH.get(target_meal_type or "", "饮食")
                    food_items = str(data.get("food_items") or "").strip()
                    payload["message"] = (
                        f"已更新{meal_label}：{food_items}"
                        if food_items else f"已更新{meal_label}记录"
                    )
                    result = json.dumps(payload, ensure_ascii=False)
            return result

        return local_write_rejection(
            "health_manage_operation_unsupported",
            message="当前健康记录管理操作不受支持。",
        )

    def _invalidate_twin_after_mutation(self) -> None:
        if self._current_user_id is None:
            return
        # A4: Twin 已变 → 本回合 done 侧 KB 证据卡强制重算 (belt-and-suspenders:
        # health_manage 也走上面主循环的 write_attempted 标记, 这里覆盖任何未来直接调用者)。
        self._turn_twin_write_occurred = True
        try:
            from app.twin.cache import invalidate_twin
            invalidate_twin(self._current_user_id)
        except Exception as e:
            logger.warning(f"[health_manage] Twin invalidation 失败 (旁路): {e}")

    async def _exec_health_analysis(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康分析"""
        atype = args.get("analysis_type", "comprehensive")
        days = args.get("days", 7)
        question = args.get("question", "")

        # orchestrator: 多专家协作深度分析
        if atype == "orchestrator" and question:
            # rank8: 默认进程内直调 run_orchestrator, 绕开 localhost HTTP + 全 FastAPI 中间件
            # 重入 (含 main.py 60s 请求超时中间件 —— 历史"内层 60s 连杀"故障类的根)。
            # kill-switch orchestrator_in_process=False 回退旧 HTTP 路径 (保留一个 release)。
            # 两条路径都过 _project_orchestrator_result: 进程内返回值与 HTTP 响应体 shape 一致。
            if getattr(settings, "orchestrator_in_process", True):
                result = await self._run_orchestrator_in_process(question)
            else:
                result = await self._api_post(
                    f"{base}/orchestrator/chat", headers,
                    {"query": question}
                )
            return _project_orchestrator_result(result)

        # supplement_effectiveness: 补剂效果评估
        if atype == "supplement_effectiveness":
            result = await self._api_post(
                f"{base}/supplements/scientific-recommendation", headers,
                {"use_llm": True}
            )
            return result

        analysis_map = {
            "comprehensive": f"/garmin-analysis/me/comprehensive?days={days}",
            "sleep_insight": f"/garmin-analysis/me/sleep?days={days}",
            "heart_rate_insight": f"/garmin-analysis/me/heart-rate?days={days}",
            "recovery_status": f"/garmin-analysis/me/body-battery?days={days}",
            "risk_factors": f"/garmin-analysis/me/comprehensive?days={days}",
            "trend": f"/garmin-analysis/me/comprehensive?days={days}",
        }

        path = analysis_map.get(atype, analysis_map["comprehensive"])
        return await self._api_get(f"{base}{path}", headers)

    # rank8: 内层深分析进程内直调超时 (秒)。旧 localhost HTTP 路径的有效预算是
    # min(main.py 60s 请求中间件, httpx 90s 读) = 60s —— 中间件先杀, 正是"内层 60s 连杀"
    # 故障类。进程内不再经中间件, 由本 wait_for 独占超时所有权。取 120s: 覆盖 prod 深分析
    # 最坏 115-187s 里的绝大多数完成回合 (旧路径这些全部被 60s 中间件误杀成 500), 又不让
    # 真卡死的回合无限期吃 /agent/send 的 300s 硬帽预算。超时 → 抛 TimeoutError → 落到
    # 既有工具失败处理 (返回 "Error: ..." 字符串), 回合存活。
    ORCHESTRATOR_IN_PROCESS_TIMEOUT_S: float = 120.0

    async def _run_orchestrator_in_process(self, question: str) -> str:
        """进程内直调 run_orchestrator, 替换 localhost POST /orchestrator/chat (rank8)。

        返回值 = OrchestratorResponse.model_dump(mode="json") 的 JSON 字符串, 与旧
        _api_post(/orchestrator/chat) 响应体 SHAPE-IDENTICAL (synthesis / intent /
        used_specialists / findings)。上层 _project_orchestrator_result 与 rank7 shadow
        捕获 (json.loads → 读 synthesis/perf) 零改动。

        DB 会话: 用**独立的 fresh SessionLocal**, 不复用 self.db —— 忠实复刻 HTTP 边界的
        会话隔离 (旧路径 /orchestrator/chat 走自己 request-scoped get_db session, 与 /agent
        请求的 session 完全隔离)。理由: run_orchestrator 会向传入 db 写副作用 (ActionCard
        落地 / clinical journal / memory extract / audit, 各自内部 commit)。复用 self.db 会
        (a) 把这些写与 executor 未提交的 user_message 事务纠缠、(b) 内部 commit 提前提交
        executor 的 pending 事务、(c) autoflush 意外推未提交对象。深分析只读已提交的健康数据
        (question 携带意图, 不依赖本回合未提交写), fresh session 安全且正确。契约同 get_db:
        不显式 commit (副作用写各自内部 commit), finally close, 异常 rollback。

        用户作用域: user_id 显式传 self._current_user_id (== 旧 HTTP 路径 JWT 解出的
        current_user.id), per-user 隔离一字不差 (health_read.canonical_read 先例)。

        超时所有权: 中间件已不在链路, 由 asyncio.wait_for 接管; 超时/异常 → 返回
        "Error: ..." 字符串 (与其余 _exec_* 失败契约一致), 回合存活。

        NOTE (rank11 seam): 流式 stream_orchestrator 的进程内分段流式改造是 rank11 的活,
        本方法只做非流式 run_orchestrator; 那里会在 caps=genui-v1 深报告路径切进程内 SSE。
        """
        from app.database import SessionLocal
        from app.orchestrator import OrchestratorRequest, run_orchestrator

        user_id = self._current_user_id
        if user_id is None:
            return "Error: 缺少用户身份, 无法执行深度分析"

        # 与旧 HTTP body {"query": question} 逐字节等价: source 不传 (默认 None), 不触发
        # source=='siri' 的 fast 短路; client_caps/specialists 用默认 (旧路径未带 caps 头)。
        req = OrchestratorRequest(query=question)
        orch_db = SessionLocal()
        try:
            response = await asyncio.wait_for(
                run_orchestrator(orch_db, user_id, req),
                timeout=self.ORCHESTRATOR_IN_PROCESS_TIMEOUT_S,
            )
            return json.dumps(
                response.model_dump(mode="json"), ensure_ascii=False, default=str
            )
        except asyncio.TimeoutError:
            orch_db.rollback()
            logger.error(
                "[agent_executor] in-process orchestrator timed out after %.0fs user=%s",
                self.ORCHESTRATOR_IN_PROCESS_TIMEOUT_S, user_id,
            )
            return (
                f"Error: 深度分析超时（>{int(self.ORCHESTRATOR_IN_PROCESS_TIMEOUT_S)}s），"
                "请稍后重试"
            )
        except Exception as e:  # noqa: BLE001 — 任何失败降级为工具错误字符串, 回合存活
            orch_db.rollback()
            logger.exception(
                "[agent_executor] in-process orchestrator failed user=%s: %s", user_id, e
            )
            return f"Error: 深度分析执行失败: {safe_llm_error_message(str(e))}"
        finally:
            orch_db.close()

    async def _exec_environment(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行环境数据查询"""
        ctype = args.get("check_type", "weather")
        path_map = {
            "weather": "/environment/weather",
            "air_quality": "/environment/air-quality",
            # outdoor-advice 是历史 typo, 真实端点: exercise-suitability (单项) /
            # advice (综合). 用 advice 信息更全, 含天气+AQI+UV+建议
            "outdoor_suitability": "/environment/advice",
            "exercise_suitability": "/environment/exercise-suitability",
            "morning_briefing": "/environment/morning-briefing",
            "forecast": "/environment/weather/forecast",
        }
        path = path_map.get(ctype, "/environment/weather")
        params: Dict[str, Any] = {}
        city = str(args.get("city") or "").strip()
        if city:
            params["city"] = city
        if ctype == "forecast":
            try:
                days = int(args.get("days", 3))
            except (TypeError, ValueError):
                days = 3
            params["days"] = min(max(days, 1), 7)
        if params:
            path = f"{path}?{urlencode(params)}"
        return await self._api_get(f"{base}{path}", headers)

    async def _exec_supplement_guide(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """获取补剂指南"""
        # D1: 进程内直读(复用 daily_supplement_guide service);flag 关 → 旧 localhost HTTP。
        if getattr(settings, "reads_in_process", True):
            from app.services.agent_read_tools import read_supplement_daily_guide

            raw = await self._read_in_process(
                read_supplement_daily_guide, self._current_user_id
            )
            return _truncate_for_display(raw)
        return await self._api_get(f"{base}/supplements/daily-guide", headers)

    async def _exec_manage_plan(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """管理健康计划"""
        action = args.get("action", "")
        data = args.get("data", {})

        if action == "generate_weekly":
            return await self._api_post(f"{base}/smart-plan/generate", headers, data)
        elif action == "complete_item":
            plan_id = data.get("plan_id")
            item_id = data.get("item_id")
            if plan_id and item_id:
                return await self._api_patch(
                    f"{base}/smart-plan/{plan_id}/items/{item_id}",
                    headers, {"is_completed": True}
                )
            return local_write_rejection(
                "plan_item_identity_missing",
                message="完成计划项缺少计划 ID 或项目 ID。",
                recovery_guidance="请先查询并确认要完成的计划项目。",
            )
        elif action == "save_to_card":
            return await self._api_post(f"{base}/action-cards/from-message", headers, data)
        return local_write_rejection(
            "plan_action_unsupported",
            message="当前计划操作不受支持。",
        )

    async def _exec_intervention_cycle(self, args: dict) -> str:
        """N-of-1 干预结局闭环工具 — status/list/start/update/cancel.

        直接复用 intervention_cycle_service (不重写 SQL/不重算 delta), 用户隔离靠
        self._current_user_id。service 是同步, 丢线程池避免阻塞事件循环。
        """
        import asyncio as _aio

        action = args.get("action", "")
        user_id = self._current_user_id
        if user_id is None:
            return local_write_rejection(
                "intervention_user_missing",
                message="当前会话缺少用户身份，无法操作干预周期。",
            )

        if action == "status":
            return await _aio.to_thread(self._intervention_status, user_id)

        if action in {"list", "history"}:
            status = str(args.get("status") or "all")
            try:
                limit = int(args.get("limit") or 20)
            except (TypeError, ValueError):
                limit = 20
            return await _aio.to_thread(self._intervention_list, user_id, status, limit)

        if action == "start":
            # 写操作: 沿用 _confirm_or_describe 两段式确认门 (与 health_record 一致)。
            confirmed = args.get("confirmed") is True or args.get("confirm") is True
            if not confirmed:
                return (
                    "[NEEDS_CONFIRMATION] 我准备为你开启一个 N-of-1 代谢干预周期: "
                    "锁定当前化验/身体快照作为基线, 以你当前偏高的代谢指标 (如 LDL/尿酸/血糖/肝酶) "
                    "作为结局目标, 一段时间后用你自己的复查数据验证干预是否有效。"
                    "这是健康自我管理工具, 非医疗诊断, 重大调整请结合医生意见。"
                    "请向用户复述并问一次'要开启这个周期吗？', "
                    "用户确认后**重新调用** intervention_cycle(action='start', confirmed=true)。"
                )
            days = args.get("days", 90)
            try:
                days = int(days)
            except (ValueError, TypeError):
                days = 90
            if days < 7 or days > 365:
                days = 90
            return await _aio.to_thread(self._intervention_start, user_id, days)

        if action == "update":
            confirmed = args.get("confirmed") is True or args.get("confirm") is True
            if not confirmed:
                return (
                    "[NEEDS_CONFIRMATION] 我准备调整你的干预周期参数。"
                    "这会影响后续的计划窗口、目标指标或停止条件, 但不会改历史基线和已记录复查。"
                    "请向用户复述要调整的内容并确认; 用户明确同意后重新调用 "
                    "intervention_cycle(action='update', confirmed=true)。"
                )
            return await _aio.to_thread(self._intervention_update, user_id, args)

        if action in {"cancel", "delete"}:
            confirmed = args.get("confirmed") is True or args.get("confirm") is True
            if not confirmed:
                return (
                    "[NEEDS_CONFIRMATION] 我准备取消当前干预周期。"
                    "取消后会保留历史记录, 状态改为 abandoned, 不会删除既有数据。"
                    "请向用户确认是否取消; 用户明确同意后重新调用 "
                    "intervention_cycle(action='cancel', confirmed=true)。"
                )
            return await _aio.to_thread(self._intervention_cancel, user_id, args)

        return local_write_rejection(
            "intervention_action_unsupported",
            message="当前干预周期操作不受支持。",
        )

    async def _exec_draft_aigc_media(self, args: dict) -> str:
        """Create a server-bound AIGC draft; a user click dispatches it later."""
        from app.services.aigc_media_job_service import (
            AIGCMediaJobError,
            AIGCMediaJobRequest,
            AIGCMediaJobRequestError,
            AIGCMediaJobService,
        )
        from app.services.aigc_media_service import AIGCMediaConfigurationError

        user_id = self._current_user_id
        if user_id is None:
            return local_write_rejection(
                "aigc_user_missing",
                message="当前会话缺少用户身份，无法创建创作草稿。",
            )
        kind = str(args.get("kind") or "").strip()
        requires_source = kind in {"image_to_image", "image_to_video"}
        source_message_id = self._current_turn_source_message_id if requires_source else None
        if requires_source and (source_message_id is None or not self._current_turn_image_urls):
            return local_write_rejection(
                "aigc_source_image_missing",
                message="当前创作类型需要一张来源图片。",
                recovery_guidance="请在当前消息上传图片后重新创建草稿。",
            )
        service = AIGCMediaJobService(self.db)
        try:
            confirmation = await service.issue_confirmation(
                user_id=user_id,
                conversation_id=self._current_turn_conversation_id,
                request=AIGCMediaJobRequest(
                    kind=kind,
                    purpose=str(args.get("purpose") or ""),
                    prompt=str(args.get("prompt") or ""),
                    source_message_id=source_message_id,
                    source_image_index=0,
                    duration_seconds=int(args.get("duration_seconds") or 5),
                    ratio=str(args.get("ratio") or "9:16"),
                ),
            )
        except AIGCMediaConfigurationError:
            return local_write_rejection(
                "aigc_service_unconfigured",
                message="AIGC 媒体服务当前未配置。",
            )
        except AIGCMediaJobRequestError as exc:
            return local_write_rejection(
                "aigc_request_invalid",
                message=str(exc),
            )
        except AIGCMediaJobError as exc:
            return f"Error: {exc}"

        card_data = {
            "confirmation_id": confirmation.id,
            "kind": confirmation.kind,
            "title": (
                "短视频草稿"
                if confirmation.kind in {"text_to_video", "image_to_video"}
                else "图片草稿"
            ),
            "provider": (
                "百炼 HappyHorse"
                if confirmation.kind in {"text_to_video", "image_to_video"}
                and str(confirmation.model).startswith("happyhorse-")
                else "百炼"
            ),
            "source_attached": confirmation.source_message_id is not None,
            "status": "pending",
            **_aigc_media_content_preview(
                kind=confirmation.kind,
                prompt=str(args.get("prompt") or ""),
            ),
        }
        if confirmation.kind in {"text_to_video", "image_to_video"}:
            from app.services.aigc_media_capabilities import video_capability_for

            capability = video_capability_for(
                model=confirmation.model,
                kind=confirmation.kind,
            )
            card_data.update(
                {
                    "duration_seconds": confirmation.duration_seconds,
                    "duration_options": list(capability.selectable_duration_seconds),
                    "ratio": confirmation.ratio,
                    "resolution": capability.default_resolution,
                    "generates_audio": capability.generates_audio,
                }
            )
        descriptor = {
            "type": "aigc_media_confirmation",
            "data": card_data,
            "actions": [
                {
                    "id": f"aigc_media.confirm:{confirmation.id}",
                    "label": "确认并生成",
                    "action": "aigc_media.confirm",
                    "endpoint": f"/aigc/media/confirmations/{confirmation.id}/confirm",
                    "requires_manual_confirm": True,
                    "capability_id": "aigc_media_confirmation.v1",
                    "required_receipt": True,
                    "autonomy_tier": "manual_confirm",
                    "policy_reason": "manual_confirm_write",
                }
            ],
        }
        self._turn_aigc_media_cards = _merge_agent_card_descriptors(
            self._turn_aigc_media_cards,
            [descriptor],
        )
        return json.dumps(
            {
                "id": confirmation.id,
                "resource_type": "aigc_media_confirmation",
                "operation_id": f"draft_aigc_media:{confirmation.id}",
                "status": "pending_user_confirmation",
                "kind": confirmation.kind,
            },
            ensure_ascii=False,
        )

    def _intervention_list(self, user_id: int, status: str, limit: int) -> str:
        """列出当前用户干预周期历史。"""
        from app.services import intervention_cycle_service as ics

        if status not in {"all", "active", "completed", "abandoned"}:
            status = "all"
        cycles = ics.list_cycles(self.db, user_id, status=status, limit=limit)
        if not cycles:
            return "暂无干预周期历史。"

        lines = []
        for c in cycles:
            start = c.start_date.isoformat() if c.start_date else "?"
            end = c.planned_end_date.isoformat() if c.planned_end_date else "?"
            target_count = len(c.target_metrics or [])
            outcome_count = len(c.outcomes or [])
            lines.append(
                f"- #{c.id}: {c.status} · {c.cycle_type} · {start}→{end} · "
                f"目标 {target_count} 项 · 结局 {outcome_count} 项"
            )
        return "干预周期历史:\n" + "\n".join(lines)

    def _owned_intervention_cycle(self, user_id: int, cycle_id=None):
        from app.models.intervention_cycle import InterventionCycle
        from app.services import intervention_cycle_service as ics

        if cycle_id is None:
            return ics.get_active_cycle(self.db, user_id)
        try:
            cid = int(cycle_id)
        except (TypeError, ValueError):
            return None
        if cid <= 0:
            return None
        return (
            self.db.query(InterventionCycle)
            .filter(InterventionCycle.id == cid, InterventionCycle.user_id == user_id)
            .first()
        )

    @staticmethod
    def _intervention_write_receipt(cycle, action: str, message: str) -> str:
        """Return a verifiable receipt while retaining the user-facing copy."""
        return json.dumps(
            {
                "id": cycle.id,
                "resource_type": "intervention_cycle",
                "operation_id": f"intervention_cycle:{cycle.id}:{action}",
                "status": "verified",
                "success": True,
                "message": message,
            },
            ensure_ascii=False,
        )

    def _intervention_update(self, user_id: int, args: dict) -> str:
        """调整 active cycle 参数; 不修改历史基线。"""
        from app.services import intervention_cycle_service as ics

        cycle = self._owned_intervention_cycle(user_id, args.get("cycle_id"))
        if cycle is None:
            return local_write_rejection(
                "intervention_cycle_not_found",
                message="没有找到可调整的干预周期。",
                recovery_guidance="请先查询并确认要调整的周期。",
            )
        if cycle.status != "active":
            return local_write_rejection(
                "intervention_cycle_not_active",
                message="只能调整进行中的干预周期。",
            )

        days = args.get("days")
        if days is not None:
            try:
                days = int(days)
            except (TypeError, ValueError):
                return local_write_rejection(
                    "intervention_days_invalid",
                    message="干预周期天数必须是整数。",
                )
        target_specs = args.get("target_specs") if isinstance(args.get("target_specs"), list) else None
        stop_conditions = (
            args.get("stop_conditions") if isinstance(args.get("stop_conditions"), list) else None
        )
        if days is None and target_specs is None and stop_conditions is None:
            return local_write_rejection(
                "intervention_update_empty",
                message="干预周期调整缺少可更新的字段。",
                recovery_guidance="请提供天数、目标或停止条件。",
            )

        try:
            cycle = ics.update_cycle_params(
                self.db,
                cycle,
                days=days,
                target_specs=target_specs,
                stop_conditions=stop_conditions,
            )
        except Exception:
            self.db.rollback()
            raise

        end = cycle.planned_end_date.isoformat() if cycle.planned_end_date else "未设置"
        message = (
            f"已调整干预周期 #{cycle.id}: 计划结束日 {end}, "
            f"目标 {len(cycle.target_metrics or [])} 项, 停止条件 {len(cycle.stop_conditions or [])} 条。"
        )
        return self._intervention_write_receipt(cycle, "update", message)

    def _intervention_cancel(self, user_id: int, args: dict) -> str:
        """取消 active cycle; 保留历史记录。"""
        from app.services import intervention_cycle_service as ics

        cycle = self._owned_intervention_cycle(user_id, args.get("cycle_id"))
        if cycle is None:
            return local_write_rejection(
                "intervention_cycle_not_found",
                message="没有找到可取消的干预周期。",
                recovery_guidance="请先查询并确认要取消的周期。",
            )
        if cycle.status != "active":
            return local_write_rejection(
                "intervention_cycle_not_active",
                message="只能取消进行中的干预周期。",
            )

        try:
            cycle = ics.complete_cycle(self.db, cycle, status="abandoned")
        except Exception:
            self.db.rollback()
            raise
        reason = str(args.get("reason") or "").strip()
        reason_text = f" 原因: {reason}" if reason else ""
        message = f"已取消干预周期 #{cycle.id}, 历史记录已保留。{reason_text}"
        return self._intervention_write_receipt(cycle, "cancel", message)

    def _intervention_status(self, user_id: int) -> str:
        """组织当前 active 周期的人话进展摘要 (无周期则友好提示)。"""
        from app.services import intervention_cycle_service as ics
        from app.biomarkers import get_definition
        from app.services.personal_models.intervention_priors import _is_clinician_gated_code

        cycle = ics.get_active_cycle(self.db, user_id)
        if cycle is None:
            return (
                "目前没有进行中的干预周期。如果你有偏高的代谢指标 (如 LDL/尿酸/血糖), "
                "可以开一个 N-of-1 周期, 用你自己的复查数据验证某个干预是否有效。"
            )

        _status_zh = {
            "met": "达标", "improving": "改善中", "worsening": "变差",
            "flat": "持平", "pending": "待复查",
        }
        lines = []
        for om in cycle.outcomes:
            defn = get_definition(om.metric_code)
            name = defn.display if defn else om.metric_code
            unit = om.unit or ""
            if om.baseline_value is None:
                lines.append(f"- {name}: 基线缺失, 待补化验")
                continue
            if om.latest_value is None:
                tgt = f"(目标 {om.target_value}{unit})" if om.target_value is not None else ""
                lines.append(f"- {name}: 基线 {om.baseline_value}{unit} {tgt}, 待复查")
                continue
            tgt = f", 目标 {om.target_value}{unit}" if om.target_value is not None else ""
            # R16 P1:处方/激素指标(LDL/糖化/血糖 …)不外吐裸裁决(改善中/变差)与变化幅度
            # —— 会被反推成「对你有效」的效应裁决(被并行处方药混杂),违 R4。只给事实值 + 需医生评估。
            if _is_clinician_gated_code(om.metric_code):
                lines.append(
                    f"- {name}: {om.baseline_value}{unit} → {om.latest_value}{unit}{tgt} [需医生评估]"
                )
                continue
            zh = _status_zh.get(om.status, om.status or "待复查")
            delta_txt = ""
            if om.delta is not None:
                sign = "+" if om.delta > 0 else ""
                pct = f" ({sign}{om.delta_pct}%)" if om.delta_pct is not None else ""
                delta_txt = f", Δ {sign}{om.delta}{unit}{pct}"
            lines.append(
                f"- {name}: {om.baseline_value}{unit} → {om.latest_value}{unit}{delta_txt}{tgt} [{zh}]"
            )

        body = "\n".join(lines) if lines else "- (尚无结局指标)"
        header = (
            f"当前干预周期 ({cycle.cycle_type}, 状态 {cycle.status}, "
            f"起始 {cycle.start_date.isoformat() if cycle.start_date else '?'})。\n"
            "各结局指标 (基线 → 最新):\n"
        )
        return header + body

    def _intervention_start(self, user_id: int, days: int) -> str:
        """复用 service 开周期; 已有进行中则返回它。DB 异常 rollback 并上抛感知。"""
        from app.services import intervention_cycle_service as ics
        from app.twin.builder import build_twin

        existing = ics.get_active_cycle(self.db, user_id)
        if existing is not None:
            message = (
                "你已经有一个进行中的干预周期了 (同一时间只跟踪一个), 没有重复开。"
                "想看进展用 status; 想换目标可以等当前周期结束。"
            )
            return self._intervention_write_receipt(existing, "start", message)

        try:
            twin = build_twin(self.db, user_id, use_cache=False)
            cycle = ics.start_metabolic_cycle(self.db, user_id, twin, days=days)
            # 开周期时若 biomarker 尚未归一, 目标可能为空 → 用 service 补齐 (幂等)。
            if not cycle.outcomes:
                ics.refresh_cycle_targets(self.db, cycle)
        except Exception:
            self.db.rollback()
            raise

        n = len(cycle.outcomes)
        if n == 0:
            message = (
                f"已开启干预周期 (周期 {days} 天), 但暂时没有可锁定的异常代谢指标作为目标。"
                "建议先补一次化验 (血脂/血糖/肝功/尿酸), 之后复查时就能验证效果了。"
            )
            return self._intervention_write_receipt(cycle, "start", message)
        from app.biomarkers import get_definition
        names = [
            (get_definition(om.metric_code).display if get_definition(om.metric_code) else om.metric_code)
            for om in cycle.outcomes
        ]
        message = (
            f"已开启 N-of-1 干预周期 (周期 {days} 天), 锁定基线快照。"
            f"将跟踪 {n} 项结局指标: {', '.join(names)}。"
            "过段时间复查化验后, 我会用你自己的数据告诉你有没有改善。"
            "(非医疗诊断, 重大健康调整请结合医生意见。)"
        )
        return self._intervention_write_receipt(cycle, "start", message)

    async def _exec_upload_genetic_txt(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """上传 23andMe / WeGene TXT 原始数据."""
        txt = args.get("txt_content") or ""
        if len(txt) < 50:
            return local_write_rejection(
                "genetic_text_invalid",
                message="基因原始数据内容过短或格式不正确。",
                recovery_guidance="请上传包含 rsid 的完整原始 TXT 内容。",
            )
        today = self._agent_kernel_reference_now().strftime("%Y-%m-%d")
        payload = {
            "test_provider": args.get("test_provider") or "unknown",
            "test_date": args.get("test_date") or today,
            "txt_content": txt,
            "notes": args.get("notes") or "LLM 工具自动上传",
        }
        return await self._api_post(f"{base}/genetic/profiles/upload-txt", headers, payload)

    async def _exec_query_genetic_profile(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """列出基因档案."""
        # D1: 进程内直读(仅档案元数据 provider/date/notes,不含变异位点);flag 关 → 旧 HTTP。
        if getattr(settings, "reads_in_process", True):
            from app.services.agent_read_tools import read_genetic_profiles

            raw = await self._read_in_process(
                read_genetic_profiles, self._current_user_id
            )
            return _truncate_for_display(raw)
        return await self._api_get(f"{base}/genetic/profiles/me", headers)

    async def _exec_upload_medical_exam_text(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """口述化验文本 → medical_text_parser → 入 MedicalExam + Indicator."""
        text = (args.get("text") or "").strip()
        if not text:
            return local_write_rejection(
                "medical_exam_text_missing",
                message="化验记录文本不能为空。",
            )
        if self._current_user_id is None:
            return local_write_rejection(
                "medical_exam_user_missing",
                message="当前会话缺少用户身份，无法写入化验指标。",
            )

        from app.services.medical_text_parser import parse_lab_indicators_from_text

        raw_date = args.get("exam_date")
        normalized_date = _normalize_relative_date(
            raw_date,
            reference_now=self._agent_kernel_reference_now(),
        )
        if raw_date and not normalized_date:
            return local_write_rejection(
                "medical_exam_date_invalid",
                message="化验日期格式无效。",
                recovery_guidance="请使用 YYYY-MM-DD 或今天、昨天等明确日期。",
            )
        exam_date = datetime.strptime(
            normalized_date or self._agent_kernel_reference_now().date().isoformat(),
            "%Y-%m-%d",
        ).date()

        try:
            items = parse_lab_indicators_from_text(text)
        except (TypeError, ValueError):
            items = []
        report_type = str(args.get("report_type") or "").strip().lower()
        narrative_report_types = {
            "imaging",
            "mri",
            "ct",
            "pathology",
            "ultrasound",
            "endoscopy",
            "medical_report",
        }
        is_narrative_report = report_type in narrative_report_types
        if not items and not is_narrative_report:
            return local_write_rejection(
                "medical_exam_text_invalid",
                message="未能从文本中识别出可入库的化验指标。",
                recovery_guidance=(
                    "化验结果请补充项目、数值和单位；MRI、CT、病理等报告"
                    "请同时标明报告类型。"
                ),
            )

        try:
            from app.services.data_collection.medical_exam_import import (
                MedicalExamImportService,
            )
            from app.services.agent_operation_reconciliation import (
                runtime_operation_source_fingerprint,
            )
            from app.twin.cache import invalidate_twin

            runtime_operation_id = str(
                args.get("_runtime_operation_id") or ""
            ).strip()
            source_fingerprint = (
                runtime_operation_source_fingerprint(runtime_operation_id)
                if runtime_operation_id
                else None
            )
            exam_type = (
                "imaging"
                if report_type in {"mri", "ct", "ultrasound", "endoscopy"}
                else (report_type or "biochemistry")
            )
            exam = MedicalExamImportService.import_from_items(
                self.db,
                user_id=self._current_user_id,
                items_data=items,
                exam_date=exam_date,
                exam_type=exam_type,
                notes=(
                    "从聊天文本导入，叙述内容待用户核对"
                    if is_narrative_report
                    else "从聊天文本导入"
                ),
                source="agent_text",
                overall_assessment=text if is_narrative_report else None,
                source_fingerprint=source_fingerprint,
            )
            # 这里显式置位, 让 done 侧 KB 证据卡重算反映刚写入的化验指标;
            # 同时由统一写入回执集合负责验证本次持久化身份。
            self._turn_twin_write_occurred = True
            try:
                invalidate_twin(self._current_user_id)
            except Exception:
                pass
            return json.dumps(
                {
                    "message": "化验指标已写入系统",
                    "id": exam.id,
                    "exam_id": exam.id,
                    "resource_type": "medical_exam",
                    "exam_date": exam.exam_date.isoformat() if exam.exam_date else None,
                    "items_count": len(exam.items or []),
                },
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "medical exam import failed error_type=%s",
                type(exc).__name__,
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            return "Error: 化验指标入库失败"

    _MAX_LAB_BATCH_NAMES = 20  # 单次批量最多查这么多指标(防滥用/超时)

    def _query_one_lab_indicator(self, name: str, since, limit: int) -> dict:
        """单指标历史查询(BP 桥接 + MedicalIndicator)。返回 dict(调用方 json.dumps)。同步读 self.db。"""
        from sqlalchemy import or_, desc as sa_desc

        name = (name or "").strip()
        if name and _is_blood_pressure_indicator_name(name):
            from app.models.blood_pressure import BloodPressureRecord

            rows = (
                self.db.query(BloodPressureRecord)
                .filter(
                    BloodPressureRecord.user_id == self._current_user_id,
                    BloodPressureRecord.record_date >= since,
                )
                .order_by(
                    sa_desc(BloodPressureRecord.record_date),
                    sa_desc(BloodPressureRecord.id),
                )
                .limit(limit)
                .all()
            )
            items = [_blood_pressure_indicator_item(record) for record in rows]
            if not items:
                return {
                    "count": 0,
                    "metric_key": "blood_pressure",
                    "items": [],
                    "hint": "未找到血压记录；血压属于 vital sign，会从 blood_pressure_records 查询，不属于 MedicalIndicator 化验表。",
                }
            return {
                "count": len(items),
                "metric_key": "blood_pressure",
                "source": "blood_pressure_records",
                "items": items,
            }

        from app.models.family_health import MedicalIndicator

        q = self.db.query(MedicalIndicator).filter(
            MedicalIndicator.user_id == self._current_user_id,
            MedicalIndicator.record_date >= since,
        )
        if name:
            up = name.upper()
            q = q.filter(or_(
                MedicalIndicator.name == name,
                MedicalIndicator.name_en == up,
                MedicalIndicator.name.ilike(f"%{name}%"),
            ))
        rows = q.order_by(sa_desc(MedicalIndicator.record_date)).limit(limit).all()
        if not rows:
            return {"count": 0, "items": [], "hint": f"未找到 {name or '任何'} 指标"}
        items = [
            {
                "name": r.name, "name_en": r.name_en,
                "value": r.value, "unit": r.unit,
                "record_date": r.record_date.isoformat() if r.record_date else None,
                "is_abnormal": r.is_abnormal,
                "reference_low": r.reference_low,
                "reference_high": r.reference_high,
            }
            for r in rows
        ]
        return {"count": len(items), "items": items}

    async def _exec_query_lab_indicators(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """查询 MedicalIndicator (跨次体检的指标历史). 直接读 DB, 不走 HTTP.

        **批量**: 传 names=[...] 一次查多个指标(省 LLM 往返轮);单指标传 name(shape 向后兼容不变)。
        """
        if self._current_user_id is None:
            return "Error: 当前会话无 user_id, 无法查询"

        since_str = args.get("since")
        limit = max(1, min(int(args.get("limit") or 20), 100))
        try:
            from datetime import date as _date
            since = (datetime.strptime(since_str, "%Y-%m-%d").date()
                     if since_str else _date.today() - timedelta(days=365))
        except Exception:
            return f"Error: since 必须是 YYYY-MM-DD, got {since_str!r}"

        # 批量路径:names(list)优先。去重、保序、去空、封顶。
        raw_names = args.get("names")
        # 弱模型兜底:names 可能被吐成字符串化的 JSON 数组(如 '["LDL","ALT"]')→ 试解析。
        if isinstance(raw_names, str):
            s = raw_names.strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        raw_names = parsed
                except Exception:
                    pass  # 解析失败 → 落回单指标路径(fail-safe)
        if isinstance(raw_names, list):
            seen: set[str] = set()
            names: list[str] = []
            for n in raw_names:
                s = str(n or "").strip()
                if s and s not in seen:
                    seen.add(s)
                    names.append(s)
            names = names[: self._MAX_LAB_BATCH_NAMES]
            if names:
                by_name = {n: self._query_one_lab_indicator(n, since, limit) for n in names}
                total = sum(v.get("count", 0) for v in by_name.values())
                truncated = len([x for x in raw_names if str(x or "").strip()]) > self._MAX_LAB_BATCH_NAMES
                result = json.dumps(
                    {"batch": True, "count": total, "queried": names,
                     "by_name": by_name, "truncated": truncated},
                    ensure_ascii=False,
                )
                from app.utils.blood_pressure_classify import append_severe_bp_reading_warning

                return append_severe_bp_reading_warning(result)

        # 单指标(向后兼容:返回原 shape)
        result = json.dumps(
            self._query_one_lab_indicator(args.get("name"), since, limit),
            ensure_ascii=False,
        )
        from app.utils.blood_pressure_classify import append_severe_bp_reading_warning

        return append_severe_bp_reading_warning(result)

    async def _read_in_process(self, reader, *args, **kwargs) -> str:
        """D1 读拉类进程内直调统一入口 —— 在 fresh SessionLocal 里跑一个同步只读函数。

        照 `_run_orchestrator_in_process` 的会话纪律(garmin-sync 治理 Wave 3 D1):
        - **fresh SessionLocal(非 self.db)**:忠实复刻 HTTP 边界会话隔离,bulletproof 防
          reader 内部隐藏 commit / autoflush 纠缠执行器未提交的 user_message 事务。
        - **只读**:成功不显式 commit;`finally` close;异常 rollback + close。
        - **丢线程池**(`asyncio.to_thread`):reader 是同步 DB 读,复刻 FastAPI 对 sync
          handler 的 threadpool 行为,不阻塞事件循环。Session 非线程安全 → 在线程内新建。
        - reader 签名:`reader(db, *args, **kwargs) -> str`。reader 内部**绝不**调 build_twin
          (其 Phase B 忽略传入 db 自开 SessionLocal 连真 PG,见 memory
          project_build_twin_sessionlocal_ignores_db)。

        超时所有权:本调用被 `_run_tool_with_progress` 的 per-tool 预算 + 心跳包住(D2:
        工具执行脑独占 wall-clock),此处不自设 timeout。
        """
        from app.database import SessionLocal

        def _run() -> str:
            db = SessionLocal()
            try:
                return reader(db, *args, **kwargs)
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        return await asyncio.to_thread(_run)

    async def _api_get_json(self, url: str, headers: dict):
        """HTTP GET, 返回解析后的 JSON (list/dict)。

        与 _api_get 不同: 不做任何"显示截断"——后者会把超长响应按字符截到 3000,
        切断 JSON token (如 'null'→'nul'), 导致调用方 json.loads 抛
        'Invalid control character' / 'Extra data'。机器要解析的内部查找
        (补剂/药物/症状 ID 匹配) 必须走这里, 拿干净可解析的数据。

        返回 (data, None) 成功; (None, err_str) 失败 — 调用方据此给用户友好兜底。
        """
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        try:
            resp = await client.get(url, headers=headers)
        except Exception as e:
            return None, f"网络错误: {e}"
        if resp.status_code != 200:
            return None, f"API 返回 {resp.status_code}"
        try:
            return resp.json(), None
        except Exception as e:
            logger.warning(f"[agent] _api_get_json 解析失败 url={url}: {e}")
            return None, "数据格式异常"

    async def _api_get(self, url: str, headers: dict) -> str:
        """HTTP GET (返回文本, 给 LLM 当上下文; 超长会做显示截断)。

        ⚠️ 注意: 返回值可能被字符截断, 不可直接 json.loads。机器解析请用 _api_get_json。
        """
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        return _truncate_for_display(resp.text)

    async def _api_post(self, url: str, headers: dict, data: dict) -> str:
        """HTTP POST"""
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.post(url, headers={**headers, "Content-Type": "application/json"}, json=data)
        if resp.status_code not in (200, 201):
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        return resp.text

    async def _api_post_json(self, url: str, headers: dict, data: dict):
        """HTTP POST, 返回解析后的 JSON (dict/list)。给机器解析(如取新建资源的 id)。

        返回 (data, None) 成功; (None, err_str) 失败 —— 同 _api_get_json 约定。
        """
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        try:
            resp = await client.post(url, headers={**headers, "Content-Type": "application/json"}, json=data)
        except Exception as e:
            return None, f"网络错误: {e}"
        if resp.status_code not in (200, 201):
            return None, f"API 返回 {resp.status_code}"
        try:
            return resp.json(), None
        except Exception as e:
            logger.warning(f"[agent] _api_post_json 解析失败 url={url}: {e}")
            return None, "数据格式异常"

    async def _api_patch(self, url: str, headers: dict, data: dict) -> str:
        """HTTP PATCH"""
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.patch(url, headers={**headers, "Content-Type": "application/json"}, json=data)
        if resp.status_code not in (200, 201):
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        return resp.text

    async def _api_put(self, url: str, headers: dict, data: dict) -> str:
        """HTTP PUT"""
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.put(url, headers={**headers, "Content-Type": "application/json"}, json=data)
        if resp.status_code not in (200, 201):
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        return resp.text

    async def _api_delete(self, url: str, headers: dict) -> str:
        """HTTP DELETE"""
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.delete(url, headers=headers)
        if resp.status_code not in (200, 202, 204):
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        return resp.text
