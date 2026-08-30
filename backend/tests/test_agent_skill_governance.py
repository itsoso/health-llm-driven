from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

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
TOOLING_TESTS = (
    "backend/tests/test_agent_skill_governance.py",
    "backend/tests/test_agent_skill_manifests.py",
    "backend/tests/test_doc_drift_narrative_counts.py",
    "backend/tests/test_doc_drift_skill_contract.py",
    "backend/tests/test_dossier_consistency.py",
    "backend/tests/test_reva_health_harness_plugin_package.py",
    "backend/tests/test_system_map_agent_context.py",
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
    assert command[command.index("-o") + 1] == "addopts="
    assert "-q" in command
    assert "--strict-markers" in command
    assert "--tb=short" in command
    assert command[command.index("-p") + 1] == "no:cacheprovider"
    assert not any(argument.startswith("--cov") for argument in command)
    assert tuple(runner.DEFAULT_TESTS) == TOOLING_TESTS

    environment = runner.sanitized_environment(
        {"PYTEST_ADDOPTS": "--cov=app --cov-report=html", "KEEP_ME": "yes"}
    )
    assert "PYTEST_ADDOPTS" not in environment
    assert environment["KEEP_ME"] == "yes"


def test_tooling_pytest_runner_only_adds_benchmark_on_explicit_request():
    runner = _tooling_pytest_runner_module()

    default_command = runner.build_command(include_benchmark=False)
    benchmark_command = runner.build_command(include_benchmark=True)

    assert TOOLING_BENCHMARK_TEST not in default_command
    assert benchmark_command[-1] == TOOLING_BENCHMARK_TEST
    assert benchmark_command.count(TOOLING_BENCHMARK_TEST) == 1


def test_tooling_pytest_allowlist_is_present_and_ast_runtime_independent():
    runner = _tooling_pytest_runner_module()
    allowlist = (*runner.DEFAULT_TESTS, runner.BENCHMARK_TEST)

    assert tuple(runner.DEFAULT_TESTS) == TOOLING_TESTS
    assert runner.BENCHMARK_TEST == TOOLING_BENCHMARK_TEST
    assert len(runner.DEFAULT_TESTS) == 7

    for relative in allowlist:
        path = ROOT / relative
        assert path.is_file(), relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
                assert all(
                    name not in {"app", "main"}
                    and not name.startswith(("app.", "main."))
                    for name in imported
                ), (relative, imported)
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module not in {"app", "main"} and not module.startswith(
                    ("app.", "main.")
                ), (relative, module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                argument_names = {
                    argument.arg
                    for argument in (
                        *node.args.posonlyargs,
                        *node.args.args,
                        *node.args.kwonlyargs,
                    )
                }
                forbidden = {
                    name
                    for name in argument_names
                    if {"db", "client", "auth"} & set(name.split("_"))
                }
                assert not forbidden, (relative, node.name, forbidden)


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
    for skill in _registry()["skills"]:
        for source in skill["sources"]:
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", source],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, (skill["id"], source)


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

    assert registry["trace_event_schema"] == str(TRACE_EVENT_SCHEMA.relative_to(ROOT))
    assert registry["benchmark_collector"] == str(BENCHMARK_COLLECTOR.relative_to(ROOT))
    for path in (TRACE_EVENT_SCHEMA, BENCHMARK_COLLECTOR):
        assert path.is_file()
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert tracked.returncode == 0, path


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
