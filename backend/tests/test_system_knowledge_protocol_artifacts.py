import json
from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_ingest import IngestResult, write_reviewed_artifacts


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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

    result = import_system_kb_artifacts(db, artifact_dir, actor="test")

    assert result == {"documents": 3, "edges": 0}
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
