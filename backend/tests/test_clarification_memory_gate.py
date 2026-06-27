"""R4 门控: voice/dialog 抽取 → memory_facts 写入路径不得对药物混杂指标下因果裁决.

镜像 tests/test_outcome_memory_loop.py::TestClinicianGatedMetricNoCausalVerdict 的意图,
但作用于另一条 *独立* 的 ungated producer —— clarification.extract-memory:

  对话抽取器可能产出 responds_to / does_not_respond_to (confidence 0.8) 的因果事实;
  若 subject/object 提及 ALT/尿酸/LDL/血压 等药物混杂生物标志, 这条 🟢 高可信 "X 有效"
  事实会喂回 chat LLM —— 而混杂的他汀/降尿酸药/降压药才可能是真因 (R4 违规).

修复: clarification 写库前对因果谓词跑 gate_text_for_clinician (单一事实源,
与 effect_estimator / crossover_verdict 共用门控集), 命中则降级为描述性 observed_change.

两类断言 (缺一不可):
  1. 提及 ALT/尿酸/LDL + responds_to → 持久化谓词 NOT 因果 (== observed_change)
  2. 关于 sleep/coffee/pillow + responds_to → 仍持久化 responds_to (非空泛门控)
"""
from __future__ import annotations

import pytest

from app.models.memory_fact import MemoryFact
from app.services.memory_dialog_extractor import ExtractedFact
from app.services.personal_models.intervention_priors import gate_text_for_clinician

from tests.conftest import create_authenticated_user

CAUSAL_PREDICATES = {"responds_to", "does_not_respond_to", "partially_responds_to"}


# ─────────────────────────── 单元: 自由文本门控矩阵 ───────────────────────────
class TestGateTextForClinician:
    @pytest.mark.parametrize(
        "text",
        [
            "戒了夜宵，转氨酶降了",           # ALT (中文)
            "停了某补剂后尿酸下来了",          # UA (中文)
            "我的胆固醇好像降了",              # TC/LDL (中文)
            "低密度脂蛋白下降",                # LDL (中文)
            "血压稳了",                        # BP (中文)
            "收缩压降了",                      # SBP (中文; 血压非其子串)
            "舒张压下来了",                    # DBP (中文)
            "载脂蛋白B改善",                   # ApoB (中文)
            "糖化血红蛋白改善",                # HbA1c (中文)
            "睾酮升高",                        # 激素 (中文)
            "user.labs.alt 下降",              # alt (英文 token)
            "ldl improved a lot",              # ldl (英文 token)
            "hba1c down to 5.4",               # hba1c (归一化子串)
            "user.health.uric_acid lower",     # uric_acid (长 code 子串)
            "blood pressure dropped",          # 空格英文 BP (归一化)
            "systolic came down",              # systolic (英文叙述)
            "diastolic improved",              # diastolic (英文叙述)
            "uric acid is lower now",          # 空格英文 UA (归一化)
            "apo b lower",                     # apo b → apob (归一化)
            "apolipoprotein B improved",       # 拼全 ApoB (英文叙述)
            "liver enzymes normalized",        # 肝酶英文叙述 (归一化)
            "total cholesterol down",          # 空格英文 TC (归一化)
        ],
    )
    def test_gated_metrics_match(self, text):
        assert gate_text_for_clinician(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "user.sleep.pillow_height 比平时高",   # 枕头/睡眠
            "我换了高枕头睡眠好多了",               # 睡眠
            "user.diet.coffee 戒了",               # 咖啡
            "我每周跑三次步",                       # 运动
            "user.exercise.frequency 增加",        # 运动
            "reduced salt intake",                 # salt ⊃ "alt" 不得误伤
            "I log it manually every day",         # manual ⊃ "ua" 不得误伤
            "I wear a watch to bed",               # watch ⊃ "tc" 不得误伤
            "resting hr 60 bpm",                   # bpm ⊃ "bp" 不得误伤 (短 keyword token 化)
            "draft4 of my plan",                   # draft4 ⊃ "ft4" 不得误伤
            "甘油三酯降了",                        # TG: 生活方式主导, 设计上不门控
            "",                                    # 空
            "心情好多了",                          # 情绪, 非生物标志
        ],
    )
    def test_lifestyle_and_false_substrings_not_matched(self, text):
        assert gate_text_for_clinician(text) is False


# ──────────────────── 集成: clarification 写库路径降级 ────────────────────
def _patch_extractor(monkeypatch, facts):
    """把 clarification 里引用的 async 抽取器替换为返回固定 facts 的桩."""

    async def _stub(user_text, *, context_hint=None, max_facts=5):
        return facts

    monkeypatch.setattr("app.api.clarification.extract_facts_from_dialog", _stub)


class TestClarificationDialogClinicianGate:
    def test_gated_metric_responds_to_demoted(self, client, db, monkeypatch):
        """转氨酶 + responds_to → 持久化为 observed_change, 绝不留因果谓词."""
        user, token = create_authenticated_user(db)
        _patch_extractor(
            monkeypatch,
            [
                ExtractedFact(
                    subject="user.diet.late_night_snack",
                    predicate="responds_to",
                    object_value="戒掉后转氨酶降了",
                    confidence=0.8,
                )
            ],
        )

        resp = client.post(
            "/api/v1/clarification/extract-memory",
            json={"user_turns": ["我戒了夜宵，转氨酶降了"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        rows = (
            db.query(MemoryFact)
            .filter(MemoryFact.user_id == user.id)
            .all()
        )
        assert len(rows) == 1
        fact = rows[0]
        assert fact.predicate not in CAUSAL_PREDICATES
        assert fact.predicate == "observed_change"
        # 观察本身保留 (object 不丢), 来源标注降级出处
        assert "转氨酶" in fact.object_value
        assert fact.sources[0].get("clinician_gated_demotion") == "responds_to"

    def test_uric_acid_does_not_respond_demoted(self, client, db, monkeypatch):
        """尿酸 + does_not_respond_to (否定因果) 同样降级."""
        user, token = create_authenticated_user(db)
        _patch_extractor(
            monkeypatch,
            [
                ExtractedFact(
                    subject="user.supplement.unknown",
                    predicate="does_not_respond_to",
                    object_value="停了之后尿酸没变化",
                    confidence=0.8,
                )
            ],
        )

        resp = client.post(
            "/api/v1/clarification/extract-memory",
            json={"user_turns": ["停了某补剂尿酸也没降"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        fact = db.query(MemoryFact).filter(MemoryFact.user_id == user.id).one()
        assert fact.predicate == "observed_change"

    def test_lifestyle_responds_to_preserved(self, client, db, monkeypatch):
        """非空泛护栏: 枕头/睡眠 + responds_to → 仍持久化 responds_to."""
        user, token = create_authenticated_user(db)
        _patch_extractor(
            monkeypatch,
            [
                ExtractedFact(
                    subject="user.sleep.pillow_height",
                    predicate="responds_to",
                    object_value="换高枕头后睡眠改善",
                    confidence=0.8,
                )
            ],
        )

        resp = client.post(
            "/api/v1/clarification/extract-memory",
            json={"user_turns": ["我换了高枕头，睡得好多了"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        fact = db.query(MemoryFact).filter(MemoryFact.user_id == user.id).one()
        assert fact.predicate == "responds_to"
        assert fact.sources[0].get("clinician_gated_demotion") is None

    def test_non_causal_predicate_untouched(self, client, db, monkeypatch):
        """is_value 等非因果谓词不受门控影响 (即便提及生物标志)."""
        user, token = create_authenticated_user(db)
        _patch_extractor(
            monkeypatch,
            [
                ExtractedFact(
                    subject="user.labs.ldl",
                    predicate="is_value",
                    object_value="3.1 mmol/L",
                    confidence=0.8,
                )
            ],
        )

        resp = client.post(
            "/api/v1/clarification/extract-memory",
            json={"user_turns": ["我的LDL是3.1"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        fact = db.query(MemoryFact).filter(MemoryFact.user_id == user.id).one()
        assert fact.predicate == "is_value"
