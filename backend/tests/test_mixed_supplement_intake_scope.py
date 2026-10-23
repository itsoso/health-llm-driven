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
