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
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import { useToast } from '../hooks/useToast';

export default function MedicationEditScreen() {
  const router = useRouter();
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
            <Ionicons name="chevron-back" size={26} color={C.ink1} />
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
          <Ionicons name="chevron-back" size={26} color={C.ink1} />
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
            <View style={styles.center}><ActivityIndicator color={C.green500} /></View>
          ) : medQuery.isError ? (
            <View style={styles.center}>
              <Ionicons name="alert-circle-outline" size={44} color={C.ink3} />
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
              <Ionicons name="help-circle-outline" size={44} color={C.ink3} />
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
                  placeholderTextColor={C.ink3}
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
                  placeholderTextColor={C.ink3}
                  style={styles.input}
                  accessibilityLabel="剂量"
                />
              </Field>
              <Field label="频率">
                <TextInput
                  value={frequency}
                  onChangeText={setFrequency}
                  placeholder="例如: 每日 2 次"
                  placeholderTextColor={C.ink3}
                  style={styles.input}
                  accessibilityLabel="频率"
                />
              </Field>
              <Field label="用途">
                <TextInput
                  value={purpose}
                  onChangeText={setPurpose}
                  placeholder="例如: 控糖 / 鼻炎控制"
                  placeholderTextColor={C.ink3}
                  style={styles.input}
                  accessibilityLabel="用途"
                />
              </Field>
              <Field label="备注">
                <TextInput
                  value={notes}
                  onChangeText={setNotes}
                  placeholder="例如: 饭后服用"
                  placeholderTextColor={C.ink3}
                  style={[styles.input, styles.notesInput]}
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
  if (alerts.length === 0) return null;

  return (
    <View style={styles.alertPanel}>
      <View style={styles.alertHeader}>
        <Ionicons name="warning-outline" size={18} color={revaSemantic.caution.fg} />
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
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.ink2 }}>
        {label}{required ? ' *' : ''}
      </Text>
      {children}
    </View>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface input / 活力绿 / 安全提醒走 caution 三步语义。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2,
  },
  backBtn: { width: 48, alignItems: 'flex-start' },
  saveBtn: {
    minWidth: 64,
    alignItems: 'flex-end',
    paddingVertical: 6,
  },
  scroll: { paddingHorizontal: revaSpacing.s3, paddingBottom: revaSpacing.s5 },
  center: { paddingTop: 80, alignItems: 'center' },
  retryBtn: {
    marginTop: revaSpacing.s3,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: 12,
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    ...revaShadows.sm,
  },
  form: { paddingTop: revaSpacing.s3, gap: revaSpacing.s3 },
  alertPanel: {
    gap: 10,
    padding: revaSpacing.s3,
    borderRadius: revaRadii.lg,
    backgroundColor: revaSemantic.caution.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
  },
  alertHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  alertItem: {
    gap: 6,
    paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: revaSemantic.caution.line,
  },
  alertItemHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  input: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: 12,
    fontFamily: revaFonts.mono,
    color: C.ink1,
    ...revaShadows.sm,
  },
  notesInput: { fontFamily: revaFonts.sans, height: 96, textAlignVertical: 'top' },
  bottomPad: { height: 20 },
});

// 剂量/频率录入走 IBM Plex Mono;文字走 Manrope/ink。安全提醒文字用 caution.fg。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1 } as TextStyle,
  hint: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink2 } as TextStyle,
  errorTitle: { fontFamily: revaFonts.sans, marginTop: 10, fontSize: 16, fontWeight: '700', color: C.ink1 } as TextStyle,
  retryText: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '700', color: C.green500 } as TextStyle,
  saveText: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '700', color: C.green500 } as TextStyle,
  alertTitle: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '800', color: revaSemantic.caution.fg } as TextStyle,
  alertBadge: {
    fontFamily: revaFonts.sans,
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
    backgroundColor: revaSemantic.caution.line,
    fontSize: 12,
    fontWeight: '800',
    color: revaSemantic.caution.fg,
  } as TextStyle,
  alertItemTitle: { fontFamily: revaFonts.sans, flex: 1, fontSize: 14, fontWeight: '800', color: revaSemantic.caution.fg } as TextStyle,
  alertMessage: { fontFamily: revaFonts.sans, fontSize: 13, lineHeight: 18, color: revaSemantic.caution.fg } as TextStyle,
  alertAction: { fontFamily: revaFonts.sans, fontSize: 13, lineHeight: 18, fontWeight: '700', color: revaSemantic.caution.fg } as TextStyle,
  alertBoundary: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 17, color: revaSemantic.caution.fg } as TextStyle,
};
