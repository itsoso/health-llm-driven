from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from app.models.family_health import MedicalIndicator
from app.services.agent_executor import AgentExecutor
from app.services.exam_packages import create_indicator_from_item
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


def test_create_indicator_prefers_explicit_item_code_over_fuzzy_name():
    indicator = create_indicator_from_item(
        user_id=3,
        exam_id=18,
        record_date=date(2026, 5, 11),
        item_dict={
            "item_name": "尿素氮/肌酐",
            "item_code": "BUN_CREA_RATIO",
            "value": 14.0,
        },
        source="manual_backfill",
    )

    assert indicator.item_code == "BUN_CREA_RATIO"
    assert indicator.name_en == "BUN_CREA_RATIO"


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
            persist=True,
        )

    rows = db.query(MedicalIndicator).filter(MedicalIndicator.user_id == user.id).all()
    codes = {row.item_code for row in rows}
    assert "已从图片中识别 3 项化验指标并写入系统" in note
    assert {"ALT", "GGT", "CREA"} <= codes
    assert next(row for row in rows if row.item_code == "GGT").source == "agent_image_ocr"


# ---------------------------------------------------------------------------
# 病理/叙述性报告入库 (exam_id=42 病理诊断全文丢失的根因回归)
# ---------------------------------------------------------------------------

_PATHOLOGY_DX = "胃窦后壁黏膜慢性轻度炎伴糜烂,另见小片炎性坏死渗出物,HP-"


async def test_agent_chat_pathology_report_persists_full_conclusion(db, auth_user_and_headers):
    """病理报告(0 数值项, 只有诊断全文)必须入库, overall_assessment 逐字保留,
    且 value=null 的病理项绝不被当数值异常上报。"""
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    mock_ocr = {
        "report_category": "narrative_report",
        "report_type": "pathology",
        "report_date": "2026-05-17",
        "institution": "测试医院病理科",
        "items": [
            {
                "name": "病理诊断",
                "value": None,
                "value_text": _PATHOLOGY_DX,
                "is_abnormal": True,  # OCR 误标, 落库时必须被压回 normal
            }
        ],
        "conclusion": _PATHOLOGY_DX,
    }

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        note = await executor._try_import_medical_report_images(
            user.id,
            [{"base64": "fake", "type": "jpeg"}],
            persist=True,
        )

    # 1) exam 入库, overall_assessment 与 OCR conclusion 字符串相等 (相等非包含)
    exam = db.query(MedicalExam).filter(MedicalExam.user_id == user.id).one()
    assert exam.overall_assessment == _PATHOLOGY_DX
    assert exam.exam_type == "pathology"

    # 2) value=null 的病理项不被当数值异常: MedicalExamItem.is_abnormal 压回 normal
    exam_items = db.query(MedicalExamItem).filter(MedicalExamItem.exam_id == exam.id).all()
    assert len(exam_items) == 1
    path_item = exam_items[0]
    assert path_item.value is None
    assert path_item.value_text == _PATHOLOGY_DX
    assert path_item.is_abnormal == "normal"

    # 3) MedicalIndicator 侧同样不标异常, value_text 逐字保留
    indicators = db.query(MedicalIndicator).filter(MedicalIndicator.user_id == user.id).all()
    assert len(indicators) == 1
    assert indicators[0].is_abnormal is False
    assert indicators[0].value is None
    assert indicators[0].value_text == _PATHOLOGY_DX

    # 4) 回显 note 逐字包含诊断原文, 不谎报"N 项化验指标"
    assert _PATHOLOGY_DX in note
    assert "3 项化验指标" not in note
    assert "0 项化验指标" not in note


async def test_agent_chat_conclusion_only_report_still_persists(db, auth_user_and_headers):
    """只有 conclusion、无 items 的自由文本报告仍入库并落 overall_assessment。"""
    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    concl = "双肺纹理增粗,未见明显实质性病灶,建议随访。"
    mock_ocr = {
        "report_category": "narrative_report",
        "report_type": "imaging",
        "items": [],
        "conclusion": concl,
    }

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        note = await executor._try_import_medical_report_images(
            user.id,
            [{"base64": "fake", "type": "jpeg"}],
            persist=True,
        )

    exam = db.query(MedicalExam).filter(MedicalExam.user_id == user.id).one()
    assert exam.overall_assessment == concl
    assert note is not None
    assert concl in note


async def test_agent_chat_mri_report_uses_user_relative_date_and_produces_receipt(
    db,
    auth_user_and_headers,
):
    """Attachment preprocessing is a real write and must join the turn receipt ledger."""
    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_turn_user_message = "记录下来 昨天的MRI"
    executor._start_agent_kernel_turn(
        user_id=user.id,
        message=executor._current_turn_user_message,
        channel="typed",
    )
    conclusion = "右膝内侧半月板后角损伤，关节腔少量积液。"
    mock_ocr = {
        "report_category": "narrative_report",
        "report_type": "imaging",
        "report_date": executor._agent_kernel_reference_now().date().isoformat(),
        "items": [],
        "conclusion": conclusion,
    }

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        note = await executor._try_import_medical_report_images(
            user.id,
            [{"base64": "fake", "type": "jpeg"}],
            persist=True,
        )

    exam = db.query(MedicalExam).filter(MedicalExam.user_id == user.id).one()
    assert exam.exam_date == executor._agent_kernel_reference_now().date() - timedelta(days=1)
    assert conclusion in note
    assert executor._turn_attachment_write_receipts == [
        {
            "operation_id": (
                "medical-report-image:"
                "0536d3e9b18e52fa27c2951938d4d922"
            ),
            "status": "verified",
            "resource_type": "medical_exam",
            "resource_id": str(exam.id),
            "verified": True,
            "verification_scope": "persistence_only",
            "content_verified": False,
        }
    ]
    assert exam.source_fingerprint
    assert conclusion not in (exam.notes or "")


async def test_agent_chat_reuses_same_medical_report_image(db, auth_user_and_headers):
    """Re-analyzing the same attachment must reuse its canonical exam."""
    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_turn_user_message = "记录并分析这份 MRI"
    conclusion = "右膝内侧半月板后角损伤，关节腔少量积液。"
    mock_ocr = {
        "report_category": "narrative_report",
        "report_type": "imaging",
        "items": [],
        "conclusion": conclusion,
    }
    image = [{"base64": "same-mri-image", "type": "jpeg"}]

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        first_note = await executor._try_import_medical_report_images(
            user.id,
            image,
            persist=True,
        )
        first_receipt = dict(executor._turn_attachment_write_receipts[0])
        executor._turn_attachment_write_receipts = []
        second_note = await executor._try_import_medical_report_images(
            user.id,
            image,
            persist=True,
        )

    exams = db.query(MedicalExam).filter(MedicalExam.user_id == user.id).all()
    assert len(exams) == 1
    assert first_note == second_note
    assert executor._turn_attachment_write_receipts == [first_receipt]


async def test_agent_chat_reuses_same_image_across_base64_wrappers(
    db,
    auth_user_and_headers,
):
    """A data-URI wrapper must not create a second record for identical bytes."""
    import base64

    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_turn_user_message = "记录并分析这份 MRI"
    encoded = base64.b64encode(b"same-mri-image-bytes").decode("ascii")
    mock_ocr = {
        "report_category": "narrative_report",
        "report_type": "imaging",
        "items": [],
        "conclusion": "右膝内侧半月板后角损伤。",
    }

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        await executor._try_import_medical_report_images(
            user.id,
            [{"base64": encoded, "type": "jpeg"}],
            persist=True,
        )
        executor._turn_attachment_write_receipts = []
        await executor._try_import_medical_report_images(
            user.id,
            [{"base64": f"data:image/jpeg;base64,{encoded}", "type": "jpeg"}],
            persist=True,
        )

    assert (
        db.query(MedicalExam)
        .filter(MedicalExam.user_id == user.id)
        .count()
        == 1
    )


async def test_agent_chat_analysis_only_medical_image_does_not_persist(
    db,
    auth_user_and_headers,
):
    """分析附件不是写入授权；OCR 可用于回答，但不得旁路 CapabilityPolicy 入库。"""
    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_turn_user_message = "帮我看看这份 MRI，有问题吗？不要保存"
    conclusion = "右膝内侧半月板后角损伤，关节腔少量积液。"
    mock_ocr = {
        "report_category": "narrative_report",
        "report_type": "imaging",
        "items": [],
        "conclusion": conclusion,
    }

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        note = await executor._try_import_medical_report_images(
            user.id,
            [{"base64": "analysis-only", "type": "jpeg"}],
            persist=False,
        )

    assert conclusion in note
    assert "尚未保存" in note
    assert executor._turn_attachment_write_receipts == []
    assert db.query(MedicalExam).filter(MedicalExam.user_id == user.id).count() == 0


def test_medical_report_intent_separates_record_only_from_analysis(db):
    from app.services.agent_executor import (
        _medical_report_analysis_requested,
    )

    executor = AgentExecutor(db)
    snapshot = executor._start_agent_kernel_turn(
        user_id=1,
        message="分析我的 MRI 报告，不要保存",
        channel="typed",
    )
    assert snapshot.intent.is_write is False
    assert _medical_report_analysis_requested(
        "帮我看看 MRI 严重吗？",
        persisted=True,
    )
    assert not _medical_report_analysis_requested(
        "记录下来昨天的 MRI",
        persisted=True,
    )


async def test_agent_chat_no_items_no_conclusion_skips(db, auth_user_and_headers):
    """既无数值项又无诊断结论 → 不入库、不产生空噪声记录 (准入门挡非报告照片)。"""
    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    mock_ocr = {"report_type": "其他", "items": [], "conclusion": ""}

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value=mock_ocr),
    ):
        note = await executor._try_import_medical_report_images(
            user.id,
            [{"base64": "fake", "type": "jpeg"}],
            persist=True,
        )

    assert note is None
    assert db.query(MedicalExam).filter(MedicalExam.user_id == user.id).count() == 0


async def test_agent_chat_ocr_error_skips(db, auth_user_and_headers):
    """OCR error 结果 → 不入库、不产生记录。"""
    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    with patch(
        "app.services.ai.medical_report_ocr.recognize_medical_report",
        new=AsyncMock(return_value={"error": "无法识别"}),
    ):
        note = await executor._try_import_medical_report_images(
            user.id,
            [{"base64": "fake", "type": "jpeg"}],
            persist=True,
        )

    assert note is None
    assert db.query(MedicalExam).filter(MedicalExam.user_id == user.id).count() == 0


def test_import_from_items_accepts_narrative_only(db, auth_user_and_headers):
    """import_from_items: items 空但 overall_assessment 非空 → 入库落 overall_assessment。"""
    from app.services.data_collection.medical_exam_import import MedicalExamImportService

    user, _headers = auth_user_and_headers
    exam = MedicalExamImportService.import_from_items(
        db,
        user_id=user.id,
        items_data=[],
        exam_type="pathology",
        overall_assessment=_PATHOLOGY_DX,
    )
    assert exam.id is not None
    assert exam.overall_assessment == _PATHOLOGY_DX


def test_import_from_items_rejects_empty_and_no_narrative(db, auth_user_and_headers):
    """import_from_items: 既无 items 又无 overall_assessment → 抛错, 不建空壳记录。"""
    import pytest as _pytest
    from app.services.data_collection.medical_exam_import import MedicalExamImportService

    user, _headers = auth_user_and_headers
    with _pytest.raises(ValueError):
        MedicalExamImportService.import_from_items(
            db,
            user_id=user.id,
            items_data=[],
        )
