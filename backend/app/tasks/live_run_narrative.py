"""跑后 LLM 复盘任务 (Live Run Coach Phase 4).

end_run API 触发, 异步生成 narrative:
  - 今天表现 (1 段)
  - 1 个具体改进点
  - 明天建议 (休 / easy / 同强度)

输入:
  - LiveRunSession (events, gps_samples, 配速, 时长)
  - Digital Health Twin (readiness / 鼻炎 / AQI / 历史 7 天跑量)

设计:
  - 失败旁路, 不影响主流程
  - narrative_status: pending → running → completed / failed
  - 时长 < 60s 或 距离 < 100m 直接 skip (无意义)
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.live_run import LiveRunSession
from app.models.user import User

logger = logging.getLogger(__name__)


NARRATIVE_PROMPT = """你是跑步教练, 基于本次跑步数据给出简短复盘.

**本次跑步**:
- 距离: {distance_km:.2f} km
- 时长: {duration_str}
- 平均配速: {avg_pace_str}/km
- 目标配速: {target_pace_str}/km ({target_label})
- 实时提示触发: {events_summary}

**用户当前状态 (Digital Health Twin)**:
{twin_blob}

**最近 7 天跑量**:
{recent_runs_summary}

请用中文回复, 严格按以下格式 (3 段, 每段 ≤ 50 字):

【今天表现】<一句话评价: 配速控制 / 完成度 / 状态>
【改进建议】<最值得改的 1 件具体事, 不要空泛>
【明天建议】<休息 / Easy 慢跑 / 同强度 三选一, 给一句理由>"""


def _format_pace(seconds: int | None) -> str:
    if not seconds or seconds <= 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}小时{m}分"
    return f"{m}分{s}秒"


def _summarize_events(events: list) -> str:
    if not events:
        return "无 (节奏稳定)"
    counts: dict[str, int] = {}
    for e in events:
        rid = e.get("rule_id", "unknown") if isinstance(e, dict) else "unknown"
        counts[rid] = counts.get(rid, 0) + 1
    parts = []
    label_map = {
        "pace_drift": "配速偏快",
        "hr_zone_overload": "心率高区",
        "total_load_exceeded": "总量超限",
    }
    for rid, n in counts.items():
        parts.append(f"{label_map.get(rid, rid)} ×{n}")
    return ", ".join(parts)


def _summarize_recent_runs(db, user_id: int, exclude_id: int) -> str:
    cutoff = datetime.now(UTC) - timedelta(days=7)
    rows = (
        db.query(LiveRunSession)
        .filter(LiveRunSession.user_id == user_id)
        .filter(LiveRunSession.id != exclude_id)
        .filter(LiveRunSession.started_at >= cutoff)
        .filter(LiveRunSession.aborted == False)  # noqa: E712
        .order_by(LiveRunSession.started_at.desc())
        .limit(7)
        .all()
    )
    if not rows:
        return "(本周首次记录跑步)"
    total_km = sum((r.total_distance_m or 0) / 1000 for r in rows)
    total_min = sum((r.total_duration_s or 0) / 60 for r in rows)
    return f"{len(rows)} 次, 累计 {total_km:.1f} km / {total_min:.0f} 分钟"


@celery_app.task(name="app.tasks.live_run_narrative.generate_narrative", bind=True, max_retries=2)
def generate_narrative(self, run_id: int) -> dict:
    """为单次 LiveRunSession 生成复盘 narrative."""
    from app.twin.builder import build_twin
    from app.twin.formatter import twin_to_prompt_blob
    from app.services.llm.factory import create_llm_provider
    from app.services.llm.usage_tracker import set_caller

    with SessionLocal() as db:
        s = db.query(LiveRunSession).filter(LiveRunSession.id == run_id).first()
        if s is None:
            logger.warning(f"[live-run-narrative] run {run_id} not found")
            return {"status": "not_found"}

        # Skip 无意义记录
        if (s.total_distance_m or 0) < 100 or (s.total_duration_s or 0) < 60 or s.aborted:
            s.narrative = None
            s.narrative_status = "skipped"
            db.commit()
            return {"status": "skipped", "reason": "too_short_or_aborted"}

        s.narrative_status = "running"
        db.commit()

        try:
            set_caller("live_run_narrative.generate", user_id=s.user_id)
            twin = build_twin(db, s.user_id)
            twin_blob = twin_to_prompt_blob(twin) or "(无 Twin 数据)"

            prompt = NARRATIVE_PROMPT.format(
                distance_km=(s.total_distance_m or 0) / 1000,
                duration_str=_format_duration(s.total_duration_s or 0),
                avg_pace_str=_format_pace(s.avg_pace_seconds),
                target_pace_str=_format_pace(s.target_pace_seconds),
                target_label=s.target_label or "easy",
                events_summary=_summarize_events(s.events or []),
                twin_blob=twin_blob[:1500],
                recent_runs_summary=_summarize_recent_runs(db, s.user_id, s.id),
            )

            provider = create_llm_provider(None)
            if provider is None:
                raise RuntimeError("no llm provider available")

            response = asyncio.run(provider.chat(
                messages=[
                    {"role": "system", "content": "你是经验丰富的跑步教练, 回复必须按指定格式, 不超过 200 字."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=400,
            ))
            narrative = response.strip() if isinstance(response, str) else str(response)
            if not narrative:
                raise RuntimeError("empty narrative")

            s.narrative = narrative
            s.narrative_status = "completed"
            db.commit()
            logger.info(f"[live-run-narrative] run {run_id} narrative ok ({len(narrative)} chars)")
            return {"status": "ok", "length": len(narrative)}

        except Exception as e:
            logger.warning(f"[live-run-narrative] run {run_id} failed: {e}")
            s.narrative_status = "failed"
            db.commit()
            try:
                raise self.retry(exc=e, countdown=60)
            except self.MaxRetriesExceededError:
                return {"status": "failed", "error": str(e)}
