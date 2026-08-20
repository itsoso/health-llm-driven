from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "doc-drift-fix" / "SKILL.md"
SYSTEM_MAP_SKILL = ROOT / ".claude" / "skills" / "system-map" / "SKILL.md"
SYSTEM_MAP_INDEX = ROOT / "docs" / "system-map" / "INDEX.md"
AGENT_ENTRYPOINTS = (
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "agent-skill-binding.md",
)
SYSTEM_MAP_PROTOCOLS = (SYSTEM_MAP_SKILL, SYSTEM_MAP_INDEX)
AGENT_CONTEXT = "docs/_generated/system-map-agent-context.md"
EVIDENCE_ORDER = (
    "证据优先级：代码与测试 > 代码派生 System Map > 受审声明 > 带新鲜度的叙事"
)


def test_doc_drift_skill_uses_generated_map_instead_of_manual_counts() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "逐条改文档数字" not in text
    assert "删除手写动态计数" in text
    assert "./scripts/system-map-check.sh" in text
    assert "python scripts/dump_system_map.py" not in text
    assert "python scripts/check_doc_drift.py" not in text


def test_system_map_skill_documents_v2_admin_and_reproducible_gate() -> None:
    text = SYSTEM_MAP_SKILL.read_text(encoding="utf-8")

    assert "schema_version" in text
    assert "entities" in text
    assert "relations" in text
    assert "/admin/system-map" in text
    assert "./scripts/system-map-check.sh" in text
    assert "生成字段" in text
    assert "叙事" in text
    assert "mobile/scripts/dump_nav_graph.py --check" in text


def test_all_agent_entrypoints_require_compact_global_context() -> None:
    for path in AGENT_ENTRYPOINTS:
        text = path.read_text(encoding="utf-8")
        assert AGENT_CONTEXT in text, path


def test_system_map_protocol_requires_query_and_source_verification() -> None:
    for path in SYSTEM_MAP_PROTOCOLS:
        text = path.read_text(encoding="utf-8")
        assert "scripts/system_map_context.py" in text, path
        assert EVIDENCE_ORDER in text, path
        assert "地图不能替代源码和测试验证" in text, path
