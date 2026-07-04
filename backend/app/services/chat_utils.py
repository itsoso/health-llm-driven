"""Shared chat utilities — image upload, compression.

Used by AgentExecutor and conversation services to avoid duplication.
"""
import base64
import logging
import os
import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "uploads", "chat",
)


def upload_chat_image(image_base64: str, image_type: str = "jpeg") -> Optional[str]:
    """Save a base64-encoded chat image to disk, return the relative URL."""
    try:
        os.makedirs(_UPLOAD_DIR, exist_ok=True)
        raw = image_base64.split(",", 1)[-1] if "," in image_base64 else image_base64
        data = base64.b64decode(raw)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{uuid.uuid4().hex[:8]}.{image_type}"
        with open(os.path.join(_UPLOAD_DIR, fname), "wb") as f:
            f.write(data)
        return f"/api/v1/upload/files/chat/{fname}"
    except Exception:
        logger.warning("Chat image upload failed", exc_info=True)
        return None


def compress_image_base64(
    base64_data: str, image_type: str = "jpeg",
    max_size: int = 1024, quality: int = 75,
) -> str:
    """Compress a base64 image — max edge `max_size` px, JPEG output."""
    try:
        from PIL import Image
        raw = base64.b64decode(base64_data)
        img = Image.open(BytesIO(raw))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = base64.b64encode(buf.getvalue()).decode()
        logger.info(f"Image compressed: {len(base64_data)//1024}KB -> {len(compressed)//1024}KB, {img.size}")
        return compressed
    except Exception as e:
        logger.warning(f"Image compression failed, using original: {e}")
        return base64_data
