"""
Safety Guardian 规则引擎。

设计：
- 每条规则是一个 Python 函数 `(twin: HealthTwin) -> Optional[Alert] | List[Alert]`
- 规则按 category 分组在不同模块里（rules/vitals.py、rules/ddi.py 等）
- 启动时通过 @register 装饰器自动注册，不需要中央清单
- 评估时逐条调用，任一条异常被隔离，不影响其他规则
- 支持启用/禁用（通过 env var 或后续 DB 配置）
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable, List, Optional, Union

from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)

RuleFn = Callable[[HealthTwin], Union[Optional[Alert], List[Alert]]]


class RuleRegistry:
    """全局规则注册表 —— 单例风格。"""

    def __init__(self) -> None:
        self._rules: List[tuple[str, RuleFn]] = []

    def register(self, rule_fn: RuleFn) -> RuleFn:
        """装饰器：注册一条规则。函数名作为 rule_id 前缀。"""
        name = getattr(rule_fn, "__name__", repr(rule_fn))
        self._rules.append((name, rule_fn))
        return rule_fn

    def all_rules(self) -> Iterable[tuple[str, RuleFn]]:
        return list(self._rules)

    def count(self) -> int:
        return len(self._rules)

    def clear(self) -> None:
        """仅测试用。"""
        self._rules.clear()


# 全局单例
registry = RuleRegistry()


def register(rule_fn: RuleFn) -> RuleFn:
    """顶层快捷装饰器。"""
    return registry.register(rule_fn)


def evaluate_rules_with_status(twin: HealthTwin) -> tuple[List[Alert], int]:
    """对 Twin 运行所有已注册规则，收集 Alert，并统计**部分失败**的规则条数。

    返回 `(alerts, failed_rule_count)`：
    - `alerts` —— 成功跑出的所有告警（与 `evaluate_rules` 完全一致的隔离语义：
      单条规则抛异常被吞、不影响其他规则，保护通用 safety report 的韧性）。
    - `failed_rule_count` —— 本次有几条规则抛异常被跳过。**这是关键信号**：
      安全敏感路径(腕上记症状)据此判断「自动安全筛查是否部分缺席」，
      绝不能因为某条急症规则崩了、`alerts` 退化成空就静默冒充「无告警=安全」。

    隔离逻辑(per-rule try/except 吞异常)保持不变 —— 通用报告仍要韧性；
    新增的只是把「跳过了几条」这个原本只进 log 的事实**返回给调用方**，
    让需要 fail-loud 的调用方(under-alarm 是医疗危险)能感知部分失败。
    """
    alerts: List[Alert] = []
    failed = 0
    for name, rule_fn in registry.all_rules():
        try:
            result = rule_fn(twin)
            if result is None:
                continue
            if isinstance(result, list):
                alerts.extend([a for a in result if a is not None])
            elif isinstance(result, Alert):
                alerts.append(result)
            else:
                logger.warning(f"[safety] rule {name} 返回非法类型: {type(result)}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"[safety] rule {name} 执行失败: {e}", exc_info=False)
    return alerts, failed


def evaluate_rules(twin: HealthTwin) -> List[Alert]:
    """对 Twin 运行所有已注册规则，收集 Alert。

    薄封装 `evaluate_rules_with_status`，只取 alerts。**警告**：丢弃 `failed_rule_count`
    会让「某条规则崩 → alerts 退化空」静默冒充「无告警=安全」绿灯(under-alarm,医疗
    场景最危险失败)。安全敏感的调用方**必须**改用 `evaluate_rules_with_status` 并在
    `failed>0` 时注入 `make_fail_safe_advisory()`；本薄封装仅留给「失败本就当『未命中』
    安全」的非裁决场景(如 red-team 覆盖 gate，规则缺失=该场景未通过，方向本就安全)。
    """
    return evaluate_rules_with_status(twin)[0]


def make_fail_safe_advisory() -> Alert:
    """安全评估**部分/整体未完成**时注入的 fail-safe 告警(加层不减层，客户端无关)。

    `evaluate_rules_with_status` 的 per-rule try/except 把单条规则的崩溃吞成「跳过」，
    `alerts` 可能因此退化成空。若调用方据此当「无告警=安全」就是静默 under-alarm
    —— 一个真急症因为某个规则在该用户数据 shape 上崩了而被讲成安全，是医疗场景最
    危险的失败。故所有安全裁决面在 `failed_rule_count>0` 时都往**主渲染路径**
    `alerts` 注入这条 HIGH 告警：**只渲染 `alerts[0]` 的客户端也必须看到**，绝不让
    under-alarm 依赖客户端正确读一个可选的 side flag(空 alerts + 侧 flag 会被忽略成绿灯)。

    R4 不诊断：不下任何病名/结论，只如实说「自动筛查未完成、如有不适及时就医」——
    给动作不给诊断。`severity=HIGH`(稳居就医引导档，又不冒称我们并不掌握的 CRITICAL
    急症：我们只知道筛查没跑全，不知道到底命没命中急症)。这是 watch.py 腕上症状面与
    guardian.evaluate_safety 等所有面共享的**单一** fail-safe 文案来源。
    """
    return Alert(
        rule_id="safety.evaluation_incomplete",
        category="meta",
        severity=Severity.HIGH,
        title="安全评估未完成",
        message=(
            "本次自动安全筛查未能完整跑完,无法确认是否存在安全风险。"
            "这不代表安全,只代表系统未能完成评估。"
        ),
        action=(
            "本次未能完成自动安全筛查,请勿据此判断为安全;"
            "如有任何不适请及时就医,情况紧急请拨打 120。"
        ),
        data_citation={"reason": "rule_engine_partial_or_total_failure"},
        requires_medical_attention=True,
    )


def _load_rule_modules() -> None:
    """显式导入所有规则模块，触发 @register 装饰器副作用。"""
    # 导入顺序 = 稳定的规则评估顺序（前置的先跑）
    from app.agents.safety_guardian.rules import (  # noqa: F401
        vitals,
        labs,
        ddi,
        dsi,
        pgx,
        training_load,
        cgm,
        symptoms,
        cardiac,
        problem_red_lines,
        guidance_red_lines,
    )


# 模块加载时自动加载规则
_load_rule_modules()
