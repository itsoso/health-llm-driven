"""realtime_search 工具 — chat/体检分析路径的最新指南/时效事实接地 (阿里云 IQS)。

钉:
  - fetch_realtime_evidence 返回 block → 工具带前缀返回该 block。
  - 返回 "" (未启用/无命中) → 诚实「未返回结果…勿编造引用」。
  - 抛异常 → fail-honest「暂不可用…勿编造依据」。
  - 空 query → Error。
  - HEALTH_KEYWORDS 已补全器官/血液学词 (肝 / 血常规)。

隐私: 工具只把模型给的 query 传给 IQS, 绝不注入 Twin/PII。
"""
import app.services.agent_executor as ae
import app.services.iqs_search as iqs_search
import app.agents.knowledge_librarian.indexer as indexer

PREFIX = "以下为实时联网检索结果"


def _make_executor(db):
    return ae.AgentExecutor(db)


def _patch_iqs(monkeypatch, fn):
    monkeypatch.setattr(iqs_search, "fetch_realtime_evidence", fn)


async def test_block_returned_with_prefix(db, monkeypatch):
    block = "【实时检索证据 · 关于「2024 高血压指南」· 共2条】\n[1] ……"

    async def _fake(query, **kw):
        return block

    _patch_iqs(monkeypatch, _fake)
    out = await _make_executor(db)._exec_realtime_search({"query": "2024 高血压指南"})
    assert PREFIX in out
    assert "不替代医生" in out
    assert block in out


async def test_empty_block_returns_honest_miss(db, monkeypatch):
    async def _fake(query, **kw):
        return ""

    _patch_iqs(monkeypatch, _fake)
    out = await _make_executor(db)._exec_realtime_search({"query": "无此主题"})
    assert "未返回结果" in out
    assert "勿编造引用" in out
    assert PREFIX not in out


async def test_exception_fails_honest(db, monkeypatch):
    seen = {}

    async def _boom(query, **kw):
        seen.update(kw)
        raise iqs_search.RealtimeSearchUnavailable("upstream_error")

    _patch_iqs(monkeypatch, _boom)
    out = await _make_executor(db)._exec_realtime_search({"query": "高血压"})
    assert seen["raise_on_unavailable"] is True
    assert out.startswith("Error:")
    assert "暂不可用" in out
    assert "勿编造依据" in out
    assert PREFIX not in out


async def test_empty_query_errors(db):
    out = await _make_executor(db)._exec_realtime_search({"query": "  "})
    assert out.startswith("Error:")


def test_health_keywords_expanded():
    assert "肝" in indexer.HEALTH_KEYWORDS
    assert "血常规" in indexer.HEALTH_KEYWORDS
    assert indexer._is_health_related("肝功能检查")
    assert indexer._is_health_related("血常规分析")
