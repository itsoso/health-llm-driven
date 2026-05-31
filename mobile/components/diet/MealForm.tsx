import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, Alert } from 'react-native';
import * as Haptics from 'expo-haptics';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { DietRecord, DietRecordCreate } from '../../services/diet';

interface Props {
  date: string;
  onSubmit: (record: DietRecordCreate) => void;
  onCancel: () => void;
  /** 编辑模式: 传入 record 预填全部字段; 不传则是新建. */
  initialRecord?: DietRecord;
  initialDescription?: string;
  initialCalories?: number;
  initialProtein?: number;
  initialCarbs?: number;
  initialFat?: number;
}

const MEAL_TYPES = [
  { key: 'breakfast' as const, label: '早餐' },
  { key: 'lunch' as const, label: '午餐' },
  { key: 'dinner' as const, label: '晚餐' },
  { key: 'snack' as const, label: '加餐' },
];

export default function MealForm({ date, onSubmit, onCancel, initialRecord, initialDescription, initialCalories, initialProtein, initialCarbs, initialFat }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const isEdit = !!initialRecord;
  const [mealType, setMealType] = useState<'breakfast' | 'lunch' | 'dinner' | 'snack'>(
    (initialRecord?.meal_type as any) || 'lunch'
  );
  const [desc, setDesc] = useState(initialRecord?.food_items ?? initialDescription ?? '');
  const [cal, setCal] = useState(
    initialRecord?.calories?.toString() ?? initialCalories?.toString() ?? ''
  );
  const [protein, setProtein] = useState(
    initialRecord?.protein?.toString() ?? initialProtein?.toString() ?? ''
  );
  const [carbs, setCarbs] = useState(
    initialRecord?.carbs?.toString() ?? initialCarbs?.toString() ?? ''
  );
  const [fat, setFat] = useState(
    initialRecord?.fat?.toString() ?? initialFat?.toString() ?? ''
  );
  const [alcohol, setAlcohol] = useState(initialRecord?.alcohol_units?.toString() ?? '');

  const handleSubmit = () => {
    if (!desc.trim()) { Alert.alert('请输入食物描述'); return; }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onSubmit({
      record_date: date,
      meal_type: mealType,
      food_items: desc.trim(),
      calories: cal ? parseFloat(cal) : undefined,
      protein: protein ? parseFloat(protein) : undefined,
      carbs: carbs ? parseFloat(carbs) : undefined,
      fat: fat ? parseFloat(fat) : undefined,
      alcohol_units: alcohol ? parseFloat(alcohol) : undefined,
    });
  };

  return (
    <View style={styles.container}>
      <View style={styles.typeRow}>
        {MEAL_TYPES.map(t => (
          <TouchableOpacity key={t.key}
            style={[styles.typeChip, mealType === t.key && styles.typeChipActive]}
            onPress={() => setMealType(t.key)} activeOpacity={0.7}>
            <Text style={[styles.typeText, mealType === t.key && styles.typeTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TextInput style={styles.input} placeholder="食物描述（如：鸡胸肉200g、米饭一碗）" placeholderTextColor={c.labelTertiary}
        value={desc} onChangeText={setDesc} multiline />
      <View style={styles.nutriRow}>
        <NutrientInput label="热量" unit="kcal" value={cal} onChange={setCal} />
        <NutrientInput label="蛋白质" unit="g" value={protein} onChange={setProtein} />
        <NutrientInput label="碳水" unit="g" value={carbs} onChange={setCarbs} />
        <NutrientInput label="脂肪" unit="g" value={fat} onChange={setFat} />
      </View>
      <View style={styles.alcoholRow}>
        <Text style={styles.alcoholLabel}>🍺 饮酒</Text>
        <TextInput style={styles.alcoholInput} keyboardType="decimal-pad"
          placeholder="0" placeholderTextColor={c.labelQuaternary}
          value={alcohol} onChangeText={setAlcohol} />
        <Text style={styles.alcoholUnit}>标准杯</Text>
        <View style={styles.alcoholPresets}>
          {['1', '2', '3'].map(v => (
            <TouchableOpacity key={v} style={styles.alcoholChip}
              onPress={() => { Haptics.selectionAsync(); setAlcohol(v); }} activeOpacity={0.6}>
              <Text style={styles.alcoholChipText}>{v}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      <Text style={styles.alcoholHint}>1 杯 ≈ 330ml 啤酒 ≈ 150ml 红酒 ≈ 45ml 白酒</Text>
      <View style={styles.btnRow}>
        <TouchableOpacity style={styles.cancelBtn} onPress={onCancel} activeOpacity={0.7}>
          <Text style={styles.cancelText}>取消</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.saveBtn} onPress={handleSubmit} activeOpacity={0.7}>
          <Text style={styles.saveText}>{isEdit ? '更新' : '保存'}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function NutrientInput({ label, unit, value, onChange }: { label: string; unit: string; value: string; onChange: (v: string) => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={styles.nutriCell}>
      <Text style={styles.nutriLabel}>{label}</Text>
      <TextInput style={styles.nutriInput} keyboardType="decimal-pad"
        placeholder="0" placeholderTextColor={c.labelQuaternary}
        value={value} onChangeText={onChange} />
      <Text style={styles.nutriUnit}>{unit}</Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    container: { backgroundColor: c.bgCard, borderRadius: radii.lg, padding: spacing.lg, marginBottom: spacing.md },
    typeRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.md },
    typeChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: radii.full, backgroundColor: c.bgPrimary },
    typeChipActive: { backgroundColor: c.brand },
    input: {
      backgroundColor: c.bgPrimary, borderRadius: radii.md,
      paddingHorizontal: 14, paddingVertical: 10, fontSize: 14,
      color: c.labelPrimary, marginBottom: spacing.md, minHeight: 44,
    },
    nutriRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.md },
    nutriCell: { flex: 1, alignItems: 'center' },
    nutriInput: {
      backgroundColor: c.bgPrimary, borderRadius: radii.sm,
      paddingHorizontal: 6, paddingVertical: 6, fontSize: 14,
      color: c.labelPrimary, textAlign: 'center', width: '100%',
    },
    alcoholRow: {
      flexDirection: 'row', alignItems: 'center', gap: 8,
      paddingVertical: 8, paddingHorizontal: 10,
      backgroundColor: c.bgPrimary, borderRadius: radii.md,
      marginBottom: 4,
    },
    alcoholInput: {
      width: 48, textAlign: 'center', fontSize: 15,
      color: c.labelPrimary, paddingVertical: 4,
      backgroundColor: c.bgCard, borderRadius: radii.sm,
    },
    alcoholPresets: { flexDirection: 'row', gap: 4, marginLeft: 'auto' },
    alcoholChip: {
      paddingHorizontal: 10, paddingVertical: 4,
      backgroundColor: c.bgCard, borderRadius: radii.full,
    },
    btnRow: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
    cancelBtn: { flex: 1, paddingVertical: 12, borderRadius: radii.md, backgroundColor: c.bgPrimary, alignItems: 'center' },
    saveBtn: { flex: 1, paddingVertical: 12, borderRadius: radii.md, backgroundColor: c.brand, alignItems: 'center' },
    typeText: { fontSize: 13, fontWeight: '500', color: c.labelSecondary },
    typeTextActive: { color: '#fff', fontWeight: '600' },
    nutriLabel: { fontSize: 10, color: c.labelTertiary, marginBottom: 4 },
    nutriUnit: { fontSize: 10, color: c.labelTertiary, marginTop: 2 },
    alcoholLabel: { fontSize: 13, color: c.labelSecondary, fontWeight: '500' },
    alcoholUnit: { fontSize: 12, color: c.labelTertiary },
    alcoholChipText: { fontSize: 13, color: c.labelSecondary, fontWeight: '500' },
    alcoholHint: { fontSize: 10, color: c.labelTertiary, marginBottom: spacing.sm, paddingLeft: 2 },
    cancelText: { fontSize: 15, fontWeight: '500', color: c.labelSecondary },
    saveText: { fontSize: 15, fontWeight: '600', color: '#fff' },
  });
}
