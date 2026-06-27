#!/usr/bin/env python3
"""Compile a dedao-kbase export into gated System KB artifacts.

Default mode is dry-run. ``--write`` writes draft artifacts only; use
``--promote-reviewed --reviewer`` after human review to allow serving import.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./dedao_kbase_export_ingest_cli.db")

DEFAULT_SOURCE_ROOT = os.environ.get("DEDAO_KBASE_ROOT", "/Users/liqiuhua/work/personal/down-dedao")
DEFAULT_ARTIFACT_DIR = BACKEND_ROOT / "data" / "system_kb_v2_seed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--export-path", default=None)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run mode. This is the default.")
    parser.add_argument("--write", action="store_true", help="Write draft artifacts.")
    parser.add_argument("--promote-reviewed", action="store_true", help="Promote draft artifacts after review.")
    parser.add_argument("--reviewer", default=None, help="Reviewer id/email required by --promote-reviewed.")
    parser.add_argument("--json-summary", action="store_true", help="Print machine-readable JSON summary.")
    parser.add_argument("--no-diff", action="store_true", help="Skip PR-style diff output in dry-run mode.")
    args = parser.parse_args()

    if args.promote_reviewed and not args.write:
        parser.error("--promote-reviewed requires --write")
    if args.promote_reviewed and not args.reviewer:
        parser.error("--promote-reviewed requires --reviewer")

    from app.services.dedao_kbase_export_importer import compile_dedao_kbase_export_artifacts
    from app.services.system_knowledge_ingest import (
        build_pr_style_diff,
        review_draft_artifacts,
        validate_artifact_review_gate,
        write_draft_artifacts,
    )

    result = compile_dedao_kbase_export_artifacts(
        source_root=args.source_root,
        base_artifact_dir=args.artifact_dir,
        export_path=args.export_path,
    )
    export_path = result.manifest["export_path"]
    summary: dict[str, object] = {
        "mode": "dry_run",
        "source_root": str(result.source_root),
        "export_path": export_path,
        "artifact_dir": str(Path(args.artifact_dir)),
        "diff": result.diff,
        "source_count": len(result.source_stats),
        "sources": result.source_stats,
    }

    if args.write:
        draft_manifest = write_draft_artifacts(
            result,
            args.artifact_dir,
            extractor=f"dedao-kbase-export:{export_path}",
            note="dedao-kbase export imported as draft; requires human review before serving.",
        )
        gate = validate_artifact_review_gate(args.artifact_dir)
        summary["mode"] = "write_draft"
        summary["draft_manifest"] = draft_manifest
        summary["gate"] = gate
        if args.promote_reviewed:
            review = review_draft_artifacts(args.artifact_dir, reviewer=args.reviewer)
            summary["mode"] = "write_reviewed"
            summary["review"] = review
        _print_summary(summary, as_json=args.json_summary)
        return 0

    _print_summary(summary, as_json=args.json_summary)
    if not args.json_summary and not args.no_diff:
        print("\n--- PR-style artifact diff ---")
        print(build_pr_style_diff(result, args.artifact_dir) or "(no artifact changes)")
    return 0


def _print_summary(summary: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"mode: {summary['mode']}")
    print(f"source_root: {summary['source_root']}")
    print(f"export_path: {summary['export_path']}")
    print(f"artifact_dir: {summary['artifact_dir']}")
    print(f"source_count: {summary['source_count']}")
    print("diff:")
    for key, value in dict(summary["diff"]).items():
        print(f"  {key}: {value}")
    if "draft_manifest" in summary:
        print("draft_manifest:")
        for key, value in dict(summary["draft_manifest"]).items():
            print(f"  {key}: {value}")
    if "review" in summary:
        print("review:")
        for key, value in dict(summary["review"]).items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
