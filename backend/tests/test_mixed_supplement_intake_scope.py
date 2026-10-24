"""A mixed intake statement grants two bounded facts, never cross-type writes."""
import pytest
from app.services.write_intent_scope import authorized_health_record_clauses
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot
from app.services.agent_kernel.capability_policy import decide_tool_capability

TEXT = '记录补剂 吃了一粒锌片 喝了一杯豆浆'


def decision(text, record_type, data):
    envelope = AgentEnvelope(user_id=1, channel="chat", text=text)
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    snapshot = TurnSnapshot(
        envelope=envelope, context=context,
        intent=build_intent_frame(envelope, context),
    )
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": record_type, "data": data},
        source="structured",
    )
    return decide_tool_capability(snapshot, request)


@pytest.mark.parametrize("text", [
    TEXT,
    "记录补剂吃了一粒锌片喝了一杯豆浆",
    "请记录补剂：我今天吃了一粒锌片，然后我喝了一杯豆浆。",
])
def test_mixed_intake_has_authority_for_both_typed_facts(text):
    assert len(authorized_health_record_clauses(text)) == 2
    supplement = decision(text, 'supplement', {'supplement_name': '锌片', 'dosage': '1粒'})
    assert supplement.action == 'allow'
    assert supplement.normalized_args['data']['supplement_name'] == '锌片'
    assert decision(text, 'diet', {'meal_type': 'snack', 'food_items': '一杯豆浆'}).action == 'allow'


@pytest.mark.parametrize('record_type,data', [
    ('supplement', {'supplement_name': '豆浆', 'dosage': '1杯'}),
    ('supplement', {'supplement_name': '锌片', 'dosage': '2粒'}),
    ('supplement', {'supplement_name': '锌片', 'dosage': '50mg'}),
    ('supplement', {'supplement_name': '锌片', 'dosage': '1粒',
                    'items': [{'supplement_name': '褪黑素', 'dosage': '20粒'}]}),
    ('diet', {'food_items': '一粒锌片'}),
    ('diet', {'food_items': '两杯豆浆'}),
    ('diet', {'food_items': '一杯豆浆', 'meal_type': 'dinner'}),
    ('medication', {'name': '锌片', 'dosage': '1粒'}),
])
def test_mixed_intake_rejects_cross_type_or_invented_details(record_type, data):
    assert decision(TEXT, record_type, data).action == 'block'


@pytest.mark.parametrize('text', [
    '不要记录补剂吃了一粒锌片喝了一杯豆浆',
    '记录补剂妈妈吃了一粒锌片喝了一杯豆浆',
    '记录补剂吃了一粒锌片妈妈喝了一杯豆浆',
    '记录补剂吃了一粒锌片喝了一杯豆浆，这是妈妈的',
    '他说记录补剂吃了一粒锌片喝了一杯豆浆',
    '“记录补剂吃了一粒锌片喝了一杯豆浆”',
    '明天记录补剂吃了一粒锌片喝了一杯豆浆',
    '记录补剂准备吃一粒锌片喝一杯豆浆',
    '记录补剂没吃一粒锌片喝了一杯豆浆',
    '记录补剂吃了一粒锌片没喝一杯豆浆',
    '记录补剂吃了一粒阿莫西林喝了一杯豆浆',
    '记录补剂吃了一锌片喝了一杯豆浆',
    '记录补剂吃了一粒锌片喝了一杯豆浆吗',
    '记录补剂吃了一粒锌片喝了一杯豆浆，不要记录',
])
def test_mixed_intake_does_not_bypass_provenance_or_dose_boundaries(text):
    for record_type, data in [('supplement', {'supplement_name': '锌片', 'dosage': '1粒'}), ('diet', {'food_items': '一杯豆浆'})]:
        assert decision(text, record_type, data).action == 'block'


@pytest.mark.parametrize('items', [[], None, 'invalid', [{'supplement_name': '锌片', 'dosage': '999粒'}]])
@pytest.mark.parametrize('container', ['top', 'data'])
def test_mixed_single_intake_rejects_any_batch_payload(items, container):
    envelope = AgentEnvelope(user_id=1, channel='chat', text=TEXT)
    context = ExecutionContext.for_test(user_id=1, channel='chat')
    snapshot = TurnSnapshot(envelope=envelope, context=context, intent=build_intent_frame(envelope, context))
    args = {'record_type': 'supplement', 'data': {'supplement_name': '锌片', 'dosage': '1粒'}}
    (args if container == 'top' else args['data'])['items'] = items
    result = decide_tool_capability(snapshot, ToolExecutionRequest(tool_name='health_record', arguments=args))
    assert result.action == 'block'


@pytest.mark.parametrize('quantity', ['二三', '两三', '一一', '十十', '零', '0'])
@pytest.mark.parametrize('slot', ['supplement', 'drink'])
def test_mixed_intake_does_not_parse_ambiguous_or_invalid_chinese_quantities(quantity, slot):
    from app.services.write_intent_scope import direct_mixed_supplement_food_values
    text = (f'记录补剂吃了{quantity}粒锌片喝了一杯豆浆' if slot == 'supplement'
            else f'记录补剂吃了一粒锌片喝了{quantity}杯豆浆')
    assert direct_mixed_supplement_food_values(text) is None


@pytest.mark.parametrize('source,target', [('1.5杯豆浆', '15杯豆浆'), ('1.0杯豆浆', '10杯豆浆'), ('1.50杯豆浆', '150杯豆浆'), ('一杯豆浆', '.1杯豆浆')])
def test_mixed_drink_preserves_decimal_quantity(source, target):
    assert decision(f'记录补剂吃了一粒锌片喝了{source}', 'diet',
                    {'food_items': target, 'meal_type': 'snack'}).action == 'block'


@pytest.mark.parametrize('dosage', ['.1粒', '1..粒', '1!粒', '1,粒'])
def test_mixed_supplement_rejects_corrupted_dosage(dosage):
    assert decision(TEXT, 'supplement', {'supplement_name': '锌片', 'dosage': dosage}).action == 'block'


@pytest.mark.parametrize('source,target', [('1.5杯豆浆', '豆浆1.50杯'), ('半杯豆浆', '豆浆0.5杯'), ('两杯牛奶', '牛奶2杯'), ('十毫升酸奶', '酸奶10ml')])
def test_mixed_drink_equivalent_exact_quantities_are_allowed(source, target):
    result = decision(f'记录补剂吃了一粒锌片喝了{source}', 'diet', {'food_items': target, 'meal_type': 'snack'})
    assert result.action == 'allow'
    assert result.normalized_args['data']['food_items'] == target

@pytest.mark.parametrize('text', [
    '记录一下，喝了一杯豆浆，吃了一粒锌片',
    '帮我记下：刚吃了锌片一粒，还喝了豆浆一杯',
    '记录补剂吃了一粒锌片和两粒鱼油喝了一杯豆浆',
])
def test_order_independent_intake_plan(text):
    from app.services.intake_plan import parse_intake_plan
    plan = parse_intake_plan(text)
    assert plan.status == 'complete'
    assert len(plan.items) >= 2
    for item in plan.items:
        assert parse_intake_plan(item.canonical_text).status == 'complete'
        data = ({'supplement_name': item.name, 'dosage': item.amount_text}
                if item.record_type == 'supplement' else
                {'food_items': item.amount_text + item.name, 'meal_type': 'snack'})
        assert decision(text, item.record_type, data).action == 'allow'

@pytest.mark.parametrize('text', [
    '记录补剂吃了一粒锌片和两粒锌片喝了一杯豆浆',
    '记录补剂吃了一粒锌片喝了一杯豆浆妈妈喝了一杯牛奶',
    '记录补剂吃了一粒锌片和未知补剂喝了一杯豆浆',
    '记录补剂吃了一粒锌片喝了一杯豆浆明天再喝一杯牛奶',
])
def test_incomplete_plan_cannot_fall_back_to_partial_authority(text):
    from app.services.intake_plan import parse_intake_plan
    assert parse_intake_plan(text).status == 'needs_clarification'
    assert authorized_health_record_clauses(text) == ()


def test_plan_limits_unique_items_and_preserves_source_spans():
    from app.services.intake_plan import parse_intake_plan
    source = '记录吃了一粒锌片和一粒钙片和一粒鱼油和一粒甘氨酸镁和一粒褪黑素和一粒复合维生素喝了一杯豆浆和半杯牛奶'
    plan = parse_intake_plan(source)
    assert plan.status == 'complete' and len(plan.items) == 8
    assert all(source[item.source_span[0]:item.source_span[1]] for item in plan.items)
    assert parse_intake_plan(source + '和一杯酸奶').status == 'needs_clarification'
    assert authorized_health_record_clauses(source + '和一杯酸奶') == ()


@pytest.mark.parametrize('text', [
    '记录一下，喝了一杯豆浆，妈妈吃了一粒锌片',
    '记录一下，喝了一杯豆浆，没吃一粒锌片',
    '记录一下，喝了一杯豆浆，明天吃一粒锌片',
    '记录一下，昨天喝了一杯豆浆，今天吃了一粒锌片',
    '记录一下，喝了一杯豆浆，吃了一粒50mg锌片',
    '记录一下，喝了二三杯豆浆，吃了一粒锌片',
    '记录一下，喝了一杯豆浆，吃了一粒锌片，这是妈妈的',
    '记录一下，喝了一杯豆浆，吃了一粒锌片，不要记录',
])
def test_plan_extension_does_not_expand_subject_date_or_strength(text):
    from app.services.intake_plan import parse_intake_plan
    assert parse_intake_plan(text).status == 'needs_clarification'
    assert authorized_health_record_clauses(text) == ()


def test_each_planned_item_rejects_wrong_owner_date_quantity_and_type():
    text = '记录一下，喝了一杯豆浆，吃了一粒锌片和两粒鱼油'
    for kind, data in [
        ('supplement', {'supplement_name': '鱼油', 'dosage': '1粒'}),
        ('supplement', {'supplement_name': '鱼油', 'dosage': '2粒', 'record_date': '2001-01-01'}),
        ('supplement', {'supplement_name': '豆浆', 'dosage': '1杯'}),
        ('diet', {'food_items': '一粒锌片', 'meal_type': 'snack'}),
    ]:
        assert decision(text, kind, data).action == 'block'


def test_plan_projection_drops_model_owned_user_id():
    result = decision('记录一下，喝了一杯豆浆，吃了一粒锌片和两粒鱼油',
                      'supplement', {'supplement_name': '鱼油', 'dosage': '2粒', 'user_id': 2})
    assert result.action == 'allow'
    assert 'user_id' not in result.normalized_args['data']
    assert 'user_id' not in result.normalized_args


def test_shared_intake_matcher_indexes_exact_items_without_mutating_payloads():
    from copy import deepcopy
    from app.services.agent_kernel.capability_policy import authorized_intake_item_index
    text = '记录一下，喝了一杯豆浆，吃了一粒锌片和两粒鱼油'
    envelope = AgentEnvelope(user_id=1, channel='chat', text=text)
    context = ExecutionContext.for_test(user_id=1, channel='chat')
    snapshot = TurnSnapshot(envelope=envelope, context=context, intent=build_intent_frame(envelope, context))
    for index, kind, data in [
        (0, 'diet', {'food_items': '豆浆1杯', 'meal_type': 'snack'}),
        (1, 'supplement', {'supplement_name': '锌片', 'dosage': '1粒'}),
        (2, 'supplement', {'supplement_name': '鱼油', 'dosage': '2粒'}),
        (None, 'supplement', {'supplement_name': '鱼油', 'dosage': '1粒'}),
        (None, 'supplement', {'supplement_name': '鱼油', 'dosage': '2粒', 'record_date': '2001-01-01'}),
        (None, 'supplement', {'supplement_name': '鱼油', 'dosage': '2粒', 'items': []}),
        (None, 'diet', {'food_items': '豆浆1.5杯', 'meal_type': 'snack'}),
    ]:
        args = {'record_type': kind, 'data': data}
        before = deepcopy(args)
        assert authorized_intake_item_index(snapshot, args) == index
        assert args == before
