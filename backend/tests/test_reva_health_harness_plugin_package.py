from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "reva-health-harness"


def test_reva_health_harness_plugin_manifest_is_installable():
    manifest_path = PLUGIN / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "reva-health-harness"
    assert manifest["version"].startswith("0.1.0")
    assert manifest["skills"] == "./skills/"
    assert "hooks" not in manifest
    assert manifest["interface"]["displayName"] == "Reva Health Harness"
    assert "Health" in manifest["keywords"]
    assert manifest["author"]["name"] == "executor.life"


def test_reva_health_harness_marketplace_entry_points_to_repo_plugin():
    marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["name"] == "reva-health"
    assert marketplace["interface"]["displayName"] == "Reva Health"

    entries = {entry["name"]: entry for entry in marketplace["plugins"]}

    entry = entries["reva-health-harness"]
    assert entry["source"] == {"source": "local", "path": "./plugins/reva-health-harness"}
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
    assert entry["category"] == "Productivity"


def test_reva_health_harness_packages_core_project_skills():
    expected_skills = {
        "product-pipeline": "复元 Product Pipeline",
        "health-harness-orchestrator": "复元 Health Harness",
    }

    for name, marker in expected_skills.items():
        skill_path = PLUGIN / "skills" / name / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        assert marker in content
        assert "scripts/harness_workflow_trace.py" in content
        assert content == (ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")

    assert (PLUGIN / "scripts" / "harness_workflow_trace.py").read_text(encoding="utf-8") == (
        ROOT / "scripts" / "harness_workflow_trace.py"
    ).read_text(encoding="utf-8")
