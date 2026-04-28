"""
Telegram Webhook — 医生回复 → user_directives.

设置 Telegram bot webhook 指向:
  https://health.executor.life/api/v1/telegram/webhook?secret={TELEGRAM_WEBHOOK_SECRET}

工作流:
  医生在 Telegram 给 bot 发文字消息
  → bot 转发到我们的 webhook
  → 我们识别 chat_id == TELEGRAM_DOCTOR_CHAT_ID
  → directive_parser.parse_and_store
  → 用 telegram_push 回一句 "✅ 已记录 N 条 directive: ..."

不识别图片/语音 (后续接 OCR/STT 再说). reply_to_message 也忽略 — 直接全文解析.

一次性配置:
  curl "https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://health.executor.life/api/v1/telegram/webhook?secret=XXX"
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


def _verify_secret(request: Request, secret: Optional[str]) -> None:
    from app.config import settings
    expected = settings.telegram_webhook_secret
    if not expected:
        # 没配 secret 就认为 webhook 没启用, 拒绝所有
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
        logger.warning(f"[telegram-webhook] 回复失败 (旁路): {e}")


@router.post("/webhook", summary="Telegram bot webhook (医生回复入口)")
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
        logger.warning(f"[telegram-webhook] JSON parse failed: {e}")
        return {"ok": False, "reason": "bad_json"}

    msg = update.get("message") or update.get("edited_message") or {}
    if not msg:
        return {"ok": True, "ignored": "no_message"}

    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    text = (msg.get("text") or "").strip()
    message_id = msg.get("message_id")

    from app.config import settings
    doctor_chat_id = str(settings.telegram_doctor_chat_id or "")
    doctor_user_id = settings.telegram_doctor_user_id

    if not doctor_chat_id or not doctor_user_id:
        logger.info("[telegram-webhook] doctor chat 未配置, 忽略所有消息")
        return {"ok": True, "ignored": "doctor_not_configured"}

    if chat_id != doctor_chat_id:
        logger.info(f"[telegram-webhook] chat_id={chat_id} 非 doctor, 忽略")
        return {"ok": True, "ignored": "not_doctor_chat"}

    if not text or len(text) < 4:
        # 太短可能是 emoji / 表情包, 不处理
        return {"ok": True, "ignored": "text_too_short"}

    # 不处理命令 (/start, /help)
    if text.startswith("/"):
        await _reply_to_telegram(
            chat_id,
            "ℹ️ 我会把您的回复解析为 patient 的诊疗指令. 直接发文字即可,如:\n"
            "  - LDL 控制在 2.6 以下\n  - 继续吃美托洛尔 25mg 每天\n  - 严格戒酒 30 天",
        )
        return {"ok": True, "ignored": "command"}

    # 解析 + 存入 directives
    from app.services.directive_parser import parse_and_store
    try:
        ids = parse_and_store(
            db, user_id=int(doctor_user_id),
            text=text,
            source="doctor_telegram",
            source_message_id=str(message_id) if message_id else None,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[telegram-webhook] parse_and_store 失败: {e}", exc_info=True)
        await _reply_to_telegram(chat_id, f"⚠️ 解析失败: {e}")
        return {"ok": False, "reason": "parse_error", "error": str(e)}

    # 回执
    if not ids:
        await _reply_to_telegram(
            chat_id,
            "ℹ️ 没识别出有效指令. 请用更明确的表达, 例如:\n"
            "  '把 LDL 目标降到 2.6'\n  '停用阿司匹林'\n  '严格戒酒 30 天'",
            reply_to_message_id=message_id,
        )
        return {"ok": True, "created": 0}

    # 拉刚创建的 directives 显示给医生确认
    from app.models.user_directive import UserDirective
    rows = db.query(UserDirective).filter(UserDirective.id.in_(ids)).all()
    summary = "\n".join(
        f"  • [{r.kind}] {r.instruction[:80]}"
        + (f"  ({r.metric_key}={r.target_value})" if r.metric_key and r.target_value else "")
        + (f"  ⏰{r.expires_at.strftime('%m-%d')}" if r.expires_at else "")
        for r in rows
    )
    await _reply_to_telegram(
        chat_id,
        f"✅ 已记录 {len(ids)} 条 directive (patient #{doctor_user_id}):\n{summary}\n\n"
        f"specialist 下次评估时会自动遵循.",
    )
    logger.info(f"[telegram-webhook] doctor created {len(ids)} directives for user={doctor_user_id}")
    return {"ok": True, "created": len(ids), "ids": ids}


@router.get("/webhook/status", summary="webhook 配置状态 (无需认证, 但 secret 鉴权)")
def webhook_status(
    secret: Optional[str] = Query(None),
    request: Request = None,
):
    _verify_secret(request, secret)
    from app.config import settings
    return {
        "doctor_chat_configured": bool(settings.telegram_doctor_chat_id),
        "doctor_user_id": settings.telegram_doctor_user_id,
        "bot_token_configured": bool(settings.telegram_bot_token),
        "webhook_secret_configured": bool(settings.telegram_webhook_secret),
    }
