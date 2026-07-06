#!/usr/bin/env python3
"""Dry-run a dedao-kbase verified evidence pull manifest for health.

This command only validates the remote contract and prints candidate counts.
It does not write System KB artifacts or database rows.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-url", default=os.environ.get("DEDAO_KBASE_EVIDENCE_MANIFEST_URL"))
    parser.add_argument("--auth-token", default=os.environ.get("DEDAO_KBASE_AUTH_TOKEN"))
    parser.add_argument("--json-summary", action="store_true", help="Print machine-readable JSON summary.")
    args = parser.parse_args()

    if not args.manifest_url:
        parser.error("--manifest-url or DEDAO_KBASE_EVIDENCE_MANIFEST_URL is required")

    from app.services.dedao_kbase_evidence_pull import dry_run_dedao_kbase_evidence_pull

    report = dry_run_dedao_kbase_evidence_pull(
        manifest_url=args.manifest_url,
        auth_token=args.auth_token,
    )
    if args.json_summary:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(f"status: {report['status']}")
    print(f"pack_id: {report['pack_id']}")
    print(f"source_fingerprint: {report['source_fingerprint']}")
    print(f"total_records: {report['total_records']}")
    print(f"accepted_candidates: {report['accepted_candidates']}")
    print(f"review_required_records: {report['review_required_records']}")
    print(f"blocked_records: {report['blocked_records']}")
    print("would_write: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
