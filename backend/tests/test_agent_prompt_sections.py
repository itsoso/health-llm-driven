"""Freeze the provider-visible rules before extracting the stage builders."""
import hashlib
import json
from pathlib import Path

import pytest

from app.services import agent_executor as ae

BASELINE = json.loads((Path(__file__).parent / 'fixtures/prompt_base_7d934b3.json').read_text())


@pytest.mark.parametrize('case', BASELINE['cases'])
def test_extracted_base_rules_match_original_bytes(case):
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
    assert hashlib.sha256('\n'.join(parts).encode()).hexdigest() == case['sha256']


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
