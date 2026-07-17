"""GenUI medication_list 卡 — builder + render 单测。

覆盖:契约信封(v 是整数 1)、fail-open 降级、safety alert 存在性(加层不减层)、
缺字段优雅降级、fence 可被 JSON 还原、R4 纪律(卡里没有推断/建议派生字段)。
"""
import json

import pytest

from app.services.genui import (
    build_medication_list,
    render_medication_list_block,
    GENUI_MEDICATION_LIST_CAP,
    MEDICATION_LIST_TYPE,
)

# 契约字段集(与移动端 MedicationListCard parse* 一字对齐)。测试**硬钉**这两个集合:
# 后端多吐一个键 = 移动端静默丢弃/漂移;少吐一个 = 卡片渲染空洞。
_DATA_KEYS = {"medications", "total", "safety_alert_count"}
# 刻意**不含** has_safety_alert:safety_alerts 是用户级的, 逐药标记=编造因果(见 builder docstring)。
_MED_KEYS = {
    "name", "dosage", "frequency", "timing_label",
    "category", "purpose", "start_date",
}


def _med(name="沃克（伏诺拉生）", **kw):
    """镜像 app/api/medication.py:_serialize_medication 的真实出参形状。"""
    body = {
        "id": 1,
        "user_id": 1,
        "name": name,
        "dosage": "20mg",
        "frequency": "每日2次",
        "times_per_day": 2,
        "reminder_times": ["08:00", "20:00"],
        "timing_relation": "before",
        "meal_anchor": "meal",
        "timing_label": "餐前",
        "category": "胃药",
        "purpose": "胃窦溃疡",
        "side_effects": None,
        "interactions": None,
        "start_date": "2026-07-01",
        "end_date": None,
        "is_active": True,
        "notes": None,
        "created_at": "2026-07-01 08:00:00",
    }
    body.update(kw)
    return body


class TestEnvelope:
    def test_builds_descriptor_with_integer_version(self):
        desc = build_medication_list([_med()])
        assert desc is not None
        assert desc["type"] == MEDICATION_LIST_TYPE == "medication_list"
        # 跨端契约铁律:v 必须是**整数** 1(移动端 fence parser 校验 v === 1)。
        # bool 是 int 的子类,显式排除,否则 True 能混过 isinstance 检查。
        assert desc["v"] == 1
        assert isinstance(desc["v"], int) and not isinstance(desc["v"], bool)

    def test_cap_token_is_the_string_form(self):
        assert GENUI_MEDICATION_LIST_CAP == "genui-medication-list-v1"

    def test_passes_through_recorded_fields_verbatim(self):
        desc = build_medication_list([_med()])
        m = desc["data"]["medications"][0]
        assert m == {
            "name": "沃克（伏诺拉生）",
            "dosage": "20mg",
            "frequency": "每日2次",
            "timing_label": "餐前",
            "category": "胃药",
            "purpose": "胃窦溃疡",
            "start_date": "2026-07-01",
        }

    def test_total_matches_rendered_rows(self):
        desc = build_medication_list([_med(name="A"), _med(name="B"), _med(name="C")])
        assert desc["data"]["total"] == 3
        assert len(desc["data"]["medications"]) == 3

    def test_does_not_truncate_long_medication_lists(self):
        """漏一味药 = 用户问"我在吃什么"却少给一味(且可能恰是带告警那味)。"""
        desc = build_medication_list([_med(name=f"药{i}") for i in range(20)])
        assert desc["data"]["total"] == 20
        assert len(desc["data"]["medications"]) == 20


class TestFailOpen:
    @pytest.mark.parametrize("bad", [
        None, [], {}, "", "not json", 0, {"medications": []},
        [{"id": 1}],                       # 全部无 name
        [{"name": ""}, {"name": "   "}],   # name 空/纯空白
        ["纯字符串", 42, None],             # 非 dict 条目
    ])
    def test_returns_none_so_caller_falls_back_to_prose(self, bad):
        assert build_medication_list(bad) is None

    def test_skips_nameless_items_but_keeps_the_rest(self):
        desc = build_medication_list([_med(name="有名字"), {"id": 2}, _med(name="")])
        assert desc["data"]["total"] == 1
        assert desc["data"]["medications"][0]["name"] == "有名字"


class TestSafetyAlerts:
    def test_never_attributes_alerts_to_individual_drugs(self):
        """契约承重墙:safety_alerts 是**用户级**的(同一份挂到每味药)。

        `_medication_safety_alerts(db, user_id)` 按整个方案跑 PGx/DDI/DSI,
        `list_my_medications` 把同一份挂到每个条目 → 逐药标记会把一条 DDI 归因到无关的药
        (真实复现:一条 dsi.ppi_b12 让铝碳酸镁也带上)。故卡里**绝不**出现逐药字段。
        这条红 = 有人把 has_safety_alert 加回来了 = 卡片开始编造因果。
        """
        alerts = [{"rule_id": "dsi.ppi_b12", "severity": 3, "title": "长期抑酸"}]
        desc = build_medication_list([
            _med(name="沃克（伏诺拉生）", safety_alerts=alerts),
            _med(name="铝碳酸镁", safety_alerts=alerts),  # 服务端就是这么挂的(同一份)
        ])
        for m in desc["data"]["medications"]:
            assert "has_safety_alert" not in m, "逐药归因字段不得存在"

    def test_user_level_alert_counted_once_not_per_drug(self):
        """去重:3 味药 + 1 条 DDI → 1(而非错报成 3)。"""
        alerts = [{"rule_id": "ddi.warfarin_nsaid", "severity": 4, "title": "相互作用"}]
        desc = build_medication_list([
            _med(name="华法林", safety_alerts=alerts),
            _med(name="布洛芬", safety_alerts=alerts),
            _med(name="维生素C", safety_alerts=alerts),
        ])
        assert desc["data"]["safety_alert_count"] == 1
        assert desc["data"]["total"] == 3

    def test_distinct_rules_counted_separately(self):
        alerts = [{"rule_id": "ddi.a"}, {"rule_id": "dsi.b"}]
        desc = build_medication_list([_med(name="A", safety_alerts=alerts)])
        assert desc["data"]["safety_alert_count"] == 2

    def test_missing_safety_alerts_key_is_not_an_alert(self):
        desc = build_medication_list([_med()])
        assert desc["data"]["safety_alert_count"] == 0

    def test_never_under_alarms_on_odd_alert_payloads(self):
        """加层不减层:非列表但 truthy 的畸形 safety_alerts 仍记 1 —— 绝不吞成 0。"""
        desc = build_medication_list([_med(name="怪数据", safety_alerts="有告警")])
        assert desc["data"]["safety_alert_count"] == 1

    def test_alert_bodies_never_leak_into_the_card(self):
        """卡只给存在性标记;告警正文留给安全面板/散文,不在此二次改写成弱化版。"""
        desc = build_medication_list([_med(
            name="华法林",
            safety_alerts=[{"rule_id": "ddi.x", "message": "出血风险", "action": "立即就医"}],
        )])
        blob = json.dumps(desc, ensure_ascii=False)
        assert "出血风险" not in blob
        assert "立即就医" not in blob


class TestMissingFields:
    def test_only_name_yields_nulls_not_crashes(self):
        desc = build_medication_list([{"name": "某药"}])
        m = desc["data"]["medications"][0]
        assert m["name"] == "某药"
        for k in ("dosage", "frequency", "timing_label", "category", "purpose", "start_date"):
            assert m[k] is None, k
        assert desc["data"]["total"] == 1

    def test_explicit_nulls_stay_null_not_the_string_none(self):
        """str(None) == 'None' 会把缺值渲染成用户可见的字面 "None"。"""
        desc = build_medication_list([_med(dosage=None, purpose=None, timing_label=None)])
        m = desc["data"]["medications"][0]
        assert m["dosage"] is None and m["purpose"] is None and m["timing_label"] is None
        assert "None" not in json.dumps(desc, ensure_ascii=False)

    def test_blank_strings_normalize_to_null(self):
        desc = build_medication_list([_med(dosage="   ", category="")])
        m = desc["data"]["medications"][0]
        assert m["dosage"] is None and m["category"] is None

    def test_whitespace_is_stripped(self):
        desc = build_medication_list([_med(name="  奥美拉唑  ", dosage=" 20mg ")])
        m = desc["data"]["medications"][0]
        assert m["name"] == "奥美拉唑" and m["dosage"] == "20mg"


class TestRender:
    def test_fence_round_trips_through_json(self):
        desc = build_medication_list([_med()])
        block = render_medication_list_block(desc)
        assert block.startswith("```reva-ui\n") and block.endswith("\n```")
        payload = block[len("```reva-ui\n"):-len("\n```")]
        assert json.loads(payload) == desc

    def test_chinese_is_not_escaped(self):
        block = render_medication_list_block(build_medication_list([_med()]))
        assert "沃克（伏诺拉生）" in block


class TestR4Discipline:
    """卡片只如实呈现用户登记的记录 —— 零医学推断、零建议、零编造剂量。"""

    def test_data_carries_exactly_the_contract_keys(self):
        """没有 observations/advice/assessment 之类的派生 —— 用药领域没有可安全派生的阈值。"""
        desc = build_medication_list([_med(name="A", safety_alerts=[{"rule_id": "x"}])])
        assert set(desc["data"].keys()) == _DATA_KEYS
        assert set(desc.keys()) == {"type", "v", "data"}
        for m in desc["data"]["medications"]:
            assert set(m.keys()) == _MED_KEYS

    def test_no_derived_keys_appear_under_any_input(self):
        desc = build_medication_list([_med(), _med(name="B", dosage=None)])
        blob = json.dumps(desc, ensure_ascii=False)
        for forbidden in ("observation", "advice", "recommend", "assessment", "severity", "action"):
            assert forbidden not in blob.lower(), forbidden

    def test_builder_never_invents_a_dosage(self):
        """没记剂量就是没记 —— 绝不补默认值(编造剂量 = 最危险的幻觉面)。"""
        desc = build_medication_list([{"name": "某药"}])
        assert desc["data"]["medications"][0]["dosage"] is None

    def test_dosage_string_is_not_parsed_or_rewritten(self):
        """原样透传:不解析数字、不换算单位、不规范化写法。"""
        for raw in ("20mg", "半片", "1粒 (10mg)", "20 mg bid", "遵医嘱"):
            desc = build_medication_list([_med(dosage=raw)])
            assert desc["data"]["medications"][0]["dosage"] == raw
