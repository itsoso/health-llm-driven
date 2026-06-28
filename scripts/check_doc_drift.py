#!/usr/bin/env python3
"""
Doc-drift check: CLAUDE.md + ARCHITECTURE.md 里声明的架构数字是否与代码实际一致。

Background:
历史上文档里硬编码的 "47 条安全规则"、"10 specialists"、"13 Twin 分区"
随代码演进发生过静默漂移 —— 文档在骗未来的 Claude。
ARCHITECTURE.md 首次落地时 ("9 specialists" "12 分区" "75 mobile 路由")
也立刻暴露出同样问题, 所以把文档里的数字也纳入校验。

Mechanism:
  - 脚本扫描代码得出"真实数字"
  - 从 ARCHITECTURE.md / CLAUDE.md 里 grep 出对应断言
  - 不一致 → exit 1, CI 挂掉

When adding/removing a safety rule / specialist / twin partition / API 路由 /
Celery 任务 / model / service / mobile route, you must:
  1. 让代码处于目标状态
  2. 更新 CLAUDE.md / ARCHITECTURE.md 里对应数字
  3. 本脚本会校验二者一致 —— 不要动本脚本的 EXPECTED, 除非代码数字故意变

Usage:
  python scripts/check_doc_drift.py         # from repo root
"""

from __future__ import annotations

import os
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
        "symptoms": 5,
        "cardiac": 1,
        "problem_red_lines": 1,
        "guidance_red_lines": 2,
    },
    "specialists_count": 13,
    "twin_partitions": 15,
}


def count_register_decorators(rules_dir: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in sorted(rules_dir.glob("*.py")):
        if p.name == "__init__.py":
            continue
        text = p.read_text(encoding="utf-8")
        out[p.stem] = len(re.findall(r"^@register\b", text, re.MULTILINE))
    return out


def _prime_env() -> None:
    """Backend modules assert required env vars at import time."""
    os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
    os.environ.setdefault(
        "GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU="
    )
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


def count_specialists() -> int:
    _prime_env()
    sys.path.insert(0, str(BACKEND))
    try:
        from app.orchestrator.specialists import all_specialists
        return len(all_specialists())
    finally:
        if sys.path[0] == str(BACKEND):
            sys.path.pop(0)


def count_twin_partitions() -> int:
    """HealthTwin fields minus container/meta fields."""
    _prime_env()
    sys.path.insert(0, str(BACKEND))
    try:
        from app.twin.schema import HealthTwin
        fields = set(HealthTwin.model_fields.keys())
        non_partitions = {"meta", "gene_config"}
        return len(fields - non_partitions)
    finally:
        if sys.path[0] == str(BACKEND):
            sys.path.pop(0)


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


def assert_doc_number(
    failures: list[str],
    *,
    label: str,
    expected: int,
    patterns: list[str],
    required_docs: tuple[str, ...] = ("docs/ARCHITECTURE.md",),
) -> None:
    r"""
    每个 required_docs 里:
      - 扫描全部 pattern 的所有命中 (把 {n} 换成 \d+)
      - 如果一个命中都没有 → 漂移 (doc 里没声明这个数字)
      - 只要有任何一个命中的数字 != expected → 漂移

    这样防止 "一处写对, 别处写错" 的部分漂移 (e.g. 同一份文档既说 42 又说 75 条路由).
    """
    docs = _doc_texts()
    for doc_name in required_docs:
        text = docs.get(doc_name)
        if text is None:
            failures.append(f"  {label}: {doc_name} 不存在, 无法校验")
            continue

        any_number_patterns = [p.replace("{n}", r"(\d+)") for p in patterns]
        total_hits = 0
        for np in any_number_patterns:
            for m in re.finditer(np, text):
                total_hits += 1
                claimed = int(m.group(1))
                if claimed != expected:
                    failures.append(
                        f"  {label}: {doc_name} 写着 '{m.group(0)}', "
                        f"代码实际 {expected}"
                    )
        if total_hits == 0:
            failures.append(
                f"  {label}: {doc_name} 未找到关于 '{label}' 的数字声明 "
                f"(期望模式: {patterns!r}, expected={expected})"
            )


def main() -> int:
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

    # 4. ARCHITECTURE.md 文档数字与代码一致
    actual_api_routers = count_api_include_routers()
    actual_celery_tasks = count_celery_tasks()
    actual_models = count_model_files()
    actual_services = count_service_files()
    actual_mobile_routes = count_mobile_routes()
    actual_web_pages = count_web_pages()

    # 对 safety rules / specialists / twin partitions, doc 里有常见写法也校验
    if actual_specialists > 0:
        assert_doc_number(
            failures,
            label="specialists 数量",
            expected=actual_specialists,
            patterns=[
                # 后面不能紧跟"单测|单元|test|覆盖"之类测试上下文
                r"{n}\s*个?\s*[Ss]pecialist(?!\s*(?:单测|单元|unit|test|覆盖|测试))",
                r"{n}\s*[Ss]pecialists(?!\s*(?:单测|单元|unit|test|覆盖|测试))",
            ],
            required_docs=("docs/ARCHITECTURE.md",),
        )
    if actual_partitions > 0:
        assert_doc_number(
            failures,
            label="Twin 分区数",
            expected=actual_partitions,
            patterns=[r"{n}\s*分区", r"{n}-partition"],
            required_docs=("docs/ARCHITECTURE.md",),
        )
    if total_actual > 0:
        assert_doc_number(
            failures,
            label="安全规则条数",
            expected=total_actual,
            patterns=[
                r"{n}\s*条\s*(?:安全|确定性)?\s*规则",
                r"{n}\s*safety\s*rules?",
                r"规则分类[（(]\s*{n}\s*条",  # Hook 3: 防 "规则分类(51 条)" 子标题漏检
            ],
            required_docs=("docs/ARCHITECTURE.md",),
        )

    # API 路由 / Celery / models / services / 前后端路由 (只在 ARCHITECTURE.md 里)
    assert_doc_number(
        failures,
        label="API include_router 数",
        expected=actual_api_routers,
        patterns=[r"{n}\s*(?:条)?\s*API\s*路由", r"{n}\s*API\s*路由"],
    )
    assert_doc_number(
        failures,
        label="Celery 任务数",
        expected=actual_celery_tasks,
        patterns=[r"{n}\s*Celery", r"{n}\s*个?\s*(?:Celery\s*)?任务"],
    )
    assert_doc_number(
        failures,
        label="模型文件数",
        expected=actual_models,
        patterns=[r"{n}\s*models\b"],
    )
    assert_doc_number(
        failures,
        label="service 文件数",
        expected=actual_services,
        patterns=[r"{n}\s*services\b"],
    )
    assert_doc_number(
        failures,
        label="mobile 路由数",
        expected=actual_mobile_routes,
        patterns=[r"{n}\s*RN\s*路由", r"{n}\s*mobile\s*路由", r"\(\s*{n}\s*路由\s*\)"],
    )
    # web pages 在 CLAUDE.md / ARCHITECTURE.md 里写法灵活, 放宽到存在即可
    # 如果 doc 里确实写了 "X 路由" / "X 页面" 就要对齐
    # (避免误报: 若 doc 里 web 数字没提, 不算 fail)

    # 5. System-map 代码派生事实 (docs/_generated/system-map.json) 与代码一致。
    #    System-map 防漂移核心: 计数/roster 只准从代码生成进无人手改的 JSON, committed 与
    #    代码不符即红 (跑 scripts/dump_system_map.py 重新生成即修)。见 docs/system-map/INDEX.md。
    try:
        import json
        sys.path.insert(0, str(ROOT / "scripts"))
        from dump_system_map import OUT as SYSMAP_OUT
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
        print("❌ CLAUDE.md / ARCHITECTURE.md 与代码已漂移：", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        print(
            "\n修复：\n"
            "  1) 确认代码是目标状态\n"
            "  2) 同步更新 CLAUDE.md / docs/ARCHITECTURE.md 里对应数字\n"
            "  3) 不一致数字列在上面, 一条一条修",
            file=sys.stderr,
        )
        return 1

    print("✅ CLAUDE.md + ARCHITECTURE.md 数字与代码一致")
    print(f"   safety rules: {total_actual} total {actual_rules}")
    print(f"   specialists:  {actual_specialists}")
    print(f"   twin partitions: {actual_partitions}")
    print(f"   API routers: {actual_api_routers}")
    print(f"   celery tasks: {actual_celery_tasks}")
    print(f"   model files: {actual_models}")
    print(f"   service files: {actual_services}")
    print(f"   mobile routes: {actual_mobile_routes}")
    print(f"   web pages: {actual_web_pages}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
