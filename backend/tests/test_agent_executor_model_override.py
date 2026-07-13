import json

from app.services.agent_executor import (
    _extract_database_verification_instruction,
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


def test_extract_database_verification_instruction_requires_diet_query_from_db():
    extra_context = json.dumps({
        "from": "diet/post_confirm",
        "database_verification": {
            "required": True,
            "date": "2026-07-11",
            "verify_record_id": 89,
            "query_scope": "daily_diet_records",
            "totals_source": "database",
            "forbid_cached_totals": True,
            "missing_record_instruction": "如果数据库里查不到 verify_record_id 对应记录，明确提示同步失败。",
        },
    }, ensure_ascii=False)

    instruction = _extract_database_verification_instruction(extra_context)

    assert instruction is not None
    assert "health_query(dimension='diet')" in instruction
    assert "2026-07-11" in instruction
    assert "89" in instruction
    assert "不要使用入口上下文里的 totals" in instruction
    assert "同步失败" in instruction


def test_extract_database_verification_instruction_ignores_unrelated_context():
    assert _extract_database_verification_instruction("not json") is None
    assert _extract_database_verification_instruction(json.dumps({"from": "diet/today"})) is None
