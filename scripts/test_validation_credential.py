from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.validation_credential as validation_credential

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
DEPENDENCY_STATE = {
    "backend": "a" * 64,
    "frontend": "b" * 64,
    "mobile": "c" * 64,
}
VALIDATION_ENVIRONMENT = {
    "DATABASE_URL": "sqlite:///:memory:",
    "TEST_DATABASE_URL": "sqlite:///:memory:",
    "TZ": "Asia/Shanghai",
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
        profile_name="all",
        profile_version="1",
        commands=COMMANDS,
        logs={"mobile:lint": log},
        ttl_seconds=ttl,
        now=now,
        toolchain=TOOLCHAIN,
        dependency_state=DEPENDENCY_STATE,
        validation_environment=VALIDATION_ENVIRONMENT,
    )
    path = credential_path(repo, "all")
    write_credential_atomic(path, payload)
    return path, log


def _verify(repo: Path, path: Path, *, now: int = 1_100, **overrides):
    options = {
        "repo": repo,
        "path": path,
        "profile_name": "all",
        "profile_version": "1",
        "commands": COMMANDS,
        "now": now,
        "toolchain": TOOLCHAIN,
        "dependency_state": DEPENDENCY_STATE,
        "validation_environment": VALIDATION_ENVIRONMENT,
    }
    options.update(overrides)
    return verify_credential(**options)


def test_same_tree_rebase_does_not_reuse_same_uid_credential(tmp_path: Path) -> None:
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
    assert not verdict.reusable
    assert "disabled" in verdict.reason


def test_compatibility_loader_never_returns_same_uid_credential(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    payload = json.loads(path.read_text(encoding="utf-8"))

    loaded = validation_credential.load_reusable_credential(
        path,
        payload,
        now=1_100,
    )

    assert loaded is None


def test_credential_git_queries_ignore_inherited_config_rewrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/tmp/attacker-worktree")
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.bare'='true'")

    assert validation_credential._run_text(
        ["git", "rev-parse", "--show-toplevel"], cwd=repo
    ) == str(repo)


def test_toolchain_collection_scrubs_node_and_npm_execution_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    poison = tmp_path / "exit-zero.js"
    poison.write_text("process.exit(0);\n", encoding="utf-8")
    monkeypatch.setenv("NODE_OPTIONS", f"--require={poison}")
    monkeypatch.setenv("Npm_Config_Script-Shell", "/usr/bin/true")

    toolchain = validation_credential.collect_toolchain(repo, profile="structural")

    assert toolchain["node"] != "__missing__"
    assert toolchain["npm"] != "__missing__"


def test_issue_cli_cannot_turn_caller_supplied_log_into_pass_credential(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    log = validation_state_dir(repo) / "caller-written.log"
    log.write_text("I claim the suite passed\n", encoding="utf-8")
    log.chmod(0o600)
    commands = tmp_path / "commands.json"
    logs = tmp_path / "logs.json"
    toolchain = tmp_path / "toolchain.json"
    dependencies = tmp_path / "dependencies.json"
    environment = tmp_path / "environment.json"
    commands.write_text(json.dumps(COMMANDS), encoding="utf-8")
    logs.write_text(json.dumps({"mobile:lint": str(log)}), encoding="utf-8")
    toolchain.write_text(json.dumps(TOOLCHAIN), encoding="utf-8")
    dependencies.write_text(
        json.dumps({"mobile": "c" * 64}), encoding="utf-8"
    )
    environment.write_text(json.dumps(VALIDATION_ENVIRONMENT), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(validation_credential.__file__).resolve()),
            "issue",
            "--repo",
            str(repo),
            "--profile",
            "mobile",
            "--commands-json",
            str(commands),
            "--logs-json",
            str(logs),
            "--toolchain-json",
            str(toolchain),
            "--dependency-state-json",
            str(dependencies),
            "--validation-environment-json",
            str(environment),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert not credential_path(repo, "mobile").exists()


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


@pytest.mark.parametrize("component", ["backend", "frontend", "mobile"])
def test_reuse_fails_when_installed_dependency_state_changes(
    tmp_path: Path,
    component: str,
) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    changed = {**DEPENDENCY_STATE, component: "d" * 64}

    verdict = _verify(repo, path, dependency_state=changed)

    assert not verdict.reusable
    assert "dependency" in verdict.reason


def test_reuse_fails_when_canonical_validation_environment_changes(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)

    verdict = _verify(
        repo,
        path,
        validation_environment={**VALIDATION_ENVIRONMENT, "TZ": "UTC"},
    )

    assert not verdict.reusable
    assert "environment" in verdict.reason


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


@pytest.mark.parametrize("unsafe_kind", ["permissions", "owner"])
def test_validation_state_directory_rejects_unsafe_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_kind: str,
) -> None:
    repo = _init_repo(tmp_path)
    state_dir = validation_state_dir(repo)
    if unsafe_kind == "permissions":
        state_dir.chmod(0o755)
        expected = "0700"
    else:
        monkeypatch.setattr(os, "getuid", lambda: state_dir.stat().st_uid + 1)
        expected = "owner"

    with pytest.raises(ValueError, match=expected):
        validation_state_dir(repo)


@pytest.mark.parametrize("target", ["credential", "log"])
@pytest.mark.parametrize("unsafe_kind", ["owner_executable", "hardlink"])
def test_credential_reuse_rejects_unsafe_proof_inode_metadata(
    tmp_path: Path,
    target: str,
    unsafe_kind: str,
) -> None:
    repo = _init_repo(tmp_path)
    path, log = _issue(repo)
    unsafe = path if target == "credential" else log
    if unsafe_kind == "owner_executable":
        unsafe.chmod(0o700)
    else:
        os.link(unsafe, unsafe.with_name(f"{unsafe.name}.hardlink"))

    verdict = _verify(repo, path)

    assert not verdict.reusable
    assert "0600" in verdict.reason or "hard link" in verdict.reason


def test_credential_reuse_rejects_foreign_owned_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    monkeypatch.setattr(os, "getuid", lambda: path.stat().st_uid + 1)

    verdict = _verify(repo, path)

    assert not verdict.reusable
    assert "owner" in verdict.reason


@pytest.mark.parametrize("unsafe_kind", ["owner_executable", "hardlink", "owner"])
def test_credential_write_rejects_unsafe_existing_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_kind: str,
) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    credential = json.loads(path.read_text(encoding="utf-8"))
    if unsafe_kind == "owner_executable":
        path.chmod(0o700)
        expected = "0600"
    elif unsafe_kind == "hardlink":
        os.link(path, tmp_path / "credential-external-link.json")
        expected = "hard link"
    else:
        monkeypatch.setattr(os, "getuid", lambda: path.stat().st_uid + 1)
        expected = "owner"

    with pytest.raises(ValueError, match=expected):
        write_credential_atomic(path, credential)


def test_credential_read_does_not_follow_a_path_replaced_after_metadata_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    path, _ = _issue(repo)
    original = json.loads(path.read_text(encoding="utf-8"))
    original["read_marker"] = "original"
    path.write_text(json.dumps(original), encoding="utf-8")
    path.chmod(0o600)
    replacement = tmp_path / "replacement.json"
    replacement.write_text(json.dumps({"read_marker": "replacement"}), encoding="utf-8")
    replacement.chmod(0o600)
    saved = tmp_path / "saved-original.json"
    real_read_text = Path.read_text
    replaced = False

    def replace_before_path_read(candidate: Path, *args, **kwargs):
        nonlocal replaced
        if candidate == path and not replaced:
            replaced = True
            path.rename(saved)
            path.symlink_to(replacement)
        return real_read_text(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", replace_before_path_read)

    loaded = validation_credential._read_stored(path)

    assert loaded.reusable
    assert loaded.credential is not None
    assert loaded.credential["read_marker"] == "original"


def test_log_digest_does_not_follow_a_path_replaced_after_metadata_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    log = validation_state_dir(repo) / "trusted.log"
    trusted_bytes = b"trusted validation output\n"
    log.write_bytes(trusted_bytes)
    log.chmod(0o600)
    replacement = tmp_path / "replacement.log"
    replacement.write_bytes(b"attacker-controlled output\n")
    replacement.chmod(0o600)
    saved = tmp_path / "saved-trusted.log"
    real_open = Path.open
    replaced = False

    def replace_before_path_open(candidate: Path, *args, **kwargs):
        nonlocal replaced
        if candidate == log and not replaced:
            replaced = True
            log.rename(saved)
            log.symlink_to(replacement)
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replace_before_path_open)

    credential = build_credential(
        repo=repo,
        profile_name="mobile",
        profile_version="1",
        commands=COMMANDS,
        logs={"mobile:lint": log},
        ttl_seconds=600,
        now=1_000,
        toolchain=TOOLCHAIN,
        dependency_state={"mobile": "c" * 64},
        validation_environment=VALIDATION_ENVIRONMENT,
    )

    assert credential["logs"]["mobile:lint"]["sha256"] == hashlib.sha256(
        trusted_bytes
    ).hexdigest()


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
            dependency_state={"mobile": "c" * 64},
            validation_environment=VALIDATION_ENVIRONMENT,
        )
