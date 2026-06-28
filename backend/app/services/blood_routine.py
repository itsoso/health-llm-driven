"""血常规(CBC)深度评估 —— 消费已在库的血常规历史,给趋势 + 联合解读(非诊断)。

盘点结论:ALT/GGT 已通过 ``app/services/liver_health.py`` 拿到趋势 + 注入 agent,
但血常规(红细胞系/白细胞分类/血小板)无等价深度层 —— 一次真实体检对话里
红细胞压积 54% + Hb 173 同向偏高没有被联合解读、中性/淋巴比例倒置被过度归因。

本模块镜像 ``liver_health``,做三件事(全部 R4 安全:不诊断、不开药、不给剂量):
  1. HGB / HCT / RBC / WBC / PLT / NEUT% / LYMPH% 长期趋势(compute_trend)
  2. 红细胞系整体偏高(red_cell_elevation):**HGB 与 HCT 同向超上限才标**
     —— 单点常见伪影(腕式/脱水),只在两项互相佐证时才提示,降伪阳。
  3. 中性/淋巴比例倒置(NEUT%<50 且 LYMPH%>40):提示而非归因。

边界:全部"提示/趋势/需复查",反复声明非诊断、相关非因果、由血液科评估。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.chronic_trends import Trend, compute_trend, describe_trend

# ─────────────────────── CBC 指标名「锚定白名单」(单一真源) ───────────────────────
#
# 为什么不用「子串包含 + 黑名单」: resolve_code 的最长子串回退把 *任何* 含「血红蛋白」
# 的名字都判成 hemoglobin —— 黑名单是打地鼠 (网织红细胞血红蛋白含量/还原血红蛋白/血红蛋白A2/
# 胎儿血红蛋白/血红蛋白电泳 都会漏)。一个晚于 HGB 的此类行 → twin.labs.hemoglobin 变成 33/2.5
# → <170 → red_cell_elevation **静默不触发** (安全规则 under-alarm)。血小板/白细胞同病。
#
# 结构修复: 只接受「规范化后整串恰好等于某个 CBC 规范名」(^...$ 锚定)。复合名 (有额外
# 前/后缀 token) 必然 ^...$ 失配 → 被拒。安全取向: feeder 指标 (hemoglobin/hematocrit) 宁可
# 假阴 (不触发, 由 prompt blob + 用户兜底) 也绝不假阳 (错值 → 误判方向)。
#
# 本 helper 是 _collectors.fetch_latest_labs 与 blood_routine._history 共用的单一真源。

# 规范化时剥离的良性后缀 (体检系统常加, 不改变指标身份)
_BENIGN_SUFFIXES = ("测定", "定量", "检测", "计数值", "结果", "值")

# 每个 analyte 的锚定模式 (作用在规范化后的整串上)。键 = LabsContext 字段名。
_CBC_ANCHORED: dict[str, re.Pattern] = {
    # 血红蛋白 / 血红蛋白浓度 / HGB / HB / HEMOGLOBIN —— 拒糖化/平均/网织/还原/A2/F/电泳
    "hemoglobin": re.compile(r"^(血红蛋白|血色素|HGB|HB|HEMOGLOBIN)(浓度)?$"),
    "hematocrit": re.compile(r"^(红细胞压积|血细胞比容|红细胞比容|HCT|HEMATOCRIT)$"),
    # 红细胞计数 / RBC —— 拒裸「红细胞」(=会吞 HCT/MCV/RDW)
    "rbc": re.compile(r"^(红细胞计数|RBC|RED BLOOD CELL COUNT)$"),
    # 血小板 / 血小板计数 / PLT —— 拒 平均血小板体积(MPV)/血小板分布宽度(PDW)/大血小板比率(P-LCR)/血小板压积(PCT)
    "platelet": re.compile(r"^(血小板计数|血小板|PLT|PLATELET( COUNT)?)$"),
    # 白细胞 / 白细胞计数 / WBC —— 拒 白细胞酯酶/尿白细胞/白细胞介素6
    "wbc": re.compile(r"^(白细胞计数|白细胞|WBC)$"),
    "neutrophil_pct": re.compile(r"^(中性粒细胞百分比|中性粒细胞比率|中性粒细胞%|NEUT%?|NEUTROPHIL%?)$"),
    "lymphocyte_pct": re.compile(r"^(淋巴细胞百分比|淋巴细胞比率|淋巴细胞%|LYMPH%?|LYMPHOCYTE%?)$"),
    "mch": re.compile(r"^(平均血红蛋白量|平均红细胞血红蛋白量|MCH)$"),
    "mchc": re.compile(r"^(平均血红蛋白浓度|平均红细胞血红蛋白浓度|MCHC)$"),
}


def _normalize_indicator_name(name: Optional[str]) -> str:
    """规范化原始指标名以做锚定匹配:去空白、剥单位括号、去良性后缀、ASCII 大写。"""
    s = (name or "").strip()
    # 全角百分号 → 半角 (部分国内化验报告用 ％, 否则中性/淋巴百分比锚定会漏)
    s = s.replace("％", "%")
    # 去尾部括号单位/注释: (g/L) （%） 等 (中英文括号)
    s = re.sub(r"[（(][^（()]*[)）]\s*$", "", s).strip()
    # 去良性后缀 (可能叠加, 循环剥到不变)
    changed = True
    while changed:
        changed = False
        for suf in _BENIGN_SUFFIXES:
            if s.endswith(suf):
                s = s[: -len(suf)].strip()
                changed = True
    # 去内部空白 + ASCII 大写 (英文缩写大小写无关)
    s = re.sub(r"\s+", " ", s).upper()
    return s


def cbc_analyte_of(name: Optional[str]) -> Optional[str]:
    """原始指标名 → CBC analyte 键 (LabsContext 字段名),不匹配返回 None。

    锚定白名单: 规范化后整串恰好等于某规范名才接受。复合名 (网织红细胞血红蛋白含量、
    平均血小板体积、白细胞酯酶 等) 全部拒绝 —— 这是防 under-alarm 的结构性保证。
    """
    norm = _normalize_indicator_name(name)
    if not norm:
        return None
    for analyte, pattern in _CBC_ANCHORED.items():
        if pattern.match(norm):
            return analyte
    return None


def name_matches_cbc_analyte(name: Optional[str], analyte: str) -> bool:
    """该原始指标名是否锚定匹配指定 CBC analyte。"""
    return cbc_analyte_of(name) == analyte


# 宽 SQL 预筛关键字 (仅为性能缩小扫描行;最终判定一律走 cbc_analyte_of 锚定校验)。
_CBC_SQL_PREFILTER: dict[str, list[str]] = {
    "hemoglobin": ["血红蛋白", "血色素", "Hb", "HGB"],
    "hematocrit": ["红细胞压积", "红细胞比容", "血细胞比容", "HCT"],
    "rbc": ["红细胞计数", "RBC"],
    "wbc": ["白细胞", "WBC"],
    "platelet": ["血小板", "PLT"],
    "neutrophil_pct": ["中性粒细胞", "NEUT"],
    "lymphocyte_pct": ["淋巴细胞", "LYMPH"],
}

# 性别感知上限(成人):HGB g/L、HCT %。男性阈值更高;性别未知时取男性阈值
# (保守 = 少报,避免在不知性别时对女性用更低阈值产生假阳)。
_HGB_ULN_MALE = 170.0
_HGB_ULN_FEMALE = 150.0
_HCT_ULN_MALE = 50.0
_HCT_ULN_FEMALE = 45.0


def _is_female(sex: Optional[str]) -> bool:
    """性别归一:仅当明确为女性时返回 True;未知/其它一律按男性(保守,阈值更高)。"""
    if not sex:
        return False
    s = str(sex).strip().lower()
    return s in ("女", "f", "female", "woman")


def _red_cell_uln(sex: Optional[str]) -> tuple[float, float]:
    """返回 (HGB 上限, HCT 上限);性别未知 → 男性阈值。"""
    if _is_female(sex):
        return _HGB_ULN_FEMALE, _HCT_ULN_FEMALE
    return _HGB_ULN_MALE, _HCT_ULN_MALE


def _history(db: Session, user_id: int, analyte: str) -> list[tuple[date, float]]:
    """取某 CBC analyte 的 (日期, 值) 历史(value 非空)。

    防子串污染(结构性): SQL 用宽前缀仅缩小扫描行, **最终判定一律走 cbc_analyte_of 锚定
    校验** —— 只有规范化后整串等于该 analyte 规范名的行才进序列。复合名(网织红细胞血红蛋白
    含量/平均血小板体积/白细胞酯酶 等)即使被 SQL 前缀命中也会在 Python 侧被锚定拒绝。
    SELECT 取 name 列做锚定判定;返回 shape 仍是 (date, value)。
    """
    prefilters = _CBC_SQL_PREFILTER.get(analyte) or []
    if not prefilters:
        return []
    like = " OR ".join([f"name LIKE :p{i}" for i in range(len(prefilters))])
    params: dict[str, Any] = {"uid": user_id}
    for i, p in enumerate(prefilters):
        params[f"p{i}"] = f"%{p}%"
    rows = db.execute(text(
        f"SELECT record_date, value, name FROM medical_indicators "
        f"WHERE user_id = :uid AND value IS NOT NULL AND ({like}) "
        f"ORDER BY record_date"
    ), params).fetchall()

    out: list[tuple[date, float]] = []
    for r in rows:
        if r[0] is None:
            continue
        if not name_matches_cbc_analyte(r[2], analyte):  # 锚定白名单, 拒所有复合名
            continue
        d = _as_date(r[0])
        if d is not None:
            out.append((d, float(r[1])))
    return out


def _as_date(v: Any) -> Optional[date]:
    """record_date 归一:Postgres 返回 date,SQLite 返回 'YYYY-MM-DD' 字符串。"""
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _trend_dict(t: Optional[Trend]) -> Optional[dict[str, Any]]:
    if t is None:
        return None
    return {
        "n": t.n, "first_value": t.first_value, "last_value": t.last_value,
        "first_date": t.first_date.isoformat(), "last_date": t.last_date.isoformat(),
        "pct_change": t.pct_change, "direction": t.direction,
        "verdict": t.verdict(higher_is_worse=True),
    }


def assess_blood_routine(
    db: Session, user_id: int, sex: Optional[str] = None
) -> dict[str, Any]:
    """综合血常规评估。返回结构化 dict(含 flags + advice),全部为提示非诊断。

    sex: "男"/"女"/None。None 或未识别 → 用男性(更高)阈值,保守少报。
    """
    # 全部走锚定白名单 (cbc_analyte_of):复合名 (网织血红蛋白/MPV/白细胞酯酶 等) 结构性拒绝。
    hgb_h = _history(db, user_id, "hemoglobin")
    hct_h = _history(db, user_id, "hematocrit")
    rbc_h = _history(db, user_id, "rbc")
    wbc_h = _history(db, user_id, "wbc")
    plt_h = _history(db, user_id, "platelet")
    neut_h = _history(db, user_id, "neutrophil_pct")
    lymph_h = _history(db, user_id, "lymphocyte_pct")

    if not any([hgb_h, hct_h, rbc_h, wbc_h, plt_h, neut_h, lymph_h]):
        return {"available": False, "reason": "暂无血常规历史数据,建议做一次血常规检查。"}

    def _last(h: list[tuple[date, float]]) -> Optional[float]:
        return h[-1][1] if h else None

    hgb_last = _last(hgb_h)
    hct_last = _last(hct_h)
    rbc_last = _last(rbc_h)
    wbc_last = _last(wbc_h)
    plt_last = _last(plt_h)
    neut_last = _last(neut_h)
    lymph_last = _last(lymph_h)

    # 趋势(higher_is_worse 仅用于 verdict 措辞;CBC 高低各有意义,这里只描述方向)
    trends = {
        "hgb": compute_trend(hgb_h), "hct": compute_trend(hct_h),
        "rbc": compute_trend(rbc_h), "wbc": compute_trend(wbc_h),
        "plt": compute_trend(plt_h),
        "neut_pct": compute_trend(neut_h), "lymph_pct": compute_trend(lymph_h),
    }

    summary_lines: list[str] = []
    for label, key, unit in (
        ("血红蛋白", "hgb", " g/L"), ("红细胞压积", "hct", " %"),
        ("白细胞", "wbc", " 10⁹/L"), ("血小板", "plt", " 10⁹/L"),
    ):
        t = trends[key]
        if t:
            summary_lines.append(describe_trend(label, t, unit, higher_is_worse=True))

    flags: list[dict[str, Any]] = []
    advice: list[str] = []

    # ── flag 1: 红细胞系整体偏高 —— HGB 与 HCT 必须同向超上限(互相佐证) ──
    hgb_uln, hct_uln = _red_cell_uln(sex)
    if (hgb_last is not None and hgb_last > hgb_uln
            and hct_last is not None and hct_last > hct_uln):
        msg = (
            "红细胞系统整体偏高(HGB+HCT同向),建议血液科评估排除脱水/缺氧/"
            "睡眠呼吸暂停/真性红细胞增多;需复查确认。相关提示,非诊断。"
        )
        flags.append({
            "code": "red_cell_elevation",
            "message": msg,
            "hgb": hgb_last, "hct": hct_last,
            "hgb_uln": hgb_uln, "hct_uln": hct_uln,
        })
        advice.append(msg)

    # ── flag 2: 中性/淋巴比例倒置 —— 仅提示,不归因 ──
    if (neut_last is not None and neut_last < 50
            and lymph_last is not None and lymph_last > 40):
        msg = (
            "中性/淋巴比例倒置:单次百分比可能为生理性或病毒感染后,"
            "需结合绝对值与复查,非诊断。"
        )
        flags.append({
            "code": "neutrophil_lymphocyte_inversion",
            "message": msg,
            "neutrophil_pct": neut_last, "lymphocyte_pct": lymph_last,
        })
        advice.append(msg)

    if advice:
        advice.append("以上为基于历史数据的提示,相关非因果、非诊断;请以血液科/内科医生评估为准。")

    return {
        "available": True,
        "hgb_latest": hgb_last, "hct_latest": hct_last, "rbc_latest": rbc_last,
        "wbc_latest": wbc_last, "plt_latest": plt_last,
        "neutrophil_pct_latest": neut_last, "lymphocyte_pct_latest": lymph_last,
        "trends": {k: _trend_dict(v) for k, v in trends.items()},
        "summary_lines": summary_lines,
        "flags": flags,
        "advice": advice,
    }


def blood_routine_prompt_blob(
    db: Session, user_id: int, sex: Optional[str] = None
) -> str:
    """注入 agent 的紧凑文本;无血常规数据返回空串(仅在相关时注入)。"""
    a = assess_blood_routine(db, user_id, sex)
    if not a.get("available"):
        return ""
    lines = a.get("summary_lines", [])
    flags = a.get("flags", [])
    if not lines and not flags:
        return ""
    txt = "【血常规趋势(事实,非诊断)】"
    if lines:
        txt += "\n" + "\n".join(lines)
    for f in flags:
        txt += f"\n⚠ {f.get('message', '')}"
    return txt
