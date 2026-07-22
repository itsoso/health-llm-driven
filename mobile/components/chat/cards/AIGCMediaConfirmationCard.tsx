import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../../services/api';
import { CardShell } from './CardShell';
import { AIGCMediaJobCardView, type AIGCMediaJobCardData } from './AIGCMediaJobCard';
import type { CardSpec } from './types';
import { revaColors as C, revaFonts, revaRadii } from '../../../constants/revaTheme';

export interface AIGCMediaConfirmationCardData {
  confirmation_id: string;
  kind: string;
  status: 'pending' | string;
  title?: string;
  provider?: string;
  source_attached?: boolean;
}

function kindLabel(kind: string): string {
  if (kind === 'text_to_image') return '文生图';
  if (kind === 'image_to_image') return '图片创作';
  if (kind === 'text_to_video') return '文生短视频';
  if (kind === 'image_to_video') return '图生短视频';
  return '媒体创作';
}

function normalizeJob(value: unknown): AIGCMediaJobCardData | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const payload = value as Record<string, unknown>;
  if (typeof payload.id !== 'string') return null;
  return { ...payload, job_id: payload.id } as AIGCMediaJobCardData;
}

export function AIGCMediaConfirmationCardView(data: AIGCMediaConfirmationCardData) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<AIGCMediaJobCardData | null>(null);
  const confirmationID = String(data.confirmation_id || '').trim();

  useEffect(() => {
    if (!confirmationID) return;
    let active = true;
    void api.get(`/aigc/media/confirmations/${encodeURIComponent(confirmationID)}`)
      .then((response) => {
        const projection = normalizeJob(response?.data?.job);
        if (active && projection) setJob(projection);
      })
      .catch(() => {
        // Keep an unconsumed draft actionable. Durable history will resolve it
        // after the next successful owner-scoped status refresh.
      });
    return () => { active = false; };
  }, [confirmationID]);

  if (job) return <AIGCMediaJobCardView {...job} />;

  const confirm = async () => {
    if (!confirmationID || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.post(
        `/aigc/media/confirmations/${encodeURIComponent(confirmationID)}/confirm`,
      );
      const projection = normalizeJob(response?.data);
      if (!projection) throw new Error('aigc_confirmation_missing_job');
      setJob(projection);
    } catch {
      setError('提交未完成，请稍后重试。');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <CardShell
      icon="sparkles-outline"
      iconColor={C.green600}
      title={data.title || '小巴创作草稿'}
      badge={kindLabel(String(data.kind || ''))}
      badgeColor={C.green500}
    >
      <View style={styles.notice}>
        <Ionicons name="shield-checkmark-outline" size={17} color={C.green600} />
        <Text maxFontSizeMultiplier={1.2} style={styles.noticeText}>
          将发送你的创作描述{data.source_attached ? '和当前图片' : ''}给{data.provider || '百炼 Wan'}生成。
        </Text>
      </View>
      {error ? <Text maxFontSizeMultiplier={1.2} style={styles.error}>{error}</Text> : null}
      <Pressable
        onPress={confirm}
        disabled={!confirmationID || submitting}
        accessibilityRole="button"
        accessibilityLabel="发送给百炼并生成"
        style={({ pressed }) => [styles.confirmButton, (pressed || submitting) && { opacity: 0.82 }]}
      >
        {submitting ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="sparkles" size={16} color="#fff" />}
        <Text maxFontSizeMultiplier={1.15} style={styles.confirmText}>发送给百炼并生成</Text>
      </Pressable>
    </CardShell>
  );
}

export const AIGCMediaConfirmationCardSpec: CardSpec<AIGCMediaConfirmationCardData> = {
  type: 'aigc_media_confirmation',
  label: '小巴创作确认',
  match: () => null,
  build: () => null,
  render: (data) => <AIGCMediaConfirmationCardView {...data} />,
};

const styles = StyleSheet.create({
  notice: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, padding: 10, borderRadius: revaRadii.md, backgroundColor: C.green50 },
  noticeText: { flex: 1, fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, color: C.ink2 } as TextStyle,
  error: { marginTop: 8, fontFamily: revaFonts.sans, fontSize: 12, color: '#C84B3C' } as TextStyle,
  confirmButton: { minHeight: 44, marginTop: 12, borderRadius: revaRadii.md, backgroundColor: C.green600, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 7 },
  confirmText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
});
