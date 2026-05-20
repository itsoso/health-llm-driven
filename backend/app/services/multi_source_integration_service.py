"""多源数据整合服务 — 综合健康画像、数据完整性、跨模态关联"""
import logging
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import case, desc, distinct, func
from sqlalchemy.orm import Session

from app.models.basic_health import BasicHealthData
from app.models.daily_health import DietRecord, GarminData
from app.models.user import User
from app.models.weight import WeightRecord

logger = logging.getLogger(__name__)
SOURCE_WEIGHTS = {"garmin": 0.30, "diet": 0.25, "weight": 0.15, "basic_health": 0.20, "genetic": 0.10}


def _freshness(d: Optional[date]) -> str:
    if not d: return "无数据"
    delta = (date.today() - d).days
    if delta == 0: return "今天"
    if delta <= 30: return f"{delta}天前"
    if delta <= 90: return f"{delta // 7}周前"
    if delta <= 365: return f"{delta // 30}月前"
    return "超过1年"


def _age(bd):
    if not bd: return None
    t = date.today()
    return t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))


def _pearson(xs, ys):
    n = len(xs)
    if n < 5 or len(ys) != n: return None
    xm, ym = sum(xs) / n, sum(ys) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    dx = sum((x - xm) ** 2 for x in xs)
    dy = sum((y - ym) ** 2 for y in ys)
    den = math.sqrt(dx * dy)
    return round(num / den, 3) if den else None


def _strength(r):
    if r is None: return "不足"
    a = abs(r)
    if a < 0.3: return "弱"
    if a < 0.6: return "中等"
    if a < 0.8: return "较强"
    return "强"


class MultiSourceIntegrationService:

    def get_integrated_profile(self, db: Session, user_id: int) -> Dict[str, Any]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user: return {"error": "用户不存在"}
        age_val, gender = _age(user.birth_date), user.gender or "未设置"

        garmin = db.query(GarminData).filter(GarminData.user_id == user_id).order_by(desc(GarminData.record_date)).first()
        # P4 多源合并: 同一日期可能有 garmin/apple-watch/ringconn/oura 多行,
        # 每字段按 source 优先级独立挑值. 见 multi_source_merger 优先级表.
        garmin_rows: list = []
        if garmin:
            garmin_rows = db.query(GarminData).filter(
                GarminData.user_id == user_id,
                GarminData.record_date == garmin.record_date,
            ).all()
        weight = db.query(WeightRecord).filter(WeightRecord.user_id == user_id).order_by(desc(WeightRecord.record_date)).first()
        health = db.query(BasicHealthData).filter(BasicHealthData.user_id == user_id).order_by(desc(BasicHealthData.record_date)).first()

        today = date.today()
        diet_today = db.query(DietRecord).filter(DietRecord.user_id == user_id, DietRecord.record_date == today).all()

        gm = None
        if garmin:
            from app.services.multi_source_merger import merge_rows
            merged = merge_rows(garmin_rows, [
                "resting_heart_rate", "hrv", "sleep_score", "steps",
                "stress_level", "body_battery_current", "spo2_avg",
            ])
            v = merged["values"]
            gm = {"date": str(garmin.record_date),
                  "resting_hr": v.get("resting_heart_rate"),
                  "hrv": v.get("hrv"),
                  "sleep_score": v.get("sleep_score"),
                  "steps": v.get("steps"),
                  "stress_level": v.get("stress_level"),
                  "body_battery_current": v.get("body_battery_current"),
                  "spo2_avg": v.get("spo2_avg"),
                  "sources": merged["sources"]}  # P4: 每字段 winning source, LLM source-aware

        bc = {"date": str(weight.record_date), "weight": weight.weight, "bmi": weight.bmi,
              "body_fat_pct": weight.body_fat_percentage} if weight else None

        labs = None
        if health:
            bp = f"{health.systolic_bp}/{health.diastolic_bp}" if health.systolic_bp and health.diastolic_bp else None
            labs = {"date": str(health.record_date), "total_cholesterol": health.total_cholesterol,
                    "blood_glucose": health.blood_glucose, "blood_pressure": bp}

        ds = None
        if diet_today:
            ds = {"total_calories": round(sum(d.calories or 0 for d in diet_today)),
                  "protein_g": round(sum(d.protein or 0 for d in diet_today)), "meals_logged": len(diet_today)}

        gen = []
        try:
            from app.models.genetic_data import GeneticVariant
            vs = db.query(GeneticVariant).filter(GeneticVariant.user_id == user_id, GeneticVariant.risk_level.in_(["高风险", "中风险"])).limit(5).all()
            gen = [f"{v.gene_name} {v.genotype}({v.result_label})" for v in vs]
        except Exception: pass

        sources = [s for s, cond in [("garmin", garmin), ("diet", diet_today), ("weight", weight), ("basic_health", health), ("genetic", gen)] if cond]

        parts = []
        if age_val: parts.append(f"{age_val}岁{gender}")
        if bc and bc.get("bmi"):
            b = bc["bmi"]; cat = "体重过低" if b < 18.5 else ("正常" if b < 23 else ("超重" if b < 25 else "肥胖"))
            parts.append(f"BMI{cat}({b})")
        if gm and gm.get("hrv"):
            h = gm["hrv"]; lvl = "偏低" if h < 50 else ("中等" if h <= 100 else "良好"); parts.append(f"心率变异性{lvl}({h}ms)")
        if gm and gm.get("sleep_score"):
            s = gm["sleep_score"]; lvl = "差" if s < 60 else ("良好" if s <= 80 else "优秀"); parts.append(f"睡眠质量{lvl}({s}分)")

        return {
            "user_summary": {"name": user.name, "age": age_val, "gender": gender, "data_sources": sources},
            "latest_metrics": {"garmin": gm, "body_composition": bc, "labs": labs, "diet_today": ds, "genetic_highlights": gen},
            "health_narrative": "，".join(parts) + "。" if parts else "数据不足，无法生成健康画像。",
            "data_freshness": {"garmin": _freshness(garmin.record_date if garmin else None),
                               "weight": _freshness(weight.record_date if weight else None),
                               "labs": _freshness(health.record_date if health else None),
                               "diet": _freshness(today if diet_today else None),
                               "genetic": "一次性数据" if gen else "未录入"}}

    def get_data_completeness(self, db: Session, user_id: int) -> Dict[str, Any]:
        c30 = date.today() - timedelta(days=30)
        si: Dict[str, Any] = {}

        # Garmin — SQL 聚合替代全量加载
        g_stats = db.query(
            func.count(distinct(GarminData.record_date)).label("days"),
            func.sum(case((GarminData.avg_heart_rate.isnot(None), 1), else_=0)).label("hr_cnt"),
            func.sum(case((GarminData.sleep_score.isnot(None), 1), else_=0)).label("sleep_cnt"),
            func.sum(case((GarminData.hrv.isnot(None), 1), else_=0)).label("hrv_cnt"),
            func.sum(case((GarminData.spo2_avg.isnot(None), 1), else_=0)).label("spo2_cnt"),
        ).filter(GarminData.user_id == user_id, GarminData.record_date >= c30).first()
        g_total = db.query(func.count(GarminData.id)).filter(GarminData.user_id == user_id).scalar() or 0
        g_last = db.query(func.max(GarminData.record_date)).filter(GarminData.user_id == user_id).scalar()
        g_days = g_stats.days if g_stats else 0; n = max(g_days, 1)
        g_cov = round(g_days / 30, 2)
        si["garmin"] = {
            "status": "活跃" if g_last and (date.today() - g_last).days <= 7 else ("部分活跃" if g_last else "未接入"),
            "coverage_30d": g_cov, "total_records": g_total,
            "last_update": str(g_last) if g_last else None, "missing_days_30d": 30 - g_days,
            "key_metrics": {k: {"coverage": round(cnt / n, 2), "status": "充足" if cnt / n > 0.7 else "部分"} for k, cnt in [
                ("heart_rate", g_stats.hr_cnt or 0), ("sleep", g_stats.sleep_cnt or 0),
                ("hrv", g_stats.hrv_cnt or 0), ("spo2", g_stats.spo2_cnt or 0)]}}

        # Diet — SQL 聚合替代全量加载
        d_stats = db.query(
            func.count(distinct(DietRecord.record_date)).label("days"),
            func.count(DietRecord.id).label("total_30d"),
        ).filter(DietRecord.user_id == user_id, DietRecord.record_date >= c30).first()
        d_total = db.query(func.count(DietRecord.id)).filter(DietRecord.user_id == user_id).scalar() or 0
        d_last = db.query(func.max(DietRecord.record_date)).filter(DietRecord.user_id == user_id).scalar()
        d_days = d_stats.days if d_stats else 0; avg_m = round((d_stats.total_30d or 0) / max(d_days, 1), 1)
        si["diet"] = {"status": "活跃" if d_last and (date.today() - d_last).days <= 7 else ("部分活跃" if d_last else "未接入"),
                      "coverage_30d": round(d_days / 30, 2), "total_records": d_total,
                      "last_update": str(d_last) if d_last else None, "avg_meals_per_day": avg_m}
        if avg_m < 2.5 and d_days > 0: si["diet"]["recommendation"] = "建议每天记录3餐以提高营养分析准确度"

        # Weight
        w_total = db.query(func.count(WeightRecord.id)).filter(WeightRecord.user_id == user_id).scalar() or 0
        w_last = db.query(func.max(WeightRecord.record_date)).filter(WeightRecord.user_id == user_id).scalar()
        w30 = db.query(WeightRecord).filter(WeightRecord.user_id == user_id, WeightRecord.record_date >= c30).count()
        si["weight"] = {"status": "活跃" if w_last and (date.today() - w_last).days <= 7 else ("低频" if w_last else "未接入"),
                        "coverage_30d": round(w30 / 30, 2), "total_records": w_total,
                        "last_update": str(w_last) if w_last else None}

        # Basic health
        h_total = db.query(func.count(BasicHealthData.id)).filter(BasicHealthData.user_id == user_id).scalar() or 0
        h_last = db.query(func.max(BasicHealthData.record_date)).filter(BasicHealthData.user_id == user_id).scalar()
        stale = (date.today() - h_last).days if h_last else None
        lh = db.query(BasicHealthData).filter(BasicHealthData.user_id == user_id).order_by(desc(BasicHealthData.record_date)).first()
        avail, miss = [], []
        if lh:
            for label, field in [("血压", lh.systolic_bp), ("血脂", lh.total_cholesterol), ("血糖", lh.blood_glucose), ("BMI", lh.bmi)]:
                (avail if field else miss).append(label)
        si["basic_health"] = {"status": "低频" if h_last else "未接入", "total_records": h_total,
                              "last_update": str(h_last) if h_last else None, "staleness_days": stale,
                              "available_metrics": avail, "missing_metrics": miss}

        # Genetic
        gi = {"status": "未接入", "total_variants": 0}
        try:
            from app.models.genetic_data import GeneticVariant
            gc = db.query(func.count(GeneticVariant.id)).filter(GeneticVariant.user_id == user_id).scalar() or 0
            if gc:
                cats = [c[0] for c in db.query(GeneticVariant.category).filter(GeneticVariant.user_id == user_id).distinct().all()]
                gi = {"status": "已录入", "total_variants": gc, "categories": cats}
        except Exception: pass
        si["genetic"] = gi

        cov = {"garmin": g_cov, "diet": round(d_days / 30, 2), "weight": round(w30 / 30, 2),
               "basic_health": 1.0 if h_last and stale and stale < 180 else (0.5 if h_last else 0),
               "genetic": 1.0 if gi["total_variants"] > 0 else 0}
        overall = round(sum(SOURCE_WEIGHTS[k] * cov.get(k, 0) for k in SOURCE_WEIGHTS) / sum(SOURCE_WEIGHTS.values()), 2)

        recs = []
        if cov["diet"] < 0.5: recs.append("饮食记录不足，建议每天记录3餐")
        if stale and stale > 90: recs.append(f"体检数据已{stale}天未更新，建议定期录入")
        if "血脂" not in avail: recs.append("缺少血脂数据，影响心血管风险评估")
        if cov["garmin"] < 0.5: recs.append("Garmin数据覆盖不足，请检查设备同步")

        return {"overall_completeness": overall, "sources": si, "recommendations": recs}

    def find_correlations(self, db: Session, user_id: int, days: int = 30) -> Dict[str, Any]:
        days = min(max(days, 14), 90)
        cutoff = date.today() - timedelta(days=days)
        garmin = db.query(GarminData).filter(GarminData.user_id == user_id, GarminData.record_date >= cutoff).order_by(GarminData.record_date).all()
        diets = db.query(DietRecord).filter(DietRecord.user_id == user_id, DietRecord.record_date >= cutoff).all()

        gbd = {g.record_date: g for g in garmin}
        dbd: Dict[date, Dict] = {}
        for d in diets:
            e = dbd.setdefault(d.record_date, {"calories": 0, "protein": 0})
            e["calories"] += d.calories or 0; e["protein"] += d.protein or 0

        dates = sorted(gbd.keys())
        corrs = []

        def _check(name, sa, sb, ma, mb, pairs):
            if len(pairs) < 5: return
            xs, ys = zip(*pairs)
            r = _pearson(list(xs), list(ys))
            if r and abs(r) > 0.2:
                corrs.append({"finding": f"{ma}与{mb}" + ("正相关" if r > 0 else "负相关"),
                              "source_a": sa, "source_b": sb, "metric_a": ma, "metric_b": mb,
                              "direction": "正相关" if r > 0 else "负相关", "occurrences": len(pairs),
                              "strength": _strength(r), "evidence_level": "D级(个人观察)"})

        # Sleep → next day steps
        pairs = [(float(gbd[dates[i]].sleep_score), float(gbd[dates[i + 1]].steps))
                 for i in range(len(dates) - 1) if (dates[i + 1] - dates[i]).days == 1
                 and gbd[dates[i]].sleep_score and gbd[dates[i + 1]].steps]
        _check("sleep_steps", "garmin_sleep", "garmin_activity", "睡眠分数", "次日步数", pairs)

        # Active minutes → sleep score
        pairs = [(float(g.active_minutes), float(g.sleep_score)) for g in garmin if g.active_minutes and g.sleep_score]
        _check("active_sleep", "garmin_activity", "garmin_sleep", "活动分钟数", "睡眠分数", pairs)

        # Protein → next day HRV
        pairs = [(dbd[dates[i]]["protein"], float(gbd[dates[i + 1]].hrv))
                 for i in range(len(dates) - 1) if (dates[i + 1] - dates[i]).days == 1
                 and dates[i] in dbd and dbd[dates[i]]["protein"] > 0 and gbd[dates[i + 1]].hrv]
        _check("protein_hrv", "diet", "garmin", "蛋白质摄入", "次日HRV", pairs)

        # RHR → stress
        pairs = [(float(g.resting_heart_rate), float(g.stress_level)) for g in garmin if g.resting_heart_rate and g.stress_level]
        _check("rhr_stress", "garmin", "garmin", "静息心率", "压力水平", pairs)

        return {"period": f"近{days}天", "correlations": corrs, "sample_size": len(dates),
                "caveat": "关联分析基于个人数据的简单统计，不代表因果关系。样本量小，结论仅供参考。"}


multi_source_integration_service = MultiSourceIntegrationService()
