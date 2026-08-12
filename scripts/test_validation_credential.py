from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.validation_credential import (
    build_credential,
    credential_path,
    validation_state_dir,
    verify_credential,
    write_credential_atomic,
)


COMMANDS = [
    {
        "name": "mobile:lint",
        "argv": ["npm", "run", "lint"],
        "cwd": "mobile",
        "blocking": True,
    }
]
TOOLCHAIN = {
    "python": "3.12.4",
    "node": "v22.1.0",
    "npm": "10.8.0",
    "swift": "Swift 6.0",
    "os": "test-os-arm64",
}


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "credential@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Credential Test"],
        cwd=repo,
        check=True,
    )
    (repo / "mobile").mkdir()
    (repo / "mobile/package-lock.json").write_text("lock-v1\n", encoding="utf-8")
    (repo / "app.txt").write_text("source-v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    return repo


def _issue(repo: Path, *, now: int = 1_000, ttl: int = 600) -> tuple[Path, Path]:
    log = validation_state_dir(repo) / "logs" / "run" / "mobile-lint.log"
    log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    log.write_text("lint passed\n", encoding="utf-8")
    log.chmod(0o600)
    payload = build_credential(
        repo=repo,
        profile_name="mobile",
        profile_version="1",
        commands=COMMANDS,
        logs={"mobile:lint": log},
        ttl_seconds=ttl,
        now=now,
        toolchain=TOOLCHAIN,
    )
    path = credential_path(repo, "mobile")
    write_credential_atomic(path, payload)
    return path, log


def _verify(repo: Path, path: Path, *, now: int = 1_100, **overrides):
    options = {
        "repo": repo,
        "path": path,
        "profile_name": "mobile",
        "profile_version": "1",
        "commands": COMMANDS,
        "now": now,
        "toolchain": TOOLCHAIN,
    }
    options.update(overrides)
    return verify_credential(**options)


def test_same_tree_rebase_reuses_successful_credential(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    original_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    original_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True
    ).strip()

    subprocess.run(
        ["git", "commit", "--amend", "-qm", "same tree, new commit metadata"],
        cwd=repo,
        check=True,
    )

    assert subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip() != original_commit
    assert subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True
    ).strip() == original_tree
    verdict = _verify(repo, path)
    assert verdict.reusable, verdict.reason


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"profile_version": "2"}, "profile"),
        (
            {
                "commands": [
                    {
                        "name": "mobile:lint",
                        "argv": ["npm", "run", "lint", "--", "--strict"],
                        "cwd": "mobile",
                        "blocking": True,
                    }
                ]
            },
            "commands",
        ),
        ({"toolchain": {**TOOLCHAIN, "node": "v23.0.0"}}, "toolchain"),
    ],
)
def test_reuse_fails_when_bound_inputs_change(
    tmp_path: Path, override: dict, reason: str
) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)

    verdict = _verify(repo, path, **override)

    assert not verdict.reusable
    assert reason in verdict.reason


def test_reuse_fails_when_tree_changes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    (repo / "app.txt").write_text("source-v2\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "change source"], cwd=repo, check=True)

    verdict = _verify(repo, path)

    assert not verdict.reusable
    assert "tree" in verdict.reason


def test_reuse_fails_when_worktree_has_uncommitted_source(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    (repo / "app.txt").write_text("uncommitted source\n", encoding="utf-8")

    verdict = _verify(repo, path)

    assert not verdict.reusable
    assert "dirty" in verdict.reason


def test_reuse_fails_when_lockfile_or_log_changes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path, log = _issue(repo)

    (repo / "mobile/package-lock.json").write_text("lock-v2\n", encoding="utf-8")
    lock_verdict = _verify(repo, path)
    assert not lock_verdict.reusable
    assert "lock" in lock_verdict.reason

    (repo / "mobile/package-lock.json").write_text("lock-v1\n", encoding="utf-8")
    log.write_text("tampered\n", encoding="utf-8")
    log_verdict = _verify(repo, path)
    assert not log_verdict.reusable
    assert "log" in log_verdict.reason


def test_reuse_fails_after_expiry_or_corrupt_state(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo, now=1_000, ttl=10)

    expired = _verify(repo, path, now=1_011)
    assert not expired.reusable
    assert "expired" in expired.reason

    path.write_text("not-json", encoding="utf-8")
    corrupt = _verify(repo, path, now=1_001)
    assert not corrupt.reusable
    assert "invalid" in corrupt.reason


def test_reuse_rejects_tampered_expiry(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo, now=1_000, ttl=10)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expires_at"] = 99_999
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)

    verdict = _verify(repo, path, now=1_001)

    assert not verdict.reusable
    assert "identity" in verdict.reason


def test_state_is_shared_by_worktrees_and_written_atomically_private(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(linked), "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    assert validation_state_dir(linked) == validation_state_dir(repo)
    path, _ = _issue(repo)

    assert path.parent == validation_state_dir(repo) / "credentials"
    assert stat.S_IMODE(validation_state_dir(repo).stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob(".tmp-*"))


def test_credential_rejects_non_private_or_symlinked_logs(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path, log = _issue(repo)
    log.chmod(0o644)

    public_log = _verify(repo, path)
    assert not public_log.reusable
    assert "private" in public_log.reason

    log.chmod(0o600)
    original = log.with_name("original.log")
    log.rename(original)
    os.symlink(original, log)
    symlinked = _verify(repo, path)
    assert not symlinked.reusable
    assert "symlink" in symlinked.reason


def test_credential_requires_one_log_binding_per_command(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    with pytest.raises(ValueError, match="log bindings"):
        build_credential(
            repo=repo,
            profile_name="mobile",
            profile_version="1",
            commands=COMMANDS,
            logs={},
            ttl_seconds=600,
            now=1_000,
            toolchain=TOOLCHAIN,
        )
