import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { useTheme, type ColorPalette } from '../../../hooks/useTheme';
import type { CardSpec } from './types';

interface AbnormalItem {
  name: string;
  value: number;
  unit: string;
  trend?: 'up' | 'down' | 'stable';
}

interface MedicalReportData {
  report_date?: string;
  abnormal_count: number;
  abnormals: AbnormalItem[];
}

const TREND_ICON: Record<string, string> = {
  up: 'trending-up',
  down: 'trending-down',
  stable: 'remove',
};

function trendColor(t: string | undefined, c: ColorPalette): string {
  if (t === 'up') return c.red;
  if (t === 'down') return c.green;
  return c.labelTertiary;
}

export function MedicalReportCardView({ report_date, abnormal_count, abnormals }: MedicalReportData) {
  const router = useRouter();
  const { c } = useTheme();
  return (
    <CardShell
      icon="document-text"
      iconColor={c.purple}
      title="体检报告"
      badge={abnormal_count > 0 ? `${abnormal_count} 项异常` : undefined}
      badgeColor={abnormal_count > 0 ? c.red : undefined}
      bg={c.tintPurple}
      onPress={() => router.push({ pathname: '/indicator-history', params: { type: 'weight' } })}
    >
      {report_date && (
        <Text maxFontSizeMultiplier={1.3} style={[styles.date, { color: c.labelTertiary }]}>
          最近报告: {report_date}
        </Text>
      )}
      {abnormals.length > 0 ? (
        <View style={styles.list}>
          {abnormals.slice(0, 5).map((item) => (
            <View key={item.name} style={styles.itemRow}>
              <Text maxFontSizeMultiplier={1.3} style={[styles.itemName, { color: c.labelPrimary }]} numberOfLines={1}>
                {item.name}
              </Text>
              <View style={styles.valueRow}>
                <Text maxFontSizeMultiplier={1.3} style={[styles.itemValue, { color: c.red }]}>
                  {item.value} {item.unit}
                </Text>
                {item.trend && (
                  <Ionicons
                    name={(TREND_ICON[item.trend] ?? 'remove') as any}
                    size={12}
                    color={trendColor(item.trend, c)}
                  />
                )}
              </View>
            </View>
          ))}
        </View>
      ) : (
        <Text maxFontSizeMultiplier={1.3} style={[styles.allNormal, { color: c.green }]}>
          所有指标正常
        </Text>
      )}
    </CardShell>
  );
}

export const MedicalReportCardSpec: CardSpec<MedicalReportData> = {
  type: 'medical_report',
  label: '体检报告',
  match({ query_lower }) {
    if (/体检|报告|化验|指标|异常/.test(query_lower)) return 14;
    return null;
  },
  async build({ api }) {
    try {
      const res = await api.get('/family-health/medical-indicators/analysis');
      const data = res.data;
      if (!data) return null;

      const abnormals: AbnormalItem[] = (data.abnormal_indicators ?? []).map((i: any) => ({
        name: i.indicator_name ?? i.name,
        value: i.latest_value ?? i.value,
        unit: i.unit ?? '',
        trend: i.trend,
      }));

      return {
        report_date: data.latest_report_date ?? data.report_date,
        abnormal_count: data.abnormal_count ?? abnormals.length,
        abnormals,
      };
    } catch {
      return null;
    }
  },
  render: (d) => <MedicalReportCardView {...d} />,
};

const styles = StyleSheet.create({
  list: { gap: 4, marginTop: 4 },
  itemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  date: { fontSize: 10, marginBottom: 4 } as TextStyle,
  itemName: { fontSize: 12, flex: 1 } as TextStyle,
  itemValue: { fontSize: 12, fontWeight: '600', fontVariant: ['tabular-nums'] as const } as TextStyle,
  allNormal: { fontSize: 13, fontWeight: '600', marginTop: 4 } as TextStyle,
});
