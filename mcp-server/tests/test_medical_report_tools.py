"""Synthetic HTTP contracts for authenticated, read-only medical report tools."""
import ast
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import query


@pytest.fixture
def client():
    with patch.object(query, "get_client") as factory:
        value = AsyncMock()
        factory.return_value = value
        yield value


@pytest.mark.asyncio
async def test_report_list_marks_truncation_and_owned_detail(client):
    text = "合成报告前缀" * 120 + "TAIL_GRADE"
    client.get.return_value = [{"id": 41, "exam_date": "2026-10-01",
                                "overall_assessment": text, "items": []}]
    result = json.loads(await query.get_medical_exam_reports(limit=1, skip=2))
    client.get.assert_called_once_with("/medical-exams/me", params={"limit": 1, "skip": 2})
    assert result["status"] == "ok"
    assert result["next_skip"] == 3
    assert result["may_have_more"] is True
    report = result["reports"][0]
    assert report["overall_assessment_truncated"] is True
    assert "TAIL_GRADE" not in report["overall_assessment"]
    assert report["detail_tool"] == "get_medical_exam_report"
    assert report["detail_path"] == "/medical-exams/me/41"
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_report_detail_preserves_full_text_and_source(client):
    text = "合成文本" * 200 + "TAIL_GRADE"
    payload = {"id": 41, "overall_assessment": text, "items": [],
               "source": "synthetic_ocr", "conclusions": ["合成结论"]}
    client.get.return_value = payload
    result = json.loads(await query.get_medical_exam_report(41))
    assert result["status"] == "ok"
    assert result["report"] == payload
    assert result["original_image_verified"] is False
    assert "OCR" in result["evidence_note"]
    client.get.assert_called_once_with("/medical-exams/me/41")
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_short_and_empty_assessments_are_not_marked_truncated(client):
    client.get.return_value = [{"id": 1, "overall_assessment": "合成摘要"},
                               {"id": 2, "overall_assessment": None}]
    result = json.loads(await query.get_medical_exam_reports())
    assert all(r["overall_assessment_truncated"] is False for r in result["reports"])
    assert result["next_skip"] is None
    assert result["may_have_more"] is False


@pytest.mark.asyncio
async def test_empty_page_is_not_claim_of_no_medical_history(client):
    client.get.return_value = []
    result = json.loads(await query.get_medical_exam_reports(skip=20))
    assert result["status"] == "ok"
    assert result["reports"] == []
    assert "本页" in result["message"]
    assert "无病史" not in result["message"]


@pytest.mark.parametrize("payload", [{"error": "private diagnostic"}, {"detail": "Not found"},
                                     {"id": 1}, {"id": 1, "overall_assessment": []}, None, "bad"])
@pytest.mark.asyncio
async def test_api_error_is_explicit_failure_not_empty_list(client, payload):
    client.get.return_value = payload
    for call in (query.get_medical_exam_reports(), query.get_medical_exam_report(1)):
        result = json.loads(await call)
        assert result["status"] == "error"
        assert "reports" not in result
        assert "读取失败" in result["message"]
        assert "private diagnostic" not in json.dumps(result)


@pytest.mark.parametrize("exam_id", [0, -1, True, "1/../user/2", "https://example.invalid", 1.5])
@pytest.mark.asyncio
async def test_detail_rejects_nonpositive_or_noninteger_id_before_http(client, exam_id):
    with pytest.raises(ValueError):
        await query.get_medical_exam_report(exam_id)
    client.get.assert_not_called()


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"limit": True}, {"skip": -1}, {"skip": "1"}])
@pytest.mark.asyncio
async def test_list_rejects_invalid_pagination_before_http(client, kwargs):
    with pytest.raises(ValueError):
        await query.get_medical_exam_reports(**kwargs)
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_detail_wrong_identity_is_error(client):
    client.get.return_value = {"id": 2, "overall_assessment": "synthetic"}
    assert json.loads(await query.get_medical_exam_report(1))["status"] == "error"


@pytest.mark.asyncio
async def test_report_tools_use_existing_bearer_client_and_get_only():
    import httpx
    from client import HealthAPIClient

    requests = []
    def respond(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-test-token"
        assert request.method == "GET"
        report = {"id": 7, "overall_assessment": "合成 OCR 摘要", "items": []}
        return httpx.Response(200, json=[report] if request.url.path.endswith("/me") else report)

    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    authenticated = HealthAPIClient(base_url="https://synthetic.invalid/api/v1", token="synthetic-test-token")
    with patch.object(query, "get_client", return_value=authenticated), patch(
        "client.httpx.AsyncClient", side_effect=lambda **kwargs: real_async_client(transport=transport, **kwargs),
    ):
        assert json.loads(await query.get_medical_exam_reports())["status"] == "ok"
        assert json.loads(await query.get_medical_exam_report(7))["status"] == "ok"
    assert [r.url.path for r in requests] == ["/api/v1/medical-exams/me", "/api/v1/medical-exams/me/7"]


def test_both_read_tools_are_registered_and_have_no_user_or_url_arguments():
    source = Path(__file__).resolve().parents[1] / "server.py"
    tree = ast.parse(source.read_text())
    registered = {node.value.args[0].id for node in tree.body
                  if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                  and isinstance(node.value.func, ast.Call) and node.value.args
                  and isinstance(node.value.args[0], ast.Name)}
    assert {"get_medical_exam_reports", "get_medical_exam_report"} <= registered
    import inspect
    assert set(inspect.signature(query.get_medical_exam_reports).parameters) == {"limit", "skip"}
    assert set(inspect.signature(query.get_medical_exam_report).parameters) == {"exam_id"}
