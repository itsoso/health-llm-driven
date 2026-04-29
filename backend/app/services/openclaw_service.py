"""OpenClaw Channel 对话服务 — 代理连接 OpenClaw Gateway"""
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import AsyncGenerator, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.openclaw import OpenClawConversation, OpenClawMessage
from app.services.openclaw_skills_service import openclaw_skills_service
from app.services.skills_hub_client import skills_hub_client

logger = logging.getLogger(__name__)


class OpenClawService:
    """OpenClaw Channel 服务"""

    def __init__(self, db: Session):
        self.db = db

    # ── 会话管理 ──────────────────────────────────────────

    def get_or_create_conversation(
        self, user_id: int, conversation_id: Optional[int], title: str = "新对话"
    ) -> OpenClawConversation:
        if conversation_id:
            conv = (
                self.db.query(OpenClawConversation)
                .filter(
                    OpenClawConversation.id == conversation_id,
                    OpenClawConversation.user_id == user_id,
                )
                .first()
            )
            if not conv:
                raise ValueError("对话不存在")
            return conv

        conv = OpenClawConversation(
            user_id=user_id,
            title=title[:50],
            session_key=f"health-{user_id}-{uuid.uuid4().hex[:12]}",
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get_conversations(self, user_id: int, limit: int = 20, title_like: Optional[str] = None) -> List[OpenClawConversation]:
        q = (
            self.db.query(OpenClawConversation)
            .filter(OpenClawConversation.user_id == user_id)
        )
        if title_like:
            q = q.filter(OpenClawConversation.title.ilike(f"%{title_like}%"))
        return q.order_by(OpenClawConversation.updated_at.desc()).limit(limit).all()

    def get_conversation_detail(
        self, user_id: int, conversation_id: int
    ) -> Optional[OpenClawConversation]:
        from sqlalchemy.orm import joinedload
        return (
            self.db.query(OpenClawConversation)
            .options(joinedload(OpenClawConversation.messages))
            .filter(
                OpenClawConversation.id == conversation_id,
                OpenClawConversation.user_id == user_id,
            )
            .first()
        )

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        conv = (
            self.db.query(OpenClawConversation)
            .filter(
                OpenClawConversation.id == conversation_id,
                OpenClawConversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True

    # ── 消息管理 ──────────────────────────────────────────

    def save_message(self, conversation_id: int, role: str, content: str, image_url: str | None = None) -> OpenClawMessage:
        msg = OpenClawMessage(conversation_id=conversation_id, role=role, content=content, image_url=image_url)
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def build_messages(self, conversation_id: int, limit: int = 20) -> List[Dict[str, str]]:
        """从 DB 取最近 N 条历史，构建 OpenAI 格式 messages 列表"""
        history = (
            self.db.query(OpenClawMessage)
            .filter(OpenClawMessage.conversation_id == conversation_id)
            .order_by(OpenClawMessage.created_at.asc())
            .all()
        )
        recent = history[-limit:] if len(history) > limit else history
        return [{"role": m.role, "content": m.content} for m in recent]

    # ── 图片识别（Vision） ─────────────────────────────────

    async def _describe_image(self, image_base64: str, image_type: str, user_text: str) -> Optional[str]:
        """用 vision 模型识别图片内容，返回文字描述"""
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.usage_tracker import set_caller
            set_caller("openclaw.describe_image")
            compressed = self._compress_image_base64(image_base64, image_type)
            messages = [
                {"role": "system", "content": "你是图片识别助手。请详细描述图片中的内容。如果是食物，请列出每种食物的名称和大概份量。"},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text or "请描述这张图片"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{compressed}",
                        "detail": "high",
                    }},
                ]},
            ]
            provider = get_llm_provider()
            result = await provider.chat(messages=messages)
            if result:
                desc = result if isinstance(result, str) else str(result)
                logger.info(f"图片识别结果: {desc[:100]}...")
                return desc
        except Exception as e:
            logger.warning(f"图片识别失败: {e}")
        return None

    # ── 图片压缩 ──────────────────────────────────────────

    @staticmethod
    @staticmethod
    def _compress_image_base64(base64_data: str, image_type: str = "jpeg", max_size: int = 1024, quality: int = 75) -> str:
        from app.services.chat_utils import compress_image_base64
        return compress_image_base64(base64_data, image_type, max_size, quality)

    # ── Gateway 流式调用 ──────────────────────────────────

    async def _call_gateway_stream(
        self, messages: List[Dict], session_key: str
    ) -> AsyncGenerator[str, None]:
        """流式调用 OpenClaw Gateway /v1/chat/completions"""
        gateway_url = settings.openclaw_gateway_url.rstrip("/")
        if not gateway_url:
            raise ValueError("OPENCLAW_GATEWAY_URL 未配置")

        url = f"{gateway_url}/v1/chat/completions"
        headers = {}
        if settings.openclaw_api_key:
            headers["Authorization"] = f"Bearer {settings.openclaw_api_key}"

        # Gateway 要求 model 格式 "openclaw" 或 "openclaw/<agentId>"
        # env 可能写成 "openclaw:main"（冒号分隔），这里兼容转换
        raw_model = settings.openclaw_model or "openclaw"
        model = raw_model.replace(":", "/") if ":" in raw_model else raw_model
        if not model.startswith("openclaw"):
            model = "openclaw"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "user": session_key,
        }

        # 多模型分析场景下首次响应可能需要较长时间（Gateway 需先调多个 LLM）
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(f"OpenClaw Gateway error {resp.status_code}: {body[:500]}")
                    raise RuntimeError(f"Gateway returned {resp.status_code}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    # ── 技能管理命令 ────────────────────────────────────────

    def _try_handle_skill_command(self, message: str, is_admin: bool) -> Optional[str]:
        """检测并处理技能管理命令，返回响应文本或 None"""
        if not is_admin:
            return None

        text = message.strip()

        # 1. 检测 SKILL.md 内容安装（frontmatter 格式）
        if text.startswith("---") and "\nname:" in text:
            return self._install_skill_from_content(text)

        # 2. "安装技能" + JSON 或文本描述（支持前缀文字，如"基于...安装技能"）
        m = re.match(r'^.*?安装技能[：:\s]*(.+)', text, re.DOTALL)
        if m:
            body = m.group(1).strip()
            # 尝试解析为 JSON
            try:
                skill_data = json.loads(body)
                return self._install_skill_from_json(skill_data)
            except (json.JSONDecodeError, ValueError):
                pass
            # 如果是 frontmatter 格式
            if body.startswith("---") and "\nname:" in body:
                return self._install_skill_from_content(body)
            return f"无法解析技能内容。请使用以下格式之一：\n\n**1. SKILL.md 格式**（推荐）：\n```\n---\nname: my-skill\ndescription: 技能描述\nversion: 1.0.0\n---\n\n技能指令内容...\n```\n\n**2. JSON 格式**：\n```json\n{{\"name\": \"my-skill\", \"description\": \"...\", \"skill_md_content\": \"...\"}}\n```"

        # 3. 列出已安装技能
        if re.match(r'^(列出|查看|显示)(已安装|所有)?(技能|skills?)', text, re.IGNORECASE):
            return self._list_skills_response()

        # 4. ClawHub 搜索
        m = re.match(r'^(搜索|search)\s*(技能|skills?)?\s*(.+)', text, re.IGNORECASE)
        if m:
            return self._clawhub_search_response(m.group(3).strip())

        # 5. ClawHub 安装 (slug 含斜杠)
        m = re.match(r'^(从\s*clawhub\s*)?(安装|install)\s*(技能|skills?)?\s*(.+)', text, re.IGNORECASE)
        if m:
            slug = m.group(4).strip()
            if "/" in slug:
                return self._clawhub_install_response(slug)

        # 6. 删除技能
        m = re.match(r'^(删除|卸载|remove|uninstall)\s*(技能|skills?)?\s*(.+)', text, re.IGNORECASE)
        if m:
            return self._delete_skill_response(m.group(3).strip())

        # 7. 启用/禁用技能
        m = re.match(r'^(启用|enable)\s*(技能|skills?)?\s*(.+)', text, re.IGNORECASE)
        if m:
            return self._toggle_skill_response(m.group(3).strip(), True)
        m = re.match(r'^(禁用|disable)\s*(技能|skills?)?\s*(.+)', text, re.IGNORECASE)
        if m:
            return self._toggle_skill_response(m.group(3).strip(), False)

        # 8. 重启 Gateway
        if re.match(r'^(重启|restart)\s*(gateway|网关)', text, re.IGNORECASE):
            return self._restart_gateway_response()

        # 9. Gateway 状态
        if re.match(r'^(gateway|网关)\s*(状态|status)', text, re.IGNORECASE):
            return self._gateway_status_response()

        # 10. Hub 分类
        if re.match(r'^(Hub|技能市场|技能商店)\s*(分类|领域|domains?)', text, re.IGNORECASE):
            return self._hub_domains_response()

        # 11. Hub 搜索
        m = re.match(r'^(Hub|技能市场)\s*(搜索|search)\s+(.+)', text, re.IGNORECASE)
        if m:
            return self._hub_search_response(m.group(3).strip())

        # 12. Hub 安装
        m = re.match(r'^(Hub|技能市场)\s*(安装|install)\s+(\S+)\s+(\S+)', text, re.IGNORECASE)
        if m:
            return self._hub_install_response(m.group(3).strip(), m.group(4).strip())

        # 13. Hub 卸载
        m = re.match(r'^(Hub|技能市场)\s*(卸载|uninstall)\s+(\S+)', text, re.IGNORECASE)
        if m:
            return self._hub_uninstall_response(m.group(3).strip())

        # 14. 兜底：消息中包含技能 JSON 定义（含 name + description 字段）
        json_match = re.search(r'\{[^{}]*"name"\s*:\s*"[^"]+"[^{}]*"description"\s*:\s*"[^"]+".+?\}', text, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{[^{}]*"description"\s*:\s*"[^"]+"[^{}]*"name"\s*:\s*"[^"]+".+?\}', text, re.DOTALL)
        if json_match:
            try:
                skill_data = json.loads(json_match.group())
                if 'name' in skill_data and 'description' in skill_data:
                    return self._install_skill_from_json(skill_data)
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    def _install_skill_from_content(self, content: str) -> str:
        """从 SKILL.md 内容安装技能"""
        try:
            info = openclaw_skills_service._parse_frontmatter(content)
            name = info.get("name", "").strip()
            if not name:
                return "安装失败：SKILL.md 缺少 `name` 字段。请确保 frontmatter 中包含 `name: your-skill-name`。"
            env = {}
            if "HEALTH_API_URL" in content:
                env["HEALTH_API_URL"] = settings.health_api_base_url
            if "HEALTH_API_TOKEN" in content:
                env["HEALTH_API_TOKEN"] = "<需要在 Skills 页面配置 API Key>"
            result = openclaw_skills_service.create_or_update_skill(
                name=name, skill_md_content=content, enabled=True, env=env if env else None,
            )
            desc = info.get("description", "")
            version = info.get("version", "")
            lines = [f"技能 **{name}** 安装成功！"]
            if desc:
                lines.append(f"- 描述: {desc}")
            if version:
                lines.append(f"- 版本: {version}")
            lines.append(f"- 状态: {'已启用' if result.get('enabled') else '已禁用'}")
            lines.append('\n⚠️ 请**重启 Gateway** 使新技能生效（发送「重启 Gateway」）。')
            return "\n".join(lines)
        except Exception as e:
            return f"安装失败: {e}"

    def _install_skill_from_json(self, data: dict) -> str:
        """从 JSON 数据安装技能"""
        name = data.get("name", "").strip()
        if not name:
            return "安装失败：缺少 `name` 字段。"
        desc = data.get("description", "")
        skill_md = data.get("skill_md_content", "")
        if not skill_md:
            # 用 JSON 自动生成一个简单的 SKILL.md
            skill_md = f"---\nname: {name}\ndescription: {desc}\nversion: 1.0.0\n---\n\n{json.dumps(data, indent=2, ensure_ascii=False)}"
        env = data.get("env") or {}
        api_key = data.get("api_key")
        try:
            result = openclaw_skills_service.create_or_update_skill(
                name=name, skill_md_content=skill_md, enabled=True, env=env if env else None, api_key=api_key,
            )
            lines = [f"技能 **{name}** 安装成功！"]
            if desc:
                lines.append(f"- 描述: {desc}")
            lines.append(f"- 状态: {'已启用' if result.get('enabled') else '已禁用'}")
            lines.append('\n⚠️ 请**重启 Gateway** 使新技能生效（发送「重启 Gateway」）。')
            return "\n".join(lines)
        except Exception as e:
            return f"安装失败: {e}"

    def _list_skills_response(self) -> str:
        try:
            skills = openclaw_skills_service.list_skills()
            if not skills:
                return "当前没有已安装的技能。"
            lines = [f"已安装 **{len(skills)}** 个技能：\n"]
            for s in skills:
                status = "✅ 启用" if s["enabled"] else "⏸️ 禁用"
                lines.append(f"- **{s['name']}** {status}")
                if s.get("description"):
                    lines.append(f"  {s['description']}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取技能列表失败: {e}"

    def _clawhub_search_response(self, query: str) -> str:
        try:
            result = openclaw_skills_service.clawhub_search(query)
            return f"**ClawHub 搜索「{query}」结果：**\n\n```\n{result}\n```\n\n如需安装，发送：`安装 <slug>`（例如：`安装 author/skill-name`）"
        except Exception as e:
            return f"搜索失败: {e}"

    def _clawhub_install_response(self, slug: str) -> str:
        try:
            result = openclaw_skills_service.clawhub_install(slug)
            return f"**从 ClawHub 安装 `{slug}`：**\n\n```\n{result}\n```\n\n⚠️ 请**重启 Gateway** 使新技能生效（发送「重启 Gateway」）。"
        except Exception as e:
            return f"安装失败: {e}"

    def _delete_skill_response(self, name: str) -> str:
        try:
            ok = openclaw_skills_service.delete_skill(name)
            if ok:
                return f"技能 **{name}** 已删除。\n\n⚠️ 请**重启 Gateway** 使变更生效。"
            return f"技能 **{name}** 不存在。"
        except Exception as e:
            return f"删除失败: {e}"

    def _toggle_skill_response(self, name: str, enabled: bool) -> str:
        try:
            ok = openclaw_skills_service.toggle_skill(name, enabled)
            if ok:
                status = "启用" if enabled else "禁用"
                return f"技能 **{name}** 已{status}。\n\n⚠️ 请**重启 Gateway** 使变更生效。"
            return f"技能 **{name}** 配置不存在。"
        except Exception as e:
            return f"操作失败: {e}"

    def _restart_gateway_response(self) -> str:
        try:
            result = openclaw_skills_service.restart_gateway()
            return f"Gateway 重启完成：{result}"
        except Exception as e:
            return f"重启失败: {e}"

    def _gateway_status_response(self) -> str:
        try:
            status = openclaw_skills_service.get_gateway_status()
            return f"**Gateway 状态**\n- 运行: {status['status']}\n- 启动时间: {status['uptime']}"
        except Exception as e:
            return f"获取状态失败: {e}"

    # ── Skills Hub 命令 ──────────────────────────────────

    def _hub_domains_response(self) -> str:
        """列出 Hub 技能领域"""
        try:
            domains = skills_hub_client.list_domains()
            if not domains:
                return "Hub 暂无可用领域，请检查网络连接"
            lines = ["**技能市场 - 领域分类**\n"]
            for d in domains:
                lines.append(f"- **{d['name']}**: {d.get('description', '')} ({d.get('skill_count', 0)} 个技能)")
            lines.append("\n使用 `Hub 搜索 <关键词>` 搜索技能")
            return "\n".join(lines)
        except Exception as e:
            return f"获取 Hub 领域失败: {e}"

    def _hub_search_response(self, keyword: str) -> str:
        """搜索 Hub 技能"""
        try:
            results = skills_hub_client.search_skills(keyword)
            if not results:
                return f"未找到与 \"{keyword}\" 相关的技能"
            lines = [f"**搜索结果: \"{keyword}\"** ({len(results)} 个)\n"]
            for r in results[:10]:
                status = "✅ 已安装" if r.get("installed") else "📦 可安装"
                lines.append(f"- {status} **{r['name']}** ({r['domain']}): {r.get('description', '')}")
            lines.append(f"\n使用 `Hub 安装 <领域> <技能名>` 安装技能")
            return "\n".join(lines)
        except Exception as e:
            return f"搜索失败: {e}"

    def _hub_install_response(self, domain: str, skill_name: str) -> str:
        """从 Hub 安装技能"""
        try:
            result = skills_hub_client.install_skill(domain, skill_name)
            if result["success"]:
                return f"✅ 成功安装技能 **{skill_name}** (领域: {domain})\n\n需要重启 Gateway 生效。发送 `重启 Gateway`"
            return f"❌ 安装失败: {result.get('error', '未知错误')}"
        except Exception as e:
            return f"安装失败: {e}"

    def _hub_uninstall_response(self, skill_name: str) -> str:
        """卸载 Hub 技能"""
        try:
            result = skills_hub_client.uninstall_skill(skill_name)
            if result["success"]:
                return f"✅ 已卸载技能 **{skill_name}**"
            return f"❌ 卸载失败: {result.get('error', '未知错误')}"
        except Exception as e:
            return f"卸载失败: {e}"

    # ── 食物图片自动保存 ──────────────────────────────────

    def _try_auto_save_diet(self, user_id: int, user_msg: str, ai_reply: str) -> Optional[dict]:
        """如果用户发了食物图片且 AI 回复包含营养信息，自动保存饮食记录（best-effort）"""
        import re as _re
        from datetime import date as _date, datetime as _dt, timedelta as _td

        # 检测 AI 回复中是否包含食物/营养关键词
        food_keywords = ["kcal", "热量", "蛋白质", "碳水", "千卡", "大卡", "卡路里"]
        if not any(kw in ai_reply for kw in food_keywords):
            return None

        try:
            from app.models.daily_health import DietRecord

            # 推断餐次
            hour = _dt.now().hour
            if 5 <= hour < 10:
                meal_type = "breakfast"
            elif 10 <= hour < 14:
                meal_type = "lunch"
            elif 14 <= hour < 17:
                meal_type = "snack"
            elif 17 <= hour < 21:
                meal_type = "dinner"
            else:
                meal_type = "snack"

            today = _date.today()

            # 检查最近 90 秒是否已有同类记录（避免重复）
            existing = self.db.query(DietRecord).filter(
                DietRecord.user_id == user_id,
                DietRecord.record_date == today,
                DietRecord.meal_type == meal_type,
                DietRecord.created_at >= _dt.now() - _td(seconds=90),
            ).first()
            if existing:
                return None

            # 提取食物描述（取 AI 回复前 200 字符作为摘要）
            food_items = ai_reply[:200].replace("\n", " ").strip()

            # 提取热量
            calories = None
            cal_match = _re.search(r"[=≈约共合计总]?\s*([\d,.]+)\s*(?:kcal|千卡|大卡|cal|卡路里)", ai_reply, _re.IGNORECASE)
            if cal_match:
                try:
                    val = float(cal_match.group(1).replace(",", ""))
                    if val <= 3000:
                        calories = val
                except ValueError:
                    pass

            record = DietRecord(
                user_id=user_id,
                record_date=today,
                meal_type=meal_type,
                food_items=food_items,
                calories=calories,
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)

            logger.info(f"食物图片自动保存: user={user_id}, meal={meal_type}, cal={calories}")
            return {
                "id": record.id,
                "meal_type": meal_type,
                "food_items": food_items[:80],
                "calories": calories,
            }
        except Exception as e:
            logger.warning(f"食物图片自动保存失败: {e}")
            return None

    # ── 提醒检测 ──────────────────────────────────────────

    async def _try_create_reminder(self, user_id: int, user_msg: str, ai_reply: str):
        """检测 OpenClaw 回复中的提醒意图，创建真实提醒"""
        import re as _re
        from app.utils.timezone import get_china_now

        # 快速判断：用户消息或AI回复中是否包含提醒相关关键词
        reminder_keywords = ["提醒", "闹钟", "别忘", "记得", "到时候"]
        confirm_keywords = ["已设置", "已安排", "会提醒", "好的.*提醒", "设好了"]

        user_has_intent = any(kw in user_msg for kw in reminder_keywords)
        ai_confirmed = any(_re.search(kw, ai_reply) for kw in confirm_keywords)

        if not (user_has_intent and ai_confirmed):
            return

        # 用 LLM 提取结构化提醒信息
        now = get_china_now()
        extract_prompt = f"""从以下对话中提取提醒信息，返回 JSON 格式。如果不是设置提醒的对话，返回 {{"is_reminder": false}}

用户: {user_msg}
AI: {ai_reply}
当前时间: {now.strftime('%Y-%m-%d %H:%M')} (北京时间)

请返回 JSON（不要 markdown 代码块）：
{{"is_reminder": true/false, "title": "简短标题", "message": "详细内容", "remind_at": "YYYY-MM-DDTHH:MM:00+08:00", "priority": "low/normal/high/urgent"}}"""

        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.usage_tracker import set_caller
            set_caller("openclaw.reminder_extract", user_id=user_id)
            llm = get_llm_provider()
            result_text = await llm.chat(
                [{"role": "user", "content": extract_prompt}],
                temperature=0,
                max_tokens=300,
            )

            # 提取 JSON
            json_match = _re.search(r'\{[^{}]+\}', result_text)
            if not json_match:
                return

            import json as _json
            data = _json.loads(json_match.group())

            if not data.get("is_reminder"):
                return

            # 创建提醒
            from app.models.smart_reminder import SmartReminder
            from dateutil.parser import parse as parse_dt

            remind_at = parse_dt(data["remind_at"])
            if remind_at.tzinfo is None:
                from datetime import timezone, timedelta
                remind_at = remind_at.replace(tzinfo=timezone(timedelta(hours=8)))

            if remind_at < now:
                logger.info(f"OpenClaw 提醒时间已过，跳过: {data}")
                return

            reminder = SmartReminder(
                user_id=user_id,
                title=data.get("title", "提醒"),
                message=data.get("message", user_msg),
                remind_at=remind_at,
                priority=data.get("priority", "normal"),
                source="openclaw",
                status="pending",
            )
            self.db.add(reminder)
            self.db.commit()
            logger.info(f"OpenClaw 自动创建提醒: user={user_id}, title='{reminder.title}', at={remind_at}")

        except Exception as e:
            logger.warning(f"OpenClaw 提醒提取失败: {e}")

    # ── 主流程 ────────────────────────────────────────────

    async def send_message_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        is_admin: bool = False,
        image_base64: Optional[str] = None,
        image_type: str = "jpeg",
        user_auth_token: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """流式发送消息到 OpenClaw Gateway 并实时转发"""
        import time
        _stream_start = time.time()

        # 1. 获取或创建会话
        conv = self.get_or_create_conversation(user_id, conversation_id, title=message)

        # 2. 保存用户消息
        saved_image_url = None
        if image_base64:
            from app.services.agent_executor import AgentExecutor
            saved_image_url = AgentExecutor._upload_chat_image(image_base64, image_type)
        self.save_message(conv.id, "user", message, image_url=saved_image_url)

        # 3. 检查是否为技能管理命令（管理员专属）
        skill_response = self._try_handle_skill_command(message, is_admin)
        if skill_response is not None:
            yield {"event": "token", "data": {"content": skill_response}}
            ai_msg = self.save_message(conv.id, "assistant", skill_response)
            conv.updated_at = datetime.now(UTC)
            self.db.commit()
            yield {"event": "done", "data": {"conversation_id": conv.id, "message_id": ai_msg.id}}
            return

        # 4. 构建 messages 列表
        messages = self.build_messages(conv.id, limit=20)

        # 4.1 注入健康上下文 + 对话记忆 + 时段感知
        try:
            from app.services.health_context_lite_service import (
                build_lite_health_context, OPENCLAW_HEALTH_SYSTEM_RULES, _get_time_period,
            )
            from app.services.conversation_memory_service import get_relevant_memories

            health_ctx = build_lite_health_context(self.db, user_id)
            if health_ctx:
                system_content = OPENCLAW_HEALTH_SYSTEM_RULES + "\n" + health_ctx

                # 4.1.1 注入跨会话记忆（用户偏好、医嘱、过敏等）
                memories = get_relevant_memories(self.db, user_id, limit=5)
                if memories:
                    system_content += "\n\n" + memories

                # 4.1.2 时段感知指令
                _, period = _get_time_period()
                period_hints = {
                    "清晨": "[时段: 清晨] 重点关注昨晚睡眠恢复、今日能量状态、晨起建议。语气温和鼓励。",
                    "上午": "[时段: 上午] 适合规划今日目标和运动安排。如果恢复状态好，建议上午运动。",
                    "中午": "[时段: 午间] 关注午餐营养和上午活动量。提醒饮水。",
                    "下午": "[时段: 下午] 检查今日目标进度。适合补充活动或完成打卡。",
                    "晚上": "[时段: 晚上] 回顾全天数据：步数、饮食、饮水是否达标。给出晚间恢复建议。",
                    "深夜": "[时段: 深夜] 简短回复即可。建议用户休息，关注睡眠准备。",
                }
                hint = period_hints.get(period, "")
                if hint:
                    system_content += "\n\n" + hint

                # 4.1.3 新对话首条消息：主动健康评估
                is_new_conversation = len([m for m in messages if m["role"] == "assistant"]) == 0
                if is_new_conversation:
                    system_content += (
                        "\n\n[新对话指令] 这是新对话的第一条消息。在回答用户问题的同时，请：\n"
                        "1. 快速扫描健康档案，找出最值得关注的 1-2 个发现（趋势变化、异常指标、恢复状态）\n"
                        "2. 检查待办完成情况（饮水、打卡、补剂），提醒未完成项\n"
                        "3. 如果恢复就绪度数据可用，给出今日运动/休息建议\n"
                        "4. 所有提醒自然融入回复，像一个了解你的私人健康顾问在对话，不要机械罗列\n"
                        "5. 如果用户问了具体问题，优先回答问题，健康提醒作为补充\n"
                        "6. 如果需要更详细的数据来回答，主动调用对应的 Skill 获取"
                    )

                # 4.1.4 注入用户专属 API 凭证（多租户：每个用户使用自己的 token）
                if user_auth_token:
                    system_content += (
                        "\n\n[Skill 环境变量]\n"
                        f"HEALTH_API_TOKEN={user_auth_token}\n"
                        f"HEALTH_API_URL={settings.health_api_base_url or settings.site_base_url + '/api/v1'}\n"
                        "在执行任何 Skill 的 curl 命令时，必须使用上面的 HEALTH_API_TOKEN 和 HEALTH_API_URL。"
                    )

                messages.insert(0, {
                    "role": "system",
                    "content": system_content,
                })
        except Exception as e:
            logger.warning(f"健康上下文注入失败(不影响对话): {e}")

        # 4.5 如果有图片，先用 vision 模型识别内容，再把描述注入文本
        #     OpenClaw Gateway 不支持多模态 image_url，只能传纯文本
        if image_base64 and messages:
            last_msg = messages[-1]
            if last_msg.get("role") == "user":
                image_desc = await self._describe_image(image_base64, image_type, last_msg["content"])
                if image_desc:
                    messages[-1] = {
                        "role": "user",
                        "content": f"{last_msg['content']}\n\n[图片内容识别结果]\n{image_desc}",
                    }

        # 5. 流式调用 Gateway
        full_reply = ""
        try:
            async for token in self._call_gateway_stream(messages, conv.session_key):
                full_reply += token
                yield {"event": "token", "data": {"content": token}}
        except Exception as e:
            logger.error(f"OpenClaw Gateway 调用失败: {type(e).__name__}: {e}")
            full_reply = "抱歉，OpenClaw 暂时无法响应，请稍后再试。"
            yield {"event": "token", "data": {"content": full_reply}}

        # 6. 保存 AI 回复
        ai_msg = self.save_message(conv.id, "assistant", full_reply)

        # 6.5 检测提醒意图并创建真实提醒
        try:
            await self._try_create_reminder(user_id, message, full_reply)
        except Exception as e:
            logger.warning(f"OpenClaw 提醒检测失败: {e}")

        # 6.6 食物图片自动保存
        diet_auto_saved = None
        if image_base64:
            try:
                diet_auto_saved = self._try_auto_save_diet(user_id, message, full_reply)
            except Exception as e:
                logger.warning(f"食物图片自动保存异常: {e}")

        # 6.7 提取对话记忆（用户偏好、医嘱、过敏等持久性事实）
        try:
            from app.services.conversation_memory_service import extract_memories
            extract_memories(message, full_reply, user_id, conv.id, self.db)
        except Exception as e:
            logger.debug(f"记忆提取跳过: {e}")

        # 7. 更新会话时间
        conv.updated_at = datetime.now(UTC)
        self.db.commit()

        # 8. 记录隐式反馈（skill 调用、成功/失败、响应时间）
        try:
            from app.services.feedback_service import feedback_service
            elapsed_ms = int((time.time() - _stream_start) * 1000)
            feedback_service.record_implicit(
                db=self.db,
                user_id=user_id,
                conversation_type="openclaw",
                conversation_id=conv.id,
                message_id=ai_msg.id,
                success=bool(full_reply and not full_reply.startswith("抱歉")),
                response_time_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"记录隐式反馈失败: {e}")

        # 9. done 事件
        done_data = {
            "conversation_id": conv.id,
            "message_id": ai_msg.id,
        }
        if diet_auto_saved:
            done_data["diet_auto_saved"] = diet_auto_saved
        yield {
            "event": "done",
            "data": done_data,
        }
