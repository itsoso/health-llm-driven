# -*- coding: utf-8 -*-
"""冷启动信息增益(Next Horizon Tier 4)回归。

钉:空 Twin → 建议补血检/可穿戴/体重;PhenoAge 已有越多 priority 越高;
已有数据不再建议;端点鉴权。
"""
from datetime import datetime

from app.twin.schema import (
    BodyCompositionState,
    HealthTwin,
    LabsContext,
    PhysiologicalState,
    TwinMeta,
)


def _twin(**kw):
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 6)), **kw)


def test_empty_twin_suggests_all_three():
    from app.services.data_acquisition_guidance import next_best_data
    out = next_best_data(_twin())
    unlocks = " ".join(s["unlocks"] for s in out["suggestions"])
    assert "生物年龄" in unlocks and "VO2max" in unlocks and "代谢基线" in unlocks
    # 排序:生物年龄(50+)> VO2max(40)> 体重(30)
    assert out["suggestions"][0]["unlocks"].startswith("生物年龄")


def test_each_suggestion_carries_its_route():
    """每条建议带 route,前端点击才能跳对页(血检→化验、可穿戴→导入、体重→体重趋势)。"""
    from app.services.data_acquisition_guidance import next_best_data
    by_item = {s["item"]: s["route"] for s in next_best_data(_twin())["suggestions"]}
    blood = next(r for it, r in by_item.items() if "血检" in it)
    wearable = next(r for it, r in by_item.items() if "可穿戴" in it)
    weight = next(r for it, r in by_item.items() if "体重" in it)
    assert blood == "/medical-exams"
    assert wearable == "/import"
    assert weight == "/indicator-history?type=weight"


def test_phenoage_priority_rises_with_more_data():
    from app.services.data_acquisition_guidance import next_best_data
    few = _twin(labs=LabsContext(albumin=45))                       # 有 1 项
    many = _twin(labs=LabsContext(albumin=45, creatinine=80, blood_glucose=5,
                                  crp=0.1, lymphocyte_pct=30, mcv=90, rdw=13))  # 有 7 项
    p_few = next((s for s in next_best_data(few)["suggestions"] if "血检" in s["item"]))
    p_many = next((s for s in next_best_data(many)["suggestions"] if "血检" in s["item"]))
    assert p_many["priority"] > p_few["priority"]   # 差得越少,补齐 ROI 越高
    assert p_many["missing_count"] == 2


def test_no_suggestion_when_data_present():
    from app.services.data_acquisition_guidance import next_best_data
    t = _twin(
        labs=LabsContext(phenotypic_age=44.0),
        physiological=PhysiologicalState(vo2max_running=45.0),
        body_composition=BodyCompositionState(weight_kg=72.0),
    )
    assert next_best_data(t)["suggestions"] == []


def test_endpoint_requires_auth(client):
    r = client.get("/api/v1/twin/me/next-data")
    assert r.status_code in (401, 403)
