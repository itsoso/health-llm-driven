#!/usr/bin/env python3
"""Validate docs/system-map.json as the agent-readable product/system map."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path("docs/system-map.json")

REQUIRED_TOP_LEVEL = {
    "schema_version",
    "system",
    "authority",
    "capabilities",
    "surfaces",
    "workflows",
}
ALLOWED_STATUSES = {"implemented", "partial", "planned", "gap", "deprecated"}
IMPLEMENTED_STATUSES = {"implemented", "partial"}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iter_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        out: list[str] = []
        for child in value.values():
            out.extend(_iter_paths(child))
        return out
    return []


def _path_exists(root: Path, rel_path: str) -> bool:
    if rel_path.startswith(("http://", "https://")):
        return True
    return (root / rel_path).exists()


def _load_manifest(root: Path, failures: list[str]) -> dict[str, Any]:
    path = root / MANIFEST
    if not path.exists():
        failures.append(f"{MANIFEST}: missing")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"{MANIFEST}: invalid JSON at line {exc.lineno}: {exc.msg}")
        return {}
    if not isinstance(data, dict):
        failures.append(f"{MANIFEST}: root must be an object")
        return {}
    return data


def _validate_system(manifest: dict[str, Any], failures: list[str]) -> None:
    system = manifest.get("system")
    if not isinstance(system, dict):
        failures.append("system: must be an object")
        return
    for field in ("name", "goal", "north_star_metric"):
        if not _nonempty_string(system.get(field)):
            failures.append(f"system.{field}: required non-empty string")


def _validate_capabilities(root: Path, manifest: dict[str, Any], failures: list[str]) -> None:
    surfaces = {
        surface.get("id")
        for surface in _as_list(manifest.get("surfaces"))
        if isinstance(surface, dict) and _nonempty_string(surface.get("id"))
    }
    capabilities = _as_list(manifest.get("capabilities"))
    if not capabilities:
        failures.append("capabilities: must contain at least one capability")
        return

    for index, capability in enumerate(capabilities):
        label = f"capabilities[{index}]"
        if not isinstance(capability, dict):
            failures.append(f"{label}: must be an object")
            continue
        cap_id = capability.get("id")
        if not _nonempty_string(cap_id):
            failures.append(f"{label}.id: required non-empty string")
            cap_id = label
        status = capability.get("status")
        if status not in ALLOWED_STATUSES:
            failures.append(f"{cap_id}.status: expected one of {sorted(ALLOWED_STATUSES)}")
        cap_surfaces = _as_list(capability.get("surfaces"))
        if not cap_surfaces:
            failures.append(f"{cap_id}.surfaces: must reference at least one surface")
        for surface in cap_surfaces:
            if surface not in surfaces:
                failures.append(f"{cap_id}.surfaces: unknown surface '{surface}'")

        source = capability.get("source_of_truth")
        if not isinstance(source, dict):
            failures.append(f"{cap_id}.source_of_truth: required object")
            continue
        if not _iter_paths(source.get("prd")):
            failures.append(f"{cap_id}.source_of_truth.prd: must reference at least one PRD")
        if status in IMPLEMENTED_STATUSES:
            for group in ("code", "tests"):
                if not _iter_paths(source.get(group)):
                    failures.append(f"{cap_id}.source_of_truth.{group}: required for {status}")
        for rel_path in _iter_paths(source):
            if not _path_exists(root, rel_path):
                failures.append(f"{cap_id}: missing referenced path {rel_path}")


def _validate_surfaces(root: Path, manifest: dict[str, Any], failures: list[str]) -> None:
    surfaces = _as_list(manifest.get("surfaces"))
    if not surfaces:
        failures.append("surfaces: must contain at least one surface")
        return
    for index, surface in enumerate(surfaces):
        label = f"surfaces[{index}]"
        if not isinstance(surface, dict):
            failures.append(f"{label}: must be an object")
            continue
        surface_id = surface.get("id")
        if not _nonempty_string(surface_id):
            failures.append(f"{label}.id: required non-empty string")
            surface_id = label
        if not _nonempty_string(surface.get("role")):
            failures.append(f"{surface_id}.role: required non-empty string")
        paths = _iter_paths(surface.get("paths"))
        if not paths:
            failures.append(f"{surface_id}.paths: must reference at least one path")
        for rel_path in paths:
            if not _path_exists(root, rel_path):
                failures.append(f"{surface_id}: missing referenced path {rel_path}")


def _validate_workflows(root: Path, manifest: dict[str, Any], failures: list[str]) -> None:
    workflows = _as_list(manifest.get("workflows"))
    if not workflows:
        failures.append("workflows: must contain at least one workflow")
        return
    for index, workflow in enumerate(workflows):
        label = f"workflows[{index}]"
        if not isinstance(workflow, dict):
            failures.append(f"{label}: must be an object")
            continue
        workflow_id = workflow.get("id")
        if not _nonempty_string(workflow_id):
            failures.append(f"{label}.id: required non-empty string")
            workflow_id = label
        entry = workflow.get("entry")
        if not _nonempty_string(entry):
            failures.append(f"{workflow_id}.entry: required path")
        elif not _path_exists(root, entry):
            failures.append(f"{workflow_id}: missing referenced path {entry}")


def validate_system_map(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    manifest = _load_manifest(root, failures)
    if not manifest:
        return failures

    missing = sorted(REQUIRED_TOP_LEVEL - set(manifest))
    for field in missing:
        failures.append(f"{field}: missing top-level field")

    _validate_system(manifest, failures)

    for rel_path in _iter_paths(manifest.get("authority")):
        if not _path_exists(root, rel_path):
            failures.append(f"authority: missing referenced path {rel_path}")
    if not _iter_paths(manifest.get("authority")):
        failures.append("authority: must reference at least one source of truth")

    _validate_surfaces(root, manifest, failures)
    _validate_capabilities(root, manifest, failures)
    _validate_workflows(root, manifest, failures)
    return failures


def main() -> int:
    failures = validate_system_map(ROOT)
    if failures:
        print("❌ system-map.json validation failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("✅ system-map.json validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
