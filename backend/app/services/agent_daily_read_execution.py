"""Execute the server-owned daily scope and attest its individual read results."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.services.agent_kernel.daily_read_plan import DailyReadPlan
from app.services.genui.table_builder import load_tool_result_json
from app.services.agent_write_outcome import result_declares_explicit_failure


def planned_daily_calls(plan: DailyReadPlan) -> list[dict[str, Any]]:
    meal_args = plan.diet_list_args() if plan.meal_type else None
    requests = [('health_manage', meal_args)] if meal_args else [
        ('health_query', args) for args in plan.queries()]
    return [{'id': f'daily-read-{index}', 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps(args, ensure_ascii=False),
    }} for index, (name, args) in enumerate(requests)]


def daily_read_prompt(plan: DailyReadPlan) -> str:
    domains = '、'.join({'diet': '饮食', 'sleep': '睡眠'}[d] for d in plan.dimensions)
    return (
        f'\n[本轮查询范围]\n{plan.start_date} 至 {plan.end_date}，{plan.timezone}，{domains}。'
        + ('饮食只查询晚餐。' if plan.meal_type == 'dinner' else '')
        + '必须用本轮工具结果回答；无记录不等于没有发生。'
        + ('本次今日总结仅覆盖饮食与睡眠，开头简短说明范围；不要暗示其他健康领域也已查询。' if plan.is_summary else '')
        + '分别说明查到的事实、未查到的项目和依据这些结果可给出的建议。'
        '卡片已展示的完整记录不要再重复为同一张表；正文解释重点和不确定性。'
    )


def daily_result_goal(plan: DailyReadPlan, decision: Any, result: Any) -> dict[str, str] | None:
    if decision is None:
        return None
    args = decision.normalized_args
    name = decision.normalized_tool_name
    if name == 'health_query':
        dimension = args.get('dimension')
        bound = next((q for q in plan.queries() if q['dimension'] == dimension), None)
        matches = bound is not None and all(args.get(k) == v for k, v in bound.items())
    elif name == 'health_manage':
        dimension = 'diet'
        bound = plan.diet_list_args()
        matches = bound is not None and all(args.get(k) == v for k, v in bound.items())
    else:
        return None
    if not matches:
        return None
    payload = load_tool_result_json(result) if isinstance(result, str) else result
    has_result = isinstance(payload, list) or (
        isinstance(payload, dict) and any(isinstance(payload.get(k), list) for k in ('records', 'data', 'items'))
    )
    scope_conflict = False
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = next((payload[k] for k in ('records', 'data', 'items') if isinstance(payload.get(k), list)), [])
        scope_conflict = payload.get('dimension', dimension) != dimension
        if 'window' in payload:
            scope_conflict |= payload['window'] != {
                'start_date': plan.start_date, 'end_date': plan.end_date, 'timezone': plan.timezone,
            }
    for row in rows:
        if not isinstance(row, dict):
            scope_conflict = True
            continue
        if row.get('record_date') is not None:
            try:
                row_day = date.fromisoformat(str(row['record_date'])).isoformat()
                scope_conflict |= not plan.start_date <= row_day <= plan.end_date
            except ValueError:
                scope_conflict = True
        if plan.meal_type and row.get('meal_type') is not None:
            scope_conflict |= row['meal_type'] != plan.meal_type
    truncated = name == 'health_manage' and len(rows) >= int(args.get('limit') or 20)
    verified = not truncated and decision.action == 'allow' and has_result and not scope_conflict and not result_declares_explicit_failure(result)
    return {'goal_id': dimension, 'kind': 'query', 'status': 'verified' if verified else 'failed',
            'evidence_kind': 'read_result' if verified else '',
            'reason_code': ('query_verified' if verified else
                            'query_result_scope_conflict' if scope_conflict else
                            'query_result_truncated' if truncated else 'query_result_unavailable')}


def daily_goal_outcomes(plan: DailyReadPlan | None, completed: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    if plan is None:
        return []
    return [completed.get(d, {'goal_id': d, 'kind': 'query', 'status': 'failed',
                             'reason_code': 'query_not_executed'}) for d in plan.dimensions]
