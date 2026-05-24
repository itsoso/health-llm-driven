import json

from app.services.agent_executor import _extract_model_id_from_extra_context


def test_extract_model_id_from_mac_extra_context_accepts_registry_id():
    extra_context = json.dumps({
        "client": "mac",
        "model_id": "qwen3.6-plus",
    })

    assert _extract_model_id_from_extra_context(extra_context) == "qwen3.6-plus"


def test_extract_model_id_from_extra_context_rejects_invalid_values():
    assert _extract_model_id_from_extra_context('{"model_id": "../bad"}') is None
    assert _extract_model_id_from_extra_context("not json") is None
