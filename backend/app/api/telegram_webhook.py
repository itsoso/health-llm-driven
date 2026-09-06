"""
Telegram Webhook — 用户通过 Telegram 给 bot 发文字/语音 → 自动解析成健康行为.

输入支持:
  - 文字: 直接处理
  - 语音 (voice/audio): getFile + 下载 ogg → 已披露 ASR 服务 → 当文字处理

意图分流 (services.telegram_inbound.classify_intent):
  directive (硬性指令: '戒酒 30 天')      → user_directives (老路径)
  record    (健康录入: '吃了 2 个鸡蛋')   → health_record 工具 (LLM tool calling)
  query/chat (查询/闲聊: '昨晚怎么样')   → LLM 简短回复

设置 Telegram bot webhook 指向:
  https://health.executor.life/api/v1/telegram/webhook?secret={TELEGRAM_WEBHOOK_SECRET}

授权: 只有 telegram_advisor_chat_id 配置的 chat 能用 (单用户场景).
未来多用户时通过 chat_id ↔ user_id 映射表扩展.

注: 涉及医疗判断的硬性指令应在用户和其执业医师确认后再录入.

一次性配置:
  curl "https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://health.executor.life/api/v1/telegram/webhook?secret=XXX"
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ai_consent import ai_user_scope, require_ai_consent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


def _verify_secret(request: Request, secret: Optional[str]) -> None:
    from app.config import settings
    expected = settings.telegram_webhook_secret
    if not expected:
        raise HTTPException(503, "Telegram webhook not configured")
    if secret != expected:
        raise HTTPException(403, "invalid secret")


async def _reply_to_telegram(chat_id: str, text: str, reply_to_message_id: Optional[int] = None) -> None:
    """简易 Telegram 回复 (复用现有 push service)."""
    try:
        from app.services.notification.telegram_push import TelegramPushService
        svc = TelegramPushService()
        if not svc.configured and not chat_id:
            return
        await svc.send_message(text=text, chat_id=str(chat_id))
    except Exception as e:  # noqa: BLE001
        logger.warning("[telegram-webhook] reply failed error_type=%s", type(e).__name__)


async def _reply_ai_permission_error(chat_id: str, exc: HTTPException) -> dict:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = detail.get("code")
    messages = {
        "ai_consent_required": "请先在小巴健康 App 的设置中阅读并确认 AI 数据使用授权；撤回后需重新确认才能使用 AI。",
        "ai_consent_unavailable": "暂时无法核验 AI 数据使用授权，请稍后重试。",
        "ai_recipient_not_disclosed": "当前 AI 服务尚未完成数据使用披露，暂不可用，请在 App 中使用已披露的服务。",
    }
    if code not in messages:
        code = "handler_error"
    await _reply_to_telegram(chat_id, messages.get(code, "暂时无法处理，请稍后重试。"))
    return {"ok": False, "reason": code}


@router.post("/webhook", summary="Telegram bot webhook (健康助理入口)")
async def telegram_webhook(
    request: Request,
    secret: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """处理 Telegram 推送的 update."""
    _verify_secret(request, secret)

    try:
        update: Dict[str, Any] = await request.json()
    except Exception as e:
        logger.warning("[telegram-webhook] JSON parse failed error_type=%s", type(e).__name__)
        return {"ok": False, "reason": "bad_json"}

    msg = update.get("message") or update.get("edited_message") or {}
    if not msg:
        return {"ok": True, "ignored": "no_message"}

    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    text = (msg.get("text") or "").strip()
    voice = msg.get("voice") or msg.get("audio")  # voice = 录音条, audio = 上传的音频文件
    message_id = msg.get("message_id")

    from app.config import settings
    advisor_chat_id = str(
        settings.telegram_advisor_chat_id
        or settings.telegram_doctor_chat_id
        or ""
    )
    advisor_user_id = (
        settings.telegram_advisor_user_id
        or settings.telegram_doctor_user_id
    )

    if not advisor_chat_id or not advisor_user_id:
        logger.info("[telegram-webhook] advisor chat 未配置, 忽略所有消息")
        return {"ok": True, "ignored": "advisor_not_configured"}

    if chat_id != advisor_chat_id:
        logger.info("[telegram-webhook] unconfigured chat ignored")
        return {"ok": True, "ignored": "not_advisor_chat"}

    # ── 语音消息 → STT → text ──
    if voice:
        from app.services.telegram_inbound import (
            download_telegram_file, transcribe_voice_bytes,
        )
        file_id = voice.get("file_id")
        if not file_id:
            await _reply_to_telegram(chat_id, "⚠️ 未拿到 voice file_id")
            return {"ok": False, "reason": "no_file_id"}
        audio = await download_telegram_file(file_id)
        if not audio:
            await _reply_to_telegram(chat_id, "⚠️ 语音下载失败")
            return {"ok": False, "reason": "download_failed"}
        # Only the server-configured advisor mapping, checked above, may bind AI
        # identity. A payload user_id never participates in this authorization.
        try:
            with ai_user_scope(int(advisor_user_id)):
                require_ai_consent()
                text = await transcribe_voice_bytes(audio, ext="ogg") or ""
        except HTTPException as exc:
            return await _reply_ai_permission_error(chat_id, exc)
        if not text:
            await _reply_to_telegram(chat_id, "⚠️ 语音识别失败, 试试发文字")
            return {"ok": False, "reason": "transcribe_failed"}
        # 给用户回执显示识别结果, 让用户能看到 STT 出错时的错误
        await _reply_to_telegram(chat_id, f"📝 识别: {text}")

    if not text:
        return {"ok": True, "ignored": "no_text"}

    # 太短可能是 emoji / 表情包, 跳过
    if len(text) < 2:
        return {"ok": True, "ignored": "text_too_short"}

    # 不处理命令 (/start, /help)
    if text.startswith("/"):
        await _reply_to_telegram(
            chat_id,
            "ℹ️ 我能帮你:\n"
            "  📝 录健康数据 ('体重 71.2'/'吃了 2 个鸡蛋')\n"
            "  💬 回答健康问题 ('昨晚睡得怎么样')\n"
            "  ⚙️ 接收硬指令 ('戒酒 30 天')\n\n"
            "可以发**语音**, 我会自动转写.",
        )
        return {"ok": True, "ignored": "command"}
    if message_id is None or not str(message_id).strip():
        logger.warning("[telegram-webhook] missing provider message_id")
        return {"ok": False, "reason": "missing_message_id"}

    # 主路径: 自动意图分流
    from app.services.telegram_inbound import handle_inbound_text
    try:
        with ai_user_scope(int(advisor_user_id)):
            # Commands and empty messages have already returned above. This
            # entry invokes AI, so report permission failures before parsing.
            require_ai_consent()
            reply = await handle_inbound_text(
                db,
                int(advisor_user_id),
                text,
                source_message_id=str(message_id) if message_id is not None else None,
                source_conversation_id=chat_id,
            )
    except HTTPException as exc:
        return await _reply_ai_permission_error(chat_id, exc)
    except Exception as e:
        logger.error("[telegram-webhook] handler failed error_type=%s", type(e).__name__)
        await _reply_to_telegram(chat_id, "暂时无法处理，请稍后重试。")
        return {"ok": False, "reason": "handler_error"}

    await _reply_to_telegram(chat_id, reply)
    logger.info(f"[telegram-webhook] handled user={advisor_user_id} reply_len={len(reply)}")
    return {"ok": True, "reply": reply[:200]}


@router.get("/webhook/status", summary="webhook 配置状态 (无需认证, 但 secret 鉴权)")
def webhook_status(
    secret: Optional[str] = Query(None),
    request: Request = None,
):
    _verify_secret(request, secret)
    from app.config import settings
    return {
        "advisor_chat_configured": bool(
            settings.telegram_advisor_chat_id or settings.telegram_doctor_chat_id
        ),
        "advisor_user_id": (
            settings.telegram_advisor_user_id or settings.telegram_doctor_user_id
        ),
        "bot_token_configured": bool(settings.telegram_bot_token),
        "webhook_secret_configured": bool(settings.telegram_webhook_secret),
    }
