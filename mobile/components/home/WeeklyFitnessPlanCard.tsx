/**
 * WeeklyFitnessPlanCard —— 首页「本周健身计划」入口(C1, P2 · PRD §3.C).
 *
 * 轻量入口卡:有计划时显示一行摘要 + 状态(待确认 / 已排入时间线),点进 /fitness-plan 看全周。
 * 空态 / 出错 → 不渲染(与 WriteIntentCard 一致,不显示噪声卡)。
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { revaColors as C, revaRadii } from '../../constants/revaTheme';
import { Card, Icon, SectionLabel } from '../reva/RevaKit';
import { useWeeklyFitnessPlan } from '../../hooks/useFitness';

export default function WeeklyFitnessPlanCard() {
  const router = useRouter();
  const q = useWeeklyFitnessPlan();

  const plan = q.data;
  // 空态 / 出错 / 本周无计划 → 不渲染。
  if (q.isError || !plan || plan.plan_id == null || (plan.days?.length ?? 0) === 0) {
    return null;
  }

  const isProposed = plan.status === 'proposed';
  const hardCount = plan.days.filter((d) => d.day_type === 'hard').length;
  const restCount = plan.days.filter((d) => d.day_type === 'rest').length;

  return (
    <View>
      <SectionLabel>本周健身计划</SectionLabel>
      <Card
        pad={14}
        onPress={() => router.push('/fitness-plan' as any)}
        accessibilityLabel="本周健身计划,点击查看"
      >
        <View style={styles.row}>
          <View style={styles.icon}>
            <Icon name="activity" size={19} color={C.green600} />
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.title} numberOfLines={1}>
              {plan.goal || '本周训练编排'}
            </Text>
            <Text style={styles.sub} numberOfLines={1}>
              {hardCount} 天强度 · {restCount} 天休息
            </Text>
          </View>
          {isProposed ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>待确认</Text>
            </View>
          ) : (
            <View style={styles.confirmedRow}>
              <Icon name="check-circle-2" size={15} color={C.green600} />
              <Text style={styles.confirmedText}>已排期</Text>
            </View>
          )}
          <Icon name="chevron-right" size={18} color={C.ink3} />
        </View>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  icon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { fontSize: 14.5, fontWeight: '600', color: C.ink1 },
  sub: { fontSize: 12.5, color: C.ink3, marginTop: 2 },
  badge: {
    backgroundColor: C.green50,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeText: { color: C.green600, fontSize: 12, fontWeight: '700' },
  confirmedRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  confirmedText: { color: C.green600, fontSize: 12, fontWeight: '600' },
});
