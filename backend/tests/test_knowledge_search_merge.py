"""knowledge_search 工具合并两路知识库 (已审定 System KB v2 + 得到 wiki)。

钉:
  - 两路都有命中 → 两个区块标题都出现, 各自内容都在。
  - 仅 System KB 命中 → 只出现 reviewed 区块 (得到挂了不影响)。
  - 仅得到命中 → 只出现 wiki 区块 (System KB 挂了不影响)。
  - 两路全空 + 得到不可用 → 诚实「检索失败…勿编造依据」。
  - 两路全空 + 得到可用 → 诚实「未命中…勿编造引用」。
"""
import app.services.agent_executor as ae
import app.services.system_knowledge_service as sks
import app.agents.knowledge_librarian.indexer as indexer

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

_DEDAO_RESULTS = [
    {"text": "得到 wiki 关于 B12 的科普片段。", "title": "B12 科普", "source": "dedao"},
]


def _make_executor(db):
    return ae.AgentExecutor(db)


def _patch_kb(monkeypatch, payload):
    monkeypatch.setattr(sks, "search_knowledge", lambda db, query, **kw: payload)


def _patch_dedao(monkeypatch, results):
    monkeypatch.setattr(indexer, "search_knowledge", lambda query, n_results=5: results)


async def test_both_sources_merged(db, monkeypatch):
    _patch_kb(monkeypatch, _KB_PAYLOAD)
    _patch_dedao(monkeypatch, _DEDAO_RESULTS)
    out = await _make_executor(db)._exec_knowledge_search({"query": "二甲双胍 B12"})
    assert REVIEWED_HEADER in out
    assert WIKI_HEADER in out
    assert "二甲双胍可能降低维生素B12" in out
    assert "得到 wiki 关于 B12" in out
    assert "证据等级 A" in out
    # reviewed 区块明确标注「通用结论, 非个性化」+ 不替代医生
    assert "非针对当前用户的个性化判断" in out
    assert "不替代医生" in out
    # I2: 主题召回适用性 caveat —— 不符则以 Twin evidence card 为准并忽略本条
    assert "未经『是否适用于本用户』判定" in out
    assert "以 Twin evidence card 为准并忽略本条" in out


async def test_only_system_kb_when_dedao_empty(db, monkeypatch):
    _patch_kb(monkeypatch, _KB_PAYLOAD)
    _patch_dedao(monkeypatch, [])
    out = await _make_executor(db)._exec_knowledge_search({"query": "二甲双胍"})
    assert REVIEWED_HEADER in out
    assert WIKI_HEADER not in out


async def test_only_dedao_when_kb_empty(db, monkeypatch):
    _patch_kb(monkeypatch, {"results": []})
    _patch_dedao(monkeypatch, _DEDAO_RESULTS)
    out = await _make_executor(db)._exec_knowledge_search({"query": "B12"})
    assert WIKI_HEADER in out
    assert REVIEWED_HEADER not in out


async def test_one_source_crash_does_not_kill_tool(db, monkeypatch):
    """System KB 抛异常 → 仍返回 dedao 区块 (fail-honest, 不崩)。"""
    def _boom(db, query, **kw):
        raise RuntimeError("kb down")
    monkeypatch.setattr(sks, "search_knowledge", _boom)
    _patch_dedao(monkeypatch, _DEDAO_RESULTS)
    out = await _make_executor(db)._exec_knowledge_search({"query": "B12"})
    assert WIKI_HEADER in out
    assert REVIEWED_HEADER not in out


async def test_both_empty_and_unavailable_returns_honest_failure(db, monkeypatch):
    _patch_kb(monkeypatch, {"results": []})
    _patch_dedao(monkeypatch, [])
    # dedao 探测不可用
    monkeypatch.setattr(indexer, "_get_collection", lambda: None)
    out = await _make_executor(db)._exec_knowledge_search({"query": "无此主题"})
    assert "检索失败" in out and "勿编造依据" in out
    assert REVIEWED_HEADER not in out and WIKI_HEADER not in out


async def test_both_empty_but_available_returns_honest_miss(db, monkeypatch):
    _patch_kb(monkeypatch, {"results": []})
    _patch_dedao(monkeypatch, [])

    class _Coll:
        def count(self):
            return 42

    monkeypatch.setattr(indexer, "_get_collection", lambda: _Coll())
    out = await _make_executor(db)._exec_knowledge_search({"query": "无此主题"})
    assert "未命中" in out and "勿编造引用" in out
    assert REVIEWED_HEADER not in out and WIKI_HEADER not in out


async def test_empty_query_errors(db):
    out = await _make_executor(db)._exec_knowledge_search({"query": "  "})
    assert out.startswith("Error:")


async def test_knowledge_search_scrubs_direct_identifiers_before_both_retrievers(db, monkeypatch):
    seen = {}

    def _kb(db, query, **kw):
        seen["kb"] = query
        return {"results": []}

    def _dedao(query, n_results=5):
        seen["dedao"] = query
        return _DEDAO_RESULTS

    monkeypatch.setattr(sks, "search_knowledge", _kb)
    monkeypatch.setattr(indexer, "search_knowledge", _dedao)

    out = await _make_executor(db)._exec_knowledge_search({
        "query": "LDL 13800138000 alice@example.com",
    })

    assert WIKI_HEADER in out
    assert seen == {
        "kb": "LDL [PHONE] [EMAIL]",
        "dedao": "LDL [PHONE] [EMAIL]",
    }
    assert "13800138000" not in out
    assert "alice@example.com" not in out
