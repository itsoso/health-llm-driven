import asyncio
import threading
import time

import pytest

from app.services.data_collection.garmin_executor import (
    GARMIN_EXECUTOR_MAX_WORKERS,
    run_garmin_blocking,
)


@pytest.mark.asyncio
async def test_garmin_blocking_work_does_not_stall_the_event_loop() -> None:
    started = threading.Event()
    release = threading.Event()

    def blocking_call() -> str:
        started.set()
        release.wait(timeout=2)
        return "done"

    task = asyncio.create_task(run_garmin_blocking(blocking_call))
    assert await asyncio.to_thread(started.wait, 1)

    before = time.monotonic()
    await asyncio.sleep(0.01)
    event_loop_delay = time.monotonic() - before

    release.set()
    assert await task == "done"
    assert event_loop_delay < 0.1


def test_garmin_executor_has_a_small_explicit_capacity() -> None:
    assert GARMIN_EXECUTOR_MAX_WORKERS == 2
