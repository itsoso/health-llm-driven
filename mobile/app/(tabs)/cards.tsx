import React, { useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-native-markdown-display';
import { getActiveCards, completeCard, type ActionCard } from '@/services/actionCards';

const TYPE_CONFIG: Record<string, { color: string; icon: keyof typeof Ionicons.glyphMap }> = {
  guide:          { color: '#30B0C7', icon: 'compass' },
  plan:           { color: '#AF52DE', icon: 'calendar' },
  recommendation: { color: '#34C759', icon: 'bulb' },
  reminder:       { color: '#FF9500', icon: 'alarm' },
  insight:        { color: '#007AFF', icon: 'analytics' },
};

export default function CardsScreen() {
  const queryClient = useQueryClient();
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['actionCards'],
    queryFn: getActiveCards,
  });

  const cards = data || [];

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <FlatList
        data={cards}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#007AFF" />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="checkmark-done-circle" size={64} color="#34C759" />
            <Text style={styles.emptyTitle}>全部完成</Text>
            <Text style={styles.emptySubtitle}>暂无待办行动卡片</Text>
          </View>
        }
        renderItem={({ item }) => (
          <CardItem
            card={item}
            onComplete={async () => {
              try {
                await completeCard(item.id);
                queryClient.invalidateQueries({ queryKey: ['actionCards'] });
              } catch {
                Alert.alert('操作失败', '请稍后重试');
              }
            }}
          />
        )}
      />
    </SafeAreaView>
  );
}

function CardItem({
  card,
  onComplete,
}: {
  card: ActionCard;
  onComplete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const cfg = TYPE_CONFIG[card.card_type] || TYPE_CONFIG.insight;

  return (
    <View style={styles.card}>
      <TouchableOpacity
        style={styles.cardHeader}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
      >
        <View style={[styles.cardDot, { backgroundColor: cfg.color }]} />
        <View style={styles.cardTitleWrap}>
          <Text style={styles.cardTitle} numberOfLines={expanded ? undefined : 2}>
            {card.title}
          </Text>
          <View style={styles.cardMeta}>
            <Ionicons name={cfg.icon} size={12} color={cfg.color} />
            <Text style={[styles.cardType, { color: cfg.color }]}>
              {card.card_type}
            </Text>
            {card.source && (
              <Text style={styles.cardSource}>{card.source}</Text>
            )}
          </View>
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color="#8E8E93"
        />
      </TouchableOpacity>

      {expanded && (
        <View style={styles.cardBody}>
          <View style={styles.markdownWrap}>
            <Markdown
              style={{
                body: { fontSize: 14, color: '#3C3C43', lineHeight: 22 },
                heading2: { fontSize: 16, fontWeight: '600', color: '#1C1C1E', marginTop: 8 },
                heading3: { fontSize: 15, fontWeight: '600', color: '#1C1C1E', marginTop: 6 },
                list_item: { marginVertical: 2 },
              }}
            >
              {card.content}
            </Markdown>
          </View>
          <TouchableOpacity style={styles.completeBtn} onPress={onComplete}>
            <Ionicons name="checkmark-circle" size={18} color="#fff" />
            <Text style={styles.completeBtnText}>标记完成</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FDFBF7' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 16 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    marginBottom: 10,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    gap: 10,
  },
  cardDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  cardTitleWrap: { flex: 1 },
  cardTitle: { fontSize: 15, fontWeight: '600', color: '#1C1C1E' },
  cardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
  },
  cardType: { fontSize: 11, fontWeight: '500' },
  cardSource: { fontSize: 11, color: '#8E8E93', marginLeft: 6 },
  cardBody: {
    paddingHorizontal: 14,
    paddingBottom: 14,
    borderTopWidth: 0.5,
    borderTopColor: '#E5E5EA',
  },
  markdownWrap: { paddingTop: 10 },
  completeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#34C759',
    borderRadius: 10,
    paddingVertical: 10,
    marginTop: 12,
  },
  completeBtnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  empty: { alignItems: 'center', paddingTop: 120 },
  emptyTitle: { fontSize: 20, fontWeight: '700', color: '#1C1C1E', marginTop: 12 },
  emptySubtitle: { fontSize: 14, color: '#8E8E93', marginTop: 4 },
});
