import React, { useMemo } from 'react';
import { View, Text, FlatList, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { useWorkoutList, useWorkoutStats } from '../hooks/useWorkouts';
import { syncGarminWorkouts, type WorkoutSummary } from '../services/workouts';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../constants/revaTheme';
import { createWorkoutAgentContext, pushChatWithContext } from '../utils/agentContext';

const TYPE_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  running: 'walk-outline',
  cycling: 'bicycle-outline',
  swimming: 'water-outline',
  strength: 'barbell-outline',
  yoga: 'body-outline',
  hiking: 'trail-sign-outline',
  default: 'fitness-outline',
};

export default function WorkoutListScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: workouts, isLoading, refetch, isRefetching } = useWorkoutList();
  const { data: stats } = useWorkoutStats();
  const [syncing, setSyncing] = React.useState(false);

  const handleChatWorkouts = React.useCallback(() => {
    pushChatWithContext(router, {
      prompt: '请基于我最近的运动记录, 分析训练负荷、恢复风险和下一次训练怎么安排。',
      context: createWorkoutAgentContext({
        workouts,
        stats,
      }),
      badge: `基于最近 ${workouts?.length ?? 0} 次运动`,
    });
  }, [router, stats, workouts]);

  const handleSync = async () => {
    setSyncing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await syncGarminWorkouts();
      qc.invalidateQueries({ queryKey: ['workouts'] });
      qc.invalidateQueries({ queryKey: ['workoutStats'] });
    } catch { Alert.alert('同步失败', '运动数据同步失败'); } finally {
      setSyncing(false);
    }
  };

  const renderItem = ({ item }: { item: WorkoutSummary }) => {
    const icon = TYPE_ICONS[(item.workout_type || '').toLowerCase()] || TYPE_ICONS.default;
    const durationMin = item.duration_seconds ? Math.round(item.duration_seconds / 60) : 0;
    return (
      <TouchableOpacity style={styles.row}
        onPress={() => router.push(`/workout-detail?id=${item.id}` as any)}
        activeOpacity={0.7}>
        <View style={styles.iconCircle}>
          <Ionicons name={icon} size={18} color={C.green500} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={txt.type}>{item.workout_name || item.workout_type || '运动'}</Text>
          <Text style={txt.time}>{item.workout_date ? new Date(item.workout_date).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', weekday: 'short' }) : ''}</Text>
        </View>
        <View style={styles.metaCol}>
          <Text style={txt.duration}>{durationMin}min</Text>
          {item.calories != null && <Text style={txt.cal}>{item.calories}kcal</Text>}
        </View>
        <Ionicons name="chevron-forward" size={14} color={C.ink3} />
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={C.ink1} />
        </TouchableOpacity>
        <Text style={txt.title}>运动记录</Text>
        <TouchableOpacity onPress={handleSync} style={styles.backBtn} disabled={syncing}>
          <Ionicons name="sync-outline" size={20} color={syncing ? C.ink3 : C.green500} />
        </TouchableOpacity>
      </View>

      {/* Stats summary */}
      {stats && (
        <View style={styles.statsRow}>
          <StatBadge label="本月次数" value={`${stats.total_workouts ?? 0}`} />
          <StatBadge label="总时长" value={`${Math.round(stats.total_duration_minutes ?? 0)}min`} />
          <StatBadge label="总消耗" value={`${Math.round(stats.total_calories ?? 0)}kcal`} />
          <StatBadge label="总距离" value={`${(stats.total_distance_km ?? 0).toFixed(1)}km`} />
        </View>
      )}
      {(workouts?.length ?? 0) > 0 && (
        <TouchableOpacity
          style={[styles.agentLink, { borderColor: C.line }]}
          onPress={handleChatWorkouts}
          activeOpacity={0.75}
          accessibilityRole="button"
          accessibilityLabel="跟 Agent 详细聊运动记录"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={16} color={C.green500} />
          <Text style={[txt.agentLinkText, { color: C.green500 }]}>跟 Agent 详细聊运动安排</Text>
          <Ionicons name="chevron-forward" size={15} color={C.green500} style={{ marginLeft: 'auto' }} />
        </TouchableOpacity>
      )}

      {isLoading ? (
        <ActivityIndicator color={C.green500} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={workouts}
          keyExtractor={i => String(i.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={C.green500} />}
          ListEmptyComponent={<Text style={txt.empty}>暂无运动记录</Text>}
        />
      )}
    </SafeAreaView>
  );
}

function StatBadge({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.statBadge}>
      <Text style={txt.statVal}>{value}</Text>
      <Text style={txt.statLabel}>{label}</Text>
    </View>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / r-lg 18 / 时长卡路里走等宽 mono。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2 },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  statsRow: {
    flexDirection: 'row', gap: 8, paddingHorizontal: revaSpacing.s4, marginBottom: revaSpacing.s3,
  },
  agentLink: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3,
    marginHorizontal: revaSpacing.s4,
    marginBottom: revaSpacing.s3,
  },
  statBadge: {
    flex: 1, backgroundColor: C.surface, borderRadius: revaRadii.md,
    padding: revaSpacing.s2, alignItems: 'center', ...revaShadows.sm,
  },
  list: { paddingHorizontal: revaSpacing.s4, paddingBottom: 100 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    padding: revaSpacing.s4, marginBottom: revaSpacing.s2, ...revaShadows.sm,
  },
  iconCircle: {
    width: 36, height: 36, borderRadius: revaRadii.sm,
    backgroundColor: C.green50, alignItems: 'center', justifyContent: 'center',
  },
  metaCol: { alignItems: 'flex-end', marginRight: 4 },
});

// 时长/卡路里/距离/次数/日期走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1, textAlign: 'center' } as TextStyle,
  type: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '600', color: C.ink1 } as TextStyle,
  time: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink2, marginTop: 2 } as TextStyle,
  duration: { fontFamily: revaFonts.mono, fontSize: 14, fontWeight: '700', color: C.ink1 } as TextStyle,
  cal: { fontFamily: revaFonts.mono, fontSize: 11, color: C.ink2, marginTop: 1 } as TextStyle,
  empty: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3, textAlign: 'center', marginTop: 40 } as TextStyle,
  agentLinkText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600' } as TextStyle,
  statVal: { fontFamily: revaFonts.mono, fontSize: 16, fontWeight: '700', color: C.ink1 } as TextStyle,
  statLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2, marginTop: 2 } as TextStyle,
};
