"""症状级急症红线 + 世界观注入。钉:危急组合命中 CRITICAL;无症状/普通症状不误报。"""
from datetime import datetime

from app.agents.safety_guardian.engine import evaluate_rules
from app.agents.safety_guardian.schema import Severity
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
