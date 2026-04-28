import asyncio
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.models.checkin import CheckinTemplate
from app.services.health_context_lite_service import build_lite_health_context
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)


class SmartPlanService:
    def __init__(self, db: Session):
        self.db = db

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

    # ===== 分析上下文（供前端向导 Step 1 展示） =====

    async def analyze_context(self, user_id: int, target_week: str = "current") -> dict:
        """预计算分析数据，不调用 LLM，纯数据聚合"""
        week_start = self._get_week_start(target_week)
        week_end = week_start + timedelta(days=6)

        past_performance = self._get_performance_summary(user_id, week_start)
        body_metrics = self._get_body_metrics_snapshot(user_id)
        try:
            weather_forecast = await asyncio.wait_for(
                self._get_week_weather(user_id, week_start), timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning("_get_week_weather 超时 (15s)，跳过天气数据")
            weather_forecast = {"available": False, "reason": "天气服务超时"}
        goals = self._get_goals_summary(user_id)
        trips = self._get_trips_context(user_id, week_start)
        suggested_focus = self._compute_suggested_focus(past_performance, body_metrics, goals)

        return {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "past_performance": past_performance,
            "body_metrics": body_metrics,
            "weather_forecast": weather_forecast,
            "active_goals": goals,
            "trips": trips,
            "suggested_focus": suggested_focus,
        }

    def _get_performance_summary(self, user_id: int, current_week_start: date) -> dict:
        """返回结构化的历史计划执行摘要"""
        from collections import defaultdict

        all_cat_stats = defaultdict(lambda: {"done": 0, "total": 0, "items": set()})
        weeks_analyzed = 0
        total_rate = 0.0
        rates = []

        for weeks_ago in range(1, 5):
            ws = current_week_start - timedelta(weeks=weeks_ago)
            plan = self.db.query(WeeklyPlan).filter(
                WeeklyPlan.user_id == user_id,
                WeeklyPlan.week_start == ws
            ).first()
            if not plan:
                continue
            items = self.db.query(PlanItem).filter(PlanItem.plan_id == plan.id).all()
            if not items:
                continue

            weeks_analyzed += 1
            total_rate += plan.completion_rate
            rates.append(plan.completion_rate)

            for item in items:
                cat = all_cat_stats[item.category]
                cat["total"] += 1
                if item.is_completed:
                    cat["done"] += 1
                    cat["items"].add(item.title)

        if weeks_analyzed == 0:
            return {"weeks_analyzed": 0, "avg_completion_rate": 0, "by_category": {}, "trend": "none", "strong_items": [], "weak_items": []}

        avg_rate = total_rate / weeks_analyzed
        # 趋势判断
        trend = "stable"
        if len(rates) >= 2:
            if rates[0] > rates[-1] + 10:
                trend = "improving"
            elif rates[0] < rates[-1] - 10:
                trend = "declining"

        by_category = {}
        strong_items = []
        weak_items = []
        for cat_name, stat in all_cat_stats.items():
            rate = (stat["done"] / stat["total"] * 100) if stat["total"] > 0 else 0
            top_items = list(stat["items"])[:5]
            by_category[cat_name] = {"done": stat["done"], "total": stat["total"], "rate": round(rate), "top_items": top_items}
            if rate >= 70:
                strong_items.extend(top_items[:2])
            elif rate < 50:
                weak_items.extend(top_items[:2])

        return {
            "weeks_analyzed": weeks_analyzed,
            "avg_completion_rate": round(avg_rate),
            "by_category": by_category,
            "trend": trend,
            "strong_items": strong_items[:5],
            "weak_items": weak_items[:5],
        }

    def _get_body_metrics_snapshot(self, user_id: int) -> dict:
        """获取身体指标快照"""
        from app.models.user_profile import UserProfile
        from app.models.weight import WeightRecord
        from app.models.daily_health import GarminData

        result = {}

        # 用户目标
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        target_weight = profile.target_weight_kg if profile else None

        # 最新体重
        latest_weight = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id
        ).order_by(WeightRecord.record_date.desc()).first()
        if latest_weight:
            result["weight"] = {
                "current": latest_weight.weight,
                "target": target_weight,
                "unit": "kg",
                "date": latest_weight.record_date.isoformat(),
            }
            if latest_weight.bmi:
                result["bmi"] = latest_weight.bmi
            if latest_weight.body_fat_percentage:
                result["body_fat"] = latest_weight.body_fat_percentage

        # 最新 Garmin 数据
        latest_garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id
        ).order_by(GarminData.record_date.desc()).first()
        if latest_garmin:
            if latest_garmin.body_battery_current is not None:
                result["body_battery"] = latest_garmin.body_battery_current
            if latest_garmin.stress_level is not None:
                result["stress_level"] = latest_garmin.stress_level
            if latest_garmin.sleep_score is not None:
                result["sleep_score"] = latest_garmin.sleep_score
            if latest_garmin.resting_heart_rate is not None:
                result["resting_hr"] = latest_garmin.resting_heart_rate

        return result

    def _get_user_city(self, user_id: int) -> Optional[str]:
        """获取用户所在城市"""
        from app.models.user_profile import UserProfile
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            return None
        if profile.use_manual_location and profile.manual_city:
            return profile.manual_city
        if profile.detected_city:
            return profile.detected_city
        return profile.city

    async def _get_week_weather(self, user_id: int, week_start: date) -> dict:
        """获取目标周的天气预报 + 空气质量"""
        from app.services.environment.weather_service import WeatherService
        from app.services.environment.air_quality_service import AirQualityService

        city = self._get_user_city(user_id)
        if not city:
            return {"available": False, "reason": "未设置城市"}

        try:
            weather_service = WeatherService()
            forecast_data = await weather_service.get_weather_forecast(city=city, days=7)
            if not forecast_data.get("available"):
                return {"available": False, "reason": "天气服务不可用"}

            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            daily = []
            for i, f in enumerate(forecast_data.get("forecasts", [])[:7]):
                d = week_start + timedelta(days=i)
                daily.append({
                    "date": f"{d.month}/{d.day}",
                    "day_name": day_names[i] if i < 7 else "",
                    "weather": f.get("weather", ""),
                    "temp_high": f.get("temp_max"),
                    "temp_low": f.get("temp_min"),
                })

            # 获取当前空气质量
            air_quality = None
            try:
                aq_service = AirQualityService()
                aq_data = await aq_service.get_air_quality(city=city)
                if aq_data.get("available"):
                    air_quality = {
                        "aqi": aq_data.get("aqi"),
                        "level": aq_data.get("level", ""),
                        "primary_pollutant": aq_data.get("primary_pollutant", ""),
                    }
            except Exception as e:
                logger.warning(f"获取空气质量失败: {e}")

            # 运动建议
            rain_days = [d["day_name"] for d in daily if "雨" in d.get("weather", "") or "雪" in d.get("weather", "")]
            hot_days = [d["day_name"] for d in daily if d.get("temp_high") and d["temp_high"] > 35]
            cold_days = [d["day_name"] for d in daily if d.get("temp_low") and d["temp_low"] < 0]

            advice_parts = []
            if rain_days:
                advice_parts.append(f"{'、'.join(rain_days)}有雨雪，建议安排室内运动")
            if hot_days:
                advice_parts.append(f"{'、'.join(hot_days)}气温较高，避免正午户外运动")
            if cold_days:
                advice_parts.append(f"{'、'.join(cold_days)}气温较低，注意保暖")
            if air_quality and air_quality.get("aqi") and air_quality["aqi"] > 150:
                advice_parts.append(f"空气质量{air_quality['level']}(AQI {air_quality['aqi']})，减少户外运动")
            if not advice_parts:
                advice_parts.append("本周天气适宜户外运动")

            return {
                "available": True,
                "city": city,
                "daily": daily,
                "air_quality": air_quality,
                "exercise_advice": "；".join(advice_parts),
            }
        except Exception as e:
            logger.warning(f"获取天气预报失败: {e}")
            return {"available": False, "reason": str(e)}

    def _get_trips_context(self, user_id: int, week_start: date) -> list:
        """获取目标周内的行程信息"""
        from app.models.trip import Trip
        week_end = week_start + timedelta(days=6)

        trips = self.db.query(Trip).filter(
            Trip.user_id == user_id,
            Trip.start_date <= week_end,
            Trip.end_date >= week_start,
        ).all()

        result = []
        for trip in trips:
            trip_data = {
                "name": trip.trip_name,
                "destination": trip.destination,
                "start_date": trip.start_date.isoformat(),
                "end_date": trip.end_date.isoformat(),
                "days": [],
            }
            for item in trip.items:
                if week_start <= item.item_date <= week_end:
                    day_idx = (item.item_date - week_start).days
                    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                    trip_data["days"].append({
                        "day_name": day_names[day_idx] if day_idx < 7 else "",
                        "date": item.item_date.isoformat(),
                        "title": item.title,
                        "type": item.item_type,
                    })
            result.append(trip_data)
        return result

    def _get_goals_summary(self, user_id: int) -> list:
        """获取活跃目标摘要"""
        from app.models.health_goal_plan import PeriodGoal

        goals = self.db.query(PeriodGoal).filter(
            PeriodGoal.user_id == user_id,
            PeriodGoal.status == "active"
        ).all()

        result = []
        for g in goals:
            goal_data = {
                "id": g.id,
                "period_type": g.period_type,
                "period_start": g.period_start.isoformat(),
                "period_end": g.period_end.isoformat(),
                "focus_areas": g.focus_areas or [],
                "metrics": [],
            }
            for m in g.metrics:
                goal_data["metrics"].append({
                    "metric_name": m.metric_name or m.metric_type,
                    "current_value": m.current_value,
                    "target_value": m.target_value,
                    "unit": m.unit,
                })
            result.append(goal_data)
        return result

    def _compute_suggested_focus(self, past_performance: dict, body_metrics: dict, goals: list) -> list:
        """基于规则引擎生成建议聚焦点"""
        suggestions = []

        # 基于历史完成率
        by_cat = past_performance.get("by_category", {})
        if by_cat.get("diet", {}).get("rate", 100) < 50:
            suggestions.append({"label": "改善饮食习惯", "reason": f"近期饮食打卡率仅{by_cat['diet']['rate']}%"})
        if by_cat.get("exercise", {}).get("rate", 0) >= 70:
            suggestions.append({"label": "提升运动强度", "reason": f"运动执行率{by_cat['exercise']['rate']}%，可适当提升难度"})
        elif by_cat.get("exercise", {}).get("rate", 100) < 50:
            suggestions.append({"label": "降低运动门槛", "reason": f"运动执行率仅{by_cat['exercise']['rate']}%，建议降低难度先建立习惯"})
        if by_cat.get("habit", {}).get("rate", 100) < 50:
            suggestions.append({"label": "培养日常习惯", "reason": f"习惯打卡率{by_cat['habit']['rate']}%，需加强"})

        # 基于身体指标
        weight_data = body_metrics.get("weight", {})
        if weight_data.get("current") and weight_data.get("target"):
            diff = weight_data["current"] - weight_data["target"]
            if diff > 5:
                suggestions.append({"label": "减脂控重", "reason": f"距目标体重还差{diff:.1f}kg"})
            elif diff > 0:
                suggestions.append({"label": "维持体重趋势", "reason": f"距目标体重{diff:.1f}kg，继续保持"})

        if body_metrics.get("sleep_score") and body_metrics["sleep_score"] < 70:
            suggestions.append({"label": "提升睡眠质量", "reason": f"近期睡眠评分{body_metrics['sleep_score']}分"})

        if body_metrics.get("stress_level") and body_metrics["stress_level"] > 60:
            suggestions.append({"label": "压力管理", "reason": f"压力水平{body_metrics['stress_level']}，偏高"})

        # 基于目标
        for goal in goals:
            for metric in goal.get("metrics", []):
                if metric.get("current_value") and metric.get("target_value"):
                    name = metric["metric_name"]
                    suggestions.append({"label": f"推进{name}目标", "reason": f"当前{metric['current_value']}{metric.get('unit', '')}，目标{metric['target_value']}{metric.get('unit', '')}"})

        # 默认建议
        if not suggestions:
            suggestions = [
                {"label": "均衡运动", "reason": "保持每周3-5次运动"},
                {"label": "规律饮食", "reason": "三餐规律，营养均衡"},
                {"label": "充足休息", "reason": "保证7-8小时睡眠"},
            ]

        return suggestions[:6]  # 最多6个建议

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

    async def generate_plan(self, user_id: int, target_week: str = "current",
                            user_focus: List[str] = None, user_notes: str = "",
                            intensity: str = "moderate", debug: bool = False) -> Dict[str, Any]:
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
        health_context = build_lite_health_context(self.db, user_id) or ""
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

        # Step 5.5: 获取天气和行程
        step_start = time.time()
        try:
            weather_data = await asyncio.wait_for(
                self._get_week_weather(user_id, week_start), timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning("_get_week_weather 超时 (15s)，跳过天气数据")
            weather_data = {"available": False, "reason": "天气服务超时"}
        trips_data = self._get_trips_context(user_id, week_start)
        self._add_step(debug_info, "获取天气和行程", step_start)

        weather_context = ""
        if weather_data.get("available"):
            weather_parts = [f"所在城市: {weather_data.get('city', '')}"]
            for d in weather_data.get("daily", []):
                weather_parts.append(f"  {d['day_name']}({d['date']}): {d['weather']} {d.get('temp_low', '')}~{d.get('temp_high', '')}°C")
            if weather_data.get("air_quality"):
                aq = weather_data["air_quality"]
                weather_parts.append(f"  当前空气质量: AQI {aq.get('aqi', '?')} {aq.get('level', '')}")
            weather_parts.append(f"  运动建议: {weather_data.get('exercise_advice', '')}")
            weather_context = "\n".join(weather_parts)
            self._add_reasoning(debug_info, f"天气数据: {weather_data.get('city', '')}", "data")

        trips_context = ""
        if trips_data:
            trips_parts = []
            for trip in trips_data:
                trips_parts.append(f"行程: {trip['name']}（{trip.get('destination', '')}，{trip['start_date']}~{trip['end_date']}）")
                for day in trip.get("days", []):
                    trips_parts.append(f"  {day['day_name']}: {day['title']}（{day['type']}）")
            trips_context = "\n".join(trips_parts)
            self._add_reasoning(debug_info, f"本周有 {len(trips_data)} 个行程", "info")

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

        # 用户偏好
        intensity_map = {"light": "轻松（以恢复和习惯养成为主）", "moderate": "适中（平衡挑战与可持续性）", "challenge": "挑战（追求突破，高强度训练）"}
        intensity_label = intensity_map.get(intensity, intensity_map["moderate"])
        user_prefs = f"""## 用户本周偏好（必须优先满足）
- 重点方向: {', '.join(user_focus) if user_focus else '由你根据数据分析决定'}
- 运动强度偏好: {intensity_label}
- 用户备注: {user_notes if user_notes else '无特殊要求'}"""
        if user_focus:
            self._add_reasoning(debug_info, f"用户选择重点: {', '.join(user_focus)}", "goal")

        # Step 7: 构建 Prompt
        step_start = time.time()
        prompt = f"""你是一位资深的运动医学和营养学专家。你需要先深入分析用户的健康数据，发现隐藏的规律和风险，然后基于这些洞察制定周计划。

## 用户健康数据（请仔细分析趋势和异常）
{health_context}

## 历史计划执行情况（请分析行为模式：哪些容易坚持？哪些总是失败？为什么？）
{feedback_context if feedback_context else "（首次生成计划，无历史数据）"}

## 用户当前阶段性目标（周计划需要服务于这些目标）
{goals_context if goals_context else "（暂无设定目标）"}

## 本周天气与空气质量（影响运动安排）
{weather_context if weather_context else "（天气数据不可用）"}

## 本周行程安排（有行程的日期应调整运动安排）
{trips_context if trips_context else "（本周无特殊行程）"}

{user_prefs}

## 用户打卡模板（运动/习惯项尽量匹配）
{templates_str if templates_str else "（暂无打卡模板）"}

## 你的任务

请为 {week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')} 生成周计划。

**在制定计划前，你必须先完成以下分析（体现在 insights 和 weekly_summary 中）：**

1. **数据洞察**：从健康数据中发现了什么？
2. **行为模式分析**（如果有历史数据）：哪类任务执行率高/低？
3. **风险预警**：是否有健康指标需要关注？
4. **环境因素**：天气、空气质量、行程对运动安排的影响

请严格按照以下 JSON 格式输出（不要输出其他文字）：
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
  "weekly_summary": "基于以上分析，本周计划的核心策略是...（引用具体数据）",
  "days": {{
    "1": [
      {{"category": "exercise", "title": "跑步30分钟", "description": "【依据】根据最近配速和心率数据设定目标", "target_value": 30, "target_unit": "分钟"}},
      {{"category": "diet", "title": "午餐高蛋白", "description": "【依据】近3天蛋白质摄入不足", "target_value": null, "target_unit": null}}
    ],
    "2": [...], "3": [...], "4": [...], "5": [...], "6": [...], "7": [...]
  }}
}}
```

## 关键要求
1. 每个 description 包含"【依据】"，引用具体数据
2. 每天 3-5 个行动项，category: exercise/diet/rest/habit/other
3. insights 基于数据发现，不是泛泛健康常识
4. 雨天/差空气质量日安排室内运动，有行程日减少运动安排
5. 运动安排考虑恢复周期，饮食建议具体到食物/营养素量
6. 对历史低执行率类别降低门槛或换种形式"""
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
        from app.services.llm.usage_tracker import set_caller
        set_caller("smart_plan.generate", user_id=getattr(self, "user_id", None))
        llm_debug = {} if debug else None

        provider = get_llm_provider()

        messages = [
            {"role": "system", "content": "你是一位资深运动医学和营养学专家，擅长从健康数据中发现规律、识别风险、制定精准的个性化健康计划。你的建议必须基于数据证据，而非泛泛的健康常识。请严格按 JSON 格式输出。"},
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
                logger.error(f"LLM 调用失败: {type(e).__name__}: {e}")
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
