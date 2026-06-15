import { describe, expect, it } from 'vitest';

import {
  clinicalBoundaryForGeneticFinding,
  sanitizePgxTemplateLabel,
} from './geneticClinicalBoundary';

describe('geneticClinicalBoundary', () => {
  it('replaces prescription-like PGx labels with clinician-confirmation language', () => {
    expect(sanitizePgxTemplateLabel('别嘌醇可使用')).toBe('未发现此位点风险信号，仍需结合病史与医嘱');
    expect(sanitizePgxTemplateLabel('别嘌醇禁用(严重过敏)')).toBe('别嘌醇用药前需医生/药师确认');
    expect(sanitizePgxTemplateLabel('慢代谢(需调整剂量)')).toBe('慢代谢，用药前需医生/药师确认');
  });

  it('returns a PGx clinical boundary for drug sensitivity findings', () => {
    expect(clinicalBoundaryForGeneticFinding({
      category: 'drug_sensitivity',
      clinical_status: 'pharmacogenomic_screening',
    })).toEqual({
      label: '用药确认',
      text: 'PGx 结果只提示用药风险分层；开始、停用或调整药物前请让医生或药师结合病史和临床检测确认。',
    });
  });
});
