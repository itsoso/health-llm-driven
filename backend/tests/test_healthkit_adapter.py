"""HealthKit 多源汇入: 同 (user, date) 多源不互覆盖, upsert 幂等, 未知源不抛."""
from datetime import date

import pytest

from tests.conftest import create_authenticated_user


def _record(record_date: str, source: str, **kwargs):
    base = {"record_date": record_date, "data_source": source}
    base.update(kwargs)
    return base


def test_healthkit_import_three_sources_three_rows(client, db):
    """同一天 apple-watch + ringconn + oura 三条 → garmin_data 三行各占一 source."""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"records": [
        _record("2026-05-19", "apple-watch", steps=8000, resting_heart_rate=58),
        _record("2026-05-19", "ringconn", hrv=45.3, spo2_avg=97.1),
        _record("2026-05-19", "oura", sleep_score=82, total_sleep_minutes=420),
    ]}
    resp = client.post("/api/v1/devices/healthkit/import", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported_count"] == 3
    assert body["source_breakdown"] == {"apple-watch": 1, "ringconn": 1, "oura": 1}
    assert body["errors"] == []

    from app.models.daily_health import GarminData
    rows = db.query(GarminData).filter(
        GarminData.user_id == user.id,
        GarminData.record_date == date(2026, 5, 19),
    ).all()
    assert len(rows) == 3
    sources = {r.data_source for r in rows}
    assert sources == {"apple-watch", "ringconn", "oura"}

    aw = next(r for r in rows if r.data_source == "apple-watch")
    assert aw.steps == 8000 and aw.resting_heart_rate == 58
    rc = next(r for r in rows if r.data_source == "ringconn")
    assert rc.hrv == pytest.approx(45.3) and rc.spo2_avg == pytest.approx(97.1)
    ou = next(r for r in rows if r.data_source == "oura")
    assert ou.sleep_score == 82 and ou.total_sleep_duration == 420


def test_healthkit_import_idempotent_upsert(client, db):
    """重复 POST 同一批不重复插入 — (user_id, record_date, data_source) 唯一约束."""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"records": [
        _record("2026-05-18", "apple-watch", steps=7000),
    ]}

    r1 = client.post("/api/v1/devices/healthkit/import", json=payload, headers=headers)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/v1/devices/healthkit/import", json=payload, headers=headers)
    assert r2.status_code == 200, r2.text

    from app.models.daily_health import GarminData
    rows = db.query(GarminData).filter(
        GarminData.user_id == user.id,
        GarminData.record_date == date(2026, 5, 18),
    ).all()
    assert len(rows) == 1
    assert rows[0].steps == 7000
    assert rows[0].data_source == "apple-watch"

    # 同一日期再推第二个 source — 应新增一行,不覆盖 apple-watch
    payload2 = {"records": [_record("2026-05-18", "ringconn", hrv=42.0)]}
    r3 = client.post("/api/v1/devices/healthkit/import", json=payload2, headers=headers)
    assert r3.status_code == 200
    rows = db.query(GarminData).filter(
        GarminData.user_id == user.id,
        GarminData.record_date == date(2026, 5, 18),
    ).all()
    assert len(rows) == 2


def test_healthkit_import_unknown_source_falls_back(client, db):
    """白名单外 / sourceName 字典 miss 都落 unknown,不抛."""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"records": [
        # 显式 data_source 不在白名单 → unknown
        _record("2026-05-17", "weird-app", steps=5000),
        # 仅给 source_name,字典 miss → unknown
        {"record_date": "2026-05-16", "source_name": "com.unknown.healthapp", "steps": 4000},
        # source_name 命中字典
        {"record_date": "2026-05-15", "source_name": "com.ringconn.app", "hrv": 50.0},
    ]}
    resp = client.post("/api/v1/devices/healthkit/import", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported_count"] == 3
    assert body["source_breakdown"].get("unknown") == 2
    assert body["source_breakdown"].get("ringconn") == 1


def test_garmin_connect_display_name_maps_to_garmin_app():
    """回归: Garmin Connect 写 HealthKit 用显示名 'Connect'(非 bundle id、不含
    'Garmin')→ 之前落 unknown。两层 map 补 'Connect' → garmin-app。"""
    from app.services.device_adapters.healthkit import map_source_name_to_data_source
    assert map_source_name_to_data_source("Connect") == "garmin-app"
    # bundle id 路径仍可用, 未知源仍兜底 unknown
    assert map_source_name_to_data_source("com.garmin.connect.mobile") == "garmin-app"
    assert map_source_name_to_data_source("com.fitbit.FitbitMobile") == "unknown"


def test_healthkit_import_connect_source_lands_garmin_app(client, db):
    """端到端: source_name='Connect' 的 record → data_source='garmin-app'(不再 unknown)。"""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"records": [
        {"record_date": "2026-06-14", "source_name": "Connect", "steps": 5143},
    ]}
    resp = client.post("/api/v1/devices/healthkit/import", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["source_breakdown"].get("garmin-app") == 1


def test_healthkit_import_apple_xml_path_unaffected(client, db):
    """回归: AppleHealthAdapter (XML 文件导入) 与 HealthKitAdapter 共存,
    XML 路径走 source='apple', HealthKit 路径走 source='apple-watch' 等,各占独立行."""
    from app.services.device_adapters.apple import AppleHealthAdapter
    from app.services.device_adapters.base import NormalizedHealthData
    from app.services.device_adapters import DeviceManager

    user, token = create_authenticated_user(db)
    # AppleHealthAdapter XML 路径模拟: 直接构造 NormalizedHealthData(source="apple")
    DeviceManager._save_health_data(db, user.id, NormalizedHealthData(
        record_date=date(2026, 5, 14),
        source="apple",
        steps=6000,
    ))
    # HealthKit 路径
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/v1/devices/healthkit/import",
        json={"records": [_record("2026-05-14", "apple-watch", steps=8500)]},
        headers=headers,
    )

    from app.models.daily_health import GarminData
    rows = db.query(GarminData).filter(
        GarminData.user_id == user.id,
        GarminData.record_date == date(2026, 5, 14),
    ).all()
    assert len(rows) == 2
    by_src = {r.data_source: r for r in rows}
    assert by_src["apple"].steps == 6000
    assert by_src["apple-watch"].steps == 8500


def test_healthkit_import_ecg_persists_when_daily_fails(client, db):
    """端点级: 一条带 ECG (AtrialFibrillation) 但 record_date 不可解析 →
    日聚合解析失败但反映在 errors (kind='daily'), ECG 仍落库 (ecg_imported_count=1)。
    防回归: ECG 点事件不因日聚合失败被静默丢弃。

    注: record_date 在请求 schema 是必填 str, 完全缺失会被请求级 422 拦下 (见
    test_twin_builder 的 batch_save 直测覆盖该 contract 层); 端点级真实失败路径是
    '存在但格式错误的 record_date' (过 str 校验, _parse_date 返回 None → ValueError)。"""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"records": [{
        "record_date": "not-a-date",  # 过 str 校验但 _parse_date 解析失败 → 日聚合 ValueError
        "data_source": "apple-watch",
        "ecg_classification": "AtrialFibrillation",
        "ecg_recorded_at": "2026-06-10T08:15:00",
        "afib_event_count": 1,
    }]}
    resp = client.post("/api/v1/devices/healthkit/import", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["imported_count"] == 0
    assert body["ecg_imported_count"] == 1
    daily_errors = [e for e in body["errors"] if e["kind"] == "daily"]
    assert len(daily_errors) == 1
    assert not [e for e in body["errors"] if e["kind"] == "ecg"]

    from app.models.ecg_observation import EcgObservation
    rows = db.query(EcgObservation).filter(EcgObservation.user_id == user.id).all()
    assert len(rows) == 1
    assert rows[0].classification == "AtrialFibrillation"


def test_healthkit_import_fractional_int_fields_coerced_not_422(client, db):
    """avg() 聚合常把小数 float 喂给 int 字段(resting_heart_rate=52.5)。
    回归:整批 422 → 0 导入(用户实测 '已导入 0 天 1 条错误')。
    现在后端 before-validator 取整,坏值不再拖垮整批。"""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"records": [_record(
        "2026-06-09", "apple-watch",
        resting_heart_rate=52.5, steps=8123.0, total_sleep_minutes=420,
    )]}
    resp = client.post("/api/v1/devices/healthkit/import", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported_count"] == 1

    from app.models.daily_health import GarminData
    row = db.query(GarminData).filter(
        GarminData.user_id == user.id,
        GarminData.record_date == date(2026, 6, 9),
        GarminData.data_source == "apple-watch",
    ).one()
    assert row.resting_heart_rate == 52  # 52.5 → 取整
    assert row.steps == 8123
    assert row.total_sleep_duration == 420
