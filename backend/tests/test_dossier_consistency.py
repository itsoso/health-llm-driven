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


def test_real_dossiers_all_consistent():
    # 仓库现有真 dossier 必须自洽(否则就是真问题,gate 该红)
    m = _mod()
    ddir = Path(__file__).resolve().parents[1].parent / "docs" / "dossiers"
    for d in sorted(ddir.glob("*.md")):
        assert m.check_dossier(d) == [], f"{d.name} 不自洽: {m.check_dossier(d)}"
