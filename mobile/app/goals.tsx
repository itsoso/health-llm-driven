import React, { useState, useCallback, useMemo } from 'react';
import { View, Text, FlatList, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, Alert, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { useGoals, useUpdateGoalProgress } from '../hooks/useGoals';
import { generateGoalsFromAnalysis, type GoalResponse } from '../services/goals';
import GoalCard from '../components/goals/GoalCard';
import ProgressUpdateSheet from '../components/goals/ProgressUpdateSheet';
import { spacing, radii, shadows } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createGoalsAgentContext } from '../utils/agentContext';

export default function GoalsScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const qc = useQueryClient();
  const { data: goals, isLoading, refetch, isRefetching } = useGoals('active');
  const progressMutation = useUpdateGoalProgress();
  const [selectedGoal, setSelectedGoal] = useState<GoalResponse | null>(null);
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await generateGoalsFromAnalysis();
      qc.invalidateQueries({ queryKey: ['goals'] });
    } catch {
      Alert.alert('生成失败', '请稍后再试');
    } finally {
      setGenerating(false);
    }
  };

  const handleProgressSubmit = useCallback((value: number, _notes: string) => {
    if (!selectedGoal) return;
    progressMutation.mutate({ id: selectedGoal.id, progressValue: value });
  }, [selectedGoal, progressMutation]);

  const renderItem = ({ item }: { item: GoalResponse }) => (
    <GoalCard goal={item}
      onUpdateProgress={() => setSelectedGoal(item)} />
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>健康目标</Text>
        <View style={{ width: 40 }} />
      </View>

      {isLoading ? (
        <ActivityIndicator color={c.brand} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={goals}
          keyExtractor={i => String(i.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />}
          ListHeaderComponent={
            <GoalsExecutionHeader
              goals={goals ?? []}
              generating={generating}
              onGenerate={handleGenerate}
            />
          }
          ListEmptyComponent={
            <View style={styles.emptyBox}>
              <Ionicons name="flag-outline" size={48} color={c.labelQuaternary} />
              <Text style={txt.empty}>暂无目标</Text>
              <Text style={txt.emptyHint}>点击"AI 生成目标"自动创建</Text>
            </View>
          }
        />
      )}

      <ProgressUpdateSheet goal={selectedGoal} visible={!!selectedGoal}
        onClose={() => setSelectedGoal(null)} onSubmit={handleProgressSubmit} />
    </SafeAreaView>
  );
}

function GoalsExecutionHeader({
  goals,
  generating,
  onGenerate,
}: {
  goals: GoalResponse[];
  generating: boolean;
  onGenerate: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const weeklyCommitments = goals
    .filter(goal => goal.goal_period === 'weekly' || goal.priority === 1)
    .slice(0, 3);
  const todayActions = goals
    .map(goal => ({
      id: goal.id,
      title: goal.title,
      action: goal.implementation_steps?.trim() || goal.description?.trim(),
    }))
    .filter(item => Boolean(item.action))
    .slice(0, 3);

  return (
    <View style={styles.headerStack}>
      <View style={[styles.commitmentPanel, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
        <View style={styles.panelTitleRow}>
          <View style={[styles.panelIcon, { backgroundColor: c.brandLight }]}>
            <Ionicons name="flag-outline" size={17} color={c.brand} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={txt.panelTitle}>本周承诺</Text>
            <Text style={txt.panelSub}>{goals.length} 个活跃目标</Text>
          </View>
        </View>
        {weeklyCommitments.length > 0 ? (
          weeklyCommitments.map(goal => (
            <View key={goal.id} style={styles.commitmentRow}>
              <Text style={txt.commitmentTitle} numberOfLines={1}>{goal.title}</Text>
              <Text style={txt.commitmentProgress}>
                {formatGoalProgress(goal)}
              </Text>
            </View>
          ))
        ) : (
          <Text style={txt.emptyInline}>先生成目标，再把本周承诺固定下来。</Text>
        )}
      </View>

      <View style={[styles.todayActionPanel, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
        <View style={styles.panelTitleRow}>
          <View style={[styles.panelIcon, { backgroundColor: `${c.green}18` }]}>
            <Ionicons name="checkmark-circle-outline" size={17} color={c.green} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={txt.panelTitle}>今日动作</Text>
            <Text style={txt.panelSub}>把目标拆成今天能完成的事</Text>
          </View>
        </View>
        {todayActions.length > 0 ? (
          todayActions.map((item, index) => (
            <View key={item.id} style={styles.todayActionRow}>
              <Text style={txt.todayActionIndex}>{index + 1}</Text>
              <View style={{ flex: 1 }}>
                <Text style={txt.todayActionText} numberOfLines={2}>{item.action}</Text>
                <Text style={txt.todayActionGoal} numberOfLines={1}>{item.title}</Text>
              </View>
            </View>
          ))
        ) : (
          <Text style={txt.emptyInline}>暂无拆解动作，先让 Agent 调整目标。</Text>
        )}
      </View>

      <View style={styles.actionRow}>
        <TouchableOpacity style={styles.actionBtn} onPress={onGenerate} disabled={generating} activeOpacity={0.7}>
          <Ionicons name="sparkles-outline" size={18} color={c.brand} />
          <Text style={txt.actionText}>{generating ? 'AI 分析中...' : 'AI 生成目标'}</Text>
        </TouchableOpacity>
        <AgentFeedbackLink
          label="跟 Agent 调整健康目标"
          accessibilityLabel="跟 Agent 调整健康目标"
          prompt="请基于我的当前健康目标，判断目标是否合理、优先级是否需要调整，并拆解成接下来 7 天可执行的行动。"
          context={createGoalsAgentContext(goals as any)}
          badge={`活跃目标 ${goals.length} 个`}
          style={styles.agentLink}
        />
      </View>
    </View>
  );
}

function formatGoalProgress(goal: GoalResponse): string {
  if (goal.current_value == null || goal.target_value == null) return '待开始';
  const unit = goal.target_unit ?? '';
  return `${goal.current_value}/${goal.target_value}${unit}`;
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg, paddingBottom: 100 },
  headerStack: { gap: spacing.md, marginBottom: spacing.lg },
  commitmentPanel: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadows.subtle,
  },
  todayActionPanel: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.sm,
  },
  panelTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  panelIcon: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  commitmentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: 5,
  },
  todayActionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    paddingVertical: 5,
  },
  actionRow: { marginBottom: spacing.lg },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, ...shadows.subtle,
  },
  agentLink: { marginTop: spacing.sm },
  emptyBox: { alignItems: 'center', gap: 8, paddingVertical: 60 },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  panelTitle: { fontSize: 16, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  panelSub: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  commitmentTitle: { flex: 1, fontSize: 14, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  commitmentProgress: { fontSize: 12, fontWeight: '800', color: c.brand } as TextStyle,
  todayActionIndex: { width: 18, fontSize: 12, fontWeight: '900', color: c.green, textAlign: 'center' } as TextStyle,
  todayActionText: { fontSize: 14, fontWeight: '700', color: c.labelPrimary, lineHeight: 19 } as TextStyle,
  todayActionGoal: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  emptyInline: { fontSize: 13, color: c.labelTertiary, lineHeight: 18 } as TextStyle,
  actionText: { fontSize: 15, fontWeight: '600', color: c.brand } as TextStyle,
  empty: { fontSize: 16, fontWeight: '600', color: c.labelTertiary } as TextStyle,
  emptyHint: { fontSize: 13, color: c.labelQuaternary } as TextStyle,
});
