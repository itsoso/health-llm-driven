"""A bounded control probe may never become a global clinical thinking cap."""
from types import SimpleNamespace
import pytest

@pytest.mark.parametrize('model,floor,deep,eligible,expected', [
    ('qwen3.8-max', False, False, True, True),
    ('qwen3.8-flash', False, False, True, False),
    ('qwen3.8-max', True, False, True, False),
    ('qwen3.8-max', False, True, True, False),
    ('qwen3.8-max', False, False, False, False),
])
@pytest.mark.parametrize('budget', [512, 8192])
def test_budget_probe_requires_preplanned_read_and_preserves_quality_floor(model, floor, deep, eligible, expected, budget):
    from eval.experimental_read_thinking_budget import install_read_thinking_budget
    planner_result = [{'id': 'read'}] if eligible else []
    executor = SimpleNamespace(_last_effective_model_id=model, _turn_invoked_deep_analysis=deep,
        _requires_quality_floor=lambda: floor, _preplanned_owned_read_calls=lambda *a, **k: planner_result,
        _maybe_apply_synthesis_thinking_budget=lambda wire: None)
    install_read_thinking_budget(executor, budget=budget)
    early = {}
    executor._maybe_apply_synthesis_thinking_budget(early)
    assert early == {}
    assert executor._preplanned_owned_read_calls() is planner_result
    kwargs = {'max_tokens':8000, 'temperature':0.3}
    executor._maybe_apply_synthesis_thinking_budget(kwargs)
    assert kwargs == {'max_tokens':8000, 'temperature':0.3, **({'thinking_budget':budget} if expected else {})}
    tool = {'tools':[{'name':'health_query'}]}
    executor._maybe_apply_synthesis_thinking_budget(tool)
    assert 'thinking_budget' not in tool


@pytest.mark.parametrize('budget', [0, 4096, 16384, True, 8192.0, '8192'])
def test_probe_rejects_unconfigured_control_before_mutation(budget):
    from eval.experimental_read_thinking_budget import install_read_thinking_budget
    executor = SimpleNamespace()
    with pytest.raises(ValueError, match='unsupported_eval_thinking_budget'):
        install_read_thinking_budget(executor, budget=budget)
    assert vars(executor) == {}
