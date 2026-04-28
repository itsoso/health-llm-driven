"""
User Directive — "硬性指令", specialist 必须遵循.

注: 本系统不提供医疗服务. 涉及用药/化验目标的决策, 应由用户和其执业医师确认后,
作为指令录入. 系统的角色是执行用户授权的约束, 不是医疗判断方.

设计原则:
1. specialist 跑评估时优先读 active directives, 与 specialist 原始判断冲突 → 听 directive
2. directives 来自:
   - 外部 Telegram 通道 (用户/健康教练/家人 输入, LLM 解析为结构化)
   - 用户自己设置 (web/mobile UI)
   - 体检报告里的备注条目
3. 类型化:
   - medication_change:  '继续/停用/更换/调整剂量' 某药 (须用户已与医生确认)
   - target_override:    '把 LDL 目标设到 < 2.6' (覆盖 specialist 默认)
   - lifestyle:          '严格戒酒 30 天' / '低钠饮食'
   - watch_metric:       '每天测血压, 收缩压 > 135 立刻提醒'
   - skip_recommendation: '不要给我推鱼油了'
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base


class UserDirective(Base):
    __tablename__ = "user_directives"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # 类型 — 决定 specialist 在 prompt 里如何注入
    kind = Column(String(40), nullable=False, index=True)
    # 'medication_change' / 'target_override' / 'lifestyle' / 'watch_metric' / 'skip_recommendation'

    # 自然语言 (主要内容)
    instruction = Column(Text, nullable=False)

    # 结构化字段 (可选, 帮 specialist 编程式访问)
    metric_key = Column(String(50))           # 关联的 metric (LDL/BP/...)
    target_value = Column(String(100))        # 比如 'LDL < 2.6'
    medication_name = Column(String(100))     # 药品名
    severity = Column(String(20))             # advisory / strong / mandatory

    # 来源 (审计)
    source = Column(String(40), default="manual", index=True)
    # 'external_telegram' / 'user_self' / 'medical_exam_parsed' / 'manual'
    source_message_id = Column(String(100))   # Telegram message_id / 等

    # 生命周期
    status = Column(String(20), default="active", index=True)
    # 'active' / 'expired' / 'revoked'
    effective_from = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))    # NULL = 永久

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    revoked_reason = Column(String(200))

    __table_args__ = (
        Index('idx_user_directive_user_status', 'user_id', 'status'),
        Index('idx_user_directive_user_metric', 'user_id', 'metric_key'),
    )
