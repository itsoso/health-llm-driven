"""Workday microbreak §8.3 deterministic safety gate.

Codex spec §8.3:
    safety:
      readiness_red: choose_mobility_or_rest
      after_meal_less_than_60_min: avoid_pushup
      acute_symptom: reject

覆盖三分支 + 正常态 + 幂等。微运动建议是 advisory(R4),闸门只做确定性安全降级/拒绝。
"""
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.daily_health import DietRecord, GarminData
from app.models.health_protocol import HealthProtocol
from app.models.symptom_entry import SymptomEntry
from app.models.user import User
from app.services import agenda_service
from app.services import workday_health_scheduler as scheduler
from app.services.workday_microbreak_safety import contains_acute_symptom_language


def _user(db):
    user = User(
        username=f"microbreak_{uuid.uuid4().hex[:8]}",
        email=f"microbreak_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="microbreak",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _readiness(db, user_id: int, score: int):
    db.add(GarminData(
        user_id=user_id,
        record_date=date.today(),
        data_source="apple-watch",
        training_readiness_score=score,
    ))
    db.commit()


_LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def test_acute_symptom_language_covers_pressure_breathing_and_one_sided_weakness():
    for text in (
        "胸口像有人坐着还能跑步吗",
        "吸不进气还能训练吗",
        "一侧胳膊抬不起来",
    ):
        assert contains_acute_symptom_language(text) is True


def _diet(db, user_id: int, *, minutes_ago: int):
    """写一条今天的饮食记录。

    meal_time 必须是**本地挂钟**(diet.py 真实写入语义),与 gate 的本地比较对齐。
    用 UTC 写会复现历史 tz 漂移 bug —— 这里特意用 Asia/Shanghai 挂钟。
    """
    now_local = datetime.now(_LOCAL_TZ)
    meal_dt = now_local - timedelta(minutes=minutes_ago)
    db.add(DietRecord(
        user_id=user_id,
        record_date=now_local.date(),  # gate 用本地日期查询餐次,fixture 对齐
        meal_type="午餐",
        meal_time=time(meal_dt.hour, meal_dt.minute, meal_dt.second),
        food_items="鸡胸肉,米饭",
    ))
    db.commit()


def _symptom(db, user_id: int, description: str):
    db.add(SymptomEntry(
        user_id=user_id,
        body_part="general",
        description=description,
        occurred_at=datetime.now(UTC),
        source="manual",
    ))
    db.commit()


def _active_protocols(db, user_id: int):
    return db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id,
        HealthProtocol.status == "active",
        HealthProtocol.notes.like("workday_scheduler:v0:%"),
    ).order_by(HealthProtocol.time_window, HealthProtocol.id).all()


def _arrival(protocols):
    return next(p for p in protocols if (p.implied_quantity or {}).get("slot") == "arrival")


# ─────────────────────── 1) readiness red → mobility/rest, NOT pushups ───────────────────────
def test_readiness_red_downgrades_arrival_to_non_pushup(db):
    user = _user(db)
    _readiness(db, user.id, 32)  # red

    result = scheduler.generate_today(db, user.id)

    assert result["readiness_tone"] == "red"
    assert result["microbreak_status"] == "downgraded"
    protocols = _active_protocols(db, user.id)
    assert len(protocols) == 3
    assert all("俯卧撑" not in p.name for p in protocols)
    arrival = _arrival(protocols)
    assert arrival.implied_quantity["exercise_type"] != "pushups"
    assert arrival.implied_quantity["downgraded_from"] == "pushups"


# ─────────────────────── 2) last meal < 60 min → avoid pushups (mobility/walk) ───────────────────────
def test_recent_meal_under_60_min_avoids_pushups_even_when_green(db):
    user = _user(db)
    _readiness(db, user.id, 85)   # green → 本应给俯卧撑
    _diet(db, user.id, minutes_ago=20)  # 餐后 20 分钟

    result = scheduler.generate_today(db, user.id)

    assert result["readiness_tone"] == "green"
    assert result["microbreak_status"] == "downgraded"
    assert "进餐" in result["safety_reason"]
    protocols = _active_protocols(db, user.id)
    assert len(protocols) == 3
    arrival = _arrival(protocols)
    assert arrival.implied_quantity["exercise_type"] != "pushups"
    assert arrival.implied_quantity["safety_gate"] == "after_meal_less_than_60_min"
    assert "俯卧撑" not in arrival.name


def test_meal_over_60_min_still_offers_pushups(db):
    user = _user(db)
    _readiness(db, user.id, 85)
    _diet(db, user.id, minutes_ago=90)  # 餐后 90 分钟 → 不触发

    result = scheduler.generate_today(db, user.id)

    assert result["microbreak_status"] == "offered"
    protocols = _active_protocols(db, user.id)
    arrival = _arrival(protocols)
    assert arrival.implied_quantity["exercise_type"] == "pushups"


# ─────────────────────── 3) acute red-flag symptom → reject (no nudge) ───────────────────────
def test_acute_symptom_rejects_microbreak_entirely(db):
    user = _user(db)
    _readiness(db, user.id, 85)  # green,但症状应一票否决
    _symptom(db, user.id, "运动时胸痛伴冷汗")

    result = scheduler.generate_today(db, user.id)

    assert result["microbreak_status"] == "rejected"
    assert result["created"] == 0
    assert result["safety_reason"]  # 带安全理由
    assert any("acute_symptom" in s for s in result["safety_signals"])
    assert _active_protocols(db, user.id) == []


def test_gi_bleed_keyword_rejects_microbreak(db):
    """消化道出血(柏油样便)是 symptoms.py 的 CRITICAL,微运动闸门不得漏(under-alarm)。"""
    user = _user(db)
    _readiness(db, user.id, 85)
    _symptom(db, user.id, "今天发现柏油样便")

    result = scheduler.generate_today(db, user.id)

    assert result["microbreak_status"] == "rejected"
    assert _active_protocols(db, user.id) == []


def test_acute_symptom_archives_previously_generated_protocols(db):
    user = _user(db)
    _readiness(db, user.id, 85)
    # 先正常生成
    first = scheduler.generate_today(db, user.id)
    assert first["created"] == 3
    assert len(_active_protocols(db, user.id)) == 3

    # 之后出现急性症状 → 再次生成应归档既有协议、不再投影
    _symptom(db, user.id, "突然呼吸困难")
    second = scheduler.generate_today(db, user.id)

    assert second["microbreak_status"] == "rejected"
    assert second["archived"] == 3
    assert _active_protocols(db, user.id) == []


# ─────────────────────── 4) normal → pushups offered + completable ───────────────────────
def test_normal_state_offers_pushups_and_is_completable(db):
    user = _user(db)
    _readiness(db, user.id, 85)  # green, no meal, no symptom

    result = scheduler.generate_today(db, user.id)

    assert result["microbreak_status"] == "offered"
    assert result["created"] == 3
    protocols = _active_protocols(db, user.id)
    arrival = _arrival(protocols)
    assert arrival.implied_quantity["exercise_type"] == "pushups"
    assert arrival.name == "到公司后俯卧撑 12 个"

    # 可完成性:agenda 投影出来 + 协议轨可一键完成
    agenda = agenda_service.today(db, user.id)
    titles = {item["title"] for item in agenda["items"]}
    assert "到公司后俯卧撑 12 个" in titles
    assert arrival.completion_mode == "one_tap"
    assert arrival.manual_track_allowed is True


# ─────────────────────── 5) idempotent: regenerating same day, no duplicates ───────────────────────
def test_regenerating_same_day_does_not_duplicate(db):
    user = _user(db)
    _readiness(db, user.id, 78)

    first = scheduler.generate_today(db, user.id)
    second = scheduler.generate_today(db, user.id)

    assert first["created"] == 3
    assert second["created"] == 0
    assert second["updated"] == 3
    assert len(_active_protocols(db, user.id)) == 3


def test_idempotent_under_post_meal_downgrade(db):
    user = _user(db)
    _readiness(db, user.id, 85)
    _diet(db, user.id, minutes_ago=15)

    first = scheduler.generate_today(db, user.id)
    second = scheduler.generate_today(db, user.id)

    assert first["microbreak_status"] == "downgraded"
    assert first["created"] == 3
    assert second["created"] == 0
    assert second["updated"] == 3
    assert len(_active_protocols(db, user.id)) == 3
