# Post-Workout Analysis (跑后智能分析) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a user finishes a workout and says "我跑完了" (via chat, quick button, or Siri), automatically sync Garmin data, find the latest workout, run multi-model AI analysis via OpenClaw, and return a comprehensive training report.

**Architecture:** Three trigger surfaces (chat action, quick button, Siri endpoint) share a single backend `PostRunAnalyzeService` that orchestrates: Garmin sync → workout detection → OpenClaw multi-model analysis → formatted response. The chat integration uses the existing `<<<ACTIONS>>>` marker system.

**Tech Stack:** FastAPI, SQLAlchemy, httpx (async), OpenClaw Analyze API, existing GarminConnectService/WorkoutSyncService, Next.js React frontend

---

## Task 1: OpenClaw Analyze Client

Create a reusable client for OpenClaw's multi-model analyze API (submit + poll).

**Files:**
- Create: `backend/app/services/openclaw_analyze.py`

**Step 1: Create the OpenClaw analyze client**

```python
"""OpenClaw 多模型分析客户端"""
import asyncio
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

OPENCLAW_ANALYZE_URL = "https://base.executor.life/api/openclaw/analyze"
OPENCLAW_STATUS_URL = "https://base.executor.life/api/openclaw/status"
OPENCLAW_ANALYZE_API_KEY = "oc-kuaishou-2026"
OPENCLAW_KIM_USER_ID = "baokun"

POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 6  # 60 seconds max


class OpenClawAnalyzeClient:
    """OpenClaw 多模型分析客户端：提交 prompt → 轮询结果"""

    async def analyze(self, prompt: str) -> Dict[str, Any]:
        """
        提交分析并轮询结果。

        Returns:
            {
                "status": "completed" | "partial" | "timeout" | "error",
                "model_results": [...],  # 各模型分析结果
                "aggregation": "..."     # 综合汇总
            }
        """
        batch_id = await self._submit(prompt)
        if not batch_id:
            return {"status": "error", "model_results": [], "aggregation": "提交分析失败"}

        return await self._poll(batch_id)

    async def _submit(self, prompt: str) -> Optional[str]:
        """提交分析请求，返回 batch_id"""
        payload = {
            "prompt": prompt,
            "kim_user_id": OPENCLAW_KIM_USER_ID,
            "api_key": OPENCLAW_ANALYZE_API_KEY,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(OPENCLAW_ANALYZE_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("ok"):
                    batch_id = data.get("batch_id")
                    logger.info(f"[OpenClaw分析] 提交成功: batch_id={batch_id}")
                    return batch_id
                else:
                    logger.error(f"[OpenClaw分析] 提交失败: {data}")
                    return None
        except Exception as e:
            logger.error(f"[OpenClaw分析] 提交异常: {e}")
            return None

    async def _poll(self, batch_id: str) -> Dict[str, Any]:
        """轮询分析结果"""
        url = f"{OPENCLAW_STATUS_URL}/{batch_id}"
        for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                status = data.get("status", "")
                logger.info(f"[OpenClaw分析] 轮询 {attempt}/{MAX_POLL_ATTEMPTS}: status={status}")

                if status in ("completed", "partial"):
                    return {
                        "status": status,
                        "model_results": data.get("model_results", []),
                        "aggregation": data.get("aggregation", ""),
                    }
                # pending / processing → continue
            except Exception as e:
                logger.warning(f"[OpenClaw分析] 轮询异常 ({attempt}): {e}")

        return {
            "status": "timeout",
            "model_results": [],
            "aggregation": "分析超时，请稍后在运动记录中查看结果。",
        }
```

**Step 2: Verify the file is syntactically correct**

Run: `cd /Users/liqiuhua/work/personal/health-llm-driven/backend && python -c "import ast; ast.parse(open('app/services/openclaw_analyze.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/app/services/openclaw_analyze.py
git commit -m "feat: add OpenClaw multi-model analyze client"
```

---

## Task 2: PostRunAnalyzeService

Core orchestration: sync Garmin → detect workout → build prompt → call OpenClaw → format result.

**Files:**
- Create: `backend/app/services/post_run_analyze.py`

**Step 1: Create the service**

```python
"""跑后智能分析服务：Garmin同步 → 检测最新运动 → 多模型分析"""
import json
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models.daily_health import WorkoutRecord, GarminData
from app.models.user_profile import UserProfile
from app.services.openclaw_analyze import OpenClawAnalyzeClient
from app.utils.timezone import get_china_now, get_china_today

logger = logging.getLogger(__name__)

MAX_GARMIN_SYNC_RETRIES = 3
GARMIN_SYNC_INTERVAL_SECONDS = 10


class PostRunAnalyzeService:
    """跑后分析服务"""

    def __init__(self, db: Session):
        self.db = db
        self.openclaw = OpenClawAnalyzeClient()

    async def analyze(
        self,
        user_id: int,
        workout_type: Optional[str] = None,
        format: str = "full",
    ) -> Dict[str, Any]:
        """
        完整流程：同步 → 检测 → 分析 → 返回

        Args:
            user_id: 用户ID
            workout_type: 可选运动类型过滤
            format: "full" 完整报告 | "brief" 简洁摘要

        Returns:
            分析结果字典
        """
        # Step 1: Sync Garmin data
        sync_result = await self._sync_garmin(user_id)
        logger.info(f"[跑后分析] Garmin同步: {sync_result}")

        # Step 2: Find latest workout
        workout = self._find_latest_workout(user_id, workout_type)
        if not workout:
            return {
                "success": False,
                "message": "未检测到最近2小时内的运动记录。请确认 Garmin 手表已结束运动并完成数据上传。"
            }

        # Step 3: Build workout data summary
        workout_data = self._build_workout_data(workout)

        # Step 4: Build analysis prompt
        prompt = self._build_prompt(user_id, workout, workout_data)

        # Step 5: Call OpenClaw multi-model analysis
        analysis = await self.openclaw.analyze(prompt)

        # Step 6: Format response
        if format == "brief":
            return self._format_brief(workout_data, analysis)
        return self._format_full(workout_data, analysis)

    async def _sync_garmin(self, user_id: int) -> Dict[str, Any]:
        """同步 Garmin 运动数据（缓存token登录，最多重试3次）"""
        import asyncio
        from app.services.auth import GarminCredentialService
        from app.services.workout_sync import WorkoutSyncService

        cred_service = GarminCredentialService()
        credentials = cred_service.get_decrypted_credentials(self.db, user_id)
        if not credentials:
            return {"status": "no_credentials", "synced_count": 0}

        last_error = None
        for attempt in range(1, MAX_GARMIN_SYNC_RETRIES + 1):
            try:
                sync_service = WorkoutSyncService(
                    email=credentials["email"],
                    password=credentials["password"],
                    is_cn=credentials.get("is_cn", False),
                    user_id=user_id,
                )
                result = await sync_service.sync_activities(self.db, user_id, days=1)
                if result.get("synced_count", 0) > 0:
                    return {"status": "synced", "synced_count": result["synced_count"]}
                # No new data yet, wait and retry
                if attempt < MAX_GARMIN_SYNC_RETRIES:
                    logger.info(f"[跑后分析] Garmin无新数据, 等待重试 ({attempt}/{MAX_GARMIN_SYNC_RETRIES})")
                    await asyncio.sleep(GARMIN_SYNC_INTERVAL_SECONDS)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[跑后分析] Garmin同步异常 ({attempt}): {e}")
                if attempt < MAX_GARMIN_SYNC_RETRIES:
                    await asyncio.sleep(GARMIN_SYNC_INTERVAL_SECONDS)

        return {"status": "no_new_data", "synced_count": 0, "error": last_error}

    def _find_latest_workout(self, user_id: int, workout_type: Optional[str] = None) -> Optional[WorkoutRecord]:
        """查找最近2小时内的最新运动记录"""
        today = get_china_today()
        yesterday = today - timedelta(days=1)

        query = self.db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= yesterday,
        )
        if workout_type and workout_type != "other":
            query = query.filter(WorkoutRecord.workout_type == workout_type)

        workout = query.order_by(
            WorkoutRecord.workout_date.desc(),
            WorkoutRecord.start_time.desc()
        ).first()

        return workout

    def _build_workout_data(self, workout: WorkoutRecord) -> Dict[str, Any]:
        """构建结构化运动数据"""
        distance_km = round(workout.distance_meters / 1000, 2) if workout.distance_meters else None
        duration_min = round(workout.duration_seconds / 60, 1) if workout.duration_seconds else None

        pace_display = None
        if workout.avg_pace_seconds_per_km:
            m = workout.avg_pace_seconds_per_km // 60
            s = workout.avg_pace_seconds_per_km % 60
            pace_display = f"{m}'{s:02d}\""

        # HR zone percentages
        hr_zones = {}
        zone_secs = [
            workout.hr_zone_1_seconds or 0,
            workout.hr_zone_2_seconds or 0,
            workout.hr_zone_3_seconds or 0,
            workout.hr_zone_4_seconds or 0,
            workout.hr_zone_5_seconds or 0,
        ]
        total_zone = sum(zone_secs)
        if total_zone > 0:
            hr_zones = {
                "warmup": round(zone_secs[0] / total_zone * 100),
                "fat_burn": round(zone_secs[1] / total_zone * 100),
                "aerobic": round(zone_secs[2] / total_zone * 100),
                "anaerobic": round(zone_secs[3] / total_zone * 100),
                "max": round(zone_secs[4] / total_zone * 100),
            }

        return {
            "workout_id": workout.id,
            "type": workout.workout_type,
            "name": workout.workout_name,
            "date": str(workout.workout_date),
            "distance_km": distance_km,
            "duration_min": duration_min,
            "pace": pace_display,
            "avg_hr": workout.avg_heart_rate,
            "max_hr": workout.max_heart_rate,
            "hr_zones": hr_zones,
            "training_effect_aerobic": workout.training_effect_aerobic,
            "training_effect_anaerobic": workout.training_effect_anaerobic,
            "calories": workout.calories,
            "elevation_gain": workout.elevation_gain_meters,
            "steps": workout.steps,
            "avg_cadence": workout.avg_cadence,
        }

    def _build_prompt(self, user_id: int, workout: WorkoutRecord, data: Dict[str, Any]) -> str:
        """构建多模型分析的 prompt"""
        # User profile
        profile = self.db.query(UserProfile).filter_by(user_id=user_id).first()
        profile_str = ""
        if profile:
            parts = []
            if profile.gender:
                parts.append(f"{'男' if profile.gender == 'male' else '女'}")
            if profile.age:
                parts.append(f"{profile.age}岁")
            if profile.weight:
                parts.append(f"体重{profile.weight}kg")
            profile_str = "、".join(parts)

        # Resting HR from latest Garmin data
        resting_hr = None
        latest_garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id
        ).order_by(GarminData.record_date.desc()).first()
        if latest_garmin:
            resting_hr = latest_garmin.resting_heart_rate

        # Recent workout history (same type, last 30 days)
        history_records = self.db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_type == workout.workout_type,
            WorkoutRecord.id != workout.id,
            WorkoutRecord.workout_date >= get_china_today() - timedelta(days=30),
        ).order_by(WorkoutRecord.workout_date.desc()).limit(5).all()

        history_str = ""
        if history_records:
            lines = []
            for h in history_records:
                d_km = round(h.distance_meters / 1000, 2) if h.distance_meters else "?"
                d_min = round(h.duration_seconds / 60, 1) if h.duration_seconds else "?"
                pace = ""
                if h.avg_pace_seconds_per_km:
                    pm, ps = divmod(h.avg_pace_seconds_per_km, 60)
                    pace = f" 配速{pm}'{ps:02d}\""
                lines.append(f"  - {h.workout_date}: {d_km}km / {d_min}分钟{pace}")
            history_str = "\n".join(lines)

        # Build the prompt
        workout_section = f"""【本次运动】
- 类型：{data.get('name') or data.get('type', '未知')}
- 日期：{data['date']}"""

        if data.get("distance_km"):
            workout_section += f"\n- 距离：{data['distance_km']}km"
        if data.get("duration_min"):
            workout_section += f"\n- 时长：{data['duration_min']}分钟"
        if data.get("pace"):
            workout_section += f"\n- 配速：{data['pace']}/km"
        if data.get("avg_hr"):
            workout_section += f"\n- 心率：平均{data['avg_hr']}"
            if data.get("max_hr"):
                workout_section += f" / 最大{data['max_hr']}"
            if resting_hr:
                workout_section += f" / 静息{resting_hr}"
        if data.get("hr_zones"):
            z = data["hr_zones"]
            workout_section += f"\n- 心率区间：热身{z.get('warmup',0)}% | 燃脂{z.get('fat_burn',0)}% | 有氧{z.get('aerobic',0)}% | 无氧{z.get('anaerobic',0)}% | 极限{z.get('max',0)}%"
        if data.get("training_effect_aerobic"):
            workout_section += f"\n- 训练效果：有氧{data['training_effect_aerobic']}"
            if data.get("training_effect_anaerobic"):
                workout_section += f" / 无氧{data['training_effect_anaerobic']}"
        if data.get("calories"):
            workout_section += f"\n- 消耗：{data['calories']}大卡"
        if data.get("elevation_gain"):
            workout_section += f"\n- 爬升：{data['elevation_gain']}米"
        if data.get("avg_cadence"):
            workout_section += f"\n- 步频：{data['avg_cadence']}步/分"

        prompt = f"""你是运动科学专家。请分析以下运动数据并给出专业指导。

{workout_section}"""

        if history_str:
            prompt += f"\n\n【近30天同类运动历史】\n{history_str}"

        if profile_str:
            prompt += f"\n\n【用户画像】\n{profile_str}"
            if resting_hr:
                prompt += f"，静息心率{resting_hr}"

        prompt += """

请输出以下内容（用中文）：
1. **本次训练总结**：表现评价，与历史对比
2. **心率区间分析**：分布是否合理，训练效果评估
3. **跑后拉伸方案**：具体动作名称 + 每个动作持续时间，针对本次运动类型定制（至少5个动作）
4. **恢复建议**：营养补充、水分、休息安排
5. **下次训练建议**：建议时间间隔、强度、运动类型"""

        return prompt

    def _format_full(self, workout_data: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """格式化完整报告"""
        return {
            "success": True,
            "format": "full",
            "workout": workout_data,
            "multi_model_analysis": {
                "status": analysis.get("status"),
                "model_results": analysis.get("model_results", []),
                "aggregation": analysis.get("aggregation", ""),
            },
        }

    def _format_brief(self, workout_data: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """格式化简洁摘要（Siri 用）"""
        aggregation = analysis.get("aggregation", "")
        # Truncate for Siri display
        if len(aggregation) > 500:
            aggregation = aggregation[:497] + "..."

        # Build a one-line workout summary
        parts = []
        if workout_data.get("distance_km"):
            parts.append(f"{workout_data['distance_km']}km")
        if workout_data.get("duration_min"):
            parts.append(f"{workout_data['duration_min']}分钟")
        if workout_data.get("pace"):
            parts.append(f"配速{workout_data['pace']}")
        workout_summary = " | ".join(parts) if parts else workout_data.get("type", "运动")

        return {
            "success": True,
            "format": "brief",
            "summary": f"本次{workout_data.get('name') or workout_data.get('type', '运动')}：{workout_summary}\n\n{aggregation}",
        }
```

**Step 2: Verify syntax**

Run: `cd /Users/liqiuhua/work/personal/health-llm-driven/backend && python -c "import ast; ast.parse(open('app/services/post_run_analyze.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/app/services/post_run_analyze.py
git commit -m "feat: add PostRunAnalyzeService orchestration"
```

---

## Task 3: REST Endpoint

Add `POST /api/v1/workout/post-run-analyze` with dual auth (JWT + API Key for Siri).

**Files:**
- Modify: `backend/app/api/workout.py` (append at end of file)

**Step 1: Add the endpoint**

Add the following at the end of `backend/app/api/workout.py`, before no other code:

```python
# ========== 跑后智能分析（多模型）==========

@router.post("/post-run-analyze")
async def post_run_analyze(
    format: str = Query(default="full", regex="^(full|brief)$", description="full=完整报告 brief=Siri简洁摘要"),
    workout_type: Optional[str] = Query(default=None, description="运动类型过滤，如 running/cycling"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    跑后智能分析：同步Garmin → 检测最新运动 → OpenClaw多模型分析

    支持三种触发方式：
    1. AI助手对话（通过 action 系统）
    2. AI助手快捷按钮（前端直接调用）
    3. Siri快捷指令（format=brief，使用 X-API-Key 认证）
    """
    from app.services.post_run_analyze import PostRunAnalyzeService

    service = PostRunAnalyzeService(db)
    try:
        result = await service.analyze(
            user_id=current_user.id,
            workout_type=workout_type,
            format=format,
        )
        return result
    except Exception as e:
        logger.error(f"跑后分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")
```

Also add a Siri-compatible version that uses the dual auth pattern from `health_event.py`:

```python
@router.post("/post-run-analyze-siri")
async def post_run_analyze_siri(
    request: Request,
    format: str = Query(default="brief"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Siri 快捷指令专用端点，支持 X-API-Key 认证"""
    from app.api.health_event import get_user_id_from_any_auth

    user_id = await get_user_id_from_any_auth(request, x_api_key, current_user, db)

    from app.services.post_run_analyze import PostRunAnalyzeService
    service = PostRunAnalyzeService(db)
    try:
        result = await service.analyze(user_id=user_id, format="brief")
        return result
    except Exception as e:
        logger.error(f"Siri跑后分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")
```

Add this import at the top of the file (near existing imports):

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status, Header, Request
```

**Step 2: Verify imports compile**

Run: `cd /Users/liqiuhua/work/personal/health-llm-driven/backend && python -c "import ast; ast.parse(open('app/api/workout.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/app/api/workout.py
git commit -m "feat: add post-run-analyze REST endpoints (JWT + Siri API Key)"
```

---

## Task 4: Chat Action Integration

Add `workout_analyze` action to the system prompt and handler in `chat_service.py`.

**Files:**
- Modify: `backend/app/services/chat_service.py`

**Step 1: Add workout_analyze to the system prompt**

In `_get_system_prompt()` (around line 1127, after the `create_plan_prompt` block and before `health_ctx`), insert:

```python
        # 运动完成分析功能
        workout_analyze_prompt = (
            "\n\n## 运动完成分析功能\n"
            "当用户表达运动/跑步/锻炼/训练完成的意图时，帮助用户同步数据并分析。\n\n"
            "### 触发条件\n"
            "用户说「跑完了」「运动结束」「锻炼完了」「训练结束了」「刚跑完步」"
            "「帮我分析刚才的运动」「同步一下运动数据」等表达已完成运动的意图时触发。\n\n"
            "### 格式\n"
            "在正常回复之后附加（用户不可见）：\n"
            '<<<ACTIONS:[{"type":"workout_analyze","workout_type":"运动类型"}]>>>\n\n'
            "### 规则\n"
            "1. workout_type 根据用户描述判断：running/cycling/swimming/hiit/strength/yoga/other\n"
            "2. 如用户未明确运动类型，使用 \"other\"，系统会自动检测最新记录的类型\n"
            "3. 触发后在回复中告知用户：「正在同步 Garmin 数据并分析你的运动，请稍等...」\n"
            "4. 只在用户表达**已完成**运动时触发，计划运动或询问不触发\n\n"
            "### 示例\n"
            "- \"我跑完了\" → workout_analyze, workout_type=\"running\"\n"
            "- \"刚骑完车\" → workout_analyze, workout_type=\"cycling\"\n"
            "- \"锻炼结束了，帮我看看数据\" → workout_analyze, workout_type=\"other\"\n"
            "- \"游泳完了，同步一下\" → workout_analyze, workout_type=\"swimming\"\n"
        )
```

Then update the prompt assembly line (currently line ~1130):

From:
```python
        prompt = base + activity_prompt + create_plan_prompt
```
To:
```python
        prompt = base + activity_prompt + create_plan_prompt + workout_analyze_prompt
```

**Step 2: Add handler in `_execute_actions`**

Currently `_execute_actions` is synchronous. The `workout_analyze` action needs async (like `create_plan`).

In `send_message()` (around line 1631-1640), add workout_analyze alongside create_plan as an async action:

From:
```python
            plan_actions = [a for a in actions if a.get("type") == "create_plan"]
            other_actions = [a for a in actions if a.get("type") != "create_plan"]
```
To:
```python
            plan_actions = [a for a in actions if a.get("type") == "create_plan"]
            workout_actions = [a for a in actions if a.get("type") == "workout_analyze"]
            other_actions = [a for a in actions if a.get("type") not in ("create_plan", "workout_analyze")]
```

And after the plan_actions handling block, add:

```python
            for wa in workout_actions:
                workout_result = await self._handle_workout_analyze_action(user_id, wa)
                if workout_result:
                    activity_results.append(workout_result)
```

**Step 3: Implement the handler method**

Add this method to the `ChatService` class (after `_handle_create_plan_async`):

```python
    async def _handle_workout_analyze_action(self, user_id: int, action: dict) -> Optional[Dict]:
        """处理运动完成分析 action：同步Garmin → 检测运动 → 多模型分析"""
        workout_type = action.get("workout_type", "other")
        try:
            from app.services.post_run_analyze import PostRunAnalyzeService
            service = PostRunAnalyzeService(self.db)
            result = await service.analyze(
                user_id=user_id,
                workout_type=workout_type if workout_type != "other" else None,
                format="full",
            )
            if not result.get("success"):
                return {
                    "type": "workout_analyze",
                    "status": "no_data",
                    "message": result.get("message", "未检测到运动记录"),
                }

            # Format the analysis as chat-friendly text
            workout = result.get("workout", {})
            analysis = result.get("multi_model_analysis", {})
            aggregation = analysis.get("aggregation", "")

            # Build workout summary line
            parts = []
            if workout.get("name"):
                parts.append(workout["name"])
            if workout.get("distance_km"):
                parts.append(f"{workout['distance_km']}km")
            if workout.get("duration_min"):
                parts.append(f"{workout['duration_min']}分钟")
            if workout.get("pace"):
                parts.append(f"配速{workout['pace']}")
            workout_line = " | ".join(parts)

            # Build model insights (show individual model highlights if available)
            model_insights = ""
            model_results = analysis.get("model_results", [])
            if model_results:
                insights = []
                for mr in model_results:
                    site = mr.get("site", "")
                    content = mr.get("content", "")
                    # Extract model display name
                    display_name = site.replace("lb-", "").replace("-", " ").title()
                    if content:
                        # Take first 200 chars as insight preview
                        preview = content[:200] + "..." if len(content) > 200 else content
                        insights.append(f"**{display_name}**:\n{preview}")
                if insights:
                    model_insights = "\n\n---\n\n".join(insights)

            analysis_text = ""
            if aggregation:
                analysis_text = f"\n\n**综合分析：**\n{aggregation}"
            if model_insights:
                analysis_text += f"\n\n**各模型视角：**\n\n{model_insights}"

            return {
                "type": "workout_analyze",
                "status": "analyzed",
                "message": f"🏃 运动分析完成：{workout_line}{analysis_text}",
                "workout_data": workout,
            }
        except Exception as e:
            logger.error(f"运动分析 action 处理失败: {e}", exc_info=True)
            return {
                "type": "workout_analyze",
                "status": "error",
                "message": f"运动分析失败: {str(e)}",
            }
```

**Step 4: Verify syntax**

Run: `cd /Users/liqiuhua/work/personal/health-llm-driven/backend && python -c "import ast; ast.parse(open('app/services/chat_service.py').read()); print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add backend/app/services/chat_service.py
git commit -m "feat: integrate workout_analyze action into chat service"
```

---

## Task 5: Frontend Quick Button

Add "运动完成" quick action button to the AI assistant page.

**Files:**
- Modify: `frontend/src/app/ai-assistant/page.tsx`

**Step 1: Add the quick question**

In `QUICK_QUESTIONS` array (line 17-22), add:

```typescript
const QUICK_QUESTIONS = [
  { label: '分析打卡', text: '请分析一下我今天的打卡完成情况，给出建议' },
  { label: '运动建议', text: '根据我的身体数据，今天适合做什么运动？' },
  { label: '睡眠分析', text: '帮我分析一下最近的睡眠质量，有什么改善建议？' },
  { label: '饮食建议', text: '根据我的健康目标，今天的饮食应该注意什么？' },
  { label: '运动完成', text: '我刚运动完，帮我同步Garmin数据并分析本次训练，给出拉伸和恢复建议' },
];
```

**Step 2: Verify frontend compiles**

Run: `cd /Users/liqiuhua/work/personal/health-llm-driven/frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/app/ai-assistant/page.tsx
git commit -m "feat: add '运动完成' quick action button to AI assistant"
```

---

## Task 6: End-to-end test via deploy

Deploy and verify the full flow works.

**Step 1: Deploy backend**

Run: `./deploy.sh -b`

**Step 2: Deploy frontend**

Run: `./deploy.sh -f`

**Step 3: Test the REST endpoint**

Run (replace token with a valid JWT):
```bash
curl -X POST "https://health-api.executor.life/api/v1/workout/post-run-analyze?format=brief" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

**Step 4: Test via AI assistant**

Open the health app → AI 助手 → click "运动完成" button or type "我跑完了"
Verify: Garmin sync happens, workout is found, multi-model analysis returns in chat.

**Step 5: Commit any fixes**

If any issues found during testing, fix and commit.
