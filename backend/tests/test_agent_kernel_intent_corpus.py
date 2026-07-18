import json
from pathlib import Path

import pytest

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext


CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "agent_intent_corpus.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case['channel']}:{case['text'][:12]}")
def test_agent_kernel_intent_corpus(case):
    envelope = AgentEnvelope(
        user_id=1,
        channel=case["channel"],
        text=case["text"],
    )
    frame = build_intent_frame(
        envelope,
        ExecutionContext.for_test(user_id=1, channel=case["channel"]),
    )

    assert frame.primary == case["primary"]
    assert frame.domain == case["domain"]
    assert frame.operation == case["operation"]
    assert frame.is_write is case["is_write"]


def test_intent_frame_marks_ambiguous_unknown_for_clarification():
    frame = build_intent_frame(
        AgentEnvelope(user_id=1, channel="chat", text="好的"),
        ExecutionContext.for_test(user_id=1, channel="chat"),
    )

    assert frame.primary == "unknown"
    assert "low_confidence" in frame.ambiguity
    assert frame.is_write is False
