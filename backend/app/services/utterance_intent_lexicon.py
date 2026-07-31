"""Shared deterministic lexicon for utterance intent extraction.

The legacy tuples are a public-classifier compatibility view.  Evidence
parsing uses the immutable structured rows at the bottom of this module so it
can add stricter placement semantics without changing legacy routing.
"""

from dataclasses import dataclass
from typing import Literal, TypeAlias

READ_ACTIONS = (
    "重新列出",
    "列出",
    "列表",
    "列个表格",
    "列一下表格",
    "列成表格",
    "整理成表格",
    "表格",
    "查询",
    "查看",
    "看一下",
    "看看",
    "查一下",
    "显示",
    "告诉我",
    "汇总",
)

QUESTION_SIGNALS = (
    "?",
    "？",
    "多少",
    "什么",
    "啥",
    "哪些",
    "几",
    "有没有",
    "是不是",
    "是否",
    "吗",
    "呢",
    "如何",
    "怎么",
    "为什么",
    "多高",
    "多重",
    "多久",
    "高不高",
    "正常吗",
    "有问题吗",
    "能否",
    "可否",
    "可不可以",
    "怎么样",
)

WRITE_ACTIONS = (
    "记录",
    "打卡",
    "打个卡",
    "新增",
    "录入",
    "保存",
    "记下",
    "记一下",
    "帮我记一下",
    "写入",
    "存下来",
    "吃了",
    "喝了",
    "服药",
    "已服用",
    "已吃",
    "已喝",
)

WRITE_NEGATIONS = (
    "别记录",
    "不要记录",
    "不用记录",
    "无需记录",
    "勿记录",
    "甭记录",
    "别记",
    "不要记",
    "不用记",
    "无需记",
    "记在心里",
    "记到心里",
)

WRITE_NEGATION_EXCEPTIONS = (
    "别忘了记录",
    "不要记错",
    "别记错",
    "别记成",
    "别记录错",
    "别记录成",
)

WRITE_COMMAND_PREFIXES = (
    "帮我",
    "请",
    "给我",
    "麻烦",
    "先",
    "再",
    "然后",
    "并",
    "顺便",
    "要",
    "把",
    "我想",
    "想",
    "希望",
    "需要",
)

RECORD_NOUN_SUFFIXES = (
    "出发",
    "显示",
    "表明",
    "提示",
    "证明",
    "分析",
    "推断",
    "里",
    "中",
    "上",
    "的",
)

MUTATE_ACTIONS = {
    "delete": ("删除", "删掉", "删了", "移除", "去掉", "撤销", "清掉"),
    "update": ("修改", "改成", "改为", "改到", "更新", "调整", "更正", "修正"),
    "sync": ("同步", "sync", "拉取最新数据", "刷新一下数据", "刷新数据"),
}

MUTATION_NEGATIONS = (
    "不要",
    "别",
    "不用",
    "无需",
    "不需要",
    "不想",
    "先别",
    "暂不",
    "不能",
    "不可",
    "禁止",
    "避免",
)

MUTATION_NEGATION_EXCEPTIONS = ("别忘了", "不要忘了")

MEDIA_TERMS = (
    "aigc",
    "百炼",
    "万相",
    "wan",
    "图片",
    "图像",
    "海报",
    "封面",
    "短视频",
    "视频",
    "图生视频",
    "文生图",
    "文生视频",
)

MEDIA_CREATE_ACTIONS = (
    "生成",
    "制作",
    "做成",
    "做一个",
    "创作",
    "创作一个",
    "渲染",
    "变成",
)

PLAN_TERMS = (
    "计划",
    "计划项",
    "周计划",
    "行动卡",
    "首页计划",
    "干预周期",
)

PLAN_CREATE_ACTIONS = (
    "生成",
    "制定",
    "安排",
    "加入",
    "列入",
    "保存",
)

PLAN_UPDATE_ACTIONS = (
    "完成",
    "标记完成",
    "调整计划",
    "更新计划",
)

REMINDER_TERMS = (
    "提醒",
    "提醒我",
    "定时提醒",
    "闹钟",
    "一次性提醒",
    "循环提醒",
)

REMINDER_CREATE_ACTIONS = (
    "提醒",
    "提醒我",
    "定时提醒",
    "创建",
    "设置",
    "设一个",
    "设个",
    "帮我设",
    "帮我定",
    "定个",
)

CLINICIAN_CONTEXT_WRITE_ACTIONS = (
    "记录",
    "记一下",
    "记下",
    "录入",
    "保存",
    "写入",
    "存下来",
)

CLAUSE_ACTION_NEGATIONS = (
    "没有必要",
    "不需要",
    "不想",
    "不要",
    "不用",
    "无需",
    "不必",
    "先别",
    "别",
)

CLAUSE_SAVE_MODAL_TERMS = ("需要", "是否", "要不要")


EvidenceFamily: TypeAlias = Literal[
    "read",
    "save",
    "update",
    "delete",
    "sync",
    "advice",
    "media",
    "plan",
    "reminder",
]
EvidenceCuePlacement: TypeAlias = Literal[
    "prefix",
    "terminal",
    "between",
    "boundary",
]
EvidenceStanceKind: TypeAlias = Literal[
    "question_prefix",
    "question_terminal",
    "negative_command",
    "negative_statement",
    "negative_exception",
    "completed_prefix",
    "completed_suffix",
    "conditional",
    "strict_command",
    "user_subject",
]
EvidenceTargetKind: TypeAlias = Literal[
    "clinician_content",
    "clinician_record",
    "symptom",
    "medication",
    "diet",
    "weight",
    "health_record",
    "media",
    "plan",
    "reminder",
]


@dataclass(frozen=True)
class EvidenceActionLexeme:
    surface: str
    allowed_families: frozenset[EvidenceFamily]


@dataclass(frozen=True)
class EvidenceCue:
    surface: str
    placement: EvidenceCuePlacement


@dataclass(frozen=True)
class EvidenceQuotePair:
    opener: str
    closer: str


@dataclass(frozen=True)
class EvidenceProviderLexeme:
    surface: str


@dataclass(frozen=True)
class EvidenceRelationLexeme:
    surface: str
    relation: Literal["report", "basis"]


@dataclass(frozen=True)
class EvidenceTargetLexeme:
    surface: str
    target: EvidenceTargetKind


@dataclass(frozen=True)
class EvidenceStanceLexeme:
    surface: str
    kind: EvidenceStanceKind


EVIDENCE_ADVICE_ACTIONS = ("分析", "解读", "评估")


def _build_evidence_action_lexicon() -> tuple[EvidenceActionLexeme, ...]:
    families_by_surface: dict[str, set[EvidenceFamily]] = {}

    def add(
        surfaces: tuple[str, ...],
        family: EvidenceFamily,
    ) -> None:
        for surface in surfaces:
            families_by_surface.setdefault(surface, set()).add(family)

    add(READ_ACTIONS, "read")
    add(CLINICIAN_CONTEXT_WRITE_ACTIONS, "save")
    for family, surfaces in MUTATE_ACTIONS.items():
        add(surfaces, family)
    add(EVIDENCE_ADVICE_ACTIONS, "advice")
    add(MEDIA_CREATE_ACTIONS, "media")
    add(PLAN_CREATE_ACTIONS, "plan")
    add(PLAN_UPDATE_ACTIONS, "plan")
    add(REMINDER_CREATE_ACTIONS, "reminder")

    return tuple(
        EvidenceActionLexeme(surface, frozenset(families))
        for surface, families in sorted(
            families_by_surface.items(),
            key=lambda item: (-len(item[0]), item[0]),
        )
    )


EVIDENCE_ACTION_LEXICON = _build_evidence_action_lexicon()

EVIDENCE_QUESTION_CUES = tuple(
    EvidenceCue(surface, "prefix")
    for surface in (
        "是否需要",
        "可不可以",
        "该不该",
        "要不要",
        "是不是",
        "能否",
        "可否",
        "是否",
        "怎么",
        "如何",
    )
) + tuple(
    EvidenceCue(surface, "terminal")
    for surface in ("吗", "么", "？", "?")
)

EVIDENCE_NEGATION_CUES = tuple(
    EvidenceCue(surface, "prefix")
    for surface in (
        "没有必要",
        "不要帮我",
        "不需要",
        "不想",
        "不要",
        "不用",
        "无需",
        "不必",
        "先别",
        "暂不",
        "不能",
        "不可",
        "禁止",
        "避免",
        "不再",
        "勿",
        "甭",
        "别",
    )
)

EVIDENCE_NEGATION_EXCEPTION_CUES = tuple(
    EvidenceCue(surface, "prefix")
    for surface in ("不要忘了", "别忘了")
)

EVIDENCE_STRICT_USER_COMMAND_CUES = tuple(
    EvidenceCue(surface, "prefix")
    for surface in ("帮我", "请")
)

EVIDENCE_USER_SUBJECT_CUES = tuple(
    EvidenceCue(surface, "prefix")
    for surface in ("我想", "我要")
)

EVIDENCE_ACTOR_TRANSITION_CUES = tuple(
    EvidenceCue(surface, "between")
    for surface in (
        "但是",
        "不过",
        "可是",
        "然后",
        "随后",
        "接着",
        "而",
        "但",
    )
)

EVIDENCE_HARD_BOUNDARIES = tuple(
    EvidenceCue(surface, "boundary")
    for surface in ("。", "；", ";", "\n", "！", "!")
)

EVIDENCE_QUOTE_PAIRS = tuple(
    EvidenceQuotePair(opener, closer)
    for opener, closer in (
        ("“", "”"),
        ("‘", "’"),
        ("「", "」"),
        ('"', '"'),
    )
)


# The evidence metadata below is intentionally separate from the legacy tuple
# views above.  The classifier keeps importing the byte-compatible legacy
# values while the authorization parser consumes these typed rows.
EVIDENCE_PROVIDER_LEXICON = tuple(
    EvidenceProviderLexeme(surface)
    for surface in (
        "物理治疗师",
        "主治医生",
        "康复师",
        "理疗师",
        "医生",
        "医师",
        "大夫",
    )
)

EVIDENCE_RELATION_LEXICON = tuple(
    EvidenceRelationLexeme(surface, "basis")
    for surface in ("根据", "依据", "按照")
) + tuple(
    EvidenceRelationLexeme(surface, "report")
    for surface in (
        "告诉",
        "表示",
        "认为",
        "诊断",
        "判断",
        "建议",
        "要求",
        "让我",
        "叫我",
        "指示",
        "希望",
        "嘱咐",
        "说",
        "称",
    )
)

EVIDENCE_TARGET_LEXICON = tuple(
    EvidenceTargetLexeme(surface, target)
    for surface, target in (
        ("医生诊断记录", "clinician_record"),
        ("用药删除记录", "medication"),
        ("用药剂量", "medication"),
        ("用药记录", "medication"),
        ("每天腰痛情况", "symptom"),
        ("今天腰痛6分", "symptom"),
        ("每天疼痛", "symptom"),
        ("每天腰痛", "symptom"),
        ("今天腰痛", "symptom"),
        ("疼痛记录", "symptom"),
        ("饮食记录", "diet"),
        ("体重记录", "weight"),
        ("运动记录", "health_record"),
        ("健康记录", "health_record"),
        ("健康数据", "health_record"),
        ("昨天记录", "health_record"),
        ("旧记录", "health_record"),
        ("诊断记录", "clinician_record"),
        ("医生说的内容", "clinician_content"),
        ("检查结果", "clinician_content"),
        ("康复图片", "media"),
        ("复查提醒", "reminder"),
        ("康复计划", "plan"),
        ("药物", "medication"),
        ("用药", "medication"),
        ("腰痛", "symptom"),
        ("疼痛", "symptom"),
        ("饮食", "diet"),
        ("午餐", "diet"),
        ("体重71kg", "weight"),
        ("体重", "weight"),
        ("诊断", "clinician_content"),
        ("图片", "media"),
        ("提醒", "reminder"),
        ("计划", "plan"),
        ("记录", "health_record"),
    )
)


def _evidence_dynamic_targets() -> tuple[EvidenceTargetLexeme, ...]:
    existing = {row.surface for row in EVIDENCE_TARGET_LEXICON}
    rows: list[EvidenceTargetLexeme] = []
    for surfaces, target in (
        (MEDIA_TERMS, "media"),
        (PLAN_TERMS, "plan"),
        (REMINDER_TERMS, "reminder"),
    ):
        rows.extend(
            EvidenceTargetLexeme(surface, target)
            for surface in surfaces
            if surface not in existing
        )
        existing.update(surfaces)
    return tuple(rows)


EVIDENCE_TARGET_LEXICON += _evidence_dynamic_targets()

EVIDENCE_STANCE_LEXICON = tuple(
    EvidenceStanceLexeme(surface, "question_prefix")
    for surface in (
        "是否需要",
        "应不应该",
        "可不可以",
        "该不该",
        "要不要",
        "是不是",
        "能否",
        "可否",
        "是否",
        "怎么",
        "如何",
    )
) + tuple(
    EvidenceStanceLexeme(surface, "question_terminal")
    for surface in ("会怎么样", "好不好", "吗", "么", "？", "?")
) + tuple(
    EvidenceStanceLexeme(surface, "negative_command")
    for surface in (
        "没有必要",
        "不要帮我",
        "不需要",
        "不想",
        "不要",
        "不用",
        "无需",
        "不必",
        "先别",
        "暂不",
        "不能",
        "不可",
        "禁止",
        "避免",
        "不再",
        "勿",
        "甭",
        "别",
    )
) + tuple(
    EvidenceStanceLexeme(surface, "negative_statement")
    for surface in ("不应该", "不应", "不得", "拒绝")
) + tuple(
    EvidenceStanceLexeme(surface, "negative_exception")
    for surface in ("不要忘了", "别忘了")
) + tuple(
    EvidenceStanceLexeme(surface, "completed_prefix")
    for surface in (
        "已经",
        "刚刚",
        "刚才",
        "早就",
        "之前",
        "曾经",
        "曾",
        "已",
        "刚",
    )
) + tuple(
    EvidenceStanceLexeme(surface, "completed_suffix")
    for surface in ("后的", "过的", "了的", "了", "过")
) + tuple(
    EvidenceStanceLexeme(surface, "conditional")
    for surface in ("如果", "假如", "倘若")
) + tuple(
    EvidenceStanceLexeme(surface, "strict_command")
    for surface in ("请帮我", "帮我", "麻烦", "给我", "请")
) + tuple(
    EvidenceStanceLexeme(surface, "user_subject")
    for surface in ("我需要", "我想", "我要")
)

EVIDENCE_SOFT_CONJUNCTIONS = (
    "或者",
    "以及",
    "并且",
    "然后",
    "随后",
    "接着",
    "再",
    "或",
    "和",
    "与",
    "及",
    "并",
    "、",
)

EVIDENCE_GROUP_BOUNDARIES = (
    "但是",
    "不过",
    "可是",
    "然后",
    "随后",
    "接着",
    "现在",
    "但",
    "而",
    "后",
    "，",
    ",",
    "。",
    "；",
    ";",
    "！",
    "!",
    "？",
    "?",
    "\n",
)

EVIDENCE_REPORT_NOUN_CONTINUATIONS = {
    "诊断": ("记录", "报告", "结果", "证明", "清单", "列表"),
    "建议": ("记录", "报告", "清单", "列表", "文档"),
    "说": ("内容", "话"),
}

EVIDENCE_COMMAND_PARTICLES = ("顺便", "然后", "先", "再", "要")
EVIDENCE_REPORT_FILLER_CHARS = frozenset("的对跟给我是要先再：:，, ")
EVIDENCE_BA_PARTICLE_CHARS = frozenset("把都给将 ")
