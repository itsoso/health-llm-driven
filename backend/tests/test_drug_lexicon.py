"""单一事实源药名/补剂词库(drug_lexicon)的不变量测试。

护住三件事:
1. safety 规则(ddi/dsi)引用的就是共享对象 → 迁移不改安全行为(逐字节相同)。
2. 药名别名**自动流入** KB 对账处方 gate → gate 跟随安全词库,不再手抄会漂移的副本。
3. 派生 gate term set 对自由文本**去了歧义 + 去食物类** → 保持 over-refuse 偏向但不误伤良性 claim。
"""
from app.services.drug_lexicon import (
    COMMON_DRUG_ALIASES,
    DRUG_CLASS_ALIASES,
    SUPPLEMENT_CLASS_ALIASES,
    _FREE_TEXT_AMBIGUOUS_TERMS,
    _FREE_TEXT_EXCLUDED_SUPPLEMENT_CLASSES,
    contains_drug_name,
    contains_supplement_name,
    drug_name_spans,
    drug_name_free_text_terms,
    prescriptive_free_text_terms,
    supplement_name_entity_terms,
)


def test_ddi_dsi_reference_shared_object():
    """ddi.DRUG_ALIASES / dsi.SUPP_ALIASES 就是共享 lexicon 对象 → 安全行为逐字节不变。"""
    from app.agents.safety_guardian.rules.ddi import DRUG_ALIASES
    from app.agents.safety_guardian.rules.dsi import SUPP_ALIASES

    assert DRUG_ALIASES is DRUG_CLASS_ALIASES
    assert SUPP_ALIASES is SUPPLEMENT_CLASS_ALIASES


def test_drug_aliases_flow_into_gate_single_source():
    """每个非歧义药名别名都自动进 gate term set —— 单一事实源不断裂。"""
    terms = prescriptive_free_text_terms()
    for cls, aliases in {**DRUG_CLASS_ALIASES, **COMMON_DRUG_ALIASES}.items():
        for alias in aliases:
            tok = alias.strip().lower()
            if tok in _FREE_TEXT_AMBIGUOUS_TERMS:
                continue  # 歧义短子串刻意不进自由文本集(见 denylist)
            assert tok in terms, f"{cls}:{alias!r} 未进 gate term set(单一事实源断裂)"


def test_included_supplement_classes_flow_into_gate():
    terms = prescriptive_free_text_terms()
    for cls, aliases in SUPPLEMENT_CLASS_ALIASES.items():
        if cls in _FREE_TEXT_EXCLUDED_SUPPLEMENT_CLASSES:
            continue
        for alias in aliases:
            tok = alias.strip().lower()
            if tok in _FREE_TEXT_AMBIGUOUS_TERMS:
                continue
            assert tok in terms, f"{cls}:{alias!r} 未进 gate term set"


def test_food_and_herb_classes_excluded_from_gate():
    """食物/草药类的独特别名不进 gate —— 命名它们的良性饮食 claim 不被硬拒。"""
    terms = prescriptive_free_text_terms()
    for probe in ("葡萄柚", "西柚", "grapefruit", "大蒜", "garlic", "银杏", "ginkgo",
                  "姜黄素", "turmeric", "益生菌", "akkermansia"):
        assert probe not in terms, f"{probe!r} 不应进 gate(食物/草药类,会误伤良性 claim)"


def test_ambiguous_short_substrings_excluded_from_gate():
    """自由文本会误伤的短/歧义子串必须被剔除(钙化/地铁/environ/April 陷阱)。"""
    terms = prescriptive_free_text_terms()
    for probe in ("铁", "钙", "锌", "镁", "锂", "门冬", "普利", "格列",
                  "iron", "pril", "mao", "vk", "epa", "dha"):
        assert probe not in terms, f"歧义子串 {probe!r} 泄漏进 gate → 会 over-refuse"


def test_named_drug_residual_now_covered():
    """评审点名的命名残余(旧 gate 漏)现在都在 gate term set 里。"""
    terms = prescriptive_free_text_terms()
    for probe in ("氨氯地平", "amlodipine", "阿莫西林", "amoxicillin", "左甲状腺素",
                  "levothyroxine", "lisinopril", "布洛芬", "ibuprofen", "他克莫司",
                  "别嘌醇", "allopurinol", "对乙酰氨基酚"):
        assert probe in terms, f"{probe!r} 应在 gate term set 里(命名残余未闭合)"


def test_drug_name_detector_covers_complete_names_without_short_substring_false_positives():
    terms = drug_name_free_text_terms()
    assert "二甲双胍" in terms
    assert "格列美脲" in terms
    assert contains_drug_name("把二甲双胍换成格列美脲") is True
    assert len(drug_name_spans("把二甲双胍换成格列美脲")) == 2
    assert contains_drug_name("停用跑步机，改为户外步行") is False
    assert contains_drug_name("停用睡前闹钟") is False
    assert contains_drug_name("ｗａｒｆａｒｉｎ1片") is True


def test_supplement_name_detector_uses_complete_names_without_food_or_substring_false_positives():
    assert contains_supplement_name("fish oil 2粒") is True
    assert contains_supplement_name("omega-3 2粒") is True
    assert contains_supplement_name("magnesium 2粒") is True
    assert contains_supplement_name("coq102粒") is True
    assert contains_supplement_name("b122粒") is True
    assert contains_supplement_name("d32粒") is True
    assert contains_supplement_name("Ｄ３2粒") is True
    assert contains_supplement_name("ＣｏＱ１０2粒") is True
    assert contains_supplement_name("Ｂ１２2粒") is True
    assert contains_supplement_name("fish‑oil2粒") is True
    assert contains_supplement_name("fish–oil2粒") is True
    assert contains_supplement_name("fish​oil2粒") is True
    assert contains_supplement_name("d₃2粒") is True
    assert contains_supplement_name("coq₁₀2粒") is True
    assert contains_supplement_name("vitaminDfishoil") is True
    assert contains_supplement_name("vitamindandfishoil") is True
    assert contains_supplement_name("d3-fish-oil") is True
    assert contains_supplement_name("environment monitoring") is False
    assert contains_supplement_name("garlic bread") is False
    assert contains_supplement_name("coq10environment") is False
    assert contains_supplement_name("d32factor") is False


def test_explicit_supplement_entity_lexicon_keeps_exact_food_and_herb_names():
    terms = supplement_name_entity_terms()
    assert {"garlic", "姜黄素", "益生菌"} <= terms


# 迁移前 kb_reconciliation_merge 手抄的处方 term 全集(2026-07 迁到 drug_lexicon 前)。
# 钉死「覆盖只 TIGHTEN 不 loosen」—— 新派生集必须是旧集的**严格超集**,否则是覆盖回归。
_LEGACY_PRESCRIPTIVE_TERMS = frozenset({
    "剂量", "服用", "口服", "顿服", "维持量", "负荷量", "停药", "减量", "加量", "滴定", "用法用量",
    "二甲双胍", "华法林", "阿托伐他汀", "辛伐他汀", "他汀", "阿司匹林", "氯吡格雷", "胰岛素",
    "泼尼松", "甲氨蝶呤", "利伐沙班", "达比加群", "质子泵抑制剂",
    "dose", "dosage", "titrat", "mg/kg", "maintenance dose", "loading dose", "posology",
    "metformin", "warfarin", "statin", "atorvastatin", "simvastatin", "aspirin", "clopidogrel",
    "insulin", "prednis", "methotrexate", "rivaroxaban", "dabigatran", "ssri", "nsaid",
})


def test_new_gate_is_strict_superset_of_legacy():
    """加层不减层:派生 gate 集必须覆盖旧手抄集里的每一个词(覆盖只 TIGHTEN)。"""
    terms = prescriptive_free_text_terms()
    missing = sorted(t for t in _LEGACY_PRESCRIPTIVE_TERMS if t not in terms)
    assert not missing, f"覆盖回归(loosened): 旧 gate 词丢失 {missing}"


def test_derived_terms_all_nonempty_and_lowercased():
    terms = prescriptive_free_text_terms()
    assert terms, "派生 term set 不应为空"
    for t in terms:
        assert t == t.strip().lower() and t, f"term {t!r} 未规范化(strip+lower)"
