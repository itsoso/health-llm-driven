"""统一今日时间线投影(首页新脊柱)。钉:
① 空用户返回结构合法、items=[]、不抛
② 1 个 due 协议 + 1 条今日 workout → action 进 items、observation 进 past
③ 归因项 best-effort:无 graded card 时 proof 不出现且不报错
④ API shape:GET /api/v1/timeline/today 200 + 顶层键齐全

组合服务,只读投影。build_twin/Redis 在测试里走降级(agenda 内部 try/except 容忍 None)。
"""
from datetime import date, datetime, timezone

import pytest

from app.services.today_timeline_service import build_today_spine

TOP_KEYS = {"date", "current_window", "now", "items", "past", "counts"}
COUNT_KEYS = {"actionable", "overdue", "info"}


def _rhythm_items(spine):
    return [it for it in spine["items"] if it.get("action_kind") == "day_rhythm"]


def _add_today_workout(db, user_id: int):
    from app.models.daily_health import WorkoutRecord

    w = WorkoutRecord(
        user_id=user_id,
        workout_date=date.today(),
        start_time=datetime.now(timezone.utc),
        workout_type="running",
        duration_seconds=1080,
        distance_meters=2600,
        avg_heart_rate=150,
    )
    db.add(w)
    db.commit()
    return w


def test_empty_user_valid_shape(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    spine = build_today_spine(db, user.id)
    assert set(spine.keys()) == TOP_KEYS
    assert _rhythm_items(spine), "空用户也应有低打扰日内时间骨架"
    assert spine["date"] == str(date.today())
    assert spine["current_window"] in {
        "morning", "noon", "afternoon", "evening", "bedtime", "anytime"}
    assert spine["past"]["events"] == []
    assert spine["past"]["completed_count"] == 0
    assert set(spine["counts"].keys()) == COUNT_KEYS
    assert spine["counts"]["actionable"] == 0


def test_day_rhythm_covers_user_day_without_becoming_tasks(db, auth_user_and_headers):
    """用户视角完整时间动线:晨起/午间/下午/晚间/睡前都有低打扰系统时刻卡。"""
    user, _ = auth_user_and_headers

    spine = build_today_spine(db, user.id)
    rhythm = _rhythm_items(spine)

    assert {it["time_window"] for it in rhythm} >= {
        "morning", "noon", "afternoon", "evening", "bedtime",
    }
    assert all(it["driver"] == "time_driven" for it in rhythm)
    assert all(it["kind"] == "advisory" for it in rhythm)
    assert all(it["can_complete"] is False for it in rhythm)
    assert all(it["event_id"] is None for it in rhythm)
    assert all(it["complete_ref"] is None for it in rhythm)


def test_day_rhythm_skips_domains_already_covered():
    """已有运动/饮食/睡眠类真实项时,系统时刻卡不重复提醒同一类事情。"""
    import app.services.today_timeline_service as svc

    existing = [
        {"action_kind": "training", "time_window": "morning", "title": "晨练"},
        {"action_kind": "diet", "time_window": "noon", "title": "午餐记录"},
        {"action_kind": "sleep", "time_window": "bedtime", "title": "睡眠计划"},
    ]

    rhythm = svc._day_rhythm_items(existing)
    ids = {it["id"] for it in rhythm}

    assert "rhythm_morning_movement" not in ids
    assert "rhythm_noon_meal" not in ids
    assert "rhythm_bedtime_wind_down" not in ids


def test_today_uses_user_profile_timezone(db, auth_user_and_headers, monkeypatch):
    """用户在美东晚间时,不应被固定 Asia/Shanghai 推到下一天。"""
    import app.services.today_timeline_service as svc
    from app.models.user_profile import UserProfile

    user, _ = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, timezone="America/New_York"))
    db.commit()

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 6, 16, 2, 30, tzinfo=timezone.utc)
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)

    monkeypatch.setattr(svc, "datetime", FixedDateTime)

    spine = svc.build_today_spine(db, user.id)

    assert spine["date"] == "2026-06-15"
    assert spine["current_window"] == "bedtime"


def test_due_protocol_and_today_workout(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    # 1 个 due 协议(今日待办、pending)
    client.post("/api/v1/protocols/seed/water-cup", headers=h)
    # 1 条今日 workout(过去已发生)
    _add_today_workout(db, user.id)

    spine = build_today_spine(db, user.id)

    # action 进 items:可完成的协议项
    actions = [it for it in spine["items"] if it["kind"] == "action"]
    assert actions, "due 协议应映射成 action item"
    water = next(it for it in actions if it["complete_ref"]
                 and it["complete_ref"]["object_type"] == "health_protocol")
    assert water["can_complete"] is True
    assert water["status"] == "pending"
    assert spine["counts"]["actionable"] >= 1

    # observation 进 past(不在 items 里)
    assert all(it["kind"] != "observation" for it in spine["items"])
    obs = spine["past"]["events"]
    assert any(o["kind"] == "observation" and o["id"].startswith("workout_") for o in obs)


def test_driver_survives_response_model(client, auth_user_and_headers):
    """driver 必须穿过 TodaySpineItem response_model 到客户端 —— service 有但 schema
    没声明会被 FastAPI 静默剥离(本测试盯端点响应,非 service dict)。"""
    _, h = auth_user_and_headers
    client.post("/api/v1/protocols/seed/water-cup", headers=h)
    r = client.get("/api/v1/timeline/today", headers=h)
    assert r.status_code == 200
    actions = [it for it in r.json()["items"] if it["kind"] == "action"]
    assert actions, "应有 due 协议 action item"
    assert "driver" in actions[0], "driver 被 response_model 剥离 —— TodaySpineItem 需声明该字段"
    assert actions[0]["driver"] == "plan_driven"


def test_day_rhythm_survives_response_model(client, auth_user_and_headers):
    """time_driven 系统时刻卡必须穿过 response_model,否则移动端看不到完整时间动线。"""
    _, h = auth_user_and_headers
    r = client.get("/api/v1/timeline/today", headers=h)

    assert r.status_code == 200
    rhythm = [it for it in r.json()["items"] if it.get("action_kind") == "day_rhythm"]
    assert rhythm, "response_model 不应剥离系统时刻卡"
    assert {it["time_window"] for it in rhythm} >= {
        "morning", "noon", "afternoon", "evening", "bedtime",
    }
    assert all(it["driver"] == "time_driven" for it in rhythm)
    assert all(it["can_complete"] is False for it in rhythm)


def test_auto_observed_protocol_counts_as_completed_not_actionable(client, db, auth_user_and_headers):
    """可穿戴自动观测完成应计入今日完成数,但不再是可点击待办。"""
    from app.services import health_protocol_service as proto_svc

    user, h = auth_user_and_headers
    protocol_id = client.post("/api/v1/protocols", headers=h, json={
        "domain": "training",
        "name": "到公司后俯卧撑 20 个",
        "mechanism": "passive_device",
        "completion_mode": "auto_observed",
    }).json()["id"]

    proto_svc.auto_observe_protocol(
        db,
        protocol_id,
        user.id,
        value={"observed_from": "test"},
    )

    spine = build_today_spine(db, user.id)
    row = next(it for it in spine["items"] if it["complete_ref"]
               and it["complete_ref"]["object_id"] == protocol_id)
    assert row["status"] == "auto_observed"
    assert row["can_complete"] is False
    assert spine["past"]["completed_count"] == 1


def test_outcome_best_effort_no_graded_card(db, auth_user_and_headers):
    """无 graded ActionCard 时:不报错,且无 outcome item / proof 不出现。"""
    user, _ = auth_user_and_headers
    spine = build_today_spine(db, user.id)
    assert all(it["kind"] != "outcome" for it in spine["items"])
    assert all(it.get("proof") is None for it in spine["items"])


def test_outcome_item_when_graded_card_improved(db, auth_user_and_headers):
    """有 graded improved 卡 → outcome item 带 proof(增强项生效)。

    proof 必须标 association_only(非因果, PRD R9);标题不下「改善了」因果断言。
    构造的卡用低风险 severity 以仍命中归因通道。
    """
    from app.models.action_card import ActionCard

    user, _ = auth_user_and_headers
    db.add(ActionCard(
        user_id=user.id,
        title="提前入睡 30 分钟",
        content="x",
        metric_key="sleep_score",
        baseline_value="62",
        actual_value="78",
        outcome="improved",
        severity="low",
        graded_at=datetime.now(timezone.utc),
    ))
    db.commit()

    spine = build_today_spine(db, user.id)
    outcomes = [it for it in spine["items"] if it["kind"] == "outcome"]
    assert outcomes, "improved 卡应折成 outcome item"
    item = outcomes[0]
    # 标题去因果:不含「改善了」这种「做了→好了」的因果完成态断言
    assert "改善了" not in item["title"]
    proof = item["proof"]
    assert proof["metric"] == "sleep_score"
    assert proof["label"] == "睡眠评分"
    assert proof["delta"] == "62 → 78"
    assert proof["direction"] == "up"
    # 非因果标志:时序关联,前端据此标注 PRD R9
    assert proof["association_only"] is True


def test_critical_severity_card_not_in_items(db, auth_user_and_headers):
    """高风险(critical severity)卡的好转不进绿色 trophy「庆祝」通道。"""
    from app.models.action_card import ActionCard

    user, _ = auth_user_and_headers
    db.add(ActionCard(
        user_id=user.id,
        title="血压急性升高已回落",
        content="x",
        metric_key="bp",
        baseline_value="180",
        actual_value="135",
        outcome="improved",
        severity="critical",
        graded_at=datetime.now(timezone.utc),
    ))
    db.commit()

    spine = build_today_spine(db, user.id)
    assert all(it["kind"] != "outcome" for it in spine["items"]), \
        "critical severity 卡不应渲染成 outcome 庆祝项"


@pytest.mark.parametrize(
    ("metric_key", "title"),
    [("ldl", "降低 LDL"), ("blood_glucose", "控制血糖")],
)
def test_clinician_gated_legacy_card_not_rendered_as_outcome_trophy(
    db, auth_user_and_headers, metric_key, title,
):
    from app.models.action_card import ActionCard

    user, _ = auth_user_and_headers
    db.add(ActionCard(
        user_id=user.id, title=title, content="x", metric_key=metric_key,
        baseline_value="4.2", actual_value="2.8", outcome="improved",
        graded_at=datetime.now(timezone.utc),
    ))
    db.commit()

    spine = build_today_spine(db, user.id)

    assert all(it["kind"] != "outcome" for it in spine["items"])


def test_api_shape(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.get("/api/v1/timeline/today", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == TOP_KEYS
    assert isinstance(body["items"], list)
    assert set(body["past"].keys()) == {"completed_count", "events"}
    assert set(body["counts"].keys()) == COUNT_KEYS
