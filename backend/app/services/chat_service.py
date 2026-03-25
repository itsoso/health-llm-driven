"""
聊天服务 - 通过统一 LLM Provider 提供 AI 对话能力
注入用户健康上下文

重构后将职责拆分为：
- HealthContextBuilder: 健康上下文构建（health_context_builder.py）
- ChatActionHandler: Action 解析与执行（chat_action_handler.py）
- ChatSkillsHandler: OpenClaw Skills 管理（chat_skills_handler.py）
- ChatService: 核心对话逻辑（本文件）
"""
import json
import logging
import re
import asyncio
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.daily_health import DietRecord
from app.models.chat import ChatConversation, ChatMessage
from app.services.ai.food_recognition import food_recognition_service
from app.services.quark_search import get_search_client
from app.services.llm import get_llm_provider
from app.services.chat_tools import HEALTH_TOOLS, execute_tool
from app.services.health_context_builder import HealthContextBuilder
from app.services.chat_action_handler import ChatActionHandler
from app.services.chat_skills_handler import ChatSkillsHandler

logger = logging.getLogger(__name__)


class ChatService:
    """聊天服务 - 核心对话逻辑"""

    def __init__(self, db: Session):
        self.db = db
        self._context_builder = HealthContextBuilder(db)
        self._action_handler = ChatActionHandler(db)
        self._skills_handler = ChatSkillsHandler()

    # ── 饮食/搜索检测 ──────────────────────────────────────

    def _is_food_message(self, message: str) -> bool:
        """检测消息是否是记录饮食的内容"""
        quantity_words = '个只条碗盘杯片块份根勺两斤克袋瓶罐把串盒听颗粒'
        pattern = rf'[一二三四五六七八九十百千万半\d]+\s*[{quantity_words}]'
        matches = re.findall(pattern, message)

        if len(matches) >= 2:
            return True

        food_action_keywords = ['计算热量', '记录饮食', '热量计算', '算一下热量', '算热量',
                                '多少卡', '多少热量', '多少卡路里', '记一下饮食']
        if any(kw in message for kw in food_action_keywords):
            return True

        food_context_keywords = ['吃了', '吃的', '早餐', '午餐', '晚餐', '夜宵',
                                 '早饭', '中饭', '晚饭', '喝了', '加餐']
        if len(matches) >= 1 and any(kw in message for kw in food_context_keywords):
            return True

        return False

    def _should_search(self, message: str) -> bool:
        """检测消息是否需要联网搜索 - 默认搜索，只排除明确不需要的"""
        msg = message.strip()
        if self._is_food_message(message):
            return False
        if len(msg) < 3:
            return False
        no_search = ['你好', '嗨', '早上好', '晚上好', '下午好', '谢谢', '好的',
                     '嗯', '哦', '知道了', '明白', '收到', '好', '是的', '不是',
                     '对', '不对', '行', '可以', '不行', '没有', '有']
        if msg in no_search:
            return False
        activity_only = ['刚', '做了', '喝了水', '吃了药', '洗了鼻']
        if len(msg) < 10 and any(msg.startswith(w) for w in activity_only):
            return False
        return True

    def _get_meal_type_by_time(self) -> str:
        """根据当前时间推断餐次"""
        hour = datetime.now().hour
        if hour < 10:
            return "breakfast"
        elif hour < 14:
            return "lunch"
        elif hour < 17:
            return "snack"
        elif hour < 21:
            return "dinner"
        else:
            return "snack"

    def _process_diet_record(self, user_id: int, message: str, nutrition_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将营养数据保存为饮食记录"""
        try:
            foods = nutrition_data.get("foods", [])
            if not foods:
                return None

            food_items = ", ".join([
                f"{f.get('name', '')}({f.get('quantity', '')})" if f.get('quantity') else f.get('name', '')
                for f in foods
            ])
            food_name = food_items[:100] if len(food_items) > 100 else food_items

            meal_type = self._get_meal_type_by_time()
            today = date.today()

            db_record = DietRecord(
                user_id=user_id,
                record_date=today,
                meal_type=meal_type,
                food_name=food_name,
                food_items=food_items,
                calories=nutrition_data.get("total_calories"),
                protein=nutrition_data.get("total_protein"),
                carbs=nutrition_data.get("total_carbs"),
                fat=nutrition_data.get("total_fat"),
                notes=f"通过智能助理对话自动记录: {message[:100]}",
                ai_recognized=True,
                ai_raw_result=json.dumps(nutrition_data, ensure_ascii=False),
                health_tips=nutrition_data.get("health_tips"),
            )
            self.db.add(db_record)
            self.db.commit()
            self.db.refresh(db_record)

            logger.info(f"用户 {user_id} 通过对话自动保存饮食记录: id={db_record.id}, {food_items}")

            return {
                "record_id": db_record.id,
                "food_items": food_items,
                "total_calories": nutrition_data.get("total_calories"),
                "total_protein": nutrition_data.get("total_protein"),
                "total_carbs": nutrition_data.get("total_carbs"),
                "total_fat": nutrition_data.get("total_fat"),
                "meal_type": meal_type,
                "record_date": str(today),
            }
        except Exception as e:
            logger.error(f"自动保存饮食记录失败: {e}")
            self.db.rollback()
            return None

    # ── LLM 调用 ──────────────────────────────────────────

    async def _call_openclaw(self, messages: list, tools: list = None):
        """调用 LLM Provider（非流式）"""
        provider = get_llm_provider()
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
        result = await provider.chat(messages=messages, **kwargs)
        return result

    async def _call_openclaw_stream(self, messages: list):
        """调用 LLM Provider 流式 API，逐 token yield"""
        provider = get_llm_provider()
        stream = await provider.chat(messages=messages, stream=True)
        async for token in stream:
            yield token

    # ── 核心对话方法 ──────────────────────────────────────

    async def send_message(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        is_kids_mode: bool = False,
        image_base64: Optional[str] = None,
        image_type: Optional[str] = "jpeg",
    ) -> Dict[str, Any]:
        """发送消息到 LLM 并返回回复"""

        # 获取或创建对话
        if conversation_id:
            conv = self.db.query(ChatConversation).filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            ).first()
            if not conv:
                raise ValueError("对话不存在")
        else:
            conv = ChatConversation(user_id=user_id, title=message[:50])
            self.db.add(conv)
            self.db.commit()
            self.db.refresh(conv)

        # 保存用户消息
        user_msg = ChatMessage(conversation_id=conv.id, role="user", content=message)
        self.db.add(user_msg)
        self.db.commit()

        # 检测是否是饮食记录消息
        diet_result = None
        diet_context = ""
        if self._is_food_message(message):
            logger.info(f"检测到饮食记录消息: {message[:80]}")
            try:
                nutrition_data = await asyncio.to_thread(
                    food_recognition_service.estimate_nutrition_from_text, message
                )
                if nutrition_data.get("success"):
                    diet_result = self._process_diet_record(user_id, message, nutrition_data)
                    if diet_result:
                        foods_detail = "\n".join([
                            f"- {f.get('name', '')}: {f.get('quantity', '')}, {f.get('calories', 0)}kcal, "
                            f"蛋白质{f.get('protein', 0)}g, 碳水{f.get('carbs', 0)}g, 脂肪{f.get('fat', 0)}g"
                            for f in nutrition_data.get("foods", [])
                        ])
                        meal_type_cn = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}.get(diet_result["meal_type"], "加餐")
                        diet_context = (
                            f"\n\n[系统提示：已自动分析用户的饮食并保存为{meal_type_cn}记录。营养分析结果：\n"
                            f"食物明细：\n{foods_detail}\n"
                            f"总热量：{nutrition_data.get('total_calories', 0)}kcal\n"
                            f"总蛋白质：{nutrition_data.get('total_protein', 0)}g\n"
                            f"总碳水：{nutrition_data.get('total_carbs', 0)}g\n"
                            f"总脂肪：{nutrition_data.get('total_fat', 0)}g\n"
                            f"请基于以上数据给用户一个友好的饮食反馈，包含各食物热量明细、总热量、营养评价和建议。"
                            f"告知用户饮食已自动记录。]"
                        )
                else:
                    logger.warning(f"营养估算失败: {nutrition_data.get('error')}")
            except Exception as e:
                logger.error(f"饮食检测处理失败: {e}")

        # 联网搜索增强
        search_context = ""
        if self._should_search(message):
            search_client = get_search_client()
            if search_client:
                try:
                    search_context = await search_client.search_with_context(message, max_results=3, context_length=500)
                    if search_context:
                        logger.info(f"夸克搜索命中: query={message[:50]}")
                except Exception as e:
                    logger.warning(f"夸克搜索异常: {e}")

        # 构建消息列表（最近 20 条作为上下文）
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()

        recent = history[-20:] if len(history) > 20 else history

        system_prompt = await self._context_builder.build_system_prompt(user_id, is_kids_mode=is_kids_mode, user_question=message)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in recent:
            content = msg.content
            if msg.id == user_msg.id:
                if diet_context:
                    content += diet_context
                if search_context:
                    content += f"\n\n[参考资料 - 来自网络搜索]\n{search_context}\n[请基于以上参考资料和你的专业知识回答用户问题，不要直接提及搜索结果或参考资料。]"
                if image_base64:
                    content_parts = [
                        {"type": "text", "text": content},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{image_type};base64,{image_base64}",
                            "detail": "high"
                        }}
                    ]
                    messages.append({"role": msg.role, "content": content_parts})
                    continue
            messages.append({"role": msg.role, "content": content})

        # 调用 LLM API（传入 Function Calling tools）
        try:
            reply_content = await self._call_openclaw(messages, tools=HEALTH_TOOLS)
        except Exception as e:
            logger.error(f"LLM 调用失败: {type(e).__name__}: {e}")
            reply_content = "抱歉，智能助理暂时无法响应，请稍后再试。"

        # ---- Function Calling 处理 ----
        fc_activity_results = []
        if isinstance(reply_content, dict) and reply_content.get("tool_calls"):
            tool_calls = reply_content["tool_calls"]
            logger.info(f"LLM 返回 {len(tool_calls)} 个 tool_calls: {[tc['function']['name'] for tc in tool_calls]}")

            fc_user = self.db.query(User).filter(User.id == user_id).first()

            messages.append({
                "role": "assistant",
                "content": reply_content.get("content"),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    func_args = {}
                try:
                    result = await execute_tool(func_name, func_args, self.db, fc_user)
                except Exception as tool_err:
                    logger.error(f"execute_tool({func_name}) 异常: {tool_err}")
                    result = {"error": str(tool_err)}

                fc_activity_results.append({"type": func_name, **result})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

            try:
                reply_content = await self._call_openclaw(messages)
                if isinstance(reply_content, dict):
                    reply_content = reply_content.get("content") or "操作已完成。"
            except Exception as e:
                logger.error(f"Function Calling 第二轮调用失败: {e}")
                success_msgs = [r.get("message", "") for r in fc_activity_results if r.get("success")]
                reply_content = "；".join(success_msgs) if success_msgs else "操作已执行，但生成回复时出错。"

        # ---- <<<ACTIONS: 解析（作为 fallback） ----
        clean_reply, actions = self._action_handler.parse_actions(reply_content if isinstance(reply_content, str) else str(reply_content))
        activity_results = []
        if actions:
            plan_actions = [a for a in actions if a.get("type") == "create_plan"]
            workout_actions = [a for a in actions if a.get("type") == "workout_analyze"]
            other_actions = [a for a in actions if a.get("type") not in ("create_plan", "workout_analyze")]
            if other_actions:
                activity_results = self._action_handler.execute_actions(user_id, other_actions)
            for pa in plan_actions:
                plan_result = await self._action_handler.handle_create_plan_async(user_id, pa)
                if plan_result:
                    activity_results.append(plan_result)
            for wa in workout_actions:
                workout_result = await self._action_handler.handle_workout_analyze_action(user_id, wa)
                if workout_result:
                    activity_results.append(workout_result)
            logger.info(f"用户{user_id} 执行了{len(activity_results)}个活动（<<<ACTIONS: fallback）")

        # 合并 Function Calling 执行结果
        if fc_activity_results:
            for fc_r in fc_activity_results:
                if fc_r.get("action_type") == "create_plan":
                    plan_result = await self._action_handler.handle_create_plan_async(user_id, fc_r.get("arguments", {}))
                    if plan_result:
                        activity_results.append(plan_result)
                elif fc_r.get("action_type") == "workout_analyze":
                    workout_result = await self._action_handler.handle_workout_analyze_action(user_id, fc_r.get("arguments", {}))
                    if workout_result:
                        activity_results.append(workout_result)
                elif fc_r.get("success"):
                    activity_results.append(fc_r)
            logger.info(f"用户{user_id} Function Calling 执行了{len(fc_activity_results)}个工具")

        # 图片消息后处理
        food_keywords = ["食", "吃", "喝", "餐", "饭", "菜", "营养", "热量", "卡路里", "蛋白", "碳水", "脂肪", "识别", "recognize"]
        is_food_intent = image_base64 and any(kw in message for kw in food_keywords)
        if is_food_intent and not diet_result and clean_reply:
            try:
                nutrition_data = await asyncio.to_thread(
                    food_recognition_service.estimate_nutrition_from_text, clean_reply
                )
                if nutrition_data.get("success") and nutrition_data.get("foods"):
                    diet_result = self._process_diet_record(user_id, message, nutrition_data)
                    if diet_result:
                        logger.info(f"从图片AI分析中提取饮食记录: {diet_result.get('food_items', '')}")
            except Exception as e:
                logger.warning(f"图片消息饮食提取失败: {e}")

        # 保存 AI 回复
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=clean_reply)
        self.db.add(ai_msg)
        conv.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ai_msg)

        # 提取对话记忆
        try:
            from app.services.conversation_memory_service import extract_memories
            extract_memories(message, clean_reply, user_id, conv.id, self.db)
        except Exception as e:
            logger.warning(f"提取对话记忆失败: {e}")

        result = {
            "conversation_id": conv.id,
            "reply": clean_reply,
            "message_id": ai_msg.id
        }

        # 运动分析结果作为追加消息
        workout_analysis_msg = None
        if activity_results:
            for ar in activity_results:
                if ar.get("type") == "workout_analyze" and ar.get("status") == "analyzed":
                    analysis_content = ar.get("message", "")
                    if analysis_content:
                        workout_analysis_msg = ChatMessage(
                            conversation_id=conv.id,
                            role="assistant",
                            content=analysis_content
                        )
                        self.db.add(workout_analysis_msg)
                        self.db.commit()
                        self.db.refresh(workout_analysis_msg)
                        result["workout_analysis"] = {
                            "message_id": workout_analysis_msg.id,
                            "content": analysis_content,
                            "workout_data": ar.get("workout_data"),
                        }
                    break

        if diet_result:
            result["diet_saved"] = True
            result["diet_data"] = diet_result

        non_workout_activities = [a for a in activity_results if a.get("type") != "workout_analyze"] if activity_results else []
        if non_workout_activities:
            result["activities_saved"] = True
            result["activities"] = non_workout_activities

            for ar in activity_results:
                if ar.get("type") == "activity_status" and ar.get("status") == "saved":
                    reminder_mins = ar.get("reminder_minutes")
                    if reminder_mins and reminder_mins > 0:
                        result["reminder"] = {
                            "reminder_minutes": reminder_mins,
                            "reminder_message": ar.get("reminder_message", "该休息一下了"),
                            "activity_name": ar.get("activity_name", ""),
                        }
                        break

        return result

    async def send_message_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        is_kids_mode: bool = False,
        image_base64: Optional[str] = None,
        image_type: Optional[str] = "jpeg",
    ):
        """流式发送消息，yield SSE 事件字典"""
        import time as _time_mod
        _stream_start = _time_mod.time()

        # 获取或创建对话
        if conversation_id:
            conv = self.db.query(ChatConversation).filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            ).first()
            if not conv:
                yield {"event": "error", "data": {"message": "对话不存在"}}
                return
        else:
            conv = ChatConversation(user_id=user_id, title=message[:50])
            self.db.add(conv)
            self.db.commit()
            self.db.refresh(conv)

        # 保存用户消息
        user_msg = ChatMessage(conversation_id=conv.id, role="user", content=message)
        self.db.add(user_msg)
        self.db.commit()

        # 饮食检测
        diet_result = None
        diet_context = ""
        if self._is_food_message(message):
            try:
                nutrition_data = await asyncio.to_thread(
                    food_recognition_service.estimate_nutrition_from_text, message
                )
                if nutrition_data.get("success"):
                    diet_result = self._process_diet_record(user_id, message, nutrition_data)
                    if diet_result:
                        foods_detail = "\n".join([
                            f"- {f.get('name', '')}: {f.get('quantity', '')}, {f.get('calories', 0)}kcal, "
                            f"蛋白质{f.get('protein', 0)}g, 碳水{f.get('carbs', 0)}g, 脂肪{f.get('fat', 0)}g"
                            for f in nutrition_data.get("foods", [])
                        ])
                        meal_type_cn = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}.get(diet_result["meal_type"], "加餐")
                        diet_context = (
                            f"\n\n[系统提示：已自动分析用户的饮食并保存为{meal_type_cn}记录。营养分析结果：\n"
                            f"食物明细：\n{foods_detail}\n"
                            f"总热量：{nutrition_data.get('total_calories', 0)}kcal\n"
                            f"请基于以上数据给用户一个友好的饮食反馈。告知用户饮食已自动记录。]"
                        )
            except Exception as e:
                logger.warning(f"流式模式饮食检测异常: {e}")

        # 搜索上下文
        search_context = ""
        if not diet_context and not image_base64 and self._should_search(message):
            try:
                search_client = get_search_client()
                if search_client:
                    results = await search_client.search(message, max_results=3)
                    if results:
                        search_context = "\n".join([f"- {r.get('title', '')}: {r.get('content', '')[:500]}" for r in results])
            except Exception as e:
                logger.warning(f"流式模式搜索异常: {e}")

        # 构建消息列表
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()
        recent = history[-20:] if len(history) > 20 else history

        system_prompt = await self._context_builder.build_system_prompt(user_id, is_kids_mode=is_kids_mode, user_question=message)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in recent:
            content = msg.content
            if msg.id == user_msg.id:
                if diet_context:
                    content += diet_context
                if search_context:
                    content += f"\n\n[参考资料 - 来自网络搜索]\n{search_context}\n[请基于以上参考资料和你的专业知识回答用户问题，不要直接提及搜索结果或参考资料。]"
                if image_base64:
                    content_parts = [
                        {"type": "text", "text": content},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{image_type};base64,{image_base64}",
                            "detail": "high"
                        }}
                    ]
                    messages.append({"role": msg.role, "content": content_parts})
                    continue
            messages.append({"role": msg.role, "content": content})

        # 流式调用 LLM
        full_response = ""
        in_action_block = False
        try:
            async for token in self._call_openclaw_stream(messages):
                full_response += token
                if "<<<ACTIONS:" in full_response and not in_action_block:
                    in_action_block = True
                    pre_action = full_response.split("<<<ACTIONS:")[0]
                    already_sent = full_response[:len(full_response) - len(token)]
                    remaining = pre_action[len(already_sent):]
                    if remaining:
                        yield {"event": "token", "data": {"content": remaining}}
                    continue
                if not in_action_block:
                    yield {"event": "token", "data": {"content": token}}
        except Exception as e:
            logger.error(f"LLM 流式调用失败: {type(e).__name__}: {e}")
            full_response = "抱歉，智能助理暂时无法响应，请稍后再试。"
            yield {"event": "token", "data": {"content": full_response}}

        # 解析 actions
        clean_reply, actions = self._action_handler.parse_actions(full_response)
        activity_results = []
        if actions:
            plan_actions = [a for a in actions if a.get("type") == "create_plan"]
            workout_actions = [a for a in actions if a.get("type") == "workout_analyze"]
            other_actions = [a for a in actions if a.get("type") not in ("create_plan", "workout_analyze")]
            if other_actions:
                activity_results = self._action_handler.execute_actions(user_id, other_actions)
            for pa in plan_actions:
                plan_result = await self._action_handler.handle_create_plan_async(user_id, pa)
                if plan_result:
                    activity_results.append(plan_result)
            for wa in workout_actions:
                workout_result = await self._action_handler.handle_workout_analyze_action(user_id, wa)
                if workout_result:
                    activity_results.append(workout_result)

        # 图片消息后处理
        food_keywords = ["食", "吃", "喝", "餐", "饭", "菜", "营养", "热量", "卡路里", "蛋白", "碳水", "脂肪", "识别", "recognize"]
        is_food_intent = image_base64 and any(kw in message for kw in food_keywords)
        if is_food_intent and not diet_result and clean_reply:
            try:
                nutrition_data = await asyncio.to_thread(
                    food_recognition_service.estimate_nutrition_from_text, clean_reply
                )
                if nutrition_data.get("success") and nutrition_data.get("foods"):
                    diet_result = self._process_diet_record(user_id, message, nutrition_data)
                    if diet_result:
                        logger.info(f"流式模式 - 从图片AI分析中提取饮食记录: {diet_result.get('food_items', '')}")
            except Exception as e:
                logger.warning(f"流式模式 - 图片消息饮食提取失败: {e}")

        # 保存 AI 回复
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=clean_reply)
        self.db.add(ai_msg)
        conv.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ai_msg)

        # 提取对话记忆
        try:
            from app.services.conversation_memory_service import extract_memories
            extract_memories(message, clean_reply, user_id, conv.id, self.db)
        except Exception as e:
            logger.warning(f"提取对话记忆失败: {e}")

        # 构建完成事件
        result_data = {
            "conversation_id": conv.id,
            "message_id": ai_msg.id,
        }
        if diet_result:
            result_data["diet_saved"] = True
            result_data["diet_data"] = diet_result
        non_workout = [a for a in activity_results if a.get("type") != "workout_analyze"] if activity_results else []
        if non_workout:
            result_data["activities_saved"] = True
            result_data["activities"] = non_workout
        for ar in (activity_results or []):
            if ar.get("type") == "workout_analyze" and ar.get("status") == "analyzed":
                analysis_content = ar.get("message", "")
                if analysis_content:
                    workout_analysis_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=analysis_content)
                    self.db.add(workout_analysis_msg)
                    self.db.commit()
                    self.db.refresh(workout_analysis_msg)
                    result_data["workout_analysis"] = {
                        "message_id": workout_analysis_msg.id,
                        "content": analysis_content,
                    }
                break

        # 记录隐式反馈
        try:
            from app.services.feedback_service import feedback_service
            feedback_service.record_implicit(
                db=self.db,
                user_id=user_id,
                conversation_type="chat",
                conversation_id=conv.id,
                message_id=ai_msg.id,
                success=True,
                response_time_ms=int((_time_mod.time() - _stream_start) * 1000),
            )
        except Exception as e:
            logger.warning(f"记录隐式反馈失败: {e}")

        yield {"event": "done", "data": result_data}

    async def send_message_stream_proxy(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        is_admin: bool = False,
    ):
        """OpenClaw 代理模式：直接转发消息，不构建健康上下文，不解析动作"""
        # 获取或创建对话
        if conversation_id:
            conv = self.db.query(ChatConversation).filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            ).first()
            if not conv:
                yield {"event": "error", "data": {"message": "对话不存在"}}
                return
        else:
            conv = ChatConversation(user_id=user_id, title=message[:50], mode="proxy")
            self.db.add(conv)
            self.db.commit()
            self.db.refresh(conv)

        # 保存用户消息
        user_msg = ChatMessage(conversation_id=conv.id, role="user", content=message)
        self.db.add(user_msg)
        self.db.commit()

        # 检查是否为技能管理命令（管理员专属）
        skill_response = self._skills_handler.try_handle_skill_command(message, is_admin)
        if skill_response is not None:
            yield {"event": "token", "data": {"content": skill_response}}
            ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=skill_response)
            self.db.add(ai_msg)
            conv.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(ai_msg)
            yield {"event": "done", "data": {
                "conversation_id": conv.id,
                "message_id": ai_msg.id,
            }}
            return

        # 构建消息列表（无 system prompt，无健康上下文）
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()
        recent = history[-20:] if len(history) > 20 else history

        messages = [{"role": msg.role, "content": msg.content} for msg in recent]

        # 直接流式转发到 LLM
        full_response = ""
        try:
            async for token in self._call_openclaw_stream(messages):
                full_response += token
                yield {"event": "token", "data": {"content": token}}
        except Exception as e:
            logger.error(f"OpenClaw Proxy 流式调用失败: {type(e).__name__}: {e}")
            full_response = "抱歉，OpenClaw 暂时无法响应，请稍后再试。"
            yield {"event": "token", "data": {"content": full_response}}

        # 保存 AI 回复
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=full_response)
        self.db.add(ai_msg)
        conv.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ai_msg)

        yield {"event": "done", "data": {
            "conversation_id": conv.id,
            "message_id": ai_msg.id,
        }}

    # ── 对话 CRUD ──────────────────────────────────────────

    def get_conversations(self, user_id: int, limit: int = 20) -> List[ChatConversation]:
        """获取用户的对话列表"""
        return self.db.query(ChatConversation).filter(
            ChatConversation.user_id == user_id
        ).order_by(ChatConversation.updated_at.desc()).limit(limit).all()

    def get_conversation_messages(self, user_id: int, conversation_id: int) -> Optional[ChatConversation]:
        """获取对话详情及所有消息"""
        return self.db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id
        ).first()

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        """删除对话"""
        conv = self.db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id
        ).first()
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True
