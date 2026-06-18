import React, { useMemo } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { getRokidSelfCheck, type RokidSelfCheckItem } from '../services/rokidDiagnostics';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette, type SemanticPalette } from '../hooks/useTheme';

function severityTone(severity: RokidSelfCheckItem['severity'], s: SemanticPalette) {
  switch (severity) {
    case 'pass':
      return s.success;
    case 'block':
      return s.danger;
    case 'warn':
      return s.warning;
    default:
      return s.info;
  }
}

function severityIcon(severity: RokidSelfCheckItem['severity']): keyof typeof Ionicons.glyphMap {
  switch (severity) {
    case 'pass':
      return 'checkmark-circle';
    case 'block':
      return 'close-circle';
    case 'warn':
      return 'alert-circle';
    default:
      return 'information-circle';
  }
}

export default function RokidDiagnosticsScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const query = useQuery({
    queryKey: ['rokid-diagnostics'],
    queryFn: getRokidSelfCheck,
    staleTime: 15_000,
  });

  const check = query.data;
  const blocking = check?.items.some((item) => item.severity === 'block') === true;
  const warning = check?.items.some((item) => item.severity === 'warn') === true;
  const summaryTone = blocking ? s.danger : warning ? s.warning : s.success;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconButton} accessibilityRole="button" accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>Rokid 自检</Text>
        <Pressable onPress={() => query.refetch()} style={styles.iconButton} accessibilityRole="button" accessibilityLabel="刷新 Rokid 自检">
          <Ionicons name="refresh" size={20} color={c.labelSecondary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={query.refetch} />}
      >
        {query.isLoading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={c.labelTertiary} />
        ) : query.isError || !check ? (
          <Text style={txt.empty}>Rokid 自检失败, 下拉重试。</Text>
        ) : (
          <>
            <View style={[styles.summaryCard, { backgroundColor: summaryTone.bg }]}>
              <Ionicons
                name={blocking ? 'close-circle' : warning ? 'alert-circle' : 'checkmark-circle'}
                size={28}
                color={summaryTone.solid}
              />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[txt.summaryTitle, { color: summaryTone.fg }]}>
                  {blocking ? '存在阻塞项' : warning ? '需要继续验证' : '链路就绪'}
                </Text>
                <Text style={[txt.summaryMeta, { color: summaryTone.fg }]}>
                  Bridge {check.summary.bridge} · SDK {check.summary.sdk} · Session {check.summary.session}
                </Text>
              </View>
            </View>

            <View style={styles.card}>
              <Text style={txt.sectionTitle}>状态</Text>
              {check.items.map((item) => (
                <StatusRow key={item.id} item={item} />
              ))}
            </View>

            <View style={styles.card}>
              <Text style={txt.sectionTitle}>真机验证</Text>
              {check.validationSteps.map((step) => (
                <View key={step.id} style={styles.stepRow}>
                  <View style={[styles.stepIcon, step.status === 'done' ? { backgroundColor: s.success.bg } : { backgroundColor: c.fill }]}>
                    <Ionicons
                      name={step.status === 'done' ? 'checkmark' : step.status === 'blocked' ? 'close' : 'ellipse-outline'}
                      size={16}
                      color={step.status === 'done' ? s.success.solid : step.status === 'blocked' ? s.danger.solid : c.labelTertiary}
                    />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={txt.stepTitle}>{step.title}</Text>
                    <Text style={txt.stepDetail}>{step.detail}</Text>
                  </View>
                  <Text style={txt.stepStatus}>{step.status}</Text>
                </View>
              ))}
            </View>

            <Pressable
              onPress={() => router.push('/rokid-health' as any)}
              style={styles.primaryButton}
              accessibilityRole="button"
            >
              <Ionicons name="scan-outline" size={17} color="#fff" />
              <Text style={txt.primaryButton}>打开 Rokid 健康模式</Text>
            </Pressable>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );

  function StatusRow({ item }: { item: RokidSelfCheckItem }) {
    const tone = severityTone(item.severity, s);
    return (
      <View style={styles.statusRow}>
        <Ionicons name={severityIcon(item.severity)} size={19} color={tone.solid} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={txt.statusLabel}>{item.label}</Text>
          {item.detail ? <Text style={txt.statusDetail} numberOfLines={2}>{item.detail}</Text> : null}
        </View>
        <Text style={[txt.statusValue, { color: tone.fg }]} numberOfLines={2}>{item.value}</Text>
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
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  card: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    overflow: 'hidden',
    marginBottom: spacing.md,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: spacing.lg,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: spacing.lg,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  stepIcon: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  primaryButton: {
    minHeight: 44,
    borderRadius: radii.sm,
    backgroundColor: c.brand,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '700', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  summaryTitle: { fontSize: 17, fontWeight: '800' } as TextStyle,
  summaryMeta: { fontSize: 13, marginTop: 3 } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary, padding: spacing.lg } as TextStyle,
  statusLabel: { fontSize: 14, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  statusDetail: { fontSize: 12, color: c.labelTertiary, marginTop: 2, lineHeight: 17 } as TextStyle,
  statusValue: { width: 116, textAlign: 'right', fontSize: 12, fontWeight: '700', lineHeight: 17 } as TextStyle,
  stepTitle: { fontSize: 14, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  stepDetail: { fontSize: 12, color: c.labelSecondary, marginTop: 2, lineHeight: 17 } as TextStyle,
  stepStatus: { width: 52, textAlign: 'right', fontSize: 11, fontWeight: '700', color: c.labelTertiary } as TextStyle,
  primaryButton: { color: '#fff', fontSize: 15, fontWeight: '800' } as TextStyle,
  empty: { fontSize: 14, color: c.labelTertiary, textAlign: 'center', marginTop: 40 } as TextStyle,
});
