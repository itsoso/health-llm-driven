"""体检套餐和检测项目定义

用于标准化体检项目的分类和识别
"""
import re
from typing import Any, Dict, List, Optional, Tuple

# ========== 体检套餐定义 ==========
EXAM_PACKAGES: Dict[str, Dict[str, Any]] = {
    # 生化全套
    "biochemistry_full": {
        "name": "肝肾脂糖电解质测定",
        "aliases": ["生化全套", "肝功肾功", "生化常规", "肝肾功能"],
        "description": "包含肝功能、肾功能、血脂、血糖、电解质全套检测",
        "items": [
            "liver_alt", "liver_ast", "liver_ggt", "liver_tbil", "liver_alb",
            "kidney_crea", "kidney_bun", "kidney_ua",
            "lipid_tc", "lipid_tg", "lipid_hdl", "lipid_ldl",
            "glucose_fasting",
            "electrolyte_k", "electrolyte_na", "electrolyte_cl", "electrolyte_ca"
        ],
    },
    # 糖化血红蛋白
    "hba1c_test": {
        "name": "糖化血红蛋白测定",
        "aliases": ["HbA1c", "糖化血红蛋白", "糖化", "GHb"],
        "description": "反映近2-3个月血糖控制水平",
        "items": ["glucose_hba1c"],
    },
    # 粪便检查
    "stool_full": {
        "name": "粪便检查（常规+OB）",
        "aliases": ["大便常规", "粪便常规", "大便OB", "粪便隐血", "大便隐血"],
        "description": "粪便常规+隐血检测",
        "items": ["stool_routine", "stool_occult"],
    },
    # 载脂蛋白检测
    "apolipoprotein": {
        "name": "血清载脂蛋白测定",
        "aliases": ["载脂蛋白", "ApoA", "ApoB", "载脂蛋白A1", "载脂蛋白B"],
        "description": "载脂蛋白A1 + 载脂蛋白B",
        "items": ["lipid_apoa1", "lipid_apob"],
    },
    # 心肌酶谱
    "cardiac_enzyme_panel": {
        "name": "心肌酶谱常规检查",
        "aliases": ["心肌酶谱", "心肌酶", "心酶"],
        "description": "CK、CK-MB、LDH、肌红蛋白等",
        "items": ["cardiac_ck", "cardiac_ckmb", "cardiac_ldh", "cardiac_myo"],
    },
    # 肌钙蛋白
    "troponin_i": {
        "name": "血清肌钙蛋白I测定（定量）",
        "aliases": ["肌钙蛋白I", "cTnI", "TnI", "心肌肌钙蛋白"],
        "description": "心肌损伤标志物，高敏定量检测",
        "items": ["cardiac_tnl"],
    },
    # 肿瘤标志物套餐（男性）
    "tumor_marker_male": {
        "name": "肿瘤标志物套餐（男）",
        "aliases": ["肿瘤标志物男", "男性肿标"],
        "description": "CA125+PSA+FPSA+SCC+CYFRA21-1+NSE",
        "items": ["tumor_ca125", "tumor_psa", "tumor_fpsa", "tumor_scc", "tumor_cyfra211", "tumor_nse"],
    },
    # 肿瘤标志物套餐（女性）
    "tumor_marker_female": {
        "name": "肿瘤标志物套餐（女）",
        "aliases": ["肿瘤标志物女", "女性肿标"],
        "description": "CA125+CA153+SCC+CYFRA21-1+NSE+HE4",
        "items": ["tumor_ca125", "tumor_ca153", "tumor_scc", "tumor_cyfra211", "tumor_nse", "tumor_he4"],
    },
    # 胰岛素测定
    "insulin_fasting": {
        "name": "血清胰岛素测定（空腹）",
        "aliases": ["空腹胰岛素", "胰岛素测定", "INS"],
        "description": "空腹胰岛素水平检测",
        "items": ["hormone_insulin_fasting"],
    },
    # 甲状腺功能全套
    "thyroid_full": {
        "name": "甲状腺功能全套",
        "aliases": ["甲功全套", "甲功七项", "甲状腺功能", "TT3/TT4/TSH/FT3/FT4"],
        "description": "TT3、TT4、TSH、FT3、FT4、TPOAb、TgAb",
        "items": ["thyroid_t3", "thyroid_t4", "thyroid_tsh", "thyroid_ft3", "thyroid_ft4", "thyroid_tpoab", "thyroid_tgab"],
    },
    # 维生素D
    "vitamin_d": {
        "name": "25羟维生素D测定",
        "aliases": ["维生素D", "25-OH-VD", "25羟基维生素D", "VitD"],
        "description": "评估维生素D营养状态",
        "items": ["bone_vitd"],
    },
    # 淋巴细胞亚群
    "lymphocyte_subset": {
        "name": "CD3/4/8/16/19/45/56测定",
        "aliases": ["淋巴细胞亚群", "CD系列", "淋巴亚群"],
        "description": "淋巴细胞亚群分析",
        "items": ["immune_cd3", "immune_cd4", "immune_cd8", "immune_cd16", "immune_cd19", "immune_cd45", "immune_cd56"],
    },
    # T细胞亚型分析
    "tcell_10cd": {
        "name": "免疫功能T细胞亚型分析（10CD）",
        "aliases": ["T细胞亚群", "10CD", "免疫功能分析"],
        "description": "全面T细胞亚群分析",
        "items": [
            "immune_cd3", "immune_cd4", "immune_cd8", "immune_cd4cd8",
            "immune_cd16", "immune_cd19", "immune_cd45", "immune_cd56",
            "immune_nk", "immune_bcell"
        ],
    },
}

# ========== 检测项目标准化映射 ==========
# 用于将PDF中识别的各种名称映射到标准代码
ITEM_NAME_MAPPING: Dict[str, str] = {
    # 肝肾功能
    "ALT": "ALT",
    "谷丙转氨酶": "ALT",
    "丙氨酸氨基转移酶": "ALT",
    "AST": "AST",
    "谷草转氨酶": "AST",
    "天门冬氨酸氨基转移酶": "AST",
    "GGT": "GGT",
    "γ-谷氨酰转肽酶": "GGT",
    "谷氨酰转肽酶": "GGT",
    "CHE": "CHE",
    "胆碱酯酶": "CHE",
    "TBIL": "TBIL",
    "总胆红素": "TBIL",
    "DBIL": "DBIL",
    "直接胆红素": "DBIL",
    "Cr": "CREA",
    "CREA": "CREA",
    "肌酐": "CREA",
    "血肌酐": "CREA",
    "BUN": "BUN",
    "尿素氮": "BUN",
    "UA": "UA",
    "尿酸": "UA",

    # 糖化血红蛋白 (标准 NGSP A1c)
    "糖化血红蛋白": "glucose_hba1c",
    "糖化血红蛋白测定": "glucose_hba1c",
    "糖化血红蛋白A1c": "glucose_hba1c",
    "HbA1c": "glucose_hba1c",
    "糖化": "glucose_hba1c",
    "GHb": "glucose_hba1c",
    # 总糖化血红蛋白 (HbA1, 参考 6.3–9.0%) —— 与标准 A1c 是不同指标, 必须分流,
    # 否则子串「糖化血红蛋白」会把 A1 误归 glucose_hba1c, 污染糖尿病阈值/趋势。
    "糖化血红蛋白A1": "glucose_hba1_total",
    "HbA1": "glucose_hba1_total",
    "GHbA1": "glucose_hba1_total",

    # 血红蛋白 (hemoglobin, g/L) —— 「血红蛋白」是「糖化血红蛋白」的子串,
    # 必须有独立精确映射, 否则模糊匹配 (clean_name in key) 会把它误归 glucose_hba1c。
    "血红蛋白": "hemoglobin",
    "血色素": "hemoglobin",
    "Hb": "hemoglobin",
    "HGB": "hemoglobin",
    "HB": "hemoglobin",

    # 粪便检查
    "粪便常规": "stool_routine",
    "大便常规": "stool_routine",
    "粪便隐血": "stool_occult",
    "大便隐血": "stool_occult",
    "大便OB": "stool_occult",
    "OB": "stool_occult",
    "便潜血": "stool_occult",

    # 载脂蛋白
    "载脂蛋白A": "lipid_apoa",
    "载脂蛋白A1": "lipid_apoa1",
    "载脂蛋白AⅠ": "lipid_apoa1",
    "ApoA1": "lipid_apoa1",
    "Apo-A1": "lipid_apoa1",
    "载脂蛋白B": "lipid_apob",
    "ApoB": "lipid_apob",
    "Apo-B": "lipid_apob",

    # 心肌酶谱
    "肌酸激酶": "cardiac_ck",
    "CK": "cardiac_ck",
    "肌酸激酶同工酶": "cardiac_ckmb",
    "CK-MB": "cardiac_ckmb",
    "CKMB": "cardiac_ckmb",
    "乳酸脱氢酶": "cardiac_ldh",
    "LDH": "cardiac_ldh",
    "肌红蛋白": "cardiac_myo",
    "Myo": "cardiac_myo",
    "MYO": "cardiac_myo",

    # 肌钙蛋白
    "肌钙蛋白I": "cardiac_tnl",
    "cTnI": "cardiac_tnl",
    "TnI": "cardiac_tnl",
    "肌钙蛋白T": "cardiac_tnt",
    "cTnT": "cardiac_tnt",
    "TnT": "cardiac_tnt",
    "高敏肌钙蛋白": "cardiac_tnl",

    # 肿瘤标志物
    "CA125": "tumor_ca125",
    "CA-125": "tumor_ca125",
    "糖类抗原125": "tumor_ca125",
    "PSA": "tumor_psa",
    "前列腺特异抗原": "tumor_psa",
    "FPSA": "tumor_fpsa",
    "游离PSA": "tumor_fpsa",
    "f-PSA": "tumor_fpsa",
    "SCC": "tumor_scc",
    "鳞状细胞癌抗原": "tumor_scc",
    "CYFRA21-1": "tumor_cyfra211",
    "CYFRA 21-1": "tumor_cyfra211",
    "细胞角蛋白19片段": "tumor_cyfra211",
    "NSE": "tumor_nse",
    "神经元特异性烯醇化酶": "tumor_nse",
    "CA153": "tumor_ca153",
    "CA15-3": "tumor_ca153",
    "CA-153": "tumor_ca153",
    "HE4": "tumor_he4",
    "人附睾蛋白4": "tumor_he4",

    # 胰岛素
    "空腹胰岛素": "hormone_insulin_fasting",
    "胰岛素(空腹)": "hormone_insulin_fasting",
    "INS": "hormone_insulin_fasting",
    "餐后胰岛素": "hormone_insulin_postprandial",
    "C肽": "hormone_cpeptide",
    "C-肽": "hormone_cpeptide",

    # 甲状腺功能
    "TSH": "thyroid_tsh",
    "促甲状腺激素": "thyroid_tsh",
    "FT3": "thyroid_ft3",
    "游离T3": "thyroid_ft3",
    "FT4": "thyroid_ft4",
    "游离T4": "thyroid_ft4",
    "TT3": "thyroid_t3",
    "总T3": "thyroid_t3",
    "TT4": "thyroid_t4",
    "总T4": "thyroid_t4",
    "TPOAb": "thyroid_tpoab",
    "甲状腺过氧化物酶抗体": "thyroid_tpoab",
    "抗TPO抗体": "thyroid_tpoab",
    "TgAb": "thyroid_tgab",
    "甲状腺球蛋白抗体": "thyroid_tgab",
    "抗Tg抗体": "thyroid_tgab",

    # 维生素D
    "25羟维生素D": "bone_vitd",
    "25-OH-VD": "bone_vitd",
    "25-羟基维生素D": "bone_vitd",
    "维生素D": "bone_vitd",
    "VitD": "bone_vitd",

    # 淋巴细胞亚群
    "CD3+T细胞": "immune_cd3",
    "CD3": "immune_cd3",
    "CD3+": "immune_cd3",
    "CD4+T细胞": "immune_cd4",
    "CD4": "immune_cd4",
    "CD4+": "immune_cd4",
    "CD8+T细胞": "immune_cd8",
    "CD8": "immune_cd8",
    "CD8+": "immune_cd8",
    "CD4/CD8": "immune_cd4cd8",
    "CD4/CD8比值": "immune_cd4cd8",
    "CD16": "immune_cd16",
    "CD16+": "immune_cd16",
    "CD19": "immune_cd19",
    "CD19+": "immune_cd19",
    "CD19+B细胞": "immune_cd19",
    "CD45": "immune_cd45",
    "CD45+": "immune_cd45",
    "CD56": "immune_cd56",
    "CD56+": "immune_cd56",
    "CD56+NK细胞": "immune_cd56",
    "NK细胞": "immune_nk",
    "CD16+CD56+": "immune_nk",
    "B淋巴细胞": "immune_bcell",
}

# ========== 检测项目标准名称 ==========
ITEM_LABELS: Dict[str, str] = {
    # 肝肾功能
    "ALT": "谷丙转氨酶",
    "AST": "谷草转氨酶",
    "GGT": "谷氨酰转肽酶",
    "CHE": "胆碱酯酶",
    "TBIL": "总胆红素",
    "DBIL": "直接胆红素",
    "CREA": "肌酐",
    "BUN": "尿素氮",
    "UA": "尿酸",

    # 血糖相关
    "glucose_hba1c": "糖化血红蛋白",
    "glucose_hba1_total": "糖化血红蛋白A1",
    "hemoglobin": "血红蛋白",
    "glucose_fasting": "空腹血糖",
    "glucose_postprandial": "餐后血糖",
    "glucose_ga": "糖化白蛋白",

    # 粪便
    "stool_routine": "粪便常规",
    "stool_occult": "粪便隐血(OB)",

    # 载脂蛋白
    "lipid_apoa": "载脂蛋白A",
    "lipid_apoa1": "载脂蛋白A1",
    "lipid_apob": "载脂蛋白B",

    # 心肌酶谱
    "cardiac_ck": "肌酸激酶(CK)",
    "cardiac_ckmb": "肌酸激酶同工酶(CK-MB)",
    "cardiac_ldh": "乳酸脱氢酶(LDH)",
    "cardiac_myo": "肌红蛋白(Myo)",
    "cardiac_tnl": "肌钙蛋白I(cTnI)",
    "cardiac_tnt": "肌钙蛋白T(cTnT)",

    # 肿瘤标志物
    "tumor_ca125": "CA125",
    "tumor_psa": "前列腺特异抗原(PSA)",
    "tumor_fpsa": "游离PSA(fPSA)",
    "tumor_scc": "鳞状细胞癌抗原(SCC)",
    "tumor_cyfra211": "CYFRA21-1",
    "tumor_nse": "神经元特异性烯醇化酶(NSE)",
    "tumor_ca153": "CA15-3",
    "tumor_he4": "HE4",

    # 胰岛素
    "hormone_insulin_fasting": "空腹胰岛素",
    "hormone_insulin_postprandial": "餐后胰岛素",
    "hormone_cpeptide": "C肽",
    "hormone_homa_ir": "HOMA-IR指数",

    # 甲状腺功能
    "thyroid_tsh": "促甲状腺激素(TSH)",
    "thyroid_ft3": "游离T3(FT3)",
    "thyroid_ft4": "游离T4(FT4)",
    "thyroid_t3": "总T3(TT3)",
    "thyroid_t4": "总T4(TT4)",
    "thyroid_tpoab": "甲状腺过氧化物酶抗体(TPOAb)",
    "thyroid_tgab": "甲状腺球蛋白抗体(TgAb)",

    # 维生素D
    "bone_vitd": "25羟维生素D",

    # 免疫功能
    "immune_cd3": "CD3+T细胞",
    "immune_cd4": "CD4+T细胞",
    "immune_cd8": "CD8+T细胞",
    "immune_cd4cd8": "CD4/CD8比值",
    "immune_cd16": "CD16+细胞",
    "immune_cd19": "CD19+B细胞",
    "immune_cd45": "CD45+细胞",
    "immune_cd56": "CD56+NK细胞",
    "immune_nk": "NK细胞",
    "immune_bcell": "B淋巴细胞",
}


def normalize_item_name(name: str) -> tuple[str, str]:
    """
    标准化检测项目名称

    Args:
        name: 原始项目名称

    Returns:
        (标准代码, 标准名称)
    """
    # 清理名称
    clean_name = name.strip()

    # 尝试直接匹配
    if clean_name in ITEM_NAME_MAPPING:
        code = ITEM_NAME_MAPPING[clean_name]
        label = ITEM_LABELS.get(code, clean_name)
        return code, label

    # 尝试模糊匹配（包含关系）—— 取最长匹配 key, 避免短别名抢走更具体的项
    # (例: 「糖化血红蛋白A1」必须命中 A1 总糖化, 而非更短子串「糖化血红蛋白」标准 A1c)。
    best_key: str = ""
    best_code: str = ""
    for key, code in ITEM_NAME_MAPPING.items():
        if (key in clean_name or clean_name in key) and len(key) > len(best_key):
            best_key, best_code = key, code
    if best_code:
        label = ITEM_LABELS.get(best_code, clean_name)
        return best_code, label

    # 无法匹配，返回原始名称
    return "", clean_name


def get_package_items(package_key: str) -> List[Dict[str, str]]:
    """
    获取套餐中的所有项目

    Args:
        package_key: 套餐代码

    Returns:
        项目列表，每个项目包含 code 和 name
    """
    if package_key not in EXAM_PACKAGES:
        return []

    package = EXAM_PACKAGES[package_key]
    items = []

    for item_code in package["items"]:
        item_name = ITEM_LABELS.get(item_code, item_code)
        items.append({
            "code": item_code,
            "name": item_name,
        })

    return items


# ========== 指标统一化工具函数 ==========

_ABNORMAL_LABELS = frozenset({
    "true", "yes", "1", "异常", "偏高", "偏低",
    "高", "低", "阳性", "abnormal", "high", "low",
})

_RANGE_RE = re.compile(
    r"^\s*([<>≤≥]?)\s*([\d.]+)\s*(?:[-~～—–]\s*([\d.]+))?\s*",
)


def parse_reference_range(range_str: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    if not range_str:
        return None, None
    m = _RANGE_RE.match(range_str)
    if not m:
        return None, None
    op, first, second = m.group(1), m.group(2), m.group(3)
    try:
        v1 = float(first)
    except (ValueError, TypeError):
        return None, None
    if second is not None:
        try:
            return v1, float(second)
        except (ValueError, TypeError):
            return v1, None
    if op in ("<", "≤"):
        return None, v1
    if op in (">", "≥"):
        return v1, None
    return None, None


def abnormal_str_to_bool(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.strip().lower() in _ABNORMAL_LABELS


def create_indicator_from_item(
    user_id: int,
    exam_id: Optional[int],
    record_date,
    item_dict: dict,
    source: str = "manual",
):
    from app.models.family_health import MedicalIndicator

    raw_name = item_dict.get("item_name") or item_dict.get("name") or ""
    item_code_hint = str(item_dict.get("item_code") or "").strip()
    if item_code_hint:
        code = ITEM_NAME_MAPPING.get(item_code_hint, item_code_hint)
        standard_name = ITEM_LABELS.get(code, raw_name)
    else:
        code, standard_name = normalize_item_name(raw_name)

    raw_value = item_dict.get("value")
    numeric_value = None
    if raw_value is not None:
        try:
            numeric_value = float(raw_value)
        except (ValueError, TypeError):
            pass

    ref_low = item_dict.get("reference_low")
    ref_high = item_dict.get("reference_high")
    raw_range = item_dict.get("reference_range")
    if ref_low is None and ref_high is None and raw_range:
        ref_low, ref_high = parse_reference_range(raw_range)

    is_ab_raw = item_dict.get("is_abnormal")
    if isinstance(is_ab_raw, bool):
        is_ab = is_ab_raw
    else:
        is_ab = abnormal_str_to_bool(str(is_ab_raw) if is_ab_raw is not None else "")

    severity = item_dict.get("severity")
    if not severity and is_ab:
        flag = str(is_ab_raw or "").strip().lower()
        if flag in ("偏高", "偏低", "high", "low", "高", "低"):
            severity = "mild"
        else:
            severity = "moderate"

    return MedicalIndicator(
        user_id=user_id,
        exam_id=exam_id,
        name=standard_name or raw_name,
        name_en=code if code else None,
        item_code=code if code else None,
        category=item_dict.get("category"),
        value=numeric_value,
        value_text=item_dict.get("value_text"),
        unit=item_dict.get("unit"),
        reference_low=ref_low,
        reference_high=ref_high,
        reference_range=raw_range,
        is_abnormal=is_ab,
        severity=severity or "normal",
        result=item_dict.get("result"),
        notes=item_dict.get("notes"),
        source=source,
        record_date=record_date,
    )


def identify_package(items: List[str]) -> List[str]:
    """
    根据项目列表识别可能的套餐

    Args:
        items: 项目代码列表

    Returns:
        匹配的套餐代码列表
    """
    matched_packages = []
    item_set = set(items)

    for pkg_key, pkg_info in EXAM_PACKAGES.items():
        pkg_items = set(pkg_info["items"])
        # 如果套餐中的项目有50%以上在列表中，认为匹配
        overlap = len(pkg_items & item_set)
        if overlap >= len(pkg_items) * 0.5:
            matched_packages.append(pkg_key)

    return matched_packages
