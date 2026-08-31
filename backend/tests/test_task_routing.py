# -*- coding: utf-8 -*-
"""任务分级模型路由(Next Horizon Tier 4 / RFC 方向十)回归。

钉:tier→speed_tier 选模型;flag 关=零行为变更(不走路由);flag 开+匹配=用 tier 模型。
"""
from unittest.mock import MagicMock, patch

import pytest


def test_staged_response_ships_off_until_canary_is_authorized():
    from app.config import Settings

    assert Settings.model_fields["staged_response_mode"].default == "off"


@pytest.mark.parametrize(
    "message,has_attachments,expected",
    [
        ("查一下我今天走了多少步", False, "casual"),
        ("昨晚睡得怎样，今天是否适合锻炼？", False, "balanced"),
        ("深入分析我的恢复状态", False, "balanced"),
        ("分析我最近一周的饮食结构", False, "balanced"),
        ("结合我的用药和肝功能判断今天能否锻炼", False, "high_stakes"),
        ("胃溃疡应该怎么吃", False, "high_stakes"),
        ("补剂怎么吃", False, "high_stakes"),
        ("我膝盖痛今天能运动吗", False, "high_stakes"),
        ("我运动时心慌气短，今天还能跑吗", False, "high_stakes"),
        ("吃这个药要注意什么", False, "high_stakes"),
        ("停用这个药可以吗", False, "high_stakes"),
        ("把这个药加倍可以吗", False, "high_stakes"),
        ("孕妇能运动吗", False, "high_stakes"),
        ("哺乳期能运动吗", False, "high_stakes"),
        ("排便有鲜血怎么办", False, "high_stakes"),
        ("我刚才突然看不清", False, "high_stakes"),
        ("阿司匹林怎么吃", False, "high_stakes"),
        ("二甲双胍要停吗", False, "high_stakes"),
        ("保健品可以加倍吗", False, "high_stakes"),
        ("这个能多吃一颗吗", False, "high_stakes"),
        ("继续按这个量吃吗", False, "high_stakes"),
        ("和那个一起吃呢", False, "high_stakes"),
        ("那今晚还吃吗", False, "high_stakes"),
        ("那我照旧吃就行？", False, "high_stakes"),
        ("心跳突然很乱还能运动吗", False, "high_stakes"),
        ("正在喂奶能跑步吗", False, "high_stakes"),
        ("胸口像被石头压住，今天还能练吗", False, "high_stakes"),
        ("吐出来像咖啡渣", False, "high_stakes"),
        ("大便像柏油一样", False, "high_stakes"),
        ("喘不上来还能运动吗", False, "high_stakes"),
        ("心跳漏拍还能跑吗", False, "high_stakes"),
        ("突然一只手没劲还能走吗", False, "high_stakes"),
        ("视线突然模糊还能开车吗", False, "high_stakes"),
        ("心脏像被攥住还能跑吗", False, "high_stakes"),
        ("喘不过来还能运动吗", False, "high_stakes"),
        ("透不过气还能训练吗", False, "high_stakes"),
        ("眼前发黑还能开车吗", False, "high_stakes"),
        ("说话大舌头", False, "high_stakes"),
        ("一边脸耷拉了", False, "high_stakes"),
        ("胸口被压着还能跑吗", False, "high_stakes"),
        ("心口堵得慌还能练吗", False, "high_stakes"),
        ("呼吸怎么也吸不进来", False, "high_stakes"),
        ("吸不进气还能训练吗", False, "high_stakes"),
        ("胸口像有人坐着还能跑步吗", False, "high_stakes"),
        ("一侧胳膊抬不起来", False, "high_stakes"),
        ("左手突然使不上劲", False, "high_stakes"),
        ("看东西突然糊了", False, "high_stakes"),
        ("胸口像压了块东西", False, "high_stakes"),
        ("我现在胸痛而且呼吸困难，怎么办", False, "high_stakes"),
        ("帮我看看这个", True, "high_stakes"),
        ("解读这份体检报告", True, "high_stakes"),
        ("分析这份病理报告", True, "high_stakes"),
        ("记录照片里的这餐", True, "balanced"),
        ("记录午餐吃了富含维生素和矿物质的沙拉", False, "casual"),
        ("记录晚餐吃了高血糖指数的米饭", False, "casual"),
        ("记录晚餐吃了药膳鸡", False, "casual"),
        ("午餐吃了富含维生素C的橙子", False, "casual"),
        ("早餐吃了高血糖指数的白米饭", False, "casual"),
        ("午餐吃了药膳鸡汤", False, "casual"),
        ("早餐喝了维生素饮料一瓶", False, "casual"),
        ("早餐吃了两片面包", False, "casual"),
        ("我们今天一起运动吗", False, "casual"),
        ("今晚吃什么", False, "casual"),
        ("今晚吃了火锅", False, "casual"),
        ("记录我吃了富含维生素C的橙子", False, "casual"),
        ("刚吃了维生素C含量高的橙子", False, "casual"),
        ("喝了一瓶维生素饮料", False, "casual"),
        ("吃了药膳鸡汤", False, "casual"),
        ("记录一个富含矿物质的沙拉", False, "casual"),
        ("继续一起训练吗", False, "casual"),
        ("这个面包片热量多少", False, "casual"),
        ("那颗苹果还能吃吗", False, "casual"),
        ("记录我吃了这个", False, "high_stakes"),
        ("记录今晚吃了两片", False, "high_stakes"),
        ("记下吃了那一颗", False, "high_stakes"),
        ("打卡吃了这个", False, "high_stakes"),
        ("记录吃了半颗", False, "high_stakes"),
        ("午餐吃了富含维生素C的橙子和鱼油", False, "high_stakes"),
        ("记一下吞了两片", False, "high_stakes"),
        ("记录刚吞了半颗", False, "high_stakes"),
        ("记录打了一针", False, "high_stakes"),
        ("记录刚用了两粒", False, "high_stakes"),
        ("记录我吃了它", False, "high_stakes"),
        ("记下嚼了半片", False, "high_stakes"),
        ("饭后吃这个可以吗", False, "high_stakes"),
        ("记录刚咽了一粒", False, "high_stakes"),
        ("记录刚滴了两滴", False, "high_stakes"),
        ("记录吸入了两揿哮喘气雾剂", False, "high_stakes"),
        ("记录注射了10单位", False, "high_stakes"),
        ("记录注射了8U", False, "high_stakes"),
        ("记一下打了0.5ml", False, "high_stakes"),
        ("记录吃了矿物质一粒", False, "high_stakes"),
        ("记录吃了富含维生素C一粒", False, "high_stakes"),
        ("记录吃了高血糖指数一片", False, "high_stakes"),
        ("午餐吃了一粒矿物质补充剂和一个苹果", False, "high_stakes"),
        ("午餐吃了一粒钙片和一个苹果", False, "high_stakes"),
        ("午餐吃了维生素C一粒和橙子", False, "high_stakes"),
        ("午餐吃了一粒维C和一个苹果", False, "high_stakes"),
        ("午餐吃了一粒VC和一个苹果", False, "high_stakes"),
        ("午餐吃了一粒铁片和一个苹果", False, "high_stakes"),
        ("午餐吃了一粒锌片和一个苹果", False, "high_stakes"),
        ("午餐吃了一粒镁片和一个苹果", False, "high_stakes"),
        ("午餐吃了一粒维C配一个苹果", False, "high_stakes"),
        ("午餐吃了一粒VC搭配一个苹果", False, "high_stakes"),
        ("午餐吃了一粒铁片与一个苹果", False, "high_stakes"),
        ("午餐吃了一粒锌片跟一个苹果", False, "high_stakes"),
        ("午餐吃了一粒镁片加一个苹果", False, "high_stakes"),
        ("午餐吃了维C一粒苹果一个", False, "high_stakes"),
        ("午餐维C一粒苹果一个", False, "high_stakes"),
        ("午餐吃了鸡肉一片和一个苹果", False, "casual"),
        ("早餐吃了两片全麦面包", False, "casual"),
        ("午餐吃了苹果和一片面包", False, "casual"),
        ("记录用了鼻喷剂两下", False, "high_stakes"),
        ("运动前用了鼻喷剂两下", False, "high_stakes"),
        ("记录用了气雾剂两下", False, "high_stakes"),
        ("记录喷了两下哮喘喷雾", False, "high_stakes"),
        ("记录用了哮喘吸入器两下", False, "high_stakes"),
        ("记录用了吸入器两下", False, "high_stakes"),
        ("记录用了定量吸入器两下", False, "high_stakes"),
        ("记录吸了两口吸入器", False, "high_stakes"),
        ("记录用了鼻喷两下", False, "high_stakes"),
        ("继续用这个训练计划吗", False, "casual"),
        ("这个健身器械怎么用", False, "balanced"),
        ("这个动作怎么用", False, "balanced"),
        ("这个贴纸怎么贴", False, "balanced"),
        ("这个喷壶怎么喷", False, "balanced"),
        ("这个面膜怎么贴", False, "balanced"),
        ("记录我吃了富含维生素C的猕猴桃", False, "casual"),
        ("刚吃了富含矿物质的西兰花", False, "casual"),
        ("吃了药膳排骨", False, "casual"),
    ],
)
def test_answer_task_tier_is_conservative_and_domain_aware(
    message, has_attachments, expected
):
    from app.services.llm.task_routing import classify_answer_task_tier

    assert classify_answer_task_tier(
        message,
        has_attachments=has_attachments,
    ) == expected


def test_user_facing_answer_tiers_never_pick_fast_model():
    from app.services.llm.model_registry import get_model
    from app.services.llm.task_routing import (
        classify_answer_task_tier,
        pick_model_id_by_tier,
    )

    for message in (
        "昨晚睡得怎样，今天是否适合锻炼？",
        "结合我的用药和肝功能判断今天能否锻炼",
    ):
        tier = classify_answer_task_tier(message, has_attachments=False)
        model_id = pick_model_id_by_tier(tier, only_available=False)
        assert model_id is not None
        assert get_model(model_id).speed_tier != "fast"


def test_pick_model_id_by_tier():
    from app.services.llm.task_routing import pick_model_id_by_tier
    # only_available=False:不依赖 env,只验"按 speed_tier 选到对应档模型"
    hs = pick_model_id_by_tier("high_stakes", only_available=False)
    casual = pick_model_id_by_tier("casual", only_available=False)
    bal = pick_model_id_by_tier("balanced", only_available=False)
    assert hs and casual and bal
    from app.services.llm.model_registry import get_model
    assert get_model(hs).speed_tier == "reasoning"
    # casual 是用户可见回答档，安全地板禁止落到 fast；简单查/写的
    # 快路由 AgentExecutor 的可验证确定性路径单独承担。
    assert get_model(casual).speed_tier in ("balanced", "reasoning")
    assert get_model(bal).speed_tier == "balanced"
    assert pick_model_id_by_tier("nonsense", only_available=False) is None
    assert pick_model_id_by_tier(None) is None


def test_tier_for_intent_wiring():
    """成本路由接线:orchestrator 按 intent 类别定 task_tier(高风险→reasoning)。"""
    from app.orchestrator.orchestrator import _tier_for_intent

    class _I:
        def __init__(self, c): self.categories = c
    assert _tier_for_intent(_I(["safety"])) == "high_stakes"
    assert _tier_for_intent(_I(["longevity"])) == "high_stakes"
    assert _tier_for_intent(_I(["recovery"])) == "balanced"
    assert _tier_for_intent(_I(["fuel", "movement"])) == "balanced"
    # 安全不变量:合成路径永不降到 casual(=fast),general/空也地板到 balanced。
    assert _tier_for_intent(_I(["general"])) == "balanced"
    assert _tier_for_intent(_I([])) == "balanced"


def test_routing_taken_when_flag_on():
    """flag 开 + tier 匹配 → 用 tier 模型(不落到用户偏好/默认)。"""
    from app.config import settings
    from app.services.llm import factory

    sentinel = object()
    with patch.object(settings, "task_tiered_routing", True), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier", return_value="m-x"), \
         patch("app.services.llm.model_registry.get_model", return_value=MagicMock()), \
         patch.object(factory, "_create_from_entry", return_value="raw"), \
         patch("app.services.llm.usage_tracker.wrap_provider", side_effect=lambda x: x), \
         patch("app.services.llm.pii_scrub.wrap_provider_pii_scrub", return_value=sentinel):
        out = factory.create_provider_for_user(1, MagicMock(), task_tier="high_stakes")
    assert out is sentinel


def test_routing_skipped_when_flag_off():
    """flag 关 → 不走路由(zero behavior change),回退既有逻辑。"""
    from app.config import settings
    from app.services.llm import factory

    pick = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # 无 user 偏好
    with patch.object(settings, "task_tiered_routing", False), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier", pick), \
         patch.object(factory, "get_llm_provider", return_value="default-provider"):
        out = factory.create_provider_for_user(1, db, task_tier="high_stakes")
    pick.assert_not_called()        # flag 关 → 根本不调用路由
    assert out == "default-provider"


# ─────────────────────────────────────────────────────────────
# 内部工具路由 pick_* 必须能看到 chat_selectable=False 的最快可靠工具模型
# (qwen3.6-flash)。回归 bug:pick_* 曾漏传 include_non_chat=True →
# 只能落到次快的 deepseek-v4-flash (~7s vs qwen3.6-flash evaled ~1-2.6s),
# 白白丢一半 tool-round 快路由收益。
# ─────────────────────────────────────────────────────────────

def test_pick_fast_returns_qwen_flash_in_real_registry():
    """真实注册表 (env-agnostic):最快可靠工具模型 = qwen3.6-flash,
    虽然它 chat_selectable=False (不进用户答案 picker),内部快路由仍必须选到它。"""
    from app.services.llm.model_registry import pick_fast_tool_model_id, get_model
    fast_id = pick_fast_tool_model_id(only_available=False)
    assert fast_id == "qwen3.6-flash", f"期望 qwen3.6-flash, 实际 {fast_id}"
    assert get_model(fast_id).speed_tier == "fast"


def test_pick_reliable_near_fast_returns_qwen_flash_in_real_registry():
    """pick_reliable_tool_model_id(near='fast') 也应命中 qwen3.6-flash
    (注册顺序把它排在 deepseek-v4-flash 之前)。"""
    from app.services.llm.model_registry import pick_reliable_tool_model_id
    mid = pick_reliable_tool_model_id(near_speed_tier="fast", only_available=False)
    assert mid == "qwen3.6-flash", f"期望 qwen3.6-flash, 实际 {mid}"


def test_pick_reliable_can_leave_failed_provider_domain():
    """供应商额度/故障后必须能排除整个 provider，而不是只换 model id。"""
    from app.services.llm.model_registry import get_model, pick_reliable_tool_model_id

    mid = pick_reliable_tool_model_id(
        only_available=False,
        exclude_providers={"tokenplan"},
    )

    assert mid is not None
    assert get_model(mid).provider != "tokenplan"


def test_qwen_flash_registered_before_deepseek_flash():
    """注册顺序不变量:qwen3.6-flash 必须排在 deepseek-v4-flash 前,
    否则"最快档第一个"会退回 deepseek-v4-flash。"""
    from app.services.llm.model_registry import MODELS
    ids = [m.id for m in MODELS]
    assert ids.index("qwen3.6-flash") < ids.index("deepseek-v4-flash")


def test_pick_reliable_fast_returns_qwen_flash_with_env(monkeypatch):
    """env-present 路径 (only_available=True + tokenplan key):同样返回 qwen3.6-flash。"""
    from app.config import settings
    from app.services.llm.model_registry import (
        pick_fast_tool_model_id,
        pick_reliable_tool_model_id,
    )
    monkeypatch.setattr(settings, "tokenplan_api_key", "test-key-present")
    assert pick_fast_tool_model_id(only_available=True) == "qwen3.6-flash"
    assert pick_reliable_tool_model_id(
        near_speed_tier="fast", only_available=True
    ) == "qwen3.6-flash"


def test_pick_functions_never_return_non_text_model(monkeypatch):
    """对抗:即便某图片生成模型被误标 reliable_tool_calling=True 且是 fast 档,
    capability 护栏 (text_generation) 也绝不让它被工具路由选中。"""
    from app.services.llm import model_registry as reg
    fake = [
        # 图片生成模型 — 故意误标 reliable + fast, 但只有 image_generation 能力
        reg.ModelEntry(
            "img-x", "img", "tokenplan", "img", "fast",
            capabilities=("image_generation",),
            chat_selectable=False, reliable_tool_calling=True,
        ),
        # 合法的文本快模型 — 唯一应被选中的
        reg.ModelEntry(
            "txt-fast", "t", "tokenplan", "t", "fast",
            capabilities=("text_generation",),
            chat_selectable=False, reliable_tool_calling=True,
        ),
    ]
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False, include_non_chat=False: list(fake),
    )
    assert reg.pick_fast_tool_model_id(only_available=False) == "txt-fast"
    assert reg.pick_reliable_tool_model_id(
        near_speed_tier="fast", only_available=False
    ) == "txt-fast"


def test_non_chat_models_stay_hidden_from_default_list_models():
    """用户 picker 不变量未被本次 fix 破坏:list_models() 默认输出仍不含
    chat_selectable=False 的模型 (qwen3.6-flash / 图片生成模型)。
    include_non_chat 只在内部 pick_* 里生效,不泄漏到用户可选目录。"""
    from app.services.llm.model_registry import list_models
    default_ids = {m.id for m in list_models()}
    assert "qwen3.6-flash" not in default_ids
    assert "qwen-image-2.0" not in default_ids
    # 但内部工具路由能看到 (include_non_chat=True)
    internal_ids = {m.id for m in list_models(include_non_chat=True)}
    assert "qwen3.6-flash" in internal_ids
