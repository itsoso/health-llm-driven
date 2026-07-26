import React, { useState, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextStyle, ScrollView,
  ActivityIndicator, RefreshControl, Alert, TextInput,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import * as Clipboard from 'expo-clipboard';

import { spacing, radii, shadows } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import {
  exportDoctorReport, submitDoctorFeedback, listDoctorFeedback,
  type DoctorExport, type DoctorFeedback,
} from '../services/doctorReport';
import { sharePlainText } from '../utils/share';
import { todayStr } from '../utils/dietDate';

const EXPORT_QK = (days: number) => ['doctorExport', days];
const FEEDBACK_QK = ['doctorFeedback'];

export default function DoctorLoopScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const qc = useQueryClient();
  const [days] = useState(30);

  const expQ = useQuery<DoctorExport>({
    queryKey: EXPORT_QK(days),
    queryFn: () => exportDoctorReport(days),
    staleTime: 60_000,
  });

  const fbQ = useQuery<DoctorFeedback[]>({
    queryKey: FEEDBACK_QK,
    queryFn: () => listDoctorFeedback(20),
    staleTime: 60_000,
  });

  const [assessment, setAssessment] = useState('');
  const [plan, setPlan] = useState('');
  const [summary, setSummary] = useState('');

  const submitMut = useMutation({
    mutationFn: () => submitDoctorFeedback({
      summary: summary.trim() || undefined,
      assessment: assessment.trim() || undefined,
      plan: plan.trim() || undefined,
      visit_date: todayStr(),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FEEDBACK_QK });
      setSummary(''); setAssessment(''); setPlan('');
      Alert.alert('已记录', '医生反馈已存入档案');
    },
    onError: () => Alert.alert('失败', '请稍后重试'),
  });

  const onShare = async () => {
    if (!expQ.data?.markdown) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await sharePlainText({ title: '医生沟通摘要', message: expQ.data.markdown });
    } catch (e) {
      if (__DEV__) console.warn('[doctor-loop] share failed:', e);
    }
  };

  const onCopy = async () => {
    if (!expQ.data?.markdown) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    await Clipboard.setStringAsync(expQ.data.markdown);
    Alert.alert('已复制', '粘贴到微信/邮件发给医生即可');
  };

  const onSubmit = () => {
    if (!assessment.trim() && !plan.trim() && !summary.trim()) {
      Alert.alert('请至少填一项', '');
      return;
    }
    submitMut.mutate();
  };

  const loading = expQ.isLoading || !expQ.data;
  const refreshing = expQ.isRefetching || fbQ.isRefetching;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.btn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>医生回路</Text>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={
            <RefreshControl refreshing={refreshing}
              onRefresh={() => { expQ.refetch(); fbQ.refetch(); }}
              tintColor={c.brand}
            />
          }
          keyboardShouldPersistTaps="handled"
        >
          {/* 导出卡 */}
          <Text style={txt.section}>给医生看的摘要</Text>
          <View style={styles.card}>
            {loading ? (
              <ActivityIndicator color={c.brand} />
            ) : (
              <>
                <Text style={txt.exportSummary}>
                  涵盖近 {days} 天 · {expQ.data.vitals.samples} 天数据
                  {expQ.data.ai_scorecard.total_graded > 0
                    ? ` · ${expQ.data.ai_scorecard.total_graded} 条 AI 评分`
                    : ''}
                </Text>
                <View style={styles.exportActions}>
                  <TouchableOpacity style={styles.primaryBtn} onPress={onShare} activeOpacity={0.7}>
                    <Ionicons name="share-outline" size={16} color="#fff" />
                    <Text style={txt.primaryBtnText}>分享</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.secondaryBtn} onPress={onCopy} activeOpacity={0.7}>
                    <Ionicons name="copy-outline" size={16} color={c.brand} />
                    <Text style={txt.secondaryBtnText}>复制 Markdown</Text>
                  </TouchableOpacity>
                </View>
                <Text style={txt.preview} numberOfLines={8}>
                  {expQ.data.markdown.slice(0, 400)}
                  {expQ.data.markdown.length > 400 ? '...' : ''}
                </Text>
              </>
            )}
          </View>

          {/* 录入反馈 */}
          <Text style={txt.section}>录入医生反馈</Text>
          <Text style={txt.hint}>就诊后把医生说的关键点记下来 · 会进入你的 Clinical Journal</Text>
          <View style={styles.card}>
            <Text style={txt.label}>就诊主诉 / 背景</Text>
            <TextInput
              style={styles.input}
              value={summary}
              onChangeText={setSummary}
              placeholder="例如: 夜间呼吸暂停疑虑, 准备 PSG..."
              placeholderTextColor={c.labelTertiary}
              multiline
            />
            <Text style={txt.label}>医生评估</Text>
            <TextInput
              style={styles.input}
              value={assessment}
              onChangeText={setAssessment}
              placeholder="例如: 轻度 OSAHS 倾向, AHI 预估 8-12..."
              placeholderTextColor={c.labelTertiary}
              multiline
            />
            <Text style={txt.label}>下一步计划</Text>
            <TextInput
              style={styles.input}
              value={plan}
              onChangeText={setPlan}
              placeholder="例如: 2 周后复查 SpO2 趋势; 改用鼻贴..."
              placeholderTextColor={c.labelTertiary}
              multiline
            />
            <TouchableOpacity
              style={[styles.primaryBtn, styles.submitBtn,
                submitMut.isPending && { opacity: 0.6 }]}
              onPress={onSubmit}
              disabled={submitMut.isPending}
              activeOpacity={0.7}
            >
              {submitMut.isPending
                ? <ActivityIndicator size="small" color="#fff" />
                : <Text style={txt.primaryBtnText}>保存到档案</Text>}
            </TouchableOpacity>
          </View>

          {/* 历史反馈 */}
          {fbQ.data && fbQ.data.length > 0 && (
            <>
              <Text style={txt.section}>历史就诊记录</Text>
              <View style={styles.card}>
                {fbQ.data.map((f, i) => (
                  <View
                    key={f.id}
                    style={[styles.fbRow, i < fbQ.data!.length - 1 && styles.fbRowBorder]}
                  >
                    <Text style={txt.fbDate}>
                      {(f.generated_at || '').slice(0, 10)}
                    </Text>
                    {f.subjective ? <Text style={txt.fbBody}>S: {f.subjective}</Text> : null}
                    {f.assessment ? <Text style={txt.fbBody}>A: {f.assessment}</Text> : null}
                    {f.plan ? <Text style={txt.fbBody}>P: {f.plan}</Text> : null}
                  </View>
                ))}
              </View>
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  btn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg, paddingBottom: 120 },
  card: {
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.md,
    ...shadows.subtle,
  },
  exportActions: {
    flexDirection: 'row', gap: spacing.sm, marginVertical: spacing.md,
  },
  primaryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, backgroundColor: c.brand,
    paddingVertical: 10, paddingHorizontal: 16,
    borderRadius: radii.md, flex: 1,
  },
  secondaryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, backgroundColor: c.brandLight,
    paddingVertical: 10, paddingHorizontal: 16,
    borderRadius: radii.md, flex: 1,
  },
  submitBtn: { marginTop: spacing.sm },
  input: {
    minHeight: 60, backgroundColor: c.fill,
    borderRadius: radii.md, padding: 10,
    color: c.labelPrimary, fontSize: 14,
    marginBottom: spacing.md,
    textAlignVertical: 'top',
  },
  fbRow: { paddingVertical: spacing.sm },
  fbRowBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: c.separator,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: {
    fontSize: 17, fontWeight: '600', color: c.labelPrimary,
    flex: 1, textAlign: 'center',
  } as TextStyle,
  section: {
    fontSize: 13, fontWeight: '500', color: c.labelSecondary,
    marginBottom: spacing.xs, marginTop: spacing.sm, marginLeft: spacing.xs,
  } as TextStyle,
  hint: {
    fontSize: 11, color: c.labelTertiary,
    marginLeft: spacing.xs, marginBottom: spacing.xs,
  } as TextStyle,
  exportSummary: { fontSize: 13, color: c.labelSecondary } as TextStyle,
  primaryBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' } as TextStyle,
  secondaryBtnText: { color: c.brand, fontSize: 14, fontWeight: '600' } as TextStyle,
  preview: {
    fontSize: 11, color: c.labelTertiary, lineHeight: 16,
    backgroundColor: c.fill, padding: 10, borderRadius: radii.sm,
  } as TextStyle,
  label: {
    fontSize: 12, fontWeight: '500', color: c.labelSecondary,
    marginBottom: 4,
  } as TextStyle,
  fbDate: { fontSize: 12, color: c.labelTertiary, marginBottom: 4 } as TextStyle,
  fbBody: { fontSize: 13, color: c.labelPrimary, lineHeight: 19, marginTop: 2 } as TextStyle,
});
