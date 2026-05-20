"""B6: 杭州静默 fallback 已干掉 — _city_to_coords 未知城市返 None.

历史: city dict 不含的城市 (e.g. 'Atlantis' / '海淀') 都默认杭州 (30.27, 120.16).
用户在北京海淀走 IP geo 但 detected_city='海淀' 不在 dict, 拿到的天气是杭州的.

修法: 返 None, callers (get_current_weather / get_weather_forecast) 早返 unavailable.
正确路径是 GPS 反查存 detected_lat/lon, environment.py 优先用坐标透传, 根本不走这里.
"""
from app.services.environment.weather_service import WeatherService


def test_city_to_coords_known_city_returns_coords():
    """字典里的城市返坐标."""
    svc = WeatherService()
    coords = svc._city_to_coords("北京")
    assert coords is not None
    assert len(coords) == 2
    lat, lon = coords
    assert 30 < lat < 45 and 100 < lon < 130


def test_city_to_coords_unknown_city_returns_none():
    """字典外的城市返 None — 不再默认杭州."""
    svc = WeatherService()
    assert svc._city_to_coords("Atlantis") is None
    assert svc._city_to_coords("海淀") is None  # 老坑: 区名不在城市 dict


def test_city_to_coords_none_input_returns_none():
    svc = WeatherService()
    assert svc._city_to_coords("") is None


def test_geoapi_host_stays_public_when_custom_host_set():
    """客户专属 host (`*.re.qweatherapi.com`) 只代理 /v7 不代理 /v2/city/lookup.
    历史: __init__ 把 GeoAPI URL 也改到客户 host → city 查 ID 全 404 → weather/now
    用脏 location 串失败, 日志刷 'API 返回错误: None'. GeoAPI 必须永远公用 host."""
    from app.services.environment.weather_service import WeatherService

    svc = WeatherService(api_key="test", api_type="premium", api_host="abc.re.qweatherapi.com")
    assert svc.QWEATHER_BASE_URL == "https://abc.re.qweatherapi.com/v7"
    assert svc.QWEATHER_GEO_URL == "https://geoapi.qweather.com/v2"


def test_qweather_error_message_handles_both_shapes():
    """老 shape `{code: ...}` 和新 shape `{error: {title, status, detail}}` 都要给可读消息.
    回归: 之前 `data.get('code')` 在新 shape 下返 None → 日志 'API 返回错误: None'."""
    from app.services.environment.weather_service import _qweather_error_message

    legacy = _qweather_error_message({"code": "404"}, "120,30")
    assert "404" in legacy and "120,30" in legacy

    modern = _qweather_error_message(
        {"error": {"status": 403, "title": "Invalid Host", "detail": "unauthorized API host"}},
        "120,30",
    )
    assert "Invalid Host" in modern
    assert "403" in modern
    assert "120,30" in modern

    empty = _qweather_error_message({}, "X")
    assert "X" in empty
