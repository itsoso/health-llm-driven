import { extractPhenoAge } from '../twinHelpers';

describe('extractPhenoAge', () => {
  it('ok: 有 phenotypic_age → 提取数字/delta/chrono/claim_boundary', () => {
    const twin = {
      labs: {
        phenotypic_age: 41.68,
        phenotypic_age_delta_years: -8.32,
        phenoage_claim_boundary: '基于血检的代理指标,不作诊断。',
      },
    };
    const v = extractPhenoAge(twin);
    expect(v.status).toBe('ok');
    expect(v.phenotypicAge).toBeCloseTo(41.7, 1);
    expect(v.deltaYears).toBeCloseTo(-8.32, 2);
    expect(v.chronoAge).toBeCloseTo(50, 1); // 41.68 - (-8.32) = 50
    expect(v.claimBoundary).toContain('不作诊断');
    expect(v.missingLabels).toEqual([]);
  });

  it('incomplete: 无 phenotypic_age → 列出缺失血检项', () => {
    const twin = {
      labs: {
        albumin: 45,
        creatinine: 80,
        blood_glucose: 5.0,
        // 缺 crp/lymphocyte_pct/mcv/rdw/alp/wbc
      },
    };
    const v = extractPhenoAge(twin);
    expect(v.status).toBe('incomplete');
    expect(v.phenotypicAge).toBeNull();
    expect(v.missingLabels).toContain('CRP');
    expect(v.missingLabels).toContain('白细胞');
    expect(v.missingLabels).not.toContain('白蛋白'); // 已有
    expect(v.missingLabels.length).toBe(6);
  });

  it('incomplete: labs 全空 → 9 项全缺', () => {
    const v = extractPhenoAge({ labs: {} });
    expect(v.status).toBe('incomplete');
    expect(v.missingLabels.length).toBe(9);
  });

  it('健壮性: twin/labs 为空不崩', () => {
    expect(extractPhenoAge(undefined).status).toBe('incomplete');
    expect(extractPhenoAge({}).status).toBe('incomplete');
    expect(extractPhenoAge(null).missingLabels.length).toBe(9);
  });

  it('phenotypic_age 非有限值 → 当作 incomplete', () => {
    expect(extractPhenoAge({ labs: { phenotypic_age: null } }).status).toBe('incomplete');
    expect(extractPhenoAge({ labs: { phenotypic_age: NaN } }).status).toBe('incomplete');
  });
});
