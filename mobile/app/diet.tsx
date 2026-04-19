import React, { useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, Alert, Modal } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { useDailyDiet } from '@/hooks/useDiet';
import { createDietRecord, estimateNutrition, type DietRecordCreate } from '@/services/diet';
import HealthCard from '@/components/design-system/HealthCard';
import MealForm from '@/components/diet/MealForm';
import DietFAB from '@/components/diet/DietFAB';
import { colors, spacing, radii, shadows } from '@/constants/theme';

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
  const router = useRouter();
  const qc = useQueryClient();
  const [date, setDate] = useState(todayStr());
  const { data: daily, refetch, isRefetching } = useDailyDiet(date);
  const [showForm, setShowForm] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const [formDefaults, setFormDefaults] = useState<Partial<DietRecordCreate>>({});

  const handleSave = useCallback(async (record: DietRecordCreate) => {
    try {
      await createDietRecord(record);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setShowForm(false);
      qc.invalidateQueries({ queryKey: ['diet'] });
    } catch {
      Alert.alert('保存失败', '请稍后再试');
    }
  }, [qc]);

  const handleText = useCallback(async () => {
    Alert.prompt('文字估算', '描述你吃的食物（如：鸡胸肉200g + 糙米饭一碗）', async (text) => {
      if (!text?.trim()) return;
      setEstimating(true);
      try {
        const est = await estimateNutrition(text);
        setFormDefaults({
          food_description: est.food_description || text,
          calories: est.calories,
          protein_g: est.protein_g,
          carbs_g: est.carbs_g,
          fat_g: est.fat_g,
        });
        setShowForm(true);
      } catch {
        Alert.alert('估算失败');
      } finally {
        setEstimating(false);
      }
    });
  }, []);

  const handlePhoto = useCallback(() => {
    Alert.alert('拍照识别', '该功能需要相机权限，即将开放');
  }, []);

  const isToday = date === todayStr();
  const dateLabel = isToday ? '今天' : new Date(date).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', weekday: 'short' });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>饮食记录</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Date selector */}
      <View style={styles.dateRow}>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, -1))}>
          <Ionicons name="chevron-back-circle-outline" size={28} color={colors.labelSecondary} />
        </TouchableOpacity>
        <Text style={txt.dateText}>{dateLabel}</Text>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, 1))} disabled={isToday}>
          <Ionicons name="chevron-forward-circle-outline" size={28} color={isToday ? colors.labelQuaternary : colors.labelSecondary} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
        showsVerticalScrollIndicator={false}>

        {/* Summary */}
        {daily && (
          <View style={styles.summaryCard}>
            <NutriPill label="热量" value={`${daily.total_calories.toFixed(0)}`} unit="kcal" color="#FF6723" />
            <NutriPill label="蛋白质" value={`${daily.total_protein_g.toFixed(1)}`} unit="g" color="#FF375F" />
            <NutriPill label="碳水" value={`${daily.total_carbs_g.toFixed(1)}`} unit="g" color="#FF9F0A" />
            <NutriPill label="脂肪" value={`${daily.total_fat_g.toFixed(1)}`} unit="g" color="#BF5AF2" />
          </View>
        )}

        {/* Meal form */}
        {showForm && (
          <MealForm date={date} onSubmit={handleSave} onCancel={() => { setShowForm(false); setFormDefaults({}); }}
            initialDescription={formDefaults.food_description}
            initialCalories={formDefaults.calories}
            initialProtein={formDefaults.protein_g}
            initialCarbs={formDefaults.carbs_g}
            initialFat={formDefaults.fat_g} />
        )}

        {/* Meal records */}
        {daily?.records && daily.records.length > 0 ? (
          daily.records.map((r) => (
            <View key={r.id} style={styles.mealRow}>
              <View style={styles.mealDot} />
              <View style={{ flex: 1 }}>
                <Text style={txt.mealType}>{MEAL_LABEL[r.meal_type] || r.meal_type}</Text>
                <Text style={txt.mealFood} numberOfLines={2}>{r.food_description}</Text>
              </View>
              <Text style={txt.mealCal}>{r.calories ? `${r.calories}kcal` : ''}</Text>
            </View>
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
  return (
    <View style={styles.nutriItem}>
      <Text style={[txt.nutriVal, { color }]}>{value}</Text>
      <Text style={txt.nutriUnit}>{unit}</Text>
      <Text style={txt.nutriLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  dateRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, paddingVertical: spacing.sm },
  content: { padding: spacing.lg },
  summaryCard: {
    flexDirection: 'row', justifyContent: 'space-around',
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.lg, ...shadows.subtle,
  },
  nutriItem: { alignItems: 'center', gap: 2 },
  mealRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.lg, marginBottom: spacing.sm, ...shadows.subtle,
  },
  mealDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: colors.brand },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  dateText: { fontSize: 16, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  nutriVal: { fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  nutriUnit: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  nutriLabel: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  mealType: { fontSize: 13, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  mealFood: { fontSize: 13, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  mealCal: { fontSize: 13, fontWeight: '600', color: '#FF6723' } as TextStyle,
  empty: { fontSize: 14, color: colors.labelTertiary, textAlign: 'center', paddingVertical: 30 } as TextStyle,
};
