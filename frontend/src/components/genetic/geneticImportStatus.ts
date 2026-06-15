export type GeneticImportPhase = 'pending' | 'running' | 'complete' | 'failed' | 'unknown';
export type GeneticImportTone = 'amber' | 'teal' | 'red' | 'gray';

export interface GeneticImportJobPayload {
  status?: string | null;
  matched_count?: number | null;
  unmapped_count?: number | null;
  missing_count?: number | null;
  error_message?: string | null;
}

export interface GeneticImportCoveragePayload {
  known_total?: number | null;
  present?: number | null;
  missing?: number | null;
  missing_by_reason?: Record<string, number> | null;
  missing_by_rsids?: Record<string, string> | null;
}

export interface GeneticProfileStatusPayload {
  id: number;
  status?: string | null;
  variant_count?: number | null;
  notes?: string | null;
  import_job?: GeneticImportJobPayload | null;
  coverage?: GeneticImportCoveragePayload | null;
}

export interface GeneticImportStatusView {
  phase: GeneticImportPhase;
  label: string;
  detail: string;
  terminal: boolean;
  tone: GeneticImportTone;
  coverageLine?: string;
}

export function geneticImportStatusView(payload: GeneticProfileStatusPayload): GeneticImportStatusView {
  const rawStatus = normalizeStatus(payload.import_job?.status ?? payload.status);
  const variantCount = numberOrZero(payload.variant_count ?? payload.import_job?.matched_count);
  const matchedCount = numberOrZero(payload.import_job?.matched_count ?? payload.variant_count);
  const phase = phaseForStatus(rawStatus, variantCount);
  const coverageLine = coverageSummary(payload.coverage, payload.import_job);
  const failureMessage = cleanText(payload.import_job?.error_message) || cleanText(payload.notes);

  if (phase === 'failed') {
    return {
      phase,
      label: '解析失败',
      detail: failureMessage || '未能完成结构化解析，请换用原始 TXT 数据或稍后重试。',
      terminal: true,
      tone: 'red',
      coverageLine,
    };
  }

  if (phase === 'complete') {
    const count = Math.max(variantCount, matchedCount);
    return {
      phase,
      label: '解析完成',
      detail: count > 0 ? `已提取 ${count} 个健康相关位点。` : '解析完成，但未匹配到已知健康位点。',
      terminal: true,
      tone: 'teal',
      coverageLine,
    };
  }

  if (phase === 'pending') {
    return {
      phase,
      label: '排队中',
      detail: '文件已收到，等待后台解析。',
      terminal: false,
      tone: 'amber',
      coverageLine,
    };
  }

  if (phase === 'running') {
    return {
      phase,
      label: '解析中',
      detail: variantCount > 0
        ? `已提取 ${variantCount} 个位点，仍在整理覆盖率。`
        : '后台正在提取基因位点，通常需要 1-3 分钟。',
      terminal: false,
      tone: 'amber',
      coverageLine,
    };
  }

  return {
    phase,
    label: '状态未知',
    detail: '导入任务状态暂时不可识别，请稍后刷新。',
    terminal: false,
    tone: 'gray',
    coverageLine,
  };
}

export function isTerminalGeneticImportStatus(view: Pick<GeneticImportStatusView, 'terminal'>): boolean {
  return view.terminal;
}

function normalizeStatus(status: string | null | undefined): string {
  return (status || '').trim().toLowerCase();
}

function phaseForStatus(status: string, variantCount: number): GeneticImportPhase {
  if (status === 'queued') return 'pending';
  if (['processing', 'running', 'started'].includes(status)) return 'running';
  if (['done', 'complete', 'completed', 'succeeded', 'success'].includes(status)) return 'complete';
  if (['failed', 'error'].includes(status)) return 'failed';
  if (!status && variantCount > 0) return 'complete';
  if (!status) return 'running';
  return 'unknown';
}

function coverageSummary(
  coverage: GeneticImportCoveragePayload | null | undefined,
  job: GeneticImportJobPayload | null | undefined,
): string | undefined {
  const knownTotal = positiveNumberOrNull(coverage?.known_total);
  const present = nonNegativeNumberOrNull(coverage?.present ?? job?.matched_count);
  const missing = nonNegativeNumberOrNull(coverage?.missing ?? job?.missing_count);
  const unmapped = nonNegativeNumberOrNull(job?.unmapped_count);
  const parts: string[] = [];

  if (knownTotal !== null && present !== null) {
    const missingPart = missing !== null ? `，缺失 ${missing} 个` : '';
    parts.push(`覆盖 ${present}/${knownTotal} 个已知健康位点${missingPart}`);
  } else if (present !== null) {
    parts.push(`匹配 ${present} 个已知健康位点`);
  }

  if (unmapped !== null && unmapped > 0) {
    parts.push(`原始文件未映射 ${unmapped} 条`);
  }

  if (parts.length === 0) return undefined;
  return `${parts.join('；')}。`;
}

function numberOrZero(value: number | null | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function positiveNumberOrNull(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;
}

function nonNegativeNumberOrNull(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function cleanText(value: string | null | undefined): string {
  return (value || '').trim();
}
