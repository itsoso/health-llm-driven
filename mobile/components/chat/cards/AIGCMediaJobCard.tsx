import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
  Pressable,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { Image } from 'expo-image';
import { VideoView, useVideoPlayer } from 'expo-video';
import { Ionicons } from '@expo/vector-icons';

import api, { BASE_URL } from '../../../services/api';
import { emitClientEvent } from '../../../services/clientEvents';
import {
  shareImage,
  shareRemoteVideo,
  type VideoShareTarget,
} from '../../../utils/share';
import { SocialBrandIcon } from '../../common/SocialBrandIcon';
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
  spec?: {
    duration_seconds?: number;
    ratio?: string;
    ratio_mode?: 'fixed' | 'source' | string;
    resolution?: string;
    generates_audio?: boolean;
  } | null;
  result?: {
    media_type?: string | null;
    url?: string | null;
    byte_size?: number | null;
  } | null;
  error_message?: string | null;
  error_code?: string | null;
  can_retry?: boolean;
}

const ACTIVE_STATUSES = new Set<AIGCStatus>(['queued', 'running']);
function pollDelay(attempt: number): number {
  if (attempt < 2) return 6000;
  if (attempt < 6) return 15000;
  return 30000;
}

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
  const [sharingTarget, setSharingTarget] = useState<VideoShareTarget | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const mounted = useRef(true);
  const sharingRef = useRef(false);
  const refreshInFlight = useRef<Promise<void> | null>(null);
  const appStateRef = useRef(AppState.currentState);
  const networkConnectedRef = useRef<boolean | null>(null);
  const playbackEventSent = useRef(false);

  useEffect(() => {
    setData(initialData);
  }, [initialData]);

  const refresh = useCallback(async () => {
    const jobId = String(initialData.job_id || '').trim();
    if (!jobId) return;
    if (refreshInFlight.current) return refreshInFlight.current;
    const request = (async () => {
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
    })();
    refreshInFlight.current = request;
    try {
      await request;
    } finally {
      if (refreshInFlight.current === request) refreshInFlight.current = null;
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
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    const schedule = () => {
      timer = setTimeout(() => {
        if (cancelled) return;
        void refresh().finally(() => {
          attempt += 1;
          if (!cancelled) schedule();
        });
      }, pollDelay(attempt));
    };
    schedule();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [data.status, refresh]);

  useEffect(() => {
    if (!ACTIVE_STATUSES.has(statusOf(data.status))) return;
    const appStateSubscription = AppState.addEventListener('change', (nextState) => {
      const previousState = appStateRef.current;
      appStateRef.current = nextState;
      if (nextState === 'active' && previousState !== 'active') {
        void refresh();
      }
    });
    const removeNetworkListener = NetInfo.addEventListener((state) => {
      const wasConnected = networkConnectedRef.current;
      networkConnectedRef.current = state.isConnected;
      if (state.isConnected === true && wasConnected === false) {
        void refresh();
      }
    });
    return () => {
      appStateSubscription?.remove?.();
      removeNetworkListener?.();
    };
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
    playbackEventSent.current = false;
  }, [resultUrl]);

  const detail = useMemo(() => {
    if (status === 'queued') return '小巴已提交任务，正在等待百炼处理。';
    if (status === 'running' && progress < 75) return '正在生成画面和音频，请保持网络可用。';
    if (status === 'running') return '生成已接近完成，正在保存到你的私有空间。';
    if (status === 'succeeded') return '结果仅对当前账号可见。';
    if (status === 'submission_unknown') return '提交结果待核验，已停止自动重试以避免重复生成。';
    return data.error_message || '本次创作未完成，修改描述后可以重新生成。';
  }, [data.error_message, progress, status]);

  const specText = useMemo(() => {
    const duration = Number(data.spec?.duration_seconds);
    if (!Number.isFinite(duration) || duration <= 0) return null;
    const parts = [
      `${Math.round(duration)}秒`,
      data.spec?.ratio_mode === 'source' ? '跟随原图' : data.spec?.ratio,
      data.spec?.resolution,
      data.spec?.generates_audio === true ? '含音频' : null,
    ].filter(Boolean);
    return parts.join(' · ');
  }, [data.spec]);

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
      if (!playbackEventSent.current) {
        playbackEventSent.current = true;
        void emitClientEvent('aigc_media_played', { media_kind: 'video' });
      }
    } catch {
      setActionError('视频暂时无法播放，请稍后重试。');
    }
  }, [isVideo, resultUrl, videoPlayer]);

  const shareResult = useCallback(async (target: VideoShareTarget) => {
    if ((!isVideo && !isImage) || !resultUrl || sharingRef.current) return;
    sharingRef.current = true;
    setActionError(null);
    setSharingTarget(target);
    try {
      let shareUrl = resultUrl;
      let response: { data?: unknown } | null = null;
      try {
        response = await api.get(`/aigc/media/jobs/${encodeURIComponent(data.job_id)}`);
      } catch {
        // The card already owns a signed URL; refresh is best effort.
      }
      const projection = normalizeJobProjection(response?.data, data.job_id);
      const freshResultUrl = privateMediaUrl(projection?.result?.url);
      const freshMediaType = String(projection?.result?.media_type || '').toLowerCase();
      const hasMatchingFreshResult = isVideo
        ? freshMediaType.startsWith('video/')
        : freshMediaType.startsWith('image/');
      if (freshResultUrl && hasMatchingFreshResult) {
        shareUrl = freshResultUrl;
        if (mounted.current && projection) setData(projection);
      }
      if (isVideo) {
        await shareRemoteVideo(shareUrl, {
          target,
          cacheKey: data.job_id,
        });
      } else {
        await shareImage(shareUrl, {
          target,
          cacheKey: data.job_id,
          mimeType: mediaType,
        });
      }
      void emitClientEvent('aigc_media_shared', {
        phase: 'completed',
        media_kind: isVideo ? 'video' : 'image',
        share_target: target,
      });
    } catch {
      void emitClientEvent('aigc_media_shared', {
        phase: 'failed',
        media_kind: isVideo ? 'video' : 'image',
        share_target: target,
        error_code: 'share_failed',
      });
      if (mounted.current) {
        setActionError(`${isVideo ? '视频' : '图片'}分享未打开，请检查网络后再试。`);
      }
    } finally {
      sharingRef.current = false;
      if (mounted.current) setSharingTarget(null);
    }
  }, [data.job_id, isImage, isVideo, mediaType, resultUrl]);

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
      {specText ? (
        <View style={styles.specPill}>
          <Ionicons name="videocam-outline" size={14} color={C.green700} />
          <Text maxFontSizeMultiplier={1.15} style={styles.specText}>{specText}</Text>
        </View>
      ) : null}

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
        <View style={styles.imageWrap}>
          <Image
            source={{ uri: resultUrl }}
            style={styles.image}
            contentFit="cover"
            transition={160}
            accessibilityLabel="小巴生成的图片"
          />
        </View>
      ) : null}

      {resultUrl && isVideo ? (
        <>
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
        </>
      ) : null}

      {resultUrl && (isImage || isVideo) ? (
        <View style={styles.shareRow}>
          <Pressable
            testID={`aigc-${isVideo ? 'video' : 'image'}-share-wechat`}
            style={({ pressed }) => [
              styles.shareButton,
              pressed && !sharingTarget && styles.shareButtonPressed,
            ]}
            onPress={() => { void shareResult('wechat'); }}
            disabled={sharingTarget !== null}
            accessibilityRole="button"
            accessibilityLabel={isVideo ? '分享到微信' : '图片分享到微信'}
            accessibilityState={{ disabled: sharingTarget !== null, busy: sharingTarget === 'wechat' }}
          >
            {sharingTarget === 'wechat'
              ? <ActivityIndicator size="small" color={C.green600} />
              : <SocialBrandIcon brand="wechat" size={14} />}
            <Text style={styles.shareText}>微信</Text>
          </Pressable>
          <Pressable
            testID={`aigc-${isVideo ? 'video' : 'image'}-share-xiaohongshu`}
            style={({ pressed }) => [
              styles.shareButton,
              pressed && !sharingTarget && styles.shareButtonPressed,
            ]}
            onPress={() => { void shareResult('xiaohongshu'); }}
            disabled={sharingTarget !== null}
            accessibilityRole="button"
            accessibilityLabel={isVideo ? '分享到小红书' : '图片分享到小红书'}
            accessibilityState={{ disabled: sharingTarget !== null, busy: sharingTarget === 'xiaohongshu' }}
          >
            {sharingTarget === 'xiaohongshu'
              ? <ActivityIndicator size="small" color={C.green600} />
              : <SocialBrandIcon brand="xiaohongshu" size={14} />}
            <Text style={styles.shareText}>小红书</Text>
          </Pressable>
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
  specPill: { alignSelf: 'flex-start', marginTop: 10, minHeight: 30, paddingHorizontal: 10, borderRadius: revaRadii.pill, backgroundColor: C.green50, flexDirection: 'row', alignItems: 'center', gap: 5 },
  specText: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700', color: C.green700 } as TextStyle,
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
  imageWrap: { width: '100%', aspectRatio: 1, marginTop: 12, borderRadius: revaRadii.md, overflow: 'hidden' },
  image: { width: '100%', height: '100%', backgroundColor: C.paper2 },
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
  shareRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 6,
    marginTop: 8,
  },
  shareButton: {
    minHeight: 34,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    paddingHorizontal: 10,
  },
  shareButtonPressed: { backgroundColor: C.green50 },
  shareText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
    color: C.ink2,
  } as TextStyle,
});
