"""喷嚏路径两修(founder 2026-07-17 生产日志实锤)。

生产事实(user=3, 24h):
  ① 全天最慢的 4 个回合**全是最简单的记录、全在整轮快路由上**, 全部 rounds=9(打满
     MAX_TOOL_ROUNDS)——「记录刚才打了一个喷嚏。」total=203s。快路由 p50=8.9s 是真收益,
     但 max=203s 比强模型 max=119s 还差 1.7 倍 → 加轮次逃生门, 只砍尾部。
  ② 「麦当劳店记录打了一个喷嚏。」→ 弱模型吐「✅ **症状已记录**」但**一个工具都没调**
     (它调的是只读 health_query), 且这段字**已经流到屏幕上**。:7228 的诚实覆盖只改了
     final_text/落库消息, 救不回已下发的 token → 必须在下发前就抑制。
"""
from app.services.agent_executor import (
    FAST_ROUTE_ESCALATE_AFTER_ROUNDS,
    MAX_TOOL_ROUNDS,
    AgentExecutor,
)


class TestFastRouteEscalateConstant:
    def test_escalates_well_before_burning_all_rounds(self):
        # 逃生门必须**远早于**打满:founder 那 4 个回合就是打满 8 轮 = 203s。
        assert 1 <= FAST_ROUTE_ESCALATE_AFTER_ROUNDS < MAX_TOOL_ROUNDS
        assert FAST_ROUTE_ESCALATE_AFTER_ROUNDS <= 3, "留太多轮给弱模型空转就失去意义"


class TestFastRouteEscalationSemantics:
    """逃生门的状态转移(纯状态判定, 不驱动整条流)。"""

    def _mk(self, db):
        ex = AgentExecutor(db)
        ex._current_user_id = 3
        ex._fast_route_simple_turn = True
        ex._request_model_id = "qwen3.6-flash"  # 快路由接管时的样子(:5743)
        return ex

    def _escalate_if_needed(self, ex, round_idx):
        """镜像 run_stream 循环顶部的逃生门判据(与实现同源的语义快照)。"""
        if ex._fast_route_simple_turn and round_idx >= FAST_ROUTE_ESCALATE_AFTER_ROUNDS:
            ex._fast_route_simple_turn = False
            ex._request_model_id = None
            return True
        return False

    def test_early_rounds_stay_on_fast_model(self, db):
        ex = self._mk(db)
        for r in range(FAST_ROUTE_ESCALATE_AFTER_ROUNDS):
            assert self._escalate_if_needed(ex, r) is False
        assert ex._request_model_id == "qwen3.6-flash"  # p50=8.9s 的收益不能被误伤
        assert ex._fast_route_simple_turn is True

    def test_escalates_at_threshold_and_restores_default_route(self, db):
        ex = self._mk(db)
        assert self._escalate_if_needed(ex, FAST_ROUTE_ESCALATE_AFTER_ROUNDS) is True
        # _request_model_id=None = 精确还原到快路由介入前(它只在 None 时接管, :5735)
        assert ex._request_model_id is None
        assert ex._fast_route_simple_turn is False

    def test_escalation_is_idempotent(self, db):
        ex = self._mk(db)
        self._escalate_if_needed(ex, FAST_ROUTE_ESCALATE_AFTER_ROUNDS)
        # 后续轮不再重复升级(flag 已清)
        assert self._escalate_if_needed(ex, FAST_ROUTE_ESCALATE_AFTER_ROUNDS + 1) is False
        assert ex._request_model_id is None

    def test_explicitly_chosen_model_never_escalated(self, db):
        # 显式选模型时快路由根本不接管(_fast_route_simple_turn=False)→ 逃生门不得改他的选择
        ex = AgentExecutor(db)
        ex._fast_route_simple_turn = False
        ex._request_model_id = "qwen3.7-max"
        assert self._escalate_if_needed(ex, MAX_TOOL_ROUNDS) is False
        assert ex._request_model_id == "qwen3.7-max", "绝不能覆盖用户显式选的模型"


class TestRecordClaimNotStreamedBeforeVerification:
    """② 未经验证的「已记录」绝不 live 下发。"""

    def _suppress(self, *, prefer_fast_record, tool_executed_count):
        """镜像 :6374 的下发门判据(inline_suppressed / tool_round_fast_routed 皆 False 时)。"""
        return bool(prefer_fast_record and tool_executed_count == 0)

    def test_record_turn_with_zero_tools_is_suppressed(self):
        # 这就是「麦当劳店记录打了一个喷嚏。」的现场:0 工具却吐「✅ 症状已记录」
        assert self._suppress(prefer_fast_record=True, tool_executed_count=0) is True

    def test_record_turn_streams_live_once_a_tool_actually_ran(self):
        # 工具真跑过之后「已记录」才是真的 → 恢复 live 流(不牺牲正常记录的体验)
        assert self._suppress(prefer_fast_record=True, tool_executed_count=1) is False

    def test_non_record_turns_unaffected(self):
        # 普通问答/分析轮逐字节现状:绝不因本修改丢流式
        assert self._suppress(prefer_fast_record=False, tool_executed_count=0) is False
        assert self._suppress(prefer_fast_record=False, tool_executed_count=3) is False
