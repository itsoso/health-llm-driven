"""Transport immutable dedao-kbase Knowledge Releases into draft System KB artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.services.dedao_kbase_export_importer import compile_dedao_kbase_export_payload_artifacts
from app.services.system_knowledge_ingest import IngestResult


RELEASE_PIPELINE_NAME = "dedao_kbase_release_v1"
_OPAQUE_ID = re.compile(r"[^A-Za-z0-9._:-]+")


class DedaoKBaseReleaseClient:
    def __init__(self, base_url: str, *, auth_token: str | None = None, timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url:
            raise ValueError("dedao-kbase release base URL is required")
        self.auth_token = (auth_token or "").strip()
        self.timeout = timeout

    def list_releases(self, *, after: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("release list limit must be between 1 and 200")
        query = urlencode({"after": after, "limit": limit})
        payload = self._request("GET", f"/api/knowledge/releases?{query}")
        records = payload.get("releases") if isinstance(payload, dict) else None
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ValueError("dedao-kbase release list has invalid schema")
        return records

    def get_release(self, release_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/knowledge/releases/{quote(release_id, safe='')}")
        _validate_release(payload)
        return payload

    def post_feedback(
        self,
        release_id: str,
        *,
        event_id: str,
        consumer: str,
        outcome: str,
        claim_ids: list[str] | None = None,
        reason_code: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "event_id": event_id,
            "consumer": consumer,
            "outcome": outcome,
        }
        if claim_ids:
            body["claim_ids"] = claim_ids
        if reason_code:
            body["reason_code"] = reason_code
        payload = self._request(
            "POST",
            f"/api/knowledge/releases/{quote(release_id, safe='')}/feedback",
            body,
        )
        if not isinstance(payload, dict):
            raise ValueError("dedao-kbase feedback response has invalid schema")
        return payload

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("ascii")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", headers=headers, data=data, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raise RuntimeError(f"dedao-kbase release request failed: HTTP {exc.code} {path}") from exc
        except URLError as exc:
            raise RuntimeError(f"dedao-kbase release request failed: {path}: {exc.reason}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"dedao-kbase release response is not valid JSON: {path}") from exc


def compile_knowledge_release_artifacts(
    *,
    release: dict[str, Any],
    base_artifact_dir: str | Path,
    source_root: str | Path,
    now: datetime | None = None,
) -> IngestResult:
    _validate_release(release)
    current_time = now or datetime.now(UTC)
    payload = _release_as_system_kb_export(release, current_time)
    result = compile_dedao_kbase_export_payload_artifacts(
        source_root=source_root,
        base_artifact_dir=base_artifact_dir,
        payload=payload,
        export_ref=f"knowledge-release:{release['release_id']}",
        now=current_time,
    )
    for row in [*result.pages, *result.entities, *result.claims, *result.relations]:
        metadata = dict(row.get("metadata") or {})
        metadata.update(
            {
                "origin": "dedao-kbase-release",
                "release_id": release["release_id"],
                "content_hash": release["content_hash"],
                "usage_policy": release["usage_policy"],
                "review_status": "draft",
            }
        )
        row["metadata"] = metadata
    result.manifest["ingest"].update(
        {
            "pipeline": RELEASE_PIPELINE_NAME,
            "review_status": "draft",
            "requires_review": True,
            "serving_allowed": False,
        }
    )
    result.manifest["release_id"] = release["release_id"]
    result.manifest["usage_policy"] = release["usage_policy"]
    return result


def combine_release_results(results: list[IngestResult]) -> IngestResult:
    if not results:
        raise ValueError("at least one release result is required")
    combined = results[-1]
    combined.pages = _unique_rows(results, "pages", "doc_id")
    combined.entities = _unique_rows(results, "entities", "doc_id")
    combined.claims = _unique_rows(results, "claims", "doc_id")
    combined.relations = _unique_relations(results)
    combined.diff = {
        "pages_added": len(combined.pages),
        "entities_added": len(combined.entities),
        "claims_added": len(combined.claims),
        "relations_added": len(combined.relations),
    }
    combined.source_stats = [item for result in results for item in result.source_stats]
    return combined


def _validate_release(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("dedao-kbase release must be a JSON object")
    required = ("release_id", "book_id", "content_hash", "usage_policy", "book", "analysis", "quality")
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise ValueError(f"dedao-kbase release missing fields: {', '.join(missing)}")
    if not isinstance(payload["book"], dict) or not isinstance(payload["analysis"], dict):
        raise ValueError("dedao-kbase release book and analysis must be JSON objects")
    if not isinstance(payload["quality"], dict):
        raise ValueError("dedao-kbase release quality must be a JSON object")
    if payload["usage_policy"] not in {"standard", "evidence_only"}:
        raise ValueError("dedao-kbase release has invalid usage_policy")
    if payload["quality"].get("decision") != "pass":
        raise ValueError("dedao-kbase release quality decision must be pass")
    claims = payload["analysis"].get("claims") if isinstance(payload["analysis"], dict) else None
    if not isinstance(claims, list) or not claims:
        raise ValueError("dedao-kbase release requires structured claims")
    if any(not isinstance(claim, dict) for claim in claims):
        raise ValueError("dedao-kbase release claims must be JSON objects")
    claim_ids = [str(claim.get("id") or "").strip() for claim in claims]
    if any(not claim_id for claim_id in claim_ids):
        raise ValueError("dedao-kbase release claim id is required")
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError("dedao-kbase release has duplicate claim id")


def _release_as_system_kb_export(release: dict[str, Any], now: datetime) -> dict[str, Any]:
    release_id = str(release["release_id"])
    book_id = _safe_id(str(release["book_id"]))
    book = release["book"]
    analysis = release["analysis"]
    title = str(book.get("title") or book.get("name") or release["book_id"])
    source_ids = [str(item.get("id")) for item in release.get("sources") or [] if item.get("id")]
    page_id = f"release-{_safe_id(release_id)}"
    claims = []
    relations = []
    entity_doc_id = f"entity:knowledge_source:{book_id}"
    for claim in analysis["claims"]:
        claim_id = f"{_safe_id(release_id)}-{_safe_id(str(claim.get('id') or 'claim'))}"
        citation_ids = [str(item) for item in claim.get("citation_ids") or []]
        metadata = {
            "release_id": release_id,
            "content_hash": release["content_hash"],
            "usage_policy": release["usage_policy"],
            "citation_ids": citation_ids,
            "scope": claim.get("scope") or [],
            "risk_level": claim.get("risk_level") or "low",
            "review_status": "draft",
        }
        claims.append(
            {
                "claim_id": claim_id,
                "entity_type": "knowledge_source",
                "entity_id": book_id,
                "title": str(claim.get("statement") or title),
                "summary": str(claim.get("statement") or ""),
                "body": str(claim.get("statement") or ""),
                "sources": citation_ids or source_ids or [release_id],
                "metadata": metadata,
            }
        )
        relations.append(
            {
                "src_doc_id": entity_doc_id,
                "dst_doc_id": f"claim:{claim_id}",
                "relation": "has_claim",
                "confidence": float(claim.get("confidence") or 0.5),
                "source_claim_id": f"claim:{claim_id}",
                "metadata": metadata,
            }
        )
    return {
        "schema_id": "knowledge-release-system-kb-export",
        "version": release_id,
        "source": "dedao-kbase",
        "source_commit": release["content_hash"],
        "compiled_at": now.isoformat(),
        "pages": [
            {
                "id": page_id,
                "title": title,
                "summary": str(analysis.get("summary") or ""),
                "content": str(analysis.get("summary") or ""),
                "content_hash": release["content_hash"],
                "review_status": "draft",
            }
        ],
        "entities": [
            {
                "doc_id": entity_doc_id,
                "entity_type": "knowledge_source",
                "entity_id": book_id,
                "title": title,
                "summary": str(analysis.get("summary") or ""),
                "body": str(analysis.get("summary") or ""),
                "sources": source_ids or [release_id],
                "metadata": {"release_id": release_id, "review_status": "draft"},
            }
        ],
        "claims": claims,
        "relations": relations,
    }


def _safe_id(value: str) -> str:
    return _OPAQUE_ID.sub("-", value.strip()).strip("-") or "unknown"


def _unique_rows(results: list[IngestResult], field: str, key: str) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for result in results:
        for row in getattr(result, field):
            rows[str(row[key])] = row
    return sorted(rows.values(), key=lambda row: str(row[key]))


def _unique_relations(results: list[IngestResult]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for result in results:
        for row in result.relations:
            key = (str(row["src_doc_id"]), str(row["relation"]), str(row["dst_doc_id"]))
            rows[key] = row
    return [rows[key] for key in sorted(rows)]
