#!/usr/bin/env python3
"""Validate and query the Reva development-agent Skill governance contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "governance" / "agent-skill-registry.json"

SCHEMA_VERSION = "agent-skill-registry.v1"
LIFECYCLE = ["experimental", "recommended", "standard", "deprecated"]
LAYERS = ["platform", "workflow", "incubator"]
KINDS = ["router", "controller", "capability", "overlay", "terminal"]
MODES = ["analysis", "quick_fix", "feature", "implementation", "incident", "release"]
ACTIVATION_PHASES = [
    "immediate",
    "diagnosis",
    "on_demand",
    "implementation",
    "verification",
    "S5",
]
PLATFORMS = {"agent-neutral", "claude", "codex"}

STANDARD_FIELDS = {
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
SAFE_EVENT_FIELDS = {
    "run_id",
    "task_id",
    "task_mode",
    "selected_skills",
    "gate",
    "outcome",
    "validation_exit_code",
    "duration_ms",
    "review_rounds",
    "manual_interventions",
    "reason_code",
}
TRACE_EVENT_FIELDS = {
    "schema_version",
    "run_id",
    "task_id",
    "arm",
    "task_mode",
    "stage",
    "outcome",
    "timestamp_utc",
    "sequence",
    "source_sha256",
    "registry_sha256",
    "route_sha256",
    "evidence_sha256",
    "prev_event_sha256",
    "event_sha256",
}
TRACE_ARMS = ["transition_v0_observational", "router_v1_prospective"]
TRACE_STAGES = [
    "run_started",
    "route_selected",
    "root_cause_identified",
    "red_test_observed",
    "green_test_observed",
    "g3_decided",
    "g4_decided",
    "g5_decided",
    "g6_decided",
    "manual_intervention",
    "run_finished",
]
TRACE_OUTCOMES = [
    "pending",
    "pass",
    "fail",
    "blocked",
    "not_applicable",
    "cancelled",
]
TRACE_TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:"
    r"[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"
)
REASON_CODES = {
    "none",
    "completed",
    "validation_failed",
    "governance_blocked",
    "safety_blocked",
    "route_rejected",
    "manual_decision_required",
    "dependency_unavailable",
    "budget_exhausted",
    "release_failed",
    "user_cancelled",
    "unknown_failure",
}
SENSITIVE_FIELD_FRAGMENTS = {
    "prompt",
    "healthtext",
    "medication",
    "diagnosis",
    "secret",
    "token",
}
CODEX_FORBIDDEN = {
    "TeamCreate",
    "TaskCreate",
    "SendMessage",
    'model: "opus"',
    "Co-Authored-By: Claude",
}
AGENT_NEUTRAL_FORBIDDEN = CODEX_FORBIDDEN | {
    "CLAUDE.md",
    "`backend-engineer`/",
    "`release-engineer` agent",
    "subagent_type",
    "[[",
}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_UUID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[4-7][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
OPAQUE_UUID4_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class GovernanceError(Exception):
    """A deterministic, user-actionable governance failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise GovernanceError(code, detail)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    _require(path.is_file(), "missing_file", f"{label}: {path.relative_to(ROOT)}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GovernanceError("invalid_json", f"{label}: {exc}") from exc
    _require(
        isinstance(value, dict), "invalid_document", f"{label} must be a JSON object"
    )
    return value


def _repo_file(relative: object, label: str) -> Path:
    _require(
        isinstance(relative, str) and bool(relative),
        "invalid_path",
        f"{label} must be a path",
    )
    candidate = (ROOT / relative).resolve()
    _require(candidate.is_relative_to(ROOT), "path_escape", f"{label}: {relative}")
    _require(candidate.is_file(), "missing_file", f"{label}: {relative}")
    return candidate


def _tracked_files() -> frozenset[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise GovernanceError(
            "tracked_file_inventory_failed", "git ls-files could not start"
        ) from exc
    _require(
        result.returncode == 0,
        "tracked_file_inventory_failed",
        f"git ls-files exited {result.returncode}",
    )
    return frozenset(
        os.fsdecode(relative) for relative in result.stdout.split(b"\0") if relative
    )


def _require_tracked(
    relative: str, label: str, tracked_files: frozenset[str]
) -> None:
    _require(relative in tracked_files, "untracked_source", f"{label}: {relative}")


def _string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    _require(isinstance(value, list), "invalid_list", f"{label} must be a list")
    _require(allow_empty or bool(value), "empty_list", f"{label} must not be empty")
    _require(
        all(isinstance(item, str) and bool(item) for item in value),
        "invalid_list_item",
        f"{label} must contain non-empty strings",
    )
    result = list(value)
    _require(
        len(result) == len(set(result)),
        "duplicate_item",
        f"{label} contains duplicates",
    )
    return result


def _validate_date(value: object, label: str) -> None:
    _require(isinstance(value, str), "invalid_date", f"{label} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise GovernanceError("invalid_date", f"{label}: {value}") from exc


def _validate_sources(skill: dict[str, Any], tracked_files: frozenset[str]) -> None:
    sources = _string_list(skill.get("sources"), f"skills.{skill['id']}.sources")
    for source in sources:
        source_path = _repo_file(source, f"skills.{skill['id']}.sources")
        _require_tracked(source, f"skills.{skill['id']}.sources", tracked_files)
        if skill["platforms"] != ["agent-neutral"] or not source.endswith("SKILL.md"):
            continue
        content = source_path.read_text(encoding="utf-8")
        leaked = sorted(token for token in AGENT_NEUTRAL_FORBIDDEN if token in content)
        _require(
            not leaked,
            "agent_neutral_source_leak",
            f"skills.{skill['id']}: {', '.join(leaked)}",
        )

    adapters = skill.get("adapters", {})
    _require(
        isinstance(adapters, dict), "invalid_adapters", f"skills.{skill['id']}.adapters"
    )
    for platform, relative in adapters.items():
        _require(
            platform in PLATFORMS,
            "unknown_platform",
            f"skills.{skill['id']}: {platform}",
        )
        _require(
            platform in skill["platforms"],
            "adapter_platform_mismatch",
            f"skills.{skill['id']}: {platform}",
        )
        _require(
            relative in sources,
            "adapter_source_missing",
            f"skills.{skill['id']}: {relative}",
        )
        adapter_path = _repo_file(relative, f"skills.{skill['id']}.adapters.{platform}")
        if platform != "codex":
            continue
        content = adapter_path.read_text(encoding="utf-8")
        leaked = sorted(token for token in CODEX_FORBIDDEN if token in content)
        _require(
            not leaked,
            "codex_adapter_leak",
            f"skills.{skill['id']}: {', '.join(leaked)}",
        )
        _require("Codex" in content, "codex_adapter_identity", f"skills.{skill['id']}")
        _require(
            "docs/governance/agent-skill-registry.json" in content,
            "codex_adapter_registry_missing",
            f"skills.{skill['id']}",
        )
        _require(
            "docs/governance/agent-skill-governance.md" in content,
            "codex_adapter_contract_missing",
            f"skills.{skill['id']}",
        )


def _validate_adapter_semantics(
    skill_id: str,
    platform: str,
    content: str,
    contract: dict[str, Any],
) -> None:
    markers = _string_list(
        contract.get("required_markers"),
        f"adapter_contracts.{skill_id}.required_markers",
    )
    missing = [marker for marker in markers if marker not in content]
    _require(
        not missing,
        "adapter_semantic_marker_missing",
        f"{skill_id}.{platform}: {', '.join(missing)}",
    )
    hashes = contract.get("adapter_sha256")
    _require(
        isinstance(hashes, dict),
        "invalid_adapter_digest",
        f"adapter_contracts.{skill_id}.adapter_sha256",
    )
    expected = hashes.get(platform)
    _require(
        isinstance(expected, str) and SHA256_RE.fullmatch(expected) is not None,
        "invalid_adapter_digest",
        f"{skill_id}.{platform}",
    )
    actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
    _require(actual == expected, "adapter_content_drift", f"{skill_id}.{platform}")


def _validate_adapter_contracts(
    value: object,
    skills: dict[str, dict[str, Any]],
) -> None:
    _require(isinstance(value, dict), "invalid_adapter_contracts", "must be an object")
    adapter_skills = {
        skill_id for skill_id, skill in skills.items() if "adapters" in skill
    }
    _require(
        set(value) == adapter_skills,
        "adapter_contract_coverage",
        "adapter Skill set drifted",
    )
    for skill_id in sorted(adapter_skills):
        contract = value[skill_id]
        _require(isinstance(contract, dict), "invalid_adapter_contract", skill_id)
        _require(
            set(contract) == {"version", "required_markers", "adapter_sha256"},
            "invalid_adapter_contract",
            skill_id,
        )
        _require(
            contract.get("version") == skills[skill_id]["version"],
            "adapter_version_drift",
            skill_id,
        )
        hashes = contract.get("adapter_sha256")
        _require(
            isinstance(hashes, dict)
            and set(hashes) == set(skills[skill_id]["adapters"]),
            "adapter_digest_coverage",
            skill_id,
        )
        for platform, relative in skills[skill_id]["adapters"].items():
            content = _repo_file(
                relative, f"skills.{skill_id}.adapters.{platform}"
            ).read_text(encoding="utf-8")
            _validate_adapter_semantics(skill_id, platform, content, contract)


def _validate_skill(
    skill: object, seen: set[str], tracked_files: frozenset[str]
) -> dict[str, Any]:
    _require(
        isinstance(skill, dict), "invalid_skill", "each skills item must be an object"
    )
    skill_id = skill.get("id")
    _require(
        isinstance(skill_id, str) and ID_RE.fullmatch(skill_id) is not None,
        "invalid_skill_id",
        str(skill_id),
    )
    _require(skill_id not in seen, "duplicate_skill", skill_id)
    seen.add(skill_id)

    lifecycle = skill.get("lifecycle")
    _require(lifecycle in LIFECYCLE, "invalid_lifecycle", f"{skill_id}: {lifecycle}")
    if lifecycle == "standard":
        missing = sorted(STANDARD_FIELDS - set(skill))
        _require(
            not missing,
            "standard_metadata_missing",
            f"{skill_id}: {', '.join(missing)}",
        )

    _require(
        isinstance(skill.get("owner"), str) and bool(skill["owner"]),
        "invalid_owner",
        skill_id,
    )
    _require(
        isinstance(skill.get("version"), str) and SEMVER_RE.fullmatch(skill["version"]),
        "invalid_version",
        skill_id,
    )
    _require(
        skill.get("layer") in LAYERS,
        "invalid_layer",
        f"{skill_id}: {skill.get('layer')}",
    )
    _require(
        skill.get("kind") in KINDS, "invalid_kind", f"{skill_id}: {skill.get('kind')}"
    )

    platforms = _string_list(skill.get("platforms"), f"skills.{skill_id}.platforms")
    unknown_platforms = sorted(set(platforms) - PLATFORMS)
    _require(
        not unknown_platforms,
        "unknown_platform",
        f"{skill_id}: {', '.join(unknown_platforms)}",
    )
    _string_list(skill.get("trigger_family"), f"skills.{skill_id}.trigger_family")
    _validate_date(skill.get("last_reviewed"), f"skills.{skill_id}.last_reviewed")
    _string_list(skill.get("evidence"), f"skills.{skill_id}.evidence")
    _validate_sources(skill, tracked_files)
    return skill


def _validate_external(
    value: object, project_ids: set[str]
) -> dict[str, dict[str, Any]]:
    _require(
        isinstance(value, list), "invalid_external_recommendations", "must be a list"
    )
    external: dict[str, dict[str, Any]] = {}
    for item in value:
        _require(
            isinstance(item, dict),
            "invalid_external_recommendation",
            "each item must be an object",
        )
        item_id = item.get("id")
        _require(
            isinstance(item_id, str) and ID_RE.fullmatch(item_id),
            "invalid_skill_id",
            str(item_id),
        )
        _require(
            item_id not in project_ids and item_id not in external,
            "duplicate_skill",
            item_id,
        )
        _require(
            isinstance(item.get("version"), str)
            and SEMVER_RE.fullmatch(item["version"]),
            "invalid_version",
            item_id,
        )
        _require(
            item.get("lifecycle") in LIFECYCLE,
            "invalid_lifecycle",
            f"{item_id}: {item.get('lifecycle')}",
        )
        _require(
            item.get("kind") in KINDS, "invalid_kind", f"{item_id}: {item.get('kind')}"
        )
        _require(
            isinstance(item.get("allow_direct_controller"), bool),
            "invalid_controller_policy",
            item_id,
        )
        _require(
            isinstance(item.get("reason"), str) and bool(item["reason"]),
            "missing_reason",
            item_id,
        )
        if item["lifecycle"] == "deprecated":
            _require(
                item["allow_direct_controller"] is False,
                "deprecated_controller_enabled",
                item_id,
            )
        external[item_id] = item
    return external


def _skill_kind(skill_id: str, known: dict[str, dict[str, Any]]) -> str:
    _require(skill_id in known, "unknown_skill", skill_id)
    return str(known[skill_id]["kind"])


def _validate_best_set(
    registry: dict[str, Any], known: dict[str, dict[str, Any]], router_id: str
) -> None:
    best = registry.get("best_skill_set")
    _require(isinstance(best, dict), "invalid_best_skill_set", "must be an object")
    _require(
        best.get("router") == router_id, "router_mismatch", str(best.get("router"))
    )
    baseline = _string_list(
        best.get("baseline_capabilities"), "best_skill_set.baseline_capabilities"
    )
    controllers = _string_list(
        best.get("primary_controllers"), "best_skill_set.primary_controllers"
    )
    _require(
        not set(baseline) & set(controllers),
        "role_conflict",
        "capability is also a controller",
    )
    for skill_id in baseline:
        _require(
            _skill_kind(skill_id, known) == "capability", "invalid_capability", skill_id
        )
    for skill_id in controllers:
        _require(
            _skill_kind(skill_id, known) == "controller", "invalid_controller", skill_id
        )


def _validate_routes(
    registry: dict[str, Any], known: dict[str, dict[str, Any]]
) -> None:
    routing = registry.get("routing")
    _require(isinstance(routing, dict), "invalid_routing", "routing must be an object")
    routes = routing.get("routes")
    _require(
        isinstance(routes, dict) and list(routes) == MODES,
        "invalid_modes",
        "routes must use the closed mode set in canonical order",
    )

    for mode in MODES:
        route = routes[mode]
        _require(isinstance(route, dict), "invalid_route", mode)
        _require(
            set(route) == {"controller", "delegates", "capabilities"},
            "invalid_route_fields",
            mode,
        )
        controller = route["controller"]
        _require(
            controller is None or isinstance(controller, str),
            "invalid_controller",
            mode,
        )
        if controller is not None:
            _require(
                _skill_kind(controller, known) == "controller",
                "invalid_controller",
                f"{mode}: {controller}",
            )
            _require(
                known[controller].get("lifecycle") != "deprecated",
                "deprecated_controller",
                controller,
            )
        delegates = _string_list(
            route["delegates"], f"routing.routes.{mode}.delegates", allow_empty=True
        )
        capabilities = _string_list(
            route["capabilities"],
            f"routing.routes.{mode}.capabilities",
            allow_empty=True,
        )
        _require(controller not in delegates, "controller_cycle", mode)
        for delegate in delegates:
            _require(
                _skill_kind(delegate, known) == "controller",
                "invalid_delegate",
                f"{mode}: {delegate}",
            )
        for capability in capabilities:
            _require(
                _skill_kind(capability, known) == "capability",
                "invalid_capability",
                f"{mode}: {capability}",
            )
        if mode == "release":
            _require(
                controller is None,
                "release_controller_conflict",
                "release controller comes from one target",
            )

    overlays = routing.get("overlays")
    _require(
        isinstance(overlays, dict) and bool(overlays),
        "invalid_overlays",
        "must be a non-empty object",
    )
    for trigger, skill_ids in overlays.items():
        _require(
            isinstance(trigger, str) and ID_RE.fullmatch(trigger),
            "invalid_overlay",
            str(trigger),
        )
        for skill_id in _string_list(skill_ids, f"routing.overlays.{trigger}"):
            _require(
                _skill_kind(skill_id, known) == "overlay",
                "invalid_overlay_skill",
                f"{trigger}: {skill_id}",
            )

    capability_triggers = routing.get("capability_triggers")
    _require(
        isinstance(capability_triggers, dict) and bool(capability_triggers),
        "invalid_capability_triggers",
        "must be a non-empty object",
    )
    for trigger, skill_ids in capability_triggers.items():
        _require(
            isinstance(trigger, str) and ID_RE.fullmatch(trigger),
            "invalid_capability_trigger",
            str(trigger),
        )
        for skill_id in _string_list(
            skill_ids, f"routing.capability_triggers.{trigger}"
        ):
            _require(
                _skill_kind(skill_id, known) == "capability",
                "invalid_capability_trigger_skill",
                f"{trigger}: {skill_id}",
            )

    targets = routing.get("release_targets")
    _require(
        isinstance(targets, dict) and bool(targets),
        "invalid_release_targets",
        "must be a non-empty object",
    )
    for target, skill_id in targets.items():
        _require(
            isinstance(target, str) and ID_RE.fullmatch(target),
            "invalid_release_target",
            str(target),
        )
        _require(isinstance(skill_id, str), "invalid_release_skill", str(skill_id))
        _require(
            _skill_kind(skill_id, known) == "terminal",
            "invalid_release_skill",
            f"{target}: {skill_id}",
        )

    policy = routing.get("activation_policy")
    _require(
        isinstance(policy, dict),
        "invalid_activation_policy",
        "routing.activation_policy must be an object",
    )
    _require(
        set(policy)
        == {
            "phases",
            "role_phases",
            "capability_phases",
            "capability_trigger_phase",
            "eager_phases_by_mode",
            "delegate_phases",
        },
        "invalid_activation_policy",
        "activation policy fields drifted",
    )
    _require(
        policy["phases"] == ACTIVATION_PHASES,
        "invalid_activation_phase",
        "closed activation phase vocabulary drifted",
    )

    role_phases = policy["role_phases"]
    immediate_roles = {"router", "controller", "overlay", "terminal"}
    _require(
        isinstance(role_phases, dict) and set(role_phases) == immediate_roles,
        "invalid_activation_policy",
        "role_phases must cover all immediate ownership roles",
    )
    for role, phase in role_phases.items():
        _require(
            phase in ACTIVATION_PHASES,
            "invalid_activation_phase",
            f"role_phases.{role}: {phase}",
        )
        _require(
            phase == "immediate",
            "invalid_activation_policy",
            f"role_phases.{role} must be immediate",
        )

    capability_phases = policy["capability_phases"]
    _require(
        isinstance(capability_phases, dict),
        "invalid_activation_policy",
        "capability_phases must be an object",
    )
    route_capabilities = {
        skill_id for route in routes.values() for skill_id in route["capabilities"]
    }
    _require(
        set(capability_phases) == route_capabilities,
        "activation_policy_coverage",
        "capability phase coverage drifted",
    )
    for skill_id, phase in capability_phases.items():
        _require(
            _skill_kind(skill_id, known) == "capability",
            "invalid_activation_capability",
            skill_id,
        )
        _require(
            phase in ACTIVATION_PHASES,
            "invalid_activation_phase",
            f"capability_phases.{skill_id}: {phase}",
        )

    trigger_phase = policy["capability_trigger_phase"]
    _require(
        trigger_phase in ACTIVATION_PHASES,
        "invalid_activation_phase",
        f"capability_trigger_phase: {trigger_phase}",
    )
    _require(
        trigger_phase == "immediate",
        "invalid_activation_policy",
        "authoring capability triggers must be immediate",
    )

    eager_by_mode = policy["eager_phases_by_mode"]
    _require(
        isinstance(eager_by_mode, dict),
        "invalid_activation_policy",
        "eager_phases_by_mode must be an object",
    )
    unknown_eager_modes = sorted(set(eager_by_mode) - set(MODES))
    _require(
        not unknown_eager_modes,
        "invalid_activation_mode",
        ", ".join(unknown_eager_modes),
    )
    for eager_mode, phases in eager_by_mode.items():
        for phase in _string_list(
            phases, f"routing.activation_policy.eager_phases_by_mode.{eager_mode}"
        ):
            _require(
                phase in ACTIVATION_PHASES,
                "invalid_activation_phase",
                f"eager_phases_by_mode.{eager_mode}: {phase}",
            )

    delegate_phases = policy["delegate_phases"]
    _require(
        isinstance(delegate_phases, dict),
        "invalid_activation_policy",
        "delegate_phases must be an object",
    )
    expected_delegate_modes = {
        mode for mode, route in routes.items() if route["delegates"]
    }
    _require(
        set(delegate_phases) == expected_delegate_modes,
        "activation_policy_coverage",
        "delegate phase mode coverage drifted",
    )
    for delegate_mode, phases_by_skill in delegate_phases.items():
        _require(
            isinstance(phases_by_skill, dict)
            and set(phases_by_skill) == set(routes[delegate_mode]["delegates"]),
            "activation_policy_coverage",
            f"delegate phase coverage drifted: {delegate_mode}",
        )
        for skill_id, phase in phases_by_skill.items():
            _require(
                phase in ACTIVATION_PHASES,
                "invalid_activation_phase",
                f"delegate_phases.{delegate_mode}.{skill_id}: {phase}",
            )


def _canonical_field(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def _schema_property_names(node: object) -> list[str]:
    if isinstance(node, list):
        return [name for item in node for name in _schema_property_names(item)]
    if not isinstance(node, dict):
        return []
    names: list[str] = []
    properties = node.get("properties")
    if isinstance(properties, dict):
        names.extend(str(name) for name in properties)
    for value in node.values():
        names.extend(_schema_property_names(value))
    return names


def _validate_closed_schema_objects(node: object, location: str = "event") -> None:
    if isinstance(node, list):
        for index, item in enumerate(node):
            _validate_closed_schema_objects(item, f"{location}[{index}]")
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" or "properties" in node:
        _require(
            node.get("additionalProperties") is False, "event_schema_open", location
        )
    for key, value in node.items():
        _validate_closed_schema_objects(value, f"{location}.{key}")


def _validate_event_schema(path: Path) -> None:
    schema = _load_json(path, "event_schema")
    _require(
        schema.get("$id") == "agent-skill-run-event.v1",
        "event_schema_id",
        str(schema.get("$id")),
    )
    _require(
        schema.get("type") == "object", "event_schema_type", "top level must be object"
    )
    _require(
        schema.get("additionalProperties") is False,
        "event_schema_open",
        "top level must be closed",
    )
    properties = schema.get("properties")
    _require(
        isinstance(properties, dict),
        "event_schema_properties",
        "properties must be an object",
    )
    _require(
        set(properties) == SAFE_EVENT_FIELDS,
        "event_schema_fields",
        "event fields must match the closed governance contract",
    )
    required = schema.get("required")
    _require(
        isinstance(required, list) and set(required) == SAFE_EVENT_FIELDS,
        "event_schema_required",
        "all governance fields must be required",
    )
    reason_code = properties.get("reason_code")
    _require(
        isinstance(reason_code, dict),
        "event_reason_code",
        "reason_code must be an object",
    )
    _require(
        reason_code.get("type") == "string"
        and set(reason_code.get("enum", [])) == REASON_CODES,
        "event_reason_code",
        "reason_code must use the closed privacy-safe vocabulary",
    )
    _require(
        "pattern" not in reason_code,
        "event_reason_code",
        "reason_code cannot be free-form",
    )
    task_mode = properties.get("task_mode")
    _require(
        isinstance(task_mode, dict) and task_mode.get("enum") == MODES,
        "event_schema_modes",
        "mode enum drifted",
    )
    for identifier in ("run_id", "task_id"):
        spec = properties.get(identifier)
        _require(
            isinstance(spec, dict) and spec.get("pattern") == OPAQUE_UUID_PATTERN,
            "event_identifier_not_opaque",
            identifier,
        )

    for field in _schema_property_names(schema):
        canonical = _canonical_field(field)
        leaked = sorted(
            fragment for fragment in SENSITIVE_FIELD_FRAGMENTS if fragment in canonical
        )
        _require(not leaked, "sensitive_event_field", f"{field}: {', '.join(leaked)}")

    _validate_closed_schema_objects(schema)
    definitions = schema.get("$defs")
    _require(
        isinstance(definitions, dict),
        "event_schema_definitions",
        "$defs must be an object",
    )
    for name, definition in definitions.items():
        if isinstance(definition, dict) and definition.get("type") == "object":
            _require(
                definition.get("additionalProperties") is False,
                "event_schema_open",
                f"$defs.{name}",
            )


def _validate_trace_event_schema(path: Path) -> None:
    schema = _load_json(path, "trace_event_schema")
    _require(
        schema.get("$id") == "agent-skill-run-trace-event.v1",
        "trace_event_schema_id",
        str(schema.get("$id")),
    )
    _require(
        schema.get("type") == "object",
        "trace_event_schema_type",
        "top level must be object",
    )
    _require(
        schema.get("additionalProperties") is False,
        "trace_event_schema_open",
        "top level must be closed",
    )
    properties = schema.get("properties")
    required = schema.get("required")
    _require(
        isinstance(properties, dict) and set(properties) == TRACE_EVENT_FIELDS,
        "trace_event_schema_fields",
        "trace fields must match the closed collector contract",
    )
    _require(
        isinstance(required, list) and set(required) == TRACE_EVENT_FIELDS,
        "trace_event_schema_required",
        "all trace fields must be required",
    )
    for identifier in ("run_id", "task_id"):
        spec = properties[identifier]
        _require(
            isinstance(spec, dict) and spec.get("pattern") == OPAQUE_UUID4_PATTERN,
            "trace_identifier_not_uuid4",
            identifier,
        )
    _require(
        properties["schema_version"] == {"const": "agent-skill-run-trace-event.v1"},
        "trace_schema_version_contract",
        "schema_version must be a fixed constant",
    )
    for field, expected in (
        ("arm", TRACE_ARMS),
        ("task_mode", MODES),
        ("stage", TRACE_STAGES),
        ("outcome", TRACE_OUTCOMES),
    ):
        _require(
            properties[field] == {"type": "string", "enum": expected},
            "trace_vocabulary_drift",
            field,
        )
    _require(
        properties["timestamp_utc"]
        == {"type": "string", "pattern": TRACE_TIMESTAMP_PATTERN},
        "trace_timestamp_contract",
        "timestamp_utc",
    )
    _require(
        properties["sequence"] == {"type": "integer", "minimum": 1},
        "trace_sequence_contract",
        "sequence",
    )
    required_digest = {"type": "string", "pattern": r"^[0-9a-f]{64}$"}
    nullable_digest = {"oneOf": [required_digest, {"type": "null"}]}
    for field in ("source_sha256", "registry_sha256", "event_sha256"):
        _require(
            properties[field] == required_digest,
            "trace_digest_contract",
            field,
        )
    for field in (
        "route_sha256",
        "evidence_sha256",
        "prev_event_sha256",
    ):
        _require(
            properties[field] == nullable_digest,
            "trace_digest_contract",
            field,
        )
    for field in _schema_property_names(schema):
        canonical = _canonical_field(field)
        leaked = sorted(
            fragment for fragment in SENSITIVE_FIELD_FRAGMENTS if fragment in canonical
        )
        _require(not leaked, "sensitive_trace_field", f"{field}: {', '.join(leaked)}")


def _validate_local_skill_coverage(
    project_ids: set[str], tracked_files: set[str]
) -> None:
    prefix = ".claude/skills/"
    suffix = "/SKILL.md"
    discovered = {
        path.removeprefix(prefix).removesuffix(suffix)
        for path in tracked_files
        if path.startswith(prefix)
        and path.endswith(suffix)
        and "/" not in path.removeprefix(prefix).removesuffix(suffix)
    }
    missing = sorted(discovered - project_ids)
    stale = sorted(project_ids - discovered)
    _require(not missing, "unregistered_project_skill", ", ".join(missing))
    _require(not stale, "missing_project_skill", ", ".join(stale))


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    tracked_files = _tracked_files()
    _require(
        registry.get("schema_version") == SCHEMA_VERSION,
        "schema_version",
        str(registry.get("schema_version")),
    )
    _require(
        registry.get("lifecycle") == LIFECYCLE,
        "lifecycle_vocabulary",
        "closed lifecycle vocabulary drifted",
    )
    _require(
        registry.get("layers") == LAYERS,
        "layer_vocabulary",
        "closed layer vocabulary drifted",
    )
    _require(
        registry.get("kinds") == KINDS,
        "kind_vocabulary",
        "closed kind vocabulary drifted",
    )
    _validate_date(registry.get("last_reviewed"), "last_reviewed")

    _require(
        registry.get("contract") == "docs/governance/agent-skill-governance.md",
        "contract_path",
        str(registry.get("contract")),
    )
    _repo_file(registry["contract"], "contract")
    _require(
        registry.get("event_schema")
        == "docs/governance/agent-skill-run-event.schema.json",
        "event_schema_path",
        str(registry.get("event_schema")),
    )
    event_schema_path = _repo_file(registry["event_schema"], "event_schema")
    _require(
        registry.get("trace_event_schema")
        == "docs/governance/agent-skill-run-trace-event.schema.json",
        "trace_event_schema_path",
        str(registry.get("trace_event_schema")),
    )
    trace_event_schema_path = _repo_file(
        registry["trace_event_schema"], "trace_event_schema"
    )
    _require_tracked(
        registry["trace_event_schema"], "trace_event_schema", tracked_files
    )
    _require(
        registry.get("benchmark_collector") == "scripts/agent_skill_benchmark.py",
        "benchmark_collector_path",
        str(registry.get("benchmark_collector")),
    )
    _repo_file(registry["benchmark_collector"], "benchmark_collector")
    _require_tracked(
        registry["benchmark_collector"], "benchmark_collector", tracked_files
    )

    skills_value = registry.get("skills")
    _require(
        isinstance(skills_value, list) and bool(skills_value),
        "invalid_skills",
        "skills must be a non-empty list",
    )
    seen: set[str] = set()
    skills = [_validate_skill(item, seen, tracked_files) for item in skills_value]
    by_id = {skill["id"]: skill for skill in skills}
    routers = [skill["id"] for skill in skills if skill["kind"] == "router"]
    _require(
        routers == ["reva-workflow-router"],
        "router_count",
        f"expected one canonical router, got {routers}",
    )

    external = _validate_external(registry.get("external_recommendations"), set(by_id))
    known = {**by_id, **external}
    _validate_best_set(registry, known, routers[0])
    _validate_adapter_contracts(registry.get("adapter_contracts"), by_id)
    _validate_routes(registry, known)
    _validate_event_schema(event_schema_path)
    _validate_trace_event_schema(trace_event_schema_path)
    _validate_local_skill_coverage(set(by_id), tracked_files)

    for deprecated_id in ("using-superpowers", "executing-plans"):
        item = external.get(deprecated_id)
        _require(item is not None, "missing_deprecation", deprecated_id)
        _require(
            item["lifecycle"] == "deprecated", "invalid_deprecation", deprecated_id
        )
        _require(
            item["allow_direct_controller"] is False,
            "deprecated_controller_enabled",
            deprecated_id,
        )
    return registry


def load_and_validate() -> dict[str, Any]:
    return validate_registry(_load_json(REGISTRY_PATH, "registry"))


def recommend(
    registry: dict[str, Any],
    mode: str,
    overlay_triggers: list[str],
    capability_triggers: list[str],
    release_targets: list[str],
) -> dict[str, Any]:
    routes = registry["routing"]["routes"]
    _require(mode in routes, "unknown_mode", mode)

    overlay_map = registry["routing"]["overlays"]
    unknown_overlays = sorted(set(overlay_triggers) - set(overlay_map))
    _require(not unknown_overlays, "unknown_overlay", ", ".join(unknown_overlays))

    capability_map = registry["routing"]["capability_triggers"]
    unknown_capabilities = sorted(set(capability_triggers) - set(capability_map))
    _require(
        not unknown_capabilities,
        "unknown_capability_trigger",
        ", ".join(unknown_capabilities),
    )

    if mode == "release":
        _require(
            len(release_targets) == 1,
            "release_target_required",
            "release requires exactly one --release-target",
        )
        target = release_targets[0]
        release_map = registry["routing"]["release_targets"]
        _require(target in release_map, "unknown_release_target", target)
        controller = release_map[target]
    else:
        _require(not release_targets, "release_target_not_allowed", mode)
        target = None
        controller = routes[mode]["controller"]

    route = routes[mode]
    delegates = list(route["delegates"])
    capabilities = list(route["capabilities"])
    triggered_capabilities = sorted(
        {
            skill_id
            for trigger in capability_triggers
            for skill_id in capability_map[trigger]
        }
    )
    capabilities = list(dict.fromkeys([*capabilities, *triggered_capabilities]))
    overlays = sorted(
        {skill_id for trigger in overlay_triggers for skill_id in overlay_map[trigger]}
    )
    controller_count = int(controller is not None)
    _require(controller_count <= 1, "controller_conflict", mode)

    router = registry["best_skill_set"]["router"]
    known = {
        **{skill["id"]: skill for skill in registry["skills"]},
        **{skill["id"]: skill for skill in registry["external_recommendations"]},
    }
    policy = registry["routing"]["activation_policy"]
    eager_phases = set(policy["eager_phases_by_mode"].get(mode, []))
    triggered_set = set(triggered_capabilities)

    selections: list[tuple[str, str, str]] = [
        (router, "router", policy["role_phases"]["router"])
    ]
    if controller is not None:
        controller_role = (
            "terminal" if known[controller]["kind"] == "terminal" else "controller"
        )
        selections.append(
            (controller, controller_role, policy["role_phases"][controller_role])
        )
    for skill_id in capabilities:
        phase = (
            policy["capability_trigger_phase"]
            if skill_id in triggered_set
            else policy["capability_phases"][skill_id]
        )
        selections.append((skill_id, "capability", phase))
    selections.extend(
        (skill_id, "overlay", policy["role_phases"]["overlay"])
        for skill_id in overlays
    )
    selections.extend(
        (
            skill_id,
            "delegate",
            policy["delegate_phases"][mode][skill_id],
        )
        for skill_id in delegates
    )

    details_by_id: dict[str, dict[str, str]] = {}
    selection_order: list[str] = []
    for skill_id, role, phase in selections:
        if skill_id in details_by_id:
            continue
        selection_order.append(skill_id)
        details_by_id[skill_id] = {
            "id": skill_id,
            "version": known[skill_id]["version"],
            "role": role,
            "activation_phase": phase,
        }

    immediate_skills = [
        skill_id
        for skill_id in selection_order
        if details_by_id[skill_id]["activation_phase"] == "immediate"
        or details_by_id[skill_id]["activation_phase"] in eager_phases
    ]
    deferred_by_phase = {
        phase: [
            skill_id
            for skill_id in selection_order
            if details_by_id[skill_id]["activation_phase"] == phase
            and skill_id not in immediate_skills
        ]
        for phase in policy["phases"]
        if phase != "immediate"
    }
    deferred_by_phase = {
        phase: skill_ids
        for phase, skill_ids in deferred_by_phase.items()
        if skill_ids
    }
    phase_deferred_skills = [
        skill_id for skill_ids in deferred_by_phase.values() for skill_id in skill_ids
    ]
    activation_skills = [*immediate_skills, *phase_deferred_skills]
    activation_skill_details = [
        details_by_id[skill_id] for skill_id in activation_skills
    ]
    selected_skills = [
        skill_id
        for skill_id in selection_order
        if details_by_id[skill_id]["role"] != "delegate"
    ]
    selected_skill_details = [details_by_id[skill_id] for skill_id in selected_skills]
    deferred_skills = list(delegates)
    deferred_skill_details = [details_by_id[skill_id] for skill_id in deferred_skills]

    return {
        "schema_version": "agent-skill-recommendation.v2",
        "mode": mode,
        "router": router,
        "controller": controller,
        "controller_count": controller_count,
        "delegates": delegates,
        "immediate_skills": immediate_skills,
        "deferred_by_phase": deferred_by_phase,
        "activation_skills": activation_skills,
        "activation_skill_details": activation_skill_details,
        "deferred_skills": deferred_skills,
        "deferred_skill_details": deferred_skill_details,
        "capabilities": capabilities,
        "triggered_capabilities": triggered_capabilities,
        "overlays": overlays,
        "release_target": target,
        "selected_skills": selected_skills,
        "selected_skill_details": selected_skill_details,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate the committed governance contract")

    recommend_parser = subparsers.add_parser(
        "recommend", help="return one deterministic task route"
    )
    recommend_parser.add_argument("--mode", required=True)
    recommend_parser.add_argument("--overlay", action="append", default=[])
    recommend_parser.add_argument("--capability-trigger", action="append", default=[])
    recommend_parser.add_argument("--release-target", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        registry = load_and_validate()
        if args.command == "check":
            routing = registry["routing"]
            print(
                "agent-skill-governance: PASS "
                f"skills={len(registry['skills'])} "
                f"routes={len(routing['routes'])} "
                f"overlays={len(routing['overlays'])} "
                f"release_targets={len(routing['release_targets'])}"
            )
            return 0

        result = recommend(
            registry,
            args.mode,
            args.overlay,
            args.capability_trigger,
            args.release_target,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except GovernanceError as exc:
        print(f"agent-skill-governance: FAIL {exc.code}: {exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
