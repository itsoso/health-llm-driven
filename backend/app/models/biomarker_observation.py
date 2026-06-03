"""BiomarkerObservation — 归一化后的生物标志物观测 (PRD P1 数据底座 #2, G3).

每条 = 一个体检项被归一化后的标准观测:
  - code: canonical 生物标志物代码 (ALT / lipid_ldl / UA ...)
  - value/unit: 原始值与单位 (审计用)
  - normalized_value/normalized_unit: 换算到标准单位后的值
  - ref_low/ref_high + flag: 按性别/年龄解析出的参考范围与位置 (low/normal/high)
  - is_risk: 偏离方向是否为风险 (HDL/eGFR 偏低才是风险, 见 definitions.higher_is_risk)
  - source_exam_item_id: 溯源到 MedicalExamItem
  - confidence: 单位换算/范围命中 → high/medium/low

这是"标准化数据底座": 趋势、风险分层、复查 delta 都基于 observation 而非原始项目名。
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from app.database import Base


class BiomarkerObservation(Base):
    __tablename__ = "biomarker_observations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    code = Column(String(40), nullable=False, index=True)   # canonical biomarker code
    domain = Column(String(24), index=True)                 # lipid/glucose/liver/kidney/metabolic

    value = Column(Float)                                    # 原始值
    unit = Column(String(32))                                # 原始单位
    normalized_value = Column(Float, nullable=False)
    normalized_unit = Column(String(32), nullable=False)

    ref_low = Column(Float)
    ref_high = Column(Float)
    flag = Column(String(12))                                # low / normal / high / unknown
    abnormal = Column(Boolean, default=False, index=True)
    is_risk = Column(Boolean, default=False)
    confidence = Column(String(12))                          # high / medium / low

    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)  # 体检日期
    source_exam_item_id = Column(Integer, ForeignKey("medical_exam_items.id", ondelete="SET NULL"))
    source = Column(String(20))                              # manual/ocr/pdf/...

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_biomarker_obs_user_code_observed", "user_id", "code", "observed_at"),
        Index("idx_biomarker_obs_user_abnormal", "user_id", "abnormal"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BiomarkerObservation user={self.user_id} {self.code}={self.normalized_value}{self.normalized_unit} {self.flag}>"
