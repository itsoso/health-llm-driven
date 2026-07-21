"""Regression guards for health-content logging at Agent execution boundaries."""

from __future__ import annotations

import inspect

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
