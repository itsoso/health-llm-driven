"""B5: Celery 切到 get_fresh_city, 早晨任务 stale IP 用户能被同步刷新.

只测 wiring (notifications._get_user_city → get_fresh_city), 详细 freshness 行为
在 test_location_resolver.py::TestGetFreshCity 覆盖.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock


def test_notifications_get_user_city_routes_to_fresh_helper(db):
    """notifications._get_user_city 必须走 get_fresh_city — Celery 早晨任务用."""
    from app.tasks.notifications import _get_user_city
    from app.models.user import User
    from app.models.user_profile import UserProfile

    user = User(
        username="freshtest", email="fresh@test.com",
        hashed_password="x", name="测", is_active=True, is_approved=True,
    )
    db.add(user); db.commit(); db.refresh(user)

    # 昨天的时间戳, stale 20h, source='ip'
    yesterday = datetime.now(timezone.utc) - timedelta(hours=20)
    p = UserProfile(
        user_id=user.id,
        detected_city="杭州", detected_region="杭州市",
        detected_source="ip",
        last_ip="1.2.3.4",
        location_updated_at=yesterday,
    )
    db.add(p); db.commit()

    # mock IP geo → 返北京. notifications._get_user_city 应触发 re-geo.
    from app.services.ip_geolocation import GeoLocation
    with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
        mock_svc = mock_geo.return_value
        mock_svc.get_location_from_ip = AsyncMock(
            return_value=GeoLocation(city="北京", region="北京市", country="中国")
        )
        city = _get_user_city(db, user.id)

    # 应拿到刷新后的北京 (而不是旧 city 杭州)
    assert city == "北京"


def test_smart_plan_get_user_city_routes_to_fresh_helper(db):
    """smart_plan_service._get_user_city 也走 get_fresh_city."""
    from app.services.smart_plan_service import SmartPlanService
    from app.models.user import User
    from app.models.user_profile import UserProfile

    user = User(
        username="freshtest2", email="fresh2@test.com",
        hashed_password="x", name="测", is_active=True, is_approved=True,
    )
    db.add(user); db.commit(); db.refresh(user)

    # 今天已刷过 → same-day 限速生效, 不再刷
    today_earlier = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    p = UserProfile(
        user_id=user.id,
        detected_city="杭州", detected_region="杭州市",
        detected_source="ip",
        last_ip="1.2.3.4",
        location_updated_at=today_earlier,
    )
    db.add(p); db.commit()

    svc = SmartPlanService(db)
    from unittest.mock import patch
    with patch("app.services.ip_geolocation.get_geolocation_service") as mock_geo:
        city = svc._get_user_city(user.id)
        mock_geo.assert_not_called()  # same-day 限速

    assert city == "杭州"
