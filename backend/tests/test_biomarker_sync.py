"""medical_indicators → biomarker_observations 同步。钉:识别归一/跳过未知/幂等/周期刷新。"""
from datetime import date, datetime

from sqlalchemy import text

from app.models.biomarker_observation import BiomarkerObservation
from app.services.biomarker_sync import sync_indicators_to_biomarkers


def _seed_ind(db, user_id, name, value, d, unit="U/L"):
    db.execute(text(
        "INSERT INTO medical_indicators (user_id, name, value, unit, record_date) "
        "VALUES (:u, :n, :v, :unit, :d)"
    ), {"u": user_id, "n": name, "v": value, "unit": unit, "d": d})
    db.commit()


def _exam_item(db, user_id, name, value, d, unit="U/L"):
    """真实 exam + item (PostgreSQL 强制 source_exam_item_id 外键; 假 id 只在 SQLite 下能过)。"""
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    exam = MedicalExam(user_id=user_id, exam_date=d, exam_type="biochemistry")
    db.add(exam)
    db.flush()
    item = MedicalExamItem(exam_id=exam.id, item_name=name, value=value, unit=unit, source="exam")
    db.add(item)
    db.commit()
    return item


def test_sync_recognizes_and_writes(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2025, 8, 1))
    _seed_ind(db, user.id, "甘油三酯", 2.1, date(2026, 5, 1), unit="mmol/L")
    _seed_ind(db, user.id, "某不存在的指标", 99, date(2026, 5, 1))  # definitions 外 → 跳过

    r = sync_indicators_to_biomarkers(db, user.id)
    assert r["scanned"] == 3 and r["recognized"] == 2 and r["written"] == 2
    obs = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user.id).all()
    codes = {o.code for o in obs}
    assert "GGT" in codes and "lipid_tg" in codes
    ggt = next(o for o in obs if o.code == "GGT")
    assert ggt.normalized_value == 78 and ggt.abnormal is True  # 78 > 60 ULN


def test_sync_is_idempotent(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "谷草转氨酶", 32, date(2025, 8, 1))
    sync_indicators_to_biomarkers(db, user.id)
    sync_indicators_to_biomarkers(db, user.id)  # 再跑一次不应翻倍
    n = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user.id).count()
    assert n == 1


def test_sync_updates_existing_on_value_change(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2025, 8, 1))
    sync_indicators_to_biomarkers(db, user.id)
    # 改同日期同指标的值(纠错场景)→ 更新非新增
    db.execute(text("UPDATE medical_indicators SET value = 70 WHERE user_id = :u"), {"u": user.id})
    db.commit()
    sync_indicators_to_biomarkers(db, user.id)
    obs = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user.id).all()
    assert len(obs) == 1 and obs[0].normalized_value == 70


def test_sync_skips_when_exam_source_exists_same_day(client, db):
    """跨源去重:同日同指标先有 exam 来源的 observation → sync 跳过,不产生重复行。"""
    from tests.conftest import create_authenticated_user
    from app.services.biomarker_service import observe_exam_item
    user, _ = create_authenticated_user(db)

    # 先走 exam 路径落一行(source != indicator_sync),observed_at 带时分
    item = _exam_item(db, user.id, "谷氨酰转肽酶", 78, date(2026, 5, 1))
    observe_exam_item(
        db, user.id, item,
        observed_at=datetime(2026, 5, 1, 9, 30),  # 带时分,与午夜 datetime 不等
    )

    # 再走 sync 路径:同日同指标(record_date 仅日期)
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2026, 5, 1))
    r = sync_indicators_to_biomarkers(db, user.id)

    obs = db.query(BiomarkerObservation).filter(
        BiomarkerObservation.user_id == user.id,
        BiomarkerObservation.code == "GGT",
    ).all()
    assert len(obs) == 1  # 只有 1 行,无重复
    assert obs[0].source == "exam"  # exam 优先,未被 sync 覆盖
    assert r["skipped"] == 1
    assert r["written"] == 0


def test_sync_skip_is_idempotent_across_reruns(client, db):
    """跨源跳过场景重跑仍只 1 行(幂等)。"""
    from tests.conftest import create_authenticated_user
    from app.services.biomarker_service import observe_exam_item
    user, _ = create_authenticated_user(db)

    item = _exam_item(db, user.id, "谷氨酰转肽酶", 78, date(2026, 5, 1))
    observe_exam_item(db, user.id, item, observed_at=datetime(2026, 5, 1, 9, 30))
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2026, 5, 1))

    sync_indicators_to_biomarkers(db, user.id)
    sync_indicators_to_biomarkers(db, user.id)  # 重跑不应翻倍

    n = db.query(BiomarkerObservation).filter(
        BiomarkerObservation.user_id == user.id,
        BiomarkerObservation.code == "GGT",
    ).count()
    assert n == 1


def test_biomarker_sync_endpoint(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    _seed_ind(db, user.id, "空腹血糖", 6.5, date(2026, 5, 1), unit="mmol/L")
    r = client.post("/api/v1/chronic/biomarker-sync",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["sync"]["written"] == 1
    assert client.post("/api/v1/chronic/biomarker-sync").status_code in (401, 403)


def test_refresh_cycle_targets_fills_empty(client, db):
    """根因修复:开周期时归一层空 → 空目标;sync 后 refresh 应补出目标。"""
    from tests.conftest import create_authenticated_user
    from app.models.intervention_cycle import InterventionCycle
    from app.services.intervention_cycle_service import refresh_cycle_targets
    user, _ = create_authenticated_user(db)
    # 异常指标:GGT 78(>60)
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2026, 5, 1))
    cycle = InterventionCycle(user_id=user.id, cycle_type="metabolic_90d", status="active",
                              start_date=date(2026, 6, 1), planned_end_date=date(2026, 9, 1),
                              target_metrics=[])
    db.add(cycle)
    db.commit()
    assert cycle.target_metrics == []  # 空目标(根因)

    sync_indicators_to_biomarkers(db, user.id)
    refresh_cycle_targets(db, cycle)
    codes = {s["code"] for s in cycle.target_metrics}
    assert "GGT" in codes  # 现在有目标了
    assert len(cycle.outcomes) >= 1  # OutcomeMetric 也建了基线


# ── 2026-09-30 事故回归 (合成数值) ─────────────────────────────────────────

def _obs(db, user_id, code=None):
    q = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user_id)
    if code is not None:
        q = q.filter(BiomarkerObservation.code == code)
    return q.all()


def _pairs(db, user_id):
    db.expire_all()
    return sorted((r.code, r.normalized_value, r.source) for r in _obs(db, user_id))


def test_sync_same_day_indicators_write_one_row(client, db):
    """autoflush=False: 同一次 sync 里前面 add 的行对后续查询不可见 → 旧实现同一次测量写出多行。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "低密度脂蛋白-C", 3.1, date(2026, 1, 15), unit="mmol/L")
    _seed_ind(db, user.id, "LDL-C", 3.1, date(2026, 1, 15), unit="mmol/L")

    sync_indicators_to_biomarkers(db, user.id)
    sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("lipid_ldl", 3.1, "indicator_sync")]


def test_sync_keeps_distinct_same_day_values(client, db):
    """同日不同值是两次测量: 旧实现「每 (code, 日) 一行」会丢掉其中一个。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "尿酸", 480, date(2026, 1, 15), unit="μmol/L")
    _seed_ind(db, user.id, "尿酸", 510, date(2026, 1, 15), unit="μmol/L")

    sync_indicators_to_biomarkers(db, user.id)
    sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("UA", 480, "indicator_sync"), ("UA", 510, "indicator_sync")]


def test_sync_does_not_write_vldl_as_ldl(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "低密度脂蛋白-C", 3.1, date(2026, 1, 15), unit="mmol/L")
    _seed_ind(db, user.id, "极低密度脂蛋白-C", 0.7, date(2026, 1, 15), unit="mmol/L")

    sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("lipid_ldl", 3.1, "indicator_sync")]


def test_sync_deletes_rows_written_by_old_mapping(client, db):
    """旧首命中逻辑把「肾小球滤过率(EPI-cr)」落成 CREA (ml/min, flag=high)。重跑必须清掉它。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "肾小球滤过率(EPI-cr)", 96, date(2026, 1, 15), unit="ml/min")
    db.add(BiomarkerObservation(
        user_id=user.id, code="CREA", domain="kidney", value=96, unit="ml/min",
        normalized_value=96, normalized_unit="ml/min", flag="high", abnormal=True, is_risk=True,
        observed_at=datetime(2026, 1, 15), source="indicator_sync",
    ))
    db.commit()

    r = sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("egfr", 96, "indicator_sync")]
    assert r["deleted"] == 1


def test_sync_removes_its_rows_duplicating_an_exam_measurement(client, db):
    """indicator_sync 与 exam 同一次测量 (同 code、同日、同值) 的重复行必须删, 不靠「第一个候选」碰运气。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    for source in ("indicator_sync", "manual", "indicator_sync"):
        db.add(BiomarkerObservation(
            user_id=user.id, code="GGT", domain="liver", value=72, unit="U/L",
            normalized_value=72, normalized_unit="U/L", flag="high", abnormal=True,
            observed_at=datetime(2026, 1, 15), source=source,
        ))
    db.commit()
    _seed_ind(db, user.id, "谷氨酰转肽酶", 72, date(2026, 1, 15))

    sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("GGT", 72, "manual")]


def test_sync_keeps_other_source_value_that_differs_from_exam(client, db):
    """同日另一来源 (不挂 exam 的报告) 的不同值不是重复, exam 落库后仍保留。"""
    from tests.conftest import create_authenticated_user
    from app.services.biomarker_service import ingest_exam
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "空腹血糖", 7.6, date(2026, 1, 15), unit="mmol/L")
    sync_indicators_to_biomarkers(db, user.id)
    item = _exam_item(db, user.id, "空腹血糖", 5.2, date(2026, 1, 15), unit="mmol/L")

    ingest_exam(db, item.exam)
    sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("glucose_fasting", 5.2, "exam"), ("glucose_fasting", 7.6, "indicator_sync")]


def test_sync_ingests_exam_and_rejects_relabelled_indicator(client, db):
    """确认导入建了 exam+items+indicators 却从未归一化 → sync 先兜底 exam 路径。

    exam 关联的指标行 name 可能是写入期归一化器改过的标签 (尿肌酐 →「肌酐」mg/g): 单位闸门拒收。
    """
    from tests.conftest import create_authenticated_user
    from app.models.family_health import MedicalIndicator
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    user, _ = create_authenticated_user(db)
    exam = MedicalExam(user_id=user.id, exam_date=date(2026, 2, 9), exam_type="comprehensive")
    db.add(exam)
    db.flush()
    for name, value, unit in [
        ("低密度脂蛋白-C", 3.1, "mmol/L"),
        ("极低密度脂蛋白-C", 0.7, "mmol/L"),
        ("谷氨酰转肽酶", 72, "U/L"),
        ("尿肌酐", 2.4, "mg/g"),
    ]:
        db.add(MedicalExamItem(exam_id=exam.id, item_name=name, value=value, unit=unit, source="manual"))
    db.add(MedicalIndicator(user_id=user.id, exam_id=exam.id, name="肌酐", item_code="CREA",
                            value=2.4, unit="mg/g", record_date=date(2026, 2, 9)))
    db.commit()

    sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("GGT", 72, "manual"), ("lipid_ldl", 3.1, "manual")]


def test_sync_keeps_exam_linked_indicator_that_no_exam_item_covers(client, db):
    """挂 exam 但 exam 里没有对应 item 的指标 (部分/历史数据) 照常同步, 已有的行不被删。"""
    from tests.conftest import create_authenticated_user
    from app.models.family_health import MedicalIndicator
    user, _ = create_authenticated_user(db)
    item = _exam_item(db, user.id, "谷丙转氨酶", 31, date(2026, 1, 15))
    db.add(MedicalIndicator(user_id=user.id, exam_id=item.exam_id, name="尿酸", value=520, unit="μmol/L",
                            record_date=date(2026, 1, 15)))
    db.add(BiomarkerObservation(
        user_id=user.id, code="UA", domain="metabolic", value=520, unit="μmol/L", normalized_value=520,
        normalized_unit="µmol/L", flag="high", abnormal=True, observed_at=datetime(2026, 1, 15),
        source="indicator_sync",
    ))
    db.commit()

    sync_indicators_to_biomarkers(db, user.id)

    assert _pairs(db, user.id) == [("ALT", 31, "exam"), ("UA", 520, "indicator_sync")]
