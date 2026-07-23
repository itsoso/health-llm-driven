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
  duration_seconds?: number;
  duration_options?: number[];
  ratio?: string;
  ratio_mode?: 'fixed' | 'source' | string;
  resolution?: string;
  generates_audio?: boolean;
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
  const [selectedDuration, setSelectedDuration] = useState(
    Number(data.duration_seconds) || 5,
  );
  const confirmationID = String(data.confirmation_id || '').trim();
  const isVideo = data.kind === 'text_to_video' || data.kind === 'image_to_video';
  const durationOptions = (data.duration_options || [5, 10, 15])
    .filter((value) => Number.isInteger(value) && value >= 3 && value <= 15);

  useEffect(() => {
    if (!confirmationID) return;
    let active = true;
    void api.get(`/aigc/media/confirmations/${encodeURIComponent(confirmationID)}`)
      .then((response) => {
        const projection = normalizeJob(response?.data?.job);
        if (active && projection) setJob(projection);
        const duration = Number(response?.data?.spec?.duration_seconds);
        if (active && Number.isInteger(duration) && duration >= 3 && duration <= 15) {
          setSelectedDuration(duration);
        }
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
      const endpoint = `/aigc/media/confirmations/${encodeURIComponent(confirmationID)}/confirm`;
      const response = isVideo
        ? await api.post(endpoint, { duration_seconds: selectedDuration })
        : await api.post(endpoint);
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
          将发送你的创作描述{data.source_attached ? '和当前图片' : ''}给{data.provider || '百炼'}生成。
        </Text>
      </View>
      {isVideo ? (
        <View style={styles.specSection}>
          <View style={styles.specHeader}>
            <Text maxFontSizeMultiplier={1.2} style={styles.specLabel}>视频时长</Text>
            <Text maxFontSizeMultiplier={1.2} style={styles.specSummary}>
              {data.ratio_mode === 'source' ? '跟随原图' : (data.ratio || '9:16')}
              {' · '}{data.resolution || '720P'}
              {data.generates_audio === true ? ' · 含音频' : ''}
            </Text>
          </View>
          <View style={styles.durationRow}>
            {durationOptions.map((duration) => {
              const selected = duration === selectedDuration;
              return (
                <Pressable
                  key={duration}
                  onPress={() => setSelectedDuration(duration)}
                  accessibilityRole="button"
                  accessibilityLabel={`选择${duration}秒`}
                  accessibilityState={{ selected }}
                  style={({ pressed }) => [
                    styles.durationOption,
                    selected && styles.durationOptionSelected,
                    pressed && { opacity: 0.78 },
                  ]}
                >
                  <Text style={[styles.durationText, selected && styles.durationTextSelected]}>
                    {duration} 秒
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ) : null}
      {error ? <Text maxFontSizeMultiplier={1.2} style={styles.error}>{error}</Text> : null}
      <Pressable
        onPress={confirm}
        disabled={!confirmationID || submitting}
        accessibilityRole="button"
        accessibilityLabel={isVideo ? `确认生成${selectedDuration}秒短视频` : '发送给百炼并生成'}
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
  specSection: { marginTop: 12, gap: 8 },
  specHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  specLabel: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.ink1 } as TextStyle,
  specSummary: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3 } as TextStyle,
  durationRow: { flexDirection: 'row', gap: 8 },
  durationOption: { flex: 1, minHeight: 38, alignItems: 'center', justifyContent: 'center', borderRadius: revaRadii.md, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, backgroundColor: C.paper },
  durationOptionSelected: { borderColor: C.green500, backgroundColor: C.green100 },
  durationText: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.ink2 } as TextStyle,
  durationTextSelected: { color: C.green700 },
  error: { marginTop: 8, fontFamily: revaFonts.sans, fontSize: 12, color: '#C84B3C' } as TextStyle,
  confirmButton: { minHeight: 44, marginTop: 12, borderRadius: revaRadii.md, backgroundColor: C.green600, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 7 },
  confirmText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
});
