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

    assert payload["version"] == "health-semantics-v2"
    assert re.fullmatch(r"[0-9a-f]{64}", payload["content_digest"])


@pytest.mark.parametrize(
    "entity",
    (
        "结节性多动脉炎",
        "遗传性血管性水肿",
        "阵发性睡眠性血红蛋白尿",
        "成人斯蒂尔病",
        "原发性醛固酮增多症",
        "克雅氏病",
        "特发性血小板减少性紫癜",
        "贝赫切特病",
        "法布雷病",
        "戈谢病",
        "庞贝病",
        "威尔逊病",
        "美尼尔病",
        "Still病",
        "β-地中海贫血",
        "COVID‑19肺炎",
        "HER2+乳腺癌",
        "NMO谱系病",
        "CADASIL病",
        "原发性主动脉炎",
        "肉芽肿性多血管炎",
        "嗜酸性粒细胞性多血管炎",
        "视神经脊髓炎",
        "进行性核上性麻痹",
        "结节病",
        "原发性硬化性胆管炎",
        "系统性淀粉样变性",
        "多系统萎缩",
    ),
)
def test_v40_long_tail_and_unicode_disease_is_exact(entity):
    resolution = semantics.resolve_illness_entity(entity)

    assert resolution.status == "exact"


@pytest.mark.parametrize(
    "entity",
    (
        "Avery类风湿关节炎",
        "Олег桥本甲状腺炎",
        "Σωκράτης原发性胆汁性胆管炎",
        "共同监护人类风湿关节炎",
        "临时照护人原发性胆汁性胆管炎",
        "زید结节性多动脉炎",
    ),
)
def test_v40_arbitrary_owner_prefix_never_resolves_as_exact_illness(entity):
    assert semantics.resolve_illness_entity(entity).status != "exact"
    assert semantics.illness_target_is_unowned_or_referential(entity) is True


@pytest.mark.parametrize(
    "entity",
    (
        "神经网络异常",
        "遗传算法炎",
        "病毒扫描癌",
        "血管拓扑异常",
        "免疫缓存综合征",
    ),
)
def test_v40_nonhealth_compound_with_clinical_tokens_is_not_illness(entity):
    assert semantics.resolve_illness_entity(entity).status == "nonhealth"


@pytest.mark.parametrize(
    "text",
    (
        "查询我的房颤记录到此为止",
        "查看我的糖尿病记录这事先搁一搁",
        "我的偏头痛病历别再调了",
        "我的痛风查询作罢",
        "叫停我的哮喘记录查询",
    ),
)
def test_v40_postpositive_or_synonym_read_cancellation_has_no_active_clause(text):
    assert semantics.health_read_cancelled(text) is True
    assert semantics.active_health_read_clause(text) == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("撤回同事痛风查询；再查我自己的痛风", "查我自己的痛风"),
        ("不再打开老师房颤病历，不过查询我的房颤记录", "查询我的房颤记录"),
        ("查询室友哮喘到此为止，不过仅翻看我的哮喘记录", "翻看我的哮喘记录"),
        ("叫停José CT查询，然后调出我的DWI脑MRI", "调出我的DWI脑MRI"),
    ),
)
def test_v40_cancelled_clause_preserves_later_explicit_self_read(text, expected):
    assert semantics.active_health_read_clause(text) == expected
    assert semantics.health_read_cancelled(text) is False


@pytest.mark.parametrize(
    ("name", "replacement"),
    (
        ("THIRD_PARTY_ROLE_RE", re.compile(r"$^")),
        ("UNRESOLVED_HEALTH_REFERENCE_RE", re.compile(r"$^")),
        ("BARE_DEICTIC_REFERENCE_RE", re.compile(r"$^")),
        ("_READ_SCOPE_BOUNDARY_RE", re.compile(r"$^")),
    ),
)
def test_v40_contract_digest_changes_with_every_shared_authorization_regex(
    monkeypatch,
    name,
    replacement,
):
    before = semantics.health_semantics_contract_payload()["content_digest"]

    monkeypatch.setattr(semantics, name, replacement)

    assert semantics.health_semantics_contract_payload()["content_digest"] != before
