"""Closed Pi transports fail explicitly without retrying tool decisions."""
import asyncio
from types import SimpleNamespace

import pytest

from app.services.pi_kernel import PiKernelError, PiKernelSession


@pytest.mark.parametrize("stop_child", [False, True])
def test_real_pi_exit_during_model_await_is_transport_failure(stop_child):
    uvloop = pytest.importorskip('uvloop')

    async def exercise():
        async with PiKernelSession() as session:
            await session.start(messages=[{'role': 'user', 'content': 'Public weather query'}], tools=[], max_turns=2)
            request = await anext(session)
            assert request['type'] == 'model_request'
            if stop_child:
                session.process.terminate()
                await asyncio.wait_for(session.process.wait(), 3)
                with pytest.raises(PiKernelError, match='^pi_transport_failed$'):
                    await session.respond(request, content='Synthetic answer', tool_calls=[], finish_reason='stop')
            else:
                await session.respond(request, content='Synthetic answer', tool_calls=[], finish_reason='stop')
                done = await anext(session)
                assert done['type'] == 'done'
                assert done['content'] == 'Synthetic answer'
                assert done['finish_reason'] == 'stop'

    uvloop.run(exercise())


class ControlledWriter:
    def __init__(self, error, *, closes=False):
        self.error = error
        self.closes = closes
        self.closed = False
        self.writes = 0

    def is_closing(self):
        return self.closed

    def write(self, payload):
        self.writes += 1
        self.closed = self.closes
        raise self.error


@pytest.mark.asyncio
async def test_close_between_precheck_and_write_is_normalized_without_retry():
    writer = ControlledWriter(RuntimeError('synthetic closed transport'), closes=True)
    session = PiKernelSession()
    session.process = SimpleNamespace(stdin=writer, returncode=None)
    with pytest.raises(PiKernelError, match='^pi_transport_failed$') as raised:
        await session._send({'type': 'model_response'})
    assert type(raised.value.__cause__) is RuntimeError
    assert writer.writes == 1


@pytest.mark.asyncio
async def test_unrelated_runtime_error_from_open_transport_propagates():
    original = RuntimeError('synthetic unrelated failure')
    writer = ControlledWriter(original)
    session = PiKernelSession()
    session.process = SimpleNamespace(stdin=writer, returncode=None)
    with pytest.raises(RuntimeError) as raised:
        await session._send({'type': 'model_response'})
    assert raised.value is original
    assert writer.writes == 1


@pytest.mark.asyncio
async def test_transport_cancellation_is_not_normalized_or_retried():
    original = asyncio.CancelledError()
    writer = ControlledWriter(original, closes=True)
    session = PiKernelSession()
    session.process = SimpleNamespace(stdin=writer, returncode=None)
    with pytest.raises(asyncio.CancelledError) as raised:
        await session._send({'type': 'model_response'})
    assert raised.value is original
    assert writer.writes == 1
