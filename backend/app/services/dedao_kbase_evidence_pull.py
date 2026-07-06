"""Dry-run consumption of dedao-kbase verified evidence pull manifests.

This module intentionally does not write System KB artifacts or database rows.
It checks the transport contract and produces review candidates for the next
health import gate.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


PULL_MANIFEST_CONTRACT = "verified_evidence_pull_manifest_v1"
EVIDENCE_PACK_CONTRACT = "verified_evidence_pack_v1"
SAFE_HEALTH_RISK_TIERS = {"auto_usable"}
SAFE_HEALTH_QUALITY_STATUSES = {"usable"}


def dry_run_dedao_kbase_evidence_pull(
    *,
    manifest_url: str,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """Fetch a kbase pull manifest and return a no-write health import report."""

    manifest = fetch_dedao_kbase_evidence_manifest(manifest_url, auth_token=auth_token)
    _validate_pull_manifest(manifest)
    export_url = _resolve_manifest_endpoint(manifest_url, manifest["endpoints"]["evidence_pack_jsonl_url"])
    records = fetch_dedao_kbase_evidence_jsonl(export_url, auth_token=auth_token)
    return build_dedao_kbase_evidence_dry_run_report(manifest, records)


def fetch_dedao_kbase_evidence_manifest(manifest_url: str, *, auth_token: str | None = None) -> dict[str, Any]:
    payload = _fetch_text(manifest_url, auth_token=auth_token, accept="application/json")
    manifest = json.loads(payload)
    if not isinstance(manifest, dict):
        raise ValueError("dedao-kbase evidence manifest must be a JSON object")
    return manifest


def fetch_dedao_kbase_evidence_jsonl(export_url: str, *, auth_token: str | None = None) -> list[dict[str, Any]]:
    payload = _fetch_text(export_url, auth_token=auth_token, accept="application/x-ndjson")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"evidence JSONL line {line_number} must be an object")
        records.append(record)
    return records


def build_dedao_kbase_evidence_dry_run_report(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    _validate_pull_manifest(manifest)
    current_pack = manifest["current_pack"]
    expected_fingerprint = str(current_pack["source_fingerprint"])
    candidates: list[dict[str, Any]] = []
    rejected_reasons: dict[str, int] = {}
    review_required = 0
    blocked = 0

    for record in records:
        _validate_evidence_record(record, expected_fingerprint)
        reason = _record_rejection_reason(record)
        if reason == "accepted":
            candidates.append(_candidate_from_record(record))
        elif reason == "review_required":
            review_required += 1
        else:
            blocked += 1
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1

    return {
        "status": "dry_run",
        "consumer_contract": manifest["consumer_contract"],
        "project_id": manifest["project_id"],
        "target_system": manifest["target_system"],
        "pack_id": current_pack["pack_id"],
        "source_fingerprint": expected_fingerprint,
        "manifest_record_count": current_pack.get("record_count"),
        "total_records": len(records),
        "accepted_candidates": len(candidates),
        "review_required_records": review_required,
        "blocked_records": blocked,
        "rejected_reasons": rejected_reasons,
        "gate_checks": [
            "check_source_fingerprint",
            "reject_blocked",
            "draft_only",
        ],
        "would_write": False,
        "candidates": candidates,
    }


def _fetch_text(url: str, *, auth_token: str | None, accept: str) -> str:
    headers = {"Accept": accept}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"dedao-kbase evidence fetch failed: HTTP {exc.code} {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"dedao-kbase evidence fetch failed: {url}: {exc.reason}") from exc


def _validate_pull_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("consumer_contract") != PULL_MANIFEST_CONTRACT:
        raise ValueError(f"unsupported evidence manifest contract: {manifest.get('consumer_contract')}")
    if manifest.get("project_id") != "health":
        raise ValueError(f"unsupported evidence manifest project: {manifest.get('project_id')}")
    current_pack = manifest.get("current_pack")
    if not isinstance(current_pack, dict):
        raise ValueError("evidence manifest missing current_pack")
    if current_pack.get("consumer_contract") != EVIDENCE_PACK_CONTRACT:
        raise ValueError(f"unsupported evidence pack contract: {current_pack.get('consumer_contract')}")
    if not current_pack.get("pack_id") or not current_pack.get("source_fingerprint"):
        raise ValueError("evidence manifest missing current pack identity")
    endpoints = manifest.get("endpoints")
    if not isinstance(endpoints, dict) or not endpoints.get("evidence_pack_jsonl_url"):
        raise ValueError("evidence manifest missing evidence_pack_jsonl_url")
    gate = manifest.get("consumer_gate")
    if not isinstance(gate, dict):
        raise ValueError("evidence manifest missing consumer_gate")
    if gate.get("must_check_source_fingerprint") is not True:
        raise ValueError("evidence manifest must require source fingerprint checks")
    if gate.get("must_reject_blocked") is not True:
        raise ValueError("evidence manifest must require blocked-record rejection")


def _validate_evidence_record(record: dict[str, Any], expected_fingerprint: str) -> None:
    if record.get("consumer_contract") != EVIDENCE_PACK_CONTRACT:
        raise ValueError(f"unsupported evidence record contract: {record.get('consumer_contract')}")
    if record.get("source_fingerprint") != expected_fingerprint:
        raise ValueError(
            f"source_fingerprint_mismatch: record={record.get('source_fingerprint')} manifest={expected_fingerprint}"
        )
    if not record.get("evidence_id"):
        raise ValueError("evidence record missing evidence_id")


def _record_rejection_reason(record: dict[str, Any]) -> str:
    risk_tier = str(record.get("risk_tier") or "")
    quality_status = str(record.get("quality_status") or "")
    if risk_tier == "blocked" or quality_status == "rejected":
        return "blocked_record"
    source_refs = record.get("source_refs") if isinstance(record.get("source_refs"), dict) else {}
    if not source_refs.get("source_hash") or not source_refs.get("citations"):
        return "missing_source_refs"
    if risk_tier not in SAFE_HEALTH_RISK_TIERS or quality_status not in SAFE_HEALTH_QUALITY_STATUSES:
        return "review_required"
    return "accepted"


def _candidate_from_record(record: dict[str, Any]) -> dict[str, Any]:
    source_refs = record.get("source_refs") if isinstance(record.get("source_refs"), dict) else {}
    return {
        "evidence_id": record["evidence_id"],
        "title": record.get("title") or "",
        "summary": record.get("summary") or record.get("normalized_claim") or "",
        "source_refs": {
            "source_type": source_refs.get("source_type"),
            "source_id": source_refs.get("source_id"),
            "claim_id": source_refs.get("claim_id"),
            "citations": source_refs.get("citations") or [],
            "source_hash": source_refs.get("source_hash"),
        },
        "allowed_uses": record.get("allowed_uses") or [],
        "blocked_uses": record.get("blocked_uses") or [],
        "review_status": "draft_candidate",
    }


def _resolve_manifest_endpoint(manifest_url: str, endpoint: str) -> str:
    return urljoin(manifest_url, endpoint)
