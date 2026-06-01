import React, { useCallback, useMemo, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, RefreshControl, TouchableOpacity, TextStyle, TextInput, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDashboardData } from '../../services/dashboard';
import api from '../../services/api';
import { useRouter } from 'expo-router';
import { emitClientEvent } from '../../services/clientEvents';
import {
  recordWater,
  deleteWater,
  getFrequentSupplements,
  getFrequentWater,
  supplementApi,
  type FrequentSupplement,
  type FrequentWater,
} from '../../services/records';
import FrequentChipsRow from '../../components/records/FrequentChipsRow';
import { filterMedicationRecordItems } from '../../services/medicationFilters';
import { invalidateRecordMutation, queryKeys } from '../../applib/queryKeys';
import {
  createBodyMetricsAgentContext,
  createHydrationAgentContext,
  createSupplementAgentContext,
  pushChatWithContext,
} from '../../utils/agentContext';
import SupplementCheckin from '../../components/dashboard/SupplementCheckin';
import RhinitisCard from '../../components/dashboard/RhinitisCard';
import StrengthCard from '../../components/dashboard/StrengthCard';
import SymptomCard from '../../components/dashboard/SymptomCard';
import HealthCard from '../../components/design-system/HealthCard';
import AgentFeedbackLink from '../../components/agent/AgentFeedbackLink';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

const mealTypeMap: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };

type QuickRecordEntry = {
  key: string;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  hint: string;
  color: string;
  priority: number;
  onPress: () => void;
};

type RecordGapState = {
  isMorning: boolean;
  isMealWindow: boolean;
  isPreWorkoutWindow: boolean;
  missingBody: boolean;
  missingMeal: boolean;
};

export default function RecordScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const { data, refetch, isRefetching } = useQuery({ queryKey: queryKeys.dashboard, queryFn: fetchDashboardData, staleTime: 60_000 });
  const [bodyDietTab, setBodyDietTab] = useState<'diet' | 'body'>('diet');
  const [weightInput, setWeightInput] = useState('');
  const [bpSysInput, setBpSysInput] = useState('');
  const [bpDiaInput, setBpDiaInput] = useState('');
  const [undo, setUndo] = useState<{ label: string; action: () => Promise<void> } | null>(null);

  const exerciseToday = Array.isArray(data?.exerciseToday) ? data.exerciseToday : [];
  const medications = filterMedicationRecordItems(data?.medicationToday);
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
  const waterRecords = useMemo(
    () => waterData?.records ?? (Array.isArray(waterData) ? waterData : []),
    [waterData],
  );
  const recordGaps = useMemo<RecordGapState>(() => {
    const hour = new Date().getHours();
    return {
      isMorning: hour >= 5 && hour <= 10,
      isMealWindow: (hour >= 11 && hour <= 14) || (hour >= 17 && hour <= 20),
      isPreWorkoutWindow: hour >= 16 && hour <= 21,
      missingBody: !weightStats?.current_weight && !bpStats?.average_systolic,
      missingMeal: meals.length === 0,
    };
  }, [bpStats?.average_systolic, meals.length, weightStats?.current_weight]);

  const today = new Date().toISOString().split('T')[0];
  const highFrequencyRecords = useMemo<QuickRecordEntry[]>(() => {
    const entries: QuickRecordEntry[] = [
      {
        key: 'diet',
        icon: 'nutrition-outline',
        label: '饮食',
        hint: recordGaps.missingMeal ? '今天还没记餐' : '补充餐食细节',
        color: c.orange,
        priority: (recordGaps.isMealWindow && recordGaps.missingMeal) ? 95 : recordGaps.missingMeal ? 62 : 30,
        onPress: () => router.push('/diet' as any),
      },
      {
        key: 'body',
        icon: 'body-outline',
        label: '体重腰围',
        hint: recordGaps.missingBody ? '缺少基础指标' : '更新体重血压',
        color: c.teal,
        priority: (recordGaps.isMorning && recordGaps.missingBody) ? 100 : recordGaps.missingBody ? 70 : 28,
        onPress: () => router.push('/body-measurements' as any),
      },
      {
        key: 'voice',
        icon: 'mic-outline',
        label: '声音笔记',
        hint: '不想打字就说',
        color: c.blue,
        priority: 24,
        onPress: () => router.push('/voice-chat?intent=journal' as any),
      },
      {
        key: 'preworkout',
        icon: 'flash-outline',
        label: '跑前准备',
        hint: '跑前确认状态',
        color: c.green,
        priority: recordGaps.isPreWorkoutWindow ? 72 : 18,
        onPress: () => router.push('/voice-chat?intent=preworkout&workout_type=running' as any),
      },
    ];

    return entries.sort((a, b) => b.priority - a.priority);
  }, [c.blue, c.green, c.orange, c.teal, recordGaps, router]);
  const recommendedRecord = highFrequencyRecords[0];
  const shouldShowRecommendedRecord = recommendedRecord?.priority >= 60;

  const showUndo = (label: string, action: () => Promise<void>) => { setUndo({ label, action }); setTimeout(() => setUndo(null), 5000); };
  const doWater = useCallback(async (amt: number, drinkType = '水') => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try { const rec = await recordWater(amt, drinkType); await invalidateRecordMutation(qc); showUndo(`${amt}ml`, async () => { await deleteWater(rec.id); await invalidateRecordMutation(qc); }); } catch { Alert.alert('记录失败', '饮水记录保存失败，请重试'); }
  }, [qc]);

  // 常用补剂 / 常用饮水 —— 一键记录 (后端按历史频次聚合)
  const frequentSupplementsQuery = useQuery({
    queryKey: ['supplements', 'frequent'],
    queryFn: () => getFrequentSupplements(8, 30),
    staleTime: 10 * 60 * 1000,
  });
  const frequentWaterQuery = useQuery({
    queryKey: ['water', 'frequent'],
    queryFn: () => getFrequentWater(6, 30),
    staleTime: 10 * 60 * 1000,
  });
  const frequentSupplements: FrequentSupplement[] = Array.isArray(frequentSupplementsQuery.data) ? frequentSupplementsQuery.data : [];
  const frequentWater: FrequentWater[] = Array.isArray(frequentWaterQuery.data) ? frequentWaterQuery.data : [];

  const doFrequentSupplement = useCallback(async (s: FrequentSupplement) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await supplementApi.batchCheckin(today, s.supplement_id, true);
      await invalidateRecordMutation(qc);
      showUndo(`已打卡 ${s.name}`, async () => {
        await supplementApi.batchCheckin(today, s.supplement_id, false);
        await invalidateRecordMutation(qc);
      });
    } catch { Alert.alert('记录失败', '补剂打卡失败，请重试'); }
  }, [qc, today]);

  const handleChatHydration = useCallback(() => {
    pushChatWithContext(router, {
      prompt: '请基于我今天的饮水记录, 复盘是否达标, 安排接下来几个小时怎么补水, 并结合运动、睡眠和补剂提醒注意事项。',
      context: createHydrationAgentContext({
        date: today,
        totalMl: waterTotal,
        targetMl: waterTarget,
        records: waterRecords,
      }),
      badge: `今日饮水 ${waterTotal}/${waterTarget}ml`,
    });
  }, [router, today, waterRecords, waterTarget, waterTotal]);

  const handleChatSupplements = useCallback(() => {
    const supplements = data?.supplements || [];
    const total = supplements.length;
    const taken = supplements.filter((s: any) => s.record?.taken || s.is_taken || s.checked).length;
    pushChatWithContext(router, {
      prompt: '请基于我今天的补剂打卡情况, 复盘执行情况, 提醒漏服/冲突风险, 并给出今晚和明天的补剂安排。最后请问我需要补充哪些体感反馈。',
      context: createSupplementAgentContext({
        date: today,
        supplements,
      }),
      badge: `今日补剂 ${taken}/${total}`,
    });
  }, [data?.supplements, router, today]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />} showsVerticalScrollIndicator={false}>
        <Text style={txt.title}>健康记录</Text>

        {/* Quick navigation */}
        <View style={styles.recordEntryPanel}>
          <View style={styles.entryHeader}>
            <View>
              <Text style={txt.sectionEyebrow}>高频记录</Text>
              <Text style={txt.sectionHint}>先录入会改变今日建议的数据</Text>
            </View>
          </View>
          {shouldShowRecommendedRecord && recommendedRecord && (
            <RecordFocusCard
              entry={recommendedRecord}
              gaps={recordGaps}
              onPress={recommendedRecord.onPress}
              onAskAgent={() => {
                pushChatWithContext(router, {
                  prompt: `请帮我判断现在最该补充哪条健康记录，并说明为什么优先「${recommendedRecord.label}」。`,
                  badge: '记录优先级',
                  context: {
                    from: 'record/focus',
                    recommended_record: recommendedRecord.key,
                    missing_body: recordGaps.missingBody,
                    missing_meal: recordGaps.missingMeal,
                    water_total_ml: waterTotal,
                    water_target_ml: waterTarget,
                  },
                });
              }}
            />
          )}
          <View style={styles.captureModeRow}>
            <CaptureModeBtn
              icon="mic-outline"
              label="说一句"
              hint="语音记录"
              color={c.blue}
              onPress={() => router.push('/voice-chat?intent=journal' as any)}
              accessibilityLabel="说一句记录健康状态"
            />
            <CaptureModeBtn
              icon="camera-outline"
              label="拍一下"
              hint="餐食照片"
              color={c.orange}
              onPress={() => router.push('/diet?capture=photo' as any)}
              accessibilityLabel="拍一下记录饮食"
            />
            <CaptureModeBtn
              icon="hand-left-outline"
              label="点一下"
              hint="记录症状"
              color={c.green}
              onPress={() => router.push('/symptom-record' as any)}
              accessibilityLabel="点一下记录症状"
            />
          </View>
          <View style={styles.quickNav} testID="high-frequency-records">
            {highFrequencyRecords.map((entry) => (
              <QuickNavBtn
                key={entry.key}
                icon={entry.icon}
                label={entry.label}
                hint={entry.hint}
                color={entry.color}
                onPress={entry.onPress}
              />
            ))}
          </View>
          <Text style={txt.moreTitle}>更多记录</Text>
          <View style={styles.moreRecordRow} testID="more-records">
            <MoreRecordBtn icon="document-text-outline" label="化验记录" color={c.brand} onPress={() => router.push('/medical-exams' as any)} />
            <MoreRecordBtn icon="git-branch-outline" label="基因" color={c.teal} onPress={() => router.push('/genetic-report' as any)} />
            <MoreRecordBtn icon="moon-outline" label="睡眠" color={c.purple} onPress={() => router.push('/sleep' as any)} />
            <MoreRecordBtn icon="barbell-outline" label="运动" color={c.pink} onPress={() => router.push('/workout-list' as any)} />
            <MoreRecordBtn icon="cloud-upload-outline" label="导入档案" color={c.purple} onPress={() => router.push('/import' as any)} />
            <MoreRecordBtn icon="flag-outline" label="目标" color={c.green} onPress={() => router.push('/goals' as any)} />
          </View>
        </View>

        {/* 看板回显已迁至首页 — 此页只保留录入相关模块 (2026-05-28) */}

        {/* 4. Rhinitis */}
        <RhinitisCard checkin={data?.checkin} medications={medications} onUpdate={refetch} />

        {/* 4.5 Symptoms — 偶发症状通用录入 */}
        <SymptomCard />

        {/* 4.6 Live Run Coach — 跑步动态指导 */}
        <TouchableOpacity
          style={styles.runCard}
          onPress={() => router.push('/live-run' as any)}
          activeOpacity={0.7}
        >
          <View style={styles.runCardContent}>
            <Text style={styles.runCardTitle}>跑步指导</Text>
            <Text style={styles.runCardSubtitle}>GPS 实时配速 · 规则引擎 · 跑后复盘</Text>
            <View style={{ width: 32, height: 32, backgroundColor: c.tintGreen, borderRadius: 16, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="play" size={18} color={c.green} />
            </View>
          </View>
        </TouchableOpacity>

        {/* 5. Strength */}
        <StrengthCard exerciseToday={exerciseToday} onUpdate={refetch} />

        {/* 6. Supplements */}
        {frequentSupplements.length > 0 && (
          <FrequentChipsRow
            label="常吃补剂 · 点一下打卡"
            icon="medkit-outline"
            chips={frequentSupplements.map(s => ({
              key: String(s.supplement_id),
              title: s.name,
              meta: s.dosage ?? undefined,
            }))}
            onPick={(i) => doFrequentSupplement(frequentSupplements[i])}
          />
        )}
        <SupplementCheckin supplements={data?.supplements || []} onToggle={refetch} onChat={handleChatSupplements} />

        {/* 7. Body + Diet (tabbed) */}
        <View style={styles.tabCard}>
          <View style={styles.tabHeader}>
            <TouchableOpacity style={[styles.tabBtn, bodyDietTab === 'diet' && styles.tabBtnActive]} onPress={() => setBodyDietTab('diet')} accessibilityRole="tab" accessibilityState={{ selected: bodyDietTab === 'diet' }} accessibilityLabel="饮食营养">
              <Text style={[txt.tabText, bodyDietTab === 'diet' && txt.tabTextActive]}>饮食营养</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.tabBtn, bodyDietTab === 'body' && styles.tabBtnActive]} onPress={() => setBodyDietTab('body')} accessibilityRole="tab" accessibilityState={{ selected: bodyDietTab === 'body' }} accessibilityLabel="身体数据">
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
              <AgentFeedbackLink
                label="跟 Agent 看身体和血压趋势"
                accessibilityLabel="跟 Agent 看身体和血压趋势"
                prompt="请基于我的体重、腰围和血压记录, 复盘近期趋势和风险, 并给出今天饮食、饮水、运动和睡眠上的调整建议。"
                context={createBodyMetricsAgentContext({
                  date: today,
                  latestWeightKg: weightStats?.current_weight ?? null,
                  latestWeightDate: weightStats?.latest_date ?? null,
                  latestWaistCm: weightStats?.current_waist ?? null,
                  latestWaistDate: weightStats?.latest_waist_date ?? null,
                  weightStats,
                  bloodPressureStats: bpStats,
                })}
                badge="身体数据和血压"
                style={styles.bodyAgentLink}
              />
              {/* Quick record */}
              <View style={styles.quickInputRow}>
                <TextInput style={styles.quickInput} placeholder="体重 kg" placeholderTextColor={c.labelTertiary}
                  keyboardType="decimal-pad" value={weightInput} onChangeText={setWeightInput} />
                <TouchableOpacity style={styles.quickSaveBtn} onPress={async () => {
                  const w = parseFloat(weightInput);
                  if (!w || w < 30 || w > 200) { Alert.alert('请输入有效体重'); return; }
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                  try {
                    await api.post('/weight/records', { weight: w, record_date: new Date().toISOString().split('T')[0] });
                    emitClientEvent('quick_record_logged', { kind: 'weight' }); // Phase 0.4
                    setWeightInput(''); await invalidateRecordMutation(qc);
                  } catch { Alert.alert('记录失败'); }
                }} activeOpacity={0.7}><Text style={txt.quickSaveTxt}>记录</Text></TouchableOpacity>
              </View>
              <View style={styles.quickInputRow}>
                <TextInput style={[styles.quickInput, { flex: 1 }]} placeholder="收缩压" placeholderTextColor={c.labelTertiary}
                  keyboardType="number-pad" value={bpSysInput} onChangeText={setBpSysInput} />
                <Text style={txt.bpSlash}>/</Text>
                <TextInput style={[styles.quickInput, { flex: 1 }]} placeholder="舒张压" placeholderTextColor={c.labelTertiary}
                  keyboardType="number-pad" value={bpDiaInput} onChangeText={setBpDiaInput} />
                <TouchableOpacity style={styles.quickSaveBtn} onPress={async () => {
                  const sys = parseInt(bpSysInput), dia = parseInt(bpDiaInput);
                  if (!sys || !dia || sys < 60 || sys > 250 || dia < 30 || dia > 150) { Alert.alert('请输入有效血压'); return; }
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                  try {
                    await api.post('/blood-pressure/records', { systolic: sys, diastolic: dia, record_date: new Date().toISOString().split('T')[0] });
                    emitClientEvent('quick_record_logged', { kind: 'bp' }); // Phase 0.4
                    setBpSysInput(''); setBpDiaInput(''); await invalidateRecordMutation(qc);
                  } catch { Alert.alert('记录失败'); }
                }} activeOpacity={0.7}><Text style={txt.quickSaveTxt}>记录</Text></TouchableOpacity>
              </View>
            </View>
          )}
        </View>

        {/* 8. Medication */}
        {Array.isArray(medications) && medications.length > 0 && (
          <HealthCard title="用药状态" icon="medical-outline" iconColor={c.brand} iconBg={c.brandLight}>
            <View style={styles.medList}>
              {medications.map((m: any) => {
                const lastToday: string | undefined = m.last_taken_time;
                const lastOverall: string | undefined = m.last_taken_time_overall;
                const lastOverallDate: string | undefined = m.last_taken_date_overall;
                const done = m.taken_count >= (m.total_count || 1);
                return (
                  <TouchableOpacity key={m.medication_id}
                    style={[styles.medItem, done && { backgroundColor: c.tintGreen }]}
                    onPress={async () => {
                      Haptics.impactAsync(done ? Haptics.ImpactFeedbackStyle.Medium : Haptics.ImpactFeedbackStyle.Light);
                      const now = new Date();
                      const hh = String(now.getHours()).padStart(2, '0');
                      const mm = String(now.getMinutes()).padStart(2, '0');
                      try {
                        const res = await api.post('/medication/logs', {
                          medication_id: m.medication_id,
                          taken_time: `${hh}:${mm}`,
                          status: 'taken',
                        });
                        emitClientEvent('quick_record_logged', { kind: 'medication' }); // Phase 0.4
                        await invalidateRecordMutation(qc);
                        // done 时点击 = '加记一次' (鼻喷雾常需多喷); 否则 = 首次打卡.
                        // 区分 toast 文案让用户知道这次点击生效了 (之前 done 状态视觉不变, 用户疑惑'无效').
                        const msg = done
                          ? `再记一次 ${m.name} ${hh}:${mm}`
                          : `已记录 ${m.name} ${hh}:${mm}`;
                        showUndo(msg, async () => {
                          try { await api.delete(`/medication/logs/${res.data.id}`); await invalidateRecordMutation(qc); } catch (e) {
                            if (__DEV__) console.warn('[record] undo medication log delete failed:', e);
                          }
                        });
                      } catch { Alert.alert('记录失败'); }
                    }}
                    activeOpacity={0.7}
                  >
                    <View style={styles.medLeft}>
                      <Ionicons name={done ? 'checkmark-circle' : 'medical'} size={18} color={done ? '#30D158' : c.brand} />
                      <View style={{ flex: 1 }}>
                        <Text style={txt.medItemName} numberOfLines={1}>{m.name}</Text>
                        <Text style={txt.medItemMeta}>
                          {lastToday ? `今日 ${m.taken_count}/${m.total_count || 1} · 上次 ${lastToday}` :
                           lastOverall ? `上次 ${lastOverallDate} ${lastOverall}` :
                           '今日未记录'}
                        </Text>
                      </View>
                    </View>
                    <Ionicons name="add-circle" size={22} color={c.brand} />
                  </TouchableOpacity>
                );
              })}
            </View>
          </HealthCard>
        )}

        {/* 9. Trends */}
        {/* 周趋势已合并到 VitalsGrid 每卡底部 sparkline, 原 TrendMiniCharts 删除避免信息重复 */}

        {/* 10. Water (low priority) */}
        <HealthCard title="饮水" icon="water-outline" iconColor={c.blue} iconBg={c.tintBlue}
          rightAccessory={<Text style={txt.waterTotal}>{waterTotal}/{waterTarget}ml</Text>}>
          <FrequentChipsRow
            label="常喝 · 点一下直接记录"
            icon="water-outline"
            chips={frequentWater.map(w => ({
              key: `${w.amount_ml}-${w.drink_type ?? ''}`,
              title: `${w.amount_ml}ml${w.drink_type && w.drink_type !== '水' ? ` ${w.drink_type}` : ''}`,
            }))}
            onPick={(i) => { const w = frequentWater[i]; doWater(w.amount_ml, w.drink_type ?? '水'); }}
          />
          <View style={styles.waterBtnRow}>
            {[200, 300, 500].map(a => (
              <TouchableOpacity key={a} style={styles.waterBtn} onPress={() => doWater(a)} activeOpacity={0.7}>
                <Text style={txt.waterBtnText}>+{a}ml</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity
            onPress={handleChatHydration}
            style={styles.agentLink}
            activeOpacity={0.75}
            accessibilityRole="button"
            accessibilityLabel="跟 Agent 调整今日饮水"
          >
            <Ionicons name="chatbubble-ellipses-outline" size={15} color={c.brand} />
            <Text style={txt.agentLink}>跟 Agent 调整今日饮水</Text>
            <Ionicons name="chevron-forward" size={14} color={c.brand} />
          </TouchableOpacity>
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

function getRecordFocusReason(entry: QuickRecordEntry, gaps: RecordGapState) {
  if (entry.key === 'body') {
    if (gaps.isMorning && gaps.missingBody) return '早晨体重和血压会直接影响今天的饮食、运动和风险判断。';
    if (gaps.missingBody) return '缺少基础身体指标，先补齐会提高今日建议的可信度。';
    return '更新体重、腰围或血压，让趋势更连续。';
  }
  if (entry.key === 'diet') {
    if (gaps.isMealWindow && gaps.missingMeal) return '当前餐窗还没记录，先补餐食会影响热量和蛋白目标。';
    if (gaps.missingMeal) return '今天还没有餐食记录，先补一餐让 Agent 有依据。';
    return '补充餐食细节，帮助复盘今天的营养目标。';
  }
  if (entry.key === 'preworkout') return '跑前先确认配速、心率上限和血氧风险。';
  return '用一句话补充体感、异常或今天的执行情况。';
}

function RecordFocusCard({
  entry,
  gaps,
  onPress,
  onAskAgent,
}: {
  entry: QuickRecordEntry;
  gaps: RecordGapState;
  onPress: () => void;
  onAskAgent: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <View style={[styles.recordFocusCard, { borderColor: `${entry.color}55`, backgroundColor: `${entry.color}0F` }]}>
      <View style={styles.recordFocusTop}>
        <View style={[styles.recordFocusIcon, { backgroundColor: `${entry.color}1F` }]}>
          <Ionicons name={entry.icon} size={22} color={entry.color} />
        </View>
        <View style={styles.recordFocusBody}>
          <Text style={[txt.recordFocusKicker, { color: entry.color }]}>现在优先</Text>
          <Text style={txt.recordFocusTitle}>{entry.label}</Text>
          <Text style={txt.recordFocusHint}>{getRecordFocusReason(entry, gaps)}</Text>
        </View>
      </View>
      <View style={styles.recordFocusActions}>
        <TouchableOpacity
          style={[styles.recordFocusPrimary, { backgroundColor: entry.color }]}
          onPress={onPress}
          activeOpacity={0.76}
          accessibilityRole="button"
          accessibilityLabel={`开始记录${entry.label}`}
        >
          <Ionicons name="play" size={15} color="#fff" />
          <Text style={txt.recordFocusPrimaryText}>开始记录</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.recordFocusSecondary, { borderColor: `${entry.color}45` }]}
          onPress={onAskAgent}
          activeOpacity={0.76}
          accessibilityRole="button"
          accessibilityLabel={`询问 Agent 为什么优先记录${entry.label}`}
        >
          <Ionicons name="chatbubble-ellipses-outline" size={15} color={entry.color} />
          <Text style={[txt.recordFocusSecondaryText, { color: entry.color }]}>问 Agent</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function CaptureModeBtn({
  icon,
  label,
  hint,
  color,
  accessibilityLabel,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  hint: string;
  color: string;
  accessibilityLabel: string;
  onPress: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <TouchableOpacity
      style={[styles.captureModeBtn, { borderColor: c.separator }]}
      onPress={onPress}
      activeOpacity={0.72}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
    >
      <View style={[styles.captureModeIcon, { backgroundColor: `${color}18` }]}>
        <Ionicons name={icon} size={17} color={color} />
      </View>
      <Text style={txt.captureModeLabel}>{label}</Text>
      <Text style={txt.captureModeHint}>{hint}</Text>
    </TouchableOpacity>
  );
}

function QuickNavBtn({
  icon,
  label,
  hint,
  color,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  hint: string;
  color: string;
  onPress: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <TouchableOpacity style={styles.quickNavBtn} onPress={onPress} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel={label}>
      <View style={[styles.quickNavIcon, { backgroundColor: `${color}18` }]}>
        <Ionicons name={icon} size={18} color={color} />
      </View>
      <View style={styles.quickNavCopy}>
        <Text style={txt.quickNavLabel}>{label}</Text>
        <Text style={txt.quickNavHint} numberOfLines={1}>{hint}</Text>
      </View>
      <Ionicons name="chevron-forward" size={14} color={c.labelQuaternary} />
    </TouchableOpacity>
  );
}

function MoreRecordBtn({ icon, label, color, onPress }: { icon: any; label: string; color: string; onPress: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <TouchableOpacity
      style={[styles.moreRecordBtn, { borderColor: c.separator }]}
      onPress={onPress}
      activeOpacity={0.72}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Ionicons name={icon} size={16} color={color} />
      <Text style={txt.moreRecordLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

function NutritionCircle({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  // 数值显示压缩: ≥100 显示整数 (避免 "125.0" 在圆里换行)
  const display = (() => {
    const n = parseFloat(value);
    if (Number.isFinite(n) && n >= 100) return String(Math.round(n));
    // 尾零去掉: "75.0" → "75"
    return value.replace(/\.0$/, '');
  })();
  return (
    <View style={styles.nutriItem}>
      <View style={[styles.nutriDot, { backgroundColor: `${color}20` }]}>
        <Text
          style={[txt.nutriVal, { color }]}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.7}
        >{display}</Text>
      </View>
      <Text style={txt.nutriUnit}>{unit}</Text>
      <Text style={txt.nutriLabel}>{label}</Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  content: { padding: spacing.lg, paddingBottom: 118 },
  promptStack: { marginBottom: spacing.md },

  // Quick navigation
  recordEntryPanel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.xl,
    padding: spacing.md,
    gap: spacing.md,
    marginBottom: spacing.lg,
    ...shadows.subtle,
  },
  entryHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  quickNav: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  quickNavBtn: {
    width: '48.5%',
    minHeight: 72,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    backgroundColor: c.bgPrimary,
    borderRadius: radii.md,
    paddingVertical: 11,
    paddingHorizontal: 10,
  },
  quickNavIcon: { width: 32, height: 32, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  quickNavCopy: { flex: 1, minWidth: 0 },
  recordFocusCard: {
    borderWidth: 1,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  recordFocusTop: { flexDirection: 'row', gap: spacing.sm },
  recordFocusIcon: {
    width: 44,
    height: 44,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recordFocusBody: { flex: 1, minWidth: 0 },
  recordFocusActions: { flexDirection: 'row', gap: spacing.sm },
  recordFocusPrimary: {
    flex: 1.3,
    minHeight: 42,
    borderRadius: radii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  recordFocusSecondary: {
    flex: 1,
    minHeight: 42,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: c.bgCard,
  },
  moreRecordRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  captureModeRow: { flexDirection: 'row', gap: spacing.sm },
  captureModeBtn: {
    flex: 1,
    minHeight: 78,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: c.bgPrimary,
    paddingHorizontal: 6,
  },
  captureModeIcon: {
    width: 30,
    height: 30,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  moreRecordBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.full,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },

  // Tabbed card (body + diet)
  tabCard: {
    backgroundColor: c.bgCard, borderRadius: radii.xl,
    marginBottom: spacing.md, overflow: 'hidden', ...shadows.subtle,
  },
  tabHeader: {
    flexDirection: 'row', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.separator,
  },
  tabBtn: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabBtnActive: { borderBottomWidth: 2, borderBottomColor: c.brand },
  tabContent: { padding: spacing.lg },

  // Nutrition
  nutritionRow: { flexDirection: 'row', justifyContent: 'space-around', marginBottom: spacing.md },
  nutriItem: { alignItems: 'center', gap: 3 },
  nutriDot: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },

  // Meals
  mealRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.separator,
  },
  mealDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: c.brand },

  // Body grid
  bodyGrid: { flexDirection: 'row', gap: spacing.md, justifyContent: 'center' },
  bodyCell: { alignItems: 'center', flex: 1, backgroundColor: c.bgPrimary, borderRadius: radii.md, padding: spacing.md },
  bodyAgentLink: { marginTop: spacing.md },

  // Medication
  medRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  medChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radii.full, backgroundColor: c.bgPrimary },
  medList: { gap: 6 },
  medItem: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: c.bgPrimary, borderRadius: radii.md,
  },
  medLeft: { flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 },

  // Water
  waterBtnRow: { flexDirection: 'row', gap: spacing.sm },
  waterBtn: { flex: 1, backgroundColor: c.bgPrimary, borderRadius: radii.md, paddingVertical: 10, alignItems: 'center' },
  agentLink: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginTop: spacing.md, paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator,
  },
  quickInputRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: spacing.md },
  quickInput: { flex: 2, backgroundColor: c.bgPrimary, borderRadius: radii.md, paddingHorizontal: 12, paddingVertical: 8, fontSize: 14, color: c.labelPrimary },
  quickSaveBtn: { backgroundColor: c.brand, borderRadius: radii.md, paddingHorizontal: 14, paddingVertical: 8 },

  // Undo
  undoBar: {
    position: 'absolute', bottom: 100, left: spacing.lg, right: spacing.lg,
    backgroundColor: '#1C1C1E', borderRadius: radii.full,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 10, ...shadows.heavy,
  },
  runCard: {
    backgroundColor: c.bgCard, borderRadius: radii.md,
    padding: spacing.md, ...shadows.subtle,
  },
  runCardContent: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
  },
  runCardTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  runCardSubtitle: { fontSize: 12, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  });
}

function createTxt(c: ColorPalette) {
  return {
  title: { fontSize: 28, fontWeight: '700', color: c.labelPrimary, marginBottom: spacing.md } as TextStyle,
  captureModeLabel: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  captureModeHint: { fontSize: 10, color: c.labelTertiary, fontWeight: '600' } as TextStyle,
  quickNavLabel: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  quickNavHint: { fontSize: 10, color: c.labelTertiary, fontWeight: '600', marginTop: 2 } as TextStyle,
  recordFocusKicker: { fontSize: 12, fontWeight: '800' } as TextStyle,
  recordFocusTitle: { fontSize: 19, fontWeight: '900', color: c.labelPrimary, marginTop: 2 } as TextStyle,
  recordFocusHint: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 4 } as TextStyle,
  recordFocusPrimaryText: { fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
  recordFocusSecondaryText: { fontSize: 13, fontWeight: '800' } as TextStyle,
  sectionEyebrow: { fontSize: 16, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  sectionHint: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  moreTitle: { fontSize: 12, fontWeight: '700', color: c.labelTertiary } as TextStyle,
  moreRecordLabel: { fontSize: 12, fontWeight: '600', color: c.labelSecondary } as TextStyle,
  tabText: { fontSize: 14, fontWeight: '500', color: c.labelTertiary } as TextStyle,
  tabTextActive: { color: c.brand, fontWeight: '600' } as TextStyle,
  nutriVal: { fontSize: 16, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  nutriUnit: { fontSize: 10, color: c.labelSecondary } as TextStyle,
  nutriLabel: { fontSize: 11, fontWeight: '500', color: c.labelTertiary } as TextStyle,
  mealType: { fontSize: 12, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  mealFood: { fontSize: 13, color: c.labelSecondary, marginTop: 1 } as TextStyle,
  mealCal: { fontSize: 13, fontWeight: '600', color: '#FF6723', fontVariant: ['tabular-nums'] as const } as TextStyle,
  bodyVal: { fontSize: 22, fontWeight: '800', color: c.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  bodyUnit: { fontSize: 11, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  bodyChange: { fontSize: 11, fontWeight: '500', marginTop: 2 } as TextStyle,
  medName: { fontSize: 13, color: c.labelPrimary, maxWidth: 80 } as TextStyle,
  medItemName: { fontSize: 14, fontWeight: '500', color: c.labelPrimary } as TextStyle,
  medItemMeta: { fontSize: 11, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  waterTotal: { fontSize: 14, fontWeight: '700', color: '#64D2FF' } as TextStyle,
  waterBtnText: { fontSize: 14, fontWeight: '600', color: c.brand } as TextStyle,
  agentLink: { fontSize: 13, color: c.brand, fontWeight: '600', flex: 1 } as TextStyle,
  quickSaveTxt: { fontSize: 13, fontWeight: '600', color: '#fff' } as TextStyle,
  bpSlash: { fontSize: 16, color: c.labelTertiary } as TextStyle,
  empty: { fontSize: 13, color: c.labelTertiary, textAlign: 'center', paddingVertical: 16 } as TextStyle,
  undoText: { fontSize: 14, color: '#fff' } as TextStyle,
  undoBtn: { fontSize: 14, fontWeight: '600', color: c.brand } as TextStyle,
  };
}
