"""体检数据API"""
import tempfile
import os
import base64
import logging
from datetime import datetime, date, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload
from typing import List
from app.database import get_db
from app.schemas.medical_exam import (
    MedicalExamCreate,
    MedicalExamResponse,
    MedicalExamItemUpdate,
    MedicalExamItemResponse,
    MedicalExamReportSummary,
)
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.data_collection.medical_exam_import import MedicalExamImportService
from app.services.pdf_parser import pdf_parser
from app.services.exam_packages import create_indicator_from_item
from app.services.ai.medical_report_ocr import recognize_medical_report
from app.services.secure_upload import (
    UploadContentInvalid,
    UploadTooLarge,
    read_upload_limited,
    validate_csv_bytes,
    validate_image_bytes,
    validate_pdf_bytes,
)

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB,防 OCR 被大图灌穿
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_CSV_BYTES = 5 * 1024 * 1024


class MedicalExamTextImportRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    exam_date: str | None = None
    hospital_name: str | None = Field(default=None, max_length=200)
    exam_type: str | None = Field(default="biochemistry", max_length=80)


class LabPhotoParseRequest(BaseModel):
    image_base64: str = Field(..., min_length=1, max_length=14_000_000, description="化验单照片 base64")
    image_type: str = Field(default="jpeg", max_length=10)


@router.post("/parse-photo", summary="多模态录入:化验单拍照 → 结构化项(待用户确认)")
async def parse_lab_photo_endpoint(
    req: LabPhotoParseRequest,
    current_user: User = Depends(get_current_user_required),
):
    """vision 解析化验单照片为 {项目,值,单位};**返回供用户确认,不直接入库**(OCR 可能出错)。"""
    from app.services.lab_photo_parse import parse_lab_photo
    try:
        encoded = req.image_base64.split(",", 1)[-1]
        image_bytes = base64.b64decode(encoded, validate=True)
        validate_image_bytes(image_bytes, declared_extension=req.image_type)
    except (ValueError, UploadContentInvalid) as exc:
        raise HTTPException(status_code=400, detail="图片内容无效") from exc
    try:
        items = await parse_lab_photo(req.image_base64, req.image_type)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[lab_photo] 解析失败 user={current_user.id}: {e}")
        raise HTTPException(status_code=503, detail="解析服务暂不可用,请手动录入或重试")
    return {"items": items, "count": len(items),
            "note": "OCR 结果可能有误,请确认后再导入。"}


def parse_date(date_str) -> date:
    """将日期字符串转换为date对象"""
    if isinstance(date_str, date):
        return date_str
    if not date_str:
        return date.today()
    try:
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except ValueError:
        return date.today()


@router.post("/", response_model=MedicalExamResponse)
def create_medical_exam(
    exam: MedicalExamCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建体检记录"""
    # 忽略 payload 里的 user_id,强制绑到当前登录用户 (防止越权写别人数据)
    payload = exam.model_dump(exclude={"items", "user_id"})
    db_exam = MedicalExam(user_id=current_user.id, **payload)
    db.add(db_exam)
    db.flush()

    # 创建体检项目
    for item in exam.items:
        db_item = MedicalExamItem(
            exam_id=db_exam.id,
            **item.model_dump()
        )
        db.add(db_item)
        indicator = create_indicator_from_item(
            user_id=current_user.id, exam_id=db_exam.id,
            record_date=db_exam.exam_date,
            item_dict=item.model_dump(), source="manual",
        )
        db.add(indicator)

    db.commit()
    db.refresh(db_exam)
    return db_exam


# ========== 体检指标趋势 ==========

@router.get("/me/indicator-trends")
def get_my_indicator_trends(
    indicators: str = Query(default="HCY,ALT,GGT,TC,TG,FBG,UA,BMI", description="逗号分隔的指标代码"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取关键体检指标多年趋势（需要登录）"""
    from app.models.family_health import MedicalIndicator
    codes = [c.strip() for c in indicators.split(",") if c.strip()]

    results = {}
    for code in codes:
        rows = db.query(MedicalIndicator).filter(
            MedicalIndicator.user_id == current_user.id,
            MedicalIndicator.name_en == code
        ).order_by(MedicalIndicator.record_date).all()

        if rows:
            results[code] = {
                "name": rows[0].name,
                "unit": rows[0].unit,
                "reference_low": rows[0].reference_low,
                "reference_high": rows[0].reference_high,
                "data": [
                    {
                        "date": r.record_date.isoformat(),
                        "value": r.value,
                        "is_abnormal": r.is_abnormal,
                    }
                    for r in rows
                ]
            }

    return results


# ========== /me 端点必须在 /user/{user_id} 之前定义 ==========

@router.get("/me", response_model=List[MedicalExamResponse])
def get_my_medical_exams(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的体检记录（需要登录）"""
    exams = db.query(MedicalExam).filter(
        MedicalExam.user_id == current_user.id
    ).order_by(MedicalExam.exam_date.desc()).offset(skip).limit(limit).all()
    return exams


def _medical_exam_report_summary(exam: MedicalExam) -> dict:
    items = list(exam.items or [])
    abnormal_count = sum(
        1
        for item in items
        if str(item.is_abnormal or "").strip().lower() not in ("", "normal")
    )
    conclusions = exam.conclusions if isinstance(exam.conclusions, list) else []
    overall_assessment = exam.overall_assessment
    if overall_assessment and len(overall_assessment) > 500:
        overall_assessment = overall_assessment[:500] + "..."
    return {
        "id": exam.id,
        "exam_date": exam.exam_date,
        "exam_type": exam.exam_type,
        "body_system": exam.body_system,
        "hospital_name": exam.hospital_name,
        "doctor_name": exam.doctor_name,
        "overall_assessment": overall_assessment,
        "conclusions_count": len(conclusions),
        "items_count": len(items),
        "abnormal_items_count": abnormal_count,
        "created_at": exam.created_at,
    }


@router.get("/me/reports", response_model=List[MedicalExamReportSummary])
def get_my_medical_exam_report_summaries(
    skip: int = 0,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的体检/检查报告级摘要列表,不返回全量指标明细。"""
    exams = (
        db.query(MedicalExam)
        .options(selectinload(MedicalExam.items))
        .filter(MedicalExam.user_id == current_user.id)
        .order_by(MedicalExam.created_at.desc(), MedicalExam.exam_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_medical_exam_report_summary(exam) for exam in exams]


# ========== Calibrate UI: 单条 item 校正 (OCR 抽错值后用户回写) ==========

@router.get("/{exam_id}/explain", summary="体检异常解释包 (review #2, 2026-05-12)")
def get_exam_explain(
    exam_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """单次体检 → 异常项 + 基因关联 + 趋势 + LLM 解释 + 行动 + 复查建议.

    用户痛点是"我体检异常怎么办" — 这个端点把单次 exam 一次性聚合成
    "为什么异常 + 你能做什么 + 何时复查 + 找什么医生" 的完整包.
    """
    from app.services.exam_explain_service import build_exam_explain

    pkg = build_exam_explain(db, current_user.id, exam_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="体检不存在或无权限")
    return pkg


@router.patch("/items/{item_id}", response_model=MedicalExamItemResponse)
def update_medical_exam_item(
    item_id: int,
    body: MedicalExamItemUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手工校正单条 item — 同步更新 medical_indicators (按 exam_id + item_code/name 关联).

    第一次校正时, 把当前值快照到 original_value/original_value_text (作为 OCR 原值轨迹).
    """
    item = db.query(MedicalExamItem).filter(MedicalExamItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")

    exam = db.query(MedicalExam).filter(MedicalExam.id == item.exam_id).first()
    if not exam or exam.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    # 第一次校正: 把现值快照成 original
    if item.manually_corrected_at is None and item.original_value is None and item.original_value_text is None:
        item.original_value = item.value
        item.original_value_text = item.value_text

    payload = body.model_dump(exclude_unset=True)
    for field, val in payload.items():
        setattr(item, field, val)
    item.manually_corrected_at = datetime.now(timezone.utc)

    # 同步 medical_indicators — 按 exam_id + (item_code or item_name) 关联.
    # 历史 OCR 写入会同时落 MedicalIndicator (source='image_ocr'), 校正必须 mirror.
    from app.models.family_health import MedicalIndicator
    indicator_q = db.query(MedicalIndicator).filter(MedicalIndicator.exam_id == item.exam_id)
    if item.item_code:
        indicator = indicator_q.filter(MedicalIndicator.item_code == item.item_code).first()
    else:
        indicator = indicator_q.filter(MedicalIndicator.name == item.item_name).first()
    if indicator:
        if "value" in payload:
            indicator.value = item.value
        if "value_text" in payload:
            indicator.value_text = item.value_text
        if "unit" in payload:
            indicator.unit = item.unit
        if "reference_range" in payload:
            indicator.reference_range = item.reference_range
        if "is_abnormal" in payload:
            ab = (item.is_abnormal or "").strip().lower()
            indicator.is_abnormal = ab not in ("", "normal")
        if "item_name" in payload:
            indicator.name = item.item_name

    db.commit()
    db.refresh(item)

    # 让 Twin 重读 (基因/化验改动 → invalidate, 同 Iter 2 Day 1 hook)
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(current_user.id)
    except Exception:
        pass

    return item


@router.get("/user/{user_id}", response_model=List[MedicalExamResponse])
def get_user_medical_exams(
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的体检记录 (只能看自己的)"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能查看自己的体检记录")
    exams = db.query(MedicalExam).filter(
        MedicalExam.user_id == user_id
    ).order_by(MedicalExam.exam_date.desc()).offset(skip).limit(limit).all()
    return exams


@router.post("/import/json")
def import_medical_exam_from_json(
    exam_data: dict,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """从JSON格式导入体检数据"""
    service = MedicalExamImportService()
    exam = service.import_from_json(db, current_user.id, exam_data)
    return {"message": "导入成功", "exam_id": exam.id}


@router.post("/import/text")
def import_medical_exam_from_text(
    body: MedicalExamTextImportRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """从手工粘贴文本导入化验指标,用于 mobile OCR 失败后的兜底路径."""
    try:
        exam = MedicalExamImportService.import_from_text(
            db,
            user_id=current_user.id,
            text=body.text,
            exam_date=parse_date(body.exam_date),
            source="mobile_text",
        )
        if body.hospital_name:
            exam.hospital_name = body.hospital_name
        if body.exam_type:
            exam.exam_type = body.exam_type
        db.commit()
        db.refresh(exam)

        try:
            from app.twin.cache import invalidate_twin
            invalidate_twin(current_user.id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[体检文字] Twin invalidation 失败 (旁路): {e}")

        return {
            "message": "文字解析并导入成功",
            "exam_id": exam.id,
            "exam_date": str(exam.exam_date),
            "exam_type": exam.exam_type,
            "hospital_name": exam.hospital_name,
            "items_count": len(exam.items or []),
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"文字导入入库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")


@router.post("/import/csv")
async def import_medical_exam_from_csv(
    file: UploadFile = File(...),
    exam_info: dict = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """从CSV格式导入体检数据"""
    try:
        content = await read_upload_limited(file, max_bytes=MAX_CSV_BYTES)
        validate_csv_bytes(content)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail="CSV 文件过大") from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
        tmp_file.write(content)
        tmp_file_path = tmp_file.name

    try:
        service = MedicalExamImportService()
        exam = service.import_from_csv(db, current_user.id, tmp_file_path, exam_info or {})
        return {"message": "导入成功", "exam_id": exam.id}
    finally:
        os.unlink(tmp_file_path)


@router.post("/import/pdf")
async def import_medical_exam_from_pdf(
    file: UploadFile = File(..., description="PDF文件"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    从PDF格式导入体检数据

    上传体检报告PDF，系统会自动解析并结构化保存。
    使用AI分析PDF内容，提取检查项目、数值、参考范围等信息。
    """
    user_id = current_user.id
    try:
        content = await read_upload_limited(file, max_bytes=MAX_PDF_BYTES)
        validate_pdf_bytes(content)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail="PDF 文件过大") from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(content)
        tmp_file_path = tmp_file.name

    try:
        # 解析PDF
        logger.info(f"开始解析PDF: {file.filename}")
        parsed_data = pdf_parser.parse_pdf(tmp_file_path)
        logger.info(f"PDF解析完成，提取到 {len(parsed_data.get('items', []))} 个检查项目")

        # 创建体检记录
        db_exam = MedicalExam(
            user_id=user_id,
            patient_name=parsed_data.get("patient_name"),
            patient_gender=parsed_data.get("patient_gender"),
            patient_age=parsed_data.get("patient_age"),
            exam_number=parsed_data.get("exam_number"),
            exam_date=parse_date(parsed_data.get("exam_date")),
            exam_type=parsed_data.get("exam_type", "comprehensive"),
            body_system=parsed_data.get("body_system"),
            hospital_name=parsed_data.get("hospital_name"),
            doctor_name=parsed_data.get("doctor_name"),
            overall_assessment=parsed_data.get("overall_assessment"),
            conclusions=parsed_data.get("conclusions"),
            notes=f"从PDF导入: {file.filename}"
        )
        db.add(db_exam)
        db.flush()

        # 创建检查项目
        for item in parsed_data.get("items", []):
            # 处理value：可能是数字或None
            value = item.get("value")
            if isinstance(value, str):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = None

            db_item = MedicalExamItem(
                exam_id=db_exam.id,
                category=item.get("category"),
                item_name=item.get("item_name"),
                item_code=item.get("item_code"),
                value=value,
                value_text=item.get("value_text"),
                unit=item.get("unit"),
                reference_range=item.get("reference_range"),
                is_abnormal=item.get("is_abnormal", "normal"),
                notes=item.get("notes")
            )
            db.add(db_item)
            indicator = create_indicator_from_item(
                user_id=user_id, exam_id=db_exam.id,
                record_date=db_exam.exam_date,
                item_dict=item, source="pdf_import",
            )
            db.add(indicator)

        db.commit()
        db.refresh(db_exam)

        # 统计各类别项目数量
        category_counts = {}
        for item in parsed_data.get("items", []):
            cat = item.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Twin invalidation: 化验入库后让 specialist 立刻拿新数据 (旁路)
        try:
            from app.twin.cache import invalidate_twin
            invalidate_twin(user_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[体检PDF] Twin invalidation 失败 (旁路): {e}")

        return {
            "message": "PDF解析并导入成功",
            "exam_id": db_exam.id,
            "patient_name": db_exam.patient_name,
            "exam_date": str(db_exam.exam_date),
            "exam_type": db_exam.exam_type,
            "hospital_name": db_exam.hospital_name,
            "items_count": len(parsed_data.get("items", [])),
            "conclusions_count": len(parsed_data.get("conclusions", [])),
            "category_summary": category_counts,
            "parsed_data": parsed_data
        }

    except ValueError as e:
        logger.error(f"PDF解析失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"PDF导入失败: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
    finally:
        os.unlink(tmp_file_path)


@router.post("/import/image")
async def import_medical_exam_from_image(
    file: UploadFile = File(..., description="体检报告图片 (jpg/png/heic/webp)"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    从图片导入体检数据 (拍照路径)

    走 vision model OCR (medical_report_ocr.recognize_medical_report),
    返回结构化指标后按同 /import/pdf 的路径入库 (MedicalExam + MedicalExamItem + MedicalIndicator).
    """
    user_id = current_user.id

    filename = (file.filename or "").lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("jpg", "jpeg", "png", "heic", "webp"):
        raise HTTPException(status_code=400, detail="请上传图片文件 (jpg/png/heic/webp)")

    image_type = "jpeg" if ext in ("jpg", "jpeg") else ext

    try:
        content = await read_upload_limited(file, max_bytes=MAX_IMAGE_BYTES)
        image_type = validate_image_bytes(content, declared_extension=ext)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail="图片过大,请压缩后重试") from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    image_base64 = base64.b64encode(content).decode("ascii")

    logger.info(f"开始 OCR 识别体检报告图片: {file.filename} ({len(content)} bytes)")
    result = await recognize_medical_report(image_base64, image_type=image_type)

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    items = result.get("items", []) or []
    conclusion = (result.get("conclusion") or "").strip()
    # 准入门 (与聊天路径对齐, 只加不减方向): 数值项非空 OR 有诊断结论全文才入库。
    # 病理/影像报告常 0 数值项、只有诊断全文, 若仍硬性要求 items 会把它们全丢。
    if not items and not conclusion:
        raise HTTPException(status_code=422, detail="未能从图片中识别出检查指标或诊断结论,请换一张更清晰的照片")

    logger.info(f"OCR 识别完成: {result.get('report_type', '未知')} 共 {len(items)} 项")

    try:
        db_exam = MedicalExam(
            user_id=user_id,
            exam_date=parse_date(result.get("report_date")),
            exam_type=result.get("report_type", "comprehensive"),
            hospital_name=result.get("institution"),
            overall_assessment=conclusion or None,
            conclusions=result.get("conclusions"),
            notes=f"从图片 OCR 导入: {file.filename}"
        )
        db.add(db_exam)
        db.flush()

        for it in items:
            value = it.get("value")
            if isinstance(value, str):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = None

            # 红线#2: value=null 的病理/影像项不进数值异常门 —— 只有真数值项才标 abnormal。
            item_value_text = it.get("value_text")
            is_ab_flag = "abnormal" if (it.get("is_abnormal") and value is not None) else "normal"

            ref_range_str = None
            if it.get("reference_low") is not None and it.get("reference_high") is not None:
                ref_range_str = f"{it.get('reference_low')}-{it.get('reference_high')}"

            db_item = MedicalExamItem(
                exam_id=db_exam.id,
                item_name=it.get("name"),
                item_code=it.get("name_en"),
                value=value,
                value_text=item_value_text,
                unit=it.get("unit"),
                reference_range=ref_range_str,
                is_abnormal=is_ab_flag,
                source="ocr",
                original_value=value,
                original_value_text=item_value_text,
            )
            db.add(db_item)

            indicator = create_indicator_from_item(
                user_id=user_id, exam_id=db_exam.id,
                record_date=db_exam.exam_date,
                item_dict={
                    "item_name": it.get("name"),
                    "item_code": it.get("name_en"),
                    "value": value,
                    "value_text": item_value_text,
                    "unit": it.get("unit"),
                    "reference_low": it.get("reference_low"),
                    "reference_high": it.get("reference_high"),
                    "is_abnormal": bool(it.get("is_abnormal")) and value is not None,
                },
                source="image_ocr",
            )
            db.add(indicator)

        db.commit()
        db.refresh(db_exam)

        # 红线#2: 只统计有真实数值且标异常的项 —— value=null 的病理/影像项
        # 已在落库时压回 normal, 响应计数也不得把它们当数值异常上报。
        abnormal_count = sum(
            1 for i in items if i.get("is_abnormal") and i.get("value") is not None
        )

        # Twin invalidation: OCR 入库后让 specialist 立刻拿新数据 (旁路)
        try:
            from app.twin.cache import invalidate_twin
            invalidate_twin(user_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[化验图片] Twin invalidation 失败 (旁路): {e}")

        return {
            "message": "图片 OCR 导入成功",
            "exam_id": db_exam.id,
            "exam_date": str(db_exam.exam_date),
            "exam_type": db_exam.exam_type,
            "hospital_name": db_exam.hospital_name,
            "items_count": len(items),
            "abnormal_count": abnormal_count,
            "conclusion": result.get("conclusion"),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"图片导入入库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")


@router.post("/parse-pdf-preview")
async def parse_pdf_preview(
    file: UploadFile = File(..., description="PDF文件"),
    current_user: User = Depends(get_current_user_required),
):
    """
    预览PDF解析结果（不保存到数据库）

    用于在正式导入前预览解析结果，确认内容正确。
    需要登录 — 该路径会消耗 LLM vision 配额,不能裸奔.
    """
    try:
        content = await read_upload_limited(file, max_bytes=MAX_PDF_BYTES)
        validate_pdf_bytes(content)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail="PDF 文件过大") from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(content)
        tmp_file_path = tmp_file.name

    try:
        # 提取文本
        text_content = pdf_parser.extract_text_from_pdf(tmp_file_path)

        # 解析
        parsed_data = pdf_parser.parse_pdf(tmp_file_path)

        return {
            "message": "PDF解析成功",
            "filename": file.filename,
            "text_preview": text_content[:2000] + "..." if len(text_content) > 2000 else text_content,
            "parsed_data": parsed_data
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"PDF预览解析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        os.unlink(tmp_file_path)
