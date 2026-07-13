export type DedaoClaimDecision = 'approve' | 'needs_evidence' | 'reject' | 'background_only';

export interface AdjudicationFormState {
  workspaceFingerprint: string;
  decision: DedaoClaimDecision;
  note: string;
  evidenceLevel: '' | 'A' | 'B' | 'C' | 'D';
  confidence: string;
  evidenceKind: string;
  evidenceSource: string;
  evidenceTitle: string;
  evidenceUrl: string;
}

export interface AdjudicationPayload {
  workspace_fingerprint: string;
  decision: DedaoClaimDecision;
  note?: string;
  evidence_level?: 'A' | 'B' | 'C' | 'D';
  confidence?: number;
  evidence?: {
    kind?: string;
    source: string;
    title?: string;
    url?: string;
  };
}

const DECISION_LABELS: Record<DedaoClaimDecision, string> = {
  approve: '批准',
  needs_evidence: '待补证据',
  reject: '拒绝',
  background_only: '仅作背景',
};

export function decisionLabel(decision: DedaoClaimDecision): string {
  return DECISION_LABELS[decision];
}

export function buildAdjudicationPayload(form: AdjudicationFormState): AdjudicationPayload {
  const payload: AdjudicationPayload = {
    workspace_fingerprint: form.workspaceFingerprint,
    decision: form.decision,
  };
  const note = form.note.trim();
  if (note) payload.note = note;
  if (form.decision !== 'approve') return payload;

  if (form.evidenceLevel) payload.evidence_level = form.evidenceLevel;
  const confidence = Number.parseFloat(form.confidence);
  if (Number.isFinite(confidence)) payload.confidence = Math.min(1, Math.max(0, confidence));

  const source = form.evidenceSource.trim();
  if (source) {
    const evidence: NonNullable<AdjudicationPayload['evidence']> = { source };
    const kind = form.evidenceKind.trim();
    const title = form.evidenceTitle.trim();
    const url = form.evidenceUrl.trim();
    if (kind) evidence.kind = kind;
    if (title) evidence.title = title;
    if (url) evidence.url = url;
    payload.evidence = evidence;
  }
  return payload;
}

export function canFinalizeReleaseReview({
  total,
  unresolvedCount,
}: {
  total: number;
  unresolvedCount: number;
}): boolean {
  return total > 0 && unresolvedCount === 0;
}

export function isStaleWorkspaceError(error: unknown): boolean {
  return (error as { response?: { status?: number } })?.response?.status === 409;
}
