"""An unbound user restriction cannot become a shadow-mode read."""

from datetime import datetime
import json

import pytest

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import (
    AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "shadow"])
@pytest.mark.parametrize("tool,args", [
    ("health_query", {"dimension": "diet", "days": 7}),
    ("health_query_batch", {"queries": [{"dimension": "diet", "days": 7}]}),
    ("health_manage", {"record_type": "diet", "operation": "list"}),
])
async def test_unresolved_user_limit_never_dispatches_or_advertises_parameter_repair(mode, tool, args):
    envelope = AgentEnvelope(user_id=41, channel="typed", text="只看今早，查询我的饮食并分析")
    context = ExecutionContext(
        user_id=41, channel="typed", timezone="Asia/Shanghai",
        current_time=datetime.fromisoformat("2026-09-13T09:00:00+08:00"),
    )
    snapshot = TurnSnapshot(
        envelope, context, build_intent_frame(envelope, context), policy_mode=mode,
    )
    dispatched = []

    async def dispatch(request):
        dispatched.append(request)
        return '{"records": []}'

    result = await ToolGateway(snapshot).execute(ToolExecutionRequest(tool, args), dispatch)
    assert not dispatched
    assert result.decision.action == "block"
    assert result.decision.reason == "longitudinal_read_scope_unresolved"
    payload = json.loads(result.content)
    assert payload["dispatch_started"] is False
    assert payload["terminal"] is True
    assert payload["retryable"] is False
    assert "范围" in payload["message"]
