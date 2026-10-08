"""Candidate only: remove planning prose from a sealed answer stage."""
from app.services import agent_executor as ae
from app.services.agent_prompt_sections import build_base_prompt_parts
import pytest
from pathlib import Path
import json
import os
from tests.test_agent_read_repair_round_budget import clock as clock


def arguments():
    return dict(synthesis_only=True, health_evidence_runtime=False,
                exercise_plan_parts=[], health_status_intent_prompt=ae._HEALTH_STATUS_INTENT_PROMPT,
                clinician_provenance_parts=ae._CLINICIAN_PROVENANCE_PROMPT_BLOCK,
                gene_rules_parts=(), menu_share_parts=())


def test_sealed_answer_keeps_all_clinician_r4_behavior_and_evidence_rules():
    from eval.experimental_read_synthesis import build_read_synthesis_parts

    kwargs = arguments()
    before = build_base_prompt_parts(**kwargs)
    after = build_read_synthesis_parts(**kwargs)
    assert len('\n'.join(after)) < len('\n'.join(before)) * .8
    assert '## 本轮任务边界' not in after
    assert ae._HEALTH_STATUS_INTENT_PROMPT not in after
    assert before[2] in after  # original time grounding
    assert all(rule in after for rule in ae._CLINICIAN_PROVENANCE_PROMPT_BLOCK)
    for heading in ('## 本轮只依据返回结果回答', '## 行为准则', '## 安全与边界 (R4 — 必须严格遵守)'):
        start = before.index(heading)
        end = next((i for i in range(start+1,len(before)) if before[i].startswith('## ')), len(before))
        assert all(rule in after for rule in before[start:end] if rule)


@pytest.mark.parametrize('key,value', [
    ('synthesis_only', False), ('health_evidence_runtime', True),
    ('exercise_plan_parts', ['exercise-boundary']), ('gene_rules_parts', ae._GENE_RULES_PROMPT_BLOCK),
    ('menu_share_parts', ae._MENU_SHARE_PROMPT_BLOCK),
])
def test_noneligible_stage_is_byte_identical(key, value):
    from eval.experimental_read_synthesis import build_read_synthesis_parts

    kwargs = arguments()
    kwargs[key] = value
    assert build_read_synthesis_parts(**kwargs) == build_base_prompt_parts(**kwargs)


def test_policy_changes_remain_complete(monkeypatch):
    from eval import experimental_read_synthesis as experiment

    kwargs = arguments()
    changed = build_base_prompt_parts(**kwargs)
    changed.insert(changed.index('## 本轮只依据返回结果回答'), '新增必须保留的约束')
    monkeypatch.setattr(experiment, 'build_base_prompt_parts', lambda **_: changed)
    assert experiment.build_read_synthesis_parts(**kwargs) == changed


def test_new_health_status_rule_is_not_removed():
    from eval.experimental_read_synthesis import build_read_synthesis_parts

    kwargs = arguments()
    kwargs['health_status_intent_prompt'] += '\n新增必须保留的约束'
    assert build_read_synthesis_parts(**kwargs) == build_base_prompt_parts(**kwargs)


def test_no_application_import_or_experiment_flag():
    root = Path(__file__).resolve().parents[1] / 'app'
    assert not any('experimental_read_synthesis' in path.read_text() for path in root.rglob('*.py'))


def test_benchmark_preserves_evidence_and_write_controls(monkeypatch):
    import importlib.util
    from eval.prompt_projection_quality import synthetic_projection_cases

    path = Path(__file__).resolve().parents[2] / 'scripts/benchmark_read_synthesis.py'
    spec = importlib.util.spec_from_file_location('read_stage_benchmark', path)
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', False)
    for case in synthetic_projection_cases():
        if case.stage != 'answer':
            continue
        payloads = benchmark.variants(case)
        before, after = payloads['baseline'], payloads['candidate']
        assert before[1:] == after[1:]
        if all(entry['name'] == 'health_record' for entry in case.evidence):
            assert before == after
        else:
            assert len(after[0]['content']) < len(before[0]['content'])
    assert ae.settings.domain_prompt_optimization is False


async def test_actual_pi_provider_projection_preserves_facts_tools_and_saved_answer(db, auth_user_and_headers, monkeypatch, clock):
    from tests.test_agent_diet_synthesis_projection import _run
    from eval.experimental_read_synthesis import build_read_synthesis_parts

    user, _ = auth_user_and_headers
    pairs = []
    for enabled in (False, True):
        with monkeypatch.context() as patch:
            patch.setattr(ae.settings, 'domain_prompt_optimization', True)
            if enabled:
                patch.setattr('app.services.agent_prompt_sections.build_base_prompt_parts', build_read_synthesis_parts)
            _, calls, dispatches, done, saved = await _run(db, user, patch, query='今天我吃的怎么样?', client_turn_id=f'read-stage-{enabled}')
            assert done['completion_status'] == 'complete'
            pairs.append({'enabled': enabled, 'calls': calls,
                          'dispatches': [(r.tool_name, r.arguments) for r in dispatches],
                          'saved': saved.content})
    before, after = pairs
    assert before['dispatches'] == after['dispatches']
    assert before['saved'] == after['saved']
    assert len(before['calls']) == len(after['calls']) == 2
    # The planning call (including full write schemas if present) is untouched.
    assert before['calls'][0] == after['calls'][0]
    old, new = before['calls'][-1], after['calls'][-1]
    assert not old.get('tools') and not new.get('tools')
    assert old['messages'][1:] == new['messages'][1:]
    assert len(new['messages'][0]['content']) < len(old['messages'][0]['content'])
    for marker in ('不做诊断', '相关性,非因果', 'STATIC_TRIAGE_SENTINEL',
                   '临床来源与写入边界', '数据合理性提示'):
        assert marker in new['messages'][0]['content']
    if output := os.environ.get('REVA_READ_SYNTHESIS_PAYLOADS'):
        Path(output).write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + '\n')
