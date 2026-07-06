from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
import sys
from pathlib import Path
from threading import Thread

import pytest

from app.services.dedao_kbase_evidence_pull import dry_run_dedao_kbase_evidence_pull


def test_dry_run_dedao_kbase_evidence_pull_accepts_only_safe_review_candidates():
    manifest = _manifest()
    records = [
        _record("dedao:book:claim-safe", risk_tier="auto_usable", quality_status="usable"),
        _record("dedao:book:claim-review", risk_tier="assistive_only", quality_status="needs_review"),
        _record("dedao:book:claim-blocked", risk_tier="blocked", quality_status="rejected"),
    ]

    server, thread = _start_server(manifest, records)
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        report = dry_run_dedao_kbase_evidence_pull(
            manifest_url=f"{base_url}/api/projects/health/evidence-pack/manifest",
            auth_token="secret-token",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert report["status"] == "dry_run"
    assert report["consumer_contract"] == "verified_evidence_pull_manifest_v1"
    assert report["pack_id"] == "vep_test"
    assert report["source_fingerprint"] == "fp-test"
    assert report["total_records"] == 3
    assert report["accepted_candidates"] == 1
    assert report["review_required_records"] == 1
    assert report["blocked_records"] == 1
    assert report["would_write"] is False
    assert [item["evidence_id"] for item in report["candidates"]] == ["dedao:book:claim-safe"]
    assert report["candidates"][0]["review_status"] == "draft_candidate"
    assert "reject_blocked" in report["gate_checks"]
    assert "blocked_record" in report["rejected_reasons"]


def test_dry_run_dedao_kbase_evidence_pull_rejects_source_fingerprint_mismatch():
    manifest = _manifest()
    records = [_record("dedao:book:claim-safe", source_fingerprint="other-fp")]

    server, thread = _start_server(manifest, records)
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(ValueError, match="source_fingerprint_mismatch"):
            dry_run_dedao_kbase_evidence_pull(
                manifest_url=f"{base_url}/api/projects/health/evidence-pack/manifest",
                auth_token="secret-token",
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dedao_kbase_evidence_pull_cli_prints_json_summary():
    manifest = _manifest()
    records = [_record("dedao:book:claim-safe", risk_tier="auto_usable", quality_status="usable")]
    server, thread = _start_server(manifest, records)
    backend_root = Path(__file__).resolve().parents[1]
    try:
        manifest_url = f"http://127.0.0.1:{server.server_port}/api/projects/health/evidence-pack/manifest"
        run = subprocess.run(
            [
                sys.executable,
                str(backend_root / "scripts" / "dry_run_dedao_kbase_evidence_pull.py"),
                "--manifest-url",
                manifest_url,
                "--auth-token",
                "secret-token",
                "--json-summary",
            ],
            cwd=backend_root,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert run.returncode == 0, run.stderr
    summary = json.loads(run.stdout)
    assert summary["status"] == "dry_run"
    assert summary["accepted_candidates"] == 1
    assert summary["would_write"] is False


def test_dedao_kbase_evidence_pull_task_writes_redacted_dry_run_audit(db):
    from app.models.system_knowledge import KBAudit
    from app.tasks.system_knowledge_lifecycle import sync_dedao_kbase_evidence_pull_dry_run_once

    manifest = _manifest()
    records = [
        _record("dedao:book:claim-safe", risk_tier="auto_usable", quality_status="usable"),
        _record("dedao:book:claim-review", risk_tier="assistive_only", quality_status="needs_review"),
        _record("dedao:book:claim-blocked", risk_tier="blocked", quality_status="rejected"),
    ]
    server, thread = _start_server(manifest, records)
    try:
        manifest_url = f"http://127.0.0.1:{server.server_port}/api/projects/health/evidence-pack/manifest"
        report = sync_dedao_kbase_evidence_pull_dry_run_once(
            db,
            manifest_url=manifest_url,
            auth_token="secret-token",
            actor="test:dedao-evidence-pull",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert report["status"] == "dry_run"
    assert report["would_write"] is False
    assert report["accepted_candidates"] == 1
    assert report["review_required_records"] == 1
    assert report["blocked_records"] == 1

    audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_evidence_pull_dry_run").one()
    assert audit.actor == "test:dedao-evidence-pull"
    assert audit.diff["status"] == "dry_run"
    assert audit.diff["manifest_url"] == manifest_url
    assert audit.diff["pack_id"] == "vep_test"
    assert audit.diff["source_fingerprint"] == "fp-test"
    assert audit.diff["accepted_candidates"] == 1
    assert audit.diff["candidate_evidence_ids"] == ["dedao:book:claim-safe"]
    assert audit.diff["would_write"] is False
    assert "candidates" not in audit.diff
    assert "transformed summary only" not in json.dumps(audit.diff, ensure_ascii=False)


def _manifest() -> dict:
    return {
        "consumer_contract": "verified_evidence_pull_manifest_v1",
        "schema_version": "1",
        "project_id": "health",
        "target_system": "health-llm-driven",
        "export_type": "health_authority_candidates",
        "current_pack": {
            "consumer_contract": "verified_evidence_pack_v1",
            "pack_id": "vep_test",
            "source_fingerprint": "fp-test",
            "record_count": 3,
            "quality_summary": {"total": 3, "accepted": 1, "assistive": 1, "blocked": 1},
        },
        "endpoints": {
            "evidence_pack_jsonl_url": "/api/projects/health/evidence-pack/export?format=jsonl&limit=25",
            "diff_url_template": "/api/projects/health/evidence-pack/diff?previous_pack_id={pack_id}&limit=25",
            "domain_pack_jsonl_url": "/api/projects/health/authority-pack/export?format=jsonl&limit=25",
        },
        "consumer_gate": {
            "mode": "pull_and_verify",
            "must_check_source_fingerprint": True,
            "must_reject_blocked": True,
            "allowed_uses": ["education_context"],
            "blocked_uses": ["diagnosis", "treatment", "medication_change"],
            "human_loop": "async_audit_only",
        },
        "next_actions": ["pull:evidence_pack_jsonl", "run:health_import_dry_run"],
    }


def _record(
    evidence_id: str,
    *,
    risk_tier: str = "auto_usable",
    quality_status: str = "usable",
    source_fingerprint: str = "fp-test",
) -> dict:
    return {
        "consumer_contract": "verified_evidence_pack_v1",
        "schema_version": "1",
        "pack_id": "vep_test",
        "project_id": "health",
        "target_system": "health-llm-driven",
        "source_fingerprint": source_fingerprint,
        "evidence_id": evidence_id,
        "title": f"title {evidence_id}",
        "summary": "transformed summary only",
        "normalized_claim": "transformed summary only",
        "quality_status": quality_status,
        "risk_tier": risk_tier,
        "decision": "allow" if risk_tier == "auto_usable" else "queue",
        "allowed_uses": ["education_context"],
        "blocked_uses": ["diagnosis", "treatment"],
        "source_refs": {
            "source_type": "dedao_book_claim",
            "source_id": "book",
            "source_title": "source title",
            "claim_id": evidence_id,
            "citations": ["citation-1"],
            "source_hash": "hash-1",
        },
        "audit": {"review_status": "not_required", "audit_status": "not_required"},
    }


def _start_server(manifest: dict, records: list[dict]) -> tuple[ThreadingHTTPServer, Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(manifest, records))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _handler(manifest: dict, records: list[dict]):
    manifest_body = json.dumps(manifest).encode("utf-8")
    export_body = "\n".join(json.dumps(record, ensure_ascii=False) for record in records).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Authorization") != "Bearer secret-token":
                self.send_response(401)
                self.end_headers()
                return
            if self.path == "/api/projects/health/evidence-pack/manifest":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(manifest_body)
                return
            if self.path == "/api/projects/health/evidence-pack/export?format=jsonl&limit=25":
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.end_headers()
                self.wfile.write(export_body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):
            return

    return Handler
