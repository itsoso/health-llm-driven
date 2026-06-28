"""Dossier 跨产物一致性闸测试 —— 证明闸有牙(能真抓违规,非 no-op)。

#5(spec-kit /analyze 的确定性子集)落地。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dossier_consistency.py"


def _mod():
    spec = importlib.util.spec_from_file_location("check_dossier_consistency", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 一个引用真实存在锚点文件的干净 dossier(用本测试文件自身相对路径确保 ROOT/link 存在)
_EXISTING_LINK = "docs/dossiers"  # 目录一定在;但 checker 只匹配 *.md,故引一个真 .md:


def _clean(status="building", stage="S5 实现", gates="G1: PASS", link=None):
    link = link or "docs/dossiers/2026-06-28-home-daily-artifact-runtime.md"
    g_lines = "\n\n".join(
        f"## {g.split(':')[0]} · x\n- 裁决: {g.split(':')[1].strip()}。" for g in gates.split("\n") if ":" in g
    )
    return f"""# Dossier: 测试

| 字段 | 值 |
|---|---|
| slug | `t` |
| 当前阶段 | {stage} |
| 状态 | {status} |

## S1 · Discovery
- PRD 锚点: `{link}`

{g_lines}
"""


def _check(tmp_path, content):
    p = tmp_path / "d.md"
    p.write_text(content, encoding="utf-8")
    return _mod().check_dossier(p)


def test_clean_dossier_passes(tmp_path):
    assert _check(tmp_path, _clean()) == []


def test_bold_gate_verdict_passes(tmp_path):
    c = _clean().replace("- 裁决: PASS。", "- **裁决**: PASS")
    assert _check(tmp_path, c) == []


def test_unresolved_marker_in_delivery_fails(tmp_path):
    c = _clean() + "\n\n## S2\n- [NEEDS CLARIFICATION: 用哪个端点?]\n"
    v = _check(tmp_path, c)
    assert any("NEEDS CLARIFICATION" in x for x in v)


def test_marker_ok_in_define_loop(tmp_path):
    # 还在定义环(intake/S1)留标记是合法的,不该报
    c = _clean(status="intake", stage="S1 Discovery") + "\n- [NEEDS CLARIFICATION: 待定]\n"
    assert _check(tmp_path, c) == []


def test_broken_anchor_link_fails(tmp_path):
    c = _clean(link="docs/prd/this-does-not-exist-xyz.md")
    v = _check(tmp_path, c)
    assert any("不存在" in x for x in v)


def test_gate_stage_mismatch_fails(tmp_path):
    # 进了交付环(S5)但 G1 不是 PASS
    c = _clean(gates="G1: REJECT")
    v = _check(tmp_path, c)
    assert any("G1 准入" in x for x in v)


def test_shipped_with_block_fails(tmp_path):
    c = _clean(status="shipped", stage="S8 沉淀", gates="G1: PASS\nG4: BLOCK")
    v = _check(tmp_path, c)
    assert any("REJECT/BLOCK" in x for x in v)


# ── 加固:裁决词表对齐 template(GO/绿=pass、红/NO-GO/真红/FAIL=fail)──

def test_go_green_verdicts_recognized_as_pass(tmp_path):
    # 真 dossier 的 G3=绿、G4=GO 是"通过",不该被当成 None 静默跳过,clean dossier 应过
    c = _clean(status="shipped", stage="S8 沉淀", gates="G1: PASS\nG3: 绿\nG4: GO\nG5: PASS\nG6: PASS")
    assert _check(tmp_path, c) == []


def test_shipped_with_colloquial_fail_verdict_caught(tmp_path):
    # 关键回归:旧 _VERDICT 只认 REJECT/BLOCK,真红/NO-GO/FAIL 全漏 → shipped 带失败闸能干净过(fail-open)
    for fail_word in ["真红", "NO-GO", "FAIL", "红", "失败"]:
        c = _clean(status="shipped", stage="S8 沉淀", gates=f"G1: PASS\nG4: {fail_word}")
        v = _check(tmp_path, c)
        assert any("判失败" in x for x in v), f"shipped + G4={fail_word} 应被抓到失败,实得 {v}"


def test_subheading_gate_failure_caught(tmp_path):
    # ### 子级 gate 标题里的失败裁决不能逃逸
    c = f"""# Dossier: 测试

| 字段 | 值 |
|---|---|
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |

## S1 · Discovery
- PRD 锚点: `docs/dossiers/2026-06-28-home-daily-artifact-runtime.md`

## G1 · 准入
- **裁决**: PASS

### G4 · 安全闸
- **裁决**: REJECT
"""
    v = _check(tmp_path, c)
    assert any("判失败" in x for x in v), f"### 级 G4=REJECT 应被抓,实得 {v}"


def test_merged_gate_header_failure_caught(tmp_path):
    # 合并头 `## G5/G6` 里 G6=FAIL 不能因只捕获 G5 而漏
    c = f"""# Dossier: 测试

| 字段 | 值 |
|---|---|
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |

## S1 · Discovery
- PRD 锚点: `docs/dossiers/2026-06-28-home-daily-artifact-runtime.md`

## G1 · 准入
- **裁决**: PASS

## G5/G6 · 部署健康与上线验证
- **裁决**: FAIL
"""
    v = _check(tmp_path, c)
    assert any("判失败" in x for x in v), f"合并头 G5/G6=FAIL 应被抓,实得 {v}"


def test_stage_s10_still_in_delivery(tmp_path):
    # 多位阶段号 S10 不能被读成 S1 而漏出交付环判定
    c = _clean(status="intake", stage="S10 扩展", gates="G1: REJECT")
    v = _check(tmp_path, c)
    assert any("G1 准入" in x for x in v), f"S10 应判在交付环、G1 非 PASS 应报,实得 {v}"


def test_missing_frontmatter_fails_closed(tmp_path):
    # 完全没有 front-matter 表 → 不能静默跳过交付闸,应 fail-loud 报"无法解析"
    c = "# Dossier: 残缺\n\n## G1 · 准入\n- 裁决: REJECT\n\n- [NEEDS CLARIFICATION: 谁负责?]\n"
    v = _check(tmp_path, c)
    assert any("无法解析" in x for x in v), f"缺 front-matter 应 fail-closed 报,实得 {v}"


def test_unknown_verdict_in_shipped_flagged(tmp_path):
    # shipped dossier 出现无法识别的裁决词 → fail-closed 报警(防新失败词汇静默逃逸)
    c = _clean(status="shipped", stage="S8 沉淀", gates="G1: PASS\nG4: 待定")
    v = _check(tmp_path, c)
    assert any("无法识别" in x for x in v), f"shipped + 未知裁决词应报警,实得 {v}"


# ── 二轮加固回归(对抗复审在一轮加固里发现的新洞)──

def test_negated_pass_verdict_not_washed_to_pass(tmp_path):
    # 关键 fail-open:`未通过`=失败,绝不能被 "通过" 子串洗成 pass
    m = _mod()
    assert m._classify_verdict("未通过") == "fail"
    assert m._classify_verdict("暂未通过") == "fail"
    assert m._classify_verdict("通过") == "pass"
    c = _clean(status="shipped", stage="S8 沉淀", gates="G1: PASS\nG6: 未通过")
    v = _check(tmp_path, c)
    assert any("判失败" in x for x in v), f"shipped + G6=未通过 应被抓,实得 {v}"


def test_reject_synonyms_caught_in_delivery(tmp_path):
    # 驳回/打回/退回 是失败词,building 交付环也该抓(不只 shipped)
    c = _clean(status="building", stage="S5 实现", gates="G1: PASS\nG4: 驳回")
    v = _check(tmp_path, c)
    assert any("判失败" in x for x in v), f"building + G4=驳回 应被抓,实得 {v}"


def test_five_level_and_midline_gate_headers_caught(tmp_path):
    # 5 级标题 / G 号在标题中段,失败 gate 不能因标题写法逃逸
    for hdr in ["##### G4 · 安全闸", "## 测试闸 G4"]:
        c = f"""# Dossier: x

| 字段 | 值 |
|---|---|
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |

## S1 · Discovery
- PRD 锚点: `docs/dossiers/2026-06-28-home-daily-artifact-runtime.md`

## G1 · 准入
- **裁决**: PASS

{hdr}
- **裁决**: BLOCK
"""
        v = _check(tmp_path, c)
        assert any("判失败" in x for x in v), f"标题写法 '{hdr}' 的失败 gate 漏判,实得 {v}"


def test_real_dossiers_all_consistent():
    # 仓库现有真 dossier 必须自洽(否则就是真问题,gate 该红)
    m = _mod()
    ddir = Path(__file__).resolve().parents[1].parent / "docs" / "dossiers"
    for d in sorted(ddir.glob("*.md")):
        assert m.check_dossier(d) == [], f"{d.name} 不自洽: {m.check_dossier(d)}"
