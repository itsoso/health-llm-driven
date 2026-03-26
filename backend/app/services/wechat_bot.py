"""微信 Bot 消息路由 — 处理来自企业微信/服务号的消息

消息类型路由：
- 图片 → 判断是体检报告还是药盒 → 调用对应 API
- 语音 → ASR 转文字 → medical_text_parser → 调用对应 API
- 文字 → medical_text_parser（快速匹配）→ 失败则转发 OpenClaw
"""
import logging
import hashlib
import time
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class WeChatBotHandler:
    """微信消息处理器"""

    def __init__(self, db: Session):
        self.db = db

    async def handle_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一消息入口。

        Args:
            msg: {
                "msg_type": "text" | "image" | "voice",
                "content": str,  # 文字内容 / 图片 base64 / 语音 base64
                "wechat_openid": str,  # 发送者 OpenID
                "user_id": int | None,  # 已绑定的 shadow user_id
            }

        Returns:
            {"reply": str, "action": dict | None}
        """
        msg_type = msg.get("msg_type", "text")
        content = msg.get("content", "")
        user_id = msg.get("user_id")

        if not user_id:
            return {"reply": "您好！请先让家人帮您绑定账号。", "action": None}

        if msg_type == "image":
            return await self._handle_image(content, user_id)
        elif msg_type == "voice":
            return await self._handle_voice(content, user_id)
        elif msg_type == "text":
            return await self._handle_text(content, user_id)
        else:
            return {"reply": "暂不支持该消息类型，请发送文字、照片或语音。", "action": None}

    async def _handle_image(self, image_base64: str, user_id: int) -> Dict[str, Any]:
        """处理图片消息：判断是体检报告还是药盒"""
        try:
            from app.services.llm import get_llm_provider
            llm = get_llm_provider()

            # 先判断图片类型
            classify_msg = [
                {"role": "system", "content": (
                    "判断这张图片是什么类型，只返回一个词：\n"
                    "- report（体检报告、化验单、检查结果）\n"
                    "- medication（药盒、药瓶、处方）\n"
                    "- other（其他）"
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": "这是什么类型的图片？"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64[:100000]}", "detail": "low"}},
                ]},
            ]
            img_type = (await llm.chat(classify_msg, temperature=0.1)).strip().lower()

            if "report" in img_type:
                # 体检报告 → 调用异步提取
                from datetime import date
                from app.models.family_health import MedicalReport
                report = MedicalReport(
                    user_id=user_id,
                    report_date=date.today(),
                    title="微信上传报告",
                    status="processing",
                )
                self.db.add(report)
                self.db.commit()
                self.db.refresh(report)

                # 后台提取
                import threading
                from app.api.family_health import _process_report_background
                threading.Thread(
                    target=_process_report_background,
                    args=(report.id, user_id, date.today(), [image_base64]),
                    daemon=True,
                ).start()

                return {
                    "reply": f"📋 收到体检报告，AI 正在分析中（编号 {report.id}），稍后会把结果发给您。",
                    "action": {"type": "report_upload", "report_id": report.id},
                }

            elif "medication" in img_type:
                # 药盒 → 识别并添加
                from app.api.family_health import recognize_medication
                # 直接调用识别逻辑
                try:
                    from app.services.llm import get_llm_provider
                    llm2 = get_llm_provider()
                    msg_list = [
                        {"role": "system", "content": (
                            "你是药品识别专家。请识别照片中的药品，返回 JSON 格式：\n"
                            '{"name": "药品名", "dosage": "剂量", "frequency": "频次", "purpose": "适应症"}\n'
                            "只返回 JSON。"
                        )},
                        {"role": "user", "content": [
                            {"type": "text", "text": "请识别药品信息："},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64[:100000]}", "detail": "low"}},
                        ]},
                    ]
                    import json
                    resp = await llm2.chat(msg_list, temperature=0.1)
                    text = resp.strip()
                    if text.startswith("```"):
                        text = text.split("```")[1].strip()
                        if text.startswith("json"):
                            text = text[4:].strip()
                    drug_info = json.loads(text)

                    from app.models.medication import Medication
                    med = Medication(
                        user_id=user_id,
                        name=drug_info.get("name", "未识别"),
                        dosage=drug_info.get("dosage"),
                        frequency=drug_info.get("frequency"),
                        purpose=drug_info.get("purpose"),
                        start_date=__import__("datetime").date.today(),
                    )
                    self.db.add(med)
                    self.db.commit()

                    return {
                        "reply": f"💊 已识别药品: {med.name}\n剂量: {med.dosage or '未知'}\n频次: {med.frequency or '未知'}\n用途: {med.purpose or '未知'}",
                        "action": {"type": "medication_added", "medication_id": med.id},
                    }
                except Exception as e:
                    return {"reply": f"💊 药品识别失败，请拍照清晰一些再试。", "action": None}

            else:
                return {"reply": "收到图片，但我不确定这是什么。请发体检报告或药盒的照片给我。", "action": None}

        except Exception as e:
            logger.error(f"图片消息处理失败: {e}", exc_info=True)
            return {"reply": "图片处理遇到问题，请稍后再试。", "action": None}

    async def _handle_voice(self, voice_base64: str, user_id: int) -> Dict[str, Any]:
        """处理语音消息：ASR → 文字 → 解析"""
        try:
            # TODO: 接入腾讯云 ASR 或 iFlytek
            # 临时方案：用 LLM 描述（如果 voice 已经被微信转为文字）
            # 企业微信会自动提供 recognition 字段（语音识别结果）
            text = voice_base64  # 假设已经是识别后的文字

            return await self._handle_text(text, user_id)

        except Exception as e:
            logger.error(f"语音消息处理失败: {e}", exc_info=True)
            return {"reply": "没听清楚，能再说一遍吗？比如说'血压120/80'或'今天吃药了'。", "action": None}

    async def _handle_text(self, text: str, user_id: int) -> Dict[str, Any]:
        """处理文字消息：正则快速匹配 → LLM 兜底 → OpenClaw 转发"""
        from app.services.medical_text_parser import parse_and_route

        parsed = await parse_and_route(text)

        if parsed and parsed.get("type") != "unknown":
            # 有明确的健康数据意图
            action = parsed.get("api_action")
            display = parsed.get("display", text)

            if action and action.get("endpoint"):
                # 执行 API 调用
                result = await self._execute_api_action(action, user_id)
                if result.get("success"):
                    return {"reply": f"✅ 已记录: {display}", "action": parsed}
                else:
                    return {"reply": f"记录失败: {result.get('error', '未知错误')}", "action": None}
            else:
                return {"reply": f"📝 收到: {display}（已记录）", "action": parsed}
        else:
            # 转发给 OpenClaw AI 对话
            return {
                "reply": None,  # 由调用方转发到 OpenClaw
                "action": {"type": "forward_to_openclaw", "text": text},
            }

    async def _execute_api_action(self, action: Dict, user_id: int) -> Dict[str, Any]:
        """执行映射的 API 动作"""
        try:
            endpoint = action.get("endpoint", "")
            method = action.get("method", "POST")
            body = action.get("body")

            if "water/records/quick" in endpoint:
                from app.models.daily_health import WaterIntake
                from datetime import date, datetime
                record = WaterIntake(
                    user_id=user_id,
                    record_date=date.today(),
                    intake_time=datetime.now(),
                    amount_ml=int(endpoint.split("amount=")[-1]) if "amount=" in endpoint else 250,
                )
                self.db.add(record)
                self.db.commit()
                return {"success": True}

            elif "blood-pressure/records" in endpoint and body:
                from app.models.daily_health import BloodPressureRecord
                record = BloodPressureRecord(
                    user_id=user_id,
                    record_date=__import__("datetime").date.today(),
                    systolic=body.get("systolic"),
                    diastolic=body.get("diastolic"),
                )
                self.db.add(record)
                self.db.commit()
                return {"success": True}

            elif "weight/records" in endpoint and body:
                from app.models.weight import WeightRecord
                record = WeightRecord(
                    user_id=user_id,
                    record_date=__import__("datetime").date.today(),
                    weight=body.get("weight"),
                )
                self.db.add(record)
                self.db.commit()
                return {"success": True}

            elif "medications" in endpoint and "take" in endpoint:
                from app.models.medication import Medication, MedicationLog
                # 找到第一个活跃药物
                med = self.db.query(Medication).filter(
                    Medication.user_id == user_id,
                    Medication.is_active == True,
                ).first()
                if med:
                    log = MedicationLog(
                        user_id=user_id,
                        medication_id=med.id,
                        taken_date=__import__("datetime").date.today(),
                        status="taken",
                    )
                    self.db.add(log)
                    self.db.commit()
                    return {"success": True}
                return {"success": False, "error": "未找到活跃药物"}

            return {"success": False, "error": "未支持的操作"}

        except Exception as e:
            logger.error(f"API action 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
