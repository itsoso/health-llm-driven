"""
Tests for memory_reference_detector heuristic.

Marker phrases must trigger detection. Generic Twin-data descriptions must NOT.
False positives erode the metric (we'd overestimate "memory used").
"""
import pytest

from app.services.memory_reference_detector import (
    detect_memory_reference,
    find_memory_references,
)


# ─────────────── True cases ───────────────

@pytest.mark.parametrize("text", [
    # 时间锚定
    "你之前提到鼻炎发作时会咳嗽。",
    "上次我们讨论过这点。",
    "上周你睡眠也不好。",
    "前几天的 HRV 数据显示同样趋势。",
    "几天前你血氧也低过。",
    # 历史/记忆
    "记得你对花生过敏。",
    "根据你的历史,这种情况通常 3 天恢复。",
    "根据您之前的偏好,推荐温和方案。",
    "按你之前的反馈,我们调整剂量。",
    "历史上你 LDL 一直偏高。",
    "你曾经反馈过类似症状。",
    # 持续性
    "你一直对乳制品敏感。",
    "你向来习惯晨练。",
    "平时你睡眠质量不错,这次例外。",
    # 对话回指
    "你提到最近压力大。",
    "你提到过这个药副作用。",
    "你说过不喜欢有刺激性气味的产品。",
    "你之前提及鼻塞问题。",
])
def test_positive_cases_detected(text):
    assert detect_memory_reference(text), f"应识别为引用 memory: {text!r}"


# ─────────────── False cases (Twin data 描述, 非记忆引用) ───────────────

@pytest.mark.parametrize("text", [
    "今天 HRV 48,睡眠分 89,恢复达标。",
    "睡前清洗鼻腔有助于改善 SpO2。",
    "建议明天早睡,持续观察一周。",
    "ALDH2 杂合可能影响乙醛代谢。",
    "建议补充维生素 D,每日 2000 IU。",
    "心率 49,压力 22,均在正常范围。",
    "建议查 LDL、HbA1c、CRP。",
    # "之前" 单字在某些非回忆语境也可能出现 — 我们的 pattern 是 "之前提到/说过/讲过",
    # 所以下面这些应该不被误判:
    "建议睡前刷牙。",
    "用药前先咨询医生。",
])
def test_negative_cases_not_detected(text):
    assert not detect_memory_reference(text), f"不应识别为引用 memory: {text!r}"


# ─────────────── Edge ───────────────

def test_empty_text():
    assert detect_memory_reference("") is False
    assert detect_memory_reference(None) is False


def test_find_returns_matches():
    text = "你之前提到鼻炎,记得你对花生过敏。"
    matches = find_memory_references(text)
    assert len(matches) >= 2  # 两个 marker


def test_find_empty_returns_empty_list():
    assert find_memory_references("") == []
    assert find_memory_references(None) == []


def test_full_paragraph_with_one_marker():
    """实际 LLM 输出片段, 应能从复合段里识别出引用."""
    text = (
        "你昨晚睡得总体不错。睡眠七个半小时,睡眠分八十九分,恢复是达标的。"
        "记得你之前反馈过夜间鼻塞,今晚建议睡前做一次鼻腔清洗再入睡。"
    )
    assert detect_memory_reference(text) is True


def test_full_paragraph_no_marker_not_false_positive():
    """纯 Twin 数据描述不应被误判."""
    text = (
        "你昨晚睡得总体不错。睡眠七个半小时,睡眠分八十九分,恢复是达标的。"
        "要留意的是血氧最低到百分之八十三,虽说 ODI 一点二不高,"
        "但今晚建议睡前做一次鼻腔清洗再入睡。"
    )
    assert detect_memory_reference(text) is False
