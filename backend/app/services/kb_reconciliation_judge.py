"""System KB V2 跨源对账 —— Phase B P5:LLM judge(advisory)+ can_auto_approve 9 闸 + auto executor。

**安全由 `can_auto_approve` 的服务端硬闸负责,不信 judge 自报。** judge 只 advisory 给 relation_tag + score。
Founder ratified(见设计 §10):
- τ=0.95 全局(`_AUTO_APPROVE_TAU`);eval 不再硬 gate 但仍必跑测精度 + 不变量。
- **claim_overlap v1 恒人工**(#2)—— auto 只对 kind==entity_align。
- 医疗类 entity_type 永不 auto(#2)。
- 同类 reviewed×reviewed 需**强信号硬合取**(#4:edge_neighborhood ∧ alias_overlap ∧ 归一 title 命中)。
- auto **ships DISABLED**:只对**显式传入**的 enabled_entity_types 跑,默认空集 = 什么都不自动。

自动合并**调 P4 的 `merge_candidate`**(actor='llm_dedup_judge:vN'):additive + 可逆(C9 依赖已过的 unalign)+
prescriptive/无 reviewed 锚硬拒(can_merge 复用)+ license fail-closed。

**关于 conflict(诚实说明)**:`relation_tag=='conflict'` 是 **judge advisory**——P3 detector 从不发 conflict,
judge 是唯一来源,故「judge 说谎 duplicate」时 can_merge 的 conflict 分支不触发。**真正不信 judge 的服务端
backstop 是**:(1) prescriptive floor(entity_type + 药名/剂量内容);(2) reviewed down-dedao 锚(resolve_canonical);
(3) 同类 reviewed 需强信号硬合取;(4) **C6b 确定性状态反义冲突**(阳性/未知 等,`_deterministic_conflict`);
(5) 全程 additive + 可逆(unalign)。judge 唯一能左右的是 relation_tag+score,被这五道 + τ 夹死。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBAudit, KBDocument, KBReconciliationCandidate
from app.services.kb_reconciliation import _norm_title
from app.services.kb_reconciliation_merge import (
    _is_prescriptive,
    _sides,
    can_merge,
    merge_candidate,
)

JUDGE_VERSION = "v1"
JUDGE_ACTOR = f"llm_dedup_judge:{JUDGE_VERSION}"  # 机器 actor,永非人 reviewer_id(审计可辨 + 熔断可圈)
_AUTO_APPROVE_TAU = 0.95  # founder ratified 全局阈(§10);doc-drift 钉此常量

# ── P6 运行时后备(§10:开任何 entity_type 的 auto 前必接)──
_SHADOW_AUDIT_EVERY = 20   # 每 20 笔 auto 合抽 1 笔进影子人工复核(founder Q7:1/20 抽样)
_MAX_AUTO_PER_RUN = 20     # 单次运行 auto 合上限(爆炸半径帽;到帽即停 auto,fail-loud auto_capped)
_BREAKER_WINDOW = 200      # 熔断窗口:最近 200 笔 auto 合
_BREAKER_FP_BUDGET = 1.0 / 200  # 误合率预算(founder Q7:≤1/200);检出率**严格超**预算即熔断
# 医疗/处方类 entity_type:永不 auto(#2;与 claim_overlap 恒人工叠加)。
_AUTO_NEVER_ENTITY_TYPES = frozenset(
    {"medication", "drug", "supplement", "diet", "nutrient", "gene", "regimen", "dose", "dosage"}
)
_VALID_TAGS = ("duplicate", "agree", "complementary", "conflict")

# 确定性状态反义对 —— 命中即**确定性冲突**(不同状态/结论,绝非 duplicate)。服务端 backstop,
# **不信 judge**(P3 detector 从不发 conflict,judge 是唯一 conflict 来源;这里补服务端硬拒)。
# 关掉 Hp阳性×Hp未知 这类「相关非同」被 judge 误判 duplicate 后自动合的路径。
_CONFLICT_ANTONYMS = (
    ("阳性", "阴性"), ("阳性", "未知"), ("阳性", "不明"), ("阴性", "未知"), ("阴性", "不明"),
    ("positive", "negative"), ("positive", "unknown"), ("negative", "unknown"),
    ("升高", "降低"), ("偏高", "偏低"), ("过高", "过低"), ("增高", "减低"),
    ("缺乏", "过量"), ("不足", "过量"), ("急性", "慢性"),
    ("high", "low"), ("elevated", "reduced"), ("deficiency", "excess"),
)


def _text_bag(doc: KBDocument) -> str:
    parts = [doc.title or ""]
    parts += [str(x) for x in (doc.metadata_json or {}).get("aliases") or []]
    return " ".join(parts).lower()


def _deterministic_conflict(left: KBDocument, right: KBDocument) -> bool:
    """两条目在某状态轴上取反(一侧 A-only、另一侧 B-only)→ 确定性冲突。over-block 偏向(走人=安全)。"""
    lt, rt = _text_bag(left), _text_bag(right)
    for a, b in _CONFLICT_ANTONYMS:
        a, b = a.lower(), b.lower()
        la, lb, ra, rb = a in lt, b in lt, a in rt, b in rt
        if (la and rb and not lb and not ra) or (lb and ra and not la and not rb):
            return True
    return False

# 可注入分类器(测试/eval 用 fake);默认走 LLM,失败 fail-safe 返回 score=0 → 不自动。
Classifier = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


def _doc_view(doc: KBDocument) -> Dict[str, Any]:
    meta = doc.metadata_json or {}
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "summary": doc.summary,
        "entity_type": doc.entity_type,
        "aliases": meta.get("aliases") or [],
        "origin": meta.get("origin"),
    }


def _default_classifier(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """默认 LLM 分类器。任何失败 → 保守 {relation_tag:None, score:0.0} → 不触发 auto(fail-safe)。"""
    try:
        from app.services.llm.factory import get_llm_provider

        provider = get_llm_provider()
        prompt = (
            "你是知识库跨源判重器。判断两条目是否为**同一指称的重复**。只输出 JSON:\n"
            '{"relation_tag":"duplicate|agree|complementary|conflict","score":0..1,"rationale":"..."}\n'
            "duplicate=同一实体/同一 claim 的重复;complementary=相关但内容互补(勿合);"
            "conflict=矛盾(勿合);agree=一致但非重复。score=你对该判定的置信度。\n"
            f"条目A: {json.dumps(left, ensure_ascii=False)}\n条目B: {json.dumps(right, ensure_ascii=False)}"
        )
        raw = provider.complete(prompt)  # 同步补全
        text = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            return {"relation_tag": None, "score": 0.0, "rationale": "unparseable"}
        obj = json.loads(text[start : end + 1])
        tag = obj.get("relation_tag")
        score = float(obj.get("score") or 0.0)
        if tag not in _VALID_TAGS:
            tag, score = None, 0.0
        return {"relation_tag": tag, "score": max(0.0, min(1.0, score)), "rationale": str(obj.get("rationale") or "")[:500]}
    except Exception as exc:  # noqa: BLE001 — judge 失败必须 fail-safe(不自动),不得抛断扫描
        return {"relation_tag": None, "score": 0.0, "rationale": f"judge_error: {type(exc).__name__}"}


def _normalize_verdict(v: Any) -> Dict[str, Any]:
    """夹死任何分类器输出:tag 非法→None,score clamp [0,1]。不信任何 classifier 的原始返回。"""
    if not isinstance(v, dict):
        return {"relation_tag": None, "score": 0.0, "rationale": "bad verdict type"}
    tag = v.get("relation_tag")
    if tag not in _VALID_TAGS:
        tag = None
    try:
        score = float(v.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return {"relation_tag": tag, "score": max(0.0, min(1.0, score)), "rationale": str(v.get("rationale") or "")[:500]}


def classify_candidate(
    db: Session, cand: KBReconciliationCandidate, *, classifier: Optional[Classifier] = None,
    commit: bool = True,
) -> Dict[str, Any]:
    """advisory 分类。写回 candidate.relation_tag + score + signals['judge']。

    **对任意 classifier fail-safe**:分类器抛异常 → 保守 {None,0.0}(不抛断扫描);
    输出经 `_normalize_verdict` 夹死(非法 tag→None、score clamp)。安全不依赖分类器自律。
    commit=False:只在 session 内写不提交(供 dry-run preview 末尾整体 rollback)。
    """
    left, right = _sides(db, cand)
    if left is None or right is None:
        return {"relation_tag": None, "score": 0.0, "rationale": "missing docs"}
    fn = classifier or _default_classifier
    try:
        raw = fn(_doc_view(left), _doc_view(right))
    except Exception as exc:  # noqa: BLE001 — judge 失败 fail-safe,不得抛断批量/eval
        raw = {"relation_tag": None, "score": 0.0, "rationale": f"classifier_error: {type(exc).__name__}"}
    verdict = _normalize_verdict(raw)
    # content_hash 完全相同是**确定性** duplicate,不被 judge 降级(结构真相 > judge)。
    detectors = (cand.signals or {}).get("detectors") or []
    if "content_hash" in detectors:
        verdict = {"relation_tag": "duplicate", "score": max(verdict.get("score") or 0.0, 1.0),
                   "rationale": "deterministic content_hash match"}
    cand.relation_tag = verdict.get("relation_tag")
    if verdict.get("score") is not None:
        cand.score = float(verdict["score"])
    sig = dict(cand.signals or {})
    sig["judge"] = {"version": JUDGE_VERSION, **verdict}
    cand.signals = sig
    if commit:
        db.commit()
    return verdict


def _strong_signal_conjunction(cand: KBReconciliationCandidate, left: KBDocument, right: KBDocument) -> bool:
    """同类 reviewed×reviewed auto 的硬合取(#4):edge_neighborhood ∧ alias_overlap ∧ 归一 title 命中。
    从 signals(服务端持久,非 judge 自报)判。"""
    detectors = set((cand.signals or {}).get("detectors") or [])
    if not ({"edge_neighborhood", "alias_overlap"} <= detectors):
        return False
    lt, rt = _norm_title(left.title), _norm_title(right.title)
    return bool(lt) and lt == rt


_MERGE_AUDIT_OPS = ("entity_align_approved", "claim_merge_source_folded")


def auto_breaker_status(db: Session) -> Dict[str, Any]:
    """**粘性**熔断(§10 P6,按 JUDGE_ACTOR 圈定):上次人工 reset 之后,**任何**一笔 auto 合被人
    unalign(= 检出误合)即熔断,且**保持熔断直到显式人工 reset**(`reset_auto_breaker`)。

    为什么粘性而非滑动窗口率:窗口率会被后续干净合**稀释自愈**(对抗审计实测:1 误合 + 10 笔在途
    干净合即回到预算内),与「人工复核后方可恢复」矛盾。粘性 = 严格 fail-closed(比 1/200 预算更严,
    over-refuse 方向);rate/window 仅作观测报告。确定性、无新表:全从 KBAudit 推。
    诚实说明:merge 审计行若缺 candidate_id 只影响观测 rate 的分母;熔断判定只依赖 unalign 行的
    merged_by(当前代码恒写),不受其影响。
    """
    # 上次人工 reset(无则从头算)。id 单调,拿最新一条。
    last_reset = (
        db.query(KBAudit)
        .filter(KBAudit.op == "breaker_reset")
        .order_by(KBAudit.id.desc())
        .first()
    )
    reset_id = last_reset.id if last_reset is not None else 0
    # reset 之后检出的 auto 误合(unalign 行 merged_by==JUDGE_ACTOR)。unalign 是稀少人工动作,
    # 且已按 id > reset_id 过滤,规模有界。
    unaligns = (
        db.query(KBAudit)
        .filter(KBAudit.op == "entity_align_unaligned", KBAudit.id > reset_id)
        .all()
    )
    detected_fp = sum(1 for u in unaligns if (u.diff or {}).get("merged_by") == JUDGE_ACTOR)
    tripped = detected_fp >= 1  # 粘性:reset 后任一检出误合即熔断,不自愈

    # 观测用滑动窗口率(信息性,不参与判定)
    recent = (
        db.query(KBAudit)
        .filter(KBAudit.actor == JUDGE_ACTOR, KBAudit.op.in_(_MERGE_AUDIT_OPS))
        .order_by(KBAudit.ts.desc(), KBAudit.id.desc())
        .limit(_BREAKER_WINDOW)
        .all()
    )
    window = len(recent)
    return {
        "tripped": tripped,
        "detected_fp": detected_fp,
        "since_reset_audit_id": reset_id,
        "window": window,
        "rate": round(detected_fp / window, 4) if window else None,
        "budget": _BREAKER_FP_BUDGET,
        "semantics": "sticky: any detected FP since last human reset trips until explicit reset",
    }


def reset_auto_breaker(db: Session, *, actor: str, note: str = "") -> Dict[str, Any]:
    """人工复位熔断(审计化):确认 reset 前的误合已复核处理。之后**新**检出误合会再次熔断。"""
    db.add(KBAudit(doc_id=None, op="breaker_reset", actor=actor, diff={"note": note[:500]}))
    db.commit()
    return auto_breaker_status(db)


def can_auto_approve(
    db: Session,
    cand: KBReconciliationCandidate,
    *,
    enabled_entity_types: frozenset,
    breaker: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """9+ 闸服务端硬门(re-read live rows,不信 judge)。全 True 才可无人自动合。返回 (ok, reasons)。

    breaker 可传预计算结果(批量循环省查询);None 则现算。熔断中 → 一律拒(C10)。
    """
    reasons: List[str] = []
    # C10 粘性熔断:上次人工 reset 后有任一检出误合 → 全体 auto 停(fail-closed,先判;
    # 不自愈,与「人工复核后方可恢复」逐字一致 —— reset 走 /reconciliation/breaker/reset 审计化端点)
    b = breaker if breaker is not None else auto_breaker_status(db)
    if b.get("tripped"):
        return False, [
            f"C10 熔断中(粘性):上次 reset 后检出 {b.get('detected_fp')} 笔 auto 误合;"
            f"人工复核并显式 reset 后方可恢复"
        ]
    # 先过人工合并同一道硬闸(conflict/prescriptive/无 reviewed 锚)。
    ok, why, canonical_id = can_merge(db, cand)
    if not ok:
        return False, [f"can_merge 拒: {why}"]
    left, right = _sides(db, cand)

    # C1:仅 entity_align + duplicate(claim_overlap v1 恒人工;#2)
    if cand.kind != "entity_align":
        reasons.append("C1 非 entity_align(claim_overlap v1 恒人工)")
    if cand.relation_tag != "duplicate":
        reasons.append("C1 relation_tag 非 duplicate")
    # C6b(服务端确定性冲突 backstop,不信 judge):状态反义(阳性/未知 等)→ 非重复,拒
    if _deterministic_conflict(left, right):
        reasons.append("C6b 确定性状态冲突(反义,如 阳性/未知)→ 非重复,走人")
    # C5(auto 加严):医疗/处方类 entity_type 永不 auto
    for d in (left, right):
        if (d.entity_type or "").lower() in _AUTO_NEVER_ENTITY_TYPES:
            reasons.append(f"C5 医疗类 entity_type={d.entity_type} 永不 auto")
            break
    # 显式启用门:enabled_entity_types 空 = 什么都不自动(ships DISABLED)
    et = (left.entity_type or right.entity_type or "").lower()
    if et not in {e.lower() for e in enabled_entity_types}:
        reasons.append(f"entity_type={et} 未在 enabled 集(auto 默认 DISABLED)")
    # C8:τ=0.95 全局
    if (cand.score or 0.0) < _AUTO_APPROVE_TAU:
        reasons.append(f"C8 score={cand.score} < τ={_AUTO_APPROVE_TAU}")
    # #4:同类 reviewed×reviewed 需强信号硬合取
    both_reviewed = (
        (left.metadata_json or {}).get("review_status") == "reviewed"
        and (right.metadata_json or {}).get("review_status") == "reviewed"
    )
    if both_reviewed and not _strong_signal_conjunction(cand, left, right):
        reasons.append("#4 同类 reviewed×reviewed 缺强信号合取(edge∧alias∧title)")

    return (len(reasons) == 0), reasons


def confirm_shadow_audit(db: Session, candidate_id: int, *, actor: str) -> Dict[str, Any]:
    """影子复核确认:人看过这笔 auto 合,判定正确。(判定错误 → 走 unalign,那才是误合信号。)"""
    cand = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.id == candidate_id)
        .first()
    )
    if cand is None:
        raise ValueError("candidate 不存在")
    shadow = (cand.decision or {}).get("shadow_audit") or {}
    if cand.status != "approved" or shadow.get("status") != "pending":
        raise ValueError("非待影子复核的 auto 合,无可确认")
    decision = dict(cand.decision or {})
    decision["shadow_audit"] = {**shadow, "status": "confirmed", "confirmed_by": actor}
    cand.decision = decision
    db.add(KBAudit(doc_id=None, op="shadow_audit_confirmed", actor=actor,
                   diff={"candidate_id": candidate_id}))
    db.commit()
    return {"candidate_id": candidate_id, "shadow_audit": "confirmed"}


def preview_auto_merge(
    db: Session,
    *,
    enabled_entity_types: Optional[frozenset] = None,
    classifier: Optional[Classifier] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """**Dry-run**:跑真 judge + 9 闸,报「会 auto 合的候选」+ 各 skip 理由,**零 serving mutation、
    零候选状态改动**(judge 的 relation_tag/score 写在 SAVEPOINT 里,结束 rollback)。

    首次为某 entity_type 开 auto 前的 look-before-you-leap:人先看真 judge 在真候选上会合掉哪些
    (含真实分数),确认这批对再翻 enable —— τ=0.95(比零误合激进)下的补偿控制。
    """
    enabled = frozenset(enabled_entity_types or ())
    opens = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.status == "open")
        .order_by(KBReconciliationCandidate.id.asc())
        .limit(max(1, min(int(limit or 200), 1000)))
        .all()
    )
    would_merge: List[Dict[str, Any]] = []
    would_skip: List[Dict[str, Any]] = []
    breaker = auto_breaker_status(db)
    # judge 的 advisory 写入用 commit=False 只留在 session,函数末整体 rollback →
    # 预览零副作用(连 judge 分数都不落库)。前置的 scan/候选已各自 commit,不受影响。
    try:
        for cand in opens:
            verdict = classify_candidate(db, cand, classifier=classifier, commit=False)
            ok, reasons = can_auto_approve(db, cand, enabled_entity_types=enabled, breaker=breaker)
            row = {
                "candidate_id": cand.id,
                "left_doc_id": cand.left_doc_id,
                "right_doc_id": cand.right_doc_id,
                "entity_type": cand.entity_type,
                "canonical_hint": cand.canonical_hint,
                "judge": {"relation_tag": verdict.get("relation_tag"), "score": verdict.get("score")},
            }
            if ok:
                would_merge.append(row)
            else:
                would_skip.append({**row, "reasons": reasons})
    finally:
        db.rollback()  # 丢弃全部未提交 judge 写入 → 候选状态与调用前一致
    return {
        "dry_run": True,
        "previewed": len(opens),
        "would_auto_merge": would_merge,
        "would_auto_merge_count": len(would_merge),
        "would_skip_count": len(would_skip),
        "would_skip_sample": would_skip[:20],
        "enabled_entity_types": sorted(enabled),
        "tau": _AUTO_APPROVE_TAU,
        "breaker_tripped": breaker.get("tripped"),
    }


def run_judge_and_auto(
    db: Session,
    *,
    actor: str,
    enabled_entity_types: Optional[frozenset] = None,
    classifier: Optional[Classifier] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """对 open 候选跑 judge(写 relation_tag/score),再对过 9 闸者无人自动合(调 P4 merge_candidate)。

    **enabled_entity_types 默认空 = 只 judge 不 auto(ships DISABLED)。** 每次 auto 合写 KBAudit(机器 actor)。
    """
    enabled = frozenset(enabled_entity_types or ())
    opens = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.status == "open")
        .order_by(KBReconciliationCandidate.id.asc())
        .limit(max(1, min(int(limit or 200), 1000)))
        .all()
    )
    judged = 0
    auto_merged = 0
    left_for_human = 0
    auto_capped = False
    auto_merge_errors = 0
    shadow_enqueued = 0
    # 影子抽样位置:每轮随机(否则 cap=20 下永远只抽每轮第 1 笔 = 确定性位置可被排序操纵)
    import random as _random
    shadow_pos = _random.randrange(_SHADOW_AUDIT_EVERY)
    breaker = auto_breaker_status(db)  # 起点快照仅供返回值观测
    for cand in opens:
        classify_candidate(db, cand, classifier=classifier)
        judged += 1
        if auto_merged >= _MAX_AUTO_PER_RUN:
            # 单次运行帽:到帽后剩余全部留人工(fail-loud,不静默继续无人合)
            auto_capped = True
            left_for_human += 1
            continue
        # 熔断每候选**现算**(breaker=None):并发 unalign 落地即刻生效,不吃整轮陈旧快照
        # (对抗审计实测:陈旧快照正是稀释自愈的喂料口)。粘性熔断下查询有界,量小可承受。
        ok, _reasons = can_auto_approve(db, cand, enabled_entity_types=enabled, breaker=None)
        if not ok:
            left_for_human += 1
            continue
        try:
            merge_candidate(db, cand.id, actor=JUDGE_ACTOR)
        except ValueError:
            # 闸后竞态(文档被并发改/删等):单条失败不炸批,计数暴露,留人工
            auto_merge_errors += 1
            left_for_human += 1
            continue
        auto_merged += 1
        # 影子审计抽样(founder Q7:1/20 为下限;短轮次会过抽 = 保守方向):
        # 抽中的 auto 合标 pending,等人静默复核;人若判误合 → unalign → 粘性熔断。
        if auto_merged % _SHADOW_AUDIT_EVERY == shadow_pos or _SHADOW_AUDIT_EVERY == 1:
            decision = dict(cand.decision or {})
            decision["shadow_audit"] = {
                "status": "pending",
                "requested_at": datetime.now(timezone.utc).isoformat(),
            }
            cand.decision = decision
            db.add(KBAudit(doc_id=None, op="shadow_audit_enqueued", actor=JUDGE_ACTOR,
                           diff={"candidate_id": cand.id}))
            db.commit()
            shadow_enqueued += 1
    return {
        "judged": judged,
        "auto_merged": auto_merged,
        "left_for_human": left_for_human,
        "auto_capped": auto_capped,
        "auto_merge_errors": auto_merge_errors,
        "shadow_enqueued": shadow_enqueued,
        "breaker": breaker,
        "enabled_entity_types": sorted(enabled),
        "tau": _AUTO_APPROVE_TAU,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
