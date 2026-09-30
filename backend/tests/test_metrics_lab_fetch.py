"""tasks.metrics 化验取数 (SupplementAdvisor N-of-1 卡片的基线/目标)。数值均为合成值。

2026-09-30 事故排查: _fetch_lab_item 导入不存在的 MedicalExamRecord → ImportError 被吞 →
所有化验 metric 恒为 None。修好导入后只放开能按 biomarker registry 校验的指标 (LDL/HbA1c/空腹血糖);
微营养项 (Hcy/维生素D/B12/铁蛋白) 的关键字会取到别的项目, 继续返回 None (卡片显示「未测」)。
"""
import uuid
from datetime import date

import pytest

from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.user import User
from app.tasks.metrics import (
    fetch_b12,
    fetch_fasting_glucose,
    fetch_ferritin,
    fetch_hba1c,
    fetch_hcy,
    fetch_ldl,
    fetch_vitamin_d,
)

END = date(2026, 3, 1)
EXAM_DAY = date(2026, 2, 9)


def _user(db):
    u = User(username=f"m_{uuid.uuid4().hex[:8]}", email=f"m_{uuid.uuid4().hex[:8]}@example.com",
             hashed_password="x", name="测试", birth_date=date(1985, 1, 1), gender="男",
             is_active=True, is_approved=True)
    db.add(u)
    db.commit()
    return u


def _exam(db, user_id, d, items):
    exam = MedicalExam(user_id=user_id, exam_date=d, exam_type="comprehensive")
    db.add(exam)
    db.flush()
    for name, value, unit in items:
        db.add(MedicalExamItem(exam_id=exam.id, item_name=name, value=value, unit=unit, source="manual"))
    db.commit()


def test_fetch_ldl_skips_same_day_vldl(db):
    u = _user(db)
    _exam(db, u.id, EXAM_DAY, [("低密度脂蛋白-C", 3.1, "mmol/L"), ("极低密度脂蛋白-C", 0.7, "mmol/L")])
    assert fetch_ldl(db, u.id, END) == 3.1


def test_fetch_hba1c_reads_standard_a1c(db):
    u = _user(db)
    _exam(db, u.id, EXAM_DAY, [("糖化血红蛋白", 5.6, "%"), ("糖化血红蛋白A1", 7.4, "%")])
    assert fetch_hba1c(db, u.id, END) == 5.6


def test_fetch_fasting_glucose_converts_mg_dl(db):
    u = _user(db)
    _exam(db, u.id, EXAM_DAY, [("空腹血糖", 108, "mg/dL")])
    assert fetch_fasting_glucose(db, u.id, END) == pytest.approx(6.0, abs=0.01)


@pytest.mark.parametrize("fetch,items", [
    (fetch_vitamin_d, [("25-羟基维生素D(总)", 18, "ng/mL"), ("25-羟基维生素D2", 0.8, "ng/mL")]),
    (fetch_vitamin_d, [("25-羟基维生素D", 15, "ng/mL"), ("1,25-二羟基维生素D3", 48, "pg/mL")]),
    (fetch_b12, [("维生素B12", 180, "pg/mL"), ("全转钴胺素(HoloTC) B12", 32, "pmol/L")]),
    (fetch_ferritin, [("转铁蛋白", 2.5, "g/L"), ("铁蛋白", 120, "ng/mL")]),
    (fetch_hcy, [("同型半胱氨酸", 13.8, "μmol/L")]),
])
def test_micronutrient_fetchers_stay_unvalidated_none(db, fetch, items):
    """关键字会取到分量/别的项目当基线, 进 N-of-1 卡片的目标 —— 没有 canonical 校验前宁可「未测」。"""
    u = _user(db)
    _exam(db, u.id, EXAM_DAY, items)
    assert fetch(db, u.id, END) is None
