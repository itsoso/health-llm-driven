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

_scripts_path = str(SCRIPTS)
_caller_sys_path = sys.path.copy()
if not sys.path or sys.path[0] != _scripts_path:
    sys.path.insert(0, _scripts_path)
try:
    from check_doc_drift import main as check_doc_drift  # noqa: E402
    from dump_system_map import build_map, check_artifacts  # noqa: E402
    from system_map_context import (  # noqa: E402
        SystemMapContextError,
        render_agent_context,
    )
    from system_map_contract import (  # noqa: E402
        SystemMapContractError,
        validate_system_map,
    )
finally:
    sys.path[:] = _caller_sys_path


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
    print("→ system-map", flush=True)
    try:
        fresh_map = build_map()
        matches, message = check_artifacts(fresh_map)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print(
            "❌ system-map failed with exit code 1",
            file=sys.stderr,
            flush=True,
        )
        return None
    if not matches:
        print(
            f"❌ {message}：跑 python3.12 scripts/dump_system_map.py",
            file=sys.stderr,
            flush=True,
        )
        print(
            "❌ system-map failed with exit code 1",
            file=sys.stderr,
            flush=True,
        )
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
    print(f"→ {name}", flush=True)
    sys.stdout.write(stdout)
    sys.stdout.flush()
    sys.stderr.write(stderr)
    sys.stderr.flush()
    if returncode != 0:
        print(
            f"❌ {name} failed with exit code {returncode}",
            file=sys.stderr,
            flush=True,
        )


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
    except BaseException as cancellation:
        _kill_and_reap_cancelled_mobile(process, cancellation)
        raise


def _kill_and_reap_cancelled_mobile(
    process,
    cancellation: BaseException,
) -> None:
    try:
        process.kill()
    except BaseException:
        cancellation.add_note(
            f"mobile cancellation cleanup failed:\n{traceback.format_exc()}"
        )
        return
    try:
        process.communicate()
    except BaseException:
        cancellation.add_note(
            f"mobile cancellation cleanup failed:\n{traceback.format_exc()}"
        )
        try:
            process.wait()
        except BaseException:
            cancellation.add_note(
                f"mobile cancellation cleanup failed:\n{traceback.format_exc()}"
            )


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
        print(
            f"❌ System Map contract validation failed: {exc}",
            file=sys.stderr,
            flush=True,
        )
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
    except BaseException as cancellation:
        if mobile_process is not None:
            _kill_and_reap_cancelled_mobile(mobile_process, cancellation)
            mobile_process = None
        raise
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
