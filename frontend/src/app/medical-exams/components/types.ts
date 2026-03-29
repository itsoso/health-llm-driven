export interface MedicalExamItem {
  id: number;
  category?: string;
  item_name: string;
  item_code?: string;
  value?: number;
  value_text?: string;
  unit?: string;
  reference_range?: string;
  result?: string;
  is_abnormal?: string;
  notes?: string;
}

export interface Conclusion {
  type?: string;
  category?: string;
  title?: string;
  description?: string;
  recommendation?: string;
  recommendations?: string;
}

export interface MedicalExam {
  id: number;
  user_id: number;
  patient_name?: string;
  patient_gender?: string;
  patient_age?: number;
  exam_number?: string;
  exam_date: string;
  exam_type: string;
  body_system?: string;
  hospital_name?: string;
  doctor_name?: string;
  overall_assessment?: string;
  conclusions?: Conclusion[];
  notes?: string;
  created_at?: string;
  items: MedicalExamItem[];
}

// 异常状态样式
export const abnormalStyles: Record<string, string> = {
  normal: 'bg-green-100 text-green-800',
  abnormal: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  low: 'bg-blue-100 text-blue-800',
};

export const abnormalLabels: Record<string, string> = {
  normal: '正常',
  abnormal: '异常',
  high: '偏高',
  low: '偏低',
};

// 身体系统映射
export const bodySystemLabels: Record<string, string> = {
  nervous: '神经系统',
  circulatory: '循环系统',
  respiratory: '呼吸系统',
  digestive: '消化系统',
  urinary: '泌尿系统',
  endocrine: '内分泌系统',
  immune: '免疫系统',
  skeletal: '骨骼系统',
  muscular: '肌肉系统',
  other: '其他',
};

// 体检类型/检查类别映射（完整版）
export const examTypeLabels: Record<string, string> = {
  // ========== 血液检查 ==========
  blood_routine: '血常规',
  blood_routine_wbc: '白细胞',
  blood_routine_rbc: '红细胞',
  blood_routine_hgb: '血红蛋白',
  blood_routine_plt: '血小板',
  blood_routine_neut: '中性粒细胞',
  blood_routine_lymph: '淋巴细胞',
  blood_routine_mono: '单核细胞',
  blood_routine_eos: '嗜酸性粒细胞',
  blood_routine_baso: '嗜碱性粒细胞',

  // ========== 血脂检查 ==========
  lipid_profile: '血脂',
  lipid_tc: '总胆固醇',
  lipid_tg: '甘油三酯',
  lipid_hdl: '高密度脂蛋白',
  lipid_ldl: '低密度脂蛋白',
  lipid_vldl: '极低密度脂蛋白',
  lipid_apoa: '载脂蛋白A',
  lipid_apoa1: '载脂蛋白A1',
  lipid_apob: '载脂蛋白B',
  lipid_lpa: '脂蛋白a',
  lipid_sdldl: '小而密低密度脂蛋白',

  // ========== 血糖检查 ==========
  blood_glucose: '血糖',
  glucose_fasting: '空腹血糖',
  glucose_postprandial: '餐后血糖',
  glucose_hba1c: '糖化血红蛋白',
  glucose_ogtt: '糖耐量试验',
  glucose_ga: '糖化白蛋白',

  // ========== 尿液检查 ==========
  urine_routine: '尿常规',
  urine_protein: '尿蛋白',
  urine_glucose: '尿糖',
  urine_blood: '尿隐血',
  urine_wbc: '尿白细胞',
  urine_microalbumin: '尿微量白蛋白',

  // ========== 大便检查 ==========
  stool_routine: '大便常规',
  stool_occult: '大便隐血',

  // ========== 肝功能 ==========
  liver_function: '肝功能',
  liver_alt: '谷丙转氨酶(ALT)',
  liver_ast: '谷草转氨酶(AST)',
  liver_ggt: '谷氨酰转肽酶(GGT)',
  liver_alp: '碱性磷酸酶(ALP)',
  liver_tbil: '总胆红素',
  liver_dbil: '直接胆红素',
  liver_ibil: '间接胆红素',
  liver_tp: '总蛋白',
  liver_alb: '白蛋白',
  liver_glob: '球蛋白',
  liver_ag_ratio: '白球比',

  // ========== 肾功能 ==========
  kidney_function: '肾功能',
  kidney_crea: '肌酐',
  kidney_bun: '尿素氮',
  kidney_ua: '尿酸',
  kidney_cystc: '胱抑素C',
  kidney_egfr: '肾小球滤过率',
  kidney_b2m: 'β2微球蛋白',

  // ========== 电解质 ==========
  electrolyte: '电解质',
  electrolyte_k: '钾',
  electrolyte_na: '钠',
  electrolyte_cl: '氯',
  electrolyte_ca: '钙',
  electrolyte_mg: '镁',
  electrolyte_p: '磷',
  electrolyte_co2: '二氧化碳结合力',

  // ========== 心肌酶谱 ==========
  cardiac_enzyme: '心肌酶谱',
  cardiac_ck: '肌酸激酶(CK)',
  cardiac_ckmb: '肌酸激酶同工酶(CK-MB)',
  cardiac_ldh: '乳酸脱氢酶(LDH)',
  cardiac_tnl: '肌钙蛋白I',
  cardiac_tnt: '肌钙蛋白T',
  cardiac_bnp: 'B型钠尿肽(BNP)',
  cardiac_ntprobnp: 'NT-proBNP',
  cardiac_myo: '肌红蛋白',

  // ========== 凝血功能 ==========
  coagulation: '凝血功能',
  coag_pt: '凝血酶原时间(PT)',
  coag_inr: '国际标准化比值(INR)',
  coag_aptt: '活化部分凝血活酶时间(APTT)',
  coag_tt: '凝血酶时间(TT)',
  coag_fib: '纤维蛋白原',
  coag_ddimer: 'D-二聚体',

  // ========== 免疫功能 ==========
  immune: '免疫功能',
  immune_cd3: 'CD3+T细胞',
  immune_cd4: 'CD4+T细胞',
  immune_cd8: 'CD8+T细胞',
  immune_cd4cd8: 'CD4/CD8比值',
  immune_cd16: 'CD16+细胞',
  immune_cd19: 'CD19+B细胞',
  immune_cd45: 'CD45+细胞',
  immune_cd56: 'CD56+NK细胞',
  immune_nk: 'NK细胞(CD16+CD56+)',
  immune_bcell: 'B淋巴细胞',
  immune_tcell_10cd: 'T细胞亚型(10CD)',
  immune_lymph_subset: '淋巴细胞亚群分析',
  immune_iga: '免疫球蛋白A(IgA)',
  immune_igg: '免疫球蛋白G(IgG)',
  immune_igm: '免疫球蛋白M(IgM)',
  immune_ige: '免疫球蛋白E(IgE)',
  immune_c3: '补体C3',
  immune_c4: '补体C4',

  // ========== 肿瘤标志物 ==========
  tumor_marker: '肿瘤标志物',
  tumor_afp: '甲胎蛋白(AFP)',
  tumor_cea: '癌胚抗原(CEA)',
  tumor_ca199: 'CA19-9',
  tumor_ca125: 'CA125',
  tumor_ca153: 'CA15-3',
  tumor_ca724: 'CA72-4',
  tumor_psa: '前列腺特异抗原(PSA)',
  tumor_fpsa: '游离PSA',
  tumor_nsclc: '非小细胞肺癌抗原',
  tumor_scc: '鳞状细胞癌抗原(SCC)',
  tumor_cyfra211: '细胞角蛋白19片段',
  tumor_ferritin: '铁蛋白',
  tumor_nse: '神经元特异性烯醇化酶(NSE)',
  tumor_progrp: '胃泌素释放肽前体',
  tumor_tpsa: '总PSA',
  tumor_he4: 'HE4',
  tumor_roma: 'ROMA指数',

  // ========== 自身免疫 ==========
  autoimmune: '自身免疫抗体',
  auto_ana: '抗核抗体(ANA)',
  auto_dsdna: '抗双链DNA抗体',
  auto_ena: '抗可提取核抗原抗体(ENA)',
  auto_rf: '类风湿因子(RF)',
  auto_ccp: '抗环瓜氨酸肽抗体(CCP)',
  auto_anca: '抗中性粒细胞胞浆抗体(ANCA)',
  auto_gpc: '抗胃壁细胞抗体',
  auto_tpo: '抗甲状腺过氧化物酶抗体(TPO)',
  auto_tg: '抗甲状腺球蛋白抗体(TG)',

  // ========== 甲状腺功能 ==========
  thyroid: '甲状腺功能',
  thyroid_tsh: '促甲状腺激素(TSH)',
  thyroid_ft3: '游离T3(FT3)',
  thyroid_ft4: '游离T4(FT4)',
  thyroid_t3: '总T3',
  thyroid_t4: '总T4',
  thyroid_tgab: '甲状腺球蛋白抗体(TgAb)',
  thyroid_tpoab: '甲状腺过氧化物酶抗体(TPOAb)',
  thyroid_trab: '促甲状腺受体抗体(TRAb)',
  thyroid_tg: '甲状腺球蛋白(Tg)',
  thyroid_ct: '降钙素(CT)',

  // ========== 性激素 ==========
  hormone: '激素检查',
  hormone_fsh: '卵泡刺激素(FSH)',
  hormone_lh: '黄体生成素(LH)',
  hormone_e2: '雌二醇(E2)',
  hormone_prog: '孕酮(P)',
  hormone_test: '睾酮(T)',
  hormone_prl: '泌乳素(PRL)',
  hormone_dheas: '硫酸脱氢表雄酮',
  hormone_cortisol: '皮质醇',
  hormone_acth: '促肾上腺皮质激素',
  hormone_gh: '生长激素',
  hormone_igf1: '胰岛素样生长因子-1',
  hormone_insulin_fasting: '空腹胰岛素',
  hormone_insulin_postprandial: '餐后胰岛素',
  hormone_cpeptide: 'C肽',
  hormone_homa_ir: 'HOMA-IR指数',

  // ========== 感染标志物 ==========
  infection: '感染标志物',
  infection_crp: 'C反应蛋白(CRP)',
  infection_hscrp: '超敏C反应蛋白',
  infection_pct: '降钙素原(PCT)',
  infection_esr: '血沉(ESR)',
  infection_il6: '白介素-6',

  // ========== 肝炎标志物 ==========
  hepatitis: '肝炎标志物',
  hep_hbsag: '乙肝表面抗原(HBsAg)',
  hep_hbsab: '乙肝表面抗体(HBsAb)',
  hep_hbeag: '乙肝e抗原(HBeAg)',
  hep_hbeab: '乙肝e抗体(HBeAb)',
  hep_hbcab: '乙肝核心抗体(HBcAb)',
  hep_hbvdna: '乙肝病毒DNA',
  hep_hcvab: '丙肝抗体(HCVAb)',
  hep_hcvrna: '丙肝病毒RNA',
  hep_havab: '甲肝抗体',
  hep_hevab: '戊肝抗体',

  // ========== 贫血相关 ==========
  anemia: '贫血检查',
  anemia_iron: '血清铁',
  anemia_ferritin: '铁蛋白',
  anemia_tibc: '总铁结合力',
  anemia_transferrin: '转铁蛋白',
  anemia_folate: '叶酸',
  anemia_b12: '维生素B12',
  anemia_retic: '网织红细胞',
  anemia_epo: '促红细胞生成素',

  // ========== 骨代谢 ==========
  bone: '骨代谢',
  bone_osteocalcin: '骨钙素',
  bone_pinp: 'P1NP',
  bone_ctx: 'β-CTX',
  bone_vitd: '25羟维生素D',
  bone_pth: '甲状旁腺激素(PTH)',
  bone_density: '骨密度',

  // ========== 超声检查 ==========
  ultrasound: '超声检查',
  us_liver: '肝脏超声',
  us_gallbladder: '胆囊超声',
  us_spleen: '脾脏超声',
  us_pancreas: '胰腺超声',
  us_kidney: '肾脏超声',
  us_bladder: '膀胱超声',
  us_prostate: '前列腺超声',
  us_uterus: '子宫超声',
  us_ovary: '卵巢超声',
  us_breast: '乳腺超声',
  us_thyroid: '甲状腺超声',
  us_carotid: '颈动脉超声',
  us_cardiac: '心脏超声',
  us_abdominal: '腹部超声',
  us_urinary: '泌尿系超声',

  // ========== CT检查 ==========
  ct: 'CT检查',
  brain_ct: '脑部CT',
  head_ct: '头颅CT',
  chest_ct: '胸部CT',
  lung_ct: '肺部CT',
  abdominal_ct: '腹部CT',
  pelvic_ct: '盆腔CT',
  spine_ct: '脊柱CT',
  cardiac_ct: '心脏CT',
  coronary_cta: '冠脉CTA',

  // ========== MRI检查 ==========
  mri: 'MRI检查',
  brain_mri: '脑部MRI',
  spine_mri: '脊柱MRI',
  joint_mri: '关节MRI',
  abdominal_mri: '腹部MRI',
  pelvic_mri: '盆腔MRI',
  cardiac_mri: '心脏MRI',
  breast_mri: '乳腺MRI',

  // ========== X光检查 ==========
  xray: 'X光检查',
  chest_xray: '胸片',
  spine_xray: '脊柱X光',
  joint_xray: '关节X光',
  bone_xray: '骨骼X光',

  // ========== 心电检查 ==========
  ecg: '心电图',
  ecg_resting: '静息心电图',
  ecg_holter: '动态心电图(Holter)',
  ecg_stress: '运动心电图',
  echocardiography: '心脏彩超',

  // ========== 肺功能 ==========
  pulmonary: '肺功能',
  pulm_fvc: '用力肺活量(FVC)',
  pulm_fev1: '一秒用力呼气量(FEV1)',
  pulm_fev1fvc: 'FEV1/FVC',
  pulm_pef: '呼气峰流速',
  pulm_dlco: '弥散功能',

  // ========== 胃肠镜 ==========
  endoscopy: '内镜检查',
  gastroscopy: '胃镜',
  colonoscopy: '肠镜',
  enteroscopy: '小肠镜',

  // ========== 眼科检查 ==========
  eye: '眼科检查',
  eye_vision: '视力',
  eye_iop: '眼压',
  eye_fundus: '眼底检查',
  eye_oct: '眼底OCT',
  eye_refraction: '屈光检查',
  eye_slit: '裂隙灯检查',
  eye_color: '色觉检查',

  // ========== 耳鼻喉科 ==========
  ent: '耳鼻喉科',
  ent_hearing: '听力检查',
  ent_tympanometry: '鼓室图',
  ent_nasal: '鼻腔检查',
  ent_pharynx: '咽喉检查',
  ent_laryngoscopy: '喉镜检查',

  // ========== 口腔科 ==========
  dental: '口腔科',
  dental_teeth: '牙齿检查',
  dental_gum: '牙龈检查',
  dental_xray: '口腔X光',

  // ========== 妇科检查 ==========
  gynecology: '妇科检查',
  gyn_pap: '宫颈涂片(TCT)',
  gyn_hpv: 'HPV检测',
  gyn_colposcopy: '阴道镜',
  gyn_mammography: '乳腺钼靶',

  // ========== 体格检查 ==========
  body_composition: '体成分分析',
  physical: '一般检查',
  physical_height: '身高',
  physical_weight: '体重',
  physical_bmi: 'BMI',
  physical_waist: '腰围',
  physical_hip: '臀围',
  physical_bp: '血压',
  physical_pulse: '脉搏',
  physical_bodyfat: '体脂率',

  internal_medicine: '内科检查',
  surgery: '外科检查',
  neurology: '神经内科',
  dermatology: '皮肤科',

  // ========== 其他 ==========
  comprehensive: '综合体检',
  other: '其他',
};

// ========== 体检套餐/组合检查 ==========
export const examPackages: Record<string, { name: string; description: string; items: string[] }> = {
  biochemistry_full: {
    name: '肝肾脂糖电解质测定',
    description: '包含肝功能、肾功能、血脂、血糖、电解质全套检测',
    items: ['liver_alt', 'liver_ast', 'liver_ggt', 'liver_tbil', 'liver_alb', 'kidney_crea', 'kidney_bun', 'kidney_ua', 'lipid_tc', 'lipid_tg', 'lipid_hdl', 'lipid_ldl', 'glucose_fasting', 'electrolyte_k', 'electrolyte_na', 'electrolyte_cl', 'electrolyte_ca'],
  },
  hba1c_test: {
    name: '糖化血红蛋白测定',
    description: '反映近2-3个月血糖控制水平',
    items: ['glucose_hba1c'],
  },
  stool_full: {
    name: '粪便检查（常规+OB）',
    description: '粪便常规+隐血检测',
    items: ['stool_routine', 'stool_occult'],
  },
  apolipoprotein: {
    name: '血清载脂蛋白测定',
    description: '载脂蛋白A1 + 载脂蛋白B',
    items: ['lipid_apoa1', 'lipid_apob'],
  },
  cardiac_enzyme_panel: {
    name: '心肌酶谱常规检查',
    description: 'CK、CK-MB、LDH、肌红蛋白等',
    items: ['cardiac_ck', 'cardiac_ckmb', 'cardiac_ldh', 'cardiac_myo'],
  },
  troponin_i: {
    name: '血清肌钙蛋白I测定（定量）',
    description: '心肌损伤标志物，高敏定量检测',
    items: ['cardiac_tnl'],
  },
  tumor_marker_male: {
    name: '肿瘤标志物套餐（男）',
    description: 'CA125+PSA+FPSA+SCC+CYFRA21-1+NSE',
    items: ['tumor_ca125', 'tumor_psa', 'tumor_fpsa', 'tumor_scc', 'tumor_cyfra211', 'tumor_nse'],
  },
  tumor_marker_female: {
    name: '肿瘤标志物套餐（女）',
    description: 'CA125+CA153+SCC+CYFRA21-1+NSE+HE4',
    items: ['tumor_ca125', 'tumor_ca153', 'tumor_scc', 'tumor_cyfra211', 'tumor_nse', 'tumor_he4'],
  },
  insulin_fasting: {
    name: '血清胰岛素测定（空腹）',
    description: '空腹胰岛素水平检测',
    items: ['hormone_insulin_fasting'],
  },
  thyroid_full: {
    name: '甲状腺功能全套',
    description: 'TT3、TT4、TSH、FT3、FT4、TPOAb、TgAb',
    items: ['thyroid_t3', 'thyroid_t4', 'thyroid_tsh', 'thyroid_ft3', 'thyroid_ft4', 'thyroid_tpoab', 'thyroid_tgab'],
  },
  vitamin_d: {
    name: '25羟维生素D测定',
    description: '评估维生素D营养状态',
    items: ['bone_vitd'],
  },
  lymphocyte_subset: {
    name: 'CD3/4/8/16/19/45/56测定',
    description: '淋巴细胞亚群分析',
    items: ['immune_cd3', 'immune_cd4', 'immune_cd8', 'immune_cd16', 'immune_cd19', 'immune_cd45', 'immune_cd56'],
  },
  tcell_10cd: {
    name: '免疫功能T细胞亚型分析（10CD）',
    description: '全面T细胞亚群分析',
    items: ['immune_cd3', 'immune_cd4', 'immune_cd8', 'immune_cd4cd8', 'immune_cd16', 'immune_cd19', 'immune_cd45', 'immune_cd56', 'immune_nk', 'immune_bcell'],
  },
};
