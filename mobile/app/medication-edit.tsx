/**
 * 药品编辑页 (轻量).
 *
 * 入口:
 * - 用药管理页点击某个药品 → 跳转到本页
 *
 * 说明:
 * - 仅编辑基础字段, 避免引入复杂提醒/计划逻辑
 * - backend 已支持 `PUT /medication/medications/{id}`
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

import { getMedication, updateMedication, type Medication, type MedicationSafetyAlert } from '../services/medications';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import { useToast } from '../hooks/useToast';

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
  const [safetyAlerts, setSafetyAlerts] = useState<MedicationSafetyAlert[]>([]);

  useEffect(() => {
    const m = medQuery.data;
    if (!m) return;
    setName(m.name || '');
    setDosage(m.dosage || '');
    setFrequency(m.frequency || '');
    setPurpose(m.purpose || '');
    setNotes(m.notes || '');
    if (Array.isArray(m.safety_alerts)) {
      setSafetyAlerts(m.safety_alerts);
    }
  }, [medQuery.data]);

  const updateMut = useMutation({
    mutationFn: (payload: Partial<Medication>) => updateMedication(id, payload),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ['medications'] });
      const alerts = saved.safety_alerts ?? [];
      setSafetyAlerts(alerts);
      toast.show(alerts.length > 0 ? '已保存，发现用药安全提醒' : '已保存', 'success');
      if (alerts.length > 0) return;
      router.back();
    },
    onError: () => Alert.alert('保存失败', '请稍后再试'),
  });

  const handleSave = () => {
    if (!validId) return;
    const trimmedName = name.trim();
    if (!trimmedName) {
      Alert.alert('请输入药品名称');
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    updateMut.mutate({
      name: trimmedName,
      dosage: dosage.trim() || null,
      frequency: frequency.trim() || null,
      purpose: purpose.trim() || null,
      notes: notes.trim() || null,
    });
  };

  if (!validId) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
          </TouchableOpacity>
          <Text style={txt.title}>编辑药品</Text>
          <View style={{ width: 64 }} />
        </View>
        <View style={styles.center}>
          <Text style={txt.hint}>参数错误: 缺少药品 id</Text>
        </View>
      </SafeAreaView>
    );
  }

  const isLoading = medQuery.isLoading;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>编辑药品</Text>
        <TouchableOpacity
          onPress={handleSave}
          hitSlop={10}
          style={styles.saveBtn}
          accessibilityRole="button"
          accessibilityLabel="保存药品"
        >
          <Text style={txt.saveText}>{updateMut.isPending ? '保存中' : '保存'}</Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {isLoading ? (
            <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
          ) : medQuery.isError ? (
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
          ) : !medQuery.data ? (
            <View style={styles.center}>
              <Ionicons name="help-circle-outline" size={44} color={c.labelTertiary} />
              <Text style={txt.errorTitle}>未找到药品</Text>
              <Text style={txt.hint}>可能已被删除或不可用</Text>
            </View>
          ) : (
            <View style={styles.form}>
              <MedicationSafetyAlertsPanel alerts={safetyAlerts} />
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

function MedicationSafetyAlertsPanel({ alerts }: { alerts: MedicationSafetyAlert[] }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  if (alerts.length === 0) return null;

  return (
    <View style={styles.alertPanel}>
      <View style={styles.alertHeader}>
        <Ionicons name="warning-outline" size={18} color="#B45309" />
        <Text style={txt.alertTitle}>用药安全提醒</Text>
      </View>
      {alerts.map((alert) => (
        <View key={alert.rule_id} style={styles.alertItem}>
          <View style={styles.alertItemHeader}>
            <Text style={txt.alertBadge}>{alert.severity.label_zh}</Text>
            <Text style={txt.alertItemTitle}>{alert.title}</Text>
          </View>
          <Text style={txt.alertMessage}>{alert.message}</Text>
          {alert.action ? <Text style={txt.alertAction}>{alert.action}</Text> : null}
        </View>
      ))}
      <Text style={txt.alertBoundary}>这些提醒用于风险分层，不替代医生诊断或处方决定。</Text>
    </View>
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
    form: { paddingTop: spacing.md, gap: spacing.md },
    alertPanel: {
      gap: 10,
      padding: spacing.md,
      borderRadius: radii.lg,
      backgroundColor: '#FFFBEB',
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: '#F59E0B',
    },
    alertHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    alertItem: {
      gap: 6,
      paddingTop: 10,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: 'rgba(180, 83, 9, 0.25)',
    },
    alertItemHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
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
    alertTitle: { fontSize: 15, fontWeight: '800', color: '#92400E' } as TextStyle,
    alertBadge: {
      overflow: 'hidden',
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: 999,
      backgroundColor: '#FDE68A',
      fontSize: 12,
      fontWeight: '800',
      color: '#92400E',
    } as TextStyle,
    alertItemTitle: { flex: 1, fontSize: 14, fontWeight: '800', color: '#78350F' } as TextStyle,
    alertMessage: { fontSize: 13, lineHeight: 18, color: '#92400E' } as TextStyle,
    alertAction: { fontSize: 13, lineHeight: 18, fontWeight: '700', color: '#78350F' } as TextStyle,
    alertBoundary: { fontSize: 12, lineHeight: 17, color: '#A16207' } as TextStyle,
  };
}
