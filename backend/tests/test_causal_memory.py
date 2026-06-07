# -*- coding: utf-8 -*-
"""因果记忆(RFC 方向二)回归。

钉:事件后指标显著变化→记忆条;方向(改善/走低)按指标语义;阈值/缺值跳过;
文案标"相关非因果";端点鉴权。真实因果不声称(observational)。
"""
from app.services.causal_memory import notes_from_impact


def _impact(before, after, title="补充维D", window=30):
    return {"title": title, "window_days": window, "before": before, "after": after}


def test_improvement_note_direction():
    # HRV 升(越高越好)→ 改善;RHR 升(越低越好)→ 走低
    notes = notes_from_impact(_impact(
        before={"hrv": 40, "rhr": 60}, after={"hrv": 48, "rhr": 66}))
    by = {n["metric"]: n for n in notes}
    assert by["hrv"]["direction"] == "改善"
    assert by["rhr"]["direction"] == "走低"
    assert "相关非因果" in by["hrv"]["text"] and "补充维D" in by["hrv"]["text"]


def test_below_threshold_skipped():
    notes = notes_from_impact(_impact(before={"hrv": 50}, after={"hrv": 51}))  # 2% < 5%
    assert notes == []


def test_missing_or_zero_skipped():
    assert notes_from_impact(_impact(before={"hrv": None}, after={"hrv": 50})) == []
    assert notes_from_impact(_impact(before={"hrv": 0}, after={"hrv": 50})) == []
    assert notes_from_impact(_impact(before={}, after={})) == []


def test_derive_empty_when_no_events(db):
    from app.services.causal_memory import derive_causal_notes
    out = derive_causal_notes(db, user_id=99999)
    assert out["notes"] == [] and out["evidence_tier"] == "observational"


def test_endpoint_requires_auth(client):
    r = client.get("/api/v1/personal-outcome/me/causal-notes")
    assert r.status_code in (401, 403)
