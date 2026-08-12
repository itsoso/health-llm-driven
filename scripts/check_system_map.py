#!/usr/bin/env python3
"""Validate all generated System Map artifacts through one blocking gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SYSTEM_MAP = ROOT / "docs" / "_generated" / "system-map.json"
SYSTEM_MAP_SCHEMA = ROOT / "docs" / "_generated" / "system-map.schema.json"

sys.path.insert(0, str(SCRIPTS))
from system_map_contract import SystemMapContractError, validate_system_map  # noqa: E402


CHECKS = (
    ("system-map", [sys.executable, "scripts/dump_system_map.py", "--check"]),
    ("mobile-nav", [sys.executable, "mobile/scripts/dump_nav_graph.py", "--check"]),
    ("doc-drift", [sys.executable, "scripts/check_doc_drift.py"]),
)


def validate_artifact() -> None:
    """Validate the committed artifact against JSON Schema and graph semantics."""
    schema = json.loads(SYSTEM_MAP_SCHEMA.read_text(encoding="utf-8"))
    artifact = json.loads(SYSTEM_MAP.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(artifact)
    validate_system_map(artifact)


def main() -> int:
    try:
        validate_artifact()
    except (OSError, json.JSONDecodeError, SchemaError, ValidationError, SystemMapContractError) as exc:
        print(f"❌ System Map contract validation failed: {exc}", file=sys.stderr)
        return 1

    for name, argv in CHECKS:
        print(f"→ {name}")
        result = subprocess.run(argv, cwd=ROOT, check=False)
        if result.returncode != 0:
            print(f"❌ {name} failed with exit code {result.returncode}", file=sys.stderr)
            return result.returncode
    print("✅ System Map verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
