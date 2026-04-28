import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, TextStyle, Alert } from 'react-native';
import * as Haptics from 'expo-haptics';
import { colors, spacing, radii } from '../../constants/theme';
import type { DietRecordCreate } from '../../services/diet';

interface Props {
  date: string;
  onSubmit: (record: DietRecordCreate) => void;
  onCancel: () => void;
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

export default function MealForm({ date, onSubmit, onCancel, initialDescription, initialCalories, initialProtein, initialCarbs, initialFat }: Props) {
  const [mealType, setMealType] = useState<'breakfast' | 'lunch' | 'dinner' | 'snack'>('lunch');
  const [desc, setDesc] = useState(initialDescription || '');
  const [cal, setCal] = useState(initialCalories?.toString() || '');
  const [protein, setProtein] = useState(initialProtein?.toString() || '');
  const [carbs, setCarbs] = useState(initialCarbs?.toString() || '');
  const [fat, setFat] = useState(initialFat?.toString() || '');
  const [alcohol, setAlcohol] = useState('');

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
            <Text style={[txt.typeText, mealType === t.key && txt.typeTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TextInput style={styles.input} placeholder="食物描述（如：鸡胸肉200g、米饭一碗）" placeholderTextColor={colors.labelTertiary}
        value={desc} onChangeText={setDesc} multiline />
      <View style={styles.nutriRow}>
        <NutrientInput label="热量" unit="kcal" value={cal} onChange={setCal} />
        <NutrientInput label="蛋白质" unit="g" value={protein} onChange={setProtein} />
        <NutrientInput label="碳水" unit="g" value={carbs} onChange={setCarbs} />
        <NutrientInput label="脂肪" unit="g" value={fat} onChange={setFat} />
      </View>
      <View style={styles.alcoholRow}>
        <Text style={txt.alcoholLabel}>🍺 饮酒</Text>
        <TextInput style={styles.alcoholInput} keyboardType="decimal-pad"
          placeholder="0" placeholderTextColor={colors.labelQuaternary}
          value={alcohol} onChangeText={setAlcohol} />
        <Text style={txt.alcoholUnit}>标准杯</Text>
        <View style={styles.alcoholPresets}>
          {['1', '2', '3'].map(v => (
            <TouchableOpacity key={v} style={styles.alcoholChip}
              onPress={() => { Haptics.selectionAsync(); setAlcohol(v); }} activeOpacity={0.6}>
              <Text style={txt.alcoholChip}>{v}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      <Text style={txt.alcoholHint}>1 杯 ≈ 330ml 啤酒 ≈ 150ml 红酒 ≈ 45ml 白酒</Text>
      <View style={styles.btnRow}>
        <TouchableOpacity style={styles.cancelBtn} onPress={onCancel} activeOpacity={0.7}>
          <Text style={txt.cancelText}>取消</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.saveBtn} onPress={handleSubmit} activeOpacity={0.7}>
          <Text style={txt.saveText}>保存</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function NutrientInput({ label, unit, value, onChange }: { label: string; unit: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={styles.nutriCell}>
      <Text style={txt.nutriLabel}>{label}</Text>
      <TextInput style={styles.nutriInput} keyboardType="decimal-pad"
        placeholder="0" placeholderTextColor={colors.labelQuaternary}
        value={value} onChangeText={onChange} />
      <Text style={txt.nutriUnit}>{unit}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colors.bgCard, borderRadius: radii.lg, padding: spacing.lg, marginBottom: spacing.md },
  typeRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.md },
  typeChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: radii.full, backgroundColor: colors.bgPrimary },
  typeChipActive: { backgroundColor: colors.brand },
  input: {
    backgroundColor: colors.bgPrimary, borderRadius: radii.md,
    paddingHorizontal: 14, paddingVertical: 10, fontSize: 14,
    color: colors.labelPrimary, marginBottom: spacing.md, minHeight: 44,
  },
  nutriRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.md },
  nutriCell: { flex: 1, alignItems: 'center' },
  nutriInput: {
    backgroundColor: colors.bgPrimary, borderRadius: radii.sm,
    paddingHorizontal: 6, paddingVertical: 6, fontSize: 14,
    color: colors.labelPrimary, textAlign: 'center', width: '100%',
  },
  alcoholRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: colors.bgPrimary, borderRadius: radii.md,
    marginBottom: 4,
  },
  alcoholInput: {
    width: 48, textAlign: 'center', fontSize: 15,
    color: colors.labelPrimary, paddingVertical: 4,
    backgroundColor: colors.bgCard, borderRadius: radii.sm,
  },
  alcoholPresets: { flexDirection: 'row', gap: 4, marginLeft: 'auto' },
  alcoholChip: {
    paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: colors.bgCard, borderRadius: radii.full,
  },
  btnRow: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  cancelBtn: { flex: 1, paddingVertical: 12, borderRadius: radii.md, backgroundColor: colors.bgPrimary, alignItems: 'center' },
  saveBtn: { flex: 1, paddingVertical: 12, borderRadius: radii.md, backgroundColor: colors.brand, alignItems: 'center' },
});

const txt = {
  typeText: { fontSize: 13, fontWeight: '500', color: colors.labelSecondary } as TextStyle,
  typeTextActive: { color: '#fff', fontWeight: '600' } as TextStyle,
  nutriLabel: { fontSize: 10, color: colors.labelTertiary, marginBottom: 4 } as TextStyle,
  nutriUnit: { fontSize: 10, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
  alcoholLabel: { fontSize: 13, color: colors.labelSecondary, fontWeight: '500' } as TextStyle,
  alcoholUnit: { fontSize: 12, color: colors.labelTertiary } as TextStyle,
  alcoholChip: { fontSize: 13, color: colors.labelSecondary, fontWeight: '500' } as TextStyle,
  alcoholHint: { fontSize: 10, color: colors.labelTertiary, marginBottom: spacing.sm, paddingLeft: 2 } as TextStyle,
  cancelText: { fontSize: 15, fontWeight: '500', color: colors.labelSecondary } as TextStyle,
  saveText: { fontSize: 15, fontWeight: '600', color: '#fff' } as TextStyle,
};
