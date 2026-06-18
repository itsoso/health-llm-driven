import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';

import {
  closeRokidCustomView,
  openRokidCustomView,
  updateRokidCustomView,
} from '../modules/rokid-bridge';
import { invalidateRecordMutation } from '../applib/queryKeys';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import api from '../services/api';
import {
  buildPushupExercisePayload,
  createPushupCoachState,
  createRokidPushupCoachCustomViewLayout,
  updatePushupCoach,
  type PushupCoachState,
  type PushupPoseSample,
} from '../services/pushupCoach';

type RokidSessionState = 'idle' | 'opening' | 'opened' | 'failed';
type SaveState = 'idle' | 'saving' | 'saved' | 'failed';

function readResultOk(result: Record<string, unknown>) {
  return result.ok !== false;
}

export default function RokidPushupCoachScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [coach, setCoach] = useState<PushupCoachState>(() => createPushupCoachState({ targetReps: 20 }));
  const [sessionState, setSessionState] = useState<RokidSessionState>('idle');
  const [sessionMessage, setSessionMessage] = useState('');
  const [saveState, setSaveState] = useState<SaveState>('idle');

  const pushViewToGlasses = useCallback(async (nextCoach: PushupCoachState, force = false) => {
    if (!force && sessionState !== 'opened') {
      return;
    }
    try {
      const result = force
        ? await openRokidCustomView(createRokidPushupCoachCustomViewLayout(nextCoach))
        : await updateRokidCustomView(createRokidPushupCoachCustomViewLayout(nextCoach));
      if (!readResultOk(result)) {
        throw new Error(typeof result.reason === 'string' ? result.reason : 'rokid_custom_view_failed');
      }
      if (force) {
        setSessionState('opened');
        setSessionMessage('眼镜计数视图已打开');
      }
    } catch (error) {
      setSessionState('failed');
      setSessionMessage(error instanceof Error ? error.message : 'rokid_custom_view_failed');
    }
  }, [sessionState]);

  const applyPoseSample = useCallback((sample: PushupPoseSample) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setCoach((prev) => {
      const next = updatePushupCoach(prev, sample);
      void pushViewToGlasses(next);
      return next;
    });
  }, [pushViewToGlasses]);

  const openCoachView = useCallback(async () => {
    setSessionState('opening');
    setSessionMessage('正在打开眼镜计数视图...');
    await pushViewToGlasses(coach, true);
  }, [coach, pushViewToGlasses]);

  const closeCoachView = useCallback(async () => {
    try {
      await closeRokidCustomView(createRokidPushupCoachCustomViewLayout(coach));
    } catch {
      // Best effort close; the mobile session can still reset locally.
    }
    setSessionState('idle');
    setSessionMessage('眼镜计数视图已关闭');
  }, [coach]);

  const resetSession = useCallback(() => {
    const next = createPushupCoachState({ targetReps: coach.targetReps });
    setCoach(next);
    setSaveState('idle');
    void pushViewToGlasses(next);
  }, [coach.targetReps, pushViewToGlasses]);

  const addFullRep = useCallback(() => {
    const now = Date.now();
    setCoach((prev) => {
      const ready = updatePushupCoach(prev, {
        timestampMs: now,
        elbowAngleDeg: 170,
        shoulderHipAnkleAngleDeg: 176,
        visibility: 0.94,
      });
      const down = updatePushupCoach(ready, {
        timestampMs: now + 450,
        elbowAngleDeg: 84,
        shoulderHipAnkleAngleDeg: 174,
        visibility: 0.94,
      });
      const up = updatePushupCoach(down, {
        timestampMs: now + 1250,
        elbowAngleDeg: 166,
        shoulderHipAnkleAngleDeg: 175,
        visibility: 0.94,
      });
      void pushViewToGlasses(up);
      return up;
    });
  }, [pushViewToGlasses]);

  const saveExercise = useCallback(async () => {
    if (coach.reps <= 0) {
      Alert.alert('还没有计数', '完成至少 1 个俯卧撑后再保存本组。');
      return;
    }
    setSaveState('saving');
    try {
      const payload = buildPushupExercisePayload(coach);
      await api.post('/daily-health/exercise', {
        record_date: payload.record_date,
        exercise_type: payload.exercise_type,
        reps: payload.reps,
        sets: payload.sets,
        intensity: payload.intensity,
        notes: payload.notes,
      });
      await invalidateRecordMutation(qc);
      setSaveState('saved');
      const savedCoach: PushupCoachState = {
        ...coach,
        feedback: `已保存 ${coach.reps} 个俯卧撑。`,
        suggestion: '休息后再决定是否追加一组, 不需要硬撑。',
      };
      setCoach(savedCoach);
      void pushViewToGlasses(savedCoach);
    } catch (error) {
      setSaveState('failed');
      Alert.alert('保存失败', error instanceof Error ? error.message : '俯卧撑记录保存失败。');
    }
  }, [coach, pushViewToGlasses, qc]);

  const progress = Math.min(coach.reps / coach.targetReps, 1);
  const sessionTone = sessionState === 'opened'
    ? s.success.solid
    : sessionState === 'failed'
      ? s.warning.solid
      : c.labelSecondary;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="返回"
          hitSlop={10}
        >
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>Rokid 俯卧撑计数</Text>
        <Pressable
          onPress={resetSession}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="重置俯卧撑计数"
          hitSlop={10}
        >
          <Ionicons name="refresh" size={20} color={c.labelSecondary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.heroPanel}>
          <View style={styles.heroTop}>
            <View style={styles.heroIcon}>
              <Ionicons name="body-outline" size={24} color={c.orange} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={txt.heroKicker}>本组目标</Text>
              <Text style={txt.heroTitle}>{coach.targetReps} 个标准俯卧撑</Text>
            </View>
          </View>

          <View style={styles.countRow}>
            <Text style={txt.count}>{coach.reps}</Text>
            <Text style={txt.countTotal}>/ {coach.targetReps}</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
          </View>
          <Text style={txt.feedback}>{coach.feedback}</Text>
          <Text style={txt.suggestion}>{coach.suggestion}</Text>
        </View>

        <View style={styles.panel}>
          <View style={styles.sectionHeader}>
            <Text style={txt.sectionTitle}>眼镜显示</Text>
            <Text style={[txt.sessionState, { color: sessionTone }]}>
              {sessionState === 'opened' ? '已打开' : sessionState === 'opening' ? '打开中' : '未打开'}
            </Text>
          </View>
          <View style={styles.buttonRow}>
            <Pressable
              onPress={openCoachView}
              disabled={sessionState === 'opening'}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
                sessionState === 'opening' && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="browsers-outline" size={17} color="#fff" />
              <Text style={txt.primaryButton}>{sessionState === 'opening' ? '打开中...' : '打开眼镜视图'}</Text>
            </Pressable>
            <Pressable
              onPress={closeCoachView}
              disabled={sessionState !== 'opened'}
              style={({ pressed }) => [
                styles.secondaryButton,
                pressed && styles.pressed,
                sessionState !== 'opened' && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="close-circle-outline" size={16} color={c.brand} />
              <Text style={txt.secondaryButton}>关闭</Text>
            </Pressable>
          </View>
          {sessionMessage ? <Text style={txt.sessionMessage}>{sessionMessage}</Text> : null}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>姿态采样</Text>
          <View style={styles.sampleGrid}>
            <PoseButton
              label="下放"
              icon="arrow-down-outline"
              color={c.orange}
              onPress={() => applyPoseSample({
                timestampMs: Date.now(),
                elbowAngleDeg: 84,
                shoulderHipAnkleAngleDeg: 174,
                visibility: 0.94,
              })}
            />
            <PoseButton
              label="推起"
              icon="arrow-up-outline"
              color={c.green}
              onPress={() => applyPoseSample({
                timestampMs: Date.now(),
                elbowAngleDeg: 166,
                shoulderHipAnkleAngleDeg: 175,
                visibility: 0.94,
              })}
            />
            <PoseButton
              label="+1 校准"
              icon="add-circle-outline"
              color={c.blue}
              onPress={addFullRep}
            />
            <PoseButton
              label="身体松动"
              icon="alert-circle-outline"
              color={s.warning.solid}
              onPress={() => applyPoseSample({
                timestampMs: Date.now(),
                elbowAngleDeg: 96,
                shoulderHipAnkleAngleDeg: 142,
                visibility: 0.94,
              })}
            />
          </View>
        </View>

        {coach.formWarnings.length > 0 ? (
          <View style={styles.panel}>
            <Text style={txt.sectionTitle}>动作评价</Text>
            <View style={styles.scoreRow}>
              <Text style={txt.score}>{coach.qualityScore}</Text>
              <Text style={txt.scoreUnit}>分</Text>
            </View>
            {coach.formWarnings.map((warning) => (
              <View key={warning.code} style={styles.warningRow}>
                <Ionicons name="information-circle-outline" size={16} color={s.warning.solid} />
                <Text style={txt.warningText}>{warning.message}</Text>
              </View>
            ))}
          </View>
        ) : null}

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>保存</Text>
          <Text style={txt.saveHint}>保存后会进入今日力量训练记录, 参与日程和训练负荷判断。</Text>
          <Pressable
            onPress={saveExercise}
            disabled={saveState === 'saving' || coach.reps <= 0}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.pressed,
              (saveState === 'saving' || coach.reps <= 0) && styles.disabledButton,
            ]}
            accessibilityRole="button"
          >
            <Ionicons name="save-outline" size={17} color="#fff" />
            <Text style={txt.primaryButton}>
              {saveState === 'saving' ? '保存中...' : saveState === 'saved' ? '已保存' : '保存本组'}
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );

  function PoseButton({
    label,
    icon,
    color,
    onPress,
  }: {
    label: string;
    icon: keyof typeof Ionicons.glyphMap;
    color: string;
    onPress: () => void;
  }) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [styles.poseButton, pressed && styles.pressed]}
        accessibilityRole="button"
      >
        <Ionicons name={icon} size={18} color={color} />
        <Text style={[txt.poseButtonText, { color }]}>{label}</Text>
      </Pressable>
    );
  }
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  iconButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    padding: spacing.lg,
    paddingBottom: 110,
  },
  heroPanel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  heroTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: spacing.md,
  },
  heroIcon: {
    width: 44,
    height: 44,
    borderRadius: radii.sm,
    backgroundColor: c.tintOrange,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginTop: spacing.sm,
  },
  progressTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: c.fill,
    overflow: 'hidden',
    marginTop: spacing.sm,
    marginBottom: spacing.md,
  },
  progressFill: {
    height: 8,
    borderRadius: 4,
    backgroundColor: c.orange,
  },
  panel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  primaryButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: radii.sm,
    backgroundColor: c.brand,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingHorizontal: spacing.sm,
  },
  secondaryButton: {
    minHeight: 44,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.fill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: spacing.md,
  },
  sampleGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  poseButton: {
    width: '48%',
    minHeight: 42,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    paddingTop: spacing.sm,
  },
  pressed: { opacity: 0.82 },
  disabledButton: { opacity: 0.5 },
});

const createTxt = (c: ColorPalette) => ({
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  heroKicker: { fontSize: 12, fontWeight: '800', color: c.orange } as TextStyle,
  heroTitle: { fontSize: 18, fontWeight: '900', color: c.labelPrimary, marginTop: 2 } as TextStyle,
  count: { fontSize: 68, fontWeight: '900', color: c.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  countTotal: { fontSize: 24, fontWeight: '800', color: c.labelTertiary, marginBottom: 12 } as TextStyle,
  feedback: { fontSize: 16, fontWeight: '800', color: c.labelPrimary, lineHeight: 22 } as TextStyle,
  suggestion: { fontSize: 13, color: c.labelSecondary, lineHeight: 19, marginTop: 6 } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  sessionState: { fontSize: 12, fontWeight: '800' } as TextStyle,
  sessionMessage: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: spacing.sm } as TextStyle,
  primaryButton: { fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
  secondaryButton: { fontSize: 13, fontWeight: '800', color: c.brand } as TextStyle,
  poseButtonText: { fontSize: 13, fontWeight: '800' } as TextStyle,
  score: { fontSize: 42, fontWeight: '900', color: c.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  scoreUnit: { fontSize: 14, fontWeight: '800', color: c.labelSecondary, marginBottom: 8, marginLeft: 4 } as TextStyle,
  warningText: { flex: 1, fontSize: 13, lineHeight: 18, color: c.labelSecondary } as TextStyle,
  saveHint: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 4, marginBottom: spacing.md } as TextStyle,
});
