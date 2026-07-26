"""Regression guards for health-content logging at Agent execution boundaries."""

from __future__ import annotations

import inspect
import logging

import pytest

from app.services.agent_executor import AgentExecutor


def test_agent_executor_does_not_log_raw_health_or_model_payloads():
    source = inspect.getsource(AgentExecutor)

    assert "图片识别完成: {vision_description" not in source
    assert "preview={str(response)" not in source
    assert "result={result[:200]}" not in source
    assert "content[:120]" not in source
    assert "botched[:120]" not in source
    assert "tap_result[:120]" not in source


def test_agent_executor_keeps_metadata_only_observability_markers():
    source = inspect.getsource(AgentExecutor)

    assert "图片识别完成 chars=" in source
    assert "tool_call_count=" in source
    assert "result_chars=" in source


@pytest.mark.asyncio
async def test_tool_progress_failure_log_does_not_include_exception_text(
    db,
    monkeypatch,
    caplog,
):
    executor = AgentExecutor(db)
    private_text = "private-medication-dose-50mg"

    async def fail_tool(*_args, **_kwargs):
        raise RuntimeError(private_text)

    monkeypatch.setattr(executor, "_execute_tool", fail_tool)

    with caplog.at_level(logging.WARNING):
        events = [
            event
            async for event in executor._run_tool_with_progress(
                "health_record",
                {"record_type": "medication"},
                None,
                "记录用药",
            )
        ]

    assert events[-1][0] == "result"
    assert private_text not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_telegram_write_failure_hides_exception_text(
    db,
    monkeypatch,
    caplog,
):
    from app.services import telegram_inbound
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    private_text = "private-diet-and-medication-payload"

    monkeypatch.setattr(
        "app.api.wechat.create_access_token",
        lambda _user_id: "test-token",
    )

    async def fail_runtime(_self, **_kwargs):
        raise RuntimeError(private_text)

    monkeypatch.setattr(CloudAgentRuntimeFacade, "execute_tool", fail_runtime)

    with caplog.at_level(logging.WARNING):
        result = await telegram_inbound.execute_health_record(
            db,
            1,
            {"record_type": "diet", "data": {"food_items": "private"}},
            source_text="记录这餐",
            client_turn_id="telegram-test-turn",
        )

    assert private_text not in result
    assert private_text not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_directive_parser_failure_hides_provider_exception_text(
    monkeypatch,
    caplog,
):
    from app.services import directive_parser

    private_text = "private-medication-directive"

    class FailingProvider:
        async def chat(self, **_kwargs):
            raise RuntimeError(private_text)

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_extraction",
        lambda _model_id: FailingProvider(),
    )

    with caplog.at_level(logging.WARNING):
        result = await directive_parser._parse_with_llm_async("继续服药")

    assert result == []
    assert private_text not in caplog.text
    assert "RuntimeError" in caplog.text


def test_directive_write_failure_hides_database_exception_text(
    db,
    monkeypatch,
    caplog,
):
    from app.services import directive_parser

    private_text = "private-medication-database-payload"

    def fail_flush():
        raise RuntimeError(private_text)

    monkeypatch.setattr(db, "flush", fail_flush)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match=private_text):
            directive_parser._store_parsed_directives(
                db,
                1,
                "继续服药",
                [{
                    "kind": "medication_change",
                    "instruction": "继续服药",
                    "severity": "strong",
                }],
                source="user_self",
                source_message_id="privacy-test",
            )

    assert private_text not in caplog.text
    assert "RuntimeError" in caplog.text
