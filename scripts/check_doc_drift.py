#!/usr/bin/env python3
"""
Doc-drift check: generated system facts and active architecture narrative stay current.

Background:
历史上文档里硬编码的 "47 条安全规则"、"10 specialists"、"13 Twin 分区"
随代码演进发生过静默漂移 —— 文档在骗未来的 Claude。
ARCHITECTURE.md 首次落地时 ("9 specialists" "12 分区" "75 mobile 路由")
也立刻暴露出同样问题, 所以把文档里的数字也纳入校验。

Mechanism:
  - 扫描代码并与 docs/_generated/system-map.json 做确定性等值比较
  - 拒绝在 ARCHITECTURE.md 活跃叙事中复制可变架构计数
  - 校验 Safety/Specialist/Twin 等显式治理契约
  - 任一不一致 → exit 1, CI 挂掉

When adding/removing a safety rule / specialist / twin partition / API 路由 /
Celery 任务 / model / service / mobile route, you must:
  1. 让代码处于目标状态
  2. 运行 python scripts/dump_system_map.py
  3. 保持叙事只引用生成快照；只有治理契约故意变化时才更新 EXPECTED

Usage:
  python scripts/check_doc_drift.py         # from repo root
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
MOBILE = ROOT / "mobile"
FRONTEND = ROOT / "frontend"

EXPECTED: dict = {
    "safety_rules": {
        "vitals": 12,
        "labs": 9,
        "ddi": 7,
        "dsi": 8,
        "pgx": 10,
        "pgx_cpic_table": 0,  # 纯数据文件, 无 @register, 但 glob 会扫到 → 必须登记防 "unknown file"
        "training_load": 3,
        "cgm": 6,
        "symptoms": 6,
        "cardiac": 1,
        "problem_red_lines": 1,
        "guidance_red_lines": 2,
    },
    "specialists_count": 13,
    "twin_partitions": 15,
    # KB 对账 auto-approve 阈(founder ratified §10)。运行时真闸(C8);此处钉死防悄悄调低无 CI 拦。
    "kb_auto_approve_tau": "0.95",
}


def count_register_decorators(rules_dir: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in sorted(rules_dir.glob("*.py")):
        if p.name == "__init__.py":
            continue
        text = p.read_text(encoding="utf-8")
        out[p.stem] = len(re.findall(r"^@register\b", text, re.MULTILINE))
    return out


def specialist_roster() -> list[str]:
    """Return specialist constructors registered by ``_build_registry``.

    This intentionally parses the registry instead of importing it: the doc/system-map
    gate must not require application secrets, a database URL, or backend side effects.
    """
    path = BACKEND / "app" / "orchestrator" / "specialists.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "_build_registry":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Return) or not isinstance(child.value, ast.List):
                continue
            names: list[str] = []
            for item in child.value.elts:
                if not isinstance(item, ast.Call):
                    continue
                if isinstance(item.func, ast.Name):
                    names.append(item.func.id)
                elif isinstance(item.func, ast.Attribute):
                    names.append(item.func.attr)
            if names:
                return sorted(names)
    raise RuntimeError(f"specialist registry return list not found: {path}")


def twin_partition_roster() -> list[str]:
    """Return annotated HealthTwin fields, excluding non-partition containers."""
    path = BACKEND / "app" / "twin" / "schema.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "HealthTwin":
            continue
        fields = {
            item.target.id
            for item in node.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        }
        return sorted(fields - {"meta", "gene_config"})
    raise RuntimeError(f"HealthTwin class not found: {path}")


def count_specialists() -> int:
    return len(specialist_roster())


def count_twin_partitions() -> int:
    """HealthTwin fields minus container/meta fields."""
    return len(twin_partition_roster())


# ---------- Code scanners (stateless, no import side-effects) ----------

def count_api_include_routers() -> int:
    """backend/app/api/main.py 中 app.include_router(...) 的次数."""
    p = BACKEND / "app" / "api" / "main.py"
    if not p.exists():
        return 0
    return len(re.findall(r"\.include_router\(", p.read_text(encoding="utf-8")))


def count_celery_tasks() -> int:
    """backend/app/tasks/**/*.py 里 @celery_app.task / @shared_task / @app.task 装饰器总数."""
    root = BACKEND / "app" / "tasks"
    if not root.is_dir():
        return 0
    total = 0
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        total += len(re.findall(
            r"^@(?:celery_app|shared_task|app)\.task(?:\b|\()",
            text,
            re.MULTILINE,
        ))
    return total


def count_model_files() -> int:
    """backend/app/models/*.py 非 __init__ 的文件数."""
    root = BACKEND / "app" / "models"
    if not root.is_dir():
        return 0
    return sum(1 for p in root.glob("*.py") if p.name != "__init__.py")


def count_service_files() -> int:
    """backend/app/services/**/*.py 非 __init__ 的文件数."""
    root = BACKEND / "app" / "services"
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*.py") if p.name != "__init__.py")


def count_mobile_routes() -> int:
    """mobile/app/**/*.tsx 排除 _layout.tsx (expo-router 约定)."""
    root = MOBILE / "app"
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*.tsx") if p.name != "_layout.tsx")


def count_web_pages() -> int:
    """frontend/src/app/**/page.tsx 的数量."""
    root = FRONTEND / "src" / "app"
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("page.tsx"))


# ---------- Doc assertion scanner ----------

def _doc_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in ("CLAUDE.md", "docs/ARCHITECTURE.md"):
        p = ROOT / name
        if p.exists():
            out[name] = p.read_text(encoding="utf-8")
    return out


_MANUAL_ARCHITECTURE_COUNT_PATTERNS = (
    r"\b\d+\s+Specialists?\b",
    r"\b\d+\s*分区\b",
    r"\b\d+\s*条\s*,\s*主要分\s*\d+\s*域",
    r"\b\d+\s*页\s*,\s*主要分域",
    r"Celery\s*调度\(\d+\s*个任务\)",
    r"\b\d+\s*tab\b",
    r"stack pages\s*[—-]\s*\d+\+",
    r"AGENTS\.md`?\s*\|\s*AI Agent 开发规范,\s*\d+\s*行",
    r"\b\d+\s*个模型\s+entry\b",
    r"\b\d+\s*个\s+AppIntent\b",
    r"\b\d+\s*个\s+specialist\s*单测\b",
    r"\b\d+\s*API\s*路由\b",
    r"\b\d+\s*Celery\s*任务\b",
    r"\b\d+\s+(?:services?|models?)\b",
    r"\b\d+\s*mobile\s*路由\b",
    r"\b\d+\s*web\s*页\b",
)


def find_manual_architecture_counts(text: str) -> list[str]:
    """Return mutable architecture counts that must come from system-map.json."""
    active_text = text.partition("### 16.3 演进 log")[0]
    matches = [
        (match.start(), match.group(0))
        for pattern in _MANUAL_ARCHITECTURE_COUNT_PATTERNS
        for match in re.finditer(pattern, active_text)
    ]
    return [claim for _, claim in sorted(matches)]


def main(*, fresh_map: dict | None = None) -> int:
    failures: list[str] = []

    # 1. Safety rules per category
    actual_rules = count_register_decorators(
        BACKEND / "app" / "agents" / "safety_guardian" / "rules"
    )
    expected_rules = EXPECTED["safety_rules"]
    for cat, expected in expected_rules.items():
        got = actual_rules.get(cat, 0)
        if got != expected:
            failures.append(
                f"  rules/{cat}.py: expected {expected} @register, found {got}"
            )
    extras = set(actual_rules) - set(expected_rules)
    if extras:
        failures.append(
            f"  unknown rule file(s) not in EXPECTED: {sorted(extras)}"
        )

    total_expected = sum(expected_rules.values())
    total_actual = sum(actual_rules.values())
    if total_actual != total_expected:
        failures.append(
            f"  total safety rules: expected {total_expected}, found {total_actual}"
        )

    # 2. Specialists count (via registry import)
    try:
        actual_specialists = count_specialists()
    except Exception as e:
        failures.append(f"  specialists registry import failed: {e}")
        actual_specialists = -1
    else:
        if actual_specialists != EXPECTED["specialists_count"]:
            failures.append(
                f"  specialists: expected {EXPECTED['specialists_count']}, "
                f"found {actual_specialists}"
            )

    # 3. Twin partitions
    try:
        actual_partitions = count_twin_partitions()
    except Exception as e:
        failures.append(f"  twin schema import failed: {e}")
        actual_partitions = -1
    else:
        if actual_partitions != EXPECTED["twin_partitions"]:
            failures.append(
                f"  twin partitions: expected {EXPECTED['twin_partitions']}, "
                f"found {actual_partitions}"
            )

    # 4. Architecture counts are code-derived only. Narrative docs link to
    # docs/_generated/system-map.json instead of duplicating mutable numbers.
    architecture_text = _doc_texts().get("docs/ARCHITECTURE.md", "")
    for claim in find_manual_architecture_counts(architecture_text):
        failures.append(
            "  architecture narrative: mutable count "
            f"'{claim}' must reference docs/_generated/system-map.json"
        )

    # 4b. KB 对账 auto-approve τ 钉死 (founder ratified §10)。悄悄调低 τ 无 CI 拦 = 安全护栏缺口。
    judge_src = BACKEND / "app" / "services" / "kb_reconciliation_judge.py"
    if judge_src.exists():
        m = re.search(r"_AUTO_APPROVE_TAU\s*=\s*([0-9.]+)", judge_src.read_text(encoding="utf-8"))
        if not m:
            failures.append("  kb_auto_approve_tau: 未在 kb_reconciliation_judge.py 找到 _AUTO_APPROVE_TAU")
        elif m.group(1) != EXPECTED["kb_auto_approve_tau"]:
            failures.append(
                f"  kb_auto_approve_tau: 代码 _AUTO_APPROVE_TAU={m.group(1)} != 钉死值 "
                f"{EXPECTED['kb_auto_approve_tau']}(改 τ 须 founder 批 + 同步 EXPECTED + 设计 §10)"
            )

    # 5. System-map 代码派生事实 (docs/_generated/system-map.json) 与代码一致。
    #    System-map 防漂移核心: 计数/roster 只准从代码生成进无人手改的 JSON, committed 与
    #    代码不符即红 (跑 scripts/dump_system_map.py 重新生成即修)。见 docs/system-map/INDEX.md。
    try:
        import json
        sys.path.insert(0, str(ROOT / "scripts"))
        from dump_system_map import OUT as SYSMAP_OUT
        if fresh_map is None:
            from dump_system_map import build_map

            fresh_map = build_map()
        if not SYSMAP_OUT.exists():
            failures.append(
                "  system-map: docs/_generated/system-map.json 缺失, "
                "跑 python scripts/dump_system_map.py 生成并提交"
            )
        else:
            committed_map = json.loads(SYSMAP_OUT.read_text(encoding="utf-8"))
            if committed_map != fresh_map:
                failures.append(
                    "  system-map: docs/_generated/system-map.json 与代码不符, "
                    "跑 python scripts/dump_system_map.py 重新生成并提交"
                )
    except Exception as e:  # noqa: BLE001
        failures.append(f"  system-map build/compare failed: {e}")

    if failures:
        print("❌ 架构治理事实与代码已漂移：", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        print(
            "\n修复：\n"
            "  1) 确认代码是目标状态\n"
            "  2) 运行 python scripts/dump_system_map.py 更新代码派生快照\n"
            "  3) 不要把架构计数手写回叙事文档",
            file=sys.stderr,
        )
        return 1

    print("✅ 架构治理事实与代码一致")
    print(f"   safety rules: {total_actual} total {actual_rules}")
    print(f"   specialists:  {actual_specialists}")
    print(f"   twin partitions: {actual_partitions}")
    for key, value in fresh_map["counts"].items():
        print(f"   {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
