"""体检数据API"""
import tempfile
import os
import base64
import logging
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas.medical_exam import MedicalExamCreate, MedicalExamResponse
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.data_collection.medical_exam_import import MedicalExamImportService
from app.services.pdf_parser import pdf_parser
from app.services.exam_packages import create_indicator_from_item
from app.services.ai.medical_report_ocr import recognize_medical_report

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB,防 OCR 被大图灌穿


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


@router.post("/import/csv")
async def import_medical_exam_from_csv(
    file: UploadFile = File(...),
    exam_info: dict = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """从CSV格式导入体检数据"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
        content = await file.read()
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
    # 验证文件类型
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="请上传PDF格式文件")

    # 保存上传的文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        content = await file.read()
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

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"图片过大 ({len(content) // 1024 // 1024}MB),请压缩到 {MAX_IMAGE_BYTES // 1024 // 1024}MB 以内"
        )
    image_base64 = base64.b64encode(content).decode("ascii")

    logger.info(f"开始 OCR 识别体检报告图片: {file.filename} ({len(content)} bytes)")
    result = await recognize_medical_report(image_base64, image_type=image_type)

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    items = result.get("items", []) or []
    if not items:
        raise HTTPException(status_code=422, detail="未能从图片中识别出检查指标,请换一张更清晰的照片")

    logger.info(f"OCR 识别完成: {result.get('report_type', '未知')} 共 {len(items)} 项")

    try:
        db_exam = MedicalExam(
            user_id=user_id,
            exam_date=parse_date(result.get("report_date")),
            exam_type=result.get("report_type", "comprehensive"),
            hospital_name=result.get("institution"),
            overall_assessment=result.get("conclusion"),
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

            is_ab_flag = "abnormal" if it.get("is_abnormal") else "normal"

            ref_range_str = None
            if it.get("reference_low") is not None and it.get("reference_high") is not None:
                ref_range_str = f"{it.get('reference_low')}-{it.get('reference_high')}"

            db_item = MedicalExamItem(
                exam_id=db_exam.id,
                item_name=it.get("name"),
                item_code=it.get("name_en"),
                value=value,
                unit=it.get("unit"),
                reference_range=ref_range_str,
                is_abnormal=is_ab_flag,
            )
            db.add(db_item)

            indicator = create_indicator_from_item(
                user_id=user_id, exam_id=db_exam.id,
                record_date=db_exam.exam_date,
                item_dict={
                    "item_name": it.get("name"),
                    "item_code": it.get("name_en"),
                    "value": value,
                    "unit": it.get("unit"),
                    "reference_low": it.get("reference_low"),
                    "reference_high": it.get("reference_high"),
                    "is_abnormal": bool(it.get("is_abnormal")),
                },
                source="image_ocr",
            )
            db.add(indicator)

        db.commit()
        db.refresh(db_exam)

        abnormal_count = sum(1 for i in items if i.get("is_abnormal"))

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
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="请上传PDF格式文件")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        content = await file.read()
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
