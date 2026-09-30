"""HTML presentation stays separate from authenticated read authority."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.agent_conversation import AgentMessage
from app.models.daily_health import GarminData
from app.services.agent_query_window import parse_query_window, read_calendar_health_query
from tests.conftest import create_authenticated_user
from tests.test_query_reliability_outcomes import _run_scripted


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "分析最近一周的睡眠数据,HTML 形式表达",
    "分析最近一周的睡眠数据，用HTML形式表达",
])
async def test_html_request_executes_owned_read_and_persists_original_format(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, query,
):
    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    db.add_all([
        GarminData(user_id=user.id, record_date=today, data_source="garmin", sleep_score=73),
        GarminData(user_id=other.id, record_date=today, data_source="garmin", sleep_score=99),
        GarminData(user_id=user.id, record_date=today - timedelta(days=40), data_source="garmin", sleep_score=98),
    ])
    db.commit()
    verified = []

    def dispatch(request):
        assert request.tool_name == "health_query"
        args = request.arguments
        assert args["dimension"] == "sleep" and args["timezone"] == "Asia/Shanghai"
        window = parse_query_window(args)
        assert window is not None
        assert (window.end_date - window.start_date).days == 6
        result = read_calendar_health_query(db, user.id, "sleep", window)
        assert [row["sleep_score"] for row in result["records"]] == [73]
        verified.append(result)
        return result

    executor, done, saved, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query=query, first_tool="health_query",
        first_args={"dimension": "sleep"}, dispatch=dispatch,
        reply="本次查询返回一条睡眠记录，记录评分为73。",
        turn_id="html-owned-window",
    )
    assert dispatched and len(verified) == 1
    assert done["completion_status"] == done["turn_outcome"]["status"] == "complete"
    assert not done.get("write_receipts")
    assert "范围限制尚不能完整解析" not in saved.content + public
    source = db.query(AgentMessage).filter_by(conversation_id=done["conversation_id"], role="user").one()
    assert source.content == query
    assert executor._current_turn_user_message == query


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "分析最近一周妈妈的睡眠数据，用HTML形式表达",
    "分析最近一周的睡眠数据，只看上午，用HTML形式表达",
    "    分析最近一周的睡眠数据，用HTML形式表达",
    "\t分析最近一周的睡眠数据，用HTML形式表达",
    "    使用HTML方式输出最近一周的睡眠情况以及你的分析。",
])
async def test_html_request_cannot_dispatch_unowned_or_unresolved_scope(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, query,
):
    user, _ = auth_user_and_headers

    def forbidden(_request):
        pytest.fail("Unsupported original authority must not read personal data")

    _, done, saved, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query=query, first_tool="health_query",
        first_args={"dimension": "sleep"}, dispatch=forbidden,
        reply="查询未执行。", turn_id="html-denied-scope",
    )
    assert not dispatched and not done.get("write_receipts")
    assert done["turn_outcome"]["status"] != "complete"
