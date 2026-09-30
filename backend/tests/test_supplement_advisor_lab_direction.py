"""SupplementAdvisor 化验方向门控单测.

flagged_abnormal 只说明"异常",不说明方向。镁 / 维生素 D 推荐必须以
value < 参考下限(确证偏低)为前提:
- 确证偏低 → 推荐
- 标记异常但不低(如高镁血症 / 维生素 D 过量) → 不推荐, 且压过症状/基因触发
- 方向不可解析(缺参考范围 / "<X" / 纯文字) → 保守不推荐, 给 needs-review 提示
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.agents.supplement_advisor import SupplementAdvisorSpecialist
from app.twin.schema import (
    AcuteHealthState,
    GeneticContext,
    HealthTwin,
    LabsContext,
    TwinMeta,
)
from app.utils.lab_range import is_below_range


def _twin(labs: list, *, sleep_complaint: bool = False, vdr: bool = False) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.labs = LabsContext(flagged_abnormal=labs)
    if sleep_complaint:
        t.acute = AcuteHealthState(recent_symptoms=["失眠"])
    if vdr:
        t.genetic = GeneticContext(
            has_profile=True,
            total_variants=1,
            nutrition_variants=[{"gene_name": "VDR", "genotype": "TT", "result_label": "reduced"}],
        )
    return t


def _rec_ids(f) -> set:
    return {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}


def _warnings(f) -> list:
    return [x["message"] for x in f.findings if x.get("type") == "warning"]


# ─────────── shared parser ───────────

def test_is_below_range_directions():
    assert is_below_range(0.6, "0.75-1.02") is True
    assert is_below_range(1.5, "0.75-1.02") is False
    assert is_below_range(10, "≥30") is True
    assert is_below_range(10, "<30") is None
    assert is_below_range(0.6, None) is None
    assert is_below_range("abc", "0.75-1.02") is None


# ─────────── 镁 ───────────

def test_low_magnesium_with_range_recommends():
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": "血清镁", "value": 0.6, "reference_range": "0.75-1.02"}]), {}
    )
    assert "magnesium_sleep" in _rec_ids(f)


def test_high_magnesium_does_not_recommend():
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": "血清镁", "value": 1.5, "reference_range": "0.75-1.02"}]), {}
    )
    assert "magnesium_sleep" not in _rec_ids(f)


def test_high_magnesium_overrides_sleep_complaint():
    """高镁血症 + 失眠主诉 → 仍不推镁(确证偏高压过症状触发)."""
    f = SupplementAdvisorSpecialist().run(
        _twin(
            [{"item_name": "Magnesium", "value": 1.5, "reference_range": "0.75-1.02"}],
            sleep_complaint=True,
        ),
        {},
    )
    assert "magnesium_sleep" not in _rec_ids(f)
    assert any("镁" in w and "医生" in w for w in _warnings(f))


def test_unparsable_magnesium_direction_is_conservative():
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": "血清镁", "value": 0.6}], sleep_complaint=True), {}
    )
    assert "magnesium_sleep" not in _rec_ids(f)
    assert any("镁" in w and "核读" in w for w in _warnings(f))


def test_sleep_complaint_without_mg_lab_still_recommends():
    f = SupplementAdvisorSpecialist().run(_twin([], sleep_complaint=True), {})
    assert "magnesium_sleep" in _rec_ids(f)


# ─────────── 维生素 D ───────────

def test_low_vitamin_d_with_range_recommends():
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": "25-OH-D", "value": 12, "reference_range": "30-100"}]), {}
    )
    assert "vdr_vitamin_d" in _rec_ids(f)


def test_high_vitamin_d_does_not_recommend():
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": "维生素D", "value": 160, "reference_range": "30-100"}]), {}
    )
    assert "vdr_vitamin_d" not in _rec_ids(f)
    assert "vdr_vitamin_k2" not in _rec_ids(f)


def test_high_vitamin_d_overrides_vdr_gene():
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": "25羟维生素D", "value": 160, "reference_range": "30-100"}], vdr=True),
        {},
    )
    assert "vdr_vitamin_d" not in _rec_ids(f)
    assert any("维生素 D" in w and "医生" in w for w in _warnings(f))


def test_unparsable_vitamin_d_direction_is_conservative():
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": "25-OH-D", "value": 12, "reference_range": "见报告"}]), {}
    )
    assert "vdr_vitamin_d" not in _rec_ids(f)
    assert any("维生素 D" in w and "核读" in w for w in _warnings(f))


def test_vdr_gene_without_vd_lab_still_recommends():
    f = SupplementAdvisorSpecialist().run(_twin([], vdr=True), {})
    assert "vdr_vitamin_d" in _rec_ids(f)


# ─────────── 别名 / 分析物混淆 (safety-gate 复审阻断项) ───────────

@pytest.mark.parametrize("name", [
    "25-OH-VD", "VitD", "25(OH)D", "Vitamin D", "25-羟基维生素D",
    "25-OHD", "25OHD", "25-OH D", "维D", "VITAMIN_D", "25(OH)VD", "Vitamin D, 25-Hydroxy",
])
def test_high_vitamin_d_alias_overrides_vdr_gene(name):
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": name, "value": 160, "reference_range": "30-100"}], vdr=True), {}
    )
    assert "vdr_vitamin_d" not in _rec_ids(f)
    assert "vdr_vitamin_k2" not in _rec_ids(f)


@pytest.mark.parametrize("name", [
    "Mg", "mg", "Serum Magnesium", "Serum Mg", "MG-血清", "Mg-S", "镁(Mg)", "Mg2+", "S-Mg",
    "MG", "Mg²⁺", "RBC Mg", "Mg 离子",
])
def test_high_magnesium_alias_overrides_sleep_complaint(name):
    f = SupplementAdvisorSpecialist().run(
        _twin(
            [{"item_name": name, "value": 1.5, "reference_range": "0.75-1.02"}],
            sleep_complaint=True,
        ),
        {},
    )
    assert "magnesium_sleep" not in _rec_ids(f)


@pytest.mark.parametrize("name", [
    "1,25-二羟维生素D3", "1,25-(OH)2D", "维生素D结合蛋白", "维D结合蛋白", "1α,25-二羟维生素D", "1-25 OH D",
])
def test_low_non_25oh_vitamin_d_analyte_does_not_recommend(name):
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": name, "value": 10, "reference_range": "19.6-54.3"}]), {}
    )
    assert "vdr_vitamin_d" not in _rec_ids(f)


@pytest.mark.parametrize("name", ["24小时尿镁", "Urine Magnesium"])
def test_low_urine_magnesium_does_not_recommend(name):
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": name, "value": 1.0, "reference_range": "2.1-8.2"}]), {}
    )
    assert "magnesium_sleep" not in _rec_ids(f)


def test_mg_substring_does_not_match_unrelated_item():
    """整词匹配 "mg": 名称里含 mg 子串的无关项不应压制主诉触发."""
    f = SupplementAdvisorSpecialist().run(
        _twin(
            [{"item_name": "IgM", "value": 5, "reference_range": "0.4-2.3"}],
            sleep_complaint=True,
        ),
        {},
    )
    assert "magnesium_sleep" in _rec_ids(f)


@pytest.mark.parametrize("name", ["血糖(mg/dL)", "IgM"])
def test_mg_unit_or_substring_not_treated_as_magnesium(name):
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": name, "value": 500, "reference_range": "3.9-6.1"}], sleep_complaint=True),
        {},
    )
    assert "magnesium_sleep" in _rec_ids(f)


_NON_MG_ANALYTES = [
    "β2-MG", "β2微球蛋白(β2-MG)", "B2-MG", "α1-MG", "MG抗体", "重症肌无力抗体(MG)", "AChR-Ab (MG)", "Mg-ATP",
    "β2 MG", "β2 -MG", "β2\u2010MG", "β2–MG", "β₂-MG", "MG(β2)", "α1 MG", "B2 MG", "b-2 mg",
    "MG-Ab", "抗MG", "MG IgG", "Mg-24h", "CK-MB mg",
]


@pytest.mark.parametrize("name", _NON_MG_ANALYTES)
def test_low_non_magnesium_mg_named_analyte_does_not_recommend(name):
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": name, "value": 0.8, "reference_range": "1.0-3.0"}]), {}
    )
    assert "magnesium_sleep" not in _rec_ids(f)


@pytest.mark.parametrize("name", _NON_MG_ANALYTES)
def test_high_non_magnesium_mg_named_analyte_does_not_suppress(name):
    f = SupplementAdvisorSpecialist().run(
        _twin(
            [
                {"item_name": name, "value": 5.0, "reference_range": "1.0-3.0"},
                {"item_name": "镁", "value": 0.6, "reference_range": "0.75-1.02"},
            ],
            sleep_complaint=True,
        ),
        {},
    )
    assert "magnesium_sleep" in _rec_ids(f)
    assert not any("镁" in w for w in _warnings(f))


@pytest.mark.parametrize("name", ["骨化二醇", "Calcidiol"])
def test_high_calcidiol_overrides_vdr_gene(name):
    f = SupplementAdvisorSpecialist().run(
        _twin([{"item_name": name, "value": 180, "reference_range": "30-100"}], vdr=True), {}
    )
    assert "vdr_vitamin_d" not in _rec_ids(f)
