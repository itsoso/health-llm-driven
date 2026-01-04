'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

// ========== 体检套餐/组合检查 ==========
const examPackages: Record<string, { name: string; description: string; items: string[] }> = {
  // 生化全套
  biochemistry_full: {
    name: '肝肾脂糖电解质测定',
    description: '包含肝功能、肾功能、血脂、血糖、电解质全套检测',
    items: ['liver_alt', 'liver_ast', 'liver_ggt', 'liver_tbil', 'liver_alb', 'kidney_crea', 'kidney_bun', 'kidney_ua', 'lipid_tc', 'lipid_tg', 'lipid_hdl', 'lipid_ldl', 'glucose_fasting', 'electrolyte_k', 'electrolyte_na', 'electrolyte_cl', 'electrolyte_ca'],
  },
  // 糖化血红蛋白
  hba1c_test: {
    name: '糖化血红蛋白测定',
    description: '反映近2-3个月血糖控制水平',
    items: ['glucose_hba1c'],
  },
  // 粪便检查
  stool_full: {
    name: '粪便检查（常规+OB）',
    description: '粪便常规+隐血检测',
    items: ['stool_routine', 'stool_occult'],
  },
  // 载脂蛋白检测
  apolipoprotein: {
    name: '血清载脂蛋白测定',
    description: '载脂蛋白A1 + 载脂蛋白B',
    items: ['lipid_apoa1', 'lipid_apob'],
  },
  // 心肌酶谱
  cardiac_enzyme_panel: {
    name: '心肌酶谱常规检查',
    description: 'CK、CK-MB、LDH、肌红蛋白等',
    items: ['cardiac_ck', 'cardiac_ckmb', 'cardiac_ldh', 'cardiac_myo'],
  },
  // 肌钙蛋白
  troponin_i: {
    name: '血清肌钙蛋白I测定（定量）',
    description: '心肌损伤标志物，高敏定量检测',
    items: ['cardiac_tnl'],
  },
  // 肿瘤标志物套餐（男性）
  tumor_marker_male: {
    name: '肿瘤标志物套餐（男）',
    description: 'CA125+PSA+FPSA+SCC+CYFRA21-1+NSE',
    items: ['tumor_ca125', 'tumor_psa', 'tumor_fpsa', 'tumor_scc', 'tumor_cyfra211', 'tumor_nse'],
  },
  // 肿瘤标志物套餐（女性）
  tumor_marker_female: {
    name: '肿瘤标志物套餐（女）',
    description: 'CA125+CA153+SCC+CYFRA21-1+NSE+HE4',
    items: ['tumor_ca125', 'tumor_ca153', 'tumor_scc', 'tumor_cyfra211', 'tumor_nse', 'tumor_he4'],
  },
  // 胰岛素测定
  insulin_fasting: {
    name: '血清胰岛素测定（空腹）',
    description: '空腹胰岛素水平检测',
    items: ['hormone_insulin_fasting'],
  },
  // 甲状腺功能全套
  thyroid_full: {
    name: '甲状腺功能全套',
    description: 'TT3、TT4、TSH、FT3、FT4、TPOAb、TgAb',
    items: ['thyroid_t3', 'thyroid_t4', 'thyroid_tsh', 'thyroid_ft3', 'thyroid_ft4', 'thyroid_tpoab', 'thyroid_tgab'],
  },
  // 维生素D
  vitamin_d: {
    name: '25羟维生素D测定',
    description: '评估维生素D营养状态',
    items: ['bone_vitd'],
  },
  // 淋巴细胞亚群
  lymphocyte_subset: {
    name: 'CD3/4/8/16/19/45/56测定',
    description: '淋巴细胞亚群分析',
    items: ['immune_cd3', 'immune_cd4', 'immune_cd8', 'immune_cd16', 'immune_cd19', 'immune_cd45', 'immune_cd56'],
  },
  // T细胞亚型分析
  tcell_10cd: {
    name: '免疫功能T细胞亚型分析（10CD）',
    description: '全面T细胞亚群分析',
    items: ['immune_cd3', 'immune_cd4', 'immune_cd8', 'immune_cd4cd8', 'immune_cd16', 'immune_cd19', 'immune_cd45', 'immune_cd56', 'immune_nk', 'immune_bcell'],
  },
};

// 体检类型/检查类别映射（完整版）
const examTypeLabels: Record<string, string> = {
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

// 身体系统映射
const bodySystemLabels: Record<string, string> = {
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

// 异常状态样式
const abnormalStyles: Record<string, string> = {
  normal: 'bg-green-100 text-green-800',
  abnormal: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  low: 'bg-blue-100 text-blue-800',
};

const abnormalLabels: Record<string, string> = {
  normal: '正常',
  abnormal: '异常',
  high: '偏高',
  low: '偏低',
};

interface MedicalExamItem {
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

interface Conclusion {
  type?: string;
  category?: string;
  title?: string;
  description?: string;
  recommendation?: string;
  recommendations?: string;
}

interface MedicalExam {
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

function MedicalExamsContent() {
  const { user } = useAuth();
  const userId = user?.id || 1;
  const [showForm, setShowForm] = useState(false);
  const [showPdfUpload, setShowPdfUpload] = useState(false);
  const [expandedExam, setExpandedExam] = useState<number | null>(null);
  const [showItemForm, setShowItemForm] = useState(false);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfPreview, setPdfPreview] = useState<any>(null);
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const queryClient = useQueryClient();
  const today = format(new Date(), 'yyyy-MM-dd');

  const [formData, setFormData] = useState({
    exam_date: today,
    exam_type: 'blood_routine',
    body_system: '',
    hospital_name: '',
    doctor_name: '',
    overall_assessment: '',
    notes: '',
  });

  const [items, setItems] = useState<Array<{
    item_name: string;
    value: string;
    unit: string;
    reference_range: string;
    is_abnormal: string;
    notes: string;
  }>>([]);

  const [newItem, setNewItem] = useState({
    item_name: '',
    value: '',
    unit: '',
    reference_range: '',
    is_abnormal: 'normal',
    notes: '',
  });

  const [selectedPackage, setSelectedPackage] = useState<string>('');

  // 获取体检记录
  const { data: examsResponse, isLoading } = useQuery({
    queryKey: ['medical-exams', userId],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/medical-exams/user/${userId}`);
      return res.json();
    },
  });

  const exams: MedicalExam[] = Array.isArray(examsResponse) ? examsResponse : [];

  // 创建体检记录
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/medical-exams/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('创建失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['medical-exams'] });
      setShowForm(false);
      setFormData({
        exam_date: today,
        exam_type: 'blood_routine',
        body_system: '',
        hospital_name: '',
        doctor_name: '',
        overall_assessment: '',
        notes: '',
      });
      setItems([]);
      alert('✅ 体检记录创建成功！');
    },
    onError: () => {
      alert('❌ 创建失败，请重试');
    },
  });

  // PDF预览解析
  const previewPdfMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/medical-exams/parse-pdf-preview`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '解析失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      setPdfPreview(data);
      setUploadProgress('解析完成，请确认结果');
    },
    onError: (error: any) => {
      setUploadProgress('');
      alert(`❌ PDF解析失败: ${error.message}`);
    },
  });

  // PDF上传导入
  const uploadPdfMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/medical-exams/import/pdf?user_id=${userId}`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '导入失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['medical-exams'] });
      setShowPdfUpload(false);
      setPdfFile(null);
      setPdfPreview(null);
      setUploadProgress('');
      alert(`✅ PDF导入成功！已解析 ${data.items_count} 个检查项目`);
    },
    onError: (error: any) => {
      alert(`❌ PDF导入失败: ${error.message}`);
    },
  });

  const handlePdfSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('请选择PDF格式文件');
        return;
      }
      setPdfFile(file);
      setPdfPreview(null);
      setUploadProgress('正在解析PDF...');
      previewPdfMutation.mutate(file);
    }
  };

  const handlePdfImport = () => {
    if (pdfFile) {
      setUploadProgress('正在导入...');
      uploadPdfMutation.mutate(pdfFile);
    }
  };

  const handleAddItem = () => {
    if (!newItem.item_name) {
      alert('请输入检查项目名称');
      return;
    }
    setItems([...items, { ...newItem }]);
    setNewItem({
      item_name: '',
      value: '',
      unit: '',
      reference_range: '',
      is_abnormal: 'normal',
      notes: '',
    });
    setShowItemForm(false);
  };

  const handleRemoveItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      user_id: userId,
      exam_date: formData.exam_date,
      exam_type: formData.exam_type,
      body_system: formData.body_system || null,
      hospital_name: formData.hospital_name || null,
      doctor_name: formData.doctor_name || null,
      overall_assessment: formData.overall_assessment || null,
      notes: formData.notes || null,
      items: items.map((item) => ({
        item_name: item.item_name,
        value: item.value ? parseFloat(item.value) : null,
        unit: item.unit || null,
        reference_range: item.reference_range || null,
        is_abnormal: item.is_abnormal,
        notes: item.notes || null,
      })),
    });
  };

  // 统计异常项目数量
  const getAbnormalCount = (exam: MedicalExam) => {
    return exam.items.filter((item) => item.is_abnormal && item.is_abnormal !== 'normal').length;
  };

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-800 text-lg font-medium">加载中...</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <p className="text-gray-600 text-sm">管理您的体检报告和检查项目</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => { setShowPdfUpload(!showPdfUpload); setShowForm(false); }}
              className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-600 hover:to-pink-700 shadow-md transition-all flex items-center gap-2"
            >
              📄 {showPdfUpload ? '取消上传' : '上传PDF'}
            </button>
            <button
              onClick={() => { setShowForm(!showForm); setShowPdfUpload(false); }}
              className="px-4 py-2 bg-gradient-to-r from-teal-500 to-cyan-600 text-white font-semibold rounded-lg hover:from-teal-600 hover:to-cyan-700 shadow-md transition-all"
            >
            {showForm ? '取消' : '+ 添加体检记录'}
            </button>
          </div>
        </div>

        {/* PDF上传区域 */}
        {showPdfUpload && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-purple-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">📄 上传体检报告PDF</h3>
            <p className="text-gray-600 text-sm mb-4">
              上传体检报告PDF文件，系统将使用AI自动解析并提取检查项目数据。
            </p>
            
            {/* 文件选择 */}
            <div className="border-2 border-dashed border-purple-300 rounded-lg p-8 text-center mb-4 hover:border-purple-500 transition-colors">
              <input
                type="file"
                accept=".pdf"
                onChange={handlePdfSelect}
                className="hidden"
                id="pdf-upload"
              />
              <label htmlFor="pdf-upload" className="cursor-pointer">
                <div className="text-5xl mb-3">📁</div>
                <p className="text-gray-700 font-medium mb-2">
                  {pdfFile ? pdfFile.name : '点击或拖拽PDF文件到这里'}
                </p>
                <p className="text-gray-500 text-sm">支持 .pdf 格式</p>
              </label>
            </div>

            {/* 进度提示 */}
            {uploadProgress && (
              <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200 text-blue-800">
                <div className="flex items-center gap-2">
                  {(previewPdfMutation.isPending || uploadPdfMutation.isPending) && (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                  )}
                  {uploadProgress}
                </div>
              </div>
            )}

            {/* 预览结果 */}
            {pdfPreview && (
              <div className="mb-4">
                <h4 className="font-bold text-gray-800 mb-3">📋 解析预览</h4>
                
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">体检日期</div>
                    <div className="font-medium text-gray-900">{pdfPreview.parsed_data?.exam_date || '-'}</div>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">体检类型</div>
                    <div className="font-medium text-gray-900">{examTypeLabels[pdfPreview.parsed_data?.exam_type] || '-'}</div>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">医院</div>
                    <div className="font-medium text-gray-900">{pdfPreview.parsed_data?.hospital_name || '-'}</div>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">检查项目</div>
                    <div className="font-medium text-gray-900">{pdfPreview.parsed_data?.items?.length || 0} 项</div>
                  </div>
                </div>

                {/* 项目预览列表 */}
                {pdfPreview.parsed_data?.items?.length > 0 && (
                  <div className="max-h-60 overflow-y-auto border border-gray-200 rounded-lg">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-100 sticky top-0">
                        <tr>
                          <th className="text-left p-2 font-semibold text-gray-700">项目</th>
                          <th className="text-right p-2 font-semibold text-gray-700">检测值</th>
                          <th className="text-left p-2 font-semibold text-gray-700">单位</th>
                          <th className="text-left p-2 font-semibold text-gray-700">参考范围</th>
                          <th className="text-center p-2 font-semibold text-gray-700">状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pdfPreview.parsed_data.items.map((item: any, idx: number) => (
                          <tr key={idx} className="border-b border-gray-100">
                            <td className="p-2 text-gray-900">{item.item_name}</td>
                            <td className="p-2 text-right font-mono text-gray-900">{item.value ?? '-'}</td>
                            <td className="p-2 text-gray-600">{item.unit || '-'}</td>
                            <td className="p-2 text-gray-600">{item.reference_range || '-'}</td>
                            <td className="p-2 text-center">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${abnormalStyles[item.is_abnormal || 'normal']}`}>
                                {abnormalLabels[item.is_abnormal || 'normal']}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {pdfPreview.parsed_data?.overall_assessment && (
                  <div className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-100">
                    <div className="text-sm font-semibold text-blue-800 mb-1">总体评价</div>
                    <div className="text-gray-800 text-sm">{pdfPreview.parsed_data.overall_assessment}</div>
                  </div>
                )}
              </div>
            )}

            {/* 操作按钮 */}
            {pdfPreview && (
              <div className="flex gap-3">
                <button
                  onClick={handlePdfImport}
                  disabled={uploadPdfMutation.isPending}
                  className="flex-1 py-3 bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-600 hover:to-pink-700 disabled:opacity-50 shadow-md"
                >
                  {uploadPdfMutation.isPending ? '导入中...' : '✓ 确认导入'}
                </button>
                <button
                  onClick={() => { setPdfFile(null); setPdfPreview(null); setUploadProgress(''); }}
                  className="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300"
                >
                  重新选择
                </button>
              </div>
            )}
          </div>
        )}

        {/* 统计卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl shadow-md border border-teal-100">
            <p className="text-sm text-gray-600 mb-1">总体检次数</p>
            <p className="text-3xl font-bold text-teal-600">{exams.length}</p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-blue-100">
            <p className="text-sm text-gray-600 mb-1">检查项目</p>
            <p className="text-3xl font-bold text-blue-600">
              {exams.reduce((sum, exam) => sum + exam.items.length, 0)}
            </p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-orange-100">
            <p className="text-sm text-gray-600 mb-1">异常项目</p>
            <p className="text-3xl font-bold text-orange-600">
              {exams.reduce((sum, exam) => sum + getAbnormalCount(exam), 0)}
            </p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-green-100">
            <p className="text-sm text-gray-600 mb-1">最近体检</p>
            <p className="text-lg font-bold text-green-600">
              {exams.length > 0 ? exams[0].exam_date : '-'}
            </p>
          </div>
        </div>

        {/* 添加体检记录表单 */}
        {showForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-teal-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">🏥 添加体检记录</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* 基本信息 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">体检日期 *</label>
                  <input
                    type="date"
                    required
                    value={formData.exam_date}
                    onChange={(e) => setFormData({ ...formData, exam_date: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">体检类型 *</label>
                  <select
                    required
                    value={formData.exam_type}
                    onChange={(e) => setFormData({ ...formData, exam_type: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
                  >
                    {Object.entries(examTypeLabels).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">身体系统</label>
                  <select
                    value={formData.body_system}
                    onChange={(e) => setFormData({ ...formData, body_system: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
                  >
                    <option value="">选择系统</option>
                    {Object.entries(bodySystemLabels).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* 体检套餐快速选择 */}
              <div className="border border-purple-200 rounded-lg p-4 bg-purple-50">
                <label className="block text-sm font-semibold text-purple-800 mb-3">🧪 体检套餐（快速添加检查项目）</label>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                  {Object.entries(examPackages).map(([key, pkg]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => {
                        // 添加套餐中的所有项目
                        const newItems = pkg.items.map(itemKey => ({
                          item_name: examTypeLabels[itemKey] || itemKey,
                          value: '',
                          unit: '',
                          reference_range: '',
                          is_abnormal: 'normal',
                          notes: '',
                        }));
                        setItems([...items, ...newItems]);
                        setSelectedPackage(key);
                      }}
                      className={`px-3 py-2 text-xs rounded-lg border transition-all text-left ${
                        selectedPackage === key
                          ? 'bg-purple-600 text-white border-purple-600'
                          : 'bg-white text-purple-700 border-purple-300 hover:bg-purple-100'
                      }`}
                    >
                      <div className="font-medium">{pkg.name}</div>
                      <div className="text-[10px] opacity-75 truncate">{pkg.description}</div>
                    </button>
                  ))}
                </div>
                <p className="text-xs text-purple-600 mt-2">💡 点击套餐可快速添加相关检查项目到列表</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">医院名称</label>
                  <input
                    type="text"
                    value={formData.hospital_name}
                    onChange={(e) => setFormData({ ...formData, hospital_name: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
                    placeholder="例如：北京协和医院"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">医生姓名</label>
                  <input
                    type="text"
                    value={formData.doctor_name}
                    onChange={(e) => setFormData({ ...formData, doctor_name: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
                    placeholder="例如：张医生"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">总体评价</label>
                <textarea
                  value={formData.overall_assessment}
                  onChange={(e) => setFormData({ ...formData, overall_assessment: e.target.value })}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
                  rows={2}
                  placeholder="医生对本次体检的总体评价..."
                />
              </div>

              {/* 检查项目 */}
              <div className="border-t pt-4">
                <div className="flex justify-between items-center mb-3">
                  <h4 className="font-bold text-gray-800">📋 检查项目 ({items.length}项)</h4>
                  <button
                    type="button"
                    onClick={() => setShowItemForm(true)}
                    className="px-3 py-1 bg-teal-100 text-teal-700 rounded-lg hover:bg-teal-200 text-sm font-medium"
                  >
                    + 添加项目
                  </button>
                </div>

                {/* 添加项目表单 */}
                {showItemForm && (
                  <div className="bg-gray-50 p-4 rounded-lg mb-4 border border-gray-200">
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
                      <div>
                        <label className="block text-xs font-semibold text-gray-700 mb-1">项目名称 *</label>
                        <input
                          type="text"
                          value={newItem.item_name}
                          onChange={(e) => setNewItem({ ...newItem, item_name: e.target.value })}
                          className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                          placeholder="例如：血红蛋白"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-gray-700 mb-1">检测值</label>
                        <input
                          type="number"
                          step="0.01"
                          value={newItem.value}
                          onChange={(e) => setNewItem({ ...newItem, value: e.target.value })}
                          className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                          placeholder="例如：145"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-gray-700 mb-1">单位</label>
                        <input
                          type="text"
                          value={newItem.unit}
                          onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })}
                          className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                          placeholder="例如：g/L"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-gray-700 mb-1">参考范围</label>
                        <input
                          type="text"
                          value={newItem.reference_range}
                          onChange={(e) => setNewItem({ ...newItem, reference_range: e.target.value })}
                          className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                          placeholder="例如：130-175"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-gray-700 mb-1">结果状态</label>
                        <select
                          value={newItem.is_abnormal}
                          onChange={(e) => setNewItem({ ...newItem, is_abnormal: e.target.value })}
                          className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                        >
                          <option value="normal">正常</option>
                          <option value="high">偏高</option>
                          <option value="low">偏低</option>
                          <option value="abnormal">异常</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-gray-700 mb-1">备注</label>
                        <input
                          type="text"
                          value={newItem.notes}
                          onChange={(e) => setNewItem({ ...newItem, notes: e.target.value })}
                          className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                          placeholder="可选备注"
                        />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={handleAddItem}
                        className="px-3 py-1 bg-teal-600 text-white rounded text-sm hover:bg-teal-700"
                      >
                        确认添加
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowItemForm(false)}
                        className="px-3 py-1 bg-gray-300 text-gray-700 rounded text-sm hover:bg-gray-400"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}

                {/* 已添加的项目列表 */}
                {items.length > 0 && (
                  <div className="space-y-2">
                    {items.map((item, index) => (
                      <div key={index} className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
                        <div className="flex items-center gap-4">
                          <span className="font-medium text-gray-900">{item.item_name}</span>
                          {item.value && (
                            <span className="text-gray-600">
                              {item.value} {item.unit}
                            </span>
                          )}
                          {item.reference_range && (
                            <span className="text-xs text-gray-500">参考: {item.reference_range}</span>
                          )}
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${abnormalStyles[item.is_abnormal]}`}>
                            {abnormalLabels[item.is_abnormal]}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleRemoveItem(index)}
                          className="text-red-500 hover:text-red-700"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">备注</label>
                <textarea
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
                  rows={2}
                  placeholder="其他备注信息..."
                />
              </div>

              <button
                type="submit"
                disabled={createMutation.isPending}
                className="w-full py-3 bg-gradient-to-r from-teal-500 to-cyan-600 text-white font-semibold rounded-lg hover:from-teal-600 hover:to-cyan-700 disabled:opacity-50 shadow-md"
              >
                {createMutation.isPending ? '保存中...' : '保存体检记录'}
              </button>
            </form>
          </div>
        )}

        {/* 体检记录列表 */}
        <div className="space-y-4">
          {exams.length === 0 ? (
            <div className="bg-white rounded-xl shadow-md p-12 text-center">
              <div className="text-6xl mb-4">🏥</div>
              <h3 className="text-xl font-bold text-gray-800 mb-2">暂无体检记录</h3>
              <p className="text-gray-600">点击上方按钮添加您的第一条体检记录</p>
            </div>
          ) : (
            exams.map((exam) => (
              <div key={exam.id} className="bg-white rounded-xl shadow-md border border-gray-100 overflow-hidden">
                {/* 记录头部 */}
                <div
                  className="p-4 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => setExpandedExam(expandedExam === exam.id ? null : exam.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-teal-100 rounded-xl flex items-center justify-center">
                        <span className="text-2xl">🩺</span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-gray-900">{exam.exam_date}</span>
                          {exam.patient_name && (
                            <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-sm font-medium">
                              👤 {exam.patient_name}
                            </span>
                          )}
                          <span className="px-2 py-0.5 bg-teal-100 text-teal-700 rounded text-sm font-medium">
                            {examTypeLabels[exam.exam_type?.toLowerCase()] || exam.exam_type}
                          </span>
                          {exam.body_system && (
                            <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-sm">
                              {bodySystemLabels[exam.body_system?.toLowerCase()] || exam.body_system}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-600 mt-1">
                          {exam.hospital_name && <span>{exam.hospital_name}</span>}
                          {exam.doctor_name && <span className="ml-2">• {exam.doctor_name}</span>}
                          <span className="ml-2">• {exam.items.length} 项检查</span>
                          {getAbnormalCount(exam) > 0 && (
                            <span className="ml-2 text-orange-600 font-medium">
                              ⚠️ {getAbnormalCount(exam)} 项异常
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="text-gray-400 text-2xl">
                      {expandedExam === exam.id ? '▲' : '▼'}
                    </div>
                  </div>
                </div>

                {/* 展开的详情 */}
                {expandedExam === exam.id && (
                  <div className="border-t border-gray-100 p-4 bg-gray-50">
                    {/* 患者信息 */}
                    {(exam.patient_name || exam.patient_gender || exam.patient_age || exam.exam_number) && (
                      <div className="mb-4 p-3 bg-purple-50 rounded-lg border border-purple-100">
                        <div className="text-sm font-semibold text-purple-800 mb-2">👤 患者信息</div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                          {exam.patient_name && (
                            <div><span className="text-gray-500">姓名:</span> <span className="text-gray-900 font-medium">{exam.patient_name}</span></div>
                          )}
                          {exam.patient_gender && (
                            <div><span className="text-gray-500">性别:</span> <span className="text-gray-900">{exam.patient_gender}</span></div>
                          )}
                          {exam.patient_age && (
                            <div><span className="text-gray-500">年龄:</span> <span className="text-gray-900">{exam.patient_age}岁</span></div>
                          )}
                          {exam.exam_number && (
                            <div><span className="text-gray-500">体检号:</span> <span className="text-gray-900">{exam.exam_number}</span></div>
                          )}
                        </div>
                      </div>
                    )}

                    {exam.overall_assessment && (
                      <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-100">
                        <div className="text-sm font-semibold text-blue-800 mb-1">📋 总体评价</div>
                        <div className="text-gray-800">{exam.overall_assessment}</div>
                      </div>
                    )}

                    {/* 结论建议 */}
                    {exam.conclusions && exam.conclusions.length > 0 && (
                      <div className="mb-4 p-3 bg-amber-50 rounded-lg border border-amber-200">
                        <div className="text-sm font-semibold text-amber-800 mb-2">⚠️ 检查结论与建议</div>
                        <div className="space-y-2">
                          {exam.conclusions.map((conclusion, idx) => {
                            const category = conclusion.category || conclusion.type || '';
                            const title = conclusion.title || '';
                            const rec = conclusion.recommendations || conclusion.recommendation || '';
                            return (
                              <div key={idx} className="p-3 bg-white rounded border border-amber-100">
                                <div className="flex items-start gap-2 mb-1">
                                  {category && (
                                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium shrink-0 ${
                                      category.includes('attention') || category.includes('关注') ? 'bg-red-100 text-red-700' :
                                      category.includes('followup') || category.includes('随诊') ? 'bg-yellow-100 text-yellow-700' :
                                      'bg-blue-100 text-blue-700'
                                    }`}>
                                      {category.includes('attention') ? '需要关注' :
                                       category.includes('followup') ? '定期随诊' :
                                       category}
                                    </span>
                                  )}
                                  {title && (
                                    <span className="font-semibold text-gray-800">{title}</span>
                                  )}
                                </div>
                                {conclusion.description && (
                                  <div className="text-gray-700 text-sm mb-1">{conclusion.description}</div>
                                )}
                                {rec && (
                                  <div className="text-teal-700 text-sm bg-teal-50 p-2 rounded mt-2">
                                    💡 <span className="font-medium">建议:</span> {rec}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {exam.items.length > 0 ? (
                      <div>
                        <h4 className="font-bold text-gray-800 mb-3">检查项目明细</h4>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="bg-gray-100">
                                <th className="text-left p-2 font-semibold text-gray-700">类别</th>
                                <th className="text-left p-2 font-semibold text-gray-700">项目名称</th>
                                <th className="text-right p-2 font-semibold text-gray-700">检测值</th>
                                <th className="text-left p-2 font-semibold text-gray-700">单位</th>
                                <th className="text-left p-2 font-semibold text-gray-700">参考范围</th>
                                <th className="text-center p-2 font-semibold text-gray-700">状态</th>
                              </tr>
                            </thead>
                            <tbody>
                              {exam.items.map((item) => (
                                <tr key={item.id} className="border-b border-gray-100 hover:bg-white">
                                  <td className="p-2 text-gray-500 text-xs">
                                    {examTypeLabels[item.category?.toLowerCase() || ''] || item.category || '-'}
                                  </td>
                                  <td className="p-2 font-medium text-gray-900">{item.item_name}</td>
                                  <td className="p-2 text-right font-mono text-gray-900">
                                    {item.value !== null && item.value !== undefined 
                                      ? item.value 
                                      : item.value_text || '-'}
                                  </td>
                                  <td className="p-2 text-gray-600">{item.unit || '-'}</td>
                                  <td className="p-2 text-gray-600">{item.reference_range || '-'}</td>
                                  <td className="p-2 text-center">
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${abnormalStyles[item.is_abnormal || 'normal']}`}>
                                      {abnormalLabels[item.is_abnormal || 'normal']}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : (
                      <p className="text-gray-500 text-center py-4">暂无检查项目明细</p>
                    )}

                    {exam.notes && (
                      <div className="mt-4 p-3 bg-yellow-50 rounded-lg border border-yellow-100">
                        <div className="text-sm font-semibold text-yellow-800 mb-1">📝 备注</div>
                        <div className="text-gray-800">{exam.notes}</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function MedicalExamsPage() {
  return (
    <ProtectedRoute>
      <MedicalExamsContent />
    </ProtectedRoute>
  );
}

