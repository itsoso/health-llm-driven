from __future__ import annotations

import ast
import builtins
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "governance" / "agent-skill-registry.json"
EVENT_SCHEMA = ROOT / "docs" / "governance" / "agent-skill-run-event.schema.json"
TRACE_EVENT_SCHEMA = (
    ROOT / "docs" / "governance" / "agent-skill-run-trace-event.schema.json"
)
BENCHMARK_COLLECTOR = ROOT / "scripts" / "agent_skill_benchmark.py"
CHECKER = ROOT / "scripts" / "check_agent_skill_governance.py"
TOOLING_PYTEST_RUNNER = ROOT / "scripts" / "run_tooling_pytests.py"
TOOLING_PYTEST_GUARD = ROOT / "scripts" / "tooling_pytest_guard.py"
TOOLING_TESTS = (
    "backend/tests/test_agent_skill_governance.py",
    "backend/tests/test_agent_skill_manifests.py",
    "backend/tests/test_doc_drift_narrative_counts.py",
    "backend/tests/test_doc_drift_skill_contract.py",
    "backend/tests/test_dossier_consistency.py",
    "backend/tests/test_reva_health_harness_plugin_package.py",
    "backend/tests/test_system_map_agent_context.py",
    "backend/tests/test_system_map_generator.py",
)
TOOLING_BENCHMARK_TEST = "backend/tests/test_agent_skill_benchmark.py"
CANONICAL_MODES = (
    "analysis",
    "quick_fix",
    "feature",
    "implementation",
    "incident",
    "release",
)
MODE_PHASE_NOTE = (
    "`planning` and `verification` are workflow phases, not mode values."
)
OPAQUE_UUID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[4-7][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _checker_module():
    spec = importlib.util.spec_from_file_location(
        "agent_skill_governance_checker", CHECKER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tooling_pytest_runner_module():
    assert TOOLING_PYTEST_RUNNER.is_file(), "tooling pytest runner is required"
    spec = importlib.util.spec_from_file_location(
        "tooling_pytest_runner", TOOLING_PYTEST_RUNNER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tooling_pytest_guard_module():
    assert TOOLING_PYTEST_GUARD.is_file(), "tooling pytest guard is required"
    spec = importlib.util.spec_from_file_location(
        "tooling_pytest_guard", TOOLING_PYTEST_GUARD
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _attribute_path(node: ast.expr) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return tuple(reversed(parts))


def _literal_fixture_names(call: ast.Call) -> set[str]:
    values = [
        *call.args,
        *(keyword.value for keyword in call.keywords if keyword.arg == "argname"),
    ]
    return {
        argument.value
        for argument in values
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }


def _pytest_usefixtures_paths(tree: ast.AST) -> set[tuple[str, ...]]:
    paths = {("pytest", "mark", "usefixtures")}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pytest":
                    paths.add((alias.asname or "pytest", "mark", "usefixtures"))
        if not isinstance(node, ast.ImportFrom) or node.level != 0:
            continue
        if node.module == "pytest":
            for alias in node.names:
                if alias.name == "mark":
                    paths.add((alias.asname or "mark", "usefixtures"))
        if node.module == "pytest.mark":
            for alias in node.names:
                if alias.name == "usefixtures":
                    paths.add((alias.asname or "usefixtures",))
    return paths


def _assert_tooling_test_ast_safe(source: str, filename: str) -> None:
    guard = _tooling_pytest_guard_module()
    tree = ast.parse(source, filename=filename)
    usefixtures_paths = _pytest_usefixtures_paths(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
            forbidden = [
                name for name in imported if guard.is_forbidden_module_name(name)
            ]
            assert not forbidden, (filename, forbidden)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported = [
                module,
                *(f"{module}.{alias.name}" for alias in node.names if module),
            ]
            forbidden = [
                name
                for name in imported
                if node.level == 0 and guard.is_forbidden_module_name(name)
            ]
            assert not forbidden, (filename, forbidden)
        is_test_function = isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name.startswith("test_")
        if is_test_function:
            argument_names = {
                argument.arg
                for argument in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
            }
            forbidden = argument_names & guard.FORBIDDEN_FIXTURES
            assert not forbidden, (filename, node.name, forbidden)
        if not isinstance(node, ast.Call):
            continue
        call_path = _attribute_path(node.func)
        if call_path in usefixtures_paths:
            forbidden = _literal_fixture_names(node) & guard.FORBIDDEN_FIXTURES
            assert not forbidden, (filename, "pytest.mark.usefixtures", forbidden)
        if call_path == ("request", "getfixturevalue"):
            forbidden = _literal_fixture_names(node) & guard.FORBIDDEN_FIXTURES
            assert not forbidden, (filename, "request.getfixturevalue", forbidden)


@pytest.fixture(autouse=True)
def _isolate_twin_cache():
    """Override the repository Redis-flushing fixture for pure governance tests."""
    yield


@pytest.fixture(autouse=True)
def _noop_twin_cache():
    """Do not patch or connect to runtime Twin cache in repository-contract tests."""
    yield


def _registry() -> dict:
    assert REGISTRY.is_file(), "machine-readable Agent Skill registry is required"
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


@cache
def _tracked_project_files() -> frozenset[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, os.fsdecode(result.stderr)
    return frozenset(
        os.fsdecode(relative) for relative in result.stdout.split(b"\0") if relative
    )


def _recommend(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "recommend", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _assert_activation_partition(result: dict) -> None:
    phases = _registry()["routing"]["activation_policy"]["phases"]
    allowed_phases = set(phases)
    expected_phase_order = [
        phase
        for phase in phases
        if phase != "immediate" and phase in result["deferred_by_phase"]
    ]
    assert list(result["deferred_by_phase"]) == expected_phase_order

    phase_deferred = [
        skill_id
        for phase in expected_phase_order
        for skill_id in result["deferred_by_phase"][phase]
    ]
    activation = [*result["immediate_skills"], *phase_deferred]

    assert set(result["immediate_skills"]).isdisjoint(phase_deferred)
    assert result["activation_skills"] == activation
    assert len(activation) == len(set(activation))
    assert [item["id"] for item in result["activation_skill_details"]] == activation
    assert result["deferred_skills"] == result["delegates"]
    assert [item["id"] for item in result["deferred_skill_details"]] == result[
        "delegates"
    ]
    assert all(
        item["role"] == "delegate" for item in result["deferred_skill_details"]
    )
    assert set(result["selected_skills"]).isdisjoint(result["deferred_skills"])
    assert set(result["selected_skills"]) | set(result["deferred_skills"]) == set(
        activation
    )
    assert [item["id"] for item in result["selected_skill_details"]] == result[
        "selected_skills"
    ]
    assert {
        item["activation_phase"] for item in result["activation_skill_details"]
    } <= allowed_phases


def test_registry_has_one_router_and_closed_governance_vocabulary():
    registry = _registry()

    assert registry["schema_version"] == "agent-skill-registry.v1"
    assert registry["lifecycle"] == [
        "experimental",
        "recommended",
        "standard",
        "deprecated",
    ]
    assert registry["layers"] == ["platform", "workflow", "incubator"]
    assert registry["kinds"] == [
        "router",
        "controller",
        "capability",
        "overlay",
        "terminal",
    ]

    routers = [skill for skill in registry["skills"] if skill["kind"] == "router"]
    assert [skill["id"] for skill in routers] == ["reva-workflow-router"]
    assert "domain-rule-factory" not in {skill["id"] for skill in registry["skills"]}


def test_mode_vocabulary_is_identical_across_registry_checker_and_entrypoints():
    checker = _checker_module()
    registry = _registry()
    mode_argument = f"--mode <{'|'.join(CANONICAL_MODES)}>"

    assert tuple(checker.MODES) == CANONICAL_MODES
    assert tuple(registry["routing"]["routes"]) == CANONICAL_MODES

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert mode_argument in agents
    assert MODE_PHASE_NOTE in agents

    for path in (
        ROOT / ".claude" / "skills" / "reva-workflow-router" / "SKILL.md",
        ROOT
        / "plugins"
        / "reva-health-harness"
        / "skills"
        / "reva-workflow-router"
        / "SKILL.md",
    ):
        text = path.read_text(encoding="utf-8")
        for mode in CANONICAL_MODES:
            assert f"`{mode}`" in text
        assert MODE_PHASE_NOTE in text


def test_checker_rejects_registry_mode_order_drift():
    checker = _checker_module()
    registry = _registry()
    routes = registry["routing"]["routes"]
    registry["routing"]["routes"] = {
        mode: routes[mode] for mode in reversed(CANONICAL_MODES)
    }

    with pytest.raises(checker.GovernanceError) as exc:
        checker.validate_registry(registry)

    assert exc.value.code == "invalid_modes"


def test_tooling_pytest_runner_uses_an_isolated_no_coverage_command():
    runner = _tooling_pytest_runner_module()

    command = runner.build_command(include_benchmark=False)
    assert command[:3] == [sys.executable, "-m", "pytest"]
    assert "--noconftest" in command
    assert "-c" in command
    assert command[command.index("-c") + 1] == os.devnull
    assert "--rootdir" in command
    assert command[command.index("--rootdir") + 1] == str(ROOT)
    assert command[command.index("-o") + 1] == "addopts="
    assert "-q" in command
    assert "--strict-markers" in command
    assert "--tb=short" in command
    plugins = [
        command[index + 1]
        for index, argument in enumerate(command[:-1])
        if argument == "-p"
    ]
    assert plugins == ["no:cacheprovider", "scripts.tooling_pytest_guard"]
    assert not any(argument.startswith("--cov") for argument in command)

    environment = runner.sanitized_environment(
        {
            "PYTEST_ADDOPTS": "--cov=app --cov-report=html",
            "PYTEST_PLUGINS": "untrusted_plugin",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "0",
            "KEEP_ME": "yes",
        }
    )
    assert "PYTEST_ADDOPTS" not in environment
    assert "PYTEST_PLUGINS" not in environment
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["KEEP_ME"] == "yes"


def test_tooling_pytest_runner_has_exact_default_allowlist():
    runner = _tooling_pytest_runner_module()

    assert tuple(runner.DEFAULT_TESTS) == TOOLING_TESTS


def test_tooling_pytest_runner_only_adds_benchmark_on_explicit_request():
    runner = _tooling_pytest_runner_module()

    default_command = runner.build_command(include_benchmark=False)
    benchmark_command = runner.build_command(include_benchmark=True)

    assert TOOLING_BENCHMARK_TEST not in default_command
    assert benchmark_command[-1] == TOOLING_BENCHMARK_TEST
    assert benchmark_command.count(TOOLING_BENCHMARK_TEST) == 1


def test_tooling_pytest_runner_preserves_fixed_cwd_and_child_exit_code(monkeypatch):
    runner = _tooling_pytest_runner_module()
    invocation = {}

    def completed_with_failure(command, **kwargs):
        invocation.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, returncode=17)

    monkeypatch.setattr(runner.subprocess, "run", completed_with_failure)

    assert runner.main([]) == 17
    assert invocation["command"] == runner.build_command(include_benchmark=False)
    assert invocation["cwd"] == ROOT
    assert invocation["check"] is False


def test_tooling_pytest_runner_help_states_supplemental_scope(capsys):
    runner = _tooling_pytest_runner_module()

    with pytest.raises(SystemExit) as exc:
        runner.parse_args(["--help"])

    assert exc.value.code == 0
    help_text = " ".join(capsys.readouterr().out.lower().split())
    assert "supplemental" in help_text
    assert "skips coverage" in help_text
    assert "does not replace regular project tests or ci gates" in help_text


def test_tooling_pytest_allowlist_is_present_and_ast_runtime_independent():
    runner = _tooling_pytest_runner_module()
    allowlist = (*runner.DEFAULT_TESTS, runner.BENCHMARK_TEST)

    assert runner.BENCHMARK_TEST == TOOLING_BENCHMARK_TEST

    for relative in allowlist:
        path = ROOT / relative
        assert path.is_file(), relative
        _assert_tooling_test_ast_safe(path.read_text(encoding="utf-8"), relative)


def test_tooling_ast_guard_allows_helper_parameter_names():
    _assert_tooling_test_ast_safe(
        "def helper(client_name):\n    return client_name\n",
        "helper_probe.py",
    )


@pytest.mark.parametrize(
    ("source", "module_name"),
    [
        ("import app.services\n", "app.services"),
        ("from main import create_app\n", "main"),
        ("import backend.app.models\n", "backend.app.models"),
        ("from backend.main import app\n", "backend.main"),
        ("from backend import app\n", "backend.app"),
    ],
)
def test_tooling_ast_guard_rejects_application_imports(source, module_name):
    with pytest.raises(AssertionError, match=re.escape(module_name)):
        _assert_tooling_test_ast_safe(source, "import_probe.py")


@pytest.mark.parametrize(
    ("source", "fixture_name"),
    [
        ("def test_probe(client):\n    pass\n", "client"),
        (
            '@pytest.mark.usefixtures("auth_user_and_headers")\n'
            "def test_probe():\n    pass\n",
            "auth_user_and_headers",
        ),
        (
            "def test_probe(request):\n"
            '    request.getfixturevalue("db")\n',
            "db",
        ),
        (
            "import pytest as pt\n"
            '@pt.mark.usefixtures("db")\n'
            "def test_probe():\n    pass\n",
            "db",
        ),
        (
            "from pytest import mark\n"
            '@mark.usefixtures("client")\n'
            "def test_probe():\n    pass\n",
            "client",
        ),
        (
            "def test_probe(request):\n"
            '    request.getfixturevalue(argname="db")\n',
            "db",
        ),
    ],
)
def test_tooling_ast_guard_rejects_application_fixture_access(source, fixture_name):
    with pytest.raises(AssertionError, match=fixture_name):
        _assert_tooling_test_ast_safe(source, "fixture_probe.py")


def test_tooling_pytest_guard_fails_for_dynamically_loaded_application_module(
    tmp_path,
):
    runner = _tooling_pytest_runner_module()
    assert TOOLING_PYTEST_GUARD.is_file(), "tooling pytest guard is required"
    package = tmp_path / "app"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "dynamic_probe.py").write_text("VALUE = 1\n", encoding="utf-8")
    probe = tmp_path / "test_dynamic_application_import.py"
    probe.write_text(
        "import importlib\n"
        "import sys\n"
        "\n"
        "def test_dynamic_application_import():\n"
        '    name = "app.dynamic_probe"\n'
        "    assert importlib.import_module(name).VALUE == 1\n"
        "    sys.modules.pop(name)\n"
        '    sys.modules.pop("app")\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *runner.PYTEST_OPTIONS, str(probe)],
        cwd=ROOT,
        env=runner.sanitized_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "app.dynamic_probe" in result.stdout + result.stderr


def test_tooling_pytest_guard_fails_for_direct_application_source_loaders(tmp_path):
    runner = _tooling_pytest_runner_module()
    detached_source = tmp_path / "detached_source.py"
    detached_source.write_text("VALUE = 1\n", encoding="utf-8")
    backend_app_source = ROOT / "backend" / "app" / "__init__.py"
    probe = tmp_path / "test_direct_application_source_loader.py"
    probe.write_text(
        "import importlib.util\n"
        "import sys\n"
        "\n"
        "def load_detached(name, path):\n"
        "    spec = importlib.util.spec_from_file_location(name, path)\n"
        "    assert spec and spec.loader\n"
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    assert name not in sys.modules\n"
        "\n"
        "def test_direct_application_source_loader():\n"
        f"    load_detached('app.direct_loader_probe', {str(detached_source)!r})\n"
        f"    load_detached('backend_app_path_probe', {str(backend_app_source)!r})\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *runner.PYTEST_OPTIONS, str(probe)],
        cwd=ROOT,
        env=runner.sanitized_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "app.direct_loader_probe" in output
    assert "backend_app_path_probe" in output


def test_tooling_pytest_guard_allows_direct_safe_script_loader(tmp_path):
    runner = _tooling_pytest_runner_module()
    safe_source = ROOT / "scripts" / "run_tooling_pytests.py"
    probe = tmp_path / "test_direct_safe_script_loader.py"
    probe.write_text(
        "import importlib.util\n"
        "import sys\n"
        "\n"
        "def test_direct_safe_script_loader():\n"
        "    name = 'tooling_safe_loader_probe'\n"
        f"    spec = importlib.util.spec_from_file_location(name, {str(safe_source)!r})\n"
        "    assert spec and spec.loader\n"
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    assert name not in sys.modules\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *runner.PYTEST_OPTIONS, str(probe)],
        cwd=ROOT,
        env=runner.sanitized_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_tooling_pytest_guard_restores_hooks_after_sessionstart_error(
    tmp_path,
    monkeypatch,
):
    guard = _tooling_pytest_guard_module()
    original_import = builtins.__import__
    original_import_module = importlib.import_module
    original_exec_module = importlib.machinery.SourceFileLoader.exec_module
    probe = tmp_path / "test_guard_recovery_probe.py"
    probe.write_text("def test_ok():\n    pass\n", encoding="utf-8")
    args = [
        "--noconftest",
        "-c",
        os.devnull,
        "--rootdir",
        str(tmp_path),
        "-q",
        "-p",
        "no:cacheprovider",
        str(probe),
    ]

    class FailingSessionStart:
        @pytest.hookimpl(trylast=True)
        def pytest_sessionstart(self):
            raise RuntimeError("sessionstart probe")

    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    try:
        first_exit = pytest.main(args, plugins=[guard, FailingSessionStart()])

        assert first_exit == pytest.ExitCode.INTERNAL_ERROR
        assert builtins.__import__ is original_import
        assert importlib.import_module is original_import_module
        assert importlib.machinery.SourceFileLoader.exec_module is original_exec_module

        second_exit = pytest.main(args, plugins=[guard])

        assert second_exit == pytest.ExitCode.OK
        assert builtins.__import__ is original_import
        assert importlib.import_module is original_import_module
        assert importlib.machinery.SourceFileLoader.exec_module is original_exec_module
    finally:
        guard._restore_import_functions()


def test_tooling_pytest_guard_preserves_existing_nonzero_exit_status(monkeypatch):
    guard = _tooling_pytest_guard_module()
    session = SimpleNamespace(
        exitstatus=pytest.ExitCode.INTERRUPTED,
        config=SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda _name: None)
        ),
    )
    monkeypatch.setattr(
        guard,
        "loaded_forbidden_module_names",
        lambda: ("app.dynamic_probe",),
    )

    guard.pytest_sessionfinish(session)

    assert session.exitstatus == pytest.ExitCode.INTERRUPTED


def test_tooling_pytest_guard_resets_history_for_each_session(monkeypatch):
    guard = _tooling_pytest_guard_module()
    guard._observed_forbidden_modules.add("app.stale_session")
    monkeypatch.setattr(guard, "_observe_current_modules", lambda: None)

    guard.pytest_sessionstart()
    try:
        assert guard._observed_forbidden_modules == set()
    finally:
        guard._restore_import_functions()


def test_agents_limits_the_tooling_fast_lane_to_pure_tooling_changes():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert (
        "uv run --isolated --with-requirements backend/requirements-dev.txt "
        "python scripts/run_tooling_pytests.py"
    ) in agents
    assert "仅修改 agent-governance、System Map 或 doc-tooling" in agents
    assert "不得作为每个任务的默认入口" in agents
    assert "不替代常规项目测试、coverage 或 CI Gate" in agents


def test_every_standard_project_skill_is_owned_versioned_and_evidenced():
    registry = _registry()
    required = {
        "owner",
        "version",
        "layer",
        "kind",
        "platforms",
        "trigger_family",
        "last_reviewed",
        "evidence",
        "sources",
    }

    for skill in registry["skills"]:
        if skill["lifecycle"] != "standard":
            continue
        assert required <= skill.keys(), skill["id"]
        assert skill["owner"]
        assert skill["evidence"]
        assert skill["sources"]


def test_every_registered_project_source_is_committed_not_only_present_locally():
    tracked_files = _tracked_project_files()
    for skill in _registry()["skills"]:
        for source in skill["sources"]:
            assert source in tracked_files, (skill["id"], source)


def test_validation_queries_the_tracked_file_inventory_once(monkeypatch):
    checker = _checker_module()
    real_run = checker.subprocess.run
    git_calls: list[list[str]] = []

    def recording_run(command, *args, **kwargs):
        if command[:2] == ["git", "ls-files"]:
            git_calls.append(command)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(checker.subprocess, "run", recording_run)

    checker.validate_registry(_registry())

    assert git_calls == [["git", "ls-files", "-z"]]


def test_consecutive_validations_refresh_the_tracked_file_inventory(monkeypatch):
    checker = _checker_module()
    registry = _registry()
    missing_source = registry["skills"][0]["sources"][0]
    tracked_files = _tracked_project_files()
    inventories = [tracked_files, tracked_files - {missing_source}]
    git_calls: list[list[str]] = []

    def changing_inventory(command, *args, **kwargs):
        git_calls.append(command)
        inventory = inventories[len(git_calls) - 1]
        stdout = b"\0".join(os.fsencode(path) for path in sorted(inventory)) + b"\0"
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout=stdout,
            stderr=b"",
        )

    monkeypatch.setattr(checker.subprocess, "run", changing_inventory)

    checker.validate_registry(registry)
    with pytest.raises(checker.GovernanceError) as exc:
        checker.validate_registry(registry)

    assert exc.value.code == "untracked_source"
    assert missing_source in exc.value.detail
    assert git_calls == [
        ["git", "ls-files", "-z"],
        ["git", "ls-files", "-z"],
    ]


def test_validation_fails_closed_when_tracked_inventory_cannot_be_loaded(
    monkeypatch,
):
    checker = _checker_module()

    def failing_git(command, *args, **kwargs):
        return subprocess.CompletedProcess(
            command,
            returncode=128,
            stdout=b"",
            stderr=b"fatal: tracked inventory unavailable",
        )

    monkeypatch.setattr(checker.subprocess, "run", failing_git)

    with pytest.raises(checker.GovernanceError) as exc:
        checker.validate_registry(_registry())

    assert exc.value.code == "tracked_file_inventory_failed"


def test_untracked_source_still_blocks_cached_inventory(monkeypatch):
    checker = _checker_module()
    registry = _registry()
    missing_source = registry["skills"][0]["sources"][0]
    tracked_files = _tracked_project_files() - {missing_source}
    inventory = b"\0".join(os.fsencode(path) for path in sorted(tracked_files)) + b"\0"

    def inventory_without_source(command, *args, **kwargs):
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout=inventory,
            stderr=b"",
        )

    monkeypatch.setattr(checker.subprocess, "run", inventory_without_source)

    with pytest.raises(checker.GovernanceError) as exc:
        checker.validate_registry(registry)

    assert exc.value.code == "untracked_source"
    assert missing_source in exc.value.detail


def test_tracked_file_inventory_preserves_paths_with_spaces(monkeypatch):
    checker = _checker_module()
    assert hasattr(checker, "_tracked_files"), "tracked inventory API is required"
    inventory = b"plain.py\0docs/path with spaces.md\0"

    def spaced_inventory(command, *args, **kwargs):
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout=inventory,
            stderr=b"",
        )

    monkeypatch.setattr(checker.subprocess, "run", spaced_inventory)

    assert checker._tracked_files() == frozenset(
        {"plain.py", "docs/path with spaces.md"}
    )


def test_shared_protocol_skills_are_agent_neutral_not_implicit_platform_copies():
    registry = _registry()

    for skill in registry["skills"]:
        if "adapters" in skill:
            continue
        assert skill["platforms"] == ["agent-neutral"], skill["id"]


def test_unhardened_release_skills_are_recommended_not_platform_standard():
    registry = _registry()
    skills = {skill["id"]: skill for skill in registry["skills"]}

    for skill_id in (
        "backend-deploy",
        "ios-app-review-gate",
        "mac-build-deploy",
        "mobile-testflight-release",
    ):
        assert skills[skill_id]["lifecycle"] == "recommended"

    assert skills["mobile-ota"]["lifecycle"] == "standard"


def test_agent_neutral_skill_sources_do_not_contain_provider_only_instructions():
    registry = _registry()
    forbidden = {
        "TeamCreate",
        "TaskCreate",
        "SendMessage",
        "subagent_type",
        'model: "opus"',
        "Co-Authored-By: Claude",
        "CLAUDE.md",
        "`backend-engineer`/",
        "`release-engineer` agent",
        "[[",
    }

    for skill in registry["skills"]:
        if skill["platforms"] != ["agent-neutral"]:
            continue
        for source in skill["sources"]:
            if not source.endswith("SKILL.md"):
                continue
            content = (ROOT / source).read_text(encoding="utf-8")
            assert all(token not in content for token in forbidden), skill["id"]


def test_best_skill_set_is_explicit_and_keeps_capabilities_out_of_controller_role():
    registry = _registry()
    best = registry["best_skill_set"]

    assert best["router"] == "reva-workflow-router"
    assert set(best["baseline_capabilities"]) == {
        "system-map",
        "karpathy-guidelines",
        "test-driven-development",
        "systematic-debugging",
        "verification-before-completion",
    }
    assert set(best["primary_controllers"]) == {
        "product-pipeline",
        "health-harness-orchestrator",
    }
    assert not set(best["baseline_capabilities"]) & set(best["primary_controllers"])


def test_project_deprecates_direct_superpowers_and_executing_plans_control():
    registry = _registry()
    external = {item["id"]: item for item in registry["external_recommendations"]}

    assert all(item["version"].count(".") == 2 for item in external.values())
    for skill_id in ("using-superpowers", "executing-plans"):
        assert external[skill_id]["lifecycle"] == "deprecated"
        assert external[skill_id]["allow_direct_controller"] is False


def test_feature_route_has_exactly_one_controller_and_deduplicated_overlays():
    result = _recommend(
        "--mode",
        "feature",
        "--overlay",
        "safety",
        "--overlay",
        "database",
        "--overlay",
        "notification-privacy",
    )

    assert result["controller"] == "product-pipeline"
    assert result["delegates"] == ["health-harness-orchestrator"]
    assert result["deferred_by_phase"]["S5"] == ["health-harness-orchestrator"]
    assert result["deferred_skills"] == ["health-harness-orchestrator"]
    assert "health-harness-orchestrator" not in result["selected_skills"]
    assert result["selected_skills"] == [
        "reva-workflow-router",
        "product-pipeline",
        "system-map",
        "karpathy-guidelines",
        "test-driven-development",
        "verification-before-completion",
        "add-managed-migration",
        "safety-gate",
    ]
    assert result["activation_skills"] == [
        "reva-workflow-router",
        "product-pipeline",
        "add-managed-migration",
        "safety-gate",
        "system-map",
        "karpathy-guidelines",
        "test-driven-development",
        "verification-before-completion",
        "health-harness-orchestrator",
    ]
    assert result["overlays"] == ["add-managed-migration", "safety-gate"]
    assert result["controller_count"] == 1
    _assert_activation_partition(result)


def test_quick_fix_route_does_not_create_a_workflow_controller():
    result = _recommend("--mode", "quick_fix")

    assert result["controller"] is None
    assert result["delegates"] == []
    assert result["controller_count"] == 0
    assert "test-driven-development" in result["capabilities"]
    assert "verification-before-completion" in result["capabilities"]
    assert [item["id"] for item in result["selected_skill_details"]] == result[
        "selected_skills"
    ]
    assert all(
        item["version"].count(".") == 2 for item in result["selected_skill_details"]
    )
    assert {item["role"] for item in result["selected_skill_details"]} <= {
        "router",
        "controller",
        "delegate",
        "capability",
        "overlay",
        "terminal",
    }
    _assert_activation_partition(result)


def test_skill_and_plugin_governance_add_only_the_relevant_authoring_capabilities():
    result = _recommend(
        "--mode",
        "analysis",
        "--capability-trigger",
        "skill-governance",
        "--capability-trigger",
        "plugin-authoring",
    )

    assert result["controller"] is None
    assert result["triggered_capabilities"] == [
        "plugin-creator",
        "skill-creator",
        "writing-skills",
    ]
    assert "test-driven-development" not in result["selected_skills"]


def test_recommendation_v2_partitions_startup_from_deferred_phase_loading():
    result = _recommend(
        "--mode",
        "implementation",
        "--overlay",
        "doc-drift",
        "--capability-trigger",
        "skill-governance",
    )

    assert result["schema_version"] == "agent-skill-recommendation.v2"
    assert result["immediate_skills"] == [
        "reva-workflow-router",
        "health-harness-orchestrator",
        "skill-creator",
        "writing-skills",
        "doc-drift-fix",
    ]
    assert result["deferred_by_phase"] == {
        "on_demand": ["system-map"],
        "implementation": ["karpathy-guidelines", "test-driven-development"],
        "verification": ["verification-before-completion"],
    }
    assert result["deferred_skills"] == []
    assert result["selected_skills"] == [
        "reva-workflow-router",
        "health-harness-orchestrator",
        "system-map",
        "karpathy-guidelines",
        "test-driven-development",
        "verification-before-completion",
        "skill-creator",
        "writing-skills",
        "doc-drift-fix",
    ]
    assert result["activation_skills"] == [
        "reva-workflow-router",
        "health-harness-orchestrator",
        "skill-creator",
        "writing-skills",
        "doc-drift-fix",
        "system-map",
        "karpathy-guidelines",
        "test-driven-development",
        "verification-before-completion",
    ]
    phases = {
        item["id"]: item["activation_phase"]
        for item in result["selected_skill_details"]
    }
    assert phases["reva-workflow-router"] == "immediate"
    assert phases["doc-drift-fix"] == "immediate"
    assert phases["skill-creator"] == "immediate"
    assert phases["system-map"] == "on_demand"
    assert phases["test-driven-development"] == "implementation"
    assert phases["verification-before-completion"] == "verification"
    _assert_activation_partition(result)


def test_incident_debugging_is_eager_but_keeps_diagnosis_phase_semantics():
    result = _recommend("--mode", "incident")

    assert "systematic-debugging" in result["immediate_skills"]
    details = {item["id"]: item for item in result["selected_skill_details"]}
    assert details["systematic-debugging"]["activation_phase"] == "diagnosis"
    assert "diagnosis" not in result["deferred_by_phase"]
    _assert_activation_partition(result)


def test_release_terminal_is_immediate_and_verification_remains_deferred():
    result = _recommend("--mode", "release", "--release-target", "mobile-ota")

    assert result["immediate_skills"] == [
        "reva-workflow-router",
        "mobile-ota",
    ]
    assert result["deferred_by_phase"] == {
        "verification": ["verification-before-completion"]
    }
    _assert_activation_partition(result)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda policy: policy["phases"].append("whenever"),
            id="phase-vocabulary",
        ),
        pytest.param(
            lambda policy: policy["role_phases"].update({"router": "whenever"}),
            id="role-phase",
        ),
        pytest.param(
            lambda policy: policy["capability_phases"].update(
                {"system-map": "whenever"}
            ),
            id="capability-phase",
        ),
        pytest.param(
            lambda policy: policy.update({"capability_trigger_phase": "whenever"}),
            id="capability-trigger-phase",
        ),
        pytest.param(
            lambda policy: policy["eager_phases_by_mode"].update(
                {"incident": ["whenever"]}
            ),
            id="eager-mode-phase",
        ),
        pytest.param(
            lambda policy: policy["delegate_phases"]["feature"].update(
                {"health-harness-orchestrator": "whenever"}
            ),
            id="delegate-phase",
        ),
    ],
)
def test_checker_rejects_unknown_activation_phase_from_registry(mutation):
    checker = _checker_module()
    registry = _registry()
    mutation(registry["routing"]["activation_policy"])

    with pytest.raises(checker.GovernanceError) as exc:
        checker.validate_registry(registry)

    assert exc.value.code == "invalid_activation_phase"


def test_unknown_capability_trigger_fails_closed():
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "recommend",
            "--mode",
            "analysis",
            "--capability-trigger",
            "write-anything",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "unknown_capability_trigger" in result.stderr


@pytest.mark.parametrize(
    ("mode", "controller"),
    [
        ("analysis", None),
        ("implementation", "health-harness-orchestrator"),
        ("incident", "health-harness-orchestrator"),
    ],
)
def test_every_non_release_mode_has_zero_or_one_expected_controller(mode, controller):
    result = _recommend("--mode", mode)

    assert result["controller"] == controller
    assert result["controller_count"] == int(controller is not None)
    assert len({item for item in result["overlays"]}) == len(result["overlays"])
    _assert_activation_partition(result)


def test_incident_route_adds_debugging_as_a_capability_not_a_controller():
    result = _recommend("--mode", "incident")

    assert "systematic-debugging" in result["capabilities"]
    assert result["controller"] != "systematic-debugging"


def test_release_route_requires_one_target_and_selects_one_terminal_skill():
    result = _recommend("--mode", "release", "--release-target", "mobile-ota")

    assert result["controller"] == "mobile-ota"
    assert result["controller_count"] == 1


def test_unknown_overlay_fails_closed():
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "recommend",
            "--mode",
            "feature",
            "--overlay",
            "unknown-overlay",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "unknown_overlay" in result.stderr


def test_run_event_schema_is_closed_and_cannot_store_raw_health_or_prompt_text():
    assert EVENT_SCHEMA.is_file()
    schema = json.loads(EVENT_SCHEMA.read_text(encoding="utf-8"))

    assert schema["$id"] == "agent-skill-run-event.v1"
    assert schema["additionalProperties"] is False
    properties = set(schema["properties"])
    expected_properties = {
        "run_id",
        "task_id",
        "task_mode",
        "selected_skills",
        "gate",
        "outcome",
        "duration_ms",
        "review_rounds",
        "manual_interventions",
        "reason_code",
        "validation_exit_code",
    }
    assert properties == expected_properties
    assert not properties & {
        "prompt",
        "raw_prompt",
        "health_text",
        "medication_name",
        "diagnosis",
        "secret",
        "token",
    }
    reason_code = schema["properties"]["reason_code"]
    assert set(reason_code) >= {"type", "enum"}
    assert "pattern" not in reason_code
    assert all("-" not in value and " " not in value for value in reason_code["enum"])

    for field in ("run_id", "task_id"):
        assert schema["properties"][field]["pattern"] == OPAQUE_UUID_PATTERN
        assert re.fullmatch(OPAQUE_UUID_PATTERN, "019c8f4a-7c40-7abc-8def-0123456789ab")
        assert not re.fullmatch(OPAQUE_UUID_PATTERN, "diet-two-bowls-user-request")


def test_registry_wires_the_append_only_trace_schema_and_benchmark_collector():
    registry = _registry()
    tracked_files = _tracked_project_files()

    assert registry["trace_event_schema"] == str(TRACE_EVENT_SCHEMA.relative_to(ROOT))
    assert registry["benchmark_collector"] == str(BENCHMARK_COLLECTOR.relative_to(ROOT))
    for path in (TRACE_EVENT_SCHEMA, BENCHMARK_COLLECTOR):
        assert path.is_file()
        assert str(path.relative_to(ROOT)) in tracked_files, path


@pytest.mark.parametrize(
    "mutation",
    [
        lambda schema: schema["properties"]["arm"]["enum"].append("free-form-arm"),
        lambda schema: schema["properties"]["timestamp_utc"].update({"pattern": ".*"}),
        lambda schema: schema["properties"]["source_sha256"].update({"pattern": ".*"}),
    ],
)
def test_checker_rejects_trace_vocabulary_or_integrity_pattern_drift(
    monkeypatch, mutation
):
    checker = _checker_module()
    schema = json.loads(TRACE_EVENT_SCHEMA.read_text(encoding="utf-8"))
    mutation(schema)
    monkeypatch.setattr(checker, "_load_json", lambda _path, _label: schema)

    with pytest.raises(checker.GovernanceError):
        checker._validate_trace_event_schema(TRACE_EVENT_SCHEMA)


def test_adapter_semantic_contracts_cover_every_platform_adapter_and_exact_content():
    registry = _registry()
    contracts = registry["adapter_contracts"]
    adapter_skills = {
        skill["id"]: skill for skill in registry["skills"] if "adapters" in skill
    }

    assert set(contracts) == set(adapter_skills)
    for skill_id, skill in adapter_skills.items():
        contract = contracts[skill_id]
        assert contract["version"] == skill["version"]
        assert len(contract["required_markers"]) >= 5
        assert set(contract["adapter_sha256"]) == set(skill["adapters"])
        for platform, path in skill["adapters"].items():
            content = (ROOT / path).read_text(encoding="utf-8")
            assert all(marker in content for marker in contract["required_markers"]), (
                skill_id,
                platform,
            )


def test_adapter_semantic_mutation_is_rejected_before_a_route_can_use_it():
    checker = _checker_module()
    registry = _registry()

    for skill in registry["skills"]:
        if "adapters" not in skill:
            continue
        contract = registry["adapter_contracts"][skill["id"]]
        marker = contract["required_markers"][0]
        for platform, path in skill["adapters"].items():
            content = (ROOT / path).read_text(encoding="utf-8")
            mutated = content.replace(marker, "")
            with pytest.raises(checker.GovernanceError) as exc:
                checker._validate_adapter_semantics(
                    skill["id"], platform, mutated, contract
                )
            assert exc.value.code == "adapter_semantic_marker_missing"


def test_governance_checker_accepts_the_committed_contract():
    result = subprocess.run(
        [sys.executable, str(CHECKER), "check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "agent-skill-governance: PASS" in result.stdout


@pytest.mark.parametrize(
    "path",
    [ROOT / "AGENTS.md", ROOT / "docs" / "agent-skill-binding.md"],
)
def test_project_entrypoints_route_before_loading_workflow_adapters(path: Path):
    text = path.read_text(encoding="utf-8")

    assert "reva-workflow-router" in text
    assert "scripts/check_agent_skill_governance.py recommend" in text


@pytest.mark.parametrize(
    "path",
    [ROOT / "AGENTS.md", ROOT / "docs" / "agent-skill-binding.md"],
)
def test_project_entrypoints_route_before_loading_system_map(path: Path):
    text = path.read_text(encoding="utf-8")

    assert text.index("scripts/check_agent_skill_governance.py recommend") < text.index(
        "scripts/system_map_context.py"
    )


def test_agents_contract_is_concise_and_does_not_embed_a_skill_catalog():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert len(text.encode("utf-8")) <= 10 * 1024
    assert "<skills_system" not in text
    assert "## Available Skills" not in text
    assert "npx openskills read" not in text
    assert "非仓库元任务" in text
    assert "immediate_skills" in text
    assert "deferred_by_phase.on_demand" in text
    assert "activation_skills" in text
    assert "selected_skills" in text
    assert "禁止作为预载清单" in text


def test_governance_contract_version_and_compatibility_fields_match_v2():
    text = (
        ROOT / "docs" / "governance" / "agent-skill-governance.md"
    ).read_text(encoding="utf-8")

    assert "**版本：** 2.0" in "\n".join(text.splitlines()[:10])
    assert "`selected_skills` / `selected_skill_details` 保留 v1 的非 delegate 选择" in text
    assert "`deferred_skills` / `deferred_skill_details` 只保留 delegate" in text
    assert "`activation_skills` / `activation_skill_details`" in text
    assert "不得驱动预载" in text


def test_codex_router_documents_supported_capability_trigger():
    router = (
        ROOT
        / "plugins"
        / "reva-health-harness"
        / "skills"
        / "reva-workflow-router"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "--capability-trigger <canonical-id>" in router


@pytest.mark.parametrize(
    "path",
    [
        ROOT / ".claude" / "skills" / "reva-workflow-router" / "SKILL.md",
        ROOT
        / "plugins"
        / "reva-health-harness"
        / "skills"
        / "reva-workflow-router"
        / "SKILL.md",
    ],
)
def test_router_adapters_load_by_activation_phase_not_compatibility_union(path: Path):
    text = path.read_text(encoding="utf-8")

    assert "immediate_skills" in text
    assert "deferred_by_phase" in text
    assert "activation_skills" in text
    assert "selected_skills" in text
    assert "selected_skills cannot be used as a preload list" in text
    assert "v1 non-delegate selection" in text
    assert "v1 delegate-only compatibility view" in text


@pytest.mark.parametrize(
    "path",
    [
        ROOT / ".claude" / "skills" / "health-harness-orchestrator" / "SKILL.md",
        ROOT
        / "plugins"
        / "reva-health-harness"
        / "skills"
        / "health-harness-orchestrator"
        / "SKILL.md",
    ],
)
def test_health_harness_adapters_activate_system_map_only_on_demand(path: Path):
    text = path.read_text(encoding="utf-8")

    assert "deferred_by_phase.on_demand" in text
    assert "system-map" in text
    assert "docs/system-map/INDEX.md" not in text
    assert "docs/_generated/system-map-agent-context.md" not in text
