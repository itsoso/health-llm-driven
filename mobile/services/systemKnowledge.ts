import api from './api';

export interface KnowledgeDocument {
  doc_id: string;
  doc_type?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  title?: string | null;
  summary?: string | null;
  body?: string | null;
  confidence?: number | null;
  evidence_level?: string | null;
  evidence_level_detail?: {
    level?: string | null;
    label?: string | null;
    description?: string | null;
  } | null;
  applies_when?: string[];
  recommends_lookup?: string[];
  sources?: string[];
  source_details?: KnowledgeSourceDetail[];
  source_groups?: KnowledgeSourceGroup[];
  last_confirmed?: string | null;
  decay_rate?: string | null;
  metadata?: Record<string, any>;
}

export interface KnowledgeSourceDetail {
  source: string;
  kind?: string | null;
  label?: string | null;
  trust_tier?: string | null;
  display_name?: string | null;
}

export interface KnowledgeSourceGroup {
  kind: string;
  label?: string | null;
  trust_tier?: string | null;
  count: number;
  sources: KnowledgeSourceDetail[];
}

export interface KnowledgeClaimBundle {
  claim: KnowledgeDocument;
  neighbors?: KnowledgeDocument[];
  edges?: any[];
  claim_boundary?: string;
}

export interface KnowledgeEntityBundle {
  entity: KnowledgeDocument;
  linked_claims?: KnowledgeDocument[];
  edges?: any[];
  claim_boundary?: string;
}

export async function getKnowledgeClaim(claimId: string): Promise<KnowledgeClaimBundle> {
  const encoded = encodeURIComponent(claimId);
  const res = await api.get(`/knowledge/claim/${encoded}`);
  return res.data;
}

export async function getKnowledgeEntity(
  entityType: string,
  entityId: string,
): Promise<KnowledgeEntityBundle> {
  const encoded = encodeURIComponent(entityId);
  const res = await api.get(`/knowledge/entity/${entityType}/${encoded}`);
  return res.data;
}

export async function submitKnowledgeClaimFeedback(
  claimId: string,
  reason?: string,
): Promise<{ ok: boolean; claim_id?: string; op?: string }> {
  const encoded = encodeURIComponent(claimId);
  const res = await api.post(`/knowledge/claim/${encoded}/feedback`, {
    feedback: 'disagree',
    reason,
  });
  return res.data;
}
