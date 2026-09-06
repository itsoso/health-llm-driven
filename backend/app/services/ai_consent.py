"""Versioned, auditable permission checked immediately before third-party AI I/O.

No positive cache: withdrawal applies to every subsequent dispatch. Unknown
destinations and missing identities fail closed, including background jobs.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
import json
import logging
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.agent_audit_log import AgentAuditLog
from app.models.user import User
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)
POLICY_VERSION = "2026-09-06.1"
CONSENT_KEY = "_ai_consent_v1"
RECIPIENTS = [{
    "id": "aliyun-bailian",
    "name": "阿里云百炼（含通义千问、语音和图像模型服务）",
    "purpose": "处理对话、图片与语音，生成健康管理回复和用户请求的内容",
}, {
    "id": "apple-speech",
    "name": "Apple 系统语音识别",
    "purpose": "在设备采用系统语音识别时处理语音输入；处理可能在设备端或 Apple 服务器进行",
}]
DATA_TYPES = ["发送的对话内容", "主动选择上传的图片、文件与语音", "与本次请求相关的健康记录、个人资料和对话上下文"]
PURPOSE = "按你的请求提供 AI 对话、健康记录整理、图片识别、语音转写与朗读、图像和视频生成。拒绝或撤回后仍可使用不依赖第三方 AI 的功能。"
_ALLOWED_HOSTS = frozenset({
    "dashscope.aliyuncs.com",
    "token-plan.cn-beijing.maas.aliyuncs.com",
})
_UNBOUND = object()
_user_ctx = ContextVar("ai_consent_user", default=_UNBOUND)


@contextmanager
def ai_user_scope(user_id: int | None):
    """Bind one request/job; None explicitly clears inherited identity."""
    token = _user_ctx.set(user_id)
    try:
        yield
    finally:
        _user_ctx.reset(token)


async def ai_request_scope():
    """FastAPI dependency: isolate identity from unrelated requests/tasks."""
    from app.services.llm.usage_tracker import _user_id_ctx
    usage_token = _user_id_ctx.set(None)
    with ai_user_scope(None):
        try:
            yield
        finally:
            _user_id_ctx.reset(usage_token)


def bind_ai_user(user_id: int) -> None:
    _user_ctx.set(int(user_id))


def is_disclosed_destination(destination: str | None) -> bool:
    try:
        parsed = urlsplit(destination or "")
        return (parsed.scheme in {"https", "wss"} and parsed.hostname in _ALLOWED_HOSTS
                and not parsed.username and not parsed.password and parsed.port in {None, 443})
    except (TypeError, ValueError):
        return False


def is_disclosed_model(entry) -> bool:
    from app.config import settings
    field = {"tokenplan": "tokenplan_base_url", "openai-proxy": "openai_base_url",
             "moonshot": "moonshot_base_url", "zhipu": "zhipu_base_url",
             "langbridge-proxy": "langbridge_gateway_base_url"}.get(entry.provider)
    return bool(field) and is_disclosed_destination(getattr(settings, field, None))


def _settings_dict(value) -> dict:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value) if isinstance(value, dict) else {}


def get_ai_consent(db: Session, user_id: int) -> dict:
    # Select the scalar column: an ORM identity-map copy could predate withdrawal.
    row = db.query(UserProfile.privacy_settings).filter(UserProfile.user_id == user_id).first()
    record = _settings_dict(row[0] if row else None).get(CONSENT_KEY, {})
    record = record if isinstance(record, dict) else {}
    accepted = record.get("accepted") is True and record.get("policy_version") == POLICY_VERSION
    return {
        "policy_version": POLICY_VERSION,
        "accepted": accepted,
        "accepted_at": record.get("accepted_at") if accepted else None,
        "recipients": RECIPIENTS,
        "data_types": DATA_TYPES,
        "purpose": PURPOSE,
    }


def lock_consent_owner(db: Session, user_id: int) -> None:
    # A stable parent row also serializes the first profile creation. Profile
    # privacy updates take this same lock so they cannot resurrect old consent.
    if not db.query(User.id).filter(User.id == user_id).with_for_update().first():
        raise HTTPException(status_code=401, detail="用户不存在")


def merge_public_privacy(current, submitted) -> dict:
    from app.schemas.user_profile import PrivacySettings
    result = _settings_dict(current)
    # Even internal callers cannot overwrite the consent key through this helper.
    result.update({k: v for k, v in (submitted or {}).items() if k in PrivacySettings.model_fields})
    return result


def update_ai_consent(db: Session, user_id: int, accepted: bool, policy_version: str) -> dict:
    if accepted and policy_version != POLICY_VERSION:
        raise HTTPException(status_code=409, detail={"code": "ai_consent_policy_changed", "message": "AI 数据使用说明已更新，请重新阅读后确认"})
    lock_consent_owner(db, user_id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).populate_existing().first()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    now = datetime.now(UTC).isoformat()
    privacy = _settings_dict(profile.privacy_settings)
    record = {"accepted": accepted, "policy_version": POLICY_VERSION, "accepted_at": now if accepted else None, "updated_at": now}
    privacy[CONSENT_KEY] = record
    profile.privacy_settings = privacy
    db.add(AgentAuditLog(user_id=user_id, agent_type="ai_consent", action="grant" if accepted else "revoke", result_detail={**record, "recipients": RECIPIENTS, "data_types": DATA_TYPES}))
    db.commit()
    return get_ai_consent(db, user_id)


def require_ai_consent(user_id: int | None = None, *, destination: str | None = None) -> None:
    """Raise before I/O if identity, current consent, or recipient is unverified."""
    if user_id is None:
        user_id = _user_ctx.get()
        if user_id is _UNBOUND:
            from app.services.llm.usage_tracker import get_caller_user_id
            user_id = get_caller_user_id()
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise HTTPException(status_code=403, detail={"code": "ai_consent_required", "message": "请先确认 AI 数据使用授权"})
    if destination is not None:
        if not is_disclosed_destination(destination):
            raise HTTPException(status_code=403, detail={"code": "ai_recipient_not_disclosed", "message": "此 AI 服务尚未完成数据使用披露，暂不可用"})
    try:
        with SessionLocal() as db:
            db.info["app_user_id"] = user_id
            user = db.query(User.id).filter(User.id == user_id, User.is_active.is_(True), User.is_approved.is_(True)).first()
            accepted = bool(user) and get_ai_consent(db, user_id)["accepted"]
    except Exception as exc:
        logger.error("AI consent verification unavailable: error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "ai_consent_unavailable", "message": "暂时无法核验 AI 授权，请稍后再试"}) from exc
    if not accepted:
        raise HTTPException(status_code=403, detail={"code": "ai_consent_required", "message": "请先确认 AI 数据使用授权"})
