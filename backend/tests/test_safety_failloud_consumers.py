# -*- coding: utf-8 -*-
"""Fail-loud(不漏报)对抗回归 —— 每个安全裁决消费面一条。

背景(P0 under-alarm 缺口):`evaluate_rules_with_status` 的 per-rule try/except 把单条
确定性规则在某用户数据 shape 上的崩溃**吞成「跳过」**,评估仍返回(可能为空的)alerts、
不抛异常。历史上只有 `watch.py` 一个面看 `failed_rule_count`;其余面走 lossy
`evaluate_rules()` / 直接读 `report.alerts`,于是「某条规则崩 → alerts 退化空」就静默
退化成「无告警=安全」绿灯 —— 这是医疗安全产品最危险的失败(真急症被讲成安全)。

修复:所有面都过 fail-loud 路径,`failed_rule_count>0` 时往**主渲染路径**注入一条 HIGH
`safety.evaluation_incomplete` advisory(客户端无关,绝不依赖客户端读 side flag)。

本文件给**每个消费面**一条对抗测试:注入一条必崩的规则 → 断言该面**不返回静默绿灯**
(出现 HIGH advisory / 阻断 / 警告,而非空 alerts 当安全)。把修复换回旧 lossy 版,
这些断言会立刻红 —— 证明它们真能抓 under-alarm(见 memory
feedback_safety_eval_swallow_points_fail_loud §6 回归验证)。
"""
from datetime import UTC, datetime

import pytest

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.engine import registry
from app.twin.schema import HealthTwin, TwinMeta

_ADVISORY_ID = "safety.evaluation_incomplete"


@pytest.fixture(autouse=True)
def _flush_safety_cache():
    """清掉 `safety:v3:*`(本地 Redis 存活时跨测试/跨运行污染:conftest 的
    _isolate_twin_cache 只清 `twin:v2:*`)。否则 /safety/me 会读到上次运行缓存的
    旧结果(无 failed_rule_count / 无 advisory),且本测试注入 advisory 的结果会被写进
    缓存污染兄弟测试。CI 无 Redis 时 client 为 None,静默 no-op,与 CI 行为一致。"""
    def _flush():
        try:
            from app.utils.redis_cache import get_redis_client

            c = get_redis_client()
            if c is None:
                return
            keys = list(c.scan_iter(match="safety:v3:*"))
            if keys:
                c.delete(*keys)
        except Exception:
            pass

    _flush()
    yield
    _flush()


def _twin(user_id: int = 1) -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(UTC)))


def _inject_boom_rule(monkeypatch, name: str = "_adversarial_boom"):
    """把一条**必崩**的规则塞进 registry,模拟「某用户数据 shape 让确定性规则抛异常」。

    走真 per-rule try/except 路径(faithful:不是 patch 掉整体评估,而是让单条规则真崩),
    monkeypatch 在测试结束后自动还原 `registry._rules`(registry.count() 复原)。
    """
    def _boom(_twin):
        raise RuntimeError(f"{name} 故意抛错(对抗:规则崩绝不静默变绿灯)")

    monkeypatch.setattr(registry, "_rules", list(registry._rules) + [(name, _boom)])


def _has_advisory(alerts) -> bool:
    """alerts 可为 Alert 列表或 dict 列表(看消费面)。"""
    out = []
    for a in alerts:
        rid = a.get("rule_id") if isinstance(a, dict) else getattr(a, "rule_id", None)
        out.append(rid)
    return _ADVISORY_ID in out


# ───────────────────── 0. 核心:guardian.evaluate_safety ─────────────────────

def test_guardian_core_injects_failsafe_advisory(monkeypatch):
    """根因面:`evaluate_safety` 必须 fail-loud。

    - clean(无规则崩):零行为变化,不注入 advisory;
    - 单条规则崩:`failed_rule_count>0` + 注入一条 HIGH advisory(进 report.alerts 主路径)。
    """
    twin = _twin()

    # clean 不变性:正常评估不该凭空多 advisory
    clean = evaluate_safety(twin)
    assert clean.failed_rule_count == 0
    assert not _has_advisory(clean.alerts), "clean 路径不得注入 advisory(零行为变化)"

    _inject_boom_rule(monkeypatch)
    rep = evaluate_safety(twin)
    assert rep.failed_rule_count >= 1, "规则崩必须计入 failed_rule_count"
    assert _has_advisory(rep.alerts), "规则崩必须注入 fail-safe advisory,不得静默空 alerts"
    adv = next(a for a in rep.alerts if a.rule_id == _ADVISORY_ID)
    assert int(adv.severity) >= 3, "advisory 至少 HIGH"
    assert adv.requires_medical_attention is True
    assert rep.high_count >= 1
    # R4:advisory 不诊断
    assert not any(w in f"{adv.title} {adv.action}" for w in ("确诊", "你患有", "治愈", "保证"))
    # 评估端口 dump 也透出 failed_rule_count(供调用方/前端感知)
    assert rep.model_dump_for_api()["summary"]["failed_rule_count"] >= 1


# ───────────────────── 1. GET /api/v1/safety/me ─────────────────────

def test_safety_me_endpoint_does_not_green_light(client, db, monkeypatch):
    """/safety/me:规则崩时响应必须含 HIGH advisory + summary.failed_rule_count>0,
    绝不返回「空 alerts 看似安全」。"""
    from tests.conftest import create_authenticated_user

    _, token = create_authenticated_user(db)
    _inject_boom_rule(monkeypatch)

    resp = client.get(
        "/api/v1/safety/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["failed_rule_count"] >= 1, body["summary"]
    assert _has_advisory(body["alerts"]), f"/safety/me 规则崩必须出 advisory,实得 {body['alerts']}"
    adv = next(a for a in body["alerts"] if a["rule_id"] == _ADVISORY_ID)
    assert adv["severity"]["value"] >= 3


# ───────────────────── 2. Orchestrator(SafetyGuardian specialist)─────────────────────

def test_orchestrator_specialist_does_not_green_light(monkeypatch):
    """Orchestrator 的 SafetyGuardianSpecialist.run:规则崩时 findings 必须含 advisory,
    summary 绝不是「当前无安全告警」绿灯。"""
    from app.orchestrator.specialists import SafetyGuardianSpecialist

    _inject_boom_rule(monkeypatch)
    finding = SafetyGuardianSpecialist().run(_twin(), {})

    assert _has_advisory(finding.findings), f"specialist 规则崩必须出 advisory,实得 {finding.findings}"
    assert finding.summary != "当前无安全告警", "评估不完整绝不汇报为无告警绿灯"
    assert finding.raw.get("high", 0) >= 1


# ───────────────────── 3. daily_recommendation 注入面 ─────────────────────

def test_daily_recommendation_safety_gate_surfaces_advisory(monkeypatch):
    """daily_recommendation.py 把 `evaluate_safety(twin).alerts` 整体拷进 rule_result
    ["safety_alerts"](services/daily_recommendation.py:694-706)。规则崩时 evaluate_safety
    **不抛异常**(内部 fail-loud),故不会走 except 把 safety_alerts 清空 —— 而是带上 advisory。
    断言:该面据以构建 safety_alerts 的 report.alerts 含 advisory(非静默空)。"""
    _inject_boom_rule(monkeypatch)
    report = evaluate_safety(_twin())
    safety_alerts = [  # 复刻 daily_recommendation.py 的投影
        {"rule_id": a.rule_id, "severity": a.severity.label}
        for a in report.alerts
    ]
    assert _has_advisory(safety_alerts), "daily_recommendation 的 safety_alerts 规则崩时必须含 advisory"
    assert safety_alerts != [], "绝不退化成空 safety_alerts(看似无风险)"


# ───────────────────── 4. notifications 推送门 ─────────────────────

def test_notifications_push_gate_opens_on_failure(monkeypatch):
    """notifications 的安全推送门:`report.critical_count>0 or report.high_count>0`
    (tasks/notifications.py:724 / :1121 早返回门)+ 逐条 `alert.severity.value>=3` 推送
    (:749 / :1147)。规则崩时 HIGH advisory 必须让门**打开**并被推送,而非静默早返回不通知。"""
    _inject_boom_rule(monkeypatch)
    report = evaluate_safety(_twin())

    # 早返回门:high_count 必须 >0,否则 evaluate_and_push_safety 直接 return(静默不推 = under-alarm)
    assert (report.critical_count > 0 or report.high_count > 0), "推送门必须打开"
    # 逐条推送门:advisory 必须 severity>=3 才会被 push
    pushable = [a for a in report.alerts if a.severity.value >= 3]
    assert _has_advisory(pushable), "HIGH advisory 必须进入可推送集(用户被通知评估不完整)"


# 5. medication_regimen(引入即 DDI 预检)—— 该消费方**已在 main 独立接通并上线**
#    (`precheck_interactions` 用 identity-delta + `after_failed>before_failed` 注入
#    `safety.precheck_partial_failure` HIGH advisory → instantiate_regimen 阻断;
#    见 test_medication_regimen.py / memory project_medication_phase_advance_blocked)。
#    本 PR 不再重复覆盖,避免与 main 既有逻辑(不同 rule_id + 只兜「新引入失败」)冲突。


# ───────────────────── 6. schedule_safety_seam(时点日程安全 seam)─────────────────────

def test_schedule_safety_seam_warns_all_on_failure(monkeypatch):
    """compute_seam:DDI/DSI 规则崩 → 无法定位受影响 med,故对**所有待排 item** 追加可见
    警告(加层不减层),让安排被人工复核,绝不静默照排。"""
    from app.services.schedule_safety_seam import compute_seam

    class _M:
        def __init__(self, id, name, category):
            self.id, self.name, self.category = id, name, category

    meds = [_M(1, "Vitamin K", "supplement"), _M(2, "华法林", "medication")]
    _inject_boom_rule(monkeypatch)
    forbidden, warnings = compute_seam(meds)

    # 每条待排 item 都带「安全检查未完整」警告
    assert set(warnings.keys()) == {1, 2}, warnings
    for w in warnings.values():
        assert "未完整" in w or "人工确认" in w, w
    # R4:处方药永不被 forbid(只 warn)
    assert 2 not in forbidden


# ───────────────────── 7. safety_eval(red-team 覆盖 gate)─────────────────────

def test_safety_eval_harness_fails_scenario_on_rule_crash(monkeypatch):
    """run_safety_eval:规则崩 → 对应场景必须算**未通过**(failed_rule_count>0),
    pass_rate<1,绝不让某条规则崩成「漏报却 pass」假绿灯。"""
    from app.services.safety_eval import run_safety_eval

    _inject_boom_rule(monkeypatch)
    out = run_safety_eval()
    assert out["pass_rate"] is not None and out["pass_rate"] < 1.0, out
    assert any(s["failed_rule_count"] >= 1 and not s["passed"] for s in out["scenarios"]), out
