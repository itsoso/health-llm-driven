#!/usr/bin/env python3
"""One fail-closed local release lease shared by Python and shell entrypoints."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import signal
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


STATE_DIRECTORY_NAME = "reva-release-state"
LOCK_FILE_NAME = "release-publish.lock"
LOCK_SCHEMA_VERSION = 1
GIT_BINARY = "/usr/bin/git"


class ReleaseLockError(RuntimeError):
    """A release lease could not be acquired or verified."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class ReleaseLease:
    path: Path
    fd: int
    audit_fd: int
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        try:
            try:
                _replace_payload(self.audit_fd, b"{}\n")
            finally:
                os.close(self.audit_fd)
        finally:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self._released = True

    def __enter__(self) -> ReleaseLease:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _git_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": "/var/empty",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def git_common_dir(repo_root: Path) -> Path:
    try:
        completed = subprocess.run(
            [
                GIT_BINARY,
                "--no-replace-objects",
                "-C",
                str(repo_root.resolve()),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=_git_environment(),
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseLockError(
            f"cannot resolve Git common directory for {repo_root}", kind="unsafe"
        ) from error
    common = Path(completed.stdout.strip())
    if not common.is_absolute():
        raise ReleaseLockError("Git common directory is not absolute", kind="unsafe")
    return common.resolve()


def lock_path(repo_root: Path) -> Path:
    return git_common_dir(repo_root) / STATE_DIRECTORY_NAME / LOCK_FILE_NAME


def _validate_common_directory(descriptor: int, path: Path) -> os.stat_result:
    metadata = os.fstat(descriptor)
    entry = os.stat(path, follow_symlinks=False)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or not stat.S_ISDIR(entry.st_mode)
        or (metadata.st_dev, metadata.st_ino) != (entry.st_dev, entry.st_ino)
    ):
        raise ReleaseLockError(
            f"unsafe Git common directory: {path}", kind="unsafe"
        )
    return metadata


def _open_common_directory(repo_root: Path) -> tuple[int, Path]:
    common = git_common_dir(repo_root)
    common_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    common_flags |= getattr(os, "O_DIRECTORY", 0)
    common_flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(common, common_flags)
        _validate_common_directory(descriptor, common)
        if git_common_dir(repo_root) != common:
            raise ReleaseLockError(
                "Git common directory changed while opening the release lock",
                kind="unsafe",
            )
        _validate_common_directory(descriptor, common)
        return descriptor, common
    except ReleaseLockError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ReleaseLockError(
            f"unsafe Git common directory: {common}", kind="unsafe"
        ) from error


def _open_state_directory(
    common_fd: int,
    common: Path,
    *,
    create: bool,
) -> tuple[int, Path]:
    state_fd: int | None = None
    try:
        if create:
            try:
                os.mkdir(STATE_DIRECTORY_NAME, mode=0o700, dir_fd=common_fd)
            except FileExistsError:
                pass
        state_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        state_flags |= getattr(os, "O_DIRECTORY", 0)
        state_flags |= getattr(os, "O_NOFOLLOW", 0)
        state_fd = os.open(STATE_DIRECTORY_NAME, state_flags, dir_fd=common_fd)
        metadata = os.fstat(state_fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ReleaseLockError(
                f"unsafe release state directory: {common / STATE_DIRECTORY_NAME}",
                kind="unsafe",
            )
        return state_fd, common / STATE_DIRECTORY_NAME
    except ReleaseLockError:
        if state_fd is not None:
            os.close(state_fd)
        raise
    except OSError as error:
        if state_fd is not None:
            os.close(state_fd)
        raise ReleaseLockError(
            f"unsafe release state directory: {common / STATE_DIRECTORY_NAME}",
            kind="unsafe",
        ) from error


def _open_owner_audit(
    common_fd: int,
    common: Path,
    *,
    create: bool,
) -> tuple[int, Path]:
    state_fd: int | None = None
    descriptor: int | None = None
    try:
        state_fd, directory = _open_state_directory(
            common_fd,
            common,
            create=create,
        )
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        if create:
            flags |= os.O_CREAT
        descriptor = os.open(LOCK_FILE_NAME, flags, 0o600, dir_fd=state_fd)
        metadata = os.fstat(descriptor)
        entry = os.stat(LOCK_FILE_NAME, dir_fd=state_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino) != (entry.st_dev, entry.st_ino)
        ):
            raise ReleaseLockError(
                f"unsafe release publish lock: {directory / LOCK_FILE_NAME}",
                kind="unsafe",
            )
        return descriptor, directory / LOCK_FILE_NAME
    except ReleaseLockError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ReleaseLockError("unsafe release publish lock", kind="unsafe") from error
    finally:
        if state_fd is not None:
            os.close(state_fd)


def _replace_payload(descriptor: int, payload: bytes) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write to release lock")
        view = view[written:]
    os.fsync(descriptor)


def _encode_owner(label: str) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": LOCK_SCHEMA_VERSION,
                "label": label[:160],
                "pid": os.getpid(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def acquire_release_lock(
    repo_root: Path,
    *,
    label: str = "release",
) -> ReleaseLease:
    descriptor, common = _open_common_directory(repo_root)
    audit_descriptor: int | None = None
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise ReleaseLockError(
                    "another release publish transaction is already active",
                    kind="busy",
                ) from error
            raise
        audit_descriptor, path = _open_owner_audit(
            descriptor,
            common,
            create=True,
        )
        _replace_payload(audit_descriptor, _encode_owner(label))
        return ReleaseLease(
            path=path,
            fd=descriptor,
            audit_fd=audit_descriptor,
        )
    except BaseException:
        if audit_descriptor is not None:
            os.close(audit_descriptor)
        os.close(descriptor)
        raise


def _validate_candidate_descriptor(descriptor: int) -> os.stat_result:
    if descriptor < 3:
        raise ReleaseLockError(
            "inherited release lock descriptor must be at least 3", kind="adoption"
        )
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        raise ReleaseLockError(
            "inherited release lock descriptor is not open", kind="adoption"
        ) from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
    ):
        raise ReleaseLockError(
            "inherited release lock descriptor is unsafe", kind="adoption"
        )
    return metadata


def _try_nonblocking_lock(descriptor: int) -> bool:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise


def verify_adoption(repo_root: Path, descriptor: int) -> Path:
    """Prove *descriptor* is the explicitly inherited, currently locked OFD."""

    candidate = _validate_candidate_descriptor(descriptor)
    probe, common = _open_common_directory(repo_root)
    probe_acquired = False
    try:
        expected = os.fstat(probe)
        if (candidate.st_dev, candidate.st_ino) != (expected.st_dev, expected.st_ino):
            raise ReleaseLockError(
                "inherited release lock descriptor points to the wrong inode",
                kind="adoption",
            )

        # An independent open must be blocked, proving a live kernel lock exists.
        probe_acquired = _try_nonblocking_lock(probe)
        if probe_acquired:
            raise ReleaseLockError(
                "inherited release lock has no live kernel lock owner",
                kind="adoption",
            )

        # Re-locking the explicitly inherited descriptor succeeds only when it
        # shares the already-locked open-file-description. A reopened same-inode
        # descriptor remains blocked and is rejected.
        if not _try_nonblocking_lock(descriptor):
            raise ReleaseLockError(
                "inherited descriptor does not share the release lock owner",
                kind="adoption",
            )
        _validate_common_directory(probe, common)
        if git_common_dir(repo_root) != common:
            raise ReleaseLockError(
                "Git common directory changed during release lock adoption",
                kind="adoption",
            )
        return common / STATE_DIRECTORY_NAME / LOCK_FILE_NAME
    finally:
        if probe_acquired:
            fcntl.flock(probe, fcntl.LOCK_UN)
        os.close(probe)


def run_release_entrypoint(
    repo_root: Path,
    *,
    label: str,
    command: Sequence[str],
) -> int:
    if not command:
        raise ReleaseLockError("release entrypoint command is empty", kind="unsafe")
    with acquire_release_lock(repo_root, label=label) as lease:
        environment = dict(os.environ)
        environment.pop("REVA_RELEASE_LOCK_TOKEN", None)
        environment["REVA_RELEASE_LOCK_ADOPT"] = "1"
        environment["REVA_RELEASE_LOCK_FD"] = str(lease.fd)
        child: subprocess.Popen[bytes] | None = None
        received_signal: int | None = None
        previous_handlers: dict[int, object] = {}

        def forward_signal(signum: int, _frame: object) -> None:
            nonlocal received_signal
            received_signal = signum
            if child is None or child.poll() is not None:
                return
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, forward_signal)
        try:
            child = subprocess.Popen(
                list(command),
                env=environment,
                pass_fds=(lease.fd,),
                start_new_session=True,
            )
            if received_signal is not None and child.poll() is None:
                try:
                    os.killpg(child.pid, received_signal)
                except ProcessLookupError:
                    pass
            returncode = child.wait()
        finally:
            for signum, previous_handler in previous_handlers.items():
                signal.signal(signum, previous_handler)

        if returncode < 0:
            return 128 + abs(returncode)
        if received_signal is not None and returncode == 0:
            return 128 + received_signal
        return returncode


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    path_command = subcommands.add_parser("path")
    path_command.add_argument("--repo-root", type=Path, required=True)
    verify = subcommands.add_parser("verify-adopt")
    verify.add_argument("--repo-root", type=Path, required=True)
    verify.add_argument("--fd", type=int, required=True)
    run = subcommands.add_parser("run")
    run.add_argument("--repo-root", type=Path, required=True)
    run.add_argument("--label", required=True)
    run.add_argument("entrypoint", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "path":
            print(lock_path(args.repo_root))
            return 0
        if args.command == "verify-adopt":
            verify_adoption(args.repo_root, args.fd)
            return 0
        if args.command == "run":
            command = list(args.entrypoint)
            if command and command[0] == "--":
                command.pop(0)
            return run_release_entrypoint(
                args.repo_root,
                label=args.label,
                command=command,
            )
        raise AssertionError(f"unhandled release lock command: {args.command}")
    except ReleaseLockError as error:
        print(str(error), file=sys.stderr)
        if error.kind == "busy":
            print("✗ 另一个发布任务正在执行。", file=sys.stderr)
        elif error.kind == "unsafe":
            print("✗ 发布锁路径不安全，拒绝继续。", file=sys.stderr)
        return 73 if error.kind in {"busy", "adoption"} else 70
    except OSError as error:
        print(f"release lock I/O failure: {error}", file=sys.stderr)
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
