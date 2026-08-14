#!/usr/bin/env python3
"""Prepare one transaction-private EAS CLI from the committed integrity lock."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    print(
        "locked EAS CLI error: direct EAS CLI preparation is frozen; "
        "use the external trusted Gate",
        file=sys.stderr,
    )
    raise SystemExit(78)

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Mapping, Sequence


EAS_CLI_VERSION = "21.8.0"
TYPESCRIPT_VERSION = "5.9.3"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
NPM_BINARY = Path("/usr/local/bin/npm")
NODE_BINARY = Path("/usr/local/bin/node")
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
TOOL_PREFIX = "reva-locked-eas-cli."


class LockedEasCliError(RuntimeError):
    """The integrity-locked EAS CLI could not be prepared safely."""


Runner = Callable[..., subprocess.CompletedProcess[object]]


def _read_regular(path: Path, *, maximum: int) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            raise LockedEasCliError(f"unsafe locked EAS input: {path}")
        raw = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
        if (
            len(raw) != metadata.st_size
            or len(raw) > maximum
            or os.read(descriptor, 1)
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
            )
        ):
            raise LockedEasCliError(f"locked EAS input changed: {path}")
        current = os.stat(path, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise LockedEasCliError(f"locked EAS input changed: {path}")
        return raw
    finally:
        os.close(descriptor)


def _strict_json(raw: bytes, *, label: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate field: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=unique,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid constant: {value}")
            ),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise LockedEasCliError(f"invalid {label}") from error
    if not isinstance(payload, dict):
        raise LockedEasCliError(f"invalid {label}")
    return payload


def _validate_manifests(manifest: bytes, lock: bytes) -> str:
    manifest_json = _strict_json(manifest, label="EAS package manifest")
    lock_json = _strict_json(lock, label="EAS package lock")
    dependencies = manifest_json.get("dependencies")
    packages = lock_json.get("packages")
    root_package = packages.get("") if isinstance(packages, dict) else None
    root_dependencies = (
        root_package.get("dependencies") if isinstance(root_package, dict) else None
    )
    if (
        dependencies
        != {"eas-cli": EAS_CLI_VERSION, "typescript": TYPESCRIPT_VERSION}
        or not isinstance(root_dependencies, dict)
        or root_dependencies
        != {"eas-cli": EAS_CLI_VERSION, "typescript": TYPESCRIPT_VERSION}
        or lock_json.get("lockfileVersion") != 3
    ):
        raise LockedEasCliError("EAS CLI manifest/lock is not exact 21.8.0")
    return hashlib.sha256(manifest + b"\0" + lock).hexdigest()


def _safe_environment(workspace: Path, source: Mapping[str, str]) -> dict[str, str]:
    environment = {
        "PATH": SAFE_PATH,
        "HOME": str(workspace / "home"),
        "TMPDIR": str(workspace / "tmp"),
        # npm 11 rejects using the same path for user and global configs.
        # Both files live in the private transaction workspace and are
        # created empty/readonly before npm starts.
        "NPM_CONFIG_USERCONFIG": str(workspace / "npm-user.conf"),
        "NPM_CONFIG_GLOBALCONFIG": str(workspace / "npm-global.conf"),
        "NPM_CONFIG_AUDIT": "false",
        "NPM_CONFIG_FUND": "false",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        "NPM_CONFIG_IGNORE_SCRIPTS": "true",
        "NPM_CONFIG_CACHE": str(workspace / "npm-cache"),
        "LANG": "C",
        "LC_ALL": "C",
        "CI": "1",
    }
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy"):
        value = source.get(name)
        if value:
            environment[name] = value
    return environment


def _validate_installed_tool(workspace: Path, *, lock_digest: str) -> Path:
    package_path = workspace / "tool/node_modules/eas-cli/package.json"
    package = _strict_json(
        _read_regular(package_path, maximum=MAX_MANIFEST_BYTES),
        label="installed EAS package manifest",
    )
    if package.get("version") != EAS_CLI_VERSION:
        raise LockedEasCliError("installed EAS CLI version is not exact")
    typescript = _strict_json(
        _read_regular(
            workspace / "tool/node_modules/typescript/package.json",
            maximum=MAX_MANIFEST_BYTES,
        ),
        label="installed TypeScript package manifest",
    )
    if typescript.get("version") != TYPESCRIPT_VERSION:
        raise LockedEasCliError("installed TypeScript version is not exact")
    eas_link = workspace / "tool/node_modules/.bin/eas"
    try:
        link_metadata = os.lstat(eas_link)
        resolved = eas_link.resolve(strict=True)
        tool_root = (workspace / "tool").resolve(strict=True)
        resolved.relative_to(tool_root)
        resolved_metadata = os.stat(resolved, follow_symlinks=False)
    except (OSError, ValueError) as error:
        raise LockedEasCliError("installed EAS CLI binary is unsafe") from error
    if (
        not stat.S_ISLNK(link_metadata.st_mode)
        or not stat.S_ISREG(resolved_metadata.st_mode)
        or resolved_metadata.st_uid != os.geteuid()
        or resolved_metadata.st_nlink != 1
        or not os.access(resolved, os.X_OK)
    ):
        raise LockedEasCliError("installed EAS CLI binary is unsafe")
    receipt = workspace / "tool.receipt"
    receipt.write_text(
        f"schema=1\neas_cli={EAS_CLI_VERSION}\nlock_digest={lock_digest}\n",
        encoding="ascii",
    )
    receipt.chmod(0o600)
    return eas_link


def prepare_locked_eas_cli(
    repo_root: Path,
    *,
    runner: Runner = subprocess.run,
    source_env: Mapping[str, str] | None = None,
) -> tuple[Path, Path]:
    """Install exact EAS bytes once and return ``(workspace, executable)``."""

    repo_root = repo_root.resolve(strict=True)
    source_dir = repo_root / "scripts/eas-cli-tool"
    manifest = _read_regular(source_dir / "package.json", maximum=MAX_MANIFEST_BYTES)
    lock = _read_regular(source_dir / "package-lock.json", maximum=MAX_MANIFEST_BYTES)
    lock_digest = _validate_manifests(manifest, lock)
    workspace = Path(tempfile.mkdtemp(prefix=TOOL_PREFIX)).resolve(strict=True)
    workspace.chmod(0o700)
    try:
        for name in ("tool", "home", "tmp", "npm-cache"):
            (workspace / name).mkdir(mode=0o700)
        for name in ("npm-user.conf", "npm-global.conf"):
            config = workspace / name
            config.write_bytes(b"")
            config.chmod(0o400)
        for name, payload in (("package.json", manifest), ("package-lock.json", lock)):
            target = workspace / "tool" / name
            target.write_bytes(payload)
            target.chmod(0o600)
        if not NPM_BINARY.is_file() or not os.access(NPM_BINARY, os.X_OK):
            raise LockedEasCliError("fixed npm binary is unavailable")
        completed = runner(
            [
                str(NPM_BINARY),
                "ci",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
            ],
            cwd=workspace / "tool",
            env=_safe_environment(workspace, source_env or os.environ),
            stdin=subprocess.DEVNULL,
            # npm output is neither release evidence nor safe to retain in
            # memory: a compromised registry/proxy could otherwise emit an
            # unbounded stream before the timeout.  The exact exit code is the
            # only install result consumed by the coordinator.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            raise LockedEasCliError(
                f"integrity-locked EAS install failed ({completed.returncode})"
            )
        executable = _validate_installed_tool(workspace, lock_digest=lock_digest)
        return workspace, executable
    except BaseException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise


def cleanup_locked_eas_cli(workspace: Path) -> None:
    resolved = workspace.resolve(strict=True)
    if (
        resolved.parent != Path(tempfile.gettempdir()).resolve(strict=True)
        or not resolved.name.startswith(TOOL_PREFIX)
        or not resolved.is_dir()
    ):
        raise LockedEasCliError("refusing unsafe EAS tool cleanup target")
    shutil.rmtree(resolved)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--repo-root", type=Path, required=True)
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("workspace", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "prepare":
        workspace, executable = prepare_locked_eas_cli(arguments.repo_root)
        print(f"{workspace}\t{executable}")
    else:
        cleanup_locked_eas_cli(arguments.workspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
