/**
 * /guided-task —— 引导式运动执行屏(Reva R17 任务线/JITAI 执行层 · phone-first 第一刀)。
 *
 * 从「今日时间线」运动项点「开始」进入(?domain=strength)。守 R17 裁决③「降摩擦不劫持」:
 * 不自动打开,用户主动点「开始」才进;给「现在做 / 晚点 / 今天跳过(带原因)」三个出口。
 *
 * 结构:门控状态(裁决①可见性,系统替你判断)→ 动作卡(要领/禁忌/证据)→ 计划 →
 *       引导执行(语音 expo-speech 念 cue + 震动节拍)→ 完成(RPE + 写回 + 肯定反馈)。
 * 展示层子组件与样式拆到 components/movement/GuidedTaskViews.tsx(守 ≤500 行预算)。
 *
 * 内容全部来自后端循证库(useGuidedTask),前端不写死动作要领。
 *
 * 语音:走 expo-speech(已在 package.json,无需 build)。Speech.speak() 中文 zh-CN 念当前步。
 *       —— 若未来要换 native TTS 才需 build;当前 v1 不引入新 native 依赖。
 */
import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import * as Speech from 'expo-speech';

import { useTheme } from '../hooks/useTheme';
import { useGuidedTask, useCompleteAgendaItem } from '../hooks/useGuidedTask';
import type { AgendaSource } from '../services/agenda';
import {
  createStyles,
  DoneView,
  ExerciseCard,
  GateBanner,
  GuideStepper,
  Header,
  NotSyncedView,
  PlanCard,
  RpeAndComplete,
  SafetyFooter,
  SkipPicker,
} from '../components/movement/GuidedTaskViews';

const TIMELINE_TODAY_KEY = ['timeline', 'today'];

export default function GuidedTaskScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const qc = useQueryClient();
  const styles = useMemo(() => createStyles(c), [c]);

  const params = useLocalSearchParams<{
    domain?: string;
    completeType?: string;
    completeId?: string;
  }>();
  const domain = (params.domain ?? 'movement').toString();
  // 时间线把运动项的 complete_ref 透传过来 → 有则走 /agenda/complete 双轨写回。
  const completeRef: AgendaSource | null =
    params.completeType && params.completeId
      ? { object_type: String(params.completeType), object_id: Number(params.completeId) }
      : null;

  const { data, isLoading, isError, refetch } = useGuidedTask(domain);
  const complete = useCompleteAgendaItem();

  const [stepIdx, setStepIdx] = useState(0);
  const [rpe, setRpe] = useState<number | null>(null);
  const [showSkip, setShowSkip] = useState(false);
  const [done, setDone] = useState(false);
  // 无 complete_ref 时进入「未同步」诚实终态(不是成功态)。
  const [notSynced, setNotSynced] = useState(false);
  // action-lock:防双击,完成请求在途时锁住按钮。
  const submitting = useRef(false);
  const [submittingState, setSubmittingState] = useState(false);

  const speak = useCallback((line: string) => {
    Speech.stop();
    Speech.speak(line, { language: 'zh-CN' });
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
  }, []);

  const onStep = useCallback(
    (idx: number, script: string[]) => {
      const clamped = Math.max(0, Math.min(idx, script.length - 1));
      setStepIdx(clamped);
      speak(script[clamped]);
    },
    [speak],
  );

  const finishWriteback = useCallback(() => {
    Speech.stop();
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    setDone(true);
    submitting.current = false;
    setSubmittingState(false);
  }, []);

  const onComplete = useCallback(() => {
    if (submitting.current) return; // action-lock
    submitting.current = true;
    setSubmittingState(true);

    if (completeRef) {
      // 有 complete_ref → 走协议轨写真实记录,失败不静默。
      complete.mutate(completeRef, {
        onSuccess: finishWriteback,
        onError: () => {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
          Alert.alert('完成失败', '没有保存成功,请稍后重试。');
          submitting.current = false;
          setSubmittingState(false);
        },
      });
    } else {
      // v1 无 complete_ref → 这次没有任何记录写回后端。不能假装成功(Rule#1):
      // 进「未同步」诚实终态,只 invalidate 时间线,不显示「已记录」。
      Speech.stop();
      qc.invalidateQueries({ queryKey: TIMELINE_TODAY_KEY }).catch(() => {});
      setNotSynced(true);
      submitting.current = false;
      setSubmittingState(false);
    }
  }, [completeRef, complete, finishWriteback, qc]);

  const onSkip = useCallback(() => {
    // v1 仅本地记录原因 + 关屏(后端原因驱动自纠偏后续接);轻震动反馈。
    Speech.stop();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    qc.invalidateQueries({ queryKey: TIMELINE_TODAY_KEY }).catch(() => {});
    router.back();
  }, [qc, router]);

  const onLater = useCallback(() => {
    Speech.stop();
    router.back();
  }, [router]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <Header title={data?.title ?? '引导执行'} onClose={onLater} styles={styles} c={c} />

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={c.brand} />
        </View>
      ) : isError || !data ? (
        <View style={styles.center}>
          <Text style={styles.errText}>没能加载这次的引导任务</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={() => refetch()}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : notSynced ? (
        <NotSyncedView styles={styles} c={c} onClose={onLater} />
      ) : done ? (
        <DoneView styles={styles} s={s} onClose={onLater} />
      ) : (
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <GateBanner task={data} styles={styles} s={s} />
          <ExerciseCard task={data} styles={styles} c={c} s={s} />
          <PlanCard task={data} styles={styles} c={c} />
          <GuideStepper task={data} stepIdx={stepIdx} onStep={onStep} styles={styles} c={c} s={s} />
          {showSkip ? (
            <SkipPicker onPick={onSkip} onCancel={() => setShowSkip(false)} styles={styles} c={c} />
          ) : (
            <RpeAndComplete
              task={data}
              rpe={rpe}
              setRpe={setRpe}
              submitting={submittingState}
              onComplete={onComplete}
              onLater={onLater}
              onSkip={() => setShowSkip(true)}
              styles={styles}
              c={c}
              s={s}
            />
          )}
          <SafetyFooter styles={styles} c={c} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
