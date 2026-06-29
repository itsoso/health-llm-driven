"""GenUI — 把 AI 回答升级为受 schema 约束的声明式组件 (`reva-ui` block).

铁律 (governance R4 + 本目录存在的全部理由):
组件里的数值**永远**来自确定性 DB 查询, **绝不**来自 LLM。LLM 只可写叙事 +
annotation 文案。数据不足时调用方显"数据不足", 绝不补点。

契约见 `docs/plans/2026-06-30-reva-genui-contract.md` §3.2。
"""

from app.services.genui.chart_builder import (
    build_line_chart,
    detect_chart_request,
    render_reva_ui_block,
    SUPPORTED_METRICS,
)

__all__ = [
    "build_line_chart",
    "detect_chart_request",
    "render_reva_ui_block",
    "SUPPORTED_METRICS",
]
