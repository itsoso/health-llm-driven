#!/usr/bin/env python3
"""Generate docs/_generated/system-map.json — 代码派生的系统事实(计数 + roster)。

System-map 防漂移核心(见 .claude/skills/system-map/SKILL.md + docs/system-map/INDEX.md):
一个事实只允许两种状态 —— ① 从代码生成进无人手改的文件,或 ② 带 last-reviewed 日期的纯叙事(显式不含 live 数字)。
本脚本产出 ①。复用 scripts/check_doc_drift.py 的扫描器(单一真源,别复制计数逻辑)。

输出是**确定性的**(全部 sorted,无时间戳)→ check_doc_drift.py 重算后可直接相等比对,
committed 与代码不符即 CI 红(跑本脚本重新生成即修)。

Usage:
  python scripts/dump_system_map.py          # 写 docs/_generated/system-map.json
  python scripts/dump_system_map.py --check   # 只比对,不写(committed == fresh?)
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
OUT = ROOT / "docs" / "_generated" / "system-map.json"
DECLARATIONS = ROOT / "docs" / "system-map" / "declarations.json"

sys.path.insert(0, str(SCRIPTS))
import check_doc_drift as cdd  # noqa: E402  复用扫描器,不复制计数逻辑
from system_map_contract import validate_system_map  # noqa: E402


def _specialist_roster() -> list[str]:
    return cdd.specialist_roster()


def _twin_partition_roster() -> list[str]:
    return cdd.twin_partition_roster()


def _source(path: Path, *, symbol: str | None = None) -> dict:
    value = {"type": "code", "path": path.relative_to(ROOT).as_posix()}
    if symbol:
        value["symbol"] = symbol
    return value


def _slug_part(value: str) -> str:
    if value.startswith("[") and value.endswith("]"):
        value = f"param-{value[1:-1]}"
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "root"


def _route_entity_id(surface: str, route: str) -> str:
    parts = [_slug_part(part) for part in route.strip("/").split("/") if part]
    suffix = ".".join(parts) if parts else "root"
    return f"surface.{surface}.{suffix}"


def _mobile_route(path: Path) -> str:
    rel = path.relative_to(cdd.MOBILE / "app").with_suffix("")
    parts = [part for part in rel.parts if not (part.startswith("(") and part.endswith(")"))]
    if parts and parts[-1] == "index":
        parts.pop()
    return "/" + "/".join(parts) if parts else "/"


def _mobile_surfaces() -> tuple[list[dict], list[dict]]:
    app = cdd.MOBILE / "app"
    entities: list[dict] = []
    relations: list[dict] = []
    excluded_names = {"_layout.tsx", "+html.tsx", "+not-found.tsx"}
    for path in sorted(app.rglob("*.tsx")):
        if path.name in excluded_names or path.name.endswith((".test.tsx", ".spec.tsx")):
            continue
        if "__tests__" in path.parts:
            continue
        route = _mobile_route(path)
        entity_id = _route_entity_id("mobile", route)
        source = _source(path)
        entities.append({
            "id": entity_id,
            "kind": "surface",
            "name": f"Mobile {route}",
            "coverage": "complete",
            "source": source,
            "owner": "mobile",
            "tags": ["mobile"],
        })
        relations.append({
            "from": "component.mobile",
            "type": "renders",
            "to": entity_id,
            "coverage": "complete",
            "source": source,
        })
    return entities, relations


def _web_surfaces() -> tuple[list[dict], list[dict]]:
    app = cdd.FRONTEND / "src" / "app"
    entities: list[dict] = []
    relations: list[dict] = []
    for path in sorted(app.rglob("page.tsx")):
        if "__tests__" in path.parts:
            continue
        rel = path.parent.relative_to(app)
        parts = [part for part in rel.parts if not (part.startswith("(") and part.endswith(")"))]
        route = "/" + "/".join(parts) if parts else "/"
        entity_id = _route_entity_id("web", route)
        source = _source(path)
        entities.append({
            "id": entity_id,
            "kind": "surface",
            "name": f"Web {route}",
            "coverage": "complete",
            "source": source,
            "owner": "web",
            "tags": ["web"],
        })
        relations.append({
            "from": "component.frontend",
            "type": "renders",
            "to": entity_id,
            "coverage": "complete",
            "source": source,
        })
    return entities, relations


def _is_celery_task_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id == "shared_task"
    return isinstance(target, ast.Attribute) and target.attr == "task"


def _celery_jobs() -> tuple[list[dict], list[dict]]:
    tasks_root = cdd.BACKEND / "app" / "tasks"
    entities: list[dict] = []
    relations: list[dict] = []
    for path in sorted(tasks_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module = path.relative_to(tasks_root).with_suffix("").as_posix()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(_is_celery_task_decorator(item) for item in node.decorator_list):
                continue
            entity_id = f"job.celery.{_slug_part(module)}.{_slug_part(node.name)}"
            source = _source(path, symbol=node.name)
            entities.append({
                "id": entity_id,
                "kind": "job",
                "name": node.name,
                "coverage": "complete",
                "source": source,
                "owner": "backend",
                "tags": ["celery"],
            })
            relations.append({
                "from": entity_id,
                "type": "partOf",
                "to": "component.celery-worker",
                "coverage": "complete",
                "source": source,
            })
    return entities, relations


def _load_declarations() -> dict:
    return json.loads(DECLARATIONS.read_text(encoding="utf-8"))


def build_map() -> dict:
    """单一真源的代码派生系统事实。确定性(sorted,无时间戳)。"""
    rules = cdd.count_register_decorators(
        cdd.BACKEND / "app" / "agents" / "safety_guardian" / "rules"
    )
    declarations = _load_declarations()
    entities = list(declarations["entities"])
    relations = list(declarations["relations"])
    for build in (_mobile_surfaces, _web_surfaces, _celery_jobs):
        generated_entities, generated_relations = build()
        entities.extend(generated_entities)
        relations.extend(generated_relations)
    for relation in relations:
        if "flows" in relation:
            relation["flows"] = sorted(relation["flows"])
    result = {
        "_note": "DO NOT EDIT — System Map v2 generated by scripts/dump_system_map.py. "
                 "代码事实来自扫描器，治理事实来自 docs/system-map/declarations.json。",
        "schema_version": "2.0",
        "entities": sorted(entities, key=lambda item: item["id"]),
        "relations": sorted(
            relations,
            key=lambda item: (item["from"], item["type"], item["to"]),
        ),
        "coverage": dict(sorted(declarations["coverage"].items())),
        "counts": {
            "safety_rules_total": sum(rules.values()),
            "specialists": cdd.count_specialists(),
            "twin_partitions": cdd.count_twin_partitions(),
            "api_routers": cdd.count_api_include_routers(),
            "celery_tasks": cdd.count_celery_tasks(),
            "model_files": cdd.count_model_files(),
            "service_files": cdd.count_service_files(),
            "mobile_routes": cdd.count_mobile_routes(),
            "web_pages": cdd.count_web_pages(),
        },
        "safety_rules_by_category": dict(sorted(rules.items())),
        "specialists_roster": _specialist_roster(),
        "twin_partitions_roster": _twin_partition_roster(),
    }
    validate_system_map(result)
    return result


def _serialize(m: dict) -> str:
    return json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    fresh = build_map()
    if "--check" in argv:
        if not OUT.exists():
            print(f"❌ {OUT} 缺失,跑 scripts/dump_system_map.py", file=sys.stderr)
            return 1
        committed = json.loads(OUT.read_text(encoding="utf-8"))
        if committed != fresh:
            print(f"❌ {OUT} 与代码不符,跑 scripts/dump_system_map.py 重新生成", file=sys.stderr)
            return 1
        print(f"✅ {OUT.relative_to(ROOT)} 与代码一致")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_serialize(fresh), encoding="utf-8")
    print(f"✅ wrote {OUT.relative_to(ROOT)}")
    print(_serialize(fresh["counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
