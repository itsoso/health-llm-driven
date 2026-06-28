#!/usr/bin/env python3
"""Selective MEMORY.md priming for Reva harness sessions.

The goal is to avoid dumping the entire local memory registry into context.
This small deterministic search returns ranked line-level matches that an
agent can paste into a Dossier or status note with line numbers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MEMORY_ROOT = Path.home() / ".codex" / "memories"


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _normalize_keywords(values: list[str]) -> list[str]:
    keywords: list[str] = []
    for value in values:
        for part in value.split(","):
            keyword = part.strip().lower()
            if keyword:
                keywords.append(keyword)
    return keywords


def _score_line(line: str, keywords: list[str], require_all: bool) -> int:
    haystack = line.lower()
    hits = [keyword for keyword in keywords if keyword in haystack]
    if require_all and len(hits) != len(set(keywords)):
        return 0
    return len(hits)


def collect_matches(
    memory_root: Path,
    keywords: list[str],
    *,
    limit: int,
    require_all: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    registry = memory_root / "MEMORY.md"
    if not registry.exists():
        return [], "memory_registry_missing"

    matches: list[dict[str, Any]] = []
    for index, line in enumerate(registry.read_text(encoding="utf-8").splitlines(), start=1):
        score = _score_line(line, keywords, require_all=require_all)
        if score <= 0:
            continue
        matches.append({
            "path": "MEMORY.md",
            "line": index,
            "score": score,
            "text": line.strip(),
        })

    matches.sort(key=lambda item: (-int(item["score"]), int(item["line"])))
    return matches[:limit], None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Selectively prime local Codex memory by keyword")
    parser.add_argument("--memory-root", default=str(DEFAULT_MEMORY_ROOT))
    parser.add_argument("--keywords", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--require-all", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    keywords = _normalize_keywords(args.keywords)
    if not keywords:
        _write_json({"ok": False, "error": "keywords_required", "matches": []})
        return 2

    matches, error = collect_matches(
        Path(args.memory_root),
        keywords,
        limit=max(1, int(args.limit)),
        require_all=bool(args.require_all),
    )
    if error:
        _write_json({"ok": False, "error": error, "matches": []})
        return 2

    _write_json({
        "ok": True,
        "memory_root": str(Path(args.memory_root)),
        "keywords": keywords,
        "require_all": bool(args.require_all),
        "matches": matches,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
