import { describe, expect, it } from 'vitest';

import {
  geneticImportStatusView,
  isTerminalGeneticImportStatus,
} from './geneticImportStatus';

describe('geneticImportStatusView', () => {
  it('maps queued and processing jobs to non-terminal user-facing states', () => {
    expect(geneticImportStatusView({
      id: 7,
      status: 'queued',
      variant_count: 0,
      import_job: { status: 'queued' },
    })).toMatchObject({
      phase: 'pending',
      label: '排队中',
      terminal: false,
    });

    expect(geneticImportStatusView({
      id: 7,
      status: 'processing',
      variant_count: 3,
      import_job: { status: 'processing', matched_count: 3 },
    })).toMatchObject({
      phase: 'running',
      label: '解析中',
      terminal: false,
      detail: '已提取 3 个位点，仍在整理覆盖率。',
    });
  });

  it('summarizes completed coverage without exposing raw missing-rsid lists', () => {
    const view = geneticImportStatusView({
      id: 7,
      status: 'done',
      variant_count: 12,
      import_job: {
        status: 'done',
        matched_count: 12,
        unmapped_count: 18176,
        missing_count: 1198,
      },
      coverage: {
        known_total: 1210,
        present: 12,
        missing: 1198,
        missing_by_rsids: {
          rs123: 'not_in_raw_file',
        },
      },
    });

    expect(view).toMatchObject({
      phase: 'complete',
      label: '解析完成',
      terminal: true,
      detail: '已提取 12 个健康相关位点。',
      coverageLine: '覆盖 12/1210 个已知健康位点，缺失 1198 个；原始文件未映射 18176 条。',
    });
    expect(view.coverageLine).not.toContain('rs123');
    expect(isTerminalGeneticImportStatus(view)).toBe(true);
  });

  it('surfaces failed import errors as terminal states', () => {
    const view = geneticImportStatusView({
      id: 7,
      status: 'failed',
      variant_count: 0,
      notes: 'PDF 提取失败',
      import_job: { status: 'failed', error_message: 'LLM timeout' },
    });

    expect(view).toMatchObject({
      phase: 'failed',
      label: '解析失败',
      terminal: true,
      detail: 'LLM timeout',
    });
  });
});
