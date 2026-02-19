"""
Siri 快捷指令 API - 为 Apple Shortcuts 提供语音健康记录接口

用法：
  POST /siri/say
  Header: Authorization: Bearer <token>
  Body:   {"message": "记录我刚吃了三个西红柿和5颗花生"}
  Return: {"text": "已记录！西红柿3个约54千卡，花生5颗约30千卡..."}

在 Apple Shortcuts 中配置：
  触发词 → 「获取文本」(语音输入) → 「获取URL内容」(POST) → 「朗读文本」
"""
import re
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.chat import ChatConversation
from app.api.deps import get_current_user_required
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/siri", tags=["Siri快捷指令"])

# Siri 专用对话标题
SIRI_CONVERSATION_TITLE = "🎙️ Siri快捷指令"


def strip_markdown(text: str) -> str:
    """去除 Markdown 格式，返回适合 Siri 朗读的纯文本"""
    # 去除代码块
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    # 去除加粗 / 斜体
    text = re.sub(r'\*{1,3}([^*]*)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]*)_{1,3}', r'\1', text)
    # 去除标题符号
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 去除链接，保留文字
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 去除水平线
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # 去除列表符号，保留内容
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    # 合并多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def get_or_create_siri_conversation(user_id: int, db: Session) -> int:
    """获取或创建用户的 Siri 专用对话，避免污染普通对话列表"""
    conv = db.query(ChatConversation).filter(
        ChatConversation.user_id == user_id,
        ChatConversation.title == SIRI_CONVERSATION_TITLE,
    ).first()
    if not conv:
        conv = ChatConversation(
            user_id=user_id,
            title=SIRI_CONVERSATION_TITLE,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv.id


class SiriRequest(BaseModel):
    message: str


class SiriResponse(BaseModel):
    text: str               # 纯文本，适合 Siri 朗读
    diet_saved: bool = False
    activities_saved: bool = False


@router.post("/say", response_model=SiriResponse, summary="Siri语音健康记录")
async def siri_say(
    req: SiriRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    Siri 快捷指令主入口。接收自然语言，自动完成饮食/运动/打卡记录并返回纯文本回复。

    支持的语音指令示例：
    - 「记录我刚吃了三个西红柿和5颗花生」→ 自动保存饮食记录
    - 「我刚跑步40分钟」→ 自动保存运动记录
    - 「完成了50个俯卧撑」→ 自动打卡
    - 「最近的步数怎么样」→ 查看数据
    - 「今天成都天气怎么样，适合户外吗」→ 基于当前位置/行程给建议
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 使用专属 Siri 对话（不影响普通对话列表的排序）
    conversation_id = get_or_create_siri_conversation(current_user.id, db)

    chat_service = ChatService(db)
    try:
        result = await chat_service.send_message(
            user_id=current_user.id,
            message=message,
            conversation_id=conversation_id,
        )
    except Exception as e:
        logger.error(f"Siri 请求处理失败 user={current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="处理失败，请稍后重试")

    reply = result.get("reply", "收到了，请稍后查看记录。")
    clean_text = strip_markdown(reply)

    return SiriResponse(
        text=clean_text,
        diet_saved=bool(result.get("diet_saved")),
        activities_saved=bool(result.get("activities_saved")),
    )


@router.get("/token-hint", summary="获取Token提示")
async def token_hint(
    current_user: User = Depends(get_current_user_required),
):
    """
    提示用户如何获取 Token 用于配置 Shortcuts。
    访问此接口时已验证身份，说明 Token 有效。
    """
    return {
        "user": current_user.name or current_user.username,
        "hint": "你的 Authorization Header 中的 Bearer Token 即为 Shortcuts 所需的 token。",
        "shortcut_url": "POST https://health.executor.life/api/siri/say",
        "body_example": {"message": "记录我刚吃了三个西红柿和5颗花生"},
    }
