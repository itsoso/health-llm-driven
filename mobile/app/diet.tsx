import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, Alert, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import ReanimatedSwipeable from 'react-native-gesture-handler/ReanimatedSwipeable';
import { useDailyDiet } from '../hooks/useDiet';
import { useDietEstimate, type EstimateSource } from '../hooks/useDietEstimate';
import { createDietRecord, updateDietRecord, deleteDietRecord, getFrequentFoods, type DietRecord, type DietRecordCreate, type FrequentFood } from '../services/diet';
import { computeDietTotals, isPendingNutrition } from '../utils/dietTotals';
import * as ImagePicker from 'expo-image-picker';
import MealForm from '../components/diet/MealForm';
import DietFAB from '../components/diet/DietFAB';
import FrequentFoodsRow from '../components/diet/FrequentFoodsRow';
import { useToast } from '../hooks/useToast';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import { createDietAgentContext, pushChatWithContext } from '../utils/agentContext';
import { todayStr, offsetDate } from '../utils/dietDate';

const MEAL_LABEL: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };

function guessMealType(): DietRecordCreate['meal_type'] {
  const h = new Date().getHours();
  if (h < 10) return 'breakfast';
  if (h < 14) return 'lunch';
  if (h < 20) return 'dinner';
  return 'snack';
}

export default function DietScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ capture?: string }>();
  const captureConsumedRef = useRef(false);
  const qc = useQueryClient();
  const toast = useToast();
  const [date, setDate] = useState(todayStr());
  const { data: daily, refetch, isRefetching } = useDailyDiet(date);
  const { estimate, pendingIds, failedIds } = useDietEstimate();
  // 记住每条记录的估算来源, 让「点重试」用同一来源 (photo/voice/text) 重跑.
  const sourceMapRef = useRef<Map<number, EstimateSource>>(new Map());
  const reconciledRef = useRef<Set<number>>(new Set());
  const frequentQuery = useQuery({
    queryKey: ['diet', 'frequent'],
    queryFn: () => getFrequentFoods(8, 30),
    staleTime: 10 * 60 * 1000,
  });
  const [showForm, setShowForm] = useState(false);
  const [formDefaults, setFormDefaults] = useState<Partial<DietRecordCreate>>({});
  const [editingRecord, setEditingRecord] = useState<DietRecord | null>(null);

  // 记录立刻入库 (无营养) → 关闭输入 → toast → 后台估算回填. 不阻塞用户.
  // 快速记录 (文字/语音/拍照 FAB) 语义永远是「我刚吃的」= 现在, 因此在 submit 时
  // 现取 todayStr(), 绝不用浏览器回翻过的 selector `date` (数据完整性: 曾把午餐记到 2 天前).
  const recordThenEstimate = useCallback(async (
    description: string,
    mealType: DietRecordCreate['meal_type'],
    source: EstimateSource,
  ) => {
    let created: DietRecord;
    try {
      created = await createDietRecord({ record_date: todayStr(), meal_type: mealType, food_items: description });
    } catch {
      toast.show('记录失败,请重试', 'error');
      return;
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    sourceMapRef.current.set(created.id, source);
    qc.invalidateQueries({ queryKey: ['diet'] });
    toast.show('已记录 · 营养后台估算中', 'success');
    estimate(created.id, source);
  }, [estimate, qc, toast]);

  const retryEstimate = useCallback((record: DietRecord) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const source = sourceMapRef.current.get(record.id)
      ?? { kind: 'text', description: record.food_items } as EstimateSource;
    estimate(record.id, source);
  }, [estimate]);

  const handleSave = useCallback(async (record: DietRecordCreate) => {
    try {
      if (editingRecord) {
        await updateDietRecord(editingRecord.id, record);
      } else {
        await createDietRecord(record);
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setShowForm(false);
      setEditingRecord(null);
      setFormDefaults({});
      qc.invalidateQueries({ queryKey: ['diet'] });
    } catch {
      Alert.alert(editingRecord ? '更新失败' : '保存失败', '请稍后再试');
    }
  }, [qc, editingRecord]);

  // P1-b: 点「常吃」chip → 直接入库(用历史营养素中位数)+ 5s undo. 失败要让用户感知 (rule#1).
  // 「常吃」也是「我现在又吃了这个」= 现在, 同 recordThenEstimate 在 submit 时现取 todayStr(),
  // 不用回翻过的 selector `date` (数据完整性 belt-and-suspenders).
  const handlePickFrequent = useCallback(async (f: FrequentFood) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    let created: DietRecord;
    try {
      created = await createDietRecord({
        record_date: todayStr(),
        meal_type: f.meal_type,
        food_items: f.food_items,
        calories: f.calories ?? undefined,
        protein: f.protein ?? undefined,
        carbs: f.carbs ?? undefined,
        fat: f.fat ?? undefined,
      });
    } catch {
      toast.show('记录失败,请重试', 'error');
      return;
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    qc.invalidateQueries({ queryKey: ['diet'] });
    toast.showUndoable(
      `已记录「${f.food_items.slice(0, 14)}」`,
      async () => {
        try {
          await deleteDietRecord(created.id);
          qc.invalidateQueries({ queryKey: ['diet'] });
        } catch {
          toast.show('撤销失败,请重试', 'error');
        }
      },
      5000,
    );
  }, [qc, toast]);

  const handleEdit = useCallback((r: DietRecord) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setEditingRecord(r);
    setFormDefaults({});
    setShowForm(true);
  }, []);

  const handleDelete = useCallback((r: DietRecord) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const preview = (r.food_items || '').slice(0, 30);
    Alert.alert(
      '删除饮食记录',
      `确定删除 ${MEAL_LABEL[r.meal_type] || r.meal_type}: ${preview} 吗?`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteDietRecord(r.id);
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
              qc.invalidateQueries({ queryKey: ['diet'] });
            } catch {
              Alert.alert('删除失败', '请稍后再试');
            }
          },
        },
      ],
    );
  }, [qc]);

  const handleText = useCallback(() => {
    Alert.prompt('文字记录', '描述你吃的食物（如：鸡胸肉200g + 糙米饭一碗）', (text) => {
      const raw = text?.trim();
      if (!raw) return;
      recordThenEstimate(raw, guessMealType(), { kind: 'text', description: raw });
    });
  }, [recordThenEstimate]);

  const handleVoiceText = useCallback(() => {
    Alert.prompt('语音记录饮食', '说完后保留转写文本，例如: "晚饭吃了鸡胸肉和一碗米饭"', (text) => {
      const raw = text?.trim();
      if (!raw) return;
      recordThenEstimate(raw, guessMealType(), { kind: 'voice', rawText: raw });
    });
  }, [recordThenEstimate]);

  const handlePhoto = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相机权限', '请在设置中开启相机权限');
        return;
      }
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ['images'],
        quality: 0.8,
        base64: true,
      });
      if (result.canceled || !result.assets[0]?.base64) return;
      // 拍完立刻入库占位 (来源=照片), 营养后台识别回填. 图片本身仍走识别, 只是不阻塞.
      await recordThenEstimate('照片记录的一餐', guessMealType(), { kind: 'photo', imageBase64: result.assets[0].base64 });
    } catch {
      Alert.alert('拍照失败', '请稍后重试');
    }
  }, [recordThenEstimate]);

  useEffect(() => {
    if (params.capture !== 'photo' || captureConsumedRef.current) return;
    captureConsumedRef.current = true;
    handlePhoto();
  }, [handlePhoto, params.capture]);

  // 进入/刷新时对账: 任何 calories==null 的当日记录 (含上次中途退出卡住的),
  // 若本会话尚未跑过 → 用已知来源或文字兜底自动重试一次. 不让一餐永远空着.
  useEffect(() => {
    const meals = daily?.meals;
    if (!meals || date !== todayStr()) return;
    for (const r of meals) {
      if (!isPendingNutrition(r)) { reconciledRef.current.delete(r.id); continue; }
      if (pendingIds.has(r.id) || failedIds.has(r.id) || reconciledRef.current.has(r.id)) continue;
      reconciledRef.current.add(r.id);
      const source = sourceMapRef.current.get(r.id)
        ?? { kind: 'text', description: r.food_items } as EstimateSource;
      estimate(r.id, source);
    }
  }, [daily?.meals, date, estimate, pendingIds, failedIds]);

  const meals = daily?.meals ?? [];
  const totals = useMemo(() => computeDietTotals(meals), [meals]);
  const isToday = date === todayStr();
  const dateLabel = isToday ? '今天' : new Date(date).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', weekday: 'short' });

  const handleChatDiet = useCallback(() => {
    if (!daily) return;
    pushChatWithContext(router, {
      prompt: `${dateLabel}饮食结构怎么样? 蛋白质够吗? 帮我给出下一餐调整建议。`,
      context: createDietAgentContext(daily),
      badge: `基于${dateLabel}饮食 ${daily.meals_count ?? daily.meals?.length ?? 0} 餐`,
    });
  }, [daily, dateLabel, router]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={C.ink1} />
        </TouchableOpacity>
        <Text style={txt.title}>饮食记录</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Date selector */}
      <View style={styles.dateRow}>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, -1))}>
          <Ionicons name="chevron-back-circle-outline" size={28} color={C.ink2} />
        </TouchableOpacity>
        <Text style={txt.dateText}>{dateLabel}</Text>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, 1))} disabled={isToday}>
          <Ionicons name="chevron-forward-circle-outline" size={28} color={isToday ? C.ink4 : C.ink2} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={C.green500} />}
        showsVerticalScrollIndicator={false}>

        {/* Summary — pending 记录不计入, 单独标注 (不假装成功) */}
        {daily && (
          <>
            <View style={styles.summaryCard}>
              <NutriPill label="热量" value={`${totals.calories.toFixed(0)}`} unit="kcal" color="#FF6723" />
              <NutriPill label="蛋白质" value={`${totals.protein.toFixed(1)}`} unit="g" color="#FF375F" />
              <NutriPill label="碳水" value={`${totals.carbs.toFixed(1)}`} unit="g" color="#FF9F0A" />
              <NutriPill label="脂肪" value={`${totals.fat.toFixed(1)}`} unit="g" color="#BF5AF2" />
            </View>
            {totals.pendingMeals > 0 && (
              <Text style={txt.pendingNote}>含 {totals.pendingMeals} 项营养估算中,暂未计入总量</Text>
            )}
          </>
        )}
        {daily && (
          <TouchableOpacity
            style={[styles.agentLink, { borderColor: C.line }]}
            onPress={handleChatDiet}
            activeOpacity={0.75}
            accessibilityRole="button"
            accessibilityLabel="跟 Agent 详细聊今日饮食"
          >
            <Ionicons name="chatbubble-ellipses-outline" size={16} color={C.green500} />
            <Text style={[txt.agentLinkText, { color: C.green500 }]}>跟 Agent 详细聊{dateLabel}饮食</Text>
            <Ionicons name="chevron-forward" size={15} color={C.green500} style={{ marginLeft: 'auto' }} />
          </TouchableOpacity>
        )}

        {/* 常吃一键复用 (P1-b): 不在编辑/表单态时显示 */}
        {!showForm && (
          <FrequentFoodsRow
            foods={frequentQuery.data ?? []}
            onPick={handlePickFrequent}
          />
        )}

        {/* Meal form */}
        {showForm && (
          <MealForm date={date}
            initialRecord={editingRecord || undefined}
            initialMealType={formDefaults.meal_type}
            onSubmit={handleSave}
            onCancel={() => { setShowForm(false); setEditingRecord(null); setFormDefaults({}); }}
            initialDescription={formDefaults.food_items}
            initialCalories={formDefaults.calories}
            initialProtein={formDefaults.protein}
            initialCarbs={formDefaults.carbs}
            initialFat={formDefaults.fat} />
        )}

        {/* Meal records — 左滑暴露 编辑 + 删除 */}
        {meals.length > 0 ? (
          meals.map((r) => {
            const pending = isPendingNutrition(r);
            const isEstimating = pendingIds.has(r.id);
            const failed = failedIds.has(r.id);
            return (
              <ReanimatedSwipeable
                key={r.id}
                friction={2}
                rightThreshold={40}
                renderRightActions={() => (
                  <View style={styles.swipeActions}>
                    <TouchableOpacity
                      style={[styles.swipeBtn, { backgroundColor: C.green500 }]}
                      onPress={() => handleEdit(r)}
                      activeOpacity={0.85}
                      accessibilityLabel="编辑"
                    >
                      <Ionicons name="pencil" size={18} color="#fff" />
                      <Text style={txt.swipeText}>编辑</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.swipeBtn, { backgroundColor: revaSemantic.risk.fg }]}
                      onPress={() => handleDelete(r)}
                      activeOpacity={0.85}
                      accessibilityLabel="删除"
                    >
                      <Ionicons name="trash" size={18} color="#fff" />
                      <Text style={txt.swipeText}>删除</Text>
                    </TouchableOpacity>
                  </View>
                )}
              >
                <View style={styles.mealRow}>
                  <View style={styles.mealDot} />
                  <View style={{ flex: 1 }}>
                    <Text style={txt.mealType}>{MEAL_LABEL[r.meal_type] || r.meal_type}</Text>
                    <Text style={txt.mealFood} numberOfLines={2}>{r.food_items}</Text>
                  </View>
                  {pending ? (
                    failed && !isEstimating ? (
                      <TouchableOpacity
                        style={styles.retryBtn}
                        onPress={() => retryEstimate(r)}
                        activeOpacity={0.7}
                        accessibilityRole="button"
                        accessibilityLabel="营养估算失败,点击重试"
                      >
                        <Ionicons name="refresh" size={13} color={revaSemantic.risk.fg} />
                        <Text style={[txt.retryText, { color: revaSemantic.risk.fg }]}>估算失败 · 重试</Text>
                      </TouchableOpacity>
                    ) : (
                      <View style={styles.pendingChip}>
                        <ActivityIndicator size="small" color={C.ink3} />
                        <Text style={txt.pendingChipText}>估算中…</Text>
                      </View>
                    )
                  ) : (
                    <Text style={txt.mealCal}>{r.calories != null ? `${Math.round(r.calories)}kcal` : ''}</Text>
                  )}
                </View>
              </ReanimatedSwipeable>
            );
          })
        ) : (
          <Text style={txt.empty}>{date === todayStr() ? '今天还没有饮食记录' : '当日无记录'}</Text>
        )}

        <View style={{ height: 140 }} />
      </ScrollView>

      <DietFAB onPhoto={handlePhoto} onText={handleText} onVoice={handleVoiceText} />
    </SafeAreaView>
  );
}

function NutriPill({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  return (
    <View style={styles.nutriItem}>
      <Text style={[txt.nutriVal, { color }]}>{value}</Text>
      <Text style={txt.nutriUnit}>{unit}</Text>
      <Text style={txt.nutriLabel}>{label}</Text>
    </View>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / r-lg 18 / 数字等宽 mono / light-first 软阴影。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2 },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  dateRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, paddingVertical: revaSpacing.s2 },
  content: { padding: revaSpacing.s4 },
  summaryCard: {
    flexDirection: 'row', justifyContent: 'space-around',
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    padding: revaSpacing.s4, marginBottom: revaSpacing.s4, ...revaShadows.sm,
  },
  nutriItem: { alignItems: 'center', gap: 2 },
  mealRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: C.surface, borderRadius: revaRadii.md,
    padding: revaSpacing.s4, marginBottom: revaSpacing.s2, ...revaShadows.sm,
  },
  mealDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: C.green500 },
  pendingChip: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  retryBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: revaRadii.pill, backgroundColor: C.paper,
  },
  swipeActions: {
    flexDirection: 'row', alignItems: 'stretch',
    marginBottom: revaSpacing.s2,
  },
  swipeBtn: {
    width: 76,
    alignItems: 'center', justifyContent: 'center',
    gap: 4,
    marginLeft: 6,
    borderRadius: revaRadii.md,
  },
  agentLink: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3,
    marginTop: -revaSpacing.s2,
    marginBottom: revaSpacing.s4,
  },
});

// 数字/计数/指标值/单位/日期走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1, textAlign: 'center' } as TextStyle,
  dateText: { fontFamily: revaFonts.mono, fontSize: 16, fontWeight: '600', color: C.ink1 } as TextStyle,
  nutriVal: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  nutriUnit: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink2 } as TextStyle,
  nutriLabel: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3 } as TextStyle,
  pendingNote: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, textAlign: 'center', marginTop: -revaSpacing.s3, marginBottom: revaSpacing.s4 } as TextStyle,
  mealType: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.ink1 } as TextStyle,
  mealFood: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, marginTop: 2 } as TextStyle,
  mealCal: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '600', color: '#FF6723' } as TextStyle,
  pendingChipText: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3 } as TextStyle,
  retryText: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '600' } as TextStyle,
  swipeText: { fontFamily: revaFonts.sans, fontSize: 11, color: '#fff', fontWeight: '600' } as TextStyle,
  agentLinkText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600' } as TextStyle,
  empty: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3, textAlign: 'center', paddingVertical: 30 } as TextStyle,
};
