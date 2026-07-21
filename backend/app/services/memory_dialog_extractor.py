"""
Conversation → Memory facts 自动抽取 (Karpathy "anterograde amnesia" 解药).

为什么:
  D 里 AI 主动澄清 → 用户答 "我换了高枕头" → 这是金子事实
  不写进 memory_facts → 下次告警 Twin 不带, AI 重复问相同问题, 闭环失效.

设计:
  - 输入: 一段 conversation 文本 (建议: 最近 N 轮 user 回答, 不超过 800 字)
  - 输出: List[ExtractedFact] (subject/predicate/object_value/confidence)
  - LLM 后处理 (一次低成本调用, 不阻塞用户对话)
  - 调用方再走 memory_service.write_fact 写入 (自动去重/reinforce)

约束:
  - 只抽用户陈述的"自身"事实 (user.* 子树), 不抽推测/AI 建议
  - 严格 JSON output, 失败 fallback 到空列表 (绝不阻塞)
  - 一次抽取上限 5 条 — 防止幻觉淹没
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from pydantic import BaseModel

from app.config import settings
from app.services.llm.factory import create_provider_for_extraction

logger = logging.getLogger(__name__)


class ExtractedFact(BaseModel):
    subject: str  # 'user.sleep.pillow' / 'user.diet.coffee_intake'
    predicate: str  # 'is_value' / 'has_history' / 'responds_to' ...
    object_value: str  # '高枕头' / '咖啡过敏'
    confidence: float = 0.6  # 用户自陈通常 0.6-0.8
    object_unit: Optional[str] = None


_EXTRACT_PROMPT = """你是一个结构化事实抽取器, 从一段对话文本里提取用户陈述的关于自身的事实.

规则:
1. 只抽用户**自陈**的事实 (我换了高枕 / 我对咖啡过敏 / 我每周跑 3 次)
2. 不抽 AI 的建议 / 推测 / 假设性问题
3. subject 用层级命名空间, 例: user.sleep.pillow_height / user.diet.coffee / user.exercise.frequency
4. predicate 用标准词:
   is_value (取值=...) / has_history (有过...) / responds_to (X 对 Y 有效) /
   does_not_respond_to (X 对 Y 无效) / triggers (诱发) / improves (改善) /
   takes_medication (服药) / is_above (高于) / is_below (低于) / equals (等于)
5. confidence: 用户明确肯定 0.8, 推测/可能 0.5, 否定也是事实但 confidence 0.7
6. 最多 5 条; 没有可抽的事实就返回空数组

返回严格 JSON 格式 (不要任何 markdown 代码块标记, 不要解释):
{"facts": [
  {"subject": "user.sleep.pillow_height", "predicate": "is_value", "object_value": "比平时高", "confidence": 0.8},
  ...
]}

对话文本:
---
%s
---
"""


async def extract_facts_from_dialog(
    user_text: str,
    *,
    context_hint: Optional[str] = None,
    max_facts: int = 5,
) -> List[ExtractedFact]:
    """
    从一段对话文本抽事实.

    Args:
        user_text: 用户说的话 (拼接多轮也可)
        context_hint: 可选, 给 LLM 一个上下文提示 (如 "用户在回答关于睡眠的 follow-up")
                      这是 alert_clarification.rationale, 让抽取更精准
        max_facts: 上限

    Returns: List[ExtractedFact], 失败/空返回 []
    """
    if not user_text or not user_text.strip():
        return []

    # 拼 prompt — 短文本快速抽
    full_text = user_text.strip()
    if context_hint:
        full_text = f"[上下文: {context_hint}]\n\n{full_text}"

    prompt = _EXTRACT_PROMPT % full_text[:1500]

    try:
        from app.services.llm.usage_tracker import set_caller
        set_caller("memory.dialog_extractor")
        # Batch-1 token-perf: 纯抽取, 降档 flash; 创建失败 fail-soft 回退默认 provider。
        provider = create_provider_for_extraction(settings.dialog_extract_model_id)
        # provider.chat 接受 messages 数组而不是 string
        raw = await provider.chat(
            messages=[
                {"role": "system", "content": "你是一个结构化事实抽取器, 严格按要求输出 JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,  # 低温度确保 JSON 稳定
            max_tokens=600,
        )
        # 兼容 dict (tool_calls) / str (content) 返回
        if isinstance(raw, dict):
            raw = raw.get("content", "") or ""
    except Exception as e:
        logger.warning(f"[dialog_extractor] LLM 调用失败: {e}")
        return []

    if not raw:
        return []

    # 容错解析: LLM 可能加了 ```json ... ``` 或前后废话
    text = raw.strip()
    if "```" in text:
        # 抽 JSON 块
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                text = p
                break

    # 找第一个 { 到最后一个 } (容错前后多余内容)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return []
    text = text[start : end + 1]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(
            "[dialog_extractor] JSON 解析失败 error_type=%s response_len=%s",
            type(e).__name__,
            len(raw),
        )
        return []

    raw_facts = parsed.get("facts", [])
    if not isinstance(raw_facts, list):
        return []

    facts: List[ExtractedFact] = []
    for item in raw_facts[:max_facts]:
        try:
            facts.append(ExtractedFact(**item))
        except Exception:  # 字段不全
            continue

    return facts
