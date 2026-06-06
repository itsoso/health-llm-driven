# -*- coding: utf-8 -*-
"""数据质量 → Agent 置信度门控(Next Horizon Tier 5)回归。

钉:源越少置信越低;low/medium 给 hedge,high 不给;blob 低置信注入 hedge,高置信不注入。
"""
from datetime import datetime

from app.twin.schema import HealthTwin, LabsContext, PhysiologicalState, TwinMeta


def _twin(sources):
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 6),
                                    data_sources=sources))


def test_confidence_levels():
    from app.services.data_confidence import assess_data_confidence
    low = assess_data_confidence(_twin(["garmin"]))            # 1/5=0.2 → low
    med = assess_data_confidence(_twin(["garmin", "weight"]))  # 2/5=0.4 → medium
    high = assess_data_confidence(_twin(["a", "b", "c", "d", "e"]))  # 1.0 → high
    assert low["level"] == "low" and low["hedge_hint"]
    assert med["level"] == "medium" and med["hedge_hint"]
    assert high["level"] == "high" and high["hedge_hint"] == ""
    assert low["score"] < med["score"] < high["score"]


def test_empty_sources_low():
    from app.services.data_confidence import assess_data_confidence
    a = assess_data_confidence(_twin([]))
    assert a["level"] == "low" and a["present_sources"] == 0


def test_blob_injects_hedge_when_low():
    """低置信 + 有内容 → blob 含 hedge(末尾,不破坏首行);高置信不注入。"""
    from app.twin.formatter import twin_to_prompt_blob
    t = _twin(["garmin"])
    t.physiological = PhysiologicalState(hrv_latest=42.0, resting_hr=55)
    blob = twin_to_prompt_blob(t)
    assert blob and "置信度低" in blob
    assert blob.startswith("生理:")          # 首行格式不被破坏
    assert blob.splitlines()[-1].startswith("⚠️")  # hedge 在末尾

    t2 = _twin(["a", "b", "c", "d", "e"])
    t2.physiological = PhysiologicalState(hrv_latest=42.0, resting_hr=55)
    blob2 = twin_to_prompt_blob(t2)
    assert "置信度" not in blob2             # high → 不注入


def test_blob_empty_stays_empty():
    """无任何数据 → blob 仍为空(不因 hedge 变非空)。"""
    from app.twin.formatter import twin_to_prompt_blob
    assert twin_to_prompt_blob(_twin([])) == ""
