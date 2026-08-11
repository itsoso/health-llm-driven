"""单一事实源:药名 / 补剂名词库(中英)。

**一份词库,两类消费者:**

1. **safety_guardian 规则**(`rules/ddi.py` · `rules/dsi.py`)—— 按 class key 精确取别名
   列表,匹配**受控的在服药/补剂名字段**(`med["name"]` / `supplement["name"]`)。子串
   匹配在这个受控小空间里是安全的(如别名 `"铁"` / `"pril"` 只会撞到用户登记的药名,不会
   撞自由文本里的「地铁」/「April」)。这两个模块从本文件 import `DRUG_CLASS_ALIASES` /
   `SUPPLEMENT_CLASS_ALIASES`,**行为与内联定义时逐字节相同**。

2. **KB 对账处方 gate**(`services/kb_reconciliation_merge.py::_is_prescriptive_text`)——
   对**自由文本**(doc title/summary/body)做子串扫描,判 claim 是否处方式(I4 硬拒地板)。
   自由文本里短/歧义子串会误伤良性 claim,故 gate 用的是 `prescriptive_free_text_terms()`
   —— 从结构化 lexicon **派生 + 去歧义 + 去食物类**,不是全量 flatten。

**不变量:** safety 规则行为**只依赖 class→alias 结构**,与 gate 的派生 term set 解耦。
往某个 class 加一个药名 → **自动进 gate**(除非它落在 `_FREE_TEXT_AMBIGUOUS_TERMS` 去歧义
名单里),这样对账 gate 自动跟随安全词库生长,不再手抄一份会漂移的副本。

**范围边界(诚实记录):**
- `ddi.py` / `dsi.py` 的别名字典已迁到此处(真去重)。
- `rules/pgx.py` 的药名内联在规则逻辑里(与 `_HANDWRITTEN_SKIP` / phenotype 判定交织),
  重接会改行为、超出「先加共享常量再引用」的安全边界 → **暂不动 pgx 的匹配逻辑**;其药名
  词汇(可待因/曲马多/华法林/氯吡格雷/他克莫司/硫唑嘌呤/别嘌醇/卡马西平/苯妥英/氟尿嘧啶…)
  另在 `COMMON_DRUG_ALIASES` 里为 gate 复述,pgx 侧仍是其内联表的权威。
- `COMMON_DRUG_ALIASES` = **无专属 safety 规则、但 gate 应识别**的常见药(CCB/抗生素/甲状腺
  素/PPI/β 阻滞剂/降糖/皮质激素/利尿/免疫抑制/DOAC…)。**无任何 safety 规则 lookup 这些
  key**,故纯 additive、对安全零影响;它把 gate 从「~25 个命名高危药地板」拓成真正的常见
  药名探测器(闭合 布洛芬/氨氯地平/阿莫西林/左甲状腺素/lisinopril 等命名残余)。
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Dict, FrozenSet, List, Pattern

# ─────────────────────────── 药名 class → 别名(safety: ddi.py 消费) ──────────────
# 从 `rules/ddi.py` 迁入,逐字节不变。每个「药物类」下列常见中英文别名(小写 + 正则友好)。
DRUG_CLASS_ALIASES: Dict[str, List[str]] = {
    "glp1": [
        "替尔泊肽", "tirzepatide", "司美格鲁肽", "semaglutide", "利拉鲁肽",
        "liraglutide", "杜拉糖肽", "dulaglutide", "艾塞那肽", "exenatide",
        "毕马西肽", "lixisenatide",
        # 高知名度品牌名(用户/LLM 常直呼品牌;推送隐私对抗复审 2026-07-12 补)
        "ozempic", "wegovy", "mounjaro", "诺和泰", "诺和盈", "穆峰达",
    ],
    "insulin": ["胰岛素", "insulin", "优泌林", "甘精", "门冬", "德谷", "赖脯"],
    "sulfonylurea": [
        "格列", "格列美脲", "格列齐特", "格列本脲", "格列吡嗪",
        "gliclazide", "glimepiride", "glibenclamide", "磺脲",
        "glipizide", "tolbutamide",
    ],
    "cetirizine": ["西替利嗪", "cetirizine", "仙特明", "zyrtec"],
    "first_gen_antihistamine": [
        "苯海拉明", "diphenhydramine", "氯苯那敏", "扑尔敏", "chlorpheniramine",
        "异丙嗪", "promethazine", "羟嗪", "hydroxyzine",
    ],
    "benzodiazepine": [
        "艾司唑仑", "阿普唑仑", "劳拉西泮", "地西泮", "氯硝西泮",
        "diazepam", "alprazolam", "lorazepam", "clonazepam", "estazolam", "midazolam",
    ],
    "opioid": [
        "吗啡", "芬太尼", "可待因", "曲马多", "羟考酮", "氢可酮",
        "morphine", "fentanyl", "codeine", "tramadol", "oxycodone", "hydrocodone",
    ],
    "warfarin": ["华法林", "warfarin"],
    "antiplatelet": ["氯吡格雷", "clopidogrel", "阿司匹林", "aspirin"],
    "mao_inhibitor": ["苯乙肼", "异丙烟肼", "mao", "phenelzine", "selegiline"],
    "metformin": ["二甲双胍", "metformin", "格华止"],
    "mometasone_nasal": ["糠酸莫米松", "mometasone", "内舒拿", "nasonex"],
    "ipratropium_nasal": ["异丙托溴铵", "ipratropium", "爱全乐", "atrovent"],
    "cyp3a4_strong_inhibitor": [
        "利托那韦", "ritonavir", "克拉霉素", "clarithromycin",
        "酮康唑", "ketoconazole", "伊曲康唑", "itraconazole",
        "泊沙康唑", "posaconazole", "考比司他", "cobicistat",
    ],
    "nsaid": [
        "布洛芬", "ibuprofen", "双氯芬酸", "diclofenac", "萘普生", "naproxen",
        "塞来昔布", "celecoxib", "美洛昔康", "meloxicam",
    ],
    "acei_arb": [
        "普利", "pril", "沙坦", "sartan", "依那普利", "enalapril",
        "缬沙坦", "valsartan", "氯沙坦", "losartan",
    ],
    "ssri": [
        "舍曲林", "sertraline", "氟西汀", "fluoxetine", "帕罗西汀", "paroxetine",
        "西酞普兰", "citalopram", "艾司西酞普兰", "escitalopram",
    ],
    "statin": [
        "他汀", "statin", "辛伐他汀", "simvastatin", "阿托伐他汀", "atorvastatin",
        "瑞舒伐他汀", "rosuvastatin", "普伐他汀", "pravastatin",
    ],
}

# ─────────────────────── 补剂 class → 别名(safety: dsi.py 消费) ──────────────────
# 从 `rules/dsi.py` 迁入,逐字节不变。
SUPPLEMENT_CLASS_ALIASES: Dict[str, List[str]] = {
    "calcium": ["calcium", "钙", "碳酸钙", "柠檬酸钙"],
    "iron": ["iron", "铁", "血红素铁", "硫酸亚铁", "甘氨酸亚铁"],
    "zinc": ["zinc", "锌", "甘氨酸锌"],
    "magnesium": ["magnesium", "镁", "甘氨酸镁", "苏糖酸镁"],
    "omega3": ["omega", "鱼油", "fish oil", "epa", "dha"],
    "vitamin_k": ["vitamin k", "维生素 k", "vitamin-k", "vk"],
    "st_johns_wort": ["st john", "贯叶连翘", "圣约翰草"],
    "grapefruit": ["grapefruit", "葡萄柚", "西柚"],
    "ginkgo": ["ginkgo", "银杏"],
    "garlic": ["garlic", "大蒜"],
    "curcumin": ["curcumin", "姜黄素", "turmeric"],
    "coq10": ["coq10", "co-q10", "辅酶 q10", "辅酶q10", "ubiquinol"],
    "vitamin_d": [
        "vitamin d", "维生素 d", "vitamin-d", "vitamin d3", "vitamin d2", "d3", "d2",
    ],
    "b12": ["b12", "甲钴胺", "cyanocobalamin", "methylcobalamin"],
    "folate": ["folate", "叶酸", "methyl folate", "甲基叶酸"],
    "niacin": ["niacin", "烟酸", "nicotinic"],
    "probiotic": ["probiotic", "益生菌", "lactobif", "akk", "akkermansia", "lactobacillus"],
}

# ─────────── 常见药(无专属 safety 规则;仅 gate 消费,把 gate 拓成常见药名探测器)───────────
# 注意:**没有任何 safety 规则 lookup 这些 key** —— 纯 additive,对 SafetyGuardian 零影响。
# 只列**完整**药名(不列 `-地平`/`-列净` 之类裸后缀:自由文本里裸后缀撞「地平线」这类常用词,
# 而完整名已足够覆盖 doc 文本里的药物指称)。
COMMON_DRUG_ALIASES: Dict[str, List[str]] = {
    # 钙通道阻滞剂(氨氯地平 = 评审点名的命名残余)
    "ccb": [
        "氨氯地平", "amlodipine", "左旋氨氯地平", "levamlodipine", "硝苯地平", "nifedipine",
        "非洛地平", "felodipine", "地尔硫卓", "diltiazem", "维拉帕米", "verapamil",
    ],
    # ACEI/ARB 完整名(ddi 只列裸 -pril/-sartan;补 lisinopril 等命名残余)
    "acei_arb_named": [
        "赖诺普利", "lisinopril", "培哚普利", "perindopril", "雷米普利", "ramipril",
        "贝那普利", "benazepril", "厄贝沙坦", "irbesartan", "替米沙坦", "telmisartan",
        "坎地沙坦", "candesartan", "奥美沙坦", "olmesartan",
    ],
    # 青霉素/头孢/大环内酯/喹诺酮类抗生素(阿莫西林 = 评审点名的命名残余)
    "antibiotic": [
        "阿莫西林", "amoxicillin", "青霉素", "penicillin", "氨苄西林", "ampicillin",
        "头孢", "cephalexin", "头孢呋辛", "cefuroxime", "头孢克肟", "cefixime",
        "阿奇霉素", "azithromycin", "红霉素", "erythromycin",
        "左氧氟沙星", "levofloxacin", "环丙沙星", "ciprofloxacin", "莫西沙星", "moxifloxacin",
        "多西环素", "doxycycline", "甲硝唑", "metronidazole",
    ],
    # 甲状腺替代(左甲状腺素 = 评审点名的命名残余)
    "thyroid_replacement": ["左甲状腺素", "levothyroxine", "优甲乐", "euthyrox"],
    # 质子泵抑制剂 / P-CAB(gate 复述,不改 deprescribing/dsi 的抑酸判定)
    "ppi": [
        "质子泵抑制剂", "奥美拉唑", "omeprazole", "埃索美拉唑", "esomeprazole",
        "兰索拉唑", "lansoprazole", "泮托拉唑", "pantoprazole", "雷贝拉唑", "rabeprazole",
        "伏诺拉生", "vonoprazan",
    ],
    # β 受体阻滞剂(完整名;-洛尔 裸后缀不列)
    "beta_blocker": [
        "美托洛尔", "metoprolol", "比索洛尔", "bisoprolol", "阿替洛尔", "atenolol",
        "普萘洛尔", "propranolol", "卡维地洛", "carvedilol",
    ],
    # 降糖(GLP-1/胰岛素/磺脲 已在 DRUG_CLASS_ALIASES;此处补 SGLT2/DPP-4/二甲双胍复方,列全名)
    "oral_hypoglycemic": [
        "达格列净", "dapagliflozin", "恩格列净", "empagliflozin", "卡格列净", "canagliflozin",
        "西格列汀", "sitagliptin", "维格列汀", "vildagliptin", "利格列汀", "linagliptin",
        "阿卡波糖", "acarbose",
    ],
    # 皮质激素(泼尼松 已在旧 gate;补齐系统性糖皮质激素)
    "corticosteroid": [
        "泼尼松", "prednis", "prednisone", "泼尼松龙", "prednisolone",
        "地塞米松", "dexamethasone", "甲泼尼龙", "methylprednisolone",
        "氢化可的松", "hydrocortisone", "倍他米松", "betamethasone",
    ],
    # 利尿剂
    "diuretic": [
        "呋塞米", "furosemide", "氢氯噻嗪", "hydrochlorothiazide",
        "螺内酯", "spironolactone", "吲达帕胺", "indapamide", "托拉塞米", "torasemide",
    ],
    # 抗凝(DOAC;华法林已在 DRUG_CLASS_ALIASES)
    "doac": [
        "利伐沙班", "rivaroxaban", "达比加群", "dabigatran",
        "阿哌沙班", "apixaban", "艾多沙班", "edoxaban",
    ],
    # 免疫抑制 / 化疗 / 抗癫痫 / 情绪稳定(多为 pgx 覆盖的高危药,gate 侧复述)
    "immunosuppressant_chemo": [
        "甲氨蝶呤", "methotrexate", "环孢素", "cyclosporine", "他克莫司", "tacrolimus",
        "硫唑嘌呤", "azathioprine", "巯基嘌呤", "mercaptopurine", "别嘌醇", "allopurinol",
        "卡马西平", "carbamazepine", "苯妥英", "phenytoin", "丙戊酸", "valproate",
        "氟尿嘧啶", "capecitabine", "卡培他滨", "他莫昔芬", "tamoxifen",
        "伏立康唑", "voriconazole",
    ],
    # 其它常见镇痛(对乙酰氨基酚 = 非 NSAID 镇痛)
    "analgesic_other": [
        "对乙酰氨基酚", "acetaminophen", "paracetamol", "扑热息痛",
    ],
}

# ─────────────────── 自由文本处方 gate 的派生规则(仅 gate 消费) ───────────────────

# 用药 / 剂量动词 + 类名缩写(中英)—— 处方式语气锚点。这些不在 class→alias 结构里,
# 是 gate 专有的处方式信号词。避开会撞常用词的缩写(如 "ppi"⊂"shipping")。
_PRESCRIPTIVE_ACTION_TERMS: FrozenSet[str] = frozenset({
    # 剂量/用药动词(中)
    "剂量", "服用", "口服", "顿服", "维持量", "负荷量", "停药", "减量", "加量",
    "滴定", "用法用量",
    # 剂量/用药(英)
    "dose", "dosage", "titrat", "mg/kg", "maintenance dose", "loading dose", "posology",
    # 药物类缩写(足够独特,不撞常用词)
    "ssri", "nsaid", "maoi", "glp-1",
})

# **自由文本**里会误伤良性 claim 的短/歧义子串 —— 从 gate term set 剔除。
# (仍留在 class→alias 结构里给 safety 规则用:受控药名字段里这些子串不会误配。)
#   - 单字元素:钙化/地铁/钢铁/镁合金/锂电池 都会撞
#   - iron ⊂ environ,pril ⊂ April,epa/dha/vk/mao 太泛(EPA 机构 / Mao 姓 / 随机串)
#   - 门冬 ⊂ 门冬氨酸(氨基酸),普利 ⊂ 普利司通/普利茅斯,格列 ⊂ 格列佛
_FREE_TEXT_AMBIGUOUS_TERMS: FrozenSet[str] = frozenset({
    "钙", "铁", "锌", "镁", "锂",
    "门冬", "普利", "格列",
    "iron", "pril", "epa", "dha", "vk", "mao",
})

# 食物 / 草药类补剂 —— 相互作用相关但**非处方式内容**;命名它们的良性饮食/科普 claim 不该
# 被 gate 硬拒(over-refuse 误伤)。真剂量(如「银杏 240mg 每日」)仍由 `_DOSE_RE` 兜住。
_FREE_TEXT_EXCLUDED_SUPPLEMENT_CLASSES: FrozenSet[str] = frozenset({
    "grapefruit", "garlic", "ginkgo", "curcumin", "probiotic",
})


def _flatten_aliases(
    mapping: Dict[str, List[str]], *, exclude_classes: FrozenSet[str] = frozenset()
) -> FrozenSet[str]:
    out = set()
    for key, aliases in mapping.items():
        if key in exclude_classes:
            continue
        for alias in aliases:
            token = (alias or "").strip().lower()
            if token:
                out.add(token)
    return frozenset(out)


@lru_cache(maxsize=1)
def prescriptive_free_text_terms() -> FrozenSet[str]:
    """自由文本子串匹配用的处方式 term set(药名 + 剂量动词 + 核心补剂)。

    从结构化 lexicon **派生**:药物全量 + 补剂(去食物/草药类)+ 用药动词,再去掉
    `_FREE_TEXT_AMBIGUOUS_TERMS`(自由文本会误伤的短/歧义子串)。往 lexicon 加药名
    → 自动进本集(除非落在去歧义名单),对账 gate 因此自动跟随安全词库,不手抄副本。
    """
    terms = set(_PRESCRIPTIVE_ACTION_TERMS)
    terms |= _flatten_aliases(DRUG_CLASS_ALIASES)
    terms |= _flatten_aliases(COMMON_DRUG_ALIASES)
    terms |= _flatten_aliases(
        SUPPLEMENT_CLASS_ALIASES, exclude_classes=_FREE_TEXT_EXCLUDED_SUPPLEMENT_CLASSES
    )
    return frozenset(t for t in terms if t and t not in _FREE_TEXT_AMBIGUOUS_TERMS)


def _has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


@lru_cache(maxsize=1)
def drug_name_free_text_terms() -> FrozenSet[str]:
    """完整药名探测词，只用于自由文本中的药物上下文识别。"""
    terms = set(_flatten_aliases(DRUG_CLASS_ALIASES))
    terms |= _flatten_aliases(COMMON_DRUG_ALIASES)
    terms -= _FREE_TEXT_AMBIGUOUS_TERMS
    collapsed = {t.replace(" ", "") for t in terms if " " in t and _has_cjk(t)}
    return frozenset(t for t in (terms | collapsed) if t)


@lru_cache(maxsize=1)
def _drug_name_free_text_pattern() -> Pattern[str]:
    adjacent_dose = (
        r"\d+(?:\.\d+)?\s*(?:ml|mg|mcg|μg|ug|iu|g|毫升|毫克|克|单位|"
        r"片|粒|颗|袋|包|滴|支|瓶|tablets?|capsules?)"
    )
    alternatives: list[str] = []
    for term in sorted(drug_name_free_text_terms(), key=lambda value: (-len(value), value)):
        escaped = re.escape(term)
        if term.isascii():
            alternatives.append(
                rf"(?<![a-z0-9]){escaped}s?(?=$|[^a-z0-9]|{adjacent_dose})"
            )
        else:
            alternatives.append(escaped)
    return re.compile("|".join(alternatives), re.IGNORECASE)


_GENERIC_MEDICATION_REFERENCE_PATTERN = re.compile(
    r"(?:降压|降糖|降脂|抗凝|抗血小板|抗抑郁|助眠|胃病|胃|处方|所有|全部|"
    r"这类|该类|某类|某种|任何|正在吃的|在服的)?药(?:物|品)?(?!膳|店|厂|学|材|妆)"
)


def contains_drug_name(text: str | None) -> bool:
    """识别自由文本中的完整药名，并规避 iron/environment 等短词误配。"""
    if not text:
        return False
    return _drug_name_free_text_pattern().search(_normalize_intake_name_text(text)) is not None


@lru_cache(maxsize=1)
def supplement_name_free_text_terms() -> FrozenSet[str]:
    """完整补剂名探测词；排除会把普通食物误判为补剂的草药/食物类。"""
    terms = set(_flatten_aliases(
        SUPPLEMENT_CLASS_ALIASES,
        exclude_classes=_FREE_TEXT_EXCLUDED_SUPPLEMENT_CLASSES,
    ))
    terms -= _FREE_TEXT_AMBIGUOUS_TERMS
    collapsed = {t.replace(" ", "") for t in terms if " " in t and _has_cjk(t)}
    return frozenset(t for t in (terms | collapsed) if t)


@lru_cache(maxsize=1)
def supplement_name_entity_terms() -> FrozenSet[str]:
    """All exact supplement aliases for explicit entity validation."""
    terms = set(_flatten_aliases(SUPPLEMENT_CLASS_ALIASES))
    collapsed = {t.replace(" ", "") for t in terms if " " in t and _has_cjk(t)}
    return frozenset(t for t in (terms | collapsed) if t)


_UNICODE_NAME_DASH_RE = re.compile(r"[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]")
_UNICODE_NAME_INVISIBLE_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
_COMPACT_MULTI_SUPPLEMENT_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:vitamind|d[23]|b12|coq10)(?:and)?(?:fishoil|magnesium|nac|omega3)|"
    r"(?:fishoil|magnesium|nac|omega3)(?:and)?(?:vitamind|d[23]|b12|coq10)"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)


def _normalize_intake_name_text(text: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    normalized = _UNICODE_NAME_DASH_RE.sub("-", normalized)
    return _UNICODE_NAME_INVISIBLE_RE.sub("", normalized)


def _compile_supplement_name_pattern(terms: FrozenSet[str]) -> Pattern[str]:
    adjacent_dose = (
        r"\d+(?:\.\d+)?\s*(?:ml|mg|mcg|μg|ug|iu|g|毫升|毫克|克|单位|"
        r"片|粒|颗|袋|包|滴|勺|支|瓶|tablets?|capsules?|softgels?)"
    )
    alternatives: list[str] = []
    for term in sorted(terms, key=lambda value: (-len(value), value)):
        normalized_term = _normalize_intake_name_text(term)
        escaped = r"[\s-]*".join(
            re.escape(part)
            for part in re.split(r"[\s-]+", normalized_term)
            if part
        )
        if term.isascii():
            alternatives.append(
                rf"(?<![a-z0-9]){escaped}(?=$|[^a-z0-9]|{adjacent_dose})"
            )
        else:
            alternatives.append(escaped)
    return re.compile("|".join(alternatives), re.IGNORECASE)


@lru_cache(maxsize=1)
def _supplement_name_free_text_pattern() -> Pattern[str]:
    return _compile_supplement_name_pattern(supplement_name_free_text_terms())


def contains_supplement_name(text: str | None) -> bool:
    """识别自由文本中的完整补剂名，并保留 ASCII 词边界。"""
    if not text:
        return False
    normalized = _normalize_intake_name_text(text)
    if _supplement_name_free_text_pattern().search(normalized) is not None:
        return True
    compact = re.sub(r"[\s-]+", "", normalized)
    return _COMPACT_MULTI_SUPPLEMENT_RE.search(compact) is not None


def drug_name_spans(text: str | None) -> tuple[tuple[int, int], ...]:
    """返回完整药名在自由文本中的位置，供子句级安全语义判断使用。"""
    if not text:
        return ()
    return tuple(
        (match.start(), match.end())
        for match in _drug_name_free_text_pattern().finditer(str(text).lower())
    )


def medication_reference_spans(text: str | None) -> tuple[tuple[int, int], ...]:
    """返回具名药与泛称药物引用的位置，供变更动作邻域判断使用。"""
    if not text:
        return ()
    normalized = str(text).lower()
    spans = set(drug_name_spans(normalized))
    spans.update(
        (match.start(), match.end())
        for match in _GENERIC_MEDICATION_REFERENCE_PATTERN.finditer(normalized)
    )
    return tuple(sorted(spans))


def contains_medication_reference(text: str | None) -> bool:
    return bool(medication_reference_spans(text))


def strip_medication_references(text: str) -> str:
    """删除协调警示中的药物引用，保留连接词供作用域校验。"""
    normalized = str(text).lower()
    normalized = _drug_name_free_text_pattern().sub("", normalized)
    return _GENERIC_MEDICATION_REFERENCE_PATTERN.sub("", normalized)


@lru_cache(maxsize=1)
def sensitive_name_free_text_terms() -> FrozenSet[str]:
    """推送隐私 backstop 用的**名称类**敏感词(自由文本匹配,见 push_privacy)。

    与 `prescriptive_free_text_terms()` 的区别:**只含药名/补剂名,不含用药动词**
    (「记得按时服药」是 §5.6 允许的类别级文案,动词入集会把它误伤成 over-redaction)。

    派生规则与 gate 同源:药物全量 + 补剂(去食物/草药类,饮食建议里点名大蒜/西柚
    不泄露诊断)- `_FREE_TEXT_AMBIGUOUS_TERMS`。额外为 CJK+ASCII 混排别名补空格
    折叠变体(lexicon 写「维生素 d」,LLM 文案常写「维生素D」)。
    """
    terms = set(drug_name_free_text_terms())
    terms |= _flatten_aliases(
        SUPPLEMENT_CLASS_ALIASES, exclude_classes=_FREE_TEXT_EXCLUDED_SUPPLEMENT_CLASSES
    )
    terms -= _FREE_TEXT_AMBIGUOUS_TERMS
    collapsed = {t.replace(" ", "") for t in terms if " " in t and _has_cjk(t)}
    return frozenset(t for t in (terms | collapsed) if t)
