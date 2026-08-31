"""转后异步生活事件抽取 v1 测试。

抽取写入复用的 HealthEpisode(episode_type="life_event"), 读走既有
/episodes/me/life-events 与 health_query(events) 维度。覆盖:
时间精度三档 / 抽取幂等 / 防过度抽取四道闸 / 读路 + 跨用户隔离 /
health_query events 维度别名 + 未知维度仍 fail-loud。
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.episode import HealthEpisode
from app.models.user import User
from app.services.health_query_dimensions import normalize_health_query_args
from app.services.life_event_extractor import (
    _looks_like_health_record,
    _resolve_time,
    extract_life_events_from_message,
)

BJ = timezone(timedelta(hours=8))
# 消息时间取北京晚 22:00 → "21:07" 落在今天 (occurred_time 未来时刻回退昨天的逻辑不触发)。
_ANCHOR = datetime(2026, 7, 13, 22, 0, tzinfo=BJ)
_MSG_CREATED_UTC = datetime(2026, 7, 13, 14, 0)  # = 北京 22:00


def _mk_user(db) -> User:
    u = User(
        username=f"life_{uuid.uuid4().hex[:8]}",
        email=f"life_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="生活事件用户",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_user_message(db, user_id: int, content: str, created_at: datetime) -> AgentMessage:
    conv = AgentConversation(user_id=user_id, title="t", session_key=f"s-{uuid.uuid4().hex[:6]}")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    msg = AgentMessage(
        conversation_id=conv.id, role="user", content=content, created_at=created_at
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _life_events(db, user_id):
    return (
        db.query(HealthEpisode)
        .filter(
            HealthEpisode.user_id == user_id,
            HealthEpisode.episode_type == "life_event",
        )
        .all()
    )


# ── 确定性时间精度三档 (复用 occurred_time, 空/不可解析 → inferred) ──

def test_resolve_time_exact_hhmm():
    dt, precision = _resolve_time("21:07", _ANCHOR)
    assert precision == "exact"
    assert dt.hour == 21 and dt.minute == 7


def test_resolve_time_part_of_day_is_approx():
    dt, precision = _resolve_time("下午", _ANCHOR)
    assert precision == "part_of_day"
    assert dt.hour == 15


def test_resolve_time_inferred_when_no_time():
    dt, precision = _resolve_time("", _ANCHOR)
    assert precision == "inferred"
    assert dt == _ANCHOR
    dt2, precision2 = _resolve_time(None, _ANCHOR)
    assert precision2 == "inferred" and dt2 == _ANCHOR


def test_resolve_time_unparseable_falls_back_inferred():
    dt, precision = _resolve_time("某个说不清的时候", _ANCHOR)
    assert precision == "inferred"
    assert dt == _ANCHOR


# ── 抽取幂等 (同天同归一化 title 只落一条) ─────────────────────

def test_extraction_is_idempotent(db):
    user = _mk_user(db)
    msg = _mk_user_message(db, user.id, "下午从家出发, 21:07 落地北京", _MSG_CREATED_UTC)
    events = [
        {"title": "落地北京", "category": "arrival", "time_text": "21:07"},
        {"title": "从家出发", "category": "travel", "time_text": "下午"},
    ]
    s1 = extract_life_events_from_message(db, user.id, msg.id, llm_events=events)
    assert s1["created"] == 2

    s2 = extract_life_events_from_message(db, user.id, msg.id, llm_events=events)
    assert s2["created"] == 0
    assert s2["skipped_duplicate"] == 2

    rows = _life_events(db, user.id)
    assert len(rows) == 2
    by_title = {r.headline: r for r in rows}
    assert by_title["落地北京"].context_snapshot["occurred_precision"] == "exact"
    assert by_title["落地北京"].occurred_at.hour == 21
    assert by_title["从家出发"].context_snapshot["occurred_precision"] == "part_of_day"
    # provenance + category 记进 snapshot
    assert by_title["落地北京"].source_id == msg.id
    assert by_title["落地北京"].context_snapshot["category"] == "arrival"
    assert by_title["落地北京"].source_type == "chat"


# ── 闸 ①: category 白名单外丢弃 ───────────────────────────────

def test_gate_category_whitelist_drops(db):
    user = _mk_user(db)
    msg = _mk_user_message(db, user.id, "点了杯咖啡", _MSG_CREATED_UTC)
    events = [{"title": "点了杯咖啡", "category": "beverage", "time_text": ""}]
    s = extract_life_events_from_message(db, user.id, msg.id, llm_events=events)
    assert s["created"] == 0
    assert s["dropped_category"] == 1
    assert len(_life_events(db, user.id)) == 0


# ── 闸 ②: 每日上限触发丢弃 + warning ──────────────────────────

def test_gate_daily_cap_drops(db, caplog):
    user = _mk_user(db)
    for i in range(20):
        db.add(
            HealthEpisode(
                user_id=user.id,
                episode_type="life_event",
                source_type="seed",
                occurred_at=datetime(2026, 7, 13, 10, 0, tzinfo=BJ) + timedelta(minutes=i),
                status="closed",
                risk_level="L0",
                headline=f"事件{i}",
                context_snapshot={"occurred_precision": "inferred"},
            )
        )
    db.commit()

    msg = _mk_user_message(db, user.id, "下午出门散步", _MSG_CREATED_UTC)
    events = [{"title": "出门散步", "category": "routine", "time_text": "下午"}]
    with caplog.at_level("WARNING"):
        s = extract_life_events_from_message(db, user.id, msg.id, llm_events=events)
    assert s["created"] == 0
    assert s["dropped_daily_cap"] == 1
    assert any("每日上限" in r.message for r in caplog.records)


# ── 闸 ②: 每消息上限 (最多 3) ─────────────────────────────────

def test_gate_per_message_cap_drops(db):
    user = _mk_user(db)
    msg = _mk_user_message(db, user.id, "一连串事件", _MSG_CREATED_UTC)
    events = [
        {"title": f"独立事件{i}", "category": "other", "time_text": ""} for i in range(5)
    ]
    s = extract_life_events_from_message(db, user.id, msg.id, llm_events=events)
    assert s["created"] == 3
    assert s["dropped_message_cap"] == 2


# ── 闸 ③: 已有专表的数值记录不抽 ──────────────────────────────

def test_gate_health_record_not_extracted(db):
    user = _mk_user(db)
    msg = _mk_user_message(db, user.id, "喝了500ml水", _MSG_CREATED_UTC)
    events = [{"title": "喝了500ml水", "category": "routine", "time_text": ""}]
    s = extract_life_events_from_message(db, user.id, msg.id, llm_events=events)
    assert s["created"] == 0
    assert s["dropped_health_record"] == 1
    assert len(_life_events(db, user.id)) == 0


def test_looks_like_health_record_does_not_catch_purchase():
    assert _looks_like_health_record("喝了500ml水") is True
    assert _looks_like_health_record("体重78.5kg") is True
    assert _looks_like_health_record("血压135/88") is True
    # 合法生活事件不误伤
    assert _looks_like_health_record("买了500g牛肉") is False
    assert _looks_like_health_record("到公司了") is False


# ── 抽取跳过非本人 / 非 user 消息 ─────────────────────────────

def test_extraction_skips_non_owner_message(db):
    owner = _mk_user(db)
    other = _mk_user(db)
    msg = _mk_user_message(db, owner.id, "下午到公司", _MSG_CREATED_UTC)
    events = [{"title": "到公司", "category": "arrival", "time_text": "下午"}]
    s = extract_life_events_from_message(db, other.id, msg.id, llm_events=events)
    assert s["created"] == 0


# ── 读路: 抽取结果经既有 /episodes/me/life-events 可见 + 跨用户隔离 ──

def test_extracted_events_readable_via_episodes_api(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    recent_message_created_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    )
    msg = _mk_user_message(
        db,
        user.id,
        "下午从家出发, 21:07落地北京",
        recent_message_created_at,
    )
    events = [
        {"title": "落地北京", "category": "arrival", "time_text": "21:07"},
        {"title": "从家出发", "category": "travel", "time_text": "下午"},
    ]
    extract_life_events_from_message(db, user.id, msg.id, llm_events=events)

    # 另一用户抽取的事件不可见 (跨用户隔离)
    from tests.conftest import create_authenticated_user

    other, _ = create_authenticated_user(db)
    omsg = _mk_user_message(db, other.id, "刚到机场", _MSG_CREATED_UTC)
    extract_life_events_from_message(
        db, other.id, omsg.id, llm_events=[{"title": "到机场", "category": "arrival", "time_text": ""}]
    )

    r = client.get("/api/v1/episodes/me/life-events", params={"days": 30}, headers=headers)
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()]
    assert "落地北京" in titles and "从家出发" in titles
    assert "到机场" not in titles

    # part_of_day 精度诚实展示原话时段
    from_home = next(e for e in r.json() if e["title"] == "从家出发")
    assert from_home["occurred_precision"] == "part_of_day"
    assert from_home["occurred_display"] == "下午"


# ── health_query events 维度别名 + 未知维度 fail-loud ──────────

def test_health_query_alias_maps_to_events():
    # 既有别名
    assert normalize_health_query_args({"dimension": "行程"})["dimension"] == "events"
    assert normalize_health_query_args({"dimension": "时间线"})["dimension"] == "events"
    # 本切片新增别名
    assert normalize_health_query_args({"dimension": "轨迹"})["dimension"] == "events"
    assert normalize_health_query_args({"dimension": "trip"})["dimension"] == "events"


def test_exec_health_query_unknown_dimension_fails_loud(db, auth_user_and_headers):
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    out = asyncio.run(
        ex._exec_health_query("", {}, {"dimension": "totally_bogus_dim_xyz"})
    )
    assert "未知 dimension" in out
    assert "合法值" in out
    # events 是合法维度, 应在 fail-loud 列出的合法值里
    assert "events" in out
