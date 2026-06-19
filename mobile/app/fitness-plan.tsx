/**
 * /fitness-plan —— 本周健身计划 (C1, P2 · proactive-planning PRD §3.C).
 *
 * MovementCoach 按目标 + 训练负荷(ACWR)生成 7 天难/易/休。status=="proposed" 时
 * 一键【确认】排进时间线(T2 写层,镜像 WriteIntentCard 交互);==="confirmed" 显示「已排入时间线」。
 * 点某天有 exercise_key 的训练 → C2 动作图文指导。全程 hedged,不开方不出因果。
 */
import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';

import { revaColors as C, revaRadii } from '../constants/revaTheme';
import { Card, Icon, SectionLabel } from '../components/reva/RevaKit';
import {
  useConfirmWeeklyFitnessPlan,
  useDismissWeeklyFitnessPlan,
  useWeeklyFitnessPlan,
} from '../hooks/useFitness';
import type { FitnessDayType, FitnessPlanDay } from '../services/fitness';

// day_type → 三步临床语义色(hard=偏高红 / easy=达标绿 / rest=信息蓝)
const DAY_TYPE_META: Record<
  FitnessDayType,
  { label: string; fg: string; bg: string; line: string }
> = {
  hard: { label: '强', fg: '#D5503A', bg: '#FBE8E4', line: '#F3CDC4' },
  easy: { label: '轻', fg: C.green500, bg: C.green50, line: C.green100 },
  rest: { label: '休', fg: '#2A6FDB', bg: '#E7EEFB', line: '#CBDCF6' },
};

function DayTypeChip({ type }: { type: FitnessDayType }) {
  const m = DAY_TYPE_META[type] ?? DAY_TYPE_META.rest;
  return (
    <View style={[styles.chip, { backgroundColor: m.bg, borderColor: m.line }]}>
      <Text style={[styles.chipText, { color: m.fg }]}>{m.label}</Text>
    </View>
  );
}

function DayRow({
  day,
  last,
  onPressWorkout,
}: {
  day: FitnessPlanDay;
  last: boolean;
  onPressWorkout: (exerciseKey: string) => void;
}) {
  const w = day.workout;
  const hasGuide = !!w && w.exercise_key.length > 0;
  const tappable = hasGuide;

  const body = (
    <View style={[styles.dayRow, last && { borderBottomWidth: 0 }]}>
      <View style={styles.dayLeft}>
        <Text style={styles.weekday}>{day.weekday}</Text>
        <Text style={styles.dayDate}>{day.date.slice(5)}</Text>
        <DayTypeChip type={day.day_type} />
      </View>
      <View style={styles.dayMain}>
        {w ? (
          <>
            <View style={styles.workoutTitleRow}>
              <Text style={styles.workoutName} numberOfLines={2}>
                {w.name}
              </Text>
              {hasGuide ? (
                <Icon name="chevron-right" size={18} color={C.ink3} />
              ) : null}
            </View>
            <View style={styles.workoutMetaRow}>
              {/* duration_min 是整数;0 视作未给(不编造) */}
              {w.duration_min > 0 ? (
                <Text style={styles.workoutMeta}>{w.duration_min} 分钟</Text>
              ) : null}
              {w.intensity_note ? (
                <Text style={styles.workoutMeta} numberOfLines={1}>
                  {w.duration_min > 0 ? ' · ' : ''}
                  {w.intensity_note}
                </Text>
              ) : null}
            </View>
            {day.rationale ? (
              <Text style={styles.rationale} numberOfLines={3}>
                {day.rationale}
              </Text>
            ) : null}
          </>
        ) : (
          <>
            <Text style={styles.restName}>休息日</Text>
            {day.rationale ? (
              <Text style={styles.rationale} numberOfLines={3}>
                {day.rationale}
              </Text>
            ) : null}
          </>
        )}
      </View>
    </View>
  );

  if (tappable && w) {
    return (
      <Pressable
        onPress={() => onPressWorkout(w.exercise_key)}
        accessibilityRole="button"
        accessibilityLabel={`${day.weekday} ${w.name},查看动作指导`}
        style={({ pressed }) => pressed && { opacity: 0.7 }}
      >
        {body}
      </Pressable>
    );
  }
  return body;
}

export default function FitnessPlanScreen() {
  const router = useRouter();
  const { data, isLoading, isError, refetch, isRefetching } = useWeeklyFitnessPlan();
  const confirm = useConfirmWeeklyFitnessPlan();
  const dismiss = useDismissWeeklyFitnessPlan();

  const onConfirm = () => {
    if (data?.plan_id == null) return;
    confirm.mutate(data.plan_id, {
      onSuccess: () => {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(
          () => {},
        );
      },
    });
  };
  const onDismiss = () => {
    if (data?.plan_id == null) return;
    dismiss.mutate(data.plan_id, {
      onSuccess: () => router.back(),
    });
  };

  const goGuide = (exerciseKey: string) => {
    router.push({
      pathname: '/exercise-guide/[key]' as any,
      params: { key: exerciseKey },
    });
  };

  const Header = (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} hitSlop={10} style={styles.back}>
        <Ionicons name="chevron-back" size={26} color={C.ink1} />
      </TouchableOpacity>
      <Text style={styles.headerTitle}>本周健身计划</Text>
      <View style={styles.back} />
    </View>
  );

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        {Header}
        <View style={styles.center}>
          <ActivityIndicator color={C.green500} />
        </View>
      </SafeAreaView>
    );
  }

  if (isError || !data) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        {Header}
        <View style={styles.center}>
          <Icon name="alert-triangle" size={30} color={C.ink3} />
          <Text style={styles.emptyTitle}>暂时拉不到本周计划</Text>
          <Text style={styles.emptySub}>请检查网络后重试</Text>
          <Pressable style={styles.retryBtn} onPress={() => refetch()}>
            <Text style={styles.retryText}>重试</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  // 后端可能返回「本周还没有计划」(plan_id=null & days 空)→ 中性空态,不渲染半截卡。
  const days = Array.isArray(data.days) ? data.days : [];
  if (days.length === 0) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        {Header}
        <View style={styles.center}>
          <Icon name="calendar-check" size={30} color={C.ink3} />
          <Text style={styles.emptyTitle}>本周还没有健身计划</Text>
          <Text style={styles.emptySub}>
            等积累足够的训练负荷数据后,这里会给出难/易/休的一周编排。
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  const isProposed = data.status === 'proposed';
  const isConfirmed = data.status === 'confirmed';
  const busy = confirm.isPending || dismiss.isPending;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      {Header}
      <ScrollView contentContainerStyle={styles.content}>
        {/* 目标 + 负荷概览 */}
        <Card pad={16} style={{ marginBottom: 16 }}>
          <Text style={styles.weekStart}>本周 · 起始 {data.week_start}</Text>
          {data.goal ? <Text style={styles.goal}>{data.goal}</Text> : null}
          <View style={styles.overviewRow}>
            {data.acwr != null ? (
              <View style={styles.overviewItem}>
                <Text style={styles.overviewLabel}>负荷比 ACWR</Text>
                <Text style={styles.overviewValue}>{data.acwr.toFixed(2)}</Text>
              </View>
            ) : null}
          </View>
          {data.readiness_note ? (
            <Text style={styles.readinessNote}>{data.readiness_note}</Text>
          ) : null}
          {isConfirmed ? (
            <View style={styles.confirmedBadge}>
              <Icon name="check-circle-2" size={16} color={C.green600} />
              <Text style={styles.confirmedText}>已排入时间线</Text>
            </View>
          ) : null}
        </Card>

        <SectionLabel>一周安排</SectionLabel>
        <Card pad={0}>
          {days.map((d, i) => (
            <DayRow
              key={`${d.date}-${i}`}
              day={d}
              last={i === days.length - 1}
              onPressWorkout={goGuide}
            />
          ))}
        </Card>

        {/* hedged 免责声明 */}
        {data.disclaimer ? (
          <Text style={styles.disclaimer}>{data.disclaimer}</Text>
        ) : null}

        {/* 底部留白给 sticky 确认条 */}
        {isProposed ? <View style={{ height: 96 }} /> : null}
      </ScrollView>

      {/* sticky 确认条(仅 proposed;镜像 WriteIntentCard 一键确认) */}
      {isProposed ? (
        <View style={styles.stickyBar}>
          {busy ? (
            <View style={styles.confirmBtn}>
              <ActivityIndicator color={C.greenOn} />
            </View>
          ) : (
            <>
              <Pressable
                style={({ pressed }) => [styles.dismissBtn, pressed && { opacity: 0.6 }]}
                onPress={onDismiss}
                accessibilityRole="button"
                accessibilityLabel="忽略本周计划"
              >
                <Text style={styles.dismissText}>忽略</Text>
              </Pressable>
              <Pressable
                style={({ pressed }) => [styles.confirmBtn, pressed && { opacity: 0.9 }]}
                onPress={onConfirm}
                accessibilityRole="button"
                accessibilityLabel="一键确认,排入时间线"
              >
                <Icon name="check" size={17} color={C.greenOn} />
                <Text style={styles.confirmText}>一键确认排期</Text>
              </Pressable>
            </>
          )}
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  back: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: 17, fontWeight: '700', color: C.ink1 },
  content: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 24 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 8 },

  emptyTitle: { fontSize: 16, fontWeight: '700', color: C.ink1, marginTop: 4 },
  emptySub: { fontSize: 13.5, color: C.ink3, textAlign: 'center', lineHeight: 20 },
  retryBtn: {
    marginTop: 8,
    backgroundColor: C.green500,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 22,
    paddingVertical: 10,
  },
  retryText: { color: C.greenOn, fontSize: 14, fontWeight: '700' },

  weekStart: { fontSize: 12, fontWeight: '600', color: C.ink3, marginBottom: 4 },
  goal: { fontSize: 16, fontWeight: '700', color: C.ink1, lineHeight: 22 },
  overviewRow: { flexDirection: 'row', gap: 18, marginTop: 12 },
  overviewItem: {},
  overviewLabel: { fontSize: 11, fontWeight: '600', color: C.ink3 },
  overviewValue: {
    fontFamily: 'IBMPlexMono',
    fontWeight: '500',
    fontSize: 20,
    color: C.ink1,
    marginTop: 2,
  },
  readinessNote: { fontSize: 13.5, color: C.ink2, lineHeight: 20, marginTop: 10 },
  confirmedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 12,
    alignSelf: 'flex-start',
    backgroundColor: C.green50,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  confirmedText: { color: C.green600, fontSize: 13, fontWeight: '700' },

  dayRow: {
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  dayLeft: { width: 48, alignItems: 'center', gap: 4 },
  weekday: { fontSize: 14, fontWeight: '700', color: C.ink1 },
  dayDate: { fontFamily: 'IBMPlexMono', fontSize: 11, color: C.ink3 },
  chip: {
    minWidth: 24,
    alignItems: 'center',
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 8,
    paddingVertical: 2,
    marginTop: 2,
  },
  chipText: { fontSize: 12, fontWeight: '700' },
  dayMain: { flex: 1, minWidth: 0 },
  workoutTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  workoutName: { flex: 1, fontSize: 15, fontWeight: '600', color: C.ink1 },
  workoutMetaRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 3 },
  workoutMeta: { fontSize: 12.5, color: C.ink3 },
  restName: { fontSize: 15, fontWeight: '600', color: C.ink3 },
  rationale: { fontSize: 12.5, color: C.ink2, lineHeight: 18, marginTop: 6 },

  disclaimer: {
    fontSize: 11.5,
    color: C.ink3,
    lineHeight: 17,
    marginTop: 16,
    paddingHorizontal: 4,
  },

  stickyBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 28,
    backgroundColor: C.surface,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  confirmBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    backgroundColor: C.green500,
    borderRadius: revaRadii.pill,
    paddingVertical: 15,
  },
  confirmText: { color: C.greenOn, fontSize: 16, fontWeight: '700' },
  dismissBtn: {
    paddingHorizontal: 20,
    paddingVertical: 15,
    borderRadius: revaRadii.pill,
    borderWidth: 1.5,
    borderColor: C.lineStrong,
  },
  dismissText: { color: C.ink2, fontSize: 15, fontWeight: '600' },
});
