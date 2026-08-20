from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "governance" / "agent-skill-registry.json"
EVENT_SCHEMA = ROOT / "docs" / "governance" / "agent-skill-run-event.schema.json"
CHECKER = ROOT / "scripts" / "check_agent_skill_governance.py"


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
    assert result["overlays"] == ["add-managed-migration", "safety-gate"]
    assert result["controller_count"] == 1


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
    assert all(item["version"].count(".") == 2 for item in result["selected_skill_details"])
    assert {item["role"] for item in result["selected_skill_details"]} <= {
        "router",
        "controller",
        "delegate",
        "capability",
        "overlay",
        "terminal",
    }


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
    assert {
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
    } <= properties
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
