"""体检数据API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas.medical_exam import MedicalExamCreate, MedicalExamResponse
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.services.data_collection.medical_exam_import import MedicalExamImportService

router = APIRouter()


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
    # 保存上传的文件
    import tempfile
    import os
    
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

