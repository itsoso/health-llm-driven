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


def evaluate_rules(twin: HealthTwin) -> List[Alert]:
    """对 Twin 运行所有已注册规则，收集 Alert。"""
    alerts: List[Alert] = []
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
            logger.warning(f"[safety] rule {name} 执行失败: {e}", exc_info=False)
    return alerts


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
    )


# 模块加载时自动加载规则
_load_rule_modules()
