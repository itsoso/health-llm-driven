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


# ─── /me/effective-location — 单一事实之主端点 ───

def test_effective_location_unknown_when_empty(client, auth_user_and_headers, db):
    """没任何位置数据 → source='unknown', city=None, lat/lon=None."""
    user, headers = auth_user_and_headers
    resp = client.get("/api/v1/profile/me/effective-location", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["city"] is None
    assert body["source"] == "unknown"
    assert body["lat"] is None and body["lon"] is None


def test_effective_location_manual_wins(client, auth_user_and_headers, db):
    """use_manual_location=True 且 manual_city 非空 → source='manual', 暴露 manual_city."""
    user, headers = auth_user_and_headers
    from app.models.user_profile import UserProfile
    p = UserProfile(
        user_id=user.id, use_manual_location=True, manual_city="北京",
        detected_city="海淀", detected_region="北京市",
        detected_lat=39.95, detected_lon=116.31,
    )
    db.add(p)
    db.commit()
    resp = client.get("/api/v1/profile/me/effective-location", headers=headers)
    body = resp.json()
    assert body["city"] == "北京"
    assert body["source"] == "manual"
    # manual 模式不暴露坐标
    assert body["lat"] is None and body["lon"] is None


def test_effective_location_gps_strips_admin_suffix(client, auth_user_and_headers, db):
    """非 manual + 有 GPS → source='gps', city 从 region 去市/省 (而不是 detected_city/区名)."""
    user, headers = auth_user_and_headers
    from app.models.user_profile import UserProfile
    p = UserProfile(
        user_id=user.id, use_manual_location=False,
        detected_city="余杭",   # 区/县名
        detected_region="杭州市",  # 城市级
        detected_lat=30.27, detected_lon=120.15,
    )
    db.add(p)
    db.commit()
    resp = client.get("/api/v1/profile/me/effective-location", headers=headers)
    body = resp.json()
    assert body["city"] == "杭州"   # 不是 "余杭"
    assert body["source"] == "gps"
    assert body["lat"] == 30.27 and body["lon"] == 120.15


def test_effective_location_ip_only_when_no_lat_lon(client, auth_user_and_headers, db):
    """有 detected_city 但没坐标 → source='ip'."""
    user, headers = auth_user_and_headers
    from app.models.user_profile import UserProfile
    p = UserProfile(
        user_id=user.id, use_manual_location=False,
        detected_city="海淀", detected_region="北京市",
    )
    db.add(p)
    db.commit()
    resp = client.get("/api/v1/profile/me/effective-location", headers=headers)
    body = resp.json()
    assert body["city"] == "北京"
    assert body["source"] == "ip"


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


def test_resolve_location_returns_no_coords_in_manual_mode(db, auth_user_and_headers):
    """environment._resolve_location: manual 模式下 lat/lon=None (用户显式指定了 city,
    应走 city 字典, 不跳到 detected_lat/lon 残留)."""
    user, _ = auth_user_and_headers
    from app.models.user_profile import UserProfile
    from app.api.environment import _resolve_location
    p = UserProfile(
        user_id=user.id,
        use_manual_location=True,
        manual_city="北京",
        detected_lat=39.95,  # 残留 — auto 模式才用
        detected_lon=116.31,
    )
    db.add(p)
    db.commit()

    lat, lon, city = _resolve_location(db, user.id)
    assert lat is None and lon is None
    assert city == "北京"


def test_resolve_location_returns_lat_lon_in_auto_mode(db, auth_user_and_headers):
    """auto 模式 + detected_lat/lon → 返回坐标, 透传给 weather/AQ service, 跳过 city 字典."""
    user, _ = auth_user_and_headers
    from app.models.user_profile import UserProfile
    from app.api.environment import _resolve_location
    p = UserProfile(
        user_id=user.id,
        use_manual_location=False,
        detected_city="海淀",
        detected_region="北京市",
        detected_lat=39.9561,
        detected_lon=116.3103,
    )
    db.add(p)
    db.commit()

    lat, lon, city = _resolve_location(db, user.id)
    assert lat == 39.9561
    assert lon == 116.3103
    # city 仍返回, caller 决定优先用 lat/lon
    assert city == "北京"


def test_resolve_location_no_profile_returns_none(db, auth_user_and_headers):
    """没建过 profile 的用户 → 全 None."""
    user, _ = auth_user_and_headers
    from app.api.environment import _resolve_location
    lat, lon, city = _resolve_location(db, user.id)
    assert lat is None and lon is None and city is None


# ─── B4: GPS endpoint 接客户端 hint + qweather 软失败 ───

def test_gps_location_uses_client_city_hint_skips_qweather(client, auth_user_and_headers, db):
    """客户端传 city/region → backend 跳过 qweather, 直接信任写入. 去 qweather 依赖."""
    user, headers = auth_user_and_headers

    # 关键: 即使 qweather 完全没配, 客户端有 city hint 也能跑.
    from app.config import settings
    qweather_called = {"hit": False}

    class _SpyClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw):
            qweather_called["hit"] = True
            raise AssertionError("不该调 qweather: 客户端已传 city")

    with patch.object(settings, "qweather_api_key", ""), \
         patch.object(settings, "qweather_api_host", ""), \
         patch("httpx.AsyncClient", _SpyClient):
        resp = client.post(
            "/api/v1/profile/me/gps-location",
            json={"lat": 39.9561, "lon": 116.3103, "city": "北京", "region": "北京市", "country": "中国"},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["location"]["city"] == "北京"
    assert body["geocode_source"] == "client"
    assert qweather_called["hit"] is False

    from app.models.user_profile import UserProfile
    p = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    assert p.detected_city == "北京"
    assert p.detected_source == "gps"


def test_gps_location_qweather_unconfigured_no_hint_still_saves_coords(client, auth_user_and_headers, db):
    """qweather 没配 + 客户端没 city → 不再 503, 200 返回 city=null, lat/lon 仍写入.

    L1: resolver 会标 source='gps', environment.py 优先读 lat/lon, 天气/AQ 仍能正常出.
    """
    user, headers = auth_user_and_headers
    from app.config import settings
    with patch.object(settings, "qweather_api_key", ""), \
         patch.object(settings, "qweather_api_host", ""):
        resp = client.post(
            "/api/v1/profile/me/gps-location",
            json={"lat": 39.9561, "lon": 116.3103},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["location"]["city"] is None
    assert body["location"]["lat"] == 39.9561
    assert body["geocode_source"] == "none"

    from app.models.user_profile import UserProfile
    p = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    assert p.detected_lat == 39.9561
    assert p.detected_lon == 116.3103
    assert p.detected_source == "gps"


def test_gps_location_qweather_network_failure_returns_200_with_coords(client, auth_user_and_headers, db):
    """qweather 配了但请求炸了 → 不再 502, 200 返回 city=null, lat/lon 仍存."""
    user, headers = auth_user_and_headers
    from app.config import settings

    class _FailingClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw):
            raise ConnectionError("qweather 死了")

    with patch.object(settings, "qweather_api_key", "test-key"), \
         patch.object(settings, "qweather_api_host", "test.qweatherapi.com"), \
         patch("httpx.AsyncClient", _FailingClient):
        resp = client.post(
            "/api/v1/profile/me/gps-location",
            json={"lat": 39.9561, "lon": 116.3103},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["location"]["city"] is None
    assert body["location"]["lat"] == 39.9561

    from app.models.user_profile import UserProfile
    p = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    assert p.detected_lat == 39.9561
    assert p.detected_source == "gps"


def test_gps_location_rejects_english_city_in_china_falls_back_to_qweather(client, auth_user_and_headers, db):
    """iOS CLGeocoder 在 PRC 偶尔返英文 city ('Beijing' + country='中国') →
    backend 丢弃 hint, 走 qweather 兜底.
    """
    user, headers = auth_user_and_headers
    from app.config import settings
    with patch.object(settings, "qweather_api_key", "test-key"), \
         patch.object(settings, "qweather_api_host", "test.qweatherapi.com"), \
         _patch_qweather_geoapi(name="海淀"):
        resp = client.post(
            "/api/v1/profile/me/gps-location",
            json={
                "lat": 39.9561, "lon": 116.3103,
                "city": "Beijing", "region": "Beijing Shi", "country": "中国",
            },
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    # qweather 返"海淀" 兜底 — 英文 hint 被丢弃
    assert body["location"]["city"] == "海淀"
    assert body["geocode_source"] == "qweather"


def test_gps_location_keeps_english_city_outside_china(client, auth_user_and_headers, db):
    """境外 (country='United States') 的英文 city 不丢弃."""
    user, headers = auth_user_and_headers
    from app.config import settings
    with patch.object(settings, "qweather_api_key", ""), \
         patch.object(settings, "qweather_api_host", ""):
        resp = client.post(
            "/api/v1/profile/me/gps-location",
            json={
                "lat": 37.7749, "lon": -122.4194,
                "city": "San Francisco", "region": "California", "country": "United States",
            },
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["location"]["city"] == "San Francisco"
    assert body["geocode_source"] == "client"
