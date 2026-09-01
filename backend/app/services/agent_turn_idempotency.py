"""Bounded semantic idempotency for read-only Agent turns.

The cache stores only SHA-256 fingerprints and opaque client turn ids. It never
stores raw health text or image bytes and never admits write-shaped requests.
Exact idempotency remains owned by ``client_turn_id`` and the durable Runtime.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Iterable


SEMANTIC_DEDUPE_WINDOW_SECONDS = 45.0
_REDIS_RETRY_COOLDOWN_SECONDS = 30.0
_redis_retry_after = 0.0
_WRITE_MARKERS = re.compile(
    r"(?:记录|保存|写入|补录|修改|更新|删除|移除|撤销|完成|打卡|添加|创建|设置|设定|提醒|同步|执行|服用|吃了|喝了)"
    r"|\b(?:record|save|log|add|update|delete|remove|complete|remind|sync|take|took|ate|drank|schedule|cancel)\b",
    re.I,
)
_READ_MARKERS = re.compile(
    r"(?:分析|解读|查询|查看|多少|怎么样|如何|能否|是否|建议|趋势|为什么|什么|吗|？|\?)"
    r"|\b(?:analy[sz]e|query|show|check|review|explain|how|what|why|can|could|should|trend)\b",
    re.I,
)


def normalize_semantic_request(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.casefold().split()).strip()


def is_semantic_read_only_candidate(message: str) -> bool:
    normalized = normalize_semantic_request(message)
    return bool(normalized) and _WRITE_MARKERS.search(normalized) is None and _READ_MARKERS.search(normalized) is not None


def image_content_hashes(images: Iterable[dict] | None) -> tuple[str, ...]:
    hashes: list[str] = []
    for image in images or ():
        if not isinstance(image, dict):
            continue
        encoded = str(image.get("base64") or "")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            content = encoded.encode("ascii", errors="ignore")
        hashes.append(hashlib.sha256(content).hexdigest())
    return tuple(hashes)


def semantic_turn_fingerprint(
    *,
    user_id: int,
    conversation_id: int | None,
    message: str,
    data_version: str | None = None,
    image_hashes: Iterable[str] = (),
    intent: str = "read",
) -> str:
    payload = {
        "version": "semantic-turn-v1",
        "owner": int(user_id),
        "conversation": int(conversation_id or 0),
        "request": normalize_semantic_request(message),
        "data_version": str(data_version or "none")[:128],
        "images": sorted(str(value) for value in image_hashes if value),
        "intent": str(intent or "read")[:64],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SemanticTurnResolution:
    client_turn_id: str
    fingerprint: str
    dedupe_hit: bool


class SemanticTurnDedupeCache:
    def __init__(self, *, ttl_seconds: float = SEMANTIC_DEDUPE_WINDOW_SECONDS, max_entries: int = 1024):
        self._ttl_seconds = max(1.0, float(ttl_seconds))
        self._max_entries = max(16, int(max_entries))
        self._entries: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def resolve(
        self,
        *,
        fingerprint: str,
        proposed_client_turn_id: str,
        now: float | None = None,
    ) -> SemanticTurnResolution:
        current = time.monotonic() if now is None else float(now)
        with self._lock:
            if len(self._entries) >= self._max_entries:
                self._entries = {
                    key: entry for key, entry in self._entries.items() if entry[1] > current
                }
                while len(self._entries) >= self._max_entries:
                    self._entries.pop(next(iter(self._entries)))
            existing = self._entries.get(fingerprint)
            if existing is not None and existing[1] > current:
                return SemanticTurnResolution(
                    client_turn_id=existing[0],
                    fingerprint=fingerprint,
                    dedupe_hit=existing[0] != proposed_client_turn_id,
                )
            self._entries[fingerprint] = (
                proposed_client_turn_id,
                current + self._ttl_seconds,
            )
        return SemanticTurnResolution(
            client_turn_id=proposed_client_turn_id,
            fingerprint=fingerprint,
            dedupe_hit=False,
        )


def resolve_distributed_semantic_turn(
    *,
    cache: SemanticTurnDedupeCache,
    fingerprint: str,
    proposed_client_turn_id: str,
) -> SemanticTurnResolution:
    """Resolve across workers through Redis, with bounded in-process fallback."""
    global _redis_retry_after
    try:
        from app.utils.redis_cache import get_redis_client

        now = time.monotonic()
        client = get_redis_client() if now >= _redis_retry_after else None
        if client is None:
            _redis_retry_after = now + _REDIS_RETRY_COOLDOWN_SECONDS
        if client is not None:
            key = f"agent:semantic-turn:v1:{fingerprint}"
            acquired = client.set(
                key,
                proposed_client_turn_id,
                nx=True,
                ex=max(1, int(SEMANTIC_DEDUPE_WINDOW_SECONDS)),
            )
            if acquired:
                return SemanticTurnResolution(
                    client_turn_id=proposed_client_turn_id,
                    fingerprint=fingerprint,
                    dedupe_hit=False,
                )
            existing = client.get(key)
            if isinstance(existing, str) and existing:
                return SemanticTurnResolution(
                    client_turn_id=existing[:80],
                    fingerprint=fingerprint,
                    dedupe_hit=existing != proposed_client_turn_id,
                )
    except Exception:
        # Availability beats dedupe. Durable exact-id runtime protection still
        # applies, and the local cache covers repeated requests on this worker.
        pass
    return cache.resolve(
        fingerprint=fingerprint,
        proposed_client_turn_id=proposed_client_turn_id,
    )
