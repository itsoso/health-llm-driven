"""Owner-scoped AIGC media-job lifecycle for Xiaoba.

The service deliberately separates an authenticated user's source image from
the Model Studio provider boundary: image generation gets an in-memory data
URI; image-to-video gets a short-lived, public HTTPS capability URL. Provider
outputs are copied into Xiaoba's private storage before the user sees them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_consent import ai_user_scope, require_ai_consent
from app.models.agent_audit_log import AgentAuditLog
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.aigc_media_job import AIGCMediaJob
from app.models.aigc_media_confirmation import AIGCMediaConfirmation
from app.models.user import User
from app.services.aigc_media_service import (
    AIGCMediaConfigurationError,
    AIGCMediaProvider,
    AIGCMediaProviderError,
    AIGCMediaProviderIndeterminateError,
    _extract_result_urls,
)
from app.services.aigc_media_capabilities import (
    validate_video_spec,
    video_capability_for,
)
from app.services.chat_utils import (
    build_short_lived_chat_image_provider_url,
    read_owned_chat_image_data_uri,
)
from app.services.private_uploads import build_signed_private_upload_url
from app.services.aigc_media_policy import AIGCMediaPolicyError, validate_aigc_media_policy
from app.services.tenant_crypto import decrypt_aigc_confirmation_for, encrypt_aigc_confirmation_for
from app.utils.runtime_data import upload_dir


logger = logging.getLogger(__name__)

MEDIA_KINDS = frozenset({"text_to_image", "image_to_image", "text_to_video", "image_to_video"})
IMAGE_KINDS = frozenset({"text_to_image", "image_to_image"})
VIDEO_KINDS = MEDIA_KINDS - IMAGE_KINDS
SOURCE_IMAGE_KINDS = frozenset({"image_to_image", "image_to_video"})
# submission_unknown is terminal from a client polling perspective: we cannot
# prove whether Model Studio accepted a paid request, so retries are unsafe.
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "submission_unknown"})
_MUTABLE_ACTIVE_STATUSES = frozenset({"dispatching", "queued", "running"})
_BILLABLE_OPEN_STATUSES = frozenset({"dispatching", "queued", "running", "submission_unknown"})
AIGC_SAFE_RETRY_ERROR_CODES = frozenset(
    {
        "configuration_invalid",
        "provider_auth_failed",
        "provider_rate_limited",
        "provider_request_rejected",
        "provider_unavailable",
        "provider_request_failed",
        "missing_provider_task",
    }
)
_AIGC_UPLOAD_ROOT = upload_dir() / "aigc"
_MAX_IMAGE_RESULT_BYTES = 20 * 1024 * 1024
_MAX_VIDEO_RESULT_BYTES = 100 * 1024 * 1024
# A creation card is part of durable chat history, so a 10-minute lifetime made
# a normal "come back later" flow look actionable while the server had already
# rejected it. New drafts remain directly confirmable for a day. A fresh owner
# click may also reclaim an expired draft within the same window; that click is
# the new explicit consent and the atomic status claim still prevents duplicate
# provider spend.
_CONFIRMATION_TTL = timedelta(hours=24)
_CONFIRMATION_RECOVERY_WINDOW = timedelta(hours=24)
# Confirmation claiming is a short database lease, not a permanent state. The
# durable job row is committed before any provider call, so a claim with no
# matching job after this window is safe to release for a fresh owner click.
_CONFIRMATION_CLAIM_LEASE = timedelta(seconds=30)
_REVIEW_TOKEN_TTL = timedelta(minutes=10)
_REVIEW_TOKEN_CONTEXT = b"aigc-media-prompt-review-v1"


def is_recoverable_provider_result_missing_job(job: AIGCMediaJob) -> bool:
    """Return whether a historical video result can be re-polled safely.

    This only reuses an existing provider task after an older client release
    misread Wan's successful ``output.video_url`` response. It never creates a
    second billable request.
    """
    return bool(
        job.status == "failed"
        and job.kind in VIDEO_KINDS
        and job.provider_task_id
        and job.provider_error_code == "provider_result_missing"
    )


class AIGCMediaJobError(RuntimeError):
    """Base class for errors that the AIGC API can safely surface."""


class AIGCMediaJobRequestError(AIGCMediaJobError):
    """The caller asked for an invalid or unauthorized media operation."""


class AIGCMediaJobConflict(AIGCMediaJobError):
    """The requested state transition cannot be applied."""


class AIGCMediaJobQuotaExceeded(AIGCMediaJobError):
    """A configured cost or concurrency boundary rejected a new dispatch."""


@dataclass(frozen=True)
class AIGCMediaJobRequest:
    kind: Literal["text_to_image", "image_to_image", "text_to_video", "image_to_video"]
    prompt: str
    purpose: str
    source_message_id: int | None = None
    source_image_index: int = 0
    duration_seconds: int = 5
    ratio: str = "9:16"
    resolution: str = "720P"
    # Only the service sets this internal field when it issues a confirmation.
    # It freezes the billable provider/model choice across the confirmation TTL.
    model: str | None = None


ProviderFactory = Callable[[], AIGCMediaProvider]
ResultDownloader = Callable[[str, str], Awaitable[tuple[bytes, str, str]]]
ResultHTTPClientFactory = Callable[[], httpx.AsyncClient]


def configured_aigc_media_provider() -> AIGCMediaProvider:
    """Create the image provider plus the configured video provider."""
    video_provider = str(settings.aigc_video_provider or "").strip().lower()
    if video_provider == "tokenplan":
        video_api_key = settings.tokenplan_api_key
        video_api_base_url = settings.tokenplan_aigc_base_url
        text_to_video_model = settings.tokenplan_aigc_text_to_video_model
        image_to_video_model = settings.tokenplan_aigc_image_to_video_model
    elif video_provider == "model_studio":
        video_api_key = settings.dashscope_aigc_api_key
        video_api_base_url = settings.dashscope_aigc_base_url
        text_to_video_model = settings.dashscope_aigc_text_to_video_model
        image_to_video_model = settings.dashscope_aigc_image_to_video_model
    else:
        raise AIGCMediaConfigurationError("Unsupported AIGC video provider")
    return AIGCMediaProvider(
        api_key=settings.dashscope_aigc_api_key,
        api_base_url=settings.dashscope_aigc_base_url,
        image_model=settings.dashscope_aigc_image_model,
        text_to_video_model=text_to_video_model,
        image_to_video_model=image_to_video_model,
        video_api_key=video_api_key,
        video_api_base_url=video_api_base_url,
        video_provider=video_provider,
        blocked_api_keys=(settings.tokenplan_api_key,),
    )


def is_aigc_provider_configured_for_model(model: str) -> bool:
    selected_model = str(model or "").strip()
    video_provider = str(settings.aigc_video_provider or "").strip().lower()
    if selected_model.startswith("happyhorse-") and video_provider == "tokenplan":
        return bool(str(settings.tokenplan_api_key or "").strip())
    return bool(str(settings.dashscope_aigc_api_key or "").strip())


class AIGCMediaJobService:
    def __init__(
        self,
        db: Session,
        *,
        provider_factory: ProviderFactory = configured_aigc_media_provider,
        result_downloader: ResultDownloader | None = None,
        result_http_client_factory: ResultHTTPClientFactory | None = None,
    ) -> None:
        self.db = db
        self._provider_factory = provider_factory
        self._result_http_client_factory = result_http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), follow_redirects=False)
        )
        self._result_downloader = result_downloader or self._download_provider_result

    def _recover_confirmation_job(
        self,
        *,
        user_id: int,
        confirmation: AIGCMediaConfirmation,
    ) -> AIGCMediaJob | None:
        job = None
        if confirmation.job_id:
            job = (
                self.db.query(AIGCMediaJob)
                .filter(
                    AIGCMediaJob.id == confirmation.job_id,
                    AIGCMediaJob.user_id == int(user_id),
                )
                .first()
            )
        if job is None:
            job = (
                self.db.query(AIGCMediaJob)
                .filter(
                    AIGCMediaJob.user_id == int(user_id),
                    AIGCMediaJob.idempotency_key == f"aigc-confirmation:{confirmation.id}",
                )
                .first()
            )
        if job is not None and (
            confirmation.status != "dispatched"
            or confirmation.job_id != job.id
        ):
            confirmation.status = "dispatched"
            confirmation.job_id = job.id
            self.db.commit()
        return job

    def _release_stale_confirmation_claim(
        self,
        *,
        user_id: int,
        confirmation: AIGCMediaConfirmation,
        now: datetime,
    ) -> bool:
        if confirmation.status != "dispatching" or confirmation.job_id:
            return False
        consumed_at = confirmation.consumed_at
        if consumed_at is not None:
            normalized = consumed_at if consumed_at.tzinfo else consumed_at.replace(tzinfo=UTC)
            if normalized > now - _CONFIRMATION_CLAIM_LEASE:
                return False
        released = (
            self.db.query(AIGCMediaConfirmation)
            .filter(
                AIGCMediaConfirmation.id == confirmation.id,
                AIGCMediaConfirmation.user_id == int(user_id),
                AIGCMediaConfirmation.status == "dispatching",
                AIGCMediaConfirmation.job_id.is_(None),
                or_(
                    AIGCMediaConfirmation.consumed_at.is_(None),
                    AIGCMediaConfirmation.consumed_at <= now - _CONFIRMATION_CLAIM_LEASE,
                ),
            )
            .update(
                {"status": "pending", "consumed_at": None},
                synchronize_session=False,
            )
        )
        self.db.commit()
        if released:
            self.db.refresh(confirmation)
        return bool(released)

    async def issue_confirmation(
        self,
        *,
        user_id: int,
        request: AIGCMediaJobRequest,
        conversation_id: int | None = None,
    ) -> AIGCMediaConfirmation:
        """Create a server-bound AIGC draft without contacting Model Studio."""
        self._validate_request(request)
        normalized_purpose = validate_aigc_media_policy(purpose=request.purpose, prompt=request.prompt)
        bound_request = replace(
            request,
            purpose=normalized_purpose,
            model=self._model_for_kind(request.kind),
        )
        if bound_request.kind in SOURCE_IMAGE_KINDS:
            # Validate ownership at draft time, then bind the exact message and
            # image index into the immutable confirmation record.
            self._load_owned_source_url(user_id, bound_request)
        now = datetime.now(UTC)
        bound_conversation_id = self._owned_conversation_id(
            user_id,
            conversation_id,
        ) if conversation_id is not None else self._conversation_id_for_source(
            user_id,
            bound_request.source_message_id,
        )
        confirmation = AIGCMediaConfirmation(
            id=f"aigc_confirm_{uuid4().hex}",
            user_id=int(user_id),
            conversation_id=bound_conversation_id,
            source_message_id=bound_request.source_message_id,
            source_image_index=bound_request.source_image_index if bound_request.kind in SOURCE_IMAGE_KINDS else None,
            kind=bound_request.kind,
            purpose=bound_request.purpose,
            model=bound_request.model,
            prompt_ciphertext=encrypt_aigc_confirmation_for(int(user_id), bound_request.prompt.strip()),
            prompt_fingerprint=self._fingerprint(user_id=user_id, request=bound_request),
            duration_seconds=int(bound_request.duration_seconds),
            ratio=bound_request.ratio,
            status="pending",
            created_at=now,
            expires_at=now + _CONFIRMATION_TTL,
        )
        self.db.add(confirmation)
        self.db.commit()
        self.db.refresh(confirmation)
        return confirmation

    async def confirm_and_dispatch(
        self,
        *,
        user_id: int,
        confirmation_id: str,
        review_token: str,
        duration_seconds: int | None = None,
    ) -> AIGCMediaJob:
        """Atomically consume a user confirmation and start exactly one job."""
        now = datetime.now(UTC)
        candidate = (
            self.db.query(AIGCMediaConfirmation)
            .filter(
                AIGCMediaConfirmation.id == str(confirmation_id),
                AIGCMediaConfirmation.user_id == int(user_id),
            )
            .first()
        )
        if not candidate:
            raise AIGCMediaJobRequestError("AIGC 确认不存在或无权使用")
        self._verify_review_token(
            user_id=int(user_id),
            confirmation=candidate,
            review_token=review_token,
            now=now,
        )
        requested_duration = (
            int(duration_seconds)
            if duration_seconds is not None
            else int(candidate.duration_seconds)
        )
        if candidate.kind in VIDEO_KINDS:
            try:
                validate_video_spec(
                    model=candidate.model,
                    kind=candidate.kind,  # type: ignore[arg-type]
                    duration_seconds=requested_duration,
                    ratio=candidate.ratio,
                    resolution="720P",
                )
            except ValueError as exc:
                raise AIGCMediaJobRequestError(str(exc)) from exc
        elif duration_seconds is not None:
            raise AIGCMediaJobRequestError("图片创作不支持视频时长设置")

        recovered_job = self._recover_confirmation_job(
            user_id=user_id,
            confirmation=candidate,
        )
        if recovered_job is not None:
            return recovered_job
        self._release_stale_confirmation_claim(
            user_id=user_id,
            confirmation=candidate,
            now=now,
        )

        claim_values: dict[str, object] = {
            "status": "dispatching",
            "consumed_at": now,
            "expires_at": now + _CONFIRMATION_TTL,
        }
        if candidate.kind in VIDEO_KINDS:
            claim_values["duration_seconds"] = requested_duration
        recovery_cutoff = now - _CONFIRMATION_RECOVERY_WINDOW
        claimed = (
            self.db.query(AIGCMediaConfirmation)
            .filter(
                AIGCMediaConfirmation.id == str(confirmation_id),
                AIGCMediaConfirmation.user_id == int(user_id),
                AIGCMediaConfirmation.status.in_(("pending", "expired")),
                AIGCMediaConfirmation.created_at >= recovery_cutoff,
                AIGCMediaConfirmation.job_id.is_(None),
            )
            .update(claim_values, synchronize_session=False)
        )
        self.db.commit()
        confirmation = (
            self.db.query(AIGCMediaConfirmation)
            .filter(
                AIGCMediaConfirmation.id == str(confirmation_id),
                AIGCMediaConfirmation.user_id == int(user_id),
            )
            .first()
        )
        if not confirmation:
            raise AIGCMediaJobRequestError("AIGC 确认不存在或无权使用")
        if not claimed:
            # A process can die after persisting the provider job but before it
            # writes confirmation.job_id.  The confirmation ID is also the
            # job's unique idempotency key, so recover that durable job instead
            # of leaving the owner with a permanently spinning draft or
            # attempting a second provider call.
            recovered_job = self._recover_confirmation_job(
                user_id=user_id,
                confirmation=confirmation,
            )
            if recovered_job:
                return recovered_job
            if confirmation.status == "deduplicated":
                matching_job = (
                    self.db.query(AIGCMediaJob)
                    .filter(
                        AIGCMediaJob.user_id == int(user_id),
                        AIGCMediaJob.request_fingerprint == confirmation.prompt_fingerprint,
                    )
                    .order_by(AIGCMediaJob.created_at.desc())
                    .first()
                )
                if matching_job:
                    return matching_job
            expires_at = confirmation.expires_at
            if expires_at.tzinfo is None:  # SQLite test/dev compatibility
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < now:
                if confirmation.status == "pending":
                    confirmation.status = "expired"
                    self.db.commit()
                raise AIGCMediaJobConflict("该 AIGC 确认已过期，请重新发起")
            if confirmation.status == "dispatching":
                raise AIGCMediaJobConflict("AIGC 任务正在提交，请稍后查看")
            raise AIGCMediaJobConflict("该 AIGC 确认已使用，请重新发起")

        try:
            request = AIGCMediaJobRequest(
                kind=confirmation.kind,  # type: ignore[arg-type]
                purpose=confirmation.purpose,
                prompt=decrypt_aigc_confirmation_for(int(user_id), confirmation.prompt_ciphertext),
                source_message_id=confirmation.source_message_id,
                source_image_index=confirmation.source_image_index or 0,
                duration_seconds=confirmation.duration_seconds,
                ratio=confirmation.ratio,
                resolution="720P",
                model=confirmation.model,
            )
            confirmation.prompt_fingerprint = self._fingerprint(
                user_id=user_id,
                request=request,
            )
            self.db.commit()
            job = await self._dispatch_confirmed(
                user_id=user_id,
                request=request,
                confirmation_id=confirmation.id,
                conversation_id=confirmation.conversation_id,
            )
        except AIGCMediaJobQuotaExceeded:
            # This is a temporary local cost/concurrency gate, not a consumed
            # provider request. Keep the original explicit confirmation usable.
            confirmation.status = "pending"
            confirmation.consumed_at = None
            self.db.commit()
            raise
        except AIGCMediaJobError:
            # The provider may reject after the durable job/audit record has
            # been created. Link that failed job to the consumed confirmation so
            # the caller gets an honest terminal projection, not an orphaned
            # billable attempt with a permanently spinning confirmation card.
            job = (
                self.db.query(AIGCMediaJob)
                .filter(
                    AIGCMediaJob.user_id == int(user_id),
                    AIGCMediaJob.idempotency_key == f"aigc-confirmation:{confirmation.id}",
                )
                .first()
            )
            if job:
                confirmation.status = "dispatched"
                confirmation.job_id = job.id
                self.db.commit()
                return job
            confirmation.status = "failed"
            self.db.commit()
            raise
        except Exception:
            # A failed dispatch must never leave an indeterminate confirmation
            # that can later be replayed. The user can draft again deliberately.
            confirmation.status = "failed"
            self.db.commit()
            raise
        existing_confirmation = (
            self.db.query(AIGCMediaConfirmation.id)
            .filter(
                AIGCMediaConfirmation.job_id == job.id,
                AIGCMediaConfirmation.id != confirmation.id,
            )
            .first()
        )
        # A job has a one-to-one confirmation ledger relation. A later,
        # byte-for-byte duplicate confirmation returns the same job to the
        # caller but remains explicitly unlinked rather than violating that
        # invariant or creating a second provider request.
        if existing_confirmation:
            confirmation.status = "deduplicated"
            confirmation.job_id = None
        else:
            confirmation.status = "dispatched"
            confirmation.job_id = job.id
        self.db.commit()
        self.db.refresh(job)
        return job

    async def _dispatch_confirmed(
        self,
        *,
        user_id: int,
        request: AIGCMediaJobRequest,
        confirmation_id: str,
        conversation_id: int | None = None,
    ) -> AIGCMediaJob:
        self._validate_request(request)
        require_ai_consent(user_id)
        fingerprint = self._fingerprint(user_id=user_id, request=request)
        idempotency_key = f"aigc-confirmation:{confirmation_id}"
        existing = (
            self.db.query(AIGCMediaJob)
            .filter(
                AIGCMediaJob.user_id == int(user_id),
                AIGCMediaJob.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            return existing
        matching_job = self._find_matching_fingerprint_job(user_id=user_id, fingerprint=fingerprint)
        if matching_job:
            # A separate confirmation with the same immutable draft must open
            # the prior job, including failed/unknown outcomes. Re-sending it
            # would risk a second paid provider task with no user-visible
            # distinction between the two confirmations.
            return matching_job

        source_url, source_data_uri = self._prepare_owned_source(user_id=user_id, request=request)

        # The advisory lock is intentionally acquired before the second
        # fingerprint lookup. Two confirmations can race through the initial
        # lookup, but only the winner may reserve capacity and insert a job.
        self._acquire_dispatch_lock()
        matching_job = self._find_matching_fingerprint_job(user_id=user_id, fingerprint=fingerprint)
        if matching_job:
            return matching_job
        self._reserve_dispatch_capacity(user_id=int(user_id), lock_acquired=True)

        now = datetime.now(UTC)
        job = AIGCMediaJob(
            id=f"aigc_{uuid4().hex}",
            user_id=int(user_id),
            conversation_id=(
                int(conversation_id)
                if conversation_id is not None
                else self._conversation_id_for_source(user_id, request.source_message_id)
            ),
            source_message_id=request.source_message_id,
            source_image_index=request.source_image_index if request.kind in SOURCE_IMAGE_KINDS else None,
            kind=request.kind,
            # Persist before any provider call. A process crash or response
            # loss afterwards cannot be replayed as a new billable task.
            status="dispatching",
            progress=0,
            model=request.model or self._model_for_kind(request.kind),
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            result_metadata={
                "request": self._request_spec_metadata(request),
            },
            created_at=now,
        )
        # The accepted job and the user's explicit provider disclosure are one
        # durable record. Keep the audit payload intentionally coarse: prompt,
        # source URL, and source bytes must never leave the protected job flow.
        audit = AgentAuditLog(
            user_id=int(user_id),
            agent_type="aigc_media",
            action="provider_dispatch_confirmed",
            result_summary=f"confirmed AIGC provider dispatch job={job.id} kind={job.kind}",
            result_detail={
                "job_id": job.id,
                "kind": job.kind,
                "model": job.model,
                "source_attached": request.kind in SOURCE_IMAGE_KINDS,
                "duration_seconds": (
                    int(request.duration_seconds)
                    if request.kind in VIDEO_KINDS
                    else None
                ),
                "resolution": (
                    request.resolution
                    if request.kind in VIDEO_KINDS
                    else None
                ),
            },
        )
        self.db.add_all([job, audit])
        try:
            self.db.commit()
        except IntegrityError:
            # SQLite/dev has no cross-process advisory lock; the database
            # uniqueness rule remains the final anti-duplicate guarantee.
            self.db.rollback()
            matching_job = self._find_matching_fingerprint_job(user_id=user_id, fingerprint=fingerprint)
            if matching_job:
                return matching_job
            raise
        self.db.refresh(job)

        return await self._submit_provider_job(
            job=job,
            request=request,
            source_url=source_url,
            source_data_uri=source_data_uri,
            started_at=now,
        )

    async def retry_failed(self, *, user_id: int, job_id: str) -> AIGCMediaJob:
        """Retry one definitively rejected provider submission in-place.

        The existing ledger row and confirmation remain the idempotency boundary.
        Unknown submissions and any job with a provider task ID are deliberately
        excluded because creating another provider task could duplicate spend.
        """
        require_ai_consent(user_id)
        job = (
            self.db.query(AIGCMediaJob)
            .filter(AIGCMediaJob.id == str(job_id), AIGCMediaJob.user_id == int(user_id))
            .first()
        )
        if not job:
            raise AIGCMediaJobRequestError("AIGC 任务不存在或无权使用")
        if not self._is_safely_retryable(job):
            raise AIGCMediaJobConflict("该任务不能重新提交，以避免重复生成或重复计费")

        confirmation = (
            self.db.query(AIGCMediaConfirmation)
            .filter(
                AIGCMediaConfirmation.job_id == job.id,
                AIGCMediaConfirmation.user_id == int(user_id),
            )
            .first()
        )
        if not confirmation:
            raise AIGCMediaJobConflict("原创作草稿不可用，请重新描述后发起")
        request = AIGCMediaJobRequest(
            kind=confirmation.kind,  # type: ignore[arg-type]
            purpose=confirmation.purpose,
            prompt=decrypt_aigc_confirmation_for(int(user_id), confirmation.prompt_ciphertext),
            source_message_id=confirmation.source_message_id,
            source_image_index=confirmation.source_image_index or 0,
            duration_seconds=confirmation.duration_seconds,
            ratio=confirmation.ratio,
            resolution="720P",
            model=confirmation.model,
        )
        source_url, source_data_uri = self._prepare_owned_source(user_id=user_id, request=request)

        self._acquire_dispatch_lock()
        self._reserve_dispatch_capacity(user_id=int(user_id), lock_acquired=True)
        now = datetime.now(UTC)
        claimed = (
            self.db.query(AIGCMediaJob)
            .filter(
                AIGCMediaJob.id == job.id,
                AIGCMediaJob.user_id == int(user_id),
                AIGCMediaJob.status == "failed",
                AIGCMediaJob.provider_task_id.is_(None),
                AIGCMediaJob.provider_error_code.in_(AIGC_SAFE_RETRY_ERROR_CODES),
            )
            .update(
                {
                    "status": "dispatching",
                    "progress": 0,
                    "provider_error_code": None,
                    "error_message": None,
                    "started_at": None,
                    "completed_at": None,
                    "last_provider_checked_at": None,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        if not claimed:
            self.db.refresh(job)
            raise AIGCMediaJobConflict("任务状态已变化，请查看最新结果")
        self.db.refresh(job)
        self.db.add(AgentAuditLog(
            user_id=int(user_id),
            agent_type="aigc_media",
            action="provider_dispatch_retried",
            result_summary=f"explicit AIGC retry job={job.id} kind={job.kind}",
            result_detail={"job_id": job.id, "kind": job.kind, "model": job.model},
        ))
        self.db.commit()

        try:
            return await self._submit_provider_job(
                job=job,
                request=request,
                source_url=source_url,
                source_data_uri=source_data_uri,
                started_at=now,
            )
        except AIGCMediaJobError:
            # A provider rejection is a truthful job projection, not a transport
            # failure of this API. Return it so every client renders one state.
            self.db.refresh(job)
            return job

    async def _submit_provider_job(
        self,
        *,
        job: AIGCMediaJob,
        request: AIGCMediaJobRequest,
        source_url: str | None,
        source_data_uri: str | None,
        started_at: datetime,
    ) -> AIGCMediaJob:
        provider: AIGCMediaProvider | None = None
        provider_request_started = False
        provider_accepted = False
        try:
            require_ai_consent(job.user_id)
            provider = self._provider_factory()
            if request.kind in IMAGE_KINDS:
                provider_request_started = True
                with ai_user_scope(job.user_id):
                    urls = await provider.generate_image(
                        prompt=request.prompt,
                        image_data_uri=source_data_uri,
                        model=job.model,
                    )
                provider_accepted = True
                await self._complete_from_provider_url(job, urls[0], kind=request.kind)
            else:
                provider_request_started = True
                with ai_user_scope(job.user_id):
                    task = await provider.create_video_task(
                        kind=request.kind,
                        prompt=request.prompt,
                        source_url=source_url,
                        duration_seconds=request.duration_seconds,
                        ratio=request.ratio,
                        resolution=request.resolution,
                        model=job.model,
                    )
                provider_accepted = True
                job.provider_task_id = task.task_id
                job.status = "queued" if task.status == "PENDING" else "running"
                job.progress = 10 if job.status == "queued" else 25
                job.started_at = started_at
                job.last_provider_checked_at = started_at
                self.db.commit()
                self.db.refresh(job)
            return job
        except HTTPException:
            # Consent rejection proves no new vendor dispatch was permitted;
            # preserve the permission response instead of claiming unknown I/O.
            self._mark_failed(job, "ai_consent_required", "请先确认 AI 数据使用授权，再重新发起创作。")
            raise
        except AIGCMediaProviderIndeterminateError as exc:
            self._mark_submission_unknown(job, "provider_submission_unknown")
            logger.warning(
                "[aigc_media] provider outcome unknown job_id=%s kind=%s error=%s",
                job.id,
                job.kind,
                type(exc).__name__,
            )
            self.db.refresh(job)
            return job
        except AIGCMediaConfigurationError as exc:
            message = "创作服务配置异常，已通知管理员。"
            self._mark_failed(job, "configuration_invalid", message)
            logger.error(
                "[aigc_media] dispatch configuration invalid job_id=%s kind=%s",
                job.id,
                job.kind,
            )
            raise AIGCMediaJobError(message) from exc
        except AIGCMediaProviderError as exc:
            error_code = (
                exc.error_code
                if exc.error_code in AIGC_SAFE_RETRY_ERROR_CODES
                else "provider_request_failed"
            )
            message = self._provider_failure_message(error_code)
            self._mark_failed(job, error_code, message)
            logger.warning(
                "[aigc_media] dispatch rejected job_id=%s kind=%s code=%s status=%s",
                job.id,
                job.kind,
                error_code,
                exc.status_code,
            )
            raise AIGCMediaJobError(message) from exc
        except OSError as exc:
            if provider_accepted or provider_request_started:
                self._mark_submission_unknown(job, "provider_result_persistence_unknown")
                raise AIGCMediaJobError("创作结果保存状态待核验") from exc
            message = "创作服务暂时不可用，可以稍后重试。"
            self._mark_failed(job, "provider_request_failed", message)
            raise AIGCMediaJobError(message) from exc
        except Exception as exc:
            # A crash after the request starts can lose a provider task ID. Do
            # not turn that uncertainty into a replay opportunity.
            if provider_request_started:
                self.db.rollback()
                persisted = self.db.get(AIGCMediaJob, job.id)
                if persisted:
                    self._mark_submission_unknown(persisted, "provider_submission_unknown")
                raise AIGCMediaJobError("百炼媒体提交结果待核验") from exc
            raise
        finally:
            if provider is not None:
                try:
                    await provider.aclose()
                except Exception as exc:  # noqa: BLE001 - never obscure durable job outcome
                    logger.warning("[aigc_media] provider close failed error=%s", type(exc).__name__)

    def _prepare_owned_source(
        self,
        *,
        user_id: int,
        request: AIGCMediaJobRequest,
    ) -> tuple[str | None, str | None]:
        source_url: str | None = None
        source_data_uri: str | None = None
        if request.kind not in SOURCE_IMAGE_KINDS:
            return source_url, source_data_uri
        source_url = self._load_owned_source_url(user_id, request)
        try:
            if request.kind == "image_to_image":
                source_data_uri = read_owned_chat_image_data_uri(source_url, user_id)
            else:
                source_url = build_short_lived_chat_image_provider_url(
                    source_url,
                    user_id,
                    public_base_url=settings.site_base_url,
                    ttl_seconds=settings.dashscope_aigc_source_url_ttl_seconds,
                )
        except ValueError as exc:
            raise AIGCMediaJobRequestError("源图片当前不可用于生成，请重新上传后再试") from exc
        return source_url, source_data_uri

    @staticmethod
    def _is_safely_retryable(job: AIGCMediaJob) -> bool:
        return bool(
            job.status == "failed"
            and not job.provider_task_id
            and job.provider_error_code in AIGC_SAFE_RETRY_ERROR_CODES
        )

    @staticmethod
    def _provider_failure_message(error_code: str) -> str:
        if error_code == "provider_auth_failed":
            return "创作服务授权异常，已通知管理员。"
        if error_code == "provider_rate_limited":
            return "创作服务当前繁忙，可以稍后重试。"
        if error_code == "provider_unavailable":
            return "创作服务暂时不可用，可以稍后重试。"
        if error_code == "provider_request_rejected":
            return "本次创作请求未被服务接受，可以调整描述后重试。"
        return "创作任务未能提交，可以稍后重试。"

    async def refresh(self, job: AIGCMediaJob) -> AIGCMediaJob:
        if job.status in TERMINAL_STATUSES:
            if not is_recoverable_provider_result_missing_job(job):
                return job
            if not self._reopen_provider_result_missing_job(job):
                self.db.refresh(job)
                return job
            self.db.refresh(job)
        if not job.provider_task_id:
            if job.status == "dispatching":
                self._mark_submission_unknown(job, "provider_submission_unknown")
            else:
                self._mark_failed(job, "missing_provider_task", "任务未能提交，请重新生成")
            return job
        if not self._claim_provider_poll_lease(job):
            self.db.refresh(job)
            return job
        provider: AIGCMediaProvider | None = None
        try:
            provider = self._provider_factory()
            payload = await provider.get_task(job.provider_task_id, model=job.model)
            output = payload.get("output") if isinstance(payload, dict) else {}
            provider_status = str((output or {}).get("task_status") or "UNKNOWN").upper()
            if provider_status == "PENDING":
                self._update_active_job(job, status="queued", progress=max(job.progress, 10))
            elif provider_status == "RUNNING":
                self._update_active_job(job, status="running", progress=max(job.progress, 50))
            elif provider_status == "SUCCEEDED":
                urls = _extract_result_urls(payload)
                if not urls:
                    self._mark_failed(job, "provider_result_missing", "生成结果不可用，请重新生成")
                else:
                    await self._complete_from_provider_url(job, urls[0], kind=job.kind)
            elif provider_status in {"CANCELED", "CANCELLED"}:
                self._update_active_job(
                    job,
                    status="cancelled",
                    progress=0,
                    cancelled_at=datetime.now(UTC),
                )
            else:
                self._mark_failed(job, "provider_task_failed", "生成未完成，请重新生成")
        except (AIGCMediaConfigurationError, AIGCMediaProviderError, OSError) as exc:
            logger.warning(
                "[aigc_media] refresh failed job_id=%s error=%s",
                job.id,
                type(exc).__name__,
            )
            # Polling is advisory. A network/configuration interruption is not
            # proof that an already accepted Wan task failed, so retain its
            # active state and let the scheduler/client retry.
            pass
        finally:
            if provider is not None:
                await provider.aclose()
        self.db.refresh(job)
        return job

    async def cancel(self, job: AIGCMediaJob) -> AIGCMediaJob:
        if job.status in TERMINAL_STATUSES:
            raise AIGCMediaJobConflict("任务已完成，不能取消")
        if not job.provider_task_id:
            raise AIGCMediaJobConflict("任务尚未提交，不能取消")
        provider = self._provider_factory()
        try:
            await provider.cancel_task(job.provider_task_id, model=job.model)
        except (AIGCMediaConfigurationError, AIGCMediaProviderError) as exc:
            logger.warning(
                "[aigc_media] cancel failed job_id=%s error=%s",
                job.id,
                type(exc).__name__,
            )
            raise AIGCMediaJobError("取消任务失败，请稍后重试") from exc
        finally:
            await provider.aclose()
        if not self._update_active_job(
            job,
            status="cancelled",
            progress=0,
            cancelled_at=datetime.now(UTC),
        ):
            self.db.refresh(job)
            raise AIGCMediaJobConflict("任务状态已变化，不能取消")
        self.db.refresh(job)
        return job

    def project(self, job: AIGCMediaJob) -> dict:
        result_metadata = (
            dict(job.result_metadata)
            if isinstance(job.result_metadata, dict)
            else {}
        )
        request_spec = result_metadata.get("request")
        if not isinstance(request_spec, dict):
            request_spec = None
        result_url = None
        if job.output_filename:
            result_url = build_signed_private_upload_url(
                "aigc", job.user_id, job.output_filename
            )
        return {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "progress": job.progress,
            "model": job.model,
            "spec": request_spec,
            "result": {
                "media_type": job.output_media_type,
                "url": result_url,
                "byte_size": result_metadata.get("byte_size"),
            },
            "error_message": job.error_message if job.status in {"failed", "submission_unknown"} else None,
            "error_code": job.provider_error_code if job.status in {"failed", "submission_unknown"} else None,
            "can_retry": self._is_safely_retryable(job),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def persist_job_card(
        self,
        *,
        user_id: int,
        job: AIGCMediaJob,
        confirmation_id: str | None = None,
    ) -> bool:
        """Replace a durable confirmation card with its authoritative job.

        The confirmation click used to update only component-local state. A
        reload therefore resurrected the stale draft and lost retryability.
        Persist only stable projection fields; signed result URLs are fetched
        from the owner-scoped job endpoint when the card mounts.
        """
        confirmation_ids = {str(confirmation_id).strip()} if confirmation_id else set()
        confirmations = (
            self.db.query(AIGCMediaConfirmation)
            .filter(
                AIGCMediaConfirmation.user_id == int(user_id),
                or_(
                    AIGCMediaConfirmation.job_id == job.id,
                    AIGCMediaConfirmation.id == str(confirmation_id),
                ) if confirmation_id else AIGCMediaConfirmation.job_id == job.id,
            )
            .all()
        )
        confirmation_ids.update(str(item.id) for item in confirmations)
        conversation_ids = {
            int(value)
            for value in [job.conversation_id, *(item.conversation_id for item in confirmations)]
            if value is not None
        }
        query = (
            self.db.query(AgentMessage)
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .filter(
                AgentConversation.user_id == int(user_id),
                AgentMessage.role == "assistant",
            )
        )
        if conversation_ids:
            query = query.filter(AgentMessage.conversation_id.in_(conversation_ids))
        messages = query.order_by(AgentMessage.id.desc()).limit(100).all()
        projection = self.project(job)
        stable_data = {
            "job_id": job.id,
            "kind": job.kind,
            "status": projection["status"],
            "progress": projection["progress"],
            "title": "小巴创作",
            "spec": projection["spec"],
            "error_message": projection["error_message"],
            "error_code": projection["error_code"],
            "can_retry": projection["can_retry"],
        }
        replacement = {"type": "aigc_media_job", "data": stable_data}
        changed_any = False
        for message in messages:
            meta = dict(message.meta or {})
            cards = list(meta.get("cards") or [])
            changed = False
            next_cards: list = []
            for card in cards:
                data = card.get("data") if isinstance(card, dict) else None
                is_confirmation = bool(
                    isinstance(data, dict)
                    and card.get("type") == "aigc_media_confirmation"
                    and str(data.get("confirmation_id") or "") in confirmation_ids
                )
                is_job = bool(
                    isinstance(data, dict)
                    and card.get("type") == "aigc_media_job"
                    and str(data.get("job_id") or data.get("id") or "") == job.id
                )
                if is_confirmation or is_job:
                    if not any(
                        isinstance(existing, dict)
                        and existing.get("type") == "aigc_media_job"
                        and str((existing.get("data") or {}).get("job_id") or "") == job.id
                        for existing in next_cards
                    ):
                        next_cards.append(replacement)
                    changed = True
                else:
                    next_cards.append(card)
            if not changed:
                continue
            meta["cards"] = next_cards
            message.meta = meta
            changed_any = True
        if changed_any:
            self.db.commit()
        return changed_any

    def confirmation_projection(self, *, user_id: int, confirmation_id: str) -> dict:
        """Return an owner-only prompt review state and its existing job.

        The plaintext prompt is never persisted in chat/card metadata. It is
        decrypted only for this authenticated projection, together with a
        short-lived stateless token that the confirm endpoint must verify.
        """
        confirmation = (
            self.db.query(AIGCMediaConfirmation)
            .filter(
                AIGCMediaConfirmation.id == str(confirmation_id),
                AIGCMediaConfirmation.user_id == int(user_id),
            )
            .first()
        )
        if not confirmation:
            raise AIGCMediaJobRequestError("AIGC 确认不存在或无权使用")
        now = datetime.now(UTC)
        job = self._recover_confirmation_job(
            user_id=user_id,
            confirmation=confirmation,
        )
        if job is None:
            self._release_stale_confirmation_claim(
                user_id=user_id,
                confirmation=confirmation,
                now=now,
            )
        expires_at = confirmation.expires_at
        if expires_at.tzinfo is None:  # SQLite test/dev compatibility
            expires_at = expires_at.replace(tzinfo=UTC)
        if confirmation.status == "pending" and expires_at < now:
            confirmation.status = "expired"
            self.db.commit()
        created_at = confirmation.created_at
        if created_at.tzinfo is None:  # SQLite test/dev compatibility
            created_at = created_at.replace(tzinfo=UTC)
        can_confirm = bool(
            confirmation.job_id is None
            and confirmation.status in {"pending", "expired"}
            and created_at >= now - _CONFIRMATION_RECOVERY_WINDOW
        )
        if job is None and confirmation.status == "deduplicated":
            job = self._find_matching_fingerprint_job(
                user_id=int(user_id),
                fingerprint=confirmation.prompt_fingerprint,
            )
        outbound_prompt: str | None = None
        review_token: str | None = None
        review_expires_at: str | None = None
        if can_confirm:
            try:
                candidate_prompt = decrypt_aigc_confirmation_for(
                    int(user_id),
                    confirmation.prompt_ciphertext,
                )
            except Exception as exc:  # noqa: BLE001 - crypto errors fail closed
                logger.error(
                    "AIGC prompt review decrypt failed confirmation=%s user=%s error_type=%s",
                    confirmation.id,
                    int(user_id),
                    type(exc).__name__,
                )
                can_confirm = False
            else:
                if (
                    not isinstance(candidate_prompt, str)
                    or not candidate_prompt.strip()
                    or len(candidate_prompt) > 5000
                ):
                    logger.error(
                        "AIGC prompt review rejected empty prompt confirmation=%s user=%s",
                        confirmation.id,
                        int(user_id),
                    )
                    can_confirm = False
                else:
                    outbound_prompt = candidate_prompt
                    token_expires_at = min(now + _REVIEW_TOKEN_TTL, now + _CONFIRMATION_RECOVERY_WINDOW)
                    review_token = self._issue_review_token(
                        user_id=int(user_id),
                        confirmation=confirmation,
                        expires_at=token_expires_at,
                    )
                    review_expires_at = token_expires_at.isoformat()
        return {
            "id": confirmation.id,
            "status": confirmation.status,
            "can_confirm": can_confirm,
            "requires_reconfirmation": confirmation.status == "expired" and can_confirm,
            "expires_at": expires_at.isoformat(),
            "outbound_prompt": outbound_prompt,
            "review_token": review_token,
            "review_expires_at": review_expires_at,
            "spec": self._confirmation_spec(confirmation),
            "job": self.project(job) if job is not None else None,
        }

    @staticmethod
    def _review_provider_route(confirmation: AIGCMediaConfirmation) -> str:
        if confirmation.kind in IMAGE_KINDS:
            return "model_studio"
        return str(settings.aigc_video_provider or "").strip().lower()

    @classmethod
    def _review_binding(
        cls,
        *,
        user_id: int,
        confirmation: AIGCMediaConfirmation,
    ) -> str:
        canonical = json.dumps(
            {
                "user_id": int(user_id),
                "confirmation_id": confirmation.id,
                "kind": confirmation.kind,
                "purpose": confirmation.purpose,
                "model": confirmation.model,
                "provider_route": cls._review_provider_route(confirmation),
                "prompt_ciphertext": confirmation.prompt_ciphertext,
                "source_message_id": confirmation.source_message_id,
                "source_image_index": confirmation.source_image_index,
                "ratio": confirmation.ratio,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        key = hmac.new(
            settings.secret_key.encode("utf-8"),
            _REVIEW_TOKEN_CONTEXT,
            hashlib.sha256,
        ).digest()
        return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _review_token_b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _review_token_b64decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(
            f"{value}{padding}".encode("ascii"),
            altchars=b"-_",
            validate=True,
        )

    @classmethod
    def _issue_review_token(
        cls,
        *,
        user_id: int,
        confirmation: AIGCMediaConfirmation,
        expires_at: datetime,
    ) -> str:
        payload = json.dumps(
            {
                "v": 1,
                "uid": int(user_id),
                "cid": confirmation.id,
                "binding": cls._review_binding(
                    user_id=int(user_id),
                    confirmation=confirmation,
                ),
                "exp": int(expires_at.timestamp()),
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded_payload = cls._review_token_b64encode(payload)
        key = hmac.new(
            settings.secret_key.encode("utf-8"),
            _REVIEW_TOKEN_CONTEXT,
            hashlib.sha256,
        ).digest()
        signature = hmac.new(
            key,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded_payload}.{cls._review_token_b64encode(signature)}"

    @classmethod
    def _verify_review_token(
        cls,
        *,
        user_id: int,
        confirmation: AIGCMediaConfirmation,
        review_token: str,
        now: datetime,
    ) -> None:
        error = AIGCMediaJobRequestError("请先审阅完整创作描述后再确认")
        token = str(review_token or "").strip()
        if not token or len(token) > 4096:
            raise error
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            supplied_signature = cls._review_token_b64decode(encoded_signature)
            key = hmac.new(
                settings.secret_key.encode("utf-8"),
                _REVIEW_TOKEN_CONTEXT,
                hashlib.sha256,
            ).digest()
            expected_signature = hmac.new(
                key,
                encoded_payload.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise error
            payload = json.loads(
                cls._review_token_b64decode(encoded_payload).decode("utf-8")
            )
            expected_binding = cls._review_binding(
                user_id=int(user_id),
                confirmation=confirmation,
            )
            valid = bool(
                isinstance(payload, dict)
                and payload.get("v") == 1
                and payload.get("uid") == int(user_id)
                and payload.get("cid") == confirmation.id
                and isinstance(payload.get("binding"), str)
                and hmac.compare_digest(payload["binding"], expected_binding)
                and isinstance(payload.get("exp"), int)
                and payload["exp"] > int(now.timestamp())
            )
            if not valid:
                raise error
        except AIGCMediaJobRequestError:
            raise
        except (UnicodeError, ValueError, TypeError, KeyError):
            raise error from None

    async def _complete_from_provider_url(self, job: AIGCMediaJob, url: str, *, kind: str) -> None:
        data, media_type, extension = await self._result_downloader(url, kind)
        filename = self._write_private_result(job.user_id, data, extension)
        result_metadata = (
            dict(job.result_metadata)
            if isinstance(job.result_metadata, dict)
            else {}
        )
        result_metadata["byte_size"] = len(data)
        completed = self._update_active_job(
            job,
            status="succeeded",
            progress=100,
            output_filename=filename,
            output_media_type=media_type,
            result_metadata=result_metadata,
            completed_at=datetime.now(UTC),
            provider_error_code=None,
            error_message=None,
        )
        if not completed:
            # Another worker/user cancellation won the state transition. Never
            # expose the orphaned private output after a cancelled task.
            self._delete_private_result(job.user_id, filename)
        self.db.refresh(job)
        if completed and kind in VIDEO_KINDS:
            await self._notify_video_completion(job)

    async def _notify_video_completion(self, job: AIGCMediaJob) -> None:
        """Send a generic, deduplicated completion push without health content."""
        from app.models.notification import NotificationChannel
        from app.services.notification.push_service import PushService

        try:
            result = await PushService(self.db).send_notification(
                user_id=int(job.user_id),
                notification_type="aigc_media_completed",
                title="小巴创作已完成",
                content="你的创作结果已准备好，打开小巴即可查看。",
                data={
                    "rule_id": f"aigc_media_completed:{job.id}",
                    "job_id": job.id,
                    "kind": job.kind,
                    "deep_link": "/(tabs)/chat",
                },
                channels=[NotificationChannel.IOS_APNS.value],
                respect_quiet_hours=True,
                severity="info",
                dedup_window_hours=168,
            )
            logger.info(
                "[aigc_media] completion notification job_id=%s delivered=%s",
                job.id,
                bool(result.get("success")),
            )
        except Exception as exc:  # noqa: BLE001
            # The private result is already durable. Push is an optional wake-up
            # surface and must never roll back or mislabel a successful job.
            logger.warning(
                "[aigc_media] completion notification failed job_id=%s error=%s",
                job.id,
                type(exc).__name__,
            )

    def _load_owned_source_url(self, user_id: int, request: AIGCMediaJobRequest) -> str:
        if request.source_message_id is None:
            raise AIGCMediaJobRequestError("图像生成需要选择当前对话中的一张图片")
        message = (
            self.db.query(AgentMessage)
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .filter(
                AgentMessage.id == int(request.source_message_id),
                AgentConversation.user_id == int(user_id),
            )
            .first()
        )
        if not message or not message.image_url:
            raise AIGCMediaJobRequestError("源图片不存在或无权使用")
        try:
            parsed = json.loads(message.image_url)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AIGCMediaJobRequestError("源图片不可用") from exc
        urls = parsed if isinstance(parsed, list) else [parsed]
        if not 0 <= int(request.source_image_index) < len(urls):
            raise AIGCMediaJobRequestError("源图片不存在或无权使用")
        source_url = str(urls[int(request.source_image_index)] or "")
        if not source_url:
            raise AIGCMediaJobRequestError("源图片不可用")
        return source_url

    def _conversation_id_for_source(self, user_id: int, source_message_id: int | None) -> int | None:
        if source_message_id is None:
            return None
        row = (
            self.db.query(AgentConversation.id)
            .join(AgentMessage, AgentMessage.conversation_id == AgentConversation.id)
            .filter(AgentMessage.id == int(source_message_id), AgentConversation.user_id == int(user_id))
            .first()
        )
        return int(row[0]) if row else None

    def _owned_conversation_id(self, user_id: int, conversation_id: int) -> int:
        owned = (
            self.db.query(AgentConversation.id)
            .filter(
                AgentConversation.id == int(conversation_id),
                AgentConversation.user_id == int(user_id),
            )
            .first()
        )
        if not owned:
            raise AIGCMediaJobRequestError("AIGC 对话不存在或无权使用")
        return int(owned[0])

    @staticmethod
    def _validate_request(request: AIGCMediaJobRequest) -> None:
        if request.kind not in MEDIA_KINDS:
            raise AIGCMediaJobRequestError("不支持的 AIGC 生成类型")
        if not str(request.prompt or "").strip() or len(request.prompt.strip()) > 5000:
            raise AIGCMediaJobRequestError("生成描述不能为空且不能超过 5000 字")
        try:
            validate_aigc_media_policy(purpose=request.purpose, prompt=request.prompt)
        except AIGCMediaPolicyError as exc:
            raise AIGCMediaJobRequestError(str(exc)) from exc
        if request.kind in SOURCE_IMAGE_KINDS and request.source_message_id is None:
            raise AIGCMediaJobRequestError("图像生成需要选择当前对话中的一张图片")
        if request.model is not None and (not request.model.strip() or len(request.model.strip()) > 80):
            raise AIGCMediaJobRequestError("AIGC 模型配置无效")
        if request.kind in VIDEO_KINDS:
            model = request.model or AIGCMediaJobService._model_for_kind(request.kind)
            try:
                validate_video_spec(
                    model=model,
                    kind=request.kind,  # type: ignore[arg-type]
                    duration_seconds=request.duration_seconds,
                    ratio=request.ratio,
                    resolution=request.resolution,
                )
            except ValueError as exc:
                raise AIGCMediaJobRequestError(str(exc)) from exc
        elif request.ratio not in {"16:9", "9:16", "1:1", "4:3", "3:4"}:
            raise AIGCMediaJobRequestError("不支持的视频比例")

    @staticmethod
    def _fingerprint(*, user_id: int, request: AIGCMediaJobRequest) -> str:
        canonical = json.dumps(
            {
                "user_id": int(user_id),
                "kind": request.kind,
                "purpose": request.purpose,
                "prompt": request.prompt.strip(),
                "source_message_id": request.source_message_id,
                "source_image_index": request.source_image_index,
                "duration_seconds": request.duration_seconds,
                "ratio": request.ratio,
                "resolution": request.resolution,
                "model": request.model,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        # A plain SHA-256 of a short health prompt is dictionary-attackable if
        # a database dump leaks. The key is already required for production
        # authentication, so use it to make the idempotency fingerprint opaque.
        return hmac.new(
            settings.secret_key.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _request_spec_metadata(request: AIGCMediaJobRequest) -> dict:
        if request.kind not in VIDEO_KINDS:
            return {}
        model = request.model or AIGCMediaJobService._model_for_kind(request.kind)
        capability = video_capability_for(
            model=model,
            kind=request.kind,  # type: ignore[arg-type]
        )
        spec = {
            "duration_seconds": int(request.duration_seconds),
            "resolution": request.resolution.upper(),
            "generates_audio": capability.generates_audio,
            "ratio_mode": "fixed" if capability.supports_ratio else "source",
        }
        if capability.supports_ratio:
            spec["ratio"] = request.ratio
        return spec

    @staticmethod
    def _confirmation_spec(confirmation: AIGCMediaConfirmation) -> dict | None:
        if confirmation.kind not in VIDEO_KINDS:
            return None
        capability = video_capability_for(
            model=confirmation.model,
            kind=confirmation.kind,  # type: ignore[arg-type]
        )
        spec = {
            "duration_seconds": int(confirmation.duration_seconds),
            "duration_options": list(capability.selectable_duration_seconds),
            "resolution": capability.default_resolution,
            "generates_audio": capability.generates_audio,
            "ratio_mode": "fixed" if capability.supports_ratio else "source",
        }
        if capability.supports_ratio:
            spec["ratio"] = confirmation.ratio
        return spec

    @staticmethod
    def _model_for_kind(kind: str) -> str:
        if kind in IMAGE_KINDS:
            return settings.dashscope_aigc_image_model
        video_provider = str(settings.aigc_video_provider or "").strip().lower()
        if video_provider == "tokenplan":
            if kind == "image_to_video":
                return settings.tokenplan_aigc_image_to_video_model
            return settings.tokenplan_aigc_text_to_video_model
        if video_provider != "model_studio":
            raise AIGCMediaConfigurationError("Unsupported AIGC video provider")
        if kind == "image_to_video":
            return settings.dashscope_aigc_image_to_video_model
        return settings.dashscope_aigc_text_to_video_model

    def _mark_failed(self, job: AIGCMediaJob, error_code: str, message: str) -> None:
        self._update_active_job(
            job,
            status="failed",
            provider_error_code=error_code,
            error_message=message,
            completed_at=datetime.now(UTC),
        )

    def _mark_submission_unknown(self, job: AIGCMediaJob, error_code: str) -> None:
        self._update_active_job(
            job,
            status="submission_unknown",
            provider_error_code=error_code,
            error_message="提交结果待核验，已停止自动重试以避免重复生成",
        )

    def _acquire_dispatch_lock(self) -> None:
        """Serialize account-wide billable AIGC dispatch on PostgreSQL."""
        bind = self.db.get_bind()
        if bind.dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 872319})

    def _reserve_dispatch_capacity(self, *, user_id: int, lock_acquired: bool = False) -> None:
        """Atomically apply shared provider cost/concurrency limits.

        PostgreSQL serializes this low-volume reservation with an advisory
        transaction lock. SQLite is used only in tests/dev and executes the
        same checks serially in its local process. The durable job is inserted
        and committed immediately afterwards, before the lock is released.
        """
        if not lock_acquired:
            self._acquire_dispatch_lock()

        active_filter = AIGCMediaJob.status.in_(tuple(_BILLABLE_OPEN_STATUSES))
        global_active = self.db.query(func.count(AIGCMediaJob.id)).filter(active_filter).scalar() or 0
        user_active = (
            self.db.query(func.count(AIGCMediaJob.id))
            .filter(AIGCMediaJob.user_id == int(user_id), active_filter)
            .scalar()
            or 0
        )
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_dispatches = (
            self.db.query(func.count(AIGCMediaJob.id))
            .filter(AIGCMediaJob.user_id == int(user_id), AIGCMediaJob.created_at >= day_start)
            .scalar()
            or 0
        )
        if global_active >= max(1, int(settings.dashscope_aigc_max_active_jobs_global)):
            raise AIGCMediaJobQuotaExceeded("百炼创作任务繁忙，请稍后再试")
        is_admin = bool(
            self.db.query(User.is_admin)
            .filter(User.id == int(user_id))
            .scalar()
        )
        if is_admin:
            return
        if user_active >= max(1, int(settings.dashscope_aigc_max_active_jobs_per_user)):
            raise AIGCMediaJobQuotaExceeded("你已有进行中的创作任务，请等待结果后再试")
        if daily_dispatches >= max(1, int(settings.dashscope_aigc_max_dispatches_per_user_per_day)):
            raise AIGCMediaJobQuotaExceeded("今日创作次数已达上限，请明天再试")

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def _claim_provider_poll_lease(self, job: AIGCMediaJob) -> bool:
        """Claim task and account-level poll capacity before an HTTP request.

        The lease is committed before contacting Model Studio. This keeps
        long-running HTTP calls out of a database transaction while making the
        rate boundary visible to concurrent Web, Mobile, Mac, and Celery
        callers.
        """
        self._acquire_provider_poll_lock()
        now = datetime.now(UTC)
        global_minimum = max(1, int(settings.dashscope_aigc_global_poll_min_interval_seconds))
        latest_global_poll = (
            self.db.query(func.max(AIGCMediaJob.last_provider_checked_at))
            .filter(AIGCMediaJob.status.in_(tuple(_MUTABLE_ACTIVE_STATUSES)))
            .scalar()
        )
        if latest_global_poll and now - self._as_utc(latest_global_poll) < timedelta(seconds=global_minimum):
            self.db.rollback()
            return False

        task_minimum = max(1, int(settings.dashscope_aigc_poll_min_interval_seconds))
        task_cutoff = now - timedelta(seconds=task_minimum)
        affected = (
            self.db.query(AIGCMediaJob)
            .filter(
                AIGCMediaJob.id == job.id,
                AIGCMediaJob.user_id == job.user_id,
                AIGCMediaJob.status.in_(tuple(_MUTABLE_ACTIVE_STATUSES)),
                or_(
                    AIGCMediaJob.last_provider_checked_at.is_(None),
                    AIGCMediaJob.last_provider_checked_at <= task_cutoff,
                ),
            )
            .update({"last_provider_checked_at": now}, synchronize_session=False)
        )
        self.db.commit()
        return bool(affected)

    def _acquire_provider_poll_lock(self) -> None:
        """Serialize the account-wide poll lease on PostgreSQL."""
        bind = self.db.get_bind()
        if bind.dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 872320})

    def _find_matching_fingerprint_job(self, *, user_id: int, fingerprint: str) -> AIGCMediaJob | None:
        return (
            self.db.query(AIGCMediaJob)
            .filter(
                AIGCMediaJob.user_id == int(user_id),
                AIGCMediaJob.request_fingerprint == fingerprint,
            )
            .order_by(AIGCMediaJob.created_at.desc())
            .first()
        )

    def _update_active_job(self, job: AIGCMediaJob, **values: object) -> bool:
        """Compare-and-set an active job so terminal states cannot resurrect."""
        affected = (
            self.db.query(AIGCMediaJob)
            .filter(
                AIGCMediaJob.id == job.id,
                AIGCMediaJob.user_id == job.user_id,
                AIGCMediaJob.status.in_(tuple(_MUTABLE_ACTIVE_STATUSES)),
            )
            .update(values, synchronize_session=False)
        )
        self.db.commit()
        return bool(affected)

    def _reopen_provider_result_missing_job(self, job: AIGCMediaJob) -> bool:
        """Re-poll a falsely failed historical video task without resubmission."""
        affected = (
            self.db.query(AIGCMediaJob)
            .filter(
                AIGCMediaJob.id == job.id,
                AIGCMediaJob.user_id == job.user_id,
                AIGCMediaJob.status == "failed",
                AIGCMediaJob.kind.in_(tuple(VIDEO_KINDS)),
                AIGCMediaJob.provider_task_id.is_not(None),
                AIGCMediaJob.provider_error_code == "provider_result_missing",
            )
            .update(
                {
                    "status": "running",
                    "completed_at": None,
                    "last_provider_checked_at": None,
                    "provider_error_code": None,
                    "error_message": None,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return bool(affected)

    async def _download_provider_result(self, url: str, kind: str) -> tuple[bytes, str, str]:
        parsed = urlsplit(str(url or ""))
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host.endswith((".aliyuncs.com", ".aliyun.com")):
            raise AIGCMediaProviderError("Model Studio returned an unsupported result URL")
        max_bytes = _MAX_IMAGE_RESULT_BYTES if kind in IMAGE_KINDS else _MAX_VIDEO_RESULT_BYTES
        try:
            async with self._result_http_client_factory() as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise AIGCMediaProviderError("Model Studio result download failed")
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) <= 0 or int(content_length) > max_bytes:
                                raise AIGCMediaProviderError("Model Studio result download failed")
                        except ValueError as exc:
                            raise AIGCMediaProviderError("Model Studio result download failed") from exc
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise AIGCMediaProviderError("Model Studio result download failed")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        except httpx.HTTPError as exc:
            raise AIGCMediaProviderError("Model Studio result download failed") from exc
        if not content:
            raise AIGCMediaProviderError("Model Studio result download failed")
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "video/mp4": "mp4",
        }
        extension = extensions.get(media_type)
        expected_prefix = "image/" if kind in IMAGE_KINDS else "video/"
        if not extension or not media_type.startswith(expected_prefix):
            raise AIGCMediaProviderError("Model Studio result format is unsupported")
        return content, media_type, extension

    @staticmethod
    def _write_private_result(user_id: int, data: bytes, extension: str) -> str:
        owner_dir = _AIGC_UPLOAD_ROOT / str(int(user_id))
        owner_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.{extension}"
        destination = owner_dir / filename
        temporary = owner_dir / f".{filename}.{uuid4().hex}.tmp"
        try:
            with open(temporary, "xb") as file_handle:
                file_handle.write(data)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return filename

    @staticmethod
    def _delete_private_result(user_id: int, filename: str) -> None:
        destination = _AIGC_UPLOAD_ROOT / str(int(user_id)) / filename
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            logger.warning("[aigc_media] failed to delete orphaned output user_id=%s", user_id)
