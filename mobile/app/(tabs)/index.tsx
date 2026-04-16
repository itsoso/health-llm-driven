import React from 'react';
import {
  ScrollView,
  View,
  Text,
  StyleSheet,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useDashboardData, useLatestGarmin } from '@/hooks/useDashboardData';
import ScoreRing from '@/components/ScoreRing';
import VitalTile from '@/components/VitalTile';
import CounterChip from '@/components/CounterChip';

export default function DashboardScreen() {
  const { data, isLoading, refetch, isRefetching } = useDashboardData();
  const garmin = useLatestGarmin(data);

  const score = data?.healthScore?.score ?? 0;
  const sleep = garmin?.sleep_hours ?? garmin?.sleep_duration_hours;
  const hrv = garmin?.hrv_weekly_avg ?? garmin?.hrv;
  const energy = garmin?.body_battery_max ?? garmin?.body_battery;
  const hr = garmin?.resting_heart_rate ?? garmin?.rhr;
  const steps = garmin?.steps ?? 0;
  const activeMin = garmin?.active_minutes ?? garmin?.moderate_activity_minutes ?? 0;
  const stress = garmin?.avg_stress ?? garmin?.stress_avg;

  const waterTotal = Array.isArray(data?.waterRecords)
    ? data.waterRecords.reduce((s: number, r: any) => s + (r.amount || 0), 0)
    : 0;
  const suppCount = Array.isArray(data?.supplements)
    ? data.supplements.length
    : 0;

  const weather = data?.weather;
  const aqi = data?.airQuality;

  const checkin = data?.checkin;
  const dietRecords = data?.dietRecords;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor="#007AFF"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        {/* Hero Card */}
        <View style={styles.heroCard}>
          <View style={styles.heroTop}>
            <ScoreRing score={score} size={110} strokeWidth={9} />
            <View style={styles.vitalsGrid}>
              <VitalTile
                label="睡眠"
                value={sleep ? `${Number(sleep).toFixed(1)}` : '--'}
                unit="h"
                icon="moon-outline"
                color="#5856D6"
              />
              <VitalTile
                label="HRV"
                value={hrv ?? '--'}
                unit="ms"
                icon="pulse-outline"
                color="#30B0C7"
              />
              <VitalTile
                label="电量"
                value={energy ?? '--'}
                icon="battery-charging-outline"
                color="#34C759"
              />
              <VitalTile
                label="心率"
                value={hr ?? '--'}
                unit="bpm"
                icon="fitness-outline"
                color="#FF3B30"
              />
            </View>
          </View>
          <View style={styles.counters}>
            <CounterChip
              label="步数"
              value={steps.toLocaleString()}
              target={8000}
              color="#FF9500"
            />
            <CounterChip
              label="活动"
              value={`${activeMin}`}
              target={30}
              color="#FF2D55"
            />
            <CounterChip
              label="饮水"
              value={`${waterTotal}ml`}
              target={2000}
              color="#007AFF"
            />
            <CounterChip
              label="补剂"
              value={`${suppCount}`}
              color="#AF52DE"
            />
            <CounterChip
              label="压力"
              value={stress ?? '--'}
              color="#FF9500"
            />
          </View>
        </View>

        {/* Weather / AQI */}
        {(weather || aqi) && (
          <View style={styles.weatherBar}>
            {weather && (
              <View style={styles.weatherItem}>
                <Ionicons name="partly-sunny-outline" size={18} color="#FF9500" />
                <Text style={styles.weatherText}>
                  {weather.temperature ?? '--'}°C {weather.description || ''}
                </Text>
              </View>
            )}
            {aqi && (
              <View style={styles.weatherItem}>
                <Ionicons name="leaf-outline" size={18} color={getAqiColor(aqi.aqi)} />
                <Text style={styles.weatherText}>
                  AQI {aqi.aqi ?? '--'} PM2.5 {aqi.pm25 ?? '--'}
                </Text>
              </View>
            )}
          </View>
        )}

        {/* Sleep Card */}
        <InfoCard
          title="睡眠分析"
          icon="moon"
          iconColor="#5856D6"
          items={[
            { label: '总时长', value: sleep ? `${Number(sleep).toFixed(1)}h` : '--' },
            { label: 'HRV', value: hrv ? `${hrv}ms` : '--' },
            { label: '深睡', value: garmin?.deep_sleep_hours ? `${Number(garmin.deep_sleep_hours).toFixed(1)}h` : '--' },
          ]}
        />

        {/* Diet Card */}
        <InfoCard
          title="今日饮食"
          icon="restaurant"
          iconColor="#FF9500"
          items={
            Array.isArray(dietRecords) && dietRecords.length > 0
              ? dietRecords.slice(0, 3).map((d: any) => ({
                  label: d.meal_type || '餐食',
                  value: d.total_calories ? `${d.total_calories}kcal` : d.description?.slice(0, 20) || '--',
                }))
              : [{ label: '暂无', value: '今天还没有饮食记录' }]
          }
        />

        {/* Rhinitis Card */}
        {checkin && (checkin.nasal_wash_count > 0 || checkin.sneeze_count > 0) && (
          <InfoCard
            title="鼻炎追踪"
            icon="water"
            iconColor="#30B0C7"
            items={[
              { label: '洗鼻', value: `${checkin.nasal_wash_count ?? 0}次` },
              { label: '喷嚏', value: `${checkin.sneeze_count ?? 0}次` },
              { label: '用药', value: checkin.mometasone ? '已用莫米松' : '未用药' },
            ]}
          />
        )}

        <View style={{ height: 24 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function InfoCard({
  title,
  icon,
  iconColor,
  items,
}: {
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  iconColor: string;
  items: { label: string; value: string }[];
}) {
  return (
    <View style={styles.infoCard}>
      <View style={styles.infoHeader}>
        <Ionicons name={icon} size={18} color={iconColor} />
        <Text style={styles.infoTitle}>{title}</Text>
      </View>
      <View style={styles.infoItems}>
        {items.map((item, i) => (
          <View key={i} style={styles.infoItem}>
            <Text style={styles.infoLabel}>{item.label}</Text>
            <Text style={styles.infoValue}>{item.value}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const getAqiColor = (v: number | null) =>
  !v ? '#8E8E93' : v <= 50 ? '#34C759' : v <= 100 ? '#FF9500' : '#FF3B30';

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FDFBF7' },
  scroll: { flex: 1 },
  content: { padding: 16 },
  heroCard: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
    marginBottom: 12,
  },
  heroTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  vitalsGrid: {
    flex: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  counters: {
    flexDirection: 'row',
    marginTop: 16,
    paddingTop: 14,
    borderTopWidth: 0.5,
    borderTopColor: '#E5E5EA',
  },
  weatherBar: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
    gap: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  weatherItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  weatherText: { fontSize: 13, color: '#3C3C43' },
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  infoHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  infoTitle: { fontSize: 15, fontWeight: '600', color: '#1C1C1E' },
  infoItems: { flexDirection: 'row', gap: 12 },
  infoItem: {
    flex: 1,
    backgroundColor: '#F9F9FB',
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
  },
  infoLabel: { fontSize: 11, color: '#8E8E93', marginBottom: 4 },
  infoValue: { fontSize: 15, fontWeight: '600', color: '#1C1C1E' },
});
