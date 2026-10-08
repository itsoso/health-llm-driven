"""Project registry prose for a server-owned task, without changing authority."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import re
from typing import Any

from app.services.agent_kernel.read_task_scope import OwnedReadScope
from app.services.tool_schema_registry import HEALTH_TOOLS

_SUPPORTED_DIMENSIONS = frozenset({"sleep", "spo2", "diet", "workout", "supplements"})
_SECTION = re.compile(r"(?m)^【[^\n]+】\n")
_ENTRY = re.compile(r"(?m)^  ([a-z][a-z0-9_]*(?: / [a-z][a-z0-9_]*)*)[ \t]+—")
_DATE_RULES = "\ndays 参数只表示"
_BATCH_PLAN = "\nplan 结构:\n"
_BATCH_EXAMPLE = "\n完整示例 ("
_BATCH_RESULT = "\n→ 每条回 "


# Process-local public metadata only. Exact description text and dimensions are
# the keys, so registry edits miss immediately. No time-based TTL is needed for
# these immutable text projections; each helper retains at most 64 LRU entries.
# Never cache scopes, user data, authorized tool lists or mutable schemas.
@lru_cache(maxsize=64)
def _query_description(description: str, dimensions: frozenset[str]) -> str | None:
    """Select whole registry entries including all indented safety prose."""
    if description.count(_DATE_RULES) != 1:
        return None
    guide, date_rules = description.split(_DATE_RULES)
    sections = list(_SECTION.finditer(guide))
    if not sections:
        return None
    selected = []
    found = set()
    for index, section in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(guide)
        body = guide[section.end():end]
        entries = list(_ENTRY.finditer(body))
        if not entries:
            return None
        kept = []
        for offset, entry in enumerate(entries):
            names = frozenset(entry[1].split(" / "))
            if names & dimensions:
                found.update(names & dimensions)
                stop = entries[offset + 1].start() if offset + 1 < len(entries) else len(body)
                kept.append(body[entry.start():stop].rstrip())
        if kept:
            selected.append(section[0] + body[:entries[0].start()] + "\n".join(kept))
    if found != dimensions:
        return None
    return (
        guide[:sections[0].start()].rstrip() + "\n\n"
        + "\n\n".join(selected) + _DATE_RULES + date_rules
    )


@lru_cache(maxsize=64)
def _batch_description(description: str, query_guidance: str) -> str | None:
    if any(description.count(marker) != 1 for marker in (
        _BATCH_PLAN, _BATCH_EXAMPLE, _BATCH_RESULT,
    )):
        return None
    plan = description.index(_BATCH_PLAN)
    example = description.index(_BATCH_EXAMPLE)
    result = description.index(_BATCH_RESULT)
    if not plan < example < result:
        return None
    # Remove only selection examples. Preserve plan semantics, units, unknown
    # value errors and source-derived per-dimension/date/screening limitations.
    return (
        description.split("\n\n", 1)[0]
        + description[plan:example] + description[result:]
        + "\n\n" + query_guidance
    )


def project_owned_read_tool_descriptions(
    tools: list[dict[str, Any]], scope: OwnedReadScope | None,
) -> list[dict[str, Any]]:
    """Return provider-only descriptions of already authorized tools.

    Call after authority filtering. This neither grants tools nor narrows
    argument schemas: dispatch must still enforce the server-owned scope.
    Unknown scopes and specialized/sealed schemas retain their original form.
    """
    if not isinstance(scope, OwnedReadScope) or not scope.queries:
        return tools
    if any(not isinstance(query, dict) or not isinstance(query.get("dimension"), str) for query in scope.queries):
        return tools
    dimensions = frozenset(query.get("dimension") for query in scope.queries)
    if not dimensions or not dimensions <= _SUPPORTED_DIMENSIONS:
        return tools
    canonical = {tool["function"]["name"]: tool for tool in HEALTH_TOOLS}
    query_guidance = _query_description(
        canonical["health_query"]["function"]["description"], dimensions,
    )
    if query_guidance is None:
        return tools
    note = "本轮服务端已绑定查询维度：" + "、".join(sorted(dimensions)) + "。日期和范围以服务端绑定为准，不得自行扩大。\n\n"
    result = []
    for tool in tools:
        function = tool.get("function") or {}
        name = function.get("name")
        if name not in {"health_query", "health_query_batch"}:
            result.append(tool)
            continue
        original = canonical[name]["function"]
        if (
            tool.get("type") != "function"
            or function.get("description") != original["description"]
            or function.get("parameters") != original["parameters"]
        ):
            result.append(tool)
            continue
        description = (
            query_guidance if name == "health_query"
            else _batch_description(original["description"], query_guidance)
        )
        if description is None:
            result.append(tool)
            continue
        projected = deepcopy(tool)
        projected["function"]["description"] = note + description
        result.append(projected)
    return result
