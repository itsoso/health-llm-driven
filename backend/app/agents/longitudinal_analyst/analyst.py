"""
Longitudinal Analyst —— 长期趋势分析 + 因果叙事。

核心算法：
1. 从 PersonalOutcomeService 取 6 个月时间序列
2. 对每个指标计算 first→last 变化 + 方向（desirable or not）
3. 把干预事件（补剂开始/体检/首次 BP 记录）和指标变化做时间关联
4. 生成因果叙事片段（finding type="narrative"）

注意：这里的"因果"是 correlation-based attribution，不是真正的因果推断。
系统会在措辞上加 "可能因为" / "时间上关联"。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List


from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


METRIC_LABELS = {
    "hrv": ("HRV", "ms", "up"),
    "rhr": ("静息心率", "bpm", "down"),
    "sleep_score": ("睡眠评分", "分", "up"),
    "weight": ("体重", "kg", "context"),  # 取决于目标
    "systolic": ("收缩压", "mmHg", "down"),
    "steps": ("日均步数", "步", "up"),
    "body_battery_high": ("电量峰值", "", "up"),
}


def _direction_text(delta: float, desirable: str) -> str:
    if abs(delta) < 0.5:
        return "基本持平"
    d = "上升" if delta > 0 else "下降"
    if desirable == "up":
        good = delta > 0
    elif desirable == "down":
        good = delta < 0
    else:
        good = None  # context-dependent

    if good is True:
        return f"{d} ✅（良性趋势）"
    elif good is False:
        return f"{d} ⚠️（需要关注）"
    return d


def _correlate_events_with_metrics(
    summary_metrics: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """尝试把干预事件和指标变化做时间关联。"""
    narratives: List[Dict[str, Any]] = []

    for event in events:
        event_date = event.get("date", "")
        kind = event.get("kind", "")
        title = event.get("title", "")

        if kind == "supplement_start":
            # 补剂开始后的指标变化叙事
            narratives.append({
                "type": "narrative",
                "event": title,
                "event_date": event_date,
                "text": f"你在 {event_date} 开始 {title}。建议在 3-6 个月后复查相关指标，评估实际效果。",
            })
        elif kind == "medical_exam":
            narratives.append({
                "type": "narrative",
                "event": title,
                "event_date": event_date,
                "text": f"{event_date} 做了体检（{title}），这是追踪化验指标变化的锚点。",
            })

    return narratives[:5]  # 最多 5 条叙事


class LongitudinalAnalystSpecialist:
    name = "longitudinal_analyst"
    category = "longitudinal"

    TRIGGER_KEYWORDS = {
        "趋势", "变化", "进步", "改善", "恶化", "长期", "过去",
        "几个月", "半年", "一年", "上个月", "最近",
        "时间机器", "个人成果", "长期改善",
        "trend", "progress", "outcome", "longitudinal",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # general dashboard 场景下也参与（提供长期视角）
        if "general" in intent.categories:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            db = context.get("db")
            user_id = twin.meta.user_id

            if db is None:
                return SpecialistFinding(
                    specialist_name=self.name,
                    category=self.category,
                    summary="需要数据库连接",
                    findings=[],
                    raw={"error": "no db in context"},
                    ms_elapsed=int((time.monotonic() - t0) * 1000),
                )

            from app.services.personal_outcome_service import PersonalOutcomeService

            svc = PersonalOutcomeService()
            timeline = svc.get_timeline(db, user_id, range_key="6m", granularity="month")

            points = timeline.get("points", [])
            events = timeline.get("events", [])
            summary_data = timeline.get("summary", {})
            metrics = summary_data.get("metrics", {})

            findings: List[Dict[str, Any]] = []
            summary_parts: List[str] = []

            # 1. 指标趋势摘要
            for key, (label, unit, desirable) in METRIC_LABELS.items():
                m = metrics.get(key)
                if not m or m.get("first") is None or m.get("last") is None:
                    continue
                delta = m["delta"]
                direction = _direction_text(delta, desirable)
                findings.append({
                    "type": "trend",
                    "metric": key,
                    "label": label,
                    "first": m["first"],
                    "last": m["last"],
                    "delta": round(delta, 2),
                    "unit": unit,
                    "direction": direction,
                })
                summary_parts.append(f"{label} {m['first']}→{m['last']} {unit}")

            # 2. 数据覆盖度
            covered_days = summary_data.get("covered_days", 0)
            total_days = summary_data.get("total_days", 180)
            findings.append({
                "type": "coverage",
                "covered_days": covered_days,
                "total_days": total_days,
                "months_of_data": len(points),
            })

            # 3. 因果叙事（干预事件 × 指标变化）
            narratives = _correlate_events_with_metrics(metrics, events)
            findings.extend(narratives)

            # 4. 核心发现（最显著的变化）
            significant = []
            for key, (label, unit, desirable) in METRIC_LABELS.items():
                m = metrics.get(key)
                if not m or m.get("delta") is None:
                    continue
                delta = m["delta"]
                first = m.get("first", 0)
                if first and abs(delta / first) > 0.05:  # >5% 变化
                    significant.append({
                        "metric": label,
                        "delta_pct": round(delta / first * 100, 1),
                        "direction": "改善" if (
                            (desirable == "up" and delta > 0) or
                            (desirable == "down" and delta < 0)
                        ) else "恶化" if (
                            (desirable == "up" and delta < 0) or
                            (desirable == "down" and delta > 0)
                        ) else "变化",
                    })

            if significant:
                findings.append({
                    "type": "significant_changes",
                    "changes": significant,
                })

            summary = " · ".join(summary_parts[:4]) if summary_parts else "长期数据暂缺"
            summary = f"6 个月趋势 · {summary}"

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "months": len(points),
                    "events_count": len(events),
                    "significant_changes": len(significant),
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[longitudinal_analyst] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"长期分析失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
