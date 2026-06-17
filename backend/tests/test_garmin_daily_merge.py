"""多源 GarminData 按天合并端点测试 (/daily-health/garmin/me)。

回归 (2026-06-17): 同一天 apple-watch 行有 steps=3454, 而 garmin/ringconn 行 steps 为空。
端点旧实现返回每源一行, 客户端读 days[0] 落到空 steps 的单源行 → 首页步数/活动/卡路里
显示 0(其实数据都在)。端点须按 record_date 合并, 逐指标按 device_source_priority 取
最高优先级的非空值。
"""
from datetime import date

import pytest

from app.models.user import User
from app.models.daily_health import GarminData


@pytest.fixture
def test_user(db):
    u = User(
        username="mguser",
        email="mg@example.com",
        hashed_password="x",
        name="MG",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def auth_headers(client, test_user):
    from app.services.auth import auth_service

    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


def _get(client, headers, start, end):
    return client.get(
        f"/api/v1/daily-health/garmin/me?start_date={start}&end_date={end}",
        headers=headers,
    )


class TestGarminDailyMerge:
    def test_multisource_day_merges_to_one_row_with_real_steps(self, client, db, auth_headers, test_user):
        d = date(2026, 6, 17)
        db.add_all([
            # apple-watch: 真实步数/活动/卡路里 + RHR/HRV
            GarminData(
                user_id=test_user.id, record_date=d, data_source="apple-watch",
                steps=3454, active_minutes=4, active_calories=90,
                resting_heart_rate=48, hrv=54.0,
            ),
            # garmin: 步数为空, active_minutes=0 (占位), 无热量 —— days[0] 落这行就会显示 0
            GarminData(
                user_id=test_user.id, record_date=d, data_source="garmin",
                steps=None, active_minutes=0, active_calories=None,
                body_battery_current=66,
            ),
            # ringconn: 几乎全空
            GarminData(user_id=test_user.id, record_date=d, data_source="ringconn", steps=None),
        ])
        db.commit()

        r = _get(client, auth_headers, d.isoformat(), d.isoformat())
        assert r.status_code == 200
        rows = r.json()
        # 三个单源行 → 合并成「一天一行」
        assert len(rows) == 1
        row = rows[0]
        assert row["record_date"] == d.isoformat()
        # 步数/活动/卡路里取 apple-watch (watch-first) 的真实值, 不被 garmin 的空/0 掩盖
        assert row["steps"] == 3454
        assert row["active_minutes"] == 4
        assert row["active_calories"] == 90
        # body_battery 取 garmin (garmin-first)
        assert row["body_battery_current"] == 66
        # RHR 取 apple-watch (watch+ring first)
        assert row["resting_heart_rate"] == 48

    def test_single_source_day_passthrough(self, client, db, auth_headers, test_user):
        d = date(2026, 6, 10)
        db.add(GarminData(
            user_id=test_user.id, record_date=d, data_source="garmin",
            steps=8000, active_minutes=30,
        ))
        db.commit()

        r = _get(client, auth_headers, d.isoformat(), d.isoformat())
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["steps"] == 8000
        assert rows[0]["active_minutes"] == 30

    def test_multiple_dates_one_row_each_newest_first(self, client, db, auth_headers, test_user):
        d1 = date(2026, 6, 8)
        d2 = date(2026, 6, 9)
        db.add_all([
            GarminData(user_id=test_user.id, record_date=d1, data_source="apple-watch", steps=100),
            GarminData(user_id=test_user.id, record_date=d1, data_source="garmin", steps=None),
            GarminData(user_id=test_user.id, record_date=d2, data_source="apple-watch", steps=200),
        ])
        db.commit()

        r = _get(client, auth_headers, d1.isoformat(), d2.isoformat())
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        # newest first
        assert rows[0]["record_date"] == d2.isoformat()
        assert rows[0]["steps"] == 200
        assert rows[1]["record_date"] == d1.isoformat()
        assert rows[1]["steps"] == 100
