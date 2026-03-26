"""Gunicorn 配置 — 确保 scheduler 只在一个 worker 中运行"""
import os


def post_fork(server, worker):
    """worker fork 后回调：只有第一个 worker 运行 scheduler"""
    # worker.age 从 1 开始递增，第一个 worker 的 age 为 1
    if worker.age == 1:
        os.environ["SCHEDULER_ENABLED"] = "1"
        server.log.info(f"Worker {worker.pid} (age={worker.age}) designated as scheduler leader")
    else:
        os.environ.pop("SCHEDULER_ENABLED", None)
