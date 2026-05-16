#!/usr/bin/env python3
"""Authoring-plane CLI for compiling course sources into system KB artifacts.

Default mode is dry-run: print a reviewable summary/diff and do not mutate
artifacts. Use --write after review. Use --promote-reviewed only after human
approval of the generated artifacts.
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

os.environ.setdefault("DATABASE_URL", "sqlite:///./system_kb_ingest_cli.db")

DEFAULT_SOURCE_ROOT = "/Users/liqiuhua/work/personal/down-dedao"
DEFAULT_ARTIFACT_DIR = BACKEND_ROOT / "data" / "system_kb_v2_seed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--course", action="append", dest="courses", help="Course name to ingest. Repeatable.")
    parser.add_argument("--max-courses", type=int, default=None)
    parser.add_argument("--max-lessons-per-course", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run mode. This is the default.")
    parser.add_argument("--write", action="store_true", help="Write merged JSONL artifacts.")
    parser.add_argument("--promote-reviewed", action="store_true", help="Promote draft artifacts to reviewed after write.")
    parser.add_argument("--reviewer", default=None, help="Reviewer id/email required by --promote-reviewed.")
    parser.add_argument("--json-summary", action="store_true", help="Print machine-readable JSON summary.")
    parser.add_argument("--no-diff", action="store_true", help="Skip unified diff output in dry-run mode.")
    args = parser.parse_args()

    if args.promote_reviewed and not args.write:
        parser.error("--promote-reviewed requires --write")
    if args.promote_reviewed and not args.reviewer:
        parser.error("--promote-reviewed requires --reviewer")

    from app.services.system_knowledge_ingest import (
        build_pr_style_diff,
        compile_dedao_ingest_artifacts,
        promote_artifact_review_status,
        write_reviewed_artifacts,
    )

    result = compile_dedao_ingest_artifacts(
        source_root=args.source_root,
        base_artifact_dir=args.artifact_dir,
        course_names=args.courses,
        max_courses=args.max_courses,
        max_lessons_per_course=args.max_lessons_per_course,
    )
    summary = {
        "mode": "write" if args.write else "dry_run",
        "source_root": str(result.source_root),
        "artifact_dir": str(Path(args.artifact_dir)),
        "diff": result.diff,
        "source_count": len(result.source_stats),
        "sources": result.source_stats,
    }

    if args.write:
        summary["counts"] = write_reviewed_artifacts(result, args.artifact_dir)
        if args.promote_reviewed:
            summary["review"] = promote_artifact_review_status(args.artifact_dir, reviewer=args.reviewer)
        _print_summary(summary, as_json=args.json_summary)
        return 0

    _print_summary(summary, as_json=args.json_summary)
    if not args.json_summary and not args.no_diff:
        print("\n--- PR-style artifact diff ---")
        print(build_pr_style_diff(result, args.artifact_dir) or "(no artifact changes)")
    return 0


def _print_summary(summary: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"mode: {summary['mode']}")
    print(f"source_root: {summary['source_root']}")
    print(f"artifact_dir: {summary['artifact_dir']}")
    print(f"source_count: {summary['source_count']}")
    print("diff:")
    for key, value in summary["diff"].items():
        print(f"  {key}: {value}")
    if "counts" in summary:
        print("counts:")
        for key, value in summary["counts"].items():
            print(f"  {key}: {value}")
    if "review" in summary:
        print("review:")
        for key, value in summary["review"].items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
