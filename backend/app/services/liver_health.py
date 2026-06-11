"""肝脏健康评估 —— 消费已在库的肝酶历史,给趋势 + 脂肪肝风险(非诊断)。

盘点结论:ALT/GGT 多年趋势在 medical_indicators 里却无人消费。本模块:
  1. ALT / GGT 长期趋势(compute_trend)
  2. AST/ALT 比值(<1 倾向脂肪肝,>2 倾向酒精性/纤维化 —— 仅倾向,非诊断)
  3. FIB-4 肝纤维化指数 = (年龄×AST) / (血小板×√ALT) —— **仅当有血小板时算**,
     缺血小板明确返回 None 并提示补一次血常规(宁可不答不可错答)
  4. 脂肪肝风险启发(ALT 偏高 + 高 TG / 高 BMI)—— 标注为"提示",非诊断

边界:全部"提示/趋势",反复声明非诊断、需结合腹部超声 + 医生。
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.chronic_trends import Trend, compute_trend, describe_trend

# 指标名匹配(中文体检报告常见写法 + 英文缩写)
_ALT_PAT = ["谷丙转氨酶", "丙氨酸氨基转移酶", "ALT"]
_AST_PAT = ["谷草转氨酶", "天门冬氨酸氨基转移酶", "天冬氨酸氨基转移酶", "AST"]
_GGT_PAT = ["谷氨酰转肽酶", "γ-谷氨酰", "谷氨酰基转移酶", "GGT", "GGT/GT"]
_PLT_PAT = ["血小板计数", "血小板", "PLT"]
_TG_PAT = ["甘油三酯", "三酰甘油", "TG"]

# 上限(成人,U/L);超过视为偏高(用于脂肪肝风险启发)
_ALT_ULN = 50.0
_GGT_ULN = 60.0


def _history(db: Session, user_id: int, patterns: list[str]) -> list[tuple[date, float]]:
    """按多个名称模式取某指标的 (日期, 值) 历史(value 非空)。"""
    like = " OR ".join([f"name LIKE :p{i}" for i in range(len(patterns))])
    params: dict[str, Any] = {"uid": user_id}
    for i, p in enumerate(patterns):
        params[f"p{i}"] = f"%{p}%"
    rows = db.execute(text(
        f"SELECT record_date, value FROM medical_indicators "
        f"WHERE user_id = :uid AND value IS NOT NULL AND ({like}) "
        f"ORDER BY record_date"
    ), params).fetchall()
    return [(_as_date(r[0]), float(r[1])) for r in rows if r[0] is not None]


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


def _fib4(age: float, ast: float, alt: float, platelets: float) -> Optional[float]:
    """FIB-4 = (年龄×AST) / (血小板[10^9/L] × √ALT)。任一缺/非法返回 None。"""
    if not (age and ast and alt and platelets) or alt <= 0 or platelets <= 0:
        return None
    return round((age * ast) / (platelets * math.sqrt(alt)), 2)


def _fib4_band(fib4: float, age: float) -> str:
    """FIB-4 风险分层(<65 岁阈值 1.30/2.67;≥65 用 2.0/2.67)。"""
    low, high = (2.0, 2.67) if age >= 65 else (1.30, 2.67)
    if fib4 < low:
        return "低(进展性纤维化可能性小)"
    if fib4 < high:
        return "中(不确定,建议专科进一步评估)"
    return "偏高(建议消化/肝病专科评估)"


def assess_liver(db: Session, user_id: int, age: Optional[float] = None) -> dict[str, Any]:
    """综合肝脏评估。返回结构化 dict(含 advice 列表),全部为提示非诊断。"""
    alt_h = _history(db, user_id, _ALT_PAT)
    ast_h = _history(db, user_id, _AST_PAT)
    ggt_h = _history(db, user_id, _GGT_PAT)
    plt_h = _history(db, user_id, _PLT_PAT)
    tg_h = _history(db, user_id, _TG_PAT)

    if not alt_h and not ggt_h:
        return {"available": False, "reason": "暂无肝酶历史数据,建议做一次肝功能检查。"}

    alt_trend: Optional[Trend] = compute_trend(alt_h)
    ggt_trend: Optional[Trend] = compute_trend(ggt_h)
    alt_last = alt_h[-1][1] if alt_h else None
    ast_last = ast_h[-1][1] if ast_h else None
    ggt_last = ggt_h[-1][1] if ggt_h else None
    plt_last = plt_h[-1][1] if plt_h else None
    tg_last = tg_h[-1][1] if tg_h else None

    ast_alt_ratio = round(ast_last / alt_last, 2) if (ast_last and alt_last) else None

    fib4 = _fib4(age or 0, ast_last or 0, alt_last or 0, plt_last or 0)
    fib4_band = _fib4_band(fib4, age or 0) if fib4 is not None else None

    advice: list[str] = []
    summary_lines: list[str] = []

    if alt_trend:
        summary_lines.append(describe_trend("ALT", alt_trend, " U/L", higher_is_worse=True))
    if ggt_trend:
        summary_lines.append(describe_trend("GGT", ggt_trend, " U/L", higher_is_worse=True))

    # GGT 持续偏高/上升:最敏感的肝胆/代谢负荷信号
    if ggt_last and ggt_last > _GGT_ULN:
        advice.append(f"GGT {ggt_last:g} U/L 高于上限({_GGT_ULN:g});GGT 对酒精、脂肪肝、药物/补剂负荷敏感,"
                      "建议复盘近期饮酒、保健品与体重。")
    elif ggt_trend and ggt_trend.verdict(higher_is_worse=True) == "worsening":
        advice.append("GGT 长期呈上升趋势,虽未必超标,但值得关注饮酒/体重/补剂负荷。")

    if alt_last and alt_last > _ALT_ULN:
        advice.append(f"ALT {alt_last:g} U/L 偏高,提示肝细胞负荷;结合 AST/ALT 比值与超声判断。")

    # AST/ALT 比值倾向(仅倾向)
    if ast_alt_ratio is not None:
        if ast_alt_ratio < 1:
            advice.append(f"AST/ALT={ast_alt_ratio} (<1),在排除其他病因下更常见于脂肪肝倾向(非诊断)。")
        elif ast_alt_ratio > 2:
            advice.append(f"AST/ALT={ast_alt_ratio} (>2),建议排查酒精性肝损或进展性纤维化(就医)。")

    # 脂肪肝风险启发(非诊断):ALT 偏高 + (高 TG 或已知超重)
    fatty_risk = None
    if alt_last and alt_last > 40 and tg_last and tg_last > 1.7:
        fatty_risk = "偏高"
        advice.append("ALT 偏高 + 甘油三酯偏高 → 代谢相关脂肪性肝病(MASLD)风险提示;"
                      "首选干预=减重 5–10%、减少精制糖/酒精、增加有氧。建议做一次腹部超声确认。")

    # FIB-4 缺血小板 → 明确提示补数据(不臆测)
    if fib4 is None and (alt_last and ast_last):
        advice.append("缺血小板计数,无法计算 FIB-4 肝纤维化指数;下次体检加做血常规即可自动评估。")

    advice.append("以上为基于历史数据的趋势提示,非诊断;肝酶持续异常请到消化/肝病科,并完善腹部超声。")

    return {
        "available": True,
        "alt_latest": alt_last, "ast_latest": ast_last, "ggt_latest": ggt_last,
        "platelets_latest": plt_last, "tg_latest": tg_last,
        "ast_alt_ratio": ast_alt_ratio,
        "alt_trend": _trend_dict(alt_trend), "ggt_trend": _trend_dict(ggt_trend),
        "fib4": fib4, "fib4_band": fib4_band,
        "fatty_liver_risk": fatty_risk,
        "summary_lines": summary_lines,
        "advice": advice,
    }


def _trend_dict(t: Optional[Trend]) -> Optional[dict[str, Any]]:
    if t is None:
        return None
    return {
        "n": t.n, "first_value": t.first_value, "last_value": t.last_value,
        "first_date": t.first_date.isoformat(), "last_date": t.last_date.isoformat(),
        "pct_change": t.pct_change, "direction": t.direction,
        "verdict": t.verdict(higher_is_worse=True),
    }


def liver_prompt_blob(db: Session, user_id: int, age: Optional[float] = None) -> str:
    """注入 agent 的紧凑文本;无数据返回空串。"""
    a = assess_liver(db, user_id, age)
    if not a.get("available"):
        return ""
    lines = a.get("summary_lines", [])
    flags = [x for x in (a.get("fatty_liver_risk"), a.get("fib4_band")) if x]
    if not lines and not flags:
        return ""
    txt = "【肝脏趋势(事实,非诊断)】\n" + "\n".join(lines)
    if a.get("fib4") is not None:
        txt += f"\nFIB-4={a['fib4']}(风险{a['fib4_band']})"
    if a.get("fatty_liver_risk"):
        txt += f"\n脂肪肝风险提示:{a['fatty_liver_risk']}"
    return txt
