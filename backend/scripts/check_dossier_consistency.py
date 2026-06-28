#!/usr/bin/env python3
"""Dossier 跨产物一致性闸(spec-kit 只读 /analyze 的确定性子集)。

product-pipeline 的定义环产出 PRD↔Plan↔Dossier 三件套,但此前没有任何东西验证它们
**自洽**就放进昂贵交付环。本检查把"能确定性判"的一致性做成硬闸(符合 harness「把纪律
变机械」基因);语义级一致(PRD 说的目标 plan 有没有落)留给 LLM 只读 /analyze。

四条确定性规则(保守,避免稻草人;**fail-closed**:判不出来宁可报也不放过):
  A. 进了交付环(状态∈building/shipping/shipped 或 阶段≥S4)却仍留**未解**的
     `[NEEDS CLARIFICATION]` 标记 → 带着开放问题进昂贵交付 = 违规。
  B. Dossier 里引用的 `docs/{prd,plans,specs}/*.md` 锚点文件**必须存在** → 断链=违规。
  C. Gate↔阶段自洽:进交付环则 G1 准入必须 PASS;状态=shipped 则不得有任何 Gate 判失败
     (REJECT/BLOCK/NO-GO/真红/红/FAIL/失败/自动回滚)。**裁决词表对齐 dossier-template**
     (G3=绿/真红、G4=GO/BLOCK、G5=PASS/自动回滚、G6=PASS/FAIL),并对交付环里**无法识别**
     的裁决词 fail-closed 报警(防新词汇再次静默逃逸)。
  D. front-matter 必须可解析(有状态或阶段字段)。完全解析不出 = 无法施加交付闸 = fail-loud 报。

退出非零 = 有违规。可挂 product-pipeline G2/G3 或手动 / CI / 提交闸 hook。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent  # 仓库根(backend/scripts → 上两级)
DOSSIER_DIR = ROOT / "docs" / "dossiers"

# 交付环状态:对齐 dossier-template 的状态枚举(intake/defining/building/shipping/shipped/
# rejected/parked)里**已进或在交付期**的子集 + 中文别名。删掉 template 不承认的 testing/verifying
# 死分支(单一真源 = template)。判不准时还有 _in_delivery 的 stage≥S4 兜底。
_DELIVERY_STATUS = {"building", "shipping", "shipped", "构建", "部署", "部署中", "上线"}

_FM_ROW = re.compile(r"^\|\s*(?P<k>[^|]+?)\s*\|\s*(?P<v>[^|]+?)\s*\|\s*$", re.MULTILINE)
_LINK = re.compile(r"docs/(?:prd|plans|specs)/[^\s`)\"'，。、]+\.md")
# gate 标题:容忍 ## ~ ###### 层级、G 号在标题任意位置、合并头(`## G5/G6 …`)、行内代码(`` `G3` ``)。
# 整行(含标题文字)捕获,G 号在代码里 findall —— 这样 `##### G4`、`## 测试闸 G3`、`` ## `G3` `` 都不漏。
_GATE_HDR_LINE = re.compile(r"^#{2,6}\s+([^\n]*G\d[^\n]*)$", re.MULTILINE)
_GATE_NUM = re.compile(r"G(\d)")
# 裁决词:捕获 `裁决:` 后第一个 token(容忍 markdown 粗体 `**裁决**:`),词表分类在代码里做。
_VERDICT = re.compile(r"\**裁决\**\s*[:：]\s*\**\s*([^\s。,，;；)）(（*]+)", re.IGNORECASE)
_MARKER = re.compile(r"\[NEEDS CLARIFICATION")

# 裁决词表(对齐 dossier-template 的各 Gate 通过/失败词)。
_PASS_WORDS = {"PASS", "GO", "OK", "绿", "通过", "GREEN"}
_FAIL_WORDS = {
    "REJECT", "BLOCK", "NO-GO", "NOGO", "FAIL", "FAILED", "RED",
    "真红", "红", "失败", "自动回滚", "回滚", "拒绝", "不通过", "阻断",
    "驳回", "打回", "退回", "不予通过",
}
# 否定式"通过"(未通过/尚未通过/不予通过/没达标)= 失败 —— 必须**先于** pass 子串判定,
# 否则 "通过" 子串会把 "未通过" 误洗成 pass(这是上一轮加固漏掉的 fail-open)。
_NEG_PASS_RE = re.compile(r"(未|不予?|没|尚未|暂未|暂不)\s*(通过|达标|过关|合格)")


def _classify_verdict(token: str) -> str:
    """→ 'pass' | 'fail' | 'unknown'(裁决行存在但词不认得→fail-closed 视为可疑)。"""
    raw = token.strip().strip("*").rstrip("。,，;；)）")
    upper = raw.upper()
    if _NEG_PASS_RE.search(raw):          # 未通过/不予通过/尚未达标 = 失败,先判(否则被 pass 子串洗白)
        return "fail"
    for w in _FAIL_WORDS:
        if w.upper() in upper or w in raw:
            return "fail"
    for w in _PASS_WORDS:
        if w.upper() == upper or w in raw:
            return "pass"
    return "unknown"


def _front_matter(text: str) -> dict:
    """解析 markdown 表格 front-matter(`| 字段 | 值 |`)。"""
    fm = {}
    for m in _FM_ROW.finditer(text[:1500]):  # 只扫开头表(略放宽窗口)
        k, v = m.group("k").strip(), m.group("v").strip().strip("`")
        if k in ("字段", "---"):
            continue
        fm[k] = v
    return fm


def _has_front_matter(fm: dict) -> bool:
    return any(k in fm for k in ("状态", "status", "当前阶段", "current_stage"))


def _in_delivery(fm: dict) -> bool:
    status = (fm.get("状态") or fm.get("status") or "").strip().lower()
    stage = (fm.get("当前阶段") or fm.get("current_stage") or "")
    if status in _DELIVERY_STATUS:
        return True
    m = re.search(r"S(\d+)", stage)  # 多位数字(S10+ 不再被读成 S1)
    return bool(m and int(m.group(1)) >= 4)


def _gate_sections(text: str):
    """→ [(gate_nums:set[str], verdict_class:'pass'|'fail'|'unknown'|None), ...]
    每个 gate 标题段(到下一个 gate 标题)取首条裁决并分类。合并头 `G5/G6` 把两个号归同段。"""
    sections = []
    hdrs = list(_GATE_HDR_LINE.finditer(text))
    for i, h in enumerate(hdrs):
        nums = set(_GATE_NUM.findall(h.group(1)))
        seg = text[h.end(): hdrs[i + 1].start() if i + 1 < len(hdrs) else len(text)]
        v = _VERDICT.search(seg)
        cls = _classify_verdict(v.group(1)) if v else None
        sections.append((nums, cls))
    return sections


def check_dossier(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    fm = _front_matter(text)
    violations: list[str] = []

    # D. front-matter 不可解析 → fail-loud(否则交付闸被静默跳过 = fail-open)
    if not _has_front_matter(fm):
        violations.append("无法解析 dossier front-matter(缺状态/阶段字段),无法施加交付闸")
        delivery = True  # 状态未知时保守按"在交付环"继续后续检查(fail-closed)
    else:
        delivery = _in_delivery(fm)

    # A. 未解 NEEDS CLARIFICATION + 进交付环
    if delivery and _MARKER.search(text):
        violations.append("进了交付环仍留未解的 [NEEDS CLARIFICATION] 标记")

    # B. 断链
    for rel in sorted(set(_LINK.findall(text))):
        if not (ROOT / rel).exists():
            violations.append(f"引用的锚点文件不存在: {rel}")

    # C. Gate↔阶段自洽
    sections = _gate_sections(text)
    status = (fm.get("状态") or fm.get("status") or "").strip().lower()
    is_shipped = status in ("shipped", "上线")

    if delivery:
        g1 = next((cls for nums, cls in sections if "1" in nums), "MISSING")
        if g1 != "pass":
            label = {"fail": "判失败", "unknown": "裁决词无法识别", None: "无裁决", "MISSING": "缺 G1 段"}.get(g1, g1)
            violations.append(f"已进交付环但 G1 准入非 PASS({label})")

    if is_shipped or delivery:
        for nums, cls in sections:
            tag = "/".join("G" + n for n in sorted(nums)) or "G?"
            if cls == "fail":
                where = "状态=shipped" if is_shipped else "已进交付环"
                violations.append(f"{where} 但 {tag} 判失败(REJECT/BLOCK/红/FAIL 类)")
            elif cls == "unknown" and is_shipped:
                # fail-closed:shipped dossier 里出现不认识的裁决词,可能是失败被新词汇藏住
                violations.append(f"{tag} 裁决词无法识别(疑似新失败词汇,fail-closed 报警)")
    return violations


def main() -> int:
    if not DOSSIER_DIR.exists():
        # 打印解析到的绝对路径,便于发现"目录被改名/迁移"导致的静默 no-op
        print(f"✅ 无 docs/dossiers/(查找路径: {DOSSIER_DIR}),跳过")
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
