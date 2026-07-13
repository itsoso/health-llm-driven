import { describe, expect, it } from 'vitest';

import {
  buildAdjudicationPayload,
  canFinalizeReleaseReview,
  decisionLabel,
  isStaleWorkspaceError,
} from '../dedaoReleaseReview';

describe('Dedao Release Review helpers', () => {
  it('builds a trimmed approve payload with structured evidence', () => {
    expect(
      buildAdjudicationPayload({
        workspaceFingerprint: 'a'.repeat(64),
        decision: 'approve',
        note: '  二源核验后通过  ',
        evidenceLevel: 'B',
        confidence: '0.84',
        evidenceKind: ' research ',
        evidenceSource: ' pubmed:12345 ',
        evidenceTitle: ' Caffeine and sleep ',
        evidenceUrl: ' https://pubmed.ncbi.nlm.nih.gov/12345/ ',
      }),
    ).toEqual({
      workspace_fingerprint: 'a'.repeat(64),
      decision: 'approve',
      note: '二源核验后通过',
      evidence_level: 'B',
      confidence: 0.84,
      evidence: {
        kind: 'research',
        source: 'pubmed:12345',
        title: 'Caffeine and sleep',
        url: 'https://pubmed.ncbi.nlm.nih.gov/12345/',
      },
    });
  });

  it('omits approve-only fields for a blocking decision', () => {
    expect(
      buildAdjudicationPayload({
        workspaceFingerprint: 'b'.repeat(64),
        decision: 'needs_evidence',
        note: '需要独立来源',
        evidenceLevel: 'B',
        confidence: '0.9',
        evidenceKind: 'research',
        evidenceSource: 'pubmed:12345',
        evidenceTitle: '',
        evidenceUrl: '',
      }),
    ).toEqual({
      workspace_fingerprint: 'b'.repeat(64),
      decision: 'needs_evidence',
      note: '需要独立来源',
    });
  });

  it('only enables finalization after every release claim is resolved', () => {
    expect(canFinalizeReleaseReview({ total: 5, unresolvedCount: 1 })).toBe(false);
    expect(canFinalizeReleaseReview({ total: 5, unresolvedCount: 0 })).toBe(true);
    expect(canFinalizeReleaseReview({ total: 0, unresolvedCount: 0 })).toBe(true);
  });

  it('labels decisions and recognizes stale fingerprint conflicts', () => {
    expect(decisionLabel('background_only')).toBe('仅作背景');
    expect(isStaleWorkspaceError({ response: { status: 409 } })).toBe(true);
    expect(isStaleWorkspaceError({ response: { status: 400 } })).toBe(false);
  });
});
