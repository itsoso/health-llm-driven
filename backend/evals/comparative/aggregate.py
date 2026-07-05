"""aggregate.py —— 汇总 judge 打分,出 report.md。

输入:scores.jsonl(judge 产出;若已 restore 则每条带 arm,否则需 --key 还原)。
输出 report.md:
  1. 总表:每臂 × 五维均分 + overall + 平均延迟 + 总成本 + 安全违规数。
  2. 分家族表:每臂在六家族上的 overall 均分(看数据管线臂在 state_read/root_cause 上的增益)。
  3. 安全违规清单:所有 flags 含 safety_violation / fabrication 的记录逐条列出(arm + 题 + 理由)。

命题验证提示写进报告:对比 chatgpt_bare vs chatgpt_context vs xiaoba 在
personalization / state_read 家族上的差,量化"数据管线"带来的增益。
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from evals.comparative.battery import load_battery
from evals.comparative.common import read_jsonl
from evals.comparative.judge import SCORED_DIMS

_VIOLATION_FLAGS = ("safety_violation", "fabrication")


def _mean(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 3) if xs else None


def _violation_flags(record: Dict[str, Any]) -> List[str]:
    """返回该记录里命中的违规 flag(前缀匹配 safety_violation / fabrication)。"""
    return [f for f in record.get("flags", []) if any(f.startswith(v) for v in _VIOLATION_FLAGS)]


def _has_violation(record: Dict[str, Any]) -> bool:
    return bool(_violation_flags(record))


def aggregate(scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按 arm 聚合。scores 每条须带 arm(judge --key 还原后)。"""
    by_arm: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in scores:
        arm = s.get("arm")
        if not arm:
            raise ValueError(
                f"score 记录缺 arm(prompt_id={s.get('prompt_id')})。"
                "judge 时请带 --key 还原,或 aggregate --key。"
            )
        by_arm[arm].append(s)

    arm_summary: Dict[str, Any] = {}
    for arm, rows in by_arm.items():
        dim_means = {}
        for dim in SCORED_DIMS:
            dim_means[dim] = _mean([r["dimensions"].get(dim, {}).get("score") for r in rows if r.get("dimensions")])
        overalls = [r.get("overall") for r in rows]
        latencies = [r.get("latency_ms") for r in rows]
        costs = [r.get("cost") for r in rows if r.get("cost") is not None]
        violations = [r for r in rows if _has_violation(r)]
        arm_summary[arm] = {
            "n": len(rows),
            "dims": dim_means,
            "overall": _mean(overalls),
            "avg_latency_ms": _mean(latencies),
            "total_cost": round(sum(costs), 6) if costs else None,
            "violations": len(violations),
        }

    # 分家族:arm × family → overall 均分
    fam_table: Dict[str, Dict[str, Optional[float]]] = defaultdict(dict)
    for arm, rows in by_arm.items():
        by_fam: Dict[str, List[float]] = defaultdict(list)
        for r in rows:
            if r.get("overall") is not None:
                by_fam[r["family"]].append(r["overall"])
        for fam, vals in by_fam.items():
            fam_table[arm][fam] = _mean(vals)

    # 违规清单
    violation_list: List[Dict[str, Any]] = []
    for arm, rows in by_arm.items():
        for r in rows:
            hit = _violation_flags(r)
            if hit:
                reasons = "; ".join(
                    f"{d}:{r['dimensions'][d]['reason']}"
                    for d in ("safety", "honesty", "factual")
                    if r.get("dimensions", {}).get(d)
                )
                violation_list.append(
                    {"arm": arm, "prompt_id": r["prompt_id"], "family": r["family"], "flags": hit, "reason": reasons}
                )

    return {"arms": arm_summary, "families": dict(fam_table), "violations": violation_list}


def _fmt(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.2f}"


def render_report(agg: Dict[str, Any], battery_families: List[str]) -> str:
    arms = agg["arms"]
    lines: List[str] = ["# 对比评测报告 — 小巴 vs ChatGPT/阿福/lbclaw", ""]
    lines.append("> 命题:「数据管线 + 平价模型」能否在个体化健康问答上胜过裸的大模型。")
    lines.append("> 对照重点:chatgpt_bare(裸) vs chatgpt_context(粘数据) vs xiaoba(全管线),")
    lines.append("> 看 personalization 维与 state_read/root_cause 家族上的增益。")
    lines.append("")

    # 1. 总表
    lines.append("## 1. 总表(五维均分 + overall + 延迟/成本 + 安全违规)")
    lines.append("")
    header = "| 臂 | n | " + " | ".join(SCORED_DIMS) + " | overall | 均延迟ms | 总成本$ | 违规 |"
    sep = "|" + "---|" * (len(SCORED_DIMS) + 6)
    lines.append(header)
    lines.append(sep)
    # 按 overall 降序
    for arm in sorted(arms, key=lambda a: (arms[a]["overall"] or 0), reverse=True):
        s = arms[arm]
        dims = " | ".join(_fmt(s["dims"].get(d)) for d in SCORED_DIMS)
        cost = "—" if s["total_cost"] is None else f"{s['total_cost']:.4f}"
        lat = "—" if s["avg_latency_ms"] is None else f"{s['avg_latency_ms']:.0f}"
        lines.append(
            f"| {arm} | {s['n']} | {dims} | {_fmt(s['overall'])} | {lat} | {cost} | {s['violations']} |"
        )
    lines.append("")

    # 2. 分家族
    lines.append("## 2. 分家族 overall 均分")
    lines.append("")
    fams = battery_families
    fam_header = "| 臂 | " + " | ".join(fams) + " |"
    fam_sep = "|" + "---|" * (len(fams) + 1)
    lines.append(fam_header)
    lines.append(fam_sep)
    for arm in sorted(agg["families"]):
        row = agg["families"][arm]
        cells = " | ".join(_fmt(row.get(f)) for f in fams)
        lines.append(f"| {arm} | {cells} |")
    lines.append("")

    # 3. 安全违规清单
    lines.append("## 3. 安全违规清单(safety_violation / fabrication)")
    lines.append("")
    if not agg["violations"]:
        lines.append("_无 —— 所有臂在安全边界与诚实度上均未触发硬违规。_")
    else:
        lines.append("| 臂 | 题 | 家族 | flags | 理由 |")
        lines.append("|---|---|---|---|---|")
        for v in agg["violations"]:
            lines.append(
                f"| {v['arm']} | {v['prompt_id']} | {v['family']} | {','.join(v['flags'])} | {v['reason']} |"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="aggregate", description="汇总打分出 report.md")
    ap.add_argument("--scores", default="scores.jsonl")
    ap.add_argument("--key", default=None, help="answer_key.json(scores 未带 arm 时用它还原)")
    ap.add_argument("--out", default="report.md")
    ap.add_argument("--battery", default=None)
    args = ap.parse_args(argv)

    battery = load_battery(Path(args.battery) if args.battery else None)
    scores = read_jsonl(Path(args.scores))
    if args.key:
        key = json.loads(Path(args.key).read_text(encoding="utf-8"))
        for s in scores:
            bid = s.get("blind_id")
            if bid and bid in key and not s.get("arm"):
                s.update({k: key[bid][k] for k in ("arm", "latency_ms", "cost") if k in key[bid]})

    agg = aggregate(scores)
    families = ["fact", "state_read", "safety_refusal", "root_cause", "honesty", "multi_turn"]
    report = render_report(agg, families)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"[aggregate] report → {args.out}")
    print(f"[aggregate] 臂={sorted(agg['arms'])};安全违规={len(agg['violations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
