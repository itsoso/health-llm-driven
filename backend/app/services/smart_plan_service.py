import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.models.checkin import CheckinTemplate
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)


class SmartPlanService:
    def __init__(self, db: Session):
        self.db = db
        self.chat_service = ChatService(db)

    def _get_week_start(self, target: str) -> date:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        if target == "next":
            monday += timedelta(weeks=1)
        return monday

    def _get_last_week_feedback(self, user_id: int, current_week_start: date) -> str:
        last_week = current_week_start - timedelta(weeks=1)
        last_plan = self.db.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == user_id,
            WeeklyPlan.week_start == last_week
        ).first()

        if not last_plan:
            return ""

        items = self.db.query(PlanItem).filter(PlanItem.plan_id == last_plan.id).all()
        completed = [i for i in items if i.is_completed]
        not_completed = [i for i in items if not i.is_completed]

        parts = [f"\n上周计划完成率: {last_plan.completion_rate:.0f}%"]
        if completed:
            parts.append(f"完成的项目: {', '.join(i.title for i in completed[:10])}")
        if not_completed:
            parts.append(f"未完成的项目: {', '.join(i.title for i in not_completed[:10])}")
        if last_plan.user_feedback:
            parts.append(f"用户对上周计划评分: {last_plan.user_feedback}/5")

        return "\n".join(parts)

    def _get_checkin_templates(self, user_id: int) -> List[Dict]:
        templates = self.db.query(CheckinTemplate).filter(
            CheckinTemplate.user_id == user_id,
            CheckinTemplate.is_active == True
        ).all()
        return [
            {"id": t.id, "name": t.name, "category": t.category, "unit": t.unit, "default_target": t.default_target}
            for t in templates
        ]

    def _match_template(self, title: str, templates: List[Dict]) -> Optional[int]:
        title_lower = title.lower()
        for t in templates:
            name_lower = t["name"].lower()
            if name_lower in title_lower or title_lower in name_lower:
                return t["id"]
        keywords_map = {
            "跑步": ["跑", "慢跑", "快跑"],
            "深蹲": ["深蹲", "蹲"],
            "俯卧撑": ["俯卧撑", "push"],
            "拉伸": ["拉伸", "stretch", "放松"],
            "平板支撑": ["平板", "plank"],
            "跳绳": ["跳绳", "rope"],
            "喝水": ["喝水", "饮水", "补水"],
            "冥想": ["冥想", "meditation", "正念"],
            "称体重": ["体重", "称重"],
        }
        for t in templates:
            kws = keywords_map.get(t["name"], [])
            for kw in kws:
                if kw in title_lower:
                    return t["id"]
        return None

    async def generate_plan(self, user_id: int, target_week: str = "current") -> WeeklyPlan:
        week_start = self._get_week_start(target_week)

        # 归档已有计划
        existing = self.db.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == user_id,
            WeeklyPlan.week_start == week_start,
            WeeklyPlan.status.in_(["active", "draft"])
        ).first()
        if existing:
            existing.status = "archived"
            self.db.flush()

        # 收集上下文
        health_context = await self.chat_service._build_health_context(user_id)
        feedback_context = self._get_last_week_feedback(user_id, week_start)
        templates = self._get_checkin_templates(user_id)
        templates_str = "\n".join(
            f"- {t['name']}（{t['category']}，单位:{t['unit']}，目标:{t['default_target']}）"
            for t in templates
        )

        week_end = week_start + timedelta(days=6)
        prompt = f"""你是一位专业的健康教练。请根据用户的健康数据，为 {week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')} 这一周生成个性化健康计划。

用户健康数据：
{health_context}
{feedback_context}

用户已有的打卡模板（生成运动/习惯项时请尽量匹配这些名称）：
{templates_str if templates_str else "（暂无打卡模板）"}

请严格按照以下 JSON 格式输出，不要输出其他内容：
```json
{{
  "focus_areas": ["重点1", "重点2", "重点3"],
  "weekly_summary": "一段话总结本周计划的思路和重点...",
  "days": {{
    "1": [
      {{"category": "exercise", "title": "跑步30分钟", "description": "有氧训练，心率控制在130-145bpm", "target_value": 30, "target_unit": "分钟"}},
      {{"category": "diet", "title": "控制午餐碳水", "description": "建议以蛋白质为主...", "target_value": null, "target_unit": null}},
      {{"category": "rest", "title": "23:00前入睡", "description": "保证7-8小时睡眠", "target_value": null, "target_unit": null}}
    ],
    "2": [...],
    "3": [...],
    "4": [...],
    "5": [...],
    "6": [...],
    "7": [...]
  }}
}}
```

要求：
1. 每天 3-5 个行动项
2. category 只能是: exercise/diet/rest/habit/other
3. 运动类项目请尽量使用用户已有打卡模板的名称
4. 根据用户实际数据调整强度，循序渐进
5. 如果有上周未完成的项目，适当降低难度或调整安排"""

        plan_json = await self._call_llm(prompt)
        if not plan_json:
            raise ValueError("AI 生成计划失败，请稍后重试")

        plan = WeeklyPlan(
            user_id=user_id,
            week_start=week_start,
            status="active",
            focus_areas=plan_json.get("focus_areas", []),
            weekly_summary=plan_json.get("weekly_summary", ""),
            ai_model=settings.openclaw_model,
        )
        self.db.add(plan)
        self.db.flush()

        days_data = plan_json.get("days", {})
        for day_str, items in days_data.items():
            try:
                day_num = int(day_str)
            except ValueError:
                continue
            if not isinstance(items, list):
                continue
            for idx, item_data in enumerate(items):
                if not isinstance(item_data, dict):
                    continue
                template_id = self._match_template(item_data.get("title", ""), templates)
                plan_item = PlanItem(
                    plan_id=plan.id,
                    day_of_week=day_num,
                    category=item_data.get("category", "other"),
                    title=item_data.get("title", ""),
                    description=item_data.get("description", ""),
                    target_value=item_data.get("target_value"),
                    target_unit=item_data.get("target_unit"),
                    checkin_template_id=template_id,
                    sort_order=idx,
                )
                self.db.add(plan_item)

        self.db.commit()
        self.db.refresh(plan)
        return plan

    async def _call_llm(self, prompt: str) -> Optional[Dict]:
        if not settings.openclaw_api_key:
            logger.error("OpenClaw API key not configured")
            return None

        messages = [
            {"role": "system", "content": "你是一位专业的健康教练，擅长制定个性化健康计划。请严格按 JSON 格式输出。"},
            {"role": "user", "content": prompt}
        ]

        content = ""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{settings.openclaw_base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.openclaw_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": settings.openclaw_model,
                            "messages": messages,
                            "temperature": 0.7,
                        }
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]

                    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group(1))
                    return json.loads(content)

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"LLM 响应解析失败 (attempt {attempt+1}): {e}")
                if attempt == 0:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "你的输出格式不正确，请严格按照 JSON 格式重新输出，不要包含任何其他文字。"})
                continue
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                return None

        return None

    def update_completion_rate(self, plan_id: int):
        total = self.db.query(func.count(PlanItem.id)).filter(PlanItem.plan_id == plan_id).scalar()
        completed = self.db.query(func.count(PlanItem.id)).filter(
            PlanItem.plan_id == plan_id,
            PlanItem.is_completed == True
        ).scalar()
        rate = (completed / total * 100) if total > 0 else 0.0

        plan = self.db.query(WeeklyPlan).filter(WeeklyPlan.id == plan_id).first()
        if plan:
            plan.completion_rate = round(rate, 1)
            if rate >= 100:
                plan.status = "completed"
            self.db.commit()
