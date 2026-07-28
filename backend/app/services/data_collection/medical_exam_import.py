"""体检数据导入服务"""
import csv
from typing import List, Dict, Any, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.schemas.medical_exam import MedicalExamCreate, MedicalExamItemCreate
from app.models.medical_exam import ExamType, BodySystem
from app.services.exam_packages import create_indicator_from_item


class MedicalExamImportService:
    """体检数据导入服务"""

    @staticmethod
    def _ingest_biomarkers(db: Session, db_exam) -> None:
        """旁路: 体检入库后归一化为 BiomarkerObservation (PRD P1 接通). 失败不影响导入。"""
        try:
            from app.services.biomarker_service import ingest_exam
            ingest_exam(db, db_exam)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("biomarker ingest skipped for exam %s", getattr(db_exam, "id", "?"))

    @staticmethod
    def import_from_items(
        db: Session,
        user_id: int,
        items_data: List[Dict[str, Any]],
        exam_date: date | None = None,
        exam_type: str = "comprehensive",
        hospital_name: Optional[str] = None,
        notes: Optional[str] = None,
        source: str = "agent_text",
        overall_assessment: Optional[str] = None,
        conclusions: Optional[list] = None,
        source_fingerprint: Optional[str] = None,
    ) -> MedicalExam:
        """Persist already-structured lab items into the canonical exam tables.

        ``overall_assessment`` carries the verbatim narrative conclusion (病理/影像
        诊断全文) and ``conclusions`` the structured结论列表. Narrative reports
        (病理/影像) often have zero numeric items but a load-bearing diagnosis —
        so we accept the import when EITHER numeric items OR an overall_assessment
        is present, and only reject when both are empty.
        """
        has_items = bool(items_data)
        has_narrative = bool(overall_assessment and str(overall_assessment).strip())
        if not has_items and not has_narrative:
            raise ValueError("既无化验指标也无诊断结论,无可导入内容")

        db_exam = MedicalExam(
            user_id=user_id,
            exam_date=exam_date or date.today(),
            exam_type=exam_type,
            hospital_name=hospital_name,
            notes=notes,
            overall_assessment=overall_assessment,
            conclusions=conclusions,
            source_fingerprint=source_fingerprint,
        )
        db.add(db_exam)
        db.flush()

        for item_data in items_data:
            value = item_data.get("value")
            if isinstance(value, str):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = None
            is_abnormal_raw = item_data.get("is_abnormal", "normal")
            if isinstance(is_abnormal_raw, bool):
                item_abnormal = "abnormal" if is_abnormal_raw else "normal"
            else:
                item_abnormal = str(is_abnormal_raw or "normal")
            # 红线#2: value=null 的病理/影像自由文本项绝不进数值异常门。
            # 无数值时把异常标记压回 normal, 只保留 value_text 里的逐字诊断原文。
            if value is None:
                item_abnormal = "normal"

            item_payload = {
                "category": item_data.get("category"),
                "item_name": item_data.get("item_name") or item_data.get("name") or item_data.get("item_code") or "未命名指标",
                "item_code": item_data.get("item_code") or item_data.get("name_en"),
                "value": value,
                "value_text": item_data.get("value_text"),
                "unit": item_data.get("unit"),
                "reference_range": item_data.get("reference_range"),
                "result": item_data.get("result"),
                "is_abnormal": item_abnormal,
                "notes": item_data.get("notes"),
            }
            db.add(MedicalExamItem(exam_id=db_exam.id, source=source, **item_payload))
            db.add(
                create_indicator_from_item(
                    user_id=user_id,
                    exam_id=db_exam.id,
                    record_date=db_exam.exam_date,
                    item_dict={
                        **item_payload,
                        "reference_low": item_data.get("reference_low"),
                        "reference_high": item_data.get("reference_high"),
                        "severity": item_data.get("severity"),
                    },
                    source=source,
                )
            )

        db.commit()
        db.refresh(db_exam)
        MedicalExamImportService._ingest_biomarkers(db, db_exam)
        return db_exam

    @staticmethod
    def import_from_text(
        db: Session,
        user_id: int,
        text: str,
        exam_date: date | None = None,
        source: str = "agent_text",
    ) -> MedicalExam:
        """Parse pasted/chat lab text and persist all recognized indicators."""
        from app.services.medical_text_parser import parse_lab_indicators_from_text

        items = parse_lab_indicators_from_text(text)
        if not items:
            raise ValueError("未能从文本中识别出可入库的化验指标")
        import_note = (
            "从手工粘贴文本导入，原文未复制到备注。"
            if source == "mobile_text"
            else "从文本导入，原文未复制到备注。"
        )
        return MedicalExamImportService.import_from_items(
            db,
            user_id=user_id,
            items_data=items,
            exam_date=exam_date,
            exam_type="biochemistry",
            notes=import_note,
            source=source,
        )

    @staticmethod
    def import_from_json(
        db: Session,
        user_id: int,
        json_data: Dict[str, Any],
        source: str = "json_import",
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
            indicator = create_indicator_from_item(
                user_id=user_id, exam_id=db_exam.id,
                record_date=db_exam.exam_date,
                item_dict=item_create.model_dump(), source=source,
            )
            db.add(indicator)

        db.commit()
        db.refresh(db_exam)
        MedicalExamImportService._ingest_biomarkers(db, db_exam)
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

        return MedicalExamImportService.import_from_json(db, user_id, exam_data, source="csv_import")

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

        return MedicalExamImportService.import_from_json(db, user_id, exam_data, source="csv_import")
