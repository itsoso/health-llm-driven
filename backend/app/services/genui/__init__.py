"""GenUI — 把 AI 回答升级为受 schema 约束的声明式组件 (`reva-ui` block).

铁律 (governance R4 + 本目录存在的全部理由):
组件里的数值**永远**来自确定性 DB 查询, **绝不**来自 LLM。LLM 只可写叙事 +
annotation 文案。数据不足时调用方显"数据不足", 绝不补点。

契约见 `docs/plans/2026-06-30-reva-genui-contract.md` §3.2。
"""

from app.services.genui.chart_builder import (
    build_empty_state,
    build_line_chart,
    build_intra_curve,
    build_multi_metric_chart,
    build_nocturnal_curve,
    build_nocturnal_spo2_curve,
    detect_chart_request,
    detect_chart_requests,
    detect_intra_curve_request,
    detect_nocturnal_curve_request,
    placeholder_reva_ui_blocks,
    render_reva_ui_block,
    strip_reva_ui_blocks,
    SUPPORTED_METRICS,
)
from app.services.genui.chart_rich import compute_chart_rich
from app.services.genui.table_builder import (
    build_table_from_tool_call,
    build_tables_from_tool_calls,
    GENUI_TABLE_CAP,
    load_tool_result_json,
    METRIC_TABLE_TYPE,
    render_metric_table_block,
)
from app.services.genui.diet_summary import (
    build_diet_daily_summary,
    render_diet_summary_block,
    DIET_SUMMARY_TYPE,
    GENUI_DIET_SUMMARY_CAP,
)
from app.services.genui.sleep_summary import (
    build_sleep_summary,
    render_sleep_summary_block,
    SLEEP_SUMMARY_TYPE,
    GENUI_SLEEP_SUMMARY_CAP,
)
from app.services.genui.medication_list import (
    build_medication_list,
    render_medication_list_block,
    MEDICATION_LIST_TYPE,
    GENUI_MEDICATION_LIST_CAP,
)

__all__ = [
    "build_line_chart",
    "build_multi_metric_chart",
    "build_empty_state",
    "build_intra_curve",
    "build_nocturnal_curve",
    "build_nocturnal_spo2_curve",
    "detect_chart_request",
    "detect_chart_requests",
    "detect_intra_curve_request",
    "detect_nocturnal_curve_request",
    "placeholder_reva_ui_blocks",
    "render_reva_ui_block",
    "strip_reva_ui_blocks",
    "SUPPORTED_METRICS",
    "compute_chart_rich",
    "build_table_from_tool_call",
    "build_tables_from_tool_calls",
    "load_tool_result_json",
    "render_metric_table_block",
    "GENUI_TABLE_CAP",
    "build_diet_daily_summary",
    "render_diet_summary_block",
    "DIET_SUMMARY_TYPE",
    "GENUI_DIET_SUMMARY_CAP",
    "build_sleep_summary",
    "render_sleep_summary_block",
    "SLEEP_SUMMARY_TYPE",
    "GENUI_SLEEP_SUMMARY_CAP",
    "build_medication_list",
    "render_medication_list_block",
    "MEDICATION_LIST_TYPE",
    "GENUI_MEDICATION_LIST_CAP",
    "METRIC_TABLE_TYPE",
]
