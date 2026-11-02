#!/usr/bin/env python3
"""Live synthetic tool protocol checks; never executes a tool or uses user data.

Requires APP_ENV=test, DATABASE_URL=sqlite:///:memory: and provider credentials.
Uses the harness's audited ephemeral consent subject; production consent stays on.
Reports only case IDs, pass/fail, error types and timings, never provider payloads.
This is capability evidence, not a production latency or safety acceptance test.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

TOOLS = [
    {"type": "function", "function": {
        "name": "health_record", "description": "Synthetic water record; amount must be explicit in the current message.",
        "parameters": {"type": "object", "properties": {
            "record_type": {"type": "string", "enum": ["water"]},
            "data": {"type": "object", "properties": {"amount": {"type": "number"}},
                     "required": ["amount"], "additionalProperties": False},
        }, "required": ["record_type", "data"], "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "health_query", "description": "Read synthetic water records for an explicit date range.",
        "parameters": {"type": "object", "properties": {
            "record_type": {"type": "string", "enum": ["water"]},
            "start_date": {"type": "string"}, "end_date": {"type": "string"},
        }, "required": ["record_type", "start_date", "end_date"], "additionalProperties": False},
    }},
]
SYSTEM = (
    "This is a synthetic protocol evaluation. Use structured tools for explicit reads or writes. "
    "Never invent missing quantities or dates; ask when required fields are missing. "
    "Do not write if the CURRENT user says not to record, regardless of older turns. "
    "For greetings and a completed tool result answer directly. Never print tool syntax as text. "
    "Keep text answers under 30 words."
)
CASES = [
    ("nested_write", [{"role": "user", "content": "帮我记录：刚喝了500ml水。"}],
     ("health_record", {"record_type": "water", "data": {"amount": 500}})),
    ("scoped_read", [{"role": "user", "content": "查询2026-10-01到2026-10-02的饮水记录。"}],
     ("health_query", {"record_type": "water", "start_date": "2026-10-01", "end_date": "2026-10-02"})),
    ("negated_write", [
        {"role": "user", "content": "以后喝水都帮我记录。"},
        {"role": "assistant", "content": "每次记录前我会以你当前的指令为准。"},
        {"role": "user", "content": "刚喝了500ml水，但这次不要记录。"},
    ], None),
    ("missing_amount", [{"role": "user", "content": "帮我记录喝水了，还没告诉你喝了多少。"}], None),
    ("greeting", [{"role": "user", "content": "你好，只回复你好即可。"}], None),
    ("tool_result", [
        {"role": "user", "content": "查询2026-10-01到2026-10-02的饮水记录。"},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "synthetic-read-1", "type": "function", "function": {
                "name": "health_query", "arguments": json.dumps({
                    "record_type": "water", "start_date": "2026-10-01", "end_date": "2026-10-02",
                }),
            },
        }]},
        {"role": "tool", "tool_call_id": "synthetic-read-1",
         "content": '{"success":true,"records":[],"count":0}'},
    ], None),
]


def valid_response(calls, content, expected):
    if any(marker in content.lower() for marker in ("<invoke", "tool calls:", "[工具调用", "<tool_call")):
        return False
    if expected is None:
        return bool(content.strip()) and not calls
    if len(calls) != 1 or not calls[0].get("id"):
        return False
    function = calls[0].get("function", {})
    args = function.get("arguments")
    if isinstance(args, str):
        args = json.loads(args)
    return function.get("name") == expected[0] and args == expected[1]


async def run_case(model_id, case, stream, repeat):
    from app.services.llm.factory import create_provider_for_model_id

    case_id, messages, expected = case
    row = {"case": case_id, "stream": stream, "repeat": repeat}
    start = time.monotonic()
    first = None
    try:
        provider = create_provider_for_model_id(model_id)
        kwargs = dict(messages=[{"role": "system", "content": SYSTEM}, *messages],
                      tools=TOOLS, temperature=0, max_tokens=256)
        calls, content = [], ""
        async with asyncio.timeout(40):
            if stream:
                async for event in provider.chat_stream(**kwargs):
                    if event.get("type") == "content":
                        content += event.get("text", "")
                    elif event.get("type") == "tool_calls":
                        calls.extend(event.get("tool_calls") or [])
                    if first is None and (content.strip() or calls):
                        first = round((time.monotonic() - start) * 1000)
            else:
                result = await provider.chat(**kwargs, stream=False)
                if isinstance(result, dict):
                    calls, content = result.get("tool_calls") or [], result.get("content") or ""
                else:
                    content = str(result)
        row.update(passed=valid_response(calls, content, expected), tool_calls=len(calls), first_ms=first)
    except Exception as exc:
        row.update(passed=False, error_type=type(exc).__name__)
    row["total_ms"] = round((time.monotonic() - start) * 1000)
    return row


async def main(args):
    rows = []
    # Sequential, bounded repeats avoid load amplification and cache races.
    for repeat in range(args.repeat):
        for case in CASES:
            for stream in (False, True):
                row = await run_case(args.model_id, case, stream, repeat)
                rows.append(row)
                print(json.dumps(row), flush=True)
    result = {"model_id": args.model_id, "synthetic_only": True, "tools_executed": 0,
              "passed": all(row["passed"] for row in rows), "rows": rows}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--repeat", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    from scripts.harness_llm_regression_gate import _live_llm_eval_consent_scope

    with _live_llm_eval_consent_scope(True):
        sys.exit(asyncio.run(main(args)))
