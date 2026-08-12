from __future__ import annotations

import builtins
import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def minimal_graph() -> dict:
    return {
        "_note": "test graph",
        "schema_version": "2.0",
        "entities": [
            {
                "id": "api.health-v1",
                "kind": "api",
                "name": "Health API v1",
                "coverage": "declaration",
                "source": {"type": "declaration", "path": "backend/app/api/main.py"},
            },
            {
                "id": "component.backend-api",
                "kind": "component",
                "name": "FastAPI Backend",
                "coverage": "declaration",
                "source": {"type": "declaration", "path": "backend/app/api/main.py"},
                "owner": "backend",
                "data_classes": ["L1", "L3", "L4"],
                "trust_boundary": "health-backend",
            },
            {
                "id": "component.mobile",
                "kind": "component",
                "name": "Mobile App",
                "coverage": "declaration",
                "source": {"type": "declaration", "path": "mobile/app/"},
                "owner": "mobile",
                "data_classes": ["L1", "L3"],
                "trust_boundary": "user-device",
            },
            {
                "id": "resource.postgresql",
                "kind": "resource",
                "name": "PostgreSQL",
                "coverage": "declaration",
                "source": {"type": "declaration", "path": "backend/app/database.py"},
                "data_classes": ["L2", "L3", "L4"],
            },
            {
                "id": "surface.mobile.home",
                "kind": "surface",
                "name": "Mobile /home",
                "coverage": "complete",
                "source": {"type": "code", "path": "mobile/app/home.tsx"},
                "owner": "mobile",
            },
        ],
        "relations": [
            {
                "from": "component.backend-api",
                "type": "providesApi",
                "to": "api.health-v1",
                "coverage": "declaration",
                "source": {"type": "declaration", "path": "backend/app/api/main.py"},
                "flows": ["agent-chat"],
            },
            {
                "from": "component.backend-api",
                "type": "writesTo",
                "to": "resource.postgresql",
                "coverage": "declaration",
                "source": {"type": "declaration", "path": "backend/app/database.py"},
                "flows": ["health-record"],
            },
            {
                "from": "component.mobile",
                "type": "consumesApi",
                "to": "api.health-v1",
                "coverage": "declaration",
                "source": {"type": "declaration", "path": "mobile/services/"},
                "flows": ["agent-chat", "health-record"],
            },
            {
                "from": "component.mobile",
                "type": "renders",
                "to": "surface.mobile.home",
                "coverage": "complete",
                "source": {"type": "code", "path": "mobile/app/home.tsx"},
            },
        ],
        "coverage": {
            "mobile_surfaces": {
                "source": "mobile/app/",
                "status": "complete",
            },
            "runtime_dependencies": {
                "source": "docs/system-map/declarations.json",
                "status": "partial",
                "limitations": "Conditional runtime dependencies are not discovered.",
            },
        },
        "counts": {"mobile_routes": 2, "service_files": 3},
        "safety_rules_by_category": {},
        "specialists_roster": [],
        "twin_partitions_roster": [],
    }


def test_render_agent_context_is_deterministic_and_global(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    first = context.render_agent_context(minimal_graph)

    assert first == context.render_agent_context(minimal_graph)
    assert "DO NOT EDIT" in first
    assert "component.backend-api" in first
    assert "resource.postgresql" in first
    assert "agent-chat" in first
    assert "partial" in first
    assert "backend/app/api/main.py" in first
    assert "surface.mobile.home" not in first
    assert "verify behavior in source code and tests" in first
    assert len(first.encode("utf-8")) <= context.AGENT_CONTEXT_MAX_BYTES


def test_render_agent_context_uses_canonical_counts(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    text = context.render_agent_context(minimal_graph)

    for key, value in minimal_graph["counts"].items():
        assert f"{key}: {value}" in text


def test_render_agent_context_fails_when_budget_is_exceeded(
    minimal_graph: dict,
    monkeypatch,
) -> None:
    context = importlib.import_module("system_map_context")
    monkeypatch.setattr(context, "AGENT_CONTEXT_MAX_BYTES", 64)

    with pytest.raises(context.SystemMapContextError, match="exceeds"):
        context.render_agent_context(minimal_graph)


def test_agent_context_renderer_does_not_import_backend_runtime(
    minimal_graph: dict,
    monkeypatch,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app" or name.startswith("app."):
            raise AssertionError(f"agent context imported backend runtime module: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    sys.modules.pop("system_map_context", None)

    context = importlib.import_module("system_map_context")

    assert "component.mobile" in context.render_agent_context(minimal_graph)


def test_entity_query_includes_one_hop_neighbors(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    result = context.query_graph(minimal_graph, entity="component.mobile")

    assert {item["id"] for item in result.entities} == {
        "api.health-v1",
        "component.mobile",
        "surface.mobile.home",
    }
    assert result.relations
    assert result.sources


def test_flow_query_selects_only_that_flow(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    result = context.query_graph(minimal_graph, flow="agent-chat")

    assert result.relations
    assert all(
        "agent-chat" in relation.get("flows", [])
        for relation in result.relations
    )


def test_path_query_matches_entity_and_relation_source_prefix(
    minimal_graph: dict,
) -> None:
    context = importlib.import_module("system_map_context")

    result = context.query_graph(minimal_graph, path="mobile/")

    assert {entity["id"] for entity in result.entities} >= {
        "component.mobile",
        "surface.mobile.home",
    }


def test_keyword_query_is_case_insensitive(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    result = context.query_graph(minimal_graph, keyword="POSTGRES")

    assert any(entity["id"] == "resource.postgresql" for entity in result.entities)


def test_declared_evidence_warns_and_points_to_sources(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    result = context.query_graph(minimal_graph, entity="component.mobile")
    text = context.render_query_result(result)

    assert "VERIFY SOURCE" in text
    assert "mobile/app/" in text
    assert all(source for source in result.sources)


def test_query_fails_instead_of_returning_empty(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    with pytest.raises(context.SystemMapContextError, match="not indexed"):
        context.query_graph(minimal_graph, keyword="does-not-exist")


def test_query_requires_exactly_one_selector(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    with pytest.raises(context.SystemMapContextError, match="exactly one"):
        context.query_graph(minimal_graph)
    with pytest.raises(context.SystemMapContextError, match="exactly one"):
        context.query_graph(
            minimal_graph,
            entity="component.mobile",
            keyword="mobile",
        )


def test_query_rejects_depth_above_two(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    with pytest.raises(context.SystemMapContextError, match="depth"):
        context.query_graph(minimal_graph, entity="component.mobile", depth=3)


def test_query_fails_instead_of_truncating(minimal_graph: dict) -> None:
    context = importlib.import_module("system_map_context")

    with pytest.raises(context.SystemMapContextError, match="narrow"):
        context.query_graph(minimal_graph, keyword="component", max_entities=1)


def test_query_cli_prints_context_from_checked_in_shape(
    minimal_graph: dict,
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    context = importlib.import_module("system_map_context")
    artifact = tmp_path / "system-map.json"
    artifact.write_text(json.dumps(minimal_graph), encoding="utf-8")
    monkeypatch.setattr(context, "SYSTEM_MAP_PATH", artifact)

    exit_code = context.main(["--entity", "component.mobile"])

    output = capsys.readouterr()
    assert exit_code == 0
    assert "component.mobile" in output.out
    assert output.err == ""


def test_query_cli_returns_explicit_error_for_unknown_match(
    minimal_graph: dict,
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    context = importlib.import_module("system_map_context")
    artifact = tmp_path / "system-map.json"
    artifact.write_text(json.dumps(minimal_graph), encoding="utf-8")
    monkeypatch.setattr(context, "SYSTEM_MAP_PATH", artifact)

    exit_code = context.main(["--keyword", "does-not-exist"])

    output = capsys.readouterr()
    assert exit_code == 2
    assert "not indexed" in output.err
    assert output.out == ""
