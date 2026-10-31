"""A record request remains an obligation even without a known record domain."""
import pytest

from app.services.agent_record_obligation import record_obligation_requested


@pytest.mark.parametrize('text', [
    '记录，我洗鼻一次，使用了一支10毫升的生理盐水',
    '请帮我记录今天冥想20分钟',
    '记录，我做了康复训练一次',
    '登记今天的日照时长15分钟',
    '请保存我的呼吸训练记录',
    '记录，昨天洗鼻一次',
    '记录体重71kg',
    '记一下我今天做的平衡练习',
])
def test_explicit_record_request_is_domain_independent(text):
    assert record_obligation_requested(text) is True


@pytest.mark.parametrize('text', [
    '',
    '今天洗鼻一次',
    '你能记录洗鼻吗？',
    '系统支持记录呼吸训练吗？',
    '记录什么比较好？',
    '记录哪些内容？',
    '“记录我洗鼻一次”',
    '刚才那条洗鼻记录保存了吗？',
    '查询昨天的洗鼻记录',
    '我昨天记录过洗鼻一次',
    '不要记录，我洗鼻一次',
    '记录我洗鼻一次，算了别记了',
    '假如我洗鼻一次，就记录下来',
    '等我洗鼻后再记录',
    '明天帮我记录洗鼻一次',
    '记录我明天要做的洗鼻',
    '记录爸爸洗鼻一次',
    '记录，我朋友洗鼻一次',
    '妈妈让我记录洗鼻一次',
    '请分析这句话：“记录我洗鼻一次”',
    '他说：记录我洗鼻一次',
    '> 记录我洗鼻一次',
    '```\n记录我洗鼻一次\n```',
    '删除昨天的洗鼻记录',
    '修改洗鼻记录为两次',
    '更新我的洗鼻记录',
])
def test_context_mentions_and_other_operations_do_not_create_obligation(text):
    assert record_obligation_requested(text) is False


@pytest.mark.parametrize(('text', 'expected'), [
    ('记录，我洗鼻一次，另外喝水300ml', ('记录，我洗鼻一次', '喝水300ml')),
    ('记录我喝水300ml，再记录光照适应一次', ('记录我喝水300ml', '记录光照适应一次')),
    ('记录我喝水300ml。记录光照适应一次', ('记录我喝水300ml', '记录光照适应一次')),
    ('记录我喝水300ml；请记录光照适应一次', ('记录我喝水300ml', '请记录光照适应一次')),
    ('记录我做了平衡训练，同时登记一次光照适应', ('记录我做了平衡训练', '登记一次光照适应')),
    ('记录我喝水300ml并记录我喝水200ml', ('记录我喝水300ml', '记录我喝水200ml')),
    ('记录我冥想一次，另外我呼吸练习两次', ('记录我冥想一次', '我呼吸练习两次')),
    ('记录我做了平衡训练，另外记录我做了握力训练', ('记录我做了平衡训练', '记录我做了握力训练')),
])
def test_record_obligation_parts_preserve_separate_requested_actions(text, expected):
    from app.services.agent_record_obligation import record_obligation_parts
    assert record_obligation_parts(text) == expected


@pytest.mark.parametrize('text', [
    '记录，我洗鼻一次，使用了一支10毫升的生理盐水',
    '记录早餐鸡蛋和牛奶',
    '记录我同时吃了鸡蛋和牛奶',
    '记录，同时做了呼吸训练',
    '记录我喝水300ml，今天上午',
    '记录我做了平衡训练一次',
])
def test_record_obligation_parts_do_not_split_attributes_or_plain_lists(text):
    from app.services.agent_record_obligation import record_obligation_parts
    assert record_obligation_parts(text) == (text,)


@pytest.mark.parametrize('text', [
    '不要记录我喝水300ml，也不要记录洗鼻一次',
    '记录我喝水300ml，再记录洗鼻一次，算了都不要记了',
    '请分析这句话：“记录我喝水300ml。另外记录洗鼻一次”',
    '> 记录我喝水300ml。记录洗鼻一次',
    '```\n记录我喝水300ml。记录洗鼻一次\n```',
    '你能记录我喝水300ml，再记录洗鼻一次吗？',
    '我喝水300ml，同时洗鼻一次',
])
def test_record_obligation_parts_do_not_promote_quoted_or_cancelled_acts(text):
    from app.services.agent_record_obligation import record_obligation_parts
    assert record_obligation_parts(text) == ()


@pytest.mark.parametrize('text', [
    '午餐吃了牛肉面，帮我记录一下',
    '记录晚餐吃了沙拉，同时计算这餐的卡路里、蛋白质、碳水、脂肪和膳食纤维',
    '这是审核账号的测试记录。记录今天午餐：白米饭100克、鸡蛋1个，已经全部吃完。请估算营养并直接保存这一餐，备注必须保留测试标记 QA-MEAL-A。',
    '记录我喝水300ml，同时分析这条记录',
    '记录我做了平衡练习，帮我保存下来',
])
def test_record_obligation_parts_keep_restatement_analysis_and_metadata_attached(text):
    from app.services.agent_record_obligation import record_obligation_parts
    assert record_obligation_parts(text) == (text,)


@pytest.mark.parametrize(('text', 'expected'), [
    ('记录我喝水300ml，同时分析这条记录，另外记录光照适应一次',
     ('记录我喝水300ml，同时分析这条记录', '记录光照适应一次')),
    ('午餐吃了牛肉面，帮我记录一下。另外记录光照适应一次',
     ('午餐吃了牛肉面，帮我记录一下', '记录光照适应一次')),
    ('这是审核账号的测试记录。记录我喝水300ml。另外记录光照适应一次',
     ('这是审核账号的测试记录。记录我喝水300ml', '记录光照适应一次')),
])
def test_record_obligation_parts_still_keep_new_facts_after_attached_clauses(text, expected):
    from app.services.agent_record_obligation import record_obligation_parts
    assert record_obligation_parts(text) == expected


def test_embedded_frequency_conjunction_stays_inside_one_symptom_description():
    from app.services.agent_record_obligation import record_obligation_parts
    text = '帮我记录一下，眼睛发痒已经消失了，但偶尔还有轻微鼻塞。'
    assert record_obligation_parts(text) == (text,)
