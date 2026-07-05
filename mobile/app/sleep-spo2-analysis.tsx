// 夜间 SpO2 根因分析页面（P1b Mobile UI）
// 路由: /sleep-spo2-analysis?night_date=YYYY-MM-DD（缺省 = 昨天）
import React, { useMemo, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import SpO2AnalysisChart from '../components/sleep/SpO2AnalysisChart';
import SleepExperimentCard from '../components/sleep/SleepExperimentCard';
import InterventionDraftSheet from '../components/actions/InterventionDraftSheet';
import { useNightAnalysis, useNightTimeseries, useReanalyzeNight, useConfirmNoAlcohol } from '../hooks/useSpo2Analysis';
import { SpO2Correlation } from '../services/sleepSpo2';
import { getSleepQuestionPrompt } from '../services/dataHealth';
import { createInterventionDraft } from '../services/actionCards';
import { buildInterventionDraft, type InterventionDraft } from '../services/interventionDraft';
import { invalidateQueryKeys, queryKeys } from '../applib/queryKeys';
import { spacing } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';
import { createStyles, createTxt } from '../components/sleep/sleepSpo2AnalysisStyles';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createSleepSpo2AgentContext } from '../utils/agentContext';

// 北京时区 (UTC+8) 的 YYYY-MM-DD. 用 toISOString 会被转成 UTC, 早上 8 点前会偏一天.
function todayISOInBeijing(): string {
  const now = new Date();
  const beijingMs = now.getTime() + 8 * 60 * 60 * 1000;
  return new Date(beijingMs).toISOString().slice(0, 10);
}

function shiftISO(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

const SEVERITY_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  alert: { bg: '#FEE2E2', border: '#DC2626', icon: '#B91C1C' },
  warning: { bg: '#FEF3C7', border: '#D97706', icon: '#B45309' },
  info: { bg: '#DBEAFE', border: '#2563EB', icon: '#1E40AF' },
};

const SEVERITY_LABEL: Record<string, string> = {
  alert: '高优先',
  warning: '关注',
  info: '提示',
};

const CATEGORY_ICON: Record<string, any> = {
  medication: 'medical',
  supplement: 'flask',
  exercise: 'fitness',
  diet: 'restaurant',
  environment: 'leaf',
  diagnostic: 'pulse',
};

export default function SleepSpo2AnalysisScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const qc = useQueryClient();
  const params = useLocalSearchParams<{ night_date?: string }>();
  const [selectedDate, setSelectedDate] = useState(params.night_date || todayISOInBeijing());
  const [overlay, setOverlay] = useState<'hr' | 'respiration' | 'none'>('none');
  const [experimentStates, setExperimentStates] = useState<Record<string, 'queued' | 'done' | 'skipped'>>({});
  const [savingExperiment, setSavingExperiment] = useState<string | null>(null);
  const [draftExperiment, setDraftExperiment] = useState<{ action: string; draft: InterventionDraft } | null>(null);

  const analysisQ = useNightAnalysis(selectedDate);
  const tsQ = useNightTimeseries(selectedDate, 'spo2,hr,respiration,sleep_stage');
  const reanalyzeM = useReanalyzeNight();
  const confirmNoAlcoholM = useConfirmNoAlcohol();

  const analysis = analysisQ.data;
  const ts = tsQ.data;

  const isLoading = analysisQ.isLoading || tsQ.isLoading;

  // 日期翻页
  const shift = (days: number) => {
    Haptics.selectionAsync();
    setSelectedDate(shiftISO(selectedDate, days));
  };

  const onRefresh = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    reanalyzeM.mutate(selectedDate);
  };

  const setExperimentState = (action: string, state: 'queued' | 'done' | 'skipped') => {
    setExperimentStates(prev => ({ ...prev, [`${selectedDate}:${action}`]: state }));
  };

  const getExperimentState = (action: string) => experimentStates[`${selectedDate}:${action}`];

  const tryExperimentTonight = (action: string) => {
    Haptics.selectionAsync();
    setDraftExperiment({
      action,
      draft: buildInterventionDraft({
        title: action.length > 18 ? action.slice(0, 18) : action,
        advice: action,
        sourceType: 'sleep_spo2',
        sourceId: selectedDate,
        metricHint: 'spo2_odi',
        verificationDays: 1,
      }),
    });
  };

  const submitExperimentDraft = async (draft: InterventionDraft) => {
    if (!draftExperiment) return;
    setSavingExperiment(draftExperiment.action);
    try {
      await createInterventionDraft(draft);
      await invalidateQueryKeys(qc, [
        queryKeys.actionCards,
        queryKeys.todayCoachRoot,
        queryKeys.agentAgendaRoot,
      ]);
      setExperimentState(draftExperiment.action, 'queued');
      setDraftExperiment(null);
      Alert.alert('已加入行动', '明天可以回到这里复盘 ODI、最低血氧和事件数。');
    } catch {
      Alert.alert('创建失败', '睡眠实验行动保存失败，请稍后重试。');
    } finally {
      setSavingExperiment(null);
    }
  };

  // 规则按 severity 分组
  const grouped = useMemo(() => {
    const out: Record<string, SpO2Correlation[]> = { alert: [], warning: [], info: [] };
    if (!analysis) return out;
    analysis.correlations.forEach((c) => {
      if (!out[c.severity]) out[c.severity] = [];
      out[c.severity].push(c);
    });
    return out;
  }, [analysis]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.btn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>夜间血氧分析</Text>
        <View style={{ flexDirection: 'row' }}>
          <TouchableOpacity
            onPress={() => router.push('/sleep-spo2-longitudinal' as any)}
            style={styles.btn}
            accessibilityLabel="查看 30 天趋势"
          >
            <Ionicons name="stats-chart-outline" size={20} color={c.labelPrimary} />
          </TouchableOpacity>
          <TouchableOpacity onPress={onRefresh} style={styles.btn} disabled={reanalyzeM.isPending}>
            <Ionicons name="refresh" size={22} color={reanalyzeM.isPending ? c.labelTertiary : c.labelPrimary} />
          </TouchableOpacity>
        </View>
      </View>

      {/* 日期选择 */}
      <View style={styles.dateBar}>
        <TouchableOpacity onPress={() => shift(-1)} style={styles.dateBtn}>
          <Ionicons name="chevron-back" size={18} color={c.brand} />
        </TouchableOpacity>
        <Text style={txt.dateLabel}>{selectedDate}</Text>
        <TouchableOpacity
          onPress={() => shift(1)}
          style={styles.dateBtn}
          disabled={selectedDate >= todayISOInBeijing()}
        >
          <Ionicons
            name="chevron-forward"
            size={18}
            color={selectedDate >= todayISOInBeijing() ? c.labelTertiary : c.brand}
          />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={analysisQ.isRefetching} onRefresh={() => analysisQ.refetch()} />}
      >
        {isLoading && !analysis ? (
          <View style={styles.loading}>
            <ActivityIndicator size="large" color={c.brand} />
            <Text style={[txt.body, { marginTop: 12 }]}>加载分析中...</Text>
          </View>
        ) : !analysis ? (
          <View style={styles.loading}>
            <Text style={txt.body}>暂无数据</Text>
          </View>
        ) : (
          <>
            {/* 摘要卡片 */}
            <View style={styles.summary}>
              <SummaryTile
                label="最低 SpO₂"
                value={analysis.min_spo2 != null ? `${analysis.min_spo2.toFixed(0)}%` : '—'}
                color={
                  !analysis.min_spo2 ? c.labelTertiary :
                  analysis.min_spo2 < 85 ? '#DC2626' :
                  analysis.min_spo2 < 88 ? '#D97706' :
                  '#10B981'
                }
              />
              <SummaryTile
                label="ODI"
                value={analysis.odi.toFixed(1)}
                color={
                  analysis.odi >= 15 ? '#DC2626' :
                  analysis.odi >= 5 ? '#D97706' :
                  '#10B981'
                }
                sub="/小时"
              />
              <SummaryTile
                label="氧降事件"
                value={String(analysis.events_count)}
                color={c.labelPrimary}
              />
              <SummaryTile
                label="睡眠"
                value={`${(analysis.total_sleep_minutes / 60).toFixed(1)}h`}
                color={c.labelPrimary}
              />
            </View>

            <AgentFeedbackLink
              label="跟小巴制定今晚睡眠实验"
              accessibilityLabel="跟小巴制定今晚睡眠实验"
              prompt="请基于昨晚夜间血氧和呼吸风险分析, 复盘风险等级与可能诱因, 帮我制定今晚可执行的睡眠实验，并列出需要补充的背景信息和什么时候应咨询医生。不要做医学诊断。"
              context={createSleepSpo2AgentContext(analysis)}
              badge={`夜间血氧 · ${selectedDate}`}
              style={styles.agentLink}
            />

            {/* 图表 */}
            {ts && ts.metrics?.spo2?.length ? (
              <View style={styles.chartCard}>
                <View style={styles.chartHeader}>
                  <Text style={txt.sectionTitle}>夜间时序</Text>
                  <View style={styles.overlayBtns}>
                    <OverlayBtn
                      active={overlay === 'none'}
                      label="仅 SpO₂"
                      onPress={() => setOverlay('none')}
                    />
                    <OverlayBtn
                      active={overlay === 'hr'}
                      label="+ 心率"
                      onPress={() => setOverlay('hr')}
                    />
                    <OverlayBtn
                      active={overlay === 'respiration'}
                      label="+ 呼吸"
                      onPress={() => setOverlay('respiration')}
                    />
                  </View>
                </View>
                <SpO2AnalysisChart
                  spo2Series={ts.metrics.spo2 || []}
                  hrSeries={ts.metrics.hr || []}
                  respirationSeries={ts.metrics.respiration || []}
                  events={analysis.events}
                  sleepStages={ts.sleep_stages || []}
                  showOverlay={overlay}
                  height={240}
                />
              </View>
            ) : null}

            {/* 数据缺口追问 — 当夜有问题但关键数据没录入 */}
            {analysis.ask_questions && analysis.ask_questions.length > 0 ? (
              <View style={styles.askCard}>
                <Text style={txt.askTitle}>❓ 帮我补全这些信息</Text>
                <Text style={txt.askSub}>当夜确认有低氧/事件，但缺关键背景。补一下能让分析更准。</Text>
                {analysis.ask_questions.map((q, i) => {
                  const isAlcohol = q.includes('饮酒');
                  const prompt = getSleepQuestionPrompt(q);
                  return (
                    <View key={i} style={styles.askItem}>
                      <Text style={txt.askText}>{q}</Text>
                      <View style={styles.askBtnRow}>
                        {isAlcohol ? (
                          <TouchableOpacity
                            style={[styles.askChip, styles.askChipPrimary]}
                            onPress={() => {
                              Haptics.selectionAsync();
                              confirmNoAlcoholM.mutate(selectedDate);
                            }}
                            disabled={confirmNoAlcoholM.isPending}
                            activeOpacity={0.7}
                          >
                            <Text style={txt.askChipPrimary}>没喝</Text>
                          </TouchableOpacity>
                        ) : null}
                        <TouchableOpacity
                          style={styles.askChip}
                          onPress={() => {
                            router.push(prompt.route as any);
                          }}
                          activeOpacity={0.7}
                        >
                          <Text style={txt.askChipSecondary}>
                            {prompt.label} →
                          </Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : null}

            {/* 今晚可试 — action priorities */}
            {analysis.action_priorities.length > 0 ? (
              <View style={styles.actionCard}>
                <Text style={txt.sectionTitle}>✨ 今晚可试</Text>
                {analysis.action_priorities.map((a, i) => (
                  <SleepExperimentCard
                    key={`${a}-${i}`}
                    index={i}
                    action={a}
                    state={getExperimentState(a)}
                    isSaving={savingExperiment === a}
                    onTryTonight={() => tryExperimentTonight(a)}
                    onDone={() => {
                      Haptics.selectionAsync();
                      setExperimentState(a, 'done');
                    }}
                    onSkip={() => {
                      Haptics.selectionAsync();
                      setExperimentState(a, 'skipped');
                    }}
                  />
                ))}
              </View>
            ) : null}

            {/* 根因假设（按严重度分组）*/}
            {['alert', 'warning', 'info'].map((sev) => {
              const items = grouped[sev] || [];
              if (!items.length) return null;
              const sc = SEVERITY_COLORS[sev];
              return (
                <View key={sev} style={{ marginBottom: spacing.lg }}>
                  <Text style={[txt.sectionTitle, { marginBottom: 8 }]}>
                    {SEVERITY_LABEL[sev]} · {items.length}
                  </Text>
                  {items.map((c) => (
                    <View
                      key={c.rule}
                      style={[styles.findingCard, { backgroundColor: sc.bg, borderLeftColor: sc.border }]}
                    >
                      <View style={styles.findingHeader}>
                        <Ionicons
                          name={CATEGORY_ICON[c.category] || 'alert-circle'}
                          size={16}
                          color={sc.icon}
                        />
                        <Text style={[txt.findingSubject, { color: sc.icon }]}>
                          {c.subject}
                        </Text>
                        <Text style={txt.confidence}>{c.confidence}</Text>
                      </View>
                      <Text style={txt.hypothesis}>{c.hypothesis}</Text>
                      <Text style={[txt.action, { color: sc.border }]}>
                        → {c.suggested_action}
                      </Text>
                    </View>
                  ))}
                </View>
              );
            })}

            {analysis.correlations.length === 0 ? (
              <View style={styles.noFindings}>
                <Ionicons name="checkmark-circle" size={40} color={c.green} />
                <Text style={[txt.body, { marginTop: 8 }]}>本夜无规则触发</Text>
                <Text style={[txt.caption, { marginTop: 4, textAlign: 'center' }]}>
                  继续记录用药时间、运动、饮食，规则会给出更针对的建议
                </Text>
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
      <InterventionDraftSheet
        visible={!!draftExperiment}
        draft={draftExperiment?.draft ?? null}
        isSaving={!!savingExperiment}
        onClose={() => setDraftExperiment(null)}
        onSubmit={submitExperimentDraft}
      />
    </SafeAreaView>
  );
}

function SummaryTile({
  label,
  value,
  color,
  sub,
}: {
  label: string;
  value: string;
  color: string;
  sub?: string;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <View style={styles.sumTile}>
      <Text style={txt.sumLabel}>{label}</Text>
      <Text style={[txt.sumValue, { color }]}>{value}{sub ? <Text style={txt.sumSub}>{sub}</Text> : null}</Text>
    </View>
  );
}

function OverlayBtn({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[styles.overlayBtn, active && styles.overlayBtnActive]}
    >
      <Text style={[txt.overlayBtn, active && txt.overlayBtnActive]}>{label}</Text>
    </TouchableOpacity>
  );
}
