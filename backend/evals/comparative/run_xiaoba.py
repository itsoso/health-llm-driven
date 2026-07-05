"""run_xiaoba.py —— 对部署的小巴 (Reva) API 自动跑全题库。

臂: xiaoba。走 POST /agent/send(非流式简单)。
- 采集: 回答文本 + 延迟 + meta(conversation_id / mode / elapsed_ms;model/cost 若响应带则收)。
- multi_turn: 同一 conversation_id 串起首问 + follow_ups,测记忆连续性。
- 只读评测: 题库本身无"记录"意图。跑完做 sanity 检查 —— 抓评测窗口前后的
  记录计数(饮水/饮食/体重等),若新增则告警(评测不该写库)。

环境:
  REVA_EVAL_BASE   默认 https://health.executor.life/api/v1
  REVA_EVAL_TOKEN  必填(env,绝不入库)

用法:
  REVA_EVAL_TOKEN=... python -m evals.comparative.run_xiaoba --out transcripts_xiaoba.jsonl
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from evals.comparative.battery import Battery, load_battery
from evals.comparative.common import (
    Transcript,
    Turn,
    bearer_headers,
    eval_base,
    http_get_json,
    http_post_json,
    write_jsonl,
)

ARM = "xiaoba"

# poster 签名: (message, conversation_id) -> dict(至少含 reply;可含 conversation_id/elapsed_ms/mode/usage)
Poster = Callable[[str, Optional[int]], Dict[str, Any]]


def real_poster(base: Optional[str] = None, throttle_s: float = 3.5) -> Poster:
    """真 HTTP poster。带节流:/agent/send 有 3s 同 message 去重窗,轮次间 sleep 避免撞。"""
    base = (base or eval_base()).rstrip("/")
    url = f"{base}/agent/send"
    headers = bearer_headers()
    last_call = {"t": 0.0}

    def _post(message: str, conversation_id: Optional[int]) -> Dict[str, Any]:
        wait = throttle_s - (time.monotonic() - last_call["t"])
        if wait > 0:
            time.sleep(wait)
        payload: Dict[str, Any] = {"message": message, "channel": "typed"}
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        resp = http_post_json(url, payload, headers=headers, timeout=120)
        last_call["t"] = time.monotonic()
        return resp

    return _post


def _run_one(q, poster: Poster) -> Transcript:
    """跑单题(含多轮)。每轮复用上一轮返回的 conversation_id。"""
    turns: List[Turn] = []
    conv_id: Optional[int] = None
    answers: List[str] = []
    meta: Dict[str, Any] = {}
    try:
        for prompt in q.turns():
            t0 = time.monotonic()
            resp = poster(prompt, conv_id)
            latency_ms = int((time.monotonic() - t0) * 1000)
            reply = str(resp.get("reply", ""))
            conv_id = resp.get("conversation_id", conv_id)
            turn_meta = {
                "conversation_id": resp.get("conversation_id"),
                "mode": resp.get("mode"),
                "elapsed_ms": resp.get("elapsed_ms"),
            }
            usage = resp.get("usage") or resp.get("llm_usage")
            if isinstance(usage, dict):
                turn_meta["usage"] = usage
            turns.append(Turn(prompt=prompt, answer=reply, latency_ms=latency_ms, meta=turn_meta))
            answers.append(reply)
        meta["conversation_id"] = conv_id
        # 多轮时把每轮 elapsed_ms 之和留档
        meta["model"] = None  # 小巴不回传具体 model 名;留位以对齐其他臂 schema
        combined = "\n\n---\n\n".join(answers) if len(answers) > 1 else (answers[0] if answers else "")
        return Transcript(
            arm=ARM,
            prompt_id=q.id,
            family=q.family,
            answer=combined,
            latency_ms=sum(t.latency_ms for t in turns),
            cost=None,
            requires_personal_data=q.requires_personal_data,
            turns=[t.__dict__ for t in turns],
            meta=meta,
        )
    except Exception as e:  # noqa: BLE001 — 单题失败不吞:记 error 字段,继续跑其余题,报告可见
        return Transcript(
            arm=ARM,
            prompt_id=q.id,
            family=q.family,
            answer="".join(a for a in answers),
            latency_ms=sum(t.latency_ms for t in turns),
            requires_personal_data=q.requires_personal_data,
            turns=[t.__dict__ for t in turns],
            meta=meta,
            error=f"{type(e).__name__}: {e}",
        )


def run_battery(battery: Battery, poster: Poster) -> List[Transcript]:
    """跑全题库,返回 transcript 列表。纯函数(poster 注入),测试可 mock。"""
    return [_run_one(q, poster) for q in battery.questions]


def _record_counts(base: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """尽力抓一个 twin 快照做写库 sanity 对比(不是精确记录数,取几个易变计数)。

    只读:失败不抛(sanity 检查本身不应挡评测),返回 error 标记。
    """
    try:
        twin = http_get_json(f"{base}/twin/me", headers=headers, timeout=60)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    beh = twin.get("behavioral") or {}
    return {
        "water_ml_today": beh.get("water_ml_today"),
        "diet_entries_today": beh.get("diet_entries_today") or beh.get("meals_today"),
        "freshness": (twin.get("freshness") or {}),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="run_xiaoba", description="小巴臂自动跑题库(只读评测)")
    ap.add_argument("--out", default="transcripts_xiaoba.jsonl", help="输出 JSONL 路径")
    ap.add_argument("--battery", default=None, help="题库路径(默认内置 battery.yaml)")
    ap.add_argument("--no-sanity", action="store_true", help="跳过写库 sanity 检查")
    args = ap.parse_args(argv)

    battery = load_battery(Path(args.battery) if args.battery else None)
    base = eval_base()
    headers = bearer_headers()

    before = None if args.no_sanity else _record_counts(base, headers)

    poster = real_poster(base)
    transcripts = run_battery(battery, poster)

    out = write_jsonl(Path(args.out), [t.to_json() for t in transcripts])

    errs = [t for t in transcripts if t.error]
    print(f"[xiaoba] {len(transcripts)} 题跑完 → {out}", file=sys.stderr)
    if errs:
        print(f"[xiaoba] {len(errs)} 题出错: {[t.prompt_id for t in errs]}", file=sys.stderr)

    if not args.no_sanity:
        after = _record_counts(base, headers)
        _sanity_warn(before, after)

    return 1 if errs else 0


def _sanity_warn(before: Optional[Dict[str, Any]], after: Dict[str, Any]) -> None:
    """比对评测前后计数,若疑似写库则显式告警(评测应只读)。"""
    if not before or "error" in before or "error" in after:
        print("[xiaoba] sanity: twin 快照不可用,跳过写库检查", file=sys.stderr)
        return
    changed = []
    for k in ("water_ml_today", "diet_entries_today"):
        if before.get(k) != after.get(k):
            changed.append((k, before.get(k), after.get(k)))
    if changed:
        print(
            f"[xiaoba] ⚠ SANITY: 评测窗口内计数变化 {changed} —— 评测本应只读,请核查题库是否误触发写库!",
            file=sys.stderr,
        )
    else:
        print("[xiaoba] sanity: 未见记录计数变化(只读评测符合预期)", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
