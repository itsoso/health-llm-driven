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
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.safety_guardian.engine import evaluate_rules_with_status
from app.agents.safety_guardian.schema import Alert, Severity
from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.symptom_entry import SymptomEntry
from app.models.user import User
from app.services import agenda_service
from app.services import health_protocol_service as proto_svc
from app.services.watch_summary import build_watch_summary
from app.twin import builder
from app.twin.schema import HealthTwin, TwinMeta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watch", tags=["Apple Watch Companion"])

_SYMPTOM_MAX_LEN = 500

# action_id 编码: agenda-{object_type}-{object_id}(与 client_events meta 零翻译)
_ACTION_ID_RE = re.compile(r"^agenda-(?P<ot>[a-z_]+)-(?P<oid>\d+)$")

# source_model → 回写表的 written 标签(响应给 watch,稳定不随幂等变化)
_WRITTEN_BY_SOURCE_MODEL = {
    "medication_logs": "medication_log",
    "supplement_records": "supplement_record",
    "diet_records": "diet_record",
    "water_records": "water_record",
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


@router.post("/actions/{action_id}/complete")
async def complete_action(
    action_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上「一键已做」→ 完成到点项,完成事实落真实业务表(用药/补剂依从)。

    - user_id 取自 token(绝不信任客户端)。
    - action_id 解析失败 / 非 health_protocol 源 → 400(fail loud)。
    - 协议不存在或非本人(IDOR)→ 404。
    - 幂等:首次「非完成→完成」才落领域记录;重复 POST 不重复写。
    - 请求内禁 build_twin(本端点只操作协议/领域表)。
    """
    m = _ACTION_ID_RE.match(action_id)
    if not m:
        raise HTTPException(status_code=400, detail="action_id 格式非法")
    object_type = m.group("ot")
    object_id = int(m.group("oid"))

    if object_type != "health_protocol":
        raise HTTPException(status_code=400, detail="该来源不支持腕上完成")

    try:
        result = agenda_service.complete_item(
            db, current_user.id, object_type, object_id, track="protocol", value=None
        )
    except ValueError:
        # 仅 health_protocol 走到这里 → 唯一 ValueError 是「协议不存在/非本人」(含 IDOR)
        raise HTTPException(status_code=404, detail="协议不存在")

    # written 标签由协议 source_model 推导(user 过滤,IDOR 安全;不进 build_twin)
    p = proto_svc.get_protocol(db, object_id, current_user.id)
    written = _WRITTEN_BY_SOURCE_MODEL.get(p.source_model, "none") if p else "none"

    return {
        "action_id": action_id,
        "object_type": result["object_type"],
        "object_id": result["object_id"],
        "status": "completed",
        "written": written,
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

    为什么是「注入一条 alert」而不是只置 flag:**绝不让 under-alarm 依赖客户端
    正确读一个可选字段**。只渲染 alerts[0] 的腕上客户端也必须看到安全提示,
    否则「某条急症规则崩了 → alerts 退化成空 → 看似绿灯」就是静默 under-alarm。

    R4 不诊断:这条 advisory 不下任何病名/结论,只如实说「自动筛查未完成、
    如有不适及时就医」—— 给动作不给诊断。severity=HIGH(≥HIGH),稳居就医引导档,
    又不冒称 CRITICAL 急症(我们并不知道到底命没命中急症,只知道筛查没跑全)。
    """
    return Alert(
        rule_id="safety.evaluation_incomplete",
        category="meta",
        severity=Severity.HIGH,
        title="安全评估未完成",
        message="本次自动安全筛查未能完整跑完,无法确认是否存在安全风险。这不代表安全,只代表系统未能完成评估。",
        action="本次未能完成自动安全筛查,请勿据此判断为安全;如有任何不适请及时就医,情况紧急请拨打 120。",
        data_citation={"reason": "rule_engine_partial_or_total_failure"},
        requires_medical_attention=True,
    )


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
