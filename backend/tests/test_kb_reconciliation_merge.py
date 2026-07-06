"""KB Phase-B P4:人工 merge + unalign(首个 serving mutation)。

不变量:additive(loser 归档不删)· count 恒定 · conflict/prescriptive/无锚硬拒 ·
license fail-closed 最严(永不放宽)· unalign 字节往返可逆 · serving 门随 loser 归档收紧。
"""
import pytest

from app.models.system_knowledge import KBDocument, KBEdge, KBReconciliationCandidate
from app.services.kb_reconciliation_merge import can_merge, merge_candidate, unalign_candidate

DOWN = "down-dedao-llm-wiki"
KBASE = "dedao-kbase-export"


def _doc(db, doc_id, *, doc_type="entity", entity_type="condition", entity_id=None,
         title="幽门螺杆菌", origin=DOWN, review_status="reviewed", license_scope=None,
         aliases=None, is_archived=False, content_hash=None):
    meta = {"origin": origin, "review_status": review_status}
    if license_scope is not None:
        meta["license_scope"] = license_scope
    if aliases is not None:
        meta["aliases"] = aliases
    db.add(KBDocument(doc_id=doc_id, doc_type=doc_type, entity_type=entity_type,
                      entity_id=entity_id, title=title, content_hash=content_hash,
                      is_archived=is_archived, metadata_json=meta))
    db.commit()


def _edge(db, src, dst, relation="has_claim"):
    db.add(KBEdge(src_doc_id=src, dst_doc_id=dst, relation=relation))
    db.commit()


def _cand(db, left, right, *, kind="entity_align", relation_tag=None, status="open"):
    c = KBReconciliationCandidate(kind=kind, left_doc_id=left, right_doc_id=right,
                                  relation_tag=relation_tag, status=status, signals={})
    db.add(c)
    db.commit()
    return c.id


def _serving(db, doc_id):
    from app.services.system_knowledge_service import _serving_document_filters
    return (db.query(KBDocument)
            .filter(KBDocument.doc_id == doc_id, *_serving_document_filters()).first())


def test_merge_folds_loser_into_canonical_additive(db):
    _doc(db, "dd:hp", origin=DOWN, review_status="reviewed", aliases=["幽门螺杆菌"])
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", title="Hp感染", aliases=["Hp", "pylori"])
    cid = _cand(db, "dd:hp", "kb:hp")
    res = merge_candidate(db, cid, actor="admin:1")
    assert res["canonical"] == "dd:hp" and res["folded"] == "kb:hp"

    db.expire_all()
    loser = db.query(KBDocument).filter(KBDocument.doc_id == "kb:hp").first()
    canon = db.query(KBDocument).filter(KBDocument.doc_id == "dd:hp").first()
    assert loser.is_archived is True
    assert loser.metadata_json["merged_into"] == "dd:hp"
    assert loser.metadata_json["review_status"] == "archived"
    # canonical:别名并入,review_status 不动
    assert canon.metadata_json["review_status"] == "reviewed"
    assert "Hp" in canon.metadata_json["aliases"] and "幽门螺杆菌" in canon.metadata_json["aliases"]
    assert canon.metadata_json["provenance_lineage"][0]["folded_doc_id"] == "kb:hp"
    # serving 门:loser 掉出、canonical 仍在
    assert _serving(db, "kb:hp") is None
    assert _serving(db, "dd:hp") is not None
    # candidate approved
    c = db.query(KBReconciliationCandidate).filter_by(id=cid).first()
    assert c.status == "approved"


def test_merge_count_invariant(db):
    _doc(db, "dd:hp", origin=DOWN)
    _doc(db, "kb:hp", origin=KBASE, review_status="draft")
    before = db.query(KBDocument).count()
    merge_candidate(db, _cand(db, "dd:hp", "kb:hp"), actor="admin:1")
    db.expire_all()
    assert db.query(KBDocument).count() == before  # 归档不删 → 总数恒定


def test_merge_repoints_edges_keeps_old(db):
    _doc(db, "dd:hp", origin=DOWN)
    _doc(db, "kb:hp", origin=KBASE, review_status="draft")
    _doc(db, "c1", doc_type="claim", origin=KBASE, review_status="draft", title="claim1")
    _edge(db, "c1", "kb:hp", relation="has_claim")  # 指向 loser 的边
    edges_before = db.query(KBEdge).count()
    merge_candidate(db, _cand(db, "dd:hp", "kb:hp"), actor="admin:1")
    db.expire_all()
    # 新边(c1 → dd:hp)增,旧边(c1 → kb:hp)留 + superseded 标记
    assert db.query(KBEdge).count() == edges_before + 1
    old = db.query(KBEdge).filter(KBEdge.dst_doc_id == "kb:hp").first()
    assert old.metadata_json.get("superseded_by_align") is not None
    new = db.query(KBEdge).filter(KBEdge.dst_doc_id == "dd:hp", KBEdge.src_doc_id == "c1").first()
    assert new is not None


def test_unalign_byte_roundtrip(db):
    _doc(db, "dd:hp", origin=DOWN, aliases=["幽门螺杆菌"], license_scope="licensed_transformed_content")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", title="Hp", aliases=["Hp"])
    _doc(db, "c1", doc_type="claim", origin=KBASE, review_status="draft", title="claim1")
    _edge(db, "c1", "kb:hp")
    db.expire_all()
    canon_before = dict(db.query(KBDocument).filter_by(doc_id="dd:hp").first().metadata_json)
    loser_before = dict(db.query(KBDocument).filter_by(doc_id="kb:hp").first().metadata_json)
    loser_archived_before = db.query(KBDocument).filter_by(doc_id="kb:hp").first().is_archived
    edges_before = db.query(KBEdge).count()

    cid = _cand(db, "dd:hp", "kb:hp")
    merge_candidate(db, cid, actor="admin:1")
    unalign_candidate(db, cid, actor="admin:1")

    db.expire_all()
    canon = db.query(KBDocument).filter_by(doc_id="dd:hp").first()
    loser = db.query(KBDocument).filter_by(doc_id="kb:hp").first()
    assert dict(canon.metadata_json) == canon_before  # 字节还原
    assert dict(loser.metadata_json) == loser_before
    assert loser.is_archived == loser_archived_before
    assert db.query(KBEdge).count() == edges_before  # 新边删、旧边留
    old = db.query(KBEdge).filter(KBEdge.dst_doc_id == "kb:hp").first()
    assert "superseded_by_align" not in (old.metadata_json or {})  # 标记摘掉
    c = db.query(KBReconciliationCandidate).filter_by(id=cid).first()
    assert c.status == "open"  # 回到可再审


def test_conflict_hard_rejected(db):
    _doc(db, "dd:hp", origin=DOWN)
    _doc(db, "kb:hp", origin=KBASE, review_status="draft")
    cid = _cand(db, "dd:hp", "kb:hp", relation_tag="conflict")
    ok, reason, _ = can_merge(db, db.query(KBReconciliationCandidate).filter_by(id=cid).first())
    assert ok is False and "conflict" in reason
    with pytest.raises(ValueError):
        merge_candidate(db, cid, actor="admin:1")


def test_prescriptive_hard_rejected(db):
    _doc(db, "dd:med", origin=DOWN, entity_type="medication", title="二甲双胍")
    _doc(db, "kb:med", origin=KBASE, review_status="draft", entity_type="medication", title="metformin")
    cid = _cand(db, "dd:med", "kb:med")
    with pytest.raises(ValueError):
        merge_candidate(db, cid, actor="admin:1")


def test_no_reviewed_anchor_rejected(db):
    # 两个 draft(无 reviewed down-dedao 锚)→ 硬拒
    _doc(db, "kb:a", origin=KBASE, review_status="draft", title="A")
    _doc(db, "kb:b", origin=KBASE, review_status="draft", title="B")
    cid = _cand(db, "kb:a", "kb:b")
    with pytest.raises(ValueError):
        merge_candidate(db, cid, actor="admin:1")


def test_license_fail_closed_never_widens(db):
    # canonical=licensed(rank2), loser=internal(rank3 更严) → canonical 收严到 internal
    _doc(db, "dd:hp", origin=DOWN, license_scope="licensed_transformed_content")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", license_scope="internal_transformed_claims")
    merge_candidate(db, _cand(db, "dd:hp", "kb:hp"), actor="admin:1")
    db.expire_all()
    canon = db.query(KBDocument).filter_by(doc_id="dd:hp").first()
    assert canon.metadata_json["license_scope"] == "internal_transformed_claims"  # 收严


def test_license_does_not_loosen_when_canonical_stricter(db):
    # canonical=internal(更严), loser=licensed → canonical 保持 internal(不被放宽)
    _doc(db, "dd:hp", origin=DOWN, license_scope="internal_transformed_claims")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", license_scope="licensed_transformed_content")
    merge_candidate(db, _cand(db, "dd:hp", "kb:hp"), actor="admin:1")
    db.expire_all()
    canon = db.query(KBDocument).filter_by(doc_id="dd:hp").first()
    assert canon.metadata_json["license_scope"] == "internal_transformed_claims"


def test_cannot_merge_already_approved(db):
    _doc(db, "dd:hp", origin=DOWN)
    _doc(db, "kb:hp", origin=KBASE, review_status="draft")
    cid = _cand(db, "dd:hp", "kb:hp")
    merge_candidate(db, cid, actor="admin:1")
    with pytest.raises(ValueError):  # status=approved → 不可再合
        merge_candidate(db, cid, actor="admin:1")


# ── 对抗回归 #1:stacked merge 的 LIFO 可逆(绝对快照只对最晚一次正确)──

def test_stacked_merge_lifo_unalign(db):
    """两个 loser 折入同一 canonical:必须 LIFO 撤销,否则早的 unalign 会覆盖晚的 fold(orphan)。"""
    _doc(db, "dd:hp", origin=DOWN, aliases=["幽门螺杆菌"])
    _doc(db, "kb:a", origin=KBASE, review_status="draft", title="A", aliases=["aliasA"])
    _doc(db, "kb:b", origin=KBASE, review_status="draft", title="B", aliases=["aliasB"])
    db.expire_all()
    canon_original = dict(db.query(KBDocument).filter_by(doc_id="dd:hp").first().metadata_json)

    ca = _cand(db, "dd:hp", "kb:a")
    cb = _cand(db, "dd:hp", "kb:b")
    merge_candidate(db, ca, actor="admin:1")
    merge_candidate(db, cb, actor="admin:1")

    # 撤销早的(A)必须被 LIFO 拒
    with pytest.raises(ValueError, match="LIFO"):
        unalign_candidate(db, ca, actor="admin:1")

    # 先撤晚的(B)→ canonical 回到 post-A(A 的别名还在)
    unalign_candidate(db, cb, actor="admin:1")
    db.expire_all()
    canon = db.query(KBDocument).filter_by(doc_id="dd:hp").first()
    assert "aliasA" in canon.metadata_json["aliases"]  # A 的 fold 未被 B 的撤销破坏
    assert "aliasB" not in canon.metadata_json["aliases"]

    # 再撤 A → canonical 字节回到最初
    unalign_candidate(db, ca, actor="admin:1")
    db.expire_all()
    canon = db.query(KBDocument).filter_by(doc_id="dd:hp").first()
    assert dict(canon.metadata_json) == canon_original


def test_null_edge_meta_byte_roundtrip(db):
    """旧边 metadata_json 原为 NULL → merge 打标 → unalign 必还原为 NULL(不漂成 {})。"""
    from app.models.system_knowledge import KBEdge

    _doc(db, "dd:hp", origin=DOWN)
    _doc(db, "kb:hp", origin=KBASE, review_status="draft")
    _doc(db, "c1", doc_type="claim", origin=KBASE, review_status="draft", title="c1")
    db.add(KBEdge(src_doc_id="c1", dst_doc_id="kb:hp", relation="has_claim", metadata_json=None))
    db.commit()
    cid = _cand(db, "dd:hp", "kb:hp")
    merge_candidate(db, cid, actor="admin:1")
    unalign_candidate(db, cid, actor="admin:1")
    db.expire_all()
    e = db.query(KBEdge).filter(KBEdge.dst_doc_id == "kb:hp", KBEdge.src_doc_id == "c1").first()
    assert e.metadata_json is None  # 字节还原 NULL


# ── 对抗回归 #2:处方内容(药名/剂量)在 claim/article/None entity_type 下也硬拒(I4)──

@pytest.mark.parametrize("etype,title", [
    ("claim", "华法林维持剂量每日3mg"),
    ("claim", "warfarin maintenance dose"),
    ("article", "二甲双胍缓释片用法用量"),
    ("protocol", "肌酸负荷 5 g once daily"),
    (None, "metformin 500 mg titration"),
])
def test_prescriptive_content_hard_rejected_regardless_of_entity_type(db, etype, title):
    _doc(db, "dd:x", origin=DOWN, entity_type=etype, doc_type="claim", title=title)
    _doc(db, "kb:x", origin=KBASE, review_status="draft", entity_type=etype, doc_type="claim", title=title + " v2")
    cid = _cand(db, "dd:x", "kb:x", kind="claim_overlap")
    with pytest.raises(ValueError):  # 药名/剂量内容 → 硬拒走人工
        merge_candidate(db, cid, actor="admin:1")


def test_nonprescriptive_claim_still_merges(db):
    """非处方 claim(无药名/剂量)仍可正常合并 —— 内容 gate 不误伤良性 claim。"""
    _doc(db, "dd:sleep", origin=DOWN, entity_type="concept", doc_type="claim",
         title="固定就寝时间有助睡眠稳定")
    _doc(db, "kb:sleep", origin=KBASE, review_status="draft", entity_type="concept", doc_type="claim",
         title="规律作息改善睡眠")
    cid = _cand(db, "dd:sleep", "kb:sleep", kind="claim_overlap")
    res = merge_candidate(db, cid, actor="admin:1")  # 不抛
    assert res["merged"] is True


# ── 对抗回归 #3:扩词后,无剂量的**未列名药**名 claim(generic entity_type)也硬拒(I4 收窄残余)──
# 旧 gate 只认 ~25 命名高危药 + 剂量数字 → 布洛芬/氨氯地平/阿莫西林/左甲状腺素/lisinopril
# 这类**无剂量、未列名**药名会漏合。单一事实源词库(drug_lexicon)接入后必须硬拒。
# 用**非处方** entity_type(condition),迫使**内容层药名 gate**(而非 entity_type 地板)
# 成为唯一拒绝点 —— 证明扩词真在起作用,而非 entity_type 兜底。

@pytest.mark.parametrize("drug_title", [
    "布洛芬", "氨氯地平", "阿莫西林", "左甲状腺素", "他克莫司", "别嘌醇",
    "lisinopril", "amlodipine", "ibuprofen", "levothyroxine",
])
def test_named_drug_without_dose_hard_rejected(db, drug_title):
    _doc(db, "dd:x", origin=DOWN, entity_type="condition", doc_type="claim",
         title=f"{drug_title}的作用机制")
    _doc(db, "kb:x", origin=KBASE, review_status="draft", entity_type="condition",
         doc_type="claim", title=f"{drug_title}用途说明")
    cid = _cand(db, "dd:x", "kb:x", kind="claim_overlap")
    cobj = db.query(KBReconciliationCandidate).filter_by(id=cid).first()
    ok, reason, _ = can_merge(db, cobj)
    assert ok is False and "处方" in reason  # 药名内容 gate 拒(非 entity_type / 无锚)
    with pytest.raises(ValueError):
        merge_candidate(db, cid, actor="admin:1")


# ── 对抗回归 #4:扩词**不**过度收严 —— 食物/草药名、撞常用词的短子串仍可合(收窄误伤)──
# 保持 over-refuse 偏向 ≠ 把「西柚/大蒜/银杏/地铁通勤」这类良性科普 claim 也拒掉。
# 食物/草药类刻意不入 gate;歧义短子串(铁→地铁、iron→environment、pril→April)去了歧义。

@pytest.mark.parametrize("t1,t2", [
    ("西柚富含维生素C", "葡萄柚的营养价值"),      # 食物(grapefruit 排除类)
    ("大蒜的抗菌作用", "大蒜素与日常饮食"),        # 食物/草药(garlic 排除类)
    ("银杏叶的传统用途", "银杏与记忆的科普"),      # 草药(ginkgo 排除类)
    ("益生菌与肠道菌群", "酸奶里的益生菌"),        # 补剂但非处方(probiotic 排除类)
    ("地铁通勤与久坐问题", "通勤方式影响活动量"),  # 铁 陷阱(地铁)
    ("环境噪音影响睡眠", "the ambient environment"),  # iron⊂environ / 英文陷阱
])
def test_expanded_gate_does_not_over_refuse_benign(db, t1, t2):
    _doc(db, "dd:b", origin=DOWN, entity_type="concept", doc_type="claim", title=t1)
    _doc(db, "kb:b", origin=KBASE, review_status="draft", entity_type="concept",
         doc_type="claim", title=t2)
    res = merge_candidate(db, _cand(db, "dd:b", "kb:b", kind="claim_overlap"), actor="admin:1")
    assert res["merged"] is True  # 良性 claim 未被扩词误伤
