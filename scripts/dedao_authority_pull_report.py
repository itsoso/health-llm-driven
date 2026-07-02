#!/usr/bin/env python3
"""Pull dedao-kbase Health Authority Pack and print a dry-run report."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
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
    evaluate_dedao_authority_pull_gate,
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


def _print_gate_text(payload: dict) -> None:
    counts = payload["counts"]
    pull = payload["pull"]
    print(f"Dedao authority gate: {payload['status']}")
    print(f"reasons: {', '.join(payload['reasons']) or '-'}")
    print(f"source: {pull.get('source_url') or '-'}")
    print(f"http_status: {pull.get('http_status') or '-'}")
    print(f"fetch_status: {pull.get('status') or '-'}")
    print(f"source_unchanged: {payload.get('source_unchanged')}")
    if pull.get("error"):
        print(f"error: {pull['error']}")
    print(f"total: {counts['total']}")
    print(f"accepted_for_review: {counts['accepted_for_review']}")
    print(f"blocked: {counts['blocked']}")
    print(f"duplicates: {counts['duplicates']}")
    print(f"invalid: {counts['invalid']}")
    print(f"missing_source_refs: {counts['missing_source_refs']}")
    print(f"would_write: {payload['would_write']}")


def _exit_code_for_gate(status: str, *, fail_on_warn: bool) -> int:
    if status == "fail":
        return 1
    if status == "warn" and fail_on_warn:
        return 1
    return 0


def _write_output_text(text: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_previous_source_sha256(artifact_path: str | Path) -> str:
    if not artifact_path:
        return ""
    try:
        payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    pull = payload.get("pull")
    if not isinstance(pull, dict):
        return ""
    return str(pull.get("source_sha256") or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("DEDAO_KBASE_BASE_URL", ""))
    parser.add_argument("--token", default=os.getenv("DEDAO_KBASE_TOKEN", ""))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument("--gate", action="store_true", help="Evaluate pass/warn/fail gate status.")
    parser.add_argument(
        "--redacted-json",
        action="store_true",
        help="Print the gate artifact without raw record payloads.",
    )
    parser.add_argument(
        "--redacted-output",
        default="",
        help="Write the redacted gate JSON artifact to this path.",
    )
    parser.add_argument(
        "--previous-artifact",
        default="",
        help="Read a previous redacted gate artifact and mark source_unchanged when hashes match.",
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Return non-zero for warn gate status as well as fail.",
    )
    args = parser.parse_args(argv)

    report = dry_run_import_dedao_authority_pack_from_kbase(
        args.base_url,
        args.token,
        limit=args.limit,
        timeout=args.timeout,
    )
    if args.gate or args.redacted_json or args.redacted_output:
        gate = evaluate_dedao_authority_pull_gate(report)
        payload = gate.to_redacted_dict(
            generated_at=_utc_timestamp(),
            previous_source_sha256=_read_previous_source_sha256(args.previous_artifact),
        )
        redacted_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.redacted_output:
            _write_output_text(redacted_json, args.redacted_output)
        if args.as_json or args.redacted_json:
            print(redacted_json, end="")
        else:
            _print_gate_text(payload)
            if args.redacted_output:
                print(f"redacted_output: {args.redacted_output}")
        return _exit_code_for_gate(gate.status, fail_on_warn=args.fail_on_warn)

    payload = report.to_dict()
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
