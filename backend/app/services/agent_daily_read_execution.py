"""Execute the server-owned daily scope and attest its individual read results."""
from __future__ import annotations

import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.agent_kernel.daily_read_plan import DailyReadPlan
from app.services.genui.table_builder import load_tool_result_json
from app.services.agent_write_outcome import result_declares_explicit_failure
from app.utils.number_format import format_display_number


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
    summary_readable = not plan.is_summary or _summary_rows(plan, dimension, payload) is not None
    verified = summary_readable and not truncated and decision.action == 'allow' and has_result and not scope_conflict and not result_declares_explicit_failure(result)
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


def summary_advice_text(text: str) -> str:
    """Keep an explicitly headed advice section, including its heading text."""
    heading = re.search(
        r'^[ \t]*(?:#{1,6}[ \t]+建议(?:[（(][^\n）)]*[）)])?[ \t]*$'
        r'|\*\*建议\*\*[ \t]*$|建议[：:])', text, re.MULTILINE,
    )
    return text[heading.start():] if heading else text


def summary_advice_contract_failure(text: str) -> str | None:
    """Check only the qualitative advice contract after verified daily facts.

    This finite language boundary is not a general grounding or medical-safety
    verifier. The caller must preserve failures, not rewrite rejected advice.
    """
    if not text.strip():
        return 'summary_advice_unavailable'
    # Formatting must not turn a permitted future action into a measurement.
    text = text.replace('**', '').replace('__', '')
    number = r'(?:\d+(?:[.,]\d+)*|[零〇一二两三四五六七八九十百千万点半]+)'
    # Exempt only bounded imperative/future action spans, never an entire reply.
    # The same duration in an observation ("你今天睡了7小时") stays rejected.
    action_spans = [match.span() for match in re.finditer(
        rf'(?:^|[。！？!?；;，,\n])\s*(?:'
        rf'(?:建议|可以|可|不妨)?(?:睡前{number}\s*(?:小时|分钟)减少屏幕使用'
        rf'|饭后散步{number}\s*分钟)'
        rf'|建议把入睡安排在接下来{number}\s*(?:小时|分钟)内)', text,
    )]
    for match in re.finditer(
        rf'{number}\s*(?:个\s*)?(?:千卡|大卡|kcal|卡路里|小时|分钟|评分|分)'
        rf'|评分\s*(?:为|是|约为|约|[:：])?\s*{number}'
        r'(?![\d零〇一二两三四五六七八九十百千万点半]|\s*项)', text, re.IGNORECASE,
    ):
        if not any(start <= match.start() and match.end() <= end for start, end in action_spans):
            return 'summary_advice_repeats_measurement'
    intake_claim = re.compile(
        r'(?:今天|今日|全天)[^。！？!?；;\n]{0,24}?(?:只吃|总共摄入|总摄入只有)'
        r'|摄入\s*(?:明显|严重|已经|确实)?\s*(?:不足|过量)'
        r'|摄入的热量\s*(?:太少|太多)'
    )
    uncertainty = re.compile(
        r'(?:不能|无法|不应|不可|不足以)[^。！？!?；;\n]{0,24}(?:判断|认定|推断|说明|证明|断言)'
        r'|(?:不代表|不意味着|没有证据说明|没有证据表明)'
    )
    for clause in re.split(r'[。！？!?；;，,\n]|但是|但|然而|不过', text):
        for match in intake_claim.finditer(clause):
            prefix = clause[:match.start()]
            if uncertainty.search(prefix) or re.search(r'(?:避免|防止)\s*$', prefix):
                continue
            return 'summary_advice_infers_complete_intake'
    return None


def _summary_decimal(value: Any) -> Decimal | None:
    """Missing, nonnumeric, negative and nonfinite measurements stay unknown."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or not math.isfinite(float(number)):
            return None
        return number
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _summary_display(number: Decimal) -> str | None:
    try:
        value = float(number)
    except (OverflowError, ValueError):
        return None
    return str(format_display_number(value)) if math.isfinite(value) else None


def _summary_rows(plan: DailyReadPlan, dimension: str, payload: Any) -> list[dict] | None:
    if not isinstance(payload, dict) or result_declares_explicit_failure(payload):
        return None
    rows = payload.get('records')
    if not isinstance(rows, list) or payload.get('dimension', dimension) != dimension:
        return None
    if 'window' in payload and payload['window'] != {
        'start_date': plan.start_date, 'end_date': plan.end_date, 'timezone': plan.timezone,
    }:
        return None
    if payload.get('availability') not in (None, 'available', 'partial', 'no_data'):
        return None
    if rows and payload.get('availability') == 'no_data':
        return None
    for row in rows:
        if not isinstance(row, dict):
            return None
        try:
            row_date = date.fromisoformat(str(row.get('record_date'))).isoformat()
        except ValueError:
            return None
        if not plan.start_date <= row_date <= plan.end_date:
            return None
    return rows


def verified_daily_summary(
    plan: DailyReadPlan, payloads: dict[str, dict], goals: dict[str, dict],
    *, include_food_names: bool = True,
) -> str:
    """Render facts from already owner-scoped, verified current-turn reads.

    This is a presentation projection, not an authorization or query step.
    Record identity/cardinality is preserved: equal food names never cause a
    row to disappear. Sleep duration is stored/projected in minutes by the
    wearable ingestion contract, and is converted to hours only for display.
    """
    if not plan.is_summary:
        return ''
    date_label = plan.start_date if plan.start_date == plan.end_date else f'{plan.start_date}至{plan.end_date}'
    zone_label = '北京时间' if plan.timezone == 'Asia/Shanghai' else plan.timezone
    lines = [f'本次总结仅覆盖饮食与睡眠记录（{date_label}，{zone_label}）。'
             '已记录饮食不代表全天完整摄入，未记录不等于没有发生。']
    for dimension, label in (('diet', '饮食'), ('sleep', '睡眠')):
        goal = goals.get(dimension) or {}
        if goal.get('status') != 'verified' or goal.get('evidence_kind') != 'read_result':
            lines.append(f'{label}：本轮查询未完成，暂不汇总。')
            continue
        rows = _summary_rows(plan, dimension, payloads.get(dimension))
        if rows is None:
            lines.append(f'{label}：本轮查询结果无法核对，暂不汇总。')
            continue
        if not rows:
            suffix = '，不代表没有进食' if dimension == 'diet' else '，不能据此判断睡眠情况'
            lines.append(f'{label}：目标日期没有可用记录{suffix}。')
            continue
        count = format_display_number(len(rows))
        if dimension == 'diet':
            line = f'饮食：已记录{count}条。'
            known = [value for row in rows if (value := _summary_decimal(row.get('calories'))) is not None]
            total = _summary_display(sum(known, Decimal(0))) if known else None
            if total is None:
                line += '缺少可汇总的有效热量读数，无法给出已记录热量合计。'
            elif len(known) == len(rows):
                line += f'已记录热量合计{total}千卡。'
            else:
                missing = format_display_number(len(rows) - len(known))
                line += f'已知热量小计{total}千卡；另{missing}条缺少有效热量读数，无法给出完整合计。'
            for row in rows if include_food_names else ():
                food = row.get('food_name') or row.get('food_items')
                if isinstance(food, str) and food.strip() and not any(marker in food for marker in ('{', '}', '[', ']')):
                    line += f'记录中包括“{" ".join(food.split())[:36]}”。'
                    break
            lines.append(line)
        elif len(rows) != 1:
            lines.append(f'睡眠：查询到{count}条记录，未合并为单一读数，请查看明细。')
        else:
            duration = _summary_decimal(rows[0].get('total_sleep_duration'))
            score = _summary_decimal(rows[0].get('sleep_score'))
            hours_text = _summary_display(duration / Decimal(60)) if duration is not None else None
            score_text = _summary_display(score) if score is not None else None
            duration_fact = f'时长{hours_text}小时' if hours_text is not None else '时长缺少有效读数'
            score_fact = f'评分{score_text}' if score_text is not None else '评分缺少有效读数'
            lines.append(f'睡眠：{duration_fact}；{score_fact}。')
    return '\n\n'.join(lines)
