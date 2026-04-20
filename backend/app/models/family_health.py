"""家庭健康管理 Phase 2 模型 — 体检报告 + 用药管理 + 复查日历"""
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class MedicalReport(Base):
    """体检报告（AI 提取结构化数据）"""
    __tablename__ = "medical_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 报告基本信息
    report_date = Column(Date, nullable=False)                     # 体检日期
    hospital = Column(String(200), nullable=True)                  # 医院名称
    report_type = Column(String(50), default="general")            # general/blood/imaging/specialist
    title = Column(String(200), nullable=True)                     # 报告标题

    # 原始文件
    image_urls = Column(JSON, nullable=True)                       # 报告照片/PDF URL 列表

    # AI 提取结果
    extracted_items = Column(JSON, nullable=True)                  # [{name, value, unit, reference_range, is_abnormal, trend}]
    abnormal_items = Column(JSON, nullable=True)                   # 异常指标列表 [{name, value, severity, suggestion}]
    ai_summary = Column(Text, nullable=True)                       # AI 总结
    ai_suggestions = Column(JSON, nullable=True)                   # AI 建议列表
    raw_ocr_text = Column(Text, nullable=True)                     # OCR 原始文本（用于重新解析）

    # 状态
    status = Column(String(20), default="pending")                 # pending/processing/completed/failed

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('idx_medical_report_user_date', 'user_id', 'report_date'),
    )


class MedicalIndicator(Base):
    """体检指标时间线 — 唯一指标存储（PDF/图片/手动/CSV 统一写入）"""
    __tablename__ = "medical_indicators"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    report_id = Column(Integer, ForeignKey("medical_reports.id", ondelete="CASCADE"), nullable=True)
    exam_id = Column(Integer, ForeignKey("medical_exams.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(100), nullable=False)           # 指标名称（如"空腹血糖"）
    name_en = Column(String(100), nullable=True)         # 英文名（如"FBG"）
    item_code = Column(String(100), nullable=True)       # 标准编码（normalize_item_name 产出）
    category = Column(String(50), nullable=True)         # 分类：blood/liver/kidney/thyroid/lipid/glucose/other
    value = Column(Float, nullable=True)                 # 数值（影像等纯文字结果可为空）
    value_text = Column(Text, nullable=True)             # 非数值结果（影像结论等）
    unit = Column(String(50), nullable=True)             # 单位
    reference_low = Column(Float, nullable=True)         # 参考范围下限
    reference_high = Column(Float, nullable=True)        # 参考范围上限
    reference_range = Column(String(200), nullable=True) # 原始参考范围字符串
    is_abnormal = Column(Boolean, default=False)         # 是否异常
    severity = Column(String(20), nullable=True)         # normal/mild/moderate/severe
    result = Column(String(100), nullable=True)          # 描述性结果（偏高/阳性等）
    notes = Column(Text, nullable=True)
    source = Column(String(20), default="manual")        # manual/pdf_import/json_import/csv_import/image_ai
    record_date = Column(Date, nullable=False)           # 检测日期

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_indicator_user_name_date', 'user_id', 'name', 'record_date'),
        Index('idx_indicator_user_category', 'user_id', 'category'),
        Index('idx_indicator_user_code_date', 'user_id', 'item_code', 'record_date'),
    )


# 用药模型复用 app.models.medication.Medication / MedicationLog


class ReviewSchedule(Base):
    """复查计划"""
    __tablename__ = "review_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 复查项目
    item_name = Column(String(200), nullable=False)      # 如"空腹血糖"、"甲状腺功能"、"CT复查"
    category = Column(String(50), nullable=True)         # blood/imaging/specialist/other
    department = Column(String(100), nullable=True)      # 科室（如"内分泌科"）
    hospital = Column(String(200), nullable=True)        # 推荐医院

    # 时间
    last_check_date = Column(Date, nullable=True)        # 上次检查日期
    next_due_date = Column(Date, nullable=False)         # 下次到期日期
    interval_months = Column(Integer, nullable=True)     # 复查间隔（月）

    # 状态
    priority = Column(String(20), default="normal")      # low/normal/high/urgent
    status = Column(String(20), default="pending")       # pending/completed/overdue
    completed_date = Column(Date, nullable=True)         # 实际完成日期
    notes = Column(Text, nullable=True)                  # 备注

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('idx_review_user_due', 'user_id', 'next_due_date'),
        Index('idx_review_user_status', 'user_id', 'status'),
    )
