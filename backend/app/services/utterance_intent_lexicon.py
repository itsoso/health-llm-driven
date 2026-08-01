"""Shared deterministic lexicon for utterance intent extraction.

The legacy tuples remain a byte-compatible classifier view.  The clinician
vocabulary at the bottom is intentionally narrow: it supports provenance
recognition, not general action authorization.
"""

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



# Shared clinician-provenance vocabulary.  Keep longest providers first so a
# character scan does not reduce "主治医生" to the embedded "医生".
CLINICIAN_PROVIDER_TERMS = (
    "物理治疗师",
    "主治医生",
    "康复师",
    "医生",
    "医师",
    "大夫",
)

CLINICIAN_REPORT_PREDICATES = (
    "告诉我",
    "告诉",
    "表示",
    "认为",
    "诊断",
    "判断",
    "评估",
    "建议",
    "要求",
    "嘱咐",
    "说",
    "称",
)

CLINICIAN_FEEDBACK_OBJECT_NOUNS = (
    "诊断",
    "意见",
    "反馈",
    "结论",
)

CLINICIAN_FEEDBACK_WRITE_ROOTS = (
    "记录",
    "保存",
    "录入",
    "写入",
)

CLINICIAN_STRICT_COMMAND_PREFIXES = (
    "麻烦帮我",
    "请帮我",
    "麻烦",
    "帮我",
    "请",
)

CLINICIAN_CONSULTATION_TERMS = (
    "咨询",
    "请教",
)

CLINICIAN_REPORT_NOUN_CONTINUATIONS = (
    "记录",
    "报告",
    "诊断书",
    "书",
    "文档",
    "档案",
    "结果",
    "证明",
    "清单",
    "列表",
)
