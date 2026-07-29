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

    # 4. Architecture counts are code-derived only. Narrative docs link to
    # docs/_generated/system-map.json instead of duplicating mutable numbers.
    # The generated-map comparison below is the single documentation drift gate.

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
