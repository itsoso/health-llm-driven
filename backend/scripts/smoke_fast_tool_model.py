#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真网络烟测: 验证快工具模型 (默认 qwen3.6-flash) 吐**干净的结构化 tool_calls**。

背景 (工具决策轮快路由, tool_round_fast_routed):
  agent_executor 把首个工具决策轮降到一个 fast + reliable_tool_calling 模型
  (qwen3.6-flash) 以砍时延。安全网 (3 层文本/XML/bracket 兜底解析 + 直接答文本
  丢弃重合成) 会兜住坏工具调用, 但**上线前**应先真网络确认这个 fast 模型确实
  能吐结构化 tool_calls, 而不是把工具调用写成文本 —— 否则每轮都要走一次兜底,
  白白吃掉快路由省下的时延。

  本脚本就是 "上线前那道真网络门"。CI **不**跑 (需 TOKENPLAN_API_KEY + 真出网)。
  reviewer / release-engineer 在把 task_tiered_routing 打到 prod 前手动跑一次。

判定 (任一失败 exit 非零):
  1. provider.chat(..., tools=[...], stream=False) 对一个明确该调工具的 prompt,
     返回 dict 且带非空 tool_calls (结构化);
  2. tool_calls[0].function.name == 期望工具名;
  3. arguments 是可 json.loads 的对象 (不是文本/弯引号/XML 泄漏);
  4. 返回的 content 里**不**含文本式工具调用标记 (Tool calls: / <invoke> / [工具调用:)。

用法:
  export TOKENPLAN_API_KEY=...            # prod 已有
  export SECRET_KEY=... GARMIN_ENCRYPTION_KEY=...   # settings 需要
  python3 backend/scripts/smoke_fast_tool_model.py                 # 默认 qwen3.6-flash
  python3 backend/scripts/smoke_fast_tool_model.py --model-id deepseek-v4-flash
  python3 backend/scripts/smoke_fast_tool_model.py --repeat 5      # 抽多次看稳定性
  python3 backend/scripts/smoke_fast_tool_model.py --parallel      # rank5: 并行门, 一轮 ≥2 call

  退出码: 0 = 干净结构化 tool_calls; 非 0 = 不可靠 (含预算/配置缺失也非 0)。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

# app.config 需要的 env (import app 前设好, 镜像 conftest / run_system_kb_eval)。
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

_ROOT = Path(__file__).resolve().parents[1]  # backend/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 文本式工具调用泄漏标记 (与 agent_executor 的兜底解析同源, 简化正则)
_TEXT_LEAK_RE = re.compile(r"(Tool\s*calls?\s*:|<invoke\b|<minimax:tool_call|\[工具调用[:：])", re.I)

_DEFAULT_MODEL_ID = "qwen3.6-flash"
_EXPECTED_TOOL = "health_record"

# 一个明确该触发 health_record 写入意图的 prompt。
_SYSTEM = (
    "你是健康助理。用户要记录健康数据时, 必须用结构化 function calling 调用 health_record, "
    "绝不要把工具调用写成文本。"
)
_USER = "帮我记录一下: 我刚喝了 500ml 水。"

_TOOLS = [{
    "type": "function",
    "function": {
        "name": _EXPECTED_TOOL,
        "description": "记录一条健康数据 (饮水/体重/血压/饮食/症状等)。",
        "parameters": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "description": "如 water/weight/symptom"},
                "data": {"type": "object", "description": "记录内容, 如 {\"amount\": 500}"},
            },
            "required": ["record_type", "data"],
        },
    },
}]


# 并行工具调用 (rank5) 专用 prompt: 明确要求记录**两件**事 → 期望一轮回 ≥2 个 tool_call。
_USER_PARALLEL = "帮我记录两件事: 我刚喝了 500ml 水, 又吃了一个苹果。"


async def _run_once(model_id: str) -> tuple[bool, str]:
    """跑一次, 返回 (ok, detail)。"""
    from app.services.llm.factory import create_provider_for_model_id

    provider = create_provider_for_model_id(model_id)
    resp = await provider.chat(
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": _USER}],
        model=None,
        temperature=0.0,
        max_tokens=512,
        stream=False,
        tools=_TOOLS,
    )
    # 结构化 tool_calls 时 provider 返回 dict; 纯文本时返回 str。
    if not isinstance(resp, dict):
        content = resp if isinstance(resp, str) else str(resp)
        leak = "(含文本式工具调用标记!)" if _TEXT_LEAK_RE.search(content or "") else ""
        return False, f"未返回结构化 tool_calls, 而是纯文本 {leak}: {content[:160]!r}"

    tool_calls = resp.get("tool_calls") or []
    content = resp.get("content") or ""
    if not tool_calls:
        leak = "(含文本式工具调用标记!)" if _TEXT_LEAK_RE.search(content) else ""
        return False, f"dict 无 tool_calls {leak}; content={content[:160]!r}"

    tc = tool_calls[0]
    name = (tc.get("function") or {}).get("name")
    if name != _EXPECTED_TOOL:
        return False, f"tool name={name!r} 不是期望的 {_EXPECTED_TOOL!r}"

    raw_args = (tc.get("function") or {}).get("arguments")
    args_obj = raw_args
    if isinstance(raw_args, str):
        try:
            args_obj = json.loads(raw_args)
        except Exception as e:  # noqa: BLE001
            return False, f"arguments 不是合法 JSON ({e}): {raw_args[:160]!r}"
    if not isinstance(args_obj, dict):
        return False, f"arguments 不是对象: {args_obj!r}"

    if _TEXT_LEAK_RE.search(content):
        return False, f"tool_calls 结构化但 content 含泄漏标记: {content[:160]!r}"

    return True, f"OK tool={name} args={json.dumps(args_obj, ensure_ascii=False)[:120]}"


async def _run_once_parallel(model_id: str) -> tuple[bool, str]:
    """并行工具调用真网络门 (rank5): 传 parallel_tool_calls=True + 一个明确要记录**两件**事
    的 prompt, 断言一轮回 ≥2 个**干净结构化** tool_call。返回 (ok, detail)。"""
    from app.services.llm.factory import create_provider_for_model_id

    provider = create_provider_for_model_id(model_id)
    resp = await provider.chat(
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": _USER_PARALLEL}],
        model=None,
        temperature=0.0,
        max_tokens=512,
        stream=False,
        tools=_TOOLS,
        parallel_tool_calls=True,
    )
    if not isinstance(resp, dict):
        content = resp if isinstance(resp, str) else str(resp)
        leak = "(含文本式工具调用标记!)" if _TEXT_LEAK_RE.search(content or "") else ""
        return False, f"未返回结构化 tool_calls, 而是纯文本 {leak}: {content[:160]!r}"

    tool_calls = resp.get("tool_calls") or []
    content = resp.get("content") or ""
    if len(tool_calls) < 2:
        leak = "(含文本式工具调用标记!)" if _TEXT_LEAK_RE.search(content) else ""
        return False, (f"一轮只回 {len(tool_calls)} 个 tool_call (期望 ≥2 = 并行未生效或模型"
                       f"只发一个) {leak}; content={content[:160]!r}")

    for i, tc in enumerate(tool_calls):
        name = (tc.get("function") or {}).get("name")
        if name != _EXPECTED_TOOL:
            return False, f"tool_calls[{i}].name={name!r} 不是期望 {_EXPECTED_TOOL!r}"
        raw_args = (tc.get("function") or {}).get("arguments")
        args_obj = raw_args
        if isinstance(raw_args, str):
            try:
                args_obj = json.loads(raw_args)
            except Exception as e:  # noqa: BLE001
                return False, f"tool_calls[{i}].arguments 非法 JSON ({e}): {raw_args[:120]!r}"
        if not isinstance(args_obj, dict):
            return False, f"tool_calls[{i}].arguments 非对象: {args_obj!r}"
    if _TEXT_LEAK_RE.search(content):
        return False, f"tool_calls 结构化但 content 含泄漏标记: {content[:160]!r}"

    return True, f"OK 一轮并行回 {len(tool_calls)} 个干净 tool_call (全部 {_EXPECTED_TOOL})"


async def _main(model_id: str, repeat: int, parallel: bool) -> int:
    from app.services.llm.model_registry import get_model

    entry = get_model(model_id)
    if entry is None:
        print(f"[FAIL] 模型 {model_id!r} 不在注册表", file=sys.stderr)
        return 2
    mode = "并行 (parallel_tool_calls=true, 期望一轮 ≥2 call)" if parallel else "单 call"
    print(f"[info] model={model_id} speed_tier={entry.speed_tier} "
          f"reliable_tool_calling={entry.reliable_tool_calling} repeat={repeat} mode={mode}")
    if entry.speed_tier != "fast":
        print(f"[warn] {model_id} speed_tier={entry.speed_tier} 非 fast —— "
              f"agent_executor 只对 fast 档做工具轮快路由, 该模型不会被此特性选中。")

    runner = _run_once_parallel if parallel else _run_once
    ok_count = 0
    for i in range(repeat):
        try:
            ok, detail = await runner(model_id)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] 第 {i+1}/{repeat} 次 chat 抛异常: {e}", file=sys.stderr)
            return 3
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {i+1}/{repeat}: {detail}")
        ok_count += int(ok)

    what = "一轮并行 ≥2 个干净 tool_calls" if parallel else "干净结构化 tool_calls"
    print(f"\n结果: {ok_count}/{repeat} 次吐出{what}。")
    if ok_count != repeat:
        if parallel:
            print("[VERDICT] 并行不可靠 —— prod 不要开 LLM_PARALLEL_TOOL_CALLS "
                  "(该模型一轮回不稳 ≥2 call, 折叠收益拿不到)。", file=sys.stderr)
        else:
            print("[VERDICT] 不可靠 —— 上线前不要开 task_tiered_routing 的工具轮快路由 "
                  "(或把该模型 reliable_tool_calling 标 False)。", file=sys.stderr)
        return 1
    print("[VERDICT] 可靠 (本次抽样全部干净)。可作为开启前置门的证据之一。")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="快工具模型结构化 tool_calls 真网络烟测")
    ap.add_argument("--model-id", default=_DEFAULT_MODEL_ID)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--parallel", action="store_true",
                    help="并行工具调用门 (rank5): 传 parallel_tool_calls=true, 断言一轮 ≥2 call")
    ns = ap.parse_args()
    try:
        sys.exit(asyncio.run(_main(ns.model_id, ns.repeat, ns.parallel)))
    except KeyboardInterrupt:
        sys.exit(130)
