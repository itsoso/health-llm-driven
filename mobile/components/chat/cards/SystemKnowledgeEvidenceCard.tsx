import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { useTheme } from '../../../hooks/useTheme';
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
  const { c } = useTheme();
  const firstClaim = claims[0];
  const title = entity?.title || entity?.entity_id || '系统知识库';
  const sources = firstClaim?.sources?.slice(0, 3) || [];

  return (
    <CardShell
      icon="library"
      iconColor={c.blue}
      title={title}
      badge={evidenceLabel(firstClaim?.evidence_level)}
      badgeColor={c.blue}
      bg={c.tintBlue}
    >
      {firstClaim?.title ? (
        <Text
          maxFontSizeMultiplier={1.3}
          style={[styles.claimTitle, { color: c.labelPrimary }]}
          numberOfLines={2}
        >
          {firstClaim.title}
        </Text>
      ) : null}

      {typeof firstClaim?.confidence === 'number' ? (
        <View style={styles.confidenceRow}>
          <Ionicons name="shield-checkmark-outline" size={12} color={c.blue} />
          <Text maxFontSizeMultiplier={1.3} style={[styles.meta, { color: c.blue }]}>
            置信度 {Math.round(firstClaim.confidence * 100)}%
          </Text>
        </View>
      ) : null}

      {sources.length > 0 ? (
        <View style={styles.sources}>
          {sources.map((source) => (
            <View
              key={source}
              style={[styles.sourceChip, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}
            >
              <Ionicons name="document-text-outline" size={10} color={c.labelSecondary} />
              <Text
                maxFontSizeMultiplier={1.3}
                style={[styles.source, { color: c.labelSecondary }]}
                numberOfLines={1}
              >
                {source}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {claim_boundary ? (
        <Text
          maxFontSizeMultiplier={1.3}
          style={[styles.boundary, { color: c.labelSecondary }]}
          numberOfLines={3}
        >
          {claim_boundary}
        </Text>
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
    borderWidth: StyleSheet.hairlineWidth,
  },
  claimTitle: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  } as TextStyle,
  meta: {
    fontSize: 11,
    fontWeight: '600',
  } as TextStyle,
  source: {
    fontSize: 10,
    maxWidth: 160,
  } as TextStyle,
  boundary: {
    marginTop: 8,
    fontSize: 10,
    lineHeight: 15,
  } as TextStyle,
});
