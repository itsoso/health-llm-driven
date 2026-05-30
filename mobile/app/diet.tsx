import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import ReanimatedSwipeable from 'react-native-gesture-handler/ReanimatedSwipeable';
import { useDailyDiet } from '../hooks/useDiet';
import { createDietRecord, updateDietRecord, deleteDietRecord, estimateNutrition, recognizeFood, getFrequentFoods, type DietRecord, type DietRecordCreate, type FrequentFood } from '../services/diet';
import * as ImagePicker from 'expo-image-picker';
import MealForm from '../components/diet/MealForm';
import DietFAB from '../components/diet/DietFAB';
import FrequentFoodsRow from '../components/diet/FrequentFoodsRow';
import { useToast } from '../hooks/useToast';
import { spacing, radii, shadows } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { createDietAgentContext, pushChatWithContext } from '../utils/agentContext';

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function offsetDate(base: string, offset: number) {
  const d = new Date(base);
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const MEAL_LABEL: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };

export default function DietScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const params = useLocalSearchParams<{ capture?: string }>();
  const captureConsumedRef = useRef(false);
  const qc = useQueryClient();
  const toast = useToast();
  const [date, setDate] = useState(todayStr());
  const { data: daily, refetch, isRefetching } = useDailyDiet(date);
  const frequentQuery = useQuery({
    queryKey: ['diet', 'frequent'],
    queryFn: () => getFrequentFoods(8, 30),
    staleTime: 10 * 60 * 1000,
  });
  const [showForm, setShowForm] = useState(false);
  const [, setEstimating] = useState(false);
  const [formDefaults, setFormDefaults] = useState<Partial<DietRecordCreate>>({});
  const [editingRecord, setEditingRecord] = useState<DietRecord | null>(null);

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
  const handlePickFrequent = useCallback(async (f: FrequentFood) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    let created: DietRecord;
    try {
      created = await createDietRecord({
        record_date: date,
        meal_type: f.meal_type,
        food_items: f.food_items,
        calories: f.calories ?? undefined,
        protein: f.protein ?? undefined,
        carbs: f.carbs ?? undefined,
        fat: f.fat ?? undefined,
      });
    } catch {
      toast.show('记录失败，请重试', 'error');
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
          toast.show('撤销失败，请重试', 'error');
        }
      },
      5000,
    );
  }, [date, qc, toast]);

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

  const handleText = useCallback(async () => {
    Alert.prompt('文字估算', '描述你吃的食物（如：鸡胸肉200g + 糙米饭一碗）', async (text) => {
      if (!text?.trim()) return;
      setEstimating(true);
      try {
        const est = await estimateNutrition(text);
        if (est.success && est.foods.length > 0) {
          setFormDefaults({
            food_items: est.foods.map(f => f.name).join('、') || text,
            calories: est.total_calories ?? undefined,
            protein: est.total_protein ?? undefined,
            carbs: est.total_carbs ?? undefined,
            fat: est.total_fat ?? undefined,
          });
          setShowForm(true);
        } else {
          setFormDefaults({ food_items: text });
          setShowForm(true);
        }
      } catch {
        Alert.alert('估算失败');
      } finally {
        setEstimating(false);
      }
    });
  }, []);

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

      setEstimating(true);
      const recognition = await recognizeFood(result.assets[0].base64);
      if (recognition && (recognition.foods?.length > 0 || recognition.meal_description)) {
        const foodDesc = recognition.meal_description
          || recognition.foods?.map(f => f.name).join('、')
          || '';
        setFormDefaults({
          food_items: foodDesc,
          calories: recognition.total_calories ?? undefined,
          protein: recognition.total_protein ?? undefined,
          carbs: recognition.total_carbs ?? undefined,
          fat: recognition.total_fat ?? undefined,
        });
        setShowForm(true);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else {
        Alert.alert('未识别到食物', '请拍摄更清晰的食物照片');
      }
    } catch {
      Alert.alert('识别失败', '请稍后重试');
    } finally {
      setEstimating(false);
    }
  }, []);

  useEffect(() => {
    if (params.capture !== 'photo' || captureConsumedRef.current) return;
    captureConsumedRef.current = true;
    handlePhoto();
  }, [handlePhoto, params.capture]);

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
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>饮食记录</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Date selector */}
      <View style={styles.dateRow}>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, -1))}>
          <Ionicons name="chevron-back-circle-outline" size={28} color={c.labelSecondary} />
        </TouchableOpacity>
        <Text style={txt.dateText}>{dateLabel}</Text>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, 1))} disabled={isToday}>
          <Ionicons name="chevron-forward-circle-outline" size={28} color={isToday ? c.labelQuaternary : c.labelSecondary} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />}
        showsVerticalScrollIndicator={false}>

        {/* Summary */}
        {daily && (
          <View style={styles.summaryCard}>
            <NutriPill label="热量" value={`${(daily.total_calories ?? 0).toFixed(0)}`} unit="kcal" color="#FF6723" />
            <NutriPill label="蛋白质" value={`${(daily.total_protein ?? 0).toFixed(1)}`} unit="g" color="#FF375F" />
            <NutriPill label="碳水" value={`${(daily.total_carbs ?? 0).toFixed(1)}`} unit="g" color="#FF9F0A" />
            <NutriPill label="脂肪" value={`${(daily.total_fat ?? 0).toFixed(1)}`} unit="g" color="#BF5AF2" />
          </View>
        )}
        {daily && (
          <TouchableOpacity
            style={[styles.agentLink, { borderColor: c.separator }]}
            onPress={handleChatDiet}
            activeOpacity={0.75}
            accessibilityRole="button"
            accessibilityLabel="跟 Agent 详细聊今日饮食"
          >
            <Ionicons name="chatbubble-ellipses-outline" size={16} color={c.brand} />
            <Text style={[txt.agentLinkText, { color: c.brand }]}>跟 Agent 详细聊{dateLabel}饮食</Text>
            <Ionicons name="chevron-forward" size={15} color={c.brand} style={{ marginLeft: 'auto' }} />
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
            onSubmit={handleSave}
            onCancel={() => { setShowForm(false); setEditingRecord(null); setFormDefaults({}); }}
            initialDescription={formDefaults.food_items}
            initialCalories={formDefaults.calories}
            initialProtein={formDefaults.protein}
            initialCarbs={formDefaults.carbs}
            initialFat={formDefaults.fat} />
        )}

        {/* Meal records — 左滑暴露 编辑 + 删除 */}
        {daily?.meals && daily.meals.length > 0 ? (
          daily.meals.map((r) => (
            <ReanimatedSwipeable
              key={r.id}
              friction={2}
              rightThreshold={40}
              renderRightActions={() => (
                <View style={styles.swipeActions}>
                  <TouchableOpacity
                    style={[styles.swipeBtn, { backgroundColor: c.brand }]}
                    onPress={() => handleEdit(r)}
                    activeOpacity={0.85}
                    accessibilityLabel="编辑"
                  >
                    <Ionicons name="pencil" size={18} color="#fff" />
                    <Text style={txt.swipeText}>编辑</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.swipeBtn, { backgroundColor: c.red }]}
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
                <Text style={txt.mealCal}>{r.calories ? `${r.calories}kcal` : ''}</Text>
              </View>
            </ReanimatedSwipeable>
          ))
        ) : (
          <Text style={txt.empty}>{date === todayStr() ? '今天还没有饮食记录' : '当日无记录'}</Text>
        )}

        <View style={{ height: 140 }} />
      </ScrollView>

      <DietFAB onPhoto={handlePhoto} onText={handleText} />
    </SafeAreaView>
  );
}

function NutriPill({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <View style={styles.nutriItem}>
      <Text style={[txt.nutriVal, { color }]}>{value}</Text>
      <Text style={txt.nutriUnit}>{unit}</Text>
      <Text style={txt.nutriLabel}>{label}</Text>
    </View>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  dateRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, paddingVertical: spacing.sm },
  content: { padding: spacing.lg },
  summaryCard: {
    flexDirection: 'row', justifyContent: 'space-around',
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.lg, ...shadows.subtle,
  },
  nutriItem: { alignItems: 'center', gap: 2 },
  mealRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: c.bgCard, borderRadius: radii.md,
    padding: spacing.lg, marginBottom: spacing.sm, ...shadows.subtle,
  },
  mealDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: c.brand },
  swipeActions: {
    flexDirection: 'row', alignItems: 'stretch',
    marginBottom: spacing.sm,
  },
  swipeBtn: {
    width: 76,
    alignItems: 'center', justifyContent: 'center',
    gap: 4,
    marginLeft: 6,
    borderRadius: radii.md,
  },
  agentLink: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: c.bgCard,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    marginTop: -spacing.sm,
    marginBottom: spacing.lg,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  dateText: { fontSize: 16, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  nutriVal: { fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  nutriUnit: { fontSize: 10, color: c.labelSecondary } as TextStyle,
  nutriLabel: { fontSize: 11, color: c.labelTertiary } as TextStyle,
  mealType: { fontSize: 13, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  mealFood: { fontSize: 13, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  mealCal: { fontSize: 13, fontWeight: '600', color: '#FF6723' } as TextStyle,
  swipeText: { fontSize: 11, color: '#fff', fontWeight: '600' } as TextStyle,
  agentLinkText: { fontSize: 14, fontWeight: '600' } as TextStyle,
  empty: { fontSize: 14, color: c.labelTertiary, textAlign: 'center', paddingVertical: 30 } as TextStyle,
});
