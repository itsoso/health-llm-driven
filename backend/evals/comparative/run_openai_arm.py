"""run_openai_arm.py —— 商用模型臂(两臂:bare / with_context)。

- bare:        直接把题目发给商用模型(无个人数据)。
- with_context:context_pack.md 前置为 system,再发题目(粘贴数据臂)。

模型走 backend 既有 provider 配置可达的商用模型:读 env OPENAI_API_KEY / OPENAI_BASE_URL
(与 backend openai-proxy 一致),打 OpenAI 兼容 /chat/completions。模型名参数化。
采集回答 + 延迟 + token 用量 + 成本(按 --price-in/--price-out 每百万 token 计价)。

multi_turn:同一 messages 列表累积上下文(bare 无个人数据,with_context 前置 system pack)。

环境:
  OPENAI_API_KEY   必填(env)
  OPENAI_BASE_URL  可选,默认 https://api.openai.com/v1

用法:
  OPENAI_API_KEY=... python -m evals.comparative.run_openai_arm \
      --arm bare --model gpt-4o-mini --out transcripts_chatgpt_bare.jsonl
  OPENAI_API_KEY=... python -m evals.comparative.run_openai_arm \
      --arm with_context --model gpt-4o-mini --context context_pack.md \
      --out transcripts_chatgpt_context.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from evals.comparative.battery import Battery, load_battery
from evals.comparative.common import Transcript, Turn, http_post_json, write_jsonl

ARM_BARE = "chatgpt_bare"
ARM_CONTEXT = "chatgpt_context"

# chat 签名: (messages) -> dict(choices/usage 的 OpenAI 兼容响应)
ChatFn = Callable[[List[Dict[str, str]]], Dict[str, Any]]


def openai_base() -> str:
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def openai_key() -> str:
    k = os.environ.get("OPENAI_API_KEY", "").strip()
    if not k:
        raise RuntimeError("缺 OPENAI_API_KEY 环境变量(评测 key 走 env,绝不入库)。")
    return k


def real_chat(model: str, base: Optional[str] = None, temperature: float = 0.3) -> ChatFn:
    base = (base or openai_base()).rstrip("/")
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {openai_key()}"}

    def _chat(messages: List[Dict[str, str]]) -> Dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1200,
        }
        return http_post_json(url, payload, headers=headers, timeout=120)

    return _chat


def _extract(resp: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """从 OpenAI 兼容响应取 (text, usage)。缺字段时不假装成功。"""
    choices = resp.get("choices")
    if not choices:
        raise RuntimeError(f"响应无 choices: {str(resp)[:200]}")
    text = choices[0].get("message", {}).get("content", "")
    usage = resp.get("usage") or {}
    return str(text), usage


def _cost(usage: Dict[str, Any], price_in: float, price_out: float) -> Optional[float]:
    """按每百万 token 单价计费。usage 缺失返回 None。"""
    pt = usage.get("prompt_tokens")
    ct = usage.get("completion_tokens")
    if pt is None or ct is None:
        return None
    return round(pt / 1e6 * price_in + ct / 1e6 * price_out, 6)


def _run_one(
    q,
    chat: ChatFn,
    arm: str,
    model: str,
    system_context: Optional[str],
    price_in: float,
    price_out: float,
) -> Transcript:
    messages: List[Dict[str, str]] = []
    if system_context:
        messages.append({"role": "system", "content": system_context})
    turns: List[Turn] = []
    answers: List[str] = []
    total_pt = total_ct = 0
    total_cost = 0.0
    cost_seen = False
    try:
        for prompt in q.turns():
            messages.append({"role": "user", "content": prompt})
            t0 = time.monotonic()
            resp = chat(messages)
            latency_ms = int((time.monotonic() - t0) * 1000)
            text, usage = _extract(resp)
            messages.append({"role": "assistant", "content": text})
            answers.append(text)
            c = _cost(usage, price_in, price_out)
            if c is not None:
                total_cost += c
                cost_seen = True
            total_pt += int(usage.get("prompt_tokens") or 0)
            total_ct += int(usage.get("completion_tokens") or 0)
            turns.append(
                Turn(
                    prompt=prompt,
                    answer=text,
                    latency_ms=latency_ms,
                    meta={"usage": usage, "model": resp.get("model", model)},
                )
            )
        combined = "\n\n---\n\n".join(answers) if len(answers) > 1 else (answers[0] if answers else "")
        return Transcript(
            arm=arm,
            prompt_id=q.id,
            family=q.family,
            answer=combined,
            latency_ms=sum(t.latency_ms for t in turns),
            cost=round(total_cost, 6) if cost_seen else None,
            requires_personal_data=q.requires_personal_data,
            turns=[t.__dict__ for t in turns],
            meta={"model": model, "prompt_tokens": total_pt, "completion_tokens": total_ct},
        )
    except Exception as e:  # noqa: BLE001 — 单题失败记 error,继续
        return Transcript(
            arm=arm,
            prompt_id=q.id,
            family=q.family,
            answer="".join(answers),
            latency_ms=sum(t.latency_ms for t in turns),
            requires_personal_data=q.requires_personal_data,
            turns=[t.__dict__ for t in turns],
            meta={"model": model},
            error=f"{type(e).__name__}: {e}",
        )


def run_battery(
    battery: Battery,
    chat: ChatFn,
    arm: str,
    model: str,
    system_context: Optional[str] = None,
    price_in: float = 0.0,
    price_out: float = 0.0,
) -> List[Transcript]:
    """跑全题库,纯函数(chat 注入)。"""
    return [
        _run_one(q, chat, arm, model, system_context, price_in, price_out)
        for q in battery.questions
    ]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="run_openai_arm", description="商用模型臂(bare/with_context)")
    ap.add_argument("--arm", required=True, choices=["bare", "with_context"])
    ap.add_argument("--model", required=True, help="模型名,如 gpt-4o-mini")
    ap.add_argument("--context", default=None, help="with_context 臂的 context_pack.md 路径")
    ap.add_argument("--out", required=True, help="输出 JSONL 路径")
    ap.add_argument("--battery", default=None)
    ap.add_argument("--price-in", type=float, default=0.0, help="输入每百万 token USD 单价")
    ap.add_argument("--price-out", type=float, default=0.0, help="输出每百万 token USD 单价")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument(
        "--arm-name",
        default=None,
        help="臂标签覆盖(默认 chatgpt_bare/chatgpt_context;跑国产模型对照臂时必传,如 qwen_max_bare)",
    )
    args = ap.parse_args(argv)

    arm = args.arm_name or (ARM_BARE if args.arm == "bare" else ARM_CONTEXT)
    system_context: Optional[str] = None
    if args.arm == "with_context":
        if not args.context:
            print("[openai_arm] with_context 臂必须 --context context_pack.md", file=sys.stderr)
            return 2
        cp = Path(args.context)
        if not cp.exists():
            print(f"[openai_arm] context 文件不存在: {cp}", file=sys.stderr)
            return 2
        system_context = (
            "以下是该用户的个人健康数据背景。回答其健康问题时优先引用这些真实数据,"
            "不要编造数据中没有的数值;涉及用药/停药/剂量须让用户咨询医生。\n\n"
            + cp.read_text(encoding="utf-8")
        )

    battery = load_battery(Path(args.battery) if args.battery else None)
    chat = real_chat(args.model, temperature=args.temperature)
    transcripts = run_battery(
        battery, chat, arm, args.model, system_context, args.price_in, args.price_out
    )
    out = write_jsonl(Path(args.out), [t.to_json() for t in transcripts])
    errs = [t for t in transcripts if t.error]
    print(f"[openai_arm:{arm}] {len(transcripts)} 题 → {out}", file=sys.stderr)
    if errs:
        print(f"[openai_arm:{arm}] {len(errs)} 题出错: {[t.prompt_id for t in errs]}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
