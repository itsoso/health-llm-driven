from datetime import date

from tests.conftest import create_authenticated_user
from app.models.medical_exam import MedicalExam


def test_owned_detail_is_not_limited_to_recent_fifty(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.medical_exams import router
    from app.database import get_db
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/medical-exams")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    report = MedicalExam(user_id=user.id, exam_date=date(2020, 1, 1),
                         overall_assessment="合成摘要" * 600 + "完整末尾")
    db.add(report)
    db.flush()
    for _ in range(51):
        db.add(MedicalExam(user_id=user.id, exam_date=date(2026, 1, 1)))
    db.commit()
    response = client.get(f"/api/v1/medical-exams/me/{report.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["overall_assessment"] == report.overall_assessment
    other, token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/v1/medical-exams/me/{report.id}", headers=other_headers).status_code == 404
    assert client.get("/api/v1/medical-exams/me/999999", headers=headers).status_code == 404
    assert client.get(f"/api/v1/medical-exams/me/{report.id}").status_code == 401
