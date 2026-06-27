/**
 * EvidenceRefsRow — unified system-KB evidence chip + ClaimSheet entry.
 *
 * All Mobile recommendation surfaces should use this component instead of
 * hand-written evidence chips, so claim loading, feedback, and formatting stay
 * consistent.
 */
import React, { useMemo, useState } from 'react';
import { GestureResponderEvent, StyleSheet, Text, TextStyle, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { KnowledgeClaimBundle } from '../../services/systemKnowledge';
import { useTheme } from '../../hooks/useTheme';
import { ClaimSheet } from './ClaimSheet';

export type EvidenceRef = string | { claim_id?: string; doc_id?: string; id?: string };

export interface KnowledgeContraindication {
  title?: string | null;
  summary?: string | null;
  severity?: string | null;
  blocks?: string[] | null;
  trigger?: string[] | null;
}

interface EvidenceRefsRowProps {
  refs?: EvidenceRef[] | null;
  claimBoundary?: string | null;
  contraindications?: KnowledgeContraindication[] | null;
  testID?: string;
  /** @deprecated ClaimSheet 自己调 getKnowledgeClaim. 保留参数防破坏 callsite. */
  loadClaim?: (claimId: string) => Promise<KnowledgeClaimBundle>;
  /** @deprecated ClaimSheet 自己调 submitKnowledgeClaimFeedback. */
  submitFeedback?: (claimId: string, reason?: string) => Promise<any>;
}

export function normalizeEvidenceRefs(refs?: EvidenceRef[] | null): string[] {
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

function firstContraindicationLabel(items?: KnowledgeContraindication[] | null): string | null {
  if (!Array.isArray(items)) return null;
  for (const item of items) {
    const label = String(item?.title || item?.summary || '').trim();
    if (label) return label;
  }
  return null;
}

export function EvidenceRefsRow({
  refs,
  claimBoundary,
  contraindications,
  testID = 'system-kb-evidence-chip',
}: EvidenceRefsRowProps) {
  const { c, s } = useTheme();
  const claimIds = useMemo(() => normalizeEvidenceRefs(refs), [refs]);
  const [visible, setVisible] = useState(false);
  const boundaryText = String(claimBoundary || '').trim();
  const safetyLabel = firstContraindicationLabel(contraindications);

  if (claimIds.length === 0) return null;

  const open = (event?: GestureResponderEvent) => {
    event?.stopPropagation?.();
    setVisible(true);
  };

  return (
    <>
      <TouchableOpacity
        testID={testID}
        activeOpacity={0.75}
        style={[styles.chip, { backgroundColor: s.info.bg }]}
        onPress={open}
      >
        <Ionicons name="library-outline" size={11} color={s.info.fg} />
        <Text style={[styles.chipText, { color: s.info.fg }]}>系统证据 {claimIds.length}</Text>
        <Ionicons name="chevron-forward" size={10} color={s.info.fg} />
      </TouchableOpacity>

      {boundaryText ? (
        <View style={[styles.metaRow, { backgroundColor: s.warning.bg }]}>
          <Ionicons name="information-circle-outline" size={11} color={s.warning.fg} />
          <Text
            maxFontSizeMultiplier={1.3}
            style={[styles.metaText, { color: c.labelSecondary }]}
            numberOfLines={2}
          >
            证据边界 · {boundaryText}
          </Text>
        </View>
      ) : null}

      {safetyLabel ? (
        <View style={[styles.metaRow, { backgroundColor: s.danger.bg }]}>
          <Ionicons name="alert-circle-outline" size={11} color={s.danger.fg} />
          <Text
            maxFontSizeMultiplier={1.3}
            style={[styles.metaText, { color: c.labelSecondary }]}
            numberOfLines={2}
          >
            安全命中 · {safetyLabel}
          </Text>
        </View>
      ) : null}

      <ClaimSheet
        visible={visible}
        claimIds={claimIds}
        onClose={() => setVisible(false)}
      />
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
  },
  chipText: { fontSize: 10, fontWeight: '700' } as TextStyle,
  metaRow: {
    alignSelf: 'flex-start',
    maxWidth: '100%',
    marginTop: 5,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 4,
    paddingHorizontal: 7,
    paddingVertical: 4,
    borderRadius: 7,
  },
  metaText: {
    flexShrink: 1,
    fontSize: 10,
    fontWeight: '600',
    lineHeight: 14,
  } as TextStyle,
});
