from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOBILE_RELEASE_SKILL = (
    ROOT / ".claude" / "skills" / "mobile-testflight-release" / "SKILL.md"
)
APP_STORE_PUBLICATION_REFERENCE = (
    ROOT / "docs" / "governance" / "app-store-publication.md"
)


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


def test_mobile_release_continues_through_public_app_store_readback():
    skill = MOBILE_RELEASE_SKILL.read_text(encoding="utf-8")
    publication = APP_STORE_PUBLICATION_REFERENCE.read_text(encoding="utf-8")

    assert "../../../docs/governance/app-store-publication.md" in skill
    assert "审核通过不等于公开上架" in skill

    ordered_states = (
        "Ready for Distribution",
        "Processing to Available",
        "Available",
        "public lookup resultCount=1",
    )
    recovery_path = publication[
        publication.index("一次缺少地区配置的恢复路径") : publication.index(
            "## 公开商店回读"
        )
    ]
    state_lines = [line.removeprefix("-> ") for line in recovery_path.splitlines()]
    positions = [state_lines.index(state) for state in ordered_states]
    assert positions == sorted(positions)

    assert "App Availability" in publication
    assert "仅在用户明确要求全球发布时" in publication
    assert "itunes.apple.com/lookup" in publication
    assert "最终确认" in publication
    assert "静默监控" in publication


def test_mobile_release_preserves_authorization_and_scope_boundaries():
    skill = MOBILE_RELEASE_SKILL.read_text(encoding="utf-8")
    publication = APP_STORE_PUBLICATION_REFERENCE.read_text(encoding="utf-8")

    assert "仅在已明确的 iOS 上架任务中" in skill
    assert "复用当前会话中仍适用的用户授权" in publication
    assert "已授权的相同范围不重复索取确认" in publication
    assert "仅在用户要求后续监控" in publication
    assert "未经授权不得联系 Apple" in publication
    assert "抽样地区通过不能代表全部地区" in publication
    assert "不要用\n一次旧确认覆盖数天后的新动作" not in publication
    assert "在最终确认前请求即时授权" not in publication
