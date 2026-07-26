/**
 * 化验/体检记录列表页 — 解决"上传后没法回看"dead-end.
 *
 * P6 (2026-05-04): 用户已有 16 份化验报告但 mobile 没专门列表页, 上传完看不到.
 * 这个页:
 * - 列出全部化验, 按日期倒序
 * - 每条卡片显示: 日期 + 医院 + 项目数 + 异常项数(红字) + AI overall_assessment 摘要
 * - 点击进入详情 (vs 上次对比, 突出变化最大的指标)
 *
 * NOTE: 上传仍走 chat → Agent OCR 流程.
 * 这里只解决"上传后看得见" 这一断点.
 */
import React, { useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextStyle,
  RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';

import {
  listMedicalExams,
  countAbnormal,
  relativeExamDate,
  type MedicalExam,
} from '../services/medicalExams';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import { createMedicalExamAgentContext, pushChatWithContext } from '../utils/agentContext';

export default function MedicalExamsScreen() {
  const router = useRouter();
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const examsQuery = useQuery({
    queryKey: ['medical-exams'],
    queryFn: () => listMedicalExams(50),
    staleTime: 60_000,
  });

  const exams = examsQuery.data ?? [];
  const latestExam = exams[0] ?? null;
  const refetchExams = examsQuery.refetch;
  const openMedicalImport = useCallback(() => {
    router.push({
      pathname: '/import',
      params: { focus: 'medical' },
    } as any);
  }, [router]);

  useFocusEffect(
    useCallback(() => {
      void refetchExams();
    }, [refetchExams]),
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>体检记录</Text>
        <Pressable
          onPress={openMedicalImport}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel="导入体检报告"
          style={({ pressed }) => [styles.headerImportButton, pressed && { opacity: 0.7 }]}
        >
          <Ionicons name="cloud-upload-outline" size={20} color={c.brand} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={examsQuery.isFetching}
            onRefresh={() => examsQuery.refetch()}
            tintColor={c.brand}
          />
        }
      >
        {examsQuery.isLoading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="small" color={c.brand} />
          </View>
        ) : null}

        {!examsQuery.isLoading && exams.length === 0 ? (
          <View style={styles.emptyWrap}>
            <Ionicons name="document-text-outline" size={36} color={c.labelTertiary} />
            <Text style={txt.empty}>
              还没有化验记录{'\n'}
              上传体检报告 PDF、化验单照片，或粘贴文字结果，AI 会自动识别录入
            </Text>
            <Pressable
              onPress={openMedicalImport}
              accessibilityRole="button"
              accessibilityLabel="导入第一份体检报告"
              style={({ pressed }) => [styles.emptyImportButton, pressed && { opacity: 0.76 }]}
            >
              <Ionicons name="cloud-upload-outline" size={16} color="#fff" />
              <Text style={txt.emptyImportButton}>导入第一份报告</Text>
            </Pressable>
          </View>
        ) : null}

        {latestExam ? (
          <Pressable
            style={({ pressed }) => [styles.agentLink, { borderColor: c.separator }, pressed && { opacity: 0.75 }]}
            onPress={() => pushChatWithContext(router, {
              prompt: '请基于我最新这份体检/化验报告, 解释异常项、风险优先级和未来 30 天该做什么。',
              context: createMedicalExamAgentContext(latestExam),
              badge: `基于 ${latestExam.exam_date} 体检报告`,
            })}
            accessibilityRole="button"
            accessibilityLabel="跟小巴详细聊最新体检报告"
          >
            <Ionicons name="chatbubble-ellipses-outline" size={16} color={c.brand} />
            <Text style={[txt.agentLinkText, { color: c.brand }]}>跟小巴详细聊最新报告</Text>
            <Ionicons name="chevron-forward" size={15} color={c.brand} style={{ marginLeft: 'auto' }} />
          </Pressable>
        ) : null}

        {exams.map((exam, idx) => {
          const previous = exams[idx + 1] ?? null;
          return (
            <ExamCard
              key={exam.id}
              exam={exam}
              previous={previous}
              c={c}
              onPress={() =>
                router.push(`/medical-exam-detail?id=${exam.id}` as any)
              }
            />
          );
        })}

        {/* 顶部统计 — 在底部 footer 减少 hero card 噪声 */}
        {exams.length > 0 ? (
          <Text style={txt.footer}>
            共 {exams.length} 份记录 · 最早 {exams[exams.length - 1]?.exam_date}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

interface ExamCardProps {
  exam: MedicalExam;
  previous: MedicalExam | null;
  c: ColorPalette;
  onPress: () => void;
}

function ExamCard({ exam, previous, c, onPress }: ExamCardProps) {
  const styles = useMemo(() => createStyles(c, false), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const abnormalCount = countAbnormal(exam);
  const itemsCount = exam.items?.length ?? 0;
  const rel = relativeExamDate(exam.exam_date);
  const hospital = (exam.hospital_name || exam.exam_type || '').trim();

  return (
    <Pressable
      style={({ pressed }) => [styles.examCard, pressed && { opacity: 0.7 }]}
      onPress={onPress}
      accessibilityRole="button"
    >
      <View style={styles.examHeader}>
        <View style={{ flex: 1 }}>
          <Text style={txt.examDate}>{exam.exam_date}</Text>
          <Text style={txt.examMeta} numberOfLines={1}>
            {rel}
            {hospital ? ` · ${hospital}` : ''}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
      </View>

      {/* Stat row */}
      <View style={styles.examStats}>
        <View style={styles.examStatPill}>
          <Text style={txt.examStatValue}>{itemsCount}</Text>
          <Text style={txt.examStatLabel}>项</Text>
        </View>
        {abnormalCount > 0 ? (
          <View style={[styles.examStatPill, { backgroundColor: c.tintRed }]}>
            <Ionicons name="alert-circle" size={12} color={c.red} />
            <Text style={[txt.examStatValue, { color: c.red }]}>{abnormalCount}</Text>
            <Text style={[txt.examStatLabel, { color: c.red }]}>异常</Text>
          </View>
        ) : (
          <View style={[styles.examStatPill, { backgroundColor: c.tintGreen }]}>
            <Ionicons name="checkmark-circle" size={12} color={c.green} />
            <Text style={[txt.examStatLabel, { color: c.green }]}>全部正常</Text>
          </View>
        )}
        {previous ? (
          <View style={styles.examStatPill}>
            <Ionicons name="trending-up-outline" size={12} color={c.labelSecondary} />
            <Text style={txt.examStatLabel}>vs 上次</Text>
          </View>
        ) : null}
      </View>

      {exam.overall_assessment ? (
        <Text style={txt.examAssessment} numberOfLines={2}>
          {exam.overall_assessment}
        </Text>
      ) : null}
    </Pressable>
  );
}

function createStyles(c: ColorPalette, _isDark: boolean) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    headerImportButton: {
      width: 34,
      height: 34,
      borderRadius: 17,
      backgroundColor: c.brandLight,
      alignItems: 'center',
      justifyContent: 'center',
    },
    content: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 40 },
    loadingWrap: { paddingVertical: 40, alignItems: 'center' },
    emptyWrap: {
      paddingVertical: 60, paddingHorizontal: 30,
      alignItems: 'center', gap: 12,
    },
    emptyImportButton: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginTop: spacing.sm,
      paddingHorizontal: spacing.lg,
      paddingVertical: 10,
      borderRadius: radii.full,
      backgroundColor: c.brand,
    },
    examCard: {
      backgroundColor: c.bgCard,
      borderRadius: radii.md,
      padding: spacing.lg,
      gap: spacing.sm,
      ...shadows.subtle,
    },
    examHeader: { flexDirection: 'row', alignItems: 'center' },
    examStats: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
    examStatPill: {
      flexDirection: 'row', alignItems: 'center', gap: 3,
      paddingHorizontal: spacing.sm + 2, paddingVertical: 4,
      borderRadius: radii.full,
      backgroundColor: c.bgPrimary,
    },
    agentLink: {
      flexDirection: 'row', alignItems: 'center', gap: 8,
      backgroundColor: c.bgCard,
      borderWidth: StyleSheet.hairlineWidth,
      borderRadius: radii.md,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    examDate: { fontSize: 16, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    examMeta: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
    examStatValue: { fontSize: 13, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    examStatLabel: { fontSize: 11, color: c.labelSecondary } as TextStyle,
    examAssessment: {
      fontSize: 13, color: c.labelSecondary, lineHeight: 19,
      paddingTop: 4,
    } as TextStyle,
    agentLinkText: { fontSize: 14, fontWeight: '600' } as TextStyle,
    empty: {
      fontSize: 13, color: c.labelTertiary, textAlign: 'center', lineHeight: 19,
    } as TextStyle,
    emptyImportButton: { fontSize: 13, fontWeight: '600', color: '#fff' } as TextStyle,
    footer: {
      fontSize: 12, color: c.labelTertiary, textAlign: 'center', paddingTop: 12,
    } as TextStyle,
  };
}
