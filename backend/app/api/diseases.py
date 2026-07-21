"""疾病记录API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas.disease import DiseaseRecordCreate, DiseaseRecordResponse
from app.models.disease import DiseaseRecord
from app.models.user import User
from app.api.deps import get_current_user_required, require_self_or_admin

router = APIRouter()


@router.post("/", response_model=DiseaseRecordResponse)
def create_disease_record(
    disease: DiseaseRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建疾病记录"""
    require_self_or_admin(current_user, disease.user_id, resource="疾病记录")
    db_disease = DiseaseRecord(**disease.model_dump())
    db.add(db_disease)
    db.commit()
    db.refresh(db_disease)
    return db_disease


@router.get("/user/{user_id}", response_model=List[DiseaseRecordResponse])
def get_user_disease_records(
    user_id: int,
    status: str = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的疾病记录"""
    require_self_or_admin(current_user, user_id, resource="疾病记录")
    query = db.query(DiseaseRecord).filter(DiseaseRecord.user_id == user_id)

    if status:
        query = query.filter(DiseaseRecord.status == status)

    diseases = query.order_by(DiseaseRecord.diagnosis_date.desc()).offset(skip).limit(limit).all()
    return diseases


@router.get("/{disease_id}", response_model=DiseaseRecordResponse)
def get_disease_record(
    disease_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取疾病记录详情"""
    query = db.query(DiseaseRecord).filter(DiseaseRecord.id == disease_id)
    if not getattr(current_user, "is_admin", False):
        query = query.filter(DiseaseRecord.user_id == current_user.id)
    disease = query.first()
    if not disease:
        raise HTTPException(status_code=404, detail="疾病记录不存在")
    return disease
