"""体检数据API"""
import tempfile
import os
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

router = APIRouter()
logger = logging.getLogger(__name__)


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
    db: Session = Depends(get_db)
):
    """创建体检记录"""
    db_exam = MedicalExam(**exam.model_dump(exclude={"items"}))
    db.add(db_exam)
    db.flush()
    
    # 创建体检项目
    for item in exam.items:
        db_item = MedicalExamItem(
            exam_id=db_exam.id,
            **item.model_dump()
        )
        db.add(db_item)
    
    db.commit()
    db.refresh(db_exam)
    return db_exam


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
    db: Session = Depends(get_db)
):
    """获取用户的体检记录"""
    exams = db.query(MedicalExam).filter(
        MedicalExam.user_id == user_id
    ).order_by(MedicalExam.exam_date.desc()).offset(skip).limit(limit).all()
    return exams


@router.post("/import/json")
def import_medical_exam_from_json(
    user_id: int,
    exam_data: dict,
    db: Session = Depends(get_db)
):
    """从JSON格式导入体检数据"""
    service = MedicalExamImportService()
    exam = service.import_from_json(db, user_id, exam_data)
    return {"message": "导入成功", "exam_id": exam.id}


@router.post("/import/csv")
async def import_medical_exam_from_csv(
    user_id: int,
    file: UploadFile = File(...),
    exam_info: dict = None,
    db: Session = Depends(get_db)
):
    """从CSV格式导入体检数据"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name
    
    try:
        service = MedicalExamImportService()
        exam = service.import_from_csv(db, user_id, tmp_file_path, exam_info or {})
        return {"message": "导入成功", "exam_id": exam.id}
    finally:
        os.unlink(tmp_file_path)


@router.post("/import/pdf")
async def import_medical_exam_from_pdf(
    user_id: int = Query(..., description="用户ID"),
    file: UploadFile = File(..., description="PDF文件"),
    db: Session = Depends(get_db)
):
    """
    从PDF格式导入体检数据
    
    上传体检报告PDF，系统会自动解析并结构化保存。
    使用AI分析PDF内容，提取检查项目、数值、参考范围等信息。
    """
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
                value=value,
                value_text=item.get("value_text"),
                unit=item.get("unit"),
                reference_range=item.get("reference_range"),
                is_abnormal=item.get("is_abnormal", "normal"),
                notes=item.get("notes")
            )
            db.add(db_item)
        
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


@router.post("/parse-pdf-preview")
async def parse_pdf_preview(
    file: UploadFile = File(..., description="PDF文件")
):
    """
    预览PDF解析结果（不保存到数据库）
    
    用于在正式导入前预览解析结果，确认内容正确。
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

