"""Hermes Agent 执行器 — 结构化工具调用 + 多步推理循环

路径 B 方案：复杂任务走 Agent 执行器（Hermes 模型 + tool_call），
普通对话仍走 OpenClaw。

流程：
  1. 注入健康上下文 + tool schemas
  2. 调用 Hermes 模型（OpenAI 兼容）
  3. 解析 tool_call → 执行 Health API
  4. 将 tool_result 返回模型 → 循环直到无更多 tool_call
  5. 最终回答通过 SSE 流式输出
"""
import json
import logging
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.tool_schema_registry import get_health_tools

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6  # 最多 6 轮工具调用，防止死循环
AGENT_MODEL = "NousResearch/Hermes-3-Llama-3.1-8B"  # 可通过 config 覆盖


class AgentExecutor:
    """Hermes Agent 执行器"""

    def __init__(self, db: Session):
        self.db = db

    async def run_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        user_auth_token: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """运行 Agent 循环，SSE 流式输出"""
        start_time = time.time()

        # 1. 获取或创建会话（复用 OpenClaw 的对话管理）
        from app.services.openclaw_service import OpenClawService
        svc = OpenClawService(self.db)
        conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)
        svc.save_message(conv.id, "user", message)

        # 2. 构建 system prompt（复用健康上下文）
        system_content = self._build_system_prompt(user_id, conv.id, user_auth_token)

        # 3. 构建对话历史
        messages = svc.build_messages(conv.id, limit=15)
        messages.insert(0, {"role": "system", "content": system_content})

        # 4. 工具定义
        tools = get_health_tools()

        # 5. Agent 循环
        full_reply = ""
        yield {"event": "agent_start", "data": {"message": "Agent 正在分析..."}}

        try:
            import asyncio as _asyncio_loop
            for round_idx in range(MAX_TOOL_ROUNDS):
                # 多轮间加间隔，防止触发 Nginx 限流
                if round_idx > 0:
                    await _asyncio_loop.sleep(2)
                # 调用 LLM（非流式，需要完整解析 tool_call）
                response = await self._call_llm(messages, tools)

                # 检查是否有 tool_call
                if isinstance(response, dict) and response.get("tool_calls"):
                    tool_calls = response["tool_calls"]
                    text_content = response.get("content") or ""

                    # 流式输出思考过程
                    if text_content:
                        yield {"event": "token", "data": {"content": text_content}}
                        full_reply += text_content

                    # 追加 assistant message（含 tool_calls）
                    messages.append({
                        "role": "assistant",
                        "content": text_content,
                        "tool_calls": tool_calls,
                    })

                    # 执行每个工具
                    for tc in tool_calls:
                        func_name = tc["function"]["name"]
                        func_args = tc["function"]["arguments"]
                        tool_id = tc["id"]

                        # 通知前端正在执行工具
                        yield {
                            "event": "tool_call",
                            "data": {
                                "tool": func_name,
                                "args": func_args if isinstance(func_args, str) else json.dumps(func_args, ensure_ascii=False),
                                "round": round_idx + 1,
                            },
                        }

                        # 执行工具
                        result = await self._execute_tool(
                            func_name, func_args, user_auth_token
                        )

                        # 追加 tool_result 到 messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result,
                        })

                        yield {
                            "event": "tool_result",
                            "data": {
                                "tool": func_name,
                                "success": not result.startswith("Error"),
                                "preview": result[:200],
                            },
                        }

                    # 继续循环让模型处理 tool_result
                    continue

                else:
                    # 纯文本回复 — 最终答案
                    final_text = response if isinstance(response, str) else (response.get("content") or "")

                    # 流式输出最终回答
                    # 为了模拟流式体验，分块发送
                    for i in range(0, len(final_text), 20):
                        chunk = final_text[i:i + 20]
                        yield {"event": "token", "data": {"content": chunk}}
                    full_reply += final_text
                    break

            else:
                # 达到最大轮次
                msg = "\n\n（已达到最大推理轮次，结束分析）"
                yield {"event": "token", "data": {"content": msg}}
                full_reply += msg

        except Exception as e:
            logger.error(f"Agent 执行异常: {e}", exc_info=True)
            error_msg = f"Agent 执行遇到问题: {str(e)}"
            yield {"event": "token", "data": {"content": error_msg}}
            full_reply = error_msg

        # 6. 保存回复
        ai_msg = svc.save_message(conv.id, "assistant", full_reply)
        conv.updated_at = datetime.utcnow()
        self.db.commit()

        elapsed_ms = int((time.time() - start_time) * 1000)
        yield {
            "event": "done",
            "data": {
                "conversation_id": conv.id,
                "message_id": ai_msg.id,
                "elapsed_ms": elapsed_ms,
                "mode": "agent",
            },
        }

    def _build_system_prompt(
        self, user_id: int, conv_id: int, user_auth_token: Optional[str]
    ) -> str:
        """构建 Agent 的 system prompt"""
        parts = [
            "你是用户的 AI 健康助理（Agent 模式）。你可以通过工具调用获取和记录用户的健康数据。",
            "",
            "## 工作方式",
            "1. 分析用户请求，决定需要调用哪些工具",
            "2. 调用工具获取数据",
            "3. 基于返回的数据进行分析和推理",
            "4. 给出有据可依的建议",
            "",
            "## 行为准则",
            "- 数据驱动：引用具体数据，不要泛泛而谈",
            "- 主动分析：不仅回答问题，还要发现潜在问题",
            "- 中文回复：简洁实用，给出可执行的建议",
            "- 严重异常（HRV持续偏低、SpO2<92%、血压异常）→ 建议就医",
            "",
            "## 基因解读规则（必须遵守）",
            "- 标记为[优势]的基因是保护性基因，不要误判为需要干预的风险基因",
            "- FADS1 TT = 东亚高效转化型，植物源Omega-3转化能力强，是优势基因",
            "- SOD2 AA(Ala/Ala) = MnSOD线粒体转运效率高，是优势基因",
            "- GPX1 GG = 谷胱甘肽过氧化物酶活性正常，不需要额外干预",
            "- ⚠️用药安全基因必须优先展示和警告（CYP2D6慢代谢→止痛药危险、SLCO1B1 CT→他汀肌病风险）",
            "- 补剂推荐必须交叉参考体检历史（肾结石→维D/钙谨慎、肝功异常→某些补剂禁忌）",
            "- 补剂剂量不能简单按mg数比较不同剂型（如MitoQ 5mg ≈ 线粒体内CoQ10 200-500mg）",
            "- 补剂受法规限制剂量时（如钾99mg/粒），优先推荐饮食策略而非加量",
        ]

        # 注入健康上下文
        try:
            from app.services.health_context_lite_service import (
                build_lite_health_context, _get_time_period,
            )
            health_ctx = build_lite_health_context(self.db, user_id)
            if health_ctx:
                parts.append("\n## 用户健康档案")
                parts.append(health_ctx)

            _, period = _get_time_period()
            parts.append(f"\n当前时段: {period}")
        except Exception as e:
            logger.warning(f"Agent 健康上下文注入失败: {e}")

        # 注入记忆
        try:
            from app.services.conversation_memory_service import get_relevant_memories
            memories = get_relevant_memories(self.db, user_id, limit=5)
            if memories:
                parts.append("\n## 用户记忆")
                parts.append(memories)
        except Exception:
            pass

        return "\n".join(parts)

    async def _call_llm(
        self, messages: List[Dict], tools: List[Dict]
    ) -> Any:
        """调用 LLM（优先走 OpenClaw Gateway，回退到默认 provider）"""
        agent_base = settings.agent_base_url
        agent_key = settings.agent_api_key
        model = settings.agent_model or settings.llm_model

        if agent_base and agent_key:
            # 走 OpenClaw Gateway chatCompletions（去掉第三方代理）
            return await self._call_llm_direct(messages, tools, model, agent_base, agent_key)

        # 回退到默认 provider
        from app.services.llm.factory import get_llm_provider
        provider = get_llm_provider()
        return await provider.chat(
            messages=messages, model=model,
            temperature=0.3, max_tokens=4000, stream=False, tools=tools,
        )

    async def _call_llm_direct(
        self, messages: List[Dict], tools: List[Dict],
        model: str, base_url: str, api_key: str,
    ) -> Any:
        """直接调用 OpenAI 兼容的 chatCompletions 端点，含 429 重试"""
        import asyncio as _asyncio

        url = f"{base_url.rstrip('/')}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4000,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t["function"]} if "function" in t else t for t in tools]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        max_retries = 5
        for attempt in range(max_retries):
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 429:
                    wait = min(10 * (2 ** attempt), 60)  # 10s, 20s, 40s, 60s, 60s
                    logger.warning(f"LLM API 429 限流，第{attempt+1}/{max_retries}次重试，等待{wait}s")
                    await _asyncio.sleep(wait)
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(f"LLM API 返回 {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                break
        else:
            raise RuntimeError("AI 服务暂时繁忙，请稍后再试（已重试5次）")

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})

        # 解析 tool_calls
        if msg.get("tool_calls"):
            return {
                "content": msg.get("content") or "",
                "tool_calls": [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"].get("arguments", "{}"),
                        },
                    }
                    for i, tc in enumerate(msg["tool_calls"])
                ],
            }
        return msg.get("content") or ""

    async def _execute_tool(
        self, tool_name: str, args_raw: Any, user_token: Optional[str]
    ) -> str:
        """执行工具调用，返回结果文本"""
        try:
            if isinstance(args_raw, str):
                args = json.loads(args_raw)
            else:
                args = args_raw
        except json.JSONDecodeError:
            return f"Error: 参数解析失败: {args_raw}"

        base_url = "https://health.executor.life/api"
        headers = {"Authorization": f"Bearer {user_token}"} if user_token else {}

        try:
            if tool_name == "health_query":
                return await self._exec_health_query(base_url, headers, args)
            elif tool_name == "health_record":
                return await self._exec_health_record(base_url, headers, args)
            elif tool_name == "health_analysis":
                return await self._exec_health_analysis(base_url, headers, args)
            elif tool_name == "environment_check":
                return await self._exec_environment(base_url, headers, args)
            elif tool_name == "supplement_guide":
                return await self._exec_supplement_guide(base_url, headers, args)
            else:
                return f"Error: 未知工具 {tool_name}"
        except Exception as e:
            logger.error(f"工具执行失败 {tool_name}: {e}")
            return f"Error: {tool_name} 执行失败: {str(e)}"

    async def _exec_health_query(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康数据查询"""
        dim = args.get("dimension", "comprehensive")
        days = args.get("days", 7)

        endpoint_map = {
            "comprehensive": f"/garmin-analysis/me/comprehensive?days={days}",
            "sleep": f"/garmin-analysis/me/sleep?days={days}",
            "heart_rate": f"/garmin-analysis/me/heart-rate?days={days}",
            "hrv": f"/garmin-analysis/me/hrv?days={days}",
            "activity": f"/garmin-analysis/me/activity?days={days}",
            "spo2": f"/garmin-analysis/me/spo2?days={days}",
            "body_battery": f"/garmin-analysis/me/body-battery?days={days}",
            "stress": f"/garmin-analysis/me/stress?days={days}",
            "weight": "/weight/records/me/recent?limit=10",
            "blood_pressure": "/blood-pressure/records/me/recent?limit=10",
            "supplements": f"/supplements/me/date/{datetime.now().strftime('%Y-%m-%d')}",
            "water": "/water/records/me/today",
            "diet": "/diet/records/me/today",
            "exercise": "/exercise/me/today",
        }

        path = endpoint_map.get(dim, endpoint_map["comprehensive"])
        return await self._api_get(f"{base}{path}", headers)

    async def _exec_health_record(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康数据记录"""
        rtype = args.get("record_type", "")
        data = args.get("data", {})
        today = datetime.now().strftime("%Y-%m-%d")

        # 补全 diet 必填字段
        if rtype == "diet":
            data.setdefault("record_date", today)
            data.setdefault("meal_type", "snack")
            # food_items 必须是字符串
            if isinstance(data.get("food_items"), list):
                data["food_items"] = ", ".join(
                    (f.get("name", str(f)) if isinstance(f, dict) else str(f))
                    for f in data["food_items"]
                )
            elif not data.get("food_items"):
                data["food_items"] = data.get("description", data.get("notes", "未知食物"))

        # 补全 weight 必填字段
        if rtype == "weight":
            data.setdefault("record_date", today)
            # 兼容 LLM 传 value/weight_kg 等字段名
            if "weight" not in data and "value" in data:
                data["weight"] = data.pop("value")
            if "weight" not in data and "weight_kg" in data:
                data["weight"] = data.pop("weight_kg")

        record_map = {
            "water": ("/water/records/quick", "POST", {"amount": data.get("amount", 250)}),
            "weight": ("/weight/records", "POST", data),
            "blood_pressure": ("/blood-pressure/records", "POST", data),
            "exercise": ("/exercise/records", "POST", data),
            "diet": ("/diet/records", "POST", data),
            "supplement": ("/supplements/records", "POST", data),
            "rhinitis": ("/health-checkin/me/rhinitis", "POST", data),
            "mood": ("/mood/records", "POST", data),
        }

        if rtype in record_map:
            path, method, payload = record_map[rtype]
            if method == "POST":
                result = await self._api_post(f"{base}{path}", headers, payload)
                logger.info(f"[health_record] type={rtype} result={result[:200]}")
                return result
        return f"Error: 不支持的记录类型 {rtype}"

    async def _exec_health_analysis(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康分析"""
        atype = args.get("analysis_type", "comprehensive")
        days = args.get("days", 7)

        analysis_map = {
            "comprehensive": f"/garmin-analysis/me/comprehensive?days={days}",
            "sleep_insight": f"/garmin-analysis/me/sleep?days={days}",
            "heart_rate_insight": f"/garmin-analysis/me/heart-rate?days={days}",
            "recovery_status": f"/garmin-analysis/me/body-battery?days={days}",
            "risk_factors": f"/garmin-analysis/me/comprehensive?days={days}",
            "trend": f"/garmin-analysis/me/comprehensive?days={days}",
        }

        path = analysis_map.get(atype, analysis_map["comprehensive"])
        return await self._api_get(f"{base}{path}", headers)

    async def _exec_environment(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行环境数据查询"""
        ctype = args.get("check_type", "weather")
        path_map = {
            "weather": "/environment/weather",
            "air_quality": "/environment/air-quality",
            "outdoor_suitability": "/environment/outdoor-advice",
        }
        path = path_map.get(ctype, "/environment/weather")
        return await self._api_get(f"{base}{path}", headers)

    async def _exec_supplement_guide(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """获取补剂指南"""
        return await self._api_get(f"{base}/supplements/daily-guide", headers)

    async def _api_get(self, url: str, headers: dict) -> str:
        """HTTP GET"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
            # 截断过长的响应
            text = resp.text
            if len(text) > 3000:
                text = text[:3000] + "\n...(数据已截断)"
            return text

    async def _api_post(self, url: str, headers: dict, data: dict) -> str:
        """HTTP POST"""
        headers = {**headers, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=data)
            if resp.status_code not in (200, 201):
                return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
            return resp.text
