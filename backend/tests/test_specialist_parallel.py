"""Phase 2.1: 测试 Specialist 并行执行"""
import time
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.orchestrator.orchestrator import _run_specialists
from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin, TwinMeta


def _twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


class FakeSpecialist:
    """可配置的假 specialist，用于测试调度逻辑。"""

    def __init__(self, name: str, category: str = "test", sleep_sec: float = 0, raw: dict = None):
        self.name = name
        self.category = category
        self._sleep = sleep_sec
        self._raw = raw or {}

    def applies_to(self, intent, twin) -> bool:
        return True

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        if self._sleep:
            time.sleep(self._sleep)
        return SpecialistFinding(
            specialist_name=self.name,
            category=self.category,
            summary=f"{self.name} done",
            findings=[],
            raw={**self._raw, "ctx_snapshot": dict(context)},
            ms_elapsed=0,
        )


class FakeRecoveryCoach:
    """模拟 Recovery Coach — 写入 readiness_zone 到 context。"""

    name = "recovery_coach"
    category = "recovery"

    def applies_to(self, intent, twin) -> bool:
        return True

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        time.sleep(0.05)  # 模拟一点计算延迟
        return SpecialistFinding(
            specialist_name=self.name,
            category=self.category,
            summary="readiness zone: green",
            findings=[],
            raw={"zone": "green", "score": 85},
            ms_elapsed=50,
        )


class FakeMovementCoach:
    """模拟 Movement Coach — 读取 context 中的 readiness_zone。"""

    name = "movement_coach"
    category = "movement"

    def applies_to(self, intent, twin) -> bool:
        return True

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        zone = context.get("readiness_zone", "unknown")
        return SpecialistFinding(
            specialist_name=self.name,
            category=self.category,
            summary=f"movement prescription (zone={zone})",
            findings=[],
            raw={"readiness_zone_used": zone},
            ms_elapsed=0,
        )


class FailingSpecialist:
    """总是抛异常的 specialist。"""

    name = "failing_specialist"
    category = "test"

    def applies_to(self, intent, twin) -> bool:
        return True

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        raise RuntimeError("模拟失败")


# ─────────────────── 测试用例 ───────────────────


class TestParallelSpecialistExecution:

    def test_basic_parallel_execution(self):
        """多个独立 specialist 应并行执行"""
        specialists = [
            FakeSpecialist("sp_a", sleep_sec=0.1),
            FakeSpecialist("sp_b", sleep_sec=0.1),
            FakeSpecialist("sp_c", sleep_sec=0.1),
        ]
        twin = _twin()
        t0 = time.monotonic()
        findings = _run_specialists(twin, specialists, {"query": "test"})
        elapsed = time.monotonic() - t0

        assert len(findings) == 3
        # 串行需要 0.3s，并行应 <0.25s
        assert elapsed < 0.25, f"took {elapsed:.2f}s, expected <0.25s (parallel)"

    def test_recovery_coach_runs_first(self):
        """Recovery Coach 应在其他 specialist 之前执行"""
        recovery = FakeRecoveryCoach()
        movement = FakeMovementCoach()
        other = FakeSpecialist("other_sp")

        # 注意：故意把 recovery_coach 放在列表中间
        specialists = [other, recovery, movement]
        twin = _twin()
        findings = _run_specialists(twin, specialists, {"query": "test"})

        assert len(findings) == 3
        # Recovery Coach 的 finding 应排在第一位
        assert findings[0].specialist_name == "recovery_coach"

    def test_movement_coach_receives_readiness_zone(self):
        """Movement Coach 应能读到 Recovery Coach 写入的 readiness_zone"""
        recovery = FakeRecoveryCoach()
        movement = FakeMovementCoach()
        specialists = [recovery, movement]

        twin = _twin()
        findings = _run_specialists(twin, specialists, {"query": "test"})

        # 找到 movement_coach 的 finding
        mc_finding = next(f for f in findings if f.specialist_name == "movement_coach")
        assert mc_finding.raw["readiness_zone_used"] == "green"

    def test_without_recovery_coach(self):
        """没有 Recovery Coach 时应正常并行执行"""
        specialists = [
            FakeSpecialist("sp_a"),
            FakeMovementCoach(),
            FakeSpecialist("sp_c"),
        ]
        twin = _twin()
        findings = _run_specialists(twin, specialists, {"query": "test"})

        assert len(findings) == 3
        mc_finding = next(f for f in findings if f.specialist_name == "movement_coach")
        assert mc_finding.raw["readiness_zone_used"] == "unknown"

    def test_failing_specialist_doesnt_block_others(self):
        """单个 specialist 失败不应阻塞其他"""
        specialists = [
            FakeSpecialist("sp_ok_1"),
            FailingSpecialist(),
            FakeSpecialist("sp_ok_2"),
        ]
        twin = _twin()
        findings = _run_specialists(twin, specialists, {"query": "test"})

        # 失败的不在结果中，成功的 2 个在
        assert len(findings) == 2
        names = [f.specialist_name for f in findings]
        assert "sp_ok_1" in names
        assert "sp_ok_2" in names

    def test_findings_order_preserved(self):
        """输出应保持注册顺序（Recovery Coach 在前，其余按原始顺序）"""
        recovery = FakeRecoveryCoach()
        specialists = [
            FakeSpecialist("alpha", sleep_sec=0.05),
            recovery,
            FakeSpecialist("beta"),
            FakeSpecialist("gamma"),
        ]
        twin = _twin()
        findings = _run_specialists(twin, specialists, {})

        names = [f.specialist_name for f in findings]
        # recovery_coach 排第一，其余按原始列表中的顺序
        assert names[0] == "recovery_coach"
        rest = names[1:]
        assert rest == ["alpha", "beta", "gamma"]

    def test_empty_specialist_list(self):
        """空列表应返回空结果"""
        findings = _run_specialists(_twin(), [], {"query": "test"})
        assert findings == []

    def test_only_recovery_coach(self):
        """只有 Recovery Coach 时应正常工作"""
        findings = _run_specialists(_twin(), [FakeRecoveryCoach()], {"query": "test"})
        assert len(findings) == 1
        assert findings[0].specialist_name == "recovery_coach"

    def test_context_not_mutated(self):
        """原始 context 不应被修改"""
        original_ctx = {"query": "test", "extra": "data"}
        ctx_copy = dict(original_ctx)
        specialists = [FakeRecoveryCoach(), FakeSpecialist("sp")]

        _run_specialists(_twin(), specialists, original_ctx)
        assert original_ctx == ctx_copy

    def test_timings_kwarg_collects_per_specialist_ms(self):
        """perf (2026-05-28): 传 timings={} 时应填入完整 perf breakdown."""
        # 无 movement → recovery 并入并行池
        specialists = [
            FakeRecoveryCoach(),
            FakeSpecialist("alpha", sleep_sec=0.03),
            FakeSpecialist("beta", sleep_sec=0.01),
        ]
        timings: Dict[str, Any] = {}
        findings = _run_specialists(
            _twin(), specialists, {"query": "test"}, timings=timings,
        )
        assert len(findings) == 3
        # 字段齐全
        assert set(timings.keys()) == {
            "recovery_ms", "parallel_wall_ms", "per_specialist_ms",
            "total_ms", "failed", "timed_out", "recovery_inlined",
        }
        # 每个 specialist 都有耗时
        assert set(timings["per_specialist_ms"].keys()) == {"recovery_coach", "alpha", "beta"}
        for sp_ms in timings["per_specialist_ms"].values():
            assert sp_ms >= 0
        # recovery 被并入池 → recovery_ms (Phase 1 同步时长) 为 0
        assert timings["recovery_ms"] == 0
        assert timings["recovery_inlined"] is True
        # parallel_wall_ms 接近最慢的 specialist (recovery=50ms 因 sleep), 不是串行和
        assert timings["parallel_wall_ms"] < 150  # 4 workers 全并发, 留余量
        # 无失败 / 超时
        assert timings["failed"] == []
        assert timings["timed_out"] == []

    def test_recovery_synced_when_movement_present(self):
        """movement_coach 在列表时, recovery 必须同步先跑, 才能传 readiness_zone."""
        timings: Dict[str, Any] = {}
        findings = _run_specialists(
            _twin(),
            [FakeRecoveryCoach(), FakeMovementCoach(), FakeSpecialist("other")],
            {"query": "test"},
            timings=timings,
        )
        assert len(findings) == 3
        # recovery 应有非 0 同步耗时
        assert timings["recovery_ms"] > 0
        assert timings["recovery_inlined"] is False
        # movement_coach 应读到 readiness_zone='green'
        mc = next(f for f in findings if f.specialist_name == "movement_coach")
        assert mc.raw["readiness_zone_used"] == "green"

    def test_recovery_inlined_without_movement_saves_serial_wait(self):
        """无 movement_coach 时, recovery 进并行池, 不再消耗串行等待时间."""
        timings: Dict[str, Any] = {}
        # 故意让 recovery 慢 (sleep 0.05), 其它快 (0.01)
        # 旧逻辑: 0.05 sync + 0.01 parallel = 60ms
        # 新逻辑: max(0.05, 0.01) = 50ms parallel
        _run_specialists(
            _twin(),
            [FakeRecoveryCoach(), FakeSpecialist("a", sleep_sec=0.01)],
            {"q": "x"},
            timings=timings,
        )
        assert timings["recovery_inlined"] is True
        # parallel_wall_ms 接近 50ms (recovery), 不是 60ms (串行)
        assert timings["parallel_wall_ms"] < 100

    def test_timings_records_failed_specialist(self):
        """异常的 specialist 也要记入 failed 列表 + per_specialist_ms."""
        class FailingSp:
            name = "broken"
            category = "test"
            def applies_to(self, intent, twin): return True
            def run(self, twin, ctx): raise RuntimeError("boom")

        timings: Dict[str, Any] = {}
        _run_specialists(
            _twin(),
            [FakeRecoveryCoach(), FailingSp()],
            {"query": "test"},
            timings=timings,
        )
        assert "broken" in timings["failed"]
        assert "broken" in timings["per_specialist_ms"]

    def test_timings_kwarg_optional(self):
        """不传 timings 时函数照常工作 (向后兼容)."""
        findings = _run_specialists(_twin(), [FakeRecoveryCoach(), FakeSpecialist("a")], {"q": "x"})
        assert len(findings) == 2

    def test_parallel_pool_timeout_doesnt_block_other_findings(self):
        """超时的 specialist 进 timed_out + failed[], 其余 finding 正常返回."""
        import app.orchestrator.orchestrator as orch_mod

        class StuckSpecialist:
            name = "stuck"
            category = "test"
            def applies_to(self, intent, twin): return True
            def run(self, twin, ctx):
                time.sleep(2.0)  # 远超下面 patch 的 0.1s 超时
                return SpecialistFinding(
                    specialist_name=self.name, category=self.category,
                    summary="ok", findings=[], raw={}, ms_elapsed=2000,
                )

        # 临时把整体超时拉到 100ms 以便测试快速完成
        original_timeout = orch_mod._SPECIALIST_PARALLEL_TIMEOUT_S
        orch_mod._SPECIALIST_PARALLEL_TIMEOUT_S = 0.1
        try:
            timings: Dict[str, Any] = {}
            findings = _run_specialists(
                _twin(),
                [FakeSpecialist("fast_a", sleep_sec=0), StuckSpecialist(), FakeSpecialist("fast_b", sleep_sec=0)],
                {"q": "x"},
                timings=timings,
            )
        finally:
            orch_mod._SPECIALIST_PARALLEL_TIMEOUT_S = original_timeout

        # 卡住的 specialist 进 timed_out + failed
        assert "stuck" in timings["timed_out"]
        assert "stuck" in timings["failed"]
        # 其余 2 个 finding 正常返回
        names = {f.specialist_name for f in findings}
        assert names == {"fast_a", "fast_b"}
