/**
 * Directive 管理 — 外部指令通道.
 *
 * 合规定位: 用户 / 家人 / 教练 / 授权的 advisor 给 AI 下的硬性约束.
 * 不是医嘱. AI 在 specialist prompt 注入这些指令作为约束, 不替代医生决策.
 *
 * 用户必须:
 * - 看到全部 active directive
 * - 可撤销任何一条
 * - 可自己创建 (自然语言或结构化)
 */
import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, FlatList, Alert, ActivityIndicator,
  Modal, TextInput, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Swipeable } from 'react-native-gesture-handler';
import * as Haptics from 'expo-haptics';
import {
  listMyDirectives, revokeDirective, parseFreeText,
  KIND_LABEL, SEVERITY_LABEL, SEVERITY_COLOR, sourceLabel,
  type UserDirective,
} from '../services/userDirectives';
import { colors, spacing, radii } from '../constants/theme';

const QK = ['userDirectives'] as const;

export default function DirectivesScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [freeText, setFreeText] = useState('');

  const { data: directives = [], isLoading, refetch } = useQuery({
    queryKey: QK,
    queryFn: listMyDirectives,
    staleTime: 60_000,
  });

  const revokeMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => revokeDirective(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK }),
  });

  const parseMut = useMutation({
    mutationFn: (text: string) => parseFreeText(text, 'manual'),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: QK });
      setShowAdd(false);
      setFreeText('');
      if (result.count === 0) {
        Alert.alert('未识别出指令', '请尝试更明确的表述, 如"血压控制在 130 以下"/"停用美托洛尔"/"戒酒 30 天"');
      } else {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
    },
    onError: () => Alert.alert('解析失败', '请稍后再试'),
  });

  const handleRevoke = (item: UserDirective) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert(
      '撤销这条指令?',
      `${KIND_LABEL[item.kind]}: ${item.instruction.slice(0, 80)}`,
      [
        { text: '取消', style: 'cancel' },
        { text: '撤销', style: 'destructive', onPress: () => revokeMut.mutate({ id: item.id }) },
      ],
    );
  };

  const renderRight = (item: UserDirective) => (
    <TouchableOpacity style={styles.swipeRevoke} onPress={() => handleRevoke(item)}>
      <Ionicons name="close-circle-outline" size={20} color="#fff" />
      <Text style={styles.swipeText}>撤销</Text>
    </TouchableOpacity>
  );

  const renderItem = ({ item }: { item: UserDirective }) => {
    const sevColor = SEVERITY_COLOR[item.severity];
    return (
      <Swipeable renderRightActions={() => renderRight(item)}>
        <View style={styles.row}>
          <View style={styles.rowHeader}>
            <View style={[styles.kindBadge, { backgroundColor: colors.fill }]}>
              <Text style={styles.kindBadgeText}>{KIND_LABEL[item.kind]}</Text>
            </View>
            <View style={[styles.sevBadge, { borderColor: sevColor }]}>
              <Text style={[styles.sevBadgeText, { color: sevColor }]}>
                {SEVERITY_LABEL[item.severity]}
              </Text>
            </View>
            <View style={{ flex: 1 }} />
            <Text style={styles.source}>{sourceLabel(item.source)}</Text>
          </View>
          <Text style={styles.instruction}>{item.instruction}</Text>
          {(item.metric_key || item.target_value || item.medication_name) && (
            <View style={styles.meta}>
              {item.metric_key && <Text style={styles.metaText}>指标: {item.metric_key}</Text>}
              {item.target_value && <Text style={styles.metaText}>目标: {item.target_value}</Text>}
              {item.medication_name && <Text style={styles.metaText}>药: {item.medication_name}</Text>}
              {item.expires_at && (
                <Text style={styles.metaText}>
                  至 {item.expires_at.slice(0, 10)}
                </Text>
              )}
            </View>
          )}
        </View>
      </Swipeable>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.title}>硬性指令</Text>
        <TouchableOpacity onPress={() => setShowAdd(true)} style={styles.addBtn}>
          <Ionicons name="add" size={24} color={colors.brand} />
        </TouchableOpacity>
      </View>

      <View style={styles.complianceBanner}>
        <Ionicons name="information-circle-outline" size={14} color={colors.labelSecondary} />
        <Text style={styles.complianceText}>
          这些是你设置给 AI 的硬性约束 · AI 在推荐时会遵循 · 不替代医生诊断
        </Text>
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : directives.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="document-text-outline" size={48} color={colors.labelTertiary} />
          <Text style={styles.emptyTitle}>暂无指令</Text>
          <Text style={styles.emptyHint}>
            你可以给 AI 下硬性约束, 比如"血压控制在 130 以下"
            {'\n'}"停用美托洛尔"/"戒酒 30 天"/"不要再推鱼油"
          </Text>
          <TouchableOpacity style={styles.emptyBtn} onPress={() => setShowAdd(true)}>
            <Text style={styles.emptyBtnText}>添加第一条</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={directives}
          keyExtractor={(i) => String(i.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          onRefresh={() => refetch()}
          refreshing={false}
        />
      )}

      <Modal visible={showAdd} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={styles.modalSafe}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={{ flex: 1 }}
          >
            <View style={styles.modalHeader}>
              <TouchableOpacity onPress={() => setShowAdd(false)}>
                <Text style={styles.modalCancel}>取消</Text>
              </TouchableOpacity>
              <Text style={styles.modalTitle}>添加指令</Text>
              <TouchableOpacity
                disabled={freeText.trim().length < 4 || parseMut.isPending}
                onPress={() => parseMut.mutate(freeText.trim())}
              >
                <Text style={[
                  styles.modalSubmit,
                  (freeText.trim().length < 4 || parseMut.isPending) && styles.modalSubmitDisabled,
                ]}>
                  {parseMut.isPending ? '解析中…' : '完成'}
                </Text>
              </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={styles.modalBody}>
              <Text style={styles.modalHint}>
                自然语言描述, AI 会自动解析成结构化指令. 例如:
              </Text>
              <View style={styles.examplesBox}>
                {EXAMPLES.map((ex, i) => (
                  <TouchableOpacity key={i} onPress={() => setFreeText(ex)}>
                    <Text style={styles.example}>· {ex}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TextInput
                style={styles.input}
                placeholder="写下你的约束..."
                placeholderTextColor={colors.labelTertiary}
                multiline
                value={freeText}
                onChangeText={setFreeText}
                autoFocus
              />
            </ScrollView>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const EXAMPLES = [
  '血压控制在 130/80 以下',
  'LDL 胆固醇目标 2.6 以下',
  '继续服用美托洛尔 25mg 每天两次',
  '戒酒 30 天',
  '每天监测血压',
  '不要再推鱼油和银杏',
];

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.separator,
  },
  backBtn: { padding: 4 },
  addBtn: { padding: 4 },
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '600', color: colors.labelPrimary },
  complianceBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: colors.fill,
  },
  complianceText: { fontSize: 11, color: colors.labelSecondary, flex: 1 },
  list: { padding: spacing.md, gap: spacing.sm },
  row: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: 6,
  },
  rowHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  kindBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  kindBadgeText: { fontSize: 11, color: colors.labelSecondary },
  sevBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, borderWidth: 1 },
  sevBadgeText: { fontSize: 11, fontWeight: '600' },
  source: { fontSize: 11, color: colors.labelTertiary },
  instruction: { fontSize: 15, color: colors.labelPrimary, lineHeight: 22 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 2 },
  metaText: { fontSize: 11, color: colors.labelTertiary },
  swipeRevoke: {
    width: 80, backgroundColor: '#FF453A',
    justifyContent: 'center', alignItems: 'center',
    marginBottom: spacing.sm, borderTopRightRadius: radii.md, borderBottomRightRadius: radii.md,
  },
  swipeText: { color: '#fff', fontSize: 12, marginTop: 2 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xxl, gap: spacing.md },
  emptyTitle: { fontSize: 17, fontWeight: '600', color: colors.labelSecondary },
  emptyHint: { fontSize: 13, color: colors.labelTertiary, textAlign: 'center', lineHeight: 20 },
  emptyBtn: {
    marginTop: spacing.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.sm,
    backgroundColor: colors.brand, borderRadius: radii.md,
  },
  emptyBtnText: { color: '#fff', fontWeight: '600' },
  modalSafe: { flex: 1, backgroundColor: colors.bgPrimary },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.separator,
  },
  modalCancel: { color: colors.labelSecondary, fontSize: 15 },
  modalTitle: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary },
  modalSubmit: { color: colors.brand, fontSize: 15, fontWeight: '600' },
  modalSubmitDisabled: { color: colors.labelQuaternary },
  modalBody: { padding: spacing.md, gap: spacing.md },
  modalHint: { fontSize: 13, color: colors.labelSecondary, lineHeight: 20 },
  examplesBox: { backgroundColor: colors.bgCard, borderRadius: radii.md, padding: spacing.md, gap: 4 },
  example: { fontSize: 13, color: colors.labelSecondary, lineHeight: 22 },
  input: {
    backgroundColor: colors.bgCard, borderRadius: radii.md, padding: spacing.md,
    minHeight: 120, fontSize: 15, color: colors.labelPrimary,
    textAlignVertical: 'top',
  },
});
