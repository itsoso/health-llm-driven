#!/usr/bin/env python3
"""Prove the active interpreter exactly matches a compiled requirements lock."""

from __future__ import annotations

import argparse
import csv
import io
import importlib
import importlib.metadata
import os
import pwd
import secrets
import stat
import re
import sys
from pathlib import Path


EXACT_REQUIREMENT = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^;\\\s]+)\s*\\?"
)

# Packages that must not survive a lock transition even when pip reuses the
# existing production venv. ChromaDB has no patched release for
# CVE-2026-45830/45831/45833, and its legacy runtime is disabled.
FORBIDDEN_INSTALLED_PACKAGES = ("chromadb", "chroma-hnswlib")


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def verify_lock(
    lock_path: Path,
    *,
    sanitize_forbidden_packages: bool = False,
    runtime_user: str | None = None,
) -> list[str]:
    if runtime_user is not None:
        identity_error = _runtime_identity_error(runtime_user)
        if identity_error:
            return [identity_error]
    expected: list[tuple[str, str]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(
        lock_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line or raw_line[0].isspace() or raw_line.startswith(("#", "--")):
            continue
        match = EXACT_REQUIREMENT.fullmatch(raw_line)
        if match is None:
            errors.append(
                f"line {line_number}: unsupported lock requirement: {raw_line}"
            )
            continue
        expected.append((match.group("name"), match.group("version")))

    if not expected:
        errors.append("lock contains no exact requirements")
    for name, version in expected:
        if (
            sanitize_forbidden_packages
            and _normalize_package_name(name) in FORBIDDEN_INSTALLED_PACKAGES
        ):
            continue
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"{name}: missing; expected={version}")
            continue
        if installed != version:
            errors.append(f"{name}: installed={installed}; expected={version}")
    for name in FORBIDDEN_INSTALLED_PACKAGES:
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        errors.append(f"{name}: forbidden installed package; installed={installed}")
    if runtime_user is not None and not errors:
        readable: dict[str, set[Path]] = {}
        for name, _version in expected:
            if (
                sanitize_forbidden_packages
                and _normalize_package_name(name) in FORBIDDEN_INSTALLED_PACKAGES
            ):
                continue
            paths, error = _read_distribution_record(name, _version)
            if error:
                errors.append(error)
            else:
                readable[_normalize_package_name(name)] = paths
        if not errors:
            error = _verify_pyjwt(readable.get("pyjwt", set()))
            if error:
                errors.append(error)
    return errors


def _runtime_identity_error(runtime_user: str) -> str | None:
    try:
        expected_uid = pwd.getpwnam(runtime_user).pw_uid
    except KeyError:
        return "runtime identity: requested account does not exist"
    actual = (os.getuid(), os.geteuid())
    if hasattr(os, "getresuid"):
        actual += os.getresuid()
    if expected_uid == 0 or any(uid != expected_uid or uid == 0 for uid in actual):
        return "runtime identity: process must run as the requested non-root account"
    return None


def _read_distribution_record(name: str, version: str) -> tuple[set[Path], str | None]:
    """Open installed wheel members as data under this interpreter's prefix.

    Real opens, rather than mode-bit guesses or root's os.access, prove that the
    service identity can traverse parents and read code. RECORD paths may use
    ../../../bin for console scripts, but cannot authorize outside-prefix reads.
    """
    paths: set[Path] = set()
    try:
        distribution = importlib.metadata.distribution(name)
        if distribution.version != version or _normalize_package_name(
            distribution.metadata["Name"] or ""
        ) != _normalize_package_name(name):
            return paths, f"{name}: installed RECORD distribution identity mismatch"
        raw_record = distribution.read_text("RECORD")
        if not raw_record:
            return paths, f"{name}: missing or empty installed RECORD"
        # Distribution.files can filter out missing members. Parse the original
        # RECORD itself so deleted code cannot disappear from this verification.
        rows = list(csv.reader(io.StringIO(raw_record), strict=True))
        if not rows or any(len(row) != 3 or not row[0] for row in rows):
            return paths, f"{name}: malformed installed RECORD"
        prefix = Path(sys.prefix).resolve(strict=True)
        for entry, _hash, _size in rows:
            path = Path(distribution.locate_file(entry)).resolve(strict=True)
            if not path.is_relative_to(prefix):
                return paths, f"{name}: RECORD member escapes interpreter prefix"
            # Open only regular package data; never a device, FIFO, or socket.
            before = path.stat()
            if not stat.S_ISREG(before.st_mode):
                return paths, f"{name}: RECORD member is not a regular file"
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino, opened.st_mode) != (
                    before.st_dev,
                    before.st_ino,
                    before.st_mode,
                ):
                    return paths, f"{name}: RECORD member changed before read"
                while stream.read(1024 * 1024):
                    pass
            paths.add(path)
    except (
        OSError,
        ValueError,
        csv.Error,
        importlib.metadata.PackageNotFoundError,
    ) as exc:
        return paths, f"{name}: RECORD missing or unreadable ({type(exc).__name__})"
    return paths, None


def _verify_pyjwt(recorded: set[Path]) -> str | None:
    """Check installed provenance and real crypto behavior without application data."""
    if not recorded:
        return "PyJWT: required locked distribution is absent"
    try:
        jwt = importlib.import_module("jwt")
        origin = getattr(jwt, "__file__", None)
        if not origin or Path(origin).resolve(strict=True) not in recorded:
            return "PyJWT: imported jwt does not originate from its locked RECORD"
        for function in (getattr(jwt, "encode", None), getattr(jwt, "decode", None)):
            if not callable(function) or not getattr(
                function, "__module__", ""
            ).startswith("jwt."):
                return "PyJWT: imported jwt lacks its signing and verification implementation"
        for name, module in tuple(sys.modules.items()):
            if name == "jwt" or name.startswith("jwt."):
                origin = getattr(module, "__file__", None)
                if not origin or Path(origin).resolve(strict=True) not in recorded:
                    return "PyJWT: imported implementation escapes its locked RECORD"
        secret = secrets.token_bytes(32)
        payload = {"sub": "runtime-readability-probe"}
        token = jwt.encode(payload, secret, algorithm="HS256")
        if jwt.decode(token, secret, algorithms=["HS256"]) != payload:
            return "PyJWT: synthetic HS256 roundtrip failed"
        try:
            jwt.decode(token, secrets.token_bytes(32), algorithms=["HS256"])
        except jwt.InvalidSignatureError:
            pass  # Expected rejection is part of the probe, not a fallback.
        else:
            return "PyJWT: invalid signature was accepted"
        try:
            jwt.decode("invalid-synthetic-token", secret, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            pass  # Malformed tokens must not be accepted as authenticated data.
        else:
            return "PyJWT: invalid token was accepted"
    except Exception as exc:
        # Vendor exception messages can contain tokens; expose only the type.
        return f"PyJWT: runtime verification failed ({type(exc).__name__})"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize-forbidden-packages", action="store_true")
    parser.add_argument("--runtime-user")
    parser.add_argument("lock_path", type=Path)
    args = parser.parse_args()
    lock_path = args.lock_path
    try:
        errors = verify_lock(
            lock_path,
            sanitize_forbidden_packages=args.sanitize_forbidden_packages,
            runtime_user=args.runtime_user,
        )
    except OSError as exc:
        print(f"locked requirements verification failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print(
            "locked requirements verification failed:\n" + "\n".join(errors),
            file=sys.stderr,
        )
        return 1
    package_count = sum(
        1
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line and not line[0].isspace() and not line.startswith(("#", "--"))
    )
    print(f"LOCKED_REQUIREMENTS_OK packages={package_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
