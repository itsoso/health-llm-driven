from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REMOVAL_SENTINEL = "scripts/check_governed_path_removals.py"
GOVERNED_HOOK_IDS = (
    "system-map",
    "dossier-consistency",
    "agent-skill-governance",
)


def _pre_commit_hook_block(hook_id: str) -> str:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    header = f"      - id: {hook_id}\n"
    assert header in config, f"missing pre-commit hook: {hook_id}"
    block = config.split(header, 1)[1]
    next_hook = re.search(r"(?m)^      - id: ", block)
    if next_hook:
        block = block[: next_hook.start()]
    return block


def _pre_commit_hook_files_pattern(hook_id: str) -> re.Pattern[str]:
    block = _pre_commit_hook_block(hook_id)
    files = re.search(r"(?m)^        files: '([^']+)'$", block)
    assert files, f"pre-commit hook {hook_id} must declare a files regex"
    return re.compile(files.group(1))


def _copy_test_harness(target: Path) -> None:
    source_helper = ROOT / "scripts" / "test-output.sh"
    assert source_helper.is_file(), "scripts/test-output.sh must be sourceable"
    scripts = target / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "run-all-tests.sh", scripts)
    shutil.copy2(source_helper, scripts)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed


def _init_removal_sentinel_repo(tmp_path: Path) -> tuple[Path, Path]:
    sentinel = ROOT / REMOVAL_SENTINEL
    assert sentinel.is_file(), f"missing removal sentinel: {sentinel}"

    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(sentinel, scripts / sentinel.name)
    gate_log = repo / "gate.log"
    python = sys.executable
    (repo / ".pre-commit-config.yaml").write_text(
        f"""repos:
  - repo: local
    hooks:
      - id: system-map
        name: system map
        entry: {python} scripts/fake_gate.py system-map
        language: system
        pass_filenames: false
        files: '^(?:\\.pre-commit-config\\.yaml$|{REMOVAL_SENTINEL}$|system/)'
      - id: dossier-consistency
        name: dossier consistency
        entry: {python} scripts/fake_gate.py dossier-consistency
        language: system
        pass_filenames: false
        files: '^(?:\\.pre-commit-config\\.yaml$|{REMOVAL_SENTINEL}$|dossier/)'
      - id: agent-skill-governance
        name: agent skill governance
        entry: {python} scripts/fake_gate.py agent-skill-governance
        language: system
        pass_filenames: false
        files: '^(?:\\.pre-commit-config\\.yaml$|{REMOVAL_SENTINEL}$|governance/)'
      - id: governed-path-removals
        name: governed path removals
        entry: {python} {REMOVAL_SENTINEL}
        language: system
        files: '^(?:\\.pre-commit-config\\.yaml$|{REMOVAL_SENTINEL}$)'
        pass_filenames: true
        always_run: true
""",
        encoding="utf-8",
    )
    (scripts / "fake_gate.py").write_text(
        """from __future__ import annotations

import os
import sys
from pathlib import Path

gate = sys.argv[1]
with Path(os.environ["GATE_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(gate + "\\n")
if os.environ.get("FAIL_GATE") == gate:
    raise SystemExit(int(os.environ.get("FAIL_CODE", "1")))
""",
        encoding="utf-8",
    )
    for relative in (
        "system/original.txt",
        "dossier/original.txt",
        "governance/original.txt",
        "README.md",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative + "\n", encoding="utf-8")

    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Removal Sentinel Test")
    _git(repo, "config", "user.email", "removal-sentinel@example.invalid")
    _git(
        repo,
        "add",
        ".pre-commit-config.yaml",
        REMOVAL_SENTINEL,
        "scripts/fake_gate.py",
        "system/original.txt",
        "dossier/original.txt",
        "governance/original.txt",
        "README.md",
    )
    _git(repo, "commit", "-qm", "baseline")
    return repo, gate_log


def _run_removal_sentinel(
    repo: Path,
    gate_log: Path,
    *pre_commit_paths: str,
    **extra_env: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, REMOVAL_SENTINEL, *pre_commit_paths],
        cwd=repo,
        env={**os.environ, "GATE_LOG": str(gate_log), **extra_env},
        text=True,
        capture_output=True,
        check=False,
    )


def _gate_runs(gate_log: Path) -> list[str]:
    if not gate_log.exists():
        return []
    return gate_log.read_text(encoding="utf-8").splitlines()


def _load_validate_module():
    spec = importlib.util.spec_from_file_location(
        "validate_harness", ROOT / "scripts" / "validate.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_runs_dossier_consistency_as_blocking_gate(monkeypatch):
    validate = _load_validate_module()
    captured = []

    def fake_run(check):
        captured.append(check)
        return "pass", 0.0, ""

    monkeypatch.setattr(validate, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["validate.py"])

    assert validate.main() == 0

    dossier_checks = [
        check for check in captured if check.name == "dossier-consistency"
    ]
    assert dossier_checks, "scripts/validate.py must run dossier consistency"
    assert dossier_checks[0].blocking is True
    assert dossier_checks[0].argv[-1] == "backend/scripts/check_dossier_consistency.py"

    system_map_checks = [check for check in captured if check.name == "system-map"]
    assert system_map_checks, "scripts/validate.py must run the central System Map gate"
    assert system_map_checks[0].blocking is True
    assert system_map_checks[0].argv[-1] == "scripts/system-map-check.sh"

    skill_governance_checks = [
        check for check in captured if check.name == "agent-skill-governance"
    ]
    assert skill_governance_checks, (
        "scripts/validate.py must run Agent Skill governance"
    )
    assert skill_governance_checks[0].blocking is True
    assert skill_governance_checks[0].argv[-2:] == [
        "scripts/check_agent_skill_governance.py",
        "check",
    ]


def test_validate_fails_when_dossier_consistency_fails(monkeypatch):
    validate = _load_validate_module()

    def fake_run(check):
        if check.name == "dossier-consistency":
            return "fail", 0.0, "Dossier consistency failed"
        return "pass", 0.0, ""

    monkeypatch.setattr(validate, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["validate.py"])

    assert validate.main() == 1


def test_pre_commit_runs_distributed_governance_gates():
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "entry: ./scripts/system-map-check.sh" in config
    assert "entry: python3 scripts/check_doc_drift.py" not in config
    assert "entry: python3 backend/scripts/check_dossier_consistency.py" in config
    assert "entry: python3 scripts/check_agent_skill_governance.py check" in config
    assert config.count("pass_filenames: false") >= 3


def test_pre_commit_governance_hooks_scope_only_relevant_files():
    cases = {
        "system-map": {
            "match": {
                ".pre-commit-config.yaml",
                "AGENTS.md",
                "CLAUDE.md",
                "backend/app/api/main.py",
                "backend/app/services/weather.py",
                "mobile/app/(tabs)/index.tsx",
                "frontend/src/app/page.tsx",
                "mobile/scripts/dump_nav_graph.py",
                "docs/ARCHITECTURE.md",
                "docs/system-map/declarations.json",
                "docs/_generated/system-map.json",
                "docs/_generated/system-map.schema.json",
                "docs/_generated/system-map-agent-context.md",
                "docs/_generated/mobile-nav-graph.json",
                "scripts/check_system_map.py",
                "scripts/check_doc_drift.py",
                "scripts/dump_system_map.py",
                "scripts/system_map_context.py",
                "scripts/system_map_contract.py",
                "scripts/system_map_imports.py",
                "scripts/system-map-check.sh",
                "scripts/system-map-requirements.txt",
                ".claude/skills/system-map/SKILL.md",
                ".claude/skills/doc-drift-fix/SKILL.md",
            },
            "skip": {
                "README.md",
                "backend/tests/test_login.py",
                "mobile/components/Button.tsx",
                "frontend/src/components/Button.tsx",
            },
        },
        "dossier-consistency": {
            "match": {
                ".pre-commit-config.yaml",
                "backend/scripts/check_dossier_consistency.py",
                "docs/dossiers/2026-08-30-example.md",
                "docs/prd/example.md",
                "docs/plans/example.md",
                "docs/specs/example.md",
                ".claude/skills/product-pipeline/dossier-template.md",
                "plugins/reva-health-harness/skills/product-pipeline/dossier-template.md",
            },
            "skip": {
                "README.md",
                "backend/app/api/main.py",
                "docs/notes/example.md",
            },
        },
        "agent-skill-governance": {
            "match": {
                ".pre-commit-config.yaml",
                "AGENTS.md",
                "docs/agent-skill-binding.md",
                "docs/design-agent-operating-harness.md",
                "docs/governance/agent-skill-registry.json",
                "docs/governance/agent-skill-governance.md",
                "docs/governance/agent-skill-run-event.schema.json",
                "docs/governance/agent-skill-run-trace-event.schema.json",
                "docs/specs/product-pipeline-contract.md",
                "docs/system-map/INDEX.md",
                ".claude/skills/reva-workflow-router/SKILL.md",
                "plugins/reva-health-harness/.codex-plugin/plugin.json",
                ".agents/plugins/marketplace.json",
                "scripts/check_agent_skill_governance.py",
                "scripts/agent_skill_benchmark.py",
            },
            "skip": {
                "README.md",
                "backend/app/api/main.py",
                "docs/dossiers/example.md",
            },
        },
    }

    for hook_id, paths in cases.items():
        pattern = _pre_commit_hook_files_pattern(hook_id)
        for path in paths["match"]:
            assert pattern.search(path), f"{hook_id} must run for {path}"
        for path in paths["skip"]:
            assert not pattern.search(path), f"{hook_id} should skip {path}"


def test_pre_commit_wires_one_always_run_removal_sentinel():
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    block = _pre_commit_hook_block("governed-path-removals")

    assert f"entry: python3.12 {REMOVAL_SENTINEL}" in block
    assert "pass_filenames: true" in block
    assert "always_run: true" in block
    sentinel_pattern = _pre_commit_hook_files_pattern("governed-path-removals")
    assert sentinel_pattern.search(".pre-commit-config.yaml")
    assert sentinel_pattern.search(REMOVAL_SENTINEL)
    assert not sentinel_pattern.search("README.md")
    for hook_id in GOVERNED_HOOK_IDS:
        assert _pre_commit_hook_files_pattern(hook_id).search(REMOVAL_SENTINEL), (
            f"{hook_id} must run when its removal sentinel changes"
        )
        assert config.index(f"      - id: {hook_id}\n") < config.index(
            "      - id: governed-path-removals\n"
        )


def test_removal_sentinel_runs_gate_for_nul_safe_rename_out(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)
    old = repo / "system" / "line\nbreak\tname.txt"
    old.write_text("governed\n", encoding="utf-8")
    _git(repo, "add", str(old.relative_to(repo)))
    _git(repo, "commit", "-qm", "add unusual path")
    destination = repo / "unrelated" / "renamed.txt"
    destination.parent.mkdir()
    _git(
        repo,
        "mv",
        str(old.relative_to(repo)),
        str(destination.relative_to(repo)),
    )

    completed = _run_removal_sentinel(repo, gate_log)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _gate_runs(gate_log) == ["system-map"]


def test_removal_sentinel_runs_each_gate_for_staged_deletions(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)
    for relative in (
        "system/original.txt",
        "dossier/original.txt",
        "governance/original.txt",
    ):
        (repo / relative).unlink()
    _git(repo, "add", "-u")

    completed = _run_removal_sentinel(repo, gate_log)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _gate_runs(gate_log) == list(GOVERNED_HOOK_IDS)


def test_removal_sentinel_does_not_duplicate_gate_with_governed_new_path(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)
    _git(repo, "mv", "system/original.txt", "system/renamed.txt")
    (repo / "dossier" / "original.txt").unlink()
    (repo / "dossier" / "replacement.txt").write_text(
        "replacement\n", encoding="utf-8"
    )
    _git(repo, "add", "dossier/original.txt", "dossier/replacement.txt")

    completed = _run_removal_sentinel(repo, gate_log)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _gate_runs(gate_log) == []


def test_removal_sentinel_skips_unrelated_staged_change(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)
    (repo / "README.md").write_text("ordinary docs change\n", encoding="utf-8")
    _git(repo, "add", "README.md")

    completed = _run_removal_sentinel(repo, gate_log)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _gate_runs(gate_log) == []


def test_removal_sentinel_skips_when_anchor_paths_signal_full_hook_coverage(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)
    for relative in (
        "system/original.txt",
        "dossier/original.txt",
        "governance/original.txt",
    ):
        (repo / relative).unlink()
    _git(repo, "add", "-u")

    completed = _run_removal_sentinel(
        repo,
        gate_log,
        ".pre-commit-config.yaml",
        REMOVAL_SENTINEL,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _gate_runs(gate_log) == []


def test_removal_sentinel_fails_closed_on_config_parse_error(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)
    config = repo / ".pre-commit-config.yaml"
    broken = re.sub(
        r"(?m)^        files: .+\n",
        "",
        config.read_text(encoding="utf-8"),
        count=1,
    )
    config.write_text(broken, encoding="utf-8")
    _git(repo, "add", ".pre-commit-config.yaml")

    completed = _run_removal_sentinel(repo, gate_log)

    assert completed.returncode != 0
    assert "system-map" in completed.stderr
    assert "files" in completed.stderr
    assert _gate_runs(gate_log) == []


def test_removal_sentinel_fails_closed_when_git_diff_fails(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)

    completed = _run_removal_sentinel(
        repo,
        gate_log,
        GIT_DIR=str(tmp_path / "missing-git-dir"),
    )

    assert completed.returncode != 0
    assert "git diff" in completed.stderr
    assert _gate_runs(gate_log) == []


def test_removal_sentinel_propagates_governed_gate_failure(tmp_path):
    repo, gate_log = _init_removal_sentinel_repo(tmp_path)
    (repo / "system" / "original.txt").unlink()
    _git(repo, "add", "-u")

    completed = _run_removal_sentinel(
        repo,
        gate_log,
        FAIL_GATE="system-map",
        FAIL_CODE="7",
    )

    assert completed.returncode == 7
    assert _gate_runs(gate_log) == ["system-map"]


def test_run_all_tests_uses_logged_commands_without_truncating_pipes():
    source = (ROOT / "scripts" / "run-all-tests.sh").read_text(encoding="utf-8")

    assert 'source "$ROOT/scripts/test-output.sh"' in source
    assert not re.search(r"\|\s*(?:tail|head)\b", source)
    assert "PIPESTATUS" not in source


def test_logged_command_preserves_failure_and_prints_bounded_context(tmp_path):
    helper = ROOT / "scripts" / "test-output.sh"
    assert helper.is_file(), "scripts/test-output.sh must be sourceable"
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    completed = subprocess.run(
        [
            "bash",
            "-c",
            """
source scripts/test-output.sh
fake_failure() {
  local line=1
  while [ "$line" -le 30 ]; do
    printf 'line-%s\\n' "$line"
    line=$((line + 1))
  done
  return 7
}
run_with_log "fake command" 3 4 fake_failure
exit $?
""",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 7
    lines = completed.stderr.splitlines()
    assert "fake command failed with exit 7" in completed.stderr
    for expected in ("line-1", "line-2", "line-3", "line-27", "line-28", "line-29", "line-30"):
        assert expected in lines
    assert "line-4" not in lines
    assert "line-26" not in lines
    assert not list(tmp_path.glob("reva-test-output.*"))


def test_logged_command_prints_only_success_tail_and_cleans_log(tmp_path):
    helper = ROOT / "scripts" / "test-output.sh"
    assert helper.is_file(), "scripts/test-output.sh must be sourceable"
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    completed = subprocess.run(
        [
            "bash",
            "-c",
            """
source scripts/test-output.sh
fake_success() {
  local line=1
  while [ "$line" -le 8 ]; do
    printf 'success-line-%s\\n' "$line"
    line=$((line + 1))
  done
  return 0
}
run_with_log "fake command" 3 4 fake_success
status=$?
printf 'after-success\\n'
exit "$status"
""",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.splitlines() == [
        "success-line-5",
        "success-line-6",
        "success-line-7",
        "success-line-8",
        "after-success",
    ]
    assert "success-line-4" not in completed.stdout
    assert completed.stderr == ""
    assert not list(tmp_path.glob("reva-test-output.*"))


def test_run_all_tests_surfaces_backend_exit_without_losing_context(tmp_path):
    repo = tmp_path / "repo"
    _copy_test_harness(repo)
    activate = repo / "backend" / "venv" / "bin" / "activate"
    activate.parent.mkdir(parents=True)
    activate.write_text("# fake venv\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    pytest = fake_bin / "pytest"
    pytest.write_text(
        "#!/usr/bin/env bash\n"
        "line=1\n"
        "while [ \"$line\" -le 35 ]; do echo \"pytest-line-$line\"; line=$((line + 1)); done\n"
        "exit 7\n",
        encoding="utf-8",
    )
    pytest.chmod(0o755)
    logs = tmp_path / "logs"
    logs.mkdir()
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "TMPDIR": str(logs),
    }

    completed = subprocess.run(
        ["bash", "scripts/run-all-tests.sh", "--backend"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    output = completed.stdout + completed.stderr

    assert completed.returncode == 1
    assert "Backend pytest failed with exit 7" in output
    assert "pytest-line-1" in output
    assert "pytest-line-35" in output
    assert "backend:pytest" in output
    assert not list(logs.glob("reva-test-output.*"))


def test_frontend_lint_exit_is_explicit_but_remains_non_blocking(tmp_path):
    repo = tmp_path / "repo"
    _copy_test_harness(repo)
    (repo / "frontend" / "node_modules").mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    npm = fake_bin / "npm"
    npm.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = run ] && [ \"${2:-}\" = lint ]; then\n"
        "  echo 'lint error context'\n"
        "  exit 7\n"
        "fi\n"
        "echo 'frontend test context'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    npm.chmod(0o755)
    npx = fake_bin / "npx"
    npx.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    npx.chmod(0o755)
    logs = tmp_path / "logs"
    logs.mkdir()
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "TMPDIR": str(logs),
    }

    completed = subprocess.run(
        ["bash", "scripts/run-all-tests.sh", "--frontend"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    output = completed.stdout + completed.stderr

    assert completed.returncode == 0
    assert "frontend test context" in output
    assert "Frontend lint failed with exit 7" in output
    assert "Frontend lint exit 7" in output
    assert "全部通过" in output
    assert not list(logs.glob("reva-test-output.*"))


def test_test_harness_shell_scripts_parse():
    helper = ROOT / "scripts" / "test-output.sh"
    assert helper.is_file(), "scripts/test-output.sh must be sourceable"
    completed = subprocess.run(
        ["bash", "-n", str(ROOT / "scripts" / "run-all-tests.sh"), str(helper)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_ci_runs_dossier_consistency_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check dossier consistency" in workflow
    assert "python backend/scripts/check_dossier_consistency.py" in workflow


def test_ci_runs_central_system_map_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check System Map and doc drift" in workflow
    assert "python scripts/check_system_map.py" in workflow
    assert "python -m pip install --disable-pip-version-check" in workflow
    assert "pytest==9.1.1 -r scripts/system-map-requirements.txt" in workflow
    assert "python scripts/check_doc_drift.py" not in workflow


def test_ci_runs_agent_skill_governance_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check Agent Skill governance" in workflow
    assert "python scripts/check_agent_skill_governance.py check" in workflow
