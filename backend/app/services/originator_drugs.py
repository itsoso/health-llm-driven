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

from collections.abc import Mapping
from types import MappingProxyType
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
    "阿卡波糖": {"generic": "阿卡波糖", "brand": "拜唐苹", "manufacturer": "拜耳 Bayer"},
    "格列美脲": {"generic": "格列美脲", "brand": "亚莫利", "manufacturer": "赛诺菲 Sanofi"},
    "达格列净": {"generic": "达格列净", "brand": "安达唐", "manufacturer": "阿斯利康 AstraZeneca"},
    "恩格列净": {"generic": "恩格列净", "brand": "欧唐静", "manufacturer": "勃林格殷格翰 Boehringer Ingelheim"},
    "利拉鲁肽": {"generic": "利拉鲁肽", "brand": "诺和力", "manufacturer": "诺和诺德 Novo Nordisk"},
    "司美格鲁肽": {"generic": "司美格鲁肽", "brand": "诺和泰(注射)", "manufacturer": "诺和诺德 Novo Nordisk"},
    "替尔泊肽": {"generic": "替尔泊肽", "brand": "穆峰达", "manufacturer": "礼来 Eli Lilly"},
    # ── 降压(续) ──
    "美托洛尔": {"generic": "美托洛尔", "brand": "倍他乐克", "manufacturer": "阿斯利康 AstraZeneca"},
    "硝苯地平": {"generic": "硝苯地平(控释)", "brand": "拜新同", "manufacturer": "拜耳 Bayer"},
    "培哚普利": {"generic": "培哚普利", "brand": "雅施达", "manufacturer": "施维雅 Servier"},
    "贝那普利": {"generic": "贝那普利", "brand": "洛汀新", "manufacturer": "诺华 Novartis"},
    "氯沙坦": {"generic": "氯沙坦", "brand": "科素亚", "manufacturer": "默沙东 MSD"},
    "替米沙坦": {"generic": "替米沙坦", "brand": "美卡素", "manufacturer": "勃林格殷格翰 Boehringer Ingelheim"},
    # ── 心血管其他 ──
    "氯吡格雷": {"generic": "氯吡格雷", "brand": "波立维", "manufacturer": "赛诺菲 Sanofi"},
    "阿司匹林": {"generic": "阿司匹林(肠溶)", "brand": "拜阿司匹灵", "manufacturer": "拜耳 Bayer"},
    "依折麦布": {"generic": "依折麦布", "brand": "益适纯", "manufacturer": "默沙东 MSD"},
    # ── 消化(续) ──
    "伊托必利": {"generic": "盐酸伊托必利", "brand": "加斯清", "manufacturer": "雅培 Abbott"},
    "多潘立酮": {"generic": "多潘立酮", "brand": "吗丁啉", "manufacturer": "西安杨森(强生 J&J)"},
    "铝碳酸镁": {"generic": "铝碳酸镁", "brand": "达喜", "manufacturer": "拜耳 Bayer"},
    # ── 过敏 / 鼻炎 / 呼吸 ──
    "氯雷他定": {"generic": "氯雷他定", "brand": "开瑞坦", "manufacturer": "拜耳 Bayer(原先灵葆雅)"},
    "西替利嗪": {"generic": "盐酸西替利嗪", "brand": "仙特明", "manufacturer": "UCB"},
    "地氯雷他定": {"generic": "地氯雷他定", "brand": "恩理思", "manufacturer": "默沙东 MSD(原先灵葆雅)"},
    "孟鲁司特": {"generic": "孟鲁司特钠", "brand": "顺尔宁", "manufacturer": "默沙东 MSD"},
    "糠酸莫米松": {"generic": "糠酸莫米松鼻喷雾剂", "brand": "内舒拿", "manufacturer": "默沙东 MSD(原先灵葆雅)"},
    "布地奈德": {"generic": "布地奈德", "brand": "普米克", "manufacturer": "阿斯利康 AstraZeneca"},
    # ── 抗感染 ──
    "阿奇霉素": {"generic": "阿奇霉素", "brand": "希舒美", "manufacturer": "辉瑞 Pfizer"},
    "头孢呋辛酯": {"generic": "头孢呋辛酯", "brand": "西力欣", "manufacturer": "葛兰素史克 GSK"},
    "左氧氟沙星": {"generic": "左氧氟沙星", "brand": "可乐必妥", "manufacturer": "第一三共 Daiichi Sankyo"},
    "莫西沙星": {"generic": "莫西沙星", "brand": "拜复乐", "manufacturer": "拜耳 Bayer"},
    # ── 其他常用 ──
    "塞来昔布": {"generic": "塞来昔布", "brand": "西乐葆", "manufacturer": "辉瑞 Pfizer"},
    "非布司他": {"generic": "非布司他", "brand": "菲布力", "manufacturer": "帝人 Teijin"},
    "左甲状腺素": {"generic": "左甲状腺素钠", "brand": "优甲乐", "manufacturer": "默克 Merck"},
    "氟西汀": {"generic": "氟西汀", "brand": "百忧解", "manufacturer": "礼来 Eli Lilly"},
    "舍曲林": {"generic": "舍曲林", "brand": "左洛复", "manufacturer": "辉瑞 Pfizer"},
    "艾司西酞普兰": {"generic": "艾司西酞普兰", "brand": "来士普", "manufacturer": "灵北 Lundbeck"},
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
    # 降糖(续)
    "拜唐苹": "阿卡波糖", "glucobay": "阿卡波糖", "acarbose": "阿卡波糖",
    "亚莫利": "格列美脲", "amaryl": "格列美脲", "glimepiride": "格列美脲",
    "安达唐": "达格列净", "forxiga": "达格列净", "dapagliflozin": "达格列净",
    "欧唐静": "恩格列净", "jardiance": "恩格列净", "empagliflozin": "恩格列净",
    "诺和力": "利拉鲁肽", "victoza": "利拉鲁肽", "liraglutide": "利拉鲁肽",
    "诺和泰": "司美格鲁肽", "ozempic": "司美格鲁肽", "semaglutide": "司美格鲁肽",
    "穆峰达": "替尔泊肽", "mounjaro": "替尔泊肽", "tirzepatide": "替尔泊肽",
    # 降压(续)/心血管
    "倍他乐克": "美托洛尔", "betaloc": "美托洛尔", "metoprolol": "美托洛尔",
    "拜新同": "硝苯地平", "adalat": "硝苯地平", "nifedipine": "硝苯地平",
    "雅施达": "培哚普利", "perindopril": "培哚普利",
    "洛汀新": "贝那普利", "lotensin": "贝那普利", "benazepril": "贝那普利",
    "科素亚": "氯沙坦", "cozaar": "氯沙坦", "losartan": "氯沙坦",
    "美卡素": "替米沙坦", "micardis": "替米沙坦", "telmisartan": "替米沙坦",
    "波立维": "氯吡格雷", "plavix": "氯吡格雷", "clopidogrel": "氯吡格雷", "硫酸氢氯吡格雷": "氯吡格雷",
    "拜阿司匹灵": "阿司匹林", "aspirin": "阿司匹林",
    "益适纯": "依折麦布", "ezetrol": "依折麦布", "ezetimibe": "依折麦布",
    # 消化(续)
    "加斯清": "伊托必利", "itopride": "伊托必利", "谐畅动力": "伊托必利",
    "吗丁啉": "多潘立酮", "motilium": "多潘立酮", "domperidone": "多潘立酮",
    "达喜": "铝碳酸镁", "talcid": "铝碳酸镁",
    # 过敏/鼻炎/呼吸
    "开瑞坦": "氯雷他定", "claritin": "氯雷他定", "loratadine": "氯雷他定",
    "仙特明": "西替利嗪", "zyrtec": "西替利嗪", "cetirizine": "西替利嗪",
    "恩理思": "地氯雷他定", "aerius": "地氯雷他定", "desloratadine": "地氯雷他定",
    "顺尔宁": "孟鲁司特", "singulair": "孟鲁司特", "montelukast": "孟鲁司特",
    "内舒拿": "糠酸莫米松", "nasonex": "糠酸莫米松", "莫米松": "糠酸莫米松",
    "普米克": "布地奈德", "pulmicort": "布地奈德", "budesonide": "布地奈德",
    # 抗感染
    "希舒美": "阿奇霉素", "zithromax": "阿奇霉素", "azithromycin": "阿奇霉素",
    "西力欣": "头孢呋辛酯", "zinnat": "头孢呋辛酯", "cefuroxime": "头孢呋辛酯",
    "可乐必妥": "左氧氟沙星", "cravit": "左氧氟沙星", "levofloxacin": "左氧氟沙星",
    "拜复乐": "莫西沙星", "avelox": "莫西沙星", "moxifloxacin": "莫西沙星",
    # 其他
    "西乐葆": "塞来昔布", "celebrex": "塞来昔布", "celecoxib": "塞来昔布",
    "菲布力": "非布司他", "feburic": "非布司他", "febuxostat": "非布司他",
    "优甲乐": "左甲状腺素", "euthyrox": "左甲状腺素", "levothyroxine": "左甲状腺素",
    "百忧解": "氟西汀", "prozac": "氟西汀", "fluoxetine": "氟西汀",
    "左洛复": "舍曲林", "zoloft": "舍曲林", "sertraline": "舍曲林",
    "来士普": "艾司西酞普兰", "lexapro": "艾司西酞普兰", "escitalopram": "艾司西酞普兰",
}


def medication_aliases() -> Mapping[str, str]:
    """返回不可变的药名/品牌别名 → 规范通用名映射。"""
    aliases = {generic: generic for generic in _TABLE}
    # The display generic is what imported/user-created medication definitions
    # often store (e.g. 盐酸伊托必利), while the compact table key is the
    # canonical identity (伊托必利). Both exact forms must resolve to one drug.
    aliases.update({entry["generic"].strip().lower(): key for key, entry in _TABLE.items()})
    aliases.update(_ALIASES)
    return MappingProxyType(aliases)

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
