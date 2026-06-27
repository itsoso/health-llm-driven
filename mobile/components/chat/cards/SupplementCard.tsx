import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { EvidenceRefsRow } from './EvidenceRefsRow';
import type { EvidenceRef, KnowledgeContraindication } from './EvidenceRefsRow';
import { useTheme } from '../../../hooks/useTheme';
import type { CardSpec } from './types';

interface SupplementData {
  checked: number;
  total: number;
  pending_names: string[];
  evidence_refs?: EvidenceRef[];
  claim_boundary?: string | null;
  contraindications?: KnowledgeContraindication[] | null;
}

export function SupplementCardView({
  checked,
  total,
  pending_names,
  evidence_refs,
  claim_boundary,
  contraindications,
}: SupplementData) {
  const { c } = useTheme();
  const pct = total > 0 ? Math.round((checked / total) * 100) : 0;
  // 进度颜色 = 完成度语义 (绿/橙/红), 不随主题切换
  const barColor = pct >= 80 ? '#30D158' : pct >= 50 ? '#FF9F0A' : '#FF453A';
  return (
    <CardShell
      icon="medical"
      iconColor={c.purple}
      title="补剂打卡"
      badge={`${checked}/${total}`}
      badgeColor={barColor}
      bg={c.tintPurple}
    >
      <View style={[styles.progressTrack, { backgroundColor: c.fill }]}>
        <View style={[styles.progressFill, { width: `${pct}%`, backgroundColor: barColor }]} />
      </View>
      {pending_names.length > 0 && (
        <View style={styles.pendingWrap}>
          <Text maxFontSizeMultiplier={1.3} style={[styles.pendingLabel, { color: c.labelSecondary }]}>
            未打卡：
          </Text>
          <View style={styles.chips}>
            {pending_names.slice(0, 4).map((n) => (
              <View key={n} style={[styles.chip, { backgroundColor: c.bgPrimary }]}>
                <Ionicons name="time-outline" size={9} color={c.labelTertiary} />
                <Text maxFontSizeMultiplier={1.3} style={[styles.chipText, { color: c.labelPrimary }]} numberOfLines={1}>
                  {n}
                </Text>
              </View>
            ))}
            {pending_names.length > 4 && (
              <Text maxFontSizeMultiplier={1.3} style={[styles.more, { color: c.labelTertiary }]}>
                +{pending_names.length - 4}
              </Text>
            )}
          </View>
        </View>
      )}
      {pending_names.length === 0 && total > 0 && (
        <Text maxFontSizeMultiplier={1.3} style={[styles.allDone, { color: c.green }]}>
          ✅ 今日补剂已全部打卡
        </Text>
      )}
      <EvidenceRefsRow
        refs={evidence_refs}
        claimBoundary={claim_boundary}
        contraindications={contraindications}
      />
    </CardShell>
  );
}

export const SupplementCardSpec: CardSpec<SupplementData> = {
  type: 'supplement_status',
  label: '补剂打卡',
  match({ query_lower }) {
    if (/补剂吃了吗|补剂进度|今天吃了什么补剂|补剂状态|补剂打卡|未吃的补剂/.test(query_lower)) return 15;
    return null;
  },
  async build({ api }) {
    try {
      const today = new Date().toISOString().split('T')[0];
      const res = await api.get(`/supplements/me/date/${today}`);
      const list: any[] = res.data || [];
      if (list.length === 0) return null;
      const seen = new Set<string>();
      const dedup = list.filter((s) => {
        const key = `${s.supplement?.name || s.supplement_name || s.name}_${s.supplement?.timing || s.timing || 'morning'}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      const checked = dedup.filter((s) => s.record?.taken || s.is_taken || s.checked).length;
      const pending_names = dedup
        .filter((s) => !(s.record?.taken || s.is_taken || s.checked))
        .map((s) => s.supplement?.name || s.supplement_name || s.name || '未知');
      return { checked, total: dedup.length, pending_names };
    } catch {
      return null;
    }
  },
  render: (d) => <SupplementCardView {...d} />,
};

const styles = StyleSheet.create({
  progressTrack: { height: 6, borderRadius: 3, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 3 },
  pendingWrap: { marginTop: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 8,
  },
  pendingLabel: { fontSize: 10 } as TextStyle,
  chipText: { fontSize: 10, maxWidth: 80 } as TextStyle,
  more: { fontSize: 10, alignSelf: 'center' } as TextStyle,
  allDone: { fontSize: 11, marginTop: 6, fontWeight: '600' } as TextStyle,
});
