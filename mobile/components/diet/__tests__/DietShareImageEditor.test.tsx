import React from 'react';
import { Alert, StyleSheet } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

import { revaColors as C } from '../../../constants/revaTheme';

const mockManipulateAsync = jest.fn();
let mockManipulatorAvailable = true;
const mockGestureHandlers: Record<'pan' | 'pinch', Record<string, (event?: any) => void>> = {
  pan: {},
  pinch: {},
};
const mockAnimatedStyleFactories: (() => any)[] = [];

jest.mock('expo-image-manipulator', () => ({
  get manipulateAsync() {
    return mockManipulatorAvailable
      ? (...args: unknown[]) => mockManipulateAsync(...args)
      : undefined;
  },
  SaveFormat: { JPEG: 'jpeg' },
}));

const mockDeleteAsync = jest.fn().mockResolvedValue(undefined);
jest.mock('expo-file-system/legacy', () => ({
  deleteAsync: (...args: unknown[]) => mockDeleteAsync(...args),
}));

jest.mock('expo-image', () => {
  const ReactModule: any = jest.requireActual('react');
  const { View }: any = jest.requireActual('react-native');
  return {
    Image: ReactModule.forwardRef((props: unknown, ref: unknown) => (
      ReactModule.createElement(View, { ...(props as object), ref })
    )),
  };
});

jest.mock('react-native-reanimated', () => {
  const ReactModule: any = jest.requireActual('react');
  const RN: any = jest.requireActual('react-native');
  const createAnimatedComponent = (Component: any) => (
    ReactModule.forwardRef((props: unknown, ref: unknown) => (
      ReactModule.createElement(Component, { ...(props as object), ref })
    ))
  );
  const Animated = {
    View: createAnimatedComponent(RN.View),
    createAnimatedComponent,
  };
  return {
    __esModule: true,
    default: Animated,
    useSharedValue: (initial: unknown) => {
      let value = initial;
      return {
        get: () => value,
        set: (next: unknown) => { value = next; },
      };
    },
    useAnimatedStyle: (factory: () => unknown) => {
      mockAnimatedStyleFactories.push(factory);
      return factory();
    },
    runOnJS: (fn: (...args: unknown[]) => unknown) => fn,
  };
});

jest.mock('react-native-gesture-handler', () => {
  const chain = (kind: 'pan' | 'pinch') => {
    const gesture: Record<string, jest.Mock> = {};
    ['onBegin', 'onUpdate', 'onFinalize'].forEach((name) => {
      gesture[name] = jest.fn((handler: (event?: any) => void) => {
        mockGestureHandlers[kind][name] = handler;
        return gesture;
      });
    });
    return gesture;
  };
  return {
    Gesture: {
      Pan: () => chain('pan'),
      Pinch: () => chain('pinch'),
      Simultaneous: (...gestures: unknown[]) => gestures,
    },
    GestureDetector: ({ children }: { children: React.ReactNode }) => children,
  };
});

// Mocks must be registered before the native-backed component is loaded.
// eslint-disable-next-line import/first
import {
  constrainDietShareGesture,
  DietShareImageEditor,
  resolveDietShareEditorTopInset,
  type DietShareImageEditorResult,
} from '../DietShareImageEditor';
// eslint-disable-next-line import/first
import { initialDietShareImageEdit } from '../dietShareImageEdit';

const SOURCE_URI = 'file:///private/meal.jpg';
const SOURCE_SIZE = { width: 1200, height: 1600 };

function renderEditor(overrides: Partial<React.ComponentProps<typeof DietShareImageEditor>> = {}) {
  const onComplete = jest.fn<void, [DietShareImageEditorResult]>();
  const onCancel = jest.fn();
  const view = render(
    <DietShareImageEditor
      visible
      sourceUri={SOURCE_URI}
      onComplete={onComplete}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return { ...view, onComplete, onCancel };
}

function loadPhoto(view: ReturnType<typeof renderEditor>, size = SOURCE_SIZE) {
  fireEvent(view.getByTestId('diet-share-editor-image'), 'load', { source: size });
}

function layoutEditor(view: ReturnType<typeof renderEditor>, width: number, height: number) {
  fireEvent(view.getByTestId('diet-share-editor-root'), 'layout', {
    nativeEvent: { layout: { x: 0, y: 0, width, height } },
  });
  const viewportStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-viewport').props.style);
  fireEvent(view.getByTestId('diet-share-editor-viewport'), 'layout', {
    nativeEvent: {
      layout: { x: 0, y: 0, width: viewportStyle.width, height: viewportStyle.height },
    },
  });
  return viewportStyle;
}

function drawPrivacyStroke(view: ReturnType<typeof renderEditor>) {
  fireEvent.press(view.getByRole('button', { name: '隐私涂抹' }));
  const canvas = view.getByTestId('diet-share-privacy-canvas');
  fireEvent(canvas, 'layout', {
    nativeEvent: { layout: { x: 0, y: 0, width: 300, height: 400 } },
  });
  fireEvent(canvas, 'responderGrant', { nativeEvent: { locationX: 30, locationY: 40 } });
  fireEvent(canvas, 'responderMove', { nativeEvent: { locationX: 180, locationY: 220 } });
  fireEvent(canvas, 'responderRelease', { nativeEvent: { locationX: 240, locationY: 300 } });
}

function runGesture(
  kind: 'pan' | 'pinch',
  phase: 'onBegin' | 'onUpdate' | 'onFinalize',
  event: Record<string, number> = {},
) {
  const handler = mockGestureHandlers[kind][phase];
  if (!handler) throw new Error(`missing ${kind}.${phase} gesture handler`);
  act(() => handler(event));
}

function latestAnimatedStyle(): any {
  const factory = mockAnimatedStyleFactories[mockAnimatedStyleFactories.length - 1];
  if (!factory) throw new Error('missing animated style factory');
  return factory();
}

function performPinch(scale: number) {
  runGesture('pinch', 'onBegin');
  runGesture('pinch', 'onUpdate', { scale });
  runGesture('pinch', 'onFinalize');
}

function attemptSwipeBack(
  view: ReturnType<typeof renderEditor>,
  gestureOverrides: Record<string, number> = {},
) {
  const surface = view.getByTestId('diet-share-image-editor-swipe-back');
  const gesture = {
    x0: 12,
    y0: 220,
    dx: 132,
    dy: 4,
    vx: 0.4,
    vy: 0,
    numberActiveTouches: 1,
    ...gestureOverrides,
  };
  const touchEvent = (
    pageX: number,
    pageY: number,
    previousPageX: number,
    previousPageY: number,
    timestamp: number,
    activeTouches = gesture.numberActiveTouches,
  ) => ({
    nativeEvent: {
      pageX,
      pageY,
      touches: Array.from(
        { length: activeTouches },
        (_, index) => ({ pageX: pageX + index, pageY: pageY + index }),
      ),
    },
    touchHistory: {
      numberActiveTouches: activeTouches,
      indexOfSingleActiveTouch: 0,
      mostRecentTimeStamp: timestamp,
      touchBank: [{
        touchActive: true,
        startPageX: gesture.x0,
        startPageY: gesture.y0,
        startTimeStamp: 1,
        currentPageX: pageX,
        currentPageY: pageY,
        currentTimeStamp: timestamp,
        previousPageX,
        previousPageY,
        previousTimeStamp: Math.max(1, timestamp - 1),
      }],
    },
  });
  const startEvent = touchEvent(gesture.x0, gesture.y0, gesture.x0, gesture.y0, 1);
  const capturedAtStart = surface.props.onStartShouldSetResponderCapture?.(startEvent) ?? false;
  const claimDx = gesture.dx > 0 ? Math.min(12, gesture.dx) : gesture.dx;
  const claimDy = gesture.dx > 0 && Math.abs(gesture.dy) < Math.abs(gesture.dx)
    ? gesture.dy * (claimDx / gesture.dx)
    : gesture.dy;
  const claimEvent = touchEvent(
    gesture.x0 + claimDx,
    gesture.y0 + claimDy,
    gesture.x0,
    gesture.y0,
    2,
  );
  const claimed = capturedAtStart
    || surface.props.onMoveShouldSetResponderCapture?.(claimEvent)
    || false;
  if (claimed) {
    const endEvent = touchEvent(
      gesture.x0 + gesture.dx,
      gesture.y0 + gesture.dy,
      gesture.x0 + claimDx,
      gesture.y0 + claimDy,
      3,
      0,
    );
    act(() => {
      surface.props.onResponderGrant?.(claimEvent);
      surface.props.onResponderMove?.(endEvent);
      surface.props.onResponderRelease?.(endEvent);
    });
  }
  return claimed;
}

describe('DietShareImageEditor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGestureHandlers.pan = {};
    mockGestureHandlers.pinch = {};
    mockAnimatedStyleFactories.length = 0;
    mockManipulatorAvailable = true;
    mockManipulateAsync.mockResolvedValue({
      uri: 'file:///cache/edited-meal.jpg',
      width: 1600,
      height: 1200,
    });
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('falls back to the launch-window top inset when a full-screen modal loses safe-area context', () => {
    expect(resolveDietShareEditorTopInset(0, 59)).toBe(59);
    expect(resolveDietShareEditorTopInset(47, 59)).toBe(59);
    expect(resolveDietShareEditorTopInset(62, 59)).toBe(62);
  });

  it('presents a compact, task-oriented editor without claiming automatic privacy detection', () => {
    const view = renderEditor();

    expect(view.getByText('调整照片')).toBeTruthy();
    expect(view.getByText('裁剪与隐私处理')).toBeTruthy();
    expect(view.getByText('分享前请检查人脸、地址、条码与二维码')).toBeTruthy();
    expect(view.getByText('拖动调整构图 · 双指缩放')).toBeTruthy();
    expect(view.getByText('旋转')).toBeTruthy();
    expect(view.getByText('遮挡')).toBeTruthy();
    expect(view.getByText('撤销')).toBeTruthy();
    expect(view.getByText('重做')).toBeTruthy();
    expect(view.getByText('重置')).toBeTruthy();
    expect(view.getByText('生成分享图')).toBeTruthy();
    expect(view.getByRole('button', { name: '隐私涂抹' })).toBeTruthy();
    expect(view.queryByText(/自动检测|自动识别|检测到/)).toBeNull();
  });

  it('loads into ready and applies clockwise rotation before a legal pixel crop', async () => {
    const view = renderEditor();
    expect(view.getByText('正在加载照片…')).toBeTruthy();
    expect(view.getByRole('button', { name: '完成图片编辑' })).toBeDisabled();

    loadPhoto(view);
    expect(view.getByLabelText('图片编辑状态')).toHaveAccessibilityValue({ text: '旋转 0 度，隐私涂抹 0 条' });

    fireEvent.press(view.getByRole('button', { name: '顺时针旋转照片' }));
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));

    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(mockManipulateAsync).toHaveBeenCalledWith(
      SOURCE_URI,
      [
        { rotate: 90 },
        { crop: { originX: 350, originY: 0, width: 900, height: 1200 } },
      ],
      { compress: 0.95, format: 'jpeg' },
    );
    const result = view.onComplete.mock.calls[0][0];
    expect(result).toEqual(expect.objectContaining({
      editedUri: 'file:///cache/edited-meal.jpg',
      crop: { x: 0, y: 0, width: 1, height: 1 },
      rotation: 90,
      redactions: [],
      cleanup: expect.any(Function),
    }));

    await result.cleanup();
    expect(mockDeleteAsync).toHaveBeenCalledWith(
      'file:///cache/edited-meal.jpg',
      { idempotent: true },
    );
  });

  it('normalizes a non-square initial crop instead of stretching the 3:4 preview', async () => {
    const view = renderEditor({
      initialEdit: {
        ...initialDietShareImageEdit(),
        crop: { x: 0.1, y: 0.2, width: 0.75, height: 0.7 },
      },
    });
    layoutEditor(view, 390, 844);
    loadPhoto(view);

    const imageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);
    expect(imageStyle.width / imageStyle.height).toBeCloseTo(SOURCE_SIZE.width / SOURCE_SIZE.height);
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));

    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(view.onComplete.mock.calls[0][0].crop).toEqual({
      x: 0.1,
      y: 0.2,
      width: 0.7,
      height: 0.7,
    });
  });

  it('clamps live pan, commits pinch plus pan, and keeps preview and export on the same crop', async () => {
    const view = renderEditor();
    const viewportStyle = layoutEditor(view, 390, 844);
    loadPhoto(view);
    const initialImageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);

    runGesture('pinch', 'onBegin');
    runGesture('pinch', 'onUpdate', { scale: 2 });
    runGesture('pan', 'onBegin');
    runGesture('pan', 'onUpdate', { translationX: 99_999, translationY: -99_999 });

    const expected = constrainDietShareGesture(
      initialDietShareImageEdit(),
      { width: viewportStyle.width, height: viewportStyle.height },
      2,
      99_999,
      -99_999,
    );
    const liveTransform = latestAnimatedStyle().transform;
    expect(liveTransform).toEqual(expect.arrayContaining([
      { scale: expected.scale },
      { translateX: expected.translateX },
      { translateY: expected.translateY },
    ]));
    expect(expected.translateX).toBeLessThan(99_999);
    expect(expected.translateY).toBeGreaterThan(-99_999);

    runGesture('pan', 'onFinalize');
    runGesture('pinch', 'onFinalize');

    const committedImageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);
    expect(committedImageStyle.width).toBeCloseTo(initialImageStyle.width * 2);
    expect(committedImageStyle.width / committedImageStyle.height).toBeCloseTo(
      SOURCE_SIZE.width / SOURCE_SIZE.height,
    );
    expect(view.getByLabelText('图片编辑状态')).toHaveAccessibilityValue({
      text: '旋转 0 度，隐私涂抹 0 条',
    });

    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(view.onComplete.mock.calls[0][0].crop).toEqual(expected.crop);
    expect(mockManipulateAsync).toHaveBeenCalledWith(
      SOURCE_URI,
      [{ crop: { originX: 0, originY: 800, width: 600, height: 800 } }],
      { compress: 0.95, format: 'jpeg' },
    );
  });

  it('enforces an absolute crop floor across repeated 8x pinches and exports a useful pixel crop', async () => {
    const view = renderEditor();
    layoutEditor(view, 390, 844);
    loadPhoto(view);
    const initialImageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);

    performPinch(8);
    performPinch(8);

    const boundedImageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);
    expect(boundedImageStyle.width).toBeCloseTo(initialImageStyle.width * 8);
    expect(boundedImageStyle.width).toBeLessThan(initialImageStyle.width * 8.01);
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));

    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(view.onComplete.mock.calls[0][0].crop).toEqual({
      x: 0.4375,
      y: 0.4375,
      width: 0.125,
      height: 0.125,
    });
    expect(mockManipulateAsync).toHaveBeenCalledWith(
      SOURCE_URI,
      [{ crop: { originX: 525, originY: 700, width: 150, height: 200 } }],
      { compress: 0.95, format: 'jpeg' },
    );
  });

  it('allows a reverse pinch to enlarge a cropped view back to identity without exceeding it', async () => {
    const view = renderEditor({
      initialEdit: {
        ...initialDietShareImageEdit(),
        crop: { x: 0.4375, y: 0.4375, width: 0.125, height: 0.125 },
      },
    });
    layoutEditor(view, 390, 844);
    loadPhoto(view);

    performPinch(0.01);
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));

    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(view.onComplete.mock.calls[0][0].crop).toEqual({
      x: 0,
      y: 0,
      width: 1,
      height: 1,
    });
  });

  it('commits simultaneous pan and pinch only after the last gesture finalizes', () => {
    const view = renderEditor();
    layoutEditor(view, 390, 844);
    loadPhoto(view);
    const initialImageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);

    runGesture('pinch', 'onBegin');
    runGesture('pan', 'onBegin');
    runGesture('pinch', 'onUpdate', { scale: 2 });
    runGesture('pan', 'onUpdate', { translationX: 100, translationY: -100 });
    runGesture('pinch', 'onFinalize');

    expect(view.getByRole('button', { name: '撤销图片编辑' })).toBeDisabled();
    expect(latestAnimatedStyle().transform).toEqual(expect.arrayContaining([
      { scale: 2 },
      { translateX: 100 },
      { translateY: -100 },
    ]));

    runGesture('pan', 'onUpdate', { translationX: 140, translationY: -120 });
    expect(latestAnimatedStyle().transform).toEqual(expect.arrayContaining([
      { scale: 2 },
      { translateX: 140 },
      { translateY: -120 },
    ]));
    runGesture('pan', 'onFinalize');

    expect(view.getByRole('button', { name: '撤销图片编辑' })).not.toBeDisabled();
    const committedImageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);
    expect(committedImageStyle.width).toBeCloseTo(initialImageStyle.width * 2);
    fireEvent.press(view.getByRole('button', { name: '撤销图片编辑' }));
    const undoneImageStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-image').props.style);
    expect(undoneImageStyle.width).toBeCloseTo(initialImageStyle.width);
    expect(view.getByRole('button', { name: '撤销图片编辑' })).toBeDisabled();
  });

  it('supports rotation and privacy-stroke history, then resets crop, rotation, and strokes', async () => {
    const view = renderEditor({
      initialEdit: {
        ...initialDietShareImageEdit(),
        crop: { x: 0.1, y: 0.2, width: 0.75, height: 0.7 },
      },
    });
    loadPhoto(view);

    expect(view.getByRole('button', { name: '撤销图片编辑' })).toBeDisabled();
    expect(view.getByRole('button', { name: '重做图片编辑' })).toBeDisabled();
    fireEvent.press(view.getByRole('button', { name: '顺时针旋转照片' }));
    drawPrivacyStroke(view);
    expect(view.getByLabelText('图片编辑状态')).toHaveAccessibilityValue({ text: '旋转 90 度，隐私涂抹 1 条' });

    fireEvent.press(view.getByRole('button', { name: '撤销图片编辑' }));
    expect(view.getByLabelText('图片编辑状态')).toHaveAccessibilityValue({ text: '旋转 90 度，隐私涂抹 0 条' });
    expect(view.getByRole('button', { name: '重做图片编辑' })).not.toBeDisabled();
    fireEvent.press(view.getByRole('button', { name: '撤销图片编辑' }));
    expect(view.getByLabelText('图片编辑状态')).toHaveAccessibilityValue({ text: '旋转 0 度，隐私涂抹 0 条' });

    fireEvent.press(view.getByRole('button', { name: '重做图片编辑' }));
    fireEvent.press(view.getByRole('button', { name: '重做图片编辑' }));
    expect(view.getByLabelText('图片编辑状态')).toHaveAccessibilityValue({ text: '旋转 90 度，隐私涂抹 1 条' });

    fireEvent.press(view.getByRole('button', { name: '重置图片编辑' }));
    expect(view.getByLabelText('图片编辑状态')).toHaveAccessibilityValue({ text: '旋转 0 度，隐私涂抹 0 条' });
    expect(view.getByRole('button', { name: '重做图片编辑' })).toBeDisabled();
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(view.onComplete.mock.calls[0][0]).toEqual(expect.objectContaining({
      crop: { x: 0, y: 0, width: 1, height: 1 },
      rotation: 0,
      redactions: [],
    }));
  });

  it('asks before discarding changed edits from cancel or system back, but closes unchanged immediately', () => {
    const changed = renderEditor();
    loadPhoto(changed);
    fireEvent.press(changed.getByRole('button', { name: '顺时针旋转照片' }));
    fireEvent.press(changed.getByRole('button', { name: '取消图片编辑' }));

    expect(changed.onCancel).not.toHaveBeenCalled();
    expect(Alert.alert).toHaveBeenCalledWith(
      '放弃图片编辑？',
      '未保存的裁剪、旋转和隐私涂抹会丢失。',
      expect.any(Array),
    );
    const firstButtons = (Alert.alert as jest.Mock).mock.calls[0][2];
    act(() => firstButtons.find((button: { text: string }) => button.text === '丢弃编辑').onPress());
    expect(changed.onCancel).toHaveBeenCalledTimes(1);

    fireEvent(changed.getByTestId('diet-share-image-editor-modal'), 'requestClose');
    expect(Alert.alert).toHaveBeenCalledTimes(2);

    const unchanged = renderEditor();
    fireEvent.press(unchanged.getByRole('button', { name: '取消图片编辑' }));
    expect(unchanged.onCancel).toHaveBeenCalledTimes(1);
  });

  it('uses a completed left-edge swipe as cancel and ignores unrelated gestures', () => {
    const startCaptureView = renderEditor();
    const surface = startCaptureView.getByTestId('diet-share-image-editor-swipe-back');

    expect(surface.props.onStartShouldSetResponderCapture?.({
      nativeEvent: { pageX: 12, touches: [{ pageX: 12, pageY: 220 }] },
      touchHistory: {
        numberActiveTouches: 1,
        indexOfSingleActiveTouch: 0,
        mostRecentTimeStamp: 1,
        touchBank: [{
          touchActive: true,
          startPageX: 12,
          startPageY: 220,
          startTimeStamp: 1,
          currentPageX: 12,
          currentPageY: 220,
          currentTimeStamp: 1,
          previousPageX: 12,
          previousPageY: 220,
          previousTimeStamp: 1,
        }],
      },
    })).toBe(true);
    startCaptureView.unmount();

    const offEdge = renderEditor();
    expect(attemptSwipeBack(offEdge, { x0: 64 })).toBe(false);
    expect(offEdge.onCancel).not.toHaveBeenCalled();
    offEdge.unmount();

    const multitouch = renderEditor();
    expect(attemptSwipeBack(multitouch, { numberActiveTouches: 2 })).toBe(false);
    expect(multitouch.onCancel).not.toHaveBeenCalled();
    multitouch.unmount();

    const completed = renderEditor();
    expect(attemptSwipeBack(completed)).toBe(true);
    expect(completed.onCancel).toHaveBeenCalledTimes(1);
  });

  it('routes a dirty edge swipe through the discard confirmation', () => {
    const view = renderEditor();
    loadPhoto(view);
    fireEvent.press(view.getByRole('button', { name: '顺时针旋转照片' }));

    expect(attemptSwipeBack(view)).toBe(true);
    expect(view.onCancel).not.toHaveBeenCalled();
    expect(Alert.alert).toHaveBeenCalledWith(
      '放弃图片编辑？',
      '未保存的裁剪、旋转和隐私涂抹会丢失。',
      expect.any(Array),
    );

    const buttons = (Alert.alert as jest.Mock).mock.calls[0][2];
    act(() => buttons.find((button: { text: string }) => button.text === '丢弃编辑').onPress());
    expect(view.onCancel).toHaveBeenCalledTimes(1);
  });

  it('uses the normalized session input as the clean baseline across rebuilt props and source changes', () => {
    const baseline = {
      ...initialDietShareImageEdit(),
      crop: { x: 0.1, y: 0.2, width: 0.75, height: 0.7 },
      rotation: 90 as const,
    };
    const view = renderEditor({ initialEdit: baseline });
    loadPhoto(view);

    fireEvent.press(view.getByRole('button', { name: '取消图片编辑' }));
    expect(view.onCancel).toHaveBeenCalledTimes(1);
    expect(Alert.alert).not.toHaveBeenCalled();

    view.onCancel.mockClear();
    view.rerender(
      <DietShareImageEditor
        visible
        sourceUri={SOURCE_URI}
        initialEdit={{ ...baseline, crop: { ...baseline.crop } }}
        onComplete={view.onComplete}
        onCancel={view.onCancel}
      />,
    );
    fireEvent(view.getByTestId('diet-share-image-editor-modal'), 'requestClose');
    expect(view.onCancel).toHaveBeenCalledTimes(1);
    expect(Alert.alert).not.toHaveBeenCalled();

    view.onCancel.mockClear();
    fireEvent.press(view.getByRole('button', { name: '顺时针旋转照片' }));
    fireEvent(view.getByTestId('diet-share-image-editor-modal'), 'requestClose');
    expect(view.onCancel).not.toHaveBeenCalled();
    expect(Alert.alert).toHaveBeenCalledTimes(1);

    (Alert.alert as jest.Mock).mockClear();
    const nextBaseline = {
      ...initialDietShareImageEdit(),
      crop: { x: 0.2, y: 0.15, width: 0.6, height: 0.6 },
      rotation: 270 as const,
    };
    view.rerender(
      <DietShareImageEditor
        visible
        sourceUri="file:///private/other-meal.jpg"
        initialEdit={nextBaseline}
        onComplete={view.onComplete}
        onCancel={view.onCancel}
      />,
    );
    loadPhoto(view);
    fireEvent.press(view.getByRole('button', { name: '取消图片编辑' }));
    expect(view.onCancel).toHaveBeenCalledTimes(1);
    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it('keeps a fully opaque round privacy stroke in the completion result', async () => {
    const view = renderEditor();
    loadPhoto(view);
    drawPrivacyStroke(view);

    // Global SVG host mock exposes native Path nodes under their element name.
    const path = view.getAllByTestId('Path')[0];
    expect(C.ink1).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(path.props).toEqual(expect.objectContaining({
      stroke: C.ink1,
      strokeOpacity: 1,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
    }));

    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(view.onComplete.mock.calls[0][0].redactions).toEqual([{
      points: [
        { x: 0.1, y: 0.1 },
        { x: 0.6, y: 0.55 },
        { x: 0.8, y: 0.75 },
      ],
      width: 0.06,
    }]);
  });

  it('rotates an existing off-centre privacy stroke with the photo before export', async () => {
    const view = renderEditor();
    loadPhoto(view);
    drawPrivacyStroke(view);

    fireEvent.press(view.getByRole('button', { name: '顺时针旋转照片' }));

    expect(view.getAllByTestId('Path')[0].props.d).not.toBe('M 270 40 L 135 240 L 75 320');
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    const [redaction] = view.onComplete.mock.calls[0][0].redactions;
    expect(redaction?.width).toBe(0.06);
    expect(redaction?.points).toHaveLength(3);
    [
      { x: 1.211111, y: 0.1 },
      { x: 0.411111, y: 0.6 },
      { x: 0.055556, y: 0.8 },
    ].forEach((expected, index) => {
      expect(redaction?.points[index]?.x).toBeCloseTo(expected.x);
      expect(redaction?.points[index]?.y).toBeCloseTo(expected.y);
    });
  });

  it('fails loudly when the runtime cannot edit and keeps the original photo visible', async () => {
    mockManipulatorAvailable = false;
    const view = renderEditor();
    loadPhoto(view);

    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));

    await waitFor(() => expect(view.getByText('当前版本暂不支持图片编辑')).toBeTruthy());
    expect(view.getByTestId('diet-share-editor-image')).toBeTruthy();
    expect(view.getByRole('button', { name: '重试图片编辑' })).toBeTruthy();
    expect(view.onComplete).not.toHaveBeenCalled();
    expect(mockManipulateAsync).not.toHaveBeenCalled();
  });

  it('shows an actionable failure without losing the original when manipulation rejects', async () => {
    mockManipulateAsync.mockRejectedValueOnce(new Error(`do not expose ${SOURCE_URI}`));
    const view = renderEditor();
    loadPhoto(view);

    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));

    await waitFor(() => expect(view.getByText('图片编辑失败')).toBeTruthy());
    expect(view.getByText('请重试，或取消后重新选择照片。')).toBeTruthy();
    expect(view.getByTestId('diet-share-editor-image')).toBeTruthy();
    expect(view.onComplete).not.toHaveBeenCalled();
    expect(console.warn).toHaveBeenCalledWith('[DietShareImageEditor] image manipulation failed');
  });

  it('ignores stale load and error events after a source switch and exports with the new dimensions', async () => {
    const view = renderEditor();
    const oldImage = view.getByTestId('diet-share-editor-image');
    const oldOnLoad = oldImage.props.onLoad;
    const oldOnError = oldImage.props.onError;

    view.rerender(
      <DietShareImageEditor
        visible
        sourceUri="file:///private/new-source.jpg"
        onComplete={view.onComplete}
        onCancel={view.onCancel}
      />,
    );
    expect(view.getByText('正在加载照片…')).toBeTruthy();
    act(() => oldOnLoad({ source: { width: 1200, height: 1600 } }));
    expect(view.getByText('正在加载照片…')).toBeTruthy();
    expect(view.getByRole('button', { name: '完成图片编辑' })).toBeDisabled();

    const newImage = view.getByTestId('diet-share-editor-image');
    act(() => newImage.props.onLoad({ source: { width: 2000, height: 1000 } }));
    expect(view.getByRole('button', { name: '完成图片编辑' })).not.toBeDisabled();
    act(() => oldOnError());
    expect(view.queryByText('照片加载失败')).toBeNull();
    expect(view.getByRole('button', { name: '完成图片编辑' })).not.toBeDisabled();

    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(mockManipulateAsync).toHaveBeenCalledWith(
      'file:///private/new-source.jpg',
      [{ crop: { originX: 625, originY: 0, width: 750, height: 1000 } }],
      { compress: 0.95, format: 'jpeg' },
    );
  });

  it('makes applying terminal against cancel and system back, then completes exactly once', async () => {
    let resolveManipulation: ((value: { uri: string; width: number; height: number }) => void) | undefined;
    mockManipulateAsync.mockImplementationOnce(() => new Promise(resolve => {
      resolveManipulation = resolve;
    }));
    const view = renderEditor();

    fireEvent(view.getByTestId('diet-share-editor-image'), 'error');
    expect(view.getByText('照片加载失败')).toBeTruthy();
    fireEvent.press(view.getByRole('button', { name: '重新加载照片' }));
    expect(view.getByText('正在加载照片…')).toBeTruthy();
    loadPhoto(view);

    fireEvent.press(view.getByRole('button', { name: '顺时针旋转照片' }));
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    expect(view.getByText('正在应用图片编辑…')).toBeTruthy();
    expect(view.getByRole('button', { name: '完成图片编辑' })).toBeDisabled();
    expect(view.getByRole('button', { name: '取消图片编辑' })).toBeDisabled();
    expect(attemptSwipeBack(view)).toBe(false);
    fireEvent.press(view.getByRole('button', { name: '取消图片编辑' }));
    fireEvent(view.getByTestId('diet-share-image-editor-modal'), 'requestClose');
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    expect(mockManipulateAsync).toHaveBeenCalledTimes(1);
    expect(view.onCancel).not.toHaveBeenCalled();
    expect(Alert.alert).not.toHaveBeenCalled();

    await act(async () => {
      resolveManipulation?.({ uri: 'file:///cache/final.jpg', width: 1200, height: 1600 });
    });
    await waitFor(() => expect(view.onComplete).toHaveBeenCalledTimes(1));
    expect(view.onCancel).not.toHaveBeenCalled();
  });

  it('cleans a stale output and suppresses callbacks when the editor becomes hidden mid-apply', async () => {
    let resolveManipulation: ((value: { uri: string; width: number; height: number }) => void) | undefined;
    mockManipulateAsync.mockImplementationOnce(() => new Promise(resolve => {
      resolveManipulation = resolve;
    }));
    const view = renderEditor();
    loadPhoto(view);
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));

    view.rerender(
      <DietShareImageEditor
        visible={false}
        sourceUri={SOURCE_URI}
        onComplete={view.onComplete}
        onCancel={view.onCancel}
      />,
    );
    await act(async () => {
      resolveManipulation?.({ uri: 'file:///cache/stale-editor-output.jpg', width: 1200, height: 1600 });
    });

    await waitFor(() => expect(mockDeleteAsync).toHaveBeenCalledWith(
      'file:///cache/stale-editor-output.jpg',
      { idempotent: true },
    ));
    expect(mockDeleteAsync).not.toHaveBeenCalledWith(SOURCE_URI, expect.anything());
    expect(view.onComplete).not.toHaveBeenCalled();
    expect(view.onCancel).not.toHaveBeenCalled();
  });

  it('warns without a URI when stale-output cleanup fails after hiding', async () => {
    let resolveManipulation: ((value: { uri: string; width: number; height: number }) => void) | undefined;
    mockManipulateAsync.mockImplementationOnce(() => new Promise(resolve => {
      resolveManipulation = resolve;
    }));
    mockDeleteAsync.mockRejectedValueOnce(new Error('private stale path'));
    const view = renderEditor();
    loadPhoto(view);
    fireEvent.press(view.getByRole('button', { name: '完成图片编辑' }));
    view.rerender(
      <DietShareImageEditor
        visible={false}
        sourceUri={SOURCE_URI}
        onComplete={view.onComplete}
        onCancel={view.onCancel}
      />,
    );

    await act(async () => {
      resolveManipulation?.({ uri: 'file:///cache/secret-stale-output.jpg', width: 1200, height: 1600 });
    });

    await waitFor(() => expect(console.warn).toHaveBeenCalledWith(
      '[DietShareImageEditor] stale edit cleanup failed',
    ));
    expect(String((console.warn as jest.Mock).mock.calls[0])).not.toContain('secret-stale-output');
    expect(view.onComplete).not.toHaveBeenCalled();
    expect(view.onCancel).not.toHaveBeenCalled();
  });

  it.each([
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ])('computes a numeric 3:4 viewport with ready controls at $width x $height', ({ width, height }) => {
    const view = renderEditor();
    layoutEditor(view, width, height);
    loadPhoto(view);

    const rootStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-root').props.style);
    const viewportStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-viewport').props.style);
    const toolbarStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-toolbar').props.style);
    const actionsStyle = StyleSheet.flatten(view.getByTestId('diet-share-editor-actions').props.style);
    expect(rootStyle.flex).toBe(1);
    expect(typeof viewportStyle.width).toBe('number');
    expect(typeof viewportStyle.height).toBe('number');
    expect(viewportStyle.width / viewportStyle.height).toBeCloseTo(3 / 4);
    expect(viewportStyle.width).toBeLessThanOrEqual(width - 32);
    expect(viewportStyle.height).toBeLessThan(height);
    expect(toolbarStyle.flexShrink).toBe(0);
    expect(actionsStyle.flexShrink).toBe(0);
    expect(view.getByRole('button', { name: '取消图片编辑' })).not.toBeDisabled();
    expect(view.getByRole('button', { name: '顺时针旋转照片' })).not.toBeDisabled();
    expect(view.getByRole('button', { name: '完成图片编辑' })).not.toBeDisabled();
  });

  it('provides 44-point toolbar targets and exposes privacy mode as a selected toggle', () => {
    const view = renderEditor();
    layoutEditor(view, 390, 844);
    loadPhoto(view);
    const privacy = view.getByRole('button', { name: '隐私涂抹' });
    const beforeStyle = StyleSheet.flatten(privacy.props.style);

    expect(beforeStyle.minHeight).toBeGreaterThanOrEqual(44);
    expect(privacy).toHaveAccessibilityState({ selected: false });
    fireEvent.press(privacy);

    const selected = view.getByRole('button', { name: '隐私涂抹' });
    expect(selected).toHaveAccessibilityState({ selected: true });
    expect(StyleSheet.flatten(selected.props.style).backgroundColor).not.toBe(beforeStyle.backgroundColor);
  });
});
