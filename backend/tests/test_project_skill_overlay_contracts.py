from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_safety_overlay_covers_health_writes_notifications_and_supplements():
    skill = (ROOT / ".claude" / "skills" / "safety-gate" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for term in ("补剂", "提醒", "通知", "写路径", "隐私"):
        assert term in skill
    assert "overlay" in skill.lower()
    assert "不得" in skill and "ledger" in skill


def test_database_policy_matches_the_repository_hybrid_test_matrix():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    migration_skill = (
        ROOT / ".claude" / "skills" / "add-managed-migration" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "生产语义与新数据库行为必须用 PostgreSQL 验证" in agents
    assert "SQLite 只保留快速单元测试与迁移兼容性验证" in agents
    assert "PostgreSQL 语义集成" in migration_skill
    assert "SQLite 兼容性" in migration_skill
    assert "SQLite (已废弃)" not in migration_skill
