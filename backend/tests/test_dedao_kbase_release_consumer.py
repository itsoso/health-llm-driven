from __future__ import annotations

from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

import pytest

from app.models.system_knowledge import KBAudit


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
    assert claim["metadata"]["usage_policy"] == "evidence_only"
    assert claim["metadata"]["review_status"] == "draft"
    assert claim["metadata"]["citation_ids"] == ["citation-1"]
    assert result.manifest["ingest"]["serving_allowed"] is False


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
            now=datetime(2026, 7, 12, 13, tzinfo=UTC),
        )
        resumed = sync_dedao_kbase_releases_draft_once(
            db,
            base_url=f"http://127.0.0.1:{server.server_port}",
            auth_token="secret-token",
            artifact_dir=tmp_path / "artifacts",
            source_root=tmp_path / "source",
            actor="test:release-sync",
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
    assert resumed == {"status": "up_to_date", "cursor": "release-abc", "release_count": 0}
    assert any("after=release-abc" in path for method, path, _ in requests if method == "GET")
    assert not any(method == "POST" for method, _, _ in requests)


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
