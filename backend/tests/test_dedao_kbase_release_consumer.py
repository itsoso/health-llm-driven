from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
from threading import Event, Thread
from unittest.mock import patch

import pytest

from app.models.system_knowledge import KBAudit, KBDocument


def _release_payload(release_id: str = "release-abc", *, usage_policy: str = "evidence_only") -> dict:
    return {
        "version": "1",
        "release_id": release_id,
        "book_id": "source-health-1",
        "content_hash": "content-123",
        "usage_policy": usage_policy,
        "book": {"book_id": "source-health-1", "title": "睡眠与咖啡因", "content_hash": "content-123"},
        "analysis": {
            "summary": "咖啡因暴露可能延后入睡。",
            "claims": [
                {
                    "id": "claim-1",
                    "statement": "晚间咖啡因可能延长睡眠潜伏期。",
                    "citation_ids": ["citation-1"],
                    "confidence": 0.82,
                    "scope": ["成年人"],
                    "risk_level": "high",
                }
            ],
            "risks": [],
            "actions": [],
        },
        "quality": {"decision": "pass", "usage_policy": usage_policy},
        "sources": [{"id": "citation-1", "title": "原文片段", "content": "原文证据"}],
        "citations": [{"citation_id": "citation-1", "label": "原文片段"}],
        "created_at": "2026-07-12T12:00:00Z",
    }


def _agent_package_payload(
    *,
    release: dict | None = None,
    package_id: str = "health-book",
    version: str = "1.0.0",
) -> dict:
    release = release or _release_payload()
    content_hash = f"sha256:agent-package-{package_id}"
    return {
        "schema_version": "agent-package.v1",
        "package_id": package_id,
        "version": version,
        "content_hash": content_hash,
        "lifecycle_state": "published",
        "published_at": "2026-07-19T12:00:00Z",
        "releases": [
            {
                "release_id": release["release_id"],
                "content_hash": release["content_hash"],
                "citation_ids": ["citation-1"],
            }
        ],
        "retrieval_policy": {
            "strategy": "hybrid",
            "allowed_source_types": ["dedao_ebook"],
            "require_citations": True,
            "max_context_chunks": 4,
        },
        "model_policy": {
            "preferred_capability": "grounded_reasoning",
            "max_cost_usd": 0.1,
            "timeout_ms": 30_000,
        },
        "prompt_profiles": [{"profile_id": "health-evidence", "output_schema": "claim-set.v1"}],
        "tool_policy": {"tools": []},
        "safety_policy": {
            "usage_policy": "evidence_only",
            "abstention_reasons": ["insufficient_evidence", "conflicting_evidence"],
            "escalation_target": "health-domain-review",
        },
        "evaluation_policy": {
            "suite_version": "health-agent-eval.v1",
            "minimum_scores": {"citations": 1.0, "abstention": 1.0},
        },
        "evaluation": {
            "schema_version": "agent-evaluation-report.v1",
            "package_id": package_id,
            "package_content_hash": content_hash,
            "suite_version": "health-agent-eval.v1",
            "input_hash": f"sha256:evaluation-input-{package_id}",
            "evaluator_version": "deterministic-agent-evaluator.v1",
            "metrics": {"citations": 1.0, "abstention": 1.0},
            "passed": True,
            "evaluated_at": "2026-07-19T11:59:00Z",
        },
        "ui_manifest": {"capabilities": ["evidence"]},
    }


def test_release_client_lists_fetches_and_posts_feedback():
    from app.integrations.dedao_kbase_release_consumer import DedaoKBaseReleaseClient

    release = _release_payload()
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _release_handler(release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = DedaoKBaseReleaseClient(
            f"http://127.0.0.1:{server.server_port}", auth_token="secret-token"
        )
        records = client.list_releases(after="release-old", limit=10)
        detail = client.get_release("release-abc")
        feedback = client.post_feedback(
            "release-abc",
            event_id="sync-release-abc",
            consumer="health-llm-driven",
            outcome="used",
            reason_code="used_for_answer",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert records[0]["release_id"] == "release-abc"
    assert detail["analysis"]["claims"][0]["citation_ids"] == ["citation-1"]
    assert feedback["status"] == "accepted"
    assert requests[0][:2] == ("GET", "/api/knowledge/releases?after=release-old&limit=10")
    assert requests[-1][2]["outcome"] == "used"


class _FeedbackClient:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def post_feedback(self, release_id, **payload):
        self.calls.append((release_id, payload))
        if self.fail:
            raise RuntimeError("producer unavailable")
        return {"status": "accepted"}


def test_feedback_flusher_groups_actual_use_and_rejection_and_advances_past_no_signal(db):
    from app.tasks.system_knowledge_lifecycle import flush_dedao_kbase_feedback_once

    db.add_all(
        [
            KBDocument(
                doc_id="claim:health-a",
                doc_type="claim",
                metadata_json={
                    "origin": "dedao-kbase-release",
                    "release_id": "release-a",
                    "release_claim_id": "claim-a",
                },
            ),
            KBDocument(
                doc_id="claim:health-b",
                doc_type="claim",
                metadata_json={
                    "origin": "dedao-kbase-release",
                    "release_id": "release-a",
                    "release_claim_id": "claim-b",
                },
            ),
            KBDocument(
                doc_id="claim:health-package",
                doc_type="claim",
                metadata_json={
                    "origin": "dedao-kbase-agent-package",
                    "release_id": "release-a",
                    "release_claim_id": "claim-package",
                    "package_id": "health-book",
                    "package_version": "1.0.0",
                },
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            KBAudit(
                op="kb_citation_usage",
                actor="system",
                diff={"used_ids": ["claim:health-a", "claim:health-b", "claim:health-package"]},
            ),
            KBAudit(
                doc_id="claim:health-rejected",
                op="dedao_kbase_claim_adjudicated",
                actor="admin:1",
                diff={
                    "decision": "background_only",
                    "release_id": "release-b",
                    "release_claim_id": "claim-rejected",
                },
            ),
            KBAudit(
                doc_id="claim:health-needs-evidence",
                op="dedao_kbase_verification_applied",
                actor="admin:1",
                diff={
                    "decision": "needs_evidence",
                    "release_id": "release-c",
                    "release_claim_id": "claim-pending",
                },
            ),
        ]
    )
    db.commit()
    expected_cursor = db.query(KBAudit.id).order_by(KBAudit.id.desc()).first()[0]
    client = _FeedbackClient()

    result = flush_dedao_kbase_feedback_once(
        db,
        base_url="https://kbase.example",
        auth_token="secret",
        client=client,
        actor="test",
    )

    assert result == {
        "status": "flushed",
        "cursor": expected_cursor,
        "scanned": 3,
        "posted": 2,
        "outcomes": {"rejected": 1, "used": 1},
    }
    assert [(release_id, payload["outcome"], payload.get("claim_ids"), payload.get("reason_code"))
            for release_id, payload in client.calls] == [
        ("release-a", "used", ["claim-a", "claim-b", "claim-package"], "used_for_answer"),
        ("release-b", "rejected", ["claim-rejected"], "out_of_scope"),
    ]
    assert all("note" not in payload and "actor" not in payload for _, payload in client.calls)
    assert flush_dedao_kbase_feedback_once(
        db,
        base_url="https://kbase.example",
        auth_token="secret",
        client=client,
        actor="test",
    )["status"] == "up_to_date"
    assert len(client.calls) == 2


def test_feedback_flusher_keeps_cursor_and_reuses_event_id_after_failure(db):
    from app.tasks.system_knowledge_lifecycle import flush_dedao_kbase_feedback_once

    db.add(
        KBAudit(
            doc_id="claim:health-rejected",
            op="dedao_kbase_claim_adjudicated",
            actor="admin:1",
            diff={
                "decision": "reject",
                "release_id": "release-a",
                "release_claim_id": "claim-a",
            },
        )
    )
    db.commit()
    failing = _FeedbackClient(fail=True)

    with pytest.raises(RuntimeError, match="producer unavailable"):
        flush_dedao_kbase_feedback_once(
            db,
            base_url="https://kbase.example",
            auth_token="secret",
            client=failing,
            actor="test",
        )

    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_feedback_flush").count() == 0
    retry = _FeedbackClient()
    flush_dedao_kbase_feedback_once(
        db,
        base_url="https://kbase.example",
        auth_token="secret",
        client=retry,
        actor="test",
    )
    assert retry.calls[0][1]["event_id"] == failing.calls[0][1]["event_id"]


def test_compile_release_preserves_evidence_only_policy_and_provenance(tmp_path):
    from app.integrations.dedao_kbase_release_consumer import compile_knowledge_release_artifacts

    result = compile_knowledge_release_artifacts(
        release=_release_payload(),
        base_artifact_dir=tmp_path / "artifacts",
        source_root=tmp_path / "source",
        now=datetime(2026, 7, 12, 13, tzinfo=UTC),
    )

    assert [row["doc_id"] for row in result.claims] == ["claim:release-abc-claim-1"]
    claim = result.claims[0]
    assert claim["metadata"]["origin"] == "dedao-kbase-release"
    assert claim["metadata"]["release_id"] == "release-abc"
    assert claim["metadata"]["release_claim_id"] == "claim-1"
    assert claim["metadata"]["usage_policy"] == "evidence_only"
    assert claim["metadata"]["review_status"] == "draft"
    assert claim["metadata"]["citation_ids"] == ["citation-1"]
    assert result.manifest["ingest"]["serving_allowed"] is False
    assert result.relations[0]["metadata"]["release_claim_id"] == "claim-1"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda release: release.update(quality={"decision": "quarantine"}), "quality decision"),
        (
            lambda release: release["analysis"]["claims"].append(dict(release["analysis"]["claims"][0])),
            "duplicate claim id",
        ),
    ],
)
def test_compile_release_rejects_non_publishable_contracts(tmp_path, mutate, message):
    from app.integrations.dedao_kbase_release_consumer import compile_knowledge_release_artifacts

    release = _release_payload()
    mutate(release)
    with pytest.raises(ValueError, match=message):
        compile_knowledge_release_artifacts(
            release=release,
            base_artifact_dir=tmp_path / "artifacts",
            source_root=tmp_path / "source",
        )


def test_agent_package_client_lists_and_fetches_published_version():
    from app.integrations.dedao_kbase_release_consumer import DedaoKBaseReleaseClient

    release = _release_payload()
    package = _agent_package_payload(release=release)
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _agent_package_handler(package, release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = DedaoKBaseReleaseClient(
            f"http://127.0.0.1:{server.server_port}", auth_token="secret-token"
        )
        records = client.list_agent_packages(after="previous@0.9.0", limit=1)
        detail = client.get_agent_package("health-book", version="1.0.0")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert records[0]["package_id"] == "health-book"
    assert detail["safety_policy"]["usage_policy"] == "evidence_only"
    assert requests[:2] == [
        ("GET", "/api/agent-packages?after=previous%400.9.0&limit=1", None),
        ("GET", "/api/agent-packages/health-book?version=1.0.0", None),
    ]


def test_compile_agent_package_preserves_review_and_safety_provenance(tmp_path):
    from app.integrations.dedao_kbase_release_consumer import compile_agent_package_artifacts

    release = _release_payload()
    package = _agent_package_payload(release=release)
    result = compile_agent_package_artifacts(
        package=package,
        releases=[release],
        base_artifact_dir=tmp_path / "artifacts",
        source_root=tmp_path / "source",
        now=datetime(2026, 7, 19, 13, tzinfo=UTC),
    )

    assert result.manifest["ingest"] == {
        "pipeline": "dedao_kbase_agent_package_v1",
        "review_status": "draft",
        "requires_review": True,
        "serving_allowed": False,
    }
    assert result.manifest["agent_package"] == {
        "package_id": "health-book",
        "version": "1.0.0",
        "content_hash": "sha256:agent-package-health-book",
        "evaluation_status": "passed",
        "evaluation_suite_version": "health-agent-eval.v1",
        "evaluation_input_hash": "sha256:evaluation-input-health-book",
        "evaluation_evaluator_version": "deterministic-agent-evaluator.v1",
        "evaluated_at": "2026-07-19T11:59:00Z",
        "release_ids": ["release-abc"],
    }
    claim = result.claims[0]
    assert claim["metadata"]["origin"] == "dedao-kbase-agent-package"
    assert claim["metadata"]["package_version"] == "1.0.0"
    assert claim["metadata"]["release_id"] == "release-abc"
    assert claim["metadata"]["evaluation_status"] == "passed"
    assert claim["metadata"]["evaluation_input_hash"] == "sha256:evaluation-input-health-book"
    assert claim["metadata"]["safety_flags"] == {
        "usage_policy": "evidence_only",
        "abstention_reasons": ["insufficient_evidence", "conflicting_evidence"],
        "escalation_target": "health-domain-review",
    }
    assert result.protocols == []
    assert result.contraindications == []


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda package, release: package.update(lifecycle_state="superseded"), "stale"),
        (
            lambda package, release: package["releases"][0].update(content_hash="content-conflict"),
            "conflict",
        ),
        (lambda package, release: package.update(evaluation_policy={}), "unevaluated"),
        (lambda package, release: package.pop("evaluation"), "unevaluated"),
        (
            lambda package, release: package["safety_policy"].update(usage_policy="standard"),
            "non_evidence_only",
        ),
    ],
)
def test_compile_agent_package_holds_ineligible_packages(tmp_path, mutate, reason):
    from app.integrations.dedao_kbase_release_consumer import compile_agent_package_artifacts

    release = _release_payload()
    package = _agent_package_payload(release=release)
    mutate(package, release)

    with pytest.raises(ValueError, match=rf"held.*{reason}"):
        compile_agent_package_artifacts(
            package=package,
            releases=[release],
            base_artifact_dir=tmp_path / "artifacts",
            source_root=tmp_path / "source",
        )


def test_agent_package_sync_writes_draft_without_serving_or_personal_data_mutation(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_agent_packages_draft_once

    release = _release_payload()
    package = _agent_package_payload(release=release)
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _agent_package_handler(package, release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "agent-package-review"
    _write_canonical_artifacts(canonical, marker="trusted-base")
    try:
        result = sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:agent-package-sync",
            limit=1,
            now=datetime(2026, 7, 19, 13, tzinfo=UTC),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["status"] == "draft_written"
    assert result["cursor"] == "health-book@1.0.0"
    assert result["package_count"] == 1
    assert result["held_packages"] == []
    assert result["gate"]["serving_allowed"] is False
    assert json.loads((canonical / "pages.jsonl").read_text().splitlines()[0])["title"] == "trusted-base"
    draft_claim = json.loads((workspace / "claims.jsonl").read_text().splitlines()[-1])
    assert draft_claim["metadata"]["package_id"] == "health-book"
    assert draft_claim["metadata"]["review_status"] == "draft"
    assert db.query(KBDocument).count() == 0
    audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_agent_package_sync_draft").one()
    assert audit.diff["gate"]["serving_allowed"] is False


def test_agent_package_sync_preserves_previous_unreviewed_batch(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_agent_packages_draft_once

    release_one = _release_payload("release-one")
    release_two = _release_payload("release-two")
    packages = [
        _agent_package_payload(release=release_one, package_id="health-book-one"),
    ]
    releases = {release_one["release_id"]: release_one, release_two["release_id"]: release_two}
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _agent_package_sequence_handler(packages, releases, requests),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "agent-package-review"
    _write_canonical_artifacts(canonical, marker="trusted-base")
    try:
        first = sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:agent-package-sync",
            limit=1,
        )
        packages.append(
            _agent_package_payload(release=release_two, package_id="health-book-two")
        )
        second = sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:agent-package-sync",
            limit=1,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first["mode"] == "rebuild"
    assert second["mode"] == "incremental"
    assert second["cursor"] == "health-book-two@1.0.0"
    claims = [json.loads(line) for line in (workspace / "claims.jsonl").read_text().splitlines()]
    assert {claim["metadata"]["package_id"] for claim in claims} == {
        "health-book-one",
        "health-book-two",
    }
    manifest = json.loads((workspace / "draft_manifest.json").read_text())
    assert [item["package_id"] for item in manifest["agent_packages"]] == [
        "health-book-one",
        "health-book-two",
    ]


def test_agent_package_sync_retires_superseded_version_from_incremental_workspace(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_agent_packages_draft_once

    release_one = _release_payload("release-one")
    release_two = _release_payload("release-two")
    first_package = _agent_package_payload(release=release_one, version="1.0.0")
    second_package = _agent_package_payload(release=release_two, version="2.0.0")
    second_package["supersedes"] = "health-book@1.0.0"
    packages = [first_package]
    releases = {release_one["release_id"]: release_one, release_two["release_id"]: release_two}
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _agent_package_sequence_handler(packages, releases, requests),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "agent-package-review"
    _write_canonical_artifacts(canonical, marker="trusted-base")
    try:
        first = sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:agent-package-sync",
            limit=1,
        )
        packages.append(second_package)
        second = sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:agent-package-sync",
            limit=1,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first["cursor"] == "health-book@1.0.0"
    assert second["mode"] == "incremental"
    assert second["cursor"] == "health-book@2.0.0"
    claims = [json.loads(line) for line in (workspace / "claims.jsonl").read_text().splitlines()]
    assert {claim["metadata"]["release_id"] for claim in claims} == {"release-two"}
    assert {
        (lineage["package_id"], lineage["version"])
        for claim in claims
        for lineage in claim["metadata"]["agent_package_lineage"]
    } == {("health-book", "2.0.0")}
    manifest = json.loads((workspace / "draft_manifest.json").read_text())
    assert [(item["package_id"], item["version"]) for item in manifest["agent_packages"]] == [
        ("health-book", "2.0.0")
    ]


def test_agent_package_sync_preserves_lineage_for_sequential_overlapping_packages(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_agent_packages_draft_once

    release = _release_payload()
    packages = [_agent_package_payload(release=release, package_id="health-book-one")]
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _agent_package_sequence_handler(packages, {release["release_id"]: release}, requests),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "agent-package-review"
    _write_canonical_artifacts(canonical, marker="trusted-base")
    try:
        sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:agent-package-sync",
            limit=1,
        )
        packages.append(_agent_package_payload(release=release, package_id="health-book-two"))
        sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:agent-package-sync",
            limit=1,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    claim = json.loads((workspace / "claims.jsonl").read_text().splitlines()[-1])
    assert [
        item["package_id"] for item in claim["metadata"]["agent_package_lineage"]
    ] == ["health-book-one", "health-book-two"]
    for manifest_name in ("manifest.json", "draft_manifest.json"):
        manifest = json.loads((workspace / manifest_name).read_text())
        assert [item["package_id"] for item in manifest["agent_packages"]] == [
            "health-book-one",
            "health-book-two",
        ]


def test_overlapping_agent_packages_preserve_all_package_lineage(tmp_path):
    from app.integrations.dedao_kbase_release_consumer import (
        combine_release_results,
        compile_agent_package_artifacts,
    )

    release = _release_payload()
    first_package = _agent_package_payload(release=release, package_id="health-book-one")
    second_package = _agent_package_payload(release=release, package_id="health-book-two")
    first = compile_agent_package_artifacts(
        package=first_package,
        releases=[release],
        base_artifact_dir=tmp_path / "artifacts",
        source_root=tmp_path / "source",
    )
    second = compile_agent_package_artifacts(
        package=second_package,
        releases=[deepcopy(release)],
        base_artifact_dir=tmp_path / "artifacts",
        source_root=tmp_path / "source",
    )

    combined = combine_release_results([first, second])

    lineage = combined.claims[0]["metadata"]["agent_package_lineage"]
    assert [item["package_id"] for item in lineage] == ["health-book-one", "health-book-two"]
    assert [item["package_id"] for item in combined.manifest["agent_packages"]] == [
        "health-book-one",
        "health-book-two",
    ]


def test_agent_package_draft_sync_is_explicitly_registered_not_auto_published():
    from app.celery_app import celery_app
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_agent_packages_draft  # noqa: F401

    task_name = "app.tasks.system_knowledge_lifecycle.sync_dedao_kbase_agent_packages_draft"
    assert task_name in celery_app.tasks
    assert all(
        entry.get("task") != task_name
        for entry in (celery_app.conf.beat_schedule or {}).values()
    )


def test_incremental_release_sync_writes_draft_and_advances_cursor_without_false_usage_feedback(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_releases_draft_once

    release = _release_payload()
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _release_handler(release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=tmp_path / "artifacts",
            source_root=tmp_path / "source",
            actor="test:release-sync",
            limit=1,
            now=datetime(2026, 7, 12, 13, tzinfo=UTC),
        )
        resumed = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=tmp_path / "artifacts",
            source_root=tmp_path / "source",
            actor="test:release-sync",
            limit=1,
            now=datetime(2026, 7, 12, 14, tzinfo=UTC),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["status"] == "draft_written"
    assert result["release_count"] == 1
    assert result["cursor"] == "release-abc"
    assert result["gate"]["serving_allowed"] is False
    audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_release_sync_draft").one()
    assert audit.diff["cursor"] == "release-abc"
    assert resumed["status"] == "up_to_date"
    assert resumed["mode"] == "incremental"
    assert resumed["cursor"] == "release-abc"
    assert resumed["release_count"] == 0
    assert any("after=release-abc" in path for method, path, _ in requests if method == "GET")
    assert not any(method == "POST" for method, _, _ in requests)


def test_release_sync_replays_when_persistent_workspace_is_lost(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_releases_draft_once

    release = _release_payload()
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _release_handler(release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(canonical, marker="base-v1")
    try:
        first = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:release-sync",
            limit=1,
        )
        shutil.rmtree(workspace)
        replayed = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
            actor="test:release-sync",
            limit=1,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first["mode"] == "rebuild"
    assert replayed["status"] == "draft_written"
    assert replayed["mode"] == "rebuild"
    assert replayed["previous_cursor"] == "release-abc"
    assert (workspace / "draft_manifest.json").exists()
    assert sum("after=&" in path for method, path, _ in requests if method == "GET") == 2
    assert sum("after=release-abc" in path for method, path, _ in requests if method == "GET") == 2


def test_release_sync_rebuilds_when_canonical_base_changes(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_releases_draft_once
    from app.services.system_knowledge_ingest import review_draft_artifacts
    from app.services.kbase_review_workspace import workspace_content_fingerprint

    release = _release_payload()
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _release_handler(release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(canonical, marker="base-v1")
    try:
        first = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
        )
        agent_workspace = workspace / "agent-packages"
        _write_canonical_artifacts(agent_workspace, marker="agent-review")
        agent_fingerprint = workspace_content_fingerprint(agent_workspace)
        _write_canonical_artifacts(canonical, marker="base-v2")
        rebuilt = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert rebuilt["mode"] == "rebuild"
    assert rebuilt["base_fingerprint"] != first["base_fingerprint"]
    pages = [json.loads(line) for line in (workspace / "pages.jsonl").read_text().splitlines()]
    assert any(page.get("title") == "base-v2" for page in pages)
    assert workspace_content_fingerprint(agent_workspace) == agent_fingerprint
    agent_pages = [json.loads(line) for line in (agent_workspace / "pages.jsonl").read_text().splitlines()]
    assert any(page.get("title") == "agent-review" for page in agent_pages)
    assert rebuilt["gate"]["relations"]["missing"] == 0
    review = review_draft_artifacts(workspace, reviewer="test:reviewer")
    assert review["serving_allowed"] is True


def test_release_sync_failed_rebuild_preserves_previous_workspace_and_cursor(tmp_path, db):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_releases_draft_once

    release = _release_payload()
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _release_handler(release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(canonical, marker="base-v1")
    try:
        sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
        )
        before = (workspace / "pages.jsonl").read_bytes()
        _write_canonical_artifacts(canonical, marker="base-v2")
        with patch(
            "app.tasks.system_knowledge_lifecycle.write_draft_artifacts",
            side_effect=RuntimeError("injected rebuild failure"),
        ), pytest.raises(RuntimeError, match="injected rebuild failure"):
            sync_dedao_kbase_releases_draft_once(
                db,
                base_url=f"http://127.0.0.1:{server.server_port}",
                auth_token="secret-token",
                artifact_dir=workspace,
                base_artifact_dir=canonical,
                source_root=tmp_path / "source",
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert (workspace / "pages.jsonl").read_bytes() == before
    audits = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_release_sync_draft").all()
    assert len(audits) == 1
    assert audits[0].diff["cursor"] == "release-abc"


@pytest.mark.parametrize("damage", ["stale_cursor", "missing_artifact", "count_mismatch"])
def test_release_sync_rebuilds_when_workspace_state_disagrees_with_audit(tmp_path, db, damage):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_releases_draft_once

    release = _release_payload()
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _release_handler(release, requests))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    canonical = tmp_path / "canonical"
    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(canonical, marker="base-v1")
    try:
        sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
        )
        if damage == "stale_cursor":
            manifest_path = workspace / "draft_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["cursor"] = "release-old"
            manifest_path.write_text(json.dumps(manifest))
        else:
            if damage == "missing_artifact":
                (workspace / "claims.jsonl").unlink()
            else:
                manifest_path = workspace / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest["counts"]["claims"] += 1
                manifest_path.write_text(json.dumps(manifest))
        repaired = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert repaired["mode"] == "rebuild"
    assert repaired["status"] == "draft_written"
    assert (workspace / "claims.jsonl").exists()


@pytest.mark.parametrize("layout", ["equal", "review_inside_base", "base_inside_review"])
def test_release_sync_rejects_review_workspace_overlapping_canonical_seed(tmp_path, db, layout):
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_releases_draft_once

    if layout == "equal":
        canonical = workspace = tmp_path / "canonical"
    elif layout == "review_inside_base":
        canonical = tmp_path / "canonical"
        workspace = canonical / "review-workspace"
    else:
        workspace = tmp_path / "review-workspace"
        canonical = workspace / "canonical"
    _write_canonical_artifacts(canonical, marker="base-v1")

    with pytest.raises(ValueError, match="must not overlap canonical"):
        sync_dedao_kbase_releases_draft_once(
            db,
            base_url="https://kbase.example.test",
            auth_token="secret-token",
            artifact_dir=workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
        )


def test_review_bundle_uses_dedicated_release_workspace(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.system_knowledge_service import get_dedao_kbase_draft_review_bundle

    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(workspace, marker="persistent-review")
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(workspace))

    bundle = get_dedao_kbase_draft_review_bundle()

    assert bundle["artifact_dir"] == str(workspace)
    assert bundle["preview"]["pages"][0]["title"] == "persistent-review"
    assert len(bundle["workspace_fingerprint"]) == 64


def test_review_approval_rejects_workspace_changed_after_preview(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.system_knowledge_service import (
        approve_dedao_kbase_draft_review,
        get_dedao_kbase_draft_review_bundle,
    )

    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(workspace, marker="reviewed-version")
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(workspace))
    bundle = get_dedao_kbase_draft_review_bundle()
    with (workspace / "pages.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")

    with pytest.raises(ValueError, match="changed since preview"):
        approve_dedao_kbase_draft_review(
            reviewer="reviewer:test",
            expected_workspace_fingerprint=bundle["workspace_fingerprint"],
        )


def test_review_bundle_rejects_manifest_count_mismatch(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.system_knowledge_service import get_dedao_kbase_draft_review_bundle

    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(workspace, marker="truncated-review")
    manifest_path = workspace / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["counts"]["pages"] = 2
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(workspace))

    with pytest.raises(ValueError, match="incomplete or corrupt"):
        get_dedao_kbase_draft_review_bundle()


def test_workspace_lock_serializes_concurrent_writers(tmp_path):
    from app.tasks.system_knowledge_lifecycle import _workspace_lock

    workspace = tmp_path / "review-workspace"
    first_acquired = Event()
    release_first = Event()
    order: list[str] = []

    def first_writer() -> None:
        with _workspace_lock(workspace):
            order.append("first-enter")
            first_acquired.set()
            release_first.wait(timeout=2)
            order.append("first-exit")

    def second_writer() -> None:
        first_acquired.wait(timeout=2)
        with _workspace_lock(workspace):
            order.append("second-enter")

    first = Thread(target=first_writer)
    second = Thread(target=second_writer)
    first.start()
    second.start()
    assert first_acquired.wait(timeout=2)
    assert order == ["first-enter"]
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert order == ["first-enter", "first-exit", "second-enter"]


def test_release_and_agent_package_workspaces_share_one_lock(tmp_path):
    from app.services.kbase_review_workspace import review_workspace_lock

    release_workspace = tmp_path / "review-workspace"
    agent_workspace = release_workspace / "agent-packages"
    agent_acquired = Event()

    def agent_writer() -> None:
        with review_workspace_lock(agent_workspace):
            agent_acquired.set()

    with review_workspace_lock(release_workspace):
        writer = Thread(target=agent_writer)
        writer.start()
        assert agent_acquired.wait(timeout=0.1) is False

    assert agent_acquired.wait(timeout=2)
    writer.join(timeout=2)
    assert writer.is_alive() is False


def test_configured_release_root_symlink_uses_one_workspace_for_sync_and_review(
    tmp_path,
    db,
    monkeypatch,
):
    from app.config import settings
    from app.services.kbase_review_workspace import review_workspace_lock
    from app.services.system_knowledge_service import _configured_system_kb_artifact_dir
    from app.tasks.system_knowledge_lifecycle import (
        _dedao_kbase_review_artifact_dir,
        sync_dedao_kbase_releases_draft_once,
    )

    physical_workspace = tmp_path / "physical-review-workspace"
    physical_workspace.mkdir()
    configured_workspace = tmp_path / "configured-review-workspace"
    configured_workspace.symlink_to(physical_workspace, target_is_directory=True)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(configured_workspace))

    sync_workspace = _dedao_kbase_review_artifact_dir()
    review_workspace = _configured_system_kb_artifact_dir(workspace="release")
    assert sync_workspace == physical_workspace.resolve()
    assert review_workspace == physical_workspace.resolve()

    review_acquired = Event()

    def review_reader() -> None:
        with review_workspace_lock(review_workspace):
            review_acquired.set()

    with review_workspace_lock(sync_workspace):
        reader = Thread(target=review_reader)
        reader.start()
        assert review_acquired.wait(timeout=0.1) is False

    assert review_acquired.wait(timeout=2)
    reader.join(timeout=2)
    assert reader.is_alive() is False

    release = _release_payload()
    requests: list[tuple[str, str, dict | None]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _release_handler(release, requests))
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    canonical = tmp_path / "canonical"
    _write_canonical_artifacts(canonical, marker="base-v1")
    try:
        result = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=sync_workspace,
            base_artifact_dir=canonical,
            source_root=tmp_path / "source",
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    assert result["status"] == "draft_written"
    assert Path(result["artifact_dir"]) == physical_workspace.resolve()
    assert configured_workspace.is_symlink()
    assert (review_workspace / "draft_manifest.json").is_file()


def test_review_bundle_recovers_workspace_backup_before_read(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.kbase_review_workspace import workspace_backup_path
    from app.services.system_knowledge_service import get_dedao_kbase_draft_review_bundle

    workspace = tmp_path / "review-workspace"
    backup = workspace_backup_path(workspace)
    _write_canonical_artifacts(backup, marker="recovered-review")
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(workspace))

    bundle = get_dedao_kbase_draft_review_bundle()

    assert workspace.exists()
    assert not backup.exists()
    assert bundle["preview"]["pages"][0]["title"] == "recovered-review"


def test_review_bundle_waits_for_active_workspace_sync(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.kbase_review_workspace import review_workspace_lock
    from app.services.system_knowledge_service import get_dedao_kbase_draft_review_bundle

    workspace = tmp_path / "review-workspace"
    _write_canonical_artifacts(workspace, marker="serialized-review")
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(workspace))
    review_started = Event()
    review_finished = Event()

    def read_review_bundle() -> None:
        review_started.set()
        get_dedao_kbase_draft_review_bundle()
        review_finished.set()

    with review_workspace_lock(workspace):
        review = Thread(target=read_review_bundle)
        review.start()
        assert review_started.wait(timeout=2)
        assert not review_finished.wait(timeout=0.1)

    review.join(timeout=2)
    assert review_finished.is_set()


def test_list_review_claims_returns_bounded_release_claims(tmp_path):
    from app.services.kbase_review_workspace import list_review_claims

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)

    result = list_review_claims(workspace, offset=0, limit=20)

    assert result["total"] == 1
    assert result["unresolved_count"] == 1
    assert result["decision_counts"] == {"unresolved": 1}
    assert result["offset"] == 0
    assert result["limit"] == 20
    assert len(result["workspace_fingerprint"]) == 64
    assert result["items"] == [
        {
            "doc_id": "claim:release-abc-claim-1",
            "title": "睡眠与咖啡因:晚间咖啡因可能延长睡眠潜伏期。",
            "summary": "晚间咖啡因可能延长睡眠潜伏期。",
            "evidence_level": "C",
            "confidence": 0.68,
            "sources": ["citation-1"],
            "source_count": 1,
            "review_status": "draft",
            "decision": None,
            "release_id": "release-abc",
            "release_claim_id": "claim-1",
            "usage_policy": "evidence_only",
            "citation_ids": ["citation-1"],
        }
    ]


def test_list_review_claims_includes_legacy_export_claim_without_release_id(tmp_path):
    from app.services.kbase_review_workspace import list_review_claims

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    claims = [json.loads(line) for line in (workspace / "claims.jsonl").read_text().splitlines()]
    claims[0]["metadata"].pop("release_id", None)
    (workspace / "claims.jsonl").write_text(
        "".join(json.dumps(claim, ensure_ascii=False) + "\n" for claim in claims),
        encoding="utf-8",
    )

    result = list_review_claims(workspace, offset=0, limit=20)

    assert result["total"] == 1
    assert result["unresolved_count"] == 1
    assert result["items"][0]["doc_id"] == "claim:release-abc-claim-1"
    assert result["items"][0]["release_id"] is None
    assert result["gate"]["serving_allowed"] is False


def test_adjudicate_review_claim_approves_with_structured_evidence(tmp_path):
    from app.services.kbase_review_workspace import (
        adjudicate_review_claim,
        list_review_claims,
        workspace_content_fingerprint,
    )

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    before = workspace_content_fingerprint(workspace)

    result = adjudicate_review_claim(
        workspace,
        doc_id="claim:release-abc-claim-1",
        decision="approve",
        reviewer="admin:7",
        expected_workspace_fingerprint=before,
        note="二源核验后通过",
        evidence={
            "kind": "research",
            "source": "pubmed:12345",
            "title": "Caffeine and sleep",
            "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
        },
        evidence_level="B",
        confidence=0.86,
    )

    assert result["decision"] == "approve"
    assert result["release_id"] == "release-abc"
    assert result["release_claim_id"] == "claim-1"
    assert result["workspace_fingerprint"] != before
    item = list_review_claims(workspace, offset=0, limit=20)["items"][0]
    assert item["decision"] == "approve"
    assert item["review_status"] == "reviewed"
    assert item["evidence_level"] == "B"
    assert item["confidence"] == 0.86
    assert item["source_count"] == 2
    ledger = [json.loads(line) for line in (workspace / "adjudications.jsonl").read_text().splitlines()]
    assert ledger[0]["doc_id"] == item["doc_id"]
    assert ledger[0]["decision"] == "approve"
    assert ledger[0]["reviewer"] == "admin:7"
    assert "body" not in ledger[0]


def test_adjudicate_review_claim_needs_evidence_remains_blocking(tmp_path):
    from app.services.kbase_review_workspace import adjudicate_review_claim, list_review_claims
    from app.services.system_knowledge_ingest import validate_artifact_review_gate

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    before = list_review_claims(workspace, offset=0, limit=20)["workspace_fingerprint"]

    adjudicate_review_claim(
        workspace,
        doc_id="claim:release-abc-claim-1",
        decision="needs_evidence",
        reviewer="admin:7",
        expected_workspace_fingerprint=before,
        note="需要独立临床来源",
    )

    item = list_review_claims(workspace, offset=0, limit=20)["items"][0]
    assert item["decision"] == "needs_evidence"
    assert item["review_status"] == "draft"
    assert validate_artifact_review_gate(workspace)["serving_allowed"] is False


@pytest.mark.parametrize("decision", ["reject", "background_only"])
def test_adjudicate_review_claim_excludes_claim_and_connected_relations(tmp_path, decision):
    from app.services.kbase_review_workspace import adjudicate_review_claim, list_review_claims

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    before = list_review_claims(workspace, offset=0, limit=20)["workspace_fingerprint"]

    result = adjudicate_review_claim(
        workspace,
        doc_id="claim:release-abc-claim-1",
        decision=decision,
        reviewer="admin:7",
        expected_workspace_fingerprint=before,
        note="不适用于 Health serving",
    )

    assert result["decision"] == decision
    assert list_review_claims(workspace, offset=0, limit=20)["items"] == []
    relations = [json.loads(line) for line in (workspace / "relations.jsonl").read_text().splitlines()]
    assert all(row.get("dst_doc_id") != "claim:release-abc-claim-1" for row in relations)
    ledger = json.loads((workspace / "adjudications.jsonl").read_text().strip())
    assert ledger["decision"] == decision


def test_adjudicate_review_claim_rejects_stale_fingerprint_without_mutation(tmp_path):
    from app.services.kbase_review_workspace import adjudicate_review_claim, workspace_content_fingerprint

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    before = workspace_content_fingerprint(workspace)

    with pytest.raises(ValueError, match="changed since preview"):
        adjudicate_review_claim(
            workspace,
            doc_id="claim:release-abc-claim-1",
            decision="approve",
            reviewer="admin:7",
            expected_workspace_fingerprint="0" * 64,
        )

    assert workspace_content_fingerprint(workspace) == before
    assert not (workspace / "adjudications.jsonl").exists()


def test_adjudicate_review_claim_preserves_workspace_when_candidate_validation_fails(tmp_path):
    from app.services.kbase_review_workspace import adjudicate_review_claim, workspace_content_fingerprint

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    before = workspace_content_fingerprint(workspace)

    with patch(
        "app.services.kbase_review_workspace.workspace_artifacts_valid",
        side_effect=[True, False],
    ):
        with pytest.raises(ValueError, match="candidate validation failed"):
            adjudicate_review_claim(
                workspace,
                doc_id="claim:release-abc-claim-1",
                decision="approve",
                reviewer="admin:7",
                expected_workspace_fingerprint=before,
            )

    assert workspace_content_fingerprint(workspace) == before
    assert not (workspace / "adjudications.jsonl").exists()


def test_finalize_review_workspace_rejects_unresolved_claim_without_mutation(tmp_path):
    from app.services.kbase_review_workspace import finalize_review_workspace, workspace_content_fingerprint

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    before = workspace_content_fingerprint(workspace)

    with pytest.raises(ValueError, match="unresolved claim decisions"):
        finalize_review_workspace(
            workspace,
            reviewer="admin:7",
            expected_workspace_fingerprint=before,
        )

    assert workspace_content_fingerprint(workspace) == before


def test_finalize_review_workspace_rejects_legacy_reviewed_claim_without_adjudication(tmp_path):
    from app.services.kbase_review_workspace import (
        finalize_review_workspace,
        list_review_claims,
        workspace_content_fingerprint,
    )

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    claims = [json.loads(line) for line in (workspace / "claims.jsonl").read_text().splitlines()]
    claims[-1]["metadata"]["review_status"] = "reviewed"
    (workspace / "claims.jsonl").write_text(
        "".join(json.dumps(claim, ensure_ascii=False) + "\n" for claim in claims),
        encoding="utf-8",
    )
    before = workspace_content_fingerprint(workspace)

    projection = list_review_claims(workspace, offset=0, limit=20)
    assert projection["items"][0]["review_status"] == "reviewed"
    assert projection["items"][0]["decision"] is None
    assert projection["unresolved_count"] == 1
    with pytest.raises(ValueError, match="unresolved claim decisions"):
        finalize_review_workspace(
            workspace,
            reviewer="admin:7",
            expected_workspace_fingerprint=before,
        )

    assert workspace_content_fingerprint(workspace) == before


def test_finalize_review_workspace_rejects_needs_evidence_claim(tmp_path):
    from app.services.kbase_review_workspace import (
        adjudicate_review_claim,
        finalize_review_workspace,
        workspace_content_fingerprint,
    )

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    first = adjudicate_review_claim(
        workspace,
        doc_id="claim:release-abc-claim-1",
        decision="needs_evidence",
        reviewer="admin:7",
        expected_workspace_fingerprint=workspace_content_fingerprint(workspace),
        note="awaiting independent source",
    )

    with pytest.raises(ValueError, match="unresolved claim decisions"):
        finalize_review_workspace(
            workspace,
            reviewer="admin:7",
            expected_workspace_fingerprint=first["workspace_fingerprint"],
        )


def test_finalize_review_workspace_allows_all_release_claims_to_be_excluded(tmp_path):
    from app.services.kbase_review_workspace import (
        adjudicate_review_claim,
        finalize_review_workspace,
        workspace_content_fingerprint,
    )

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    adjudicated = adjudicate_review_claim(
        workspace,
        doc_id="claim:release-abc-claim-1",
        decision="reject",
        reviewer="admin:7",
        expected_workspace_fingerprint=workspace_content_fingerprint(workspace),
        note="not suitable for Health serving",
    )

    result = finalize_review_workspace(
        workspace,
        reviewer="admin:7",
        expected_workspace_fingerprint=adjudicated["workspace_fingerprint"],
    )

    assert result["gate"]["serving_allowed"] is True
    assert (workspace / "claims.jsonl").read_text(encoding="utf-8") == ""


def test_finalize_review_workspace_resolves_containers_relations_and_gate(tmp_path):
    from app.services.kbase_review_workspace import (
        adjudicate_review_claim,
        finalize_review_workspace,
        workspace_content_fingerprint,
    )

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    adjudicated = adjudicate_review_claim(
        workspace,
        doc_id="claim:release-abc-claim-1",
        decision="approve",
        reviewer="admin:7",
        expected_workspace_fingerprint=workspace_content_fingerprint(workspace),
    )

    result = finalize_review_workspace(
        workspace,
        reviewer="admin:7",
        expected_workspace_fingerprint=adjudicated["workspace_fingerprint"],
        reviewed_at=datetime(2026, 7, 13, 15, tzinfo=UTC),
    )

    assert result["gate"]["serving_allowed"] is True
    assert result["workspace_fingerprint"] != adjudicated["workspace_fingerprint"]
    for name in ("pages.jsonl", "entities.jsonl", "claims.jsonl", "relations.jsonl"):
        for row in [json.loads(line) for line in (workspace / name).read_text().splitlines()]:
            assert row["metadata"]["review_status"] == "reviewed"
    manifest = json.loads((workspace / "manifest.json").read_text())
    assert manifest["review"]["status"] == "reviewed"
    assert manifest["review"]["reviewer"] == "admin:7"
    assert json.loads((workspace / "draft_manifest.json").read_text())["serving_allowed"] is True


def test_finalize_review_workspace_rejects_stale_fingerprint(tmp_path):
    from app.services.kbase_review_workspace import finalize_review_workspace, workspace_content_fingerprint

    workspace = tmp_path / "review-workspace"
    _write_release_review_workspace(workspace)
    before = workspace_content_fingerprint(workspace)

    with pytest.raises(ValueError, match="changed since preview"):
        finalize_review_workspace(
            workspace,
            reviewer="admin:7",
            expected_workspace_fingerprint="0" * 64,
        )

    assert workspace_content_fingerprint(workspace) == before


def _write_release_review_workspace(root: Path) -> None:
    from app.integrations.dedao_kbase_release_consumer import compile_knowledge_release_artifacts
    from app.services.system_knowledge_ingest import write_draft_artifacts

    result = compile_knowledge_release_artifacts(
        release=_release_payload(),
        base_artifact_dir=root,
        source_root=root.parent / "source",
        now=datetime(2026, 7, 12, 13, tzinfo=UTC),
    )
    write_draft_artifacts(
        result,
        root,
        extractor="test:release",
        created_at=datetime(2026, 7, 12, 13, tzinfo=UTC),
    )


def _write_canonical_artifacts(root: Path, *, marker: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pages.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "page:canonical",
                "doc_type": "article",
                "title": marker,
                "summary": marker,
                "metadata": {"review_status": "reviewed"},
            }
        )
        + "\n"
    )
    for name in (
        "entities.jsonl",
        "claims.jsonl",
        "protocols.jsonl",
        "contraindications.jsonl",
        "eval_cases.jsonl",
    ):
        (root / name).write_text("")
    (root / "relations.jsonl").write_text(
        json.dumps(
            {
                "src_doc_id": "page:canonical",
                "dst_doc_id": "page:canonical",
                "relation": "mentions",
                "confidence": 1.0,
            }
        )
        + "\n"
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "ingest": {"review_status": "reviewed"},
                "marker": marker,
                "counts": {
                    "pages": 1,
                    "entities": 0,
                    "claims": 0,
                    "protocols": 0,
                    "contraindications": 0,
                    "eval_cases": 0,
                    "relations": 1,
                },
            }
        )
        + "\n"
    )
    (root / "draft_manifest.json").write_text(
        json.dumps({"status": "reviewed", "requires_review": False, "serving_allowed": True}) + "\n"
    )


def _release_handler(release: dict, requests: list[tuple[str, str, dict | None]]):
    class ReleaseHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(("GET", self.path, None))
            if self.headers.get("Authorization") != "Bearer secret-token":
                self._write(401, {"error": "unauthorized"})
                return
            if self.path.startswith("/api/knowledge/releases?"):
                if "after=release-abc" in self.path:
                    self._write(200, {"releases": [], "next_cursor": ""})
                    return
                self._write(
                    200,
                    {"releases": [
                        {
                            "release_id": release["release_id"],
                            "book_id": release["book_id"],
                            "content_hash": release["content_hash"],
                            "usage_policy": release["usage_policy"],
                            "created_at": release["created_at"],
                        }
                    ], "next_cursor": release["release_id"]},
                )
                return
            if self.path == f"/api/knowledge/releases/{release['release_id']}":
                self._write(200, release)
                return
            self._write(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            requests.append(("POST", self.path, body))
            self._write(200, {"status": "accepted"})

        def _write(self, status: int, payload: object):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return ReleaseHandler


def _agent_package_handler(
    package: dict,
    release: dict,
    requests: list[tuple[str, str, dict | None]],
):
    package_ref = f"{package['package_id']}@{package['version']}"

    class AgentPackageHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(("GET", self.path, None))
            if self.headers.get("Authorization") != "Bearer secret-token":
                self._write(401, {"error": "unauthorized"})
                return
            if self.path.startswith("/api/agent-packages?"):
                if f"after={package_ref.replace('@', '%40')}" in self.path:
                    self._write(200, {"packages": [], "next_cursor": ""})
                    return
                self._write(
                    200,
                    {
                        "packages": [
                            {
                                "package_id": package["package_id"],
                                "version": package["version"],
                                "content_hash": package["content_hash"],
                                "lifecycle_state": package["lifecycle_state"],
                                "url": (
                                    f"/api/agent-packages/{package['package_id']}"
                                    f"?version={package['version']}"
                                ),
                            }
                        ],
                        "next_cursor": package_ref,
                    },
                )
                return
            if self.path == (
                f"/api/agent-packages/{package['package_id']}?version={package['version']}"
            ):
                self._write(200, package)
                return
            if self.path == f"/api/knowledge/releases/{release['release_id']}":
                self._write(200, release)
                return
            self._write(404, {"error": "not found"})

        def _write(self, status: int, payload: object):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return AgentPackageHandler


def _agent_package_sequence_handler(
    packages: list[dict],
    releases: dict[str, dict],
    requests: list[tuple[str, str, dict | None]],
):
    class AgentPackageSequenceHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import parse_qs, urlparse

            requests.append(("GET", self.path, None))
            if self.headers.get("Authorization") != "Bearer secret-token":
                self._write(401, {"error": "unauthorized"})
                return
            parsed = urlparse(self.path)
            if parsed.path == "/api/agent-packages":
                query = parse_qs(parsed.query)
                after = query.get("after", [""])[0]
                limit = int(query.get("limit", ["50"])[0])
                refs = [f"{package['package_id']}@{package['version']}" for package in packages]
                start = refs.index(after) + 1 if after in refs else 0
                page = packages[start : start + limit]
                self._write(
                    200,
                    {
                        "packages": [
                            {
                                "package_id": package["package_id"],
                                "version": package["version"],
                                "content_hash": package["content_hash"],
                                "lifecycle_state": package["lifecycle_state"],
                                "supersedes": package.get("supersedes", ""),
                            }
                            for package in page
                        ],
                        "next_cursor": (
                            f"{page[-1]['package_id']}@{page[-1]['version']}" if page else ""
                        ),
                    },
                )
                return
            for package in packages:
                if self.path == (
                    f"/api/agent-packages/{package['package_id']}?version={package['version']}"
                ):
                    self._write(200, package)
                    return
            for release in releases.values():
                if self.path == f"/api/knowledge/releases/{release['release_id']}":
                    self._write(200, release)
                    return
            self._write(404, {"error": "not found"})

        def _write(self, status: int, payload: object):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return AgentPackageSequenceHandler
