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
