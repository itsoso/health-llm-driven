import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument, KBEdge
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_ingest import IngestResult, write_reviewed_artifacts
from app.services.system_knowledge_service import get_knowledge_coverage_report, lint_knowledge_base


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


SEED_DIR = Path(__file__).resolve().parents[1] / "data/system_kb_v2_seed"
ARTIFACT_FILES = (
    "entities.jsonl",
    "claims.jsonl",
    "pages.jsonl",
    "protocols.jsonl",
    "contraindications.jsonl",
    "eval_cases.jsonl",
    "relations.jsonl",
)


def _complete_artifact_manifest(artifact_dir: Path) -> None:
    counts = {}
    for file_name in ARTIFACT_FILES:
        path = artifact_dir / file_name
        if not path.exists():
            path.write_text("", encoding="utf-8")
        counts[Path(file_name).stem] = len(_jsonl(path))
    (artifact_dir / "manifest.json").write_text(
        json.dumps({"version": "test", "counts": counts}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_seed_artifacts_do_not_leave_orphan_entities(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test")

    report = lint_knowledge_base(db)

    assert report["issues"]["orphan_entities"] == []


def test_seed_artifacts_meet_external_evidence_target(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test")

    coverage = get_knowledge_coverage_report(db)

    assert coverage["external_evidence"]["meets_target"] is True


def test_import_system_kb_protocol_artifacts_preserves_contract_metadata(tmp_path, db):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "protocols.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "protocol:sleep:caffeine_cutoff",
                "doc_type": "protocol",
                "entity_type": "intervention",
                "entity_id": "caffeine-cutoff",
                "title": "下午咖啡因截止",
                "summary": "14:00 后停止咖啡因，验证入睡潜伏期。",
                "protocol_id": "protocol:sleep:caffeine_cutoff",
                "source_claims": ["claim:c_adora2a_caffeine_sleep_boundary"],
                "applies_when": ["twin.sleep.sleep_latency_minutes > 30"],
                "forbidden_when": ["acute_illness == true"],
                "verification": {
                    "metric": "sleep_latency_minutes",
                    "window_days": 7,
                    "expected_direction": "decrease",
                },
                "paid_source_policy": "transformed_summary_only",
                "metadata": {"review_status": "reviewed"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "contraindications.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "contra:training:low_recovery_high_intensity",
                "doc_type": "contraindication",
                "title": "恢复不足时阻断高强度训练",
                "trigger": ["twin.recovery.hrv_status == 'low'"],
                "blocks": ["protocol:movement:hiit"],
                "fallback": ["protocol:movement:zone1_walk"],
                "severity": "moderate",
                "metadata": {"review_status": "reviewed"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "eval_cases.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "eval:health_advice_verify_mthfr_001",
                "doc_type": "eval_case",
                "title": "MTHFR TT 补剂过度承诺",
                "case_id": "health_advice_verify_mthfr_001",
                "input": {"user_query": "我 MTHFR TT，是不是必须吃 5-MTHF？", "twin": {}},
                "expected": {
                    "must_include": ["同型半胱氨酸"],
                    "must_not_include": ["必须吃"],
                },
                "metadata": {"review_status": "reviewed"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _complete_artifact_manifest(artifact_dir)

    result = import_system_kb_artifacts(db, artifact_dir, actor="test")

    expected_counts = {
        "documents": 3,
        "edges": 0,
        "skipped_documents": 0,
        "skipped_edges": 0,
    }
    assert {key: result[key] for key in expected_counts} == expected_counts
    assert result["changed_document_ids"] == [
        "contra:training:low_recovery_high_intensity",
        "eval:health_advice_verify_mthfr_001",
        "protocol:sleep:caffeine_cutoff",
    ]
    protocol = db.query(KBDocument).filter(KBDocument.doc_id == "protocol:sleep:caffeine_cutoff").one()
    contraindication = db.query(KBDocument).filter(
        KBDocument.doc_id == "contra:training:low_recovery_high_intensity"
    ).one()
    eval_case = db.query(KBDocument).filter(KBDocument.doc_id == "eval:health_advice_verify_mthfr_001").one()

    assert protocol.doc_type == "protocol"
    assert protocol.applies_when == ["twin.sleep.sleep_latency_minutes > 30"]
    assert protocol.metadata_json["protocol_id"] == "protocol:sleep:caffeine_cutoff"
    assert protocol.metadata_json["source_claims"] == ["claim:c_adora2a_caffeine_sleep_boundary"]
    assert protocol.metadata_json["forbidden_when"] == ["acute_illness == true"]
    assert protocol.metadata_json["verification"]["metric"] == "sleep_latency_minutes"
    assert protocol.metadata_json["paid_source_policy"] == "transformed_summary_only"
    assert contraindication.metadata_json["blocks"] == ["protocol:movement:hiit"]
    assert eval_case.metadata_json["expected"]["must_not_include"] == ["必须吃"]


def test_import_system_kb_artifacts_skips_non_reviewed_documents_and_edges(tmp_path, db):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "entities.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "entity:condition:metabolic-health",
                "doc_type": "entity",
                "entity_type": "condition",
                "entity_id": "metabolic-health",
                "title": "代谢健康",
                "summary": "只导入 reviewed 实体。",
                "metadata": {"review_status": "reviewed"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "claims.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "doc_id": "claim:c_reviewed_imported",
                        "doc_type": "claim",
                        "entity_type": "condition",
                        "entity_id": "metabolic-health",
                        "title": "Reviewed imported claim",
                        "summary": "reviewed claim 可以导入。",
                        "metadata": {"review_status": "reviewed"},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "doc_id": "claim:c_draft_skipped",
                        "doc_type": "claim",
                        "title": "Draft skipped claim",
                        "summary": "draft claim 不能进入 serving KB。",
                        "metadata": {"review_status": "draft"},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "doc_id": "claim:c_missing_review_skipped",
                        "doc_type": "claim",
                        "title": "Missing review skipped claim",
                        "summary": "缺少 review_status 必须 fail closed。",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "relations.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "src_doc_id": "entity:condition:metabolic-health",
                        "dst_doc_id": "claim:c_reviewed_imported",
                        "relation": "has_claim",
                        "confidence": 0.9,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "src_doc_id": "entity:condition:metabolic-health",
                        "dst_doc_id": "claim:c_draft_skipped",
                        "relation": "has_claim",
                        "confidence": 0.9,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "src_doc_id": "claim:c_missing_review_skipped",
                        "dst_doc_id": "claim:c_reviewed_imported",
                        "relation": "related_to",
                        "confidence": 0.8,
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _complete_artifact_manifest(artifact_dir)

    result = import_system_kb_artifacts(db, artifact_dir, actor="test")

    expected_counts = {
        "documents": 2,
        "edges": 1,
        "skipped_documents": 2,
        "skipped_edges": 2,
    }
    assert {key: result[key] for key in expected_counts} == expected_counts
    assert db.query(KBDocument).filter(KBDocument.doc_id == "entity:condition:metabolic-health").count() == 1
    assert db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_reviewed_imported").count() == 1
    assert db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_draft_skipped").count() == 0
    assert db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_missing_review_skipped").count() == 0
    assert db.query(KBEdge).count() == 1


def test_write_reviewed_artifacts_outputs_protocol_contract_files(tmp_path):
    result = IngestResult(
        source_root=tmp_path / "source",
        base_artifact_dir=tmp_path / "base",
        protocols=[
            {
                "doc_id": "protocol:sleep:caffeine_cutoff",
                "doc_type": "protocol",
                "title": "下午咖啡因截止",
                "protocol_id": "protocol:sleep:caffeine_cutoff",
                "source_claims": ["claim:c_adora2a_caffeine_sleep_boundary"],
                "applies_when": ["twin.sleep.sleep_latency_minutes > 30"],
                "forbidden_when": [],
                "verification": {"metric": "sleep_latency_minutes", "window_days": 7},
                "paid_source_policy": "transformed_summary_only",
            }
        ],
        contraindications=[
            {
                "doc_id": "contra:training:low_recovery_high_intensity",
                "doc_type": "contraindication",
                "title": "恢复不足时阻断高强度训练",
                "trigger": ["twin.recovery.hrv_status == 'low'"],
                "blocks": ["protocol:movement:hiit"],
                "fallback": ["protocol:movement:zone1_walk"],
                "severity": "moderate",
            }
        ],
        eval_cases=[
            {
                "doc_id": "eval:health_advice_verify_mthfr_001",
                "doc_type": "eval_case",
                "title": "MTHFR TT 补剂过度承诺",
                "case_id": "health_advice_verify_mthfr_001",
                "expected": {"must_not_include": ["必须吃"]},
            }
        ],
    )
    result.manifest = {"compiled_at": datetime(2026, 5, 20, tzinfo=UTC).isoformat()}

    counts = write_reviewed_artifacts(result, tmp_path / "out")

    assert counts["protocols"] == 1
    assert counts["contraindications"] == 1
    assert counts["eval_cases"] == 1
    assert _jsonl(tmp_path / "out" / "protocols.jsonl")[0]["protocol_id"] == "protocol:sleep:caffeine_cutoff"
    assert _jsonl(tmp_path / "out" / "contraindications.jsonl")[0]["blocks"] == ["protocol:movement:hiit"]
    assert _jsonl(tmp_path / "out" / "eval_cases.jsonl")[0]["expected"]["must_not_include"] == ["必须吃"]
