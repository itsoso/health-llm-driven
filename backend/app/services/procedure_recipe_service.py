"""程序性记忆/配方(Harness 自由度升级 Slice 3)。

配方 = **确定性重放的工具序列**,不是程序、不是 LLM 现场生成。核心不变量:

1. **确认门原样生效** — 重放每步先过 ``_auto_confirm_fast_record_args``
   (与直接调用完全一致的 AUTO / typed_only / never_auto 分级),再走
   AgentExecutor 既有工具执行路径(``_execute_tool``)。never_auto kind
   (medication 等)重放仍返回 ``[NEEDS_CONFIRMATION]``、**绝不写库**。
2. **模板确定性** — ``args_template`` 只允许既有槽位的确定性填充:唯一的
   占位符是 ``{{today}}``(重放当天北京日期)。禁止 LLM 现场改参。
3. **confirmed 剥除(双端)** — 存入时和重放时都剥掉 confirmed/confirm 标志,
   防止「用户在原对话确认过一次」被配方继承成永久免确认(对抗评审向量)。
4. **精确触发** — trigger_phrase strip 后与消息等值才命中,不做模糊匹配
   (控误触发;近似短语落回正常 LLM 链路)。

见 docs/plans/2026-07-07-agent-harness-freedom-upgrades.md §Slice 3。
"""
import copy
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.procedure_recipe import ProcedureRecipe

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

# v1 只允许 health_record 步骤:确认档位(auto/typed_only/never_auto)有唯一
# 执行点(_auto_confirm_fast_record_args + _exec_health_record 内联确认),
# 重放语义清晰。health_manage(update/delete 绑一次性 record_id,不可重放)与
# intervention_cycle(N-of-1 周期,重放无意义)不入白名单 —— fail-loud 拒存。
ALLOWED_RECIPE_TOOLS = frozenset({"health_record"})

MAX_STEPS = 10
# 安全评审必改:防单用户无限造配方(表膨胀 + match_trigger 每消息 O(配方×短语) 开销)。
# 30 × 5 短语 = 每消息最多 150 次精确等值比较,开销有界。
MAX_RECIPES_PER_USER = 30
MAX_TRIGGER_PHRASES = 5
MIN_TRIGGER_LEN = 2   # 单字短语("好"/"嗯")误触发风险太高,拒绝
MAX_TRIGGER_LEN = 40
MAX_NAME_LEN = 100

TODAY_PLACEHOLDER = "{{today}}"
# 只对这些确定性日期槽位做模板化;其余字段原样存(不做任何推断/改写)。
_DATE_KEYS = frozenset({"record_date", "start_date", "end_date", "date"})
# 一次性确认标志:存入前 + 重放前双端剥除(见模块 docstring 不变量 3)。
_CONFIRM_KEYS = ("confirmed", "confirm", "_fast_record_requires_confirmation")


def _today_str() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")


# ─────────────────────────── args 模板(确定性) ───────────────────────────

def sanitize_step_args(args: Any) -> Dict[str, Any]:
    """深拷贝 + 剥除顶层与 data 层的一次性确认标志。非 dict 输入返回空 dict。"""
    if not isinstance(args, dict):
        return {}
    cleaned = copy.deepcopy(args)
    for key in _CONFIRM_KEYS:
        cleaned.pop(key, None)
    data = cleaned.get("data")
    if isinstance(data, dict):
        for key in _CONFIRM_KEYS:
            data.pop(key, None)
    return cleaned


def template_step_args(args: Dict[str, Any], today: Optional[str] = None) -> Dict[str, Any]:
    """把「值 == 存入当天」的日期槽位替换成 {{today}}(存入时调用)。

    只匹配白名单日期键 + 精确等值,其他一概不动 —— 模板化是确定性收窄,
    不是自由改写。
    """
    today = today or _today_str()
    templated = copy.deepcopy(args)

    def _walk(obj: Dict[str, Any]) -> None:
        for key, value in obj.items():
            if key in _DATE_KEYS and isinstance(value, str) and value.strip() == today:
                obj[key] = TODAY_PLACEHOLDER
            elif key == "data" and isinstance(value, dict):
                _walk(value)

    _walk(templated)
    return templated


def fill_step_args(args_template: Any, today: Optional[str] = None) -> Dict[str, Any]:
    """重放前:{{today}} → 当天日期;并再次剥除确认标志(防御纵深)。"""
    today = today or _today_str()
    filled = sanitize_step_args(args_template)

    def _walk(obj: Dict[str, Any]) -> None:
        for key, value in obj.items():
            if isinstance(value, str) and value == TODAY_PLACEHOLDER:
                obj[key] = today
            elif isinstance(value, dict):
                _walk(value)

    _walk(filled)
    return filled


# ─────────────────────────── CRUD + 校验 ───────────────────────────

def _validate_name(name: Any) -> str:
    cleaned = str(name or "").strip()
    if not cleaned:
        raise ValueError("配方名称不能为空")
    if len(cleaned) > MAX_NAME_LEN:
        raise ValueError(f"配方名称不能超过 {MAX_NAME_LEN} 字")
    return cleaned


def _validate_trigger_phrases(
    db: Session, user_id: int, phrases: Any, *, exclude_recipe_id: Optional[int] = None
) -> List[str]:
    if not isinstance(phrases, list) or not phrases:
        raise ValueError("至少需要一条触发短语")
    cleaned: List[str] = []
    for raw in phrases:
        phrase = str(raw or "").strip()
        if not phrase:
            continue
        if len(phrase) < MIN_TRIGGER_LEN:
            raise ValueError(f"触发短语「{phrase}」太短(至少 {MIN_TRIGGER_LEN} 字,防误触发)")
        if len(phrase) > MAX_TRIGGER_LEN:
            raise ValueError(f"触发短语不能超过 {MAX_TRIGGER_LEN} 字")
        if phrase not in cleaned:
            cleaned.append(phrase)
    if not cleaned:
        raise ValueError("至少需要一条触发短语")
    if len(cleaned) > MAX_TRIGGER_PHRASES:
        raise ValueError(f"触发短语最多 {MAX_TRIGGER_PHRASES} 条")

    # 同用户跨配方短语冲突 → 拒绝(命中歧义比拒绝更危险)
    existing = list_recipes(db, user_id)
    for recipe in existing:
        if exclude_recipe_id is not None and recipe.id == exclude_recipe_id:
            continue
        overlap = set(cleaned) & {str(p).strip() for p in (recipe.trigger_phrases or [])}
        if overlap:
            raise ValueError(
                f"触发短语「{sorted(overlap)[0]}」已被配方「{recipe.name}」占用"
            )
    return cleaned


def validate_steps(steps: Any) -> List[Dict[str, Any]]:
    """校验 + 归一步骤列表。fail-loud:未知工具/坏形状直接 ValueError,不静默剔除。"""
    if not isinstance(steps, list) or not steps:
        raise ValueError("配方至少需要一个步骤")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"配方步骤最多 {MAX_STEPS} 个")
    normalized: List[Dict[str, Any]] = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError(f"步骤 {index} 形状不合法(应为对象)")
        tool = str(step.get("tool") or "").strip()
        if tool not in ALLOWED_RECIPE_TOOLS:
            raise ValueError(
                f"步骤 {index} 工具「{tool or '(空)'}」不允许入配方"
                f"(允许: {sorted(ALLOWED_RECIPE_TOOLS)})"
            )
        raw_args = step.get("args_template")
        if not isinstance(raw_args, dict) or not raw_args:
            raise ValueError(f"步骤 {index} 缺少 args_template")

        # 函数级 import 避免与 agent_executor 的相互引用成环(对方也函数级引本模块)。
        from app.services.agent_executor import _FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS
        from app.services.agent_kernel.capability_policy import (
            RECIPE_REPLAY_ALLOWED_RECORD_TYPES,
            recipe_replay_record_type,
        )

        step_kind = recipe_replay_record_type(raw_args)
        # never_auto kind(用药等)重放永远要求确认、永不可能自动执行,
        # 存进配方是纯死重量,且把药名/剂量多写进一处明文 JSONB。存入时直接拒绝。
        if step_kind in _FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS:
            raise ValueError(
                f"步骤 {index} 类型「{step_kind}」需逐次人工确认,不支持存入配方"
            )
        if step_kind not in RECIPE_REPLAY_ALLOWED_RECORD_TYPES:
            raise ValueError(
                f"步骤 {index} 类型「{step_kind or '未知'}」不支持存入配方"
            )
        normalized.append({
            "tool": tool,
            "args_template": template_step_args(sanitize_step_args(raw_args)),
        })
    return normalized


def create_recipe(
    db: Session,
    user_id: int,
    *,
    name: Any,
    trigger_phrases: Any,
    steps: Any,
    created_from_conversation_id: Optional[int] = None,
) -> ProcedureRecipe:
    existing_count = (
        db.query(ProcedureRecipe).filter(ProcedureRecipe.user_id == user_id).count()
    )
    if existing_count >= MAX_RECIPES_PER_USER:
        raise ValueError(f"配方数量已达上限({MAX_RECIPES_PER_USER}),请先删除不用的配方")
    recipe = ProcedureRecipe(
        user_id=user_id,
        name=_validate_name(name),
        trigger_phrases=_validate_trigger_phrases(db, user_id, trigger_phrases),
        steps=validate_steps(steps),
        created_from_conversation_id=created_from_conversation_id,
        use_count=0,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def list_recipes(db: Session, user_id: int) -> List[ProcedureRecipe]:
    return (
        db.query(ProcedureRecipe)
        .filter(ProcedureRecipe.user_id == user_id)
        .order_by(ProcedureRecipe.created_at.desc(), ProcedureRecipe.id.desc())
        .all()
    )


def delete_recipe(db: Session, user_id: int, recipe_id: int) -> bool:
    recipe = (
        db.query(ProcedureRecipe)
        .filter(ProcedureRecipe.id == recipe_id, ProcedureRecipe.user_id == user_id)
        .first()
    )
    if recipe is None:
        return False
    db.delete(recipe)
    db.commit()
    return True


def serialize(recipe: ProcedureRecipe) -> Dict[str, Any]:
    return {
        "id": recipe.id,
        "name": recipe.name,
        "trigger_phrases": list(recipe.trigger_phrases or []),
        "steps": list(recipe.steps or []),
        "created_from_conversation_id": recipe.created_from_conversation_id,
        "use_count": recipe.use_count or 0,
        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
    }


# ─────────────────────────── 触发匹配(精确) ───────────────────────────

def match_trigger(db: Session, user_id: int, text: Any) -> Optional[ProcedureRecipe]:
    """strip 后精确等值匹配(先于 LLM)。不做模糊/子串/前缀匹配 —— 控误触发。"""
    message = str(text or "").strip()
    if not message or len(message) < MIN_TRIGGER_LEN:
        return None
    for recipe in list_recipes(db, user_id):
        for phrase in recipe.trigger_phrases or []:
            if message == str(phrase or "").strip():
                return recipe
    return None


def increment_use_count(db: Session, recipe: ProcedureRecipe) -> None:
    recipe.use_count = (recipe.use_count or 0) + 1
    db.commit()


# ─────────────────────────── 从对话反推候选步骤 ───────────────────────────

def recipe_candidate_from_conversation(
    db: Session, user_id: int, conversation_id: int
) -> Optional[Dict[str, Any]]:
    """取该对话最近一条带 meta.recipe_candidate 的助手消息的候选步骤。

    候选由 agent_executor 在「一轮完成 ≥2 个写类工具」时写入(已 sanitize +
    模板化)。归属校验:对话必须属于该用户,否则返回 None(不泄露存在性)。
    """
    from app.models.agent_conversation import AgentConversation, AgentMessage

    conv = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        )
        .first()
    )
    if conv is None:
        return None
    messages = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.role == "assistant",
        )
        .order_by(AgentMessage.id.desc())
        .limit(20)
        .all()
    )
    for message in messages:
        candidate = (message.meta or {}).get("recipe_candidate")
        if isinstance(candidate, dict) and isinstance(candidate.get("steps"), list):
            return {"steps": candidate["steps"], "message_id": message.id}
    return None


# ─────────────────────────── 确定性重放 ───────────────────────────

def step_label(step: Dict[str, Any]) -> str:
    """步骤的确定性人话标签(存卡预览 + 重放回执共用)。"""
    args = step.get("args_template") or {}
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    kind = str(
        args.get("record_type") or args.get("type") or data.get("record_type") or ""
    ).strip().lower()
    kind_labels = {
        "water": "饮水", "diet": "饮食", "weight": "体重",
        "blood_pressure": "血压", "bp": "血压", "exercise": "运动",
        "supplement": "补剂", "medication": "用药", "reminder": "提醒",
        "symptom": "症状", "rhinitis": "鼻炎", "sleep": "睡眠",
        "mood": "心情", "waist": "腰围", "goal": "目标",
    }
    label = kind_labels.get(kind, kind or "记录")
    detail = ""
    if kind == "water" and data.get("amount"):
        detail = f" {data['amount']}ml"
    elif kind == "diet" and data.get("food_items"):
        detail = f" {str(data['food_items'])[:20]}"
    elif kind == "weight" and data.get("weight"):
        detail = f" {data['weight']}kg"
    elif kind in ("blood_pressure", "bp") and data.get("systolic") and data.get("diastolic"):
        detail = f" {data['systolic']}/{data['diastolic']}"
    elif kind in ("medication", "supplement") and (data.get("name") or data.get("medication_name")):
        detail = f" {data.get('name') or data.get('medication_name')}"
    return f"{label}{detail}"


async def replay(
    recipe: ProcedureRecipe,
    executor: Any,
    *,
    user_auth_token: Optional[str],
    channel: Optional[str],
) -> AsyncGenerator[Dict[str, Any], None]:
    """逐步确定性重放:每步 = 填模板 → 过既有确认门 → 走 executor._execute_tool。

    **不绕任何确认门**:``_auto_confirm_fast_record_args`` 与快路由直接调用
    完全同一函数、同一分级 —— AUTO kind 确定性放行;typed_only kind 依 channel;
    never_auto kind(medication 等)恒被置 ``_fast_record_requires_confirmation``,
    ``_exec_health_record`` 会返回 ``[NEEDS_CONFIRMATION]`` 而不写库。

    两段式 yield(executor 侧据此在执行前下发 tool_call、执行后下发 tool_result):
      {"phase": "start",  step_index, tool, args}
      {"phase": "result", step_index, tool, args, result, needs_confirmation, error}
    """
    # 懒 import 防循环(executor 亦懒 import 本模块)
    from app.services.agent_executor import _auto_confirm_fast_record_args
    from app.services.agent_kernel.capability_policy import (
        RECIPE_REPLAY_ALLOWED_RECORD_TYPES,
        recipe_replay_record_type,
    )

    for index, step in enumerate(recipe.steps or [], 1):
        tool = str((step or {}).get("tool") or "").strip()
        if tool not in ALLOWED_RECIPE_TOOLS:
            # 库里出现白名单外工具(历史数据/手改库)→ fail-loud 拒执行该步
            yield {
                "phase": "result",
                "step_index": index,
                "tool": tool,
                "args": {},
                "result": f"Error: 配方步骤工具「{tool}」不允许重放",
                "needs_confirmation": False,
                "error": True,
            }
            continue
        args = fill_step_args((step or {}).get("args_template") or {})
        gated_args = _auto_confirm_fast_record_args(tool, args, channel=channel)
        if not isinstance(gated_args, dict):
            try:
                gated_args = json.loads(gated_args)
            except (json.JSONDecodeError, TypeError, ValueError):
                gated_args = args
        record_type = recipe_replay_record_type(gated_args)
        if record_type not in RECIPE_REPLAY_ALLOWED_RECORD_TYPES:
            yield {
                "phase": "start",
                "step_index": index,
                "tool": tool,
                "args": gated_args,
            }
            if gated_args.get("_fast_record_requires_confirmation"):
                yield {
                    "phase": "result",
                    "step_index": index,
                    "tool": tool,
                    "args": gated_args,
                    "result": (
                        "[NEEDS_CONFIRMATION] 此步骤需要你逐次确认，未执行写入。"
                    ),
                    "needs_confirmation": True,
                    "error": False,
                }
                continue
            yield {
                "phase": "result",
                "step_index": index,
                "tool": tool,
                "args": gated_args,
                "result": (
                    f"Error: 配方步骤记录类型「{record_type or '未知'}」不允许重放"
                ),
                "needs_confirmation": False,
                "error": True,
            }
            continue
        yield {
            "phase": "start",
            "step_index": index,
            "tool": tool,
            "args": gated_args,
        }
        result = await executor._execute_recipe_step(
            tool, json.dumps(gated_args, ensure_ascii=False), user_auth_token
        )
        result_text = str(result or "")
        yield {
            "phase": "result",
            "step_index": index,
            "tool": tool,
            "args": gated_args,
            "result": result_text,
            "needs_confirmation": result_text.startswith("[NEEDS_CONFIRMATION]"),
            "error": result_text.startswith("Error"),
        }
