from __future__ import annotations

import asyncio
import json
import logging
import socket
from dataclasses import dataclass, replace
from typing import Any
from unittest.mock import patch

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import ToolExecutionRequest


logging.disable(logging.CRITICAL)


class ExternalTripwire(RuntimeError):
    pass


class TripwireDB:
    attempts = 0

    def __getattr__(self, name: str) -> Any:
        type(self).attempts += 1
        raise ExternalTripwire(f"database access forbidden: {name}")


@dataclass(frozen=True)
class Case:
    category: str
    text: str
    tool: str
    args: dict[str, Any]
    should_dispatch: bool
    expected_args: dict[str, Any] | None = None
    goal_kind: str | None = None


CASES: list[Case] = []


def add_block(category: str, text: str, tool: str, args: dict[str, Any]) -> None:
    CASES.append(Case(category, text, tool, args, False))


def add_allow(
    category: str,
    text: str,
    tool: str,
    args: dict[str, Any],
    expected_args: dict[str, Any],
    *,
    goal_kind: str | None = None,
) -> None:
    CASES.append(
        Case(category, text, tool, args, True, expected_args, goal_kind=goal_kind)
    )


WRONG_ILLNESS = {"dimension": "illness", "keyword": "系统性硬化症", "days": 2}
WRONG_METRIC = {"dimension": "sleep", "days": 2}
WRONG_BATCH = {"queries": [{"dimension": "sleep", "days": 2, "agg": None}]}


# Arbitrary Unicode/Latin/role owners. Possessive and concatenated forms are
# deliberately distinct; the latter is a common path around finite role lists.
owners = (
    "Ξάνθη",
    "محمد",
    "Ольга",
    "Nguyễn",
    "Jean-Luc",
    "OConnor",
    "轮值药师",
    "访问学者",
)
for owner in owners:
    possessive = f"调阅{owner}的偏头痛病史"
    concat = f"调阅{owner}偏头痛病史"
    for message in (possessive, concat):
        add_block("l3-owner-illness", message, "health_query", WRONG_ILLNESS)
        add_block("l3-owner-illness", message, "health_query_batch", WRONG_BATCH)
        add_block(
            "l3-owner-illness",
            message,
            "health_manage",
            {"record_type": "illness", "operation": "list"},
        )


# Third-party imaging, including possessive and concatenated names. An owner
# must not become a medical_exam keyword and cross the owner boundary.
imaging_owners = ("Ξάνθη", "Ольга", "Nguyễn", "Jean-Luc", "外聘顾问", "代班护士")
for owner in imaging_owners:
    for message in (f"调出{owner}的左膝MRI报告", f"调出{owner}左膝MRI报告"):
        add_block("l3-owner-imaging", message, "health_query", WRONG_METRIC)
        add_block("l3-owner-imaging", message, "health_query_batch", WRONG_BATCH)
        add_block(
            "l3-owner-imaging",
            message,
            "health_manage",
            {"record_type": "medical_exam", "operation": "list"},
        )


# Direct illness and generic-memory write routes must share owner isolation.
write_owners = ("Ξάνθη", "محمد", "Ольга", "Nguyễn", "Jean-Luc", "轮值药师")
for owner in write_owners:
    text = f"记录疾病：{owner}偏头痛"
    add_block(
        "l3-owner-write-direct",
        text,
        "health_record",
        {"record_type": "illness", "data": {"name": f"{owner}偏头痛"}},
    )
    add_block(
        "l3-owner-write-memory",
        text,
        "health_record",
        {
            "record_type": "remember",
            "data": {"predicate": "确诊疾病", "object_value": f"{owner}偏头痛"},
        },
    )


# Open-vocabulary current-user availability. None of these disease names is
# copied from the committed v38 examples.
rare_diseases = (
    "肠易激综合征",
    "多囊卵巢综合征",
    "抗磷脂综合征",
    "吉兰-巴雷综合征",
    "埃勒斯-当洛斯综合征",
    "噬血细胞综合征",
    "慢性疲劳综合征",
    "缺铁性贫血",
    "再生障碍性贫血",
    "地中海贫血",
    "幽门螺杆菌感染",
    "呼吸道合胞病毒感染",
    "泌尿道感染",
    "功能性便秘",
    "阵发性房颤",
    "非酒精性脂肪肝",
    "嗜酸性肉芽肿性多血管炎",
    "骨质疏松症",
)
for disease in rare_diseases:
    query = f"调阅我过去三个月{disease}的病史"
    expected_query = {"dimension": "illness", "keyword": disease, "days": 90}
    add_allow(
        "availability-rare-query",
        query,
        "health_query",
        WRONG_METRIC,
        expected_query,
    )
    add_allow(
        "availability-rare-manage",
        query,
        "health_manage",
        {"record_type": "illness", "operation": "list"},
        {"record_type": "illness", "operation": "list"},
    )
    write = f"记录疾病：{disease}"
    expected_write = {"record_type": "illness", "data": {"name": disease}}
    add_allow(
        "availability-rare-write-direct",
        write,
        "health_record",
        {"record_type": "illness", "data": {"name": disease, "severity": 8}},
        expected_write,
        goal_kind="simple_health_record",
    )
    add_allow(
        "availability-rare-write-memory",
        write,
        "health_record",
        {
            "record_type": "remember",
            "data": {"predicate": "疾病史", "object_value": disease},
        },
        expected_write,
        goal_kind="simple_health_record",
    )


# Non-health suffix collisions not present in the finite root deny-list.
collisions = (
    "仓库感染",
    "流水线异常",
    "微服务瘫痪",
    "博客综合征",
    "小说贫血",
    "合同出血",
    "税务肝炎",
    "机票癌",
    "摄像头震颤",
    "打印机卒中",
    "路由器感染",
    "芯片异常",
    "机器人癫痫",
    "算法偏头痛",
    "血糖异常",
    "ALT异常",
    "HRV异常",
    "订单肠炎",
)
for entity in collisions:
    message = f"调阅过去三个月{entity}的历史记录"
    add_block("non-health-suffix", message, "health_query", WRONG_ILLNESS)
    add_block(
        "non-health-suffix",
        message,
        "health_manage",
        {"record_type": "illness", "operation": "list"},
    )


# General ordinal and discourse references without durable identity.
references = (
    "调出头一份MRI",
    "调出倒着数第二份MRI",
    "调出从后往前第三份MRI",
    "调出最靠前那份MRI",
    "调出最靠后那份MRI",
    "调出第一百零一份MRI",
    "调出第卌份MRI",
    "调出上溯第二条疾病记录",
    "调出先前保存的MRI",
    "调出早先那份MRI",
    "调出较新的那份MRI",
    "调出前面保存的那份MRI",
    "调出你此前概括的疾病记录",
    "调出刚才归纳的那个病史",
)
for message in references:
    add_block("unresolved-reference", message, "health_query", WRONG_ILLNESS)
    add_block("unresolved-reference", message, "health_query_batch", WRONG_BATCH)
    add_block(
        "unresolved-reference",
        message,
        "health_manage",
        {"record_type": "medical_exam", "operation": "list"},
    )


# Cancellation language not copied from the committed matrix.
cancelled = (
    "别查了，偏头痛病史不用看",
    "不查偏头痛了",
    "这次查询作罢",
    "检索暂停一下",
    "停止继续浏览我的病史",
    "不用再找偏头痛记录",
    "暂缓查询我的疾病历史",
    "叫停搜索偏头痛病史",
    "终止这次读取疾病记录",
    "撤下这次调阅偏头痛记录的请求",
)
for message in cancelled:
    add_block("cancelled-read", message, "health_query", WRONG_ILLNESS)
    add_block("cancelled-read", message, "health_query_batch", WRONG_BATCH)
    add_block(
        "cancelled-read",
        message,
        "health_manage",
        {"record_type": "illness", "operation": "list"},
    )


# Later self-owned scope must remain available and must overwrite the model's
# first-clause/other-entity proposal.
later_self = (
    "别调阅Ольга的偏头痛；只调阅我过去三个月哮喘病史",
    "取消查看Nguyễn的偏头痛。转而调阅我过去三个月痛风病史",
    "Jean-Luc的湿疹病史不用看，不过调阅我过去三个月鼻炎病史",
    "别看轮值药师的癫痫，我要调阅自己过去三个月房颤病史",
)
later_expected = ("哮喘", "痛风", "鼻炎", "房颤")
for message, disease in zip(later_self, later_expected, strict=True):
    expected = {"dimension": "illness", "keyword": disease, "days": 90}
    add_allow("later-self-scope", message, "health_query", WRONG_ILLNESS, expected)
    add_allow(
        "later-self-scope",
        message,
        "health_manage",
        {"record_type": "illness", "operation": "list"},
        {"record_type": "illness", "operation": "list"},
    )

later_batch = (
    "别调阅Ольга的睡眠；只比较我的睡眠和HRV",
    "Nguyễn的体重不用查。转而比较我自己的睡眠和步数",
)
batch_plans = (
    {
        "queries": [
            {"dimension": "sleep", "days": 7, "agg": "avg"},
            {"dimension": "hrv", "days": 7, "agg": "avg"},
        ],
        "compare": {"a": 0, "b": 1, "op": "diff"},
    },
    {
        "queries": [
            {"dimension": "sleep", "days": 7, "agg": "avg"},
            {"dimension": "activity", "days": 7, "agg": "avg"},
        ],
        "compare": {"a": 0, "b": 1, "op": "diff"},
    },
)
for message, expected in zip(later_batch, batch_plans, strict=True):
    add_allow("later-self-batch", message, "health_query_batch", WRONG_BATCH, expected)


# Present-tense observations are not read authority.
observations = (
    "今早偏头痛冒头了",
    "目前胸口发紧了",
    "今天手麻越来越严重",
    "最近哮喘好像又犯了",
    "这两天湿疹明显恶化了",
    "刚才房颤又出现了",
    "现在膝盖疼得厉害",
    "今天鼻炎又犯",
)
for message in observations:
    add_block("observation-only", message, "health_query", WRONG_ILLNESS)
    add_block("observation-only", message, "health_query_batch", WRONG_BATCH)
    add_block(
        "observation-only",
        message,
        "health_manage",
        {"record_type": "illness", "operation": "list"},
    )


# health_manage(list) must not accept a wrong domain proposed by the model.
wrong_manage = (
    ("调阅我过去三个月睡眠历史", "illness"),
    ("调阅我过去三个月饮水历史", "illness"),
    ("调阅我过去三个月体重历史", "illness"),
    ("调阅我过去三个月MRI报告", "illness"),
    ("调阅我过去三个月偏头痛病史", "medical_exam"),
    ("调阅我过去三个月湿疹病史", "sleep"),
)
for message, record_type in wrong_manage:
    add_block(
        "wrong-domain-manage",
        message,
        "health_manage",
        {"record_type": record_type, "operation": "list"},
    )


# New punctuated imaging identifiers should stay available and exact.
imaging = (
    "T1+C MRI",
    "ADC-map MRI",
    "3D-TOF MRI",
    "C6/7颈椎MRI",
    "L5-S1腰椎MRI",
    "T2* GRE MRI",
    "DCE-MRI",
    "DWI/ADC脑MRI",
    "SWI+QSM MRI",
)
for exam in imaging:
    message = f"调出我的{exam}报告"
    expected = {"dimension": "medical_exam", "keyword": exam}
    add_allow("availability-punctuated-mri", message, "health_query", WRONG_METRIC, expected)
    add_allow(
        "availability-punctuated-mri",
        message,
        "health_manage",
        {"record_type": "medical_exam", "operation": "list"},
        {"record_type": "medical_exam", "operation": "list"},
    )


# Original query and explicit model-override probes.
add_allow(
    "original-query",
    "我上一次口腔溃疡是什么时候 最近半年分别有哪些记录",
    "health_query",
    WRONG_METRIC,
    {"dimension": "illness", "keyword": "口腔溃疡", "days": 183},
)
override_queries = (
    ("调阅我过去三个月哮喘病史", "哮喘"),
    ("调阅我过去三个月痛风病史", "痛风"),
    ("调阅我过去三个月湿疹病史", "湿疹"),
    ("调阅我过去三个月房颤病史", "房颤"),
)
for message, disease in override_queries:
    add_allow(
        "model-proposal-override",
        message,
        "health_query",
        {"dimension": "illness", "keyword": "Ольга偏头痛", "days": 1},
        {"dimension": "illness", "keyword": disease, "days": 90},
    )


async def main() -> None:
    failures: list[dict[str, Any]] = []
    category_totals: dict[str, int] = {}
    category_failures: dict[str, int] = {}
    decisions: dict[str, int] = {}
    dispatches = 0

    def deny_external(*_args: Any, **_kwargs: Any) -> Any:
        raise ExternalTripwire("socket/http/filesystem external side effect forbidden")

    patches = (
        patch("socket.socket", side_effect=deny_external),
        patch("socket.create_connection", side_effect=deny_external),
        patch("httpx.request", side_effect=deny_external),
        patch("httpx.get", side_effect=deny_external),
        patch("httpx.post", side_effect=deny_external),
        patch("requests.request", side_effect=deny_external),
        patch("requests.get", side_effect=deny_external),
        patch("requests.post", side_effect=deny_external),
    )
    for item in patches:
        item.start()
    try:
        for case_index, case in enumerate(CASES):
            category_totals[case.category] = category_totals.get(case.category, 0) + 1
            for mode in ("enforce", "shadow"):
                executor = AgentExecutor(TripwireDB())
                executor._current_user_id = 909001
                executor._turn_channel = "typed"
                executor._current_turn_user_message = case.text
                snapshot = executor._ensure_agent_kernel_turn(channel="typed")
                snapshot = replace(snapshot, policy_mode=mode)
                executor._agent_kernel_snapshot = snapshot
                gateway = ToolGateway(snapshot)
                calls: list[dict[str, Any]] = []

                async def fake_terminal(request: ToolExecutionRequest) -> str:
                    nonlocal dispatches
                    dispatches += 1
                    calls.append(dict(request.arguments))
                    if request.tool_name == "health_record":
                        return json.dumps(
                            {"status": "success", "operation_id": "fake-only"},
                            ensure_ascii=False,
                        )
                    return "[]"

                try:
                    result = await gateway.execute(
                        ToolExecutionRequest(
                            tool_name=case.tool,
                            arguments=case.args,
                            source="structured",
                            tool_call_id=f"g4-{case_index}-{mode}",
                        ),
                        fake_terminal,
                    )
                    decision = result.decision
                    assert decision is not None
                    decisions[decision.reason] = decisions.get(decision.reason, 0) + 1
                    errors: list[str] = []
                    if case.should_dispatch:
                        if decision.action != "allow":
                            errors.append(f"decision={decision.action}:{decision.reason}")
                        if len(calls) != 1:
                            errors.append(f"dispatch_count={len(calls)}")
                        elif calls[0] != case.expected_args:
                            errors.append(
                                f"args={calls[0]!r} expected={case.expected_args!r}"
                            )
                        if case.goal_kind and (
                            snapshot.goal is None or snapshot.goal.kind != case.goal_kind
                        ):
                            errors.append(
                                f"goal={getattr(snapshot.goal, 'kind', None)!r} expected={case.goal_kind!r}"
                            )
                    else:
                        if calls:
                            errors.append(f"UNSAFE_DISPATCH={calls!r}")
                        if decision.action != "block":
                            errors.append(f"decision={decision.action}:{decision.reason}")
                    if errors:
                        category_failures[case.category] = (
                            category_failures.get(case.category, 0) + 1
                        )
                        failures.append(
                            {
                                "index": case_index,
                                "mode": mode,
                                "category": case.category,
                                "text": case.text,
                                "tool": case.tool,
                                "intent": (
                                    snapshot.intent.primary,
                                    snapshot.intent.domain,
                                    snapshot.intent.operation,
                                ),
                                "goal": (
                                    snapshot.goal.kind if snapshot.goal else None,
                                    snapshot.goal.domain if snapshot.goal else None,
                                    snapshot.goal.operation if snapshot.goal else None,
                                    snapshot.goal.requires_clarification if snapshot.goal else None,
                                ),
                                "decision": (decision.action, decision.reason),
                                "errors": errors,
                            }
                        )
                except Exception as exc:
                    category_failures[case.category] = (
                        category_failures.get(case.category, 0) + 1
                    )
                    failures.append(
                        {
                            "index": case_index,
                            "mode": mode,
                            "category": case.category,
                            "text": case.text,
                            "tool": case.tool,
                            "exception": f"{type(exc).__name__}: {exc}",
                        }
                    )
    finally:
        for item in reversed(patches):
            item.stop()

    unique_failed = len({item["index"] for item in failures})
    print(
        json.dumps(
            {
                "sha_expected": "2ea545906cdeb4c8a200383ee5cd3cead2d5f1d6",
                "implementation_parent": "f5497195bc4181d766dc3752d4ed9ddfb09b7877",
                "unique_cases": len(CASES),
                "executions": len(CASES) * 2,
                "unique_failed": unique_failed,
                "execution_failures": len(failures),
                "execution_passes": len(CASES) * 2 - len(failures),
                "fake_terminal_dispatches": dispatches,
                "db_tripwire_blocks": TripwireDB.attempts,
                "categories": category_totals,
                "category_failure_executions": category_failures,
                "decision_reasons": decisions,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


asyncio.run(main())
