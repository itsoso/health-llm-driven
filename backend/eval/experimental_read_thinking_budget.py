"""Eval-only Qwen Max control probe; never imported by application code.

Requires a hit in the default-off runtime preplanner. The unchanged quality
floor, deep-analysis boundary and actual model resolver still apply. This probe
is not a verified model-registry capability or an approved production setting.
"""


THINKING_PROBES = {"preplan_budget512": 512, "preplan_budget8192": 8192}


def install_read_thinking_budget(executor, *, budget=512):
    if type(budget) is not int or budget not in THINKING_PROBES.values():
        raise ValueError("unsupported_eval_thinking_budget")
    original_plan = executor._preplanned_owned_read_calls
    original_controls = executor._maybe_apply_synthesis_thinking_budget
    preplanned = False

    def plan(*args, **kwargs):
        nonlocal preplanned
        result = original_plan(*args, **kwargs)
        # The executor asks again in the answer round; an empty later proposal
        # must not erase the first round's observed preplanning hit.
        preplanned = preplanned or bool(result)
        return result

    def controls(wire):
        original_controls(wire)
        if (preplanned and executor._last_effective_model_id == 'qwen3.8-max'
                and not executor._requires_quality_floor()
                and not executor._turn_invoked_deep_analysis and not wire.get('tools')):
            wire['thinking_budget'] = budget

    executor._preplanned_owned_read_calls = plan
    executor._maybe_apply_synthesis_thinking_budget = controls
