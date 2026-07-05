"""blind_pack.py —— 盲评打包:去品牌 + 乱序,answer key 单独存。

为什么盲评:judge 看到 "小巴/ChatGPT" 会有品牌偏见。打包时:
  - 每条 transcript 分配一个不透明 blind_id(如 b0001),arm 名从盲评面里剥掉。
  - 同一题的多个臂在盲评文件里打乱顺序(judge 看不出哪个是哪家)。
  - answer key(blind_id → arm)单独存一个文件,judge 跑完再用它还原归属。

确定性:给定 seed,乱序可复现(测试要能断言"打乱了且 key 能还原")。
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from evals.comparative.common import read_jsonl, write_jsonl


def make_blind_pack(
    transcripts: List[Dict[str, Any]], seed: int = 1234
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """返回 (blind_records, answer_key)。

    blind_records: 去品牌 + 组内乱序的评测面,每条含 blind_id/prompt_id/family/answer/turns。
    answer_key:    {blind_id: {arm, prompt_id, family}} —— 单独存,评完还原。
    """
    rng = random.Random(seed)
    # 按 prompt_id 分组,组内打乱臂顺序(这样同题不同臂在最终列表里也散开)
    by_prompt: Dict[str, List[Dict[str, Any]]] = {}
    for t in transcripts:
        by_prompt.setdefault(t["prompt_id"], []).append(t)

    blind_records: List[Dict[str, Any]] = []
    answer_key: Dict[str, Dict[str, Any]] = {}
    counter = 0

    # prompt_id 也按 seed 打乱输出顺序(避免题目顺序泄漏结构)
    prompt_ids = list(by_prompt.keys())
    rng.shuffle(prompt_ids)

    for pid in prompt_ids:
        group = list(by_prompt[pid])
        rng.shuffle(group)  # 组内臂乱序
        for t in group:
            counter += 1
            blind_id = f"b{counter:04d}"
            blind_records.append(
                {
                    "blind_id": blind_id,
                    "prompt_id": t["prompt_id"],
                    "family": t["family"],
                    "requires_personal_data": t.get("requires_personal_data", False),
                    "answer": t.get("answer", ""),
                    "turns": t.get("turns", []),
                    "error": t.get("error"),
                }
            )
            answer_key[blind_id] = {
                "arm": t["arm"],
                "prompt_id": t["prompt_id"],
                "family": t["family"],
                "latency_ms": t.get("latency_ms", 0),
                "cost": t.get("cost"),
            }
    return blind_records, answer_key


def restore(
    blind_records: List[Dict[str, Any]], answer_key: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """用 answer key 把盲评记录还原成带 arm 的记录(校验:blind_id 必须都在 key 里)。"""
    out: List[Dict[str, Any]] = []
    for r in blind_records:
        bid = r["blind_id"]
        if bid not in answer_key:
            raise KeyError(f"blind_id {bid} 不在 answer key 中,无法还原")
        merged = dict(r)
        merged.update(answer_key[bid])
        out.append(merged)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="blind_pack", description="盲评打包(去品牌+乱序)")
    ap.add_argument("--transcripts", default="transcripts.jsonl")
    ap.add_argument("--blind-out", default="blind.jsonl", help="盲评面(喂 judge)")
    ap.add_argument("--key-out", default="answer_key.json", help="answer key(单独存)")
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args(argv)

    transcripts = read_jsonl(Path(args.transcripts))
    blind, key = make_blind_pack(transcripts, seed=args.seed)
    write_jsonl(Path(args.blind_out), blind)
    Path(args.key_out).write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[blind_pack] {len(blind)} 条盲评记录 → {args.blind_out};key → {args.key_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
