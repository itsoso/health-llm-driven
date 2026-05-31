/**
 * JudgmentFeedbackBar — 通用"对/不对"反馈条
 *
 * 用法: 嵌入到任何展示 AI 判断的卡片底部
 *   <JudgmentFeedbackBar targetType="anomaly_alert" targetId={alert.id}
 *                        snapshot={alert.message} existing={alert.feedback} />
 */
import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { spacing } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';

export type JudgmentFeedback = 'helpful' | 'not_helpful' | 'irrelevant' | 'already_knew';
export type JudgmentTargetType =
  | 'insight' | 'anomaly_alert' | 'action_card'
  | 'safety_alert' | 'llm_arbitration' | 'specialist_finding';

interface Props {
  targetType: JudgmentTargetType;
  targetId: number;
  snapshot?: string;
  existing?: JudgmentFeedback | null;
  invalidateQueryKeys?: readonly (readonly unknown[])[];
  compact?: boolean;  // 紧凑模式: 只 3 个 icon 按钮 (默认带文字)
}

const LABEL: Record<JudgmentFeedback, string> = {
  helpful: '有用',
  not_helpful: '不对',
  irrelevant: '不相关',
  already_knew: '我知道',
};

export default function JudgmentFeedbackBar({
  targetType, targetId, snapshot, existing, invalidateQueryKeys, compact,
}: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const qc = useQueryClient();
  const [local, setLocal] = useState<JudgmentFeedback | null>(existing ?? null);

  const submitMut = useMutation({
    mutationFn: async (feedback: JudgmentFeedback) => {
      await api.post('/judgment/feedback', {
        target_type: targetType,
        target_id: targetId,
        feedback,
        snapshot,
      });
    },
    onSuccess: (_, feedback) => {
      setLocal(feedback);
      (invalidateQueryKeys ?? []).forEach(k => qc.invalidateQueries({ queryKey: k }));
    },
  });

  const handle = (f: JudgmentFeedback) => {
    if (submitMut.isPending) return;
    Haptics.notificationAsync(
      f === 'helpful'
        ? Haptics.NotificationFeedbackType.Success
        : Haptics.NotificationFeedbackType.Warning,
    );
    submitMut.mutate(f);
  };

  if (local) {
    return (
      <View style={styles.done}>
        <Ionicons name="checkmark-circle" size={12} color={c.green} />
        <Text style={styles.doneText}>已反馈: {LABEL[local]}</Text>
        {submitMut.isPending && <Text style={styles.doneText}>(更新中)</Text>}
      </View>
    );
  }

  return (
    <View style={styles.bar}>
      {!compact && <Text style={styles.prompt}>这个判断对你有用吗?</Text>}
      <View style={styles.btnRow}>
        <TouchableOpacity
          style={[styles.btn, styles.btnHelpful]}
          onPress={() => handle('helpful')}
          accessibilityLabel="有用"
        >
          <Ionicons name="thumbs-up-outline" size={13} color={c.brand} />
          {!compact && <Text style={[styles.btnText, { color: c.brand }]}>有用</Text>}
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.btn, styles.btnNeutral]}
          onPress={() => handle('already_knew')}
          accessibilityLabel="我早知道"
        >
          <Ionicons name="information-circle-outline" size={13} color={c.labelSecondary} />
          {!compact && <Text style={[styles.btnText, { color: c.labelSecondary }]}>我知道</Text>}
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.btn, styles.btnNo]}
          onPress={() => handle('not_helpful')}
          accessibilityLabel="不对"
        >
          <Ionicons name="thumbs-down-outline" size={13} color={c.red} />
          {!compact && <Text style={[styles.btnText, { color: c.red }]}>不对</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    bar: {
      gap: 6,
      paddingVertical: spacing.sm,
    },
    prompt: { fontSize: 11, color: c.labelTertiary },
    btnRow: { flexDirection: 'row', gap: 6 },
    btn: {
      flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
      paddingVertical: 8, borderRadius: 8,
      borderWidth: StyleSheet.hairlineWidth,
    },
    btnHelpful: { borderColor: c.brand, backgroundColor: c.brandLight },
    btnNeutral: { borderColor: c.separator, backgroundColor: c.bgPrimary },
    btnNo: { borderColor: `${c.red}44`, backgroundColor: c.tintRed },
    btnText: { fontSize: 12, fontWeight: '600' as const },
    done: {
      flexDirection: 'row', alignItems: 'center', gap: 6,
      paddingVertical: 6,
    },
    doneText: { fontSize: 11, color: c.labelSecondary },
  });
}
