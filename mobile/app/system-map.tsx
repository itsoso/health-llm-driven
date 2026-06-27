import React, { useMemo } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { radii, spacing } from '../constants/theme';
import { systemMapSnapshot } from '../constants/systemMap.generated';
import { useAuth } from '../hooks/useAuth';
import { useTheme, type ColorPalette, type SemanticPalette } from '../hooks/useTheme';

type CountKey = keyof typeof systemMapSnapshot.counts;
type ToneKey = keyof SemanticPalette;

const COUNT_CARDS: Array<{
  key: CountKey;
  label: string;
  detail: string;
  icon: keyof typeof Ionicons.glyphMap;
  tone: ToneKey;
}> = [
  { key: 'api_routers', label: 'API routers', detail: '后端入口', icon: 'server-outline', tone: 'info' },
  { key: 'mobile_routes', label: 'Mobile routes', detail: 'Expo 页面', icon: 'phone-portrait-outline', tone: 'success' },
  { key: 'safety_rules_total', label: '安全规则', detail: '确定性守门', icon: 'shield-checkmark-outline', tone: 'danger' },
  { key: 'specialists', label: 'Specialists', detail: '多 agent 专家', icon: 'people-outline', tone: 'warning' },
  { key: 'twin_partitions', label: 'Twin 分区', detail: '人体状态视图', icon: 'body-outline', tone: 'success' },
  { key: 'service_files', label: 'Services', detail: '业务能力层', icon: 'construct-outline', tone: 'neutral' },
];

const LAYERS = [
  { code: 'A', title: '叙事层', body: '目标、规划、业务流，用 last-reviewed 管新鲜度。' },
  { code: 'B', title: '代码派生层', body: '计数与 roster 由 dump_system_map.py 生成，CI 做等值比对。' },
  { code: 'C', title: '在途层', body: 'dossiers 承载当前 feature，不混进长期叙事。' },
];

const SOURCE_ROWS = [
  { label: 'Agent 入口', value: 'docs/system-map/INDEX.md' },
  { label: '代码真源', value: 'docs/_generated/system-map.json' },
  { label: '生成器', value: 'scripts/dump_system_map.py' },
  { label: '漂移闸', value: 'scripts/check_doc_drift.py' },
];

export default function SystemMapScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const accountLabel = user?.id ? `user_id=${user.id}` : '未登录';
  const generatedNote = String(systemMapSnapshot._note || 'generated');

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconButton} accessibilityRole="button" accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.navTitle}>系统地图</Text>
        <View style={styles.iconButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <View style={styles.heroTop}>
            <View style={styles.heroIcon}>
              <Ionicons name="map-outline" size={22} color="#fff" />
            </View>
            <View style={styles.accountPill}>
              <Ionicons name="person-circle-outline" size={14} color={c.brandDark} />
              <Text style={txt.accountPill}>{accountLabel}</Text>
            </View>
          </View>
          <Text style={txt.heroEyebrow}>REVA OPERATING MAP</Text>
          <Text style={txt.heroTitle}>Agent 一遍读懂系统</Text>
          <Text style={txt.heroCopy}>
            移动端直接展示系统透明化层的生成快照、权威入口和防漂移机制，后续 agent 开工先读这里对应的项目地图。
          </Text>
          <View style={styles.heroRule}>
            <View style={[styles.ruleSegment, { backgroundColor: s.success.solid }]} />
            <View style={[styles.ruleSegment, { backgroundColor: s.info.solid }]} />
            <View style={[styles.ruleSegment, { backgroundColor: s.warning.solid }]} />
            <View style={[styles.ruleSegment, { backgroundColor: s.danger.solid }]} />
          </View>
        </View>

        <Text style={txt.sectionLabel}>代码派生快照</Text>
        <View style={styles.metricGrid}>
          {COUNT_CARDS.map((item) => (
            <MetricCard
              key={item.key}
              countKey={item.key}
              label={item.label}
              detail={item.detail}
              icon={item.icon}
              tone={item.tone}
            />
          ))}
        </View>

        <View style={styles.panel}>
          <View style={styles.panelHeader}>
            <Ionicons name="layers-outline" size={18} color={c.brand} />
            <Text style={txt.panelTitle}>三层真源</Text>
          </View>
          {LAYERS.map((layer, index) => (
            <View key={layer.code} style={[styles.layerRow, index === 0 && styles.layerRowFirst]}>
              <View style={styles.layerCode}>
                <Text style={txt.layerCode}>{layer.code}</Text>
              </View>
              <View style={styles.layerCopy}>
                <Text style={txt.layerTitle}>{layer.title}</Text>
                <Text style={txt.layerBody}>{layer.body}</Text>
              </View>
            </View>
          ))}
        </View>

        <RosterPanel
          icon="sparkles-outline"
          title="Specialist roster"
          items={systemMapSnapshot.specialists_roster}
        />

        <RosterPanel
          icon="git-network-outline"
          title="Twin partitions"
          items={systemMapSnapshot.twin_partitions_roster}
        />

        <View style={styles.panel}>
          <View style={styles.panelHeader}>
            <Ionicons name="git-branch-outline" size={18} color={c.brand} />
            <Text style={txt.panelTitle}>读写闭环</Text>
          </View>
          {SOURCE_ROWS.map((row, index) => (
            <View key={row.label} style={[styles.sourceRow, index === 0 && styles.sourceRowFirst]}>
              <Text style={txt.sourceLabel}>{row.label}</Text>
              <Text style={txt.sourceValue} selectable numberOfLines={2}>{row.value}</Text>
            </View>
          ))}
          <Text style={txt.generatedNote} numberOfLines={3}>{generatedNote}</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function MetricCard({
  countKey,
  label,
  detail,
  icon,
  tone,
}: {
  countKey: CountKey;
  label: string;
  detail: string;
  icon: keyof typeof Ionicons.glyphMap;
  tone: ToneKey;
}) {
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const tonePalette = s[tone];
  const value = systemMapSnapshot.counts[countKey];

  return (
    <View style={[styles.metricCard, { borderTopColor: tonePalette.solid }]}>
      <View style={styles.metricHeader}>
        <View style={[styles.metricIcon, { backgroundColor: tonePalette.bg }]}>
          <Ionicons name={icon} size={17} color={tonePalette.fg} />
        </View>
        <Text style={txt.metricDetail}>{detail}</Text>
      </View>
      <Text testID={`system-map-count-${countKey}`} style={txt.metricValue}>{value}</Text>
      <Text style={txt.metricLabel} numberOfLines={1}>{label}</Text>
    </View>
  );
}

function RosterPanel({
  icon,
  title,
  items,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  items: readonly string[];
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  return (
    <View style={styles.panel}>
      <View style={styles.panelHeader}>
        <Ionicons name={icon} size={18} color={c.brand} />
        <Text style={txt.panelTitle}>{title}</Text>
      </View>
      <View style={styles.tagWrap}>
        {items.map((item) => (
          <View key={item} style={styles.tag}>
            <Text style={txt.tagText}>{item}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  iconButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg, paddingBottom: 112 },
  hero: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    padding: spacing.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    marginBottom: spacing.lg,
  },
  heroTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.lg },
  heroIcon: {
    width: 42,
    height: 42,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brand,
  },
  accountPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    backgroundColor: c.brandLight,
  },
  heroRule: { flexDirection: 'row', gap: 6, marginTop: spacing.lg },
  ruleSegment: { flex: 1, height: 4, borderRadius: 2 },
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.lg },
  metricCard: {
    width: '48.8%',
    minHeight: 126,
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    borderTopWidth: 3,
    padding: spacing.md,
  },
  metricHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  metricIcon: { width: 30, height: 30, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  panel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  panelHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
  layerRow: {
    flexDirection: 'row',
    gap: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  layerRowFirst: { paddingTop: 0, borderTopWidth: 0 },
  layerCode: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.fill,
  },
  layerCopy: { flex: 1, minWidth: 0, paddingBottom: spacing.md },
  tagWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tag: {
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    paddingHorizontal: spacing.sm,
    paddingVertical: 7,
  },
  sourceRow: {
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
    gap: 4,
    marginTop: spacing.md,
  },
  sourceRowFirst: { paddingTop: 0, borderTopWidth: 0, marginTop: 0 },
});

const createTxt = (c: ColorPalette) => ({
  navTitle: { fontSize: 17, fontWeight: '700', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  accountPill: { fontSize: 12, fontWeight: '800', color: c.brandDark } as TextStyle,
  heroEyebrow: { fontSize: 11, fontWeight: '800', color: c.brand, letterSpacing: 0 } as TextStyle,
  heroTitle: { fontSize: 26, fontWeight: '800', color: c.labelPrimary, lineHeight: 31, marginTop: 4 } as TextStyle,
  heroCopy: { fontSize: 14, color: c.labelSecondary, lineHeight: 20, marginTop: spacing.sm } as TextStyle,
  sectionLabel: { fontSize: 12, fontWeight: '800', color: c.labelTertiary, marginBottom: spacing.sm, marginLeft: 2 } as TextStyle,
  metricDetail: { fontSize: 11, fontWeight: '700', color: c.labelTertiary, flex: 1, textAlign: 'right' } as TextStyle,
  metricValue: { fontSize: 30, fontWeight: '800', color: c.labelPrimary, marginTop: spacing.lg, fontVariant: ['tabular-nums'] } as TextStyle,
  metricLabel: { fontSize: 12, fontWeight: '700', color: c.labelSecondary, marginTop: 2 } as TextStyle,
  panelTitle: { fontSize: 16, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  layerCode: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  layerTitle: { fontSize: 14, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  layerBody: { fontSize: 13, color: c.labelSecondary, lineHeight: 19, marginTop: 3 } as TextStyle,
  tagText: { fontSize: 12, fontWeight: '700', color: c.labelSecondary } as TextStyle,
  sourceLabel: { fontSize: 12, fontWeight: '800', color: c.labelTertiary } as TextStyle,
  sourceValue: { fontSize: 14, fontWeight: '700', color: c.labelPrimary, lineHeight: 19 } as TextStyle,
  generatedNote: { fontSize: 11, color: c.labelTertiary, lineHeight: 16, marginTop: spacing.md } as TextStyle,
});
