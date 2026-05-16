import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, spacing } from '../../../constants/theme';
import type { KnowledgeClaimBundle } from '../../../services/systemKnowledge';

export type EvidenceRef = string | { claim_id?: string; doc_id?: string; id?: string };

interface EvidenceRefsRowProps {
  refs?: EvidenceRef[] | null;
  loadClaim?: (claimId: string) => Promise<KnowledgeClaimBundle>;
}

function normalizeRefs(refs?: EvidenceRef[] | null): string[] {
  if (!Array.isArray(refs)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const ref of refs) {
    const value = typeof ref === 'string' ? ref : ref?.claim_id || ref?.doc_id || ref?.id;
    if (!value || !String(value).startsWith('claim:')) continue;
    if (seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  return out;
}

function evidenceLevelLabel(level?: string | null): string {
  if (!level) return '证据';
  return `${String(level).toUpperCase()}级`;
}

async function defaultLoadClaim(claimId: string): Promise<KnowledgeClaimBundle> {
  const { getKnowledgeClaim } = await import('../../../services/systemKnowledge');
  return getKnowledgeClaim(claimId);
}

export function EvidenceRefsRow({ refs, loadClaim = defaultLoadClaim }: EvidenceRefsRowProps) {
  const claimIds = useMemo(() => normalizeRefs(refs), [refs]);
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [bundles, setBundles] = useState<KnowledgeClaimBundle[]>([]);
  const [error, setError] = useState<string | null>(null);

  if (claimIds.length === 0) return null;

  async function openDetails() {
    setVisible(true);
    if (bundles.length > 0 || loading) return;
    setLoading(true);
    setError(null);
    try {
      const settled = await Promise.allSettled(claimIds.slice(0, 3).map((id) => loadClaim(id)));
      const ok = settled
        .filter((item): item is PromiseFulfilledResult<KnowledgeClaimBundle> => item.status === 'fulfilled')
        .map((item) => item.value)
        .filter((item) => item?.claim?.doc_id);
      setBundles(ok);
      if (ok.length === 0) setError('暂时无法读取证据详情');
    } catch {
      setError('暂时无法读取证据详情');
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <TouchableOpacity
        testID="system-kb-evidence-chip"
        activeOpacity={0.75}
        style={styles.chip}
        onPress={openDetails}
      >
        <Ionicons name="library-outline" size={11} color="#0A84FF" />
        <Text style={txt.chipText}>系统证据 {claimIds.length}</Text>
        <Ionicons name="chevron-forward" size={10} color="#0A84FF" />
      </TouchableOpacity>

      <Modal
        visible={visible}
        transparent
        animationType="fade"
        onRequestClose={() => setVisible(false)}
      >
        <Pressable style={styles.backdrop} onPress={() => setVisible(false)}>
          <Pressable style={styles.sheet}>
            <View style={styles.sheetHeader}>
              <View style={styles.sheetTitleRow}>
                <Ionicons name="library" size={15} color="#0A84FF" />
                <Text style={txt.sheetTitle}>系统知识库证据</Text>
              </View>
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="关闭证据详情"
                onPress={() => setVisible(false)}
              >
                <Ionicons name="close" size={19} color={colors.labelSecondary} />
              </TouchableOpacity>
            </View>

            {loading ? (
              <View style={styles.loading}>
                <ActivityIndicator color="#0A84FF" />
                <Text style={txt.meta}>读取证据中</Text>
              </View>
            ) : null}

            {!loading && error ? <Text style={txt.error}>{error}</Text> : null}

            {!loading && bundles.length > 0 ? (
              <ScrollView style={styles.claimList} contentContainerStyle={styles.claimListContent}>
                {bundles.map((bundle) => {
                  const claim = bundle.claim;
                  const sources = claim.sources?.slice(0, 3) || [];
                  return (
                    <View key={claim.doc_id} style={styles.claimBlock}>
                      <View style={styles.claimHeader}>
                        <Text style={txt.claimTitle} numberOfLines={3}>
                          {claim.title || claim.doc_id}
                        </Text>
                        <View style={styles.levelChip}>
                          <Text style={txt.levelText}>{evidenceLevelLabel(claim.evidence_level)}</Text>
                        </View>
                      </View>
                      {typeof claim.confidence === 'number' ? (
                        <Text style={txt.meta}>置信度 {Math.round(claim.confidence * 100)}%</Text>
                      ) : null}
                      {claim.summary ? <Text style={txt.summary}>{claim.summary}</Text> : null}
                      {sources.length > 0 ? (
                        <View style={styles.sources}>
                          {sources.map((source) => (
                            <View key={`${claim.doc_id}-${source}`} style={styles.sourceChip}>
                              <Ionicons name="document-text-outline" size={10} color="#506174" />
                              <Text style={txt.source} numberOfLines={1}>{source}</Text>
                            </View>
                          ))}
                        </View>
                      ) : null}
                    </View>
                  );
                })}
                {bundles[0]?.claim_boundary ? (
                  <Text style={txt.boundary}>{bundles[0].claim_boundary}</Text>
                ) : null}
              </ScrollView>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  chip: {
    alignSelf: 'flex-start',
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 7,
    paddingVertical: 4,
    borderRadius: 7,
    backgroundColor: '#EAF1FB',
  },
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0, 0, 0, 0.28)',
  },
  sheet: {
    maxHeight: '72%',
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    backgroundColor: colors.bgCard,
    paddingTop: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  sheetTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  loading: {
    paddingVertical: spacing.xl,
    alignItems: 'center',
    gap: spacing.sm,
  },
  claimList: {
    maxHeight: 440,
  },
  claimListContent: {
    paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
  claimBlock: {
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.separator,
    padding: spacing.sm,
    backgroundColor: '#F8FAFD',
  },
  claimHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  levelChip: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
    backgroundColor: '#DCEBFF',
  },
  sources: {
    marginTop: 7,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
  },
  sourceChip: {
    maxWidth: 220,
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
  chipText: { color: '#0A84FF', fontSize: 10, fontWeight: '700' } as TextStyle,
  sheetTitle: { color: colors.labelPrimary, fontSize: 15, fontWeight: '800' } as TextStyle,
  claimTitle: { flex: 1, color: colors.labelPrimary, fontSize: 13, lineHeight: 18, fontWeight: '800' } as TextStyle,
  levelText: { color: '#0A61B8', fontSize: 10, fontWeight: '800' } as TextStyle,
  meta: { color: colors.labelSecondary, fontSize: 11, marginTop: 4 } as TextStyle,
  summary: { color: colors.labelSecondary, fontSize: 12, lineHeight: 17, marginTop: 6 } as TextStyle,
  source: { color: '#506174', fontSize: 10, maxWidth: 185 } as TextStyle,
  boundary: { color: colors.labelTertiary, fontSize: 10, lineHeight: 15, marginTop: 2 } as TextStyle,
  error: { color: colors.red, fontSize: 12, paddingVertical: spacing.lg } as TextStyle,
};
