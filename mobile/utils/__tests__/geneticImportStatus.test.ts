import {
  geneticImportStatusView,
  isTerminalGeneticImportStatus,
} from '../geneticImportStatus';

describe('geneticImportStatusView', () => {
  it('treats queued imports as active work instead of failure', () => {
    const view = geneticImportStatusView({
      id: 12,
      status: 'queued',
      variant_count: 0,
      import_job: { status: 'queued' },
    });

    expect(view).toMatchObject({
      phase: 'pending',
      label: '排队中',
      terminal: false,
    });
  });

  it('formats completed coverage and hides raw rsid lists', () => {
    const view = geneticImportStatusView({
      id: 12,
      status: 'done',
      variant_count: 5,
      import_job: { status: 'done', matched_count: 5, unmapped_count: 99, missing_count: 47 },
      coverage: {
        known_total: 52,
        present: 5,
        missing: 47,
        missing_by_rsids: { rs999: 'not_in_raw_file' },
      },
    });

    expect(view.detail).toBe('已提取 5 个健康相关位点。');
    expect(view.coverageLine).toBe('覆盖 5/52 个已知健康位点，缺失 47 个；原始文件未映射 99 条。');
    expect(view.coverageLine).not.toContain('rs999');
    expect(isTerminalGeneticImportStatus(view)).toBe(true);
  });
});
