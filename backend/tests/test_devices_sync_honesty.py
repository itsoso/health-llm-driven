"""设备同步"诚实性"回归: 整批失败绝不谎报成功 (仓库硬规则 #1 不假装成功)。

覆盖 devices.py 三个出口:
  1. POST /devices/healthkit/import — 整批导入失败 → DataConnection 置 degraded + 保留
     真实 sync_error (不置 active / 不抹错误 / 不刷新 last_success_at)。
  2. POST /devices/apple/import — synced=0 → success=False, message 以"导入失败"开头。
  3. POST /devices/sync-all — 有设备失败 → 只把成功设备计入, message 反映 N/M。
"""
from datetime import date

import pytest

from tests.conftest import create_authenticated_user, grant_healthkit_consent


def _post_healthkit(client, token, records):
    return client.post(
        "/api/v1/devices/healthkit/import",
        json={"records": records},
        headers={"Authorization": f"Bearer {token}"},
    )


# ── Fix 1: HealthKit 整批导入失败 → 连接状态诚实降级 ────────────────────────────

def test_healthkit_whole_batch_fail_marks_connection_degraded(client, db):
    """所有记录导入失败 (record_date 坏, 无点事件落库) → 连接不谎报成功。

    imported_count/ecg/bp/spo2 全 0 且 errors 非空时, 必须 record_sync_result(success=False):
    连接置 degraded、保留真实 sync_error、不刷新 last_success_at。
    """
    user, token = create_authenticated_user(db)
    connection = grant_healthkit_consent(db, user)

    records = [
        {"record_date": "not-a-date", "data_source": "apple-watch"},
        {"record_date": "still-bad", "data_source": "apple-watch"},
    ]
    resp = _post_healthkit(client, token, records)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 一条都没落库
    assert body["imported_count"] == 0
    assert body["ecg_imported_count"] == 0
    assert body["blood_pressure_imported_count"] == 0
    assert body["spo2_sample_imported_count"] == 0
    assert len(body["errors"]) == 2

    # 连接状态必须诚实: degraded + 真实错误, 不谎报成功
    db.refresh(connection)
    assert connection.connection_status == "degraded"
    assert connection.last_success_at is None
    assert connection.sync_error is not None
    assert "全部导入失败" in connection.sync_error
    assert "成功" not in connection.sync_error.split("全部导入失败")[0]
    # §5 脱敏: 持久化的 sync_error 只含 kind/异常类名, 不回灌原始输入/健康值。
    # 坏 record_date 'not-a-date' 会出现在异常 message body 里 —— 脱敏后必须被剥掉。
    assert "not-a-date" not in connection.sync_error
    assert "/" in connection.sync_error.split("全部导入失败:")[-1]  # kind/reason 形态


def test_healthkit_partial_success_marks_connection_active(client, db):
    """部分记录落库 (imported_any=True) → 连接置 active, 即使有个别失败项。"""
    user, token = create_authenticated_user(db)
    connection = grant_healthkit_consent(db, user)

    records = [
        {"record_date": "2026-06-10", "data_source": "apple-watch", "steps": 5000},
        {"record_date": "not-a-date", "data_source": "apple-watch"},
    ]
    resp = _post_healthkit(client, token, records)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported_count"] == 1  # 第一条落库
    assert len(body["errors"]) == 1     # 第二条失败

    db.refresh(connection)
    assert connection.connection_status == "active"
    assert connection.last_success_at is not None
    assert connection.sync_error is None


def test_healthkit_empty_batch_not_marked_failed(client, db):
    """空批 (无记录无错误) 不算失败 → 连接保持 active。"""
    user, token = create_authenticated_user(db)
    connection = grant_healthkit_consent(db, user)

    resp = _post_healthkit(client, token, [])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported_count"] == 0
    assert body["errors"] == []

    db.refresh(connection)
    assert connection.connection_status == "active"
    assert connection.sync_error is None


# ── Fix 2: Apple Health XML 导入 synced=0 → success=False ───────────────────────

def _upload_apple(client, token):
    return client.post(
        "/api/v1/devices/apple/import",
        files={"file": ("export.xml", b"<HealthData/>", "text/xml")},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_apple_import_all_days_fail_returns_failure(client, db, monkeypatch):
    """每天 fetch 都抛 → synced=0, failed=N → success=False, message 不以"导入成功"开头。"""
    user, token = create_authenticated_user(db)

    from app.services.device_adapters.apple import AppleHealthAdapter
    from app.services.device_adapters.manager import DeviceManager

    parsed = {"2026-06-10": {"steps": 100}, "2026-06-11": {"steps": 200}}
    monkeypatch.setattr(AppleHealthAdapter, "parse_health_xml", staticmethod(lambda xml: parsed))

    async def _boom(self, target_date):
        raise RuntimeError("save failed")

    monkeypatch.setattr(AppleHealthAdapter, "fetch_daily_data", _boom)
    monkeypatch.setattr(DeviceManager, "_save_health_data", staticmethod(lambda *a, **k: None))

    resp = _upload_apple(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["synced_days"] == 0
    assert body["failed_days"] == 2
    assert body["message"].startswith("导入失败")
    assert "导入成功" not in body["message"]


def test_apple_import_partial_success_reports_counts(client, db, monkeypatch):
    """一天成功一天失败 → synced=1, failed=1 → success=True, message 以"导入成功"开头。"""
    user, token = create_authenticated_user(db)

    from app.services.device_adapters.apple import AppleHealthAdapter
    from app.services.device_adapters.manager import DeviceManager

    parsed = {"2026-06-10": {"steps": 100}, "2026-06-11": {"steps": 200}}
    monkeypatch.setattr(AppleHealthAdapter, "parse_health_xml", staticmethod(lambda xml: parsed))

    async def _one_ok(self, target_date):
        if target_date == date(2026, 6, 10):
            return {"steps": 100}  # truthy → 落库计数
        raise RuntimeError("save failed")

    monkeypatch.setattr(AppleHealthAdapter, "fetch_daily_data", _one_ok)
    monkeypatch.setattr(DeviceManager, "_save_health_data", staticmethod(lambda *a, **k: None))

    resp = _upload_apple(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["synced_days"] == 1
    assert body["failed_days"] == 1
    assert body["message"].startswith("导入成功")


# ── Fix 3: /devices/sync-all 只把成功设备计入"已同步" ───────────────────────────

def test_sync_all_counts_only_successful_devices(client, db, monkeypatch):
    """3 设备 1 个失败 → success=True (仍有成功) 但 message 反映 2/3, 不谎报"已同步 3 个"。"""
    user, token = create_authenticated_user(db)

    from app.services.device_adapters.manager import DeviceManager

    async def _fake_sync_all(db_, user_id, days):
        return [
            {"device": "garmin", "success": True, "synced_days": 7, "message": "ok"},
            {"device": "withings", "success": False, "message": "鉴权失败"},
            {"device": "apple", "success": True, "synced_days": 3, "message": "ok"},
        ]

    monkeypatch.setattr(DeviceManager, "sync_all_devices", classmethod(
        lambda cls, db_, user_id, days=7: _fake_sync_all(db_, user_id, days)
    ))

    resp = client.post(
        "/api/v1/devices/sync-all",
        json={"days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert "2/3" in body["message"]
    assert "已同步 3 个设备" not in body["message"]
    assert "withings" in body["message"]  # 失败设备被点名


def test_sync_all_all_devices_fail_reports_zero_success(client, db, monkeypatch):
    """所有设备失败 → success=False, message 反映 0/N。"""
    user, token = create_authenticated_user(db)

    from app.services.device_adapters.manager import DeviceManager

    async def _fake_sync_all(db_, user_id, days):
        return [
            {"device": "garmin", "success": False, "message": "鉴权失败"},
            {"device": "withings", "success": False, "message": "鉴权失败"},
        ]

    monkeypatch.setattr(DeviceManager, "sync_all_devices", classmethod(
        lambda cls, db_, user_id, days=7: _fake_sync_all(db_, user_id, days)
    ))

    resp = client.post(
        "/api/v1/devices/sync-all",
        json={"days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "0/2" in body["message"]


def test_sync_all_no_devices_is_success(client, db, monkeypatch):
    """无绑定设备 (空 results) → success=True (没有失败可言), message 0/0。"""
    user, token = create_authenticated_user(db)

    from app.services.device_adapters.manager import DeviceManager

    async def _fake_sync_all(db_, user_id, days):
        return []

    monkeypatch.setattr(DeviceManager, "sync_all_devices", classmethod(
        lambda cls, db_, user_id, days=7: _fake_sync_all(db_, user_id, days)
    ))

    resp = client.post(
        "/api/v1/devices/sync-all",
        json={"days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert "0/0" in body["message"]
