"""location_resolver — Phase A.1 单元测试 (single source of truth for current city)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.location_resolver import resolve_effective_location, _strip_admin_suffix


class TestStripAdminSuffix:
    def test_strip_shi(self):
        assert _strip_admin_suffix("北京市") == "北京"

    def test_strip_sheng(self):
        assert _strip_admin_suffix("浙江省") == "浙江"

    def test_no_suffix(self):
        assert _strip_admin_suffix("杭州") == "杭州"

    def test_none(self):
        assert _strip_admin_suffix(None) is None

    def test_empty(self):
        assert _strip_admin_suffix("") is None

    def test_whitespace(self):
        assert _strip_admin_suffix("  上海市  ") == "上海"


class TestResolveEffective:
    def _profile(self, **kwargs):
        defaults = dict(
            use_manual_location=False,
            manual_city=None,
            detected_city=None,
            detected_region=None,
            detected_lat=None,
            detected_lon=None,
            location_updated_at=None,
            updated_at=None,
            city=None,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_none_profile(self):
        result = resolve_effective_location(None)
        assert result["city"] is None
        assert result["source"] == "unknown"
        assert result["lat"] is None and result["lon"] is None

    def test_manual_wins_when_flag_on(self):
        p = self._profile(use_manual_location=True, manual_city="北京",
                          detected_city="海淀", detected_region="北京市",
                          detected_lat=39.9, detected_lon=116.4)
        result = resolve_effective_location(p)
        assert result["city"] == "北京"
        assert result["source"] == "manual"
        # manual 模式不暴露坐标 (manual city 没对应 GPS, 暴露反误导)
        assert result["lat"] is None and result["lon"] is None

    def test_manual_flag_on_but_empty_falls_through(self):
        """flag=True 但 manual_city 空 → 不当作 manual, 走 detected."""
        p = self._profile(use_manual_location=True, manual_city="  ",
                          detected_region="杭州市")
        result = resolve_effective_location(p)
        assert result["city"] == "杭州"
        assert result["source"] == "ip"

    def test_detected_region_strips_shi(self):
        """non-manual 模式优先 region 去市/省 (qweather adm1 = 城市级)."""
        p = self._profile(detected_city="海淀", detected_region="北京市")
        result = resolve_effective_location(p)
        assert result["city"] == "北京"  # 不是 "海淀"
        assert result["source"] == "ip"

    def test_falls_back_to_detected_city_when_no_region(self):
        p = self._profile(detected_city="海淀")
        result = resolve_effective_location(p)
        assert result["city"] == "海淀"
        assert result["source"] == "ip"

    def test_gps_source_when_lat_lon_present(self):
        p = self._profile(detected_city="余杭", detected_region="杭州市",
                          detected_lat=30.27, detected_lon=120.15)
        result = resolve_effective_location(p)
        assert result["city"] == "杭州"
        assert result["source"] == "gps"
        assert result["lat"] == 30.27 and result["lon"] == 120.15

    def test_unknown_when_all_empty(self):
        p = self._profile()
        result = resolve_effective_location(p)
        assert result["city"] is None
        assert result["source"] == "unknown"
        assert result["lat"] is None and result["lon"] is None

    def test_use_manual_false_ignores_manual_city(self):
        """flag=False 即使有 manual_city 也忽略 (历史残留场景)."""
        p = self._profile(use_manual_location=False, manual_city="北京",
                          detected_region="杭州市", detected_lat=30.27, detected_lon=120.15)
        result = resolve_effective_location(p)
        assert result["city"] == "杭州"
        assert result["source"] == "gps"

    def test_stale_minutes_computed(self):
        now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
        p = self._profile(
            detected_region="杭州市",
            detected_lat=30.27, detected_lon=120.15,
            location_updated_at=now - timedelta(minutes=15),
        )
        result = resolve_effective_location(p, now=now)
        assert result["stale_minutes"] == 15

    def test_stale_minutes_none_when_no_timestamp(self):
        p = self._profile(detected_region="杭州市")
        result = resolve_effective_location(p)
        assert result["stale_minutes"] is None

    def test_updated_at_iso_format(self):
        now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
        p = self._profile(
            detected_region="杭州市", location_updated_at=now,
        )
        result = resolve_effective_location(p, now=now)
        assert result["updated_at"] == "2026-05-16T12:00:00+00:00"


class TestStoredSourceTrust:
    """B3: resolver 优先 stored detected_source, legacy 启发式只兜底."""
    def _profile(self, **kwargs):
        defaults = dict(
            use_manual_location=False, manual_city=None,
            detected_city=None, detected_region=None,
            detected_lat=None, detected_lon=None,
            detected_source=None,
            location_updated_at=None, updated_at=None, city=None,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_stored_gps_wins_even_when_lat_lon_missing(self):
        """stored='gps' 即使没 lat/lon (旧数据) 也算 gps."""
        p = self._profile(detected_city="北京", detected_source="gps")
        assert resolve_effective_location(p)["source"] == "gps"

    def test_stored_ip_wins_even_when_lat_lon_present(self):
        """IP 后端如果偶尔写了 lat (ip-api 返了), 不该被启发式当成 GPS — 信任 stored."""
        p = self._profile(
            detected_city="北京", detected_lat=39.9, detected_lon=116.4,
            detected_source="ip",
        )
        assert resolve_effective_location(p)["source"] == "ip"

    def test_legacy_null_source_falls_back_to_lat_lon_heuristic(self):
        """detected_source=NULL (旧行) → 有 lat/lon 时按启发式当 gps."""
        p = self._profile(
            detected_city="北京", detected_lat=39.9, detected_lon=116.4,
            detected_source=None,
        )
        assert resolve_effective_location(p)["source"] == "gps"

    def test_legacy_null_source_no_lat_lon_falls_back_to_ip(self):
        p = self._profile(detected_city="北京", detected_source=None)
        assert resolve_effective_location(p)["source"] == "ip"


class TestGetFreshCity:
    """get_fresh_city — Celery 早晨任务用. stale IP 触发 re-geo, 但单用户单日限速."""

    def _make_profile(self, db, **kwargs):
        from app.models.user_profile import UserProfile
        defaults = dict(
            user_id=999,
            use_manual_location=False, manual_city=None,
            detected_city="杭州", detected_region="杭州市",
            detected_source="ip",
            last_ip="1.2.3.4",
        )
        defaults.update(kwargs)
        p = UserProfile(**defaults)
        db.add(p); db.commit(); db.refresh(p)
        return p

    def test_fresh_data_no_refresh(self, db):
        """source='ip' 但只 stale 10min (< 6h 阈值) → 不刷."""
        from app.services.location_resolver import get_fresh_city
        now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        p = self._make_profile(db, location_updated_at=now - timedelta(minutes=10))
        # ip_geolocation 不该被调
        from unittest.mock import patch, AsyncMock
        with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
            city = get_fresh_city(db, p.user_id, now=now)
            assert city == "杭州"
            mock_geo.assert_not_called()

    def test_stale_ip_triggers_refresh(self, db):
        """source='ip' + stale 8h (> 6h 阈值) + 不是今天 → 同步刷 IP."""
        from app.services.location_resolver import get_fresh_city
        from app.services.ip_geolocation import GeoLocation
        now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        # 昨天的时间戳 — 不算单日限速
        p = self._make_profile(
            db, location_updated_at=now - timedelta(hours=20),
        )

        from unittest.mock import AsyncMock, patch
        new_loc = GeoLocation(city="北京", region="北京市", country="中国")
        with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
            mock_svc = mock_geo.return_value
            mock_svc.get_location_from_ip = AsyncMock(return_value=new_loc)
            city = get_fresh_city(db, p.user_id, now=now)

        assert city == "北京"
        db.refresh(p)
        assert p.detected_city == "北京"
        assert p.detected_source == "ip"

    def test_stale_gps_within_12h_no_refresh(self, db):
        """source='gps' + 10h stale (< 12h 阈值) → 不刷."""
        from app.services.location_resolver import get_fresh_city
        now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        p = self._make_profile(
            db, detected_source="gps",
            detected_lat=30.27, detected_lon=120.15,
            location_updated_at=now - timedelta(hours=10),
        )
        from unittest.mock import patch
        with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
            city = get_fresh_city(db, p.user_id, now=now)
            assert city == "杭州"
            mock_geo.assert_not_called()

    def test_manual_never_refreshes(self, db):
        """manual 永不刷新 — 用户显式指定 city, 任何 IP/GPS 都该忽略."""
        from app.services.location_resolver import get_fresh_city
        now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        p = self._make_profile(
            db,
            use_manual_location=True, manual_city="上海",
            location_updated_at=now - timedelta(days=30),  # 巨 stale
        )
        from unittest.mock import patch
        with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
            city = get_fresh_city(db, p.user_id, now=now)
            assert city == "上海"
            mock_geo.assert_not_called()

    def test_same_day_rate_limit(self, db):
        """已是今天 (Celery 早晨任务 N 个并发) → 跳过 IP geo, 用旧 city."""
        from app.services.location_resolver import get_fresh_city
        now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        # 今天早些时候已刷过 (8h 前 → 已 stale 但同一天)
        # 注: 当天 stale 仍超 6h, 但 same-day 限速生效, 不再刷
        same_day_earlier = datetime(2026, 5, 17, 0, 0, 0, tzinfo=timezone.utc)
        p = self._make_profile(db, location_updated_at=same_day_earlier)

        from unittest.mock import patch
        with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
            city = get_fresh_city(db, p.user_id, now=now)
            assert city == "杭州"
            mock_geo.assert_not_called()

    def test_no_last_ip_no_refresh(self, db):
        """last_ip 空 → 没法 fallback, 用旧 city."""
        from app.services.location_resolver import get_fresh_city
        now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        p = self._make_profile(
            db, last_ip=None,
            location_updated_at=now - timedelta(hours=20),
        )
        city = get_fresh_city(db, p.user_id, now=now)
        assert city == "杭州"

    def test_ip_geo_failure_returns_old_city(self, db):
        """IP geo 服务挂了/限速 → fallback 旧 city, 不抛."""
        from app.services.location_resolver import get_fresh_city
        now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        p = self._make_profile(
            db, location_updated_at=now - timedelta(hours=20),
        )
        from unittest.mock import AsyncMock, patch
        with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
            mock_svc = mock_geo.return_value
            mock_svc.get_location_from_ip = AsyncMock(side_effect=Exception("rate limited"))
            city = get_fresh_city(db, p.user_id, now=now)
        assert city == "杭州"

    def test_no_profile_returns_none(self, db):
        from app.services.location_resolver import get_fresh_city
        city = get_fresh_city(db, 12345)
        assert city is None
