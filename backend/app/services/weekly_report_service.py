"""周度健康周报服务 — 穿越式反馈引擎

v2 升级点 (相比单纯的数据聚合):
1. cross_reference_engine: 拉 active supplement_audits 和 health_consultations 的 pending items,
   基于本周打卡/运动/饮食/Garmin 数据计算每条 action 的执行证据
2. verify_active_predictions: 复用 health_consultation_service.verify_predictions 做中期校验
   (不改 predictions 原状态, 只写入周报的 comparison.predictions_mid_check)
3. gene_alignment_score: 读 genetic_variants + 本周 diet/supplement/exercise, 按基因-行为匹配规则打分
4. build_enhanced_review: 主入口 — 先调 health_report_service.generate_report 拿基础 summary,
   然后 UPDATE 扩展字段 (ai_analysis markdown + comparison 扩展)
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.checkin import CheckinRecord
from app.models.daily_health import DietRecord, ExerciseRecord, GarminData
from app.models.genetic_data import GeneticVariant
from app.models.health_consultation import ConsultationItem, HealthConsultation
from app.models.health_report import HealthReport
from app.models.medication import MedicationLog
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.supplement_audit import SupplementAudit, SupplementAuditItem

logger = logging.getLogger(__name__)


# ---------- 基因-行为匹配规则引擎 (rule-based) ----------
# 每条规则: 读本周数据, 判断是否命中某个基因的最佳实践
GENE_ALIGNMENT_RULES = [
    {
        "gene": "FADS1",
        "genotype_match": "TT",
        "check": "omega3_food_count",  # 本周三文鱼/秋刀鱼/鲭鱼次数
        "target_min": 2,
        "weight": 1,
    },
    {
        "gene": "IL-6",
        "genotype_match": "GG",
        "check": "antiinflammatory_food_count",  # 姜黄/鱼油/莓果/深绿蔬次数
        "target_min": 2,
        "weight": 1,
    },
    {
        "gene": "ALDH2",
        "genotype_match": "GA",  # 也包括 AA
        "check": "alcohol_count",
        "target_max": 1,  # 每周不超过 1 次
        "weight": 2,  # 违反扣双倍分
    },
    {
        "gene": "KCNJ11",
        "genotype_match": "TT",
        "check": "high_gi_meal_count",  # 粗略用 total_meals 超过阈值代替
        "target_max": 1,
        "weight": 1,
    },
    {
        "gene": "PPARGC1A",
        "genotype_match": "TT",  # Ser/Ser 线粒体弱, 需要运动刺激
        "check": "exercise_days",
        "target_min": 3,
        "weight": 1,
    },
    {
        "gene": "MTHFR",
        "genotype_match": "TT",
        "check": "methylation_supplement_adherence",  # 5-MTHF + B12 依从性
        "target_min": 5,  # 本周至少 5 天服用
        "weight": 1,
    },
]

OMEGA3_KEYWORDS = ["三文鱼", "秋刀鱼", "鲭鱼", "沙丁鱼", "亚麻", "鱼油", "金枪鱼"]
ANTIINFLAM_KEYWORDS = ["姜黄", "蓝莓", "蓝莓", "菠菜", "西兰花", "姜黄素", "深海鱼"]
ALCOHOL_KEYWORDS = ["啤酒", "白酒", "红酒", "葡萄酒", "威士忌", "清酒", "鸡尾酒", "黄酒", "米酒"]


class WeeklyReportService:
    """升级版周报引擎 — 跨实体反馈闭环"""

    # ====================================================================
    # 公开入口
    # ====================================================================

    def build_enhanced_review(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
    ) -> Optional[HealthReport]:
        """主入口: 生成并持久化升级版周报

        流程:
        1. 调 health_report_service 拿基础 summary (落库)
        2. 做 cross-reference / prediction-verify / gene-alignment
        3. UPDATE health_report 的 ai_analysis + comparison 扩展字段
        """
        from app.services.health_report_service import health_report_service

        logger.info(f"[WeeklyV2] 开始 user={user_id} 周={week_start}~{week_end}")

        # 1. 基础周报 (会直接 INSERT 到 health_reports)
        report = health_report_service.generate_report(
            db=db,
            user_id=user_id,
            report_type="weekly",
            start_date=week_start,
        )

        # 2. 跨实体引用 + 预测中期校验 + 基因对齐
        cross_ref = self.cross_reference_engine(db, user_id, week_start, week_end)
        predictions = self.verify_active_predictions(db, user_id)
        gene_score = self.gene_alignment_score(db, user_id, week_start, week_end)

        # 3. 生成 ai_analysis markdown
        markdown = self._render_markdown(
            user_id, week_start, week_end, report, cross_ref, predictions, gene_score
        )

        # 4. 扩展 comparison 字段
        comparison = dict(report.comparison or {})
        comparison["action_execution_report"] = cross_ref
        comparison["predictions_mid_check"] = predictions
        comparison["gene_alignment_score"] = gene_score

        report.ai_analysis = markdown
        report.comparison = comparison

        # 扩展 ai_recommendations 也塞一份 link 索引
        # health_report_service 返回的是 list 或 dict, 统一包装成 dict
        existing_recs = report.ai_recommendations
        if isinstance(existing_recs, list):
            recs: Dict[str, Any] = {"items": existing_recs}
        elif isinstance(existing_recs, dict):
            recs = dict(existing_recs)
        else:
            recs = {}
        recs["linked_supplement_audit_ids"] = cross_ref.get("linked_audit_ids", [])
        recs["linked_consultation_ids"] = cross_ref.get("linked_consultation_ids", [])
        report.ai_recommendations = recs

        db.commit()
        db.refresh(report)
        logger.info(f"[WeeklyV2] 完成 report_id={report.id} score={report.health_score}")
        return report

    # ====================================================================
    # 1. Cross-reference engine
    # ====================================================================

    def cross_reference_engine(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
    ) -> Dict[str, Any]:
        """读取 active supplement_audits + health_consultations 的 pending items,
        结合本周数据计算每条 action 的执行证据."""
        result: Dict[str, Any] = {
            "linked_audit_ids": [],
            "linked_consultation_ids": [],
            "supplement_audit_items": [],
            "consultation_actions": [],
            "summary": {"total": 0, "evidenced_done": 0, "evidenced_violation": 0, "no_evidence": 0},
        }

        # -- active supplement_audits --
        audits = (
            db.query(SupplementAudit)
            .filter(SupplementAudit.user_id == user_id, SupplementAudit.status == "active")
            .all()
        )
        for a in audits:
            result["linked_audit_ids"].append(a.id)
            pending_items = (
                db.query(SupplementAuditItem)
                .filter(
                    SupplementAuditItem.audit_id == a.id,
                    SupplementAuditItem.status == "pending",
                )
                .all()
            )
            for it in pending_items:
                result["supplement_audit_items"].append({
                    "audit_id": a.id,
                    "item_id": it.id,
                    "action_type": it.action_type,
                    "title": it.title,
                    "status": it.status,
                })
                result["summary"]["total"] += 1
                result["summary"]["no_evidence"] += 1  # 补剂方案类通常无直接证据

        # -- active health_consultations --
        consultations = (
            db.query(HealthConsultation)
            .filter(
                HealthConsultation.user_id == user_id,
                HealthConsultation.status == "active",
            )
            .all()
        )
        for c in consultations:
            result["linked_consultation_ids"].append(c.id)
            action_items = (
                db.query(ConsultationItem)
                .filter(
                    ConsultationItem.consultation_id == c.id,
                    ConsultationItem.item_type == "action",
                    ConsultationItem.status.in_(["pending", "in_progress"]),
                )
                .all()
            )
            for it in action_items:
                evidence = self._evidence_for_action(db, user_id, week_start, week_end, it)
                result["consultation_actions"].append({
                    "consultation_id": c.id,
                    "item_id": it.id,
                    "item_code": it.item_code,
                    "title": it.title,
                    "status": it.status,
                    "evidence": evidence,
                })
                result["summary"]["total"] += 1
                if evidence["verdict"] == "done":
                    result["summary"]["evidenced_done"] += 1
                elif evidence["verdict"] == "violation":
                    result["summary"]["evidenced_violation"] += 1
                else:
                    result["summary"]["no_evidence"] += 1

        return result

    def _evidence_for_action(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
        item: ConsultationItem,
    ) -> Dict[str, Any]:
        """对单条 consultation action 计算本周执行证据.

        verdict: done | violation | no_evidence
        """
        title = (item.title or "").lower()

        # HRV 采集类: 优先查模型映射的 hrv 字段, fallback 到生产独有的 hrv_last_night
        if "hrv" in title or ("garmin" in title and "hrv" in title):
            has_hrv = (
                db.query(func.count(GarminData.id))
                .filter(
                    GarminData.user_id == user_id,
                    GarminData.record_date >= week_start,
                    GarminData.record_date <= week_end,
                    GarminData.hrv.isnot(None),
                )
                .scalar()
            ) or 0
            # Fallback: 生产上还可能是 hrv_last_night 字段 (未在 ORM 映射, 用 raw SQL 兼容)
            if has_hrv == 0:
                try:
                    from sqlalchemy import text
                    row = db.execute(
                        text(
                            "SELECT COUNT(*) FROM garmin_data WHERE user_id=:u "
                            "AND record_date BETWEEN :s AND :e AND hrv_last_night IS NOT NULL"
                        ),
                        {"u": user_id, "s": week_start, "e": week_end},
                    ).scalar()
                    has_hrv = int(row or 0)
                except Exception:
                    pass
            if has_hrv > 0:
                return {"verdict": "done", "note": f"本周 {has_hrv} 天采集到 HRV 数据"}
            else:
                return {"verdict": "no_evidence", "note": "HRV 字段本周全空"}

        # 避免刺激食物 / 酒精
        if "酒精" in item.title or "避免" in item.title and "食物" in item.title:
            alcohol_count = self._count_alcohol_this_week(db, user_id, week_start, week_end)
            if alcohol_count == 0:
                return {"verdict": "done", "note": "本周无酒精记录"}
            else:
                return {"verdict": "violation", "note": f"本周 {alcohol_count} 次含酒精饮食"}

        # 挂号/就医类: 无法从打卡直接判断
        if "挂" in item.title or "门诊" in item.title or "psg" in title or "查" in item.title:
            return {"verdict": "no_evidence", "note": "无结构化数据验证, 需用户报告"}

        # 默认
        return {"verdict": "no_evidence", "note": "暂无规则判定"}

    # ====================================================================
    # 2. Prediction mid-check
    # ====================================================================

    def verify_active_predictions(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """对所有 active consultation 的 pending predictions 做中期校验.
        复用 health_consultation_service.verify_predictions 不改 predictions 原状态.
        """
        from app.services.health_consultation_service import health_consultation_service

        results: List[Dict[str, Any]] = []
        consultations = (
            db.query(HealthConsultation)
            .filter(
                HealthConsultation.user_id == user_id,
                HealthConsultation.status == "active",
            )
            .all()
        )
        for c in consultations:
            try:
                per_consult = health_consultation_service.verify_predictions(db, user_id, c.id)
                for r in per_consult:
                    r["consultation_id"] = c.id
                    results.append(r)
            except Exception as e:
                logger.warning(f"[WeeklyV2] verify_predictions 失败 consult={c.id}: {e}")
        return results

    # ====================================================================
    # 3. Gene alignment scoring
    # ====================================================================

    def gene_alignment_score(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
    ) -> Dict[str, Any]:
        """根据用户基因档案 + 本周数据, 计算基因-行为对齐分数."""
        variants = db.query(GeneticVariant).filter(GeneticVariant.user_id == user_id).all()
        variant_map = {v.gene_name: v for v in variants}

        hits: List[Dict[str, Any]] = []
        misses: List[Dict[str, Any]] = []
        partial: List[Dict[str, Any]] = []
        max_score = 0
        total_score = 0

        for rule in GENE_ALIGNMENT_RULES:
            v = variant_map.get(rule["gene"])
            if not v:
                continue
            if rule["genotype_match"] not in (v.genotype or ""):
                continue

            weight = rule["weight"]
            max_score += weight

            check = rule["check"]
            actual = self._compute_check_value(db, user_id, week_start, week_end, check)

            if "target_min" in rule:
                if actual >= rule["target_min"]:
                    total_score += weight
                    hits.append({"gene": rule["gene"], "check": check, "actual": actual, "target_min": rule["target_min"]})
                elif actual >= rule["target_min"] / 2:
                    total_score += weight / 2
                    partial.append({"gene": rule["gene"], "check": check, "actual": actual, "target_min": rule["target_min"]})
                else:
                    misses.append({"gene": rule["gene"], "check": check, "actual": actual, "target_min": rule["target_min"]})
            elif "target_max" in rule:
                if actual <= rule["target_max"]:
                    total_score += weight
                    hits.append({"gene": rule["gene"], "check": check, "actual": actual, "target_max": rule["target_max"]})
                else:
                    misses.append({"gene": rule["gene"], "check": check, "actual": actual, "target_max": rule["target_max"]})

        return {
            "total": round(total_score, 1),
            "max": max_score,
            "pct": round(total_score / max_score * 100, 1) if max_score > 0 else 0,
            "hits": hits,
            "partial": partial,
            "misses": misses,
        }

    def _compute_check_value(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
        check: str,
    ) -> float:
        """规则引擎 — 计算每个 check 的本周实际值."""
        if check == "omega3_food_count":
            return self._count_diet_keywords(db, user_id, week_start, week_end, OMEGA3_KEYWORDS)
        if check == "antiinflammatory_food_count":
            return self._count_diet_keywords(db, user_id, week_start, week_end, ANTIINFLAM_KEYWORDS)
        if check == "alcohol_count":
            return self._count_alcohol_this_week(db, user_id, week_start, week_end)
        if check == "exercise_days":
            return (
                db.query(func.count(func.distinct(ExerciseRecord.record_date)))
                .filter(
                    ExerciseRecord.user_id == user_id,
                    ExerciseRecord.record_date >= week_start,
                    ExerciseRecord.record_date <= week_end,
                )
                .scalar()
            ) or 0
        if check == "high_gi_meal_count":
            # 粗略: 本周 dessert/snack 类记录数
            return (
                db.query(func.count())
                .filter(
                    DietRecord.user_id == user_id,
                    DietRecord.record_date >= week_start,
                    DietRecord.record_date <= week_end,
                    DietRecord.meal_type == "snack",
                )
                .scalar()
            ) or 0
        if check == "methylation_supplement_adherence":
            # 找 5-MTHF/甲基叶酸相关补剂的打卡天数
            mthf_defs = (
                db.query(SupplementDefinition.id)
                .filter(
                    SupplementDefinition.user_id == user_id,
                    SupplementDefinition.is_active == True,  # noqa: E712
                    SupplementDefinition.name.ilike("%methyl%folate%"),
                )
                .scalar_subquery()
            )
            days = (
                db.query(func.count(func.distinct(SupplementRecord.record_date)))
                .filter(
                    SupplementRecord.user_id == user_id,
                    SupplementRecord.record_date >= week_start,
                    SupplementRecord.record_date <= week_end,
                    SupplementRecord.taken == True,  # noqa: E712
                    SupplementRecord.supplement_id.in_(mthf_defs),
                )
                .scalar()
            ) or 0
            return days
        return 0

    def _count_diet_keywords(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
        keywords: List[str],
    ) -> int:
        """饮食记录里 food_name 命中任一关键词的条数."""
        count = 0
        records = (
            db.query(DietRecord)
            .filter(
                DietRecord.user_id == user_id,
                DietRecord.record_date >= week_start,
                DietRecord.record_date <= week_end,
            )
            .all()
        )
        for r in records:
            name = r.food_name or ""
            if any(kw in name for kw in keywords):
                count += 1
        return count

    def _count_alcohol_this_week(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
    ) -> int:
        return self._count_diet_keywords(db, user_id, week_start, week_end, ALCOHOL_KEYWORDS)

    # ====================================================================
    # 4. Markdown render
    # ====================================================================

    def _render_markdown(
        self,
        user_id: int,
        week_start: date,
        week_end: date,
        report: HealthReport,
        cross_ref: Dict[str, Any],
        predictions: List[Dict[str, Any]],
        gene: Dict[str, Any],
    ) -> str:
        """把所有模块汇总成 markdown 周报."""
        lines: List[str] = []
        lines.append(f"# 本周健康周报 ({week_start} ~ {week_end})\n")

        # 1. 数据快照
        lines.append("## 📊 数据快照\n")
        vs = report.vital_signs_summary or {}
        if vs:
            lines.append(f"- 平均步数: {(report.exercise_summary or {}).get('avg_daily_steps', '—')}")
            lines.append(f"- 平均 RHR: {vs.get('avg_resting_heart_rate', '—')}")
            lines.append(f"- 平均 SpO2: {vs.get('avg_spo2', '—')}")
            sleep = report.sleep_summary or {}
            lines.append(f"- 平均睡眠评分: {sleep.get('avg_sleep_score', '—')}")
            lines.append(f"- 平均深睡: {sleep.get('avg_deep_sleep_minutes', '—')} min")
            lines.append(f"- 健康评分: {report.health_score}/100\n")

        # 2. Consultation v1 Action 执行对照
        if cross_ref.get("consultation_actions"):
            lines.append("## 🎯 跟踪中的行动项执行对照\n")
            lines.append("| 来源 | 行动 | 证据判定 | 说明 |")
            lines.append("|---|---|---|---|")
            for a in cross_ref["consultation_actions"]:
                ev = a.get("evidence", {})
                icon = {"done": "✅", "violation": "❌", "no_evidence": "❓"}.get(ev.get("verdict"), "•")
                lines.append(
                    f"| consult#{a['consultation_id']} {a['item_code'] or ''} | {a['title']} | {icon} {ev.get('verdict')} | {ev.get('note', '')} |"
                )
            s = cross_ref.get("summary", {})
            lines.append(
                f"\n**汇总**: {s.get('total',0)} 条跟踪 · ✅{s.get('evidenced_done',0)} · ❌{s.get('evidenced_violation',0)} · ❓{s.get('no_evidence',0)}\n"
            )

        # 3. Predictions 中期校验
        if predictions:
            lines.append("## 📈 可验证预测中期进度\n")
            lines.append("| 来源 | 指标 | 目标 | 实际 | 建议 | 说明 |")
            lines.append("|---|---|---|---|---|---|")
            for p in predictions:
                actual = p.get("actual_value")
                lines.append(
                    f"| consult#{p.get('consultation_id')} {p.get('item_code','')} | {p.get('metric_name','')} | {p.get('target','')} | {actual if actual is not None else '—'} | **{p.get('suggested_status','')}** | {p.get('note','')} |"
                )
            lines.append("")

        # 4. 基因对齐度
        if gene.get("max"):
            lines.append(f"## 🧬 基因对齐度: {gene.get('total')}/{gene.get('max')} ({gene.get('pct')}%)\n")
            for h in gene.get("hits", []):
                lines.append(f"- ✅ **{h['gene']}**: {h['check']} = {h['actual']} (达标)")
            for p in gene.get("partial", []):
                lines.append(f"- ⚠️ **{p['gene']}**: {p['check']} = {p['actual']} (部分达标)")
            for m in gene.get("misses", []):
                lines.append(f"- ❌ **{m['gene']}**: {m['check']} = {m['actual']} (未达标)")
            lines.append("")

        # 5. 建议 (从 report.ai_recommendations, 可能是 list 或 dict)
        raw_recs = report.ai_recommendations
        if isinstance(raw_recs, dict):
            items = raw_recs.get("items") or raw_recs.get("next_week_must_do") or []
        elif isinstance(raw_recs, list):
            items = raw_recs
        else:
            items = []
        if items and isinstance(items, list):
            lines.append("## 💡 下周行动建议\n")
            for i, rec in enumerate(items[:10], 1):
                if isinstance(rec, dict):
                    lines.append(f"{i}. **{rec.get('action', rec.get('title', ''))}** — {rec.get('rationale', rec.get('detail', ''))}")
                else:
                    lines.append(f"{i}. {rec}")
            lines.append("")

        return "\n".join(lines)

    # ====================================================================
    # 向后兼容: 旧 API (返回 dict, 不落库)
    # ====================================================================

    def generate_report(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
    ) -> Dict[str, Any]:
        """[deprecated] 旧的纯聚合 API. 保留避免破坏调用方. 新代码用 build_enhanced_review."""
        logger.warning("[WeeklyV2] generate_report 已 deprecated, 推荐使用 build_enhanced_review")
        report = self.build_enhanced_review(db, user_id, week_start, week_end)
        if not report:
            return {"days_with_data": 0}
        return {
            "period": f"{week_start} ~ {week_end}",
            "days_with_data": 7,
            "health_score": report.health_score,
            "report_id": report.id,
        }


weekly_report_service = WeeklyReportService()
