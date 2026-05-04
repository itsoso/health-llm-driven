"""
测试跑后教练推送的文案提取函数 (W3).

_first_paragraph / _coach_oneliner 是纯文本处理, 不依赖 DB, 可单元级测试.
"""
from app.tasks.garmin_sync import _first_paragraph, _coach_oneliner


class TestFirstParagraph:
    def test_empty(self):
        assert _first_paragraph("") == ""
        assert _first_paragraph(None) == ""  # type: ignore

    def test_skips_markdown_heading(self):
        text = "## 本次训练总结\n\n这次 5km 跑步完成得不错。"
        assert "本次训练总结" not in _first_paragraph(text)
        assert "5km" in _first_paragraph(text)

    def test_strips_bold_and_list(self):
        text = "- **强度**: 本次训练保持在 Z2 区间。"
        out = _first_paragraph(text)
        assert "**" not in out
        assert not out.startswith("-")

    def test_max_len(self):
        long_text = "很长的段落" * 100
        assert len(_first_paragraph(long_text, max_len=50)) <= 50


class TestCoachOneliner:
    def test_empty(self):
        assert _coach_oneliner("") == ""

    def test_high_intensity_pattern(self):
        """强度过大 + 推荐休息 → 评价+action 拼成一句."""
        text = """### 心率区间分析
心率分布显示，本次训练中极限心率占比较高（59%），这表明训练强度过大，可能导致身体过度疲劳。

### 下次训练建议
- 建议时间间隔：至少休息1-2天
- 强度：建议降低强度"""
        out = _coach_oneliner(text)
        # 评价: 剥掉"心率分布显示，"冗余前缀
        assert not out.startswith("心率分布显示")
        assert "强度过大" in out
        # action: 剥掉"时间间隔："冒号前, 补"建议"前缀
        assert "建议至少休息1-2天" in out

    def test_normal_pattern(self):
        text = """## 心率区间分析
分布合理，主要集中在Z2区。

## 下次训练建议
建议保持每周3次有氧训练的节奏。
"""
        out = _coach_oneliner(text)
        assert "分布合理" in out
        assert "建议保持" in out

    def test_fallback_to_first_paragraph(self):
        """无结构化段落时降级到第一段."""
        text = "本次运动数据已分析完成。整体表现不错。"
        out = _coach_oneliner(text)
        assert out  # 非空
        assert "表现不错" in out or "分析完成" in out

    def test_max_len_80(self):
        text = """### 心率区间分析
""" + "非常非常长的评价内容" * 50 + """

### 下次训练建议
建议多休息。"""
        out = _coach_oneliner(text, max_len=80)
        assert len(out) <= 80
