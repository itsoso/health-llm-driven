#!/usr/bin/env python3
"""Dossier 跨产物一致性闸(spec-kit 只读 /analyze 的确定性子集)。

product-pipeline 的定义环产出 PRD↔Plan↔Dossier 三件套,但此前没有任何东西验证它们
**自洽**就放进昂贵交付环。本检查把"能确定性判"的一致性做成硬闸(符合 harness「把纪律
变机械」基因);语义级一致(PRD 说的目标 plan 有没有落)留给 LLM 只读 /analyze。

三条确定性规则(保守,避免稻草人):
  A. 进了交付环(状态∈building/testing/verifying/shipped 或 阶段≥S4)却仍留**未解**的
     `[NEEDS CLARIFICATION]` 标记 → 带着开放问题进昂贵交付 = 违规。
  B. Dossier 里引用的 `docs/{prd,plans,specs}/*.md` 锚点文件**必须存在** → 断链=违规。
  C. Gate↔阶段自洽:进交付环则 G1 准入必须 PASS;状态=shipped 则不得有任何 Gate 是 REJECT/BLOCK。

退出非零 = 有违规。可挂 product-pipeline G2/G3 或 CI / 提交闸 hook。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent  # 仓库根(backend/scripts → 上两级)
DOSSIER_DIR = ROOT / "docs" / "dossiers"

_DELIVERY_STATUS = {"building", "testing", "verifying", "shipped", "构建", "测试", "验证", "上线"}
_FM_ROW = re.compile(r"^\|\s*(?P<k>[^|]+?)\s*\|\s*(?P<v>[^|]+?)\s*\|\s*$", re.MULTILINE)
_LINK = re.compile(r"docs/(?:prd|plans|specs)/[^\s`)\"'，。、]+\.md")
_GATE_HDR = re.compile(r"^##\s*(G\d)\b.*$", re.MULTILINE)
_VERDICT = re.compile(r"\**裁决\**[:：]\s*\**\s*(PASS|REJECT|BLOCK)", re.IGNORECASE)
_MARKER = re.compile(r"\[NEEDS CLARIFICATION")


def _front_matter(text: str) -> dict:
    """解析 markdown 表格 front-matter(`| 字段 | 值 |`)。"""
    fm = {}
    for m in _FM_ROW.finditer(text[:1200]):  # 只扫开头表
        k, v = m.group("k").strip(), m.group("v").strip().strip("`")
        if k in ("字段", "---"):
            continue
        fm[k] = v
    return fm


def _in_delivery(fm: dict) -> bool:
    status = (fm.get("状态") or fm.get("status") or "").strip().lower()
    stage = (fm.get("当前阶段") or fm.get("current_stage") or "")
    if status in _DELIVERY_STATUS:
        return True
    m = re.search(r"S(\d)", stage)
    return bool(m and int(m.group(1)) >= 4)


def _gate_verdicts(text: str) -> dict:
    """{G1: PASS|REJECT|BLOCK|None, ...} —— 每个 ## G<n> 段里第一条裁决。"""
    out = {}
    hdrs = list(_GATE_HDR.finditer(text))
    for i, h in enumerate(hdrs):
        seg = text[h.end(): hdrs[i + 1].start() if i + 1 < len(hdrs) else len(text)]
        v = _VERDICT.search(seg)
        out[h.group(1)] = v.group(1).upper() if v else None
    return out


def check_dossier(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    fm = _front_matter(text)
    violations: list[str] = []
    delivery = _in_delivery(fm)

    # A. 未解 NEEDS CLARIFICATION + 进交付环
    if delivery and _MARKER.search(text):
        violations.append("进了交付环仍留未解的 [NEEDS CLARIFICATION] 标记")

    # B. 断链
    for rel in sorted(set(_LINK.findall(text))):
        if not (ROOT / rel).exists():
            violations.append(f"引用的锚点文件不存在: {rel}")

    # C. Gate↔阶段自洽
    verdicts = _gate_verdicts(text)
    if delivery and verdicts.get("G1") != "PASS":
        violations.append(f"已进交付环但 G1 准入裁决={verdicts.get('G1')}(应为 PASS)")
    status = (fm.get("状态") or fm.get("status") or "").strip().lower()
    if status in ("shipped", "上线"):
        blocked = [g for g, v in verdicts.items() if v in ("REJECT", "BLOCK")]
        if blocked:
            violations.append(f"状态=shipped 但这些 Gate 仍 REJECT/BLOCK: {blocked}")
    return violations


def main() -> int:
    if not DOSSIER_DIR.exists():
        print("✅ 无 docs/dossiers/,跳过")
        return 0
    dossiers = sorted(DOSSIER_DIR.glob("*.md"))
    bad = {}
    for d in dossiers:
        v = check_dossier(d)
        if v:
            bad[d.name] = v
    if bad:
        print("❌ Dossier 一致性闸:以下 dossier 不自洽:")
        for name, vs in bad.items():
            print(f"  · {name}")
            for x in vs:
                print(f"      - {x}")
        print("修:解决标记/补锚点文件/对齐 Gate 裁决,再进交付或提交。")
        return 1
    print(f"✅ Dossier 一致性闸:{len(dossiers)} 份 dossier 全自洽")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
