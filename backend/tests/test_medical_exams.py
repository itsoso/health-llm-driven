"""体检数据API测试 — 所有端点强制 auth 到 current_user"""
from io import BytesIO
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from app.models.user import User
from app.services.auth import auth_service
from PIL import Image


def _tiny_image_bytes(image_format: str = "JPEG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(output, format=image_format)
    return output.getvalue()


def _create_user(db):
    """创建普通用户,返回 (user, headers)"""
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        name="测试用户",
        birth_date=date(1990, 1, 1),
        gender="男",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, {"Authorization": f"Bearer {token}"}


def test_create_medical_exam_requires_auth(client, sample_medical_exam_data):
    """未登录 → 401"""
    resp = client.post("/api/v1/medical-exams", json=sample_medical_exam_data)
    assert resp.status_code == 401


def test_create_medical_exam(client, db, sample_medical_exam_data):
    """创建体检记录 — 强制绑到 current_user"""
    user, headers = _create_user(db)
    # 即使 payload 传 user_id=999,也应被忽略强制为 current_user.id
    sample_medical_exam_data["user_id"] = 999

    resp = client.post("/api/v1/medical-exams", json=sample_medical_exam_data, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user.id
    assert data["exam_type"] == sample_medical_exam_data["exam_type"]
    assert len(data["items"]) == len(sample_medical_exam_data["items"])


def test_get_user_medical_exams_self(client, db, sample_medical_exam_data):
    """GET /user/{id} 只能看自己的"""
    user, headers = _create_user(db)
    client.post("/api/v1/medical-exams", json=sample_medical_exam_data, headers=headers)

    resp = client.get(f"/api/v1/medical-exams/user/{user.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_other_user_medical_exams_forbidden(client, db):
    """试图看别人的体检记录 → 403"""
    _, headers = _create_user(db)
    other, _ = _create_user(db)
    resp = client.get(f"/api/v1/medical-exams/user/{other.id}", headers=headers)
    assert resp.status_code == 403


def test_get_my_medical_exams(client, db, sample_medical_exam_data):
    """GET /me 端点"""
    _, headers = _create_user(db)
    client.post("/api/v1/medical-exams", json=sample_medical_exam_data, headers=headers)

    resp = client.get("/api/v1/medical-exams/me", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_get_my_medical_exam_report_summaries_is_compact_and_user_scoped(client, db):
    """报告级列表返回紧凑摘要,不把所有 item 明细塞进 Agent 上下文。"""
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    user, headers = _create_user(db)
    other, _ = _create_user(db)

    recent = MedicalExam(
        user_id=user.id,
        exam_date=date(2026, 7, 1),
        exam_type="MRI",
        body_system="skeletal",
        hospital_name="杭州测试医院",
        overall_assessment="左膝关节内外侧盘状半月板考虑，并半月板水平损伤。",
        created_at=datetime.now(timezone.utc),
    )
    older = MedicalExam(
        user_id=user.id,
        exam_date=date(2026, 6, 1),
        exam_type="blood_routine",
        hospital_name="旧报告医院",
        overall_assessment="血常规复查。",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    other_exam = MedicalExam(
        user_id=other.id,
        exam_date=date(2026, 7, 2),
        exam_type="CT",
        overall_assessment="其他用户报告不应出现。",
        created_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add_all([recent, older, other_exam])
    db.flush()
    db.add_all([
        MedicalExamItem(exam_id=recent.id, item_name="内侧半月板", is_abnormal="abnormal"),
        MedicalExamItem(exam_id=recent.id, item_name="外侧半月板", is_abnormal="normal"),
        MedicalExamItem(exam_id=older.id, item_name="白细胞", is_abnormal="normal"),
    ])
    db.commit()

    resp = client.get("/api/v1/medical-exams/me/reports?limit=20", headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert [row["id"] for row in data] == [recent.id, older.id]
    assert data[0]["items_count"] == 2
    assert data[0]["abnormal_items_count"] == 1
    assert data[0]["overall_assessment"].startswith("左膝关节")
    assert "items" not in data[0]
    assert all("其他用户" not in str(row) for row in data)


def test_import_medical_exam_from_json(client, db):
    """JSON 导入不再需要 user_id 参数,自动绑当前用户"""
    _, headers = _create_user(db)

    import_data = {
        "exam": {
            "exam_date": "2024-01-01",
            "exam_type": "blood_routine",
            "body_system": "circulatory",
            "hospital_name": "测试医院"
        },
        "items": [
            {
                "item_name": "白细胞",
                "value": 6.5,
                "unit": "10^9/L",
                "reference_range": "3.5-9.5",
                "result": "正常",
                "is_abnormal": "normal"
            }
        ]
    }

    resp = client.post("/api/v1/medical-exams/import/json", json=import_data, headers=headers)
    assert resp.status_code == 200
    assert "exam_id" in resp.json()


def test_import_medical_exam_from_json_requires_auth(client):
    """导入也需要 auth"""
    resp = client.post("/api/v1/medical-exams/import/json", json={})
    assert resp.status_code == 401


def test_import_medical_exam_from_text_persists_indicators(client, db):
    """Mobile 手工贴文字兜底必须真实入库,不能只做 parse preview."""
    from app.models.family_health import MedicalIndicator

    user, headers = _create_user(db)
    payload = {
        "text": "ALT 31 U/L，AST 24 U/L，肌酐 71 μmol/L，尿素 4.03 mmol/L，尿酸 299 μmol/L，空腹血糖 5.60 mmol/L",
        "exam_date": "2026-05-11",
        "hospital_name": "手工录入",
    }

    resp = client.post("/api/v1/medical-exams/import/text", json=payload, headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items_count"] >= 6
    assert data["exam_date"] == "2026-05-11"

    rows = db.query(MedicalIndicator).filter(MedicalIndicator.user_id == user.id).all()
    codes = {row.item_code for row in rows}
    assert {"ALT", "AST", "CREA", "BUN", "UA", "FBG"} <= codes
    assert next(row for row in rows if row.item_code == "FBG").value == 5.6
    assert next(row for row in rows if row.item_code == "CREA").record_date.isoformat() == "2026-05-11"

    from app.models.medical_exam import MedicalExam

    exam = db.query(MedicalExam).filter(MedicalExam.id == data["exam_id"]).one()
    assert payload["text"] not in (exam.notes or "")
    assert exam.notes == "从手工粘贴文本导入，原文未复制到备注。"


def test_import_medical_exam_from_text_error_does_not_leak_report(
    client,
    db,
    monkeypatch,
    caplog,
):
    """DB/provider exceptions must not echo health text into logs or API errors."""
    from app.services.data_collection.medical_exam_import import (
        MedicalExamImportService,
    )

    _, headers = _create_user(db)
    private_report = "private-MRI-report-content"

    def fail_import(*args, **kwargs):
        raise RuntimeError(private_report)

    monkeypatch.setattr(
        MedicalExamImportService,
        "import_from_text",
        fail_import,
    )

    with caplog.at_level("ERROR", logger="app.api.medical_exams"):
        resp = client.post(
            "/api/v1/medical-exams/import/text",
            json={"text": private_report},
            headers=headers,
        )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "入库服务暂不可用，请稍后重试"
    assert private_report not in caplog.text
    assert private_report not in resp.text
    assert "RuntimeError" in caplog.text


def test_import_image_requires_auth(client):
    resp = client.post("/api/v1/medical-exams/import/image")
    assert resp.status_code in (401, 422)  # 401 auth / 422 missing file


def test_import_image_rejects_non_image(client, db):
    _, headers = _create_user(db)
    resp = client.post(
        "/api/v1/medical-exams/import/image",
        files={"file": ("report.txt", b"not an image", "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "图片" in resp.json()["detail"]


def test_import_image_ocr_success(client, db):
    _, headers = _create_user(db)

    mock_ocr = {
        "report_type": "生化",
        "report_date": "2026-03-15",
        "institution": "测试医院",
        "items": [
            {
                "name": "丙氨酸氨基转移酶",
                "name_en": "ALT",
                "value": 25.0,
                "unit": "U/L",
                "reference_low": 0,
                "reference_high": 40,
                "is_abnormal": False,
            },
            {
                "name": "低密度脂蛋白",
                "name_en": "LDL-C",
                "value": 3.9,
                "unit": "mmol/L",
                "reference_low": 0,
                "reference_high": 3.37,
                "is_abnormal": True,
            },
        ],
        "conclusion": "血脂偏高,建议饮食调整",
    }

    with patch(
        "app.api.medical_exams.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        resp = client.post(
            "/api/v1/medical-exams/import/image",
            files={"file": ("report.jpg", _tiny_image_bytes(), "image/jpeg")},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items_count"] == 2
    assert data["abnormal_count"] == 1
    assert data["hospital_name"] == "测试医院"
    assert "exam_id" in data


def test_parse_image_preview_does_not_persist(client, db):
    """Mobile preview must never write health data before user confirmation."""
    from app.models.medical_exam import MedicalExam

    user, headers = _create_user(db)
    mock_ocr = {
        "report_type": "生化",
        "report_date": "2026-07-29",
        "institution": "测试医院",
        "items": [
            {
                "name": "丙氨酸氨基转移酶",
                "name_en": "ALT",
                "value": 25.0,
                "unit": "U/L",
                "reference_low": 0,
                "reference_high": 40,
                "is_abnormal": False,
            }
        ],
        "conclusion": "本响应只用于导入前复核",
    }

    with patch(
        "app.api.medical_exams.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        resp = client.post(
            "/api/v1/medical-exams/parse-image-preview",
            files={"file": ("report.jpg", _tiny_image_bytes(), "image/jpeg")},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["parsed_data"]["items"][0]["name_en"] == "ALT"
    assert (
        db.query(MedicalExam)
        .filter(MedicalExam.user_id == user.id)
        .count()
        == 0
    )


def test_create_medical_exam_idempotency_key_is_owner_scoped(
    client,
    db,
    sample_medical_exam_data,
):
    """Repeated confirmation returns one report; another owner gets their own."""
    from app.models.medical_exam import MedicalExam

    user, headers = _create_user(db)
    other, other_headers = _create_user(db)
    idempotency_key = f"mobile-medical-import-{uuid.uuid4().hex}"
    request_headers = {**headers, "Idempotency-Key": idempotency_key}

    first = client.post(
        "/api/v1/medical-exams",
        json=sample_medical_exam_data,
        headers=request_headers,
    )
    second = client.post(
        "/api/v1/medical-exams",
        json=sample_medical_exam_data,
        headers=request_headers,
    )
    other_result = client.post(
        "/api/v1/medical-exams",
        json=sample_medical_exam_data,
        headers={**other_headers, "Idempotency-Key": idempotency_key},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert other_result.status_code == 200, other_result.text
    assert first.json()["id"] == second.json()["id"]
    assert other_result.json()["id"] != first.json()["id"]
    assert (
        db.query(MedicalExam)
        .filter(MedicalExam.user_id == user.id)
        .count()
        == 1
    )
    assert (
        db.query(MedicalExam)
        .filter(MedicalExam.user_id == other.id)
        .count()
        == 1
    )


def test_import_image_pathology_narrative_persists_conclusion(client, db):
    """REST 上传路径: 病理报告(0 数值项, 只有诊断全文)入库,
    overall_assessment 逐字保留, value=null 病理项不进数值异常门, value_text 落库。"""
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    user, headers = _create_user(db)
    dx = "胃窦后壁黏膜慢性轻度炎伴糜烂,另见小片炎性坏死渗出物,HP-"
    mock_ocr = {
        "report_category": "narrative_report",
        "report_type": "pathology",
        "report_date": "2026-05-17",
        "institution": "测试医院病理科",
        "items": [
            {"name": "病理诊断", "value": None, "value_text": dx, "is_abnormal": True},
        ],
        "conclusion": dx,
    }

    with patch(
        "app.api.medical_exams.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        resp = client.post(
            "/api/v1/medical-exams/import/image",
            files={"file": ("path.jpg", _tiny_image_bytes(), "image/jpeg")},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["conclusion"] == dx
    assert data["abnormal_count"] == 0

    exam = db.query(MedicalExam).filter(MedicalExam.id == data["exam_id"]).one()
    assert exam.overall_assessment == dx
    item = db.query(MedicalExamItem).filter(MedicalExamItem.exam_id == exam.id).one()
    assert item.value is None
    assert item.value_text == dx
    assert item.is_abnormal == "normal"


def test_import_image_ocr_error_passes_through(client, db):
    _, headers = _create_user(db)
    with patch(
        "app.api.medical_exams.recognize_medical_report",
        new=AsyncMock(return_value={"error": "无法识别"}),
    ):
        resp = client.post(
            "/api/v1/medical-exams/import/image",
            files={"file": ("blurry.jpg", _tiny_image_bytes(), "image/jpeg")},
            headers=headers,
        )
    assert resp.status_code == 422
    assert "无法识别" in resp.json()["detail"]


def test_import_image_empty_items(client, db):
    _, headers = _create_user(db)
    with patch(
        "app.api.medical_exams.recognize_medical_report",
        new=AsyncMock(return_value={"report_type": "unknown", "items": []}),
    ):
        resp = client.post(
            "/api/v1/medical-exams/import/image",
            files={"file": ("report.png", _tiny_image_bytes("PNG"), "image/png")},
            headers=headers,
        )
    assert resp.status_code == 422


def test_import_image_rejects_oversized_file(client, db):
    """超过 MAX_IMAGE_BYTES 的图片 → 413"""
    from app.api.medical_exams import MAX_IMAGE_BYTES
    _, headers = _create_user(db)
    oversized = b"x" * (MAX_IMAGE_BYTES + 1024)
    resp = client.post(
        "/api/v1/medical-exams/import/image",
        files={"file": ("huge.jpg", oversized, "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 413
    assert "图片过大" in resp.json()["detail"]


def test_parse_pdf_preview_requires_auth(client):
    """/parse-pdf-preview 也要 auth (消耗 LLM vision 配额,不能裸奔)"""
    resp = client.post(
        "/api/v1/medical-exams/parse-pdf-preview",
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 401
