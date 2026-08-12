from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "doc-drift-fix" / "SKILL.md"
SYSTEM_MAP_SKILL = ROOT / ".claude" / "skills" / "system-map" / "SKILL.md"


def test_doc_drift_skill_uses_generated_map_instead_of_manual_counts() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "逐条改文档数字" not in text
    assert "删除手写动态计数" in text
    assert "python scripts/dump_system_map.py" in text
    assert "python scripts/check_doc_drift.py" in text


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
