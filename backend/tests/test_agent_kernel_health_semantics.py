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

    assert payload["version"] == "health-semantics-v7"
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


@pytest.mark.parametrize(
    "entity",
    (
        "免疫球蛋白A肾病",
        "原发性中枢神经系统淋巴瘤",
        "慢性炎症性脱髓鞘性多发性神经病",
        "遗传性出血性毛细血管扩张症",
        "亨廷顿病",
        "脊髓小脑性共济失调",
        "显微镜下多血管炎",
        "抗NMDA受体脑炎",
        "IgG4相关性疾病",
        "HLA-B27相关脊柱关节炎",
        "BCR::ABL1阳性白血病",
        "β2微球蛋白淀粉样变性",
    ),
)
def test_v41_compositional_and_terminology_backed_disease_is_exact(entity):
    assert semantics.resolve_illness_entity(entity).status == "exact"


@pytest.mark.parametrize(
    "entity",
    (
        "尿蛋白异常",
        "血小板异常",
        "红蛋白异常",
        "淋巴细胞异常",
        "血管异常",
        "胆汁异常",
        "心肌细胞异常",
        "免疫细胞异常",
    ),
)
def test_v41_indicator_abnormality_is_not_an_illness_entity(entity):
    assert semantics.resolve_illness_entity(entity).status == "nonhealth"


@pytest.mark.parametrize(
    "text",
    (
        "查询我的房颤记录，打住",
        "暂缓查看我的糖尿病记录",
        "不用继续查询我的痛风记录",
        "我的哮喘记录查到这儿",
        "把我的糖尿病记录查询撤了吧",
    ),
)
def test_v41_structured_read_act_resolves_more_cancellations(text):
    resolution = semantics.resolve_health_read_act(text)

    assert resolution.status == "cancelled"
    assert resolution.active_clause == ""
    assert semantics.health_read_cancelled(text) is True


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("查询老师的房颤，打住；再查我自己的房颤", "查我自己的房颤"),
        ("暂缓调取同事的MRI，不过查看我的左膝MRI", "查看我的左膝MRI"),
        ("不用继续查询室友痛风；然后查询我的痛风", "查询我的痛风"),
    ),
)
def test_v41_structured_read_act_keeps_later_self_clause(text, expected):
    resolution = semantics.resolve_health_read_act(text)

    assert resolution.status == "active"
    assert resolution.active_clause == expected
    assert semantics.health_read_cancelled(text) is False


def test_v41_contract_digest_changes_when_authorization_function_changes(monkeypatch):
    before = semantics.health_semantics_contract_payload()["content_digest"]

    monkeypatch.setattr(semantics, "health_read_cancelled", lambda _text: False)

    assert semantics.health_semantics_contract_payload()["content_digest"] != before


@pytest.mark.parametrize(
    "entity",
    (
        "Mia显微镜下多血管炎",
        "Noah免疫球蛋白A肾病",
        "AvaIgG4相关性疾病",
        "LeoHLA-B27相关脊柱关节炎",
        "Noahβ2微球蛋白淀粉样变性",
        "CACHE血管炎",
        "API肾病",
        "MODEL脑炎",
        "SERVER血管炎",
        "INDEX神经病",
        "QUEUE肺炎",
        "ROUTER胆管炎",
        "HTTP肠炎",
        "CPU肌病",
        "GPU脑病",
        "QA肺病",
    ),
)
def test_v42_ascii_owner_or_system_prefix_is_not_open_illness_authority(entity):
    assert semantics.resolve_illness_entity(entity).status != "exact"


@pytest.mark.parametrize(
    "entity",
    (
        "MIA2显微镜下多血管炎",
        "LI-1显微镜下多血管炎",
        "ANA::1显微镜下多血管炎",
        "API2显微镜下多血管炎",
        "CACHE-1显微镜下多血管炎",
        "R2D2显微镜下多血管炎",
        "MIA2痛风",
        "HTTP2痛风",
        "MODEL7脑膜炎",
    ),
)
def test_v43_biomedical_shaped_owner_prefix_cannot_borrow_disease_tail(entity):
    assert semantics.resolve_illness_entity(entity).status != "exact"


@pytest.mark.parametrize(
    "entity",
    (
        "显微镜下多血管炎",
        "HLA-B27相关脊柱关节炎",
        "MOG抗体相关疾病",
        "EB病毒感染",
        "Sjögren综合征",
        "Guillain-Barré综合征",
        "α1抗胰蛋白酶缺乏症",
        "C3肾小球病",
        "PLA2R相关膜性肾病",
        "抗MDA5阳性皮肌炎",
        "抗LGI1抗体脑炎",
        "抗磷脂酶A2受体阳性膜性肾病",
        "NTRK融合阳性实体瘤",
        "MPL-W515L阳性骨髓增殖性肿瘤",
        "HLA-DQ2.5相关乳糜泻",
        "anti-MDA5阳性皮肌炎",
        "GFAP-IgG阳性星形胶质细胞病",
        "SYNGAP1相关神经发育障碍",
        "PIGA相关阵发性睡眠性血红蛋白尿",
        "C9orf72相关额颞叶痴呆",
        "PR3-ANCA阳性肉芽肿性多血管炎",
        "A20单倍剂量不足综合征",
        "ADA2缺乏症",
        "NLRP3相关自身炎症性疾病",
        "PAX6相关无虹膜症",
        "LAM-TSC2相关肺淋巴管肌瘤病",
        "WT1相关肾病综合征",
        "MOG-IgG相关皮质脑炎",
        "抗GAD65自身免疫性脑炎",
        "LAMP2抗体相关坏死性肾小球肾炎",
        "m.3243A>G相关MELAS综合征",
    ),
)
def test_v42_versioned_biomedical_terminology_is_exact(entity):
    assert semantics.resolve_illness_entity(entity).status == "exact"


@pytest.mark.parametrize(
    "entity",
    (
        "ALK融合阳性肺癌",
        "EGFR-L858R阳性肺腺癌",
        "ROS1融合阳性肺癌",
        "RET融合阳性甲状腺癌",
        "JAK2-V617F阳性真性红细胞增多症",
        "CALR外显子9突变骨髓增殖性肿瘤",
        "FGFR3融合阳性膀胱癌",
        "IDH1-R132H阳性胶质瘤",
        "H3K27M弥漫性中线胶质瘤",
        "NPM1突变急性髓系白血病",
        "FLT3-ITD阳性急性髓系白血病",
        "BRCA1相关遗传性乳腺癌",
        "LMNA相关扩张型心肌病",
        "SCN5A相关Brugada综合征",
        "TSC1相关结节性硬化症",
        "HTT-CAG重复扩增亨廷顿病",
        "SMN1相关脊髓性肌萎缩症",
        "ATP7B相关威尔逊病",
        "PKD1相关常染色体显性多囊肾病",
        "anti-GBM抗体病",
        "AQP4-IgG阳性视神经脊髓炎谱系病",
        "NMOSD",
        "Duchenne型肌营养不良",
        "MYH7相关肥厚型心肌病",
        "KCNQ1相关长QT综合征",
        "RYR1相关恶性高热易感症",
        "ABCD1相关X连锁肾上腺脑白质营养不良",
        "COL4A5相关Alport综合征",
        "VHL相关肿瘤综合征",
        "MEN2A型多发性内分泌腺瘤病",
        "APOL1相关肾病",
        "BRAF-V600E阳性黑色素瘤",
        "FBN1相关马凡综合征",
        "GBA1相关帕金森病",
        "HLA-B51相关Behçet病",
    ),
)
def test_v43_versioned_biomedical_registry_accepts_reviewed_entities(entity):
    assert semantics.resolve_illness_entity(entity).status == "exact"


@pytest.mark.parametrize(
    "text",
    (
        "先别查老师的痛风；明天再查我的房颤记录",
        "暂缓查看同事MRI；稍后再打开我的左膝MRI",
        "查询我的克雅氏病记录，先别继续了",
        "查看我的痛风记录，暂且作罢",
        "列出我的亨廷顿病记录，先缓一缓",
    ),
)
def test_v42_deferred_or_trailing_cancelled_read_has_no_active_clause(text):
    assert semantics.active_health_read_clause(text) == ""
    assert semantics.health_read_cancelled(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "我的痛风记录已经查询完成",
        "查看我的痛风记录已经完成",
        "查我的痛风记录这件事已经结束了",
        "查询我的痛风记录只是一个示例",
        "查询我的痛风记录这句话来自教程",
        "查询我的痛风记录会发生什么",
    ),
)
def test_v42_completed_reported_or_hypothetical_read_is_not_active(text):
    assert semantics.resolve_health_read_act(text).status == "none"


@pytest.mark.parametrize(
    "text",
    (
        "查询我的痛风记录，先放一放",
        "查询我的痛风记录，晚点再说",
        "查询我的痛风记录，先等等",
        "查询我的痛风记录，暂时不用",
        "查询我的痛风记录，回头再说",
        "查询我的痛风记录已经做完了",
        "我的痛风记录查完了",
        "查询我的痛风记录早就结束了",
        "查询我的痛风记录刚完成",
        "查询我的痛风记录是测试用例",
        "查询我的痛风记录仅供演示",
        "查询我的痛风记录只是为了测试",
        "查询我的痛风记录是文档里的命令",
        "查询我的痛风记录的话会怎么样",
        "查询我的痛风记录会不会有结果",
        "查询我的痛风记录是假设，不要执行",
        "查询我的痛风记录？不，这是测试",
        "查询我的痛风记录是反例",
        "查询我的痛风记录是否安全",
    ),
)
def test_v43_non_authorizing_read_language_has_no_active_clause(text):
    assert semantics.resolve_health_read_act(text).status != "active"
    assert semantics.active_health_read_clause(text) == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("前一个查询已经完成；现在查询我的房颤记录", "查询我的房颤记录"),
        ("明天再查痛风记录，现在先查我的房颤记录", "查我的房颤记录"),
    ),
)
def test_v43_later_active_read_survives_prior_completed_or_deferred_clause(
    text,
    expected,
):
    resolution = semantics.resolve_health_read_act(text)

    assert resolution.status == "active"
    assert resolution.active_clause == expected


def test_v42_semantic_digest_is_stable_after_authorization_execution():
    before = semantics.health_semantics_contract_payload()["content_digest"]

    for _ in range(100):
        semantics.resolve_illness_entity("HLA-B27相关脊柱关节炎")
        semantics.resolve_health_read_act("查询我的克雅氏病记录")

    assert semantics.health_semantics_contract_payload()["content_digest"] == before


def test_v42_semantic_digest_tracks_transitive_local_helper(monkeypatch):
    before = semantics.health_semantics_contract_payload()["content_digest"]

    monkeypatch.setattr(semantics, "has_positive_health_read_verb", lambda _text: False)

    assert semantics.health_semantics_contract_payload()["content_digest"] != before


@pytest.mark.parametrize(
    "text",
    (
        "查询我的痛风记录完成了",
        "查询我的痛风记录结束了",
        "查询我的痛风记录做完了",
        "查询我的痛风记录搞定了",
        "查询我的痛风记录，改天再说",
        "查询我的痛风记录，等会儿再说",
        "查询我的痛风记录，到时候再说",
        "查询我的痛风记录，这是个例子",
        "查询我的痛风记录，这只是举例",
        "查询我的痛风记录，仅用于演示",
        "查询我的痛风记录是个测试用例",
        "查询我的痛风记录仅用于测试",
        "查询我的痛风记录是个假设",
        "查询我的痛风记录可能会返回什么",
        "查询我的痛风记录能得到什么结果",
        "查询我的痛风记录？不",
        "查询我的痛风记录，我没有授权",
        "查询我的痛风记录，但不要真的执行",
    ),
)
def test_v44_structural_non_authorizing_read_has_no_active_clause(text):
    resolution = semantics.resolve_health_read_act(text)

    assert resolution.status != "active"
    assert resolution.active_clause == ""


@pytest.mark.parametrize(
    "prefix",
    (
        "查询我的痛风记录完成了",
        "查询我的痛风记录，这是个例子",
        "查询我的痛风记录，改天再说",
        "查询我的痛风记录能得到什么结果",
    ),
)
def test_v44_later_explicit_read_restarts_after_meta_clause(prefix):
    resolution = semantics.resolve_health_read_act(
        f"{prefix}；现在查询我的房颤记录"
    )

    assert resolution.status == "active"
    assert resolution.active_clause == "查询我的房颤记录"


@pytest.mark.parametrize(
    "text",
    (
        "查询我的血压记录，看看是否安全",
        "查询我的血糖记录，看看会有什么影响",
        "查询我的体重记录，看看会怎样变化",
    ),
)
def test_v44_query_then_health_assessment_remains_active(text):
    assert semantics.resolve_health_read_act(text).status == "active"


@pytest.mark.parametrize("owner", ("Alice", "MIA2", "CACHE-1", "小王"))
@pytest.mark.parametrize("entity", ("血压", "体重", "睡眠", "用药"))
def test_v44_generic_health_domain_explicit_other_owner_is_nonself(owner, entity):
    assert semantics.health_read_has_nonself_subject(
        f"查询{owner}的{entity}记录"
    ) is True


@pytest.mark.parametrize("owner", ("Alice", "MIA2", "CACHE-1", "小王"))
@pytest.mark.parametrize("entity", ("血压", "体重", "睡眠", "用药"))
def test_v44_generic_health_domain_concatenated_other_owner_is_nonself(owner, entity):
    assert semantics.health_read_has_nonself_subject(
        f"查询{owner}{entity}记录"
    ) is True


@pytest.mark.parametrize(
    "text",
    (
        "查询我的痛风记录？不用",
        "查询我的痛风记录？我没让你查",
        "查询我的痛风记录纯属假设",
        "查询我的痛风记录仅作测试",
        "查询我的痛风记录不代表要执行",
        "查询我的痛风记录，我没同意",
        "查询我的痛风记录，我不允许",
        "查询我的痛风记录，我拒绝",
        "查询我的痛风记录，别真的查",
        "查询我的痛风记录？不是",
        "查询我的痛风记录？并不是",
        "查询我的痛风记录？没有这个意思",
        "查询我的痛风记录意味着什么",
        "查询我的痛风记录仅供参考",
        "查询我的痛风记录不是让你真的查",
        "查询我的痛风记录？否",
        "查询我的痛风记录？No",
        "查询我的痛风记录，先不要",
        "查询我的痛风记录，不用了",
        "查询我的痛风记录，不必了",
        "查询我的痛风记录，没必要",
        "查询我的痛风记录只是举个例子",
        "查询我的痛风记录作为示例",
        "查询我的痛风记录，过两天再说",
        "查询我的痛风记录，晚些时候再说",
        "查询我的痛风记录，有空再说",
        "查询我的痛风记录会返回哪些数据",
        "查询我的痛风记录会不会成功",
        "查询我的痛风记录，我没授权",
        "查询我的痛风记录，我不同意",
        "查询我的痛风记录，未经我同意",
    ),
)
def test_v44_generalized_read_veto_resets_authority(text):
    assert semantics.resolve_health_read_act(text).status != "active"


@pytest.mark.parametrize(
    "scope",
    (
        "今早",
        "晨起",
        "运动后",
        "服药后",
        "睡前",
        "起床后",
        "午后",
        "夜间",
    ),
)
def test_v44_temporal_scope_is_not_an_other_owner(scope):
    entity = "体重" if scope in {"睡前", "起床后"} else "血压"
    assert semantics.health_read_has_nonself_subject(
        f"查询{scope}的{entity}记录"
    ) is False


@pytest.mark.parametrize("owner", ("小明", "妈妈", "Alice", "MIA2", "朋友"))
@pytest.mark.parametrize("scope", ("今早", "运动后", "早餐后", "晚上", "睡前"))
@pytest.mark.parametrize(
    "template",
    (
        "查询{owner}{scope}的血压记录",
        "查询{owner}的{scope}血压记录",
    ),
)
def test_v45_temporal_scope_does_not_hide_an_other_owner(owner, scope, template):
    assert semantics.health_read_has_nonself_subject(
        template.format(owner=owner, scope=scope)
    ) is True


@pytest.mark.parametrize(
    "text",
    (
        "查询我的血压记录，看看哪些运动不允许",
        "查询我的痛风记录，看看治疗会不会成功",
    ),
)
def test_v45_read_followed_by_health_assessment_remains_active(text):
    assert semantics.resolve_health_read_act(text).status == "active"
