"""GPS 定位回归 — 2026-05-12 修复 G-loc bug.

历史: 用户 GPS 反查到"海淀"区级名, environment.py 用 city 字典查不到 → fallback
杭州坐标. 修法: 把 GPS 实测 lat/lon 存进 profile, environment 路由透传给 qweather
service 跳过字典. 同时 GPS 按钮触发时把 use_manual_location 关掉 (不然 detected_*
被忽略).
"""
from unittest.mock import patch, AsyncMock


def _patch_qweather_geoapi(name="海淀"):
    """Stub 和风 GeoAPI 反查 — 不要打外网."""
    fake_resp = type("R", (), {
        "json": lambda self: {
            "code": "200",
            "location": [{
                "name": name,
                "adm1": "北京市",
                "adm2": "北京",
                "country": "中国",
                "lat": "39.95607",
                "lon": "116.31032",
                "id": "101010200",
            }],
        },
        "raise_for_status": lambda self: None,
    })()

    class FakeAsyncClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw): return fake_resp

    return patch("httpx.AsyncClient", FakeAsyncClient)


def test_gps_location_persists_lat_lon(client, auth_user_and_headers, db):
    """POST /gps-location 必须把 user 提交的 lat/lon 存进 profile."""
    user, headers = auth_user_and_headers
    from app.config import settings
    # 强制让 handler 走真实路径 (qweather_api_host 必须有值)
    with patch.object(settings, "qweather_api_key", "test-key"), \
         patch.object(settings, "qweather_api_host", "test.qweatherapi.com"), \
         _patch_qweather_geoapi():
        resp = client.post(
            "/api/v1/profile/me/gps-location",
            json={"lat": 39.9561, "lon": 116.3103},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["location"]["lat"] == 39.9561
    assert body["location"]["lon"] == 116.3103

    from app.models.user_profile import UserProfile
    p = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    assert p is not None
    assert p.detected_lat == 39.9561
    assert p.detected_lon == 116.3103


def test_gps_location_disables_manual_mode(client, auth_user_and_headers, db):
    """用户在 manual mode 时点 GPS, 应自动关 manual (语义=用 GPS 自动定位).

    根因复盘: 用户报"GPS 设置后位置仍没改", 实际是 manual_city 优先级高于
    GPS detected_*, GPS 数据存了但被路由忽略.
    """
    user, headers = auth_user_and_headers
    from app.models.user_profile import UserProfile
    p = UserProfile(
        user_id=user.id,
        use_manual_location=True,
        manual_city="北京",
    )
    db.add(p)
    db.commit()

    from app.config import settings
    with patch.object(settings, "qweather_api_key", "test-key"), \
         patch.object(settings, "qweather_api_host", "test.qweatherapi.com"), \
         _patch_qweather_geoapi():
        resp = client.post(
            "/api/v1/profile/me/gps-location",
            json={"lat": 31.2304, "lon": 121.4737},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["use_manual_location"] is False

    db.refresh(p)
    assert p.use_manual_location is False
    assert p.detected_lat == 31.2304


def test_resolve_user_coords_returns_none_in_manual_mode(db, auth_user_and_headers):
    """environment._resolve_user_coords: manual 模式下不返回 GPS 坐标 (用户显式
    指定了 city, 应该走 city 字典, 不该跳到 detected_lat/lon)."""
    user, _ = auth_user_and_headers
    from app.models.user_profile import UserProfile
    from app.api.environment import _resolve_user_coords
    p = UserProfile(
        user_id=user.id,
        use_manual_location=True,
        manual_city="北京",
        detected_lat=39.95,  # 残留 — auto 模式才用
        detected_lon=116.31,
    )
    db.add(p)
    db.commit()

    assert _resolve_user_coords(db, user.id) == (None, None)


def test_resolve_user_coords_returns_lat_lon_in_auto_mode(db, auth_user_and_headers):
    """auto 模式下 detected_lat/lon 透传给 weather/AQ service, 跳过 city 字典."""
    user, _ = auth_user_and_headers
    from app.models.user_profile import UserProfile
    from app.api.environment import _resolve_user_coords
    p = UserProfile(
        user_id=user.id,
        use_manual_location=False,
        detected_city="海淀",
        detected_lat=39.9561,
        detected_lon=116.3103,
    )
    db.add(p)
    db.commit()

    lat, lon = _resolve_user_coords(db, user.id)
    assert lat == 39.9561
    assert lon == 116.3103


def test_resolve_user_coords_no_profile_returns_none(db, auth_user_and_headers):
    """没建过 profile 的用户 → (None, None) 让 caller fallback 城市字典."""
    user, _ = auth_user_and_headers
    from app.api.environment import _resolve_user_coords
    assert _resolve_user_coords(db, user.id) == (None, None)
