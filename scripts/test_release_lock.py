import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_HELPER = ROOT / "scripts" / "release_lock.sh"


def _bash(script: str, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_lock_blocks_a_second_publisher_and_cleans_up(tmp_path: Path):
    lock_dir = tmp_path / "release.lock"
    env = os.environ.copy()
    env["REVA_RELEASE_LOCK_DIR"] = str(lock_dir)
    owner = subprocess.Popen(
        [
            "bash",
            "-c",
            (
                f'source "{LOCK_HELPER}"; '
                'acquire_release_lock "owner"; '
                'echo READY; '
                'read -r _'
            ),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert owner.stdout is not None
        assert owner.stdout.readline().strip() == "READY"

        contender = _bash(
            f'source "{LOCK_HELPER}"; acquire_release_lock "contender"',
            env=env,
        )

        assert contender.returncode == 73
        assert "发布任务正在执行" in contender.stderr
    finally:
        assert owner.stdin is not None
        owner.stdin.write("done\n")
        owner.stdin.flush()
        owner.wait(timeout=5)

    for _ in range(20):
        if not lock_dir.exists():
            break
        time.sleep(0.05)
    assert not lock_dir.exists()


def test_release_lock_recovers_a_dead_owner(tmp_path: Path):
    lock_dir = tmp_path / "release.lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text("99999999\n", encoding="utf-8")
    (lock_dir / "label").write_text("stale\n", encoding="utf-8")
    env = os.environ.copy()
    env["REVA_RELEASE_LOCK_DIR"] = str(lock_dir)

    result = _bash(
        f'source "{LOCK_HELPER}"; acquire_release_lock "replacement"; release_release_lock',
        env=env,
    )

    assert result.returncode == 0
    assert "清理陈旧发布锁" in result.stderr
    assert not lock_dir.exists()


def test_release_lock_resolves_the_repo_when_started_outside_it(tmp_path: Path):
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f'source "{LOCK_HELPER}"; '
                'resolved="$(_release_lock_path)"; '
                'test "$resolved" = "$(git -C '
                f'"{ROOT}" rev-parse --path-format=absolute --git-common-dir)'
                '/reva-release.lock"'
            ),
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_release_lock_allows_an_inherited_release_child(tmp_path: Path):
    lock_dir = tmp_path / "release.lock"
    env = os.environ.copy()
    env["REVA_RELEASE_LOCK_DIR"] = str(lock_dir)

    result = _bash(
        (
            'set -e; '
            f'source "{LOCK_HELPER}"; '
            'acquire_release_lock "outer"; '
            f'bash -c \'source "{LOCK_HELPER}"; acquire_release_lock "inner"\'; '
            'test -d "${REVA_RELEASE_LOCK_DIR}"; '
            'release_release_lock'
        ),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not lock_dir.exists()


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
    assert 'acquire_release_lock "testflight:${MODE}"' in testflight
