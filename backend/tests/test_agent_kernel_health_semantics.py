"""Direct contract tests for owner-scoped health entity resolution."""

import re

import pytest

from app.services.agent_kernel import health_semantics as semantics


@pytest.mark.parametrize(
    "entity",
    (
        "格林-巴利综合征",
        "吉兰-巴雷综合征",
        "埃勒斯-当洛斯综合征",
        "库欣综合征",
        "抗磷脂综合征",
        "Rett综合征",
        "Goodpasture综合征",
        "Shwachman-Diamond综合征",
        "Brugada综合征",
        "Lambert-Eaton综合征",
        "韦格纳肉芽肿",
        "肠易激综合征",
        "缺铁性贫血",
        "幽门螺杆菌感染",
        "阵发性房颤",
    ),
)
def test_v39_long_tail_disease_is_medical_and_current_user_eligible(entity):
    assert semantics.illness_entity_has_medical_semantics(entity) is True
    assert semantics.illness_target_is_unowned_or_referential(entity) is False


@pytest.mark.parametrize(
    "entity",
    (
        "欧阳锋多发性硬化症",
        "司徒兰胶质母细胞瘤",
        "Xavier脑膜炎",
        "Müller皮肌炎",
        "Nguyen系统性硬化症",
        "Иван脑膜炎",
        "产品经理脑膜炎",
        "咖啡师黑色素瘤",
        "合租人多发性硬化症",
        "我舅爷脑膜炎",
        "远房表叔强直性脊柱炎",
        "咱爸心肌炎",
        "Quinn白血病",
        "زید脑膜炎",
        "李雷罕见神经炎",
        "健身搭档心肌炎",
        "儿科主任皮肌炎",
        "社群管理员白血病",
        "未婚夫骨髓炎",
        "旅行团领队脑膜炎",
    ),
)
def test_v39_unpunctuated_third_party_disease_target_is_unowned(entity):
    assert semantics.illness_target_is_unowned_or_referential(entity) is True


@pytest.mark.parametrize(
    "entity",
    (
        "路由器异常",
        "构建异常",
        "模型异常",
        "任务异常",
        "集群异常",
        "网关障碍",
        "账号障碍",
        "脚本炎",
        "表单癌",
        "页面瘤",
        "音箱疹",
        "GPU异常",
        "JSON异常",
        "Kafka异常",
        "队列炎",
        "证书癌",
        "血糖异常",
        "ALT异常",
    ),
)
def test_v39_nonhealth_or_metric_suffix_collision_is_not_illness(entity):
    assert semantics.illness_entity_has_medical_semantics(entity) is False


@pytest.mark.parametrize(
    "reference",
    (
        "从后往前第二张MRI报告",
        "倒数第二新MRI",
        "前面数来第四张CT",
        "最下面一张CT",
        "第N份CT",
        "第Ⅲ份MRI",
        "头一份MRI",
        "第卌份MRI",
    ),
)
def test_v39_generalized_health_reference_is_unresolved(reference):
    assert semantics.is_unresolved_health_reference(reference) is True


@pytest.mark.parametrize(
    "text",
    (
        "查Xavier脑膜炎记录",
        "查产品经理脑膜炎记录",
        "调出Ольга左膝MRI报告",
        "查看José左膝DWI/ADC MRI",
        "调出ИванL4/5腰椎CT",
        "展示产品经理3.0T脑部MRI",
    ),
)
def test_v39_unpunctuated_third_party_health_read_is_nonself(text):
    assert semantics.health_read_has_nonself_subject(text) is True


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("撤掉张三MRI查询；然后查我的DWI/ADC脑MRI", "查我的DWI/ADC脑MRI"),
        ("取消老师房颤查询，改查我自己的房颤记录", "改查我自己的房颤记录"),
        ("作废José CT查询；请展示我的L4/5腰椎MRI", "展示我的L4/5腰椎MRI"),
    ),
)
def test_v39_active_read_clause_selects_later_current_user_request(text, expected):
    clause = semantics.active_health_read_clause(text)
    assert clause == expected
    assert semantics.health_read_cancelled(text) is False


@pytest.mark.parametrize(
    ("text", "keyword"),
    (
        ("查我的DWI/ADC脑MRI影像", "DWI/ADC脑MRI"),
        ("查我自己的L4/5腰椎MRI报告", "L4/5腰椎MRI"),
        ("查3.0T脑部MRI结果", "3.0T脑部MRI"),
        ("查T2-FLAIR MRI影像", "T2-FLAIR MRI"),
        ("查T2* GRE MRI图像", "T2* GRE MRI"),
        ("查ADC/DWI头颅MRI图像", "ADC/DWI头颅MRI"),
    ),
)
def test_v39_medical_exam_resolution_preserves_exact_current_user_keyword(
    text,
    keyword,
):
    resolution = semantics.resolve_medical_exam_query(text)
    assert resolution.status == "exact"
    assert resolution.entity == keyword


@pytest.mark.parametrize(
    "text",
    (
        "查张三MRI报告",
        "查看José左膝DWI/ADC MRI",
        "调出ИванL4/5腰椎CT",
        "查询我合租人C5-C6颈椎MRI",
        "展示产品经理3.0T脑部MRI",
        "把咖啡师T2-FLAIR MRI发我",
    ),
)
def test_v39_medical_exam_resolution_rejects_unpunctuated_nonself_subject(text):
    assert semantics.resolve_medical_exam_query(text).status == "nonself"


def test_v39_health_semantics_contract_is_versioned_and_content_digested():
    payload = semantics.health_semantics_contract_payload()

    assert payload["version"] == "health-semantics-v1"
    assert re.fullmatch(r"[0-9a-f]{64}", payload["content_digest"])
