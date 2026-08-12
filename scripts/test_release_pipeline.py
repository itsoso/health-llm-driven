import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT = ROOT / "scripts/release.py"


def _release_module():
    assert RELEASE_SCRIPT.exists(), "scripts/release.py has not been implemented"
    spec = importlib.util.spec_from_file_location("reva_release", RELEASE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _change(release, status: str, *paths: str):
    return release.Change(status=status, paths=paths)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    ).strip()


@pytest.fixture
def repository_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "release@example.test")
    _git(repo, "config", "user.name", "Release Test")
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "initial")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-qu", "origin", "main")
    return repo, origin


def test_parses_git_name_status_with_rename_and_delete():
    release = _release_module()

    changes = release.parse_name_status(
        b"R100\0backend/app/old.py\0mobile/app/new.tsx\0"
        b"D\0mobile/app.json\0"
    )

    assert changes == (
        _change(
            release,
            "R100",
            "backend/app/old.py",
            "mobile/app/new.tsx",
        ),
        _change(release, "D", "mobile/app.json"),
    )


def test_mobile_runtime_change_plans_ota_only():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", "mobile/app/settings.tsx"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_ota",)
    assert plan.actions == ("validate", "mobile_ota")
    assert plan.publishable is True


def test_native_mobile_change_suppresses_ota():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "mobile/app/settings.tsx"),
            _change(release, "M", "mobile/app.json"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_native", "mobile_ota")
    assert plan.actions == ("validate", "native_build")
    assert "mobile_ota" not in plan.actions
    assert plan.publishable is False


def test_backend_and_mobile_ota_are_ordered_server_first():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "mobile/services/api.ts"),
            _change(release, "M", "backend/app/api/profile.py"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.actions == ("validate", "deploy_backend", "mobile_ota")


def test_frontend_change_uses_full_deploy_for_new_repository_sha():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", "frontend/app/page.tsx"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.actions == ("validate", "deploy_all")
    assert "deploy_frontend" not in plan.actions


def test_frontend_backend_and_ota_use_one_full_deploy_then_ota():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "backend/app/main.py"),
            _change(release, "M", "frontend/app/page.tsx"),
            _change(release, "M", "mobile/app/index.tsx"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.actions == ("validate", "deploy_all", "mobile_ota")


def test_docs_and_tests_are_validation_only():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "docs/governance/deploy.md"),
            _change(release, "A", "backend/tests/test_profile.py"),
            _change(release, "A", "mobile/app/__tests__/settings.test.tsx"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("validation_only",)
    assert plan.actions == ("validate",)
    assert plan.publishable is True


def test_unknown_path_blocks_release_fail_closed():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "A", "new-product-surface/config.toml"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.blocked_paths == ("new-product-surface/config.toml",)
    assert plan.publishable is False


def test_root_eas_build_input_requires_native_release():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", ".easignore"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_native",)
    assert plan.blocked_paths == ()
    assert plan.publishable is False


def test_rename_classifies_both_old_and_new_paths_and_delete_keeps_old_surface():
    release = _release_module()

    rename_plan = release.build_plan(
        (
            _change(
                release,
                "R096",
                "backend/app/old.py",
                "mobile/app/new.tsx",
            ),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )
    delete_plan = release.build_plan(
        (_change(release, "D", "apps/watch/Sources/App.swift"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert rename_plan.actions == (
        "validate",
        "deploy_backend",
        "mobile_ota",
    )
    assert delete_plan.actions == ("validate", "native_build")


def test_completed_surface_is_not_repeated_after_partial_publish():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "backend/app/main.py"),
            _change(release, "M", "mobile/app/index.tsx"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
        completed_actions=("deploy_backend",),
    )

    assert plan.completed_actions == ("deploy_backend",)
    assert plan.actions == ("validate", "mobile_ota")


def test_validation_credential_hit_skips_full_suite(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    verified: dict[str, object] = {}

    def verify(**kwargs):
        verified.update(kwargs)
        return release.validation_credential.CredentialVerdict(
            True, "reusable", {"result": "pass"}
        )

    monkeypatch.setattr(release.validation_credential, "verify_credential", verify)
    monkeypatch.setattr(
        release.validation_credential,
        "collect_toolchain",
        lambda _repo: {"python": "test"},
    )

    def runner(*_args, **_kwargs):
        raise AssertionError("credential hit must not rerun validation")

    release.run_validation(plan, repo, runner=runner)

    assert verified["repo"] == repo
    assert verified["profile_name"] == "all"
    assert verified["profile_version"] == release.validation_credential.PROFILE_VERSION
    assert verified["commands"] == [
        {
            "name": "validation:all",
            "argv": ["bash", "scripts/run-all-tests.sh"],
            "cwd": ".",
            "blocking": True,
        }
    ]
    assert verified["toolchain"] == {"python": "test"}
    assert "validation credential hit" in capsys.readouterr().out


@pytest.mark.parametrize(
    "reason", ["credential missing", "credential is invalid JSON", "credential expired"]
)
def test_validation_credential_miss_runs_suite_then_atomically_issues(
    reason: str,
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "mobile/app/index.tsx"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    calls: list[tuple[str, ...]] = []
    built: dict[str, object] = {}
    written: list[tuple[Path, dict[str, str]]] = []

    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: release.validation_credential.CredentialVerdict(
            False, reason
        ),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "collect_toolchain",
        lambda _repo: {"python": "test"},
    )

    def build(**kwargs):
        built.update(kwargs)
        return {"result": "pass"}

    monkeypatch.setattr(release.validation_credential, "build_credential", build)
    monkeypatch.setattr(
        release.validation_credential,
        "write_credential_atomic",
        lambda path, payload: written.append((Path(path), payload)),
    )

    def runner(command, **kwargs):
        calls.append(tuple(command))
        kwargs["stdout"].write("all checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    release.run_validation(plan, repo, runner=runner)

    assert calls == [("bash", "scripts/run-all-tests.sh")]
    assert built["repo"] == repo
    assert built["profile_name"] == "all"
    assert built["commands"] == [
        {
            "name": "validation:all",
            "argv": ["bash", "scripts/run-all-tests.sh"],
            "cwd": ".",
            "blocking": True,
        }
    ]
    log_path = Path(built["logs"]["validation:all"])
    assert log_path.read_text(encoding="utf-8") == "all checks passed\n"
    assert written == [
        (release.validation_credential.credential_path(repo, "all"), {"result": "pass"})
    ]
    output = capsys.readouterr().out
    assert f"validation credential miss: profile=all reason={reason}" in output
    assert "validation credential issued" in output


def test_failed_validation_never_writes_a_credential(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    writes: list[object] = []
    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: release.validation_credential.CredentialVerdict(
            False, "credential expired"
        ),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "collect_toolchain",
        lambda _repo: {"python": "test"},
    )
    monkeypatch.setattr(
        release.validation_credential,
        "write_credential_atomic",
        lambda *_args: writes.append(object()),
    )

    def runner(command, **_kwargs):
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(subprocess.CalledProcessError):
        release.run_validation(plan, repo, runner=runner)

    assert writes == []


def test_ci_never_reuses_or_issues_tree_credential(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("CI must not load a tree credential")
        ),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "write_credential_atomic",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("CI must not issue a tree credential")
        ),
    )

    def runner(command, **kwargs):
        calls.append(tuple(command))
        kwargs["stdout"].write("commit-specific checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    release.run_validation(plan, repo, runner=runner)

    assert calls == [("bash", "scripts/run-all-tests.sh")]
    assert "CI requires commit-specific validation" in capsys.readouterr().out


def test_validation_invokes_no_mutating_release_script(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    commands: list[tuple[str, ...]] = []

    monkeypatch.setenv("CI", "true")

    def runner(command, **kwargs):
        commands.append(tuple(str(part) for part in command))
        kwargs["stdout"].write("checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )
    release.run_validation(plan, repo, runner=runner)

    assert commands == [("bash", "scripts/run-all-tests.sh")]
    assert all("deploy.sh" not in part for command in commands for part in command)
    assert all(
        "mobile-ota.sh" not in part for command in commands for part in command
    )


def test_publish_rechecks_release_source_after_validation_before_mutation(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    commands: list[str] = []

    def dirty_after_validation(_plan, _repo, **_kwargs):
        (repo / "validation-generated.txt").write_text(
            "unexpected\n", encoding="utf-8"
        )

    monkeypatch.setattr(release, "run_validation", dirty_after_validation)

    def runner(command, **_kwargs):
        commands.append(str(command[0]))
        return subprocess.CompletedProcess(command, 0)

    with pytest.raises(release.ReleaseError, match="dirty"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="test",
            runner=runner,
        )

    assert commands == []


def test_release_worktree_is_detached_and_exactly_tracks_remote_main(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    release_path = tmp_path / "permanent.release"

    prepared = release.ensure_release_worktree(repo, release_path=release_path)

    assert prepared == release_path.resolve()
    assert subprocess.run(
        ["git", "-C", str(prepared), "symbolic-ref", "-q", "HEAD"],
        check=False,
    ).returncode != 0
    assert _git(prepared, "rev-parse", "HEAD") == _git(
        repo, "rev-parse", "origin/main"
    )
    release.assert_release_source(prepared)


def test_dirty_release_worktree_is_refused_without_cleanup(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    release_path = tmp_path / "permanent.release"
    release.ensure_release_worktree(repo, release_path=release_path)
    old_head = _git(release_path, "rev-parse", "HEAD")
    dirty_file = release_path / "operator-notes.txt"
    dirty_file.write_text("do not delete\n", encoding="utf-8")
    (repo / "README.md").write_text("advanced\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "advance main")
    _git(repo, "push", "-q", "origin", "main")

    with pytest.raises(release.ReleaseError, match="dirty"):
        release.ensure_release_worktree(repo, release_path=release_path)

    assert dirty_file.read_text(encoding="utf-8") == "do not delete\n"
    assert _git(release_path, "rev-parse", "HEAD") == old_head


def test_named_feature_branch_release_worktree_is_refused(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    release_path = tmp_path / "permanent.release"
    release.ensure_release_worktree(repo, release_path=release_path)
    _git(release_path, "checkout", "-qb", "feature/not-production")

    with pytest.raises(release.ReleaseError, match="feature/not-production"):
        release.ensure_release_worktree(repo, release_path=release_path)

    assert _git(release_path, "branch", "--show-current") == (
        "feature/not-production"
    )


def test_shared_release_state_uses_git_common_dir_and_private_permissions(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    other_worktree = tmp_path / "other-worktree"
    _git(repo, "worktree", "add", "--detach", str(other_worktree), "HEAD")

    release.write_release_state(repo, {"schema_version": 1, "ok": True})
    main_state_dir = release.release_state_dir(repo)
    other_state_dir = release.release_state_dir(other_worktree)
    state_file = main_state_dir / "release-state.json"

    assert main_state_dir == other_state_dir
    assert release.read_release_state(other_worktree)["ok"] is True
    assert stat.S_IMODE(main_state_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600
    assert json.loads(state_file.read_text(encoding="utf-8"))["ok"] is True


def test_plan_command_does_not_create_shared_operational_state(
    repository_with_origin: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
):
    release = _release_module()
    repo, _origin = repository_with_origin
    common_dir = Path(_git(repo, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    state_dir = common_dir.resolve() / "reva-release-state"

    exit_code = release.main(
        [
            "plan",
            "--repo",
            str(repo),
            "--base",
            "HEAD",
            "--target",
            "HEAD",
        ]
    )

    assert exit_code == 0, capsys.readouterr().err
    assert not state_dir.exists()


def test_validate_runs_for_manual_native_plan_without_publishing(
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "mobile").mkdir()
    (repo / "mobile/app.json").write_text('{"expo": {}}\n', encoding="utf-8")
    _git(repo, "add", "mobile/app.json")
    _git(repo, "commit", "-qm", "native config")
    _git(repo, "push", "-q", "origin", "main")
    validations: list[tuple[str, ...]] = []

    def record_validation(plan, _repo):
        validations.append(plan.surfaces)

    monkeypatch.setattr(release, "run_validation", record_validation)
    exit_code = release.main(
        [
            "validate",
            "--repo",
            str(repo),
            "--base",
            baseline,
            "--release-worktree",
            str(tmp_path / "release"),
        ]
    )

    assert exit_code == 0, capsys.readouterr().err
    assert validations == [("mobile_native",)]
