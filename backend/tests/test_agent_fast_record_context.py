"""fast-record 路由保留上一轮助手回合(修跟进式记录上下文丢失 bug)。

实测 bug:助手问「要不要记录鼻炎症状(打喷嚏/流鼻涕)?」用户答「记录症状」,fast-record 路由
只把最新一条用户消息发给模型 → 模型不知道记什么 → 重新泛问「什么症状?」。修=保留紧邻的上一条
assistant 回合做消歧上下文(其余长历史仍剔除,保持 compact)。
"""
from app.services.agent_executor import _build_fast_record_messages


def _roles(out):
    return [m["role"] for m in out]


def test_keeps_prior_assistant_turn_for_followup_record():
    messages = [
        {"role": "system", "content": "<long twin/kb system prompt>"},
        {"role": "user", "content": "我有点累"},
        {"role": "assistant", "content": "需要我帮你记录一下今天的鼻炎症状(打喷嚏/流鼻涕)吗?"},
        {"role": "user", "content": "记录症状"},
    ]
    out = _build_fast_record_messages(messages)
    # 稳态 [system, user](折进 user,不发裸 assistant —— 弱/代理模型友好)
    assert _roles(out) == ["system", "user"]
    # 上一轮助手的鼻炎上下文 + 最新用户回复都在最后那条 user 里(否则「记录症状」无从消歧)
    u = out[-1]["content"]
    assert "鼻炎" in u and "记录症状" in u
    # 仍 compact:不夹带「我有点累」那条早历史
    assert not any("有点累" in (m.get("content") or "") for m in out)


def test_pure_record_no_prior_assistant_stays_compact():
    # 直接「记录体重70kg」无上一轮助手 → user 内容原样,不夹带「[上一轮助手问我:]」
    messages = [
        {"role": "system", "content": "x"},
        {"role": "user", "content": "记录体重70kg"},
    ]
    out = _build_fast_record_messages(messages)
    assert _roles(out) == ["system", "user"]
    assert out[-1]["content"] == "记录体重70kg"
    assert "上一轮助手" not in out[-1]["content"]


def test_long_prior_assistant_truncated():
    long = "鼻炎相关说明" + "啰嗦" * 1000 + "要记录吗?"  # 以提问结尾 → 会折入
    messages = [
        {"role": "assistant", "content": long},
        {"role": "user", "content": "记录"},
    ]
    out = _build_fast_record_messages(messages)
    # 折进的助手上下文截断 ≤400(整条 user 含包装文字略长,但助手原文被截)
    assert "啰嗦" * 1000 not in out[-1]["content"]
    assert out[-1]["content"].count("啰嗦") <= 400


def test_non_question_prior_assistant_not_folded_no_context_bleed():
    """上一轮是分析/陈述(非提问)→ 不折进,防上下文串味。founder 2026-07-17 实测:
    刚分析完麦当劳那餐后记录喷嚏,被幻觉成「麦当劳店记录打了喷嚏」。"""
    messages = [
        {"role": "assistant", "content": "这一餐脂肪偏高,主要来自麦当劳的芝士和薯条,建议下一餐清淡些。"},
        {"role": "user", "content": "记录刚才打了一个喷嚏"},
    ]
    out = _build_fast_record_messages(messages)
    u = out[-1]["content"]
    assert "麦当劳" not in u and "上一轮助手" not in u   # 陈述不折进
    assert u == "记录刚才打了一个喷嚏"                    # 自足记录原样


def test_empty_assistant_turn_skipped():
    # 空/纯空白的上一轮 assistant 不算上下文(不折空包装)
    messages = [
        {"role": "assistant", "content": "   "},
        {"role": "user", "content": "记录血压120/80"},
    ]
    out = _build_fast_record_messages(messages)
    assert out[-1]["content"] == "记录血压120/80"
    assert "上一轮助手" not in out[-1]["content"]


def test_picks_most_recent_assistant_not_older():
    messages = [
        {"role": "assistant", "content": "旧助手回合-无关"},
        {"role": "user", "content": "嗯"},
        {"role": "assistant", "content": "要不要记录鼻炎症状?"},
        {"role": "user", "content": "记录"},
    ]
    out = _build_fast_record_messages(messages)
    u = out[-1]["content"]
    assert "鼻炎" in u and "无关" not in u
