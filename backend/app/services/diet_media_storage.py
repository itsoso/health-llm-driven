"""Private storage primitives for diet photos.

The functions here deliberately accept raw bytes/base64 or an already-owned
chat image.  They never fetch arbitrary URLs, which keeps photo ownership at
the storage boundary rather than trusting a model or client supplied path.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import uuid
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class StoredDietPhoto:
    storage_key: str
    file_path: str
    content_sha256: str
    media_type: str


def store_diet_image(
    image_base64: str,
    image_type: str | None,
    owner_id: int,
) -> StoredDietPhoto:
    """Validate and atomically publish an owner-scoped diet image."""
    from app.api.upload import (
        ALLOWED_EXTENSIONS,
        UPLOAD_DIR,
        ensure_upload_dir,
        generate_filename,
        validate_image_content,
    )

    normalized_type = (image_type or "jpeg").lower()
    if normalized_type == "jpg":
        normalized_type = "jpeg"
    if normalized_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的饮食图片类型")

    encoded = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
    try:
        image_data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="饮食图片编码无效") from exc
    validate_image_content(image_data)

    ensure_upload_dir()
    filename = generate_filename(normalized_type, "diet", owner_id)
    filepath = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    temporary = f"{filepath}.uploading-{uuid.uuid4().hex}"
    try:
        with open(temporary, "wb") as image_file:
            image_file.write(image_data)
        os.replace(temporary, filepath)
    except Exception:
        remove_diet_image_file(temporary)
        raise
    return StoredDietPhoto(
        storage_key=f"/api/v1/upload/files/{filename}",
        file_path=filepath,
        content_sha256=hashlib.sha256(image_data).hexdigest(),
        media_type=f"image/{normalized_type}",
    )


def persist_diet_image(
    image_base64: str,
    image_type: str | None,
    owner_id: int,
) -> tuple[str, str]:
    """Compatibility wrapper retained for the existing Diet REST endpoint."""
    stored = store_diet_image(image_base64, image_type, owner_id)
    return stored.storage_key, stored.file_path


def copy_owned_chat_image_to_diet(
    chat_image_url: str,
    owner_id: int,
) -> StoredDietPhoto:
    """Copy only an owner's persisted chat image into the diet namespace."""
    from app.services.chat_utils import read_owned_chat_image_data_uri

    data_uri = read_owned_chat_image_data_uri(chat_image_url, owner_id)
    try:
        header, encoded = data_uri.split(",", 1)
        media_type = header.removeprefix("data:").split(";", 1)[0]
        image_type = media_type.split("/", 1)[1]
    except (IndexError, ValueError) as exc:
        raise ValueError("owned_chat_image_media_type_invalid") from exc
    return store_diet_image(encoded, image_type, owner_id)


def remove_diet_image_file(filepath: str | None) -> None:
    if not filepath:
        return
    try:
        os.remove(filepath)
    except FileNotFoundError:
        return
