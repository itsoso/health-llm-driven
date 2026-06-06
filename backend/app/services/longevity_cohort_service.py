# -*- coding: utf-8 -*-
"""抗衰群体证据聚合(N-of-1 → N-of-many,Phase3 P3-3)。

把所有用户已评分的生物年龄 N-of-1 卡聚合成**去标识**群体证据:
「哪个生物年龄指标、改善率多少、平均年轻几岁」。
- 既是产品决策依据(什么干预对什么人有效),也是退出叙事的数据资产。
- **强制去标识**:输出只含计数/均值,绝不含 user_id;样本量 < MIN_COHORT 的格子
  整体抑制(不出具体数),避免小样本再识别。

注:ActionCard 不携带干净的「干预类型」字段,故按 metric_key 聚合,不强分干预域
(诚实——不编造没有的维度)。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.tasks.metrics import HIGHER_IS_BETTER  # 方向单一真值源(越高/越低好)

# 生物年龄类指标(bioage 版对外保留"年轻几岁"口径)
BIOAGE_METRICS = ("phenotypic_age", "biological_age", "vo2max", "fitness_age")
# 去标识阈值:某 metric 已评分样本 < 此值 → 抑制具体数字
MIN_COHORT = 5

_CLAIM_BOUNDARY = (
    "群体观察性聚合,非随机对照试验;反映已执行 N-of-1 的真实分布,"
    "不构成疗效证明,不替代医学结论。"
)


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        s = str(v).strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _similar_user_ids(db: Session, user_id: int) -> Optional[set]:
    """飞轮 v2:与目标用户"相似"的 user_id 集(同年龄段 decade + 同性别)。

    目标缺 birth_date/gender → None(无法分层,调用方回退人群平均)。
    年龄段 = 出生年所在十年(如 1980s),用 birth_date 区间匹配,避免 SQL 日期算。
    """
    from datetime import date

    from app.models.user import User

    target = db.query(User).filter(User.id == user_id).first()
    if not target or not target.birth_date or not target.gender:
        return None
    by = target.birth_date.year
    decade_lo = (by // 10) * 10          # 1980
    lo, hi = date(decade_lo, 1, 1), date(decade_lo + 9, 12, 31)
    rows = (
        db.query(User.id)
        .filter(
            User.gender == target.gender,
            User.birth_date >= lo,
            User.birth_date <= hi,
        )
        .all()
    )
    return {uid for (uid,) in rows}


def _aggregate(db: Session, metric_keys: Optional[set],
               user_ids: Optional[set] = None) -> dict[str, Any]:
    """通用核心:跨用户聚合已评分 ActionCard。metric_keys=None → 全部指标。
    user_ids 非 None → 仅这些用户(飞轮 v2 匹配队列)。

    mean_improvement = improved 卡朝目标方向的绝对改善均值(方向用 HIGHER_IS_BETTER;
    单位是该指标自身单位)。小样本 < MIN_COHORT → suppressed。去标识(无 user_id)。
    """
    q = db.query(ActionCard).filter(ActionCard.outcome.isnot(None))
    if metric_keys is not None:
        q = q.filter(ActionCard.metric_key.in_(tuple(metric_keys)))
    if user_ids is not None:
        if not user_ids:
            return {}
        q = q.filter(ActionCard.user_id.in_(tuple(user_ids)))
    rows = q.all()

    by_metric: dict[str, dict[str, Any]] = {}
    for r in rows:
        m = (r.metric_key or "").lower()
        if not m or (metric_keys is not None and m not in metric_keys):
            continue
        b = by_metric.setdefault(m, {"n": 0, "improved": 0, "worsened": 0,
                                     "unchanged": 0, "_impr": []})
        b["n"] += 1
        oc = (r.outcome or "").lower()
        if oc in ("improved", "worsened", "unchanged"):
            b[oc] += 1
        if oc == "improved":
            base, act = _num(r.baseline_value), _num(r.actual_value)
            if base is not None and act is not None:
                higher = HIGHER_IS_BETTER.get(m, False)
                imp = (act - base) if higher else (base - act)  # 朝目标方向的绝对改善
                if imp > 0:
                    b["_impr"].append(round(imp, 1))

    out: dict[str, Any] = {}
    for m, b in by_metric.items():
        n = b["n"]
        if n < MIN_COHORT:
            out[m] = {"n": n, "suppressed": True, "note": f"样本 < {MIN_COHORT},去标识抑制"}
            continue
        impr = b.pop("_impr")
        out[m] = {
            "n": n, "improved": b["improved"], "worsened": b["worsened"],
            "unchanged": b["unchanged"],
            "improvement_rate": round(b["improved"] / n, 3) if n else None,
            "mean_improvement": round(sum(impr) / len(impr), 1) if impr else None,
        }
    return out


def _wrap(metrics_out: dict[str, Any]) -> dict[str, Any]:
    return {
        "metrics": metrics_out,
        "min_cohort": MIN_COHORT,
        "evidence_tier": "observational",  # 群体观察,非 RCT;不夸大成疗效
        "claim_boundary": _CLAIM_BOUNDARY,
    }


def cohort_biological_age_outcomes(
    db: Session, similar_to_user_id: Optional[int] = None,
) -> dict[str, Any]:
    """生物年龄群体证据(去标识)。mean_improvement 即"年轻几岁",保留旧键名。
    similar_to_user_id 非 None → 匹配队列(同龄段·同性别)。"""
    user_ids = _similar_user_ids(db, similar_to_user_id) if similar_to_user_id else None
    out = _aggregate(db, set(BIOAGE_METRICS), user_ids)
    for v in out.values():
        if "mean_improvement" in v:
            v["mean_improvement_years"] = v.pop("mean_improvement")
    return _wrap(out)


def cohort_metric_outcomes(
    db: Session, metrics: Optional[list[str]] = None,
    similar_to_user_id: Optional[int] = None,
) -> dict[str, Any]:
    """群体证据泛化:任一 outcome 指标的去标识聚合。metrics=None → 全部已评分指标。
    similar_to_user_id 非 None → 匹配队列。mean_improvement 为指标自身单位(非"岁")。
    """
    keys = {k.lower() for k in metrics} if metrics else None
    user_ids = _similar_user_ids(db, similar_to_user_id) if similar_to_user_id else None
    return _wrap(_aggregate(db, keys, user_ids))


def _snippet_from_metric(m: dict[str, Any], matched: bool) -> Optional[dict[str, Any]]:
    n = m.get("n") or 0
    rate = m.get("improvement_rate")
    years = m.get("mean_improvement_years")
    if not n or rate is None:
        return None
    who = "和你相似的" if matched else "已完成同类 12 周计划的"
    tail = "(同龄段·同性别,观察性,非因果)" if matched else "(观察性,非因果)"
    parts = [f"{who} {n} 位用户中,{round(rate * 100)}% 生物年龄改善"]
    if years:
        parts.append(f"平均年轻 {years} 岁")
    return {
        "n": n, "improvement_rate": rate, "mean_improvement_years": years,
        "matched": matched,
        "text": "群体证据:" + "、".join(parts) + tail,
        "evidence_tier": "observational",
    }


def cohort_recommendation_snippet(
    db: Session, metric: str = "phenotypic_age",
    similar_to_user_id: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """数据飞轮:群体已验证结果做成可挂在 N-of-1 推荐上的证据。

    飞轮 v2:有 similar_to_user_id 时优先"和你相似的人"(匹配队列);匹配队列样本
    不足则回退到人群平均(仍给证据,只是不带"相似"声明)。都不足 → None(不编造)。
    """
    key = (metric or "").lower()
    if similar_to_user_id:
        matched = (cohort_biological_age_outcomes(db, similar_to_user_id)
                   .get("metrics", {}).get(key))
        if matched and not matched.get("suppressed"):
            snip = _snippet_from_metric(matched, matched=True)
            if snip:
                return snip
    pop = cohort_biological_age_outcomes(db).get("metrics", {}).get(key)
    if not pop or pop.get("suppressed"):
        return None
    return _snippet_from_metric(pop, matched=False)
