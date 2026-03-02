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
        """
        # Step 1: Sync Garmin data
        sync_result = await self._sync_garmin(user_id)
        logger.info(f"[跑后分析] Garmin同步: {sync_result}")

        # Step 2: Find latest workout
        workout = self._find_latest_workout(user_id, workout_type)
        if not workout:
            return {
                "success": False,
                "message": "未检测到最近的运动记录。请确认 Garmin 手表已结束运动并完成数据上传。"
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
        """同步 Garmin 全量数据：运动记录 + 当日健康数据（步数、心率、压力等）"""
        import asyncio
        from app.services.auth import GarminCredentialService
        from app.services.workout_sync import WorkoutSyncService
        from app.services.data_collection.garmin_connect import GarminConnectService

        cred_service = GarminCredentialService()
        credentials = cred_service.get_decrypted_credentials(self.db, user_id)
        if not credentials:
            return {"status": "no_credentials", "synced_count": 0}

        email = credentials["email"]
        password = credentials["password"]
        is_cn = credentials.get("is_cn", False)

        # === Part 1: 同步运动记录（WorkoutRecord）===
        workout_synced = 0
        last_error = None
        for attempt in range(1, MAX_GARMIN_SYNC_RETRIES + 1):
            try:
                sync_service = WorkoutSyncService(
                    email=email, password=password, is_cn=is_cn, user_id=user_id,
                )
                result = await sync_service.sync_activities(self.db, user_id, days=1)
                workout_synced = result.get("synced_count", 0)
                if workout_synced > 0:
                    break
                # synced_count=0 可能是数据库已有记录，检查DB中是否已有近期运动
                existing = self._find_latest_workout(user_id)
                if existing:
                    logger.info(f"[跑后分析] 数据库已有近期运动记录(id={existing.id})，跳过重试")
                    break
                if attempt < MAX_GARMIN_SYNC_RETRIES:
                    logger.info(f"[跑后分析] Garmin无新运动数据, 等待重试 ({attempt}/{MAX_GARMIN_SYNC_RETRIES})")
                    await asyncio.sleep(GARMIN_SYNC_INTERVAL_SECONDS)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[跑后分析] Garmin运动同步异常 ({attempt}): {e}")
                if attempt < MAX_GARMIN_SYNC_RETRIES:
                    await asyncio.sleep(GARMIN_SYNC_INTERVAL_SECONDS)

        # === Part 2: 同步当日健康数据（GarminData: 步数、静息心率、压力、Body Battery等）===
        daily_synced = False
        today = get_china_today()
        try:
            garmin_service = GarminConnectService(
                email=email, password=password, is_cn=is_cn, user_id=user_id,
            )
            garmin_data = await asyncio.to_thread(
                garmin_service.sync_daily_data, self.db, user_id, today
            )
            if garmin_data:
                daily_synced = True
                logger.info(f"[跑后分析] 当日健康数据同步成功: 步数={garmin_data.steps}, 静息心率={garmin_data.resting_heart_rate}")
        except Exception as e:
            logger.warning(f"[跑后分析] 当日健康数据同步失败: {e}")

        if workout_synced > 0 or daily_synced:
            return {
                "status": "synced",
                "synced_count": workout_synced,
                "daily_synced": daily_synced,
            }
        return {"status": "no_new_data", "synced_count": 0, "daily_synced": False, "error": last_error}

    def _find_latest_workout(self, user_id: int, workout_type: Optional[str] = None) -> Optional[WorkoutRecord]:
        """查找最近的运动记录（今天或昨天）"""
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
            if profile.birth_date:
                from datetime import date as _date
                age = (_date.today() - profile.birth_date).days // 365
                if age > 0:
                    parts.append(f"{age}岁")
            if profile.current_weight_kg:
                parts.append(f"体重{profile.current_weight_kg}kg")
            profile_str = "、".join(parts)

        # Today's Garmin daily data (freshly synced: steps, resting HR, body battery, stress, sleep)
        resting_hr = None
        daily_health_str = ""
        latest_garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id
        ).order_by(GarminData.record_date.desc()).first()
        if latest_garmin:
            resting_hr = latest_garmin.resting_heart_rate
            daily_parts = []
            if latest_garmin.steps:
                daily_parts.append(f"今日步数{latest_garmin.steps}")
            if latest_garmin.resting_heart_rate:
                daily_parts.append(f"静息心率{latest_garmin.resting_heart_rate}")
            if latest_garmin.body_battery_current:
                daily_parts.append(f"Body Battery当前{latest_garmin.body_battery_current}")
            if latest_garmin.stress_level:
                daily_parts.append(f"压力指数{latest_garmin.stress_level}")
            if latest_garmin.sleep_score:
                daily_parts.append(f"昨晚睡眠评分{latest_garmin.sleep_score}")
            if latest_garmin.total_sleep_duration:
                sleep_hours = round(latest_garmin.total_sleep_duration / 3600, 1)
                daily_parts.append(f"睡眠时长{sleep_hours}小时")
            if latest_garmin.hrv:
                daily_parts.append(f"HRV {latest_garmin.hrv}ms")
            if daily_parts:
                daily_health_str = "、".join(daily_parts)

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
            workout_section += f"\n- 心率区间：热身{z.get('warmup', 0)}% | 燃脂{z.get('fat_burn', 0)}% | 有氧{z.get('aerobic', 0)}% | 无氧{z.get('anaerobic', 0)}% | 极限{z.get('max', 0)}%"
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

        if daily_health_str:
            prompt += f"\n\n【当日身体状态】\n{daily_health_str}"

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
        if len(aggregation) > 500:
            aggregation = aggregation[:497] + "..."

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
