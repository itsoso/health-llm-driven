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
import React, { useState, useMemo } from 'react';
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
import { spacing, radii } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createDirectivesAgentContext } from '../utils/agentContext';

const QK = ['userDirectives'] as const;

export default function DirectivesScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
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
            <View style={[styles.kindBadge, { backgroundColor: c.fill }]}>
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
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.title}>硬性指令</Text>
        <TouchableOpacity onPress={() => setShowAdd(true)} style={styles.addBtn}>
          <Ionicons name="add" size={24} color={c.brand} />
        </TouchableOpacity>
      </View>

      <View style={styles.complianceBanner}>
        <Ionicons name="information-circle-outline" size={14} color={c.labelSecondary} />
        <Text style={styles.complianceText}>
          这些是你设置给 AI 的硬性约束 · AI 在推荐时会遵循 · 不替代医生诊断
        </Text>
      </View>

      <View style={styles.agentWrap}>
        <AgentFeedbackLink
          label="跟阿衡检查指令冲突"
          accessibilityLabel="跟阿衡检查指令冲突"
          prompt="请基于我当前给 AI 的硬性指令，检查是否存在冲突、过期、表达不清或需要补充边界的地方。涉及用药和诊断时只整理问题，不给处方。"
          context={createDirectivesAgentContext(directives as any)}
          badge={`硬性指令 ${directives.length} 条`}
        />
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : directives.length === 0 ? (
        <View style={styles.emptyWrap}>
          <View style={styles.emptyCard}>
            <View style={styles.emptyHeader}>
              <View style={styles.emptyIcon}>
                <Ionicons name="shield-checkmark-outline" size={24} color={c.brand} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.emptyTitle}>先给阿衡一条硬边界</Text>
                <Text style={styles.emptyHint}>适合放必须遵守的限制、目标或禁忌。</Text>
              </View>
            </View>
            <View style={styles.ruleExamples}>
              {EMPTY_DIRECTIVE_EXAMPLES.map((example) => (
                <TouchableOpacity
                  key={example}
                  style={styles.ruleExample}
                  onPress={() => {
                    setFreeText(example);
                    setShowAdd(true);
                  }}
                  activeOpacity={0.75}
                >
                  <Ionicons name="add-circle-outline" size={16} color={c.brand} />
                  <Text style={styles.ruleExampleText}>{example}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity style={styles.emptyBtn} onPress={() => setShowAdd(true)} activeOpacity={0.75}>
              <Text style={styles.emptyBtnText}>添加指令</Text>
            </TouchableOpacity>
            <Text style={styles.emptyFootnote}>涉及诊断和处方时, 这里仅作为 AI 推荐边界, 不替代医生决策。</Text>
          </View>
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
                placeholderTextColor={c.labelTertiary}
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

const EMPTY_DIRECTIVE_EXAMPLES = [
  '血压高于 140/90 时不要安排高强度训练',
  '鼻炎发作期优先恢复睡眠, 不追求运动目标',
  '不要再推荐鱼油和银杏类补剂',
];

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  backBtn: { padding: 4 },
  addBtn: { padding: 4 },
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '600', color: c.labelPrimary },
  complianceBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: c.fill,
  },
  complianceText: { fontSize: 11, color: c.labelSecondary, flex: 1 },
  agentWrap: { paddingHorizontal: spacing.md, paddingTop: spacing.sm },
  list: { padding: spacing.md, gap: spacing.sm },
  row: {
    backgroundColor: c.bgCard,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: 6,
  },
  rowHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  kindBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  kindBadgeText: { fontSize: 11, color: c.labelSecondary },
  sevBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, borderWidth: 1 },
  sevBadgeText: { fontSize: 11, fontWeight: '600' },
  source: { fontSize: 11, color: c.labelTertiary },
  instruction: { fontSize: 15, color: c.labelPrimary, lineHeight: 22 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 2 },
  metaText: { fontSize: 11, color: c.labelTertiary },
  swipeRevoke: {
    width: 80, backgroundColor: '#FF453A',
    justifyContent: 'center', alignItems: 'center',
    marginBottom: spacing.sm, borderTopRightRadius: radii.md, borderBottomRightRadius: radii.md,
  },
  swipeText: { color: '#fff', fontSize: 12, marginTop: 2 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyWrap: { flex: 1, padding: spacing.md, paddingTop: spacing.sm },
  emptyCard: {
    backgroundColor: c.bgCard,
    borderRadius: radii.lg,
    padding: spacing.lg,
    gap: spacing.md,
  },
  emptyHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  emptyIcon: {
    width: 46,
    height: 46,
    borderRadius: radii.lg,
    backgroundColor: c.tintTeal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyTitle: { fontSize: 19, lineHeight: 24, fontWeight: '800', color: c.labelPrimary },
  emptyHint: { fontSize: 13, color: c.labelSecondary, lineHeight: 18, marginTop: 2 },
  ruleExamples: { gap: spacing.xs },
  ruleExample: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: 9,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  ruleExampleText: { flex: 1, fontSize: 13, lineHeight: 18, color: c.labelPrimary },
  emptyBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.xs,
    paddingHorizontal: spacing.xl,
    paddingVertical: 12,
    backgroundColor: c.brand, borderRadius: radii.md,
  },
  emptyBtnText: { color: '#fff', fontWeight: '600' },
  emptyFootnote: { fontSize: 11, lineHeight: 16, color: c.labelTertiary },
  modalSafe: { flex: 1, backgroundColor: c.bgPrimary },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
  },
  modalCancel: { color: c.labelSecondary, fontSize: 15 },
  modalTitle: { fontSize: 17, fontWeight: '600', color: c.labelPrimary },
  modalSubmit: { color: c.brand, fontSize: 15, fontWeight: '600' },
  modalSubmitDisabled: { color: c.labelQuaternary },
  modalBody: { padding: spacing.md, gap: spacing.md },
  modalHint: { fontSize: 13, color: c.labelSecondary, lineHeight: 20 },
  examplesBox: { backgroundColor: c.bgCard, borderRadius: radii.md, padding: spacing.md, gap: 4 },
  example: { fontSize: 13, color: c.labelSecondary, lineHeight: 22 },
  input: {
    backgroundColor: c.bgCard, borderRadius: radii.md, padding: spacing.md,
    minHeight: 120, fontSize: 15, color: c.labelPrimary,
    textAlignVertical: 'top',
  },
});
