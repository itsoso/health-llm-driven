#!/usr/bin/env python3
"""Generate the Mobile access map and product-flow knowledge graph.

The system-map layer only stays useful if structural facts are generated from
code. This scanner turns Expo routes, tab entries, settings rows, and static
router.push calls into a deterministic graph that agents can read before
changing Mobile IA or user journeys.

Usage:
  python scripts/dump_mobile_access_map.py
  python scripts/dump_mobile_access_map.py --check
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MOBILE = ROOT / "mobile"
MOBILE_APP = MOBILE / "app"
MOBILE_COMPONENTS = MOBILE / "components"
OUT = ROOT / "docs" / "_generated" / "mobile-access-map.json"
MOBILE_OUT = MOBILE / "constants" / "mobileAccessMap.generated.ts"

ROUTE_FILE_SUFFIXES = {".tsx"}
SKIP_PARTS = {"__tests__"}
SKIP_ROUTE_SUFFIXES = (".test.tsx", ".spec.tsx")
GROUP_RE = re.compile(r"^\(.+\)$")
DYNAMIC_SEGMENT_RE = re.compile(r"^\[[^/]+\]$")

DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("system_transparency", ("system-map", "app-diagnostics", "data-integrity", "admin-llm", "privacy-policy")),
    ("medication_supplement", ("medication", "medications", "deprescribing", "supplement")),
    ("data_devices", ("device", "rokid", "location", "calendar", "import", "shared", "genetic", "snp")),
    ("capture", ("record", "symptom", "diet", "meal", "body-measurements", "prescription-scan", "medical-exam")),
    ("movement", ("fitness", "exercise", "workout", "live-run", "movement", "pushup")),
    ("review", ("progress", "monthly", "biological", "longevity", "indicator", "sleep", "liver", "trace", "consultation")),
    ("daily_execution", ("agenda", "day-schedule", "timeline", "guided-task", "reminders", "notification", "alerts")),
    ("coach", ("chat", "voice-chat", "coach", "reva", "ai-profile", "llm")),
    ("settings_admin", ("settings", "directives", "memory", "family", "eye-care", "voice-style", "connection")),
]

DOMAIN_OBJECTS: dict[str, list[str]] = {
    "daily_execution": ["HealthAgendaItem", "LeverageAction", "ExecutionEvent"],
    "capture": ["ExecutionEvent", "HealthTwin", "WriteIntent"],
    "coach": ["LeveragePoint", "LeverageAction", "SafetyGuardian"],
    "review": ["InterventionCycle", "HealthTwin", "HealthProblem"],
    "data_devices": ["HealthTwin", "ExecutionEvent", "SafetyGuardian"],
    "medication_supplement": ["HealthProtocol", "SafetyGuardian", "ExecutionEvent"],
    "movement": ["HealthProtocol", "LeverageAction", "ExecutionEvent"],
    "system_transparency": ["WriteIntent"],
    "settings_admin": ["WriteIntent", "HealthProgram"],
    "other": ["HealthTwin"],
}


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def discover_route_files() -> list[Path]:
    """Return Expo route files that represent Mobile pages/special routes."""
    if not MOBILE_APP.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(MOBILE_APP.rglob("*.tsx")):
        if path.name == "_layout.tsx":
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name.endswith(SKIP_ROUTE_SUFFIXES):
            continue
        files.append(path)
    return files


def _raw_route_parts(path: Path) -> list[str]:
    rel = path.relative_to(MOBILE_APP).with_suffix("")
    return list(rel.parts)


def _route_id_from_parts(parts: list[str]) -> str:
    if parts and parts[-1] == "index":
        parts = parts[:-1]
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def _strip_route_groups(route_id: str) -> str:
    parts = [part for part in route_id.strip("/").split("/") if part]
    stripped = [part for part in parts if not GROUP_RE.match(part)]
    return "/" + "/".join(stripped) if stripped else "/"


def _route_aliases(route_id: str, raw_parts: list[str]) -> list[str]:
    aliases = {route_id, _strip_route_groups(route_id)}
    raw_route = "/" + "/".join(raw_parts)
    aliases.add(raw_route)
    if raw_parts and raw_parts[-1] == "index":
        aliases.add("/" + "/".join(raw_parts[:-1]) if len(raw_parts) > 1 else "/")
    return sorted(aliases)


def route_for_file(path: Path, tab_meta: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    raw_parts = _raw_route_parts(path)
    route_id = _route_id_from_parts(raw_parts)
    label = _label_for_route(route_id, raw_parts, tab_meta or {})
    domain = _domain_for_route(route_id)
    return {
        "id": route_id,
        "path": _strip_route_groups(route_id),
        "aliases": _route_aliases(route_id, raw_parts),
        "file": _rel(path),
        "label": label,
        "kind": _kind_for_route(route_id, raw_parts, tab_meta or {}),
        "domain": domain,
        "surface_role": _surface_role_for_route(route_id, raw_parts, tab_meta or {}),
        "first_class_objects": DOMAIN_OBJECTS.get(domain, DOMAIN_OBJECTS["other"]),
        "dynamic": any(DYNAMIC_SEGMENT_RE.match(part) for part in raw_parts),
    }


def _kind_for_route(route_id: str, raw_parts: list[str], tab_meta: dict[str, dict[str, Any]]) -> str:
    if raw_parts and raw_parts[-1].startswith("+"):
        return "expo_special"
    if route_id == "/login":
        return "auth"
    if route_id.startswith("/(tabs)"):
        tab_name = raw_parts[1] if len(raw_parts) > 1 else "index"
        if raw_parts[-1] == "index" and len(raw_parts) == 1:
            tab_name = "index"
        meta = tab_meta.get(tab_name)
        return "hidden_tab" if meta and meta.get("hidden") else "main_tab"
    if any(DYNAMIC_SEGMENT_RE.match(part) for part in raw_parts):
        return "dynamic_detail"
    return "screen"


def _surface_role_for_route(route_id: str, raw_parts: list[str], tab_meta: dict[str, dict[str, Any]]) -> str:
    if route_id in {"/settings", "/(tabs)/me"}:
        return "settings_hub"
    if route_id == "/(tabs)":
        return "home"
    if route_id.startswith("/(tabs)"):
        tab_name = raw_parts[1] if len(raw_parts) > 1 else "index"
        if tab_name in tab_meta and not tab_meta[tab_name].get("hidden"):
            return "primary_tab"
        return "hidden_tab"
    if route_id == "/login":
        return "auth"
    if any(DYNAMIC_SEGMENT_RE.match(part) for part in raw_parts):
        return "detail"
    if route_id in {"/system-map", "/app-diagnostics", "/data-integrity"}:
        return "transparency"
    return "secondary_screen"


def _label_for_route(route_id: str, raw_parts: list[str], tab_meta: dict[str, dict[str, Any]]) -> str:
    if route_id.startswith("/(tabs)"):
        tab_name = raw_parts[1] if len(raw_parts) > 1 else "index"
        if raw_parts[-1] == "index" and len(raw_parts) == 1:
            tab_name = "index"
        if tab_name in tab_meta and tab_meta[tab_name].get("title"):
            return str(tab_meta[tab_name]["title"])
    fallback = raw_parts[-1] if raw_parts else "index"
    if fallback == "index" and len(raw_parts) > 1:
        fallback = raw_parts[-2]
    return fallback.replace("-", " ").replace("[", "").replace("]", "")


def _domain_for_route(route_id: str) -> str:
    key = route_id.lower()
    for domain, needles in DOMAIN_RULES:
        if any(needle in key for needle in needles):
            return domain
    if route_id in {"/", "/(tabs)"}:
        return "daily_execution"
    return "other"


def parse_tab_meta() -> dict[str, dict[str, Any]]:
    path = MOBILE_APP / "(tabs)" / "_layout.tsx"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r"<Tabs\.Screen\s+name=\"([^\"]+)\"(?P<body>.*?)(?=<Tabs\.Screen|</Tabs>)", text, re.S):
        name = match.group(1)
        body = match.group("body")
        title_match = re.search(r"title:\s*['\"]([^'\"]+)['\"]", body)
        out[name] = {
            "name": name,
            "title": title_match.group(1) if title_match else name,
            "hidden": bool(re.search(r"href:\s*null", body)),
        }
    return out


def parse_stack_screens(route_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    path = MOBILE_APP / "_layout.tsx"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    edges: list[dict[str, Any]] = []
    for match in re.finditer(r"<Stack\.Screen\s+name=\"([^\"]+)\"", text):
        name = match.group(1)
        target_alias = "/" + name
        target = resolve_target(target_alias, route_index)
        edges.append(_edge(
            kind="stack_registered",
            source="root_stack",
            target_raw=target_alias,
            target=target,
            source_file=_rel(path),
            line=_line_for_offset(text, match.start()),
            label=name,
        ))
    return edges


def parse_settings_edges(route_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    path = MOBILE_APP / "settings.tsx"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    rows: list[tuple[str, str, int]] = []
    for match in re.finditer(r"<(?P<component>SettingRow|LocationSettingsRow)\b(?P<body>.*?)/>", text, re.S):
        component = match.group("component")
        body = match.group("body")
        label_match = re.search(r"label=\"([^\"]+)\"", body)
        label = label_match.group(1) if label_match else ("GPS / 城市定位" if component == "LocationSettingsRow" else component)
        target_match = re.search(r"router\.push\(\s*['\"]([^'\"]+)['\"]", body)
        if not target_match:
            continue
        rows.append((label, target_match.group(1), _line_for_offset(text, match.start())))

    edges: list[dict[str, Any]] = []
    for source in ("/settings", "/(tabs)/me"):
        for label, raw_target, line in rows:
            target = resolve_target(raw_target, route_index)
            edges.append(_edge(
                kind="settings_row",
                source=source,
                target_raw=raw_target,
                target=target,
                source_file=_rel(path),
                line=line,
                label=label,
            ))
    return edges


def parse_router_edges(route_index: dict[str, dict[str, Any]], file_to_route: dict[str, str]) -> list[dict[str, Any]]:
    roots = [MOBILE_APP, MOBILE_COMPONENTS]
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(sorted(root.rglob("*.tsx")))
            files.extend(sorted(root.rglob("*.ts")))

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int, str]] = set()
    for path in files:
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name.endswith(SKIP_ROUTE_SUFFIXES):
            continue
        text = path.read_text(encoding="utf-8")
        source = file_to_route.get(_rel(path), f"component:{_rel(path)}")
        for method, raw_target, offset in _router_targets(text):
            target = resolve_target(raw_target, route_index)
            line = _line_for_offset(text, offset)
            key = (source, raw_target, method, line, _rel(path))
            if key in seen:
                continue
            seen.add(key)
            edges.append(_edge(
                kind=f"router_{method}",
                source=source,
                target_raw=raw_target,
                target=target,
                source_file=_rel(path),
                line=line,
            ))
        for raw_target, offset in _link_targets(text):
            target = resolve_target(raw_target, route_index)
            line = _line_for_offset(text, offset)
            key = (source, raw_target, "link", line, _rel(path))
            if key in seen:
                continue
            seen.add(key)
            edges.append(_edge(
                kind="link_href",
                source=source,
                target_raw=raw_target,
                target=target,
                source_file=_rel(path),
                line=line,
            ))
    return edges


def _router_targets(text: str) -> list[tuple[str, str, int]]:
    targets: list[tuple[str, str, int]] = []
    literal = re.compile(r"router\.(push|replace)\(\s*([\"'`])(?P<target>.*?)(?<!\\)\2", re.S)
    obj = re.compile(r"router\.(push|replace)\(\s*\{\s*pathname:\s*([\"'`])(?P<target>.*?)(?<!\\)\2", re.S)
    for regex in (literal, obj):
        for match in regex.finditer(text):
            targets.append((match.group(1), match.group("target"), match.start()))
    return targets


def _link_targets(text: str) -> list[tuple[str, int]]:
    return [(m.group(2), m.start()) for m in re.finditer(r"<Link\b[^>]*href=([\"'])([^\"']+)\1", text)]


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _normalize_target(raw: str) -> str:
    target = raw.strip()
    target = target.split("?", 1)[0]
    target = re.sub(r"\$\{[^}]+\}", "[param]", target)
    if target and not target.startswith("/") and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        target = "/" + target
    return target or raw


def resolve_target(raw: str, route_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    normalized = _normalize_target(raw)
    alias_index: dict[str, str] = {}
    for route_id, node in route_index.items():
        for alias in node["aliases"]:
            alias_index[alias] = route_id
    if normalized in alias_index:
        route_id = alias_index[normalized]
        return {"id": route_id, "path": route_index[route_id]["path"], "resolved": True}

    dynamic = _match_dynamic_alias(normalized, route_index)
    if dynamic:
        return {"id": dynamic, "path": route_index[dynamic]["path"], "resolved": True}

    return {"id": normalized, "path": normalized, "resolved": False}


def _match_dynamic_alias(target: str, route_index: dict[str, dict[str, Any]]) -> str | None:
    target_parts = [part for part in target.strip("/").split("/") if part]
    for route_id, node in sorted(route_index.items()):
        for alias in node["aliases"]:
            alias_parts = [part for part in alias.strip("/").split("/") if part]
            if len(alias_parts) != len(target_parts):
                continue
            ok = True
            for alias_part, target_part in zip(alias_parts, target_parts):
                if DYNAMIC_SEGMENT_RE.match(alias_part):
                    continue
                if target_part == "[param]" and DYNAMIC_SEGMENT_RE.match(alias_part):
                    continue
                if alias_part != target_part:
                    ok = False
                    break
            if ok:
                return route_id
    return None


def _edge(
    *,
    kind: str,
    source: str,
    target_raw: str,
    target: dict[str, Any],
    source_file: str,
    line: int,
    label: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{kind}:{source}:{target['id']}:{source_file}:{line}:{label or ''}",
        "kind": kind,
        "source": source,
        "target": target["id"],
        "target_path": target["path"],
        "target_raw": target_raw,
        "resolved": bool(target["resolved"]),
        "source_file": source_file,
        "line": line,
        **({"label": label} if label else {}),
    }


def _journey(
    *,
    jid: str,
    title: str,
    scenario: str,
    route_ids: list[str],
    core_loop_steps: list[str],
    assessment: str,
    improvement: str,
    route_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": jid,
        "title": title,
        "scenario": scenario,
        "routes": [
            {
                "id": rid,
                "label": route_index[rid]["label"],
                "domain": route_index[rid]["domain"],
            }
            for rid in route_ids
            if rid in route_index
        ],
        "core_loop_steps": core_loop_steps,
        "assessment": assessment,
        "improvement": improvement,
    }


def build_journeys(route_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _journey(
            jid="daily_execution_loop",
            title="日常执行闭环",
            scenario="用户打开 App 后完成今日最高杠杆动作,必要时进入记录或私教解释。",
            route_ids=["/(tabs)", "/agenda", "/guided-task", "/(tabs)/record", "/(tabs)/chat", "/my-progress"],
            core_loop_steps=["Agenda top action", "Execution event", "Outcome review"],
            assessment="主 Tab 与 Health OS core loop 对齐,但详情页入口分散在首页卡片和设置 Hub。",
            improvement="把今日行动卡的后续验证入口显性化,减少用户从完成动作到结果追踪的路径跳转。",
            route_index=route_index,
        ),
        _journey(
            jid="fast_capture_loop",
            title="快速记录闭环",
            scenario="用户快速记录饮食、俯卧撑、症状、语音输入,进入 Agent 做结构化确认。",
            route_ids=["/(tabs)", "/(tabs)/record", "/symptom-record", "/voice-chat", "/(tabs)/chat"],
            core_loop_steps=["Capture", "HealthTwin update", "Safety Gate"],
            assessment="记录 Tab 位置正确,但语音/文本/拍照/运动记录分散在多个页面和组件入口。",
            improvement="记录页应成为所有低摩擦 capture 的统一入口,并把运动/饮食/症状的常用动作做成首屏快捷项。",
            route_index=route_index,
        ),
        _journey(
            jid="lab_import_review_loop",
            title="检查报告到医生回路",
            scenario="用户导入体检或医院报告,查看解释、趋势和需要医生确认的事项。",
            route_ids=["/(tabs)/me", "/import", "/medical-exams", "/exam-explain/[id]", "/consultations", "/doctor-loop"],
            core_loop_steps=["Labs", "Digital Health Twin", "Safety Gate", "Clinician review"],
            assessment="能力链完整,但入口主要藏在设置 Hub,对新用户不够像一个明确的报告工作流。",
            improvement="在 Mobile 加“报告/化验”任务流聚合页,把导入、解释、趋势、医生回路串成一步一步的路径。",
            route_index=route_index,
        ),
        _journey(
            jid="medication_supplement_loop",
            title="用药补剂治理闭环",
            scenario="用户查看用药、补剂库存、多药梳理和通知提醒,完成安全与依从性治理。",
            route_ids=["/(tabs)/me", "/medications", "/deprescribing", "/supplement-inventory", "/notification-settings"],
            core_loop_steps=["HealthProtocol", "SafetyGuardian", "Execution event"],
            assessment="功能强但分散,更像工具箱;用户需要理解哪个入口解决什么问题。",
            improvement="按“今天要吃什么/有没有冲突/快没了/要不要复盘”重排信息架构,而不是按功能模块平铺。",
            route_index=route_index,
        ),
        _journey(
            jid="movement_coach_loop",
            title="运动计划到执行闭环",
            scenario="用户查看计划、动作指导、实时跑步/训练和历史运动详情。",
            route_ids=["/(tabs)/me", "/fitness-plan", "/exercise-guide/[key]", "/live-run", "/workout-detail"],
            core_loop_steps=["HealthProtocol", "LeverageAction", "Execution event", "Outcome review"],
            assessment="运动能力有计划、指导、执行和复盘,但入口被设置 Hub 和首页卡片切开。",
            improvement="把运动作为记录页的一级快捷动作,并在 Today 根据恢复状态直接露出“做/降强度/恢复”决策。",
            route_index=route_index,
        ),
        _journey(
            jid="system_transparency_loop",
            title="系统透明化闭环",
            scenario="人或 agent 从 Mobile 看到系统地图、诊断和代码生成事实,再决定下一步改造。",
            route_ids=["/(tabs)/me", "/system-map", "/app-diagnostics"],
            core_loop_steps=["Discovery", "Planning", "Verification"],
            assessment="透明化已进入 Mobile,但目前是摘要视图,还没有完整页面图谱可视化。",
            improvement="下一步在系统地图页增加 Mobile Access Map 分组、旅程和风险列表的展开视图。",
            route_index=route_index,
        ),
    ]


def build_evaluation(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], tab_meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    incoming: dict[str, int] = defaultdict(int)
    product_incoming: dict[str, int] = defaultdict(int)
    outgoing: dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge["resolved"]:
            incoming[edge["target"]] += 1
            if edge["kind"] != "stack_registered":
                product_incoming[edge["target"]] += 1
        outgoing[edge["source"]] += 1

    settings_rows = {
        (edge.get("label", ""), edge["target"])
        for edge in edges
        if edge["kind"] == "settings_row" and edge["source"] == "/settings"
    }
    duplicate_targets = sorted([
        {"target": target, "labels": sorted(labels)}
        for target, labels in sorted(_labels_by_target(settings_rows).items())
        if len(labels) > 1
    ], key=lambda item: (item["target"], item["labels"]))
    low_exposure = [
        node["id"] for node in nodes
        if product_incoming[node["id"]] == 0
        and node["kind"] not in {"expo_special", "auth", "main_tab"}
        and node["id"] not in {"/settings", "/(tabs)/me"}
    ]
    visible_tabs = [
        meta["title"] for meta in tab_meta.values()
        if not meta.get("hidden") and meta["name"] in {"index", "chat", "record", "me"}
    ]
    domain_counts = Counter(node["domain"] for node in nodes)
    unresolved_edges = [edge for edge in edges if not edge["resolved"] and edge["kind"] != "stack_registered"]

    return {
        "core_loop_alignment": {
            "primary_tab_model": visible_tabs,
            "assessment": "今日/私教/记录/我覆盖执行、对话、捕获、管理,方向正确;设置 Hub 承载过多深功能。",
        },
        "settings_hub": {
            "unique_rows": len(settings_rows),
            "risk": "high_density" if len(settings_rows) >= 30 else "medium_density",
            "duplicate_targets": duplicate_targets,
            "assessment": "设置页已经从设置变成全量功能目录,应拆成健康数据、计划执行、设备与诊断几个工作流入口。",
        },
        "reachability": {
            "low_exposure_routes": sorted(low_exposure),
            "unresolved_static_edges": [
                {
                    "source": edge["source"],
                    "target_raw": edge["target_raw"],
                    "source_file": edge["source_file"],
                    "line": edge["line"],
                }
                for edge in unresolved_edges
            ],
        },
        "domain_distribution": dict(sorted(domain_counts.items())),
        "recommendations": [
            "把 Mobile 首屏围绕今日最高杠杆动作、快速记录和验证入口继续收敛。",
            "把设置 Hub 拆成可理解的产品工作流,减少用户从功能名猜路径。",
            "把报告导入、医生回路、用药补剂、运动执行分别沉淀成 canonical journey,每次新增页面必须挂到其中一个 journey 或声明新 journey。",
            "对 low_exposure_routes 做产品审查:保留为 deep link、并入现有路径、隐藏开发入口,或删除。",
            "后续 UI 可用本 JSON 生成 Mobile Access Map 页面,而不是手写页面清单。",
        ],
    }


def _labels_by_target(settings_rows: set[tuple[str, str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for label, target in settings_rows:
        out[target].add(label)
    return out


def build_mobile_access_map() -> dict[str, Any]:
    tab_meta = parse_tab_meta()
    route_files = discover_route_files()
    nodes = [route_for_file(path, tab_meta) for path in route_files]
    route_index = {node["id"]: node for node in nodes}
    file_to_route = {node["file"]: node["id"] for node in nodes}

    edges: list[dict[str, Any]] = []
    for name, meta in tab_meta.items():
        target_id = "/(tabs)" if name == "index" else f"/(tabs)/{name}"
        target = resolve_target(target_id, route_index)
        edges.append(_edge(
            kind="tab_entry",
            source="bottom_tab_bar",
            target_raw=target_id,
            target=target,
            source_file=_rel(MOBILE_APP / "(tabs)" / "_layout.tsx"),
            line=1,
            label=str(meta["title"]),
        ))
    edges.extend(parse_stack_screens(route_index))
    edges.extend(parse_settings_edges(route_index))
    edges.extend(parse_router_edges(route_index, file_to_route))
    edges = sorted(edges, key=lambda e: (e["kind"], e["source"], e["target"], e["source_file"], e["line"], e.get("label", "")))

    journeys = build_journeys(route_index)
    evaluation = build_evaluation(nodes, edges, tab_meta)

    return {
        "_note": "DO NOT EDIT — generated by scripts/dump_mobile_access_map.py from Mobile code. "
                 "It models Expo routes, static navigation edges, canonical user journeys, and IA review signals.",
        "counts": {
            "routes": len(nodes),
            "edges": len(edges),
            "settings_rows": evaluation["settings_hub"]["unique_rows"],
            "journeys": len(journeys),
            "low_exposure_routes": len(evaluation["reachability"]["low_exposure_routes"]),
            "unresolved_static_edges": len(evaluation["reachability"]["unresolved_static_edges"]),
        },
        "nodes": nodes,
        "edges": edges,
        "journeys": journeys,
        "evaluation": evaluation,
    }


def _serialize(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _serialize_mobile_ts(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        "// DO NOT EDIT. Generated by scripts/dump_mobile_access_map.py from Mobile code.\n"
        "// Mobile uses this snapshot to show the access map without reading docs at runtime.\n"
        f"export const mobileAccessMapSnapshot = {payload} as const;\n"
        "export type MobileAccessMapSnapshot = typeof mobileAccessMapSnapshot;\n"
    )


def main(argv: list[str]) -> int:
    fresh = build_mobile_access_map()
    if "--check" in argv:
        ok = True
        if not OUT.exists():
            print(f"❌ {OUT} 缺失,跑 scripts/dump_mobile_access_map.py", file=sys.stderr)
            ok = False
        elif OUT.read_text(encoding="utf-8") != _serialize(fresh):
            print(f"❌ {OUT} 与 Mobile 代码不符,跑 scripts/dump_mobile_access_map.py 重新生成", file=sys.stderr)
            ok = False
        if not MOBILE_OUT.exists():
            print(f"❌ {MOBILE_OUT} 缺失,跑 scripts/dump_mobile_access_map.py", file=sys.stderr)
            ok = False
        elif MOBILE_OUT.read_text(encoding="utf-8") != _serialize_mobile_ts(fresh):
            print(f"❌ {MOBILE_OUT} 与 Mobile 代码不符,跑 scripts/dump_mobile_access_map.py 重新生成", file=sys.stderr)
            ok = False
        if not ok:
            return 1
        print(f"✅ {OUT.relative_to(ROOT)} 与 Mobile 代码一致")
        print(f"✅ {MOBILE_OUT.relative_to(ROOT)} 与 Mobile 代码一致")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_serialize(fresh), encoding="utf-8")
    MOBILE_OUT.parent.mkdir(parents=True, exist_ok=True)
    MOBILE_OUT.write_text(_serialize_mobile_ts(fresh), encoding="utf-8")
    print(f"✅ wrote {OUT.relative_to(ROOT)}")
    print(f"✅ wrote {MOBILE_OUT.relative_to(ROOT)}")
    print(_serialize(fresh["counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
