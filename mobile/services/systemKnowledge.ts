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
  applies_when?: string[];
  recommends_lookup?: string[];
  sources?: string[];
  last_confirmed?: string | null;
  decay_rate?: string | null;
  metadata?: Record<string, any>;
}

export interface KnowledgeClaimBundle {
  claim: KnowledgeDocument;
  neighbors?: KnowledgeDocument[];
  edges?: any[];
  claim_boundary?: string;
}

export async function getKnowledgeClaim(claimId: string): Promise<KnowledgeClaimBundle> {
  const encoded = encodeURIComponent(claimId);
  const res = await api.get(`/knowledge/claim/${encoded}`);
  return res.data;
}
