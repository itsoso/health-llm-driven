"""Tests for sentry_status_snapshot — Phase 0.5."""
from __future__ import annotations

from unittest.mock import patch

from app.services.sentry_status import sentry_status_snapshot


def test_disabled_when_no_dsn():
    """未配 DSN 时, enabled=False, hint 指向 setup doc."""
    with patch("app.services.sentry_status.__name__"):
        from app import config
        with patch.object(config, "settings") as mock:
            mock.sentry_dsn = None
            mock.sentry_environment = "production"
            mock.sentry_traces_sample_rate = 0.1
            from importlib import reload
            from app.services import sentry_status
            reload(sentry_status)
            out = sentry_status.sentry_status_snapshot()

    assert out["enabled"] is False
    assert "SENTRY_DSN" in out["hint"]


def test_disabled_when_empty_string_dsn():
    """空字符串 DSN 也算未启用 (env 里 SENTRY_DSN= 空值场景)."""
    with patch("app.config.settings") as mock:
        mock.sentry_dsn = "   "
        mock.sentry_environment = "production"
        mock.sentry_traces_sample_rate = 0.1
        out = sentry_status_snapshot()

    assert out["enabled"] is False


def test_enabled_when_dsn_set():
    """配了 DSN → enabled=True, 不回传 DSN 本身."""
    with patch("app.config.settings") as mock:
        mock.sentry_dsn = "https://abc@o0.ingest.sentry.io/0"
        mock.sentry_environment = "production"
        mock.sentry_traces_sample_rate = 0.1
        out = sentry_status_snapshot()

    assert out["enabled"] is True
    assert out["environment"] == "production"
    assert out["traces_sample_rate"] == 0.1
    # 反向: DSN 不应回传给前端
    assert "abc@o0" not in str(out)
    assert "dsn" not in {k.lower() for k in out.keys()}


def test_traces_sample_rate_coerced_to_float():
    """rate 在 settings 里若是 str/Decimal, 应转 float."""
    with patch("app.config.settings") as mock:
        mock.sentry_dsn = "https://x@y.io/1"
        mock.sentry_environment = "staging"
        mock.sentry_traces_sample_rate = "0.25"
        out = sentry_status_snapshot()

    assert isinstance(out["traces_sample_rate"], float)
    assert out["traces_sample_rate"] == 0.25


def test_handles_settings_failure_gracefully():
    """settings 属性访问本身崩, 也不该让 admin 看板崩."""
    from app import config

    class _BoomSettings:
        def __getattr__(self, name):
            raise RuntimeError(f"settings.{name} broken")

    with patch.object(config, "settings", _BoomSettings()):
        out = sentry_status_snapshot()

    # 即使失败也要返回 dict, 不抛
    assert isinstance(out, dict)
    assert out["enabled"] is False
    assert out["environment"] == "unknown"


def test_environment_unset_default():
    """env 没配时, 仍能产出 unset 字面量, 不空字符串."""
    with patch("app.config.settings") as mock:
        mock.sentry_dsn = None
        mock.sentry_environment = ""
        mock.sentry_traces_sample_rate = 0.0
        out = sentry_status_snapshot()

    assert out["environment"] == "unset"
