"""
Anomaly alert clarification — 告警的"主动澄清对话"开场白模板.

Agent Native 闭环设计:
  告警 (anomaly_alert) 不是终点, 是对话起点.
  推送时附带 intent=clarify, 用户点开 voice-chat → AI 主动开口问 follow-up,
  收集用户的语境信息 → 写 conversation 历史 → 下次告警更精准.

每个 alert_type 配:
  opener:   AI 一开场说的话 (口语化, 60-120 字, 适合 TTS)
  questions: 优先问哪几个 follow-up (内含 hypothesis, 让用户验证或反驳)
  rationale: 用户接话后, AI 应该如何决策 (LLM prompt context)

返回结果可被 voice-chat 拉取后, 第一句直接 TTS 播 (类似晨间简报 speakDirect).
"""
from __future__ import annotations

from typing import Optional

from app.models.anomaly_alert import AnomalyAlert


# alert_type → (opener, hypothesis_questions, rationale)
# opener 必须口语化 + 短, 适合私享女声朗读. 不要堆砌专业术语.
_TEMPLATES: dict[str, dict] = {
    "spo2_low": {
        "opener_template": (
            "嗨，我注意到你{nights_count}晚血氧偏低，最低到了{min_value}。"
            "我有几个判断想跟你确认一下。"
            "最近是不是侧睡或者枕头比平时高？另外，鼻子有没有不通气？"
        ),
        "fallback_opener": (
            "嗨，我注意到你这几晚血氧偏低。最近是不是侧睡或者枕头比平时高？另外鼻子有没有不通气？"
        ),
        "rationale": (
            "用户最近 SpO2 低于 92 多次. 优先确认: 1) 睡姿/枕头变化 (机械性气道) "
            "2) 鼻塞 (上呼吸道) 3) 室内空气 (灰尘/低氧). "
            "拿到答案后给具体建议 (换低枕/侧睡变仰卧/通鼻). 不要给医疗诊断."
        ),
    },
    "hrv_drop": {
        "opener_template": (
            "嗨，{nights_count}晚你的 HRV 都比平时低不少。"
            "想跟你聊聊。最近是不是工作压力大？或者训练强度突然加了？"
        ),
        "fallback_opener": (
            "嗨，你最近几晚 HRV 偏低。最近是不是工作压力大或者训练量加大了？"
        ),
        "rationale": "确认: 压力 / 训练负荷 / 饮酒 / 睡眠不规律. 给降负荷建议.",
    },
    "rhr_spike": {
        "opener_template": (
            "嗨，最近你的静息心率比平时高了{delta}下。"
            "想问一下，最近是不是有点感冒或者酒喝多了？"
        ),
        "fallback_opener": (
            "嗨，最近你的静息心率比平时偏高。最近是不是感冒、压力大或者酒喝多了？"
        ),
        "rationale": "RHR 持续偏高 = 感染/应激/恢复不良. 排除常见原因.",
    },
    "sleep_low": {
        "opener_template": (
            "嗨，{nights_count}晚你只睡了{hours}小时。"
            "想问一下，是工作忙、还是入睡有困难？"
        ),
        "fallback_opener": "嗨，你最近睡眠时长偏少。是工作忙、还是入睡有困难？",
        "rationale": "睡眠不足. 确认是行为型 (晚睡) 还是入睡困难 (睡眠卫生).",
    },
    "stress_high": {
        "opener_template": (
            "嗨，你这几天的压力指标都偏高。最近是工作上的事，"
            "还是有什么让你睡不好？"
        ),
        "fallback_opener": "嗨，你最近压力指标偏高。最近是工作上的事，还是有什么让你睡不好？",
        "rationale": "压力高. 区分情境性 (deadline) vs 长期 (失眠焦虑).",
    },
}


def get_clarification_opener(alert: AnomalyAlert) -> Optional[dict]:
    """
    根据 alert 拿对应的开场白模板 + 填充数据.

    返回:
      None — 该 alert_type 没有 clarify 模板, 用户应当走原路径 (trace 详情)
      {
        "opener": "嗨, 我注意到你...",   # AI 第一句开场白, 直接 TTS
        "rationale": "...",              # 后续用户接话时给 LLM 的 system prompt 补充
        "alert_type": "spo2_low",
        "alert_id": 123,
      }
    """
    tmpl = _TEMPLATES.get(alert.alert_type)
    if not tmpl:
        return None

    # AnomalyAlert 字段: current_value / baseline_value / threshold_value (Float).
    # 不同 alert_type 的语义含义:
    #   spo2_low      current=最低 SpO2,   baseline=7d 均值
    #   hrv_drop      current=昨夜 HRV,    baseline=7d 均值
    #   rhr_spike     current=昨日 RHR,    baseline=7d 均值
    #   sleep_low     current=昨夜睡眠 h,  baseline=7d 均值
    cur = alert.current_value
    base = alert.baseline_value

    delta_str = "几"
    if cur is not None and base is not None:
        delta_str = str(int(abs(base - cur))) if abs(base - cur) >= 1 else f"{abs(base - cur):.1f}"

    try:
        opener = tmpl["opener_template"].format(
            nights_count="近几",  # 暂时用'近几晚', 没有 explicit 计数字段; 后续可从 ActionCard / 历史 alert 算
            min_value=int(cur) if alert.alert_type == "spo2_low" and cur else "90",
            delta=delta_str,
            hours=f"{cur:.1f}" if alert.alert_type == "sleep_low" and cur else "几个",
        )
    except (KeyError, ValueError):
        opener = tmpl["fallback_opener"]

    return {
        "opener": opener,
        "rationale": tmpl["rationale"],
        "alert_type": alert.alert_type,
        "alert_id": alert.id,
    }
