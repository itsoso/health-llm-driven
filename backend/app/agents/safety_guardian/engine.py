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

from app.agents.safety_guardian.schema import Alert
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

    薄封装 `evaluate_rules_with_status`，只取 alerts —— 现有调用方
    (guardian.evaluate_safety / orchestrator / safety_eval / medication_regimen)
    行为零变化；需要部分失败计数的调用方改用 `evaluate_rules_with_status`。
    """
    return evaluate_rules_with_status(twin)[0]


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
