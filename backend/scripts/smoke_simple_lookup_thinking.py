"""Synthetic Qwen3.8 lookup A/B: no tools executed or real user records used.

Requires APP_ENV=test, DATABASE_URL=sqlite:///:memory: and TokenPlan credentials.
Measures first content and completed answers, retaining failures and cold samples.
Synthetic answer text is retained for semantic review. This is not App latency.
"""

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
logging.disable(logging.CRITICAL)
from app.services.llm.factory import create_provider_for_model_id

from scripts.harness_llm_regression_gate import _live_llm_eval_consent_scope

SYSTEM = "你是合成数据查询助手。只依据给定工具结果简短回答，不新增数值，不给医学建议，不调用工具。输出为一句中文。"
CASES = [
    (
        "water",
        "今天饮水记录共两条：200毫升和300毫升；总量500毫升。请报告总量。",
        ["500"],
    ),
    (
        "weights",
        "最近三次体重记录：70.1千克、70.3千克、70.2千克。按此顺序列出，不分析。",
        ["70.1", "70.3", "70.2"],
    ),
    ("empty", "查询已完成：本周没有睡眠记录。说明没有记录，不估计睡眠时长。", ["没有"]),
]


async def main(args):
    rows = []
    p = create_provider_for_model_id("qwen3.8-max")
    for repeat in range(args.repeat):
        for name, query, required in CASES:
            for mode in (
                ["default", "disabled"] if repeat % 2 == 0 else ["disabled", "default"]
            ):
                kw = {
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0,
                    "max_tokens": 2048,
                }
                if mode == "disabled":
                    kw["enable_thinking"] = False
                start = time.monotonic()
                first = None
                content = ""
                calls = []
                finish = None
                row = {"case": name, "repeat": repeat, "mode": mode}
                try:
                    async with asyncio.timeout(65):
                        async for e in p.chat_stream(**kw):
                            if e.get("type") == "content":
                                chunk = e.get("text", "")
                                content += chunk
                                if first is None and chunk.strip():
                                    first = round((time.monotonic() - start) * 1000)
                            elif e.get("type") == "tool_calls":
                                calls += e.get("tool_calls") or []
                            elif e.get("type") == "finish":
                                finish = e.get("finish_reason")
                    numbers = re.findall(r"\d+(?:\.\d+)?", content)
                    expected_numbers = [] if name == "empty" else required
                    row.update(
                        passed=finish == "stop"
                        and bool(content.strip())
                        and not calls
                        and sorted(numbers) == sorted(expected_numbers)
                        and all(x in content for x in required),
                        finish=finish,
                        chars=len(content),
                        tool_call_count=len(calls),
                        answer=content,
                    )
                except Exception as e:  # noqa: BLE001 - retain failed samples, exit nonzero
                    row.update(passed=False, error_type=type(e).__name__)
                row.update(
                    first_ms=first, total_ms=round((time.monotonic() - start) * 1000)
                )
                rows.append(row)
                print(json.dumps(row), flush=True)
                args.output.write_text(
                    json.dumps(
                        {"synthetic_only": True, "model": "qwen3.8-max", "rows": rows},
                        indent=2,
                    )
                    + "\n"
                )
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with _live_llm_eval_consent_scope(True):
        sys.exit(asyncio.run(main(args)))
