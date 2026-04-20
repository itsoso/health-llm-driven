"""
存量数据迁移：medical_exam_items → medical_indicators

用法:
  cd backend
  source venv/bin/activate
  python scripts/migrate_exam_items_to_indicators.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.family_health import MedicalIndicator
from app.services.exam_packages import create_indicator_from_item


def migrate(batch_size: int = 100):
    db: Session = SessionLocal()
    try:
        exams = (
            db.query(MedicalExam)
            .order_by(MedicalExam.exam_date)
            .all()
        )
        total = 0
        migrated = 0
        skipped = 0
        failed = 0

        for exam in exams:
            items = (
                db.query(MedicalExamItem)
                .filter(MedicalExamItem.exam_id == exam.id)
                .all()
            )
            for item in items:
                total += 1
                existing = (
                    db.query(MedicalIndicator.id)
                    .filter(
                        MedicalIndicator.user_id == exam.user_id,
                        MedicalIndicator.name == item.item_name,
                        MedicalIndicator.record_date == exam.exam_date,
                        MedicalIndicator.exam_id == exam.id,
                    )
                    .first()
                )
                if existing:
                    skipped += 1
                    continue
                try:
                    indicator = create_indicator_from_item(
                        user_id=exam.user_id,
                        exam_id=exam.id,
                        record_date=exam.exam_date,
                        item_dict={
                            "item_name": item.item_name,
                            "item_code": item.item_code,
                            "value": item.value,
                            "value_text": item.value_text,
                            "unit": item.unit,
                            "reference_range": item.reference_range,
                            "is_abnormal": item.is_abnormal,
                            "result": item.result,
                            "category": item.category,
                            "notes": item.notes,
                        },
                        source="pdf_import" if (exam.notes and "PDF" in exam.notes) else "manual",
                    )
                    db.add(indicator)
                    migrated += 1
                except Exception as e:
                    failed += 1
                    print(f"  FAIL item_id={item.id} ({item.item_name}): {e}")

                if migrated % batch_size == 0 and migrated > 0:
                    db.commit()
                    print(f"  committed {migrated} rows...")

        db.commit()
        print(f"\nDone: total={total} migrated={migrated} skipped={skipped} failed={failed}")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
