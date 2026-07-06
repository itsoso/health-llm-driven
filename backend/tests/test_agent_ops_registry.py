"""CI 闸:agent_ops_registry(后端操作面注册表)× agent_executor 单一源一致性。

spec: docs/specs/active/2026-07-02-agent-operable-module-contract.md §3.4
原则:executor 是唯一行为真源,注册表是诚实盘点 —— 两边比对全部
**source-derived**(AST 扫 executor 源码 + 直接 import 活的确认档位集合),
不允许在本文件手抄第二份清单。executor 加/删 record_type、manage 映射、
query dimension 而不改注册表(或反之)→ 本文件红,空洞在 CI 暴露而不是
用户嘴里。
"""
import ast
from pathlib import Path

from app.services import agent_executor, health_read, tool_schema_registry
from app.services.agent_ops_registry import AGENT_OPS, registry_violations

_normalize = agent_executor._normalize_fast_record_kind

_EXECUTOR_TREE = ast.parse(Path(agent_executor.__file__).read_text(encoding="utf-8"))
_HEALTH_READ_TREE = ast.parse(Path(health_read.__file__).read_text(encoding="utf-8"))


# ── AST 提取(source-derived,禁手抄)────────────────────────────────────

def _find_func(name: str, tree: ast.AST = _EXECUTOR_TREE):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name} —— executor/health_read 重构后请同步本闸")


def _dict_str_keys(func, var_name: str) -> set:
    """提取函数体内 `var_name = {...}` dict 字面量的字符串键集合。"""
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == var_name for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            keys = set()
            for k in node.value.keys:
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                    raise AssertionError(
                        f"{func.name}.{var_name} 含非字符串常量键,闸无法解析 —— 请改回字面量或更新本闸"
                    )
                keys.add(k.value)
            return keys
    raise AssertionError(f"在 {func.name} 里找不到 dict 字面量 {var_name}")


def _set_str_literal(func, var_name: str) -> set:
    """提取函数体内 `var_name = {...}` set 字面量的字符串元素集合。"""
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == var_name for t in node.targets)
            and isinstance(node.value, ast.Set)
        ):
            elems = set()
            for e in node.value.elts:
                if not (isinstance(e, ast.Constant) and isinstance(e.value, str)):
                    raise AssertionError(
                        f"{func.name}.{var_name} 含非字符串常量元素 —— 请更新本闸"
                    )
                elems.add(e.value)
            return elems
    raise AssertionError(f"在 {func.name} 里找不到 set 字面量 {var_name}")


def _compare_eq_strings(func, var_name: str) -> set:
    """提取 `var == "..."` / `var in ("...", ...)` 比较里的字符串常量集合。"""
    found = set()
    for node in ast.walk(func):
        if not (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == var_name
        ):
            continue
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                found.add(comp.value)
            elif isinstance(op, ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                for e in comp.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        found.add(e.value)
    return found


# ── 注册表侧提取 ─────────────────────────────────────────────────────────

def _op_entries(op: str):
    """yield (object_type, entry),只取声明了真实通路的条目(排除 gap/opt_out)。"""
    for obj, ops in sorted(AGENT_OPS.items()):
        if not isinstance(ops, dict) or "opt_out" in ops or ops.get("gap") is True:
            continue  # 整对象 opt_out/gap
        entry = ops.get(op)
        if isinstance(entry, dict) and "via" in entry:
            yield obj, entry


def _manage_record_types(op: str) -> set:
    return {
        e["record_type"] for _o, e in _op_entries(op) if e.get("tool") == "health_manage"
    }


# ── 闸 0:结构校验 ───────────────────────────────────────────────────────

def test_registry_structurally_valid():
    assert registry_violations() == []


# ── 闸 (a):确认档位镜像 executor 活集合 ─────────────────────────────────

def test_create_confirm_tiers_mirror_live_sets():
    auto_live = {
        _normalize(k) for k in agent_executor._FAST_RECORD_AUTO_CONFIRM_KINDS
    } - {_normalize(k) for k in agent_executor._TYPED_ONLY_AUTO_CONFIRM_KINDS}
    typed_live = {_normalize(k) for k in agent_executor._TYPED_ONLY_AUTO_CONFIRM_KINDS}
    never_live = {_normalize(k) for k in agent_executor._FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS}

    reg = {"auto": set(), "typed_only": set(), "never_auto": set()}
    for _obj, entry in _op_entries("create"):
        if entry.get("tool") != "health_record":
            continue
        reg[entry["confirm"]].add(entry["record_type"])

    # auto / typed_only 精确镜像(注册表不许比 executor 更宽或更窄)
    assert reg["auto"] == auto_live, (
        f"auto 档漂移: registry-only={reg['auto'] - auto_live}, executor-only={auto_live - reg['auto']}"
    )
    assert reg["typed_only"] == typed_live, (
        f"typed_only 档漂移: registry-only={reg['typed_only'] - typed_live}, "
        f"executor-only={typed_live - reg['typed_only']}"
    )
    # never_auto ⊇ NEVER 集 ∩ 注册面(fail-closed 方向:executor 恒确认的,
    # 注册表绝不许标成 auto/typed_only)
    registered = reg["auto"] | reg["typed_only"] | reg["never_auto"]
    assert never_live & registered <= reg["never_auto"], (
        f"NEVER 集内的 record_type 被注册成了更宽档位: {never_live & registered - reg['never_auto']}"
    )
    assert not (reg["auto"] | reg["typed_only"]) & never_live


# ── 闸 (b):health_record create 双向覆盖 ────────────────────────────────

def test_health_record_create_coverage_bidirectional():
    func = _find_func("_exec_health_record")
    handled = {_normalize(s) for s in _compare_eq_strings(func, "rtype")}
    handled |= {_normalize(k) for k in _dict_str_keys(func, "record_map")}

    registered = {
        e["record_type"]
        for _o, e in _op_entries("create")
        if e.get("tool") == "health_record"
    }
    # 注册表只登记 canonical 名(别名如 bp 不入表)
    assert registered == {_normalize(r) for r in registered}
    assert handled == registered, (
        "executor 处理的 record_type 与注册表 create 面漂移: "
        f"executor-only={handled - registered}, registry-only={registered - handled}"
    )


# ── 闸 (c):health_manage list/update/delete 映射双向镜像 ────────────────

def test_health_manage_maps_mirror_registry():
    func = _find_func("_exec_health_manage")
    list_keys = _dict_str_keys(func, "list_paths")
    delete_keys = _dict_str_keys(func, "record_paths")
    update_keys = _set_str_literal(func, "update_supported") & delete_keys

    assert _manage_record_types("list") == list_keys, (
        f"list 面漂移: registry-only={_manage_record_types('list') - list_keys}, "
        f"executor-only={list_keys - _manage_record_types('list')}"
    )
    assert _manage_record_types("delete") == delete_keys, (
        f"delete 面漂移: registry-only={_manage_record_types('delete') - delete_keys}, "
        f"executor-only={delete_keys - _manage_record_types('delete')}"
    )
    assert _manage_record_types("update") == update_keys, (
        f"update 面漂移: registry-only={_manage_record_types('update') - update_keys}, "
        f"executor-only={update_keys - _manage_record_types('update')}"
    )


# ── 闸 (d):health_query dimension 双向覆盖 ──────────────────────────────

def test_health_query_dimensions_bidirectional():
    endpoint_dims = _dict_str_keys(_find_func("_exec_health_query"), "endpoint_map")
    # canonical 读层维度(endpoint_map 之前短路):medical_exam + wearable 别名集
    canonical_dims = set(health_read._WEARABLE_DIMS) | _compare_eq_strings(
        _find_func("canonical_read", _HEALTH_READ_TREE), "dimension"
    )
    live = endpoint_dims | canonical_dims

    reg_dims = set()
    for _o, e in _op_entries("read"):
        if e.get("tool") == "health_query" and "dimensions" in e:
            reg_dims |= set(e["dimensions"])

    missing = live - reg_dims
    assert not missing, f"executor 可读维度未在任何对象登记 read 面: {missing}"
    aspirational = reg_dims - live
    assert not aspirational, f"注册表登记了 executor 不认识的维度(愿景≠盘点): {aspirational}"


# ── 闸 (e):spec 落地状态章节与本闸互链 ──────────────────────────────────

def test_spec_doc_records_landing_state():
    spec = (
        Path(__file__).resolve().parents[2]
        / "docs/specs/active/2026-07-02-agent-operable-module-contract.md"
    )
    text = spec.read_text(encoding="utf-8")
    assert "agent_ops_registry" in text, "spec 必须引用注册表文件名(§3.4 落地)"
    assert "落地状态" in text, "spec 缺 '## 落地状态' 盘点章节(task #43 交付物)"


def _tool_function(name: str) -> dict:
    for tool in tool_schema_registry.HEALTH_TOOLS:
        fn = tool.get("function") or {}
        if fn.get("name") == name:
            return fn
    raise AssertionError(f"找不到工具 schema: {name}")


def _tool_enum(tool_name: str, prop: str) -> set:
    fn = _tool_function(tool_name)
    params = fn.get("parameters") or {}
    props = params.get("properties") or {}
    schema = props.get(prop) or {}
    return set(schema.get("enum") or [])


def test_p2_agent_create_gaps_are_closed_for_manual_body_records():
    for obj in ("waist", "sleep", "excretion"):
        entry = AGENT_OPS[obj]["create"]
        assert not entry.get("gap"), f"{obj}.create 不能再是 gap"
        assert entry["tool"] == "health_record"
        assert entry["record_type"] == obj
        assert entry["confirm"] == "auto"
        assert entry.get("undo")


def test_p2_supplement_intake_records_are_manageable():
    for op in ("list", "update", "delete"):
        entry = AGENT_OPS["supplement"][op]
        assert not entry.get("gap"), f"supplement.{op} 不能再是 gap"
        assert entry["tool"] == "health_manage"
        assert entry["record_type"] == "supplement"
    assert AGENT_OPS["supplement"]["create"]["undo"] == "health_manage(delete supplement {record_id})"
    assert "undo_gap" not in AGENT_OPS["supplement"]["create"]


def test_tool_schemas_expose_p2_agent_record_and_manage_types():
    assert {"waist", "sleep", "excretion"} <= _tool_enum("health_record", "record_type")
    assert "supplement" in _tool_enum("health_manage", "record_type")


def test_p2_goal_agent_crud_is_exposed():
    create = AGENT_OPS["goal"]["create"]
    assert create["tool"] == "health_record"
    assert create["record_type"] == "goal"
    assert create["confirm"] == "typed_only"
    assert create["undo"] == "health_manage(delete goal {record_id})"

    read = AGENT_OPS["goal"]["read"]
    assert read["tool"] == "health_manage"
    assert read["record_type"] == "goal"

    for op in ("list", "update", "delete"):
        entry = AGENT_OPS["goal"][op]
        assert not entry.get("gap"), f"goal.{op} 不能再是 gap"
        assert entry["tool"] == "health_manage"
        assert entry["record_type"] == "goal"

    assert "goal" in _tool_enum("health_record", "record_type")
    assert "goal" in _tool_enum("health_manage", "record_type")


def test_p2_medical_exam_report_list_is_exposed_without_mutation():
    assert AGENT_OPS["medical_exam"]["list"]["tool"] == "health_manage"
    assert AGENT_OPS["medical_exam"]["list"]["record_type"] == "medical_exam"
    assert not AGENT_OPS["medical_exam"]["list"].get("gap")

    assert AGENT_OPS["medical_exam"]["create"].get("opt_out")
    assert AGENT_OPS["medical_exam"]["update"].get("opt_out")
    assert AGENT_OPS["medical_exam"]["delete"].get("opt_out")
    assert "medical_exam" in _tool_enum("health_manage", "record_type")
