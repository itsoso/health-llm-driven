"""Shared speech-act parser for deterministic health-write authorization."""
from __future__ import annotations

import re
import unicodedata

from app.services.utterance_intent_lexicon import (
    QUESTION_SIGNALS,
    READ_ACTIONS,
    RECORD_NOUN_SUFFIXES,
    STRUCTURAL_WRITE_NEGATIONS,
    WRITE_ACTIONS,
    WRITE_COMMAND_ACTIONS,
    WRITE_COMMAND_PREFIXES,
    WRITE_NEGATION_EXCEPTIONS,
)

_CLAUSE_BOUNDARY_RE = re.compile(
    r"[，,。.!！；;]|但是|但|不过|然而|可是|只是|却|而是|"
    r"是(?=请(?:你)?)|然后|接着|随后|"
    r"(?<=.)(?=请(?:你)?"
    r"(?:记录|记一下|记下|打个卡|打卡|新增|录入|保存|写入|存下来))"
)
_CONTEXTUAL_DENIAL_COMMA_RE = re.compile(
    r"((?:没有|没|未|未经|无).{0,12}(?:同意|授权|许可|允许)"
    r".{0,8}(?:情况下|情形下|前提下))[，,]"
)
_CAPABILITY_INQUIRY_PREFIXES = (
    "我想问一下",
    "我想问",
    "想问一下",
    "想问",
    "请问一下",
    "请问",
    "我想知道",
    "想知道",
    "请告诉我",
    "告诉我",
    "我想了解",
    "想了解",
    "我想确认",
    "想确认",
    "请确认",
    "确认",
    "请说明",
    "说明",
)
_CAPABILITY_SUBJECTS = (
    "这个功能",
    "该功能",
    "这个系统",
    "该系统",
    "这个服务",
    "该服务",
    "这个应用",
    "该应用",
    "这个助手",
    "该助手",
    "系统",
    "小巴",
    "应用",
    "平台",
    "这个",
    "它",
)
_CAPABILITY_MODALS = (
    "可不可以",
    "能不能",
    "会不会",
    "是否会",
    "有没有",
    "具不具备",
    "具备",
    "可以",
    "能否",
    "可否",
    "支持",
    "会",
    "能",
)
_NON_NEGATING_MODALS = (
    "可不可以",
    "能不能",
    "该不该",
    "要不要",
    "不得不",
    "不能不",
    "不妨",
)
_NEGATION_LEXICAL_CONTAINERS = (
    "分别",
    "区别",
    "性别",
    "个别",
    "特别",
    "类别",
    "级别",
    "识别",
    "鉴别",
    "告别",
)
_POSITIVE_REMINDER_RE = re.compile(r"(?:不要|别|勿|甭)(?:忘记|忘了|忘)")
_NEGATED_CONTROL_RE = re.compile(
    r"(?:不|没有|没|未曾|未|未经|无).{0,3}"
    r"(?:同意|允许|授权|许可|准许|要求|希望|愿意|乐意|打算|考虑|"
    r"接受|赞成|想|让|叫|肯)"
)
_DIRECT_DENIAL_SCOPE_RE = re.compile(
    r"(?:反对|抗拒|抵制).{0,12}(?:让|由|帮我|替我|为我)"
)
_HISTORY_NOUN_TERMS = ("历史", "列表", "汇总")
_PAST_TIME_TERMS = (
    "以前",
    "上一次",
    "上次",
    "上回",
    "之前",
    "刚才",
    "刚刚",
    "方才",
    "昨天",
    "前天",
    "大前天",
    "上周",
    "上个月",
    "去年",
    "那次",
    "当时",
    "此前",
    "先前",
    "早先",
    "最近一次",
    "既往",
    "曾经",
)
_HISTORY_TERMS = (*_HISTORY_NOUN_TERMS, *_PAST_TIME_TERMS)
_COMPLETED_TAILS = ("了", "过", "没有", "没")
_NON_ASPECT_GUARDS = ("过敏", "过量", "过高", "过低", "过去", "过程")
_COMPLETION_TRAILING_PARTICLES = "?？啊呀呢么嘛吗"
_POST_ACTION_DENIAL_RE = re.compile(
    r"(?:还是)?(?:算了(?:吧)?|取消(?:吧|了|这件事)?|撤销(?:吧|了)?|撤回|"
    r"暂缓|搁置|缓一缓|先缓缓|推迟|等一下再说|先放一放|作罢|就免了|免了|"
    r"先不要了|不要了|未获授权|没有授权|未经授权|不被允许|"
    r"是不允许的?|是不可以的?|不允许|我不同意|不行)"
)
_TRAILING_REVOCATION_CLAUSE_RE = re.compile(
    r"^(?:还是)?(?:算了(?:吧)?|取消(?:吧|了|这件事)?|撤销(?:吧|了)?|撤回|"
    r"暂缓|搁置|缓一缓|先缓缓|推迟|等一下再说|先放一放|"
    r"(?:这件事)?作罢|先不要了|不要了|我不同意|不行)$"
)
_RESULT_CHECK_LEADS = (
    "确认",
    "核对",
    "查查",
    "检查",
    "验证",
    "查看",
    "看看",
    "查一下",
)
_RESULT_STATE_MARKERS = ("有没有", "是否", "是否已", "是否已经", "已经", "已")
_RESULT_TAIL_MARKERS = ("成功", "完成", "生效", "写进", "写到", "存进", "存到")
_REPORTING_VERBS = (
    "说",
    "表示",
    "称",
    "写着",
    "写道",
    "提到",
    "显示",
    "提示",
    "转告",
    "转述",
    "复述",
    "引用",
    "告诉",
    "告知",
)
_METALANGUAGE_ACTIONS = (
    "转述",
    "复述",
    "翻译",
    "解释这句话",
    "引用",
    "举例",
    "例子",
    "例如",
    "比如",
    "譬如",
    "假设",
    "假定",
    "模拟场景",
    "这句话",
    "是什么意思",
)
_BACKFILL_DATE_SIGNALS = (
    "发作日期",
    "开始日期",
    "起病日期",
    "发生日期",
    "日期是",
    "日期为",
    "时间是",
    "时间为",
)
_BACKFILL_REQUEST_MARKERS = (
    "请",
    "帮我",
    "把",
    "麻烦",
    "替我",
    "给我",
    "为我",
    "补充",
)
_DIRECT_REQUEST_HELPERS = (
    "别忘了",
    "我想请你",
    "我想让你",
    "我希望你",
    "我需要你",
    "我想请",
    "麻烦帮我",
    "麻烦你",
    "请你",
    "帮我",
    "帮忙",
    "给我",
    "替我",
    "为我",
    "麻烦",
    "劳烦",
    "请",
    "我想",
    "希望",
    "需要",
    "想",
    "能帮我",
    "可以帮我",
)
_DIRECT_REQUEST_MODIFIERS = (
    "可不可以",
    "能不能",
    "不得不",
    "不能不",
    "不妨",
    "可以",
    "能否",
    "可否",
    "能",
    "分别",
    "顺便",
    "现在",
    "立即",
    "马上",
    "主动",
    "务必",
    "然后",
    "再",
    "先",
    "就",
    "你",
)
_VOCATIVE_PREFIXES = ("小巴你", "小巴", "助手你", "助手")
_DENIAL_SCOPE_INTRO_ENDINGS = (
    "执行",
    "执行以下操作",
    "执行如下操作",
    "以下操作",
    "如下操作",
    "这些操作",
    "这项操作",
    "以下行为",
    "如下行为",
    "这些行为",
    "这项行为",
    "以下事项",
    "如下事项",
    "以下内容",
    "如下内容",
    "以下动作",
    "如下动作",
    "这件事",
    "该件事",
    "这回事",
)
_DIRECT_DENIAL_PREDICATES = (
    "禁止",
    "严禁",
    "拒绝",
    "避免",
    "杜绝",
    "停止",
    "暂停",
    "终止",
    "取消",
    "撤销",
    "放弃",
    "谢绝",
)
_ORDERED_WRITE_ACTIONS = tuple(sorted(WRITE_COMMAND_ACTIONS, key=len, reverse=True))
_ORDERED_WRITE_SIGNALS = tuple(sorted(WRITE_ACTIONS, key=len, reverse=True))
_ORDERED_NEGATIONS = tuple(sorted(STRUCTURAL_WRITE_NEGATIONS, key=len, reverse=True))
_ORDERED_NON_NEGATING_MODALS = tuple(
    sorted(_NON_NEGATING_MODALS, key=len, reverse=True)
)


def normalize_write_scope_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(normalized.split()).lower()


def split_write_clauses(value: str) -> tuple[str, ...]:
    text = normalize_write_scope_text(value)
    text = _CONTEXTUAL_DENIAL_COMMA_RE.sub(r"\1", text)
    colon_scoped: list[str] = []
    current = ""
    for character in text:
        if character not in ("：", ":"):
            current += character
            continue
        if _colon_extends_denial_scope(current):
            continue
        if current:
            colon_scoped.append(current)
        current = ""
    if current:
        colon_scoped.append(current)
    return tuple(
        clause
        for segment in colon_scoped
        for clause in _CLAUSE_BOUNDARY_RE.split(segment)
        if clause
    )


def _colon_extends_denial_scope(left: str) -> bool:
    if any(predicate in left for predicate in _DIRECT_DENIAL_PREDICATES):
        return True
    if not any(negation in left for negation in _ORDERED_NEGATIONS):
        return False
    return left.endswith(_DENIAL_SCOPE_INTRO_ENDINGS)


def _clean_negation_clause(raw_clause: str) -> str:
    clause = raw_clause
    for exception in WRITE_NEGATION_EXCEPTIONS:
        clause = clause.replace(exception, "")
    clause = _POSITIVE_REMINDER_RE.sub("", clause)
    for container in _NEGATION_LEXICAL_CONTAINERS:
        clause = clause.replace(container, "")
    for modal in _ORDERED_NON_NEGATING_MODALS:
        clause = clause.replace(modal, "")
    return clause


def _last_action_in_clause(clause: str) -> tuple[str, int] | None:
    context: tuple[str, int] | None = None
    for action in _ORDERED_WRITE_ACTIONS:
        start = clause.rfind(action)
        if start < 0:
            continue
        if context is None or start > context[1]:
            context = (action, start)
    return context


def _last_write_signal_in_clause(clause: str) -> tuple[str, int] | None:
    context: tuple[str, int] | None = None
    for signal in _ORDERED_WRITE_SIGNALS:
        start = clause.rfind(signal)
        if start < 0:
            continue
        if context is None or start > context[1]:
            context = (signal, start)
    return context


def _last_write_action_context(value: str) -> tuple[str, str, int] | None:
    last_context: tuple[str, str, int] | None = None
    for clause in split_write_clauses(value):
        action_context = _last_action_in_clause(clause)
        if action_context is not None:
            action, start = action_context
            last_context = (clause, action, start)
    return last_context


def _starts_with_completed_aspect(after_action: str) -> bool:
    if after_action.startswith("了"):
        return True
    return after_action.startswith("过") and not after_action.startswith(
        _NON_ASPECT_GUARDS
    )


def _write_clause_denials(value: str) -> tuple[bool, ...]:
    text = normalize_write_scope_text(value)
    if not text:
        return ()

    denials: list[bool] = []
    for raw_clause in split_write_clauses(text):
        clause = _clean_negation_clause(raw_clause)
        action_context = _last_write_signal_in_clause(clause)
        if action_context is None:
            if (
                denials
                and _TRAILING_REVOCATION_CLAUSE_RE.fullmatch(clause)
            ):
                denials[-1] = True
            continue
        _action, action_position = action_context
        before_action = clause[:action_position]
        after_action = clause[action_position:]
        denials.append(
            bool(
                any(
                    clause.find(negation, 0, action_position) >= 0
                    for negation in _ORDERED_NEGATIONS
                )
                or _NEGATED_CONTROL_RE.search(before_action)
                or _DIRECT_DENIAL_SCOPE_RE.search(before_action)
                or _POST_ACTION_DENIAL_RE.search(after_action)
            )
        )
    return tuple(denials)


def has_negated_write_scope(value: str) -> bool:
    """Return whether the governing write-bearing clause denies authorization.

    Contrast clauses are evaluated in order. A later positive write clause can
    supersede an earlier refusal, while a trailing revocation applies to the
    most recent write clause.
    """
    denials = _write_clause_denials(value)
    return bool(denials and denials[-1])


def has_mixed_write_polarity(value: str) -> bool:
    """Return true when denied and authorized write clauses coexist."""
    denials = _write_clause_denials(value)
    return any(denials) and any(not denied for denied in denials)


def is_write_capability_question(value: str) -> bool:
    """Recognize product-capability questions without treating them as requests."""
    context = _last_write_action_context(value)
    if context is None:
        return False
    clause, action, action_position = context
    before_action = clause[:action_position]
    after_action = clause[action_position + len(action):]
    has_inquiry_cue = any(
        cue in before_action for cue in _CAPABILITY_INQUIRY_PREFIXES
    )
    subject_match = min(
        (
            (position, candidate)
            for candidate in _CAPABILITY_SUBJECTS
            if (position := before_action.find(candidate)) >= 0
        ),
        default=None,
    )
    if subject_match is None:
        return has_inquiry_cue and (
            any(signal.lower() in clause for signal in QUESTION_SIGNALS)
            or any(modal in before_action for modal in _CAPABILITY_MODALS)
        )
    subject_position, subject = subject_match
    after_subject = clause[subject_position + len(subject):]
    subject_action_position = after_subject.find(action)
    if subject_action_position < 0:
        return False
    before_subject_action = after_subject[:subject_action_position]
    if (
        subject == "小巴"
        and not has_inquiry_cue
        and (
            "你能帮我" in before_action
            or "你可以帮我" in before_action
            or after_action.startswith(("一下", "下来"))
        )
    ):
        return False
    return has_inquiry_cue or any(
        modal in before_subject_action for modal in _CAPABILITY_MODALS
    )


def _is_explicit_dated_backfill(value: str) -> bool:
    text = normalize_write_scope_text(value)
    if not any(term in text for term in _HISTORY_TERMS):
        return False
    if not (
        any(signal in text for signal in _BACKFILL_DATE_SIGNALS)
        or any(term in text for term in _PAST_TIME_TERMS)
    ):
        return False
    if any(signal in text for signal in QUESTION_SIGNALS):
        return False
    for clause in split_write_clauses(text):
        candidates: list[tuple[int, str]] = []
        for action in _ORDERED_WRITE_ACTIONS:
            start = clause.find(action)
            while start >= 0:
                candidates.append((start, action))
                start = clause.find(action, start + len(action))
        for action_position, action in sorted(candidates):
            before_action = clause[:action_position]
            after_action = clause[action_position + len(action):]
            if action == "记录" and (
                after_action.startswith(RECORD_NOUN_SUFFIXES)
                or (
                    not after_action
                    and any(
                        earlier_position < action_position
                        for earlier_position, _earlier_action in candidates
                    )
                )
            ):
                continue
            if (
                action_position == 0
                or before_action.endswith(_BACKFILL_REQUEST_MARKERS)
                or after_action.startswith(("一下", "下来"))
            ):
                return True
    return False


def is_historical_write_reference(value: str) -> bool:
    """Recognize completion and historical/list noun frames for the last action."""
    if _is_explicit_dated_backfill(value):
        return False
    context = _last_write_action_context(value)
    if context is None:
        return False
    clause, action, start = context
    after = clause[start + len(action):]
    if _starts_with_completed_aspect(after):
        return True
    completed_tail = after.rstrip(_COMPLETION_TRAILING_PARTICLES)
    if completed_tail.endswith(_COMPLETED_TAILS):
        return True
    if any(term in clause for term in _HISTORY_NOUN_TERMS):
        return True
    has_question = any(signal.lower() in clause for signal in QUESTION_SIGNALS)
    return any(
        (term_position := clause.find(term)) >= 0
        and (term_position < start or has_question)
        for term in _PAST_TIME_TERMS
    )


def is_read_action_write_reference(value: str) -> bool:
    """Return true when a read verb governs a later write-action noun."""
    context = _last_write_action_context(value)
    if context is None:
        return False
    clause, _action, start = context
    return any(
        (read_position := clause.find(read_action)) >= 0 and read_position < start
        for read_action in READ_ACTIONS
    )


def is_write_result_check(value: str) -> bool:
    """Recognize checks of an earlier write's completion or persistence state."""
    context = _last_write_action_context(value)
    if context is None:
        return False
    clause, action, start = context
    before_action = clause[:start]
    after_action = clause[start + len(action):]
    has_check_lead = any(cue in before_action for cue in _RESULT_CHECK_LEADS)
    has_state = any(marker in before_action for marker in _RESULT_STATE_MARKERS)
    has_result_tail = any(marker in after_action for marker in _RESULT_TAIL_MARKERS)
    return (has_check_lead and (has_state or has_result_tail)) or (
        has_result_tail and any(signal in clause for signal in QUESTION_SIGNALS)
    )


def is_reported_write_reference(value: str) -> bool:
    """Recognize attributed, quoted, or metalinguistic write language."""
    text = normalize_write_scope_text(value)
    if any(mark in text for mark in ('"', "“", "「", "『")) and any(
        mark in text for mark in ('"', "”", "」", "』")
    ):
        return True

    clauses = split_write_clauses(text)
    if not clauses:
        return False
    signal_index = next(
        (
            index
            for index in range(len(clauses) - 1, -1, -1)
            if _last_write_signal_in_clause(clauses[index]) is not None
        ),
        len(clauses) - 1,
    )
    candidate_indices = (signal_index - 1, signal_index)
    for index in candidate_indices:
        if index < 0:
            continue
        segment = clauses[index]
        signal = (
            _last_write_signal_in_clause(segment)
            if index == signal_index
            else None
        )
        before_signal = segment[:signal[1]] if signal is not None else segment
        if any(action in before_signal for action in _METALANGUAGE_ACTIONS):
            return True
        for verb in _REPORTING_VERBS:
            verb_position = before_signal.find(verb)
            if verb_position < 0:
                continue
            subject = before_signal[:verb_position]
            if (
                subject
                and not any(negation in subject for negation in _ORDERED_NEGATIONS)
                and _strip_direct_request_prefix(subject)
            ):
                return True
    return False


def governing_authorized_write_clause(value: str) -> str | None:
    """Return the concrete current clause that owns health-write authority.

    The result is intentionally clause-scoped.  It never returns quoted,
    reported, historical, denied, result-check, or revoked language.  Callers
    can classify this clause to bind a tool request to its concrete target
    instead of inheriting a boolean authorization from the whole turn.
    """
    text = normalize_write_scope_text(value)
    if not text or has_negated_write_scope(text):
        return None
    if (
        is_write_capability_question(text)
        or is_historical_write_reference(text)
        or is_read_action_write_reference(text)
        or is_write_result_check(text)
        or is_reported_write_reference(text)
    ):
        return None

    clauses = split_write_clauses(text)
    for clause in reversed(clauses):
        if _last_write_signal_in_clause(clause) is not None:
            if _last_action_in_clause(clause) is not None and not (
                has_explicit_authorizing_write_request(text)
            ):
                return None
            return clause

    # Metric, symptom and event observations can be write speech acts without
    # a lexical write verb.  The intent frame decides whether that final clause
    # is an observation; this parser only guarantees direct provenance.
    return clauses[-1] if clauses else None


def has_write_action_mention(value: str) -> bool:
    """Return whether user text mentions a registered health-write action."""
    text = normalize_write_scope_text(value)
    return any(action in text for action in _ORDERED_WRITE_ACTIONS)


def _strip_direct_request_prefix(clause: str) -> str:
    remainder = clause
    for vocative in _VOCATIVE_PREFIXES:
        if remainder.startswith(vocative):
            remainder = remainder[len(vocative):]
            break
    tokens = tuple(
        sorted(
            (
                token
                for token in (
                *_DIRECT_REQUEST_HELPERS,
                *_DIRECT_REQUEST_MODIFIERS,
                *WRITE_COMMAND_PREFIXES,
                )
                if token != "把"
            ),
            key=len,
            reverse=True,
        )
    )
    for _ in range(12):
        matched = next((token for token in tokens if remainder.startswith(token)), None)
        if matched is None:
            break
        remainder = remainder[len(matched):]
    return remainder


def has_explicit_authorizing_write_request(value: str) -> bool:
    """Require a positive, direct speech act before authorizing health writes.

    The classifier and final tool gate share this positive predicate. Mentions,
    questions, reported text, completed-state checks, and denied clauses are
    fail-closed instead of becoming authorized merely because no veto matched.
    """
    context = _last_write_action_context(value)
    if context is None:
        return False
    if has_negated_write_scope(value):
        return False
    if (
        is_write_capability_question(value)
        or is_historical_write_reference(value)
        or is_read_action_write_reference(value)
        or is_write_result_check(value)
        or is_reported_write_reference(value)
    ):
        return False
    if _is_explicit_dated_backfill(value):
        return True

    clause, action, start = context
    after_action = clause[start + len(action):]
    if action == "记录" and after_action.startswith(RECORD_NOUN_SUFFIXES):
        return False
    if _starts_with_completed_aspect(after_action):
        return False
    direct_clause = _strip_direct_request_prefix(clause)
    if direct_clause.startswith(action):
        return True
    if direct_clause.startswith(("把", "将")) and action in direct_clause:
        return action != "记录" or after_action.startswith(("下来", "到", "为"))
    before_action = clause[:start]
    return start == 0 or before_action.endswith(
        (*_DIRECT_REQUEST_HELPERS, *WRITE_COMMAND_PREFIXES)
    )
