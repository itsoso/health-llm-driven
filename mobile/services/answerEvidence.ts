export type AnswerEvidenceFreshness = 'current' | 'recent' | 'stale' | 'unknown';
export type AnswerEvidenceConfidence = 'high' | 'medium' | 'low' | 'unknown';

export interface AnswerEvidenceBasis {
  id: string;
  label: string;
  observation: string;
  context?: string;
  source: string;
  purpose?: string;
  observedAt?: string;
  freshness?: AnswerEvidenceFreshness;
  confidence?: AnswerEvidenceConfidence;
}

export interface AnswerEvidenceLimitation {
  id: string;
  title: string;
  detail?: string;
  handling: string;
}

export interface AnswerEvidence {
  version: 'answer-evidence.v1';
  summary: string;
  basis: AnswerEvidenceBasis[];
  limitations: AnswerEvidenceLimitation[];
}

const TOP_LEVEL_KEYS = new Set(['version', 'summary', 'basis', 'limitations']);
const BASIS_KEYS = new Set([
  'id', 'label', 'observation', 'context', 'source', 'purpose',
  'observed_at', 'freshness', 'confidence',
]);
const LIMITATION_KEYS = new Set(['id', 'title', 'detail', 'handling']);
const FRESHNESS = new Set<AnswerEvidenceFreshness>(['current', 'recent', 'stale', 'unknown']);
const CONFIDENCE = new Set<AnswerEvidenceConfidence>(['high', 'medium', 'low', 'unknown']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: Set<string>): boolean {
  return Object.keys(value).every(key => allowed.has(key));
}

function boundedText(value: unknown, maxLength = 180): string | undefined {
  if (typeof value !== 'string') return undefined;
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) return undefined;
  return normalized.slice(0, maxLength);
}

function normalizeBasis(value: unknown): AnswerEvidenceBasis | undefined {
  if (!isRecord(value) || !hasOnlyKeys(value, BASIS_KEYS)) return undefined;
  const id = boundedText(value.id);
  const label = boundedText(value.label);
  const observation = boundedText(value.observation);
  const source = boundedText(value.source);
  if (!id || !label || !observation || !source) return undefined;

  const item: AnswerEvidenceBasis = { id, label, observation, source };
  const context = boundedText(value.context);
  const purpose = boundedText(value.purpose);
  const observedAt = boundedText(value.observed_at);
  if (context) item.context = context;
  if (purpose) item.purpose = purpose;
  if (observedAt) item.observedAt = observedAt;
  if (value.freshness !== undefined) {
    if (!FRESHNESS.has(value.freshness as AnswerEvidenceFreshness)) return undefined;
    item.freshness = value.freshness as AnswerEvidenceFreshness;
  }
  if (value.confidence !== undefined) {
    if (!CONFIDENCE.has(value.confidence as AnswerEvidenceConfidence)) return undefined;
    item.confidence = value.confidence as AnswerEvidenceConfidence;
  }
  return item;
}

function normalizeLimitation(value: unknown): AnswerEvidenceLimitation | undefined {
  if (!isRecord(value) || !hasOnlyKeys(value, LIMITATION_KEYS)) return undefined;
  const id = boundedText(value.id);
  const title = boundedText(value.title);
  const handling = boundedText(value.handling);
  if (!id || !title || !handling) return undefined;
  const item: AnswerEvidenceLimitation = { id, title, handling };
  const detail = boundedText(value.detail);
  if (detail) item.detail = detail;
  return item;
}

export function normalizeAnswerEvidence(value: unknown): AnswerEvidence | undefined {
  if (!isRecord(value) || !hasOnlyKeys(value, TOP_LEVEL_KEYS)) return undefined;
  if (value.version !== 'answer-evidence.v1') return undefined;
  const summary = boundedText(value.summary, 120);
  if (!summary || !Array.isArray(value.basis) || !Array.isArray(value.limitations)) {
    return undefined;
  }
  if (value.basis.length > 4 || value.limitations.length > 3) return undefined;
  const basis = value.basis.map(normalizeBasis);
  const limitations = value.limitations.map(normalizeLimitation);
  if (basis.some(item => !item) || limitations.some(item => !item)) return undefined;
  return {
    version: 'answer-evidence.v1',
    summary,
    basis: basis as AnswerEvidenceBasis[],
    limitations: limitations as AnswerEvidenceLimitation[],
  };
}
