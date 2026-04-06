"""慢病风险评估服务 — 心血管风险(改良Framingham) + 代谢综合征(IDF) + 90天趋势"""
import logging
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.basic_health import BasicHealthData
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.weight import WeightRecord

logger = logging.getLogger(__name__)

AGE_PTS_M = [(30, 0), (35, 2), (40, 5), (45, 7), (50, 8), (55, 10), (60, 11), (65, 12), (70, 14)]
AGE_PTS_F = [(30, 0), (35, 2), (40, 4), (45, 5), (50, 7), (55, 8), (60, 9), (65, 10), (70, 11)]
TC_THRESH = [4.14, 5.18, 6.22, 7.25]
HDL_PTS = [(1.55, -1), (1.30, 0), (1.03, 1)]
SBP_PTS_M = [(120, 0), (130, 1), (140, 1), (160, 2)]
SBP_PTS_F = [(120, 0), (130, 2), (140, 3), (160, 4)]
RISK_LEVELS = [(10, "低"), (20, "中等"), (30, "高")]


def _calc_age(bd: Optional[date]) -> Optional[int]:
    if not bd:
        return None
    t = date.today()
    return t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))


def _lookup(age, is_male):
    table = AGE_PTS_M if is_male else AGE_PTS_F
    return max((p for a, p in table if age >= a), default=0)


def _tc_pts(tc, is_male):
    if tc < TC_THRESH[0]: return 0
    if tc < TC_THRESH[1]: return 3 if is_male else 2
    if tc < TC_THRESH[2]: return 5 if is_male else 4
    if tc < TC_THRESH[3]: return 6 if is_male else 5
    return 8 if is_male else 7


def _hdl_pts(hdl):
    for t, p in HDL_PTS:
        if hdl >= t: return p
    return 2


def _sbp_pts(sbp, is_male):
    table = SBP_PTS_M if is_male else SBP_PTS_F
    return max((p for t, p in table if sbp >= t), default=0)


def _to_prob(score, is_male):
    b, c = (0.88936, 0.04826) if is_male else (0.95012, 0.03352)
    return round(max(0, min((1 - b ** math.exp(score * c)) * 100, 100)), 1)


def _risk_level(p):
    for t, l in RISK_LEVELS:
        if p < t: return l
    return "极高"


def _trend(vals):
    n = len(vals)
    if n < 2: return None
    xm, ym = (n - 1) / 2, sum(vals) / n
    num = sum((i - xm) * (v - ym) for i, v in enumerate(vals))
    den = sum((i - xm) ** 2 for i in range(n))
    if den == 0: return "稳定"
    slope = num / den
    threshold = 0.01 * abs(ym) if ym else 0.1
    if abs(slope) < threshold: return "稳定"
    return "上升" if slope > 0 else "下降"


def _ms_criterion(name, threshold, value, check_fn):
    if value is None:
        return {"name": name, "threshold": threshold, "value": None, "status": "数据缺失", "met": False}
    met = check_fn(value)
    display = f"{value}" if not isinstance(value, tuple) else f"{value[0]}/{value[1]}"
    return {"name": name, "threshold": threshold, "value": display, "status": "异常" if met else "正常", "met": met}


class ChronicRiskService:

    def _latest(self, db, model, uid, order_col="record_date"):
        return db.query(model).filter(model.user_id == uid).order_by(desc(getattr(model, order_col))).first()

    def _garmin_recent(self, db, uid, days=7):
        cutoff = date.today() - timedelta(days=days)
        return db.query(GarminData).filter(GarminData.user_id == uid, GarminData.record_date >= cutoff).order_by(GarminData.record_date).all()

    def assess_cardiovascular_risk(self, db: Session, user_id: int) -> Dict[str, Any]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user: return {"error": "用户不存在"}
        age, is_male = _calc_age(user.birth_date), (user.gender or "男") == "男"
        health = self._latest(db, BasicHealthData, user_id)
        bp_rec = self._latest(db, BloodPressureRecord, user_id)
        g7 = self._garmin_recent(db, user_id)

        sbp = (bp_rec.systolic if bp_rec else None) or (health.systolic_bp if health else None)
        tc = health.total_cholesterol if health else None
        hdl = health.hdl_cholesterol if health else None

        missing = []
        if not age: missing.append("出生日期")
        if not tc: missing.append("总胆固醇")
        if not hdl: missing.append("HDL胆固醇")
        if not sbp: missing.append("血压")

        score, breakdown = 0, {}
        if age is not None:
            p = _lookup(age, is_male); score += p
            breakdown["age"] = {"value": age, "points": p}
            if age < 30 or age > 74: breakdown["age"]["warning"] = "超出Framingham适用范围(30-74)"
        breakdown["gender"] = {"value": "男" if is_male else "女", "points": 0}
        if tc: p = _tc_pts(tc, is_male); score += p; breakdown["total_cholesterol"] = {"value": tc, "points": p}
        if hdl: p = _hdl_pts(hdl); score += p; breakdown["hdl_cholesterol"] = {"value": hdl, "points": p}
        if sbp: p = _sbp_pts(sbp, is_male); score += p; breakdown["systolic_bp"] = {"value": sbp, "points": p, "treated": False}

        prob = _to_prob(score, is_male) if len(missing) < 3 else 0
        ci = [round(max(0, prob * 0.8), 1), round(min(100, prob * 1.2), 1)]

        wearable, adj = {}, 0.0
        if g7:
            rhr = [g.resting_heart_rate for g in g7 if g.resting_heart_rate]
            if rhr:
                avg = sum(rhr) / len(rhr); a = 1.0 if avg > 75 else (-0.5 if avg < 60 else 0); adj += a
                wearable["resting_heart_rate"] = {"value": round(avg), "adjustment": f"{a:+.1f}%", "evidence": "B级"}
            hrv = [g.hrv for g in g7 if g.hrv]
            if hrv:
                avg = sum(hrv) / len(hrv); a = 0.5 if avg < 50 else (-0.5 if avg > 100 else 0); adj += a
                wearable["hrv"] = {"value": round(avg, 1), "adjustment": f"{a:+.1f}%", "evidence": "C级"}
            wk = sum((g.moderate_intensity_minutes or 0) + (g.vigorous_intensity_minutes or 0) * 2 for g in g7)
            a = -1.0 if wk >= 150 else (0.5 if wk < 60 else 0); adj += a
            wearable["exercise_minutes_weekly"] = {"value": wk, "adjustment": f"{a:+.1f}%", "evidence": "A级"}

        fp = round(max(0, prob + adj), 1)
        recs = []
        if tc and tc > 5.18: recs.append("降低LDL至<3.4 mmol/L")
        if sbp and sbp >= 130: recs.append("控制血压至<130/80 mmHg")
        if not recs: recs.append("维持当前健康生活方式")

        return {"framingham_score": score, "risk_level": _risk_level(fp), "10yr_event_probability": f"{fp}%",
                "confidence_interval": ci, "score_breakdown": breakdown, "wearable_modifiers": wearable,
                "recommendations": recs, "missing_data": missing,
                "last_labs_date": str(health.record_date) if health else None}

    def assess_metabolic_syndrome(self, db: Session, user_id: int) -> Dict[str, Any]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user: return {"error": "用户不存在"}
        is_male = (user.gender or "男") == "男"
        h = self._latest(db, BasicHealthData, user_id)
        bp = self._latest(db, BloodPressureRecord, user_id)
        w = self._latest(db, WeightRecord, user_id)

        bmi = (w.bmi if w and w.bmi else (h.bmi if h else None))
        sbp = (bp.systolic if bp else None) or (h.systolic_bp if h else None)
        dbp = (bp.diastolic if bp else None) or (h.diastolic_bp if h else None)
        glucose = h.blood_glucose if h else None
        hdl = h.hdl_cholesterol if h else None
        tg = h.triglycerides if h else None

        criteria = [
            _ms_criterion("腰围/BMI替代", "BMI≥25(替代)", bmi, lambda v: v >= 25),
            _ms_criterion("血压", "≥130/85 mmHg",
                          (sbp, dbp) if sbp and dbp else None,
                          lambda v: v[0] >= 130 or v[1] >= 85),
            _ms_criterion("空腹血糖", "≥5.6 mmol/L", glucose, lambda v: v >= 5.6),
            _ms_criterion("HDL胆固醇", "男<1.03/女<1.29 mmol/L", hdl,
                          lambda v: v < (1.03 if is_male else 1.29)),
            _ms_criterion("甘油三酯", "≥1.7 mmol/L", tg, lambda v: v >= 1.7),
        ]
        # Fix blood pressure display
        for c in criteria:
            if c["name"] == "血压" and isinstance(c["value"], str) and c["value"].startswith("("):
                c["value"] = f"{sbp}/{dbp}" if sbp and dbp else None

        met = sum(1 for c in criteria if c["met"])
        detected = met >= 3
        bmi_info = None
        if bmi:
            cat = "体重过低" if bmi < 18.5 else ("正常" if bmi < 23 else ("超重" if bmi < 25 else "肥胖"))
            bmi_info = {"value": round(bmi, 1), "category": cat}

        recs = []
        if detected: recs.append("建议内分泌科就诊，进行系统评估")
        if bmi and bmi >= 24: recs.append("减重至BMI<24")
        if tg and tg >= 1.7: recs.append("控制甘油三酯（减少精制碳水、增加omega-3）")

        return {"detected": detected, "criteria_met": met, "criteria_total": 5, "criteria": criteria,
                "bmi": bmi_info, "risk_interpretation": f"当前满足{met}/5项标准，{'已达到' if detected else '尚未达到'}代谢综合征诊断阈值",
                "recommendations": recs}

    def assess_comprehensive_risk(self, db: Session, user_id: int) -> Dict[str, Any]:
        cv = self.assess_cardiovascular_risk(db, user_id)
        ms = self.assess_metabolic_syndrome(db, user_id)

        g90 = self._garmin_recent(db, user_id, 90)
        trend_info = {"direction": "数据不足", "improving": [], "worsening": []}
        if g90:
            for vals, up_label, down_label in [
                ([g.resting_heart_rate for g in g90 if g.resting_heart_rate], "静息心率上升趋势", "静息心率下降趋势"),
                ([g.steps for g in g90 if g.steps], "日步数减少趋势", "日步数增长趋势"),
            ]:
                t = _trend(vals) if vals else None
                if t == "上升": (trend_info["worsening" if "心率" in up_label else "worsening"]).append(up_label)
                elif t == "下降": (trend_info["improving" if "心率" in down_label else "improving"]).append(down_label)

            # 静息心率上升→恶化, 步数上升→改善（修正方向）
            rhr_t = _trend([g.resting_heart_rate for g in g90 if g.resting_heart_rate])
            steps_t = _trend([g.steps for g in g90 if g.steps])
            trend_info = {"direction": "数据不足", "improving": [], "worsening": []}
            if rhr_t == "下降": trend_info["improving"].append("静息心率下降趋势")
            elif rhr_t == "上升": trend_info["worsening"].append("静息心率上升趋势")
            if steps_t == "上升": trend_info["improving"].append("日步数增长趋势")
            elif steps_t == "下降": trend_info["worsening"].append("日步数减少趋势")

        cutoff = date.today() - timedelta(days=90)
        weights = db.query(WeightRecord).filter(WeightRecord.user_id == user_id, WeightRecord.record_date >= cutoff).order_by(WeightRecord.record_date).all()
        if len(weights) >= 2:
            wt = _trend([w.weight for w in weights])
            diff = round(abs(weights[-1].weight - weights[0].weight), 1)
            if wt == "下降": trend_info["improving"].append(f"体重减轻{diff}kg")
            elif wt == "上升": trend_info["worsening"].append(f"体重增加{diff}kg")

        if trend_info["improving"] or trend_info["worsening"]:
            ni, nw = len(trend_info["improving"]), len(trend_info["worsening"])
            trend_info["direction"] = "改善" if ni > nw else ("恶化" if nw > ni else "混合")

        health = self._latest(db, BasicHealthData, user_id)
        missing = cv.get("missing_data", [])
        level = cv.get("risk_level", "未知")
        if ms.get("detected") and level == "低": level = "中等"

        return {
            "overall_risk_level": level,
            "cardiovascular": {"framingham_score": cv.get("framingham_score"), "risk_level": cv.get("risk_level"),
                               "10yr_event_probability": cv.get("10yr_event_probability"),
                               "confidence_interval": cv.get("confidence_interval"),
                               "contributing_factors": missing, "wearable_adjustments": cv.get("wearable_modifiers", {})},
            "metabolic_syndrome": {"detected": ms.get("detected"), "criteria_met": ms.get("criteria_met"),
                                   "criteria_total": ms.get("criteria_total"),
                                   "details": [c["name"] + c["status"] for c in ms.get("criteria", [])]},
            "trend_90d": trend_info,
            "recommendations": list(set(cv.get("recommendations", []) + ms.get("recommendations", []))),
            "population_applicability": "本评估基于Framingham队列，适用于30-74岁无已知心血管疾病人群",
            "data_quality": {"completeness": round(max(0, 1 - len(missing) / 7), 2), "missing": missing,
                             "last_labs_date": str(health.record_date) if health else None},
        }


chronic_risk_service = ChronicRiskService()
