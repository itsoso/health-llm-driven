"""Ephemeral completion projection from owner-bound reads, never model prose.

The caller supplies the scope resolved from this authenticated turn and actual
ToolExecutionResults. This module neither authorizes reads nor verifies user
identity; the scoped dispatcher does that. Sync job receipts are not read data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re
from typing import Iterable

from app.services.agent_daily_read_execution import _summary_decimal, _summary_display
from app.services.agent_kernel.read_task_scope import OwnedReadScope
from app.services.agent_kernel.types import ToolExecutionResult
from app.services.agent_query_window import parse_query_window
from app.services.agent_write_outcome import result_declares_explicit_failure
from app.services.genui.table_builder import load_tool_result_json
from app.utils.number_format import format_display_number

_LABELS = {"diet": "饮食", "sleep": "睡眠", "workout": "运动", "supplements": "补剂", "spo2": "血氧"}
_ACTUAL_SOURCES = {
    "workout": ("owned_actual_workout_records", {"workout_record", "exercise_record"}),
    "supplements": (
        "owned_actual_supplement_intake_logs",
        {"supplement_intake", "supplement_taken_log"},
    ),
}
_TERMINAL = {"success", "completed", "complete", "ok", "succeeded"}


@dataclass(frozen=True)
class ComposedReadCompletion:
    goals: tuple[dict, ...]
    missing_dimensions: tuple[str, ...]
    trusted_fact_summary: str
    complete: bool
    verified_evidence: dict | None = None


# These fields mirror the bounded calendar and actual-intake adapters. Extra
# record metadata never enters the answer model; source identity stays data.
_EVIDENCE_FIELDS = {
    "spo2": ("record_date", "daily_metrics", "daily_sources", "sample_summaries"),
    "diet": ("id", "record_date", "meal_type", "meal_time", "food_name", "food_items",
             "quantity", "unit", "calories", "protein", "carbs", "fat", "fiber"),
    "sleep": ("record_date", "sleep_score", "total_sleep_duration", "deep_sleep_duration",
              "rem_sleep_duration", "light_sleep_duration", "awake_duration",
              "sleep_start_time", "sleep_end_time", "sources", "source_row_updates"),
    "workout": ("id", "record_kind", "source_table", "record_date", "workout_type",
                "duration_seconds", "distance_meters", "calories", "avg_heart_rate"),
    "supplements": ("id", "record_kind", "source_table", "record_date", "taken",
                    "supplement_name", "dosage", "unit", "intake_time"),
}
_NUMERIC_FIELDS = frozenset({
    "quantity", "calories", "protein", "carbs", "fat", "fiber", "sleep_score",
    "total_sleep_duration", "deep_sleep_duration", "rem_sleep_duration",
    "light_sleep_duration", "awake_duration", "duration_seconds", "distance_meters",
    "avg_heart_rate", "dosage",
})
_FIELD_UNITS = {
    "spo2": {"daily_metrics": "percent", "sample_summaries": "percent; data_points=count"},
    "diet": {"calories": "kcal", "protein": "g", "carbs": "g", "fat": "g", "fiber": "g",
             "quantity": "per_record_unit"},
    "sleep": {**{field: "minutes" for field in _EVIDENCE_FIELDS["sleep"] if field.endswith("_duration")},
              "sleep_score": "points"},
    "workout": {"duration_seconds": "seconds", "distance_meters": "meters",
                "calories": "kcal", "avg_heart_rate": "beats_per_minute"},
    "supplements": {"dosage": "per_record_unit_unknown_if_unit_missing"},
}


def _evidence_value(field, value):
    if field == 'daily_metrics':
        if isinstance(value, dict) and set(value) == {'spo2_avg', 'spo2_min', 'spo2_max'} and all(
            v is None or (type(v) in {int, float} and _summary_decimal(v) is not None) for v in value.values()
        ):
            return dict(value)
        return None
    if field == 'sample_summaries':
        if isinstance(value, list) and all(
            isinstance(row, dict) and set(row) == {'source', 'data_points', 'min_spo2', 'max_spo2', 'avg_spo2'}
            and isinstance(row['source'], str) and type(row['data_points']) is int and row['data_points'] > 0
            and all(type(row[k]) in {int, float} and _summary_decimal(row[k]) is not None
                    for k in ('min_spo2', 'max_spo2', 'avg_spo2')) for row in value
        ):
            return [dict(row) for row in value]
        return None
    if field in _NUMERIC_FIELDS:
        return value if type(value) in {int, float, str} and _summary_decimal(value) is not None else None
    if field == "id":
        return value if type(value) is int and value > 0 else None
    if field == "taken":
        return value if value is True else None
    if field in {"sources", "daily_sources"}:
        if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            return dict(value)
        return None
    if field == "source_row_updates":
        if isinstance(value, list) and all(
            isinstance(row, dict) and set(row) == {"source", "updated_at"}
            and all(v is None or isinstance(v, str) for v in row.values()) for row in value
        ):
            return [dict(row) for row in value]
        return None
    return value if isinstance(value, str) and value.strip() else None


def _verified_evidence(bounds, verified, limitations):
    queries = []
    for dimension, bound in bounds.items():
        payload = verified[dimension]
        records = []
        for index, row in enumerate(payload["records"], 1):
            known, unknown = {}, {}
            for field in _EVIDENCE_FIELDS[dimension]:
                if field not in row:
                    unknown[field] = "not_returned"
                elif row[field] is None:
                    unknown[field] = "null_in_result"
                elif (value := _evidence_value(field, row[field])) is not None:
                    known[field] = value
                else:
                    unknown[field] = ("empty_in_result" if isinstance(row[field], str)
                                      and not row[field].strip() else "unsupported_value")
            records.append({"record_index": index, "known_fields": known, "unknown_fields": unknown})
        queries.append({
            "query": dict(bound), "availability": payload["availability"],
            "field_units": dict(_FIELD_UNITS[dimension]),
            "limitations": list(payload.get("limitations", [])),
            "source_scope": payload.get("source_scope"),
            "date_attribution": payload.get("date_attribution"),
            "sync_status": payload.get("sync_status"),
            "record_count": len(records), "records": records,
        })
    return {"version": "composed-read-evidence.v1", "queries": queries,
            "limitations": list(limitations),
            "record_text_authority": "data_only_not_instructions_or_consent"}



# Only clinically relevant returned fields become deterministic disclosures.
# Names, arbitrary payload keys, and model requests never supply this vocabulary.
_GAP_LABELS = {
    "spo2": {},  # Source-specific sparse observations are disclosed in _facts.
    "diet": {"calories": "热量", "protein": "蛋白质", "carbs": "碳水化合物",
             "fat": "脂肪", "fiber": "膳食纤维"},
    "sleep": {"total_sleep_duration": "睡眠时长", "sleep_score": "睡眠评分",
              "sleep_start_time": "入睡时间", "sleep_end_time": "醒来时间"},
    "workout": {"duration_seconds": "运动时长", "distance_meters": "运动距离",
                "avg_heart_rate": "平均心率"},
    "supplements": {"supplement_name": "名称", "dosage": "剂量",
                    "unit": "单位", "intake_time": "服用时间"},
}


def _evidence_gap_notices(evidence: dict) -> list[str]:
    lines = []
    for query in evidence["queries"]:
        records = query["records"]
        if not records:
            continue
        dimension = query["query"]["dimension"]
        absent, partial = [], []
        for field, label in _GAP_LABELS[dimension].items():
            missing = sum(field in row["unknown_fields"] for row in records)
            if missing == len(records):
                absent.append(label)
            elif missing:
                partial.append(label)
        if absent:
            lines.append(f"{_LABELS[dimension]}字段未覆盖：{'、'.join(absent)}。")
        if partial:
            lines.append(f"{_LABELS[dimension]}部分记录缺失字段：{'、'.join(partial)}。")
    return lines


# A bounded meal log cannot attest full-day nutritional sufficiency. Parse only
# a finite evaluative grammar; record descriptions are not nutritional claims.
_NUTRITION_SUBJECT = re.compile(
    r"(?:营养|膳食|饮食)(?:摄入|覆盖|结构|搭配|种类|质量)?"
    r"|(?:蛋白质|蔬果|蔬菜|水果)(?:摄入量|摄入|吃得|量)?|总摄入"
)
_NUTRITION_NEGATION = (
    r"并不意味着|不意味着|不等于|不代表|并不是|并没有|不是|并非|并无|并不|"
    r"不存在|没有|未发现|未见|未必|不一定|不能说|不"
)
_NUTRITION_MODIFIER = (
    r"可能|似乎|或许|比较|较为|较|过于|相对|稍微|稍显|略显|有些|有点|仍|"
    r"明显|存在|有|非常|十分|极其|严重|完全|绝对|一点也|就|几乎|基本|很|太|偏|过|稍|略|够"
)
_NUTRITION_OPERATOR = re.compile(_NUTRITION_NEGATION)
_NUTRITION_EPISTEMIC_OPERATOR = re.compile(r"未发现|未见|未必|不一定|不能说|不意味着|不等于|不代表")
_NUTRITION_PREDICATE = re.compile(
    rf"(?P<operators>(?:(?:{_NUTRITION_NEGATION}|{_NUTRITION_MODIFIER})[^\S\n]*){{0,12}})"
    r"(?P<deficit>不足|不够|缺乏|欠缺|欠均衡|失衡|欠佳|单一|单调|有限|不佳|没吃|未吃|低|少|差)"
    r"(?=\W|$|了|的|与否|尚|仍|目前|无法|并不)"
    r"|(?P<adequate_operators>(?:(?:" + _NUTRITION_NEGATION + "|" + _NUTRITION_MODIFIER
    + r")[^\S\n]*){0,12})(?P<adequate>均衡|多样|合理|充足|全面|丰富|多|高)"
    r"(?=\W|$|了|的|与否|尚|仍|目前|无法|并不)"
)
_NUTRITION_PREFIX_CHAIN = re.compile(
    rf"(?:(?:{_NUTRITION_NEGATION})[^\S\n]*(?:(?:完全|绝对|一点也|就)[^\S\n]*)?)+"
    r"(?:证据(?:证明|表明|显示|支持))?[^\S\n]*$"
)
_NUTRITION_UNKNOWN = re.compile(
    r"(?:无法|不能|难以)(?:判断|确认|确定)|不确定|不明确|未知|不清楚"
)
_NUTRITION_UNKNOWN_PREFIX = re.compile(
    r"(?:不能据此|不能仅凭|无法证明|无法判断|无法确认|无法确定|尚无证据|"
    r"缺乏(?:充分|足够|可靠|直接|明确|已核验)?的?证据)"
)
_NUTRITION_CLAUSE_BREAK = re.compile(r"[。；;!?！？\n]|但是|但|不过(?!量|度|高|低)|然而|而是|却")


def _nutrition_assertion_in_clause(clause: str) -> bool:
    for subject in _NUTRITION_SUBJECT.finditer(clause):
        rest = clause[subject.end():]
        # An evaluative predicate must directly follow this subject. Searching
        # arbitrary later text would attribute record counts to personal intake.
        predicate = _NUTRITION_PREDICATE.match(rest.lstrip())
        if predicate is None:
            continue
        prefix = re.split(r"[，,]", clause[:subject.start()])[-1]
        suffix = rest.lstrip()[predicate.end():]
        operators = predicate.group("operators") or predicate.group("adequate_operators") or ""
        negations = _NUTRITION_OPERATOR.findall(operators)
        deficit = bool(predicate.group("deficit")) ^ bool(len(negations) % 2)
        if not deficit:
            continue
        # Unknown existence covers the claim; unknown cause or severity does not.
        if ((re.search(r"(?:是否(?:存在)?|有无)\s*$", prefix)
             or re.match(r"\s*与否", suffix)) and _NUTRITION_UNKNOWN.search(suffix)):
            continue
        if re.match(r"\s*的?证据(?:不足|不够|缺乏|有限)", suffix):
            continue
        if _NUTRITION_UNKNOWN_PREFIX.search(prefix):
            continue
        chain = _NUTRITION_PREFIX_CHAIN.search(prefix)
        if chain and len(_NUTRITION_OPERATOR.findall(chain.group())) % 2:
            continue
        if _NUTRITION_EPISTEMIC_OPERATOR.search(operators) and len(negations) % 2:
            continue
        return True
    return False


# A record-only read cannot attest clinical recovery, training safety, or a
# regimen. Unlike meal descriptions, these claims remain unsupported even if
# every requested row and field was returned: there is no clinical assessment
# or prescribed plan in this evidence contract.
_HEALTH_SUBJECT = (
    r"(?:睡眠(?:恢复|质量)|恢复(?:水平|质量|状态|程度|能力|情况)?|"
    r"你(?:的)?(?:身体)?状态|身体(?:状态|状况)?|生活(?:节奏|作息|状态)|作息|"
    r"训练(?:量|负荷|状态|强度)?|运动(?:量|负荷|强度|安全性)?|(?:总体)?情况|(?:各项)?指标|一切|状态|你)"
)
_HEALTH_LINK = (
    r"(?:的|得|是|为|属于|呈现(?:出|为)?|表现为|处于|达到|已经|目前|总体|整体|"
    r"看起来|显得|似乎|可能|相对|比较|较为|非常|很|太|偏|稍|仍然|仍|还|了|"
    r"并非|并不|并没有|没有|并|不|是否|有无|能否|较)"
)
_HEALTH_EVALUATION = (
    r"(?:中等偏好|不错|尚可|理想|还可以|良好|稳定|规律|正常|安全|合理|适宜|适量|充分|充足|足够|"
    r"健康|欠佳|不佳|较差|过量|过度|康复|痊愈|恢复|好|差)"
)
_HEALTH_ABSENCE = (
    r"(?:没有(?:发现|看到)?|未见|未发现|不存在|看不到|无|没什么|没啥|没)"
    r"(?:(?:明显|任何|显著|需要(?:紧急)?关注的)\s*){0,3}"
    r"(?:异常(?:信号|情况)?|过度训练|安全风险|健康风险|值得担心|问题)"
)
_CURRENT_HEALTH_CLAIM = re.compile(
    r"(?P<subject>" + _HEALTH_SUBJECT + r")\s*(?:" + _HEALTH_LINK + r"\s*){0,12}"
    r"(?P<evaluation>" + _HEALTH_EVALUATION + r")|" + _HEALTH_ABSENCE
    + r"|中等偏好|(?:稳定|良好|充分)(?:的)?恢复|(?:早已|已经)痊愈"
    r"|(?:目前)?(?:已经|已)恢复|恢复了"
)
_RECORD_OPERATION_SUBJECT = re.compile(
    r"(?:查询|调用|返回|接口|字段|格式|解析|记录校验|记录本身|记录格式)"
    r"(?:结果|过程|状态|结构)?[^，,。；;!?！？\n]{0,8}$"
)
_CLAIM_UNKNOWN_PREFIX = re.compile(
    _NUTRITION_UNKNOWN_PREFIX.pattern
    + r"|不代表|不意味着|不等于|不能说明|不能证明|不能断言|不支持|不能判断|难以判断"
)
# One finite operation grammar for both normal text and presentation wrapping.
# It must end at a conclusion action, never span unrelated advice or punctuation.
_HEALTH_PROHIBITION_OPERATOR = r"(?:不必|不要|不应|不可|避免|不建议|不宜)"
_HEALTH_CONCLUSION_PROHIBITION = (
    _HEALTH_PROHIBITION_OPERATOR + r"{gap}(?:(?:急于|急着|轻易|贸然|直接){gap})?"
    r"(?:(?:仅凭|只凭|根据|依据|凭){gap}"
    r"(?:(?:(?:(?:最近|过去){gap})?几天|这些|少量|部分|本轮|当前|现有){gap})?(?:的{gap})?"
    r"(?:记录(?:{gap}样本)?|样本|生活数据){gap})?"
    r"(?:(?:给|为){gap}(?:自己|你){gap})?"
    r"(?:(?:用来|用于){gap})?(?:下|得出|做出|作出|判断|认定|认为|断言|推断)"
)
_HEALTH_INABILITY_OPERATION = (
    r"(?:不能|无法|难以){gap}(?:(?:据此|由此|因此){gap})?(?:直接{gap})?"
    r"(?:得出|推出|推断|断言|断定|认定|说明|证明|判断)"
)
_HEALTH_CONCLUSION_ENUMERATION = (
    r"(?:(?:你{gap})?(?:当前{gap})?(?:的{gap})?"
    r"(?:(?:免疫|恢复|运动|补剂|状态|训练){gap}(?:、|和|及|与|或){gap})+)?"
)
_HEALTH_CONCLUSION_UNKNOWN = re.compile(
    _CLAIM_UNKNOWN_PREFIX.pattern
    + r"|" + _HEALTH_INABILITY_OPERATION.replace("{gap}", "")
    +
    r"|(?:没有|缺乏|缺少)(?:足够|充分|可靠)?的?(?:依据|证据)(?:来)?(?:得出|推断|断言|断定|认定)"
    r"|(?:没有|尚无|缺乏)[^，,]{0,10}证据(?:证明|表明|显示|支持)?\s*$"
    + r"|" + _HEALTH_CONCLUSION_PROHIBITION.replace("{gap}", "")
)
_HEALTH_UNCERTAINTY_NEGATION = re.compile(
    r"(?:并非|不是|并不|不|未必|不一定)\s*(?:(?:说|真的|完全|绝对|一定)\s*)?$"
)
_HEALTH_FORMAT_GAP = r"[^\S\r\n]*(?:\r?\n[^\S\r\n]*)?"
_HEALTH_UNCERTAINTY_OPERATION_WRAP = re.compile(
    r"(?:" + _HEALTH_INABILITY_OPERATION.replace("{gap}", _HEALTH_FORMAT_GAP)
    + r"|(?:没有|尚无|缺乏|缺少)(?:" + _HEALTH_FORMAT_GAP + r"(?:足够|充分|可靠))?"
    r"(?:" + _HEALTH_FORMAT_GAP + r"的)?" + _HEALTH_FORMAT_GAP + r"(?:依据|证据)"
    r"(?:" + _HEALTH_FORMAT_GAP + r"来)?" + _HEALTH_FORMAT_GAP
    + r"(?:得出|推断|断言|断定|认定|证明|表明|显示|支持)"
    r"|不" + _HEALTH_FORMAT_GAP + r"(?:代表|意味着|等于|支持)"
    + r"|" + _HEALTH_CONCLUSION_PROHIBITION.replace("{gap}", _HEALTH_FORMAT_GAP) + r")"
    + _HEALTH_FORMAT_GAP + _HEALTH_CONCLUSION_ENUMERATION.replace("{gap}", _HEALTH_FORMAT_GAP)
    + r"(?=[“‘\"'（(]*(?:" + _CURRENT_HEALTH_CLAIM.pattern
    + r"|(?:已|已经)?" + _HEALTH_SUBJECT + r"))"
)
_HEALTH_UNCERTAINTY_WRAP = re.compile(
    _HEALTH_UNCERTAINTY_NEGATION.pattern.removesuffix("$").replace(r"\s*", _HEALTH_FORMAT_GAP)
    + r"(?=不能|无法|难以|没有|尚无|缺乏|缺少|不代表|不意味着|不等于|不支持|"
    + _HEALTH_PROHIBITION_OPERATOR + r")"
)
_EXERCISE_TOPIC = re.compile(r"运动|训练|锻炼|练|走|健身|力量|有氧|阻力|散步|步行|跑步|深蹲|划船|弹力带|俯卧撑|骑行|游泳")
_EXERCISE_QUANTITY = re.compile(
    r"半(?:个)?小时|(?:[一二两三四五六七八九十百\d]+(?:\.\d+)?\s*"
    r"(?:[–—~～至到-]\s*[一二两三四五六七八九十百\d]+(?:\.\d+)?)?"
    r"\s*(?:次|回|组|分钟|个小时|小时|公里|km|米|个))"
)
_EXERCISE_PLAN_ACTION = re.compile(
    r"建议|可以|应该|应当|请|加入|增加|提高|过渡到|开始|安排|合理的起点|即可|就行|照做|做|练|锻炼|运动|走"
)
_EXERCISE_RECORD_DATE = r"(?:\d{4}[-/年])?\d{1,2}[-/月.]\d{1,2}日?"
_EXERCISE_RECORD_COUNT = re.compile(
    r"^(?:" + _EXERCISE_RECORD_DATE
    + r"(?:\s*[–—~～至到-]\s*" + _EXERCISE_RECORD_DATE + r")?\s*)?"
    r"(?:(?:每天|每日|当天|当日)\s*)?(?:约\s*)?"
    r"(?:[一二两三四五六七八九十百\d]+\s*条\s*记录|"
    r"(?:有|共|记录了)(?:约\s*)?[一二两三四五六七八九十百\d]+\s*条)"
)
_EXERCISE_RECORD_CHECK = re.compile(
    r"(?:(?:建议|可以|应该|请)\s*)?(?:(?:每周|每天|每日|一周)\s*)?"
    r"(?:查看|核对|检查|回看|对比|整理|统计|分析)"
    r"[^，,。；;!?！？\n]{0,24}?(?:记录|条目)"
)
_EXERCISE_EVENT_READ = re.compile(
    r"(?:分析|只看|查询|查看|回看|对比|统计)(?:一下)?\s*"
    r"(?:某|这|那|第)?[一二两三四五六七八九十\d]+次(?:的)?\s*"
    r"(?:运动|训练|锻炼|散步|步行|跑步|骑行|游泳)"
    r"(?:后的(?:状态|情况)|的(?:记录|详情|数据))?"
)
_SUPPLEMENT_REMINDER_ACTION = re.compile(
    r"留意|注意|记得|别忘(?:了)?|不要忘(?:记)?|别漏(?:掉)?|别落下|不要漏(?:掉)?|提醒|"
    r"(?:可以)?(?:看看|检查|核对)"
)
_SUPPLEMENT_OBJECT = re.compile(r"补剂|保健品|维生素|鱼油|辅酶(?:Q10)?|红景天|叶酸|NAC|NMN", re.I)
_INTAKE_OR_ADHERENCE_ACTION = re.compile(r"服用(?!时间|记录)|漏(?:服|吃|了|掉)?|吃|补打卡")
_RECORD_OR_HANDLING_OBJECT = re.compile(r"记录|字段|名称|剂量|单位|服用时间|包装|标签|批号|照片")


def _asserted_record_only_claim(pattern: re.Pattern, clause: str) -> bool:
    for match in pattern.finditer(clause):
        prefix = re.split(r"[，,]|但是|但|不过|然而|而是|却|——", clause[:match.start()])[-1]
        suffix = clause[match.end():]
        unknown_pattern = _HEALTH_CONCLUSION_UNKNOWN if pattern is _CURRENT_HEALTH_CLAIM else _CLAIM_UNKNOWN_PREFIX
        unknown = unknown_pattern.search(prefix)
        # Every current-health uncertainty form uses the same local polarity
        # check; the older grammar must not bypass it with an early exemption.
        if unknown and (pattern is not _CURRENT_HEALTH_CLAIM
                        or not _HEALTH_UNCERTAINTY_NEGATION.search(prefix[:unknown.start()])):
            continue
        if pattern is _CURRENT_HEALTH_CLAIM:
            if match.group("evaluation") == "健康" and re.match(r"(?:背景|档案|资料|记录)", suffix):
                # A health-profile noun does not assert that its owner is healthy.
                continue
            if (match.group("subject") is None
                    or (match.group("subject") == "状态" and match.group("evaluation") == "正常")) and _RECORD_OPERATION_SUBJECT.search(prefix):
                continue
            if (match.group("evaluation") in {"稳定", "规律"}
                    and re.search(r"(?:已记录|记录中的|本轮已返回)[^，,]{0,8}$", prefix)
                    and not re.search(r"你|身体|生活", match.group("subject") or "")):
                continue
        else:
            chain = _NUTRITION_PREFIX_CHAIN.search(prefix)
            if chain and len(_NUTRITION_OPERATOR.findall(chain.group())) % 2:
                continue
        if re.match(r"\s*的?证据(?:不足|不够|缺乏|有限)", suffix):
            continue
        decision_unknown = (_NUTRITION_UNKNOWN.search(suffix)
                            or re.search(r"(?:应|需|需要)(?:由)?(?:医生|药师)(?:判断|评估|确认)", suffix))
        if ("是否" in prefix + match.group() or "有无" in prefix + match.group()) and decision_unknown:
            continue
        if pattern is _CURRENT_HEALTH_CLAIM and re.match(r"\s*(?:如果|若|假如)", prefix):
            # A hypothetical recovery condition is not a claimed assessment.
            # Exercise prescriptions are independently checked below.
            continue
        if pattern is not _CURRENT_HEALTH_CLAIM and re.search(r"(?:不要|不建议|请勿|不得|不能)[^，,]{0,24}$", prefix):
            continue
        return True
    return False


def _quantified_exercise_plan(clause: str) -> bool:
    # Carry an exercise proposal only into adjacent short clauses without a new
    # record/read subject or another domain. This supports "力量训练，每周两次"
    # without pairing a factual duration with an unrelated record-check request.
    carried = ""
    for part in re.split(r"[，,]|然后|接下来", clause):
        part = part.strip()
        record_only = ((re.match(r"(?:每周|每天)?(?:已记录|记录显示|记录中|本轮返回的记录|(?:运动|训练|锻炼)(?:记录|日志))", part)
                        or _EXERCISE_RECORD_COUNT.match(part))
                       and not re.search(r"建议|应该|应当|可以|请|安排|加入|增加|提高|开始|计划|方案|处方", part))
        if record_only:
            carried = ""
            continue
        part = _EXERCISE_RECORD_CHECK.sub("", part)
        # Project the finite read operation, including its event count, rather
        # than interpreting "分析某一次散步" as a prescribed exercise frequency.
        # Later actions in this clause remain visible to the safety check.
        part = _EXERCISE_EVENT_READ.sub("", part)
        if re.search(r"睡眠|饮食|补剂|情绪|工作", part) and not _EXERCISE_TOPIC.search(part):
            carried = ""
            continue
        window = (carried + "，" + part) if carried else part
        if (_EXERCISE_TOPIC.search(window) and _EXERCISE_QUANTITY.search(window)
                and _asserted_record_only_claim(_EXERCISE_PLAN_ACTION, window)):
            return True
        carried = window if _EXERCISE_TOPIC.search(window) and len(window) <= 80 else ""
    return False


def _supplement_adherence_nudge(clause: str) -> bool:
    previous_object = False
    previous_missing_log = False
    for part in re.split(r"[，,]|然后|接下来", clause):
        local_object = bool(_SUPPLEMENT_OBJECT.search(part))
        for action in _SUPPLEMENT_REMINDER_ACTION.finditer(part):
            prefix, tail = part[:action.start()], part[action.end():]
            if (_CLAIM_UNKNOWN_PREFIX.search(prefix)
                    or re.search(r"(?:不要|不建议|请勿|不得|不能)[^，,]{0,18}$", prefix)):
                continue
            # The recipient/purpose is a clinician, not an ingestion action.
            # Only this local action is exempt; later reminders are examined.
            if (re.match(r"(?:了)?(?:问|咨询|请教|告诉|提醒|告知)[^，,]{0,8}(?:医生|药师)", tail)
                    or re.match(r"(?:医生|药师)", tail)
                    or re.match(r"(?:带|携带)[^，,]{0,20}(?:医生|药师)", tail)):
                continue
            intake = _INTAKE_OR_ADHERENCE_ACTION.search(tail)
            if intake and (local_object or previous_object or re.search(r"服用(?!时间|记录)|漏服", tail)):
                return True
            if (local_object and re.match(r"别忘|不要忘|别漏|别落下|不要漏", action.group())
                    and not _RECORD_OR_HANDLING_OBJECT.search(tail)):
                return True
            if previous_missing_log and re.match(r"提醒", action.group()) and "自己" in tail:
                return True
        previous_object = local_object
        previous_missing_log = local_object and bool(re.search(r"(?:没|未|暂无)[^，,]{0,8}(?:打卡|记录)", part))
    return False


_EXISTING_REGIMEN_CONTINUATION = re.compile(
    r"(?:继续\s*(?:按(?:照)?|执行|遵循)?|维持|沿用)\s*"
    r"(?:原(?:来|有)?|既定|既往|现有)的?(?:治疗|用药|补剂|运动)?方案"
)
_REGIMEN_PROHIBITION = re.compile(r"(?:不要|不建议|请勿|不得|不能(?:据此)?(?:建议)?)\s*$")


def _unverified_regimen_continuation(clause: str) -> bool:
    # A read-only record bundle does not verify a currently applicable clinician
    # plan. Conditional mentions of a doctor cannot authorize regimen adherence.
    for part in re.split(r"[，,]|但是|但|不过|然而|而是|却", clause):
        for match in _EXISTING_REGIMEN_CONTINUATION.finditer(part):
            prefix = part[:match.start()]
            prohibition = _REGIMEN_PROHIBITION.search(prefix)
            if prohibition and not _HEALTH_UNCERTAINTY_NEGATION.search(prefix[:prohibition.start()]):
                continue
            return True
    return False


def enforce_composed_synthesis_boundaries(text: str, completion):
    from app.services.guidance_validator import (
        GuidanceValidationResult, _medical_assertion_matching_text,
    )

    evidence = completion.verified_evidence if completion is not None and completion.complete else None
    if not evidence or len(evidence["queries"]) < 2:
        return GuidanceValidationResult(text=text)
    # Formatting normalization is confined to the matching view. Accepted text
    # is returned byte-for-byte, including its uncertainty and record qualifiers.
    normalized = re.sub(r"[*_`]", "", _medical_assertion_matching_text(text))
    clauses = _NUTRITION_CLAUSE_BREAK.split(normalized)
    reasons = []
    if (any(q["query"]["dimension"] == "diet" for q in evidence["queries"])
            and any(_nutrition_assertion_in_clause(c) for c in clauses)):
        reasons.append("unsupported_nutrition_inference")
    # Fold only finite uncertainty operations and an adjacent health predicate,
    # then their outer-negation chain. A gap cannot span an empty paragraph.
    # Sentence boundaries and other domain matching views remain unchanged.
    health_normalized = _HEALTH_UNCERTAINTY_OPERATION_WRAP.sub(
        lambda match: re.sub(r"\s+", "", match.group()), normalized,
    )
    health_normalized = _HEALTH_UNCERTAINTY_WRAP.sub(
        lambda match: re.sub(r"\s+", " ", match.group()), health_normalized,
    )
    if any(_asserted_record_only_claim(_CURRENT_HEALTH_CLAIM, c)
           for c in _NUTRITION_CLAUSE_BREAK.split(health_normalized)):
        reasons.append("unsupported_current_health_inference")
    if any(_quantified_exercise_plan(c) for c in clauses):
        reasons.append("unsupported_exercise_program")
    if any(_supplement_adherence_nudge(c) for c in clauses):
        reasons.append("unsupported_supplement_adherence")
    if any(_unverified_regimen_continuation(c) for c in clauses):
        reasons.append("unsupported_existing_regimen")
    if not reasons:
        return GuidanceValidationResult(text=text)
    notices = {
        "unsupported_existing_regimen": "本轮记录未核实当前适用的医嘱，不能据此建议继续原有或既定方案。",
        "unsupported_nutrition_inference": "本轮记录不能支持营养不足的个体判断，相关推断未通过证据校验。",
        "unsupported_current_health_inference": "本轮记录不能证明当前恢复质量、训练安全或没有健康异常。",
        "unsupported_exercise_program": "本轮记录不足以制定或背书个体化的量化运动方案。",
        "unsupported_supplement_adherence": "缺少服用计划和时点证据，不能根据未见记录提示服用或推断漏服。",
    }
    return GuidanceValidationResult(
        text=completion.trusted_fact_summary + "\n\n"
        + "\n".join(notices[reason] for reason in reasons),
        flagged=True, violations=reasons,
    )


# Re-asking an already resolved date/module is navigation text, not analysis.
# This presentation projection runs only AFTER medical checks on the full text.
_META_QUERY_INVITATION = re.compile(
    r"(?:如需|如果|若|想要|希望)[^。！？!?\n]{0,24}(?:分析|复盘|比较)[^。！？!?\n]{0,8}"
    r"(?:可|可以|请|你可以)(?:指定|选择|告诉我)[^。！？!?\n]{0,20}(?:某一天|日期|某个问题|范围|模块)|"
    r"(?:请|你可以)(?:指定|选择|告诉我)[^。！？!?\n]{0,20}(?:想分析|想查询|查询范围|日期|模块)|"
    r"(?:你想|你希望)(?:先)?(?:看|分析|查询)[^。！？!?\n]{0,20}(?:还是|哪个)|"
    r"(?:如果|若|如需|希望|想要)[^。！？!?\n]{0,80}(?:告诉我|指定|选择)"
    r"[^。！？!?\n]{0,80}(?:分析|评估|判断|记录|补剂|睡眠|饮食|运动|日期|某一天|方向|范围)|"
    r"需要我[^。！？!?\n]{0,16}(?:哪个方向|哪(?:个|一)?(?:模块|方面))"
    r"[^。！？!?\n]{0,16}(?:展开|分析|继续)"
)
_META_QUERY_FOLLOWUP = re.compile(
    r"^(?:例如|比如)[^。！？!?\n]*(?:分析|只看|查询)|"
    r"^我(?:会|将)(?:基于已验证记录)?继续做(?:单日|单领域)"
)

_META_CONTINUE_ACTION = re.compile(r"继续|接着|深入|展开|分析|评估|查询|看看|看")
_META_SELECTION = re.compile(r"哪个|哪一项|哪一方面|哪方面|哪(?:个|一)?方向|要不要|某个模块")
_META_RECORD_CAPTURE = re.compile(
    r"(?:如果|若)你(?:实际)?有吃午餐[，,]\s*建议(?:随手)?记一下|"
    r"(?:下次|后续)打卡时(?:请)?(?:带上|填上|补上|附上|提供)(?:具体)?(?:品名|名称|剂量)"
)
_META_COLLECTION_ACTION = re.compile(r"告诉我|补充|提供|补齐|补全|记录|收集|完善")
_META_COLLECTION_FIELD = re.compile(
    r"补剂(?:名称)?|剂量|服用时间|单位|情绪|主观感受|工作压力|午餐|加餐|"
    r"入睡时间|醒来时间|睡眠时间|设备(?:名称|信息|来源)"
)
_META_COLLECTION_REQUEST = re.compile(
    r"(?:请|建议(?:后续|你)?|需要|你可以|可以|记得|希望你|希望)"
    r"(?:再|先|继续|后续|简单地?|主动)?\s*$"
)

_META_GENERAL_QUESTION = re.compile(
    r"(?:还|你还|你|您)?(?:想|要|需要)(?:我)?(?:接着|继续)?"
    r"(?:了解|分析|展开|深入|做|继续)(?:什么|吗)[?？]?"
)
_META_HELP_OFFER = re.compile(
    r"(?:有(?:其他)?问题|如需|如果需要|若需)(?:更多|进一步|其他|更深入)?"
    r"(?:分析|帮助|复盘|信息|建议|解答)?(?:请|可以|可)?(?:随时)?"
    r"(?:继续问|告诉我|提问|问我)[。.!！]?"
)


def _completed_scope_invitation(text: str) -> bool:
    if (_META_QUERY_INVITATION.search(text) or _META_GENERAL_QUESTION.fullmatch(text)
            or _META_HELP_OFFER.fullmatch(text) or _META_RECORD_CAPTURE.search(text)):
        return True
    if (_META_CONTINUE_ACTION.search(text) and _META_SELECTION.search(text)
            and re.search(r"想|希望|需要我|还有|要不要|你", text)
            and not re.search(r"医生|药师", text)):
        return True
    # Request cue, collection verb and field object must belong to the same
    # clause. A prior clinician decision cannot turn the later noun 记录 into
    # a request to collect data.
    for clause in re.split(r"[，,；;]", text):
        if not _META_COLLECTION_FIELD.search(clause):
            continue
        for collector in _META_COLLECTION_ACTION.finditer(clause):
            prefix = clause[:collector.start()].strip()
            if re.search(r"(?:不要|无需|不必|不建议|不需要)[^，,]{0,8}$", prefix):
                continue
            if _META_COLLECTION_REQUEST.search(prefix):
                return True
            if re.match(r"(?:请|建议|你可以|可以|需要)?(?:把|将)", prefix):
                return True
            if not prefix.strip() and collector.group() != "记录":
                return True
    return False


_RECORD_PROVENANCE = re.compile(r"模板(?:化)?|占位|固定来源")
_RECORD_DIMENSIONS = {
    "spo2": re.compile(r"血氧|SpO2", re.I),
    "diet": re.compile(r"饮食|早餐|午餐|晚餐|摄入"),
    "sleep": re.compile(r"睡眠|睡觉"),
    "workout": _EXERCISE_TOPIC,
    "supplements": _SUPPLEMENT_OBJECT,
}


def _uncertain_record_statement(text: str, position: int) -> bool:
    prefix = re.split(r"[，,]|但是|但|不过|然而|而是|却", text[:position])[-1]
    unknown = _HEALTH_CONCLUSION_UNKNOWN.search(prefix)
    return bool(unknown and not _HEALTH_UNCERTAINTY_NEGATION.search(prefix[:unknown.start()]))


def _record_description_flags(text: str, completion) -> list[str]:
    flags = []
    if any(not _uncertain_record_statement(text, m.start()) for m in _RECORD_PROVENANCE.finditer(text)):
        flags.append("unsupported_record_provenance_removed")
    daily = re.search(r"每天|每日", text)
    if daily and not _uncertain_record_statement(text, daily.start()):
        for dimension, pattern in _RECORD_DIMENSIONS.items():
            if not pattern.search(text):
                continue
            query = next((q for q in completion.verified_evidence["queries"]
                          if q["query"]["dimension"] == dimension), None)
            if query is None:
                flags.append("unsupported_daily_coverage_removed")
                break
            window = query["query"]
            days = (date.fromisoformat(window["end_date"]) - date.fromisoformat(window["start_date"])).days + 1
            covered = {row["known_fields"].get("record_date") for row in query["records"]}
            covered.discard(None)
            # Date presence alone does not verify a repeated per-day quantity
            # or activity subtype. Authoritative details remain in the summary.
            if len(covered) != days or _EXERCISE_QUANTITY.search(text):
                flags.append("unsupported_daily_coverage_removed")
                break
    return flags


def project_composed_answer_quality(quality, completion):
    """Remove resolved-scope solicitations without granting any safety exemption.

    Call only after checking the complete unfiltered model answer. An audit flag
    distinguishes this presentation correction from a medical/task failure.
    """
    if (completion is None or not completion.complete or not completion.verified_evidence
            or len(completion.verified_evidence["queries"]) < 2):
        return quality
    from app.services.agent_output_quality import AgentOutputQualityResult, enforce_agent_output_quality

    trusted = enforce_agent_output_quality(completion.trusted_fact_summary).text
    trusted_end = quality.text.find(trusted) + len(trusted) if trusted in quality.text else 0
    prefix, body = quality.text[:trusted_end], quality.text[trusted_end:]
    kept, removed, in_invitation, record_flags = [], False, False, []
    for segment in re.findall(r"[^。；;！？!?\n]+[。；;！？!?]*|[。；;！？!?\n]+", body):
        matching = re.sub(r"^[ \t]*(?:\d+[.)、]|[-*+] )?[ \t]*", "", segment)
        matching = re.sub(r"[*_`]", "", matching).strip()
        if re.match(r"^[ \t]*(?:\d+[.)、]|[-*+] )", segment):
            in_invitation = False
        if _completed_scope_invitation(matching):
            removed, in_invitation = True, True
            continue
        flags = _record_description_flags(matching, completion)
        if flags:
            record_flags.extend(flags)
            in_invitation = False
            continue
        if in_invitation and _META_QUERY_FOLLOWUP.search(matching):
            continue
        if matching:
            in_invitation = False
        kept.append(segment)
    if not removed and not record_flags:
        return quality
    text = re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip()
    text = re.sub(r"(?m)^(\*{0,2})(接下来|下一步)[一二三四五\d]+条(\*{0,2})\s*$", r"\1\2\3", text)
    lines, ordinal = [], 0
    for line in text.splitlines():
        if re.match(r"^\s*(?:#{1,6}\s|\*\*.*\*\*\s*$|接下来$|下一步$)", line):
            ordinal = 0
        number = re.match(r"^(\s*)\d+([.)、])(?=\s)", line)
        if number:
            ordinal += 1
            line = number.group(1) + str(ordinal) + number.group(2) + line[number.end():]
        lines.append(line)
    # Removing all optional invitations must not leave a promised numbered
    # section with no content. Only next-step headings are normalized here.
    normalized_lines = []
    for line in lines:
        heading = re.sub(r"[*#:：\s]", "", line)
        if re.fullmatch(
            r"(?:(?:最多)?[一二三四五\d]+条(?:下一步)?建议|"
            r"(?:接下来|下一步)(?:可以做的)?[一二三四五\d]+(?:条|件事)|"
            r"下一步[（(]最多[一二三四五\d]+条[）)])", heading,
        ):
            line = "下一步"
        normalized_lines.append(line)
    while normalized_lines and not normalized_lines[-1].strip():
        normalized_lines.pop()
    if normalized_lines and re.sub(r"[*#:：\s]", "", normalized_lines[-1]) in {"下一步", "接下来"}:
        normalized_lines.pop()
    text = "\n".join(normalized_lines).strip()
    if prefix:
        text = prefix + ("\n\n" + text if text else "")
    if record_flags:
        text += "\n\n部分描述缺少记录依据，未展示；已核验记录见上。"
    flags = tuple(dict.fromkeys((*quality.flags, *record_flags,
                                *(("meta_query_invitation_removed",) if removed else ()))))
    return AgentOutputQualityResult(text, flags, quality.original_length, len(text))


def _payload(content):
    return load_tool_result_json(content) if isinstance(content, str) else content


def _terminal(payload: dict) -> bool:
    return not result_declares_explicit_failure(payload) and (
        "status" not in payload
        or (isinstance(payload["status"], str) and payload["status"] in _TERMINAL)
    )


def _validate(bound: dict, payload) -> str | None:
    if not isinstance(payload, dict) or not _terminal(payload):
        return "query_result_unavailable"
    if payload.get("dimension") != bound["dimension"] or payload.get("window") != {
        k: bound[k] for k in ("start_date", "end_date", "timezone")
    }:
        return "query_result_scope_conflict"
    if (
        payload.get("truncated")
        or payload.get("has_more")
        or payload.get("next_cursor")
    ):
        return "query_result_truncated"
    actual_source = _ACTUAL_SOURCES.get(bound["dimension"])
    if actual_source and payload.get("source_scope") != actual_source[0]:
        return "query_result_source_conflict"
    rows = payload.get("records")
    availability = payload.get("availability")
    limitations = payload.get("limitations", [])
    if (
        not isinstance(limitations, list)
        or any(not isinstance(v, str) for v in limitations)
        or not isinstance(rows, list)
        or not isinstance(availability, str)
        or availability not in {"available", "partial", "no_data"}
        or (not rows) != (availability == "no_data")
    ):
        return "query_result_unavailable"
    for row in rows:
        if not isinstance(row, dict):
            return "query_result_unavailable"
        if actual_source and (
            not isinstance(row.get("record_kind"), str)
            or row["record_kind"] not in actual_source[1]
        ):
            return "query_result_source_conflict"
        if bound["dimension"] == "supplements" and row.get("taken") is not True:
            return "query_result_source_conflict"
        try:
            day = date.fromisoformat(str(row.get("record_date"))).isoformat()
        except ValueError:
            return "query_result_scope_conflict"
        if not bound["start_date"] <= day <= bound["end_date"]:
            return "query_result_scope_conflict"
    return None


def _facts(dimension: str, payload: dict) -> str:
    """Reuse the daily summary's finite numeric projection, omit raw text fields."""
    label, rows = _LABELS[dimension], payload["records"]
    if not rows:
        absence = {
            "spo2": "，不能判断血氧正常或异常；已排除不用于血氧判断的来源。",
            "diet": "，不代表没有进食。",
            "sleep": "，不能据此判断睡眠情况。",
            "workout": "，不能据此断定没有运动。",
            "supplements": "，不能据此断定没有服用补剂。",
        }
        return f"{label}：目标日期没有可用记录" + absence[dimension]
    count = format_display_number(len(rows))
    if dimension == "diet":
        text = f"饮食：已记录{count}条。"
        known = [
            v
            for row in rows
            if (v := _summary_decimal(row.get("calories"))) is not None
        ]
        total = _summary_display(sum(known, Decimal(0))) if known else None
        if total is None:
            text += "缺少可汇总的有效热量读数，无法给出已记录热量合计。"
        elif len(known) == len(rows):
            text += f"已记录热量合计{total}千卡。"
        else:
            text += (
                f"已知热量小计{total}千卡；另{format_display_number(len(rows) - len(known))}"
                "条缺少有效热量读数，无法给出完整合计。"
            )
    elif dimension == "spo2":
        text = (f"血氧：目标日期内有{count}天的合格来源观测，不代表连续整夜监测。"
                "未验证采样的睡眠区间，不能推算ODI或据此确诊睡眠呼吸暂停。")
    elif dimension == "supplements":
        text = f"补剂：实际服用记录{count}条；定义、计划与当前启停状态不代表实际摄入。"
    elif dimension == "workout":
        text = f"运动：已记录{count}条。"
        known = [
            v
            for row in rows
            if (v := _summary_decimal(row.get("duration_seconds"))) is not None
        ]
        minutes = (
            _summary_display(sum(known, Decimal(0)) / Decimal(60)) if known else None
        )
        if minutes is None:
            text += "缺少可汇总的有效时长读数，无法给出已记录运动时长合计。"
        elif len(known) == len(rows):
            text += f"已记录运动时长合计{minutes}分钟。"
        else:
            text += (
                f"已知运动时长小计{minutes}分钟；另"
                f"{format_display_number(len(rows) - len(known))}条缺少有效时长，"
                "无法给出完整合计。"
            )
        text += "已记录运动不代表全部活动。"
    elif len(rows) != 1:
        text = f"睡眠：查询到{count}条记录，未合并为单一读数，请查看明细。"
    else:
        duration = _summary_decimal(rows[0].get("total_sleep_duration"))
        score = _summary_decimal(rows[0].get("sleep_score"))
        hours = (
            _summary_display(duration / Decimal(60)) if duration is not None else None
        )
        points = _summary_display(score) if score is not None else None
        text = "睡眠：" + (
            f"时长{hours}小时" if hours is not None else "时长缺少有效读数"
        )
        text += (
            "；"
            + (f"评分{points}" if points is not None else "评分缺少有效读数")
            + "。"
        )
    if payload["availability"] == "partial":
        text += "部分日期或指标缺失，不能视为完整数据。"
    if dimension == "sleep":
        text += "按醒来日期归属；每日记录不能证明完整睡眠区间。"
        if "sync_status_unknown" in (payload.get("limitations") or []):
            text += "同步状态未知。"
    return text


def read_scope_synthesis_instructions(scope) -> str:
    if len(scope.queries) < 2 and not any("days" in query for query in scope.queries):
        return ""
    return (
        "\n[实际记录分析的证据边界]\n"
        "回答先给能由本轮记录支持的结论，再按已查领域各用一两句说明，最多三条下一步，可以没有下一步。"
        "普通复盘控制在800字以内；用户明确要求详细报告时才展开。"
        "短续问只补充新的结论和依据，不重写上一轮报告、不反复展开同一批数值。"
        "完成冻结范围的查询后不要再邀请用户选择日期、模块、评估方向或收集新字段。"
        "未要求日程时不生成分时段行动表；先把当前问题完整回答，再结束。"
        "先区分实际查到的记录、未知项目与一般建议。病史时间是用户背景，"
        "不能据此断言已经痊愈、仍在患病或当前恢复程度。"
        "记录热量和时长只能称为已记录合计，不能当作全天实际摄入或全部活动。"
        "不同来源内容相似不证明是同一次事件；无共同事件标识，不得自行去重或构造实际时长上下界。"
        "数值相同不能证明是模板、占位或未称量；缺少记录不能推出没有做，更不能据此要求补吃一餐。"
        "餐次名称和当前时刻不证明该餐未发生，也不证明误录或预录。"
        "指标缺失只能说明未覆盖，不能推出恢复差、营养不足或据此制定训练禁令。"
        "血氧观测须保留数据源与日期覆盖限制；未验证采样的睡眠区间、连续性和阶段对应时，"
        "不能把日汇总当整夜监测，不能推算ODI、睡眠阶段关联或诊断睡眠呼吸暂停。"
        "部分样本不能支持恢复良好、中等偏好、作息稳定、睡眠足够、训练安全、没有过度训练或没有异常信号等个体判断；"
        "即使返回了全部请求字段，记录也不是临床评估或完整生活覆盖。只描述已记录样本的分布与重复。"
        "不与档案中的默认目标作差距比较，不给健康或恢复状态分级。"
        "不提供量化运动方案，包括每周次数、每次时长、组数；轻度、自重、循序渐进也不例外。"
        "不要根据今日暂无记录提醒留意是否已经服用、检查漏服或补打卡；没有日志不证明没有摄入，当前时刻不证明已到服用时间。"
        "短续问不复述或背书上一答的运动、用药或恢复判断，先前模型建议不构成事实或安全依据。"
        "没有本轮可核验的医嘱，不新增补剂、剂量、服用时点或治疗方案。"
        "个人目标必须有明确来源，不虚构目标。情绪和工作未查询是本次读取能力未覆盖，"
        "不要声称用户未授权，更不要承诺尚未提供的读取能力。"
        "字段缺口由系统从已验证记录展示，模型不重复缺口，不生成数据采集任务或追问清单。"
        "不要要求用户补充、提供、记录、收集、完善或补齐字段；短续问同样遵守。"
        "不得从记录重复、缺餐或缺少营养素字段推断蛋白质、蔬果或总摄入不足。"
        "饮食记录种类重复时只能描述记录本身，全天营养是否充足无法判断。"
        "只给出与现有证据相称的条件性下一步；既往感冒不能直接归因于当前状态。"
    )


def read_scope_notices(scope) -> tuple[str, ...]:
    """One disclosure source for the prompt, final answer, and trusted facts."""
    lines = []
    if "scope_diet_sleep_only" in scope.limitations:
        lines.append("本次复盘仅覆盖饮食与睡眠记录；活动等其他健康领域未覆盖。")
    if "default_recent_7_days" in scope.limitations:
        lines.append(
            "未指定复盘范围，本次默认查询最近7天；背景中提到的日期不作为查询起点。"
        )
    if (
        "mood_not_queried" in scope.limitations
        or "unsupported_mood_work_context" in scope.limitations
    ):
        lines.append("情绪背景未查询结构化记录，不能据此判断情绪趋势或归因。")
    if (
        "work_not_queried" in scope.limitations
        or "unsupported_mood_work_context" in scope.limitations
    ):
        lines.append("工作背景未查询结构化记录，不能据此判断工作状态或归因。")
    return tuple(lines)


def evaluate_composed_read_completion(
    scope: OwnedReadScope,
    executions: Iterable[ToolExecutionResult],
) -> ComposedReadCompletion:
    """Attest each domain independently; a real matching retry can recover it.

    Only exact canonical health_query arguments or a batch of those arguments
    are admitted. Batch items match by dimension, never position. Keep an
    already verified read when an unrelated/later failed attempt is observed.
    """
    bounds = {}
    for query in scope.queries:
        dimension = query.get("dimension")
        try:
            parsed_window = parse_query_window(query)
            window = parsed_window.as_dict()
        except (ValueError, TypeError) as exc:
            raise ValueError("composed_read_scope_invalid") from exc
        canonical = {"dimension": dimension, **window}
        if "days" in query:
            days = query["days"]
            if (
                type(days) is not int
                or days != (parsed_window.end_date - parsed_window.start_date).days + 1
            ):
                raise ValueError("composed_read_scope_invalid")
            canonical["days"] = days
        if dimension not in _LABELS or dimension in bounds or query != canonical:
            raise ValueError("composed_read_scope_invalid")
        bounds[dimension] = dict(query)
    if not bounds:
        raise ValueError("composed_read_scope_invalid")
    goals = {
        d: {
            "goal_id": d,
            "kind": "query",
            "status": "failed",
            "evidence_kind": "",
            "reason_code": "query_not_executed",
            "query": dict(bounds[d]),
        }
        for d in bounds
    }
    verified = {}
    for execution in executions:
        decision = execution.decision
        if decision is None or decision.action != "allow":
            continue
        name, args = decision.normalized_tool_name, decision.normalized_args
        if name != execution.tool_name or not isinstance(args, dict):
            continue
        content = _payload(execution.content)
        if name == "health_query":
            candidates = [(args, content)]
        elif name == "health_query_batch":
            if (
                set(args) != {"queries"}
                or not isinstance(args["queries"], list)
                or not isinstance(content, dict)
                or not _terminal(content)
                or content.get("status") not in _TERMINAL
                or not isinstance(content.get("results"), list)
            ):
                continue
            queries, results = args["queries"], content["results"]
            if any(not isinstance(q, dict) for q in queries) or len(
                {q.get("dimension") for q in queries}
            ) != len(queries):
                continue
            candidates = []
            for query in queries:
                matches = [
                    r
                    for r in results
                    if isinstance(r, dict)
                    and r.get("dimension") == query.get("dimension")
                ]
                candidates.append((query, matches[0] if len(matches) == 1 else None))
        else:
            continue
        for query, payload in candidates:
            dimension = query.get("dimension")
            if (
                dimension not in bounds
                or query != bounds[dimension]
                or ("days" in query and type(query["days"]) is not int)
            ):
                continue
            reason = _validate(bounds[dimension], payload)
            if reason is None:
                verified[dimension] = payload
                goals[dimension] = {
                    "goal_id": dimension,
                    "kind": "query",
                    "status": "verified",
                    "evidence_kind": "read_result",
                    "reason_code": "query_verified",
                    "availability": payload["availability"],
                    "query": dict(bounds[dimension]),
                }
            elif dimension not in verified:
                goals[dimension]["reason_code"] = reason
    missing = tuple(d for d in bounds if d not in verified)
    lines = list(read_scope_notices(scope))
    if "diet" in verified and verified["diet"]["records"]:
        lines.append("已记录饮食不代表全天完整摄入，未记录不等于没有发生；全天营养是否充足无法判断。")
    for dimension, query in bounds.items():
        day = (
            query["start_date"]
            if query["start_date"] == query["end_date"]
            else f"{query['start_date']}至{query['end_date']}"
        )
        lines.append(f"查询范围：{_LABELS[dimension]}，{day}，{query['timezone']}。")
        lines.append(
            _facts(dimension, verified[dimension])
            if dimension in verified
            else f"{_LABELS[dimension]}：本轮查询未完成，暂不汇总。"
        )
    evidence = _verified_evidence(bounds, verified, scope.limitations) if not missing else None
    if evidence is not None:
        lines.extend(_evidence_gap_notices(evidence))
    return ComposedReadCompletion(
        tuple(goals.values()), missing, "\n\n".join(lines), not missing, evidence,
    )
