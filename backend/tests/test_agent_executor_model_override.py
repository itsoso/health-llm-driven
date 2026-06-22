import json

from app.services.agent_executor import (
    _extract_desktop_response_instruction,
    _extract_model_id_from_extra_context,
)


def test_extract_model_id_from_mac_extra_context_accepts_registry_id():
    extra_context = json.dumps({
        "client": "mac",
        "model_id": "qwen3.6-plus",
    })

    assert _extract_model_id_from_extra_context(extra_context) == "qwen3.6-plus"


def test_extract_model_id_from_mac_extra_context_maps_provider_model_alias():
    extra_context = json.dumps({
        "client": "mac",
        "model_id": "commercial/Claude-Opus-4.7",
    })

    assert _extract_model_id_from_extra_context(extra_context) == "claude-opus-4.7"


def test_extract_model_id_from_extra_context_rejects_invalid_values():
    assert _extract_model_id_from_extra_context('{"model_id": "../bad"}') is None
    assert _extract_model_id_from_extra_context("not json") is None


def test_extract_desktop_response_instruction_from_extra_context():
    extra_context = json.dumps({
        "client": "mac",
        "desktop_markdown_response_instruction": "请用 Markdown 分段，不要输出密集长段落。",
    })

    assert _extract_desktop_response_instruction(extra_context) == "请用 Markdown 分段，不要输出密集长段落。"


def test_extract_desktop_response_instruction_requires_mac_client():
    extra_context = json.dumps({
        "client": "mobile",
        "desktop_markdown_response_instruction": "不要输出 markdown",
    })

    assert _extract_desktop_response_instruction(extra_context) is None
