"""Freeze the provider-visible rules before extracting the stage builders."""
import hashlib
import json
import re
from pathlib import Path

import pytest

from app.services import agent_executor as ae

BASELINE = json.loads((Path(__file__).parent / 'fixtures/prompt_base_7d934b3.json').read_text())
CONTRACT_UPDATES = json.loads((Path(__file__).parent / 'fixtures/prompt_tool_contract_round2.json').read_text())['replacements']


@pytest.mark.parametrize('case', BASELINE['cases'])
def test_base_safety_rules_unchanged_by_response_style(case):
    from app.services.agent_prompt_sections import build_base_prompt_parts

    parts = build_base_prompt_parts(
        synthesis_only=case['synthesis_only'],
        health_evidence_runtime=case['health_evidence_runtime'],
        exercise_plan_parts=['EXERCISE_SCOPE_SENTINEL'] if case['exercise'] else [],
        health_status_intent_prompt=ae._HEALTH_STATUS_INTENT_PROMPT,
        clinician_provenance_parts=ae._CLINICIAN_PROVENANCE_PROMPT_BLOCK,
        gene_rules_parts=ae._GENE_RULES_PROMPT_BLOCK if case['gene'] else (),
        menu_share_parts=ae._MENU_SHARE_PROMPT_BLOCK if case['menu'] else (),
    )
    original, separator, style = '\n'.join(parts).partition('\n\n## 回答组织\n')
    assert separator, 'Both execution and synthesis prompts need response guidance'
    # Freeze every unedited rule, including R4. Only these reviewed contract
    # corrections may differ; do not regenerate the old safety hashes.
    for old, new in CONTRACT_UPDATES:
        original = original.replace(new, old)
    assert hashlib.sha256(original.encode()).hexdigest() == case['sha256']
    assert '先直接回答用户当前问题' in style
    assert '不能为了简短省略' in style
    assert '不改变工具权限' in style
    assert '不要以“如果你愿意”' in style


def test_extracted_parts_are_independent_between_requests():
    from app.services.agent_prompt_sections import build_base_prompt_parts

    kwargs = dict(synthesis_only=True, health_evidence_runtime=False,
                  exercise_plan_parts=[], health_status_intent_prompt='STATUS',
                  clinician_provenance_parts=('CLINICIAN',),
                  gene_rules_parts=(), menu_share_parts=())
    first = build_base_prompt_parts(**kwargs)
    second = build_base_prompt_parts(**kwargs)
    first.append('user-specific evidence')
    assert 'user-specific evidence' not in second


def test_persona_is_xiaoqihou_and_does_not_encourage_scope_expansion():
    prompt = _execution_prompt()
    assert '你是“小气候”' in prompt
    assert '严格完成本轮请求' in prompt
    assert '不得主动扩大' in prompt
    assert '唯一的对话入口' not in prompt


def test_read_synthesis_projection_removes_planning_only_rules_and_keeps_safety():
    from app.services.agent_prompt_sections import (
        build_base_prompt_parts,
        build_read_synthesis_parts,
    )

    kwargs = dict(
        synthesis_only=True,
        health_evidence_runtime=False,
        exercise_plan_parts=[],
        health_status_intent_prompt=ae._HEALTH_STATUS_INTENT_PROMPT,
        clinician_provenance_parts=ae._CLINICIAN_PROVENANCE_PROMPT_BLOCK,
        gene_rules_parts=(),
        menu_share_parts=(),
    )
    before = build_base_prompt_parts(**kwargs)
    after = build_read_synthesis_parts(**kwargs)
    rendered = '\n'.join(after)

    assert len(rendered) < len('\n'.join(before)) * 0.8
    assert '## 本轮任务边界' not in rendered
    assert '## 健康近况与用药意图' not in rendered
    for marker in (
        '## 本轮只依据返回结果回答',
        '## 临床来源与写入边界（服务端护栏优先）',
        '## 安全与边界 (R4 — 必须严格遵守)',
        '不做诊断', '相关性,非因果', '数据合理性提示',
        '读取失败、缺失或未核验字段不能当作已核验事实',
    ):
        assert marker in rendered


@pytest.mark.parametrize('key,value', [
    ('synthesis_only', False),
    ('health_evidence_runtime', True),
    ('exercise_plan_parts', ['exercise-boundary']),
    ('gene_rules_parts', ae._GENE_RULES_PROMPT_BLOCK),
    ('menu_share_parts', ae._MENU_SHARE_PROMPT_BLOCK),
])
def test_read_synthesis_projection_fails_closed_outside_sealed_read_answer(key, value):
    from app.services.agent_prompt_sections import (
        build_base_prompt_parts,
        build_read_synthesis_parts,
    )

    kwargs = dict(
        synthesis_only=True,
        health_evidence_runtime=False,
        exercise_plan_parts=[],
        health_status_intent_prompt=ae._HEALTH_STATUS_INTENT_PROMPT,
        clinician_provenance_parts=ae._CLINICIAN_PROVENANCE_PROMPT_BLOCK,
        gene_rules_parts=(),
        menu_share_parts=(),
    )
    kwargs[key] = value
    assert build_read_synthesis_parts(**kwargs) == build_base_prompt_parts(**kwargs)


def _execution_prompt():
    from app.services.agent_prompt_sections import build_base_prompt_parts
    return '\n'.join(build_base_prompt_parts(
        synthesis_only=False, health_evidence_runtime=False,
        exercise_plan_parts=[], health_status_intent_prompt='',
        clinician_provenance_parts=(), gene_rules_parts=(), menu_share_parts=(),
    ))


@pytest.mark.parametrize('old,new', CONTRACT_UPDATES)
def test_record_instructions_follow_runtime_contract(old, new):
    prompt = _execution_prompt()
    assert new in prompt
    assert old not in prompt


def test_prompt_tool_examples_use_registered_parameter_names():
    from app.services.tool_schema_registry import HEALTH_TOOLS
    schemas = {t['function']['name']: t['function']['parameters'] for t in HEALTH_TOOLS}
    examples = re.findall(r'\b(health_record|health_analysis)\(([^()]*)\)', _execution_prompt())
    assert examples
    for name, arguments in examples:
        keys = set(re.findall(r'\b(\w+)\s*=', arguments))
        assert keys <= set(schemas[name]['properties']), (name, keys)
        assert set(schemas[name]['required']) <= keys, (name, keys)


def test_read_descriptions_do_not_default_unknown_scope_to_comprehensive():
    from app.services.tool_schema_registry import HEALTH_TOOLS
    tools = {t['function']['name']: t['function'] for t in HEALTH_TOOLS}
    query = tools['health_query']['description']
    analysis = tools['health_analysis']['parameters']['properties']['analysis_type']['description']
    for description in (query, analysis):
        assert '不确定' not in description
        assert '不得扩大' in description


def test_water_does_not_inherit_supplement_required_facts():
    water = next((line for line in _execution_prompt().splitlines() if line.startswith('- 饮水记录：')), '')
    assert 'amount' in water
    assert not any(word in water for word in ('产品名称', '服用', '服药'))


def test_analysis_examples_do_not_expand_an_unspecified_query():
    from app.services.tool_schema_registry import HEALTH_TOOLS
    description = next(t['function']['description'] for t in HEALTH_TOOLS if t['function']['name'] == 'health_analysis')
    assert '近7天怎么样 / 最近怎么样' not in description
    assert '目标或维度不明时先澄清' in description


def test_prompt_corrections_do_not_change_tool_schema_structure():
    from app.services.tool_schema_registry import HEALTH_TOOLS

    def without_descriptions(value):
        if isinstance(value, dict):
            return {k: without_descriptions(v) for k, v in value.items() if k != 'description'}
        if isinstance(value, list):
            return [without_descriptions(v) for v in value]
        return value

    contract = json.loads((Path(__file__).parent / 'fixtures/prompt_tool_contract_round2.json').read_text())
    structure = without_descriptions(HEALTH_TOOLS)
    # Body review and personal dietary evidence add reviewed read dimensions.
    # Keep the original freeze for every other tool, field and enum value.
    query = next(t['function'] for t in structure if t['function']['name'] == 'health_query')
    dimensions = query['parameters']['properties']['dimension']['enum']
    assert dimensions.count('age') == 1
    dimensions.remove('age')
    assert dimensions.count('waist') == 1
    waist_index = dimensions.index('waist')
    assert dimensions[waist_index - 1:waist_index + 2] == ['weight', 'waist', 'bmi']
    dimensions.remove('waist')
    # The reviewed record capability adds one enum; preserve the freeze for
    # every legacy field instead of accepting arbitrary schema drift.
    record = next(t['function'] for t in structure if t['function']['name'] == 'health_record')
    record_types = record['parameters']['properties']['record_type']['enum']
    assert record_types.count('nasal_wash') == 1
    record_types.remove('nasal_wash')
    serialized = json.dumps(structure, sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(serialized.encode()).hexdigest() == contract['schema_structure_sha256']
