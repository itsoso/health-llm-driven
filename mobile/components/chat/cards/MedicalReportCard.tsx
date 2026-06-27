import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { revaColors as C, revaSemantic, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

// 体检报告类目 accent (紫) + 卡底 tint = 装饰色, 保留字面量 (= legacy purple/tintPurple).
const REPORT_ACCENT = '#7C5CBF';
const REPORT_TINT = '#EDE7F6';

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

// 趋势方向 = 临床「好坏」语义 (升高 risk / 下降 normal / 持平中性)
function trendColor(t: string | undefined): string {
  if (t === 'up') return revaSemantic.risk.fg;
  if (t === 'down') return revaSemantic.normal.fg;
  return C.ink3;
}

export function MedicalReportCardView({ report_date, abnormal_count, abnormals }: MedicalReportData) {
  const router = useRouter();
  return (
    <CardShell
      icon="document-text"
      iconColor={REPORT_ACCENT}
      title="体检报告"
      badge={abnormal_count > 0 ? `${abnormal_count} 项异常` : undefined}
      badgeColor={abnormal_count > 0 ? revaSemantic.risk.fg : undefined}
      bg={REPORT_TINT}
      onPress={() => router.push({ pathname: '/indicator-history', params: { type: 'weight' } })}
    >
      {report_date && (
        <Text maxFontSizeMultiplier={1.3} style={styles.date}>
          最近报告: {report_date}
        </Text>
      )}
      {abnormals.length > 0 ? (
        <View style={styles.list}>
          {abnormals.slice(0, 5).map((item) => (
            <View key={item.name} style={styles.itemRow}>
              <Text maxFontSizeMultiplier={1.3} style={styles.itemName} numberOfLines={1}>
                {item.name}
              </Text>
              <View style={styles.valueRow}>
                <Text maxFontSizeMultiplier={1.3} style={styles.itemValue}>
                  {item.value} {item.unit}
                </Text>
                {item.trend && (
                  <Ionicons
                    name={(TREND_ICON[item.trend] ?? 'remove') as any}
                    size={12}
                    color={trendColor(item.trend)}
                  />
                )}
              </View>
            </View>
          ))}
        </View>
      ) : (
        <Text maxFontSizeMultiplier={1.3} style={styles.allNormal}>
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
  date: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink3, marginBottom: 4 } as TextStyle,
  itemName: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink1, flex: 1 } as TextStyle,
  itemValue: { fontFamily: revaFonts.mono, fontSize: 12, fontWeight: '600', color: revaSemantic.risk.fg, fontVariant: ['tabular-nums'] as const } as TextStyle,
  allNormal: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.green500, marginTop: 4 } as TextStyle,
});
