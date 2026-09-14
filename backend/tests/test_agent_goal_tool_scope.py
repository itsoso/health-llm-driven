from app.services.agent_input_tool_scope import scope_tools_for_goal
from app.services.agent_kernel.types import GoalSpec


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


def test_fully_read_only_goal_hides_pure_writes_but_keeps_mixed_reads():
    tools = [_tool("manage_plan"), _tool("health_manage"), _tool("knowledge_search")]
    goal = GoalSpec(
        kind="answer",
        domain="plan",
        operation="analyze",
        prohibited_operations=("create", "update", "delete"),
    )

    assert [tool["function"]["name"] for tool in scope_tools_for_goal(tools, goal)] == [
        "health_manage",
        "knowledge_search",
    ]


def test_write_capable_goal_keeps_existing_tool_set():
    tools = [_tool("manage_plan"), _tool("health_manage"), _tool("knowledge_search")]
    goal = GoalSpec(kind="write", domain="plan", operation="create")

    assert scope_tools_for_goal(tools, goal) is tools
