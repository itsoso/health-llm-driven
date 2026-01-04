"""体检套餐和检测项目定义

用于标准化体检项目的分类和识别
"""
from typing import Dict, List, Any

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
    # 糖化血红蛋白
    "糖化血红蛋白": "glucose_hba1c",
    "糖化血红蛋白测定": "glucose_hba1c",
    "HbA1c": "glucose_hba1c",
    "糖化": "glucose_hba1c",
    "GHb": "glucose_hba1c",
    
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
    # 血糖相关
    "glucose_hba1c": "糖化血红蛋白",
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
    
    # 尝试模糊匹配（包含关系）
    for key, code in ITEM_NAME_MAPPING.items():
        if key in clean_name or clean_name in key:
            label = ITEM_LABELS.get(code, clean_name)
            return code, label
    
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

