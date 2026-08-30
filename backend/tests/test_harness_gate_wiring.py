from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _pre_commit_hook_files_pattern(hook_id: str) -> re.Pattern[str]:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    header = f"      - id: {hook_id}\n"
    assert header in config, f"missing pre-commit hook: {hook_id}"
    block = config.split(header, 1)[1]
    next_hook = re.search(r"(?m)^      - id: ", block)
    if next_hook:
        block = block[: next_hook.start()]
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
    assert "pip install -r scripts/system-map-requirements.txt" in workflow
    assert "python scripts/check_doc_drift.py" not in workflow


def test_ci_runs_agent_skill_governance_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check Agent Skill governance" in workflow
    assert "python scripts/check_agent_skill_governance.py check" in workflow
