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
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import {
  listMedications, deactivateMedication, restoreMedication, addMedication, logMedication, type Medication,
} from '../services/medications';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import { useToast } from '../hooks/useToast';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createMedicationAgentContext } from '../utils/agentContext';
import { todayStr } from '../utils/dietDate';

type TabKey = 'active' | 'archived';

export default function MedicationsScreen() {
  const router = useRouter();
  const routeParams = useLocalSearchParams();
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>('active');
  const [draftDismissed, setDraftDismissed] = useState(false);
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
  const isError = tab === 'active' ? activeQuery.isError : allQuery.isError;
  const isFetching = tab === 'active' ? activeQuery.isFetching : allQuery.isFetching;
  const refetch = tab === 'active' ? activeQuery.refetch : allQuery.refetch;
  const today = todayStr();
  const activeMedications = activeQuery.data || [];
  const medicationDraft = useMemo(() => parseMedicationDraftParams(routeParams), [routeParams]);

  const confirmDraftMut = useMutation({
    mutationFn: async () => {
      if (!medicationDraft || medicationDraft.needsReview) throw new Error('invalid_medication_draft');
      const existing = activeMedications.find((med) => sameMedicationName(med.name, medicationDraft.name));
      const medication = existing ?? await addMedication({
        name: medicationDraft.name,
        dosage: medicationDraft.dose,
        notes: '来自小巴用药草稿, 由用户确认后写入。',
      });
      await logMedication({
        medication_id: medication.id,
        taken_time: currentTimeLabel(),
        status: 'taken',
        actual_dosage: medicationDraft.dose,
        notes: '小巴用药草稿确认记录。',
      });
      return medication;
    },
    onSuccess: (medication) => {
      setDraftDismissed(true);
      setTab('active');
      qc.invalidateQueries({ queryKey: ['medications'] });
      qc.invalidateQueries({ queryKey: ['medicationToday'] });
      toast.show(`已记录 ${medication.name}`, 'success');
    },
    onError: () => {
      Alert.alert('记录失败', '用药草稿没有保存成功, 请核对后重试。');
    },
  });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} accessibilityRole="button" accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={26} color={C.ink1} />
        </TouchableOpacity>
        <Text style={txt.title}>用药管理</Text>
        <TouchableOpacity
          onPress={() => router.push('/deprescribing' as any)}
          hitSlop={12}
          style={styles.backBtn}
          accessibilityRole="button"
          accessibilityLabel="多药梳理"
        >
          <Ionicons name="list-outline" size={22} color={C.ink1} />
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
            accessibilityRole="tab"
            accessibilityState={{ selected: tab === k }}
            onPress={() => setTab(k)}
          >
            <Text style={[txt.tabText, tab === k && txt.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={isFetching} onRefresh={() => { refetch(); }} tintColor={C.green500} />}
      >
        <Text style={txt.sectionHint}>管理用药安排，服用后再打卡</Text>
        {medicationDraft && !draftDismissed && (
          <View style={styles.draftCard}>
            <View style={styles.draftHeader}>
              <View style={styles.draftIcon}>
                <Ionicons name="sparkles-outline" size={18} color={C.green500} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={txt.draftTitle}>{medicationDraft.needsReview ? '这条内容需要核对' : '小巴识别到用药草稿'}</Text>
                <Text style={txt.draftHint}>{medicationDraft.needsReview ? '这段文字包含查询或操作指令，不能直接作为药名记录。' : '请核对药名和剂量，仅在实际服用后确认。'}</Text>
              </View>
            </View>
            <Text style={medicationDraft.needsReview ? txt.draftHint : txt.draftName}>{medicationDraft.name}</Text>
            {medicationDraft.dose ? <Text style={txt.draftDose}>{medicationDraft.dose}</Text> : null}
            <View style={styles.draftActions}>
              {!medicationDraft.needsReview && <TouchableOpacity
                style={[styles.draftPrimary, confirmDraftMut.isPending && styles.draftDisabled]}
                disabled={confirmDraftMut.isPending}
                onPress={() => confirmDraftMut.mutate()}
                accessibilityRole="button"
                accessibilityLabel="确认记录用药"
              >
                <Ionicons name="checkmark" size={16} color="#fff" />
                <Text style={txt.draftPrimary}>
                  {confirmDraftMut.isPending ? '记录中' : '确认记录用药'}
                </Text>
              </TouchableOpacity>}
              <TouchableOpacity
                style={styles.draftSecondary}
                onPress={() => setDraftDismissed(true)}
                accessibilityRole="button"
                accessibilityLabel={medicationDraft.needsReview ? '关闭待核对提示' : '稍后处理用药草稿'}
              >
                <Text style={txt.draftSecondary}>{medicationDraft.needsReview ? '关闭提示' : '稍后处理'}</Text>
              </TouchableOpacity>
            </View>
            <Text style={txt.draftBoundary}>不替代医嘱, 不自动调整剂量。</Text>
          </View>
        )}
        {isLoading ? (
          <View style={styles.center}><ActivityIndicator color={C.green500} /></View>
        ) : isError ? (
          <View style={styles.empty}>
            <Ionicons name="cloud-offline-outline" size={32} color={C.ink2} />
            <Text style={txt.emptyTitle}>暂时无法加载用药清单</Text>
            <TouchableOpacity style={styles.reminderAction} accessibilityRole="button" accessibilityLabel="重试加载用药清单" onPress={() => { refetch(); }}>
              <Text style={txt.actionLabel}>重新加载</Text>
            </TouchableOpacity>
          </View>
        ) : currentList.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="medical-outline" size={48} color={C.ink3} />
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
                key={m.id} med={m}
                tab={tab}
                onEdit={() => router.push(`/medication-edit?id=${m.id}` as any)}
                onReminder={() => router.push(`/medication-reminder?id=${m.id}` as any)}
                onDeactivate={() => handleDeactivate(m)}
                onRestore={() => handleRestore(m)}
              />
            ))}
          </View>
        )}
        {activeMedications.length > 0 && (
          <AgentFeedbackLink
            label="跟小巴整理用药问题"
            accessibilityLabel="跟小巴整理用药问题"
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
      </ScrollView>
    </SafeAreaView>
  );
}

// Route parameters may contain old assistant prose. They are not a medication identity.
function isInstructionName(name: string) {
  return /(?:不要|不用|别|请勿|不需要|无需).{0,12}(?:记录|服药|停药|换药|剂量)|(?:查询|核实|查看).{0,20}(?:药品|用药|计划|记录)|(?:记录状态|用药提醒|计划时间)/.test(name);
}

function formatFrequency(value: string) {
  const labels: Record<string, string> = { daily: '每日', bid: '每日两次', tid: '每日三次', qd: '每日一次', weekly: '每周', 'once daily': '每日一次', 'twice daily': '每日两次' };
  return labels[value.trim().toLowerCase()] ?? value;
}

type MedicationDraftRouteParams = ReturnType<typeof useLocalSearchParams>;

function parseMedicationDraftParams(params: MedicationDraftRouteParams) {
  const draft = readParam(params.draft);
  const name = readParam(params.name);
  if (draft !== 'medication' || !name) return null;
  return {
    name,
    needsReview: isInstructionName(name),
    dose: readParam(params.dose),
  };
}

function readParam(value: unknown): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  if (typeof raw !== 'string') return undefined;
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  try {
    return decodeURIComponent(trimmed).trim() || undefined;
  } catch {
    return trimmed;
  }
}

function sameMedicationName(left: string | null | undefined, right: string) {
  const normalize = (value: string | null | undefined) => (value || '').replace(/\s+/g, '').toLowerCase();
  return normalize(left) === normalize(right);
}

function currentTimeLabel() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function MedicationRow({
  med, tab, onEdit, onReminder, onDeactivate, onRestore,
}: {
  med: Medication; tab: TabKey;
  onEdit: () => void;
  onReminder: () => void;
  onDeactivate: () => void; onRestore: () => void;
}) {
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

  const needsReview = isInstructionName(med.name);
  const openActions = () => Alert.alert(med.name, '仅管理清单状态，不代表医生建议停药或恢复用药。', [
    { text: '编辑信息', onPress: onEdit },
    tab === 'active'
      ? { text: '移至已停用', style: 'destructive', onPress: confirmDeactivate }
      : { text: '恢复至在用清单', onPress: onRestore },
    { text: '取消', style: 'cancel' },
  ]);
  return (
    <View style={styles.row}>
      <View style={styles.rowHeading}>
        <TouchableOpacity style={styles.medContent} onPress={onEdit}
          accessibilityRole="button" accessibilityLabel={`编辑 ${med.name}`}>
          {needsReview && <Text style={txt.reviewLabel}>名称待核对</Text>}
          <Text style={txt.medName}>{med.name}</Text>
          <View style={styles.metaRow}>
            {med.dosage ? <Text style={txt.medMeta}>{med.dosage}</Text> : null}
            {med.frequency ? <Text style={txt.medMeta}>{formatFrequency(med.frequency)}</Text> : null}
            {!med.dosage && !med.frequency && <Text style={txt.medPurpose}>剂量与频次待完善</Text>}
          </View>
          {med.purpose && <Text style={txt.medPurpose} numberOfLines={2}>{med.purpose}</Text>}
        </TouchableOpacity>
        <TouchableOpacity onPress={openActions} style={styles.actionBtn}
          accessibilityRole="button" accessibilityLabel={`更多 ${med.name} 的操作`}>
          <Ionicons name="ellipsis-horizontal" size={22} color={C.ink2} />
        </TouchableOpacity>
      </View>
      {tab === 'active' && !needsReview && <TouchableOpacity onPress={onReminder} style={styles.reminderAction}
        accessibilityRole="button" accessibilityLabel={`查看 ${med.name} 的提醒`}>
        <Ionicons name="notifications-outline" size={17} color={C.green600} />
        <Text style={txt.actionLabel}>提醒与打卡</Text>
        <Ionicons name="chevron-forward" size={15} color={C.green600} />
      </TouchableOpacity>}
      {needsReview && <Text style={txt.draftHint}>请编辑并核对药品名称，原记录保持不变。</Text>}
    </View>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / paper2 segmented / 活力绿 / 剂量等宽 mono。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2,
  },
  backBtn: { width: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  tabBar: {
    flexDirection: 'row',
    marginHorizontal: revaSpacing.s3, marginBottom: revaSpacing.s1,
    backgroundColor: C.paper2, borderRadius: revaRadii.sm, padding: 3,
  },
  tabBtn: {
    flex: 1, minHeight: 44, paddingVertical: 12, alignItems: 'center',
    borderRadius: revaRadii.sm - 2,
  },
  tabBtnActive: { backgroundColor: C.surface },
  scroll: { paddingHorizontal: revaSpacing.s3, paddingBottom: revaSpacing.s5 + 24 },
  agentLink: { marginTop: revaSpacing.s2, marginBottom: revaSpacing.s3 },
  center: { paddingTop: 80, alignItems: 'center' },
  empty: { paddingTop: 80, alignItems: 'center', paddingHorizontal: revaSpacing.s4 },
  list: { gap: revaSpacing.s2, paddingTop: revaSpacing.s2 },
  draftCard: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s3,
    marginBottom: revaSpacing.s3,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    ...revaShadows.sm,
  },
  draftHeader: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2 },
  draftIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  draftActions: { flexDirection: 'row', gap: revaSpacing.s2, marginTop: revaSpacing.s3 },
  draftPrimary: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    flex: 1,
    borderRadius: revaRadii.pill,
    paddingVertical: 10,
    backgroundColor: C.green500,
  },
  draftDisabled: { opacity: 0.55 },
  draftSecondary: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.pill,
    paddingHorizontal: revaSpacing.s3,
    minHeight: 44,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper2,
  },
  row: {
    backgroundColor: C.surface, borderRadius: revaRadii.md,
    padding: revaSpacing.s3, gap: revaSpacing.s2,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.line,
  },
  rowHeading: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  medContent: { flex: 1, minHeight: 44 },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 6 },
  reminderAction: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, minHeight: 44, borderRadius: revaRadii.sm, backgroundColor: C.green50, paddingHorizontal: 12, marginTop: 4 },
  actionBtn: { width: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
});

// 剂量/频次走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { flex: 1, textAlign: 'center', fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1 } as TextStyle,
  sectionHint: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, lineHeight: 18, marginVertical: 12 } as TextStyle,
  actionLabel: { fontFamily: revaFonts.sans, fontSize: 13, color: C.green700, fontWeight: '600' } as TextStyle,
  reviewLabel: { fontFamily: revaFonts.sans, fontSize: 12, color: revaSemantic.caution.fg, marginBottom: 4 } as TextStyle,
  tabText: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink2, fontWeight: '500' } as TextStyle,
  tabTextActive: { color: C.ink1, fontWeight: '600' } as TextStyle,
  emptyTitle: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.ink1, marginTop: revaSpacing.s3 } as TextStyle,
  emptyHint: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, lineHeight: 20, textAlign: 'center', marginTop: revaSpacing.s1 } as TextStyle,
  medName: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.ink1 } as TextStyle,
  medMeta: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink2, marginTop: 2 } as TextStyle,
  medPurpose: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 2 } as TextStyle,
  draftTitle: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '800', color: C.ink1 } as TextStyle,
  draftHint: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 17, color: C.ink2, marginTop: 2 } as TextStyle,
  draftName: { fontFamily: revaFonts.sans, fontSize: 18, lineHeight: 24, fontWeight: '800', color: C.ink1, marginTop: revaSpacing.s3 } as TextStyle,
  draftDose: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '700', color: C.green700, marginTop: 4 } as TextStyle,
  draftPrimary: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
  draftSecondary: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '700', color: C.ink2 } as TextStyle,
  draftBoundary: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 17, color: C.ink3, marginTop: revaSpacing.s2 } as TextStyle,
};
