export type ReviewStatus = '' | 'draft' | 'reviewed' | 'needs_review' | 'archived';
export type EvidenceLevel = '' | 'A' | 'B' | 'C' | 'D';

export interface ClaimReviewFormState {
  reviewStatus: ReviewStatus;
  evidenceLevel: EvidenceLevel;
  confidence: string;
  sourceKind: string;
  source: string;
  sourceTitle: string;
  sourceUrl: string;
  clearCandidateDuplicates: boolean;
  resolveFeedback: boolean;
  note: string;
}

export interface ClaimReviewPayload {
  review_status?: Exclude<ReviewStatus, ''>;
  evidence_level?: Exclude<EvidenceLevel, ''>;
  confidence?: number;
  external_source?: {
    kind?: string;
    source: string;
    title?: string;
    url?: string;
  };
  clear_candidate_duplicates?: boolean;
  resolve_feedback?: boolean;
  note?: string;
}

const REASON_LABELS: Record<string, string> = {
  draft: '草稿待审',
  needs_review: '需要复核',
  missing_external_evidence: '缺少外部证据',
  candidate_duplicate: '候选重复',
  user_feedback: '用户反馈',
};

export function reasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

export function buildClaimReviewPayload(form: ClaimReviewFormState): ClaimReviewPayload {
  const payload: ClaimReviewPayload = {};

  if (form.reviewStatus) {
    payload.review_status = form.reviewStatus;
  }
  if (form.evidenceLevel) {
    payload.evidence_level = form.evidenceLevel;
  }

  const confidence = Number.parseFloat(form.confidence);
  if (Number.isFinite(confidence)) {
    payload.confidence = Math.min(1, Math.max(0, Number(confidence.toFixed(4))));
  }

  const source = form.source.trim();
  if (source) {
    const externalSource: ClaimReviewPayload['external_source'] = { source };
    const kind = form.sourceKind.trim();
    const title = form.sourceTitle.trim();
    const url = form.sourceUrl.trim();
    if (kind) externalSource.kind = kind;
    if (title) externalSource.title = title;
    if (url) externalSource.url = url;
    payload.external_source = externalSource;
  }

  if (form.clearCandidateDuplicates) {
    payload.clear_candidate_duplicates = true;
  }
  if (form.resolveFeedback) {
    payload.resolve_feedback = true;
  }

  const note = form.note.trim();
  if (note) {
    payload.note = note;
  }

  return payload;
}
