#!/usr/bin/env python3
"""Absorb compiled down-dedao LLM Wiki artifacts into System KB V2 seed files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        default="~/work/personal/down-dedao",
        help="Root containing down-dedao artifacts/.",
    )
    parser.add_argument(
        "--artifact-dir",
        default=str(ROOT / "data" / "system_kb_v2_seed"),
        help="System KB V2 seed directory.",
    )
    parser.add_argument("--write", action="store_true", help="Write merged JSONL artifacts.")
    parser.add_argument("--json-summary", action="store_true", help="Print machine-readable summary only.")
    args = parser.parse_args()

    from app.services.down_dedao_wiki_bridge import (
        compile_down_dedao_wiki_artifacts,
        write_down_dedao_wiki_artifacts,
    )
    from app.services.gene_knowledge_audit import audit_gene_knowledge

    result = compile_down_dedao_wiki_artifacts(args.source_root, args.artifact_dir)
    gene_knowledge_path = Path(args.source_root).expanduser() / "artifacts" / "gene_knowledge.json"
    gene_knowledge_audit = None
    quality_issue_count = 0
    if gene_knowledge_path.exists():
        payload = json.loads(gene_knowledge_path.read_text(encoding="utf-8"))
        gene_knowledge_audit = audit_gene_knowledge(payload)
        gates = gene_knowledge_audit.get("quality_gates") or {}
        quality_issue_count = sum(len(value or []) for value in gates.values())

    counts = None
    if args.write:
        counts = write_down_dedao_wiki_artifacts(result, args.artifact_dir)

    summary = {
        "mode": "write" if args.write else "dry_run",
        "diff": result.diff,
        "counts": counts,
        "skipped_private": result.skipped_private,
        "gene_knowledge_audit": gene_knowledge_audit,
    }
    if args.json_summary:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if quality_issue_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
