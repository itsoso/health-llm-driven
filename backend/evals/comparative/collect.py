"""collect.py —— 把所有臂合并成 transcripts.jsonl。

两类输入:
  1. 自动臂 JSONL:run_xiaoba / run_openai_arm 直接产出的 transcripts_*.jsonl。
  2. 手工臂 markdown:manual_*.md(按 manual_arm_template.md 格式填的),解析成 transcript。

输出统一 schema(与 common.Transcript 一致):
  {arm, prompt_id, family, answer, latency_ms, cost, requires_personal_data, turns, meta, error}

fail-loud:手工模板 arm 未替换 / QID 不在题库 / 重复 (arm, prompt_id) → 抛。
空回答的手工题:跳过并告警(算该臂缺该题,不静默塞空串当已答)。

用法:
  python -m evals.comparative.collect --out transcripts.jsonl \
      --jsonl transcripts_xiaoba.jsonl transcripts_chatgpt_bare.jsonl \
      --manual manual_afu.md manual_lbclaw.md
  # 或让它自动扫当前目录:
  python -m evals.comparative.collect --out transcripts.jsonl --auto
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from evals.comparative.battery import Battery, load_battery
from evals.comparative.common import read_jsonl, write_jsonl

_ARM_RE = re.compile(r"^arm:\s*(\S+)\s*$", re.MULTILINE)
_QID_RE = re.compile(r"^###\s+QID:\s*(\S+)\s*$", re.MULTILINE)


def _split_blocks(text: str) -> List[tuple[str, str]]:
    """按 `### QID: xxx` 切块,返回 [(qid, block_body), ...]。"""
    matches = list(_QID_RE.finditer(text))
    blocks: List[tuple[str, str]] = []
    for i, m in enumerate(matches):
        qid = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((qid, text[start:end]))
    return blocks


def _parse_answer_blocks(body: str) -> List[str]:
    """提取 body 里所有 ```answer ... ``` 的内容(按出现顺序:首问,followup1, ...)。"""
    return [m.strip() for m in re.findall(r"```answer\s*\n(.*?)```", body, re.DOTALL)]


def _parse_latencies(body: str) -> List[int]:
    """提取所有 LATENCY_MS: n(顺序对应各 answer 块)。"""
    out: List[int] = []
    for m in re.findall(r"LATENCY_MS:\s*(\d+)", body):
        out.append(int(m))
    return out


def parse_manual(text: str, battery: Battery) -> List[Dict[str, Any]]:
    """解析一份手工臂 markdown → transcript dict 列表。"""
    arm_m = _ARM_RE.search(text)
    if not arm_m:
        raise ValueError("手工模板缺 `arm: <name>` 行")
    arm = arm_m.group(1)
    if arm.upper() == "REPLACE_ME":
        raise ValueError("手工模板 arm 仍是占位符 REPLACE_ME,请替换为真实臂名")

    rows: List[Dict[str, Any]] = []
    for qid, body in _split_blocks(text):
        try:
            q = battery.by_id(qid)
        except KeyError as e:
            raise ValueError(f"手工模板含题库中不存在的 QID: {qid}") from e
        answers = _parse_answer_blocks(body)
        latencies = _parse_latencies(body)
        expected_turns = len(q.turns())
        # 空题(所有 answer 块空)跳过并告警
        non_empty = [a for a in answers if a.strip()]
        if not non_empty:
            print(f"[collect] ⚠ 手工臂 {arm} 题 {qid} 无回答,跳过", file=sys.stderr)
            continue
        if len(answers) < expected_turns:
            print(
                f"[collect] ⚠ 手工臂 {arm} 题 {qid} 只填了 {len(answers)}/{expected_turns} 轮",
                file=sys.stderr,
            )
        turns = []
        for idx, prompt in enumerate(q.turns()):
            ans = answers[idx] if idx < len(answers) else ""
            lat = latencies[idx] if idx < len(latencies) else 0
            turns.append({"prompt": prompt, "answer": ans, "latency_ms": lat, "meta": {}})
        combined = "\n\n---\n\n".join(a["answer"] for a in turns if a["answer"].strip())
        rows.append(
            {
                "arm": arm,
                "prompt_id": qid,
                "family": q.family,
                "answer": combined,
                "latency_ms": sum(t["latency_ms"] for t in turns),
                "cost": _parse_cost(body),
                "requires_personal_data": q.requires_personal_data,
                "turns": turns,
                "meta": {"source": "manual"},
                "error": None,
            }
        )
    return rows


def _parse_cost(body: str) -> Optional[float]:
    m = re.search(r"COST_USD:\s*([0-9.]+)", body)
    return float(m.group(1)) if m else None


def merge(
    jsonl_paths: List[Path], manual_paths: List[Path], battery: Battery
) -> List[Dict[str, Any]]:
    """合并所有来源,去重 (arm, prompt_id)(重复=fail-loud)。"""
    rows: List[Dict[str, Any]] = []
    for p in jsonl_paths:
        rows.extend(read_jsonl(p))
    for p in manual_paths:
        rows.extend(parse_manual(Path(p).read_text(encoding="utf-8"), battery))

    seen: set[tuple[str, str]] = set()
    for r in rows:
        key = (r.get("arm"), r.get("prompt_id"))
        if None in key:
            raise ValueError(f"transcript 缺 arm/prompt_id: {r}")
        if key in seen:
            raise ValueError(f"重复 (arm, prompt_id): {key} —— 同一臂同一题出现两次")
        seen.add(key)
    return rows


def _auto_discover(cwd: Path) -> tuple[List[Path], List[Path]]:
    jsonl = sorted(cwd.glob("transcripts_*.jsonl"))
    manual = sorted(cwd.glob("manual_*.md"))
    # 排除模板本身
    manual = [m for m in manual if m.name != "manual_arm_template.md"]
    return jsonl, manual


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="collect", description="合并各臂 transcript")
    ap.add_argument("--out", default="transcripts.jsonl")
    ap.add_argument("--jsonl", nargs="*", default=[], help="自动臂 JSONL 文件")
    ap.add_argument("--manual", nargs="*", default=[], help="手工臂 markdown 文件")
    ap.add_argument("--auto", action="store_true", help="自动扫 --dir(默认 cwd)下 transcripts_*.jsonl + manual_*.md")
    ap.add_argument("--dir", default=None, help="--auto 扫描的目录(默认当前目录);从 backend/ 跑时指到 out/")
    ap.add_argument("--battery", default=None)
    args = ap.parse_args(argv)

    battery = load_battery(Path(args.battery) if args.battery else None)
    jsonl = [Path(p) for p in args.jsonl]
    manual = [Path(p) for p in args.manual]
    if args.auto:
        scan_dir = Path(args.dir) if args.dir else Path.cwd()
        aj, am = _auto_discover(scan_dir)
        jsonl += aj
        manual += am
    if not jsonl and not manual:
        print("[collect] 无输入(既没 --jsonl/--manual 也没命中 --auto)", file=sys.stderr)
        return 2

    rows = merge(jsonl, manual, battery)
    out = write_jsonl(Path(args.out), rows)
    arms = sorted({r["arm"] for r in rows})
    print(f"[collect] 合并 {len(rows)} 条 transcript,臂={arms} → {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
