"""血压分级 + 读路径急症提示 —— 单一事实源。

分级函数是全仓库唯一权威(api/blood_pressure.py 转发、models/blood_pressure.py
property 委托、voice_command_service 复用),避免三份内联副本各自漂移。

急症阈值与 Safety Guardian ``vitals.bp_hypertensive_crisis`` 同源(收缩压 ≥180
或舒张压 ≥120,2017 ACC/AHA),不新造数值;该规则改阈值时这里必须同步
(test_blood_pressure 有同源断言钉死)。
"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional

# 与 agents/safety_guardian/rules/vitals.py bp_hypertensive_crisis 同源。
BP_CRISIS_SYSTOLIC = 180
BP_CRISIS_DIASTOLIC = 120
BP_CRISIS_CATEGORY = "高血压急症"

# 与 agent_executor.SAFETY_WARNING_MARKER 同源(test 里有 drift 断言钉死)。
# 读路径追加此前缀后, query_readouts 不变量 3 自动禁用确定性短路 → 强模型作答。
SAFETY_WARNING_MARKER = "\n\n⚠️ 安全提示:"


def classify_blood_pressure(systolic: int, diastolic: int) -> str:
    """血压分类 —— 收缩压/舒张压各自定档,取较高档(under-alarm 修复)。

    旧实现 elif 链用 ``or`` 会让单侧高值被另一侧拉低(190/85 → "高血压前期"),
    且 ≥180/120 折叠进"高血压3级"丢失急症的立即就医语义。本版全部输入分档
    只升不降(TIGHTEN-only, test_blood_pressure 逐例锁死)。
    """
    if systolic >= BP_CRISIS_SYSTOLIC or diastolic >= BP_CRISIS_DIASTOLIC:
        return BP_CRISIS_CATEGORY
    if diastolic >= 110:  # 收缩压 ≥180 已被急症档吸收, 3级仅余舒张压 110-119 路径
        return "高血压3级"
    if systolic >= 160 or diastolic >= 100:
        return "高血压2级"
    if systolic >= 140 or diastolic >= 90:
        return "高血压1级"
    if systolic >= 130 or diastolic >= 80:
        return "高血压前期"
    if systolic >= 120:
        return "正常偏高"
    return "正常"


# ── 读路径确定性急症提示(agent_executor._exec_health_query 血压维度出口) ──


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        m = re.search(r"-?\d+", value)
        if m:
            return int(m.group())
    return None


def _parse_records(result: str) -> Optional[List[dict]]:
    """尽力从 tool result 文本解析出血压记录 dict 列表;解析不出 → None。

    与 query_readouts._parse_json_result 同策略: 严格 loads 优先, 失败从首个
    ``[``/``{`` raw_decode(救 _api_get 的"仅显示前N条"尾注), 只认合法前缀。

    形状泛化: 递归收集含 systolic+diastolic 键的 dict(带深度帽), 同时覆盖
    health_query 的记录数组、query_lab_indicators 单指标 ``{items:[...]}`` 与
    批量 ``{by_name:{名:{items:[...]}}}`` 三种真实形状(及未来嵌套变体)。
    """
    s = (result or "").strip()
    if not s or s.startswith("Error"):
        return None
    payload: Any = None
    try:
        payload = json.loads(s)
    except json.JSONDecodeError:
        starts = [i for i in (s.find("["), s.find("{")) if i != -1]
        if starts:
            try:
                payload, _ = json.JSONDecoder().raw_decode(s[min(starts):])
            except json.JSONDecodeError:
                return None
    if payload is None:
        return None

    found: List[dict] = []

    def _walk(node: Any, depth: int) -> None:
        if depth > 5:
            return
        if isinstance(node, dict):
            if "systolic" in node and "diastolic" in node:
                found.append(node)  # 记录本体, 不再深入 (components 子项无这对键)
                return
            for v in node.values():
                _walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                _walk(v, depth + 1)

    _walk(payload, 0)
    if not isinstance(payload, (list, dict)):
        return None  # 标量 JSON: 无结构可扫 → 退化到调用方的分级词扫描
    return found  # 可能为空 = 结构合法但无血压记录 → 无需提示


def is_crisis_record(record: dict) -> bool:
    """双判 fail-closed: 原始数字过阈值, 或服务端分级字段已是急症。"""
    sys_bp = _as_int(record.get("systolic"))
    dia_bp = _as_int(record.get("diastolic"))
    if (sys_bp is not None and sys_bp >= BP_CRISIS_SYSTOLIC) or (
        dia_bp is not None and dia_bp >= BP_CRISIS_DIASTOLIC
    ):
        return True
    return str(record.get("category") or "").strip() == BP_CRISIS_CATEGORY


def append_bp_crisis_read_warning(result: str) -> str:
    """血压**读查询**结果含急症级读数 → 追加确定性 ``⚠️ 安全提示`` 后缀。

    补的是 under-alarm 缺口: evaluate_safety 只挂在 health_record 写路径后,
    用户查「看看我的血压」时库里躺着 185/122 也不会有任何告警。本函数零 LLM、
    零 Twin 构建(纯文本/JSON 扫描), 不拖慢正常查询回合;命中后 query_readouts
    不变量 3 令确定性短路失效, 提示文本必然进入强模型答案。

    fail-closed 细节:
      - JSON 解析失败但文本中出现急症分级词 → 仍追加(泛化措辞, 不引数字)。
      - 已带安全提示后缀(未来写路径复用等) → 不重复追加(加层不减层, 原文不动)。
      - 措辞与 Safety Guardian bp_hypertensive_crisis 的 action 同向: 复测 + 急症症状即就医。
    """
    if not result or SAFETY_WARNING_MARKER in result:
        return result

    records = _parse_records(result)
    if records is None:
        # 解析不出结构, 退化为分级词扫描(under-alarm 方向宁多勿漏; "Error" 前缀
        # 已在 _parse_records 内排除, 但其召回为 None 会落到这里, 故再挡一次)。
        s = (result or "").strip()
        if not s.startswith("Error") and BP_CRISIS_CATEGORY in result:
            return result + (
                f"{SAFETY_WARNING_MARKER} 查询结果中存在达到高血压急症"
                f"(收缩压≥{BP_CRISIS_SYSTOLIC} 或舒张压≥{BP_CRISIS_DIASTOLIC} mmHg)的读数。"
                "若为近期测量, 请平静休息后复测;复测仍高或伴胸痛、剧烈头痛、视物模糊、"
                "意识改变时, 请立即就医或拨打急救电话。"
            )
        return result

    crisis = [r for r in records if is_crisis_record(r)]
    if not crisis:
        return result

    top = crisis[0]  # 记录按日期倒序, 首条命中即最近一次急症读数
    sys_bp = _as_int(top.get("systolic"))
    dia_bp = _as_int(top.get("diastolic"))
    when = str(top.get("record_date") or top.get("measured_at") or "").strip()
    when_part = f"({when})" if when else ""
    if sys_bp is not None and dia_bp is not None:
        lead = (
            f"查询结果中最近一次达到高血压急症水平的血压为 {sys_bp}/{dia_bp} mmHg"
            f"{when_part}, 已达急症阈值"
        )
    else:
        # 数字缺失但分级字段已是急症 (category-only 记录) → 不引数字, 只述事实
        lead = f"查询结果中存在达到高血压急症水平的血压记录{when_part}, 已达急症阈值"
    return result + (
        f"{SAFETY_WARNING_MARKER} {lead}(收缩压≥{BP_CRISIS_SYSTOLIC} 或舒张压≥"
        f"{BP_CRISIS_DIASTOLIC} mmHg)。若为近期测量, 请平静休息后复测;复测仍高或伴"
        "胸痛、剧烈头痛、视物模糊、意识改变时, 请立即就医或拨打急救电话。"
    )
