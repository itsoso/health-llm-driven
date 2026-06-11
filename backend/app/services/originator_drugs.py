"""原研药(原厂参考制剂)精选表 + 查询。

背景:处方常开仿制药,用户想知道对应的**原研药**(原研厂家的品牌制剂)。
原则(安全核心):**药厂/品牌是事实,绝不靠 LLM 编**。本表只收录**高把握**的常见药
原研信息;表外的药明确返回 None("暂无数据"),宁可不答不可错答。LLM 只用于把
OCR 出来的乱名规整成标准通用名(在调用方做),不参与原研事实判定。

每条:active_ingredient(通用名,小写无空格 key)→ {generic, brand, manufacturer}
alias:常见中文/英文别名 → 标准通用名 key,提高命中率。

维护:新增条目务必是**可查证**的原研信息;不确定就别加。
"""
from __future__ import annotations

from typing import Optional, TypedDict


class Originator(TypedDict):
    generic: str       # 通用名(展示用,中文)
    brand: str         # 原研药品牌名(中文)
    manufacturer: str  # 原研厂家


# key 为规范化通用名(_normalize 后)。仅高把握条目。
_TABLE: dict[str, Originator] = {
    # ── 抑酸:PPI / P-CAB ──
    "奥美拉唑": {"generic": "奥美拉唑", "brand": "洛赛克", "manufacturer": "阿斯利康 AstraZeneca"},
    "埃索美拉唑": {"generic": "埃索美拉唑", "brand": "耐信", "manufacturer": "阿斯利康 AstraZeneca"},
    "雷贝拉唑": {"generic": "雷贝拉唑", "brand": "波利特", "manufacturer": "卫材 Eisai"},
    "泮托拉唑": {"generic": "泮托拉唑", "brand": "潘妥洛克(泰美尼克)", "manufacturer": "武田 Takeda"},
    "兰索拉唑": {"generic": "兰索拉唑", "brand": "达克普隆", "manufacturer": "武田 Takeda"},
    "伏诺拉生": {"generic": "富马酸伏诺拉生", "brand": "沃克", "manufacturer": "武田 Takeda"},
    # ── 胃黏膜保护 ──
    "替普瑞酮": {"generic": "替普瑞酮", "brand": "施维舒", "manufacturer": "卫材 Eisai"},
    "瑞巴派特": {"generic": "瑞巴派特", "brand": "膜固思达", "manufacturer": "大塚 Otsuka"},
    # ── 他汀 ──
    "阿托伐他汀": {"generic": "阿托伐他汀", "brand": "立普妥", "manufacturer": "辉瑞 Pfizer"},
    "瑞舒伐他汀": {"generic": "瑞舒伐他汀", "brand": "可定", "manufacturer": "阿斯利康 AstraZeneca"},
    "辛伐他汀": {"generic": "辛伐他汀", "brand": "舒降之", "manufacturer": "默沙东 MSD"},
    # ── 降压 ──
    "氨氯地平": {"generic": "氨氯地平", "brand": "络活喜", "manufacturer": "辉瑞 Pfizer"},
    "缬沙坦": {"generic": "缬沙坦", "brand": "代文", "manufacturer": "诺华 Novartis"},
    "厄贝沙坦": {"generic": "厄贝沙坦", "brand": "安博维", "manufacturer": "赛诺菲 Sanofi"},
    # ── 降糖 ──
    "二甲双胍": {"generic": "二甲双胍", "brand": "格华止", "manufacturer": "默克 Merck(中美上海施贵宝)"},
    "西格列汀": {"generic": "西格列汀", "brand": "捷诺维", "manufacturer": "默沙东 MSD"},
}

# 别名 → 标准通用名 key。覆盖常见品牌名/英文/化学名变体。
_ALIASES: dict[str, str] = {
    # 品牌名 → 通用名
    "洛赛克": "奥美拉唑", "losec": "奥美拉唑", "omeprazole": "奥美拉唑",
    "耐信": "埃索美拉唑", "nexium": "埃索美拉唑", "esomeprazole": "埃索美拉唑",
    "波利特": "雷贝拉唑", "pariet": "雷贝拉唑", "rabeprazole": "雷贝拉唑",
    "泰美尼克": "泮托拉唑", "潘妥洛克": "泮托拉唑", "泮立苏": "泮托拉唑",
    "pantoprazole": "泮托拉唑", "泮托拉唑钠": "泮托拉唑",
    "达克普隆": "兰索拉唑", "lansoprazole": "兰索拉唑",
    "沃克": "伏诺拉生", "vonoprazan": "伏诺拉生", "takecab": "伏诺拉生",
    "富马酸伏诺拉生": "伏诺拉生", "伏诺拉生": "伏诺拉生",
    "施维舒": "替普瑞酮", "selbex": "替普瑞酮", "teprenone": "替普瑞酮",
    "膜固思达": "瑞巴派特", "rebamipide": "瑞巴派特",
    "立普妥": "阿托伐他汀", "lipitor": "阿托伐他汀", "atorvastatin": "阿托伐他汀",
    "可定": "瑞舒伐他汀", "crestor": "瑞舒伐他汀", "rosuvastatin": "瑞舒伐他汀",
    "舒降之": "辛伐他汀", "simvastatin": "辛伐他汀",
    "络活喜": "氨氯地平", "norvasc": "氨氯地平", "amlodipine": "氨氯地平", "苯磺酸氨氯地平": "氨氯地平",
    "代文": "缬沙坦", "diovan": "缬沙坦", "valsartan": "缬沙坦",
    "安博维": "厄贝沙坦", "aprovel": "厄贝沙坦", "irbesartan": "厄贝沙坦",
    "格华止": "二甲双胍", "glucophage": "二甲双胍", "metformin": "二甲双胍", "盐酸二甲双胍": "二甲双胍",
    "捷诺维": "西格列汀", "januvia": "西格列汀", "sitagliptin": "西格列汀",
}

# 规格/剂型噪声词,规范化时剥离以提高命中。
_NOISE = ["片", "胶囊", "肠溶", "缓释", "分散", "钠", "钙", "镁", "盐酸", "富马酸", "苯磺酸",
          "颗粒", "口服", "注射液", "mg", "毫克", "g", "克"]


def _normalize(name: str) -> str:
    """规范化药名:去空格/规格数字/剂型噪声/括号内容,转小写比对用。"""
    if not name:
        return ""
    s = name.strip().lower()
    # 去括号内容(商品名/规格常在括号里,单独走 alias)
    import re
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"\d+\.?\d*", "", s)  # 去数字(剂量/规格)
    s = s.replace(" ", "")
    for w in _NOISE:
        s = s.replace(w.lower(), "")
    return s


def find_originator(name: str) -> Optional[Originator]:
    """给一个药名(通用名/品牌/含规格),返回原研药信息;表外返回 None。

    匹配顺序:① 别名精确(原名 + 规范化)② 通用名表(规范化)。
    """
    if not name:
        return None
    raw = name.strip().lower().replace(" ", "")
    norm = _normalize(name)
    # 别名:先原始小写,再规范化
    for key in (raw, norm):
        if key and key in _ALIASES:
            return _TABLE.get(_ALIASES[key])
    # 直接通用名表
    if norm and norm in _TABLE:
        return _TABLE[norm]
    # 别名/通用名做包含匹配(规范化后),覆盖"泮托拉唑钠肠溶胶囊"这类
    for alias, gkey in _ALIASES.items():
        if alias and len(alias) >= 3 and alias in norm:
            return _TABLE.get(gkey)
    for gkey in _TABLE:
        if gkey in norm:
            return _TABLE[gkey]
    return None
