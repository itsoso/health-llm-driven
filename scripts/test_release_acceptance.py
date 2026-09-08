"""Offline synthetic protocol and order acceptance regressions (no credentials)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("release_acceptance.py")


def load_helper():
    assert SCRIPT.exists(), "Reusable offline release acceptance helper must exist"
    spec = importlib.util.spec_from_file_location("release_acceptance", SCRIPT)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def event(name, data):
    return ("data: " + json.dumps({"event": name, "data": data}, ensure_ascii=False) + "\n\n").encode()


def draft():
    return {
        "type": "diet_draft",
        "data": {"food_items": [{"name": "synthetic meal", "quantity": "1", "portion_basis": "order_quantity"}]},
        "actions": [{"action": "diet_record.create", "requires_manual_confirm": True}],
    }


def receipt(**overrides):
    return {"operation_id": "synthetic:1", "status": "verified", "resource_type": "diet_record",
            "resource_id": "1", "verified": True, "completed_at": "2026-09-08T00:00:00Z", **overrides}


def test_fragmented_utf8_envelope_and_confirmation_path():
    helper = load_helper()
    wire = event("token", {"content": "合成内容"}) + event("card", {"descriptor": draft()}) + event("done", {})
    result = helper.analyze_order_stream(wire[i:i + 1] for i in range(len(wire)))
    assert result == {"status": "pending_confirmation", "event_count": 3,
                      "write_verified": False, "requires_confirmation": True, "requires_readback": False}


@pytest.mark.parametrize("wrapper", [lambda d: d, lambda d: {"descriptor": d}, lambda d: {"card": d}])
def test_supported_card_wrappers(wrapper):
    helper = load_helper()
    assert helper.analyze_order_stream([event("proposed_card", wrapper(draft())), event("done", {})])["status"] == "pending_confirmation"


def test_done_cards_and_crlf_comments_flat_status_and_sentinel():
    helper = load_helper()
    wire = b': keepalive\r\n\r\ndata: {"type":"status","stage":"accepted"}\r\n\r\n'
    wire += event("done", {"cards": [draft()]}).replace(b"\n", b"\r\n") + b"data: [DONE]\r\n\r\n"
    assert helper.analyze_order_stream([wire])["status"] == "pending_confirmation"


@pytest.mark.parametrize("encoded", [False, True])
def test_actual_contextual_card_uses_food_label_and_nested_recognition(encoded):
    helper = load_helper()
    card = draft()
    recognition = {"foods": card["data"]["food_items"]}
    card["data"]["food_items"] = "synthetic meal 1"
    card["data"]["ai_raw_result"] = json.dumps(recognition) if encoded else recognition
    assert helper.analyze_order_stream([event("done", {"cards": [card]})])["status"] == "pending_confirmation"


@pytest.mark.parametrize("data", [
    {"completion_status": "interrupted"},
    {"turn_outcome": {"status": "blocked"}},
    {"turn_outcome": {"status": "refused"}},
    {"turn_outcome": {"status": "reconciliation_required"}},
    {"turn_outcome": {"status": "unknown_future_status"}},
])
def test_non_success_terminal_cannot_be_hidden_by_prior_confirmation(data):
    helper = load_helper()
    with pytest.raises(helper.AcceptanceError, match="stream_error"):
        helper.analyze_order_stream([event("card", draft()), event("done", data)])


def test_verified_receipt_is_not_independent_database_readback():
    helper = load_helper()
    result = helper.analyze_order_stream([event("done", {"write_receipts": [receipt()]})])
    assert result["status"] == "recorded_receipt"
    assert result["requires_readback"] is True
    assert result["write_verified"] is False


@pytest.mark.parametrize("data", [
    {"content": "已记录成功"}, {"cards": [{"type": "diet_draft", "data": {"recorded": True, "record_id": 1}}]},
    {"write_receipts": [receipt(verified=False)]}, {"write_receipts": [receipt(status="dismissed")]},
    {"write_receipts": [receipt(action="delete")]}, {"write_receipts": [receipt(resource_type="write_intent")]},
    {"write_receipts": [receipt(resource_id=True)]},
])
def test_prose_recorded_card_or_invalid_receipt_never_proves_record(data):
    helper = load_helper()
    with pytest.raises(helper.AcceptanceError, match="order_outcome_missing"):
        helper.analyze_order_stream([event("done", data)])


@pytest.mark.parametrize("wire,code", [
    (b'data: {secret}\n\n', "invalid_json"),
    (b'data: []\n\n', "invalid_envelope"),
    (b'data: {"event":"done","data":null}\n\n', "invalid_envelope"),
    (b'data: {"event":"done","data":{},"data":{}}\n\n', "invalid_json"),
    (b'data: {"event":"done","data":{"x":NaN}}\n\n', "invalid_json"),
    (b'data: \xff\n\n', "invalid_utf8"),
    (event("error", {"message": "secret"}), "stream_error"),
    (event("done", {"error": "secret"}), "stream_error"),
    (event("done", {"turn_outcome": {"status": "failed"}}), "stream_error"),
    (event("card", draft()), "terminal_missing"),
    (b'data: {"event":"done","data":{}}', "truncated_frame"),
    (event("done", {}) + event("token", {"content": "secret"}), "event_after_terminal"),
    (b'event: done\ndata: {}\n\n', "invalid_envelope"),
])
def test_fail_closed_without_echoing_payload(wire, code):
    helper = load_helper()
    with pytest.raises(helper.AcceptanceError) as failure:
        helper.analyze_order_stream([wire])
    assert str(failure.value) == code


def test_limits_apply_to_fragmented_total_and_frame():
    helper = load_helper()
    with pytest.raises(helper.AcceptanceError, match="frame_too_large"):
        helper.analyze_order_stream([b"data: ", b"x" * 30], max_frame_bytes=20)
    with pytest.raises(helper.AcceptanceError, match="stream_too_large"):
        helper.analyze_order_stream([b":ping\n\n"] * 10, max_total_bytes=20)


def test_multiline_data_is_json_envelope_not_separate_event_field():
    helper = load_helper()
    wire = b'data: {"event":"done",\ndata: "data":' + json.dumps({"cards": [draft()]}).encode() + b'}\n\n'
    assert helper.analyze_order_stream([wire])["status"] == "pending_confirmation"


def test_cli_stdin_is_offline_and_failure_redacted():
    load_helper()
    failed = subprocess.run([sys.executable, str(SCRIPT), "analyze"], input=b'data: password-secret\n\n', capture_output=True, check=False)
    assert failed.returncode == 1
    assert b"password-secret" not in failed.stdout + failed.stderr
    assert json.loads(failed.stdout) == {"status": "failed", "error": "invalid_json"}
    passed = subprocess.run([sys.executable, str(SCRIPT), "analyze"], input=event("done", {"cards": [draft()]}), capture_output=True, check=False)
    assert passed.returncode == 0
    assert json.loads(passed.stdout)["status"] == "pending_confirmation"
    assert b"synthetic meal" not in passed.stdout
