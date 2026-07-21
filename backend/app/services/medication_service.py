"""用药管理服务"""
import logging
from typing import Dict, Any, List, Optional
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError

from app.models.medication import Medication, MedicationLog, medication_timing_label

logger = logging.getLogger(__name__)

_BEIJING_TZ = timezone(timedelta(hours=8))


def normalize_taken_time(raw: Any) -> Optional[str]:
    """把任意 taken_time 输入归一成列语义的 "HH:MM"(单一真源)。

    背景(2026-07-12 生产实锤):executor 默认值曾是带微秒+时区的完整 ISO
    (32 字符)→ 溢出 medication_logs.taken_time varchar → 500 → 无写回执,
    用药确认流看似"指令没遵循"。列语义本就是短时刻 "08:00"(依从性幂等
    去重按该槽位撞;剂次槽解析 _resolve_dose_slot 也按 HH:MM 匹配),
    正解是归一化,不是加宽列。

    接受:"HH:MM" / "HH:MM:SS" / 完整 ISO(含微秒/时区,tz-aware 折算北京时)。
    None/空 → None(调用方自定默认)。解析不了 → ValueError(fail-loud,
    400 而不是数据库 500)。
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # 完整 ISO 日期时间(含 T 或 空格分隔)
    if "T" in s or (" " in s and "-" in s):
        try:
            dt = datetime.fromisoformat(s.replace(" ", "T", 1))
        except ValueError as exc:
            raise ValueError(f"无法解析 taken_time: {s!r}") from exc
        if dt.tzinfo is not None:
            dt = dt.astimezone(_BEIJING_TZ)
        return dt.strftime("%H:%M")
    # "HH:MM" / "HH:MM:SS"
    parts = s.split(":")
    if len(parts) >= 2:
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError as exc:
            raise ValueError(f"无法解析 taken_time: {s!r}") from exc
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    raise ValueError(f"无法解析 taken_time: {s!r}")


class MedicationService:
    """用药管理服务"""

    def add_medication(
        self,
        db: Session,
        user_id: int,
        data: Dict[str, Any],
    ) -> Medication:
        """添加药品"""
        logger.info(f"[Medication] 添加药品: user={user_id}, name={data.get('name')}")

        med = Medication(
            user_id=user_id,
            name=data["name"],
            dosage=data.get("dosage"),
            frequency=data.get("frequency"),
            times_per_day=data.get("times_per_day", 1),
            reminder_times=data.get("reminder_times"),
            timing_relation=data.get("timing_relation"),
            meal_anchor=data.get("meal_anchor"),
            category=data.get("category"),
            purpose=data.get("purpose"),
            side_effects=data.get("side_effects"),
            interactions=data.get("interactions"),
            start_date=data.get("start_date", date.today()),
            end_date=data.get("end_date"),
            notes=data.get("notes"),
            is_active=True,
        )
        db.add(med)
        db.commit()
        db.refresh(med)
        logger.info(f"[Medication] 药品已添加: id={med.id}")
        return med

    def get_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
    ) -> Optional[Medication]:
        """获取药品详情"""
        return db.query(Medication).filter(
            Medication.id == medication_id,
            Medication.user_id == user_id,
        ).first()

    def list_medications(
        self,
        db: Session,
        user_id: int,
        active_only: bool = True,
    ) -> List[Medication]:
        """列出用户药品"""
        logger.info(f"[Medication] 列出药品: user={user_id}, active_only={active_only}")
        query = db.query(Medication).filter(Medication.user_id == user_id)
        if active_only:
            query = query.filter(Medication.is_active == True)
        return query.order_by(desc(Medication.created_at)).all()

    def update_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
        data: Dict[str, Any],
    ) -> Optional[Medication]:
        """更新药品信息"""
        logger.info(f"[Medication] 更新药品: id={medication_id}, user={user_id}")
        med = self.get_medication(db, medication_id, user_id)
        if not med:
            return None

        updatable = ["name", "dosage", "frequency", "times_per_day", "reminder_times",
                      "timing_relation", "meal_anchor",
                      "category", "purpose", "side_effects", "interactions",
                      "start_date", "end_date", "notes"]
        for key in updatable:
            if key in data:
                setattr(med, key, data[key])

        db.commit()
        db.refresh(med)
        return med

    def deactivate_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
    ) -> bool:
        """停用药品"""
        logger.info(f"[Medication] 停用药品: id={medication_id}, user={user_id}")
        med = self.get_medication(db, medication_id, user_id)
        if not med:
            return False
        med.is_active = False
        med.end_date = date.today()
        db.commit()
        return True

    def reactivate_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
    ) -> bool:
        """恢复已停用药品 (误点击回滚用).

        不受 is_active=True/False 过滤影响 — 直接查 id + user 所有权.
        恢复后清 end_date, 让药品回到 '在用' 状态.
        """
        logger.info(f"[Medication] 恢复药品: id={medication_id}, user={user_id}")
        med = db.query(Medication).filter(
            Medication.id == medication_id,
            Medication.user_id == user_id,
        ).first()
        if not med:
            return False
        med.is_active = True
        med.end_date = None
        db.commit()
        return True

    def log_medication(
        self,
        db: Session,
        user_id: int,
        medication_id: int,
        taken_time: str,
        status: str = "taken",
        skip_reason: Optional[str] = None,
        actual_dosage: Optional[str] = None,
        notes: Optional[str] = None,
        commit: bool = True,
        taken_date: Optional[date] = None,
    ) -> MedicationLog:
        """记录服药。

        commit=True(默认,保持既有调用方行为)立即提交并 refresh。
        commit=False:只 flush(拿到 id),把提交权交还调用方 —— 协议完成路径
        (complete_protocol)用它把领域写并入终态事件的一次性 commit,避免中途
        提交半成品 event 破坏原子性(S2)。

        幂等(commit=True 路径):同 (药, 日期, 时点) 已存在(并发重复点击 / 重试)→ 唯一索引
        uq_medlog_med_date_time 让第二条 INSERT 撞 IntegrityError → 回滚重读返回既有行,不静默
        落第二条虚高依从(否则经 twin.medication.adherence_7d_pct 误证给 DDI/PGx/SafetyGuardian)。
        commit=False(协议路径)由 complete_protocol 的事件门控保证至多一次领域写,这里只 flush。
        """
        logger.info(f"[Medication] 记录服药: user={user_id}, med={medication_id}, status={status}")

        log = MedicationLog(
            user_id=user_id,
            medication_id=medication_id,
            taken_date=taken_date or date.today(),
            taken_time=taken_time,
            status=status,
            skip_reason=skip_reason,
            actual_dosage=actual_dosage,
            notes=notes,
        )
        db.add(log)
        if commit:
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                q = db.query(MedicationLog).filter(
                    MedicationLog.user_id == user_id,
                    MedicationLog.medication_id == medication_id,
                    MedicationLog.taken_date == log.taken_date,
                )
                # taken_time 是唯一槽的一部分(NULL 折叠成 ''),按值精确回查既有行。
                if taken_time is None:
                    q = q.filter(MedicationLog.taken_time.is_(None))
                else:
                    q = q.filter(MedicationLog.taken_time == taken_time)
                existing = q.order_by(MedicationLog.id.desc()).first()
                if existing is None:  # 撞唯一约束却查不到 → 反常, fail loud
                    raise
                # 同槽先跳过/延迟、后确认已服：以更强的用户执行事实 supersede，
                # 仍只保留一行。反向的 taken→skipped 不在快捷动作里降级，调用方
                # 会从响应 status 看见冲突并要求在 App 内显式修正。
                if status == "taken" and existing.status in {"skipped", "delayed"}:
                    existing.status = "taken"
                    existing.skip_reason = None
                    if actual_dosage is not None:
                        existing.actual_dosage = actual_dosage
                    if notes is not None:
                        existing.notes = notes
                    db.commit()
                    db.refresh(existing)
                return existing
            db.refresh(log)
        else:
            db.flush()
        return log

    def upsert_medication_log(
        self,
        db: Session,
        user_id: int,
        medication_id: int,
        taken_time: str,
        status: str = "taken",
        skip_reason: Optional[str] = None,
        actual_dosage: Optional[str] = None,
        notes: Optional[str] = None,
        commit: bool = False,
        taken_date: Optional[date] = None,
    ) -> MedicationLog:
        """同槽 upsert 服药/漏服记录(supersede 语义)。

        uq_medlog_med_date_time 是 (药, 日期, 时点) 唯一且 **status-agnostic** ——
        同一确定性槽至多一行。普通 INSERT(log_medication)在「先跳后服」会撞约束。
        本方法改为 **find-then-update**:

        - 同槽已有行 → 原地改 status/skip_reason/actual_dosage(skipped→taken 的 supersede,
          以及 taken→taken / skipped→skipped 的幂等)。绝不落第二条 → 依从计数不虚高。
        - 同槽无行 → INSERT;并发竞态(另一事务刚插同槽)撞 IntegrityError → 重读那行再原地改。

        commit=False(议程闭环路径默认):只 flush,提交权交回调用方单次事务;
        IntegrityError 后只能重读(不 rollback,以免撤掉调用方未提交的状态转移)。
        commit=True:自带提交 + 失败回滚重试(独立调用方)。

        守不变量:① 同槽至多一条(去重)② skipped→taken 可 supersede(用户先跳后服记成服)
        ③ 同槽已有 **taken** 行又来一次 taken(不同议程事件的重复完成,= 同一剂双领)→ 不静默
           合并:落到 INSERT 撞 uq_medlog → 上抛 IntegrityError,让调用方 fail-loud(守
           「至多一条依从、回写失败不翻 done」;同事件重复完成由上游议程原子 claim 已短路)。
        ④ 写库失败向上抛(fail-loud,不假装成功)。
        """
        slot = taken_time if taken_time else None
        target_date = taken_date or date.today()

        def _find_same_slot() -> Optional[MedicationLog]:
            q = db.query(MedicationLog).filter(
                MedicationLog.user_id == user_id,
                MedicationLog.medication_id == medication_id,
                MedicationLog.taken_date == target_date,
            )
            if slot is None:
                q = q.filter(MedicationLog.taken_time.is_(None))
            else:
                q = q.filter(MedicationLog.taken_time == slot)
            return q.order_by(MedicationLog.id.desc()).first()

        def _apply(row: MedicationLog) -> None:
            row.status = status
            row.skip_reason = skip_reason
            if actual_dosage is not None:
                row.actual_dosage = actual_dosage
            if notes is not None:
                row.notes = notes

        existing = _find_same_slot()
        # 仅在「现有行非 taken」(pending/skipped→supersede)或「现有行与目标同为 skipped」(幂等)
        # 时原地改;现有行已是 taken 又要再 taken → 不 supersede,落 INSERT 撞约束 fail-loud
        # (同一剂被两条不同议程事件双领的残留缝隙,守至多一条依从)。
        if existing is not None and existing.status != "taken":
            _apply(existing)
            if commit:
                db.commit()
                db.refresh(existing)
            else:
                db.flush()
            logger.info(
                f"[Medication] upsert(supersede): user={user_id}, med={medication_id}, "
                f"slot={slot}, {existing.status!r}→{status!r}"
            )
            return existing

        log = MedicationLog(
            user_id=user_id,
            medication_id=medication_id,
            taken_date=target_date,
            taken_time=slot,
            status=status,
            skip_reason=skip_reason,
            actual_dosage=actual_dosage,
            notes=notes,
        )
        db.add(log)
        if commit:
            # 独立调用方:并发同槽 INSERT 撞 → rollback 重读原地改(commit 路径可安全 rollback)。
            try:
                db.commit()
                db.refresh(log)
            except IntegrityError:
                db.rollback()
                existing = _find_same_slot()
                if existing is None:  # 撞唯一约束却查不到 → 反常,fail loud
                    raise
                _apply(existing)
                db.commit()
                db.refresh(existing)
                return existing
        else:
            # commit=False(议程闭环路径):find 已确认无同槽行,故此 INSERT 不应撞约束。
            # 若仍撞(两条议程行真并发首插同一确定性槽)→ flush 抛 IntegrityError 不在此吞:
            # 让调用方(complete_agenda_event)整事务回滚 + 转 AgendaCompleteError → 422,
            # 守「至多一条依从、回写失败不翻 done」(test_two_agenda_events...fails_loud)。
            db.flush()
        logger.info(
            f"[Medication] upsert(insert): user={user_id}, med={medication_id}, "
            f"slot={slot}, status={status}"
        )
        return log

    def get_today_status(
        self,
        db: Session,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """获取今日服药状态"""
        logger.info(f"[Medication] 获取今日状态: user={user_id}")
        today = date.today()

        # 获取活跃药品
        meds = self.list_medications(db, user_id, active_only=True)

        result = []
        for med in meds:
            # 获取今日记录（按 taken_time 排序方便取 last）
            logs = db.query(MedicationLog).filter(
                MedicationLog.medication_id == med.id,
                MedicationLog.user_id == user_id,
                MedicationLog.taken_date == today,
            ).order_by(MedicationLog.taken_time.asc()).all()

            taken_count = sum(1 for l in logs if l.status == "taken")
            skipped_count = sum(1 for l in logs if l.status == "skipped")

            # 今日最后一次 taken
            last_today = None
            for l in reversed(logs):
                if l.status == "taken":
                    last_today = l.taken_time
                    break

            # 若今日无记录，查最近一次 taken（可能昨天或更早）
            last_overall = None
            last_overall_date = None
            if last_today is None:
                last_log = db.query(MedicationLog).filter(
                    MedicationLog.medication_id == med.id,
                    MedicationLog.user_id == user_id,
                    MedicationLog.status == "taken",
                ).order_by(
                    MedicationLog.taken_date.desc(),
                    MedicationLog.taken_time.desc(),
                ).first()
                if last_log:
                    last_overall = last_log.taken_time
                    last_overall_date = str(last_log.taken_date)

            result.append({
                "medication_id": med.id,
                "name": med.name,
                "dosage": med.dosage,
                "timing_relation": med.timing_relation,
                "meal_anchor": med.meal_anchor,
                "timing_label": medication_timing_label(med.timing_relation, med.meal_anchor),
                "category": med.category,
                # 长期用药安全规则(如 dsi.long_term_acid_suppression)按 start_date 算时长
                "start_date": med.start_date.isoformat() if med.start_date else None,
                "total_count": med.times_per_day,
                "taken_count": taken_count,
                "skipped_count": skipped_count,
                "last_taken_time": last_today,  # HH:MM today or None
                "last_taken_time_overall": last_overall,  # 若今日未记录，最近一次时间
                "last_taken_date_overall": last_overall_date,  # 最近一次日期
                "reminder_times": med.reminder_times or [],
                "logs": [
                    {"time": l.taken_time, "status": l.status, "id": l.id}
                    for l in logs
                ],
            })

        return result

    def get_adherence_stats(
        self,
        db: Session,
        user_id: int,
        days: int = 7,
    ) -> Dict[str, Any]:
        """获取服药依从性统计"""
        logger.info(f"[Medication] 获取依从性: user={user_id}, days={days}")
        start_date = date.today() - timedelta(days=days - 1)

        # 获取时段内的服药记录
        logs = db.query(MedicationLog).filter(
            MedicationLog.user_id == user_id,
            MedicationLog.taken_date >= start_date,
        ).all()

        total_taken = sum(1 for l in logs if l.status == "taken")
        total_skipped = sum(1 for l in logs if l.status == "skipped")
        total_logs = len(logs)

        # 获取活跃药品的预期总次数
        meds = self.list_medications(db, user_id, active_only=True)
        # Unknown schedule (NULL) is not evidence for an expected daily dose.
        # It can exist for an observed one-off intake and must neither crash
        # Twin/adherence reads nor silently become the model default of 1/day.
        expected_total = sum((m.times_per_day or 0) for m in meds) * days

        adherence_rate = round(total_taken / expected_total * 100, 1) if expected_total > 0 else 0

        # 按药品统计
        med_stats = {}
        for log in logs:
            mid = log.medication_id
            if mid not in med_stats:
                med_stats[mid] = {"taken": 0, "skipped": 0, "total": 0}
            med_stats[mid]["total"] += 1
            if log.status == "taken":
                med_stats[mid]["taken"] += 1
            elif log.status == "skipped":
                med_stats[mid]["skipped"] += 1

        return {
            "adherence_rate": adherence_rate,
            "total_taken": total_taken,
            "total_skipped": total_skipped,
            "total_expected": expected_total,
            "days": days,
            "medication_stats": med_stats,
        }


medication_service = MedicationService()
