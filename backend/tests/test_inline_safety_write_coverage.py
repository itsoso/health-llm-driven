"""写后内联安全筛查的覆盖契约(scan #9: under-alarm 修复)。

写后 SafetyGuardian 重跑此前硬编码 `func_name == "health_record"`,漏掉同样写库的
health_manage(update/delete) 与 intervention_cycle → 「把血压改成 190/120」走 health_manage
不触发安全告警。现在门禁改用 _write_tool_completed(覆盖全部三个写工具、且只在确有写回执时触发)。

本测试锁定该 predicate 的覆盖面——它是内联安全门的判据。若有人把门禁退回
func_name=="health_record",或 _write_tool_completed 不再认 health_manage update,本测试红。
"""
import json

from app.services.agent_executor import _write_tool_completed


def _ok(id_=605, **extra):
    return json.dumps({"id": id_, "message": "已更新", **extra})


class TestInlineSafetyWriteCoverage:
    def test_health_record_write_completed(self):
        assert _write_tool_completed(
            "health_record",
            {"record_type": "blood_pressure", "data": {"systolic": 190, "diastolic": 120}},
            _ok(record_type="blood_pressure"),
        ) is True

    def test_health_manage_update_completed(self):
        # 关键回归: BP 改成危象值走 health_manage(update) 必须被内联安全门覆盖
        assert _write_tool_completed(
            "health_manage",
            {"operation": "update", "record_type": "blood_pressure", "record_id": 42},
            _ok(id_=42),
        ) is True

    def test_health_manage_delete_completed(self):
        assert _write_tool_completed(
            "health_manage",
            {"operation": "delete", "record_type": "blood_pressure", "record_id": 42},
            json.dumps({"id": 42, "message": "Record deleted successfully"}),
        ) is True

    def test_health_manage_list_is_not_a_write(self):
        # 只读 list 不应触发写后安全重跑(否则每次列记录都白跑 evaluate_safety)
        assert _write_tool_completed(
            "health_manage",
            {"operation": "list", "record_type": "blood_pressure"},
            json.dumps([{"id": 42}]),
        ) is False

    def test_intervention_cycle_start_completed(self):
        assert _write_tool_completed(
            "intervention_cycle",
            {"action": "start", "supplement": "omega-3"},
            _ok(id_=7),
        ) is True

    def test_soft_fail_result_not_completed(self):
        # 软失败(未找到 / prose)→ 不算写完成 → 不拼安全告警到失败回复上
        assert _write_tool_completed(
            "health_manage",
            {"operation": "update", "record_id": 42},
            "未找到该记录",
        ) is False

    def test_non_write_tool_not_completed(self):
        assert _write_tool_completed(
            "health_query", {"metric": "blood_pressure"}, json.dumps({"data": []})
        ) is False
