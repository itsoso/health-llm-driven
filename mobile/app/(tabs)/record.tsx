import React, { useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  RefreshControl, TextStyle, Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDashboardData } from '@/services/dashboard';
import { recordWater, deleteWater, updateCheckin } from '@/services/records';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function RecordScreen() {
  const queryClient = useQueryClient();
  const { data, isLoading, refetch, isRefetching } = useQuery({ queryKey: ['dashboard'], queryFn: fetchDashboardData, staleTime: 60_000 });
  const [undo, setUndo] = useState<{ label: string; action: () => Promise<void> } | null>(null);

  const waterTotal = Array.isArray(data?.waterRecords)
    ? data.waterRecords.reduce((s: number, r: any) => s + (r.amount || 0), 0)
    : 0;
  const checkin = data?.checkin;

  const showUndo = (label: string, action: () => Promise<void>) => {
    setUndo({ label, action });
    setTimeout(() => setUndo(null), 5000);
  };

  const doRecordWater = useCallback(async (amount: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const rec = await recordWater(amount);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      showUndo(`记录 ${amount}ml 饮水`, async () => { await deleteWater(rec.id); queryClient.invalidateQueries({ queryKey: ['dashboard'] }); });
    } catch {}
  }, [queryClient]);

  const doCheckin = useCallback(async (field: string, label: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const current = checkin?.[field] || 0;
    try {
      await updateCheckin(field, current + 1);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      showUndo(label, async () => { await updateCheckin(field, current); queryClient.invalidateQueries({ queryKey: ['dashboard'] }); });
    } catch {}
  }, [checkin, queryClient]);

  const doMedCheckin = useCallback(async (field: string, label: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await updateCheckin(field, 1);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      showUndo(label, async () => { await updateCheckin(field, 0); queryClient.invalidateQueries({ queryKey: ['dashboard'] }); });
    } catch {}
  }, [queryClient]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
        showsVerticalScrollIndicator={false}
      >
        <Text style={txt.screenTitle}>记录</Text>
        <Text style={txt.dateText}>{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</Text>

        {/* Summary chips */}
        <View style={styles.summaryRow}>
          <SummaryChip icon="water" color="#64D2FF" label="饮水" value={`${waterTotal}ml`} />
          <SummaryChip icon="nose" color="#30B0C7" label="洗鼻" value={`${checkin?.nasal_wash_count || 0}次`} />
          <SummaryChip icon="flash" color="#FF9F0A" label="喷嚏" value={`${checkin?.sneeze_count || 0}次`} />
        </View>

        {/* Water */}
        <Text style={txt.sectionTitle}>饮水</Text>
        <View style={styles.btnRow}>
          {[200, 300, 500].map(amt => (
            <TouchableOpacity key={amt} style={styles.actionBtn} onPress={() => doRecordWater(amt)} activeOpacity={0.7}>
              <Ionicons name="water" size={20} color="#64D2FF" />
              <Text style={txt.btnLabel}>{amt}ml</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Rhinitis */}
        <Text style={txt.sectionTitle}>鼻炎管理</Text>
        <View style={styles.btnGrid}>
          <TouchableOpacity style={styles.actionBtn} onPress={() => doCheckin('nasal_wash_count', '洗鼻 +1')} activeOpacity={0.7}>
            <Text style={styles.emoji}>👃</Text>
            <Text style={txt.btnLabel}>洗鼻 +1</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => doCheckin('sneeze_count', '喷嚏 +1')} activeOpacity={0.7}>
            <Text style={styles.emoji}>🤧</Text>
            <Text style={txt.btnLabel}>喷嚏 +1</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => doMedCheckin('mometasone', '莫米松打卡')} activeOpacity={0.7}>
            <Text style={styles.emoji}>💊</Text>
            <Text style={txt.btnLabel}>莫米松</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => doMedCheckin('cetirizine', '西替利嗪打卡')} activeOpacity={0.7}>
            <Text style={styles.emoji}>💊</Text>
            <Text style={txt.btnLabel}>西替利嗪</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Undo snackbar */}
      {undo && (
        <View style={styles.undoBar}>
          <Text style={txt.undoText}>{undo.label}</Text>
          <TouchableOpacity onPress={async () => { await undo.action(); setUndo(null); }}>
            <Text style={txt.undoBtn}>撤销</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

function SummaryChip({ icon, color, label, value }: { icon: string; color: string; label: string; value: string }) {
  return (
    <View style={styles.summaryChip}>
      <Ionicons name={icon as any} size={16} color={color} />
      <Text style={txt.chipValue}>{value}</Text>
      <Text style={txt.chipLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  content: { padding: spacing.xl },
  summaryRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xxl },
  summaryChip: {
    flex: 1, backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md, alignItems: 'center', gap: 4, ...shadows.subtle,
  },
  btnRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.xxl },
  btnGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginBottom: spacing.xxl },
  actionBtn: {
    flex: 1, minWidth: '45%',
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, alignItems: 'center', gap: 6,
    ...shadows.subtle,
  },
  emoji: { fontSize: 24 },
  undoBar: {
    position: 'absolute', bottom: 100, left: spacing.xl, right: spacing.xl,
    backgroundColor: '#1C1C1E', borderRadius: radii.full,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    ...shadows.heavy,
  },
});

const txt = {
  screenTitle: { fontSize: 34, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  dateText: { fontSize: 13, color: colors.labelSecondary, marginTop: 2, marginBottom: spacing.xl } as TextStyle,
  sectionTitle: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, marginBottom: spacing.md } as TextStyle,
  chipValue: { fontSize: 17, fontWeight: '700', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  chipLabel: { fontSize: 11, fontWeight: '500', color: colors.labelTertiary } as TextStyle,
  btnLabel: { fontSize: 14, fontWeight: '500', color: colors.labelPrimary } as TextStyle,
  undoText: { fontSize: 14, color: '#fff' } as TextStyle,
  undoBtn: { fontSize: 14, fontWeight: '600', color: colors.brand } as TextStyle,
};
