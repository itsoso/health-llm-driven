"""化验参考范围方向解析(纯函数,无 DB/注册副作用)。

供 Safety Guardian DSI 规则与 SupplementAdvisor 共用:flagged_abnormal 只说明"异常",
不说明方向;需要"偏低"语义的调用方必须经此判向,不可把"异常"当"偏低"。
"""
from __future__ import annotations

import re
from typing import Optional


def is_below_range(value, reference_range) -> Optional[bool]:
    """value < 参考下限 → True;> 下限/无法判向 → False;不可解析或缺值 → None。"""
    if value is None or not reference_range:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    rr = str(reference_range)
    # lo-hi:兼容多种分隔符(ASCII - ~、全角 ～－、中文 至、en/em dash);收紧数字 token 防误锚
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~～–—－至]\s*(\d+(?:\.\d+)?)", rr)
    if m:
        return v < float(m.group(1))
    # 仅下限:≥X / >X / >=X
    m2 = re.search(r"[≥>＞]\s*=?\s*(\d+(?:\.\d+)?)", rr)
    if m2:
        return v < float(m2.group(1))
    return None  # 不可解析(如 "<X"、纯文字) → 交调用方保守兜底,不静默当正常


# 分析物 → (归一化关键词, 排除词, 整名白名单正则)。只匹配 item_name。
# 排除词在原始小写名上先判(保留 "1,25" / "(oh)2" 等标点语义),防分析物混淆:
#   尿镁≠血清镁;1,25-(OH)₂D / 维生素D结合蛋白 ≠ 25-OH-D(营养状态指标)。
# 关键词在归一化名(去空格、各类连字符、括号、标点)上做子串匹配,覆盖 25-OHD / 25(OH)VD / VITAMIN_D 等。
# 裸 "mg" 太短,只接受归一化后**整名**就是镁的写法(Mg / S-Mg / Serum Mg / Mg²⁺ / RBC Mg ...),
# 以免 β2-MG(微球蛋白)、MG 抗体、Mg-ATP、单位 mg 等被当成镁。
MAGNESIUM_ANALYTE = (
    ["镁", "magnesium"],
    ["尿", "urine", "urinary", "肌酐", "creatinine", "脑脊液", "csf",
     "微球蛋白", "microglobulin", "抗体", "achr", "atp"],
    re.compile(
        r"(血清|血浆|血|serum|plasma|s|p|rbc|红细胞|总|total|ionized|离子)?"
        r"mg(2\+|\+\+|²⁺|\+2)?(离子|血清|serum|s|rbc|红细胞)?"
    ),
)
VITAMIN_D_25OH_ANALYTE = (
    ["25ohd", "25ohvd", "25羟", "25hydroxy", "vitd", "vitamind", "维生素d", "维d",
     "骨化二醇", "calcidiol"],
    ["1,25", "1，25", "1-25", "1 25", "1.25", "1α", "1a,25", "24,25", "二羟", "dihydroxy", "(oh)2", "结合蛋白", "binding"],
    None,
)

_NAME_NOISE = re.compile(r"[\s\-_()\[\].,，（）【】‐‑‒–—－]")


def matches_analyte(item_name, analyte) -> bool:
    keywords, excludes, whole_name_re = analyte
    raw = (item_name or "").strip().lower()
    if not raw or any(ex in raw for ex in excludes):
        return False
    norm = _NAME_NOISE.sub("", raw)
    if any(k in norm for k in keywords):
        return True
    return bool(whole_name_re and whole_name_re.fullmatch(norm))
