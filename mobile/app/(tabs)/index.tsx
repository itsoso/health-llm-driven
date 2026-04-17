import React from 'react';
import { ScrollView, View, Text, StyleSheet, RefreshControl, ViewStyle, TextStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useDashboardData, useLatestGarmin } from '@/hooks/useDashboardData';
import GreetingHeader from '@/components/dashboard/GreetingHeader';
import HealthScoreHero from '@/components/dashboard/HealthScoreHero';
import VitalsGrid from '@/components/dashboard/VitalsGrid';
import ActivityRingBar from '@/components/dashboard/ActivityRingBar';
import TrendMiniCharts from '@/components/dashboard/TrendMiniCharts';
import SupplementCheckin from '@/components/dashboard/SupplementCheckin';
import SectionHeader from '@/components/design-system/SectionHeader';
import HealthCard from '@/components/design-system/HealthCard';
import { colors, typography, spacing, radii, shadows, metricColors } from '@/constants/theme';

export default function DashboardScreen() {
  const { data, isLoading, refetch, isRefetching } = useDashboardData();
  const garmin = useLatestGarmin(data);

  // ── Score ──
  const score = data?.healthScore?.total_score ?? data?.healthScore?.score ?? 0;
  const dims = (data?.healthScore?.dimensions || []).map((d: any) => ({
    name: d.name,
    score: d.score ?? 0,
    color: d.name === '运动' ? '#FF6723' : d.name === '睡眠' ? '#BF5AF2' : d.name === '体征' ? '#FF375F' : '#0A8F8F',
  }));

  // ── Garmin vitals ──
  const sleepMin = garmin?.total_sleep_duration;
  const sleepHours = sleepMin ? sleepMin / 60 : null;
  const deepMin = garmin?.deep_sleep_duration;
  const deepHours = deepMin ? deepMin / 60 : null;
  const hr = garmin?.resting_heart_rate;
  const hrv = garmin?.hrv;
  const battery = garmin?.body_battery_most_charged ?? garmin?.body_battery_current;
  const batteryMax = garmin?.body_battery_most_charged;
  const steps = garmin?.steps ?? 0;
  const activeMin = garmin?.active_minutes ?? 0;
  const calories = garmin?.active_calories ?? 0;
  const stress = garmin?.stress_level;
  const spo2 = garmin?.spo2_avg;

  // ── Weather ──
  const weather = data?.weather?.weather ?? data?.weather;
  const aqi = data?.airQuality;
  const forecast = data?.weatherForecast?.forecasts;
  const profile = data?.profile;
  const city = profile?.manual_location?.city || profile?.detected_location?.city || profile?.city;

  // ── Other data ──
  const waterTotal = Array.isArray(data?.waterRecords)
    ? data.waterRecords.reduce((s: number, r: any) => s + (r.amount || 0), 0)
    : 0;
  const suppCount = Array.isArray(data?.supplements) ? data.supplements.length : 0;
  const suppTaken = Array.isArray(data?.supplements)
    ? data.supplements.filter((s: any) => s.record?.taken || s.is_taken).length
    : 0;
  const weightStats = data?.weightStats;
  const bpStats = data?.bloodPressureStats;
  const dietRecords = data?.dietRecords?.meals ?? (Array.isArray(data?.dietRecords) ? data.dietRecords : []);
  const medications = data?.medicationToday;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Greeting */}
        <GreetingHeader weather={weather} aqi={aqi} forecast={forecast} city={city} />

        {/* Health Score Hero */}
        <HealthScoreHero totalScore={score} dimensions={dims.length > 0 ? dims : undefined} />

        {/* Today's Vitals */}
        <SectionHeader title="今日数据" />
        <VitalsGrid
          sleep={sleepHours}
          deepSleep={deepHours}
          heartRate={hr}
          hrv={hrv}
          bodyBattery={battery}
          batteryMax={batteryMax}
        />

        {/* Activity Rings */}
        <ActivityRingBar steps={steps} activeMin={activeMin} calories={calories} />

        {/* Quick Stats Row */}
        <View style={styles.statsRow}>
          <StatChip icon="water-outline" color={metricColors.water.main} bg={metricColors.water.tint} label="饮水" value={`${waterTotal}`} unit="ml" />
          <StatChip icon="medical-outline" color={metricColors.supplements.main} bg={metricColors.supplements.tint} label="补剂" value={`${suppTaken}/${suppCount}`} />
          <StatChip icon="cloudy-outline" color={metricColors.stress.main} bg={metricColors.stress.tint} label="压力" value={stress != null ? `${stress}` : '--'} />
          <StatChip icon="fitness-outline" color={colors.teal} bg={colors.tintTeal} label="血氧" value={spo2 != null ? `${spo2}%` : '--'} />
        </View>

        {/* Supplement Checkin */}
        <SupplementCheckin supplements={data?.supplements || []} onToggle={refetch} />

        {/* Weekly Trends */}
        <TrendMiniCharts garminDays={Array.isArray(data?.garminDaily) ? data.garminDaily : []} />

        {/* Medication Status */}
        {Array.isArray(medications) && medications.length > 0 && (
          <>
            <SectionHeader title="用药状态" />
            <View style={styles.medRow}>
              {medications.map((m: any) => (
                <View key={m.medication_id} style={[styles.medChip, { backgroundColor: m.taken_count > 0 ? colors.tintGreen : colors.bgPrimary }]}>
                  <Ionicons name={m.taken_count > 0 ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={m.taken_count > 0 ? colors.green : colors.labelTertiary} />
                  <Text style={textStyles.medName} numberOfLines={1}>{m.name}</Text>
                </View>
              ))}
            </View>
          </>
        )}

        {/* Body Stats */}
        {(weightStats?.current_weight || bpStats?.average_systolic) && (
          <HealthCard title="身体数据" icon="body-outline" iconColor={colors.brand} iconBg={colors.brandLight}>
            <View style={styles.bodyRow}>
              {weightStats?.current_weight != null && (
                <View style={styles.bodyItem}>
                  <Text style={textStyles.bodyValue}>{weightStats.current_weight}<Text style={textStyles.bodyUnit}>kg</Text></Text>
                  <Text style={textStyles.bodyLabel}>体重</Text>
                  {weightStats.weight_change_7d != null && (
                    <Text style={[textStyles.bodyChange, { color: weightStats.weight_change_7d <= 0 ? colors.green : colors.red }]}>
                      7天 {weightStats.weight_change_7d > 0 ? '+' : ''}{weightStats.weight_change_7d}kg
                    </Text>
                  )}
                </View>
              )}
              {bpStats?.average_systolic != null && (
                <View style={styles.bodyItem}>
                  <Text style={textStyles.bodyValue}>{Math.round(bpStats.average_systolic)}/{Math.round(bpStats.average_diastolic)}</Text>
                  <Text style={textStyles.bodyLabel}>血压</Text>
                </View>
              )}
            </View>
          </HealthCard>
        )}

        {/* Diet */}
        <HealthCard title="今日饮食" icon="restaurant-outline" iconColor={colors.orange} iconBg={colors.tintOrange}>
          {Array.isArray(dietRecords) && dietRecords.length > 0 ? (
            dietRecords.slice(0, 3).map((d: any, i: number) => (
              <View key={i} style={styles.dietRow}>
                <Text style={textStyles.dietType}>{d.meal_type || '餐食'}</Text>
                <Text style={textStyles.dietDesc} numberOfLines={1}>{d.description || d.food_items || '--'}</Text>
                {d.total_calories ? <Text style={textStyles.dietCal}>{d.total_calories}kcal</Text> : null}
              </View>
            ))
          ) : (
            <Text style={textStyles.emptyText}>今天还没有饮食记录</Text>
          )}
        </HealthCard>

        <View style={{ height: 100 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Inline Components ──

function StatChip({ icon, color, bg, label, value, unit }: { icon: any; color: string; bg: string; label: string; value: string; unit?: string }) {
  return (
    <View style={styles.statChip}>
      <View style={[styles.statIconDot, { backgroundColor: bg }]}>
        <Ionicons name={icon} size={12} color={color} />
      </View>
      <Text style={textStyles.statValue}>{value}{unit ? <Text style={textStyles.statUnit}>{unit}</Text> : null}</Text>
      <Text style={textStyles.statLabel}>{label}</Text>
    </View>
  );
}

const getAqiColor = (v: number | null) =>
  !v ? colors.labelTertiary : v <= 50 ? colors.green : v <= 100 ? colors.amber : colors.red;

// ── Styles ──

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  scroll: { flex: 1 },
  content: { padding: spacing.xl },

  // Stats row
  statsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  statChip: {
    flex: 1,
    backgroundColor: colors.bgCard,
    borderRadius: radii.md,
    paddingVertical: 10,
    paddingHorizontal: 6,
    alignItems: 'center',
    gap: 4,
    ...shadows.subtle,
  },
  statIconDot: {
    width: 22, height: 22, borderRadius: 7,
    alignItems: 'center', justifyContent: 'center',
  },

  // Medication
  medRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.lg },
  medChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radii.full,
  },

  // Body stats
  bodyRow: { flexDirection: 'row', gap: spacing.xxl },
  bodyItem: { alignItems: 'center' } as ViewStyle,

  // Diet
  dietRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, gap: spacing.sm },

  // Environment
  envRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: 6 },
});

// Text styles kept separate to avoid StyleSheet type conflicts with fontVariant
const textStyles = {
  statValue: { fontSize: 16, fontWeight: '700' as const, color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  statUnit: { fontSize: 11, fontWeight: '400' as const, color: colors.labelSecondary } as TextStyle,
  statLabel: { fontSize: 10, fontWeight: '500' as const, color: colors.labelTertiary } as TextStyle,
  medName: { fontSize: 13, color: colors.labelPrimary, maxWidth: 80 } as TextStyle,
  bodyValue: { fontSize: 22, fontWeight: '700' as const, color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  bodyUnit: { fontSize: 13, color: colors.labelSecondary } as TextStyle,
  bodyLabel: { fontSize: 11, fontWeight: '500' as const, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  bodyChange: { fontSize: 11, fontWeight: '500' as const, marginTop: 2 } as TextStyle,
  dietType: { fontSize: 11, fontWeight: '500' as const, color: colors.labelSecondary, width: 32 } as TextStyle,
  dietDesc: { fontSize: 15, color: colors.labelPrimary, flex: 1 } as TextStyle,
  dietCal: { fontSize: 13, color: colors.labelSecondary } as TextStyle,
  emptyText: { fontSize: 13, color: colors.labelTertiary, textAlign: 'center' as const, paddingVertical: spacing.lg } as TextStyle,
  envText: { fontSize: 15, color: colors.labelPrimary } as TextStyle,
};
