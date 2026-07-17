/**
 * /device-sources —— 数据来源页(对标 Mac 的 DataSourcesView)。
 *
 * 调 GET /devices/sources/summary,按数据源(Garmin / Apple Watch / RingConn / …)
 * 列出各自近 N 天覆盖天数 + 最新一天的各指标快照。让用户看清「记录来自哪个设备、
 * 每个设备贡献了多少数据」。三源同戴时一目了然。
 */
import React, { useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import {
  getDeviceSourcesSummary,
  sortedSources,
  latestDayMetrics,
  type DeviceSourceSummary,
} from '../services/deviceSources';
import { sourceLabel } from '../services/deviceCompare';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

const WINDOW_OPTIONS = [
  { label: '7 天', days: 7 },
  { label: '30 天', days: 30 },
  { label: '90 天', days: 90 },
];

function sourceIcon(src: string): keyof typeof Ionicons.glyphMap {
  if (/apple/i.test(src)) return 'watch-outline';
  if (/ring|oura/i.test(src)) return 'ellipse-outline';
  if (/garmin/i.test(src)) return 'fitness-outline';
  if (/withings/i.test(src)) return 'scale-outline';
  if (/manual/i.test(src)) return 'create-outline';
  return 'help-circle-outline';
}

function SourceCard({ source }: { source: DeviceSourceSummary }) {
  const { c } = useTheme();
  const styles = createStyles(c);
  const metrics = latestDayMetrics(source);
  const isUnknown = source.data_source === 'unknown';
  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.cardHeader}>
        <View style={[styles.iconWrap, { backgroundColor: c.brandLight }]}>
          <Ionicons name={sourceIcon(source.data_source)} size={18} color={c.brand} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[styles.sourceName, { color: c.labelPrimary }]} numberOfLines={1}>
            {sourceLabel(source.data_source)}
          </Text>
          <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1}>
            覆盖 {source.days_covered} 天
          </Text>
        </View>
      </View>

      {isUnknown && (
        <Text style={[styles.unknownNote, { color: c.labelTertiary }]}>
          来源名未识别 —— 可能是 RingConn 等设备,暂未归类。识别后将单独显示并优先采用其睡眠/血氧。
        </Text>
      )}

      <View style={[styles.latestDivider, { borderTopColor: c.separator }]}>
        <Text style={[styles.latestTitle, { color: c.labelSecondary }]}>
          {source.latest_date ? `最近一天 · ${source.latest_date}` : '最近一天'}
        </Text>
        {metrics.length > 0 ? (
          <View style={styles.metricGrid}>
            {metrics.map((m) => (
              <View key={m.key} style={styles.metricCell}>
                <Text style={[styles.metricVal, { color: c.labelPrimary }]} numberOfLines={1}>{m.text}</Text>
                <Text style={[styles.metricLabel, { color: c.labelTertiary }]} numberOfLines={1}>{m.label}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={[styles.sub, { color: c.labelTertiary }]}>最近一天无可展示指标</Text>
        )}
      </View>
    </View>
  );
}

export default function DeviceSourcesScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = createStyles(c);
  const [days, setDays] = useState(30);

  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ['device-sources', days],
    queryFn: () => getDeviceSourcesSummary(days),
    staleTime: 5 * 60 * 1000,
  });

  const sources = sortedSources(data);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={[styles.title, { color: c.labelPrimary }]}>数据来源</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.windowRow}>
        {WINDOW_OPTIONS.map((opt) => {
          const active = opt.days === days;
          return (
            <TouchableOpacity
              key={opt.days}
              onPress={() => setDays(opt.days)}
              style={[styles.windowChip, { backgroundColor: active ? c.brand : c.fill }]}
              accessibilityRole="button"
            >
              <Text style={{ color: active ? '#fff' : c.labelSecondary, fontSize: 13, fontWeight: '600' }}>{opt.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        {isLoading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={c.labelTertiary} />
        ) : error ? (
          <Text style={[styles.empty, { color: c.labelTertiary }]}>加载失败,下拉重试</Text>
        ) : sources.length === 0 ? (
          <Text style={[styles.empty, { color: c.labelTertiary }]}>
            近 {days} 天暂无设备数据。绑定 Garmin、或在「健康」App 接入 Apple Watch / RingConn 后同步即可看到。
          </Text>
        ) : (
          <>
            <Text style={[styles.hint, { color: c.labelTertiary }]}>
              近 {data?.window_days ?? days} 天统计覆盖;卡片展示各来源最近一天的同日数据
            </Text>
            {sources.map((s) => (
              <SourceCard key={s.data_source} source={s} />
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) =>
  StyleSheet.create({
    safe: { flex: 1 },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    title: { fontSize: 17, fontWeight: '700' },
    windowRow: { flexDirection: 'row', gap: 8, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
    windowChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16 },
    content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },
    hint: { fontSize: 12, marginBottom: 2 },
    empty: { fontSize: 14, textAlign: 'center', marginTop: 40, lineHeight: 20, paddingHorizontal: spacing.lg },
    card: { borderRadius: radii.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.md, gap: 10 },
    cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
    iconWrap: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
    sourceName: { fontSize: 15, fontWeight: '800' },
    sub: { fontSize: 12, fontWeight: '500' },
    unknownNote: { fontSize: 11, lineHeight: 15 },
    latestDivider: { borderTopWidth: StyleSheet.hairlineWidth, paddingTop: 10, gap: 9 },
    latestTitle: { fontSize: 12, fontWeight: '600' },
    metricGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
    metricCell: { width: '30%', minWidth: 90 },
    metricVal: { fontSize: 15, fontWeight: '700' },
    metricLabel: { fontSize: 11, fontWeight: '500', marginTop: 1 },
  });
