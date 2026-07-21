import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SCRIPT = ROOT / "backend/scripts/rollback_release.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "release"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "security@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Security Test"], cwd=repo, check=True)
    (repo / "backend/venv/bin").mkdir(parents=True)
    (repo / "backend/requirements.lock").write_text("", encoding="utf-8")
    (repo / "backend/.env").write_text(
        'DATABASE_URL=sqlite:///:memory:\ntouch "$FAKE_ENV_EXECUTED"\n',
        encoding="utf-8",
    )
    _write_executable(repo / "backend/venv/bin/pip", "#!/bin/sh\nexit 0\n")
    _write_executable(
        repo / "backend/venv/bin/python",
        "#!/bin/sh\nprintf 'schema-probe-ran\\n' > \"$FAKE_SCHEMA_PROBE_LOG\"\nexit 0\n",
    )
    (repo / "release.txt").write_text("known-good", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "known good"], cwd=repo, check=True)
    known_good = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "release.txt").write_text("failed-release", encoding="utf-8")
    subprocess.run(["git", "add", "release.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "failed release"], cwd=repo, check=True)
    failed = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    return repo, known_good, failed


def _fake_commands(tmp_path: Path, *, healthy: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "systemctl",
        """#!/bin/sh
case "$1" in
  stop) printf 'stopped\n' > "$FAKE_SERVICE_STATE" ;;
  start) printf 'active\n' > "$FAKE_SERVICE_STATE" ;;
  is-active) test "$(cat "$FAKE_SERVICE_STATE")" = active ;;
  *) exit 1 ;;
esac
""",
    )
    _write_executable(bin_dir / "sleep", "#!/bin/sh\nexit 0\n")
    health_result = "exit 0" if healthy else "exit 1"
    _write_executable(
        bin_dir / "curl",
        f"""#!/bin/sh
case "$*" in
  *auth/me*) printf '401'; exit 0 ;;
esac
{health_result}
""",
    )
    return bin_dir


def test_release_rollback_moves_head_and_requires_health_check(tmp_path: Path):
    repo, known_good, failed = _make_release_repo(tmp_path)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "2",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_ENV_EXECUTED": str(tmp_path / "env-executed"),
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")

    result = subprocess.run(
        [str(ROLLBACK_SCRIPT), str(repo), known_good],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert failed != known_good
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip() == known_good
    assert (repo / "release.txt").read_text(encoding="utf-8") == "known-good"
    assert "ROLLBACK_OK" in result.stdout
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "active"
    assert Path(env["FAKE_SCHEMA_PROBE_LOG"]).read_text(encoding="utf-8").strip() == "schema-probe-ran"
    assert not Path(env["FAKE_ENV_EXECUTED"]).exists()


def test_release_rollback_never_claims_success_when_health_check_fails(tmp_path: Path):
    repo, known_good, _ = _make_release_repo(tmp_path)
    bin_dir = _fake_commands(tmp_path, healthy=False)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "2",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")

    result = subprocess.run(
        [str(ROLLBACK_SCRIPT), str(repo), known_good],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert "健康检查失败" in result.stderr
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "stopped"


def test_release_rollback_preflight_failure_does_not_stop_running_services(tmp_path: Path):
    repo, known_good, _ = _make_release_repo(tmp_path)
    (repo / "release.txt").write_text("uncommitted change", encoding="utf-8")
    bin_dir = _fake_commands(tmp_path, healthy=True)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "2",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")

    result = subprocess.run(
        [str(ROLLBACK_SCRIPT), str(repo), known_good],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert "工作树存在未提交的 tracked 改动" in result.stderr
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "active"
