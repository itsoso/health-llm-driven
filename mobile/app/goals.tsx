import React, { useState, useCallback } from 'react';
import { View, Text, FlatList, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, Alert, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { useGoals, useUpdateGoalProgress } from '@/hooks/useGoals';
import { createGoal, generateGoalsFromAnalysis, type GoalResponse, type GoalCreate } from '@/services/goals';
import GoalCard from '@/components/goals/GoalCard';
import ProgressUpdateSheet from '@/components/goals/ProgressUpdateSheet';
import SectionHeader from '@/components/design-system/SectionHeader';
import { colors, spacing, radii, shadows } from '@/constants/theme';

export default function GoalsScreen() {
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
      onPress={() => {}}
      onUpdateProgress={() => setSelectedGoal(item)} />
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>健康目标</Text>
        <View style={{ width: 40 }} />
      </View>

      {isLoading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={goals}
          keyExtractor={i => String(i.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
          ListHeaderComponent={
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.actionBtn} onPress={handleGenerate} disabled={generating} activeOpacity={0.7}>
                <Ionicons name="sparkles-outline" size={18} color={colors.brand} />
                <Text style={txt.actionText}>{generating ? 'AI 分析中...' : 'AI 生成目标'}</Text>
              </TouchableOpacity>
            </View>
          }
          ListEmptyComponent={
            <View style={styles.emptyBox}>
              <Ionicons name="flag-outline" size={48} color={colors.labelQuaternary} />
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

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg, paddingBottom: 100 },
  actionRow: { marginBottom: spacing.lg },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, ...shadows.subtle,
  },
  emptyBox: { alignItems: 'center', gap: 8, paddingVertical: 60 },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  actionText: { fontSize: 15, fontWeight: '600', color: colors.brand } as TextStyle,
  empty: { fontSize: 16, fontWeight: '600', color: colors.labelTertiary } as TextStyle,
  emptyHint: { fontSize: 13, color: colors.labelQuaternary } as TextStyle,
};
