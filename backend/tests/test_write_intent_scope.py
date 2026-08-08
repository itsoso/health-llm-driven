import pytest

from app.services.utterance_intent_lexicon import WRITE_COMMAND_ACTIONS
from app.services.write_intent_scope import (
    has_negated_write_scope,
    is_historical_write_reference,
    is_write_capability_question,
    split_write_clauses,
)


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
        "该功能能否保存病症记录？",
    ),
)
def test_capability_questions_are_distinct_from_write_requests(text: str) -> None:
    assert is_write_capability_question(text) is True


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
    ),
)
def test_explicit_dated_backfill_is_not_a_history_query(text: str) -> None:
    assert is_historical_write_reference(text) is False
