"""R2 探针 — TokenPlan(qwen)对 force tool_choice / strict:true 的真网验证。

纪律:prod 翻 flag 前先跑真网探针(镜像 probe_explicit_cache 的先例)。任一子探不过,
对应能力就不开 —— fail-loud,不猜。只调 chat completions,零写库零副作用。

用法(需 TOKENPLAN_API_KEY;从仓库根或 backend/ 跑均可):
    python backend/scripts/probe_tool_choice_strict.py
    python backend/scripts/probe_tool_choice_strict.py --models qwen3.6-flash
退出码:0=全过;1=有子探失败(输出逐项判定,按需选择性启用)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

# 缩小版 health_record 工具(探针专用;够真实又不给探针背 8k schema)
TOOL = {
    "type": "function",
    "function": {
        "name": "health_record",
        "description": "记录用户健康数据(饮水/体重等)。用户要求记录时必须调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "enum": ["water", "weight"]},
                "data": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "integer", "description": "毫升"},
                        "weight": {"type": "number", "description": "kg"},
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["record_type", "data"],
            "additionalProperties": False,
        },
    },
}

DISTRACT = {
    "type": "function",
    "function": {
        "name": "health_query",
        "description": "查询健康数据。",
        "parameters": {"type": "object", "properties": {"dimension": {"type": "string"}},
                        "required": ["dimension"], "additionalProperties": False},
    },
}


def _load_key() -> str:
    key = os.environ.get("TOKENPLAN_API_KEY")
    if key:
        return key
    for env in (Path(__file__).resolve().parents[2] / ".env",
                Path(__file__).resolve().parents[1] / ".env"):
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("TOKENPLAN_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    print("FATAL: 无 TOKENPLAN_API_KEY(env 或 根.env)"); raise SystemExit(2)


def _call(client, model: str, **kw):
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "喝了300ml水"}],
        max_tokens=200,
        **kw,
    )


def probe_model(client, model: str) -> dict:
    out: dict = {"model": model}

    # ① force tool_choice:必须实际调 health_record(不是仅接受参数不报错)
    try:
        r = _call(client, model, tools=[TOOL, DISTRACT],
                  tool_choice={"type": "function", "function": {"name": "health_record"}})
        calls = r.choices[0].message.tool_calls or []
        forced = bool(calls) and calls[0].function.name == "health_record"
        out["force_tool_choice"] = "PASS" if forced else f"FAIL(called={[c.function.name for c in calls]})"
    except Exception as e:  # noqa: BLE001
        out["force_tool_choice"] = f"REJECTED({type(e).__name__}: {str(e)[:90]})"

    # ② strict:true:端点接受 + 参数合法(不接受=不开 strict,不算事故)
    strict_tool = json.loads(json.dumps(TOOL))
    strict_tool["function"]["strict"] = True
    try:
        r = _call(client, model, tools=[strict_tool], tool_choice="auto")
        calls = r.choices[0].message.tool_calls or []
        if calls:
            args = json.loads(calls[0].function.arguments)
            ok = args.get("record_type") in ("water", "weight") and isinstance(args.get("data"), dict)
            out["strict_mode"] = "PASS" if ok else f"PASS_ACCEPTED_BAD_ARGS({calls[0].function.arguments[:80]})"
        else:
            out["strict_mode"] = "ACCEPTED_NO_CALL(strict 被接受但模型没调工具)"
    except Exception as e:  # noqa: BLE001
        out["strict_mode"] = f"REJECTED({type(e).__name__}: {str(e)[:90]})"
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="qwen3.6-flash,qwen3.7-max")
    args = parser.parse_args()

    from openai import OpenAI
    client = OpenAI(api_key=_load_key(), base_url=BASE)

    failed = False
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        r = probe_model(client, model)
        print(json.dumps(r, ensure_ascii=False))
        if not str(r["force_tool_choice"]).startswith("PASS"):
            failed = True  # force 是 R2 主目标;strict 仅试点,REJECTED 不算探针失败
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
