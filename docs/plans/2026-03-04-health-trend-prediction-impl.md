# 健康趋势预测系统 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于历史健康数据，通过 OpenClaw 多模型 LLM 分析，每日自动生成健康趋势报告，支持 Dashboard 嵌入、通知推送、Chatbot 查询三渠道展示。

**Architecture:** 新增 `HealthTrendService` 服务聚合 4 个维度（体重、睡眠、运动、综合）的历史数据，构造结构化 prompt 发送给 OpenClaw 多模型分析，结果存储到 `HealthTrendReport` 表。通过 Celery beat 每晚 22:00 触发分析，次日 08:00 推送摘要。

**Tech Stack:** FastAPI, SQLAlchemy, Celery, OpenClaw API, Next.js, React Query, Recharts

---

### Task 1: 数据模型 — HealthTrendReport

**Files:**
- Create: `backend/app/models/health_trend.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: 创建 HealthTrendReport 模型**

```python
# backend/app/models/health_trend.py
"""健康趋势预测报告模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Index, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class HealthTrendReport(Base):
    """健康趋势预测报告"""
    __tablename__ = "health_trend_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 报告维度和周期
    report_date = Column(Date, nullable=False, index=True)
    dimension = Column(String(20), nullable=False)  # weight, sleep, exercise, overall
    period = Column(String(10), nullable=False, default="7d")  # 7d, 14d, 30d

    # 趋势结果
    trend_direction = Column(String(20), nullable=True)  # improving, declining, stable
    raw_data_summary = Column(JSON, nullable=True)  # 原始数据摘要
    insights = Column(JSON, nullable=True)  # LLM 洞察列表
    suggestions = Column(JSON, nullable=True)  # LLM 建议列表
    risk_alerts = Column(JSON, nullable=True)  # 风险提醒
    full_report = Column(Text, nullable=True)  # 完整报告文本

    # OpenClaw 元数据
    openclaw_batch_id = Column(String(100), nullable=True)
    model_results = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="health_trend_reports")

    __table_args__ = (
        Index('idx_trend_user_date_dim_period', 'user_id', 'report_date', 'dimension', 'period', unique=True),
    )

    def __repr__(self):
        return f"<HealthTrendReport {self.dimension}/{self.period} user={self.user_id} date={self.report_date}>"
```

**Step 2: 注册模型到 `__init__.py`**

在 `backend/app/models/__init__.py` 末尾添加：

```python
# 健康趋势预测
from app.models.health_trend import HealthTrendReport
```

在 `__all__` 列表末尾添加：

```python
    # 健康趋势预测
    "HealthTrendReport",
```

**Step 3: 验证模型导入**

Run: `cd backend && python -c "from app.models.health_trend import HealthTrendReport; print('OK:', HealthTrendReport.__tablename__)"`
Expected: `OK: health_trend_reports`

**Step 4: Commit**

```bash
git add backend/app/models/health_trend.py backend/app/models/__init__.py
git commit -m "feat: 添加 HealthTrendReport 数据模型"
```

---

### Task 2: Schema — 请求/响应模型

**Files:**
- Create: `backend/app/schemas/health_trend.py`

**Step 1: 创建 schema 文件**

```python
# backend/app/schemas/health_trend.py
"""健康趋势预测 Schema"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List, Dict, Any


class TrendDimensionSummary(BaseModel):
    """单维度趋势摘要"""
    dimension: str
    period: str
    trend_direction: Optional[str] = None
    insights: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None
    risk_alerts: Optional[List[str]] = None
    report_date: date


class TrendLatestResponse(BaseModel):
    """最新趋势概览响应"""
    report_date: Optional[date] = None
    dimensions: List[TrendDimensionSummary]


class TrendDetailResponse(BaseModel):
    """趋势详细报告响应"""
    id: int
    user_id: int
    report_date: date
    dimension: str
    period: str
    trend_direction: Optional[str] = None
    raw_data_summary: Optional[Dict[str, Any]] = None
    insights: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None
    risk_alerts: Optional[List[str]] = None
    full_report: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TrendHistoryResponse(BaseModel):
    """历史报告列表响应"""
    items: List[TrendDetailResponse]
    total: int
```

**Step 2: 验证 schema**

Run: `cd backend && python -c "from app.schemas.health_trend import TrendLatestResponse; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/app/schemas/health_trend.py
git commit -m "feat: 添加健康趋势 Schema"
```

---

### Task 3: 核心服务 — HealthTrendService

**Files:**
- Create: `backend/app/services/health_trend_service.py`

**Step 1: 编写测试**

Create `backend/tests/test_health_trend.py`:

```python
"""健康趋势预测服务测试"""
import pytest
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.health_trend import HealthTrendReport
from app.models.daily_health import GarminData
from app.models.weight import WeightRecord
from app.models.user import User
from app.services.health_trend_service import HealthTrendService


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(name="趋势测试用户", phone="13900139000")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def service(db):
    """创建服务实例"""
    return HealthTrendService(db)


@pytest.fixture
def today():
    return date(2026, 3, 4)


def _create_garmin_data(db, user_id, record_date, **kwargs):
    """辅助函数：创建Garmin数据"""
    data = GarminData(user_id=user_id, record_date=record_date, **kwargs)
    db.add(data)
    db.commit()
    return data


def _create_weight_record(db, user_id, record_date, weight, bmi=None):
    """辅助函数：创建体重记录"""
    record = WeightRecord(user_id=user_id, record_date=record_date, weight=weight, bmi=bmi)
    db.add(record)
    db.commit()
    return record


class TestAggregateWeightData:
    """体重数据聚合测试"""

    def test_aggregate_weight_7d_with_data(self, db, test_user, service, today):
        """7天内有体重数据时应正确聚合"""
        for i in range(7):
            d = today - timedelta(days=i)
            _create_weight_record(db, test_user.id, d, weight=70.0 + i * 0.1)

        data = service._aggregate_weight_data(test_user.id, today, days=7)
        assert data is not None
        assert len(data["records"]) == 7
        assert "latest" in data
        assert "earliest" in data
        assert "change" in data

    def test_aggregate_weight_no_data(self, db, test_user, service, today):
        """没有体重数据时应返回None"""
        data = service._aggregate_weight_data(test_user.id, today, days=7)
        assert data is None


class TestAggregateSleepData:
    """睡眠数据聚合测试"""

    def test_aggregate_sleep_with_data(self, db, test_user, service, today):
        """有睡眠数据时应正确聚合"""
        for i in range(7):
            d = today - timedelta(days=i)
            _create_garmin_data(db, test_user.id, d,
                                sleep_score=75 + i, total_sleep_duration=420 + i * 10,
                                deep_sleep_duration=60 + i)

        data = service._aggregate_sleep_data(test_user.id, today, days=7)
        assert data is not None
        assert "avg_sleep_score" in data
        assert "avg_total_duration" in data
        assert "avg_deep_sleep" in data
        assert len(data["daily"]) == 7

    def test_aggregate_sleep_no_data(self, db, test_user, service, today):
        """没有睡眠数据时应返回None"""
        data = service._aggregate_sleep_data(test_user.id, today, days=7)
        assert data is None


class TestAggregateExerciseData:
    """运动数据聚合测试"""

    def test_aggregate_exercise_with_data(self, db, test_user, service, today):
        """有运动数据时应正确聚合"""
        for i in range(7):
            d = today - timedelta(days=i)
            _create_garmin_data(db, test_user.id, d,
                                steps=8000 + i * 500, calories_burned=2000 + i * 100,
                                active_minutes=30 + i * 5)

        data = service._aggregate_exercise_data(test_user.id, today, days=7)
        assert data is not None
        assert "avg_steps" in data
        assert "avg_calories" in data
        assert "total_active_minutes" in data

    def test_aggregate_exercise_no_data(self, db, test_user, service, today):
        """没有运动数据时应返回None"""
        data = service._aggregate_exercise_data(test_user.id, today, days=7)
        assert data is None


class TestBuildPrompt:
    """Prompt 构建测试"""

    def test_build_prompt_weight(self, service):
        """体重维度 prompt 应包含关键信息"""
        data = {
            "records": [{"date": "2026-03-01", "weight": 70.0}],
            "latest": 70.0,
            "earliest": 71.0,
            "change": -1.0,
        }
        prompt = service._build_dimension_prompt("weight", data)
        assert "体重" in prompt
        assert "70.0" in prompt
        assert "趋势" in prompt

    def test_build_prompt_sleep(self, service):
        """睡眠维度 prompt 应包含关键信息"""
        data = {
            "avg_sleep_score": 78,
            "avg_total_duration": 440,
            "avg_deep_sleep": 65,
            "daily": [{"date": "2026-03-01", "sleep_score": 78}],
        }
        prompt = service._build_dimension_prompt("sleep", data)
        assert "睡眠" in prompt
        assert "78" in prompt


class TestParseAnalysisResult:
    """分析结果解析测试"""

    def test_parse_valid_result(self, service):
        """应正确解析 OpenClaw 返回的结果"""
        raw = {
            "status": "completed",
            "aggregation": """趋势方向：improving
洞察：
1. 体重在过去7天持续下降
2. 平均每天减少0.15kg
建议：
1. 保持当前饮食计划
2. 增加力量训练
风险：无""",
            "model_results": [{"model": "gpt-4", "text": "..."}],
        }
        parsed = service._parse_analysis_result(raw)
        assert parsed["trend_direction"] in ("improving", "declining", "stable")
        assert len(parsed["insights"]) > 0
        assert len(parsed["suggestions"]) > 0

    def test_parse_empty_result(self, service):
        """空结果应返回默认值"""
        raw = {"status": "error", "aggregation": "", "model_results": []}
        parsed = service._parse_analysis_result(raw)
        assert parsed["trend_direction"] == "stable"
        assert parsed["insights"] == []


class TestStoreReport:
    """报告存储测试"""

    def test_store_report_creates_record(self, db, test_user, service, today):
        """应正确创建报告记录"""
        service._store_report(
            user_id=test_user.id,
            report_date=today,
            dimension="weight",
            period="7d",
            trend_direction="improving",
            raw_data_summary={"latest": 70.0},
            insights=["体重持续下降"],
            suggestions=["保持饮食计划"],
            risk_alerts=[],
            full_report="完整报告内容",
            openclaw_batch_id="batch-123",
            model_results=[],
        )

        report = db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == test_user.id,
            HealthTrendReport.dimension == "weight",
        ).first()
        assert report is not None
        assert report.trend_direction == "improving"
        assert report.insights == ["体重持续下降"]

    def test_store_report_upsert(self, db, test_user, service, today):
        """同一维度同一天应覆盖更新"""
        service._store_report(
            user_id=test_user.id, report_date=today, dimension="weight", period="7d",
            trend_direction="stable", raw_data_summary={}, insights=["旧洞察"],
            suggestions=[], risk_alerts=[], full_report="旧报告",
            openclaw_batch_id="batch-1", model_results=[],
        )
        service._store_report(
            user_id=test_user.id, report_date=today, dimension="weight", period="7d",
            trend_direction="improving", raw_data_summary={}, insights=["新洞察"],
            suggestions=[], risk_alerts=[], full_report="新报告",
            openclaw_batch_id="batch-2", model_results=[],
        )

        reports = db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == test_user.id,
            HealthTrendReport.dimension == "weight",
            HealthTrendReport.report_date == today,
        ).all()
        assert len(reports) == 1
        assert reports[0].trend_direction == "improving"
        assert reports[0].insights == ["新洞察"]


class TestGetLatest:
    """获取最新报告测试"""

    def test_get_latest_returns_all_dimensions(self, db, test_user, service, today):
        """应返回所有维度的最新报告"""
        for dim in ["weight", "sleep", "exercise", "overall"]:
            service._store_report(
                user_id=test_user.id, report_date=today, dimension=dim, period="7d",
                trend_direction="stable", raw_data_summary={}, insights=["测试"],
                suggestions=[], risk_alerts=[], full_report="报告",
                openclaw_batch_id="b1", model_results=[],
            )

        result = service.get_latest(test_user.id)
        assert len(result) == 4
        dims = [r.dimension for r in result]
        assert "weight" in dims
        assert "sleep" in dims

    def test_get_latest_empty(self, db, test_user, service):
        """无报告时返回空列表"""
        result = service.get_latest(test_user.id)
        assert result == []
```

**Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_health_trend.py -v --tb=short 2>&1 | head -30`
Expected: FAIL (module not found)

**Step 3: 实现 HealthTrendService**

```python
# backend/app/services/health_trend_service.py
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
from app.services.openclaw_analyze import OpenClawAnalyzeClient
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
        """解析 OpenClaw 分析结果"""
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
                      openclaw_batch_id: str, model_results: List) -> HealthTrendReport:
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
            existing.openclaw_batch_id = openclaw_batch_id
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
            openclaw_batch_id=openclaw_batch_id,
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

        aggregators = {
            "weight": lambda: self._aggregate_weight_data(user_id, target_date, days=7),
            "sleep": lambda: self._aggregate_sleep_data(user_id, target_date, days=7),
            "exercise": lambda: self._aggregate_exercise_data(user_id, target_date, days=7),
            "overall": lambda: self._aggregate_overall_data(user_id, target_date, days=7),
        }

        client = OpenClawAnalyzeClient()
        analyzed_dims = []

        for dimension, aggregator in aggregators.items():
            try:
                data = aggregator()
                if data is None:
                    logger.info(f"[趋势分析] {dimension} 无数据，跳过")
                    continue

                prompt = self._build_dimension_prompt(dimension, data)
                raw_result = await client.analyze(prompt)
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
                    openclaw_batch_id="",
                    model_results=raw_result.get("model_results", []),
                )
                analyzed_dims.append(dimension)
                logger.info(f"[趋势分析] {dimension} 完成: {parsed['trend_direction']}")

            except Exception as e:
                logger.error(f"[趋势分析] {dimension} 失败: {e}")

        logger.info(f"[趋势分析] 完成: user={user_id}, 分析了 {len(analyzed_dims)} 个维度")
        return analyzed_dims
```

**Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/test_health_trend.py -v --tb=short`
Expected: 全部 PASS

**Step 5: Commit**

```bash
git add backend/app/services/health_trend_service.py backend/tests/test_health_trend.py
git commit -m "feat: 实现 HealthTrendService 核心服务 + 测试"
```

---

### Task 4: API 端点

**Files:**
- Create: `backend/app/api/health_trend.py`
- Modify: `backend/app/api/main.py`

**Step 1: 创建 API 路由**

```python
# backend/app/api/health_trend.py
"""健康趋势预测 API"""
import asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.health_trend_service import HealthTrendService

router = APIRouter(prefix="/health-trends", tags=["health-trends"])


@router.get("/latest")
async def get_latest_trends(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取最新一期各维度趋势概览"""
    svc = HealthTrendService(db)
    reports = svc.get_latest(current_user.id)
    return {
        "report_date": str(reports[0].report_date) if reports else None,
        "dimensions": [
            {
                "dimension": r.dimension,
                "period": r.period,
                "trend_direction": r.trend_direction,
                "insights": r.insights or [],
                "suggestions": r.suggestions or [],
                "risk_alerts": r.risk_alerts or [],
                "report_date": str(r.report_date),
            }
            for r in reports
        ],
    }


@router.get("/{dimension}")
async def get_dimension_trend(
    dimension: str,
    period: str = Query(default="7d", regex="^(7d|14d|30d)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取指定维度详细报告"""
    if dimension not in ("weight", "sleep", "exercise", "overall"):
        return {"error": "无效维度，支持: weight, sleep, exercise, overall"}

    svc = HealthTrendService(db)
    report = svc.get_dimension_report(current_user.id, dimension, period)
    if not report:
        return {"error": "暂无该维度的趋势报告"}

    return {
        "id": report.id,
        "user_id": report.user_id,
        "report_date": str(report.report_date),
        "dimension": report.dimension,
        "period": report.period,
        "trend_direction": report.trend_direction,
        "raw_data_summary": report.raw_data_summary,
        "insights": report.insights or [],
        "suggestions": report.suggestions or [],
        "risk_alerts": report.risk_alerts or [],
        "full_report": report.full_report,
        "created_at": str(report.created_at),
    }


@router.get("/history")
async def get_trend_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取历史报告列表"""
    svc = HealthTrendService(db)
    result = svc.get_history(current_user.id, limit=limit, offset=offset)
    return {
        "total": result["total"],
        "items": [
            {
                "id": r.id,
                "report_date": str(r.report_date),
                "dimension": r.dimension,
                "period": r.period,
                "trend_direction": r.trend_direction,
                "insights": r.insights or [],
                "created_at": str(r.created_at),
            }
            for r in result["items"]
        ],
    }


@router.post("/generate")
async def generate_trends(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手动触发趋势分析（调试用）"""
    svc = HealthTrendService(db)
    analyzed = await svc.analyze_trends(current_user.id)
    return {"analyzed_dimensions": analyzed}
```

**Step 2: 注册路由到 `main.py`**

在 `backend/app/api/main.py` 的 import 区添加:

```python
    health_trend,  # 健康趋势预测
```

在路由注册区末尾添加:

```python
# 健康趋势预测
api_router.include_router(health_trend.router)  # 健康趋势预测
```

**Step 3: 验证路由注册**

Run: `cd backend && python -c "from app.api.main import api_router; print('Routes:', len(api_router.routes))"`
Expected: 输出路由数量

**Step 4: Commit**

```bash
git add backend/app/api/health_trend.py backend/app/api/main.py
git commit -m "feat: 添加健康趋势 API 端点"
```

---

### Task 5: Celery 定时任务

**Files:**
- Modify: `backend/app/tasks/notifications.py`
- Modify: `backend/app/celery_app.py`

**Step 1: 在 `notifications.py` 添加趋势分析任务**

在文件末尾追加:

```python
@celery_app.task(time_limit=600)
def daily_trend_analysis():
    """
    每日健康趋势分析（22:00执行）
    为活跃用户生成各维度健康趋势报告。
    """
    from app.models.device_credential import DeviceCredential
    from app.services.health_trend_service import HealthTrendService

    logger.info("[趋势分析] 开始每日趋势分析")

    with SessionLocal() as db:
        credentials = db.query(DeviceCredential).filter(
            DeviceCredential.device_type == "garmin",
            DeviceCredential.is_active == True
        ).all()
        user_ids = [c.user_id for c in credentials]

    logger.info(f"[趋势分析] 发现 {len(user_ids)} 个活跃用户")
    analyzed_count = 0

    for user_id in user_ids:
        try:
            with SessionLocal() as db:
                svc = HealthTrendService(db)
                dims = asyncio.run(svc.analyze_trends(user_id))
                if dims:
                    analyzed_count += 1
                    logger.info(f"[趋势分析] 用户 {user_id} 完成: {dims}")
        except Exception as e:
            logger.error(f"[趋势分析] 用户 {user_id} 失败: {e}")

    logger.info(f"[趋势分析] 完成，分析 {analyzed_count}/{len(user_ids)} 用户")
    return {"analyzed_count": analyzed_count, "total_users": len(user_ids)}


@celery_app.task
def send_trend_morning_push():
    """
    早间趋势摘要推送（08:30执行）
    推送昨日生成的趋势报告摘要。
    """
    from app.models.health_trend import HealthTrendReport

    logger.info("[趋势推送] 开始早间推送")

    with SessionLocal() as db:
        today = date.today()
        yesterday = today - timedelta(days=1)

        reports = db.query(HealthTrendReport).filter(
            HealthTrendReport.report_date == yesterday,
            HealthTrendReport.period == "7d",
        ).all()

        user_reports = {}
        for r in reports:
            user_reports.setdefault(r.user_id, []).append(r)

        push_service = PushService(db)
        sent_count = 0

        for user_id, user_rpts in user_reports.items():
            try:
                # 优先推送有风险提醒的
                risk_items = [r for r in user_rpts if r.risk_alerts]
                if risk_items:
                    body = f"⚠️ {risk_items[0].risk_alerts[0]}"
                else:
                    improving = [r for r in user_rpts if r.trend_direction == "improving"]
                    declining = [r for r in user_rpts if r.trend_direction == "declining"]
                    dim_labels = {"weight": "体重", "sleep": "睡眠", "exercise": "运动", "overall": "综合"}
                    parts = []
                    if improving:
                        parts.append("↑ " + "、".join(dim_labels.get(r.dimension, r.dimension) for r in improving))
                    if declining:
                        parts.append("↓ " + "、".join(dim_labels.get(r.dimension, r.dimension) for r in declining))
                    body = " | ".join(parts) if parts else "各项指标平稳"

                asyncio.run(
                    push_service.send_notification(
                        user_id=user_id,
                        notification_type="trend_report",
                        title="📈 健康趋势",
                        content=body[:200],
                    )
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"[趋势推送] 用户 {user_id} 推送失败: {e}")

    logger.info(f"[趋势推送] 完成，推送 {sent_count} 条")
    return {"sent_count": sent_count}
```

**Step 2: 在 `celery_app.py` 添加 beat schedule**

在 `beat_schedule` 字典末尾（`daily-anomaly-check` 之后）添加:

```python
    # 每日 22:00 健康趋势分析
    "daily-trend-analysis": {
        "task": "app.tasks.notifications.daily_trend_analysis",
        "schedule": crontab(hour=22, minute=0),
    },

    # 每日 08:30 趋势摘要推送
    "trend-morning-push": {
        "task": "app.tasks.notifications.send_trend_morning_push",
        "schedule": crontab(hour=8, minute=30),
    },
```

**Step 3: 验证 Celery 配置**

Run: `cd backend && python -c "from app.celery_app import celery_app; print('Tasks:', [k for k in celery_app.conf.beat_schedule.keys() if 'trend' in k])"`
Expected: `Tasks: ['daily-trend-analysis', 'trend-morning-push']`

**Step 4: Commit**

```bash
git add backend/app/tasks/notifications.py backend/app/celery_app.py
git commit -m "feat: 添加健康趋势定时任务 — 22:00分析 + 08:30推送"
```

---

### Task 6: Chatbot 集成

**Files:**
- Modify: `backend/app/services/chat_service.py`

**Step 1: 在 ChatService 的系统 prompt 中注入趋势数据**

在 `chat_service.py` 中找到构建系统 prompt 的方法（`_build_system_prompt` 或类似），添加趋势数据注入逻辑:

```python
# 在系统 prompt 数据聚合部分追加：
def _get_trend_context(self, user_id: int) -> str:
    """获取用户最新趋势数据，注入到聊天上下文"""
    from app.models.health_trend import HealthTrendReport
    reports = self.db.query(HealthTrendReport).filter(
        HealthTrendReport.user_id == user_id,
        HealthTrendReport.period == "7d",
    ).order_by(HealthTrendReport.report_date.desc()).limit(4).all()

    if not reports:
        return ""

    dim_labels = {"weight": "体重", "sleep": "睡眠", "exercise": "运动", "overall": "综合"}
    lines = [f"\n## 健康趋势（{reports[0].report_date}）"]
    for r in reports:
        label = dim_labels.get(r.dimension, r.dimension)
        direction_cn = {"improving": "改善中", "declining": "下降中", "stable": "平稳"}.get(r.trend_direction, "未知")
        lines.append(f"- {label}: {direction_cn}")
        if r.insights:
            for insight in r.insights[:2]:
                lines.append(f"  - {insight}")
    return "\n".join(lines)
```

然后在构建系统 prompt 的地方调用 `self._get_trend_context(user_id)` 并拼入系统 prompt。

**Step 2: Commit**

```bash
git add backend/app/services/chat_service.py
git commit -m "feat: Chatbot 注入健康趋势上下文"
```

---

### Task 7: 前端 API 服务

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: 添加 healthTrendApi**

在 `frontend/src/services/api.ts` 的 `achievementApi` 之后添加:

```typescript
export const healthTrendApi = {
  getLatest: () =>
    api.get<{
      report_date: string | null;
      dimensions: Array<{
        dimension: string;
        period: string;
        trend_direction: string | null;
        insights: string[];
        suggestions: string[];
        risk_alerts: string[];
        report_date: string;
      }>;
    }>('/health-trends/latest'),
  getDimension: (dimension: string, period: string = '7d') =>
    api.get<{
      id: number;
      report_date: string;
      dimension: string;
      period: string;
      trend_direction: string | null;
      raw_data_summary: Record<string, unknown> | null;
      insights: string[];
      suggestions: string[];
      risk_alerts: string[];
      full_report: string | null;
      created_at: string;
    }>(`/health-trends/${dimension}`, { params: { period } }),
  getHistory: (limit: number = 20, offset: number = 0) =>
    api.get<{
      total: number;
      items: Array<{
        id: number;
        report_date: string;
        dimension: string;
        period: string;
        trend_direction: string | null;
        insights: string[];
        created_at: string;
      }>;
    }>('/health-trends/history', { params: { limit, offset } }),
  generate: () =>
    api.post<{ analyzed_dimensions: string[] }>('/health-trends/generate'),
};
```

**Step 2: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: 添加 healthTrendApi 前端服务"
```

---

### Task 8: 前端趋势详情页

**Files:**
- Create: `frontend/src/app/health-trends/page.tsx`

**Step 1: 创建趋势页面**

```tsx
// frontend/src/app/health-trends/page.tsx
'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { healthTrendApi } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const DIMENSION_LABELS: Record<string, string> = {
  weight: '体重/体脂',
  sleep: '睡眠质量',
  exercise: '运动表现',
  overall: '综合健康',
};

const DIMENSION_ICONS: Record<string, string> = {
  weight: '⚖️',
  sleep: '😴',
  exercise: '🏃',
  overall: '💚',
};

const TREND_ICONS: Record<string, string> = {
  improving: '📈',
  declining: '📉',
  stable: '➡️',
};

const TREND_LABELS: Record<string, string> = {
  improving: '改善中',
  declining: '下降中',
  stable: '平稳',
};

const TREND_COLORS: Record<string, string> = {
  improving: 'text-green-600 bg-green-50',
  declining: 'text-red-600 bg-red-50',
  stable: 'text-blue-600 bg-blue-50',
};

function HealthTrendsContent() {
  const { user } = useAuth();
  const [selectedDim, setSelectedDim] = useState<string | null>(null);
  const [period, setPeriod] = useState('7d');

  const { data: latestData, isLoading } = useQuery({
    queryKey: ['health-trends-latest', user?.id],
    queryFn: () => healthTrendApi.getLatest(),
    enabled: !!user?.id,
  });

  const { data: detailData, isLoading: isDetailLoading } = useQuery({
    queryKey: ['health-trends-detail', user?.id, selectedDim, period],
    queryFn: () => healthTrendApi.getDimension(selectedDim!, period),
    enabled: !!user?.id && !!selectedDim,
  });

  const latest = latestData?.data;
  const detail = detailData?.data;

  return (
    <div className="min-h-screen bg-gray-50 p-4 pb-20">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">健康趋势</h1>

      {isLoading ? (
        <div className="text-center text-gray-500 py-12">加载中...</div>
      ) : !latest?.dimensions?.length ? (
        <div className="text-center text-gray-500 py-12">
          <p className="text-lg mb-2">暂无趋势数据</p>
          <p className="text-sm">系统每晚自动分析，请保持数据记录</p>
        </div>
      ) : (
        <>
          {/* 趋势概览卡片 */}
          <div className="grid grid-cols-2 gap-3 mb-6">
            {latest.dimensions.map((dim) => (
              <button
                key={dim.dimension}
                onClick={() => setSelectedDim(dim.dimension === selectedDim ? null : dim.dimension)}
                className={`p-4 rounded-xl text-left transition-all ${
                  selectedDim === dim.dimension
                    ? 'ring-2 ring-blue-500 bg-white shadow-lg'
                    : 'bg-white shadow-sm hover:shadow-md'
                }`}
              >
                <div className="text-2xl mb-1">
                  {DIMENSION_ICONS[dim.dimension] || '📊'}
                </div>
                <div className="text-sm font-medium text-gray-700">
                  {DIMENSION_LABELS[dim.dimension] || dim.dimension}
                </div>
                <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs mt-2 ${
                  TREND_COLORS[dim.trend_direction || 'stable']
                }`}>
                  {TREND_ICONS[dim.trend_direction || 'stable']}{' '}
                  {TREND_LABELS[dim.trend_direction || 'stable']}
                </div>
                {dim.insights?.[0] && (
                  <p className="text-xs text-gray-500 mt-2 line-clamp-2">
                    {dim.insights[0]}
                  </p>
                )}
              </button>
            ))}
          </div>

          {/* 详细报告区 */}
          {selectedDim && (
            <div className="bg-white rounded-xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">
                  {DIMENSION_ICONS[selectedDim]} {DIMENSION_LABELS[selectedDim]} 详细报告
                </h2>
                <div className="flex gap-1">
                  {['7d', '14d', '30d'].map((p) => (
                    <button
                      key={p}
                      onClick={() => setPeriod(p)}
                      className={`px-3 py-1 rounded-full text-xs ${
                        period === p
                          ? 'bg-blue-500 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {p.replace('d', '天')}
                    </button>
                  ))}
                </div>
              </div>

              {isDetailLoading ? (
                <div className="text-center text-gray-400 py-8">分析加载中...</div>
              ) : detail?.full_report ? (
                <div className="space-y-4">
                  {/* 洞察 */}
                  {detail.insights?.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 mb-2">关键洞察</h3>
                      <ul className="space-y-1">
                        {detail.insights.map((item: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                            <span className="text-blue-500 mt-0.5">•</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* 建议 */}
                  {detail.suggestions?.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 mb-2">行动建议</h3>
                      <ul className="space-y-1">
                        {detail.suggestions.map((item: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                            <span className="text-green-500 mt-0.5">✓</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* 风险 */}
                  {detail.risk_alerts?.length > 0 && (
                    <div className="bg-red-50 rounded-lg p-3">
                      <h3 className="text-sm font-medium text-red-700 mb-1">风险提醒</h3>
                      {detail.risk_alerts.map((item: string, i: number) => (
                        <p key={i} className="text-sm text-red-600">{item}</p>
                      ))}
                    </div>
                  )}

                  <p className="text-xs text-gray-400 pt-2">
                    报告日期: {detail.report_date}
                  </p>
                </div>
              ) : (
                <div className="text-center text-gray-400 py-8">暂无该周期的报告</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function HealthTrendsPage() {
  return (
    <ProtectedRoute>
      <HealthTrendsContent />
    </ProtectedRoute>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/health-trends/page.tsx
git commit -m "feat: 添加健康趋势详情页面"
```

---

### Task 9: Dashboard 嵌入趋势卡片

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`

**Step 1: 在 Dashboard 页面添加趋势卡片**

在 `DashboardContent` 组件中添加查询:

```tsx
import { healthTrendApi } from '@/services/api';

// 在 DashboardContent 中添加:
const { data: trendData } = useQuery({
  queryKey: ['health-trends-latest', userId],
  queryFn: () => healthTrendApi.getLatest(),
  enabled: !!userId,
});
```

在合适位置渲染趋势卡片（在其他数据卡片区域附近）:

```tsx
{/* 健康趋势卡片 */}
{trendData?.data?.dimensions?.length > 0 && (
  <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-base font-semibold text-gray-800">健康趋势</h3>
      <a href="/health-trends" className="text-sm text-blue-500">查看详情 →</a>
    </div>
    <div className="grid grid-cols-2 gap-2">
      {trendData.data.dimensions.map((dim: any) => {
        const icons: Record<string, string> = { weight: '⚖️', sleep: '😴', exercise: '🏃', overall: '💚' };
        const labels: Record<string, string> = { weight: '体重', sleep: '睡眠', exercise: '运动', overall: '综合' };
        const trendIcons: Record<string, string> = { improving: '↑', declining: '↓', stable: '→' };
        const trendColors: Record<string, string> = { improving: 'text-green-600', declining: 'text-red-600', stable: 'text-blue-600' };
        return (
          <div key={dim.dimension} className="flex items-center gap-2 p-2 rounded-lg bg-gray-50">
            <span>{icons[dim.dimension] || '📊'}</span>
            <span className="text-sm text-gray-700">{labels[dim.dimension] || dim.dimension}</span>
            <span className={`ml-auto font-medium ${trendColors[dim.trend_direction || 'stable']}`}>
              {trendIcons[dim.trend_direction || 'stable']}
            </span>
          </div>
        );
      })}
    </div>
    {trendData.data.dimensions[0]?.insights?.[0] && (
      <p className="text-xs text-gray-500 mt-2">{trendData.data.dimensions[0].insights[0]}</p>
    )}
  </div>
)}
```

**Step 2: Commit**

```bash
git add frontend/src/app/dashboard/page.tsx
git commit -m "feat: Dashboard 嵌入健康趋势卡片"
```

---

### Task 10: 运行全部测试 + 最终验证

**Step 1: 运行后端测试**

Run: `cd backend && python -m pytest tests/test_health_trend.py -v`
Expected: 全部 PASS

**Step 2: 运行前端构建验证**

Run: `cd frontend && npx next build 2>&1 | tail -20`
Expected: 构建成功，无错误

**Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat: 健康趋势预测系统 — 完整实现"
```

---

## 文件清单总结

| 新增 | 说明 |
|------|------|
| `backend/app/models/health_trend.py` | HealthTrendReport 模型 |
| `backend/app/services/health_trend_service.py` | 数据聚合 + OpenClaw 分析 + 解析 |
| `backend/app/api/health_trend.py` | 4 个 API 端点 |
| `backend/app/schemas/health_trend.py` | 请求/响应模型 |
| `backend/tests/test_health_trend.py` | 单元测试 |
| `frontend/src/app/health-trends/page.tsx` | 趋势详情页 |

| 修改 | 改动 |
|------|------|
| `backend/app/models/__init__.py` | 注册模型 |
| `backend/app/api/main.py` | 注册路由 |
| `backend/app/celery_app.py` | 定时任务 |
| `backend/app/tasks/notifications.py` | 趋势分析 + 推送任务 |
| `backend/app/services/chat_service.py` | 趋势上下文注入 |
| `frontend/src/services/api.ts` | healthTrendApi |
| `frontend/src/app/dashboard/page.tsx` | 趋势卡片 |
