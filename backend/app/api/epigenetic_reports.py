# -*- coding: utf-8 -*-
"""DNAm 表观遗传时钟报告摄入 API(抗衰 Phase2 W3)。

第三方时钟(TruDiagnostic/GrimAge/DunedinPACE 等)结果上传入口。读路径(Twin
EpigeneticState + LongevitySpecialist 交叉展示)此前已就绪,这里补写入侧。

不自建时钟;evidence_tier=experimental(claim_boundary 随读取返回)。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.epigenetic_report_service import (
    create_epigenetic_report,
    epigenetic_report_summary,
    list_epigenetic_reports,
)

router = APIRouter()


class EpigeneticReportIn(BaseModel):
    vendor: str = Field(..., min_length=1, max_length=120, description="检测厂商, 如 TruDiagnostic")
    clock_type: str = Field(..., min_length=1, max_length=120, description="时钟类型, 如 GrimAge/DunedinPACE")
    sample_date: date = Field(..., description="采样日期")
    biological_age: Optional[float] = Field(None, ge=0, le=150, description="生物年龄(岁)")
    pace_of_aging: Optional[float] = Field(None, ge=0, le=5, description="衰老速率 (DunedinPACE)")
    raw_summary: dict[str, Any] = Field(default_factory=dict, description="原始报告字段(可选)")


@router.post("/me", summary="上传一份第三方 DNAm 时钟报告")
def upload_my_epigenetic_report(
    payload: EpigeneticReportIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    report = create_epigenetic_report(
        db,
        current_user.id,
        vendor=payload.vendor,
        clock_type=payload.clock_type,
        sample_date=payload.sample_date,
        biological_age=payload.biological_age,
        pace_of_aging=payload.pace_of_aging,
        raw_summary=payload.raw_summary,
    )
    return epigenetic_report_summary(report)


@router.get("/me", summary="列出我的 DNAm 时钟报告")
def list_my_epigenetic_reports(
    limit: int = 20,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return {"reports": list_epigenetic_reports(db, current_user.id, limit=limit)}
