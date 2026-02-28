import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

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

    def _init_debug_info(self) -> Dict[str, Any]:
        return {
            "steps": [],
            "data_sources": {},
            "reasoning": [],
            "performance": {},
        }

    def _add_step(self, debug: Optional[Dict], name: str, start: float = None):
        if not debug:
            return
        step_num = len(debug["steps"]) + 1
        debug["steps"].append(f"{step_num}. {name}")
        if start:
            elapsed = (time.time() - start) * 1000
            debug["performance"][name] = f"{elapsed:.0f}ms"

    def _add_reasoning(self, debug: Optional[Dict], msg: str, level: str = "info"):
        if not debug:
            return
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌",
                 "goal": "🎯", "data": "📊", "heart": "💓", "workout": "🏃", "knowledge": "📚"}
        debug["reasoning"].append(f"{icons.get(level, '•')} {msg}")

    def _add_data(self, debug: Optional[Dict], key: str, value: Any):
        if debug:
            debug["data_sources"][key] = value

    def _get_week_start(self, target: str) -> date:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        if target == "next":
            monday += timedelta(weeks=1)
        return monday

    def _get_recent_plans_feedback(self, user_id: int, current_week_start: date) -> str:
        """获取最近 2-4 周的计划完成分析，识别行为模式"""
        parts = []
        for weeks_ago in range(1, 5):
            week_start = current_week_start - timedelta(weeks=weeks_ago)
            plan = self.db.query(WeeklyPlan).filter(
                WeeklyPlan.user_id == user_id,
                WeeklyPlan.week_start == week_start
            ).first()
            if not plan:
                continue

            items = self.db.query(PlanItem).filter(PlanItem.plan_id == plan.id).all()
            if not items:
                continue

            # 按类别统计完成情况
            from collections import defaultdict
            cat_stats = defaultdict(lambda: {"total": 0, "done": 0, "items": []})
            for item in items:
                cat = cat_stats[item.category]
                cat["total"] += 1
                if item.is_completed:
                    cat["done"] += 1
                    cat["items"].append(f"✅{item.title}")
                else:
                    cat["items"].append(f"❌{item.title}")

            week_label = f"{weeks_ago}周前" if weeks_ago > 1 else "上周"
            parts.append(f"\n【{week_label}计划 {week_start}】完成率 {plan.completion_rate:.0f}%")
            for cat_name, stat in cat_stats.items():
                rate = (stat["done"] / stat["total"] * 100) if stat["total"] > 0 else 0
                parts.append(f"  {cat_name}: {stat['done']}/{stat['total']} ({rate:.0f}%) — {', '.join(stat['items'][:5])}")
            if plan.user_feedback:
                parts.append(f"  用户评分: {plan.user_feedback}/5")

        return "\n".join(parts)

    def _get_active_goals_context(self, user_id: int) -> str:
        """获取活跃的阶段性目标，让周计划与目标对齐"""
        from app.models.health_goal_plan import PeriodGoal
        goals = self.db.query(PeriodGoal).filter(
            PeriodGoal.user_id == user_id,
            PeriodGoal.status == "active"
        ).all()
        if not goals:
            return ""
        parts = []
        for g in goals:
            label = "月度目标" if g.period_type == "monthly" else "年度目标"
            parts.append(f"\n【{label} {g.period_start}~{g.period_end}】")
            if g.focus_areas:
                parts.append(f"  重点: {', '.join(g.focus_areas)}")
            for m in g.metrics:
                progress = ""
                if m.current_value is not None and m.target_value is not None:
                    progress = f" (进度: {m.current_value} → 目标 {m.target_value}{m.unit or ''})"
                parts.append(f"  {m.metric_name or m.metric_type}{progress}")
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

    async def generate_plan(self, user_id: int, target_week: str = "current", debug: bool = False) -> Dict[str, Any]:
        overall_start = time.time()
        debug_info = self._init_debug_info() if debug else None

        # Step 1: 计算目标周
        step_start = time.time()
        week_start = self._get_week_start(target_week)
        week_end = week_start + timedelta(days=6)
        self._add_step(debug_info, "计算目标周", step_start)
        self._add_reasoning(debug_info, f"目标周: {week_start} ~ {week_end} ({target_week})", "info")

        # Step 2: 删除已有计划（唯一约束 user_id + week_start）
        step_start = time.time()
        existing = self.db.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == user_id,
            WeeklyPlan.week_start == week_start,
        ).first()
        if existing:
            old_id = existing.id
            self.db.delete(existing)
            self.db.flush()
            self._add_reasoning(debug_info, f"已删除旧计划 ID={old_id}（重新生成）", "warning")
        else:
            self._add_reasoning(debug_info, "无已有计划，直接创建", "info")
        self._add_step(debug_info, "检查并清理已有计划", step_start)

        # Step 3: 获取健康上下文
        step_start = time.time()
        health_context = await self.chat_service._build_health_context(user_id)
        self._add_step(debug_info, "获取用户健康数据上下文", step_start)
        self._add_reasoning(debug_info, f"健康上下文长度: {len(health_context)} 字符", "data")
        self._add_data(debug_info, "health_context", health_context[:2000] + ("..." if len(health_context) > 2000 else ""))

        # Step 4: 获取历史计划执行分析
        step_start = time.time()
        feedback_context = self._get_recent_plans_feedback(user_id, week_start)
        self._add_step(debug_info, "分析历史计划执行", step_start)
        if feedback_context:
            self._add_reasoning(debug_info, f"获取到历史计划数据", "data")
            self._add_data(debug_info, "plan_history", feedback_context)
        else:
            self._add_reasoning(debug_info, "无历史计划数据", "info")

        # Step 5: 获取活跃目标
        step_start = time.time()
        goals_context = self._get_active_goals_context(user_id)
        self._add_step(debug_info, "获取阶段性目标", step_start)
        if goals_context:
            self._add_reasoning(debug_info, "有活跃目标，将指导计划方向", "goal")
            self._add_data(debug_info, "active_goals", goals_context)

        # Step 6: 获取打卡模板
        step_start = time.time()
        templates = self._get_checkin_templates(user_id)
        templates_str = "\n".join(
            f"- {t['name']}（{t['category']}，单位:{t['unit']}，目标:{t['default_target']}）"
            for t in templates
        )
        self._add_step(debug_info, "获取用户打卡模板", step_start)
        self._add_reasoning(debug_info, f"找到 {len(templates)} 个打卡模板", "data")
        self._add_data(debug_info, "checkin_templates", templates)

        # Step 7: 构建 Prompt
        step_start = time.time()
        prompt = f"""你是一位资深的运动医学和营养学专家。你需要先深入分析用户的健康数据，发现隐藏的规律和风险，然后基于这些洞察制定下周计划。

## 用户健康数据（请仔细分析趋势和异常）
{health_context}

## 历史计划执行情况（请分析行为模式：哪些容易坚持？哪些总是失败？为什么？）
{feedback_context if feedback_context else "（首次生成计划，无历史数据）"}

## 用户当前阶段性目标（周计划需要服务于这些目标）
{goals_context if goals_context else "（暂无设定目标）"}

## 用户打卡模板（运动/习惯项尽量匹配）
{templates_str if templates_str else "（暂无打卡模板）"}

## 你的任务

请为 {week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')} 生成周计划。

**在制定计划前，你必须先完成以下分析（体现在 insights 和 weekly_summary 中）：**

1. **数据洞察**：从健康数据中发现了什么？比如：
   - 睡眠质量趋势（深睡比例是否正常？REM够不够？）
   - 运动强度是否匹配目标（心率区间是否合理？配速变化？）
   - 饮食结构问题（蛋白质是否充足？热量缺口？营养比例？）
   - 压力与恢复的平衡（身体电量、压力水平的变化规律）
   - 体重/体脂变化与运动饮食的关联

2. **行为模式分析**（如果有历史数据）：
   - 哪类任务执行率高？哪类低？是什么原因？
   - 一周内哪几天执行力强/弱？是否跟工作日/休息日有关？
   - 重复失败的项目是否需要换种方式或降低门槛？

3. **风险预警**：
   - 是否有健康指标需要关注？（如血压偏高、体脂过高、睡眠不足）
   - 运动是否有受伤风险？（强度过大、缺乏恢复）
   - 是否存在过度训练/恢复不足的信号？

请严格按照以下 JSON 格式输出：
```json
{{
  "insights": [
    "从数据中发现的洞察1（引用具体数据）",
    "从数据中发现的洞察2",
    "从数据中发现的洞察3"
  ],
  "risks": [
    "需要注意的健康风险或行为风险"
  ],
  "focus_areas": ["本周重点1", "本周重点2", "本周重点3"],
  "weekly_summary": "基于以上分析，本周计划的核心策略是...（必须引用具体数据支撑决策）",
  "days": {{
    "1": [
      {{"category": "exercise", "title": "跑步30分钟", "description": "【依据】根据最近配速x'xx和心率xxxbpm，本次目标心率控制在xxx-xxxbpm，配速不低于x'xx", "target_value": 30, "target_unit": "分钟"}},
      {{"category": "diet", "title": "午餐高蛋白", "description": "【依据】近3天蛋白质摄入仅xxg，目标每餐30g+蛋白质", "target_value": null, "target_unit": null}}
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

## 关键要求
1. **每个计划项的 description 必须包含"【依据】"**，引用具体数据解释为什么安排这个任务、目标值怎么来的
2. 每天 3-5 个行动项，category 只能是: exercise/diet/rest/habit/other
3. insights 必须是从数据中挖掘的发现，不是泛泛的健康常识
4. 如果有阶段性目标，周计划要明确服务于目标进度
5. 运动安排要考虑恢复周期（不要连续高强度），饮食建议要具体到食物/营养素量
6. 基于历史执行模式，对低执行率类别降低门槛或换种形式"""
        self._add_step(debug_info, "构建 AI 分析 Prompt", step_start)
        self._add_reasoning(debug_info, f"Prompt 长度: {len(prompt)} 字符", "info")
        self._add_data(debug_info, "prompt_preview", prompt[:800] + "...")

        # Step 7: 调用 LLM
        step_start = time.time()
        plan_json, llm_debug = await self._call_llm(prompt, debug=debug)
        self._add_step(debug_info, "调用 LLM 生成计划", step_start)
        if llm_debug and debug_info:
            debug_info["data_sources"]["llm_info"] = llm_debug
        if not plan_json:
            self._add_reasoning(debug_info, "LLM 生成失败", "error")
            raise ValueError("AI 生成计划失败，请稍后重试")
        self._add_reasoning(debug_info, f"LLM 生成成功，模型: {settings.openclaw_model}", "success")
        self._add_reasoning(debug_info, f"focus_areas: {plan_json.get('focus_areas', [])}", "goal")
        insights = plan_json.get("insights", [])
        risks = plan_json.get("risks", [])
        if insights:
            self._add_reasoning(debug_info, f"AI 洞察 ({len(insights)} 条): {insights[0][:80]}...", "data")
        if risks:
            self._add_reasoning(debug_info, f"风险预警 ({len(risks)} 条): {risks[0][:80]}...", "warning")

        # Step 8: 保存计划到数据库
        step_start = time.time()
        plan = WeeklyPlan(
            user_id=user_id,
            week_start=week_start,
            status="active",
            focus_areas=plan_json.get("focus_areas", []),
            ai_insights=insights,
            ai_risks=risks,
            weekly_summary=plan_json.get("weekly_summary", ""),
            ai_model=settings.openclaw_model,
        )
        self.db.add(plan)
        self.db.flush()

        days_data = plan_json.get("days", {})
        total_items = 0
        matched_templates = 0
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
                if template_id:
                    matched_templates += 1
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
                total_items += 1

        self.db.commit()
        self.db.refresh(plan)
        self._add_step(debug_info, "保存计划到数据库", step_start)
        self._add_reasoning(debug_info, f"共创建 {total_items} 个计划项，覆盖 {len(days_data)} 天", "success")
        self._add_reasoning(debug_info, f"匹配到 {matched_templates} 个打卡模板联动", "data")

        # 汇总
        if debug_info:
            total_time = (time.time() - overall_start) * 1000
            debug_info["performance"]["总耗时"] = f"{total_time:.0f}ms"
            debug_info["performance"]["总耗时(秒)"] = f"{total_time/1000:.2f}s"
            self._add_reasoning(debug_info, f"生成完成，总耗时 {total_time:.0f}ms", "success")

        return {"plan": plan, "debug": debug_info}

    async def _call_llm(self, prompt: str, debug: bool = False):
        """返回 (plan_json, llm_debug_info)"""
        llm_debug = {} if debug else None

        if not settings.openclaw_api_key:
            logger.error("OpenClaw API key not configured")
            return None, llm_debug

        messages = [
            {"role": "system", "content": "你是一位资深运动医学和营养学专家，擅长从健康数据中发现规律、识别风险、制定精准的个性化健康计划。你的建议必须基于数据证据，而非泛泛的健康常识。请严格按 JSON 格式输出。"},
            {"role": "user", "content": prompt}
        ]

        content = ""
        for attempt in range(2):
            try:
                call_start = time.time()
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
                    call_time = (time.time() - call_start) * 1000
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})

                    if llm_debug is not None:
                        llm_debug["model"] = settings.openclaw_model
                        llm_debug["attempt"] = attempt + 1
                        llm_debug["api_call_ms"] = f"{call_time:.0f}ms"
                        llm_debug["usage"] = usage
                        llm_debug["response_length"] = len(content)
                        llm_debug["response_preview"] = content[:500] + ("..." if len(content) > 500 else "")

                    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group(1)), llm_debug
                    return json.loads(content), llm_debug

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"LLM 响应解析失败 (attempt {attempt+1}): {e}")
                if llm_debug is not None:
                    llm_debug[f"parse_error_attempt_{attempt+1}"] = str(e)
                if attempt == 0:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "你的输出格式不正确，请严格按照 JSON 格式重新输出，不要包含任何其他文字。"})
                continue
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                if llm_debug is not None:
                    llm_debug["error"] = str(e)
                return None, llm_debug

        return None, llm_debug

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
