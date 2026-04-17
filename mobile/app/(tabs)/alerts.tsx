import React, { useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl, TextStyle, LayoutAnimation,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { getSafetyReport, explainAlert, type SafetyAlert } from '@/services/safety';
import { colors, spacing, radii, shadows } from '@/constants/theme';

const SEVERITY_CONFIG: Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap; label: string }> = {
  critical: { color: '#FF453A', bg: '#FFE8E6', icon: 'alert-circle', label: '严重' },
  high:     { color: '#FF9F0A', bg: '#FFF5E6', icon: 'alert-circle-outline', label: '高' },
  medium:   { color: '#FFCC00', bg: '#FFFDF0', icon: 'warning-outline', label: '中' },
  low:      { color: '#0A8F8F', bg: '#E6F5F5', icon: 'information-circle-outline', label: '关注' },
  info:     { color: '#8E8E93', bg: '#F2F2F7', icon: 'information-outline', label: '提示' },
};

function getSeverityKey(severity: any): string {
  return typeof severity === 'string' ? severity : severity?.label ?? 'info';
}

function getSeverityLabel(severity: any): string {
  return typeof severity === 'string' ? (SEVERITY_CONFIG[severity]?.label ?? severity) : severity?.label_zh ?? severity?.label ?? 'info';
}

export default function InsightsScreen() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['safety'],
    queryFn: getSafetyReport,
  });

  const alerts = (data?.alerts || []).sort((a: any, b: any) => {
    const order = ['critical', 'high', 'medium', 'low', 'info'];
    return order.indexOf(getSeverityKey(a.severity)) - order.indexOf(getSeverityKey(b.severity));
  });

  // Group by importance
  const attention = alerts.filter((a: any) => ['critical', 'high'].includes(getSeverityKey(a.severity)));
  const suggestions = alerts.filter((a: any) => getSeverityKey(a.severity) === 'medium');
  const reminders = alerts.filter((a: any) => ['low', 'info'].includes(getSeverityKey(a.severity)));

  if (isLoading) {
    return <View style={styles.center}><ActivityIndicator size="large" color={colors.brand} /></View>;
  }

  const sections = [
    ...(attention.length > 0 ? [{ title: '需要关注', data: attention, color: '#FF453A' }] : []),
    ...(suggestions.length > 0 ? [{ title: '改善建议', data: suggestions, color: '#FF9F0A' }] : []),
    ...(reminders.length > 0 ? [{ title: '日常提醒', data: reminders, color: '#0A8F8F' }] : []),
  ];

  const allItems = sections.flatMap(s => [
    { type: 'header' as const, title: s.title, color: s.color, count: s.data.length },
    ...s.data.map((alert: any) => ({ type: 'alert' as const, alert })),
  ]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Text style={txt.screenTitle}>洞察</Text>
      {alerts.length === 0 ? (
        <EmptyState onRefresh={refetch} refreshing={isRefetching} />
      ) : (
        <FlatList
          data={allItems}
          keyExtractor={(item, idx) => `${idx}`}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
          ListHeaderComponent={
            <Text style={txt.summary}>
              {data?.rules_evaluated ?? 0} 条规则已评估 | {alerts.length} 条洞察
            </Text>
          }
          renderItem={({ item }) =>
            item.type === 'header' ? (
              <View style={styles.sectionHeaderRow}>
                <View style={[styles.sectionDot, { backgroundColor: item.color }]} />
                <Text style={txt.sectionTitle}>{item.title}</Text>
                <Text style={txt.sectionCount}>{item.count}</Text>
              </View>
            ) : (
              <AlertItem alert={item.alert} />
            )
          }
        />
      )}
    </SafeAreaView>
  );
}

function EmptyState({ onRefresh, refreshing }: { onRefresh: () => void; refreshing: boolean }) {
  return (
    <FlatList
      data={[]}
      renderItem={() => null}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      ListEmptyComponent={
        <View style={styles.empty}>
          <View style={styles.emptyCircle}>
            <Ionicons name="checkmark-circle" size={56} color={colors.green} />
          </View>
          <Text style={txt.emptyTitle}>一切正常</Text>
          <Text style={txt.emptySub}>所有健康指标都在正常范围内</Text>
        </View>
      }
    />
  );
}

function AlertItem({ alert }: { alert: SafetyAlert }) {
  const [expanded, setExpanded] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);

  const severityKey = getSeverityKey(alert.severity);
  const severityLabel = getSeverityLabel(alert.severity);
  const cfg = SEVERITY_CONFIG[severityKey] || SEVERITY_CONFIG.info;

  const handleExplain = async () => {
    if (explanation) return;
    setExplaining(true);
    try {
      const result = await explainAlert(alert.rule_id, alert.message);
      setExplanation(result.explanation);
    } catch {
      setExplanation('无法获取解读，请稍后重试');
    } finally {
      setExplaining(false);
    }
  };

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded(!expanded);
  };

  return (
    <TouchableOpacity style={styles.alertCard} onPress={toggle} activeOpacity={0.7}>
      <View style={[styles.alertAccent, { backgroundColor: cfg.color }]} />
      <View style={styles.alertBody}>
        <View style={styles.alertHeader}>
          <View style={[styles.alertIcon, { backgroundColor: cfg.bg }]}>
            <Ionicons name={cfg.icon} size={16} color={cfg.color} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={txt.alertTitle}>{alert.title}</Text>
            <Text style={txt.alertCategory}>{alert.category} · {severityLabel}</Text>
          </View>
          <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.labelTertiary} />
        </View>
        <Text style={txt.alertMessage} numberOfLines={expanded ? undefined : 2}>{alert.message}</Text>
        {alert.action && expanded && <Text style={txt.alertAction}>{alert.action}</Text>}
        {expanded && (
          <TouchableOpacity style={styles.explainBtn} onPress={handleExplain}>
            {explaining ? (
              <ActivityIndicator size="small" color={colors.brand} />
            ) : (
              <>
                <Ionicons name="sparkles" size={14} color={colors.brand} />
                <Text style={txt.explainText}>AI 解读</Text>
              </>
            )}
          </TouchableOpacity>
        )}
        {explanation && (
          <View style={styles.explanationBox}>
            <Text style={txt.explanation}>{explanation}</Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: spacing.xl, paddingTop: 0 },
  sectionHeaderRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginTop: spacing.lg, marginBottom: spacing.sm,
  },
  sectionDot: { width: 8, height: 8, borderRadius: 4 },
  alertCard: {
    flexDirection: 'row',
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    marginBottom: spacing.sm,
    overflow: 'hidden',
    ...shadows.subtle,
  },
  alertAccent: { width: 4 },
  alertBody: { flex: 1, padding: spacing.md },
  alertHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  alertIcon: { width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  explainBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: spacing.sm, paddingTop: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.separator },
  explanationBox: { backgroundColor: colors.bgPrimary, borderRadius: radii.md, padding: spacing.md, marginTop: spacing.sm },
  empty: { alignItems: 'center', paddingTop: 120 },
  emptyCircle: { width: 88, height: 88, borderRadius: 44, backgroundColor: '#E8FAF0', alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
});

const txt = {
  screenTitle: { fontSize: 34, fontWeight: '700', color: colors.labelPrimary, paddingHorizontal: spacing.xl, paddingTop: spacing.lg, paddingBottom: spacing.sm } as TextStyle,
  summary: { fontSize: 13, fontWeight: '500', color: colors.labelSecondary, marginBottom: spacing.md } as TextStyle,
  sectionTitle: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1 } as TextStyle,
  sectionCount: { fontSize: 13, fontWeight: '600', color: colors.labelTertiary } as TextStyle,
  alertTitle: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  alertCategory: { fontSize: 11, color: colors.labelTertiary, marginTop: 1 } as TextStyle,
  alertMessage: { fontSize: 14, color: colors.labelSecondary, lineHeight: 20 } as TextStyle,
  alertAction: { fontSize: 13, color: colors.brand, fontWeight: '500', marginTop: 6 } as TextStyle,
  explainText: { fontSize: 14, color: colors.brand, fontWeight: '500' } as TextStyle,
  explanation: { fontSize: 14, color: colors.labelSecondary, lineHeight: 20 } as TextStyle,
  emptyTitle: { fontSize: 22, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  emptySub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4 } as TextStyle,
};
