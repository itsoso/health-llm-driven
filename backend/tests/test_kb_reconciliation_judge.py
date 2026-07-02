"""KB Phase-B P5:LLM judge(advisory)+ can_auto_approve 9 闸 + auto executor + eval。

安全在服务端 can_auto_approve(不信 judge):τ=0.95、entity_align only、医疗类永不 auto、
同类 reviewed 需强信号、显式启用才 auto(默认 DISABLED)。auto 合并复用 P4(可逆 + 硬拒)。
"""
import pytest

from app.models.system_knowledge import KBDocument, KBReconciliationCandidate
from app.services.kb_reconciliation_judge import (
    can_auto_approve,
    classify_candidate,
    run_judge_and_auto,
)
from app.services.kb_reconciliation_eval import check_merge_invariants, run_dedup_judge_eval

DOWN = "down-dedao-llm-wiki"
KBASE = "dedao-kbase-export"


def _doc(db, doc_id, *, entity_type="condition", origin=DOWN, review_status="reviewed",
         title="幽门螺杆菌", aliases=None, doc_type="entity"):
    meta = {"origin": origin, "review_status": review_status}
    if aliases is not None:
        meta["aliases"] = aliases
    db.add(KBDocument(doc_id=doc_id, doc_type=doc_type, entity_type=entity_type,
                      title=title, is_archived=False, metadata_json=meta))
    db.commit()


def _cand(db, left, right, *, kind="entity_align", relation_tag="duplicate", score=0.99,
          detectors=("alias_overlap",), gold_label=None):
    sig = {"detectors": list(detectors)}
    if gold_label:
        sig["gold_label"] = gold_label
    c = KBReconciliationCandidate(kind=kind, left_doc_id=left, right_doc_id=right,
                                  relation_tag=relation_tag, score=score, status="open", signals=sig)
    db.add(c)
    db.commit()
    return c.id


def _get(db, cid):
    return db.query(KBReconciliationCandidate).filter_by(id=cid).first()


# fake 分类器:标题含 "dup" → duplicate 0.99;否则 complementary 0.3(精确的 judge)。
def _fake_classifier(left, right):
    if "dup" in (left.get("title") or "").lower():
        return {"relation_tag": "duplicate", "score": 0.99, "rationale": "fake dup"}
    return {"relation_tag": "complementary", "score": 0.3, "rationale": "fake non-dup"}


def test_auto_approve_happy_path(db):
    _doc(db, "dd:hp", origin=DOWN, review_status="reviewed", entity_type="condition")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", entity_type="condition")
    cid = _cand(db, "dd:hp", "kb:hp")
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"condition"}))
    assert ok is True, reasons


def test_auto_disabled_by_default(db):
    _doc(db, "dd:hp", origin=DOWN); _doc(db, "kb:hp", origin=KBASE, review_status="draft")
    cid = _cand(db, "dd:hp", "kb:hp")
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset())
    assert ok is False and any("DISABLED" in r for r in reasons)


def test_claim_overlap_never_auto(db):
    _doc(db, "dd:c", origin=DOWN, doc_type="claim", entity_type="concept")
    _doc(db, "kb:c", origin=KBASE, review_status="draft", doc_type="claim", entity_type="concept")
    cid = _cand(db, "dd:c", "kb:c", kind="claim_overlap")
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"concept"}))
    assert ok is False and any("entity_align" in r for r in reasons)


def test_medical_entity_type_never_auto(db):
    # gene 在 _AUTO_NEVER 但不在处方集 → 过 can_merge 但被 C5 auto-never 拒
    _doc(db, "dd:g", origin=DOWN, entity_type="gene", title="MTHFR")
    _doc(db, "kb:g", origin=KBASE, review_status="draft", entity_type="gene", title="mthfr")
    cid = _cand(db, "dd:g", "kb:g")
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"gene"}))
    assert ok is False and any("医疗类" in r for r in reasons)


def test_score_below_tau_blocks(db):
    _doc(db, "dd:hp", origin=DOWN); _doc(db, "kb:hp", origin=KBASE, review_status="draft")
    cid = _cand(db, "dd:hp", "kb:hp", score=0.9)
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"condition"}))
    assert ok is False and any("τ" in r for r in reasons)


def test_same_class_reviewed_needs_strong_signal(db):
    # 两侧都 reviewed down-dedao → 需 edge∧alias∧同 title 强信号
    _doc(db, "dd:a", origin=DOWN, review_status="reviewed", title="幽门螺杆菌")
    _doc(db, "dd:b", origin=DOWN, review_status="reviewed", title="幽门螺杆菌")
    # 弱信号(只 alias)→ 拒
    cid_weak = _cand(db, "dd:a", "dd:b", detectors=("alias_overlap",))
    ok, reasons = can_auto_approve(db, _get(db, cid_weak), enabled_entity_types=frozenset({"condition"}))
    assert ok is False and any("强信号" in r for r in reasons)


def test_same_class_reviewed_with_strong_signal_ok(db):
    _doc(db, "dd:a", origin=DOWN, review_status="reviewed", title="幽门螺杆菌")
    _doc(db, "dd:b", origin=DOWN, review_status="reviewed", title="幽门螺杆菌")  # 同归一 title
    cid = _cand(db, "dd:a", "dd:b", detectors=("edge_neighborhood", "alias_overlap"))
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"condition"}))
    assert ok is True, reasons


def test_content_hash_forces_duplicate_over_judge(db):
    _doc(db, "dd:hp", origin=DOWN); _doc(db, "kb:hp", origin=KBASE, review_status="draft", title="其它")
    cid = _cand(db, "dd:hp", "kb:hp", relation_tag=None, score=0.0, detectors=("content_hash",))
    # fake 会返回 complementary(title 无 dup),但 content_hash 强制 duplicate 1.0
    verdict = classify_candidate(db, _get(db, cid), classifier=_fake_classifier)
    assert verdict["relation_tag"] == "duplicate" and verdict["score"] == 1.0


def test_run_judge_and_auto_disabled_only_judges(db):
    _doc(db, "dd:hp", origin=DOWN, title="dup幽门"); _doc(db, "kb:hp", origin=KBASE, review_status="draft", title="dup幽门")
    _cand(db, "dd:hp", "kb:hp", relation_tag=None, score=0.0)
    res = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset(), classifier=_fake_classifier)
    assert res["judged"] == 1 and res["auto_merged"] == 0  # DISABLED → 只 judge


def test_run_judge_and_auto_enabled_merges(db):
    _doc(db, "dd:hp", origin=DOWN, review_status="reviewed", entity_type="condition", title="dup幽门")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", entity_type="condition", title="dup幽门")
    _cand(db, "dd:hp", "kb:hp", relation_tag=None, score=0.0)
    res = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}),
                             classifier=_fake_classifier)
    assert res["auto_merged"] == 1
    loser = db.query(KBDocument).filter_by(doc_id="kb:hp").first()
    assert loser.is_archived is True  # 真的合了


def test_eval_precision_zero_fp_and_invariants(db):
    # gold:一对真重复(title 含 dup)+ 一对近似非重复
    _doc(db, "dd:dup", origin=DOWN, review_status="reviewed", entity_type="condition", title="dup幽门")
    _doc(db, "kb:dup", origin=KBASE, review_status="draft", entity_type="condition", title="dup幽门")
    _doc(db, "dd:neg", origin=DOWN, review_status="reviewed", entity_type="condition", title="胃炎")
    _doc(db, "kb:neg", origin=KBASE, review_status="draft", entity_type="condition", title="胃溃疡")
    dup_id = _cand(db, "dd:dup", "kb:dup", relation_tag=None, score=0.0, gold_label="duplicate")
    _cand(db, "dd:neg", "kb:neg", relation_tag=None, score=0.0, gold_label="not_duplicate")

    report = run_dedup_judge_eval(db, classifier=_fake_classifier,
                                  enabled_entity_types=frozenset({"condition"}))
    assert report["n"] == 2
    assert report["auto_approve_fp"] == 0  # 精确 judge → 无无人误合
    assert report["precision"] == 1.0

    # 对会 auto-fire 的真重复跑 6 不变量断言(merge→断言→unalign 还原)
    checks = check_merge_invariants(db, dup_id, actor="eval")
    assert all(checks.values()), checks


# ── 对抗回归:任意 classifier fail-safe + 确定性状态冲突 backstop ──

def test_raising_classifier_is_failsafe_no_batch_abort(db):
    """分类器抛异常 → classify 不抛、该候选不 auto(score 0),批量不中断。"""
    _doc(db, "dd:hp", origin=DOWN, review_status="reviewed", entity_type="condition")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", entity_type="condition")
    _cand(db, "dd:hp", "kb:hp", relation_tag=None, score=0.0)

    def _boom(left, right):
        raise RuntimeError("judge exploded")

    res = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}), classifier=_boom)
    assert res["judged"] == 1 and res["auto_merged"] == 0  # fail-safe:不合、不崩


def test_invalid_verdict_clamped_and_sanitized(db):
    """分类器返回越界 score + 非法 tag → 夹死(score∈[0,1]、tag→None),不写入垃圾、不 auto。"""
    _doc(db, "dd:hp", origin=DOWN, review_status="reviewed", entity_type="condition")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", entity_type="condition")
    cid = _cand(db, "dd:hp", "kb:hp", relation_tag=None, score=0.0)

    def _bogus(left, right):
        return {"relation_tag": "TOTALLY_BOGUS", "score": 5.0, "rationale": "x"}

    classify_candidate(db, _get(db, cid), classifier=_bogus)
    c = _get(db, cid)
    assert c.relation_tag is None          # 非法 tag 不落库
    assert 0.0 <= (c.score or 0.0) <= 1.0  # score 夹死
    ok, _ = can_auto_approve(db, c, enabled_entity_types=frozenset({"condition"}))
    assert ok is False  # 非 duplicate → 不 auto


def test_deterministic_conflict_blocks_auto_even_if_judge_says_duplicate(db):
    """Hp阳性(reviewed)× Hp未知(draft):judge 说 duplicate 0.99,但状态反义 → C6b 服务端硬拒。"""
    _doc(db, "dd:pos", origin=DOWN, review_status="reviewed", entity_type="condition",
         title="幽门螺杆菌阳性")
    _doc(db, "kb:unk", origin=KBASE, review_status="draft", entity_type="condition",
         title="幽门螺杆菌状态未知")
    cid = _cand(db, "dd:pos", "kb:unk", relation_tag="duplicate", score=0.99)
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"condition"}))
    assert ok is False and any("冲突" in r for r in reasons)


# ── P6 运行时后备:影子审计 + 速率熔断 + 单次运行帽(开 auto 前必接)──

from app.services.kb_reconciliation_judge import (
    JUDGE_ACTOR,
    auto_breaker_status,
    confirm_shadow_audit,
)
from app.services.kb_reconciliation_merge import merge_candidate, unalign_candidate


def _auto_merge_pair(db, n, *, et="condition"):
    """造第 n 对(reviewed down-dedao × draft kbase)并以 JUDGE_ACTOR 合并 = 模拟一笔 auto 合。"""
    _doc(db, f"dd:{n}", origin=DOWN, review_status="reviewed", entity_type=et, title=f"实体{n}")
    _doc(db, f"kb:{n}", origin=KBASE, review_status="draft", entity_type=et, title=f"实体{n}别名")
    cid = _cand(db, f"dd:{n}", f"kb:{n}")
    merge_candidate(db, cid, actor=JUDGE_ACTOR)
    return cid


def test_breaker_trips_on_detected_fp_and_blocks_auto(db):
    """2 笔 auto 合,人 unalign 其中 1 笔(检出误合)→ 率 1/2 > 1/200 → 熔断,C10 拒一切 auto。"""
    c1 = _auto_merge_pair(db, 1)
    _auto_merge_pair(db, 2)
    assert auto_breaker_status(db)["tripped"] is False  # 未检出误合 → 不熔断

    unalign_candidate(db, c1, actor="admin:9")  # 人工撤销 auto 合 = 检出一笔误合
    b = auto_breaker_status(db)
    assert b["tripped"] is True and b["detected_fp"] == 1

    # 熔断中:新候选即便全闸绿也被 C10 拒
    _doc(db, "dd:new", origin=DOWN, review_status="reviewed", entity_type="condition")
    _doc(db, "kb:new", origin=KBASE, review_status="draft", entity_type="condition")
    cid = _cand(db, "dd:new", "kb:new")
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"condition"}))
    assert ok is False and any("C10" in r for r in reasons)


def test_human_merge_unalign_does_not_trip_breaker(db):
    """人工合并被撤销(merged_by=人)不计入 judge 熔断窗口 —— 熔断只按机器 actor 圈定。"""
    _doc(db, "dd:h", origin=DOWN, review_status="reviewed", entity_type="condition")
    _doc(db, "kb:h", origin=KBASE, review_status="draft", entity_type="condition")
    cid = _cand(db, "dd:h", "kb:h")
    merge_candidate(db, cid, actor="admin:1")  # 人工合
    unalign_candidate(db, cid, actor="admin:2")
    assert auto_breaker_status(db)["tripped"] is False  # 窗口里没有 judge 的 auto 合


def test_shadow_audit_sampling_and_confirm(db, monkeypatch):
    """抽样=1(monkeypatch)→ 每笔 auto 合都标 shadow pending;confirm 后转 confirmed。"""
    import app.services.kb_reconciliation_judge as m

    monkeypatch.setattr(m, "_SHADOW_AUDIT_EVERY", 1)
    _doc(db, "dd:s", origin=DOWN, review_status="reviewed", entity_type="condition", title="dup实体S")
    _doc(db, "kb:s", origin=KBASE, review_status="draft", entity_type="condition", title="dup实体S别名")
    _cand(db, "dd:s", "kb:s", relation_tag=None, score=0.0)
    res = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}),
                             classifier=_fake_classifier)
    assert res["auto_merged"] == 1 and res["shadow_enqueued"] == 1

    cand = db.query(KBReconciliationCandidate).first()
    assert (cand.decision or {}).get("shadow_audit", {}).get("status") == "pending"
    confirm_shadow_audit(db, cand.id, actor="admin:1")
    cand = db.query(KBReconciliationCandidate).first()
    assert cand.decision["shadow_audit"]["status"] == "confirmed"
    # 已确认不可重复确认
    import pytest as _pytest
    with _pytest.raises(ValueError):
        confirm_shadow_audit(db, cand.id, actor="admin:1")


def test_auto_per_run_cap(db, monkeypatch):
    """单次运行帽:cap=1 时两笔可自动的只合 1 笔,auto_capped fail-loud,其余留人工。"""
    import app.services.kb_reconciliation_judge as m

    monkeypatch.setattr(m, "_MAX_AUTO_PER_RUN", 1)
    for i in range(2):
        _doc(db, f"dd:c{i}", origin=DOWN, review_status="reviewed", entity_type="condition", title=f"dup实体{i}")
        _doc(db, f"kb:c{i}", origin=KBASE, review_status="draft", entity_type="condition", title=f"dup实体{i}x")
        _cand(db, f"dd:c{i}", f"kb:c{i}", relation_tag=None, score=0.0)
    res = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}),
                             classifier=_fake_classifier)
    assert res["auto_merged"] == 1
    assert res["auto_capped"] is True
    assert res["left_for_human"] == 1


def test_merge_error_mid_batch_contained(db, monkeypatch):
    """闸后 merge 抛 ValueError(竞态)→ 单条计入 auto_merge_errors,批次不炸。"""
    import app.services.kb_reconciliation_judge as m

    _doc(db, "dd:e", origin=DOWN, review_status="reviewed", entity_type="condition", title="dup实体E")
    _doc(db, "kb:e", origin=KBASE, review_status="draft", entity_type="condition", title="dup实体Ex")
    _cand(db, "dd:e", "kb:e", relation_tag=None, score=0.0)

    def _boom_merge(db_, cid_, *, actor):
        raise ValueError("竞态:文档已被并发修改")

    monkeypatch.setattr(m, "merge_candidate", _boom_merge)
    res = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}),
                             classifier=_fake_classifier)
    assert res["auto_merge_errors"] == 1
    assert res["auto_merged"] == 0
    assert res["judged"] == 1  # 批次跑完,没中断


def test_unalign_records_merged_by_for_breaker(db):
    """unalign 审计行必须带 merged_by(熔断按它圈定 auto 误合)。"""
    from app.models.system_knowledge import KBAudit

    cid = _auto_merge_pair(db, 7)
    unalign_candidate(db, cid, actor="admin:1")
    row = db.query(KBAudit).filter(KBAudit.op == "entity_align_unaligned").first()
    assert row.diff.get("merged_by") == JUDGE_ACTOR


# ── 对抗回归(skeptic 抓的 fail-open):粘性熔断不稀释自愈 + 显式 reset + 影子队列不埋页 ──

from app.services.kb_reconciliation_judge import reset_auto_breaker


def test_breaker_sticky_no_dilution_self_heal(db):
    """对抗回归:1 笔误合后,再多干净 auto 合也**不自愈**(旧窗口率会被稀释复位,粘性不会)。"""
    c1 = _auto_merge_pair(db, 1)
    unalign_candidate(db, c1, actor="admin:9")  # 检出 1 笔误合 → 熔断
    assert auto_breaker_status(db)["tripped"] is True
    for i in range(12):  # 一打新的干净 auto 合(模拟在途轮次喂稀释)
        _auto_merge_pair(db, 100 + i)
    assert auto_breaker_status(db)["tripped"] is True  # 仍熔断:粘性,不被稀释


def test_breaker_reset_restores_and_new_fp_retrips(db):
    """显式人工 reset(审计化)才恢复;reset 后**新**误合再次熔断。"""
    c1 = _auto_merge_pair(db, 1)
    unalign_candidate(db, c1, actor="admin:9")
    assert auto_breaker_status(db)["tripped"] is True

    b = reset_auto_breaker(db, actor="admin:9", note="误合已复核:实体确非重复,已回滚")
    assert b["tripped"] is False  # reset 前的误合已被确认处理

    # 恢复后可正常 auto(C10 放行)
    _doc(db, "dd:ok", origin=DOWN, review_status="reviewed", entity_type="condition")
    _doc(db, "kb:ok", origin=KBASE, review_status="draft", entity_type="condition")
    cid = _cand(db, "dd:ok", "kb:ok")
    ok, reasons = can_auto_approve(db, _get(db, cid), enabled_entity_types=frozenset({"condition"}))
    assert ok is True, reasons

    # reset 后新误合 → 再次熔断
    c2 = _auto_merge_pair(db, 2)
    unalign_candidate(db, c2, actor="admin:9")
    assert auto_breaker_status(db)["tripped"] is True


def test_shadow_pending_list_not_buried_by_pagination(db, monkeypatch):
    """对抗回归:pending 项不被页内过滤埋没 —— 专用查询全量过滤,total 不虚报。"""
    import app.services.kb_reconciliation_judge as m
    from app.services.kb_reconciliation import list_shadow_pending

    monkeypatch.setattr(m, "_SHADOW_AUDIT_EVERY", 1)
    _doc(db, "dd:sp", origin=DOWN, review_status="reviewed", entity_type="condition", title="dup埋没")
    _doc(db, "kb:sp", origin=KBASE, review_status="draft", entity_type="condition", title="dup埋没x")
    _cand(db, "dd:sp", "kb:sp", relation_tag=None, score=0.0)
    run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}),
                       classifier=_fake_classifier)
    # 再塞一堆高分 approved 干扰项(会把 pending 挤出旧实现的第一页)
    for i in range(5):
        _doc(db, f"dd:n{i}", origin=DOWN, review_status="reviewed", entity_type="condition", title=f"噪声{i}")
        _doc(db, f"kb:n{i}", origin=KBASE, review_status="draft", entity_type="condition", title=f"噪声{i}x")
        cid = _cand(db, f"dd:n{i}", f"kb:n{i}", score=0.999)
        merge_candidate(db, cid, actor="admin:1")  # 人工合,无 shadow 标

    res = list_shadow_pending(db, limit=2, offset=0)
    assert res["total"] == 1  # total = 真 pending 数,不看页
    assert len(res["candidates"]) == 1
    assert res["candidates"][0]["shadow_audit"]["status"] == "pending"
