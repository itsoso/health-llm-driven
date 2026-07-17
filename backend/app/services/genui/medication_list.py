"""GenUI medication_list 构建器 — 确定性把当前用药清单打成结构化 reva-ui 卡片。

汇总卡族第三张(diet / sleep 之后)。数据来自 health_query(dimension='medication')
= `GET /medication/medications/me`(active_only 默认 True → 只含在用药品),逐项由
`app/api/medication.py:_serialize_medication` 产出。

**R4 纪律(本卡最硬的一条,与 diet/sleep 的关键差异)**:
这张卡只**如实呈现用户自己登记的用药记录**,零推断、零改写。
  - `dosage`/`frequency`/`timing_label` 全部**原样透传**用户记录里的字符串,builder 绝不
    解析剂量数字、绝不换算、绝不补默认值、绝不推断"应该怎么吃"。
  - **刻意不做 observations 派生**(diet 有、sleep 有,本卡没有):用药领域不存在可安全
    派生的常识阈值 —— "这个剂量偏高/偏低"是处方判断,属临床医生职权。别自己发明。
  - 卡内不出现任何建议/命令式文案;解读与行动留给散文正文与安全面板。

**安全告警只在卡级、绝不逐药归因**(集成时揪出的契约缺陷,勿回退):
`/medications/me` 的 `safety_alerts` 是**用户级**列表 —— 服务端 `_medication_safety_alerts(db,
user_id)` 按**整个用药方案**跑 PGx/DDI/DSI,再把**同一份**挂到每个条目上
(`api/medication.py: list_my_medications`)。所以它**不能**被读成"该药触发了告警":一条
`dsi.ppi_b12` 会让清单里每味药(哪怕铝碳酸镁)都带着它。
→ 故本卡**不产出**逐药的 `has_safety_alert` 字段。发一个数据支撑不了的逐项字段 = 保证客户端
误渲染成逐药徽标 = **编造因果**(集成前的初版契约正是这么错的)。只在**卡级**给
`safety_alert_count`("你有 N 条用药安全提示")。
**加层不减层不受影响**:信号一条没少 —— 有告警时卡级仍如实呈现,且 alert 正文不进卡
(安全面板与散文已完整呈现),卡只给存在性计数,不把告警二次改写成弱化版本。

**跨端契约铁律**(diet 上线即坏的教训):块内 `v` 是**整数 1**(移动端 fence parser 校验
v===1),cap token 才用字符串 "genui-medication-list-v1";字段名与 mobile MedicationListCard
的 parse* 一字对齐(medications[name/dosage/frequency/timing_label/category/purpose/
start_date] · total · safety_alert_count)。
"""
from __future__ import annotations

import json
from typing import Any, Optional

MEDICATION_LIST_TYPE = "medication_list"
GENUI_MEDICATION_LIST_CAP = "genui-medication-list-v1"  # 客户端能力位(点亮门控)
# reva-ui 信封版本 = 整数 1(与 metric_table/charts/diet/sleep 同一契约)。
# 注意:cap token 用 "genui-medication-list-v1" 字符串,但**块内 v 是整数**,别混。
_VERSION = 1


def _clean(v: Any) -> Optional[str]:
    """→ 去空白的字符串,空/缺值 → None。

    None 必须先短路:str(None) == "None" 会把缺值渲染成字面 "None"(用户可见的假数据)。
    数值型字段(如 times_per_day)不经此函数 —— 本卡只透传服务端已成文的展示字符串。
    """
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _safety_alert_count(meds: list) -> int:
    """用户级用药安全告警**条数**(跨条目去重)。

    见模块 docstring:`safety_alerts` 是用户级列表, 同一份挂在每个条目上 → 直接 `sum(有 alert
    的药)` 会得到"药品数"而非"告警数"(3 味药 + 1 条 DDI → 错报成 3)。此处按 rule_id 去重,
    把重复挂载折回真实条数。若将来后端改成逐药告警, union 语义依然正确。
    非列表但 truthy 的畸形值 → 记 1(宁可多报, 绝不把真告警吞成 0 = under-alarm)。
    """
    ids: set[str] = set()
    for m in meds:
        if not isinstance(m, dict):
            continue
        raw = m.get("safety_alerts")
        if not raw:
            continue
        if not isinstance(raw, list):
            ids.add("__malformed__")
            continue
        for a in raw:
            key = (
                str(a.get("rule_id") or a.get("title") or a)[:120]
                if isinstance(a, dict) else str(a)[:120]
            )
            if key:
                ids.add(key)
    return len(ids)


def build_medication_list(meds: Any) -> Optional[dict]:
    """health_query(medication) 结果(**数组**)→ medication_list descriptor。

    非数组 / 空 / 全部无 name → None(fail-open,回退散文)。

    不截断条目数:用药清单被截断 = 用户问"我在吃什么"却少给一味药,且可能恰好漏掉带
    安全告警的那味。宁可卡片长,不可漏药。
    """
    if not isinstance(meds, list) or not meds:
        return None

    medications: list[dict] = []
    for m in meds:
        if not isinstance(m, dict):
            continue
        name = _clean(m.get("name"))
        if not name:
            continue  # 无药名的条目渲染出来毫无意义,跳过
        medications.append({
            "name": name,
            # 以下全部原样透传用户记录(R4:不解析、不换算、不补默认)。
            "dosage": _clean(m.get("dosage")),
            "frequency": _clean(m.get("frequency")),
            "timing_label": _clean(m.get("timing_label")),
            "category": _clean(m.get("category")),
            "purpose": _clean(m.get("purpose")),
            "start_date": _clean(m.get("start_date")),
            # 刻意**没有** has_safety_alert:safety_alerts 是用户级的(同一份挂到每味药),
            # 逐药标记 = 把一条 DDI 归因到无关的药 = 编造因果。见模块 docstring。
        })
    if not medications:
        return None

    data: dict[str, Any] = {
        "medications": medications,
        "total": len(medications),
        # 卡级(非逐药):该用户的用药安全告警条数, 去重后的真实条数。
        "safety_alert_count": _safety_alert_count(meds),
    }
    return {"type": MEDICATION_LIST_TYPE, "v": _VERSION, "data": data}


def render_medication_list_block(descriptor: dict) -> str:
    """descriptor → ```reva-ui fenced 文本(与 diet/sleep/table/chart 同机制)。"""
    payload = json.dumps(descriptor, ensure_ascii=False, separators=(",", ":"))
    return f"```reva-ui\n{payload}\n```"
