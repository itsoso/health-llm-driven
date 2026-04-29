"""
ActionCard —— 对话产出固化到首页的行动卡片。

用户在 AI 助理对话中生成的有价值建议（训练计划、饮食方案、复查提醒等），
可以"钉"到智能助理首页，成为持久化的可跟踪行动项。

来源：
- conversation: 用户在对话中点📌或说"固化到首页"
- orchestrator: AI 主动建议固化
- manual: 用户手动创建
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ActionCard(Base):
    __tablename__ = "action_cards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 内容
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)  # markdown
    card_type = Column(String(30), default="note")  # plan / insight / recommendation / note
    color = Column(String(20))  # 可选颜色标签

    # 来源溯源
    source_type = Column(String(30), default="manual")  # conversation / orchestrator / manual
    source_id = Column(String(120))  # 原始消息 ID 或 conversation_id

    # 状态
    status = Column(String(20), default="active", index=True)  # active / completed / archived
    priority = Column(Integer, default=0)  # 越大越靠前
    is_visible = Column(Boolean, default=True)

    # 时间
    expires_at = Column(DateTime(timezone=True))  # 可选过期时间
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 干预效果追踪（Agent Native Phase 2）
    checklist = Column(JSON, default=list)  # [{"item": "约耳鼻喉科", "done": false}, ...]
    last_assessed_at = Column(DateTime(timezone=True))  # 上次 LLM 评估时间
    assessment_count = Column(Integer, default=0)  # 累计评估次数
    latest_assessment = Column(JSON)  # 最近一次评估结果 {"score":N, "summary":"..."}

    # 结构化干预字段：用于 Agent 把建议转成可验证实验
    metric_key = Column(String(50))  # sleep_score / hrv / rhr / weight / bp / spo2_odi / custom
    baseline_value = Column(String(100))
    target_value = Column(String(100))
    verification_days = Column(Integer)

    # 信任循环 (Outcome Tracking) — 用于 specialist hit-rate 计算
    creator_specialist = Column(String(64), index=True)  # recovery_coach / fuel_strategist / ...
    check_back_date = Column(DateTime(timezone=True), index=True)  # 自动评分日期
    actual_value = Column(String(100))      # 评分时拉到的实测值
    accuracy_score = Column(Integer)        # 0-100 命中度（None=未评分）
    graded_at = Column(DateTime(timezone=True))  # 评分时间
    grading_notes = Column(Text)            # 评分解释

    # 依从度信号 (Adherence) — 没有依从度的评分是噪声. 评分公式会 accuracy × adherence_confidence.
    # adherence_kind:
    #   'self_reported' — 用户 checklist 勾完成, 最弱信号 (默认置信度 0.5)
    #   'device'        — 设备数据证实 (睡眠时间提前 / 训练心率 / 步数达标等), 最强信号 (0.9)
    #   'proxy'         — 间接信号 (早餐打卡频率暗示起床规律等), 中等 (0.7)
    #   None            — 未评估依从度, 按 1.0 处理 (兼容历史卡)
    adherence_kind = Column(String(30))
    adherence_confidence = Column(Integer)  # 0-100 整数便于过滤查询 (0=完全没做, 100=完全做到)

    user = relationship("User", backref="action_cards")
