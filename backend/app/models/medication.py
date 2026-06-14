"""用药管理模型"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Text, Boolean, JSON, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Medication(Base):
    """药品定义"""
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(200), nullable=False)  # 药品名称
    dosage = Column(String(100))  # 用量（如 400mg）
    frequency = Column(String(100))  # 服用频率描述（如 每日2次）
    times_per_day = Column(Integer, default=1)  # 每日次数
    reminder_times = Column(JSON)  # 提醒时间 ["08:00", "20:00"]
    category = Column(String(50))  # 分类：处方药/非处方药/保健品
    purpose = Column(String(200))  # 用途/适应症
    side_effects = Column(Text)  # 已知副作用
    interactions = Column(Text)  # 药物相互作用提醒

    # 相对吃饭的服用时点 —— 复杂方案(如胃溃疡三联)无脑化的硬前提
    # PPI 要空腹/饭前、抗生素要饭后、铋剂要饭前；没有这个字段提醒只能报「该吃X」却说不出怎么吃
    timing_relation = Column(String(20))  # 相对吃饭的时点；NULL = 无特殊要求
    meal_anchor = Column(String(10))  # breakfast / lunch / dinner；哪一餐(可空)
    regimen_id = Column(Integer, ForeignKey("medication_regimens.id"))  # 属于哪个疗程方案(可空)

    start_date = Column(Date)  # 开始服用日期
    end_date = Column(Date)  # 计划结束日期
    is_active = Column(Boolean, default=True)  # 是否在服用中

    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="medications")
    logs = relationship("MedicationLog", back_populates="medication", lazy="dynamic")

    __table_args__ = (
        Index("ix_medications_user_active", "user_id", "is_active"),
    )


class MedicationLog(Base):
    """服药记录"""
    __tablename__ = "medication_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=False)

    taken_date = Column(Date, nullable=False)  # 服药日期
    taken_time = Column(String(10))  # 服药时间 "08:00"
    status = Column(String(20), nullable=False, default="taken")  # taken / skipped / delayed
    skip_reason = Column(String(200))  # 跳过原因
    actual_dosage = Column(String(100))  # 实际用量（如果与标准不同）
    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="medication_logs")
    medication = relationship("Medication", back_populates="logs")

    __table_args__ = (
        Index("ix_medication_logs_user_date", "user_id", "taken_date"),
        Index("ix_medication_logs_med_date", "medication_id", "taken_date"),
    )


class MedicationRegimen(Base):
    """用药方案 / 疗程(多阶段)。

    胃溃疡 Hp 根除是多阶段:根除期(14d,4 药)→ 愈合期(4–8w,1 药)。一条疗程串起多阶段,
    每阶段一组带时点的药。`phases` JSON 是「整套方案」的不可变快照;实际生效的药品是按
    current_phase 在 medications 表里实例化的(regimen_id 指回来)。阶段切换 = 停旧阶段药、
    建新阶段药(P1b 的 Celery 任务做)。

    定位:这是「执行/录入」工具,不是「开方」。phases 来自医生处方(选模板脚手架 / OCR / 手填),
    系统永不自动开方或调量。
    """
    __tablename__ = "medication_regimens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(200), nullable=False)  # "幽门螺杆菌根除·铋剂四联 + PPI 愈合"
    source = Column(String(40))  # template:<id> / ocr_prescription / manual
    template_id = Column(String(60))  # 若来自模板
    status = Column(String(20), default="active")  # active / completed / paused
    current_phase = Column(Integer, default=0)  # 0-based 当前阶段序号
    phases = Column(JSONB)  # [{name, duration_days, meds:[{name,dosage,times_per_day,reminder_times,timing_relation,meal_anchor}]}]
    review_on_complete = Column(Text)  # 疗程结束复查说明(接 medication_course_service)

    started_on = Column(Date)
    expected_end_on = Column(Date)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="medication_regimens")

    __table_args__ = (
        Index("ix_medication_regimens_user_status", "user_id", "status"),
    )


# ── 相对吃饭时点 → 中文执行指令 ───────────────────────────────────
# 纯函数，无副作用；service(today_status) 与 Celery 提醒任务共用，保证文案一致
_TIMING_LABELS = {
    "empty_stomach": "空腹",
    "before_meal_30": "饭前30分钟",
    "before_meal": "饭前",
    "with_meal": "随餐",
    "after_meal": "饭后",
    "bedtime": "睡前",
    "anytime": "",
}
_MEAL_LABELS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}


def medication_timing_label(timing_relation, meal_anchor=None) -> str:
    """把 (相对吃饭时点, 餐次) 渲染成中文执行指令。

    例：('before_meal_30','breakfast') → '早餐前30分钟'；('empty_stomach',None) → '空腹'；
    ('after_meal',None) → '饭后'。无要求 / 未知值 → 空串(调用方据此省略时点提示)。
    """
    if not timing_relation:
        return ""
    base = _TIMING_LABELS.get(timing_relation, "")
    if not base:
        return ""
    # 空腹 / 睡前 不挂餐次
    if timing_relation in ("empty_stomach", "bedtime"):
        return base
    meal = _MEAL_LABELS.get(meal_anchor or "")
    # 饭前/饭后/饭前30分钟 → 替换「饭」为具体餐次(早餐前30分钟)
    if meal and base.startswith("饭"):
        return base.replace("饭", meal, 1)
    return base
