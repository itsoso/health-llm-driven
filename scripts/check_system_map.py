#!/usr/bin/env python3
"""Validate all generated System Map artifacts through one blocking gate."""

from __future__ import annotations

import io
import json
import os
import signal
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

try:
    from scripts.system_map_imports import load_repo_module
except ModuleNotFoundError as error:
    if error.name not in {"scripts", "scripts.system_map_imports"}:
        raise
    from system_map_imports import load_repo_module

_check_doc_drift_module = load_repo_module("check_doc_drift", SCRIPTS)
_dump_system_map_module = load_repo_module("dump_system_map", SCRIPTS)
_system_map_context_module = load_repo_module("system_map_context", SCRIPTS)
_system_map_contract_module = load_repo_module("system_map_contract", SCRIPTS)

check_doc_drift = _check_doc_drift_module.main
build_map = _dump_system_map_module.build_map
check_artifacts = _dump_system_map_module.check_artifacts
SystemMapContextError = _system_map_context_module.SystemMapContextError
render_agent_context = _system_map_context_module.render_agent_context
SystemMapContractError = _system_map_contract_module.SystemMapContractError
validate_system_map = _system_map_contract_module.validate_system_map


MOBILE_CHECK = [sys.executable, "mobile/scripts/dump_nav_graph.py", "--check"]
MOBILE_REAP_TIMEOUT_SECONDS = 1.0


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
    except BaseException as error:
        failure = _format_exception("mobile communicate failed", error)
        if isinstance(error, Exception):
            primary, failures = _cleanup_mobile_process(
                process,
                failure_reports=[failure],
            )
            if primary is not None:
                raise primary
            return "", "\n".join(failures), 1
        _cleanup_mobile_process(process, primary=error)
        raise


def _format_exception(label: str, error: BaseException) -> str:
    detail = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    return f"{label}:\n{detail}"


def _record_cleanup_failure(
    primary: BaseException | None,
    failures: list[str],
    label: str,
    error: BaseException,
) -> BaseException | None:
    report = _format_exception(label, error)
    if primary is None and not isinstance(error, Exception):
        primary = error
        for failure in failures:
            primary.add_note(failure)
        failures.clear()
    elif primary is None:
        failures.append(report)
    else:
        primary.add_note(report)
    return primary


def _attempt_cleanup(
    label: str,
    action,
    primary: BaseException | None,
    failures: list[str],
) -> tuple[BaseException | None, bool]:
    try:
        action()
    except BaseException as error:  # cleanup must continue after cancellation
        primary = _record_cleanup_failure(
            primary,
            failures,
            label,
            error,
        )
        if isinstance(error, Exception):
            return primary, False
        try:
            action()
        except BaseException as retry_error:
            return _record_cleanup_failure(
                primary,
                failures,
                f"{label} after interruption",
                retry_error,
            ), False
        return primary, True
    return primary, True


def _cleanup_mobile_process(
    process,
    *,
    primary: BaseException | None = None,
    failure_reports: list[str] | None = None,
) -> tuple[BaseException | None, list[str]]:
    failures = list(failure_reports or ())
    pid = getattr(process, "pid", None)
    killed = False
    if os.name == "posix" and isinstance(pid, int):
        def kill_group() -> None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        primary, killed = _attempt_cleanup(
            "mobile process-group kill failed",
            kill_group,
            primary,
            failures,
        )
    if not killed:
        primary, _ = _attempt_cleanup(
            "mobile direct kill failed",
            process.kill,
            primary,
            failures,
        )

    for stream_name in ("stdout", "stderr"):
        stream = getattr(process, stream_name, None)
        close = getattr(stream, "close", None)
        if close is None:
            continue
        primary, _ = _attempt_cleanup(
            f"mobile {stream_name} close failed",
            close,
            primary,
            failures,
        )

    wait = getattr(process, "wait", None)
    if wait is not None:
        primary, _ = _attempt_cleanup(
            "mobile bounded wait failed",
            lambda: wait(timeout=MOBILE_REAP_TIMEOUT_SECONDS),
            primary,
            failures,
        )
    return primary, failures


def _kill_and_reap_cancelled_mobile(
    process,
    cancellation: BaseException,
) -> None:
    _cleanup_mobile_process(process, primary=cancellation)


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
            start_new_session=True,
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
