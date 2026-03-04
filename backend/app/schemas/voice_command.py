"""语音指令请求/响应模型"""
from typing import Optional, Dict, Any
from pydantic import BaseModel


class VoiceCommandRequest(BaseModel):
    text: str


class VoiceCommandResponse(BaseModel):
    matched: bool
    command_type: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
