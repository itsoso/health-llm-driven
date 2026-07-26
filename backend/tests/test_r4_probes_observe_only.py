"""两个 R4 观测探针(只测量、不改行为)。

founder 选了「先探针再堵」/「纯 logger 影子测量」——因为:
- 用药 R4 逃逸通路可达已确证, 但**模型实际伪造 confirmed 的频率无生产证据**; 而修错会
  over-block(founder 每天要记 3 种胃药)。
- guidance 红线在主对话全程是暗的, 但现有饮食正则在开放域 9/15 误命中, 直接上 alert/审计
  会污染 /safety/audit(审计面 under-alarm)。
本测试锁死「探针零行为变更」这个不变量 —— 探针一旦开始拦截/写库, 这里必须红。
"""
import json
import logging

import pytest

from app.services.agent_executor import _guidance_shadow_probe
from app.services.meal_analysis import evaluate_guidance_rules, run_guidance_rules


# ───────────── #5 guidance 纯影子探针 ─────────────

class TestGuidanceShadowProbe:
    def test_evaluate_guidance_rules_is_pure_no_db(self):
        # 纯求值: 不收 db、不写审计。命中确定性处方文本。
        alerts = evaluate_guidance_rules(1, "每天吃 50 克坚果，别吃米饭。")
        assert alerts, "确定性量化饮食处方应命中"
        assert any(a.get("rule_id") for a in alerts)

    def test_evaluate_guidance_rules_empty_on_benign(self):
        assert evaluate_guidance_rules(1, "这餐约 450kcal, 今日蛋白还差 35g。") == []

    def test_probe_logs_on_hit(self, caplog):
        with caplog.at_level(logging.WARNING):
            _guidance_shadow_probe(1, "每天吃 50 克坚果，别吃米饭。")
        assert any("[guidance-probe]" in r.getMessage() for r in caplog.records)

    def test_probe_silent_on_benign(self, caplog):
        with caplog.at_level(logging.WARNING):
            _guidance_shadow_probe(1, "这餐约 450kcal。")
        assert not any("[guidance-probe]" in r.getMessage() for r in caplog.records)

    def test_probe_noop_on_empty(self, caplog):
        with caplog.at_level(logging.WARNING):
            _guidance_shadow_probe(1, "")
            _guidance_shadow_probe(1, "   ")
        assert not any("[guidance-probe]" in r.getMessage() for r in caplog.records)

    def test_probe_fail_soft_never_raises(self, monkeypatch, caplog):
        # 规则层抛错 → 探针不得打死回合, 但要留 log(不静默绿)
        import app.services.meal_analysis as ma

        def _boom(*a, **k):
            raise RuntimeError("rule exploded")

        monkeypatch.setattr(ma, "evaluate_guidance_rules", _boom)
        with caplog.at_level(logging.WARNING):
            _guidance_shadow_probe(1, "每天吃 50 克坚果")  # 不抛
        assert any("影子扫描失败" in r.getMessage() for r in caplog.records)

    def test_run_guidance_rules_still_audits(self, db, monkeypatch):
        # 回归: 餐食路径的带审计版本行为不变(探针重构不得动它)
        seen = {}

        import app.services.meal_analysis as ma

        def _fake_audit(db_, **kw):
            seen.update(kw)

        monkeypatch.setattr(ma.audit, "log_safety_evaluation", _fake_audit)
        alerts = run_guidance_rules(db, 1, "每天吃 50 克坚果，别吃米饭。")
        assert alerts
        assert seen.get("alerts_count") == len(alerts)  # 审计仍写


# ───────────── #2 用药 R4 逃逸探针 ─────────────

class TestMedicationR4Probe:
    @pytest.mark.asyncio
    async def test_block_logs_when_medication_arrives_with_model_confirmed(self, db, caplog):
        """模型自报 confirmed 被服务端授权边界阻断并留下无内容日志。"""
        from app.services.agent_executor import AgentExecutor

        ex = AgentExecutor(db)
        ex._current_user_id = 1
        ex._prefer_fast_record_model = False  # 有图/分析词时的真实取值 = Gate A 不跑
        ex._current_turn_user_message = "记录我吃了奥美拉唑"

        async def _fake_post_json(url, headers, data):
            return None, "network disabled in test"

        async def _fake_get_json(url, headers):
            return None, "network disabled in test"

        ex._api_post_json = _fake_post_json
        ex._api_get_json = _fake_get_json

        args = {
            "record_type": "medication",
            "data": {
                "medication_name": "奥美拉唑",
                "actual_dosage": "1粒",
                "confirmed": True,
            },
        }
        with caplog.at_level(logging.WARNING):
            await ex._exec_health_record("http://x/api/v1", {}, args)

        msgs = [r.getMessage() for r in caplog.records]
        assert any("[R4-block]" in m for m in msgs), f"阻断日志未触发: {msgs}"
        assert any("medication" in m for m in msgs if "[R4-block]" in m)

    @pytest.mark.asyncio
    async def test_model_confirmed_is_blocked_without_server_plan(self, db, caplog):
        """模型布尔值不是授权；无服务端计划时必须 fail closed。"""
        from app.services.agent_executor import AgentExecutor

        ex = AgentExecutor(db)
        ex._current_user_id = 1
        ex._prefer_fast_record_model = False
        ex._current_turn_user_message = "记录我吃了奥美拉唑"

        async def _fake_post_json(url, headers, data):
            return None, "network disabled in test"

        async def _fake_get_json(url, headers):
            return None, "network disabled in test"

        ex._api_post_json = _fake_post_json
        ex._api_get_json = _fake_get_json

        args = {
            "record_type": "medication",
            "data": {
                "medication_name": "奥美拉唑",
                "actual_dosage": "1粒",
                "confirmed": True,
            },
        }
        result = await ex._exec_health_record("http://x/api/v1", {}, args)
        payload = json.loads(result)
        assert payload["status"] == "rejected"
        assert payload["success"] is False
        assert payload["dispatch_started"] is False
        assert payload["error_code"] == "medication_plan_context_missing"
        assert "没有写入" in payload["message"]

    @pytest.mark.asyncio
    async def test_probe_silent_for_auto_kinds(self, db, caplog):
        """AUTO kind(water)带 confirmed 不该触发 R4 探针(只观测 NEVER_AUTO)。"""
        from app.services.agent_executor import AgentExecutor

        ex = AgentExecutor(db)
        ex._current_user_id = 1
        ex._prefer_fast_record_model = False
        ex._current_turn_user_message = "记录喝水 250ml"

        async def _fake_post(url, headers, data):
            return "{}"

        ex._api_post = _fake_post

        args = {"record_type": "water", "data": {"amount": 250, "confirmed": True}}
        with caplog.at_level(logging.WARNING):
            await ex._exec_health_record("http://x/api/v1", {}, args)
        assert not any("[R4-probe]" in r.getMessage() for r in caplog.records)
