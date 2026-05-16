import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { colors } from '../../../constants/theme';
import type { CardSpec } from './types';

interface KnowledgeClaim {
  title?: string;
  evidence_level?: string | null;
  confidence?: number | null;
  sources?: string[];
}

interface KnowledgeEvidenceData {
  entity?: {
    title?: string;
    entity_id?: string;
    entity_type?: string;
  };
  claims?: KnowledgeClaim[];
  claim_boundary?: string;
}

function evidenceLabel(level?: string | null) {
  if (!level) return '证据';
  return `${String(level).toUpperCase()}级`;
}

export function SystemKnowledgeEvidenceCardView({
  entity,
  claims = [],
  claim_boundary,
}: KnowledgeEvidenceData) {
  const firstClaim = claims[0];
  const title = entity?.title || entity?.entity_id || '系统知识库';
  const sources = firstClaim?.sources?.slice(0, 3) || [];

  return (
    <CardShell
      icon="library"
      iconColor="#0A84FF"
      title={title}
      badge={evidenceLabel(firstClaim?.evidence_level)}
      badgeColor="#0A84FF"
      bg="#F4F8FF"
    >
      {firstClaim?.title ? (
        <Text style={txt.claimTitle} numberOfLines={2}>{firstClaim.title}</Text>
      ) : null}

      {typeof firstClaim?.confidence === 'number' ? (
        <View style={styles.confidenceRow}>
          <Ionicons name="shield-checkmark-outline" size={12} color="#0A84FF" />
          <Text style={txt.meta}>置信度 {Math.round(firstClaim.confidence * 100)}%</Text>
        </View>
      ) : null}

      {sources.length > 0 ? (
        <View style={styles.sources}>
          {sources.map((source) => (
            <View key={source} style={styles.sourceChip}>
              <Ionicons name="document-text-outline" size={10} color="#506174" />
              <Text style={txt.source} numberOfLines={1}>{source}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {claim_boundary ? (
        <Text style={txt.boundary} numberOfLines={3}>{claim_boundary}</Text>
      ) : null}
    </CardShell>
  );
}

export const SystemKnowledgeEvidenceCardSpec: CardSpec<KnowledgeEvidenceData> = {
  type: 'system_knowledge_evidence',
  label: '系统知识证据',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <SystemKnowledgeEvidenceCardView {...data} />,
};

const styles = StyleSheet.create({
  confidenceRow: {
    marginTop: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  sources: {
    marginTop: 8,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
  },
  sourceChip: {
    maxWidth: 190,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 7,
    backgroundColor: '#EAF1FB',
  },
});

const txt = {
  claimTitle: {
    color: colors.labelPrimary,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  } as TextStyle,
  meta: {
    color: '#0A84FF',
    fontSize: 11,
    fontWeight: '600',
  } as TextStyle,
  source: {
    color: '#506174',
    fontSize: 10,
    maxWidth: 160,
  } as TextStyle,
  boundary: {
    marginTop: 8,
    color: colors.labelSecondary,
    fontSize: 10,
    lineHeight: 15,
  } as TextStyle,
};
