# -*- coding: utf-8 -*-
"""D1 读拉类进程内直调(garmin-sync 治理 Wave 3)—— golden-master parity + 不变量。

背景:agent_executor 读工具过去对每个维度打 localhost 回环(`_api_get`)重入整个 FastAPI
中间件栈,付跨-worker 饥饿 + 内层 60s 中间件连杀 + 双鉴权/双 JSON 税。D1 把只读维度改为
进程内直读(fresh SessionLocal,`agent_read_tools` reader),照 `_run_orchestrator_in_process`
先例。写工具**绝不**进程内(Wave 2 写取消安全依赖回环事务隔离)。

契约钉死:
- **shape parity**:进程内 reader 输出 == 真 route(TestClient,完整 response_model)输出
  —— D1 是纯 transport 变更,LLM 所见绝不因换传输而漂移。
- **killswitch**:`reads_in_process=False` → 回退旧 `_api_get`;True → 零 HTTP。
- **会话纪律**:fresh SessionLocal(非 self.db),成功不 commit、finally close、异常 rollback+close。
- **用户作用域**:reader 显式 `filter(user_id==)`,A 的 executor 永不拿到 B 的数据。
- **fail-loud**:user_id 为 None → 诚实 Error 串,绝不裸查。
- **截断单一真源**:`_truncate_for_display` HTTP 与进程内两路共用。
"""
import asyncio
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_required
from app.config import settings
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import (
    DietRecord,
    ExerciseRecord,
    GarminData,
    SleepLevelInterval,
    SpO2Sample,
    WaterIntake,
    WorkoutRecord,
)
from app.models.episode import HealthEpisode
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.illness import IllnessEpisode
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.models.weight import WeightRecord
from app.services import agent_read_tools as art
from app.services import agent_read_tools_analysis as arta
from app.services.agent_executor import AgentExecutor, _truncate_for_display
from main import app

BEIJING_TZ = timezone(timedelta(hours=8))


def _beijing_today():
    return datetime.now(BEIJING_TZ).date()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_user(db) -> User:
    u = User(
        username=f"d1_{uuid.uuid4().hex[:6]}",
        email=f"d1_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="D1 User",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _seed_weight(db, user_id):
    db.add(WeightRecord(user_id=user_id, record_date=date.today(), weight=70.5, source="manual"))
    db.add(
        WeightRecord(
            user_id=user_id, record_date=date.today() - timedelta(days=1), weight=71.0, source="manual"
        )
    )
    db.commit()


class _SpySession:
    """替身 fresh session:reader 被打桩故不真查询,只记录 commit/rollback/close 生命周期。"""

    def __init__(self):
        self.closed = False
        self.rolled_back = False
        self.committed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


# ── shape parity:进程内 reader == 真 route(TestClient)─────────────────────────


def test_weight_parity_via_testclient(db, client):
    user = _make_user(db)
    _seed_weight(db, user.id)
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/weight/records/me?limit=10").json()
    inproc = json.loads(art.read_weight(db, user.id, limit=10))

    assert inproc == http  # 逐字段数据等价(同一 response_model 序列化 + 同一查询)
    assert [r["weight"] for r in inproc] == [70.5, 71.0]  # order by record_date desc


def test_genetic_profile_parity_via_testclient(db, client):
    user = _make_user(db)
    db.add(
        GeneticProfile(
            user_id=user.id, test_provider="WeGene", test_date=date.today(), report_id="R1", notes="档案A"
        )
    )
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/genetic/profiles/me").json()
    inproc = json.loads(art.read_genetic_profiles(db, user.id))

    assert inproc == http
    assert inproc[0]["test_provider"] == "WeGene"


def test_supplement_guide_parity_matches_service(db):
    """补剂指南进程内 reader 与直调 service 数据等价(端点即 service 薄包装)。"""
    from app.services.daily_supplement_guide import get_daily_supplement_guide

    user = _make_user(db)
    direct = get_daily_supplement_guide(db, user.id, None)
    inproc = json.loads(art.read_supplement_daily_guide(db, user.id))
    assert inproc == json.loads(json.dumps(direct, ensure_ascii=False, default=str))


# ── executor 集成(flag True):数据流经 _read_in_process,且不打 HTTP ──────────────


def test_exec_health_query_weight_in_process_no_http(db, monkeypatch):
    user = _make_user(db)
    _seed_weight(db, user.id)
    # 让 _read_in_process 的 SessionLocal 指向测试库(同一 StaticPool 引擎)
    test_sm = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    monkeypatch.setattr("app.database.SessionLocal", test_sm)
    monkeypatch.setattr(settings, "reads_in_process", True, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id

    async def _boom(*a, **k):
        raise AssertionError("进程内路径绝不能打 _api_get")

    ex._api_get = _boom

    out = _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "weight"}))
    parsed = json.loads(out)
    assert [r["weight"] for r in parsed] == [70.5, 71.0]


def test_exec_supplement_guide_in_process_no_http(db, monkeypatch):
    user = _make_user(db)
    test_sm = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    monkeypatch.setattr("app.database.SessionLocal", test_sm)
    monkeypatch.setattr(settings, "reads_in_process", True, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id

    async def _boom(*a, **k):
        raise AssertionError("进程内路径绝不能打 _api_get")

    ex._api_get = _boom

    out = _run(ex._exec_supplement_guide("http://x/api/v1", {}, {}))
    json.loads(out)  # 可解析即证进程内路径走通、未打 HTTP


def test_exec_query_genetic_profile_in_process_no_http(db, monkeypatch):
    user = _make_user(db)
    db.add(GeneticProfile(user_id=user.id, test_provider="WeGene", test_date=date.today()))
    db.commit()
    test_sm = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    monkeypatch.setattr("app.database.SessionLocal", test_sm)
    monkeypatch.setattr(settings, "reads_in_process", True, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id

    async def _boom(*a, **k):
        raise AssertionError("进程内路径绝不能打 _api_get")

    ex._api_get = _boom

    out = _run(ex._exec_query_genetic_profile("http://x/api/v1", {}, {}))
    assert json.loads(out)[0]["test_provider"] == "WeGene"


# ── killswitch:flag False → 旧 HTTP 路径(_api_get 命中)────────────────────────


def test_weight_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get

    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "weight"}))
    assert calls["url"].endswith("/weight/records/me?limit=10")


def test_supplement_guide_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "{}"

    ex._api_get = fake_api_get

    _run(ex._exec_supplement_guide("http://x/api/v1", {}, {}))
    assert calls["url"].endswith("/supplements/daily-guide")


def test_genetic_profile_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get

    _run(ex._exec_query_genetic_profile("http://x/api/v1", {}, {}))
    assert calls["url"].endswith("/genetic/profiles/me")


# ── 会话纪律:fresh SessionLocal,close,不 commit;异常 rollback+close ────────────


def test_read_in_process_fresh_session_closes_no_commit(db, monkeypatch):
    spy = _SpySession()
    monkeypatch.setattr("app.database.SessionLocal", lambda: spy)

    def reader(session):
        assert session is spy  # 收到的是 fresh session,非 self.db
        return "ok"

    ex = AgentExecutor(db)
    ex._current_user_id = 7
    out = _run(ex._read_in_process(reader))

    assert out == "ok"
    assert spy.closed is True
    assert spy.committed is False  # 只读:绝不 commit
    assert spy.rolled_back is False


def test_read_in_process_not_self_db(db, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind()),
    )

    def reader(session):
        captured["db"] = session
        return "ok"

    ex = AgentExecutor(db)
    ex._current_user_id = 7
    _run(ex._read_in_process(reader))
    assert captured["db"] is not ex.db  # fresh session,非执行器事务 session


def test_read_in_process_rollback_and_close_on_error(db, monkeypatch):
    spy = _SpySession()
    monkeypatch.setattr("app.database.SessionLocal", lambda: spy)

    def boom(session):
        raise RuntimeError("reader 炸了")

    ex = AgentExecutor(db)
    ex._current_user_id = 7
    with pytest.raises(RuntimeError):
        _run(ex._read_in_process(boom))

    assert spy.rolled_back is True
    assert spy.closed is True
    assert spy.committed is False


# ── 用户作用域:sensitive 维度 A 永不拿到 B 的数据 ──────────────────────────────


def test_genetic_profile_user_scoping(db):
    a = _make_user(db)
    b = _make_user(db)
    db.add(GeneticProfile(user_id=a.id, test_provider="WeGene", test_date=date.today(), notes="A档案"))
    db.add(GeneticProfile(user_id=b.id, test_provider="23andMe", test_date=date.today(), notes="B机密"))
    db.commit()

    a_out = art.read_genetic_profiles(db, a.id)
    assert "A档案" in a_out
    assert "B机密" not in a_out and "23andMe" not in a_out

    b_out = art.read_genetic_profiles(db, b.id)
    assert "B机密" in b_out
    assert "A档案" not in b_out and "WeGene" not in b_out


def test_weight_user_scoping(db):
    a = _make_user(db)
    b = _make_user(db)
    db.add(WeightRecord(user_id=a.id, record_date=date.today(), weight=60.0, source="manual"))
    db.add(WeightRecord(user_id=b.id, record_date=date.today(), weight=99.9, source="manual"))
    db.commit()

    a_out = json.loads(art.read_weight(db, a.id, limit=10))
    assert [r["weight"] for r in a_out] == [60.0]  # 只见自己的


# ── fail-loud:无 user_id ───────────────────────────────────────────────────────


def test_readers_fail_loud_without_user():
    assert art.read_weight(None, None).startswith("Error")
    assert art.read_genetic_profiles(None, None).startswith("Error")
    assert art.read_supplement_daily_guide(None, None).startswith("Error")


# ── 截断单一真源 ────────────────────────────────────────────────────────────────


def test_truncate_short_passthrough():
    assert _truncate_for_display("短文本") == "短文本"


def test_truncate_long_list_first_10():
    # 每项加 pad 让总长 >3000 才触发 list 截断(短 list 原样返回)。
    big = json.dumps([{"i": i, "pad": "x" * 80} for i in range(50)], ensure_ascii=False)
    assert len(big) > 3000
    out = _truncate_for_display(big)
    assert "仅显示前10条" in out
    assert len(json.loads(out.split("\n")[0])) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# D1 增量 A2:剩余 7 个只读维度进程内直调 golden-master parity + killswitch
# 每维:进程内 reader 输出 == 真 route(TestClient,完整 response_model)输出。
# ═══════════════════════════════════════════════════════════════════════════════


# ── blood_pressure ──────────────────────────────────────────────────────────────


def test_blood_pressure_parity_via_testclient(db, client):
    user = _make_user(db)
    db.add(
        BloodPressureRecord(
            user_id=user.id, record_date=date.today(), systolic=165, diastolic=105, pulse=72
        )
    )
    db.add(
        BloodPressureRecord(
            user_id=user.id,
            record_date=date.today() - timedelta(days=1),
            systolic=118,
            diastolic=76,
            pulse=64,
        )
    )
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/blood-pressure/records/me?limit=10").json()
    inproc = json.loads(art.read_blood_pressure(db, user.id, limit=10))

    assert inproc == http  # 逐字段数据等价(同一 response_model + category 分类)
    assert inproc[0]["category"] == "高血压2级"  # 165/105 order by record_date desc
    assert inproc[1]["category"] == "正常"  # 118/76


def test_blood_pressure_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "blood_pressure"}))
    assert calls["url"].endswith("/blood-pressure/records/me?limit=10")


def test_blood_pressure_user_scoping(db):
    a = _make_user(db)
    b = _make_user(db)
    db.add(BloodPressureRecord(user_id=a.id, record_date=date.today(), systolic=120, diastolic=80))
    db.add(BloodPressureRecord(user_id=b.id, record_date=date.today(), systolic=190, diastolic=120))
    db.commit()

    a_out = json.loads(art.read_blood_pressure(db, a.id, limit=10))
    assert [(r["systolic"], r["diastolic"]) for r in a_out] == [(120, 80)]  # 只见自己的
    b_out = json.loads(art.read_blood_pressure(db, b.id, limit=10))
    assert [(r["systolic"], r["diastolic"]) for r in b_out] == [(190, 120)]


# ── water ────────────────────────────────────────────────────────────────────────


def test_water_parity_via_testclient(db, client):
    user = _make_user(db)
    today = _beijing_today()
    db.add(WaterIntake(user_id=user.id, record_date=today, amount_ml=500, drink_type="水"))
    db.add(WaterIntake(user_id=user.id, record_date=today, amount_ml=300, drink_type="茶"))
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get(f"/api/v1/water/records/me/date/{today.isoformat()}").json()
    inproc = json.loads(art.read_daily_water(db, user.id))

    assert inproc == http
    assert inproc["total_amount"] == 800
    assert inproc["records_count"] == 2


def test_water_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "{}"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "water"}))
    today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    assert calls["url"].endswith(f"/water/records/me/date/{today}")


# ── diet ─────────────────────────────────────────────────────────────────────────


def test_diet_parity_via_testclient(db, client):
    user = _make_user(db)
    today = _beijing_today()
    db.add(
        DietRecord(
            user_id=user.id,
            record_date=today,
            meal_type="breakfast",
            food_items="燕麦",
            calories=300.0,
            protein=10.0,
            carbs=50.0,
            fat=5.0,
            fiber=4.0,
        )
    )
    db.add(
        DietRecord(
            user_id=user.id,
            record_date=today,
            meal_type="lunch",
            food_items="鸡胸肉",
            calories=250.0,
            protein=40.0,
            carbs=2.0,
            fat=6.0,
            fiber=0.0,
        )
    )
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get(f"/api/v1/diet/records/me/date/{today.isoformat()}").json()
    inproc = json.loads(art.read_daily_diet(db, user.id))

    assert inproc == http  # 含 display_message post-init + 宏量四舍五入
    assert inproc["total_calories"] == 550
    assert inproc["meals_count"] == 2


def test_diet_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "{}"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "diet"}))
    today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    assert calls["url"].endswith(f"/diet/records/me/date/{today}")


# ── workout / exercise(两个 dim 都映射到 /workout/me)──────────────────────────────


def test_workout_parity_via_testclient(db, client):
    user = _make_user(db)
    today = date.today()
    db.add(
        WorkoutRecord(
            user_id=user.id,
            workout_date=today,
            workout_type="running",
            workout_name="晨跑",
            duration_seconds=1800,
            distance_meters=5000.0,
            avg_heart_rate=150,
            calories=350,
            feeling="good",
        )
    )
    db.add(
        WorkoutRecord(
            user_id=user.id,
            workout_date=today - timedelta(days=2),
            workout_type="cycling",
            duration_seconds=3600,
            calories=500,
        )
    )
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/workout/me?days=7").json()
    inproc = json.loads(art.read_workouts(db, user.id, days=7))

    assert inproc == http
    assert inproc[0]["workout_type"] == "running"  # order by workout_date desc


def test_exercise_dim_also_uses_workout_reader_no_http(db, monkeypatch):
    """dim='exercise' 与 dim='workout' 同走 read_workouts,进程内不打 HTTP。"""
    user = _make_user(db)
    db.add(
        WorkoutRecord(
            user_id=user.id, workout_date=date.today(), workout_type="hiit", duration_seconds=600
        )
    )
    db.commit()
    test_sm = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    monkeypatch.setattr("app.database.SessionLocal", test_sm)
    monkeypatch.setattr(settings, "reads_in_process", True, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id

    async def _boom(*a, **k):
        raise AssertionError("进程内路径绝不能打 _api_get")

    ex._api_get = _boom
    out = _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "exercise", "days": 7}))
    assert json.loads(out)[0]["workout_type"] == "hiit"


def test_workout_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "workout", "days": 14}))
    assert calls["url"].endswith("/workout/me?days=14")


def test_exercise_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "exercise", "days": 3}))
    assert calls["url"].endswith("/workout/me?days=3")


# ── manual_exercise ──────────────────────────────────────────────────────────────


def test_manual_exercise_parity_via_testclient(db, client):
    user = _make_user(db)
    db.add(
        ExerciseRecord(
            user_id=user.id,
            record_date=date.today(),
            exercise_type="俯卧撑",
            reps=30,
            sets=3,
        )
    )
    db.add(
        ExerciseRecord(
            user_id=user.id,
            record_date=date.today() - timedelta(days=1),
            exercise_type="平板支撑",
            duration_seconds=90,
        )
    )
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/daily-health/exercise/me?days=7").json()
    inproc = json.loads(art.read_manual_exercises(db, user.id, days=7))

    assert inproc == http  # 含 ExerciseRecordResponse.display_message post-init
    assert any("俯卧撑" in r["display_message"] for r in inproc)


def test_manual_exercise_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "manual_exercise", "days": 5}))
    assert calls["url"].endswith("/daily-health/exercise/me?days=5")


# ── events(生活事件时间线)────────────────────────────────────────────────────────


def test_events_parity_via_testclient(db, client):
    user = _make_user(db)
    db.add(
        HealthEpisode(
            user_id=user.id,
            episode_type="life_event",
            source_type="chat",
            occurred_at=datetime.now(timezone.utc) - timedelta(hours=2),
            status="closed",
            risk_level="L0",
            headline="到北京",
            context_snapshot={
                "occurred_precision": "exact",
                "occurred_raw": "14:00",
                "notes": "落地首都机场",
            },
        )
    )
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/episodes/me/life-events?days=7").json()
    inproc = json.loads(art.read_life_events(db, user.id, days=7))

    assert inproc == http
    assert inproc[0]["title"] == "到北京"
    assert inproc[0]["occurred_display"]  # precision_display 非空


def test_events_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "events", "days": 7}))
    assert calls["url"].endswith("/episodes/me/life-events?days=7")


# ── supplements(依从统计,inline list[dict],无 response_model)──────────────────────


def test_supplements_parity_via_testclient(db, client):
    user = _make_user(db)
    supp = SupplementDefinition(
        user_id=user.id, name="维生素D", category="维生素", is_active=True
    )
    db.add(supp)
    db.commit()
    db.refresh(supp)
    # 7 天窗内取 3 天已服用
    for i in range(3):
        db.add(
            SupplementRecord(
                user_id=user.id,
                supplement_id=supp.id,
                record_date=date.today() - timedelta(days=i),
                taken=True,
            )
        )
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/supplements/me/stats?days=7").json()
    inproc = json.loads(art.read_supplement_stats(db, user.id, days=7))

    assert inproc == http  # 逐字段 dict 投影等价
    assert inproc[0]["taken_days"] == 3
    assert inproc[0]["total_days"] == 7
    assert inproc[0]["completion_rate"] == round(3 / 7 * 100, 1)


def test_supplements_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "supplements", "days": 30}))
    assert calls["url"].endswith("/supplements/me/stats?days=30")


# ── fail-loud:新增 reader 无 user_id ────────────────────────────────────────────


def test_new_readers_fail_loud_without_user():
    assert art.read_blood_pressure(None, None).startswith("Error")
    assert art.read_daily_water(None, None).startswith("Error")
    assert art.read_daily_diet(None, None).startswith("Error")
    assert art.read_workouts(None, None).startswith("Error")
    assert art.read_manual_exercises(None, None).startswith("Error")
    assert art.read_life_events(None, None).startswith("Error")
    assert art.read_supplement_stats(None, None).startswith("Error")


# ═══════════════════════════════════════════════════════════════════════════════
# D1 增量 B1:非敏感确定性分析维度进程内直读 golden-master parity + killswitch
# comprehensive/sleep 复用 GarminAnalysisService;spo2 两维复刻 app/api/spo2.py 算法。
# 每维:进程内 reader 输出 == 真 route(TestClient,完整 response_model/dict)输出。
# ═══════════════════════════════════════════════════════════════════════════════


def _seed_garmin_sleep(db, user_id, record_date):
    db.add(
        GarminData(
            user_id=user_id,
            record_date=record_date,
            sleep_score=82,
            total_sleep_duration=480,
            deep_sleep_duration=110,
            rem_sleep_duration=95,
            light_sleep_duration=250,
            awake_duration=25,
            sleep_start_time=time(22, 0),
            sleep_end_time=time(6, 0),
            avg_heart_rate=58,
            resting_heart_rate=50,
            hrv=45.0,
        )
    )
    db.commit()


# ── comprehensive(Garmin 综合分析,无 response_model → dict)───────────────────────


def test_comprehensive_parity_via_testclient(db, client):
    user = _make_user(db)
    _seed_garmin_sleep(db, user.id, date.today())
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/garmin-analysis/me/comprehensive?days=7").json()
    inproc = json.loads(arta.read_comprehensive_analysis(db, user.id, days=7))

    assert inproc == http  # 逐字段数据等价(同一 GarminAnalysisService + daily_data date.isoformat)
    assert inproc["sleep"]["status"] == "success"
    assert set(inproc.keys()) == {"sleep", "heart_rate", "body_battery", "activity", "spo2"}


def test_comprehensive_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "{}"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "comprehensive", "days": 14}))
    assert calls["url"].endswith("/garmin-analysis/me/comprehensive?days=14")


# ── illness(语义病症查询, canonical owner-scoped reader)──────────────────────


def test_illness_query_uses_canonical_reader_without_wearable_http(db):
    user = _make_user(db)
    other = _make_user(db)
    own = IllnessEpisode(
        user_id=user.id,
        name="口腔溃疡",
        start_date=date.today() - timedelta(days=12),
        status="resolved",
        severity=3,
    )
    db.add_all([
        own,
        IllnessEpisode(
            user_id=other.id,
            name="口腔溃疡",
            start_date=date.today() - timedelta(days=1),
            status="active",
            severity=5,
        ),
    ])
    db.commit()
    db.refresh(own)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id

    async def _boom(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("illness canonical query must not call HTTP/wearable endpoints")

    ex._api_get = _boom
    out = _run(ex._exec_health_query(
        "http://x/api/v1",
        {},
        {"dimension": "illness", "days": 183, "keyword": "口腔溃疡"},
    ))
    rows = json.loads(out)

    assert [row["id"] for row in rows] == [own.id]
    assert rows[0]["name"] == "口腔溃疡"
    assert "sleep" not in out.lower()


# ── sleep(Garmin 睡眠质量分析,无 response_model → dict)────────────────────────────


def test_sleep_parity_via_testclient(db, client):
    user = _make_user(db)
    _seed_garmin_sleep(db, user.id, date.today())
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/garmin-analysis/me/sleep?days=7").json()
    inproc = json.loads(arta.read_sleep_analysis(db, user.id, days=7))

    assert inproc == http
    assert inproc["status"] == "success"
    assert inproc["average_sleep_score"] == 82  # round(82, 1)


def test_sleep_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "{}"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "sleep", "days": 30}))
    assert calls["url"].endswith("/garmin-analysis/me/sleep?days=30")


def test_sleep_in_process_no_http(db, monkeypatch):
    """dim='sleep' 走进程内 GarminAnalysisService,零 HTTP。"""
    user = _make_user(db)
    _seed_garmin_sleep(db, user.id, date.today())
    test_sm = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    monkeypatch.setattr("app.database.SessionLocal", test_sm)
    monkeypatch.setattr(settings, "reads_in_process", True, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id

    async def _boom(*a, **k):
        raise AssertionError("进程内路径绝不能打 _api_get")

    ex._api_get = _boom
    out = _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "sleep", "days": 7}))
    assert json.loads(out)["status"] == "success"


# ── spo2 latest-night(response_model=SpO2NightlyResponse)──────────────────────────


def _seed_spo2_night(db, user_id, record_date):
    """一晚采样:14:00 日间点(sleep window 应被过滤)+ 23:00/23:30/02:00 睡眠期点。"""
    for sample_time, epoch_ms, spo2 in [
        (time(14, 0), 1000, 98),  # 日间 → sleep window 过滤掉
        (time(23, 0), 2000, 96),
        (time(23, 30), 3000, 95),
        (time(2, 0), 4000, 93),
    ]:
        db.add(
            SpO2Sample(
                user_id=user_id,
                record_date=record_date,
                sample_time=sample_time,
                spo2_value=spo2,
                epoch_ms=epoch_ms,
            )
        )
    db.commit()


def test_spo2_latest_night_parity_via_testclient(db, client):
    user = _make_user(db)
    # 两个 record_date → 验证 max(record_date) 选夜逻辑与端点一致(都选 today)
    _seed_spo2_night(db, user.id, date.today())
    db.add(
        SpO2Sample(
            user_id=user.id,
            record_date=date.today() - timedelta(days=1),
            sample_time=time(23, 0),
            spo2_value=99,
            epoch_ms=500,
        )
    )
    _seed_garmin_sleep(db, user.id, date.today())  # sleep_start=22:00 sleep_end=06:00 → 跨日窗
    db.commit()
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/spo2/me/latest-night").json()
    inproc = json.loads(arta.read_latest_night_spo2(db, user.id))

    assert inproc == http  # 逐字段数据等价(同一 SpO2NightlyResponse + 选夜 + sleep window)
    assert inproc["record_date"] == date.today().isoformat()  # 选了 today 这一夜
    assert inproc["window"] == "sleep"
    assert inproc["summary"]["data_points"] == 3  # 14:00 日间点被 sleep window 过滤
    assert inproc["summary"]["min_spo2"] == 93
    assert [p["value"] for p in inproc["timeline"]] == [96, 95, 93]  # epoch_ms asc


def test_spo2_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "{}"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "spo2"}))
    assert calls["url"].endswith("/spo2/me/latest-night")  # 无 days 参数


def test_spo2_in_process_no_http(db, monkeypatch):
    user = _make_user(db)
    _seed_spo2_night(db, user.id, date.today())
    test_sm = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    monkeypatch.setattr("app.database.SessionLocal", test_sm)
    monkeypatch.setattr(settings, "reads_in_process", True, raising=False)

    ex = AgentExecutor(db)
    ex._current_user_id = user.id

    async def _boom(*a, **k):
        raise AssertionError("进程内路径绝不能打 _api_get")

    ex._api_get = _boom
    out = _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "spo2"}))
    assert json.loads(out)["record_date"] == date.today().isoformat()


def test_spo2_user_scoping(db):
    a = _make_user(db)
    b = _make_user(db)
    _seed_spo2_night(db, a.id, date.today())
    db.add(
        SpO2Sample(
            user_id=b.id,
            record_date=date.today(),
            sample_time=time(23, 0),
            spo2_value=80,  # B 的低值,A 绝不该看到
            epoch_ms=9999,
        )
    )
    db.commit()

    a_out = json.loads(arta.read_latest_night_spo2(db, a.id))
    assert a_out["summary"]["min_spo2"] == 93  # 只见自己(A 无 80 那条)
    b_out = json.loads(arta.read_latest_night_spo2(db, b.id))
    assert b_out["summary"]["min_spo2"] == 80


# ── spo2 sleep-correlation(response_model=SpO2SleepCorrelationResponse)─────────────


def _seed_spo2_correlation(db, user_id, record_date):
    """一晚:deep/rem/light 三段 + 落在各段内的采样点,用真实 ms 尺度以得到有意义的时长。"""
    base = 1_700_000_000_000
    minute = 60_000
    for start_min, end_min, level in [
        (0, 60, "deep"),
        (60, 90, "rem"),
        (90, 150, "light"),
    ]:
        db.add(
            SleepLevelInterval(
                user_id=user_id,
                record_date=record_date,
                start_epoch_ms=base + start_min * minute,
                end_epoch_ms=base + end_min * minute,
                activity_level=level,
            )
        )
    # sample_time 必须各异(uq_spo2_user_date_time_source);correlation 只用 epoch_ms,
    # sample_time 仅为满足 NOT NULL + 唯一约束,值本身不影响关联结果。
    for offset_min, spo2 in [(10, 95), (20, 94), (70, 90), (75, 88), (100, 96)]:
        db.add(
            SpO2Sample(
                user_id=user_id,
                record_date=record_date,
                sample_time=time(offset_min // 60, offset_min % 60),
                spo2_value=spo2,
                epoch_ms=base + offset_min * minute,
            )
        )
    db.commit()


def test_spo2_sleep_correlation_parity_via_testclient(db, client):
    user = _make_user(db)
    _seed_spo2_correlation(db, user.id, date.today())
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/spo2/me/sleep-correlation?days=7").json()
    inproc = json.loads(arta.read_spo2_sleep_correlation(db, user.id, days=7))

    assert inproc == http  # 逐字段:stages 分段统计 + summary 聚合 + risk 分类 + disclaimer
    assert inproc["days"] == 7
    assert len(inproc["nights"]) == 1
    assert inproc["summary"]["nights_analyzed"] == 1
    stages = {s["stage"]: s for s in inproc["nights"][0]["stages"]}
    assert stages["deep"]["data_points"] == 2  # 落在 deep 段的两点
    assert stages["rem"]["data_points"] == 2
    assert stages["light"]["data_points"] == 1


def test_spo2_sleep_correlation_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "{}"

    ex._api_get = fake_api_get
    _run(
        ex._exec_health_query(
            "http://x/api/v1", {}, {"dimension": "spo2_sleep_correlation", "days": 14}
        )
    )
    assert calls["url"].endswith("/spo2/me/sleep-correlation?days=14")


def test_spo2_sleep_correlation_empty_parity(db, client):
    """无采样时 route 返回 nights=[] summary=None;reader 数据等价(非 Error,是合法空结构)。"""
    user = _make_user(db)
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/spo2/me/sleep-correlation?days=7").json()
    inproc = json.loads(arta.read_spo2_sleep_correlation(db, user.id, days=7))

    assert inproc == http
    assert inproc["nights"] == [] and inproc["summary"] is None


# ── fail-loud:分析维度 reader 无 user_id ─────────────────────────────────────────


def test_analysis_readers_fail_loud_without_user():
    assert arta.read_comprehensive_analysis(None, None).startswith("Error")
    assert arta.read_sleep_analysis(None, None).startswith("Error")
    assert arta.read_latest_night_spo2(None, None).startswith("Error")
    assert arta.read_spo2_sleep_correlation(None, None).startswith("Error")


# ── 增量 B2: genetic 变异位点(Tier-5 敏感)────────────────────────────────────────


def _seed_genetic(db, user, *, gene, genotype, category="drug_sensitivity"):
    profile = GeneticProfile(user_id=user.id, test_provider="WeGene", test_date=date.today())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.add(
        GeneticVariant(
            user_id=user.id, profile_id=profile.id, category=category, gene_name=gene,
            rsid="rs1801133", genotype=genotype, raw_genotype=genotype, result_label="示例",
        )
    )
    db.commit()
    return profile


def test_genetic_variants_parity_via_testclient(db, client):
    user = _make_user(db)
    _seed_genetic(db, user, gene="MTHFR", genotype="CT")
    app.dependency_overrides[get_current_user_required] = lambda: user

    http = client.get("/api/v1/genetic/variants/me").json()
    inproc = json.loads(art.read_genetic_variants(db, user.id))

    assert inproc == http  # 14 字段逐字段数据等价(含解密后的 genotype)
    assert inproc[0]["gene_name"] == "MTHFR"
    assert inproc[0]["genotype"] == "CT"


def test_genetic_variants_killswitch_false_uses_http(db, monkeypatch):
    user = _make_user(db)
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    calls = {}

    async def fake_api_get(url, headers):
        calls["url"] = url
        return "[]"

    ex._api_get = fake_api_get
    _run(ex._exec_health_query("http://x/api/v1", {}, {"dimension": "genetic"}))
    assert calls["url"].endswith("/genetic/variants/me")


def test_genetic_variants_user_scoping_no_cross_user_genotype_leak(db):
    """Tier-5 硬隔离:A 的会话绝不可能拿到 B 的变异/基因型(最敏感字段)。"""
    a = _make_user(db)
    b = _make_user(db)
    _seed_genetic(db, a, gene="MTHFR", genotype="AA_secret_A")
    _seed_genetic(db, b, gene="APOE", genotype="ZZ_secret_B")

    a_out = art.read_genetic_variants(db, a.id)
    assert "AA_secret_A" in a_out and "MTHFR" in a_out
    assert "ZZ_secret_B" not in a_out and "APOE" not in a_out  # B 的基因型绝不泄漏给 A

    b_out = art.read_genetic_variants(db, b.id)
    assert "ZZ_secret_B" in b_out
    assert "AA_secret_A" not in b_out and "MTHFR" not in b_out


def test_genetic_variants_indicator_filters_by_gene(db):
    user = _make_user(db)
    profile = GeneticProfile(user_id=user.id, test_provider="WeGene", test_date=date.today())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.add_all([
        GeneticVariant(user_id=user.id, profile_id=profile.id, category="drug_sensitivity",
                       gene_name="MTHFR", rsid="rs1", genotype="CT"),
        GeneticVariant(user_id=user.id, profile_id=profile.id, category="nutrition",
                       gene_name="APOE", rsid="rs2", genotype="E3"),
    ])
    db.commit()

    out = json.loads(art.read_genetic_variants(db, user.id, indicator="MTHFR"))
    assert [v["gene_name"] for v in out] == ["MTHFR"]  # 命中项只返回 MTHFR


def test_genetic_variants_fail_loud_without_user():
    assert art.read_genetic_variants(None, None).startswith("Error")
