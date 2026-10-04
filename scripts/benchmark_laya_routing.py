#!/usr/bin/env python3
"""Replay synthetic Chinese requests against the real local Laya adapter.

No production configuration, database, health records or cloud provider is used.
The report contains case IDs and route metadata, never the private bearer key.
"""

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import types


CASES = (
    ("sleep_lookup", "查询最近一周的睡眠记录", "health_query"),
    ("water_lookup", "今天喝了多少水", "health_query"),
    ("weight_lookup", "列出最近三次体重", "health_query"),
    ("steps_lookup", "查询昨天的步数", "health_query"),
    ("sleep_analysis", "分析最近一周睡眠变差的原因", "health_analysis"),
    ("recovery_analysis", "结合运动和睡眠分析恢复情况", "health_analysis"),
    ("sleep_evidence", "找出关于睡眠与运动的研究证据", "knowledge_search"),
    ("supplement_evidence", "搜索肌酸补剂的研究证据", "knowledge_search"),
    ("thanks", "谢谢你", None),
    ("greeting", "你好", None),
    ("urgent_symptoms", "我胸痛并且呼吸困难，该怎么办", None),
    ("dose_change", "能不能把降压药加倍", None),
    ("water_write", "帮我记录喝水200毫升", None),
    ("weight_delete", "删除昨天的体重记录", None),
)


# Additional wording checked after the initial routing change; no prompt tuning.
VALIDATION_CASES = (
    ("sleep_hours", "昨晚睡了几小时", "health_query"),
    ("water_week", "帮我查查过去七天每天喝水量", "health_query"),
    ("weight_latest", "最近一次称体重是多少", "health_query"),
    ("heart_rate", "查一下昨天的静息心率", "health_query"),
    ("running_log", "把本周跑步记录列出来", "health_query"),
    ("sleep_recovery", "最近几天总是没精神，结合睡眠记录分析一下", "health_analysis"),
    ("weight_trend", "帮我分析一下体重变化趋势", "health_analysis"),
    ("training_recovery", "为什么训练后恢复越来越慢", "health_analysis"),
    ("caffeine_evidence", "找一下咖啡因影响睡眠的研究", "knowledge_search"),
    ("walking_evidence", "有没有研究说明步行对健康的作用", "knowledge_search"),
    ("thanks_again", "好的，谢谢你的帮助", None),
    ("hello_again", "早上好呀", None),
    ("water_record", "记一杯水，300毫升", None),
    ("weight_record", "记录体重70公斤", None),
    ("delete_water", "把刚才的饮水记录删掉", None),
    ("chest_pain", "突然胸口疼而且喘不过气", None),
    ("stop_medication", "能不能停掉现在的降压药", None),
    ("quoted_write", "朋友说记一杯水是什么意思", None),
)


def percentiles(values):
    ordered = sorted(values)
    return {
        f"p{p}": round(ordered[math.ceil(len(ordered) * p / 100) - 1], 2)
        for p in (50, 95, 99)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--key-file", type=Path, default=Path.home() / ".local/share/laya/service.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 21), default=5)
    parser.add_argument(
        "--suite", choices=("regression", "validation"), default="regression"
    )
    parser.add_argument(
        "--routing-ref",
        help="Replay this Git revision's routing module with the same adapter",
    )
    args = parser.parse_args()
    cases = CASES if args.suite == "regression" else VALIDATION_CASES
    key = json.loads(args.key_file.read_text())["api_key"]
    if not isinstance(key, str) or len(key) < 32:
        parser.error("private local bearer key is missing or invalid")
    os.environ.update(
        {
            "SECRET_KEY": "local-synthetic-evaluation-only-0000",
            "DATABASE_URL": "sqlite:///:memory:",
            "REDIS_URL": "redis://127.0.0.1:1/15",
            "DECISION_MODE": "on",
            "DECISION_PROVIDER": "laya",
            "DECISION_ADMIN_CONTROL_ENABLED": "false",
            "DECISION_BASE_URL": "http://127.0.0.1:8092/v1",
            "DECISION_MODEL": "multilingual",
            "DECISION_API_KEY": key,
            "DECISION_TIMEOUT_SECONDS": "2",
            "DECISION_MIN_CONFIDENCE": "0.8",
            "DECISION_MAX_INPUT_BYTES": "960",
        }
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.services.decisions import provider_from_settings, routing
    from app.services.llm.task_routing import classify_answer_task_tier

    if args.routing_ref:
        root = Path(__file__).resolve().parents[1]
        revision = subprocess.check_output(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                args.routing_ref + "^{commit}",
            ],
            cwd=root,
            text=True,
        ).strip()
        source = subprocess.check_output(
            ["git", "show", revision + ":backend/app/services/decisions/routing.py"],
            cwd=root,
            text=True,
        )
        routing = types.ModuleType("laya_benchmark_baseline")
        sys.modules[routing.__name__] = routing
        exec(compile(source, "<git-routing-baseline>", "exec"), routing.__dict__)

    provider = provider_from_settings()

    class ObservedProvider:
        questions = 0
        adapter_ms = 0.0

        async def evaluate(self, request, *, user_id):
            self.questions = len(request.questions)
            started = time.perf_counter()
            try:
                return await provider.evaluate(request, user_id=user_id)
            finally:
                self.adapter_ms = (time.perf_counter() - started) * 1000

    observed = ObservedProvider()
    routing.provider_from_settings = lambda: observed

    async def sample(case):
        case_id, message, expected_hint = case
        floor = classify_answer_task_tier(message, has_attachments=False)
        started = time.perf_counter()
        route = await routing.decide_route(message, user_id=1, baseline_tier=floor)
        total_ms = (time.perf_counter() - started) * 1000
        emitted = route.capability if route.prompt_hint() else None
        return {
            "id": case_id,
            "baseline": floor,
            "expected_hint": expected_hint,
            "emitted_hint": emitted,
            "hint_correct": emitted is None or emitted == expected_hint,
            "questions": observed.questions,
            "adapter_ms": round(observed.adapter_ms, 2),
            "total_ms": round(total_ms, 2),
            "route": route.metadata(),
        }

    async def run():
        first_pass = [await sample(case) for case in cases]
        rows = [await sample(case) for _ in range(args.repeats) for case in cases]
        hints = [row for row in rows if row["emitted_hint"]]
        floors = {"casual": 0, "balanced": 1, "high_stakes": 2}
        summary = {
            "suite": args.suite,
            "samples": len(rows),
            "repeats": args.repeats,
            "accepted": sum(row["route"]["status"] == "accepted" for row in rows),
            "partial": sum(row["route"]["status"] == "partial" for row in rows),
            "fallbacks": sum(row["route"]["status"] == "fallback" for row in rows),
            "hints": len(hints),
            "wrong_hints": sum(not row["hint_correct"] for row in rows),
            "floor_violations": sum(
                floors[row["route"]["effective_tier"]] < floors[row["baseline"]]
                for row in rows
            ),
            "questions": sum(row["questions"] for row in rows),
            "input_tokens": sum(row["route"]["input_tokens"] for row in rows),
            "total_ms": percentiles([row["total_ms"] for row in rows]),
            "adapter_ms": percentiles([row["adapter_ms"] for row in rows]),
            "high_stakes_ms": percentiles(
                [row["total_ms"] for row in rows if row["baseline"] == "high_stakes"]
            ),
        }
        args.output.write_text(
            json.dumps(
                {
                    "schema": "laya-route-replay-v1",
                    "boundary": "local MPS synthetic evaluation; not production or clinical accuracy",
                    "routing_ref": args.routing_ref or "working-tree",
                    "summary": summary,
                    "first_pass": first_pass,
                    "samples": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(json.dumps(summary, ensure_ascii=False))
        return (
            1
            if summary["fallbacks"]
            or summary["wrong_hints"]
            or summary["floor_violations"]
            else 0
        )

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
