"""Only canonical owner-bound images; clients use authenticated upload access."""
import hashlib
import json
import re

_PATH = re.compile(r"/api/v1/upload/files/(chat|diet)/([1-9][0-9]*)/([A-Za-z0-9_-]+\.(?:jpeg|jpg|png|gif|webp))")
_GENERATED = re.compile(r"(?:[0-9]{8}_[0-9]{6}_(?:[a-f0-9]{8}|[a-f0-9]{32})|[A-Za-z0-9_-]{1,96}_[a-f0-9]{16})\.(?:jpeg|jpg|png|gif|webp)")


def source_images(kind, source, owner_id):
    if kind == "life_event":
        return [], "none"
    raw = source.image_url
    digests = {}
    if kind == "diet" and source.photo_assets:
        assets = [a for a in source.photo_assets if a.lifecycle == "attached" and a.deleted_at is None]
        if any(a.user_id != owner_id or a.diet_record_id != source.id for a in assets):
            return [], "unavailable"
        if any(not re.fullmatch(r"[a-f0-9]{64}", a.content_sha256 or "") for a in assets):
            return [], "unavailable"
        values = [a.storage_key for a in assets]
        digests = {a.storage_key: a.content_sha256 for a in assets}
        if raw and any(a.storage_key == raw for a in source.photo_assets) and raw not in values:
            # A deleted ledger asset cannot become a legacy cover fallback.
            return [], "unavailable"
        # A legacy cover is also a source image; never hide an invalid member.
        if raw and raw not in values:
            values.insert(0, raw)
    elif not raw:
        return [], "none"
    elif kind == "chat_photo" and raw.startswith("["):
        try:
            values = json.loads(raw)
        except (ValueError, TypeError):
            return [], "unavailable"
    else:
        values = [raw]
    if not isinstance(values, list) or len(values) > 30 or not values:
        return [], "unavailable"
    checked = []
    for value in values:
        if not isinstance(value, str):
            return [], "unavailable"
        match = _PATH.fullmatch(value)
        if not match or int(match[2]) != owner_id or not _GENERATED.fullmatch(match[3]):
            return [], "unavailable"
        if kind == "chat_photo" and match[1] != "chat":
            return [], "unavailable"
        if value not in [item[0] for item in checked]:
            checked.append((value, match[1], match[3]))
    # Never mint bearer capability URLs for this feature. The upload endpoint
    # authenticates the current Bearer user against the owner path instead.
    return [
        {"key": hashlib.sha256(f"{owner_id}:{kind}:{source.id}:{path}:{digests.get(path, '')}".encode()).hexdigest(),
         "url": path}
        for path, category, filename in checked
    ], "ready"
