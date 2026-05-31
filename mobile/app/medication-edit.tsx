/**
 * 药品 添加 / 编辑 页 (轻量).
 *
 * 入口:
 * - 用药管理页点击某个药品 → 编辑 (带 ?id=)
 * - 用药管理页右上角 "+" → 添加 (无 id)
 *
 * 说明:
 * - 仅编辑基础字段, 避免引入复杂提醒/计划逻辑
 * - 编辑: `PUT /medication/medications/{id}`
 * - 添加: `POST /medication/medications` —— 响应体可能带 safety_alerts
 *   (Tier 0 ②: 新增药物即时跑 SafetyGuardian, 命中 DDI/DSI/PGx high/critical
 *   相互作用时当场预警, 而不是等 23:00 批量检测). 命中时**不**静默返回,
 *   显著展示告警后再让用户离开 (诚实的三态).
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
  KeyboardAvoidingView,
  TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import {
  getMedication, updateMedication, addMedication,
  type Medication, type MedicationSafetyAlert,
} from '../services/medications';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import { useToast } from '../hooks/useToast';
import MedicationSafetyAlerts from '../components/medication/MedicationSafetyAlerts';

export default function MedicationEditScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const params = useLocalSearchParams() as any;
  const qc = useQueryClient();
  const toast = useToast();

  const id = Number(params?.id);
  const validId = Number.isFinite(id) && id > 0;
  const isAdd = !validId; // 无 id → 添加模式

  const medQuery = useQuery<Medication>({
    queryKey: ['medications', 'detail', id],
    queryFn: () => getMedication(id),
    enabled: validId,
    staleTime: 30_000,
  });

  const [name, setName] = useState('');
  const [dosage, setDosage] = useState('');
  const [frequency, setFrequency] = useState('');
  const [purpose, setPurpose] = useState('');
  const [notes, setNotes] = useState('');
  // 添加成功且命中高危相互作用时停在本页展示告警 (而不是立即 back).
  const [safetyAlerts, setSafetyAlerts] = useState<MedicationSafetyAlert[] | null>(null);

  useEffect(() => {
    const m = medQuery.data;
    if (!m) return;
    setName(m.name || '');
    setDosage(m.dosage || '');
    setFrequency(m.frequency || '');
    setPurpose(m.purpose || '');
    setNotes(m.notes || '');
  }, [medQuery.data]);

  const updateMut = useMutation({
    mutationFn: (payload: Partial<Medication>) => updateMedication(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['medications'] });
      toast.show('已保存', 'success');
      router.back();
    },
    onError: () => Alert.alert('保存失败', '请稍后再试'),
  });

  const addMut = useMutation({
    mutationFn: (payload: Partial<Medication>) => addMedication(payload),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['medications'] });
      if (res.safety_alerts.length > 0) {
        // 命中高危相互作用: 药已存, 但停在本页显著告警, 不静默 back.
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
        setSafetyAlerts(res.safety_alerts);
      } else {
        toast.show('已添加', 'success');
        router.back();
      }
    },
    onError: () => Alert.alert('添加失败', '请稍后再试'),
  });

  const saving = isAdd ? addMut.isPending : updateMut.isPending;

  const handleSave = () => {
    if (safetyAlerts) return; // 已是告警终态
    const trimmedName = name.trim();
    if (!trimmedName) {
      Alert.alert('请输入药品名称');
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const payload = {
      name: trimmedName,
      dosage: dosage.trim() || null,
      frequency: frequency.trim() || null,
      purpose: purpose.trim() || null,
      notes: notes.trim() || null,
    };
    if (isAdd) {
      addMut.mutate(payload);
    } else {
      updateMut.mutate(payload);
    }
  };

  // 添加命中高危相互作用 → 终态: 显著展示告警 + "我知道了" 离开.
  if (safetyAlerts) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <View style={{ width: 48 }} />
          <Text style={txt.title}>用药风险提醒</Text>
          <View style={{ width: 64 }} />
        </View>
        <ScrollView contentContainerStyle={styles.scroll}>
          <View style={{ paddingTop: spacing.md }}>
            <MedicationSafetyAlerts alerts={safetyAlerts} />
          </View>
        </ScrollView>
        <View style={styles.ackBar}>
          <TouchableOpacity
            onPress={() => router.back()}
            style={styles.ackBtn}
            accessibilityRole="button"
            accessibilityLabel="我知道了"
          >
            <Text style={txt.ackText}>我知道了</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const isLoading = !isAdd && medQuery.isLoading;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>{isAdd ? '添加药品' : '编辑药品'}</Text>
        <TouchableOpacity
          onPress={handleSave}
          hitSlop={10}
          style={styles.saveBtn}
          accessibilityRole="button"
          accessibilityLabel="保存药品"
        >
          <Text style={txt.saveText}>{saving ? '保存中' : '保存'}</Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {isLoading ? (
            <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
          ) : !isAdd && medQuery.isError ? (
            <View style={styles.center}>
              <Ionicons name="alert-circle-outline" size={44} color={c.labelTertiary} />
              <Text style={txt.errorTitle}>加载失败</Text>
              <Text style={txt.hint}>请检查网络后重试</Text>
              <TouchableOpacity
                onPress={() => { medQuery.refetch(); }}
                style={styles.retryBtn}
                accessibilityRole="button"
                accessibilityLabel="重试加载"
              >
                <Text style={txt.retryText}>重试</Text>
              </TouchableOpacity>
            </View>
          ) : !isAdd && !medQuery.data ? (
            <View style={styles.center}>
              <Ionicons name="help-circle-outline" size={44} color={c.labelTertiary} />
              <Text style={txt.errorTitle}>未找到药品</Text>
              <Text style={txt.hint}>可能已被删除或不可用</Text>
            </View>
          ) : (
            <View style={styles.form}>
              <Field label="药品名称" required>
                <TextInput
                  value={name}
                  onChangeText={setName}
                  placeholder="例如: 二甲双胍"
                  placeholderTextColor={c.labelTertiary}
                  style={styles.input}
                  accessibilityLabel="药品名称"
                  autoCapitalize="none"
                />
              </Field>
              <Field label="剂量">
                <TextInput
                  value={dosage}
                  onChangeText={setDosage}
                  placeholder="例如: 500mg"
                  placeholderTextColor={c.labelTertiary}
                  style={styles.input}
                  accessibilityLabel="剂量"
                />
              </Field>
              <Field label="频率">
                <TextInput
                  value={frequency}
                  onChangeText={setFrequency}
                  placeholder="例如: 每日 2 次"
                  placeholderTextColor={c.labelTertiary}
                  style={styles.input}
                  accessibilityLabel="频率"
                />
              </Field>
              <Field label="用途">
                <TextInput
                  value={purpose}
                  onChangeText={setPurpose}
                  placeholder="例如: 控糖 / 鼻炎控制"
                  placeholderTextColor={c.labelTertiary}
                  style={styles.input}
                  accessibilityLabel="用途"
                />
              </Field>
              <Field label="备注">
                <TextInput
                  value={notes}
                  onChangeText={setNotes}
                  placeholder="例如: 饭后服用"
                  placeholderTextColor={c.labelTertiary}
                  style={[styles.input, { height: 96, textAlignVertical: 'top' }]}
                  accessibilityLabel="备注"
                  multiline
                />
              </Field>

              <View style={styles.bottomPad} />
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  const { c } = useTheme();
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ fontSize: 13, fontWeight: '600', color: c.labelSecondary }}>
        {label}{required ? ' *' : ''}
      </Text>
      {children}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    },
    backBtn: { width: 48, alignItems: 'flex-start' },
    saveBtn: {
      minWidth: 64,
      alignItems: 'flex-end',
      paddingVertical: 6,
    },
    scroll: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl },
    center: { paddingTop: 80, alignItems: 'center' },
    retryBtn: {
      marginTop: spacing.md,
      paddingHorizontal: spacing.lg,
      paddingVertical: 12,
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      ...shadows.subtle,
    },
    ackBar: {
      paddingHorizontal: spacing.md,
      paddingTop: spacing.sm,
      paddingBottom: spacing.lg,
    },
    ackBtn: {
      backgroundColor: c.brand,
      borderRadius: radii.lg,
      paddingVertical: 14,
      alignItems: 'center',
    },
    form: { paddingTop: spacing.md, gap: spacing.md },
    input: {
      backgroundColor: c.bgCard,
      borderRadius: radii.md,
      paddingHorizontal: spacing.md,
      paddingVertical: 12,
      color: c.labelPrimary,
      ...shadows.subtle,
    },
    bottomPad: { height: 20 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    hint: { fontSize: 14, color: c.labelSecondary } as TextStyle,
    errorTitle: { marginTop: 10, fontSize: 16, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    retryText: { fontSize: 15, fontWeight: '700', color: c.brand } as TextStyle,
    saveText: { fontSize: 15, fontWeight: '700', color: c.brand } as TextStyle,
    ackText: { fontSize: 16, fontWeight: '700', color: '#FFFFFF' } as TextStyle,
  };
}
