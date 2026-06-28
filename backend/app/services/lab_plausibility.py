"""确定性数值合理性闸 — 标记生理上极不寻常的录入/采集错误值。

动机: 生产事故里模型把 "SpO2 53%"(清醒常规体检几乎不可能, 多半是 95% 或脉搏 53
的录入错误)当成 🔴立即行动 的依据。本模块在工具结果回给模型前做一道确定性体检。

设计铁律 —— 标记 = "请核实, 别锚定, 若属实则就医", 永不等于 "忽略":
  一个被标记的值必须在**两个方向**都安全 ——
    • 若是录入/采集错误 → 提示用户核对原始报告;
    • 若数值属实 → 仍属危急范围, 必须建议尽快就医。
  这个语义即使在闸略微"过标"时也不会造成 under-alarm —— 这是相对原 SpO2-53 漏报
  的关键修正(原方案"请勿作为判断依据"会把一个真实危急值埋掉, 比 bug 本身更糟)。

两档 tier(措辞不同, 但**都**走上面的安全语义, tier 只调"几乎不可能" vs "危急/可疑"):
  • impossible —— 活体生理上**绝不可能**产生 → 几乎必为转录错误。
  • suspect    —— 真实危急 OR 可能错误, 无法区分 → 标记去**核实**, 绝不去忽略。

纯函数, 无外部依赖, 完全可测。任何异常都退回原文 —— 绝不能弄坏工具调用。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Tier 常量
TIER_IMPOSSIBLE = "impossible"
TIER_SUSPECT = "suspect"

# ── 同义词分类(token 精确匹配 vs 子串匹配) ─────────────────────
# 短 ASCII 同义词(hr/temp/...): 极易撞别的 token(hr ⊂ thr_value, temp ⊂ attempts),
#   必须**整 alnum-token 相等** —— 见 _SHORT_TO_METRIC / _SHORT_PATTERNS。
# 长词 / 中文同义词: 足够长, 子串匹配是安全的。
_LONG_SUBSTRING_SYNONYMS_BY_METRIC: dict[str, list[str]] = {
    "spo2": ["血氧饱和度", "血氧", "脉氧", "blood oxygen", "oxygen saturation"],
    "hr": ["心率", "脉搏", "heart rate", "heartrate", "heart_rate", "pulse_rate"],
    "temp": ["体温", "temperature"],
    "hb": ["血红蛋白", "hemoglobin"],
    "hct": ["红细胞压积", "血细胞比容", "红细胞比容", "hematocrit"],
    "sbp": ["收缩压", "systolic"],
    "dbp": ["舒张压", "diastolic"],
    "wbc": ["白细胞", "leukocyte"],
    "plt": ["血小板", "platelet"],
}

# ── 指标合理性边界(双档) ───────────────────────────────────────
# metric_key -> {
#   "impossible": (lo, hi),  # 活体绝不可能 → 几乎必为录入错误; None=该侧无界
#   "suspect":    (lo, hi),  # 真实危急 OR 错误(无法区分), 标记去核实; None=该侧无 suspect
#   "unit": "...",
# }
# 注: 血红蛋白(hb)走单位/量级感知, 边界以 g/dL 表达, 不放进本表。
_BOUNDS: dict[str, dict[str, Any]] = {
    "spo2": {
        "impossible": (None, 100.0),   # >100 不可能
        "suspect": (85.0, None),       # <85 危急/可疑 → 核实, 真则就医(catches SpO2 53)
        "unit": "%",
    },
    "temp": {
        "impossible": (20.0, 45.0),    # <20 或 >45 °C 不可能
        "suspect": (None, None),       # 无单独 suspect 档
        "unit": "°C",
    },
    "hr": {
        "impossible": (10.0, 300.0),   # <10 或 >300 bpm 不可能
        "suspect": (None, None),
        "unit": "bpm",
    },
    "hct": {
        "impossible": (5.0, 75.0),     # <5 或 >75 % 不可能
        "suspect": (None, 65.0),       # >65 % 危急/可疑(红细胞增多症 vs 错误)
        "unit": "%",
    },
    "sbp": {
        "impossible": (40.0, 320.0),   # <40 或 >320 mmHg 不可能
        "suspect": (None, None),
        "unit": "mmHg",
    },
    "dbp": {
        "impossible": (20.0, 220.0),   # <20 或 >220 mmHg 不可能
        "suspect": (None, None),
        "unit": "mmHg",
    },
    "wbc": {
        "impossible": (0.0, 200.0),    # <0(不可能) 或 >200 不可能
        "suspect": (1.0, None),        # <1.0 危急/可疑(重度粒缺 vs 错误) → 核实, 真则就医
        "unit": "×10^9/L",
    },
    "plt": {
        "impossible": (0.0, 3000.0),   # <0 或 >3000 不可能
        "suspect": (20.0, None),       # <20 危急/可疑(重度血小板减少 vs 错误)
        "unit": "×10^9/L",
    },
}

# 血红蛋白(单位/量级感知, g/dL 边界)
_HB_IMPOSSIBLE_GDL = (1.0, 26.0)    # <1 或 >26 g/dL (≈ <10 或 >260 g/L) 不可能
_HB_SUSPECT_GDL_LO = 5.0            # <5 g/dL (=50 g/L) 危急/可疑 → 核实, 真则就医

# 遍历裸 key:number 对时的 DENYLIST —— 这些 key 不是测量值, 绝不拿去比生理边界。
_DENYLIST_KEYS = {
    "reference_low", "reference_high", "ref_low", "ref_high",
    "normal_low", "normal_high", "count", "id", "score",
    "days", "age", "limit", "total", "min", "max",
}
_DENYLIST_SUFFIXES = ("_id", "_count", "_low", "_high")


def _to_float(value: Any) -> float | None:
    """解析为 float; 去掉 ↑↓ 箭头/空格/单位尾巴; 非数值返回 None(不抛)。"""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool 是 int 子类, 不当作数值指标
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    s = s.replace("↑", "").replace("↓", "").replace("⬆", "").replace("⬇", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _is_denylisted_key(key: str) -> bool:
    """裸 key:number 对的 key 是否属于非测量字段(参考范围/计数/id 等)。"""
    low = key.lower()
    if low in _DENYLIST_KEYS:
        return True
    return any(low.endswith(suf) for suf in _DENYLIST_SUFFIXES)


# 短同义词 → metric_key 归一(hgb/hb→hb, pulse→hr, ...)。
# 用 alnum 边界整 token 匹配: spo2 在 "spo2" 命中, 但 hr 在 "thr_value"/temp 在
# "attempts" 不命中(被前后 alnum 字符挡住)。SpO2(含数字)作为整 alnum run 安全保留。
_SHORT_TO_METRIC: dict[str, str] = {
    "spo2": "spo2",
    "hr": "hr", "pulse": "hr",
    "hb": "hb", "hgb": "hb",
    "hct": "hct",
    "plt": "plt",
    "wbc": "wbc",
    "sbp": "sbp",
    "dbp": "dbp",
    "temp": "temp",
}
# 预编译: (?<![a-z0-9])syn(?![a-z0-9]) —— syn 须是完整 alnum run(两侧非 alnum 或边界)。
_SHORT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"(?<![a-z0-9]){re.escape(syn)}(?![a-z0-9])"), metric)
    for syn, metric in _SHORT_TO_METRIC.items()
]


def _match_metric(name: str) -> str | None:
    """返回 name 匹配到的 metric_key('spo2'/'hr'/...), 无匹配返回 None。

    短 ASCII 同义词(hr/hb/temp/...): 整 alnum-token 相等(avoid thr_value→hr 误配)。
    长词/中文同义词: 子串匹配(它们足够长, 安全)。
    """
    if not name:
        return None
    low = name.lower()

    # 1) 短同义词整 token 匹配(alnum 边界)
    for pat, metric in _SHORT_PATTERNS:
        if pat.search(low):
            return metric

    # 2) 长词/中文同义词子串匹配
    for metric_key, syns in _LONG_SUBSTRING_SYNONYMS_BY_METRIC.items():
        if any(syn.lower() in low for syn in syns):
            return metric_key

    return None


def _check_bounds(metric_key: str, val: float, unit: str) -> tuple[str, str] | None:
    """对非 hb 指标做双档检查, 返回 (tier, reason) 或 None。"""
    spec = _BOUNDS.get(metric_key)
    if spec is None:
        return None

    imp = spec.get("impossible") or (None, None)
    imp_lo, imp_hi = imp
    if (imp_lo is not None and val < imp_lo) or (imp_hi is not None and val > imp_hi):
        rng = _fmt_range(imp_lo, imp_hi, unit)
        return (TIER_IMPOSSIBLE, f"生理上几乎不可能(活体范围约 {rng}),极可能是录入/采集错误")

    sus = spec.get("suspect") or (None, None)
    sus_lo, sus_hi = sus
    if (sus_lo is not None and val < sus_lo) or (sus_hi is not None and val > sus_hi):
        # 描述触发侧的危急阈值, 方向语义清晰
        if sus_lo is not None and val < sus_lo:
            edge = f"< {sus_lo:g}{unit}"
        else:
            edge = f"> {sus_hi:g}{unit}"
        return (
            TIER_SUSPECT,
            f"处于危急/可疑范围({edge}),需核实原始报告;若属实属危急,应尽快就医",
        )

    return None


def _check_hb(val: float, unit: str | None) -> tuple[str, str] | None:
    """血红蛋白单位/量级感知双档检查, 返回 (tier, reason) 或 None。"""
    unit_norm = (unit or "").lower().replace(" ", "")
    # 优先显式单位; 单位未知时才用量级启发(<30 视作 g/dL)。
    #   显式 g/L  → /10 得 g/dL(避免把 5 g/L 误当 5 g/dL)
    #   显式 g/dL → 原值
    #   未知      → <30 视作 g/dL, 否则 /10
    if "g/dl" in unit_norm or "gdl" in unit_norm:
        gdl = val
    elif "g/l" in unit_norm or "gl" in unit_norm:
        gdl = val / 10.0
    elif val < 30.0:
        gdl = val
    else:
        gdl = val / 10.0

    lo, hi = _HB_IMPOSSIBLE_GDL
    if gdl < lo or gdl > hi:
        return (
            TIER_IMPOSSIBLE,
            "血红蛋白生理上几乎不可能(活体约 1–26 g/dL / 10–260 g/L),极可能是录入错误",
        )
    if gdl < _HB_SUSPECT_GDL_LO:
        return (
            TIER_SUSPECT,
            "血红蛋白处于危急/可疑范围(< 50 g/L),需核实原始报告;若属实属危急,应尽快就医",
        )
    return None


def _fmt_range(lo: float | None, hi: float | None, unit: str) -> str:
    if lo is not None and hi is not None:
        return f"{lo:g}–{hi:g}{unit}"
    if lo is not None:
        return f"≥{lo:g}{unit}"
    if hi is not None:
        return f"≤{hi:g}{unit}"
    return unit


def scan_implausible(items: list[dict]) -> list[dict]:
    """items: [{"name": str, "value": float|str, "unit": str|None}, ...]

    返回 [{"name","value","tier","reason"}] —— 标记**生理上极不寻常**的值。
    每个 flag 都带 tier(impossible/suspect), 两档都走"核实, 真则就医"的安全语义。
    """
    flags: list[dict] = []
    if not items:
        return flags

    for item in items:
        try:
            name = str(item.get("name") or "")
            raw = item.get("value")
            unit = item.get("unit")
            val = _to_float(raw)
            if not name or val is None:
                continue

            metric_key = _match_metric(name)
            if metric_key is None:
                continue

            if metric_key == "hb":
                res = _check_hb(val, unit)
            else:
                u = _BOUNDS.get(metric_key, {}).get("unit", "")
                res = _check_bounds(metric_key, val, u)

            if res is not None:
                tier, reason = res
                flags.append({"name": name, "value": raw, "tier": tier, "reason": reason})
        except Exception:  # noqa: BLE001 — 单条解析异常不影响其它条
            continue

    return flags


# ── JSON 结果防御性包裹 ──────────────────────────────────────

def _dict_unit(node: dict) -> str | None:
    for k in ("unit", "units", "单位"):
        u = node.get(k)
        if isinstance(u, str):
            return u
    return None


def _metric_record_name(node: dict) -> str | None:
    """若 dict 是 {name:'血氧', value:53} 形态(显式指标名 + 显式 value 字段), 返回该名。"""
    for k in ("name", "indicator", "metric", "指标", "项目", "title"):
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _record_value(node: dict) -> Any:
    """取记录的显式 value 字段(value/result/数值)。"""
    for k in ("value", "result", "数值"):
        if k in node:
            return node.get(k)
    return None


def _collect_leaves(node: Any, out: list[dict], parent_unit: str | None = None) -> None:
    """递归遍历 dict/list, 收集**疑似测量值**叶子为 {name, value, unit}。

    优先识别"指标记录"形态: dict 有 name 字段 + 显式 value/result/数值 字段 →
      用 name 作指标名, 不扫该 dict 的其它 key(避免参考范围等噪音)。
    否则走裸 key:number 对, 但 DENYLIST 掉非测量 key(reference_low/count/id/...)。
    """
    if isinstance(node, dict):
        sibling_unit = _dict_unit(node)
        explicit_name = _metric_record_name(node)
        rec_value = _record_value(node)

        # 指标记录形态: 有 name + 有显式 value 标量 → 只收这一条, 不下钻它的兄弟 key
        if explicit_name is not None and rec_value is not None \
                and isinstance(rec_value, (int, float, str)) and not isinstance(rec_value, bool):
            out.append({"name": explicit_name, "value": rec_value, "unit": sibling_unit})
            # 仍需下钻嵌套容器(可能是 {latest:{...}, history:[...]})
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    _collect_leaves(value, out, sibling_unit)
            return

        # 普通 dict: 逐 key; 容器下钻, 标量按 key 名收(DENYLIST 非测量 key)
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                _collect_leaves(value, out, sibling_unit)
            elif isinstance(value, (int, float, str)) and not isinstance(value, bool):
                if _is_denylisted_key(str(key)):
                    continue
                out.append({"name": str(key), "value": value, "unit": sibling_unit})
    elif isinstance(node, list):
        for elem in node:
            _collect_leaves(elem, out, parent_unit)


def annotate_if_implausible(result_text: str) -> str:
    """防御性包裹: 保持 JSON 有效, 把警告注入为新 top-level key, 绝不修改原数据。

    • JSON object  → 注入 "_data_plausibility_warning": [{name,value,tier,reason},...] 后 re-dumps
    • JSON array   → 包成 {"data": <array>, "_data_plausibility_warning": [...]}
    • 非 JSON 自由文本 → 原样返回(无结构可扫; 保守 fail-open)
    每条 reason 都走"核实, 真则就医"的安全语义; 模型侧由 R4 prompt 强化"绝不忽略"。
    任何异常 → 原样返回(fail-open, 绝不弄坏工具调用)。
    """
    try:
        if not isinstance(result_text, str) or not result_text.strip():
            return result_text
        try:
            parsed = json.loads(result_text)
        except (json.JSONDecodeError, ValueError):
            # 非 JSON 自由文本: 没有结构可扫, 直接原样返回。
            # (历史上自由文本不含结构化数值; 真要扫纯文本需另写解析, 此处保守 fail-open)
            return result_text
        if not isinstance(parsed, (dict, list)):
            return result_text

        leaves: list[dict] = []
        _collect_leaves(parsed, leaves)
        flags = scan_implausible(leaves)
        if not flags:
            return result_text

        warning_payload = [
            {"name": f["name"], "value": f["value"], "tier": f["tier"], "reason": f["reason"]}
            for f in flags
        ]

        if isinstance(parsed, dict):
            # _data_plausibility_warning 是系统保留键,直接写入/覆盖
            # (它不是用户数据;若上游意外带了同名键,以本闸的检测结果为准更安全)
            enriched = dict(parsed)
            enriched["_data_plausibility_warning"] = warning_payload
            return json.dumps(enriched, ensure_ascii=False)
        else:  # list
            enriched = {"data": parsed, "_data_plausibility_warning": warning_payload}
            return json.dumps(enriched, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — 绝不能因本函数弄坏工具调用
        return result_text
