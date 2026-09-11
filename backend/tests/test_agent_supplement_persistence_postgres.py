"""Synthetic supplement input reaches real authenticated PostgreSQL writes.

Only model output is scripted; intent policy, tool dispatch, API authorization,
supplement creation/tap, receipt verification, and readback stay real.
"""

import json
from urllib.parse import urlsplit

import pytest

from app.models.daily_health import DietRecord
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.services.agent_executor import AgentExecutor, _write_receipt_from_tool_result

pytestmark = pytest.mark.usefixtures("consenting_agent_user")
NAME = "营养素乙"


@pytest.fixture
def supplement_transport(db, client, auth_user_and_headers, monkeypatch):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires TEST_DATABASE_URL PostgreSQL")
    owner, headers = auth_user_and_headers
    executor = AgentExecutor(db)
    requests = []

    def request(method, url, request_headers, data=None):
        path = urlsplit(url).path
        assert request_headers["Authorization"] == headers["Authorization"]
        assert path in {"/api/v1/supplements/me/definitions",
                        "/api/v1/supplements/definitions", "/api/v1/nfc/tap",
                        "/api/v1/diet/records"}
        requests.append((method, path))
        response = client.request(method, path, headers=request_headers, json=data)
        assert response.status_code == 200, response.status_code
        return response

    async def get_json(url, request_headers):
        return request("GET", url, request_headers).json(), None

    async def post_json(url, request_headers, data):
        return request("POST", url, request_headers, data).json(), None

    async def post(url, request_headers, data):
        return request("POST", url, request_headers, data).text

    monkeypatch.setattr(executor, "_api_get_json", get_json)
    monkeypatch.setattr(executor, "_api_post_json", post_json)
    monkeypatch.setattr(executor, "_api_post", post)
    return executor, owner, headers, requests


async def test_explicit_supplement_stream_writes_owned_log_with_verified_receipt(
    db, client, supplement_transport, monkeypatch,
):
    executor, owner, headers, requests = supplement_transport
    other = User(username="supplement-other", name="合成他人账号", hashed_password="synthetic")
    db.add(other)
    db.flush()
    db.add(SupplementDefinition(user_id=other.id, name=NAME, dosage="9粒", is_active=True))
    db.commit()
    args = {"record_type": "supplement", "data": {"supplement_name": NAME, "dosage": "2粒"}}
    call = {"id": "synthetic-supplement-call", "type": "function", "function": {
        "name": "health_record", "arguments": json.dumps(args, ensure_ascii=False),
    }}
    rounds = 0

    async def model_response(messages, tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return {"content": "", "tool_calls": [call], "finish_reason": "tool_calls"}
        return {"content": "补剂记录已处理。", "tool_calls": [], "finish_reason": "stop"}

    async def model_stream(messages, tools):
        response = await model_response(messages, tools)
        if response["tool_calls"]:
            yield {"type": "tool_calls", "tool_calls": response["tool_calls"]}
        else:
            yield {"type": "content", "text": response["content"]}
        yield {"type": "finish", "finish_reason": response["finish_reason"]}

    monkeypatch.setattr(executor, "_call_llm", model_response)
    monkeypatch.setattr(executor, "_call_llm_stream", model_stream)
    token = headers["Authorization"].removeprefix("Bearer ")
    message = f"记录补剂：{NAME}两粒"
    events = [event async for event in executor.run_stream(
        user_id=owner.id, message=message, user_auth_token=token,
        client_turn_id="turn-90-1789100000000",
    )]
    done = next(event["data"] for event in events if event.get("event") == "done")
    assert done["turn_outcome"]["category"] == "success"
    assert len(done["write_receipts"]) == 1
    receipt = done["write_receipts"][0]
    assert receipt["verified"] is True
    definition = db.query(SupplementDefinition).filter_by(user_id=owner.id).one()
    record = db.query(SupplementRecord).filter_by(user_id=owner.id).one()
    assert definition.name == NAME and definition.dosage == "2粒"
    assert record.supplement_id == definition.id and record.taken is True
    assert str(record.id) == str(receipt["resource_id"])
    assert db.query(DietRecord).count() == 0
    assert db.query(SupplementRecord).filter_by(user_id=other.id).count() == 0
    assert requests == [("GET", "/api/v1/supplements/me/definitions"),
                        ("POST", "/api/v1/supplements/definitions"), ("POST", "/api/v1/nfc/tap")]
    readback = client.get("/api/v1/supplements/me/records", headers=headers)
    assert readback.status_code == 200
    assert [(row["id"], row["user_id"]) for row in readback.json()] == [(record.id, owner.id)]

    # A persisted turn replay must not re-create or re-tap the supplement.
    request_count = len(requests)
    replay = [event async for event in executor.run_stream(
        user_id=owner.id, message=message, user_auth_token=token,
        client_turn_id="turn-90-1789100000000",
    )]
    assert any(event.get("event") == "done" for event in replay)
    assert len(requests) == request_count
    assert db.query(SupplementRecord).filter_by(user_id=owner.id).count() == 1


@pytest.mark.parametrize("message,args", [
    (f"记录补剂：{NAME}一粒两粒", {"record_type": "supplement",
                                "data": {"supplement_name": NAME, "dosage": "1粒"}}),
    (f"记录补剂：{NAME}两粒", {"record_type": "diet",
                             "data": {"food_items": NAME + "两粒", "meal_type": "snack", "calories": 1}}),
])
async def test_ambiguous_or_wrong_domain_tool_proposal_has_zero_health_writes(
    db, supplement_transport, message, args,
):
    executor, owner, headers, requests = supplement_transport
    executor._current_user_id = owner.id
    executor._current_turn_user_message = message
    # Enter the real tool gateway with an adverse model proposal, without
    # replacing its intent frame, authorization policy or API transport.
    result = await executor._execute_tool(
        "health_record", args, headers["Authorization"].removeprefix("Bearer "),
    )
    assert _write_receipt_from_tool_result("health_record", args, result) is None
    assert requests == []
    assert db.query(SupplementDefinition).filter_by(user_id=owner.id).count() == 0
    assert db.query(SupplementRecord).count() == 0
    assert db.query(DietRecord).count() == 0
