#!/usr/bin/python3
"""Transactional migration of mutable runtime state out of the checkout.

The production CLI deliberately has no path overrides.  Tests may inject a
``Layout`` by importing this module, but every CLI invocation uses the fixed
production layout returned by :func:`production_layout`.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import grp
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence


UNITS = (
    "health-backend.service",
    "celery-worker.service",
    "celery-beat.service",
)
BOOT_GATE_UNITS = ("health-backend.socket", *UNITS)
CANDIDATE_NAMES = {
    "health-backend.service": "health-backend-runtime-state.conf",
    "celery-worker.service": "celery-worker-runtime-state.conf",
    "celery-beat.service": "celery-beat-runtime-state.conf",
}
RUNTIME_ITEMS = {
    "gene_knowledge.json": "file",
    "knowledge_chromadb": "dir",
    "knowledge_base": "dir",
}
SHELF_SUFFIXES = ("", ".db", ".dat", ".dir", ".bak")
VALID_PHASES = {
    "ARMING",
    "PREPARED",
    "INSTALLED",
    "COMMITTING",
    "COMMITTED",
    "RESTORED",
    "RESTORE_FINALIZED",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
STAGE_RE = re.compile(r"^/tmp/health-app-backup-preflight-[1-9][0-9]*-[1-9][0-9]*$")
SCHEDULE_RE = re.compile(r"(?:^|\s)--schedule(?:=|\s+)([^\s;}\]]+)")
SUPPORTED_ENABLEMENT_STATES = {"enabled", "disabled", "static"}


class TransactionError(RuntimeError):
    """A fail-closed release transaction error."""


class Systemd(Protocol):
    def show(self, unit: str, prop: str) -> str: ...

    def daemon_reload(self) -> None: ...

    def is_enabled(self, unit: str) -> str: ...

    def disable(self, unit: str) -> None: ...

    def enable(self, unit: str) -> None: ...


class SubprocessSystemd:
    """Systemd adapter with fixed argv and no shell interpolation."""

    def show(self, unit: str, prop: str) -> str:
        result = subprocess.run(
            [
                "/usr/bin/systemctl",
                "show",
                unit,
                f"--property={prop}",
                "--value",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def daemon_reload(self) -> None:
        subprocess.run(
            ["/usr/bin/systemctl", "daemon-reload"],
            check=True,
        )

    def is_enabled(self, unit: str) -> str:
        result = subprocess.run(
            ["/usr/bin/systemctl", "is-enabled", unit],
            check=False,
            capture_output=True,
            text=True,
        )
        state = result.stdout.strip()
        if result.returncode not in {0, 1} or not state:
            raise subprocess.CalledProcessError(
                result.returncode,
                ["/usr/bin/systemctl", "is-enabled", unit],
                output=result.stdout,
                stderr=result.stderr,
            )
        return state

    def disable(self, unit: str) -> None:
        subprocess.run(
            ["/usr/bin/systemctl", "disable", unit],
            check=True,
        )

    def enable(self, unit: str) -> None:
        subprocess.run(
            ["/usr/bin/systemctl", "enable", unit],
            check=True,
        )


@dataclass(frozen=True)
class CandidatePaths:
    paths: Mapping[str, Path]

    def __getitem__(self, unit: str) -> Path:
        return self.paths[unit]


@dataclass(frozen=True)
class Layout:
    repo_root: Path
    runtime_root: Path
    skills_cache_root: Path
    beat_state_dir: Path
    dedao_legacy_root: Path
    dedao_container: Path
    systemd_root: Path
    release_stage: Path
    transaction_root: Path
    candidate_dropins: CandidatePaths
    health_uid: int
    health_gid: int
    root_uid: int = 0
    root_gid: int = 0
    require_root: bool = True

    @property
    def backend_data(self) -> Path:
        return self.repo_root / "backend/data"

    @property
    def legacy_uploads(self) -> Path:
        return self.repo_root / "backend/uploads"

    @property
    def uploads_root(self) -> Path:
        return self.runtime_root.parent / "uploads"

    @property
    def legacy_shelf_base(self) -> Path:
        return self.backend_data / "celerybeat-schedule"

    @property
    def current_shelf_base(self) -> Path:
        return self.beat_state_dir / "celerybeat-schedule"

    @property
    def dedao_workspace(self) -> Path:
        return self.dedao_container / "workspace"

    @property
    def live_dropins(self) -> Mapping[str, Path]:
        return {
            unit: self.systemd_root / f"{unit}.d" / "90-runtime-state.conf"
            for unit in UNITS
        }

    @property
    def base_units(self) -> Mapping[str, Path]:
        return {unit: self.systemd_root / unit for unit in BOOT_GATE_UNITS}


@dataclass(frozen=True)
class CliArgs:
    command: str
    first_sha: str | None
    second_sha: str | None
    lock_dir: Path
    token: str


def production_layout(script_dir: Path) -> Layout:
    """Return the only layout accepted by the production CLI."""

    if not STAGE_RE.fullmatch(str(script_dir)):
        raise TransactionError("helper is outside the fixed release stage")
    try:
        health_uid = pwd.getpwnam("health-app").pw_uid
        health_gid = grp.getgrnam("health-app").gr_gid
    except KeyError as exc:
        raise TransactionError("health-app user/group is missing") from exc
    return Layout(
        repo_root=Path("/opt/health-app"),
        runtime_root=Path("/var/lib/health-app/runtime"),
        skills_cache_root=Path("/var/cache/health-app/skills-hub"),
        beat_state_dir=Path("/var/lib/health-app/celery-beat"),
        dedao_legacy_root=Path("/var/lib/health-app/dedao-kbase-review"),
        dedao_container=Path("/var/lib/health-app/dedao-kbase"),
        systemd_root=Path("/etc/systemd/system"),
        release_stage=script_dir,
        transaction_root=Path(
            "/var/lib/health-app/release-state/runtime-state-transaction"
        ),
        candidate_dropins=CandidatePaths(
            {unit: script_dir / name for unit, name in CANDIDATE_NAMES.items()}
        ),
        health_uid=health_uid,
        health_gid=health_gid,
    )


def _validate_sha(value: str, label: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise TransactionError(f"{label} must be a 40-character lowercase SHA")


def _validate_lock_inputs(lock_dir: Path, token: str) -> None:
    value = str(lock_dir)
    if (
        not lock_dir.is_absolute()
        or value == "/"
        or "/../" in value
        or value.endswith("/..")
        or "/./" in value
        or value.endswith("/.")
        or not re.fullmatch(r"/[A-Za-z0-9._/-]+", value)
    ):
        raise TransactionError("release lock path is unsafe")
    if not TOKEN_RE.fullmatch(token):
        raise TransactionError("release lock token is unsafe")


def parse_cli(argv: Sequence[str]) -> CliArgs:
    if not argv:
        raise TransactionError(
            "command must be preflight, prepare, install, restore, "
            "commit, release-gate, finalize, or status"
        )
    command = argv[0]
    if command in {"preflight", "prepare", "install"}:
        if len(argv) != 5:
            raise TransactionError(
                f"{command} requires OLD_SHA CANDIDATE_SHA LOCK_DIR TOKEN"
            )
        old_sha, candidate_sha, lock_value, token = argv[1:]
        _validate_sha(old_sha, "old SHA")
        _validate_sha(candidate_sha, "candidate SHA")
        lock_dir = Path(lock_value)
        _validate_lock_inputs(lock_dir, token)
        return CliArgs(command, old_sha, candidate_sha, lock_dir, token)
    if command in {"restore", "commit", "release-gate", "finalize"}:
        if len(argv) != 4:
            raise TransactionError(f"{command} requires SHA LOCK_DIR TOKEN")
        release_sha, lock_value, token = argv[1:]
        _validate_sha(release_sha, f"{command} SHA")
        lock_dir = Path(lock_value)
        _validate_lock_inputs(lock_dir, token)
        return CliArgs(command, release_sha, None, lock_dir, token)
    if command == "status":
        if len(argv) != 3:
            raise TransactionError("status requires LOCK_DIR TOKEN")
        lock_value, token = argv[1:]
        lock_dir = Path(lock_value)
        _validate_lock_inputs(lock_dir, token)
        return CliArgs(command, None, None, lock_dir, token)
    raise TransactionError(f"unsupported command: {command}")


def _expected_candidate(unit: str) -> bytes:
    if unit == "health-backend.service":
        return (
            "[Service]\n"
            "ReadWritePaths=\n"
            "ReadWritePaths=/var/lib/health-app/uploads "
            "/var/cache/health-app/skills-hub "
            "/var/lib/health-app/runtime "
            "/var/lib/health-app/dedao-kbase\n"
        ).encode()
    if unit == "celery-worker.service":
        return (
            "[Service]\n"
            "ReadWritePaths=\n"
            "ReadWritePaths=/var/lib/health-app/uploads "
            "/var/lib/health-app/dedao-kbase\n"
        ).encode()
    if unit == "celery-beat.service":
        return (
            "[Service]\n"
            "StateDirectory=health-app/celery-beat\n"
            "StateDirectoryMode=0700\n"
            "ReadWritePaths=\n"
            "ReadWritePaths=/var/lib/health-app/celery-beat\n"
            "ExecStart=\n"
            "ExecStart=/opt/health-app/backend/venv/bin/celery "
            "-A app.celery_app:celery_app beat --loglevel=info "
            "--schedule=/var/lib/health-app/celery-beat/"
            "celerybeat-schedule\n"
        ).encode()
    raise TransactionError(f"unknown unit: {unit}")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _metadata(path: Path) -> dict[str, int]:
    current = path.lstat()
    return {
        "uid": current.st_uid,
        "gid": current.st_gid,
        "mode": stat.S_IMODE(current.st_mode),
    }


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        current = os.fstat(descriptor)
        if not stat.S_ISREG(current.st_mode):
            raise TransactionError(f"not a regular file: {path}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _transaction_id(old_sha: str, candidate_sha: str) -> str:
    return hashlib.sha256(f"{old_sha}:{candidate_sha}".encode()).hexdigest()[:32]


class ReleaseTransaction:
    """A durable unit/state transaction shared by deploy and rollback."""

    def __init__(
        self,
        layout: Layout,
        systemd: Systemd,
        *,
        event_sink: Callable[[str], None] | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.layout = layout
        self.systemd = systemd
        self._event_sink = event_sink or (lambda _event: None)
        self._fault_hook = fault_hook or (lambda _point: None)
        self._active_transaction_id: str | None = None

    def _emit(self, event: str) -> None:
        self._event_sink(event)

    def _fault(self, point: str) -> None:
        self._fault_hook(point)

    def _activate_transaction(self, old_sha: str, candidate_sha: str) -> None:
        self._active_transaction_id = _transaction_id(
            old_sha,
            candidate_sha,
        )

    def _temporary_path(self, destination: Path) -> Path:
        if self._active_transaction_id is None:
            raise TransactionError("transaction identity is not active")
        return destination.parent / (
            f".{destination.name}.runtime-state-{self._active_transaction_id}.tmp"
        )

    def _assert_release_lock(self, lock_dir: Path, token: str) -> None:
        _validate_lock_inputs(lock_dir, token)
        token_path = lock_dir / "token"
        self._validate_regular(token_path, allow_writable=False)
        if token_path.read_text(encoding="utf-8").rstrip("\n") != token:
            raise TransactionError("release lock ownership changed")

    def _validate_regular(
        self,
        path: Path,
        *,
        allow_writable: bool,
    ) -> os.stat_result:
        try:
            current = path.lstat()
        except FileNotFoundError as exc:
            raise TransactionError(f"required file is missing: {path}") from exc
        if stat.S_ISLNK(current.st_mode):
            raise TransactionError(f"symlink is not allowed: {path}")
        if not stat.S_ISREG(current.st_mode):
            raise TransactionError(f"not a regular file: {path}")
        if current.st_nlink != 1:
            raise TransactionError(f"hard link is not allowed: {path}")
        if not allow_writable and current.st_mode & 0o022:
            raise TransactionError(f"group/world writable file: {path}")
        return current

    def _validate_directory(
        self,
        path: Path,
        *,
        required: bool,
    ) -> os.stat_result | None:
        try:
            current = path.lstat()
        except FileNotFoundError:
            if required:
                raise TransactionError(f"required directory is missing: {path}")
            return None
        if stat.S_ISLNK(current.st_mode):
            raise TransactionError(f"symlink is not allowed: {path}")
        if not stat.S_ISDIR(current.st_mode):
            raise TransactionError(f"not a directory: {path}")
        if current.st_mode & 0o022:
            raise TransactionError(f"group/world writable directory: {path}")
        return current

    def _validate_tree(
        self,
        path: Path,
        *,
        expected_kind: str | None = None,
    ) -> None:
        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(current.st_mode):
            raise TransactionError(f"symlink is not allowed: {path}")
        if stat.S_ISREG(current.st_mode):
            if expected_kind == "dir":
                raise TransactionError(f"expected directory: {path}")
            if current.st_nlink != 1:
                raise TransactionError(f"hard link is not allowed: {path}")
            if current.st_mode & 0o022:
                raise TransactionError(f"group/world writable file: {path}")
            return
        if not stat.S_ISDIR(current.st_mode):
            raise TransactionError(f"special file is not allowed: {path}")
        if expected_kind == "file":
            raise TransactionError(f"expected regular file: {path}")
        if current.st_mode & 0o022:
            raise TransactionError(f"group/world writable directory: {path}")
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            self._validate_tree(child)

    def _validate_runtime_root(self) -> None:
        root_state = self._validate_directory(
            self.layout.runtime_root,
            required=False,
        )
        if root_state is None:
            return
        unknown = {
            child.name
            for child in self.layout.runtime_root.iterdir()
            if child.name not in RUNTIME_ITEMS
        }
        if unknown:
            raise TransactionError(
                "unknown runtime entry: " + ", ".join(sorted(unknown))
            )
        for name, kind in RUNTIME_ITEMS.items():
            self._validate_tree(
                self.layout.runtime_root / name,
                expected_kind=kind,
            )

    def _validate_shelf_family(self, base: Path, *, dedicated: bool) -> None:
        parent = base.parent
        if not parent.exists():
            return
        self._validate_directory(parent, required=True)
        allowed = {f"{base.name}{suffix}" for suffix in SHELF_SUFFIXES}
        for child in parent.iterdir():
            if dedicated and child.name not in allowed:
                raise TransactionError(f"unknown beat state entry: {child}")
            if child.name.startswith(base.name) and child.name not in allowed:
                raise TransactionError(f"unknown shelf suffix: {child}")
        for suffix in SHELF_SUFFIXES:
            target = Path(f"{base}{suffix}")
            if target.exists() or target.is_symlink():
                self._validate_regular(target, allow_writable=False)

    def _schedule_path(self, exec_start: str) -> Path:
        matches = SCHEDULE_RE.findall(exec_start)
        if len(matches) != 1:
            raise TransactionError(
                "celery-beat must have exactly one effective schedule path"
            )
        schedule = Path(matches[0])
        if schedule not in {
            self.layout.legacy_shelf_base,
            self.layout.current_shelf_base,
        }:
            raise TransactionError(f"unexpected celery-beat schedule path: {schedule}")
        return schedule

    def _old_effective(self) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        for unit in UNITS:
            fragment = self.systemd.show(unit, "FragmentPath")
            if fragment != str(self.layout.base_units[unit]):
                raise TransactionError(
                    f"unexpected FragmentPath for {unit}: {fragment}"
                )
            result[unit] = {
                "FragmentPath": fragment,
                "DropInPaths": self.systemd.show(unit, "DropInPaths"),
                "ExecStart": self.systemd.show(unit, "ExecStart"),
                "ReadWritePaths": self.systemd.show(
                    unit,
                    "ReadWritePaths",
                ),
            }
        self._schedule_path(result["celery-beat.service"]["ExecStart"])
        return result

    def _assert_boot_gate_units_inactive(self) -> None:
        for unit in BOOT_GATE_UNITS:
            state = self.systemd.show(unit, "ActiveState")
            if state != "inactive":
                raise TransactionError(
                    f"boot-gated unit must be inactive: {unit} state={state}"
                )

    def _assert_boot_gate_units_active(self) -> None:
        for unit in BOOT_GATE_UNITS:
            state = self.systemd.show(unit, "ActiveState")
            if state != "active":
                raise TransactionError(
                    f"boot-gated unit must be active: {unit} state={state}"
                )

    def _capture_original_enablement(self) -> dict[str, str]:
        result = {unit: self.systemd.is_enabled(unit) for unit in BOOT_GATE_UNITS}
        self._validate_enablement_manifest(result)
        return result

    def _validate_enablement_manifest(self, value: object) -> None:
        if not isinstance(value, dict) or set(value) != set(BOOT_GATE_UNITS):
            raise TransactionError("invalid original enablement manifest")
        for unit, state in value.items():
            if state not in SUPPORTED_ENABLEMENT_STATES:
                raise TransactionError(
                    f"unsupported is-enabled state: {unit} state={state}"
                )

    def _gated_enablement(self, original: str) -> str:
        return "disabled" if original == "enabled" else original

    def _ensure_boot_gate_armed(self, journal: dict) -> None:
        if journal.get("boot_gate_released") is True:
            raise TransactionError("released boot gate cannot be rearmed")
        original_enablement = journal["original_enablement"]
        self._validate_enablement_manifest(original_enablement)
        for unit in BOOT_GATE_UNITS:
            original = original_enablement[unit]
            expected = self._gated_enablement(original)
            actual = self.systemd.is_enabled(unit)
            if original == "enabled" and actual == "enabled":
                self.systemd.disable(unit)
                self._fault(f"boot-gate:{unit}:after-disable")
                actual = self.systemd.is_enabled(unit)
            if actual != expected:
                raise TransactionError(
                    f"boot gate is not armed: {unit} "
                    f"expected={expected} actual={actual}"
                )
        if journal.get("boot_gate_armed") is not True:
            journal["boot_gate_armed"] = True
            self._atomic_write_json(
                self.layout.transaction_root / "journal.json",
                journal,
            )

    def _verify_boot_gate_armed(self, journal: Mapping) -> None:
        if (
            journal.get("boot_gate_armed") is not True
            or journal.get("boot_gate_released") is not False
        ):
            raise TransactionError("boot gate durable proof is not armed")
        original_enablement = journal["original_enablement"]
        self._validate_enablement_manifest(original_enablement)
        for unit in BOOT_GATE_UNITS:
            expected = self._gated_enablement(original_enablement[unit])
            actual = self.systemd.is_enabled(unit)
            if actual != expected:
                raise TransactionError(
                    f"boot gate is not armed: {unit} "
                    f"expected={expected} actual={actual}"
                )

    def _verify_original_enablement(self, journal: Mapping) -> None:
        original_enablement = journal["original_enablement"]
        self._validate_enablement_manifest(original_enablement)
        for unit in BOOT_GATE_UNITS:
            actual = self.systemd.is_enabled(unit)
            expected = original_enablement[unit]
            if actual != expected:
                raise TransactionError(
                    f"original enablement is not restored: {unit} "
                    f"expected={expected} actual={actual}"
                )

    def _release_boot_gate(
        self,
        journal: dict,
        *,
        phase: str,
    ) -> None:
        if journal.get("release_target") not in {"old", "candidate"}:
            raise TransactionError("boot gate release lacks an irreversible target")
        self._assert_boot_gate_units_active()
        if journal["boot_gate_released"]:
            self._verify_original_enablement(journal)
            if journal["phase"] != phase:
                raise TransactionError("released boot gate phase mismatch")
            return
        original_enablement = journal["original_enablement"]
        self._validate_enablement_manifest(original_enablement)
        for unit in BOOT_GATE_UNITS:
            expected = original_enablement[unit]
            actual = self.systemd.is_enabled(unit)
            if expected == "enabled" and actual == "disabled":
                self.systemd.enable(unit)
                self._fault(f"boot-gate:{unit}:after-enable")
                actual = self.systemd.is_enabled(unit)
            if actual != expected:
                raise TransactionError(
                    f"cannot restore original enablement: {unit} "
                    f"expected={expected} actual={actual}"
                )
        self._assert_boot_gate_units_active()
        journal["phase"] = phase
        journal["boot_gate_armed"] = False
        journal["boot_gate_released"] = True
        self._atomic_write_json(
            self.layout.transaction_root / "journal.json",
            journal,
        )

    def _validate_candidates(self) -> None:
        stage = self.layout.release_stage
        stage_state = self._validate_directory(stage, required=True)
        if (
            stage_state is None
            or stage_state.st_uid != self.layout.root_uid
            or stage_state.st_gid != self.layout.root_gid
            or stat.S_IMODE(stage_state.st_mode) != 0o700
        ):
            raise TransactionError("release stage must be root-owned mode 0700")
        for unit in UNITS:
            candidate = self.layout.candidate_dropins[unit]
            if candidate.parent != stage or candidate.name != CANDIDATE_NAMES[unit]:
                raise TransactionError(f"candidate escaped release stage: {candidate}")
            self._validate_regular(candidate, allow_writable=False)
            if candidate.read_bytes() != _expected_candidate(unit):
                raise TransactionError(
                    f"candidate drop-in contract mismatch: {candidate}"
                )

    def _validate_transaction_location(self) -> None:
        parent = self.layout.transaction_root.parent
        if self.layout.transaction_root != parent / "runtime-state-transaction":
            raise TransactionError("unsafe persistent transaction path")
        if not parent.exists() and not parent.is_symlink():
            self._validate_directory(parent.parent, required=True)
            try:
                parent.mkdir(mode=0o700)
            except FileExistsError:
                pass
            if parent.exists() and not parent.is_symlink():
                self._apply_metadata(
                    parent,
                    uid=self.layout.root_uid,
                    gid=self.layout.root_gid,
                    mode=0o700,
                )
        parent_state = self._validate_directory(parent, required=True)
        if (
            parent_state is None
            or parent_state.st_uid != self.layout.root_uid
            or parent_state.st_gid != self.layout.root_gid
            or stat.S_IMODE(parent_state.st_mode) != 0o700
        ):
            raise TransactionError("transaction parent must be root-owned mode 0700")
        if self.layout.transaction_root.exists():
            root_state = self._validate_directory(
                self.layout.transaction_root,
                required=True,
            )
            if (
                root_state is None
                or root_state.st_uid != self.layout.root_uid
                or root_state.st_gid != self.layout.root_gid
                or stat.S_IMODE(root_state.st_mode) != 0o700
            ):
                raise TransactionError("transaction root must be root-owned mode 0700")

    def _preparing_root(self) -> Path:
        return (
            self.layout.transaction_root.parent / ".runtime-state-transaction.preparing"
        )

    def _read_preparing_journal(self) -> dict:
        preparing = self._preparing_root()
        state = self._validate_directory(preparing, required=True)
        if (
            state is None
            or state.st_uid != self.layout.root_uid
            or state.st_gid != self.layout.root_gid
            or stat.S_IMODE(state.st_mode) != 0o700
        ):
            raise TransactionError("preparing transaction must be root-owned mode 0700")
        journal_path = preparing / "journal.json"
        self._validate_regular(journal_path, allow_writable=False)
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransactionError("invalid preparing transaction journal") from exc
        if (
            not isinstance(journal, dict)
            or journal.get("version") != 1
            or journal.get("phase") != "ARMING"
        ):
            raise TransactionError("invalid preparing transaction journal")
        _validate_sha(str(journal.get("old_sha")), "preparing old SHA")
        _validate_sha(
            str(journal.get("candidate_sha")),
            "preparing candidate SHA",
        )
        if journal.get("transaction_id") != _transaction_id(
            journal["old_sha"],
            journal["candidate_sha"],
        ):
            raise TransactionError("invalid preparing transaction identity")
        return journal

    def _recover_preparing_transaction(
        self,
        old_sha: str,
        candidate_sha: str,
    ) -> None:
        preparing = self._preparing_root()
        if not preparing.exists() and not preparing.is_symlink():
            return
        journal = self._read_preparing_journal()
        if journal["old_sha"] != old_sha or journal["candidate_sha"] != candidate_sha:
            raise TransactionError(
                "preparing transaction belongs to a different release"
            )
        if self.layout.transaction_root.exists():
            raise TransactionError("canonical and preparing transactions both exist")
        os.replace(preparing, self.layout.transaction_root)
        _fsync_dir(self.layout.transaction_root.parent)

    def _assert_no_terminal_cleanup_pending(self) -> None:
        marker_path = self._terminal_marker_path()
        if not marker_path.exists() and not marker_path.is_symlink():
            return
        marker = self._load_terminal_marker()
        reap = self._terminal_reap_path(marker["transaction_id"])
        if reap.exists() or reap.is_symlink():
            raise TransactionError("terminal cleanup pending")

    def _terminal_marker_path(self) -> Path:
        return self.layout.transaction_root.parent / "runtime-state-terminal.json"

    def _terminal_reap_path(self, transaction_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
            raise TransactionError("invalid terminal transaction identity")
        return self.layout.transaction_root.parent / (
            f"runtime-state-transaction.reap-{transaction_id}"
        )

    def _load_terminal_marker(self) -> dict:
        path = self._terminal_marker_path()
        self._validate_regular(path, allow_writable=False)
        try:
            marker = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransactionError("invalid terminal marker") from exc
        if not isinstance(marker, dict) or marker.get("version") != 1:
            raise TransactionError("invalid terminal marker")
        for field in ("old_sha", "candidate_sha", "terminal_sha"):
            _validate_sha(str(marker.get(field)), f"terminal {field}")
        transaction_id = _transaction_id(
            marker["old_sha"],
            marker["candidate_sha"],
        )
        if marker.get("transaction_id") != transaction_id:
            raise TransactionError("invalid terminal transaction identity")
        expected_reap = self._terminal_reap_path(transaction_id)
        if marker.get("reap_name") != expected_reap.name:
            raise TransactionError("invalid terminal reap path")
        if marker.get("target") not in {"old", "candidate"}:
            raise TransactionError("invalid terminal target")
        if marker.get("phase") not in {
            "RESTORE_FINALIZED",
            "COMMITTED",
        }:
            raise TransactionError("invalid terminal phase")
        if marker.get("result") not in {
            "RESTORE_FINALIZED",
            "finalized",
        }:
            raise TransactionError("invalid terminal result")
        if marker["target"] == "old":
            expected = {
                "phase": "RESTORE_FINALIZED",
                "result": "RESTORE_FINALIZED",
                "terminal_sha": marker["old_sha"],
            }
        else:
            expected = {
                "phase": "COMMITTED",
                "result": "finalized",
                "terminal_sha": marker["candidate_sha"],
            }
        if any(marker[field] != value for field, value in expected.items()):
            raise TransactionError("invalid terminal marker contract")
        return marker

    def _resume_terminal_cleanup(
        self,
        *,
        terminal_sha: str,
        target: str,
    ) -> str:
        self._validate_transaction_location()
        marker = self._load_terminal_marker()
        if marker["terminal_sha"] != terminal_sha:
            raise TransactionError("terminal SHA mismatch")
        if marker["target"] != target:
            raise TransactionError("terminal target mismatch")
        self._activate_transaction(
            marker["old_sha"],
            marker["candidate_sha"],
        )
        reap = self._terminal_reap_path(marker["transaction_id"])
        if reap.exists() or reap.is_symlink():
            self._remove_path(reap)
            _fsync_dir(reap.parent)
        return str(marker["result"])

    def _terminalize(
        self,
        journal: Mapping,
        *,
        terminal_sha: str,
        target: str,
        phase: str,
        result: str,
    ) -> str:
        if journal.get("boot_gate_released") is not True:
            raise TransactionError("terminal cleanup requires released boot gate")
        if journal.get("release_target") != target:
            raise TransactionError("terminal cleanup target mismatch")
        if target == "old":
            expected = {
                "phase": "RESTORE_FINALIZED",
                "result": "RESTORE_FINALIZED",
                "terminal_sha": journal["old_sha"],
            }
        elif target == "candidate":
            expected = {
                "phase": "COMMITTED",
                "result": "finalized",
                "terminal_sha": journal["candidate_sha"],
            }
        else:
            raise TransactionError("invalid terminal cleanup target")
        supplied = {
            "phase": phase,
            "result": result,
            "terminal_sha": terminal_sha,
        }
        if supplied != expected:
            raise TransactionError("invalid terminal cleanup contract")
        transaction_id = str(journal["transaction_id"])
        reap = self._terminal_reap_path(transaction_id)
        marker = {
            "version": 1,
            "old_sha": journal["old_sha"],
            "candidate_sha": journal["candidate_sha"],
            "terminal_sha": terminal_sha,
            "transaction_id": transaction_id,
            "target": target,
            "phase": phase,
            "result": result,
            "reap_name": reap.name,
        }
        self._atomic_write_json(self._terminal_marker_path(), marker)
        self._fault("terminal:after-marker")
        if reap.exists() or reap.is_symlink():
            raise TransactionError("terminal reap path already exists")
        os.replace(self.layout.transaction_root, reap)
        _fsync_dir(reap.parent)
        self._fault("terminal:after-rename")
        self._remove_path(reap)
        _fsync_dir(reap.parent)
        self._fault("terminal:after-reap")
        return result

    def _validate_layout(self) -> None:
        if self.layout.require_root and os.geteuid() != 0:
            raise TransactionError("runtime state transaction must run as root")
        self._validate_transaction_location()
        self._validate_directory(self.layout.backend_data, required=True)
        self._validate_directory(
            self.layout.dedao_legacy_root,
            required=True,
        )
        self._validate_tree(
            self.layout.dedao_legacy_root,
            expected_kind="dir",
        )
        self._validate_tree(
            self.layout.dedao_container,
            expected_kind="dir",
        )
        self._validate_directory(
            self.layout.legacy_uploads.parent,
            required=True,
        )
        self._validate_directory(
            self.layout.uploads_root.parent,
            required=True,
        )
        self._validate_tree(
            self.layout.legacy_uploads,
            expected_kind="dir",
        )
        self._validate_tree(
            self.layout.uploads_root,
            expected_kind="dir",
        )
        self._validate_skills_cache_location()
        self._validate_runtime_root()
        for name, kind in RUNTIME_ITEMS.items():
            self._validate_tree(
                self.layout.backend_data / name,
                expected_kind=kind,
            )
        self._validate_shelf_family(
            self.layout.legacy_shelf_base,
            dedicated=False,
        )
        self._validate_shelf_family(
            self.layout.current_shelf_base,
            dedicated=True,
        )
        for live in self.layout.live_dropins.values():
            if live.exists() or live.is_symlink():
                self._validate_regular(live, allow_writable=False)
            if live.parent.exists():
                self._validate_directory(live.parent, required=True)
        self._validate_base_units()

    def _validate_base_units(self) -> None:
        for base_unit in self.layout.base_units.values():
            current = self._validate_regular(
                base_unit,
                allow_writable=False,
            )
            if (
                current.st_uid != self.layout.root_uid
                or current.st_gid != self.layout.root_gid
                or stat.S_IMODE(current.st_mode) != 0o644
            ):
                raise TransactionError(
                    f"base unit ownership/mode mismatch: {base_unit}"
                )

    def _validate_skills_cache_location(self) -> None:
        root = self.layout.skills_cache_root
        if (
            not root.is_absolute()
            or root.name != "skills-hub"
            or root.parent.name != "health-app"
        ):
            raise TransactionError("unsafe skills cache path")
        if root.exists() or root.is_symlink():
            self._validate_directory(root, required=True)
        if root.parent.exists() or root.parent.is_symlink():
            self._validate_directory(root.parent, required=True)
        else:
            self._validate_directory(root.parent.parent, required=True)

    def _validate_install_destinations(self) -> None:
        self._validate_directory(self.layout.backend_data, required=True)
        for parent in {
            self.layout.runtime_root.parent,
            self.layout.beat_state_dir.parent,
            self.layout.dedao_container.parent,
            self.layout.legacy_uploads.parent,
            self.layout.uploads_root.parent,
            self.layout.systemd_root,
        }:
            self._validate_directory(parent, required=True)
        for name, kind in RUNTIME_ITEMS.items():
            self._validate_tree(
                self.layout.backend_data / name,
                expected_kind=kind,
            )
        self._validate_runtime_root()
        self._validate_tree(
            self.layout.dedao_container,
            expected_kind="dir",
        )
        self._validate_tree(
            self.layout.legacy_uploads,
            expected_kind="dir",
        )
        self._validate_tree(
            self.layout.uploads_root,
            expected_kind="dir",
        )
        self._validate_skills_cache_location()
        self._validate_shelf_family(
            self.layout.legacy_shelf_base,
            dedicated=False,
        )
        self._validate_shelf_family(
            self.layout.current_shelf_base,
            dedicated=True,
        )
        for live in self.layout.live_dropins.values():
            if live.exists() or live.is_symlink():
                self._validate_regular(live, allow_writable=False)
            if live.parent.exists():
                self._validate_directory(live.parent, required=True)
        self._validate_base_units()

    def preflight(
        self,
        old_sha: str,
        candidate_sha: str,
        lock_dir: Path,
        token: str,
    ) -> str:
        _validate_sha(old_sha, "old SHA")
        _validate_sha(candidate_sha, "candidate SHA")
        if old_sha == candidate_sha:
            raise TransactionError("old and candidate SHA must differ")
        self._assert_release_lock(lock_dir, token)
        self._validate_candidates()
        self._validate_transaction_location()
        self._recover_preparing_transaction(old_sha, candidate_sha)
        if self.layout.transaction_root.exists():
            journal = self._load_journal()
            if (
                journal["old_sha"] != old_sha
                or journal["candidate_sha"] != candidate_sha
            ):
                raise TransactionError("transaction belongs to a different release")
            return str(journal["beat_authority"])
        self._assert_no_terminal_cleanup_pending()
        authority, _upload_authority, _old_effective = self._new_transaction_snapshot(
            old_sha,
            candidate_sha,
            lock_dir,
            token,
        )
        return authority

    def _new_transaction_snapshot(
        self,
        old_sha: str,
        candidate_sha: str,
        lock_dir: Path,
        token: str,
    ) -> tuple[str, str, dict[str, dict[str, str]]]:
        self._validate_layout()
        old_effective = self._old_effective()
        schedule = self._schedule_path(
            old_effective["celery-beat.service"]["ExecStart"]
        )
        upload_authority = self._old_upload_authority(old_effective)
        self._assert_release_lock(lock_dir, token)
        authority = "legacy" if schedule == self.layout.legacy_shelf_base else "current"
        return authority, upload_authority, old_effective

    def _old_upload_authority(
        self,
        old_effective: Mapping[str, Mapping[str, str]],
    ) -> str:
        authorities: set[str] = set()
        for unit in ("health-backend.service", "celery-worker.service"):
            paths = set(old_effective[unit]["ReadWritePaths"].split())
            has_legacy = str(self.layout.legacy_uploads) in paths
            has_external = str(self.layout.uploads_root) in paths
            if has_legacy == has_external:
                raise TransactionError(
                    f"cannot determine old upload authority from {unit}"
                )
            authorities.add("legacy" if has_legacy else "external")
        if len(authorities) != 1:
            raise TransactionError("old upload authority differs across writers")
        authority = authorities.pop()
        if authority == "external":
            if self.layout.legacy_uploads.exists() or self.layout.legacy_uploads.is_symlink():
                raise TransactionError("old external upload authority has a legacy copy")
            self._validate_directory(self.layout.uploads_root, required=True)
            self._validate_tree(self.layout.uploads_root, expected_kind="dir")
        else:
            external = self._upload_manifest(self.layout.uploads_root)
            if external.get("exists") is True and (
                external.get("kind") != "dir"
                or bool(external.get("children"))
            ):
                raise TransactionError(
                    "old legacy upload authority has unproven external content"
                )
        return authority

    def _atomic_copy_file(
        self,
        source: Path,
        destination: Path,
        *,
        uid: int,
        gid: int,
        mode: int,
        expected_sha256: str | None = None,
        no_clobber: bool = False,
        temporary_path: Path | None = None,
    ) -> str:
        source_fd = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        temporary: Path | None = None
        try:
            before = os.fstat(source_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise TransactionError(f"unsafe source file: {source}")
            temporary = temporary_path or self._temporary_path(destination)
            if temporary.exists() or temporary.is_symlink():
                self._remove_path(temporary)
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            self._emit(f"copy:{destination}:temp")
            digest = hashlib.sha256()
            try:
                while True:
                    chunk = os.read(source_fd, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    view = memoryview(chunk)
                    while view:
                        written = os.write(descriptor, view)
                        view = view[written:]
                os.fchmod(descriptor, mode)
                current = os.fstat(descriptor)
                if current.st_uid != uid or current.st_gid != gid:
                    os.fchown(descriptor, uid, gid)
                os.fsync(descriptor)
                self._emit(f"copy:{destination}:file-fsync")
            finally:
                os.close(descriptor)
            after = os.fstat(source_fd)
            stable_fields = (
                "st_dev",
                "st_ino",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            if any(
                getattr(before, field) != getattr(after, field)
                for field in stable_fields
            ):
                raise TransactionError(f"source changed during copy: {source}")
            source_hash = digest.hexdigest()
            if expected_sha256 is not None and source_hash != expected_sha256:
                raise TransactionError(
                    f"source changed since merge preflight: {source}"
                )
            if _sha256(temporary) != source_hash:
                raise TransactionError(f"copy hash mismatch: {source} -> {destination}")
            self._emit(f"copy:{destination}:hash")
            self._fault(f"{destination}:before-rename")
            if no_clobber:
                try:
                    os.link(
                        temporary,
                        destination,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    self._validate_regular(
                        destination,
                        allow_writable=False,
                    )
                    if _sha256(destination) != source_hash:
                        raise TransactionError(
                            f"upload content conflict: {destination}"
                        )
                else:
                    temporary.unlink()
                    temporary = None
            else:
                os.replace(temporary, destination)
                temporary = None
            self._emit(f"copy:{destination}:rename")
            self._fault(f"{destination}:after-rename")
            _fsync_dir(destination.parent)
            self._emit(f"copy:{destination}:dir-fsync")
            return source_hash
        finally:
            os.close(source_fd)
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _atomic_write_json(self, path: Path, value: Mapping) -> None:
        payload = (
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        temporary = self._temporary_path(path)
        if temporary.exists() or temporary.is_symlink():
            self._remove_path(temporary)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            if _sha256(temporary) != hashlib.sha256(payload).hexdigest():
                raise TransactionError(f"journal hash mismatch: {path}")
            os.replace(temporary, path)
            _fsync_dir(path.parent)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def _snapshot_path(
        self,
        source: Path,
        snapshot: Path,
    ) -> dict:
        try:
            current = source.lstat()
        except FileNotFoundError:
            return {"exists": False}
        if stat.S_ISLNK(current.st_mode):
            raise TransactionError(f"symlink is not allowed: {source}")
        record = {
            "exists": True,
            "uid": current.st_uid,
            "gid": current.st_gid,
            "mode": stat.S_IMODE(current.st_mode),
        }
        if stat.S_ISREG(current.st_mode):
            if current.st_nlink != 1:
                raise TransactionError(f"hard link is not allowed: {source}")
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            record["kind"] = "file"
            record["sha256"] = self._atomic_copy_file(
                source,
                snapshot,
                uid=os.geteuid(),
                gid=os.getegid(),
                mode=0o600,
            )
            return record
        if not stat.S_ISDIR(current.st_mode):
            raise TransactionError(f"special file is not allowed: {source}")
        snapshot.mkdir(parents=True, mode=0o700)
        children = {}
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            children[child.name] = self._snapshot_path(
                child,
                snapshot / child.name,
            )
        _fsync_dir(snapshot)
        record["kind"] = "dir"
        record["children"] = children
        return record

    def _verify_snapshot_record(
        self,
        record: Mapping,
        snapshot: Path,
    ) -> None:
        if record.get("exists") is False:
            if snapshot.exists() or snapshot.is_symlink():
                raise TransactionError(
                    f"unexpected snapshot for absent path: {snapshot}"
                )
            return
        kind = record.get("kind")
        if kind == "file":
            self._validate_regular(snapshot, allow_writable=False)
            if _sha256(snapshot) != record.get("sha256"):
                raise TransactionError(f"snapshot hash mismatch: {snapshot}")
            return
        if kind != "dir":
            raise TransactionError(f"invalid snapshot kind: {snapshot}")
        self._validate_directory(snapshot, required=True)
        children = record.get("children")
        if not isinstance(children, dict):
            raise TransactionError(f"invalid snapshot manifest: {snapshot}")
        actual = {child.name for child in snapshot.iterdir()}
        if actual != set(children):
            raise TransactionError(f"snapshot tree mismatch: {snapshot}")
        for name, child_record in children.items():
            if "/" in name or name in {"", ".", ".."}:
                raise TransactionError("invalid snapshot child name")
            self._verify_snapshot_record(
                child_record,
                snapshot / name,
            )

    def _snapshot_locations(self, root: Path) -> dict[str, object]:
        snapshots = root / "snapshots"
        result: dict[str, object] = {
            "dropins": {},
            "shelf": {"legacy": {}, "current": {}},
            "runtime_legacy": {},
            "runtime_current": {},
        }
        for unit in UNITS:
            result["dropins"][unit] = self._snapshot_path(
                self.layout.live_dropins[unit],
                snapshots / "dropins" / unit,
            )
        for namespace, base in (
            ("legacy", self.layout.legacy_shelf_base),
            ("current", self.layout.current_shelf_base),
        ):
            for suffix in SHELF_SUFFIXES:
                label = suffix or "base"
                result["shelf"][namespace][label] = self._snapshot_path(
                    Path(f"{base}{suffix}"),
                    snapshots / "shelf" / namespace / label,
                )
        for name in RUNTIME_ITEMS:
            result["runtime_legacy"][name] = self._snapshot_path(
                self.layout.backend_data / name,
                snapshots / "runtime-legacy" / name,
            )
            result["runtime_current"][name] = self._snapshot_path(
                self.layout.runtime_root / name,
                snapshots / "runtime-current" / name,
            )
        result["dedao_legacy"] = self._snapshot_path(
            self.layout.dedao_legacy_root,
            snapshots / "dedao-legacy",
        )
        result["dedao_current"] = self._snapshot_path(
            self.layout.dedao_container,
            snapshots / "dedao-current",
        )
        result["uploads_legacy"] = self._snapshot_path(
            self.layout.legacy_uploads,
            snapshots / "uploads-legacy",
        )
        result["uploads_current"] = self._snapshot_path(
            self.layout.uploads_root,
            snapshots / "uploads-current",
        )
        return result

    def _verify_all_snapshots(self, journal: Mapping) -> None:
        root = self.layout.transaction_root / "snapshots"
        snapshots = journal.get("snapshots")
        if not isinstance(snapshots, dict):
            raise TransactionError("transaction snapshot manifest is missing")
        for unit in UNITS:
            self._verify_snapshot_record(
                snapshots["dropins"][unit],
                root / "dropins" / unit,
            )
        for namespace in ("legacy", "current"):
            for suffix in SHELF_SUFFIXES:
                label = suffix or "base"
                self._verify_snapshot_record(
                    snapshots["shelf"][namespace][label],
                    root / "shelf" / namespace / label,
                )
        for namespace, directory in (
            ("runtime_legacy", "runtime-legacy"),
            ("runtime_current", "runtime-current"),
        ):
            for name in RUNTIME_ITEMS:
                self._verify_snapshot_record(
                    snapshots[namespace][name],
                    root / directory / name,
                )
        self._verify_snapshot_record(
            snapshots["dedao_legacy"],
            root / "dedao-legacy",
        )
        self._verify_snapshot_record(
            snapshots["dedao_current"],
            root / "dedao-current",
        )
        self._verify_snapshot_record(
            snapshots["uploads_legacy"],
            root / "uploads-legacy",
        )
        self._verify_snapshot_record(
            snapshots["uploads_current"],
            root / "uploads-current",
        )

    def _load_journal(self) -> dict:
        self._validate_transaction_location()
        path = self.layout.transaction_root / "journal.json"
        self._validate_regular(path, allow_writable=False)
        try:
            journal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransactionError("invalid transaction journal") from exc
        if not isinstance(journal, dict) or journal.get("version") != 1:
            raise TransactionError("unsupported transaction journal")
        _validate_sha(str(journal.get("old_sha")), "journal old SHA")
        _validate_sha(
            str(journal.get("candidate_sha")),
            "journal candidate SHA",
        )
        if journal.get("transaction_id") != _transaction_id(
            journal["old_sha"],
            journal["candidate_sha"],
        ):
            raise TransactionError("invalid transaction identity")
        self._activate_transaction(
            journal["old_sha"],
            journal["candidate_sha"],
        )
        if journal.get("phase") not in VALID_PHASES:
            raise TransactionError("invalid transaction phase")
        if journal.get("beat_authority") not in {"legacy", "current"}:
            raise TransactionError("invalid beat authority")
        if journal.get("old_upload_authority") not in {"legacy", "external"}:
            raise TransactionError("invalid old upload authority")
        upload_authority = journal.get("upload_authority")
        if upload_authority not in {
            "mixed",
            "external-retiring-legacy",
            "external",
            "legacy-retiring-external",
            "legacy",
        }:
            raise TransactionError("invalid upload authority")
        installed_upload_manifest = journal.get("installed_upload_manifest")
        rollback_upload_manifest = journal.get("rollback_upload_manifest")
        if upload_authority == "mixed":
            if (
                installed_upload_manifest is not None
                or rollback_upload_manifest is not None
            ):
                raise TransactionError("mixed upload authority published a manifest")
        else:
            self._validate_upload_manifest_record(
                installed_upload_manifest,
                label="installed upload manifest",
            )
        if upload_authority in {"legacy-retiring-external", "legacy"}:
            self._validate_upload_manifest_record(
                rollback_upload_manifest,
                label="rollback upload manifest",
            )
        elif (
            upload_authority == "external-retiring-legacy"
            and rollback_upload_manifest is not None
        ):
            raise TransactionError("premature rollback upload manifest")
        elif (
            upload_authority == "external"
            and rollback_upload_manifest is not None
        ):
            self._validate_upload_manifest_record(
                rollback_upload_manifest,
                label="rollback upload manifest",
            )
        self._validate_enablement_manifest(journal.get("original_enablement"))
        if not isinstance(journal.get("boot_gate_armed"), bool):
            raise TransactionError("invalid boot gate armed state")
        if not isinstance(journal.get("boot_gate_released"), bool):
            raise TransactionError("invalid boot gate released state")
        if journal.get("release_target") not in {
            None,
            "old",
            "candidate",
        }:
            raise TransactionError("invalid irreversible release target")
        if journal["boot_gate_armed"] and journal["boot_gate_released"]:
            raise TransactionError("boot gate cannot be armed and released")
        if journal["boot_gate_released"] and journal["release_target"] is None:
            raise TransactionError("released boot gate lacks a target")
        phase = journal["phase"]
        target = journal["release_target"]
        armed = journal["boot_gate_armed"]
        released = journal["boot_gate_released"]
        if target == "old" and phase not in {"RESTORED", "RESTORE_FINALIZED"}:
            raise TransactionError("old release target phase mismatch")
        if target == "candidate" and phase != "COMMITTED":
            raise TransactionError("candidate release target phase mismatch")
        if phase in {"PREPARED", "INSTALLED", "COMMITTING", "RESTORED"}:
            if not armed or released:
                raise TransactionError("boot gate phase contract mismatch")
        if phase == "COMMITTED":
            if released:
                if armed or target != "candidate":
                    raise TransactionError("committed release contract mismatch")
            elif not armed:
                raise TransactionError("committing boot gate is not armed")
        if phase == "RESTORE_FINALIZED" and (armed or not released or target != "old"):
            raise TransactionError("restored release contract mismatch")
        if phase not in {"COMMITTED", "RESTORED", "RESTORE_FINALIZED"} and (
            target is not None or released
        ):
            raise TransactionError("premature release target")
        if journal["phase"] == "ARMING":
            if "snapshots" in journal or "metadata" in journal:
                raise TransactionError("arming journal cannot publish snapshots")
        else:
            self._verify_all_snapshots(journal)
        return journal

    def _finish_prepare(
        self,
        journal: dict,
        lock_dir: Path,
        token: str,
    ) -> str:
        if journal["phase"] != "ARMING":
            raise TransactionError("only an arming transaction can snapshot")
        self._assert_boot_gate_units_inactive()
        self._ensure_boot_gate_armed(journal)
        self._assert_boot_gate_units_inactive()
        self._recover_scoped_orphans(journal)
        self._fault("prepare:after-gate")
        confirmed_effective = self._old_effective()
        if confirmed_effective != journal["old_effective"]:
            raise TransactionError(
                "effective config changed while preparing transaction"
            )
        self._assert_release_lock(lock_dir, token)
        transaction_id = journal["transaction_id"]
        build_root = (
            self.layout.transaction_root / f".snapshot-build-{transaction_id}.tmp"
        )
        canonical_snapshots = self.layout.transaction_root / "snapshots"
        if build_root.exists() or build_root.is_symlink():
            self._remove_path(build_root)
        if canonical_snapshots.exists() or canonical_snapshots.is_symlink():
            self._remove_path(canonical_snapshots)
        build_root.mkdir(mode=0o700)
        _fsync_dir(self.layout.transaction_root)
        try:
            snapshots = self._snapshot_locations(build_root)
            _fsync_dir(build_root)
            os.replace(
                build_root / "snapshots",
                canonical_snapshots,
            )
            _fsync_dir(self.layout.transaction_root)
            self._fault("prepare:after-snapshot-publish")
            build_root.rmdir()
            _fsync_dir(self.layout.transaction_root)
        except BaseException:
            raise
        journal["metadata"] = {
            "backend_data": _metadata(self.layout.backend_data),
            "runtime_root": (
                _metadata(self.layout.runtime_root)
                if self.layout.runtime_root.exists()
                else None
            ),
            "beat_state_dir": (
                _metadata(self.layout.beat_state_dir)
                if self.layout.beat_state_dir.exists()
                else None
            ),
        }
        journal["snapshots"] = snapshots
        self._write_journal_phase(journal, "PREPARED")
        self._assert_release_lock(lock_dir, token)
        return "PREPARED"

    def status(self, lock_dir: Path, token: str) -> str:
        self._assert_release_lock(lock_dir, token)
        if not self.layout.transaction_root.exists():
            preparing = self._preparing_root()
            if preparing.exists() or preparing.is_symlink():
                journal = self._read_preparing_journal()
                return (
                    f"phase=ARMING old_sha={journal['old_sha']} "
                    f"candidate_sha={journal['candidate_sha']} "
                    "gate_armed=false gate_released=false "
                    "release_target=none next_action=prepare "
                    "state_source=preparing"
                )
            marker_path = self._terminal_marker_path()
            if not marker_path.exists() and not marker_path.is_symlink():
                return (
                    "phase=NONE old_sha=none candidate_sha=none "
                    "gate_armed=false gate_released=false "
                    "release_target=none next_action=preflight "
                    "state_source=none"
                )
            marker = self._load_terminal_marker()
            reap = self._terminal_reap_path(marker["transaction_id"])
            next_action = "release-gate" if marker["target"] == "old" else "finalize"
            if not reap.exists() and not reap.is_symlink():
                next_action = "none"
            return (
                f"phase={marker['phase']} "
                f"old_sha={marker['old_sha']} "
                f"candidate_sha={marker['candidate_sha']} "
                "gate_armed=false gate_released=true "
                f"release_target={marker['target']} "
                f"next_action={next_action} state_source=terminal"
            )
        journal = self._load_journal()
        self._assert_release_lock(lock_dir, token)
        phase = journal["phase"]
        if phase == "ARMING":
            next_action = "prepare"
        elif phase == "PREPARED":
            next_action = "install"
        elif phase == "INSTALLED":
            next_action = "candidate-guard"
        elif phase == "COMMITTING":
            next_action = "commit"
        elif phase == "COMMITTED":
            next_action = "finalize" if journal["boot_gate_released"] else "commit"
        elif phase == "RESTORED":
            next_action = (
                "release-gate"
                if journal["release_target"] == "old"
                else "rollback-guard"
            )
        else:
            next_action = "release-gate"
        gate_armed = str(journal["boot_gate_armed"]).lower()
        gate_released = str(journal["boot_gate_released"]).lower()
        release_target = journal["release_target"] or "none"
        return (
            f"phase={phase} old_sha={journal['old_sha']} "
            f"candidate_sha={journal['candidate_sha']} "
            f"gate_armed={gate_armed} "
            f"gate_released={gate_released} "
            f"release_target={release_target} "
            f"next_action={next_action} state_source=journal"
        )

    def prepare(
        self,
        old_sha: str,
        candidate_sha: str,
        lock_dir: Path,
        token: str,
    ) -> str:
        _validate_sha(old_sha, "old SHA")
        _validate_sha(candidate_sha, "candidate SHA")
        if old_sha == candidate_sha:
            raise TransactionError("old and candidate SHA must differ")
        self._activate_transaction(old_sha, candidate_sha)
        self._assert_release_lock(lock_dir, token)
        self._validate_candidates()
        self._validate_transaction_location()
        self._recover_preparing_transaction(old_sha, candidate_sha)
        if self.layout.transaction_root.exists():
            journal = self._load_journal()
            if (
                journal["old_sha"] != old_sha
                or journal["candidate_sha"] != candidate_sha
            ):
                raise TransactionError("transaction belongs to a different release")
            self._assert_release_lock(lock_dir, token)
            if journal["boot_gate_released"]:
                raise TransactionError(
                    "terminal transaction boot gate is already released"
                )
            if journal["phase"] == "ARMING":
                return self._finish_prepare(journal, lock_dir, token)
            self._assert_boot_gate_units_inactive()
            self._ensure_boot_gate_armed(journal)
            return str(journal["phase"])
        self._assert_no_terminal_cleanup_pending()
        authority, upload_authority, old_effective = self._new_transaction_snapshot(
            old_sha,
            candidate_sha,
            lock_dir,
            token,
        )
        self._assert_boot_gate_units_inactive()
        confirmed_effective = self._old_effective()
        if confirmed_effective != old_effective:
            raise TransactionError(
                "effective config changed while preparing transaction"
            )
        original_enablement = self._capture_original_enablement()
        parent = self.layout.transaction_root.parent
        self._validate_directory(parent, required=True)
        temporary = self._preparing_root()
        if temporary.exists() or temporary.is_symlink():
            raise TransactionError("unexpected preparing transaction collision")
        temporary.mkdir(mode=0o700)
        self._apply_metadata(
            temporary,
            uid=self.layout.root_uid,
            gid=self.layout.root_gid,
            mode=0o700,
        )
        intent_durable = False
        try:
            journal = {
                "version": 1,
                "old_sha": old_sha,
                "candidate_sha": candidate_sha,
                "transaction_id": _transaction_id(
                    old_sha,
                    candidate_sha,
                ),
                "phase": "ARMING",
                "beat_authority": authority,
                "old_upload_authority": upload_authority,
                "upload_authority": "mixed",
                "old_effective": old_effective,
                "original_enablement": original_enablement,
                "boot_gate_armed": False,
                "boot_gate_released": False,
                "release_target": None,
            }
            self._atomic_write_json(temporary / "journal.json", journal)
            _fsync_dir(temporary)
            intent_durable = True
            self._fault("prepare:before-intent-publish")
            self._assert_release_lock(lock_dir, token)
            os.replace(temporary, self.layout.transaction_root)
            _fsync_dir(parent)
            self._fault("prepare:after-intent")
            return self._finish_prepare(journal, lock_dir, token)
        except BaseException:
            if temporary.exists() and not intent_durable:
                self._remove_path(temporary)
            raise

    def _apply_metadata(
        self,
        path: Path,
        *,
        uid: int,
        gid: int,
        mode: int,
    ) -> None:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode):
            raise TransactionError(f"symlink is not allowed: {path}")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        if stat.S_ISDIR(before.st_mode):
            flags |= getattr(os, "O_DIRECTORY", 0)
        elif not stat.S_ISREG(before.st_mode):
            raise TransactionError(f"special file is not allowed: {path}")
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if opened.st_dev != before.st_dev or opened.st_ino != before.st_ino:
                raise TransactionError(f"path changed while applying metadata: {path}")
            if opened.st_uid != uid or opened.st_gid != gid:
                os.fchown(descriptor, uid, gid)
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
            after = os.fstat(descriptor)
            if after.st_dev != before.st_dev or after.st_ino != before.st_ino:
                raise TransactionError(f"path changed while applying metadata: {path}")
        finally:
            os.close(descriptor)
        _fsync_dir(path.parent)

    def _normalize_runtime_tree(self, path: Path) -> None:
        current = path.lstat()
        if stat.S_ISREG(current.st_mode):
            if current.st_nlink != 1:
                raise TransactionError(f"hard link is not allowed: {path}")
            self._apply_metadata(
                path,
                uid=self.layout.health_uid,
                gid=self.layout.health_gid,
                mode=0o600,
            )
            return
        if not stat.S_ISDIR(current.st_mode):
            raise TransactionError(f"special file is not allowed: {path}")
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            self._normalize_runtime_tree(child)
        self._apply_metadata(
            path,
            uid=self.layout.health_uid,
            gid=self.layout.health_gid,
            mode=0o700,
        )

    def _upload_manifest(self, path: Path) -> dict:
        try:
            before = path.lstat()
        except FileNotFoundError:
            return {"exists": False}
        if stat.S_ISLNK(before.st_mode):
            raise TransactionError(f"symlink is not allowed: {path}")
        if before.st_mode & 0o022:
            raise TransactionError(f"group/world writable upload entry: {path}")
        record = {
            "exists": True,
            "uid": before.st_uid,
            "gid": before.st_gid,
            "mode": stat.S_IMODE(before.st_mode),
        }
        if stat.S_ISREG(before.st_mode):
            if before.st_nlink != 1:
                raise TransactionError(f"hard link is not allowed: {path}")
            record["kind"] = "file"
            record["sha256"] = _sha256(path)
        elif stat.S_ISDIR(before.st_mode):
            record["kind"] = "dir"
            record["children"] = {
                child.name: self._upload_manifest(child)
                for child in sorted(path.iterdir(), key=lambda item: item.name)
            }
        else:
            raise TransactionError(f"special file is not allowed: {path}")
        try:
            after = path.lstat()
        except FileNotFoundError as exc:
            raise TransactionError(
                f"upload source changed while scanning: {path}"
            ) from exc
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ):
            raise TransactionError(f"upload source changed while scanning: {path}")
        return record

    def _validate_upload_manifest_record(
        self,
        record: object,
        *,
        label: str,
    ) -> None:
        if not isinstance(record, dict):
            raise TransactionError(f"invalid {label}")
        if record.get("exists") is False:
            if set(record) != {"exists"}:
                raise TransactionError(f"invalid {label}")
            return
        if record.get("exists") is not True:
            raise TransactionError(f"invalid {label}")
        for field in ("uid", "gid", "mode"):
            value = record.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TransactionError(f"invalid {label}")
        if int(record["mode"]) & 0o022:
            raise TransactionError(f"unsafe {label}")
        kind = record.get("kind")
        if kind == "file":
            if set(record) != {"exists", "uid", "gid", "mode", "kind", "sha256"}:
                raise TransactionError(f"invalid {label}")
            digest = record.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise TransactionError(f"invalid {label}")
            return
        if kind != "dir":
            raise TransactionError(f"invalid {label}")
        if set(record) != {"exists", "uid", "gid", "mode", "kind", "children"}:
            raise TransactionError(f"invalid {label}")
        children = record.get("children")
        if not isinstance(children, dict):
            raise TransactionError(f"invalid {label}")
        for name, child in children.items():
            if (
                not isinstance(name, str)
                or name in {"", ".", ".."}
                or "/" in name
                or "\x00" in name
            ):
                raise TransactionError(f"invalid {label}")
            self._validate_upload_manifest_record(
                child,
                label=f"{label} child",
            )

    def _assert_upload_manifest(
        self,
        path: Path,
        expected: Mapping,
        *,
        label: str,
    ) -> None:
        self._validate_upload_manifest_record(expected, label=label)
        if self._upload_manifest(path) != expected:
            raise TransactionError(f"{label} mismatch: {path}")

    def _upload_manifest_is_subset(
        self,
        current: Mapping,
        sealed: Mapping,
        *,
        require_metadata_match: bool,
        allow_empty_root_if_sealed_absent: bool,
        is_root: bool = True,
    ) -> bool:
        if current.get("exists") is False:
            return True
        if sealed.get("exists") is False:
            return bool(
                is_root
                and allow_empty_root_if_sealed_absent
                and current.get("kind") == "dir"
                and not current.get("children")
            )
        if current.get("kind") != sealed.get("kind"):
            return False
        if require_metadata_match and any(
            current.get(field) != sealed.get(field)
            for field in ("uid", "gid", "mode")
        ):
            return False
        if current.get("kind") == "file":
            return current.get("sha256") == sealed.get("sha256")
        current_children = current.get("children")
        sealed_children = sealed.get("children")
        if not isinstance(current_children, dict) or not isinstance(
            sealed_children,
            dict,
        ):
            return False
        return all(
            name in sealed_children
            and self._upload_manifest_is_subset(
                child,
                sealed_children[name],
                require_metadata_match=require_metadata_match,
                allow_empty_root_if_sealed_absent=False,
                is_root=False,
            )
            for name, child in current_children.items()
        )

    def _assert_upload_manifest_subset(
        self,
        path: Path,
        sealed: Mapping,
        *,
        label: str,
        require_metadata_match: bool,
        allow_empty_root_if_sealed_absent: bool = False,
    ) -> None:
        self._validate_upload_manifest_record(
            sealed,
            label=f"{label} sealed manifest",
        )
        current = self._upload_manifest(path)
        if not self._upload_manifest_is_subset(
            current,
            sealed,
            require_metadata_match=require_metadata_match,
            allow_empty_root_if_sealed_absent=allow_empty_root_if_sealed_absent,
        ):
            raise TransactionError(f"{label} is not a sealed subset: {path}")

    def _plan_upload_merge(
        self,
        record: Mapping,
        source: Path,
        destination: Path,
        directories: list[Path],
        files: list[tuple[Mapping, Path, Path, bool]],
    ) -> None:
        if record.get("exists") is False:
            return
        kind = record.get("kind")
        try:
            destination_state = destination.lstat()
        except FileNotFoundError:
            destination_state = None
        if kind == "file":
            if destination_state is None:
                files.append((record, source, destination, True))
                return
            self._validate_regular(destination, allow_writable=False)
            if _sha256(destination) != record.get("sha256"):
                raise TransactionError(f"upload content conflict: {destination}")
            files.append((record, source, destination, False))
            return
        if kind != "dir":
            raise TransactionError(f"invalid upload merge record: {source}")
        if destination_state is None:
            directories.append(destination)
        else:
            self._validate_directory(destination, required=True)
        children = record.get("children")
        if not isinstance(children, dict):
            raise TransactionError(f"invalid upload merge manifest: {source}")
        for name, child_record in sorted(children.items()):
            if "/" in name or name in {"", ".", ".."}:
                raise TransactionError("invalid upload merge child name")
            self._plan_upload_merge(
                child_record,
                source / name,
                destination / name,
                directories,
                files,
            )

    def _apply_upload_merge(
        self,
        directories: Sequence[Path],
        files: Sequence[tuple[Mapping, Path, Path, bool]],
        *,
        destination_root: Path,
        stage: Path,
    ) -> None:
        for destination in directories:
            try:
                destination.lstat()
            except FileNotFoundError:
                self._validate_directory(destination.parent, required=True)
                try:
                    destination.mkdir(mode=0o700)
                except FileExistsError:
                    pass
                _fsync_dir(destination.parent)
            self._validate_directory(destination, required=True)
            self._apply_metadata(
                destination,
                uid=self.layout.health_uid,
                gid=self.layout.health_gid,
                mode=0o700,
            )
        for record, source, destination, copy_required in files:
            expected_hash = record.get("sha256")
            if not isinstance(expected_hash, str):
                raise TransactionError(f"invalid upload file manifest: {source}")
            if copy_required:
                relative = destination.relative_to(destination_root)
                stage_name = hashlib.sha256(str(relative).encode("utf-8")).hexdigest()
                self._atomic_copy_file(
                    source,
                    destination,
                    uid=self.layout.health_uid,
                    gid=self.layout.health_gid,
                    mode=0o600,
                    expected_sha256=expected_hash,
                    no_clobber=True,
                    temporary_path=stage / stage_name,
                )
                continue
            self._validate_regular(source, allow_writable=False)
            self._validate_regular(destination, allow_writable=False)
            if (
                _sha256(source) != expected_hash
                or _sha256(destination) != expected_hash
            ):
                raise TransactionError(f"upload content conflict: {destination}")

    def _merge_upload_record(
        self,
        record: Mapping,
        source: Path,
        destination: Path,
        *,
        provision_destination: bool,
    ) -> None:
        if record.get("exists") is False:
            if provision_destination:
                self._ensure_directory(
                    destination,
                    uid=self.layout.health_uid,
                    gid=self.layout.health_gid,
                    mode=0o700,
                )
                self._validate_tree(destination, expected_kind="dir")
                self._normalize_runtime_tree(destination)
            return
        if record.get("kind") != "dir":
            raise TransactionError(f"upload root must be a directory: {source}")
        self._validate_tree(destination, expected_kind="dir")
        directories: list[Path] = []
        files: list[tuple[Mapping, Path, Path, bool]] = []
        self._plan_upload_merge(
            record,
            source,
            destination,
            directories,
            files,
        )
        stage = self._temporary_path(destination)
        if stage.exists() or stage.is_symlink():
            self._recover_upload_stage(stage)
        self._validate_directory(stage.parent, required=True)
        stage.mkdir(mode=0o700)
        self._apply_metadata(
            stage,
            uid=self.layout.root_uid,
            gid=self.layout.root_gid,
            mode=0o700,
        )
        try:
            self._apply_upload_merge(
                directories,
                files,
                destination_root=destination,
                stage=stage,
            )
        finally:
            self._recover_upload_stage(stage)
        self._normalize_runtime_tree(destination)

    def _persist_upload_journal(self, journal: Mapping) -> None:
        self._atomic_write_json(
            self.layout.transaction_root / "journal.json",
            journal,
        )

    def _retire_upload_tree(
        self,
        path: Path,
        sealed: Mapping,
        *,
        fault_prefix: str,
    ) -> None:
        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        if sealed.get("exists") is not True:
            raise TransactionError(f"unsealed upload source entry: {path}")
        if stat.S_ISLNK(current.st_mode):
            raise TransactionError(f"refusing to retire upload symlink: {path}")
        if any(
            actual != sealed.get(field)
            for field, actual in (
                ("uid", current.st_uid),
                ("gid", current.st_gid),
                ("mode", stat.S_IMODE(current.st_mode)),
            )
        ):
            raise TransactionError(f"retiring upload source metadata changed: {path}")
        if stat.S_ISREG(current.st_mode):
            if sealed.get("kind") != "file":
                raise TransactionError(f"retiring upload source kind changed: {path}")
            if current.st_nlink != 1 or current.st_mode & 0o022:
                raise TransactionError(f"refusing to retire unsafe upload file: {path}")
            if self._upload_manifest(path) != sealed:
                raise TransactionError(f"retiring upload source changed: {path}")
            path.unlink()
            _fsync_dir(path.parent)
            self._fault(f"{fault_prefix}:{path}:after-remove")
            return
        if sealed.get("kind") != "dir":
            raise TransactionError(f"retiring upload source kind changed: {path}")
        if not stat.S_ISDIR(current.st_mode) or current.st_mode & 0o022:
            raise TransactionError(f"refusing to retire unsafe upload entry: {path}")
        sealed_children = sealed.get("children")
        if not isinstance(sealed_children, dict):
            raise TransactionError(f"invalid sealed upload source: {path}")
        children = sorted(path.iterdir(), key=lambda item: item.name)
        if any(child.name not in sealed_children for child in children):
            raise TransactionError(f"unsealed upload source entry below: {path}")
        for child in children:
            self._retire_upload_tree(
                child,
                sealed_children[child.name],
                fault_prefix=fault_prefix,
            )
        after = path.lstat()
        if (
            after.st_dev != current.st_dev
            or after.st_ino != current.st_ino
            or after.st_mode != current.st_mode
            or after.st_uid != current.st_uid
            or after.st_gid != current.st_gid
        ):
            raise TransactionError(f"retiring upload source changed: {path}")
        path.rmdir()
        _fsync_dir(path.parent)
        self._fault(f"{fault_prefix}:{path}:after-remove")

    def _install_uploads(self, journal: dict) -> None:
        authority = journal["upload_authority"]
        prepared = journal["snapshots"]["uploads_legacy"]
        snapshot = self.layout.transaction_root / "snapshots/uploads-legacy"
        if authority == "mixed":
            if journal["old_upload_authority"] == "external":
                if (
                    self.layout.legacy_uploads.exists()
                    or self.layout.legacy_uploads.is_symlink()
                ):
                    raise TransactionError(
                        "old external upload authority has a legacy copy"
                    )
                prepared_current = journal["snapshots"]["uploads_current"]
                if self._upload_manifest(self.layout.uploads_root) != prepared_current:
                    raise TransactionError("external uploads changed after snapshot")
                self._validate_tree(self.layout.uploads_root, expected_kind="dir")
                installed = self._upload_manifest(self.layout.uploads_root)
                self._validate_upload_manifest_record(
                    installed,
                    label="installed upload manifest",
                )
                journal["installed_upload_manifest"] = installed
                journal["upload_authority"] = "external"
                self._persist_upload_journal(journal)
                return
            if self._upload_manifest(self.layout.legacy_uploads) != prepared:
                raise TransactionError("legacy uploads changed after snapshot")
            self._assert_upload_manifest_subset(
                self.layout.uploads_root,
                prepared,
                label="external upload partial",
                require_metadata_match=False,
                allow_empty_root_if_sealed_absent=True,
            )
            self._merge_upload_record(
                prepared,
                snapshot,
                self.layout.uploads_root,
                provision_destination=True,
            )
            installed = self._upload_manifest(self.layout.uploads_root)
            self._validate_upload_manifest_record(
                installed,
                label="installed upload manifest",
            )
            journal["installed_upload_manifest"] = installed
            journal["upload_authority"] = "external-retiring-legacy"
            self._persist_upload_journal(journal)
            authority = "external-retiring-legacy"
        if authority == "external":
            if self.layout.legacy_uploads.exists() or self.layout.legacy_uploads.is_symlink():
                raise TransactionError("legacy upload authority unexpectedly exists")
            self._validate_directory(self.layout.uploads_root, required=True)
            self._validate_tree(self.layout.uploads_root, expected_kind="dir")
            return
        if authority != "external-retiring-legacy":
            raise TransactionError("uploads are not installable from current authority")
        self._assert_upload_manifest(
            self.layout.uploads_root,
            journal["installed_upload_manifest"],
            label="installed upload manifest",
        )
        self._assert_upload_manifest_subset(
            self.layout.legacy_uploads,
            prepared,
            label="retiring legacy upload source",
            require_metadata_match=True,
        )
        self._retire_upload_tree(
            self.layout.legacy_uploads,
            prepared,
            fault_prefix="uploads:install-retire",
        )
        if self.layout.legacy_uploads.exists() or self.layout.legacy_uploads.is_symlink():
            raise TransactionError("legacy upload retirement did not complete")
        journal["upload_authority"] = "external"
        self._persist_upload_journal(journal)

    def _restore_uploads(self, journal: dict) -> None:
        authority = journal["upload_authority"]
        if authority in {"mixed", "external-retiring-legacy"}:
            self._install_uploads(journal)
            authority = journal["upload_authority"]
        if journal["old_upload_authority"] == "external":
            if authority != "external":
                raise TransactionError("old external uploads are not authoritative")
            if self.layout.legacy_uploads.exists() or self.layout.legacy_uploads.is_symlink():
                raise TransactionError("old external upload authority has a legacy copy")
            self._validate_directory(self.layout.uploads_root, required=True)
            self._validate_tree(self.layout.uploads_root, expected_kind="dir")
            return
        expected = journal.get("rollback_upload_manifest")
        if authority == "external" and expected is None:
            if self.layout.legacy_uploads.exists() or self.layout.legacy_uploads.is_symlink():
                raise TransactionError("legacy upload tree exists before rollback copy")
            self._validate_tree(self.layout.uploads_root, expected_kind="dir")
            self._normalize_runtime_tree(self.layout.uploads_root)
            expected = self._upload_manifest(self.layout.uploads_root)
            if expected.get("exists") is not True or expected.get("kind") != "dir":
                raise TransactionError("external upload authority is missing")
            self._validate_upload_manifest_record(
                expected,
                label="rollback upload manifest",
            )
            journal["rollback_upload_manifest"] = expected
            self._persist_upload_journal(journal)
        if authority == "external":
            if expected is None:
                raise TransactionError("rollback upload manifest is missing")
            self._assert_upload_manifest(
                self.layout.uploads_root,
                expected,
                label="rollback upload source manifest",
            )
            if self._upload_manifest(self.layout.legacy_uploads) != expected:
                self._merge_upload_record(
                    expected,
                    self.layout.uploads_root,
                    self.layout.legacy_uploads,
                    provision_destination=True,
                )
            self._assert_upload_manifest(
                self.layout.legacy_uploads,
                expected,
                label="rollback upload destination manifest",
            )
            journal["upload_authority"] = "legacy-retiring-external"
            self._persist_upload_journal(journal)
            authority = "legacy-retiring-external"
        if authority == "legacy":
            if expected is None:
                raise TransactionError("rollback upload manifest is missing")
            self._assert_upload_manifest(
                self.layout.legacy_uploads,
                expected,
                label="rollback upload destination manifest",
            )
            if self.layout.uploads_root.exists() or self.layout.uploads_root.is_symlink():
                raise TransactionError("external upload authority unexpectedly exists")
            return
        if authority != "legacy-retiring-external" or expected is None:
            raise TransactionError("uploads are not restorable from current authority")
        self._assert_upload_manifest(
            self.layout.legacy_uploads,
            expected,
            label="rollback upload destination manifest",
        )
        self._assert_upload_manifest_subset(
            self.layout.uploads_root,
            expected,
            label="retiring external upload source",
            require_metadata_match=True,
        )
        self._retire_upload_tree(
            self.layout.uploads_root,
            expected,
            fault_prefix="uploads:restore-retire",
        )
        if self.layout.uploads_root.exists() or self.layout.uploads_root.is_symlink():
            raise TransactionError("external upload retirement did not complete")
        journal["upload_authority"] = "legacy"
        self._persist_upload_journal(journal)

    def _verify_upload_authority(self, journal: Mapping, *, target: str) -> None:
        if target == "candidate":
            if journal.get("upload_authority") != "external":
                raise TransactionError("candidate upload authority is not external")
            if self.layout.legacy_uploads.exists() or self.layout.legacy_uploads.is_symlink():
                raise TransactionError("candidate upload authority has a legacy copy")
            self._validate_directory(self.layout.uploads_root, required=True)
            self._validate_tree(self.layout.uploads_root, expected_kind="dir")
            return
        if target == "old":
            old_authority = journal.get("old_upload_authority")
            if journal.get("upload_authority") != old_authority:
                raise TransactionError("old upload authority does not match its release")
            if old_authority == "external":
                if (
                    self.layout.legacy_uploads.exists()
                    or self.layout.legacy_uploads.is_symlink()
                ):
                    raise TransactionError("old upload authority has a legacy copy")
                self._validate_directory(self.layout.uploads_root, required=True)
                self._validate_tree(self.layout.uploads_root, expected_kind="dir")
                return
            if old_authority != "legacy":
                raise TransactionError("invalid old upload authority")
            if (
                self.layout.uploads_root.exists()
                or self.layout.uploads_root.is_symlink()
            ):
                raise TransactionError("old upload authority has an external copy")
            self._validate_directory(self.layout.legacy_uploads, required=True)
            self._validate_tree(self.layout.legacy_uploads, expected_kind="dir")
            return
        raise TransactionError("invalid upload authority target")

    def _install_skills_cache(self) -> None:
        self._ensure_directory(
            self.layout.skills_cache_root.parent,
            uid=self.layout.root_uid,
            gid=self.layout.root_gid,
            mode=0o755,
        )
        self._ensure_directory(
            self.layout.skills_cache_root,
            uid=self.layout.health_uid,
            gid=self.layout.health_gid,
            mode=0o700,
        )

    def _ensure_directory(
        self,
        path: Path,
        *,
        uid: int,
        gid: int,
        mode: int,
    ) -> None:
        if path.exists() or path.is_symlink():
            self._validate_directory(path, required=True)
        else:
            self._validate_directory(path.parent, required=True)
            path.mkdir(mode=mode)
            _fsync_dir(path.parent)
        self._apply_metadata(path, uid=uid, gid=gid, mode=mode)

    def _remove_path(self, path: Path) -> None:
        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(current.st_mode):
            raise TransactionError(f"refusing to remove symlink: {path}")
        if stat.S_ISREG(current.st_mode):
            if current.st_nlink != 1:
                raise TransactionError(f"refusing to remove hard link: {path}")
            path.unlink()
            _fsync_dir(path.parent)
            return
        if not stat.S_ISDIR(current.st_mode):
            raise TransactionError(f"refusing to remove special file: {path}")
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            self._remove_path(child)
        path.rmdir()
        _fsync_dir(path.parent)

    def _recover_upload_stage(self, stage: Path) -> None:
        try:
            stage_state = stage.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(stage_state.st_mode) or not stat.S_ISDIR(stage_state.st_mode):
            raise TransactionError(f"unsafe scoped upload stage: {stage}")
        if (
            stage_state.st_uid != self.layout.root_uid
            or stage_state.st_gid != self.layout.root_gid
            or stat.S_IMODE(stage_state.st_mode) != 0o700
        ):
            raise TransactionError(f"unsafe scoped upload stage metadata: {stage}")
        for child in sorted(stage.iterdir(), key=lambda item: item.name):
            child_state = child.lstat()
            if (
                not re.fullmatch(r"[0-9a-f]{64}", child.name)
                or not stat.S_ISREG(child_state.st_mode)
                or child_state.st_nlink not in {1, 2}
            ):
                raise TransactionError(f"unsafe scoped upload stage entry: {child}")
            child.unlink()
        _fsync_dir(stage)
        stage.rmdir()
        _fsync_dir(stage.parent)

    def _recover_scoped_orphans(self, journal: Mapping) -> None:
        if journal.get("transaction_id") != self._active_transaction_id:
            raise TransactionError("cannot recover another transaction")
        destinations = [
            self.layout.transaction_root / "journal.json",
            self.layout.dedao_container,
            self.layout.dedao_workspace,
            *self.layout.live_dropins.values(),
        ]
        destinations.extend(self.layout.backend_data / name for name in RUNTIME_ITEMS)
        for base in (
            self.layout.legacy_shelf_base,
            self.layout.current_shelf_base,
        ):
            destinations.extend(Path(f"{base}{suffix}") for suffix in SHELF_SUFFIXES)
        destinations.extend(self.layout.runtime_root / name for name in RUNTIME_ITEMS)
        for destination in destinations:
            if not destination.parent.exists():
                continue
            temporary = self._temporary_path(destination)
            if temporary.exists() or temporary.is_symlink():
                self._remove_path(temporary)
        self._recover_upload_stage(self._temporary_path(self.layout.legacy_uploads))
        self._recover_upload_stage(self._temporary_path(self.layout.uploads_root))
        snapshot_build = self.layout.transaction_root / (
            f".snapshot-build-{self._active_transaction_id}.tmp"
        )
        if snapshot_build.exists() or snapshot_build.is_symlink():
            self._remove_path(snapshot_build)

    def _materialize_record(
        self,
        record: Mapping,
        snapshot: Path,
        destination: Path,
        *,
        runtime_policy: bool = False,
    ) -> None:
        if record.get("exists") is False:
            self._remove_path(destination)
            return
        kind = record["kind"]
        uid = self.layout.health_uid if runtime_policy else int(record["uid"])
        gid = self.layout.health_gid if runtime_policy else int(record["gid"])
        mode = (
            (0o600 if kind == "file" else 0o700)
            if runtime_policy
            else int(record["mode"])
        )
        if kind == "file":
            if destination.exists() and destination.is_dir():
                self._remove_path(destination)
            self._atomic_copy_file(
                snapshot,
                destination,
                uid=uid,
                gid=gid,
                mode=mode,
            )
            return
        if kind != "dir":
            raise TransactionError(f"invalid record kind for {destination}")
        self._validate_directory(destination.parent, required=True)
        temporary = self._temporary_path(destination)
        if temporary.exists() or temporary.is_symlink():
            self._remove_path(temporary)
        temporary.mkdir(mode=0o700)
        _fsync_dir(destination.parent)
        try:
            for name, child_record in record["children"].items():
                self._materialize_record(
                    child_record,
                    snapshot / name,
                    temporary / name,
                    runtime_policy=runtime_policy,
                )
            self._apply_metadata(
                temporary,
                uid=uid,
                gid=gid,
                mode=mode,
            )
            if destination.exists() or destination.is_symlink():
                self._remove_path(destination)
            os.replace(temporary, destination)
            _fsync_dir(destination.parent)
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise

    def _write_journal_phase(self, journal: dict, phase: str) -> None:
        if phase not in VALID_PHASES:
            raise TransactionError(f"invalid phase: {phase}")
        journal["phase"] = phase
        self._atomic_write_json(
            self.layout.transaction_root / "journal.json",
            journal,
        )

    def _install_runtime_bootstrap(self, journal: Mapping) -> None:
        snapshots = journal["snapshots"]
        root = self.layout.transaction_root / "snapshots"
        for name in RUNTIME_ITEMS:
            destination = self.layout.runtime_root / name
            if destination.exists() or destination.is_symlink():
                self._validate_tree(
                    destination,
                    expected_kind=RUNTIME_ITEMS[name],
                )
                self._normalize_runtime_tree(destination)
                continue
            record = snapshots["runtime_legacy"][name]
            if record.get("exists"):
                self._materialize_record(
                    record,
                    root / "runtime-legacy" / name,
                    destination,
                    runtime_policy=True,
                )

    def _install_shelf(self, journal: Mapping) -> None:
        if journal["beat_authority"] == "current":
            self._validate_shelf_family(
                self.layout.current_shelf_base,
                dedicated=True,
            )
            for suffix in SHELF_SUFFIXES:
                target = Path(f"{self.layout.current_shelf_base}{suffix}")
                if target.exists():
                    self._normalize_runtime_tree(target)
            return
        root = self.layout.transaction_root / "snapshots/shelf/legacy"
        for suffix in SHELF_SUFFIXES:
            label = suffix or "base"
            record = journal["snapshots"]["shelf"]["legacy"][label]
            destination = Path(f"{self.layout.current_shelf_base}{suffix}")
            self._materialize_record(
                record,
                root / label,
                destination,
                runtime_policy=True,
            )

    def _install_dedao(self, journal: Mapping) -> None:
        self._ensure_directory(
            self.layout.dedao_container,
            uid=self.layout.health_uid,
            gid=self.layout.health_gid,
            mode=0o700,
        )
        if self.layout.dedao_workspace.exists():
            self._validate_tree(
                self.layout.dedao_container,
                expected_kind="dir",
            )
            self._normalize_runtime_tree(self.layout.dedao_container)
            return
        record = journal["snapshots"]["dedao_legacy"]
        if record.get("exists"):
            self._materialize_record(
                record,
                self.layout.transaction_root / "snapshots/dedao-legacy",
                self.layout.dedao_workspace,
                runtime_policy=True,
            )
        else:
            self._ensure_directory(
                self.layout.dedao_workspace,
                uid=self.layout.health_uid,
                gid=self.layout.health_gid,
                mode=0o700,
            )

    def _install_dropins(self) -> None:
        for unit in UNITS:
            destination = self.layout.live_dropins[unit]
            self._ensure_directory(
                destination.parent,
                uid=self.layout.root_uid,
                gid=self.layout.root_gid,
                mode=0o755,
            )
            self._atomic_copy_file(
                self.layout.candidate_dropins[unit],
                destination,
                uid=self.layout.root_uid,
                gid=self.layout.root_gid,
                mode=0o644,
            )

    def _validate_candidate_effective(self) -> None:
        for unit in UNITS:
            if self.systemd.show(unit, "FragmentPath") != str(
                self.layout.base_units[unit]
            ):
                raise TransactionError(f"candidate FragmentPath mismatch for {unit}")
            dropins = self.systemd.show(unit, "DropInPaths").split()
            if str(self.layout.live_dropins[unit]) not in dropins:
                raise TransactionError(f"candidate drop-in is not effective for {unit}")
            writable = {
                value.removeprefix("-")
                for value in self.systemd.show(unit, "ReadWritePaths").split()
            }
            if unit == "health-backend.service":
                expected = {
                    str(self.layout.uploads_root),
                    str(self.layout.skills_cache_root),
                    str(self.layout.runtime_root),
                    str(self.layout.dedao_container),
                }
                if writable != expected:
                    raise TransactionError(f"unexpected writable paths for {unit}")
            elif unit == "celery-worker.service":
                expected = {
                    str(self.layout.uploads_root),
                    str(self.layout.dedao_container),
                }
                if writable != expected:
                    raise TransactionError(f"unexpected writable paths for {unit}")
            else:
                expected = {
                    str(self.layout.beat_state_dir),
                }
                if writable != expected:
                    raise TransactionError(
                        "celery-beat writable paths exceed its state boundary"
                    )
        schedule = self._schedule_path(
            self.systemd.show("celery-beat.service", "ExecStart")
        )
        if schedule != self.layout.current_shelf_base:
            raise TransactionError("candidate celery-beat schedule is not current")

    def install(
        self,
        old_sha: str,
        candidate_sha: str,
        lock_dir: Path,
        token: str,
    ) -> str:
        _validate_sha(old_sha, "old SHA")
        _validate_sha(candidate_sha, "candidate SHA")
        self._assert_release_lock(lock_dir, token)
        self._validate_candidates()
        journal = self._load_journal()
        self._recover_scoped_orphans(journal)
        if journal["old_sha"] != old_sha or journal["candidate_sha"] != candidate_sha:
            raise TransactionError("transaction SHA mismatch")
        self._verify_boot_gate_armed(journal)
        if journal["phase"] in {"INSTALLED", "COMMITTING", "COMMITTED"}:
            self._validate_candidate_effective()
            return str(journal["phase"])
        if journal["phase"] not in {"PREPARED", "RESTORED"}:
            raise TransactionError("transaction is not installable")
        self._assert_boot_gate_units_inactive()
        self._validate_install_destinations()
        self._assert_release_lock(lock_dir, token)
        self._install_uploads(journal)
        self._install_skills_cache()
        self._apply_metadata(
            self.layout.backend_data,
            uid=self.layout.root_uid,
            gid=self.layout.root_gid,
            mode=0o755,
        )
        self._ensure_directory(
            self.layout.runtime_root,
            uid=self.layout.health_uid,
            gid=self.layout.health_gid,
            mode=0o700,
        )
        self._ensure_directory(
            self.layout.beat_state_dir,
            uid=self.layout.health_uid,
            gid=self.layout.health_gid,
            mode=0o700,
        )
        self._install_runtime_bootstrap(journal)
        self._install_dedao(journal)
        self._install_shelf(journal)
        self._install_dropins()
        self._assert_release_lock(lock_dir, token)
        self.systemd.daemon_reload()
        self._validate_candidate_effective()
        self._write_journal_phase(journal, "INSTALLED")
        self._assert_release_lock(lock_dir, token)
        return "INSTALLED"

    def _restore_dropins(self, journal: Mapping) -> None:
        root = self.layout.transaction_root / "snapshots/dropins"
        for unit in UNITS:
            destination = self.layout.live_dropins[unit]
            record = journal["snapshots"]["dropins"][unit]
            if record.get("exists"):
                self._ensure_directory(
                    destination.parent,
                    uid=self.layout.root_uid,
                    gid=self.layout.root_gid,
                    mode=0o755,
                )
            self._materialize_record(
                record,
                root / unit,
                destination,
            )

    def _restore_shelf(self, journal: Mapping) -> None:
        root = self.layout.transaction_root / "snapshots/shelf"
        for namespace, base in (
            ("legacy", self.layout.legacy_shelf_base),
            ("current", self.layout.current_shelf_base),
        ):
            for suffix in SHELF_SUFFIXES:
                label = suffix or "base"
                self._materialize_record(
                    journal["snapshots"]["shelf"][namespace][label],
                    root / namespace / label,
                    Path(f"{base}{suffix}"),
                )

    def _restore_runtime(self, journal: Mapping) -> None:
        root = self.layout.transaction_root / "snapshots/runtime-current"
        for name in RUNTIME_ITEMS:
            self._materialize_record(
                journal["snapshots"]["runtime_current"][name],
                root / name,
                self.layout.runtime_root / name,
            )
        original = journal["metadata"]["runtime_root"]
        if original is None:
            if self.layout.runtime_root.exists():
                self._validate_runtime_root()
                if any(self.layout.runtime_root.iterdir()):
                    raise TransactionError("runtime root is not empty after restore")
                self.layout.runtime_root.rmdir()
                _fsync_dir(self.layout.runtime_root.parent)
        else:
            self._apply_metadata(
                self.layout.runtime_root,
                uid=int(original["uid"]),
                gid=int(original["gid"]),
                mode=int(original["mode"]),
            )

    def _restore_legacy_runtime(self, journal: Mapping) -> None:
        root = self.layout.transaction_root / "snapshots/runtime-legacy"
        for name in RUNTIME_ITEMS:
            self._materialize_record(
                journal["snapshots"]["runtime_legacy"][name],
                root / name,
                self.layout.backend_data / name,
            )

    def _restore_beat_dir_metadata(self, journal: Mapping) -> None:
        original = journal["metadata"]["beat_state_dir"]
        if original is None:
            if self.layout.beat_state_dir.exists():
                self._validate_shelf_family(
                    self.layout.current_shelf_base,
                    dedicated=True,
                )
                if any(self.layout.beat_state_dir.iterdir()):
                    raise TransactionError(
                        "beat state directory is not empty after restore"
                    )
                self.layout.beat_state_dir.rmdir()
                _fsync_dir(self.layout.beat_state_dir.parent)
        else:
            self._apply_metadata(
                self.layout.beat_state_dir,
                uid=int(original["uid"]),
                gid=int(original["gid"]),
                mode=int(original["mode"]),
            )

    def _validate_old_effective(self, journal: Mapping) -> None:
        expected = journal["old_effective"]
        for unit in UNITS:
            for prop in (
                "FragmentPath",
                "DropInPaths",
                "ExecStart",
                "ReadWritePaths",
            ):
                actual = self.systemd.show(unit, prop)
                if actual != expected[unit][prop]:
                    raise TransactionError(
                        f"old effective config mismatch: {unit} {prop}"
                    )

    def restore(
        self,
        rollback_sha: str,
        lock_dir: Path,
        token: str,
    ) -> str:
        _validate_sha(rollback_sha, "rollback SHA")
        self._assert_release_lock(lock_dir, token)
        journal = self._load_journal()
        self._recover_scoped_orphans(journal)
        if rollback_sha == journal["candidate_sha"]:
            if journal["release_target"] not in {None, "candidate"}:
                raise TransactionError("opposite release target is irrevocable")
            if journal["phase"] not in {
                "INSTALLED",
                "COMMITTING",
                "COMMITTED",
            }:
                raise TransactionError("candidate cannot be retained before install")
            self._validate_candidate_effective()
            self._verify_upload_authority(journal, target="candidate")
            if journal["boot_gate_released"]:
                self._verify_original_enablement(journal)
            else:
                self._verify_boot_gate_armed(journal)
            self._assert_release_lock(lock_dir, token)
            return "candidate-retained"
        if journal["release_target"] is not None:
            raise TransactionError(
                "release target is irrevocable; restore is forbidden"
            )
        if rollback_sha != journal["old_sha"]:
            raise TransactionError("rollback SHA matches neither old nor candidate")
        if journal["phase"] in {"COMMITTING", "COMMITTED"}:
            raise TransactionError("candidate rollback floor is already committed")
        if journal["phase"] == "ARMING":
            raise TransactionError("transaction is not prepared for restore")
        self._verify_boot_gate_armed(journal)
        self._assert_boot_gate_units_inactive()
        self._validate_install_destinations()
        self._assert_release_lock(lock_dir, token)
        self._restore_uploads(journal)
        self._restore_shelf(journal)
        self._restore_runtime(journal)
        self._restore_legacy_runtime(journal)
        self._materialize_record(
            journal["snapshots"]["dedao_current"],
            self.layout.transaction_root / "snapshots/dedao-current",
            self.layout.dedao_container,
        )
        self._restore_dropins(journal)
        self._restore_beat_dir_metadata(journal)
        backend = journal["metadata"]["backend_data"]
        self._apply_metadata(
            self.layout.backend_data,
            uid=int(backend["uid"]),
            gid=int(backend["gid"]),
            mode=int(backend["mode"]),
        )
        self._assert_release_lock(lock_dir, token)
        self.systemd.daemon_reload()
        self._validate_old_effective(journal)
        self._verify_boot_gate_armed(journal)
        self._write_journal_phase(journal, "RESTORED")
        self._assert_release_lock(lock_dir, token)
        return "restored"

    def release_gate(
        self,
        old_sha: str,
        lock_dir: Path,
        token: str,
    ) -> str:
        _validate_sha(old_sha, "release-gate SHA")
        self._assert_release_lock(lock_dir, token)
        if not self.layout.transaction_root.exists():
            result = self._resume_terminal_cleanup(
                terminal_sha=old_sha,
                target="old",
            )
            self._assert_release_lock(lock_dir, token)
            return result
        journal = self._load_journal()
        if old_sha != journal["old_sha"]:
            raise TransactionError("release-gate requires the old SHA")
        if journal["phase"] not in {"RESTORED", "RESTORE_FINALIZED"}:
            raise TransactionError("release-gate requires a restored old release")
        self._validate_old_effective(journal)
        self._verify_upload_authority(journal, target="old")
        if journal["release_target"] is None:
            self._verify_boot_gate_armed(journal)
            self._assert_boot_gate_units_active()
            journal["release_target"] = "old"
            self._atomic_write_json(
                self.layout.transaction_root / "journal.json",
                journal,
            )
            self._fault("release-gate:after-release-intent")
        elif journal["release_target"] != "old":
            raise TransactionError("opposite release target is irrevocable")
        self._release_boot_gate(
            journal,
            phase="RESTORE_FINALIZED",
        )
        self._assert_release_lock(lock_dir, token)
        return self._terminalize(
            journal,
            terminal_sha=old_sha,
            target="old",
            phase="RESTORE_FINALIZED",
            result="RESTORE_FINALIZED",
        )

    def commit(
        self,
        candidate_sha: str,
        lock_dir: Path,
        token: str,
    ) -> str:
        _validate_sha(candidate_sha, "candidate SHA")
        self._assert_release_lock(lock_dir, token)
        journal = self._load_journal()
        if candidate_sha != journal["candidate_sha"]:
            raise TransactionError("candidate SHA mismatch")
        if journal["phase"] not in {"INSTALLED", "COMMITTING"}:
            if journal["phase"] != "COMMITTED":
                raise TransactionError("transaction is not committable")
        self._validate_candidate_effective()
        self._verify_upload_authority(journal, target="candidate")
        if journal["phase"] in {"INSTALLED", "COMMITTING"}:
            self._verify_boot_gate_armed(journal)
            self._validate_shelf_family(
                self.layout.legacy_shelf_base,
                dedicated=False,
            )
            if journal["phase"] == "INSTALLED":
                self._write_journal_phase(journal, "COMMITTING")
            for suffix in SHELF_SUFFIXES:
                target = Path(f"{self.layout.legacy_shelf_base}{suffix}")
                if target.exists() or target.is_symlink():
                    self._validate_regular(target, allow_writable=False)
                    target.unlink()
                    _fsync_dir(target.parent)
            self._assert_release_lock(lock_dir, token)
            self._write_journal_phase(journal, "COMMITTED")
        if journal["release_target"] is None:
            self._verify_boot_gate_armed(journal)
            self._assert_boot_gate_units_active()
            journal["release_target"] = "candidate"
            self._atomic_write_json(
                self.layout.transaction_root / "journal.json",
                journal,
            )
            self._fault("commit:after-release-intent")
        elif journal["release_target"] != "candidate":
            raise TransactionError("opposite release target is irrevocable")
        self._release_boot_gate(journal, phase="COMMITTED")
        self._assert_release_lock(lock_dir, token)
        return "COMMITTED"

    def finalize(
        self,
        candidate_sha: str,
        lock_dir: Path,
        token: str,
    ) -> str:
        _validate_sha(candidate_sha, "finalize SHA")
        self._assert_release_lock(lock_dir, token)
        if not self.layout.transaction_root.exists():
            result = self._resume_terminal_cleanup(
                terminal_sha=candidate_sha,
                target="candidate",
            )
            self._assert_release_lock(lock_dir, token)
            return result
        journal = self._load_journal()
        if candidate_sha != journal["candidate_sha"]:
            raise TransactionError("finalize candidate SHA mismatch")
        if (
            journal["phase"] != "COMMITTED"
            or journal["release_target"] != "candidate"
            or journal["boot_gate_released"] is not True
        ):
            raise TransactionError("finalize requires committed released candidate")
        self._validate_candidate_effective()
        self._verify_upload_authority(journal, target="candidate")
        self._verify_original_enablement(journal)
        self._assert_release_lock(lock_dir, token)
        return self._terminalize(
            journal,
            terminal_sha=candidate_sha,
            target="candidate",
            phase="COMMITTED",
            result="finalized",
        )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parse_cli(list(argv if argv is not None else sys.argv[1:]))
        layout = production_layout(Path(__file__).resolve().parent)
        transaction = ReleaseTransaction(layout, SubprocessSystemd())
        if arguments.command == "status":
            result = transaction.status(
                arguments.lock_dir,
                arguments.token,
            )
        elif arguments.command == "preflight":
            result = transaction.preflight(
                str(arguments.first_sha),
                str(arguments.second_sha),
                arguments.lock_dir,
                arguments.token,
            )
        elif arguments.command == "prepare":
            result = transaction.prepare(
                arguments.first_sha,
                str(arguments.second_sha),
                arguments.lock_dir,
                arguments.token,
            )
        elif arguments.command == "install":
            result = transaction.install(
                arguments.first_sha,
                str(arguments.second_sha),
                arguments.lock_dir,
                arguments.token,
            )
        elif arguments.command == "restore":
            result = transaction.restore(
                arguments.first_sha,
                arguments.lock_dir,
                arguments.token,
            )
        elif arguments.command == "release-gate":
            result = transaction.release_gate(
                str(arguments.first_sha),
                arguments.lock_dir,
                arguments.token,
            )
        elif arguments.command == "finalize":
            result = transaction.finalize(
                str(arguments.first_sha),
                arguments.lock_dir,
                arguments.token,
            )
        else:
            result = transaction.commit(
                str(arguments.first_sha),
                arguments.lock_dir,
                arguments.token,
            )
        print(
            f"RUNTIME_STATE_TRANSACTION_OK command={arguments.command} result={result}"
        )
        return 0
    except (OSError, subprocess.CalledProcessError, TransactionError) as exc:
        print(f"RUNTIME_STATE_TRANSACTION_FAILED error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
