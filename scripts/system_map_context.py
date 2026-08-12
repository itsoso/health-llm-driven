#!/usr/bin/env python3
"""Render bounded, code-derived context views from the canonical System Map."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system_map_contract import SystemMapContractError, validate_system_map


ROOT = Path(__file__).resolve().parent.parent
SYSTEM_MAP_PATH = ROOT / "docs" / "_generated" / "system-map.json"
AGENT_CONTEXT_MAX_BYTES = 16 * 1024
GLOBAL_KINDS = {"component", "api", "resource"}


class SystemMapContextError(ValueError):
    """Raised when a bounded context view cannot be produced safely."""


@dataclass(frozen=True)
class QueryResult:
    """A deterministic, bounded subgraph plus evidence metadata."""

    entities: tuple[dict[str, Any], ...]
    relations: tuple[dict[str, Any], ...]
    sources: tuple[str, ...]
    warnings: tuple[str, ...]


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


def _relation_key(relation: dict[str, Any]) -> tuple[str, str, str]:
    return relation["from"], relation["type"], relation["to"]


def _search_text(item: dict[str, Any]) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True).lower()


def _check_result_size(entity_ids: set[str], max_entities: int) -> None:
    if len(entity_ids) > max_entities:
        raise SystemMapContextError(
            f"query matched {len(entity_ids)} entities; narrow the selector "
            f"or traversal depth (maximum {max_entities})"
        )


def _seed_entity_ids(
    graph: dict[str, Any],
    *,
    path: str | None,
    entity: str | None,
    flow: str | None,
    keyword: str | None,
) -> tuple[set[str], list[dict[str, Any]]]:
    entities = graph["entities"]
    relations = graph["relations"]
    if entity is not None:
        return (
            {item["id"] for item in entities if item["id"] == entity},
            relations,
        )
    if flow is not None:
        flow_relations = [
            relation
            for relation in relations
            if flow in relation.get("flows", [])
        ]
        return (
            {
                entity_id
                for relation in flow_relations
                for entity_id in (relation["from"], relation["to"])
            },
            flow_relations,
        )
    if path is not None:
        prefix = path.removeprefix("./")
        entity_ids = {
            item["id"]
            for item in entities
            if item["source"]["path"].startswith(prefix)
        }
        for relation in relations:
            if relation["source"]["path"].startswith(prefix):
                entity_ids.update((relation["from"], relation["to"]))
        return entity_ids, relations
    assert keyword is not None
    needle = keyword.casefold()
    entity_ids = {
        item["id"] for item in entities if needle in _search_text(item).casefold()
    }
    for relation in relations:
        if needle in _search_text(relation).casefold():
            entity_ids.update((relation["from"], relation["to"]))
    return entity_ids, relations


def _query_warnings(
    entities: tuple[dict[str, Any], ...],
    relations: tuple[dict[str, Any], ...],
) -> tuple[str, ...]:
    warnings = []
    for entity in entities:
        if entity["coverage"] != "complete":
            warnings.append(
                f"VERIFY SOURCE: entity {entity['id']} has coverage="
                f"{entity['coverage']}; source={_source_label(entity['source'])}"
            )
    for relation in relations:
        if relation["coverage"] != "complete":
            warnings.append(
                f"VERIFY SOURCE: relation {relation['from']} --{relation['type']}--> "
                f"{relation['to']} has coverage={relation['coverage']}; "
                f"source={_source_label(relation['source'])}"
            )
    return tuple(sorted(warnings))


def query_graph(
    graph: dict[str, Any],
    *,
    path: str | None = None,
    entity: str | None = None,
    flow: str | None = None,
    keyword: str | None = None,
    depth: int = 1,
    max_entities: int = 50,
) -> QueryResult:
    """Select a bounded subgraph without inferring or silently dropping edges."""
    selectors = (path, entity, flow, keyword)
    if sum(value is not None for value in selectors) != 1:
        raise SystemMapContextError("exactly one selector is required")
    if depth not in (0, 1, 2):
        raise SystemMapContextError("depth must be 0, 1, or 2")
    if max_entities < 1:
        raise SystemMapContextError("max_entities must be positive")

    entity_ids, candidate_relations = _seed_entity_ids(
        graph,
        path=path,
        entity=entity,
        flow=flow,
        keyword=keyword,
    )
    if not entity_ids:
        selector = next(value for value in selectors if value is not None)
        raise SystemMapContextError(f"selector is not indexed: {selector}")
    _check_result_size(entity_ids, max_entities)

    frontier = set(entity_ids)
    for _ in range(depth):
        neighbors = set()
        for relation in candidate_relations:
            if relation["from"] in frontier or relation["to"] in frontier:
                neighbors.update((relation["from"], relation["to"]))
        frontier = neighbors - entity_ids
        if not frontier:
            break
        entity_ids.update(frontier)
        _check_result_size(entity_ids, max_entities)

    entities_by_id = {item["id"]: item for item in graph["entities"]}
    result_entities = tuple(entities_by_id[item] for item in sorted(entity_ids))
    result_relations = tuple(
        sorted(
            (
                relation
                for relation in candidate_relations
                if relation["from"] in entity_ids and relation["to"] in entity_ids
            ),
            key=_relation_key,
        )
    )
    sources = tuple(
        sorted(
            {
                _source_label(item["source"])
                for item in (*result_entities, *result_relations)
            }
        )
    )
    return QueryResult(
        entities=result_entities,
        relations=result_relations,
        sources=sources,
        warnings=_query_warnings(result_entities, result_relations),
    )


def render_query_result(result: QueryResult) -> str:
    """Render a query result as deterministic, source-linked Markdown."""
    lines = [
        "# System Map Task Context",
        "",
        "> Navigation input only: verify behavior in source code and tests.",
    ]
    if result.warnings:
        lines.extend(["", "## Evidence warnings", ""])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(["", "## Entities", ""])
    for entity in result.entities:
        lines.append(
            f"- `{entity['id']}` — {entity['name']} ({_entity_details(entity)})"
        )
        lines.append(f"  source: `{_source_label(entity['source'])}`")
    lines.extend(["", "## Relations", ""])
    if result.relations:
        for relation in result.relations:
            flows = ",".join(relation.get("flows", [])) or "none"
            lines.append(
                f"- `{relation['from']}` --{relation['type']}--> "
                f"`{relation['to']}` (coverage={relation['coverage']}; flows={flows}; "
                f"source=`{_source_label(relation['source'])}`)"
            )
    else:
        lines.append("- none in the selected traversal depth")
    lines.extend(["", "## Open these sources next", ""])
    lines.extend(f"- `{source}`" for source in result.sources)
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query a bounded context slice from the canonical System Map."
    )
    selectors = parser.add_mutually_exclusive_group(required=True)
    selectors.add_argument("--path")
    selectors.add_argument("--entity")
    selectors.add_argument("--flow")
    selectors.add_argument("--keyword")
    parser.add_argument("--depth", type=int, choices=(0, 1, 2), default=1)
    parser.add_argument("--max-entities", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the read-only bounded query CLI."""
    args = _parser().parse_args(argv)
    try:
        graph = json.loads(SYSTEM_MAP_PATH.read_text(encoding="utf-8"))
        validate_system_map(graph)
        result = query_graph(
            graph,
            path=args.path,
            entity=args.entity,
            flow=args.flow,
            keyword=args.keyword,
            depth=args.depth,
            max_entities=args.max_entities,
        )
    except (
        OSError,
        json.JSONDecodeError,
        SystemMapContractError,
        SystemMapContextError,
    ) as exc:
        print(f"System Map context unavailable: {exc}", file=sys.stderr)
        return 2
    print(render_query_result(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
