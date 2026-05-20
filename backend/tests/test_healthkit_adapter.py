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
