"""Internal, scoped attestation for reusing one already validated report.

No receipt is inferred from tool JSON. Orchestrator code records the actual
provider and validator results, and the caller consumes the exact sealed object.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import re
from typing import Iterator
import unicodedata

from app.services.episode.validator import TextValidationResult

_SINGLE_REPORT = re.compile(
    r"(?:请帮我|帮我|请)?(?:综合|深度|全面)(?:分析|评估)(?:一下)?"
    r"(?:我的健康|(?:我的)?恢复)(?:状况|情况)?[。.!！?？]?"
)
# Conservative reuse veto, not semantic citation verification. Ambiguous external
# attributions retain the normal synthesis/citation path and clinical validator.
_PERSONAL_RECORD_WINDOW = (
    r"(?:(?:近|最近|过去)(?:[1-9][0-9]?|[一二两三四五六七八九十]{1,3})(?:天|周|个月)|"
    r"今天|今日|昨天|昨日|昨晚|本周|上周|本月|上个月)"
)
_PERSONAL_RECORD_SOURCE = (
    rf"你(?:的(?:记录|数据)|(?:的)?{_PERSONAL_RECORD_WINDOW}的(?:记录|数据))"
)
_CITATION = re.compile(
    r"(?:://|https?\s*:|www\.|"
    r"\.[a-z]{2,63}(?:\b|/)|"
    r"\bdoi\b|\b10\.\d{4,9}/|claim|citation|pubmed|pmid|"
    r"文献|论文|研究|参考|指南|来源|出处|源自|引自|援引|引用|发表于|刊登|资料来自|"
    r"协会|学会|机构|组织|期刊|杂志|医院|大学|实验室|医生|医师|专家|教授|学者|科学家|"
    rf"(?:根据|依据)(?!{_PERSONAL_RECORD_SOURCE})|"
    r"(?:^|[。！？!?；;，,\n])\s*据|"
    r"(?<![a-z])(?:who|cdc|nih|nice|nhs|aha|aasm|acc|esc|ada|bmj|jama|"
    r"nejm|lancet|cochrane|nature|science)(?![a-z])|"
    r"\b(?:according\s+to|sources?|research|studies|study|experts?|physicians?|"
    r"doctors?|professors?|association|society|journal|institute|university|organization)\b|"
    r"[a-z]{2,10}\s*(?:建议|表示|认为|推荐|报道)|"
    r"\[[^\]\n]*\d[^\]\n]*\]|【[^】\n]*\d[^】\n]*】|"
    r"\[[^\]\n]+\]\(|[（(][^\n()（）]*(?:19|20)\d{2}[^\n()（）]*[)）]|"
    r"||\b(?:arxiv|references|et\s+al)\b)",
    re.IGNORECASE,
)


def is_single_report_request(question: str) -> bool:
    if type(question) is not str or len(question) > 80:
        return False
    return _SINGLE_REPORT.fullmatch(unicodedata.normalize("NFKC", question).strip()) is not None


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    user_id: int
    turn_id: str
    tool_call_id: str
    query: str
    text: str
    model: str


class ReportCapture:
    """Mutable internal recorder; all events must belong to its active scope."""

    def __init__(self, user_id: int, turn_id: str, tool_call_id: str, question: str):
        self._user_id = user_id
        self._turn_id = turn_id
        self._tool_call_id = tool_call_id
        self._question = question
        self._generation_count = 0
        self._validation_count = 0
        self._text: str | None = None
        self._model: str | None = None
        self._invalid = False
        self._closed = False
        self._sealed = False
        self._consumed = False
        self._receipt: DeliveryReceipt | None = None

    @property
    def receipt(self) -> DeliveryReceipt | None:
        return self._receipt

    @property
    def user_id(self) -> int:
        return self._user_id

    def invalidate(self) -> None:
        """Poison reuse when an upstream stage recovered from an error."""
        self._invalidate()

    def _active(self) -> bool:
        return current_report_capture() is self and not self._closed and not self._invalid

    def _invalidate(self) -> None:
        self._invalid = True
        self._receipt = None

    def record_generation(self, result: object, model: str) -> None:
        self._generation_count += 1
        if (
            not self._active() or self._sealed or self._generation_count != 1
            or type(result) is not dict
            or type(result.get("finish_reason")) is not str or result["finish_reason"] != "stop"
            or type(result.get("content")) is not str or not result["content"].strip()
            or (result.get("tool_calls") is not None and not (
                type(result["tool_calls"]) is list and len(result["tool_calls"]) == 0
            ))
            or result.get("function_call") is not None
            or type(model) is not str or not model.strip()
        ):
            self._invalidate()
            return
        self._text = result["content"]
        self._model = model

    def record_validation(self, text: str, result: object) -> None:
        self._validation_count += 1
        if (
            not self._active() or self._sealed or self._validation_count != 1
            or self._generation_count != 1 or type(text) is not str or text != self._text
            or type(result) is not TextValidationResult
            or result.ok is not True or type(result.action) is not str or result.action != "pass"
            or type(result.safe_text) is not str or result.safe_text != text
            or type(result.disclaimer) is not str or result.disclaimer != ""
            or type(result.matched_terms) is not list or result.matched_terms != []
        ):
            self._invalidate()

    def seal(
        self, query: str, text: str, *, evidence_complete: bool,
        mode: str, persisted_card_ids: list,
    ) -> DeliveryReceipt | None:
        if (
            not self._active() or self._sealed
            or not is_single_report_request(self._question)
            or type(query) is not str or query != self._question
            or type(text) is not str or text != self._text
            or evidence_complete is not True or type(mode) is not str or mode != "off"
            or type(persisted_card_ids) is not list or persisted_card_ids
            or self._generation_count != 1 or self._validation_count != 1
            or self._model is None or _CITATION.search(unicodedata.normalize("NFKC", text))
        ):
            self._invalidate()
            return None
        self._sealed = True
        self._receipt = DeliveryReceipt(
            self._user_id, self._turn_id, self._tool_call_id, query, text, self._model,
        )
        return self._receipt

    def consume(self, receipt: object) -> DeliveryReceipt | None:
        if (
            not self._active() or self._consumed or self._receipt is None
            or type(receipt) is not DeliveryReceipt or receipt is not self._receipt
        ):
            return None
        self._consumed = True
        return self._receipt


_CURRENT_CAPTURE: ContextVar[ReportCapture | None] = ContextVar("orchestrator_report_capture", default=None)


def current_report_capture() -> ReportCapture | None:
    return _CURRENT_CAPTURE.get()


@contextmanager
def capture_report(
    user_id: int, turn_id: str, tool_call_id: str, question: str,
) -> Iterator[ReportCapture]:
    if type(user_id) is not int or user_id <= 0 or any(
        type(value) is not str or not value.strip() for value in (turn_id, tool_call_id, question)
    ):
        raise ValueError("invalid_report_capture_identity")
    capture = ReportCapture(user_id, turn_id, tool_call_id, question)
    token = _CURRENT_CAPTURE.set(capture)
    try:
        yield capture
    finally:
        capture._closed = True
        _CURRENT_CAPTURE.reset(token)
