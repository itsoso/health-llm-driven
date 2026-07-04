"""证据卡元 claim 排除 — prod 实锤回归(疲劳/HRV 对话弹「血压·医学边界」卡)。

根因链: 建议 chip 文本含「建议」→ 万金油词锚进元 claim 标题
「健康建议必须保留医学边界」→ 治理元声明占据用户可见 claim 席位。
修复: ① 元句/元实体硬排除出证据卡(卡底免责行才是 boundary 的展示位);
② 建议/健康/医学 进相关性停用词(只收紧准入)。Prompt 侧不受影响。
"""
from app.services.system_knowledge_service import (
    _KB_RELEVANCE_STOP_TERMS,
    _drop_meta_boundary_claims,
    _is_meta_boundary_claim,
)


def _claim(title, entity_id="bp", doc_id="claim:x"):
    return {"title": title, "entity_id": entity_id, "doc_id": doc_id}


class TestMetaBoundaryExclusion:
    def test_meta_sentence_excluded(self):
        # prod 实锤那条
        assert _is_meta_boundary_claim(_claim("医学边界:健康建议必须保留医学边界")) is True
        # P0-5 retitle 后带实体前缀的同族
        assert _is_meta_boundary_claim(
            _claim("代谢健康:健康建议必须保留医学边界", "metabolic-health")
        ) is True

    def test_meta_entity_excluded(self):
        assert _is_meta_boundary_claim(_claim("随便什么", "medical-boundary")) is True

    def test_substantive_boundary_claims_survive(self):
        # CBT-I 是正经临床 claim, title 含"医学边界"字样但不含元句 → 保留
        assert _is_meta_boundary_claim(
            _claim("失眠优先进入 CBT-I 和睡眠医学边界", "sleep-regularity")
        ) is False
        # 基因安全边界类(ALDH2×硝酸甘油)绝不误伤
        assert _is_meta_boundary_claim(
            _claim("ALDH2 缺陷者硝酸甘油应答边界", "aldh2")
        ) is False

    def test_drop_keeps_order_and_filters(self):
        claims = [
            _claim("血压管理先识别高钠来源"),
            _claim("医学边界:健康建议必须保留医学边界", "medical-boundary"),
            _claim("失眠优先进入 CBT-I 和睡眠医学边界", "sleep-regularity"),
        ]
        out = _drop_meta_boundary_claims(claims)
        assert [c["title"] for c in out] == [
            "血压管理先识别高钠来源",
            "失眠优先进入 CBT-I 和睡眠医学边界",
        ]


class TestGenericTermsStopped:
    def test_advice_vocabulary_in_stop_terms(self):
        # 万金油词必须在停用词里, 否则 advice 消息全员锚中元 claim
        for term in ("建议", "健康", "医学"):
            assert term in _KB_RELEVANCE_STOP_TERMS
