import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { colors } from '@/constants/theme';
import type { CardSpec } from './types';

interface SupplementData {
  checked: number;
  total: number;
  pending_names: string[];
}

export function SupplementCardView({ checked, total, pending_names }: SupplementData) {
  const pct = total > 0 ? Math.round((checked / total) * 100) : 0;
  const barColor = pct >= 80 ? '#30D158' : pct >= 50 ? '#FF9F0A' : '#FF453A';
  return (
    <CardShell icon="medical" iconColor="#AF52DE" title="补剂打卡" badge={`${checked}/${total}`} badgeColor={barColor} bg="#FAF5FF">
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${pct}%`, backgroundColor: barColor }]} />
      </View>
      {pending_names.length > 0 && (
        <View style={styles.pendingWrap}>
          <Text style={txt.pendingLabel}>未打卡：</Text>
          <View style={styles.chips}>
            {pending_names.slice(0, 4).map((n) => (
              <View key={n} style={styles.chip}>
                <Ionicons name="time-outline" size={9} color="#8E8E93" />
                <Text style={txt.chipText} numberOfLines={1}>{n}</Text>
              </View>
            ))}
            {pending_names.length > 4 && (
              <Text style={txt.more}>+{pending_names.length - 4}</Text>
            )}
          </View>
        </View>
      )}
      {pending_names.length === 0 && total > 0 && (
        <Text style={txt.allDone}>✅ 今日补剂已全部打卡</Text>
      )}
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
  progressTrack: {
    height: 6, backgroundColor: '#E5E5EA', borderRadius: 3, overflow: 'hidden',
  },
  progressFill: { height: '100%', borderRadius: 3 },
  pendingWrap: { marginTop: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 8, backgroundColor: '#F2F2F7',
  },
});

const txt = {
  pendingLabel: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  chipText: { fontSize: 10, color: colors.labelPrimary, maxWidth: 80 } as TextStyle,
  more: { fontSize: 10, color: colors.labelTertiary, alignSelf: 'center' } as TextStyle,
  allDone: { fontSize: 11, color: '#30D158', marginTop: 6, fontWeight: '600' } as TextStyle,
};
