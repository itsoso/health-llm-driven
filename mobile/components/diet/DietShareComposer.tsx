import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Image } from 'expo-image';
import * as MediaLibrary from 'expo-media-library';
import * as Sharing from 'expo-sharing';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';
import { captureRef, releaseCapture } from 'react-native-view-shot';

import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
} from '../../constants/revaTheme';
import { materializeImageForLocalUse } from '../../utils/share';
import DietShareCard, { dietShareCaptureDimensions } from './DietShareCard';
import {
  DietShareImageEditor,
  type DietShareImageEditorResult,
} from './DietShareImageEditor';
import {
  buildDietSharePresentation,
  type DietShareRecord,
} from './dietSharePresentation';
import { SwipeBackSurface } from './SwipeBackSurface';

export type ComposerPhase =
  | 'loading_photo'
  | 'editing'
  | 'rendering'
  | 'preview'
  | 'failed';

export type DietSharePhotoSource = {
  uri: string;
  headers?: Record<string, string>;
};

type ShareFeedback = {
  title: string;
  detail: string;
  tone: 'success' | 'warning';
};

type ShareTerminal = {
  phase: 'completed' | 'failed' | 'cancelled';
  duration_ms: number;
  has_photo: boolean;
  share_target?: 'generic';
  error_code?: 'poster_render_failed' | 'poster_save_failed' | 'poster_share_failed';
};

export type DietShareComposerProps = {
  visible: boolean;
  record: DietShareRecord;
  dateLabel: string;
  photoSource: DietSharePhotoSource;
  onClose: () => void;
  onShareText?: () => void | Promise<void>;
  onAskReva?: () => void;
  onShareFeedback?: (feedback: ShareFeedback) => void;
  onShareTerminal?: (meta: ShareTerminal) => void;
};

type SessionResources = {
  materializedCleanup?: () => Promise<void>;
  editedCleanup?: () => Promise<void>;
  capturedUri?: string;
};

type FailureKind = 'photo_load_failed' | 'poster_render_failed';
type BusyAction = 'save' | 'share' | 'text';
type BusyLock = { action: BusyAction; generation: number };

function releaseCaptureSafely(uri: string) {
  try {
    releaseCapture(uri);
  } catch {
    console.warn('[DietShareComposer] resource cleanup failed');
  }
}

function headerFingerprint(headers: Record<string, string> | undefined): string {
  if (!headers) return '';
  let hash = 2166136261;
  Object.entries(headers)
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([key, value]) => {
      [key, ':', value, '|'].forEach((part) => {
        for (let index = 0; index < part.length; index += 1) {
          hash ^= part.charCodeAt(index);
          hash = Math.imul(hash, 16777619);
        }
      });
    });
  return (hash >>> 0).toString(16);
}

function isNativeShareCancellation(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const candidate = error as { code?: unknown; name?: unknown; message?: unknown };
  const signal = [candidate.code, candidate.name, candidate.message]
    .filter((value): value is string => typeof value === 'string')
    .join(' ')
    .toLowerCase();
  return /cancel(?:ed|led)?|dismiss(?:ed)?/.test(signal);
}

function shareTextForRecord(record: DietShareRecord): string {
  const presentation = buildDietSharePresentation(record);
  return [
    presentation.headline,
    presentation.foodLine,
    ...presentation.macroLines,
    presentation.nextAction,
    presentation.disclosure,
  ].filter((line): line is string => Boolean(line)).join('\n');
}

export function DietShareComposer({
  visible,
  record,
  dateLabel,
  photoSource,
  onClose,
  onShareText,
  onAskReva,
  onShareFeedback,
  onShareTerminal,
}: DietShareComposerProps) {
  const posterRef = useRef<View>(null);
  const sessionGenerationRef = useRef(0);
  const phaseRef = useRef<ComposerPhase>('loading_photo');
  const captureInFlightRef = useRef<number | null>(null);
  const captureAttemptSequenceRef = useRef(0);
  const closeInFlightRef = useRef(false);
  const mountedRef = useRef(true);
  const wasVisibleRef = useRef(false);
  const busyActionRef = useRef<BusyLock | null>(null);
  const resourcesRef = useRef<SessionResources>({});
  const latestPhotoSourceRef = useRef(photoSource);
  const [phase, setPhase] = useState<ComposerPhase>('loading_photo');
  const [failureKind, setFailureKind] = useState<FailureKind>('photo_load_failed');
  const [localPhotoUri, setLocalPhotoUri] = useState<string | null>(null);
  const [editedResult, setEditedResult] = useState<DietShareImageEditorResult | null>(null);
  const [capturedUri, setCapturedUri] = useState<string | null>(null);
  const [retryGeneration, setRetryGeneration] = useState(0);
  const [busyAction, setBusyAction] = useState<BusyAction | null>(null);
  const headersFingerprint = headerFingerprint(photoSource.headers);
  latestPhotoSourceRef.current = photoSource;

  const transition = useCallback((next: ComposerPhase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const cleanupResources = useCallback(async () => {
    const resources = resourcesRef.current;
    resourcesRef.current = {};
    captureAttemptSequenceRef.current += 1;
    captureInFlightRef.current = null;
    if (resources.capturedUri) {
      releaseCaptureSafely(resources.capturedUri);
    }
    const cleanups = [resources.editedCleanup, resources.materializedCleanup]
      .filter((cleanup): cleanup is () => Promise<void> => Boolean(cleanup));
    await Promise.all(cleanups.map(async cleanup => {
      try {
        await cleanup();
      } catch {
        console.warn('[DietShareComposer] resource cleanup failed');
      }
    }));
  }, []);

  const beginAction = useCallback((action: BusyAction): number | null => {
    if (!mountedRef.current || closeInFlightRef.current || busyActionRef.current) return null;
    const generation = sessionGenerationRef.current;
    busyActionRef.current = { action, generation };
    setBusyAction(action);
    return generation;
  }, []);

  const finishAction = useCallback((action: BusyAction, generation: number) => {
    if (
      busyActionRef.current?.action !== action
      || busyActionRef.current.generation !== generation
    ) return;
    busyActionRef.current = null;
    if (sessionGenerationRef.current === generation) setBusyAction(null);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      closeInFlightRef.current = true;
      sessionGenerationRef.current += 1;
      void cleanupResources();
    };
  }, [cleanupResources]);

  useEffect(() => {
    const opening = visible && !wasVisibleRef.current;
    wasVisibleRef.current = visible;
    if (opening) closeInFlightRef.current = false;
    const generation = sessionGenerationRef.current + 1;
    sessionGenerationRef.current = generation;

    if (!visible || closeInFlightRef.current) {
      if (!visible) closeInFlightRef.current = true;
      void cleanupResources();
      return () => {
        sessionGenerationRef.current += 1;
        void cleanupResources();
      };
    }

    transition('loading_photo');
    setFailureKind('photo_load_failed');
    setLocalPhotoUri(null);
    setEditedResult(null);
    setCapturedUri(null);
    busyActionRef.current = null;
    setBusyAction(null);

    void (async () => {
      await cleanupResources();
      try {
        const activePhotoSource = latestPhotoSourceRef.current;
        const materialized = await materializeImageForLocalUse(activePhotoSource.uri, {
          headers: activePhotoSource.headers,
        });
        if (
          sessionGenerationRef.current !== generation
          || !mountedRef.current
          || closeInFlightRef.current
        ) {
          try {
            await materialized.cleanup();
          } catch {
            console.warn('[DietShareComposer] resource cleanup failed');
          }
          return;
        }
        resourcesRef.current.materializedCleanup = materialized.cleanup;
        setLocalPhotoUri(materialized.uri);
        transition('editing');
      } catch {
        if (
          sessionGenerationRef.current === generation
          && mountedRef.current
          && !closeInFlightRef.current
        ) {
          setFailureKind('photo_load_failed');
          transition('failed');
        }
      }
    })();

    return () => {
      sessionGenerationRef.current += 1;
      void cleanupResources();
    };
  }, [
    cleanupResources,
    dateLabel,
    headersFingerprint,
    photoSource.uri,
    record.id,
    retryGeneration,
    transition,
    visible,
  ]);

  const closeComposer = useCallback(async () => {
    if (closeInFlightRef.current) return;
    closeInFlightRef.current = true;
    sessionGenerationRef.current += 1;
    await cleanupResources();
    onClose();
  }, [cleanupResources, onClose]);

  const failRendering = useCallback(() => {
    if (!mountedRef.current || closeInFlightRef.current || phaseRef.current !== 'rendering') return;
    captureAttemptSequenceRef.current += 1;
    captureInFlightRef.current = null;
    setFailureKind('poster_render_failed');
    transition('failed');
  }, [transition]);

  const capturePoster = useCallback(async () => {
    const generation = sessionGenerationRef.current;
    if (
      phaseRef.current !== 'rendering'
      || !mountedRef.current
      || closeInFlightRef.current
      || captureInFlightRef.current !== null
      || resourcesRef.current.capturedUri
      || !posterRef.current
    ) return;
    const captureAttempt = captureAttemptSequenceRef.current + 1;
    captureAttemptSequenceRef.current = captureAttempt;
    captureInFlightRef.current = captureAttempt;
    const startedAt = Date.now();
    try {
      const uri = await captureRef(posterRef, {
        format: 'png',
        quality: 1,
        ...dietShareCaptureDimensions(),
        result: 'tmpfile',
      });
      if (
        sessionGenerationRef.current !== generation
        || !mountedRef.current
        || closeInFlightRef.current
        || phaseRef.current !== 'rendering'
        || captureAttemptSequenceRef.current !== captureAttempt
      ) {
        releaseCaptureSafely(uri);
        return;
      }
      resourcesRef.current.capturedUri = uri;
      setCapturedUri(uri);
      transition('preview');
    } catch {
      if (
        sessionGenerationRef.current === generation
        && mountedRef.current
        && !closeInFlightRef.current
        && phaseRef.current === 'rendering'
        && captureAttemptSequenceRef.current === captureAttempt
      ) {
        setFailureKind('poster_render_failed');
        transition('failed');
        onShareTerminal?.({
          phase: 'failed',
          duration_ms: Date.now() - startedAt,
          has_photo: true,
          share_target: 'generic',
          error_code: 'poster_render_failed',
        });
      }
    } finally {
      if (captureInFlightRef.current === captureAttempt) {
        captureInFlightRef.current = null;
      }
    }
  }, [onShareTerminal, transition]);

  const captureAfterDisplay = useCallback(() => {
    const generation = sessionGenerationRef.current;
    requestAnimationFrame(() => {
      if (
        sessionGenerationRef.current !== generation
        || !mountedRef.current
        || closeInFlightRef.current
        || phaseRef.current !== 'rendering'
      ) return;
      void capturePoster();
    });
  }, [capturePoster]);

  const completeEditing = useCallback((result: DietShareImageEditorResult) => {
    if (!mountedRef.current || closeInFlightRef.current || !visible || phaseRef.current !== 'editing') {
      void result.cleanup().catch(() => {
        console.warn('[DietShareComposer] resource cleanup failed');
      });
      return;
    }
    resourcesRef.current.editedCleanup = result.cleanup;
    setEditedResult(result);
    transition('rendering');
  }, [transition, visible]);

  const shareText = useCallback(async () => {
    const generation = beginAction('text');
    if (generation == null) return;
    try {
      if (onShareText) await onShareText();
      else {
        await Share.share({
          title: '分享饮食记录',
          message: shareTextForRecord(record),
        });
      }
    } catch {
      if (sessionGenerationRef.current === generation) {
        Alert.alert('正文分享失败', '请稍后重试');
      }
    } finally {
      finishAction('text', generation);
    }
  }, [beginAction, finishAction, onShareText, record]);

  const savePoster = useCallback(async () => {
    if (!capturedUri) return;
    const generation = beginAction('save');
    if (generation == null) return;
    const startedAt = Date.now();
    try {
      const permission = await MediaLibrary.requestPermissionsAsync(true);
      if (sessionGenerationRef.current !== generation) return;
      if (!permission.granted && permission.status !== 'granted') {
        onShareFeedback?.({ title: '需要相册权限', detail: '允许访问相册后再保存海报', tone: 'warning' });
        return;
      }
      await MediaLibrary.saveToLibraryAsync(capturedUri);
      if (sessionGenerationRef.current !== generation) return;
      onShareFeedback?.({ title: '海报已保存', detail: '可从相册选择并发布', tone: 'success' });
      onShareTerminal?.({
        phase: 'completed',
        duration_ms: Date.now() - startedAt,
        has_photo: true,
        share_target: 'generic',
      });
    } catch {
      if (sessionGenerationRef.current !== generation) return;
      onShareTerminal?.({
        phase: 'failed',
        duration_ms: Date.now() - startedAt,
        has_photo: true,
        share_target: 'generic',
        error_code: 'poster_save_failed',
      });
      Alert.alert('保存失败', '请检查相册权限后重试');
    } finally {
      finishAction('save', generation);
    }
  }, [beginAction, capturedUri, finishAction, onShareFeedback, onShareTerminal]);

  const sharePoster = useCallback(async () => {
    if (!capturedUri) return;
    const generation = beginAction('share');
    if (generation == null) return;
    const startedAt = Date.now();
    try {
      if (Platform.OS === 'ios') {
        const result = await Share.share(
          { url: capturedUri },
          { dialogTitle: '分享饮食海报' },
        );
        if (sessionGenerationRef.current !== generation) return;
        if (result.action === Share.dismissedAction) {
          onShareTerminal?.({
            phase: 'cancelled',
            duration_ms: Date.now() - startedAt,
            has_photo: true,
            share_target: 'generic',
          });
          return;
        }
        onShareTerminal?.({
          phase: 'completed',
          duration_ms: Date.now() - startedAt,
          has_photo: true,
          share_target: 'generic',
        });
      } else {
        if (!await Sharing.isAvailableAsync()) throw new Error('sharing_unavailable');
        if (sessionGenerationRef.current !== generation) return;
        await Sharing.shareAsync(capturedUri, {
          mimeType: 'image/png',
          UTI: 'public.png',
          dialogTitle: '分享饮食海报',
        });
        // expo-sharing resolves void for both share and cancel. Do not report
        // a false success when the native boundary cannot distinguish them.
      }
    } catch (error) {
      if (sessionGenerationRef.current !== generation) return;
      if (isNativeShareCancellation(error)) {
        onShareTerminal?.({
          phase: 'cancelled',
          duration_ms: Date.now() - startedAt,
          has_photo: true,
          share_target: 'generic',
        });
        return;
      }
      onShareTerminal?.({
        phase: 'failed',
        duration_ms: Date.now() - startedAt,
        has_photo: true,
        share_target: 'generic',
        error_code: 'poster_share_failed',
      });
      Alert.alert('分享失败', '请稍后重试');
    } finally {
      finishAction('share', generation);
    }
  }, [beginAction, capturedUri, finishAction, onShareTerminal]);

  const retry = useCallback(() => {
    if (!mountedRef.current || closeInFlightRef.current) return;
    if (failureKind === 'poster_render_failed' && editedResult) {
      transition('rendering');
      return;
    }
    setRetryGeneration(value => value + 1);
  }, [editedResult, failureKind, transition]);

  if (!visible) return null;

  return (
    <Modal visible animationType="slide" onRequestClose={() => { void closeComposer(); }}>
      <StatusBar style="dark" backgroundColor={C.paper} />
      <SwipeBackSurface
        testID="diet-share-composer-swipe-back"
        enabled={busyAction === null}
        onBack={() => { void closeComposer(); }}
        style={styles.root}
      >
        <SafeAreaView style={styles.root}>
          <View style={styles.header}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="关闭饮食分享编辑器"
              onPress={() => { void closeComposer(); }}
              hitSlop={8}
              style={({ pressed }) => [styles.closeButton, pressed ? styles.buttonPressed : null]}
            >
              <Ionicons name="chevron-back" size={24} color={C.ink1} />
            </Pressable>
            <View style={styles.titleGroup}>
              <Text style={styles.title}>分享这餐</Text>
              <Text style={styles.subtitle}>确认画面无误后再发布</Text>
            </View>
            <View style={styles.headerSpacer} />
          </View>

          {phase === 'loading_photo' ? (
            <View style={styles.centered}>
              <ActivityIndicator color={C.green500} />
              <Text style={styles.statusText}>正在安全加载照片…</Text>
            </View>
          ) : null}

          {phase === 'editing' && localPhotoUri ? (
            <DietShareImageEditor
              visible
              sourceUri={localPhotoUri}
              onComplete={completeEditing}
              onCancel={() => { void closeComposer(); }}
            />
          ) : null}

          {phase === 'rendering' && editedResult ? (
            <View style={styles.renderingWrap}>
              <View ref={posterRef} collapsable={false} style={styles.posterSurface}>
                <DietShareCard
                  record={record}
                  dateLabel={dateLabel}
                  imageSource={{ uri: editedResult.editedUri }}
                  redactions={editedResult.redactions}
                  onImageReady={captureAfterDisplay}
                  onImageError={failRendering}
                />
              </View>
              <View style={styles.renderingStatus} pointerEvents="none">
                <ActivityIndicator color={C.greenOn} />
                <Text style={styles.renderingText}>正在生成海报…</Text>
              </View>
            </View>
          ) : null}

          {phase === 'preview' && capturedUri ? (
            <ScrollView
              style={styles.previewScroll}
              contentContainerStyle={styles.previewContent}
              showsVerticalScrollIndicator={false}
            >
              <View style={styles.readyBadge}>
                <Ionicons name="checkmark-circle" size={17} color={C.green600} />
                <Text style={styles.readyBadgeText}>分享图已生成</Text>
              </View>
              <View style={styles.previewFrame}>
                <Image
                  testID="diet-share-captured-preview"
                  source={{ uri: capturedUri }}
                  contentFit="contain"
                  style={styles.previewImage}
                />
              </View>
              <View style={styles.privacyNotice}>
                <Ionicons name="shield-checkmark-outline" size={16} color={C.green600} />
                <Text style={styles.privacyNoticeText}>
                  公开分享前，再确认图片中没有人脸、地址或二维码
                </Text>
              </View>
              <View style={styles.actionRow}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="保存海报到相册"
                  accessibilityState={{ disabled: busyAction !== null }}
                  disabled={busyAction !== null}
                  onPress={() => { void savePoster(); }}
                  style={({ pressed }) => [
                    styles.secondaryAction,
                    pressed ? styles.buttonPressed : null,
                    busyAction !== null ? styles.buttonDisabled : null,
                  ]}
                >
                  <Ionicons name="download-outline" size={19} color={C.ink2} />
                  <Text style={styles.secondaryActionText}>
                    {busyAction === 'save' ? '保存中…' : '存到相册'}
                  </Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="分享饮食海报"
                  accessibilityState={{ disabled: busyAction !== null }}
                  disabled={busyAction !== null}
                  onPress={() => { void sharePoster(); }}
                  style={({ pressed }) => [
                    styles.primaryAction,
                    pressed ? styles.buttonPressed : null,
                    busyAction !== null ? styles.buttonDisabled : null,
                  ]}
                >
                  <Ionicons name="share-outline" size={19} color={C.greenOn} />
                  <Text style={styles.primaryActionText}>
                    {busyAction === 'share' ? '分享中…' : '分享海报'}
                  </Text>
                </Pressable>
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="分享饮食文字"
                accessibilityState={{ disabled: busyAction !== null }}
                disabled={busyAction !== null}
                onPress={() => { void shareText(); }}
                style={({ pressed }) => [styles.textActionButton, pressed ? styles.buttonPressed : null]}
              >
                <Ionicons name="document-text-outline" size={17} color={C.green600} />
                <Text style={styles.textAction}>{busyAction === 'text' ? '分享中…' : '仅分享文字'}</Text>
              </Pressable>
              {onAskReva ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="问小巴复盘今日饮食"
                  onPress={onAskReva}
                  style={({ pressed }) => [styles.textActionButton, pressed ? styles.buttonPressed : null]}
                >
                  <Ionicons name="sparkles-outline" size={17} color={C.green600} />
                  <Text style={styles.textAction}>问小巴复盘今日饮食</Text>
                </Pressable>
              ) : null}
            </ScrollView>
          ) : null}

          {phase === 'failed' ? (
            <View style={styles.centered}>
              <View style={styles.failureIcon}>
                <Ionicons name="image-outline" size={25} color={C.green600} />
              </View>
              <Text style={styles.failureTitle}>
                {failureKind === 'photo_load_failed' ? '照片加载失败' : '分享图生成失败'}
              </Text>
              <Text style={styles.failureDetail}>
                {failureKind === 'photo_load_failed'
                  ? '没有生成图片。你可以重试，或直接分享文字内容。'
                  : '照片编辑结果已保留，可以直接重新生成。'}
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={failureKind === 'photo_load_failed' ? '重试照片加载' : '重新生成分享图'}
                onPress={retry}
                style={({ pressed }) => [styles.primaryAction, styles.failurePrimary, pressed ? styles.buttonPressed : null]}
              >
                <Ionicons name="refresh-outline" size={19} color={C.greenOn} />
                <Text style={styles.primaryActionText}>
                  {failureKind === 'photo_load_failed' ? '重试' : '重新生成'}
                </Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="分享饮食文字"
                onPress={() => { void shareText(); }}
                style={({ pressed }) => [styles.textActionButton, pressed ? styles.buttonPressed : null]}
              >
                <Ionicons name="document-text-outline" size={17} color={C.green600} />
                <Text style={styles.textAction}>仅分享文字</Text>
              </Pressable>
            </View>
          ) : null}
        </SafeAreaView>
      </SwipeBackSurface>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.paper },
  header: {
    minHeight: 64,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  closeButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: -6,
    borderRadius: revaRadii.pill,
  },
  headerSpacer: { width: 44 },
  titleGroup: { alignItems: 'center', gap: 1 },
  title: {
    fontFamily: revaFonts.cjk,
    fontSize: 18,
    lineHeight: 23,
    fontWeight: '800',
    color: C.ink1,
  },
  subtitle: {
    fontFamily: revaFonts.cjk,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '500',
    color: C.ink3,
  },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, paddingHorizontal: 28 },
  statusText: { color: C.ink2, fontWeight: '600', fontFamily: revaFonts.cjk },
  failureIcon: {
    width: 52,
    height: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
  failureTitle: { fontSize: 19, color: C.ink1, fontWeight: '800', fontFamily: revaFonts.cjk },
  failureDetail: { color: C.ink2, lineHeight: 21, textAlign: 'center', fontFamily: revaFonts.cjk },
  renderingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  posterSurface: { width: '92%', maxWidth: 360, aspectRatio: 3 / 4 },
  renderingStatus: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: 'rgba(38, 29, 22, 0.42)',
  },
  renderingText: { color: C.greenOn, fontWeight: '800', fontFamily: revaFonts.cjk },
  previewScroll: { flex: 1 },
  previewContent: {
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 28,
    gap: 12,
  },
  readyBadge: {
    minHeight: 30,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    alignSelf: 'flex-start',
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    borderRadius: revaRadii.pill,
  },
  readyBadgeText: {
    color: C.green700,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
    fontFamily: revaFonts.cjk,
  },
  previewFrame: {
    width: '100%',
    maxWidth: 390,
    padding: 8,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.lg,
    borderCurve: 'continuous',
    ...revaShadows.md,
  },
  previewImage: {
    width: '100%',
    aspectRatio: 3 / 4,
    backgroundColor: C.paper2,
    borderRadius: revaRadii.md,
    borderCurve: 'continuous',
  },
  privacyNotice: {
    width: '100%',
    maxWidth: 430,
    minHeight: 42,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: C.green50,
    borderRadius: revaRadii.md,
  },
  privacyNoticeText: {
    flex: 1,
    color: C.ink2,
    fontSize: 12,
    lineHeight: 18,
    fontFamily: revaFonts.cjk,
  },
  actionRow: { width: '100%', maxWidth: 430, flexDirection: 'row', gap: 10 },
  primaryAction: {
    flex: 1,
    minHeight: 46,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    borderRadius: revaRadii.md,
    borderCurve: 'continuous',
    backgroundColor: C.green600,
    ...revaShadows.sm,
  },
  primaryActionText: { color: C.greenOn, fontWeight: '800', fontFamily: revaFonts.cjk },
  secondaryAction: {
    flex: 1,
    minHeight: 46,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    borderRadius: revaRadii.md,
    borderCurve: 'continuous',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    backgroundColor: C.surface,
  },
  secondaryActionText: { color: C.ink2, fontWeight: '700', fontFamily: revaFonts.cjk },
  failurePrimary: { flex: 0, minWidth: 180, marginTop: 4 },
  textActionButton: {
    minHeight: 44,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: revaRadii.md,
  },
  textAction: { color: C.green600, fontWeight: '700', fontFamily: revaFonts.cjk },
  buttonPressed: { opacity: 0.72 },
  buttonDisabled: { opacity: 0.48 },
});
