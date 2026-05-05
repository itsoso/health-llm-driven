"""
运动前 'readiness 短稿' 生成 (产品改进 F).

故事:
  用户首页点 '马上要跑步' 按钮 → 立即拉本 service → voice-chat ?intent=preworkout
  → 私享女声: '今天 HRV 偏低 43ms, 电量 38. 建议把目标心率压到 Z2 (130-140), 跑 30 分钟即可.'
  → 进 listening 接 '好, 那我穿衣服了'

设计:
  - 复用 ExerciseRecoveryService.get_recovery_readiness (现成)
  - 60-100 字, 口语化, 给具体数字 + actionable 建议
  - readiness_level 决定建议强度:
      high     -> 可以放开练
      moderate -> 中等强度
      low      -> 降负荷, 给具体心率区间
      very_low -> 直接劝退, 改休息
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.services.exercise_recovery_service import ExerciseRecoveryService

logger = logging.getLogger(__name__)

_recovery_svc = ExerciseRecoveryService()


def build_preworkout_voice_script(
    db: Session,
    user_id: int,
    *,
    workout_type: Optional[str] = None,
) -> str:
    """生成跑前/练前 60-100 字语音稿. 没数据兜底文案.

    Args:
        workout_type: 用户预期运动 (running / cycling / strength / yoga / ...).
                      影响建议强度区间措辞.
    """
    try:
        readiness = _recovery_svc.get_recovery_readiness(db, user_id)
    except Exception as e:
        logger.warning(f"[preworkout_voice] readiness 失败 user={user_id}: {e}")
        return "准备运动了。还没拿到今天的状态数据，按平时强度练就行，注意热身。"

    score = readiness.get("readiness_score")
    level = readiness.get("readiness_level", "unknown")
    components = readiness.get("components", {})

    if score is None:
        return "准备运动了。今天 Garmin 数据还没同步好，按平时强度练就行，热身要做足。"

    # 抽关键负向信号 (HRV / sleep / battery / stress) 用于解释建议
    bits_diag = []
    hrv_s = components.get("hrv_score", 100)
    sleep_s = components.get("sleep_score", 100)
    bb_s = components.get("body_battery_score", 100)
    stress_s = components.get("stress_score", 100)

    if hrv_s < 50:
        bits_diag.append("HRV 偏低")
    if sleep_s < 60:
        bits_diag.append("昨晚没睡好")
    if bb_s < 40:
        bits_diag.append("身体电量不足")
    if stress_s < 40:  # 注意 stress_s = 100 - stress_level, 低意味压力高
        bits_diag.append("压力偏高")

    diag = "、".join(bits_diag[:2]) if bits_diag else ""
    activity = _activity_zh(workout_type)

    # 按 readiness 档位给建议
    if level == "high":
        if diag:
            advice = f"今天{diag}，但综合状态还不错（{score:.0f}分）。{activity}可以按计划练，但别加量。"
        else:
            advice = f"今天恢复得不错（{score:.0f}分），{activity}可以放开练。"
    elif level == "moderate":
        if diag:
            advice = f"今天{diag}，状态一般（{score:.0f}分）。建议{activity}降一档，目标心率压到 Z2-Z3。"
        else:
            advice = f"状态一般（{score:.0f}分）。{activity}走中等强度就行，别上阈值。"
    elif level == "low":
        advice = (
            f"今天{diag or '恢复不足'}（评分 {score:.0f}）。"
            f"建议把{activity}改成轻松节奏，目标心率压在 Z2 (130-140)，时长缩到 30 分钟。"
        )
    else:  # very_low
        advice = (
            f"今天{diag or '严重疲劳'}（评分 {score:.0f}）。"
            f"不太建议{activity}，今天以散步或拉伸为主，明天再练。"
        )

    return advice


def _activity_zh(workout_type: Optional[str]) -> str:
    if not workout_type:
        return "今天的训练"
    m = {
        "running": "跑步",
        "cycling": "骑行",
        "swimming": "游泳",
        "hiit": "HIIT",
        "strength": "力量训练",
        "cardio": "有氧",
        "yoga": "瑜伽",
        "walking": "散步",
        "hiking": "徒步",
    }
    return m.get(workout_type.lower(), "今天的训练")
