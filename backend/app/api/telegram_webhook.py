"""
Telegram Webhook — 外部指令通道, 输入文字 → user_directives.

注: 本系统不提供医疗服务. 此通道用于用户自己 / 家人 / 健康教练 在 Telegram
向 agent 下达硬性约束指令. 任何涉及医疗判断的内容应在用户和其执业医师
确认后再录入.

设置 Telegram bot webhook 指向:
  https://health.executor.life/api/v1/telegram/webhook?secret={TELEGRAM_WEBHOOK_SECRET}

工作流:
  授权外部用户在 Telegram 给 bot 发文字
  → bot 转发到我们的 webhook
  → 验证 chat_id == TELEGRAM_ADVISOR_CHAT_ID (或历史 DOCTOR_CHAT_ID 兼容)
  → directive_parser.parse_and_store(source='external_telegram')
  → 回执 "✅ 已记录 N 条 directive"

不识别图片/语音 (后续接 OCR/STT 再说).

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
    # 优先用新字段 advisor, 兼容历史 doctor 字段
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
        logger.info(f"[telegram-webhook] chat_id={chat_id} 非 advisor, 忽略")
        return {"ok": True, "ignored": "not_advisor_chat"}

    if not text or len(text) < 4:
        # 太短可能是 emoji / 表情包, 不处理
        return {"ok": True, "ignored": "text_too_short"}

    # 不处理命令 (/start, /help)
    if text.startswith("/"):
        await _reply_to_telegram(
            chat_id,
            "ℹ️ 我会把您的文字解析为指令录入 agent. 直接发文字即可,如:\n"
            "  - LDL 控制在 2.6 以下\n  - 严格戒酒 30 天\n  - 不要再推鱼油了\n\n"
            "注: 涉及用药/医疗判断, 请先与执业医师确认后再录入.",
        )
        return {"ok": True, "ignored": "command"}

    # 解析 + 存入 directives
    from app.services.directive_parser import parse_and_store
    try:
        ids = parse_and_store(
            db, user_id=int(advisor_user_id),
            text=text,
            source="external_telegram",
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
            "  '把 LDL 目标降到 2.6'\n  '严格戒酒 30 天'\n  '不要再推鱼油'",
            reply_to_message_id=message_id,
        )
        return {"ok": True, "created": 0}

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
        f"✅ 已录入 {len(ids)} 条指令 (user #{advisor_user_id}):\n{summary}\n\n"
        f"specialist 下次评估时会自动遵循.",
    )
    logger.info(f"[telegram-webhook] external created {len(ids)} directives for user={advisor_user_id}")
    return {"ok": True, "created": len(ids), "ids": ids}


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
