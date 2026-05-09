"""Episode Reflection Worker — Agent-Native v3 Increment 4 §1.

每天早上扫所有"刚关闭还没回填 Reflection"的 Episode, 拉次日生理数据 (HRV / Sleep),
计算 metrics_delta + 一句话 summary, 写回 EpisodeOutcome.

设计 dec:
  - 不进 LLM 调用 — Increment 4 §1 用确定性模板, 把信号产出来. LLM 可以下迭代叠加.
  - 仅处理 closed_at >= now - 48h 的 Episode (避免历史回灌打 LLM 月度账单).
  - 跑次日早晨 09:40 北京 = UTC 01:40 (Garmin 同步任务 01:30 完成, 数据已落).
  - 单批最多 100 条, 防御性上限.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


_LOOKBACK_HOURS = 48
_BATCH_LIMIT = 100


@celery_app.task(bind=True, time_limit=300, max_retries=0)
def run_episode_reflection(self):
    """对最近关闭、还没 Reflection 的 Episode 回填 metrics_delta + summary.

    Returns: {"reflected": N, "skipped_no_data": K}
    """
    from app.models.daily_health import GarminData
    from app.models.episode import EpisodeOutcome, HealthEpisode

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=_LOOKBACK_HOURS)

    reflected = 0
    skipped_no_data = 0

    with SessionLocal() as db:
        q = (
            db.query(HealthEpisode, EpisodeOutcome)
            .join(EpisodeOutcome, EpisodeOutcome.episode_id == HealthEpisode.id)
            .filter(
                HealthEpisode.status == "closed",
                HealthEpisode.closed_at >= cutoff,
                EpisodeOutcome.summary.is_(None),
            )
            .order_by(HealthEpisode.closed_at.desc())
            .limit(_BATCH_LIMIT)
        )
        rows = q.all()
        for ep, outcome in rows:
            try:
                delta, summary = _build_reflection(db, ep, outcome, GarminData)
            except Exception as e:
                logger.warning(
                    f"[Reflection] failed ep={ep.id}: {e}", exc_info=True,
                )
                continue
            if delta is None:
                skipped_no_data += 1
                continue
            outcome.metrics_delta = delta
            outcome.summary = summary
            reflected += 1
        if reflected:
            db.commit()

    if reflected or skipped_no_data:
        logger.info(
            f"[Reflection] swept reflected={reflected} skipped_no_data={skipped_no_data}"
        )
    return {"reflected": reflected, "skipped_no_data": skipped_no_data}


def _build_reflection(db, episode, outcome, GarminData):
    """计算单条 Episode 的 metrics_delta + summary.

    Returns: (delta_dict, summary_str) 或 (None, None) 表示数据不够还不能 reflect.
    """
    # 次日 = occurred_at 第二天 (本地时间 ≈ UTC 跑步当天的次日 record_date).
    next_date = (episode.occurred_at + timedelta(hours=12)).date() + timedelta(days=1)

    next_g = (
        db.query(GarminData)
        .filter(GarminData.user_id == episode.user_id)
        .filter(GarminData.record_date == next_date)
        .first()
    )
    if next_g is None:
        # 次日数据还没同步 — 留给明天再 reflect (loopback 48h 给了 ~2 次重试机会).
        return None, None

    # baseline 优先从 episode 触发时落的 7d HRV / 30d sleep 中位数读.
    base = episode.baseline_snapshot or {}
    hrv_baseline = base.get("hrv_7d_avg")
    sleep_min_baseline = base.get("sleep_total_min_30d")

    delta: dict = {}
    if next_g.hrv is not None:
        delta["hrv_next_morning"] = round(next_g.hrv, 1)
        # baseline 缺失就 fallback 用 GarminData.hrv_7day_avg
        baseline = hrv_baseline if hrv_baseline is not None else next_g.hrv_7day_avg
        if baseline:
            delta["hrv_delta_vs_baseline"] = round(next_g.hrv - baseline, 1)
    if next_g.sleep_score is not None:
        delta["sleep_score_next_night"] = next_g.sleep_score
    if next_g.total_sleep_duration is not None:
        delta["sleep_total_min_next_night"] = next_g.total_sleep_duration
        if sleep_min_baseline:
            delta["sleep_delta_min_vs_baseline"] = (
                next_g.total_sleep_duration - sleep_min_baseline
            )
    if next_g.deep_sleep_duration is not None:
        delta["deep_sleep_min_next_night"] = next_g.deep_sleep_duration

    if not delta:
        return None, None

    summary = _summary_text(episode, outcome, delta)
    return delta, summary


def _summary_text(episode, outcome, delta) -> str:
    """1-2 句中文 Reflection. 模板化, 避免 LLM 成本."""
    parts: list[str] = []

    rate = outcome.completion_rate or 0
    if outcome.actions_total > 0:
        if rate >= 0.99:
            parts.append("方案完整执行")
        elif rate >= 0.5:
            parts.append(
                f"完成 {outcome.actions_done}/{outcome.actions_total} 步"
            )
        else:
            parts.append(
                f"仅完成 {outcome.actions_done}/{outcome.actions_total} 步"
            )

    hrv_d = delta.get("hrv_delta_vs_baseline")
    if hrv_d is not None:
        if hrv_d >= 3:
            parts.append(f"次日 HRV 比基线高 {hrv_d:+.0f} ms,恢复良好")
        elif hrv_d <= -5:
            parts.append(f"次日 HRV 比基线低 {hrv_d:+.0f} ms,恢复偏弱,留意疲劳累积")
        else:
            parts.append(f"次日 HRV 与基线持平 ({hrv_d:+.0f} ms)")
    else:
        hrv_now = delta.get("hrv_next_morning")
        if hrv_now is not None:
            parts.append(f"次日 HRV {hrv_now} ms")

    sleep_score = delta.get("sleep_score_next_night")
    sleep_d = delta.get("sleep_delta_min_vs_baseline")
    if sleep_score is not None and sleep_d is not None:
        sign = "增加" if sleep_d > 0 else "减少"
        parts.append(f"睡眠评分 {sleep_score},较基线{sign} {abs(sleep_d)} 分钟")
    elif sleep_score is not None:
        parts.append(f"睡眠评分 {sleep_score}")

    if not parts:
        return "本次方案已闭环,数据待累积."
    return "。".join(parts) + "。"
