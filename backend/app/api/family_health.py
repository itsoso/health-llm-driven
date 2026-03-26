"""家庭健康管理 Phase 2 API — 体检报告 + 用药管理 + 复查日历"""
import json
import logging
from datetime import date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User
from app.models.family_health import MedicalReport, MedicalIndicator, ReviewSchedule
from app.models.medication import Medication, MedicationLog
from app.api.deps import get_current_user_required

logger = logging.getLogger(__name__)

router = APIRouter()


# ══════════════════════════════════════════════════════════
# 体检报告
# ══════════════════════════════════════════════════════════

class ReportUploadRequest(BaseModel):
    report_date: date
    hospital: Optional[str] = None
    report_type: str = "general"
    title: Optional[str] = None
    image_base64_list: Optional[List[str]] = Field(None, description="Base64 编码的报告图片列表")


@router.post("/medical-reports/upload", summary="上传体检报告（AI 提取）", tags=["medical-reports"])
async def upload_medical_report(
    req: ReportUploadRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    上传体检报告照片/PDF，AI 自动提取指标并建立趋势。
    支持一次上传多张图片（如多页报告）。
    """
    report = MedicalReport(
        user_id=current_user.id,
        report_date=req.report_date,
        hospital=req.hospital,
        report_type=req.report_type,
        title=req.title or f"{req.report_date} 体检报告",
        status="processing",
    )
    db.add(report)
    db.flush()

    # AI 提取（异步，先返回 report ID）
    extracted_items = []
    abnormal_items = []
    ai_summary = ""

    if req.image_base64_list:
        try:
            from app.services.llm import get_llm_provider
            llm = get_llm_provider()

            all_text = []
            for i, img_b64 in enumerate(req.image_base64_list):
                messages = [
                    {"role": "system", "content": (
                        "你是专业的体检报告解读助手。请仔细阅读这张体检报告图片，"
                        "提取所有检查指标。对每个指标，返回 JSON 数组格式：\n"
                        '[{"name": "指标名", "value": 数值, "unit": "单位", '
                        '"reference_low": 下限, "reference_high": 上限, '
                        '"is_abnormal": true/false, "severity": "normal/mild/moderate/severe"}]\n'
                        "只返回 JSON，不要其他文字。如果图片不清晰或不是体检报告，返回空数组 []。"
                    )},
                    {"role": "user", "content": [
                        {"type": "text", "text": f"这是体检报告第 {i+1} 页，请提取所有指标："},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "high"}},
                    ]},
                ]
                resp = await llm.chat(messages, temperature=0.1)
                all_text.append(resp)

            # 解析 AI 返回的 JSON
            for resp_text in all_text:
                try:
                    # 尝试提取 JSON
                    text = resp_text.strip()
                    if text.startswith("```"):
                        text = text.split("```")[1].strip()
                        if text.startswith("json"):
                            text = text[4:].strip()
                    items = json.loads(text)
                    if isinstance(items, list):
                        extracted_items.extend(items)
                except (json.JSONDecodeError, IndexError):
                    logger.warning(f"体检报告 AI 解析失败，原始文本: {resp_text[:200]}")

            # 筛选异常指标
            abnormal_items = [item for item in extracted_items if item.get("is_abnormal")]

            # 生成总结
            if extracted_items:
                summary_messages = [
                    {"role": "system", "content": "你是健康管理专家。根据以下体检指标，用中文简要总结：1）主要异常项及风险 2）需要关注的趋势 3）建议的后续检查。100字以内。"},
                    {"role": "user", "content": json.dumps(extracted_items, ensure_ascii=False)},
                ]
                ai_summary = await llm.chat(summary_messages, temperature=0.3)

            report.extracted_items = extracted_items
            report.abnormal_items = abnormal_items
            report.ai_summary = ai_summary
            report.status = "completed"

            # 将指标写入时间线表
            for item in extracted_items:
                if item.get("value") is not None:
                    try:
                        indicator = MedicalIndicator(
                            user_id=current_user.id,
                            report_id=report.id,
                            name=item["name"],
                            category=_categorize_indicator(item["name"]),
                            value=float(item["value"]),
                            unit=item.get("unit"),
                            reference_low=item.get("reference_low"),
                            reference_high=item.get("reference_high"),
                            is_abnormal=item.get("is_abnormal", False),
                            severity=item.get("severity", "normal"),
                            record_date=req.report_date,
                        )
                        db.add(indicator)
                    except (ValueError, TypeError):
                        pass

        except Exception as e:
            logger.error(f"体检报告 AI 提取失败: {e}", exc_info=True)
            report.status = "failed"
            report.ai_summary = f"AI 提取失败: {str(e)}"

    db.commit()

    return {
        "id": report.id,
        "status": report.status,
        "extracted_count": len(extracted_items),
        "abnormal_count": len(abnormal_items),
        "ai_summary": ai_summary,
        "abnormal_items": abnormal_items,
    }


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
    image_base64: str = Field(..., description="药盒照片 Base64")


@router.post("/medications/recognize", summary="拍药盒识别", tags=["medications"])
async def recognize_medication(
    req: MedicationRecognizeRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """拍药盒照片，AI 自动识别药名、剂量、用法并添加到用药清单"""
    try:
        from app.services.llm import get_llm_provider
        llm = get_llm_provider()

        messages = [
            {"role": "system", "content": (
                "你是药品识别专家。请识别照片中的药品，返回 JSON 格式：\n"
                '{"name": "药品名", "category": "通用名", '
                '"dosage": "剂量如5mg", "frequency": "频次如每日1次", '
                '"timing": "morning/noon/evening/bedtime", '
                '"indication": "适应症", "notes": "注意事项"}\n'
                "只返回 JSON，不要其他文字。"
            )},
            {"role": "user", "content": [
                {"type": "text", "text": "请识别这个药盒上的药品信息："},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{req.image_base64}", "detail": "high"}},
            ]},
        ]
        resp = await llm.chat(messages, temperature=0.1)

        # 解析
        text = resp.strip()
        if text.startswith("```"):
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        drug_info = json.loads(text)

        # 自动添加到用药清单（匹配 Medication 模型字段）
        med = Medication(
            user_id=current_user.id,
            name=drug_info.get("name", "未识别"),
            category=drug_info.get("category"),
            dosage=drug_info.get("dosage"),
            frequency=drug_info.get("frequency"),
            purpose=drug_info.get("indication"),
            notes=drug_info.get("notes"),
            start_date=date.today(),
        )
        db.add(med)
        db.commit()

        return {
            "id": med.id,
            "recognized": drug_info,
            "message": f"已识别并添加: {med.name}",
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="AI 识别结果解析失败，请重新拍照")
    except Exception as e:
        logger.error(f"药品识别失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"识别失败: {str(e)}")


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
    existing = db.query(MedicationLog).filter(
        MedicationLog.medication_id == med_id,
        MedicationLog.taken_date == today,
    ).first()

    if existing:
        existing.status = "taken"
    else:
        log = MedicationLog(
            user_id=current_user.id,
            medication_id=med_id,
            taken_date=today,
            status="taken",
        )
        db.add(log)

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
# 辅助函数
# ══════════════════════════════════════════════════════════

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
