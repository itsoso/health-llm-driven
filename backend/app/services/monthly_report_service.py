"""MonthlyReportService — 生成月度复盘报告.

组合已有原语：
- PersonalOutcomeService.get_timeline() → 指标 + 干预事件
- ActionCard 查询 → 命中率 / top hits / top misses
- 简单启发式生成 narrative + next_focus（不调 LLM，避免月初批量跑时的成本）
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.monthly_report import MonthlyReport
from app.services.outcome_safety import is_efficacy_score_eligible_card
from app.services.personal_outcome_service import PersonalOutcomeService

logger = logging.getLogger(__name__)

# TimelinePoint 的扁平字段 → (label, unit, desirable_direction)
METRIC_META = {
    "hrv":               ("HRV",           "ms",   "up"),
    "rhr":               ("静息心率",       "bpm",  "down"),
    "sleep_score":       ("睡眠评分",       "分",    "up"),
    "weight_kg":         ("体重",           "kg",   "context"),
    "systolic":          ("收缩压",         "mmHg", "down"),
    "steps":             ("日均步数",       "步",    "up"),
    "body_battery_high": ("电量峰值",       "",     "up"),
}

SPECIALIST_LABEL = {
    "recovery_coach": "恢复",
    "fuel_strategist": "营养",
    "movement_coach": "运动",
    "mental_health_companion": "心理",
    "hypertension_specialist": "高血压",
    "metabolic_specialist": "代谢",
    "rhinitis_specialist": "鼻炎",
    "safety_guardian": "安全",
    "knowledge_librarian": "知识",
    "longitudinal_analyst": "趋势",
}


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    _, last = monthrange(year, month)
    end = date(year, month, last)
    return start, end


def _direction(delta: float, desirable: str) -> str:
    if abs(delta) < 0.5:
        return "basically_flat"
    if desirable == "up":
        return "improved" if delta > 0 else "regressed"
    if desirable == "down":
        return "improved" if delta < 0 else "regressed"
    return "changed"


class MonthlyReportService:
    """月度复盘生成器."""

    def __init__(self) -> None:
        self._outcome = PersonalOutcomeService()

    # ------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------

    def get_or_generate(
        self, db: Session, user_id: int, year: int, month: int,
        force: bool = False,
    ) -> MonthlyReport:
        existing = (
            db.query(MonthlyReport)
            .filter_by(user_id=user_id, year=year, month=month)
            .first()
        )
        if existing and not force:
            return existing

        report_data = self._build_report_data(db, user_id, year, month)

        if existing and force:
            existing.report_data = report_data
            existing.generated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            return existing

        row = MonthlyReport(
            user_id=user_id, year=year, month=month,
            report_data=report_data,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_reports(
        self, db: Session, user_id: int, limit: int = 24,
    ) -> List[MonthlyReport]:
        return (
            db.query(MonthlyReport)
            .filter_by(user_id=user_id)
            .order_by(MonthlyReport.year.desc(), MonthlyReport.month.desc())
            .limit(limit)
            .all()
        )

    # ------------------------------------------------------------
    # 内部构建
    # ------------------------------------------------------------

    def _build_report_data(
        self, db: Session, user_id: int, year: int, month: int,
    ) -> Dict[str, Any]:
        start, end = _month_range(year, month)
        days_in_month = (end - start).days + 1

        # 复用 timeline (取 6 个月，按月聚合，本月 + 上月比对)
        timeline = self._outcome.get_timeline(
            db, user_id, range_key="6m", granularity="month",
        )
        points = timeline.get("points", []) or []
        events_all = timeline.get("events", []) or []

        # 提取本月 / 上月的点
        curr_bucket = f"{year:04d}-{month:02d}"
        prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
        prev_bucket = f"{prev_y:04d}-{prev_m:02d}"

        curr_point = next((p for p in points if p.get("bucket") == curr_bucket), None)
        prev_point = next((p for p in points if p.get("bucket") == prev_bucket), None)

        metric_trends = self._build_metric_trends(curr_point, prev_point)
        ai_scorecard = self._build_ai_scorecard(db, user_id, start, end)
        key_interventions = self._build_interventions(events_all, start, end)
        coverage = self._build_coverage(curr_point, days_in_month)
        narrative, next_focus = self._build_narrative(
            metric_trends, ai_scorecard, key_interventions,
        )

        return {
            "period": {
                "year": year,
                "month": month,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days_in_month": days_in_month,
            },
            "coverage": coverage,
            "metric_trends": metric_trends,
            "ai_scorecard": ai_scorecard,
            "key_interventions": key_interventions,
            "narrative": narrative,
            "next_focus": next_focus,
        }

    def _build_metric_trends(
        self,
        curr: Optional[Dict[str, Any]],
        prev: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """TimelinePoint 字段是扁平的 (hrv/rhr/sleep_score/...)."""
        if not curr:
            return []

        trends: List[Dict[str, Any]] = []
        for key, (label, unit, desirable) in METRIC_META.items():
            cv = curr.get(key)
            if cv is None:
                continue
            pv = (prev or {}).get(key) if prev else None
            delta = (cv - pv) if pv is not None else 0.0
            pct = (delta / pv * 100) if pv else None

            trends.append({
                "metric": key,
                "label": label,
                "unit": unit,
                "curr": round(float(cv), 2),
                "prev": round(float(pv), 2) if pv is not None else None,
                "delta": round(float(delta), 2),
                "delta_pct": round(pct, 1) if pct is not None else None,
                "direction": _direction(delta, desirable),
                "desirable": desirable,
            })
        return trends

    def _build_ai_scorecard(
        self, db: Session, user_id: int, start: date, end: date,
    ) -> Dict[str, Any]:
        """本月内 graded_at 落在窗口内的 ActionCard 命中率."""
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)

        scored_cards = db.query(ActionCard).filter(
            ActionCard.user_id == user_id,
            ActionCard.graded_at.isnot(None),
            ActionCard.graded_at >= start_dt,
            ActionCard.graded_at <= end_dt,
            ActionCard.accuracy_score.isnot(None),
        ).all()
        eligible_cards = [
            card for card in scored_cards if is_efficacy_score_eligible_card(card)
        ]
        scores = [int(card.accuracy_score) for card in eligible_cards]
        total = len(scores)
        hits = sum(score >= 70 for score in scores)
        misses = sum(score <= 30 for score in scores)

        overall = {
            "total_graded": total,
            "hit_count": hits,
            "miss_count": misses,
            "avg_score": round(sum(scores) / total, 1) if total else 0.0,
            "hit_rate": round(hits / total * 100, 1) if total else 0.0,
        }

        by_specialist_scores: dict[str, list[int]] = {}
        for card in eligible_cards:
            if card.creator_specialist:
                by_specialist_scores.setdefault(card.creator_specialist, []).append(
                    int(card.accuracy_score)
                )

        by_specialist = sorted(
            [
                {
                    "name": specialist,
                    "label": SPECIALIST_LABEL.get(specialist, specialist),
                    "total": len(specialist_scores),
                    "hits": sum(score >= 70 for score in specialist_scores),
                    "hit_rate": round(
                        sum(score >= 70 for score in specialist_scores)
                        / len(specialist_scores) * 100,
                        1,
                    ),
                    "avg_score": round(
                        sum(specialist_scores) / len(specialist_scores), 1
                    ),
                }
                for specialist, specialist_scores in by_specialist_scores.items()
            ],
            key=lambda x: -x["hit_rate"],
        )

        def _card(c: ActionCard) -> dict:
            return {
                "card_id": c.id,
                "title": c.title,
                "metric": c.metric_key,
                "score": int(c.accuracy_score or 0),
                "specialist": c.creator_specialist,
                "graded_at": c.graded_at.isoformat() if c.graded_at else None,
            }

        top_hits = sorted(
            (card for card in eligible_cards if card.accuracy_score >= 70),
            key=lambda card: card.accuracy_score,
            reverse=True,
        )[:3]
        top_misses = sorted(
            (card for card in eligible_cards if card.accuracy_score <= 30),
            key=lambda card: card.accuracy_score,
        )[:3]

        return {
            "overall": overall,
            "by_specialist": by_specialist,
            "top_hits": [_card(c) for c in top_hits],
            "top_misses": [_card(c) for c in top_misses],
        }

    def _build_interventions(
        self, events: List[Dict[str, Any]], start: date, end: date,
    ) -> List[Dict[str, Any]]:
        kept: List[Dict[str, Any]] = []
        s, e = start.isoformat(), end.isoformat()
        for ev in events:
            d = ev.get("date", "")
            if s <= d <= e:
                kept.append({
                    "date": d,
                    "kind": ev.get("kind"),
                    "title": ev.get("title"),
                    "detail": ev.get("detail"),
                })
        # 按时间升序 → 最多 6 个
        kept.sort(key=lambda x: x.get("date", ""))
        return kept[:6]

    def _build_coverage(
        self, curr_point: Optional[Dict[str, Any]], days_in_month: int,
    ) -> Dict[str, Any]:
        covered = int((curr_point or {}).get("samples", 0) or 0)
        pct = round(covered / days_in_month * 100, 1) if days_in_month else 0.0
        return {
            "covered_days": covered,
            "total_days": days_in_month,
            "pct": pct,
        }

    def _build_narrative(
        self,
        trends: List[Dict[str, Any]],
        scorecard: Dict[str, Any],
        interventions: List[Dict[str, Any]],
    ) -> tuple[str, List[str]]:
        """启发式生成 narrative + next_focus，避免月初批量 LLM 成本."""
        parts: List[str] = []
        focus: List[str] = []

        improved = [t for t in trends if t["direction"] == "improved"]
        regressed = [t for t in trends if t["direction"] == "regressed"]

        if improved:
            names = "、".join(t["label"] for t in improved[:3])
            parts.append(f"本月 {names} 改善。")
        if regressed:
            names = "、".join(t["label"] for t in regressed[:3])
            parts.append(f"{names} 有退步，值得关注。")
            for t in regressed[:2]:
                focus.append(f"盯 {t['label']}（当前 {t['curr']}{t['unit']}，对比上月{'升' if t['delta'] > 0 else '降'} {abs(t['delta']):.1f}{t['unit']}）")

        overall = scorecard.get("overall", {})
        total = overall.get("total_graded", 0)
        if total:
            parts.append(
                f"AI 建议命中率 {overall.get('hit_rate', 0):.0f}%（{total} 条评分）。"
            )

        by_sp = scorecard.get("by_specialist", [])
        if by_sp:
            top = by_sp[0]
            if top.get("hit_rate", 0) >= 60:
                parts.append(f"{top['label']}方向的建议贴合度最高。")
                focus.append(f"延续{top['label']}类行动")
            tail = by_sp[-1] if len(by_sp) > 1 else None
            if tail and tail.get("hit_rate", 0) <= 30 and tail["total"] >= 3:
                parts.append(f"{tail['label']}方向的建议偏离较多，下月收敛。")

        if interventions:
            parts.append(f"本月关键干预 {len(interventions)} 次。")

        if not focus:
            focus.append("维持现有节奏，持续记录以积累数据")

        narrative = " ".join(parts) or "本月数据较少，建议提高打卡与数据同步频率。"
        return narrative, focus[:3]
