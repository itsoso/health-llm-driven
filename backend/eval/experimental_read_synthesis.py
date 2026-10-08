"""Unapproved answer-stage experiment. No application imports or feature flag.

Only the benchmark patches the pure rule builder. It retains the canonical
clinical provenance, evidence limits, behavior and R4 safety instructions.
This stage filter does not establish task authority or clinical noninferiority.
"""
import hashlib

from app.services.agent_prompt_sections import build_base_prompt_parts

# A future policy edit must be reviewed again, not silently omitted by this
# experiment merely because its heading stayed the same.
_TASK_SCOPE_SHA256 = 'd203e56e07940f816c2b9555db310f2db0003849d27c9aaf498e206385669102'
_STATUS_SHA256 = '25081bdc026f31b584201d2c9459a9a0ac42a39958ccd556fa2528a4fa77ccc6'


def build_read_synthesis_parts(**kwargs):
    original = build_base_prompt_parts(**kwargs)
    if (
        kwargs['synthesis_only'] is not True
        or kwargs['health_evidence_runtime']
        or kwargs['exercise_plan_parts']
        or kwargs['gene_rules_parts']
        or kwargs['menu_share_parts']
    ):
        return original
    # Exact canonical boundaries: unknown future layouts retain all rules.
    task_heading = '## 本轮任务边界'
    answer_heading = '## 本轮只依据返回结果回答'
    status = kwargs['health_status_intent_prompt']
    if any(original.count(item) != 1 for item in (task_heading, answer_heading, status)):
        return original
    start, end = original.index(task_heading), original.index(answer_heading)
    if start >= end:
        return original
    if (
        hashlib.sha256('\n'.join(original[start:end]).encode()).hexdigest() != _TASK_SCOPE_SHA256
        or hashlib.sha256(status.encode()).hexdigest() != _STATUS_SHA256
    ):
        return original
    return [part for part in original[:start] + original[end:] if part != status]
