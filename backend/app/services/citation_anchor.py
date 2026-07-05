"""
Citation Anchor — 数字锚定核验(shadow 模式,观测不干预)。

产品主张「每句可验证」的地基:AI 回答里引用的**个人**数值(HRV 42ms / 睡眠 3.3h /
血氧 92%)必须能锚定到用户的 Digital Health Twin 或记录。外部裁判无法区分「真数据引用」
与「模型编造」时,会把真实引用整片误判成 fabrication(盲评实锤)。本模块把「回答里有多少
个人数值能对上 Twin」量化成一个可观测比率(anchored_ratio),先只观测,不改写/不拦截答案
(enforcement 是二期,等 shadow 数据说话)。

三个纯函数,零 LLM:
  - build_fact_index(twin)              → {数值 → [(类目, 原始键, 日期?)]} 可检索索引
  - extract_personal_numeric_claims(text) → 个人指涉语境下的数值断言(排除通用知识数值)
  - anchor_report(text, twin)           → {total, anchored, unanchored, anchored_ratio}

浮点匹配容差:相对 ±1% 或末位量级(见 _values_match)。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.twin.schema import HealthTwin

# ─────────────────────────── Fact index ────────────────────────────────

# Twin 顶层分区 → 人话类目标签(与 evals/comparative 的 facts 拍平口径一致)。
_PARTITION_LABELS: Dict[str, str] = {
    "physiological": "生理",
    "body_composition": "身体成分",
    "labs": "化验",
    "cgm": "CGM",
    "medication": "用药",
    "supplement": "补剂",
    "genetic": "基因",
    "environment": "环境",
    "behavioral": "行为",
    "acute": "急性",
    "mental": "心理",
    "chronic": "慢病",
    "goals": "目标",
}

# 不进 fact index 的键:计数/占比/枚举/内部标记等,不是「用户引用的健康数值」,
# 收进来只会制造巧合匹配(如 count=92 撞上某个 HRV=92)。保守起见只排明确的噪音键;
# 宁可多收几个真值,anchored 侧是「答案有据」的证明,漏收会低估 anchored_ratio(偏保守)。
_NOISE_KEY_SUBSTRINGS: Tuple[str, ...] = (
    "count",
    "_pct",  # 百分比派生(water_progress_pct 等),数值本身不是用户引用的原始读数
    "samples",
    "user_id",
    "build_ms",
    "elapsed",
    "total_variants",
    "total_active",
    "readings_count",
    "n_days",
    "event_count",
    # schema **默认常量**,不是采集到的用户数据 —— 收进索引会造成巧合锚定
    # (答案「建议每天 2000ml」误对上 water_goal_ml 默认 2000)。
    "water_goal_ml",
    "taking_window_days",
    "goal",  # *_goal_* 类目标常量
)

_DATE_KEY_HINTS: Tuple[str, ...] = ("date", "_at", "measured", "recorded", "weighed", "updated")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _extract_date_from_mapping(mapping: Dict[str, Any]) -> Optional[str]:
    """从一个 dict 里找日期字段(逐夜序列/异常项/基线项每条自带 date)。"""
    for k, v in mapping.items():
        kl = str(k).lower()
        if any(h in kl for h in _DATE_KEY_HINTS) and isinstance(v, (str, date, datetime)):
            s = str(v)
            # ISO 日期取前 10 位(2026-07-05T... → 2026-07-05)
            m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
            if m:
                return m.group(1)
    return None


def _is_noise_key(key: str) -> bool:
    kl = str(key).lower()
    return any(sub in kl for sub in _NOISE_KEY_SUBSTRINGS)


def _walk_numbers(
    obj: Any,
    category: str,
    key_path: str,
    ctx_date: Optional[str],
    out: Dict[float, List[Tuple[str, str, Optional[str]]]],
) -> None:
    """递归把结构里所有数值叶子收进索引。

    obj: 当前节点(标量/dict/list)
    key_path: 到达该节点的键路径(如 physiological.hrv_latest)
    ctx_date: 从祖先 dict 继承下来的日期(如逐夜序列每条的 date)
    """
    if _is_number(obj):
        # 末段键判噪音(hrv_nightly_series 里的 count 不收,但 hrv_avg 收)。
        leaf_key = key_path.rsplit(".", 1)[-1]
        if _is_noise_key(leaf_key):
            return
        _add(out, float(obj), category, key_path, ctx_date)
        return
    if isinstance(obj, dict):
        # 本层 dict 若自带日期,作为子节点的 ctx_date
        local_date = _extract_date_from_mapping(obj) or ctx_date
        for k, v in obj.items():
            _walk_numbers(v, category, f"{key_path}.{k}", local_date, out)
        return
    if isinstance(obj, (list, tuple)):
        for item in obj:
            # list 元素若是 dict,让它自己解析日期;标量继承 ctx_date
            _walk_numbers(item, category, key_path, ctx_date, out)
        return
    # 其它类型(str/None/date)不收


def _add(
    out: Dict[float, List[Tuple[str, str, Optional[str]]]],
    value: float,
    category: str,
    key: str,
    d: Optional[str],
) -> None:
    entry = (category, key, d)
    bucket = out.setdefault(value, [])
    if entry not in bucket:
        bucket.append(entry)


def build_fact_index(twin: HealthTwin) -> Dict[float, List[Tuple[str, str, Optional[str]]]]:
    """把 HealthTwin 拍平成 {数值 → [(类目, 原始键, 日期?)]} 可检索索引。

    吃结构化 twin 对象(非 markdown):逐分区递归所有数值叶子,包括嵌套 dict/list
    里的值(逐夜 HRV 序列、异常化验项、个人基线项)。日期尽量从每条记录自带的 date
    字段回填,回填不到就是 None(仍算 anchored,只是无日期)。

    Returns:
        dict:key 是精确 float 值,value 是命中该值的所有来源三元组。匹配走
        _values_match 的容差比较,不靠精确相等,所以 key 只作候选桶。
    """
    out: Dict[float, List[Tuple[str, str, Optional[str]]]] = {}
    try:
        data = twin.model_dump()
    except Exception:  # noqa: BLE001 — schema 漂移不该炸 shadow 观测层
        return out
    for partition, label in _PARTITION_LABELS.items():
        section = data.get(partition)
        if section is None:
            continue
        _walk_numbers(section, label, partition, None, out)
    return out


# ────────────────────── Personal numeric claim extraction ───────────────

# 个人指代词:数值窗口内出现任一,才认定为「个人指涉语境下的数值断言」。
_PERSONAL_MARKERS: Tuple[str, ...] = (
    "你的", "您的", "你", "您",
    "记录显示", "数据显示", "记录到", "监测到", "检测到",
    "最近", "今天", "昨天", "昨晚", "今早", "近期", "过去",
    "当前", "目前", "现在",
    "我的",  # 用户视角复述
)

# 泛化词:局部子句里出现任一(且无更强个人指代)→ 该数值是通用知识参考值,不算个人断言。
# 只收**直接把数字标成人群/参考/建议值**的词,不收会与个人叙述并存的软词(如「阈值」——
# 「你 92% 已触及低氧阈值」里 92% 是个人读数,阈值只是它跨过的界;把「阈值」当泛化词会
# 把真实个人值误杀)。判据:该词紧邻的数字本身是不是"给所有人看的参考区间"。
_GENERIC_MARKERS: Tuple[str, ...] = (
    "正常范围", "正常值", "正常应", "正常在", "参考范围", "参考值",
    "参考上限", "参考下限", "参考区间", "参考", "建议范围", "建议量",
    "推荐量", "推荐摄入",
)

# 数值 + 单位模式。捕获数字(含小数)与紧随单位(**必需**)。
# 单位表覆盖健康域常见量纲;纯数字后接 % 也算(血氧/TIR)。
# 刻意不含 天/周/月:那是回看窗口/时间跨度(「最近 8 天」「过去半年」),不是健康读数,
# 收进来只会当 unanchored 噪音。小时/分钟/岁 是真读数(睡眠/REM/年龄),保留。
#
# **单位必需(shadow 保守取舍)**: 只抽带明确健康量纲的数值。裸数字(「睡眠分 42」「电量
# 7」)缺量纲、需 metric-label 词典才能可靠框定,shadow 阶段宁可漏(under-capture 只是少
# 信号)不可误抓(over-capture 会把无关整数当 unanchored 假报)。带单位的读数(HRV 42ms /
# 睡眠 3.3h / SpO2 92% / 静息心率 69bpm / LDL 4.1 无单位除外)正是盲评裁判纠结的「个人数值
# 引用」。裸数字锚定留给二期(需 metric 词典)。
# μ 有两个常见 codepoint:MICRO SIGN(U+00B5, µ)与 GREEK MU(U+03BC, μ)。中文体检报告/
# 本仓库 schema 注释混用,两个都必须收,否则 8.0 µmol/L 静默漏抓。
_UNIT_PATTERN = (
    r"(?:ms|毫秒|bpm|次/分|mmol/L|mmol|mg/dL|mg/dl|mg|[µμ]mol/L|umol/L|[µμ]mol|umol|"
    r"ng/mL|ng/ml|ng|pg/mL|pg/ml|pg|g/L|g/dL|g/dl|g|kg|cm|mm|kcal|大卡|卡|"
    r"小时|min|分钟|℃|°C|%|‰|岁|步|ml|mL|L)"
)
# 数字:允许 1-4 位整数/小数,不含千分位逗号(健康读数一般不带)。单位强制,区间(a-b)由局部泛化词过滤。
_NUMERIC_CLAIM_RE = re.compile(
    r"(?P<num>\d{1,4}(?:\.\d{1,2})?)\s*(?P<unit>" + _UNIT_PATTERN + r")"
)

# 日期形态:先在原文里定位所有日期 span,数值抽取时命中 span 的整体跳过。
# 覆盖 ISO(2026-07-05)/ 月斜杠日(7/5、07/05)/ 中文月日(7月5日、6月)。
# 不这么做的话 "7/5" 会被拆成 7.0 与 5.0 两个假数值断言,污染 total。
_DATE_SPAN_RE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}"          # 2026-07-05
    r"|\d{1,2}\s*/\s*\d{1,2}"          # 7/5  07 / 05
    r"|\d{1,2}\s*月(?:\s*\d{1,2}\s*[日号])?"  # 7月5日 / 6月
)

# 局部窗口上限(字符数):向前后各取,但被子句分隔符截断(见 _clause_window)。
# 用作 context_snippet 与通用知识判定的局部范围。中文密度高,±16 字够框住「你的 HRV 42ms」。
_CTX_WINDOW = 16

# 子句分隔符:通用知识判定的局部窗口在最近的分隔符处截断,避免相邻子句的泛化词
# (如「静息心率 69bpm。REM 仅 13 分钟(正常应 90-120min)」里 69bpm 后面那句的「正常应」)
# 误染当前数值。半角/全角标点 + 换行 + markdown 表格竖线。
_CLAUSE_DELIMS = set("。，,；;、！!？?\n|｜（）()《》【】")


def _has_any(text: str, markers: Tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def _date_spans(text: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in _DATE_SPAN_RE.finditer(text)]


def _overlaps_any(span: Tuple[int, int], spans: List[Tuple[int, int]]) -> bool:
    s, e = span
    return any(s < de and ds < e for ds, de in spans)


def _clause_window(text: str, start: int, end: int) -> str:
    """取数值所在**子句**的局部窗口:从 start 向左、end 向右各扩 _CTX_WINDOW 字,
    但一遇到子句分隔符就停。这样相邻子句的泛化词不会污染当前数值的通用知识判定。"""
    ls = start
    lo = max(0, start - _CTX_WINDOW)
    while ls > lo and text[ls - 1] not in _CLAUSE_DELIMS:
        ls -= 1
    re_ = end
    hi = min(len(text), end + _CTX_WINDOW)
    while re_ < hi and text[re_] not in _CLAUSE_DELIMS:
        re_ += 1
    return text[ls:re_]


def extract_personal_numeric_claims(text: str) -> List[Dict[str, Any]]:
    """抽取「个人指涉语境下的数值断言」。

    个人语境是**答案级**的,不是逐数字 ±16 字的:真实健康回答一次性建立个人语境
    (「综合你最近 8 天的数据…」),随后成段罗列 42.0ms / 3.3 小时 / 92%,这些都继承
    该语境。所以判据分两层:

      1. **答案级个人门**: 整段文本出现任一个人指代词(你/您/你的/记录显示/数据显示/
         最近/今天…)才进入抽取。纯通用知识回答(如「胃溃疡分几期」)全段无个人指代 →
         零断言,不误报。
      2. **逐数字**: 数值 + 单位命中(单位必需),且落在日期 span 外,且**局部窗口**
         (±_CTX_WINDOW 字)不是通用知识语境(有泛化词「参考范围/正常应/建议量」且窗口
         内无强个人指代「你的/您的/我的」→ 判通用,排除,如「正常应 90-120min」)。

    返回每条 {value: float, unit: str, context_snippet: str, raw: str}。
    纯函数,不碰 twin。
    """
    if not text:
        return []
    # 答案级个人门:全段无任何个人指代 → 不是在讲用户数据,零个人断言。
    if not _has_any(text, _PERSONAL_MARKERS):
        return []

    claims: List[Dict[str, Any]] = []
    seen_spans: set[Tuple[int, float]] = set()
    date_spans = _date_spans(text)
    for m in _NUMERIC_CLAIM_RE.finditer(text):
        num_raw = m.group("num")
        unit = m.group("unit") or ""
        try:
            value = float(num_raw)
        except ValueError:
            continue
        start, end = m.span()
        # 数字落在日期 span 内(7/5 的 7 与 5、2026-07-05 的三段)→ 是日期,不是断言。
        if _overlaps_any((m.start("num"), m.end("num")), date_spans):
            continue
        key = (start, value)
        if key in seen_spans:
            continue
        seen_spans.add(key)

        # 子句级局部窗口(被标点截断,不跨句污染)。
        window = _clause_window(text, start, end)

        # 局部通用知识数值:泛化词命中 → 排除(除非窗口里有强个人指代「你的/您的/我的」把
        # 它拉回个人语境,如「你的 LDL 4.1 已超参考上限」——这里 4.1 仍是个人值)。
        generic = _has_any(window, _GENERIC_MARKERS)
        strong_personal = _has_any(window, ("你的", "您的", "我的"))
        if generic and not strong_personal:
            continue

        claims.append(
            {
                "value": value,
                "unit": unit,
                "context_snippet": window.strip(),
                "raw": m.group(0).strip(),
            }
        )
    return claims


# ─────────────────────────── Anchor report ─────────────────────────────


def _values_match(claim_val: float, fact_val: float) -> bool:
    """浮点匹配容差:相对 ±1% 或绝对末位(0.1)取宽者。

    - 相对 1%:73.07kg vs 73.1kg 算命中。
    - 绝对 0.1:小数值(如 3.3h)相对 1% 太严,用 0.1 兜底。
    整数完全相等自然命中(差为 0)。
    """
    diff = abs(claim_val - fact_val)
    if diff == 0:
        return True
    rel_tol = abs(fact_val) * 0.01
    return diff <= max(rel_tol, 0.1)


def anchor_report(text: str, twin: HealthTwin) -> Dict[str, Any]:
    """核验答案里的个人数值能否锚定到 Twin。

    Returns:
        {
          total: int,                        # 抽到的个人数值断言总数
          anchored: int,                     # 能对上 Twin 的数量
          unanchored: [{value, context_snippet}],  # 对不上的(可疑编造/无来源)
          anchored_ratio: float,             # anchored / total,total=0 时为 1.0(无可核验断言=不扣分)
        }

    纯函数,零 LLM。异常由调用方(shadow 接线)吞掉;这里只做确定性计算。
    """
    claims = extract_personal_numeric_claims(text)
    index = build_fact_index(twin)
    fact_values = list(index.keys())

    anchored = 0
    unanchored: List[Dict[str, Any]] = []
    for claim in claims:
        cv = claim["value"]
        hit = any(_values_match(cv, fv) for fv in fact_values)
        if hit:
            anchored += 1
        else:
            unanchored.append(
                {"value": cv, "context_snippet": claim["context_snippet"]}
            )

    total = len(claims)
    ratio = 1.0 if total == 0 else round(anchored / total, 4)
    return {
        "total": total,
        "anchored": anchored,
        "unanchored": unanchored,
        "anchored_ratio": ratio,
    }
