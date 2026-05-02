import React, { useMemo, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl, TextStyle, LayoutAnimation, SectionList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { getSafetyReport, explainAlert, type SafetyAlert } from '../../services/safety';
import { buildActionCockpitSections, getActiveCards, completeCard, reviewActionCard } from '../../services/actionCards';
import InterventionCard from '../../components/actions/InterventionCard';
import { ExplainButton } from '../../components/reasoning/ExplainButton';
import { queryKeys } from '../../applib/queryKeys';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

function getSeverityKey(s: any): string { return typeof s === 'string' ? s : s?.label ?? 'info'; }

function severityMeta(c: ColorPalette): Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap }> {
  return {
    critical: { color: c.red,            bg: c.tintRed,    icon: 'alert-circle' },
    high:     { color: c.amber,          bg: c.tintAmber,  icon: 'alert-circle-outline' },
    medium:   { color: '#FFCC00',        bg: c.tintAmber,  icon: 'warning-outline' },
    low:      { color: c.brand,          bg: c.brandLight, icon: 'information-circle-outline' },
    info:     { color: c.labelTertiary,  bg: c.bgPrimary,  icon: 'information-outline' },
  };
}

function sectionMeta(c: ColorPalette): Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string }> {
  return {
    需要立即处理: { icon: 'alert-circle',          color: c.red },
    正在执行:     { icon: 'rocket-outline',         color: c.brand },
    等待验证:     { icon: 'checkmark-done-outline', color: '#0A84FF' },
    日常提示:     { icon: 'bulb-outline',           color: c.amber },
  };
}

export default function ActionsScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const SECTION_META = useMemo(() => sectionMeta(c), [c]);
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
        <View style={{ flex: 1 }} />
        <TouchableOpacity
          style={styles.journalBtn}
          onPress={() => router.push('/trace')}
          accessibilityLabel="查看推理回放"
          accessibilityRole="button"
        >
          <Ionicons name="git-network-outline" size={16} color={c.brand} />
          <Text style={styles.journalBtnText}>回放</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.journalBtn}
          onPress={() => router.push('/journal')}
          accessibilityLabel="查看案例时间线"
          accessibilityRole="button"
        >
          <Ionicons name="document-text-outline" size={16} color={c.brand} />
          <Text style={styles.journalBtnText}>时间线</Text>
        </TouchableOpacity>
      </View>

      {(sl || cl) ? (
        <View style={styles.empty}>
          <ActivityIndicator size="large" color={c.brand} />
          <Text style={txt.emptySub}>加载中...</Text>
        </View>
      ) : isEmpty ? (
        <View style={styles.empty}>
          <View style={styles.emptyCircle}>
            <Ionicons name="checkmark-done" size={40} color={c.brand} />
          </View>
          <Text style={txt.emptyTitle}>一切正常</Text>
          <Text style={txt.emptySub}>暂无待办行动，继续保持</Text>
          <TouchableOpacity style={styles.refreshBtn} onPress={refetchAll} accessibilityLabel="刷新行动列表" accessibilityRole="button">
            <Ionicons name="refresh-outline" size={14} color={c.brand} />
            <Text style={styles.refreshBtnText}>刷新</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item, idx) => `${item.type}-${idx}`}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled={false}
          refreshControl={<RefreshControl refreshing={sr || cr} onRefresh={refetchAll} tintColor={c.brand} />}
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
              ? <AlertRow alert={item.item} auditId={safetyData?.audit_id ?? null} />
              : <InterventionCard
                  card={item.item}
                  onComplete={async () => { await completeCard(item.item.id); refetchCards(); }}
                  onReview={async draft => { await reviewActionCard(item.item.id, draft); refetchCards(); }}
                />
          }
          SectionSeparatorComponent={() => <View style={{ height: 8 }} />}
        />
      )}
    </SafeAreaView>
  );
}

function buildAskPrompt(title: string, message: string, action?: string): string {
  const parts = [`我刚看到这条告警：「${title}」。`, message];
  if (action) parts.push(`建议：${action}。`);
  parts.push('请结合我的身体数据，详细分析原因、风险和下一步建议。');
  return parts.join('\n');
}

function AlertRow({ alert, auditId }: { alert: SafetyAlert; auditId: number | null }) {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const SEV = useMemo(() => severityMeta(c), [c]);
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
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-forward'} size={14} color={c.labelTertiary} />
      </View>
      {expanded && (
        <View style={styles.expandedContent}>
          <Text style={txt.alertMsg}>{alert.message}</Text>
          {alert.action && <Text style={txt.alertAction}>→ {alert.action}</Text>}
          <View style={styles.actionRow}>
            {!explanation && (
              <TouchableOpacity style={styles.aiBtn} accessibilityLabel="让 AI 解读这条告警" accessibilityRole="button" onPress={async () => {
                setExplaining(true);
                try { const r = await explainAlert(alert.rule_id, alert.message); setExplanation(r.explanation); } catch { setExplanation('无法获取解读'); } finally { setExplaining(false); }
              }}>
                {explaining ? <ActivityIndicator size="small" color={c.brand} /> : <>
                  <Ionicons name="sparkles" size={13} color={c.brand} />
                  <Text style={txt.aiText}>AI 解读</Text>
                </>}
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={styles.aiBtn}
              accessibilityLabel="问 AI 详细分析"
              accessibilityRole="button"
              onPress={() => {
                const prompt = buildAskPrompt(alert.title, alert.message, alert.action);
                router.push({
                  pathname: '/(tabs)/chat',
                  params: { prompt, badge: alert.title },
                } as any);
              }}
            >
              <Ionicons name="chatbubble-ellipses-outline" size={13} color={c.brand} />
              <Text style={txt.aiText}>问 AI</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.aiBtn}
              accessibilityLabel="查看推理 — 这条告警背后的数据与规则"
              accessibilityRole="link"
              onPress={() => router.push('/trace')}
            >
              <Ionicons name="git-network-outline" size={13} color={c.brand} />
              <Text style={txt.aiText}>查看推理</Text>
            </TouchableOpacity>
            {auditId !== null && (
              <View style={{ marginTop: 10, justifyContent: 'center' }}>
                <ExplainButton source="safety" auditId={auditId} ruleId={alert.rule_id} />
              </View>
            )}
          </View>
          {explanation && (
            <View style={styles.aiResult}>
              <Ionicons name="sparkles" size={12} color={c.brand} />
              <Text style={txt.aiResultText}>{explanation}</Text>
            </View>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center', gap: 10,
      paddingHorizontal: spacing.xl, paddingTop: spacing.lg, paddingBottom: spacing.md,
    },
    countBadge: {
      backgroundColor: c.brand, borderRadius: 10,
      paddingHorizontal: 8, paddingVertical: 2,
    },
    journalBtn: {
      flexDirection: 'row', alignItems: 'center', gap: 4,
      backgroundColor: c.brandLight, borderRadius: 16,
      paddingHorizontal: 10, paddingVertical: 6,
    },
    journalBtnText: {
      fontSize: 12, fontWeight: '600' as const, color: c.brand,
    },
    list: { paddingHorizontal: spacing.lg, paddingBottom: 100 },
    sectionHeader: {
      flexDirection: 'row', alignItems: 'center', gap: 8,
      paddingVertical: 10,
    },
    sectionIconWrap: { width: 24, height: 24, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
    sectionCountBadge: { borderRadius: 8, paddingHorizontal: 7, paddingVertical: 2 },
    alertCard: {
      backgroundColor: c.bgCard, borderRadius: radii.lg,
      marginBottom: 8,
      shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
      shadowOpacity: 0.06, shadowRadius: 3, elevation: 1,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
    },
    alertRow: {
      flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14,
    },
    alertIconWrap: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    expandedContent: {
      paddingHorizontal: 14, paddingBottom: 14, paddingTop: 12,
      borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator, marginTop: -2,
    },
    aiBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 10 },
    actionRow: { flexDirection: 'row', gap: 16 },
    aiResult: {
      flexDirection: 'row', gap: 6, marginTop: 10,
      backgroundColor: c.bgPrimary, borderRadius: radii.md, padding: 12,
    },
    empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10, paddingBottom: 80 },
    emptyCircle: {
      width: 80, height: 80, borderRadius: 40,
      backgroundColor: c.brandLight, alignItems: 'center', justifyContent: 'center',
    },
    refreshBtn: {
      flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 16,
      backgroundColor: c.brandLight, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
    },
    refreshBtnText: { fontSize: 14, fontWeight: '500' as const, color: c.brand },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 28, fontWeight: '700', color: c.labelPrimary, flex: 1 } as TextStyle,
    countText: { fontSize: 12, fontWeight: '700', color: '#fff' } as TextStyle,
    sectionTitle: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, flex: 1 } as TextStyle,
    sectionCount: { fontSize: 12, fontWeight: '600' } as TextStyle,
    alertTitle: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, lineHeight: 20 } as TextStyle,
    alertPreview: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
    alertMsg: { fontSize: 14, color: c.labelSecondary, lineHeight: 20 } as TextStyle,
    alertAction: { fontSize: 13, color: c.brand, fontWeight: '500', marginTop: 8 } as TextStyle,
    aiText: { fontSize: 13, color: c.brand, fontWeight: '500' } as TextStyle,
    aiResultText: { fontSize: 13, color: c.labelSecondary, lineHeight: 19, flex: 1 } as TextStyle,
    emptyTitle: { fontSize: 20, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    emptySub: { fontSize: 14, color: c.labelSecondary } as TextStyle,
  };
}
