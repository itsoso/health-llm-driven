/**
 * /connection-checkin —— 社会连接自评(消费后端 GET/POST /chronic/connection,PR #150)。
 *
 * UCLA-3 三题(各 1-3 分,合成 3-9)+ 两个开关(有无密友 / 稳定群体)→ 提交。
 * 展示上次结果 + interpretation + due 提示。非诊断。
 */
import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import {
  getConnectionStatus,
  submitConnectionCheckin,
  ucla3Total,
  type ConnectionStatus,
} from '../services/chronicHealth';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

// UCLA-3 量表(Hughes 2004 三题版),各 1-3 分。1=几乎不/很少,3=经常。
const UCLA_QUESTIONS = [
  '你多久会感到缺少陪伴?',
  '你多久会感到被冷落?',
  '你多久会感到与他人隔绝、孤立?',
];
const SCALE = [
  { value: 1, label: '几乎没有' },
  { value: 2, label: '有时' },
  { value: 3, label: '经常' },
];

function LastResult({ status }: { status: ConnectionStatus }) {
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  if (!status.has_checkin) return null;
  const highLonely = (status.ucla_score ?? 0) >= 6;
  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.lastHeader}>
        <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>上次自评</Text>
        {status.last_date ? (
          <Text style={[styles.lastDate, { color: c.labelTertiary }]}>{status.last_date}</Text>
        ) : null}
      </View>
      {status.ucla_score != null && (
        <View style={styles.metricRow}>
          <Text style={[styles.metricLabel, { color: c.labelSecondary }]}>UCLA-3 孤独评分</Text>
          <Text
            style={[styles.metricValue, { color: highLonely ? s.warning.solid : c.labelPrimary }]}
          >
            {status.ucla_score} / 9
          </Text>
        </View>
      )}
      <Text style={[styles.interp, { color: c.labelSecondary }]}>{status.interpretation}</Text>
    </View>
  );
}

export default function ConnectionCheckinScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['connection-status'],
    queryFn: getConnectionStatus,
    staleTime: 5 * 60 * 1000,
  });

  const [answers, setAnswers] = useState<(number | null)[]>([null, null, null]);
  const [hasConfidant, setHasConfidant] = useState(true);
  const [inStableGroup, setInStableGroup] = useState(true);

  const allAnswered = answers.every((a) => a != null);

  const mutation = useMutation({
    mutationFn: () =>
      submitConnectionCheckin({
        ucla_score: ucla3Total(answers[0]!, answers[1]!, answers[2]!),
        has_confidant: hasConfidant,
        in_stable_group: inStableGroup,
      }),
    onSuccess: (res) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.setQueryData(['connection-status'], res.status);
      qc.invalidateQueries({ queryKey: ['connection-status'] });
      setAnswers([null, null, null]);
      Alert.alert('已记录', '社会连接自评已保存。', [{ text: '好' }]);
    },
    onError: () => Alert.alert('提交失败', '请稍后再试。'),
  });

  const header = (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} hitSlop={10} accessibilityLabel="返回">
        <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
      </TouchableOpacity>
      <Text style={[styles.title, { color: c.labelPrimary }]}>社会连接自评</Text>
      <View style={{ width: 24 }} />
    </View>
  );

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      {header}

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        {isLoading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={c.labelTertiary} />
        ) : (
          <>
            {data?.due && (
              <View style={[styles.dueBox, { backgroundColor: s.info.bg }]}>
                <Ionicons name="time-outline" size={16} color={s.info.fg} />
                <Text style={[styles.dueText, { color: s.info.fg }]}>
                  {data.has_checkin
                    ? `距上次自评已 ${data.days_since ?? 0} 天,建议再做一次(每季度一次即可)。`
                    : '关系质量是长期健康最强的单一预测因子,花 1 分钟做一次自评。'}
                </Text>
              </View>
            )}

            {data ? <LastResult status={data} /> : null}

            {/* UCLA-3 三题 */}
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>
                过去这段时间,你多久有以下感受?
              </Text>
              {UCLA_QUESTIONS.map((q, qi) => (
                <View key={qi} style={styles.question}>
                  <Text style={[styles.questionText, { color: c.labelPrimary }]}>{q}</Text>
                  <View style={styles.scaleRow}>
                    {SCALE.map((opt) => {
                      const active = answers[qi] === opt.value;
                      return (
                        <TouchableOpacity
                          key={opt.value}
                          style={[
                            styles.scaleBtn,
                            {
                              backgroundColor: active ? c.brand : c.bgPrimary,
                              borderColor: active ? c.brand : c.separator,
                            },
                          ]}
                          activeOpacity={0.7}
                          accessibilityRole="radio"
                          accessibilityState={{ selected: active }}
                          accessibilityLabel={opt.label}
                          onPress={() => {
                            Haptics.selectionAsync();
                            setAnswers((prev) => {
                              const next = [...prev];
                              next[qi] = opt.value;
                              return next;
                            });
                          }}
                        >
                          <Text
                            style={[
                              styles.scaleLabel,
                              { color: active ? '#fff' : c.labelSecondary },
                            ]}
                          >
                            {opt.label}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              ))}
            </View>

            {/* 连接结构两个开关 */}
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.switchRow}>
                <View style={{ flex: 1, paddingRight: 12 }}>
                  <Text style={[styles.switchLabel, { color: c.labelPrimary }]}>有可吐露心事的人</Text>
                  <Text style={[styles.switchHint, { color: c.labelTertiary }]}>
                    至少一个能袒露脆弱、深度信任的人
                  </Text>
                </View>
                <Switch
                  value={hasConfidant}
                  onValueChange={setHasConfidant}
                  trackColor={{ false: c.separator, true: c.brand }}
                  thumbColor="#fff"
                />
              </View>
              <View style={[styles.switchRow, styles.switchRowBorder, { borderTopColor: c.separator }]}>
                <View style={{ flex: 1, paddingRight: 12 }}>
                  <Text style={[styles.switchLabel, { color: c.labelPrimary }]}>有稳定的群体归属</Text>
                  <Text style={[styles.switchHint, { color: c.labelTertiary }]}>
                    长期、定期参与的群体(同事/球队/社群等)
                  </Text>
                </View>
                <Switch
                  value={inStableGroup}
                  onValueChange={setInStableGroup}
                  trackColor={{ false: c.separator, true: c.brand }}
                  thumbColor="#fff"
                />
              </View>
            </View>

            <TouchableOpacity
              style={[
                styles.submitBtn,
                { backgroundColor: allAnswered ? c.brand : c.separator },
              ]}
              activeOpacity={0.8}
              disabled={!allAnswered || mutation.isPending}
              onPress={() => mutation.mutate()}
            >
              {mutation.isPending ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.submitText}>{allAnswered ? '提交自评' : '请先回答三题'}</Text>
              )}
            </TouchableOpacity>

            <Text style={[styles.footer, { color: c.labelTertiary }]}>
              自评用于了解社会连接,非诊断。如长期感到孤独或情绪困扰,建议与信任的人或专业人士聊聊。
            </Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) =>
  StyleSheet.create({
    safe: { flex: 1 },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    title: { fontSize: 17, fontWeight: '700' },
    content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },
    card: { borderRadius: radii.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.md, gap: 12 },
    cardTitle: { fontSize: 15, fontWeight: '800' },
    dueBox: {
      flexDirection: 'row',
      gap: 8,
      alignItems: 'flex-start',
      borderRadius: radii.md,
      paddingHorizontal: 12,
      paddingVertical: 10,
    },
    dueText: { fontSize: 13, lineHeight: 19, flex: 1 },
    lastHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    lastDate: { fontSize: 12, fontWeight: '500' },
    metricRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    metricLabel: { fontSize: 14, fontWeight: '500' },
    metricValue: { fontSize: 16, fontWeight: '800' },
    interp: { fontSize: 13, lineHeight: 19 },
    question: { gap: 8 },
    questionText: { fontSize: 14, fontWeight: '600', lineHeight: 20 },
    scaleRow: { flexDirection: 'row', gap: 8 },
    scaleBtn: {
      flex: 1,
      paddingVertical: 10,
      borderRadius: radii.md,
      borderWidth: StyleSheet.hairlineWidth,
      alignItems: 'center',
    },
    scaleLabel: { fontSize: 13, fontWeight: '600' },
    switchRow: { flexDirection: 'row', alignItems: 'center' },
    switchRowBorder: { borderTopWidth: StyleSheet.hairlineWidth, paddingTop: 12 },
    switchLabel: { fontSize: 15, fontWeight: '600' },
    switchHint: { fontSize: 12, lineHeight: 17, marginTop: 2 },
    submitBtn: {
      borderRadius: radii.lg,
      paddingVertical: 15,
      alignItems: 'center',
      marginTop: spacing.sm,
    },
    submitText: { color: '#fff', fontSize: 16, fontWeight: '700' },
    footer: { fontSize: 12, textAlign: 'center', lineHeight: 18, marginTop: spacing.sm },
  });
