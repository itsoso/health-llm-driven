"""统一健康 Agent 执行器 — 结构化工具调用 + 多步推理循环

所有对话（记录、查询、分析、图片识别）统一走此入口。

流程：
  1. 注入健康上下文 + tool schemas
  2. 调用 LLM（OpenAI 兼容）
  3. 解析 tool_call → 执行 Health API
  4. 将 tool_result 返回模型 → 循环直到无更多 tool_call
  5. 最终回答通过 SSE 流式输出
"""
import json
import logging
import re
import time
from datetime import UTC, datetime, timezone, timedelta
from typing import AsyncGenerator, Dict, Any, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.tool_schema_registry import get_health_tools
from app.services.lab_plausibility import annotate_if_implausible
from app.services.llm.error_messages import safe_llm_error_message
from app.services.health_query_dimensions import normalize_health_query_args
from app.services.post_record_quality import (
    build_post_record_quality_response,
    combine_post_record_quality_responses,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
# 最终用户回复的 token 上限。健康养护/操作清单类回复常 >4000 token,
# 旧值 4000 会把 Opus 4.7 的长回复硬截断(用户需手动点"继续")。
# Opus 4.7 / GPT-5.5 / Gemini 3.1 均支持远高于此, 8000 覆盖绝大多数长方案。
ANSWER_MAX_TOKENS = 8000
# 快路由回合 (简单记录/查询) 的答案 token 上限。简单回合的答案 (已记录/几步/多少毫升)
# 从不需要 8000, 长尾解码本身就是延迟的一部分 —— 只对 fast-routed turn 收紧到 2000,
# 其它一切 (建议/分析/复盘/长方案) 仍用 ANSWER_MAX_TOKENS。
FAST_ROUTE_ANSWER_MAX_TOKENS = 2000
INTERRUPTED_COMPLETION_NOTICE = "\n\n[回复因长度限制中断，请让我接着上文继续。]"
AGENT_MODEL = "NousResearch/Hermes-3-Llama-3.1-8B"
BEIJING_TZ = timezone(timedelta(hours=8))
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
# 流式期前缀检测:`<invoke` 或 `<minimax:tool_call` 一出现就抑制 live 下发(逐 token 泄漏兜底)。
_XML_TOOLCALL_PREFIX_RE = re.compile(r"<\s*(?:invoke\b|/?\s*minimax:tool_call\b)", re.I)

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
    """模型把工具调用写成了 Markdown 文本(`Tool calls:\\n- <tool>`)而非结构化 tool_calls。

    判定:命中 "Tool calls:"/"工具调用:" 标题 **且** 文本里出现某个已注册工具名。
    仅在 `_extract_inline_tool_call`(带参数的可解析格式)已返回 None 后调用 —
    这种无参数清单格式解析不出参数,只能重提示重试。
    """
    if not content or not _TEXT_TOOLCALL_HEADER_RE.search(content):
        return False
    allowed = {t.get("function", {}).get("name") for t in (tools or [])}
    return any(n and n in content for n in allowed)


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


def _strip_xml_tool_markers(text: str) -> str:
    """Strip ``<invoke>…</invoke>`` blocks and orphan ``<minimax:tool_call>`` tags.

    重试用尽 / name 不在白名单 / 参数解析失败时的兜底:任何情况都不能把原始工具语法
    (含悬空无开标签的 ``</minimax:tool_call>``)留在用户可见正文里。镜像
    ``_strip_bracket_tool_markers`` 的便宜预检 + 剥离。
    """
    if not text:
        return text
    low = text.lower()
    if "<invoke" not in low and "minimax:tool_call" not in low:
        return text
    stripped = _INVOKE_STRIP_RE.sub("", text)
    stripped = _MINIMAX_TAG_STRIP_RE.sub("", stripped)
    return stripped.strip()


def _strip_reva_ui_from_llm_text(text: str) -> str:
    """剥掉 LLM 生成文本里伪造的 ```reva-ui``` 图表 block (确定性护栏, 防御纵深)。

    reva-ui block 只能由确定性 genui 短路产出; LLM 编的 block 数值全是假的 (R4 违规)。
    单一真源在 `app.services.genui.strip_reva_ui_blocks`。仅作用于 LLM 生成文本 ——
    短路自身产出的 block 走独立更早返回路径, 不经过此处。"""
    from app.services.genui import strip_reva_ui_blocks

    return strip_reva_ui_blocks(text)


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


def _loads_lenient(raw: str) -> Any:
    """标准 → 引号归一 → 截断修复 → 归一+修复,逐级兜底解析弱模型 JSON。

    任何一级成功即返回;全失败抛最后一个 JSONDecodeError(调用方决定如何处理)。
    """
    candidates = (
        raw,
        _normalize_json_quotes(raw),
        _repair_truncated_json(raw),
        _repair_truncated_json(_normalize_json_quotes(raw)),
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


def _extract_inline_tool_call(text: str, tools: List[Dict]) -> Optional[Dict[str, Any]]:
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

    # XML/`<invoke>` 格式先尝试:它以 `<` 开头,与 JSON(`{`)/括号(`(`)路径互不干扰。
    xml = _extract_xml_tool_call(raw, tools, allowed)
    if xml is not None:
        return xml

    # 括号格式先于 JSON 尝试:它含 `(` 不含起始 `{`,与 JSON 路径互不干扰。
    bracket = _extract_bracket_tool_call(raw, allowed)
    if bracket is not None:
        return bracket

    def _payload_to_tool_call(payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        fn = payload.get("function") if isinstance(payload.get("function"), dict) else None
        name = payload.get("name") or payload.get("tool") or (fn or {}).get("name")
        if name not in allowed:
            # 模型可能直接吐 record 的裸 data(无 name 包装,无 record_type)。
            # 按字段推断 record_type → 包成 health_record 调用,既写库又不泄漏 JSON。
            if "health_record" in allowed:
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
        for container_key in ("parameters", "params", "arguments", "input", "args"):
            if container_key in payload:
                args = payload[container_key]
                break
        if args is None:
            args = (fn or {}).get("arguments", {})
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
            return call

    # 兜底:整段就是一个被截断的 tool-call JSON(raw_decode 对每个 `{` 都失败)。
    # 从第一个 `{` 起做截断修复再解析一次 —— 救 glm-5.1 吐到一半被切断的调用。
    first = raw.find("{")
    if first != -1:
        try:
            payload = _loads_lenient(raw[first:])
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            return _payload_to_tool_call(payload)
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


def _fallback_text_from_tool_results(messages: List[Dict[str, Any]]) -> str:
    """Use the latest successful tool result when the model fails synthesis."""
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
            tool_message = payload.get("message")
            if isinstance(tool_message, str) and tool_message.strip():
                return tool_message.strip()

            for key in ("food_items", "summary", "preview"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return f"已完成记录：{value.strip()}"

            if payload.get("id") or payload.get("record_id"):
                return "已完成记录。"

        preview = content.replace("\n", " ").strip()
        if preview:
            return f"已完成操作：{preview[:120]}"

    return ""


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
    if last_assistant:
        prior = str(last_assistant.get("content") or "").strip()[:400]  # 截断,保持 compact
        user_content = f"[上一轮助手问我:{prior}]\n我的回复:{user_content}"

    return [
        {
            "role": "system",
            "content": (
                "你是健康记录工具路由器。用户要求记录、新增、修改、删除健康数据时，"
                "必须调用 health_record 或 health_manage 工具。不要做健康分析，"
                "不要输出长建议。若用户提到多条记录，尽量一次性发起多个 tool_call；"
                "信息不足时只用一句中文追问。"
                "**若用户的回复是对上一轮助手提问的简短确认/回应**(消息里带「[上一轮助手问我:…]」"
                "且回复是「记录」「好」「嗯」之类),结合上一轮助手的提问判断要记录什么,不要重新泛问。"
            ),
        },
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
        return f"已记录心情 {record.get('mood_score')}/10"
    # water
    if s("amount") is not None and "drink_type" in record:
        return f"已记录饮水 {record.get('amount')}ml"
    # reminder (/reminders/me)
    if s("title") is not None and ("remind_at" in record or "recurrence" in record):
        recurrence = str(record.get("recurrence") or "").strip().lower()
        prefix = "已设置每日提醒" if recurrence == "daily" else "已设置提醒"
        return f"{prefix}：{record.get('title')}"
    # illness episode
    if s("illness_name") is not None or (s("name") is not None and "start_date" in record):
        return f"已记录：{record.get('illness_name') or record.get('name')}"
    return "✅ 已记录"


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
        # Plain-text tool result (already human-readable) — show as-is.
        replies.append(content.replace("\n", " ")[:160])
        append_safety_warning()

    deduped: list[str] = []
    for reply in replies:
        if reply and reply not in deduped:
            deduped.append(reply)
    return "\n".join(deduped).strip()


def _auto_confirm_fast_record_args(
    tool_name: str, func_args: Any, channel: Optional[str] = None
) -> Any:
    """Skip the two-turn confirmation gate for pure fast-record requests.

    分级 + 分通道(channel 来自**客户端传输层声明**,绝不信 LLM 工具参数——
    对抗评审证伪过 arg-based 守卫:tool schema 无 source 字段,模型是该字段
    唯一可能作者=不可信):
    - AUTO 集(water/diet/...):任何通道直接写。
    - symptom/rhinitis:仅 channel=="typed"(打字,用户逐字敲的)免确认;
      语音/未声明通道(旧客户端、Siri 单轮无屏无法撤销)fail-closed 保留确认。
    - NEVER 集(medication/dose/financial/...)与 unknown kind:恒确认(fail-closed)。
    """

    if tool_name != "health_record":
        return func_args
    try:
        args = json.loads(func_args) if isinstance(func_args, str) else dict(func_args or {})
    except Exception:
        return func_args

    kind = _fast_record_kind(args)
    requires_confirmation = (
        kind not in _FAST_RECORD_AUTO_CONFIRM_KINDS
        or kind in _FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS
        or (kind in _TYPED_ONLY_AUTO_CONFIRM_KINDS and channel != "typed")
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
    # symptom/rhinitis:确认后置(回显+可撤销)替代确认前置 —— 记录可逆、
    # 非医疗级(≠用药/剂量),写错方向顶多 over-alarm(安全方向);缺
    # body_part/description 会 fail-loud 自然追问,不是复述式确认。
    # 每条症状都二次询问被用户明确否决(2026-07-02)。
    "symptom",
    "rhinitis",
}
# 症状类仅打字通道免确认;语音/未声明通道保留确认前置(转写失真 + Siri 单轮
# 无法撤销)。channel 由客户端传输层声明(AgentRequest.channel),绝不读 LLM
# 工具参数——对抗评审证伪过 arg-based 守卫(schema 无 source 字段,模型是该
# 字段唯一可能作者=不可信=生产死代码)。
_TYPED_ONLY_AUTO_CONFIRM_KINDS = {"symptom", "rhinitis"}


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


def _parse_time_only_to_next_beijing(raw: Any) -> Optional[str]:
    """Normalize a time-only reminder like 10:30 into the next Beijing datetime."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw if raw.tzinfo else raw.replace(tzinfo=BEIJING_TZ)
        return dt.astimezone(BEIJING_TZ).isoformat(timespec="seconds")

    s = str(raw).strip()
    if not s:
        return None

    # Full ISO datetime: keep it, adding Beijing tz when omitted.
    try:
        if re.search(r"\d{4}-\d{2}-\d{2}", s):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BEIJING_TZ)
            return dt.astimezone(BEIJING_TZ).isoformat(timespec="seconds")
    except ValueError:
        pass

    compact = (
        s.lower()
        .replace("：", ":")
        .replace("点半", ":30")
        .replace("点", ":")
        .replace("时", ":")
        .strip()
    )
    m = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", compact)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if hour > 23 or minute > 59:
        return None

    now = datetime.now(BEIJING_TZ)
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


def _normalize_reminder_record_data(data: dict) -> dict:
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
        or out.get("at")
    )
    if remind_at:
        out["remind_at"] = remind_at

    for key in ("alarm_time", "reminder_time", "time", "at", "repeat", "frequency", "confirmed", "confirm"):
        out.pop(key, None)
    return out


def _merge_agent_card_descriptors(*groups: list | None) -> list[dict]:
    out: list[dict] = []
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


_MEAL_TYPE_ZH = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}


def _summarize_record_data(kind: str, record_data: Any) -> str:
    """Build a clean human summary from the structured args the model wrote.

    `record_data` is the tool's `data` argument — structured and reliable — so it
    is a far safer source for the card than re-parsing the tool result string.
    Returns "" when nothing presentable can be built (caller suppresses the card).
    """
    if not isinstance(record_data, dict):
        return ""
    if kind == "diet":
        food = str(record_data.get("food_items") or record_data.get("food") or "").strip()
        meal = _MEAL_TYPE_ZH.get(str(record_data.get("meal_type") or "").strip().lower(), "")
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
            return f"{'已设置每日提醒' if recurrence == 'daily' else '已设置提醒'}：{title}"
    return ""


def _health_record_card_descriptor(record_type: Any, record_data: Any, result: str) -> Optional[dict]:
    """Build a deterministic chat card from a completed health_record tool.

    This is intentionally not model-generated UI. It mirrors the actual tool
    result so streaming cards cannot introduce new medical claims.
    """

    if not result or result.startswith("Error") or result.startswith("[NEEDS_CONFIRMATION]"):
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
    # 2) No usable message → synthesize from the structured args (never raw JSON).
    if not detail:
        detail = _summarize_record_data(kind, record_data)
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
) -> Optional[dict]:
    """Compatibility wrapper; implementation lives in post_record_quality.py."""
    return build_post_record_quality_response(
        record_type,
        record_data,
        result=result,
        personal_context=personal_context,
        db=db,
        user_id=user_id,
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
        "illness": "疾病/不适周期",
        "medication": "用药",
        "mood": "心情",
        "reminder": "提醒",
        "rhinitis": "鼻炎症状",
        "supplement_group": "补剂批量打卡",
        "symptom": "症状",
    }.get(rtype, f"{rtype} 记录")

    name = (
        data.get("description") or data.get("medication_name") or data.get("name")
        or data.get("illness_name") or data.get("title") or args.get("name")
    )
    if name:
        return f"{label}: {name}"
    return label


def _prepare_health_record_args_for_validation(tool_name: str, args: Any) -> Any:
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


# 工具 → 思考过程 status 事件里展示的**短**中文名 (mac 端"正在……"胶囊)。
# 与 _TOOL_TO_SOURCE_LABEL (数据源溯源, 更长) 独立: 这里要短、动词化。
# 未映射的工具 → 原始名 (见 _tool_status_label)。
_TOOL_TO_STATUS_LABEL = {
    "health_query": "查询健康数据",
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


_RECORD_INTENT_RE = re.compile(
    r"(记录|打卡|新增|录入|保存|吃了|喝了|服药|已服用|已吃|已喝|删除|修改|撤销|更新)"
)
# 疑问守卫:"我今天**喝了多少**水"/"**吃了什么**"是查询不是记录 —— record 动词(吃了/喝了)
# 命中但句子是疑问形态时,绝不能按记录意图走(否则确定性回复对查询回"✅ 已记录",
# 实测线上截图复现)。守卫只列把陈述翻成疑问的词,"记录喝水500ml"等真记录不受影响。
_RECORD_INTERROGATIVE_GUARD_RE = re.compile(
    r"(多少|什么|啥|哪些|哪个|几[个次杯步条克组天分]|有没有|是不是|多不多|够不够|吗|[??])"
)
_ADVICE_OR_ANALYSIS_RE = re.compile(
    r"(分析|解读|建议|方案|风险|评估|为什么|怎么|如何|基于|结合|补剂|叶酸|训练|运动|饮食方案|适合"
    r"|复盘|综合|趋势|规划|计划安排|该不该|要不要|值不值|意味着|说明什么)"
)
# 简单查询意图 — "我今天喝了多少水" / "查一下我的体重" / "最近血压是多少" 这类
# 单次取数回合。命中这些词但**不**命中 _ADVICE_OR_ANALYSIS_RE 时算 fast-eligible。
# 保守: 只列明确的取数动词/疑问词, 复盘/综合/趋势等已在 advice 正则里被排除。
_SIMPLE_QUERY_INTENT_RE = re.compile(
    r"(查一?下|查询|查看|看一?下|多少|几次|几步|有没有|是多少|多高|多重|多长|"
    r"今天|昨天|本周|这周|最近|昨晚|列出|显示|告诉我|我的.{0,6}(数据|记录|情况|状态))"
)


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
    text = message or ""
    if has_images or has_file:
        return False
    if _ADVICE_OR_ANALYSIS_RE.search(text):
        return False
    return bool(_RECORD_INTENT_RE.search(text) or _SIMPLE_QUERY_INTENT_RE.search(text))


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
    has_record_intent = bool(_RECORD_INTENT_RE.search(text))
    has_advice_intent = bool(_ADVICE_OR_ANALYSIS_RE.search(text))
    if has_record_intent and not has_advice_intent:
        return False
    return has_advice_intent


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


def _confirm_or_describe(args: dict, data: dict, *, preview: str) -> str | None:
    """L8 (Karpathy "verification is the bottleneck"):
    高确定性 health_record 写库前强制 LLM 复述给用户确认.

    第一次调用 (无 confirmed flag): 返回 [NEEDS_CONFIRMATION] 提示,
    不写库. LLM 看到提示会复述给用户, 用户答'是的' → LLM 重新调用 + confirmed=true.

    Args:
        args: tool_call 顶层参数
        data: args.data (会被 mutate — 剥掉 confirmed 字段防 DB schema 不识别)
        preview: 给 LLM 复述的"我准备记录: ..." 部分

    Returns:
        非 None: 当前不写库, 直接 return 这个字符串
        None  : 已确认, 调用方继续写库流程
    """
    confirmed = (
        args.get("confirmed") is True or args.get("confirm") is True
        or data.get("confirmed") is True or data.get("confirm") is True
    )
    # 写库前剥掉 confirmed, 防 DB schema 不识别
    data.pop("confirmed", None)
    data.pop("confirm", None)
    if confirmed:
        return None
    return (
        f"[NEEDS_CONFIRMATION] 我准备记录: {preview}. "
        f"请向用户复述并问一次'是这样吗？', "
        f"用户确认后**重新调用** health_record 并在 data 里加 confirmed=true."
    )


class AgentExecutor:
    """统一健康 Agent 执行器"""

    def __init__(self, db: Session):
        self.db = db
        self._current_user_id: Optional[int] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._request_model_id: Optional[str] = None
        self._turn_channel: Optional[str] = None
        self._prefer_fast_record_model = False
        # 本回合是否被 fast-route 到快模型 (简单记录/查询)。仅用于把答案 max_tokens
        # 从 ANSWER_MAX_TOKENS 收紧到 FAST_ROUTE_ANSWER_MAX_TOKENS —— 见 _answer_max_tokens。
        self._fast_route_simple_turn = False
        self._last_provider_model_name: Optional[str] = None
        self._request_model_tool_fallback_used = False
        self._model_fallback_reasons: List[str] = []
        self._tool_model_names: List[str] = []

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
        start_time = time.time()
        self._current_user_id = user_id
        self._prefer_fast_record_model = False
        self._last_provider_model_name = None
        self._model_fallback_reasons = []
        self._tool_model_names = []
        sources_used: list = ["多模型综合 (Claude Opus 4.7 · GPT-5.5 · Gemini 3.1 Pro)"]
        model_label = "Claude Opus 4.7 + GPT-5.5 + Gemini 3.1 Pro (综合)"

        from app.services.agent_conversation_service import AgentConversationService
        svc = AgentConversationService(self.db)
        conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)
        svc.save_message(conv.id, "user", message)

        yield {"event": "agent_start", "data": {"message": "多模型综合分析中…", "conversation_id": conv.id}}

        system_content = self._build_system_prompt(user_id, conv.id, user_auth_token)
        tools = get_health_tools()
        full_reply = ""

        def _progress(tool: str, text: str) -> Dict:
            return {"event": "tool_result", "data": {"tool": tool, "success": True, "preview": text, "result": text}}

        self._http_client = httpx.AsyncClient(timeout=90.0)
        try:
            # 1) Lead 回合 (带工具, Claude Opus 4.7)
            yield _progress("多模型·主分析", "Claude Opus 4.7 正在查数据/记录并分析…")
            self._request_model_id = MULTI_MODEL_LEAD_ID
            lead_messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": message},
            ]
            lead_text = ""
            for _round in range(MULTI_MODEL_MAX_LEAD_ROUNDS):
                resp = await self._call_llm(lead_messages, tools)
                tool_calls = resp.get("tool_calls") if isinstance(resp, dict) else None
                content = ((resp.get("content") if isinstance(resp, dict) else str(resp)) or "")
                if not tool_calls:
                    recovered = _extract_inline_tool_call(content, tools)
                    if recovered:
                        tool_calls = [recovered]
                        content = ""
                # 文本式工具调用(Tool calls:\n- xxx)无参数可解析 → 重提示结构化重试。
                if not tool_calls and _is_botched_text_tool_call(content, tools):
                    if _round < MULTI_MODEL_MAX_LEAD_ROUNDS - 1:
                        logger.warning("[agent_executor] 文本式工具调用(多模型路), 重提示重试. preview=%s", content[:120])
                        lead_messages.append({"role": "assistant", "content": content})
                        lead_messages.append({"role": "user", "content": (
                            "你刚才把工具调用写成了文本(例如 \"Tool calls:\\n- health_query\"),"
                            "并没有真正调用工具。请立刻用结构化 function calling 真正调用所需工具并带正确参数"
                            "(例如查看补剂库用 health_query 且 dimension=\"supplements\")。"
                        )})
                        continue
                    content = _strip_text_tool_call(content)
                if tool_calls:
                    lead_messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        fn = tc["function"]["name"]
                        fa = tc["function"]["arguments"]
                        result = await self._execute_tool(fn, fa, user_auth_token)
                        lead_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                        lbl = _TOOL_TO_SOURCE_LABEL.get(fn)
                        if lbl and lbl not in sources_used:
                            sources_used.append(lbl)
                        yield {"event": "tool_result", "data": {
                            "tool": fn, "success": not result.startswith("Error"),
                            "preview": result[:200], "result": result}}
                    continue
                # 兜底:内联标记(括号 / XML `<invoke>`)未恢复成 tool_call(name 不在白名单等)时,
                # 绝不能把裸工具语法当 lead 分析落进 final_text / 喂给下游多方分析。cheap-precheck no-op。
                content = _strip_bracket_tool_markers(content)
                content = _strip_xml_tool_markers(content)
                lead_text = content
                break

            data_ctx = _gathered_data_context(lead_messages)

            # 2) 两路独立分析 (GPT-5.5 + Gemini, 并发, 不带工具)
            yield _progress("多模型·多方", "GPT-5.5、Gemini 3.1 Pro 正在各自分析…")
            persp_system = (
                "你是资深健康分析师。基于给定的用户健康数据，独立、简洁地分析用户的问题"
                "（300-600 字）。只用给定数据，不要编造；没有数据时给出审慎的一般性建议。"
            )
            persp_user = (
                f"用户问题：{message}\n\n已查到的用户健康数据：\n"
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
                final_text = lead_text or "多模型综合分析未能生成最终结论，请重试或改用单模型。"

            if not final_text.strip():
                final_text = lead_text or "多模型综合分析未能生成最终结论，请重试。"
            for i in range(0, len(final_text), 24):
                yield {"event": "token", "data": {"content": final_text[i:i + 24]}}
            full_reply = final_text
        except Exception as e:  # noqa: BLE001
            logger.error("多模型综合执行异常: %s", e, exc_info=True)
            full_reply = f"多模型综合分析遇到问题: {e}"
            yield {"event": "token", "data": {"content": full_reply}}
        finally:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

        # 确定性护栏 (R4): 多模型综合是 LLM 生成文本 → 剥掉任何伪造的 reva-ui block。
        full_reply = _strip_reva_ui_from_llm_text(full_reply)
        ai_msg = svc.save_message(conv.id, "assistant", full_reply)
        conv.updated_at = datetime.now(UTC)
        elapsed_ms = int((time.time() - start_time) * 1000)
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
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[multi_model] write meta 失败: %s", e)
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
    ) -> AsyncGenerator[Dict, None]:
        """运行 Agent 循环，SSE 流式输出"""
        from app.services.llm.usage_tracker import set_caller
        set_caller("agent_executor.run_stream", user_id=user_id)
        # 2026-07-05 P0-1: 流式进度事件 —— 流一打开立刻发 accepted (任何 LLM/会话
        # 组装之前, 目标 <100ms)。纯附加, 让客户端首 token 前 8s 有确定性反馈。
        # 多模型分支也在此点之后, 所以 accepted 恒为任何路径的第一个 wire 事件。
        yield self._progress_event("accepted")
        # 输入通道(客户端传输层声明,typed/voice/siri):症状类记录的确认策略依赖它。
        # 非法/未声明一律 None → fail-closed(症状保留确认)。
        self._turn_channel = channel if channel in ("typed", "voice", "siri") else None
        # 多模型综合分析 (商用三强 panel)。仅纯文本分析回合走此路径;
        # 带图片/附件时回退普通单模型路径 (panel 是文本综合, 不处理多模态)。
        if _extract_multi_model_flag(extra_context) and not images and not file_base64:
            async for evt in self._run_multi_model_stream(
                user_id, message, conversation_id, user_auth_token, extra_context
            ):
                yield evt
            return

        start_time = time.time()
        self._current_user_id = user_id
        self._request_model_id = _extract_model_id_from_extra_context(extra_context)
        self._request_model_tool_fallback_used = False
        self._fast_route_simple_turn = False
        self._model_fallback_reasons = []
        self._tool_model_names = []
        self._prefer_fast_record_model = (
            not images
            and not file_base64
            and bool(_RECORD_INTENT_RE.search(message or ""))
            and not bool(_ADVICE_OR_ANALYSIS_RE.search(message or ""))
            # 疑问句("喝了多少水"/"吃了什么")= 查询,不是记录 —— 见守卫正则注释。
            and not bool(_RECORD_INTERROGATIVE_GUARD_RE.search(message or ""))
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
                        "[agent_executor] fast-route simple turn user=%s model=%s msg=%r",
                        user_id, fast_id, (message or "")[:60],
                    )
            except Exception as e:  # noqa: BLE001 — 快路由失败绝不断主链路, 退回默认模型
                logger.warning("[agent_executor] fast-route failed, keep default: %s", e)
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
        conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)

        # 保存用户消息（含图片标记）
        user_content = message
        saved_image_urls: List[str] = []
        if images:
            user_content += f"\n[附图: {len(images)}张]"
            for img in images:
                url = self._upload_chat_image(img["base64"], img.get("type", "jpeg"))
                if url:
                    saved_image_urls.append(url)
        if file_base64 and file_name:
            user_content += f"\n[附件: {file_name}]"
        image_url_value = json.dumps(saved_image_urls) if saved_image_urls else None
        svc.save_message(conv.id, "user", user_content, image_url=image_url_value)
        pre_stages["conv_ms"] = _pre_stage(_t_stage)

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
            user_id, conv.id, user_auth_token, lite=self._fast_route_simple_turn
        )
        pre_stages["system_prompt_ms"] = _pre_stage(_t_stage)
        if self._fast_route_simple_turn:
            # 可观测性: 记录 lite prompt 的实际字符数, 用来看 prefill 削减 (对比 full)。
            logger.info(
                "[agent_executor] fast-route lite system prompt user=%s chars=%d",
                user_id, len(system_content),
            )
        if opener_quick_reply_note:
            system_content += (
                "\n\n## 入口动作处理结果\n"
                f"{opener_quick_reply_note}\n"
                "请先用一句话确认这次验证/反馈已经接上了对应行动卡片，再给出下一步。"
            )
            if "ActionCard" not in sources_used:
                sources_used.append("ActionCard")
        desktop_response_instruction = _extract_desktop_response_instruction(extra_context)
        if desktop_response_instruction:
            system_content += (
                "\n\n## 桌面端回复格式要求\n"
                f"{desktop_response_instruction}\n"
                "这是桌面端展示的最高优先级格式要求；除非用户明确要求纯文本，否则必须遵守。"
            )
        # 入口 deeplink 携带的结构化上下文 — 用户在 SNP/饮食/运动等页点"详细聊"时,
        # 把当前页正展示的具体方案条目透传过来, 让 LLM 不重新猜, 在已有方案上深化.
        if extra_context and extra_context.strip():
            system_content += (
                "\n\n## 入口上下文 (用户正在看的具体方案)\n"
                "用户从下面这个上下文点过来跟你详细聊, 请在**这些已展示的具体条目**上深化, "
                "不要重新生成方案; 引用条目名称时跟用户已看见的一致.\n"
                f"```\n{extra_context.strip()[:4000]}\n```"
            )
        _t_stage = time.time()
        # fast-routed 简单回合跳过系统知识库检索: KB claim 是给分析/解读用的依据,
        # 对「今天喝了多少水」无用, 且检索本身占 pre-first-token 壁钟 (kb_ms)。
        system_kb_context = (
            "" if self._fast_route_simple_turn
            else self._build_system_knowledge_prompt_context(user_id, message)
        )
        pre_stages["kb_ms"] = _pre_stage(_t_stage)
        if system_kb_context:
            system_content += f"\n\n{system_kb_context}"
            if "系统知识库" not in sources_used:
                sources_used.append("系统知识库")
        # 2026-05-14: 用户数据源 inspection — 不依赖 system_prompt 实际用了什么,
        # 直接 SQL count 用户哪些表有数据, 给"AI 用了什么数据"chip 用.
        _t_stage = time.time()
        try:
            sources_used.extend(_inspect_user_data_sources(self.db, user_id))
        except Exception as e:
            logger.warning(f"[sources_used] inspect failed: {e}")
        pre_stages["inspect_ms"] = _pre_stage(_t_stage)

        # 3. 构建对话历史
        _t_stage = time.time()
        messages = svc.build_messages(conv.id, limit=15)
        # 确定性护栏 (R4): 历史里助手消息带过 ```reva-ui``` 图表 block —— 若原样喂回
        # LLM, 它会**模仿**这个格式并**编造**图表数据 (实测: 编 "Apple Watch + Garmin +
        # RingConn 多源合并")。把历史助手消息里的 block 换成占位符, LLM 无从模仿。
        # (确定性短路自身产出的 block 走独立更早返回的路径, 不经此处 → 不受影响。)
        for _m in messages:
            if _m.get("role") == "assistant" and _m.get("content"):
                _m["content"] = _placeholder_reva_ui_in_history(_m["content"])
        messages.insert(0, {"role": "system", "content": system_content})
        pre_stages["history_ms"] = _pre_stage(_t_stage)

        # 如果有图片：LangBridge 商用模型自身支持多模态，必须直接传原图；
        # 其它模型保留原来的"先用独立 vision 识别，再降级直传"路径。
        _t_stage = time.time()
        if images:
            should_send_raw_images = self._should_send_raw_images_to_primary_model(user_id)
            vision_description = None
            if not should_send_raw_images:
                # 真实思考过程: 图片/视觉预处理 (4–20s 的 vision_ms 块) 即将开始。
                # 仅在会真的跑独立 vision 预处理时发 (原图直传多模态模型时无此阶段)。
                yield self._status_event("vision", detail=None)
                vision_description = await self._try_import_medical_report_images(user_id, images)
                if not vision_description:
                    vision_description = await self._analyze_image_with_vision(message, images)

            if vision_description:
                enriched_message = f"{message}\n\n[图片识别结果]: {vision_description}"
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i]["content"] = enriched_message
                        break
                logger.info(f"[Vision] 图片识别完成: {vision_description[:200]}")
            else:
                _attach_images_to_last_user_message(messages, message, images)
        pre_stages["vision_ms"] = _pre_stage(_t_stage) if images else 0

        # pre_llm_ms: system-prompt 组装 + KB 检索 + history + vision 到本点的总壁钟。
        # 直接取 start_time delta (最准, 不受漏计阶段影响)。fail-soft。
        try:
            pre_llm_ms = int((time.time() - start_time) * 1000)
        except Exception:  # noqa: BLE001
            pre_llm_ms = 0

        # 4. 工具定义
        tools = get_health_tools()

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
        # 后置校验: record 意图的 turn 必须真的执行了写工具。0 次 = 模型可能只是
        # 嘴上说"已记录"却没调工具(弱模型把 tool-call 当正文吐出 → 静默丢数据)。
        tool_executed_count = 0
        # 本轮 agent 实际调用过的工具/Skill 名, 去重、按首次调用顺序。供 mac/mobile
        # 展示"调用了哪些 Skills"。与 sources_used (引用了哪些数据源) 独立。
        tools_used: List[str] = []

        # 诚实的非流式 UX: 若本回合答案模型结构性非流式 (langbridge 商用模型, 上游无 SSE,
        # 整段一次返回), mac 端「正在思考…」的 token 滚动是误导 —— 在每轮 LLM 调用前多发一条
        # thinking 状态, 带 detail「整段生成, 需等待完整回答」, mac 会原样显示该 detail。
        # 流式模型 detail 恒为 None (不发此附加事件), mac 走正常滚动。fail-soft (解析异常=不发)。
        answer_model_non_streaming = self._resolved_answer_model_is_non_streaming()

        self._http_client = httpx.AsyncClient(timeout=90.0)
        try:
            for round_idx in range(MAX_TOOL_ROUNDS):
                # 真流式调用 LLM：content delta 实时 yield 给客户端,同时累积 tool_calls。
                # _call_llm_stream 内部已做 provider 路由 + failover (镜像 _call_llm)。
                round_tools = (
                    []
                    if self._should_synthesize_with_requested_model_after_tools(tool_executed_count)
                    else tools
                )
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
                _round_start = time.time()
                streamed_text = ""
                streamed_tool_calls: List[Dict[str, Any]] = []
                stream_finish_reason: Optional[str] = None
                streamed_to_client = False
                # 弱模型会把 tool-call JSON 当正文吐出(无结构化 tool_calls)。一旦累积
                # 文本可被 _extract_inline_tool_call 识别成工具调用,立刻停止 live 下发
                # 并撤回已发标记 —— 这段 JSON 后面会被恢复成真正的 tool_call (content 置空),
                # 绝不能泄漏给用户。结构化 tool_calls 的正常模型不受影响。
                inline_suppressed = False
                async for evt in self._call_llm_stream(messages, round_tools):
                    etype = evt.get("type")
                    if etype == "content":
                        delta = evt.get("text") or ""
                        if not delta:
                            continue
                        streamed_text += delta
                        if (
                            not inline_suppressed
                            and not streamed_tool_calls
                            and round_tools
                            and (
                                _extract_inline_tool_call(streamed_text, round_tools)
                                # 括号标记 `[工具调用: ...` 可能正在逐 token 形成,`)` 还没到
                                # → 上面的精确解析此刻 match 不到。一旦看到标记前缀就提前抑制,
                                # 避免裸标记被逐 delta 泄漏(即便最终参数解析不出也不外漏)。
                                or "工具调用" in streamed_text
                                # Markdown 清单式 "Tool calls:" 同样抑制(英文标记)。
                                or _TEXT_TOOLCALL_PREFIX_RE.search(streamed_text)
                                # XML `<invoke ...` / `<minimax:tool_call>` 逐 token 形成中,
                                # `</invoke>` 闭标签还没到 → 精确解析 match 不到。见到前缀即抑制。
                                or _XML_TOOLCALL_PREFIX_RE.search(streamed_text)
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
                        if not inline_suppressed:
                            streamed_to_client = True
                            # 2026-07-01: TTFT — 第一个真正下发给客户端的 token 时刻 (纯埋点)。
                            if first_token_at is None:
                                first_token_at = time.time()
                            # 真流式:逐 delta 即时下发,不再切 20-char 假块。
                            yield {"event": "token", "data": {"content": delta}}
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
                logger.info(f"LLM response type={type(response).__name__}, is_dict={isinstance(response, dict)}, has_tool_calls={isinstance(response, dict) and bool(response.get('tool_calls'))}, preview={str(response)[:200]}")

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
                        else _extract_inline_tool_call(_resp_content, round_tools)
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
                    and _is_botched_text_tool_call(response.get("content") or "", round_tools)
                ):
                    botched = response.get("content") or ""
                    if round_idx < MAX_TOOL_ROUNDS - 1:
                        logger.warning(
                            "[agent_executor] 文本式工具调用未结构化, 重提示重试 (round %d). preview=%s",
                            round_idx + 1, botched[:120],
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

                # 检查是否有 tool_call
                if isinstance(response, dict) and response.get("tool_calls"):
                    self._record_tool_model_name(self._last_provider_model_name or model_name)
                    tool_calls = response["tool_calls"]
                    text_content = response.get("content") or ""

                    # 思考过程: 真流式下已逐 delta 下发过, 这里只补 full_reply,
                    # 不重复 yield token (避免客户端看到双份)。inline-recovery 路径
                    # 会把 content 置空 → text_content 为空也不发。
                    if text_content:
                        if not streamed_to_client:
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
                                func_name, func_args, channel=self._turn_channel
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
                        _is_orch_tool = False
                        try:
                            if func_name == "health_analysis":
                                _parsed = json.loads(func_args) if isinstance(func_args, str) else func_args
                                _is_orch_tool = (
                                    isinstance(_parsed, dict)
                                    and _parsed.get("analysis_type") == "orchestrator"
                                )
                        except Exception:  # noqa: BLE001
                            _is_orch_tool = False
                        _tool_call_start = time.time()
                        result = await self._execute_tool(
                            func_name, func_args, user_auth_token
                        )
                        if _is_orch_tool:
                            try:
                                orchestrator_tool_ms = int((time.time() - _tool_call_start) * 1000)
                            except Exception:  # noqa: BLE001
                                orchestrator_tool_ms = None
                            try:
                                _orch_json = json.loads(result) if isinstance(result, str) else None
                                if isinstance(_orch_json, dict) and _orch_json.get("perf") is not None:
                                    orchestrator_perf = _orch_json.get("perf")
                            except Exception:  # noqa: BLE001
                                pass
                        result_for_record_card = result
                        safety_cards: list[dict] = []
                        tool_executed_count += 1

                        # 写操作成功后内联安全检查。
                        # 注意: 软失败(如"未找到…"/"暂时没成功")不含 "Error" 字样, 旧逻辑会把
                        # 无关的安全告警拼到一条失败回复上(截图里"未找到活跃药物 ⚠️夜间血氧…"),
                        # 故显式排除软失败。
                        _soft_fail = any(m in result for m in ("未找到", "暂时没成功", "没成功", "记录失败"))
                        if (
                            func_name == "health_record"
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
                                logger.warning(f"Safety check after write failed: {e}")

                        # 追加 tool_result 到 messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result,
                        })

                        # tool_result 事件给前端用. health_record 时附 args 让前端能识别
                        # 是哪种 record + 提取关键内容显示 summary 卡 (I Phase 2).
                        tool_event_data = {
                            "tool": func_name,
                            "success": not result.startswith("Error"),
                            "preview": result[:200],
                            "result": result,
                        }
                        record_card = None
                        quality_cards: list[dict] = []
                        if func_name == "health_record":
                            try:
                                parsed_args = json.loads(func_args) if isinstance(func_args, str) else func_args
                                tool_event_data["record_type"] = parsed_args.get("record_type")
                                tool_event_data["record_data"] = parsed_args.get("data") or {}
                                quality_response = _post_record_quality_response(
                                    tool_event_data["record_type"],
                                    tool_event_data["record_data"],
                                    result_for_record_card,
                                    personal_context=system_content,
                                    db=self.db,
                                    user_id=user_id,
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
                                    )
                            except Exception:
                                pass

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

                    # 硬门(诚实不变量):确定性"已记录…"回复只允许在本轮**真的执行过写工具**
                    # 后出现 —— 只读工具(health_query 等)成功≠写入,谎报"已记录"比慢更糟。
                    # 非写回合 fall through 到 continue,让下一轮 LLM 用工具结果作答。
                    _round_executed_write_tool = any(
                        t in ("health_record", "health_manage") for t in _round_tool_names
                    )
                    if self._prefer_fast_record_model and _round_executed_write_tool:
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
                            for i in range(0, len(final_text), 20):
                                chunk = final_text[i:i + 20]
                                yield {"event": "token", "data": {"content": chunk}}
                            full_reply += final_text
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
                        # 按本轮实际执行过的工具选兜底口径:有写工具 → "已记录…";
                        # 只读回合 → 查询味自然语言(绝不能对查询谎报"✅ 已记录")。
                        _turn_had_write_tool = any(
                            t in ("health_record", "health_manage") for t in (tools_used or [])
                        )
                        if _turn_had_write_tool:
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
                            final_text = _fallback_text_from_tool_results(messages)
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
                    if streamed_to_client and final_text.startswith(streamed_text):
                        # 正文已实时下发,只补 interrupted notice 等未流式的后缀。
                        tail = final_text[len(streamed_text):]
                        if tail:
                            if first_token_at is None:
                                first_token_at = time.time()
                            yield {"event": "token", "data": {"content": tail}}
                    else:
                        # 重试/兜底产生的新文本 (非流式来源) → 一次性下发。
                        if final_text:
                            if first_token_at is None:
                                first_token_at = time.time()
                            yield {"event": "token", "data": {"content": final_text}}
                    full_reply += final_text
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
                for i in range(0, len(final_text), 20):
                    chunk = final_text[i:i + 20]
                    yield {"event": "token", "data": {"content": chunk}}
                full_reply += final_text

        except Exception as e:
            logger.error(f"Agent 执行异常: {e}", exc_info=True)
            error_msg = safe_llm_error_message(e)
            yield {"event": "token", "data": {"content": error_msg}}
            full_reply = error_msg
            final_finish_reason = "error"
        finally:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

        # 6. 保存回复
        # 确定性护栏 (R4, 防御纵深): full_reply 是 LLM 生成文本 —— 剥掉任何伪造的
        # reva-ui 图表 block (数值只能来自确定性 genui 短路; 短路走独立路径不经此处)。
        full_reply = _strip_reva_ui_from_llm_text(full_reply)
        ai_msg = svc.save_message(conv.id, "assistant", full_reply)
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
        answer_model = model_name
        selected_model = self._display_model_name_for_id(self._request_model_id) or answer_model
        tool_models = list(self._tool_model_names)
        fallback_reasons = list(self._model_fallback_reasons)
        evidence_cards = []
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
        response_cards = _merge_agent_card_descriptors(streamed_cards, evidence_cards)

        # 后置校验 (#3 护栏): record 意图的 turn 却 0 次工具执行 = 很可能模型只是嘴上
        # 说"已记录"但没真写库(弱模型把 tool-call JSON 当正文吐出、提取失败的静默丢数据)。
        # 把这种"假装成功"从不可见变成 WARNING 日志 + message.meta 标记, 可被监控/告警捕获。
        record_intent_no_tool = bool(
            self._prefer_fast_record_model and tool_executed_count == 0
        )
        if record_intent_no_tool:
            logger.warning(
                "[agent_executor] RECORD INTENT but 0 tools executed — possible silent "
                "data loss (model may have claimed success without writing). user=%s msg=%r",
                user_id,
                (message or "")[:80],
            )

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
                "cards": response_cards,
                "finish_reason": final_finish_reason,
                "completion_status": completion_status,
                "record_intent_no_tool": record_intent_no_tool,
                "perf": perf,
            }
        except Exception as e:
            logger.warning(f"[agent_executor] write meta 失败: {e}")
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
                "mode": "agent",
                "cards": response_cards,
                "finish_reason": final_finish_reason,
                "completion_status": completion_status,
                "record_intent_no_tool": record_intent_no_tool,
                "perf": perf,
            },
        }

    @staticmethod
    def _upload_chat_image(image_base64: str, image_type: str) -> Optional[str]:
        from app.services.chat_utils import upload_chat_image
        return upload_chat_image(image_base64, image_type)

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

    def _build_system_prompt(
        self, user_id: int, conv_id: int, user_auth_token: Optional[str], lite: bool = False
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
            "- **新增记录**调用 health_record；**修改/删除已有记录**必须调用 health_manage。不要说'没有删除功能'。",
            "- 用户要删除重复记录时: 先 health_manage(list) 或 health_query(diet) 查候选 ID；如果用户已明确 ID, 直接 health_manage(delete)。",
            "- 用户说'删除这一餐'、'撤销这顿'、'我刚才不小心删除了'、'把晚餐删掉/恢复'时,这是管理已有饮食记录,绝不能把这句话作为 diet.food_items 新增一条晚餐;先查候选记录并确认。",
            "- 饮水、补剂打卡：直接执行，不需确认",
            "- 血压、血糖、体重：执行后复述确认数值（'已记录血压 138/92'）",
            "- 用户说'吃了/服用了XX'：若包含药名、药物剂型(胶囊/缓释片/颗粒/口服液等)、mg/毫克、处方/用药语境 → record_type=medication；补剂/保健品名(鱼油/维C/B族等) → record_type=supplement；明确食物或餐次 → record_type=diet",
            "- 用户说'早上的药都吃了' → record_type=supplement_group, timing=morning",
            "- 用户明确要设置提醒/闹钟/每天几点提醒,且已给出时间 → 调用 health_record(record_type=reminder, data={title,message,remind_at,recurrence})。每日提醒用 recurrence=daily; remind_at 必须是带 +08:00 的 ISO 时间; 只有 HH:MM 时按下一次北京时间生成。不能回复“系统接口限制”或让用户自己去手机/手表设置。",
            "- 如果上一轮已在问'几点提醒',用户只回复'10:30'这类时间,要继承上一轮任务标题和内容,直接创建 reminder; 不要丢失上下文。",
            "- 模糊数量：'几杯水' → 追问具体杯数再记录；'130多' → 追问具体数值",
            "- 时间归属：'昨天' → 记到昨天日期；'刚才' → 当前时间；未说明 → 今天",
            "- 图片：用户发食物照片时，先用你的视觉能力识别图片中的食物名称和份量，然后调用 health_record(type=diet, data={meal_type, food_items, calories, protein, carbs, fat, fiber, record_date}) 记录。必须在 data 中填写完整的 food_items 字符串，不能传空 data。",
            "- **饮食记录必须包含热量和营养估算：识别食物后，根据食物种类和常见份量估算总热量(kcal)、蛋白质(g)、碳水(g)、脂肪(g)、膳食纤维(g)，填入 data.calories/protein/carbs/fat/fiber 字段一起保存。不要记完再问用户'要不要算热量'。**",
            "- **重要：调用 health_record 时 data 参数必须包含具体内容，不能为空对象 {}。如果你不确定内容，先问用户再记录。**",
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
            "- 中文回复：简洁实用，给出可执行的建议",
            "- 严重异常（HRV持续偏低、SpO2<92%、血压异常）→ 建议就医",
            "- 涉及药物的建议：附加'请咨询医生'免责声明",
            "",
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
            "## 安全与边界 (R4 — 必须严格遵守)",
            "- 解读异常指标/给健康建议时,先调用 knowledge_search 取依据;无命中就如实说明依据来自通用知识,**绝不编造引用或具体研究**。",
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
        if not lite:
            try:
                from app.services.gene_rules_registry import get_registry
                gene_section = get_registry().system_prompt_section(user_phenotypes=None)
                if gene_section:
                    parts.append("\n" + gene_section)
            except Exception:
                pass

        # 注入健康上下文 (lite 与 full 都注入 —— 基础画像是记录/查询也需要的最小上下文)
        try:
            from app.services.health_context_lite_service import (
                build_lite_health_context, _get_time_period,
            )
            health_ctx = build_lite_health_context(self.db, user_id)
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
        if not lite:
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

            # 注入记忆
            try:
                from app.services.conversation_memory_service import get_relevant_memories
                memories = get_relevant_memories(self.db, user_id, limit=5)
                if memories:
                    parts.append("\n## 用户记忆")
                    parts.append(memories)
            except Exception:
                pass

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
        """Return the system-KB evidence card for this chat turn.

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
            # Cached Twin can be stale immediately after upload/import and then
            # the system KB evidence block silently disappears.
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
        """
        provider = None
        # 本回合最终会用到的 model_id (仅在能确定时填), 供工具能力门控判定。
        effective_model_id: Optional[str] = None

        # Mac/桌面端手动路由: extra_context.model_id 是 model_registry 里的 id,
        # 只影响本次请求, 不改 user_profile 持久偏好.
        if provider is None and self._request_model_id:
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

        # ──── 工具调用能力门控 (从源头减少弱模型吐坏工具调用; #147/#161 兜底解析仍在) ────
        # 仅当本回合确实要传 tools 且已确定的 effective_model 不可靠时, 才换一个可靠模型。
        # 拿不准 (effective_model_id=None / 未注册) → 保守不动, 依赖兜底解析。
        # fast-record 只压缩 prompt / 自动确认, 不再偷偷切模型。为避免用户显式选择的
        # 模型又被工具门控改掉, 该路径继续依赖 #147/#161 的兜底解析。
        if pass_tools and not self._prefer_fast_record_model:
            gated = self._gate_tool_provider(effective_model_id)
            if gated is not None:
                provider = gated

        return provider, pass_tools

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
        """若 effective_model 做工具调用不可靠, 返回一个可靠模型的 provider; 否则 None。

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
        return provider

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
        chat_kwargs = {
            "messages": messages,
            "model": None,
            "temperature": 0.3,
            "max_tokens": ANSWER_MAX_TOKENS,
            "stream": False,
            "return_metadata": True,
        }
        if pass_tools:
            chat_kwargs["tools"] = pass_tools
        if self._prefer_fast_record_model:
            chat_kwargs["messages"] = _build_fast_record_messages(messages)
        self._last_provider_model_name = (
            getattr(provider, "model", None)
            or getattr(provider, "default_model", None)
            or getattr(provider, "provider_name", None)
        )
        try:
            return await provider.chat(**chat_kwargs)
        except Exception as e:  # noqa: BLE001
            # 选定 provider 报错 → 回退到稳定的 tool-capable provider (tokenplan)。
            # 典型场景:langbridge 商用网关(GPT-5.5 等)的浏览器适配器只支持流式,
            # 不实现非流式 tool-calling chat() → 返回 500 "adapter has no chat() method"。
            # 不回退的话用户一选商用模型整个 agent 就不可用。二次失败再抛给上层兜底。
            logger.warning(
                "[agent_executor] 选定 provider chat() 失败,回退 tokenplan: %s", e
            )
            if pass_tools and self._request_model_id:
                self._request_model_tool_fallback_used = True
                self._record_model_fallback_reason("selected_model_tool_chat_failed")
            from app.services.llm.factory import create_llm_provider
            from app.services.llm.pii_scrub import wrap_provider_pii_scrub
            from app.services.llm.usage_tracker import wrap_provider
            fb = wrap_provider_pii_scrub(wrap_provider(create_llm_provider("tokenplan")))
            self._last_provider_model_name = getattr(fb, "model", None) or "tokenplan(fallback)"
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
        stream_kwargs: Dict[str, Any] = {
            "messages": _build_fast_record_messages(messages)
            if self._prefer_fast_record_model else messages,
            "model": None,
            "temperature": 0.3,
            # fast-routed 简单回合把答案 token 收紧到 2000 (长尾解码是延迟一部分),
            # 其它回合保持 8000。见 _answer_max_tokens。
            "max_tokens": self._answer_max_tokens(),
        }
        if pass_tools:
            stream_kwargs["tools"] = pass_tools
        self._last_provider_model_name = (
            getattr(provider, "model", None)
            or getattr(provider, "default_model", None)
            or getattr(provider, "provider_name", None)
        )

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
            # 流开始前/未发任何内容就报错 → 回退稳定的 tokenplan provider (镜像 _call_llm)。
            logger.warning(
                "[agent_executor] 选定 provider chat_stream() 失败,回退 tokenplan: %s", e
            )
            if pass_tools and self._request_model_id:
                self._request_model_tool_fallback_used = True
                self._record_model_fallback_reason("selected_model_tool_stream_failed")
            from app.services.llm.factory import create_llm_provider
            from app.services.llm.pii_scrub import wrap_provider_pii_scrub
            from app.services.llm.usage_tracker import wrap_provider
            fb = wrap_provider_pii_scrub(wrap_provider(create_llm_provider("tokenplan")))
            self._last_provider_model_name = getattr(fb, "model", None) or "tokenplan(fallback)"
            async for evt in fb.chat_stream(**stream_kwargs):
                yield evt

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
        if not settings.llm_vision_base_url or not settings.llm_vision_api_key:
            return None

        vision_model = settings.llm_vision_model or "qwen-vl-max"
        vision_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": (
                "你是一个食物识别助手。用户会发送食物照片，请你：\n"
                "1. 识别图片中所有食物的名称和大致份量\n"
                "2. 估算每种食物的热量(kcal)\n"
                "3. 估算这顿饭的总热量\n"
                "用简洁的中文回复，格式如：三文鱼150g(约250kcal)、黑米饭200g(约230kcal)、蔬菜100g(约30kcal)，总计约510kcal。"
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
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                logger.warning(f"[Vision] 图片分析失败: HTTP {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"[Vision] 图片分析异常: {e}")
            return None

    async def _try_import_medical_report_images(self, user_id: int, images: List[dict]) -> Optional[str]:
        """Detect lab-report images in chat, persist recognized indicators, and summarize.

        The normal chat image path used to describe photos for diet logging only.
        Lab screenshots therefore informed one answer but never reached the
        canonical MedicalIndicator timeline. This hook keeps report ingestion
        protocol-first: OCR returns structured items, then the same importer used
        by upload endpoints writes MedicalExam + MedicalIndicator.
        """
        if not images:
            return None
        try:
            from app.services.ai.medical_report_ocr import recognize_medical_report
            from app.services.data_collection.medical_exam_import import MedicalExamImportService
            from app.twin.cache import invalidate_twin

            imported = []
            for img in images:
                result = await recognize_medical_report(
                    img["base64"],
                    image_type=img.get("type", "jpeg"),
                )
                items = result.get("items") if isinstance(result, dict) else None
                if not items or len(items) < 2:
                    continue
                exam_date = None
                if result.get("report_date"):
                    try:
                        exam_date = parse_date_value = datetime.strptime(str(result["report_date"])[:10], "%Y-%m-%d").date()
                    except Exception:
                        parse_date_value = None
                    exam_date = parse_date_value
                exam = MedicalExamImportService.import_from_items(
                    self.db,
                    user_id=user_id,
                    items_data=items,
                    exam_date=exam_date or datetime.now(BEIJING_TZ).date(),
                    exam_type=result.get("report_type") or "medical_report",
                    hospital_name=result.get("institution"),
                    notes="从聊天图片 OCR 自动导入",
                    source="agent_image_ocr",
                )
                imported.append((exam, result, items))

            if not imported:
                return None

            try:
                invalidate_twin(user_id)
            except Exception:
                pass

            total_items = sum(len(items) for _exam, _result, items in imported)
            abnormal_items = [
                item
                for _exam, _result, items in imported
                for item in items
                if item.get("is_abnormal")
            ]
            abnormal_text = "；".join(
                f"{item.get('name') or item.get('item_name') or item.get('name_en')} {item.get('value')} {item.get('unit') or ''}".strip()
                for item in abnormal_items[:8]
            )
            exam_ids = ", ".join(str(exam.id) for exam, _result, _items in imported)
            note = f"已将图片中的 {total_items} 项化验指标写入系统，体检记录 ID: {exam_ids}。"
            if abnormal_text:
                note += f" 识别到异常/标记项：{abnormal_text}。"
            return note
        except Exception as e:
            logger.warning(f"[Vision] 医疗报告图片自动入库失败: {e}", exc_info=True)
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    async def _execute_tool(
        self, tool_name: str, args_raw: Any, user_token: Optional[str]
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
                    logger.warning(
                        "[_execute_tool] %s args 解析失败(含引号归一+截断修复后): %s",
                        tool_name, args_raw[:200],
                    )
                    return f"Error: 参数解析失败: {args_raw}"
            else:
                return f"Error: 参数解析失败: {args_raw}"

        # === 统一 tool_call 守门 (所有 6 个工具必过) ===
        # 日期/数值/枚举/引用 ID 存在性/越权 / 必填 — 触发 coerce 只 log,
        # 必填缺失或越权才返回 error 给 LLM (它会重试).
        from app.services.llm.tool_validator import validate_tool_call
        args = _prepare_health_record_args_for_validation(tool_name, args)
        v = validate_tool_call(tool_name, args, db=self.db, user_id=self._current_user_id)
        if v["error"]:
            return v["error"]
        args = v["data"]

        base_url = settings.health_api_base_url or "http://localhost:8000/api/v1"
        headers = {"Authorization": f"Bearer {user_token}"} if user_token else {}

        try:
            if tool_name == "health_query":
                result = await self._exec_health_query(base_url, headers, args)
                return annotate_if_implausible(result)
            elif tool_name == "health_record":
                return await self._exec_health_record(base_url, headers, args)
            elif tool_name == "health_manage":
                return await self._exec_health_manage(base_url, headers, args)
            elif tool_name == "health_analysis":
                result = await self._exec_health_analysis(base_url, headers, args)
                return annotate_if_implausible(result)
            elif tool_name == "knowledge_search":
                return await self._exec_knowledge_search(args)
            elif tool_name == "realtime_search":
                return await self._exec_realtime_search(args)
            elif tool_name == "environment_check":
                return await self._exec_environment(base_url, headers, args)
            elif tool_name == "supplement_guide":
                return await self._exec_supplement_guide(base_url, headers, args)
            elif tool_name == "manage_plan":
                return await self._exec_manage_plan(base_url, headers, args)
            elif tool_name == "intervention_cycle":
                return await self._exec_intervention_cycle(args)
            elif tool_name == "upload_genetic_txt":
                return await self._exec_upload_genetic_txt(base_url, headers, args)
            elif tool_name == "query_genetic_profile":
                return await self._exec_query_genetic_profile(base_url, headers, args)
            elif tool_name == "upload_medical_exam_text":
                return await self._exec_upload_medical_exam_text(base_url, headers, args)
            elif tool_name == "query_lab_indicators":
                result = await self._exec_query_lab_indicators(base_url, headers, args)
                return annotate_if_implausible(result)
            else:
                # RFC 方向一 Phase A: specialist 分析工具(analyze_recovery 等)
                from app.services.specialist_tools import is_specialist_tool, run_specialist_tool
                if is_specialist_tool(tool_name):
                    # specialist.run 是同步 CPU 计算, 丢线程池避免阻塞事件循环
                    import asyncio as _aio
                    return await _aio.to_thread(
                        run_specialist_tool, self.db, self._current_user_id, tool_name
                    )
                return f"Error: 未知工具 {tool_name}"
        except Exception as e:
            logger.error(f"工具执行失败 {tool_name}: {e}")
            return f"Error: {tool_name} 执行失败: {str(e)}"

    async def _exec_knowledge_search(self, args: dict) -> str:
        """检索两路知识库, fail-honest, 不静默返回空:
          1. 已审定 System KB v2 claims (DB-backed, owner-reviewed 通用结论)
          2. 得到医学 wiki RAG 片段 (ChromaDB, 仅供参考)
        二者各自独立 try/except: 一路挂不影响另一路。两路全空且 dedao 探测不可用 →
        诚实「检索失败」; 两路全空但可用 → 诚实「未命中」; 任一有命中 → 合并双区块返回。
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

        # ── 1. 已审定 System KB v2 claims (通用 reviewed 结论, 非个性化) ──
        kb_results: list[dict] = []
        try:
            from app.services.system_knowledge_service import search_knowledge as kb_search
            kb_payload = kb_search(self.db, query, limit=n)
            kb_results = (kb_payload or {}).get("results") or []
        except Exception as e:  # noqa: BLE001 — fail honest, 一路挂不冒充成功
            logger.warning(f"[knowledge_search] System KB 检索失败: {e}")
            kb_results = []

        # ── 2. 得到医学 wiki RAG (ChromaDB) ──
        dedao_results: list[dict] = []
        dedao_errored = False
        try:
            from app.agents.knowledge_librarian.indexer import search_knowledge
            dedao_results = search_knowledge(query, n_results=n) or []
        except Exception as e:  # noqa: BLE001 — fail honest, 一路挂不冒充成功
            logger.warning(f"[knowledge_search] 得到 wiki 检索失败: {e}")
            dedao_results = []
            dedao_errored = True

        # ── 双路全空: 区分「不可用」与「零命中」(否则模型把挂了误当未收录而编造) ──
        # indexer.search_knowledge 对「不可用」与「零命中」都返回 [](契约不能改,
        # librarian.py 依赖 []),故旁路探测 dedao collection 可用性。
        if not kb_results and not dedao_results:
            dedao_available = False
            if not dedao_errored:
                try:
                    from app.agents.knowledge_librarian.indexer import _get_collection
                    collection = _get_collection()
                    dedao_available = collection is not None and collection.count() > 0
                except Exception:  # noqa: BLE001 — 探测自身出错 → 视作不可用(诚实)
                    dedao_available = False

            if not dedao_available:
                return (
                    "知识库检索失败(暂不可用),请基于已有信息谨慎作答,勿编造依据。"
                )
            return (
                f"知识库未命中『{query}』相关条目(该主题可能未收录)。"
                "请如实说明依据来自通用医学知识而非本系统知识库,勿编造引用。"
            )

        # ── 合并双区块 ──
        sections: list[str] = []

        if kb_results:
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
            sections.append("\n".join(kb_lines))

        if dedao_results:
            dd_lines = ["【得到医学wiki 检索片段(仅供参考)】"]
            for i, r in enumerate(dedao_results, 1):
                snippet = (r.get("text") or "").strip().replace("\n", " ")
                if len(snippet) > 400:
                    snippet = snippet[:400] + "…"
                title = (r.get("title") or "").strip()
                source = (r.get("source") or "").strip()
                label = title or source or "片段"
                head = f"{i}. [{label}]"
                if source and source != label:
                    head += f" ({source})"
                dd_lines.append(f"{head} {snippet}")
            sections.append("\n".join(dd_lines))

        return "\n\n".join(sections)

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
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

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
            return canonical

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

        return await self._api_get(f"{base}{path}", headers)


    async def _exec_health_record(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康数据记录"""
        # 别名容错:模型常把 record_type 写成 type(实测 health_record(type=diet, data={...}))。
        rtype = _normalize_fast_record_kind(args.get("record_type") or args.get("type") or "")
        data = args.get("data", {})
        # data 偶尔被吐成 JSON 字符串(coerce 退化)→ 尽力解析回 dict。
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                data = {}
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

        # medication 是医疗级写入:无论快/慢路径恒确认前置。快路径由 gate 置 flag;
        # 慢路径(quality 模型 / telegram 直调)此前 medication 无任何确认 ——
        # pre-existing 洞,对抗评审揪出。跨轮机制不变:模型复述→用户"是的"→
        # 重调带 confirmed=true → _confirm_or_describe 放行。
        if args.pop("_fast_record_requires_confirmation", False) or rtype == "medication":
            check = _confirm_or_describe(
                args,
                data,
                preview=_health_record_confirmation_preview(rtype, args, data),
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
                return (
                    "Error: water 记录必须提供 amount (毫升, 整数). 例如 "
                    '{"record_type":"water","data":{"amount":250}}. '
                    "若用户没提具体毫升数, 请先问'喝了多少 ml?'再调用本工具."
                )
            try:
                amount_int = int(amount)
            except (ValueError, TypeError):
                return f"Error: water amount 必须是整数毫升 (got {amount!r})"
            if amount_int <= 0 or amount_int > 5000:
                return f"Error: water amount={amount_int} 不合理 (1-5000ml)"
            data["amount"] = amount_int
            check = _confirm_or_describe(
                args, data,
                preview=f"喝水 {amount_int}ml" + (f", {data['drink_type']}" if data.get("drink_type") else ""),
            )
            if check:
                return check
            return await self._api_post(
                f"{base}/water/records/quick?amount={amount_int}",
                headers,
                {},
            )

        # 补全 diet 必填字段
        if rtype == "diet":
            data.setdefault("record_date", today)
            data.setdefault("meal_type", "snack")
            # 中文 meal_type 映射
            meal_type_map = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner", "加餐": "snack", "夜宵": "snack"}
            if data.get("meal_type") in meal_type_map:
                data["meal_type"] = meal_type_map[data["meal_type"]]
            if isinstance(data.get("food_items"), list):
                data["food_items"] = ", ".join(
                    (f.get("name", str(f)) if isinstance(f, dict) else str(f))
                    for f in data["food_items"]
                )
            elif not data.get("food_items"):
                data["food_items"] = data.get("description", data.get("notes", ""))
            if not data.get("food_items"):
                return "Error: diet 记录必须提供 food_items（食物内容）。请先识别食物内容，然后重新调用 health_record 并在 data.food_items 中填写具体食物。"

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
                return "Error: weight 记录必须提供 weight（体重数值，单位 kg）。请在 data.weight 中填入数字，例如 {\"record_type\":\"weight\",\"data\":{\"weight\":71.2}}"

            # L8 (Karpathy "verification is the bottleneck"): 高确定性数值, 写错没法静默修正
            check = _confirm_or_describe(
                args, data,
                preview=f"体重 {data['weight']} kg, 日期 {data.get('record_date', today)}",
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
                return (
                    "Error: blood_pressure 记录必须提供 systolic + diastolic. 例如 "
                    '{"record_type":"blood_pressure","data":{"systolic":120,"diastolic":80}}'
                )
            # L8: 血压数值高/低风险大, 必须先确认
            check = _confirm_or_describe(
                args, data,
                preview=f"血压 {sys_v}/{dia_v}, 日期 {data.get('record_date', today)}",
            )
            if check:
                return check

        # illness 急性症状记录 — 影响疾病追踪, 必须先确认
        if rtype == "illness":
            data.setdefault("start_date", today)
            name = data.get("name") or data.get("illness_name") or args.get("name") or args.get("illness_name")
            if not name:
                return (
                    "Error: illness 记录必须提供 name. 例如 "
                    '{"record_type":"illness","data":{"name":"感冒","severity":5}}'
                )
            data["name"] = name
            sev = data.get("severity") or args.get("severity")
            if sev is not None:
                data["severity"] = sev
            preview_bits = [f"生病: {name}"]
            if sev is not None:
                preview_bits.append(f"严重度 {sev}")
            preview_bits.append(f"开始 {data.get('start_date')}")
            check = _confirm_or_describe(args, data, preview=", ".join(preview_bits))
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

        if rtype == "reminder":
            data = _normalize_reminder_record_data(data)
            args["data"] = data

        # rhinitis: 症状计数转 illness_episode (复用 illness 流程, 跟 rhinitis-tracker skill 对齐)
        if rtype == "rhinitis":
            sneezing = int(data.get("sneezing", 0) or 0)
            congestion = int(data.get("congestion", 0) or 0)
            runny_nose = int(data.get("runny_nose", 0) or 0)
            # 严重度取 congestion/runny_nose 的 1-10 量表 max, 无则按喷嚏频率兜底
            severity_vals = [v for v in (congestion, runny_nose) if v and 0 < v <= 10]
            severity = (max(severity_vals) if severity_vals
                        else (min(8, max(3, sneezing // 3)) if sneezing else 2))
            parts = []
            if sneezing:
                parts.append(f"喷嚏 {sneezing} 次")
            if congestion:
                parts.append(f"鼻塞 {congestion}/10")
            if runny_nose:
                parts.append(f"流涕 {runny_nose} 次")
            notes = data.get("notes") or "、".join(parts) or "鼻炎症状"
            payload = {
                "illness_name": "鼻炎发作",
                "severity": severity,
                "notes": notes,
                "start_date": data.get("record_date") or today,
            }
            return await self._api_post(f"{base}/illness/episodes", headers, payload)

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
                return json.dumps(
                    {"message": f"已把「{name}」加入补剂库并完成今日打卡（补剂号 {created['id']}，说「撤销」可移除）"},
                    ensure_ascii=False,
                )
            return "Error: 需要提供补剂名称（supplement_name）"

        # medication: 用药记录
        if rtype == "medication":
            med_name = data.get("medication_name", data.get("name", ""))
            if not med_name:
                return "Error: 需要提供药物名称（medication_name）"
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
            taken_time = data.get("taken_time", datetime.now(BEIJING_TZ).isoformat())
            return await self._api_post(
                f"{base}/medication/logs", headers,
                {"medication_id": matched["id"], "taken_time": taken_time, "status": "taken"}
            )

        if rtype == "illness":
            payload = dict(data)
            if "name" not in payload and payload.get("illness_name"):
                payload["name"] = payload.pop("illness_name")
            payload.setdefault("start_date", datetime.now(BEIJING_TZ).date().isoformat())
            payload.setdefault("status", "active")
            if not payload.get("name"):
                return "Error: illness 必须提供 name (如 '感冒' / '发烧')"
            return await self._api_post(f"{base}/illness/episodes", headers, payload)

        record_map = {
            "weight": ("/weight/records", "POST", data),
            "blood_pressure": ("/blood-pressure/records", "POST", data),
            "exercise": ("/daily-health/exercise", "POST", data),
            "diet": ("/diet/records", "POST", data),
            "supplement": ("/supplements/records", "POST", data),
            # rhinitis 走 special case (见上方 rtype=="rhinitis" 分支), 不在 record_map 里
            "mood": ("/mood/records", "POST", data),
            "garmin_sync": ("/data-collection/garmin/me/sync?days=1", "POST", {}),
            "reminder": ("/reminders/me", "POST", data),
        }

        # symptom: 通用身体症状 (眼痒/嗓子疼 ...). 不再需要 profile_id (新 /symptoms 表,
        # 2026-05-08 改, 替换旧 disease_tracking.SymptomLog 路径 — 那路径强行要 profile_id,
        # 用户体验差, 已废弃. 鼻炎打卡走 record_type="rhinitis".
        if rtype == "symptom":
            body_part = data.get("body_part")
            description = data.get("description")
            if not body_part:
                return "Error: symptom 必须提供 body_part (eye/respiratory/skin/digestive/musculoskeletal/head/general/other)"
            if not description:
                return "Error: symptom 必须提供 description (如 '眼睛痒' / '右膝盖钝痛')"
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
                logger.info(f"[health_record] type={rtype} result={result[:200]}")
                return result
        return f"Error: 不支持的记录类型 {rtype}"

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
        target_date = args.get("date")
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

        list_paths = {
            "diet": f"/diet/records/me/date/{target_date or today}" if target_date else "/diet/records/me?limit=20",
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
            "supplement_definition": "/supplements/me/definitions?active_only=false",
            "reminder": "/reminders/me?status=all&limit=50",
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
            "supplement_definition": "/supplements/definitions/{id}",
            "reminder": "/reminders/{id}",
        }
        update_supported = {
            "diet", "water", "weight", "waist", "blood_pressure",
            "sleep", "mood", "excretion", "illness", "medication",
            "supplement_definition", "exercise", "symptom", "medication_log",
            "reminder",
        }

        if operation == "list":
            path = list_paths.get(record_type)
            if not path:
                return f"Error: 不支持查询 {record_type}"
            return await self._api_get(f"{base}{path}", headers)

        path_tmpl = record_paths.get(record_type)
        if not path_tmpl:
            return f"Error: 不支持管理 {record_type}"
        if not record_id:
            return "Error: 修改或删除必须提供 record_id. 请先查询候选记录并确认 ID."
        path = path_tmpl.format(id=record_id)

        if operation == "delete":
            result = await self._api_delete(f"{base}{path}", headers)
            self._invalidate_twin_after_mutation()
            return result or json.dumps({"message": "删除成功", "record_id": record_id}, ensure_ascii=False)

        if operation == "update":
            if record_type not in update_supported:
                return f"Error: {record_type} 暂不支持 update, 可先删除后重记."
            result = await self._api_put(f"{base}{path}", headers, data)
            self._invalidate_twin_after_mutation()
            return result

        return f"Error: 不支持的操作 {operation}"

    def _invalidate_twin_after_mutation(self) -> None:
        if self._current_user_id is None:
            return
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
            result = await self._api_post(
                f"{base}/orchestrator/chat", headers,
                {"query": question}
            )
            return result

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
            "forecast": "/environment/weather/forecast?days=3",
        }
        path = path_map.get(ctype, "/environment/weather")
        return await self._api_get(f"{base}{path}", headers)

    async def _exec_supplement_guide(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """获取补剂指南"""
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
            return "Error: 需要 plan_id 和 item_id"
        elif action == "save_to_card":
            return await self._api_post(f"{base}/action-cards/from-message", headers, data)
        return f"Error: 不支持的计划操作 {action}"

    async def _exec_intervention_cycle(self, args: dict) -> str:
        """N-of-1 干预结局闭环工具 — status 报进展 / start 开周期 (写操作需确认).

        直接复用 intervention_cycle_service (不重写 SQL/不重算 delta), 用户隔离靠
        self._current_user_id。service 是同步, 丢线程池避免阻塞事件循环。
        """
        import asyncio as _aio

        action = args.get("action", "")
        user_id = self._current_user_id
        if user_id is None:
            return "Error: 缺少用户身份, 无法操作干预周期"

        if action == "status":
            return await _aio.to_thread(self._intervention_status, user_id)

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

        return f"Error: 不支持的干预周期操作 {action}"

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
            return (
                "你已经有一个进行中的干预周期了 (同一时间只跟踪一个), 没有重复开。"
                "想看进展用 status; 想换目标可以等当前周期结束。"
            )

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
            return (
                f"已开启干预周期 (周期 {days} 天), 但暂时没有可锁定的异常代谢指标作为目标。"
                "建议先补一次化验 (血脂/血糖/肝功/尿酸), 之后复查时就能验证效果了。"
            )
        from app.biomarkers import get_definition
        names = [
            (get_definition(om.metric_code).display if get_definition(om.metric_code) else om.metric_code)
            for om in cycle.outcomes
        ]
        return (
            f"已开启 N-of-1 干预周期 (周期 {days} 天), 锁定基线快照。"
            f"将跟踪 {n} 项结局指标: {', '.join(names)}。"
            "过段时间复查化验后, 我会用你自己的数据告诉你有没有改善。"
            "(非医疗诊断, 重大健康调整请结合医生意见。)"
        )

    async def _exec_upload_genetic_txt(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """上传 23andMe / WeGene TXT 原始数据."""
        txt = args.get("txt_content") or ""
        if len(txt) < 50:
            return "Error: txt_content 太短, 不像是 23andMe/WeGene 原始数据 (应是含 rsid 的 tab 分隔行)"
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
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
        return await self._api_get(f"{base}/genetic/profiles/me", headers)

    async def _exec_upload_medical_exam_text(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """口述化验文本 → medical_text_parser → 入 MedicalExam + Indicator."""
        text = (args.get("text") or "").strip()
        if not text:
            return "Error: text 不能为空"
        if self._current_user_id is None:
            return "Error: 当前会话无 user_id, 无法写入化验指标"

        try:
            from datetime import date as _date

            from app.services.data_collection.medical_exam_import import MedicalExamImportService
            from app.twin.cache import invalidate_twin

            raw_date = args.get("exam_date")
            exam_date = (
                datetime.strptime(raw_date, "%Y-%m-%d").date()
                if raw_date
                else _date.today()
            )
            exam = MedicalExamImportService.import_from_text(
                self.db,
                user_id=self._current_user_id,
                text=text,
                exam_date=exam_date,
                source="agent_text",
            )
            try:
                invalidate_twin(self._current_user_id)
            except Exception:
                pass
            return json.dumps(
                {
                    "message": "化验指标已写入系统",
                    "exam_id": exam.id,
                    "exam_date": exam.exam_date.isoformat() if exam.exam_date else None,
                    "items_count": len(exam.items or []),
                },
                ensure_ascii=False,
            )
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"[upload_medical_exam_text] 入库失败: {e}", exc_info=True)
            try:
                self.db.rollback()
            except Exception:
                pass
            return f"Error: 化验指标入库失败: {e}"

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
                return json.dumps(
                    {"batch": True, "count": total, "queried": names,
                     "by_name": by_name, "truncated": truncated},
                    ensure_ascii=False,
                )

        # 单指标(向后兼容:返回原 shape)
        return json.dumps(
            self._query_one_lab_indicator(args.get("name"), since, limit),
            ensure_ascii=False,
        )

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
        text = resp.text
        if len(text) > 3000:
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
            except Exception:
                pass
            text = text[:3000] + "\n...(数据已截断)"
        return text

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
