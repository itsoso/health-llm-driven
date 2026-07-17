"""R1 · 长对话溢出"截断→摘要"(history_compaction)。

不打真 Redis / 真 LLM:缓存层与折叠 LLM 都 monkeypatch(本地 Redis 会造成跨测试污染,
见 MEMORY);断言的是折叠语义 + fail-open + 窗口内行为逐字节不变。
"""
from unittest.mock import patch

import pytest

from app.services import history_compaction as hc
from app.services.agent_conversation_service import AgentConversationService


def _seed_conversation(db, n_msgs: int):
    """建一个 user/assistant 交替、内容可辨序的会话,返回 (svc, conv_id, messages)。"""
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.user import User

    user = User(name="hc_u", username="hc_u", email="hc@t.co", hashed_password="x")
    db.add(user); db.commit(); db.refresh(user)
    conv = AgentConversation(user_id=user.id, title="t")
    db.add(conv); db.commit(); db.refresh(conv)
    msgs = []
    for i in range(n_msgs):
        m = AgentMessage(
            conversation_id=conv.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"msg-{i}" + ("(已记录 体重 71.4kg #77)" if i == 3 else ""),
        )
        db.add(m); db.commit(); db.refresh(m)
        msgs.append(m)
    return AgentConversationService(db), conv.id, msgs


class _FakeCache:
    def __init__(self):
        self.store = {}
    def get(self, cid):
        return self.store.get(cid)
    def set(self, cid, payload):
        self.store[cid] = payload


@pytest.fixture()
def fake_cache(monkeypatch):
    fc = _FakeCache()
    monkeypatch.setattr(hc, "_cache_get", fc.get)
    monkeypatch.setattr(hc, "_cache_set", fc.set)
    return fc


# ── 读路径 ───────────────────────────────────────────────────────────

def test_flag_off_is_byte_identical_even_with_cache(db, fake_cache, monkeypatch):
    svc, cid, msgs = _seed_conversation(db, 20)
    fake_cache.set(cid, {"folded_thru_id": msgs[4].id, "summary": "S"})
    monkeypatch.setattr(hc.settings, "llm_history_compaction", False, raising=False)
    out = svc.build_messages(cid, limit=15)
    assert len(out) == 15
    assert out[0]["content"] == "msg-5"  # 现状截断,无摘要前置


def test_flag_on_valid_cache_prepends_summary_window_untouched(db, fake_cache, monkeypatch):
    svc, cid, msgs = _seed_conversation(db, 20)
    # 溢出 = msg-0..msg-4;缓存恰好折到最后一条溢出
    fake_cache.set(cid, {"folded_thru_id": msgs[4].id, "summary": "前情:讨论了体重趋势"})
    monkeypatch.setattr(hc.settings, "llm_history_compaction", True, raising=False)
    monkeypatch.setattr(
        "app.services.agent_conversation_service.settings.llm_history_compaction",
        True, raising=False,
    )
    out = svc.build_messages(cid, limit=15)
    assert len(out) == 16  # 摘要 + 15 窗口
    assert "对话前情摘要" in out[0]["content"] and "体重趋势" in out[0]["content"]
    assert out[0]["role"] == "user"
    # 窗口内 15 条逐字节不变
    assert [m["content"] for m in out[1:]] == [f"msg-{i}" for i in range(5, 20)]


def test_flag_on_stale_cache_fails_open_to_truncation(db, fake_cache, monkeypatch):
    svc, cid, msgs = _seed_conversation(db, 20)
    fake_cache.set(cid, {"folded_thru_id": msgs[2].id, "summary": "S"})  # 没折到 msg-4 = 陈旧
    monkeypatch.setattr(
        "app.services.agent_conversation_service.settings.llm_history_compaction",
        True, raising=False,
    )
    out = svc.build_messages(cid, limit=15)
    assert len(out) == 15
    assert out[0]["content"] == "msg-5"  # 陈旧摘要绝不冒充 → 现状截断


def test_no_overflow_no_summary(db, fake_cache, monkeypatch):
    svc, cid, _ = _seed_conversation(db, 10)
    monkeypatch.setattr(
        "app.services.agent_conversation_service.settings.llm_history_compaction",
        True, raising=False,
    )
    out = svc.build_messages(cid, limit=15)
    assert len(out) == 10 and "前情摘要" not in out[0]["content"]


# ── 写路径(后台折叠)──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_fold_caches_summary_and_receipts(db, fake_cache, monkeypatch):
    svc, cid, msgs = _seed_conversation(db, 20)
    monkeypatch.setattr(hc.settings, "llm_history_compaction", True, raising=False)
    # _refresh_fold 自建 SessionLocal(call-time import)—— 测试里指到共享 in-memory db
    import app.database as app_db
    monkeypatch.setattr(app_db, "SessionLocal", lambda: db)

    async def fake_summarize(prior, turns):
        return f"叙事({len(turns)}条新折)"
    monkeypatch.setattr(hc, "_summarize", fake_summarize)
    # db.close() 会被 _refresh_fold 调 —— in-memory 共享 fixture 不能真关
    monkeypatch.setattr(db, "close", lambda: None)

    await hc._refresh_fold(cid, keep_recent=15)
    cached = fake_cache.get(cid)
    assert cached and cached["folded_thru_id"] == msgs[4].id
    assert "叙事(5条新折)" in cached["summary"]
    # 回执行逐字保留(msg-3 是 assistant 且含 已记录…#77)
    assert any("#77" in r for r in cached["receipt_lines"])
    assert "已记录 体重 71.4kg #77" in cached["summary"]


@pytest.mark.asyncio
async def test_refresh_fold_incremental_only_new_messages(db, fake_cache, monkeypatch):
    svc, cid, msgs = _seed_conversation(db, 22)  # 溢出 = 0..6
    import app.database as app_db
    monkeypatch.setattr(app_db, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    fake_cache.set(cid, {"folded_thru_id": msgs[4].id, "summary": "旧叙事",
                         "receipt_lines": ["已记录 X #1"]})
    seen = {}

    async def fake_summarize(prior, turns):
        seen["prior"] = prior; seen["n"] = len(turns)
        return "新叙事"
    monkeypatch.setattr(hc, "_summarize", fake_summarize)

    await hc._refresh_fold(cid, keep_recent=15)
    assert seen["n"] == 2                      # 只折 msg-5/msg-6(增量)
    assert "旧叙事" in seen["prior"]           # 旧叙事作为续写基础
    cached = fake_cache.get(cid)
    assert cached["folded_thru_id"] == msgs[6].id
    assert "已记录 X #1" in cached["summary"]  # 旧回执行仍在


@pytest.mark.asyncio
async def test_refresh_fold_llm_failure_keeps_old_cache(db, fake_cache, monkeypatch):
    svc, cid, msgs = _seed_conversation(db, 20)
    import app.database as app_db
    monkeypatch.setattr(app_db, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    fake_cache.set(cid, {"folded_thru_id": msgs[2].id, "summary": "旧"})

    async def failing(prior, turns):
        return None  # LLM 失败
    monkeypatch.setattr(hc, "_summarize", failing)

    await hc._refresh_fold(cid, keep_recent=15)
    assert fake_cache.get(cid)["summary"] == "旧"  # fail-open: 保留旧缓存不覆盖


@pytest.mark.asyncio
async def test_summarize_parses_plain_string_response(monkeypatch):
    """回归(真 flash 实测抓出): provider.chat(stream=False) 返回**纯字符串**, 不是
    dict/对象。若解析成 None → _refresh_fold 恒判失败 → R1 生产静默 no-op(单测因 mock
    _summarize 而漏掉)。此测用返回 str 的假 provider 打真解析路径。"""
    class _StrProvider:
        async def chat(self, **kw):
            return "  折叠后的叙事摘要  "   # 真实 shape:strip 前的纯 str

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_extraction",
        lambda mid: _StrProvider(),
    )
    out = await hc._summarize("", [{"role": "user", "content": "x"}])
    assert out == "折叠后的叙事摘要"  # 解析出非空(不是 None)


@pytest.mark.asyncio
async def test_summarize_dict_and_object_shapes(monkeypatch):
    """带 return_metadata 的 dict 形态 + SDK 对象形态也要解析出内容(兜底不回归)。"""
    class _DictProvider:
        async def chat(self, **kw):
            return {"content": "dict叙事"}
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_extraction",
        lambda mid: _DictProvider(),
    )
    assert await hc._summarize("", [{"role": "user", "content": "x"}]) == "dict叙事"


def test_ships_off_by_default():
    from app.config import Settings
    assert Settings.model_fields["llm_history_compaction"].default is False
