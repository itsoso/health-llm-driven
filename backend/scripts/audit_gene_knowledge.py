#!/usr/bin/env python3
"""Audit down-dedao gene_knowledge.json for actionable genetics coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_GENE_KNOWLEDGE = "~/work/personal/down-dedao/artifacts/gene_knowledge.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gene-knowledge",
        default=DEFAULT_GENE_KNOWLEDGE,
        help="Path to compiled down-dedao artifacts/gene_knowledge.json.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument("--output", help="Optional output path. Defaults to stdout.")
    parser.add_argument("--fail-on-quality-gates", action="store_true")
    args = parser.parse_args()

    from app.services.gene_knowledge_audit import (
        audit_gene_knowledge,
        format_gene_knowledge_audit_markdown,
    )

    source = Path(args.gene_knowledge).expanduser()
    payload = json.loads(source.read_text(encoding="utf-8"))
    report = audit_gene_knowledge(payload)
    rendered = (
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.format == "json"
        else format_gene_knowledge_audit_markdown(report)
    )

    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"wrote gene knowledge audit: {output}")
    else:
        print(rendered)

    if args.fail_on_quality_gates:
        gates = report.get("quality_gates") or {}
        issue_count = sum(len(value or []) for value in gates.values())
        return 1 if issue_count else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
