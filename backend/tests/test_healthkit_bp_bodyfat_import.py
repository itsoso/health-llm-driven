"""HealthKit 导入: 血压点事件 (幂等) + 体脂随体重.

血压是点事件 (一天多次, 和 ECG 同范式): 按 (user_id, measured_at) 去重幂等,
与日聚合并行独立 try。体脂随 weight_kg 落 weight_records。
契约字段 (给 mobile 段定死):
  - import record.blood_pressure_readings: [{systolic, diastolic, measured_at, source}]
  - 顶层日 record.weight_kg + record.body_fat_percentage
"""
from datetime import date

from tests.conftest import create_authenticated_user


def _post(client, token, records):
    return client.post(
        "/api/v1/devices/healthkit/import",
        json={"records": records},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_bp_point_events_persist_and_count(client, db):
    """一天多条血压点事件全部落库, blood_pressure_imported_count 反映数量。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-10",
        "data_source": "apple-watch",
        "blood_pressure_readings": [
            {"systolic": 122, "diastolic": 78, "measured_at": "2026-06-10T08:00:00", "source": "Omron"},
            {"systolic": 135, "diastolic": 85, "measured_at": "2026-06-10T20:00:00", "source": "Omron"},
        ],
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["blood_pressure_imported_count"] == 2
    assert body["errors"] == []

    from app.models.blood_pressure import BloodPressureRecord
    rows = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user.id,
    ).order_by(BloodPressureRecord.measured_at).all()
    assert len(rows) == 2
    assert rows[0].systolic == 122 and rows[0].diastolic == 78
    assert rows[0].record_date == date(2026, 6, 10)
    assert rows[1].systolic == 135 and rows[1].diastolic == 85


def test_bp_idempotent_same_measured_at(client, db):
    """同 measured_at 重导不增行 ((user_id, measured_at) 唯一 + service dedup)。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-11",
        "data_source": "apple-watch",
        "blood_pressure_readings": [
            {"systolic": 118, "diastolic": 76, "measured_at": "2026-06-11T09:30:00"},
        ],
    }]
    r1 = _post(client, token, records)
    assert r1.status_code == 200, r1.text
    assert r1.json()["blood_pressure_imported_count"] == 1

    # 重导同一条 — 已存在则跳过, 计数 0, 不增行
    r2 = _post(client, token, records)
    assert r2.status_code == 200, r2.text
    assert r2.json()["blood_pressure_imported_count"] == 0

    from app.models.blood_pressure import BloodPressureRecord
    rows = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user.id,
    ).all()
    assert len(rows) == 1


def test_bp_fractional_and_bad_values_tolerated(client, db):
    """坏值容错: float→int 取整; systolic 缺失/非数 → 该条丢弃, 不崩整批。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-12",
        "data_source": "apple-watch",
        "blood_pressure_readings": [
            # float 收缩压 → 取整
            {"systolic": 121.6, "diastolic": 79.2, "measured_at": "2026-06-12T07:00:00"},
            # diastolic 非数 → 请求级被 BPReadingIn 拒? diastolic 是 int, "abc" 会 422 整批。
            # 用合法 schema 但语义可丢的: measured_at 缺失 → service 丢弃 (无去重锚点)。
            {"systolic": 130, "diastolic": 80},
        ],
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 第一条落库 (取整), 第二条无 measured_at 被 service 丢弃 → 计数 1
    assert body["blood_pressure_imported_count"] == 1

    from app.models.blood_pressure import BloodPressureRecord
    rows = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user.id,
    ).all()
    assert len(rows) == 1
    assert rows[0].systolic == 122  # 121.6 → 122
    assert rows[0].diastolic == 79  # 79.2 → 79


def test_bp_persists_when_daily_aggregate_fails(client, db):
    """并行 try: 日聚合解析失败 (record_date 坏) 不影响血压落库。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "not-a-date",  # 过 str 校验但 _parse_date 失败 → 日聚合 ValueError
        "data_source": "apple-watch",
        "blood_pressure_readings": [
            {"systolic": 140, "diastolic": 90, "measured_at": "2026-06-13T10:00:00"},
        ],
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported_count"] == 0  # 日聚合失败
    assert body["blood_pressure_imported_count"] == 1  # BP 仍落库
    daily_errors = [e for e in body["errors"] if e["kind"] == "daily"]
    assert len(daily_errors) == 1
    assert not [e for e in body["errors"] if e["kind"] == "blood_pressure"]

    from app.models.blood_pressure import BloodPressureRecord
    rows = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user.id,
    ).all()
    assert len(rows) == 1
    assert rows[0].systolic == 140


def test_body_fat_rides_with_weight(client, db):
    """体脂随 weight_kg 落 weight_records。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-14",
        "data_source": "withings-app",
        "weight_kg": 70.4,
        "body_fat_percentage": 18.5,
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text

    from app.models.weight import WeightRecord
    row = db.query(WeightRecord).filter(
        WeightRecord.user_id == user.id,
        WeightRecord.record_date == date(2026, 6, 14),
    ).one()
    assert row.weight == 70.4
    assert row.body_fat_percentage == 18.5
    assert row.source == "withings-app"


def test_body_fat_without_weight_not_written(client, db):
    """只有 body_fat 没 weight → 无 NOT NULL 载体, 不写, 不报错。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-14",
        "data_source": "apple-watch",
        "body_fat_percentage": 20.0,
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text
    assert not [e for e in resp.json()["errors"] if e["kind"] == "body_composition"]

    from app.models.weight import WeightRecord
    rows = db.query(WeightRecord).filter(WeightRecord.user_id == user.id).all()
    assert len(rows) == 0


def test_body_composition_upsert_by_date(client, db):
    """同日重导体重 → upsert 不增行, 体脂更新。"""
    user, token = create_authenticated_user(db)
    _post(client, token, [{
        "record_date": "2026-06-15", "data_source": "apple-watch",
        "weight_kg": 71.0, "body_fat_percentage": 19.0,
    }])
    _post(client, token, [{
        "record_date": "2026-06-15", "data_source": "apple-watch",
        "weight_kg": 70.8, "body_fat_percentage": 18.8,
    }])

    from app.models.weight import WeightRecord
    rows = db.query(WeightRecord).filter(
        WeightRecord.user_id == user.id,
        WeightRecord.record_date == date(2026, 6, 15),
    ).all()
    assert len(rows) == 1
    assert rows[0].weight == 70.8
    assert rows[0].body_fat_percentage == 18.8


def test_response_shape_includes_bp_count(client, db):
    """response 始终含 blood_pressure_imported_count (即使无 BP 数据)。"""
    user, token = create_authenticated_user(db)
    resp = _post(client, token, [{"record_date": "2026-06-16", "data_source": "apple-watch", "steps": 5000}])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "blood_pressure_imported_count" in body
    assert body["blood_pressure_imported_count"] == 0
    assert body["imported_count"] == 1


def test_user_isolation_bp(client, db):
    """用户隔离: A 的血压不进 B 的查询。"""
    user_a, token_a = create_authenticated_user(db)
    user_b, token_b = create_authenticated_user(db)
    _post(client, token_a, [{
        "record_date": "2026-06-10", "data_source": "apple-watch",
        "blood_pressure_readings": [
            {"systolic": 125, "diastolic": 80, "measured_at": "2026-06-10T08:00:00"},
        ],
    }])

    from app.models.blood_pressure import BloodPressureRecord
    a_rows = db.query(BloodPressureRecord).filter(BloodPressureRecord.user_id == user_a.id).all()
    b_rows = db.query(BloodPressureRecord).filter(BloodPressureRecord.user_id == user_b.id).all()
    assert len(a_rows) == 1
    assert len(b_rows) == 0


def test_bp_import_requires_auth(client, db):
    """401: 无 token 拒绝。"""
    resp = client.post("/api/v1/devices/healthkit/import", json={"records": [{
        "record_date": "2026-06-10", "data_source": "apple-watch",
        "blood_pressure_readings": [
            {"systolic": 120, "diastolic": 80, "measured_at": "2026-06-10T08:00:00"},
        ],
    }]})
    assert resp.status_code in (401, 403), resp.text


def test_same_day_two_measured_at_two_rows(client, db):
    """点事件语义: 同日不同 measured_at → 两行 (不像日聚合互相覆盖)。"""
    user, token = create_authenticated_user(db)
    _post(client, token, [{
        "record_date": "2026-06-10", "data_source": "apple-watch",
        "blood_pressure_readings": [
            {"systolic": 120, "diastolic": 78, "measured_at": "2026-06-10T08:00:00"},
            {"systolic": 128, "diastolic": 82, "measured_at": "2026-06-10T08:00:01"},
        ],
    }])
    from app.models.blood_pressure import BloodPressureRecord
    rows = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user.id,
        BloodPressureRecord.record_date == date(2026, 6, 10),
    ).all()
    assert len(rows) == 2
