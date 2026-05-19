"""Conversation starters endpoint tests.

Goal: The new-chat empty state should show dynamic prompt chips derived from
recent user data (exams/workouts/supplements/sleep) with a safe default fallback.
"""

from datetime import date, timedelta


DEFAULT_SUGGESTIONS = [
    "分析我最近的代谢健康",
    "今天怎么安排训练和恢复",
    "结合基因和体检给我建议",
    "帮我复盘最近的睡眠质量",
]


def test_endpoint_returns_default_suggestions_when_no_data(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    payload = r.json()
    assert payload["opener"] is None
    assert payload["suggestions"] == DEFAULT_SUGGESTIONS


def test_endpoint_includes_exam_hint_when_recent_exam_exists(client, db, auth_user_and_headers):
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    user, headers = auth_user_and_headers

    exam = MedicalExam(
        user_id=user.id,
        exam_date=date.today() - timedelta(days=3),
        exam_type="comprehensive",
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    db.add(
        MedicalExamItem(
            exam_id=exam.id,
            category="lipid",
            item_name="LDL-C",
            value=4.2,
            unit="mmol/L",
            reference_range="<3.4",
            result="偏高",
            is_abnormal="high",
            source="manual",
        )
    )
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    payload = r.json()
    assert isinstance(payload["suggestions"], list)
    assert any("体检" in text for text in payload["suggestions"])
    assert any("LDL" in text for text in payload["suggestions"])
