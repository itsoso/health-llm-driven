import json
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest


def _make_user(db):
    from app.models.user import User

    user = User(
        username=f"opener_{uuid.uuid4().hex[:8]}",
        email=f"opener_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Opener Test",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_action_card_opener_done_reply_records_adherence_and_grades_due_card(db):
    from app.models.action_card import ActionCard
    from app.models.weight import WeightRecord
    from app.services.opener_quick_reply import apply_opener_quick_reply_context

    now = datetime.now(timezone.utc)
    db.add(WeightRecord(user_id=3, record_date=date.today(), weight=71.2))
    card = ActionCard(
        user_id=3,
        title="AI 预测：7 天体重保持 ≤ 71.3kg",
        content="...",
        status="active",
        metric_key="weight",
        baseline_value="72.0",
        target_value="≤71.3",
        check_back_date=now - timedelta(minutes=5),
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    note = apply_opener_quick_reply_context(
        db,
        user_id=3,
        message="做到了 ✅",
        extra_context=json.dumps({
            "entry": "conversation_opener_quick_reply",
            "user_reply": "做到了 ✅",
            "opener_text": "今天就是「AI 预测：7 天体重保持 ≤ 71.3kg」的检验日，做到了吗？",
            "source": "action_card_due",
            "source_id": card.id,
            "action_card_id": card.id,
        }, ensure_ascii=False),
        now=now,
    )

    db.refresh(card)
    assert note is not None
    assert "记录 self_reported adherence=70%" in note
    assert card.adherence_kind == "self_reported"
    assert card.adherence_confidence == 70
    assert card.graded_at is not None
    assert card.actual_value == "71.2"
    assert card.accuracy_score == 70


def test_action_card_opener_missed_reply_records_zero_adherence_without_grading_early(db):
    from app.models.action_card import ActionCard
    from app.services.opener_quick_reply import apply_opener_quick_reply_context

    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=3,
        title="今晚 23:00 前入睡",
        content="...",
        status="active",
        metric_key="sleep_score",
        baseline_value="70",
        target_value="80",
        check_back_date=now + timedelta(days=1),
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    note = apply_opener_quick_reply_context(
        db,
        user_id=3,
        message="没做 ❌",
        extra_context=json.dumps({
            "entry": "conversation_opener_quick_reply",
            "user_reply": "没做 ❌",
            "source": "action_card_due",
            "source_id": card.id,
        }, ensure_ascii=False),
        now=now,
    )

    db.refresh(card)
    assert note is not None
    assert card.adherence_kind == "self_reported"
    assert card.adherence_confidence == 0
    assert card.graded_at is None


def test_action_card_opener_adjust_reply_records_adjusted_decision(db):
    from app.models.action_card import ActionCard
    from app.services.opener_quick_reply import apply_opener_quick_reply_context

    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=3,
        title="暂停跑步休息 7 天",
        content="...",
        status="active",
        check_back_date=now,
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    note = apply_opener_quick_reply_context(
        db,
        user_id=3,
        message="调整下计划",
        extra_context=json.dumps({
            "entry": "conversation_opener_quick_reply",
            "user_reply": "调整下计划",
            "source": "action_card_due",
            "source_id": card.id,
        }, ensure_ascii=False),
        now=now,
    )

    db.refresh(card)
    assert note is not None
    assert "记录 user_decision=adjusted" in note
    assert card.user_decision == "adjusted"
    assert card.decided_at is not None


@pytest.mark.asyncio
async def test_agent_stream_applies_opener_quick_reply_before_llm(db):
    from app.models.action_card import ActionCard
    from app.models.weight import WeightRecord
    from app.services.agent_executor import AgentExecutor

    user = _make_user(db)
    now = datetime.now(timezone.utc)
    db.add(WeightRecord(user_id=user.id, record_date=date.today(), weight=71.2))
    card = ActionCard(
        user_id=user.id,
        title="AI 预测：7 天体重保持 ≤ 71.3kg",
        content="...",
        status="active",
        metric_key="weight",
        baseline_value="72.0",
        target_value="≤71.3",
        check_back_date=now - timedelta(minutes=5),
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    captured_system = {}

    async def _fake_call_llm(self, messages, tools):
        captured_system["text"] = messages[0]["content"]
        return "已接上这张行动卡片并完成验证。"

    extra_context = json.dumps({
        "entry": "conversation_opener_quick_reply",
        "user_reply": "做到了 ✅",
        "source": "action_card_due",
        "source_id": card.id,
        "action_card_id": card.id,
    }, ensure_ascii=False)

    executor = AgentExecutor(db)
    events = []
    with patch.object(AgentExecutor, "_call_llm", new=_fake_call_llm):
        async for event in executor.run_stream(
            user_id=user.id,
            message="针对「今天就是 AI 预测的检验日」：做到了 ✅",
            extra_context=extra_context,
        ):
            events.append(event)

    db.refresh(card)
    assert card.adherence_confidence == 70
    assert card.graded_at is not None
    assert card.actual_value == "71.2"
    assert "入口动作处理结果" in captured_system["text"]
    assert f"ActionCard #{card.id}" in captured_system["text"]
    done = [e for e in events if e["event"] == "done"][-1]
    assert "ActionCard" in done["data"]["sources_used"]
