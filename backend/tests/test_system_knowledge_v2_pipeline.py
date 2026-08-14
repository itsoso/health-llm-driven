from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
import json

from app.models.system_knowledge import KBDocument, KBEdge
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_pipeline import (
    classify_health_source,
    find_private_source_violations,
    scan_health_sources,
)
from app.services.system_knowledge_service import lookup_for_twin
from app.services.system_knowledge_service import (
    attach_system_knowledge_evidence,
    evaluate_condition,
    format_system_knowledge_for_prompt,
    format_system_knowledge_result_for_prompt,
    system_kb_twin_payload_from_health_twin,
    _select_claim_refs_for_specialist,
)
from app.orchestrator.schema import SpecialistFinding


def test_lookup_for_twin_matches_boolean_goal_conditions(db):
    db.add(
        KBDocument(
            doc_id="claim:c_weight_waist_tracking",
            doc_type="claim",
            entity_type="intervention",
            entity_id="weight-waist-tracking",
            title="体重和腰围晨起记录",
            summary="减重和代谢风险管理应跟踪体重与腰围趋势。",
            confidence=0.72,
            evidence_level="B",
            applies_when=["twin.goals.weight_loss.active == true"],
            sources=["dedao:fengxue-weight-loss"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()

    result = lookup_for_twin(db, {"goals": {"weight_loss": {"active": True}}})

    assert [claim["doc_id"] for claim in result["claims"]] == ["claim:c_weight_waist_tracking"]
    assert result["claims"][0]["matched_conditions"] == [
        "twin.goals.weight_loss.active == true"
    ]


def test_evaluate_condition_supports_list_membership_for_medications():
    twin = {
        "medications": [
            {"name": "阿司匹林", "generic_name": "aspirin"},
            "clopidogrel",
        ]
    }

    assert evaluate_condition("twin.medications has 'clopidogrel'", twin) is True
    assert evaluate_condition("twin.medications has any of ['omeprazole', 'aspirin']", twin) is True
    assert evaluate_condition("twin.medications has 'warfarin'", twin) is False


def test_lookup_for_twin_matches_gene_drug_conditions_with_medication_lists(db):
    db.add(
        KBDocument(
            doc_id="claim:c_cyp2c19_clopidogrel_boundary",
            doc_type="claim",
            entity_type="gene",
            entity_id="CYP2C19",
            title="CYP2C19 PM 与氯吡格雷无效边界",
            summary="CYP2C19 PM 使用氯吡格雷时需要医生核对替代方案。",
            confidence=0.9,
            evidence_level="A",
            applies_when=[
                "twin.genetics.CYP2C19_phenotype == 'poor'",
                "twin.medications has 'clopidogrel'",
            ],
            sources=["cpic:guideline-cyp2c19-clopidogrel"],
            last_confirmed=datetime(2026, 5, 18, tzinfo=UTC),
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()

    result = lookup_for_twin(
        db,
        {
            "genetics": {"CYP2C19_phenotype": "poor"},
            "medications": [{"name": "波立维", "generic_name": "clopidogrel"}],
        },
    )

    assert [claim["doc_id"] for claim in result["claims"]] == [
        "claim:c_cyp2c19_clopidogrel_boundary"
    ]
    assert "twin.medications has 'clopidogrel'" in result["claims"][0]["matched_conditions"]


def test_lookup_for_twin_does_not_match_gene_drug_claim_without_medication_context(db):
    db.add(
        KBDocument(
            doc_id="claim:c_cyp2c19_clopidogrel_boundary",
            doc_type="claim",
            entity_type="gene",
            entity_id="CYP2C19",
            title="CYP2C19 PM 与氯吡格雷无效边界",
            summary="CYP2C19 PM 使用氯吡格雷时需要医生核对替代方案。",
            confidence=0.9,
            evidence_level="A",
            applies_when=[
                "twin.genetics.CYP2C19_phenotype == 'poor'",
                "twin.medications has 'clopidogrel'",
            ],
            sources=["cpic:guideline-cyp2c19-clopidogrel"],
            last_confirmed=datetime(2026, 5, 18, tzinfo=UTC),
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()

    result = lookup_for_twin(
        db,
        {
            "genetics": {"CYP2C19_phenotype": "poor"},
            "medications": [],
        },
    )

    assert result["claims"] == []


def test_system_kb_twin_payload_maps_pharmacogenomic_variants():
    class Obj:
        pass

    twin = Obj()
    twin.labs = Obj()
    twin.physiological = Obj()
    twin.behavioral = Obj()
    twin.chronic = Obj()
    twin.medication = Obj()
    twin.supplement = Obj()
    twin.goals = Obj()
    twin.goals.active_goals = []
    twin.medication.active_meds = []
    twin.supplement.active_supplements = []
    twin.physiological.training_readiness_score = 92
    twin.physiological.training_readiness_level = "high"
    twin.behavioral.acute_chronic_ratio = 0.72
    twin.behavioral.water_progress_pct = 25
    twin.behavioral.diet_protein_g_today = 80
    twin.chronic.active_conditions = ["allergic rhinitis"]
    twin.chronic.rhinitis_today = {"sneeze_count": 1}
    twin.genetic = Obj()
    twin.genetic.risk_variants = []
    twin.genetic.protective_variants = []
    twin.genetic.nutrition_variants = []
    twin.genetic.recovery_variants = []
    twin.genetic.exercise_variants = []
    twin.genetic.cognition_variants = []
    twin.genetic.personality_variants = []
    twin.genetic.sleep_variants = []
    twin.genetic.drug_sensitivity = [
        {
            "gene_name": "CYP2C19",
            "genotype": "*2/*2",
            "result_label": "慢代谢",
            "risk_level": "high",
        },
        {
            "gene_name": "SLCO1B1",
            "genotype": "CT",
            "result_label": "他汀肌病风险轻度增高",
            "risk_level": "medium",
        },
    ]

    payload = system_kb_twin_payload_from_health_twin(twin)
    genetics = payload["genetics"]

    assert genetics["CYP2C19"] == "*2/*2"
    assert genetics["CYP2C19_phenotype"] == "poor"
    assert genetics["SLCO1B1_rs4149056"] == "CT"
    assert payload["wearable"]["training_readiness_score"] == 92
    assert payload["wearable"]["training_readiness_level"] == "high"
    assert payload["behavioral"]["acute_chronic_ratio"] == 0.72
    assert payload["behavioral"]["water_progress_pct"] == 25
    assert payload["behavioral"]["diet_protein_g_today"] == 80
    assert payload["conditions"]["rhinitis"]["active"] is True
    assert payload["conditions"]["active"] == ["allergic rhinitis"]


def test_lookup_for_twin_promotes_contextualized_entity_claims(db):
    db.add_all(
        [
            KBDocument(
                doc_id="entity:biomarker:uric-acid",
                doc_type="entity",
                entity_type="biomarker",
                entity_id="uric-acid",
                title="尿酸",
                summary="尿酸是代谢和肾功能轨迹中的关键指标。",
                confidence=0.78,
                evidence_level="B",
                sources=["dedao:fengxue-gaoniaosuan"],
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="entity:condition:hyperuricemia-risk",
                doc_type="entity",
                entity_type="condition",
                entity_id="hyperuricemia-risk",
                title="高尿酸风险",
                summary="尿酸偏高需要结合饮食、酒精、体重和肾功能解释。",
                confidence=0.76,
                evidence_level="B",
                sources=["dedao:fengxue-gaoniaosuan"],
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="claim:c_uric_acid_hydration_context",
                doc_type="claim",
                entity_type="condition",
                entity_id="hyperuricemia-risk",
                title="尿酸偏高需结合饮水和肾功能复查",
                summary="尿酸偏高时应优先确认饮水、酒精、含糖饮料、体重和肾功能背景。",
                confidence=0.74,
                evidence_level="B",
                applies_when=[],
                sources=["dedao:fengxue-gaoniaosuan"],
                metadata_json={"review_status": "reviewed"},
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            KBEdge(
                src_doc_id="entity:biomarker:uric-acid",
                dst_doc_id="entity:condition:hyperuricemia-risk",
                relation="contextualizes",
                confidence=0.58,
                source_claim_id="claim:c_uric_acid_hydration_context",
            ),
            KBEdge(
                src_doc_id="entity:condition:hyperuricemia-risk",
                dst_doc_id="claim:c_uric_acid_hydration_context",
                relation="has_claim",
                confidence=0.84,
                source_claim_id="claim:c_uric_acid_hydration_context",
            ),
        ]
    )
    db.commit()

    result = lookup_for_twin(db, {"labs": {"uric_acid_umol_l": 520}})

    assert [entity["doc_id"] for entity in result["entities"]] == ["entity:biomarker:uric-acid"]
    assert [entity["doc_id"] for entity in result["contextual_entities"]] == [
        "entity:condition:hyperuricemia-risk"
    ]
    assert [claim["doc_id"] for claim in result["claims"]] == [
        "claim:c_uric_acid_hydration_context"
    ]
    assert result["claims"][0]["match_type"] == "graph_context"
    assert result["claims"][0]["matched_context"]["via_entity"] == "entity:condition:hyperuricemia-risk"


def test_scan_health_sources_filters_relevant_courses(tmp_path):
    root = tmp_path / "down-dedao"
    (root / "冯雪·高血糖医学课" / "PDF").mkdir(parents=True)
    (root / "冯雪·高血糖医学课" / "PDF" / "01 - 血糖为什么升高？.pdf").write_text("x")
    (root / "Python量化投资指南" / "PDF").mkdir(parents=True)
    (root / "Python量化投资指南" / "PDF" / "01 - 回测.pdf").write_text("x")

    sources = scan_health_sources(root)

    assert [source.course_name for source in sources] == ["冯雪·高血糖医学课"]
    assert sources[0].domains == ["metabolic_health"]
    assert sources[0].lesson_count == 1
    assert sources[0].source_key == "dedao:fengxue-gaoxuetang-yixueke"


def test_scan_health_sources_excludes_private_material(tmp_path):
    root = tmp_path / "down-dedao"
    (root / "personal" / "user-3").mkdir(parents=True)
    (root / "personal" / "user-3" / "personal-weight-management.md").write_text(
        "体重 血糖 血脂 尿酸 腰围 睡眠 健康 医学 营养",
        encoding="utf-8",
    )
    (root / "私人健康日志" / "notes").mkdir(parents=True)
    (root / "私人健康日志" / "notes" / "01 - 血糖和体重.md").write_text(
        "血糖 体重 腰围 健康 营养",
        encoding="utf-8",
    )
    (root / "冯雪·高血糖医学课" / "PDF").mkdir(parents=True)
    (root / "冯雪·高血糖医学课" / "PDF" / "01 - 血糖为什么升高？.pdf").write_text("x")

    sources = scan_health_sources(root)

    assert [source.course_name for source in sources] == ["冯雪·高血糖医学课"]


def test_find_private_source_violations_reports_private_paths_without_reading_content(tmp_path):
    root = tmp_path / "down-dedao"
    (root / "wiki" / "articles").mkdir(parents=True)
    (root / "wiki" / "articles" / "personal-weight.md").write_text(
        "体重 血糖 腰围",
        encoding="utf-8",
    )
    (root / "personal" / "user-3").mkdir(parents=True)
    (root / "personal" / "user-3" / "health-log.md").write_text(
        "用户私有健康记录",
        encoding="utf-8",
    )
    (root / "冯雪·高血糖医学课" / "MD").mkdir(parents=True)
    (root / "冯雪·高血糖医学课" / "MD" / "01 - 血糖为什么升高？.md").write_text(
        "血糖 体重 腰围 健康 营养",
        encoding="utf-8",
    )

    violations = find_private_source_violations(root)

    assert {violation["reason"] for violation in violations} == {
        "private_name",
        "private_path",
    }
    assert {Path(violation["path"]).name for violation in violations} == {
        "personal-weight.md",
        "health-log.md",
    }


def test_classify_health_source_returns_domain_priority():
    result = classify_health_source("冯雪·高血脂医学课", ["07 - 饮食：怎么吃才能降血脂？.pdf"])

    assert result.is_health is True
    assert result.domains[:2] == ["metabolic_health", "cardiovascular"]
    assert result.priority == 1


def test_import_system_kb_artifacts_is_idempotent(tmp_path, db):
    artifact_dir = tmp_path / "artifacts" / "v2"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "entities.jsonl").write_text(
        '{"doc_id":"entity:condition:metabolic-health","doc_type":"entity",'
        '"entity_type":"condition","entity_id":"metabolic-health","title":"代谢健康",'
        '"summary":"体重、腰围、血糖、血脂和血压的轨迹管理。",'
        '"confidence":0.75,"evidence_level":"B","sources":["system:test"],'
        '"metadata":{"review_status":"reviewed"}}\n'
    )
    (artifact_dir / "claims.jsonl").write_text(
        '{"doc_id":"claim:c_weight_waist_tracking","doc_type":"claim",'
        '"entity_type":"intervention","entity_id":"weight-waist-tracking",'
        '"title":"体重和腰围晨起记录","summary":"减重和代谢风险管理应跟踪体重与腰围趋势。",'
        '"confidence":0.72,"evidence_level":"B",'
        '"applies_when":["twin.goals.weight_loss.active == true"],'
        '"sources":["dedao:fengxue-weight-loss"],"decay_rate":"normal",'
        '"metadata":{"review_status":"reviewed"}}\n'
    )
    (artifact_dir / "relations.jsonl").write_text(
        '{"src_doc_id":"entity:condition:metabolic-health",'
        '"dst_doc_id":"claim:c_weight_waist_tracking","relation":"has_claim",'
        '"confidence":0.88,"source_claim_id":"claim:c_weight_waist_tracking"}\n'
    )
    for file_name in (
        "pages.jsonl",
        "protocols.jsonl",
        "contraindications.jsonl",
        "eval_cases.jsonl",
    ):
        (artifact_dir / file_name).write_text("")
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": "2.0",
                "counts": {
                    "entities": 1,
                    "claims": 1,
                    "pages": 0,
                    "protocols": 0,
                    "contraindications": 0,
                    "eval_cases": 0,
                    "relations": 1,
                },
            }
        )
        + "\n"
    )

    first = import_system_kb_artifacts(db, artifact_dir, actor="test")
    second = import_system_kb_artifacts(db, artifact_dir, actor="test")

    legacy_counts = {"documents": 2, "edges": 1, "skipped_documents": 0, "skipped_edges": 0}
    assert {key: first[key] for key in legacy_counts} == legacy_counts
    assert {key: second[key] for key in legacy_counts} == legacy_counts
    assert first["changed_document_ids"] == [
        "claim:c_weight_waist_tracking",
        "entity:condition:metabolic-health",
    ]
    assert second["changed_document_ids"] == []
    assert second["proof"]["decision"] == "miss"
    assert db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_weight_waist_tracking").count() == 1


def test_format_system_knowledge_for_prompt_is_bounded(db):
    db.add(
        KBDocument(
            doc_id="claim:c_weight_waist_tracking",
            doc_type="claim",
            entity_type="intervention",
            entity_id="weight-waist-tracking",
            title="体重和腰围晨起记录",
            summary="减重和代谢风险管理应跟踪体重与腰围趋势。",
            confidence=0.72,
            evidence_level="B",
            applies_when=["twin.goals.weight_loss.active == true"],
            sources=["dedao:fengxue-weight-loss"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()

    prompt_block = format_system_knowledge_for_prompt(
        db,
        {"goals": {"weight_loss": {"active": True}}},
        max_claims=3,
    )

    assert "## 系统知识库相关条目" in prompt_block
    assert "体重和腰围晨起记录" in prompt_block
    assert "claim:c_weight_waist_tracking" in prompt_block
    assert "不替代医生诊断" in prompt_block


def test_format_system_knowledge_result_for_prompt_matches_wrapper(monkeypatch, db):
    lookup_result = {
        "entities": [],
        "contextual_entities": [],
        "claims": [
            {
                "doc_id": "claim:c_first",
                "title": "第一条知识",
                "summary": "第一条摘要",
                "confidence": 0.82,
                "evidence_level": "A",
                "sources": ["source:first"],
            },
            {
                "doc_id": "claim:c_second",
                "title": "第二条知识",
                "summary": "第二条摘要",
                "confidence": 0.71,
                "evidence_level": "B",
                "sources": ["source:second"],
            },
        ],
        "claim_boundary": "ignored-wrapper-field",
    }
    original = deepcopy(lookup_result)
    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        lambda _db, _twin: lookup_result,
    )

    pure = format_system_knowledge_result_for_prompt(lookup_result)
    wrapped = format_system_knowledge_for_prompt(db, {"goals": {}})

    assert pure == wrapped
    assert lookup_result == original
    assert pure.index("第一条知识") < pure.index("第二条知识")
    assert "不替代医生诊断" in pure


def test_format_system_knowledge_result_for_prompt_honors_limits_and_empty_result():
    lookup_result = {
        "claims": [
            {
                "doc_id": "claim:c_first",
                "title": "第一条知识",
                "summary": "第一条很长的摘要" * 20,
                "confidence": 0.82,
                "evidence_level": "A",
                "sources": ["source:first"],
            },
            {
                "doc_id": "claim:c_second",
                "title": "第二条知识",
                "summary": "第二条摘要",
                "confidence": 0.71,
                "evidence_level": "B",
                "sources": ["source:second"],
            },
        ]
    }

    one_claim = format_system_knowledge_result_for_prompt(
        lookup_result,
        max_claims=1,
    )
    bounded = format_system_knowledge_result_for_prompt(
        lookup_result,
        max_claims=1,
        max_chars=120,
    )

    assert "第一条知识" in one_claim
    assert "第二条知识" not in one_claim
    assert len(bounded) <= 120
    assert bounded.endswith("...")
    assert format_system_knowledge_result_for_prompt({"claims": []}) == ""


def test_lookup_for_twin_matches_longevity_goal_to_aging_hallmark(db):
    db.add_all(
        [
            KBDocument(
                doc_id="entity:aging_hallmark:mitochondrial_dysfunction",
                doc_type="entity",
                entity_type="aging_hallmark",
                entity_id="mitochondrial_dysfunction",
                title="线粒体功能障碍",
                summary="衰老标志之一，用于长期轨迹解释，不直接推出补剂建议。",
                confidence=0.72,
                evidence_level="B",
                sources=["cell:2023-hallmarks-of-aging"],
                last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="claim:c_aging_hallmarks_are_trajectory_taxonomy",
                doc_type="claim",
                entity_type="aging_hallmark",
                entity_id="trajectory-taxonomy",
                title="衰老标志只作为轨迹分类框架",
                summary="衰老标志适合组织长期风险和机制沟通，不能直接映射为补剂处方。",
                confidence=0.76,
                evidence_level="B",
                applies_when=["twin.goals.longevity.active == true"],
                recommends_lookup=["entity:aging_hallmark:mitochondrial_dysfunction"],
                sources=["cell:2023-hallmarks-of-aging"],
                last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
                metadata_json={"review_status": "reviewed"},
            ),
        ]
    )
    db.commit()

    result = lookup_for_twin(db, {"goals": {"longevity": {"active": True}}})

    assert [entity["doc_id"] for entity in result["entities"]] == [
        "entity:aging_hallmark:mitochondrial_dysfunction"
    ]
    assert [claim["doc_id"] for claim in result["claims"]] == [
        "claim:c_aging_hallmarks_are_trajectory_taxonomy"
    ]


def test_seed_artifacts_include_fourteen_aging_hallmarks():
    import json
    artifact_path = Path(__file__).resolve().parents[1] / "data/system_kb_v2_seed/entities.jsonl"
    hallmarks = [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("entity_type") == "aging_hallmark"
    ]

    assert len(hallmarks) == 14
    assert {item["entity_id"] for item in hallmarks} >= {
        "genomic_instability",
        "telomere_attrition",
        "mitochondrial_dysfunction",
        "psychosocial_stress_isolation",
    }


def test_attach_system_knowledge_evidence_adds_claim_refs_to_specialist_findings(db):
    db.add(
        KBDocument(
            doc_id="claim:c_zone2_as_metabolic_base_not_when_recovery_low",
            doc_type="claim",
            entity_type="intervention",
            entity_id="zone2-training",
            title="中等强度有氧是代谢基础但需受恢复状态约束",
            summary="恢复不足时降低训练强度。",
            confidence=0.73,
            evidence_level="B",
            applies_when=["twin.wearable.sleep_duration_hours < 6.5"],
            sources=["dedao:fengxue-weight-loss"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"review_status": "reviewed", "domain": "movement"},
        )
    )
    db.commit()
    finding = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="今天降低跑步强度",
        findings=[{"title": "降低跑步强度", "action": "今天只做恢复活动"}],
    )

    attach_system_knowledge_evidence(
        db,
        {"wearable": {"sleep_duration_hours": 5.8}},
        [finding],
    )

    assert finding.evidence_refs == ["claim:c_zone2_as_metabolic_base_not_when_recovery_low"]
    assert finding.raw["system_kb_evidence_refs"] == [
        "claim:c_zone2_as_metabolic_base_not_when_recovery_low"
    ]
    assert finding.raw["evidence_resolution"]["support_status"] == "supported"
    assert finding.raw["evidence_resolution"]["unsupported"] is False
    assert finding.findings[0]["evidence_refs"] == [
        "claim:c_zone2_as_metabolic_base_not_when_recovery_low"
    ]


def test_attach_system_knowledge_evidence_uses_single_lookup_for_multiple_findings(
    db, monkeypatch
):
    lookup_calls = 0

    def fake_lookup(_db, _twin):
        nonlocal lookup_calls
        lookup_calls += 1
        return {
            "entities": [],
            "contextual_entities": [],
            "claims": [
                {
                    "doc_id": "claim:c_recovery_low_reduce_intensity",
                    "entity_type": "intervention",
                    "entity_id": "recovery-training",
                    "title": "恢复不足时降低跑步强度",
                    "summary": "恢复不足时降低训练强度并改为恢复活动。",
                    "metadata": {"domain": "movement"},
                }
            ],
            "claim_boundary": "test-boundary",
        }

    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        fake_lookup,
    )
    findings = [
        SpecialistFinding(
            specialist_name="movement_coach",
            category="movement",
            summary="恢复不足，今天降低跑步强度",
            findings=[{"title": "降低跑步强度", "action": "改为恢复活动"}],
        ),
        SpecialistFinding(
            specialist_name="movement_coach",
            category="movement",
            summary="今天只做恢复活动，避免高强度跑步",
            findings=[{"title": "恢复活动", "action": "避免高强度跑步"}],
        ),
    ]

    result = attach_system_knowledge_evidence(db, {"wearable": {}}, findings)

    assert lookup_calls == 1
    assert result["findings_updated"] == 2
    assert result["claim_refs"] == 1
    assert all(
        finding.evidence_refs == ["claim:c_recovery_low_reduce_intensity"]
        for finding in findings
    )
    assert all(
        finding.raw["evidence_resolution"]["support_status"] == "supported"
        for finding in findings
    )


def test_attach_system_knowledge_evidence_precomputed_falsey_zero_hit_does_not_lookup(
    db, monkeypatch
):
    def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("precomputed zero-hit must not trigger another lookup")

    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        unexpected_lookup,
    )
    finding = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="恢复不足，今天降低跑步强度",
        findings=[{"title": "降低跑步强度"}],
    )

    result = attach_system_knowledge_evidence(
        db,
        {"wearable": {}},
        [finding],
        lookup_result={},
    )

    assert result["findings_updated"] == 0
    assert result["claim_refs"] == 0
    assert finding.evidence_refs == []
    assert finding.raw["evidence_resolution"]["support_status"] == "model_inference"
    assert finding.raw["unsupported"] is True


def test_attach_system_knowledge_evidence_not_applicable_without_lookup(db, monkeypatch):
    def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("not-applicable findings must not query system knowledge")

    monkeypatch.setattr(
        "app.services.system_knowledge_service.lookup_for_twin",
        unexpected_lookup,
    )
    record_finding = SpecialistFinding(
        specialist_name="fuel_strategist",
        category="nutrition",
        summary="已记录晚餐",
        findings=[{"type": "record", "title": "晚餐记录"}],
        raw={"operation": "record_meal"},
    )
    gap_finding = SpecialistFinding(
        specialist_name="longitudinal_analyst",
        category="longitudinal",
        summary="长期数据暂缺",
        findings=[{"type": "data_gap", "title": "长期数据暂缺"}],
        raw={"data_gap": True},
    )

    empty_result = attach_system_knowledge_evidence(db, {}, [])
    not_applicable_result = attach_system_knowledge_evidence(
        db,
        {},
        [record_finding, gap_finding],
    )

    assert empty_result == {"findings_updated": 0, "claim_refs": 0}
    assert not_applicable_result == {"findings_updated": 0, "claim_refs": 0}
    assert record_finding.raw["evidence_resolution"]["support_status"] == "not_applicable"
    assert gap_finding.raw["evidence_resolution"]["support_status"] == "not_applicable"


def test_attach_system_knowledge_evidence_marks_record_findings_not_applicable(db):
    finding = SpecialistFinding(
        specialist_name="fuel_strategist",
        category="nutrition",
        summary="已记录晚餐",
        findings=[
            {
                "type": "record",
                "title": "晚餐记录",
                "food": "牛排 150g",
                "calories": 380,
            }
        ],
        raw={"operation": "record_meal"},
    )

    result = attach_system_knowledge_evidence(db, {}, [finding])

    assert result["findings_updated"] == 0
    assert finding.evidence_refs == []
    assert finding.raw["evidence_resolution"]["support_status"] == "not_applicable"
    assert finding.raw["evidence_resolution"]["unsupported"] is False
    assert finding.raw["unsupported"] is False
    assert finding.raw["unsupported_reason"] is None


def test_attach_system_knowledge_evidence_marks_data_gap_findings_not_applicable(db):
    finding = SpecialistFinding(
        specialist_name="longitudinal_analyst",
        category="longitudinal",
        summary="6 个月趋势 · 长期数据暂缺",
        findings=[{"type": "data_gap", "title": "长期数据暂缺"}],
        raw={"data_gap": True},
    )

    result = attach_system_knowledge_evidence(db, {}, [finding])

    assert result["findings_updated"] == 0
    assert finding.evidence_refs == []
    assert finding.raw["evidence_resolution"]["support_status"] == "not_applicable"
    assert finding.raw["evidence_resolution"]["unsupported"] is False
    assert finding.raw["unsupported"] is False
    assert finding.raw["unsupported_reason"] is None


def test_attach_system_knowledge_evidence_does_not_fallback_to_unrelated_twin_claim(db):
    db.add(
        KBDocument(
            doc_id="claim:c_mthfr_c677t_hcy_folate_boundary",
            doc_type="claim",
            entity_type="gene",
            entity_id="MTHFR",
            title="MTHFR C677T 与叶酸转化边界",
            summary="MTHFR C677T TT 与叶酸转化和同型半胱氨酸监测相关。",
            confidence=0.82,
            evidence_level="B",
            applies_when=["twin.genetics.MTHFR_C677T in [CT, TT]"],
            sources=["dedao:qiuzilong-genetics-07"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"review_status": "reviewed", "domain": "nutrition"},
        )
    )
    db.commit()
    finding = SpecialistFinding(
        specialist_name="fuel_strategist",
        category="nutrition",
        summary="晚餐热量基本平衡，炸物偏多，建议加一份蔬菜",
        findings=[{"title": "加一份蔬菜", "action": "下一餐增加绿叶菜"}],
    )

    attach_system_knowledge_evidence(
        db,
        {"genetics": {"MTHFR_C677T": "TT"}},
        [finding],
    )

    assert finding.evidence_refs == []
    assert finding.raw["evidence_resolution"]["support_status"] == "model_inference"
    assert finding.raw["unsupported"] is True


def test_select_claim_refs_requires_finding_claim_text_overlap():
    finding = SpecialistFinding(
        specialist_name="fuel_strategist",
        category="nutrition",
        summary="晚餐热量基本平衡，炸物偏多，建议加一份蔬菜",
        findings=[{"title": "加一份蔬菜", "action": "下一餐增加绿叶菜"}],
    )
    claims = [
        {
            "doc_id": "claim:c_mthfr_c677t_hcy_folate_boundary",
            "entity_type": "gene",
            "entity_id": "MTHFR",
            "title": "MTHFR C677T 与叶酸转化边界",
            "summary": "MTHFR C677T TT 与叶酸转化和同型半胱氨酸监测相关。",
            "metadata": {"domain": "nutrition"},
        }
    ]

    assert _select_claim_refs_for_specialist(finding, claims, 3) == []
