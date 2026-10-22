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


def test_prompt_corrections_do_not_change_tool_schema_structure():
    from app.services.tool_schema_registry import HEALTH_TOOLS

    def without_descriptions(value):
        if isinstance(value, dict):
            return {k: without_descriptions(v) for k, v in value.items() if k != 'description'}
        if isinstance(value, list):
            return [without_descriptions(v) for v in value]
        return value

    contract = json.loads((Path(__file__).parent / 'fixtures/prompt_tool_contract_round2.json').read_text())
    serialized = json.dumps(without_descriptions(HEALTH_TOOLS), sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(serialized.encode()).hexdigest() == contract['schema_structure_sha256']
