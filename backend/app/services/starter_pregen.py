"""Starter chip answer pre-generation (rank7 · latency roadmap Phase 2).

Home starter chips route to the slowest deep-analysis turns (~30-40s). This module
pre-generates the TOP-N served chips' answers OFF the response path (mirroring the
starter_polish BackgroundTask pattern) and, on tap, serves the stored answer
instantly IF still fresh — else it fails CLOSED and the tap runs a normal live turn.

Safety invariants (a pre-generated MEDICAL answer must never serve on changed data,
and pregen must never mutate user data):

  1. FRESHNESS is fail-closed — the tap serves only when ALL hold, else None → live:
     (a) the message EXACTLY matches the pregen'd starter text;
     (b) signals_hash(current data) == stored — a digest over the FULL deterministic
         candidate set (compute_salient_signals), stable across visits yet flipping
         on any starter-signal change;
     (c) the entry has not expired (STARTER_PREGEN_TTL_SECONDS);
     (d) the entry still exists — invalidate_pregen() drops a user's entries from the
         universal post-write choke (twin.cache.invalidate_twin), so ANY write discards.
  2. SAME pipeline — production runs the real AgentExecutor turn (all guards /
     validators / receipts), just early, with tools restricted READ-ONLY (fail-closed
     at the executor's single dispatch choke). A write attempt → ABORT, store nothing.
  3. Honest persistence — on serve the answer is a normal assistant message tagged
     `pregen_served: true` + `pregen_generated_at`.

Fail-SOFT throughout: flag off / Redis down / any error → no pregen, no serve,
byte-identical to today. Redis-backed (no new table), mirroring starter_polish.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Redis key namespace. v2 rejects every health-evidence query/payload; bumping all
# namespaces makes any legacy health entries and in-flight claims unreachable.
# be decoded into the new shape.
_ENTRY_PREFIX = "starter_pregen:v2"
_INFLIGHT_PREFIX = "starter_pregen:inflight:v2"
_METRIC_PREFIX = "starter_pregen:metric:v2"
# Per-user index SET of a user's live entry keys — invalidate_pregen clears via
# SMEMBERS+DEL rather than a full-keyspace scan_iter (C3: scans are O(keyspace)
# and ran on EVERY mutation). The index self-expires well beyond any entry TTL.
_INDEX_PREFIX = "starter_pregen:idx:v2"
_INDEX_TTL_SECONDS = 24 * 60 * 60
# An in-flight claim self-expires so a crashed pregen can't wedge a chip forever.
_INFLIGHT_TTL_SECONDS = 120
# Metrics counters live long enough to eyeball hit-rate before expansion.
_METRIC_TTL_SECONDS = 14 * 24 * 60 * 60


# ── Redis helpers (all fail-soft) ────────────────────────────────────────


def _redis():
    try:
        from app.utils.redis_cache import get_redis_client

        return get_redis_client()
    except Exception:  # noqa: BLE001
        return None


def _text_digest(starter_text: str) -> str:
    import hashlib

    return hashlib.sha256(starter_text.encode("utf-8")).hexdigest()[:24]


def _entry_key(user_id: int, starter_text: str) -> str:
    # Keyed by (user, text) only — `signals_hash` + `model_id` live INSIDE the entry
    # and are recompute-and-compared at serve time (freshness invariant 1b). This
    # keeps the hot path cheap: a non-starter message pays one Redis GET (miss) and
    # never computes the expensive data fingerprint.
    return f"{_ENTRY_PREFIX}:{user_id}:{_text_digest(starter_text)}"


def _inflight_key(user_id: int, starter_text: str) -> str:
    return f"{_INFLIGHT_PREFIX}:{user_id}:{_text_digest(starter_text)}"


def _index_key(user_id: int) -> str:
    return f"{_INDEX_PREFIX}:{user_id}"


def _incr_metric(name: str) -> None:
    """Bump a lightweight hit-rate counter (generated / hit / stale_miss)."""
    try:
        client = _redis()
        if client is None:
            return
        key = f"{_METRIC_PREFIX}:{name}"
        client.incr(key)
        client.expire(key, _METRIC_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass


def get_metrics() -> dict:
    """Return current pregen counters (generated / hit / stale_miss). Fail-soft → {}."""
    out: dict = {}
    try:
        client = _redis()
        if client is None:
            return out
        for name in ("generated", "hit", "stale_miss"):
            raw = client.get(f"{_METRIC_PREFIX}:{name}")
            try:
                out[name] = int(raw) if raw is not None else 0
            except (TypeError, ValueError):
                out[name] = 0
    except Exception:  # noqa: BLE001
        return {}
    return out


# ── Freshness key + model resolution ─────────────────────────────────────


def data_signals_hash(db: Session, user_id: int) -> str:
    """Deterministic content digest of the user's FULL starter-signal set.

    Uses compute_salient_signals(limit=0) — the complete, deterministic candidate
    list (NOT the per-visit random subset the chips display), so the hash is stable
    across home visits yet flips on any underlying data change. This is the primary
    fail-closed freshness key. Returns "" on any error → "" never matches a stored
    hash → fail-closed (no stale serve).
    """
    try:
        from app.services.conversation_starters import compute_salient_signals
        from app.services.starter_polish import signals_hash

        candidates = compute_salient_signals(db, user_id, limit=0)
        return signals_hash(candidates)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] data_signals_hash failed (fail-closed): %s", exc)
        return ""


def resolve_effective_model_id(db: Session, user_id: int) -> str:
    """Resolve the answer model a LIVE tap would use (per-user pref → global active).

    Included in the pregen key so an admin/user model switch between generation and
    tap is a key mismatch → miss → live turn. "default" when unresolved (still
    stable across pregen+serve because both resolve identically).
    """
    try:
        from app.models.user_profile import UserProfile

        profile = (
            db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        )
        pref = getattr(profile, "llm_model_id", None) if profile else None
        if pref:
            return str(pref)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.llm.model_registry import get_active_model_id

        active = get_active_model_id()
        if active:
            return str(active)
    except Exception:  # noqa: BLE001
        pass
    return "default"


# ── Store (read / write / invalidate) ────────────────────────────────────


def read_pregen(user_id: int, starter_text: str) -> Optional[dict]:
    """Return the stored pregen entry dict for (user, text) or None. Never raises.

    Freshness (signals_hash / model_id / expiry) is verified by the CALLER against
    the entry's stored fields — this is just the cheap lookup.
    """
    try:
        client = _redis()
        if client is None:
            return None
        raw = client.get(_entry_key(user_id, starter_text))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] read failed (bypassing): %s", exc)
        return None


def write_pregen(
    user_id: int,
    starter_text: str,
    payload: dict,
    *,
    ttl_seconds: int,
) -> None:
    """Persist a pregen entry for `ttl_seconds` + index it. Never raises."""
    from app.services.health_evidence.delivery import (
        metadata_claims_health,
        requires_live_health_executor,
    )

    if requires_live_health_executor(starter_text, enabled=True):
        return
    if metadata_claims_health(payload):
        return
    try:
        client = _redis()
        if client is None:
            return
        entry_key = _entry_key(user_id, starter_text)
        client.setex(entry_key, ttl_seconds, json.dumps(payload, ensure_ascii=False))
        # Track this key in the user's index set so invalidate can DEL by membership
        # (no keyspace scan). The index self-expires so it can't leak indefinitely.
        idx = _index_key(user_id)
        client.sadd(idx, entry_key)
        client.expire(idx, _INDEX_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] write failed (bypassing): %s", exc)


def invalidate_pregen(user_id: int) -> int:
    """Drop ALL pregen entries for a user (called on ANY write). Fail-soft → count.

    Write belt for freshness invariant (1d): a pre-generated answer can never
    survive a data mutation, even one the signals_hash wouldn't reflect.

    C3: this runs from twin.cache.invalidate_twin on EVERY mutation, so it must be
    cheap and gated. When the feature is OFF there are no entries to drop — return
    immediately, touching Redis zero times. When ON, clear by index-set membership
    (SMEMBERS + DEL), never a full-keyspace scan.
    """
    try:
        from app.config import settings

        if not getattr(settings, "starter_pregen_enabled", False):
            return 0
    except Exception:  # noqa: BLE001 — can't read flag → treat as off (belt is best-effort)
        return 0

    deleted = 0
    try:
        client = _redis()
        if client is None:
            return 0
        idx = _index_key(user_id)
        members = client.smembers(idx)
        keys = [
            (m.decode("utf-8") if isinstance(m, bytes) else m) for m in (members or [])
        ]
        if keys:
            deleted = client.delete(*keys) or 0
        client.delete(idx)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] invalidate failed (bypassing): %s", exc)
    return deleted


def _should_generate(
    user_id: int, starter_text: str, sig_hash: str, model_id: str
) -> bool:
    """True iff no FRESH entry is stored AND no attempt is already in flight.

    A stored-but-STALE entry (different signals_hash/model_id — e.g. after a
    time-of-day shift the write belt didn't catch) does NOT block regeneration; the
    fresh answer overwrites it. Claims an in-flight lock (SETNX + TTL) on success so
    repeated home visits don't re-generate the same (user, text) — single attempt,
    no retry storms. Fail-soft: Redis unavailable → False (skip, no unbounded fan-out).
    """
    from app.services.health_evidence.delivery import (
        requires_live_health_executor,
    )

    if requires_live_health_executor(starter_text, enabled=True):
        return False
    if not sig_hash:
        return False
    try:
        client = _redis()
        if client is None:
            return False
        existing = read_pregen(user_id, starter_text)
        if (
            existing
            and existing.get("signals_hash") == sig_hash
            and existing.get("model_id") == model_id
        ):
            return False  # already have a fresh answer for this exact state
        claimed = client.set(
            _inflight_key(user_id, starter_text),
            "1",
            nx=True,
            ex=_INFLIGHT_TTL_SECONDS,
        )
        return bool(claimed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] should_generate failed (skip): %s", exc)
        return False


def _release_inflight(user_id: int, starter_text: str) -> None:
    try:
        client = _redis()
        if client is not None:
            client.delete(_inflight_key(user_id, starter_text))
    except Exception:  # noqa: BLE001
        pass


# ── Serving (tap-time replay) ────────────────────────────────────────────


def try_serve(
    db: Session,
    user_id: int,
    message: str,
    *,
    conversation_id: Optional[int],
    client_turn_id: Optional[str],
) -> Optional[tuple[list[dict], int, int, str]]:
    """If `message` exactly matches a FRESH pregen'd starter → persist + return replay.

    Returns (sse_events, conversation_id, message_id, reply_text) on a hit, else None
    (the caller runs a normal live turn). Fail-closed on EVERY freshness check and
    fail-soft on any error. Only the exact starter text + current signals_hash +
    unexpired + still-present entry serves; anything else is None.
    """
    try:
        from app.config import settings

        if not getattr(settings, "starter_pregen_enabled", False):
            return None
        text = (message or "").strip()
        if not text:
            return None
        from app.services.health_evidence.delivery import (
            requires_live_health_executor,
        )

        if requires_live_health_executor(text, enabled=True):
            return None

        # Cheap first: a non-starter message misses on this Redis GET and pays
        # nothing more (no twin build / signal collection).
        entry = read_pregen(user_id, text)
        if not entry:
            return None
        from app.services.health_evidence.delivery import (
            metadata_claims_health,
        )

        if metadata_claims_health(entry):
            return None

        # Recompute the freshness key NOW and compare against what was stored. ANY
        # mismatch (data changed → different signals_hash, or model switched) →
        # fail-closed stale miss. A pre-generated medical answer must never serve on
        # changed data.
        sig_hash = data_signals_hash(db, user_id)
        model_id = resolve_effective_model_id(db, user_id)
        if (
            not sig_hash
            or entry.get("signals_hash") != sig_hash
            or entry.get("model_id") != model_id
        ):
            _incr_metric("stale_miss")
            return None

        # Expiry: belt beyond the Redis TTL (clock/skew defense) — a stored entry
        # older than the freshness window is a stale miss, not a hit.
        ttl = int(getattr(settings, "starter_pregen_ttl_seconds", 900) or 900)
        if _is_expired(entry.get("generated_at"), ttl):
            _incr_metric("stale_miss")
            return None

        answer_text = (entry.get("answer_text") or "").strip()
        if not answer_text:
            return None

        served = _persist_and_build_events(
            db,
            user_id,
            text,
            answer_text,
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            sources_used=entry.get("sources_used") or [],
            generated_at=entry.get("generated_at"),
        )
        if served is None:
            return None
        _incr_metric("hit")
        events, conv_id, msg_id, delivered_reply = served
        return events, conv_id, msg_id, delivered_reply
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] try_serve failed (fall through): %s", exc)
        return None


def _is_expired(generated_at: Any, ttl_seconds: int) -> bool:
    """True (fail-closed) unless generated_at parses and is within ttl_seconds."""
    try:
        if not generated_at:
            return True
        gen = datetime.fromisoformat(str(generated_at))
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - gen).total_seconds()
        return age < 0 or age > ttl_seconds
    except Exception:  # noqa: BLE001
        return True


def _persist_and_build_events(
    db: Session,
    user_id: int,
    message: str,
    full_reply: str,
    *,
    conversation_id: Optional[int],
    client_turn_id: Optional[str],
    sources_used: list,
    generated_at: Any,
) -> Optional[tuple[list[dict], int, int, str]]:
    """Persist the pregen answer as a normal assistant message and build SSE events.

    Mirrors the deterministic-answer replay precedent (GenUI short-circuit): a real
    user message + assistant message are written via AgentConversationService, so
    history reload / receipts stay honest. The assistant meta is tagged
    `pregen_served: true` + `pregen_generated_at` for transparency. Client-turn
    idempotency: an already-finalized turn is replayed rather than double-written.
    """
    from app.services.agent_conversation_service import AgentConversationService

    svc = AgentConversationService(db)
    thinking_steps = ["正在理解你的问题", "整理回复中"]

    def _replay(
        existing_user,
        existing_assistant,
    ) -> tuple[list[dict], int, int, str]:
        from app.services.health_evidence.delivery import (
            project_persisted_health_messages,
        )

        projected = project_persisted_health_messages(
            (existing_user, existing_assistant)
        )[-1]
        events = [{
            "event": "request_persisted",
            "data": {
                "conversation_id": existing_user.conversation_id,
                "user_message_id": existing_user.id,
                "client_turn_id": client_turn_id,
                "replayed": True,
            },
        }, {"event": "token", "data": {"content": projected.content}}]
        done_data = dict(projected.meta)
        done_data.update({
            "conversation_id": existing_assistant.conversation_id,
            "message_id": existing_assistant.id,
            "completion_status": done_data.get("completion_status") or "complete",
            "client_turn_id": client_turn_id,
            "replayed": True,
        })
        events.append({"event": "done", "data": done_data})
        return (
            events,
            existing_user.conversation_id,
            existing_assistant.id,
            projected.content,
        )

    claimed_turn = False
    try:
        # Idempotent replay of an already-finalized client turn.
        if client_turn_id:
            existing_user = svc.find_user_message_by_client_turn(user_id, client_turn_id)
            existing_assistant = svc.find_assistant_message_by_client_turn(user_id, client_turn_id)
            if (
                existing_user is not None
                and existing_assistant is not None
                and (existing_assistant.meta or {}).get("client_turn_finalized")
            ):
                return _replay(existing_user, existing_assistant)
            claimed_turn = svc.try_acquire_client_turn_execution(user_id, client_turn_id)
            if not claimed_turn:
                # Another worker owns this turn — let the normal executor path handle
                # it (returning None = fall through to a live turn).
                return None

        conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)
        user_msg, _ = svc.save_user_message_once(
            conv.id,
            user_id,
            message,
            client_turn_id=client_turn_id,
            meta={"client_turn_id": client_turn_id} if client_turn_id else None,
        )

        assistant_meta = {
            "mode": "agent",
            "sources_used": list(sources_used or []),
            "thinking_steps": thinking_steps,
            "completion_status": "complete",
            "pregen_served": True,
            "pregen_generated_at": generated_at,
            "client_turn_finalized": True,
            **({"client_turn_id": client_turn_id} if client_turn_id else {}),
        }
        ai_msg = svc.save_message(
            conv.id,
            "assistant",
            full_reply,
            meta=assistant_meta,
            client_turn_id=client_turn_id,
            client_turn_user_id=user_id,
        )

        events = [
            {
                "event": "request_persisted",
                "data": {
                    "conversation_id": conv.id,
                    "user_message_id": user_msg.id,
                    "client_turn_id": client_turn_id,
                },
            },
            {"event": "token", "data": {"content": full_reply}},
            {
                "event": "done",
                "data": {
                    "conversation_id": conv.id,
                    "message_id": ai_msg.id,
                    "elapsed_ms": 0,
                    "mode": "agent",
                    "sources_used": list(sources_used or []),
                    "thinking_steps": thinking_steps,
                    "completion_status": "complete",
                    "pregen_served": True,
                    "pregen_generated_at": generated_at,
                    "client_turn_id": client_turn_id,
                    "client_turn_finalized": True,
                },
            },
        ]
        return events, conv.id, ai_msg.id, full_reply
    finally:
        if claimed_turn and client_turn_id:
            svc.release_client_turn_execution(user_id, client_turn_id)
