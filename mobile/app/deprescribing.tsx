/**
 * /deprescribing —— 多药梳理 / 减药候选(消费后端 GET /medication/deprescribing-review/me,PR #154)。
 *
 * 展示:在用药数 + 多药徽章 + 每条 flag(detail + suggestion)+ 底部免责。
 * ⚠️ 安全红线:文案**全部照搬后端**,绝不出现"停药/减量"命令,统一"与医生讨论"。
 */
import React, { useMemo } from 'react';
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
  getDeprescribingReview,
  type DeprescribingFlag,
} from '../services/medications';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette, type SemanticPalette } from '../hooks/useTheme';

function flagTone(code: string, s: SemanticPalette) {
  switch (code) {
    case 'polypharmacy':
    case 'duplicate_class':
      return s.warning;
    case 'expired_still_active':
      return s.info;
    default:
      return s.neutral;
  }
}

function FlagCard({ flag }: { flag: DeprescribingFlag }) {
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const tone = flagTone(flag.code, s);
  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.flagHeader}>
        <View style={[styles.dot, { backgroundColor: tone.solid }]} />
        <Text style={[styles.flagDetail, { color: c.labelPrimary }]}>{flag.detail}</Text>
      </View>
      <View style={[styles.suggestionBox, { backgroundColor: tone.bg }]}>
        <Text style={[styles.suggestionText, { color: tone.fg }]}>{flag.suggestion}</Text>
      </View>
    </View>
  );
}

export default function DeprescribingScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ['deprescribing-review'],
    queryFn: getDeprescribingReview,
    staleTime: 5 * 60 * 1000,
  });

  const header = (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} hitSlop={10} accessibilityLabel="返回">
        <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
      </TouchableOpacity>
      <Text style={[styles.title, { color: c.labelPrimary }]}>多药梳理</Text>
      <View style={{ width: 24 }} />
    </View>
  );

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      {header}

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        {isLoading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={c.labelTertiary} />
        ) : error ? (
          <Text style={[styles.empty, { color: c.labelTertiary }]}>加载失败,下拉重试</Text>
        ) : !data ? null : (
          <>
            {/* 概览:在用药数 + 多药徽章 */}
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.overviewRow}>
                <View>
                  <Text style={[styles.overviewLabel, { color: c.labelSecondary }]}>当前在用药</Text>
                  <Text style={[styles.overviewValue, { color: c.labelPrimary }]}>
                    {data.active_count} 种
                  </Text>
                </View>
                {data.is_polypharmacy && (
                  <View style={[styles.badge, { backgroundColor: s.warning.solid }]}>
                    <Text style={styles.badgeText}>多药</Text>
                  </View>
                )}
              </View>
            </View>

            {/* flags */}
            {data.flags.length > 0 ? (
              data.flags.map((f, i) => <FlagCard key={`${f.code}-${i}`} flag={f} />)
            ) : (
              <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                <Text style={[styles.okTitle, { color: c.labelPrimary }]}>暂无减药候选提示</Text>
                <Text style={[styles.okBody, { color: c.labelTertiary }]}>
                  当前用药未触发多药、同类重复或长期使用等候选规则。用药有变化后可再下拉刷新。
                </Text>
              </View>
            )}

            {/* 免责 —— 照搬后端 disclaimer */}
            <View style={[styles.disclaimerBox, { backgroundColor: s.neutral.bg }]}>
              <Ionicons name="information-circle-outline" size={16} color={c.labelSecondary} />
              <Text style={[styles.disclaimer, { color: c.labelSecondary }]}>{data.disclaimer}</Text>
            </View>
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
    content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },
    empty: { fontSize: 14, textAlign: 'center', marginTop: 40, lineHeight: 20 },
    card: { borderRadius: radii.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.md, gap: 8 },
    overviewRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    overviewLabel: { fontSize: 13, fontWeight: '500' },
    overviewValue: { fontSize: 24, fontWeight: '800', marginTop: 2 },
    badge: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 12 },
    badgeText: { color: '#fff', fontSize: 13, fontWeight: '700' },
    flagHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
    dot: { width: 8, height: 8, borderRadius: 4, marginTop: 6 },
    flagDetail: { fontSize: 15, fontWeight: '700', flex: 1, lineHeight: 21 },
    suggestionBox: { borderRadius: radii.md, paddingHorizontal: 12, paddingVertical: 10 },
    suggestionText: { fontSize: 13, lineHeight: 19 },
    okTitle: { fontSize: 15, fontWeight: '800' },
    okBody: { fontSize: 13, lineHeight: 19 },
    disclaimerBox: {
      flexDirection: 'row',
      gap: 8,
      alignItems: 'flex-start',
      borderRadius: radii.md,
      paddingHorizontal: 12,
      paddingVertical: 10,
      marginTop: spacing.sm,
    },
    disclaimer: { fontSize: 12, lineHeight: 18, flex: 1 },
  });
