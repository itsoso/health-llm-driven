"""SpO2 血氧时间序列 Pydantic schemas"""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


class SpO2Point(BaseModel):
    timestamp: int = Field(..., description="毫秒时间戳")
    time: str = Field(..., description="HH:MM")
    value: int = Field(..., description="SpO2 %")


class SpO2NightSummary(BaseModel):
    record_date: date
    avg_spo2: Optional[float] = None
    min_spo2: Optional[int] = None
    max_spo2: Optional[int] = None
    below_90_count: int = 0
    desaturation_events: int = 0
    odi: Optional[float] = None
    data_points: int = 0


class SpO2NightlyResponse(BaseModel):
    record_date: date
    summary: SpO2NightSummary
    timeline: List[SpO2Point] = Field(default_factory=list)
    sleep_start: Optional[str] = None
    sleep_end: Optional[str] = None
    window: str = Field(
        default="sleep",
        description="timeline 覆盖的时间窗口: 'sleep'=仅 sleep_start~sleep_end 睡眠期间 (默认); 'all'=整晚全部采样 (包含日间/睡前)",
    )
    window_start: Optional[str] = Field(
        default=None, description="timeline 实际起始时间 (CST HH:MM), 便于 LLM 正确推理"
    )
    window_end: Optional[str] = Field(
        default=None, description="timeline 实际结束时间 (CST HH:MM)"
    )


class SpO2TrendResponse(BaseModel):
    days: int
    daily_data: List[SpO2NightSummary] = Field(default_factory=list)
    avg_nightly_spo2: Optional[float] = None
    avg_odi: Optional[float] = None
    nights_with_odi_above_5: int = 0


class SleepStageSpO2Stats(BaseModel):
    stage: str = Field(..., description="sleep stage: deep/light/rem/awake")
    avg_spo2: Optional[float] = None
    min_spo2: Optional[int] = None
    desaturation_events: int = 0
    below_90_count: int = 0
    duration_minutes: float = 0
    data_points: int = 0


class NightCorrelation(BaseModel):
    record_date: date
    stages: List[SleepStageSpO2Stats] = Field(default_factory=list)
    overall_odi: Optional[float] = None
    worst_stage: Optional[str] = None
    apnea_risk: str = "normal"
    apnea_risk_detail: Optional[str] = None


class SpO2SleepCorrelationResponse(BaseModel):
    days: int
    nights: List[NightCorrelation] = Field(default_factory=list)
    summary: Optional[dict] = None
