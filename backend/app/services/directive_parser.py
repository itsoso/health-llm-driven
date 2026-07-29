"""
Directive Parser — 把用户 / 健康顾问 / 家人 的自由文本指令解析为 UserDirective.

输入: "把 LDL 目标降到 2.6 以下, 限酒" (中文)
输出: 2 条 directive (target_override + lifestyle)

注: 本系统不提供医疗服务, 不出具医嘱. directives 是用户自己 (或委托人)
对 agent 的硬性约束. 如需医疗判断, 始终建议咨询执业医师.

策略:
1. 调 LLM 解析 (gpt-4o-mini), 用结构化 JSON schema
2. fallback 关键字: 如果 LLM 失败, 简单关键词匹配总比丢消息好
3. 落库时打 source='external_telegram' / 'user_self' / ...
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# 结构化 schema 给 LLM
PARSE_PROMPT_SYSTEM = """你是健康指令解析助手. 把用户/健康教练/家人的中文自由文本拆成 0 个或多个 directive.

每个 directive 输出 JSON 字段:
  kind: 'medication_change' | 'target_override' | 'lifestyle' | 'watch_metric' | 'skip_recommendation'
  instruction: 原文相关的句子 (1 句, 最多 100 字)
  metric_key: hrv/weight/ldl/hdl/tg/hba1c/systolic_bp/diastolic_bp/alt/...  (没有就 null)
  target_value: 比如 '<2.6' 或 '继续' 或 '<140/90' (没有就 null)
  medication_name: 药品名, 如 '美托洛尔' (kind=medication_change 时)
  severity: 'advisory' | 'strong' | 'mandatory' (默认 strong, 文本里强调"必须"才 mandatory)
  expires_days: 可选数字, 多少天后过期 (没说则 null)

输出 JSON 数组. 没有指令就输出 [].

规则:
- "继续/停用/换/加/减某药" → kind=medication_change
- "目标 X < Y" / "X 应控制在 Y" → kind=target_override
- "饮食/作息/运动" 类约束 → kind=lifestyle
- "监测 X" / "X 超过 Y 立刻..." → kind=watch_metric
- "不要再推 / 别给我建议 X" → kind=skip_recommendation"""


async def _parse_with_llm_async(text: str) -> List[dict]:
    """异步调 LLM 解析，避免在事件循环内嵌套 ``asyncio.run``。"""
    try:
        from app.config import settings
        from app.services.llm.factory import create_provider_for_extraction
        from app.services.llm.usage_tracker import set_caller

        set_caller("directive_parser", user_id=None)
        provider = create_provider_for_extraction(settings.directive_parse_model_id)
        out = await provider.chat(
            messages=[
                {"role": "system", "content": PARSE_PROMPT_SYSTEM},
                {"role": "user", "content": f"原文:\n{text}\n\n请输出 JSON 数组."},
            ],
            temperature=0.1,
            max_tokens=600,
        )
        if isinstance(out, dict):
            out = out.get("content") or ""
        out = str(out or "").strip()

        # 容错: 提取首个 [ ... ] JSON 块
        m = re.search(r"\[[\s\S]*\]", out)
        if not m:
            return []
        items = json.loads(m.group())
        return items if isinstance(items, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[directive_parser] LLM parse failed error_type=%s",
            type(e).__name__,
        )
        return []


def _parse_with_llm(text: str) -> List[dict]:
    """同步兼容入口，供脚本和同步 API 使用。"""
    import asyncio

    return asyncio.run(_parse_with_llm_async(text))


# Fallback 关键词解析 (LLM 不可用时)
_FALLBACK_PATTERNS = [
    # 顺序重要: target_override 在 medication 前 (避免"LDL 控制在 X"误判 medication)
    (r"(LDL|HBA1C|HDL|血压|血糖|TG|尿酸|TC|心率|HRV|体重|BMI).{0,15}(<|>|≤|≥|降到|控制在|不超过|低于|高于)", "target_override"),
    (r"(继续|停用|停|换|加|减|改).{0,15}(药|片|胶囊|针|吃|服|片药|普利|沙坦|洛尔|地平|酮)", "medication_change"),
    (r"(戒酒|戒烟|低钠|低糖|低脂|多喝水|多运动|作息|早睡|节食)", "lifestyle"),
    (r"(监测|关注|留意|注意).{0,10}(HRV|血压|心率|血糖|睡眠|体重)", "watch_metric"),
    (r"(不要|别).{0,8}(推|建议|发|说)", "skip_recommendation"),
]


def _fallback_parse(text: str) -> List[dict]:
    items: List[dict] = []
    for pat, kind in _FALLBACK_PATTERNS:
        if re.search(pat, text):
            items.append({
                "kind": kind,
                "instruction": text[:200],
                "metric_key": None,
                "target_value": None,
                "medication_name": None,
                "severity": "strong",
            })
            break  # fallback 只识别一种, 避免重复入库
    return items


def parse_and_store(
    db: Session,
    user_id: int,
    text: str,
    *,
    source: str = "external_telegram",
    source_message_id: Optional[str] = None,
) -> List[int]:
    """主入口. 返回新创建的 directive ID 列表."""
    if not text or len(text.strip()) < 4:
        return []
    parsed = _parse_with_llm(text) or _fallback_parse(text)
    return _store_parsed_directives(
        db,
        user_id,
        text,
        parsed,
        source=source,
        source_message_id=source_message_id,
    )


async def parse_and_store_async(
    db: Session,
    user_id: int,
    text: str,
    *,
    source: str = "external_telegram",
    source_message_id: Optional[str] = None,
) -> List[int]:
    """事件循环安全的指令解析与写入入口。"""
    if not text or len(text.strip()) < 4:
        return []
    parsed = await _parse_with_llm_async(text) or _fallback_parse(text)
    return _store_parsed_directives(
        db,
        user_id,
        text,
        parsed,
        source=source,
        source_message_id=source_message_id,
    )


def _store_parsed_directives(
    db: Session,
    user_id: int,
    text: str,
    parsed: List[dict],
    *,
    source: str,
    source_message_id: Optional[str],
) -> List[int]:
    """Persist already parsed directives with source-message replay protection."""
    from datetime import datetime, timedelta, timezone
    from app.models.user_directive import UserDirective

    if not text or len(text.strip()) < 4:
        return []

    if not parsed:
        logger.info("[directive_parser] 未识别出 directive text_len=%s", len(text))
        return []
    if source_message_id:
        existing = (
            db.query(UserDirective.id)
            .filter(
                UserDirective.user_id == user_id,
                UserDirective.source == source,
                UserDirective.source_message_id == source_message_id,
            )
            .order_by(UserDirective.id.asc())
            .all()
        )
        if existing:
            return [int(row[0]) for row in existing]

    created: List[int] = []
    now = datetime.now(timezone.utc)
    for d in parsed:
        try:
            kind = d.get("kind")
            if kind not in {"medication_change", "target_override", "lifestyle",
                           "watch_metric", "skip_recommendation"}:
                continue
            expires_at = None
            if d.get("expires_days"):
                try:
                    expires_at = now + timedelta(days=int(d["expires_days"]))
                except (TypeError, ValueError):
                    pass

            row = UserDirective(
                user_id=user_id,
                kind=kind,
                instruction=(d.get("instruction") or text)[:1000],
                metric_key=(d.get("metric_key") or None),
                target_value=(d.get("target_value") or None),
                medication_name=(d.get("medication_name") or None),
                severity=(d.get("severity") or "strong"),
                source=source,
                source_message_id=source_message_id,
                expires_at=expires_at,
            )
            db.add(row)
            db.flush()
            created.append(row.id)
            logger.info(
                "[directive_parser] created directive=%s kind=%s user=%s",
                row.id,
                kind,
                user_id,
            )
            # Memory: directive → high-confidence semantic fact (旁路)
            try:
                from app.services.memory_extractor import extract_from_directive
                extract_from_directive(db, row)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "[directive_parser] memory extract failed directive=%s "
                    "user=%s error_type=%s",
                    row.id,
                    user_id,
                    type(e).__name__,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[directive_parser] directive write failed user=%s kind=%s "
                "error_type=%s",
                user_id,
                d.get("kind"),
                type(e).__name__,
            )
    db.commit()
    return created


def get_active_directives_for_prompt(
    db: Session, user_id: int, metric_key: Optional[str] = None,
) -> str:
    """取该 user 当前 active directives, 拼成 markdown 给 specialist prompt 注入.

    metric_key 给定时优先返回与之相关 + 通用 (无 metric_key) 的.
    """
    from datetime import datetime, timezone
    from sqlalchemy import or_
    from app.models.user_directive import UserDirective

    now = datetime.now(timezone.utc)
    q = db.query(UserDirective).filter(
        UserDirective.user_id == user_id,
        UserDirective.status == "active",
        or_(UserDirective.expires_at.is_(None),
            UserDirective.expires_at > now),
    )
    if metric_key:
        q = q.filter(or_(
            UserDirective.metric_key == metric_key,
            UserDirective.metric_key.is_(None),
        ))
    rows = q.order_by(UserDirective.created_at.desc()).limit(10).all()

    if not rows:
        return ""

    lines = ["## 硬性指令 (specialist 必须遵循)"]
    for r in rows:
        sev_emoji = {"mandatory": "🔴", "strong": "🟡", "advisory": "ℹ️"}.get(r.severity, "")
        prefix = f"[{r.kind}]"
        if r.metric_key:
            prefix += f" [{r.metric_key}]"
        if r.medication_name:
            prefix += f" [{r.medication_name}]"
        lines.append(f"- {sev_emoji} {prefix} {r.instruction}")
    return "\n".join(lines)
