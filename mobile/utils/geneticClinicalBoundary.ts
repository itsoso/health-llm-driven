export interface GeneticBoundaryInput {
  category?: string | null;
  clinical_status?: string | null;
}

export interface GeneticRiskBadge {
  bg: string;
  text: string;
  label: string;
}

export const PGX_CONFIRMATION_TEXT =
  'PGx 结果只提示用药风险分层；开始、停用或调整药物前请让医生或药师结合病史和临床检测确认。';

export const GENETIC_CONFIRMATION_TEXT =
  'DTC 基因结果只作为风险提示；涉及疾病、携带状态或重要健康决策前需要临床检测确认。';

export function geneticClinicalBoundary(input: GeneticBoundaryInput): string | null {
  const status = (input.clinical_status ?? '').toLowerCase();
  const category = (input.category ?? '').toLowerCase();
  if (status === 'pharmacogenomic_screening' || category === 'drug_sensitivity') {
    return PGX_CONFIRMATION_TEXT;
  }
  if (status === 'requires_confirmation') {
    return GENETIC_CONFIRMATION_TEXT;
  }
  return null;
}

export function geneticRiskBadgeOverride(input: GeneticBoundaryInput): GeneticRiskBadge | null {
  const status = (input.clinical_status ?? '').toLowerCase();
  const category = (input.category ?? '').toLowerCase();
  if (status === 'pharmacogenomic_screening' || category === 'drug_sensitivity') {
    return { bg: '#FFEDD5', text: '#9A3412', label: '用药确认' };
  }
  if (status === 'requires_confirmation') {
    return { bg: '#E0F2FE', text: '#075985', label: '待确认' };
  }
  return null;
}
