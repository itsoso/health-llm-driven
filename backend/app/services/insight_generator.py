"""
Insight Generator — 每日跨事件 pattern 洞察.

区别于 DailyRecommendation (actionable 建议):
  Insight 是"我发现你 X 和 Y 有关联", 不是"今天做什么".

分层生成器:
  Tier 1: 确定性规则 (基因 × 用药 × 化验三角)
  Tier 2: 时序 pattern (最近 N 天事件关联)
  Fallback: 基于 KG 的画像摘要

每个生成器返回 Optional[InsightCandidate], 主函数选分数最高的.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ─────────────────────── 数据结构 ───────────────────────


@dataclass
class InsightCandidate:
    """生成器产出的候选 insight."""
    kind: str                              # gene_pgx / lab_trend / hrv_pattern / profile_summary
    rule_id: str
    title: str
    body: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.7
    severity: str = "info"                 # info / low / medium

    def score(self) -> float:
        """综合排序分: confidence × severity weight."""
        sev_weight = {"info": 0.5, "low": 0.7, "medium": 1.0}.get(self.severity, 0.5)
        return self.confidence * sev_weight


# ─────────────────────── PGx + 用药规则 ───────────────────────


# PGx 位点 → 受影响药物名/类别 (中文通用名小写匹配)
_PGX_DRUG_MAP = {
    "CYP2C19": {
        "drugs": ["氯吡格雷", "奥美拉唑", "兰索拉唑", "泮托拉唑", "西酞普兰", "艾司西酞普兰"],
        "class_keywords": ["ppi", "质子泵抑制剂"],
        "hint": "你有 CYP2C19 慢/中间代谢位点, 氯吡格雷(波立维)可能抗血小板不足、PPI(奥美拉唑等)血药浓度升高",
    },
    "CYP2D6": {
        "drugs": ["美托洛尔", "卡维地洛", "氟西汀", "帕罗西汀", "可待因", "曲马多", "他莫昔芬"],
        "class_keywords": ["β受体阻滞剂"],
        "hint": "你有 CYP2D6 慢代谢, 美托洛尔/可待因/曲马多等代谢变慢, 标准剂量可能血药浓度偏高",
    },
    "SLCO1B1": {
        "drugs": ["阿托伐他汀", "瑞舒伐他汀", "辛伐他汀", "普伐他汀"],
        "class_keywords": ["他汀", "statin"],
        "hint": "你有 SLCO1B1 变异, 他汀类药物肌病风险上升, 建议从低剂量开始 + 查 CK",
    },
    "VKORC1": {
        "drugs": ["华法林", "warfarin"],
        "class_keywords": ["抗凝"],
        "hint": "你有 VKORC1 高敏感位点, 华法林需要的剂量通常比常人低, 需 INR 密切监测",
    },
    "CYP1A2": {
        "drugs": ["咖啡因", "茶碱", "氯氮平"],
        "class_keywords": ["caffeine"],
        "hint": "你有 CYP1A2 慢代谢, 咖啡因清除较慢, 下午 2 点后咖啡可能影响睡眠",
    },
    "HLA-B*5701": {
        "drugs": ["阿巴卡韦", "abacavir"],
        "hint": "你有 HLA-B*5701, 阿巴卡韦严重过敏风险, 禁用",
    },
    "DPYD": {
        "drugs": ["氟尿嘧啶", "卡培他滨", "5-fu"],
        "hint": "你有 DPYD 变异, 氟尿嘧啶类化疗药严重毒性风险",
    },
    "ALDH2": {
        "drugs": ["硝酸甘油"],
        "class_keywords": ["酒精", "乙醇", "白酒", "红酒", "啤酒"],
        "hint": "你有 ALDH2 变异 (乙醛脱氢酶缺陷), 酒精转化慢, 长期饮酒食管癌风险显著升高",
    },
}


def _gen_pgx_medication_caution(db: Session, user_id: int) -> Optional[InsightCandidate]:
    """基因 PGx × 当前在服药 → 安全提示."""
    from app.models.genetic_data import GeneticVariant
    from app.models.medication import Medication

    # 查有临床意义的 PGx 位点
    genes = db.query(GeneticVariant).filter(
        GeneticVariant.user_id == user_id,
        GeneticVariant.gene_name.in_(list(_PGX_DRUG_MAP.keys())),
    ).all()
    if not genes:
        return None

    # 查在服药
    active_meds = db.query(Medication).filter(
        Medication.user_id == user_id,
        Medication.is_active.is_(True),
    ).all()
    if not active_meds:
        # 用户没在服药, 但位点有, 降级提示
        return None

    # 匹配: 基因 × 药名 (模糊包含)
    med_names = [(m.id, (m.name or "").lower()) for m in active_meds]
    for g in genes:
        info = _PGX_DRUG_MAP.get(g.gene_name)
        if not info:
            continue
        drug_keywords = [d.lower() for d in info.get("drugs", [])]
        drug_keywords += [k.lower() for k in info.get("class_keywords", [])]
        matched_med_ids = []
        matched_med_names = []
        for mid, mname in med_names:
            for kw in drug_keywords:
                if kw in mname:
                    matched_med_ids.append(mid)
                    matched_med_names.append(mname)
                    break
        if matched_med_ids:
            title = f"基因 × 在服药: {g.gene_name} 可能影响 {', '.join(matched_med_names[:2])}"
            body = (
                f"{info['hint']}\n\n"
                f"你当前在服 **{', '.join(matched_med_names)}**, "
                f"这些药代谢/作用可能受 {g.gene_name} ({g.genotype or '你的基因型'}) 影响.\n\n"
                f"**建议**: 下次复诊时可以主动向医生说明你的 {g.gene_name} 基因型, "
                f"让医生决定是否调整剂量或换药."
            )
            return InsightCandidate(
                kind="gene_pgx",
                rule_id=f"pgx_caution_{g.gene_name.lower()}",
                title=title,
                body=body,
                evidence={
                    "gene_variant_id": g.id,
                    "gene_name": g.gene_name,
                    "genotype": g.genotype,
                    "medication_ids": matched_med_ids,
                    "cite": f"基于 {g.gene_name} {g.genotype or ''} 位点 + 在服药物 {', '.join(matched_med_names)}",
                },
                confidence=0.85 if g.risk_level == "high" else 0.75,
                severity="medium" if g.risk_level == "high" else "low",
            )
    return None


# ─────────────────────── 化验趋势规则 ───────────────────────


def _gen_abnormal_lab_trend(db: Session, user_id: int) -> Optional[InsightCandidate]:
    """异常化验近 6 月趋势 (最早 vs 最近 同一指标)."""
    from app.models.family_health import MedicalIndicator
    from sqlalchemy import func

    cutoff = date.today() - timedelta(days=180)
    rows = (
        db.query(MedicalIndicator)
        .filter(
            MedicalIndicator.user_id == user_id,
            MedicalIndicator.record_date >= cutoff,
            MedicalIndicator.value.isnot(None),
        )
        .order_by(MedicalIndicator.record_date.desc())
        .all()
    )
    if len(rows) < 2:
        return None

    # 按 name 分组, 找出有 ≥ 2 次测量的指标
    by_name: Dict[str, List[Any]] = {}
    for r in rows:
        by_name.setdefault(r.name or "?", []).append(r)

    # 挑一个"变化最显著"的异常指标 (最新一次 vs 最老一次, 变化 % 最大)
    best_candidate = None
    best_change_abs = 0.0
    for name, series in by_name.items():
        if len(series) < 2:
            continue
        # 排好序: series 已按 desc
        latest = series[0]
        earliest = series[-1]
        if latest.value is None or earliest.value is None or earliest.value == 0:
            continue
        change_pct = ((latest.value - earliest.value) / earliest.value) * 100
        # 只关心异常或近异常的
        is_abnormal = bool(getattr(latest, "is_abnormal", False))
        if not is_abnormal and abs(change_pct) < 20:
            continue
        if abs(change_pct) > best_change_abs:
            best_change_abs = abs(change_pct)
            direction = "上升" if change_pct > 0 else "下降"
            best_candidate = {
                "name": name, "latest": latest, "earliest": earliest,
                "change_pct": change_pct, "direction": direction,
                "is_abnormal": is_abnormal, "series_count": len(series),
            }

    if not best_candidate:
        return None

    c = best_candidate
    latest, earliest = c["latest"], c["earliest"]
    sign = "+" if c["change_pct"] > 0 else ""
    unit = latest.unit or ""
    title = f"{c['name']} 近 {(latest.record_date - earliest.record_date).days} 天{c['direction']} {abs(c['change_pct']):.0f}%"
    body = (
        f"你的 **{c['name']}**:\n"
        f"- {earliest.record_date}: {earliest.value}{unit}\n"
        f"- {latest.record_date}: **{latest.value}{unit}** ({sign}{c['change_pct']:.1f}%)\n\n"
        f"{'⚠️ 最新一次超参考范围.' if c['is_abnormal'] else '虽在范围内, 但变化幅度大.'}\n\n"
        f"**建议**: 回看期间饮食/运动/用药变化, 下次复查继续观察."
    )
    return InsightCandidate(
        kind="lab_trend",
        rule_id="lab_trend_change",
        title=title,
        body=body,
        evidence={
            "indicator_name": c["name"],
            "latest": {"value": latest.value, "unit": unit, "date": latest.record_date.isoformat()},
            "earliest": {"value": earliest.value, "unit": unit, "date": earliest.record_date.isoformat()},
            "change_pct": c["change_pct"],
            "series_count": c["series_count"],
            "cite": f"基于 {c['series_count']} 次 {c['name']} 化验",
        },
        confidence=0.8 if c["is_abnormal"] else 0.65,
        severity="medium" if c["is_abnormal"] else "low",
    )


# ─────────────────────── HRV 跨事件 pattern ───────────────────────


def _gen_hrv_stressor_pattern(db: Session, user_id: int) -> Optional[InsightCandidate]:
    """最近 14 天 HRV 最低 3 天 vs 其他天的睡眠/压力差异."""
    # 多源按日合并 → 每天一行,rows 即天数 (low3 vs others 的对比才成立)
    from app.services.garmin_daily_merged import merged_daily_rows

    cutoff = date.today() - timedelta(days=14)
    rows = merged_daily_rows(
        db, user_id, since=cutoff, require_metrics=["hrv"], ascending=True,
    )
    if len(rows) < 7:  # 至少 7 天才有对比意义
        return None

    sorted_by_hrv = sorted(rows, key=lambda r: r.hrv or 999)
    low_days = sorted_by_hrv[:3]
    high_days = sorted_by_hrv[-(len(rows) - 3):]  # 其余

    def _avg(items, attr):
        vals = [getattr(it, attr) for it in items if getattr(it, attr) is not None]
        return sum(vals) / len(vals) if vals else None

    sleep_low = _avg(low_days, "sleep_score")
    sleep_other = _avg(high_days, "sleep_score")
    stress_low = _avg(low_days, "stress_level")
    stress_other = _avg(high_days, "stress_level")
    hrv_low = _avg(low_days, "hrv")
    hrv_other = _avg(high_days, "hrv")

    # 需要至少一个维度有显著差异 (> 15%)
    insights: List[str] = []
    if sleep_low is not None and sleep_other is not None and sleep_other:
        sleep_diff_pct = (sleep_other - sleep_low) / sleep_other * 100
        if sleep_diff_pct > 10:
            insights.append(
                f"🌙 HRV 最低 3 天, 平均睡眠评分 {sleep_low:.0f} "
                f"(其他天 {sleep_other:.0f}, 低 {sleep_diff_pct:.0f}%)"
            )
    if stress_low is not None and stress_other is not None and stress_other:
        stress_diff_pct = (stress_low - stress_other) / stress_other * 100
        if stress_diff_pct > 10:
            insights.append(
                f"😤 HRV 最低 3 天, 平均压力指数 {stress_low:.0f} "
                f"(其他天 {stress_other:.0f}, 高 {stress_diff_pct:.0f}%)"
            )

    if not insights:
        return None

    low_dates = [d.record_date.isoformat() for d in low_days]
    title = f"HRV 最低 3 天 的共同规律"
    body = (
        f"过去 14 天你 HRV 最低的 3 天 ({', '.join(low_dates)}), "
        f"平均 {hrv_low:.0f} ms (其他天 {hrv_other:.0f} ms).\n\n"
        + "\n".join(insights)
        + "\n\n**建议**: 当睡眠/压力在预警线时, 第二天 HRV 通常也会低. "
          "回看这几天前一晚的行为 (咖啡/晚餐/运动时间), 找规律."
    )
    return InsightCandidate(
        kind="hrv_pattern",
        rule_id="hrv_stressor_correlation",
        title=title,
        body=body,
        evidence={
            "low_hrv_dates": low_dates,
            "hrv_avg_low": hrv_low, "hrv_avg_other": hrv_other,
            "sleep_avg_low": sleep_low, "sleep_avg_other": sleep_other,
            "stress_avg_low": stress_low, "stress_avg_other": stress_other,
            "sample_size": len(rows),
            "cite": f"基于近 {len(rows)} 天 Garmin 数据",
        },
        confidence=0.75,
        severity="low",
    )


# ─────────────────────── Fallback: 画像摘要 ───────────────────────


def _gen_profile_summary(db: Session, user_id: int) -> Optional[InsightCandidate]:
    """Fallback: 基于 KG + Memory 当前快照画个用户画像. 永远有输出 (兜底)."""
    from app.models.health_kg import HealthEntity
    from app.models.memory_fact import MemoryFact

    entities = db.query(HealthEntity).filter(
        HealthEntity.user_id == user_id,
        HealthEntity.is_active.is_(True),
    ).all()
    facts = db.query(MemoryFact).filter(
        MemoryFact.user_id == user_id,
        MemoryFact.superseded_at.is_(None),
    ).all()

    gene_count = sum(1 for e in entities if e.type == "gene_variant")
    lab_count = sum(1 for e in entities if e.type == "lab_value")
    med_count = sum(1 for e in entities if e.type == "medication")
    if gene_count + lab_count + med_count + len(facts) < 3:
        return None  # 数据太少, 连 fallback 也不出

    parts = []
    if gene_count:
        parts.append(f"**{gene_count}** 个有临床意义的基因位点")
    if lab_count:
        parts.append(f"**{lab_count}** 项已记录化验")
    if med_count:
        parts.append(f"**{med_count}** 个在服药")
    if facts:
        parts.append(f"**{len(facts)}** 条记忆事实")

    body = (
        "📚 **你的健康画像**\n\n"
        "AI 现在对你的了解:\n"
        f"- {' + '.join(parts)}\n\n"
        "未来这些数据会自动驱动 AI 的判断, 每次对话都会考虑你的个人特征 (基因/用药/化验),"
        "而不是给通用建议."
    )
    return InsightCandidate(
        kind="profile_summary",
        rule_id="fallback_profile",
        title="今日健康画像概览",
        body=body,
        evidence={
            "entity_count": len(entities),
            "fact_count": len(facts),
            "gene_count": gene_count,
            "lab_count": lab_count,
            "med_count": med_count,
            "cite": "基于 Memory KG + Facts 当前快照",
        },
        confidence=0.5,  # fallback 故意低分, 有其他 insight 时优先非 fallback
        severity="info",
    )


# ─────────────────────── Tier 3: LLM Pattern Mining ───────────────────────


def _gen_llm_pattern_mining(db: Session, user_id: int) -> Optional[InsightCandidate]:
    """Tier 3: 让 LLM 分析 30 天数据挖跨事件 pattern.

    触发门槛 (成本控制):
      - 至少 10 条 MemoryFact (不然 LLM 没素材)
      - 至少 7 天 GarminData (不然相关性不显著)

    Grounding:
      - Prompt 要求 LLM 返回 JSON 含 evidence_refs (fact_id / metric_date)
      - 后端验证 evidence_refs 存在性, 无效 ref 直接丢弃候选
      - 如所有 ref 都假 → 返回 None (不写库)

    Cost:
      - 最多 1 次 LLM call / user / day (generate_daily_insight 幂等保证)
      - gpt-4o-mini 或 tokenplan, max_tokens=600
    """
    from app.models.memory_fact import MemoryFact
    from app.models.daily_health import GarminData, DietRecord
    from app.models.anomaly_alert import AnomalyAlert

    facts = db.query(MemoryFact).filter(
        MemoryFact.user_id == user_id,
        MemoryFact.superseded_at.is_(None),
    ).order_by(MemoryFact.confidence.desc()).limit(50).all()
    if len(facts) < 10:
        return None  # 数据不足, 走确定性 fallback

    from datetime import date as _date, timedelta as _td
    from app.services.garmin_daily_merged import merged_daily_rows
    since_gar = _date.today() - _td(days=14)
    # 多源按日合并 → 每天一行,prompt block 不出现重复日期,len 即真实天数
    garmin = merged_daily_rows(db, user_id, since=since_gar)
    if len(garmin) < 7:
        return None

    # 30 天 diet / anomaly 关联
    since_30 = _date.today() - _td(days=30)
    diets = (
        db.query(DietRecord)
        .filter(DietRecord.user_id == user_id, DietRecord.record_date >= since_30)
        .order_by(DietRecord.record_date.desc())
        .limit(60)
        .all()
    )
    anomalies = (
        db.query(AnomalyAlert)
        .filter(AnomalyAlert.user_id == user_id, AnomalyAlert.detection_date >= since_30)
        .limit(20)
        .all()
    )

    # 构造 prompt
    from app.services.memory_service import effective_memory_predicate

    facts_block = "\n".join(
        f"- [fact#{f.id}] {f.subject} {effective_memory_predicate(f.predicate, subject=f.subject, object_value=f.object_value, tags=f.tags or [])} {f.object_value}"
        f"{f' ' + f.object_unit if f.object_unit else ''} (conf={f.confidence:.2f}, tier={f.tier})"
        for f in facts[:30]
    )
    garmin_block = "\n".join(
        f"- {g.record_date.isoformat()}: HRV={g.hrv or '-'} RHR={g.resting_heart_rate or '-'} "
        f"Sleep={g.sleep_score or '-'} Stress={g.stress_level or '-'}"
        for g in garmin[:14]
    )
    diet_block = "\n".join(
        f"- {d.record_date.isoformat()} {d.meal_type or ''}: {(d.food_name or '')[:60]}"
        for d in diets[:20]
    ) if diets else "(无饮食记录)"
    anomaly_block = "\n".join(
        f"- {a.detection_date.isoformat()} {a.alert_type} {a.severity}: {(a.message or '')[:80]}"
        for a in anomalies[:10]
    ) if anomalies else "(无告警)"

    system = (
        "你是健康数据模式分析员. 任务: 从用户近 30 天 Memory Facts + 14 天 Garmin + "
        "30 天 Diet + 30 天 Anomaly 挖**跨事件 pattern** — 比如某类饮食后第二天的 "
        "HRV 下降, 或 HRV 最低的日子有共同的生理/行为特征.\n\n"
        "严格要求:\n"
        "1. 只能引用给你的真实数据, **不能编造** 值或日期\n"
        "2. 返回 JSON, **无其他文字**:\n"
        "   {\n"
        "     \"found_pattern\": true|false,\n"
        "     \"title\": \"一句话 pattern 标题 (≤30 字)\",\n"
        "     \"body\": \"详细说明 + 建议 (2-3 段, 500 字内)\",\n"
        "     \"evidence_refs\": [\n"
        "       {\"type\": \"fact\", \"id\": 数字},\n"
        "       {\"type\": \"garmin_date\", \"date\": \"YYYY-MM-DD\"},\n"
        "       {\"type\": \"diet_date\", \"date\": \"YYYY-MM-DD\"}\n"
        "     ],\n"
        "     \"confidence\": 0.0-1.0\n"
        "   }\n"
        "3. 至少 2 条 evidence_refs, 否则 found_pattern=false\n"
        "4. confidence 反映样本量: 3+ 次重复 conf>0.6, 2 次 conf<0.5, 1 次不算 pattern\n"
        "5. 合规: 不得出具医嘱, body 用\"可以关注\"\"建议记录\"等观察性措辞"
    )
    user_prompt = (
        "## Memory Facts (top 30 by confidence)\n"
        f"{facts_block}\n\n"
        "## Garmin 近 14 天\n"
        f"{garmin_block}\n\n"
        "## Diet 近 30 天\n"
        f"{diet_block}\n\n"
        "## Anomaly 近 30 天\n"
        f"{anomaly_block}\n\n"
        "请找一条跨事件 pattern 返回 JSON."
    )

    try:
        from app.services.llm import get_llm_provider
        from app.services.llm.usage_tracker import set_caller
        from app.utils.async_helpers import run_async
        set_caller("insight.llm_pattern_mining")
        provider = get_llm_provider()
        result_text = run_async(provider.chat(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_prompt}],
            temperature=0.3,
            max_tokens=700,
        ))
        if isinstance(result_text, dict):
            result_text = (result_text.get("content") or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[insight.llm] LLM 调用失败 user={user_id}: {e}")
        return None

    if not result_text:
        return None

    # 解析 JSON
    import json
    import re
    try:
        obj = json.loads(result_text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", result_text)
        if not m:
            logger.warning("[insight.llm] 响应无 JSON response_len=%s", len(result_text))
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"[insight.llm] JSON parse 失败: {e}")
            return None

    if not obj.get("found_pattern"):
        return None

    title = str(obj.get("title", ""))[:200].strip()
    body = str(obj.get("body", "")).strip()
    if not title or not body:
        return None

    # Grounding verification: evidence_refs 是否真实存在
    refs_raw = obj.get("evidence_refs") or []
    if not isinstance(refs_raw, list) or len(refs_raw) < 2:
        logger.info(f"[insight.llm] evidence_refs 太少 user={user_id}, 丢弃")
        return None

    valid_refs = []
    fact_ids = {f.id for f in facts}
    garmin_dates = {g.record_date.isoformat() for g in garmin}
    diet_dates = {d.record_date.isoformat() for d in diets}
    for r in refs_raw:
        if not isinstance(r, dict):
            continue
        rtype = r.get("type")
        if rtype == "fact":
            fid = r.get("id")
            if isinstance(fid, int) and fid in fact_ids:
                valid_refs.append({"type": "fact", "id": fid})
        elif rtype == "garmin_date":
            d = r.get("date")
            if isinstance(d, str) and d in garmin_dates:
                valid_refs.append({"type": "garmin_date", "date": d})
        elif rtype == "diet_date":
            d = r.get("date")
            if isinstance(d, str) and d in diet_dates:
                valid_refs.append({"type": "diet_date", "date": d})
        # 其他 type 忽略

    if len(valid_refs) < 2:
        logger.info(
            f"[insight.llm] grounding 验证失败 user={user_id}: "
            f"原 {len(refs_raw)} refs, 有效 {len(valid_refs)}"
        )
        return None

    try:
        conf = float(obj.get("confidence", 0.6))
    except (TypeError, ValueError):
        conf = 0.6
    conf = max(0.3, min(0.85, conf))  # clamp: LLM 不比 deterministic 高

    return InsightCandidate(
        kind="llm_pattern",
        rule_id="llm_pattern_mining_v1",
        title=title,
        body=body,
        evidence={
            "evidence_refs": valid_refs,
            "refs_valid_count": len(valid_refs),
            "refs_raw_count": len(refs_raw),
            "cite": f"基于 {len(facts)} 条记忆 + {len(garmin)} 天 Garmin + "
                    f"{len(diets)} 条饮食 LLM 分析",
            "llm_model": "default",
        },
        confidence=conf,
        severity="low",  # LLM 产出 → low, 让高 severity 的确定性 rule 优先
    )


# ─────────────────────── 主入口 ───────────────────────


_GENERATORS: List[Callable[[Session, int], Optional[InsightCandidate]]] = [
    _gen_pgx_medication_caution,
    _gen_abnormal_lab_trend,
    _gen_hrv_stressor_pattern,
    _gen_llm_pattern_mining,  # Tier 3: 放在 fallback 前, 评分靠 severity*confidence 自动竞争
    _gen_profile_summary,  # fallback 最后
]


def generate_daily_insight(db: Session, user_id: int, target_date: Optional[date] = None) -> Optional[int]:
    """生成 user 的当日 insight. 返回写入的 DailyInsight id, 失败或已存在返回 None.

    幂等: 同 (user, date) 已存在则返回已存在的 id.
    """
    from app.models.daily_insight import DailyInsight

    if target_date is None:
        target_date = date.today()

    # 幂等检查
    existing = db.query(DailyInsight).filter(
        DailyInsight.user_id == user_id,
        DailyInsight.insight_date == target_date,
    ).first()
    if existing:
        return existing.id

    # 跑所有 generators, 收集 candidate
    candidates: List[InsightCandidate] = []
    for gen in _GENERATORS:
        try:
            c = gen(db, user_id)
            if c:
                candidates.append(c)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[insight] generator {gen.__name__} 失败 (跳过): {e}")

    if not candidates:
        logger.info(f"[insight] user={user_id} 无可用 insight 生成")
        return None

    # 按 score 降序, 选第一个
    candidates.sort(key=lambda c: -c.score())
    chosen = candidates[0]

    row = DailyInsight(
        user_id=user_id,
        insight_date=target_date,
        kind=chosen.kind,
        rule_id=chosen.rule_id,
        title=chosen.title,
        body=chosen.body,
        evidence=chosen.evidence,
        confidence=chosen.confidence,
        severity=chosen.severity,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            f"[insight] user={user_id} 写入 #{row.id} "
            f"kind={chosen.kind} rule={chosen.rule_id} score={chosen.score():.2f}"
        )
        return row.id
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[insight] 写入失败 (跳过) user={user_id}: {e}")
        return None
