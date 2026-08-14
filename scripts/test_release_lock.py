import importlib.util
import json
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LOCK_HELPER = ROOT / "scripts" / "release_lock.sh"
RELEASE_SCRIPT = ROOT / "scripts" / "release.py"
TESTFLIGHT_HELPER = ROOT / "scripts" / "_run-mobile-tf.sh"
TESTFLIGHT_SOURCE_FOR_TESTS = (
    "unset EXPO_TOKEN ASC_API_KEY_PATH ASC_API_KEY_ID ASC_API_ISSUER_ID; "
    f"eval \"$(/usr/bin/sed -n "
    f"'/^# BEGIN UNREACHABLE LEGACY TESTFLIGHT IMPLEMENTATION$/,/^# END UNREACHABLE LEGACY TESTFLIGHT IMPLEMENTATION$/p' "
    f"{TESTFLIGHT_HELPER!s} | /usr/bin/sed "
    f"'s|${{BASH_SOURCE\\[0\\]}}|{TESTFLIGHT_HELPER!s}|g')\"; "
    f"ROOT={ROOT!s}; "
    f"EAS_TOOL_MANIFEST_DIR={ROOT / 'scripts/eas-cli-tool'!s}; "
    f"LOCKED_EAS_HELPER={ROOT / 'scripts/locked_eas_cli.py'!s}; "
    f"MOBILE_OTA={ROOT / 'scripts/mobile-ota.sh'!s}; "
    "ssh() { return 97; }; scp() { return 97; }; rsync() { return 97; }"
)


def _release_module():
    spec = importlib.util.spec_from_file_location("reva_release_lock_test", RELEASE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    return repo


def _lock_path(repo: Path) -> Path:
    return _common_dir(repo) / "reva-release-state" / "release-publish.lock"


def _common_dir(repo: Path) -> Path:
    return Path(
        _git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    )


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("REVA_RELEASE_LOCK_ADOPT", None)
    env.pop("REVA_RELEASE_LOCK_FD", None)
    env.pop("REVA_RELEASE_LOCK_TOKEN", None)
    env.pop("REVA_RELEASE_LOCK_DIR", None)
    return env


def _isolated_testflight_qr_wrapper(tmp_path: Path) -> Path:
    node_binary = shutil.which("node")
    assert node_binary is not None, "release invariant suite requires Node.js"

    fixture_scripts = tmp_path / "testflight-qr-fixture" / "scripts"
    fixture_scripts.mkdir(parents=True)
    fake_qrencode = fixture_scripts / "qrencode"
    fake_qrencode.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'if [ "${1:-}" = "-o" ]; then\n'
        '  printf "fixture-png" > "$2"\n'
        "else\n"
        '  printf "fixture-ansi\\n"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_qrencode.chmod(0o700)

    source = (ROOT / "scripts" / "testflight-qr.sh").read_text(
        encoding="utf-8"
    )
    assert 'NODE_BINARY="/usr/local/bin/node"' in source
    assert 'QRENCODE_BINARY="/opt/homebrew/bin/qrencode"' in source
    wrapper = fixture_scripts / "testflight-qr.sh"
    wrapper.write_text(
        source.replace(
            'NODE_BINARY="/usr/local/bin/node"',
            f"NODE_BINARY={shlex.quote(node_binary)}",
        ).replace(
            'QRENCODE_BINARY="/opt/homebrew/bin/qrencode"',
            f"QRENCODE_BINARY={shlex.quote(str(fake_qrencode))}",
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    shutil.copyfile(
        ROOT / "scripts" / "testflight-public-link.mjs",
        fixture_scripts / "testflight-public-link.mjs",
    )
    return wrapper


def _bash(
    script: str,
    *,
    env: dict[str, str] | None = None,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env=env or _clean_env(),
        text=True,
        capture_output=True,
        check=False,
        pass_fds=pass_fds,
    )


def _write_shell_entrypoint(repo: Path, body: str, *, name: str) -> Path:
    script = repo / name
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f'source "{LOCK_HELPER}"\n'
        f'_REVA_RELEASE_REPO_ROOT="{repo}"\n'
        + body,
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def _start_shell_owner(repo: Path) -> subprocess.Popen[str]:
    script = _write_shell_entrypoint(
        repo,
        'acquire_release_lock "owner"\necho READY\nread -r _\n',
        name="owner.sh",
    )
    owner = subprocess.Popen(
        [str(script)],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert owner.stdout is not None
    ready = owner.stdout.readline().strip()
    if ready != "READY":
        assert owner.stderr is not None
        pytest.fail(owner.stderr.read() or f"shell lock owner did not start: {ready!r}")
    return owner


def test_shell_guardian_restarts_no_argument_entrypoint_under_nounset(
    repository: Path,
) -> None:
    script = repository / "no-args.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'source "{LOCK_HELPER}"\n'
        f'_REVA_RELEASE_REPO_ROOT="{repository}"\n'
        'acquire_release_lock "no-args"\n'
        'printf READY\n',
        encoding="utf-8",
    )
    script.chmod(0o700)

    result = subprocess.run(
        [str(script)],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "READY"


def _stop_shell_owner(owner: subprocess.Popen[str]) -> None:
    assert owner.stdin is not None
    owner.stdin.write("done\n")
    owner.stdin.flush()
    owner.wait(timeout=5)


def test_python_planner_lock_blocks_direct_shell_publisher(repository: Path):
    release = _release_module()

    with release.release_publish_lock(repository) as lease:
        contender = _bash(
            (
                f'source "{LOCK_HELPER}"; '
                f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
                'acquire_release_lock "shell-contender"'
            )
        )

        assert lease.fd >= 3
        assert contender.returncode == 73
        assert "发布任务正在执行" in contender.stderr


def test_direct_shell_lock_blocks_python_planner(repository: Path):
    release = _release_module()
    owner = _start_shell_owner(repository)
    try:
        with pytest.raises(release.ReleaseError, match="already active"):
            with release.release_publish_lock(repository):
                raise AssertionError("the Python planner must not enter")
    finally:
        _stop_shell_owner(owner)


def test_shell_and_python_contend_across_git_worktrees(
    repository: Path,
    tmp_path: Path,
):
    release = _release_module()
    _git(repository, "config", "user.email", "release@example.test")
    _git(repository, "config", "user.name", "Release Test")
    (repository / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-qm", "initial")
    worktree = tmp_path / "other-worktree"
    _git(repository, "worktree", "add", "-q", "-b", "other", str(worktree))

    owner = _start_shell_owner(worktree)
    try:
        assert _lock_path(repository) == _lock_path(worktree)
        with pytest.raises(release.ReleaseError, match="already active"):
            with release.release_publish_lock(repository):
                raise AssertionError("worktrees must share one release lock")
    finally:
        _stop_shell_owner(owner)


def test_python_owner_allows_only_the_explicit_inherited_shell_child(
    repository: Path,
):
    release = _release_module()

    with release.release_publish_lock(repository) as lease:
        inherited_env = _clean_env()
        inherited_env["REVA_RELEASE_LOCK_ADOPT"] = "1"
        inherited_env["REVA_RELEASE_LOCK_FD"] = str(lease.fd)
        inherited = _bash(
            (
                f'source "{LOCK_HELPER}"; '
                f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
                'acquire_release_lock "inherited-child"; release_release_lock'
            ),
            env=inherited_env,
            pass_fds=(lease.fd,),
        )

    assert inherited.returncode == 0, inherited.stdout + inherited.stderr


def test_same_uid_cannot_adopt_by_reopening_the_authority_directory(
    repository: Path,
):
    release = _release_module()

    with release.release_publish_lock(repository):
        forged_fd = os.open(_common_dir(repository), os.O_RDONLY)
        try:
            forged_env = _clean_env()
            forged_env["REVA_RELEASE_LOCK_ADOPT"] = "1"
            forged_env["REVA_RELEASE_LOCK_FD"] = str(forged_fd)
            result = _bash(
                (
                    f'source "{LOCK_HELPER}"; '
                    f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
                    'acquire_release_lock "forged-child"'
                ),
                env=forged_env,
                pass_fds=(forged_fd,),
            )
        finally:
            os.close(forged_fd)

    assert result.returncode == 73
    assert "继承发布锁失败" in result.stderr


def test_stolen_legacy_token_without_an_inherited_fd_is_rejected(
    repository: Path,
):
    stolen_env = _clean_env()
    stolen_env["REVA_RELEASE_LOCK_ADOPT"] = "1"
    stolen_env["REVA_RELEASE_LOCK_TOKEN"] = "a" * 64

    result = _bash(
        (
            f'source "{LOCK_HELPER}"; '
            f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
            'acquire_release_lock "stolen-token"'
        ),
        env=stolen_env,
    )

    assert result.returncode == 73
    assert "继承发布锁失败" in result.stderr


def test_adoption_rejects_a_separately_opened_fd_when_no_owner_exists(
    repository: Path,
):
    release = _release_module()
    with release.release_publish_lock(repository):
        pass
    stale_fd = os.open(_common_dir(repository), os.O_RDONLY)
    try:
        stale_env = _clean_env()
        stale_env["REVA_RELEASE_LOCK_ADOPT"] = "1"
        stale_env["REVA_RELEASE_LOCK_FD"] = str(stale_fd)
        result = _bash(
            (
                f'source "{LOCK_HELPER}"; '
                f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
                'acquire_release_lock "stale-fd"'
            ),
            env=stale_env,
            pass_fds=(stale_fd,),
        )
    finally:
        os.close(stale_fd)

    assert result.returncode == 73
    assert "继承发布锁失败" in result.stderr


def test_adoption_rejects_an_inherited_fd_for_the_wrong_inode(
    repository: Path,
    tmp_path: Path,
):
    release = _release_module()
    wrong_path = tmp_path / "wrong-directory"
    wrong_path.mkdir()
    with release.release_publish_lock(repository):
        wrong_fd = os.open(wrong_path, os.O_RDONLY)
        try:
            wrong_env = _clean_env()
            wrong_env["REVA_RELEASE_LOCK_ADOPT"] = "1"
            wrong_env["REVA_RELEASE_LOCK_FD"] = str(wrong_fd)
            result = _bash(
                (
                    f'source "{LOCK_HELPER}"; '
                    f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
                    'acquire_release_lock "wrong-inode"'
                ),
                env=wrong_env,
                pass_fds=(wrong_fd,),
            )
        finally:
            os.close(wrong_fd)

    assert result.returncode == 73
    assert "继承发布锁失败" in result.stderr


def test_invalid_inherited_descriptor_fails_closed_with_adoption_status(
    repository: Path,
):
    script = _write_shell_entrypoint(
        repository,
        'acquire_release_lock "invalid-adoption"\necho MUST_NOT_CONTINUE\n',
        name="invalid-adoption.sh",
    )
    inherited_env = _clean_env()
    inherited_env["REVA_RELEASE_LOCK_ADOPT"] = "1"
    inherited_env["REVA_RELEASE_LOCK_FD"] = "999"

    result = subprocess.run(
        [str(script)],
        cwd=ROOT,
        env=inherited_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 73
    assert "MUST_NOT_CONTINUE" not in result.stdout
    assert "继承发布锁失败" in result.stderr


def test_shell_owner_rejects_an_unverified_nested_child_and_leaves_private_file(
    repository: Path,
):
    script = _write_shell_entrypoint(
        repository,
        (
            'acquire_release_lock "outer"\n'
            f'bash -c \'source "{LOCK_HELPER}"; '
            f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
            'acquire_release_lock "inner"\'\n'
            'release_release_lock\n'
        ),
        name="nested.sh",
    )
    result = subprocess.run(
        [str(script)],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )

    lock_path = _lock_path(repository)
    assert result.returncode == 73, result.stdout + result.stderr
    assert "发布任务正在执行" in result.stderr
    assert stat.S_IMODE(lock_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
    assert lock_path.stat().st_nlink == 1


def test_replacing_the_owner_audit_file_cannot_create_a_second_lock(
    repository: Path,
):
    release = _release_module()
    lock_path = _lock_path(repository)

    with release.release_publish_lock(repository):
        moved_path = lock_path.with_name("moved-owner-audit.json")
        lock_path.rename(moved_path)
        lock_path.write_text("{}\n", encoding="utf-8")
        lock_path.chmod(0o600)

        with pytest.raises(release.ReleaseError, match="already active"):
            with release.release_publish_lock(repository):
                raise AssertionError("a replacement audit inode must not create a lock")


def test_adopted_shell_cannot_unlock_the_guardian_lock(
    repository: Path,
):
    release = _release_module()

    with release.release_publish_lock(repository) as lease:
        inherited_env = _clean_env()
        inherited_env["REVA_RELEASE_LOCK_ADOPT"] = "1"
        inherited_env["REVA_RELEASE_LOCK_FD"] = str(lease.fd)
        adopted = _bash(
            (
                f'source "{LOCK_HELPER}"; '
                f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
                'export ATTACK_FD="$REVA_RELEASE_LOCK_FD"; '
                'acquire_release_lock "adopted-child"; '
                'if [[ -n "${REVA_RELEASE_LOCK_ADOPT+x}" || '
                '-n "${REVA_RELEASE_LOCK_FD+x}" ]]; then '
                'echo ADOPTION_ENV_LEAKED; fi; '
                'python3 - <<\'PY\'\n'
                'import fcntl\n'
                'import os\n'
                '\n'
                'try:\n'
                '    fcntl.flock(int(os.environ["ATTACK_FD"]), fcntl.LOCK_UN)\n'
                'except OSError:\n'
                '    print("FD_CLOSED")\n'
                'else:\n'
                '    print("FD_UNLOCKED")\n'
                'PY\n'
            ),
            env=inherited_env,
            pass_fds=(lease.fd,),
        )

        assert adopted.returncode == 0, adopted.stdout + adopted.stderr
        assert "FD_CLOSED" in adopted.stdout
        assert "FD_UNLOCKED" not in adopted.stdout
        assert "ADOPTION_ENV_LEAKED" not in adopted.stdout
        with pytest.raises(release.ReleaseError, match="already active"):
            with release.release_publish_lock(repository):
                raise AssertionError("the guardian must remain the exclusive lock owner")


def test_shell_owner_exit_releases_lock_even_when_a_descendant_outlives_it(
    repository: Path,
):
    owner_script = _write_shell_entrypoint(
        repository,
        'acquire_release_lock "short-owner"\n/bin/sleep 1.5 &\n',
        name="short-owner.sh",
    )
    owner = subprocess.run(
        [str(owner_script)],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert owner.returncode == 0, owner.stdout + owner.stderr

    next_script = _write_shell_entrypoint(
        repository,
        'acquire_release_lock "next-owner"\nrelease_release_lock\n',
        name="next-owner.sh",
    )
    contender = subprocess.run(
        [str(next_script)],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if contender.returncode != 0:
        time.sleep(1.6)

    assert contender.returncode == 0, contender.stdout + contender.stderr


def test_python_guardian_forwards_term_and_returns_shell_signal_status(
    repository: Path,
    tmp_path: Path,
):
    child_pid_path = tmp_path / "child.pid"
    event_path = tmp_path / "events.log"
    entrypoint = _write_shell_entrypoint(
        repository,
        (
            'acquire_release_lock "signal-owner"\n'
            f'printf "%s\\n" "$$" > "{child_pid_path}"\n'
            f'printf "READY\\n" > "{event_path}"\n'
            'while :; do :; done\n'
            f'printf "CONTINUED\\n" >> "{event_path}"\n'
        ),
        name="signal-owner.sh",
    )
    guardian = subprocess.Popen(
        [str(entrypoint)],
        cwd=ROOT,
        env=_clean_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    child_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if child_pid_path.exists() and event_path.exists():
                child_pid = int(child_pid_path.read_text(encoding="utf-8").strip())
                break
            if guardian.poll() is not None:
                break
            time.sleep(0.02)
        assert child_pid is not None, "release guardian child never became ready"

        guardian.terminate()
        returncode = guardian.wait(timeout=5)
        time.sleep(0.1)

        assert returncode == 143
        assert event_path.read_text(encoding="utf-8") == "READY\n"
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if guardian.poll() is None:
            guardian.kill()
            guardian.wait(timeout=5)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_shell_preflight_failure_releases_lock_before_the_next_invocation(
    repository: Path,
):
    failed_script = _write_shell_entrypoint(
        repository,
        'acquire_release_lock "failing-preflight"\nexit 19\n',
        name="failed-preflight.sh",
    )
    failed = subprocess.run(
        [str(failed_script)],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert failed.returncode == 19, failed.stdout + failed.stderr

    next_script = _write_shell_entrypoint(
        repository,
        'acquire_release_lock "after-failure"\nrelease_release_lock\n',
        name="after-failure.sh",
    )
    next_invocation = subprocess.run(
        [str(next_script)],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert next_invocation.returncode == 0, (
        next_invocation.stdout + next_invocation.stderr
    )


@pytest.mark.parametrize(
    "unsafe_kind",
    [
        "symlink",
        "permissions",
        "hardlink",
        "directory-symlink",
        "directory-permissions",
    ],
)
def test_shell_lock_refuses_unsafe_lock_file(
    repository: Path,
    tmp_path: Path,
    unsafe_kind: str,
):
    lock_path = _lock_path(repository)
    if unsafe_kind == "directory-symlink":
        state_target = tmp_path / "state-target"
        state_target.mkdir(mode=0o700)
        lock_path.parent.symlink_to(state_target, target_is_directory=True)
    else:
        lock_path.parent.mkdir(mode=0o700)
    if unsafe_kind == "directory-permissions":
        lock_path.parent.chmod(0o755)
    target = tmp_path / "target"
    target.write_text("unsafe\n", encoding="utf-8")
    target.chmod(0o600)
    if unsafe_kind.startswith("directory-"):
        pass
    elif unsafe_kind == "symlink":
        lock_path.symlink_to(target)
    elif unsafe_kind == "hardlink":
        os.link(target, lock_path)
    else:
        lock_path.write_text("unsafe\n", encoding="utf-8")
        lock_path.chmod(0o644)

    result = _bash(
        (
            f'source "{LOCK_HELPER}"; '
            f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
            'acquire_release_lock "unsafe"'
        )
    )

    assert result.returncode == 70
    assert "发布锁路径不安全" in result.stderr


def test_release_lock_resolves_one_common_git_file_when_started_outside_repo(
    repository: Path,
    tmp_path: Path,
):
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f'source "{LOCK_HELPER}"; '
                f'_REVA_RELEASE_REPO_ROOT="{repository}"; '
                'resolved="$(_release_lock_path)"; '
                f'test "$resolved" = "{_lock_path(repository)}"'
            ),
        ],
        cwd=tmp_path,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_release_lock_common_dir_ignores_path_and_git_exec_environment(
    repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    expected_common = _common_dir(repository)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-git-called"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        f"#!/bin/sh\nprintf called > {marker!s}\nexit 91\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_exec = tmp_path / "git-exec"
    fake_exec.mkdir()
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("GIT_EXEC_PATH", str(fake_exec))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "poison.gitconfig"))

    assert release.release_lock.git_common_dir(repository) == expected_common
    assert not marker.exists()
    environment = release.release_lock._git_environment()
    assert environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert "GIT_EXEC_PATH" not in environment
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"


def test_release_lock_shell_uses_fixed_python_not_path(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-python-called"
    for name in ("python3", "python3.12"):
        fake = fake_bin / name
        fake.write_text(
            f"#!/bin/sh\nprintf called > {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)

    result = _bash(
        f'source "{LOCK_HELPER}"; _release_lock_python',
        env={**_clean_env(), "PATH": f"{fake_bin}:/bin:/usr/bin"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "/usr/bin/python3"
    assert not marker.exists()


def test_mutating_release_entrypoints_use_the_shared_lock():
    deploy = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    ota = (ROOT / "scripts" / "mobile-ota.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "scripts" / "mobile-ota-rollback.sh").read_text(encoding="utf-8")
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(encoding="utf-8")

    assert "scripts/release_lock.sh" in deploy
    assert 'acquire_release_lock "deploy:${DEPLOY_MODE}"' in deploy
    assert "scripts/release_lock.sh" in ota
    assert 'acquire_release_lock "ota:${CHANNEL}"' in ota
    assert "scripts/release_lock.sh" in rollback
    assert 'acquire_release_lock "ota-rollback:${CHANNEL}"' in rollback
    assert "scripts/release_lock.sh" in testflight
    assert 'acquire_release_lock "testflight:remote"' in testflight


def test_testflight_helper_has_no_raw_ota_bypass_and_pins_eas_cli():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )

    assert 'MOBILE_OTA="${ROOT}/scripts/mobile-ota.sh"' in testflight
    assert '[ -x "${MOBILE_OTA}" ]' in testflight
    assert 'exec "${MOBILE_OTA}" production "${message}"' in testflight
    assert "npx eas-cli update --branch production" not in testflight
    assert 'EAS_CLI_VERSION="21.8.0"' in testflight
    assert '"${EAS_BINARY}" build' in testflight
    assert "npx" not in testflight.lower()


def test_testflight_eas_cli_is_installed_from_an_integrity_locked_manifest():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )
    manifest_path = ROOT / "scripts" / "eas-cli-tool" / "package.json"
    lock_path = ROOT / "scripts" / "eas-cli-tool" / "package-lock.json"

    assert manifest_path.is_file()
    assert lock_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert manifest["private"] is True
    assert manifest["dependencies"] == {
        "eas-cli": "21.8.0",
        "typescript": "5.9.3",
    }
    assert lock["packages"][""]["dependencies"] == manifest["dependencies"]
    assert lock["packages"]["node_modules/eas-cli"]["version"] == "21.8.0"
    assert lock["packages"]["node_modules/typescript"]["version"] == "5.9.3"
    assert lock["packages"]["node_modules/eas-cli"]["integrity"].startswith(
        "sha512-"
    )
    assert 'LOCKED_EAS_HELPER="${ROOT}/scripts/locked_eas_cli.py"' in testflight
    assert '"${PYTHON_BINARY}" "${LOCKED_EAS_HELPER}" prepare' in testflight
    assert '--repo-root "${ROOT}"' in testflight
    assert '"${PYTHON_BINARY}" "${LOCKED_EAS_HELPER}" cleanup' in testflight
    assert 'EAS_BINARY="${prepared_output#*$' in testflight
    assert "npx --yes" not in testflight


def test_testflight_remote_build_does_not_auto_submit_to_app_store_connect():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )
    app_store_check = (ROOT / "scripts" / "check_ios_app_store_submission.py").read_text(
        encoding="utf-8"
    )

    assert "--profile production" in testflight
    assert "--auto-submit" not in testflight
    assert "must not auto-submit" in app_store_check


def test_testflight_remote_build_is_hard_disabled_before_any_external_action():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )
    remote_body = testflight.split("run_remote_build() {", 1)[1].split(
        "\n}\n\nmain()", 1
    )[0]

    assert 'fail "自动原生 production 构建已冻结' in remote_body
    disabled_at = remote_body.index('fail "自动原生 production 构建已冻结')
    for marker in (
        "acquire_release_lock",
        "assert_exact_remote_main_source",
        "prepare_locked_eas_cli",
        '"${EAS_BINARY}" build',
    ):
        assert marker not in remote_body[:disabled_at]

    result = subprocess.run(
        [str(ROOT / "scripts" / "_run-mobile-tf.sh"), "remote"],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "手工 Gate" in result.stderr
    assert "尚未创建 EAS 构建" in result.stderr


@pytest.mark.parametrize("mode", ("remote", "ota", "local-archive", "unknown"))
def test_testflight_production_entrypoint_freezes_before_path_resolution(
    mode: str,
) -> None:
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )

    freeze = testflight.index("Automated production Mobile release entrypoint is frozen")
    root_resolution = testflight.index('ROOT="')
    assert freeze < root_resolution

    result = subprocess.run(
        [str(ROOT / "scripts" / "_run-mobile-tf.sh"), mode],
        cwd=ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 78
    assert "manual native/App Review Gate" in result.stderr


def test_sourcing_testflight_entrypoint_is_inert_before_caller_or_tools(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "external-called"
    after = tmp_path / "after"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("dirname", "git", "python3", "eas"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
    completed = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"set -- remote; source {TESTFLIGHT_HELPER!s}; printf AFTER > {after!s}",
        ],
        cwd=tmp_path,
        env={"PATH": str(fake_bin), "EXPO_TOKEN": "must-not-leak"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "must-not-leak" not in completed.stdout + completed.stderr
    assert after.read_text(encoding="utf-8") == "AFTER"
    assert not marker.exists()


def test_hostile_source_cannot_reach_testflight_legacy_when_builtins_are_shadowed(
    tmp_path: Path,
) -> None:
    tool_marker = tmp_path / "external-called"
    function_marker = tmp_path / "legacy-function-loaded"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("dirname", "git", "python3", "eas"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {tool_marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
    harness = f"""
set -- remote
exit() {{ return 0; }}
builtin() {{ return 0; }}
printf() {{ return 0; }}
set() {{ return 0; }}
source {TESTFLIGHT_HELPER!s}
if declare -F run_remote_build >/dev/null; then
  : > {function_marker!s}
fi
"""
    completed = subprocess.run(
        ["/bin/bash", "-c", harness],
        cwd=tmp_path,
        env={"PATH": str(fake_bin), "EXPO_TOKEN": "must-not-read"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert not tool_marker.exists()
    assert not function_marker.exists()


def test_testflight_ota_wrapper_executes_only_the_controlled_ota_entrypoint():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )

    ota_case = testflight.split("ota)", 1)[1].split(";;", 1)[0]
    assert 'exec "${MOBILE_OTA}" production "${message}"' in ota_case
    assert "acquire_release_lock" not in ota_case
    assert "tee" not in ota_case


def test_testflight_native_submission_requires_clean_exact_remote_main():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )

    assert "assert_exact_remote_main_source()" in testflight
    assert '"${GIT_BINARY}" -C "${ROOT}" status --porcelain --untracked-files=all' in testflight
    assert '"${GIT_BINARY}" -C "${ROOT}" fetch --quiet' in testflight
    assert "'+refs/heads/main:refs/remotes/origin/main'" in testflight
    assert 'CANONICAL_ORIGIN_URL="https://github.com/itsoso/health-llm-driven.git"' in testflight
    assert "remote.origin.url" in testflight
    assert "remote.origin.pushurl" in testflight
    assert "insteadOf|pushInsteadOf" in testflight
    assert '"${GIT_BINARY}" -C / ls-remote --exit-code' in testflight
    assert '"${CANONICAL_ORIGIN_URL}" refs/heads/main' in testflight
    assert "GIT_CONFIG_NOSYSTEM=1" in testflight
    assert 'GIT_CONFIG_GLOBAL="${empty_git_config}"' in testflight
    assert '"${GIT_BINARY}" -C "${ROOT}" symbolic-ref --quiet --short HEAD' in testflight
    assert 'assert_exact_remote_main_source "remote"' in testflight
    assert "工作树非干净" not in testflight


def test_testflight_source_guard_rejects_wrong_origin_and_url_rewrites(
    tmp_path: Path,
):
    helper = ROOT / "scripts" / "_run-mobile-tf.sh"
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "README.md").write_text("source\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "init",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://attacker.example/repo.git"],
        cwd=repo,
        check=True,
    )

    wrong_origin = subprocess.run(
        [
            "/bin/bash",
            "-c",
            (
                f'{TESTFLIGHT_SOURCE_FOR_TESTS}; ROOT="{repo}"; '
                'assert_exact_remote_main_source remote'
            ),
        ],
        text=True,
        capture_output=True,
        env=_clean_env(),
        check=False,
    )
    subprocess.run(
        [
            "git",
            "remote",
            "set-url",
            "origin",
            "https://github.com/itsoso/health-llm-driven.git",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "url.https://attacker.example/.insteadOf",
            "https://github.com/",
        ],
        cwd=repo,
        check=True,
    )
    rewrite = subprocess.run(
        [
            "/bin/bash",
            "-c",
            (
                f'{TESTFLIGHT_SOURCE_FOR_TESTS}; ROOT="{repo}"; '
                'assert_exact_remote_main_source remote'
            ),
        ],
        text=True,
        capture_output=True,
        env=_clean_env(),
        check=False,
    )

    assert wrong_origin.returncode != 0
    assert "canonical origin" in wrong_origin.stderr
    assert rewrite.returncode != 0
    assert "URL rewrite" in rewrite.stderr


def test_testflight_helper_uses_private_paths_and_sanitized_npm_config():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )
    locked_eas = (ROOT / "scripts" / "locked_eas_cli.py").read_text(
        encoding="utf-8"
    )

    assert "umask 077" in testflight
    assert '"${MKTEMP_BINARY}" -d "${TMPDIR:-/tmp}/reva-testflight.XXXXXX"' in testflight
    assert "/tmp/run-mobile-tf-" not in testflight
    assert 'NPM_CONFIG_USERCONFIG": str(workspace / "npm-user.conf")' in locked_eas
    assert 'NPM_CONFIG_GLOBALCONFIG": str(workspace / "npm-global.conf")' in locked_eas
    assert 'NPM_CONFIG_IGNORE_SCRIPTS": "true"' in locked_eas
    assert testflight.count("/usr/bin/env -i") >= 2
    assert 'GIT_BINARY="/usr/bin/git"' in testflight
    assert 'PYTHON_BINARY="/usr/local/bin/python3"' in testflight
    assert 'NPM_BINARY = Path("/usr/local/bin/npm")' in locked_eas
    assert 'NODE_BINARY = Path("/usr/local/bin/node")' in locked_eas
    assert 'SAFE_TOOL_PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"' in testflight
    assert "git -C" not in testflight
    assert " npx " not in testflight
    assert "| tee " not in testflight


def test_testflight_tooling_ignores_hostile_path_with_isolated_interpreter(
    tmp_path: Path,
):
    helper = ROOT / "scripts" / "_run-mobile-tf.sh"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-npm-ran"
    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        f'#!/bin/sh\nprintf PWNED > "{marker}"\n',
        encoding="utf-8",
    )
    fake_npm.chmod(0o700)

    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            (
                f'PATH="{fake_bin}"; {TESTFLIGHT_SOURCE_FOR_TESTS}; '
                f'PYTHON_BINARY={shlex.quote(sys.executable)}; '
                'assert_testflight_tooling; '
                'printf "%s\\n" "${PYTHON_BINARY}"'
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == sys.executable
    assert not marker.exists()


def test_testflight_public_qr_is_local_only_and_cannot_mutate_asc():
    public_link = (ROOT / "scripts" / "testflight-public-link.mjs").read_text(
        encoding="utf-8"
    )
    qr_wrapper = (ROOT / "scripts" / "testflight-qr.sh").read_text(
        encoding="utf-8"
    )
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    for source in (public_link, qr_wrapper):
        assert "betaGroups" not in source
        assert "APP_STORE_CONNECT" not in source
        assert "ASC_PRIVATE_KEY" not in source
        assert "api.qrserver.com" not in source
    assert "fetch(" not in public_link
    assert 'process.env.TESTFLIGHT_PUBLIC_LINK' in public_link
    assert 'src="./qr.png"' in public_link
    assert "TESTFLIGHT_PUBLIC_LINK" in qr_wrapper
    assert 'NODE_BINARY="/usr/local/bin/node"' in qr_wrapper
    assert 'QRENCODE_BINARY="/opt/homebrew/bin/qrencode"' in qr_wrapper
    assert "qrencode" in qr_wrapper
    assert package["scripts"]["testflight:public-link"] == "./scripts/testflight-qr.sh"


def test_testflight_public_qr_rejects_missing_or_non_apple_links(tmp_path: Path):
    wrapper = _isolated_testflight_qr_wrapper(tmp_path)
    common_env = _clean_env()
    common_env["TESTFLIGHT_OUTPUT_DIR"] = str(tmp_path / "output")

    missing = subprocess.run(
        [str(wrapper)],
        text=True,
        capture_output=True,
        env=common_env,
        check=False,
    )
    invalid = subprocess.run(
        [str(wrapper)],
        text=True,
        capture_output=True,
        env={
            **common_env,
            "TESTFLIGHT_PUBLIC_LINK": "https://attacker.example/join/AbCd1234",
        },
        check=False,
    )

    assert missing.returncode == 2
    assert invalid.returncode == 2
    assert "testflight.apple.com/join" in invalid.stderr
    assert not (tmp_path / "output" / "index.html").exists()


def test_testflight_public_qr_generates_only_local_artifacts(tmp_path: Path):
    wrapper = _isolated_testflight_qr_wrapper(tmp_path)
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [str(wrapper)],
        text=True,
        capture_output=True,
        env={
            **_clean_env(),
            "TESTFLIGHT_PUBLIC_LINK": (
                "https://testflight.apple.com/join/AbCd1234"
            ),
            "TESTFLIGHT_OUTPUT_DIR": str(output_dir),
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert (output_dir / "qr.png").stat().st_size > 0
    assert 'src="./qr.png"' in html
    assert "https://testflight.apple.com/join/AbCd1234" in html
    assert "qrserver" not in html
    assert "不会修改 ASC" in result.stdout


def test_testflight_cleanup_trap_exits_143_and_never_continues_after_term(
    tmp_path: Path,
):
    helper = ROOT / "scripts" / "_run-mobile-tf.sh"
    work_dir = tmp_path / "reva-testflight.signal"
    command = (
        f'{TESTFLIGHT_SOURCE_FOR_TESTS}; '
        f'WORK_DIR="{work_dir}"; '
        'TESTFLIGHT_WORK_DIR_CREATED=1; '
        '/bin/mkdir -m 700 "${WORK_DIR}"; '
        'install_testflight_cleanup_traps; '
        'printf "READY\\n"; '
        'while :; do /bin/sleep 0.05; done; '
        'printf "CONTINUED\\n"'
    )
    process = subprocess.Popen(
        ["/bin/bash", "-c", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_clean_env(),
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "READY"
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode == 143, stdout + stderr
    assert "CONTINUED" not in stdout
    assert not work_dir.exists()


def test_testflight_term_stops_the_managed_build_process_tree(
    tmp_path: Path,
):
    helper = ROOT / "scripts" / "_run-mobile-tf.sh"
    work_dir = tmp_path / "reva-testflight.pipeline"
    child_pid_path = tmp_path / "managed-child.pid"
    command = (
        f'{TESTFLIGHT_SOURCE_FOR_TESTS}; '
        f'WORK_DIR="{work_dir}"; '
        'TESTFLIGHT_WORK_DIR_CREATED=1; '
        '/bin/mkdir -m 700 "${WORK_DIR}"; '
        'install_testflight_cleanup_traps; '
        'run_testflight_managed_command "${WORK_DIR}/build.log" '
        f'/bin/bash -c \'printf "%s\\n" "$$" > "{child_pid_path}"; '
        'printf "MANAGED_READY\\n"; '
        'trap "exit 143" TERM; '
        'while :; do /bin/sleep 0.05; done\'; '
        'printf "BUILD_CONTINUED\\n"'
    )
    process = subprocess.Popen(
        ["/bin/bash", "-c", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_clean_env(),
    )
    child_pid: int | None = None
    try:
        assert process.stdout is not None
        deadline = time.monotonic() + 5
        output = ""
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            if line:
                output += line
            if child_pid_path.exists() and "MANAGED_READY" in output:
                child_pid = int(child_pid_path.read_text(encoding="utf-8").strip())
                break
            if process.poll() is not None:
                break
        assert child_pid is not None, output

        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        output += stdout

        assert process.returncode == 143, output + stderr
        assert "BUILD_CONTINUED" not in output
        assert not work_dir.exists()
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_testflight_helper_disables_unsafe_local_archive_fallback():
    testflight = (ROOT / "scripts" / "_run-mobile-tf.sh").read_text(
        encoding="utf-8"
    )

    assert "source \"${ROOT}/.env\"" not in testflight
    assert "/tmp/exportOptions.plist" not in testflight
    assert "/tmp/tf-export" not in testflight
    assert "xcrun altool --upload-app" not in testflight
    assert 'fail "local-archive 已禁用' in testflight


def test_legacy_mobile_local_archive_cannot_build_or_upload_directly():
    legacy = (ROOT / "scripts" / "mobile-local-archive.sh").read_text(
        encoding="utf-8"
    )

    assert "eas-cli" not in legacy
    assert "xcrun" not in legacy
    assert "altool" not in legacy
    assert 'exec "${CONTROLLED_TESTFLIGHT}" remote' in legacy


def test_legacy_native_archive_skill_cannot_upload_a_store_build_directly():
    legacy = (
        ROOT
        / ".claude"
        / "skills"
        / "mobile-testflight-release"
        / "scripts"
        / "native-archive-asc.sh"
    ).read_text(encoding="utf-8")

    assert "altool" not in legacy
    assert "--upload-app" not in legacy
    assert "APP_STORE_CONNECT_API_KEY" not in legacy
    assert "source \"${REPO}/.env\"" not in legacy
    assert 'exec "${CONTROLLED_TESTFLIGHT}" remote' in legacy


def test_no_tracked_mobile_shell_writer_can_bypass_the_controlled_build_authority():
    allowed = {
        ROOT / "scripts" / "_run-mobile-tf.sh",
        ROOT / "scripts" / "mobile-ota.sh",
        ROOT / "scripts" / "mobile-ota-rollback.sh",
    }
    forbidden_markers = (
        "--auto-submit",
        "auto-submit-with-profile",
        "altool --upload-app",
        "eas submit",
    )

    for path in tuple((ROOT / "scripts").glob("*.sh")) + tuple(
        (ROOT / ".claude" / "skills").glob("**/*.sh")
    ):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in forbidden_markers), path
