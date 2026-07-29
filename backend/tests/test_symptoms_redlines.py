"""症状级急症红线 + 世界观注入。钉:危急组合命中 CRITICAL;无症状/普通症状不误报。"""
from datetime import datetime

import pytest

from app.agents.safety_guardian.engine import evaluate_rules
from app.agents.safety_guardian.schema import Severity
from app.config import settings
from app.services.health_worldview import worldview_prompt_blob
from app.twin.schema import HealthTwin, TwinMeta


def _twin_with_symptoms(symptoms):
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.acute.symptom_texts_all = symptoms
    return t


def _run(symptoms):
    return evaluate_rules(_twin_with_symptoms(symptoms))


def _ids(alerts):
    return {a.rule_id for a in alerts}


@pytest.fixture(autouse=True)
def _enable_health_evidence_runtime(monkeypatch):
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)


def test_cauda_equina_rule_is_inert_while_release_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", False)

    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛", "突然无法控制尿液"])
    )


def test_cardiac_event_needs_chest_plus_danger():
    # 仅"胸闷"不报(可能是焦虑/胃食管反流);胸痛+冷汗才报
    assert "symptoms.acute_cardiac_event" not in _ids(_run(["有点胸闷"]))
    alerts = _run(["胸痛,还冒冷汗,感觉放射到左臂"])
    a = next(a for a in alerts if a.rule_id == "symptoms.acute_cardiac_event")
    assert a.severity == Severity.CRITICAL and a.requires_medical_attention


def test_stroke_fast():
    a = _ids(_run(["突然口角歪斜,说话不清"]))
    assert "symptoms.acute_stroke_fast" in a


def test_dyspnea_and_abdomen():
    assert "symptoms.acute_dyspnea" in _ids(_run(["突然喘不上气,无法平卧"]))
    assert "symptoms.acute_abdomen" in _ids(_run(["剧烈腹痛,还呕血"]))


def test_low_back_pain_with_cauda_equina_warning_signs_is_critical():
    scenarios = [
        ["腰痛", "两条腿都麻木无力"],
        ["下背痛", "会阴和肛门周围没有感觉"],
        ["腰疼", "突然排尿困难"],
        ["腰痛", "大小便失禁"],
        ["腰痛", "突然无法控制尿液"],
        ["腰痛", "最近开始漏尿"],
        ["腰痛", "尿意和便意消失"],
        ["lower back pain", "cannot empty my bladder"],
        ["lower back pain", "numbness in my saddle area"],
        ["lower back pain", "difficulty starting urination"],
    ]
    for symptoms in scenarios:
        alert = next(
            item
            for item in _run(symptoms)
            if item.rule_id == "symptoms.cauda_equina_warning"
        )
        assert alert.severity == Severity.CRITICAL
        assert alert.requires_medical_attention is True
        assert alert.references


def test_benign_back_pain_does_not_trigger_cauda_equina_warning():
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["久坐后腰有点酸", "走动后缓解"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛", "只有右腿轻微发麻"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛", "没有尿失禁，也没有会阴麻木"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛", "尿频"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛", "一条腿有点无力"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(
            [
                "腰痛，但排尿并没有任何困难",
                "会阴也完全没有麻木，双腿没有无力",
            ]
        )
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛，无明显会阴麻木，也无排尿困难"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛，不是排尿困难，只是尿频"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛", "只有右侧坐骨神经痛但症状稳定，没有无力"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(["腰痛", "排尿困难已稳定多年，今天没有新变化"])
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(
            [
                "lower back pain",
                (
                    "difficulty peeing has been stable for years "
                    "and is unchanged"
                ),
            ]
        )
    )
    assert "symptoms.cauda_equina_warning" not in _ids(
        _run(
            [
                "腰痛很严重，但不是突然出现，也没有快速加重",
                "没有双腿、会阴或大小便变化",
            ]
        )
    )
    for phrase in (
        "排尿不困难",
        "双腿不麻木，也不无力",
        "会阴并不麻木",
        "排尿并不费力",
    ):
        assert "symptoms.cauda_equina_warning" not in _ids(
            _run(["腰痛", phrase])
        )


def test_natural_cauda_equina_phrasing_still_triggers_warning():
    scenarios = [
        ["腰背痛", "排尿开始变得很困难"],
        ["腰疼", "会阴附近感觉明显变迟钝"],
        ["腰痛", "小便完全解不出来"],
        ["腰痛", "尿怎么都排不出来"],
        ["腰痛", "肛周麻木"],
        ["腰痛", "感觉不到擦拭肛门"],
    ]

    for symptoms in scenarios:
        assert "symptoms.cauda_equina_warning" in _ids(_run(symptoms))


@pytest.mark.parametrize(
    "symptoms",
    [
        ["腰痛", "我的排尿困难已稳定多年，但今天没有加重"],
        ["腰痛", "我的排尿困难已稳定多年，但今天并未加重"],
        ["腰痛", "我的排尿困难已稳定多年，目前没有恶化"],
        ["腰痛", "我长期有排尿困难，但今天没有尿潴留"],
        [
            "lower back pain",
            "longstanding difficulty peeing, but not worse today",
        ],
        [
            "lower back pain",
            "longstanding difficulty peeing, no new urinary retention",
        ],
        ["腰痛加重了", "我的排尿困难已稳定多年，没有变化"],
        ["我的排尿困难已稳定多年", "但腰痛这两天加重了"],
    ],
)
def test_negated_or_unrelated_change_does_not_trigger_guardian(symptoms):
    assert "symptoms.cauda_equina_warning" not in _ids(_run(symptoms))


@pytest.mark.parametrize(
    "symptoms",
    [
        ["腰痛", "排尿困难已稳定多年，但今天突然完全排不出尿"],
        ["腰痛", "我长期有排尿困难，但今天明显加重了"],
        ["腰痛", "我长期有排尿困难，这两天更严重了"],
        ["腰痛", "我长期有排尿困难，最近越来越难尿"],
        ["腰痛", "我长期有排尿困难，最近控制不住小便"],
        ["腰痛", "排尿困难，今天尿不出来，既往稳定多年"],
        ["腰痛", "排尿困难、现在尿不出来，此前一直稳定"],
        ["腰痛", "排尿困难，今天尿潴留，之前一直稳定"],
        ["腰痛", "排尿困难，今天尿失禁，之前稳定"],
        ["腰痛", "排尿困难，今天会阴麻木，之前稳定"],
        [
            "lower back pain",
            (
                "difficulty peeing has been stable for years, "
                "but today I cannot empty my bladder"
            ),
        ],
        [
            "lower back pain",
            "longstanding difficulty peeing, but much worse today",
        ],
        [
            "lower back pain",
            (
                "longstanding difficulty peeing, "
                "getting worse this week"
            ),
        ],
        [
            "lower back pain",
            "difficulty peeing, cannot urinate, stable before",
        ],
        [
            "lower back pain",
            "difficulty peeing, saddle numbness, stable before",
        ],
    ],
)
def test_stable_urinary_history_never_masks_a_new_guardian_warning(symptoms):
    assert "symptoms.cauda_equina_warning" in _ids(_run(symptoms))


def test_negated_persistent_red_flags_do_not_trigger_warning():
    assert "symptoms.red_flag_persistent_warning" not in _ids(
        _run(["腰痛", "没有不明原因消瘦，也没有持续发热"])
    )


def test_red_flag_warning():
    a = next(x for x in _run(["最近不明原因暴瘦,还反复发烧"])
             if x.rule_id == "symptoms.red_flag_persistent_warning")
    assert a.requires_medical_attention


def test_no_false_positive_on_benign_symptoms():
    # 普通鼻塞/轻微头痛不应触发任何症状级急症红线
    sym_ids = {i for i in _ids(_run(["鼻塞流涕", "轻微头痛", "嗓子有点痒"]))
               if i.startswith("symptoms.")}
    assert sym_ids == set()
    assert _ids(_run([])) == _ids(_run([]))  # 空症状不崩


def test_worldview_blob_content():
    blob = worldview_prompt_blob(include_triage=True)
    assert "修复速率≥损伤速率" in blob
    assert "私人健康秘书" in blob
    assert "胸痛" in blob and "卒中" in blob  # 红线在
    # 不带 triage 时红线不出现
    assert "卒中" not in worldview_prompt_blob(include_triage=False)
