"""Reviewed-only runtime boundary for the common ``knowledge_search`` tool.

Dedao material can participate in an offline authoring/review pipeline, but raw
Dedao/Chroma snippets are not runtime medical evidence and must never be used as a
fallback when the reviewed System KB misses or is unavailable.
"""

import app.agents.knowledge_librarian.indexer as indexer
import app.services.agent_executor as ae
import app.services.system_knowledge_service as sks


REVIEWED_HEADER = "【已审定知识库(owner-reviewed,通用结论,需结合个人情况,非诊断)】"
WIKI_HEADER = "【得到医学wiki 检索片段(仅供参考)】"

_KB_PAYLOAD = {
    "results": [
        {
            "score": 0.9,
            "document": {
                "doc_id": "claim_001",
                "doc_type": "claim",
                "title": "二甲双胍与维生素B12",
                "summary": "长期服用二甲双胍可能降低维生素B12水平,建议定期监测。",
                "body": "更长的正文……",
                "evidence_level": "A",
            },
            "retrieval": {},
        }
    ],
}


def _make_executor(db):
    return ae.AgentExecutor(db)


def _patch_kb(monkeypatch, payload):
    monkeypatch.setattr(sks, "search_knowledge", lambda db, query, **kw: payload)


def _forbid_raw_dedao(monkeypatch):
    def _called(*args, **kwargs):
        raise AssertionError("raw Dedao runtime retriever must not be called")

    monkeypatch.setattr(indexer, "search_knowledge", _called)
    monkeypatch.setattr(indexer, "_get_collection", _called)


async def test_reviewed_system_kb_is_the_only_runtime_source(db, monkeypatch):
    _patch_kb(monkeypatch, _KB_PAYLOAD)
    _forbid_raw_dedao(monkeypatch)

    out = await _make_executor(db)._exec_knowledge_search({"query": "二甲双胍 B12"})

    assert REVIEWED_HEADER in out
    assert WIKI_HEADER not in out
    assert "二甲双胍可能降低维生素B12" in out
    assert "证据等级 A" in out
    assert "非针对当前用户的个性化判断" in out
    assert "不替代医生" in out
    assert "未经『是否适用于本用户』判定" in out
    assert "以 Twin evidence card 为准并忽略本条" in out


async def test_reviewed_miss_never_falls_back_to_raw_dedao(db, monkeypatch):
    _patch_kb(monkeypatch, {"results": []})
    _forbid_raw_dedao(monkeypatch)

    out = await _make_executor(db)._exec_knowledge_search({"query": "无此主题"})

    assert "已审定知识库未命中" in out
    assert "勿编造引用" in out
    assert REVIEWED_HEADER not in out
    assert WIKI_HEADER not in out


async def test_reviewed_kb_failure_is_fail_honest_without_raw_fallback(db, monkeypatch):
    def _boom(db, query, **kw):
        raise RuntimeError("kb down")

    monkeypatch.setattr(sks, "search_knowledge", _boom)
    _forbid_raw_dedao(monkeypatch)

    out = await _make_executor(db)._exec_knowledge_search({"query": "B12"})

    assert "已审定知识库检索失败" in out
    assert "勿编造依据" in out
    assert REVIEWED_HEADER not in out
    assert WIKI_HEADER not in out


async def test_empty_query_errors(db):
    out = await _make_executor(db)._exec_knowledge_search({"query": "  "})
    assert out.startswith("Error:")


async def test_knowledge_search_scrubs_direct_identifiers_before_reviewed_retrieval(
    db,
    monkeypatch,
):
    seen = {}

    def _kb(db, query, **kw):
        seen["kb"] = query
        return {"results": []}

    monkeypatch.setattr(sks, "search_knowledge", _kb)
    _forbid_raw_dedao(monkeypatch)

    out = await _make_executor(db)._exec_knowledge_search({
        "query": "LDL 13800138000 alice@example.com",
    })

    assert seen == {"kb": "LDL [PHONE] [EMAIL]"}
    assert "13800138000" not in out
    assert "alice@example.com" not in out


async def test_result_count_is_bounded_for_reviewed_retrieval(db, monkeypatch):
    seen = {}

    def _kb(db, query, **kw):
        seen["limit"] = kw["limit"]
        return {"results": []}

    monkeypatch.setattr(sks, "search_knowledge", _kb)
    _forbid_raw_dedao(monkeypatch)

    await _make_executor(db)._exec_knowledge_search({"query": "B12", "n_results": 100})

    assert seen["limit"] == 8


async def test_invalid_result_count_uses_reviewed_default(db, monkeypatch):
    seen = {}

    def _kb(db, query, **kw):
        seen["limit"] = kw["limit"]
        return {"results": []}

    monkeypatch.setattr(sks, "search_knowledge", _kb)
    _forbid_raw_dedao(monkeypatch)

    await _make_executor(db)._exec_knowledge_search({
        "query": "B12",
        "n_results": "invalid",
    })

    assert seen["limit"] == 5
