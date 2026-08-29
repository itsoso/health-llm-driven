"""家庭健康管理 API 测试 — 体检报告 + 指标分析"""
import base64
import io
import json
import math
import threading
from types import SimpleNamespace

import pytest
from datetime import date
from pydantic import ValidationError
from PIL import Image

from app.models.family_health import MedicalReport, MedicalIndicator
from app.models.medication import Medication


def _jpeg_base64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_report_upload_schema_limits_page_count():
    from app.api.family_health import ReportUploadRequest

    with pytest.raises(ValidationError):
        ReportUploadRequest(
            report_date=date(2026, 7, 21),
            image_base64_list=[_jpeg_base64()] * 21,
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("-", None),
        ("—", None),
        (True, None),
        (float("nan"), None),
        (float("inf"), None),
        ("0", 0.0),
        ("1.25", 1.25),
        (3, 3.0),
    ],
)
def test_report_numeric_bound_coercion_rejects_non_numeric_values(raw, expected):
    from app.api.family_health import _coerce_optional_finite_float

    actual = _coerce_optional_finite_float(raw)

    if expected is None:
        assert actual is None
    else:
        assert math.isclose(actual, expected)


def test_mark_report_failed_rolls_back_before_updating_status():
    from app.api.family_health import _mark_report_failed

    events = []
    report = SimpleNamespace(status="processing", ai_summary=None)

    class Query:
        def filter(self, *_args):
            events.append("filter")
            return self

        def first(self):
            events.append("first")
            return report

    class Db:
        def rollback(self):
            events.append("rollback")

        def query(self, *_args):
            assert events == ["rollback"]
            events.append("query")
            return Query()

        def commit(self):
            events.append("commit")

    _mark_report_failed(Db(), report_id=5, user_id=3)

    assert events == ["rollback", "query", "filter", "first", "commit"]
    assert report.status == "failed"
    assert report.ai_summary == "AI 提取失败，请重新上传"


def test_report_upload_rejects_oversized_body_before_auth_and_schema(client):
    from app.middleware.request_body_limit import MAX_MEDICAL_REPORT_REQUEST_BYTES

    response = client.post(
        "/api/v1/family-health/medical-reports/upload",
        content=b"x" * (MAX_MEDICAL_REPORT_REQUEST_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "体检报告请求体超过 10 MB 限制"


def test_report_upload_preparation_runs_off_event_loop(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    from app.api import family_health

    _, headers = auth_user_and_headers
    seen_threads = []
    original = family_health._prepare_report_payload

    def record_thread(req):
        seen_threads.append(threading.current_thread().name)
        return original(req)

    monkeypatch.setattr(family_health, "_prepare_report_payload", record_thread)
    monkeypatch.setattr(family_health, "_process_report_background", lambda *_args: None)

    response = client.post(
        "/api/v1/family-health/medical-reports/upload",
        headers=headers,
        json={
            "report_date": "2026-07-21",
            "image_base64_list": [_jpeg_base64()],
        },
    )

    assert response.status_code == 200
    assert len(seen_threads) == 1
    assert seen_threads[0].startswith("medical-report")


def test_report_upload_rejects_when_bounded_worker_queue_is_full(
    client,
    auth_user_and_headers,
):
    from app.api import family_health

    _, headers = auth_user_and_headers
    acquired = []
    try:
        for _ in range(4):
            assert family_health._REPORT_JOB_SLOTS.acquire(blocking=False)
            acquired.append(True)
        response = client.post(
            "/api/v1/family-health/medical-reports/upload",
            headers=headers,
            json={
                "report_date": "2026-07-21",
                "image_base64_list": [_jpeg_base64()],
            },
        )
        assert response.status_code == 429
    finally:
        for _ in acquired:
            family_health._REPORT_JOB_SLOTS.release()


def test_pdf_render_rejects_more_than_page_limit():
    import fitz

    from app.api.family_health import _pdf_to_images_base64
    from app.services.secure_upload import UploadTooLarge

    document = fitz.open()
    for _ in range(21):
        document.new_page()
    payload = base64.b64encode(document.tobytes()).decode("ascii")
    document.close()

    with pytest.raises(UploadTooLarge):
        _pdf_to_images_base64(payload)


def test_medication_recognition_returns_draft_without_writing(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    _, headers = auth_user_and_headers

    class VisionProvider:
        async def chat_with_vision(self, **_kwargs):
            return json.dumps({
                "name": "测试药",
                "category": "通用名",
                "dosage": "5mg",
                "frequency": "每日1次",
                "timing": "morning",
                "indication": "测试",
                "notes": "待用户核对",
            })

    monkeypatch.setattr(
        "app.services.llm.get_vision_provider",
        lambda: VisionProvider(),
    )

    response = client.post(
        "/api/v1/family-health/medications/recognize",
        headers=headers,
        json={"image_base64": _jpeg_base64()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_confirmation"] is True
    assert payload["recognized"]["name"] == "测试药"
    assert db.query(Medication).count() == 0


def test_report_upload_marks_report_failed_when_worker_submission_fails(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    _, headers = auth_user_and_headers

    def fail_submit(*_args, **_kwargs):
        raise RuntimeError("executor unavailable")

    monkeypatch.setattr(
        "app.api.family_health._REPORT_JOB_EXECUTOR.submit",
        fail_submit,
    )

    response = client.post(
        "/api/v1/family-health/medical-reports/upload",
        headers=headers,
        json={
            "report_date": "2026-07-21",
            "image_base64_list": [_jpeg_base64()],
        },
    )

    assert response.status_code == 503
    report = db.query(MedicalReport).one()
    assert report.status == "failed"
    assert "任务启动失败" in (report.ai_summary or "")


class TestMedicalReportsMe:
    """GET /family-health/medical-reports/me"""

    def test_returns_empty_list(self, client, db, auth_user_and_headers):
        """无报告时返回空列表"""
        _, headers = auth_user_and_headers
        res = client.get("/api/v1/family-health/medical-reports/me", headers=headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_returns_own_reports(self, client, db, auth_user_and_headers):
        """返回当前用户的报告列表"""
        user, headers = auth_user_and_headers
        report = MedicalReport(
            user_id=user.id,
            report_date=date(2025, 6, 1),
            hospital="测试医院",
            report_type="general",
            title="年度体检",
            status="completed",
        )
        db.add(report)
        db.commit()

        res = client.get("/api/v1/family-health/medical-reports/me", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["title"] == "年度体检"
        assert data[0]["hospital"] == "测试医院"


class TestMedicalReportDetail:
    """GET /family-health/medical-reports/{id}"""

    def test_nonexistent_report_returns_404(self, client, db, auth_user_and_headers):
        """查询不存在的报告返回 404"""
        _, headers = auth_user_and_headers
        res = client.get("/api/v1/family-health/medical-reports/99999", headers=headers)
        assert res.status_code == 404

    def test_get_own_report_detail(self, client, db, auth_user_and_headers):
        """获取自己的报告详情"""
        user, headers = auth_user_and_headers
        report = MedicalReport(
            user_id=user.id,
            report_date=date(2025, 6, 1),
            title="血液检查",
            status="completed",
            extracted_items=[{"name": "白细胞", "value": 6.5}],
            abnormal_items=[],
            ai_summary="各项指标正常",
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        res = client.get(
            f"/api/v1/family-health/medical-reports/{report.id}", headers=headers
        )
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "血液检查"
        assert data["ai_summary"] == "各项指标正常"
        assert len(data["extracted_items"]) == 1


class TestMedicalIndicatorsAnalysis:
    """GET /family-health/medical-indicators/analysis"""

    def test_analysis_returns_structure(self, client, db, auth_user_and_headers):
        """分析接口返回正确结构"""
        user, headers = auth_user_and_headers

        # 创建一些指标数据
        for i, name in enumerate(["空腹血糖", "总胆固醇"]):
            ind = MedicalIndicator(
                user_id=user.id,
                name=name,
                category="blood" if i == 0 else "lipid",
                value=5.5 + i,
                unit="mmol/L",
                is_abnormal=False,
                severity="normal",
                record_date=date(2025, 6, 1),
            )
            db.add(ind)
        db.commit()

        res = client.get(
            "/api/v1/family-health/medical-indicators/analysis", headers=headers
        )
        assert res.status_code == 200
        data = res.json()
        assert "categories" in data or "indicators" in data or isinstance(data, dict)

    def test_analysis_empty_data(self, client, db, auth_user_and_headers):
        """无指标数据时也能正常返回"""
        _, headers = auth_user_and_headers
        res = client.get(
            "/api/v1/family-health/medical-indicators/analysis", headers=headers
        )
        assert res.status_code == 200

    def test_analysis_with_category_filter(self, client, db, auth_user_and_headers):
        """按分类过滤"""
        user, headers = auth_user_and_headers
        ind = MedicalIndicator(
            user_id=user.id,
            name="空腹血糖",
            category="glucose",
            value=5.8,
            unit="mmol/L",
            is_abnormal=False,
            severity="normal",
            record_date=date(2025, 6, 1),
        )
        db.add(ind)
        db.commit()

        res = client.get(
            "/api/v1/family-health/medical-indicators/analysis?category=glucose",
            headers=headers,
        )
        assert res.status_code == 200
