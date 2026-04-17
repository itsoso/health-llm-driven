import React, { useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl, TextStyle, LayoutAnimation,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-native-markdown-display';
import { getActiveCards, completeCard, type ActionCard } from '@/services/actionCards';
import { colors, spacing, radii, shadows } from '@/constants/theme';

const TYPE_CONFIG: Record<string, { color: string; gradient: string; icon: keyof typeof Ionicons.glyphMap; label: string }> = {
  guide:          { color: '#0A8F8F', gradient: '#E6F5F5', icon: 'compass-outline', label: '指南' },
  plan:           { color: '#AF52DE', gradient: '#F5E6FF', icon: 'calendar-outline', label: '计划' },
  recommendation: { color: '#30D158', gradient: '#E8FAF0', icon: 'bulb-outline', label: '建议' },
  reminder:       { color: '#FF9F0A', gradient: '#FFF5E6', icon: 'alarm-outline', label: '提醒' },
  insight:        { color: '#007AFF', gradient: '#E6F0FF', icon: 'analytics-outline', label: '洞察' },
};

export default function PlansScreen() {
  const queryClient = useQueryClient();
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['actionCards'],
    queryFn: getActiveCards,
  });

  const cards = data || [];

  if (isLoading) {
    return <View style={styles.center}><ActivityIndicator size="large" color={colors.brand} /></View>;
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Text style={txt.screenTitle}>计划</Text>
      {cards.length === 0 ? (
        <EmptyState onRefresh={refetch} refreshing={isRefetching} />
      ) : (
        <FlatList
          data={cards}
          keyExtractor={(item) => `${item.id}`}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
          renderItem={({ item }) => (
            <PlanCard
              card={item}
              onComplete={async () => {
                LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
                await completeCard(item.id);
                queryClient.invalidateQueries({ queryKey: ['actionCards'] });
              }}
            />
          )}
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
            <Ionicons name="checkmark-done" size={48} color={colors.brand} />
          </View>
          <Text style={txt.emptyTitle}>全部完成</Text>
          <Text style={txt.emptySub}>今天的任务都已完成</Text>
        </View>
      }
    />
  );
}

function PlanCard({ card, onComplete }: { card: ActionCard; onComplete: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = TYPE_CONFIG[card.card_type] || TYPE_CONFIG.insight;

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded(!expanded);
  };

  return (
    <TouchableOpacity style={styles.card} onPress={toggle} activeOpacity={0.7}>
      <View style={[styles.topStripe, { backgroundColor: cfg.color }]} />
      <View style={styles.cardBody}>
        <View style={styles.cardHeader}>
          <View style={[styles.typeIcon, { backgroundColor: cfg.gradient }]}>
            <Ionicons name={cfg.icon} size={16} color={cfg.color} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={txt.cardTitle} numberOfLines={expanded ? undefined : 2}>{card.title}</Text>
            <View style={styles.metaRow}>
              <Text style={[txt.typeBadge, { color: cfg.color }]}>{cfg.label}</Text>
              {card.source && <Text style={txt.source}>{card.source}</Text>}
            </View>
          </View>
          <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.labelTertiary} />
        </View>
        {expanded && (
          <>
            <Markdown style={mdStyles}>{card.content || ''}</Markdown>
            <TouchableOpacity style={styles.completeBtn} onPress={onComplete} activeOpacity={0.7}>
              <Ionicons name="checkmark-circle" size={18} color="#fff" />
              <Text style={txt.completeText}>标记完成</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: spacing.xl, paddingTop: 0 },
  card: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    marginBottom: spacing.md, overflow: 'hidden', ...shadows.subtle,
  },
  topStripe: { height: 3 },
  cardBody: { padding: spacing.md },
  cardHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  typeIcon: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  completeBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: '#30D158', borderRadius: radii.md,
    paddingVertical: spacing.sm, marginTop: spacing.md,
  },
  empty: { alignItems: 'center', paddingTop: 120 },
  emptyCircle: {
    width: 88, height: 88, borderRadius: 44,
    backgroundColor: colors.brandLight, alignItems: 'center', justifyContent: 'center', marginBottom: 16,
  },
});

const txt = {
  screenTitle: { fontSize: 34, fontWeight: '700', color: colors.labelPrimary, paddingHorizontal: spacing.xl, paddingTop: spacing.lg, paddingBottom: spacing.sm } as TextStyle,
  cardTitle: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, lineHeight: 20 } as TextStyle,
  typeBadge: { fontSize: 11, fontWeight: '600' } as TextStyle,
  source: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  content: { fontSize: 14, color: colors.labelSecondary, lineHeight: 20, marginTop: spacing.md } as TextStyle,
  completeText: { fontSize: 14, fontWeight: '600', color: '#fff' } as TextStyle,
  emptyTitle: { fontSize: 22, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  emptySub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4 } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 14, lineHeight: 20, color: colors.labelSecondary },
  heading2: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 6, marginBottom: 2 },
  heading3: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary, marginTop: 4, marginBottom: 2 },
  strong: { fontWeight: '600', color: colors.labelPrimary },
  bullet_list: { marginVertical: 2 },
  list_item: { flexDirection: 'row', marginVertical: 1 },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 3, fontFamily: 'Menlo', fontSize: 12, color: '#0A8F8F' },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 6, padding: 8, fontFamily: 'Menlo', fontSize: 12, marginVertical: 4 },
  paragraph: { marginVertical: 2 },
  link: { color: '#0A8F8F' },
});
