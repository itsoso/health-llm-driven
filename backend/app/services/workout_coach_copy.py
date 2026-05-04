"""
教练文案生成 — 从长篇 LLM aggregation 蒸一句或一段可用文本.

used by:
  - app.tasks.garmin_sync.auto_analyze_workout   → push body (20-80 字)
  - app.api.workout                              → /me/{id}/voice-coach 返回 TTS 用短稿
"""
from __future__ import annotations

import re


def first_paragraph(text: str, max_len: int = 160) -> str:
    """aggregation 第一段正文 (跳过 markdown 标题行), 截到 max_len."""
    if not text:
        return ""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    for p in paragraphs:
        first_line = p.splitlines()[0].strip()
        if first_line.startswith("#"):
            rest = "\n".join(p.splitlines()[1:]).strip()
            if rest:
                return rest[:max_len]
            continue
        clean = p.replace("**", "").lstrip("-*•· ").strip()
        if clean:
            return clean[:max_len]
    return text.strip()[:max_len]


def coach_oneliner(aggregation: str, max_len: int = 80) -> str:
    """
    把 aggregation 压成一句教练点评 (20-60 字, 推送 body / TTS 短稿用).

    规则 (不调 LLM, 省 token):
      1. 找"心率区间分析"段的判断句 (强度过大/分布合理/比例较高 等)
      2. 找"下次训练建议"段的 action 句
      3. 剥冗余前缀 + markdown 符号
      4. 拼"评价；建议" 一句. 没抓到就 fallback 到 first_paragraph
    """
    if not aggregation:
        return ""

    # 按 markdown 标题切段
    sections: dict[str, str] = {}
    current_key = ""
    buf: list[str] = []
    for line in aggregation.splitlines():
        stripped = line.strip()
        m = re.match(r"^#{1,6}\s*(?:\d+[.、]\s*)?(.+?)\s*$", stripped)
        if not m:
            m = re.match(r"^\*\*\s*(?:\d+[.、]\s*)?(.+?)\s*\*\*\s*$", stripped)
        if m:
            if current_key:
                sections[current_key] = "\n".join(buf).strip()
            current_key = m.group(1)
            buf = []
        else:
            buf.append(line)
    if current_key:
        sections[current_key] = "\n".join(buf).strip()

    def _find_section(*keywords: str) -> str:
        for k, v in sections.items():
            if any(kw in k for kw in keywords):
                return v
        return ""

    hr_section = _find_section("心率区间", "心率分析")
    next_section = _find_section("下次训练建议", "下次建议", "下一次")

    evaluation = ""
    if hr_section:
        for sent in re.split(r"[。！？\n]", hr_section):
            sent = sent.strip().lstrip("-*•· ").replace("**", "")
            if not sent:
                continue
            if any(w in sent for w in ("强度过大", "强度偏大", "强度过高", "强度过小", "强度偏低",
                                       "不合理", "分布合理", "比例较高", "占比较高", "表现不错",
                                       "过度疲劳", "有氧耐力", "恢复跑")):
                evaluation = sent
                break
        for prefix in ("心率分布显示，", "心率分布显示,", "心率数据显示，", "数据显示，",
                       "从心率区间分布来看，", "从数据来看，", "综合来看，", "整体来看，",
                       "根据心率数据，"):
            if evaluation.startswith(prefix):
                evaluation = evaluation[len(prefix):]
                break

    action = ""
    if next_section:
        for sent in re.split(r"[。！？\n]", next_section):
            sent = sent.strip().lstrip("-*•· ").replace("**", "")
            if not sent:
                continue
            if sent.startswith(("建议", "下次", "可选择")) or ("建议" in sent and len(sent) < 30):
                action = sent
                break
        if "：" in action:
            action = action.split("：", 1)[1].strip()
        elif ":" in action:
            action = action.split(":", 1)[1].strip()
        if action and not action.startswith(("建议", "下次", "可选择", "保持")):
            action = "建议" + action

    if evaluation and action:
        out = f"{evaluation}；{action}"
    elif evaluation:
        out = evaluation
    elif action:
        out = action
    else:
        out = first_paragraph(aggregation, max_len=max_len)

    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out


def workout_voice_script(
    activity: str,
    distance_meters: float | None,
    duration_seconds: int | None,
    aggregation: str,
    max_len: int = 200,
) -> str:
    """
    跑后"听一下"按钮用 — 比 oneliner 长一点, 有完整起承转合 (150-200 字).

    结构:
      开场 (一句数据回顾) + coach_oneliner (评价+建议) + 结束语

    Example:
      '本次跑步 2.6 公里, 用时 18 分钟。极限心率占比较高, 强度过大;
       建议至少休息 1-2 天。好好恢复。'
    """
    bits = []
    if distance_meters and distance_meters > 0:
        bits.append(f"{distance_meters / 1000:.1f} 公里")
    if duration_seconds and duration_seconds > 0:
        mins = duration_seconds // 60
        bits.append(f"用时 {mins} 分钟")
    lead = f"本次{activity}" + (" " + "，".join(bits) if bits else "") + "。"

    body = coach_oneliner(aggregation, max_len=max_len - len(lead) - 10)
    if not body:
        body = "整体表现平稳，保持这个节奏。"
    if not body.endswith(("。", "！", "？", "…")):
        body += "。"

    out = lead + body
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out
