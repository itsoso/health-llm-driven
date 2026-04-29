import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models.health_goal_plan import PeriodGoal, PeriodGoalMetric
from app.models.smart_plan import WeeklyPlan
from app.models.weight import WeightRecord
from app.models.user_profile import UserProfile
from app.services.health_context_lite_service import build_lite_health_context
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)


class PeriodGoalService:
    def __init__(self, db: Session):
        self.db = db

    def _get_latest_body_metrics(self, user_id: int) -> Dict[str, Any]:
        """获取用户最新身体指标"""
        latest = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id
        ).order_by(WeightRecord.record_date.desc()).first()

        profile = self.db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()

        metrics = {}
        if latest:
            metrics["weight"] = {"value": latest.weight, "unit": "kg", "date": str(latest.record_date)}
            if latest.bmi:
                metrics["bmi"] = {"value": latest.bmi, "unit": ""}
            if latest.body_fat_percentage:
                metrics["body_fat"] = {"value": latest.body_fat_percentage, "unit": "%"}
            if latest.muscle_mass_kg:
                metrics["muscle_mass"] = {"value": latest.muscle_mass_kg, "unit": "kg"}
            if latest.visceral_fat:
                metrics["visceral_fat"] = {"value": latest.visceral_fat, "unit": "级"}

        if profile:
            if profile.target_weight_kg:
                metrics.setdefault("weight", {})["target"] = profile.target_weight_kg
            if profile.height_cm:
                metrics["height"] = {"value": profile.height_cm, "unit": "cm"}

        return metrics

    def _get_recent_plan_stats(self, user_id: int, weeks: int = 4) -> Dict[str, Any]:
        """获取最近几周的计划完成统计"""
        cutoff = date.today() - timedelta(weeks=weeks)
        plans = self.db.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == user_id,
            WeeklyPlan.week_start >= cutoff
        ).all()

        if not plans:
            return {"weeks": 0, "avg_completion": 0}

        total_rate = sum(p.completion_rate for p in plans)
        return {
            "weeks": len(plans),
            "avg_completion": round(total_rate / len(plans), 1),
            "plans": [
                {"week": str(p.week_start), "rate": p.completion_rate, "focus": p.focus_areas or []}
                for p in plans
            ]
        }

    def _get_weight_trend(self, user_id: int, days: int = 90) -> List[Dict]:
        """获取体重趋势"""
        cutoff = date.today() - timedelta(days=days)
        records = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= cutoff
        ).order_by(WeightRecord.record_date).all()

        return [
            {"date": str(r.record_date), "weight": r.weight, "bmi": r.bmi, "body_fat": r.body_fat_percentage}
            for r in records
        ]

    async def generate_goal(self, user_id: int, period_type: str, target_period: Optional[str] = None, debug: bool = False) -> Dict[str, Any]:
        """生成月度或年度目标"""
        overall_start = time.time()
        debug_info = {"steps": [], "data_sources": {}, "reasoning": [], "performance": {}} if debug else None

        # Step 1: 计算目标周期
        step_start = time.time()
        today = date.today()
        if period_type == "monthly":
            if target_period:
                year, month = map(int, target_period.split("-"))
            else:
                year, month = today.year, today.month
            period_start = date(year, month, 1)
            _, last_day = monthrange(year, month)
            period_end = date(year, month, last_day)
        elif period_type == "yearly":
            if target_period:
                year = int(target_period)
            else:
                year = today.year
            period_start = date(year, 1, 1)
            period_end = date(year, 12, 31)
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")

        if debug_info:
            debug_info["steps"].append("1. 计算目标周期")
            debug_info["reasoning"].append(f"ℹ️ 周期: {period_start} ~ {period_end} ({period_type})")

        # Step 2: 归档已有目标
        step_start = time.time()
        existing = self.db.query(PeriodGoal).filter(
            PeriodGoal.user_id == user_id,
            PeriodGoal.period_type == period_type,
            PeriodGoal.period_start == period_start,
            PeriodGoal.status == "active"
        ).first()
        if existing:
            existing.status = "archived"
            self.db.flush()
            if debug_info:
                debug_info["reasoning"].append(f"⚠️ 已归档旧目标 ID={existing.id}")

        # Step 3: 获取身体指标
        body_metrics = self._get_latest_body_metrics(user_id)
        if debug_info:
            debug_info["steps"].append("2. 获取身体指标")
            debug_info["data_sources"]["body_metrics"] = body_metrics

        # Step 4: 获取计划完成统计
        plan_stats = self._get_recent_plan_stats(user_id, weeks=4 if period_type == "monthly" else 12)
        if debug_info:
            debug_info["steps"].append("3. 获取计划完成统计")
            debug_info["data_sources"]["plan_stats"] = plan_stats

        # Step 5: 获取体重趋势
        weight_trend = self._get_weight_trend(user_id, days=90 if period_type == "monthly" else 365)
        if debug_info:
            debug_info["steps"].append("4. 获取体重趋势")
            debug_info["data_sources"]["weight_trend_count"] = len(weight_trend)

        # Step 6: 获取健康上下文
        health_context = build_lite_health_context(self.db, user_id) or ""
        if debug_info:
            debug_info["steps"].append("5. 获取健康上下文")

        # Step 7: 构建 Prompt
        metrics_str = ""
        for k, v in body_metrics.items():
            name_map = {"weight": "体重", "bmi": "BMI", "body_fat": "体脂率", "muscle_mass": "肌肉量", "visceral_fat": "内脏脂肪", "height": "身高"}
            name = name_map.get(k, k)
            val = v.get("value", "?")
            unit = v.get("unit", "")
            target = v.get("target")
            line = f"- {name}: {val}{unit}"
            if target:
                line += f"（目标: {target}{unit}）"
            metrics_str += line + "\n"

        period_label = "本月" if period_type == "monthly" else "本年"
        milestone_desc = "按周" if period_type == "monthly" else "按月"

        prompt = f"""你是一位专业的健康教练。请根据用户的健康数据，为 {period_start} 至 {period_end} 制定{period_label}健康目标。

用户当前身体指标：
{metrics_str if metrics_str else "暂无身体指标数据"}

最近计划完成情况：
- 统计周数: {plan_stats['weeks']}
- 平均完成率: {plan_stats['avg_completion']}%

用户健康数据摘要：
{health_context[:1500] if health_context else "暂无"}

请严格按照以下 JSON 格式输出，不要输出其他内容：
```json
{{
  "focus_areas": ["重点1", "重点2", "重点3"],
  "summary": "一段话总结{period_label}目标的思路和重点...",
  "metrics": [
    {{
      "metric_type": "weight",
      "metric_name": "体重",
      "current_value": 80,
      "target_value": 78.5,
      "unit": "kg",
      "milestones": [
        {{"period": "第1周", "target": 79.5, "action": "每天有氧30分钟"}},
        {{"period": "第2周", "target": 79.0, "action": "增加力量训练"}}
      ],
      "strategy": "通过有氧运动和饮食控制，{milestone_desc}减重..."
    }}
  ]
}}
```

要求：
1. metrics 应包含 2-5 个可量化的身体指标目标（如体重、BMI、体脂率等）
2. 目标值要基于用户当前数据，设定合理可达的目标
3. milestones {milestone_desc}划分，每个里程碑有具体行动
4. strategy 给出详细的达成策略
5. 如果用户数据不足某个指标，可跳过该指标
6. 循序渐进，不要设定过于激进的目标"""

        if debug_info:
            debug_info["steps"].append("6. 构建 LLM Prompt")
            debug_info["data_sources"]["prompt_preview"] = prompt[:500] + "..."

        # Step 8: 调用 LLM
        step_start = time.time()
        goal_json, llm_debug = await self._call_llm(prompt, debug=debug)
        if debug_info:
            debug_info["steps"].append("7. 调用 LLM 生成目标")
            if llm_debug:
                debug_info["data_sources"]["llm_info"] = llm_debug
            elapsed = (time.time() - step_start) * 1000
            debug_info["performance"]["LLM调用"] = f"{elapsed:.0f}ms"

        if not goal_json:
            if debug_info:
                debug_info["reasoning"].append("❌ LLM 生成失败")
            raise ValueError("AI 生成目标失败，请稍后重试")

        if debug_info:
            debug_info["reasoning"].append(f"✅ LLM 生成成功")
            debug_info["reasoning"].append(f"🎯 focus_areas: {goal_json.get('focus_areas', [])}")

        # Step 9: 保存到数据库
        goal = PeriodGoal(
            user_id=user_id,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            status="active",
            focus_areas=goal_json.get("focus_areas", []),
            summary=goal_json.get("summary", ""),
            ai_model=settings.openclaw_model,
        )
        self.db.add(goal)
        self.db.flush()

        metrics_data = goal_json.get("metrics", [])
        for m in metrics_data:
            if not isinstance(m, dict):
                continue
            metric = PeriodGoalMetric(
                goal_id=goal.id,
                metric_type=m.get("metric_type", "other"),
                metric_name=m.get("metric_name", ""),
                current_value=m.get("current_value"),
                target_value=m.get("target_value"),
                unit=m.get("unit", ""),
                milestones=m.get("milestones"),
                strategy=m.get("strategy", ""),
            )
            self.db.add(metric)

        self.db.commit()
        self.db.refresh(goal)

        if debug_info:
            debug_info["steps"].append("8. 保存目标到数据库")
            debug_info["reasoning"].append(f"✅ 共创建 {len(metrics_data)} 个指标目标")
            total_time = (time.time() - overall_start) * 1000
            debug_info["performance"]["总耗时"] = f"{total_time:.0f}ms"

        return {"goal": goal, "debug": debug_info}

    async def _call_llm(self, prompt: str, debug: bool = False):
        """调用 LLM，返回 (json_data, debug_info)"""
        llm_debug = {} if debug else None

        from app.services.llm.usage_tracker import set_caller
        set_caller("period_goal.generate")
        provider = get_llm_provider()

        messages = [
            {"role": "system", "content": "你是一位专业的健康教练，擅长制定个性化健康目标。请严格按 JSON 格式输出。"},
            {"role": "user", "content": prompt}
        ]

        content = ""
        for attempt in range(2):
            try:
                call_start = time.time()
                content = await provider.chat(
                    messages=messages,
                    temperature=0.7,
                )
                call_time = (time.time() - call_start) * 1000

                if llm_debug is not None:
                    llm_debug["model"] = getattr(provider, 'model', 'unknown')
                    llm_debug["attempt"] = attempt + 1
                    llm_debug["api_call_ms"] = f"{call_time:.0f}ms"

                json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1)), llm_debug
                return json.loads(content), llm_debug

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"LLM 响应解析失败 (attempt {attempt+1}): {e}")
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

    def get_active_goals(self, user_id: int, period_type: Optional[str] = None) -> List[PeriodGoal]:
        """获取活跃目标"""
        query = self.db.query(PeriodGoal).filter(
            PeriodGoal.user_id == user_id,
            PeriodGoal.status == "active"
        )
        if period_type:
            query = query.filter(PeriodGoal.period_type == period_type)
        return query.order_by(PeriodGoal.period_start.desc()).all()

    def update_metric_current_value(self, user_id: int, metric_type: str, new_value: float):
        """自动更新活跃目标中指定类型指标的 current_value"""
        active_goals = self.db.query(PeriodGoal).filter(
            PeriodGoal.user_id == user_id,
            PeriodGoal.status == "active"
        ).all()

        for goal in active_goals:
            for metric in goal.metrics:
                if metric.metric_type == metric_type:
                    metric.current_value = new_value

        self.db.commit()
