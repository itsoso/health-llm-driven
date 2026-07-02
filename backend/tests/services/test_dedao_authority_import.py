from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.error import HTTPError

from app.services.system_kb.dedao_authority_import import (
    HEALTH_AUTHORITY_PACK_CONTRACT,
    dry_run_import_dedao_authority_pack,
    dry_run_import_dedao_authority_pack_from_kbase,
    evaluate_dedao_authority_pull_gate,
)


@dataclass
class _FakeHTTPResponse:
    body: str
    status: int = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body.encode("utf-8")


def _line(**overrides):
    payload = {
        "consumer_contract": HEALTH_AUTHORITY_PACK_CONTRACT,
        "project_id": "health",
        "target_system": "health-llm-driven",
        "claim_id": "dedao:book-1:claim-1",
        "book_id": "book-1",
        "book_title": "健康学习材料",
        "chapter_id": "chapter-1",
        "title": "睡眠复盘支持健康管理",
        "summary": "稳定复盘帮助识别睡眠行为模式。",
        "candidate_type": "education_context_candidate",
        "allowed_uses": ["health_education", "question_preparation", "context_retrieval"],
        "blocked_uses": ["diagnosis", "treatment", "dosage", "medication_change", "emergency_guidance"],
        "risk_tier": "assistive_only",
        "decision": "assist",
        "citations": ["citation-1"],
        "source_hash": "source-hash-1",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_dry_run_rejects_unknown_contract():
    report = dry_run_import_dedao_authority_pack(
        [
            _line(consumer_contract="dedao_project_collection_jsonl_v1"),
        ],
    )

    assert report.total == 1
    assert report.accepted_for_review == []
    assert report.invalid[0].reason == "unknown_contract"


def test_dry_run_blocks_medication_action_claim():
    report = dry_run_import_dedao_authority_pack(
        [
            _line(
                claim_id="dedao:book-1:claim-medication",
                title="用药剂量需要医生判断",
                summary="不能根据单一书摘自行调整药物剂量。",
                allowed_uses=["health_education", "action_support"],
                blocked_uses=["diagnosis", "treatment", "dosage", "medication_change", "emergency_guidance"],
            ),
        ],
    )

    assert report.accepted_for_review == []
    assert report.blocked[0].claim_id == "dedao:book-1:claim-medication"
    assert report.blocked[0].reason == "medical_action_claim"


def test_dry_run_reports_review_candidates_without_writing(tmp_path):
    report = dry_run_import_dedao_authority_pack(
        [
            _line(claim_id="dedao:book-1:claim-1", source_hash="source-hash-1"),
            _line(claim_id="dedao:book-1:claim-1", source_hash="source-hash-1"),
            _line(claim_id="dedao:book-1:claim-missing-source", source_hash="", citations=[]),
        ],
    )

    assert [item.claim_id for item in report.accepted_for_review] == ["dedao:book-1:claim-1"]
    assert report.duplicates[0].claim_id == "dedao:book-1:claim-1"
    assert report.missing_source_refs[0].claim_id == "dedao:book-1:claim-missing-source"
    assert report.would_write is False
    assert not any(tmp_path.iterdir())


def test_dry_run_accepts_nested_source_refs_and_preserves_review_metadata():
    report = dry_run_import_dedao_authority_pack(
        [
            _line(
                claim_id="dedao:book-1:claim-nested-source",
                source_hash="",
                citations=[],
                source_refs={
                    "book_id": "book-1",
                    "book_title": "健康学习材料",
                    "chapter_id": "chapter-1",
                    "claim_id": "dedao:book-1:claim-nested-source",
                    "citations": ["nested-citation-1"],
                    "source_hash": "nested-source-hash-1",
                },
                review_status="needs_review",
                risk_reason="dedao_educational_source",
                entity_candidates=["睡眠管理", "学习复盘"],
            ),
        ],
    )

    assert report.missing_source_refs == []
    assert report.blocked == []
    candidate = report.accepted_for_review[0]
    assert candidate.source_hash == "nested-source-hash-1"
    assert candidate.citations == ["nested-citation-1"]
    assert candidate.review_status == "needs_review"
    assert candidate.risk_reason == "dedao_educational_source"
    assert candidate.entity_candidates == ["睡眠管理", "学习复盘"]


def test_dry_run_blocks_blocked_review_status():
    report = dry_run_import_dedao_authority_pack(
        [
            _line(
                claim_id="dedao:book-1:claim-blocked-review",
                title="睡眠复盘仅作背景材料",
                summary="这条记录已由上游标记为 blocked。",
                review_status="blocked",
                risk_reason="medical_action_boundary",
                entity_candidates=["睡眠管理"],
            ),
        ],
    )

    assert report.accepted_for_review == []
    assert report.blocked[0].claim_id == "dedao:book-1:claim-blocked-review"
    assert report.blocked[0].reason == "blocked_review_status"


def test_pull_report_fetches_jsonl_with_bearer_and_sanitizes_token():
    seen = {}

    def opener(request, *, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.headers.get("Authorization")
        seen["timeout"] = timeout
        return _FakeHTTPResponse(_line())

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example/",
        "secret-token",
        limit=7,
        timeout=3,
        opener=opener,
    )

    assert report.status == "ok"
    assert report.http_status == 200
    assert report.source_url == "https://kbase.example/api/projects/health/authority-pack/export?format=jsonl&limit=7"
    assert seen == {
        "url": report.source_url,
        "authorization": "Bearer secret-token",
        "timeout": 3,
    }
    assert [item.claim_id for item in report.import_report.accepted_for_review] == ["dedao:book-1:claim-1"]
    serialized = json.dumps(report.to_dict(), ensure_ascii=False)
    assert "secret-token" not in serialized
    assert "Authorization" not in serialized


def test_pull_report_reports_http_401_without_token_leakage():
    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    assert report.status == "fetch_failed"
    assert report.http_status == 401
    assert report.error == "http_401"
    assert report.import_report.total == 0
    assert "secret-token" not in json.dumps(report.to_dict(), ensure_ascii=False)


def test_pull_report_keeps_bad_jsonl_as_import_finding():
    def opener(request, *, timeout):
        return _FakeHTTPResponse("{not-json}\n" + _line(claim_id="dedao:book-1:claim-ok"))

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    assert report.status == "ok"
    assert report.import_report.total == 2
    assert report.import_report.invalid[0].reason == "invalid_json"
    assert [item.claim_id for item in report.import_report.accepted_for_review] == ["dedao:book-1:claim-ok"]


def test_pull_gate_passes_clean_report():
    def opener(request, *, timeout):
        return _FakeHTTPResponse(_line())

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    gate = evaluate_dedao_authority_pull_gate(report)

    assert gate.status == "pass"
    assert gate.reasons == []
    assert gate.fail_count == 0
    assert gate.warn_count == 0


def test_pull_gate_fails_fetch_errors_without_token_leakage():
    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    gate = evaluate_dedao_authority_pull_gate(report)
    serialized = json.dumps(gate.to_redacted_dict(), ensure_ascii=False)

    assert gate.status == "fail"
    assert "fetch_failed" in gate.reasons
    assert gate.fail_count == 1
    assert "secret-token" not in serialized
    assert "Authorization" not in serialized


def test_pull_gate_fails_invalid_jsonl():
    def opener(request, *, timeout):
        return _FakeHTTPResponse("{not-json}\n" + _line(claim_id="dedao:book-1:claim-ok"))

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    gate = evaluate_dedao_authority_pull_gate(report)
    redacted = gate.to_redacted_dict()

    assert gate.status == "fail"
    assert "invalid_records" in gate.reasons
    assert redacted["counts"]["invalid"] == 1
    assert redacted["issues"]["invalid"] == [
        {"claim_id": "", "reason": "invalid_json", "line_no": 1},
    ]


def test_pull_gate_fails_blocked_only_report():
    def opener(request, *, timeout):
        return _FakeHTTPResponse(
            _line(
                claim_id="dedao:book-1:claim-blocked-review",
                review_status="blocked",
                risk_reason="medical_action_boundary",
            ),
        )

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    gate = evaluate_dedao_authority_pull_gate(report)

    assert gate.status == "fail"
    assert "no_accepted_candidates" in gate.reasons
    assert "blocked_records" in gate.reasons


def test_pull_gate_warns_on_mixed_accepted_and_blocked_records():
    raw_text = "raw source text should not appear in gate output"

    def opener(request, *, timeout):
        return _FakeHTTPResponse(
            "\n".join(
                [
                    _line(claim_id="dedao:book-1:claim-ok", summary=raw_text),
                    _line(
                        claim_id="dedao:book-1:claim-blocked-review",
                        review_status="blocked",
                        risk_reason="medical_action_boundary",
                        summary=raw_text,
                    ),
                ],
            ),
        )

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    gate = evaluate_dedao_authority_pull_gate(report)
    serialized = json.dumps(gate.to_redacted_dict(), ensure_ascii=False)

    assert gate.status == "warn"
    assert gate.fail_count == 0
    assert gate.warn_count == 1
    assert gate.reasons == ["blocked_records"]
    assert raw_text not in serialized
    assert "dedao:book-1:claim-blocked-review" in serialized


def test_pull_gate_redacted_artifact_has_schema_and_generation_time():
    def opener(request, *, timeout):
        return _FakeHTTPResponse(_line())

    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=opener,
    )

    gate = evaluate_dedao_authority_pull_gate(report)
    redacted = gate.to_redacted_dict(generated_at="2026-07-02T00:00:00Z")

    assert redacted["artifact_schema"] == "dedao_authority_pull_gate_v1"
    assert redacted["generated_at"] == "2026-07-02T00:00:00Z"
