#!/usr/bin/env python3
"""Detect repeated user friction patterns and propose harness improvements.

This is deliberately advisory: it finds evidence that a rule/skill may need to
be updated, but it never edits memory or skills. Promotion still goes through
the reviewed gate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


TEXT_EXTENSIONS = {".md", ".txt", ".jsonl", ".log"}

PATTERNS = [
    {
        "id": "repeated_continue",
        "label": "用户反复要求继续推进",
        "regex": re.compile(r"继续|继续实现|继续推进|不要再停下来"),
        "min_count": 3,
        "suggested_rule": "长任务中用户反复说继续时,默认沿最新规划继续执行并阶段性提交,不要反复停下询问。",
    },
    {
        "id": "source_of_truth_correction",
        "label": "用户纠正了规划/上下文真源",
        "regex": re.compile(r"不是.*规划|之前的 context|知识库相关|基于知识库|按照.*规划"),
        "min_count": 1,
        "suggested_rule": "当用户纠正真源时,先定位指定规划/Dossier/系统图,后续执行以该文件为准。",
    },
    {
        "id": "completion_uncertainty",
        "label": "用户反复追问是否完成",
        "regex": re.compile(r"全部.*完成|还有.*没|有没有.*搞定|完整实现了吗|是否全部"),
        "min_count": 1,
        "suggested_rule": "每轮实现后维护规划级完成矩阵,明确已完成/剩余/验证证据,减少用户反复追问。",
    },
]


def _iter_files(inputs: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(
                path for path in item.rglob("*")
                if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS
            )
    return sorted(set(files))


def _evidence_for(path: Path, pattern: re.Pattern[str], limit: int = 5) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return evidence
    for line_no, line in enumerate(lines, start=1):
        if pattern.search(line):
            evidence.append({"file": str(path), "line": line_no, "text": line[:240]})
            if len(evidence) >= limit:
                break
    return evidence


def scan(inputs: Iterable[Path], *, min_count_override: int | None = None) -> dict[str, Any]:
    files = _iter_files(inputs)
    suggestions: list[dict[str, Any]] = []
    for spec in PATTERNS:
        regex = spec["regex"]
        evidence: list[dict[str, Any]] = []
        for path in files:
            evidence.extend(_evidence_for(path, regex, limit=5 - len(evidence)))
            if len(evidence) >= 5:
                break
        threshold = int(min_count_override or spec["min_count"])
        if len(evidence) >= threshold:
            suggestions.append({
                "id": spec["id"],
                "label": spec["label"],
                "count": len(evidence),
                "threshold": threshold,
                "suggested_rule": spec["suggested_rule"],
                "evidence": evidence,
            })
    return {
        "status": "suggestions_found" if suggestions else "clean",
        "scanned_files": len(files),
        "suggestions": suggestions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan text artifacts for repeated user friction patterns.")
    parser.add_argument("--input", action="append", required=True, help="File or directory to scan. Repeatable.")
    parser.add_argument("--min-count", type=int, help="Override every pattern threshold.")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    payload = scan([Path(item) for item in args.input], min_count_override=args.min_count)
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"harness friction scan: {payload['status']} ({payload['scanned_files']} files)")
        for item in payload["suggestions"]:
            print(f"- {item['id']}: {item['label']} count={item['count']} threshold={item['threshold']}")
            print(f"  suggested_rule: {item['suggested_rule']}")
            for ev in item["evidence"]:
                print(f"  evidence: {ev['file']}:{ev['line']} {ev['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
