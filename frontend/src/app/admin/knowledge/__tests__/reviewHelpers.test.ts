import { describe, expect, it } from 'vitest';

import { buildClaimReviewPayload, reasonLabel } from '../reviewHelpers';

describe('knowledge review helpers', () => {
  it('builds a reviewed payload with an external evidence source', () => {
    const payload = buildClaimReviewPayload({
      reviewStatus: 'reviewed',
      evidenceLevel: 'B',
      confidence: '0.82',
      sourceKind: 'research',
      source: 'pubmed:19033271',
      sourceTitle: 'MTHFR C677T folate metabolism',
      sourceUrl: 'https://pubmed.ncbi.nlm.nih.gov/19033271/',
      clearCandidateDuplicates: true,
      resolveFeedback: true,
      note: '补充 PubMed 二源后通过审核',
    });

    expect(payload).toEqual({
      review_status: 'reviewed',
      evidence_level: 'B',
      confidence: 0.82,
      external_source: {
        kind: 'research',
        source: 'pubmed:19033271',
        title: 'MTHFR C677T folate metabolism',
        url: 'https://pubmed.ncbi.nlm.nih.gov/19033271/',
      },
      clear_candidate_duplicates: true,
      resolve_feedback: true,
      note: '补充 PubMed 二源后通过审核',
    });
  });

  it('omits empty optional fields and clamps invalid confidence', () => {
    const payload = buildClaimReviewPayload({
      reviewStatus: '',
      evidenceLevel: '',
      confidence: '1.7',
      sourceKind: 'research',
      source: '',
      sourceTitle: '',
      sourceUrl: '',
      clearCandidateDuplicates: false,
      resolveFeedback: false,
      note: '',
    });

    expect(payload).toEqual({ confidence: 1 });
  });

  it('maps queue reason codes to stable Chinese labels', () => {
    expect(reasonLabel('missing_external_evidence')).toBe('缺少外部证据');
    expect(reasonLabel('candidate_duplicate')).toBe('候选重复');
    expect(reasonLabel('unknown_reason')).toBe('unknown_reason');
  });
});
