import pytest

from app.services.utterance_intent_lexicon import WRITE_COMMAND_ACTIONS
from app.services.write_intent_scope import (
    _event_fact_has_non_current_subject,
    authorized_health_record_clauses,
    has_explicit_authorizing_write_request,
    has_negated_write_scope,
    is_historical_write_reference,
    is_read_action_write_reference,
    is_reported_write_reference,
    is_write_capability_question,
    is_write_result_check,
    split_write_clauses,
    explicit_whole_record_delete_targets,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("删除饮食记录977和979", (("diet", 977), ("diet", 979))),
        (
            "我确认要整条删除饮食记录977和979，不是修改内容，是彻底删除这两条饮食记录",
            (("diet", 977), ("diet", 979)),
        ),
        ("把饮食记录718、719、718删掉", (("diet", 718), ("diet", 719))),
    ),
)
def test_explicit_whole_record_delete_targets_accepts_bounded_typed_batch(
    text: str,
    expected: tuple[tuple[str, int], ...],
) -> None:
    assert explicit_whole_record_delete_targets(text) == expected


@pytest.mark.parametrize(
    "text",
    (
        "删掉977和979",
        "删除记录977和979",
        "删除饮食记录977到979",
        "删除所有饮食记录977和979",
        "删除饮食记录977和饮水记录979",
        "删除饮水记录718和719",
        "我确认要整条删除饮食记录977和979，不是修改内容，是彻底删除这两条饮水记录",
        "删除饮食记录977和979的备注",
        "删除饮食记录1和2和3和4和5和6",
        "不要删除饮食记录977和979",
    ),
)
def test_explicit_whole_record_delete_targets_fails_closed_for_unsafe_batch(
    text: str,
) -> None:
    assert explicit_whole_record_delete_targets(text) == ()


@pytest.mark.parametrize(
    "text",
    (
        "记录口腔溃疡，算了吧不要记了",
        "记录体重71kg，撤销吧别记录了",
        "记录口腔溃疡，不，还是别记录了",
        "记录口腔溃疡，先等等，别记了",
        "等我确诊后再记录感冒",
        "等以后如果我确诊感冒，再记录感冒",
        "确诊后再记录感冒",
        "请记录朋友的感冒",
        "帮我记录我妈妈的血压120/80",
        "记录我朋友感冒",
        "我朋友感冒了，记录一下",
        "记录妈妈感冒",
        "我妈妈感冒了，记录一下",
    ),
)
def test_compound_revocation_deferred_condition_and_third_party_have_no_authorized_clause(
    text: str,
) -> None:
    assert authorized_health_record_clauses(text) == ()
    assert has_explicit_authorizing_write_request(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "记录饮水300ml，嗯，我改主意了，这次别弄了",
        "营养师透露我喝了300ml水",
        "假使我喝了300ml水，就帮我记录饮水300ml",
        "表妹体重71kg，记录一下",
        "岳父感冒了，帮忙记录感冒",
        "护士提及：帮我记录感冒",
        "客服转达的原话是：帮我记录感冒",
        "护士提及帮我记录感冒",
        "客服转达原话帮我记录感冒",
        "一旦我确诊感冒，就记录感冒",
        "等我有空的时候，帮我记录感冒",
        "记录饮水300ml，当我没说",
        "记录饮水300ml，忽略刚才那句",
        "我对象体重71kg，记录一下",
        "我对象感冒了，记录一下",
        "邻居感冒了，帮忙记录感冒",
        "小明感冒了，帮忙记录感冒",
        "张三体重71kg，记录一下",
        "我的朋友小明感冒了，记录一下",
        "王五喝了300ml水，记录一下",
        "我的同事李雷吃了米饭，记录午餐",
        "记录张三体重71kg",
        "请记录小明体重71kg",
        "记录小明感冒",
        "记录邻居感冒",
        "我感冒了同时小明体重71kg帮我记录一下",
        "医生建议我记录体重71kg",
        "小明让我记录体重71kg",
        "记录疾病：张三感冒",
        "记录上官婉儿感冒",
        "记录左丘明体重71kg",
        "小明还是有腰疼的症状",
        "记录小明右侧腰疼",
        "记录感冒，这是小明的",
        "记录感冒，这是我孩子的",
        "记录感冒，实际上是妈妈的",
        "记录感冒，不是我的，是小明的",
        "记录感冒，这条属于张三",
        "记录感冒，这个其实是小明的",
        "记录感冒，这条其实属于小明",
        "记录感冒，这不是我的而是小明的",
        "记录感冒，这其实是我孩子的",
    ),
)
def test_revoked_reported_hypothetical_and_third_party_frames_have_no_authority(
    text: str,
) -> None:
    assert authorized_health_record_clauses(text) == ()
    assert has_explicit_authorizing_write_request(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "记录感冒，这是我本人的",
        "记录感冒，这是我自己的",
        "记录感冒，这条属于我本人",
    ),
)
def test_posterior_current_user_ownership_keeps_authority(text: str) -> None:
    assert authorized_health_record_clauses(text)
    assert has_explicit_authorizing_write_request(text) is True


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("记录体重71kg，不对，改成70kg", "记录体重70kg"),
        ("记录口腔溃疡，不对，应该是感冒", "记录感冒"),
        ("记录体重71kg，口误，是70kg", "记录体重70kg"),
        ("记录感冒，抱歉说反了，是口腔溃疡", "记录口腔溃疡"),
    ),
)
def test_correction_replaces_the_superseded_authorized_clause(
    text: str,
    expected: str,
) -> None:
    assert authorized_health_record_clauses(text) == (expected,)


def test_negation_composes_across_bridges_and_all_write_actions() -> None:
    negations = ("不要", "不用", "无需", "先别", "暂不", "勿", "甭")
    bridges = (
        "让小巴帮我",
        "让系统帮我",
        "请小巴帮我",
        "默默帮我",
        "今后自动替我",
    )

    for negation in negations:
        for bridge in bridges:
            for action in WRITE_COMMAND_ACTIONS:
                text = f"{negation}{bridge}{action}口腔溃疡"
                assert has_negated_write_scope(text) is True, text


@pytest.mark.parametrize(
    "text",
    (
        "不用让小巴帮我记录口腔溃疡，分析一下原因",
        "不要让系统帮我记录口腔溃疡",
        "勿让小巴帮我记录晚餐，分析一下热量",
        "请不要主动帮我记录口腔溃疡",
        "不要默默帮我记录口腔溃疡",
        "别总是帮我记录口腔溃疡",
        "请勿擅自帮我记录口腔溃疡",
        "无须让系统帮我记录口腔溃疡",
        "禁止帮我记录口腔溃疡",
        "我拒绝让系统帮我记录口腔溃疡",
        "请停止帮我记录口腔溃疡",
        "避免帮我记录口腔溃疡",
        "我不愿意让小巴帮我记录口腔溃疡",
        "我没有授权小巴帮我记录口腔溃疡",
        "未授权系统帮我记录口腔溃疡",
        "不一定要记录口腔溃疡",
        "不一定需要记录口腔溃疡",
        "不要执行：记录一下口腔溃疡",
        "请勿执行以下操作：记录一下今天晚餐",
        "禁止：记录口腔溃疡",
        "我从未同意系统帮我记录口腔溃疡",
        "我没有同意小巴帮我记录口腔溃疡",
        "我从没允许系统帮我记录口腔溃疡",
        "我没让系统帮我记录口腔溃疡",
        "我从没想过让系统帮我记录口腔溃疡",
        "我并没有要求系统帮我记录口腔溃疡",
        "我不乐意让小巴帮我记录口腔溃疡",
        "我无意让小巴帮我记录口腔溃疡",
        "我反对让系统帮我记录口腔溃疡",
        "未经我同意小巴帮我记录口腔溃疡",
        "严禁以下行为：记录口腔溃疡",
        "不要执行以下行为：记录口腔溃疡",
    ),
)
def test_negation_scopes_over_arbitrary_helpers_before_write_action(text: str) -> None:
    assert has_negated_write_scope(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "可不可以记录口腔溃疡",
        "能不能帮我记录口腔溃疡",
        "要不要记录今天的晚餐",
        "该不该记录今天腰痛6分",
        "我上一次口腔溃疡是什么时候，最近半年分别有哪些记录",
        "别忘记记录口腔溃疡",
        "请勿忘记记录今天的晚餐",
        "不得不记录这次用药",
        "不能不记录这次用药",
        "不妨记录今天的感受",
        "我今天不舒服，帮我记录一下",
        "我今天不舒服帮我记录一下",
        "这次不严重，帮我记录下来",
        "不是很疼，帮我记录一下",
        "这几天不想吃东西但请记录食欲下降",
        "我不能集中注意力但帮我记录一下",
        "这几天不想吃东西：请记录食欲下降",
        "这几天不想吃东西只是请记录食欲下降",
        "记录过敏反应",
        "不需要分析，记录口腔溃疡",
        "不要分析；然后记录口腔溃疡",
        "别忘了记录口腔溃疡",
        "不要记错，记录口腔溃疡",
    ),
)
def test_modal_exception_and_clause_boundaries_do_not_negate_write(text: str) -> None:
    assert has_negated_write_scope(text) is False


def test_clause_split_normalizes_text_and_preserves_scope_boundaries() -> None:
    assert split_write_clauses(" 不需要分析， 然后记录口腔溃疡。 ") == (
        "不需要分析",
        "记录口腔溃疡",
    )


@pytest.mark.parametrize(
    "text",
    (
        "不想让小巴记录口腔溃疡",
        "不允许系统记录口腔溃疡",
        "不能记录口腔溃疡",
        "不许记录口腔溃疡",
        "不准记录口腔溃疡",
        "不应记录口腔溃疡",
        "不得记录口腔溃疡",
        "不再自动记录口腔溃疡",
        "不让小巴记录口腔溃疡",
        "不是要记录口腔溃疡",
        "不打算记录口腔溃疡",
        "不希望记录口腔溃疡",
        "不同意记录口腔溃疡",
        "不授权记录口腔溃疡",
    ),
)
def test_negating_control_predicates_scope_over_write_actions(text: str) -> None:
    assert has_negated_write_scope(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "请问小巴能帮我记录口腔溃疡吗？",
        "请问系统可以帮我记录口腔溃疡吗？",
        "我想问这个功能可以帮我记录口腔溃疡吗？",
        "我想知道小巴能不能帮我记录口腔溃疡",
        "请告诉我小巴能否帮我记录口腔溃疡",
        "系统是否会帮我记录口腔溃疡？",
        "小巴会帮我记录口腔溃疡吗？",
        "这个功能支持帮我记录口腔溃疡吗？",
        "系统有没有帮我记录口腔溃疡的功能？",
        "请问能否记录口腔溃疡？",
        "这个能帮我记录口腔溃疡吗？",
        "它能帮我记录口腔溃疡吗？",
        "该功能能否保存病症记录？",
    ),
)
def test_capability_questions_are_distinct_from_write_requests(text: str) -> None:
    assert is_write_capability_question(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "请确认小巴具备记录健康数据的能力",
        "请说明小巴具不具备记录口腔溃疡的能力",
        "请确认它会自动记录口腔溃疡",
    ),
)
def test_capability_complements_are_not_direct_requests(text: str) -> None:
    assert is_write_capability_question(text) is True
    assert has_explicit_authorizing_write_request(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "小巴，能帮我记录口腔溃疡吗？",
        "系统，帮我记录口腔溃疡",
        "能不能帮我记录口腔溃疡",
    ),
)
def test_direct_requests_are_not_capability_questions(text: str) -> None:
    assert is_write_capability_question(text) is False


def test_independent_denial_classes_compose_with_all_write_actions() -> None:
    denial_bridges = (
        "我拒绝让系统帮我",
        "禁止帮我",
        "请停止帮我",
        "避免帮我",
        "我不愿意让小巴帮我",
        "我没有授权小巴帮我",
        "未授权系统帮我",
    )

    for denial_bridge in denial_bridges:
        for action in WRITE_COMMAND_ACTIONS:
            text = f"{denial_bridge}{action}口腔溃疡"
            assert has_negated_write_scope(text) is True, text


def test_independent_history_frames_cover_all_write_actions() -> None:
    for history_lead in ("上次", "上回", "之前", "刚才"):
        for action in WRITE_COMMAND_ACTIONS:
            text = f"{history_lead}帮我{action}口腔溃疡了吗？"
            assert is_historical_write_reference(text) is True, text

    for action in WRITE_COMMAND_ACTIONS:
        text = f"你帮我{action}口腔溃疡了吗？"
        assert is_historical_write_reference(text) is True, text


@pytest.mark.parametrize(
    "text",
    (
        "记录口腔溃疡历史",
        "记录列表",
        "记录汇总",
        "保存过口腔溃疡吗？",
        "录入过口腔溃疡吗？",
        "新增过口腔溃疡吗？",
        "写入过口腔溃疡吗？",
        "打卡过口腔溃疡吗？",
        "上次帮我记录口腔溃疡了吗？",
        "上回帮我记录口腔溃疡了吗？",
        "之前帮我记录口腔溃疡了吗？",
        "刚才帮我记录口腔溃疡了吗？",
        "你帮我保存口腔溃疡了吗？",
        "你帮我记录口腔溃疡没有",
        "你帮我保存口腔溃疡没有啊",
        "昨天帮我记录的口腔溃疡",
    ),
)
def test_completed_and_history_frames_are_read_references(text: str) -> None:
    assert is_historical_write_reference(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "记录口腔溃疡",
        "保存今天的晚餐",
        "打卡刚喝的水",
        "记录刚才打了一个喷嚏",
    ),
)
def test_current_write_commands_are_not_history_references(text: str) -> None:
    assert is_historical_write_reference(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "请记录我上一次口腔溃疡，发作日期是7月1日",
        "把以前的口腔溃疡记录下来，开始日期是7月1日",
        "帮我保存既往感冒记录，起病日期是6月3日",
        "昨天喝水很多 补充记录 1200 毫升",
    ),
)
def test_explicit_dated_backfill_is_not_a_history_query(text: str) -> None:
    assert is_historical_write_reference(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "请查询口腔溃疡记录",
        "请查看我的口腔溃疡记录",
        "帮我列出口腔溃疡记录",
        "麻烦显示口腔溃疡记录",
        "帮我看看口腔溃疡记录",
    ),
)
def test_read_actions_govern_later_record_nouns(text: str) -> None:
    assert is_read_action_write_reference(text) is True
    assert has_explicit_authorizing_write_request(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "请帮我确认有没有记录成功",
        "麻烦查查保存成功不成功",
        "帮我核对一下是否新增成功",
        "请查看口腔溃疡是否已录入",
        "请确认口腔溃疡是否已经成功写入数据库",
        "帮我核对口腔溃疡是否已经保存到病历中",
        "帮我看看昨天口腔溃疡是否已经记录",
        "请查一下上周那次口腔溃疡是否已保存",
    ),
)
def test_result_checks_are_not_new_write_authorizations(text: str) -> None:
    assert is_write_result_check(text) is True
    assert has_explicit_authorizing_write_request(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "客服说请记录口腔溃疡",
        "文档写着：帮我记录口腔溃疡",
        "他说记录一下口腔溃疡",
        "请转述这句话：记录口腔溃疡",
        "请复述“帮我记录口腔溃疡”",
        "我只是举个例子：帮我记录口腔溃疡",
        "假设我说“帮我记录口腔溃疡”",
        "如果以后我说帮我记录口腔溃疡会怎样",
        "“帮我记录口腔溃疡”是什么意思",
        "文档写着：我午餐吃了米饭",
        "假设我午餐吃了米饭会怎样",
        "朋友说帮我记录口腔溃疡",
        "同事转告我：帮我记录口腔溃疡",
        "例如：帮我记录口腔溃疡",
        "朋友说我喝了300ml水",
        "文档称我午餐吃了米饭",
        "假定我午餐吃了米饭",
        "模拟场景：我喝了300ml水",
        "朋友说我头痛",
        "体检报告写着体重71kg",
    ),
)
def test_reported_or_quoted_write_language_is_not_authorization(text: str) -> None:
    assert is_reported_write_reference(text) is True
    assert has_explicit_authorizing_write_request(text) is False


def test_quoted_example_split_by_metalinguistic_suffix_has_no_write_authority():
    text = "“请记录体重72kg”只是一个例句"

    assert is_reported_write_reference(text) is True
    assert has_explicit_authorizing_write_request(text) is False
    assert authorized_health_record_clauses(text) == ()


def test_quoted_example_does_not_revoke_later_direct_contrast_request():
    text = "“请记录体重72kg”只是例句，但请记录我的体重73kg"

    assert authorized_health_record_clauses(text) == ("请记录我的体重73kg",)


@pytest.mark.parametrize(
    "text",
    (
        "请不必帮我记录口腔溃疡",
        "请杜绝系统自动记录口腔溃疡",
        "在没有得到我同意的情况下，记录口腔溃疡是不允许的",
        "记录口腔溃疡就免了",
        "记录口腔溃疡这件事作罢",
        "记录口腔溃疡未获授权",
        "记录口腔溃疡，还是算了",
        "记录口腔溃疡，取消吧",
        "记录体重71kg，算了吧",
        "记录体重71kg，取消这件事",
        "记录体重71kg，撤回",
        "记录体重71kg，不过算了吧",
        "帮我记录口腔溃疡暂缓",
        "记录口腔溃疡等一下再说",
        "记录口腔溃疡先放一放",
        "记录口腔溃疡是不可以的",
        "记录口腔溃疡我不同意",
        "记录口腔溃疡不行",
        "不要做这件事：帮我记录口腔溃疡",
        "我从未叫你帮我记录口腔溃疡",
        "我可没让你帮我记录口腔溃疡",
        "未经我许可就帮我记录口腔溃疡",
        "我并不乐意让你帮我记录口腔溃疡",
    ),
)
def test_preconditions_and_trailing_revocations_deny_write(text: str) -> None:
    assert has_negated_write_scope(text) is True
    assert has_explicit_authorizing_write_request(text) is False


@pytest.mark.parametrize(
    "text",
    (
        "不要记录口腔溃疡但记录今天晚餐",
        "别保存早餐而是记录午餐",
        "不用录入昨天的但请录入今天的口腔溃疡",
        "不是不让你记录是请你记录口腔溃疡",
        "不要记录上一条，但是请记录这次口腔溃疡",
        "虽然以前不想记录，但是现在请记录这次口腔溃疡",
        "不是不要记录口腔溃疡，而是现在就记录",
    ),
)
def test_last_positive_contrast_clause_authorizes_its_write(text: str) -> None:
    assert has_negated_write_scope(text) is False
    assert has_explicit_authorizing_write_request(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "不要保存早餐请记录午餐",
        "不要记录喝水300ml请记录晚餐",
    ),
)
def test_unpunctuated_later_direct_request_has_its_own_scope(text: str) -> None:
    assert has_negated_write_scope(text) is False
    assert has_explicit_authorizing_write_request(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "如果可以，请记录体重71kg",
        "假如方便，帮我记录体重71kg",
        "请先告诉我今天还差多少水，然后记录体重71kg",
        "不要告诉我今天的热量，然后记录体重71kg",
        "计算热量和营养并记录饮食",
        "识别这顿饭同时记录晚餐",
    ),
)
def test_polite_conditions_do_not_turn_direct_requests_into_quotations(
    text: str,
) -> None:
    assert is_reported_write_reference(text) is False
    assert has_explicit_authorizing_write_request(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "小巴你能帮我记录一下口腔溃疡吗",
        "小巴麻烦你记录口腔溃疡",
        "小巴请你记录口腔溃疡",
        "小巴替我记录口腔溃疡",
        "口腔溃疡上次发作日期是7月1日请记录一下",
        "记录过敏反应",
        "请记录过量饮酒",
        "帮我记录过去三天的食欲下降",
        "请记录过程中的头痛",
        "我想让你记录口腔溃疡",
        "请务必记录口腔溃疡",
        "帮我把今天午餐记录下来",
        "把口腔溃疡记录下来",
        "记录我的体重71kg",
        "请记录我今天体重71kg",
        "把我的体重71kg记录下来",
        "记录我的右侧腰疼",
        "记录2026年8月7日午餐吃了三明治",
    ),
)
def test_direct_vocative_backfill_and_lexical_guards_authorize(text: str) -> None:
    assert has_explicit_authorizing_write_request(text) is True


def test_current_user_body_observation_has_concrete_authority() -> None:
    text = "还是有腰疼的症状"

    assert authorized_health_record_clauses(text) == (text,)


@pytest.mark.parametrize(
    "text",
    (
        "创建目标：体重达到理想范围",
        "设置目标体重达到理想水平",
        "我的目标是达到理想体重",
    ),
)
def test_goal_destination_language_is_not_misread_as_third_party_arrival(
    text: str,
) -> None:
    assert _event_fact_has_non_current_subject(text) is False
    if text.startswith(("创建", "设置")):
        assert authorized_health_record_clauses(text) != ()
