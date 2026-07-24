"""Kernel migration guards for direct write dispatch and retired regex gates."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "app/services/agent_executor.py"
VOICE_SHORTCUTS = ROOT / "app/services/voice_command_service.py"
CAPABILITY_POLICY = ROOT / "app/services/agent_kernel/capability_policy.py"


def test_health_record_and_manage_are_not_dispatched_by_direct_method_calls():
    tree = ast.parse(EXECUTOR.read_text())
    direct_calls: list[tuple[str, int]] = []

    for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in {"_exec_health_record", "_exec_health_manage"}:
                direct_calls.append((function.name, node.lineno))

    assert direct_calls == []


def test_no_surface_calls_health_write_implementation_directly():
    direct_calls: list[tuple[str, str, int]] = []
    for path in (ROOT / "app").rglob("*.py"):
        if path == EXECUTOR:
            continue
        tree = ast.parse(path.read_text())
        for function in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for node in ast.walk(function):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr in {"_exec_health_record", "_exec_health_manage"}:
                    direct_calls.append((str(path.relative_to(ROOT)), function.name, node.lineno))

    assert direct_calls == []


def test_executor_no_longer_declares_regex_write_intent_gates():
    source = EXECUTOR.read_text()
    retired = (
        "_RECORD_INTENT_RE",
        "_RECORD_INTERROGATIVE_GUARD_RE",
        "_RECORD_NEGATION_GUARD_RE",
        "_SIMPLE_QUERY_INTENT_RE",
        "_QUERY_ONLY_COMMAND_RE",
        "_QUERY_ONLY_MUTATION_RE",
        "_QUERY_ONLY_RECORD_ACTION_RE",
        "_QUERY_RELATIVE_DATE_RE",
        "_DESTRUCTIVE_OR_SYNC_INTENT_RE",
    )

    assert not [name for name in retired if name in source]


def test_voice_shortcuts_cannot_write_database_without_the_tool_gateway():
    tree = ast.parse(VOICE_SHORTCUTS.read_text())
    direct_db_mutations: list[tuple[str, int]] = []

    for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"
                and node.func.value.attr == "db"
                and node.func.attr in {"add", "commit", "delete", "flush"}
            ):
                direct_db_mutations.append((function.name, node.lineno))

    assert direct_db_mutations == []
    source = VOICE_SHORTCUTS.read_text()
    assert "CloudAgentRuntimeFacade(self.db).execute_tool(" in source
    assert "executor._execute_tool(" not in source
    assert "build_turn_snapshot(" in source


def test_every_registered_agent_tool_has_an_explicit_kernel_capability_class():
    from app.services.agent_kernel.capability_policy import KNOWN_TOOL_NAMES
    from app.services.tool_schema_registry import get_health_tools

    registered = {
        (tool.get("function") or {}).get("name")
        for tool in get_health_tools()
        if (tool.get("function") or {}).get("name")
    }

    assert registered <= KNOWN_TOOL_NAMES


def test_capability_sets_are_derived_from_tool_specs_not_a_second_manual_registry():
    source = CAPABILITY_POLICY.read_text()

    assert "from app.services.agent_kernel.tool_registry import" in source
    assert "list_tool_specs" in source
    assert "READ_ONLY_TOOLS = frozenset({" not in source
    assert "SPECIALIST_READ_ONLY_TOOLS = frozenset({" not in source
    assert "WRITE_TOOL_NAMES = frozenset({" not in source


def test_executor_dispatch_uses_gateway_and_registry_adapter_lookup():
    tree = ast.parse(EXECUTOR.read_text())
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    execute_impl = ast.unparse(functions["_execute_tool_impl"])
    dispatch = ast.unparse(functions["_dispatch_tool_request"])

    assert "ToolGateway(snapshot).execute" in execute_impl
    assert "get_tool_spec(request.tool_name)" in dispatch
    assert "getattr(self, spec.executor_method)" in dispatch
    assert "if tool_name ==" not in dispatch
