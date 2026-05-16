#!/usr/bin/env python3
"""Draft Dedao course knowledge into reviewed system KB V2 artifacts.

Default mode is dry-run: print a review-friendly diff and do not mutate files.
Use --write only after reviewing the diff.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./system_kb_ingest_cli.db")

DEFAULT_SOURCE_ROOT = "/Users/liqiuhua/work/personal/down-dedao"
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "system_kb_v2_seed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--course", action="append", dest="courses", help="Course name to ingest. Repeatable.")
    parser.add_argument("--max-courses", type=int, default=None)
    parser.add_argument("--max-lessons-per-course", type=int, default=None)
    parser.add_argument("--write", action="store_true", help="Write merged JSONL artifacts. Default is dry-run.")
    parser.add_argument("--json-summary", action="store_true", help="Print machine-readable summary instead of prose.")
    parser.add_argument("--no-diff", action="store_true", help="Skip unified diff output in dry-run mode.")
    args = parser.parse_args()

    from app.services.system_knowledge_ingest import (
        build_pr_style_diff,
        compile_dedao_ingest_artifacts,
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
        _print_summary(summary, as_json=args.json_summary)
        return 0

    if args.json_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_summary(summary, as_json=False)
    if not args.no_diff:
        diff = build_pr_style_diff(result, args.artifact_dir)
        print("\n--- PR-style artifact diff ---")
        print(diff or "(no artifact changes)")
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
    print("sources:")
    for source in summary["sources"]:
        print(
            "  - "
            f"{source['course_name']} | claims={source['claims_generated']} | "
            f"lessons={source['lessons_read']} | domains={','.join(source['domains'])}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
