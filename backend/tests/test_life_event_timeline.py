"""生活事件情景账本(2026-07-12)— 时间锚从"猜"变"存"。

不变量:
1. 时间解析唯一真源在 occurred_time.py(确定性;LLM 只传原话,不编时刻);
2. 精度诚实:"下午"存 part_of_day,展示层显示"下午"而非假装 15:00;
3. 复用 HealthEpisode(episode_type=life_event),不建新表(单一真源);
4. event kind 是 AUTO 档(非医疗决策),但走既有确认门框架(不在 never/typed 集)。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.occurred_time import BEIJING_TZ, precision_display, resolve_occurred_at

NOW = datetime(2026, 7, 12, 21, 35, tzinfo=BEIJING_TZ)


class TestResolveOccurredAt:
    def test_iso_exact(self):
        dt, p = resolve_occurred_at("2026-07-12T21:07:00+08:00", now=NOW)
        assert (dt.hour, dt.minute, p) == (21, 7, "exact")

    def test_iso_utc_converted_to_beijing(self):
        dt, p = resolve_occurred_at("2026-07-12T13:07:00+00:00", now=NOW)
        assert (dt.hour, dt.minute, p) == (21, 7, "exact")

    def test_hhmm_today(self):
        dt, p = resolve_occurred_at("21:07", now=NOW)
        assert (dt.day, dt.hour, dt.minute, p) == (12, 21, 7, "exact")

    def test_hhmm_future_means_yesterday(self):
        # 21:35 说 "23:00" → 昨晚 23:00,不是未来
        dt, p = resolve_occurred_at("23:00", now=NOW)
        assert (dt.day, dt.hour, p) == (11, 23, "exact")

    def test_part_of_day_honest_precision(self):
        dt, p = resolve_occurred_at("下午", now=NOW)
        assert (dt.day, dt.hour, p) == (12, 15, "part_of_day")

    def test_yesterday_evening_compound(self):
        dt, p = resolve_occurred_at("昨晚", now=NOW)
        assert (dt.day, dt.hour, p) == (11, 20, "part_of_day")

    def test_yesterday_with_part(self):
        dt, p = resolve_occurred_at("昨天下午", now=NOW)
        assert (dt.day, dt.hour, p) == (11, 15, "part_of_day")

    def test_just_now_hour_precision(self):
        dt, p = resolve_occurred_at("刚才", now=NOW)
        assert p == "hour" and dt == NOW - timedelta(minutes=10)

    def test_bare_day_noon_representative(self):
        dt, p = resolve_occurred_at("昨天", now=NOW)
        assert (dt.day, dt.hour, p) == (11, 12, "day")

    def test_cn_clock(self):
        dt, p = resolve_occurred_at("今天 21点", now=NOW)
        assert (dt.hour, dt.minute, p) == (21, 0, "exact")

    def test_empty_defaults_now_exact(self):
        dt, p = resolve_occurred_at(None, now=NOW)
        assert (dt, p) == (NOW, "exact")
        dt2, p2 = resolve_occurred_at("  ", now=NOW)
        assert (dt2, p2) == (NOW, "exact")

    def test_garbage_fail_loud(self):
        with pytest.raises(ValueError):
            resolve_occurred_at("大概那个时候吧", now=NOW)

    def test_precision_display_honesty(self):
        dt, p = resolve_occurred_at("下午", now=NOW)
        # part_of_day 显示原话,不假装精确
        assert precision_display(dt, p, "下午") == "下午"
        dt2, p2 = resolve_occurred_at("21:07", now=NOW)
        assert precision_display(dt2, p2) == "21:07"


class TestLifeEventAPI:
    def test_create_and_list_roundtrip(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        res = client.post("/api/v1/episodes/life-event", headers=headers, json={
            "title": "落地北京", "occurred_at": "21:07",
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["title"] == "落地北京"
        assert body["occurred_precision"] == "exact"
        assert body["occurred_display"] == "21:07"

        res2 = client.post("/api/v1/episodes/life-event", headers=headers, json={
            "title": "发现舌尖溃疡", "occurred_at": "下午", "notes": "决定美团买药送酒店",
        })
        assert res2.status_code == 200
        assert res2.json()["occurred_precision"] == "part_of_day"
        assert res2.json()["occurred_display"] == "下午"

        lst = client.get("/api/v1/episodes/me/life-events?days=1", headers=headers)
        assert lst.status_code == 200
        items = lst.json()
        titles = [it["title"] for it in items]
        assert "落地北京" in titles and "发现舌尖溃疡" in titles
        # 升序时间线
        times = [it["occurred_at"] for it in items]
        assert times == sorted(times)

    def test_garbage_time_is_400(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        res = client.post("/api/v1/episodes/life-event", headers=headers, json={
            "title": "出发", "occurred_at": "大概那个时候",
        })
        assert res.status_code == 400

    def test_cross_user_isolation(self, client, db, auth_user_and_headers):
        from app.models.episode import HealthEpisode
        from app.models.user import User as UserModel
        user, headers = auth_user_and_headers
        other = UserModel(
            username="le_other", email="le_other@example.com", hashed_password="x",
            name="other", is_active=True, is_approved=True,
        )
        db.add(other); db.commit(); db.refresh(other)
        db.add(HealthEpisode(
            user_id=other.id, episode_type="life_event", occurred_at=datetime.now(timezone.utc),
            status="closed", risk_level="L0", headline="别人的事件",
        ))
        db.commit()
        lst = client.get("/api/v1/episodes/me/life-events?days=1", headers=headers)
        assert all(it["title"] != "别人的事件" for it in lst.json())


class TestEventKindContracts:
    def test_event_kind_is_auto_tier(self):
        """event 非医疗决策 → 不在 never_auto / typed_only 集(AUTO)。"""
        from app.services.agent_executor import (
            _FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS,
            _TYPED_ONLY_AUTO_CONFIRM_KINDS,
        )
        assert "event" not in _FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS
        assert "event" not in _TYPED_ONLY_AUTO_CONFIRM_KINDS

    def test_dimension_aliases_resolve_to_events(self):
        from app.services.health_query_dimensions import HEALTH_QUERY_DIM_ALIASES
        for alias in ("timeline", "时间线", "行程", "生活事件", "life_events"):
            assert HEALTH_QUERY_DIM_ALIASES[alias] == "events"
