"""PDF解析服务 - 解析体检报告PDF并结构化保存"""
import os
import json
import logging
import tempfile
from typing import Optional, Dict, Any, List
from datetime import date
import pdfplumber
from openai import OpenAI
from app.config import settings
from app.services.exam_packages import normalize_item_name, identify_package, ITEM_LABELS

logger = logging.getLogger(__name__)


class MedicalReportPDFParser:
    """体检报告PDF解析器"""
    
    def __init__(self):
        self.client = None
        if settings.openai_api_key:
            # 支持代理配置
            client_kwargs = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                client_kwargs["base_url"] = settings.openai_base_url
            self.client = OpenAI(**client_kwargs)
        self.model = settings.openai_model or "gpt-4o-mini"
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """从PDF中提取文本"""
        text_content = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        text_content.append(f"--- 第{page_num}页 ---\n{page_text}")
                    
                    # 尝试提取表格
                    tables = page.extract_tables()
                    for table_idx, table in enumerate(tables):
                        if table:
                            table_text = self._format_table(table)
                            text_content.append(f"\n[表格 {table_idx + 1}]\n{table_text}")
        except Exception as e:
            logger.error(f"PDF解析失败: {e}")
            raise ValueError(f"PDF解析失败: {str(e)}")
        
        return "\n".join(text_content)
    
    def _format_table(self, table: List[List[str]]) -> str:
        """格式化表格为文本"""
        lines = []
        for row in table:
            if row:
                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                lines.append(" | ".join(cleaned_row))
        return "\n".join(lines)
    
    def parse_with_llm(self, text_content: str) -> Dict[str, Any]:
        """使用LLM解析体检报告文本"""
        if not self.client:
            raise ValueError("LLM服务不可用，请配置OpenAI API Key")
        
        prompt = """你是一个专业的医疗报告解析专家。请解析以下体检报告内容，提取结构化数据。

请严格按照以下JSON格式返回结果（不要包含任何其他文字，只返回JSON）：

{{
    "patient_name": "患者姓名",
    "patient_gender": "性别(male/female)",
    "patient_age": 年龄数字,
    "exam_date": "YYYY-MM-DD格式的体检日期",
    "exam_number": "体检号",
    "exam_type": "comprehensive",
    "hospital_name": "医院名称",
    "doctor_name": "医生姓名（如果有）",
    "overall_assessment": "总体评价摘要",
    "conclusions": [
        {{
            "category": "分类(urgent_attention/needs_attention/regular_followup/normal)",
            "title": "结论标题",
            "description": "详细描述",
            "recommendations": "建议措施"
        }}
    ],
    "items": [
        {{
            "category": "检查类别代码（参考下方类别说明，使用细分类别如blood_routine_wbc/liver_alt/immune_cd4/tumor_afp/thyroid_tsh/us_liver/brain_ct/ecg等）",
            "item_name": "检查项目名称",
            "value": 数值或null,
            "value_text": "文本值（如影像结论）",
            "unit": "单位",
            "reference_range": "参考范围",
            "is_abnormal": "normal/high/low/abnormal",
            "notes": "备注说明"
        }}
    ]
}}

检查类别说明（请使用以下标准类别名称，尽量使用细分类别）：

═══════════════════════════════════════════════════════════════
【血常规检查】 blood_routine 系列
═══════════════════════════════════════════════════════════════
- blood_routine: 血常规（总项）
- blood_routine_wbc: 白细胞计数
- blood_routine_rbc: 红细胞计数
- blood_routine_hgb: 血红蛋白
- blood_routine_plt: 血小板计数
- blood_routine_neut: 中性粒细胞（绝对值/百分比）
- blood_routine_lymph: 淋巴细胞（绝对值/百分比）
- blood_routine_mono: 单核细胞
- blood_routine_eos: 嗜酸性粒细胞
- blood_routine_baso: 嗜碱性粒细胞
- blood_routine_hct: 红细胞压积
- blood_routine_mcv: 平均红细胞体积
- blood_routine_mch: 平均红细胞血红蛋白含量
- blood_routine_mchc: 平均红细胞血红蛋白浓度
- blood_routine_rdw: 红细胞分布宽度
- blood_routine_mpv: 平均血小板体积

═══════════════════════════════════════════════════════════════
【血脂检查】 lipid 系列
═══════════════════════════════════════════════════════════════
- lipid_profile: 血脂全套
- lipid_tc: 总胆固醇(TC)
- lipid_tg: 甘油三酯(TG)
- lipid_hdl: 高密度脂蛋白胆固醇(HDL-C)
- lipid_ldl: 低密度脂蛋白胆固醇(LDL-C)
- lipid_vldl: 极低密度脂蛋白(VLDL)
- lipid_apoa1: 载脂蛋白A1(ApoA1)
- lipid_apob: 载脂蛋白B(ApoB)
- lipid_lpa: 脂蛋白a[Lp(a)]
- lipid_sdldl: 小而密低密度脂蛋白(sdLDL)

═══════════════════════════════════════════════════════════════
【血糖检查】 glucose 系列
═══════════════════════════════════════════════════════════════
- blood_glucose: 血糖检查（总项）
- glucose_fasting: 空腹血糖(FPG)
- glucose_postprandial: 餐后血糖(PPG)
- glucose_hba1c: 糖化血红蛋白(HbA1c)
- glucose_ga: 糖化白蛋白(GA)
- glucose_ogtt: 糖耐量试验(OGTT)

═══════════════════════════════════════════════════════════════
【尿液检查】 urine 系列
═══════════════════════════════════════════════════════════════
- urine_routine: 尿常规
- urine_protein: 尿蛋白
- urine_glucose: 尿糖
- urine_blood: 尿隐血
- urine_wbc: 尿白细胞
- urine_microalbumin: 尿微量白蛋白
- urine_creatinine: 尿肌酐
- urine_acr: 尿白蛋白/肌酐比值

═══════════════════════════════════════════════════════════════
【粪便检查】 stool 系列
═══════════════════════════════════════════════════════════════
- stool_routine: 粪便常规
- stool_occult: 粪便隐血(OB)
- stool_full: 粪便检查（常规+OB）

═══════════════════════════════════════════════════════════════
【肝功能】 liver 系列
═══════════════════════════════════════════════════════════════
- liver_function: 肝功能（总项）
- liver_alt: 谷丙转氨酶(ALT/GPT)
- liver_ast: 谷草转氨酶(AST/GOT)
- liver_ggt: 谷氨酰转肽酶(GGT/γ-GT)
- liver_alp: 碱性磷酸酶(ALP)
- liver_tbil: 总胆红素(TBIL)
- liver_dbil: 直接胆红素(DBIL)
- liver_ibil: 间接胆红素(IBIL)
- liver_tp: 总蛋白(TP)
- liver_alb: 白蛋白(ALB)
- liver_glob: 球蛋白(GLB)
- liver_ag_ratio: 白球比(A/G)
- liver_che: 胆碱酯酶
- liver_tba: 总胆汁酸
- liver_pa: 前白蛋白

═══════════════════════════════════════════════════════════════
【肾功能】 kidney 系列
═══════════════════════════════════════════════════════════════
- kidney_function: 肾功能（总项）
- kidney_crea: 肌酐(Cr)
- kidney_bun: 尿素氮(BUN)
- kidney_ua: 尿酸(UA)
- kidney_cystc: 胱抑素C(CysC)
- kidney_egfr: 肾小球滤过率(eGFR)
- kidney_b2m: β2微球蛋白

═══════════════════════════════════════════════════════════════
【电解质】 electrolyte 系列
═══════════════════════════════════════════════════════════════
- electrolyte: 电解质（总项）
- electrolyte_k: 钾(K)
- electrolyte_na: 钠(Na)
- electrolyte_cl: 氯(Cl)
- electrolyte_ca: 钙(Ca)
- electrolyte_mg: 镁(Mg)
- electrolyte_p: 磷(P)
- electrolyte_co2: 二氧化碳结合力(CO2CP)

═══════════════════════════════════════════════════════════════
【心肌酶谱/心脏标志物】 cardiac 系列
═══════════════════════════════════════════════════════════════
- cardiac_enzyme: 心肌酶谱（总项）
- cardiac_ck: 肌酸激酶(CK)
- cardiac_ckmb: 肌酸激酶同工酶(CK-MB)
- cardiac_ldh: 乳酸脱氢酶(LDH)
- cardiac_tnl: 肌钙蛋白I(cTnI)
- cardiac_tnt: 肌钙蛋白T(cTnT)
- cardiac_bnp: B型钠尿肽(BNP)
- cardiac_ntprobnp: NT-proBNP
- cardiac_myo: 肌红蛋白(Myo)
- cardiac_hfabp: 心型脂肪酸结合蛋白

═══════════════════════════════════════════════════════════════
【凝血功能】 coagulation 系列
═══════════════════════════════════════════════════════════════
- coagulation: 凝血功能（总项）
- coag_pt: 凝血酶原时间(PT)
- coag_inr: 国际标准化比值(INR)
- coag_aptt: 活化部分凝血活酶时间(APTT)
- coag_tt: 凝血酶时间(TT)
- coag_fib: 纤维蛋白原(Fib)
- coag_ddimer: D-二聚体(D-Dimer)
- coag_fdp: 纤维蛋白降解产物(FDP)
- coag_at3: 抗凝血酶III(AT-III)

═══════════════════════════════════════════════════════════════
【免疫功能/淋巴细胞亚群】 immune 系列
═══════════════════════════════════════════════════════════════
- immune: 免疫功能（总项）
- immune_cd3: CD3+T细胞（总T细胞）
- immune_cd4: CD4+T细胞（辅助T细胞）
- immune_cd8: CD8+T细胞（细胞毒性T细胞）
- immune_cd4cd8: CD4/CD8比值
- immune_cd16: CD16+细胞
- immune_cd19: CD19+B细胞
- immune_cd45: CD45+细胞
- immune_cd56: CD56+NK细胞
- immune_nk: NK细胞(CD16+CD56+)
- immune_bcell: B淋巴细胞
- immune_tcell_10cd: 免疫功能T细胞亚型分析（10CD）
- immune_lymph_subset: 淋巴细胞亚群分析(CD3/4/8/16/19/45/56)
- immune_iga: 免疫球蛋白A(IgA)
- immune_igg: 免疫球蛋白G(IgG)
- immune_igm: 免疫球蛋白M(IgM)
- immune_ige: 免疫球蛋白E(IgE)
- immune_c3: 补体C3
- immune_c4: 补体C4
- immune_ch50: 总补体(CH50)

═══════════════════════════════════════════════════════════════
【肿瘤标志物】 tumor 系列
═══════════════════════════════════════════════════════════════
- tumor_marker: 肿瘤标志物（总项）
- tumor_afp: 甲胎蛋白(AFP)
- tumor_cea: 癌胚抗原(CEA)
- tumor_ca199: 糖类抗原CA19-9
- tumor_ca125: 糖类抗原CA125
- tumor_ca153: 糖类抗原CA15-3
- tumor_ca724: 糖类抗原CA72-4
- tumor_ca50: 糖类抗原CA50
- tumor_ca242: 糖类抗原CA242
- tumor_psa: 前列腺特异抗原(tPSA)
- tumor_fpsa: 游离前列腺特异抗原(fPSA)
- tumor_psa_ratio: PSA比值(fPSA/tPSA)
- tumor_scc: 鳞状细胞癌抗原(SCC)
- tumor_cyfra211: 细胞角蛋白19片段(CYFRA21-1)
- tumor_nse: 神经元特异性烯醇化酶(NSE)
- tumor_progrp: 胃泌素释放肽前体(ProGRP)
- tumor_ferritin: 铁蛋白
- tumor_he4: 人附睾蛋白4(HE4)
- tumor_roma: ROMA指数
- tumor_afp_l3: 甲胎蛋白异质体(AFP-L3)
- tumor_pivka: 异常凝血酶原(PIVKA-II)

═══════════════════════════════════════════════════════════════
【自身免疫抗体】 autoimmune 系列
═══════════════════════════════════════════════════════════════
- autoimmune: 自身免疫抗体（总项）
- auto_ana: 抗核抗体(ANA)
- auto_dsdna: 抗双链DNA抗体
- auto_ena: 抗可提取核抗原抗体(ENA)
- auto_rf: 类风湿因子(RF)
- auto_ccp: 抗环瓜氨酸肽抗体(Anti-CCP)
- auto_anca: 抗中性粒细胞胞浆抗体(ANCA)
- auto_gpc: 抗胃壁细胞抗体
- auto_tpo: 抗甲状腺过氧化物酶抗体(TPOAb)
- auto_tg: 抗甲状腺球蛋白抗体(TgAb)
- auto_sm: 抗Sm抗体
- auto_ssa: 抗SSA抗体
- auto_ssb: 抗SSB抗体
- auto_jo1: 抗Jo-1抗体

═══════════════════════════════════════════════════════════════
【甲状腺功能】 thyroid 系列
═══════════════════════════════════════════════════════════════
- thyroid: 甲状腺功能（总项）
- thyroid_full: 甲功全套(TT3/TT4/TSH/FT3/FT4/TPOAb/TgAb)
- thyroid_tsh: 促甲状腺激素(TSH)
- thyroid_ft3: 游离三碘甲状腺原氨酸(FT3)
- thyroid_ft4: 游离甲状腺素(FT4)
- thyroid_t3: 总三碘甲状腺原氨酸(TT3)
- thyroid_t4: 总甲状腺素(TT4)
- thyroid_tgab: 甲状腺球蛋白抗体(TgAb)
- thyroid_tpoab: 甲状腺过氧化物酶抗体(TPOAb)
- thyroid_trab: 促甲状腺素受体抗体(TRAb)
- thyroid_tg: 甲状腺球蛋白(Tg)
- thyroid_ct: 降钙素(CT)

═══════════════════════════════════════════════════════════════
【激素检查】 hormone 系列
═══════════════════════════════════════════════════════════════
- hormone: 激素检查（总项）
- hormone_fsh: 卵泡刺激素(FSH)
- hormone_lh: 黄体生成素(LH)
- hormone_e2: 雌二醇(E2)
- hormone_prog: 孕酮(P)
- hormone_test: 睾酮(T)
- hormone_prl: 泌乳素(PRL)
- hormone_dheas: 硫酸脱氢表雄酮(DHEA-S)
- hormone_cortisol: 皮质醇
- hormone_acth: 促肾上腺皮质激素(ACTH)
- hormone_gh: 生长激素(GH)
- hormone_igf1: 胰岛素样生长因子-1(IGF-1)
- hormone_insulin_fasting: 空腹胰岛素(FINS)
- hormone_insulin_postprandial: 餐后胰岛素
- hormone_cpeptide: C肽(C-P)
- hormone_homa_ir: 胰岛素抵抗指数(HOMA-IR)

═══════════════════════════════════════════════════════════════
【感染标志物】 infection 系列
═══════════════════════════════════════════════════════════════
- infection: 感染标志物（总项）
- infection_crp: C反应蛋白(CRP)
- infection_hscrp: 超敏C反应蛋白(hs-CRP)
- infection_pct: 降钙素原(PCT)
- infection_esr: 血沉(ESR)
- infection_il6: 白介素-6(IL-6)
- infection_saa: 血清淀粉样蛋白A(SAA)

═══════════════════════════════════════════════════════════════
【肝炎标志物】 hepatitis 系列
═══════════════════════════════════════════════════════════════
- hepatitis: 肝炎标志物（总项）
- hep_hbsag: 乙肝表面抗原(HBsAg)
- hep_hbsab: 乙肝表面抗体(HBsAb/Anti-HBs)
- hep_hbeag: 乙肝e抗原(HBeAg)
- hep_hbeab: 乙肝e抗体(HBeAb/Anti-HBe)
- hep_hbcab: 乙肝核心抗体(HBcAb/Anti-HBc)
- hep_hbvdna: 乙肝病毒DNA(HBV-DNA)
- hep_hcvab: 丙肝抗体(Anti-HCV)
- hep_hcvrna: 丙肝病毒RNA(HCV-RNA)
- hep_havab: 甲肝抗体(Anti-HAV)
- hep_hevab: 戊肝抗体(Anti-HEV)

═══════════════════════════════════════════════════════════════
【贫血相关】 anemia 系列
═══════════════════════════════════════════════════════════════
- anemia: 贫血检查（总项）
- anemia_iron: 血清铁(Fe)
- anemia_ferritin: 铁蛋白(SF)
- anemia_tibc: 总铁结合力(TIBC)
- anemia_transferrin: 转铁蛋白(TRF)
- anemia_folate: 叶酸
- anemia_b12: 维生素B12
- anemia_retic: 网织红细胞
- anemia_epo: 促红细胞生成素(EPO)

═══════════════════════════════════════════════════════════════
【骨代谢】 bone 系列
═══════════════════════════════════════════════════════════════
- bone: 骨代谢（总项）
- bone_osteocalcin: 骨钙素(OC)
- bone_pinp: I型前胶原氨基端前肽(P1NP)
- bone_ctx: I型胶原C端肽(β-CTX)
- bone_vitd: 25羟维生素D[25(OH)D]
- bone_pth: 甲状旁腺激素(PTH)
- bone_density: 骨密度(BMD)

═══════════════════════════════════════════════════════════════
【超声检查】 ultrasound/us 系列
═══════════════════════════════════════════════════════════════
- ultrasound: 超声检查（总项）
- us_liver: 肝脏超声
- us_gallbladder: 胆囊超声
- us_spleen: 脾脏超声
- us_pancreas: 胰腺超声
- us_liver_gallbladder_spleen_pancreas: 肝胆脾胰超声
- us_kidney: 肾脏超声
- us_bladder: 膀胱超声
- us_prostate: 前列腺超声
- us_urinary: 泌尿系超声
- us_uterus: 子宫超声
- us_ovary: 卵巢超声
- us_breast: 乳腺超声
- us_thyroid: 甲状腺超声
- us_carotid: 颈动脉超声
- us_cardiac: 心脏超声/心脏彩超

═══════════════════════════════════════════════════════════════
【CT检查】 ct 系列
═══════════════════════════════════════════════════════════════
- ct: CT检查（总项）
- brain_ct: 脑部CT/头颅CT
- head_ct: 头颅CT
- chest_ct: 胸部CT
- lung_ct: 肺部CT（低剂量CT筛查）
- abdominal_ct: 腹部CT
- pelvic_ct: 盆腔CT
- spine_ct: 脊柱CT
- cardiac_ct: 心脏CT
- coronary_cta: 冠状动脉CTA

═══════════════════════════════════════════════════════════════
【MRI检查】 mri 系列
═══════════════════════════════════════════════════════════════
- mri: MRI检查（总项）
- brain_mri: 脑部MRI/头颅MRI
- spine_mri: 脊柱MRI
- joint_mri: 关节MRI
- abdominal_mri: 腹部MRI
- pelvic_mri: 盆腔MRI
- cardiac_mri: 心脏MRI
- breast_mri: 乳腺MRI

═══════════════════════════════════════════════════════════════
【X光检查】 xray 系列
═══════════════════════════════════════════════════════════════
- xray: X光检查（总项）
- chest_xray: 胸部X光/胸片
- spine_xray: 脊柱X光
- joint_xray: 关节X光
- bone_xray: 骨骼X光

═══════════════════════════════════════════════════════════════
【心电/肺功能检查】 ecg/pulmonary 系列
═══════════════════════════════════════════════════════════════
- ecg: 心电图（总项）
- ecg_resting: 静息心电图
- ecg_holter: 24小时动态心电图(Holter)
- ecg_stress: 运动心电图/平板运动试验
- echocardiography: 心脏彩超/超声心动图
- pulmonary: 肺功能检查（总项）
- pulm_fvc: 用力肺活量(FVC)
- pulm_fev1: 第一秒用力呼气量(FEV1)
- pulm_fev1fvc: FEV1/FVC比值
- pulm_pef: 呼气峰流速(PEF)
- pulm_dlco: 弥散功能(DLCO)

═══════════════════════════════════════════════════════════════
【内镜检查】 endoscopy 系列
═══════════════════════════════════════════════════════════════
- endoscopy: 内镜检查（总项）
- gastroscopy: 胃镜
- colonoscopy: 肠镜
- enteroscopy: 小肠镜
- bronchoscopy: 支气管镜

═══════════════════════════════════════════════════════════════
【眼科检查】 eye 系列
═══════════════════════════════════════════════════════════════
- eye: 眼科检查（总项）
- eye_vision: 视力检查
- eye_iop: 眼压(IOP)
- eye_fundus: 眼底检查
- eye_oct: 眼底OCT
- eye_refraction: 屈光检查
- eye_slit: 裂隙灯检查
- eye_color: 色觉检查

═══════════════════════════════════════════════════════════════
【耳鼻喉科】 ent 系列
═══════════════════════════════════════════════════════════════
- ent: 耳鼻喉科检查（总项）
- ent_hearing: 听力检查/纯音测听
- ent_tympanometry: 鼓室图/声导抗
- ent_nasal: 鼻腔检查
- ent_pharynx: 咽喉检查
- ent_laryngoscopy: 喉镜检查

═══════════════════════════════════════════════════════════════
【口腔科】 dental 系列
═══════════════════════════════════════════════════════════════
- dental: 口腔科检查（总项）
- dental_teeth: 牙齿检查
- dental_gum: 牙龈检查
- dental_panoramic: 口腔全景片

═══════════════════════════════════════════════════════════════
【妇科检查】 gynecology 系列
═══════════════════════════════════════════════════════════════
- gynecology: 妇科检查（总项）
- gyn_pap: 宫颈液基细胞学(TCT)
- gyn_hpv: HPV检测
- gyn_colposcopy: 阴道镜
- gyn_mammography: 乳腺钼靶X线

═══════════════════════════════════════════════════════════════
【体格检查】 physical 系列
═══════════════════════════════════════════════════════════════
- physical: 一般检查（总项）
- physical_height: 身高
- physical_weight: 体重
- physical_bmi: 体质指数(BMI)
- physical_waist: 腰围
- physical_hip: 臀围
- physical_whr: 腰臀比
- physical_bp: 血压
- physical_pulse: 脉搏
- body_composition: 体成分分析
- physical_bodyfat: 体脂率
- physical_muscle: 肌肉量
- physical_water: 体水分

═══════════════════════════════════════════════════════════════
【临床科室检查】
═══════════════════════════════════════════════════════════════
- internal_medicine: 内科检查
- surgery: 外科检查
- neurology: 神经内科
- dermatology: 皮肤科

═══════════════════════════════════════════════════════════════
【综合/其他】
═══════════════════════════════════════════════════════════════
- biochemistry_full: 肝肾脂糖电解质测定（生化全套）
- comprehensive: 综合体检
- other: 其他无法分类的项目

注意：
1. 日期格式必须是 YYYY-MM-DD
2. value 为数字时不含单位，非数值项目使用 value_text
3. is_abnormal 根据检测值和参考范围判断
4. 尽可能提取所有检查项目，包括血常规、肝功能、免疫功能、影像学检查等
5. conclusions 提取总检结论中的各个分类（需要关注、定期随诊等）

体检报告内容：
{text}
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的医疗报告解析专家，擅长从体检报告中提取结构化数据。只返回JSON格式，不要包含任何解释性文字。"
                    },
                    {
                        "role": "user",
                        "content": prompt.format(text=text_content[:8000])  # 限制长度
                    }
                ],
                temperature=0.1,
                max_tokens=4000,
                timeout=120  # PDF解析可能需要更长时间
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("LLM返回内容为空")
            
            result_text = result_text.strip()
            logger.info(f"LLM原始返回长度: {len(result_text)}, 前500字符: {result_text[:500]}...")
            
            # 尝试提取JSON部分
            json_text = result_text
            
            # 处理markdown代码块
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                parts = json_text.split("```")
                if len(parts) >= 2:
                    json_text = parts[1]
                    # 移除可能的语言标识符
                    lines = json_text.split('\n')
                    if lines and lines[0].strip().lower() in ['json', 'javascript', 'js']:
                        json_text = '\n'.join(lines[1:])
            
            # 去除首尾空白
            json_text = json_text.strip()
            
            # 查找JSON对象的开始和结束（处理嵌套括号）
            start_idx = json_text.find('{')
            if start_idx == -1:
                raise ValueError("未找到JSON对象开始标记 '{'")
            
            # 计算匹配的结束括号
            brace_count = 0
            end_idx = -1
            for i, char in enumerate(json_text[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break
            
            if end_idx == -1:
                # 退而求其次，使用最后一个 }
                end_idx = json_text.rfind('}')
            
            if end_idx != -1 and end_idx >= start_idx:
                json_text = json_text[start_idx:end_idx + 1]
            else:
                raise ValueError("无法提取有效的JSON对象")
            
            logger.info(f"清理后的JSON长度: {len(json_text)}, 前300字符: {json_text[:300]}...")
            
            # 尝试解析JSON
            try:
                parsed_data = json.loads(json_text)
            except json.JSONDecodeError as je:
                # 尝试修复常见问题
                # 1. 移除控制字符
                import re
                cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_text)
                # 2. 修复可能的尾部逗号
                cleaned = re.sub(r',\s*}', '}', cleaned)
                cleaned = re.sub(r',\s*]', ']', cleaned)
                parsed_data = json.loads(cleaned)
            
            return parsed_data
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM返回的JSON解析失败: {e}")
            logger.error(f"原始返回内容: {result_text[:1000] if 'result_text' in locals() else 'N/A'}")
            logger.error(f"清理后内容: {json_text[:1000] if 'json_text' in locals() else 'N/A'}")
            raise ValueError(f"解析结果格式错误，请重试。详情: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"LLM解析失败: {e}", exc_info=True)
            raise ValueError(f"LLM解析失败，请重试")
    
    def parse_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """完整解析PDF体检报告"""
        # 1. 提取PDF文本
        text_content = self.extract_text_from_pdf(pdf_path)
        
        if not text_content.strip():
            raise ValueError("PDF内容为空或无法提取文本")
        
        # 2. 使用LLM解析
        parsed_data = self.parse_with_llm(text_content)
        
        # 3. 验证和清理数据
        return self._validate_and_clean(parsed_data)
    
    def _validate_and_clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证和清理解析结果"""
        # 确保必要字段存在
        if not data.get("exam_date"):
            data["exam_date"] = date.today().isoformat()
        
        if not data.get("exam_type"):
            data["exam_type"] = "other"
        
        # 清理items，并标准化项目名称
        cleaned_items = []
        item_codes = []  # 收集所有项目代码用于套餐识别
        
        for item in data.get("items", []):
            if item.get("item_name"):
                original_name = str(item["item_name"]).strip()
                
                # 尝试标准化项目名称
                item_code, standard_name = normalize_item_name(original_name)
                
                cleaned_item = {
                    "category": item.get("category") or None,
                    "item_name": standard_name,  # 使用标准化名称
                    "item_code": item_code or item.get("item_code") or None,  # 添加项目代码
                    "value": self._safe_float(item.get("value")),
                    "value_text": item.get("value_text") or None,
                    "unit": item.get("unit") or None,
                    "reference_range": item.get("reference_range") or None,
                    "is_abnormal": item.get("is_abnormal", "normal"),
                    "notes": item.get("notes") or None
                }
                cleaned_items.append(cleaned_item)
                
                if item_code:
                    item_codes.append(item_code)
        
        data["items"] = cleaned_items
        
        # 尝试识别包含的体检套餐
        if item_codes:
            matched_packages = identify_package(item_codes)
            if matched_packages:
                data["identified_packages"] = matched_packages
                logger.info(f"识别到体检套餐: {matched_packages}")
        
        return data
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# 单例实例
pdf_parser = MedicalReportPDFParser()

