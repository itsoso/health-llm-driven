import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { colors } from '../../../constants/theme';
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

const TREND_COLOR: Record<string, string> = {
  up: colors.red,
  down: colors.green,
  stable: colors.labelTertiary,
};

export function MedicalReportCardView({ report_date, abnormal_count, abnormals }: MedicalReportData) {
  const router = useRouter();
  return (
    <CardShell
      icon="document-text"
      iconColor="#AF52DE"
      title="体检报告"
      badge={abnormal_count > 0 ? `${abnormal_count} 项异常` : undefined}
      badgeColor={abnormal_count > 0 ? colors.red : undefined}
      bg="#FAF5FF"
      onPress={() => router.push({ pathname: '/indicator-history', params: { type: 'weight' } })}
    >
      {report_date && <Text style={txt.date}>最近报告: {report_date}</Text>}
      {abnormals.length > 0 ? (
        <View style={styles.list}>
          {abnormals.slice(0, 5).map((item) => (
            <View key={item.name} style={styles.itemRow}>
              <Text style={txt.itemName} numberOfLines={1}>{item.name}</Text>
              <View style={styles.valueRow}>
                <Text style={[txt.itemValue, { color: colors.red }]}>
                  {item.value} {item.unit}
                </Text>
                {item.trend && (
                  <Ionicons
                    name={(TREND_ICON[item.trend] ?? 'remove') as any}
                    size={12}
                    color={TREND_COLOR[item.trend] ?? colors.labelTertiary}
                  />
                )}
              </View>
            </View>
          ))}
        </View>
      ) : (
        <Text style={txt.allNormal}>所有指标正常</Text>
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
});

const txt = {
  date: { fontSize: 10, color: colors.labelTertiary, marginBottom: 4 } as TextStyle,
  itemName: { fontSize: 12, color: colors.labelPrimary, flex: 1 } as TextStyle,
  itemValue: { fontSize: 12, fontWeight: '600', fontVariant: ['tabular-nums'] as const } as TextStyle,
  allNormal: { fontSize: 13, color: colors.green, fontWeight: '600', marginTop: 4 } as TextStyle,
};
