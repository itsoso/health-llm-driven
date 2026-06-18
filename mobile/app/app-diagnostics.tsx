import React, { useMemo, useState } from 'react';
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

import { getAppDiagnosticsSnapshot, type AppDiagnosticRow } from '../services/appDiagnostics';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette, type SemanticPalette } from '../hooks/useTheme';

function launchTone(source: string, s: SemanticPalette) {
  if (source === 'embedded') return s.success;
  if (source === 'ota') return s.info;
  return s.warning;
}

function Row({ row }: { row: AppDiagnosticRow }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <View style={styles.row}>
      <Text style={txt.rowLabel}>{row.label}</Text>
      <Text style={txt.rowValue} selectable numberOfLines={3}>{row.value}</Text>
    </View>
  );
}

export default function AppDiagnosticsScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [refreshKey, setRefreshKey] = useState(0);
  const snapshot = useMemo(() => getAppDiagnosticsSnapshot(), [refreshKey]);
  const tone = launchTone(snapshot.summary.launchSource, s);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconButton} accessibilityRole="button" accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>App 诊断</Text>
        <Pressable
          onPress={() => setRefreshKey((value) => value + 1)}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="刷新 App 诊断"
        >
          <Ionicons name="refresh" size={20} color={c.labelSecondary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.summaryCard, { backgroundColor: tone.bg }]}>
          <View style={styles.summaryHeader}>
            <View style={[styles.summaryIcon, { backgroundColor: tone.solid }]}>
              <Ionicons name="git-branch-outline" size={18} color="#fff" />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[txt.summaryTitle, { color: tone.fg }]}>
                {snapshot.summary.channel}
              </Text>
              <Text style={[txt.summaryMeta, { color: tone.fg }]}>
                {snapshot.summary.appVersion} ({snapshot.summary.buildNumber}) · {snapshot.summary.launchSource}
              </Text>
            </View>
          </View>
          <View style={styles.summaryGrid}>
            <SummaryPill label="Runtime" value={snapshot.summary.runtimeVersion} />
            <SummaryPill label="Channel" value={snapshot.summary.channel} />
            <SummaryPill label="Bundle" value={snapshot.summary.launchSource} />
          </View>
        </View>

        <View style={styles.card}>
          <Text style={txt.sectionTitle}>运行时</Text>
          {snapshot.rows.map((row) => (
            <Row key={row.id} row={row} />
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );

  function SummaryPill({ label, value }: { label: string; value: string }) {
    return (
      <View style={styles.summaryPill}>
        <Text style={txt.pillLabel}>{label}</Text>
        <Text style={txt.pillValue} numberOfLines={1}>{value}</Text>
      </View>
    );
  }
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
  content: { padding: spacing.lg, paddingBottom: 110 },
  summaryCard: {
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  summaryHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: spacing.md },
  summaryIcon: { width: 36, height: 36, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  summaryGrid: { flexDirection: 'row', gap: 8 },
  summaryPill: {
    flex: 1,
    minHeight: 54,
    borderRadius: radii.sm,
    backgroundColor: c.bgCard,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    justifyContent: 'center',
  },
  card: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    overflow: 'hidden',
  },
  row: {
    paddingHorizontal: spacing.lg,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
    gap: 4,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '700', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  summaryTitle: { fontSize: 18, fontWeight: '800' } as TextStyle,
  summaryMeta: { fontSize: 13, marginTop: 3 } as TextStyle,
  pillLabel: { fontSize: 11, fontWeight: '700', color: c.labelTertiary, marginBottom: 4 } as TextStyle,
  pillValue: { fontSize: 13, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary, padding: spacing.lg } as TextStyle,
  rowLabel: { fontSize: 12, fontWeight: '700', color: c.labelTertiary } as TextStyle,
  rowValue: { fontSize: 14, fontWeight: '600', color: c.labelPrimary, lineHeight: 19 } as TextStyle,
});
