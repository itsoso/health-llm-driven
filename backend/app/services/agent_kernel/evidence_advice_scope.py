"""Share execution/completion plumbing for advice with explicit read evidence."""
from app.services.agent_kernel.exercise_plan_scope import (
    resolve_exercise_plan_scope, exercise_plan_prompt, exercise_plan_evidence_outcomes,
)
from app.services.agent_kernel.personal_diet_scope import (
    PersonalDietScope, resolve_personal_diet_scope, personal_diet_prompt,
)


def resolve_evidence_advice_scope(text):
    return resolve_personal_diet_scope(text) or resolve_exercise_plan_scope(text)


def evidence_advice_prompt(scope):
    return personal_diet_prompt(scope) if isinstance(scope, PersonalDietScope) else exercise_plan_prompt(scope)


def evidence_advice_outcomes(scope, executions):
    return exercise_plan_evidence_outcomes(scope, executions, decision_reason=(
        'personal_diet_explicit_evidence' if isinstance(scope, PersonalDietScope) else 'exercise_plan_explicit_evidence'))


def incomplete_evidence_advice_notice(text):
    if resolve_personal_diet_scope(text) is not None:
        return '饮食分析所需的个人资料尚未查询完成，暂不能声称已基于你的基因、年龄或体重给出个性化建议。请稍后重试。'
    return '制定计划所需的体检或病史依据尚未查询完成，暂不能据此提供个性化恢复方案。请稍后重试。'
