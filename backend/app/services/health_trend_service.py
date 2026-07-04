"""健康趋势预测服务"""
import asyncio
import logging
import re
from datetime import date, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func, desc

from app.models.health_trend import HealthTrendReport
from app.models.daily_health import GarminData
from app.models.weight import WeightRecord
from app.services.llm import get_llm_provider
from app.services.health_score_service import HealthScoreService

logger = logging.getLogger(__name__)

DIMENSIONS = ["weight", "sleep", "exercise", "overall"]


class HealthTrendService:
    """健康趋势预测服务"""

    def __init__(self, db: Session):
        self.db = db

    # ==================== 数据聚合 ====================

    def _aggregate_weight_data(self, user_id: int, end_date: date, days: int = 7) -> Optional[Dict[str, Any]]:
        """聚合体重数据"""
        start_date = end_date - timedelta(days=days)
        records = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= start_date,
            WeightRecord.record_date <= end_date,
        ).order_by(WeightRecord.record_date).all()

        if not records:
            return None

        weights = [{"date": str(r.record_date), "weight": r.weight, "bmi": r.bmi} for r in records]
        return {
            "records": weights,
            "latest": records[-1].weight,
            "earliest": records[0].weight,
            "change": round(records[-1].weight - records[0].weight, 2),
            "count": len(records),
        }

    def _aggregate_sleep_data(self, user_id: int, end_date: date, days: int = 7) -> Optional[Dict[str, Any]]:
        """聚合睡眠数据"""
        start_date = end_date - timedelta(days=days)
        records = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date,
            GarminData.sleep_score.isnot(None),
        ).order_by(GarminData.record_date).all()

        if not records:
            return None

        daily = []
        total_score = 0
        total_duration = 0
        total_deep = 0
        count = 0
        for r in records:
            entry = {"date": str(r.record_date), "sleep_score": r.sleep_score}
            if r.total_sleep_duration:
                entry["total_duration"] = r.total_sleep_duration
                total_duration += r.total_sleep_duration
            if r.deep_sleep_duration:
                entry["deep_sleep"] = r.deep_sleep_duration
                total_deep += r.deep_sleep_duration
            daily.append(entry)
            total_score += (r.sleep_score or 0)
            count += 1

        return {
            "daily": daily,
            "avg_sleep_score": round(total_score / count) if count else 0,
            "avg_total_duration": round(total_duration / count) if count else 0,
            "avg_deep_sleep": round(total_deep / count) if count else 0,
            "count": count,
        }

    def _aggregate_exercise_data(self, user_id: int, end_date: date, days: int = 7) -> Optional[Dict[str, Any]]:
        """聚合运动数据"""
        start_date = end_date - timedelta(days=days)
        records = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date,
            GarminData.steps.isnot(None),
        ).order_by(GarminData.record_date).all()

        if not records:
            return None

        daily = []
        total_steps = 0
        total_calories = 0
        total_active = 0
        count = 0
        for r in records:
            entry = {
                "date": str(r.record_date),
                "steps": r.steps,
                "calories": r.calories_burned,
                "active_minutes": r.active_minutes,
            }
            daily.append(entry)
            total_steps += (r.steps or 0)
            total_calories += (r.calories_burned or 0)
            total_active += (r.active_minutes or 0)
            count += 1

        return {
            "daily": daily,
            "avg_steps": round(total_steps / count) if count else 0,
            "avg_calories": round(total_calories / count) if count else 0,
            "total_active_minutes": total_active,
            "count": count,
        }

    def _aggregate_overall_data(self, user_id: int, end_date: date, days: int = 7) -> Optional[Dict[str, Any]]:
        """聚合综合健康数据（利用 HealthScoreService）"""
        score_svc = HealthScoreService()
        trend = score_svc.get_score_trend(self.db, user_id, days=days)
        if not trend.get("scores"):
            return None
        return trend

    # ==================== Prompt 构建 ====================

    DIMENSION_LABELS = {
        "weight": "体重/体脂",
        "sleep": "睡眠质量",
        "exercise": "运动表现",
        "overall": "综合健康",
    }

    def _build_dimension_prompt(self, dimension: str, data: Dict[str, Any]) -> str:
        """为指定维度构建分析 prompt"""
        label = self.DIMENSION_LABELS.get(dimension, dimension)

        prompt = f"""请分析以下用户的「{label}」趋势数据，给出专业的健康趋势分析。

## 数据
{self._format_data_for_prompt(dimension, data)}

## 请按以下格式输出：

趋势方向：[improving/declining/stable 三选一]

洞察：
1. [第1条关键发现]
2. [第2条关键发现]
3. [第3条关键发现（可选）]

建议：
1. [第1条行动建议]
2. [第2条行动建议]
3. [第3条行动建议（可选）]

风险：
[如有健康风险提醒请列出，没有则写"无"]

注意：请用中文回答，简洁专业，每条不超过50字。"""

        return prompt

    def _format_data_for_prompt(self, dimension: str, data: Dict[str, Any]) -> str:
        """格式化数据为 prompt 文本"""
        if dimension == "weight":
            lines = [f"- 最新体重: {data.get('latest')}kg, 起始体重: {data.get('earliest')}kg, 变化: {data.get('change')}kg"]
            for r in data.get("records", [])[:30]:
                lines.append(f"  {r['date']}: {r['weight']}kg" + (f" BMI={r['bmi']}" if r.get('bmi') else ""))
            return "\n".join(lines)

        elif dimension == "sleep":
            lines = [
                f"- 平均睡眠评分: {data.get('avg_sleep_score')}/100",
                f"- 平均睡眠时长: {data.get('avg_total_duration')}分钟",
                f"- 平均深睡时长: {data.get('avg_deep_sleep')}分钟",
            ]
            for r in data.get("daily", [])[:14]:
                lines.append(f"  {r['date']}: 评分{r.get('sleep_score', '-')}, 时长{r.get('total_duration', '-')}分钟, 深睡{r.get('deep_sleep', '-')}分钟")
            return "\n".join(lines)

        elif dimension == "exercise":
            lines = [
                f"- 平均步数: {data.get('avg_steps')}",
                f"- 平均卡路里: {data.get('avg_calories')}kcal",
                f"- 总活动时间: {data.get('total_active_minutes')}分钟",
            ]
            for r in data.get("daily", [])[:14]:
                lines.append(f"  {r['date']}: {r.get('steps', 0)}步, {r.get('calories', 0)}kcal, 活动{r.get('active_minutes', 0)}分钟")
            return "\n".join(lines)

        elif dimension == "overall":
            lines = [
                f"- 平均健康评分: {data.get('avg_score')}/100",
                f"- 趋势: {data.get('trend', 'unknown')}",
            ]
            if data.get("best_day"):
                lines.append(f"- 最佳日: {data['best_day']['date']} ({data['best_day']['score']}分)")
            if data.get("worst_day"):
                lines.append(f"- 最差日: {data['worst_day']['date']} ({data['worst_day']['score']}分)")
            for s in data.get("scores", [])[:14]:
                lines.append(f"  {s['date']}: {s['score']}分 ({s['grade']})")
            return "\n".join(lines)

        return str(data)

    # ==================== 结果解析 ====================

    def _parse_analysis_result(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """解析多模型分析结果"""
        aggregation = raw.get("aggregation", "")

        # 提取趋势方向
        trend_direction = "stable"
        trend_match = re.search(r"趋势方向[：:]\s*(improving|declining|stable)", aggregation, re.IGNORECASE)
        if trend_match:
            trend_direction = trend_match.group(1).lower()

        # 提取洞察
        insights = self._extract_numbered_list(aggregation, "洞察")

        # 提取建议
        suggestions = self._extract_numbered_list(aggregation, "建议")

        # 提取风险
        risk_alerts = []
        risk_match = re.search(r"风险[：:]\s*(.+?)(?:\n\n|$)", aggregation, re.DOTALL)
        if risk_match:
            risk_text = risk_match.group(1).strip()
            if risk_text and risk_text != "无":
                risk_alerts = [line.strip().lstrip("- ").lstrip("0123456789.").strip()
                               for line in risk_text.split("\n") if line.strip() and line.strip() != "无"]

        return {
            "trend_direction": trend_direction,
            "insights": insights,
            "suggestions": suggestions,
            "risk_alerts": risk_alerts,
            "full_report": aggregation,
        }

    def _extract_numbered_list(self, text: str, section_name: str) -> List[str]:
        """从文本中提取编号列表"""
        pattern = rf"{section_name}[：:]\s*\n((?:\d+[.、].+\n?)+)"
        match = re.search(pattern, text)
        if not match:
            return []
        items = []
        for line in match.group(1).strip().split("\n"):
            line = line.strip()
            cleaned = re.sub(r"^\d+[.、]\s*", "", line).strip()
            if cleaned:
                items.append(cleaned)
        return items

    # ==================== 存储 ====================

    def _store_report(self, user_id: int, report_date: date, dimension: str, period: str,
                      trend_direction: str, raw_data_summary: Dict, insights: List[str],
                      suggestions: List[str], risk_alerts: List[str], full_report: str,
                      analysis_batch_id: str, model_results: List) -> HealthTrendReport:
        """存储趋势报告（upsert）"""
        existing = self.db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == user_id,
            HealthTrendReport.report_date == report_date,
            HealthTrendReport.dimension == dimension,
            HealthTrendReport.period == period,
        ).first()

        if existing:
            existing.trend_direction = trend_direction
            existing.raw_data_summary = raw_data_summary
            existing.insights = insights
            existing.suggestions = suggestions
            existing.risk_alerts = risk_alerts
            existing.full_report = full_report
            existing.analysis_batch_id = analysis_batch_id
            existing.model_results = model_results
            self.db.commit()
            return existing

        report = HealthTrendReport(
            user_id=user_id,
            report_date=report_date,
            dimension=dimension,
            period=period,
            trend_direction=trend_direction,
            raw_data_summary=raw_data_summary,
            insights=insights,
            suggestions=suggestions,
            risk_alerts=risk_alerts,
            full_report=full_report,
            analysis_batch_id=analysis_batch_id,
            model_results=model_results,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    # ==================== 查询 ====================

    def get_latest(self, user_id: int) -> List[HealthTrendReport]:
        """获取最新一期各维度趋势报告"""
        latest_date = self.db.query(sa_func.max(HealthTrendReport.report_date)).filter(
            HealthTrendReport.user_id == user_id,
            HealthTrendReport.period == "7d",
        ).scalar()

        if not latest_date:
            return []

        return self.db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == user_id,
            HealthTrendReport.report_date == latest_date,
            HealthTrendReport.period == "7d",
        ).all()

    def get_dimension_report(self, user_id: int, dimension: str, period: str = "7d") -> Optional[HealthTrendReport]:
        """获取指定维度最新报告"""
        return self.db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == user_id,
            HealthTrendReport.dimension == dimension,
            HealthTrendReport.period == period,
        ).order_by(desc(HealthTrendReport.report_date)).first()

    def get_history(self, user_id: int, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """获取历史报告列表"""
        query = self.db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == user_id,
        ).order_by(desc(HealthTrendReport.report_date), HealthTrendReport.dimension)

        total = query.count()
        items = query.offset(offset).limit(limit).all()
        return {"items": items, "total": total}

    # ==================== 主流程 ====================

    async def analyze_trends(self, user_id: int, target_date: Optional[date] = None):
        """为用户分析所有维度的健康趋势"""
        if target_date is None:
            target_date = date.today()

        logger.info(f"[趋势分析] 开始: user={user_id}, date={target_date}")

        from app.services.llm.usage_tracker import set_caller
        set_caller("health_trend.analyze", user_id=user_id)

        aggregators = {
            "weight": lambda: self._aggregate_weight_data(user_id, target_date, days=7),
            "sleep": lambda: self._aggregate_sleep_data(user_id, target_date, days=7),
            "exercise": lambda: self._aggregate_exercise_data(user_id, target_date, days=7),
            "overall": lambda: self._aggregate_overall_data(user_id, target_date, days=7),
        }

        provider = get_llm_provider()
        analyzed_dims = []

        for dimension, aggregator in aggregators.items():
            try:
                data = aggregator()
                if data is None:
                    logger.info(f"[趋势分析] {dimension} 无数据，跳过")
                    continue

                prompt = self._build_dimension_prompt(dimension, data)
                raw_result = await provider.multi_model_analyze(prompt)
                parsed = self._parse_analysis_result(raw_result)

                self._store_report(
                    user_id=user_id,
                    report_date=target_date,
                    dimension=dimension,
                    period="7d",
                    trend_direction=parsed["trend_direction"],
                    raw_data_summary=data,
                    insights=parsed["insights"],
                    suggestions=parsed["suggestions"],
                    risk_alerts=parsed["risk_alerts"],
                    full_report=parsed["full_report"],
                    analysis_batch_id="",
                    model_results=raw_result.get("model_results", []),
                )
                analyzed_dims.append(dimension)
                logger.info(f"[趋势分析] {dimension} 完成: {parsed['trend_direction']}")

            except Exception as e:
                logger.error(f"[趋势分析] {dimension} 失败: {e}")

        logger.info(f"[趋势分析] 完成: user={user_id}, 分析了 {len(analyzed_dims)} 个维度")
        return analyzed_dims
