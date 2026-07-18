import pytest


@pytest.mark.parametrize(
    "prompt",
    [
        "糖尿病患者早餐前注射20单位胰岛素的演示短视频",
        "take 20 mg prednisone daily to treat inflammation",
        "take predni\u200bsone 20 mg daily to treat inflammation",
        "create an illustration to administer 20 mg corticosteroid daily",
        "inject 15 units of heparin every morning",
        "inject 20 units of testosterone daily",
        "an instructional video on treating HIV with an antiretroviral regimen",
        "create a COPD inhaler treatment explainer",
        "制作一个每周做透析 3 次的流程海报",
        "做一张每日服用 1 粒维生素D 的行动海报",
        "生成高血压患者调整降压药方案的插画",
    ],
)
def test_rejects_medical_or_dose_content_before_provider_dispatch(prompt):
    from app.services.aigc_media_policy import AIGCMediaPolicyError, validate_aigc_media_policy

    with pytest.raises(AIGCMediaPolicyError, match="诊断、处方、用药或治疗"):
        validate_aigc_media_policy(purpose="wellness_story", prompt=prompt)


@pytest.mark.parametrize(
    ("purpose", "prompt"),
    [
        ("meal_visual", "制作一张色彩明快的早餐备餐步骤图，展示燕麦、水果和餐盘摆放"),
        ("movement_routine", "生成一段 5 秒的晨间拉伸动作演示，画面清晰简洁"),
        ("hydration_reminder", "制作一张下午补水提醒卡，包含水杯和轻松的办公室场景"),
        ("sleep_routine", "生成一张睡前放松流程插画，表现关灯、阅读和安静卧室"),
    ],
)
def test_allows_bounded_wellness_communication_content(purpose, prompt):
    from app.services.aigc_media_policy import validate_aigc_media_policy

    assert validate_aigc_media_policy(purpose=purpose, prompt=prompt) == purpose
