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
    flight_time: str | None = None
    flight_event: str | None = None
    expected: bool = False

    @property
    def allows_local_reply(self) -> bool:
        # An arbitrary hotel name is only an intent hint, never proof that its
        # free-text slot contains no additional obligation or medical concern.
        return self.kind in {"arrival", "business_trip", "gate_arrival", "transit_timeline"}

    @property
    def reply(self) -> str:
        if self.kind == "transit_timeline":
            return (
                f"赶上了，你说的是{self.flight_time}出发的地铁。"
                "这条作为本次对话里的出行叙述；没有查询健康数据或新增记录，"
                "也没有重试前面的未完成请求。"
            )
        if self.kind == "gate_arrival":
            reply = f"收到，你已到{self.place}。"
            if self.flight_time is not None:
                qualifier = "预计" if self.expected else ""
                reply += f"你补充的{qualifier}{self.flight_event}时间是{self.flight_time}。"
            return reply
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
# Exact bounded gate/clock syntax, not arbitrary travel-looking free text.
# A stated clock is echoed without inferring a date, timezone or completion.
_GATE_ARRIVAL = re.compile(
    rf"{_LEAD}(?:抵达|到达|到了)(?P<place>[A-Z]?[1-9][0-9]{{0,2}}(?:号门|号?登机口))"
    r"(?:了)?(?:[,，;；]?(?P<expected>预计)?"
    r"(?P<time>(?:[01][0-9]|2[0-3]):[0-5][0-9])(?P<event>降落|落地|起飞))?"
)
_CLOCK = r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]"
_TRANSIT_TIMELINE = re.compile(
    rf"(?:我)?赶上了(?P<departure>{_CLOCK})从(?P<origin>[\u4e00-\u9fff]{{2,12}})"
    r"出发去(?P<destination>[\u4e00-\u9fff]{2,12}机场)(?:T[1-9])?的"
    r"[1-9][0-9]?号地铁[，,。;；]?"
    rf"{_CLOCK}从家里出发[，,。;；]?{_CLOCK}到达地铁口[，,。;；]?"
    rf"(?:冲下来才能赶上[，,。;；]?)?{_CLOCK}起床洗了个澡"
)
_PATTERNS = (
    ("arrival", re.compile(rf"{_LEAD}(?:落地|抵达|到达|到了)(?P<place>{_PLACE})(?:了)?")),
    ("arrival", re.compile(rf"{_LEAD}到(?P<place>{_PLACE})了")),
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


def _known_context_places() -> set[str]:
    """Admit exact city/facility phrases, never free text ending in 机场."""
    from app.services.environment.weather_service import WeatherService

    cities = set(WeatherService._CITY_LOCATION_IDS) | {"香港", "澳门", "台北"}
    return {city + suffix for city in cities
            for suffix in ("", "市", "机场", "国际机场", "火车站", "高铁站", "口岸")}


def parse_context_statement(message: str | None) -> ContextStatement | None:
    raw = unicodedata.normalize("NFKC", message or "").strip()
    if not raw or len(raw) > 100 or any(char in raw for char in "\n\r\t"):
        return None
    text = raw.replace(" ", "").rstrip("。.!！")
    transit = _TRANSIT_TIMELINE.fullmatch(text)
    if transit is not None:
        from app.services.llm.task_routing import has_sensitive_health_language

        places = transit.group("origin") + transit.group("destination")
        if any(marker in places for marker in _NON_PLACE_LANGUAGE) or has_sensitive_health_language(text):
            return None
        # Place strings are not verified locations and are never echoed,
        # persisted as a trip, or used to grant any health read/write scope.
        return ContextStatement(kind="transit_timeline", place="", flight_time=transit.group("departure"))
    gate = _GATE_ARRIVAL.fullmatch(text)
    if gate is not None:
        return ContextStatement(
            kind="gate_arrival", place=gate.group("place"),
            flight_time=gate.group("time"), flight_event=gate.group("event"),
            expected=gate.group("expected") is not None,
        )
    for kind, pattern in _PATTERNS:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        place = match.group("place")
        if kind in {"arrival", "business_trip"}:
            if place not in _known_context_places():
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


def _is_closed_trip_pair(source, answer) -> bool:
    """Only a completed owned trip receipt closes the preceding write task."""
    from app.services.write_intent_scope import current_turn_trip_payload
    from app.services.llm.task_routing import has_sensitive_health_language

    if (source.role != "user" or answer.role != "assistant"
            or current_turn_trip_payload(source.content) is None
            or has_sensitive_health_language(source.content or "")):
        return False
    meta = answer.meta or {}
    if not isinstance(meta, dict):
        return False
    outcome = meta.get("turn_outcome") or {}
    source_meta = source.meta or {}
    if not isinstance(outcome, dict) or not isinstance(source_meta, dict):
        return False
    write_state = source_meta.get("write_state") or {}
    if not isinstance(write_state, dict) or write_state.get("status") not in {None, "verified"}:
        return False
    receipts = meta.get("write_receipts")
    closed_text = (answer.content or "").strip().replace(" ", "").rstrip("。.!！")
    return bool(
        closed_text in {"✅已记录", "已记录", "行程已记录"}
        and meta.get("client_turn_finalized") is True
        and meta.get("completion_status") == "complete"
        and outcome.get("status") == "complete"
        and not outcome.get("confirmation_required")
        and not meta.get("pending_choice") and not meta.get("health_fact_draft")
        and isinstance(receipts, list) and len(receipts) == 1
        and isinstance(receipts[0], dict)
        and receipts[0].get("verified") is True
        and receipts[0].get("status") == "verified"
        and receipts[0].get("action") == "create"
        and receipts[0].get("resource_type") == "health_episode"
        and str(receipts[0].get("resource_id") or "").isdigit()
    )


def context_reply_is_standalone(db, *, user_id: int, conversation_id: int | None) -> bool:
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
    recent = query.order_by(AgentMessage.id.desc()).limit(8).all()
    closed_trip_answers = {
        recent[index - 1].id for index, item in enumerate(recent) if index > 0
        and _is_closed_trip_pair(item, recent[index - 1])
    }
    for index, item in enumerate(recent):
        if item.role == "user":
            if item.image_url or any((item.meta or {}).get(key) for key in (
                "images", "attachments", "file_name", "file_base64", "extra_context",
            )):
                return False
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
            closed_trip = index > 0 and recent[index - 1].id in closed_trip_answers
            if not ((previous is not None and previous.allows_local_reply) or plain_record or closed_trip):
                return False
    latest_answer = next((item for item in recent if item.role == "assistant"), None)
    if latest_answer is not None:
        meta = latest_answer.meta or {}
        outcome = meta.get("turn_outcome") or {}
        if (meta.get("pending_choice") or meta.get("health_fact_draft")
                or outcome.get("confirmation_required")
                or outcome.get("status") in {"waiting_for_user", "reconciliation_required"}):
            return False
        # Unknown assistant prose may ask for a continuation without a question
        # mark. Admit only complete, closed acknowledgements or our exact
        # inert guard refusal, never absence of a question/symptom keyword.
        from app.services.guidance_validator import _ADVICE_HOLD

        answer = (latest_answer.content or "").strip()
        known_ack = any(answer == ContextStatement(kind, place).reply
                        for place in _known_context_places()
                        for kind in ("arrival", "business_trip"))
        # Gate replies contain bounded user-supplied clocks. Match the actual
        # owned prior statement, never arbitrary assistant prose or a prefix.
        known_ack = known_ack or any(
            item.role == "user"
            and (statement := parse_context_statement(item.content)) is not None
            and statement.kind == "gate_arrival" and answer == statement.reply
            for item in recent
        )
        plain_receipt = re.fullmatch(r"(?:早餐|午餐|晚餐)记录已保存。", answer)
        guard_refusal = answer in {
            _ADVICE_HOLD,
            "信息来源：用户陈述、模型推断。\n" + _ADVICE_HOLD,
            "信息来源：用户陈述、已检索证据（未逐句核验）、模型推断。\n" + _ADVICE_HOLD,
            "信息来源：上下文信息（未逐项核验）、模型推断。\n" + _ADVICE_HOLD,
            "信息来源：上下文信息（未逐项核验）、已检索证据（未逐句核验）、模型推断。\n" + _ADVICE_HOLD,
        }
        if not (known_ack or plain_receipt or guard_refusal or latest_answer.id in closed_trip_answers):
            return False
    return True
