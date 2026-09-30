"""scripts/reconcile_biomarkers.py: 默认 dry-run 必须零写入; 每条删除都说明原因; --apply 才提交,
且遇到说不清原因的删除 (DROPPED) 拒绝提交。数值均为合成值。

dry-run 依赖「外层事务 + SAVEPOINT 会话」回滚服务函数内部的 commit —— 只在 PostgreSQL 上验证
(pysqlite 的 SAVEPOINT 语义不可靠, 生产也是 PostgreSQL)。
"""
import importlib.util
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest

from app.models.biomarker_observation import BiomarkerObservation
from app.models.family_health import MedicalIndicator
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.user import User

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reconcile_biomarkers.py"
DAY = date(2026, 1, 15)


@pytest.fixture
def pg_db(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("SAVEPOINT 回滚语义只在 PostgreSQL 上验证 (设 TEST_DATABASE_URL)")
    return db


def _load_script():
    spec = importlib.util.spec_from_file_location("reconcile_biomarkers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _user(db):
    user = User(username=f"r_{uuid.uuid4().hex[:8]}", email=f"r_{uuid.uuid4().hex[:8]}@example.com",
                hashed_password="x", name="测试", gender="男", is_active=True, is_approved=True)
    db.add(user)
    db.flush()
    return user


def _row(db, user_id, code, value, unit, source, item_id=None):
    db.add(BiomarkerObservation(user_id=user_id, code=code, domain="x", value=value, unit=unit,
                                normalized_value=value, normalized_unit=unit, flag="normal",
                                observed_at=datetime(DAY.year, DAY.month, DAY.day), source=source,
                                source_exam_item_id=item_id))


def _seed(db):
    """未归一化的体检 + 旧映射写下的 VLDL-as-LDL 行 + 旧 CREA(ml/min) 行 + 一条重复的 sync 行。"""
    user = _user(db)
    exam = MedicalExam(user_id=user.id, exam_date=DAY, exam_type="biochemistry")
    db.add(exam)
    db.flush()
    ldl = MedicalExamItem(exam_id=exam.id, item_name="低密度脂蛋白-C", value=3.1, unit="mmol/L", source="manual")
    vldl = MedicalExamItem(exam_id=exam.id, item_name="极低密度脂蛋白-C", value=0.7, unit="mmol/L", source="manual")
    db.add_all([ldl, vldl])
    db.add(MedicalIndicator(user_id=user.id, name="肾小球滤过率(EPI-cr)", value=96, unit="ml/min", record_date=DAY))
    db.add(MedicalIndicator(user_id=user.id, exam_id=exam.id, name="低密度脂蛋白-C", value=3.1, unit="mmol/L",
                            record_date=DAY))
    db.flush()
    _row(db, user.id, "lipid_ldl", 0.7, "mmol/L", "manual", item_id=vldl.id)
    _row(db, user.id, "CREA", 96, "ml/min", "indicator_sync")
    _row(db, user.id, "lipid_ldl", 3.1, "mmol/L", "indicator_sync")
    db.commit()
    return user.id


def _rows(db, uid):
    db.expire_all()
    return sorted(
        (r.code, r.normalized_value, r.source)
        for r in db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == uid)
    )


def test_dry_run_labels_every_delete_and_apply_reconciles(pg_db):
    db = pg_db
    script = _load_script()
    uid = _seed(db)
    before = _rows(db, uid)

    with db.get_bind().connect() as conn:
        plans, committed = script.run(conn, [uid], apply=False)
    assert committed is False
    assert _rows(db, uid) == before  # dry-run 零写入

    reasons = {(row["code"], row["reason"].split(":")[0].split(" #")[0]) for row in plans[0]["deleted"].values()}
    assert reasons == {
        ("lipid_ldl", "mapping invalid"),   # VLDL 的 exam 行: 源项目现在被拒收
        ("CREA", "remapped to egfr"),       # 旧首命中逻辑写下的肌酐行: 源指标现在归 eGFR
        ("lipid_ldl", "superseded by"),     # 与 exam 同一次测量的 sync 行
    }
    assert not any(row["dropped"] for row in plans[0]["deleted"].values())

    with db.get_bind().connect() as conn:
        _plans, committed = script.run(conn, [uid], apply=True)
    assert committed is True
    assert _rows(db, uid) == [("egfr", 96, "indicator_sync"), ("lipid_ldl", 3.1, "manual")]


def test_apply_refuses_unexplained_drops(pg_db, monkeypatch):
    """安全网: 若对账把一条仍可推导的测量删掉 (逻辑缺陷), 标 DROPPED 且 --apply 拒绝提交。"""
    db = pg_db
    script = _load_script()
    user = _user(db)
    db.add(MedicalIndicator(user_id=user.id, name="谷氨酰转肽酶", value=72, unit="U/L", record_date=DAY))
    _row(db, user.id, "GGT", 72, "U/L", "indicator_sync")
    db.commit()

    def _buggy_sync(session, user_id):
        session.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user_id).delete()
        session.commit()
        return {}

    monkeypatch.setattr(script, "sync_indicators_to_biomarkers", _buggy_sync)
    with db.get_bind().connect() as conn:
        plans, committed = script.run(conn, [user.id], apply=True)

    assert committed is False
    assert [row["reason"] for row in plans[0]["deleted"].values()] == ["DROPPED"]
    assert _rows(db, user.id) == [("GGT", 72, "indicator_sync")]


def test_same_value_reading_of_another_analyte_cannot_mask_a_drop(pg_db, monkeypatch):
    """同日同值的别的指标 (空腹血糖 72? 这里用尿酸 72) 不能把真丢失标成 remapped 而让 --apply 通过。"""
    db = pg_db
    script = _load_script()
    user = _user(db)
    db.add(MedicalIndicator(user_id=user.id, name="尿酸碱度", value=72, unit=None, record_date=DAY))
    db.add(MedicalIndicator(user_id=user.id, name="谷氨酰转肽酶", value=72, unit="U/L", record_date=DAY))
    _row(db, user.id, "GGT", 72, "U/L", "indicator_sync")
    db.commit()

    def _buggy_sync(session, user_id):
        session.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user_id).delete()
        session.commit()
        return {}

    monkeypatch.setattr(script, "sync_indicators_to_biomarkers", _buggy_sync)
    with db.get_bind().connect() as conn:
        plans, committed = script.run(conn, [user.id], apply=True)

    assert committed is False
    assert [row["reason"] for row in plans[0]["deleted"].values()] == ["DROPPED"]
