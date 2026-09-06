"""家庭健康管理 Phase 2 API — 体检报告 + 用药管理 + 复查日历"""
import base64
import asyncio
import io
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import BoundedSemaphore
from typing import Annotated, Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel, Field, ValidationError
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.family_health import MedicalReport, MedicalIndicator, ReviewSchedule
from app.models.medication import Medication, MedicationLog
from app.api.deps import get_current_user_required
from app.services.secure_upload import (
    UploadContentInvalid,
    UploadTooLarge,
    decode_base64_limited,
    validate_image_bytes,
    validate_pdf_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_REPORT_PAGES = 20
MAX_REPORT_IMAGE_BYTES = 7 * 1024 * 1024
MAX_REPORT_PDF_BYTES = 7 * 1024 * 1024
MAX_REPORT_TOTAL_IMAGE_BYTES = 7 * 1024 * 1024
MAX_REPORT_RENDERED_BYTES = 30 * 1024 * 1024
MAX_REPORT_IMAGE_PIXELS = 20_000_000
MAX_REPORT_PDF_PAGE_PIXELS = 12_000_000
REPORT_PDF_DPI = 144
_IMAGE_BASE64_MAX_CHARS = ((MAX_REPORT_IMAGE_BYTES + 2) // 3) * 4 + 128
_PDF_BASE64_MAX_CHARS = ((MAX_REPORT_PDF_BYTES + 2) // 3) * 4 + 128
_REPORT_PREP_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="medical-report-prepare")
_REPORT_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="medical-report")
_REPORT_JOB_SLOTS = BoundedSemaphore(4)

ImageBase64 = Annotated[str, Field(min_length=1, max_length=_IMAGE_BASE64_MAX_CHARS)]
PdfBase64 = Annotated[str, Field(min_length=1, max_length=_PDF_BASE64_MAX_CHARS)]


def _coerce_optional_finite_float(value) -> Optional[float]:
    """Return a finite float for numeric LLM output, otherwise ``None``.

    Vision models sometimes preserve report placeholders such as ``-`` or ``—``
    in numeric reference-bound fields. Those values must not reach PostgreSQL
    ``DOUBLE PRECISION`` columns.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# ══════════════════════════════════════════════════════════
# 体检报告
# ══════════════════════════════════════════════════════════

class ReportUploadRequest(BaseModel):
    report_date: date
    hospital: Optional[str] = None
    report_type: str = "general"
    title: Optional[str] = None
    image_base64_list: Optional[List[ImageBase64]] = Field(
        None,
        max_length=MAX_REPORT_PAGES,
        description="Base64 编码的报告图片列表",
    )
    pdf_base64: Optional[PdfBase64] = Field(
        None,
        description="Base64 编码的 PDF 文件（会自动转为图片再提取）",
    )


def _prepare_report_payload(req: ReportUploadRequest) -> list[str]:
    """Validate/decode image or PDF pages outside the event loop."""
    image_list: list[str] = []
    total_source_bytes = 0
    for image_base64 in req.image_base64_list or []:
        prepared, source_bytes = _prepare_report_image(image_base64)
        total_source_bytes += source_bytes
        if total_source_bytes > MAX_REPORT_TOTAL_IMAGE_BYTES:
            raise UploadTooLarge("报告图片总大小超过限制")
        image_list.append(prepared)

    if req.pdf_base64:
        remaining_pages = MAX_REPORT_PAGES - len(image_list)
        if remaining_pages < 1:
            raise UploadTooLarge("报告总页数超过限制")
        pdf_images = _pdf_to_images_base64(
            req.pdf_base64,
            max_pages=remaining_pages,
            dpi=REPORT_PDF_DPI,
        )
        image_list.extend(pdf_images)
        logger.info("体检 PDF 转换完成 pages=%s", len(pdf_images))

    if not image_list:
        raise UploadContentInvalid("报告中没有可处理的页面")
    return image_list


@router.post("/medical-reports/upload", summary="上传体检报告（AI 异步提取）", tags=["medical-reports"])
async def upload_medical_report(
    req: ReportUploadRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    上传体检报告照片/PDF。立即返回 report ID，AI 在后台异步提取指标。
    前端通过 GET /medical-reports/{id} 轮询状态。
    """
    if not req.image_base64_list and not req.pdf_base64:
        raise HTTPException(status_code=400, detail="请上传报告图片或 PDF")
    if not _REPORT_JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="体检报告处理繁忙，请稍后重试")

    handed_to_worker = False
    try:
        image_list = await asyncio.get_running_loop().run_in_executor(
            _REPORT_PREP_EXECUTOR,
            _prepare_report_payload,
            req,
        )

        report = MedicalReport(
            user_id=current_user.id,
            report_date=req.report_date,
            hospital=req.hospital,
            report_type=req.report_type,
            title=req.title or f"{req.report_date} 体检报告",
            status="processing",
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        report_id = report.id
        try:
            _REPORT_JOB_EXECUTOR.submit(
                _process_report_with_slot,
                report_id,
                current_user.id,
                req.report_date,
                image_list,
            )
        except Exception as exc:
            report.status = "failed"
            report.ai_summary = "处理任务启动失败，请重新上传"
            db.commit()
            logger.error(
                "体检报告后台任务提交失败 report_id=%s error_type=%s",
                report_id,
                type(exc).__name__,
                exc_info=True,
            )
            raise HTTPException(
                status_code=503,
                detail="体检报告处理服务暂时不可用，请稍后重试",
            ) from exc
        handed_to_worker = True

        return {
            "id": report_id,
            "status": "processing",
            "pages": len(image_list),
            "message": f"报告已上传（{len(image_list)} 页），AI 正在后台提取指标...",
        }
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if not handed_to_worker:
            _REPORT_JOB_SLOTS.release()


@router.get("/medical-reports/me", summary="我的体检报告列表", tags=["medical-reports"])
async def get_my_reports(
    limit: int = 20,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    reports = db.query(MedicalReport).filter(
        MedicalReport.user_id == current_user.id
    ).order_by(desc(MedicalReport.report_date)).limit(limit).all()

    return [{
        "id": r.id,
        "report_date": str(r.report_date),
        "hospital": r.hospital,
        "report_type": r.report_type,
        "title": r.title,
        "status": r.status,
        "abnormal_count": len(r.abnormal_items or []),
        "ai_summary": r.ai_summary,
    } for r in reports]


@router.get("/medical-reports/compare", summary="多份体检报告对比", tags=["medical-reports"])
async def compare_reports(
    report_ids: str = Query(..., description="逗号分隔的报告 ID，如 '1,2,3'"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    对比多份体检报告，分析各指标变化趋势。
    按报告日期排序，计算每个指标的改善/恶化/稳定情况。
    """
    # 解析 report_ids
    try:
        id_list = [int(rid.strip()) for rid in report_ids.split(",") if rid.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="report_ids 格式错误，需逗号分隔的整数")

    if len(id_list) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 份报告才能对比")
    if len(id_list) > 10:
        raise HTTPException(status_code=400, detail="最多支持 10 份报告对比")

    # 查询报告并验证归属
    reports = db.query(MedicalReport).filter(
        MedicalReport.id.in_(id_list),
        MedicalReport.user_id == current_user.id,
    ).order_by(MedicalReport.report_date).all()

    if len(reports) != len(id_list):
        found_ids = {r.id for r in reports}
        missing = [rid for rid in id_list if rid not in found_ids]
        raise HTTPException(status_code=404, detail=f"报告不存在或无权访问: {missing}")

    report_id_set = {r.id for r in reports}
    report_date_map = {r.id: str(r.report_date) for r in reports}

    # 查询所有相关指标
    indicators = db.query(MedicalIndicator).filter(
        MedicalIndicator.report_id.in_(id_list),
        MedicalIndicator.user_id == current_user.id,
    ).order_by(MedicalIndicator.record_date).all()

    # 按指标名称分组
    indicator_groups = {}
    for ind in indicators:
        if ind.name not in indicator_groups:
            indicator_groups[ind.name] = []
        indicator_groups[ind.name].append(ind)

    # 构建对比结果
    indicators_result = {}
    improved = []
    worsened = []
    stable = []
    new_abnormal = []

    for name, records in indicator_groups.items():
        values = []
        for rec in records:
            values.append({
                "report_id": rec.report_id,
                "date": str(rec.record_date),
                "value": rec.value,
                "unit": rec.unit,
                "is_abnormal": rec.is_abnormal,
            })

        # 计算趋势：比较首末记录
        trend = "stable"
        change = None
        if len(records) >= 2:
            first_val = records[0].value
            last_val = records[-1].value
            first_abnormal = records[0].is_abnormal
            last_abnormal = records[-1].is_abnormal

            if first_val and first_val != 0:
                pct = ((last_val - first_val) / abs(first_val)) * 100
                change = f"{pct:+.0f}%" if abs(pct) >= 1 else "0%"

                # 判断趋势方向
                if last_abnormal and not first_abnormal:
                    trend = "worsening"
                elif first_abnormal and not last_abnormal:
                    trend = "improving"
                elif first_abnormal and last_abnormal:
                    # 都异常时，看参考范围方向
                    ref_low = records[0].reference_low
                    ref_high = records[0].reference_high
                    if ref_high is not None and first_val > ref_high:
                        # 偏高类指标，值降低=改善
                        trend = "improving" if last_val < first_val else "worsening"
                    elif ref_low is not None and first_val < ref_low:
                        # 偏低类指标，值升高=改善
                        trend = "improving" if last_val > first_val else "worsening"
                    else:
                        trend = "stable"
                else:
                    trend = "stable"

            # 分类
            if trend == "improving":
                improved.append(name)
            elif trend == "worsening":
                worsened.append(name)
            else:
                stable.append(name)

            # 新增异常：第一份正常，最后一份异常
            if not first_abnormal and last_abnormal:
                new_abnormal.append(name)

        indicators_result[name] = {
            "values": values,
            "trend": trend,
            "change": change,
        }

    return {
        "reports": [{
            "id": r.id,
            "report_date": str(r.report_date),
            "hospital": r.hospital,
            "title": r.title,
            "report_type": r.report_type,
        } for r in reports],
        "indicators": indicators_result,
        "summary": {
            "improved": improved,
            "worsened": worsened,
            "stable": stable,
            "new_abnormal": new_abnormal,
        },
    }


@router.get("/medical-reports/{report_id}", summary="体检报告详情", tags=["medical-reports"])
async def get_report_detail(
    report_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    report = db.query(MedicalReport).filter(
        MedicalReport.id == report_id,
        MedicalReport.user_id == current_user.id,
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    return {
        "id": report.id,
        "report_date": str(report.report_date),
        "hospital": report.hospital,
        "title": report.title,
        "status": report.status,
        "extracted_items": report.extracted_items or [],
        "abnormal_items": report.abnormal_items or [],
        "ai_summary": report.ai_summary,
        "ai_suggestions": report.ai_suggestions,
    }


@router.get("/medical-indicators/trend/{indicator_name}", summary="指标趋势", tags=["medical-reports"])
async def get_indicator_trend(
    indicator_name: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取某项指标的历史趋势（跨报告）"""
    records = db.query(MedicalIndicator).filter(
        MedicalIndicator.user_id == current_user.id,
        MedicalIndicator.name == indicator_name,
    ).order_by(MedicalIndicator.record_date).all()

    return {
        "indicator_name": indicator_name,
        "data_points": [{
            "date": str(r.record_date),
            "value": r.value,
            "unit": r.unit,
            "is_abnormal": r.is_abnormal,
            "severity": r.severity,
            "reference_low": r.reference_low,
            "reference_high": r.reference_high,
        } for r in records],
        "total_records": len(records),
    }


@router.get("/medical-indicators/analysis", summary="指标分类趋势分析", tags=["medical-reports"])
async def get_indicators_analysis(
    category: Optional[str] = Query(None, description="指标分类：blood/liver/kidney/lipid/glucose/thyroid/other"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    按分类聚合指标趋势数据。返回每个指标的历史值、当前状态、异常持续时间和严重度趋势。
    不传 category 则返回全部分类。
    """
    query = db.query(MedicalIndicator).filter(
        MedicalIndicator.user_id == current_user.id,
    )
    if category:
        query = query.filter(MedicalIndicator.category == category)

    records = query.order_by(MedicalIndicator.name, MedicalIndicator.record_date).all()

    if not records:
        return {
            "category": category,
            "indicators": [],
        }

    # 按指标名分组
    grouped = {}
    for rec in records:
        if rec.name not in grouped:
            grouped[rec.name] = []
        grouped[rec.name].append(rec)

    indicators_result = []
    for name, recs in grouped.items():
        latest = recs[-1]
        history = [{
            "date": str(r.record_date),
            "value": r.value,
            "is_abnormal": r.is_abnormal,
        } for r in recs]

        # 计算异常持续月数
        months_abnormal = 0
        if latest.is_abnormal and len(recs) >= 2:
            # 从最近记录往前找，连续异常的时间跨度
            for i in range(len(recs) - 1, -1, -1):
                if recs[i].is_abnormal:
                    months_abnormal = (latest.record_date - recs[i].record_date).days // 30
                else:
                    break
            # 至少算1个月（如果最新异常）
            if months_abnormal == 0 and latest.is_abnormal:
                months_abnormal = 1

        # 严重度趋势
        severity_order = {"normal": 0, "mild": 1, "moderate": 2, "severe": 3}
        severity_trend = "stable"
        if len(recs) >= 2:
            first_sev = severity_order.get(recs[0].severity or "normal", 0)
            last_sev = severity_order.get(latest.severity or "normal", 0)
            if last_sev > first_sev:
                severity_trend = "increasing"
            elif last_sev < first_sev:
                severity_trend = "decreasing"

        # 整体值趋势
        trend = "stable"
        if len(recs) >= 2:
            first_val = recs[0].value
            last_val = latest.value
            if first_val and first_val != 0:
                pct = ((last_val - first_val) / abs(first_val)) * 100
                if latest.is_abnormal and recs[0].is_abnormal:
                    ref_high = recs[0].reference_high
                    ref_low = recs[0].reference_low
                    if ref_high is not None and first_val > ref_high:
                        trend = "improving" if last_val < first_val else "worsening"
                    elif ref_low is not None and first_val < ref_low:
                        trend = "improving" if last_val > first_val else "worsening"
                elif not recs[0].is_abnormal and latest.is_abnormal:
                    trend = "worsening"
                elif recs[0].is_abnormal and not latest.is_abnormal:
                    trend = "improving"

        indicators_result.append({
            "name": name,
            "category": latest.category,
            "current_value": latest.value,
            "unit": latest.unit,
            "is_abnormal": latest.is_abnormal,
            "reference_low": latest.reference_low,
            "reference_high": latest.reference_high,
            "trend": trend,
            "history": history,
            "months_abnormal": months_abnormal,
            "severity_trend": severity_trend,
            "total_records": len(recs),
        })

    return {
        "category": category,
        "indicators": indicators_result,
    }


# ══════════════════════════════════════════════════════════
# 用药管理
# ══════════════════════════════════════════════════════════

class MedicationCreateRequest(BaseModel):
    name: str = Field(..., description="药品名称")
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    category: Optional[str] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None


class MedicationRecognizeRequest(BaseModel):
    image_base64: ImageBase64 = Field(..., description="药盒照片 Base64")


class MedicationRecognizedDraft(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    dosage: Optional[str] = Field(None, max_length=100)
    frequency: Optional[str] = Field(None, max_length=100)
    timing: Optional[str] = Field(None, max_length=50)
    indication: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)


@router.post("/medications/recognize", summary="拍药盒识别", tags=["medications"])
async def recognize_medication(
    req: MedicationRecognizeRequest,
    current_user: User = Depends(get_current_user_required),
):
    """识别药盒并返回草稿；只有后续显式提交才会写入用药清单。"""
    try:
        from app.services.llm import get_vision_provider
        from app.services.llm.usage_tracker import set_caller
        set_caller("family_health.medication_ocr", user_id=current_user.id)
        llm = get_vision_provider()

        prepared_image, _ = _prepare_report_image(req.image_base64)

        system_prompt = (
            "你是药品识别专家。请识别照片中的药品，返回 JSON 格式：\n"
            '{"name": "药品名", "category": "通用名", '
            '"dosage": "剂量如5mg", "frequency": "频次如每日1次", '
            '"timing": "morning/noon/evening/bedtime", '
            '"indication": "适应症", "notes": "注意事项"}\n'
            "只返回 JSON，不要其他文字。"
        )
        data_url = f"data:image/jpeg;base64,{prepared_image}"
        resp = await llm.chat_with_vision(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请识别这个药盒上的药品信息："},
            ],
            image_url=data_url,
            temperature=0.1,
        )

        # 解析
        text = resp.strip()
        if text.startswith("```"):
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        drug_info = MedicationRecognizedDraft.model_validate(json.loads(text))

        return {
            "recognized": drug_info.model_dump(),
            "requires_confirmation": True,
            "confirm_endpoint": "/api/v1/family-health/medications",
            "message": "识别完成，请核对药名、剂量和频次后再保存",
        }
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail="药盒图片过大") from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValidationError, TypeError):
        raise HTTPException(status_code=422, detail="AI 识别结果解析失败，请重新拍照")
    except Exception as e:
        logger.error("药品识别失败 error_type=%s", type(e).__name__, exc_info=True)
        raise HTTPException(status_code=500, detail="识别失败，请稍后重试") from e


@router.post("/medications", summary="手动添加用药", tags=["medications"])
async def add_medication(
    req: MedicationCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    med = Medication(
        user_id=current_user.id,
        name=req.name,
        category=req.category,
        dosage=req.dosage,
        frequency=req.frequency,
        purpose=req.purpose,
        notes=req.notes,
        start_date=date.today(),
    )
    db.add(med)
    db.commit()
    return {"id": med.id, "message": f"已添加: {med.name}"}


@router.get("/medications/me", summary="我的用药清单", tags=["medications"])
async def get_my_medications(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    meds = db.query(Medication).filter(
        Medication.user_id == current_user.id,
        Medication.is_active == True,
    ).all()

    result = []
    today = date.today()
    for m in meds:
        today_log = db.query(MedicationLog).filter(
            MedicationLog.medication_id == m.id,
            MedicationLog.taken_date == today,
        ).first()

        result.append({
            "id": m.id,
            "name": m.name,
            "category": m.category,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "purpose": m.purpose,
            "notes": m.notes,
            "start_date": str(m.start_date) if m.start_date else None,
            "taken_today": bool(today_log and today_log.status == "taken"),
        })

    return {"medications": result, "total": len(result)}


@router.post("/medications/{med_id}/take", summary="记录服药", tags=["medications"])
async def log_medication_taken(
    med_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录今天已服药"""
    med = db.query(Medication).filter(
        Medication.id == med_id,
        Medication.user_id == current_user.id,
    ).first()
    if not med:
        raise HTTPException(status_code=404, detail="用药方案不存在")

    today = date.today()
    # 依从写回幂等(读-改-写竞态 DB 兜底)。/take 是「今日按日标记已服」,taken_time=NULL;
    # 唯一索引 uq_medlog_med_date_time 用 COALESCE(taken_time,'') 把 NULL 折叠成同一槽,
    # 故两个并发 POST 都读到无行、都 INSERT 时第二条撞 IntegrityError —— 不再静默落 2 条
    # 虚高依从(否则经 twin.medication.adherence_7d_pct 误证给 DDI/PGx/SafetyGuardian)。
    existing = db.query(MedicationLog).filter(
        MedicationLog.medication_id == med_id,
        MedicationLog.taken_date == today,
    ).first()
    if existing is not None:
        if existing.status != "taken":
            existing.status = "taken"
            db.commit()
        return {"message": f"已记录服用: {med.name}"}

    log = MedicationLog(
        user_id=current_user.id,
        medication_id=med_id,
        taken_date=today,
        status="taken",
    )
    db.add(log)
    try:
        db.commit()
    except IntegrityError:
        # 并发另一个请求已落今日行 → 回滚本次 INSERT, 重读并确保 taken(幂等收敛, 不报错)。
        db.rollback()
        existing = db.query(MedicationLog).filter(
            MedicationLog.medication_id == med_id,
            MedicationLog.taken_date == today,
        ).first()
        if existing is None:  # 撞唯一约束却查不到 → 反常, fail loud 不吞
            raise
        if existing.status != "taken":
            existing.status = "taken"
            db.commit()
    return {"message": f"已记录服用: {med.name}"}


# ══════════════════════════════════════════════════════════
# 复查日历
# ══════════════════════════════════════════════════════════

class ReviewScheduleCreate(BaseModel):
    item_name: str
    category: Optional[str] = None
    department: Optional[str] = None
    hospital: Optional[str] = None
    last_check_date: Optional[date] = None
    next_due_date: date
    interval_months: Optional[int] = None
    priority: str = "normal"
    notes: Optional[str] = None


@router.post("/review-calendar", summary="添加复查计划", tags=["review-calendar"])
async def add_review_schedule(
    req: ReviewScheduleCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    schedule = ReviewSchedule(
        user_id=current_user.id,
        item_name=req.item_name,
        category=req.category,
        department=req.department,
        hospital=req.hospital,
        last_check_date=req.last_check_date,
        next_due_date=req.next_due_date,
        interval_months=req.interval_months,
        priority=req.priority,
        notes=req.notes,
    )
    db.add(schedule)
    db.commit()
    return {"id": schedule.id, "message": f"已添加复查计划: {req.item_name}"}


@router.get("/review-calendar/me", summary="我的复查日历", tags=["review-calendar"])
async def get_my_review_calendar(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取复查日历，自动标注过期/即将到期"""
    schedules = db.query(ReviewSchedule).filter(
        ReviewSchedule.user_id == current_user.id,
        ReviewSchedule.is_active == True,
    ).order_by(ReviewSchedule.next_due_date).all()

    today = date.today()
    result = []
    overdue_count = 0
    upcoming_count = 0

    for s in schedules:
        # 自动更新状态
        if s.status != "completed":
            if s.next_due_date < today:
                s.status = "overdue"
                overdue_count += 1
            elif s.next_due_date <= today + timedelta(days=30):
                upcoming_count += 1

        days_until = (s.next_due_date - today).days

        result.append({
            "id": s.id,
            "item_name": s.item_name,
            "category": s.category,
            "department": s.department,
            "hospital": s.hospital,
            "last_check_date": str(s.last_check_date) if s.last_check_date else None,
            "next_due_date": str(s.next_due_date),
            "days_until_due": days_until,
            "status": s.status,
            "priority": s.priority,
            "notes": s.notes,
            "interval_months": s.interval_months,
        })

    db.commit()

    return {
        "schedules": result,
        "summary": {
            "total": len(result),
            "overdue": overdue_count,
            "upcoming_30_days": upcoming_count,
        },
    }


@router.post("/review-calendar/{schedule_id}/complete", summary="标记复查已完成", tags=["review-calendar"])
async def complete_review(
    schedule_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    schedule = db.query(ReviewSchedule).filter(
        ReviewSchedule.id == schedule_id,
        ReviewSchedule.user_id == current_user.id,
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="复查计划不存在")

    today = date.today()
    schedule.status = "completed"
    schedule.completed_date = today
    schedule.last_check_date = today

    # 如果有间隔月数，自动创建下一次复查
    if schedule.interval_months:
        from dateutil.relativedelta import relativedelta
        next_date = today + relativedelta(months=schedule.interval_months)
        new_schedule = ReviewSchedule(
            user_id=current_user.id,
            item_name=schedule.item_name,
            category=schedule.category,
            department=schedule.department,
            hospital=schedule.hospital,
            last_check_date=today,
            next_due_date=next_date,
            interval_months=schedule.interval_months,
            priority=schedule.priority,
            notes=schedule.notes,
        )
        db.add(new_schedule)

    db.commit()
    return {"message": f"已完成: {schedule.item_name}", "next_due": str(next_date) if schedule.interval_months else None}


# ══════════════════════════════════════════════════════════
# 每周健康摘要
# ══════════════════════════════════════════════════════════

@router.get("/weekly-digest", summary="生成家庭健康周报", tags=["family-weekly-digest"])
async def get_weekly_digest(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.family_weekly_digest import generate_weekly_digest
    return generate_weekly_digest(db, current_user.id)


@router.post("/weekly-digest/send", summary="发送家庭健康周报", tags=["family-weekly-digest"])
async def send_weekly_digest_endpoint(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.family_weekly_digest import send_weekly_digest
    digest = await send_weekly_digest(db, current_user.id)
    return {"message": "周报已发送", "concerns": digest.get("total_concerns", 0)}


# ══════════════════════════════════════════════════════════
# 医疗文本解析（测试端点）
# ══════════════════════════════════════════════════════════

class ParseTextRequest(BaseModel):
    text: str = Field(..., description="待解析的医疗文本（如'血压150/95'）")

@router.post("/parse-medical-text", summary="解析医疗文本", tags=["wechat-bot"])
async def parse_medical_text_endpoint(
    req: ParseTextRequest,
    current_user: User = Depends(get_current_user_required),
):
    """测试端点：将自然语言转为结构化健康数据"""
    from app.services.medical_text_parser import parse_and_route
    result = await parse_and_route(req.text)
    return result


# ══════════════════════════════════════════════════════════
# 微信 Bot 消息 Webhook
# ══════════════════════════════════════════════════════════

class WeChatMessageRequest(BaseModel):
    msg_type: str = Field(..., description="消息类型: text/image/voice")
    content: str = Field(..., description="消息内容（文字/图片base64/语音识别文字）")
    wechat_openid: Optional[str] = Field(None, description="发送者微信 OpenID")
    msg_id: Optional[str] = Field(
        None,
        max_length=200,
        description="微信/企业微信原始消息 ID，用于防重复投递",
    )
    message_id: Optional[str] = Field(
        None,
        max_length=200,
        description="兼容调用方的原始消息 ID 字段",
    )

@router.post("/wechat-bot/message", summary="微信 Bot 消息入口", tags=["wechat-bot"])
async def handle_wechat_message(
    req: WeChatMessageRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    微信 Bot 消息处理入口。
    当前通过 JWT 认证（测试阶段），未来接入企业微信 webhook 后改为签名验证。
    """
    if not str(req.msg_id or req.message_id or "").strip():
        raise HTTPException(
            status_code=422,
            detail="缺少微信原始消息 ID，无法安全防止重复处理",
        )
    from app.services.wechat_bot import WeChatBotHandler
    from app.services.ai_consent import require_ai_consent
    require_ai_consent(current_user.id)
    handler = WeChatBotHandler(db)
    result = await handler.handle_message({
        "msg_type": req.msg_type,
        "content": req.content,
        "wechat_openid": req.wechat_openid,
        "msg_id": req.msg_id,
        "message_id": req.message_id,
        "user_id": current_user.id,
    })
    return result


# ══════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════

def _mark_report_failed(db: Session, *, report_id: int, user_id: int) -> None:
    """Recover a failed transaction before persisting the terminal state."""
    db.rollback()
    failed_report = db.query(MedicalReport).filter(
        MedicalReport.id == report_id,
        MedicalReport.user_id == user_id,
    ).first()
    if failed_report:
        failed_report.status = "failed"
        failed_report.ai_summary = "AI 提取失败，请重新上传"
        db.commit()


def _process_report_with_slot(
    report_id: int,
    user_id: int,
    report_date,
    image_list: List[str],
) -> None:
    try:
        _process_report_background(report_id, user_id, report_date, image_list)
    finally:
        _REPORT_JOB_SLOTS.release()


def _process_report_background(report_id: int, user_id: int, report_date, image_list: List[str]):
    """后台线程：AI 提取体检报告指标"""
    import asyncio
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        report = db.query(MedicalReport).filter(MedicalReport.id == report_id).first()
        if not report:
            return

        extracted_items = []
        try:
            from app.services.llm import get_vision_provider
            from app.services.llm.usage_tracker import set_caller
            set_caller("family_health.exam_vision", user_id=user_id)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            llm = get_vision_provider()

            import time as _time

            system_prompt = (
                "你是专业的体检报告解读助手。请仔细阅读这张体检报告图片，"
                "提取所有检查指标。对每个指标，返回 JSON 数组格式：\n"
                '[{"name": "指标名", "value": 数值, "unit": "单位", '
                '"reference_low": 下限, "reference_high": 上限, '
                '"is_abnormal": true/false, "severity": "normal/mild/moderate/severe"}]\n'
                "只返回 JSON，不要其他文字。如果图片不清晰或不是体检报告，返回空数组 []。"
            )

            for i, img_b64 in enumerate(image_list):
                # 页间限速：避免 TPM 限流
                if i > 0:
                    _time.sleep(3)

                # 压缩图片降低 token 消耗
                compressed = _compress_image_base64(img_b64)

                for attempt in range(3):  # 最多重试 3 次
                    try:
                        data_url = f"data:image/jpeg;base64,{compressed}"
                        resp = loop.run_until_complete(llm.chat_with_vision(
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"这是体检报告第 {i+1}/{len(image_list)} 页，请提取所有指标："},
                            ],
                            image_url=data_url,
                            temperature=0.1,
                        ))

                        text = resp.strip()
                        if text.startswith("```"):
                            text = text.split("```")[1].strip()
                            if text.startswith("json"):
                                text = text[4:].strip()
                        items = json.loads(text)
                        if isinstance(items, list):
                            extracted_items.extend(items)
                        logger.info(f"报告 {report_id} 第 {i+1}/{len(image_list)} 页提取 {len(items)} 项指标")
                        break  # 成功，退出重试
                    except Exception as e:
                        err_str = str(e)
                        if '429' in err_str and attempt < 2:
                            wait = (attempt + 1) * 5  # 5s, 10s
                            logger.warning(f"报告 {report_id} 第 {i+1} 页 429 限流，等待 {wait}s 后重试")
                            _time.sleep(wait)
                        else:
                            logger.warning(f"报告 {report_id} 第 {i+1} 页提取失败: {e}")
                            break

            # 异常指标
            abnormal_items = [item for item in extracted_items if item.get("is_abnormal")]

            # AI 总结
            ai_summary = ""
            if extracted_items:
                try:
                    from app.services.llm.usage_tracker import set_caller
                    set_caller("family_health.exam_summary", user_id=user_id)
                    summary_msg = [
                        {"role": "system", "content": "你是健康管理专家。根据以下体检指标，用中文简要总结：1）主要异常项及风险 2）需要关注的趋势 3）建议的后续检查。150字以内。"},
                        {"role": "user", "content": json.dumps(extracted_items, ensure_ascii=False)},
                    ]
                    ai_summary = loop.run_until_complete(llm.chat(summary_msg, temperature=0.3))
                except Exception as e:
                    logger.warning(f"报告 {report_id} AI 总结失败: {e}")

            # AI 建议（基于异常指标 + 用户画像）
            ai_suggestions_list = []
            if abnormal_items:
                try:
                    from app.services.llm.usage_tracker import set_caller
                    set_caller("family_health.exam_suggestions", user_id=user_id)
                    # 获取用户画像信息
                    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                    user_context = ""
                    if profile:
                        age = profile.age
                        gender_map = {"male": "男性", "female": "女性", "other": "其他"}
                        gender = gender_map.get(profile.gender, "未知")
                        parts = []
                        if age:
                            parts.append(f"年龄：{age}岁")
                        if profile.gender:
                            parts.append(f"性别：{gender}")
                        if profile.chronic_conditions:
                            parts.append(f"慢性病史：{', '.join(profile.chronic_conditions)}")
                        if profile.family_history:
                            parts.append(f"家族病史：{', '.join(profile.family_history)}")
                        if parts:
                            user_context = f"\n\n患者信息：{'; '.join(parts)}"

                    suggestions_msg = [
                        {"role": "system", "content": (
                            "你是资深临床医学专家。根据以下体检异常指标，为每个异常项生成具体的就医建议。"
                            "必须返回 JSON 数组格式，每个元素包含：\n"
                            '{"indicator": "指标名称", "status": "偏高/偏低/异常", '
                            '"risk": "具体风险描述", "action": "具体可执行的建议（饮食、运动、生活方式）", '
                            '"timeline": "复查时间建议", "specialist": "推荐就诊科室"}\n\n'
                            "要求：\n"
                            "1. 建议必须具体可执行，不要泛泛而谈\n"
                            "2. 结合患者个人信息（如有）给出个性化建议\n"
                            "3. 风险描述要准确，不夸大也不淡化\n"
                            "4. 只返回 JSON 数组，不要其他文字"
                        )},
                        {"role": "user", "content": (
                            f"异常指标：{json.dumps(abnormal_items, ensure_ascii=False)}"
                            f"{user_context}"
                        )},
                    ]
                    suggestions_resp = loop.run_until_complete(llm.chat(suggestions_msg, temperature=0.3))

                    text = suggestions_resp.strip()
                    if text.startswith("```"):
                        text = text.split("```")[1].strip()
                        if text.startswith("json"):
                            text = text[4:].strip()
                    ai_suggestions_list = json.loads(text)
                    if not isinstance(ai_suggestions_list, list):
                        ai_suggestions_list = []
                    logger.info(f"报告 {report_id} AI 生成 {len(ai_suggestions_list)} 条建议")
                except Exception as e:
                    logger.warning(f"报告 {report_id} AI 建议生成失败: {e}")

            loop.close()

            # 更新报告
            report.extracted_items = extracted_items
            report.abnormal_items = abnormal_items
            report.ai_summary = ai_summary
            report.ai_suggestions = ai_suggestions_list
            report.status = "completed"

            # 写入指标时间线
            for item in extracted_items:
                if item.get("value") is not None:
                    try:
                        numeric_value = _coerce_optional_finite_float(item.get("value"))
                        if numeric_value is None:
                            continue
                        from app.services.exam_packages import normalize_item_name
                        code, std_name = normalize_item_name(item["name"])
                        indicator = MedicalIndicator(
                            user_id=user_id,
                            report_id=report_id,
                            name=item["name"],
                            name_en=code if code else None,
                            item_code=code if code else None,
                            category=_categorize_indicator(item["name"]),
                            value=numeric_value,
                            unit=item.get("unit"),
                            reference_low=_coerce_optional_finite_float(
                                item.get("reference_low")
                            ),
                            reference_high=_coerce_optional_finite_float(
                                item.get("reference_high")
                            ),
                            is_abnormal=item.get("is_abnormal", False),
                            severity=item.get("severity", "normal"),
                            source="image_ai",
                            record_date=report_date,
                        )
                        db.add(indicator)
                    except (ValueError, TypeError):
                        pass

            db.commit()
            logger.info(f"报告 {report_id} AI 提取完成：{len(extracted_items)} 项指标，{len(abnormal_items)} 项异常")

            # Memory Extractor: 异常化验项 → fact + KG entity (旁路, fail-soft)
            try:
                from app.services.memory_extractor import (
                    extract_from_medical_exam_item, extract_kg_from_lab,
                )
                abnormal_inds = db.query(MedicalIndicator).filter(
                    MedicalIndicator.report_id == report_id,
                    MedicalIndicator.is_abnormal.is_(True),
                ).all()
                extracted_count = 0
                for ind in abnormal_inds:
                    if extract_from_medical_exam_item(db, user_id, ind):
                        extracted_count += 1
                    extract_kg_from_lab(db, user_id, ind)
                db.commit()
                logger.info(f"报告 {report_id} memory: 写入 {extracted_count}/{len(abnormal_inds)} facts")
            except Exception as e:  # noqa: BLE001
                db.rollback()
                logger.warning(f"报告 {report_id} memory extract 失败 (旁路): {e}")

        except Exception as e:
            logger.error(f"报告 {report_id} AI 提取失败: {e}", exc_info=True)
            _mark_report_failed(db, report_id=report_id, user_id=user_id)

    finally:
        db.close()


def _prepare_report_image(img_b64: str, *, max_size: int = 1600) -> tuple[str, int]:
    """Validate and normalize one bounded report image to JPEG."""
    img_bytes = decode_base64_limited(img_b64, max_bytes=MAX_REPORT_IMAGE_BYTES)
    kind = validate_image_bytes(
        img_bytes,
        max_pixels=MAX_REPORT_IMAGE_PIXELS,
    )
    if kind == "heic":
        raise UploadContentInvalid("体检报告暂不支持 HEIC，请转换为 JPEG 或 PNG")
    try:
        with Image.open(io.BytesIO(img_bytes)) as image:
            image.load()
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=80, optimize=True)
    except (OSError, ValueError) as exc:
        raise UploadContentInvalid("报告图片损坏或无法解析") from exc
    normalized = output.getvalue()
    if len(normalized) > MAX_REPORT_IMAGE_BYTES:
        raise UploadTooLarge("压缩后的报告图片仍然过大")
    return base64.b64encode(normalized).decode("ascii"), len(img_bytes)


def _compress_image_base64(img_b64: str, max_size: int = 1024) -> str:
    """Re-normalize a previously validated image for the Vision request."""
    return _prepare_report_image(img_b64, max_size=max_size)[0]


async def _get_llm():
    from app.services.llm import get_llm_provider
    return get_llm_provider()


def _pdf_to_images_base64(
    pdf_base64: str,
    max_pages: int = MAX_REPORT_PAGES,
    dpi: int = REPORT_PDF_DPI,
) -> List[str]:
    """Render a bounded PDF into bounded JPEG pages using PyMuPDF."""
    if max_pages < 1 or max_pages > MAX_REPORT_PAGES:
        raise ValueError("invalid_max_pages")
    if dpi < 72 or dpi > REPORT_PDF_DPI:
        raise ValueError("invalid_pdf_dpi")
    pdf_bytes = decode_base64_limited(pdf_base64, max_bytes=MAX_REPORT_PDF_BYTES)
    validate_pdf_bytes(pdf_bytes)

    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("服务器缺少 PyMuPDF，无法安全解析 PDF") from exc

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise UploadContentInvalid("PDF 损坏或无法解析") from exc

    try:
        if doc.needs_pass:
            raise UploadContentInvalid("暂不支持加密 PDF")
        if doc.page_count < 1:
            raise UploadContentInvalid("PDF 没有可处理页面")
        if doc.page_count > max_pages:
            raise UploadTooLarge(f"PDF 超过 {max_pages} 页限制")

        images = []
        rendered_bytes = 0
        for page in doc:
            width = max(1, int(page.rect.width * dpi / 72))
            height = max(1, int(page.rect.height * dpi / 72))
            if width * height > MAX_REPORT_PDF_PAGE_PIXELS:
                raise UploadTooLarge("PDF 单页尺寸超过限制")
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
            img_bytes = pix.tobytes("jpeg")
            rendered_bytes += len(img_bytes)
            if rendered_bytes > MAX_REPORT_RENDERED_BYTES:
                raise UploadTooLarge("PDF 渲染结果超过大小限制")
            images.append(base64.b64encode(img_bytes).decode("ascii"))
        return images
    finally:
        doc.close()


def _categorize_indicator(name: str) -> str:
    """根据指标名称自动分类"""
    categories = {
        "blood": ["血红蛋白", "白细胞", "红细胞", "血小板", "血常规"],
        "liver": ["谷丙", "谷草", "转氨酶", "胆红素", "白蛋白", "肝功"],
        "kidney": ["肌酐", "尿素", "尿酸", "肾功"],
        "lipid": ["甘油三酯", "胆固醇", "高密度", "低密度", "血脂"],
        "glucose": ["血糖", "糖化", "HbA1c", "葡萄糖"],
        "thyroid": ["甲状腺", "TSH", "T3", "T4", "甲功"],
    }
    name_lower = name.lower()
    for cat, keywords in categories.items():
        if any(kw in name_lower for kw in keywords):
            return cat
    return "other"


# ══════════════════════════════════════════════════════════
# 每日家庭健康巡检
# ══════════════════════════════════════════════════════════

@router.get("/daily-check", summary="家庭每日健康巡检", tags=["family-daily-check"])
async def family_daily_check(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    执行家庭健康巡检，返回所有成员的健康状态、待办和预警。
    可手动调用，也由每日定时任务自动执行。
    """
    from app.services.family_daily_check import run_family_daily_check
    return run_family_daily_check(db, current_user.id)


@router.post("/daily-check/send", summary="发送家庭健康日报", tags=["family-daily-check"])
async def send_family_daily_check(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """执行巡检并推送日报给管理员和家庭成员"""
    from app.services.family_daily_check import send_family_daily_brief
    report = await send_family_daily_brief(db, current_user.id)
    return {
        "message": "家庭健康日报已发送",
        "admin_summary": report["admin_summary"],
        "alert_count": report["admin_alert_count"],
        "members_checked": len(report["member_reports"]),
    }
