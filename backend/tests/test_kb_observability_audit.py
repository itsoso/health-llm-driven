"""Tests for KB retrieval observability audits (kb_zero_hit + kb_citation_usage)."""

from app.models.system_knowledge import KBAudit, KBDocument
from app.services import system_knowledge_service as svc


def _add_reviewed_claim(db, doc_id, title, entity_id="hypertension-risk", entity_type="condition"):
    db.add(
        KBDocument(
            doc_id=doc_id,
            doc_type="claim",
            entity_type=entity_type,
            entity_id=entity_id,
            title=title,
            summary=title,
            body=title,
            confidence=0.9,
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()


def test_search_zero_hit_writes_audit(db):
    # Empty KB → any query returns no results → a kb_zero_hit audit row is written.
    result = svc.search_knowledge(db, "完全不存在的查询词xyz")
    assert result["results"] == []
    rows = db.query(KBAudit).filter(KBAudit.op == "kb_zero_hit").all()
    assert len(rows) == 1
    assert rows[0].diff["source"] == "search_knowledge"
    assert "channel_stats" in rows[0].diff


def test_search_empty_query_does_not_crash(db):
    # Guarded/empty query must not raise; may or may not audit, but never errors.
    out = svc.search_knowledge(db, "")
    assert "results" in out


def test_search_with_hit_writes_no_zero_hit_audit(db):
    _add_reviewed_claim(db, "claim:c_bp_test", "高血压 家庭 血压 监测 建议")
    svc.reindex_knowledge_documents(db, actor="test")
    result = svc.search_knowledge(db, "高血压 血压 监测")
    assert result["results"], "expected a hit for a matching reviewed claim"
    assert db.query(KBAudit).filter(KBAudit.op == "kb_zero_hit").count() == 0


def test_lookup_for_twin_zero_hit_writes_audit(db):
    # No entities / no claims → lookup returns empty claims → kb_zero_hit audit.
    result = svc.lookup_for_twin(db, {})
    assert result["claims"] == []
    rows = db.query(KBAudit).filter(
        KBAudit.op == "kb_zero_hit", KBAudit.doc_id.is_(None)
    ).all()
    assert any(r.diff.get("source") == "lookup_for_twin" for r in rows)


def test_record_citation_usage_counts_used_claims(db):
    _add_reviewed_claim(db, "claim:c_used", "餐后血糖走路有帮助", entity_id="post-meal-glucose", entity_type="biomarker")
    _add_reviewed_claim(db, "claim:c_unused", "完全无关的补剂话题内容", entity_id="melatonin", entity_type="supplement")
    answer = "关于餐后血糖走路有帮助这一点，建议饭后适当活动。"
    diff = svc.record_kb_citation_usage(
        db, ["claim:c_used", "claim:c_unused"], answer, source="test"
    )
    assert diff is not None
    assert diff["provided"] == 2
    assert diff["used"] == 1
    assert diff["used_ids"] == ["claim:c_used"]
    rows = db.query(KBAudit).filter(KBAudit.op == "kb_citation_usage").all()
    assert len(rows) == 1
    assert rows[0].diff["used"] == 1


def test_record_citation_usage_empty_is_noop(db):
    assert svc.record_kb_citation_usage(db, [], "任意文本") is None
    assert db.query(KBAudit).filter(KBAudit.op == "kb_citation_usage").count() == 0


def test_audit_write_failure_is_swallowed(db, monkeypatch):
    # Realistic failure: the KBAudit commit throws. The bypass writer must swallow
    # it (log WARNING + rollback) and the caller (search) must return normally.
    real_commit = db.commit
    calls = {"n": 0}

    def _flaky_commit(*a, **kw):
        # Only the audit commit (first commit after a zero-hit) explodes once.
        calls["n"] += 1
        raise RuntimeError("audit commit failed")

    monkeypatch.setattr(db, "commit", _flaky_commit)
    # Directly exercise the writer: it must not propagate the commit error.
    svc._write_kb_observability_audit(db, op="kb_zero_hit", diff={"source": "test"})
    monkeypatch.setattr(db, "commit", real_commit)
    assert calls["n"] >= 1  # the flaky commit was actually invoked and swallowed
