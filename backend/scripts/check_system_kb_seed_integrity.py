#!/usr/bin/env python3
"""Fast, dependency-free guard for the system-KB v2 seed artifacts.

Replicates the two hard gates of ``run_external_health_knowledge_release_gate.py``
(manifest counts + orphan claims) by reading ONLY the JSONL/manifest files — no DB,
no app import, no env vars — so it can run at pre-commit time and catch an incomplete
KB change the moment it is authored, before it ever reaches CI/main.

Recurring bug it exists to stop (has hit main >=3 times across exam-gap batches):
a claim is appended to ``claims.jsonl`` without (a) its connector entity, (b) a
linking edge in ``relations.jsonl``, and/or (c) the ``manifest.json`` count sync.
Each omission turns the release gate red (``lint.orphan_claims`` / manifest mismatch).

The reviewed/edge logic mirrors ``system_knowledge_importer`` exactly:
- a doc is "reviewed" iff ``metadata.review_status == "reviewed"``;
- an edge is imported iff BOTH endpoints are reviewed docs;
- an orphan is a reviewed claim/entity that no imported edge references.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "system_kb_v2_seed"

# doc-carrying artifacts (mirrors importer.DOC_FILES) + relations edges
DOC_FILES = (
    "entities.jsonl",
    "claims.jsonl",
    "pages.jsonl",
    "protocols.jsonl",
    "contraindications.jsonl",
    "eval_cases.jsonl",
)
# manifest.counts key -> artifact file (mirrors gate.MANIFEST_COUNT_FILES)
MANIFEST_COUNT_FILES = {
    "pages": "pages.jsonl",
    "entities": "entities.jsonl",
    "claims": "claims.jsonl",
    "protocols": "protocols.jsonl",
    "contraindications": "contraindications.jsonl",
    "eval_cases": "eval_cases.jsonl",
    "relations": "relations.jsonl",
}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:  # surface parse errors loudly
            raise ValueError(f"Invalid JSONL in {path.name}:{lineno}: {exc}") from exc
    return rows


def _is_reviewed(row: dict[str, Any]) -> bool:
    meta = row.get("metadata")
    return isinstance(meta, dict) and meta.get("review_status") == "reviewed"


def _claim_title_sources_key(row: dict[str, Any]) -> tuple[Any, tuple[Any, ...]]:
    sources = row.get("sources")
    if isinstance(sources, list):
        source_key = tuple(sorted(str(s) for s in sources))
    elif sources is None:
        source_key = ()
    else:
        source_key = (str(sources),)
    return (row.get("title"), source_key)


def check_seed_integrity(artifact_dir: Path) -> dict[str, Any]:
    """Return a report dict; ``status == "pass"`` iff the seed is release-gate clean."""
    artifact_dir = Path(artifact_dir)
    problems: list[str] = []

    # --- gate 1: manifest counts == non-empty line counts ---------------------
    manifest_path = artifact_dir / "manifest.json"
    manifest_counts: dict[str, Any] = {}
    if not manifest_path.exists():
        problems.append(f"missing manifest.json in {artifact_dir}")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw = manifest.get("counts")
        manifest_counts = raw if isinstance(raw, dict) else {}

    actual_counts: dict[str, int] = {}
    for key, filename in MANIFEST_COUNT_FILES.items():
        path = artifact_dir / filename
        actual = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()) if path.exists() else 0
        actual_counts[key] = actual
        expected = manifest_counts.get(key)
        if expected is None:
            problems.append(f"manifest.counts.{key} missing (actual {filename} = {actual})")
        elif int(expected) != actual:
            problems.append(
                f"manifest.counts.{key} = {int(expected)} but {filename} has {actual} rows "
                f"(sync manifest.counts.{key} -> {actual})"
            )

    # --- gate 2: no orphan reviewed claims / entities -------------------------
    reviewed_ids: set[str] = set()
    claim_rows: dict[str, dict[str, Any]] = {}
    entity_ids: set[str] = set()
    for filename in DOC_FILES:
        for row in _read_rows(artifact_dir / filename):
            doc_id = row.get("doc_id")
            if not doc_id or not _is_reviewed(row):
                continue
            reviewed_ids.add(doc_id)
            if filename == "claims.jsonl":
                claim_rows[doc_id] = row
            elif filename == "entities.jsonl":
                entity_ids.add(doc_id)

    linked: set[str] = set()
    for edge in _read_rows(artifact_dir / "relations.jsonl"):
        src, dst = edge.get("src_doc_id"), edge.get("dst_doc_id")
        if src in reviewed_ids and dst in reviewed_ids:  # importer skips edges to non-reviewed endpoints
            linked.add(src)
            linked.add(dst)

    orphan_claims = sorted(cid for cid in claim_rows if cid not in linked)
    orphan_entities = sorted(eid for eid in entity_ids if eid not in linked)

    # --- gate 3: no duplicate claims (identical title + sources) ---------------
    # A doc_id-unique claim can still be a true content duplicate when its title AND
    # sources match another; the release-gate's serving-key check (doc_id) misses it.
    title_groups: dict[tuple[Any, tuple[Any, ...]], list[str]] = {}
    for row in _read_rows(artifact_dir / "claims.jsonl"):
        doc_id = row.get("doc_id")
        if not doc_id:
            continue
        title_groups.setdefault(_claim_title_sources_key(row), []).append(str(doc_id))
    duplicate_titles = [
        {"title": title, "sources": list(sources), "doc_ids": sorted(doc_ids)}
        for (title, sources), doc_ids in title_groups.items()
        if len(doc_ids) > 1
    ]
    for dup in duplicate_titles:
        problems.append(
            f"duplicate claim title+sources: {dup['title']!r} "
            f"sources={dup['sources']} appears in {dup['doc_ids']} — "
            f"keep the canonical claim (most edges) and re-point its edges."
        )

    for cid in orphan_claims:
        row = claim_rows[cid]
        want = row.get("recommends_lookup") or []
        etype, eid = row.get("entity_type"), row.get("entity_id")
        target = want[0] if want else (f"entity:{etype}:{eid}" if etype and eid else "entity:<type>:<id>")
        problems.append(
            f"orphan claim {cid}: no imported edge references it. "
            f"Add reviewed entity {target} + a recommends_lookup edge "
            f"(src={cid}, dst={target}, source_claim_id={cid})"
        )
    for eid in orphan_entities:
        problems.append(f"orphan entity {eid}: no imported edge references it — link it to a reviewed claim or remove it.")

    return {
        "status": "fail" if problems else "pass",
        "problems": problems,
        "actual_counts": actual_counts,
        "orphan_claims": orphan_claims,
        "orphan_entities": orphan_entities,
        "duplicate_titles": duplicate_titles,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    # pre-commit passes changed filenames as positional args; accept + ignore them
    # (we always validate the whole seed dir, since integrity is cross-file).
    parser.add_argument("files", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        report = check_seed_integrity(Path(args.artifact_dir))
    except ValueError as exc:
        print(f"❌ system-KB seed integrity: {exc}", file=sys.stderr)
        return 1

    if report["status"] == "pass":
        print(
            "✅ system-KB seed integrity: manifest counts match + no orphan claims/entities "
            f"(claims={report['actual_counts'].get('claims')}, "
            f"entities={report['actual_counts'].get('entities')}, "
            f"relations={report['actual_counts'].get('relations')})"
        )
        return 0

    print("❌ system-KB seed integrity FAILED — this would turn the release gate red:", file=sys.stderr)
    for problem in report["problems"]:
        print(f"   - {problem}", file=sys.stderr)
    print(
        "\nAdding a claim = claim + reviewed connector entity + recommends_lookup edge + "
        "manifest count sync. See scripts/run_external_health_knowledge_release_gate.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
