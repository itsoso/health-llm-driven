#!/usr/bin/env python3
"""Fail-closed receipts for narrowly reusable production release steps.

The CLI always requires root-owned proof state.  Unit tests exercise the same
implementation with a caller-supplied expected uid; production callers do not
have a flag that can weaken the root-ownership requirement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar


DEFAULT_RECEIPT_ROOT = Path("/var/cache/health-app/release-proofs")
SCHEMA_VERSION = 1
_MAX_RECEIPT_BYTES = 16 * 1024
_STEP_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_MODES = frozenset({"off", "shadow", "on"})
UNAVAILABLE_OUTPUT_DIGEST = "0" * 64


class ReceiptSecurityError(RuntimeError):
    """The receipt path is not private, regular, and owned as required."""


class ProfileUnavailable(RuntimeError):
    """A step profile cannot prove its current inputs or postconditions."""


@dataclass(frozen=True)
class ProofMaterial:
    input_digest: str
    toolchain_digest: str
    output_digest: str
    postcondition: str


@dataclass(frozen=True)
class Evaluation:
    should_skip: bool
    candidate_hit: bool
    reason: str


def _validate_step(step: str) -> None:
    if not _STEP_RE.fullmatch(step):
        raise ValueError(f"invalid proof step: {step!r}")


def _validate_material(material: ProofMaterial) -> None:
    for field_name in ("input_digest", "toolchain_digest", "output_digest"):
        value = getattr(material, field_name)
        if not _DIGEST_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a lowercase sha256 digest")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,80}", material.postcondition):
        raise ValueError("postcondition contract is invalid")


def _directory_state(
    receipt_root: Path,
    *,
    create: bool,
    expected_uid: int,
) -> tuple[int, str | None]:
    try:
        info = receipt_root.lstat()
    except FileNotFoundError:
        if not create:
            return -1, "missing-receipt"
        try:
            receipt_root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = receipt_root.lstat()

    if not stat.S_ISDIR(info.st_mode) or receipt_root.is_symlink():
        return -1, "unsafe-receipt-directory"
    if info.st_uid != expected_uid:
        return -1, "unsafe-receipt-directory-owner"
    if stat.S_IMODE(info.st_mode) != 0o700:
        return -1, "unsafe-receipt-directory-permissions"

    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(receipt_root, flags)
    except OSError:
        return -1, "unsafe-receipt-directory"
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != expected_uid
        or stat.S_IMODE(opened.st_mode) != 0o700
    ):
        os.close(directory_fd)
        return -1, "unsafe-receipt-directory"
    return directory_fd, None


def _read_receipt(
    receipt_root: Path,
    step: str,
    *,
    expected_uid: int,
) -> tuple[dict[str, object] | None, str | None]:
    directory_fd, error = _directory_state(
        receipt_root,
        create=False,
        expected_uid=expected_uid,
    )
    if error:
        return None, error
    name = f"{step}.json"
    try:
        try:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None, "missing-receipt"
        if not stat.S_ISREG(info.st_mode):
            return None, "unsafe-receipt-type"
        if info.st_uid != expected_uid:
            return None, "unsafe-receipt-owner"
        if stat.S_IMODE(info.st_mode) != 0o600:
            return None, "unsafe-receipt-permissions"
        if info.st_size <= 0 or info.st_size > _MAX_RECEIPT_BYTES:
            return None, "corrupt-receipt"

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            receipt_fd = os.open(name, flags, dir_fd=directory_fd)
        except OSError:
            return None, "unsafe-receipt-type"
        try:
            opened = os.fstat(receipt_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != expected_uid
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_size <= 0
                or opened.st_size > _MAX_RECEIPT_BYTES
            ):
                return None, "unsafe-receipt-type"
            raw = b""
            while len(raw) <= _MAX_RECEIPT_BYTES:
                chunk = os.read(
                    receipt_fd, min(4096, _MAX_RECEIPT_BYTES + 1 - len(raw))
                )
                if not chunk:
                    break
                raw += chunk
            if len(raw) > _MAX_RECEIPT_BYTES:
                return None, "corrupt-receipt"
        finally:
            os.close(receipt_fd)
    finally:
        os.close(directory_fd)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "corrupt-receipt"
    if not isinstance(payload, dict):
        return None, "corrupt-receipt"
    required = {
        "schema_version",
        "step",
        "input_digest",
        "toolchain_digest",
        "output_digest",
        "postcondition",
        "recorded_at",
    }
    if set(payload) != required:
        return None, "corrupt-receipt"
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None, "corrupt-receipt"
    if payload.get("step") != step:
        return None, "corrupt-receipt"
    for field_name in ("input_digest", "toolchain_digest", "output_digest"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
            return None, "corrupt-receipt"
    postcondition = payload.get("postcondition")
    recorded_at = payload.get("recorded_at")
    if (
        not isinstance(postcondition, str)
        or not re.fullmatch(r"[A-Za-z0-9._:-]{1,80}", postcondition)
        or not isinstance(recorded_at, str)
        or not recorded_at
    ):
        return None, "corrupt-receipt"
    return payload, None


def evaluate_receipt(
    receipt_root: Path,
    step: str,
    material: ProofMaterial,
    *,
    mode: str,
    expected_uid: int = 0,
) -> Evaluation:
    """Evaluate one receipt; every ambiguity becomes a non-reusable miss."""

    _validate_step(step)
    _validate_material(material)
    if mode not in _MODES:
        raise ValueError(f"invalid proof mode: {mode!r}")
    if mode == "off":
        return Evaluation(False, False, "disabled")

    payload, error = _read_receipt(
        Path(receipt_root),
        step,
        expected_uid=expected_uid,
    )
    if error:
        return Evaluation(False, False, error)
    assert payload is not None
    comparisons = (
        ("input_digest", "input-drift"),
        ("toolchain_digest", "toolchain-drift"),
        ("output_digest", "output-drift"),
        ("postcondition", "postcondition-drift"),
    )
    for field_name, reason in comparisons:
        if payload[field_name] != getattr(material, field_name):
            return Evaluation(False, False, reason)
    if mode == "shadow":
        return Evaluation(False, True, "shadow-hit")
    return Evaluation(True, True, "hit")


def record_receipt(
    receipt_root: Path,
    step: str,
    material: ProofMaterial,
    *,
    expected_uid: int = 0,
) -> Path:
    """Atomically replace a private receipt after caller postconditions pass."""

    _validate_step(step)
    _validate_material(material)
    receipt_root = Path(receipt_root)
    directory_fd, error = _directory_state(
        receipt_root,
        create=True,
        expected_uid=expected_uid,
    )
    if error:
        raise ReceiptSecurityError(error)
    name = f"{step}.json"
    temporary = f".{step}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "step": step,
        **asdict(material),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    temporary_fd = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        temporary_fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        os.fchmod(temporary_fd, 0o600)
        view = memoryview(encoded)
        while view:
            written = os.write(temporary_fd, view)
            if written <= 0:
                raise OSError("short receipt write")
            view = view[written:]
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = -1
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except BaseException:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(directory_fd)
    return receipt_root / name


def invalidate_receipt(
    receipt_root: Path,
    step: str,
    *,
    expected_uid: int = 0,
) -> None:
    """Remove prior success evidence before a step is rerun."""

    _validate_step(step)
    directory_fd, error = _directory_state(
        Path(receipt_root),
        create=False,
        expected_uid=expected_uid,
    )
    if error == "missing-receipt":
        return
    if error:
        raise ReceiptSecurityError(error)
    try:
        try:
            os.unlink(f"{step}.json", dir_fd=directory_fd)
            os.fsync(directory_fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(directory_fd)


T = TypeVar("T")


def execute_and_record(
    *,
    receipt_root: Path,
    step: str,
    mode: str,
    current_material: Callable[[], ProofMaterial],
    action: Callable[[], T],
    postcondition: Callable[[], object],
    expected_uid: int = 0,
) -> T | str:
    """Execute a step with the required invalidate/run/prove/record ordering."""

    material_before = current_material()
    evaluation = evaluate_receipt(
        receipt_root,
        step,
        material_before,
        mode=mode,
        expected_uid=expected_uid,
    )
    if evaluation.should_skip:
        return "reused"
    if mode != "off":
        invalidate_receipt(receipt_root, step, expected_uid=expected_uid)
    result = action()
    postcondition()
    if mode != "off":
        record_receipt(
            receipt_root,
            step,
            current_material(),
            expected_uid=expected_uid,
        )
    return result


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_path_info(
    path: Path,
    *,
    expected_uid: int,
    kind: str,
    allow_symlink: bool = False,
) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ProfileUnavailable(f"missing {kind}: {path.name}") from exc
    if path.is_symlink() and not allow_symlink:
        raise ProfileUnavailable(f"symlink {kind} is not reusable: {path.name}")
    if kind.endswith("directory"):
        if not stat.S_ISDIR(info.st_mode):
            raise ProfileUnavailable(f"{kind} is not a directory: {path.name}")
    elif not (
        stat.S_ISREG(info.st_mode) or (allow_symlink and stat.S_ISLNK(info.st_mode))
    ):
        raise ProfileUnavailable(f"{kind} is not a regular file: {path.name}")
    if info.st_uid != expected_uid:
        raise ProfileUnavailable(f"{kind} owner is not release owner: {path.name}")
    # POSIX symlink mode bits are commonly reported as 0777 and are ignored by
    # the kernel. Ownership plus the resolved executable identity are the
    # meaningful proof fields for an allowed venv interpreter symlink.
    if not stat.S_ISLNK(info.st_mode) and stat.S_IMODE(info.st_mode) & 0o022:
        raise ProfileUnavailable(f"{kind} is group/world writable: {path.name}")
    return info


def _file_fingerprint(
    path: Path,
    *,
    expected_uid: int,
    label: str,
) -> dict[str, object]:
    info = _safe_path_info(
        path,
        expected_uid=expected_uid,
        kind="input file",
    )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return {
        "label": label,
        "sha256": digest.hexdigest(),
        "size": info.st_size,
        "mode": stat.S_IMODE(info.st_mode),
    }


def _tree_fingerprint(
    root: Path,
    *,
    expected_uid: int,
    label: str,
    excluded_top_level: frozenset[str] = frozenset(),
) -> dict[str, object]:
    _safe_path_info(
        root,
        expected_uid=expected_uid,
        kind="output directory",
    )
    entries: list[dict[str, object]] = []
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        if current == root:
            directory_names[:] = [
                name for name in directory_names if name not in excluded_top_level
            ]
        directory_names.sort()
        file_names.sort()
        for directory_name in list(directory_names):
            directory = current / directory_name
            info = _safe_path_info(
                directory,
                expected_uid=expected_uid,
                kind="output directory",
            )
            entries.append(
                {
                    "path": directory.relative_to(root).as_posix() + "/",
                    "mode": stat.S_IMODE(info.st_mode),
                }
            )
        for file_name in file_names:
            file_path = current / file_name
            entries.append(
                _file_fingerprint(
                    file_path,
                    expected_uid=expected_uid,
                    label=file_path.relative_to(root).as_posix(),
                )
            )
    return {"label": label, "entries": entries}


def _run_checked(
    command: list[str],
    *,
    purpose: str,
    cwd: Path | None = None,
) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProfileUnavailable(f"{purpose} failed (exit={result.returncode})")
    return result.stdout.strip()


def _path_identity(path: Path, *, expected_uid: int, kind: str) -> dict[str, object]:
    info = _safe_path_info(
        path,
        expected_uid=expected_uid,
        kind=kind,
        allow_symlink=True,
    )
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProfileUnavailable(
            f"{kind} target cannot be resolved: {path.name}"
        ) from exc
    target_info = _safe_path_info(
        resolved,
        expected_uid=expected_uid,
        kind=f"{kind} target",
    )
    return {
        "path": str(path),
        "realpath": str(resolved),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "type": "symlink" if stat.S_ISLNK(info.st_mode) else "file",
        "target_uid": target_info.st_uid,
        "target_gid": target_info.st_gid,
        "target_mode": stat.S_IMODE(target_info.st_mode),
    }


def collect_python_dependencies_material(
    workspace: Path,
    *,
    expected_uid: int = 0,
    python_executable: Path | None = None,
    allow_missing_output: bool = False,
) -> ProofMaterial:
    workspace = Path(workspace)
    lock = workspace / "requirements.lock"
    lock_verifier = workspace / "scripts" / "verify_locked_requirements.py"
    venv = workspace / "venv"
    executable = Path(python_executable or (venv / "bin" / "python"))
    input_digest = _digest_json(
        {
            "requirements_lock": _file_fingerprint(
                lock,
                expected_uid=expected_uid,
                label="requirements.lock",
            ),
            "locked_requirements_verifier": _file_fingerprint(
                lock_verifier,
                expected_uid=expected_uid,
                label="verify_locked_requirements.py",
            ),
        }
    )
    _safe_path_info(
        venv,
        expected_uid=expected_uid,
        kind="venv directory",
    )
    executable_identity = _path_identity(
        executable,
        expected_uid=expected_uid,
        kind="venv python",
    )
    python_version = _run_checked(
        [str(executable), "--version"], purpose="python version"
    )
    pip_version = _run_checked(
        [str(executable), "-m", "pip", "--version"],
        purpose="pip version",
    )
    toolchain_digest = _digest_json(
        {
            "python": python_version,
            "pip": pip_version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "executable": executable_identity,
        }
    )
    locked_verify = subprocess.run(
        [
            str(executable),
            "scripts/verify_locked_requirements.py",
            "requirements.lock",
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    if locked_verify.returncode != 0:
        if not allow_missing_output:
            raise ProfileUnavailable(
                "locked requirements verifier failed "
                f"(exit={locked_verify.returncode})"
            )
        return ProofMaterial(
            input_digest=input_digest,
            toolchain_digest=toolchain_digest,
            output_digest=UNAVAILABLE_OUTPUT_DIGEST,
            postcondition="locked-requirements-pip-check-venv-owner-v1",
        )
    pip_check = subprocess.run(
        [str(executable), "-m", "pip", "check"],
        text=True,
        capture_output=True,
        check=False,
    )
    if pip_check.returncode != 0:
        if not allow_missing_output:
            raise ProfileUnavailable(f"pip check failed (exit={pip_check.returncode})")
        output_digest = UNAVAILABLE_OUTPUT_DIGEST
    else:
        distribution_code = (
            "import importlib.metadata as m,json;"
            "rows=sorted((d.metadata.get('Name','').lower().replace('_','-'),d.version) "
            "for d in m.distributions());"
            "print(json.dumps(rows,separators=(',',':')))"
        )
        try:
            raw_distributions = _run_checked(
                [str(executable), "-c", distribution_code],
                purpose="installed distribution inventory",
            )
            distributions = json.loads(raw_distributions)
            if not isinstance(distributions, list):
                raise ValueError("distribution inventory must be a list")
        except (ProfileUnavailable, json.JSONDecodeError, ValueError) as exc:
            if not allow_missing_output:
                raise ProfileUnavailable(
                    "installed distribution inventory failed"
                ) from exc
            output_digest = UNAVAILABLE_OUTPUT_DIGEST
        else:
            venv_info = venv.lstat()
            output_digest = _digest_json(
                {
                    "distributions": distributions,
                    "venv": {
                        "uid": venv_info.st_uid,
                        "gid": venv_info.st_gid,
                        "mode": stat.S_IMODE(venv_info.st_mode),
                    },
                    "pip_check": "passed",
                }
            )
    return ProofMaterial(
        input_digest=input_digest,
        toolchain_digest=toolchain_digest,
        output_digest=output_digest,
        postcondition="locked-requirements-pip-check-venv-owner-v1",
    )


def _frontend_toolchain(
    *,
    expected_uid: int,
) -> tuple[str, str, str, str, dict[str, object], dict[str, object]]:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise ProfileUnavailable("node/npm toolchain is unavailable")
    node_identity = _path_identity(
        Path(node),
        expected_uid=expected_uid,
        kind="node executable",
    )
    npm_identity = _path_identity(
        Path(npm),
        expected_uid=expected_uid,
        kind="npm executable",
    )
    node_version = _run_checked([node, "--version"], purpose="node version")
    npm_version = _run_checked([npm, "--version"], purpose="npm version")
    return node, npm, node_version, npm_version, node_identity, npm_identity


def collect_frontend_dependencies_material(
    workspace: Path,
    *,
    expected_uid: int = 0,
    allow_missing_output: bool = False,
) -> ProofMaterial:
    workspace = Path(workspace)
    package = workspace / "package.json"
    lock = workspace / "package-lock.json"
    node, npm, node_version, npm_version, node_identity, npm_identity = (
        _frontend_toolchain(expected_uid=expected_uid)
    )
    input_digest = _digest_json(
        [
            _file_fingerprint(
                package,
                expected_uid=expected_uid,
                label="package.json",
            ),
            _file_fingerprint(
                lock,
                expected_uid=expected_uid,
                label="package-lock.json",
            ),
        ]
    )
    toolchain_digest = _digest_json(
        {
            "node": node_version,
            "npm": npm_version,
            "node_identity": node_identity,
            "npm_identity": npm_identity,
            "platform": platform.platform(),
            "machine": platform.machine(),
        }
    )
    node_modules = workspace / "node_modules"
    installed_lock = node_modules / ".package-lock.json"
    try:
        node_modules_info = _safe_path_info(
            node_modules,
            expected_uid=expected_uid,
            kind="node_modules directory",
        )
        installed_lock_proof = _file_fingerprint(
            installed_lock,
            expected_uid=expected_uid,
            label="node_modules/.package-lock.json",
        )
        npm_tree_raw = _run_checked(
            [npm, "ls", "--all", "--json"],
            purpose="npm dependency inventory",
            cwd=workspace,
        )
        npm_tree = json.loads(npm_tree_raw)
        if not isinstance(npm_tree, dict):
            raise ValueError("npm dependency inventory must be an object")
    except (
        ProfileUnavailable,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        if not allow_missing_output:
            raise ProfileUnavailable("npm dependency proof failed") from exc
        output_digest = UNAVAILABLE_OUTPUT_DIGEST
    else:
        output_digest = _digest_json(
            {
                "installed_lock": installed_lock_proof,
                "npm_tree": npm_tree,
                "node_modules": {
                    "uid": node_modules_info.st_uid,
                    "gid": node_modules_info.st_gid,
                    "mode": stat.S_IMODE(node_modules_info.st_mode),
                },
            }
        )
    return ProofMaterial(
        input_digest=input_digest,
        toolchain_digest=toolchain_digest,
        output_digest=output_digest,
        postcondition="npm-ls-node-modules-owner-v1",
    )


_FRONTEND_BUILD_ENV_KEYS = (
    "BACKEND_URL",
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_SITE_BASE_URL",
    "NODE_ENV",
)
_FRONTEND_BUILD_ENV_FILES = (
    ".env",
    ".env.local",
    ".env.production",
    ".env.production.local",
)


def collect_frontend_build_material(
    workspace: Path,
    *,
    expected_uid: int = 0,
    allow_missing_output: bool = False,
) -> ProofMaterial:
    workspace = Path(workspace)
    dependency = collect_frontend_dependencies_material(
        workspace,
        expected_uid=expected_uid,
        allow_missing_output=allow_missing_output,
    )
    repo = workspace.parent
    frontend_tree = _run_checked(
        ["git", "-C", str(repo), "rev-parse", "HEAD:frontend"],
        purpose="frontend Git tree",
    )
    if not re.fullmatch(r"[0-9a-f]{40,64}", frontend_tree):
        raise ProfileUnavailable("frontend Git tree returned an invalid object id")
    build_environment = {
        key: {"present": key in os.environ, "value": os.environ.get(key, "")}
        for key in _FRONTEND_BUILD_ENV_KEYS
    }
    build_environment_files = []
    for name in _FRONTEND_BUILD_ENV_FILES:
        path = workspace / name
        if path.exists() or path.is_symlink():
            build_environment_files.append(
                _file_fingerprint(
                    path,
                    expected_uid=expected_uid,
                    label=name,
                )
            )
        else:
            build_environment_files.append({"label": name, "missing": True})
    input_digest = _digest_json(
        {
            "frontend_tree": frontend_tree,
            "dependency_input": dependency.input_digest,
            "dependency_output": dependency.output_digest,
            "build_environment": build_environment,
            "build_environment_files": build_environment_files,
        }
    )
    output = workspace / ".next"
    try:
        output_proof = _tree_fingerprint(
            output,
            expected_uid=expected_uid,
            label=".next",
            excluded_top_level=frozenset({"cache"}),
        )
    except ProfileUnavailable:
        if not allow_missing_output:
            raise
        output_digest = UNAVAILABLE_OUTPUT_DIGEST
    else:
        output_digest = _digest_json(output_proof)
    return ProofMaterial(
        input_digest=input_digest,
        toolchain_digest=dependency.toolchain_digest,
        output_digest=output_digest,
        postcondition="frontend-pm2-http-v1",
    )


PROFILES = {
    "python-dependencies": collect_python_dependencies_material,
    "frontend-dependencies": collect_frontend_dependencies_material,
    "frontend-build": collect_frontend_build_material,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate or record root-owned production release-step proofs "
            f"({', '.join(sorted(PROFILES))})"
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_common(command: argparse.ArgumentParser, *, mode: bool) -> None:
        if mode:
            command.add_argument("--mode", choices=sorted(_MODES), required=True)
        command.add_argument("--profile", choices=sorted(PROFILES), required=True)
        command.add_argument("--root", type=Path, default=DEFAULT_RECEIPT_ROOT)

    check = commands.add_parser("check", help="evaluate a current proof")
    add_common(check, mode=True)
    check.add_argument("--workspace", type=Path, required=True)

    record = commands.add_parser(
        "record",
        help="record a proof after the caller's postcondition succeeds",
    )
    add_common(record, mode=True)
    record.add_argument("--workspace", type=Path, required=True)

    invalidate = commands.add_parser(
        "invalidate",
        help="remove prior evidence before rerunning a step",
    )
    add_common(invalidate, mode=False)
    return parser


def _require_root() -> None:
    if os.geteuid() != 0:
        raise ReceiptSecurityError("production release-step proof access requires root")


def _collect_profile(
    profile: str,
    workspace: Path,
    *,
    allow_missing_output: bool,
) -> ProofMaterial:
    profiler = PROFILES[profile]
    if not callable(profiler):
        raise ProfileUnavailable(f"profile is not callable: {profile}")
    return profiler(
        workspace,
        expected_uid=0,
        allow_missing_output=allow_missing_output,
    )


def _print_evaluation(mode: str, step: str, result: Evaluation) -> None:
    print(
        json.dumps(
            {
                "candidate_hit": result.candidate_hit,
                "mode": mode,
                "reason": result.reason,
                "skip": result.should_skip,
                "step": step,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def cli(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "check" and args.mode == "off":
        result = Evaluation(False, False, "disabled")
        _print_evaluation(args.mode, args.profile, result)
        return 3
    if args.command == "record" and args.mode == "off":
        print(
            json.dumps(
                {"mode": "off", "recorded": False, "step": args.profile},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

    _require_root()
    if args.command == "invalidate":
        invalidate_receipt(args.root, args.profile, expected_uid=0)
        print(
            json.dumps(
                {"invalidated": True, "step": args.profile},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

    if args.command == "check":
        material = _collect_profile(
            args.profile,
            args.workspace,
            allow_missing_output=True,
        )
        result = evaluate_receipt(
            args.root,
            args.profile,
            material,
            mode=args.mode,
            expected_uid=0,
        )
        _print_evaluation(args.mode, args.profile, result)
        return 0 if result.should_skip else 3

    material = _collect_profile(
        args.profile,
        args.workspace,
        allow_missing_output=False,
    )
    receipt = record_receipt(
        args.root,
        args.profile,
        material,
        expected_uid=0,
    )
    print(
        json.dumps(
            {
                "mode": args.mode,
                "recorded": True,
                "receipt": str(receipt),
                "step": args.profile,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def main() -> int:
    try:
        return cli()
    except (ProfileUnavailable, ReceiptSecurityError, ValueError) as exc:
        print(f"release-step proof error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
