# AI 智能计划 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an AI-powered weekly health plan generator that creates personalized daily action items, links to the checkin system for tracking, and improves over time via feedback loops.

**Architecture:** New `WeeklyPlan` + `PlanItem` models, a `SmartPlanService` that reuses `ChatService._build_health_context()` to feed user data into LLM for structured plan generation. Checkin record creation hooks auto-mark plan items complete. Frontend page with day-by-day view and progress tracking.

**Tech Stack:** FastAPI, SQLAlchemy, OpenClaw LLM API, Celery, Next.js, React Query, Tailwind CSS, Taro

---

## Task 1: Database Models

**Files:**
- Create: `backend/app/models/smart_plan.py`
- Modify: `backend/app/models/__init__.py` (if exists, to export new models)

**Step 1: Create the models file**

```python
# backend/app/models/smart_plan.py
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, JSON, ForeignKey, Text, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class WeeklyPlan(Base):
    """AI 生成的周计划"""
    __tablename__ = "weekly_plans"
    __table_args__ = (
        UniqueConstraint('user_id', 'week_start', name='uq_user_week'),
        Index('ix_weekly_plan_user_status', 'user_id', 'status'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    week_start = Column(Date, nullable=False)  # 周一日期
    status = Column(String(20), default="active", nullable=False)  # draft/active/completed/archived
    focus_areas = Column(JSON, default=list)  # AI 识别的本周重点
    weekly_summary = Column(Text, nullable=True)  # AI 生成的周总览
    completion_rate = Column(Float, default=0.0)  # 0-100
    ai_model = Column(String(100), nullable=True)
    user_feedback = Column(Integer, nullable=True)  # 1-5
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship("PlanItem", back_populates="plan", cascade="all, delete-orphan")


class PlanItem(Base):
    """周计划中的单个行动项"""
    __tablename__ = "plan_items"
    __table_args__ = (
        Index('ix_plan_item_plan_day', 'plan_id', 'day_of_week'),
    )

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("weekly_plans.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 1=周一 ~ 7=周日
    category = Column(String(20), nullable=False)  # exercise/diet/rest/habit/other
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    target_value = Column(Float, nullable=True)
    target_unit = Column(String(20), nullable=True)
    checkin_template_id = Column(Integer, ForeignKey("checkin_templates.id"), nullable=True)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("WeeklyPlan", back_populates="items")
```

**Step 2: Run database migration on server**

```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && source venv/bin/activate && python -c \"
from app.database import engine, Base
from app.models.smart_plan import WeeklyPlan, PlanItem
Base.metadata.create_all(bind=engine)
print('Tables created successfully')
\""
```

**Step 3: Commit**

```bash
git add backend/app/models/smart_plan.py
git commit -m "feat(smart-plan): add WeeklyPlan and PlanItem database models"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/smart_plan.py`

**Step 1: Create schemas**

```python
# backend/app/schemas/smart_plan.py
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class PlanItemResponse(BaseModel):
    id: int
    day_of_week: int
    category: str
    title: str
    description: Optional[str] = None
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    checkin_template_id: Optional[int] = None
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    sort_order: int = 0

    class Config:
        from_attributes = True


class WeeklyPlanResponse(BaseModel):
    id: int
    user_id: int
    week_start: date
    status: str
    focus_areas: List[str] = []
    weekly_summary: Optional[str] = None
    completion_rate: float = 0.0
    ai_model: Optional[str] = None
    user_feedback: Optional[int] = None
    items: List[PlanItemResponse] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WeeklyPlanListItem(BaseModel):
    id: int
    week_start: date
    status: str
    focus_areas: List[str] = []
    completion_rate: float = 0.0
    user_feedback: Optional[int] = None
    item_count: int = 0
    completed_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class GeneratePlanRequest(BaseModel):
    target_week: str = Field("current", description="'current' 或 'next'")


class PlanItemUpdate(BaseModel):
    is_completed: bool


class PlanFeedbackRequest(BaseModel):
    score: int = Field(..., ge=1, le=5, description="评分 1-5")
```

**Step 2: Commit**

```bash
git add backend/app/schemas/smart_plan.py
git commit -m "feat(smart-plan): add Pydantic request/response schemas"
```

---

## Task 3: SmartPlanService — LLM Plan Generation

**Files:**
- Create: `backend/app/services/smart_plan_service.py`
- Read (reference): `backend/app/services/chat_service.py` — reuse `_build_health_context` pattern

**Step 1: Create the service**

```python
# backend/app/services/smart_plan_service.py
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models.user import User
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.models.checkin import CheckinTemplate
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)


class SmartPlanService:
    def __init__(self, db: Session):
        self.db = db
        self.chat_service = ChatService(db)

    def _get_week_start(self, target: str) -> date:
        """获取目标周的周一日期"""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        if target == "next":
            monday += timedelta(weeks=1)
        return monday

    def _get_last_week_feedback(self, user_id: int, current_week_start: date) -> str:
        """获取上周计划完成情况作为反馈上下文"""
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
        """获取用户所有可用打卡模板"""
        templates = self.db.query(CheckinTemplate).filter(
            CheckinTemplate.user_id == user_id,
            CheckinTemplate.is_active == True
        ).all()
        return [
            {"id": t.id, "name": t.name, "category": t.category, "unit": t.unit, "default_target": t.default_target}
            for t in templates
        ]

    def _match_template(self, title: str, templates: List[Dict]) -> Optional[int]:
        """模糊匹配打卡模板"""
        title_lower = title.lower()
        for t in templates:
            name_lower = t["name"].lower()
            # 精确包含匹配
            if name_lower in title_lower or title_lower in name_lower:
                return t["id"]
        # 关键词匹配
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
        """生成周计划"""
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
        templates_str = "\n".join(f"- {t['name']}（{t['category']}，单位:{t['unit']}，目标:{t['default_target']}）" for t in templates)

        week_end = week_start + timedelta(days=6)
        prompt = f"""你是一位专业的健康教练。请根据用户的健康数据，为 {week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')} 这一周生成个性化健康计划。

用户健康数据：
{health_context}
{feedback_context}

用户已有的打卡模板（生成运动/习惯项时请尽量匹配这些名称）：
{templates_str}

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

        # 调用 LLM
        plan_json = await self._call_llm(prompt)
        if not plan_json:
            raise ValueError("AI 生成计划失败")

        # 解析并存储
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

        # 创建 PlanItems
        days_data = plan_json.get("days", {})
        for day_str, items in days_data.items():
            day_num = int(day_str)
            for idx, item_data in enumerate(items):
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
        """调用 OpenClaw LLM 并解析 JSON 响应"""
        if not settings.openclaw_api_key:
            logger.error("OpenClaw API key not configured")
            return None

        messages = [
            {"role": "system", "content": "你是一位专业的健康教练，擅长制定个性化健康计划。请严格按 JSON 格式输出。"},
            {"role": "user", "content": prompt}
        ]

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

                    # 提取 JSON
                    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group(1))
                    # 尝试直接解析
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
        """更新计划完成率"""
        total = self.db.query(func.count(PlanItem.id)).filter(PlanItem.plan_id == plan_id).scalar()
        completed = self.db.query(func.count(PlanItem.id)).filter(
            PlanItem.plan_id == plan_id,
            PlanItem.is_completed == True
        ).scalar()
        rate = (completed / total * 100) if total > 0 else 0.0

        plan = self.db.query(WeeklyPlan).filter(WeeklyPlan.id == plan_id).first()
        if plan:
            plan.completion_rate = round(rate, 1)
            # 全部完成时标记计划为 completed
            if rate >= 100:
                plan.status = "completed"
            self.db.commit()
```

**Step 2: Commit**

```bash
git add backend/app/services/smart_plan_service.py
git commit -m "feat(smart-plan): add SmartPlanService with LLM plan generation"
```

---

## Task 4: API Router

**Files:**
- Create: `backend/app/api/smart_plan.py`
- Modify: `backend/app/api/main.py` — register router

**Step 1: Create the API router**

```python
# backend/app/api/smart_plan.py
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.schemas.smart_plan import (
    WeeklyPlanResponse, WeeklyPlanListItem,
    GeneratePlanRequest, PlanItemUpdate, PlanFeedbackRequest, PlanItemResponse
)
from app.api.auth import get_current_user_required
from app.services.smart_plan_service import SmartPlanService

router = APIRouter(prefix="/smart-plan", tags=["智能计划"])


def _plan_to_response(plan: WeeklyPlan) -> WeeklyPlanResponse:
    items = [PlanItemResponse.model_validate(item) for item in plan.items]
    return WeeklyPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        week_start=plan.week_start,
        status=plan.status,
        focus_areas=plan.focus_areas or [],
        weekly_summary=plan.weekly_summary,
        completion_rate=plan.completion_rate,
        ai_model=plan.ai_model,
        user_feedback=plan.user_feedback,
        items=sorted(items, key=lambda x: (x.day_of_week, x.sort_order)),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post("/generate", response_model=WeeklyPlanResponse)
async def generate_plan(
    request: GeneratePlanRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """生成周计划（手动触发）"""
    service = SmartPlanService(db)
    try:
        plan = await service.generate_plan(current_user.id, request.target_week)
        return _plan_to_response(plan)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current", response_model=Optional[WeeklyPlanResponse])
async def get_current_plan(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前周计划"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == current_user.id,
        WeeklyPlan.week_start == week_start,
        WeeklyPlan.status.in_(["active", "draft"])
    ).first()

    if not plan:
        return None
    return _plan_to_response(plan)


@router.get("/history", response_model=List[WeeklyPlanListItem])
async def get_plan_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取历史计划列表"""
    plans = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == current_user.id
    ).order_by(WeeklyPlan.week_start.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    result = []
    for plan in plans:
        item_count = len(plan.items)
        completed_count = sum(1 for i in plan.items if i.is_completed)
        result.append(WeeklyPlanListItem(
            id=plan.id,
            week_start=plan.week_start,
            status=plan.status,
            focus_areas=plan.focus_areas or [],
            completion_rate=plan.completion_rate,
            user_feedback=plan.user_feedback,
            item_count=item_count,
            completed_count=completed_count,
            created_at=plan.created_at,
        ))
    return result


@router.get("/{plan_id}", response_model=WeeklyPlanResponse)
async def get_plan_detail(
    plan_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取计划详情"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    return _plan_to_response(plan)


@router.patch("/{plan_id}/items/{item_id}", response_model=PlanItemResponse)
async def update_plan_item(
    plan_id: int,
    item_id: int,
    update: PlanItemUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """手动标记计划项完成/取消"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    item = db.query(PlanItem).filter(
        PlanItem.id == item_id,
        PlanItem.plan_id == plan_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="计划项不存在")

    from datetime import datetime
    item.is_completed = update.is_completed
    item.completed_at = datetime.utcnow() if update.is_completed else None
    db.commit()

    # 更新完成率
    service = SmartPlanService(db)
    service.update_completion_rate(plan_id)

    db.refresh(item)
    return PlanItemResponse.model_validate(item)


@router.post("/{plan_id}/feedback")
async def submit_feedback(
    plan_id: int,
    feedback: PlanFeedbackRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """提交计划评分反馈"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    plan.user_feedback = feedback.score
    db.commit()
    return {"message": "反馈已提交", "score": feedback.score}


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除计划"""
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.id == plan_id,
        WeeklyPlan.user_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    db.delete(plan)
    db.commit()
    return {"message": "计划已删除"}
```

**Step 2: Register router in main.py**

Find the `include_router` section in `backend/app/api/main.py` and add:

```python
from app.api import smart_plan
# ...
api_router.include_router(smart_plan.router)
```

**Step 3: Commit**

```bash
git add backend/app/api/smart_plan.py backend/app/api/main.py
git commit -m "feat(smart-plan): add API router with CRUD + generate endpoints"
```

---

## Task 5: Checkin Linkage Hook

**Files:**
- Modify: `backend/app/api/checkin.py` — add hook after record creation (lines ~271 and ~320)

**Step 1: Add the hook function and call it**

After `db.commit()` in both `create_record` (line 271) and `quick_checkin` (around line 320), add a call to link the checkin to the smart plan:

```python
# Add this import at top of checkin.py
from app.models.smart_plan import WeeklyPlan, PlanItem

# Add this helper function
def _link_checkin_to_plan(db: Session, user_id: int, template_id: int, checkin_date: date):
    """打卡后自动标记关联的计划项为完成"""
    week_start = checkin_date - timedelta(days=checkin_date.weekday())
    plan = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == user_id,
        WeeklyPlan.week_start == week_start,
        WeeklyPlan.status.in_(["active", "draft"])
    ).first()
    if not plan:
        return

    day_of_week = checkin_date.isoweekday()  # 1=Mon ~ 7=Sun
    items = db.query(PlanItem).filter(
        PlanItem.plan_id == plan.id,
        PlanItem.checkin_template_id == template_id,
        PlanItem.day_of_week == day_of_week,
        PlanItem.is_completed == False
    ).all()

    if items:
        from datetime import datetime
        for item in items:
            item.is_completed = True
            item.completed_at = datetime.utcnow()
        db.commit()

        # 更新完成率
        from sqlalchemy import func
        total = db.query(func.count(PlanItem.id)).filter(PlanItem.plan_id == plan.id).scalar()
        completed = db.query(func.count(PlanItem.id)).filter(
            PlanItem.plan_id == plan.id, PlanItem.is_completed == True
        ).scalar()
        plan.completion_rate = round((completed / total * 100) if total > 0 else 0.0, 1)
        if plan.completion_rate >= 100:
            plan.status = "completed"
        db.commit()
```

Then in `create_record` after `db.commit()` (line 271), add:
```python
    # 联动智能计划
    _link_checkin_to_plan(db, current_user.id, record_data.template_id, record_data.checkin_date)
```

Similarly in `quick_checkin` after its `db.commit()`, add:
```python
    # 联动智能计划
    _link_checkin_to_plan(db, current_user.id, record_data.template_id, today)
```

**Step 2: Commit**

```bash
git add backend/app/api/checkin.py
git commit -m "feat(smart-plan): add checkin → plan item auto-completion hook"
```

---

## Task 6: Frontend API Service

**Files:**
- Modify: `frontend/src/services/api.ts` — add SmartPlan types and API methods

**Step 1: Add types and API methods**

Add after the existing `newsApi` section:

```typescript
// 智能计划 API
export interface PlanItem {
  id: number;
  day_of_week: number;
  category: string;
  title: string;
  description: string | null;
  target_value: number | null;
  target_unit: string | null;
  checkin_template_id: number | null;
  is_completed: boolean;
  completed_at: string | null;
  sort_order: number;
}

export interface WeeklyPlan {
  id: number;
  user_id: number;
  week_start: string;
  status: string;
  focus_areas: string[];
  weekly_summary: string | null;
  completion_rate: number;
  ai_model: string | null;
  user_feedback: number | null;
  items: PlanItem[];
  created_at: string;
  updated_at: string | null;
}

export interface WeeklyPlanListItem {
  id: number;
  week_start: string;
  status: string;
  focus_areas: string[];
  completion_rate: number;
  user_feedback: number | null;
  item_count: number;
  completed_count: number;
  created_at: string;
}

export const smartPlanApi = {
  generate: (targetWeek: string = 'current') =>
    api.post<WeeklyPlan>('/smart-plan/generate', { target_week: targetWeek }),

  getCurrent: () =>
    api.get<WeeklyPlan | null>('/smart-plan/current'),

  getHistory: (page: number = 1, pageSize: number = 10) =>
    api.get<WeeklyPlanListItem[]>('/smart-plan/history', { params: { page, page_size: pageSize } }),

  getDetail: (planId: number) =>
    api.get<WeeklyPlan>(`/smart-plan/${planId}`),

  updateItem: (planId: number, itemId: number, isCompleted: boolean) =>
    api.patch<PlanItem>(`/smart-plan/${planId}/items/${itemId}`, { is_completed: isCompleted }),

  submitFeedback: (planId: number, score: number) =>
    api.post(`/smart-plan/${planId}/feedback`, { score }),

  deletePlan: (planId: number) =>
    api.delete(`/smart-plan/${planId}`),
};
```

**Step 2: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(smart-plan): add frontend API types and service methods"
```

---

## Task 7: Frontend Page — `/smart-plan`

**Files:**
- Create: `frontend/src/app/smart-plan/page.tsx`

This is the main smart plan page with day-by-day view, progress bar, and plan item cards. Follow the existing page pattern (dark theme, Tailwind, React Query, lucide-react icons).

Key UI elements:
- Header with plan title, date range, completion progress bar, regenerate button
- Feed tabs for days of week (一~日), active day highlighted, completed days with ✓
- Plan items grouped by category (exercise/diet/rest/habit), checkbox for completion
- Items linked to checkin show "已打卡" badge
- Empty state with "生成我的第一份计划" button
- Loading state during generation (AI takes ~10-20s)
- Weekly summary at bottom (AI coach comment)

Import pattern:
```typescript
'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { smartPlanApi, WeeklyPlan, PlanItem } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { Brain, Check, RefreshCw, Dumbbell, Utensils, Moon, Heart, Star, ... } from 'lucide-react';
```

**Step 1: Create the page** (full implementation ~300 lines)

**Step 2: Commit**

```bash
git add frontend/src/app/smart-plan/page.tsx
git commit -m "feat(smart-plan): add frontend smart plan page with day-by-day view"
```

---

## Task 8: Navigation Entry

**Files:**
- Modify: Navigation component (find where nav links are defined, likely in layout or a shared nav component)
- Add "智能计划" entry with Brain icon pointing to `/smart-plan`

**Step 1: Find and modify navigation**

Search for existing nav entries (e.g., "资讯", "健康报告") and add the smart plan entry nearby.

**Step 2: Commit**

```bash
git commit -m "feat(smart-plan): add navigation entry for smart plan page"
```

---

## Task 9: Deploy and Verify

**Step 1: Push code**

```bash
git push
```

**Step 2: Run database migration on server**

```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && source venv/bin/activate && python -c \"
from app.database import engine, Base
from app.models.smart_plan import WeeklyPlan, PlanItem
Base.metadata.create_all(bind=engine)
print('Smart plan tables created')
\""
```

**Step 3: Deploy**

```bash
./deploy.sh -a
```

**Step 4: Verify**

- Visit `/smart-plan` on the frontend
- Click "生成计划" to trigger plan generation
- Verify plan items appear grouped by day
- Do a checkin and verify the linked plan item auto-completes
- Check the progress bar updates

---

## Task 10 (Future): Celery Scheduled Generation

**Files:**
- Create: `backend/app/tasks/smart_plan.py`

This is deferred to a follow-up iteration. When implemented:
- Add a weekly Celery beat task for Sunday 20:00 CST
- Query all active users with recent data
- Call `SmartPlanService.generate_plan(user_id, "next")` for each
- Set status to "draft" instead of "active"

---

## Summary

| Task | Files | Estimated Effort |
|------|-------|-----------------|
| 1. DB Models | `models/smart_plan.py` | Small |
| 2. Schemas | `schemas/smart_plan.py` | Small |
| 3. Service (LLM) | `services/smart_plan_service.py` | Large |
| 4. API Router | `api/smart_plan.py` + `main.py` | Medium |
| 5. Checkin Hook | `api/checkin.py` | Small |
| 6. Frontend API | `services/api.ts` | Small |
| 7. Frontend Page | `app/smart-plan/page.tsx` | Large |
| 8. Navigation | Layout/nav component | Small |
| 9. Deploy | Server migration + deploy | Small |
| 10. Celery (future) | `tasks/smart_plan.py` | Medium |
