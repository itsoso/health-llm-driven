"""Shared chat utilities — image upload, compression.

Used by AgentExecutor and conversation services to avoid duplication.
"""
import base64
import fcntl
import hashlib
import json
import logging
import os
import re
import time
import uuid
import threading
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from typing import Callable
from urllib.parse import urlsplit

from app.services.private_uploads import (
    build_signed_private_upload_url,
    refresh_private_upload_url,
    verify_signed_private_upload_url,
)
from app.utils.runtime_data import upload_dir

logger = logging.getLogger(__name__)
_ACTIVE_STAGED_DELETION_GUARD = threading.Lock()
_ACTIVE_STAGED_DELETIONS: set[str] = set()
_CHAT_IMAGE_LIFECYCLE_PROCESS_LOCK = threading.RLock()
_CHAT_IMAGE_LIFECYCLE_THREAD_STATE = threading.local()
CHAT_IMAGE_LIFECYCLE_LOCK_TIMEOUT_SECONDS = 5.0

_UPLOAD_DIR = os.fspath(upload_dir() / "chat")


@contextmanager
def chat_image_lifecycle_lock():
    """Serialize image-reference commits and tombstone reconciliation."""
    timeout = max(0.0, float(CHAT_IMAGE_LIFECYCLE_LOCK_TIMEOUT_SECONDS))
    acquired_process_lock = _CHAT_IMAGE_LIFECYCLE_PROCESS_LOCK.acquire(
        timeout=timeout,
    )
    if not acquired_process_lock:
        raise TimeoutError("chat_image_lifecycle_lock_timeout")
    try:
        depth = int(getattr(_CHAT_IMAGE_LIFECYCLE_THREAD_STATE, "depth", 0))
        lock_fd = getattr(_CHAT_IMAGE_LIFECYCLE_THREAD_STATE, "lock_fd", None)
        if depth == 0:
            os.makedirs(_UPLOAD_DIR, exist_ok=True)
            lock_path = os.path.join(_UPLOAD_DIR, ".lifecycle.lock")
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                deadline = time.monotonic() + timeout
                while True:
                    try:
                        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                "chat_image_lifecycle_lock_timeout"
                            )
                        time.sleep(min(0.05, remaining))
            except Exception:
                os.close(lock_fd)
                raise
            _CHAT_IMAGE_LIFECYCLE_THREAD_STATE.lock_fd = lock_fd
        _CHAT_IMAGE_LIFECYCLE_THREAD_STATE.depth = depth + 1
        try:
            yield
        finally:
            remaining_depth = (
                int(getattr(_CHAT_IMAGE_LIFECYCLE_THREAD_STATE, "depth", 1)) - 1
            )
            _CHAT_IMAGE_LIFECYCLE_THREAD_STATE.depth = remaining_depth
            if remaining_depth == 0 and lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
                    delattr(_CHAT_IMAGE_LIFECYCLE_THREAD_STATE, "lock_fd")
    finally:
        _CHAT_IMAGE_LIFECYCLE_PROCESS_LOCK.release()
def build_signed_chat_image_url(
    owner_id: int,
    filename: str,
    *,
    expires: int | None = None,
    legacy: bool = False,
) -> str:
    return build_signed_private_upload_url(
        "chat",
        owner_id,
        filename,
        expires=expires,
        legacy=legacy,
    )


def verify_signed_chat_image_url(
    owner_id: int,
    filename: str,
    expires: int | None,
    signature: str | None,
    *,
    legacy: bool = False,
) -> bool:
    return verify_signed_private_upload_url(
        "chat",
        owner_id,
        filename,
        expires,
        signature,
        legacy=legacy,
    )


def refresh_chat_image_url_value(raw_value: str | None, owner_id: int) -> str | None:
    """Refresh signed capability URLs for clients that cannot attach image headers."""
    if not raw_value:
        return raw_value
    try:
        parsed = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        parsed = raw_value
    values = parsed if isinstance(parsed, list) else [parsed]
    refreshed: list[str] = []
    for value in values:
        raw_url = str(value or "")
        refreshed.append(refresh_private_upload_url(raw_url, "chat", owner_id) or raw_url)
    return json.dumps(refreshed, ensure_ascii=False) if isinstance(parsed, list) else refreshed[0]


def upload_chat_image(
    image_base64: str,
    user_id: int,
    image_type: str = "jpeg",
    object_key: str | None = None,
) -> str:
    """Save a chat image under its owner and return an authenticated URL."""
    owner_id = int(user_id)
    extension = str(image_type or "jpeg").lower().replace("jpg", "jpeg")
    if extension not in {"jpeg", "png", "gif", "webp"}:
        extension = "jpeg"
    owner_dir = os.path.join(_UPLOAD_DIR, str(owner_id))
    os.makedirs(owner_dir, exist_ok=True)
    raw = image_base64.split(",", 1)[-1] if "," in image_base64 else image_base64
    data = base64.b64decode(raw, validate=True)
    content_digest = hashlib.sha256(data).hexdigest()
    if object_key:
        safe_object_key = re.sub(r"[^a-zA-Z0-9_-]", "", object_key)[:96]
        if not safe_object_key:
            raise ValueError("invalid_chat_image_object_key")
        fname = f"{safe_object_key}_{content_digest[:16]}.{extension}"
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{uuid.uuid4().hex}.{extension}"
    destination = os.path.join(owner_dir, fname)
    temporary = os.path.join(owner_dir, f".{fname}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temporary, "xb") as file_handle:
            file_handle.write(data)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            with open(destination, "rb") as file_handle:
                if file_handle.read() != data:
                    raise RuntimeError("chat_image_object_key_collision")
        try:
            directory_fd = os.open(owner_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            logger.warning(
                "Chat image directory fsync failed for user_id=%s",
                owner_id,
                exc_info=True,
            )
    except Exception:
        logger.warning("Chat image upload failed for user_id=%s", owner_id, exc_info=True)
        raise
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            logger.warning("Chat image temp cleanup failed", exc_info=True)
    return build_signed_chat_image_url(owner_id, fname)


def _chat_image_file_path(relative_url: str, user_id: int) -> str | None:
    path = urlsplit(relative_url).path
    prefix = "/api/v1/upload/files/chat/"
    if not path.startswith(prefix):
        return None
    parts = [part for part in path[len(prefix):].split("/") if part]
    if len(parts) == 2 and parts[0] == str(int(user_id)):
        root = os.path.realpath(os.path.join(_UPLOAD_DIR, str(int(user_id))))
        candidate = os.path.realpath(os.path.join(root, os.path.basename(parts[1])))
    elif len(parts) == 1:
        root = os.path.realpath(_UPLOAD_DIR)
        candidate = os.path.realpath(os.path.join(root, os.path.basename(parts[0])))
    else:
        return None
    if not candidate.startswith(f"{root}{os.sep}"):
        return None
    return candidate


def read_owned_chat_image_data_uri(
    relative_url: str,
    user_id: int,
    *,
    max_bytes: int = 20 * 1024 * 1024,
) -> str:
    """Read an owner's persisted chat image as a bounded image data URI.

    This is for an already-authorized server-side provider call.  It does not
    accept arbitrary filesystem paths or URLs, and never logs source bytes.
    """
    path = _chat_image_file_path(relative_url, user_id)
    if not path or not os.path.isfile(path):
        raise ValueError("owned_chat_image_not_found")
    size = os.path.getsize(path)
    if size <= 0 or size > max_bytes:
        raise ValueError("owned_chat_image_size_invalid")
    extension = os.path.splitext(path)[1].lower().lstrip(".")
    mime_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    mime_type = mime_types.get(extension)
    if not mime_type:
        raise ValueError("owned_chat_image_type_invalid")
    with open(path, "rb") as file_handle:
        encoded = base64.b64encode(file_handle.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_short_lived_chat_image_provider_url(
    relative_url: str,
    user_id: int,
    *,
    public_base_url: str,
    ttl_seconds: int,
) -> str:
    """Issue a provider-fetchable, short-lived URL for an owned chat image."""
    path = _chat_image_file_path(relative_url, user_id)
    if not path or not os.path.isfile(path):
        raise ValueError("owned_chat_image_not_found")
    base = str(public_base_url or "").strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("public_https_base_url_required")
    safe_ttl = max(60, min(int(ttl_seconds), 15 * 60))
    filename = os.path.basename(path)
    signed_path = build_signed_chat_image_url(
        int(user_id),
        filename,
        expires=int(time.time()) + safe_ttl,
    )
    return f"{base}{signed_path}"


StagedChatImageDeletion = tuple[str, str, int]


def _release_staged_chat_image_lock(staged_deletion: StagedChatImageDeletion) -> None:
    _, staged, lock_fd = staged_deletion
    with _ACTIVE_STAGED_DELETION_GUARD:
        _ACTIVE_STAGED_DELETIONS.discard(staged)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(lock_fd)
    except OSError:
        pass


def stage_chat_image_deletion(
    relative_url: str,
    user_id: int,
) -> StagedChatImageDeletion | None:
    path = _chat_image_file_path(relative_url, user_id)
    if not path or not os.path.exists(path):
        return None
    staged = f"{path}.delete-{uuid.uuid4().hex}"
    lock_fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        return None
    with _ACTIVE_STAGED_DELETION_GUARD:
        _ACTIVE_STAGED_DELETIONS.add(staged)
    try:
        os.replace(path, staged)
    except Exception:
        _release_staged_chat_image_lock((path, staged, lock_fd))
        raise
    return path, staged, lock_fd


def restore_staged_chat_image(staged_deletion: StagedChatImageDeletion) -> None:
    original, staged, _ = staged_deletion
    try:
        if os.path.exists(staged) and not os.path.exists(original):
            os.replace(staged, original)
    finally:
        _release_staged_chat_image_lock(staged_deletion)


def finalize_staged_chat_image(staged_deletion: StagedChatImageDeletion) -> None:
    _, staged, _ = staged_deletion
    try:
        if os.path.exists(staged):
            os.remove(staged)
    finally:
        _release_staged_chat_image_lock(staged_deletion)


def retry_staged_chat_image_deletions(
    user_id: int | None = None,
    *,
    is_referenced: Callable[[str], bool],
) -> int:
    """Resolve unlocked tombstones against authoritative database references."""
    upload_root = os.path.realpath(_UPLOAD_DIR)
    if not os.path.isdir(upload_root):
        return 0

    scan_roots: list[str]
    if user_id is None:
        scan_roots = [upload_root]
    else:
        owner_root = os.path.realpath(os.path.join(upload_root, str(int(user_id))))
        if not owner_root.startswith(f"{upload_root}{os.sep}"):
            return 0
        scan_roots = [owner_root] if os.path.isdir(owner_root) else []

    candidates: list[str] = []
    for scan_root in scan_roots:
        for current_root, _directories, filenames in os.walk(scan_root, followlinks=False):
            for filename in filenames:
                if ".delete-" not in filename:
                    continue
                candidates.append(os.path.join(current_root, filename))
    removed = 0
    restored = 0
    failures = 0
    for path in candidates:
        candidate = os.path.realpath(path)
        if not candidate.startswith(f"{upload_root}{os.sep}"):
            continue
        with _ACTIVE_STAGED_DELETION_GUARD:
            if candidate in _ACTIVE_STAGED_DELETIONS:
                continue
        lock_fd = None
        try:
            lock_fd = os.open(candidate, os.O_RDONLY)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            original = candidate.split(".delete-", 1)[0]
            if is_referenced(original):
                if os.path.exists(original):
                    os.remove(candidate)
                    removed += 1
                else:
                    os.replace(candidate, original)
                    restored += 1
            else:
                os.remove(candidate)
                removed += 1
        except FileNotFoundError:
            continue
        except BlockingIOError:
            continue
        except OSError:
            failures += 1
            logger.error(
                "Chat image tombstone retry failed user_id=%s",
                user_id,
                exc_info=True,
            )
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
    if removed or restored or failures:
        logger.info(
            "Chat image tombstone cleanup user_id=%s removed=%s restored=%s failures=%s",
            user_id,
            removed,
            restored,
            failures,
        )
    return removed + restored


def delete_chat_image(relative_url: str, user_id: int) -> None:
    path = _chat_image_file_path(relative_url, user_id)
    if path and os.path.exists(path):
        os.remove(path)


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
