/**
 * System knowledge entity detail page.
 *
 * Deep link shape: /knowledge/entity?type=gene&id=MTHFR
 * It renders the reviewed system-KB entity page plus linked claims and source
 * metadata. The content is system-level knowledge, not user-private memory.
 */
import React, { useMemo } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';

import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import {
  getKnowledgeEntity,
  type KnowledgeDocument,
  type KnowledgeEntityBundle,
  type KnowledgeSourceDetail,
} from '../../services/systemKnowledge';
import { EntityCard } from '../../components/knowledge/EntityCard';

const EVIDENCE_LABEL: Record<string, string> = {
  A: 'A级',
  B: 'B级',
  C: 'C级',
  D: 'D级',
};
const EVIDENCE_RANK: Record<string, number> = {
  A: 4,
  B: 3,
  C: 2,
  D: 1,
};

export default function KnowledgeEntityScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ type?: string; id?: string }>();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const entityType = String(params.type || '').trim();
  const entityId = String(params.id || '').trim();

  const { data, isLoading, error } = useQuery<KnowledgeEntityBundle>({
    queryKey: ['knowledge-entity', entityType, entityId],
    queryFn: () => getKnowledgeEntity(entityType, entityId),
    enabled: Boolean(entityType && entityId),
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  const entity = data?.entity;
  const linkedClaims = useMemo(
    () => dedupeLinkedClaims(data?.linked_claims || []),
    [data?.linked_claims],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.topBar}>
        <TouchableOpacity
          testID="back-button"
          onPress={() => router.back()}
          style={styles.backBtn}
          hitSlop={12}
        >
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
          <Text style={styles.backText}>返回</Text>
        </TouchableOpacity>
        <Text style={styles.topTitle} numberOfLines={1}>
          系统知识
        </Text>
        <View style={{ width: 60 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={c.brand} />
          <Text style={styles.meta}>读取知识库条目</Text>
        </View>
      ) : error || !entity ? (
        <View style={styles.center}>
          <Ionicons name="warning-outline" size={30} color={c.amber} />
          <Text style={styles.errorTitle}>条目加载失败</Text>
          <Text style={styles.meta}>{entityType || '?'} / {entityId || '?'}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.headerCard}>
            <EntityCard entity={entity} />
            {entity.evidence_level_detail?.description ? (
              <Text style={styles.evidenceDescription}>
                {entity.evidence_level_detail.description}
              </Text>
            ) : null}
          </View>

          {entity.body ? (
            <Section title="正文" styles={styles}>
              <Text style={styles.bodyText}>{entity.body}</Text>
            </Section>
          ) : null}

          {(entity.source_details || []).length > 0 ? (
            <Section title="来源" styles={styles}>
              <View style={styles.sourceRow}>
                {(entity.source_details || []).slice(0, 6).map((source, idx) => (
                  <SourceChip key={`${source.source}-${idx}`} source={source} styles={styles} />
                ))}
              </View>
            </Section>
          ) : null}

          {linkedClaims.length > 0 ? (
            <Section title={`相关事实 ${linkedClaims.length}`} styles={styles}>
              {linkedClaims.map((claim) => (
                <ClaimRow key={claim.doc_id} claim={claim} styles={styles} />
              ))}
            </Section>
          ) : null}

          {data.claim_boundary ? (
            <View style={styles.boundaryBox}>
              <Ionicons name="information-circle" size={13} color={c.amber} />
              <Text style={styles.boundaryText}>{data.claim_boundary}</Text>
            </View>
          ) : null}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function normalizeKnowledgeText(value?: string | null) {
  return String(value || '').trim().toLowerCase().replace(/\s+/g, '');
}

function evidenceRank(level?: string | null) {
  return EVIDENCE_RANK[String(level || '').toUpperCase()] || 0;
}

function claimQualityRank(claim: KnowledgeDocument) {
  return evidenceRank(claim.evidence_level) * 100 + Math.round((claim.confidence || 0) * 100);
}

function dedupeLinkedClaims(claims: KnowledgeDocument[]) {
  const bestByKey = new Map<string, KnowledgeDocument>();
  claims.forEach((claim) => {
    const titleKey = normalizeKnowledgeText(claim.title);
    const summaryKey = normalizeKnowledgeText(claim.summary);
    const key = titleKey || summaryKey ? `${titleKey}|${summaryKey}` : claim.doc_id;
    const current = bestByKey.get(key);
    if (!current || claimQualityRank(claim) > claimQualityRank(current)) {
      bestByKey.set(key, claim);
    }
  });

  return Array.from(bestByKey.values()).sort((a, b) => {
    const confidenceDiff = (b.confidence || 0) - (a.confidence || 0);
    if (confidenceDiff !== 0) return confidenceDiff;
    return String(a.doc_id).localeCompare(String(b.doc_id));
  });
}

function Section({
  title,
  children,
  styles,
}: {
  title: string;
  children: React.ReactNode;
  styles: ReturnType<typeof createStyles>;
}) {
  return (
    <View style={styles.sectionCard}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function ClaimRow({
  claim,
  styles,
}: {
  claim: KnowledgeDocument;
  styles: ReturnType<typeof createStyles>;
}) {
  const evidenceText =
    claim.evidence_level_detail?.label ||
    (claim.evidence_level ? EVIDENCE_LABEL[claim.evidence_level] : null);
  return (
    <View style={styles.claimRow}>
      <View style={styles.claimHeader}>
        <Text style={styles.claimTitle} numberOfLines={2}>
          {claim.title || claim.doc_id}
        </Text>
        {evidenceText ? (
          <View style={styles.levelChip}>
            <Text style={styles.levelText}>{evidenceText}</Text>
          </View>
        ) : null}
      </View>
      {claim.summary ? (
        <Text style={styles.claimSummary} numberOfLines={4}>
          {claim.summary}
        </Text>
      ) : null}
    </View>
  );
}

function SourceChip({
  source,
  styles,
}: {
  source: KnowledgeSourceDetail;
  styles: ReturnType<typeof createStyles>;
}) {
  return (
    <View style={styles.sourceChip}>
      <Text style={styles.sourceLabel} numberOfLines={1}>
        {source.label || '来源'}
      </Text>
      <Text style={styles.sourceName} numberOfLines={1}>
        {source.display_name || source.source}
      </Text>
    </View>
  );
}

function createStyles(c: ReturnType<typeof useTheme>['c']) {
  return StyleSheet.create({
    safe: {
      flex: 1,
      backgroundColor: c.bgPrimary,
    },
    topBar: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: spacing.md,
      paddingVertical: 8,
    },
    backBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      minWidth: 60,
    },
    backText: {
      fontSize: 16,
      color: c.labelPrimary,
      marginLeft: -2,
    },
    topTitle: {
      flex: 1,
      textAlign: 'center',
      fontSize: 17,
      fontWeight: '600',
      color: c.labelPrimary,
    },
    center: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 32,
      gap: 10,
    },
    meta: {
      fontSize: 12,
      color: c.labelTertiary,
    },
    errorTitle: {
      fontSize: 15,
      fontWeight: '600',
      color: c.labelPrimary,
    },
    content: {
      padding: spacing.lg,
      gap: spacing.md,
      paddingBottom: spacing.xl * 2,
    },
    headerCard: {
      borderWidth: 1,
      borderRadius: radii.md,
      borderColor: c.separator,
      backgroundColor: c.bgCard,
      padding: spacing.md,
      gap: 8,
    },
    evidenceDescription: {
      fontSize: 12,
      color: c.labelSecondary,
      lineHeight: 17,
    },
    sectionCard: {
      borderWidth: 1,
      borderRadius: radii.md,
      borderColor: c.separator,
      backgroundColor: c.bgCard,
      padding: spacing.md,
      gap: 8,
    },
    sectionTitle: {
      fontSize: 11,
      fontWeight: '700',
      letterSpacing: 0.4,
      textTransform: 'uppercase',
      color: c.labelTertiary,
    },
    bodyText: {
      fontSize: 14,
      lineHeight: 21,
      color: c.labelPrimary,
    },
    sourceRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 6,
    },
    sourceChip: {
      maxWidth: '100%',
      paddingHorizontal: 8,
      paddingVertical: 5,
      borderRadius: 6,
      backgroundColor: c.bgPrimary,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    sourceLabel: {
      fontSize: 10,
      color: c.brand,
      fontWeight: '700',
      lineHeight: 13,
    },
    sourceName: {
      maxWidth: 250,
      marginTop: 1,
      fontSize: 11,
      color: c.labelSecondary,
      lineHeight: 14,
    },
    claimRow: {
      paddingVertical: 8,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
    },
    claimHeader: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 8,
    },
    claimTitle: {
      flex: 1,
      fontSize: 13,
      fontWeight: '600',
      color: c.labelPrimary,
      lineHeight: 18,
    },
    levelChip: {
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: 4,
      backgroundColor: c.brandLight,
    },
    levelText: {
      fontSize: 10,
      color: c.brand,
      fontWeight: '600',
    },
    claimSummary: {
      marginTop: 4,
      fontSize: 12,
      color: c.labelSecondary,
      lineHeight: 17,
    },
    boundaryBox: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 6,
      paddingVertical: 8,
      paddingHorizontal: 10,
      borderRadius: 8,
      backgroundColor: c.tintAmber,
    },
    boundaryText: {
      flex: 1,
      fontSize: 11,
      color: c.labelSecondary,
      lineHeight: 16,
    },
  });
}
