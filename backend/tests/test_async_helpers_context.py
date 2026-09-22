"""The sync-to-async bridge preserves security context in both execution modes."""
import asyncio
from contextvars import ContextVar

import pytest

from app.utils.async_helpers import run_async


@pytest.mark.parametrize("running_loop", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_run_async_copies_context_without_leaking_child_changes(running_loop, failure):
    guard = ContextVar("test_request_guard", default=None)

    async def child():
        assert guard.get() == "caller-guard"
        guard.set("child-only")
        await asyncio.sleep(0)
        if failure:
            raise RuntimeError("synthetic failure")
        return "completed"

    def invoke():
        if failure:
            with pytest.raises(RuntimeError, match="synthetic failure"):
                run_async(child())
        else:
            assert run_async(child()) == "completed"
        assert guard.get() == "caller-guard"

    async def invoke_inside_loop():
        invoke()

    token = guard.set("caller-guard")
    try:
        if running_loop:
            asyncio.run(invoke_inside_loop())
        else:
            invoke()
        assert guard.get() == "caller-guard"
    finally:
        guard.reset(token)
