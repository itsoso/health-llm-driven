"""
Siri 快捷指令 API - 为 Apple Shortcuts 提供语音健康记录接口

用法：
  POST /siri/say
  Header: Authorization: Bearer <token>
  Body:   {"message": "记录我刚吃了三个西红柿和5颗花生"}
  Return: {"text": "已记录！西红柿3个约54千卡，花生5颗约30千卡..."}

一键导入快捷指令：
  在 iPhone Safari 中打开：
  https://health.executor.life/api/siri/shortcut?token=<你的JWT_Token>
  iOS 会自动提示导入到「快捷指令」App。
"""
import asyncio
import re
import logging
import plistlib
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.chat import ChatConversation
from app.api.deps import get_current_user_required
from app.services.agent_executor import AgentExecutor
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/siri", tags=["Siri快捷指令"])

# Siri 专用对话标题
SIRI_CONVERSATION_TITLE = "🎙️ Siri快捷指令"

# API 基础 URL（写入快捷指令文件）
_API_BASE = f"{settings.site_base_url}/api"


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


def _generate_generic_shortcut_plist() -> bytes:
    """
    生成通用可分享的快捷指令（不含个人 Token）。

    导入时 iOS 会弹窗询问用户输入 Token，用户粘贴后即可使用。
    适合通过 iCloud 链接分享给所有人。
    """
    dictate_uuid = str(uuid.uuid4()).upper()
    download_uuid = str(uuid.uuid4()).upper()
    param_key = "health_token"

    def _action_ref(output_uuid: str, output_name: str) -> dict:
        return {
            "Value": {
                "attachmentsByRange": {
                    "{0, 1}": {
                        "Type": "ActionOutput",
                        "OutputUUID": output_uuid,
                        "OutputName": output_name,
                    }
                },
                "string": "\ufffc",
            },
            "WFSerializationType": "WFTextTokenAttachmentParameterState",
        }

    # "Bearer " 是 7 个字符，所以占位符位置是 {7, 1}
    auth_value_with_param = {
        "Value": {
            "attachmentsByRange": {
                "{7, 1}": {
                    "Type": "WorkflowConfiguration",
                    "WorkflowConfigurationParameterKey": param_key,
                }
            },
            "string": "Bearer \ufffc",
        },
        "WFSerializationType": "WFTextTokenAttachmentParameterState",
    }

    actions = [
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.dictatetext",
            "WFWorkflowActionParameters": {"UUID": dictate_uuid},
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {
                "UUID": download_uuid,
                "WFHTTPMethod": "POST",
                "WFURL": f"{_API_BASE}/siri/say",
                "WFHTTPHeaders": {
                    "Value": {
                        "WFDictionaryFieldValueItems": [
                            {
                                "WFItemType": 0,
                                "WFKey": {
                                    "Value": {"string": "Authorization"},
                                    "WFSerializationType": "WFTextTokenString",
                                },
                                "WFValue": auth_value_with_param,
                            }
                        ]
                    },
                    "WFSerializationType": "WFDictionaryFieldValue",
                },
                "WFHTTPBodyType": "File",
                "WFHTTPBody": _action_ref(dictate_uuid, "Dictated Text"),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
            "WFWorkflowActionParameters": {
                "WFGetDictionaryValueType": "Value",
                "WFDictionaryKey": "text",
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.speak",
            "WFWorkflowActionParameters": {"WFSpeakTextWaitUntilDone": True},
        },
    ]

    shortcut = {
        "WFWorkflowClientVersion": "2600.0.57",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowImportQuestions": [
            {
                "ParameterKey": param_key,
                "QuestionType": "Text",
                "Text": "请粘贴你的健康助手 Token（在 App「设置」页面复制）",
                "DefaultValue": "",
            }
        ],
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowName": "健康记录",
        "WFWorkflowActions": actions,
        "WFWorkflowTypes": [],
    }

    return plistlib.dumps(shortcut, fmt=plistlib.FMT_XML)


def _generate_shortcut_plist(token: str) -> bytes:
    """
    生成可直接导入 iPhone「快捷指令」App 的 .shortcut 文件（XML plist 格式）。

    快捷指令流程：
      1. 听写文本（语音输入）
      2. 发送 POST 请求到健康 API（body = 听写结果，text/plain）
      3. 从 JSON 响应中取 "text" 字段
      4. 朗读回复
    """
    dictate_uuid = str(uuid.uuid4()).upper()
    download_uuid = str(uuid.uuid4()).upper()

    # 引用前一步 Action 输出的 helper
    def _action_ref(output_uuid: str, output_name: str) -> dict:
        return {
            "Value": {
                "attachmentsByRange": {
                    "{0, 1}": {
                        "Type": "ActionOutput",
                        "OutputUUID": output_uuid,
                        "OutputName": output_name,
                    }
                },
                "string": "\ufffc",
            },
            "WFSerializationType": "WFTextTokenAttachmentParameterState",
        }

    actions = [
        # ── Step 1: 听写文本 ──────────────────────────────────────────
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.dictatetext",
            "WFWorkflowActionParameters": {
                "UUID": dictate_uuid,
            },
        },
        # ── Step 2: 发送到健康 API ────────────────────────────────────
        # body 类型 = File → 把上一步的文本作为 text/plain 发送
        # 后端 /siri/say 同时接受 JSON 和 text/plain
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {
                "UUID": download_uuid,
                "WFHTTPMethod": "POST",
                "WFURL": f"{_API_BASE}/siri/say",
                "WFHTTPHeaders": {
                    "Value": {
                        "WFDictionaryFieldValueItems": [
                            {
                                "WFItemType": 0,
                                "WFKey": {
                                    "Value": {"string": "Authorization"},
                                    "WFSerializationType": "WFTextTokenString",
                                },
                                "WFValue": {
                                    "Value": {"string": f"Bearer {token}"},
                                    "WFSerializationType": "WFTextTokenString",
                                },
                            }
                        ]
                    },
                    "WFSerializationType": "WFDictionaryFieldValue",
                },
                "WFHTTPBodyType": "File",
                "WFHTTPBody": _action_ref(dictate_uuid, "Dictated Text"),
            },
        },
        # ── Step 3: 取 JSON 中的 "text" 字段 ─────────────────────────
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
            "WFWorkflowActionParameters": {
                "WFGetDictionaryValueType": "Value",
                "WFDictionaryKey": "text",
            },
        },
        # ── Step 4: 朗读回复 ──────────────────────────────────────────
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.speak",
            "WFWorkflowActionParameters": {
                "WFSpeakTextWaitUntilDone": True,
            },
        },
    ]

    shortcut = {
        "WFWorkflowClientVersion": "2600.0.57",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowName": "健康记录",
        "WFWorkflowActions": actions,
        "WFWorkflowTypes": [],
    }

    return plistlib.dumps(shortcut, fmt=plistlib.FMT_XML)


class SiriRequest(BaseModel):
    message: str


class SiriResponse(BaseModel):
    text: str               # 纯文本，适合 Siri 朗读
    diet_saved: bool = False
    activities_saved: bool = False
    reminder_minutes: int = 0       # >0 时快捷指令应设置本地提醒（分钟后）
    reminder_message: str = ""      # 提醒内容


@router.post("/say", response_model=SiriResponse, summary="Siri语音健康记录")
async def siri_say(
    request: Request,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    Siri 快捷指令主入口。接收自然语言，自动完成饮食/运动/打卡记录并返回纯文本回复。

    同时支持两种 Content-Type：
    - application/json  →  {"message": "..."}
    - text/plain        →  直接发送消息文本（快捷指令 File body 模式）

    支持的语音指令示例：
    - 「记录我刚吃了三个西红柿和5颗花生」→ 自动保存饮食记录
    - 「我刚跑步40分钟」→ 自动保存运动记录
    - 「完成了50个俯卧撑」→ 自动打卡
    - 「最近的步数怎么样」→ 查看数据
    """
    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    logger.info(
        "Siri请求 user=%s content_type=%s body_len=%s",
        current_user.id,
        content_type,
        len(raw),
    )

    if "application/json" in content_type:
        import json as _json
        body = _json.loads(raw)
        message = body.get("message", "").strip()
    else:
        # text/plain — 快捷指令 "File" body 模式直接发送听写文本
        message = raw.decode("utf-8", errors="ignore").strip()

    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 使用专属 Siri 对话（不影响普通对话列表的排序）
    conversation_id = get_or_create_siri_conversation(current_user.id, db)

    # Siri 快捷指令 HTTP 超时约 25-30s，通过第一方 Agent stream 收集完整回复
    SIRI_TIMEOUT = 25
    agent = AgentExecutor(db)
    try:
        full_reply = ""
        async def collect_reply():
            nonlocal full_reply
            async for event in agent.run_stream(
                user_id=current_user.id,
                message=message,
                conversation_id=conversation_id,
                channel="siri",
            ):
                if event.get("event") == "token":
                    full_reply += event.get("data", {}).get("content", "")
        await asyncio.wait_for(collect_reply(), timeout=SIRI_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(
            "Siri 请求超时 timeout_seconds=%s user=%s message_len=%s",
            SIRI_TIMEOUT,
            current_user.id,
            len(message),
        )
        if full_reply:
            return SiriResponse(text=strip_markdown(full_reply))
        return SiriResponse(text="收到了，正在处理中。请稍后在 App 中查看结果。")
    except Exception as e:
        logger.error(f"Siri 请求处理失败 user={current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="处理失败，请稍后重试")

    clean_text = strip_markdown(full_reply or "收到了，请稍后查看记录。")

    return SiriResponse(
        text=clean_text,
        diet_saved=False,
        activities_saved=False,
        reminder_minutes=0,
        reminder_message="",
    )


@router.get("/shortcut", summary="一键下载Siri快捷指令文件")
async def download_shortcut(
    token: str = Query(..., description="JWT Token（Bearer 后面的部分）"),
):
    """
    生成并下载预配置好的快捷指令 .shortcut 文件。

    **在 iPhone 的 Safari 浏览器中打开此链接**，iOS 会自动提示导入到「快捷指令」App。

    示例链接：
    ```
    https://health.executor.life/api/siri/shortcut?token=<你的JWT_Token>
    ```
    """
    from app.services.auth import AuthService
    payload = AuthService.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期，请重新登录获取")

    shortcut_bytes = _generate_shortcut_plist(token)
    return Response(
        content=shortcut_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="HealthRecord.shortcut"'},
    )


@router.get("/setup-shortcut", summary="下载通用可分享快捷指令（导入时提示输入Token）")
async def download_setup_shortcut():
    """
    下载通用「健康记录」快捷指令文件。

    **无需登录**，任何人均可下载。导入时 iOS 会弹窗提示粘贴个人 Token。

    用法：
    1. 在 iPhone Safari 打开此链接下载 .shortcut 文件
    2. 粘贴在 App「设置」页面复制的 Token
    3. 点击「添加快捷指令」完成安装
    """
    shortcut_bytes = _generate_generic_shortcut_plist()
    return Response(
        content=shortcut_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="HealthRecord.shortcut"'},
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
        "shortcut_url": f"POST {_API_BASE}/siri/say",
        "shortcut_download": f"{_API_BASE}/siri/shortcut?token=<your_token>",
        "body_example": {"message": "记录我刚吃了三个西红柿和5颗花生"},
    }
