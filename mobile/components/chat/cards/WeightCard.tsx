import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Polyline, Circle as SvgCircle } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { CardShell } from './CardShell';
import { colors } from '../../../constants/theme';
import type { CardSpec } from './types';

interface WeightData {
  current_kg?: number;
  trend_7d?: number[]; // 最近 7 天
  change_7d_kg?: number;
  bmi?: number;
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const w = 100, h = 32, pad = 2;
  const min = Math.min(...points), max = Math.max(...points);
  const range = max - min || 1;
  const pts = points.map((v, i) => {
    const x = (i / (points.length - 1)) * (w - pad * 2) + pad;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const trend = points[points.length - 1] - points[0];
  const color = trend < -0.1 ? '#30D158' : trend > 0.1 ? '#FF453A' : '#8E8E93';
  const last = pts.split(' ').pop() || '';
  const [lx, ly] = last.split(',').map(Number);
  return (
    <Svg width={w} height={h}>
      <Polyline points={pts} fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
      {!isNaN(lx) && <SvgCircle cx={lx} cy={ly} r={2.5} fill={color} />}
    </Svg>
  );
}

export function WeightCardView({ current_kg, trend_7d, change_7d_kg, bmi }: WeightData) {
  const router = useRouter();
  const up = (change_7d_kg ?? 0) > 0;
  const changeColor = change_7d_kg == null || Math.abs(change_7d_kg) < 0.05
    ? colors.labelTertiary : up ? '#FF453A' : '#30D158';
  return (
    <CardShell icon="scale" iconColor="#0A8F8F" title="体重" bg="#F0FFFD" onPress={() => router.push({ pathname: '/indicator-history', params: { type: 'weight' } })}>
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={txt.big}>{current_kg != null ? `${current_kg.toFixed(1)}kg` : '--'}</Text>
          <View style={styles.sub}>
            {change_7d_kg != null && (
              <View style={styles.changeRow}>
                <Ionicons name={up ? 'trending-up' : 'trending-down'} size={11} color={changeColor} />
                <Text style={[txt.change, { color: changeColor }]}>
                  {up ? '+' : ''}{change_7d_kg.toFixed(1)}kg · 7天
                </Text>
              </View>
            )}
            {bmi != null && <Text style={txt.bmi}>BMI {bmi.toFixed(1)}</Text>}
          </View>
        </View>
        {trend_7d && trend_7d.length >= 2 && <Sparkline points={trend_7d} />}
      </View>
    </CardShell>
  );
}

export const WeightCardSpec: CardSpec<WeightData> = {
  type: 'weight',
  label: '体重',
  match({ query_lower }) {
    if (/记录|打卡|称/.test(query_lower) && !/趋势|变化|多少|现在/.test(query_lower)) return null;
    if (/体重|bmi|胖|瘦|减肥|减脂/.test(query_lower)) return 15;
    return null;
  },
  async build({ api }) {
    try {
      const res = await api.get('/weight/records/me', { params: { limit: 7 } });
      const records: any[] = res.data || [];
      if (records.length === 0) return null;
      const sorted = [...records].sort((a, b) => (a.record_date || '').localeCompare(b.record_date || ''));
      const vals = sorted.map((r) => r.weight_kg).filter((v) => v != null);
      if (vals.length === 0) return null;
      const cur = vals[vals.length - 1];
      const first = vals[0];
      const cardData: WeightData = { current_kg: cur, trend_7d: vals };
      if (vals.length >= 2) cardData.change_7d_kg = cur - first;
      if (sorted[sorted.length - 1]?.bmi) cardData.bmi = sorted[sorted.length - 1].bmi;
      return cardData;
    } catch {
      return null;
    }
  },
  render: (d) => <WeightCardView {...d} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  sub: { marginTop: 4, gap: 2 },
  changeRow: { flexDirection: 'row', alignItems: 'center', gap: 3 },
});

const txt = {
  big: { fontSize: 22, fontWeight: '800', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  change: { fontSize: 11, fontWeight: '600', fontVariant: ['tabular-nums'] as const } as TextStyle,
  bmi: { fontSize: 10, color: colors.labelTertiary } as TextStyle,
};
