"""加餐双卡 bug 回归 — 已记录本轮不再发同 kind 草稿 + 草稿接营养表预填。

founder 截图实锤(2026-07-05): 「加餐已记录 40kcal」下面又冒
「加餐·待确认 ——kcal」空草稿; 点确认会把油桃写两次。
双修: ① recorded_intake_kinds 从 executor 已附卡推断本轮已写入 kind,
build_cards 压制同 kind *_draft; ② 草稿真发时(无本轮记录)单品+克数
接 food_nutrition_lookup 预填, 拿不准留空(诚实 ——)。
"""
import pytest

from app.models.food_nutrition import FoodItem, FoodNutrient
from app.services import inline_cards
from app.services.inline_cards import (
    _build_diet_draft,
    _estimate_nutrition_from_table,
    build_cards,
    recorded_intake_kinds,
)
from app.api.agent import _merge_card_descriptors, _pending_intake_suppressions


def _record_card(kind: str):
    return {"type": "record", "data": {"type": kind, "detail": "已记录"}}


def _quality_card(domain: str):
    return {"type": "record_quality", "data": {"domain": domain, "title": "加餐已记录"}}


class TestRecordedIntakeKinds:
    def test_record_card_diet(self):
        assert recorded_intake_kinds([_record_card("diet")]) == {"diet"}

    def test_quality_card_domain(self):
        assert recorded_intake_kinds([_quality_card("diet")]) == {"diet"}

    def test_snack_food_aliases_map_to_diet(self):
        assert recorded_intake_kinds([_record_card("snack")]) == {"diet"}
        assert recorded_intake_kinds([_record_card("food")]) == {"diet"}

    def test_medication_and_supplement(self):
        kinds = recorded_intake_kinds(
            [_record_card("medication")], [_record_card("supplement")]
        )
        assert kinds == {"medication", "supplement"}

    def test_non_list_and_garbage_safe(self):
        assert recorded_intake_kinds(None, "x", [{"type": "vitals"}], [None]) == set()


class TestRepresentedIntakeKinds:
    @pytest.mark.parametrize(
        "data",
        [
            {"recorded": True, "record_id": 830},
            {"photo_draft_token": "draft-token"},
        ],
    )
    def test_contextual_diet_card_suppresses_legacy_query_draft(self, db, data):
        existing = [{"type": "diet_draft", "data": data}]

        suppress = inline_cards.represented_intake_kinds(existing)
        cards = build_cards(
            db,
            1,
            "记录晚餐牛肉面 500 kcal",
            suppress_intake_kinds=suppress,
        )

        assert suppress == {"diet"}
        assert not any(card["type"] == "diet_draft" for card in cards)

    def test_nested_cards_group_occupies_each_intake_family(self):
        cards = [{
            "type": "cards_group",
            "data": {
                "cards": [
                    {"type": "diet_draft", "data": {"photo_draft_token": "diet"}},
                    {"type": "medication_draft", "data": {"items": []}},
                    {"type": "supplement_draft", "data": {"items": []}},
                ],
            },
        }]

        assert inline_cards.represented_intake_kinds(cards) == {
            "diet",
            "medication",
            "supplement",
        }

    def test_detection_does_not_collapse_distinct_diet_records(self, db):
        existing = [
            {
                "type": "record_quality",
                "data": {"domain": "diet", "record_id": 101, "title": "早餐已记录"},
            },
            {
                "type": "record_quality",
                "data": {"domain": "diet", "record_id": 202, "title": "午餐已记录"},
            },
        ]

        generated = build_cards(
            db,
            1,
            "记录晚餐牛肉面 500 kcal",
            suppress_intake_kinds=inline_cards.represented_intake_kinds(existing),
        )
        merged = _merge_card_descriptors(existing, generated)

        assert [card["data"]["record_id"] for card in merged] == [101, 202]
        assert not any(card["type"] == "diet_draft" for card in generated)


class TestDraftSuppression:
    def test_server_owned_medication_batch_suppresses_legacy_medication_draft(self):
        assert _pending_intake_suppressions({
            "pending_write_intent_kinds": ["medication_intake_batch"],
        }) == {"medication"}

    def test_unrelated_pending_write_intent_does_not_over_suppress(self):
        assert _pending_intake_suppressions({
            "pending_write_intent_kinds": ["checkup_reminder"],
        }) == set()

    def test_diet_draft_suppressed_when_diet_recorded(self, db):
        q = "加餐吃了一个油桃"
        with_draft = build_cards(db, 1, q)
        assert any(c["type"] == "diet_draft" for c in with_draft), "前提: 该 query 本会出草稿"
        suppressed = build_cards(db, 1, q, suppress_intake_kinds={"diet"})
        assert not any(c["type"] == "diet_draft" for c in suppressed)

    def test_other_kind_not_over_suppressed(self, db):
        q = "加餐吃了一个油桃"
        cards = build_cards(db, 1, q, suppress_intake_kinds={"medication"})
        assert any(c["type"] == "diet_draft" for c in cards)


class TestNutritionTablePrefill:
    def _seed(self, db):
        db.add(FoodItem(
            food_id="youtao",
            canonical_name="油桃",
            aliases=[],
            calibration_names=["油桃"],
            source="test",
        ))
        db.add(FoodNutrient(
            food_id="youtao", kcal_per_100g=50.0, protein_g_per_100g=1.25,
            carbs_g_per_100g=12.5, fat_g_per_100g=0.0, fiber_g_per_100g=1.25,
            source="test",
        ))
        db.commit()

    def test_single_item_with_grams_prefills(self, db):
        self._seed(db)
        est = _estimate_nutrition_from_table(db, "油桃 约80g")
        assert est is not None
        assert est["calories"] == 40.0
        assert est["protein"] == 1.0

    def test_no_grams_stays_empty(self, db):
        self._seed(db)
        assert _estimate_nutrition_from_table(db, "油桃 记录下来 作为加餐") is None

    def test_multi_item_stays_empty(self, db):
        self._seed(db)
        assert _estimate_nutrition_from_table(db, "油桃 80g + 苹果 100g") is None

    def test_unknown_food_stays_empty(self, db):
        assert _estimate_nutrition_from_table(db, "神秘果 约80g") is None

    def test_draft_gets_prefill_and_072_confidence(self, db):
        self._seed(db)
        cards = build_cards(db, 1, "加餐吃了油桃 约80g 帮我记一下")
        draft = next((c for c in cards if c["type"] == "diet_draft"), None)
        assert draft is not None
        assert draft["data"].get("calories") == 40.0
        assert draft["data"].get("confidence") == 0.72


class TestInterrogativeNoDraft:
    """提问回合绝不产出 intake 写草稿(R4 · founder 「午餐我吃了啥？」实锤)。

    对照 TestDraftSuppression 的记录型 query「加餐吃了一个油桃」本会出草稿;
    此处的提问必须相反 —— 不出任何 diet_draft。
    """

    def test_founder_interrogative_builds_no_diet_draft(self, db):
        assert _build_diet_draft(db, 1, "午餐我吃了啥？") is None

    def test_founder_interrogative_no_diet_draft_card(self, db):
        cards = build_cards(db, 1, "午餐我吃了啥？")
        assert not any(c["type"] == "diet_draft" for c in cards), \
            "提问回合冒出了 diet_draft 草稿卡(R4 越界)"

    def test_interrogative_battery_no_intake_draft_cards(self, db):
        for q in ["今天吃了什么", "晚饭吃的啥？", "喝了多少水", "我吃了吗"]:
            cards = build_cards(db, 1, q)
            leaked = [c["type"] for c in cards
                      if c["type"] in ("diet_draft", "medication_draft", "supplement_draft")]
            assert not leaked, f"{q!r} 冒出写草稿: {leaked}"

    def test_legit_record_still_builds_draft_control(self, db):
        # 对照组:记录型 query 仍出草稿,证明守卫没把记录一并杀掉
        assert _build_diet_draft(db, 1, "加餐吃了一个油桃") is not None


class TestUiCopyNoDietDraft:
    def test_food_card_ui_copy_builds_no_diet_draft(self, db):
        assert _build_diet_draft(db, 1, "和午餐食品营养卡") is None

    def test_food_card_ui_copy_no_diet_draft_card(self, db):
        cards = build_cards(db, 1, "和午餐食品营养卡")
        assert not any(c["type"] == "diet_draft" for c in cards)
