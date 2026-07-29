"""Conversation persistence for the first-party health Agent."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from contextlib import nullcontext
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.services.agent_kernel.actionable_context import (
    extract_actionable_references,
)
from app.services.agent_kernel.types import ActionableReference


logger = logging.getLogger(__name__)

# Starter answer pre-generation (rank7) runs a real turn into a throwaway scratch
# conversation, captures the answer, then deletes it. Scratch conversations are
# tagged with this session_key prefix and excluded from every user-facing listing
# so the transient row can never leak into the user's conversation list (belt: the
# pregen orchestrator also deletes it immediately after capture).
PREGEN_SCRATCH_SESSION_PREFIX = "__reva_pregen_scratch__"

_LOCAL_CLIENT_TURN_LOCK_GUARD = threading.Lock()
_LOCAL_CLIENT_TURN_LOCKS: set[int] = set()
_CLIENT_TURN_LOCK_ENGINE_GUARD = threading.Lock()
_CLIENT_TURN_LOCK_ENGINES: dict[int, Any] = {}
CLIENT_TURN_LOCK_POOL_SIZE = 8
CLIENT_TURN_LOCK_POOL_TIMEOUT_SECONDS = 0.25
CLIENT_TURN_GLOBAL_SLOT_COUNT = 16
_CLIENT_TURN_GLOBAL_SLOT_NAMESPACE = 1_381_387_841


def _get_client_turn_lock_engine(bind):
    """Return a small dedicated pool so turn locks cannot consume the API pool."""
    source_engine = getattr(bind, "engine", bind)
    url = getattr(source_engine, "url", None)
    if url is None:
        raise RuntimeError("client_turn_lock_engine_url_unavailable")
    cache_key = id(source_engine)
    with _CLIENT_TURN_LOCK_ENGINE_GUARD:
        lock_engine = _CLIENT_TURN_LOCK_ENGINES.get(cache_key)
        if lock_engine is None:
            lock_engine = create_engine(
                url,
                pool_size=CLIENT_TURN_LOCK_POOL_SIZE,
                max_overflow=0,
                pool_timeout=CLIENT_TURN_LOCK_POOL_TIMEOUT_SECONDS,
                pool_pre_ping=True,
            )
            _CLIENT_TURN_LOCK_ENGINES[cache_key] = lock_engine
        return lock_engine


class AgentConversationService:
    """CRUD wrapper for first-party Agent conversations and messages."""

    def __init__(self, db: Session):
        self.db = db
        self._postgres_client_turn_locks: dict[int, tuple[Any, Any]] = {}

    @staticmethod
    def _client_turn_storage_key(user_id: int, client_turn_id: str) -> str:
        return f"{int(user_id)}:{client_turn_id}"

    @classmethod
    def _client_turn_lock_key(cls, user_id: int, client_turn_id: str) -> int:
        storage_key = cls._client_turn_storage_key(user_id, client_turn_id).encode()
        return int.from_bytes(
            hashlib.blake2b(storage_key, digest_size=8).digest(),
            byteorder="big",
            signed=True,
        )

    def try_acquire_client_turn_execution(self, user_id: int, client_turn_id: str) -> bool:
        """Claim a turn on a dedicated PostgreSQL transaction.

        A SQLAlchemy Session may return its connection to QueuePool on every
        business-data commit. The lock therefore cannot live on ``self.db``. A
        dedicated connection keeps a transaction-level advisory lock for the
        whole turn and releases it automatically on rollback, connection loss,
        or worker death. SQLite uses a process-local equivalent for tests/dev.
        """
        lock_key = self._client_turn_lock_key(user_id, client_turn_id)
        bind = self.db.get_bind()
        dialect = getattr(bind, "dialect", None)
        if getattr(dialect, "name", None) == "postgresql":
            if lock_key in self._postgres_client_turn_locks:
                return True
            connection = None
            transaction = None
            try:
                connection = _get_client_turn_lock_engine(bind).connect()
                transaction = connection.begin()
                slot_start = abs(lock_key) % CLIENT_TURN_GLOBAL_SLOT_COUNT
                slot_acquired = False
                for offset in range(CLIENT_TURN_GLOBAL_SLOT_COUNT):
                    slot = (slot_start + offset) % CLIENT_TURN_GLOBAL_SLOT_COUNT
                    slot_acquired = bool(connection.execute(
                        text(
                            "SELECT pg_try_advisory_xact_lock("
                            ":slot_namespace, :slot)"
                        ),
                        {
                            "slot_namespace": _CLIENT_TURN_GLOBAL_SLOT_NAMESPACE,
                            "slot": slot,
                        },
                    ).scalar())
                    if slot_acquired:
                        break
                if not slot_acquired:
                    transaction.rollback()
                    connection.close()
                    return False
                acquired = connection.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                ).scalar()
                if not acquired:
                    transaction.rollback()
                    connection.close()
                    return False
                self._postgres_client_turn_locks[lock_key] = (connection, transaction)
                return True
            except SQLAlchemyTimeoutError:
                if transaction is not None:
                    transaction.rollback()
                if connection is not None:
                    connection.close()
                return False
            except Exception:
                if transaction is not None:
                    transaction.rollback()
                if connection is not None:
                    connection.close()
                raise
        with _LOCAL_CLIENT_TURN_LOCK_GUARD:
            if lock_key in _LOCAL_CLIENT_TURN_LOCKS:
                return False
            _LOCAL_CLIENT_TURN_LOCKS.add(lock_key)
            return True

    def release_client_turn_execution(self, user_id: int, client_turn_id: str) -> None:
        lock_key = self._client_turn_lock_key(user_id, client_turn_id)
        bind = self.db.get_bind()
        dialect = getattr(bind, "dialect", None)
        if getattr(dialect, "name", None) == "postgresql":
            lock = self._postgres_client_turn_locks.pop(lock_key, None)
            if lock is None:
                logger.warning(
                    "Client turn lock release had no owned transaction user_id=%s",
                    user_id,
                )
                return
            connection, transaction = lock
            try:
                transaction.rollback()
            finally:
                connection.close()
            return
        with _LOCAL_CLIENT_TURN_LOCK_GUARD:
            _LOCAL_CLIENT_TURN_LOCKS.discard(lock_key)

    def get_or_create_conversation(
        self,
        user_id: int,
        conversation_id: Optional[int],
        title: str = "新对话",
    ) -> AgentConversation:
        if conversation_id:
            conv = (
                self.db.query(AgentConversation)
                .filter(
                    AgentConversation.id == conversation_id,
                    AgentConversation.user_id == user_id,
                )
                .first()
            )
            if not conv:
                raise ValueError("对话不存在")
            return conv

        conv = AgentConversation(
            user_id=user_id,
            title=(title or "新对话")[:50],
            session_key=f"agent-{user_id}-{uuid.uuid4().hex[:12]}",
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def _apply_search(self, q, *, title_like: Optional[str], search: Optional[str]):
        """Filter conversations by title (title_like) or title∪message-content (search).

        `search` 匹配标题 OR 任一消息正文(ilike),对应"按标题和内容搜索"。
        `title_like` 保留旧行为(仅标题),search 优先。用 EXISTS 子查询避免 join
        导致的重复行 + 无需 distinct。
        """
        term = (search or "").strip()
        if term:
            pattern = f"%{term}%"
            msg_exists = (
                self.db.query(AgentMessage.id)
                .filter(
                    AgentMessage.conversation_id == AgentConversation.id,
                    AgentMessage.content.ilike(pattern),
                )
                .exists()
            )
            return q.filter((AgentConversation.title.ilike(pattern)) | msg_exists)
        if title_like:
            return q.filter(AgentConversation.title.ilike(f"%{title_like}%"))
        return q

    def get_conversations(
        self,
        user_id: int,
        limit: int = 20,
        title_like: Optional[str] = None,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> List[AgentConversation]:
        q = self.db.query(AgentConversation).filter(AgentConversation.user_id == user_id)
        q = self._exclude_pregen_scratch(q)
        q = self._apply_search(q, title_like=title_like, search=search)
        return q.order_by(AgentConversation.updated_at.desc()).offset(offset).limit(limit).all()

    def count_conversations(
        self,
        user_id: int,
        title_like: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        q = self.db.query(AgentConversation).filter(AgentConversation.user_id == user_id)
        q = self._exclude_pregen_scratch(q)
        q = self._apply_search(q, title_like=title_like, search=search)
        return q.count()

    @staticmethod
    def _exclude_pregen_scratch(q):
        """Hide throwaway pregen scratch conversations from every user-facing list."""
        return q.filter(
            (AgentConversation.session_key.is_(None))
            | (~AgentConversation.session_key.like(f"{PREGEN_SCRATCH_SESSION_PREFIX}%"))
        )

    def get_conversation_detail(self, user_id: int, conversation_id: int) -> Optional[AgentConversation]:
        return (
            self.db.query(AgentConversation)
            .options(joinedload(AgentConversation.messages))
            .filter(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
            .first()
        )

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        from app.services.chat_utils import chat_image_lifecycle_lock

        with chat_image_lifecycle_lock():
            return self._delete_conversation_locked(user_id, conversation_id)

    def _delete_conversation_locked(self, user_id: int, conversation_id: int) -> bool:
        conv = (
            self.db.query(AgentConversation)
            .filter(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return False
        image_urls: list[str] = []
        for message in conv.messages:
            if not message.image_url:
                continue
            try:
                parsed = json.loads(message.image_url)
            except (json.JSONDecodeError, TypeError):
                parsed = message.image_url
            values = parsed if isinstance(parsed, list) else [parsed]
            image_urls.extend(str(value) for value in values if isinstance(value, str) and value)
        from app.services.chat_utils import (
            _chat_image_file_path,
            finalize_staged_chat_image,
            restore_staged_chat_image,
            stage_chat_image_deletion,
        )

        self._retry_staged_chat_image_deletions_locked(user_id)
        staged_deletions: list[Any] = []
        try:
            for image_url in image_urls:
                image_path = _chat_image_file_path(image_url, user_id)
                if image_path and self._chat_image_path_is_referenced(
                    image_path,
                    None,
                    exclude_conversation_id=conversation_id,
                ):
                    continue
                staged = stage_chat_image_deletion(image_url, user_id)
                if staged:
                    staged_deletions.append(staged)
        except Exception as error:
            for staged in reversed(staged_deletions):
                try:
                    restore_staged_chat_image(staged)
                except Exception:
                    logger.critical(
                        "Failed to restore staged chat image user_id=%s",
                        user_id,
                        exc_info=True,
                    )
            raise RuntimeError("chat_image_deletion_staging_failed") from error

        try:
            self.db.delete(conv)
            self.db.commit()
        except Exception:
            self.db.rollback()
            for staged in reversed(staged_deletions):
                try:
                    restore_staged_chat_image(staged)
                except Exception:
                    logger.critical(
                        "Failed to restore chat image after DB rollback user_id=%s",
                        user_id,
                        exc_info=True,
                    )
            raise

        for staged in staged_deletions:
            try:
                finalize_staged_chat_image(staged)
            except Exception:
                logger.error(
                    "Failed to finalize staged chat image deletion user_id=%s",
                    user_id,
                    exc_info=True,
                )
        return True

    def _chat_image_path_is_referenced(
        self,
        path: str,
        user_id: int | None,
        *,
        exclude_conversation_id: int | None = None,
    ) -> bool:
        from app.services.chat_utils import (
            _chat_image_file_path,
        )

        query = (
            self.db.query(AgentMessage.image_url, AgentConversation.user_id)
            .join(
                AgentConversation,
                AgentConversation.id == AgentMessage.conversation_id,
            )
            .filter(AgentMessage.image_url.isnot(None))
        )
        if user_id is not None:
            query = query.filter(AgentConversation.user_id == user_id)
        if exclude_conversation_id is not None:
            query = query.filter(
                AgentMessage.conversation_id != exclude_conversation_id,
            )

        for raw_image_url, owner_id in query.all():
            try:
                parsed = json.loads(raw_image_url)
            except (json.JSONDecodeError, TypeError):
                parsed = raw_image_url
            values = parsed if isinstance(parsed, list) else [parsed]
            for value in values:
                if not isinstance(value, str) or not value:
                    continue
                referenced_path = _chat_image_file_path(value, int(owner_id))
                if referenced_path == path:
                    return True
        return False

    def _retry_staged_chat_image_deletions_locked(
        self,
        user_id: int | None = None,
    ) -> int:
        from app.services.chat_utils import retry_staged_chat_image_deletions

        return retry_staged_chat_image_deletions(
            user_id,
            is_referenced=lambda path: self._chat_image_path_is_referenced(
                path,
                user_id,
            ),
        )

    def retry_staged_chat_image_deletions(self, user_id: int | None = None) -> int:
        """Reconcile tombstones against current DB references under one lock."""
        from app.services.chat_utils import chat_image_lifecycle_lock

        with chat_image_lifecycle_lock():
            return self._retry_staged_chat_image_deletions_locked(user_id)

    def update_conversation_title(
        self,
        user_id: int,
        conversation_id: int,
        title: str,
    ) -> Optional[AgentConversation]:
        normalized = (title or "").strip()
        if not normalized:
            raise ValueError("标题不能为空")
        conv = (
            self.db.query(AgentConversation)
            .filter(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return None
        conv.title = normalized[:120]
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        image_url: str | None = None,
        meta: Optional[Dict[str, Any]] = None,
        client_turn_id: str | None = None,
        client_turn_user_id: int | None = None,
    ) -> AgentMessage:
        if image_url:
            from app.services.chat_utils import chat_image_lifecycle_lock

            lifecycle_context = chat_image_lifecycle_lock()
        else:
            lifecycle_context = nullcontext()
        with lifecycle_context:
            message_meta = meta
            if role == "assistant" and client_turn_id:
                # Mark the row as partial before any final response metadata is
                # attached. A worker crash can then be taken over safely, while
                # legacy rows with missing metadata remain replay-only.
                message_meta = {
                    **(meta if isinstance(meta, dict) else {}),
                    "client_turn_finalized": (
                        meta.get("client_turn_finalized") is True
                        if isinstance(meta, dict)
                        else False
                    ),
                }
            msg = AgentMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                image_url=image_url,
                meta=message_meta,
                client_turn_id=(
                    self._client_turn_storage_key(client_turn_user_id, client_turn_id)
                    if client_turn_id and client_turn_user_id is not None
                    else client_turn_id
                ),
            )
            self.db.add(msg)
            self.db.commit()
            self.db.refresh(msg)
            # R1 长对话折叠(ships-OFF): assistant 落库 = 回合收尾 → 后台预算下一轮
            # 前情摘要(flag 关/无事件循环/异常 = 全部静默跳过, 零行为变化)。
            if role == "assistant":
                try:
                    from app.services.history_compaction import schedule_fold_refresh
                    schedule_fold_refresh(conversation_id, keep_recent=15)
                except Exception:  # noqa: BLE001
                    pass
            return msg

    def update_user_message_after_image_upload(
        self,
        user_id: int,
        message_id: int,
        *,
        content: str,
        image_url: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[AgentMessage]:
        """Attach uploaded image references atomically with image deletion."""
        from app.services.chat_utils import chat_image_lifecycle_lock

        with chat_image_lifecycle_lock():
            message = (
                self.db.query(AgentMessage)
                .join(
                    AgentConversation,
                    AgentConversation.id == AgentMessage.conversation_id,
                )
                .filter(
                    AgentMessage.id == message_id,
                    AgentMessage.role == "user",
                    AgentConversation.user_id == user_id,
                )
                .first()
            )
            if message is None:
                return None
            message.content = content
            message.image_url = image_url
            message.meta = {
                **(message.meta or {}),
                **(meta or {}),
            }
            self.db.commit()
            self.db.refresh(message)
            return message

    def find_user_message_by_client_turn(
        self,
        user_id: int,
        client_turn_id: str,
    ) -> Optional[AgentMessage]:
        if not client_turn_id:
            return None
        return (
            self.db.query(AgentMessage)
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .filter(
                AgentConversation.user_id == user_id,
                AgentMessage.role == "user",
                AgentMessage.client_turn_id == self._client_turn_storage_key(user_id, client_turn_id),
            )
            .order_by(AgentMessage.id.asc())
            .first()
        )

    def find_assistant_message_by_client_turn(
        self,
        user_id: int,
        client_turn_id: str,
    ) -> Optional[AgentMessage]:
        if not client_turn_id:
            return None
        return (
            self.db.query(AgentMessage)
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .filter(
                AgentConversation.user_id == user_id,
                AgentMessage.role == "assistant",
                AgentMessage.client_turn_id == self._client_turn_storage_key(user_id, client_turn_id),
            )
            .order_by(AgentMessage.id.desc())
            .first()
        )

    def discard_unfinalized_assistant_by_client_turn(
        self,
        user_id: int,
        client_turn_id: str,
    ) -> int:
        """Remove stale partial assistant rows before a crashed turn is resumed."""
        messages = (
            self.db.query(AgentMessage)
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .filter(
                AgentConversation.user_id == user_id,
                AgentMessage.role == "assistant",
                AgentMessage.client_turn_id == self._client_turn_storage_key(user_id, client_turn_id),
            )
            .all()
        )
        stale = [
            message
            for message in messages
            if not (message.meta or {}).get("client_turn_finalized")
        ]
        for message in stale:
            self.db.delete(message)
        if stale:
            self.db.commit()
        return len(stale)

    def save_user_message_once(
        self,
        conversation_id: int,
        user_id: int,
        content: str,
        *,
        client_turn_id: str | None,
        image_url: str | None = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> tuple[AgentMessage, bool]:
        """Persist one client turn exactly once across retries and workers."""
        if not client_turn_id:
            return self.save_message(
                conversation_id,
                "user",
                content,
                image_url=image_url,
                meta=meta,
            ), True
        if image_url:
            from app.services.chat_utils import chat_image_lifecycle_lock

            lifecycle_context = chat_image_lifecycle_lock()
        else:
            lifecycle_context = nullcontext()
        with lifecycle_context:
            existing = self.find_user_message_by_client_turn(user_id, client_turn_id)
            if existing:
                return existing, False
            msg = AgentMessage(
                conversation_id=conversation_id,
                role="user",
                content=content,
                image_url=image_url,
                meta=meta,
                client_turn_id=self._client_turn_storage_key(user_id, client_turn_id),
            )
            self.db.add(msg)
            try:
                self.db.commit()
                self.db.refresh(msg)
                return msg, True
            except IntegrityError:
                self.db.rollback()
                existing = self.find_user_message_by_client_turn(
                    user_id,
                    client_turn_id,
                )
                if existing:
                    return existing, False
                raise

    def build_messages(self, conversation_id: int, limit: int = 20) -> List[Dict[str, str]]:
        history = (
            self.db.query(AgentMessage)
            .filter(AgentMessage.conversation_id == conversation_id)
            # id 决胜: created_at 同刻(时钟回拨/同毫秒并写)时 user/assistant 顺序
            # 不能翻转,否则多轮历史喂给 LLM 时轮次错位。
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
            .all()
        )
        from app.services.health_evidence.delivery import (
            project_persisted_health_messages,
        )

        projected = project_persisted_health_messages(history)
        recent = projected[-limit:] if len(projected) > limit else projected
        out = [{"role": m.role, "content": m.content} for m in recent]
        # R1 长对话折叠(ships-OFF): 溢出部分现状是**静默丢弃**;flag 开且后台已折叠好
        # 恰到最后一条溢出消息时, 前置一条前情摘要(纯增益)。缓存无效/异常 = 现状截断
        # (fail-open, 下一轮后台自愈)。读路径零 LLM 零网络(只读 Redis)。
        if len(history) > limit and getattr(settings, "llm_history_compaction", False):
            try:
                from app.services.history_compaction import (
                    build_summary_message, get_valid_fold_summary,
                )
                overflow_projection = projected[:-limit]
                summary = (
                    None
                    if any(
                        message.sanitized
                        for message in overflow_projection
                    )
                    else get_valid_fold_summary(
                        conversation_id,
                        last_overflow_id=history[-limit - 1].id,
                    )
                )
                if summary:
                    out = [build_summary_message(summary)] + out
            except Exception:  # noqa: BLE001
                pass
        return out

    def build_actionable_references(
        self,
        conversation_id: int,
        *,
        limit: int = 8,
    ) -> tuple[ActionableReference, ...]:
        """Project recent assistant UI state without feeding raw card payloads to LLM."""
        recent = (
            self.db.query(AgentMessage)
            .filter(
                AgentMessage.conversation_id == conversation_id,
                AgentMessage.role == "assistant",
            )
            .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
            .limit(max(1, min(int(limit), 20)))
            .all()
        )
        # The first reference resolves "上面/这餐"; keep the card nearest to the
        # current turn first instead of restoring chronological display order.
        return extract_actionable_references(tuple(recent))

    @staticmethod
    def compress_image_base64(
        base64_data: str,
        image_type: str = "jpeg",
        max_size: int = 1024,
        quality: int = 75,
    ) -> str:
        from app.services.chat_utils import compress_image_base64

        return compress_image_base64(base64_data, image_type, max_size, quality)
