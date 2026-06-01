/**
 * EvidenceRefsRow — unified system-KB evidence chip + ClaimSheet entry.
 *
 * All Mobile recommendation surfaces should use this component instead of
 * hand-written evidence chips, so claim loading, feedback, and formatting stay
 * consistent.
 */
import React, { useMemo, useState } from 'react';
import { GestureResponderEvent, StyleSheet, Text, TextStyle, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { KnowledgeClaimBundle } from '../../services/systemKnowledge';
import { useTheme } from '../../hooks/useTheme';
import { ClaimSheet } from './ClaimSheet';

export type EvidenceRef = string | { claim_id?: string; doc_id?: string; id?: string };

interface EvidenceRefsRowProps {
  refs?: EvidenceRef[] | null;
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

export function EvidenceRefsRow({ refs, testID = 'system-kb-evidence-chip' }: EvidenceRefsRowProps) {
  const { s } = useTheme();
  const claimIds = useMemo(() => normalizeEvidenceRefs(refs), [refs]);
  const [visible, setVisible] = useState(false);

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
});
