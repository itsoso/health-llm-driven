"""export_context_pack.py —— 拉 GET /twin/me,组装「个人数据上下文包」文本。

用途:
  1. context_pack.md — 喂给「商用模型 + 粘贴数据」臂(chatgpt_context)的材料。
  2. facts.md(--facts-out)— 评审用「用户真实数据事实清单」,judge --facts 消费:
     twin 扁平清单 + 医疗检查记录(/medical-exams/me)+ 用药疗程投影
     (/medication-course/upcoming,系统注入 prompt 的派生数据)。
     缺类目会让 judge 把参评臂合法引用的真实数据误标 fabrication
     (实例:胃镜"胃窦溃疡 A1期"、疗程结束日 2026-08-11)。

context_pack 优先复用 backend 的 twin formatter(twin_to_prompt_blob)保证与线上
prompt 一致;若 twin JSON 与 schema 漂移导致 model_validate 失败,回退到手工按
分区格式化(fail-loud 标注回退)。

环境:
  REVA_EVAL_BASE   默认 https://health.executor.life/api/v1
  REVA_EVAL_TOKEN  必填(env)

用法:
  REVA_EVAL_TOKEN=... python -m evals.comparative.export_context_pack \
      --out context_pack.md --facts-out facts.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from evals.comparative.common import bearer_headers, eval_base, http_get_json


def fetch_twin(base: Optional[str] = None) -> Dict[str, Any]:
    base = (base or eval_base()).rstrip("/")
    return http_get_json(f"{base}/twin/me?fresh=true", headers=bearer_headers(), timeout=90)


# 疗程投影拉宽到一年:facts 要覆盖所有已登记的结束日,不止 prompt 注入的 45 天窗。
COURSE_WINDOW_DAYS = 365


def fetch_medical_exams(base: Optional[str] = None) -> List[Dict[str, Any]]:
    base = (base or eval_base()).rstrip("/")
    return http_get_json(f"{base}/medical-exams/me", headers=bearer_headers(), timeout=90)


def fetch_medication_courses(
    base: Optional[str] = None, within_days: int = COURSE_WINDOW_DAYS
) -> List[Dict[str, Any]]:
    base = (base or eval_base()).rstrip("/")
    data = http_get_json(
        f"{base}/medication-course/upcoming?within_days={within_days}",
        headers=bearer_headers(),
        timeout=90,
    )
    return data.get("items", [])


def _blob_via_formatter(twin_json: Dict[str, Any]) -> Optional[str]:
    """尝试用 backend formatter。schema 漂移则返回 None(调用方回退手工)。"""
    try:
        from app.twin.schema import HealthTwin
        from app.twin.formatter import twin_to_prompt_blob

        twin = HealthTwin.model_validate(twin_json)
        return twin_to_prompt_blob(twin)
    except Exception as e:  # noqa: BLE001 — 不静默:打到 stderr,回退手工格式化
        print(f"[context_pack] formatter 复用失败(schema 漂移?),回退手工格式化: {e}", file=sys.stderr)
        return None


# (中文标题, twin JSON 分区 key) — _manual_blob 与 facts 扁平清单共用
_PARTITIONS: List[tuple] = [
    ("生理(HRV/睡眠/心率)", "physiological"),
    ("身体成分", "body_composition"),
    ("化验", "labs"),
    ("CGM 血糖", "cgm"),
    ("用药", "medication"),
    ("补剂", "supplement"),
    ("基因", "genetic"),
    ("环境", "environment"),
    ("行为(饮食/饮水/运动)", "behavioral"),
    ("慢病", "chronic"),
    ("目标", "goals"),
]


def _manual_blob(twin_json: Dict[str, Any]) -> str:
    """手工按 twin JSON 分区格式化(formatter 不可用时的回退)。只输出有数据的分区。"""
    parts: List[str] = []
    for title, key in _PARTITIONS:
        mapping = twin_json.get(key)
        if not isinstance(mapping, dict):
            continue
        kv = {k: v for k, v in mapping.items() if v not in (None, "", [], {})}
        if kv:
            body = "; ".join(f"{k}={v}" for k, v in kv.items())
            parts.append(f"【{title}】{body}")
    return "\n".join(parts)


def build_context_pack(twin_json: Dict[str, Any]) -> str:
    """组装 markdown 上下文包。formatter 优先,手工回退。"""
    blob = _blob_via_formatter(twin_json)
    source = "backend twin_to_prompt_blob"
    if not blob:
        blob = _manual_blob(twin_json)
        source = "手工分区格式化(formatter 回退)"
    if not blob.strip():
        blob = "(twin 无可用数据)"
    lines = [
        "# 个人健康数据上下文包",
        "",
        "> 用途:粘贴到商用大模型对话前,作为「你已知我的健康数据」的背景材料。",
        f"> 生成方式:{source}。",
        "> 该材料仅供评测,只读拉取,不含 token。",
        "",
        "## 数据摘要",
        "",
        "```",
        blob,
        "```",
        "",
    ]
    # 附一份原始 JSON(裁掉可能的大数组)供需要精确值的臂参考
    lines += ["## 原始 Twin JSON(供精确核对)", "", "```json", json.dumps(twin_json, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


# ─────────────────────────── facts.md(评审用事实清单) ───────────────────────────

# 头部评审须知:与 judge rubric 的 honesty 条款同一口径,在清单侧再强调一次。
# 背景:实测 judge 曾把清单里已有的 sleep_score_latest=42(回答写作"睡眠评分42分")
# 误标 fabrication —— 键名英文/回答中文的映射 + 未覆盖类目口径,都要在清单头重申。
_FACTS_HEADER = """# 用户真实数据事实清单(评审专用)

> 评审须知(与 rubric 的 honesty 条款一致,此处再强调一次):
> 1. 下面每一行都是该用户的真实数据。部分参评产品可合法访问这些数据——回答中引用
>    与清单一致或可由清单合理推导的数据,是期望行为,不是编造。
> 2. 清单键名多为英文,回答可能用中文措辞引用同一数据(如 sleep_score_latest=42 ↔
>    「睡眠评分42分」)。语义等同即视为一致,不要因语言/措辞差异标 fabrication。
> 3. 清单未覆盖的类目,回答里出现的数据存疑不扣分,至多在 reason 注明「无法核验」。
> 4. 标注「(无记录)」的类目 = 已覆盖且为空:回答凭空引用该类目的具体记录才算编造。
"""


def _twin_facts_lines(twin_json: Dict[str, Any]) -> List[str]:
    """twin 分区扁平化:一行一个键值,便于 judge 逐条比对。"""
    lines: List[str] = []
    for title, key in _PARTITIONS:
        mapping = twin_json.get(key)
        if not isinstance(mapping, dict):
            continue
        for k, v in mapping.items():
            if v in (None, "", [], {}):
                continue
            lines.append(f"[{title}] {k}={v}")
    return lines


def _exam_facts_lines(exams: List[Dict[str, Any]]) -> List[str]:
    """医疗检查记录(胃镜/MRI/血检等):总体评价 + 结论 + 逐项结果。

    该类目缺失时,judge 会把合法引用的检查结论(如「胃窦溃疡 A1期」)误标 fabrication。
    """
    tag = "[医疗检查记录]"
    if not exams:
        return [f"{tag} (无记录)"]
    lines: List[str] = []
    for e in exams:
        head = f"{tag} {e.get('exam_date')} {e.get('exam_type') or '检查'}"
        meta: List[str] = []
        if e.get("hospital_name"):
            meta.append(str(e["hospital_name"]))
        if e.get("overall_assessment"):
            meta.append(f"总体评价={e['overall_assessment']}")
        lines.append(head + (": " + "; ".join(meta) if meta else ""))
        for c in e.get("conclusions") or []:
            if isinstance(c, dict):
                title = c.get("title") or c.get("category") or ""
                desc = c.get("description") or ""
                recs = c.get("recommendations")
                rec_txt = ""
                if recs:
                    rec_txt = f";建议: {recs if isinstance(recs, str) else '; '.join(str(r) for r in recs)}"
                lines.append(f"{head} 结论: {title} {desc}{rec_txt}".rstrip())
            else:
                lines.append(f"{head} 结论: {c}")
        for it in e.get("items") or []:
            val = it.get("value") if it.get("value") is not None else (it.get("value_text") or "")
            unit = it.get("unit") or ""
            result = it.get("result") or it.get("is_abnormal") or ""
            suffix = f"({result})" if result else ""
            lines.append(f"{head} 项目 {it.get('item_name')}={val}{unit}{suffix}")
    return lines


def _course_facts_lines(courses: List[Dict[str, Any]], within_days: int = COURSE_WINDOW_DAYS) -> List[str]:
    """用药疗程投影:疗程结束日是系统真实注入 prompt 的派生数据(medication_course_service),
    不在清单里 judge 会把「疗程结束日 2026-08-11」这类合法引用误标 fabrication。
    """
    tag = "[用药疗程投影(系统派生,已注入产品 prompt)]"
    if not courses:
        # 措辞点明窗口边界:窗口外/已过期的疗程不算"覆盖且为空",按未覆盖类目处理
        return [f"{tag} (未来{within_days}天内无已登记的疗程结束日;窗口外不据此判编造)"]
    lines: List[str] = []
    for c in courses:
        fu = c.get("followup")
        tail = f" → 届时建议{fu['item_name']}({fu['department']})" if fu else ""
        lines.append(
            f"{tag} {c.get('medication')}: 疗程结束日={c.get('end_date')}(还剩{c.get('days_left')}天){tail}"
        )
    return lines


def build_facts_md(
    twin_json: Dict[str, Any],
    exams: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    courses_within_days: int = COURSE_WINDOW_DAYS,
) -> str:
    """组装评审用事实清单(judge --facts 消费)。"""
    lines = [_FACTS_HEADER]
    lines += _twin_facts_lines(twin_json)
    lines += _exam_facts_lines(exams)
    lines += _course_facts_lines(courses, courses_within_days)
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="export_context_pack", description="导出个人数据上下文包(只读)")
    ap.add_argument("--out", default="context_pack.md", help="输出 markdown 路径")
    ap.add_argument(
        "--facts-out",
        default=None,
        help="同时导出评审用事实清单(judge --facts 消费):twin 扁平清单 + 医疗检查记录 + 用药疗程投影",
    )
    args = ap.parse_args(argv)

    twin_json = fetch_twin()
    pack = build_context_pack(twin_json)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pack, encoding="utf-8")
    print(f"[context_pack] 写入 {out} ({len(pack)} chars)", file=sys.stderr)

    if args.facts_out:
        # 拉取失败直接抛(fail-loud):缺类目的 facts 会让 judge 冤枉合法引用,宁可不产出
        exams = fetch_medical_exams()
        courses = fetch_medication_courses()
        facts = build_facts_md(twin_json, exams, courses)
        facts_out = Path(args.facts_out)
        facts_out.parent.mkdir(parents=True, exist_ok=True)
        facts_out.write_text(facts, encoding="utf-8")
        print(
            f"[context_pack] 写入 {facts_out} ({len(facts)} chars; "
            f"检查记录 {len(exams)} 份, 疗程投影 {len(courses)} 条)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
