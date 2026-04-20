import React, { useState, useRef } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl, TextStyle, LayoutAnimation, SectionList,
} from 'react-native';
// @ts-ignore - react-native-gesture-handler is bundled with expo-router
import { Swipeable } from 'react-native-gesture-handler';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-native-markdown-display';
import { getSafetyReport, explainAlert, type SafetyAlert } from '@/services/safety';
import { getActiveCards, completeCard, type ActionCard } from '@/services/actionCards';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function getSeverityKey(s: any): string { return typeof s === 'string' ? s : s?.label ?? 'info'; }

const SEV: Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap }> = {
  critical: { color: '#FF453A', bg: '#FFE8E6', icon: 'alert-circle' },
  high: { color: '#FF9F0A', bg: '#FFF5E6', icon: 'alert-circle-outline' },
  medium: { color: '#FFCC00', bg: '#FFFDF0', icon: 'warning-outline' },
  low: { color: '#0A8F8F', bg: '#E6F5F5', icon: 'information-circle-outline' },
  info: { color: '#8E8E93', bg: '#F2F2F7', icon: 'information-outline' },
};

const CARD_TYPE: Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap; label: string }> = {
  guide: { color: '#0A8F8F', bg: '#E6F5F5', icon: 'compass-outline', label: '指南' },
  plan: { color: '#AF52DE', bg: '#F5E6FF', icon: 'calendar-outline', label: '计划' },
  recommendation: { color: '#30D158', bg: '#E8FAF0', icon: 'bulb-outline', label: '建议' },
  reminder: { color: '#FF9F0A', bg: '#FFF5E6', icon: 'alarm-outline', label: '提醒' },
  insight: { color: '#007AFF', bg: '#E6F0FF', icon: 'analytics-outline', label: '洞察' },
};

export default function ActionsScreen() {
  const qc = useQueryClient();
  const { data: safetyData, refetch: refetchSafety, isRefetching: sr, isLoading: sl } = useQuery({ queryKey: ['safety'], queryFn: getSafetyReport });
  const { data: cardsData, refetch: refetchCards, isRefetching: cr, isLoading: cl } = useQuery({ queryKey: ['actionCards'], queryFn: getActiveCards });

  const alerts = (safetyData?.alerts || []).sort((a: any, b: any) => {
    const order = ['critical', 'high', 'medium', 'low', 'info'];
    return order.indexOf(getSeverityKey(a.severity)) - order.indexOf(getSeverityKey(b.severity));
  });
  const cards = cardsData || [];
  const refetchAll = () => { refetchSafety(); refetchCards(); };

  const highAlerts = alerts.filter((a: any) => ['critical', 'high', 'medium'].includes(getSeverityKey(a.severity)));
  const lowAlerts = alerts.filter((a: any) => ['low', 'info'].includes(getSeverityKey(a.severity)));

  const sections: { title: string; icon: keyof typeof Ionicons.glyphMap; color: string; count: number; data: any[] }[] = [];
  if (highAlerts.length > 0) sections.push({ title: '需要关注', icon: 'alert-circle', color: '#FF453A', count: highAlerts.length, data: highAlerts.map((a: any) => ({ type: 'alert', item: a })) });
  if (cards.length > 0) sections.push({ title: '行动计划', icon: 'rocket-outline', color: colors.brand, count: cards.length, data: cards.map((c: any) => ({ type: 'card', item: c })) });
  if (lowAlerts.length > 0) sections.push({ title: '日常提醒', icon: 'bulb-outline', color: '#FF9F0A', count: lowAlerts.length, data: lowAlerts.map((a: any) => ({ type: 'alert', item: a })) });

  const isEmpty = alerts.length === 0 && cards.length === 0;
  const totalActions = cards.length + highAlerts.length;

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
          <TouchableOpacity style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 16, backgroundColor: colors.brandLight, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }} onPress={refetchAll}>
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
              <View style={[styles.sectionIconWrap, { backgroundColor: `${section.color}18` }]}>
                <Ionicons name={section.icon} size={14} color={section.color} />
              </View>
              <Text style={txt.sectionTitle}>{section.title}</Text>
              <View style={[styles.sectionCountBadge, { backgroundColor: `${section.color}18` }]}>
                <Text style={[txt.sectionCount, { color: section.color }]}>{section.count}</Text>
              </View>
            </View>
          )}
          renderItem={({ item }) =>
            item.type === 'alert' ? <AlertRow alert={item.item} /> : <CardRow card={item.item} onComplete={async () => { await completeCard(item.item.id); refetchCards(); }} />
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
            <TouchableOpacity style={styles.aiBtn} onPress={async () => {
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

function CardRow({ card, onComplete }: { card: ActionCard; onComplete: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const swipeRef = useRef<Swipeable>(null);
  const cfg = CARD_TYPE[card.card_type] || CARD_TYPE.insight;

  const renderRightAction = () => (
    <TouchableOpacity style={styles.swipeAction} onPress={() => { swipeRef.current?.close(); onComplete(); }}>
      <Ionicons name="checkmark-circle" size={20} color="#fff" />
      <Text style={{ fontSize: 12, color: '#fff', fontWeight: '600' }}>完成</Text>
    </TouchableOpacity>
  );

  return (
    <Swipeable ref={swipeRef} renderRightActions={renderRightAction} overshootRight={false}>
    <TouchableOpacity style={styles.cardItem} onPress={() => { LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut); setExpanded(!expanded); }} activeOpacity={0.7}>
      <View style={styles.alertRow}>
        <View style={[styles.alertIconWrap, { backgroundColor: cfg.bg }]}>
          <Ionicons name={cfg.icon} size={16} color={cfg.color} />
        </View>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text style={txt.alertTitle} numberOfLines={expanded ? undefined : 2}>{card.title}</Text>
          </View>
          {!expanded && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Text style={[txt.typeBadge, { color: cfg.color }]}>{cfg.label}</Text>
              {card.created_at && <Text style={txt.timeStamp}>{card.created_at.slice(0, 10)}</Text>}
            </View>
          )}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-forward'} size={14} color={colors.labelTertiary} />
      </View>
      {expanded && (
        <View style={styles.expandedContent}>
          <View style={styles.mdWrap}>
            <Markdown style={mdStyles}>{card.content || ''}</Markdown>
          </View>
          <TouchableOpacity style={styles.completeBtn} onPress={onComplete} activeOpacity={0.7}>
            <Ionicons name="checkmark-circle" size={16} color="#fff" />
            <Text style={txt.completeBtnText}>标记完成</Text>
          </TouchableOpacity>
        </View>
      )}
    </TouchableOpacity>
    </Swipeable>
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

  // Card item
  cardItem: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    marginBottom: 8, ...shadows.subtle,
  },
  mdWrap: { marginBottom: 10 },
  completeBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: '#30D158', borderRadius: radii.md, paddingVertical: 10,
  },
  swipeAction: {
    backgroundColor: '#30D158', justifyContent: 'center', alignItems: 'center',
    width: 70, borderRadius: radii.lg, marginBottom: 8, marginLeft: 8,
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
  typeBadge: { fontSize: 11, fontWeight: '500', marginTop: 2 } as TextStyle,
  timeStamp: { fontSize: 10, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
  completeBtnText: { fontSize: 14, fontWeight: '600', color: '#fff' } as TextStyle,
  emptyTitle: { fontSize: 20, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  emptySub: { fontSize: 14, color: colors.labelSecondary } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 14, lineHeight: 20, color: colors.labelSecondary },
  heading1: { fontSize: 17, fontWeight: '700', color: colors.labelPrimary, marginTop: 10, marginBottom: 4 },
  heading2: { fontSize: 15, fontWeight: '700', color: colors.labelPrimary, marginTop: 8, marginBottom: 4 },
  heading3: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary, marginTop: 6, marginBottom: 2 },
  strong: { fontWeight: '600', color: colors.labelPrimary },
  paragraph: { marginVertical: 3 },
  bullet_list: { marginVertical: 4 },
  ordered_list: { marginVertical: 4 },
  list_item: { flexDirection: 'row', marginVertical: 2 },
  link: { color: colors.brand },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 4, fontFamily: 'Menlo', fontSize: 12, color: colors.brand },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 8, padding: 10, fontFamily: 'Menlo', fontSize: 12, marginVertical: 6 },
  table: { borderWidth: 1, borderColor: '#E5E5EA', borderRadius: 8, marginVertical: 8 },
  thead: { backgroundColor: '#F2F2F7' },
  th: { padding: 8, fontWeight: '600', fontSize: 12, color: colors.labelPrimary, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: '#E5E5EA' },
  td: { padding: 8, fontSize: 12, color: colors.labelSecondary, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: '#E5E5EA' },
  tr: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#E5E5EA', flexDirection: 'row' },
  hr: { backgroundColor: colors.separator, height: 1, marginVertical: 8 },
  blockquote: { borderLeftWidth: 3, borderLeftColor: colors.brand, paddingLeft: 10, marginVertical: 4, opacity: 0.85 },
});
