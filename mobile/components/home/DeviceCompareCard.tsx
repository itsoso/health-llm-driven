/**
 * DeviceCompareCard —— 多设备一致性对比(同时戴 Apple Watch / RingConn / Garmin 等)。
 *
 * 消费后端 /devices/compare:同指标并排各来源的窗口均值 + 一致度(by_source 动态 N 源)。
 * 诚实:
 *   - 不足两个来源 / 无可比指标 → 不渲染(返回 null),不占位造声势。
 *   - agreement 仅描述各源"一致性",不判谁更准(各家算法不同),文案点明。
 *
 * onPress 跳 /settings(那里的 AppleHealthRow 启用 Apple Health 同步)——
 * 单设备用户由此接入更多数据源,卡片才会出现。
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import {
  hasComparison,
  sourceLabel,
  type DeviceComparison,
  type DeviceMetricCompare,
} from '../../services/deviceCompare';

interface Props {
  data?: DeviceComparison | null;
  onPress?: () => void;
}

function agreementColor(a: number | null, c: any, s: any) {
  if (a == null) return c.labelTertiary;
  if (a >= 0.9) return s.success?.fg ?? c.brand;
  if (a >= 0.75) return s.warning?.fg ?? c.labelSecondary;
  return s.danger?.fg ?? c.labelSecondary;
}

function MetricRow({ m }: { m: DeviceMetricCompare }) {
  const { c, s } = useTheme();
  const srcs = Object.keys(m.by_source);
  const valText = srcs
    .map((src) => `${sourceLabel(src)} ${m.by_source[src]}${m.unit}`)
    .join('  ·  ');
  const agPct = m.agreement == null ? '—' : `${Math.round(m.agreement * 100)}%`;
  return (
    <View style={styles.metricRow}>
      <View style={styles.metricLeft}>
        <Text style={[styles.metricLabel, { color: c.labelPrimary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
          {m.label}
        </Text>
        <Text style={[styles.metricVals, { color: c.labelTertiary }]} numberOfLines={1} maxFontSizeMultiplier={1.2}>
          {valText}
        </Text>
      </View>
      <View style={[styles.agBadge, { backgroundColor: c.fill }]}>
        <Text style={[styles.agText, { color: agreementColor(m.agreement, c, s) }]} maxFontSizeMultiplier={1.2}>
          {agPct}
        </Text>
      </View>
    </View>
  );
}

export default function DeviceCompareCard({ data, onPress }: Props) {
  const { c } = useTheme();
  if (!hasComparison(data)) return null; // 不足两台 / 无可比指标 → 不渲染

  const srcTitle = (data!.sources ?? []).map(sourceLabel).join(' vs ');
  const top = data!.comparisons.slice(0, 3); // 主页只露前三条,详情留给设备页

  return (
    <Pressable
      testID="home-device-compare-card"
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed && onPress ? 0.78 : 1 },
      ]}
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityLabel={`设备对比:${srcTitle},共 ${data!.comparisons.length} 项指标。`}
    >
      <View style={styles.header}>
        <View style={[styles.iconWrap, { backgroundColor: c.brandLight }]}>
          <Ionicons name="git-compare-outline" size={16} color={c.brand} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
            设备对比
          </Text>
          <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
            {srcTitle} · 近 {data!.window_days} 天均值
          </Text>
        </View>
        {onPress ? <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} /> : null}
      </View>

      <View style={styles.metrics}>
        {top.map((m) => (
          <MetricRow key={m.metric} m={m} />
        ))}
      </View>

      <Text style={[styles.foot, { color: c.labelTertiary }]} maxFontSizeMultiplier={1.2}>
        右侧为一致度(100% = 各设备完全一致);各家算法不同,不代表谁更准。
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.md,
    gap: 10,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconWrap: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 14, fontWeight: '800' },
  sub: { fontSize: 11, fontWeight: '500' },
  metrics: { gap: 8 },
  metricRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  metricLeft: { flex: 1, minWidth: 0, gap: 2 },
  metricLabel: { fontSize: 13, fontWeight: '700' },
  metricVals: { fontSize: 11, fontWeight: '500' },
  agBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, minWidth: 42, alignItems: 'center' },
  agText: { fontSize: 12, fontWeight: '800' },
  foot: { fontSize: 10, fontWeight: '500', lineHeight: 13 },
});
