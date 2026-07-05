"""export_context_pack.py —— 拉 GET /twin/me,组装「个人数据上下文包」文本。

用途:喂给「商用模型 + 粘贴数据」臂(chatgpt_context)的材料。
优先复用 backend 的 twin formatter(twin_to_prompt_blob)保证与线上 prompt 一致;
若 twin JSON 与 schema 漂移导致 model_validate 失败,回退到手工按分区格式化(fail-loud 标注回退)。

环境:
  REVA_EVAL_BASE   默认 https://health.executor.life/api/v1
  REVA_EVAL_TOKEN  必填(env)

用法:
  REVA_EVAL_TOKEN=... python -m evals.comparative.export_context_pack --out context_pack.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from evals.comparative.common import bearer_headers, eval_base, http_get_json


def fetch_twin(base: Optional[str] = None) -> Dict[str, Any]:
    base = (base or eval_base()).rstrip("/")
    return http_get_json(f"{base}/twin/me?fresh=true", headers=bearer_headers(), timeout=90)


def _blob_via_formatter(twin_json: Dict[str, Any]) -> Optional[str]:
    """尝试用 backend formatter。schema 漂移则返回 None(调用方回退手工)。"""
    try:
        from app.twin.schema import HealthTwin
        from app.twin.formatter import twin_to_prompt_blob

        twin = HealthTwin.model_validate(twin_json)
        return twin_to_prompt_blob(twin)
    except Exception as e:  # noqa: BLE001 — 不静默:打到 stderr,回退手工格式化
        print(f"[context_pack] formatter 复用失败(schema 漂移?),回退手工格式化: {e}", file=sys.stderr)
        return None


def _manual_blob(twin_json: Dict[str, Any]) -> str:
    """手工按 twin JSON 分区格式化(formatter 不可用时的回退)。只输出有数据的分区。"""
    parts: List[str] = []

    def _section(title: str, mapping: Any) -> None:
        if not isinstance(mapping, dict):
            return
        kv = {k: v for k, v in mapping.items() if v not in (None, "", [], {})}
        if kv:
            body = "; ".join(f"{k}={v}" for k, v in kv.items())
            parts.append(f"【{title}】{body}")

    _section("生理(HRV/睡眠/心率)", twin_json.get("physiological"))
    _section("身体成分", twin_json.get("body_composition"))
    _section("化验", twin_json.get("labs"))
    _section("CGM 血糖", twin_json.get("cgm"))
    _section("用药", twin_json.get("medication"))
    _section("补剂", twin_json.get("supplement"))
    _section("基因", twin_json.get("genetic"))
    _section("环境", twin_json.get("environment"))
    _section("行为(饮食/饮水/运动)", twin_json.get("behavioral"))
    _section("慢病", twin_json.get("chronic"))
    _section("目标", twin_json.get("goals"))
    return "\n".join(parts)


def build_context_pack(twin_json: Dict[str, Any]) -> str:
    """组装 markdown 上下文包。formatter 优先,手工回退。"""
    blob = _blob_via_formatter(twin_json)
    source = "backend twin_to_prompt_blob"
    if not blob:
        blob = _manual_blob(twin_json)
        source = "手工分区格式化(formatter 回退)"
    if not blob.strip():
        blob = "(twin 无可用数据)"
    lines = [
        "# 个人健康数据上下文包",
        "",
        "> 用途:粘贴到商用大模型对话前,作为「你已知我的健康数据」的背景材料。",
        f"> 生成方式:{source}。",
        "> 该材料仅供评测,只读拉取,不含 token。",
        "",
        "## 数据摘要",
        "",
        "```",
        blob,
        "```",
        "",
    ]
    # 附一份原始 JSON(裁掉可能的大数组)供需要精确值的臂参考
    lines += ["## 原始 Twin JSON(供精确核对)", "", "```json", json.dumps(twin_json, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="export_context_pack", description="导出个人数据上下文包(只读)")
    ap.add_argument("--out", default="context_pack.md", help="输出 markdown 路径")
    args = ap.parse_args(argv)

    twin_json = fetch_twin()
    pack = build_context_pack(twin_json)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pack, encoding="utf-8")
    print(f"[context_pack] 写入 {out} ({len(pack)} chars)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
