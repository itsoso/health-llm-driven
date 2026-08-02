"""Isolate blocking Garmin SDK calls from the application event loop."""
from __future__ import annotations

import asyncio
import contextvars
import inspect
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable


GARMIN_EXECUTOR_MAX_WORKERS = 2

_garmin_executor = ThreadPoolExecutor(
    max_workers=GARMIN_EXECUTOR_MAX_WORKERS,
    thread_name_prefix="garmin-blocking",
)


def _invoke(call: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    result = call(*args, **kwargs)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


async def run_garmin_blocking(
    call: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run one sync or async Garmin flow on the dedicated bounded executor."""
    loop = asyncio.get_running_loop()
    context = contextvars.copy_context()
    invoke = partial(context.run, _invoke, call, args, kwargs)
    return await loop.run_in_executor(_garmin_executor, invoke)
