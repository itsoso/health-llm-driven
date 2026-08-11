from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "doc-drift-fix" / "SKILL.md"


def test_doc_drift_skill_uses_generated_map_instead_of_manual_counts() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "逐条改文档数字" not in text
    assert "删除手写动态计数" in text
    assert "python scripts/dump_system_map.py" in text
    assert "python scripts/check_doc_drift.py" in text
