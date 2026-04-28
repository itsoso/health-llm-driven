"""Health Knowledge Graph 测试 — entities + relations + traversal."""
import pytest

from app.models.health_kg import EntityRelation, HealthEntity
from app.services.kg_service import (
    upsert_entity, match_entity, create_relation, get_relations,
    expand_neighborhood, mention_to_entities,
    render_neighborhood_for_prompt,
)


# ─────────── upsert_entity ───────────


class TestUpsertEntity:
    def test_creates_new(self, db):
        e = upsert_entity(db, user_id=1, type="medication",
                          canonical_name="美托洛尔",
                          aliases=["倍他乐克", "metoprolol"],
                          attributes={"dosage": "25mg"},
                          source={"type": "manual"})
        assert e is not None
        assert e.canonical_name == "美托洛尔"
        assert "倍他乐克" in e.aliases

    def test_invalid_type_rejected(self, db):
        e = upsert_entity(db, user_id=1, type="bogus",
                          canonical_name="x")
        assert e is None

    def test_dup_merges_aliases(self, db):
        e1 = upsert_entity(db, user_id=1, type="medication",
                           canonical_name="美托洛尔",
                           aliases=["倍他乐克"])
        e2 = upsert_entity(db, user_id=1, type="medication",
                           canonical_name="美托洛尔",
                           aliases=["metoprolol"])
        assert e1.id == e2.id
        assert "倍他乐克" in e2.aliases
        assert "metoprolol" in e2.aliases

    def test_user_scoped(self, db):
        e1 = upsert_entity(db, user_id=1, type="medication",
                           canonical_name="美托洛尔")
        e2 = upsert_entity(db, user_id=2, type="medication",
                           canonical_name="美托洛尔")
        assert e1.id != e2.id


# ─────────── match_entity ───────────


class TestMatchEntity:
    def test_exact_canonical(self, db):
        upsert_entity(db, user_id=1, type="medication",
                      canonical_name="美托洛尔")
        m = match_entity(db, 1, "美托洛尔")
        assert m and m.canonical_name == "美托洛尔"

    def test_alias(self, db):
        upsert_entity(db, user_id=1, type="medication",
                      canonical_name="美托洛尔",
                      aliases=["倍他乐克"])
        m = match_entity(db, 1, "倍他乐克")
        assert m and m.canonical_name == "美托洛尔"

    def test_partial_canonical(self, db):
        upsert_entity(db, user_id=1, type="condition",
                      canonical_name="原发性高血压 stage1")
        m = match_entity(db, 1, "高血压")
        assert m is not None

    def test_type_filter(self, db):
        upsert_entity(db, user_id=1, type="medication", canonical_name="X")
        upsert_entity(db, user_id=1, type="condition", canonical_name="X")
        m_med = match_entity(db, 1, "X", type="medication")
        m_cond = match_entity(db, 1, "X", type="condition")
        assert m_med.type == "medication"
        assert m_cond.type == "condition"

    def test_user_isolation(self, db):
        upsert_entity(db, user_id=1, type="medication", canonical_name="X")
        m = match_entity(db, 2, "X")
        assert m is None


# ─────────── create_relation ───────────


class TestCreateRelation:
    def test_creates_edge(self, db):
        med = upsert_entity(db, user_id=1, type="medication",
                            canonical_name="美托洛尔")
        cond = upsert_entity(db, user_id=1, type="condition",
                             canonical_name="高血压")
        r = create_relation(db, user_id=1,
                            subject_id=med.id, predicate="treats",
                            object_id=cond.id, confidence=0.8)
        assert r is not None
        assert r.predicate == "treats"

    def test_invalid_predicate(self, db):
        med = upsert_entity(db, user_id=1, type="medication", canonical_name="X")
        cond = upsert_entity(db, user_id=1, type="condition", canonical_name="Y")
        r = create_relation(db, user_id=1, subject_id=med.id,
                            predicate="bogus_pred", object_id=cond.id)
        assert r is None

    def test_self_loop_rejected(self, db):
        e = upsert_entity(db, user_id=1, type="condition", canonical_name="X")
        r = create_relation(db, user_id=1, subject_id=e.id,
                            predicate="causes", object_id=e.id)
        assert r is None

    def test_dup_increments_evidence(self, db):
        med = upsert_entity(db, user_id=1, type="medication", canonical_name="X")
        cond = upsert_entity(db, user_id=1, type="condition", canonical_name="Y")
        r1 = create_relation(db, user_id=1, subject_id=med.id,
                             predicate="treats", object_id=cond.id)
        r2 = create_relation(db, user_id=1, subject_id=med.id,
                             predicate="treats", object_id=cond.id,
                             source={"type": "exam"})
        assert r1.id == r2.id
        assert r2.evidence_count == 2
        assert len(r2.sources) >= 1


# ─────────── 2-hop traversal ───────────


class TestExpandNeighborhood:
    def _build_chain(self, db):
        """美托洛尔 → treats → 高血压 → caused_by → 钠摄入 (NSAID)
        构建一个 2-hop 链 + 1 个不相关节点."""
        med = upsert_entity(db, user_id=1, type="medication",
                            canonical_name="美托洛尔")
        cond = upsert_entity(db, user_id=1, type="condition",
                             canonical_name="高血压")
        factor = upsert_entity(db, user_id=1, type="lifestyle_factor",
                               canonical_name="高钠饮食")
        nsaid = upsert_entity(db, user_id=1, type="medication",
                              canonical_name="布洛芬")
        unrelated = upsert_entity(db, user_id=1, type="symptom",
                                  canonical_name="不相关症状")

        create_relation(db, user_id=1, subject_id=med.id,
                        predicate="treats", object_id=cond.id, confidence=0.8)
        create_relation(db, user_id=1, subject_id=factor.id,
                        predicate="causes", object_id=cond.id, confidence=0.7)
        create_relation(db, user_id=1, subject_id=med.id,
                        predicate="interacts_with", object_id=nsaid.id, confidence=0.9)
        return {"med": med, "cond": cond, "factor": factor,
                "nsaid": nsaid, "unrelated": unrelated}

    def test_1hop(self, db):
        chain = self._build_chain(db)
        nbrs = expand_neighborhood(db, 1, chain["med"].id, hops=1, max_per_hop=10)
        names = {n["entity_name"] for n in nbrs}
        # 1-hop: treats → 高血压, interacts_with → 布洛芬
        assert "高血压" in names
        assert "布洛芬" in names
        # 2-hop 还不应出现
        assert "高钠饮食" not in names
        assert "不相关症状" not in names

    def test_2hop(self, db):
        chain = self._build_chain(db)
        nbrs = expand_neighborhood(db, 1, chain["med"].id, hops=2, max_per_hop=10)
        names = {n["entity_name"] for n in nbrs}
        # 2-hop 应该看到高钠饮食 (via 高血压 ← causes ← 高钠饮食)
        assert "高血压" in names
        assert "高钠饮食" in names
        assert "不相关症状" not in names  # 完全没连接

    def test_user_isolation(self, db):
        chain = self._build_chain(db)
        nbrs = expand_neighborhood(db, 999, chain["med"].id, hops=2)
        assert nbrs == []  # 不属于 user 999


# ─────────── mention_to_entities ───────────


class TestMentionToEntities:
    def test_finds_canonical_in_text(self, db):
        upsert_entity(db, user_id=1, type="medication",
                      canonical_name="美托洛尔")
        out = mention_to_entities(db, 1, "今天吃了美托洛尔, 状态还可以")
        assert len(out) == 1
        assert out[0].canonical_name == "美托洛尔"

    def test_finds_alias(self, db):
        upsert_entity(db, user_id=1, type="medication",
                      canonical_name="美托洛尔",
                      aliases=["倍他乐克"])
        out = mention_to_entities(db, 1, "倍他乐克 25mg, 一日一次")
        assert len(out) == 1
        assert out[0].canonical_name == "美托洛尔"

    def test_multiple_mentions(self, db):
        upsert_entity(db, user_id=1, type="medication", canonical_name="美托洛尔")
        upsert_entity(db, user_id=1, type="condition", canonical_name="高血压")
        out = mention_to_entities(db, 1, "美托洛尔治疗高血压效果如何")
        names = {e.canonical_name for e in out}
        assert "美托洛尔" in names
        assert "高血压" in names

    def test_no_match_returns_empty(self, db):
        upsert_entity(db, user_id=1, type="medication", canonical_name="X")
        out = mention_to_entities(db, 1, "今天天气真好")
        assert out == []


# ─────────── prompt 注入 ───────────


class TestRenderNeighborhood:
    def test_renders_chain(self, db):
        med = upsert_entity(db, user_id=1, type="medication",
                            canonical_name="美托洛尔")
        cond = upsert_entity(db, user_id=1, type="condition",
                             canonical_name="高血压")
        create_relation(db, user_id=1, subject_id=med.id,
                        predicate="treats", object_id=cond.id, confidence=0.85)

        out = render_neighborhood_for_prompt(
            db, 1, "我吃美托洛尔效果怎样",
            max_seeds=3, hops=2, max_per_hop=5,
        )
        assert "知识图谱" in out
        assert "美托洛尔" in out
        assert "treats" in out

    def test_no_seeds_returns_empty(self, db):
        out = render_neighborhood_for_prompt(db, 1, "今天天气真好")
        assert out == ""
