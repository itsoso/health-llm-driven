import {
  geneticClinicalBoundary,
  geneticRiskBadgeOverride,
} from '../geneticClinicalBoundary';

describe('geneticClinicalBoundary', () => {
  it('marks pharmacogenomic screening as medication confirmation instead of a prescription decision', () => {
    expect(geneticRiskBadgeOverride({
      category: 'drug_sensitivity',
      clinical_status: 'pharmacogenomic_screening',
    })).toEqual({ bg: '#FFEDD5', text: '#9A3412', label: '用药确认' });

    expect(geneticClinicalBoundary({
      category: 'drug_sensitivity',
      clinical_status: 'pharmacogenomic_screening',
    })).toBe('PGx 结果只提示用药风险分层；开始、停用或调整药物前请让医生或药师结合病史和临床检测确认。');
  });
});
