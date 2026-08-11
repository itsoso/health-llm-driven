from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_doc_drift as cdd  # noqa: E402


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
