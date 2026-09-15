"""Bounded, non-authorizing context statements shared by intent and delivery.

These are user assertions, not verified location observations or instructions
to write a profile/health record. Unconsumed language must take the ordinary
path; never acknowledge just a matching substring of a larger request.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class ContextStatement:
    kind: str
    place: str

    @property
    def allows_local_reply(self) -> bool:
        # An arbitrary hotel name is only an intent hint, never proof that its
        # free-text slot contains no additional obligation or medical concern.
        return self.kind in {"arrival", "business_trip"}

    @property
    def reply(self) -> str:
        if self.kind == "arrival":
            return f"收到，你已到{self.place}。"
        if self.kind == "business_trip":
            return f"收到，你现在在{self.place}出差。"
        return f"收到，你这次的差旅住处是{self.place}。仅作为本次对话背景，不修改常住地址。"


# City admission is exact against the existing static place catalog below.
# Hotel names remain unverified candidates and always retain normal inference
# and all safety checks; a suffix/character class does not establish semantics.
_PLACE = r"[\u4e00-\u9fffA-Za-z·]{2,30}?"
_LEAD = r"(?:我)?(?:今天|现在)?(?:已经|刚刚|刚|已)?"
_PATTERNS = (
    ("arrival", re.compile(rf"{_LEAD}(?:落地|抵达|到达|到了?)(?P<place>{_PLACE})(?:了)?")),
    ("business_trip", re.compile(rf"(?:我)(?:今天|现在)?(?:在)(?P<place>{_PLACE})(?:出差|差旅)")),
    ("lodging", re.compile(rf"{_LEAD}(?:入住|住在)(?P<place>{_PLACE}(?:酒店|宾馆|旅馆|民宿))(?:了)?")),
    ("lodging", re.compile(rf"(?P<place>{_PLACE}(?:酒店|宾馆|旅馆|民宿))是我(?:今天|今晚|这次|本次)(?:的)?(?:差旅|出差)?(?:居住地|住处|住宿地)")),
    ("lodging", re.compile(rf"我(?:今天|今晚|这次|本次)(?:的)?(?:差旅|出差)?(?:居住地|住处|住宿地)是(?P<place>{_PLACE}(?:酒店|宾馆|旅馆|民宿))")),
)
_NON_PLACE_LANGUAGE = (
    "我", "你", "他", "她", "我们", "然后", "但是", "不过", "并且", "因为", "所以",
    "如果", "可能", "准备", "打算", "计划", "明天", "后天", "昨天", "还没", "不是",
    "帮", "请", "需要", "想", "问", "建议", "分析", "如何", "怎么", "为什么", "是否",
    "记录", "记住", "保存", "删除", "修改", "更新", "同步", "查询", "查看", "取消",
    "胸", "痛", "疼", "晕", "吐", "喘", "痒", "咳", "发烧", "不舒服", "没睡", "睡不",
)


def parse_context_statement(message: str | None) -> ContextStatement | None:
    raw = unicodedata.normalize("NFKC", message or "").strip()
    if not raw or len(raw) > 100 or any(char in raw for char in "\n\r\t"):
        return None
    text = raw.replace(" ", "").rstrip("。.!！")
    for kind, pattern in _PATTERNS:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        place = match.group("place")
        if kind in {"arrival", "business_trip"}:
            from app.services.environment.weather_service import WeatherService

            if place.removesuffix("市") not in WeatherService._CITY_LOCATION_IDS:
                return None
        if any(marker in place for marker in _NON_PLACE_LANGUAGE):
            return None
        # Lazy import keeps the semantic classifier and model-routing module
        # acyclic at import time. The guard itself never classifies an intent.
        from app.services.llm.task_routing import has_sensitive_health_language

        if has_sensitive_health_language(text):
            return None
        return ContextStatement(kind=kind, place=place)
    return None


def context_reply_is_standalone(db, *, user_id: int, conversation_id: int | None,
                                source_message_id: int | None = None) -> bool:
    """Do not intercept an unresolved action or a recent medical follow-up.

    Only read the owned conversation. No health tables, model inference or
    permanent memory extraction are involved. Query failure propagates.
    """
    if conversation_id is None:
        return True
    from app.models.agent_conversation import AgentConversation, AgentMessage

    owned = db.query(AgentConversation).filter(
        AgentConversation.id == conversation_id, AgentConversation.user_id == user_id,
    ).first()
    if owned is None:
        raise ValueError("对话不存在")
    query = db.query(AgentMessage).filter(AgentMessage.conversation_id == owned.id)
    if source_message_id is not None:
        query = query.filter(AgentMessage.id < source_message_id)
    recent = query.order_by(AgentMessage.id.desc()).limit(8).all()
    for item in recent:
        if item.role == "user":
            # Positive admission, not absence of a symptom keyword. Unknown
            # history may hold an unresolved clinical task even when the last
            # assistant forgot to attach a pending-choice marker.
            previous = parse_context_statement(item.content)
            plain_record = re.fullmatch(
                r"(?:记录)?(?:早餐|午餐|晚餐|早饭|午饭|晚饭)|"
                r"(?:记录)?(?:我)?(?:今天)?(?:喝水|喝了水|喝了)(?:[1-9][0-9]{0,3})(?:ml|毫升)",
                unicodedata.normalize("NFKC", item.content or "").strip().rstrip("。.!！"),
                re.IGNORECASE,
            )
            if not ((previous is not None and previous.allows_local_reply) or plain_record):
                return False
    latest_answer = next((item for item in recent if item.role == "assistant"), None)
    if latest_answer is not None:
        meta = latest_answer.meta or {}
        outcome = meta.get("turn_outcome") or {}
        if re.search(r"[?？]|请补充|请提供|说一下|告诉我|你在哪|你现在在哪|是否|吗|呢", latest_answer.content or ""):
            return False
        if (meta.get("pending_choice") or meta.get("health_fact_draft")
                or outcome.get("confirmation_required")
                or outcome.get("status") in {"waiting_for_user", "reconciliation_required"}):
            return False
    return True
