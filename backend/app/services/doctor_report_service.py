"""医生回路 (H3-7) - 报告导出 + 反馈入库.

Export: 合并近 N 天 Twin / safety / scorecard / SOAP / SpO2 模式 → 紧凑 markdown,
用户可以直接分享/打印给医生看.

反馈: ClinicalJournalEntry.created_by = 'doctor' + 自由文本 assessment/plan,
不需要新表, 自动进 case_thread 时间线.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.anomaly_alert import AnomalyAlert
from app.models.clinical_journal import ClinicalJournalEntry
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.user_directive import UserDirective
from app.services.outcome_safety import is_efficacy_score_eligible_card

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Export — 汇总为 markdown 或 structured dict
# ---------------------------------------------------------------------------


def build_doctor_export(
    db: Session, user_id: int, days: int = 30,
) -> Dict[str, Any]:
    """返回结构化字典 (含 markdown 文本).

    Keys: user_brief, window, vitals, directives, alerts,
          ai_scorecard, recent_journal, spo2_pattern, markdown
    """
    end = date.today()
    start = end - timedelta(days=days - 1)

    user = db.query(User).filter(User.id == user_id).first()
    user_brief = _user_brief(user)
    vitals = _vitals_summary(db, user_id, start, end)
    directives = _active_directives(db, user_id)
    alerts = _top_alerts(db, user_id, start)
    scorecard = _scorecard(db, user_id, start)
    journal = _recent_journal(db, user_id, limit=5)
    spo2 = _spo2_pattern(db, user_id, days=min(30, days))

    payload: Dict[str, Any] = {
        "user_brief": user_brief,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "vitals": vitals,
        "directives": directives,
        "alerts": alerts,
        "ai_scorecard": scorecard,
        "recent_journal": journal,
        "spo2_pattern": spo2,
    }
    payload["markdown"] = _render_markdown(payload)
    return payload


def _user_brief(user: Optional[User]) -> Dict[str, Any]:
    if not user:
        return {}
    age = None
    if user.birth_date:
        today = date.today()
        age = today.year - user.birth_date.year - (
            (today.month, today.day) < (user.birth_date.month, user.birth_date.day)
        )
    return {
        "name": user.name or "",
        "gender": user.gender or "",
        "age": age,
    }


def _vitals_summary(
    db: Session, user_id: int, start: date, end: date,
) -> Dict[str, Any]:
    rows = db.query(
        func.avg(GarminData.resting_heart_rate).label("rhr"),
        func.avg(GarminData.hrv).label("hrv"),
        func.avg(GarminData.sleep_score).label("sleep_score"),
        func.avg(GarminData.total_sleep_duration).label("sleep_min"),
        func.avg(GarminData.stress_level).label("stress"),
        func.avg(GarminData.steps).label("steps"),
        func.count(GarminData.id).label("samples"),
    ).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= start,
        GarminData.record_date <= end,
    ).first()

    def _round(x, digits=1):
        return round(float(x), digits) if x is not None else None

    return {
        "samples": int(rows.samples or 0) if rows else 0,
        "avg_rhr": _round(rows.rhr if rows else None, 0),
        "avg_hrv": _round(rows.hrv if rows else None, 1),
        "avg_sleep_score": _round(rows.sleep_score if rows else None, 0),
        "avg_sleep_hours": _round((rows.sleep_min / 60) if (rows and rows.sleep_min) else None, 1),
        "avg_stress": _round(rows.stress if rows else None, 0),
        "avg_steps": _round(rows.steps if rows else None, 0),
    }


def _active_directives(db: Session, user_id: int) -> List[Dict[str, Any]]:
    rows = db.query(UserDirective).filter(
        UserDirective.user_id == user_id,
        UserDirective.status == "active",
    ).order_by(UserDirective.effective_from.desc()).limit(20).all()
    return [
        {
            "kind": r.kind,
            "instruction": r.instruction,
            "source": r.source,
            "severity": r.severity,
            "medication_name": r.medication_name,
            "target_value": r.target_value,
        }
        for r in rows
    ]


def _top_alerts(
    db: Session, user_id: int, start: date, limit: int = 10,
) -> List[Dict[str, Any]]:
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    rows = db.query(AnomalyAlert).filter(
        AnomalyAlert.user_id == user_id,
        AnomalyAlert.created_at >= start_dt,
    ).order_by(AnomalyAlert.created_at.desc()).limit(limit).all()
    return [
        {
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "alert_type": a.alert_type,
            "metric_name": a.metric_name,
            "severity": a.severity,
            "message": a.message,
        }
        for a in rows
    ]


def _scorecard(db: Session, user_id: int, start: date) -> Dict[str, Any]:
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    scored_cards = db.query(ActionCard).filter(
        ActionCard.user_id == user_id,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= start_dt,
        ActionCard.accuracy_score.isnot(None),
    ).all()
    scores = [
        int(card.accuracy_score)
        for card in scored_cards
        if is_efficacy_score_eligible_card(card)
    ]

    total = len(scores)
    hits = sum(score >= 70 for score in scores)
    return {
        "total_graded": total,
        "hit_count": hits,
        "hit_rate_pct": round(hits / total * 100, 1) if total else 0.0,
        "avg_score": round(sum(scores) / total, 1) if total else 0.0,
    }


def _recent_journal(
    db: Session, user_id: int, limit: int = 5,
) -> List[Dict[str, Any]]:
    rows = db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.user_id == user_id,
    ).order_by(ClinicalJournalEntry.generated_at.desc()).limit(limit).all()
    return [
        {
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "created_by": r.created_by,
            "subjective": (r.subjective or "")[:300],
            "objective": (r.objective or "")[:300],
            "assessment": (r.assessment or "")[:400],
            "plan": (r.plan or "")[:300],
        }
        for r in rows
    ]


def _spo2_pattern(db: Session, user_id: int, days: int) -> Optional[Dict[str, Any]]:
    """复用 H2-6 的 longitudinal; 只取 pattern 部分, 避免循环 import."""
    try:
        from app.services.sleep.nocturnal_spo2_longitudinal import build_longitudinal
        res = build_longitudinal(db, user_id, days=days)
        p = res.get("pattern") or {}
        if p.get("covered_nights", 0) == 0:
            return None
        return p
    except Exception as e:
        logger.warning(f"[doctor_report] spo2 pattern failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Markdown 渲染
# ---------------------------------------------------------------------------


def _render_markdown(p: Dict[str, Any]) -> str:
    u = p.get("user_brief") or {}
    w = p.get("window") or {}
    v = p.get("vitals") or {}
    ds = p.get("directives") or []
    al = p.get("alerts") or []
    sc = p.get("ai_scorecard") or {}
    jr = p.get("recent_journal") or []
    sp = p.get("spo2_pattern")

    lines: List[str] = []
    lines.append(f"# 健康情况摘要（近 {w.get('days', '?')} 天）")
    lines.append("")
    lines.append(f"- 窗口: {w.get('start','?')} → {w.get('end','?')}")
    if u:
        info = []
        if u.get("name"):
            info.append(u["name"])
        if u.get("gender"):
            info.append(u["gender"])
        if u.get("age") is not None:
            info.append(f"{u['age']} 岁")
        if info:
            lines.append(f"- 用户: {' · '.join(info)}")
    lines.append("")

    # Vitals
    lines.append("## 可穿戴核心指标")
    if v.get("samples"):
        lines.append(f"- 采样天数: {v['samples']}")
        if v.get("avg_rhr") is not None:
            lines.append(f"- 平均静息心率: {v['avg_rhr']} bpm")
        if v.get("avg_hrv") is not None:
            lines.append(f"- 平均 HRV (overnight): {v['avg_hrv']} ms")
        if v.get("avg_sleep_score") is not None:
            lines.append(f"- 平均睡眠评分: {v['avg_sleep_score']}")
        if v.get("avg_sleep_hours") is not None:
            lines.append(f"- 平均睡眠时长: {v['avg_sleep_hours']} h")
        if v.get("avg_stress") is not None:
            lines.append(f"- 平均压力: {v['avg_stress']}")
        if v.get("avg_steps") is not None:
            lines.append(f"- 日均步数: {v['avg_steps']:.0f}")
    else:
        lines.append("- 暂无可穿戴数据")
    lines.append("")

    # SpO2 pattern
    if sp:
        lines.append("## 夜间 SpO2 模式 (近 30 天)")
        lines.append(f"- 有效夜数: {sp.get('covered_nights', 0)}"
                     f" (其中 {sp.get('nights_with_odi', 0)} 夜 ODI 可算)")
        if sp.get("avg_odi") is not None:
            lines.append(f"- 平均 ODI: {sp['avg_odi']}")
        if sp.get("median_min_spo2") is not None:
            lines.append(f"- 最低 SpO2 中位数: {sp['median_min_spo2']}%")
        if sp.get("pct_nights_odi_ge_5") is not None:
            lines.append(f"- ODI≥5 的夜占比: {sp['pct_nights_odi_ge_5'] * 100:.0f}%")
        if sp.get("pct_nights_min_spo2_below_90") is not None:
            lines.append(f"- min SpO2<90 的夜占比: {sp['pct_nights_min_spo2_below_90'] * 100:.0f}%")
        if sp.get("pct_events_in_rem") is not None:
            lines.append(f"- 事件集中在 REM 期占比: {sp['pct_events_in_rem'] * 100:.0f}%")
        flags = sp.get("pattern_flags") or []
        if flags:
            lines.append(f"- 观察到模式: {', '.join(flags)}")
        lines.append("")

    # Directives (医嘱 / 硬约束)
    if ds:
        lines.append("## 当前医嘱/硬约束")
        for d in ds[:10]:
            bits = [d.get("instruction", "") or ""]
            tags = []
            if d.get("severity"):
                tags.append(d["severity"])
            if d.get("source"):
                tags.append(d["source"])
            if tags:
                bits.append(f"({' · '.join(tags)})")
            lines.append(f"- {' '.join(bits).strip()}")
        lines.append("")

    # Alerts
    if al:
        lines.append("## 近期关键告警")
        for a in al:
            sev = f"[{a.get('severity','')}] " if a.get("severity") else ""
            ts = (a.get("created_at") or "")[:10]
            title = a.get("alert_type") or a.get("metric_name") or "alert"
            lines.append(f"- {ts} {sev}{title}: {a.get('message','')}")
        lines.append("")

    # AI scorecard
    if sc.get("total_graded"):
        lines.append("## AI 建议命中率")
        lines.append(f"- 评分条数: {sc['total_graded']}  ·  高分: {sc['hit_count']}"
                     f"  ·  命中率: {sc['hit_rate_pct']}%  ·  平均分: {sc['avg_score']}")
        lines.append("")

    # Recent Journal (SOAP)
    if jr:
        lines.append("## 近期 AI 分析记录 (SOAP)")
        for e in jr:
            ts = (e.get("generated_at", "") or "")[:10]
            by = e.get("created_by", "")
            lines.append(f"### {ts}  ({by})")
            for sec, key in [("S", "subjective"), ("O", "objective"),
                             ("A", "assessment"), ("P", "plan")]:
                val = e.get(key)
                if val:
                    lines.append(f"- **{sec}**: {val}")
            lines.append("")

    lines.append("")
    lines.append("---")
    lines.append("_本报告为 AI 辅助生成的摘要, 供医生参考, 不作诊断._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Feedback 入库: 写 ClinicalJournalEntry(created_by='doctor')
# ---------------------------------------------------------------------------


def record_doctor_feedback(
    db: Session, user_id: int,
    summary: Optional[str],
    assessment: Optional[str],
    plan: Optional[str],
    visit_date: Optional[date] = None,
) -> ClinicalJournalEntry:
    """把医生反馈以 SOAP 形式写入 clinical_journal_entries.

    summary → subjective (主诉/家属转述医生的话)
    assessment → assessment (医生的评估)
    plan → plan (医生开的下一步)
    """
    entry = ClinicalJournalEntry(
        user_id=user_id,
        subjective=(summary or "").strip() or None,
        objective=f"医生随访 @ {visit_date.isoformat()}" if visit_date else None,
        assessment=(assessment or "").strip() or None,
        plan=(plan or "").strip() or None,
        created_by="doctor",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_doctor_feedback(
    db: Session, user_id: int, limit: int = 20,
) -> List[ClinicalJournalEntry]:
    return db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.user_id == user_id,
        ClinicalJournalEntry.created_by == "doctor",
    ).order_by(ClinicalJournalEntry.generated_at.desc()).limit(limit).all()
