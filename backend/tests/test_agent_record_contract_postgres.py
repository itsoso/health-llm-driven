"""Record obligations through real Pi, gateway, authenticated API and PostgreSQL.

Provider output is scripted. The production intent, tool schema, authority,
dispatch, persistence, receipt and final-message paths are not replaced.
"""

from copy import deepcopy
from datetime import date, datetime
import json
import re
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from app.models.agent_conversation import AgentMessage
from app.models.health_checkin import HealthCheckin
from app.models.user import User
from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.types import ExecutionContext
from app.services.auth import auth_service


pytestmark = pytest.mark.usefixtures("consenting_agent_user")
DAY = date(2026, 10, 31)
NOW = datetime.fromisoformat("2026-10-31T14:56:00+08:00")
ORIGINAL = "记录，我洗鼻一次，使用了一支10毫升的生理盐水"
RESEND = "今天（2026-10-31）洗鼻 1 次，使用生理盐水 10 ml"
VALUES = {"count": 1, "volume_ml": 10, "solution": "生理盐水", "record_date": DAY.isoformat()}
PATH = "/api/v1/checkin/nasal-wash"


@pytest.fixture(autouse=True)
def no_background_scheduler(monkeypatch):
    # The API lifecycle is real; unrelated recurring jobs must not outlive a test's DB.
    monkeypatch.setattr("main.start_scheduler", lambda *args, **kwargs: None)


@pytest.fixture
def record_transport(db, client, auth_user_and_headers, monkeypatch):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated TEST_DATABASE_URL PostgreSQL")
    owner, headers = auth_user_and_headers
    other = User(
        username=f"record_other_{uuid4().hex[:8]}", name="Synthetic other owner",
        email=f"record_other_{uuid4().hex[:8]}@example.invalid",
        hashed_password="synthetic", is_active=True, is_approved=True,
    )
    db.add(other)
    db.commit()
    other_headers = {"Authorization": "Bearer " + auth_service.create_access_token({"sub": str(other.id)})}
    original_now = ExecutionContext.now.__func__

    def frozen(cls, **kwargs):
        return original_now(cls, **{**kwargs, "now_utc": NOW})

    monkeypatch.setattr(ExecutionContext, "now", classmethod(frozen))
    executor = AgentExecutor(db)
    requests, model_calls, transport_errors = [], [], []

    def request(method, url, request_headers, data=None):
        path = urlsplit(url).path
        requests.append((method, path, deepcopy(data)))
        if request_headers.get("Authorization") != headers["Authorization"]:
            transport_errors.append("wrong_authentication")
        event_readback = method == "GET" and re.fullmatch(
            r"/api/v1/checkin/[1-9]\d*/nasal-wash/[0-9a-f]{64}", path,
        )
        if path not in {PATH, "/api/v1/checkin/me/history"} and not event_readback:
            transport_errors.append("unexpected_endpoint")
        assert not transport_errors
        return client.request(method, path, headers=request_headers, json=data)

    async def post(url, request_headers, data, **kwargs):
        return request("POST", url, request_headers, data).text

    async def post_json(url, request_headers, data, **kwargs):
        response = request("POST", url, request_headers, data)
        return response.json(), None if response.status_code == 200 else f"API {response.status_code}"

    async def get_json(url, request_headers, **kwargs):
        response = request("GET", url, request_headers)
        return response.json(), None if response.status_code == 200 else f"API {response.status_code}"

    monkeypatch.setattr(executor, "_api_post", post)
    monkeypatch.setattr(executor, "_api_post_json", post_json)
    monkeypatch.setattr(executor, "_api_get_json", get_json)

    def script(args=None):
        async def response(messages, tools):
            model_calls.append((messages, tools))
            if args is not None and len(model_calls) == 1:
                proposals = args if isinstance(args, list) else [args]
                return {"content": "", "tool_calls": [{
                    "id": f"record-contract-call-{index}", "type": "function",
                    "function": {"name": "health_record", "arguments": json.dumps(proposal, ensure_ascii=False)},
                } for index, proposal in enumerate(proposals)], "finish_reason": "tool_calls"}
            return {"content": "记录已完成。", "tool_calls": [], "finish_reason": "stop"}

        async def stream(messages, tools):
            result = await response(messages, tools)
            if result["tool_calls"]:
                yield {"type": "tool_calls", "tool_calls": result["tool_calls"]}
            else:
                yield {"type": "content", "text": result["content"]}
            yield {"type": "finish", "finish_reason": result["finish_reason"]}

        monkeypatch.setattr(executor, "_call_llm", response)
        monkeypatch.setattr(executor, "_call_llm_stream", stream)

    async def run(message, turn_id=None, **kwargs):
        events = [event async for event in executor.run_stream(
            owner.id, message, channel="typed",
            user_auth_token=headers["Authorization"].removeprefix("Bearer "),
            client_turn_id=turn_id or str(uuid4()),
            **kwargs,
        )]
        done = next(event["data"] for event in reversed(events) if event["event"] == "done")
        assert not transport_errors, transport_errors
        persisted = db.get(AgentMessage, done["message_id"])
        assert persisted is not None
        assert persisted.meta["completion_status"] == done["completion_status"]
        assert persisted.meta["turn_outcome"] == done["turn_outcome"]
        assert persisted.meta["write_receipts"] == done["write_receipts"]
        return done, persisted

    return SimpleNamespace(
        executor=executor, owner=owner, other=other, headers=headers, other_headers=other_headers,
        requests=requests, model_calls=model_calls, script=script, run=run,
    )


@pytest.mark.parametrize("message", [ORIGINAL, RESEND])
@pytest.mark.parametrize("provider_calls_tool", [True, False])
async def test_record_obligation_reaches_owned_postgres_and_replays_once(
    db, client, record_transport, message, provider_calls_tool,
):
    trace = record_transport
    trace.script({"record_type": "nasal_wash", "data": dict(VALUES)} if provider_calls_tool else None)
    turn_id = str(uuid4())
    done, _ = await trace.run(message, turn_id)
    assert done["perf"]["agent_kernel"] == "pi"
    assert done["completion_status"] == "complete", done["turn_outcome"]
    assert done["turn_outcome"]["status"] == "complete"
    assert done["kernel_trace"]["goal_kind"] != "chat"
    assert len(done["write_receipts"]) == 1
    receipt = done["write_receipts"][0]
    row = db.query(HealthCheckin).filter_by(user_id=trace.owner.id, checkin_date=DAY).one()
    assert receipt["verified"] is True
    assert receipt["resource_type"] == "health_checkin"
    assert str(receipt["resource_id"]) == str(row.id)
    assert row.nasal_wash_count == 1
    assert len(row.nasal_wash_times) == 1
    event = row.nasal_wash_times[0]
    assert event["event_id"] and event["time"]
    assert {key: event[key] for key in ("count", "volume_ml", "solution")} == {
        "count": 1, "volume_ml": 10, "solution": "生理盐水",
    }
    assert db.query(HealthCheckin).filter_by(user_id=trace.other.id).count() == 0
    response = client.get(
        "/api/v1/checkin/me/history", headers=trace.headers,
        params={"start_date": DAY.isoformat(), "end_date": DAY.isoformat()},
    )
    assert response.status_code == 200
    assert [(item["id"], item["user_id"], item["nasal_wash_times"]) for item in response.json()] == [
        (row.id, trace.owner.id, row.nasal_wash_times),
    ]
    other_readback = client.get(
        "/api/v1/checkin/me/history", headers=trace.other_headers,
        params={"start_date": DAY.isoformat(), "end_date": DAY.isoformat()},
    )
    assert other_readback.status_code == 200 and other_readback.json() == []
    request_count = len(trace.requests)
    replay, _ = await trace.run(message, turn_id)
    assert replay["write_receipts"] == done["write_receipts"]
    assert len(trace.requests) == request_count
    db.refresh(row)
    assert row.nasal_wash_count == 1 and len(row.nasal_wash_times) == 1


async def test_unknown_record_obligation_cannot_be_completed_by_prose(db, record_transport):
    trace = record_transport
    trace.script()
    done, persisted = await trace.run("记录，我进行了光照训练一次")
    assert done["completion_status"] != "complete"
    assert done["turn_outcome"]["status"] != "complete"
    assert done["write_receipts"] == [] and trace.requests == []
    assert db.query(HealthCheckin).count() == 0
    assert "记录已完成" not in persisted.content
    assert "重发" not in persisted.content and "再发一次" not in persisted.content


@pytest.mark.parametrize("message", [
    "记录，我洗鼻一次，另外喝水300ml",
    "记录我喝水300ml，再记录光照适应一次",
])
async def test_compound_record_obligation_not_completed_by_one_water_receipt(
    db, record_transport, message,
):
    trace = record_transport
    trace.script({"record_type": "water", "data": {"amount": 300}})
    done, persisted = await trace.run(message)
    # The executor may safely save the supported clause or reject the whole
    # request, but neither path may discard its other explicit obligation.
    assert done["completion_status"] != "complete"
    assert done["turn_outcome"]["status"] != "complete"
    assert "记录已完成" not in persisted.content
    assert db.query(HealthCheckin).count() == 0


async def test_supported_compound_water_records_complete_with_persisted_values(db, record_transport):
    from app.models.daily_health import WaterIntake
    trace = record_transport
    trace.script([{"record_type": "water", "data": {"amount": amount}} for amount in (300, 500)])
    message = "记录喝水300ml，记录喝水500ml。"
    turn_id = str(uuid4())
    done, _ = await trace.run(message, turn_id)
    assert done["perf"]["agent_kernel"] == "pi"
    assert done["completion_status"] == "complete"
    assert done["turn_outcome"]["status"] == "complete"
    rows = db.query(WaterIntake).filter_by(user_id=trace.owner.id, record_date=DAY).all()
    assert sorted(row.amount_ml for row in rows) == [300, 500]
    assert db.query(WaterIntake).filter_by(user_id=trace.other.id).count() == 0
    assert len(done["write_receipts"]) == 2
    assert all(receipt["record_obligation_proofs"] for receipt in done["write_receipts"])
    replay, _ = await trace.run(message, turn_id)
    assert replay["completion_status"] == "complete"
    assert db.query(WaterIntake).filter_by(user_id=trace.owner.id).count() == 2


async def test_partial_compound_record_overrides_model_success_in_final_and_tokens(db, record_transport):
    from app.models.daily_health import WaterIntake
    trace = record_transport
    trace.script({"record_type": "water", "data": {"amount": 300}})
    events = [event async for event in trace.executor.run_stream(
        trace.owner.id, "记录喝水300ml，记录喝水500ml。", channel="typed",
        user_auth_token=trace.headers["Authorization"].removeprefix("Bearer "),
        client_turn_id=str(uuid4()),
    )]
    done = next(event["data"] for event in reversed(events) if event["event"] == "done")
    persisted = db.get(AgentMessage, done["message_id"])
    tokens = "".join(event["data"].get("content", "") for event in events if event.get("event") == "token")
    assert done["completion_status"] != "complete"
    assert done["turn_outcome"]["status"] != "complete"
    assert persisted.meta["completion_status"] == done["completion_status"]
    assert "记录已完成" not in tokens and "记录已完成" not in persisted.content
    assert "1" in persisted.content and "2" in persisted.content
    assert "重发" not in persisted.content and "再发一次" not in persisted.content
    assert [row.amount_ml for row in db.query(WaterIntake).filter_by(user_id=trace.owner.id)] == [300]


@pytest.mark.parametrize("attack", ["count", "volume", "owner", "extra", "date"])
async def test_model_arguments_cannot_expand_record_authority(db, record_transport, attack):
    trace = record_transport
    args = {"record_type": "nasal_wash", "data": dict(VALUES)}
    if attack == "count":
        args["data"]["count"] = 20
    elif attack == "volume":
        args["data"]["volume_ml"] = 1000
    elif attack == "owner":
        args["data"]["user_id"] = trace.other.id
    elif attack == "extra":
        args["data"]["sneeze_count"] = 99
        args["data"]["confirmed"] = True
    else:
        args["data"]["record_date"] = "2026-10-30"
    trace.script(args)
    done, _ = await trace.run(ORIGINAL)
    rows = db.query(HealthCheckin).all()
    # Rejection or a server-authorized replacement is safe; model-authored facts are not.
    assert len(rows) <= 1
    if rows:
        row = rows[0]
        assert row.user_id == trace.owner.id and row.checkin_date == DAY
        assert row.nasal_wash_count == 1 and len(row.nasal_wash_times) == 1
        assert row.sneeze_count in (None, 0)
        assert row.nasal_wash_times[0]["volume_ml"] == 10
        assert row.nasal_wash_times[0]["solution"] == "生理盐水"
    if done["completion_status"] == "complete":
        assert rows and done["write_receipts"]


def test_authenticated_record_api_event_identity_is_idempotent_and_owner_scoped(
    db, client, record_transport,
):
    trace = record_transport
    data = {**VALUES, "event_id": "synthetic-nasal-event-1"}
    denied = client.post(PATH, json=data)
    assert denied.status_code in {401, 403}
    first = client.post(PATH, headers=trace.headers, json=data)
    assert first.status_code == 200, first.text
    replay = client.post(PATH, headers=trace.headers, json=data)
    assert replay.status_code == 200 and replay.json()["nasal_wash_count"] == 1
    assert replay.json()["nasal_wash_times"] == first.json()["nasal_wash_times"]
    conflict = client.post(PATH, headers=trace.headers, json={**data, "volume_ml": 30})
    assert conflict.status_code == 409
    second = client.post(PATH, headers=trace.headers, json={**data, "event_id": "synthetic-nasal-event-2"})
    assert second.status_code == 200 and second.json()["nasal_wash_count"] == 2
    assert len(second.json()["nasal_wash_times"]) == 2
    # Event identifiers belong to an owner, not to a global mutable namespace.
    other = client.post(PATH, headers=trace.other_headers, json=data)
    assert other.status_code == 200 and other.json()["user_id"] == trace.other.id
    assert other.json()["nasal_wash_count"] == 1
    assert db.query(HealthCheckin).filter_by(user_id=trace.owner.id).one().nasal_wash_count == 2


@pytest.mark.parametrize("extra", [{"user_id": 999}, {"sneeze_count": 99}, {"confirmed": True}])
def test_record_api_rejects_uncontracted_fields(db, client, record_transport, extra):
    response = client.post(
        PATH, headers=record_transport.headers,
        json={**VALUES, "event_id": "synthetic-invalid-event", **extra},
    )
    assert response.status_code == 422
    assert db.query(HealthCheckin).count() == 0


@pytest.mark.parametrize("corruption", ["transport_failure", "count", "owner", "date", "boolean_count", "event_type"])
async def test_committed_write_without_matching_readback_requires_reconciliation_and_never_replays(
    db, record_transport, monkeypatch, corruption,
):
    trace = record_transport
    trace.script({"record_type": "nasal_wash", "data": dict(VALUES)})
    original_read = trace.executor._api_get_json
    observations = []

    async def damaged_readback(url, headers, **kwargs):
        # The real authenticated endpoint still executes; only its transport evidence is damaged.
        actual, error = await original_read(url, headers, **kwargs)
        assert error is None
        observations.append(deepcopy(actual))
        if corruption == "transport_failure":
            return None, "synthetic_readback_transport_failure"
        damaged = deepcopy(actual)
        if corruption == "count":
            damaged["event"]["count"] = 2
        elif corruption == "boolean_count":
            damaged["event"]["count"] = True
        elif corruption == "owner":
            damaged["user_id"] = trace.other.id
        elif corruption == "event_type":
            damaged["event"]["type"] = "soak"
        else:
            damaged["checkin_date"] = "2026-10-30"
        return damaged, None

    monkeypatch.setattr(trace.executor, "_api_get_json", damaged_readback)
    turn_id = str(uuid4())
    done, persisted = await trace.run(ORIGINAL, turn_id)
    assert observations, "The negative result must follow a successful real write and readback attempt"
    assert done["perf"]["agent_kernel"] == "pi"
    assert done["completion_status"] == "error"
    assert done["turn_outcome"]["status"] == "reconciliation_required"
    assert done["write_receipts"] == []
    assert "记录已完成" not in persisted.content
    row = db.query(HealthCheckin).filter_by(user_id=trace.owner.id, checkin_date=DAY).one()
    assert row.nasal_wash_count == 1 and len(row.nasal_wash_times) == 1
    assert row.nasal_wash_times[0]["count"] == 1
    assert db.query(HealthCheckin).filter_by(user_id=trace.other.id).count() == 0
    post_count = sum(method == "POST" for method, _, _ in trace.requests)
    assert post_count == 1

    replay, _ = await trace.run(ORIGINAL, turn_id)
    assert replay["completion_status"] == "error"
    assert replay["turn_outcome"]["status"] == "reconciliation_required"
    assert replay["write_receipts"] == []
    assert sum(method == "POST" for method, _, _ in trace.requests) == post_count
    db.refresh(row)
    assert row.nasal_wash_count == 1 and len(row.nasal_wash_times) == 1


@pytest.mark.parametrize("identity_shape", ["string_id", "record_id_only", "zero_id"])
async def test_committed_write_with_malformed_post_identity_requires_reconciliation(
    db, record_transport, monkeypatch, identity_shape,
):
    trace = record_transport
    trace.script({"record_type": "nasal_wash", "data": dict(VALUES)})
    original_post = trace.executor._api_post

    async def damaged_post(url, headers, data, **kwargs):
        payload = json.loads(await original_post(url, headers, data, **kwargs))
        assert type(payload.get("id")) is int
        if identity_shape == "string_id":
            payload["id"] = str(payload["id"])
        elif identity_shape == "record_id_only":
            payload["record_id"] = payload.pop("id")
        else:
            payload["id"] = 0
        return json.dumps(payload)

    monkeypatch.setattr(trace.executor, "_api_post", damaged_post)
    turn_id = str(uuid4())
    done, _ = await trace.run(ORIGINAL, turn_id)
    assert done["turn_outcome"]["status"] == "reconciliation_required"
    assert done["write_receipts"] == []
    row = db.query(HealthCheckin).filter_by(user_id=trace.owner.id, checkin_date=DAY).one()
    assert row.nasal_wash_count == 1 and len(row.nasal_wash_times) == 1
    assert sum(method == "POST" for method, _, _ in trace.requests) == 1
    replay, _ = await trace.run(ORIGINAL, turn_id)
    assert replay["turn_outcome"]["status"] == "reconciliation_required"
    assert replay["write_receipts"] == []
    assert sum(method == "POST" for method, _, _ in trace.requests) == 1
    db.refresh(row)
    assert row.nasal_wash_count == 1 and len(row.nasal_wash_times) == 1


@pytest.mark.parametrize("proof", [None, {"record_type": "rhinitis", "payload_sha256": "synthetic"}])
def test_same_day_rhinitis_receipt_cannot_satisfy_nasal_wash_goal(proof):
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.postconditions import verify_goal_postconditions
    from app.services.agent_kernel.types import AgentEnvelope

    context = ExecutionContext.now(user_id=1, channel="typed", now_utc=NOW)
    envelope = AgentEnvelope(user_id=1, channel="typed", text=ORIGINAL)
    goal = compile_goal_spec(
        envelope=envelope, context=context, intent=build_intent_frame(envelope, context),
        actionable_references=(),
    )
    assert goal.target_record_type == "nasal_wash" and goal.requires_verification
    receipt = {
        "verified": True, "resource_type": "health_checkin", "resource_id": "7",
        "record_type": "rhinitis", "checkin_date": DAY.isoformat(),
    }
    if proof is not None:
        receipt["record_capability_proof"] = proof
    result = verify_goal_postconditions(goal, write_receipts=[receipt], verification_result=None)
    assert result.satisfied is False and result.verified_resource_ids == ()


async def test_unknown_record_obligation_cannot_be_completed_by_panel(db, record_transport, monkeypatch):
    trace = record_transport
    trace.script()
    panel_calls = []

    class ScriptedPanelProvider:
        async def chat(self, **kwargs):
            panel_calls.append(kwargs)
            return {"content": "记录已完成。", "finish_reason": "stop"}

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id", lambda *_: ScriptedPanelProvider(),
    )
    done, persisted = await trace.run(
        # A pure record request deliberately bypasses the panel in production.
        # The explicit analysis request selects its real lead/synthesis route.
        "记录，我进行了光照训练一次，并综合分析", extra_context='{"multi_model":true}',
    )
    entered_panel = trace.executor._multi_model_turn is True
    no_api_requests = not trace.requests
    assert entered_panel
    assert done["completion_status"] == "error"
    assert done["turn_outcome"]["status"] != "complete"
    assert done["write_receipts"] == []
    assert no_api_requests
    assert db.query(HealthCheckin).count() == 0
    assert "记录已完成" not in persisted.content
    assert "重发" not in persisted.content and "再发一次" not in persisted.content


async def test_live_provider_record_contract(db, record_transport):
    import os
    if os.getenv('REVA_RECORD_LIVE') != '1':
        pytest.skip('opt-in synthetic live-provider acceptance')
    trace = record_transport
    done, persisted = await trace.run('记录，我洗鼻一次，使用了一支10毫升的生理盐水')
    status = done['completion_status']
    assert status == 'complete'
    assert done['perf']['agent_kernel'] == 'pi'
    assert done['llm_rounds'] > 0
    assert len(done['write_receipts']) == 1
    row = db.query(HealthCheckin).filter_by(user_id=trace.owner.id, checkin_date=DAY).one()
    assert row.nasal_wash_count == 1
    assert row.nasal_wash_times[0]['volume_ml'] == 10
    assert persisted.meta['turn_outcome']['status'] == 'complete'
