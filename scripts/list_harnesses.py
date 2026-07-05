#!/usr/bin/env python3
"""List health project harnesses from the local registry manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "harness" / "registry.json"
VALID_STAGES = {"commit", "ci", "runtime", "manual", "release"}


def _as_string_list(value: Any, field: str, harness_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{harness_id}.{field} must be a list of strings")
    return value


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("harness manifest must be a JSON object")
    project = manifest.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("id"), str):
        raise ValueError("harness manifest must include project.id")
    harnesses = manifest.get("harnesses")
    if not isinstance(harnesses, list):
        raise ValueError("harness manifest must include harnesses list")

    seen: set[str] = set()
    for item in harnesses:
        if not isinstance(item, dict):
            raise ValueError("each harness entry must be an object")
        harness_id = item.get("id")
        if not isinstance(harness_id, str) or not harness_id:
            raise ValueError("each harness entry must include id")
        if harness_id in seen:
            raise ValueError(f"duplicate harness id: {harness_id}")
        seen.add(harness_id)
        if item.get("stage") not in VALID_STAGES:
            raise ValueError(f"{harness_id}.stage must be one of {sorted(VALID_STAGES)}")
        command = item.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
            raise ValueError(f"{harness_id}.command must be a non-empty list of strings")
        for field in ("tags", "requires", "evidence_paths"):
            _as_string_list(item.get(field), field, harness_id)
    return manifest


def _normalize_harness(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "name": item.get("name") or item["id"],
        "stage": item["stage"],
        "command": item["command"],
        "working_dir": item.get("working_dir") or ".",
        "description": item.get("description") or "",
        "when_to_run": item.get("when_to_run") or "",
        "tags": item.get("tags") or [],
        "read_only": bool(item.get("read_only", True)),
        "blocking": bool(item.get("blocking", True)),
        "requires": item.get("requires") or [],
        "evidence_paths": item.get("evidence_paths") or [],
    }


def build_payload(manifest_path: Path, tag: str | None = None, stage: str | None = None) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    selected = [_normalize_harness(item) for item in manifest["harnesses"]]
    if tag:
        selected = [item for item in selected if tag in item["tags"]]
    if stage:
        selected = [item for item in selected if item["stage"] == stage]
    return {
        "schema_version": manifest.get("schema_version", 1),
        "project": manifest["project"],
        "source_path": str(manifest_path),
        "filters": {"tag": tag, "stage": stage},
        "count": len(selected),
        "harnesses": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List health eval/smoke/operating harnesses.")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Harness registry manifest. Defaults to harness/registry.json.",
    )
    parser.add_argument("--tag", help="Only include harnesses carrying this tag.")
    parser.add_argument(
        "--stage",
        choices=sorted(VALID_STAGES),
        help="Only include harnesses in this lifecycle stage.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    payload = build_payload(Path(args.manifest).resolve(), tag=args.tag, stage=args.stage)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    project = payload["project"]
    print(f"project: {project['id']}")
    print(f"manifest: {payload['source_path']}")
    print()
    for item in payload["harnesses"]:
        print(f"{item['id']} [{item['stage']}]")
        if item["description"]:
            print(f"  {item['description']}")
        if item["working_dir"] != ".":
            print(f"  cwd: {item['working_dir']}")
        print(f"  command: {' '.join(item['command'])}")
        if item["tags"]:
            print(f"  tags: {', '.join(item['tags'])}")
        if item["requires"]:
            print(f"  requires: {', '.join(item['requires'])}")
        print()
    print(f"count: {payload['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
