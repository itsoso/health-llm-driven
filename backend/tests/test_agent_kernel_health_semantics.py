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
        "查询我的用药记录，看看医生不允许我吃什么",
    ),
)
def test_v45_read_followed_by_health_assessment_remains_active(text):
    assert semantics.resolve_health_read_act(text).status == "active"


@pytest.mark.parametrize("self_owner", ("我", "本人", "我自己", "我个人", "我本人"))
@pytest.mark.parametrize(
    ("scope", "entity"),
    (
        ("今天", "血压"),
        ("最近", "血压"),
        ("今早", "血压"),
        ("晨起", "血压"),
        ("服药后", "血压"),
        ("午后", "血压"),
        ("夜间", "睡眠"),
        ("起床后", "体重"),
    ),
)
def test_v45_explicit_self_temporal_owner_is_current_user(
    self_owner,
    scope,
    entity,
):
    assert semantics.health_read_has_nonself_subject(
        f"查询{self_owner}{scope}的{entity}记录"
    ) is False


@pytest.mark.parametrize("scope", ("刚测", "刚刚测", "刚测量", "刚刚测量"))
def test_v45_recent_measurement_scope_defaults_to_current_user(scope):
    assert semantics.health_read_has_nonself_subject(
        f"查询{scope}的血压记录"
    ) is False


def test_v45_metric_interpretation_is_not_command_meta_discussion():
    assert semantics.resolve_health_read_act(
        "查询我的化验记录，看看这些指标意味着什么"
    ).status == "active"


@pytest.mark.parametrize(
    "meta_object",
    ("这句话", "这个指令", "该指令", "这次查询"),
)
@pytest.mark.parametrize(
    "meaning_phrase",
    ("意味着什么", "是什么意思", "是啥意思", "什么意思"),
)
def test_v45_later_command_meta_discussion_revokes_read(
    meta_object,
    meaning_phrase,
):
    assert semantics.resolve_health_read_act(
        f"查询我的痛风记录，看看{meta_object}{meaning_phrase}"
    ).status != "active"


@pytest.mark.parametrize("meaning_phrase", ("意味着什么", "是什么意思", "是啥意思", "什么意思"))
def test_v45_metric_meaning_synonyms_remain_active(meaning_phrase):
    assert semantics.resolve_health_read_act(
        f"查询我的化验记录，看看这些指标{meaning_phrase}"
    ).status == "active"


@pytest.mark.parametrize(
    "meaning_phrase",
    ("啥意思", "是什么含义", "含义是什么", "代表什么", "怎么理解", "什么意思呢", "是什么意思啊"),
)
def test_v45_adjacent_command_meta_meanings_revoke_read(meaning_phrase):
    assert semantics.resolve_health_read_act(
        f"查询我的痛风记录，看看这个指令{meaning_phrase}"
    ).status != "active"


@pytest.mark.parametrize(
    "meaning_phrase",
    ("啥意思", "是什么含义", "含义是什么", "代表什么", "怎么理解", "什么意思呢", "是什么意思啊"),
)
def test_v45_adjacent_metric_meanings_remain_active(meaning_phrase):
    assert semantics.resolve_health_read_act(
        f"查询我的化验记录，看看这些指标{meaning_phrase}"
    ).status == "active"


@pytest.mark.parametrize(
    "meta_object",
    ("这个命令", "这条命令", "该命令", "这个请求"),
)
def test_v45_adjacent_meta_object_variants_revoke_read(meta_object):
    assert semantics.resolve_health_read_act(
        f"查询我的痛风记录，看看{meta_object}是什么意思"
    ).status != "active"


@pytest.mark.parametrize(
    "meta_object",
    ("指令", "命令", "请求", "查询", "操作"),
)
def test_v45_bare_meta_objects_revoke_read(meta_object):
    assert semantics.resolve_health_read_act(
        f"查询我的痛风记录，看看{meta_object}怎么理解"
    ).status != "active"


@pytest.mark.parametrize(
    "meta_clause",
    ("指令是什么意思", "这个命令指的是什么", "请求怎么理解", "操作有什么用途"),
)
def test_v45_meta_clause_without_lead_in_revokes_read(meta_clause):
    assert semantics.resolve_health_read_act(
        f"查询我的痛风记录，{meta_clause}"
    ).status != "active"


def test_v45_unpunctuated_metric_interpretation_remains_active():
    assert semantics.resolve_health_read_act(
        "查询我的化验记录看看这些指标是什么意思"
    ).status == "active"


@pytest.mark.parametrize(
    "text",
    (
        "查询我的痛风记录，看看这个命令指的是什么",
        "查询我的痛风记录，看看这段话是什么意思",
        "查询我的痛风记录，看看此命令是什么意思",
        "查询我的痛风记录，看看上述指令怎么理解",
    ),
)
def test_v45_extended_meta_object_and_intent_axes_revoke_read(text):
    assert semantics.resolve_health_read_act(text).status != "active"


@pytest.mark.parametrize(
    "text",
    (
        "查询我的痛风记录，这个指令是什么意思",
        "查询我的痛风记录，请解释这个指令是什么意思",
        "查询我的痛风记录，看看这个指令表达什么",
        "查询我的痛风记录，看看这番话是什么意思",
    ),
)
def test_v45_additional_meta_scaffolds_objects_and_intents_revoke_read(text):
    assert semantics.resolve_health_read_act(text).status != "active"


@pytest.mark.parametrize("metric_object", ("这些指标", "这些数值", "这些读数"))
def test_v45_unpunctuated_metric_object_variants_remain_active(metric_object):
    assert semantics.resolve_health_read_act(
        f"查询我的化验记录看看{metric_object}是什么意思"
    ).status == "active"


@pytest.mark.parametrize(
    "metric_object",
    ("这些结果", "这些化验结果", "这些测量值", "这些检测值", "这些数据"),
)
def test_v45_adjacent_clinical_data_objects_remain_active(metric_object):
    assert semantics.resolve_health_read_act(
        f"查询我的化验记录看看{metric_object}是什么意思"
    ).status == "active"


@pytest.mark.parametrize(
    "text",
    (
        "查询我的痛风记录，请解释这个指令",
        "查询我的痛风记录，请解释这番话",
        "查询我的痛风记录，查询表达什么",
        "我想了解这个指令是什么意思",
        "告诉我这个命令啥意思",
        "看看这个指令怎么用",
        "看看这个请求怎么执行",
    ),
)
def test_v45_additional_meta_intent_forms_are_non_authorizing(text):
    assert semantics.resolve_health_read_act(text).status != "active"


@pytest.mark.parametrize(
    "meta_text",
    (
        "这条指令该怎么操作",
        "上面的指令是什么意思",
        "下面这条命令是什么意思",
        "刚才的命令是什么意思",
        "这个提示词是什么意思",
        "这段查询是什么意思",
        "该查询会查什么",
        "这句话说的是啥",
        "帮我分析这个命令",
        "请说明这个指令",
        "当前查询有何用途",
        "这段文字是什么意思",
        "这个表达什么意思",
        "“本次结果”这个说法什么意思",
        "解释“报告数值”的用法",
        "看看“这些指标”这几个字是什么意思",
    ),
)
def test_v45_meta_command_language_never_authorizes_health_read(meta_text):
    text = f"查询我的化验记录，{meta_text}"
    assert semantics.is_health_tool_meta_command(text)
    assert semantics.resolve_health_read_act(text).status != "active"


def test_v45_third_party_clinical_interpretation_is_not_current_user():
    assert semantics.is_clinical_result_interpretation(
        "查询Alice的检查记录，看看这些数据是什么意思"
    ) is False


@pytest.mark.parametrize(
    "text",
    (
        "查询检查记录，这是Alice的，看看这些数据是什么意思",
        "MIA2的体检报告，帮我看看这些数据是什么意思",
        "查询CACHE-1的化验报告，看看本次结果是什么意思",
        "查询USER123检验报告，看看报告数值代表什么",
        "帮小王查询检查报告，看看上述检查结果是什么意思",
        "查询李雷刚导入的医学检查报告，看看这些数据是什么意思",
        "查询刚导入的租户42报告，看看本次结果是什么意思",
        "患者甲的检查结果，帮我看看这些数据是什么意思",
        "我朋友的检查记录，帮我看看这些数据是什么意思",
        "妈妈的体检报告，帮我看看这些数据是什么意思",
    ),
)
def test_v45_natural_third_party_report_forms_are_nonself(text):
    assert semantics.has_explicit_nonself_health_owner(text)
    assert semantics.health_read_has_nonself_subject(text)
    assert semantics.is_clinical_result_interpretation(text) is False


def test_v45_unresolved_record_clinical_interpretation_is_not_resolved():
    assert semantics.is_clinical_result_interpretation(
        "查询上一条化验记录，看看这些结果是什么意思"
    ) is False


@pytest.mark.parametrize(
    "text",
    (
        "查询这条化验记录，看看上述数据是什么意思",
        "查询末条化验记录，看看这些结果是什么意思",
        "查询第卌份化验记录，看看这些检查结果是什么意思",
        "查询先前那份化验记录，看看这些结果是什么意思",
    ),
)
def test_v45_adjacent_unresolved_clinical_references_remain_unresolved(text):
    assert semantics.is_unresolved_health_reference(text)
    assert semantics.is_unresolved_health_reference(
        semantics.clinical_interpretation_query_scope(text)
    )
    assert semantics.is_clinical_result_interpretation(text) is False


@pytest.mark.parametrize(
    "pointer",
    (
        "第一次化验记录",
        "第二次化验记录",
        "第十次化验记录",
        "最近一次化验记录",
        "最新一条化验记录",
        "最早一次化验记录",
        "末次化验记录",
        "这次化验记录",
        "那次化验记录",
        "某次化验记录",
        "上述那次化验记录",
        "前述那条化验记录",
        "刚才那次化验记录",
    ),
)
def test_v45_generic_record_selection_is_unresolved(pointer):
    assert semantics.is_unresolved_health_reference(f"查询{pointer}")


@pytest.mark.parametrize(
    "text",
    (
        "查询我的化验记录，这些结果是什么意思",
        "查询我的化验记录这些结果是什么意思",
    ),
)
def test_v45_clinical_interpretation_does_not_require_kankan_scaffold(text):
    assert semantics.is_clinical_result_interpretation(text)


@pytest.mark.parametrize(
    "veto",
    ("不允许", "不同意", "未同意", "没有批准", "不授权"),
)
def test_v45_bare_trailing_veto_revokes_read_authority(veto):
    assert semantics.resolve_health_read_act(
        f"查询我的痛风记录，{veto}"
    ).status != "active"
