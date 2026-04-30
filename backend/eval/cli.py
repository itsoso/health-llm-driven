"""Eval CLI — `python -m eval run --suite safety [--baseline main]`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.runner import run_suite, write_baseline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval", description="Golden Set runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="跑一个 suite")
    p_run.add_argument("--suite", required=True, help="如 safety / orchestrator / insight")
    p_run.add_argument("--baseline", default=None, help="对比 baselines/<name>.json 找 regression")
    p_run.add_argument("--json", dest="as_json", action="store_true", help="输出 JSON 而非文本")
    p_run.add_argument("--fail-on-regression", action="store_true",
                       help="存在 regression 时退出码 1")

    p_save = sub.add_parser("save-baseline", help="跑一遍 suite 写为 baseline")
    p_save.add_argument("--suite", required=True)
    p_save.add_argument("--name", default="main")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        report = run_suite(args.suite, baseline=args.baseline)
        if args.as_json:
            print(report.model_dump_json(indent=2))
        else:
            print(report.summarize())
            for r in report.cases:
                mark = "✓" if r.passed else ("E" if r.error else "✗")
                line = f"  [{mark}] {r.case_id} score={r.score:.2f} {r.latency_ms}ms"
                if r.error:
                    line += f"  ERROR: {r.error}"
                elif not r.passed:
                    s = r.details.get("scoring", {})
                    if s.get("missing"):
                        line += f"  missing={s['missing']}"
                    if s.get("unexpected"):
                        line += f"  unexpected={s['unexpected']}"
                print(line)
            if report.regression:
                print(f"\nREGRESSION ({len(report.regression)}): {report.regression}")
        if args.fail_on_regression and report.regression:
            return 1
        return 0 if report.failed == 0 and report.errored == 0 else 1

    if args.cmd == "save-baseline":
        report = run_suite(args.suite)
        path = write_baseline(report, args.name)
        print(f"Baseline 写入: {path}  ({report.summarize()})")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
