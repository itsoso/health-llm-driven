"""B 组 rank1+rank7:破坏性(删/改/撤销)+ 同步意图 → 强模型做工具决策。

生产实证(2026-07-14):删除/同步被降 qwen3.6-flash 后反复失败(0 工具 → 诚实守卫报错);
强模型 23:19 同句 status=complete。修 = 三条 fast 路径统一排除破坏性/同步意图。
"""
from app.services.agent_executor import (
    _needs_reliable_tool_model,
    _is_fast_eligible_turn,
    _destructive_or_sync_not_performed_message,
)


def test_needs_reliable_positive():
    for text in (
        "删除早餐 1",
        "删除重复的 保留第一条",
        "第一顿早餐记录有误 删除掉",
        "修改早餐:黑米白米粥一碗",
        "把午餐热量改成 378",
        "撤销刚才的记录",
        "帮我同步",
        "帮我同步 garmin",
        "同步Garmin数据",
        "同步 apple healthkit 数据",
        "sync my data",
        "拉取最新数据",
        "刷新一下数据",
    ):
        assert _needs_reliable_tool_model(text), f"应判定需强模型: {text!r}"


def test_needs_reliable_negative():
    # 普通记录/查询/空 → 不排除(仍可走 fast)
    for text in (
        "记录喝水300毫升",
        "早餐吃了燕麦粥",
        "今天喝了多少水",
        "列出我的饮水记录",
        "我睡眠分数",
        "记录做了10个俯卧撑",
        "",
        None,
    ):
        assert not _needs_reliable_tool_model(text), f"不应排除: {text!r}"


def test_needs_reliable_excludes_queries_and_advice():
    # 疑问句(查询,非破坏性命令)+ 分析语境 → 排除,防 backstop 误覆盖有效回答
    # 疑问标记(吗/有没有/什么/多少)+ 分析语境被排除;"了没有"这类口语变体不在共享疑问门
    # 覆盖内(方向安全:0 工具时仅过度保守诚实失败,永不谎报成功),不强行拓宽共享门。
    for text in (
        "我删除早餐了吗?",
        "同步了吗?",
        "有更新吗?",
        "综合分析我最近的睡眠趋势，我该怎么调整",
        "怎么更新我的训练方案",
    ):
        assert not _needs_reliable_tool_model(text), f"查询/分析不应判破坏性: {text!r}"


def test_fast_eligible_excludes_destructive_and_sync():
    # 破坏性/同步 → 非 fast-eligible(整轮不降 fast,留强模型)
    assert not _is_fast_eligible_turn("删除早餐 1", has_images=False, has_file=False)
    assert not _is_fast_eligible_turn("修改早餐内容", has_images=False, has_file=False)
    assert not _is_fast_eligible_turn("帮我同步 garmin", has_images=False, has_file=False)
    # 普通记录/查询仍 fast-eligible
    assert _is_fast_eligible_turn("记录喝水300ml", has_images=False, has_file=False)
    assert _is_fast_eligible_turn("今天喝了多少水", has_images=False, has_file=False)
    assert _is_fast_eligible_turn("列出我的饮水记录", has_images=False, has_file=False)


def test_fast_eligible_excludes_compound_write_and_analysis():
    # 复合回合既要可靠写入，又要完整分析，不能走只为记录优化的 fast 路由。
    assert not _is_fast_eligible_turn(
        "记录晚餐牛肉面，帮我分析今天的热量和蛋白质",
        has_images=False,
        has_file=False,
    )


def test_not_performed_message_is_honest():
    # 破坏性/同步 0 工具执行的兜底文案:不谎报已删/已改/已同步 + 明确数据无改动
    msg = _destructive_or_sync_not_performed_message("删除早餐 1")
    assert "没有任何改动" in msg
    for forbidden in ("已删除", "已删", "已修改", "已改", "已同步", "已经删除", "删除成功", "同步成功"):
        assert forbidden not in msg
