export interface GeneticBoundaryInput {
  category?: string | null;
  clinical_status?: string | null;
}

export interface GeneticClinicalBoundary {
  label: string;
  text: string;
}

export const PGX_CONFIRMATION_TEXT =
  'PGx 结果只提示用药风险分层；开始、停用或调整药物前请让医生或药师结合病史和临床检测确认。';

export const GENETIC_CONFIRMATION_TEXT =
  'DTC 基因结果只作为风险提示；涉及疾病、携带状态或重要健康决策前需要临床检测确认。';

export function clinicalBoundaryForGeneticFinding(input: GeneticBoundaryInput): GeneticClinicalBoundary | null {
  const status = (input.clinical_status ?? '').toLowerCase();
  const category = (input.category ?? '').toLowerCase();

  if (status === 'pharmacogenomic_screening' || category === 'drug_sensitivity') {
    return { label: '用药确认', text: PGX_CONFIRMATION_TEXT };
  }
  if (status === 'requires_confirmation') {
    return { label: '待确认', text: GENETIC_CONFIRMATION_TEXT };
  }
  return null;
}

export function sanitizePgxTemplateLabel(label: string): string {
  if (label.includes('可使用')) {
    return '未发现此位点风险信号，仍需结合病史与医嘱';
  }
  if (label.includes('禁用')) {
    return label.replace(/禁用.*/, '用药前需医生/药师确认');
  }
  if (label.includes('需调整剂量')) {
    return label.replace(/[\s(（]*需调整剂量[)）]*/g, '，用药前需医生/药师确认');
  }
  return label;
}
