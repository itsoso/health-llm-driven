"""R0 · prompt 分解测量 — 14k prefill 的按 block 构成(R1 compaction / R5 渐进披露的靶子)。

静态可测部分直接量(工具 schema 逐个 + 意图门控块);动态部分(Twin blob/记忆/历史)
依赖用户数据,给出解剖口径 + 已有生产实测参照。零网络零 DB,CI/本地随时跑。

用法:
    python scripts/measure_prompt_anatomy.py            # 表格输出
    python scripts/measure_prompt_anatomy.py --json     # 机器可读(接 telemetry 对比)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _tok(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 3)  # 中文近似兜底


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from app.services.tool_schema_registry import FAST_TURN_TOOL_NAMES, get_health_tools
    from app.services import agent_executor as ae

    full_tools = get_health_tools()
    fast_tools = get_health_tools(subset=list(FAST_TURN_TOOL_NAMES))

    per_tool = sorted(
        (
            {
                "tool": t["function"]["name"],
                "tokens": _tok(json.dumps(t, ensure_ascii=False)),
                "in_fast_subset": t["function"]["name"] in FAST_TURN_TOOL_NAMES,
            }
            for t in full_tools
        ),
        key=lambda x: -x["tokens"],
    )
    full_total = sum(x["tokens"] for x in per_tool)
    fast_total = _tok(json.dumps(fast_tools, ensure_ascii=False))

    gene_block = "".join(ae._GENE_RULES_PROMPT_BLOCK)
    menu_block = "".join(ae._MENU_SHARE_PROMPT_BLOCK)

    report = {
        "static": {
            "tool_schema_full_tokens": full_total,
            "tool_schema_fast_subset_tokens": fast_total,
            "tool_count": len(per_tool),
            "per_tool": per_tool,
            "gene_rules_block_tokens": _tok(gene_block),
            "menu_share_block_tokens": _tok(menu_block),
        },
        # 动态块无法离线量(依赖用户数据);解剖口径 + 生产实测参照(token 战役 2026-07):
        "dynamic_reference": {
            "history_15msg_chars": 10290,
            "system_prompt_total_chars": 5461,
            "system_static_skeleton_chars": 4233,
            "note": "动态实测走 llm_usage_logs(prompt_tokens/cached_tokens, token_source=api)",
        },
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    s = report["static"]
    print(f"工具 schema(全量 {s['tool_count']} 个): {s['tool_schema_full_tokens']:,} tokens")
    print(f"工具 schema(fast 子集 {len(FAST_TURN_TOOL_NAMES)} 个): {s['tool_schema_fast_subset_tokens']:,} tokens")
    print(f"意图门控块: gene={s['gene_rules_block_tokens']} menu={s['menu_share_block_tokens']}")
    print("\n最肥的 8 个工具(R5 渐进披露的裁剪靶):")
    for x in s["per_tool"][:8]:
        tag = " [fast]" if x["in_fast_subset"] else ""
        print(f"  {x['tokens']:>6,}  {x['tool']}{tag}")
    d = report["dynamic_reference"]
    print(f"\n动态块参照(生产实测): 历史15条≈{d['history_15msg_chars']:,}c "
          f"系统prompt≈{d['system_prompt_total_chars']:,}c(骨架 {d['system_static_skeleton_chars']:,}c)")
    print("动态真值查 llm_usage_logs(token_source=api)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
