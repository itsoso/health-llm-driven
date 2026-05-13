"""统一健康 Agent 执行器 — 结构化工具调用 + 多步推理循环

所有对话（记录、查询、分析、图片识别）统一走此入口。

流程：
  1. 注入健康上下文 + tool schemas
  2. 调用 LLM（OpenAI 兼容）
  3. 解析 tool_call → 执行 Health API
  4. 将 tool_result 返回模型 → 循环直到无更多 tool_call
  5. 最终回答通过 SSE 流式输出
"""
import json
import logging
import time
from datetime import UTC, datetime, timezone, timedelta
from typing import AsyncGenerator, Dict, Any, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.tool_schema_registry import get_health_tools

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
AGENT_MODEL = "NousResearch/Hermes-3-Llama-3.1-8B"
BEIJING_TZ = timezone(timedelta(hours=8))

import re
_NEEDS_SKILL_RE = re.compile(
    r"记录|打卡|吃了|喝了|服药|补剂|体重|血压|洗鼻|喷嚏|"
    r"早餐|午餐|晚餐|加餐|夜宵|早饭|午饭|晚饭|"
    r"固化到|钉到首页|保存到首页|加到计划|"
    r"大卡|kcal|热量.*记|记.*热量"
)

def _needs_skill(msg: str) -> bool:
    return bool(_NEEDS_SKILL_RE.search(msg))


def _confirm_or_describe(args: dict, data: dict, *, preview: str) -> str | None:
    """L8 (Karpathy "verification is the bottleneck"):
    高确定性 health_record 写库前强制 LLM 复述给用户确认.

    第一次调用 (无 confirmed flag): 返回 [NEEDS_CONFIRMATION] 提示,
    不写库. LLM 看到提示会复述给用户, 用户答'是的' → LLM 重新调用 + confirmed=true.

    Args:
        args: tool_call 顶层参数
        data: args.data (会被 mutate — 剥掉 confirmed 字段防 DB schema 不识别)
        preview: 给 LLM 复述的"我准备记录: ..." 部分

    Returns:
        非 None: 当前不写库, 直接 return 这个字符串
        None  : 已确认, 调用方继续写库流程
    """
    confirmed = (
        args.get("confirmed") is True or args.get("confirm") is True
        or data.get("confirmed") is True or data.get("confirm") is True
    )
    # 写库前剥掉 confirmed, 防 DB schema 不识别
    data.pop("confirmed", None)
    data.pop("confirm", None)
    if confirmed:
        return None
    return (
        f"[NEEDS_CONFIRMATION] 我准备记录: {preview}. "
        f"请向用户复述并问一次'是这样吗？', "
        f"用户确认后**重新调用** health_record 并在 data 里加 confirmed=true."
    )


class AgentExecutor:
    """统一健康 Agent 执行器"""

    def __init__(self, db: Session):
        self.db = db
        self._current_user_id: Optional[int] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def run_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        user_auth_token: Optional[str] = None,
        images: Optional[List[dict]] = None,
        file_base64: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """运行 Agent 循环，SSE 流式输出"""
        from app.services.llm.usage_tracker import set_caller
        set_caller("agent_executor.run_stream", user_id=user_id)
        # OpenClaw provider 不支持 function calling，记录类意图委托给 OpenClaw Gateway（有 skill）
        has_tools_support = bool(settings.agent_base_url and settings.agent_api_key) or settings.llm_provider != "openclaw"
        if not has_tools_support and (_needs_skill(message) or images or file_base64):
            async for evt in self._delegate_to_openclaw(user_id, message, conversation_id, user_auth_token, images, file_base64, file_name):
                yield evt
            return

        start_time = time.time()
        self._current_user_id = user_id

        # 1. 获取或创建会话（复用 OpenClaw 的对话管理）
        from app.services.openclaw_service import OpenClawService
        svc = OpenClawService(self.db)
        conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)

        # 保存用户消息（含图片标记）
        user_content = message
        saved_image_urls: List[str] = []
        if images:
            user_content += f"\n[附图: {len(images)}张]"
            for img in images:
                url = self._upload_chat_image(img["base64"], img.get("type", "jpeg"))
                if url:
                    saved_image_urls.append(url)
        if file_base64 and file_name:
            user_content += f"\n[附件: {file_name}]"
        image_url_value = json.dumps(saved_image_urls) if saved_image_urls else None
        svc.save_message(conv.id, "user", user_content, image_url=image_url_value)

        # 2. 构建 system prompt（复用健康上下文）
        system_content = self._build_system_prompt(user_id, conv.id, user_auth_token)

        # 3. 构建对话历史
        messages = svc.build_messages(conv.id, limit=15)
        messages.insert(0, {"role": "system", "content": system_content})

        # 如果有图片，先用 vision 模型识别内容，再将识别结果注入文本消息
        if images:
            vision_description = await self._analyze_image_with_vision(message, images)
            if vision_description:
                enriched_message = f"{message}\n\n[图片识别结果]: {vision_description}"
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i]["content"] = enriched_message
                        break
                logger.info(f"[Vision] 图片识别完成: {vision_description[:200]}")
            else:
                # Vision 模型不可用时，fallback 用多模态格式直接传图
                user_msg_content: list = [{"type": "text", "text": message}]
                for img in images:
                    user_msg_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{img.get('type', 'jpeg')};base64,{img['base64']}"},
                    })
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i]["content"] = user_msg_content
                        break

        # 4. 工具定义
        tools = get_health_tools()

        # 5. Agent 循环
        full_reply = ""
        yield {"event": "agent_start", "data": {"message": "Agent 正在分析..."}}

        # 2026-05-13: 计时 + 模型名可观测性 — 每轮 LLM 耗时积累到 done 事件
        llm_rounds_ms: list = []
        model_name: Optional[str] = None

        self._http_client = httpx.AsyncClient(timeout=90.0)
        try:
            import asyncio as _asyncio_loop
            for round_idx in range(MAX_TOOL_ROUNDS):
                # 调用 LLM（非流式，需要完整解析 tool_call）
                _round_start = time.time()
                response = await self._call_llm(messages, tools)
                llm_rounds_ms.append(int((time.time() - _round_start) * 1000))
                if model_name is None:
                    try:
                        from app.services.llm.factory import get_llm_provider
                        p = get_llm_provider()
                        model_name = getattr(p, "model", None) or getattr(p, "default_model", None) or getattr(p, "provider_name", None)
                    except Exception:
                        pass
                logger.info(f"LLM response type={type(response).__name__}, is_dict={isinstance(response, dict)}, has_tool_calls={isinstance(response, dict) and bool(response.get('tool_calls'))}, preview={str(response)[:200]}")

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

                        # 写操作成功后内联安全检查
                        if func_name == "health_record" and "Error" not in result:
                            try:
                                from app.twin.builder import build_twin
                                from app.agents.safety_guardian import evaluate_safety
                                twin = build_twin(self.db, user_id, use_cache=True)
                                report = evaluate_safety(twin)
                                critical = [a for a in report.alerts if int(a.severity) >= 3]
                                if critical:
                                    alert_msgs = "; ".join(a.title for a in critical[:3])
                                    result += f"\n\n⚠️ 安全提示: {alert_msgs}"
                            except Exception as e:
                                logger.warning(f"Safety check after write failed: {e}")

                        # 追加 tool_result 到 messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result,
                        })

                        # tool_result 事件给前端用. health_record 时附 args 让前端能识别
                        # 是哪种 record + 提取关键内容显示 summary 卡 (I Phase 2).
                        tool_event_data = {
                            "tool": func_name,
                            "success": not result.startswith("Error"),
                            "preview": result[:200],
                        }
                        if func_name == "health_record":
                            try:
                                parsed_args = json.loads(func_args) if isinstance(func_args, str) else func_args
                                tool_event_data["record_type"] = parsed_args.get("record_type")
                                tool_event_data["record_data"] = parsed_args.get("data") or {}
                            except Exception:
                                pass

                        yield {
                            "event": "tool_result",
                            "data": tool_event_data,
                        }

                    # 继续循环让模型处理 tool_result
                    continue

                else:
                    # 纯文本回复 — 最终答案，真流式输出
                    if isinstance(response, str):
                        # 已经是完整文本（fallback provider）
                        final_text = response
                        for i in range(0, len(final_text), 20):
                            chunk = final_text[i:i + 20]
                            yield {"event": "token", "data": {"content": chunk}}
                    else:
                        final_text = response.get("content") or ""
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
        finally:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

        # 6. 保存回复
        ai_msg = svc.save_message(conv.id, "assistant", full_reply)
        conv.updated_at = datetime.now(UTC)
        self.db.commit()

        elapsed_ms = int((time.time() - start_time) * 1000)
        llm_ms_total = sum(llm_rounds_ms)
        yield {
            "event": "done",
            "data": {
                "conversation_id": conv.id,
                "message_id": ai_msg.id,
                "elapsed_ms": elapsed_ms,
                "llm_ms": llm_ms_total,
                "llm_rounds": len(llm_rounds_ms),
                "llm_rounds_ms": llm_rounds_ms,
                "model": model_name,
                "mode": "agent",
            },
        }

    @staticmethod
    def _upload_chat_image(image_base64: str, image_type: str) -> Optional[str]:
        from app.services.chat_utils import upload_chat_image
        return upload_chat_image(image_base64, image_type)

    async def _delegate_to_openclaw(
        self, user_id: int, message: str,
        conversation_id: Optional[int] = None,
        user_auth_token: Optional[str] = None,
        images: Optional[List[dict]] = None,
        file_base64: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """委托给 OpenClaw Gateway（支持 Skill 写入数据）"""
        from app.services.openclaw_service import OpenClawService
        svc = OpenClawService(self.db)
        image_b64 = images[0]["base64"] if images else None
        image_type = images[0].get("type", "jpeg") if images else "jpeg"
        async for evt in svc.send_message_stream(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id,
            image_base64=image_b64,
            image_type=image_type,
            user_auth_token=user_auth_token,
        ):
            yield evt

    def _build_system_prompt(
        self, user_id: int, conv_id: int, user_auth_token: Optional[str]
    ) -> str:
        """构建统一 Agent 的 system prompt"""
        parts = [
            "你是用户的 AI 健康助理。你可以通过工具调用获取、记录和分析用户的健康数据。",
            "你是唯一的对话入口——用户的所有健康相关请求（记录数据、查询指标、深度分析、图片识别）都由你处理。",
            "",
            "## 工作方式",
            "1. 分析用户请求，决定需要调用哪些工具",
            "2. 调用工具获取或记录数据",
            "3. 基于返回的数据进行分析和推理",
            "4. 给出有据可依的建议",
            "5. 复合意图时在一次对话中同时处理（如'记一下吃了鱼油，看看对基因有什么影响' → 先记录后查询）",
            "",
            "## 数据记录规则",
            "- **核心原则：所有记录操作必须调用 health_record 工具才算完成。绝对不能口头说'已记录'而不调用工具。**",
            "- **修改记录也是新记录：用户修改了饮食内容后，必须重新调用 health_record(type=diet) 保存修改后的版本。**",
            "- 饮水、补剂打卡：直接执行，不需确认",
            "- 血压、血糖、体重：执行后复述确认数值（'已记录血压 138/92'）",
            "- 用户说'吃了XX'：药瓶/保健品名(鱼油/维C/B族等) → record_type=supplement；食物 → record_type=diet",
            "- 用户说'早上的药都吃了' → record_type=supplement_group, timing=morning",
            "- 模糊数量：'几杯水' → 追问具体杯数再记录；'130多' → 追问具体数值",
            "- 时间归属：'昨天' → 记到昨天日期；'刚才' → 当前时间；未说明 → 今天",
            "- 图片：用户发食物照片时，先用你的视觉能力识别图片中的食物名称和份量，然后调用 health_record(type=diet, data={meal_type, food_items, calories, record_date}) 记录。必须在 data 中填写完整的 food_items 字符串，不能传空 data。",
            "- **饮食记录必须包含热量估算：识别食物后，根据食物种类和常见份量估算总热量(kcal)，填入 data.calories 字段一起保存。不要记完再问用户'要不要算热量'。**",
            "- **重要：调用 health_record 时 data 参数必须包含具体内容，不能为空对象 {}。如果你不确定内容，先问用户再记录。**",
            "",
            "## 分析规则",
            "- 简单查询（'今天步数多少'）→ health_query",
            "- 趋势分析（'最近睡眠怎么样'）→ health_analysis",
            "- 跨领域复杂问题（'我的补剂方案合理吗'、'从基因角度看我该怎么调整'）→ health_analysis(type=orchestrator, question=...)",
            "",
            "## 行为准则",
            "- 数据驱动：引用具体数据，不要泛泛而谈",
            "- 主动分析：不仅回答问题，还要发现潜在问题",
            "- 中文回复：简洁实用，给出可执行的建议",
            "- 严重异常（HRV持续偏低、SpO2<92%、血压异常）→ 建议就医",
            "- 涉及药物的建议：附加'请咨询医生'免责声明",
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

        # 告诉 LLM 自己是哪个模型 — 用户问 "你是什么模型" 时如实答
        try:
            from app.services.llm.model_registry import get_active_model_id, get_model
            from app.config import settings as _settings
            active_id = get_active_model_id()
            if active_id:
                entry = get_model(active_id)
                if entry:
                    model_label = f"{entry.label} ({entry.model})"
                else:
                    model_label = active_id
            else:
                # 回落到 settings 默认
                provider = _settings.llm_provider
                if provider == "openai":
                    model_label = f"OpenAI {_settings.openai_model}"
                elif provider == "tokenplan":
                    model_label = f"Aliyun TokenPlan {_settings.tokenplan_model}"
                elif provider == "openclaw":
                    model_label = f"OpenClaw {_settings.openclaw_model}"
                else:
                    model_label = provider
            parts.append(
                "\n## 自我标识\n"
                f"- 你当前由 **{model_label}** 驱动。\n"
                "- 用户若问'你是什么模型'/'你用的是哪家 AI'/'底层模型版本'之类问题, 如实回答上面的 model_label.\n"
                "- 不要自称是 ChatGPT / Claude / 其他 — 以用户 admin 切换的为准."
            )
        except Exception:
            pass

        return "\n".join(parts)

    async def _call_llm(
        self, messages: List[Dict], tools: List[Dict],
    ) -> Any:
        """调用 LLM（优先走配置的 agent 端点，回退到默认 provider）"""
        agent_base = settings.agent_base_url
        agent_key = settings.agent_api_key

        # agent_model 仅当 AGENT_BASE_URL 显式配置时才用 (走 _call_llm_direct).
        # 否则走默认 provider 路径, model=None 让 provider 用自己 init 时的默认 model
        # (如 TokenPlan 用 settings.tokenplan_model = MiniMax-M2.5).
        # 旧逻辑用 settings.llm_model (gpt-4o-mini) 当 fallback model 名,
        # 直接发给 TokenPlan → Model not exist.
        if agent_base and agent_key:
            model = settings.agent_model or settings.llm_model
            return await self._call_llm_direct(messages, tools, model, agent_base, agent_key)

        # 回退到默认 provider — 不传 model, 让 provider 用 init 时的默认
        from app.services.llm.factory import get_llm_provider
        provider = get_llm_provider()
        pass_tools = tools if settings.llm_provider != "openclaw" else None
        return await provider.chat(
            messages=messages, model=None,
            temperature=0.3, max_tokens=4000, stream=False, tools=pass_tools,
        )

    async def _call_llm_direct(
        self, messages: List[Dict], tools: List[Dict],
        model: str, base_url: str, api_key: str,
    ) -> Any:
        """直接调用 OpenAI 兼容的 chatCompletions 端点，含 429 重试"""
        import asyncio as _asyncio

        url = f"{base_url.rstrip('/')}/chat/completions"

        has_image = any(
            isinstance(m.get("content"), list) and any(c.get("type") == "image_url" for c in m["content"])
            for m in messages if isinstance(m, dict)
        )
        logger.info(f"[_call_llm_direct] model={model}, base_url={base_url[:50]}, has_image={has_image}, msg_count={len(messages)}")
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

        max_retries = 3
        deadline = time.time() + 90
        client = self._http_client or httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0))
        for attempt in range(max_retries):
            if time.time() > deadline:
                raise RuntimeError("AI 服务响应超时，请稍后再试")
            t0 = time.time()
            try:
                logger.info(f"[_call_llm_direct] attempt={attempt+1} POST start")
                resp = await client.post(url, headers=headers, json=payload)
                latency_ms = int((time.time() - t0) * 1000)
                logger.info(f"[_call_llm_direct] attempt={attempt+1} POST done in {latency_ms/1000:.1f}s status={resp.status_code}")
                # 结构化 perf 指标 (machine-parseable, 用于 admin 看板汇总):
                # metric: llm_call provider=<base_url主机> model=<model> latency_ms=<n> status=<n> attempt=<n>
                try:
                    from urllib.parse import urlparse
                    host = urlparse(base_url).netloc
                except Exception:
                    host = base_url[:30]
                logger.info(
                    f"metric: llm_call provider={host} model={model} "
                    f"latency_ms={latency_ms} status={resp.status_code} attempt={attempt+1}"
                )
                if resp.status_code == 429:
                    wait = min(2 * (2 ** attempt), 10)  # 2s, 4s, 8s
                    logger.warning(f"LLM API 429 限流，第{attempt+1}/{max_retries}次重试，等待{wait}s")
                    await _asyncio.sleep(wait)
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(f"LLM API 返回 {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                break
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    wait = min(2 * (2 ** attempt), 8)
                    logger.warning(f"LLM API 超时/连接错误({type(e).__name__})，第{attempt+1}/{max_retries}次重试，等待{wait}s")
                    await _asyncio.sleep(wait)
                    continue
                raise
        else:
            raise RuntimeError("AI 服务暂时繁忙，请稍后再试")

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

    async def _analyze_image_with_vision(self, user_message: str, images: List[dict]) -> Optional[str]:
        """用 vision 模型预分析图片内容，返回文字描述"""
        if not settings.llm_vision_base_url or not settings.llm_vision_api_key:
            return None

        vision_model = settings.llm_vision_model or "qwen-vl-max"
        vision_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": (
                "你是一个食物识别助手。用户会发送食物照片，请你：\n"
                "1. 识别图片中所有食物的名称和大致份量\n"
                "2. 估算每种食物的热量(kcal)\n"
                "3. 估算这顿饭的总热量\n"
                "用简洁的中文回复，格式如：三文鱼150g(约250kcal)、黑米饭200g(约230kcal)、蔬菜100g(约30kcal)，总计约510kcal。"
            )},
            {"role": "user", "content": [
                {"type": "text", "text": user_message or "请识别这张图片中的食物"},
            ]},
        ]
        for img in images:
            vision_messages[1]["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/{img.get('type', 'jpeg')};base64,{img['base64']}"},
            })

        try:
            url = f"{settings.llm_vision_base_url.rstrip('/')}/chat/completions"
            payload = {
                "model": vision_model,
                "messages": vision_messages,
                "temperature": 0.3,
                "max_tokens": 500,
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.llm_vision_api_key}",
            }
            client = self._http_client or httpx.AsyncClient(timeout=60.0)
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                logger.warning(f"[Vision] 图片分析失败: HTTP {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"[Vision] 图片分析异常: {e}")
            return None

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

        # === 统一 tool_call 守门 (所有 6 个工具必过) ===
        # 日期/数值/枚举/引用 ID 存在性/越权 / 必填 — 触发 coerce 只 log,
        # 必填缺失或越权才返回 error 给 LLM (它会重试).
        from app.services.llm.tool_validator import validate_tool_call
        v = validate_tool_call(tool_name, args, db=self.db, user_id=self._current_user_id)
        if v["error"]:
            return v["error"]
        args = v["data"]

        base_url = settings.health_api_base_url or "http://localhost:8000/api/v1"
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
            elif tool_name == "manage_plan":
                return await self._exec_manage_plan(base_url, headers, args)
            elif tool_name == "upload_genetic_txt":
                return await self._exec_upload_genetic_txt(base_url, headers, args)
            elif tool_name == "query_genetic_profile":
                return await self._exec_query_genetic_profile(base_url, headers, args)
            elif tool_name == "upload_medical_exam_text":
                return await self._exec_upload_medical_exam_text(base_url, headers, args)
            elif tool_name == "query_lab_indicators":
                return await self._exec_query_lab_indicators(base_url, headers, args)
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
        indicator = args.get("indicator", "")
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

        endpoint_map = {
            "comprehensive": f"/garmin-analysis/me/comprehensive?days={days}",
            "sleep": f"/garmin-analysis/me/sleep?days={days}",
            "heart_rate": f"/garmin-analysis/me/heart-rate?days={days}",
            "hrv": f"/garmin-analysis/me/hrv?days={days}",
            "activity": f"/garmin-analysis/me/activity?days={days}",
            "spo2": "/spo2/me/latest-night",
            "spo2_sleep_correlation": f"/spo2/me/sleep-correlation?days={days}",
            "body_battery": f"/garmin-analysis/me/body-battery?days={days}",
            "stress": f"/garmin-analysis/me/stress?days={days}",
            "weight": "/weight/records/me/recent?limit=10",
            "blood_pressure": "/blood-pressure/records/me/recent?limit=10",
            "supplements": f"/supplements/me/stats?days={days}",
            "water": "/water/records/me/today",
            # diet 没有 /me/today 端点, 只有 /me/date/{record_date}; 用 today() 拼路径.
            "diet": f"/diet/records/me/date/{today}",
            # exercise 既包含 ExerciseRecord (手动录入的锻炼如俯卧撑/瑜伽),
            # 也要包含 WorkoutRecord (Garmin 同步的跑步/骑行等). LLM 问"昨天跑步"
            # 时应该拿到完整的运动数据.
            # /workout/me?days=N 是 WorkoutRecord, 含跑步/骑行/hiit/...
            # /exercise/me?days=N 是 ExerciseRecord (手动录入)
            # 默认用 workout (真实运动数据); 用户说"我做了 20 个俯卧撑"那种才走 exercise
            "exercise": f"/workout/me?days={days}",
            "workout": f"/workout/me?days={days}",
            "manual_exercise": f"/exercise/me?days={days}",
            "medical_exam": "/medical-exams/me",
            "genetic": "/genetic/variants/me",
            "genetic_cognitive": "/genetic/profile/me/cognitive",
            "genetic_personality": "/genetic/profile/me/personality",
            "genetic_comprehensive": "/genetic/profile/me/comprehensive",
            "medication": "/medication/medications/me",
        }

        path = endpoint_map.get(dim, endpoint_map["comprehensive"])
        result = await self._api_get(f"{base}{path}", headers)

        # 如果查的是体检或基因指标，从结果中过滤特定指标
        if indicator and dim in ("medical_exam", "genetic"):
            try:
                parsed = json.loads(result)
                items = parsed if isinstance(parsed, list) else parsed.get("data", [])
                matched = []
                if dim == "medical_exam":
                    for exam in items:
                        for item in (exam.get("items") or []):
                            name = str(item.get("item_name", "") or item.get("name", "")).upper()
                            if indicator.upper() in name:
                                matched.append({"exam_date": exam.get("exam_date"), **item})
                elif dim == "genetic":
                    for v in items:
                        gene = str(v.get("gene_name", "") or v.get("gene", "")).upper()
                        if indicator.upper() in gene:
                            matched.append(v)
                if matched:
                    return json.dumps(matched, ensure_ascii=False, default=str)
            except Exception:
                pass

        return result

    async def _exec_health_record(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """执行健康数据记录"""
        rtype = args.get("record_type", "")
        data = args.get("data", {})
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

        # water: 必须显式提供 amount, 不再悄悄默认 250ml.
        # 之前 LLM 在回答健康问题时偶发误调 health_record(water) 不带 amount,
        # 静默默认 250 → 用户看到莫名打卡. 现在: 没传 amount 直接 Error;
        # 传了也走 confirm gate, 跟 weight/blood_pressure 一致.
        if rtype == "water":
            amount = data.get("amount") or args.get("amount")
            if amount is None:
                return (
                    "Error: water 记录必须提供 amount (毫升, 整数). 例如 "
                    '{"record_type":"water","data":{"amount":250}}. '
                    "若用户没提具体毫升数, 请先问'喝了多少 ml?'再调用本工具."
                )
            try:
                amount_int = int(amount)
            except (ValueError, TypeError):
                return f"Error: water amount 必须是整数毫升 (got {amount!r})"
            if amount_int <= 0 or amount_int > 5000:
                return f"Error: water amount={amount_int} 不合理 (1-5000ml)"
            data["amount"] = amount_int
            check = _confirm_or_describe(
                args, data,
                preview=f"喝水 {amount_int}ml" + (f", {data['drink_type']}" if data.get("drink_type") else ""),
            )
            if check:
                return check

        # 补全 diet 必填字段
        if rtype == "diet":
            data.setdefault("record_date", today)
            data.setdefault("meal_type", "snack")
            # 中文 meal_type 映射
            meal_type_map = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner", "加餐": "snack", "夜宵": "snack"}
            if data.get("meal_type") in meal_type_map:
                data["meal_type"] = meal_type_map[data["meal_type"]]
            if isinstance(data.get("food_items"), list):
                data["food_items"] = ", ".join(
                    (f.get("name", str(f)) if isinstance(f, dict) else str(f))
                    for f in data["food_items"]
                )
            elif not data.get("food_items"):
                data["food_items"] = data.get("description", data.get("notes", ""))
            if not data.get("food_items"):
                return "Error: diet 记录必须提供 food_items（食物内容）。请先识别食物内容，然后重新调用 health_record 并在 data.food_items 中填写具体食物。"

        # 补全 weight 必填字段
        if rtype == "weight":
            data.setdefault("record_date", today)
            # LLM 常把 weight 直接放在顶层 args 而不是 args.data (参数 schema 歧义)
            # 兜底: 顶层有就挪到 data
            for src in ("weight", "value", "weight_kg", "体重"):
                if src in args and "weight" not in data:
                    data["weight"] = args[src]
                    break
            if "weight" not in data and "value" in data:
                data["weight"] = data.pop("value")
            if "weight" not in data and "weight_kg" in data:
                data["weight"] = data.pop("weight_kg")
            if "weight" not in data:
                return "Error: weight 记录必须提供 weight（体重数值，单位 kg）。请在 data.weight 中填入数字，例如 {\"record_type\":\"weight\",\"data\":{\"weight\":71.2}}"

            # L8 (Karpathy "verification is the bottleneck"): 高确定性数值, 写错没法静默修正
            check = _confirm_or_describe(
                args, data,
                preview=f"体重 {data['weight']} kg, 日期 {data.get('record_date', today)}",
            )
            if check:
                return check

        # 补全 blood_pressure 必填字段
        if rtype == "blood_pressure":
            data.setdefault("record_date", today)
            sys_v = data.get("systolic")
            dia_v = data.get("diastolic")
            # 顶层 args 兜底 (LLM 偶尔放错位置)
            if sys_v is None and args.get("systolic") is not None:
                data["systolic"] = sys_v = args["systolic"]
            if dia_v is None and args.get("diastolic") is not None:
                data["diastolic"] = dia_v = args["diastolic"]
            if sys_v is None or dia_v is None:
                return (
                    "Error: blood_pressure 记录必须提供 systolic + diastolic. 例如 "
                    '{"record_type":"blood_pressure","data":{"systolic":120,"diastolic":80}}'
                )
            # L8: 血压数值高/低风险大, 必须先确认
            check = _confirm_or_describe(
                args, data,
                preview=f"血压 {sys_v}/{dia_v}, 日期 {data.get('record_date', today)}",
            )
            if check:
                return check

        # illness 急性症状记录 — 影响疾病追踪, 必须先确认
        if rtype == "illness":
            data.setdefault("start_date", today)
            name = data.get("illness_name") or args.get("illness_name")
            if not name:
                return (
                    "Error: illness 记录必须提供 illness_name. 例如 "
                    '{"record_type":"illness","data":{"illness_name":"感冒","severity":5}}'
                )
            data["illness_name"] = name
            sev = data.get("severity") or args.get("severity")
            if sev is not None:
                data["severity"] = sev
            preview_bits = [f"生病: {name}"]
            if sev is not None:
                preview_bits.append(f"严重度 {sev}")
            preview_bits.append(f"开始 {data.get('start_date')}")
            check = _confirm_or_describe(args, data, preview=", ".join(preview_bits))
            if check:
                return check

        # 补全 exercise 必填字段 + LLM 常见字段别名映射
        if rtype == "exercise":
            data.setdefault("record_date", today)
            # LLM 可能用 count/次数/repetitions 代替 reps
            for src in ("count", "repetitions", "次数"):
                if src in data and "reps" not in data:
                    data["reps"] = data.pop(src)
            # LLM 可能用 duration_minutes / minutes 代替 duration
            for src in ("duration_minutes", "minutes", "分钟"):
                if src in data and "duration" not in data:
                    data["duration"] = data.pop(src)
            # exercise_type 必填, 若缺失从 type / name 回退
            if not data.get("exercise_type"):
                data["exercise_type"] = data.get("type") or data.get("name") or "其他"

        # rhinitis: 症状计数转 illness_episode (复用 illness 流程, 跟 rhinitis-tracker skill 对齐)
        if rtype == "rhinitis":
            sneezing = int(data.get("sneezing", 0) or 0)
            congestion = int(data.get("congestion", 0) or 0)
            runny_nose = int(data.get("runny_nose", 0) or 0)
            # 严重度取 congestion/runny_nose 的 1-10 量表 max, 无则按喷嚏频率兜底
            severity_vals = [v for v in (congestion, runny_nose) if v and 0 < v <= 10]
            severity = (max(severity_vals) if severity_vals
                        else (min(8, max(3, sneezing // 3)) if sneezing else 2))
            parts = []
            if sneezing: parts.append(f"喷嚏 {sneezing} 次")
            if congestion: parts.append(f"鼻塞 {congestion}/10")
            if runny_nose: parts.append(f"流涕 {runny_nose} 次")
            notes = data.get("notes") or "、".join(parts) or "鼻炎症状"
            payload = {
                "illness_name": "鼻炎发作",
                "severity": severity,
                "notes": notes,
                "start_date": data.get("record_date") or today,
            }
            return await self._api_post(f"{base}/illness/episodes", headers, payload)

        # supplement_group: 按时段批量打卡
        if rtype == "supplement_group":
            timing = data.get("timing", "morning")
            result = await self._api_post(
                f"{base}/nfc/tap", headers,
                {"action": "supplement_group", "timing": timing}
            )
            logger.info(f"[health_record] supplement_group timing={timing}")
            return result

        # supplement: 按名称匹配补剂打卡
        if rtype == "supplement":
            name = data.get("supplement_name", data.get("name", ""))
            if name:
                # 查找匹配的补剂定义
                lookup = await self._api_get(f"{base}/supplements/me/definitions", headers)
                try:
                    supps = json.loads(lookup)
                    supps = supps if isinstance(supps, list) else supps.get("data", [])
                    matched = next((s for s in supps if s.get("is_active") and name.lower() in s.get("name", "").lower()), None)
                    if matched:
                        result = await self._api_post(
                            f"{base}/nfc/tap", headers,
                            {"action": "supplement", "supplement_id": matched["id"]}
                        )
                        return result
                    return f"未找到名为 '{name}' 的活跃补剂"
                except Exception as e:
                    return f"Error: 补剂查找失败: {e}"
            return "Error: 需要提供补剂名称（supplement_name）"

        # medication: 用药记录
        if rtype == "medication":
            med_name = data.get("medication_name", data.get("name", ""))
            if not med_name:
                return "Error: 需要提供药物名称（medication_name）"
            # 查找 medication_id
            meds_raw = await self._api_get(f"{base}/medication/medications/me", headers)
            try:
                meds = json.loads(meds_raw)
                meds = meds if isinstance(meds, list) else meds.get("data", [])
                matched = next((m for m in meds if m.get("is_active") and med_name.lower() in m.get("name", "").lower()), None)
                if matched:
                    taken_time = data.get("taken_time", datetime.now(BEIJING_TZ).isoformat())
                    result = await self._api_post(
                        f"{base}/medication/logs", headers,
                        {"medication_id": matched["id"], "taken_time": taken_time, "status": "taken"}
                    )
                    return result
                return f"未找到名为 '{med_name}' 的活跃药物"
            except Exception as e:
                return f"Error: 用药记录失败: {e}"

        record_map = {
            # water 走前面早返路径 (L732), 不会从 record_map 命中, 但保留占位避免后续误判
            "water": ("/water/records/quick", "POST", {
                "amount": data.get("amount"),
                **({"drink_type": data["drink_type"]} if data.get("drink_type") else {}),
            }),
            "weight": ("/weight/records", "POST", data),
            "blood_pressure": ("/blood-pressure/records", "POST", data),
            "exercise": ("/daily-health/exercise", "POST", data),
            "diet": ("/diet/records", "POST", data),
            "supplement": ("/supplements/records", "POST", data),
            # rhinitis 走 special case (见上方 rtype=="rhinitis" 分支), 不在 record_map 里
            "mood": ("/mood/records", "POST", data),
            "illness": ("/illness/episodes", "POST", data),
            "garmin_sync": ("/data-collection/garmin/me/sync?days=1", "POST", {}),
            "reminder": ("/reminders/me", "POST", data),
        }

        # symptom: 通用身体症状 (眼痒/嗓子疼 ...). 不再需要 profile_id (新 /symptoms 表,
        # 2026-05-08 改, 替换旧 disease_tracking.SymptomLog 路径 — 那路径强行要 profile_id,
        # 用户体验差, 已废弃. 鼻炎打卡走 record_type="rhinitis".
        if rtype == "symptom":
            body_part = data.get("body_part")
            description = data.get("description")
            if not body_part:
                return "Error: symptom 必须提供 body_part (eye/respiratory/skin/digestive/musculoskeletal/head/general/other)"
            if not description:
                return "Error: symptom 必须提供 description (如 '眼睛痒' / '右膝盖钝痛')"
            # 标记 source=voice 便于前端区分手工 / 语音入口
            payload = dict(data)
            payload.setdefault("source", "voice")
            return await self._api_post(f"{base}/symptoms", headers, payload)

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
        question = args.get("question", "")

        # orchestrator: 多专家协作深度分析
        if atype == "orchestrator" and question:
            result = await self._api_post(
                f"{base}/orchestrator/chat", headers,
                {"query": question}
            )
            return result

        # supplement_effectiveness: 补剂效果评估
        if atype == "supplement_effectiveness":
            result = await self._api_post(
                f"{base}/supplements/scientific-recommendation", headers,
                {"use_llm": True}
            )
            return result

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
            # outdoor-advice 是历史 typo, 真实端点: exercise-suitability (单项) /
            # advice (综合). 用 advice 信息更全, 含天气+AQI+UV+建议
            "outdoor_suitability": "/environment/advice",
            "exercise_suitability": "/environment/exercise-suitability",
            "morning_briefing": "/environment/morning-briefing",
            "forecast": "/environment/weather/forecast?days=3",
        }
        path = path_map.get(ctype, "/environment/weather")
        return await self._api_get(f"{base}{path}", headers)

    async def _exec_supplement_guide(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """获取补剂指南"""
        return await self._api_get(f"{base}/supplements/daily-guide", headers)

    async def _exec_manage_plan(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """管理健康计划"""
        action = args.get("action", "")
        data = args.get("data", {})

        if action == "generate_weekly":
            return await self._api_post(f"{base}/smart-plan/generate", headers, data)
        elif action == "complete_item":
            plan_id = data.get("plan_id")
            item_id = data.get("item_id")
            if plan_id and item_id:
                return await self._api_patch(
                    f"{base}/smart-plan/{plan_id}/items/{item_id}",
                    headers, {"is_completed": True}
                )
            return "Error: 需要 plan_id 和 item_id"
        elif action == "save_to_card":
            return await self._api_post(f"{base}/action-cards/from-message", headers, data)
        return f"Error: 不支持的计划操作 {action}"

    async def _exec_upload_genetic_txt(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """上传 23andMe / WeGene TXT 原始数据."""
        txt = args.get("txt_content") or ""
        if len(txt) < 50:
            return "Error: txt_content 太短, 不像是 23andMe/WeGene 原始数据 (应是含 rsid 的 tab 分隔行)"
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
        payload = {
            "test_provider": args.get("test_provider") or "unknown",
            "test_date": args.get("test_date") or today,
            "txt_content": txt,
            "notes": args.get("notes") or "LLM 工具自动上传",
        }
        return await self._api_post(f"{base}/genetic/profiles/upload-txt", headers, payload)

    async def _exec_query_genetic_profile(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """列出基因档案."""
        return await self._api_get(f"{base}/genetic/profiles/me", headers)

    async def _exec_upload_medical_exam_text(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """口述化验文本 → medical_text_parser → 入 MedicalExam + Indicator."""
        text = (args.get("text") or "").strip()
        if not text:
            return "Error: text 不能为空"
        # 复用 family_health 的 parse-medical-text (内部 LLM 抽指标 + 路由入库)
        return await self._api_post(
            f"{base}/family-health/parse-medical-text", headers, {"text": text}
        )

    async def _exec_query_lab_indicators(
        self, base: str, headers: dict, args: dict
    ) -> str:
        """查询 MedicalIndicator (跨次体检的单指标历史). 直接读 DB, 不走 HTTP."""
        from app.models.family_health import MedicalIndicator
        from sqlalchemy import or_, desc as sa_desc

        if self._current_user_id is None:
            return "Error: 当前会话无 user_id, 无法查询"

        name = (args.get("name") or "").strip()
        since_str = args.get("since")
        limit = max(1, min(int(args.get("limit") or 20), 100))

        try:
            from datetime import date as _date
            if since_str:
                since = datetime.strptime(since_str, "%Y-%m-%d").date()
            else:
                since = _date.today() - timedelta(days=365)
        except Exception:
            return f"Error: since 必须是 YYYY-MM-DD, got {since_str!r}"

        q = self.db.query(MedicalIndicator).filter(
            MedicalIndicator.user_id == self._current_user_id,
            MedicalIndicator.record_date >= since,
        )
        if name:
            up = name.upper()
            q = q.filter(or_(
                MedicalIndicator.name == name,
                MedicalIndicator.name_en == up,
                MedicalIndicator.name.ilike(f"%{name}%"),
            ))
        rows = q.order_by(sa_desc(MedicalIndicator.record_date)).limit(limit).all()
        if not rows:
            return json.dumps({"count": 0, "items": [], "hint": f"未找到 {name or '任何'} 指标"}, ensure_ascii=False)
        items = [
            {
                "name": r.name, "name_en": r.name_en,
                "value": r.value, "unit": r.unit,
                "record_date": r.record_date.isoformat() if r.record_date else None,
                "is_abnormal": r.is_abnormal,
                "reference_low": r.reference_low,
                "reference_high": r.reference_high,
            }
            for r in rows
        ]
        return json.dumps({"count": len(items), "items": items}, ensure_ascii=False)

    async def _api_get(self, url: str, headers: dict) -> str:
        """HTTP GET"""
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        text = resp.text
        if len(text) > 3000:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list) and len(parsed) > 10:
                    parsed = parsed[:10]
                    return json.dumps(parsed, ensure_ascii=False, default=str) + "\n...(仅显示前10条)"
                elif isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if isinstance(v, list) and len(v) > 10:
                            parsed[k] = v[:10]
                    truncated = json.dumps(parsed, ensure_ascii=False, default=str)
                    if len(truncated) > 4000:
                        truncated = truncated[:4000] + "...}"
                    return truncated
            except Exception:
                pass
            text = text[:3000] + "\n...(数据已截断)"
        return text

    async def _api_post(self, url: str, headers: dict, data: dict) -> str:
        """HTTP POST"""
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.post(url, headers={**headers, "Content-Type": "application/json"}, json=data)
        if resp.status_code not in (200, 201):
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        return resp.text

    async def _api_patch(self, url: str, headers: dict, data: dict) -> str:
        """HTTP PATCH"""
        client = self._http_client or httpx.AsyncClient(timeout=90.0)
        resp = await client.patch(url, headers={**headers, "Content-Type": "application/json"}, json=data)
        if resp.status_code not in (200, 201):
            return f"Error: API 返回 {resp.status_code}: {resp.text[:200]}"
        return resp.text
