#!/usr/bin/env python3
"""Scan down-dedao for health-relevant system KB source candidates."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SOURCE_ROOT = "/Users/liqiuhua/work/personal/down-dedao"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    from app.services.system_knowledge_pipeline import scan_health_sources

    sources = scan_health_sources(args.source_root)[: args.limit]
    print(json.dumps([asdict(source) for source in sources], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
