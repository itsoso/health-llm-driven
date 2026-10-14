"""Bounded, process-local previews; callers must authorize before every lookup.

No derivative files are persisted. Keys include the canonical owner path and
source stat; entries expire after five minutes, with at most 32 x 512 KiB.
"""
from collections import OrderedDict
import io
import os
import threading
import time

from anyio import CapacityLimiter, to_thread
from fastapi import HTTPException
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError

_cache = OrderedDict()
_lock = threading.Lock()
_limiter = CapacityLimiter(2)
_TTL = 300
_MAX_ENTRIES = 32
_MAX_ENTRY_BYTES = 512 * 1024


def load_preview(filepath: str) -> tuple[bytes, str]:
    stat = os.stat(filepath)  # Deleted originals must never be served from cache.
    key = (os.path.realpath(filepath), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    now = time.monotonic()
    with _lock:
        for stale in [key for key, value in _cache.items() if value[0] <= now]:
            del _cache[stale]
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key][1]
    if stat.st_size > 20 * 1024 * 1024:
        raise ValueError("preview_source_too_large")
    with Image.open(filepath) as source:
        if source.width * source.height > 20_000_000:
            raise ValueError("preview_source_too_large")
        preview = ImageOps.exif_transpose(source)
        preview.thumbnail((960, 960), Image.Resampling.LANCZOS)
        if "A" in preview.getbands() or "transparency" in preview.info:
            rgba = preview.convert("RGBA")
            preview = Image.new("RGB", rgba.size, "white")
            preview.paste(rgba, mask=rgba.getchannel("A"))
        else:
            preview = preview.convert("RGB")
        output = io.BytesIO()
        # Explicitly omit EXIF/location and other original metadata.
        preview.save(output, format="JPEG", quality=80, optimize=True)
    result = (output.getvalue(), "image/jpeg")
    if len(result[0]) <= _MAX_ENTRY_BYTES:
        with _lock:
            _cache[key] = (time.monotonic() + _TTL, result)
            _cache.move_to_end(key)
            while len(_cache) > _MAX_ENTRIES:
                _cache.popitem(last=False)
    return result


async def private_preview_response(filepath: str) -> Response:
    try:
        data, media_type = await to_thread.run_sync(load_preview, filepath, limiter=_limiter)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    except (ValueError, UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise HTTPException(status_code=422, detail="图片预览不可用，请查看原图") from exc
    # Do not enable shared/CDN caching of a private health image.
    return Response(data, media_type=media_type, headers={"Cache-Control": "private, no-store"})
