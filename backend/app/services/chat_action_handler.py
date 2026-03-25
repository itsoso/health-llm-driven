import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, Dict

from sqlalchemy.orm import Session

from app.models.checkin import CheckinRecord, CheckinTemplate
from app.models.daily_health import WaterIntake, DietRecord
from app.models.health_checkin import HealthCheckin
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.illness import IllnessEpisode, IllnessUpdate
from app.models.excretion import ExcretionRecord
from app.models.sleep_record import SleepRecord
from app.models.activity_status import ActivityStatus
from app.models.vocabulary import VocabularyWord

logger = logging.getLogger(__name__)


class ChatActionHandler:
    """从 AI 回复中解析并执行健康活动 actions"""

    def __init__(self, db: Session):
        self.db = db

    def parse_actions(self, reply: str) -> tuple:
        """从AI回复中解析活动标记，返回 (clean_reply, actions_list)"""
        pattern = r'<<<ACTIONS:\s*(\[[\s\S]*?\])\s*>>>'
        match = re.search(pattern, reply)
        if not match:
            return reply, []
        clean_reply = reply[:match.start()].rstrip()
        try:
            actions = json.loads(match.group(1))
            if not isinstance(actions, list):
                return clean_reply, []
            return clean_reply, actions
        except json.JSONDecodeError as e:
            logger.warning(f"解析活动JSON失败: {e}")
            return clean_reply, []

    def execute_actions(self, user_id: int, actions: list) -> list:
        """执行检测到的活动并返回结果列表"""
        results = []
        today = date.today()
        now = datetime.now()
        for action in actions:
            action_type = action.get("type")
            try:
                if action_type == "checkin":
                    result = self._handle_checkin_action(user_id, action, today)
                elif action_type == "water":
                    result = self._handle_water_action(user_id, action, today, now)
                elif action_type == "supplement":
                    result = self._handle_supplement_action(user_id, action, today)
                elif action_type == "symptom":
                    result = self._handle_symptom_action(user_id, action, today)
                elif action_type == "rhinitis":
                    result = self._handle_rhinitis_action(user_id, action, today)
                elif action_type == "illness_create":
                    result = self._handle_illness_create(user_id, action, today)
                elif action_type == "illness_update":
                    result = self._handle_illness_update(user_id, action, today)
                elif action_type == "excretion":
                    result = self._handle_excretion_action(user_id, action, today, now)
                elif action_type == "sleep":
                    result = self._handle_sleep_action(user_id, action, today)
                elif action_type == "activity_status":
                    result = self._handle_activity_status_action(user_id, action, now)
                elif action_type == "vocabulary":
                    result = self._handle_vocabulary_action(user_id, action)
                else:
                    logger.warning(f"未知活动类型: {action_type}")
                    continue
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"执行{action_type}活动失败: {e}")
                self.db.rollback()
        return results

    def _handle_checkin_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理打卡活动"""
        template_id = action.get("template_id")
        template_name = action.get("template_name")
        value = action.get("value")

        # 按ID查找模板，失败则按名称
        template = None
        if template_id:
            template = self.db.query(CheckinTemplate).filter(
                CheckinTemplate.id == template_id,
                CheckinTemplate.user_id == user_id,
                CheckinTemplate.is_active == True
            ).first()
        if not template and template_name:
            template = self.db.query(CheckinTemplate).filter(
                CheckinTemplate.user_id == user_id,
                CheckinTemplate.name.ilike(f"%{template_name}%"),
                CheckinTemplate.is_active == True
            ).first()
        if not template:
            logger.warning(f"打卡模板未找到: id={template_id}, name={template_name}")
            return None

        # 检查今日是否已打卡
        existing = self.db.query(CheckinRecord).filter(
            CheckinRecord.template_id == template.id,
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date == today
        ).first()

        actual_value = value if value is not None else template.default_target

        if existing:
            # 如果已打卡，累加数值
            existing.value = (existing.value or 0) + actual_value
            existing.completion_rate = (existing.value / template.default_target * 100) if template.default_target > 0 else 100
            template.total_value = (template.total_value or 0) + actual_value
            self.db.commit()
            return {
                "type": "checkin", "status": "updated",
                "message": f"{template.icon} {template.name} 累计{existing.value}{template.unit} 已更新"
            }

        completion_rate = (actual_value / template.default_target * 100) if template.default_target > 0 else 100
        record = CheckinRecord(
            template_id=template.id, user_id=user_id,
            checkin_date=today, value=actual_value,
            target=template.default_target, completion_rate=completion_rate,
            notes="通过智能助理对话自动记录"
        )
        self.db.add(record)

        # 更新模板统计
        template.total_checkins = (template.total_checkins or 0) + 1
        template.total_value = (template.total_value or 0) + actual_value
        yesterday = today - timedelta(days=1)
        if template.last_checkin_date == yesterday:
            template.current_streak = (template.current_streak or 0) + 1
        elif template.last_checkin_date != today:
            template.current_streak = 1
        template.last_checkin_date = today
        if (template.current_streak or 0) > (template.best_streak or 0):
            template.best_streak = template.current_streak

        self.db.commit()
        logger.info(f"用户{user_id} 打卡: {template.name} {actual_value}{template.unit}")
        return {
            "type": "checkin", "status": "saved",
            "message": f"{template.icon} {template.name} {actual_value}{template.unit} 已记录"
        }

    def _handle_rhinitis_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理鼻炎活动（洗鼻/泡鼻/打喷嚏），直接写入 health_checkins 表"""
        nasal_wash = action.get("nasal_wash")          # 洗鼻次数，通常1
        nasal_wash_type = action.get("nasal_wash_type", "wash")  # "wash" 或 "soak"
        sneeze_count = action.get("sneeze_count")       # 喷嚏次数
        now_str = datetime.now().strftime("%H:%M")

        hc = self.db.query(HealthCheckin).filter(
            HealthCheckin.user_id == user_id,
            HealthCheckin.checkin_date == today,
        ).first()
        if not hc:
            hc = HealthCheckin(user_id=user_id, checkin_date=today)
            self.db.add(hc)

        msgs = []
        if nasal_wash:
            hc.nasal_wash_count = (hc.nasal_wash_count or 0) + int(nasal_wash)
            times = list(hc.nasal_wash_times or [])
            times.append({"time": now_str, "type": nasal_wash_type})
            hc.nasal_wash_times = times
            label = "泡鼻" if nasal_wash_type == "soak" else "洗鼻"
            msgs.append(f"\U0001fae7 {label} {hc.nasal_wash_count}次 已记录")

        if sneeze_count:
            hc.sneeze_count = (hc.sneeze_count or 0) + int(sneeze_count)
            times = list(hc.sneeze_times or [])
            times.append({"time": now_str, "count": int(sneeze_count)})
            hc.sneeze_times = times
            msgs.append(f"\U0001f927 打喷嚏 {hc.sneeze_count}次 已记录")

        if not msgs:
            return None

        self.db.commit()
        return {"type": "rhinitis", "status": "saved", "message": "、".join(msgs)}

    def _handle_water_action(self, user_id: int, action: dict, today: date, now: datetime) -> Optional[Dict]:
        """处理喝水活动"""
        amount = action.get("amount", 250)
        drink_type = action.get("drink_type", "水")
        record = WaterIntake(
            user_id=user_id, record_date=today,
            amount_ml=amount, intake_time=now, drink_type=drink_type,
        )
        self.db.add(record)
        self.db.commit()
        logger.info(f"用户{user_id} 喝水: {amount}ml {drink_type}")
        return {
            "type": "water", "status": "saved",
            "message": f"\U0001f4a7 {drink_type} {amount}ml 已记录"
        }

    def _handle_supplement_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理补剂活动"""
        supplement_id = action.get("supplement_id")
        supplement_name = action.get("supplement_name")

        supplement = None
        if supplement_id:
            supplement = self.db.query(SupplementDefinition).filter(
                SupplementDefinition.id == supplement_id,
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.is_active == True
            ).first()
        if not supplement and supplement_name:
            supplement = self.db.query(SupplementDefinition).filter(
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.name.ilike(f"%{supplement_name}%"),
                SupplementDefinition.is_active == True
            ).first()
        if not supplement:
            logger.warning(f"补剂未找到: id={supplement_id}, name={supplement_name}")
            return None

        existing = self.db.query(SupplementRecord).filter(
            SupplementRecord.supplement_id == supplement.id,
            SupplementRecord.user_id == user_id,
            SupplementRecord.record_date == today
        ).first()
        if existing:
            existing.taken = True
            self.db.commit()
            return {
                "type": "supplement", "status": "updated",
                "message": f"\U0001f48a {supplement.name} 已标记为已服用"
            }

        record = SupplementRecord(
            supplement_id=supplement.id, user_id=user_id,
            record_date=today, taken=True,
            notes="通过智能助理对话自动记录"
        )
        self.db.add(record)
        self.db.commit()
        logger.info(f"用户{user_id} 补剂: {supplement.name}")
        return {
            "type": "supplement", "status": "saved",
            "message": f"\U0001f48a {supplement.name} 已记录"
        }

    def _handle_symptom_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """处理症状记录活动"""
        from sqlalchemy import text as sa_text
        profile_id = action.get("profile_id")
        disease_name = action.get("disease_name")
        overall_severity = action.get("overall_severity", 3)
        symptoms = action.get("symptoms", [])

        try:
            row = None
            if profile_id:
                row = self.db.execute(sa_text(
                    "SELECT p.id, COALESCE(dt.display_name, dt.name, '未知疾病') as disease_name "
                    "FROM user_disease_profiles p "
                    "LEFT JOIN disease_templates dt ON dt.id = p.disease_id "
                    "WHERE p.id = :pid AND p.user_id = :uid"
                ), {"pid": profile_id, "uid": user_id}).first()
            if not row and disease_name:
                row = self.db.execute(sa_text(
                    "SELECT p.id, COALESCE(dt.display_name, dt.name, '未知疾病') as disease_name "
                    "FROM user_disease_profiles p "
                    "LEFT JOIN disease_templates dt ON dt.id = p.disease_id "
                    "WHERE p.user_id = :uid AND (dt.display_name ILIKE :name OR dt.name ILIKE :name)"
                ), {"uid": user_id, "name": f"%{disease_name}%"}).first()
            if not row:
                logger.warning(f"疾病档案未找到: id={profile_id}, name={disease_name}")
                return None

            p_id, p_disease_name = row[0], row[1]
            # 使用原始SQL插入，避免ORM模型与数据库字段不匹配
            symptom_type = symptoms[0]["name"] if symptoms else p_disease_name
            severity_val = overall_severity
            self.db.execute(sa_text(
                "INSERT INTO symptom_logs (user_id, disease_profile_id, log_date, symptom_type, severity, notes, created_at) "
                "VALUES (:uid, :pid, :log_date, :stype, :sev, :notes, NOW())"
            ), {
                "uid": user_id, "pid": p_id, "log_date": today,
                "stype": symptom_type, "sev": severity_val,
                "notes": "通过智能助理对话自动记录"
            })
            self.db.commit()
            logger.info(f"用户{user_id} 症状: {p_disease_name} 严重度{overall_severity}")
            return {
                "type": "symptom", "status": "saved",
                "message": f"\U0001f3e5 {p_disease_name}症状(严重度{overall_severity}/10) 已记录"
            }
        except Exception as e:
            logger.error(f"症状记录失败: {e}")
            self.db.rollback()
            return None

    def _handle_illness_create(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """通过 AI 对话新建病症发作记录"""
        name = action.get("name", "").strip()
        if not name:
            return None
        severity = max(1, min(10, int(action.get("severity", 5))))
        notes = action.get("notes", "")
        start_date_str = action.get("start_date")
        try:
            from datetime import datetime as _dt
            start_date = _dt.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else today
        except Exception:
            start_date = today

        episode = IllnessEpisode(
            user_id=user_id,
            name=name,
            start_date=start_date,
            severity=severity,
            status="active",
            notes=notes or "通过智能助理对话记录",
        )
        self.db.add(episode)
        self.db.commit()
        logger.info(f"用户{user_id} 病症发作: {name}, 严重度{severity}")
        return {
            "type": "illness_create", "status": "saved",
            "message": f"\U0001f912 {name}(严重度{severity}/10) 已记录，希望你早日康复！"
        }

    def _handle_illness_update(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """通过 AI 对话更新病症状态"""
        episode_id = action.get("episode_id")
        name = action.get("name", "").strip()

        episode = None
        if episode_id:
            episode = self.db.query(IllnessEpisode).filter(
                IllnessEpisode.id == episode_id,
                IllnessEpisode.user_id == user_id,
            ).first()
        if not episode and name:
            episode = self.db.query(IllnessEpisode).filter(
                IllnessEpisode.user_id == user_id,
                IllnessEpisode.name.ilike(f"%{name}%"),
                IllnessEpisode.status != "resolved",
            ).order_by(IllnessEpisode.start_date.desc()).first()

        if not episode:
            logger.warning(f"病症记录未找到: id={episode_id}, name={name}")
            return None

        new_status = action.get("status")
        new_severity = action.get("severity")
        notes = action.get("notes", "")

        if new_severity is not None:
            episode.severity = max(1, min(10, int(new_severity)))
        if new_status:
            episode.status = new_status
            if new_status == "resolved" and not episode.end_date:
                episode.end_date = today

        update = IllnessUpdate(
            episode_id=episode.id,
            user_id=user_id,
            update_date=today,
            severity=episode.severity,
            status=episode.status,
            notes=notes or f"通过智能助理对话更新",
        )
        self.db.add(update)
        self.db.commit()

        status_label = {"active": "发作中", "improving": "好转中", "resolved": "已痊愈"}
        label = status_label.get(episode.status, episode.status)
        msg = f"\u2705 {episode.name} 状态已更新：{label}，严重度{episode.severity}/10"
        if episode.status == "resolved":
            msg = f"\U0001f389 {episode.name} 已痊愈！共持续{(today - episode.start_date).days + 1}天"
        logger.info(f"用户{user_id} 病症更新: {episode.name} → {episode.status}")
        return {"type": "illness_update", "status": "saved", "message": msg}

    def _handle_excretion_action(self, user_id: int, action: dict, today: date, now: datetime) -> Optional[Dict]:
        """通过 AI 对话记录排泄"""
        exc_type = action.get("excretion_type", "bowel")
        if exc_type not in ("bowel", "urine"):
            exc_type = "bowel"

        record = ExcretionRecord(
            user_id=user_id,
            record_date=today,
            record_time=now.time(),
            type=exc_type,
            stool_type=action.get("stool_type"),
            color=action.get("color"),
            amount=action.get("amount"),
            urine_color=action.get("urine_color"),
            urine_amount=action.get("urine_amount"),
            notes=action.get("notes"),
        )
        self.db.add(record)
        self.db.commit()

        label = "大便" if exc_type == "bowel" else "小便"
        logger.info(f"用户{user_id} AI记录排泄: {label}")
        return {"type": "excretion", "status": "saved", "message": f"已记录{label}"}

    def _handle_sleep_action(self, user_id: int, action: dict, today: date) -> Optional[Dict]:
        """通过 AI 对话记录睡眠"""
        quality = action.get("sleep_quality", 3)
        bedtime_str = action.get("bedtime")
        wake_str = action.get("wake_time")

        if not bedtime_str or not wake_str:
            return None

        try:
            # 解析 HH:MM 格式的时间
            bh, bm = map(int, bedtime_str.split(":"))
            wh, wm = map(int, wake_str.split(":"))

            from datetime import timezone as tz
            # 入睡时间：如果是晚上（>=18点），算前一天
            bedtime_date = today - timedelta(days=1) if bh >= 18 else today
            bedtime = datetime(bedtime_date.year, bedtime_date.month, bedtime_date.day, bh, bm, tzinfo=tz.utc)
            wake_time = datetime(today.year, today.month, today.day, wh, wm, tzinfo=tz.utc)

            if wake_time <= bedtime:
                return None

            duration = int((wake_time - bedtime).total_seconds() // 60)

            record = SleepRecord(
                user_id=user_id,
                record_date=today,
                bedtime=bedtime,
                wake_time=wake_time,
                sleep_quality=max(1, min(5, int(quality))),
                total_duration_minutes=duration,
                wake_count=action.get("wake_count"),
            )
            self.db.add(record)
            self.db.commit()

            hours = duration // 60
            mins = duration % 60
            logger.info(f"用户{user_id} AI记录睡眠: {hours}h{mins}min")
            return {"type": "sleep", "status": "saved", "message": f"已记录睡眠{hours}小时{mins}分钟"}
        except Exception as e:
            logger.warning(f"解析睡眠时间失败: {e}")
            return None

    def _handle_activity_status_action(self, user_id: int, action: dict, now: datetime) -> Optional[Dict]:
        """通过 AI 对话记录当前活动状态"""
        # 结束当前活动
        if action.get("end"):
            active = self.db.query(ActivityStatus).filter(
                ActivityStatus.user_id == user_id,
                ActivityStatus.is_active == True,
            ).all()
            if not active:
                return {"type": "activity_status", "status": "no_active", "message": "当前没有进行中的活动"}
            from datetime import timezone as tz
            end_time = datetime.now(tz.utc)
            for a in active:
                a.is_active = False
                a.actual_end_time = end_time
            self.db.commit()
            names = "、".join(a.status_text for a in active)
            return {"type": "activity_status", "status": "ended", "message": f"已结束活动: {names}"}

        activity_name = action.get("activity_name", "").strip()
        if not activity_name:
            return None

        category = action.get("category", "other")
        valid_cats = {"studying", "working", "exercising", "resting", "entertainment", "other"}
        if category not in valid_cats:
            category = "other"

        estimated_minutes = action.get("estimated_duration_minutes")
        if estimated_minutes:
            estimated_minutes = max(1, min(720, int(estimated_minutes)))

        from datetime import timezone as tz
        now_utc = datetime.now(tz.utc)

        # 自动结束之前的活动
        prev_active = self.db.query(ActivityStatus).filter(
            ActivityStatus.user_id == user_id,
            ActivityStatus.is_active == True,
        ).all()
        for a in prev_active:
            a.is_active = False
            a.actual_end_time = now_utc

        estimated_end = None
        if estimated_minutes:
            estimated_end = now_utc + timedelta(minutes=estimated_minutes)

        record = ActivityStatus(
            user_id=user_id,
            status_text=activity_name,
            category=category,
            start_time=now_utc,
            estimated_duration_minutes=estimated_minutes,
            estimated_end_time=estimated_end,
            is_active=True,
            notes=action.get("notes"),
        )
        self.db.add(record)
        self.db.commit()

        dur_text = f"，预计{estimated_minutes}分钟" if estimated_minutes else ""
        logger.info(f"用户{user_id} AI记录活动状态: {activity_name}")

        # 计算提醒时间（活动预估时长后提醒休息）
        reminder_minutes = estimated_minutes if estimated_minutes else 0
        reminder_message = ""
        if reminder_minutes > 0:
            if category in ("studying", "working"):
                reminder_message = f"{activity_name}已经{reminder_minutes}分钟了，该休息一下，看看远方，活动活动身体吧！"
            elif category == "exercising":
                reminder_message = f"{activity_name}已经{reminder_minutes}分钟了，注意补充水分和适当休息！"
            else:
                reminder_message = f"{activity_name}已经{reminder_minutes}分钟了，该换换活动了！"

        return {
            "type": "activity_status", "status": "saved",
            "message": f"已开始{activity_name}{dur_text}",
            "activity_name": activity_name,
            "reminder_minutes": reminder_minutes,
            "reminder_message": reminder_message,
        }

    def _handle_vocabulary_action(self, user_id: int, action: dict) -> Optional[Dict]:
        """处理单词学习 - 保存到单词本"""
        word = action.get("word", "").strip().lower()
        if not word:
            return None

        existing = self.db.query(VocabularyWord).filter(
            VocabularyWord.user_id == user_id,
            VocabularyWord.word == word,
        ).first()

        if existing:
            existing.review_count = (existing.review_count or 0) + 1
            existing.last_reviewed_at = datetime.utcnow()
            for field in ("phonetic_us", "phonetic_uk", "meanings", "synonyms", "antonyms", "word_roots", "example_sentences"):
                if action.get(field):
                    setattr(existing, field, action[field])
            self.db.commit()
            logger.info(f"用户{user_id} 复习单词: {word} (第{existing.review_count}次)")
            return {
                "type": "vocabulary", "status": "updated",
                "message": f"单词 {word} 已更新，复习第{existing.review_count}次",
            }

        vocab = VocabularyWord(
            user_id=user_id,
            word=word,
            phonetic_us=action.get("phonetic_us"),
            phonetic_uk=action.get("phonetic_uk"),
            meanings=action.get("meanings"),
            example_sentences=action.get("example_sentences"),
            synonyms=action.get("synonyms"),
            antonyms=action.get("antonyms"),
            word_roots=action.get("word_roots"),
            notes=action.get("notes"),
            review_count=1,
            next_review_date=date.today() + timedelta(days=1),
        )
        self.db.add(vocab)
        self.db.commit()
        logger.info(f"用户{user_id} 学习新单词: {word}")
        return {
            "type": "vocabulary", "status": "saved",
            "message": f"单词 {word} 已加入单词本",
        }

    async def handle_create_plan_async(self, user_id: int, action: dict) -> Optional[Dict]:
        """通过 AI 对话直接生成并写入智能计划"""
        from app.services.smart_plan_service import SmartPlanService
        target_week = action.get("target_week", "next")
        user_focus = action.get("user_focus") or []
        user_notes = action.get("user_notes") or ""
        intensity = action.get("intensity", "moderate")
        try:
            service = SmartPlanService(self.db)
            result = await service.generate_plan(
                user_id,
                target_week=target_week,
                user_focus=user_focus,
                user_notes=user_notes,
                intensity=intensity,
            )
            plan = result["plan"]
            week_label = "下周" if target_week == "next" else "本周"
            logger.info(f"用户{user_id} AI 自动生成{week_label}计划 plan_id={plan.id}")
            return {
                "type": "create_plan",
                "status": "saved",
                "plan_id": plan.id,
                "week_label": week_label,
                "item_count": len(plan.items),
                "message": f"已为你生成{week_label}计划，共 {len(plan.items)} 项行动，可在「智能计划」页面查看",
            }
        except Exception as e:
            logger.error(f"AI 自动生成计划失败: {type(e).__name__}: {e}")
            return {
                "type": "create_plan",
                "status": "failed",
                "message": "计划生成失败，请稍后在「智能计划」页面手动生成",
            }

    async def handle_workout_analyze_action(self, user_id: int, action: dict) -> Optional[Dict]:
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

            # Build model insights
            model_insights = ""
            model_results = analysis.get("model_results", [])
            if model_results:
                insights = []
                for mr in model_results:
                    site = mr.get("site", "")
                    content = mr.get("content", "")
                    display_name = site.replace("lb-", "").replace("-", " ").title()
                    if content:
                        preview = content[:300] + "..." if len(content) > 300 else content
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
                "message": f"运动分析完成：{workout_line}{analysis_text}",
                "workout_data": workout,
            }
        except Exception as e:
            logger.error(f"运动分析 action 处理失败: {e}", exc_info=True)
            return {
                "type": "workout_analyze",
                "status": "error",
                "message": f"运动分析失败: {str(e)}",
            }
