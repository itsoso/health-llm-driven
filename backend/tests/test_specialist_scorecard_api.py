"""GET /api/v1/specialists/{name}/scorecard — 单 specialist 近 N 天详情."""
from datetime import datetime, timezone, timedelta

from app.models.action_card import ActionCard
from app.models.user import User


def test_scorecard_empty(client, auth_user_and_headers):
    """用户没任何 ActionCard, 合法 specialist 返回 0/0/cards=[]."""
    _, headers = auth_user_and_headers
    r = client.get(
        "/api/v1/specialists/recovery_coach/scorecard?days=30",
        headers=headers,
    )
    assert r.status_code == 200
    b = r.json()
    assert b["specialist"] == "recovery_coach"
    assert b["window_days"] == 30
    assert b["proposed_count"] == 0
    assert b["graded_count"] == 0
    assert b["hit_rate"] == 0.0
    assert b["avg_accuracy"] is None
    assert b["cards"] == []


def test_scorecard_mixed_graded_and_pending(client, db, auth_user_and_headers):
    """混合 2 张卡: 1 graded (accuracy=85, 命中), 1 未评分. hit_rate 按 graded 分母."""
    _, headers = auth_user_and_headers
    user = db.query(User).first()

    now = datetime.now(timezone.utc)
    db.add_all([
        ActionCard(
            user_id=user.id, title="早睡 22:30", content="c",
            creator_specialist="recovery_coach",
            created_at=now - timedelta(days=15),
            graded_at=now - timedelta(days=8),
            accuracy_score=85, metric_key="sleep_score",
            target_value="78", actual_value="81",
            adherence_kind="device", adherence_confidence=85,
            grading_notes="提前入睡 42 分, 睡眠评分超目标",
        ),
        ActionCard(
            user_id=user.id, title="蛋白 +20g", content="c",
            creator_specialist="recovery_coach",
            created_at=now - timedelta(days=5),
            # 未评分: accuracy_score=None, graded_at=None
        ),
    ])
    db.commit()

    r = client.get(
        "/api/v1/specialists/recovery_coach/scorecard?days=30",
        headers=headers,
    )
    assert r.status_code == 200
    b = r.json()
    assert b["proposed_count"] == 2
    assert b["graded_count"] == 1
    assert b["avg_accuracy"] == 85.0
    assert b["hit_rate"] == 0.5  # 1 graded / 2 proposed
    assert len(b["cards"]) == 2

    graded_card = next(c for c in b["cards"] if c["accuracy_score"] is not None)
    assert graded_card["title"] == "早睡 22:30"
    assert graded_card["metric_key"] == "sleep_score"
    assert graded_card["target_value"] == "78"
    assert graded_card["actual_value"] == "81"
    assert graded_card["adherence_kind"] == "device"
    assert graded_card["adherence_confidence"] == 85
    assert graded_card["why_short"] == "提前入睡 42 分, 睡眠评分超目标"

    pending_card = next(c for c in b["cards"] if c["accuracy_score"] is None)
    assert pending_card["title"] == "蛋白 +20g"
    assert pending_card["graded_at"] is None


def test_scorecard_hides_legacy_clinician_gated_hit_score(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    user = db.query(User).first()
    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=user.id,
        title="降低 LDL",
        content="c",
        creator_specialist="recovery_coach",
        created_at=now - timedelta(days=5),
        graded_at=now - timedelta(days=1),
        accuracy_score=95,
        metric_key="ldl",
        target_value="<3.0",
        actual_value="2.8",
    ))
    db.commit()

    response = client.get(
        "/api/v1/specialists/recovery_coach/scorecard?days=30",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["graded_count"] == 0
    assert body["avg_accuracy"] is None
    assert body["cards"][0]["accuracy_score"] is None
    assert body["cards"][0]["score_status"] == "clinician_review"


def test_personal_scorecard_excludes_legacy_clinician_gated_score(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    user = db.query(User).first()
    now = datetime.now(timezone.utc)
    db.add_all([
        ActionCard(
            user_id=user.id, title="降低 LDL", content="c",
            creator_specialist="metabolic_specialist",
            created_at=now - timedelta(days=5),
            graded_at=now - timedelta(days=1),
            accuracy_score=95, metric_key="ldl",
        ),
        ActionCard(
            user_id=user.id, title="睡眠恢复", content="c",
            creator_specialist="recovery_coach",
            created_at=now - timedelta(days=4),
            graded_at=now - timedelta(days=1),
            accuracy_score=80, metric_key="hrv",
        ),
    ])
    db.commit()

    response = client.get("/api/v1/personal-outcome/me/scorecard?days=30", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["total"] == 1
    assert body["overall"]["hit_rate"] == 100.0
    assert [card["metric"] for card in body["top_hits"]] == ["hrv"]


def test_scorecard_unknown_specialist_404(client, auth_user_and_headers):
    """非法 specialist name 返回 404, detail 含 legal_specialists 列表."""
    _, headers = auth_user_and_headers
    r = client.get(
        "/api/v1/specialists/totally_fake/scorecard",
        headers=headers,
    )
    assert r.status_code == 404
    body = r.json()
    # FastAPI 把 dict detail 包在 detail 字段里
    detail = body.get("detail")
    if isinstance(detail, dict):
        assert "legal_specialists" in detail
        assert "recovery_coach" in detail["legal_specialists"]
    else:
        # 兼容 detail 被 str 包装
        assert "recovery_coach" in str(detail)
