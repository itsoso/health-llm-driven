"""Hybrid Search (BM25 + Graph + RRF) 测试."""
import pytest

from app.services.hybrid_search import (
    _build_user_corpus, _tokenize, MiniBM25, Doc, reciprocal_rank_fusion,
    hybrid_retrieve, render_hits_for_prompt,
)


# ─────────── 分词 ───────────


class TestTokenize:
    def test_ascii_split(self):
        ts = _tokenize("LDL above 3.4 mmol/L")
        # ASCII 词不再 ngram
        assert "ldl" in ts
        assert "above" in ts
        assert "mmol" in ts

    def test_chinese_chars_and_ngrams(self):
        ts = _tokenize("美托洛尔治疗高血压")
        # char
        assert "美" in ts
        assert "压" in ts
        # 2-gram
        assert "美托" in ts
        assert "高血" in ts
        # 3-gram
        assert "美托洛" in ts
        assert "高血压" in ts

    def test_empty_handles(self):
        assert _tokenize("") == []
        assert _tokenize("   ") == []

    def test_mixed(self):
        ts = _tokenize("LDL 3.4 高血压")
        assert "ldl" in ts
        assert "3" in ts
        assert "高血" in ts


# ─────────── BM25 ───────────


class TestMiniBM25:
    def _docs(self):
        return [
            Doc(id="d1", source_type="fact", source_id=1,
                text="美托洛尔治疗高血压 stage1",
                tokens=_tokenize("美托洛尔治疗高血压 stage1"),
                metadata={"confidence": 0.8}),
            Doc(id="d2", source_type="fact", source_id=2,
                text="LDL 4.2 高于参考",
                tokens=_tokenize("LDL 4.2 高于参考"),
                metadata={"confidence": 0.9}),
            Doc(id="d3", source_type="entity", source_id=10,
                text="鼻炎 allergic_rhinitis",
                tokens=_tokenize("鼻炎 allergic_rhinitis"),
                metadata={"confidence": 0.7}),
        ]

    def test_relevant_doc_top1(self):
        bm = MiniBM25(self._docs())
        hits = bm.search("美托洛尔", top_k=3)
        assert hits
        assert hits[0][0].id == "d1"

    def test_chinese_partial_match(self):
        bm = MiniBM25(self._docs())
        hits = bm.search("高血压怎么办", top_k=3)
        assert hits
        assert hits[0][0].id == "d1"

    def test_no_match_empty(self):
        bm = MiniBM25(self._docs())
        hits = bm.search("today's weather", top_k=3)
        # ASCII 单词不在 corpus
        assert hits == []

    def test_empty_corpus(self):
        bm = MiniBM25([])
        assert bm.search("anything") == []


# ─────────── RRF ───────────


class TestRRF:
    def test_basic_fusion(self):
        # BM25 ranks: d1, d2, d3
        # Graph ranks: d2, d3
        bm25 = [("d1", 5.0), ("d2", 3.0), ("d3", 1.0)]
        graph = [("d2", 0.9), ("d3", 0.5)]
        out = reciprocal_rank_fusion([bm25, graph])
        scores = dict(out)
        # d2 在两路都靠前 (BM25 #2, graph #1) → 总分应比 d1 (BM25 #1 only) 高
        assert scores["d2"] > scores["d1"]
        assert scores["d2"] > scores["d3"]

    def test_empty_input(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[]]) == []


# ─────────── 端到端 hybrid_retrieve ───────────


class TestHybridRetrieve:
    def _seed(self, db, user_id=1):
        from app.services.memory_service import write_fact
        from app.services.kg_service import upsert_entity, create_relation

        write_fact(db, user_id=user_id, tier="semantic",
                   subject="用户 LDL", predicate="is_above",
                   object_value="3.4", object_unit="mmol/L",
                   confidence=0.85, tags=["lipid"])
        write_fact(db, user_id=user_id, tier="procedural",
                   subject="用户对鱼油", predicate="responds_to",
                   object_value="降 TG 显著",
                   confidence=0.7, tags=["lipid"])

        med = upsert_entity(db, user_id=user_id, type="medication",
                            canonical_name="美托洛尔", aliases=["倍他乐克"])
        cond = upsert_entity(db, user_id=user_id, type="condition",
                             canonical_name="高血压")
        create_relation(db, user_id=user_id,
                        subject_id=med.id, predicate="treats",
                        object_id=cond.id, confidence=0.8)
        return {"med": med, "cond": cond}

    def test_returns_relevant(self, db):
        self._seed(db)
        hits = hybrid_retrieve(db, 1, "我的 LDL 怎么办")
        assert hits
        # 至少要找到 LDL fact
        texts = [h.text_preview for h in hits]
        assert any("LDL" in t for t in texts)

    def test_graph_hits_show_up(self, db):
        self._seed(db)
        hits = hybrid_retrieve(db, 1, "倍他乐克效果如何")
        # 应该通过 alias 匹配到美托洛尔, 然后 2-hop 拉出高血压
        sources = {(h.source_type, h.text_preview) for h in hits}
        names = " ".join(t for _, t in sources)
        assert "美托洛尔" in names
        # graph 拉出来的 cond 也应在结果里
        assert "高血压" in names

    def test_user_isolation(self, db):
        self._seed(db, user_id=1)
        # user 2 没有数据
        hits = hybrid_retrieve(db, 2, "LDL")
        assert hits == []

    def test_empty_query_returns_empty(self, db):
        self._seed(db)
        assert hybrid_retrieve(db, 1, "") == []
        assert hybrid_retrieve(db, 1, "   ") == []

    def test_render(self, db):
        self._seed(db)
        hits = hybrid_retrieve(db, 1, "美托洛尔")
        out = render_hits_for_prompt(hits)
        assert "个人知识检索" in out
        assert "rrf=" in out


# ─────────── 防御 / 边界 ───────────


class TestEdge:
    def test_no_corpus(self, db):
        """user 没数据 → 空."""
        assert hybrid_retrieve(db, 12345, "任意 query") == []

    def test_only_facts_no_entities(self, db):
        from app.services.memory_service import write_fact
        write_fact(db, user_id=99, tier="semantic",
                   subject="孤立事实", predicate="equals",
                   object_value="42", confidence=0.7)
        hits = hybrid_retrieve(db, 99, "孤立")
        # graph 路径返空, 但 BM25 还能 hit
        assert hits
        assert hits[0].source_type == "fact"

    def test_only_entities_no_facts(self, db):
        from app.services.kg_service import upsert_entity
        upsert_entity(db, user_id=88, type="medication",
                      canonical_name="独立药品")
        hits = hybrid_retrieve(db, 88, "独立药品")
        assert hits
        assert hits[0].source_type == "entity"


def test_historical_gated_causal_fact_is_neutralized_before_prompt_corpus(db):
    """历史事实也不能经 hybrid 检索把处方混杂指标表述成"有效"。"""
    from app.services.memory_service import write_fact

    write_fact(
        db,
        user_id=73,
        tier="procedural",
        subject="用户",
        predicate="responds_to",
        object_value="减少夜宵 → Apo B",
        confidence=0.8,
        tags=[" Apo B "],
    )

    docs = _build_user_corpus(db, 73)

    assert len(docs) == 1
    assert "observed_change" in docs[0].text
    assert "responds_to" not in docs[0].text


def test_subject_only_gated_effect_is_neutralized_and_confidence_capped(db):
    """历史行即使只在 subject 标注指标，也不能以高置信效果结论进入 prompt。"""
    from app.services.memory_service import write_fact

    write_fact(
        db,
        user_id=74,
        tier="procedural",
        subject="用户 Apo B",
        predicate="responds_to",
        object_value="减少夜宵",
        confidence=0.8,
    )

    docs = _build_user_corpus(db, 74)

    assert len(docs) == 1
    assert "observed_change" in docs[0].text
    assert docs[0].metadata["confidence"] == pytest.approx(0.4)


def test_desktop_projection_neutralizes_subject_only_gated_effect(db):
    from app.api.desktop import _memory_fact_to_dict
    from app.services.memory_service import write_fact

    fact = write_fact(
        db,
        user_id=74,
        tier="procedural",
        subject="用户 LP A",
        predicate="responds_to",
        object_value="减少夜宵",
        confidence=0.8,
    )

    payload = _memory_fact_to_dict(fact)

    assert payload["predicate"] == "observed_change"
    assert payload["confidence"] == pytest.approx(0.4)
    assert payload["effective_confidence"] == pytest.approx(0.4)
