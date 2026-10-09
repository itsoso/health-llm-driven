"""Exercise actual subprocess lifecycle without providers or health data."""

import asyncio
import sys

import pytest

from app.services.pi_kernel import PiKernelSession, PiKernelError


@pytest.fixture(autouse=True)
def _isolate_twin_cache(isolated_agent_protocol_transport):
    """Subprocess transport tests must not probe the developer's Redis."""


@pytest.mark.asyncio
async def test_bridge_runs_real_child_and_correlates_response(tmp_path):
    child = tmp_path / "child.py"
    child.write_text(
        "import json,sys\n"
        "start=json.loads(input())\n"
        "assert start['type']=='start'\n"
        "print(json.dumps({'type':'model_request','id':'m1','messages':start['messages'],'tools':[]}),flush=True)\n"
        "reply=json.loads(input())\n"
        "assert reply['id']=='m1'\n"
        "print(json.dumps({'type':'done','messages':[], 'content':reply['content'],'finish_reason':'stop','turns':1}),flush=True)\n"
    )
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[{"role": "user", "content": "hello"}], tools=[], max_turns=2)
        request = await anext(session)
        await session.respond(request, content="answer", tool_calls=[], finish_reason="stop")
        done = await anext(session)
        assert done["content"] == "answer"
        with pytest.raises(StopAsyncIteration):
            await anext(session)
    assert session.returncode == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ["not json", '{"type":"unknown"}', '{"type":"tool_request","id":"t1"}'])
async def test_bridge_rejects_malformed_frames_without_echoing_payload(tmp_path, output):
    child = tmp_path / "child.py"
    child.write_text(f"input()\nprint({output!r},flush=True)\n")
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[], tools=[], max_turns=2)
        with pytest.raises(PiKernelError) as error:
            await anext(session)
        assert output not in str(error.value)


@pytest.mark.asyncio
async def test_bridge_does_not_treat_eof_as_success(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("input()\n")
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[], tools=[], max_turns=2)
        with pytest.raises(PiKernelError, match="pi_unexpected_exit"):
            await anext(session)


@pytest.mark.asyncio
async def test_bridge_cancellation_reaps_child(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("import time\ninput()\ntime.sleep(60)\n")
    session = PiKernelSession(command=[sys.executable, str(child)])

    async def run():
        async with session:
            await session.start(messages=[], tools=[], max_turns=2)
            await anext(session)

    task = asyncio.create_task(run())
    while session.process is None:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session.returncode is not None


@pytest.mark.asyncio
async def test_bridge_rejects_unissued_response(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("import time\ninput()\ntime.sleep(60)\n")
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[], tools=[], max_turns=2)
        with pytest.raises(PiKernelError, match="pi_response_mismatch"):
            await session.respond({"type": "tool_request", "id": "unknown"}, content="ok")


@pytest.mark.asyncio
async def test_child_does_not_inherit_provider_credentials_or_node_preload(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLAN_API_KEY", "synthetic-test-secret")
    monkeypatch.setenv("DATABASE_URL", "synthetic-test-database")
    monkeypatch.setenv("NODE_OPTIONS", "--import=untrusted.mjs")
    child = tmp_path / "child.py"
    child.write_text(
        "import json,os\ninput()\n"
        "assert not any(key in os.environ for key in ['TOKENPLAN_API_KEY','DATABASE_URL','NODE_OPTIONS'])\n"
        "print(json.dumps({'type':'done','content':'clean','messages':[],'finish_reason':'stop','turns':1}),flush=True)\n"
    )
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[], tools=[], max_turns=2)
        assert (await anext(session))["content"] == "clean"


@pytest.mark.asyncio
async def test_uncorrelated_child_tool_cannot_acquire_dispatch_authority(tmp_path):
    child = tmp_path / "child.py"
    child.write_text(
        "import json\ninput()\n"
        "print(json.dumps({'type':'tool_request','id':'t1','tool_call_id':'not-issued','name':'health_record','arguments':{}}),flush=True)\n"
    )
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[], tools=[], max_turns=2)
        with pytest.raises(PiKernelError, match="pi_unissued_tool_call"):
            await anext(session)


@pytest.mark.asyncio
async def test_done_frame_cannot_hide_unsuccessful_process_exit(tmp_path):
    child = tmp_path / "child.py"
    child.write_text(
        "import json,sys\ninput()\n"
        "print(json.dumps({'type':'done','content':'claimed success','messages':[],'finish_reason':'stop','turns':1}),flush=True)\n"
        "sys.exit(1)\n"
    )
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[], tools=[], max_turns=2)
        with pytest.raises(PiKernelError, match="pi_unsuccessful_exit"):
            await anext(session)


@pytest.mark.asyncio
async def test_silent_child_times_out_and_is_reaped(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("import time\ninput()\ntime.sleep(60)\n")
    session = PiKernelSession(command=[sys.executable, str(child)], timeout=0.1)
    with pytest.raises(PiKernelError, match="pi_invalid_frame"):
        async with session:
            await session.start(messages=[], tools=[], max_turns=2)
            await anext(session)
    assert session.returncode is not None


@pytest.mark.asyncio
async def test_missing_pi_runtime_never_falls_back_to_legacy_loop(tmp_path):
    with pytest.raises(PiKernelError, match="pi_runtime_unavailable"):
        async with PiKernelSession(command=[str(tmp_path / "missing-node")]):
            pytest.fail("unavailable runtime must fail before any tool call")


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_flag", ["false", "true", None])
async def test_child_preserves_explicit_runtime_flag_without_inheriting_secrets(
    tmp_path, monkeypatch, runtime_flag
):
    flag_name = "HEALTH_EVIDENCE_RUNTIME_ENABLED"
    if runtime_flag is None:
        monkeypatch.delenv(flag_name, raising=False)
    else:
        monkeypatch.setenv(flag_name, runtime_flag)
    for key in ("TOKENPLAN_API_KEY", "DATABASE_URL", "NODE_OPTIONS", "NODE_PATH"):
        monkeypatch.setenv(key, "synthetic-sensitive-value")
    child = tmp_path / "child.py"
    child.write_text(
        "import json,os\ninput()\n"
        f"assert os.environ.get({flag_name!r}) == {runtime_flag!r}\n"
        "assert not any(key in os.environ for key in "
        "['TOKENPLAN_API_KEY','DATABASE_URL','NODE_OPTIONS','NODE_PATH'])\n"
        "print(json.dumps({'type':'done','content':'clean','messages':[],"
        "'finish_reason':'stop','turns':1}),flush=True)\n"
    )
    async with PiKernelSession(command=[sys.executable, str(child)]) as session:
        await session.start(messages=[], tools=[], max_turns=2)
        assert (await anext(session))["content"] == "clean"
    assert session.returncode == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_flag", ["", "False", "TRUE", "0", "1", " false", "false\n", "synthetic-secret"])
async def test_invalid_runtime_flag_rejects_before_spawning_child(monkeypatch, runtime_flag):
    from unittest.mock import AsyncMock

    monkeypatch.setenv("HEALTH_EVIDENCE_RUNTIME_ENABLED", runtime_flag)
    spawn = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    session = PiKernelSession()
    with pytest.raises(PiKernelError) as error:
        async with session:
            pass
    assert str(error.value) == "pi_invalid_runtime_flag"
    spawn.assert_not_awaited()
    assert session.process is None
