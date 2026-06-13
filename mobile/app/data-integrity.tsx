/**
 * /data-integrity —— 数据自检(消费后端 GET /data-health/integrity,PR #152)。
 *
 * 诊断性页面:展示 healthy 总判 + issues 列表(量纲/范围/层断连等静默损坏)。
 * 区别于"数据完整度"(/status):这里查**正确性**。空 issues = 健康。
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
  fetchDataIntegrity,
  sortIntegrityIssues,
  type IntegrityIssue,
} from '../services/dataHealth';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette, type SemanticPalette } from '../hooks/useTheme';

function severityTone(sev: string, s: SemanticPalette) {
  switch (sev) {
    case 'critical':
      return s.danger;
    case 'warning':
      return s.warning;
    default:
      return s.info;
  }
}

function IssueCard({ issue }: { issue: IntegrityIssue }) {
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const tone = severityTone(issue.severity, s);
  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.issueHeader}>
        <View style={[styles.dot, { backgroundColor: tone.solid }]} />
        <Text style={[styles.issueDetail, { color: c.labelPrimary }]}>{issue.detail}</Text>
        {issue.count > 0 ? (
          <View style={[styles.countBadge, { backgroundColor: tone.bg }]}>
            <Text style={[styles.countText, { color: tone.fg }]}>{issue.count}</Text>
          </View>
        ) : null}
      </View>
      {issue.fix_hint ? (
        <Text style={[styles.fixHint, { color: c.labelSecondary }]}>{issue.fix_hint}</Text>
      ) : null}
    </View>
  );
}

export default function DataIntegrityScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ['data-integrity'],
    queryFn: fetchDataIntegrity,
    staleTime: 5 * 60 * 1000,
  });

  const issues = useMemo(() => (data ? sortIntegrityIssues(data.issues) : []), [data]);

  const header = (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} hitSlop={10} accessibilityLabel="返回">
        <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
      </TouchableOpacity>
      <Text style={[styles.title, { color: c.labelPrimary }]}>数据自检</Text>
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
            {/* 总判 */}
            <View
              style={[
                styles.statusCard,
                {
                  backgroundColor: data.healthy ? s.success.bg : s.warning.bg,
                  borderColor: c.separator,
                },
              ]}
            >
              <Ionicons
                name={data.healthy ? 'shield-checkmark' : 'alert-circle'}
                size={28}
                color={data.healthy ? s.success.solid : s.warning.solid}
              />
              <View style={{ flex: 1 }}>
                <Text
                  style={[
                    styles.statusTitle,
                    { color: data.healthy ? s.success.fg : s.warning.fg },
                  ]}
                >
                  {data.healthy ? '数据健康' : `发现 ${data.issue_count} 项待处理`}
                </Text>
                <Text
                  style={[
                    styles.statusBody,
                    { color: data.healthy ? s.success.fg : s.warning.fg },
                  ]}
                >
                  {data.healthy
                    ? '量纲、范围与各数据层连接均正常。'
                    : '检测到量纲/范围或数据层连接异常,处理后分析会更可信。'}
                </Text>
              </View>
            </View>

            {issues.map((it, i) => (
              <IssueCard key={`${it.code}-${i}`} issue={it} />
            ))}

            <Text style={[styles.footer, { color: c.labelTertiary }]}>
              数据自检检查的是数据的「正确性」(量纲/范围/层连接),与「完整度」不同。
            </Text>
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
    statusCard: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      borderRadius: radii.lg,
      borderWidth: StyleSheet.hairlineWidth,
      padding: spacing.md,
    },
    statusTitle: { fontSize: 16, fontWeight: '800' },
    statusBody: { fontSize: 13, lineHeight: 19, marginTop: 2 },
    card: { borderRadius: radii.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.md, gap: 6 },
    issueHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    dot: { width: 8, height: 8, borderRadius: 4 },
    issueDetail: { fontSize: 14, fontWeight: '700', flex: 1, lineHeight: 20 },
    countBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
    countText: { fontSize: 12, fontWeight: '700' },
    fixHint: { fontSize: 13, lineHeight: 19, paddingLeft: 16 },
    footer: { fontSize: 12, textAlign: 'center', lineHeight: 18, marginTop: spacing.sm },
  });
