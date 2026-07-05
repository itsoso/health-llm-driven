"""加餐双卡 bug 回归 — 已记录本轮不再发同 kind 草稿 + 草稿接营养表预填。

founder 截图实锤(2026-07-05): 「加餐已记录 40kcal」下面又冒
「加餐·待确认 ——kcal」空草稿; 点确认会把油桃写两次。
双修: ① recorded_intake_kinds 从 executor 已附卡推断本轮已写入 kind,
build_cards 压制同 kind *_draft; ② 草稿真发时(无本轮记录)单品+克数
接 food_nutrition_lookup 预填, 拿不准留空(诚实 ——)。
"""
from app.models.food_nutrition import FoodItem, FoodNutrient
from app.services.inline_cards import (
    _estimate_nutrition_from_table,
    build_cards,
    recorded_intake_kinds,
)


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


class TestDraftSuppression:
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
        db.add(FoodItem(food_id="youtao", canonical_name="油桃", aliases=[], source="test"))
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
