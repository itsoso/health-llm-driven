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
    pdf_base64: Optional[str] = Field(None, description="Base64 编码的 PDF 文件（会自动转为图片再提取）")


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
    # PDF → 图片转换（同步，速度快）
    image_list = list(req.image_base64_list or [])
    if req.pdf_base64:
        try:
            pdf_images = _pdf_to_images_base64(req.pdf_base64)
            image_list.extend(pdf_images)
            logger.info(f"PDF 转换为 {len(pdf_images)} 页图片")
        except Exception as e:
            logger.error(f"PDF 转图片失败: {e}", exc_info=True)
            return {"id": 0, "status": "failed", "message": f"PDF 解析失败: {str(e)}"}

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
    user_id = current_user.id
    report_date = req.report_date

    # 后台线程执行 AI 提取（不阻塞请求）
    if image_list:
        import threading
        threading.Thread(
            target=_process_report_background,
            args=(report_id, user_id, report_date, image_list),
            daemon=True,
        ).start()

    return {
        "id": report_id,
        "status": "processing",
        "pages": len(image_list),
        "message": f"报告已上传（{len(image_list)} 页），AI 正在后台提取指标...",
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
            from app.services.llm import get_llm_provider
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            llm = loop.run_until_complete(_get_llm())

            for i, img_b64 in enumerate(image_list):
                try:
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
                            {"type": "text", "text": f"这是体检报告第 {i+1}/{len(image_list)} 页，请提取所有指标："},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "high"}},
                        ]},
                    ]
                    resp = loop.run_until_complete(llm.chat(messages, temperature=0.1))

                    text = resp.strip()
                    if text.startswith("```"):
                        text = text.split("```")[1].strip()
                        if text.startswith("json"):
                            text = text[4:].strip()
                    items = json.loads(text)
                    if isinstance(items, list):
                        extracted_items.extend(items)
                    logger.info(f"报告 {report_id} 第 {i+1}/{len(image_list)} 页提取 {len(items)} 项指标")
                except Exception as e:
                    logger.warning(f"报告 {report_id} 第 {i+1} 页提取失败: {e}")

            # 异常指标
            abnormal_items = [item for item in extracted_items if item.get("is_abnormal")]

            # AI 总结
            ai_summary = ""
            if extracted_items:
                try:
                    summary_msg = [
                        {"role": "system", "content": "你是健康管理专家。根据以下体检指标，用中文简要总结：1）主要异常项及风险 2）需要关注的趋势 3）建议的后续检查。150字以内。"},
                        {"role": "user", "content": json.dumps(extracted_items, ensure_ascii=False)},
                    ]
                    ai_summary = loop.run_until_complete(llm.chat(summary_msg, temperature=0.3))
                except Exception as e:
                    logger.warning(f"报告 {report_id} AI 总结失败: {e}")

            loop.close()

            # 更新报告
            report.extracted_items = extracted_items
            report.abnormal_items = abnormal_items
            report.ai_summary = ai_summary
            report.status = "completed"

            # 写入指标时间线
            for item in extracted_items:
                if item.get("value") is not None:
                    try:
                        indicator = MedicalIndicator(
                            user_id=user_id,
                            report_id=report_id,
                            name=item["name"],
                            category=_categorize_indicator(item["name"]),
                            value=float(item["value"]),
                            unit=item.get("unit"),
                            reference_low=item.get("reference_low"),
                            reference_high=item.get("reference_high"),
                            is_abnormal=item.get("is_abnormal", False),
                            severity=item.get("severity", "normal"),
                            record_date=report_date,
                        )
                        db.add(indicator)
                    except (ValueError, TypeError):
                        pass

            db.commit()
            logger.info(f"报告 {report_id} AI 提取完成：{len(extracted_items)} 项指标，{len(abnormal_items)} 项异常")

        except Exception as e:
            logger.error(f"报告 {report_id} AI 提取失败: {e}", exc_info=True)
            report.status = "failed"
            report.ai_summary = f"AI 提取失败: {str(e)}"
            db.commit()

    finally:
        db.close()


async def _get_llm():
    from app.services.llm import get_llm_provider
    return get_llm_provider()


def _pdf_to_images_base64(pdf_base64: str, max_pages: int = 30, dpi: int = 200) -> List[str]:
    """将 Base64 编码的 PDF 转为每页的 Base64 JPEG 图片列表"""
    import base64
    import io

    pdf_bytes = base64.b64decode(pdf_base64)

    # 优先用 pymupdf (fitz)，速度快
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
            images.append(base64.b64encode(img_bytes).decode())
        doc.close()
        return images
    except ImportError:
        pass

    # 备选：pdf2image（需要 poppler）
    try:
        from pdf2image import convert_from_bytes
        pil_images = convert_from_bytes(pdf_bytes, dpi=dpi, last_page=max_pages)
        images = []
        for img in pil_images:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            images.append(base64.b64encode(buf.getvalue()).decode())
        return images
    except ImportError:
        pass

    raise ImportError("需要安装 pymupdf 或 pdf2image 来解析 PDF。运行: pip install pymupdf")


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
