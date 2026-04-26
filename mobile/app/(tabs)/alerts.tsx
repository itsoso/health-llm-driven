import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl, TextStyle, LayoutAnimation, SectionList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { getSafetyReport, explainAlert, type SafetyAlert } from '@/services/safety';
import { buildActionCockpitSections, getActiveCards, completeCard } from '@/services/actionCards';
import InterventionCard from '@/components/actions/InterventionCard';
import { queryKeys } from '@/lib/queryKeys';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function getSeverityKey(s: any): string { return typeof s === 'string' ? s : s?.label ?? 'info'; }

const SEV: Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap }> = {
  critical: { color: '#FF453A', bg: '#FFE8E6', icon: 'alert-circle' },
  high: { color: '#FF9F0A', bg: '#FFF5E6', icon: 'alert-circle-outline' },
  medium: { color: '#FFCC00', bg: '#FFFDF0', icon: 'warning-outline' },
  low: { color: '#0A8F8F', bg: '#E6F5F5', icon: 'information-circle-outline' },
  info: { color: '#8E8E93', bg: '#F2F2F7', icon: 'information-outline' },
};

const SECTION_META: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  需要立即处理: { icon: 'alert-circle', color: '#FF453A' },
  正在执行: { icon: 'rocket-outline', color: colors.brand },
  等待验证: { icon: 'checkmark-done-outline', color: '#007AFF' },
  日常提示: { icon: 'bulb-outline', color: '#FF9F0A' },
};

export default function ActionsScreen() {
  const { data: safetyData, refetch: refetchSafety, isRefetching: sr, isLoading: sl } = useQuery({ queryKey: queryKeys.safety, queryFn: getSafetyReport });
  const { data: cardsData, refetch: refetchCards, isRefetching: cr, isLoading: cl } = useQuery({ queryKey: queryKeys.actionCards, queryFn: getActiveCards });

  const alerts = safetyData?.alerts || [];
  const cards = cardsData || [];
  const refetchAll = () => { refetchSafety(); refetchCards(); };

  const sections = buildActionCockpitSections(alerts, cards);

  const isEmpty = alerts.length === 0 && cards.length === 0;
  const totalActions = cards.length + alerts.filter((a: any) => ['critical', 'high'].includes(getSeverityKey(a.severity))).length;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={txt.title}>行动</Text>
        {totalActions > 0 && (
          <View style={styles.countBadge}>
            <Text style={txt.countText}>{totalActions}</Text>
          </View>
        )}
      </View>

      {(sl || cl) ? (
        <View style={styles.empty}>
          <ActivityIndicator size="large" color={colors.brand} />
          <Text style={txt.emptySub}>加载中...</Text>
        </View>
      ) : isEmpty ? (
        <View style={styles.empty}>
          <View style={styles.emptyCircle}>
            <Ionicons name="checkmark-done" size={40} color={colors.brand} />
          </View>
          <Text style={txt.emptyTitle}>一切正常</Text>
          <Text style={txt.emptySub}>暂无待办行动，继续保持</Text>
          <TouchableOpacity style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 16, backgroundColor: colors.brandLight, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }} onPress={refetchAll} accessibilityLabel="刷新行动列表" accessibilityRole="button">
            <Ionicons name="refresh-outline" size={14} color={colors.brand} />
            <Text style={{ fontSize: 14, fontWeight: '500', color: colors.brand }}>刷新</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item, idx) => `${item.type}-${idx}`}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled={false}
          refreshControl={<RefreshControl refreshing={sr || cr} onRefresh={refetchAll} tintColor={colors.brand} />}
          renderSectionHeader={({ section }) => (
            <View style={styles.sectionHeader}>
              <View style={[styles.sectionIconWrap, { backgroundColor: `${SECTION_META[section.title].color}18` }]}>
                <Ionicons name={SECTION_META[section.title].icon} size={14} color={SECTION_META[section.title].color} />
              </View>
              <Text style={txt.sectionTitle}>{section.title}</Text>
              <View style={[styles.sectionCountBadge, { backgroundColor: `${SECTION_META[section.title].color}18` }]}>
                <Text style={[txt.sectionCount, { color: SECTION_META[section.title].color }]}>{section.data.length}</Text>
              </View>
            </View>
          )}
          renderItem={({ item }) =>
            item.type === 'alert'
              ? <AlertRow alert={item.item} />
              : <InterventionCard card={item.item} onComplete={async () => { await completeCard(item.item.id); refetchCards(); }} />
          }
          SectionSeparatorComponent={() => <View style={{ height: 8 }} />}
        />
      )}
    </SafeAreaView>
  );
}

function AlertRow({ alert }: { alert: SafetyAlert }) {
  const [expanded, setExpanded] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const sk = getSeverityKey(alert.severity);
  const cfg = SEV[sk] || SEV.info;

  return (
    <TouchableOpacity style={styles.alertCard} onPress={() => { LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut); setExpanded(!expanded); }} activeOpacity={0.7}
      accessibilityRole="button" accessibilityLabel={`${sk}级别告警: ${alert.title}`} accessibilityState={{ expanded }}>
      <View style={styles.alertRow}>
        <View style={[styles.alertIconWrap, { backgroundColor: cfg.bg }]}>
          <Ionicons name={cfg.icon} size={16} color={cfg.color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={txt.alertTitle} numberOfLines={expanded ? undefined : 2}>{alert.title}</Text>
          {!expanded && alert.message && <Text style={txt.alertPreview} numberOfLines={1}>{alert.message}</Text>}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-forward'} size={14} color={colors.labelTertiary} />
      </View>
      {expanded && (
        <View style={styles.expandedContent}>
          <Text style={txt.alertMsg}>{alert.message}</Text>
          {alert.action && <Text style={txt.alertAction}>→ {alert.action}</Text>}
          {!explanation && (
            <TouchableOpacity style={styles.aiBtn} accessibilityLabel="让 AI 解读这条告警" accessibilityRole="button" onPress={async () => {
              setExplaining(true);
              try { const r = await explainAlert(alert.rule_id, alert.message); setExplanation(r.explanation); } catch { setExplanation('无法获取解读'); } finally { setExplaining(false); }
            }}>
              {explaining ? <ActivityIndicator size="small" color={colors.brand} /> : <>
                <Ionicons name="sparkles" size={13} color={colors.brand} />
                <Text style={txt.aiText}>AI 解读</Text>
              </>}
            </TouchableOpacity>
          )}
          {explanation && (
            <View style={styles.aiResult}>
              <Ionicons name="sparkles" size={12} color={colors.brand} />
              <Text style={txt.aiResultText}>{explanation}</Text>
            </View>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: spacing.xl, paddingTop: spacing.lg, paddingBottom: spacing.md,
  },
  countBadge: {
    backgroundColor: colors.brand, borderRadius: 10,
    paddingHorizontal: 8, paddingVertical: 2,
  },
  list: { paddingHorizontal: spacing.lg, paddingBottom: 100 },
  sectionHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 10,
  },
  sectionIconWrap: { width: 24, height: 24, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  sectionCountBadge: { borderRadius: 8, paddingHorizontal: 7, paddingVertical: 2 },

  // Alert card
  alertCard: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    marginBottom: 8, ...shadows.subtle,
  },
  alertRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14,
  },
  alertIconWrap: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  expandedContent: {
    paddingHorizontal: 14, paddingBottom: 14, paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator, marginTop: -2,
  },
  aiBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 10 },
  aiResult: {
    flexDirection: 'row', gap: 6, marginTop: 10,
    backgroundColor: colors.bgPrimary, borderRadius: radii.md, padding: 12,
  },

  // Empty
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10, paddingBottom: 80 },
  emptyCircle: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: colors.brandLight, alignItems: 'center', justifyContent: 'center',
  },
});

const txt = {
  title: { fontSize: 28, fontWeight: '700', color: colors.labelPrimary, flex: 1 } as TextStyle,
  countText: { fontSize: 12, fontWeight: '700', color: '#fff' } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, flex: 1 } as TextStyle,
  sectionCount: { fontSize: 12, fontWeight: '600' } as TextStyle,
  alertTitle: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, lineHeight: 20 } as TextStyle,
  alertPreview: { fontSize: 12, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
  alertMsg: { fontSize: 14, color: colors.labelSecondary, lineHeight: 20 } as TextStyle,
  alertAction: { fontSize: 13, color: colors.brand, fontWeight: '500', marginTop: 8 } as TextStyle,
  aiText: { fontSize: 13, color: colors.brand, fontWeight: '500' } as TextStyle,
  aiResultText: { fontSize: 13, color: colors.labelSecondary, lineHeight: 19, flex: 1 } as TextStyle,
  emptyTitle: { fontSize: 20, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  emptySub: { fontSize: 14, color: colors.labelSecondary } as TextStyle,
};
