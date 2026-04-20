import React, { useCallback, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, RefreshControl, TouchableOpacity, TextStyle, TextInput, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDashboardData } from '@/services/dashboard';
import api from '@/services/api';
import { useRouter } from 'expo-router';
import { useLatestGarmin } from '@/hooks/useDashboardData';
import { recordWater, deleteWater } from '@/services/records';
import VitalsGrid from '@/components/dashboard/VitalsGrid';
import ActivityRingBar from '@/components/dashboard/ActivityRingBar';
import SupplementCheckin from '@/components/dashboard/SupplementCheckin';
import RhinitisCard from '@/components/dashboard/RhinitisCard';
import StrengthCard from '@/components/dashboard/StrengthCard';
import WorkoutWeekCard from '@/components/dashboard/WorkoutWeekCard';
import TrendMiniCharts from '@/components/dashboard/TrendMiniCharts';
import SectionHeader from '@/components/design-system/SectionHeader';
import HealthCard from '@/components/design-system/HealthCard';
import { colors, spacing, radii, shadows } from '@/constants/theme';

const mealTypeMap: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };

export default function RecordScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data, refetch, isRefetching } = useQuery({ queryKey: ['dashboard'], queryFn: fetchDashboardData, staleTime: 60_000 });
  const garmin = useLatestGarmin(data);
  const [bodyDietTab, setBodyDietTab] = useState<'diet' | 'body'>('diet');
  const [weightInput, setWeightInput] = useState('');
  const [bpSysInput, setBpSysInput] = useState('');
  const [bpDiaInput, setBpDiaInput] = useState('');
  const [undo, setUndo] = useState<{ label: string; action: () => Promise<void> } | null>(null);

  const sleepH = garmin?.total_sleep_duration ? garmin.total_sleep_duration / 60 : null;
  const deepH = garmin?.deep_sleep_duration ? garmin.deep_sleep_duration / 60 : null;
  const steps = garmin?.steps ?? 0;
  const activeMin = garmin?.active_minutes ?? 0;
  const calories = garmin?.active_calories ?? 0;
  const exerciseToday = Array.isArray(data?.exerciseToday) ? data.exerciseToday : [];
  const medications = Array.isArray(data?.medicationToday)
    ? data.medicationToday.filter((m: any) => m.category !== '保健品' && !/益生菌|AKK/i.test(m.name))
    : data?.medicationToday;
  const weightStats = data?.weightStats;
  const bpStats = data?.bloodPressureStats;

  // Diet data
  const dietData = data?.dietRecords;
  const meals = dietData?.meals ?? (Array.isArray(dietData) ? dietData : []);
  const totalCal = dietData?.total_calories ?? meals.reduce((s: number, m: any) => s + (m.calories || 0), 0);
  const totalProtein = dietData?.total_protein ?? 0;
  const totalCarbs = dietData?.total_carbs ?? 0;
  const totalFat = dietData?.total_fat ?? 0;

  // Water — API returns {total_amount, target_amount, records: [...]}
  const waterData = data?.waterRecords;
  const waterTotal = waterData?.total_amount ?? (Array.isArray(waterData) ? waterData.reduce((s: number, r: any) => s + (r.amount || 0), 0) : 0);
  const waterTarget = waterData?.target_amount ?? 2000;

  const showUndo = (label: string, action: () => Promise<void>) => { setUndo({ label, action }); setTimeout(() => setUndo(null), 5000); };
  const doWater = useCallback(async (amt: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try { const rec = await recordWater(amt); qc.invalidateQueries({ queryKey: ['dashboard'] }); showUndo(`${amt}ml`, async () => { await deleteWater(rec.id); qc.invalidateQueries({ queryKey: ['dashboard'] }); }); } catch { Alert.alert('记录失败', '饮水记录保存失败，请重试'); }
  }, [qc]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />} showsVerticalScrollIndicator={false}>
        <Text style={txt.title}>健康记录</Text>

        {/* Quick navigation */}
        <View style={styles.quickNav}>
          <QuickNavBtn icon="moon-outline" label="睡眠" color={colors.purple} onPress={() => router.push('/sleep' as any)} />
          <QuickNavBtn icon="barbell-outline" label="运动" color={colors.pink} onPress={() => router.push('/workout-list' as any)} />
          <QuickNavBtn icon="nutrition-outline" label="饮食" color={colors.orange} onPress={() => router.push('/diet' as any)} />
          <QuickNavBtn icon="flag-outline" label="目标" color={colors.green} onPress={() => router.push('/goals' as any)} />
        </View>

        {/* 1. Vitals */}
        <VitalsGrid sleep={sleepH} deepSleep={deepH} sleepScore={garmin?.sleep_score} heartRate={garmin?.resting_heart_rate} hrv={garmin?.hrv} bodyBattery={garmin?.body_battery_most_charged ?? garmin?.body_battery_current} batteryMax={garmin?.body_battery_most_charged} />

        {/* 2. Activity */}
        <ActivityRingBar steps={steps} activeMin={activeMin} calories={calories} />

        {/* 3. Workout Week */}
        <WorkoutWeekCard />

        {/* 4. Rhinitis */}
        <RhinitisCard checkin={data?.checkin} onUpdate={refetch} />

        {/* 5. Strength */}
        <StrengthCard exerciseToday={exerciseToday} onUpdate={refetch} />

        {/* 6. Supplements */}
        <SupplementCheckin supplements={data?.supplements || []} onToggle={refetch} />

        {/* 7. Body + Diet (tabbed) */}
        <View style={styles.tabCard}>
          <View style={styles.tabHeader}>
            <TouchableOpacity style={[styles.tabBtn, bodyDietTab === 'diet' && styles.tabBtnActive]} onPress={() => setBodyDietTab('diet')}>
              <Text style={[txt.tabText, bodyDietTab === 'diet' && txt.tabTextActive]}>饮食营养</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.tabBtn, bodyDietTab === 'body' && styles.tabBtnActive]} onPress={() => setBodyDietTab('body')}>
              <Text style={[txt.tabText, bodyDietTab === 'body' && txt.tabTextActive]}>身体数据</Text>
            </TouchableOpacity>
          </View>

          {bodyDietTab === 'diet' ? (
            <View style={styles.tabContent}>
              {/* Nutrition summary */}
              <View style={styles.nutritionRow}>
                <NutritionCircle label="热量" value={`${totalCal.toFixed(0)}`} unit="kcal" color="#FF6723" />
                <NutritionCircle label="蛋白质" value={`${totalProtein.toFixed(1)}`} unit="g" color="#FF375F" />
                <NutritionCircle label="碳水" value={`${totalCarbs.toFixed(1)}`} unit="g" color="#FF9F0A" />
                <NutritionCircle label="脂肪" value={`${totalFat.toFixed(1)}`} unit="g" color="#BF5AF2" />
              </View>
              {/* Meal list */}
              {meals.length > 0 ? meals.map((m: any, i: number) => (
                <View key={i} style={styles.mealRow}>
                  <View style={styles.mealDot} />
                  <View style={{ flex: 1 }}>
                    <Text style={txt.mealType}>{mealTypeMap[m.meal_type] || m.meal_type || '餐食'}</Text>
                    <Text style={txt.mealFood} numberOfLines={1}>{m.food_items || '--'}</Text>
                  </View>
                  <Text style={txt.mealCal}>{m.calories ? `${m.calories.toFixed(1)}kcal` : ''}</Text>
                </View>
              )) : (
                <Text style={txt.empty}>今天还没有饮食记录</Text>
              )}
            </View>
          ) : (
            <View style={styles.tabContent}>
              <View style={styles.bodyGrid}>
                {weightStats?.current_weight != null && (
                  <View style={styles.bodyCell}>
                    <Text style={txt.bodyVal}>{weightStats.current_weight.toFixed(1)}</Text>
                    <Text style={txt.bodyUnit}>kg 体重</Text>
                    {weightStats.weight_change_7d != null && (
                      <Text style={[txt.bodyChange, { color: weightStats.weight_change_7d <= 0 ? '#30D158' : '#FF453A' }]}>
                        7天 {weightStats.weight_change_7d > 0 ? '+' : ''}{weightStats.weight_change_7d}
                      </Text>
                    )}
                  </View>
                )}
                {bpStats?.average_systolic != null && (
                  <View style={styles.bodyCell}>
                    <Text style={txt.bodyVal}>{Math.round(bpStats.average_systolic)}/{Math.round(bpStats.average_diastolic)}</Text>
                    <Text style={txt.bodyUnit}>mmHg 血压</Text>
                  </View>
                )}
                {weightStats?.current_weight != null && (
                  <View style={styles.bodyCell}>
                    <Text style={txt.bodyVal}>{(weightStats.current_weight / ((data?.profile?.height || 175) / 100) ** 2).toFixed(1)}</Text>
                    <Text style={txt.bodyUnit}>BMI</Text>
                  </View>
                )}
              </View>
              {!weightStats?.current_weight && !bpStats?.average_systolic && (
                <Text style={txt.empty}>暂无身体数据</Text>
              )}
              {/* Quick record */}
              <View style={styles.quickInputRow}>
                <TextInput style={styles.quickInput} placeholder="体重 kg" placeholderTextColor={colors.labelTertiary}
                  keyboardType="decimal-pad" value={weightInput} onChangeText={setWeightInput} />
                <TouchableOpacity style={styles.quickSaveBtn} onPress={async () => {
                  const w = parseFloat(weightInput);
                  if (!w || w < 30 || w > 200) { Alert.alert('请输入有效体重'); return; }
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                  try {
                    await api.post('/weight/records', { weight: w, record_date: new Date().toISOString().split('T')[0] });
                    setWeightInput(''); qc.invalidateQueries({ queryKey: ['dashboard'] });
                  } catch { Alert.alert('记录失败'); }
                }} activeOpacity={0.7}><Text style={txt.quickSaveTxt}>记录</Text></TouchableOpacity>
              </View>
              <View style={styles.quickInputRow}>
                <TextInput style={[styles.quickInput, { flex: 1 }]} placeholder="收缩压" placeholderTextColor={colors.labelTertiary}
                  keyboardType="number-pad" value={bpSysInput} onChangeText={setBpSysInput} />
                <Text style={txt.bpSlash}>/</Text>
                <TextInput style={[styles.quickInput, { flex: 1 }]} placeholder="舒张压" placeholderTextColor={colors.labelTertiary}
                  keyboardType="number-pad" value={bpDiaInput} onChangeText={setBpDiaInput} />
                <TouchableOpacity style={styles.quickSaveBtn} onPress={async () => {
                  const sys = parseInt(bpSysInput), dia = parseInt(bpDiaInput);
                  if (!sys || !dia || sys < 60 || sys > 250 || dia < 30 || dia > 150) { Alert.alert('请输入有效血压'); return; }
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                  try {
                    await api.post('/blood-pressure/records', { systolic: sys, diastolic: dia, record_date: new Date().toISOString().split('T')[0] });
                    setBpSysInput(''); setBpDiaInput(''); qc.invalidateQueries({ queryKey: ['dashboard'] });
                  } catch { Alert.alert('记录失败'); }
                }} activeOpacity={0.7}><Text style={txt.quickSaveTxt}>记录</Text></TouchableOpacity>
              </View>
            </View>
          )}
        </View>

        {/* 8. Medication */}
        {Array.isArray(medications) && medications.length > 0 && (
          <HealthCard title="用药状态" icon="medical-outline" iconColor={colors.brand} iconBg={colors.brandLight}>
            <View style={styles.medRow}>
              {medications.map((m: any) => (
                <TouchableOpacity key={m.medication_id}
                  style={[styles.medChip, m.taken_count > 0 && { backgroundColor: '#E8FAF0' }]}
                  onPress={async () => {
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    try {
                      await api.post('/medication/log', { medication_id: m.medication_id, action: m.taken_count > 0 ? 'undo' : 'take' });
                      qc.invalidateQueries({ queryKey: ['dashboard'] });
                    } catch { Alert.alert('操作失败', '用药记录更新失败'); }
                  }}
                  activeOpacity={0.7}
                >
                  <Ionicons name={m.taken_count > 0 ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={m.taken_count > 0 ? '#30D158' : colors.labelTertiary} />
                  <Text style={txt.medName} numberOfLines={1}>{m.name}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </HealthCard>
        )}

        {/* 9. Trends */}
        <TrendMiniCharts garminDays={Array.isArray(data?.garminDaily) ? data.garminDaily : []} />

        {/* 10. Water (low priority) */}
        <HealthCard title="饮水" icon="water-outline" iconColor="#64D2FF" iconBg="#E6F5FF"
          rightAccessory={<Text style={txt.waterTotal}>{waterTotal}/{waterTarget}ml</Text>}>
          <View style={styles.waterBtnRow}>
            {[200, 300, 500].map(a => (
              <TouchableOpacity key={a} style={styles.waterBtn} onPress={() => doWater(a)} activeOpacity={0.7}>
                <Text style={txt.waterBtnText}>+{a}ml</Text>
              </TouchableOpacity>
            ))}
          </View>
        </HealthCard>

        <View style={{ height: 100 }} />
      </ScrollView>

      {undo && (
        <View style={styles.undoBar}>
          <Text style={txt.undoText}>已记录 {undo.label}</Text>
          <TouchableOpacity onPress={async () => { await undo.action(); setUndo(null); }}>
            <Text style={txt.undoBtn}>撤销</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

function QuickNavBtn({ icon, label, color, onPress }: { icon: any; label: string; color: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.quickNavBtn} onPress={onPress} activeOpacity={0.7}>
      <View style={[styles.quickNavIcon, { backgroundColor: `${color}18` }]}>
        <Ionicons name={icon} size={18} color={color} />
      </View>
      <Text style={txt.quickNavLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

function NutritionCircle({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  return (
    <View style={styles.nutriItem}>
      <View style={[styles.nutriDot, { backgroundColor: `${color}20` }]}>
        <Text style={[txt.nutriVal, { color }]}>{value}</Text>
      </View>
      <Text style={txt.nutriUnit}>{unit}</Text>
      <Text style={txt.nutriLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  content: { padding: spacing.lg },

  // Quick navigation
  quickNav: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg },
  quickNavBtn: { flex: 1, alignItems: 'center', gap: 6, backgroundColor: colors.bgCard, borderRadius: radii.md, paddingVertical: 12, ...shadows.subtle },
  quickNavIcon: { width: 32, height: 32, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },

  // Tabbed card (body + diet)
  tabCard: {
    backgroundColor: colors.bgCard, borderRadius: radii.xl,
    marginBottom: spacing.md, overflow: 'hidden', ...shadows.subtle,
  },
  tabHeader: {
    flexDirection: 'row', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  tabBtn: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabBtnActive: { borderBottomWidth: 2, borderBottomColor: colors.brand },
  tabContent: { padding: spacing.lg },

  // Nutrition
  nutritionRow: { flexDirection: 'row', justifyContent: 'space-around', marginBottom: spacing.md },
  nutriItem: { alignItems: 'center', gap: 3 },
  nutriDot: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },

  // Meals
  mealRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  mealDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: colors.brand },

  // Body grid
  bodyGrid: { flexDirection: 'row', gap: spacing.md, justifyContent: 'center' },
  bodyCell: { alignItems: 'center', flex: 1, backgroundColor: colors.bgPrimary, borderRadius: radii.md, padding: spacing.md },

  // Medication
  medRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  medChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radii.full, backgroundColor: colors.bgPrimary },

  // Water
  waterBtnRow: { flexDirection: 'row', gap: spacing.sm },
  waterBtn: { flex: 1, backgroundColor: colors.bgPrimary, borderRadius: radii.md, paddingVertical: 10, alignItems: 'center' },
  quickInputRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: spacing.md },
  quickInput: { flex: 2, backgroundColor: colors.bgPrimary, borderRadius: radii.md, paddingHorizontal: 12, paddingVertical: 8, fontSize: 14, color: colors.labelPrimary },
  quickSaveBtn: { backgroundColor: colors.brand, borderRadius: radii.md, paddingHorizontal: 14, paddingVertical: 8 },

  // Undo
  undoBar: {
    position: 'absolute', bottom: 100, left: spacing.lg, right: spacing.lg,
    backgroundColor: '#1C1C1E', borderRadius: radii.full,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 10, ...shadows.heavy,
  },
});

const txt = {
  title: { fontSize: 28, fontWeight: '700', color: colors.labelPrimary, marginBottom: spacing.md } as TextStyle,
  quickNavLabel: { fontSize: 11, fontWeight: '500', color: colors.labelSecondary } as TextStyle,
  tabText: { fontSize: 14, fontWeight: '500', color: colors.labelTertiary } as TextStyle,
  tabTextActive: { color: colors.brand, fontWeight: '600' } as TextStyle,
  nutriVal: { fontSize: 16, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  nutriUnit: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  nutriLabel: { fontSize: 11, fontWeight: '500', color: colors.labelTertiary } as TextStyle,
  mealType: { fontSize: 12, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  mealFood: { fontSize: 13, color: colors.labelSecondary, marginTop: 1 } as TextStyle,
  mealCal: { fontSize: 13, fontWeight: '600', color: '#FF6723', fontVariant: ['tabular-nums'] as const } as TextStyle,
  bodyVal: { fontSize: 22, fontWeight: '800', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  bodyUnit: { fontSize: 11, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  bodyChange: { fontSize: 11, fontWeight: '500', marginTop: 2 } as TextStyle,
  medName: { fontSize: 13, color: colors.labelPrimary, maxWidth: 80 } as TextStyle,
  waterTotal: { fontSize: 14, fontWeight: '700', color: '#64D2FF' } as TextStyle,
  waterBtnText: { fontSize: 14, fontWeight: '600', color: colors.brand } as TextStyle,
  quickSaveTxt: { fontSize: 13, fontWeight: '600', color: '#fff' } as TextStyle,
  bpSlash: { fontSize: 16, color: colors.labelTertiary } as TextStyle,
  empty: { fontSize: 13, color: colors.labelTertiary, textAlign: 'center', paddingVertical: 16 } as TextStyle,
  undoText: { fontSize: 14, color: '#fff' } as TextStyle,
  undoBtn: { fontSize: 14, fontWeight: '600', color: colors.brand } as TextStyle,
};
