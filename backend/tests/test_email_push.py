"""Email Push Service 单元测试 (不真发 SMTP)."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.notification.email_push import (
    EmailPushService, markdown_to_simple_html,
)


class TestConfigured:
    def test_empty_env_not_configured(self, monkeypatch):
        # pydantic settings 单例已实例化, 动态 patch getattr
        svc = EmailPushService()
        svc.host = ""
        svc.user = ""
        svc.password = ""
        assert svc.configured is False

    def test_all_fields_set_configured(self):
        svc = EmailPushService()
        svc.host = "smtpdm.aliyun.com"
        svc.user = "noreply@executor.life"
        svc.password = "xxx"
        assert svc.configured is True


class TestSend:
    def test_unconfigured_returns_error(self):
        svc = EmailPushService()
        svc.host = ""
        result = svc.send("a@b.test", "subj", "body")
        assert result["success"] is False
        assert "not_configured" in result["error"]

    def test_invalid_to_address(self):
        svc = EmailPushService()
        svc.host = "x"; svc.user = "u"; svc.password = "p"
        result = svc.send("not-an-email", "s", "b")
        assert result["success"] is False
        assert "invalid_to" in result["error"]

    @patch("app.services.notification.email_push.smtplib.SMTP_SSL")
    def test_ssl_send_success(self, mock_ssl):
        """SSL 端口 465: 用 SMTP_SSL, login + send_message 成功."""
        svc = EmailPushService()
        svc.host = "smtpdm.aliyun.com"; svc.port = 465; svc.use_ssl = True
        svc.user = "noreply@executor.life"
        svc.password = "secret"
        svc.from_addr = "noreply@executor.life"

        mock_smtp = MagicMock()
        mock_ssl.return_value.__enter__.return_value = mock_smtp

        result = svc.send(
            to="doc@clinic.test", subject="周度摘要",
            body_text="plain", body_html="<b>html</b>",
        )
        assert result["success"] is True
        mock_smtp.login.assert_called_once_with("noreply@executor.life", "secret")
        mock_smtp.send_message.assert_called_once()

    @patch("app.services.notification.email_push.smtplib.SMTP")
    def test_non_ssl_starttls_upgrade(self, mock_smtp_cls):
        """非 SSL 端口: 用 SMTP + STARTTLS 升级."""
        svc = EmailPushService()
        svc.host = "smtp.test"; svc.port = 25; svc.use_ssl = False
        svc.user = "u"; svc.password = "p"; svc.from_addr = "u"
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        result = svc.send("a@b.test", "s", "b")
        assert result["success"] is True
        mock_smtp.starttls.assert_called_once()

    @patch("app.services.notification.email_push.smtplib.SMTP_SSL")
    def test_auth_failure_returns_error(self, mock_ssl):
        import smtplib
        svc = EmailPushService()
        svc.host = "x"; svc.user = "u"; svc.password = "bad"
        svc.from_addr = "u"; svc.port = 465; svc.use_ssl = True
        mock_smtp = MagicMock()
        mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth fail")
        mock_ssl.return_value.__enter__.return_value = mock_smtp
        result = svc.send("a@b.test", "s", "b")
        assert result["success"] is False
        assert "auth_failed" in result["error"]

    @patch("app.services.notification.email_push.smtplib.SMTP_SSL")
    def test_generic_exception_fail_soft(self, mock_ssl):
        svc = EmailPushService()
        svc.host = "x"; svc.user = "u"; svc.password = "p"
        svc.from_addr = "u"; svc.port = 465; svc.use_ssl = True
        mock_ssl.side_effect = RuntimeError("network down")
        result = svc.send("a@b.test", "s", "b")
        assert result["success"] is False
        assert "exception" in result["error"]


class TestMarkdownToHtml:
    def test_bold_converted(self):
        assert "<strong>bold</strong>" in markdown_to_simple_html("**bold**")

    def test_italic_converted(self):
        assert "<em>it</em>" in markdown_to_simple_html("*it*")

    def test_headers_converted(self):
        html = markdown_to_simple_html("# Title\n## Sub")
        assert "<h1>Title</h1>" in html
        assert "<h2>Sub</h2>" in html

    def test_newline_to_br(self):
        assert "<br>" in markdown_to_simple_html("line1\nline2")

    def test_wrapper_style(self):
        html = markdown_to_simple_html("hello")
        assert "<!DOCTYPE html>" in html
        assert "font-family: sans-serif" in html
