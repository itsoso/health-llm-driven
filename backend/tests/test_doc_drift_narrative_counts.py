from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_doc_drift as cdd  # noqa: E402
import dump_system_map as dsm  # noqa: E402


def test_find_manual_architecture_counts_flags_code_derived_claims() -> None:
    text = """
│  13 Specialists
│  Digital Health Twin (15 分区)
132 条, 主要分 10 域:
68 页, 主要分域:
## 九、Celery 调度(69 个任务)
├── (tabs)/  — 3 tab
└── modal / stack pages — 40+
| `AGENTS.md` | AI Agent 开发规范, 992 行 |
model_registry.py — 9 个模型 entry
3 个 AppIntent: HealthCommandIntent / HealthAnalysisIntent
test_specialists.py — 5 个 specialist 单测
165 API 路由
72 Celery 任务
410 services
116 models
127 mobile 路由
72 web 页
"""

    claims = cdd.find_manual_architecture_counts(text)

    assert claims == [
        "13 Specialists",
        "15 分区",
        "132 条, 主要分 10 域",
        "68 页, 主要分域",
        "Celery 调度(69 个任务)",
        "3 tab",
        "stack pages — 40+",
        "AGENTS.md` | AI Agent 开发规范, 992 行",
        "9 个模型 entry",
        "3 个 AppIntent",
        "5 个 specialist 单测",
        "165 API 路由",
        "72 Celery 任务",
        "410 services",
        "116 models",
        "127 mobile 路由",
        "72 web 页",
    ]


def test_find_manual_architecture_counts_ignores_runtime_constants() -> None:
    text = """
Redis 5min cache
ThreadPool 12s timeout
最后写 1 条 NotificationLog
SECRET_KEY=<32+ chars>
"""

    assert cdd.find_manual_architecture_counts(text) == []


def test_find_manual_architecture_counts_ignores_historical_evolution_log() -> None:
    text = """
### 16.3 演进 log
| 2026-05-08 | 首次落地 13 Specialists / 15 分区 |
"""

    assert cdd.find_manual_architecture_counts(text) == []


def test_architecture_document_has_no_manual_code_derived_counts() -> None:
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    assert cdd.find_manual_architecture_counts(text) == []


def test_main_reuses_provided_fresh_map_without_building(monkeypatch) -> None:
    fresh_map = json.loads(dsm.OUT.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        dsm,
        "build_map",
        lambda: pytest.fail("provided fresh_map must skip build_map"),
    )

    assert cdd.main(fresh_map=fresh_map) == 0


def test_standalone_main_builds_map_once(monkeypatch) -> None:
    fresh_map = json.loads(dsm.OUT.read_text(encoding="utf-8"))
    calls = 0

    def build_map() -> dict:
        nonlocal calls
        calls += 1
        return fresh_map

    monkeypatch.setattr(dsm, "build_map", build_map)

    assert cdd.main() == 0
    assert calls == 1


@pytest.mark.parametrize("caller_has_scripts_path", (False, True))
def test_main_preserves_caller_sys_path_across_repeated_checks(
    caller_has_scripts_path: bool,
) -> None:
    fresh_map = json.loads(dsm.OUT.read_text(encoding="utf-8"))
    scripts_path = str(ROOT / "scripts")
    original_sys_path = sys.path.copy()
    sys.path[:] = [entry for entry in sys.path if entry != scripts_path]
    if caller_has_scripts_path:
        sys.path.insert(1, scripts_path)
    caller_sys_path = sys.path.copy()
    try:
        assert cdd.main(fresh_map=fresh_map) == 0
        assert cdd.main(fresh_map=fresh_map) == 0
        assert sys.path == caller_sys_path
    finally:
        sys.path[:] = original_sys_path


def test_main_prefers_repo_scripts_over_shadow_dump_module(tmp_path) -> None:
    fresh_map = json.loads(dsm.OUT.read_text(encoding="utf-8"))
    scripts_path = str(ROOT / "scripts")
    shadow_dir = tmp_path / "shadow"
    shadow_dir.mkdir()
    (shadow_dir / "dump_system_map.py").write_text(
        "raise RuntimeError('shadow dump module imported')\n",
        encoding="utf-8",
    )
    original_sys_path = sys.path.copy()
    original_dump_module = sys.modules.pop("dump_system_map", None)
    sys.path[:] = [
        str(shadow_dir),
        scripts_path,
        *(entry for entry in sys.path if entry != scripts_path),
    ]
    caller_sys_path = sys.path.copy()
    try:
        assert cdd.main(fresh_map=fresh_map) == 0
        assert sys.path == caller_sys_path
    finally:
        sys.path[:] = original_sys_path
        sys.modules.pop("dump_system_map", None)
        if original_dump_module is not None:
            sys.modules["dump_system_map"] = original_dump_module
