"""异步辅助工具 — 在同步上下文（如 Celery 任务）中安全运行协程"""
import asyncio
from typing import TypeVar, Coroutine, Any

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    在同步上下文中安全运行一个协程并返回结果。

    与直接调用 asyncio.run() 相比，此函数会先检查当前线程是否已有
    正在运行的事件循环。若有，则在新线程中执行；若无，则创建新循环运行。
    适用于 Celery worker 等无事件循环的同步环境。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 已有运行中的事件循环（不常见，但防御性处理）
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        # 无事件循环 — Celery worker 的正常情况
        return asyncio.run(coro)
