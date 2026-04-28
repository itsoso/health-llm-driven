"""User Directive — fallback parser + 注入 + 撤销."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.user_directive import UserDirective
from app.services.directive_parser import (
    _fallback_parse,
    parse_and_store,
    get_active_directives_for_prompt,
)


# ─────────────── fallback parser (LLM 不可用时) ───────────────


class TestFallbackParse:
    def test_medication(self):
        out = _fallback_parse("继续吃美托洛尔每天 25mg")
        assert len(out) == 1
        assert out[0]["kind"] == "medication_change"

    def test_target(self):
        out = _fallback_parse("LDL 控制在 2.6 以下")
        assert len(out) == 1
        assert out[0]["kind"] == "target_override"

    def test_lifestyle(self):
        out = _fallback_parse("严格戒酒 30 天")
        assert len(out) == 1
        assert out[0]["kind"] == "lifestyle"

    def test_watch_metric(self):
        out = _fallback_parse("每天监测血压, 超 140 立刻通知")
        assert len(out) == 1
        assert out[0]["kind"] == "watch_metric"

    def test_skip_recommendation(self):
        out = _fallback_parse("不要再给我推鱼油了")
        assert len(out) == 1
        assert out[0]["kind"] == "skip_recommendation"

    def test_no_match_returns_empty(self):
        assert _fallback_parse("今天天气真好") == []


# ─────────────── parse_and_store (db) ───────────────


class TestParseAndStore:
    def test_stores_to_db(self, db, monkeypatch):
        # Force fallback path (LLM mock)
        from app.services import directive_parser
        monkeypatch.setattr(directive_parser, "_parse_with_llm", lambda text: [])

        ids = parse_and_store(db, user_id=1, text="LDL 应控制在 2.6 以下")
        assert len(ids) == 1

        row = db.query(UserDirective).filter(UserDirective.id == ids[0]).one()
        assert row.kind == "target_override"
        assert row.user_id == 1
        assert row.status == "active"

    def test_short_text_no_op(self, db):
        assert parse_and_store(db, user_id=1, text="") == []
        assert parse_and_store(db, user_id=1, text="ok") == []

    def test_with_llm_output(self, db, monkeypatch):
        from app.services import directive_parser
        monkeypatch.setattr(directive_parser, "_parse_with_llm", lambda text: [
            {
                "kind": "target_override", "instruction": "LDL < 2.6",
                "metric_key": "ldl", "target_value": "<2.6",
                "severity": "strong", "expires_days": 30,
            },
            {
                "kind": "medication_change", "instruction": "继续美托洛尔",
                "medication_name": "美托洛尔", "severity": "mandatory",
            },
        ])
        ids = parse_and_store(db, user_id=42, text="任意输入", source="external_telegram")
        assert len(ids) == 2

        rows = db.query(UserDirective).filter(UserDirective.user_id == 42).all()
        kinds = sorted(r.kind for r in rows)
        assert kinds == ["medication_change", "target_override"]

        # 查 expires_at 设了
        target = next(r for r in rows if r.kind == "target_override")
        assert target.metric_key == "ldl"
        assert target.expires_at is not None


# ─────────────── 注入 prompt ───────────────


class TestPromptInject:
    def test_no_directives_empty(self, db):
        assert get_active_directives_for_prompt(db, user_id=99) == ""

    def test_active_directives_in_prompt(self, db):
        d1 = UserDirective(user_id=99, kind="target_override",
                          instruction="LDL < 2.6", metric_key="ldl",
                          target_value="<2.6", severity="strong",
                          status="active")
        d2 = UserDirective(user_id=99, kind="lifestyle",
                          instruction="严格戒酒 30 天", severity="mandatory",
                          status="active")
        db.add_all([d1, d2])
        db.commit()

        out = get_active_directives_for_prompt(db, user_id=99)
        assert "硬性指令" in out
        assert "LDL < 2.6" in out
        assert "戒酒" in out
        # mandatory severity 显示红圈
        assert "🔴" in out

    def test_metric_filter_includes_generic(self, db):
        # ldl 专属 + 通用 lifestyle 都应返回
        db.add_all([
            UserDirective(user_id=99, kind="target_override",
                         instruction="LDL < 2.6", metric_key="ldl",
                         severity="strong", status="active"),
            UserDirective(user_id=99, kind="lifestyle",
                         instruction="戒酒", severity="strong",
                         status="active"),
            UserDirective(user_id=99, kind="target_override",
                         instruction="HbA1c < 5.5", metric_key="hba1c",
                         severity="strong", status="active"),
        ])
        db.commit()

        out = get_active_directives_for_prompt(db, user_id=99, metric_key="ldl")
        assert "LDL < 2.6" in out
        assert "戒酒" in out  # 通用 lifestyle, 没 metric_key
        assert "HbA1c" not in out  # 不同 metric

    def test_revoked_excluded(self, db):
        from datetime import timezone
        d = UserDirective(user_id=99, kind="lifestyle",
                         instruction="戒酒", severity="strong",
                         status="revoked",
                         revoked_at=datetime.now(timezone.utc))
        db.add(d)
        db.commit()
        assert get_active_directives_for_prompt(db, user_id=99) == ""

    def test_expired_excluded(self, db):
        from datetime import timezone
        d = UserDirective(user_id=99, kind="lifestyle",
                         instruction="戒酒", severity="strong",
                         status="active",
                         expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        db.add(d)
        db.commit()
        assert get_active_directives_for_prompt(db, user_id=99) == ""
