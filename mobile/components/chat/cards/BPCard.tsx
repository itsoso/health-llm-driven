import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { useRouter } from 'expo-router';
import { CardShell } from './CardShell';
import { colors } from '../../../constants/theme';
import type { CardSpec } from './types';

interface BPData {
  systolic: number;
  diastolic: number;
  pulse?: number;
  measured_at?: string;
  category: string;
  category_color: string;
}

/** ACC/AHA 2017 血压分级 */
function classify(s: number, d: number): { label: string; color: string } {
  if (s >= 180 || d >= 120) return { label: '高血压急症', color: '#AF52DE' };
  if (s >= 140 || d >= 90) return { label: '高血压 2 期', color: '#FF453A' };
  if (s >= 130 || d >= 80) return { label: '高血压 1 期', color: '#FF6723' };
  if (s >= 120 && d < 80) return { label: '血压升高', color: '#FF9F0A' };
  if (s < 90 || d < 60) return { label: '偏低', color: '#5AC8FA' };
  return { label: '正常', color: '#30D158' };
}

export function BPCardView({ systolic, diastolic, pulse, measured_at, category, category_color }: BPData) {
  const router = useRouter();
  return (
    <CardShell icon="heart" iconColor="#FF453A" title="血压" badge={category} badgeColor={category_color} bg="#FFF5F5" onPress={() => router.push({ pathname: '/indicator-history', params: { type: 'blood_pressure' } })}>
      <View style={styles.row}>
        <View style={styles.bpBlock}>
          <Text style={[txt.bpNum, { color: category_color }]}>
            {systolic}<Text style={txt.bpSlash}> / </Text>{diastolic}
          </Text>
          <Text style={txt.unit}>mmHg</Text>
        </View>
        {pulse != null && (
          <View style={styles.pulseBlock}>
            <Text style={txt.pulseNum}>{pulse}</Text>
            <Text style={txt.pulseLabel}>脉搏 bpm</Text>
          </View>
        )}
      </View>
      {measured_at && <Text style={txt.time}>{measured_at}</Text>}
    </CardShell>
  );
}

export const BPCardSpec: CardSpec<BPData> = {
  type: 'blood_pressure',
  label: '血压',
  match({ query_lower }) {
    if (/血压|bp|收缩压|舒张压|高压|低压/.test(query_lower)) return 15;
    return null;
  },
  async build({ api }) {
    try {
      const res = await api.get('/blood-pressure/records/me', { params: { limit: 1 } });
      const list = res.data;
      if (!Array.isArray(list) || list.length === 0) return null;
      const r = list[0];
      if (!r || r.systolic == null || r.diastolic == null) return null;
      const c = classify(r.systolic, r.diastolic);
      return {
        systolic: r.systolic,
        diastolic: r.diastolic,
        pulse: r.pulse,
        measured_at: r.record_date ? String(r.record_date) : undefined,
        category: c.label,
        category_color: c.color,
      } as BPData;
    } catch {
      return null;
    }
  },
  render: (d) => <BPCardView {...d} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  bpBlock: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  pulseBlock: { alignItems: 'flex-end' },
});

const txt = {
  bpNum: { fontSize: 22, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  bpSlash: { fontSize: 18, fontWeight: '400', color: colors.labelTertiary } as TextStyle,
  unit: { fontSize: 10, color: colors.labelTertiary } as TextStyle,
  pulseNum: { fontSize: 18, fontWeight: '700', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  pulseLabel: { fontSize: 9, color: colors.labelTertiary } as TextStyle,
  time: { fontSize: 10, color: colors.labelTertiary, marginTop: 4 } as TextStyle,
};
