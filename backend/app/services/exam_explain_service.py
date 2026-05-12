"""exam_explain_service —— 体检异常解释包 (2026-05-12 review #2).

把单次 MedicalExam 聚合成"为什么异常 + 你能做什么 + 何时复查 + 找什么医生"
的整合包. LLM 一次调用合成 explanation, 配合基因 hits + 历史趋势.

设计:
- abnormal_items: filter is_abnormal != 'normal'
- gene_links: 用 KNOWN_SNPS 把异常项跟用户基因关联 (e.g. 高 LDL → APOE/PCSK9)
- trends: 近 12 月同 item_name 趋势 (≤6 点)
- llm_explanation: prompt 用上面三块, 一段中文 markdown
- related_cards: source_type='medical_exam_analysis' AND source_id 含 exam_id 的卡
- recommended_actions: 从 LLM 输出抽 diet/supp/follow_up, 每条带 evidence_level
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.medical_exam import MedicalExam, MedicalExamItem

logger = logging.getLogger(__name__)


# 化验项 → 基因关联 (KNOWN_SNPS 命中时高亮)
ITEM_GENE_LINKS: Dict[str, List[str]] = {
    "ldl": ["APOE", "PCSK9", "LDLR"],
    "胆固醇": ["APOE", "PCSK9"],
    "甘油三酯": ["APOE", "FADS1"],
    "homocysteine": ["MTHFR", "MTRR"],
    "同型半胱氨酸": ["MTHFR", "MTRR"],
    "尿酸": ["SLC2A9", "ABCG2"],
    "uric": ["SLC2A9", "ABCG2"],
    "vitamin d": ["VDR", "GC", "CYP2R1"],
    "维生素d": ["VDR", "GC"],
    "ferritin": ["HFE"],
    "铁蛋白": ["HFE"],
    "alt": ["PNPLA3"],
    "ast": ["PNPLA3"],
    "肝": ["PNPLA3"],
    "tsh": ["DIO2"],
    "甲状腺": ["DIO2"],
    "fasting glucose": ["TCF7L2"],
    "空腹血糖": ["TCF7L2"],
    "hba1c": ["TCF7L2"],
    "糖化血红蛋白": ["TCF7L2"],
}


def _gene_links_for_item(item_name: str, user_gene_hits: List[str]) -> List[str]:
    """返回该 item 命中的用户实测基因 (intersection of ITEM_GENE_LINKS + user_hits)."""
    if not item_name:
        return []
    name_l = item_name.lower()
    candidates: List[str] = []
    for key, genes in ITEM_GENE_LINKS.items():
        if key.lower() in name_l:
            candidates.extend(genes)
    return [g for g in dict.fromkeys(candidates) if g in user_gene_hits]


def _user_gene_hits(db: Session, user_id: int) -> List[str]:
    """KNOWN_SNPS 字典里用户实测命中的 gene names."""
    try:
        from app.api.genetic_data import KNOWN_SNPS
        from app.models.genetic_data import GeneticProfile, GeneticVariant
    except ImportError:
        return []

    profile = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == user_id)
        .order_by(desc(GeneticProfile.id))
        .first()
    )
    if not profile:
        return []
    variants = db.query(GeneticVariant).filter(
        GeneticVariant.profile_id == profile.id,
    ).all()
    user_genes = {v.gene_name for v in variants if v.gene_name}
    known_genes = {s["gene"] for s in KNOWN_SNPS.values()}
    return sorted(user_genes & known_genes)


def _fetch_trends(
    db: Session, user_id: int, item_names: List[str], end_date: date,
    months: int = 12,
) -> Dict[str, List[Dict[str, Any]]]:
    """近 N 月同 item_name 在所有 exams 里的取值, 按日期 asc 排."""
    if not item_names:
        return {}
    start = end_date - timedelta(days=months * 30)
    rows = (
        db.query(MedicalExamItem, MedicalExam)
        .join(MedicalExam, MedicalExam.id == MedicalExamItem.exam_id)
        .filter(
            MedicalExam.user_id == user_id,
            MedicalExam.exam_date >= start,
            MedicalExam.exam_date <= end_date,
            MedicalExamItem.item_name.in_(item_names),
        )
        .order_by(MedicalExam.exam_date.asc())
        .all()
    )
    out: Dict[str, List[Dict[str, Any]]] = {}
    for item, exam in rows:
        out.setdefault(item.item_name, []).append({
            "date": str(exam.exam_date),
            "value": item.value,
            "value_text": item.value_text,
            "is_abnormal": item.is_abnormal,
        })
    return out


def _related_cards(db: Session, user_id: int, exam_id: int) -> List[Dict[str, Any]]:
    """source_id 含 exam_id 的 medical_exam_analysis 卡."""
    cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.source_type == "medical_exam_analysis",
        )
        .order_by(desc(ActionCard.created_at))
        .limit(20)
        .all()
    )
    matched = []
    sid = str(exam_id)
    for c in cards:
        if c.source_id and (sid in c.source_id or c.source_id.endswith(f"-{sid}")):
            matched.append({
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "outcome": c.outcome,
                "evidence_level": c.evidence_level,
            })
    if not matched:
        # fallback: 时间最接近 exam 的 cards (无 source_id 关联)
        for c in cards[:5]:
            matched.append({
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "outcome": c.outcome,
                "evidence_level": c.evidence_level,
            })
    return matched


def _build_explain_prompt(
    exam_meta: Dict[str, Any],
    abnormal_items: List[Dict[str, Any]],
    user_gene_hits: List[str],
    user_chronic: List[str],
) -> str:
    items_str = "\n".join([
        f"- {it['item_name']}: {it.get('value') or it.get('value_text')}"
        f" {it.get('unit') or ''} (参考 {it.get('reference_range') or '-'})"
        f" — {it['is_abnormal']}"
        + (f" [基因关联 {','.join(it['gene_links'])}]" if it.get("gene_links") else "")
        for it in abnormal_items[:15]
    ])
    return f"""你是临床健康解读 Agent. 用户体检 {exam_meta['exam_date']} {exam_meta.get('exam_type') or '综合'} 检查里有以下异常:

{items_str}

用户基因实测命中 (KNOWN_SNPS): {', '.join(user_gene_hits) or '无'}
用户慢病: {', '.join(user_chronic) or '无'}

输出严格 JSON, 不要 markdown 包裹, 字段:
{{
  "summary": "1 段总结 (≤200 字), 说明哪几项最该关注 + 优先级排序",
  "actions": [
    {{
      "category": "diet" | "supplement" | "follow_up" | "lifestyle" | "see_doctor",
      "title": "≤25 字行动 (例: 复查同型半胱氨酸 / 减少酒精摄入)",
      "rationale": "≤80 字解释为什么 (引用 item + gene 关联)",
      "evidence_level": "high | medium | low | medical_grade",
      "metric_key": "(可选, 跟踪的化验项, 如 hcy / ldl)",
      "suggested_days": 30
    }}
  ],
  "recheck_window_days": 30,
  "see_doctor_specialty": "(可选, 例: 心内科 / 内分泌 / 肝胆外科; 不需要医生时填 null)"
}}

要求:
1. 对涉及用药调整 / 严重异常 → evidence_level = "medical_grade", category = "see_doctor"
2. 优先用户已有基因关联的 item (相同 root cause 一并解释)
3. 没明确证据的不要硬编 (low/medium 也行, 不要瞎说 high)
"""


def build_exam_explain(db: Session, user_id: int, exam_id: int) -> Optional[Dict[str, Any]]:
    """主入口. None = exam 不存在或无权限."""
    exam = (
        db.query(MedicalExam)
        .filter(MedicalExam.id == exam_id, MedicalExam.user_id == user_id)
        .first()
    )
    if not exam:
        return None

    items = (
        db.query(MedicalExamItem)
        .filter(MedicalExamItem.exam_id == exam_id)
        .all()
    )
    abnormal_raw = [
        it for it in items
        if it.is_abnormal and str(it.is_abnormal).lower() not in ("normal", "n", "false", "0")
    ]

    gene_hits = _user_gene_hits(db, user_id)

    abnormal_items = []
    for it in abnormal_raw:
        gl = _gene_links_for_item(it.item_name or "", gene_hits)
        abnormal_items.append({
            "item_name": it.item_name,
            "value": it.value,
            "value_text": it.value_text,
            "unit": it.unit,
            "reference_range": it.reference_range,
            "is_abnormal": it.is_abnormal,
            "gene_links": gl,
        })
    # 优先 gene-linked 排前
    abnormal_items.sort(key=lambda x: (-len(x["gene_links"]), x["item_name"] or ""))

    trends = _fetch_trends(
        db, user_id,
        item_names=[it["item_name"] for it in abnormal_items if it["item_name"]],
        end_date=exam.exam_date,
    )

    related_cards = _related_cards(db, user_id, exam_id)

    # 慢病 from user_profile
    user_chronic: List[str] = []
    try:
        from app.models.user_profile import UserProfile
        prof = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if prof and prof.chronic_conditions:
            user_chronic = list(prof.chronic_conditions)
    except Exception:
        pass

    # LLM (复用 weekly_advisor 的 normalize)
    explanation: Optional[Dict[str, Any]] = None
    try:
        from app.services.llm import get_llm_provider
        from app.services.weekly_advisor import _normalize_metric_key, _normalize_evidence_level
        provider = get_llm_provider()
        prompt = _build_explain_prompt(
            {"exam_date": str(exam.exam_date), "exam_type": exam.exam_type},
            abnormal_items, gene_hits, user_chronic,
        )
        import asyncio, json as _json

        async def _call():
            r = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1200,
            )
            return r if isinstance(r, str) else (r or {}).get("content", "")

        try:
            raw = asyncio.run(_call())
        except RuntimeError:
            import nest_asyncio
            nest_asyncio.apply()
            raw = asyncio.get_event_loop().run_until_complete(_call())

        if raw:
            t = raw.strip()
            if t.startswith("```"):
                t = t.strip("`").lstrip("json").strip()
            parsed = _json.loads(t)
            # 校验/规范 actions
            actions = []
            for a in (parsed.get("actions") or [])[:8]:
                actions.append({
                    "category": a.get("category") or "lifestyle",
                    "title": str(a.get("title", ""))[:60],
                    "rationale": str(a.get("rationale", ""))[:200],
                    "evidence_level": _normalize_evidence_level(a.get("evidence_level")),
                    "metric_key": _normalize_metric_key(a.get("metric_key")) if a.get("metric_key") else None,
                    "suggested_days": int(a.get("suggested_days") or 30),
                })
            explanation = {
                "summary": str(parsed.get("summary", ""))[:600],
                "actions": actions,
                "recheck_window_days": int(parsed.get("recheck_window_days") or 30),
                "see_doctor_specialty": parsed.get("see_doctor_specialty"),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[exam_explain] LLM 失败 user={user_id} exam={exam_id}: {e}")
        explanation = None

    return {
        "exam": {
            "id": exam.id,
            "exam_type": exam.exam_type,
            "exam_date": str(exam.exam_date),
        },
        "abnormal_items": abnormal_items,
        "trends": trends,
        "explanation": explanation,
        "related_cards": related_cards,
        "user_gene_hits": gene_hits,
    }
