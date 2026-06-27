import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { useTheme } from '../../../hooks/useTheme';
import type { CardSpec } from './types';

interface KnowledgeSourceDetail {
  source?: string | null;
  label?: string | null;
  display_name?: string | null;
}

interface KnowledgeClaim {
  doc_id?: string;
  title?: string;
  evidence_level?: string | null;
  confidence?: number | null;
  sources?: string[];
  source_details?: KnowledgeSourceDetail[];
  metadata?: Record<string, any>;
}

interface KnowledgeContraindication {
  title?: string | null;
  summary?: string | null;
  severity?: string | null;
}

interface KnowledgeEvidenceData {
  entity?: {
    title?: string;
    entity_id?: string;
    entity_type?: string;
  };
  claims?: KnowledgeClaim[];
  contraindications?: KnowledgeContraindication[] | null;
  claim_boundary?: string;
}

function evidenceLabel(level?: string | null) {
  if (!level) return '证据';
  return `${String(level).toUpperCase()}级`;
}

function isReviewedClaim(claim?: KnowledgeClaim): boolean {
  const reviewStatus = String(claim?.metadata?.review_status || claim?.metadata?.status || '').toLowerCase();
  return reviewStatus === 'reviewed' || reviewStatus === 'approved' || claim?.metadata?.reviewed === true;
}

function sourceLabel(source: KnowledgeSourceDetail): string {
  return String(source.display_name || source.label || source.source || '').trim();
}

export function SystemKnowledgeEvidenceCardView({
  entity,
  claims = [],
  contraindications,
  claim_boundary,
}: KnowledgeEvidenceData) {
  const { c } = useTheme();
  const firstClaim = claims[0];
  const title = entity?.title || entity?.entity_id || '系统知识库';
  const sourceDetails = (firstClaim?.source_details || []).slice(0, 3);
  const sources = sourceDetails.length > 0
    ? sourceDetails.map(sourceLabel).filter(Boolean)
    : firstClaim?.sources?.slice(0, 3) || [];
  const reviewed = isReviewedClaim(firstClaim);
  const claimRef = firstClaim?.doc_id?.startsWith('claim:') ? firstClaim.doc_id : null;
  const safetyHits = (contraindications || []).filter((item) => item?.title || item?.summary).slice(0, 2);

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

      {reviewed || claimRef ? (
        <View style={styles.reviewRow}>
          <Ionicons name="shield-checkmark-outline" size={12} color={c.green} />
          <Text
            maxFontSizeMultiplier={1.3}
            style={[styles.reviewText, { color: c.green }]}
            numberOfLines={1}
          >
            {reviewed ? '已审核' : '系统证据'}{claimRef ? ` · ${claimRef}` : ''}
          </Text>
        </View>
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

      {safetyHits.length > 0 ? (
        <View style={[styles.safetyBox, { backgroundColor: c.tintRed }]}>
          <View style={styles.safetyHeader}>
            <Ionicons name="alert-circle-outline" size={12} color={c.red} />
            <Text maxFontSizeMultiplier={1.3} style={[styles.safetyLabel, { color: c.red }]}>
              安全命中
            </Text>
          </View>
          {safetyHits.map((hit, index) => (
            <Text
              key={`${hit.title || hit.summary}-${index}`}
              maxFontSizeMultiplier={1.3}
              style={[styles.safetyText, { color: c.labelSecondary }]}
              numberOfLines={2}
            >
              {hit.title || hit.summary}
            </Text>
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
  reviewRow: {
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
  reviewText: {
    fontSize: 10,
    fontWeight: '700',
    flexShrink: 1,
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
  safetyBox: {
    marginTop: 8,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 7,
  },
  safetyHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  safetyLabel: {
    fontSize: 10,
    fontWeight: '800',
  } as TextStyle,
  safetyText: {
    marginTop: 3,
    fontSize: 10,
    fontWeight: '600',
    lineHeight: 14,
  } as TextStyle,
});
