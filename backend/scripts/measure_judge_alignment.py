#!/usr/bin/env python3
"""critique-shadowing 对齐度量(Hamel)—— 不变量 judge 与 founder 金标的一致率。

judge(确定性层 + 可选 LLM 层)对 eval/datasets/invariants.yaml 的每条裁 pass/fail,
与 founder 标签(expected.should_pass)比,算混淆矩阵 + precision/recall/agreement。
目标:对齐 >90%(低于阈值 → 退出非零,可当回归闸 / 迭代 rubric 的信号)。

用法:
  python scripts/measure_judge_alignment.py                 # 纯确定性层(离线,CI 友好)
  python scripts/measure_judge_alignment.py --with-llm      # 加 LLM-judge 层(细微不变量)
  python scripts/measure_judge_alignment.py --threshold 0.9 --json

扩展(scale-out):founder 在产品里用 user_judgment_feedback 标的 👎 合成,
脱敏后回流进 invariants.yaml 当更多金标 —— 见 --feedback(占位,需 audit-log 关联文本)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def compute_alignment(with_llm: bool = False) -> dict:
    import yaml

    from eval.scorers.invariant_judge import score_invariant_judge

    cases = yaml.safe_load((ROOT / "eval" / "datasets" / "invariants.yaml").read_text(encoding="utf-8"))["cases"]
    tp = fp = tn = fn = 0  # 以"判 FAIL(有违反)"为正类
    rows = []
    for c in cases:
        exp_pass = bool(c["expected"].get("should_pass", True))
        expected = dict(c["expected"])
        if not with_llm:
            expected["invariants_deterministic_only"] = True
        r = score_invariant_judge(c.get("query", ""), c.get("answer", ""), expected)
        judge_pass = r["passed"]
        aligned = (judge_pass == exp_pass)
        # 正类 = 应 FAIL(违反)
        if not exp_pass and not judge_pass:
            tp += 1
        elif exp_pass and not judge_pass:
            fp += 1
        elif exp_pass and judge_pass:
            tn += 1
        else:  # not exp_pass and judge_pass = 漏判违反(under-alarm)
            fn += 1
        rows.append({"id": c["id"], "expected_pass": exp_pass, "judge_pass": judge_pass,
                     "aligned": aligned, "violations": r["violations"]})

    n = len(cases)
    agreement = sum(1 for x in rows if x["aligned"]) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "n": n, "agreement": round(agreement, 3),
        "precision_on_violations": round(precision, 3) if precision is not None else None,
        "recall_on_violations": round(recall, 3) if recall is not None else None,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "misaligned": [x for x in rows if not x["aligned"]],
        "with_llm": with_llm,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true", help="加 LLM-judge 层(默认纯确定性)")
    ap.add_argument("--threshold", type=float, default=0.9, help="一致率阈值,低于即退出非零")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args()

    m = compute_alignment(with_llm=args.with_llm)
    if args.as_json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    else:
        print(f"judge↔founder 对齐 ({'确定性+LLM' if args.with_llm else '纯确定性'}层):")
        print(f"  一致率 agreement = {m['agreement']*100:.1f}% (n={m['n']})")
        print(f"  违反检出 precision = {m['precision_on_violations']}  recall = {m['recall_on_violations']}")
        print(f"  混淆 tp(抓到违反)={m['confusion']['tp']} fp(误判好为坏)={m['confusion']['fp']} "
              f"tn={m['confusion']['tn']} fn(漏判违反=under-alarm)={m['confusion']['fn']}")
        if m["misaligned"]:
            print("  ⚠️ 失配(judge 漂移出 founder 标准,迭代 rubric):")
            for x in m["misaligned"]:
                print(f"    - {x['id']}: expected_pass={x['expected_pass']} judge_pass={x['judge_pass']} {x['violations']}")
    return 0 if m["agreement"] >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
