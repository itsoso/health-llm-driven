"""
周聊语音稿 (产品改进 E) — 周日 20:00 推送 + voice-chat 主动开口.

故事:
  周日晚 8 点 →  推送"本周聊聊?"
  → 用户点开进 voice-chat
  → 私享女声: "这周聊聊. 你跑了 3 次共 12 公里, 比上周多 2 公里;
              HRV 平均 48ms 偏低 3 天; 睡眠少了. 下周打算还是 3 次跑步吗?"
  → 用户接话 → AI 把"下周计划"写进 conversation/Memory
  → 周三检查 → 下周日复盘

设计:
  - 复用 _generate_weekly_report_for_user 的聚合查询 (steps/HRV/sleep/workout_count/weight_change)
  - 抽 3-5 个最有"故事性"的对比点 (本周 vs 上周, 偏离明显)
  - 末尾问一个"下周计划"开放性问题, 引导用户给目标
  - 80-150 字, 适合 TTS 播 12-20 秒
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _avg(records, field):
    vals = [getattr(r, field) for r in records if getattr(r, field) is not None]
    return sum(vals) / len(vals) if vals else None


def _delta_str(curr: Optional[float], prev: Optional[float], unit: str = "") -> str:
    """生成 '比上周多 2 公里' 这种对比片段; 偏离 < 5% 不强调"""
    if curr is None or prev is None or prev == 0:
        return ""
    diff = curr - prev
    pct = abs(diff) / prev * 100
    if pct < 5:
        return ""
    direction = "多" if diff > 0 else "少"
    if unit and abs(diff) >= 1:
        return f"比上周{direction} {abs(diff):.0f}{unit}"
    if unit:
        return f"比上周{direction} {abs(diff):.1f}{unit}"
    return f"比上周{direction} {abs(diff):.0f}"


def build_weekly_review_voice_script(
    db: Session,
    user_id: int,
    *,
    today: Optional[date] = None,
) -> str:
    """
    生成本周回顾语音稿 (80-150 字).
    没数据时返回兜底文案, 不抛异常.
    """
    from app.models.daily_health import GarminData, WorkoutRecord

    if today is None:
        today = date.today()

    this_end = today
    this_start = today - timedelta(days=7)
    last_start = this_start - timedelta(days=7)

    try:
        this_garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= this_start,
            GarminData.record_date < this_end,
        ).all()
        last_garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= last_start,
            GarminData.record_date < this_start,
        ).all()

        if not this_garmin:
            return (
                "这周聊聊。本周还没同步到健康数据，"
                "等手表数据上传后我再帮你做总结。"
                "下周有什么想做的吗？"
            )

        tw_sleep = _avg(this_garmin, "sleep_score")
        tw_hrv = _avg(this_garmin, "hrv")
        tw_rhr = _avg(this_garmin, "resting_heart_rate")
        lw_sleep = _avg(last_garmin, "sleep_score")
        lw_hrv = _avg(last_garmin, "hrv")
        lw_rhr = _avg(last_garmin, "resting_heart_rate")

        # 运动 — 真实 workout (Garmin 同步), 不是手动 exercise
        workouts = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= this_start,
            WorkoutRecord.workout_date < this_end,
        ).all()
        last_workouts = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= last_start,
            WorkoutRecord.workout_date < this_start,
        ).all()

        wcount = len(workouts)
        wkm = sum((w.distance_meters or 0) for w in workouts) / 1000
        lwkm = sum((w.distance_meters or 0) for w in last_workouts) / 1000

        # 拼故事 - 优先选偏离明显的指标
        bits = []

        # 运动: 次数 + 距离对比
        if wcount > 0:
            piece = f"你跑了 {wcount} 次共 {wkm:.0f} 公里"
            km_delta = _delta_str(wkm, lwkm, " 公里")
            if km_delta:
                piece += f"，{km_delta}"
            bits.append(piece)
        elif last_workouts:
            bits.append(f"这周没跑步，上周还跑了 {len(last_workouts)} 次")

        # HRV: 状态 + 对比
        if tw_hrv is not None:
            hrv_delta = _delta_str(tw_hrv, lw_hrv, "ms")
            if hrv_delta:
                bits.append(f"HRV 平均 {tw_hrv:.0f}ms，{hrv_delta}")
            elif tw_hrv < 40:
                bits.append(f"HRV 平均偏低，只有 {tw_hrv:.0f}ms")

        # 睡眠
        if tw_sleep is not None:
            sleep_delta = _delta_str(tw_sleep, lw_sleep, "分")
            if sleep_delta:
                bits.append(f"睡眠评分 {tw_sleep:.0f}，{sleep_delta}")
            elif tw_sleep < 70:
                bits.append(f"睡眠评分 {tw_sleep:.0f}，有点低")

        # 静息心率: 高了不好
        if tw_rhr is not None and lw_rhr is not None:
            rhr_diff = tw_rhr - lw_rhr
            if rhr_diff >= 3:
                bits.append(f"静息心率比上周高 {rhr_diff:.0f}下")

        # 兜底: 至少要有 1-2 句故事
        if not bits:
            bits.append("整体数据稳定，没有明显波动")

        # 取前 3 句, 太多 TTS 听起来罗嗦
        story = "，".join(bits[:3]) + "。"

        # 末尾问一个开放问题 (Agent Native: 让用户接话, 内容会写 conversation)
        question = "下周想怎么安排？还是这个节奏，还是想调一调？"

        script = f"这周聊聊。{story}{question}"
        return script

    except Exception as e:
        logger.warning(f"[weekly_review_voice] user={user_id} 失败: {e}")
        return "这周聊聊。下周有什么想调整的吗？"
