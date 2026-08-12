#!/usr/bin/env python3
"""Render bounded, code-derived context views from the canonical System Map."""

from __future__ import annotations

from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SYSTEM_MAP_PATH = ROOT / "docs" / "_generated" / "system-map.json"
AGENT_CONTEXT_MAX_BYTES = 16 * 1024
GLOBAL_KINDS = {"component", "api", "resource"}


class SystemMapContextError(ValueError):
    """Raised when a bounded context view cannot be produced safely."""


def _source_label(source: dict[str, Any]) -> str:
    symbol = f"::{source['symbol']}" if source.get("symbol") else ""
    return f"{source['path']}{symbol} [{source['type']}]"


def _entity_details(entity: dict[str, Any]) -> str:
    details = [f"kind={entity['kind']}", f"coverage={entity['coverage']}"]
    for field in ("owner", "domain", "lifecycle", "trust_boundary"):
        if entity.get(field):
            details.append(f"{field}={entity[field]}")
    if entity.get("data_classes"):
        details.append(f"data_classes={','.join(sorted(entity['data_classes']))}")
    return "; ".join(details)


def render_agent_context(graph: dict[str, Any]) -> str:
    """Render the bounded global bootstrap from a validated canonical graph."""
    entities = sorted(
        (
            entity
            for entity in graph["entities"]
            if entity["kind"] in GLOBAL_KINDS
        ),
        key=lambda item: item["id"],
    )
    flows = sorted(
        {
            flow
            for relation in graph["relations"]
            for flow in relation.get("flows", [])
        }
    )
    lines = [
        "# Reva System Map — Agent Global Context",
        "",
        "> DO NOT EDIT — generated from docs/_generated/system-map.json.",
        "> Navigation input only: verify behavior in source code and tests before deciding or editing.",
        "",
        "## Evidence order",
        "",
        "1. Executable code, tests, runtime contracts, and registries",
        "2. Code-derived System Map facts",
        "3. Reviewed declarations with explicit coverage",
        "4. Freshness-dated narrative documents",
        "",
        "## Global entities",
        "",
    ]
    for entity in entities:
        lines.append(
            f"- `{entity['id']}` — {entity['name']} ({_entity_details(entity)})"
        )
        lines.append(f"  source: `{_source_label(entity['source'])}`")

    lines.extend(["", "## Key flows", ""])
    for flow in flows:
        lines.append(f"### {flow}")
        relations = sorted(
            (
                relation
                for relation in graph["relations"]
                if flow in relation.get("flows", [])
            ),
            key=lambda item: (item["from"], item["type"], item["to"]),
        )
        for relation in relations:
            lines.append(
                f"- `{relation['from']}` --{relation['type']}--> "
                f"`{relation['to']}` (coverage={relation['coverage']}; "
                f"source=`{_source_label(relation['source'])}`)"
            )
        lines.append("")

    lines.extend(["## Coverage limits", ""])
    for area, coverage in sorted(graph["coverage"].items()):
        limitation = ""
        if coverage.get("limitations"):
            limitation = f"; limitation={coverage['limitations']}"
        lines.append(
            f"- `{area}`: {coverage['status']}; source=`{coverage['source']}`"
            f"{limitation}"
        )

    lines.extend(["", "## Code-derived counts", ""])
    lines.extend(
        f"- {key}: {value}" for key, value in sorted(graph["counts"].items())
    )
    rendered = "\n".join(lines).rstrip() + "\n"
    size = len(rendered.encode("utf-8"))
    if size > AGENT_CONTEXT_MAX_BYTES:
        raise SystemMapContextError(
            f"agent context exceeds {AGENT_CONTEXT_MAX_BYTES} bytes: {size}"
        )
    return rendered
