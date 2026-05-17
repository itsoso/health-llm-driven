"""
Weekly Advisor —— 周日生成 3-5 条本周可执行建议, 写 action_cards (Phase 2 P2-1).

设计:
- 周日 21:07 跑 (memory: 部署默认双跑 + 7-day rule)
- 输入: Twin + Safety alerts + Specialist findings + Longitudinal 趋势
- 输出: 3-5 条 Suggestion → action_cards (source_type='weekly_advisor', card_type='recommendation')
- LLM 不可用 / 输出 < 3 条 → 退化用 Specialist findings top 3 兜底
- 幂等: 本周已有 weekly_advisor 卡 (created_at >= 本周一) → 跳过, 不重复

输出 schema:
[
  {
    "title": "周三减量训练",
    "content": "为什么 + 怎么做 + 验证指标",
    "metric_key": "rhr",
    "baseline_value": "62",
    "target_value": "58",
    "verification_days": 7
  },
  ...
]
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents.safety_guardian import evaluate_safety
from app.models.action_card import ActionCard
from app.orchestrator.intent import classify_intent
from app.orchestrator.orchestrator import (
    _apply_planner_evidence_policy,
    _attach_kb_evidence_to_findings,
    _run_specialists,
    _select_specialists,
)
from app.twin import build_twin
from app.twin.formatter import twin_to_prompt_blob

logger = logging.getLogger(__name__)


# ── 配置常量 ──
MIN_SUGGESTIONS = 3
MAX_SUGGESTIONS = 5
DEFAULT_VERIFICATION_DAYS = 7


def _week_start(now: datetime) -> datetime:
    """本周一 00:00 (UTC)."""
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start


def _has_weekly_card_this_week(db: Session, user_id: int, now: datetime) -> bool:
    """本周一以来已经写过 weekly_advisor 卡 → 不再产新建议."""
    week_start = _week_start(now)
    return (
        db.query(ActionCard.id)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.source_type == "weekly_advisor",
            ActionCard.created_at >= week_start,
        )
        .first()
        is not None
    )


def _build_advisor_prompt(
    twin_blob: str,
    safety_summary: str,
    findings_summary: str,
    primary_goal: Optional[str] = None,
    gene_highlights: Optional[str] = None,
) -> str:
    """构造 LLM 提示, 让它产出 3-5 条结构化建议 JSON."""
    goal_block = ""
    if primary_goal:
        goal_label = {
            "weight_loss": "减肥/控重",
            "glucose": "降血糖",
            "blood_pressure": "降血压",
            "sleep": "改善睡眠",
            "hrv": "提升 HRV / 恢复",
            "rhinitis": "管理鼻炎",
            "general": "总体健康",
        }.get(primary_goal, primary_goal)
        goal_block = f"\n## 用户主目标 (优先针对它给建议)\n{goal_label}\n"

    gene_block = ""
    if gene_highlights:
        gene_block = f"\n## 用户基因关键变体 (这周建议要跟它产生关联)\n{gene_highlights}\n"

    return f"""你是一位资深健康教练. 基于下面的用户健康数据快照, 产出 {MIN_SUGGESTIONS}-{MAX_SUGGESTIONS} 条本周可执行的建议.

每条建议必须满足:
1. 行动具体到"做什么 + 何时 + 多久"
2. 必须有可量化的验证指标 (HRV / RHR / 体重 / BP / SpO2 / 睡眠分 / 化验项 等)
3. 一周可观察出变化 ({DEFAULT_VERIFICATION_DAYS} 天)
4. 不超出用户当前状态 (例如 readiness < 50 不要让他冲刺训练)
5. **如有用户主目标, 至少 2 条建议要直接服务该目标** (用户最想改善什么 = 优先级最高)
6. **如有基因关键变体, 至少 1 条建议要显式关联** (例: "你的 MTHFR C677T → 这周补 5-MTHF 800μg")

返回严格 JSON 数组, 字段:
- title (≤ 20 字, 一句话标题)
- content (1-2 段, 解释为什么 + 怎么做 + 验证标准)
- metric_key — **必须**从下列白名单选, 选不到就填 "custom"; 不要瞎猜:
    sleep_score | hrv | rhr | weight | bp | systolic_bp | diastolic_bp |
    spo2 | spo2_odi | bmi | body_fat |
    ldl | hdl | tc | tg | hba1c | fasting_glucose | blood_glucose |
    alt | ast | ggt | alp | creatinine | uric_acid | urea |
    tsh | ft3 | ft4 | vitamin_d | vd | b12 | ferritin | hcy | homocysteine |
    crp | esr | wbc | rbc | hgb | plt | lp_a | apo_b |
    hydration_ml | calories_intake | supplement_adherence_pct |
    custom (没匹配的 metric 一律填这个, 不要硬塞)
- evidence_level — **必填**, 从下面四级选:
    high           — 强证据: CPIC pharmacogenomics 标准 / Garmin 实测异常 / MTHFR 叶酸代谢这类 >100 RCT 共识
    medium         — 中等证据: 单项 RCT / 小样本 / 关联性
    low            — 弱证据: 理论假设 / 单一研究 / 跨族群外推
    medical_grade  — **必须医生介入**: 用药调整 / 遗传病 / 急性血压/血糖/肝肾异常
  默认 medium. 涉及降压/降糖/抗凝/抗精神病药调整 → 必须 medical_grade
- evidence_refs — 可选数组. 如果建议来自 Specialist Findings 中的 `refs=claim:...`,
  必须原样带上这些 claim_id；不要编造新的 claim_id。
- baseline_value (当前数值, **纯数字字符串**, 例 "62" 不是 "62 bpm" 不是 "60ms, ACWR 2.38")
- target_value (目标数值, **纯数字字符串**, 例 "70" 不是 ">70ms")
- verification_days (整数, 默认 7)

## 用户健康快照 (Twin)
{twin_blob}
{goal_block}{gene_block}
## 本周 Safety Guardian 告警
{safety_summary or '(无)'}

## 本周 Specialist Findings
{findings_summary or '(无)'}

只返回 JSON 数组本身, 不要 markdown 包裹, 不要解释文字."""


def _parse_llm_suggestions(text: str) -> List[Dict[str, Any]]:
    """从 LLM 输出抽 JSON 数组. 容错: 找 [ 开始, ] 结束."""
    import re

    if not text:
        return []
    # 去掉 ```json ``` 等 markdown 包裹
    text = text.strip()
    if text.startswith("```"):
        # 找到第一个换行后的内容
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "suggestions" in data:
            return data["suggestions"]
    except Exception:
        # 找数组括号
        try:
            start = text.index("[")
            end = text.rindex("]") + 1
            data = json.loads(text[start:end])
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


_METRIC_KEY_WHITELIST = {
    "sleep_score", "hrv", "rhr", "weight", "bp", "systolic_bp", "diastolic_bp",
    "spo2", "spo2_odi", "bmi", "body_fat",
    "ldl", "hdl", "tc", "tg", "hba1c", "fasting_glucose", "blood_glucose",
    "alt", "ast", "ggt", "alp", "creatinine", "uric_acid", "urea",
    "tsh", "ft3", "ft4", "vitamin_d", "vd", "b12", "ferritin",
    "hcy", "homocysteine",
    "crp", "esr", "wbc", "rbc", "hgb", "plt", "lp_a", "apo_b",
    # 2026-05-12 P1.2
    "hydration_ml", "calories_intake", "supplement_adherence_pct",
    "custom",
}


def _normalize_metric_key(raw: Any) -> str:
    """LLM 返回的 metric_key 不在白名单 → 强制 'custom', 不让脏数据进库
    (outcome_grader 没有 custom 的 fetcher → 自动 skip, 不会错误 grade)."""
    if not raw or not isinstance(raw, str):
        return "custom"
    k = raw.strip().lower()
    return k if k in _METRIC_KEY_WHITELIST else "custom"


_EVIDENCE_LEVELS = {"high", "medium", "low", "medical_grade"}


def _normalize_evidence_level(raw: Any) -> str:
    """LLM 返回的 evidence_level 不在 4 级之内 → 默认 medium."""
    if not raw or not isinstance(raw, str):
        return "medium"
    k = raw.strip().lower()
    return k if k in _EVIDENCE_LEVELS else "medium"


def _validate_suggestion(s: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """校验单条建议. 必填: title/content. 其余有默认值."""
    title = s.get("title")
    content = s.get("content")
    if not title or not content:
        return None
    return {
        "title": str(title).strip()[:200],
        "content": str(content).strip(),
        "metric_key": _normalize_metric_key(s.get("metric_key")),
        "evidence_level": _normalize_evidence_level(s.get("evidence_level")),
        "evidence_refs": _normalize_evidence_refs(s.get("evidence_refs")),
        "baseline_value": (
            str(s["baseline_value"]) if s.get("baseline_value") is not None else None
        ),
        "target_value": (
            str(s["target_value"]) if s.get("target_value") is not None else None
        ),
        "verification_days": s.get("verification_days") or DEFAULT_VERIFICATION_DAYS,
    }


def _normalize_evidence_refs(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen = set()
    for ref in raw:
        value = str(ref).strip()
        if not value.startswith("claim:") or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _findings_to_fallback_suggestions(findings: List[Any]) -> List[Dict[str, Any]]:
    """退化策略: LLM 失败/输出不足时, 拉 Specialist findings top 3 转成建议形态."""
    out: List[Dict[str, Any]] = []
    for f in findings[:MIN_SUGGESTIONS]:
        # SpecialistFinding 是 pydantic, 容错 attr/dict 两种
        title = getattr(f, "summary", None) or (f.get("summary") if isinstance(f, dict) else None)
        body = getattr(f, "details", None) or (f.get("details") if isinstance(f, dict) else None)
        sp = getattr(f, "specialist_name", None) or (
            f.get("specialist_name") if isinstance(f, dict) else None
        )
        refs = getattr(f, "evidence_refs", None) or (
            f.get("evidence_refs") if isinstance(f, dict) else None
        )
        if not title:
            continue
        out.append(
            {
                "title": str(title)[:80],
                "content": str(body or title)[:1000],
                "metric_key": None,
                "baseline_value": None,
                "target_value": None,
                "verification_days": DEFAULT_VERIFICATION_DAYS,
                "_creator_specialist": sp,
                "evidence_refs": _normalize_evidence_refs(refs),
            }
        )
    return out


def _apply_weekly_advisor_evidence_policy(
    db: Session,
    twin: Any,
    findings: List[Any],
) -> tuple[List[Any], Dict[str, Any]]:
    """Reuse Orchestrator's evidence gate before weekly advice consumes findings."""

    if not findings:
        return findings, {"input_count": 0, "kept_count": 0, "blocked_count": 0, "blocked": []}
    try:
        _attach_kb_evidence_to_findings(db, twin, findings)
    except Exception as e:  # noqa: BLE001
        logger.debug("[WeeklyAdvisor] system KB evidence attach skipped: %s", e)
    try:
        filtered, trace = _apply_planner_evidence_policy(findings)
        return filtered, trace
    except Exception as e:  # noqa: BLE001
        logger.warning("[WeeklyAdvisor] evidence policy skipped: %s", e)
        return findings, {
            "input_count": len(findings),
            "kept_count": len(findings),
            "blocked_count": 0,
            "blocked": [],
            "error": str(e)[:200],
        }


def _persist_suggestions(
    db: Session,
    user_id: int,
    suggestions: List[Dict[str, Any]],
    fallback_used: bool,
) -> List[int]:
    """把建议写成 action_cards. 返回 card_id 列表."""
    ids: List[int] = []
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=14)  # 两周后过期

    for s in suggestions[:MAX_SUGGESTIONS]:
        card = ActionCard(
            user_id=user_id,
            title=s["title"],
            content=s["content"],
            card_type="recommendation",
            source_type="weekly_advisor",
            source_id=now.strftime("%Y-W%V"),  # ISO 周编号
            severity="low",  # 普通建议低优先级, 不打扰
            status="active",
            priority=5,
            expires_at=expires_at,
            metric_key=s.get("metric_key"),
            baseline_value=s.get("baseline_value"),
            target_value=s.get("target_value"),
            verification_days=s.get("verification_days") or DEFAULT_VERIFICATION_DAYS,
            evidence_level=s.get("evidence_level") or "medium",
            evidence_refs=s.get("evidence_refs") or [],
            creator_specialist=s.get("_creator_specialist") or "weekly_advisor",
            check_back_date=now + timedelta(days=s.get("verification_days") or DEFAULT_VERIFICATION_DAYS),
        )
        db.add(card)
        db.flush()
        ids.append(card.id)
    db.commit()
    if ids:
        logger.info(
            f"[WeeklyAdvisor] user={user_id} 写入 {len(ids)} 条建议 "
            f"({'fallback' if fallback_used else 'llm'}): card_ids={ids}"
        )
    return ids


async def generate_weekly_advice(db: Session, user_id: int) -> Dict[str, Any]:
    """主入口: 给单个用户产 3-5 条建议, 写 action_cards.

    返回: {"created": N, "fallback": bool, "skipped": str?}
    """
    now = datetime.now(timezone.utc)

    if _has_weekly_card_this_week(db, user_id, now):
        return {"created": 0, "skipped": "already_has_weekly_card"}

    try:
        twin = build_twin(db, user_id)
    except Exception as e:
        logger.warning(f"[WeeklyAdvisor] user={user_id} twin build 失败: {e}")
        return {"created": 0, "skipped": "twin_build_failed"}

    # Safety summary
    try:
        safety_report = evaluate_safety(twin)
        safety_summary = "\n".join(
            f"- [{a.severity.label if hasattr(a.severity, 'label') else a.severity}] {a.title}: {a.message[:120]}"
            for a in safety_report.alerts[:8]
        )
    except Exception as e:
        logger.warning(f"[WeeklyAdvisor] user={user_id} safety 失败: {e}")
        safety_summary = ""

    # Specialist findings (跑全部相关 specialist 一遍)
    findings: List[Any] = []
    evidence_policy_trace: Dict[str, Any] = {
        "input_count": 0,
        "kept_count": 0,
        "blocked_count": 0,
        "blocked": [],
    }
    try:
        intent = classify_intent("本周健康总结建议")
        specialists = _select_specialists(intent, twin, None)
        findings = _run_specialists(twin, specialists, {"query": "weekly_advisor", "db": db})
        findings, evidence_policy_trace = _apply_weekly_advisor_evidence_policy(db, twin, findings)
    except Exception as e:
        logger.warning(f"[WeeklyAdvisor] user={user_id} specialists 失败: {e}")

    findings_lines = []
    for f in findings[:8]:
        refs = _normalize_evidence_refs(getattr(f, "evidence_refs", None))
        ref_part = f" refs={','.join(refs[:3])}" if refs else " refs=none"
        findings_lines.append(
            f"- [{getattr(f, 'specialist_name', '?')}] {getattr(f, 'summary', '')}{ref_part}"[:260]
        )
    findings_summary = "\n".join(findings_lines)

    # 2026-05-14: 拉 primary_goal + gene highlights, 让 LLM 围绕用户最关心的目标和基因给建议
    primary_goal: Optional[str] = None
    try:
        from app.models.user_profile import UserProfile
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        primary_goal = getattr(profile, "primary_goal", None) if profile else None
    except Exception:
        pass

    gene_highlights: Optional[str] = None
    try:
        from app.models.genetic_data import GeneticVariant
        # 取 high/medium 风险 + 优势变体, 最多 5 条
        v_rows = (
            db.query(GeneticVariant)
            .filter(
                GeneticVariant.user_id == user_id,
                GeneticVariant.risk_level.in_(["high", "medium"]),
            )
            .order_by(GeneticVariant.risk_level.desc())
            .limit(5)
            .all()
        )
        if v_rows:
            gene_highlights = "\n".join(
                f"- {v.gene_name} {v.variant_name or ''} 基因型 {v.genotype or '?'}"
                f" → {v.result_label or v.risk_level} ({v.category})"
                for v in v_rows
            )
    except Exception:
        pass

    # 让 LLM 产建议
    suggestions: List[Dict[str, Any]] = []
    fallback_used = False
    try:
        twin_blob = twin_to_prompt_blob(twin)
        prompt = _build_advisor_prompt(
            twin_blob, safety_summary, findings_summary,
            primary_goal=primary_goal,
            gene_highlights=gene_highlights,
        )
        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        result = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2000,
        )
        text = result if isinstance(result, str) else (result or {}).get("content", "")
        raw = _parse_llm_suggestions(text)
        for s in raw:
            v = _validate_suggestion(s)
            if v:
                suggestions.append(v)
    except Exception as e:
        logger.warning(f"[WeeklyAdvisor] user={user_id} LLM 失败: {e}")

    # 退化: LLM 输出不足 → 用 Specialist findings 兜底
    if len(suggestions) < MIN_SUGGESTIONS:
        fallback = _findings_to_fallback_suggestions(findings)
        # 合并去重 (按 title)
        seen = {s["title"] for s in suggestions}
        for s in fallback:
            if s["title"] not in seen:
                suggestions.append(s)
                seen.add(s["title"])
                if len(suggestions) >= MIN_SUGGESTIONS:
                    break
        if not suggestions:
            return {"created": 0, "skipped": "no_suggestions_no_fallback"}
        fallback_used = True

    # 写库
    ids = _persist_suggestions(db, user_id, suggestions, fallback_used)
    return {
        "created": len(ids),
        "fallback": fallback_used,
        "card_ids": ids,
        "evidence_policy": evidence_policy_trace,
    }
