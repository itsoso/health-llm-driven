#!/usr/bin/env python3
"""Pull dedao-kbase Health Authority Pack and print a dry-run report."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.system_kb.dedao_authority_import import (  # noqa: E402
    dry_run_import_dedao_authority_pack_from_kbase,
)


def _print_text(payload: dict) -> None:
    import_report = payload["import_report"]
    print(f"Dedao authority pull: {payload['status']}")
    if payload.get("error"):
        print(f"error: {payload['error']}")
    print(f"source: {payload.get('source_url') or '-'}")
    print(f"http_status: {payload.get('http_status') or '-'}")
    print(f"total: {import_report['total']}")
    print(f"accepted_for_review: {len(import_report['accepted_for_review'])}")
    print(f"blocked: {len(import_report['blocked'])}")
    print(f"duplicates: {len(import_report['duplicates'])}")
    print(f"invalid: {len(import_report['invalid'])}")
    print(f"missing_source_refs: {len(import_report['missing_source_refs'])}")
    print(f"would_write: {import_report['would_write']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("DEDAO_KBASE_BASE_URL", ""))
    parser.add_argument("--token", default=os.getenv("DEDAO_KBASE_TOKEN", ""))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    report = dry_run_import_dedao_authority_pack_from_kbase(
        args.base_url,
        args.token,
        limit=args.limit,
        timeout=args.timeout,
    )
    payload = report.to_dict()
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
