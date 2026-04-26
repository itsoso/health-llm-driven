#!/usr/bin/env python3
"""
Doc-drift check: CLAUDE.md 里声明的架构数字是否与代码实际一致。

Background:
历史上 CLAUDE.md 里硬编码的 "47 条安全规则"、"10 specialists"、"13 Twin 分区"
随代码演进发生过静默漂移 —— 文档在骗未来的 Claude。

Mechanism:
  - 本脚本的 EXPECTED 常量 = "承诺的真实"
  - 脚本扫描代码得出 "当前的真实"
  - 不一致 → exit 1，CI 挂掉

When adding/removing a safety rule / specialist / twin partition you must update:
  1. This script's EXPECTED
  2. CLAUDE.md's matching number
Together. CI won't let them drift apart.

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

EXPECTED: dict = {
    "safety_rules": {
        "vitals": 12,
        "labs": 7,
        "ddi": 7,
        "dsi": 7,
        "pgx": 9,
        "training_load": 3,
        "cgm": 6,
    },
    "specialists_count": 10,
    "twin_partitions": 13,
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

    # 2. Specialists count
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

    if failures:
        print("❌ CLAUDE.md 与代码已漂移：", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        print(
            "\n修复：先确认代码是目标状态，然后同步更新 scripts/check_doc_drift.py "
            "的 EXPECTED 与 CLAUDE.md 里对应数字。",
            file=sys.stderr,
        )
        return 1

    print("✅ CLAUDE.md 数字与代码一致")
    print(f"   safety rules: {total_actual} total {actual_rules}")
    print(f"   specialists:  {actual_specialists}")
    print(f"   twin partitions: {actual_partitions}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
