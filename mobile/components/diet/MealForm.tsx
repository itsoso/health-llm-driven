import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, Alert } from 'react-native';
import * as Haptics from 'expo-haptics';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaFonts,
} from '../../constants/revaTheme';
import type { DietRecord, DietRecordCreate } from '../../services/diet';

interface Props {
  date: string;
  onSubmit: (record: DietRecordCreate) => void;
  onCancel: () => void;
  /** 编辑模式: 传入 record 预填全部字段; 不传则是新建. */
  initialRecord?: DietRecord;
  initialMealType?: DietRecordCreate['meal_type'];
  initialDescription?: string;
  initialCalories?: number;
  initialProtein?: number;
  initialCarbs?: number;
  initialFat?: number;
  assistiveHint?: string;
}

const MEAL_TYPES = [
  { key: 'breakfast' as const, label: '早餐' },
  { key: 'lunch' as const, label: '午餐' },
  { key: 'dinner' as const, label: '晚餐' },
  { key: 'snack' as const, label: '加餐' },
];

export default function MealForm({ date, onSubmit, onCancel, initialRecord, initialMealType, initialDescription, initialCalories, initialProtein, initialCarbs, initialFat, assistiveHint }: Props) {
  const isEdit = !!initialRecord;
  const [mealType, setMealType] = useState<'breakfast' | 'lunch' | 'dinner' | 'snack'>(
    (initialRecord?.meal_type as any) || initialMealType || 'lunch'
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
      {assistiveHint ? (
        <View style={styles.assistiveHint}>
          <Text style={styles.assistiveHintText}>{assistiveHint}</Text>
        </View>
      ) : null}
      <TextInput style={styles.input} placeholder="食物描述（如：鸡胸肉200g、米饭一碗）" placeholderTextColor={C.ink3}
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
          placeholder="0" placeholderTextColor={C.ink4}
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
  return (
    <View style={styles.nutriCell}>
      <Text style={styles.nutriLabel}>{label}</Text>
      <TextInput style={styles.nutriInput} keyboardType="decimal-pad"
        placeholder="0" placeholderTextColor={C.ink4}
        value={value} onChangeText={onChange} />
      <Text style={styles.nutriUnit}>{unit}</Text>
    </View>
  );
}

// Reva 设计语言:暖白 surface / paper2 输入底 / 活力绿 / 数字录入走等宽 mono。
const styles = StyleSheet.create({
  container: { backgroundColor: C.surface, borderRadius: revaRadii.lg, padding: revaSpacing.s4, marginBottom: revaSpacing.s3 },
  typeRow: { flexDirection: 'row', gap: 8, marginBottom: revaSpacing.s3 },
  typeChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: revaRadii.pill, backgroundColor: C.paper2 },
  typeChipActive: { backgroundColor: C.green500 },
  assistiveHint: {
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    paddingHorizontal: 12,
    paddingVertical: 9,
    marginBottom: revaSpacing.s3,
  },
  assistiveHintText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.green700,
    fontWeight: '700',
  },
  input: {
    backgroundColor: C.paper2, borderRadius: revaRadii.md,
    paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, fontFamily: revaFonts.sans,
    color: C.ink1, marginBottom: revaSpacing.s3, minHeight: 44,
  },
  nutriRow: { flexDirection: 'row', gap: 8, marginBottom: revaSpacing.s3 },
  nutriCell: { flex: 1, alignItems: 'center' },
  nutriInput: {
    backgroundColor: C.paper2, borderRadius: revaRadii.sm,
    paddingHorizontal: 6, paddingVertical: 6, fontSize: 14, fontFamily: revaFonts.mono,
    color: C.ink1, textAlign: 'center', width: '100%',
  },
  alcoholRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: C.paper2, borderRadius: revaRadii.md,
    marginBottom: 4,
  },
  alcoholInput: {
    width: 48, textAlign: 'center', fontSize: 15, fontFamily: revaFonts.mono,
    color: C.ink1, paddingVertical: 4,
    backgroundColor: C.surface, borderRadius: revaRadii.sm,
  },
  alcoholPresets: { flexDirection: 'row', gap: 4, marginLeft: 'auto' },
  alcoholChip: {
    paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: C.surface, borderRadius: revaRadii.pill,
  },
  btnRow: { flexDirection: 'row', gap: revaSpacing.s3, marginTop: revaSpacing.s4 },
  cancelBtn: { flex: 1, paddingVertical: 12, borderRadius: revaRadii.md, backgroundColor: C.paper2, alignItems: 'center' },
  saveBtn: { flex: 1, paddingVertical: 12, borderRadius: revaRadii.md, backgroundColor: C.green500, alignItems: 'center' },
  typeText: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '500', color: C.ink2 },
  typeTextActive: { color: '#fff', fontWeight: '600' },
  nutriLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink3, marginBottom: 4 },
  nutriUnit: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink3, marginTop: 2 },
  alcoholLabel: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, fontWeight: '500' },
  alcoholUnit: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3 },
  alcoholChipText: { fontFamily: revaFonts.mono, fontSize: 13, color: C.ink2, fontWeight: '500' },
  alcoholHint: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink3, marginBottom: revaSpacing.s2, paddingLeft: 2 },
  cancelText: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '500', color: C.ink2 },
  saveText: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '600', color: '#fff' },
});
