from datetime import date
from unittest.mock import AsyncMock, patch

from app.models.family_health import MedicalIndicator
from app.services.agent_executor import AgentExecutor
from app.services.medical_text_parser import parse_lab_indicators_from_text


def test_parse_lab_indicators_from_text_extracts_liver_kidney_panel():
    text = """
    最新肝肾功能：谷丙转氨酶 ALT 47 U/L ↑，谷草转氨酶 AST 28 U/L，
    谷氨酰转肽酶 GGT 78 U/L ↑，胆碱酯酶 CHE 8340 U/L，
    总胆红素 TBIL 12.4 μmol/L，直接胆红素 DBIL 3.2 μmol/L，
    肌酐 Cr 68 μmol/L，尿素氮 BUN 5.1 mmol/L，尿酸 UA 360 μmol/L。
    """

    items = parse_lab_indicators_from_text(text)
    by_code = {item["item_code"]: item for item in items}

    assert by_code["ALT"]["value"] == 47
    assert by_code["ALT"]["category"] == "liver_function"
    assert by_code["ALT"]["is_abnormal"] == "high"
    assert by_code["GGT"]["value"] == 78
    assert by_code["GGT"]["is_abnormal"] == "high"
    assert by_code["TBIL"]["value"] == 12.4
    assert by_code["DBIL"]["value"] == 3.2
    assert by_code["CREA"]["value"] == 68
    assert by_code["BUN"]["unit"] == "mmol/L"
    assert by_code["UA"]["value"] == 360


def test_agent_upload_medical_exam_text_persists_medical_indicators(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    from app.services.data_collection.medical_exam_import import MedicalExamImportService

    text = "ALT 47 U/L ↑，GGT 78 U/L ↑，肌酐 Cr 68 μmol/L，尿素氮 BUN 5.1 mmol/L，尿酸 UA 360 μmol/L"
    exam = MedicalExamImportService.import_from_text(
        db,
        user_id=user.id,
        text=text,
        exam_date=date(2026, 5, 17),
        source="agent_text",
    )

    rows = db.query(MedicalIndicator).filter(MedicalIndicator.user_id == user.id).all()
    codes = {row.item_code for row in rows}

    assert exam.id is not None
    assert {"ALT", "GGT", "CREA", "BUN", "UA"} <= codes
    ggt = next(row for row in rows if row.item_code == "GGT")
    assert ggt.value == 78
    assert ggt.is_abnormal is True
    assert ggt.source == "agent_text"


async def test_agent_chat_image_medical_report_auto_persists_indicators(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    mock_ocr = {
        "report_type": "肝肾功能",
        "report_date": "2026-05-17",
        "institution": "测试医院",
        "items": [
            {"name": "谷丙转氨酶", "name_en": "ALT", "value": 47, "unit": "U/L", "is_abnormal": True},
            {"name": "谷氨酰转肽酶", "name_en": "GGT", "value": 78, "unit": "U/L", "is_abnormal": True},
            {"name": "肌酐", "name_en": "Cr", "value": 68, "unit": "μmol/L", "is_abnormal": False},
        ],
    }

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        note = await executor._try_import_medical_report_images(
            user.id,
            [{"base64": "fake", "type": "jpeg"}],
        )

    rows = db.query(MedicalIndicator).filter(MedicalIndicator.user_id == user.id).all()
    codes = {row.item_code for row in rows}
    assert "已将图片中的 3 项化验指标写入系统" in note
    assert {"ALT", "GGT", "CREA"} <= codes
    assert next(row for row in rows if row.item_code == "GGT").source == "agent_image_ocr"
