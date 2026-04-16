import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { recordWater, deleteWater, updateCheckin } from '@/services/records';
import { fetchDashboardData } from '@/services/dashboard';

interface QuickAction {
  label: string;
  emoji: string;
  action: () => Promise<{ undo?: () => Promise<void> }>;
}

export default function RecordScreen() {
  const queryClient = useQueryClient();
  const [undoAction, setUndoAction] = useState<{
    label: string;
    fn: () => Promise<void>;
  } | null>(null);
  const [undoTimer, setUndoTimer] = useState<ReturnType<typeof setTimeout> | null>(null);

  const { data, refetch, isRefetching } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    staleTime: 30_000,
  });

  const waterTotal = Array.isArray(data?.waterRecords)
    ? data.waterRecords.reduce((s: number, r: any) => s + (r.amount || 0), 0)
    : 0;
  const nasalWash = data?.checkin?.nasal_wash_count ?? 0;
  const sneezeCount = data?.checkin?.sneeze_count ?? 0;

  const showUndo = useCallback(
    (label: string, fn: () => Promise<void>) => {
      if (undoTimer) clearTimeout(undoTimer);
      setUndoAction({ label, fn });
      const timer = setTimeout(() => setUndoAction(null), 5000);
      setUndoTimer(timer);
    },
    [undoTimer],
  );

  const handleAction = useCallback(
    async (label: string, fn: () => Promise<{ undo?: () => Promise<void> }>) => {
      try {
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
        const result = await fn();
        queryClient.invalidateQueries({ queryKey: ['dashboard'] });
        if (result.undo) {
          showUndo(label, async () => {
            await result.undo!();
            queryClient.invalidateQueries({ queryKey: ['dashboard'] });
          });
        }
      } catch (err: any) {
        Alert.alert('操作失败', err?.message || '请稍后重试');
      }
    },
    [queryClient, showUndo],
  );

  const waterAction = (amount: number): QuickAction => ({
    label: `${amount}ml`,
    emoji: '\u{1F4A7}',
    action: async () => {
      const record = await recordWater(amount);
      return { undo: async () => { await deleteWater(record.id); } };
    },
  });

  const checkinAction = (
    label: string,
    emoji: string,
    field: string,
    increment: number,
  ): QuickAction => ({
    label,
    emoji,
    action: async () => {
      const current = data?.checkin?.[field] ?? 0;
      await updateCheckin(field, current + increment);
      return {
        undo: async () => {
          await updateCheckin(field, current);
        },
      };
    },
  });

  const WATER_ACTIONS: QuickAction[] = [
    waterAction(300),
    waterAction(500),
    waterAction(1000),
  ];

  const RHINITIS_ACTIONS: QuickAction[] = [
    checkinAction('洗鼻+1', '\u{1F443}', 'nasal_wash_count', 1),
    checkinAction('喷嚏+1', '\u{1F927}', 'sneeze_count', 1),
    checkinAction('莫米松', '\u{1F48A}', 'mometasone', 1),
    checkinAction('西替利嗪', '\u{1F48A}', 'cetirizine', 1),
  ];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#007AFF" />
        }
      >
        {/* Today's counts */}
        <View style={styles.summaryRow}>
          <SummaryChip label="饮水" value={`${waterTotal}ml`} color="#007AFF" />
          <SummaryChip label="洗鼻" value={`${nasalWash}次`} color="#30B0C7" />
          <SummaryChip label="喷嚏" value={`${sneezeCount}次`} color="#FF9500" />
        </View>

        {/* Water Section */}
        <Text style={styles.sectionTitle}>饮水</Text>
        <View style={styles.grid}>
          {WATER_ACTIONS.map((a) => (
            <ActionButton
              key={a.label}
              label={a.label}
              emoji={a.emoji}
              onPress={() => handleAction(a.label, a.action)}
            />
          ))}
        </View>

        {/* Rhinitis Section */}
        <Text style={styles.sectionTitle}>鼻炎管理</Text>
        <View style={styles.grid}>
          {RHINITIS_ACTIONS.map((a) => (
            <ActionButton
              key={a.label}
              label={a.label}
              emoji={a.emoji}
              onPress={() => handleAction(a.label, a.action)}
            />
          ))}
        </View>
      </ScrollView>

      {/* Undo Snackbar */}
      {undoAction && (
        <View style={styles.snackbar}>
          <Text style={styles.snackbarText}>
            已记录 {undoAction.label}
          </Text>
          <TouchableOpacity
            onPress={async () => {
              await undoAction.fn();
              setUndoAction(null);
            }}
          >
            <Text style={styles.undoText}>撤销</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

function SummaryChip({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <View style={[styles.summaryChip, { borderColor: color }]}>
      <Text style={[styles.summaryValue, { color }]}>{value}</Text>
      <Text style={styles.summaryLabel}>{label}</Text>
    </View>
  );
}

function ActionButton({
  label,
  emoji,
  onPress,
}: {
  label: string;
  emoji: string;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.actionBtn} onPress={onPress} activeOpacity={0.7}>
      <Text style={styles.actionEmoji}>{emoji}</Text>
      <Text style={styles.actionLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FDFBF7' },
  content: { padding: 16, paddingBottom: 80 },
  summaryRow: { flexDirection: 'row', gap: 10, marginBottom: 20 },
  summaryChip: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E5E5EA',
  },
  summaryValue: { fontSize: 18, fontWeight: '700' },
  summaryLabel: { fontSize: 11, color: '#8E8E93', marginTop: 2 },
  sectionTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#1C1C1E',
    marginBottom: 12,
    marginTop: 4,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 20,
  },
  actionBtn: {
    width: '30%',
    aspectRatio: 1,
    backgroundColor: '#fff',
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  actionEmoji: { fontSize: 32, marginBottom: 6 },
  actionLabel: { fontSize: 14, fontWeight: '600', color: '#1C1C1E' },
  snackbar: {
    position: 'absolute',
    bottom: 100,
    left: 24,
    right: 24,
    backgroundColor: '#1C1C1E',
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 20,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 5,
  },
  snackbarText: { color: '#fff', fontSize: 15, fontWeight: '500' },
  undoText: { color: '#007AFF', fontSize: 15, fontWeight: '700' },
});
