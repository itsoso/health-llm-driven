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
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_required
from app.config import settings
from app.models.genetic_data import GeneticProfile
from app.models.user import User
from app.models.weight import WeightRecord
from app.services import agent_read_tools as art
from app.services.agent_executor import AgentExecutor, _truncate_for_display
from main import app


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
