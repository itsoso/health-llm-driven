r"""GenUI metric_table 构建器 — 确定性把**已执行工具结果**打成 `reva-ui` 表格卡片。

背景 (latency-roadmap-phase2 rank1): 强模型以 12-13 tok/s 把工具结果重新打成大
markdown 表是剩余 decode 税的主因。改为后端从已在 messages 里的工具结果确定性生成
metric_table reva-ui 块 (零 LLM token), 正文只写结论 + 行动。

铁律 (R4): 本模块每一个单元格都来自工具结果 JSON 里的**具名字段**, 逐字 str() 落格,
LLM 不参与数据路径 —— 请用 `grep -n "llm\|LLM\|_call_llm" table_builder.py` 自证 (无命中)。
数据来源是 AgentExecutor 已执行的只读数据查询工具, 与图表 chart_builder 的确定性纪律一致。

覆盖的工具结果形状 (其余一律 build nothing → fail-open 回散文):
  - health_query_batch  —— {queries:[{dimension,agg,value,unit,n,note}], compare}
                            (声明式批查询, 结构 100% 干净, 永不截断; rank1 主目标)。
  - query_lab_indicators —— 单指标 {count,items:[...]} / 批量 {batch,by_name:{...}}
                            (MedicalIndicator + 血压桥接, json.dumps 干净)。
  - health_query(weight / blood_pressure / water) —— 原始 API JSON list/dict。
  - health_query(sleep) —— analyze_sleep_quality dict {daily_data:[{date,sleep_score,
                            total_sleep_duration,deep_sleep_duration,…}]} (逐日结构化 JSON)。
  - health_query(diet)  —— DailyDietSummary dict {meals:[{meal_type,food_items,calories,
                            protein,…}], total_*} (逐餐结构化 JSON)。

刻意跳过 (只文本, 绝不 regex-scrape): health_query(activity/steps/heart_rate/hrv/
body_battery/stress) 走 canonical `read_wearable_daily` 返回紧凑 LLM 文本 (非 JSON);
health_query(medical_exam) 走 `read_medical_indicators` 也是文本 —— 结构化化验/异常
清单只从 query_lab_indicators 出 (上面已覆盖)。

设计:
  - 纯函数 (无 DB / 无 HTTP / 无 LLM): 输入 (tool_name, args, result_str), 输出 block dict。
  - 任一形状解析失败 / 无可落行 / 字段缺失 → 返回 None (绝不编造单元格, fail-open 回散文)。
  - 契约与三端客户端对齐: type=metric_table, columns 2-4 个 {key,label}, rows ≤12 且
    值全部 str, title ≤20 字, footnote 可选。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.services.genui.chart_builder import render_reva_ui_block
from app.utils.blood_pressure_classify import SAFETY_WARNING_MARKER
from app.utils.number_format import format_display_number

# 客户端在 X-Reva-Client-Caps 声明本 token 才发 metric_table (与图表的 genui-v1 并列)。
GENUI_TABLE_CAP = "genui-table-v1"

METRIC_TABLE_TYPE = "metric_table"
_TABLE_VERSION = 1

# 契约硬约束
_MAX_ROWS = 12
_MIN_COLUMNS = 2
_MAX_COLUMNS = 4
_MAX_TITLE_CHARS = 20
# 单回合最多拼几张表 (多次批查询 → 多表; 防刷屏)。
MAX_TABLES = 3

_FOOTNOTE = "数据来自你的设备与体检记录 · 参考值非诊断"

# health_query / batch 的 dimension → 中文短名 (确定性标签, 非 LLM 文案)。
_DIMENSION_LABEL: Dict[str, str] = {
    "activity": "步数",
    "steps": "步数",
    "heart_rate": "静息心率",
    "hrv": "HRV",
    "sleep": "睡眠评分",
    "body_battery": "身体电量",
    "stress": "压力",
    "spo2": "血氧",
    "weight": "体重",
    "blood_pressure": "血压",
    "water": "饮水",
    "diet": "饮食",
    "supplements": "补剂",
    "medication": "用药",
    "medical_exam": "化验",
}

# agg → 中文说明 (确定性)。
_AGG_LABEL: Dict[str, str] = {
    "latest": "最新",
    "avg": "平均",
    "min": "最低",
    "max": "最高",
    "trend": "趋势(首尾差)",
}

# _api_get 对超长响应会加的"显示截断"尾注 —— 机器解析前先剥掉再 json.loads。
_TRUNCATION_SUFFIXES = ("\n...(仅显示前10条)", "\n...(数据已截断)")


# ---------------------------------------------------------------------------
# 值格式化 / JSON 解析 (纯工具)
# ---------------------------------------------------------------------------


def _fmt_value(value: Any, unit: Any = None) -> Optional[str]:
    """把标量值 + 单位拼成展示串 "58 ms" / "120/80 mmHg" / "8000"。

    value 为 None/空 → None (调用方跳过该行, 绝不落空单元格冒充数据)。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    u = str(unit).strip() if unit is not None else ""
    return f"{text} {u}".strip() if u else text


def _fmt_num(value: Any, unit: Any = None) -> Optional[str]:
    """数值单元格 (AGENTS.md §14 展示精度): 整数保持整数, 小数最多 2 位去尾零
    (350.0→'350', 6.166…→'6.17', 71.4→'71.4'), 其余交给 _fmt_value 逐字。
    供饮食 kcal/g、时长 h 等常来自 DB float 的列用, 避免 "6.166666666666667" 噪声。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = format_display_number(value)
    return _fmt_value(value, unit)


def _load_json_lenient(result: str) -> Optional[Any]:
    """Parse JSON while preserving safety text for the model response itself."""
    if not isinstance(result, str):
        return None
    text = result.strip()
    if not text or text.startswith("Error"):
        return None
    marker_index = text.find(SAFETY_WARNING_MARKER)
    if marker_index >= 0:
        text = text[:marker_index].rstrip()
        if not text:
            return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    for suffix in _TRUNCATION_SUFFIXES:
        if text.endswith(suffix):
            try:
                return json.loads(text[: -len(suffix)].rstrip())
            except (json.JSONDecodeError, ValueError):
                return None
    return None


def _make_block(
    title: str,
    columns: List[Tuple[str, str]],
    rows: List[Dict[str, str]],
    footnote: Optional[str] = _FOOTNOTE,
) -> Optional[dict]:
    """组装并校验 metric_table block; 任一契约约束不满足 → None (fail-open)。

    - columns 必须 2-4 个 {key,label}; rows 1-12 且每行按 column key 取值、全部 str。
    - 缺列的行补 "" (代表该字段无数据, 诚实空值, 非编造)。
    """
    if not (_MIN_COLUMNS <= len(columns) <= _MAX_COLUMNS):
        return None
    if not rows:
        return None
    keys = [k for k, _ in columns]
    norm_rows: List[Dict[str, str]] = []
    for row in rows[:_MAX_ROWS]:
        norm_rows.append({k: str(row.get(k, "")) for k in keys})
    block: Dict[str, Any] = {
        "type": METRIC_TABLE_TYPE,
        "v": _TABLE_VERSION,
        "title": (title or "").strip()[:_MAX_TITLE_CHARS],
        "columns": [{"key": k, "label": lbl} for k, lbl in columns],
        "rows": norm_rows,
    }
    if footnote:
        block["footnote"] = footnote
    return block


def _reference_note(item: Dict[str, Any]) -> str:
    """化验项的"参考/状态"列: 优先参考区间, 否则测量日期, 附异常标注 (全部来自字段)。"""
    low = item.get("reference_low")
    high = item.get("reference_high")
    unit = str(item.get("unit") or "").strip()
    parts: List[str] = []
    if low is not None and high is not None:
        rng = f"{low}–{high}"
        parts.append(f"{rng} {unit}".strip() if unit else rng)
    elif item.get("record_date"):
        parts.append(str(item["record_date"]))
    if item.get("is_abnormal") is True:
        parts.append("异常")
    return " · ".join(parts)


def _status_note(record: Dict[str, Any]) -> str:
    """状态/危险列: 逐字透传服务端已算好的分级 (如血压 ACC/AHA `category`) 或异常旗标。

    铁律 (R4): builder **绝不自行判定**医学等级 —— 只 relay 工具结果里已有的字段。
    无 `category`/`is_abnormal` → 返回 ""(不编造, 由调用方决定是否落列)。
    """
    parts: List[str] = []
    cat = record.get("category")
    if isinstance(cat, str) and cat.strip():
        parts.append(cat.strip())
    if record.get("is_abnormal") is True:
        parts.append("异常")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# 形状提取器 (每个 fail-open: 形状不符 / 无可落行 → None)
# ---------------------------------------------------------------------------


def _table_from_batch(payload: Any) -> Optional[dict]:
    """health_query_batch: {queries:[{dimension,agg,value,unit,n,note}], compare}。"""
    if not isinstance(payload, dict):
        return None
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        return None

    rows: List[Dict[str, str]] = []
    for q in queries:
        if not isinstance(q, dict):
            continue
        value = _fmt_value(q.get("value"), q.get("unit"))
        if value is None:
            continue  # agg 省略 / 空数据 / 不可聚合 → 无标量, 不落行 (绝不编造)
        dim = str(q.get("dimension") or "")
        metric = _DIMENSION_LABEL.get(dim, dim) or dim
        note_parts: List[str] = []
        # 危险 affordance: 工具结果若已带服务端分级/异常旗标 (category / is_abnormal),
        # 领起说明列 (逐字 relay, 不发明阈值)。当前可穿戴批查询多不带此字段 → 空跳过。
        status = _status_note(q)
        if status:
            note_parts.append(status)
        agg = q.get("agg")
        if isinstance(agg, str) and agg in _AGG_LABEL:
            days = q.get("days")
            note_parts.append(
                f"近{days}天{_AGG_LABEL[agg]}" if days else _AGG_LABEL[agg]
            )
        if q.get("n"):
            note_parts.append(f"{q['n']}天数据")
        if isinstance(q.get("note"), str) and q["note"].strip():
            note_parts.append(q["note"].strip())
        rows.append({"metric": metric, "value": value, "note": " · ".join(note_parts)})

    compare = payload.get("compare")
    if isinstance(compare, dict):
        cval = _fmt_value(compare.get("value"), compare.get("unit"))
        if cval is not None:
            op = compare.get("op")
            op_label = "差值" if op == "diff" else ("比值" if op == "ratio" else str(op or ""))
            rows.append({"metric": f"对比({op_label})", "value": cval, "note": ""})

    if not rows:
        return None
    columns = [("metric", "指标"), ("value", "数值"), ("note", "说明")]
    return _make_block("指标概览", columns, rows)


def _lab_items_table(items: List[Any], title: str) -> Optional[dict]:
    """把化验 items(单指标历史 或 已展开的一批)打成 日期|数值|参考 表。"""
    rows: List[Dict[str, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        value = _fmt_value(it.get("value"), it.get("unit"))
        if value is None:
            continue
        name = str(it.get("name") or it.get("name_en") or "").strip()
        rows.append(
            {
                "metric": f"{name} {it.get('record_date') or ''}".strip() if name else str(it.get("record_date") or ""),
                "value": value,
                "note": _reference_note(it),
            }
        )
    if not rows:
        return None
    columns = [("metric", "指标"), ("value", "数值"), ("note", "参考")]
    return _make_block(title, columns, rows)


def _table_from_lab(payload: Any) -> Optional[dict]:
    """query_lab_indicators: 单指标 {count,items} 或批量 {batch,by_name:{name:{items}}}。"""
    if not isinstance(payload, dict):
        return None

    if payload.get("batch") is True and isinstance(payload.get("by_name"), dict):
        # 批量: 每个指标取**最新一条** (items 已按 record_date desc), 一指标一行。
        rows: List[Dict[str, str]] = []
        for name, sub in payload["by_name"].items():
            if not isinstance(sub, dict):
                continue
            items = sub.get("items")
            if not isinstance(items, list) or not items:
                continue
            latest = items[0]
            if not isinstance(latest, dict):
                continue
            value = _fmt_value(latest.get("value"), latest.get("unit"))
            if value is None:
                continue
            label = str(latest.get("name") or name or "").strip()
            rows.append({"metric": label, "value": value, "note": _reference_note(latest)})
        if not rows:
            return None
        columns = [("metric", "指标"), ("value", "数值"), ("note", "参考")]
        return _make_block("化验指标", columns, rows)

    items = payload.get("items")
    if isinstance(items, list) and items:
        first = items[0]
        name = ""
        if isinstance(first, dict):
            name = str(first.get("name") or first.get("name_en") or "").strip()
        title = f"{name}化验历史" if name else "化验指标"
        return _lab_items_table(items, title)
    return None


def _table_from_weight(payload: Any) -> Optional[dict]:
    """health_query(weight): [{record_date, weight, body_fat_percentage}]。"""
    if not isinstance(payload, list) or not payload:
        return None
    records = [r for r in payload if isinstance(r, dict)]
    if not records:
        return None
    has_fat = all(r.get("body_fat_percentage") is not None for r in records)
    rows: List[Dict[str, str]] = []
    for r in records:
        value = _fmt_value(r.get("weight"), "kg")
        if value is None:
            continue
        row = {"date": str(r.get("record_date") or ""), "weight": value}
        if has_fat:
            row["fat"] = _fmt_value(r.get("body_fat_percentage"), "%") or ""
        rows.append(row)
    if not rows:
        return None
    columns = [("date", "日期"), ("weight", "体重")]
    if has_fat:
        columns.append(("fat", "体脂"))
    return _make_block("体重记录", columns, rows)


def _table_from_blood_pressure(payload: Any) -> Optional[dict]:
    """health_query(blood_pressure): [{record_date, systolic, diastolic, pulse, category}]。

    `category` 是 API 端 `classify_blood_pressure` 已算好的 ACC/AHA 分级 (正常 / 高血压1-3级
    / 危象 …), builder 逐字透传到"状态"列 (危险 affordance), 不自行判定 (见 `_status_note`)。
    """
    if not isinstance(payload, list) or not payload:
        return None
    records = [r for r in payload if isinstance(r, dict)]
    if not records:
        return None
    has_pulse = all(r.get("pulse") is not None for r in records)
    # 任一记录带服务端分级/异常旗标 → 加"状态"列; 全无则不加 (fail-closed 不编造)。
    has_status = any(_status_note(r) for r in records)
    rows: List[Dict[str, str]] = []
    for r in records:
        sys_v, dia_v = r.get("systolic"), r.get("diastolic")
        if sys_v is None or dia_v is None:
            continue
        row = {"date": str(r.get("record_date") or ""), "bp": f"{sys_v}/{dia_v} mmHg"}
        if has_pulse:
            row["pulse"] = _fmt_value(r.get("pulse"), "bpm") or ""
        if has_status:
            row["status"] = _status_note(r)
        rows.append(row)
    if not rows:
        return None
    columns = [("date", "日期"), ("bp", "血压")]
    if has_pulse:
        columns.append(("pulse", "脉搏"))
    if has_status:
        columns.append(("status", "状态"))
    return _make_block("血压记录", columns, rows)


def _table_from_water(payload: Any) -> Optional[dict]:
    """health_query(water): {record_date, total_amount, target_amount, records:[...]}。

    records 非空 → 逐条 [时间·水量] 明细(汇总的超集, footnote 保留总量/目标);否则回退
    2 行汇总卡。R4: 每格来自 records[].drink_time/amount 具名字段, 空值落诚实占位, 绝不编造。
    """
    if not isinstance(payload, dict):
        return None
    total = payload.get("total_amount")
    if total is None:
        return None

    records = payload.get("records")
    if isinstance(records, list) and records:
        detail_rows: List[Dict[str, str]] = []
        for r in records:
            if not isinstance(r, dict):
                continue
            amount_cell = _fmt_num(r.get("amount"), "ml")  # 水量=锚点字段
            if amount_cell is None:
                continue  # 无水量 → 跳过该条, 不落占位
            t = str(r.get("drink_time") or "").strip()  # "HH:MM:SS" → "HH:MM"
            time_cell = t[:5] if len(t) >= 5 else (t or "—")  # None/空 → 诚实占位
            detail_rows.append({"time": time_cell, "amount": amount_cell})
        if detail_rows:
            note = f"今日 {_fmt_num(total)}"
            target = payload.get("target_amount")
            if target is not None:
                note += f"/{_fmt_num(target)}"
            note += " ml"
            if len(detail_rows) > _MAX_ROWS:
                note += f" · 仅显示前 {_MAX_ROWS} 条"
            return _make_block(
                "今日饮水明细",
                [("time", "时间"), ("amount", "水量")],
                detail_rows,
                footnote=f"{note} · {_FOOTNOTE}",
            )

    # 回退: 2 行汇总卡(旧行为逐字节保留)
    rows: List[Dict[str, str]] = [{"item": "今日饮水", "value": _fmt_value(total, "ml") or ""}]
    target = payload.get("target_amount")
    if target is not None:
        rows.append({"item": "目标", "value": _fmt_value(target, "ml") or ""})
    return _make_block("饮水概览", [("item", "项目"), ("value", "数值")], rows)


def _table_from_sleep(payload: Any) -> Optional[dict]:
    """health_query(sleep): analyze_sleep_quality dict, 逐日行来自 daily_data。

    daily_data[]: {date, sleep_score, total_sleep_duration(分钟), deep_sleep_duration(分钟), …}。
    R4: 只 relay daily_data 里的 raw 字段 (sleep_score 是设备端评分, 逐字透传); 绝不读
    quality_assessment (服务端质量判定), 也不自行判睡眠好坏或把分钟换算成小时。
    """
    if not isinstance(payload, dict):
        return None
    daily = payload.get("daily_data")
    if not isinstance(daily, list) or not daily:
        return None
    records = [d for d in daily if isinstance(d, dict)]
    # 条件列: 任一天带该字段才建列 (全缺不建列, 绝不占位)。
    has_dur = any(r.get("total_sleep_duration") is not None for r in records)
    has_deep = any(r.get("deep_sleep_duration") is not None for r in records)
    has_score = any(r.get("sleep_score") is not None for r in records)
    rows: List[Dict[str, str]] = []
    for r in records:
        dur = _fmt_num(r.get("total_sleep_duration"), "分钟")
        deep = _fmt_num(r.get("deep_sleep_duration"), "分钟")
        score = _fmt_num(r.get("sleep_score"))
        if dur is None and deep is None and score is None:
            continue  # 仅日期无任何指标 → 不落空行 (绝不编造)
        row = {"date": str(r.get("date") or "")}
        if has_dur:
            row["dur"] = dur or ""
        if has_deep:
            row["deep"] = deep or ""
        if has_score:
            row["score"] = score or ""
        rows.append(row)
    if not rows:
        return None
    columns = [("date", "日期")]
    if has_dur:
        columns.append(("dur", "时长"))
    if has_deep:
        columns.append(("deep", "深睡"))
    if has_score:
        columns.append(("score", "评分"))
    return _make_block("睡眠记录", columns, rows)


# meal_type → 中文餐次 (确定性映射, 对齐 schemas/diet.MEAL_TYPE_ZH; 非 LLM 文案)。
_MEAL_LABEL: Dict[str, str] = {
    "breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐", "extra": "其他",
}


def _table_from_diet(payload: Any) -> Optional[dict]:
    """health_query(diet): DailyDietSummary dict, 逐餐行来自 meals。

    meals[]: {meal_type, food_items, calories, protein, …}。R4: 只 relay summary 携带的
    字段 (餐次/内容/热量/蛋白); 未识别营养 → 空单元格 (非 0/占位), 绝不重算或判吃得好坏。
    合计不入表 (顶层 total_* 用 None→0 求和, 部分缺项会被误读为真总量; 交给正文叙事说)。
    """
    if not isinstance(payload, dict):
        return None
    meals = payload.get("meals")
    if not isinstance(meals, list) or not meals:
        return None
    entries = [m for m in meals if isinstance(m, dict)]
    has_cal = any(m.get("calories") is not None for m in entries)
    has_pro = any(m.get("protein") is not None for m in entries)
    rows: List[Dict[str, str]] = []
    for m in entries:
        food = str(m.get("food_items") or "").strip()
        if not food:
            continue  # 内容 (锚点字段) 缺失 → 跳过该餐
        mt = str(m.get("meal_type") or "").strip().lower()
        row = {"meal": _MEAL_LABEL.get(mt, mt) or mt, "food": food}
        if has_cal:
            row["cal"] = _fmt_num(m.get("calories"), "kcal") or ""
        if has_pro:
            row["pro"] = _fmt_num(m.get("protein"), "g") or ""
        rows.append(row)
    if not rows:
        return None
    columns = [("meal", "餐次"), ("food", "内容")]
    if has_cal:
        columns.append(("cal", "热量"))
    if has_pro:
        columns.append(("pro", "蛋白"))
    return _make_block("今日饮食", columns, rows)


# ---------------------------------------------------------------------------
# 分发 + 聚合
# ---------------------------------------------------------------------------

_SINGLE_QUERY_TABLE = {
    "weight": _table_from_weight,
    "blood_pressure": _table_from_blood_pressure,
    "water": _table_from_water,
    "sleep": _table_from_sleep,
    "diet": _table_from_diet,
}


def load_tool_result_json(result: str) -> Optional[Any]:
    """公开:宽松解析已执行工具的结果字符串(剥 `_api_get`/`_truncate_for_display` 显示截断尾注)。

    供 diet_summary 等其它 GenUI 卡的 emission 复用,与 metric_table 走**同一** JSON 解析真源
    —— 传输/截断行为若变,两条卡路径同步跟随,不会一条能出卡、另一条静默回退散文。
    """
    return _load_json_lenient(result)


def build_table_from_tool_call(
    tool_name: str, args: Optional[dict], result: str
) -> Optional[dict]:
    """按工具名分发到对应提取器; 无法确定性覆盖 → None (fail-open 回散文)。"""
    payload = _load_json_lenient(result)
    if payload is None:
        return None
    if tool_name == "health_query_batch":
        return _table_from_batch(payload)
    if tool_name == "query_lab_indicators":
        return _table_from_lab(payload)
    if tool_name == "health_query":
        dim = str((args or {}).get("dimension") or "").strip().lower()
        builder = _SINGLE_QUERY_TABLE.get(dim)
        return builder(payload) if builder else None
    return None


def build_tables_from_tool_calls(
    tool_calls: List[Tuple[str, Optional[dict], str]],
) -> List[dict]:
    """把本回合已执行的 (tool_name, args, result) 序列打成 metric_table blocks。

    - 逐条尝试提取, 失败/无覆盖跳过 (build nothing);
    - 去重 (同一 block 只出一次), 全回合封顶 MAX_TABLES 张 (防刷屏)。
    """
    out: List[dict] = []
    seen: set = set()
    for name, args, result in tool_calls:
        block = build_table_from_tool_call(name, args, result)
        if block is None:
            continue
        fingerprint = json.dumps(block, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        out.append(block)
        if len(out) >= MAX_TABLES:
            break
    return out


def render_metric_table_block(block: dict) -> str:
    """把 metric_table block 渲染成 ```reva-ui fenced 文本 (与图表同一 fence 信封)。"""
    return render_reva_ui_block(block)
