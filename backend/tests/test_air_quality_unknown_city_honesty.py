"""未知城市 → 不猜坐标、不返回"别处的真 AQI"。

生产实锤: `城市 '浙江' 不在空气质量坐标映射中,默认使用杭州坐标` ×10/24h。
老逻辑拿**猜的杭州坐标**去取**真的 AQI 数值**返回, 返回里没有任何标记说坐标是猜的
→ 调用方无从分辨。RhinitisSpecialist 拿 AQI 做症状-环境因果归因, 城市解析成省名时
那条归因就是编造的。

对照: 同文件的 `_get_default_aqi()` 一直老实返回 available=False —— 这个 codebase
知道怎么诚实降级, 就这条路径没做。sibling `weather_service._city_to_coords` 更是早在
2026-05-17 就做了同一处修正(返 None 不默认杭州), 本文件当时被漏掉了。
"""
import pytest


def _svc():
    from app.services.environment.air_quality_service import AirQualityService

    return AirQualityService()


# ───────────────────── 坐标解析层 ─────────────────────


def test_unknown_city_coords_returns_none_not_hangzhou():
    """未知城市 → None。老行为: 静默返回杭州 (30.2741, 120.1551)。"""
    assert _svc()._city_to_coords("浙江") is None


def test_known_city_coords_unchanged():
    assert _svc()._city_to_coords("杭州") == (30.2741, 120.1551)
    assert _svc()._city_to_coords("北京") == (39.9042, 116.4074)


# ───────────────────── get_air_quality 行为 ─────────────────────


@pytest.mark.asyncio
async def test_unknown_city_returns_unavailable_and_never_fetches(monkeypatch):
    """未知城市 → available=False, 且**根本不发请求**(不用猜的坐标去取真数值)。"""
    svc = _svc()
    svc._cache = {}

    called = []

    async def _boom_qweather(lat, lon):
        called.append(("qweather", lat, lon))
        raise AssertionError("不该用猜的坐标去取真 AQI")

    async def _boom_aqicn(city, lat, lon):
        called.append(("aqicn", lat, lon))
        raise AssertionError("不该用猜的坐标去取真 AQI")

    async def _boom_openmeteo(lat, lon):
        called.append(("openmeteo", lat, lon))
        raise AssertionError("不该用猜的坐标去取真 AQI")

    monkeypatch.setattr(svc, "_get_qweather_aqi", _boom_qweather)
    monkeypatch.setattr(svc, "_get_aqicn_aqi", _boom_aqicn)
    monkeypatch.setattr(svc, "_get_openmeteo_aqi", _boom_openmeteo)

    out = await svc.get_air_quality(city="浙江")

    assert out["available"] is False
    assert not called, f"未知城市不该发任何上游请求, 实际: {called}"
    assert "浙江" in out.get("error", "")


@pytest.mark.asyncio
async def test_unknown_city_does_not_return_hangzhou_real_reading(monkeypatch):
    """核心诚实性断言: 不返回"用杭州坐标算出来的真数值"当作用户所在地的空气质量。"""
    svc = _svc()
    svc._cache = {}

    async def _hangzhou_real(lat, lon):
        # 若代码仍猜杭州坐标, 这里会返回一个"真实但属于别处"的 AQI
        return {"available": True, "aqi": 137, "aqi_level": "unhealthy", "source": "openmeteo"}

    monkeypatch.setattr(svc, "_get_openmeteo_aqi", _hangzhou_real)
    monkeypatch.setattr(svc, "_get_aqicn_aqi", _hangzhou_real)

    out = await svc.get_air_quality(city="浙江")

    assert out["available"] is False
    assert out["aqi"] != 137, "返回了别处坐标算出的真 AQI —— 这正是要修的编造"


@pytest.mark.asyncio
async def test_known_city_behavior_unchanged(monkeypatch):
    """已知城市 → 行为不变(正常解析坐标并返回真数据)。"""
    svc = _svc()
    svc._cache = {}
    seen = {}

    async def _fake_aqicn(city, lat, lon):
        seen["coords"] = (lat, lon)
        return {"available": True, "aqi": 42, "aqi_level": "good", "source": "aqicn"}

    monkeypatch.setattr(svc, "_get_aqicn_aqi", _fake_aqicn)

    out = await svc.get_air_quality(city="杭州")

    assert out["available"] is True
    assert out["aqi"] == 42
    assert seen["coords"] == (30.2741, 120.1551)


@pytest.mark.asyncio
async def test_explicit_coords_still_work_without_city(monkeypatch):
    """显式传 lat/lon → 不走城市映射, 照常取数(GPS 流的正确路径)。"""
    svc = _svc()
    svc._cache = {}

    async def _fake_aqicn(city, lat, lon):
        return {"available": True, "aqi": 31, "aqi_level": "good", "source": "aqicn"}

    monkeypatch.setattr(svc, "_get_aqicn_aqi", _fake_aqicn)

    out = await svc.get_air_quality(city=None, lat=39.9, lon=116.4)

    assert out["available"] is True
    assert out["aqi"] == 31


# ───────────────── twin 侧: 占位常量不得当真写进 Twin ─────────────────


def test_twin_environment_ignores_unavailable_aqi(db, monkeypatch):
    """available=False 的占位 aqi(=50 "良") 不得写进 Twin。

    RhinitisSpecialist 读 twin.environment.aqi 做症状-环境归因; 写进去就是把
    `_get_default_aqi()` 的常量当成实测值讲给用户。宁可没有, 不可编造。
    """
    from app.models.user import User
    from app.twin.builder import _fill_environment
    from app.twin.schema import HealthTwin, TwinMeta
    from datetime import datetime, UTC

    u = User(username="aqt", email="aqt@test.com", hashed_password="x", name="a")
    db.add(u)
    db.commit()
    db.refresh(u)

    from app.services import daily_recommendation as dr_mod
    from app.utils.redis_cache import RedisCache

    monkeypatch.setattr(RedisCache, "get", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(RedisCache, "set", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        dr_mod.DailyRecommendationService,
        "get_environment_data_sync",
        lambda self, db_, uid: {
            "city": "浙江",
            "weather": {"temperature": 21.0, "humidity": 55},
            "air_quality": {"available": False, "aqi": 50, "aqi_level": "good", "pm25": 0},
        },
    )

    twin = HealthTwin(meta=TwinMeta(user_id=u.id, generated_at=datetime.now(UTC)))
    _fill_environment(db, u.id, twin, set())

    assert twin.environment.aqi is None, "占位 aqi=50 被当成实测值写进了 Twin"
    assert twin.environment.outdoor_exercise_suitability is None
    # 真实的天气数据不受影响 (只丢 aqi, 不误伤同一 payload 里的其他字段)
    assert twin.environment.temperature_c == 21.0


def test_twin_environment_keeps_available_aqi(db, monkeypatch):
    """available=True → 照常写入(没有过度收紧, 不误杀真实 AQI)。"""
    from app.models.user import User
    from app.twin.builder import _fill_environment
    from app.twin.schema import HealthTwin, TwinMeta
    from datetime import datetime, UTC

    u = User(username="aqt2", email="aqt2@test.com", hashed_password="x", name="a")
    db.add(u)
    db.commit()
    db.refresh(u)

    from app.services import daily_recommendation as dr_mod
    from app.utils.redis_cache import RedisCache

    monkeypatch.setattr(RedisCache, "get", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(RedisCache, "set", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        dr_mod.DailyRecommendationService,
        "get_environment_data_sync",
        lambda self, db_, uid: {
            "city": "北京",
            "weather": {"temperature": 18.0},
            "air_quality": {"available": True, "aqi": 128, "aqi_level": "unhealthy", "pm25": 60.0},
        },
    )

    twin = HealthTwin(meta=TwinMeta(user_id=u.id, generated_at=datetime.now(UTC)))
    _fill_environment(db, u.id, twin, set())

    assert twin.environment.aqi == 128
    assert twin.environment.pm25 == 60.0


def test_twin_environment_keeps_aqi_when_available_key_absent(db, monkeypatch):
    """shape 里没有 available 键 → 不丢弃(只在**显式** False 时丢, 避免误杀)。"""
    from app.models.user import User
    from app.twin.builder import _fill_environment
    from app.twin.schema import HealthTwin, TwinMeta
    from datetime import datetime, UTC

    u = User(username="aqt3", email="aqt3@test.com", hashed_password="x", name="a")
    db.add(u)
    db.commit()
    db.refresh(u)

    from app.services import daily_recommendation as dr_mod
    from app.utils.redis_cache import RedisCache

    monkeypatch.setattr(RedisCache, "get", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(RedisCache, "set", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        dr_mod.DailyRecommendationService,
        "get_environment_data_sync",
        lambda self, db_, uid: {
            "city": "北京",
            "air_quality": {"aqi": 77, "aqi_level": "moderate"},
        },
    )

    twin = HealthTwin(meta=TwinMeta(user_id=u.id, generated_at=datetime.now(UTC)))
    _fill_environment(db, u.id, twin, set())

    assert twin.environment.aqi == 77
