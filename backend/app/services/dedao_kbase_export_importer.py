"""Import a dedao-kbase System KB export through the reviewed artifact gate."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from app.services.down_dedao_wiki_bridge import (
    DownDedaoBridgeResult,
    _ensure_relation_endpoint_entities,
    _import_system_kb_export,
    _load_existing_doc_ids,
    _load_existing_placeholder_doc_ids,
    _load_existing_relation_keys,
)
from app.services.system_knowledge_ingest import IngestResult


SYSTEM_KB_EXPORT_FILENAME = "system_kb_export.json"
PIPELINE_NAME = "dedao_kbase_export_v1"
DEFAULT_LICENSE_SCOPE = "internal_transformed_claims"


def compile_dedao_kbase_export_artifacts(
    *,
    source_root: str | Path,
    base_artifact_dir: str | Path,
    export_path: str | Path | None = None,
    now: datetime | None = None,
) -> IngestResult:
    """Compile a dedao-kbase export into draft System KB artifacts.

    This intentionally reads only ``artifacts/system_kb_export.json`` (or the
    explicit ``export_path``). Raw notes, personal files, and sidecar artifacts
    in the source repo are not scanned by this path.
    """
    source_root = Path(source_root).expanduser()
    base_artifact_dir = Path(base_artifact_dir)
    export_path = Path(export_path).expanduser() if export_path else source_root / "artifacts" / SYSTEM_KB_EXPORT_FILENAME
    now = now or datetime.now(UTC)

    payload = _read_export(export_path)
    bridge_result = DownDedaoBridgeResult(source_root=source_root, base_artifact_dir=base_artifact_dir)

    existing_docs = _load_existing_doc_ids(base_artifact_dir)
    existing_placeholders = _load_existing_placeholder_doc_ids(base_artifact_dir)
    existing_relations = _load_existing_relation_keys(base_artifact_dir)
    _import_system_kb_export(payload, bridge_result, existing_docs, existing_placeholders, existing_relations, now)
    _ensure_relation_endpoint_entities(bridge_result, existing_docs, base_artifact_dir, now)

    _normalize_export_metadata(bridge_result, payload)
    bridge_result.diff = {
        "pages_added": len(bridge_result.pages),
        "entities_added": len(bridge_result.entities),
        "claims_added": len(bridge_result.claims),
        "relations_added": len(bridge_result.relations),
    }

    result = IngestResult(
        source_root=source_root,
        base_artifact_dir=base_artifact_dir,
        pages=sorted(bridge_result.pages, key=lambda item: item["doc_id"]),
        entities=sorted(bridge_result.entities, key=lambda item: item["doc_id"]),
        claims=sorted(bridge_result.claims, key=lambda item: item["doc_id"]),
        relations=sorted(
            bridge_result.relations,
            key=lambda item: (item["src_doc_id"], item["relation"], item["dst_doc_id"]),
        ),
        diff=bridge_result.diff,
        manifest=_manifest_for_export(source_root, export_path, payload, bridge_result.diff, now),
        source_stats=[
            {
                "source": payload.get("source") or "dedao-kbase",
                "schema_id": payload.get("schema_id"),
                "version": payload.get("version"),
                "source_repo": payload.get("source_repo"),
                "source_commit": payload.get("source_commit"),
                "export_path": str(export_path),
                "pages": len(bridge_result.pages),
                "entities": len(bridge_result.entities),
                "claims": len(bridge_result.claims),
                "relations": len(bridge_result.relations),
            }
        ],
    )
    return result


def _read_export(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"dedao-kbase export not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"dedao-kbase export must be a JSON object: {path}")
    if payload.get("type") not in {None, "system_kb_v2_export"}:
        raise ValueError(f"unsupported dedao-kbase export type: {payload.get('type')}")
    return payload


def _manifest_for_export(
    source_root: Path,
    export_path: Path,
    payload: dict[str, Any],
    diff: dict[str, int],
    now: datetime,
) -> dict[str, Any]:
    return {
        "compiled_at": now.isoformat(),
        "source_root": str(source_root),
        "export_path": str(export_path),
        "source": payload.get("source") or "dedao-kbase",
        "source_repo": payload.get("source_repo"),
        "source_commit": payload.get("source_commit"),
        "source_version": payload.get("version"),
        "schema_id": payload.get("schema_id"),
        "ingest": {
            "pipeline": PIPELINE_NAME,
            "review_status": "draft",
            "requires_review": True,
            "serving_allowed": False,
        },
        "diff": diff,
    }


def _normalize_export_metadata(result: DownDedaoBridgeResult, payload: dict[str, Any]) -> None:
    source_repo = payload.get("source_repo")
    source_commit = payload.get("source_commit") or payload.get("version")
    source = payload.get("source") or "dedao-kbase"
    default_source_path = _default_source_path(payload)
    source_paths = _source_paths_by_doc_id(payload, default_source_path)

    for row in [*result.pages, *result.entities, *result.claims]:
        metadata = dict(row.get("metadata") or {})
        doc_id = str(row.get("doc_id") or "")
        source_path = source_paths.get(doc_id) or metadata.get("source_path") or metadata.get("source_file")
        metadata.update(
            {
                "origin": "dedao-kbase-export",
                "source": source,
                "source_repo": source_repo,
                "source_commit": source_commit,
                "source_path": source_path,
                "source_version": payload.get("version"),
                "license_scope": metadata.get("license_scope")
                or payload.get("license_scope")
                or DEFAULT_LICENSE_SCOPE,
                "review_status": "draft",
            }
        )
        row["metadata"] = metadata

    for relation in result.relations:
        metadata = dict(relation.get("metadata") or {})
        metadata.update(
            {
                "origin": "dedao-kbase-export",
                "source": source,
                "source_repo": source_repo,
                "source_commit": source_commit,
                "source_version": payload.get("version"),
                "license_scope": metadata.get("license_scope")
                or payload.get("license_scope")
                or DEFAULT_LICENSE_SCOPE,
                "review_status": "draft",
            }
        )
        relation["metadata"] = metadata


def _default_source_path(payload: dict[str, Any]) -> str | None:
    paths = [str(page.get("source_file") or "") for page in payload.get("pages") or [] if isinstance(page, dict)]
    paths = [path for path in paths if path]
    if len(paths) == 1:
        return paths[0]
    return None


def _source_paths_by_doc_id(payload: dict[str, Any], default_source_path: str | None) -> dict[str, str]:
    paths: dict[str, str] = {}
    page_paths_by_page_doc_id: dict[str, str] = {}
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        source_path = str(page.get("source_file") or page.get("source_path") or "")
        if page_id and source_path:
            doc_id = f"page:ak-kbase:{page_id}"
            paths[doc_id] = source_path
            page_paths_by_page_doc_id[doc_id] = source_path

    for entity in payload.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        doc_id = str(entity.get("doc_id") or "")
        source_path = str(entity.get("source_file") or entity.get("source_path") or "")
        if doc_id and source_path:
            paths[doc_id] = source_path

    for claim in payload.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id") or str(claim.get("doc_id", "")).replace("claim:", "")
        doc_id = f"claim:{claim_id}" if claim_id else ""
        metadata = claim.get("metadata") if isinstance(claim.get("metadata"), dict) else {}
        derived_from_page = str(metadata.get("derived_from_page") or "")
        source_path = (
            str(claim.get("source_file") or claim.get("source_path") or "")
            or page_paths_by_page_doc_id.get(derived_from_page)
            or default_source_path
        )
        if doc_id and source_path:
            paths[doc_id] = source_path
    return paths
