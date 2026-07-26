/**
 * /weekly-briefing —— 本周 AI 给你的 3-5 件事 (Mobile, 2026-05-14).
 *
 * 跟 web 版同语义, 走 GET /me/weekly-briefing, POST /trigger 手动生成.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, RefreshControl, ScrollView, StyleSheet,
  Text, TouchableOpacity, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import api from '../services/api';
import { spacing, radii } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';
import EvidenceChip from '../components/shared/EvidenceChip';
import MarkdownText from '../components/shared/MarkdownText';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createWeeklyBriefingAgentContext } from '../utils/agentContext';

interface BriefingCard {
  id: number;
  title: string;
  content: string;
  metric_key: string | null;
  baseline_value: string | null;
  target_value: string | null;
  actual_value: string | null;
  verification_days: number | null;
  evidence_level: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  outcome: string | null;
  status: string | null;
  user_decision: string | null;
  created_at: string | null;
  completed_at: string | null;
  graded_at: string | null;
}

interface BriefingResponse {
  week_start: string;
  primary_goal: string | null;
  cards: BriefingCard[];
  stats: { total: number; accepted: number; completed: number; improved: number };
  last_run_at: string | null;
  can_trigger: boolean;
}

const GOAL_LABEL: Record<string, string> = {
  weight_loss: '减肥/控重', glucose: '降血糖', blood_pressure: '降血压',
  sleep: '改善睡眠', hrv: '提升 HRV', rhinitis: '管理鼻炎', general: '总体健康',
};

const METRIC_LABEL: Record<string, string> = {
  ldl: 'LDL', hdl: 'HDL', hba1c: '糖化', tg: 'TG',
  systolic_bp: '收缩压', sbp: '收缩压', dbp: '舒张压', bp: '血压',
  weight: '体重', bmi: 'BMI', hrv: 'HRV', rhr: '静息心率',
  sleep_score: '睡眠', spo2: 'SpO2', spo2_odi: 'ODI',
  hcy: '同型半胱氨酸', vitamin_d: '维 D', b12: 'B12',
};

export default function WeeklyBriefingScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const [data, setData] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get<BriefingResponse>('/me/weekly-briefing');
      setData(r.data);
    } catch (e: any) {
      Alert.alert('加载失败', e?.response?.data?.detail || e?.message || '请稍后再试');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
  }, []);

  const onRefresh = () => { setRefreshing(true); load(); };

  const trigger = async () => {
    setTriggering(true);
    try {
      const r = await api.post<{ queued: boolean; reason?: string }>('/me/weekly-briefing/trigger');
      if (r.data.queued) {
        Alert.alert('AI 正在生成', '约 30 秒后回来下拉刷新');
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = setTimeout(() => {
          refreshTimerRef.current = null;
          void load();
        }, 35000);
      } else {
        Alert.alert('已有建议', r.data.reason || '本周已有 AI 建议');
        load();
      }
    } catch (e: any) {
      Alert.alert('触发失败', e?.response?.data?.detail || e?.message || '请稍后再试');
    } finally {
      setTriggering(false);
    }
  };

  if (loading && !data) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: c.bgPrimary }]} edges={['top']}>
        <ActivityIndicator color={c.brand} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top', 'bottom']}>
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
          <Text style={[styles.backText, { color: c.labelPrimary }]}>返回</Text>
        </TouchableOpacity>
        <Text style={[styles.topTitle, { color: c.labelPrimary }]}>本周建议</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.brand} />}
      >
        {data && (
          <>
            {/* 主目标 chip */}
            {data.primary_goal && (
              <View style={[styles.goalChip, { backgroundColor: c.tintBlue, borderColor: c.blue + '40' }]}>
                <Text style={{ fontSize: 16 }}>🎯</Text>
                <Text style={[styles.goalText, { color: c.blue }]}>
                  当前主目标 · {GOAL_LABEL[data.primary_goal] || data.primary_goal}
                </Text>
              </View>
            )}

            <AgentFeedbackLink
              label="跟小巴复盘本周建议"
              accessibilityLabel="跟小巴复盘本周建议"
              prompt="请基于本周建议和执行状态，帮我判断哪些该保留、哪些要调整或放弃，并整理下周最重要的 3 个行动。"
              context={createWeeklyBriefingAgentContext(data as any)}
              badge={`本周建议 ${data.stats.total} 条`}
            />

            {data.cards.length === 0 ? (
              <View style={[styles.emptyCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                <Text style={{ fontSize: 32, textAlign: 'center', marginBottom: 8 }}>📅</Text>
                <Text style={[styles.emptyTitle, { color: c.labelPrimary }]}>本周还没有 AI 建议</Text>
                <Text style={[styles.emptySub, { color: c.labelTertiary }]}>
                  系统每周日 21:07 自动生成 3-5 条本周可执行建议.{'\n'}
                  现在可以手动触发一次, AI 会基于你的基因 / 化验 / 主目标给方案.
                </Text>
                {data.can_trigger && (
                  <TouchableOpacity
                    onPress={trigger}
                    disabled={triggering}
                    style={[styles.triggerBtn, { backgroundColor: c.brand }]}
                  >
                    {triggering ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.triggerText}>现在生成本周建议</Text>
                    )}
                  </TouchableOpacity>
                )}
              </View>
            ) : (
              <>
                {/* stats grid */}
                <View style={styles.statsRow}>
                  <Stat label="本周" value={data.stats.total} color={c.labelPrimary} c={c} />
                  <Stat label="已接受" value={data.stats.accepted} color={c.blue} c={c} />
                  <Stat label="已完成" value={data.stats.completed} color={c.purple} c={c} />
                  <Stat label="已改善" value={data.stats.improved} color={c.green} c={c} />
                </View>

                {/* cards */}
                {data.cards.map(card => (
                  <TouchableOpacity
                    key={card.id}
                    style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}
                    onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
                  >
                    <View style={styles.cardHead}>
                      <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>{card.title}</Text>
                      <EvidenceChip level={card.evidence_level} />
                    </View>
                    <MarkdownText>{card.content}</MarkdownText>
                    {card.metric_key && card.baseline_value && (
                      <View style={[styles.metricBlock, { backgroundColor: c.fill }]}>
                        <Text style={[styles.metricLabel, { color: c.labelTertiary }]}>
                          {METRIC_LABEL[card.metric_key] || card.metric_key}
                        </Text>
                        <Text style={[styles.metricVal, { color: c.labelSecondary }]}>{card.baseline_value}</Text>
                        {card.target_value && (
                          <>
                            <Text style={[styles.metricArrow, { color: c.labelTertiary }]}>→</Text>
                            <Text style={[styles.metricTarget, { color: c.green }]}>{card.target_value}</Text>
                          </>
                        )}
                        {card.actual_value && (
                          <>
                            <Text style={[styles.metricLabel, { color: c.labelTertiary }]}>实测</Text>
                            <Text style={[styles.metricTarget, { color: c.orange }]}>{card.actual_value}</Text>
                          </>
                        )}
                        {card.verification_days != null && (
                          <Text style={[styles.metricLabel, { color: c.labelTertiary }]}>
                            ({card.verification_days} 天)
                          </Text>
                        )}
                      </View>
                    )}
                  </TouchableOpacity>
                ))}
              </>
            )}

            {data.last_run_at && (
              <Text style={[styles.footer, { color: c.labelTertiary }]}>
                生成于 {new Date(data.last_run_at).toLocaleString('zh-CN')}
              </Text>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value, color, c }: { label: string; value: number; color: string; c: any }) {
  return (
    <View style={[styles.statTile, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <Text style={[styles.statValue, { color, fontVariant: ['tabular-nums'] }]}>{value}</Text>
      <Text style={[styles.statLabel, { color: c.labelTertiary }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  topBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: 8 },
  backBtn: { flexDirection: 'row', alignItems: 'center', minWidth: 60 },
  backText: { fontSize: 16, marginLeft: -2 },
  topTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '600' },
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  goalChip: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 6,
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14, borderWidth: 1,
  },
  goalText: { fontSize: 12, fontWeight: '500' },
  emptyCard: {
    borderWidth: 1, borderRadius: radii.md, padding: spacing.lg,
    alignItems: 'center', gap: 6,
  },
  emptyTitle: { fontSize: 16, fontWeight: '600', textAlign: 'center' },
  emptySub: { fontSize: 13, textAlign: 'center', lineHeight: 19, marginTop: 4, marginBottom: 12 },
  triggerBtn: { paddingHorizontal: 20, paddingVertical: 12, borderRadius: radii.md, marginTop: 8 },
  triggerText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  statsRow: { flexDirection: 'row', gap: spacing.sm },
  statTile: { flex: 1, borderWidth: 1, borderRadius: radii.md, padding: spacing.sm, alignItems: 'center' },
  statValue: { fontSize: 20, fontWeight: '700' },
  statLabel: { fontSize: 11, marginTop: 2 },
  card: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 6 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  cardTitle: { flex: 1, fontSize: 16, fontWeight: '600' },
  metricBlock: {
    flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6,
    borderRadius: radii.sm, paddingHorizontal: 10, paddingVertical: 6, marginTop: 4,
  },
  metricLabel: { fontSize: 11 },
  metricVal: { fontSize: 13, fontVariant: ['tabular-nums'] },
  metricArrow: { fontSize: 11 },
  metricTarget: { fontSize: 13, fontWeight: '700', fontVariant: ['tabular-nums'] },
  footer: { fontSize: 11, textAlign: 'center', marginTop: spacing.lg },
});
