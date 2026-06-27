from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "check_system_map.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_system_map", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_file(path: Path, text: str = "ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_manifest(root: Path, manifest: dict) -> None:
    write_file(root / "docs" / "system-map.json", json.dumps(manifest, indent=2))


def minimal_manifest() -> dict:
    return {
        "schema_version": 1,
        "system": {
            "name": "Reva Personal Health OS",
            "goal": "Help users improve health through safe execution loops.",
            "north_star_metric": "Weekly completed high-leverage health actions.",
        },
        "authority": [
            "AGENTS.md",
            "docs/specs/reva-product-governance-spec.md",
        ],
        "capabilities": [
            {
                "id": "capture.quick-record",
                "name": "Quick record",
                "status": "partial",
                "surfaces": ["mobile"],
                "source_of_truth": {
                    "prd": ["docs/prd/reva-personal-health-os-prd.md"],
                    "plan": ["docs/plans/quick-record.md"],
                    "code": ["mobile/app/(tabs)/record.tsx"],
                    "tests": ["scripts/test_check_system_map.py"],
                },
                "safety_level": "privacy_sensitive",
                "deploy_paths": ["mobile_ota"],
            }
        ],
        "surfaces": [
            {
                "id": "mobile",
                "role": "Primary daily product",
                "paths": ["mobile/app"],
            }
        ],
        "workflows": [
            {
                "id": "requirement-to-deploy",
                "entry": "docs/workflows/requirement-to-deploy.md",
            }
        ],
    }


def test_valid_manifest_passes(tmp_path: Path) -> None:
    module = load_module()
    manifest = minimal_manifest()
    for path in [
        "AGENTS.md",
        "docs/specs/reva-product-governance-spec.md",
        "docs/prd/reva-personal-health-os-prd.md",
        "docs/plans/quick-record.md",
        "mobile/app/(tabs)/record.tsx",
        "scripts/test_check_system_map.py",
        "docs/workflows/requirement-to-deploy.md",
    ]:
        write_file(tmp_path / path)
    write_dir(tmp_path / "mobile/app")
    write_manifest(tmp_path, manifest)

    assert module.validate_system_map(tmp_path) == []


def test_missing_referenced_file_fails_loud(tmp_path: Path) -> None:
    module = load_module()
    manifest = minimal_manifest()
    write_file(tmp_path / "AGENTS.md")
    write_file(tmp_path / "docs/specs/reva-product-governance-spec.md")
    write_manifest(tmp_path, manifest)

    failures = module.validate_system_map(tmp_path)

    assert any("missing referenced path" in failure for failure in failures)


def test_capability_without_traceability_fails(tmp_path: Path) -> None:
    module = load_module()
    manifest = minimal_manifest()
    manifest["capabilities"][0]["source_of_truth"] = {"prd": []}
    write_file(tmp_path / "AGENTS.md")
    write_file(tmp_path / "docs/specs/reva-product-governance-spec.md")
    write_manifest(tmp_path, manifest)

    failures = module.validate_system_map(tmp_path)

    assert any("source_of_truth" in failure for failure in failures)
