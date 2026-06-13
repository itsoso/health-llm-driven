/**
 * 用药管理页.
 *
 * 功能:
 *   - 查看在用 / 已停用药品 (tab 切换)
 *   - 停用药品 (软删除, 本地 toast 5 秒内可 undo)
 *   - 恢复已停用 (误操作回滚)
 *   - 点击药品跳编辑 (TODO)
 *
 * 入口: settings → 用药管理
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator,
  RefreshControl, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import {
  listMedications, deactivateMedication, restoreMedication, type Medication,
} from '../services/medications';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import { useToast } from '../hooks/useToast';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createMedicationAgentContext } from '../utils/agentContext';

type TabKey = 'active' | 'archived';

export default function MedicationsScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>('active');
  const toast = useToast();

  const activeQuery = useQuery<Medication[]>({
    queryKey: ['medications', 'active'],
    queryFn: () => listMedications(true),
    staleTime: 30_000,
  });

  const allQuery = useQuery<Medication[]>({
    queryKey: ['medications', 'all'],
    queryFn: () => listMedications(false),
    enabled: tab === 'archived',
    staleTime: 30_000,
  });

  const archived = useMemo(
    () => (allQuery.data || []).filter((m) => !m.is_active),
    [allQuery.data],
  );

  const deactivateMut = useMutation({
    mutationFn: (id: number) => deactivateMedication(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['medications'] });
    },
  });

  const restoreMut = useMutation({
    mutationFn: (id: number) => restoreMedication(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['medications'] });
    },
  });

  const handleDeactivate = (m: Medication) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    deactivateMut.mutate(m.id, {
      onSuccess: () => {
        toast.showUndoable(
          `已停用 ${m.name}`,
          async () => {
            // 5 秒内点 undo → 恢复
            await restoreMedication(m.id);
            qc.invalidateQueries({ queryKey: ['medications'] });
          },
        );
      },
      onError: () => Alert.alert('停用失败', '请稍后再试'),
    });
  };

  const handleRestore = (m: Medication) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    restoreMut.mutate(m.id, {
      onError: () => Alert.alert('恢复失败', '请稍后再试'),
    });
  };

  const currentList = tab === 'active' ? (activeQuery.data || []) : archived;
  const isLoading = tab === 'active' ? activeQuery.isLoading : allQuery.isLoading;
  const isFetching = tab === 'active' ? activeQuery.isFetching : allQuery.isFetching;
  const refetch = tab === 'active' ? activeQuery.refetch : allQuery.refetch;
  const today = new Date().toISOString().split('T')[0];
  const activeMedications = activeQuery.data || [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>用药管理</Text>
        <TouchableOpacity
          onPress={() => router.push('/deprescribing' as any)}
          hitSlop={12}
          style={styles.backBtn}
          accessibilityLabel="多药梳理"
        >
          <Ionicons name="list-outline" size={22} color={c.labelPrimary} />
        </TouchableOpacity>
      </View>

      <View style={styles.tabBar}>
        {([
          { k: 'active' as const, label: `在用 ${activeQuery.data?.length ? `· ${activeQuery.data.length}` : ''}` },
          { k: 'archived' as const, label: `已停用 ${archived.length ? `· ${archived.length}` : ''}` },
        ]).map(({ k, label }) => (
          <TouchableOpacity
            key={k}
            style={[styles.tabBtn, tab === k && styles.tabBtnActive]}
            onPress={() => setTab(k)}
          >
            <Text style={[txt.tabText, tab === k && txt.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={isFetching} onRefresh={() => { refetch(); }} tintColor={c.brand} />}
      >
        {activeMedications.length > 0 && (
          <AgentFeedbackLink
            label="跟 Agent 整理用药问题"
            accessibilityLabel="跟 Agent 整理用药问题"
            prompt="请基于我的在用药品列表, 帮我整理今天的用药执行情况、可能需要向医生确认的问题、近期不适该如何描述。不要建议我自行停药、换药或改剂量。"
            context={createMedicationAgentContext({
              date: today,
              activeMedications,
              archivedMedications: archived,
            })}
            badge={`在用药品 ${activeMedications.length} 个`}
            style={styles.agentLink}
          />
        )}
        {isLoading ? (
          <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
        ) : currentList.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="medical-outline" size={48} color={c.labelTertiary} />
            <Text style={txt.emptyTitle}>
              {tab === 'active' ? '还没有在用药品' : '没有已停用的药品'}
            </Text>
            <Text style={txt.emptyHint}>
              {tab === 'active'
                ? '通过对话 "记录我在吃 XX" 或体检导入添加药物'
                : '误停用的药品可以在这里恢复'}
            </Text>
          </View>
        ) : (
          <View style={styles.list}>
            {currentList.map((m) => (
              <MedicationRow
                key={m.id} med={m} c={c}
                tab={tab}
                onEdit={() => router.push(`/medication-edit?id=${m.id}` as any)}
                onDeactivate={() => handleDeactivate(m)}
                onRestore={() => handleRestore(m)}
              />
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function MedicationRow({
  med, c, tab, onEdit, onDeactivate, onRestore,
}: {
  med: Medication; c: ColorPalette; tab: TabKey;
  onEdit: () => void;
  onDeactivate: () => void; onRestore: () => void;
}) {
  const styles = createStyles(c);
  const txt = createTxt(c);

  const confirmDeactivate = () => {
    Alert.alert(
      `停用 ${med.name}?`,
      '停用后药品会移到"已停用"列表, 不影响历史记录. 误操作可在 5 秒内撤销或到"已停用"恢复.',
      [
        { text: '取消', style: 'cancel' },
        { text: '停用', style: 'destructive', onPress: onDeactivate },
      ],
    );
  };

  return (
    <View style={styles.row}>
      <TouchableOpacity
        style={{ flex: 1 }}
        onPress={onEdit}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={`编辑 ${med.name}`}
      >
        <Text style={txt.medName}>{med.name}</Text>
        {(med.dosage || med.frequency) && (
          <Text style={txt.medMeta}>
            {[med.dosage, med.frequency].filter(Boolean).join(' · ')}
          </Text>
        )}
        {med.purpose && (
          <Text style={txt.medPurpose} numberOfLines={1}>{med.purpose}</Text>
        )}
      </TouchableOpacity>
      {tab === 'active' ? (
        <TouchableOpacity onPress={confirmDeactivate} hitSlop={8} style={styles.actionBtn}>
          <Ionicons name="pause-circle-outline" size={24} color={c.red} />
        </TouchableOpacity>
      ) : (
        <TouchableOpacity onPress={onRestore} hitSlop={8} style={styles.actionBtn}>
          <Ionicons name="refresh-circle-outline" size={24} color={c.brand} />
        </TouchableOpacity>
      )}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    },
    backBtn: { width: 40, alignItems: 'flex-start' },
    tabBar: {
      flexDirection: 'row',
      marginHorizontal: spacing.md, marginBottom: spacing.xs,
      backgroundColor: c.fill, borderRadius: radii.sm, padding: 3,
    },
    tabBtn: {
      flex: 1, paddingVertical: 8, alignItems: 'center',
      borderRadius: radii.sm - 2,
    },
    tabBtnActive: { backgroundColor: c.bgCard },
    scroll: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl },
    agentLink: { marginTop: spacing.sm, marginBottom: spacing.md },
    center: { paddingTop: 80, alignItems: 'center' },
    empty: { paddingTop: 80, alignItems: 'center', paddingHorizontal: spacing.lg },
    list: { gap: spacing.sm, paddingTop: spacing.sm },
    row: {
      flexDirection: 'row', alignItems: 'center',
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md, gap: spacing.sm, ...shadows.subtle,
    },
    actionBtn: { padding: 4 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    tabText: { fontSize: 14, color: c.labelSecondary, fontWeight: '500' } as TextStyle,
    tabTextActive: { color: c.labelPrimary, fontWeight: '600' } as TextStyle,
    emptyTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary, marginTop: spacing.md } as TextStyle,
    emptyHint: { fontSize: 13, color: c.labelSecondary, lineHeight: 20, textAlign: 'center', marginTop: spacing.xs } as TextStyle,
    medName: { fontSize: 16, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    medMeta: { fontSize: 12, color: c.labelSecondary, marginTop: 2 } as TextStyle,
    medPurpose: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  };
}
