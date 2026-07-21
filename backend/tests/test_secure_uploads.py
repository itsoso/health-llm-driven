import io

import pytest
from starlette.datastructures import UploadFile


@pytest.mark.asyncio
async def test_bounded_upload_reader_rejects_before_unbounded_read():
    from app.services.secure_upload import UploadTooLarge, read_upload_limited

    upload = UploadFile(filename="large.pdf", file=io.BytesIO(b"x" * 17))
    with pytest.raises(UploadTooLarge):
        await read_upload_limited(upload, max_bytes=16, chunk_size=8)


def test_base64_decoder_is_strict_and_bounded():
    from app.services.secure_upload import (
        UploadContentInvalid,
        UploadTooLarge,
        decode_base64_limited,
    )

    with pytest.raises(UploadContentInvalid, match="Base64"):
        decode_base64_limited("not+valid===", max_bytes=20)
    with pytest.raises(UploadTooLarge):
        decode_base64_limited("eHh4eA==", max_bytes=3)


def test_agent_attachment_validation_rejects_spoofed_pdf():
    import base64

    from app.api.agent import AgentRequest, _validate_agent_attachments
    from app.services.secure_upload import UploadContentInvalid

    request = AgentRequest(
        message="分析附件",
        file_name="report.pdf",
        file_base64=base64.b64encode(b"not-pdf").decode(),
    )
    with pytest.raises(UploadContentInvalid, match="PDF"):
        _validate_agent_attachments(request)


def test_image_validation_rejects_extension_spoofing():
    from app.services.secure_upload import UploadContentInvalid, validate_image_bytes

    with pytest.raises(UploadContentInvalid, match="真实格式"):
        validate_image_bytes(b"%PDF-1.7\nnot-an-image", declared_extension="jpg")


def test_pdf_validation_uses_magic_not_filename():
    from app.services.secure_upload import UploadContentInvalid, validate_pdf_bytes

    with pytest.raises(UploadContentInvalid, match="PDF"):
        validate_pdf_bytes(b"not a pdf")


def test_text_upload_rejects_binary_or_non_utf8_content():
    from app.services.secure_upload import UploadContentInvalid, decode_utf8_text

    with pytest.raises(UploadContentInvalid, match="二进制"):
        decode_utf8_text(b"title\x00payload")
    with pytest.raises(UploadContentInvalid, match="UTF-8"):
        decode_utf8_text(b"\xff\xfe")


def test_image_validation_rejects_decompression_bomb(monkeypatch):
    from app.services.secure_upload import UploadContentInvalid, validate_image_bytes

    class _Image:
        format = "JPEG"
        size = (20_000, 20_000)

        def verify(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("PIL.Image.open", lambda *_args, **_kwargs: _Image())
    with pytest.raises(UploadContentInvalid, match="像素"):
        validate_image_bytes(b"\xff\xd8\xfffake", declared_extension="jpg")


def test_apple_health_xml_rejects_doctype_entities():
    from app.services.device_adapters.apple import AppleHealthAdapter

    payload = """<!DOCTYPE x [<!ENTITY a 'health'>]><HealthData>&a;</HealthData>"""
    with pytest.raises(ValueError, match="不安全"):
        AppleHealthAdapter.parse_health_xml(payload)


def test_apple_health_xml_enforces_record_quota(monkeypatch):
    from app.services.device_adapters.apple import AppleHealthAdapter

    monkeypatch.setattr(AppleHealthAdapter, "MAX_XML_RECORDS", 1)
    payload = """<HealthData>
      <Record type="HKQuantityTypeIdentifierStepCount" value="1"
        startDate="2026-07-01 00:00:00 +0000" endDate="2026-07-01 00:01:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierStepCount" value="1"
        startDate="2026-07-01 00:02:00 +0000" endDate="2026-07-01 00:03:00 +0000"/>
    </HealthData>"""
    with pytest.raises(ValueError, match="记录数"):
        AppleHealthAdapter.parse_health_xml(payload)
