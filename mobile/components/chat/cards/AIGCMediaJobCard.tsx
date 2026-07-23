import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Image } from 'expo-image';
import { VideoView, useVideoPlayer } from 'expo-video';
import { Ionicons } from '@expo/vector-icons';

import api, { BASE_URL } from '../../../services/api';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
} from '../../../constants/revaTheme';

type AIGCStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'submission_unknown';

export interface AIGCMediaJobCardData {
  job_id: string;
  kind: 'text_to_image' | 'image_to_image' | 'text_to_video' | 'image_to_video' | string;
  status: AIGCStatus | string;
  progress: number;
  title?: string;
  result?: {
    media_type?: string | null;
    url?: string | null;
  } | null;
  error_message?: string | null;
  error_code?: string | null;
  can_retry?: boolean;
}

const ACTIVE_STATUSES = new Set<AIGCStatus>(['queued', 'running']);
const POLL_INTERVAL_MS = 6000;

function statusOf(value: unknown): AIGCStatus {
  const normalized = String(value || '').trim().toLowerCase();
  return ['queued', 'running', 'succeeded', 'failed', 'cancelled', 'submission_unknown'].includes(normalized)
    ? normalized as AIGCStatus
    : 'queued';
}

function clampProgress(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function privateMediaUrl(value: unknown): string | null {
  const raw = typeof value === 'string' ? value.trim() : '';
  if (!raw) return null;
  if (/^https?:\/\//i.test(raw)) return raw;
  if (!raw.startsWith('/')) return null;

  const origin = String(BASE_URL || '')
    .trim()
    .replace(/\/+$/, '')
    .replace(/\/api(?:\/v\d+)?$/i, '');
  return origin ? `${origin}${raw}` : null;
}

function kindLabel(kind: string): string {
  switch (kind) {
    case 'text_to_image': return '文生图';
    case 'image_to_image': return '图片创作';
    case 'text_to_video': return '文生短视频';
    case 'image_to_video': return '图生短视频';
    default: return '媒体创作';
  }
}

function normalizeJobProjection(raw: unknown, fallbackJobId: string): AIGCMediaJobCardData | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const payload = raw as Record<string, unknown>;
  const id = typeof payload.id === 'string' ? payload.id : fallbackJobId;
  return { ...payload, job_id: typeof payload.job_id === 'string' ? payload.job_id : id } as AIGCMediaJobCardData;
}

function statusMeta(status: AIGCStatus): { label: string; color: string; icon: keyof typeof Ionicons.glyphMap } {
  switch (status) {
    case 'queued': return { label: '排队中', color: C.green500, icon: 'time-outline' };
    case 'running': return { label: '生成中', color: C.green600, icon: 'sparkles-outline' };
    case 'succeeded': return { label: '已完成', color: C.green600, icon: 'checkmark-circle' };
    case 'failed': return { label: '未完成', color: '#C84B3C', icon: 'alert-circle-outline' };
    case 'cancelled': return { label: '已取消', color: C.ink3, icon: 'close-circle-outline' };
    case 'submission_unknown': return { label: '提交待核验', color: '#B7791F', icon: 'help-circle-outline' };
  }
}

export function AIGCMediaJobCardView(initialData: AIGCMediaJobCardData) {
  const [data, setData] = useState<AIGCMediaJobCardData>(initialData);
  const [refreshing, setRefreshing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [playbackStarted, setPlaybackStarted] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    setData(initialData);
  }, [initialData]);

  const refresh = useCallback(async () => {
    const jobId = String(initialData.job_id || '').trim();
    if (!jobId) return;
    setRefreshing(true);
    try {
      const response = await api.get(`/aigc/media/jobs/${encodeURIComponent(jobId)}`);
      const projection = normalizeJobProjection(response?.data, jobId);
      if (mounted.current && projection) {
        setData(projection);
      }
    } catch {
      // Preserve the last known job projection. The next poll or task update may succeed.
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  }, [initialData.job_id]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => {
      mounted.current = false;
    };
  }, [refresh]);

  useEffect(() => {
    if (!ACTIVE_STATUSES.has(statusOf(data.status))) return;
    const timer = setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => { clearInterval(timer); };
  }, [data.status, refresh]);

  const status = statusOf(data.status);
  const meta = statusMeta(status);
  const progress = clampProgress(data.progress);
  const resultUrl = privateMediaUrl(data.result?.url);
  const mediaType = String(data.result?.media_type || '').toLowerCase();
  const isImage = mediaType.startsWith('image/');
  const isVideo = mediaType.startsWith('video/');
  const videoPlayer = useVideoPlayer(isVideo ? resultUrl : null, (player) => {
    player.loop = false;
    player.staysActiveInBackground = false;
    player.showNowPlayingNotification = false;
  });
  const canCancel = ACTIVE_STATUSES.has(status) && !cancelling;
  const canRetry = status === 'failed' && data.can_retry === true && !retrying;

  useEffect(() => {
    setPlaybackStarted(false);
  }, [resultUrl]);

  const detail = useMemo(() => {
    if (status === 'queued') return '小巴已提交任务，正在等待百炼处理。';
    if (status === 'running') return '生成完成后会自动保存到你的私有空间。';
    if (status === 'succeeded') return '结果仅对当前账号可见。';
    if (status === 'submission_unknown') return '提交结果待核验，已停止自动重试以避免重复生成。';
    return data.error_message || '本次创作未完成，修改描述后可以重新生成。';
  }, [data.error_message, status]);

  const cancel = async () => {
    if (!canCancel) return;
    setCancelling(true);
    try {
      const response = await api.post(`/aigc/media/jobs/${encodeURIComponent(data.job_id)}/cancel`);
      const projection = normalizeJobProjection(response?.data, data.job_id);
      if (projection) {
        setData(projection);
      }
    } catch {
      // Keep the active state visible; the user may retry cancellation.
    } finally {
      if (mounted.current) setCancelling(false);
    }
  };

  const retry = async () => {
    if (!canRetry) return;
    setRetrying(true);
    setActionError(null);
    try {
      const response = await api.post(`/aigc/media/jobs/${encodeURIComponent(data.job_id)}/retry`);
      const projection = normalizeJobProjection(response?.data, data.job_id);
      if (projection) setData(projection);
    } catch {
      setActionError('重试未提交，请检查网络后再试。');
    } finally {
      if (mounted.current) setRetrying(false);
    }
  };

  const playVideo = useCallback(() => {
    if (!isVideo || !resultUrl) return;
    setActionError(null);
    try {
      videoPlayer.play();
      setPlaybackStarted(true);
    } catch {
      setActionError('视频暂时无法播放，请稍后重试。');
    }
  }, [isVideo, resultUrl, videoPlayer]);

  return (
    <CardShell
      icon="sparkles-outline"
      iconColor={meta.color}
      title={data.title || '小巴创作'}
      badge={kindLabel(String(data.kind || ''))}
      badgeColor={C.green500}
      style={styles.shell}
    >
      <View style={styles.statusRow}>
        <View style={[styles.statusIcon, { backgroundColor: `${meta.color}16` }]}>
          {status === 'running' || refreshing ? (
            <ActivityIndicator size="small" color={meta.color} />
          ) : (
            <Ionicons name={meta.icon} size={17} color={meta.color} />
          )}
        </View>
        <View style={styles.statusBody}>
          <Text maxFontSizeMultiplier={1.2} style={styles.statusTitle}>{meta.label}</Text>
          <Text maxFontSizeMultiplier={1.2} style={styles.detail}>{detail}</Text>
        </View>
        {canCancel ? (
          <Pressable
            style={({ pressed }) => [styles.iconButton, pressed && styles.iconButtonPressed]}
            onPress={cancel}
            disabled={cancelling}
            accessibilityRole="button"
            accessibilityLabel="取消生成"
          >
            {cancelling ? <ActivityIndicator size="small" color={C.ink2} /> : <Ionicons name="close" size={18} color={C.ink2} />}
          </Pressable>
        ) : null}
      </View>

      {ACTIVE_STATUSES.has(status) ? (
        <View style={styles.progressWrap} accessibilityLabel={`生成进度 ${progress}%`}>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.max(progress, 4)}%` }]} />
          </View>
          <Text maxFontSizeMultiplier={1.1} style={styles.progressText}>{progress}%</Text>
        </View>
      ) : null}

      {status === 'failed' && data.can_retry === true ? (
        <Pressable
          style={({ pressed }) => [styles.retryButton, pressed && styles.retryButtonPressed]}
          onPress={retry}
          disabled={retrying}
          accessibilityRole="button"
          accessibilityLabel="重试生成"
        >
          {retrying ? (
            <ActivityIndicator size="small" color={C.green700} />
          ) : (
            <Ionicons name="refresh" size={16} color={C.green700} />
          )}
          <Text maxFontSizeMultiplier={1.2} style={styles.retryButtonText}>
            {retrying ? '正在重试' : '重试生成'}
          </Text>
        </Pressable>
      ) : null}

      {actionError ? <Text style={styles.actionError}>{actionError}</Text> : null}

      {resultUrl && isImage ? (
        <Image
          source={{ uri: resultUrl }}
          style={styles.image}
          contentFit="cover"
          transition={160}
          accessibilityLabel="小巴生成的图片"
        />
      ) : null}

      {resultUrl && isVideo ? (
        <View style={styles.videoFrame}>
          <VideoView
            testID="aigc-video-player"
            player={videoPlayer}
            style={styles.video}
            nativeControls
            contentFit="contain"
            fullscreenOptions={{ enable: true }}
            accessibilityLabel="小巴生成的短视频"
          />
          {!playbackStarted ? (
            <Pressable
              testID="aigc-video-play-button"
              style={({ pressed }) => [
                styles.playOverlay,
                pressed && styles.playOverlayPressed,
              ]}
              onPress={playVideo}
              accessibilityRole="button"
              accessibilityLabel="播放短视频"
              accessibilityHint="播放已生成的短视频，不会重新生成"
            >
              <View style={styles.playButton}>
                <Ionicons name="play" size={25} color={C.surface} />
              </View>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </CardShell>
  );
}

export const AIGCMediaJobCardSpec: CardSpec<AIGCMediaJobCardData> = {
  type: 'aigc_media_job',
  label: '小巴创作任务',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <AIGCMediaJobCardView {...data} />,
};

const styles = StyleSheet.create({
  shell: { overflow: 'hidden' },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s3 },
  statusIcon: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  statusBody: { flex: 1, gap: 2 },
  statusTitle: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '800', color: C.ink1 } as TextStyle,
  detail: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, color: C.ink3 } as TextStyle,
  iconButton: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: C.paper2 },
  iconButtonPressed: { opacity: 0.72 },
  progressWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12 },
  progressTrack: { flex: 1, height: 6, borderRadius: 3, backgroundColor: C.paper2, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 3, backgroundColor: C.green500 },
  progressText: { width: 32, textAlign: 'right', fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700', color: C.ink3 } as TextStyle,
  retryButton: { minHeight: 42, marginTop: 12, borderRadius: revaRadii.md, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, backgroundColor: C.green100 },
  retryButtonPressed: { opacity: 0.72 },
  retryButtonText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '800', color: C.green700 } as TextStyle,
  actionError: { marginTop: 8, fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, color: revaSemantic.risk.fg } as TextStyle,
  image: { width: '100%', aspectRatio: 1, borderRadius: revaRadii.md, marginTop: 12, backgroundColor: C.paper2 },
  videoFrame: { width: '100%', aspectRatio: 16 / 9, marginTop: 12, borderRadius: revaRadii.md, overflow: 'hidden', backgroundColor: C.ink1 },
  video: { flex: 1 },
  playOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(8, 24, 18, 0.12)',
  },
  playOverlayPressed: { backgroundColor: 'rgba(8, 24, 18, 0.2)' },
  playButton: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
    paddingLeft: 3,
    backgroundColor: 'rgba(15, 55, 40, 0.86)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255, 255, 255, 0.5)',
  },
});
