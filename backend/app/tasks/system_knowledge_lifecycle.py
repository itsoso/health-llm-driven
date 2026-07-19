"""System KB lifecycle tasks.

Runs global LLM Wiki V2 maintenance separately from user memory lifecycle:
lint current serving KB, decay stale claim confidence, and draft crystallized
claim candidates from repeated specialist audit observations. Crystallized
claims are never imported automatically; they remain review candidates.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models.system_knowledge import KBAudit, KBDocument
from app.services.dedao_kbase_export_importer import (
    compile_dedao_kbase_export_payload_artifacts,
    fetch_dedao_kbase_export_payload,
)
from app.integrations.dedao_kbase_release_consumer import (
    DedaoKBaseReleaseClient,
    assess_agent_package_for_health,
    combine_release_results,
    compile_agent_package_artifacts,
    compile_knowledge_release_artifacts,
)
from app.services.system_knowledge_crystallize import draft_crystallized_claim_candidates
from app.services.system_knowledge_eval import run_system_kb_eval_cases
from app.services.system_knowledge_ingest import ARTIFACT_FILES, validate_artifact_review_gate, write_draft_artifacts
from app.services.kbase_review_workspace import (
    read_workspace_metadata,
    review_workspace_lock,
    workspace_artifacts_valid,
    workspace_backup_path,
)
from app.services.system_knowledge_service import (
    apply_confidence_decay,
    lint_knowledge_base,
    run_system_kb_reindex_report,
)

logger = logging.getLogger(__name__)

DEDAO_KBASE_FEEDBACK_FLUSH_OP = "dedao_kbase_feedback_flush"
DEDAO_KBASE_FEEDBACK_SOURCE_OPS = (
    "kb_citation_usage",
    "dedao_kbase_claim_adjudicated",
    "dedao_kbase_verification_applied",
)


def _default_system_kb_artifact_dir() -> Path:
    if settings.system_kb_artifact_dir:
        return Path(settings.system_kb_artifact_dir).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "system_kb_v2_seed"


def _dedao_kbase_review_artifact_dir() -> Path:
    configured = (settings.dedao_kbase_review_artifact_dir or "").strip()
    if not configured:
        raise ValueError("DEDAO_KBASE_REVIEW_ARTIFACT_DIR is required for Release sync")
    return Path(configured).expanduser()


def _artifact_fingerprint(artifact_dir: str | Path) -> str:
    root = Path(artifact_dir)
    digest = hashlib.sha256()
    for name in (*ARTIFACT_FILES, "manifest.json"):
        path = root / name
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        if path.exists():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<missing>")
        digest.update(b"\x00")
    return digest.hexdigest()


_workspace_lock = review_workspace_lock


def _replace_workspace(candidate: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
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


def _preserve_agent_package_workspace(target: Path, candidate: Path) -> None:
    """Carry the fixed child review workspace across a parent rebuild."""
    source = target / "agent-packages"
    if not source.exists() and not source.is_symlink():
        return
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Agent Package review workspace must be a real directory under the release workspace")

    destination = candidate / "agent-packages"
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _normalize_canonical_review_status(artifact_dir: str | Path) -> None:
    """Treat missing status in the trusted repository seed as reviewed.

    Explicit draft or needs_review values remain untouched and continue to
    block serving.
    """
    root = Path(artifact_dir)
    for name in ARTIFACT_FILES:
        path = root / name
        if not path.exists():
            continue
        normalized: list[str] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            metadata = dict(row.get("metadata") or {})
            metadata.setdefault("review_status", "reviewed")
            row["metadata"] = metadata
            normalized.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
        path.write_text(("\n".join(normalized) + "\n") if normalized else "", encoding="utf-8")


def _agent_package_lineages_by_release(artifact_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    lineages: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {}
    root = Path(artifact_dir)
    for name in ARTIFACT_FILES:
        path = root / name
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            metadata = row.get("metadata") if isinstance(row, dict) else None
            if not isinstance(metadata, dict):
                continue
            release_id = str(metadata.get("release_id") or "").strip()
            if not release_id:
                continue
            release_lineages = lineages.setdefault(release_id, {})
            for item in metadata.get("agent_package_lineage") or []:
                if not isinstance(item, dict):
                    continue
                key = (
                    str(item.get("package_id") or ""),
                    str(item.get("version") or ""),
                    str(item.get("content_hash") or ""),
                )
                if all(key):
                    release_lineages[key] = item
    return {
        release_id: [items[key] for key in sorted(items)]
        for release_id, items in lineages.items()
    }


def _preserve_agent_package_lineage(
    result: Any,
    existing_by_release: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    by_release = {
        release_id: {
            (
                str(item.get("package_id") or ""),
                str(item.get("version") or ""),
                str(item.get("content_hash") or ""),
            ): item
            for item in items
            if isinstance(item, dict)
        }
        for release_id, items in existing_by_release.items()
    }
    for item in result.manifest.get("agent_packages") or []:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("package_id") or ""),
            str(item.get("version") or ""),
            str(item.get("content_hash") or ""),
        )
        if not all(key):
            continue
        for release_id in item.get("release_ids") or []:
            by_release.setdefault(str(release_id), {})[key] = item
    for row in [
        *result.pages,
        *result.entities,
        *result.claims,
        *result.relations,
    ]:
        metadata = dict(row.get("metadata") or {})
        release_id = str(metadata.get("release_id") or "").strip()
        if release_id in by_release:
            metadata["agent_package_lineage"] = [
                by_release[release_id][key] for key in sorted(by_release[release_id])
            ]
            row["metadata"] = metadata
    return {
        release_id: [items[key] for key in sorted(items)]
        for release_id, items in by_release.items()
    }


def _write_agent_package_lineage_to_artifacts(
    artifact_dir: str | Path,
    lineages_by_release: dict[str, list[dict[str, Any]]],
) -> None:
    root = Path(artifact_dir)
    for name in ARTIFACT_FILES:
        path = root / name
        if not path.exists():
            continue
        rows: list[str] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            metadata = dict(row.get("metadata") or {})
            release_id = str(metadata.get("release_id") or "").strip()
            if release_id in lineages_by_release:
                metadata["agent_package_lineage"] = lineages_by_release[release_id]
                row["metadata"] = metadata
            rows.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
        path.write_text(("\n".join(rows) + "\n") if rows else "", encoding="utf-8")


def _list_release_records(
    client: DedaoKBaseReleaseClient,
    *,
    after: str,
    limit: int,
    replay_all: bool,
) -> list[dict[str, Any]]:
    if not replay_all:
        return client.list_releases(after=after, limit=limit)
    records: list[dict[str, Any]] = []
    cursor = ""
    while True:
        page = client.list_releases(after=cursor, limit=limit)
        records.extend(page)
        if len(page) < limit:
            return records
        next_cursor = str(page[-1].get("release_id") or "")
        if not next_cursor or next_cursor == cursor:
            raise ValueError("dedao-kbase release replay cursor did not advance")
        cursor = next_cursor


def _list_agent_package_records(
    client: DedaoKBaseReleaseClient,
    *,
    after: str,
    limit: int,
    replay_all: bool,
) -> list[dict[str, Any]]:
    if not replay_all:
        return client.list_agent_packages(after=after, limit=limit)
    records: list[dict[str, Any]] = []
    cursor = ""
    while True:
        page = client.list_agent_packages(after=cursor, limit=limit)
        records.extend(page)
        if len(page) < limit:
            return records
        last = page[-1]
        next_cursor = f"{last.get('package_id', '')}@{last.get('version', '')}"
        if next_cursor == "@" or next_cursor == cursor:
            raise ValueError("dedao-kbase Agent Package replay cursor did not advance")
        cursor = next_cursor


def _feedback_event_id(audit_id: int, release_id: str) -> str:
    release_digest = hashlib.sha256(release_id.encode("utf-8")).hexdigest()[:12]
    return f"health-kb-audit-{audit_id}-{release_digest}"


def _feedback_events_for_audit(db: Session, audit: KBAudit) -> list[dict[str, Any]]:
    diff = audit.diff if isinstance(audit.diff, dict) else {}
    if audit.op == "kb_citation_usage":
        used_ids = [str(item) for item in diff.get("used_ids") or [] if str(item).strip()]
        if not used_ids:
            return []
        documents = db.query(KBDocument).filter(KBDocument.doc_id.in_(used_ids)).all()
        metadata_by_doc_id = {
            document.doc_id: document.metadata_json
            for document in documents
            if isinstance(document.metadata_json, dict)
        }
        claims_by_release: dict[str, list[str]] = {}
        for doc_id in used_ids:
            metadata = metadata_by_doc_id.get(doc_id) or {}
            if metadata.get("origin") not in {
                "dedao-kbase-release",
                "dedao-kbase-agent-package",
            }:
                continue
            release_id = str(metadata.get("release_id") or "").strip()
            release_claim_id = str(metadata.get("release_claim_id") or "").strip()
            if not release_id or not release_claim_id:
                continue
            claim_ids = claims_by_release.setdefault(release_id, [])
            if release_claim_id not in claim_ids:
                claim_ids.append(release_claim_id)
        return [
            {
                "release_id": release_id,
                "outcome": "used",
                "claim_ids": claim_ids,
                "reason_code": "used_for_answer",
            }
            for release_id, claim_ids in claims_by_release.items()
        ]

    decision = str(diff.get("decision") or "")
    if decision not in {"reject", "background_only"}:
        return []
    release_id = str(diff.get("release_id") or "").strip()
    if not release_id:
        return []
    release_claim_id = str(diff.get("release_claim_id") or "").strip()
    return [
        {
            "release_id": release_id,
            "outcome": "rejected",
            "claim_ids": [release_claim_id] if release_claim_id else [],
            "reason_code": "out_of_scope" if decision == "background_only" else "",
        }
    ]


def flush_dedao_kbase_feedback_once(
    db: Session,
    *,
    base_url: str | None,
    auth_token: str | None,
    actor: str = "system",
    limit: int = 100,
    client: DedaoKBaseReleaseClient | None = None,
) -> dict[str, Any]:
    """Flush bounded, privacy-safe KBase feedback events from the durable audit log."""
    if not 1 <= limit <= 500:
        raise ValueError("feedback flush limit must be between 1 and 500")
    base_url = (base_url or "").strip()
    if not base_url:
        return {"status": "skipped", "reason": "missing_release_base_url"}

    latest = (
        db.query(KBAudit)
        .filter(KBAudit.op == DEDAO_KBASE_FEEDBACK_FLUSH_OP)
        .order_by(KBAudit.id.desc())
        .first()
    )
    previous_cursor = int((latest.diff or {}).get("cursor") or 0) if latest else 0
    audits = (
        db.query(KBAudit)
        .filter(
            KBAudit.id > previous_cursor,
            KBAudit.op.in_(DEDAO_KBASE_FEEDBACK_SOURCE_OPS),
        )
        .order_by(KBAudit.id.asc())
        .limit(limit)
        .all()
    )
    if not audits:
        return {
            "status": "up_to_date",
            "cursor": previous_cursor,
            "scanned": 0,
            "posted": 0,
            "outcomes": {},
        }

    producer = client or DedaoKBaseReleaseClient(base_url, auth_token=auth_token)
    outcomes: dict[str, int] = {}
    posted = 0
    for audit in audits:
        for event in _feedback_events_for_audit(db, audit):
            producer.post_feedback(
                event["release_id"],
                event_id=_feedback_event_id(audit.id, event["release_id"]),
                consumer="health-llm-driven",
                outcome=event["outcome"],
                claim_ids=event["claim_ids"],
                reason_code=event["reason_code"],
            )
            posted += 1
            outcomes[event["outcome"]] = outcomes.get(event["outcome"], 0) + 1

    cursor = audits[-1].id
    report = {
        "status": "flushed",
        "cursor": cursor,
        "scanned": len(audits),
        "posted": posted,
        "outcomes": dict(sorted(outcomes.items())),
    }
    db.add(KBAudit(doc_id=None, op=DEDAO_KBASE_FEEDBACK_FLUSH_OP, actor=actor, diff=report))
    db.commit()
    return report


def sync_dedao_kbase_export_draft_once(
    db: Session,
    *,
    export_url: str | None,
    auth_token: str | None,
    artifact_dir: str | Path,
    source_root: str | Path,
    actor: str = "system",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch the online dedao-kbase export and write draft artifacts only."""
    export_url = (export_url or "").strip()
    if not export_url:
        return {
            "status": "skipped",
            "reason": "missing_export_url",
            "artifact_dir": str(artifact_dir),
        }

    current_time = now or datetime.now(UTC)
    payload = fetch_dedao_kbase_export_payload(export_url, auth_token=auth_token)
    result = compile_dedao_kbase_export_payload_artifacts(
        source_root=source_root,
        base_artifact_dir=artifact_dir,
        payload=payload,
        export_ref=export_url,
        now=current_time,
    )
    draft_manifest = write_draft_artifacts(
        result,
        artifact_dir,
        extractor=f"dedao-kbase-export:{export_url}",
        created_at=current_time,
        note="online dedao-kbase export synced as draft; requires review before serving.",
    )
    gate = validate_artifact_review_gate(artifact_dir)
    source = result.source_stats[0] if result.source_stats else {}
    report = {
        "status": "draft_written",
        "export_url": export_url,
        "artifact_dir": str(artifact_dir),
        "source": source.get("source") or payload.get("source") or "dedao-kbase",
        "source_repo": source.get("source_repo"),
        "source_commit": source.get("source_commit"),
        "source_version": source.get("version") or payload.get("version"),
        "diff": result.diff,
        "draft_manifest": draft_manifest,
        "gate": gate,
    }
    db.add(
        KBAudit(
            doc_id=None,
            op="dedao_kbase_export_sync_draft",
            actor=actor,
            diff={
                "status": report["status"],
                "export_url": export_url,
                "artifact_dir": report["artifact_dir"],
                "source": report["source"],
                "source_repo": report["source_repo"],
                "source_commit": report["source_commit"],
                "source_version": report["source_version"],
                "diff": report["diff"],
                "gate": {
                    "serving_allowed": gate["serving_allowed"],
                    "blocking_reasons": gate["blocking_reasons"],
                },
            },
        )
    )
    db.commit()
    return report


def sync_dedao_kbase_releases_draft_once(
    db: Session,
    *,
    base_url: str | None,
    auth_token: str | None,
    artifact_dir: str | Path,
    base_artifact_dir: str | Path | None = None,
    source_root: str | Path,
    actor: str = "system",
    now: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Serialize cursor reads and workspace replacement for one review path."""
    with review_workspace_lock(artifact_dir):
        return _sync_dedao_kbase_releases_draft_locked(
            db,
            base_url=base_url,
            auth_token=auth_token,
            artifact_dir=artifact_dir,
            base_artifact_dir=base_artifact_dir,
            source_root=source_root,
            actor=actor,
            now=now,
            limit=limit,
        )


def _sync_dedao_kbase_releases_draft_locked(
    db: Session,
    *,
    base_url: str | None,
    auth_token: str | None,
    artifact_dir: str | Path,
    base_artifact_dir: str | Path | None = None,
    source_root: str | Path,
    actor: str = "system",
    now: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Incrementally write immutable releases to draft artifacts without serving mutation."""
    base_url = (base_url or "").strip()
    if not base_url:
        return {"status": "skipped", "reason": "missing_release_base_url", "artifact_dir": str(artifact_dir)}
    latest = (
        db.query(KBAudit)
        .filter(KBAudit.op == "dedao_kbase_release_sync_draft")
        .order_by(KBAudit.ts.desc(), KBAudit.id.desc())
        .first()
    )
    previous_cursor = str((latest.diff or {}).get("cursor") or "") if latest else ""
    target = Path(artifact_dir)
    has_separate_base = base_artifact_dir is not None
    canonical = Path(base_artifact_dir) if base_artifact_dir is not None else target
    target_resolved = target.expanduser().resolve()
    canonical_resolved = canonical.expanduser().resolve()
    paths_overlap = (
        target_resolved == canonical_resolved
        or target_resolved in canonical_resolved.parents
        or canonical_resolved in target_resolved.parents
    )
    if has_separate_base and paths_overlap:
        raise ValueError("dedao-kbase review workspace must not overlap canonical System KB artifact dir")
    base_fingerprint = _artifact_fingerprint(canonical)
    workspace_metadata = read_workspace_metadata(target)
    recorded_fingerprint = str(workspace_metadata.get("base_fingerprint") or "")
    recorded_cursor = str(workspace_metadata.get("cursor") or "")
    recorded_base_url = str(workspace_metadata.get("producer_base_url") or "")
    workspace_valid = (
        workspace_artifacts_valid(target)
        and bool(recorded_fingerprint)
        and recorded_cursor == previous_cursor
        and recorded_base_url == base_url
    )
    if has_separate_base:
        workspace_valid = workspace_valid and recorded_fingerprint == base_fingerprint
    mode = "incremental" if workspace_valid else "rebuild"
    client = DedaoKBaseReleaseClient(base_url, auth_token=auth_token)
    cursor_for_fetch = previous_cursor if mode == "incremental" else ""
    records = _list_release_records(
        client,
        after=cursor_for_fetch,
        limit=limit,
        replay_all=mode == "rebuild",
    )
    if not records:
        return {
            "status": "up_to_date" if mode == "incremental" else "no_releases",
            "mode": mode,
            "cursor": previous_cursor,
            "release_count": 0,
            "base_fingerprint": base_fingerprint,
        }

    current_time = now or datetime.now(UTC)
    releases = [client.get_release(str(record.get("release_id") or "")) for record in records]
    target.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix=f".{target.name}.candidate-", dir=target.parent))
    source = canonical if mode == "rebuild" else target
    try:
        if source.exists():
            shutil.copytree(source, candidate, dirs_exist_ok=True)
        if mode == "rebuild":
            _normalize_canonical_review_status(candidate)
        results = [
            compile_knowledge_release_artifacts(
                release=release,
                base_artifact_dir=candidate,
                source_root=source_root,
                now=current_time,
            )
            for release in releases
        ]
        combined = combine_release_results(results)
        cursor = str(records[-1]["release_id"])
        draft_manifest = write_draft_artifacts(
            combined,
            candidate,
            extractor=f"dedao-kbase-release:{base_url}",
            created_at=current_time,
            note="immutable dedao-kbase releases synced as draft; requires review before serving.",
        )
        draft_manifest.update(
            {
                "base_fingerprint": base_fingerprint,
                "cursor": cursor,
                "producer_base_url": base_url,
                "sync_mode": mode,
            }
        )
        (candidate / "draft_manifest.json").write_text(
            json.dumps(draft_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        gate = validate_artifact_review_gate(candidate)
        _preserve_agent_package_workspace(target, candidate)
        _replace_workspace(candidate, target)
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
    report = {
        "status": "draft_written",
        "mode": mode,
        "base_url": base_url,
        "artifact_dir": str(target),
        "base_artifact_dir": str(canonical),
        "base_fingerprint": base_fingerprint,
        "previous_cursor": previous_cursor,
        "cursor": cursor,
        "release_count": len(releases),
        "release_ids": [release["release_id"] for release in releases],
        "diff": combined.diff,
        "draft_manifest": draft_manifest,
        "gate": gate,
    }
    db.add(KBAudit(doc_id=None, op="dedao_kbase_release_sync_draft", actor=actor, diff=report))
    db.commit()
    return report


def sync_dedao_kbase_agent_packages_draft_once(
    db: Session,
    *,
    base_url: str | None,
    auth_token: str | None,
    artifact_dir: str | Path,
    base_artifact_dir: str | Path,
    source_root: str | Path,
    actor: str = "system",
    now: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Import eligible evidence-only Agent Packages into a draft workspace.

    This path writes only review artifacts plus an audit receipt. It never
    mutates the serving index or any per-user health model.
    """
    with review_workspace_lock(artifact_dir):
        base_url = (base_url or "").strip()
        if not base_url:
            return {
                "status": "skipped",
                "reason": "missing_release_base_url",
                "artifact_dir": str(artifact_dir),
            }
        if not 1 <= limit <= 200:
            raise ValueError("agent package sync limit must be between 1 and 200")

        target = Path(artifact_dir)
        canonical = Path(base_artifact_dir)
        target_resolved = target.expanduser().resolve()
        canonical_resolved = canonical.expanduser().resolve()
        if (
            target_resolved == canonical_resolved
            or target_resolved in canonical_resolved.parents
            or canonical_resolved in target_resolved.parents
        ):
            raise ValueError("dedao-kbase Agent Package review workspace must not overlap canonical artifacts")

        latest = (
            db.query(KBAudit)
            .filter(KBAudit.op == "dedao_kbase_agent_package_sync_draft")
            .order_by(KBAudit.ts.desc(), KBAudit.id.desc())
            .first()
        )
        previous_cursor = str((latest.diff or {}).get("cursor") or "") if latest else ""
        base_fingerprint = _artifact_fingerprint(canonical)
        workspace_metadata = read_workspace_metadata(target)
        workspace_valid = (
            workspace_artifacts_valid(target)
            and str(workspace_metadata.get("base_fingerprint") or "") == base_fingerprint
            and str(workspace_metadata.get("cursor") or "") == previous_cursor
            and str(workspace_metadata.get("producer_base_url") or "") == base_url
        )
        mode = "incremental" if workspace_valid else "rebuild"
        client = DedaoKBaseReleaseClient(base_url, auth_token=auth_token)
        records = _list_agent_package_records(
            client,
            after=previous_cursor if mode == "incremental" else "",
            limit=limit,
            replay_all=mode == "rebuild",
        )
        if not records:
            return {
                "status": "up_to_date" if mode == "incremental" else "no_agent_packages",
                "mode": mode,
                "cursor": previous_cursor,
                "package_count": 0,
                "held_packages": [],
                "base_fingerprint": base_fingerprint,
            }

        eligible: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        held_packages: list[dict[str, Any]] = []
        for record in records:
            package_id = str(record.get("package_id") or "").strip()
            version = str(record.get("version") or "").strip()
            package = client.get_agent_package(package_id, version=version)
            releases = [
                client.get_release(str(reference.get("release_id") or ""))
                for reference in package.get("releases") or []
            ]
            assessment = assess_agent_package_for_health(package, releases)
            if assessment["eligible"]:
                eligible.append((package, releases))
            else:
                held_packages.append(
                    {
                        "package_id": package_id,
                        "version": version,
                        "reasons": assessment["hold_reasons"],
                    }
                )

        cursor = f"{records[-1].get('package_id', '')}@{records[-1].get('version', '')}"
        gate = {
            "serving_allowed": False,
            "blocking_reasons": ["human_domain_review_required"],
        }
        if not eligible:
            report = {
                "status": "held",
                "mode": mode,
                "base_url": base_url,
                "artifact_dir": str(target),
                "base_artifact_dir": str(canonical),
                "previous_cursor": previous_cursor,
                "cursor": cursor,
                "base_fingerprint": base_fingerprint,
                "package_count": 0,
                "package_ids": [],
                "held_packages": held_packages,
                "gate": gate,
            }
            db.add(
                KBAudit(
                    doc_id=None,
                    op="dedao_kbase_agent_package_sync_draft",
                    actor=actor,
                    diff=report,
                )
            )
            db.commit()
            return report

        current_time = now or datetime.now(UTC)
        target.parent.mkdir(parents=True, exist_ok=True)
        candidate = Path(tempfile.mkdtemp(prefix=f".{target.name}.candidate-", dir=target.parent))
        source = target if mode == "incremental" else canonical
        try:
            if source.exists():
                shutil.copytree(source, candidate, dirs_exist_ok=True)
            if mode == "rebuild":
                _normalize_canonical_review_status(candidate)
            existing_lineages = _agent_package_lineages_by_release(candidate)
            package_results = [
                compile_agent_package_artifacts(
                    package=package,
                    releases=releases,
                    base_artifact_dir=candidate,
                    source_root=source_root,
                    now=current_time,
                )
                for package, releases in eligible
            ]
            combined = combine_release_results(package_results)
            merged_lineages = _preserve_agent_package_lineage(combined, existing_lineages)
            _write_agent_package_lineage_to_artifacts(candidate, merged_lineages)
            previous_packages = (
                workspace_metadata.get("agent_packages") or [] if mode == "incremental" else []
            )
            package_receipts = {
                (
                    str(item.get("package_id") or ""),
                    str(item.get("version") or ""),
                    str(item.get("content_hash") or ""),
                ): item
                for item in previous_packages
                if isinstance(item, dict)
            }
            for package, _ in eligible:
                evaluation = package["evaluation"]
                receipt = {
                    "package_id": package["package_id"],
                    "version": package["version"],
                    "content_hash": package["content_hash"],
                    "release_ids": [
                        str(reference["release_id"]) for reference in package["releases"]
                    ],
                    "evaluation_status": "passed",
                    "evaluation_suite_version": evaluation["suite_version"],
                    "evaluation_input_hash": evaluation["input_hash"],
                    "evaluation_evaluator_version": evaluation["evaluator_version"],
                    "evaluated_at": evaluation["evaluated_at"],
                }
                key = (receipt["package_id"], receipt["version"], receipt["content_hash"])
                package_receipts[key] = receipt
            all_package_receipts = [package_receipts[key] for key in sorted(package_receipts)]
            combined.manifest["agent_packages"] = all_package_receipts
            draft_manifest = write_draft_artifacts(
                combined,
                candidate,
                extractor=f"dedao-kbase-agent-package:{base_url}",
                created_at=current_time,
                note="evidence-only Agent Packages synced as drafts; domain review remains required.",
            )
            draft_manifest.update(
                {
                    "base_fingerprint": base_fingerprint,
                    "cursor": cursor,
                    "producer_base_url": base_url,
                    "sync_mode": mode,
                    "agent_packages": all_package_receipts,
                }
            )
            (candidate / "draft_manifest.json").write_text(
                json.dumps(draft_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            gate = validate_artifact_review_gate(candidate)
            _replace_workspace(candidate, target)
        finally:
            if candidate.exists():
                shutil.rmtree(candidate)

        report = {
            "status": "draft_written",
            "mode": mode,
            "base_url": base_url,
            "artifact_dir": str(target),
            "base_artifact_dir": str(canonical),
            "base_fingerprint": base_fingerprint,
            "previous_cursor": previous_cursor,
            "cursor": cursor,
            "package_count": len(eligible),
            "package_ids": [package["package_id"] for package, _ in eligible],
            "held_packages": held_packages,
            "diff": combined.diff,
            "draft_manifest": draft_manifest,
            "gate": gate,
        }
        db.add(
            KBAudit(
                doc_id=None,
                op="dedao_kbase_agent_package_sync_draft",
                actor=actor,
                diff=report,
            )
        )
        db.commit()
        return report


def run_system_kb_lifecycle_once(
    db: Session,
    *,
    now: datetime | None = None,
    crystallize_min_count: int = 100,
    eval_limit: int = 10_000,
    actor: str = "system",
) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    lint = lint_knowledge_base(db)
    decay = apply_confidence_decay(db, now=current_time, actor=actor)
    crystallize = draft_crystallized_claim_candidates(
        db,
        min_count=crystallize_min_count,
        now=current_time,
    )
    eval_report = run_system_kb_eval_cases(db, limit=eval_limit)
    report = {
        "lint": lint,
        "decay": decay,
        "crystallize": {
            "draft_candidates": len(crystallize["draft_claims"]),
            "min_count": crystallize["min_count"],
            "generated_at": crystallize["generated_at"],
        },
        "eval": eval_report,
    }
    db.add(
        KBAudit(
            doc_id=None,
            op="lifecycle_report",
            actor=actor,
            diff=report,
        )
    )
    db.commit()
    return report


def run_system_kb_reindex_once(db: Session, *, actor: str = "system") -> dict[str, Any]:
    """Rebuild serving search indexes and persist the pgvector health report."""

    return run_system_kb_reindex_report(db, actor=actor)


@celery_app.task(time_limit=600, name="app.tasks.system_knowledge_lifecycle.run_system_kb_lifecycle")
def run_system_kb_lifecycle() -> dict[str, Any]:
    logger.info("[system_kb_lifecycle] start")
    with SessionLocal() as db:
        result = run_system_kb_lifecycle_once(db, actor="celery:system_kb_lifecycle")
    logger.info("[system_kb_lifecycle] done: %s", result.get("crystallize"))
    return result


@celery_app.task(time_limit=900, name="app.tasks.system_knowledge_lifecycle.run_system_kb_reindex")
def run_system_kb_reindex() -> dict[str, Any]:
    logger.info("[system_kb_reindex] start")
    with SessionLocal() as db:
        result = run_system_kb_reindex_once(db, actor="celery:system_kb_reindex")
    logger.info("[system_kb_reindex] done: %s", result.get("reindex"))
    return result


@celery_app.task(time_limit=300, name="app.tasks.system_knowledge_lifecycle.flush_dedao_kbase_feedback")
def flush_dedao_kbase_feedback() -> dict[str, Any]:
    logger.info("[dedao_kbase_feedback] start")
    with SessionLocal() as db:
        result = flush_dedao_kbase_feedback_once(
            db,
            base_url=settings.dedao_kbase_release_base_url,
            auth_token=settings.dedao_kbase_auth_token,
            actor="celery:dedao_kbase_feedback",
        )
    logger.info("[dedao_kbase_feedback] done: %s", result.get("status"))
    return result


@celery_app.task(time_limit=600, name="app.tasks.system_knowledge_lifecycle.sync_dedao_kbase_export_draft")
def sync_dedao_kbase_export_draft() -> dict[str, Any]:
    """Scheduled online dedao-kbase sync.

    The task only writes draft artifacts. Serving import still requires human
    review plus the normal release gate.
    """
    logger.info("[dedao_kbase_export_sync] start")
    canonical_artifact_dir = _default_system_kb_artifact_dir()
    with SessionLocal() as db:
        if settings.dedao_kbase_release_base_url:
            artifact_dir = _dedao_kbase_review_artifact_dir()
            result = sync_dedao_kbase_releases_draft_once(
                db,
                base_url=settings.dedao_kbase_release_base_url,
                auth_token=settings.dedao_kbase_auth_token,
                artifact_dir=artifact_dir,
                base_artifact_dir=canonical_artifact_dir,
                source_root=settings.dedao_kbase_source_root,
                actor="celery:dedao_kbase_release_sync",
                limit=settings.dedao_kbase_release_batch_size,
            )
        else:
            artifact_dir = canonical_artifact_dir
            result = sync_dedao_kbase_export_draft_once(
                db,
                export_url=settings.dedao_kbase_export_url,
                auth_token=settings.dedao_kbase_auth_token,
                artifact_dir=artifact_dir,
                source_root=settings.dedao_kbase_source_root,
                actor="celery:dedao_kbase_export_sync",
            )
    logger.info("[dedao_kbase_export_sync] done: %s", result.get("status"))
    return result


@celery_app.task(
    time_limit=600,
    name="app.tasks.system_knowledge_lifecycle.sync_dedao_kbase_agent_packages_draft",
)
def sync_dedao_kbase_agent_packages_draft() -> dict[str, Any]:
    """Explicit pilot task for Agent Packages; never scheduled or auto-published."""
    logger.info("[dedao_kbase_agent_package_sync] start")
    with SessionLocal() as db:
        result = sync_dedao_kbase_agent_packages_draft_once(
            db,
            base_url=settings.dedao_kbase_release_base_url,
            auth_token=settings.dedao_kbase_auth_token,
            artifact_dir=_dedao_kbase_review_artifact_dir() / "agent-packages",
            base_artifact_dir=_default_system_kb_artifact_dir(),
            source_root=settings.dedao_kbase_source_root,
            actor="celery:dedao_kbase_agent_package_sync",
            limit=settings.dedao_kbase_release_batch_size,
        )
    logger.info("[dedao_kbase_agent_package_sync] done: %s", result.get("status"))
    return result
