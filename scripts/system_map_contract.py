#!/usr/bin/env python3
"""Pure-Python contract checks for the generated System Map v2 artifact."""

from __future__ import annotations

import re
from typing import Any


ENTITY_KINDS = {"component", "surface", "api", "resource", "job"}
RELATION_TYPES = {
    "partOf",
    "providesApi",
    "consumesApi",
    "dependsOn",
    "readsFrom",
    "writesTo",
    "publishesTo",
    "consumesFrom",
    "renders",
}
COVERAGE_VALUES = {"complete", "partial", "declaration"}
SOURCE_TYPES = {"code", "generated", "declaration"}
DATA_CLASSES = {"L1", "L2", "L3", "L4"}
REQUIRED_TOP_LEVEL = {
    "_note",
    "schema_version",
    "entities",
    "relations",
    "coverage",
    "counts",
    "safety_rules_by_category",
    "specialists_roster",
    "twin_partitions_roster",
}
_ID_RE = re.compile(r"^[a-z][a-z0-9._:/-]*$")


class SystemMapContractError(ValueError):
    """Raised when the generated map violates the checked-in v2 contract."""


def _require_mapping(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise SystemMapContractError(f"{field} must be an object")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemMapContractError(f"{field} must be a non-empty string")
    return value


def _validate_source(source: Any, field: str) -> None:
    source = _require_mapping(source, field)
    source_type = _require_string(source.get("type"), f"{field}.type")
    if source_type not in SOURCE_TYPES:
        raise SystemMapContractError(f"unknown source type: {source_type}")
    _require_string(source.get("path"), f"{field}.path")
    if "symbol" in source:
        _require_string(source["symbol"], f"{field}.symbol")


def _validate_entity(entity: Any, index: int) -> None:
    entity = _require_mapping(entity, f"entities[{index}]")
    entity_id = _require_string(entity.get("id"), f"entities[{index}].id")
    if not _ID_RE.fullmatch(entity_id):
        raise SystemMapContractError(f"invalid entity id: {entity_id}")
    kind = _require_string(entity.get("kind"), f"entities[{index}].kind")
    if kind not in ENTITY_KINDS:
        raise SystemMapContractError(f"unknown entity kind: {kind}")
    _require_string(entity.get("name"), f"entities[{index}].name")
    coverage = _require_string(entity.get("coverage"), f"entities[{index}].coverage")
    if coverage not in COVERAGE_VALUES:
        raise SystemMapContractError(f"unknown coverage value: {coverage}")
    _validate_source(entity.get("source"), f"entities[{index}].source")
    for data_class in entity.get("data_classes", []):
        if data_class not in DATA_CLASSES:
            raise SystemMapContractError(f"unknown data class: {data_class}")


def _validate_relation(relation: Any, index: int, entity_ids: set[str]) -> None:
    relation = _require_mapping(relation, f"relations[{index}]")
    source_id = _require_string(relation.get("from"), f"relations[{index}].from")
    target_id = _require_string(relation.get("to"), f"relations[{index}].to")
    relation_type = _require_string(relation.get("type"), f"relations[{index}].type")
    if relation_type not in RELATION_TYPES:
        raise SystemMapContractError(f"unknown relation type: {relation_type}")
    if source_id not in entity_ids:
        raise SystemMapContractError(f"relation has unknown source: {source_id}")
    if target_id not in entity_ids:
        raise SystemMapContractError(f"relation has unknown target: {target_id}")
    coverage = _require_string(relation.get("coverage"), f"relations[{index}].coverage")
    if coverage not in COVERAGE_VALUES:
        raise SystemMapContractError(f"unknown coverage value: {coverage}")
    _validate_source(relation.get("source"), f"relations[{index}].source")
    flows = relation.get("flows", [])
    if not isinstance(flows, list) or any(not isinstance(flow, str) or not flow for flow in flows):
        raise SystemMapContractError(f"relations[{index}].flows must contain strings")


def validate_system_map(data: Any) -> None:
    """Validate graph semantics that JSON Schema alone cannot express."""
    data = _require_mapping(data, "system-map")
    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    if missing:
        raise SystemMapContractError(f"missing top-level fields: {missing}")
    if data.get("schema_version") != "2.0":
        raise SystemMapContractError("schema_version must be 2.0")
    if not isinstance(data["entities"], list):
        raise SystemMapContractError("entities must be a list")
    if not isinstance(data["relations"], list):
        raise SystemMapContractError("relations must be a list")
    _require_mapping(data["coverage"], "coverage")
    _require_mapping(data["counts"], "counts")

    for index, entity in enumerate(data["entities"]):
        _validate_entity(entity, index)
    entity_ids = [entity["id"] for entity in data["entities"]]
    if len(entity_ids) != len(set(entity_ids)):
        raise SystemMapContractError("duplicate entity id")
    if entity_ids != sorted(entity_ids):
        raise SystemMapContractError("entities must be sorted by id")

    entity_id_set = set(entity_ids)
    for index, relation in enumerate(data["relations"]):
        _validate_relation(relation, index, entity_id_set)
    relation_keys = [
        (relation["from"], relation["type"], relation["to"])
        for relation in data["relations"]
    ]
    if len(relation_keys) != len(set(relation_keys)):
        raise SystemMapContractError("duplicate relation")
    if relation_keys != sorted(relation_keys):
        raise SystemMapContractError("relations must be sorted by from/type/to")
