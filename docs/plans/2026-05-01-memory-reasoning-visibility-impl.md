# 记忆与推理可见化 — v1 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Safety 告警 / Specialist finding / ActionCard 命中率 + Clinical Journal case timeline 在 Mobile 上可见，看板补 Celery Health 区块。**不调 LLM**，**不新建表**，**读模型 + 小幅 schema 扩充**。

**Architecture:** 复用已有 `/reasoning-trace` 路由 + 已有 `/clinical-journal` + 已有 `/specialists`，按 design.md 的契约**扩**这三个路由；后台 `agent_audit_logs.result_detail` 用来把个别 alert/finding 的 snapshot 存下来，让 Mobile 单击一条 Safety 告警时能反查。Mobile 端新增 `ExplainSheet`（底部抽屉）、重构 `journal/index.tsx` 成 case-thread 分组 timeline、加 `mobile/app/specialist/[name].tsx` 详情页。Admin 看板 Observability Tab 追加一个 `CeleryHealthBlock`。

**Tech Stack:** FastAPI / SQLAlchemy / Pydantic / pytest · Expo Router / React Query / Reanimated · Next.js 14 Admin

> 📖 设计文档: `docs/plans/2026-05-01-memory-reasoning-visibility-design.md`（范围、边界、成功判据、止损条件）

---

## 现状与设计的重要 delta

Design 假设全部 API 要新建。实际探查后：
- ✅ `/api/v1/reasoning-trace/recent` + `/reasoning-trace/{trace_id}` 已存在（handled AnomalyAlert + llm_arbitration），下方 v1 **扩**它而非替换。
- ✅ `mobile/services/reasoningTrace.ts` + `mobile/app/trace/` 已有列表路由，Mobile 一侧扩 ExplainSheet 复用该 service。
- ✅ `/api/v1/clinical-journal` 已 mount, 但只有单条 `GET /entries/{id}`, 无 timeline 视图 —— 新增 `GET /timeline`.
- ✅ `/api/v1/specialists/hit-rate` 已有, 但无 per-specialist detail —— 新增 `GET /{name}/scorecard`.
- ⚠️  `agent_audit_logs.result_detail` 今天不带 alerts / findings, 无法按 `ref_id` 反查单条。**Day 1 必做的 schema 小扩**。

对 design.md §3 API 契约的微调：
- `/reasoning/explain` → 并入现有 `/reasoning-trace/safety/{audit_id}` 与 `/reasoning-trace/specialist/{finding_id}` 两条 path（一致的 router 前缀，降低迁移成本）。
- `GET /journal/timeline` → 实际路径 `/api/v1/clinical-journal/timeline`。
- `GET /specialists/{name}/scorecard` → 路径不变，挂到现有 router。

---

## 任务清单概览 (10 天)

- Day 1: Audit groundwork (必须先做, 否则 Safety lookup 没法反查)
- Day 2: Reasoning Explainer + Safety / Specialist /explain endpoints
- Day 3: Mobile ExplainSheet 组件 + 主屏集成 2 处
- Day 4: `/clinical-journal/timeline` API + 测试
- Day 5: Mobile Journal tab 重构为 case-thread 分组 timeline
- Day 6: `/specialists/{name}/scorecard` API + 测试
- Day 7: Mobile `specialist/[name].tsx` 详情页 + Hero chip 入口
- Day 8: Admin Celery Health block + Mobile TrustHintChip
- Day 9: interaction_feedback 埋点 + 观察期看板 3 条新 suggestion
- Day 10: 真机冒烟 + EAS preview → production + doc drift

---

## Day 1 — Audit Groundwork

**目标**: 让 `agent_audit_logs.result_detail` 携带 alerts/findings 的 snapshot，这样一条 Safety 评估或一次 Orchestrator 调度可以**按 audit_id 反查到单条 alert/finding**.

**为什么 Day 1 就做**: 下游 explainer / mobile 抽屉都依赖这个结构. 不先铺好, Day 2-3 就没数据可 trace.

### Task 1.1 — `log_safety_evaluation` 携带 alerts

**Files:**
- Modify: `backend/app/agents/audit.py` (函数 `log_safety_evaluation`)
- Modify: `backend/app/api/safety.py:75-100` (调用点)

**Step 1: 在 `tests/test_safety_audit_detail.py` 写失败测试**

```python
# backend/tests/test_safety_audit_detail.py
"""Audit detail 回传 alerts 列表, 支持单 alert 反查."""
from datetime import datetime, timezone
from app.agents.audit import log_safety_evaluation
from app.models.agent_audit_log import AgentAuditLog


def test_log_safety_evaluation_persists_alerts_snapshot(db):
    alerts_snapshot = [
        {"rule_id": "acute_hrv_drop", "category": "vitals",
         "severity": 3, "title": "HRV 急剧下降",
         "message": "...", "data_citation": {"hrv": 28}},
        {"rule_id": "ddi_warfarin_nsaid", "category": "ddi",
         "severity": 4, "title": "出血风险",
         "message": "...", "data_citation": {}},
    ]

    log_safety_evaluation(
        db=db,
        user_id=1,
        alerts_count=2,
        result_summary="1crit/1med",
        twin_build_ms=12,
        evaluate_ms=8,
        twin_sources=["garmin"],
        result_detail={"alerts": alerts_snapshot},
    )

    row = db.query(AgentAuditLog).filter(
        AgentAuditLog.agent_type == "safety_guardian"
    ).first()
    assert row is not None
    assert row.result_detail is not None
    assert len(row.result_detail["alerts"]) == 2
    assert row.result_detail["alerts"][0]["rule_id"] == "acute_hrv_drop"
```

**Step 2: 运行测试确认失败**

```bash
cd backend && source venv/bin/activate && \
SECRET_KEY='test-secret-key-32-chars-minimum!!' \
GARMIN_ENCRYPTION_KEY='mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=' \
pytest tests/test_safety_audit_detail.py -q --no-cov -x
```

期望: FAIL — 当前 `log_safety_evaluation` 的 `result_detail` 不被调用点填充（safety.py 调用处没传 alerts）。

**Step 3: 改 `app/api/safety.py` 传 alerts 到 `result_detail`**

`safety.py` 中 `log_safety_evaluation(...)` 的调用处增加：

```python
# 审计 detail: 把本次 alerts 的 snapshot 存下, 让 /reasoning-trace/safety/{audit_id} 可反查
alerts_snapshot = [
    {
        "rule_id": a.rule_id,
        "category": a.category,
        "severity": int(a.severity),
        "title": a.title,
        "message": a.message,
        "action": a.action,
        "data_citation": a.data_citation,
        "generated_at": a.generated_at.isoformat(),
    }
    for a in report.alerts
]

log_safety_evaluation(
    db=db,
    user_id=current_user.id,
    alerts_count=len(report.alerts),
    result_summary=f"{report.critical_count}crit/{report.high_count}high/{report.medium_count}med",
    twin_build_ms=report.twin_build_ms,
    evaluate_ms=report.evaluate_ms,
    twin_sources=twin.meta.data_sources,
    result_detail={"alerts": alerts_snapshot},
)
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/test_safety_audit_detail.py -q --no-cov -x
```

期望: 1 passed.

**Step 5: 回归全 safety + audit 相关测试**

```bash
pytest tests/test_safety_guardian.py tests/test_safety_audit_detail.py tests/test_agent_audit_log.py -q --no-cov -x 2>&1 | tail -5
```

期望: all green.

**Step 6: commit**

```bash
git add backend/app/agents/audit.py backend/app/api/safety.py backend/tests/test_safety_audit_detail.py
git commit -m "feat(audit): safety_guardian audit 带 alerts snapshot, 支持 /reasoning-trace 反查

审计日志 result_detail 存入本次所有 alerts 的结构化快照 (rule_id/category/severity/
data_citation/...), 让后续 /reasoning-trace/safety/{audit_id} 可按 rule_id 反查单条."
```

---

### Task 1.2 — 新增 `log_specialist_findings` audit entry

**Files:**
- Modify: `backend/app/agents/audit.py`
- Modify: `backend/app/orchestrator/orchestrator.py` (在 `_run_specialists` 后调用)
- Test: `backend/tests/test_specialist_audit.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_specialist_audit.py
from app.agents.audit import log_specialist_findings
from app.models.agent_audit_log import AgentAuditLog


def test_log_specialist_findings_persists_snapshot(db):
    findings_snapshot = [
        {"specialist": "recovery_coach", "kind": "readiness",
         "summary": "readiness=54 偏低", "data": {"readiness": 54},
         "proposed_cards": []},
        {"specialist": "fuel_strategist", "kind": "nutrition_gap",
         "summary": "蛋白缺口", "data": {"deficit_g": 20},
         "proposed_cards": []},
    ]

    log_specialist_findings(
        db=db,
        user_id=1,
        findings=findings_snapshot,
        orchestrator_run_id=None,
    )

    row = db.query(AgentAuditLog).filter(
        AgentAuditLog.agent_type == "specialist_batch"
    ).first()
    assert row is not None
    assert len(row.result_detail["findings"]) == 2
    assert row.findings_count == 2
```

**Step 2: 运行确认失败** — 函数不存在。

**Step 3: 实现 `log_specialist_findings`**

在 `app/agents/audit.py` 追加：

```python
def log_specialist_findings(
    db: Session,
    user_id: int,
    findings: List[Dict[str, Any]],
    orchestrator_run_id: Optional[int] = None,
) -> Optional[int]:
    """记录一批 specialist 产出的 findings, 支持 /reasoning-trace/specialist/{audit_id} 反查.

    Returns: 新写入的 audit_log.id, 方便调用方回写关联.
    """
    try:
        from app.models.agent_audit_log import AgentAuditLog
        from sqlalchemy.sql import func

        row = AgentAuditLog(
            user_id=user_id,
            agent_type="specialist_batch",
            action="run",
            result_summary=f"产出 {len(findings)} 条 findings",
            findings_count=len(findings),
            result_detail={
                "findings": findings,
                "orchestrator_run_id": orchestrator_run_id,
            },
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[audit] log_specialist_findings 失败 (跳过): {e}")
        return None
```

**Step 4: 在 orchestrator 调用**

`app/orchestrator/orchestrator.py` 的 `run_orchestrator` 在 `_run_specialists` 返回之后，加一个旁路 audit：

```python
# 旁路审计: 支持 /reasoning-trace/specialist/{audit_id} 反查单 finding
try:
    from app.agents.audit import log_specialist_findings
    findings_snapshot = [
        {
            "specialist": f.specialist,
            "kind": f.kind,
            "summary": f.summary,
            "data": f.data,
            "proposed_cards": [c.model_dump() for c in (f.proposed_cards or [])],
        }
        for f in findings
    ]
    log_specialist_findings(db, user_id=user_id, findings=findings_snapshot)
except Exception:
    pass
```

**Step 5: 运行测试**

```bash
pytest tests/test_specialist_audit.py tests/test_orchestrator.py -q --no-cov -x 2>&1 | tail
```

期望: all green, specialist_audit 的新 case 通过, orchestrator 原有测试不 regression.

**Step 6: commit**

```bash
git add backend/app/agents/audit.py backend/app/orchestrator/orchestrator.py backend/tests/test_specialist_audit.py
git commit -m "feat(audit): log_specialist_findings, orchestrator 旁路审计每次 specialist 产出"
```

---

## Day 2 — Reasoning Explainer + Safety/Specialist Lookup Endpoints

**目标**: 扩 `/reasoning-trace` 路由, 新增 `/safety/{audit_id}` 和 `/specialist/{audit_id}` 两条 path，让 Mobile 点一条 Safety 卡 / Specialist 卡能把对应 rule/finding 的详情拿出来。

### Task 2.1 — `reasoning_explainer.py` service

**Files:**
- Create: `backend/app/services/reasoning_explainer.py`
- Test: `backend/tests/test_reasoning_explainer.py`

**Step 1: 写失败测试 (全部)**

```python
# backend/tests/test_reasoning_explainer.py
from datetime import datetime, timezone
from app.models.agent_audit_log import AgentAuditLog
from app.services.reasoning_explainer import (
    explain_safety_alert,
    explain_specialist_finding,
)


def _seed_safety_audit(db, user_id=1, rule_id="acute_hrv_drop"):
    row = AgentAuditLog(
        user_id=user_id, agent_type="safety_guardian", action="evaluate",
        alerts_count=1, result_summary="1med",
        result_detail={"alerts": [{
            "rule_id": rule_id, "category": "vitals", "severity": 2,
            "title": "HRV 急剧下降", "message": "HRV=28",
            "data_citation": {"hrv": 28, "baseline": 50},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }]},
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_explain_safety_alert_returns_rule_and_evidence(db):
    audit = _seed_safety_audit(db)
    result = explain_safety_alert(db, audit_id=audit.id, rule_id="acute_hrv_drop", user_id=1)

    assert result["source"] == "safety"
    assert result["rule"]["name"] == "acute_hrv_drop"
    assert result["rule"]["category"] == "vitals"
    assert isinstance(result["twin_evidence"], list)
    assert isinstance(result["related_facts"], list)
    assert "confidence_note" in result


def test_explain_safety_alert_cross_user_forbidden(db):
    audit = _seed_safety_audit(db, user_id=1)
    # user 2 尝试拿 user 1 的 audit
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        explain_safety_alert(db, audit_id=audit.id, rule_id="acute_hrv_drop", user_id=2)
    assert exc.value.status_code == 403


def test_explain_safety_alert_rule_not_found(db):
    audit = _seed_safety_audit(db)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        explain_safety_alert(db, audit_id=audit.id, rule_id="nonexistent_rule", user_id=1)
    assert exc.value.status_code == 404


def test_explain_safety_alert_memory_fact_timeout_no_throw(db, monkeypatch):
    audit = _seed_safety_audit(db)

    def _boom(*a, **kw):
        raise TimeoutError("bm25 too slow")

    monkeypatch.setattr(
        "app.services.reasoning_explainer.hybrid_retrieve", _boom
    )
    # 不应抛, related_facts 应返回 []
    result = explain_safety_alert(db, audit_id=audit.id, rule_id="acute_hrv_drop", user_id=1)
    assert result["related_facts"] == []


def test_explain_specialist_finding_basic(db):
    from datetime import datetime, timezone
    audit = AgentAuditLog(
        user_id=1, agent_type="specialist_batch", action="run",
        findings_count=1, result_summary="1 finding",
        result_detail={"findings": [{
            "specialist": "recovery_coach", "kind": "readiness",
            "summary": "readiness=54",
            "data": {"readiness": 54, "hrv": 28}, "proposed_cards": [],
        }]},
    )
    db.add(audit); db.commit(); db.refresh(audit)

    result = explain_specialist_finding(
        db, audit_id=audit.id, specialist="recovery_coach", user_id=1
    )
    assert result["source"] == "specialist"
    assert result["specialist"] == "recovery_coach"
    assert result["summary"].startswith("readiness")
    assert "twin_evidence" in result


def test_explain_safety_alert_unknown_audit_id_404(db):
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        explain_safety_alert(db, audit_id=99999, rule_id="x", user_id=1)
    assert exc.value.status_code == 404
```

**Step 2: 运行确认失败**

```bash
pytest tests/test_reasoning_explainer.py -q --no-cov -x 2>&1 | tail
```

期望: FAIL — service 还未实现。

**Step 3: 实现 `reasoning_explainer.py`**

```python
# backend/app/services/reasoning_explainer.py
"""Reasoning Explainer — 把 safety alert / specialist finding 的'为什么'拼出来.

只读 DB, 不调 LLM. API 层直接 JSON 返回.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.agent_audit_log import AgentAuditLog

logger = logging.getLogger(__name__)

_CATEGORY_TO_PARTITION = {
    "vitals": "physiological",
    "labs": "labs",
    "ddi": "meds",
    "dsi": "supplement",
    "pgx": "genetic",
    "training_load": "behavioral",
    "cgm": "cgm",
}


def _load_audit(db: Session, audit_id: int, expected_agent: str, user_id: int) -> AgentAuditLog:
    row = db.query(AgentAuditLog).filter(AgentAuditLog.id == audit_id).first()
    if row is None or row.agent_type != expected_agent:
        raise HTTPException(status_code=404, detail="audit 记录不存在或已过期")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该 audit 记录")
    return row


def _twin_evidence_for_category(db: Session, user_id: int, category: str) -> List[Dict[str, Any]]:
    """从 Twin 当前快照抽 category 对应分区的几条关键字段."""
    try:
        from app.twin.builder import build_twin
        twin = build_twin(db, user_id, use_cache=True)
        partition_name = _CATEGORY_TO_PARTITION.get(category, "physiological")
        partition = getattr(twin, partition_name, None)
        if partition is None:
            return []
        # 取 partition.model_dump() 中前 4 个非 None 字段
        raw = partition.model_dump(exclude_none=True) if hasattr(partition, "model_dump") else {}
        out = []
        for k, v in list(raw.items())[:4]:
            if isinstance(v, (int, float, str, bool)):
                out.append({
                    "partition": partition_name,
                    "field": k, "value": v,
                    "source": ",".join(twin.meta.data_sources or []) or "unknown",
                    "freshness_hours": None,
                })
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[explainer] twin evidence 失败: {e}")
        return []


def _related_facts(db: Session, user_id: int, query: str, k: int = 3) -> List[Dict[str, Any]]:
    try:
        from app.services.hybrid_search import hybrid_retrieve
        hits = hybrid_retrieve(db, user_id, query, top_k=k)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[explainer] hybrid_retrieve 失败, related_facts=[]: {e}")
        return []
    out = []
    for h in hits:
        if h.source_type != "fact":
            continue
        out.append({
            "id": h.source_id,
            "tier": h.metadata.get("tier", "unknown"),
            "predicate": h.metadata.get("predicate", ""),
            "preview": h.text_preview,
            "confidence": h.metadata.get("confidence"),
        })
    return out


def explain_safety_alert(
    db: Session, audit_id: int, rule_id: str, user_id: int,
) -> Dict[str, Any]:
    audit = _load_audit(db, audit_id, expected_agent="safety_guardian", user_id=user_id)
    alerts = (audit.result_detail or {}).get("alerts") or []
    alert = next((a for a in alerts if a.get("rule_id") == rule_id), None)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"未找到 rule_id={rule_id} 的 alert")

    category = alert.get("category") or "vitals"
    twin_evidence = _twin_evidence_for_category(db, user_id, category)
    query_text = f"{rule_id} {category} {alert.get('title', '')}"
    related = _related_facts(db, user_id, query_text)

    return {
        "source": "safety",
        "summary": alert.get("title") or rule_id,
        "rule": {
            "name": rule_id,
            "category": category,
            "severity": alert.get("severity"),
            "threshold": alert.get("message"),
        },
        "twin_evidence": twin_evidence,
        "related_facts": related,
        "confidence_note": _confidence_note(twin_evidence, related),
        "generated_at": alert.get("generated_at"),
    }


def explain_specialist_finding(
    db: Session, audit_id: int, specialist: str, user_id: int,
) -> Dict[str, Any]:
    audit = _load_audit(db, audit_id, expected_agent="specialist_batch", user_id=user_id)
    findings = (audit.result_detail or {}).get("findings") or []
    finding = next((f for f in findings if f.get("specialist") == specialist), None)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"未找到 specialist={specialist} 的 finding")

    twin_evidence = _twin_evidence_for_category(db, user_id, category="vitals")
    related = _related_facts(db, user_id, f"{specialist} {finding.get('kind', '')}")

    return {
        "source": "specialist",
        "specialist": specialist,
        "summary": finding.get("summary") or "",
        "kind": finding.get("kind"),
        "data": finding.get("data") or {},
        "twin_evidence": twin_evidence,
        "related_facts": related,
        "confidence_note": _confidence_note(twin_evidence, related),
        "proposed_cards_count": len(finding.get("proposed_cards") or []),
    }


def _confidence_note(twin_evidence: List[Dict], related: List[Dict]) -> str:
    tc = len(twin_evidence)
    rc = len(related)
    if tc == 0 and rc == 0:
        return "数据不足"
    return f"基于 {tc} 条 Twin 字段 + {rc} 条记忆事实"
```

**Step 4: 运行测试**

```bash
pytest tests/test_reasoning_explainer.py -q --no-cov -x 2>&1 | tail -15
```

期望: 6 passed.

**Step 5: commit**

```bash
git add backend/app/services/reasoning_explainer.py backend/tests/test_reasoning_explainer.py
git commit -m "feat(reasoning): explainer service — safety/specialist why 拼 trace (不调 LLM)"
```

---

### Task 2.2 — HTTP endpoints `/reasoning-trace/safety/{audit_id}` + `/specialist/{audit_id}`

**Files:**
- Modify: `backend/app/api/reasoning_trace.py` (在已有 router 追加 endpoints)
- Test: `backend/tests/test_reasoning_explain_api.py`

**Step 1: 写失败 API 测试**

```python
# backend/tests/test_reasoning_explain_api.py
from datetime import datetime, timezone
from app.models.agent_audit_log import AgentAuditLog


def _seed_safety(db, user_id=1):
    row = AgentAuditLog(
        user_id=user_id, agent_type="safety_guardian", action="evaluate",
        alerts_count=1, result_summary="1med",
        result_detail={"alerts": [{
            "rule_id": "acute_hrv_drop", "category": "vitals", "severity": 2,
            "title": "HRV 急剧下降", "message": "HRV=28",
            "data_citation": {"hrv": 28},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }]},
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_safety_explain_endpoint_200(client, db, auth_headers_user_1):
    audit = _seed_safety(db, user_id=1)
    r = client.get(
        f"/api/v1/reasoning-trace/safety/{audit.id}?rule_id=acute_hrv_drop",
        headers=auth_headers_user_1,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "safety"
    assert body["rule"]["name"] == "acute_hrv_drop"


def test_safety_explain_cross_user_403(client, db, auth_headers_user_2):
    audit = _seed_safety(db, user_id=1)
    r = client.get(
        f"/api/v1/reasoning-trace/safety/{audit.id}?rule_id=acute_hrv_drop",
        headers=auth_headers_user_2,
    )
    assert r.status_code == 403


def test_safety_explain_not_found_404(client, auth_headers_user_1):
    r = client.get(
        "/api/v1/reasoning-trace/safety/99999?rule_id=x",
        headers=auth_headers_user_1,
    )
    assert r.status_code == 404
```

如果现有 `conftest.py` 没有 `auth_headers_user_1`/`user_2` fixture, 检查 `tests/conftest_enhanced.py` 或其他 test 文件里的样板（如 `tests/test_safety_guardian.py` 的 auth helper），按 DRY 复用。若无现成, 在 `tests/conftest.py` 加:

```python
@pytest.fixture
def auth_headers_user_1(db):
    from tests.conftest import create_authenticated_user  # 已存在的 helper
    _, token = create_authenticated_user(db)  # user_id=1 默认
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_2(db):
    from tests.conftest import create_authenticated_user
    _, token = create_authenticated_user(db)
    return {"Authorization": f"Bearer {token}"}
```

**Step 2: 运行确认失败**

```bash
pytest tests/test_reasoning_explain_api.py -q --no-cov -x 2>&1 | tail
```

期望: 404 — endpoint 尚未注册。

**Step 3: 在 `reasoning_trace.py` 追加 endpoints**

```python
# backend/app/api/reasoning_trace.py (追加)
from app.services.reasoning_explainer import (
    explain_safety_alert, explain_specialist_finding,
)


@router.get("/safety/{audit_id}", summary="Safety 告警推理链 (按 rule_id 反查)")
def explain_safety(
    audit_id: int,
    rule_id: str = Query(..., description="alert 的 rule_id"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return explain_safety_alert(db, audit_id=audit_id, rule_id=rule_id, user_id=current_user.id)


@router.get("/specialist/{audit_id}", summary="Specialist finding 推理链")
def explain_specialist(
    audit_id: int,
    specialist: str = Query(..., description="specialist 名字, 如 recovery_coach"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return explain_specialist_finding(db, audit_id=audit_id, specialist=specialist, user_id=current_user.id)
```

如果文件顶部没有 `User`, `get_current_user_required`, `Query` 的 import, 追加。

**Step 4: 运行测试**

```bash
pytest tests/test_reasoning_explain_api.py -q --no-cov -x 2>&1 | tail -10
```

期望: 3 passed.

**Step 5: 回归**

```bash
pytest tests/ -q --no-cov -x -k "reasoning" 2>&1 | tail
```

**Step 6: commit**

```bash
git add backend/app/api/reasoning_trace.py backend/tests/test_reasoning_explain_api.py backend/tests/conftest.py
git commit -m "feat(reasoning-trace): /safety/{id} + /specialist/{id} 返回推理链, Mobile 抽屉可接"
```

---

## Day 3 — Mobile ExplainSheet 组件 + 主屏集成

**目标**: 用户点 Safety 卡 / Specialist 卡 时弹底部抽屉显示推理链. 不写单测, 真机冒烟.

### Task 3.1 — 扩 `mobile/services/reasoningTrace.ts`

**Files:**
- Modify: `mobile/services/reasoningTrace.ts`

**Step 1: 在 service 文件加两个请求函数**

```ts
// mobile/services/reasoningTrace.ts (末尾追加)

export interface ExplainResponse {
  source: 'safety' | 'specialist';
  summary: string;
  rule?: { name: string; category: string; severity?: number; threshold?: string };
  specialist?: string;
  kind?: string;
  data?: Record<string, unknown>;
  twin_evidence: Array<{
    partition: string; field: string; value: string | number | boolean;
    source: string; freshness_hours: number | null;
  }>;
  related_facts: Array<{
    id: number; tier: string; predicate: string;
    preview: string; confidence: number | null;
  }>;
  confidence_note: string;
}

export async function explainSafety(auditId: number, ruleId: string): Promise<ExplainResponse> {
  const res = await api.get(`/reasoning-trace/safety/${auditId}`, {
    params: { rule_id: ruleId },
  });
  return res.data;
}

export async function explainSpecialist(auditId: number, specialist: string): Promise<ExplainResponse> {
  const res = await api.get(`/reasoning-trace/specialist/${auditId}`, {
    params: { specialist },
  });
  return res.data;
}
```

**Step 2: commit**

```bash
git add mobile/services/reasoningTrace.ts
git commit -m "feat(mobile/reasoning): explainSafety/explainSpecialist service fns"
```

---

### Task 3.2 — `useReasoningExplain` hook

**Files:**
- Create: `mobile/hooks/useReasoningExplain.ts`

**Step 1: 写 hook**

```ts
// mobile/hooks/useReasoningExplain.ts
import { useQuery } from '@tanstack/react-query';
import { explainSafety, explainSpecialist, ExplainResponse } from '../services/reasoningTrace';

type Args =
  | { source: 'safety'; auditId: number; ruleId: string; enabled?: boolean }
  | { source: 'specialist'; auditId: number; specialist: string; enabled?: boolean };

export function useReasoningExplain(args: Args) {
  return useQuery<ExplainResponse>({
    queryKey: ['reasoning-explain', args.source, args.auditId,
      args.source === 'safety' ? args.ruleId : args.specialist],
    queryFn: () =>
      args.source === 'safety'
        ? explainSafety(args.auditId, args.ruleId)
        : explainSpecialist(args.auditId, args.specialist),
    enabled: args.enabled !== false,
    staleTime: 5 * 60 * 1000,
  });
}
```

**Step 2: commit**

```bash
git add mobile/hooks/useReasoningExplain.ts
git commit -m "feat(mobile/hooks): useReasoningExplain"
```

---

### Task 3.3 — `ExplainSheet` 组件

**Files:**
- Create: `mobile/components/reasoning/ExplainSheet.tsx`
- Create: `mobile/components/reasoning/ExplainButton.tsx`

**Step 1: `ExplainSheet.tsx`** (底部抽屉)

```tsx
// mobile/components/reasoning/ExplainSheet.tsx
import React from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View, ActivityIndicator } from 'react-native';
import { useReasoningExplain } from '../../hooks/useReasoningExplain';
import type { ExplainResponse } from '../../services/reasoningTrace';

type Props =
  | { visible: boolean; onClose: () => void; source: 'safety'; auditId: number; ruleId: string }
  | { visible: boolean; onClose: () => void; source: 'specialist'; auditId: number; specialist: string };

export function ExplainSheet(props: Props) {
  const q = useReasoningExplain(
    props.source === 'safety'
      ? { source: 'safety', auditId: props.auditId, ruleId: props.ruleId, enabled: props.visible }
      : { source: 'specialist', auditId: props.auditId, specialist: props.specialist, enabled: props.visible }
  );

  return (
    <Modal visible={props.visible} transparent animationType="slide" onRequestClose={props.onClose}>
      <Pressable style={styles.backdrop} onPress={props.onClose}>
        <Pressable style={styles.sheet}>
          <View style={styles.handle} />
          <Text style={styles.title}>为什么?</Text>
          {q.isLoading && <ActivityIndicator />}
          {q.isError && <Text style={styles.err}>加载失败: {(q.error as Error)?.message}</Text>}
          {q.data && <Body data={q.data} />}
          <Pressable onPress={props.onClose} style={styles.close}>
            <Text style={styles.closeText}>关闭</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function Body({ data }: { data: ExplainResponse }) {
  return (
    <ScrollView style={{ maxHeight: 500 }}>
      <Text style={styles.summary}>{data.summary}</Text>

      {data.rule && (
        <Section title="规则">
          <Text style={styles.kv}>{data.rule.name} · {data.rule.category}</Text>
          {data.rule.threshold && <Text style={styles.hint}>{data.rule.threshold}</Text>}
        </Section>
      )}

      <Section title={`Twin 证据 (${data.twin_evidence.length})`}>
        {data.twin_evidence.length === 0 ? (
          <Text style={styles.hint}>数据不足</Text>
        ) : data.twin_evidence.map((e, i) => (
          <Text key={i} style={styles.kv}>
            {e.partition}.{e.field} = {String(e.value)}  <Text style={styles.hint}>({e.source})</Text>
          </Text>
        ))}
      </Section>

      <Section title={`记忆关联 (${data.related_facts.length})`}>
        {data.related_facts.length === 0 ? (
          <Text style={styles.hint}>基于确定性规则, 无记忆关联</Text>
        ) : data.related_facts.map((f) => (
          <Text key={f.id} style={styles.kv}>• {f.preview}  <Text style={styles.hint}>[{f.tier}]</Text></Text>
        ))}
      </Section>

      <Text style={styles.footer}>{data.confidence_note}</Text>
    </ScrollView>
  );
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <View style={{ marginTop: 16 }}>
    <Text style={styles.sectionTitle}>{title}</Text>
    {children}
  </View>
);

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 20, paddingBottom: 32 },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: '#D1D5DB', marginBottom: 12 },
  title: { fontSize: 20, fontWeight: '600', marginBottom: 8 },
  summary: { fontSize: 16, color: '#111827' },
  sectionTitle: { fontSize: 13, fontWeight: '600', color: '#6B7280', marginBottom: 6 },
  kv: { fontSize: 14, color: '#111827', marginVertical: 2 },
  hint: { color: '#6B7280', fontSize: 12 },
  footer: { marginTop: 16, color: '#9CA3AF', fontSize: 12 },
  err: { color: '#B91C1C' },
  close: { alignSelf: 'center', marginTop: 16, padding: 8 },
  closeText: { color: '#4F46E5', fontSize: 15 },
});
```

**Step 2: `ExplainButton.tsx`**

```tsx
// mobile/components/reasoning/ExplainButton.tsx
import React, { useState } from 'react';
import { Pressable, Text, StyleSheet } from 'react-native';
import { ExplainSheet } from './ExplainSheet';

type Props =
  | { source: 'safety'; auditId: number; ruleId: string }
  | { source: 'specialist'; auditId: number; specialist: string };

export function ExplainButton(props: Props) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Pressable onPress={() => setOpen(true)} style={styles.btn}>
        <Text style={styles.text}>为什么?</Text>
      </Pressable>
      <ExplainSheet visible={open} onClose={() => setOpen(false)} {...props} />
    </>
  );
}

const styles = StyleSheet.create({
  btn: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: '#EEF2FF' },
  text: { fontSize: 12, color: '#4F46E5', fontWeight: '500' },
});
```

**Step 3: commit**

```bash
git add mobile/components/reasoning
git commit -m "feat(mobile/reasoning): ExplainSheet + ExplainButton (底部抽屉展示 why)"
```

---

### Task 3.4 — 挂到主屏 Safety 卡 + Specialist 卡

**Files:**
- Modify: `mobile/components/dashboard/SafetyAlertCard.tsx` (或类似命名，用 `grep -rn "Safety" mobile/components/` 定位)
- Modify: 主屏上展示 Specialist finding 的组件（`grep -rn "specialist" mobile/components/` 定位）

**Step 1: 定位组件**

```bash
cd mobile
grep -rn "safety" components/ | grep -i "card\|alert" | head -5
grep -rn "specialist" components/ | grep -i "card\|panel" | head -5
```

**Step 2: 在 Safety 卡 props 增加 `audit_id`; 组件内部底部右侧放 `<ExplainButton source="safety" auditId={audit_id} ruleId={alert.rule_id} />`.**

确保 `audit_id` 能从 `/api/v1/safety/me` 响应带上来 (如未带, 去 `backend/app/api/safety.py` 的 response 里加 `audit_id`). 如果 Mobile 已经通过 `/reasoning-trace/recent` 拿到 safety-related trace id, 也可以。

**Step 3: 真机 OTA preview**

```bash
./scripts/mobile-ota.sh preview "reasoning explain sheet v1"
```

真机自己跑 Safety 卡 + Specialist 卡各点一次, 抽屉弹出 → 数据正确 → 关闭.

**Step 4: commit**

```bash
git add mobile/components
git commit -m "feat(mobile/home): Safety/Specialist 卡片加'为什么?'按钮, 弹 ExplainSheet"
```

---

## Day 4 — `/clinical-journal/timeline` API

**Files:**
- Modify: `backend/app/api/clinical_journal.py`
- Test: `backend/tests/test_journal_timeline_api.py`

### Task 4.1 — 失败测试

```python
# backend/tests/test_journal_timeline_api.py
from datetime import datetime, timedelta, timezone
from app.models.clinical_journal import CaseThread, ClinicalJournalEntry


def _seed(db, user_id=1):
    now = datetime.now(timezone.utc)
    t1 = CaseThread(user_id=user_id, theme="鼻炎管理", title="我的鼻炎",
                    status="active", opened_at=now - timedelta(days=20))
    db.add(t1); db.commit(); db.refresh(t1)

    db.add_all([
        ClinicalJournalEntry(user_id=user_id, case_thread_id=t1.id,
                             generated_at=now - timedelta(days=1),
                             created_by="orchestrator",
                             subjective="晨起鼻塞, 喷嚏连作, 前夜粉尘环境暴露",
                             objective="...", assessment="...", plan="..."),
        ClinicalJournalEntry(user_id=user_id, case_thread_id=None,
                             generated_at=now - timedelta(hours=6),
                             created_by="briefing_task",
                             subjective="周度摘要", objective="...",
                             assessment="...", plan="..."),
    ])
    db.commit()


def test_journal_timeline_empty_schema(client, auth_headers_user_1):
    r = client.get("/api/v1/clinical-journal/timeline", headers=auth_headers_user_1)
    assert r.status_code == 200
    body = r.json()
    assert body == {"threads": []}


def test_journal_timeline_groups_by_thread_plus_others(client, db, auth_headers_user_1):
    _seed(db, user_id=1)  # 假设 user_1 fixture 的 user id=1, 否则传入
    r = client.get("/api/v1/clinical-journal/timeline?days=30", headers=auth_headers_user_1)
    assert r.status_code == 200
    threads = r.json()["threads"]
    # 至少两组: 鼻炎管理 + 无主题 bucket
    themes = {t["theme"] for t in threads}
    assert "鼻炎管理" in themes
    assert any(t["thread_id"] is None for t in threads)


def test_journal_timeline_subjective_short_truncated_60_chars(client, db, auth_headers_user_1):
    _seed(db, user_id=1)
    r = client.get("/api/v1/clinical-journal/timeline", headers=auth_headers_user_1)
    entries = [e for t in r.json()["threads"] for e in t["entries"]]
    assert all(len(e["subjective_short"]) <= 60 for e in entries)


def test_journal_timeline_days_filter(client, db, auth_headers_user_1):
    now = datetime.now(timezone.utc)
    db.add(ClinicalJournalEntry(
        user_id=1, case_thread_id=None,
        generated_at=now - timedelta(days=90),
        created_by="orchestrator",
        subjective="太老了", objective="o", assessment="a", plan="p",
    ))
    db.commit()
    r = client.get("/api/v1/clinical-journal/timeline?days=30", headers=auth_headers_user_1)
    flat = [e for t in r.json()["threads"] for e in t["entries"]]
    assert not any(e["subjective_short"].startswith("太老了") for e in flat)
```

### Task 4.2 — 实现 `/timeline`

**Step 1: 运行失败**

```bash
pytest tests/test_journal_timeline_api.py -q --no-cov -x
```

**Step 2: 在 `clinical_journal.py` 加 endpoint**

```python
# 追加 imports
from collections import defaultdict
from datetime import datetime, timedelta, timezone


@router.get("/timeline", summary="按 case thread 分组的 SOAP timeline")
def journal_timeline(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.models.clinical_journal import CaseThread, ClinicalJournalEntry
    since = datetime.now(timezone.utc) - timedelta(days=days)

    entries = (
        db.query(ClinicalJournalEntry)
        .filter(ClinicalJournalEntry.user_id == current_user.id,
                ClinicalJournalEntry.generated_at >= since)
        .order_by(ClinicalJournalEntry.generated_at.desc())
        .all()
    )

    thread_ids = {e.case_thread_id for e in entries if e.case_thread_id}
    thread_map: dict[int, CaseThread] = {}
    if thread_ids:
        for t in db.query(CaseThread).filter(CaseThread.id.in_(thread_ids)).all():
            thread_map[t.id] = t

    bucket: dict[int | None, list] = defaultdict(list)
    for e in entries:
        bucket[e.case_thread_id].append(e)

    def _short(s: str | None) -> str:
        s = (s or "").strip().replace("\n", " ")
        return s[:60]

    threads_out = []
    for tid, group in bucket.items():
        if tid and tid in thread_map:
            t = thread_map[tid]
            threads_out.append({
                "thread_id": t.id, "theme": t.theme, "status": t.status,
                "title": t.title, "entry_count": len(group),
                "last_updated": group[0].generated_at.isoformat(),
                "entries": [{
                    "id": e.id, "generated_at": e.generated_at.isoformat(),
                    "created_by": e.created_by,
                    "subjective_short": _short(e.subjective),
                    "has_soap": bool((e.subjective or "").strip() and (e.plan or "").strip()),
                } for e in group],
            })
        else:
            threads_out.append({
                "thread_id": None, "theme": "其他 / 周度摘要",
                "status": None, "title": None,
                "entry_count": len(group),
                "last_updated": group[0].generated_at.isoformat(),
                "entries": [{
                    "id": e.id, "generated_at": e.generated_at.isoformat(),
                    "created_by": e.created_by,
                    "subjective_short": _short(e.subjective),
                    "has_soap": bool((e.subjective or "").strip() and (e.plan or "").strip()),
                } for e in group],
            })

    threads_out.sort(key=lambda t: t["last_updated"], reverse=True)
    return {"threads": threads_out}
```

**Step 3: 运行测试通过**

```bash
pytest tests/test_journal_timeline_api.py -q --no-cov -x 2>&1 | tail
```

**Step 4: commit**

```bash
git add backend/app/api/clinical_journal.py backend/tests/test_journal_timeline_api.py
git commit -m "feat(journal): GET /clinical-journal/timeline, case-thread 分组 + 无主题 bucket"
```

---

## Day 5 — Mobile Journal Tab 重构为分组 Timeline

**Files:**
- Modify: `mobile/app/(tabs)/journal/index.tsx`
- Create: `mobile/hooks/useJournalTimeline.ts`
- Modify: `mobile/services/clinicalJournal.ts` (加 `fetchTimeline`)

### Task 5.1 — service + hook

```ts
// mobile/services/clinicalJournal.ts (追加)
export interface TimelineEntry {
  id: number; generated_at: string; created_by: string;
  subjective_short: string; has_soap: boolean;
}
export interface TimelineThread {
  thread_id: number | null; theme: string;
  status: string | null; title: string | null;
  entry_count: number; last_updated: string;
  entries: TimelineEntry[];
}

export async function fetchJournalTimeline(days = 30): Promise<{ threads: TimelineThread[] }> {
  const res = await api.get('/clinical-journal/timeline', { params: { days } });
  return res.data;
}
```

```ts
// mobile/hooks/useJournalTimeline.ts
import { useQuery } from '@tanstack/react-query';
import { fetchJournalTimeline } from '../services/clinicalJournal';

export function useJournalTimeline(days = 30) {
  return useQuery({
    queryKey: ['journal-timeline', days],
    queryFn: () => fetchJournalTimeline(days),
    staleTime: 60 * 1000,
  });
}
```

### Task 5.2 — Journal tab 重构

**Step 1: 重写 `mobile/app/(tabs)/journal/index.tsx`**

Reference: 参考 `mobile/app/(tabs)/alerts.tsx` 的 section list / expandable pattern. 用 `SectionList` 或 `FlatList<Thread>` 每个 thread 是一个可展开的 card. 点击 entry → `router.push(\`/journal/${entry.id}\`)` (已有详情).

空态: "还没有 SOAP 记录 — 去对话聊点健康话题, 系统会自动落档."

**Step 2: 真机 preview**

```bash
./scripts/mobile-ota.sh preview "journal timeline v1"
```

在空用户 + 有数据用户各验一次。

**Step 3: commit**

```bash
git add mobile
git commit -m "feat(mobile/journal): tab 改为 case-thread 分组 timeline, 空态引导对话"
```

---

## Day 6 — `/specialists/{name}/scorecard` API

**Files:**
- Modify: `backend/app/api/specialist_hit_rate.py` (追加 endpoint)
- Test: `backend/tests/test_specialist_scorecard_api.py`

### Task 6.1 — 失败测试

```python
# backend/tests/test_specialist_scorecard_api.py
from datetime import datetime, timezone, timedelta
from app.models.action_card import ActionCard


def test_scorecard_empty(client, auth_headers_user_1):
    r = client.get(
        "/api/v1/specialists/recovery_coach/scorecard?days=30",
        headers=auth_headers_user_1,
    )
    assert r.status_code == 200
    b = r.json()
    assert b["proposed_count"] == 0
    assert b["graded_count"] == 0
    assert b["cards"] == []


def test_scorecard_mixed(client, db, auth_headers_user_1):
    now = datetime.now(timezone.utc)
    db.add_all([
        ActionCard(user_id=1, title="早睡 22:30", content="c",
                   creator_specialist="recovery_coach",
                   created_at=now - timedelta(days=15),
                   graded_at=now - timedelta(days=8),
                   accuracy_score=85, metric_key="sleep_score",
                   target_value="78", actual_value="81",
                   grading_notes="提前入睡 42 分, 达标"),
        ActionCard(user_id=1, title="蛋白 +20g", content="c",
                   creator_specialist="recovery_coach",
                   created_at=now - timedelta(days=5)),
    ])
    db.commit()

    r = client.get(
        "/api/v1/specialists/recovery_coach/scorecard?days=30",
        headers=auth_headers_user_1,
    )
    b = r.json()
    assert b["proposed_count"] == 2
    assert b["graded_count"] == 1
    assert b["avg_accuracy"] == 85.0
    assert len(b["cards"]) == 2


def test_scorecard_unknown_specialist_404(client, auth_headers_user_1):
    r = client.get(
        "/api/v1/specialists/totally_fake/scorecard",
        headers=auth_headers_user_1,
    )
    assert r.status_code == 404
    assert "legal_specialists" in r.json().get("detail", str(r.json()))
```

### Task 6.2 — 实现

```python
# 在 specialist_hit_rate.py 追加

_LEGAL_SPECIALISTS = {
    "recovery_coach", "fuel_strategist", "movement_coach",
    "mental_health_companion", "safety_guardian",
    "hypertension_specialist", "metabolic_specialist",
    "rhinitis_specialist", "knowledge_librarian", "longitudinal_analyst",
}


@router.get("/{name}/scorecard", summary="单 specialist 近 N 天命中详情")
def specialist_scorecard(
    name: str,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if name not in _LEGAL_SPECIALISTS:
        raise HTTPException(
            status_code=404,
            detail={"message": f"未知 specialist: {name}",
                    "legal_specialists": sorted(_LEGAL_SPECIALISTS)},
        )

    from app.models.action_card import ActionCard
    from sqlalchemy import func
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = db.query(ActionCard).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.creator_specialist == name,
        ActionCard.created_at >= since,
    )
    cards = base.order_by(ActionCard.created_at.desc()).all()

    graded = [c for c in cards if c.accuracy_score is not None]
    avg_acc = (sum(c.accuracy_score for c in graded) / len(graded)) if graded else None

    return {
        "specialist": name,
        "window_days": days,
        "proposed_count": len(cards),
        "graded_count": len(graded),
        "hit_rate": round(len(graded) / len(cards), 2) if cards else 0.0,
        "avg_accuracy": round(avg_acc, 1) if avg_acc is not None else None,
        "cards": [
            {
                "id": c.id, "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "graded_at": c.graded_at.isoformat() if c.graded_at else None,
                "metric_key": c.metric_key,
                "target_value": c.target_value,
                "actual_value": c.actual_value,
                "accuracy_score": c.accuracy_score,
                "adherence_kind": c.adherence_kind,
                "adherence_confidence": c.adherence_confidence,
                "why_short": (c.grading_notes or "")[:120] or None,
            }
            for c in cards
        ],
    }
```

**Step 3: 运行测试**

```bash
pytest tests/test_specialist_scorecard_api.py -q --no-cov -x 2>&1 | tail
```

期望: 3 passed.

**Step 4: commit**

```bash
git add backend/app/api/specialist_hit_rate.py backend/tests/test_specialist_scorecard_api.py
git commit -m "feat(specialist): GET /{name}/scorecard — 近 N 天 ActionCard + 评分详情"
```

---

## Day 7 — Mobile Specialist 详情页 + Hero Chip

**Files:**
- Create: `mobile/app/specialist/[name].tsx`
- Create: `mobile/hooks/useSpecialistScorecard.ts`
- Modify: `mobile/services/actionCards.ts` (或新增 `specialistScorecard.ts`)
- Modify: Hero 组件加 chip 入口 (`grep -rn "HeroCard\|Hero" mobile/components/` 定位)

### Task 7.1 — service + hook

```ts
// mobile/services/specialistScorecard.ts
import api from './api';

export interface ScorecardCard {
  id: number; title: string;
  created_at: string | null; graded_at: string | null;
  metric_key: string | null;
  target_value: string | null; actual_value: string | null;
  accuracy_score: number | null;
  adherence_kind: string | null; adherence_confidence: number | null;
  why_short: string | null;
}

export interface ScorecardResponse {
  specialist: string; window_days: number;
  proposed_count: number; graded_count: number;
  hit_rate: number; avg_accuracy: number | null;
  cards: ScorecardCard[];
}

export async function fetchScorecard(name: string, days = 30): Promise<ScorecardResponse> {
  const res = await api.get(`/specialists/${name}/scorecard`, { params: { days } });
  return res.data;
}
```

```ts
// mobile/hooks/useSpecialistScorecard.ts
import { useQuery } from '@tanstack/react-query';
import { fetchScorecard } from '../services/specialistScorecard';

export function useSpecialistScorecard(name: string, days = 30) {
  return useQuery({
    queryKey: ['specialist-scorecard', name, days],
    queryFn: () => fetchScorecard(name, days),
    enabled: Boolean(name),
    staleTime: 60 * 1000,
  });
}
```

### Task 7.2 — 详情页

```tsx
// mobile/app/specialist/[name].tsx
import React from 'react';
import { ScrollView, StyleSheet, Text, View, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { useSpecialistScorecard } from '../../hooks/useSpecialistScorecard';

const SPECIALIST_LABELS: Record<string, string> = {
  recovery_coach: '恢复教练',
  fuel_strategist: '营养策略师',
  movement_coach: '训练教练',
  // ...补全 10 个
};

export default function SpecialistScorecardScreen() {
  const { name } = useLocalSearchParams<{ name: string }>();
  const q = useSpecialistScorecard(name as string, 30);
  const label = SPECIALIST_LABELS[name as string] || name;

  return (
    <>
      <Stack.Screen options={{ title: `${label} 成绩单` }} />
      <ScrollView style={{ flex: 1, backgroundColor: '#F9FAFB' }} contentContainerStyle={{ padding: 16 }}>
        {q.isLoading && <ActivityIndicator />}
        {q.isError && <Text>加载失败</Text>}
        {q.data && (
          <>
            <View style={styles.summary}>
              <Text style={styles.h1}>{label}</Text>
              <Text style={styles.stat}>
                近 30 天: {q.data.proposed_count} 条建议 · {q.data.graded_count} 条评分
              </Text>
              {q.data.avg_accuracy !== null && (
                <Text style={styles.stat}>平均命中度 {q.data.avg_accuracy} / 100</Text>
              )}
            </View>

            {q.data.cards.length === 0 && (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>还没有评分数据</Text>
                <Text style={styles.emptyHint}>
                  评分由 outcome_grader 在建议的 check_back_date 自动生成.
                  新产的建议需等到检查日 (通常 3-14 天) 后才会出现结果.
                </Text>
              </View>
            )}

            {q.data.cards.map((c) => (
              <View key={c.id} style={styles.card}>
                <Text style={styles.title}>{c.title}</Text>
                {c.accuracy_score !== null ? (
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <Text style={styles.metric}>目标 {c.target_value}</Text>
                    <Text style={styles.metric}>实际 {c.actual_value}</Text>
                    <Text style={[styles.score, scoreColor(c.accuracy_score)]}>
                      {c.accuracy_score}/100
                    </Text>
                  </View>
                ) : (
                  <Text style={styles.pending}>等待评分</Text>
                )}
                {c.why_short && <Text style={styles.why}>{c.why_short}</Text>}
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </>
  );
}

const scoreColor = (s: number) => ({
  color: s >= 70 ? '#059669' : s >= 40 ? '#D97706' : '#B91C1C',
});

const styles = StyleSheet.create({
  summary: { marginBottom: 16 },
  h1: { fontSize: 22, fontWeight: '600' },
  stat: { marginTop: 4, color: '#4B5563' },
  card: { backgroundColor: '#fff', padding: 12, borderRadius: 10, marginBottom: 8,
          borderWidth: 1, borderColor: '#E5E7EB' },
  title: { fontSize: 15, fontWeight: '500', marginBottom: 6 },
  metric: { color: '#374151', fontSize: 13 },
  score: { fontWeight: '600' },
  pending: { color: '#9CA3AF', fontStyle: 'italic' },
  why: { marginTop: 6, color: '#6B7280', fontSize: 13 },
  empty: { padding: 24, alignItems: 'center' },
  emptyTitle: { fontSize: 15, fontWeight: '500' },
  emptyHint: { marginTop: 6, color: '#6B7280', fontSize: 13, textAlign: 'center' },
});
```

### Task 7.3 — Hero chip 入口

在 Hero 组件 (通过 `grep` 定位) 拉 `/specialists/hit-rate`（已存在）, 对 `proposed_count >= 3` 的 specialist 显示一个 chip: "恢复教练 3/5 命中 →"; 点击 `router.push(\`/specialist/${name}\`)`.

### Task 7.4 — 真机 preview

```bash
./scripts/mobile-ota.sh preview "specialist scorecard v1"
```

有命中 + 零命中各验一次。

### Task 7.5 — commit

```bash
git add mobile
git commit -m "feat(mobile/specialist): scorecard 详情页 + Hero chip 入口"
```

---

## Day 8 — Admin Celery Health + Mobile TrustHintChip

### Task 8.1 — Backend Celery Health

**Files:**
- Create: `backend/app/services/celery_health.py`
- Modify: `backend/app/api/admin_observability.py` (在 dashboard 响应里追加 `celery_health`)
- Test: `backend/tests/test_celery_health.py`

**Step 1: 失败测试**

```python
# backend/tests/test_celery_health.py
from datetime import datetime, timedelta, timezone
from app.models.agent_audit_log import AgentAuditLog
from app.services.celery_health import celery_health_snapshot


def test_celery_health_all_no_data_on_empty_db(db):
    snap = celery_health_snapshot(db)
    assert "tasks" in snap
    assert all(t["status"] == "no_data" for t in snap["tasks"])


def test_celery_health_ok_when_recent_audit_exists(db):
    db.add(AgentAuditLog(
        user_id=1, agent_type="orchestrator", action="run",
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
        result_summary="brief",
    ))
    db.commit()
    snap = celery_health_snapshot(db)
    brief = next(t for t in snap["tasks"] if t["task"] == "morning_briefing")
    assert brief["status"] in ("ok", "observing")


def test_celery_health_stale_when_old_only(db):
    db.add(AgentAuditLog(
        user_id=1, agent_type="orchestrator", action="run",
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    ))
    db.commit()
    snap = celery_health_snapshot(db)
    brief = next(t for t in snap["tasks"] if t["task"] == "morning_briefing")
    assert brief["status"] == "stale"
```

**Step 2: 实现**

```python
# backend/app/services/celery_health.py
"""Celery beat 健康探针 — 不新增监控表, 基于现有日志反推."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

# 硬编码 5 个 Celery beat 任务的"健康假设"
_TASK_SPECS: List[Dict] = [
    {"task": "morning_briefing", "probe_model": "agent_audit_log",
     "probe_filter": {"agent_type": "orchestrator"},
     "expected_per_day": 1, "window_hours": 36},
    {"task": "open_loop_daily_briefing", "probe_model": "open_loop_history",
     "probe_filter": {}, "expected_per_day": 1, "window_hours": 36},
    {"task": "outcome_grader", "probe_model": "action_card",
     "probe_filter": {"has_graded_at": True}, "expected_per_day": 1, "window_hours": 48},
    {"task": "doctor_weekly_report", "probe_model": "clinical_journal",
     "probe_filter": {"created_by": "doctor_weekly_task"},
     "expected_per_week": 1, "window_hours": 168 + 24},
    {"task": "safety_evaluation", "probe_model": "agent_audit_log",
     "probe_filter": {"agent_type": "safety_guardian"},
     "expected_per_day": 1, "window_hours": 48},
]


def _probe_last(db: Session, model: str, filters: dict, window_hours: int):
    """Return (observed_count, last_at) in window."""
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    if model == "agent_audit_log":
        from app.models.agent_audit_log import AgentAuditLog
        q = db.query(AgentAuditLog).filter(AgentAuditLog.created_at >= since)
        if "agent_type" in filters:
            q = q.filter(AgentAuditLog.agent_type == filters["agent_type"])
        count = q.count()
        last = q.with_entities(func.max(AgentAuditLog.created_at)).scalar()
        return count, last
    if model == "open_loop_history":
        from app.models.open_loop_history import OpenLoopHistory
        q = db.query(OpenLoopHistory).filter(OpenLoopHistory.sent_at >= since)
        count = q.count()
        last = q.with_entities(func.max(OpenLoopHistory.sent_at)).scalar()
        return count, last
    if model == "action_card":
        from app.models.action_card import ActionCard
        q = db.query(ActionCard).filter(ActionCard.graded_at >= since) if filters.get("has_graded_at") else \
            db.query(ActionCard).filter(ActionCard.created_at >= since)
        count = q.count()
        last = q.with_entities(func.max(ActionCard.graded_at)).scalar()
        return count, last
    if model == "clinical_journal":
        from app.models.clinical_journal import ClinicalJournalEntry
        q = db.query(ClinicalJournalEntry).filter(
            ClinicalJournalEntry.generated_at >= since,
            ClinicalJournalEntry.created_by == filters.get("created_by", ""),
        )
        count = q.count()
        last = q.with_entities(func.max(ClinicalJournalEntry.generated_at)).scalar()
        return count, last
    return 0, None


def _status_from_ratio(observed: int, expected: int) -> str:
    if observed == 0 and expected > 0:
        return "stale"
    if expected == 0:
        return "no_data"
    ratio = observed / expected
    if ratio < 0.5 or ratio > 2.0:
        return "stale"
    return "ok"


def celery_health_snapshot(db: Session) -> dict:
    tasks = []
    for spec in _TASK_SPECS:
        count, last = _probe_last(db, spec["probe_model"], spec.get("probe_filter", {}),
                                  spec["window_hours"])
        expected = spec.get("expected_per_day") or spec.get("expected_per_week") or 0
        if "expected_per_day" in spec:
            expected_in_window = expected * (spec["window_hours"] / 24.0)
        else:
            expected_in_window = expected * (spec["window_hours"] / 168.0)

        status = "no_data" if count == 0 and last is None else _status_from_ratio(
            count, max(1, int(expected_in_window))
        )
        tasks.append({
            "task": spec["task"],
            "expected_per_day": spec.get("expected_per_day"),
            "expected_per_week": spec.get("expected_per_week"),
            "observed": count,
            "last_run": last.isoformat() if last else None,
            "status": status,
        })
    return {"tasks": tasks, "note": "间接推算: 读现有表的 created_at/graded_at, 非 Celery 原生指标"}
```

**Step 3: 暴露在 observability API**

修改 `admin_observability.py`:

```python
# 在 get_observation_dashboard 返回前追加
from app.services.celery_health import celery_health_snapshot
# payload 加一行
"celery_health": celery_health_snapshot(db),
```

**Step 4: 测试通过**

```bash
pytest tests/test_celery_health.py -q --no-cov -x
pytest tests/test_observability_service.py -q --no-cov -x  # 确保 dashboard 没 regression
```

**Step 5: commit**

```bash
git add backend/app/services/celery_health.py backend/app/api/admin_observability.py backend/tests/test_celery_health.py
git commit -m "feat(observability): celery_health 区块, 读现有表反推 5 任务状态"
```

### Task 8.2 — Frontend Celery Health Block

**Files:**
- Create: `frontend/src/app/admin/components/CeleryHealthBlock.tsx`
- Modify: `frontend/src/app/admin/components/ObservabilityTab.tsx` (引入 Block)

**Step 1: 写组件**

```tsx
// frontend/src/app/admin/components/CeleryHealthBlock.tsx
'use client';

interface Task {
  task: string;
  expected_per_day: number | null;
  expected_per_week: number | null;
  observed: number;
  last_run: string | null;
  status: 'ok' | 'stale' | 'no_data' | 'observing';
}

const STATUS_STYLE: Record<string, string> = {
  ok: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/40',
  stale: 'bg-red-500/20 text-red-200 border-red-400/40',
  no_data: 'bg-slate-500/20 text-slate-200 border-slate-400/40',
  observing: 'bg-amber-500/20 text-amber-200 border-amber-400/40',
};

export default function CeleryHealthBlock({ tasks, note }: { tasks: Task[]; note?: string }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-5">
      <h3 className="text-lg font-semibold text-white mb-3">H. Celery Beat 健康</h3>
      {note && <div className="text-xs text-purple-200/60 mb-3">{note}</div>}
      <div className="grid gap-2">
        {tasks.map((t) => (
          <div key={t.task}
               className={`border rounded-md px-3 py-2 flex justify-between items-center ${STATUS_STYLE[t.status] ?? STATUS_STYLE.no_data}`}>
            <div>
              <div className="font-medium">{t.task}</div>
              <div className="text-xs opacity-70">
                {t.expected_per_day ? `~ ${t.expected_per_day}/天` : `~ ${t.expected_per_week}/周`}
                {' · '}最近: {t.last_run ? new Date(t.last_run).toLocaleString('zh-CN') : '—'}
              </div>
            </div>
            <div className="text-sm font-mono">{t.status}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: 在 ObservabilityTab 渲染**

```tsx
// ObservabilityTab.tsx (interface + JSX)
interface CeleryHealth { tasks: Task[]; note?: string }
// DashboardResponse 里加 celery_health?: CeleryHealth

// 在 Section G 之前插入:
{data.report.celery_health && (
  <CeleryHealthBlock tasks={data.report.celery_health.tasks}
                     note={data.report.celery_health.note} />
)}
```

实际上 `celery_health` 是直接挂在 payload (不在 report) 里 — 按 Day 8.1 Step 3 的写法：`data.celery_health`. 核对 Admin 返回结构后调整字段路径。

**Step 3: `npx tsc --noEmit` 通过**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "admin|Observ" | head
```

**Step 4: commit**

```bash
git add frontend/src/app/admin
git commit -m "feat(admin/observability): Celery Health block 渲染 5 任务状态"
```

### Task 8.3 — Mobile TrustHintChip

**Files:**
- Create: `mobile/components/home/TrustHintChip.tsx`
- Modify: Hero 主屏组件 引入

**Step 1: 组件**

```tsx
// mobile/components/home/TrustHintChip.tsx
import React from 'react';
import { Pressable, Text, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';

export function TrustHintChip({
  specialist, hitRate, proposedCount,
}: { specialist: string; hitRate: number; proposedCount: number }) {
  const router = useRouter();
  if (proposedCount < 3) return null;  // 新用户不显示
  return (
    <Pressable onPress={() => router.push(`/specialist/${specialist}`)} style={styles.chip}>
      <Text style={styles.text}>
        {specialist} · {Math.round(hitRate * 100)}% 命中 →
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14,
          backgroundColor: '#EEF2FF', alignSelf: 'flex-start' },
  text: { fontSize: 12, color: '#4F46E5', fontWeight: '500' },
});
```

**Step 2: 在 Hero 组件按 `/specialists/hit-rate` 返回数据 map 渲染多个 chip**

**Step 3: OTA preview + 真机验**

```bash
./scripts/mobile-ota.sh preview "trust hint chip v1"
```

**Step 4: commit**

```bash
git add mobile
git commit -m "feat(mobile/home): TrustHintChip 浮 specialist 近 30 天命中率, 点击进详情"
```

---

## Day 9 — 埋点 + 观察期看板 suggestion

**目标**: 让 design.md §4.3 的"痛点真的消失了"可度量.

### Task 9.1 — 扩 interaction_feedback event_type

**Files:**
- Modify: `backend/app/models/interaction_feedback.py` (如已有 event_type 就只扩 allowed values; 如没有, 加一个简单 event 字段)
- Create: `backend/app/api/client_events.py` (`POST /client-events` endpoint, 接 3 种 event: `reasoning_sheet_opened`, `journal_timeline_entered`, `specialist_scorecard_entered`)
- Test: `backend/tests/test_client_events.py`

先 grep 看结构:

```bash
grep -n "class\|event_type\|event\b" backend/app/models/interaction_feedback.py
```

按实际模型要么直接扩 allowed 值, 要么用一个轻量新 `ClientEvent` 模型 (只含 user_id, event_name, meta JSON, created_at). 避免新表倾向：可存到 `interaction_feedback` 现有表 + 扩 allowed `event_type` 常量 set.

### Task 9.2 — 观察期看板新增 3 条 suggestion

**Files:**
- Modify: `backend/app/services/observability_service.py::actionable_suggestions`

```python
# 在 actionable_suggestions 里追加读事件比例, 例如:
events = report.get("client_events", {})
rs_shown = events.get("reasoning_shown", 0)
rs_opened = events.get("reasoning_sheet_opened", 0)
if rs_shown > 0:
    rate = rs_opened / rs_shown
    if rate < 0.05:
        out.append(f"🔴 Reasoning Trace 点击率 {rate*100:.0f}% — 用户没觉得'为什么'值得看")
    elif rate < 0.2:
        out.append(f"🟡 Reasoning Trace 点击率 {rate*100:.0f}% — 未达 20% 目标")
    else:
        out.append(f"🟢 Reasoning Trace 点击率 {rate*100:.0f}% — 抽屉功能达标")
# 类似写 Journal / Specialist 两条
```

`collect_dashboard` 里补一个 `client_events_stats` section.

### Task 9.3 — Mobile 埋点调用

在 `ExplainSheet` 打开时 / `journal/index.tsx` 挂载时 / `specialist/[name].tsx` 挂载时, `POST /client-events` 发对应 event.

**Step 4: commit 分别**

```bash
git add backend/app/models backend/app/api backend/app/services/observability_service.py backend/tests/test_client_events.py
git commit -m "feat(events): client_events 接点 + 3 条看板 suggestion"

git add mobile
git commit -m "feat(mobile/events): ExplainSheet/Journal/Scorecard 挂载发埋点"
```

---

## Day 10 — 冒烟 + EAS preview → production + doc drift

### Task 10.1 — 真机冒烟清单

1. 主屏点 Safety 卡 × 2 类告警, 抽屉各弹一次
2. 主屏点 Specialist 卡, 抽屉弹一次
3. Journal tab 切到空用户 (或清 case_thread) + 有数据用户 各进一次
4. Hero chip 点 recovery_coach 进详情, 查看零命中 / 有命中 两种
5. Admin 看板看 Celery Health 区块 5 任务状态
6. 主屏发一条新对话确认 `log_specialist_findings` 写入 (检查 `agent_audit_logs.agent_type='specialist_batch'`)

任一失败: stop, 修了再继续.

### Task 10.2 — EAS preview → production

```bash
./scripts/mobile-ota.sh preview "v1 full: reasoning + journal + scorecard"
# 自己真机挂一晚
./scripts/mobile-ota.sh production "v1 full: reasoning + journal + scorecard"
```

### Task 10.3 — 后端部署 + 健康度

```bash
./deploy.sh -b
```

`system_health_score.py` 自动跑, 阈值不低于 35.

### Task 10.4 — doc drift

更新:

- `CLAUDE.md` Architecture 段 (如果 Safety / Orchestrator audit 行为变化需注明 `result_detail` 结构)
- `docs/STRATEGY-2026.md` §五 阶段 4.5 打勾：
  - [x] Clinical Journal 前端 case timeline UI (Mobile 版 ship)
  - [x] Reasoning Trace UI v1

```bash
# 运行 doc drift check
cd backend && python scripts/check_doc_drift.py
```

### Task 10.5 — 最终 commit

```bash
git add CLAUDE.md docs/STRATEGY-2026.md
git commit -m "docs: Sprint 记忆推理可见化 v1 ship, STRATEGY 阶段 4.5 打勾"
```

---

## 验收 & 止损

| 指标 | 判据 | 来源 |
|---|---|---|
| Reasoning 点击率 | Day 17 时 ≥20% | 观察期看板新 suggestion |
| Journal tab 进入 | Day 17 时 ≥10 次 | 同上 |
| Specialist 详情页进入 | Day 17 时 出现"actual vs target" 印象深刻瞬间 | 产品 owner 主观反馈 |
| Celery Health 误报 | 不出现连续 2 次明显误报 | 观察 |

Day 7 (仅 reasoning + journal 已 ship) 中期 check: 如果点击率 <5%, 按 design.md §4.4 止损条件, 停做 Day 7 的 Specialist 详情页; 重新想交互。

---

## 附录: 依赖与排序

- Day 1 → Day 2: 必须, audit 不带 snapshot 则 explainer 反查不了
- Day 2 → Day 3: Mobile 抽屉依赖后端 endpoint
- Day 4 → Day 5: Mobile timeline 依赖后端 timeline API
- Day 6 → Day 7: Mobile scorecard 依赖后端 scorecard API
- Day 8 可并行 (独立 celery health block)
- Day 9 应在 Day 3/5/7 都 ship 后 (埋 `rs_shown` 基数)
- Day 10 是总验收, 不并行

Buffer: 10 天 × 0.7 占用 = 7 实际工作日, 多出 3 天给不可预见 bug / refactor / EAS build 失败.
