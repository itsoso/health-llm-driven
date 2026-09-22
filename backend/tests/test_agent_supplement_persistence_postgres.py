"""Synthetic supplement input reaches real authenticated PostgreSQL writes.

Only model output is scripted; intent policy, tool dispatch, API authorization,
supplement creation/tap, receipt verification, and readback stay real.
"""

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from sqlalchemy.orm import sessionmaker

from app.api import nfc
from app.api.supplements import record_supplement_intake_batch
from app.models.daily_health import DietRecord
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.schemas.supplement import SupplementIntakeBatchCreate
from app.services.agent_executor import (
    AgentExecutor,
    _build_deterministic_supplement_record_tool_calls,
    _write_receipt_from_tool_result,
)

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
                        "/api/v1/supplements/records/intake-batch",
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


async def test_explicit_supplement_batch_is_one_atomic_postgres_write(
    db, supplement_transport,
):
    executor, owner, headers, requests = supplement_transport
    message = "打卡补剂：2粒Mitoq 1粒叶酸 十二粒NAC"
    executor._current_user_id = owner.id
    executor._current_turn_user_message = message
    args = {
        "record_type": "supplement",
        "data": {"items": [
            {"supplement_name": "Mitoq", "dosage": "2粒"},
            {"supplement_name": "叶酸", "dosage": "1粒"},
            {"supplement_name": "NAC", "dosage": "12粒"},
        ]},
    }

    result = await executor._execute_tool(
        "health_record",
        args,
        headers["Authorization"].removeprefix("Bearer "),
    )
    payload = json.loads(result)

    assert payload["status"] == "recorded"
    assert [(item["supplement_name"], item["dosage"]) for item in payload["items"]] == [
        ("Mitoq", "2粒"),
        ("叶酸", "1粒"),
        ("NAC", "12粒"),
    ]
    assert requests == [("POST", "/api/v1/supplements/records/intake-batch")]
    definitions = db.query(SupplementDefinition).filter_by(user_id=owner.id).order_by(
        SupplementDefinition.id
    ).all()
    records = db.query(SupplementRecord).filter_by(user_id=owner.id).order_by(
        SupplementRecord.id
    ).all()
    assert [definition.name for definition in definitions] == ["Mitoq", "叶酸", "NAC"]
    assert [record.actual_dosage for record in records] == ["2粒", "1粒", "12粒"]
    assert payload["record_ids"] == [record.id for record in records]


async def test_missing_units_then_complete_resend_writes_exact_batch(
    db, client, supplement_transport, monkeypatch,
):
    executor, owner, headers, requests = supplement_transport
    model_calls = []

    async def model_stream(messages, tools):
        model_calls.append(True)
        yield {"type": "content", "text": "请查看执行结果。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def model_response(messages, tools):
        model_calls.append(True)
        return {"content": "请查看执行结果。", "tool_calls": [], "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", model_stream)
    monkeypatch.setattr(executor, "_call_llm", model_response)
    token = headers["Authorization"].removeprefix("Bearer ")
    first = [event async for event in executor.run_stream(
        user_id=owner.id, message="记录补剂：1 复合VB 1 Mitoq",
        user_auth_token=token, client_turn_id="supplement-unit-question",
    )]
    first_done = next(event["data"] for event in first if event.get("event") == "done")
    assert first_done["turn_outcome"]["status"] == "waiting_for_user"
    assert requests == [] and model_calls == []
    assert db.query(SupplementRecord).filter_by(user_id=owner.id).count() == 0
    conversation_id = first_done["conversation_id"]
    message = "记录补剂：1片复合VB 1粒Mitoq"
    second = [event async for event in executor.run_stream(
        user_id=owner.id, message=message, conversation_id=conversation_id,
        user_auth_token=token, client_turn_id="supplement-unit-complete",
    )]
    done = next(event["data"] for event in second if event.get("event") == "done")
    assert done["turn_outcome"]["category"] == "success"
    assert len(done["write_receipts"]) == 1 and done["write_receipts"][0]["verified"]
    assert requests == [("POST", "/api/v1/supplements/records/intake-batch")]
    rows = client.get("/api/v1/supplements/me/records", headers=headers).json()
    definitions = {row.id: row.name for row in db.query(SupplementDefinition).filter_by(user_id=owner.id)}
    assert {(definitions[row["supplement_id"]], row["actual_dosage"]) for row in rows} == {
        ("复合VB", "1片"), ("Mitoq", "1粒"),
    }
    replay = [event async for event in executor.run_stream(
        user_id=owner.id, message=message, conversation_id=conversation_id,
        user_auth_token=token, client_turn_id="supplement-unit-complete",
    )]
    assert any(event.get("event") == "done" for event in replay)
    assert len(requests) == 1
    assert db.query(SupplementRecord).filter_by(user_id=owner.id).count() == 2


@pytest.mark.parametrize(
    ("message", "contextual_names"),
    (
        ("记录下来，吃了一粒甘氨酸镁和一粒褪黑素。", ()),
        ("全部已服用", ("鱼油", "NAC")),
    ),
)
async def test_legacy_multi_supplement_flows_keep_real_postgres_writes(
    db,
    supplement_transport,
    message,
    contextual_names,
):
    executor, owner, headers, requests = supplement_transport
    executor._current_user_id = owner.id
    executor._current_turn_user_message = message
    executor._turn_contextual_supplement_names = contextual_names
    nfc._last_tap.clear()
    calls = _build_deterministic_supplement_record_tool_calls(
        message,
        contextual_supplement_names=contextual_names,
        write_receipts=[],
    )

    assert len(calls) == 2
    for call in calls:
        args = json.loads(call["function"]["arguments"])
        result = await executor._execute_tool(
            "health_record",
            args,
            headers["Authorization"].removeprefix("Bearer "),
        )
        assert _write_receipt_from_tool_result("health_record", args, result)

    assert db.query(SupplementDefinition).filter_by(user_id=owner.id).count() == 2
    assert db.query(SupplementRecord).filter_by(user_id=owner.id).count() == 2
    assert sum(path.endswith("/tap") for _method, path in requests) == 2


def test_concurrent_same_user_batch_retries_share_postgres_rows(
    db,
    auth_user_and_headers,
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires TEST_DATABASE_URL PostgreSQL")
    owner, _headers = auth_user_and_headers
    owner_id = owner.id
    db.commit()
    sessions = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    barrier = Barrier(2)
    batch = SupplementIntakeBatchCreate(
        record_date="2026-09-21",
        items=[
            {"supplement_name": "Mitoq", "dosage": "2粒"},
            {"supplement_name": "叶酸", "dosage": "1粒"},
            {"supplement_name": "NAC", "dosage": "1粒"},
        ],
    )

    def write_batch():
        worker_db = sessions()
        try:
            barrier.wait(timeout=5)
            result = record_supplement_intake_batch(
                batch,
                current_user=SimpleNamespace(id=owner_id),
                db=worker_db,
            )
            return result["record_ids"]
        finally:
            worker_db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        record_ids = list(pool.map(lambda _index: write_batch(), range(2)))

    db.expire_all()
    assert record_ids[0] == record_ids[1]
    assert db.query(SupplementDefinition).filter_by(user_id=owner_id).count() == 3
    assert db.query(SupplementRecord).filter_by(user_id=owner_id).count() == 3


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
