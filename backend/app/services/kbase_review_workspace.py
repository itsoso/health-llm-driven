"""Coordination and validation for the persistent dedao-kbase review workspace."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterator

from app.services.kbase_claim_verification import (
    build_deterministic_verification_packet,
    claim_content_hash,
)
from app.services.system_knowledge_ingest import (
    ARTIFACT_FILES,
    review_draft_artifacts,
    validate_artifact_review_gate,
)


ADJUDICATION_LEDGER = "adjudications.jsonl"
VERIFICATION_PACKET_LEDGER = "verification_packets.jsonl"
VERIFICATION_PACKET_READ_LIMIT = 50
CLAIM_DECISIONS = frozenset({"approve", "needs_evidence", "reject", "background_only"})


def workspace_backup_path(artifact_dir: str | Path) -> Path:
    target = Path(artifact_dir)
    return target.with_name(f".{target.name}.backup")


@contextmanager
def review_workspace_lock(artifact_dir: str | Path) -> Iterator[None]:
    target = Path(artifact_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    coordination_target = target.parent if target.name == "agent-packages" else target
    lock_path = coordination_target.parent / f".{coordination_target.name}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            _recover_interrupted_replacement(target)
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def read_workspace_metadata(artifact_dir: str | Path) -> dict[str, Any]:
    path = Path(artifact_dir) / "draft_manifest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def workspace_content_fingerprint(artifact_dir: str | Path) -> str:
    root = Path(artifact_dir)
    required = (*ARTIFACT_FILES, "manifest.json", "draft_manifest.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError(f"review workspace is incomplete: missing {', '.join(missing)}")
    digest = hashlib.sha256()
    fingerprint_files = [*required]
    if (root / ADJUDICATION_LEDGER).is_file():
        fingerprint_files.append(ADJUDICATION_LEDGER)
    for name in fingerprint_files:
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update((root / name).read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def workspace_artifacts_valid(artifact_dir: str | Path) -> bool:
    root = Path(artifact_dir)
    required = (*ARTIFACT_FILES, "manifest.json", "draft_manifest.json")
    if not root.is_dir() or any(not (root / name).is_file() for name in required):
        return False
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        draft_manifest = json.loads((root / "draft_manifest.json").read_text(encoding="utf-8"))
        counts = manifest.get("counts") if isinstance(manifest, dict) else None
        if not isinstance(counts, dict) or not isinstance(draft_manifest, dict):
            return False
        actual_counts: dict[str, int] = {}
        for name in ARTIFACT_FILES:
            rows = [line for line in (root / name).read_text(encoding="utf-8").splitlines() if line.strip()]
            actual_counts[Path(name).stem] = len(rows)
            for line in rows:
                if not isinstance(json.loads(line), dict):
                    return False
        if sum(actual_counts.values()) == 0:
            return False
        if any(counts.get(name) != count for name, count in actual_counts.items()):
            return False
        ledger_path = root / ADJUDICATION_LEDGER
        for ledger_path in (root / ADJUDICATION_LEDGER, root / VERIFICATION_PACKET_LEDGER):
            if not ledger_path.exists():
                continue
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                if line.strip() and not isinstance(json.loads(line), dict):
                    return False
    except (OSError, json.JSONDecodeError):
        return False
    return True


def _recover_interrupted_replacement(target: Path) -> None:
    backup = workspace_backup_path(target)
    if not backup.exists():
        return
    if target.exists():
        shutil.rmtree(backup)
    else:
        os.replace(backup, target)


def list_review_claims(
    artifact_dir: str | Path,
    *,
    offset: int = 0,
    limit: int = 50,
    decision: str | None = None,
) -> dict[str, Any]:
    """Return a bounded claim review projection from a persistent workspace."""
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if decision is not None and decision not in CLAIM_DECISIONS:
        raise ValueError("invalid claim decision filter")

    root = Path(artifact_dir)
    with review_workspace_lock(root):
        if not workspace_artifacts_valid(root):
            raise ValueError("dedao-kbase review workspace is incomplete or corrupt")
        latest = _latest_adjudications(root)
        items = []
        for claim in _read_jsonl(root / "claims.jsonl"):
            metadata = claim.get("metadata") if isinstance(claim.get("metadata"), dict) else {}
            claim_decision = (latest.get(str(claim.get("doc_id") or "")) or {}).get("decision")
            if decision is not None and claim_decision != decision:
                continue
            sources = [str(item) for item in claim.get("sources") or [] if str(item).strip()]
            items.append(
                {
                    "doc_id": str(claim.get("doc_id") or ""),
                    "title": str(claim.get("title") or ""),
                    "summary": str(claim.get("summary") or claim.get("body") or ""),
                    "evidence_level": claim.get("evidence_level"),
                    "confidence": claim.get("confidence"),
                    "sources": sources,
                    "source_count": len(sources),
                    "review_status": metadata.get("review_status"),
                    "decision": claim_decision,
                    "release_id": metadata.get("release_id"),
                    "release_claim_id": metadata.get("release_claim_id"),
                    "usage_policy": metadata.get("usage_policy"),
                    "citation_ids": metadata.get("citation_ids") or [],
                }
            )
        items.sort(key=lambda item: item["doc_id"])
        decision_counts: dict[str, int] = {}
        for item in items:
            bucket = str(item["decision"] or "unresolved")
            decision_counts[bucket] = decision_counts.get(bucket, 0) + 1
        unresolved_count = sum(
            1
            for item in items
            if item["review_status"] == "draft" or (
                item["release_id"] and item["decision"] != "approve"
            )
        )
        return {
            "workspace_fingerprint": workspace_content_fingerprint(root),
            "gate": validate_artifact_review_gate(root),
            "total": len(items),
            "unresolved_count": unresolved_count,
            "decision_counts": dict(sorted(decision_counts.items())),
            "offset": offset,
            "limit": limit,
            "items": items[offset : offset + limit],
        }


def adjudicate_review_claim(
    artifact_dir: str | Path,
    *,
    doc_id: str,
    decision: str,
    reviewer: str,
    expected_workspace_fingerprint: str,
    note: str | None = None,
    evidence: dict[str, Any] | None = None,
    evidence_level: str | None = None,
    confidence: float | None = None,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    """Apply one claim decision through a validated sibling candidate."""
    doc_id = doc_id.strip()
    reviewer = reviewer.strip()
    if not doc_id:
        raise ValueError("claim doc_id is required")
    if decision not in CLAIM_DECISIONS:
        raise ValueError("invalid claim decision")
    if not reviewer:
        raise ValueError("reviewer is required")
    if evidence_level is not None and evidence_level not in {"A", "B", "C", "D"}:
        raise ValueError("invalid evidence level")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if decision != "approve" and (evidence is not None or evidence_level is not None or confidence is not None):
        raise ValueError("evidence updates require an approve decision")
    normalized_evidence = _validate_external_evidence(evidence) if evidence is not None else None

    root = Path(artifact_dir)
    with review_workspace_lock(root):
        if not workspace_artifacts_valid(root):
            raise ValueError("dedao-kbase review workspace is incomplete or corrupt")
        current_fingerprint = workspace_content_fingerprint(root)
        if current_fingerprint != expected_workspace_fingerprint:
            raise ValueError("dedao-kbase review workspace changed since preview; reload before approval")

        candidate = Path(tempfile.mkdtemp(prefix=f".{root.name}.candidate-", dir=root.parent))
        try:
            shutil.copytree(root, candidate, dirs_exist_ok=True)
            claims = _read_jsonl(candidate / "claims.jsonl")
            claim = next((row for row in claims if row.get("doc_id") == doc_id), None)
            if claim is None:
                raise ValueError(f"claim not found in review workspace: {doc_id}")
            metadata = claim.setdefault("metadata", {})
            if metadata.get("review_status") not in {"draft", "reviewed"}:
                raise ValueError(f"claim cannot be adjudicated from status: {metadata.get('review_status')}")
            release_id = metadata.get("release_id")
            release_claim_id = metadata.get("release_claim_id")

            timestamp = (decided_at or datetime.now(UTC)).isoformat()
            if decision == "approve":
                metadata.update(
                    {
                        "review_status": "reviewed",
                        "reviewed_by": reviewer,
                        "reviewed_at": timestamp,
                        "adjudication_decision": decision,
                    }
                )
                if evidence_level is not None:
                    claim["evidence_level"] = evidence_level
                if confidence is not None:
                    claim["confidence"] = confidence
                if normalized_evidence is not None:
                    sources = [str(item) for item in claim.get("sources") or []]
                    if normalized_evidence["source"] not in sources:
                        sources.append(normalized_evidence["source"])
                    claim["sources"] = sources
                    external_sources = list(metadata.get("external_sources") or [])
                    external_sources.append(normalized_evidence)
                    metadata["external_sources"] = external_sources
            elif decision == "needs_evidence":
                metadata["review_status"] = "draft"
                metadata["adjudication_decision"] = decision
            else:
                claims = [row for row in claims if row.get("doc_id") != doc_id]
                relations = [
                    row
                    for row in _read_jsonl(candidate / "relations.jsonl")
                    if row.get("src_doc_id") != doc_id and row.get("dst_doc_id") != doc_id
                ]
                _write_jsonl(candidate / "relations.jsonl", relations)

            _write_jsonl(candidate / "claims.jsonl", claims)
            event = {
                "doc_id": doc_id,
                "decision": decision,
                "reviewer": reviewer,
                "note": (note or "").strip() or None,
                "evidence": normalized_evidence,
                "evidence_level": evidence_level,
                "confidence": confidence,
                "decided_at": timestamp,
                "previous_workspace_fingerprint": current_fingerprint,
            }
            _append_jsonl(candidate / ADJUDICATION_LEDGER, event)
            _refresh_manifest_counts(candidate)
            if not workspace_artifacts_valid(candidate):
                raise ValueError("review workspace candidate validation failed")
            _replace_workspace(candidate, root)
        finally:
            if candidate.exists():
                shutil.rmtree(candidate)

        return {
            "artifact_dir": str(root),
            "doc_id": doc_id,
            "decision": decision,
            "release_id": release_id,
            "release_claim_id": release_claim_id,
            "workspace_fingerprint": workspace_content_fingerprint(root),
            "gate": validate_artifact_review_gate(root),
        }


def generate_review_verification_packet(
    artifact_dir: str | Path,
    *,
    doc_id: str,
    expected_workspace_fingerprint: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Generate and atomically persist an advisory packet for one claim."""
    doc_id = doc_id.strip()
    if not doc_id:
        raise ValueError("claim doc_id is required")

    root = Path(artifact_dir)
    with review_workspace_lock(root):
        if not workspace_artifacts_valid(root):
            raise ValueError("dedao-kbase review workspace is incomplete or corrupt")
        current_fingerprint = workspace_content_fingerprint(root)
        if current_fingerprint != expected_workspace_fingerprint:
            raise ValueError("dedao-kbase review workspace changed since preview; reload before approval")
        claims = _read_jsonl(root / "claims.jsonl")
        claim = next((row for row in claims if row.get("doc_id") == doc_id), None)
        if claim is None:
            raise ValueError(f"claim not found in review workspace: {doc_id}")
        packet = build_deterministic_verification_packet(
            claim,
            workspace_fingerprint=current_fingerprint,
            peer_claims=claims,
            generated_at=generated_at,
        )

        candidate = Path(tempfile.mkdtemp(prefix=f".{root.name}.candidate-", dir=root.parent))
        try:
            shutil.copytree(root, candidate, dirs_exist_ok=True)
            _append_jsonl(candidate / VERIFICATION_PACKET_LEDGER, packet)
            if not workspace_artifacts_valid(candidate):
                raise ValueError("review workspace candidate validation failed")
            _replace_workspace(candidate, root)
        finally:
            if candidate.exists():
                shutil.rmtree(candidate)

        return {
            "artifact_dir": str(root),
            "workspace_fingerprint": workspace_content_fingerprint(root),
            "packet": packet,
        }


def list_review_verification_packets(
    artifact_dir: str | Path,
    *,
    doc_id: str | None = None,
) -> dict[str, Any]:
    """Return verification packets with staleness derived from live claim content."""
    root = Path(artifact_dir)
    with review_workspace_lock(root):
        if not workspace_artifacts_valid(root):
            raise ValueError("dedao-kbase review workspace is incomplete or corrupt")
        current_fingerprint = workspace_content_fingerprint(root)
        claims = {
            str(claim.get("doc_id") or ""): claim
            for claim in _read_jsonl(root / "claims.jsonl")
        }
        candidates = []
        for stored in _read_jsonl(root / VERIFICATION_PACKET_LEDGER):
            packet_doc_id = str(stored.get("doc_id") or "")
            if doc_id is not None and packet_doc_id != doc_id:
                continue
            claim = claims.get(packet_doc_id)
            stale = (
                claim is None
                or stored.get("workspace_fingerprint") != current_fingerprint
                or stored.get("claim_content_hash") != claim_content_hash(claim)
            )
            packet = dict(stored)
            packet["stale"] = stale
            if stale:
                packet["status"] = "stale"
            candidates.append(packet)
        candidates.sort(key=lambda item: (str(item.get("generated_at") or ""), str(item.get("packet_id") or "")), reverse=True)
        items = []
        seen_packet_ids: set[str] = set()
        for packet in candidates:
            packet_id = str(packet.get("packet_id") or "")
            if not packet_id or packet_id in seen_packet_ids:
                continue
            seen_packet_ids.add(packet_id)
            items.append(packet)
            if len(items) >= VERIFICATION_PACKET_READ_LIMIT:
                break
        return {
            "workspace_fingerprint": current_fingerprint,
            "total": len(items),
            "items": items,
        }


def finalize_review_workspace(
    artifact_dir: str | Path,
    *,
    reviewer: str,
    expected_workspace_fingerprint: str,
    reviewed_at: datetime | None = None,
) -> dict[str, Any]:
    """Finalize generated containers only after every draft claim is resolved."""
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")

    root = Path(artifact_dir)
    with review_workspace_lock(root):
        if not workspace_artifacts_valid(root):
            raise ValueError("dedao-kbase review workspace is incomplete or corrupt")
        current_fingerprint = workspace_content_fingerprint(root)
        if current_fingerprint != expected_workspace_fingerprint:
            raise ValueError("dedao-kbase review workspace changed since preview; reload before approval")

        latest = _latest_adjudications(root)
        unresolved = []
        for claim in _read_jsonl(root / "claims.jsonl"):
            metadata = claim.get("metadata") if isinstance(claim.get("metadata"), dict) else {}
            doc_id = str(claim.get("doc_id") or "")
            decision = (latest.get(doc_id) or {}).get("decision")
            if metadata.get("review_status") == "draft" or (
                metadata.get("release_id") and decision != "approve"
            ):
                unresolved.append(doc_id)
        if unresolved:
            raise ValueError(f"unresolved claim decisions remain: {len(unresolved)}")

        candidate = Path(tempfile.mkdtemp(prefix=f".{root.name}.candidate-", dir=root.parent))
        try:
            shutil.copytree(root, candidate, dirs_exist_ok=True)
            _remove_dangling_relations(candidate)
            review = review_draft_artifacts(
                candidate,
                reviewer=reviewer,
                reviewed_at=reviewed_at,
            )
            _refresh_manifest_counts(candidate)
            gate = validate_artifact_review_gate(candidate)
            if not gate.get("serving_allowed"):
                reasons = ", ".join(str(reason) for reason in gate.get("blocking_reasons") or [])
                raise ValueError(f"review workspace finalization remains blocked: {reasons}")
            if not workspace_artifacts_valid(candidate):
                raise ValueError("review workspace candidate validation failed")
            _replace_workspace(candidate, root)
        finally:
            if candidate.exists():
                shutil.rmtree(candidate)

        return {
            "artifact_dir": str(root),
            "previous_workspace_fingerprint": current_fingerprint,
            "workspace_fingerprint": workspace_content_fingerprint(root),
            "review": review,
            "gate": validate_artifact_review_gate(root),
            "draft_manifest": json.loads((root / "draft_manifest.json").read_text(encoding="utf-8")),
        }


def _validate_external_evidence(evidence: dict[str, Any]) -> dict[str, str]:
    if not isinstance(evidence, dict):
        raise ValueError("external evidence must be an object")
    source = str(evidence.get("source") or "").strip()
    if not source:
        raise ValueError("external evidence source is required")
    normalized = {"source": source}
    for field in ("kind", "title", "url"):
        value = str(evidence.get(field) or "").strip()
        if value:
            normalized[field] = value
    return normalized


def _latest_adjudications(root: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in _read_jsonl(root / ADJUDICATION_LEDGER):
        doc_id = str(event.get("doc_id") or "")
        if doc_id:
            latest[doc_id] = event
    return latest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid JSONL object: {path.name}")
        rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(content, encoding="utf-8")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _refresh_manifest_counts(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"] = {
        Path(name).stem: len(_read_jsonl(root / name))
        for name in ARTIFACT_FILES
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _remove_dangling_relations(root: Path) -> None:
    document_ids = {
        str(row.get("doc_id") or "")
        for name in ARTIFACT_FILES[:-1]
        for row in _read_jsonl(root / name)
    }
    relations = [
        row
        for row in _read_jsonl(root / "relations.jsonl")
        if row.get("src_doc_id") in document_ids and row.get("dst_doc_id") in document_ids
    ]
    _write_jsonl(root / "relations.jsonl", relations)


def _replace_workspace(candidate: Path, target: Path) -> None:
    backup = workspace_backup_path(target)
    if backup.exists():
        raise RuntimeError(f"unrecovered review workspace backup: {backup}")
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(candidate, target)
    except Exception:
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)
