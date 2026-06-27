"""GERD / LPR / 消化性溃疡知识库接入测试。

验证 #3「胃病 × 慢性鼻炎打通」:
1. owner-reviewed GERD/LPR claim 已进 v2 种子并可导入 serving DB。
2. EvidenceResolver 把反流 claim 绑到 RhinitisSpecialist 真实产出的 reflux_hypothesis finding
   (即 _specialist_domain_keywords rhinitis 分支 + applies_when 守卫真正接通)。
3. KnowledgeLibrarian 能就反流/胃病问题检索出系统 KB claim。
4. 边界守门:新 claim 不含处方化剂量;HP 状态分流不无条件根除(尊重锚点用户 Hp 阴性事实)。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

NEW_CLAIM_IDS = {
    "claim:c_peptic_ulcer_hp_status_triage",
    "claim:c_hp_positive_eradication_physician_boundary",
    "claim:c_lpr_upper_airway_rhinitis_overlap",
    "claim:c_long_term_acid_suppression_monitoring",
    "claim:c_gerd_lifestyle_modifiable_factors",
    "claim:c_reflux_gastric_alarm_features",
}
LPR_CLAIM = "claim:c_lpr_upper_airway_rhinitis_overlap"
PR2_CONTRAINDICATION_IDS = {
    "contraindication:reflux_gastric_alarm_features_escalation",
    "contraindication:rhinitis_reflux_overlap_no_self_escalation",
}
PR2_EVAL_CASE_IDS = {
    "eval:gerd_alarm_features_escalate",
    "eval:lpr_rhinitis_overlap_supported",
}
HP_POSITIVE_CLAIM = "claim:c_hp_positive_eradication_physician_boundary"
HP_POSITIVE_CONTRAINDICATION = "contraindication:hp_positive_no_self_eradication_regimen"
HP_POSITIVE_EVAL = "eval:hp_positive_eradication_boundary"
HP_UNKNOWN_ANTIBIOTIC_CLAIM = "claim:c_hp_unknown_no_self_antibiotic_boundary"
HP_UNKNOWN_ANTIBIOTIC_CONTRAINDICATION = (
    "contraindication:hp_unknown_no_empiric_antibiotic_or_test_skip"
)
HP_UNKNOWN_ANTIBIOTIC_EVAL = "eval:hp_unknown_antibiotic_boundary"


def _new_claims() -> list[dict]:
    rows = []
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("doc_id") in NEW_CLAIM_IDS:
            rows.append(row)
    return rows


# ── 1. 种子可导入 ───────────────────────────────────────────────

def test_gerd_lpr_claims_imported(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:gerd_lpr")
    found = {
        d.doc_id
        for d in db.query(KBDocument).filter(KBDocument.doc_id.in_(NEW_CLAIM_IDS)).all()
    }
    assert found == NEW_CLAIM_IDS


def test_reflux_contraindications_and_eval_cases_imported(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:gerd_lpr_pr2")
    assert counts["skipped_documents"] == 0

    docs = db.query(KBDocument).filter(
        KBDocument.doc_id.in_(PR2_CONTRAINDICATION_IDS | PR2_EVAL_CASE_IDS)
    ).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == PR2_CONTRAINDICATION_IDS | PR2_EVAL_CASE_IDS
    for doc_id in PR2_CONTRAINDICATION_IDS:
        doc = by_id[doc_id]
        assert doc.doc_type == "contraindication"
        assert (doc.metadata_json or {}).get("review_status") == "reviewed"
        assert (doc.metadata_json or {}).get("forbidden_when"), doc_id
        assert (doc.metadata_json or {}).get("fallback"), doc_id
    for doc_id in PR2_EVAL_CASE_IDS:
        doc = by_id[doc_id]
        assert doc.doc_type == "eval_case"
        assert (doc.metadata_json or {}).get("case_id"), doc_id
        assert (doc.metadata_json or {}).get("expected"), doc_id


def test_hp_positive_eradication_claim_contraindication_and_eval_import(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        reindex_knowledge_documents,
        search_knowledge,
    )

    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:hp_positive_gate")
    assert counts["skipped_documents"] == 0

    doc_ids = {HP_POSITIVE_CLAIM, HP_POSITIVE_CONTRAINDICATION, HP_POSITIVE_EVAL}
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    assert by_id[HP_POSITIVE_CLAIM].doc_type == "claim"
    assert by_id[HP_POSITIVE_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[HP_POSITIVE_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id

    positive = lookup_for_twin(
        db,
        {"conditions": {"active": ["胃溃疡"], "hp_status": "positive"}},
    )
    positive_claim_ids = {claim.get("doc_id") for claim in positive.get("claims") or []}
    assert HP_POSITIVE_CLAIM in positive_claim_ids

    negative = lookup_for_twin(
        db,
        {"conditions": {"active": ["胃溃疡"], "hp_status": "negative"}},
    )
    negative_claim_ids = {claim.get("doc_id") for claim in negative.get("claims") or []}
    assert HP_POSITIVE_CLAIM not in negative_claim_ids

    reindex_knowledge_documents(db, actor="test:hp_positive_gate")
    search = search_knowledge(
        db,
        "幽门螺杆菌 阳性 消化性溃疡 根除 复查 呼气试验 医生",
        limit=10,
        doc_type="claim",
    )
    search_ids = {
        (item.get("document") or {}).get("doc_id")
        for item in (search.get("results") or [])
    }
    assert HP_POSITIVE_CLAIM in search_ids

    report = run_system_kb_eval_cases(db, case_ids={HP_POSITIVE_EVAL})
    assert report["total"] == 1
    assert report["failed"] == 0


def test_hp_unknown_antibiotic_boundary_requires_unknown_status_and_self_treatment_context(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases
    from app.services.system_knowledge_service import lookup_for_twin

    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:hp_unknown_antibiotic_gate")
    assert counts["skipped_documents"] == 0

    doc_ids = {
        HP_UNKNOWN_ANTIBIOTIC_CLAIM,
        HP_UNKNOWN_ANTIBIOTIC_CONTRAINDICATION,
        HP_UNKNOWN_ANTIBIOTIC_EVAL,
    }
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    assert by_id[HP_UNKNOWN_ANTIBIOTIC_CLAIM].doc_type == "claim"
    assert by_id[HP_UNKNOWN_ANTIBIOTIC_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[HP_UNKNOWN_ANTIBIOTIC_EVAL].doc_type == "eval_case"

    risky = lookup_for_twin(
        db,
        {"conditions": {"active": ["胃痛", "幽门螺杆菌状态不明", "想自己吃抗生素"]}},
    )
    risky_ids = {claim.get("doc_id") for claim in risky.get("claims") or []}
    assert HP_UNKNOWN_ANTIBIOTIC_CLAIM in risky_ids

    no_self_treatment = lookup_for_twin(db, {"conditions": {"active": ["胃痛"]}})
    no_self_treatment_ids = {
        claim.get("doc_id") for claim in no_self_treatment.get("claims") or []
    }
    assert HP_UNKNOWN_ANTIBIOTIC_CLAIM not in no_self_treatment_ids

    report = run_system_kb_eval_cases(db, case_ids={HP_UNKNOWN_ANTIBIOTIC_EVAL})
    assert report["total"] == 1
    assert report["failed"] == 0


# ── 2. 反流 claim 绑到鼻炎 specialist 真实 finding ────────────────

def _reflux_health_twin():
    """锚点用户形态:伏诺拉生 + 胃溃疡(Hp 阴性) + 鼻症状。"""
    from app.twin.schema import (
        AcuteHealthState,
        BehavioralState,
        ChronicConditionState,
        HealthTwin,
        MedicationState,
        ProblemRedLine,
        TwinMeta,
    )

    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.behavioral = BehavioralState(sneeze_count_today=12, nasal_wash_count_today=3)
    t.medication = MedicationState(active_meds=[{"name": "伏诺拉生", "kind": "medication"}])
    t.chronic = ChronicConditionState(
        rhinitis_today={"active": True}, active_conditions=["反流", "鼻炎"]
    )
    t.acute = AcuteHealthState(
        problem_red_lines=[
            ProblemRedLine(
                problem_name="胃溃疡(Hp 阴性,胃窦后壁)",
                condition="黑便/呕血",
                action="立即就医",
                risk_level="P1",
            )
        ]
    )
    return t


def test_reflux_claim_attaches_to_rhinitis_finding(db):
    from app.agents.chronic_specialists import RhinitisSpecialist
    from app.services.system_knowledge_service import (
        attach_system_knowledge_evidence,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:gerd_lpr")

    twin = _reflux_health_twin()
    finding = RhinitisSpecialist().run(twin, {})
    # 前提:specialist 确实产出 reflux_hypothesis(否则下面绑定无意义)
    assert any(f.get("type") == "reflux_hypothesis" for f in finding.findings)

    payload = system_kb_twin_payload_from_health_twin(twin)
    stats = attach_system_knowledge_evidence(db, payload, [finding])

    assert stats["findings_updated"] >= 1
    assert LPR_CLAIM in (finding.evidence_refs or []), finding.evidence_refs


def test_non_reflux_rhinitis_does_not_attach_gastro_claim(db):
    """纯过敏性鼻炎(无抑酸药/无反流条件)不应被贴上反流 claim。"""
    from datetime import datetime as _dt

    from app.agents.chronic_specialists import RhinitisSpecialist
    from app.services.system_knowledge_service import (
        attach_system_knowledge_evidence,
        system_kb_twin_payload_from_health_twin,
    )
    from app.twin.schema import (
        BehavioralState,
        ChronicConditionState,
        HealthTwin,
        TwinMeta,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:gerd_lpr")

    t = HealthTwin(meta=TwinMeta(user_id=2, generated_at=_dt.utcnow()))
    t.behavioral = BehavioralState(sneeze_count_today=15, nasal_wash_count_today=2)
    t.chronic = ChronicConditionState(
        rhinitis_today={"active": True}, active_conditions=["过敏性鼻炎"]
    )

    finding = RhinitisSpecialist().run(t, {})
    assert not any(f.get("type") == "reflux_hypothesis" for f in finding.findings)

    payload = system_kb_twin_payload_from_health_twin(t)
    attach_system_knowledge_evidence(db, payload, [finding])
    assert LPR_CLAIM not in (finding.evidence_refs or [])


# ── 3. librarian 检索 ──────────────────────────────────────────

def test_gerd_lpr_claims_are_retrievable(db):
    """服务层检索:反流/胃病 query 能在 claim 结果里召回新 GERD/LPR claim。

    (用 doc_type='claim' 直接验证可检索性,避免新 entity 在混合 top-N 里挤占名额的
    排序噪声——librarian 端到端已由 test_knowledge_librarian* 覆盖。)
    """
    from app.services.system_knowledge_service import (
        reindex_knowledge_documents,
        search_knowledge,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:gerd_lpr")
    reindex_knowledge_documents(db, actor="test:gerd_lpr")

    result = search_knowledge(db, "咽喉反流 胃食管反流 鼻炎样症状", limit=10, doc_type="claim")
    ids = {
        (item.get("document") or {}).get("doc_id")
        for item in (result.get("results") or [])
    }
    assert ids & NEW_CLAIM_IDS, ids


def test_system_kb_eval_runner_covers_reflux_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:gerd_lpr_eval")

    report = run_system_kb_eval_cases(db, case_ids=PR2_EVAL_CASE_IDS)

    assert report["total"] == len(PR2_EVAL_CASE_IDS)
    assert report["failed"] == 0
    assert {case["case_id"] for case in report["cases"]} == PR2_EVAL_CASE_IDS


# ── 4. 边界守门(无 DB) ─────────────────────────────────────────

def test_new_claims_carry_boundary_and_no_prescription():
    claims = _new_claims()
    assert len(claims) == len(NEW_CLAIM_IDS)
    for c in claims:
        blob = f"{c.get('title','')} {c.get('summary','')} {c.get('body','')}"
        meta = c.get("metadata") or {}
        # 边界标注必须到达 LLM 可见字段
        assert meta.get("claim_boundary"), c["doc_id"]
        assert "边界" in c.get("body", ""), c["doc_id"]
        # 必须有明确的医生/就医兜底(deferral),而非自行处置
        assert any(tok in blob for tok in ("医生", "就医", "医嘱", "消化科")), c["doc_id"]
        # R4:禁真正的处方化剂量 / 命令式停减药 / 确诊措辞。
        # 注意:"不应自行停药"是正确的安全警示语,不算越界——故只禁命令式/数值剂量。
        for banned in [
            "mg", "毫克", "确诊", "诊断为", "你患有",
            "建议停药", "请停药", "立即停药", "建议减量", "改为每", "每日服用", "每天服用",
        ]:
            assert banned not in blob, f"{c['doc_id']} 越界: {banned}"


def test_hp_triage_claim_is_status_gated_not_unconditional_eradication():
    """HP 状态分流 claim 必须把根除限定在阳性,绝不无条件推根除四联(尊重锚点用户 Hp 阴性)。"""
    claims = {c["doc_id"]: c for c in _new_claims()}
    hp = claims["claim:c_peptic_ulcer_hp_status_triage"]
    blob = f"{hp.get('summary','')} {hp.get('body','')}"
    assert "阳性" in blob and "阴性" in blob
    # 不能出现无条件的根除处方语
    assert "四联" not in blob
    assert "根除" in blob  # 提到根除概念,但限定在阳性语境


def test_hp_positive_claim_keeps_eradication_in_physician_boundary():
    claims = {c["doc_id"]: c for c in _new_claims()}
    hp = claims[HP_POSITIVE_CLAIM]
    blob = f"{hp.get('title','')} {hp.get('summary','')} {hp.get('body','')}"
    meta = hp.get("metadata") or {}
    assert meta.get("claim_boundary")
    assert "阳性" in blob
    assert "复查" in blob
    assert "呼气试验" in blob or "粪便抗原" in blob
    assert any(token in blob for token in ("医生", "医嘱", "消化科"))
    assert "根除" in blob
    for banned in [
        "四联",
        "阿莫西林",
        "克拉霉素",
        "甲硝唑",
        "mg",
        "毫克",
        "每日服用",
        "每天服用",
        "自行根除",
        "直接根除",
        "自行用药",
    ]:
        assert banned not in blob, f"{HP_POSITIVE_CLAIM} 越界: {banned}"
