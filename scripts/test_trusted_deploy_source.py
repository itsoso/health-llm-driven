"""Exercise deploy source validation with real isolated Git repositories."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def source(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.name", "Synthetic test")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "source.txt").write_text("reviewed source\n")
    git(repo, "add", "source.txt")
    git(repo, "commit", "-m", "fixture")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "main")
    # Any push, including a no-op, must not even start a receive-pack process.
    denied = tmp_path / "deny-receive"
    denied.write_text("#!/bin/sh\necho forbidden-push >&2\nexit 93\n")
    denied.chmod(0o700)
    git(repo, "config", "remote.origin.receivepack", str(denied))
    return repo


def validate(repo, sha):
    script = (ROOT / "deploy.sh").read_text()
    body = script[script.index("push_code() {"):script.index("# 部署前端\ndeploy_frontend()")]
    command = """print_step() { :; }
print_success() { :; }
print_warning() { :; }
print_error() { echo "$*" >&2; }
compute_release_input_digests() { echo SOURCE_VALIDATED; }
""" + body + "\npush_code\n"
    return subprocess.run(
        ["/bin/bash", "-e", "-c", command], cwd=repo, text=True, capture_output=True,
        env={**os.environ, "SCRIPT_DIR": str(ROOT), "DEPLOY_SOURCE_SHA": sha},
        check=False,
    )


def test_exact_source_mode_does_not_push(source):
    result = validate(source, git(source, "rev-parse", "HEAD"))
    assert result.returncode == 0, result.stderr
    assert "SOURCE_VALIDATED" in result.stdout
    assert "forbidden-push" not in result.stderr


@pytest.mark.parametrize("sha", ["main", "a" * 39, "a" * 40, "A" * 40, "$(id)"])
def test_wrong_or_malformed_source_is_rejected_without_push(source, sha):
    result = validate(source, sha)
    assert result.returncode != 0
    assert "SOURCE_VALIDATED" not in result.stdout
    assert "forbidden-push" not in result.stderr


def test_dirty_source_rejected(source):
    (source / "source.txt").write_text("unreviewed\n")
    result = validate(source, git(source, "rev-parse", "HEAD"))
    assert result.returncode != 0
    assert "SOURCE_VALIDATED" not in result.stdout


def test_untracked_source_rejected_in_exact_mode(source):
    (source / "shadow.py").write_text("raise RuntimeError('shadow')\n")
    result = validate(source, git(source, "rev-parse", "HEAD"))
    assert result.returncode != 0
    assert "SOURCE_VALIDATED" not in result.stdout


def test_unpushed_source_rejected_without_trying_to_publish_it(source):
    (source / "source.txt").write_text("new source\n")
    git(source, "commit", "-am", "unpublished")
    result = validate(source, git(source, "rev-parse", "HEAD"))
    assert result.returncode != 0
    assert "SOURCE_VALIDATED" not in result.stdout
    assert "forbidden-push" not in result.stderr


def test_non_main_source_rejected(source):
    git(source, "switch", "-c", "other")
    result = validate(source, git(source, "rev-parse", "HEAD"))
    assert result.returncode != 0
    assert "SOURCE_VALIDATED" not in result.stdout
