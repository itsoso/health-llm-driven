import React, {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { Ionicons } from '@expo/vector-icons';
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
import { StatusBar } from 'expo-status-bar';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';
import {
  initialWindowMetrics,
  SafeAreaView,
  useSafeAreaInsets,
} from 'react-native-safe-area-context';

import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
} from '../../constants/revaTheme';

import {
  addDietShareRedaction,
  baseDietShareCropForPoster,
  effectiveDietShareImageSize,
  initialDietShareImageEdit,
  resetDietShareImageEdit,
  rotateDietShareImage,
  updateDietShareCrop,
  type DietShareImageEdit,
  type DietShareRedaction,
  type NormalizedPoint,
} from './dietShareImageEdit';
import { SwipeBackSurface } from './SwipeBackSurface';

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

const VIEWPORT_ASPECT_RATIO = 3 / 4;
const DEFAULT_BRUSH_WIDTH = 0.06;
const JPEG_COMPRESSION = 0.95;
const MIN_CROP_FRACTION = 1 / 8;
const EDITOR_HORIZONTAL_PADDING = 32;
const EDITOR_FIXED_VERTICAL_SPACE = 246;

export function resolveDietShareEditorTopInset(
  contextTop: number,
  launchWindowTop: number | null | undefined = initialWindowMetrics?.insets.top,
): number {
  const safeContextTop = Number.isFinite(contextTop) ? Math.max(0, contextTop) : 0;
  const safeLaunchTop = Number.isFinite(launchWindowTop) ? Math.max(0, launchWindowTop ?? 0) : 0;
  return Math.max(safeContextTop, safeLaunchTop);
}

type GestureConstraint = {
  scale: number;
  translateX: number;
  translateY: number;
  crop: DietShareImageEdit['crop'];
};

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

function normalizedSquareCrop(crop: DietShareImageEdit['crop']): DietShareImageEdit['crop'] {
  if (
    !Number.isFinite(crop.x)
    || !Number.isFinite(crop.y)
    || !Number.isFinite(crop.width)
    || !Number.isFinite(crop.height)
    || crop.width <= 0
    || crop.height <= 0
  ) {
    return { x: 0, y: 0, width: 1, height: 1 };
  }
  const size = Math.max(
    MIN_CROP_FRACTION,
    Math.min(1, crop.width, crop.height),
  );
  return {
    x: Math.min(1 - size, Math.max(0, crop.x)),
    y: Math.min(1 - size, Math.max(0, crop.y)),
    width: size,
    height: size,
  };
}

function normalizeEditorEdit(edit: DietShareImageEdit): DietShareImageEdit {
  return {
    ...cloneEdit(edit),
    crop: normalizedSquareCrop(edit.crop),
  };
}

export function constrainDietShareGesture(
  edit: DietShareImageEdit,
  viewport: Size,
  requestedScale: number,
  requestedTranslateX: number,
  requestedTranslateY: number,
): GestureConstraint {
  'worklet';
  const rawWidth = Number.isFinite(edit.crop.width) ? edit.crop.width : 1;
  const rawHeight = Number.isFinite(edit.crop.height) ? edit.crop.height : 1;
  const size = Math.max(
    MIN_CROP_FRACTION,
    Math.min(1, rawWidth, rawHeight),
  );
  const x = Math.min(1 - size, Math.max(0, Number.isFinite(edit.crop.x) ? edit.crop.x : 0));
  const y = Math.min(1 - size, Math.max(0, Number.isFinite(edit.crop.y) ? edit.crop.y : 0));
  const minRelativeScale = size;
  const maxRelativeScale = size / MIN_CROP_FRACTION;
  const scale = Math.min(maxRelativeScale, Math.max(
    minRelativeScale,
    Number.isFinite(requestedScale) ? requestedScale : 1,
  ));
  const nextSize = size / scale;
  const inset = (size - nextSize) / 2;
  const safeWidth = Math.max(1, viewport.width);
  const safeHeight = Math.max(1, viewport.height);
  const minTranslateX = -safeWidth * (1 - nextSize - x - inset) / nextSize;
  const maxTranslateX = safeWidth * (x + inset) / nextSize;
  const minTranslateY = -safeHeight * (1 - nextSize - y - inset) / nextSize;
  const maxTranslateY = safeHeight * (y + inset) / nextSize;
  const translateX = Math.min(
    maxTranslateX,
    Math.max(minTranslateX, Number.isFinite(requestedTranslateX) ? requestedTranslateX : 0),
  );
  const translateY = Math.min(
    maxTranslateY,
    Math.max(minTranslateY, Number.isFinite(requestedTranslateY) ? requestedTranslateY : 0),
  );
  return {
    scale,
    translateX,
    translateY,
    crop: {
      x: x + inset - (translateX / safeWidth) * nextSize,
      y: y + inset - (translateY / safeHeight) * nextSize,
      width: nextSize,
      height: nextSize,
    },
  };
}

function historyReducer(state: EditHistory, action: HistoryAction): EditHistory {
  if (action.type === 'replace') {
    return { past: [], current: normalizeEditorEdit(action.edit), future: [] };
  }
  if (action.type === 'commit') {
    const edit = normalizeEditorEdit(action.edit);
    if (sameEdit(state.current, edit)) return state;
    return {
      past: [...state.past, state.current],
      current: edit,
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

function pixelCrop(
  source: Size,
  crop: DietShareImageEdit['crop'],
): { originX: number; originY: number; width: number; height: number } {
  const base = baseDietShareCropForPoster(source);
  const normalized = normalizedSquareCrop(crop);
  const exactX = base.x + normalized.x * base.width;
  const exactY = base.y + normalized.y * base.height;
  const exactRight = exactX + normalized.width * base.width;
  const exactBottom = exactY + normalized.height * base.height;
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

function previewImageLayout(
  source: Size,
  rotation: DietShareImageEdit['rotation'],
  crop: DietShareImageEdit['crop'],
  viewport: Size,
): { position: 'absolute'; width: number; height: number; left: number; top: number } {
  const effective = effectiveDietShareImageSize(source, rotation);
  const base = baseDietShareCropForPoster(effective);
  const normalized = normalizedSquareCrop(crop);
  const visibleCrop = {
    x: base.x + normalized.x * base.width,
    y: base.y + normalized.y * base.height,
    width: base.width * normalized.width,
    height: base.height * normalized.height,
  };
  const pixelScale = viewport.width / visibleCrop.width;
  const cropCenterX = visibleCrop.x + visibleCrop.width / 2;
  const cropCenterY = visibleCrop.y + visibleCrop.height / 2;
  const imageCenterX = viewport.width / 2 - (cropCenterX - effective.width / 2) * pixelScale;
  const imageCenterY = viewport.height / 2 - (cropCenterY - effective.height / 2) * pixelScale;
  const width = source.width * pixelScale;
  const height = source.height * pixelScale;
  return {
    position: 'absolute',
    width,
    height,
    left: imageCenterX - width / 2,
    top: imageCenterY - height / 2,
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
  displayLabel,
  icon,
  disabled = false,
  selected,
  onPress,
}: {
  label: string;
  displayLabel: string;
  icon: keyof typeof Ionicons.glyphMap;
  disabled?: boolean;
  selected?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{
        disabled,
        ...(typeof selected === 'boolean' ? { selected } : {}),
      }}
      disabled={disabled}
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => [
        styles.toolbarButton,
        selected ? styles.toolbarButtonSelected : null,
        pressed ? styles.buttonPressed : null,
        disabled ? styles.buttonDisabled : null,
      ]}
    >
      <Ionicons
        name={icon}
        size={20}
        color={selected ? C.greenBright : C.focusInk1}
      />
      <Text style={[styles.toolbarButtonText, selected ? styles.toolbarButtonTextSelected : null]}>
        {displayLabel}
      </Text>
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
  const safeAreaInsets = useSafeAreaInsets();
  const editorTopInset = resolveDietShareEditorTopInset(safeAreaInsets.top);
  const startingEdit = normalizeEditorEdit(initialEdit ?? initialDietShareImageEdit());
  const initialEditKey = JSON.stringify(startingEdit);
  const [history, dispatch] = useReducer(historyReducer, {
    past: [],
    current: startingEdit,
    future: [],
  });
  const [phase, setPhase] = useState<EditorPhase>('loading');
  const [failureKind, setFailureKind] = useState<FailureKind | null>(null);
  const [sourceSize, setSourceSize] = useState<Size | null>(null);
  const [viewportSize, setViewportSize] = useState<Size>({ width: 1, height: 1 });
  const [rootSize, setRootSize] = useState<Size | null>(null);
  const [privacyMode, setPrivacyMode] = useState(false);
  const [imageKey, setImageKey] = useState(0);
  const imageRequestRef = useRef({ sourceUri, imageKey, generation: 0 });
  if (
    imageRequestRef.current.sourceUri !== sourceUri
    || imageRequestRef.current.imageKey !== imageKey
  ) {
    imageRequestRef.current = {
      sourceUri,
      imageKey,
      generation: imageRequestRef.current.generation + 1,
    };
  }
  const imageRequestGeneration = imageRequestRef.current.generation;
  const strokeRef = useRef<NormalizedPoint[]>([]);
  const applyingRef = useRef(false);
  const operationGenerationRef = useRef(0);
  const visibleRef = useRef(visible);
  const baselineEditRef = useRef(startingEdit);
  const gestureScale = useSharedValue(1);
  const gestureTranslateX = useSharedValue(0);
  const gestureTranslateY = useSharedValue(0);
  const requestedTranslateX = useSharedValue(0);
  const requestedTranslateY = useSharedValue(0);
  const activeGestureCount = useSharedValue(0);
  const currentEdit = history.current;
  visibleRef.current = visible;

  useEffect(() => {
    if (!visible) return;
    operationGenerationRef.current += 1;
    baselineEditRef.current = startingEdit;
    dispatch({ type: 'replace', edit: startingEdit });
    setPhase('loading');
    setFailureKind(null);
    setSourceSize(null);
    setPrivacyMode(false);
    applyingRef.current = false;
    gestureScale.set(1);
    gestureTranslateX.set(0);
    gestureTranslateY.set(0);
    requestedTranslateX.set(0);
    requestedTranslateY.set(0);
    activeGestureCount.set(0);
  // startingEdit is represented by the stable serialization so object identity cannot reset edits.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, sourceUri, initialEditKey]);

  useEffect(() => () => {
    visibleRef.current = false;
    operationGenerationRef.current += 1;
  }, []);

  const hasChanges = !sameEdit(currentEdit, baselineEditRef.current);
  const canEdit = phase === 'ready';

  const commitGestureCrop = useCallback((scale: number, translateX: number, translateY: number) => {
    const constrained = constrainDietShareGesture(
      currentEdit,
      viewportSize,
      scale,
      translateX,
      translateY,
    );
    const next = updateDietShareCrop(currentEdit, constrained.crop);
    dispatch({ type: 'commit', edit: next });
  }, [currentEdit, viewportSize]);

  const panGesture = useMemo(() => Gesture.Pan()
    .onBegin(() => {
      if (activeGestureCount.get() === 0) {
        gestureScale.set(1);
        requestedTranslateX.set(0);
        requestedTranslateY.set(0);
        gestureTranslateX.set(0);
        gestureTranslateY.set(0);
      }
      activeGestureCount.set(activeGestureCount.get() + 1);
    })
    .onUpdate((event) => {
      requestedTranslateX.set(event.translationX);
      requestedTranslateY.set(event.translationY);
      const constrained = constrainDietShareGesture(
        currentEdit,
        viewportSize,
        gestureScale.get(),
        requestedTranslateX.get(),
        requestedTranslateY.get(),
      );
      gestureScale.set(constrained.scale);
      gestureTranslateX.set(constrained.translateX);
      gestureTranslateY.set(constrained.translateY);
    })
    .onFinalize(() => {
      const remainingGestures = Math.max(0, activeGestureCount.get() - 1);
      activeGestureCount.set(remainingGestures);
      if (remainingGestures === 0) {
        runOnJS(commitGestureCrop)(
          gestureScale.get(),
          gestureTranslateX.get(),
          gestureTranslateY.get(),
        );
        gestureScale.set(1);
        gestureTranslateX.set(0);
        gestureTranslateY.set(0);
        requestedTranslateX.set(0);
        requestedTranslateY.set(0);
      }
    }), [
      activeGestureCount,
      commitGestureCrop,
      currentEdit,
      gestureScale,
      gestureTranslateX,
      gestureTranslateY,
      requestedTranslateX,
      requestedTranslateY,
      viewportSize,
    ]);

  const pinchGesture = useMemo(() => Gesture.Pinch()
    .onBegin(() => {
      if (activeGestureCount.get() === 0) {
        gestureScale.set(1);
        requestedTranslateX.set(0);
        requestedTranslateY.set(0);
        gestureTranslateX.set(0);
        gestureTranslateY.set(0);
      }
      activeGestureCount.set(activeGestureCount.get() + 1);
    })
    .onUpdate((event) => {
      const constrained = constrainDietShareGesture(
        currentEdit,
        viewportSize,
        event.scale,
        requestedTranslateX.get(),
        requestedTranslateY.get(),
      );
      gestureScale.set(constrained.scale);
      gestureTranslateX.set(constrained.translateX);
      gestureTranslateY.set(constrained.translateY);
    })
    .onFinalize(() => {
      const remainingGestures = Math.max(0, activeGestureCount.get() - 1);
      activeGestureCount.set(remainingGestures);
      if (remainingGestures === 0) {
        runOnJS(commitGestureCrop)(
          gestureScale.get(),
          gestureTranslateX.get(),
          gestureTranslateY.get(),
        );
        gestureScale.set(1);
        gestureTranslateX.set(0);
        gestureTranslateY.set(0);
        requestedTranslateX.set(0);
        requestedTranslateY.set(0);
      }
    }), [
      activeGestureCount,
      commitGestureCrop,
      currentEdit,
      gestureScale,
      gestureTranslateX,
      gestureTranslateY,
      requestedTranslateX,
      requestedTranslateY,
      viewportSize,
    ]);

  const composedGesture = useMemo(
    () => Gesture.Simultaneous(panGesture, pinchGesture),
    [panGesture, pinchGesture],
  );

  const animatedGestureStyle = useAnimatedStyle(() => ({
    opacity: phase === 'failed' ? 0.72 : 1,
    transform: [
      { translateX: gestureTranslateX.get() },
      { translateY: gestureTranslateY.get() },
      { scale: gestureScale.get() },
    ],
  }));

  const imageLayoutStyle = useMemo(() => {
    if (!sourceSize) return styles.imageFill;
    return previewImageLayout(
      sourceSize,
      currentEdit.rotation,
      currentEdit.crop,
      viewportSize,
    );
  }, [currentEdit.crop, currentEdit.rotation, sourceSize, viewportSize]);

  const viewportFrame = useMemo(() => {
    if (!rootSize) return null;
    const availableWidth = Math.max(1, rootSize.width - EDITOR_HORIZONTAL_PADDING);
    const availableHeight = Math.max(1, rootSize.height - EDITOR_FIXED_VERTICAL_SPACE);
    const width = Math.min(430, availableWidth, availableHeight * VIEWPORT_ASPECT_RATIO);
    return { width, height: width / VIEWPORT_ASPECT_RATIO };
  }, [rootSize]);

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

  const onRootLayout = useCallback((event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    const next = validSize(width, height);
    if (!next) return;
    setRootSize(previous => (
      previous?.width === next.width && previous?.height === next.height ? previous : next
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
    if (phase === 'applying') return;
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
  }, [hasChanges, onCancel, phase]);

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
    const operationGeneration = operationGenerationRef.current + 1;
    operationGenerationRef.current = operationGeneration;
    const edit = cloneEdit(currentEdit);
    const rotatedSize = effectiveDietShareImageSize(sourceSize, edit.rotation);
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
      if (
        operationGeneration !== operationGenerationRef.current
        || !visibleRef.current
      ) {
        applyingRef.current = false;
        if (outputUri !== sourceUri) {
          try {
            await FileSystem.deleteAsync(outputUri, { idempotent: true });
          } catch {
            // Never include a local path or source identifier in stale-operation logs.
            console.warn('[DietShareImageEditor] stale edit cleanup failed');
          }
        }
        return;
      }
      onComplete({
        ...edit,
        editedUri: outputUri,
        cleanup: outputUri === sourceUri
          ? async () => undefined
          : async () => FileSystem.deleteAsync(outputUri, { idempotent: true }),
      });
    } catch {
      applyingRef.current = false;
      if (
        operationGeneration !== operationGenerationRef.current
        || !visibleRef.current
      ) return;
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
      <StatusBar style="light" backgroundColor={C.focusBg} />
      <SwipeBackSurface
        testID="diet-share-image-editor-swipe-back"
        enabled={phase !== 'applying'}
        resetBeforeBack={hasChanges}
        onBack={requestCancel}
        style={styles.root}
      >
        <SafeAreaView
          testID="diet-share-editor-root"
          edges={['bottom']}
          onLayout={onRootLayout}
          style={[styles.root, { paddingTop: editorTopInset }]}
        >
          <View style={styles.header}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="取消图片编辑"
              accessibilityState={{ disabled: phase === 'applying' }}
              disabled={phase === 'applying'}
              onPress={phase === 'applying' ? undefined : requestCancel}
              hitSlop={8}
              style={({ pressed }) => [
                styles.headerButton,
                pressed ? styles.buttonPressed : null,
                phase === 'applying' ? styles.buttonDisabled : null,
              ]}
            >
              <Ionicons name="chevron-back" size={22} color={C.focusInk1} />
              <Text style={styles.headerButtonText}>返回</Text>
            </Pressable>
            <View style={styles.titleGroup}>
              <Text style={styles.title}>调整照片</Text>
              <Text style={styles.subtitle}>裁剪与隐私处理</Text>
            </View>
            <View style={styles.headerSpacer} />
          </View>

          <View style={styles.privacyReminder}>
            <Ionicons name="shield-checkmark-outline" size={15} color={C.focusInk2} />
            <Text style={styles.privacyReminderText}>分享前请检查人脸、地址、条码与二维码</Text>
          </View>

          <View style={styles.previewArea}>
            <View
              testID="diet-share-editor-viewport"
              accessibilityLabel="图片编辑状态"
              accessibilityValue={{
                text: `旋转 ${history.current.rotation} 度，隐私涂抹 ${history.current.redactions.length} 条`,
              }}
              onLayout={onViewportLayout}
              style={[styles.viewport, viewportFrame]}
            >
            <GestureDetector gesture={composedGesture}>
              <Animated.View
                testID="diet-share-editor-transform"
                style={[styles.imageTransformLayer, animatedGestureStyle]}
              >
                <Image
                  key={imageRequestGeneration}
                  testID="diet-share-editor-image"
                  source={{ uri: sourceUri }}
                  contentFit="fill"
                  cachePolicy="memory-disk"
                  onLoad={(event) => {
                    if (
                      !visibleRef.current
                      || imageRequestGeneration !== imageRequestRef.current.generation
                    ) return;
                    onPhotoLoad(event);
                  }}
                  onError={() => {
                    if (
                      phase === 'applying'
                      || !visibleRef.current
                      || imageRequestGeneration !== imageRequestRef.current.generation
                    ) return;
                    setFailureKind('load');
                    setPhase('failed');
                  }}
                  style={[
                    imageLayoutStyle,
                    { transform: [{ rotate: `${currentEdit.rotation}deg` }] },
                  ]}
                />
              </Animated.View>
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
                    stroke={C.ink1}
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
                <ActivityIndicator color={C.greenOn} />
                <Text style={styles.statusText}>正在加载照片…</Text>
              </View>
            ) : null}
            {phase === 'applying' ? (
              <View style={styles.statusOverlay}>
                <ActivityIndicator color={C.greenOn} />
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
              <View pointerEvents="none" style={styles.viewportHint}>
                <Ionicons
                  name={privacyMode ? 'brush-outline' : 'move-outline'}
                  size={14}
                  color={C.focusInk1}
                />
                <Text style={styles.viewportHintText}>
                  {privacyMode ? '在图片上涂抹需要隐藏的信息' : '拖动调整构图 · 双指缩放'}
                </Text>
              </View>
            </View>
          </View>

          <View testID="diet-share-editor-toolbar" style={styles.toolbar}>
            <ToolbarButton
              label="顺时针旋转照片"
              displayLabel="旋转"
              icon="sync-outline"
              disabled={!canEdit}
              onPress={() => {
                if (!sourceSize) return;
                dispatch({ type: 'commit', edit: rotateDietShareImage(history.current, sourceSize) });
              }}
            />
            <ToolbarButton
              label="隐私涂抹"
              displayLabel="遮挡"
              icon="brush-outline"
              disabled={!canEdit}
              selected={privacyMode}
              onPress={() => setPrivacyMode(current => !current)}
            />
            <ToolbarButton
              label="撤销图片编辑"
              displayLabel="撤销"
              icon="arrow-undo-outline"
              disabled={!canEdit || history.past.length === 0}
              onPress={() => dispatch({ type: 'undo' })}
            />
            <ToolbarButton
              label="重做图片编辑"
              displayLabel="重做"
              icon="arrow-redo-outline"
              disabled={!canEdit || history.future.length === 0}
              onPress={() => dispatch({ type: 'redo' })}
            />
            <ToolbarButton
              label="重置图片编辑"
              displayLabel="重置"
              icon="refresh-outline"
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
              <Text style={styles.completeButtonText}>生成分享图</Text>
              <Ionicons name="arrow-forward" size={18} color={C.greenOn} />
            </Pressable>
          </View>
        </SafeAreaView>
      </SwipeBackSurface>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: C.focusBg,
  },
  header: {
    minHeight: 58,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerButton: {
    minWidth: 74,
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: -6,
  },
  headerButtonText: {
    color: C.focusInk1,
    fontSize: 16,
    fontWeight: '600',
    fontFamily: revaFonts.cjk,
  },
  headerSpacer: {
    width: 74,
  },
  titleGroup: {
    alignItems: 'center',
    gap: 1,
  },
  title: {
    color: C.greenOn,
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '800',
    fontFamily: revaFonts.cjk,
  },
  subtitle: {
    color: C.focusInk2,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '500',
    fontFamily: revaFonts.cjk,
  },
  privacyReminder: {
    minHeight: 36,
    marginHorizontal: 18,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    backgroundColor: C.focusBg2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    borderRadius: revaRadii.pill,
    borderCurve: 'continuous',
  },
  privacyReminderText: {
    color: C.focusInk2,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '500',
    fontFamily: revaFonts.cjk,
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
    backgroundColor: C.focusBg2,
    borderRadius: 18,
    borderCurve: 'continuous',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    ...revaShadows.focus,
  },
  imageFill: {
    ...StyleSheet.absoluteFillObject,
  },
  imageTransformLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  privacyCanvas: {
    ...StyleSheet.absoluteFillObject,
  },
  viewportHint: {
    position: 'absolute',
    left: 12,
    right: 12,
    bottom: 12,
    minHeight: 30,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    alignSelf: 'center',
    backgroundColor: 'rgba(15,28,23,0.78)',
    borderRadius: revaRadii.pill,
  },
  viewportHintText: {
    color: C.focusInk1,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '600',
    fontFamily: revaFonts.cjk,
  },
  statusOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: 'rgba(0,0,0,0.42)',
  },
  statusText: {
    color: C.greenOn,
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
    color: C.greenOn,
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
  failureDetail: {
    color: C.focusInk1,
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
    backgroundColor: C.focusInk1,
    borderRadius: 21,
    borderCurve: 'continuous',
  },
  retryButtonText: {
    color: C.focusBg,
    fontSize: 14,
    fontWeight: '700',
  },
  toolbar: {
    flexShrink: 0,
    minHeight: 68,
    marginHorizontal: 16,
    marginTop: 8,
    paddingHorizontal: 5,
    paddingVertical: 5,
    flexDirection: 'row',
    alignItems: 'stretch',
    backgroundColor: C.focusBg2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    borderRadius: revaRadii.lg,
    borderCurve: 'continuous',
  },
  toolbarButton: {
    flex: 1,
    minWidth: 0,
    minHeight: 56,
    paddingHorizontal: 2,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
    borderRadius: revaRadii.md,
    borderCurve: 'continuous',
  },
  toolbarButtonSelected: {
    backgroundColor: C.focusLine,
  },
  toolbarButtonText: {
    color: C.focusInk2,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '600',
    fontFamily: revaFonts.cjk,
  },
  toolbarButtonTextSelected: {
    color: C.greenBright,
  },
  actions: {
    flexShrink: 0,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 10,
  },
  completeButton: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: C.green500,
    borderRadius: revaRadii.pill,
    borderCurve: 'continuous',
    ...revaShadows.md,
  },
  completeButtonText: {
    color: C.greenOn,
    fontSize: 16,
    fontWeight: '700',
    fontFamily: revaFonts.cjk,
  },
  buttonPressed: {
    opacity: 0.72,
  },
  buttonDisabled: {
    opacity: 0.42,
  },
});
