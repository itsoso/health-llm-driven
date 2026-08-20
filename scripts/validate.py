#!/usr/bin/env python3
"""validate.py — 编码 agent 的快速结构闸门 (Agent Operating Harness Phase 4).

把「确定性 + 快」的检查聚合成一条命令, 给改完代码的 agent 一个秒级反馈环。
**不重跑重型测试套件** —— 那是 `scripts/run-all-tests.sh` / CI 的活, 这里 --full 委托过去,
不重造 (复用 > 重写)。

  python scripts/validate.py          # 结构闸门: system-map + dossier + skill governance + ruff
  python scripts/validate.py --full   # 额外委托 run-all-tests.sh 跑全栈测试
  python scripts/validate.py -v       # 打印失败检查的完整尾部输出

退出码: 0 = 所有 blocking 检查通过; 1 = 有 blocking 失败。
report-only 检查 (ruff) 不影响退出码, 只暴露给人看 (与 CI 的 non-blocking 立场一致)。

System Map 检查通过独立的 Python 3.12 `.venv` wrapper 执行，避免依赖调用
`validate.py` 的系统 Python 环境。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Check:
    def __init__(self, name, argv, *, blocking=True, skip_if_missing=None):
        self.name = name
        self.argv = argv
        self.blocking = blocking
        self.skip_if_missing = skip_if_missing


def run(check: Check):
    if check.skip_if_missing and shutil.which(check.skip_if_missing) is None:
        return "skip", 0.0, f"{check.skip_if_missing} 未安装, 跳过"
    t = time.monotonic()
    try:
        p = subprocess.run(check.argv, cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError as e:
        return "skip", time.monotonic() - t, str(e)
    dt = time.monotonic() - t
    return ("pass" if p.returncode == 0 else "fail"), dt, (p.stdout + p.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Agent Operating Harness 结构闸门")
    ap.add_argument("--full", action="store_true", help="额外委托 run-all-tests.sh 跑全栈测试")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印失败检查的完整尾部输出")
    args = ap.parse_args()

    checks = [
        Check("system-map", ["bash", "scripts/system-map-check.sh"], blocking=True),
        Check(
            "dossier-consistency",
            [sys.executable, "backend/scripts/check_dossier_consistency.py"],
            blocking=True,
        ),
        Check(
            "agent-skill-governance",
            [sys.executable, "scripts/check_agent_skill_governance.py", "check"],
            blocking=True,
        ),
        Check(
            "ruff (backend, report-only)",
            ["ruff", "check", "backend/app", "--output-format=concise"],
            blocking=False,
            skip_if_missing="ruff",
        ),
    ]
    if args.full:
        checks.append(Check("run-all-tests.sh (全栈)", ["bash", "scripts/run-all-tests.sh"], blocking=True))

    results = []
    hard_fail = False
    for c in checks:
        status, dt, out = run(c)
        results.append((c, status, dt, out))
        if status == "fail" and c.blocking:
            hard_fail = True

    icon = {"pass": "✓", "fail": "✗", "skip": "–"}
    print("\n  validate.py — Agent Operating Harness 结构闸门\n")
    total = 0.0
    for c, status, dt, out in results:
        total += dt
        tag = "" if c.blocking else "  (report-only)"
        disp = "⚠" if (status == "fail" and not c.blocking) else icon[status]
        print(f"  {disp}  {c.name:<32} {dt:5.1f}s{tag}")
        if status == "fail" and (args.verbose or c.blocking):
            for line in out.strip().splitlines()[-12:]:
                print(f"        {line}")
    print(f"\n  合计 {total:.1f}s")
    if not args.full:
        print("  ⓘ 全栈测试未跑 —— 需要时: python scripts/validate.py --full  (或 bash scripts/run-all-tests.sh)")
    print("  ✅ 通过" if not hard_fail else "  ❌ 有 blocking 检查失败")
    print()
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
