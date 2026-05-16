from datetime import UTC, datetime

from app.agents.knowledge_librarian.librarian import KnowledgeLibrarianSpecialist
from app.models.system_knowledge import KBDocument, KBEdge


def _seed_system_kb_gene_claim(db):
    entity = KBDocument(
        doc_id="entity:gene:MTHFR",
        doc_type="entity",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR",
        summary="MTHFR 参与一碳代谢和叶酸转化。",
        confidence=0.88,
        evidence_level="B",
        sources=["dedao:qiuzilong-genetics-07"],
        last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        decay_rate="slow",
    )
    claim = KBDocument(
        doc_id="claim:c_mthfr_c677t_hcy_folate_boundary",
        doc_type="claim",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR C677T 与叶酸转化边界",
        summary="C677T CT/TT 用户可优先关注同型半胱氨酸、B12 与活性叶酸。",
        confidence=0.82,
        evidence_level="B",
        applies_when=["twin.genetics.MTHFR_C677T in ['CT', 'TT']"],
        recommends_lookup=["entity:supplement:5-MTHF", "entity:biomarker:Hcy"],
        sources=["dedao:qiuzilong-genetics-07", "pubmed:19033271"],
        last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        decay_rate="normal",
    )
    db.add_all([entity, claim])
    db.flush()
    db.add(
        KBEdge(
            src_doc_id=entity.doc_id,
            dst_doc_id=claim.doc_id,
            relation="has_claim",
            confidence=0.9,
            source_claim_id=claim.doc_id,
        )
    )
    db.commit()


def test_knowledge_librarian_prefers_system_kb_for_explicit_gene_question(db):
    _seed_system_kb_gene_claim(db)

    finding = KnowledgeLibrarianSpecialist().run(
        twin=object(),
        context={"query": "我 MTHFR-TT 该注意什么？", "db": db},
    )

    assert finding.raw["source"] == "system_kb_v2"
    assert finding.evidence_refs == ["claim:c_mthfr_c677t_hcy_folate_boundary"]
    assert finding.findings[0]["type"] == "system_knowledge_reference"
    assert finding.findings[0]["evidence_refs"] == ["claim:c_mthfr_c677t_hcy_folate_boundary"]
    assert finding.findings[0]["entity"]["doc_id"] == "entity:gene:MTHFR"


def test_knowledge_librarian_uses_system_kb_search_before_legacy_chroma(db):
    _seed_system_kb_gene_claim(db)

    finding = KnowledgeLibrarianSpecialist().run(
        twin=object(),
        context={"query": "叶酸转化和同型半胱氨酸", "db": db},
    )

    assert finding.raw["source"] == "system_kb_v2"
    assert "claim:c_mthfr_c677t_hcy_folate_boundary" in finding.evidence_refs
    assert any(item["type"] == "system_knowledge_reference" for item in finding.findings)
