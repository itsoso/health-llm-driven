"""基因数据 API — 基因检测档案 + 变异位点管理 + 交叉分析"""
import logging
from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from app.models.user import User
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.api.deps import get_current_user_required

logger = logging.getLogger(__name__)

router = APIRouter()


# ══════════════════════════════════════════════════════════
# Pydantic Schemas
# ══════════════════════════════════════════════════════════

class ProfileCreateRequest(BaseModel):
    test_provider: str = Field(..., max_length=100, description="检测机构（如华大基因、微基因）")
    test_date: date = Field(..., description="检测日期")
    report_id: Optional[str] = Field(None, max_length=100, description="报告编号")
    notes: Optional[str] = Field(None, description="备注")


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    test_provider: str
    test_date: date
    report_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class VariantCreateRequest(BaseModel):
    profile_id: int = Field(..., description="所属基因档案 ID")
    category: str = Field(..., max_length=50, description="分类: nutrition/exercise/drug_sensitivity/disease_risk/sleep")
    gene_name: str = Field(..., max_length=50, description="基因名称")
    variant_name: Optional[str] = Field(None, max_length=100, description="变异名称")
    genotype: Optional[str] = Field(None, max_length=50, description="基因型")
    result_label: Optional[str] = Field(None, max_length=100, description="结果标签")
    risk_level: str = Field("info", description="风险等级: low/medium/high/info")
    description: Optional[str] = Field(None, description="描述")
    health_implications: Optional[Dict[str, Any]] = Field(None, description="健康影响 JSON")


class VariantBatchCreateRequest(BaseModel):
    variants: List[VariantCreateRequest] = Field(..., min_length=1, description="变异位点列表")


class VariantUpdateRequest(BaseModel):
    category: Optional[str] = Field(None, max_length=50)
    gene_name: Optional[str] = Field(None, max_length=50)
    variant_name: Optional[str] = Field(None, max_length=100)
    genotype: Optional[str] = Field(None, max_length=50)
    result_label: Optional[str] = Field(None, max_length=100)
    risk_level: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = None
    health_implications: Optional[Dict[str, Any]] = None


class VariantResponse(BaseModel):
    id: int
    user_id: int
    profile_id: int
    category: str
    gene_name: str
    variant_name: Optional[str] = None
    genotype: Optional[str] = None
    result_label: Optional[str] = None
    risk_level: str = "info"
    description: Optional[str] = None
    health_implications: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════
# PDF 上传 + AI 自动提取
# ══════════════════════════════════════════════════════════

# 已知健康相关 SNP 字典：rsid → (category, gene, variant, genotype→label 映射)
KNOWN_SNPS = {
    # 营养代谢
    "rs1801133": {"category": "nutrition", "gene": "MTHFR", "variant": "C677T",
        "map": {"GG": ("CC", "叶酸代谢正常", "low"), "AG": ("CT", "叶酸代谢轻度减弱", "medium"), "AA": ("TT", "叶酸代谢显著减弱", "high")},
        "desc": "亚甲基四氢叶酸还原酶，影响叶酸代谢和同型半胱氨酸水平"},
    "rs762551": {"category": "nutrition", "gene": "CYP1A2", "variant": "咖啡因代谢",
        "map": {"AA": ("AA", "快速代谢", "low"), "AC": ("AC", "中等代谢", "info"), "CC": ("CC", "慢速代谢", "medium")},
        "desc": "细胞色素P450酶，影响咖啡因代谢速度"},
    "rs4988235": {"category": "nutrition", "gene": "LCT", "variant": "乳糖耐受",
        "map": {"GG": ("CC", "乳糖不耐受", "medium"), "AG": ("CT", "部分耐受", "low"), "AA": ("TT", "乳糖耐受", "low")},
        "desc": "乳糖酶基因，影响乳制品消化能力"},
    "rs671": {"category": "nutrition", "gene": "ALDH2", "variant": "酒精代谢",
        "map": {"GG": ("GG", "酒精代谢正常", "low"), "AG": ("GA", "酒精代谢减弱(易脸红)", "medium"), "AA": ("AA", "酒精代谢缺陷", "high")},
        "desc": "乙醛脱氢酶，影响酒精代谢能力"},
    "rs1544410": {"category": "nutrition", "gene": "VDR", "variant": "维生素D受体",
        "map": {"CC": ("CC", "维D需求正常", "low"), "CT": ("CT", "维D需求轻度增高", "low"), "TT": ("TT", "维D需求增高", "medium")},
        "desc": "维生素D受体基因，影响钙吸收和骨密度"},
    # 运动能力
    "rs1815739": {"category": "exercise", "gene": "ACTN3", "variant": "R577X",
        "map": {"CC": ("RR", "爆发力型", "info"), "CT": ("RX", "混合型", "info"), "TT": ("XX", "耐力型", "info")},
        "desc": "α-辅肌动蛋白3，影响快肌纤维比例"},
    "rs12722489": {"category": "exercise", "gene": "PPARGC1A", "variant": "有氧能力",
        "map": {"CC": ("CC", "有氧能力正常", "info"), "CT": ("CT", "有氧能力较好", "info"), "TT": ("TT", "有氧能力较强", "info")},
        "desc": "线粒体生物合成关键调节因子"},
    # 药物敏感
    "rs4244285": {"category": "drug_sensitivity", "gene": "CYP2C19", "variant": "氯吡格雷代谢 *2",
        "map": {"GG": ("*1/*1", "正常代谢", "low"), "AG": ("*1/*2", "中间代谢", "medium"), "AA": ("*2/*2", "慢代谢", "high")},
        "desc": "影响氯吡格雷、奥美拉唑等药物代谢"},
    "rs5030655": {"category": "drug_sensitivity", "gene": "CYP2D6", "variant": "止痛药代谢",
        "map": {"DD": ("正常", "正常代谢", "low"), "DI": ("中间", "中间代谢", "medium"), "II": ("慢", "慢代谢(需调整剂量)", "high")},
        "desc": "影响可待因、曲马多等止痛药代谢"},
    "rs4149056": {"category": "drug_sensitivity", "gene": "SLCO1B1", "variant": "他汀类药物",
        "map": {"TT": ("TT", "他汀耐受正常", "low"), "CT": ("CT", "他汀肌病风险轻度增高", "medium"), "CC": ("CC", "他汀肌病风险增高", "high")},
        "desc": "有机阴离子转运蛋白，影响他汀类药物清除"},
    "rs1265181": {"category": "drug_sensitivity", "gene": "HLA-B*5801", "variant": "别嘌醇过敏",
        "map": {"GG": ("阴性", "别嘌醇可使用", "low"), "AG": ("携带", "别嘌醇慎用", "high"), "AA": ("阳性", "别嘌醇禁用", "high")},
        "desc": "HLA基因，与别嘌醇严重过敏反应相关"},
    # 疾病风险
    "rs429358": {"category": "disease_risk", "gene": "APOE", "variant": "ε4 (rs429358)",
        "map": {"TT": ("ε3/ε3", "标准风险", "low"), "CT": ("ε3/ε4", "心血管/AD风险轻度增高", "medium"), "CC": ("ε4/ε4", "心血管/AD风险显著增高", "high")},
        "desc": "载脂蛋白E，与阿尔茨海默病和心血管疾病风险相关"},
    "rs7903146": {"category": "disease_risk", "gene": "TCF7L2", "variant": "2型糖尿病",
        "map": {"CC": ("CC", "标准风险", "low"), "CT": ("CT", "糖尿病风险轻度增高", "medium"), "TT": ("TT", "糖尿病风险增高", "high")},
        "desc": "转录因子7-like 2，与胰岛素分泌和2型糖尿病风险相关"},
    "rs9939609": {"category": "disease_risk", "gene": "FTO", "variant": "肥胖倾向",
        "map": {"TT": ("TT", "标准体重倾向", "low"), "AT": ("AT", "轻度肥胖倾向", "medium"), "AA": ("AA", "肥胖倾向增高", "high")},
        "desc": "脂肪量和肥胖相关基因"},
    # 睡眠
    "rs1801260": {"category": "sleep", "gene": "CLOCK", "variant": "昼夜节律",
        "map": {"AA": ("TT", "标准作息型", "info"), "AG": ("TC", "轻度夜猫子", "low"), "GG": ("CC", "夜猫子型", "medium")},
        "desc": "生物钟核心基因，影响昼夜节律偏好"},
    "rs2304672": {"category": "sleep", "gene": "PER2", "variant": "睡眠周期",
        "map": {"GG": ("GG", "标准睡眠周期", "info"), "CG": ("CG", "睡眠周期轻度偏移", "low"), "CC": ("CC", "睡眠周期偏移", "medium")},
        "desc": "周期蛋白2，影响睡眠-觉醒周期"},
    "rs73598374": {"category": "sleep", "gene": "ADA", "variant": "深度睡眠",
        "map": {"CC": ("GG", "深睡正常", "info"), "CT": ("GA", "深睡偏少", "medium"), "TT": ("AA", "深睡显著偏少", "high")},
        "desc": "腺苷脱氨酶，影响深度睡眠质量"},
    # ── 酒精代谢（补充）──
    "rs1229984": {"category": "nutrition", "gene": "ADH1B", "variant": "酒精代谢速度",
        "map": {"CC": ("CC", "酒精代谢较慢", "medium"), "CT": ("CT", "酒精代谢正常", "low"), "TT": ("TT", "酒精代谢较快(东亚常见)", "info")},
        "desc": "乙醇脱氢酶，快速代谢型饮酒后不适感强，反而降低酗酒风险"},
    # ── 精神/神经 ──
    "rs4680": {"category": "nutrition", "gene": "COMT", "variant": "压力/焦虑倾向(Val158Met)",
        "map": {"GG": ("Val/Val", "压力耐受较好(战士型)", "low"), "AG": ("Val/Met", "中等压力敏感", "info"), "AA": ("Met/Met", "压力敏感/焦虑倾向(忧虑型)", "medium")},
        "desc": "儿茶酚-O-甲基转移酶，影响多巴胺代谢和压力反应"},
    "rs6265": {"category": "nutrition", "gene": "BDNF", "variant": "记忆/学习(Val66Met)",
        "map": {"CC": ("Val/Val", "记忆力正常", "info"), "CT": ("Val/Met", "学习能力轻度下降", "low"), "TT": ("Met/Met", "记忆/学习能力偏弱", "medium")},
        "desc": "脑源性神经营养因子，影响神经可塑性和记忆"},
    "rs1800497": {"category": "nutrition", "gene": "DRD2", "variant": "多巴胺受体/奖赏敏感",
        "map": {"GG": ("GG", "多巴胺受体正常", "low"), "AG": ("AG", "奖赏敏感轻度增高", "low"), "AA": ("AA", "奖赏敏感增高(易成瘾倾向)", "medium")},
        "desc": "多巴胺D2受体，影响奖赏回路和成瘾敏感性"},
    # ── 疼痛/药物 ──
    "rs1799971": {"category": "drug_sensitivity", "gene": "OPRM1", "variant": "疼痛敏感/阿片类药物",
        "map": {"AA": ("AA", "疼痛敏感度正常", "low"), "AG": ("AG", "疼痛阈值偏低", "low"), "GG": ("GG", "疼痛敏感度高(阿片需更大剂量)", "medium")},
        "desc": "μ-阿片受体，影响疼痛感知和阿片类药物效果"},
    # ── 炎症/免疫 ──
    "rs1800629": {"category": "disease_risk", "gene": "TNF-α", "variant": "炎症倾向",
        "map": {"GG": ("GG", "炎症反应正常", "low"), "AG": ("AG", "炎症倾向轻度增高", "medium"), "AA": ("AA", "促炎体质", "high")},
        "desc": "肿瘤坏死因子α，影响炎症反应强度"},
    "rs1800795": {"category": "disease_risk", "gene": "IL-6", "variant": "炎症/运动恢复",
        "map": {"GG": ("GG", "炎症反应较强(恢复较慢)", "medium"), "GC": ("GC", "炎症反应中等", "low"), "CC": ("CC", "炎症反应较弱(恢复较快)", "low")},
        "desc": "白介素6，影响运动后炎症反应和恢复速度"},
    # ── 代谢/胰岛素 ──
    "rs1801282": {"category": "disease_risk", "gene": "PPARG", "variant": "胰岛素敏感/脂肪存储",
        "map": {"CC": ("Pro/Pro", "标准脂肪存储", "low"), "CG": ("Pro/Ala", "胰岛素敏感性较好", "info"), "GG": ("Ala/Ala", "胰岛素敏感性好(不易胖)", "info")},
        "desc": "过氧化物酶体增殖物激活受体γ，影响脂肪细胞分化"},
    # ── 维生素/矿物质代谢 ──
    "rs1801394": {"category": "nutrition", "gene": "MTRR", "variant": "维B12代谢",
        "map": {"AA": ("AA", "B12代谢减弱", "medium"), "AG": ("AG", "B12代谢轻度减弱", "low"), "GG": ("GG", "B12代谢正常", "low")},
        "desc": "甲硫氨酸合成酶还原酶，影响维B12利用效率"},
    "rs1805087": {"category": "nutrition", "gene": "MTR", "variant": "甲硫氨酸合成",
        "map": {"AA": ("AA", "甲硫氨酸代谢正常", "low"), "AG": ("AG", "代谢效率轻度下降", "low"), "GG": ("GG", "代谢效率下降", "medium")},
        "desc": "甲硫氨酸合成酶，与叶酸/B12代谢通路相关"},
    "rs174547": {"category": "nutrition", "gene": "FADS1", "variant": "Omega-3代谢",
        "map": {"TT": ("TT", "Omega-3转化效率高", "info"), "CT": ("CT", "转化效率中等", "info"), "CC": ("CC", "Omega-3转化效率低(需更多摄入)", "medium")},
        "desc": "脂肪酸去饱和酶1，影响Omega-3/6脂肪酸代谢"},
    "rs7041": {"category": "nutrition", "gene": "GC", "variant": "维D结合蛋白",
        "map": {"AA": ("AA", "维D水平偏低", "medium"), "AC": ("AC", "维D水平中等", "low"), "CC": ("CC", "维D水平正常", "low")},
        "desc": "维生素D结合蛋白(GC球蛋白)，影响血清维D水平"},
    "rs4654748": {"category": "nutrition", "gene": "NBPF3", "variant": "维B6需求",
        "map": {"CC": ("CC", "B6需求正常", "low"), "CT": ("CT", "B6需求轻度增高", "low"), "TT": ("TT", "B6需求增高", "medium")},
        "desc": "影响维生素B6血清水平"},
    "rs1800562": {"category": "nutrition", "gene": "HFE", "variant": "铁代谢/血色病",
        "map": {"GG": ("GG", "铁代谢正常", "low"), "GA": ("GA", "铁蓄积风险轻度增高", "medium"), "AA": ("AA", "遗传性血色病高风险", "high")},
        "desc": "HFE基因，影响铁吸收调控，纯合变异可致铁过载"},
    # ── 心血管风险 ──
    "rs5882": {"category": "disease_risk", "gene": "CETP", "variant": "HDL胆固醇",
        "map": {"GG": ("GG", "HDL水平标准", "low"), "AG": ("AG", "HDL水平偏高(心血管保护)", "info"), "AA": ("AA", "HDL水平较高", "info")},
        "desc": "胆固醇酯转运蛋白，影响HDL-C水平"},
    "rs10757274": {"category": "disease_risk", "gene": "9p21", "variant": "心血管风险(rs10757274)",
        "map": {"GG": ("GG", "标准心血管风险", "low"), "AG": ("AG", "心血管风险轻度增高", "medium"), "AA": ("AA", "心血管风险增高", "high")},
        "desc": "9p21染色体区域，与冠心病、动脉粥样硬化风险相关"},
    # ── 糖尿病（补充位点）──
    "rs10811661": {"category": "disease_risk", "gene": "CDKN2A/B", "variant": "糖尿病风险(CDKN2A)",
        "map": {"TT": ("TT", "标准风险", "low"), "CT": ("CT", "糖尿病风险轻度增高", "medium"), "CC": ("CC", "糖尿病风险增高", "high")},
        "desc": "细胞周期蛋白依赖性激酶抑制基因，影响胰岛β细胞功能"},
    "rs4402960": {"category": "disease_risk", "gene": "IGF2BP2", "variant": "糖尿病风险(IGF2BP2)",
        "map": {"GG": ("GG", "标准风险", "low"), "GT": ("GT", "糖尿病风险轻度增高", "medium"), "TT": ("TT", "糖尿病风险增高", "high")},
        "desc": "胰岛素样生长因子2 mRNA结合蛋白2"},
    # ── 癌症风险 ──
    "rs6983267": {"category": "disease_risk", "gene": "8q24", "variant": "结直肠癌风险",
        "map": {"TT": ("TT", "标准风险", "low"), "GT": ("GT", "结直肠癌风险轻度增高", "medium"), "GG": ("GG", "结直肠癌风险增高", "high")},
        "desc": "8q24染色体区域，与结直肠癌、前列腺癌风险相关"},
    "rs401681": {"category": "disease_risk", "gene": "TERT", "variant": "多种癌症风险",
        "map": {"TT": ("TT", "标准风险", "low"), "CT": ("CT", "癌症风险轻度变化", "low"), "CC": ("CC", "部分癌症风险增高", "medium")},
        "desc": "端粒酶逆转录酶，影响端粒维护和多种癌症风险"},
    # ── 皮肤 ──
    "rs1805007": {"category": "nutrition", "gene": "MC1R", "variant": "皮肤/紫外线敏感",
        "map": {"CC": ("CC", "紫外线敏感度正常", "low"), "CT": ("CT", "紫外线敏感度增高", "medium"), "TT": ("TT", "紫外线高敏感(需加强防晒)", "high")},
        "desc": "黑色素皮质素1受体，影响皮肤色素和紫外线损伤修复"},
    # ── 认知/智商 (cognition) ──
    "rs17070145": {"category": "cognition", "gene": "KIBRA", "variant": "情景记忆力(WWC1)",
        "map": {"CC": ("CC", "记忆力较强", "info"), "CT": ("CT", "记忆力中等", "info"), "TT": ("TT", "情景记忆力偏弱", "medium")},
        "desc": "WWC1/KIBRA蛋白，T等位与海马依赖的情景记忆力下降相关，可通过有氧运动和记忆训练改善"},
    "rs363050": {"category": "cognition", "gene": "SNAP25", "variant": "突触可塑性/智商",
        "map": {"GG": ("GG", "突触传递效率较高", "info"), "AG": ("AG", "突触效率中等", "info"), "AA": ("AA", "突触效率偏低", "low")},
        "desc": "突触体相关蛋白25，参与突触囊泡融合和神经递质释放，与智商评分和认知灵活性相关"},
    "rs1800544": {"category": "cognition", "gene": "ADRA2A", "variant": "注意力/ADHD风险",
        "map": {"CC": ("CC", "注意力调控正常", "low"), "CG": ("CG", "注意力波动轻度增高", "low"), "GG": ("GG", "注意力缺陷风险增高", "medium")},
        "desc": "α2A肾上腺素受体，影响前额叶去甲肾上腺素信号，G等位与ADHD和注意力波动相关"},
    "rs1044396": {"category": "cognition", "gene": "CHRNA4", "variant": "专注力/烟碱受体",
        "map": {"CC": ("CC", "专注力较强", "info"), "CT": ("CT", "专注力中等", "info"), "TT": ("TT", "专注力偏弱(对尼古丁敏感)", "medium")},
        "desc": "烟碱型乙酰胆碱受体α4亚基，影响注意力网络效率，T等位与注意力分散和尼古丁依赖风险相关"},
    "rs4570625": {"category": "cognition", "gene": "TPH2", "variant": "血清素合成/情绪稳定",
        "map": {"GG": ("GG", "血清素合成正常", "low"), "GT": ("GT", "血清素合成轻度下降", "low"), "TT": ("TT", "血清素合成偏低(情绪波动)", "medium")},
        "desc": "色氨酸羟化酶2，脑内血清素合成限速酶，T等位与情绪不稳定、焦虑和冲动性相关"},
    # ── 个性 (personality) ──
    "rs25531": {"category": "personality", "gene": "SLC6A4", "variant": "血清素转运/焦虑倾向(5-HTTLPR)",
        "map": {"AA": ("LA/LA", "血清素回收正常(情绪稳定)", "low"), "AG": ("LA/LG", "血清素回收轻度减弱", "low"), "GG": ("LG/LG", "血清素回收减弱(焦虑易感)", "medium")},
        "desc": "血清素转运体基因，短臂/LG功能等位减少血清素回收，与焦虑、抑郁易感性和对负面事件的情绪反应增强相关"},
    "rs53576": {"category": "personality", "gene": "OXTR", "variant": "催产素受体/共情能力",
        "map": {"GG": ("GG", "高共情/亲社会倾向", "info"), "AG": ("AG", "共情能力中等", "info"), "AA": ("AA", "共情偏弱/社交回避倾向", "low")},
        "desc": "催产素受体基因，GG型社交敏感度高、共情强但孤独时心理风险更高，AA型独立性强但社交直觉弱"},
    # ── 运动扩展 (exercise) ──
    "rs4646994": {"category": "exercise", "gene": "ACE", "variant": "耐力vs力量(I/D多态)",
        "map": {"II": ("II", "耐力型(ACE活性低)", "info"), "ID": ("ID", "混合型", "info"), "DD": ("DD", "力量/爆发型(ACE活性高)", "info")},
        "desc": "血管紧张素转换酶，I等位与耐力表现相关(马拉松/铁三)，D等位与力量/爆发力相关(短跑/举重)"},
    "rs12722": {"category": "exercise", "gene": "COL5A1", "variant": "肌腱韧带损伤风险",
        "map": {"TT": ("TT", "肌腱韧带弹性好(损伤风险低)", "low"), "CT": ("CT", "中等柔韧性", "low"), "CC": ("CC", "肌腱韧带较硬(运动损伤风险增高)", "medium")},
        "desc": "V型胶原蛋白α1链，CC型肌腱/韧带胶原纤维排列较密，跑步/跳跃时ACL和跟腱损伤风险增高"},
    "rs1799983": {"category": "exercise", "gene": "NOS3", "variant": "一氧化氮/血管扩张/耐力",
        "map": {"GG": ("Glu/Glu", "NO生成正常(耐力表现正常)", "low"), "GT": ("Glu/Asp", "NO生成轻度下降", "low"), "TT": ("Asp/Asp", "NO生成偏低(耐力受限/血压偏高)", "medium")},
        "desc": "内皮型一氧化氮合酶，T等位(Asp)减少NO产生，影响运动时血管扩张和氧输送效率"},
    # ── 恢复/抗氧化 (recovery) ──
    "rs4880": {"category": "recovery", "gene": "SOD2", "variant": "超氧化物歧化酶/氧化应激",
        "map": {"TT": ("Ala/Ala", "抗氧化能力强(SOD2高活性)", "info"), "CT": ("Val/Ala", "抗氧化能力中等", "low"), "CC": ("Val/Val", "抗氧化能力弱(运动后氧化应激高)", "medium")},
        "desc": "锰超氧化物歧化酶，Ala型线粒体定位效率高，清除超氧阴离子能力强；Val/Val型建议补充CoQ10/NAC/维C"},
    "rs1050450": {"category": "recovery", "gene": "GPX1", "variant": "谷胱甘肽过氧化物酶/抗氧化",
        "map": {"CC": ("Pro/Pro", "GPX1活性较低(抗氧化偏弱)", "medium"), "CT": ("Pro/Leu", "GPX1活性中等", "low"), "TT": ("Leu/Leu", "GPX1活性正常", "low")},
        "desc": "谷胱甘肽过氧化物酶1，Pro/Pro型酶活性偏低，建议补充硒(200μg/d)和NAC(600mg/d)支持谷胱甘肽系统"},
    "rs1695": {"category": "recovery", "gene": "GSTP1", "variant": "解毒酶/补剂代谢",
        "map": {"AA": ("Ile/Ile", "解毒能力正常", "low"), "AG": ("Ile/Val", "解毒能力轻度下降", "low"), "GG": ("Val/Val", "解毒能力下降(十字花科蔬菜需求增高)", "medium")},
        "desc": "谷胱甘肽S-转移酶P1，Val/Val型对环境毒素和药物代谢物的解毒效率降低，建议增加西兰花/萝卜硫素摄入"},
    # ── 睡眠扩展 (sleep) ──
    "rs5751876": {"category": "sleep", "gene": "ADORA2A", "variant": "腺苷受体/咖啡因影响睡眠",
        "map": {"CC": ("CC", "咖啡因对睡眠影响小", "low"), "CT": ("CT", "咖啡因对睡眠影响中等", "low"), "TT": ("TT", "咖啡因严重影响睡眠(中午后禁咖啡因)", "medium")},
        "desc": "腺苷A2A受体，TT型对咖啡因阻断腺苷的效应更敏感，午后摄入咖啡因显著延长入睡潜伏期"},
}


class GeneticPdfUploadRequest(BaseModel):
    test_provider: str = Field(..., description="检测机构")
    test_date: date = Field(..., description="检测日期")
    pdf_base64: str = Field(..., description="PDF 文件 base64")
    notes: Optional[str] = None


class GeneticTxtUploadRequest(BaseModel):
    test_provider: str = Field(..., description="检测机构")
    test_date: date = Field(..., description="检测日期")
    txt_content: str = Field(..., description="TXT 原始数据内容")
    notes: Optional[str] = None


@router.post("/profiles/upload-txt", summary="上传微基因/23andMe 原始 TXT 数据，自动解析健康位点")
def upload_genetic_txt(
    req: GeneticTxtUploadRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """解析 WeGene/23andMe 格式的 TXT 原始数据，匹配已知健康 SNP"""
    profile = GeneticProfile(
        user_id=current_user.id,
        test_provider=req.test_provider,
        test_date=req.test_date,
        notes=req.notes or "TXT 原始数据解析",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # 解析 TXT
    matched = []
    for line in req.txt_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rsid = parts[0]
        genotype = parts[3].strip()
        if rsid in KNOWN_SNPS and genotype != "--":
            snp = KNOWN_SNPS[rsid]
            mapping = snp["map"].get(genotype)
            if not mapping:
                # 尝试反转基因型 (AG→GA)
                rev = genotype[::-1] if len(genotype) == 2 else genotype
                mapping = snp["map"].get(rev)
            if mapping:
                geno_label, result_label, risk = mapping
                variant = GeneticVariant(
                    user_id=current_user.id,
                    profile_id=profile.id,
                    category=snp["category"],
                    gene_name=snp["gene"],
                    variant_name=snp["variant"],
                    genotype=geno_label,
                    result_label=result_label,
                    risk_level=risk,
                    description=snp["desc"],
                )
                db.add(variant)
                matched.append({"gene": snp["gene"], "genotype": geno_label, "result": result_label, "risk": risk})

    profile.notes = f"TXT 解析完成，匹配 {len(matched)} 个健康位点"
    db.commit()

    # Memory KG: 基因位点 → entity + 'self_user has_genotype variant' (旁路)
    try:
        from app.services.memory_extractor import bulk_extract_genes_for_profile
        n = bulk_extract_genes_for_profile(db, current_user.id, profile.id)
        db.commit()
        logger.info(f"[基因TXT] profile={profile.id} KG 写入 {n} 个有临床意义的位点")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[基因TXT] KG extract 失败 (旁路): {e}")

    # Twin invalidation: 让下次 specialist 立刻拿到新基因数据 (旁路)
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(current_user.id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[基因TXT] Twin invalidation 失败 (旁路): {e}")

    return {
        "id": profile.id,
        "matched_count": len(matched),
        "variants": matched,
        "message": f"成功解析 {len(matched)} 个健康相关基因位点",
    }


@router.post("/profiles/upload-pdf", summary="上传基因检测 PDF，AI 自动提取基因位点")
def upload_genetic_pdf(
    req: GeneticPdfUploadRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """上传基因检测 PDF 报告，AI 后台异步提取基因位点数据"""
    # 1. 创建档案
    profile = GeneticProfile(
        user_id=current_user.id,
        test_provider=req.test_provider,
        test_date=req.test_date,
        notes=req.notes or "PDF 自动提取",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # 2. 后台提取
    import threading
    threading.Thread(
        target=_extract_genetic_from_pdf,
        args=(profile.id, current_user.id, req.pdf_base64),
        daemon=True,
    ).start()

    return {
        "id": profile.id,
        "status": "processing",
        "message": "PDF 已上传，AI 正在后台提取基因位点...",
    }


def _extract_genetic_from_pdf(profile_id: int, user_id: int, pdf_base64: str):
    """后台线程：PDF → 图片 → LLM 提取基因位点 → 保存"""
    import asyncio
    import json
    import base64
    import re

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # PDF 转图片
        from app.api.family_health import _pdf_to_images_base64
        from app.services.llm.usage_tracker import set_caller
        set_caller("genetic.pdf_vision", user_id=user_id)
        images = _pdf_to_images_base64(pdf_base64)
        logger.info(f"[基因PDF] profile={profile_id} PDF 转换为 {len(images)} 页")

        all_variants = []

        # 逐页 LLM 提取
        from app.services.llm.factory import get_vision_provider
        import time

        prompt = """请从这份基因检测报告页面中提取所有基因位点信息。

对每个基因位点，返回 JSON 数组：
```json
[
  {
    "category": "nutrition/exercise/drug_sensitivity/disease_risk/sleep/other",
    "gene_name": "基因名称（如 MTHFR）",
    "variant_name": "变异位点（如 C677T）",
    "genotype": "检测结果（如 CT）",
    "result_label": "中文结果描述（如 叶酸代谢轻度减弱）",
    "risk_level": "low/medium/high/info",
    "description": "简短说明"
  }
]
```

category 分类规则：
- nutrition: 营养代谢相关（叶酸、咖啡因、乳糖、酒精、维生素等）
- exercise: 运动能力相关（肌肉类型、耐力、有氧能力等）
- drug_sensitivity: 药物敏感性（药物代谢酶、过敏风险等）
- disease_risk: 疾病风险（心血管、糖尿病、肿瘤等）
- sleep: 睡眠相关（昼夜节律、深度睡眠等）
- other: 其他

如果页面中没有基因位点信息，返回空数组 []。只返回 JSON，不要其他文字。"""

        provider = get_vision_provider()

        for i, img_b64 in enumerate(images):
            try:
                # 压缩图片
                from app.services.openclaw_service import OpenClawService
                compressed = OpenClawService._compress_image_static(img_b64)

                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    provider.chat_with_vision(prompt, compressed, "jpeg")
                )
                loop.close()

                # 解析 JSON
                text = result if isinstance(result, str) else str(result)
                json_match = re.search(r'\[.*\]', text, re.DOTALL)
                if json_match:
                    variants = json.loads(json_match.group())
                    all_variants.extend(variants)
                    logger.info(f"[基因PDF] 第{i+1}页提取到 {len(variants)} 个位点")

                time.sleep(2)  # 限流
            except Exception as e:
                logger.warning(f"[基因PDF] 第{i+1}页提取失败: {e}")
                continue

        # 保存提取的位点
        saved = 0
        for v in all_variants:
            try:
                variant = GeneticVariant(
                    user_id=user_id,
                    profile_id=profile_id,
                    category=v.get("category", "other"),
                    gene_name=v.get("gene_name", ""),
                    variant_name=v.get("variant_name", ""),
                    genotype=v.get("genotype", ""),
                    result_label=v.get("result_label", ""),
                    risk_level=v.get("risk_level", "info"),
                    description=v.get("description", ""),
                )
                db.add(variant)
                saved += 1
            except Exception as e:
                logger.warning(f"[基因PDF] 保存位点失败: {e}")

        # 更新档案备注
        profile = db.query(GeneticProfile).get(profile_id)
        if profile:
            profile.notes = f"PDF 自动提取完成，共 {saved} 个位点"
        db.commit()
        logger.info(f"[基因PDF] profile={profile_id} 完成，提取 {saved} 个位点")

        # Memory KG: 基因位点 → entity + 'self_user has_genotype variant' (旁路)
        try:
            from app.services.memory_extractor import bulk_extract_genes_for_profile
            n = bulk_extract_genes_for_profile(db, user_id, profile_id)
            db.commit()
            logger.info(f"[基因PDF] profile={profile_id} KG 写入 {n} 个有临床意义的位点")
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning(f"[基因PDF] KG extract 失败 (旁路): {e}")

        # Twin invalidation: 让下次 specialist 立刻拿到新基因数据 (旁路)
        try:
            from app.twin.cache import invalidate_twin
            invalidate_twin(user_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[基因PDF] Twin invalidation 失败 (旁路): {e}")

    except Exception as e:
        logger.error(f"[基因PDF] profile={profile_id} 处理失败: {e}", exc_info=True)
        try:
            profile = db.query(GeneticProfile).get(profile_id)
            if profile:
                profile.notes = f"PDF 提取失败: {str(e)[:100]}"
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ══════════════════════════════════════════════════════════
# 基因档案 CRUD
# ══════════════════════════════════════════════════════════

@router.post("/profiles", summary="创建基因检测档案")
def create_profile(
    req: ProfileCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profile = GeneticProfile(
        user_id=current_user.id,
        test_provider=req.test_provider,
        test_date=req.test_date,
        report_id=req.report_id,
        notes=req.notes,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "test_provider": profile.test_provider,
        "test_date": str(profile.test_date),
        "report_id": profile.report_id,
        "notes": profile.notes,
    }


@router.get("/profiles/me", summary="我的基因档案列表")
def list_profiles(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profiles = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == current_user.id)
        .order_by(desc(GeneticProfile.test_date))
        .all()
    )
    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "test_provider": p.test_provider,
            "test_date": str(p.test_date),
            "report_id": p.report_id,
            "notes": p.notes,
            "created_at": str(p.created_at) if p.created_at else None,
        }
        for p in profiles
    ]


@router.get("/profiles/{profile_id}/status", summary="基因档案解析状态 (轻量轮询端点)")
def get_profile_status(
    profile_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    PDF 异步解析专用轮询端点 — 只返 status + variant_count + notes, 不带 variants 列表.

    status 语义:
      - "processing": notes 为空或含"提取中/正在"
      - "failed":     notes 含"失败"
      - "done":       notes 含"完成" 或 variant_count > 0
    """
    profile = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.id == profile_id, GeneticProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="基因档案不存在")

    variant_count = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.profile_id == profile.id)
        .count()
    )
    notes = profile.notes or ""
    if "失败" in notes:
        status = "failed"
    elif "完成" in notes or variant_count > 0:
        status = "done"
    else:
        status = "processing"

    return {
        "id": profile.id,
        "status": status,
        "variant_count": variant_count,
        "notes": notes,
    }


@router.get("/profiles/{profile_id}", summary="基因档案详情（含变异位点）")
def get_profile_detail(
    profile_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.id == profile_id, GeneticProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="基因档案不存在")

    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.profile_id == profile.id)
        .order_by(GeneticVariant.category, GeneticVariant.gene_name)
        .all()
    )

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "test_provider": profile.test_provider,
        "test_date": str(profile.test_date),
        "report_id": profile.report_id,
        "notes": profile.notes,
        "created_at": str(profile.created_at) if profile.created_at else None,
        "variants": [
            {
                "id": v.id,
                "category": v.category,
                "gene_name": v.gene_name,
                "variant_name": v.variant_name,
                "genotype": v.genotype,
                "result_label": v.result_label,
                "risk_level": v.risk_level,
                "description": v.description,
                "health_implications": v.health_implications,
            }
            for v in variants
        ],
    }


@router.delete("/profiles/{profile_id}", summary="删除基因档案（级联删除变异位点）")
def delete_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.id == profile_id, GeneticProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="基因档案不存在")

    # 先删除关联的变异位点（SQLite 不支持 ON DELETE CASCADE）
    db.query(GeneticVariant).filter(GeneticVariant.profile_id == profile.id).delete()
    db.delete(profile)
    db.commit()
    return {"message": "已删除", "id": profile_id}


# ══════════════════════════════════════════════════════════
# 变异位点 CRUD
# ══════════════════════════════════════════════════════════

@router.post("/variants/batch", summary="批量创建变异位点")
def batch_create_variants(
    req: VariantBatchCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 验证所有 profile_id 属于当前用户
    profile_ids = set(v.profile_id for v in req.variants)
    valid_profiles = (
        db.query(GeneticProfile.id)
        .filter(GeneticProfile.id.in_(profile_ids), GeneticProfile.user_id == current_user.id)
        .all()
    )
    valid_ids = {p.id for p in valid_profiles}
    invalid_ids = profile_ids - valid_ids
    if invalid_ids:
        raise HTTPException(status_code=404, detail=f"基因档案不存在或无权访问: {invalid_ids}")

    created = []
    for v in req.variants:
        variant = GeneticVariant(
            user_id=current_user.id,
            profile_id=v.profile_id,
            category=v.category,
            gene_name=v.gene_name,
            variant_name=v.variant_name,
            genotype=v.genotype,
            result_label=v.result_label,
            risk_level=v.risk_level,
            description=v.description,
            health_implications=v.health_implications,
        )
        db.add(variant)
        created.append(variant)

    db.commit()
    for v in created:
        db.refresh(v)

    # Memory KG: 批量创建的基因位点 → entity (旁路)
    try:
        from app.services.memory_extractor import extract_kg_from_gene_variant
        for v in created:
            extract_kg_from_gene_variant(db, current_user.id, v)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[基因批量] KG extract 失败 (旁路): {e}")

    return {
        "created": len(created),
        "ids": [v.id for v in created],
    }


@router.put("/variants/{variant_id}", summary="更新变异位点")
def update_variant(
    variant_id: int,
    req: VariantUpdateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    variant = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.id == variant_id, GeneticVariant.user_id == current_user.id)
        .first()
    )
    if not variant:
        raise HTTPException(status_code=404, detail="变异位点不存在")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(variant, key, value)

    db.commit()
    db.refresh(variant)
    return {
        "id": variant.id,
        "category": variant.category,
        "gene_name": variant.gene_name,
        "variant_name": variant.variant_name,
        "genotype": variant.genotype,
        "result_label": variant.result_label,
        "risk_level": variant.risk_level,
        "description": variant.description,
        "health_implications": variant.health_implications,
    }


@router.delete("/variants/{variant_id}", summary="删除变异位点")
def delete_variant(
    variant_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    variant = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.id == variant_id, GeneticVariant.user_id == current_user.id)
        .first()
    )
    if not variant:
        raise HTTPException(status_code=404, detail="变异位点不存在")

    db.delete(variant)
    db.commit()
    return {"message": "已删除", "id": variant_id}


@router.get("/variants/me", summary="我的变异位点列表（可按分类过滤）")
def list_variants(
    category: Optional[str] = Query(None, description="分类过滤: nutrition/exercise/drug_sensitivity/disease_risk/sleep"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(GeneticVariant).filter(GeneticVariant.user_id == current_user.id)
    if category:
        query = query.filter(GeneticVariant.category == category)
    variants = query.order_by(GeneticVariant.category, GeneticVariant.gene_name).all()

    return [
        {
            "id": v.id,
            "profile_id": v.profile_id,
            "category": v.category,
            "gene_name": v.gene_name,
            "variant_name": v.variant_name,
            "genotype": v.genotype,
            "result_label": v.result_label,
            "risk_level": v.risk_level,
            "description": v.description,
            "health_implications": v.health_implications,
        }
        for v in variants
    ]


# ══════════════════════════════════════════════════════════
# 统计摘要
# ══════════════════════════════════════════════════════════

@router.get("/summary/me", summary="基因变异分类统计")
def get_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """按分类统计变异位点数量，并列出高风险项"""
    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.user_id == current_user.id)
        .all()
    )

    categories: Dict[str, Any] = {}
    for v in variants:
        cat = v.category
        if cat not in categories:
            categories[cat] = {"count": 0, "high_risk": []}
        categories[cat]["count"] += 1
        if v.risk_level == "high":
            categories[cat]["high_risk"].append({
                "id": v.id,
                "gene_name": v.gene_name,
                "variant_name": v.variant_name,
                "result_label": v.result_label,
                "description": v.description,
            })

    return {
        "total_variants": len(variants),
        "categories": categories,
    }


# ══════════════════════════════════════════════════════════
# 基因档案 — 认知 / 个性 / 全景
# ══════════════════════════════════════════════════════════


def _score_dimension(genes_found: int, genes_total: int, risk_count: int) -> Dict[str, Any]:
    """根据已检测基因数和风险基因数计算维度得分(1-5)和置信度。"""
    if genes_found == 0:
        return {"score": 3, "confidence": "none", "note": "无相关基因数据"}
    confidence = "high" if genes_found >= 3 else "medium" if genes_found >= 2 else "low"
    base = 3.0
    if genes_found > 0:
        risk_ratio = risk_count / genes_found
        base = 4.5 - risk_ratio * 3.0
    return {"score": max(1, min(5, round(base))), "confidence": confidence}


def _classify_variant_risk(v) -> bool:
    risk = (getattr(v, "risk_level", None) or "").lower()
    return risk in ("medium", "high")


@router.get("/profile/me/cognitive", summary="认知基因档案")
def get_cognitive_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    variants = db.query(GeneticVariant).filter(GeneticVariant.user_id == current_user.id).all()
    by_gene = {}
    for v in variants:
        by_gene.setdefault(v.gene_name.upper(), v)

    dimensions = {}

    # 记忆力: KIBRA, BDNF
    memory_genes = [by_gene.get(g) for g in ("KIBRA", "BDNF") if g in by_gene]
    memory_risk = sum(1 for g in memory_genes if _classify_variant_risk(g))
    dimensions["memory"] = {
        **_score_dimension(len(memory_genes), 2, memory_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in memory_genes],
        "recommendations": (["有氧运动促BDNF表达，记忆训练强化海马功能"] if memory_risk > 0 else ["记忆基因表现良好，保持学习习惯"]),
    }

    # 专注力: CHRNA4, ADRA2A
    focus_genes = [by_gene.get(g) for g in ("CHRNA4", "ADRA2A") if g in by_gene]
    focus_risk = sum(1 for g in focus_genes if _classify_variant_risk(g))
    dimensions["focus"] = {
        **_score_dimension(len(focus_genes), 2, focus_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in focus_genes],
        "recommendations": (["番茄钟法管理注意力、减少多任务切换、考虑L-茶氨酸(200mg)"] if focus_risk > 0 else ["注意力基因正常，保持专注习惯"]),
    }

    # 学习速度: SNAP25
    learn_genes = [by_gene.get(g) for g in ("SNAP25",) if g in by_gene]
    learn_risk = sum(1 for g in learn_genes if _classify_variant_risk(g))
    dimensions["learning_speed"] = {
        **_score_dimension(len(learn_genes), 1, learn_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in learn_genes],
        "recommendations": (["间隔重复法(Anki)优化学习效率"] if learn_risk > 0 else ["突触传递效率良好"]),
    }

    # 抗压力: COMT
    stress_genes = [by_gene.get(g) for g in ("COMT",) if g in by_gene]
    stress_risk = sum(1 for g in stress_genes if _classify_variant_risk(g))
    comt = by_gene.get("COMT")
    comt_type = None
    if comt:
        geno = (comt.genotype or "").upper()
        if "VAL/VAL" in geno:
            comt_type = "战士型(Val/Val)—压力下稳定"
        elif "MET/MET" in geno:
            comt_type = "思考者型(Met/Met)—创造力高但易焦虑"
        else:
            comt_type = "混合型(Val/Met)"
    dimensions["stress_resilience"] = {
        **_score_dimension(len(stress_genes), 1, stress_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in stress_genes],
        "comt_type": comt_type,
        "recommendations": (["冥想/正念训练、减少咖啡因、避免多任务"] if stress_risk > 0 else ["压力耐受良好，可用高强度运动释放"]),
    }

    # 情绪稳定: TPH2
    mood_genes = [by_gene.get(g) for g in ("TPH2",) if g in by_gene]
    mood_risk = sum(1 for g in mood_genes if _classify_variant_risk(g))
    dimensions["emotional_stability"] = {
        **_score_dimension(len(mood_genes), 1, mood_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in mood_genes],
        "recommendations": (["有氧运动+ω-3+早晨光照提升血清素"] if mood_risk > 0 else ["血清素合成正常"]),
    }

    return {
        "status": "ok",
        "disclaimer": "基于有限SNP的倾向性预测，非智商诊断，仅供参考",
        "genes_tested": len(variants),
        "dimensions": dimensions,
    }


@router.get("/profile/me/personality", summary="个性基因档案")
def get_personality_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    variants = db.query(GeneticVariant).filter(GeneticVariant.user_id == current_user.id).all()
    by_gene = {}
    for v in variants:
        by_gene.setdefault(v.gene_name.upper(), v)

    big_five = {}

    # 神经质(Neuroticism): SLC6A4, TPH2
    neuro_genes = [by_gene.get(g) for g in ("SLC6A4", "TPH2") if g in by_gene]
    neuro_risk = sum(1 for g in neuro_genes if _classify_variant_risk(g))
    big_five["neuroticism"] = {
        "label": "神经质/情绪稳定性",
        **_score_dimension(len(neuro_genes), 2, neuro_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in neuro_genes],
        "interpretation": "得分越高=情绪越稳定" if neuro_risk == 0 else "焦虑/抑郁易感性偏高",
    }

    # 外向性(Extraversion): DRD2, OXTR
    extra_genes = [by_gene.get(g) for g in ("DRD2", "OXTR") if g in by_gene]
    extra_risk = sum(1 for g in extra_genes if _classify_variant_risk(g))
    big_five["extraversion"] = {
        "label": "外向性/社交驱动",
        **_score_dimension(len(extra_genes), 2, extra_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in extra_genes],
        "interpretation": "社交驱动强" if extra_risk == 0 else "独立性强/社交回避倾向",
    }

    # 开放性(Openness): COMT, BDNF
    open_genes = [by_gene.get(g) for g in ("COMT", "BDNF") if g in by_gene]
    open_risk = sum(1 for g in open_genes if _classify_variant_risk(g))
    big_five["openness"] = {
        "label": "开放性/创造力",
        **_score_dimension(len(open_genes), 2, open_risk),
        "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label} for g in open_genes],
        "interpretation": "COMT Met型与高创造力相关" if any(
            "MET" in (g.genotype or "").upper() for g in open_genes
        ) else "标准范围",
    }

    # 尽责性/宜人性
    big_five["conscientiousness"] = {
        "label": "尽责性",
        "score": 3, "confidence": "none",
        "genes": [],
        "interpretation": "暂无可靠基因标记，主要受后天环境塑造",
    }
    big_five["agreeableness"] = {
        "label": "宜人性",
        "score": 3, "confidence": "none",
        "genes": [],
        "interpretation": "暂无可靠基因标记，主要受后天环境塑造",
    }

    # 压力应对类型
    comt = by_gene.get("COMT")
    stress_coping = None
    if comt:
        geno = (comt.genotype or "").upper()
        if "VAL/VAL" in geno:
            stress_coping = {"type": "warrior", "label": "战士型", "description": "多巴胺清除快，压力下表现稳定，适合高压环境"}
        elif "MET/MET" in geno:
            stress_coping = {"type": "worrier", "label": "思考者型", "description": "多巴胺清除慢，创造力高但易焦虑，需要低压环境发挥"}
        else:
            stress_coping = {"type": "mixed", "label": "混合型", "description": "兼具战士和思考者特征，适应性强"}

    # 社交需求
    oxtr = by_gene.get("OXTR")
    social_need = None
    if oxtr:
        geno = (oxtr.genotype or "").upper()
        if "GG" in geno:
            social_need = {"level": "high", "label": "高社交需求", "tip": "孤独时心理风险高于平均，确保每天有真人互动"}
        elif "AA" in geno:
            social_need = {"level": "low", "label": "低社交需求", "tip": "独立性强，独处不焦虑，但主动社交有利身心"}
        else:
            social_need = {"level": "moderate", "label": "中等社交需求"}

    return {
        "status": "ok",
        "disclaimer": "基因对人格的解释力约10-15%，环境和经历影响更大",
        "big_five": big_five,
        "stress_coping": stress_coping,
        "social_need": social_need,
    }


@router.get("/profile/me/comprehensive", summary="全景基因档案")
def get_comprehensive_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    variants = db.query(GeneticVariant).filter(GeneticVariant.user_id == current_user.id).all()
    if not variants:
        return {"status": "no_data", "message": "暂无基因数据"}

    by_gene = {}
    by_category: Dict[str, list] = {}
    for v in variants:
        by_gene.setdefault(v.gene_name.upper(), v)
        by_category.setdefault(v.category or "other", []).append(v)

    def _dim(gene_names, total):
        found = [by_gene.get(g) for g in gene_names if g in by_gene]
        risk = sum(1 for g in found if _classify_variant_risk(g))
        return {
            **_score_dimension(len(found), total, risk),
            "genes": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label, "risk": g.risk_level} for g in found],
        }

    profile = {
        "cognition": {
            "memory": _dim(["KIBRA", "BDNF"], 2),
            "focus": _dim(["CHRNA4", "ADRA2A"], 2),
            "learning": _dim(["SNAP25"], 1),
            "stress_resilience": _dim(["COMT"], 1),
            "emotional_stability": _dim(["TPH2"], 1),
        },
        "personality": {
            "neuroticism": _dim(["SLC6A4", "TPH2"], 2),
            "extraversion": _dim(["DRD2", "OXTR"], 2),
            "openness": _dim(["COMT", "BDNF"], 2),
        },
        "exercise": {
            "power_vs_endurance": _dim(["ACTN3", "ACE"], 2),
            "injury_risk": _dim(["COL5A1"], 1),
            "vascular_function": _dim(["NOS3"], 1),
            "aerobic_capacity": _dim(["PPARGC1A"], 1),
        },
        "nutrition": {
            "folate": _dim(["MTHFR", "MTRR", "MTR"], 3),
            "vitamin_d": _dim(["VDR", "GC"], 2),
            "caffeine": _dim(["CYP1A2"], 1),
            "lactose": _dim(["LCT"], 1),
            "alcohol": _dim(["ALDH2", "ADH1B"], 2),
            "omega3": _dim(["FADS1"], 1),
            "iron": _dim(["HFE"], 1),
            "obesity": _dim(["FTO", "PPARG"], 2),
        },
        "sleep": {
            "chronotype": _dim(["CLOCK", "PER2"], 2),
            "deep_sleep": _dim(["ADA"], 1),
            "caffeine_sensitivity": _dim(["ADORA2A", "CYP1A2"], 2),
        },
        "recovery": {
            "inflammation": _dim(["IL-6", "TNF-α"], 2),
            "antioxidant": _dim(["SOD2", "GPX1"], 2),
            "detox": _dim(["GSTP1"], 1),
        },
        "drug_sensitivity": {
            "variants": [{"name": g.gene_name, "genotype": g.genotype, "result": g.result_label, "risk": g.risk_level}
                         for g in variants if (g.category or "").lower() == "drug_sensitivity"],
        },
        "disease_risk": {
            "cardiovascular": _dim(["APOE", "CETP", "9P21"], 3),
            "diabetes": _dim(["TCF7L2", "FTO", "PPARG", "CDKN2A/B", "IGF2BP2"], 5),
            "cancer": _dim(["8Q24", "TERT"], 2),
        },
    }

    # PRS 多基因风险评分
    from app.services.genetic_prs import compute_all_prs
    variant_dicts = [{"gene_name": v.gene_name, "genotype": v.genotype, "result_label": v.result_label} for v in variants]
    prs = compute_all_prs(variant_dicts)

    return {
        "status": "ok",
        "disclaimer": "基因档案基于有限SNP位点，不构成医疗诊断。疾病风险受基因、环境、生活方式共同影响。",
        "genes_tested": len(variants),
        "categories_covered": list(by_category.keys()),
        "profile": profile,
        "polygenic_risk_scores": prs,
    }


# ══════════════════════════════════════════════════════════
# 交叉分析（LLM）
# ══════════════════════════════════════════════════════════

@router.get("/cross-analysis/me", summary="基因 + 健康数据交叉分析")
def get_cross_analysis(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    综合基因变异 + 用户画像（慢性病/用药）+ 最新 Garmin 数据 + 体检指标，
    通过 LLM 生成个性化交叉分析。
    """
    # 1. 获取基因变异
    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.user_id == current_user.id)
        .all()
    )
    if not variants:
        return {
            "status": "no_data",
            "message": "暂无基因数据，请先上传基因检测报告",
            "sections": {},
        }

    # 2. 用户画像
    from app.models.user_profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    # 3. 最新 Garmin 数据
    garmin_summary = _get_latest_garmin_summary(db, current_user.id)

    # 4. 最新异常体检指标
    abnormal_indicators = _get_abnormal_indicators(db, current_user.id)

    # 5. 构建 LLM prompt
    prompt = _build_cross_analysis_prompt(variants, profile, garmin_summary, abnormal_indicators)

    # 6. 调用 LLM
    try:
        from app.services.llm.factory import get_llm_provider
        from app.services.llm.usage_tracker import set_caller
        from app.utils.async_helpers import run_async

        set_caller("genetic.cross_analysis", user_id=current_user.id)
        provider = get_llm_provider()
        messages = [
            {"role": "system", "content": "你是一位精通基因组学和精准医学的健康顾问。请基于用户的基因检测数据和健康数据，给出个性化的交叉分析。回复使用中文，以 JSON 格式返回。"},
            {"role": "user", "content": prompt},
        ]
        result = run_async(provider.chat(messages=messages, temperature=0.3, max_tokens=3000))

        # 尝试解析 JSON
        import json
        try:
            # 处理可能的 markdown 代码块
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            sections = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            sections = {"raw_analysis": result}

        return {
            "status": "ok",
            "variant_count": len(variants),
            "sections": sections,
        }
    except Exception as e:
        logger.error(f"基因交叉分析 LLM 调用失败: {e}", exc_info=True)
        # 回退：返回模板化结构
        return {
            "status": "fallback",
            "message": "AI 分析暂时不可用，返回基础统计",
            "variant_count": len(variants),
            "sections": _build_fallback_sections(variants),
        }


def _get_latest_garmin_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """获取最新 Garmin 数据摘要"""
    try:
        from app.models.garmin import GarminData
        latest = (
            db.query(GarminData)
            .filter(GarminData.user_id == user_id)
            .order_by(desc(GarminData.date))
            .first()
        )
        if latest:
            return {
                "date": str(latest.date),
                "steps": latest.steps,
                "heart_rate_avg": latest.heart_rate_avg,
                "heart_rate_rest": latest.heart_rate_rest,
                "sleep_hours": latest.sleep_hours,
                "stress_avg": getattr(latest, "stress_avg", None),
                "body_battery_high": getattr(latest, "body_battery_high", None),
            }
    except Exception:
        pass
    return {}


def _get_abnormal_indicators(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """获取最近的异常体检指标"""
    try:
        from app.models.family_health import MedicalIndicator
        indicators = (
            db.query(MedicalIndicator)
            .filter(MedicalIndicator.user_id == user_id, MedicalIndicator.is_abnormal == True)
            .order_by(desc(MedicalIndicator.record_date))
            .limit(10)
            .all()
        )
        return [
            {
                "name": ind.name,
                "value": ind.value,
                "unit": ind.unit,
                "severity": ind.severity,
                "record_date": str(ind.record_date),
            }
            for ind in indicators
        ]
    except Exception:
        return []


def _build_cross_analysis_prompt(
    variants: List[GeneticVariant],
    profile,
    garmin_summary: Dict[str, Any],
    abnormal_indicators: List[Dict[str, Any]],
) -> str:
    """构建交叉分析 prompt"""
    parts = ["## 用户基因变异数据\n"]

    # 按分类整理变异
    by_category: Dict[str, list] = {}
    for v in variants:
        by_category.setdefault(v.category, []).append(v)

    for cat, vs in by_category.items():
        parts.append(f"### {cat}")
        for v in vs:
            line = f"- {v.gene_name}"
            if v.variant_name:
                line += f" ({v.variant_name})"
            if v.genotype:
                line += f" 基因型: {v.genotype}"
            if v.result_label:
                line += f" -> {v.result_label}"
            if v.risk_level and v.risk_level != "info":
                line += f" [风险: {v.risk_level}]"
            parts.append(line)
        parts.append("")

    # 用户画像
    if profile:
        parts.append("## 用户健康画像")
        if getattr(profile, "chronic_conditions", None):
            parts.append(f"慢性病: {profile.chronic_conditions}")
        if getattr(profile, "medications", None):
            parts.append(f"用药: {profile.medications}")
        if getattr(profile, "allergies", None):
            parts.append(f"过敏: {profile.allergies}")
        parts.append("")

    # Garmin 数据
    if garmin_summary:
        parts.append("## 最近运动/睡眠数据")
        for k, v in garmin_summary.items():
            if v is not None:
                parts.append(f"- {k}: {v}")
        parts.append("")

    # 异常指标
    if abnormal_indicators:
        parts.append("## 近期异常体检指标")
        for ind in abnormal_indicators:
            parts.append(f"- {ind['name']}: {ind['value']} {ind.get('unit', '')} ({ind.get('severity', '')}) [{ind.get('record_date', '')}]")
        parts.append("")

    parts.append(
        "请基于以上数据，返回 JSON 格式的交叉分析，包含以下字段:\n"
        "- nutrition_advice: 营养建议（考虑基因对营养吸收的影响）\n"
        "- exercise_advice: 运动建议（考虑基因对运动能力的影响，结合ACTN3/ACE基因型与实际运动表现验证训练方向）\n"
        "- sleep_advice: 睡眠建议（结合CLOCK/PER2/ADA/ADORA2A基因型与实际入睡时间，判断是否与基因倾向一致）\n"
        "- recovery_advice: 恢复建议（结合IL-6/TNF-α/SOD2/GPX1基因型评估恢复策略和抗氧化补剂需求）\n"
        "- cognition_personality: 认知与个性档案（结合COMT/BDNF/DRD2/TPH2/SLC6A4/OXTR评估压力应对类型和认知特征）\n"
        "- drug_alerts: 药物敏感性提醒\n"
        "- disease_prevention: 疾病预防建议\n"
        "- gene_vs_data_validation: 基因预测与实际数据的一致性验证（如FTO基因型vs实际体重趋势、MTHFR基因型vs HCY体检值、CLOCK基因型vs实际入睡时间）\n"
        "每个字段的值为字符串，包含详细的个性化建议。"
    )

    return "\n".join(parts)


def _build_fallback_sections(variants: List[GeneticVariant]) -> Dict[str, str]:
    """LLM 不可用时的回退模板"""
    by_category: Dict[str, list] = {}
    for v in variants:
        by_category.setdefault(v.category, []).append(v)

    sections = {}

    if "nutrition" in by_category:
        genes = ", ".join(v.gene_name for v in by_category["nutrition"])
        sections["nutrition_advice"] = f"您有 {len(by_category['nutrition'])} 个营养相关基因变异（{genes}），建议关注个性化营养摄入。"

    if "exercise" in by_category:
        genes = ", ".join(v.gene_name for v in by_category["exercise"])
        sections["exercise_advice"] = f"您有 {len(by_category['exercise'])} 个运动相关基因变异（{genes}），建议根据基因特点选择运动方式。"

    if "sleep" in by_category:
        sections["sleep_advice"] = f"您有 {len(by_category['sleep'])} 个睡眠相关基因变异，建议关注睡眠质量优化。"

    if "drug_sensitivity" in by_category:
        genes = ", ".join(v.gene_name for v in by_category["drug_sensitivity"])
        sections["drug_alerts"] = f"您有 {len(by_category['drug_sensitivity'])} 个药物敏感性相关基因变异（{genes}），用药前请咨询医生。"

    if "disease_risk" in by_category:
        high_risk = [v for v in by_category["disease_risk"] if v.risk_level == "high"]
        sections["disease_prevention"] = f"您有 {len(by_category['disease_risk'])} 个疾病风险相关基因变异，其中 {len(high_risk)} 个为高风险，建议定期体检。"

    if not sections:
        sections["general"] = "您的基因数据已记录，建议结合体检指标进行综合分析。"

    return sections
