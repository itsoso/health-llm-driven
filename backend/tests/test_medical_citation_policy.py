import pytest
from app.services.medical_citation_policy import (
    build_medical_citation_bundle,
    render_medical_citation_prompt,
)


def test_apple_bmi_review_prompt_gets_chinese_and_international_authority_links():
    bundle = build_medical_citation_bundle("帮我算我的BMI")

    assert bundle.required is True
    assert bundle.topics == ("bmi",)
    assert [item["organization"] for item in bundle.public_citations] == [
        "国家卫生健康委员会",
        "美国疾病控制与预防中心",
    ]
    assert bundle.public_citations[0]["url"].startswith("https://www.nhc.gov.cn/")
    assert bundle.public_citations[1]["url"] == (
        "https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html"
    )
    assert all(item["url"].startswith("https://") for item in bundle.public_citations)

    prompt = render_medical_citation_prompt(bundle)
    assert "## 本轮医学引用" in prompt
    assert "18.5–23.9" in prompt
    assert "筛查指标，不是诊断" in prompt
    assert "客户端会在回答下方直接展示" in prompt


def test_height_and_weight_question_is_grounded_as_bmi_before_answer_generation():
    bundle = build_medical_citation_bundle("我身高 175 厘米、体重 70 公斤，正常吗？")

    assert bundle.required is True
    assert bundle.topics == ("bmi",)
    assert [item["source_id"] for item in bundle.public_citations] == [
        "nhc:adult-weight-standard",
        "cdc:adult-bmi-categories",
    ]


def test_bmi_answer_does_not_dilute_request_sources_with_incidental_advice_topics():
    bundle = build_medical_citation_bundle(
        "帮我算我的 BMI",
        answer_text=(
            "BMI 是 22.9，属于筛查范围内。日常可以继续均衡营养，"
            "关注食物热量，并保持规律活动。"
        ),
    )

    assert bundle.topics == ("bmi",)
    assert [item["source_id"] for item in bundle.public_citations] == [
        "nhc:adult-weight-standard",
        "cdc:adult-bmi-categories",
    ]


def test_personal_data_read_without_interpretation_does_not_add_medical_citations():
    bundle = build_medical_citation_bundle("我今天走了多少步？")

    assert bundle.required is False
    assert bundle.public_citations == []
    assert render_medical_citation_prompt(bundle) == ""


def test_uncataloged_health_advice_fails_safe_to_official_health_directory():
    bundle = build_medical_citation_bundle("我最近总是头痛，应该怎么办？")

    assert bundle.required is True
    assert bundle.topics == ("general_health",)
    assert bundle.public_citations == [
        {
            "source_id": "nlm:medlineplus-health-topics",
            "title": "MedlinePlus 健康主题索引",
            "organization": "美国国立医学图书馆",
            "url": "https://medlineplus.gov/healthtopics.html",
            "topic": "general_health",
            "claim_scope": "用于核对具体症状和疾病主题；不替代医生诊断。",
        }
    ]


def test_common_symptom_and_medication_advice_keeps_general_and_drug_sources_visible():
    bundle = build_medical_citation_bundle("口腔溃疡应该吃什么药？")

    assert bundle.required is True
    assert bundle.topics == ("medication", "general_health")
    assert [item["source_id"] for item in bundle.public_citations] == [
        "nlm:dailymed",
        "nlm:medlineplus-health-topics",
    ]


def test_common_cold_advice_fails_safe_to_general_health_source():
    bundle = build_medical_citation_bundle("感冒怎么办？")

    assert bundle.required is True
    assert bundle.topics == ("general_health",)
    assert bundle.public_citations[0]["source_id"] == "nlm:medlineplus-health-topics"


def test_existing_health_runtime_and_system_kb_urls_are_preserved_and_deduplicated():
    bundle = build_medical_citation_bundle(
        "腰痛怎么办？",
        health_evidence_manifest={
            "authority_sources": [
                {
                    "source": "https://www.nice.org.uk/guidance/ng59",
                    "title": "NICE 腰痛与坐骨神经痛指南",
                    "organization": "NICE",
                    "kind": "guideline",
                },
                {
                    "source": "http://insecure.example.test/source",
                    "title": "不安全来源",
                    "organization": "Unknown",
                },
                {
                    "source": "https://user:pass@example.test/source",
                    "title": "带凭据来源",
                    "organization": "Unknown",
                },
                {
                    "source": "https://localhost/source",
                    "title": "本机来源",
                    "organization": "Unknown",
                },
                {
                    "source": "https://10.0.0.1/source",
                    "title": "内网来源",
                    "organization": "Unknown",
                },
            ]
        },
        system_evidence_card={
            "type": "system_knowledge_evidence",
            "data": {
                "claims": [
                    {
                        "title": "MTHFR 解读边界",
                        "sources": ["pubmed:19033271"],
                        "metadata": {
                            "external_sources": [
                                {
                                    "source": "pubmed:19033271",
                                    "url": "https://pubmed.ncbi.nlm.nih.gov/19033271/",
                                    "title": "MTHFR review",
                                }
                            ]
                        },
                    }
                ]
            },
        },
    )

    urls = [item["url"] for item in bundle.public_citations]
    assert "https://www.nice.org.uk/guidance/ng59" in urls
    assert "https://pubmed.ncbi.nlm.nih.gov/19033271/" in urls
    assert "http://insecure.example.test/source" not in urls
    assert "https://user:pass@example.test/source" not in urls
    assert "https://localhost/source" not in urls
    assert "https://10.0.0.1/source" not in urls
    assert len(urls) == len(set(urls))


def test_topic_sources_cannot_be_evicted_by_a_large_evidence_manifest():
    bundle = build_medical_citation_bundle(
        "帮我算我的 BMI",
        health_evidence_manifest={
            "authority_sources": [
                {
                    "source": f"https://guidelines.example.org/source-{index}",
                    "title": f"外部证据 {index}",
                    "organization": "外部机构",
                }
                for index in range(4)
            ]
        },
    )

    assert [item["source_id"] for item in bundle.public_citations[:2]] == [
        "nhc:adult-weight-standard",
        "cdc:adult-bmi-categories",
    ]


def test_answer_side_calculation_adds_citation_even_when_request_looked_like_a_record():
    bundle = build_medical_citation_bundle(
        "记录午餐牛肉 50 克",
        answer_text="已估算本餐热量约 120 kcal，并给出蛋白质参考。",
    )

    assert bundle.required is True
    assert bundle.topics == ("nutrition_energy",)
    assert bundle.public_citations[0]["source_id"] == "usda:fooddata-central"


@pytest.mark.parametrize(
    ("prompt", "topic", "source_id"),
    [
        ("心率正常范围是多少？", "vital_signs", "nlm:vital-signs"),
        ("体温 39 度应该怎么办？", "vital_signs", "nlm:vital-signs"),
        ("血氧 92% 正常吗？", "oxygen_saturation", "nlm:pulse-oximetry"),
        ("成年人每天应该喝多少水？", "hydration", "nhs:hydration"),
    ],
)
def test_common_medical_measurements_and_calculations_always_have_official_sources(
    prompt,
    topic,
    source_id,
):
    bundle = build_medical_citation_bundle(prompt)

    assert bundle.required is True
    assert topic in bundle.topics
    assert source_id in [item["source_id"] for item in bundle.public_citations]
    assert all(item["url"].startswith("https://") for item in bundle.public_citations)


@pytest.mark.parametrize(
    "prompt",
    [
        "最近总是焦虑，应该怎么办？",
        "月经推迟一周正常吗？",
    ],
)
def test_common_mental_and_reproductive_health_advice_fails_safe_to_health_directory(
    prompt,
):
    bundle = build_medical_citation_bundle(prompt)

    assert bundle.required is True
    assert bundle.topics == ("general_health",)
    assert bundle.public_citations[0]["source_id"] == "nlm:medlineplus-health-topics"
