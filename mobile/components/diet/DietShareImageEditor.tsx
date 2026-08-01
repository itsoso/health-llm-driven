import React, {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import {
  ActivityIndicator,
  Alert,
  LayoutChangeEvent,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Image, type ImageLoadEventData } from 'expo-image';
import * as FileSystem from 'expo-file-system/legacy';
import type { Action } from 'expo-image-manipulator';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  addDietShareRedaction,
  initialDietShareImageEdit,
  resetDietShareImageEdit,
  rotateDietShareImage,
  updateDietShareCrop,
  type DietShareImageEdit,
  type DietShareRedaction,
  type NormalizedPoint,
} from './dietShareImageEdit';

type EditorPhase = 'loading' | 'ready' | 'applying' | 'failed';
type FailureKind = 'load' | 'unsupported' | 'manipulation';
type Size = { width: number; height: number };

type EditHistory = {
  past: DietShareImageEdit[];
  current: DietShareImageEdit;
  future: DietShareImageEdit[];
};

type HistoryAction =
  | { type: 'replace'; edit: DietShareImageEdit }
  | { type: 'commit'; edit: DietShareImageEdit }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'reset' };

export type DietShareImageEditorResult = DietShareImageEdit & {
  editedUri: string;
  cleanup: () => Promise<void>;
};

export type DietShareImageEditorProps = {
  visible: boolean;
  sourceUri: string;
  initialEdit?: DietShareImageEdit;
  onComplete: (result: DietShareImageEditorResult) => void;
  onCancel: () => void;
};

let ImageManipulator: typeof import('expo-image-manipulator') | null = null;
try {
  // Guarded runtime loading keeps OTA bundles compatible with older native binaries.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  ImageManipulator = require('expo-image-manipulator');
} catch {
  ImageManipulator = null;
}

const AnimatedImage = Animated.createAnimatedComponent(Image);
const VIEWPORT_ASPECT_RATIO = 3 / 4;
const DEFAULT_BRUSH_WIDTH = 0.06;
const JPEG_COMPRESSION = 0.95;

function cloneEdit(edit: DietShareImageEdit): DietShareImageEdit {
  return {
    crop: { ...edit.crop },
    rotation: edit.rotation,
    redactions: edit.redactions.map(redaction => ({
      width: redaction.width,
      points: redaction.points.map(point => ({ ...point })),
    })),
  };
}

function sameEdit(left: DietShareImageEdit, right: DietShareImageEdit): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function historyReducer(state: EditHistory, action: HistoryAction): EditHistory {
  if (action.type === 'replace') {
    return { past: [], current: cloneEdit(action.edit), future: [] };
  }
  if (action.type === 'commit') {
    if (sameEdit(state.current, action.edit)) return state;
    return {
      past: [...state.past, state.current],
      current: cloneEdit(action.edit),
      future: [],
    };
  }
  if (action.type === 'undo') {
    const previous = state.past[state.past.length - 1];
    if (!previous) return state;
    return {
      past: state.past.slice(0, -1),
      current: previous,
      future: [state.current, ...state.future],
    };
  }
  if (action.type === 'redo') {
    const next = state.future[0];
    if (!next) return state;
    return {
      past: [...state.past, state.current],
      current: next,
      future: state.future.slice(1),
    };
  }
  const identity = resetDietShareImageEdit(state.current);
  if (sameEdit(state.current, identity)) {
    return { ...state, future: [] };
  }
  return {
    past: [...state.past, state.current],
    current: identity,
    future: [],
  };
}

function validSize(width: number, height: number): Size | null {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }
  return { width, height };
}

function effectiveSize(source: Size, rotation: DietShareImageEdit['rotation']): Size {
  return rotation === 90 || rotation === 270
    ? { width: source.height, height: source.width }
    : source;
}

function baseCropForPoster(source: Size): { x: number; y: number; width: number; height: number } {
  const sourceRatio = source.width / source.height;
  if (sourceRatio > VIEWPORT_ASPECT_RATIO) {
    const width = source.height * VIEWPORT_ASPECT_RATIO;
    return { x: (source.width - width) / 2, y: 0, width, height: source.height };
  }
  const height = source.width / VIEWPORT_ASPECT_RATIO;
  return { x: 0, y: (source.height - height) / 2, width: source.width, height };
}

function pixelCrop(
  source: Size,
  crop: DietShareImageEdit['crop'],
): { originX: number; originY: number; width: number; height: number } {
  const base = baseCropForPoster(source);
  const exactX = base.x + crop.x * base.width;
  const exactY = base.y + crop.y * base.height;
  const exactRight = exactX + crop.width * base.width;
  const exactBottom = exactY + crop.height * base.height;
  const originX = Math.min(source.width - 1, Math.max(0, Math.floor(exactX)));
  const originY = Math.min(source.height - 1, Math.max(0, Math.floor(exactY)));
  const right = Math.min(source.width, Math.max(originX + 1, Math.ceil(exactRight)));
  const bottom = Math.min(source.height, Math.max(originY + 1, Math.ceil(exactBottom)));
  return {
    originX,
    originY,
    width: right - originX,
    height: bottom - originY,
  };
}

function normalizedPoint(event: { locationX?: number; locationY?: number }, viewport: Size): NormalizedPoint | null {
  const x = event.locationX;
  const y = event.locationY;
  if (typeof x !== 'number' || typeof y !== 'number' || viewport.width <= 0 || viewport.height <= 0) {
    return null;
  }
  return {
    x: Math.min(1, Math.max(0, x / viewport.width)),
    y: Math.min(1, Math.max(0, y / viewport.height)),
  };
}

function pathForRedaction(redaction: DietShareRedaction, viewport: Size): string {
  return redaction.points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x * viewport.width} ${point.y * viewport.height}`)
    .join(' ');
}

function ToolbarButton({
  label,
  disabled = false,
  onPress,
}: {
  label: string;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => [
        styles.toolbarButton,
        pressed ? styles.buttonPressed : null,
        disabled ? styles.buttonDisabled : null,
      ]}
    >
      <Text style={styles.toolbarButtonText}>{label}</Text>
    </Pressable>
  );
}

export function DietShareImageEditor({
  visible,
  sourceUri,
  initialEdit,
  onComplete,
  onCancel,
}: DietShareImageEditorProps) {
  const startingEdit = initialEdit ?? initialDietShareImageEdit();
  const initialEditKey = JSON.stringify(startingEdit);
  const [history, dispatch] = useReducer(historyReducer, {
    past: [],
    current: cloneEdit(startingEdit),
    future: [],
  });
  const [phase, setPhase] = useState<EditorPhase>('loading');
  const [failureKind, setFailureKind] = useState<FailureKind | null>(null);
  const [sourceSize, setSourceSize] = useState<Size | null>(null);
  const [viewportSize, setViewportSize] = useState<Size>({ width: 1, height: 1 });
  const [privacyMode, setPrivacyMode] = useState(false);
  const [imageKey, setImageKey] = useState(0);
  const strokeRef = useRef<NormalizedPoint[]>([]);
  const applyingRef = useRef(false);
  const gestureScale = useSharedValue(1);
  const gestureTranslateX = useSharedValue(0);
  const gestureTranslateY = useSharedValue(0);
  const gestureCommitted = useSharedValue(false);
  const currentEdit = history.current;

  useEffect(() => {
    if (!visible) return;
    dispatch({ type: 'replace', edit: startingEdit });
    setPhase('loading');
    setFailureKind(null);
    setSourceSize(null);
    setPrivacyMode(false);
    applyingRef.current = false;
    gestureScale.set(1);
    gestureTranslateX.set(0);
    gestureTranslateY.set(0);
    gestureCommitted.set(false);
  // startingEdit is represented by the stable serialization so object identity cannot reset edits.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, sourceUri, initialEditKey]);

  const hasChanges = !sameEdit(currentEdit, initialDietShareImageEdit());
  const canEdit = phase === 'ready';

  const commitGestureCrop = useCallback((scale: number, translateX: number, translateY: number) => {
    if (!Number.isFinite(scale) || scale <= 0) return;
    const current = currentEdit;
    const nextWidth = current.crop.width / Math.max(1, scale);
    const nextHeight = current.crop.height / Math.max(1, scale);
    const next = updateDietShareCrop(current, {
      x: current.crop.x + (current.crop.width - nextWidth) / 2
        - (translateX / viewportSize.width) * nextWidth,
      y: current.crop.y + (current.crop.height - nextHeight) / 2
        - (translateY / viewportSize.height) * nextHeight,
      width: nextWidth,
      height: nextHeight,
    });
    dispatch({ type: 'commit', edit: next });
  }, [currentEdit, viewportSize.height, viewportSize.width]);

  const panGesture = useMemo(() => Gesture.Pan()
    .onBegin(() => {
      gestureCommitted.set(false);
      gestureTranslateX.set(0);
      gestureTranslateY.set(0);
    })
    .onUpdate((event) => {
      gestureTranslateX.set(event.translationX);
      gestureTranslateY.set(event.translationY);
    })
    .onFinalize(() => {
      if (!gestureCommitted.get()) {
        gestureCommitted.set(true);
        runOnJS(commitGestureCrop)(
          gestureScale.get(),
          gestureTranslateX.get(),
          gestureTranslateY.get(),
        );
      }
      gestureScale.set(1);
      gestureTranslateX.set(0);
      gestureTranslateY.set(0);
    }), [commitGestureCrop, gestureCommitted, gestureScale, gestureTranslateX, gestureTranslateY]);

  const pinchGesture = useMemo(() => Gesture.Pinch()
    .onBegin(() => {
      gestureCommitted.set(false);
      gestureScale.set(1);
    })
    .onUpdate((event) => {
      gestureScale.set(Math.max(1, event.scale));
    })
    .onFinalize(() => {
      if (!gestureCommitted.get()) {
        gestureCommitted.set(true);
        runOnJS(commitGestureCrop)(
          gestureScale.get(),
          gestureTranslateX.get(),
          gestureTranslateY.get(),
        );
      }
      gestureScale.set(1);
      gestureTranslateX.set(0);
      gestureTranslateY.set(0);
    }), [commitGestureCrop, gestureCommitted, gestureScale, gestureTranslateX, gestureTranslateY]);

  const composedGesture = useMemo(
    () => Gesture.Simultaneous(panGesture, pinchGesture),
    [panGesture, pinchGesture],
  );

  const animatedImageStyle = useAnimatedStyle(() => ({
    opacity: phase === 'failed' ? 0.72 : 1,
    transform: [
      { rotate: `${currentEdit.rotation}deg` },
      { scale: gestureScale.get() },
      { translateX: gestureTranslateX.get() },
      { translateY: gestureTranslateY.get() },
    ],
  }));

  const imageLayoutStyle = useMemo(() => {
    if (!sourceSize) return styles.imageFill;
    const effective = effectiveSize(sourceSize, currentEdit.rotation);
    const coverScale = Math.max(
      viewportSize.width / effective.width,
      viewportSize.height / effective.height,
    );
    return {
      position: 'absolute' as const,
      width: sourceSize.width * coverScale,
      height: sourceSize.height * coverScale,
      left: (viewportSize.width - sourceSize.width * coverScale) / 2,
      top: (viewportSize.height - sourceSize.height * coverScale) / 2,
    };
  }, [currentEdit.rotation, sourceSize, viewportSize.height, viewportSize.width]);

  const onPhotoLoad = useCallback((event: ImageLoadEventData) => {
    const nextSize = validSize(event.source.width, event.source.height);
    if (!nextSize) {
      setFailureKind('load');
      setPhase('failed');
      return;
    }
    setSourceSize(nextSize);
    setFailureKind(null);
    setPhase('ready');
  }, []);

  const onViewportLayout = useCallback((event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    const next = validSize(width, height);
    if (!next) return;
    setViewportSize(previous => (
      previous.width === next.width && previous.height === next.height ? previous : next
    ));
  }, []);

  const onStrokeLayout = useCallback((event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    const next = validSize(width, height);
    if (!next) return;
    setViewportSize(previous => (
      previous.width === next.width && previous.height === next.height ? previous : next
    ));
  }, []);

  const beginStroke = useCallback((event: { nativeEvent: { locationX?: number; locationY?: number } }) => {
    const point = normalizedPoint(event.nativeEvent, viewportSize);
    strokeRef.current = point ? [point] : [];
  }, [viewportSize]);

  const continueStroke = useCallback((event: { nativeEvent: { locationX?: number; locationY?: number } }) => {
    const point = normalizedPoint(event.nativeEvent, viewportSize);
    if (point) strokeRef.current.push(point);
  }, [viewportSize]);

  const finishStroke = useCallback((event: { nativeEvent: { locationX?: number; locationY?: number } }) => {
    const point = normalizedPoint(event.nativeEvent, viewportSize);
    if (point) strokeRef.current.push(point);
    const next = addDietShareRedaction(currentEdit, {
      points: strokeRef.current,
      width: DEFAULT_BRUSH_WIDTH,
    });
    strokeRef.current = [];
    dispatch({ type: 'commit', edit: next });
  }, [currentEdit, viewportSize]);

  const requestCancel = useCallback(() => {
    if (!hasChanges) {
      onCancel();
      return;
    }
    Alert.alert(
      '放弃图片编辑？',
      '未保存的裁剪、旋转和隐私涂抹会丢失。',
      [
        { text: '继续编辑', style: 'cancel' },
        { text: '丢弃编辑', style: 'destructive', onPress: onCancel },
      ],
    );
  }, [hasChanges, onCancel]);

  const retry = useCallback(() => {
    setFailureKind(null);
    if (failureKind === 'load') {
      setSourceSize(null);
      setImageKey(previous => previous + 1);
      setPhase('loading');
      return;
    }
    setPhase('ready');
  }, [failureKind]);

  const applyEdit = useCallback(async () => {
    if (phase !== 'ready' || applyingRef.current || !sourceSize) return;
    applyingRef.current = true;
    const manipulator = ImageManipulator;
    if (!manipulator || typeof manipulator.manipulateAsync !== 'function') {
      applyingRef.current = false;
      setFailureKind('unsupported');
      setPhase('failed');
      return;
    }

    setPhase('applying');
    const edit = cloneEdit(currentEdit);
    const rotatedSize = effectiveSize(sourceSize, edit.rotation);
    const crop = pixelCrop(rotatedSize, edit.crop);
    const actions: Action[] = [];
    if (edit.rotation !== 0) actions.push({ rotate: edit.rotation });
    actions.push({ crop });

    try {
      const result = await manipulator.manipulateAsync(sourceUri, actions, {
        compress: JPEG_COMPRESSION,
        format: manipulator.SaveFormat.JPEG,
      });
      const outputUri = result.uri;
      if (!outputUri) throw new Error('image_edit_result_missing');
      onComplete({
        ...edit,
        editedUri: outputUri,
        cleanup: outputUri === sourceUri
          ? async () => undefined
          : async () => FileSystem.deleteAsync(outputUri, { idempotent: true }),
      });
    } catch {
      applyingRef.current = false;
      setFailureKind('manipulation');
      setPhase('failed');
      // URI, food and record identifiers must never enter editor diagnostics.
      console.warn('[DietShareImageEditor] image manipulation failed');
    }
  }, [currentEdit, onComplete, phase, sourceSize, sourceUri]);

  const failureTitle = failureKind === 'load'
    ? '照片加载失败'
    : failureKind === 'unsupported'
      ? '当前版本暂不支持图片编辑'
      : '图片编辑失败';
  const failureDetail = failureKind === 'load'
    ? '请重新加载，或取消后重新选择照片。'
    : failureKind === 'unsupported'
      ? '请更新应用，或取消后改为分享正文。'
      : '请重试，或取消后重新选择照片。';

  return (
    <Modal
      testID="diet-share-image-editor-modal"
      visible={visible}
      animationType="slide"
      presentationStyle="fullScreen"
      onRequestClose={requestCancel}
    >
      <SafeAreaView testID="diet-share-editor-root" style={styles.root}>
        <View style={styles.header}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="取消图片编辑"
            onPress={requestCancel}
            style={({ pressed }) => [styles.headerButton, pressed ? styles.buttonPressed : null]}
          >
            <Text style={styles.headerButtonText}>取消</Text>
          </Pressable>
          <Text style={styles.title}>编辑分享照片</Text>
          <View style={styles.headerSpacer} />
        </View>

        <Text style={styles.privacyReminder}>公开分享前，请检查人脸、地址、条码和二维码。</Text>

        <View style={styles.previewArea}>
          <View
            testID="diet-share-editor-viewport"
            accessibilityLabel="图片编辑状态"
            accessibilityValue={{
              text: `旋转 ${history.current.rotation} 度，隐私涂抹 ${history.current.redactions.length} 条`,
            }}
            onLayout={onViewportLayout}
            style={styles.viewport}
          >
            <GestureDetector gesture={composedGesture}>
              <AnimatedImage
                key={`${sourceUri}:${imageKey}`}
                testID="diet-share-editor-image"
                source={{ uri: sourceUri }}
                contentFit="fill"
                cachePolicy="memory-disk"
                onLoad={onPhotoLoad}
                onError={() => {
                  if (phase === 'applying') return;
                  setFailureKind('load');
                  setPhase('failed');
                }}
                style={[imageLayoutStyle, animatedImageStyle]}
              />
            </GestureDetector>

            <View
              testID="diet-share-privacy-canvas"
              pointerEvents={privacyMode && canEdit ? 'auto' : 'none'}
              onLayout={onStrokeLayout}
              onStartShouldSetResponder={() => privacyMode && canEdit}
              onMoveShouldSetResponder={() => privacyMode && canEdit}
              onResponderGrant={beginStroke}
              onResponderMove={continueStroke}
              onResponderRelease={finishStroke}
              style={styles.privacyCanvas}
            >
              <Svg width="100%" height="100%">
                {history.current.redactions.map((redaction, index) => (
                  <Path
                    key={`${index}:${redaction.points.length}`}
                    testID={`diet-share-redaction-path-${index}`}
                    d={pathForRedaction(redaction, viewportSize)}
                    fill="none"
                    stroke="#000000"
                    strokeOpacity={1}
                    strokeWidth={redaction.width * Math.min(viewportSize.width, viewportSize.height)}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}
              </Svg>
            </View>

            {phase === 'loading' ? (
              <View style={styles.statusOverlay}>
                <ActivityIndicator color="#FFFFFF" />
                <Text style={styles.statusText}>正在加载照片…</Text>
              </View>
            ) : null}
            {phase === 'applying' ? (
              <View style={styles.statusOverlay}>
                <ActivityIndicator color="#FFFFFF" />
                <Text style={styles.statusText}>正在应用图片编辑…</Text>
              </View>
            ) : null}
            {phase === 'failed' ? (
              <View style={styles.failureOverlay}>
                <Text style={styles.failureTitle}>{failureTitle}</Text>
                <Text style={styles.failureDetail}>{failureDetail}</Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={failureKind === 'load' ? '重新加载照片' : '重试图片编辑'}
                  onPress={retry}
                  style={({ pressed }) => [styles.retryButton, pressed ? styles.buttonPressed : null]}
                >
                  <Text style={styles.retryButtonText}>{failureKind === 'load' ? '重新加载' : '重试'}</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        </View>

        <View testID="diet-share-editor-toolbar" style={styles.toolbar}>
          <ToolbarButton
            label="顺时针旋转照片"
            disabled={!canEdit}
            onPress={() => dispatch({ type: 'commit', edit: rotateDietShareImage(history.current) })}
          />
          <ToolbarButton
            label="隐私涂抹"
            disabled={!canEdit}
            onPress={() => setPrivacyMode(current => !current)}
          />
          <ToolbarButton
            label="撤销图片编辑"
            disabled={!canEdit || history.past.length === 0}
            onPress={() => dispatch({ type: 'undo' })}
          />
          <ToolbarButton
            label="重做图片编辑"
            disabled={!canEdit || history.future.length === 0}
            onPress={() => dispatch({ type: 'redo' })}
          />
          <ToolbarButton
            label="重置图片编辑"
            disabled={!canEdit || !hasChanges}
            onPress={() => dispatch({ type: 'reset' })}
          />
        </View>

        <View testID="diet-share-editor-actions" style={styles.actions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="完成图片编辑"
            accessibilityState={{ disabled: !canEdit }}
            disabled={!canEdit}
            onPress={canEdit ? applyEdit : undefined}
            style={({ pressed }) => [
              styles.completeButton,
              pressed ? styles.buttonPressed : null,
              !canEdit ? styles.buttonDisabled : null,
            ]}
          >
            <Text style={styles.completeButtonText}>完成</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#171817',
  },
  header: {
    minHeight: 52,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerButton: {
    minWidth: 64,
    minHeight: 44,
    justifyContent: 'center',
  },
  headerButtonText: {
    color: '#F5F5F2',
    fontSize: 16,
    fontWeight: '600',
  },
  headerSpacer: {
    width: 64,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  privacyReminder: {
    color: '#D9DBD7',
    fontSize: 13,
    lineHeight: 19,
    paddingHorizontal: 20,
    paddingBottom: 10,
    textAlign: 'center',
  },
  previewArea: {
    flex: 1,
    minHeight: 0,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  viewport: {
    width: '100%',
    maxWidth: 430,
    maxHeight: '100%',
    aspectRatio: VIEWPORT_ASPECT_RATIO,
    flexShrink: 1,
    overflow: 'hidden',
    backgroundColor: '#2A2C2A',
    borderRadius: 18,
    borderCurve: 'continuous',
  },
  imageFill: {
    ...StyleSheet.absoluteFillObject,
  },
  privacyCanvas: {
    ...StyleSheet.absoluteFillObject,
  },
  statusOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: 'rgba(0,0,0,0.42)',
  },
  statusText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  failureOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 24,
    backgroundColor: 'rgba(0,0,0,0.62)',
  },
  failureTitle: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
  failureDetail: {
    color: '#E2E3E0',
    fontSize: 13,
    lineHeight: 19,
    textAlign: 'center',
  },
  retryButton: {
    minHeight: 42,
    marginTop: 6,
    paddingHorizontal: 22,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5F5F2',
    borderRadius: 21,
    borderCurve: 'continuous',
  },
  retryButtonText: {
    color: '#171817',
    fontSize: 14,
    fontWeight: '700',
  },
  toolbar: {
    flexShrink: 0,
    minHeight: 94,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 8,
  },
  toolbarButton: {
    minHeight: 36,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#303330',
    borderRadius: 18,
    borderCurve: 'continuous',
  },
  toolbarButtonText: {
    color: '#F2F3EF',
    fontSize: 12,
    fontWeight: '600',
  },
  actions: {
    flexShrink: 0,
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 10,
  },
  completeButton: {
    minHeight: 50,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#238B68',
    borderRadius: 25,
    borderCurve: 'continuous',
  },
  completeButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  buttonPressed: {
    opacity: 0.72,
  },
  buttonDisabled: {
    opacity: 0.42,
  },
});
