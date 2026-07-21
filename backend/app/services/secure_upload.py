"""Bounded upload readers and content-signature validation."""
from __future__ import annotations

import base64
import binascii
import io

from PIL import Image, UnidentifiedImageError


class UploadTooLarge(ValueError):
    pass


class UploadContentInvalid(ValueError):
    pass


def decode_base64_limited(value: str, *, max_bytes: int) -> bytes:
    """Strictly decode a raw base64 string or data URL with a decoded limit."""
    payload = str(value or "").strip()
    if payload.startswith("data:"):
        if "," not in payload:
            raise UploadContentInvalid("Base64 data URL 格式无效")
        payload = payload.split(",", 1)[1]
    if not payload:
        raise UploadContentInvalid("Base64 内容为空")
    if len(payload) > ((max_bytes + 2) // 3) * 4 + 4:
        raise UploadTooLarge("上传文件超过大小限制")
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UploadContentInvalid("Base64 内容无效") from exc
    if len(decoded) > max_bytes:
        raise UploadTooLarge("上传文件超过大小限制")
    return decoded


async def read_upload_limited(
    upload,
    *,
    max_bytes: int,
    chunk_size: int = 256 * 1024,
) -> bytes:
    """Read an UploadFile incrementally and stop at max_bytes + 1."""
    if max_bytes < 1 or chunk_size < 1:
        raise ValueError("invalid_upload_limit")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(chunk_size, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLarge("上传文件超过大小限制")
        chunks.append(chunk)
    return b"".join(chunks)


def detect_file_kind(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"mif1",
        b"msf1",
    }:
        return "heic"
    return None


def validate_pdf_bytes(data: bytes) -> None:
    if detect_file_kind(data) != "pdf":
        raise UploadContentInvalid("文件真实格式不是 PDF")


def validate_csv_bytes(data: bytes) -> None:
    if b"\x00" in data:
        raise UploadContentInvalid("CSV 包含二进制内容")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadContentInvalid("CSV 必须使用 UTF-8 编码") from exc


def decode_utf8_text(data: bytes, *, label: str = "文本文件") -> str:
    """Decode bounded text uploads without accepting binary/NUL payloads."""
    if b"\x00" in data:
        raise UploadContentInvalid(f"{label}包含二进制内容")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadContentInvalid(f"{label}必须使用 UTF-8 编码") from exc


def validate_image_bytes(
    data: bytes,
    *,
    declared_extension: str | None = None,
    max_pixels: int = 40_000_000,
) -> str:
    kind = detect_file_kind(data)
    if kind not in {"jpeg", "png", "gif", "webp", "heic"}:
        raise UploadContentInvalid("文件真实格式不是受支持的图片")

    declared = str(declared_extension or "").strip().lower().lstrip(".")
    if declared == "jpg":
        declared = "jpeg"
    if declared and declared != kind:
        raise UploadContentInvalid("图片扩展名与真实格式不一致")

    # HEIC decoding is delegated to the platform/Vision provider; the ISO BMFF
    # signature above is still mandatory. Pillow validates all local formats.
    if kind != "heic":
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if width < 1 or height < 1 or width * height > max_pixels:
                    raise UploadContentInvalid("图片像素尺寸超过限制")
                image.verify()
        except UploadContentInvalid:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise UploadContentInvalid("图片内容损坏或无法解析") from exc
    return kind
