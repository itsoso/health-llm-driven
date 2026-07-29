import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../../services/api';
import { CardShell } from './CardShell';
import { AIGCMediaJobCardView, type AIGCMediaJobCardData } from './AIGCMediaJobCard';
import type { CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../../constants/revaTheme';

const CONFIRMATION_RECONCILE_INTERVAL_MS = 1500;
const CONFIRMATION_RECONCILE_ATTEMPTS = 8;
const DEFAULT_VIDEO_DURATION_OPTIONS = [5, 8, 15];
const LEGACY_VIDEO_DURATION_OPTIONS = [5, 10, 15];

export interface AIGCMediaConfirmationCardData {
  confirmation_id: string;
  kind: string;
  status: 'pending' | string;
  title?: string;
  provider?: string;
  source_attached?: boolean;
  content_summary?: string;
  content_topics?: string[];
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

function confirmationStatus(value: unknown): string {
  return String(value || 'pending').trim().toLowerCase();
}

function responseDetail(error: unknown): string | null {
  if (!error || typeof error !== 'object') return null;
  const response = (error as { response?: unknown }).response;
  if (!response || typeof response !== 'object') return null;
  const data = (response as { data?: unknown }).data;
  if (!data || typeof data !== 'object') return null;
  const detail = (data as { detail?: unknown }).detail;
  return typeof detail === 'string' && detail.trim() ? detail.trim() : null;
}

function normalizedDurationOptions(value: unknown): number[] {
  const options = Array.isArray(value)
    ? [...new Set(
      value
        .map((item) => Number(item))
        .filter((item) => Number.isInteger(item) && item >= 3 && item <= 15),
    )]
    : [];
  const isLegacySet = options.length === LEGACY_VIDEO_DURATION_OPTIONS.length
    && LEGACY_VIDEO_DURATION_OPTIONS.every((item, index) => options[index] === item);
  return options.length > 0 && !isLegacySet
    ? options
    : [...DEFAULT_VIDEO_DURATION_OPTIONS];
}

function normalizedSelectedDuration(value: unknown, options: number[]): number {
  const duration = Number(value);
  return Number.isInteger(duration) && options.includes(duration)
    ? duration
    : (options[0] || DEFAULT_VIDEO_DURATION_OPTIONS[0]);
}

export function AIGCMediaConfirmationCardView(data: AIGCMediaConfirmationCardData) {
  const initialDurationOptions = normalizedDurationOptions(data.duration_options);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<AIGCMediaJobCardData | null>(null);
  const [status, setStatus] = useState(confirmationStatus(data.status));
  const [canConfirm, setCanConfirm] = useState(true);
  const [durationOptions, setDurationOptions] = useState(initialDurationOptions);
  const [selectedDuration, setSelectedDuration] = useState(() => (
    normalizedSelectedDuration(data.duration_seconds, initialDurationOptions)
  ));
  const submittingRef = useRef(false);
  const durationSelectedByUserRef = useRef(false);
  const confirmationID = String(data.confirmation_id || '').trim();
  const isVideo = data.kind === 'text_to_video' || data.kind === 'image_to_video';

  useEffect(() => {
    if (!confirmationID) return;
    let active = true;
    void api.get(`/aigc/media/confirmations/${encodeURIComponent(confirmationID)}`)
      .then((response) => {
        const projection = normalizeJob(response?.data?.job);
        if (active && projection) setJob(projection);
        if (active) {
          setStatus(confirmationStatus(response?.data?.status));
          if (typeof response?.data?.can_confirm === 'boolean') {
            setCanConfirm(response.data.can_confirm);
          }
        }
        if (active && isVideo) {
          const nextOptions = normalizedDurationOptions(
            response?.data?.spec?.duration_options,
          );
          setDurationOptions(nextOptions);
          setSelectedDuration((current) => (
            durationSelectedByUserRef.current && nextOptions.includes(current)
              ? current
              : normalizedSelectedDuration(
                response?.data?.spec?.duration_seconds,
                nextOptions,
              )
          ));
        }
      })
      .catch(() => {
        // Keep an unconsumed draft actionable. Durable history will resolve it
        // after the next successful owner-scoped status refresh.
      });
    return () => { active = false; };
  }, [confirmationID, isVideo]);

  useEffect(() => {
    if (!confirmationID || status !== 'dispatching' || job) return;
    let active = true;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const reconcile = async () => {
      attempts += 1;
      try {
        const response = await api.get(
          `/aigc/media/confirmations/${encodeURIComponent(confirmationID)}`,
        );
        if (!active) return;
        const projection = normalizeJob(response?.data?.job);
        if (projection) {
          setJob(projection);
          return;
        }
        const nextStatus = confirmationStatus(response?.data?.status);
        setStatus(nextStatus);
        if (typeof response?.data?.can_confirm === 'boolean') {
          setCanConfirm(response.data.can_confirm);
        }
        if (nextStatus !== 'dispatching') return;
      } catch {
        if (!active) return;
      }
      if (attempts < CONFIRMATION_RECONCILE_ATTEMPTS) {
        timer = setTimeout(reconcile, CONFIRMATION_RECONCILE_INTERVAL_MS);
      } else if (active) {
        setError('任务仍在服务器处理中，稍后重新打开对话即可继续查看。');
      }
    };

    void reconcile();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [confirmationID, job, status]);

  if (job) return <AIGCMediaJobCardView {...job} />;

  const confirm = async () => {
    if (!confirmationID || !canConfirm || submittingRef.current) return;
    submittingRef.current = true;
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
    } catch (caught) {
      let reconciled = false;
      try {
        const response = await api.get(
          `/aigc/media/confirmations/${encodeURIComponent(confirmationID)}`,
        );
        const projection = normalizeJob(response?.data?.job);
        if (projection) {
          setJob(projection);
          reconciled = true;
        } else {
          const nextStatus = confirmationStatus(response?.data?.status);
          setStatus(nextStatus);
          if (typeof response?.data?.can_confirm === 'boolean') {
            setCanConfirm(response.data.can_confirm);
          }
          reconciled = nextStatus === 'expired' || nextStatus === 'dispatching';
        }
      } catch {
        // The original response remains authoritative when reconciliation is unavailable.
      }
      if (!reconciled) {
        setError(responseDetail(caught) || '提交未完成，请检查网络后重试。');
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const isExpired = status === 'expired';
  const isDispatching = status === 'dispatching';
  const buttonDisabled = !confirmationID || !canConfirm || submitting || isDispatching;
  const buttonLabel = isVideo
    ? `${isExpired ? '重新确认生成' : '确认生成'}${selectedDuration}秒短视频`
    : isExpired ? '重新确认并生成' : '确认并生成';
  const contentSummary = String(data.content_summary || '').trim();

  return (
    <CardShell
      icon="sparkles-outline"
      iconColor={C.green600}
      title={data.title || '小巴创作草稿'}
      badge={kindLabel(String(data.kind || ''))}
      badgeColor={C.green500}
    >
      {contentSummary ? (
        <View style={styles.contentSection}>
          <Text maxFontSizeMultiplier={1.2} style={styles.contentLabel}>
            内容预览
          </Text>
          <Text maxFontSizeMultiplier={1.3} style={styles.contentSummary}>
            {contentSummary}
          </Text>
        </View>
      ) : null}
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
                  onPress={() => {
                    durationSelectedByUserRef.current = true;
                    setSelectedDuration(duration);
                  }}
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
      <View style={styles.notice}>
        <Ionicons name="shield-checkmark-outline" size={17} color={C.green600} />
        <Text maxFontSizeMultiplier={1.2} style={styles.noticeText}>
          确认后，将把创作描述{data.source_attached ? '和当前图片' : ''}发送至{data.provider || '百炼'}。
        </Text>
      </View>
      {isExpired ? (
        <View style={[styles.stateNotice, !canConfirm && styles.stateNoticeUnavailable]}>
          <Ionicons
            name={canConfirm ? 'refresh-circle-outline' : 'time-outline'}
            size={17}
            color={canConfirm ? revaSemantic.caution.fg : C.ink3}
          />
          <Text maxFontSizeMultiplier={1.2} style={styles.stateNoticeText}>
            {canConfirm
              ? '草稿已过期，点击下方可重新确认生成。'
              : '草稿已超过可恢复时间，请重新向小巴发起创作。'}
          </Text>
        </View>
      ) : null}
      {isDispatching ? (
        <View style={styles.stateNotice}>
          <ActivityIndicator size="small" color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={styles.stateNoticeText}>
            正在核对生成任务，请稍候。
          </Text>
        </View>
      ) : null}
      {error ? <Text maxFontSizeMultiplier={1.2} style={styles.error}>{error}</Text> : null}
      <Pressable
        onPress={confirm}
        disabled={buttonDisabled}
        accessibilityRole="button"
        accessibilityLabel={buttonLabel}
        style={({ pressed }) => [
          styles.confirmButton,
          buttonDisabled && styles.confirmButtonDisabled,
          (pressed || submitting) && { opacity: 0.82 },
        ]}
      >
        {submitting ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="sparkles" size={16} color="#fff" />}
        <Text maxFontSizeMultiplier={1.15} style={styles.confirmText}>
          {isDispatching ? '正在核对任务' : isExpired ? '重新确认并生成' : '确认并生成'}
        </Text>
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
  contentSection: { gap: 4, paddingLeft: 10, borderLeftWidth: 2, borderLeftColor: C.green500 },
  contentLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    color: C.green700,
  } as TextStyle,
  contentSummary: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '700',
    color: C.ink1,
  } as TextStyle,
  notice: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginTop: 12,
    padding: 10,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
  },
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
  stateNotice: { marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 7, padding: 9, borderRadius: revaRadii.sm, backgroundColor: revaSemantic.caution.bg, borderWidth: StyleSheet.hairlineWidth, borderColor: revaSemantic.caution.line },
  stateNoticeUnavailable: { backgroundColor: C.paper2, borderColor: C.line },
  stateNoticeText: { flex: 1, fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, color: C.ink2 } as TextStyle,
  error: { marginTop: 8, fontFamily: revaFonts.sans, fontSize: 12, color: '#C84B3C' } as TextStyle,
  confirmButton: { minHeight: 44, marginTop: 12, borderRadius: revaRadii.md, backgroundColor: C.green600, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 7 },
  confirmButtonDisabled: { backgroundColor: C.ink4 },
  confirmText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
});
