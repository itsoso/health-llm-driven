"""
Clinical Journal 服务 — 在 orchestrator 跑完后旁路写一条 SOAP entry.

设计:
- 不发起额外 LLM 调用 (省钱省延迟). 直接从 specialist findings + synthesis
  组装 SOAP 四段, 主要是结构化重组.
- case_thread 聚合: 按 metric_key (主指标) 找现有 active thread, 没有就开新.
- fail-soft: 任何错误只 log, 不影响主对话.

调用点: orchestrator.run_orchestrator / stream_orchestrator 落地完
proposed_cards 之后, 异步调用 (这里同步实现, 上层用 thread 包装即可).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# specialist.category / metric_key → case theme
_THEME_MAP = {
    "rhinitis": "rhinitis",
    "spo2_min_nocturnal": "sleep_osahs",
    "sleep_score": "sleep_quality",
    "alt": "liver",
    "ast": "liver",
    "ggt": "liver",
    "ldl": "lipid",
    "hdl": "lipid",
    "tg": "lipid",
    "tc": "lipid",
    "hba1c": "metabolic",
    "blood_glucose": "metabolic",
    "weight": "weight_loss",
    "bmi": "weight_loss",
    "systolic_bp": "hypertension",
    "diastolic_bp": "hypertension",
    "hrv": "recovery",
    "rhr": "recovery",
}


def _theme_from_metric(metric_key: Optional[str]) -> str:
    if not metric_key:
        return "general"
    return _THEME_MAP.get(metric_key.lower(), metric_key.lower())


def _get_or_create_case_thread(
    db: Session,
    user_id: int,
    theme: str,
    metric_key: Optional[str],
) -> "CaseThread":
    """找该用户的 active case_thread, 没有就开新."""
    from app.models.clinical_journal import CaseThread

    q = db.query(CaseThread).filter(
        CaseThread.user_id == user_id,
        CaseThread.theme == theme,
        CaseThread.status == "active",
    )
    if metric_key:
        q = q.filter(CaseThread.metric_key == metric_key)
    existing = q.order_by(CaseThread.last_updated_at.desc()).first()
    if existing:
        return existing

    title_zh = {
        "rhinitis": "鼻炎管理",
        "sleep_osahs": "睡眠呼吸",
        "sleep_quality": "睡眠质量",
        "liver": "肝功能监测",
        "lipid": "血脂管理",
        "metabolic": "代谢健康",
        "weight_loss": "体重管理",
        "hypertension": "血压管理",
        "recovery": "恢复评估",
        "general": "综合评估",
    }.get(theme, theme)

    new_thread = CaseThread(
        user_id=user_id,
        theme=theme,
        metric_key=metric_key,
        title=title_zh,
        status="active",
    )
    db.add(new_thread)
    db.flush()  # 立即拿 id
    return new_thread


def _build_subjective(query: str) -> str:
    """主诉 = 用户的话, 限长 200."""
    q = (query or "").strip()
    return q[:200] + ("…" if len(q) > 200 else "")


def _build_objective(twin) -> str:
    """从 Twin 提取关键数字, 短句拼接."""
    parts = []
    p = twin.physiological
    b = twin.body_composition
    labs = twin.labs

    if p:
        bits = []
        if getattr(p, "hrv_latest", None) is not None:
            bits.append(f"HRV {p.hrv_latest:.0f}ms")
        rhr = getattr(p, "resting_hr", None) or getattr(p, "resting_heart_rate", None)
        if rhr is not None:
            bits.append(f"RHR {rhr}")
        if getattr(p, "sleep_score_latest", None) is not None:
            bits.append(f"睡眠分 {p.sleep_score_latest}")
        if bits:
            parts.append("生理: " + " / ".join(bits))

    if b and getattr(b, "weight_kg", None):
        bmi = getattr(b, "bmi", None)
        parts.append(f"体重: {b.weight_kg}kg" + (f" BMI {bmi:.1f}" if bmi else ""))

    if labs:
        lab_bits = []
        sbp = getattr(labs, "blood_pressure_systolic", None)
        dbp = getattr(labs, "blood_pressure_diastolic", None)
        if sbp and dbp:
            lab_bits.append(f"BP {sbp}/{dbp}")
        for fld, label in (("ldl", "LDL"), ("hba1c", "HbA1c"), ("alt", "ALT")):
            v = getattr(labs, fld, None)
            if v is not None:
                lab_bits.append(f"{label} {v}")
        if lab_bits:
            parts.append("化验: " + " / ".join(lab_bits))

    return "; ".join(parts) or "(无关键指标)"


def _build_assessment(findings) -> str:
    """从 specialist findings 提取 summary 拼接."""
    if not findings:
        return "(无 specialist 评估)"
    parts = []
    for f in findings:
        s = (f.summary or "").strip()
        if s:
            parts.append(f"[{f.specialist_name}] {s}")
    return "\n".join(parts) or "(无评估文本)"


def _build_plan(findings, persisted_card_ids: List[int]) -> str:
    """Plan = 落地的 ActionCard 标题 + 任何 finding 里的 action 文本."""
    parts = []
    if persisted_card_ids:
        parts.append(f"📋 落地 {len(persisted_card_ids)} 张 ActionCard 进入信任循环 "
                     f"(IDs: {persisted_card_ids})")

    for f in findings:
        for pc in (f.proposed_cards or []):
            parts.append(f"- {pc.title} ({pc.metric_key} {pc.target_value}, "
                         f"{pc.verification_days}d 后评分)")

    return "\n".join(parts) or "(本次无新行动卡片)"


def _pick_primary_metric(findings) -> Optional[str]:
    """从 findings 选一个最'重'的 metric_key 用于 case_thread 聚合."""
    metrics: List[str] = []
    for f in findings:
        for pc in (f.proposed_cards or []):
            metrics.append(pc.metric_key)
    if metrics:
        # 出现频率最高的
        from collections import Counter
        return Counter(metrics).most_common(1)[0][0]
    return None


def write_soap_entry(
    db: Session,
    *,
    user_id: int,
    query: str,
    twin,
    findings,
    persisted_card_ids: List[int],
    source_conversation_id: Optional[int] = None,
    source_message_id: Optional[int] = None,
    created_by: str = "orchestrator",
) -> Optional[int]:
    """旁路写一条 SOAP. 返回 entry id, 出错返回 None."""
    from app.models.clinical_journal import ClinicalJournalEntry

    try:
        primary_metric = _pick_primary_metric(findings)
        theme = _theme_from_metric(primary_metric)
        thread = _get_or_create_case_thread(db, user_id, theme, primary_metric)

        entry = ClinicalJournalEntry(
            user_id=user_id,
            case_thread_id=thread.id,
            subjective=_build_subjective(query),
            objective=_build_objective(twin),
            assessment=_build_assessment(findings),
            plan=_build_plan(findings, persisted_card_ids),
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            used_specialists=",".join(f.specialist_name for f in findings) or None,
            related_action_card_ids=",".join(str(i) for i in persisted_card_ids) or None,
            created_by=created_by,
        )
        db.add(entry)

        # 更新 thread 最后活跃时间 + summary (取最近一次 assessment 首句)
        thread.last_updated_at = datetime.now(timezone.utc)
        first_assessment = (entry.assessment or "").split("\n")[0]
        thread.summary = first_assessment[:300] if first_assessment else thread.summary

        db.commit()
        db.refresh(entry)
        logger.info(f"[journal] entry #{entry.id} written user={user_id} "
                   f"theme={theme} thread={thread.id}")

        # Memory Extractor: SOAP → fact(s) (旁路, 失败不影响)
        try:
            from app.services.memory_extractor import extract_from_briefing_entry
            fids = extract_from_briefing_entry(db, entry)
            if fids:
                db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning(f"[journal] orchestrator SOAP extract 失败 (旁路): {e}")

        return entry.id
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[journal] 写 SOAP 失败 (旁路): {e}", exc_info=True)
        return None


def get_recent_case_summary(db: Session, user_id: int, metric_key: Optional[str],
                             max_entries: int = 3) -> str:
    """给 specialist prompt 注入: 找该 metric 最近 max_entries 条 SOAP 摘要."""
    from app.models.clinical_journal import CaseThread, ClinicalJournalEntry

    if not metric_key:
        return ""

    theme = _theme_from_metric(metric_key)
    thread = db.query(CaseThread).filter(
        CaseThread.user_id == user_id,
        CaseThread.theme == theme,
        CaseThread.status == "active",
    ).order_by(CaseThread.last_updated_at.desc()).first()
    if not thread:
        return ""

    entries = db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.case_thread_id == thread.id,
    ).order_by(ClinicalJournalEntry.generated_at.desc()).limit(max_entries).all()
    if not entries:
        return ""

    lines = [f"## 历史 case: {thread.title} (开 {thread.opened_at.strftime('%Y-%m-%d')})"]
    for e in reversed(entries):  # 时间正序
        date_str = e.generated_at.strftime('%Y-%m-%d')
        lines.append(f"\n### {date_str}")
        if e.subjective:
            lines.append(f"- 主诉: {e.subjective}")
        if e.assessment:
            lines.append(f"- 评估: {e.assessment.split(chr(10))[0]}")
        if e.plan and e.plan != "(本次无新行动卡片)":
            lines.append(f"- 行动: {e.plan.split(chr(10))[0]}")

    return "\n".join(lines)


def get_active_case_briefs(db: Session, user_id: int, limit: int = 5) -> List[dict]:
    """返回该用户所有 active case thread 的简要 (theme/title/summary/last_updated).

    供 specialist 或 cross-review 作为"用户有哪些 active 问题线"的上下文.
    不加载 entries, 保持轻量 (specialist 会被并发调用, 查询成本要可控).
    """
    from app.models.clinical_journal import CaseThread

    threads = db.query(CaseThread).filter(
        CaseThread.user_id == user_id,
        CaseThread.status == "active",
    ).order_by(CaseThread.last_updated_at.desc()).limit(limit).all()

    return [
        {
            "thread_id": t.id,
            "theme": t.theme,
            "metric_key": t.metric_key,
            "title": t.title,
            "summary": t.summary,
            "severity": t.severity,
            "last_updated_at": t.last_updated_at.isoformat() if t.last_updated_at else None,
        }
        for t in threads
    ]


def write_briefing_soap_entry(
    db: Session,
    *,
    user_id: int,
    target_date,  # datetime.date
    briefing_md: str,
    ai_narrative: Optional[str],
    alert_messages: Optional[List[str]] = None,
    source_conversation_id: Optional[int] = None,
    source_message_id: Optional[int] = None,
    theme: str = "daily_briefing",
    thread_title: Optional[str] = None,
    created_by: str = "briefing_task",
) -> Optional[int]:
    """每日简报 (或 doctor_weekly) 末尾旁路写一条 SOAP entry.

    与 write_soap_entry 不同: briefing 没跑 specialist 也没 findings, 所以直接
    从 briefing_md / ai_narrative / alerts 切片组装 SOAP. fail-soft.

    同一 (user, date, created_by) 已写过 → 跳过 (幂等).
    """
    from app.models.clinical_journal import CaseThread, ClinicalJournalEntry

    try:
        # 幂等: 同日同来源只写一条
        existing = db.query(ClinicalJournalEntry.id).filter(
            ClinicalJournalEntry.user_id == user_id,
            ClinicalJournalEntry.created_by == created_by,
            ClinicalJournalEntry.subjective.like(f"{target_date}%"),
        ).first()
        if existing:
            logger.info(f"[journal] {theme} SOAP 已存在 user={user_id} date={target_date}, 跳过")
            return None

        thread = _get_or_create_case_thread(db, user_id, theme=theme,
                                             metric_key=None)
        # 覆盖 title 更友好
        default_titles = {
            "daily_briefing": "每日健康简报",
            "doctor_weekly_summary": "周度数据摘要 (医生视图)",
        }
        preferred = thread_title or default_titles.get(theme)
        if preferred and thread.title == theme:
            thread.title = preferred

        # S: 日期 + 标题
        subjective = f"{target_date} {preferred or theme}"

        # O: briefing_md 前 500 字 (已含睡眠/HRV/体重/化验 数字段)
        objective = (briefing_md or "").strip()[:500]

        # A: AI 叙事段 (≤800) + alerts 前 2 条
        assessment_parts: List[str] = []
        if ai_narrative:
            assessment_parts.append(ai_narrative.strip()[:800])
        if alert_messages:
            for msg in alert_messages[:2]:
                if msg:
                    assessment_parts.append(f"⚠️ {msg[:120]}")
        assessment = "\n".join(assessment_parts) or "(无 AI 叙事)"

        # P: 从 briefing_md 里拆 "今日建议" 段 (notifications.py 用 "📌 今日建议：" 做 marker)
        plan = "(本次无新行动卡片)"
        if briefing_md and "今日建议" in briefing_md:
            try:
                after = briefing_md.split("今日建议", 1)[1]
                # 拿到 "**" 之后到下一个段落分隔之间
                plan_body = after.split("\n---", 1)[0].strip()
                plan = plan_body[:500] if plan_body else plan
            except Exception:
                pass

        entry = ClinicalJournalEntry(
            user_id=user_id,
            case_thread_id=thread.id,
            subjective=subjective,
            objective=objective,
            assessment=assessment,
            plan=plan,
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            used_specialists=None,
            related_action_card_ids=None,
            created_by=created_by,
        )
        db.add(entry)

        thread.last_updated_at = datetime.now(timezone.utc)
        if ai_narrative:
            thread.summary = ai_narrative.strip().split("\n")[0][:300]

        db.commit()
        db.refresh(entry)
        logger.info(f"[journal] {theme} SOAP #{entry.id} user={user_id} date={target_date}")

        # Memory Extractor: briefing SOAP → fact(s) (旁路, 失败不影响)
        try:
            from app.services.memory_extractor import extract_from_briefing_entry
            fids = extract_from_briefing_entry(db, entry)
            if fids:
                db.commit()
                logger.info(f"[journal] briefing #{entry.id} 抽出 {len(fids)} 条 fact")
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning(f"[journal] briefing extract 失败 (旁路): {e}")

        return entry.id
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[journal] 写 briefing SOAP 失败 (旁路): {e}", exc_info=True)
        return None
