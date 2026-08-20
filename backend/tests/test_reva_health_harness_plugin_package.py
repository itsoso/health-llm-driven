from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "reva-health-harness"


def test_reva_health_harness_plugin_manifest_is_installable():
    manifest_path = PLUGIN / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "reva-health-harness"
    assert manifest["version"].startswith("0.2.0")
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
        "reva-workflow-router": "Reva Workflow Router",
    }

    for name, marker in expected_skills.items():
        skill_path = PLUGIN / "skills" / name / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        assert marker in content
        assert "docs/governance/agent-skill-registry.json" in content


def test_codex_adapters_are_native_and_do_not_copy_claude_only_instructions():
    forbidden = {
        "TeamCreate",
        "TaskCreate",
        "SendMessage",
        'model: "opus"',
        "Co-Authored-By: Claude",
    }

    for name in ("product-pipeline", "health-harness-orchestrator"):
        codex = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        claude = (ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert codex != claude
        assert all(token not in codex for token in forbidden)
        assert "Codex" in codex
        assert "docs/governance/agent-skill-governance.md" in codex


def test_codex_router_is_the_only_implicitly_invoked_plugin_skill():
    for name in ("product-pipeline", "health-harness-orchestrator", "reva-workflow-router"):
        metadata_path = PLUGIN / "skills" / name / "agents" / "openai.yaml"
        text = metadata_path.read_text(encoding="utf-8")
        expected = "true" if name == "reva-workflow-router" else "false"
        assert f"allow_implicit_invocation: {expected}" in text

    for script_name in [
        "harness_workflow_trace.py",
        "harness_memory_prime.py",
        "harness_friction_scan.py",
        "harness_llm_change_gate.py",
    ]:
        assert (PLUGIN / "scripts" / script_name).read_text(encoding="utf-8") == (
            ROOT / "scripts" / script_name
        ).read_text(encoding="utf-8")


def test_product_pipeline_documents_quick_flow_and_correct_course():
    skill = (ROOT / ".claude" / "skills" / "product-pipeline" / "SKILL.md").read_text(encoding="utf-8")
    template = (ROOT / ".claude" / "skills" / "product-pipeline" / "dossier-template.md").read_text(
        encoding="utf-8"
    )

    assert "Quick Flow" in skill
    assert "全 6-Gate" in skill
    assert "升级为全流程" in skill
    assert "correct-course" in skill
    assert "Correction Block" in skill
    assert "## Correct Course" in template
    assert "旧基线" in template


def test_product_pipeline_documents_selective_memory_priming():
    skill = (ROOT / ".claude" / "skills" / "product-pipeline" / "SKILL.md").read_text(encoding="utf-8")

    assert "harness_memory_prime.py" in skill
    assert "MEMORY.md" in skill
    assert "选择性 priming" in skill


def test_product_pipeline_documents_friction_scan_as_advisory():
    skill = (ROOT / ".claude" / "skills" / "product-pipeline" / "SKILL.md").read_text(encoding="utf-8")

    assert "harness_friction_scan.py" in skill
    assert "摩擦检测" in skill
    assert "不自动改 memory 或 skill" in skill
