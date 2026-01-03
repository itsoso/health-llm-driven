"""体检数据导入服务"""
import json
import csv
from typing import List, Dict, Any, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.user import User
from app.schemas.medical_exam import MedicalExamCreate, MedicalExamItemCreate
from app.models.medical_exam import ExamType, BodySystem


class MedicalExamImportService:
    """体检数据导入服务"""
    
    @staticmethod
    def import_from_json(
        db: Session,
        user_id: int,
        json_data: Dict[str, Any]
    ) -> MedicalExam:
        """从JSON格式导入体检数据"""
        exam_data = json_data.get("exam", {})
        items_data = json_data.get("items", [])
        
        # 创建体检记录
        exam_create = MedicalExamCreate(
            user_id=user_id,
            exam_date=date.fromisoformat(exam_data["exam_date"]) if isinstance(exam_data.get("exam_date"), str) else exam_data.get("exam_date"),
            exam_type=ExamType(exam_data["exam_type"]) if isinstance(exam_data.get("exam_type"), str) else exam_data.get("exam_type"),
            body_system=BodySystem(exam_data["body_system"]) if exam_data.get("body_system") and isinstance(exam_data.get("body_system"), str) else exam_data.get("body_system"),
            hospital_name=exam_data.get("hospital_name"),
            doctor_name=exam_data.get("doctor_name"),
            overall_assessment=exam_data.get("overall_assessment"),
            notes=exam_data.get("notes"),
            items=[]
        )
        
        # 创建体检项目
        for item_data in items_data:
            exam_create.items.append(MedicalExamItemCreate(**item_data))
        
        # 保存到数据库
        db_exam = MedicalExam(**exam_create.model_dump(exclude={"items"}))
        db.add(db_exam)
        db.flush()
        
        # 保存体检项目
        for item_create in exam_create.items:
            db_item = MedicalExamItem(
                exam_id=db_exam.id,
                **item_create.model_dump()
            )
            db.add(db_item)
        
        db.commit()
        db.refresh(db_exam)
        return db_exam
    
    @staticmethod
    def import_from_csv(
        db: Session,
        user_id: int,
        csv_file_path: str,
        exam_info: Dict[str, Any]
    ) -> MedicalExam:
        """从CSV格式导入体检数据"""
        items = []
        
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append(MedicalExamItemCreate(
                    item_name=row.get("item_name", ""),
                    item_code=row.get("item_code"),
                    value=float(row["value"]) if row.get("value") else None,
                    unit=row.get("unit"),
                    reference_range=row.get("reference_range"),
                    result=row.get("result"),
                    is_abnormal=row.get("is_abnormal", "normal"),
                    notes=row.get("notes")
                ))
        
        exam_data = {
            "exam": exam_info,
            "items": [item.model_dump() for item in items]
        }
        
        return MedicalExamImportService.import_from_json(db, user_id, exam_data)
    
    @staticmethod
    def import_from_excel(
        db: Session,
        user_id: int,
        excel_file_path: str,
        exam_info: Dict[str, Any]
    ) -> MedicalExam:
        """
        从Excel格式导入体检数据
        
        注意：需要安装 pandas 和 openpyxl
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("需要安装pandas和openpyxl: pip install pandas openpyxl")
        
        df = pd.read_excel(excel_file_path)
        items = []
        
        for _, row in df.iterrows():
            items.append(MedicalExamItemCreate(
                item_name=row.get("item_name", ""),
                item_code=row.get("item_code"),
                value=float(row["value"]) if pd.notna(row.get("value")) else None,
                unit=row.get("unit"),
                reference_range=row.get("reference_range"),
                result=row.get("result"),
                is_abnormal=row.get("is_abnormal", "normal"),
                notes=row.get("notes")
            ))
        
        exam_data = {
            "exam": exam_info,
            "items": [item.model_dump() for item in items]
        }
        
        return MedicalExamImportService.import_from_json(db, user_id, exam_data)

