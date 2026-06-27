"""Apple Watch Companion API(W1)。腕上摘要:状态灯 + 最重要行动 + 打点入口 + 关键推送。

W1.5:到点项一键完成 + 服药/补剂依从回写。
王牌⑤(本刀):腕上语音记症状 → SafetyGuardian 确定性裁决(全场安全 stakes 最高)。
详见 docs/design-watch-voice-symptom.md。

腕上不持 user_id,经 iPhone 中继携 token,后端从 token 取 user_id(绝不信任客户端 user_id)。
"""
import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.safety_guardian.engine import (
    evaluate_rules_with_status,
    make_fail_safe_advisory,
)
from app.agents.safety_guardian.schema import Alert
from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.symptom_entry import SymptomEntry
from app.models.user import User
from app.services import health_protocol_service as proto_svc
from app.services import timeline_agenda_service as tas
from app.services import workday_health_scheduler
from app.services.guidance_validator import sanitize_guidance
from app.services.watch_summary import build_watch_summary
from app.twin import builder
from app.twin.schema import HealthTwin, TwinMeta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watch", tags=["Apple Watch Companion"])

_SYMPTOM_MAX_LEN = 500
_WATCH_ASK_FAIL_LOUD = "本次未能完成自动安全筛查,请勿据此判断为安全;不适请就医,紧急拨 120"
_WATCH_ASK_ESCALATE_TEXT = "这个问题需要在 iPhone 上结合完整资料查看,手表上不展开判断。请不要据此自行调整用药、剂量、饮食或训练。"
_WATCH_ASK_MEDICAL_TEXT = "这个情况可能涉及安全风险,手表上不展开判断。请立即在 iPhone 查看详情;如正在胸痛、呼吸困难、半身无力或情况紧急,请拨打 120。"
_WATCH_ASK_LLM_FALLBACK = "我暂时无法完成可靠短答,请到 iPhone 查看完整上下文。不要据此自行调整用药、饮食或训练。"
_WATCH_ASK_ESCALATE_RE = re.compile(
    r"(处方|用药|吃药|服药|停药|加药|换药|药量|剂量|用量|吃多少|怎么吃|"
    r"要不要吃|能不能吃[^。！？!?]{0,8}药|毫克|mg|片|胶囊|"
    r"影像|拍片|片子|CT|核磁|MRI|X光|B超|诊断|确诊|是不是|是否需要|需不需要|"
    r"要不要[^。！？!?]{0,8}(?:拍片|检查|吃药|用药|手术|就医|急诊)|"
    r"(?:会不会是|有没有可能是|疑似|像是|考虑)[^。！？!?]{0,20}(?:炎|病|症|感染|感冒|心梗|中风|癌|骨折|结石)|"
    r"(?:我)?这是[^。！？!?]{0,16}吗)",
    re.IGNORECASE,
)
_WATCH_ASK_MEDICAL_ATTENTION_RE = re.compile(
    r"(胸痛|胸口闷|心梗|中风|呼吸困难|喘不上气|半身|嘴歪|说话不清|"
    r"黑便|呕血|晕厥|剧烈腹痛|急诊|120)",
    re.IGNORECASE,
)
_WATCH_ASK_UNSAFE_OUTPUT_RE = re.compile(
    r"(确诊|你患有|你得了|你这是|"
    r"(?:可能是|考虑|疑似|像是|倾向于)[^。！？!?]{0,20}(?:炎|病|症|感染|感冒|心梗|中风|癌|骨折|结石)|"
    r"(?:可以|建议|需要|应当|最好|考虑)[^。！？!?]{0,8}(?:吃|服用|口服|使用|停用|加用|换用)[^。！？!?]{0,24}|"
    r"(?:口服|服用|吃药|用药)[^。！？!?]{0,24}|"
    r"(?:使用|外用|涂抹|滴用|喷用|滴入|喷入)[^。！？!?]{0,20}(?:药|喷雾|软膏|乳膏|滴眼液|滴鼻液|布地奈德|莫匹罗星|红霉素|左氧氟沙星|抗生素|激素)|"
    r"(?:每日|每天|每晚|早晚|一次|每次|睡前|饭前|饭后)[^。！？!?]{0,8}(?:一|二|两|三|\d+)[^。！？!?]{0,4}(?:片|粒|颗|胶囊|mg|毫克)|"
    r"(?:剂量|用量|每次|每天)[^。！？!?]{0,16}(?:mg|毫克|片|粒|胶囊))",
    re.IGNORECASE,
)

# action_id 编码: agenda-{object_type}-{object_id}(与 client_events meta 零翻译)
_ACTION_ID_RE = re.compile(r"^agenda-(?P<ot>[a-z_]+)-(?P<oid>\d+)$")

# source_model → 回写表的 written 标签(响应给 watch,稳定不随幂等变化)
_WRITTEN_BY_SOURCE_MODEL = {
    "medication_logs": "medication_log",
    "supplement_records": "supplement_record",
    "diet_records": "diet_record",
    "water_records": "water_record",
    "exercise_records": "exercise_record",
}


class WatchSkipRequest(BaseModel):
    reason: str | None = "no_time"


class WatchSnoozeRequest(BaseModel):
    minutes: int = Field(30, ge=5, le=240)


class WatchAskIn(BaseModel):
    text: str


def _parse_action_id(action_id: str) -> tuple[str, int]:
    m = _ACTION_ID_RE.match(action_id)
    if not m:
        raise HTTPException(status_code=400, detail="action_id 格式非法")
    return m.group("ot"), int(m.group("oid"))


def _written_label(object_type: str, object_id: int, user_id: int, db: Session) -> str:
    if object_type == "health_protocol":
        p = proto_svc.get_protocol(db, object_id, user_id)
        return _WRITTEN_BY_SOURCE_MODEL.get(p.source_model, "none") if p else "none"
    if object_type in ("medication", "supplement"):
        return "medication_log"
    return "none"


def _watch_ask_needs_phone(text: str) -> bool:
    return bool(_WATCH_ASK_ESCALATE_RE.search(text or ""))


def _watch_ask_needs_medical_attention(text: str) -> bool:
    return bool(_WATCH_ASK_MEDICAL_ATTENTION_RE.search(text or ""))


def _watch_ask_output_unsafe(text: str) -> bool:
    return bool(_WATCH_ASK_UNSAFE_OUTPUT_RE.search(text or ""))


def _limit_watch_ask_answer(text: str) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if not compact:
        return ""
    parts = [p for p in re.split(r"(?<=[。！？!?])", compact) if p.strip()]
    if len(parts) > 2:
        compact = "".join(parts[:2]).strip()
    if len(compact) > 160:
        compact = compact[:157].rstrip() + "..."
    return compact


async def _generate_watch_ask_answer(text: str, current_user: User, db: Session) -> str:
    """Generate the tiny Watch answer through the existing user-aware provider.

    This helper is intentionally separate so tests can replace the LLM without
    weakening the endpoint's safety gates.
    """
    from app.services.llm.factory import create_provider_for_user
    from app.services.llm.usage_tracker import set_caller

    set_caller("watch.ask", user_id=current_user.id)
    provider = create_provider_for_user(current_user.id, db, task_tier="balanced")
    raw = await provider.chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 Reva 的 Apple Watch 健康助理。只用中文回答,最多两句话。"
                    "保持保守,不诊断、不处方、不调整药物或剂量,不输出具体训练/饮食命令。"
                    "如信息不足,引导用户到 iPhone 查看完整详情。"
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.2,
        max_tokens=120,
    )
    return _limit_watch_ask_answer(str(raw or ""))


@router.post("/ask")
async def watch_ask(
    payload: WatchAskIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上一句话问 Reva → 短答 + 安全升级。

    不写健康事实表。user_id 只取 token。请求内禁 build_twin,使用同一 request
    session 的极简 HealthTwin 跑 SafetyGuardian,评估不完整时必须 fail-loud。
    """
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="问题文本不能为空")
    if len(text) > _SYMPTOM_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"问题文本过长(上限 {_SYMPTOM_MAX_LEN} 字)")

    twin = HealthTwin(meta=TwinMeta(user_id=current_user.id, generated_at=datetime.now(UTC)))
    twin.acute.symptom_texts_all = [text]

    evaluation_failed = False
    try:
        builder._fill_problem_red_lines(db, current_user.id, twin, set(), raise_on_error=True)
    except Exception as e:  # noqa: BLE001
        logger.error(
            f"[watch.ask] 个性化红线填充失败(部分 under-alarm 风险),"
            f"标记 evaluation_failed,仍跑通用安全规则兜底: {e}",
            exc_info=True,
        )
        evaluation_failed = True

    alerts: list[Alert] = []
    try:
        alerts, failed = evaluate_rules_with_status(twin)
        if failed > 0:
            logger.error(
                f"[watch.ask] {failed} 条安全规则执行失败被跳过(部分 under-alarm 风险),"
                f"标记 evaluation_failed"
            )
            evaluation_failed = True
    except Exception as e:  # noqa: BLE001
        logger.error(f"[watch.ask] 评估整体失败(fail loud): {e}", exc_info=True)
        evaluation_failed = True

    if evaluation_failed:
        return {
            "answer": _WATCH_ASK_FAIL_LOUD,
            "escalate_to_phone": True,
            "requires_medical_attention": True,
        }

    has_critical = any(int(a.severity) >= int(Severity.CRITICAL) for a in alerts)
    text_needs_phone = _watch_ask_needs_phone(text)
    text_needs_medical_attention = _watch_ask_needs_medical_attention(text)

    if has_critical or text_needs_medical_attention:
        return {
            "answer": _WATCH_ASK_MEDICAL_TEXT,
            "escalate_to_phone": True,
            "requires_medical_attention": True,
        }

    if text_needs_phone:
        return {
            "answer": _WATCH_ASK_ESCALATE_TEXT,
            "escalate_to_phone": True,
            "requires_medical_attention": False,
        }

    try:
        answer = await _generate_watch_ask_answer(text, current_user, db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[watch.ask] LLM 短答失败,升级到 iPhone: {e}", exc_info=True)
        return {
            "answer": _WATCH_ASK_LLM_FALLBACK,
            "escalate_to_phone": True,
            "requires_medical_attention": False,
        }

    sanitized = sanitize_guidance(answer)
    if sanitized.flagged or _watch_ask_output_unsafe(sanitized.text):
        logger.warning(
            "[watch.ask] LLM 短答触发安全后置门,升级到 iPhone: "
            f"violations={len(sanitized.violations)}"
        )
        return {
            "answer": _WATCH_ASK_ESCALATE_TEXT,
            "escalate_to_phone": True,
            "requires_medical_attention": False,
        }

    answer = _limit_watch_ask_answer(sanitized.text)
    if not answer:
        return {
            "answer": _WATCH_ASK_LLM_FALLBACK,
            "escalate_to_phone": True,
            "requires_medical_attention": False,
        }
    return {
        "answer": answer,
        "escalate_to_phone": False,
        "requires_medical_attention": False,
    }


@router.get("/summary")
async def watch_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上摘要(只读投影 agenda.today → watch 优化视图)。

    watch 冷启动 / complication 刷新拉这个:一眼看到今日状态灯 + 最该做的事 +
    打点入口 + 该推到手腕的关键信息(运动/补剂/睡眠/复查)。
    """
    return build_watch_summary(db, current_user.id)


@router.post("/workday/generate")
async def generate_workday_plan(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """显式生成/刷新今天的工作日微运动协议。

    v0 不接位置/日历;调用方可以是 Watch 打开、Mobile 到公司事件或后续定时任务。
    幂等:同一 slot 不重复创建协议。
    """
    return workday_health_scheduler.generate_today(db, current_user.id)


@router.post("/actions/{action_id}/complete")
async def complete_action(
    action_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上「一键已做」→ 完成到点项,完成事实落真实业务表(用药/补剂依从)。

    - user_id 取自 token(绝不信任客户端)。
    - action_id 解析失败 / 不支持来源 → 400(fail loud)。
    - source 不存在或非本人(IDOR)→ 404。
    - 幂等:首次「非完成→完成」才落领域记录;重复 POST 不重复写。
    - 请求内禁 build_twin(本端点只操作协议/领域表)。
    """
    object_type, object_id = _parse_action_id(action_id)

    try:
        result = tas.complete_by_ref(
            db, current_user.id, object_type, object_id,
            status="done", track="protocol", value=None,
        )
    except LookupError:
        # source 不存在 / 非本人(含 IDOR)→ 404。
        raise HTTPException(status_code=404, detail="完成来源不存在")
    except tas.AgendaEventNotFound:
        raise HTTPException(status_code=404, detail="议程事件不存在")
    except tas.AgendaCompleteError as e:
        raise HTTPException(status_code=422, detail=f"完成回写失败: {e}")
    except ValueError as e:
        # 不支持的来源等显式拒绝 → 400。
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "action_id": action_id,
        "object_type": object_type,
        "object_id": object_id,
        "status": "completed",
        "written": _written_label(object_type, object_id, current_user.id, db),
        "event_id": result.get("event_id"),
        "idempotent": bool(result.get("idempotent")),
    }


@router.post("/actions/{action_id}/skip")
async def skip_action(
    action_id: str,
    body: WatchSkipRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上「跳过」→ 标记今日协议 skipped,不写领域完成记录。"""
    object_type, object_id = _parse_action_id(action_id)

    if object_type != "health_protocol":
        raise HTTPException(status_code=400, detail="该来源不支持腕上跳过")

    try:
        ev = proto_svc.skip_protocol(db, object_id, current_user.id, reason=body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if ev is None:
        raise HTTPException(status_code=404, detail="协议不存在")

    return {
        "action_id": action_id,
        "object_type": object_type,
        "object_id": object_id,
        "status": ev.status,
        "skip_reason": ev.skip_reason,
    }


@router.post("/actions/{action_id}/snooze")
async def snooze_action(
    action_id: str,
    body: WatchSnoozeRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上「稍后」→ 暂停今日协议一段时间,到期后重新进入 pending。"""
    object_type, object_id = _parse_action_id(action_id)

    if object_type != "health_protocol":
        raise HTTPException(status_code=400, detail="该来源不支持腕上稍后")

    try:
        ev = proto_svc.snooze_protocol(db, object_id, current_user.id, minutes=body.minutes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if ev is None:
        raise HTTPException(status_code=404, detail="协议不存在")

    value = ev.value or {}
    return {
        "action_id": action_id,
        "object_type": object_type,
        "object_id": object_id,
        "status": ev.status,
        "minutes": value.get("minutes", body.minutes),
        "snoozed_until": value.get("snoozed_until"),
    }


# ─────────────────────────── 王牌⑤ 腕上语音记症状 ───────────────────────────

class SymptomIn(BaseModel):
    text: str


def _audit_symptom_eval(
    db: Session,
    user_id: int,
    symptom_id: int,
    alerts: list,
    evaluation_failed: bool,
) -> None:
    """SafetyGuardian 症状评估的旁路审计 —— 与主流程同一次 commit 落盘。

    隐私(R6):只记 symptom_id / severity / 命中规则,**不存症状原文**。
    旁路:加审计行失败绝不影响主流程(symptom 仍要落库)。
    """
    try:
        from app.models.agent_audit_log import AgentAuditLog

        top = max((int(a.severity) for a in alerts), default=None)
        log = AgentAuditLog(
            user_id=user_id,
            agent_type="safety_guardian",
            action="evaluate",
            result_summary=f"watch symptom #{symptom_id}: {len(alerts)} alerts"
            + (" [EVAL_FAILED]" if evaluation_failed else ""),
            alerts_count=len(alerts),
            result_detail={
                "source": "apple_watch",
                "symptom_id": symptom_id,
                "top_severity": top,
                "rules_hit": [a.rule_id for a in alerts],
                "evaluation_failed": evaluation_failed,
            },
        )
        db.add(log)
    except Exception as e:  # noqa: BLE001
        # 审计是旁路:加行失败不抛,主流程(症状落库)继续。
        logger.warning(f"[watch.symptoms] 审计写入失败(降级): {e}")


def _fail_safe_advisory() -> Alert:
    """安全评估部分/整体未完成时注入的 fail-safe 告警(加层不减层)。

    单一来源已上移到 `engine.make_fail_safe_advisory()`(guardian.evaluate_safety /
    medication_regimen 等所有面共享同一条文案);这里保留薄别名,腕上症状面的现有
    引用与对抗测试(test_watch_symptoms)不变。详见 `make_fail_safe_advisory` 文档。
    """
    return make_fail_safe_advisory()


@router.post("/symptoms")
async def record_symptom(
    payload: SymptomIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上一句话报症状 → 落 SymptomEntry 进时间线 → SafetyGuardian 确定性裁决。

    全场安全 stakes 最高,不变量(docs/design-watch-voice-symptom.md §不变量):
    - R4 不诊断:critical 给就医动作,不给病名结论。
    - critical 真命中才升级(symptoms.py 急症 / P0·P1 个性化红线),普通不适不误升。
    - **不漏报**:评估抛错绝不吞成「已记录无告警」——明确标注 evaluation_failed + 提示就医。
    - 请求内**禁 build_twin**(它自开 SessionLocal,看不到刚 flush 的症状 + 缺列 psycopg2 红)。
    - user_id 取自 token,SymptomEntry 与红线查询都按 token user_id(不信任客户端)。
    - commit 一次性(症状 + 审计)。
    """
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="症状文本不能为空")
    if len(text) > _SYMPTOM_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"症状文本过长(上限 {_SYMPTOM_MAX_LEN} 字)",
        )

    # ① 持久化(flush,不立即 commit):body_part 必填 → watch 自由文本归 "general"
    entry = SymptomEntry(
        user_id=current_user.id,
        description=text,
        body_part="general",
        occurred_at=datetime.now(UTC),
        source="apple_watch",
        # severity 不臆造:watch 一句话无分级,留空(未分级)
    )
    db.add(entry)
    db.flush()  # 拿到 entry.id,症状对后续红线查询可见;尚未 commit

    # ② 评估(严禁 build_twin):极简 twin + 个性化红线(传 request db),只跑确定性规则。
    twin = HealthTwin(meta=TwinMeta(user_id=current_user.id, generated_at=datetime.now(UTC)))
    twin.acute.symptom_texts_all = [text]

    evaluation_failed = False

    # ②a 个性化红线填充(传 request db、只填 acute.problem_red_lines 分区、不自开 session)。
    #   关键(DANGEROUS 修复):_fill_problem_red_lines 默认自带内部 try/except 吞所有异常,
    #   填充失败会静默留空 problem_red_lines。届时 health_problem_red_line 规则因
    #   `if not red_lines: return []` 早返回、不抛异常 → 引擎 failed 仍 0 → 看似绿灯。
    #   对「只有个性化红线能命中、symptoms.py 没写死」的主诉(如视物重影),这就是个性化
    #   安全层静默不响 = under-alarm。故这里用 raise_on_error=True 让填充失败可感知,
    #   置 evaluation_failed(与「单条规则崩」同档:红线没填全 = 安全筛查不完整)。
    try:
        builder._fill_problem_red_lines(db, current_user.id, twin, set(), raise_on_error=True)
    except Exception as e:  # noqa: BLE001
        # 红线填充失败:个性化安全层不完整 → 标记 evaluation_failed。但**不 return**:
        # 仍往下跑 evaluate_rules,让 symptoms.py 等通用急症规则照常兜底(填充失败不该
        # 连通用安全层都不跑)。fail-safe advisory 由 evaluation_failed 统一注入。
        logger.error(
            f"[watch.symptoms] 个性化红线填充失败(部分 under-alarm 风险),"
            f"标记 evaluation_failed,仍跑通用急症规则兜底: {e}",
            exc_info=True,
        )
        evaluation_failed = True

    # ③ 不漏报:评估抛错/部分失败绝不静默当安全。
    #   关键:per-rule try/except 把单条急症规则的崩溃吞成「跳过」,evaluate_rules 仍
    #   返回(可能为空的)alerts、不抛异常。若只在「整体抛异常」时置 evaluation_failed,
    #   单条急症规则崩溃(真心脏事件被静默退化成绿灯)就漏报。故必须看 failed 计数。
    alerts = []
    try:
        alerts, failed = evaluate_rules_with_status(twin)
        if failed > 0:
            # 部分失败:有规则被跳过 → 自动筛查不完整 → 当作 evaluation_failed。
            logger.error(
                f"[watch.symptoms] {failed} 条安全规则执行失败被跳过(部分 under-alarm 风险),"
                f"标记 evaluation_failed"
            )
            evaluation_failed = True
    except Exception as e:  # noqa: BLE001
        # 整体抛异常:安全网完全未完成。症状仍落库(进时间线),但 evaluation_failed 标记让
        # 调用方明确感知「未裁决」,绝不静默冒充「无告警=安全」。
        logger.error(f"[watch.symptoms] 评估整体失败(fail loud): {e}", exc_info=True)
        evaluation_failed = True

    # 不漏报加固:评估未完成时往 alerts 注入 fail-safe advisory(加层不减层),
    # 让**只渲染 alerts[0] 的客户端**也看到安全提示,绝不依赖客户端正确读 flag。
    if evaluation_failed:
        alerts.append(_fail_safe_advisory())

    # severity 降序(advisory HIGH 会排在普通 alert 之上、真 CRITICAL 之下)
    alerts.sort(key=lambda a: int(a.severity), reverse=True)

    # ④ 审计(旁路)+ commit 一次性(症状 + 审计)
    _audit_symptom_eval(db, current_user.id, entry.id, alerts, evaluation_failed)
    try:
        from app.services.ambient_wearables import create_audio_input_event

        create_audio_input_event(
            db,
            current_user.id,
            intent="symptom",
            transcript=text,
            source="apple_watch",
            device_type="watch",
            status="processed",
            target_type="symptom_entry",
            target_id=entry.id,
            safety_result={
                "evaluation_failed": evaluation_failed,
                "alerts_count": len(alerts),
                "top_severity": max((int(a.severity) for a in alerts), default=None),
                "rules_hit": [a.rule_id for a in alerts],
            },
            meta={"entry_source": "watch_symptoms"},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[watch.symptoms] audio input event 写入失败(降级): {e}")
    db.commit()
    db.refresh(entry)

    out_alerts = [
        {
            "severity": {
                "value": int(a.severity),
                "label": a.severity.label,
                "label_zh": a.severity.label_zh,
            },
            "title": a.title,
            "action": a.action,
            "data_citation": a.data_citation,
        }
        for a in alerts
    ]

    if evaluation_failed:
        # 症状已落库,但安全裁决未完成 → 明确告知,不静默当安全。
        # alerts 含已注入的 fail-safe advisory(severity≥HIGH、action 引导就医),
        # 即便客户端只渲染 alerts[0] 也看得到安全提示;evaluation_failed flag 同时保留。
        return {
            "symptom_id": entry.id,
            "alerts": out_alerts,
            "evaluation_failed": True,
            "message": "症状已记录,但本次自动安全评估未能完成。这不代表安全;如有不适请及时就医,情况紧急请拨打 120。",
        }

    message = (
        "已记录症状,未触发安全规则。"
        if not out_alerts
        else "已记录症状,并触发安全提醒,请查看。"
    )
    return {"symptom_id": entry.id, "alerts": out_alerts, "message": message}
