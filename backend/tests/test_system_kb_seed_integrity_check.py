"""Contract tests for the pre-commit system-KB seed integrity guard.

Each fail-case has a bad fixture the guard MUST catch; the good fixture MUST pass
(no over-alarm). This mirrors the reviewed/edge logic of system_knowledge_importer
so the fast pre-commit check stays faithful to the DB-backed release gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_system_kb_seed_integrity import check_seed_integrity


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _reviewed(doc_id: str, doc_type: str, **extra) -> dict:
    return {"doc_id": doc_id, "doc_type": doc_type, "metadata": {"review_status": "reviewed"}, **extra}


def _edge(src: str, dst: str) -> dict:
    return {"relation": "recommends_lookup", "src_doc_id": src, "dst_doc_id": dst, "source_claim_id": src}


def _build_seed(tmp_path: Path, *, claims, entities, relations, counts) -> Path:
    d = tmp_path / "seed"
    d.mkdir()
    _write(d / "claims.jsonl", claims)
    _write(d / "entities.jsonl", entities)
    _write(d / "relations.jsonl", relations)
    for name in ("pages", "protocols", "contraindications", "eval_cases"):
        _write(d / f"{name}.jsonl", [])
    full = {"pages": 0, "protocols": 0, "contraindications": 0, "eval_cases": 0, **counts}
    (d / "manifest.json").write_text(json.dumps({"counts": full}), encoding="utf-8")
    return d


def test_passes_when_claim_has_entity_edge_and_counts_synced(tmp_path):
    d = _build_seed(
        tmp_path,
        claims=[_reviewed("claim:c_ok", "claim")],
        entities=[_reviewed("entity:condition:ok", "entity")],
        relations=[_edge("claim:c_ok", "entity:condition:ok")],
        counts={"claims": 1, "entities": 1, "relations": 1},
    )
    report = check_seed_integrity(d)
    assert report["status"] == "pass", report["problems"]


def test_catches_claim_with_no_edge(tmp_path):
    d = _build_seed(
        tmp_path,
        claims=[_reviewed("claim:c_orphan", "claim", entity_type="condition", entity_id="x")],
        entities=[],
        relations=[],
        counts={"claims": 1, "entities": 0, "relations": 0},
    )
    report = check_seed_integrity(d)
    assert report["status"] == "fail"
    assert report["orphan_claims"] == ["claim:c_orphan"]
    # actionable hint names the exact entity to create
    assert any("entity:condition:x" in p for p in report["problems"])


def test_catches_edge_to_nonreviewed_entity(tmp_path):
    # importer skips edges whose endpoint is not reviewed -> claim stays orphan
    d = tmp_path / "seed"
    d.mkdir()
    _write(d / "claims.jsonl", [_reviewed("claim:c_x", "claim")])
    _write(d / "entities.jsonl", [{"doc_id": "entity:condition:draft", "doc_type": "entity", "metadata": {"review_status": "draft"}}])
    _write(d / "relations.jsonl", [_edge("claim:c_x", "entity:condition:draft")])
    for name in ("pages", "protocols", "contraindications", "eval_cases"):
        _write(d / f"{name}.jsonl", [])
    (d / "manifest.json").write_text(
        json.dumps({"counts": {"claims": 1, "entities": 1, "relations": 1, "pages": 0, "protocols": 0, "contraindications": 0, "eval_cases": 0}}),
        encoding="utf-8",
    )
    report = check_seed_integrity(d)
    assert report["status"] == "fail"
    assert report["orphan_claims"] == ["claim:c_x"]


def test_catches_manifest_count_drift(tmp_path):
    d = _build_seed(
        tmp_path,
        claims=[_reviewed("claim:c_ok", "claim")],
        entities=[_reviewed("entity:condition:ok", "entity")],
        relations=[_edge("claim:c_ok", "entity:condition:ok")],
        counts={"claims": 99, "entities": 1, "relations": 1},  # claims count is wrong
    )
    report = check_seed_integrity(d)
    assert report["status"] == "fail"
    assert any("manifest.counts.claims" in p and "claims.jsonl has 1" in p for p in report["problems"])


def test_catches_orphan_entity(tmp_path):
    d = _build_seed(
        tmp_path,
        claims=[_reviewed("claim:c_ok", "claim")],
        entities=[_reviewed("entity:condition:ok", "entity"), _reviewed("entity:condition:lonely", "entity")],
        relations=[_edge("claim:c_ok", "entity:condition:ok")],
        counts={"claims": 1, "entities": 2, "relations": 1},
    )
    report = check_seed_integrity(d)
    assert report["status"] == "fail"
    assert report["orphan_entities"] == ["entity:condition:lonely"]


def test_nonreviewed_claim_is_not_flagged(tmp_path):
    # a draft claim isn't imported, so it can't be an orphan (no over-alarm)
    d = _build_seed(
        tmp_path,
        claims=[{"doc_id": "claim:c_draft", "doc_type": "claim", "metadata": {"review_status": "draft"}}],
        entities=[],
        relations=[],
        counts={"claims": 1, "entities": 0, "relations": 0},
    )
    report = check_seed_integrity(d)
    assert report["status"] == "pass", report["problems"]


def test_catches_duplicate_claim_title_and_sources(tmp_path):
    # two reviewed claims with different doc_ids but identical title+sources = true dup
    d = _build_seed(
        tmp_path,
        claims=[
            _reviewed("claim:c_dedao_salt", "claim", title="血压风险管理先识别高钠来源", sources=["dedao:x"]),
            _reviewed("claim:c_salt", "claim", title="血压风险管理先识别高钠来源", sources=["dedao:x"]),
        ],
        entities=[_reviewed("entity:intervention:salt-reduction", "entity")],
        relations=[
            _edge("claim:c_dedao_salt", "entity:intervention:salt-reduction"),
            _edge("claim:c_salt", "entity:intervention:salt-reduction"),
        ],
        counts={"claims": 2, "entities": 1, "relations": 2},
    )
    report = check_seed_integrity(d)
    assert report["status"] == "fail"
    assert len(report["duplicate_titles"]) == 1
    assert sorted(report["duplicate_titles"][0]["doc_ids"]) == ["claim:c_dedao_salt", "claim:c_salt"]
    assert any("duplicate claim title+sources" in p for p in report["problems"])


def test_same_title_different_sources_is_not_flagged(tmp_path):
    # template-instantiated near-dups (same title, different source-course) are NOT dups
    d = _build_seed(
        tmp_path,
        claims=[
            _reviewed("claim:c_a", "claim", title="减重阶段需要力量训练", sources=["dedao:2020-2021"]),
            _reviewed("claim:c_b", "claim", title="减重阶段需要力量训练", sources=["dedao:2021-2022"]),
        ],
        entities=[_reviewed("entity:intervention:strength-training", "entity")],
        relations=[
            _edge("claim:c_a", "entity:intervention:strength-training"),
            _edge("claim:c_b", "entity:intervention:strength-training"),
        ],
        counts={"claims": 2, "entities": 1, "relations": 2},
    )
    report = check_seed_integrity(d)
    assert report["status"] == "pass", report["problems"]
    assert report["duplicate_titles"] == []


def test_real_seed_is_clean():
    # the shipped seed must always satisfy the guard
    seed = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
    report = check_seed_integrity(seed)
    assert report["status"] == "pass", report["problems"]
