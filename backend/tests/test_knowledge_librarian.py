"""KnowledgeLibrarian specialist 单元测试.

覆盖:
- applies_to 关键字 / general fallback
- run() 空 query 降级
- run() search_knowledge 返回空时的降级 summary
- run() 有结果时的 finding 结构 (relevance 计算 / 文本截断)
- run() search_knowledge 抛异常时 catch
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pytest

from app.agents.knowledge_librarian.librarian import KnowledgeLibrarianSpecialist
from app.orchestrator.intent import classify_intent
from app.orchestrator.schema import SpecialistFinding
from app.twin.schema import HealthTwin, TwinMeta


def _empty_twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


# ───────────────────────── applies_to ─────────────────────────


class TestAppliesTo:
    def test_applies_on_what_is_keyword(self):
        s = KnowledgeLibrarianSpecialist()
        intent = classify_intent("什么是 MTHFR 基因")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_applies_on_why_keyword(self):
        s = KnowledgeLibrarianSpecialist()
        intent = classify_intent("为什么我 HRV 这么低")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_applies_on_mechanism_keyword(self):
        s = KnowledgeLibrarianSpecialist()
        intent = classify_intent("解释下胰岛素抵抗的机制")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_applies_on_knowledge_english(self):
        s = KnowledgeLibrarianSpecialist()
        intent = classify_intent("search wiki about metformin")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_applies_on_general_fallback(self):
        """无 trigger keyword 但 general intent 也参与 (证据背书)."""
        s = KnowledgeLibrarianSpecialist()
        intent = classify_intent("今天身体如何")
        if "general" in intent.categories:
            assert s.applies_to(intent, _empty_twin()) is True


# ───────────────────────── run() 降级 ─────────────────────────


class TestRunDegraded:
    def test_empty_query_returns_degraded(self):
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={})  # 无 query
        assert isinstance(finding, SpecialistFinding)
        assert finding.summary == "无查询内容"
        assert finding.findings == []

    def test_empty_results_returns_hint(self, monkeypatch):
        """search_knowledge 返回空数组时, summary 提示可能需先建索引."""
        monkeypatch.setattr(
            "app.agents.knowledge_librarian.indexer.search_knowledge",
            lambda q, n_results=5: [],
        )
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})
        assert finding.findings == []
        assert "索引" in finding.summary
        assert finding.raw["results_count"] == 0

    def test_search_exception_caught(self, monkeypatch):
        """search_knowledge 抛异常 → catch, 不上抛."""
        def _boom(q, n_results=5):
            raise RuntimeError("chromadb 坏了")

        monkeypatch.setattr(
            "app.agents.knowledge_librarian.indexer.search_knowledge",
            _boom,
        )
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})
        assert "失败" in finding.summary
        assert finding.findings == []
        assert "error" in finding.raw


# ───────────────────────── run() 正常路径 ─────────────────────────


class TestRunHappyPath:
    @pytest.fixture
    def stub_results(self) -> List[Dict[str, Any]]:
        return [
            {
                "title": "MTHFR 基因解读",
                "source": "得到 wiki: 精准营养",
                "text": "MTHFR 编码亚甲基四氢叶酸还原酶..." * 30,  # 大于 500 字符
                "distance": 0.1,
            },
            {
                "title": "叶酸代谢",
                "source": "得到 wiki: 营养科学",
                "text": "叶酸是一种 B 族维生素",
                "distance": 0.3,
            },
        ]

    def _patch_search(self, monkeypatch, stub_results):
        monkeypatch.setattr(
            "app.agents.knowledge_librarian.indexer.search_knowledge",
            lambda q, n_results=5: stub_results,
        )

    def test_findings_have_correct_structure(self, monkeypatch, stub_results):
        self._patch_search(monkeypatch, stub_results)
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})

        assert len(finding.findings) == 2
        first = finding.findings[0]
        assert first["type"] == "knowledge_reference"
        assert first["order"] == 1
        assert first["title"] == "MTHFR 基因解读"
        assert first["source"] == "得到 wiki: 精准营养"

    def test_text_truncated_at_500(self, monkeypatch, stub_results):
        self._patch_search(monkeypatch, stub_results)
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})
        # 第一条原文 > 500 字, 必须截断
        assert len(finding.findings[0]["text"]) == 500

    def test_relevance_inverse_of_distance(self, monkeypatch, stub_results):
        self._patch_search(monkeypatch, stub_results)
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})
        # distance=0.1 → relevance 0.9; distance=0.3 → 0.7
        assert finding.findings[0]["relevance"] == pytest.approx(0.9)
        assert finding.findings[1]["relevance"] == pytest.approx(0.7)

    def test_relevance_defaults_when_no_distance(self, monkeypatch):
        self._patch_search(monkeypatch, [{"title": "x", "source": "y", "text": "z"}])
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "q"})
        # 没 distance 时默认 0.5 → relevance 0.5
        assert finding.findings[0]["relevance"] == pytest.approx(0.5)

    def test_raw_has_top_source(self, monkeypatch, stub_results):
        self._patch_search(monkeypatch, stub_results)
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})
        assert finding.raw["top_source"] == "得到 wiki: 精准营养"
        assert finding.raw["results_count"] == 2
        assert finding.raw["query"] == "MTHFR"

    def test_summary_reports_count(self, monkeypatch, stub_results):
        self._patch_search(monkeypatch, stub_results)
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})
        assert "2 条" in finding.summary
        assert "得到 wiki" in finding.summary

    def test_ms_elapsed_populated(self, monkeypatch, stub_results):
        self._patch_search(monkeypatch, stub_results)
        s = KnowledgeLibrarianSpecialist()
        finding = s.run(_empty_twin(), context={"query": "MTHFR"})
        assert finding.ms_elapsed is not None
        assert finding.ms_elapsed >= 0
