"""Separate an exercise answer's horizon from its explicitly requested evidence.

This closed, fully consumed grammar is an authority adapter, not an intent
classifier. Unknown owners, restrictions, quoted commands and extra clauses
stay on the existing fail-closed path. It never grants plan persistence.
"""
from dataclasses import dataclass
import json
import re

_SELF = r"(?:我(?:自己|本人|个人)?|本人)(?:的)?"
_HORIZON = r"(?:(?:未来|接下来|今后)?[0-9一二两三四五六七八九十百]{1,4}(?:天|周|个月)|今天|明天|本周|这周|下周|本月|下个月)"
_DRAFT = re.compile(
    rf"(?:请你?|麻烦你?)?(?:(?:帮|为|给)我)?(?:制定|起草|生成|设计|拟定|安排|规划)(?:一下)?"
    rf"(?:{_SELF})?(?P<horizon>{_HORIZON})?的?"
    r"(?:锻炼|运动|训练)(?:恢复|康复)?的?(?:计划|方案)?(?:草稿)?"
)
_TODAY_RECOMMENDATION = re.compile(
    r"今天(?:我)?是否适合运动[？?](?:请)?给我推荐适合我的运动(?:的)?方式"
    r"以及运动(?:的)?强度"
)
_PLAN_QUESTION = re.compile(
    rf"(?:请你?|麻烦你?)?(?:我)?(?P<horizon>{_HORIZON})"
    r"(?:应该|该|应|要)?(?:如何|怎么|怎样)(?:制定|安排|规划|设计)"
    r"(?:锻炼|运动|训练)(?:计划|方案)[？?]?"
)
_HTML_OUTPUT_SUFFIX = re.compile(
    r"[，,。；;](?:最终|最后)生成一个HTML页面$", re.IGNORECASE
)
_BASIS_ITEMS = {
    "profile": r"身体(?:状况|情况|状态)|健康(?:状况|情况|状态)",
    "medical_exam": r"体检报告|体检结果|检查报告|化验报告",
    "illness": r"历史记录的病症|既往病史|病史|病症记录|历史病症记录",
}
_SEPARATOR = re.compile(r"(?:[，,、]|以及|和|与|及)+")


@dataclass(frozen=True)
class ExercisePlanScope:
    horizon: str
    evidence_dimensions: tuple[str, ...]
    output_format: str = 'text'

    def queries(self) -> list[dict[str, str]]:
        return [{"dimension": d} for d in self.evidence_dimensions]


def resolve_exercise_plan_scope(text: str) -> ExercisePlanScope | None:
    # Do not strip quotes/markdown/reporting frames: those are not authority.
    normalized = re.sub(r"\s+", "", str(text or "")).rstrip("。.!！")
    # Consume only a closed, independent output-format suffix. The caller's
    # original message remains intact; HTML does not grant personal reads.
    output_format = 'html' if _HTML_OUTPUT_SUFFIX.search(normalized) else 'text'
    normalized = _HTML_OUTPUT_SUFFIX.sub("", normalized)
    if _TODAY_RECOMMENDATION.fullmatch(normalized):
        return ExercisePlanScope('今天', (), output_format)
    question = _PLAN_QUESTION.fullmatch(normalized)
    if question:
        return ExercisePlanScope(question['horizon'], (), output_format)
    direct = _DRAFT.fullmatch(normalized)
    if direct:
        return ExercisePlanScope(direct['horizon'] or '', (), output_format)
    # A basis declaration requires an explicit self owner; that owner may
    # govern a coordinated list, but no unmatched token can inherit it.
    basis = re.match(rf"(?:请你?)?(?:基于|结合|根据){_SELF}", normalized)
    if basis is None:
        return None
    remainder = normalized[basis.end():]
    candidates = list(re.finditer(r"(?:请你?|麻烦你?)?(?:(?:帮|为|给)我)?(?:制定|起草|生成|设计|拟定|安排|规划)", remainder))
    if len(candidates) != 1:
        return None
    split = candidates[0].start()
    draft = _DRAFT.fullmatch(remainder[split:])
    if draft is None:
        return None
    items = [i for i in _SEPARATOR.split(remainder[:split].rstrip('，,、')) if i]
    if not items:
        return None
    dimensions = []
    for item in items:
        item = re.sub(rf"^{_SELF}", "", item)
        domain = next((d for d, pattern in _BASIS_ITEMS.items() if re.fullmatch(pattern, item)), None)
        if domain is None:
            return None
        if domain != 'profile' and domain not in dimensions:
            dimensions.append(domain)
    return ExercisePlanScope(draft['horizon'] or '', tuple(dimensions), output_format)


def has_unresolved_exercise_plan_basis(text: str) -> bool:
    """Prevent a partial evidence request falling into an unrestricted report read.

    This detector only denies unsupported requests; the full parser above is
    the sole source of authority, including owners and evidence dimensions.
    """
    normalized = re.sub(r"\s+", "", str(text or ""))
    return bool(
        re.search(r"基于|结合|根据", normalized)
        and any(re.search(pattern, normalized) for pattern in _BASIS_ITEMS.values())
        and _DRAFT.search(normalized)
        and resolve_exercise_plan_scope(text) is None
    )


def exercise_plan_prompt(scope: ExercisePlanScope) -> str:
    return (
        '\n[本轮运动计划任务边界]\n'
        f'输出任务是运动计划草稿；计划期限：{scope.horizon or "用户未指定"}，不是历史查询窗口。'
        f'允许补充查询的依据仅为：{scope.queries()}。'
        '没有列出的个人数据不要额外查询，使用已提供的背景并说明未核验之处；不要误报为用户身份或权限问题。'
        '列出的依据必须实际查询，缺失或失败须说明，不能声称已完整审阅。'
        '体检查询返回的是已有指标/报告摘要，病史返回历史事件；都不能证明目前已康复或适合某训练强度。'
        '没有运动记录或健康证据缺失时，不能据此判断运动水平，'
        '不能据此认定无禁忌或今天适合运动；只提供明确前提下的通用选项。'
        '说明取数覆盖：体检沿用近365天指标与报告摘要，病史最多最近100条历史事件；这不是完整病历审阅。'
        '区分已知事实、未知风险与有条件的建议；不得开方、调整用药或作医疗安全保证。'
        '草稿不等于已保存、已执行或已创建提醒，不能调用写入或不受限的健康分析工具。'
        + (
            '\n[本轮静态 HTML 输出要求]\n'
            '用户要求的 HTML 页面是本条回复中的静态文档，不是图片、视频或创作任务。'
            '此处输出要求优先于通用创作说明；只能使用本轮实际开放的工具，'
            '不得调用 draft_aigc_media、保存、发布或其他写入工具。'
            '直接在唯一的 ```html 代码块中输出完整文档，包含 <!DOCTYPE html>、'
            '<html>、<head> 和 <body> 及各自闭合标签。正文使用标题、段落和列表。'
            '不使用 CSS、style 标签或 style 属性，不写表格、装饰容器或重复说明；'
            '正文不超过600个汉字，优先保证闭合所有标签及代码块。'
            '不含脚本、事件处理器、iframe、表单、网络请求或外部资源；'
            '不要声称已发布、保存或生成媒体。保留上述证据局限和有条件建议。'
            if scope.output_format == 'html' else ''
        )
    )


def exercise_plan_evidence_outcomes(scope: ExercisePlanScope, executions) -> list[dict]:
    """Attest actual adapter results, never the model's claim of having read."""
    from app.services.agent_write_outcome import result_declares_explicit_failure

    outcomes = {d: {'goal_id': 'plan_basis_' + d, 'kind': 'query', 'status': 'failed',
                    'reason_code': 'query_not_executed', 'query': {'dimension': d}}
                for d in scope.evidence_dimensions}
    for execution in executions:
        decision = execution.decision
        if (decision is None or decision.action != 'allow'
                or decision.reason != 'exercise_plan_explicit_evidence'
                or execution.tool_name != decision.normalized_tool_name):
            continue
        args = decision.normalized_args
        queries = [args] if execution.tool_name == 'health_query' else args.get('queries', [])
        raw = str(execution.content or '').strip()
        payloads = {}
        if execution.tool_name == 'health_query':
            payloads[args.get('dimension')] = raw
        elif execution.tool_name == 'health_query_batch':
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict) and payload.get('status') == 'success':
                rows = payload.get('results')
                if (isinstance(rows, list) and len(rows) == len(queries)
                        and all(isinstance(row, dict) and isinstance(row.get('dimension'), str)
                                and isinstance(row.get('data'), str) for row in rows)
                        and len({row['dimension'] for row in rows}) == len(rows)):
                    payloads = {row['dimension']: row['data'] for row in rows}
        for query in queries:
            d = query.get('dimension')
            if d not in outcomes or query != {'dimension': d}:
                continue
            content = payloads.get(d, '').strip()
            verified = bool(content and not content.startswith('Error:')
                            and not result_declares_explicit_failure(content))
            if outcomes[d]['status'] != 'verified':
                outcomes[d].update(status='verified' if verified else 'failed',
                                   evidence_kind='read_result' if verified else '',
                                   reason_code='query_verified' if verified else 'query_result_unavailable')
    return list(outcomes.values())


def exercise_plan_scope_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest,
        authorization_module_behavior_names,
    )
    return {
        'version': 'exercise-plan-scope-v1',
        'grammar': authorization_grammar_digest(globals()),
        'basis_items': dict(_BASIS_ITEMS),
        'behavior': authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)),
    }
