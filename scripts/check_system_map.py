#!/usr/bin/env python3
"""Validate all generated System Map artifacts through one blocking gate."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SYSTEM_MAP = ROOT / "docs" / "_generated" / "system-map.json"
SYSTEM_MAP_SCHEMA = ROOT / "docs" / "_generated" / "system-map.schema.json"
AGENT_CONTEXT = ROOT / "docs" / "_generated" / "system-map-agent-context.md"

sys.path.insert(0, str(SCRIPTS))
from check_doc_drift import main as check_doc_drift  # noqa: E402
from dump_system_map import build_map, check_artifacts  # noqa: E402
from system_map_context import SystemMapContextError, render_agent_context  # noqa: E402
from system_map_contract import SystemMapContractError, validate_system_map  # noqa: E402


MOBILE_CHECK = [sys.executable, "mobile/scripts/dump_nav_graph.py", "--check"]


def validate_artifact() -> None:
    """Validate the committed artifact against JSON Schema and graph semantics."""
    schema = json.loads(SYSTEM_MAP_SCHEMA.read_text(encoding="utf-8"))
    artifact = json.loads(SYSTEM_MAP.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(artifact)
    validate_system_map(artifact)
    committed_context = AGENT_CONTEXT.read_text(encoding="utf-8")
    if committed_context != render_agent_context(artifact):
        raise SystemMapContextError(
            "system-map-agent-context.md differs from the canonical System Map"
        )


def _build_and_check_canonical() -> dict | None:
    print("→ system-map")
    try:
        fresh_map = build_map()
        matches, message = check_artifacts(fresh_map)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print("❌ system-map failed with exit code 1", file=sys.stderr)
        return None
    if not matches:
        print(
            f"❌ {message}：跑 python3.12 scripts/dump_system_map.py",
            file=sys.stderr,
        )
        print("❌ system-map failed with exit code 1", file=sys.stderr)
        return None
    print(f"✅ {SYSTEM_MAP.relative_to(ROOT)} 与代码一致")
    print(f"✅ {AGENT_CONTEXT.relative_to(ROOT)} 与 canonical graph 一致")
    return fresh_map


def _replay_gate(
    name: str,
    stdout: str,
    stderr: str,
    returncode: int,
) -> None:
    print(f"→ {name}")
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    if returncode != 0:
        print(f"❌ {name} failed with exit code {returncode}", file=sys.stderr)


def _communicate_mobile(process) -> tuple[str, str, int]:
    try:
        stdout, stderr = process.communicate()
        return stdout, stderr, process.returncode
    except Exception:  # noqa: BLE001
        failure = traceback.format_exc()
        try:
            process.kill()
        except Exception:  # noqa: BLE001
            failure += traceback.format_exc()
        try:
            stdout, stderr = process.communicate()
        except Exception:  # noqa: BLE001
            failure += traceback.format_exc()
            try:
                process.wait()
            except Exception:  # noqa: BLE001
                failure += traceback.format_exc()
            return "", failure, 1
        return stdout, failure + stderr, 1


def main() -> int:
    try:
        validate_artifact()
    except (
        OSError,
        json.JSONDecodeError,
        SchemaError,
        ValidationError,
        SystemMapContractError,
        SystemMapContextError,
    ) as exc:
        print(f"❌ System Map contract validation failed: {exc}", file=sys.stderr)
        return 1

    fresh_map = _build_and_check_canonical()
    if fresh_map is None:
        return 1

    mobile_process = None
    mobile_stdout = ""
    mobile_stderr = ""
    mobile_returncode = 1
    try:
        mobile_process = subprocess.Popen(
            MOBILE_CHECK,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:  # noqa: BLE001
        mobile_stderr = traceback.format_exc()

    doc_stdout_buffer = io.StringIO()
    doc_stderr_buffer = io.StringIO()
    try:
        try:
            with redirect_stdout(doc_stdout_buffer), redirect_stderr(doc_stderr_buffer):
                doc_returncode = check_doc_drift(fresh_map=fresh_map)
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=doc_stderr_buffer)
            doc_returncode = 1
    finally:
        if mobile_process is not None:
            mobile_stdout, mobile_stderr, mobile_returncode = _communicate_mobile(
                mobile_process
            )

    _replay_gate(
        "mobile-nav",
        mobile_stdout,
        mobile_stderr,
        mobile_returncode,
    )
    _replay_gate(
        "doc-drift",
        doc_stdout_buffer.getvalue(),
        doc_stderr_buffer.getvalue(),
        doc_returncode,
    )
    for returncode in (mobile_returncode, doc_returncode):
        if returncode != 0:
            return returncode
    print("✅ System Map verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
