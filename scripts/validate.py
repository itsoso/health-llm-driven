#!/usr/bin/env python3
"""validate.py — 编码 agent 的快速结构闸门 (Agent Operating Harness Phase 4).

把「确定性 + 快」的检查聚合成一条命令, 给改完代码的 agent 一个秒级反馈环。
**不重跑重型测试套件** —— 那是 `scripts/run-all-tests.sh` / CI 的活, 这里 --full 委托过去,
不重造 (复用 > 重写)。

  python scripts/validate.py          # 结构闸门: system-map + dossier-consistency (blocking) + ruff (report-only)
  python scripts/validate.py --full   # 额外委托 run-all-tests.sh 跑全栈测试
  python scripts/validate.py -v       # 打印失败检查的完整输出

退出码: 0 = 所有 blocking 检查通过; 1 = 有 blocking 失败。
report-only 检查 (ruff) 不影响退出码, 只暴露给人看 (与 CI 的 non-blocking 立场一致)。

System Map 检查通过独立的 Python 3.12 `.venv` wrapper 执行，避免依赖调用
`validate.py` 的系统 Python 环境。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR: Path | None = None


def validation_state_dir(repo: Path) -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "cannot resolve Git common directory")
    path = Path(completed.stdout.strip()) / "reva-release-state"
    if path.is_symlink():
        raise RuntimeError(f"refusing symlinked validation state directory: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


class Check:
    def __init__(self, name, argv, *, blocking=True, skip_if_missing=None):
        self.name = name
        self.argv = argv
        self.blocking = blocking
        self.skip_if_missing = skip_if_missing


def _private_log_path(log_dir: Path, check: Check) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", check.name).strip("-") or "check"
    return log_dir / f"{safe_name}.log"


def run(check: Check):
    if RUN_LOG_DIR is None:
        raise RuntimeError("validation log directory is not initialized")
    log_dir = RUN_LOG_DIR
    log_path = _private_log_path(log_dir, check)
    if check.skip_if_missing and shutil.which(check.skip_if_missing) is None:
        message = f"{check.skip_if_missing} 未安装, 跳过\n"
        log_path.write_text(message, encoding="utf-8")
        log_path.chmod(0o600)
        return "skip", 0.0, message, log_path
    t = time.monotonic()
    try:
        with log_path.open("w", encoding="utf-8") as log_handle:
            log_path.chmod(0o600)
            p = subprocess.run(
                check.argv,
                cwd=ROOT,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
    except FileNotFoundError as e:
        message = f"{e}\n"
        log_path.write_text(message, encoding="utf-8")
        log_path.chmod(0o600)
        return "skip", time.monotonic() - t, message, log_path
    dt = time.monotonic() - t
    return (
        "pass" if p.returncode == 0 else "fail",
        dt,
        log_path.read_text(encoding="utf-8", errors="replace"),
        log_path,
    )


def run_parallel(checks: list[Check]):
    if not checks:
        return []
    worker_count = min(4, len(checks))
    ordered = [None] * len(checks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(run, check): index for index, check in enumerate(checks)}
        for future in concurrent.futures.as_completed(futures):
            ordered[futures[future]] = future.result()
    return ordered


def _result_parts(result, log_dir: Path, check: Check):
    if len(result) == 4:
        return result
    status, duration, output = result
    return status, duration, output, _private_log_path(log_dir, check)


def main() -> int:
    global RUN_LOG_DIR
    ap = argparse.ArgumentParser(description="Agent Operating Harness 结构闸门")
    ap.add_argument("--full", action="store_true", help="额外委托 run-all-tests.sh 跑全栈测试")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印失败检查的完整输出")
    args = ap.parse_args()

    structural_checks = [
        Check("system-map", ["bash", "scripts/system-map-check.sh"], blocking=True),
        Check(
            "dossier-consistency",
            [sys.executable, "backend/scripts/check_dossier_consistency.py"],
            blocking=True,
        ),
        Check(
            "ruff (backend, report-only)",
            ["ruff", "check", "backend/app", "--output-format=concise"],
            blocking=False,
            skip_if_missing="ruff",
        ),
        Check("git-diff-check", ["git", "diff", "--check", "HEAD"], blocking=True),
    ]
    os.umask(0o077)
    log_dir = validation_state_dir(ROOT) / "logs" / f"validate-{time.time_ns()}-{os.getpid()}"
    if log_dir.is_symlink():
        raise RuntimeError(f"refusing symlinked validation log directory: {log_dir}")
    log_dir.mkdir(parents=True, mode=0o700)
    log_dir.chmod(0o700)
    RUN_LOG_DIR = log_dir

    started = time.monotonic()
    checks = list(structural_checks)
    results = run_parallel(structural_checks)
    if args.full:
        full_check = Check(
            "run-all-tests.sh (全栈)",
            ["bash", "scripts/run-all-tests.sh"],
            blocking=True,
        )
        checks.append(full_check)
        # The delegated suite owns its own four-worker pool. Run it after the
        # structural pool so the process-wide validation ceiling stays at four.
        results.append(run(full_check))

    hard_fail = False
    for c, result in zip(checks, results, strict=True):
        status, _dt, _out, _log_path = _result_parts(result, log_dir, c)
        if status == "fail" and c.blocking:
            hard_fail = True

    icon = {"pass": "✓", "fail": "✗", "skip": "–"}
    print("\n  validate.py — Agent Operating Harness 结构闸门\n")
    for c, result in zip(checks, results, strict=True):
        status, dt, out, log_path = _result_parts(result, log_dir, c)
        tag = "" if c.blocking else "  (report-only)"
        disp = "⚠" if (status == "fail" and not c.blocking) else icon[status]
        print(f"  {disp}  {c.name:<32} {dt:5.1f}s{tag}  [{log_path}]")
        if status == "fail" and (args.verbose or c.blocking):
            lines = out.strip().splitlines()
            selected = lines if args.verbose else lines[-12:]
            for line in selected:
                print(f"        {line}")
    wall_time = time.monotonic() - started
    print(f"\n  墙钟耗时 {wall_time:.1f}s（并发上限 4）")
    print(f"  私有日志 {log_dir}")
    if not args.full:
        print("  ⓘ 全栈测试未跑 —— 需要时: python scripts/validate.py --full  (或 bash scripts/run-all-tests.sh)")
    print("  ✅ 通过" if not hard_fail else "  ❌ 有 blocking 检查失败")
    print()
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
