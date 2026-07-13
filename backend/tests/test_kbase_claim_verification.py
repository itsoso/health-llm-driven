from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import pytest


NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)


def _claim(**overrides):
    claim = {
        "doc_id": "claim:release-1-caffeine",
        "title": "晚间咖啡因可能延长睡眠潜伏期",
        "summary": "晚间咖啡因可能延长睡眠潜伏期。",
        "evidence_level": "C",
        "confidence": 0.68,
        "sources": ["citation-1"],
        "metadata": {
            "citation_ids": ["citation-1"],
            "review_status": "draft",
            "release_id": "release-1",
            "usage_policy": "evidence_only",
        },
    }
    claim.update(overrides)
    return claim


def test_verification_packet_proposes_approve_for_current_external_evidence():
    from app.services.kbase_claim_verification import build_deterministic_verification_packet

    claim = _claim(
        evidence_level="B",
        metadata={
            **_claim()["metadata"],
            "external_sources": [
                {
                    "source": "guideline:sleep-2025",
                    "kind": "guideline",
                    "title": "Sleep guideline",
                }
            ],
            "last_confirmed": "2026-03-01T00:00:00Z",
        },
    )

    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="a" * 64,
        peer_claims=[claim],
        generated_at=NOW,
    )

    assert packet["status"] == "ready"
    assert packet["proposed_decision"] == "approve"
    assert packet["claim_content_hash"]
    assert packet["workspace_fingerprint"] == "a" * 64
    assert {check["code"]: check["status"] for check in packet["checks"]} == {
        "source_completeness": "pass",
        "external_evidence": "pass",
        "freshness": "pass",
        "duplicate": "pass",
        "contradiction": "pass",
    }


def test_verification_packet_rejects_claim_without_source_references():
    from app.services.kbase_claim_verification import build_deterministic_verification_packet

    packet = build_deterministic_verification_packet(
        _claim(sources=[]),
        workspace_fingerprint="b" * 64,
        generated_at=NOW,
    )

    assert packet["status"] == "blocked"
    assert packet["proposed_decision"] == "reject"
    assert packet["blocking_reasons"] == ["missing_source_references"]


def test_verification_packet_holds_level_c_claim_without_external_evidence():
    from app.services.kbase_claim_verification import build_deterministic_verification_packet

    packet = build_deterministic_verification_packet(
        _claim(),
        workspace_fingerprint="c" * 64,
        generated_at=NOW,
    )

    assert packet["status"] == "ready"
    assert packet["proposed_decision"] == "needs_evidence"
    assert packet["missing_evidence"] == ["independent_external_source"]
    assert next(check for check in packet["checks"] if check["code"] == "external_evidence")["status"] == "warn"


def test_verification_packet_holds_stale_external_evidence():
    from app.services.kbase_claim_verification import build_deterministic_verification_packet

    claim = _claim(
        evidence_level="B",
        metadata={
            **_claim()["metadata"],
            "external_sources": [{"source": "guideline:old"}],
            "last_confirmed": "2020-01-01T00:00:00Z",
        },
    )

    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="d" * 64,
        generated_at=NOW,
    )

    assert packet["status"] == "ready"
    assert packet["proposed_decision"] == "needs_evidence"
    assert "fresh_external_source" in packet["missing_evidence"]
    assert next(check for check in packet["checks"] if check["code"] == "freshness")["status"] == "warn"


def test_verification_packet_blocks_duplicate_claim():
    from app.services.kbase_claim_verification import build_deterministic_verification_packet

    claim = _claim()
    duplicate = _claim(doc_id="claim:release-2-caffeine")

    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="e" * 64,
        peer_claims=[claim, duplicate],
        generated_at=NOW,
    )

    assert packet["status"] == "blocked"
    assert packet["proposed_decision"] == "background_only"
    assert packet["blocking_reasons"] == ["duplicate_claim"]
    assert packet["related_claim_ids"] == ["claim:release-2-caffeine"]


def test_verification_packet_blocks_explicit_contradiction():
    from app.services.kbase_claim_verification import build_deterministic_verification_packet

    claim = _claim(
        metadata={
            **_claim()["metadata"],
            "contradiction_ids": ["claim:guideline-no-caffeine-effect"],
        }
    )

    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="f" * 64,
        generated_at=NOW,
    )

    assert packet["status"] == "blocked"
    assert packet["proposed_decision"] == "needs_evidence"
    assert packet["blocking_reasons"] == ["claim_contradiction"]
    assert packet["related_claim_ids"] == ["claim:guideline-no-caffeine-effect"]


@pytest.mark.parametrize("fingerprint", ["", "short", "z" * 64])
def test_verification_packet_requires_sha256_workspace_fingerprint(fingerprint):
    from app.services.kbase_claim_verification import build_deterministic_verification_packet

    with pytest.raises(ValueError, match="workspace fingerprint"):
        build_deterministic_verification_packet(
            _claim(),
            workspace_fingerprint=fingerprint,
            generated_at=NOW,
        )


def test_generate_workspace_packet_persists_atomically_without_mutating_claim(tmp_path):
    from app.services.kbase_review_workspace import (
        generate_review_verification_packet,
        list_review_verification_packets,
        workspace_content_fingerprint,
    )

    workspace = _write_workspace(tmp_path / "review-workspace")
    before_fingerprint = workspace_content_fingerprint(workspace)
    before_claims = (workspace / "claims.jsonl").read_bytes()

    result = generate_review_verification_packet(
        workspace,
        doc_id="claim:release-1-caffeine",
        expected_workspace_fingerprint=before_fingerprint,
        generated_at=NOW,
    )

    assert result["workspace_fingerprint"] == before_fingerprint
    assert result["packet"]["proposed_decision"] == "needs_evidence"
    assert (workspace / "claims.jsonl").read_bytes() == before_claims
    assert not (workspace / "adjudications.jsonl").exists()
    listed = list_review_verification_packets(workspace, doc_id="claim:release-1-caffeine")
    assert listed["items"][0]["status"] == "ready"
    assert listed["items"][0]["stale"] is False


def test_generate_workspace_packet_rejects_stale_fingerprint_without_mutation(tmp_path):
    from app.services.kbase_review_workspace import generate_review_verification_packet

    workspace = _write_workspace(tmp_path / "review-workspace")

    with pytest.raises(ValueError, match="changed since preview"):
        generate_review_verification_packet(
            workspace,
            doc_id="claim:release-1-caffeine",
            expected_workspace_fingerprint="0" * 64,
            generated_at=NOW,
        )

    assert not (workspace / "verification_packets.jsonl").exists()


def test_list_workspace_packets_marks_packet_stale_after_claim_change(tmp_path):
    from app.services.kbase_review_workspace import (
        generate_review_verification_packet,
        list_review_verification_packets,
        workspace_content_fingerprint,
    )

    workspace = _write_workspace(tmp_path / "review-workspace")
    generate_review_verification_packet(
        workspace,
        doc_id="claim:release-1-caffeine",
        expected_workspace_fingerprint=workspace_content_fingerprint(workspace),
        generated_at=NOW,
    )
    claims = [json.loads(line) for line in (workspace / "claims.jsonl").read_text().splitlines()]
    claims[0]["summary"] = "已更新的声明。"
    (workspace / "claims.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in claims),
        encoding="utf-8",
    )

    listed = list_review_verification_packets(workspace, doc_id="claim:release-1-caffeine")

    assert listed["items"][0]["status"] == "stale"
    assert listed["items"][0]["stale"] is True


def test_list_workspace_packets_returns_only_latest_duplicate_packet(tmp_path):
    from app.services.kbase_review_workspace import (
        generate_review_verification_packet,
        list_review_verification_packets,
        workspace_content_fingerprint,
    )

    workspace = _write_workspace(tmp_path / "review-workspace")
    fingerprint = workspace_content_fingerprint(workspace)
    for generated_at in (NOW, NOW + timedelta(minutes=5)):
        generate_review_verification_packet(
            workspace,
            doc_id="claim:release-1-caffeine",
            expected_workspace_fingerprint=fingerprint,
            generated_at=generated_at,
        )

    assert len((workspace / "verification_packets.jsonl").read_text().splitlines()) == 2
    listed = list_review_verification_packets(workspace, doc_id="claim:release-1-caffeine")

    assert listed["total"] == 1
    assert len(listed["items"]) == 1
    assert listed["items"][0]["generated_at"] == (NOW + timedelta(minutes=5)).isoformat()


def test_generate_workspace_packet_preserves_workspace_on_candidate_failure(tmp_path, monkeypatch):
    from app.services import kbase_review_workspace

    workspace = _write_workspace(tmp_path / "review-workspace")
    before = kbase_review_workspace.workspace_content_fingerprint(workspace)
    validation_results = iter([True, False])
    monkeypatch.setattr(
        kbase_review_workspace,
        "workspace_artifacts_valid",
        lambda _root: next(validation_results),
    )

    with pytest.raises(ValueError, match="candidate validation failed"):
        kbase_review_workspace.generate_review_verification_packet(
            workspace,
            doc_id="claim:release-1-caffeine",
            expected_workspace_fingerprint=before,
            generated_at=NOW,
        )

    assert kbase_review_workspace.workspace_content_fingerprint(workspace) == before
    assert not (workspace / "verification_packets.jsonl").exists()


def test_model_adapter_adds_strict_cited_recommendation_without_relaxing_checks():
    from app.services.kbase_claim_verification import (
        build_deterministic_verification_packet,
        enrich_verification_packet_with_model,
    )

    claim = _claim(
        evidence_level="B",
        metadata={
            **_claim()["metadata"],
            "external_sources": [{"source": "guideline:sleep-2025"}],
            "last_confirmed": "2026-03-01T00:00:00Z",
        },
    )
    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="1" * 64,
        generated_at=NOW,
    )
    requests = []

    result = enrich_verification_packet_with_model(
        packet,
        claim=claim,
        model_adapter=lambda request: requests.append(request)
        or {
            "decision": "needs_evidence",
            "confidence": 0.86,
            "rationale": "需要确认剂量和摄入时点是否适用于目标人群。",
            "citation_ids": ["citation-1"],
            "missing_evidence": ["dose_and_timing_scope"],
        },
    )

    assert result["status"] == "ready"
    assert result["proposed_decision"] == "needs_evidence"
    assert result["model_proposal"]["confidence"] == 0.86
    assert result["model_proposal"]["citation_ids"] == ["citation-1"]
    assert requests[0]["claim"]["statement"] == claim["summary"]
    assert "body" not in requests[0]


@pytest.mark.parametrize(
    "response,error_code",
    [
        (
            {
                "decision": "auto_publish",
                "confidence": 0.9,
                "rationale": "invalid",
                "citation_ids": ["citation-1"],
                "missing_evidence": [],
            },
            "invalid_model_decision",
        ),
        (
            {
                "decision": "approve",
                "confidence": 0.9,
                "rationale": "missing citations",
                "citation_ids": [],
                "missing_evidence": [],
            },
            "missing_model_citations",
        ),
        (
            {
                "decision": "approve",
                "confidence": 0.9,
                "rationale": "unknown citation",
                "citation_ids": ["citation-unknown"],
                "missing_evidence": [],
            },
            "unsupported_model_citations",
        ),
        (
            {
                "decision": "approve",
                "confidence": 0.69,
                "rationale": "low confidence",
                "citation_ids": ["citation-1"],
                "missing_evidence": [],
            },
            "low_model_confidence",
        ),
    ],
)
def test_model_adapter_blocks_invalid_or_untrusted_output(response, error_code):
    from app.services.kbase_claim_verification import (
        build_deterministic_verification_packet,
        enrich_verification_packet_with_model,
    )

    claim = _claim()
    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="2" * 64,
        generated_at=NOW,
    )

    result = enrich_verification_packet_with_model(
        packet,
        claim=claim,
        model_adapter=lambda _request: response,
    )

    assert result["status"] == "blocked"
    assert result["model_status"] == "blocked"
    assert result["model_error"] == error_code


def test_model_adapter_error_fails_closed():
    from app.services.kbase_claim_verification import (
        build_deterministic_verification_packet,
        enrich_verification_packet_with_model,
    )

    claim = _claim()
    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="3" * 64,
        generated_at=NOW,
    )

    def fail(_request):
        raise TimeoutError("provider timeout")

    result = enrich_verification_packet_with_model(packet, claim=claim, model_adapter=fail)

    assert result["status"] == "blocked"
    assert result["model_status"] == "error"
    assert result["model_error"] == "model_adapter_failed"
    assert "provider timeout" not in json.dumps(result)


def test_deterministic_blocker_overrides_model_approval():
    from app.services.kbase_claim_verification import (
        build_deterministic_verification_packet,
        enrich_verification_packet_with_model,
    )

    claim = _claim(sources=[])
    packet = build_deterministic_verification_packet(
        claim,
        workspace_fingerprint="4" * 64,
        generated_at=NOW,
    )

    result = enrich_verification_packet_with_model(
        packet,
        claim=claim,
        model_adapter=lambda _request: {
            "decision": "approve",
            "confidence": 0.99,
            "rationale": "approve",
            "citation_ids": ["citation-1"],
            "missing_evidence": [],
        },
    )

    assert result["status"] == "blocked"
    assert result["proposed_decision"] == "reject"
    assert result["blocking_reasons"] == ["missing_source_references"]


def _write_workspace(root):
    from app.services.system_knowledge_ingest import ARTIFACT_FILES

    root.mkdir(parents=True)
    claim = _claim()
    rows = {
        "pages.jsonl": [{"doc_id": "page:release-1", "metadata": {"review_status": "draft"}}],
        "claims.jsonl": [claim],
        "relations.jsonl": [
            {
                "src_doc_id": "page:release-1",
                "dst_doc_id": claim["doc_id"],
                "relation": "supports",
            }
        ],
    }
    counts = {}
    for name in ARTIFACT_FILES:
        values = rows.get(name, [])
        (root / name).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in values),
            encoding="utf-8",
        )
        counts[name.removesuffix(".jsonl")] = len(values)
    (root / "manifest.json").write_text(
        json.dumps({"counts": counts, "ingest": {"review_status": "draft"}}) + "\n",
        encoding="utf-8",
    )
    (root / "draft_manifest.json").write_text(
        json.dumps({"status": "draft", "requires_review": True, "serving_allowed": False}) + "\n",
        encoding="utf-8",
    )
    return root
