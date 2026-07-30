"""Starter answer pre-generation — the PRODUCER side (rank7).

The store / freshness / serve half lives in `starter_pregen`; this module is the
"run the real turn early" half: the off-response-path pre-warm trigger and the
BackgroundTask that runs the actual (read-only) AgentExecutor turn and captures its
answer. Kept separate so each file stays within the complexity budget and the
"generate" concern is isolated from "store + gate + serve".

Safety: the turn runs with tools restricted to READ-ONLY (fail-closed at the
executor's single dispatch choke). If a write is attempted the answer is DISCARDED
(stored nothing). The turn runs into a throwaway scratch conversation that is always
deleted — no phantom message in the user's history. Fail-soft throughout.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.services.starter_pregen import (
    _incr_metric,
    _release_inflight,
    _should_generate,
    data_signals_hash,
    resolve_effective_model_id,
    write_pregen,
)

logger = logging.getLogger(__name__)


def enqueue_pregen(
    background_tasks,
    db: Session,
    user_id: int,
    starter_texts: Sequence[str],
    user_token: Optional[str],
) -> None:
    """Schedule pregen for the TOP-N served chips (budget cap: settings max).

    Called from the conversation-starters endpoint AFTER suggestions are served —
    on the response path only long enough to compute the freshness key + model
    (cheap) and dedupe; generation runs in a BackgroundTask. Never raises.
    """
    try:
        from app.config import settings

        if not getattr(settings, "starter_pregen_enabled", False):
            return
        cap = int(getattr(settings, "starter_pregen_max_chips", 2) or 0)
        if cap <= 0:
            return
        ttl = int(getattr(settings, "starter_pregen_ttl_seconds", 900) or 900)

        sig_hash = data_signals_hash(db, user_id)
        if not sig_hash:
            return  # no fingerprint → fail-closed, don't pregen
        model_id = resolve_effective_model_id(db, user_id)

        seen: set[str] = set()
        for text in starter_texts:
            text = (text or "").strip()
            if not text or text in seen:
                continue
            from app.services.health_evidence.delivery import (
                requires_live_health_executor,
            )

            if requires_live_health_executor(text, enabled=True):
                continue
            seen.add(text)
            if len(seen) > cap:
                break
            if _should_generate(user_id, text, sig_hash, model_id):
                background_tasks.add_task(
                    warm_pregen, user_id, text, sig_hash, model_id, ttl, user_token
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] enqueue failed (bypassing): %s", exc)


def warm_pregen(
    user_id: int,
    starter_text: str,
    sig_hash: str,
    model_id: str,
    ttl_seconds: int,
    user_token: Optional[str],
) -> None:
    """BackgroundTask entrypoint: produce one pregen answer and store it.

    Runs the REAL executor turn (read-only) in a fresh DB session, verifies no write
    was attempted, and caches the answer. Exceptions swallowed at WARNING. Releases
    the in-flight claim in finally so a transient failure can retry on a later visit.
    """
    import asyncio

    from app.database import SessionLocal
    from app.services.llm.usage_tracker import set_caller

    bg_db = SessionLocal()
    try:
        set_caller("starter_pregen", user_id)
        produced = asyncio.run(
            _produce_answer(bg_db, user_id, starter_text, model_id, user_token)
        )
        if produced is None:
            return
        payload = {
            "starter_text": starter_text,
            "signals_hash": sig_hash,
            "model_id": model_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **produced,
        }
        write_pregen(user_id, starter_text, payload, ttl_seconds=ttl_seconds)
        _incr_metric("generated")
        logger.info(
            "[starter_pregen] warmed user=%s hash=%s model=%s len=%d",
            user_id, sig_hash, model_id, len(produced.get("answer_text") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] warm task failed (bypassing): %s", exc)
    finally:
        _release_inflight(user_id, starter_text)
        try:
            bg_db.close()
        except Exception:  # noqa: BLE001
            pass


async def _produce_answer(
    db: Session,
    user_id: int,
    starter_text: str,
    model_id: str,
    user_token: Optional[str],
) -> Optional[dict]:
    """Run the real read-only turn into a throwaway scratch conversation and capture.

    Returns {answer_text, sources_used, mode}, or None whenever the answer must NOT
    be served: a write tool was attempted (starter chips are analysis prompts), the
    turn didn't complete, the answer is empty, or any error. Always deletes scratch.
    """
    from app.models.agent_conversation import AgentConversation
    from app.services.agent_conversation_service import (
        PREGEN_SCRATCH_SESSION_PREFIX,
        AgentConversationService,
    )
    from app.services.agent_executor import _WRITE_RECEIPT_TOOL_NAMES, AgentExecutor
    from app.services.health_evidence.delivery import (
        metadata_claims_health,
        requires_live_health_executor,
    )

    if requires_live_health_executor(starter_text, enabled=True):
        return None

    svc = AgentConversationService(db)
    scratch: Optional[AgentConversation] = None
    try:
        scratch = AgentConversation(
            user_id=user_id,
            title="pregen",
            session_key=f"{PREGEN_SCRATCH_SESSION_PREFIX}{user_id}-{uuid.uuid4().hex[:12]}",
        )
        db.add(scratch)
        db.commit()
        db.refresh(scratch)

        executor = AgentExecutor(db)
        reply_parts: list[str] = []
        done_data: dict = {}
        errored = False
        async for event in executor.run_stream(
            user_id=user_id,
            message=starter_text,
            conversation_id=scratch.id,
            user_auth_token=user_token,
            client_turn_id=None,
            read_only_tools=True,
        ):
            etype = event.get("event")
            if etype == "token":
                content = event.get("data", {}).get("content")
                if isinstance(content, str):
                    reply_parts.append(content)
            elif etype == "done":
                data = event.get("data")
                if isinstance(data, dict):
                    done_data = data
            elif etype == "error":
                errored = True

        # Fail-closed acceptance gate: any write attempt, incomplete turn, an error,
        # or empty answer → produce nothing (tap falls through to a live turn).
        if getattr(executor, "_read_only_turn_write_attempted", False):
            logger.warning(
                "[starter_pregen] discarded — write tool attempted during pregen user=%s",
                user_id,
            )
            return None
        tools_used = done_data.get("tools_used") or []
        if any(t in _WRITE_RECEIPT_TOOL_NAMES for t in tools_used):
            logger.warning("[starter_pregen] discarded — write tool in tools_used user=%s", user_id)
            return None
        if errored or done_data.get("completion_status") != "complete":
            return None
        if metadata_claims_health(done_data):
            logger.warning(
                "[starter_pregen] discarded — health evidence requires live "
                "release user=%s",
                user_id,
            )
            return None
        answer_text = "".join(reply_parts).strip()
        if not answer_text:
            return None

        return {
            "answer_text": answer_text,
            "sources_used": done_data.get("sources_used") or [],
            "mode": "agent",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_pregen] produce failed (bypassing): %s", exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        if scratch is not None:
            try:
                svc.delete_conversation(user_id, scratch.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[starter_pregen] scratch cleanup failed: %s", exc)
