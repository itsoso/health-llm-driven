"""体检入库的每条 API 路径都必须把数值项归一化进 biomarker_observations。

2026-09-30 事故: 移动端「确认导入」走 POST /medical-exams/ (Idempotency-Key), 建了 exam + items +
medical_indicators 却从不调用 ingest_exam; /import/pdf、/import/image、PATCH /items/{id} 同样漏接,
整张体检在归一化层零行。数值均为合成值。
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.biomarker_observation import BiomarkerObservation
from tests.test_medical_exams import _create_user, _tiny_image_bytes

EXAM_DATE = "2026-02-09"
CONFIRMED_ITEMS = [
    {"item_name": "低密度脂蛋白-C", "value": 3.1, "unit": "mmol/L", "is_abnormal": "normal"},
    {"item_name": "极低密度脂蛋白-C", "value": 0.7, "unit": "mmol/L", "is_abnormal": "normal"},
    {"item_name": "谷氨酰转肽酶", "item_code": "GGT", "value": 72, "unit": "U/L", "is_abnormal": "high"},
    {"item_name": "肾小球滤过率(EPI-cr)", "value": 96, "unit": "ml/min", "is_abnormal": "normal"},
    {"item_name": "肌酐", "item_code": "CREA", "value": 83, "unit": "μmol/L", "is_abnormal": "normal"},
    {"item_name": "叶酸", "value": 21.7, "unit": "ng/mL", "is_abnormal": "high"},  # registry 外: 不入归一化层
]


def _observations(db, user_id):
    db.expire_all()
    rows = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user_id).all()
    return {(r.code, r.normalized_value) for r in rows}


def _confirm(client, headers, items):
    return client.post(
        "/api/v1/medical-exams",
        json={"exam_date": EXAM_DATE, "exam_type": "comprehensive", "items": items},
        headers={**headers, "Idempotency-Key": f"mobile-medical-import-{uuid.uuid4().hex}"},
    )


def test_confirm_import_ingests_biomarkers(client, db):
    user, headers = _create_user(db)

    resp = _confirm(client, headers, CONFIRMED_ITEMS)

    assert resp.status_code == 200, resp.text
    assert _observations(db, user.id) == {("lipid_ldl", 3.1), ("GGT", 72), ("egfr", 96), ("CREA", 83)}
    ggt = db.query(BiomarkerObservation).filter(
        BiomarkerObservation.user_id == user.id, BiomarkerObservation.code == "GGT"
    ).one()
    assert ggt.abnormal is True and ggt.observed_at.date().isoformat() == EXAM_DATE


def test_confirm_import_keeps_abbreviated_and_english_names(client, db):
    """别名表没收录的写法靠 item_code 提示归一, 不能整张体检零行; 之后的对账也不能删掉它们。"""
    from app.services.biomarker_sync import sync_indicators_to_biomarkers
    user, headers = _create_user(db)
    items = [
        {"item_name": "CRE", "item_code": "CREA", "value": 150, "unit": "μmol/L", "is_abnormal": "high"},
        {"item_name": "Alanine aminotransferase", "item_code": "ALT", "value": 118, "unit": "U/L",
         "is_abnormal": "high"},
        {"item_name": "eGFRcr", "item_code": "egfr", "value": 27, "unit": "mL/min/1.73m2", "is_abnormal": "low"},
        {"item_name": "UricAcid", "item_code": "UA", "value": 600, "unit": "μmol/L", "is_abnormal": "high"},
    ]

    assert _confirm(client, headers, items).status_code == 200
    expected = {("CREA", 150), ("ALT", 118), ("egfr", 27), ("UA", 600)}
    assert _observations(db, user.id) == expected
    sync_indicators_to_biomarkers(db, user.id)
    assert _observations(db, user.id) == expected


def test_confirm_import_survives_biomarker_ingest_failure(client, db, monkeypatch):
    """归一化是旁路: 它失败不能让确认导入失败, 会话也必须仍可用 (响应要序列化 items)。"""
    import app.services.biomarker_service as biomarker_service

    def _boom(*_args, **_kwargs):
        raise RuntimeError("normalizer down")

    monkeypatch.setattr(biomarker_service, "ingest_exam", _boom)
    user, headers = _create_user(db)

    resp = client.post(
        "/api/v1/medical-exams",
        json={"exam_date": EXAM_DATE, "exam_type": "comprehensive", "items": CONFIRMED_ITEMS[:1]},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1
    assert _observations(db, user.id) == set()


def test_confirm_import_invalidates_twin(client, db, monkeypatch):
    """rank7 写入闸: 确认导入是唯一没让 Twin/预生成回答失效的体检写入路径。"""
    import app.twin.cache as twin_cache

    calls = []
    monkeypatch.setattr(twin_cache, "invalidate_twin", lambda user_id: calls.append(user_id))
    user, headers = _create_user(db)

    resp = _confirm(client, headers, CONFIRMED_ITEMS[:1])

    assert resp.status_code == 200, resp.text
    assert calls == [user.id]


def test_pdf_import_ingests_biomarkers(client, db):
    user, headers = _create_user(db)
    parsed = {"exam_date": EXAM_DATE, "exam_type": "comprehensive", "items": CONFIRMED_ITEMS[:3],
              "conclusions": []}

    with patch("app.api.medical_exams.pdf_parser.parse_pdf", return_value=parsed):
        resp = client.post(
            "/api/v1/medical-exams/import/pdf",
            files={"file": ("report.pdf", b"%PDF-1.4\n%synthetic\n", "application/pdf")},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    assert _observations(db, user.id) == {("lipid_ldl", 3.1), ("GGT", 72)}


def test_image_import_ingests_biomarkers(client, db):
    user, headers = _create_user(db)
    mock_ocr = {
        "report_type": "生化",
        "report_date": EXAM_DATE,
        "items": [
            {"name": "低密度脂蛋白-C", "name_en": "LDL-C", "value": 3.1, "unit": "mmol/L", "is_abnormal": False},
            {"name": "极低密度脂蛋白-C", "name_en": "VLDL-C", "value": 0.7, "unit": "mmol/L",
             "is_abnormal": False},
        ],
    }

    with patch("app.api.medical_exams.recognize_medical_report", new=AsyncMock(return_value=mock_ocr)):
        resp = client.post(
            "/api/v1/medical-exams/import/image",
            files={"file": ("report.jpg", _tiny_image_bytes(), "image/jpeg")},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    assert _observations(db, user.id) == {("lipid_ldl", 3.1)}


def test_item_correction_updates_biomarker(client, db):
    user, headers = _create_user(db)
    created = _confirm(client, headers, CONFIRMED_ITEMS[2:3])
    assert created.status_code == 200, created.text
    item_id = created.json()["items"][0]["id"]

    resp = client.patch(f"/api/v1/medical-exams/items/{item_id}", json={"value": 66}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert _observations(db, user.id) == {("GGT", 66)}


# ── 端到端: 确认导入 → Twin 取数 → Safety Guardian。名字/单位写法没认出来 ≠ 没有这个值 ──

SAFETY_CASES = {
    "egfrcr_flagged": ([{"item_name": "eGFRcr", "item_code": "egfr", "value": 25, "unit": "mL/min/1.73m2",
                         "is_abnormal": "low"}], ("labs.egfr_decline", "HIGH")),
    "egfr_dash_unit_flagged": ([{"item_name": "eGFR", "value": 25, "unit": "-", "is_abnormal": "low"}],
                               ("labs.egfr_decline", "HIGH")),
    "ldl_dash_unit_flagged": ([{"item_name": "低密度脂蛋白胆固醇", "value": 5.3, "unit": "-",
                                "is_abnormal": "high"}], ("labs.ldl_high", "HIGH")),
    "ua_dash_unit_unflagged": ([{"item_name": "尿酸", "value": 455, "unit": "-", "is_abnormal": "normal"}],
                               ("labs.uric_acid_high", "MEDIUM")),
    "hba1c_ngsp_unflagged": ([{"item_name": "糖化血红蛋白", "value": 6.3, "unit": "%(NGSP)",
                               "is_abnormal": "normal"}], ("labs.hba1c_prediabetes", "MEDIUM")),
    "control_ldl_mmol": ([{"item_name": "低密度脂蛋白胆固醇", "value": 5.3, "unit": "mmol/L",
                           "is_abnormal": "high"}], ("labs.ldl_high", "HIGH")),
}


@pytest.mark.parametrize("case", list(SAFETY_CASES))
def test_confirm_import_to_safety_alert(client, db, case):
    from app.agents.safety_guardian import evaluate_safety
    from app.twin.builder import _fill_collectors
    from app.twin.schema import HealthTwin, TwinMeta

    items, expected = SAFETY_CASES[case]
    user, headers = _create_user(db)
    assert _confirm(client, headers, items).status_code == 200

    twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
    _fill_collectors(db, user.id, twin, set())
    alerts = {(a.rule_id, a.severity.name) for a in evaluate_safety(twin).alerts if a.category == "labs"}

    assert expected in alerts
