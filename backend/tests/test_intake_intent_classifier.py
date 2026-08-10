import pytest

from app.services.intake_intent_classifier import classify_intake_intent


@pytest.mark.parametrize(("query", "kind"), [
    ("记录午餐吃了牛肉面", "diet"),
    ("午餐吃了煎牛肉能量碗 770kcal", "diet"),
    ("记录刚吃了替普瑞酮", "medication"),
    ("刚服用了替普瑞酮胶囊（施维舒）", "medication"),
    ("记录刚吃了奥美拉唑20mg", "medication"),
    ("吃了鱼油", "supplement"),
    ("吃了维生素D3", "supplement"),
    ("测试snack", "unknown"),
    ("喝了300ml水", "water"),
    ("删除这一餐", "diet_management"),
    ("我刚才不小心删除了", "diet_management"),
    ("午餐没有保存成功", "diet_management"),
    ("查询全天饮食和热量", "diet_management"),
    ("今天总热量是多少", "diet_management"),
    ("晨跑 30 分钟", "health_metric"),
    ("今天步数 5370", "health_metric"),
    ("体重 73.1kg 腰围 84cm", "health_metric"),
    ("昨晚睡了 6 小时", "health_metric"),
    ("血压 130/85 血糖 6.2", "health_metric"),
    ("刚吃了一个东西", "unknown"),
])
def test_classifies_common_intake_phrases(query, kind):
    result = classify_intake_intent(query)

    assert result.kind == kind


def test_extracts_basic_intake_slots():
    water = classify_intake_intent("记录我刚喝了 300ml 水")
    assert water.kind == "water"
    assert water.slots["amount_ml"] == 300

    medication = classify_intake_intent("记录刚吃了奥美拉唑20mg")
    assert medication.kind == "medication"
    assert medication.text == "奥美拉唑"
    assert medication.slots["dose"] == "20mg"

    diet = classify_intake_intent("记录晚餐吃了牛肉面 680kcal")
    assert diet.kind == "diet"
    assert diet.text == "牛肉面"
    assert diet.slots["meal_type"] == "dinner"


@pytest.mark.parametrize("query", [
    "阿司匹林 1片",
    "阿奇霉素 1片",
])
def test_known_medicines_with_bare_tablet_units_are_not_diet(query):
    result = classify_intake_intent(query)

    assert result.kind == "medication"


@pytest.mark.parametrize("query", [
    "华法林 1片",
    "warfarin 1片",
    "warfarin1片",
    "aspirin 1片",
    "aspirin1片",
    "azithromycin 1片",
    "azithromycin1片",
])
def test_named_medicines_keep_ascii_boundaries_around_dose_tokens(query):
    assert classify_intake_intent(query).kind == "medication"


@pytest.mark.parametrize("query", [
    "fish oil 2粒",
    "fish oil2粒",
    "omega-3 2粒",
    "omega-32粒",
    "magnesium 2粒",
    "magnesium2粒",
    "coq10 2粒",
    "coq102粒",
    "b12 2粒",
    "b122粒",
    "d3 2粒",
    "d32粒",
    "Ｄ３2粒",
    "ＣｏＱ１０2粒",
    "Ｂ１２2粒",
    "fish‑oil2粒",
    "fish–oil2粒",
    "fish​oil2粒",
    "d₃2粒",
    "coq₁₀2粒",
    "vitaminDfishoil",
    "vitamindandfishoil",
    "d3-fish-oil",
])
def test_named_supplements_keep_ascii_boundaries_around_dose_tokens(query):
    assert classify_intake_intent(query).kind == "supplement"


# ──── "打卡:X"/"记录 X" 前缀清洗(mac medication_draft 实锤) ────
def test_bare_checkin_prefix_with_colon_strips_verb():
    intent = classify_intake_intent("打卡：替普瑞酮胶囊")
    assert intent.kind == "medication"
    assert intent.text == "替普瑞酮胶囊"  # 曾整成 "打卡：替普瑞酮胶囊"


def test_bare_record_prefix_space_strips_verb():
    intent = classify_intake_intent("记录 维生素D")
    assert intent.text == "维生素D"


def test_consumption_verb_paths_unchanged():
    intent = classify_intake_intent("记录我今天吃了牛肉面")
    assert intent.kind == "diet"
    assert "牛肉面" in intent.text
    assert "记录" not in intent.text


# ──── 提问守卫(R4 边界 · founder 「午餐我吃了啥？」实锤) ────
# 查询回合绝不产出 intake 写草稿。摄入动词 + 疑问共现 → 非记录。
_RECORD_KINDS = {"diet", "medication", "supplement", "water"}


@pytest.mark.parametrize("query", [
    "午餐我吃了啥？",       # founder 精确复现
    "今天吃了什么",
    "午餐吃啥",
    "晚饭吃的啥？",
    "喝了多少水",
    "今天吃了几顿",
    "我吃了吗",
    "今天喝了吗？",
    "午餐吃什么",
    "补了几片？",
])
def test_interrogatives_never_classify_as_record(query):
    """摄入提问绝不落记录草稿——kind 不在 record 集合,理由为 intake_question。"""
    result = classify_intake_intent(query)
    assert result.kind not in _RECORD_KINDS, f"{query!r} 误判为 {result.kind}"
    assert result.kind == "unknown"
    assert result.reason == "intake_question"


@pytest.mark.parametrize(("query", "kind"), [
    ("记录午餐：牛肉面", "diet"),
    ("午餐吃了牛肉面", "diet"),
    ("刚吃了两个鸡蛋", "diet"),
    ("喝了500ml水", "water"),
    ("喝了一杯温水", "water"),
    ("补了维生素D", "supplement"),
])
def test_legit_records_still_classify(query, kind):
    """真实记录不被提问守卫误伤。"""
    result = classify_intake_intent(query)
    assert result.kind == kind, f"{query!r} 应为 {kind},实为 {result.kind}"


def test_bare_question_mark_without_intake_verb_not_swept():
    """裸问号(无摄入动词)不足以触发提问守卫——保持 PRECISE。"""
    result = classify_intake_intent("今天天气怎么样？")
    assert result.reason != "intake_question"


def test_pure_question_item_rejected_second_layer():
    """即使漏过顶层守卫,抽出的 item 若是纯疑问词也绝不成草稿。"""
    # 「午餐吃了啥」——item 抽取会拿到 "啥",item 级第二层拒绝
    result = classify_intake_intent("午餐吃了啥")
    assert result.kind == "unknown"
    assert result.text != "啥"  # 绝不带纯疑问 token 落草稿


@pytest.mark.parametrize("query", [
    # founder 2026-07-14 截图实锤:整句被误判成 diet 草稿
    "下次不吃那个牛肋骨面了，我感觉里边有一定的兴奋剂，罂粟啥的，我吃完晚上就睡不着觉了，昨晚2点才睡着",
    "下次不喝奶茶了",
    "别再吃火锅了太上火",
    "我不想吃晚饭了",
    # 以食物为病因的症状吐槽(无记录动词)
    "这碗面吃完我就拉肚子了",
])
def test_intake_reflection_and_complaint_never_draft(query):
    """否定/吐槽/症状反馈绝不落 intake 写草稿(不是记一餐)。"""
    result = classify_intake_intent(query)
    assert result.kind not in ("diet", "medication", "supplement", "water"), \
        f"{query!r} 是反思/吐槽,不应产出记录草稿,实为 {result.kind}"


@pytest.mark.parametrize(("query", "kind"), [
    # 真记录带轻微症状注释不能被误杀(有明确记录动词 "吃了")
    ("晚饭吃了牛肉面，吃完有点反酸", "diet"),
    ("晚餐吃了牛肋骨面", "diet"),
    ("记录午餐 鸡胸肉200g", "diet"),
    ("早上吃了替普瑞酮胶囊", "medication"),
])
def test_real_records_with_notes_survive_reflection_guard(query, kind):
    """否定/吐槽守卫不得误伤带注释的真实记录。"""
    result = classify_intake_intent(query)
    assert result.kind == kind, f"{query!r} 应为 {kind},实为 {result.kind}"
