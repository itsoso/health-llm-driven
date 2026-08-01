import React from 'react';
import { Alert, Platform, Share } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockMaterializedCleanup = jest.fn().mockResolvedValue(undefined);
const mockEditedCleanup = jest.fn().mockResolvedValue(undefined);
const mockMaterializeImageForLocalUse = jest.fn().mockResolvedValue({
  uri: 'file:///cache/materialized-meal.jpg',
  cleanup: mockMaterializedCleanup,
});
const mockCaptureRef = jest.fn().mockResolvedValue('file:///cache/meal-poster.png');
const mockReleaseCapture = jest.fn();
const mockShareAsync = jest.fn().mockResolvedValue(undefined);
const mockSaveToLibraryAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestPermissionsAsync = jest.fn().mockResolvedValue({ status: 'granted', granted: true });
let currentEditorProps: any;

jest.mock('../../../utils/share', () => ({
  materializeImageForLocalUse: (...args: unknown[]) => mockMaterializeImageForLocalUse(...args),
}));

jest.mock('../DietShareImageEditor', () => {
  const ReactModule: any = jest.requireActual('react');
  const { View }: any = jest.requireActual('react-native');
  return {
    DietShareImageEditor: (props: unknown) => {
      currentEditorProps = props;
      return ReactModule.createElement(View, { testID: 'mock-diet-share-editor' });
    },
  };
});

jest.mock('../DietShareCard', () => {
  const ReactModule: any = jest.requireActual('react');
  const { Pressable, View }: any = jest.requireActual('react-native');
  return {
    __esModule: true,
    default: (props: any) => ReactModule.createElement(
      View,
      { testID: 'mock-diet-share-poster' },
      ReactModule.createElement(Pressable, {
        testID: 'mock-poster-photo-load',
        onPress: props.onImageReady,
      }),
      ReactModule.createElement(Pressable, {
        testID: 'mock-poster-photo-error',
        onPress: props.onImageError,
      }),
    ),
    buildDietShareCaption: jest.fn(() => '小红书餐食正文'),
    dietShareCaptureDimensions: jest.fn(() => ({ width: 1080, height: 1440 })),
  };
});

jest.mock('expo-image', () => {
  const ReactModule: any = jest.requireActual('react');
  const { View }: any = jest.requireActual('react-native');
  return {
    Image: ReactModule.forwardRef((props: unknown, ref: unknown) => (
      ReactModule.createElement(View, { ...(props as object), ref })
    )),
  };
});

jest.mock('react-native-view-shot', () => ({
  captureRef: (...args: unknown[]) => mockCaptureRef(...args),
  releaseCapture: (...args: unknown[]) => mockReleaseCapture(...args),
}));

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  shareAsync: (...args: unknown[]) => mockShareAsync(...args),
}));

jest.mock('expo-media-library', () => ({
  requestPermissionsAsync: (...args: unknown[]) => mockRequestPermissionsAsync(...args),
  saveToLibraryAsync: (...args: unknown[]) => mockSaveToLibraryAsync(...args),
}));

// eslint-disable-next-line import/first
import { DietShareComposer } from '../DietShareComposer';
// eslint-disable-next-line import/first
import type { DietRecord } from '../../../services/diet';

const record: DietRecord = {
  id: 88,
  user_id: 1,
  record_date: '2026-08-01',
  meal_type: 'lunch',
  food_items: '番茄鸡蛋面',
  source: 'photo',
  calories: 520,
  protein: 24,
  carbs: 64,
  fat: 17,
  fiber: 4,
  alcohol_units: null,
  image_url: 'https://health.executor.life/api/v1/upload/files/diet/1/meal.jpg',
  notes: null,
  health_tips: '下一餐补蔬菜',
  ai_confidence: 0.88,
};

const photoSource = {
  uri: record.image_url!,
  headers: { Authorization: 'Bearer test-token' },
};
const originalPlatformOS = Platform.OS;

function renderComposer(overrides: Partial<React.ComponentProps<typeof DietShareComposer>> = {}) {
  const onClose = jest.fn();
  const view = render(
    <DietShareComposer
      visible
      record={record}
      dateLabel="8月1日 · 午餐"
      photoSource={photoSource}
      onClose={onClose}
      {...overrides}
    />,
  );
  return { ...view, onClose };
}

async function completeEditing(view: ReturnType<typeof renderComposer>) {
  await waitFor(() => expect(view.getByTestId('mock-diet-share-editor')).toBeTruthy());
  act(() => currentEditorProps.onComplete({
    editedUri: 'file:///cache/edited-meal.jpg',
    crop: { x: 0, y: 0, width: 1, height: 1 },
    rotation: 0,
    redactions: [{
      points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.2 }],
      width: 0.06,
    }],
    cleanup: mockEditedCleanup,
  }));
  await waitFor(() => expect(view.getByTestId('mock-poster-photo-load')).toBeTruthy());
}

async function reachPreview(view: ReturnType<typeof renderComposer>) {
  await completeEditing(view);
  fireEvent.press(view.getByTestId('mock-poster-photo-load'));
  await waitFor(() => expect(view.getByTestId('diet-share-captured-preview')).toBeTruthy());
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('DietShareComposer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    currentEditorProps = undefined;
    mockMaterializeImageForLocalUse.mockReset();
    mockMaterializeImageForLocalUse.mockResolvedValue({
      uri: 'file:///cache/materialized-meal.jpg',
      cleanup: mockMaterializedCleanup,
    });
    mockCaptureRef.mockReset();
    mockCaptureRef.mockResolvedValue('file:///cache/meal-poster.png');
    mockShareAsync.mockReset();
    mockShareAsync.mockResolvedValue(undefined);
    mockRequestPermissionsAsync.mockReset();
    mockRequestPermissionsAsync.mockResolvedValue({ status: 'granted', granted: true });
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  });

  afterEach(() => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: originalPlatformOS });
  });

  it('materializes the protected photo before opening the editor', async () => {
    const view = renderComposer();

    await waitFor(() => expect(mockMaterializeImageForLocalUse).toHaveBeenCalledWith(
      record.image_url,
      expect.objectContaining({ headers: { Authorization: 'Bearer test-token' } }),
    ));
    expect(view.getByTestId('mock-diet-share-editor')).toBeTruthy();
    expect(currentEditorProps.sourceUri).toBe('file:///cache/materialized-meal.jpg');
  });

  it('captures once and reuses the retained PNG for preview, save, and share', async () => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'android' });
    const view = renderComposer();
    await completeEditing(view);

    fireEvent.press(view.getByTestId('mock-poster-photo-load'));
    await waitFor(() => expect(mockCaptureRef).toHaveBeenCalledTimes(1));
    expect(mockCaptureRef).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      format: 'png',
      quality: 1,
      width: 1080,
      height: 1440,
      result: 'tmpfile',
    }));
    expect(view.getByTestId('diet-share-captured-preview').props.source)
      .toEqual({ uri: 'file:///cache/meal-poster.png' });

    fireEvent.press(view.getByRole('button', { name: '保存海报到相册' }));
    await waitFor(() => expect(mockSaveToLibraryAsync)
      .toHaveBeenCalledWith('file:///cache/meal-poster.png'));
    fireEvent.press(view.getByRole('button', { name: '分享饮食海报' }));
    await waitFor(() => expect(mockShareAsync).toHaveBeenCalledWith(
      'file:///cache/meal-poster.png',
      expect.objectContaining({ mimeType: 'image/png' }),
    ));
    expect(mockCaptureRef).toHaveBeenCalledTimes(1);
  });

  it('treats a dismissed system share as cancellation without an error', async () => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'ios' });
    (Share.share as jest.Mock).mockResolvedValueOnce({ action: Share.dismissedAction });
    const onShareFeedback = jest.fn();
    const onShareTerminal = jest.fn();
    const view = renderComposer({ onShareFeedback, onShareTerminal });
    await reachPreview(view);

    fireEvent.press(view.getByRole('button', { name: '分享饮食海报' }));

    await waitFor(() => expect(Share.share).toHaveBeenCalledWith(
      { url: 'file:///cache/meal-poster.png' },
      expect.objectContaining({ dialogTitle: '分享饮食海报' }),
    ));
    expect(mockShareAsync).not.toHaveBeenCalled();
    expect(Alert.alert).not.toHaveBeenCalledWith('分享失败', expect.anything());
    expect(onShareFeedback).not.toHaveBeenCalledWith(expect.objectContaining({ tone: 'warning' }));
    expect(onShareTerminal).not.toHaveBeenCalledWith(expect.objectContaining({ phase: 'completed' }));
  });

  it('never renders or captures a poster when the protected photo cannot materialize', async () => {
    mockMaterializeImageForLocalUse.mockRejectedValueOnce(new Error('download failed'));
    const view = renderComposer();

    await waitFor(() => expect(view.getByText('照片加载失败')).toBeTruthy());
    expect(view.queryByTestId('mock-diet-share-editor')).toBeNull();
    expect(view.queryByTestId('mock-diet-share-poster')).toBeNull();
    expect(view.getByRole('button', { name: '重试照片加载' })).toBeTruthy();
    expect(view.getByRole('button', { name: '分享正文' })).toBeTruthy();
    expect(mockCaptureRef).not.toHaveBeenCalled();
  });

  it('does not capture a metric poster when the edited photo cannot render', async () => {
    const view = renderComposer();
    await completeEditing(view);

    fireEvent.press(view.getByTestId('mock-poster-photo-error'));

    await waitFor(() => expect(view.getByText('分享图生成失败')).toBeTruthy());
    expect(view.queryByTestId('mock-diet-share-poster')).toBeNull();
    expect(mockCaptureRef).not.toHaveBeenCalled();
  });

  it('retries only poster rendering after capture fails', async () => {
    mockCaptureRef
      .mockRejectedValueOnce(new Error('capture failed'))
      .mockResolvedValueOnce('file:///cache/retried-poster.png');
    const view = renderComposer();
    await completeEditing(view);

    fireEvent.press(view.getByTestId('mock-poster-photo-load'));
    await waitFor(() => expect(view.getByText('分享图生成失败')).toBeTruthy());
    expect(mockMaterializeImageForLocalUse).toHaveBeenCalledTimes(1);

    fireEvent.press(view.getByRole('button', { name: '重新生成分享图' }));
    await waitFor(() => expect(view.getByTestId('mock-poster-photo-load')).toBeTruthy());
    fireEvent.press(view.getByTestId('mock-poster-photo-load'));

    await waitFor(() => expect(view.getByTestId('diet-share-captured-preview').props.source)
      .toEqual({ uri: 'file:///cache/retried-poster.png' }));
    expect(mockMaterializeImageForLocalUse).toHaveBeenCalledTimes(1);
    expect(mockEditedCleanup).not.toHaveBeenCalled();
  });

  it('blocks synchronous duplicate share actions', async () => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'android' });
    const pendingShare = deferred<undefined>();
    mockShareAsync.mockReturnValueOnce(pendingShare.promise);
    const view = renderComposer();
    await reachPreview(view);

    act(() => {
      fireEvent.press(view.getByRole('button', { name: '分享饮食海报' }));
      fireEvent.press(view.getByRole('button', { name: '分享饮食海报' }));
    });

    await waitFor(() => expect(mockShareAsync).toHaveBeenCalledTimes(1));
    await act(async () => {
      pendingShare.resolve(undefined);
      await pendingShare.promise;
    });
  });

  it('does not emit async share results after the composer closes', async () => {
    const pendingShare = deferred<undefined>();
    mockShareAsync.mockReturnValueOnce(pendingShare.promise);
    const onShareFeedback = jest.fn();
    const onShareTerminal = jest.fn();
    const view = renderComposer({ onShareFeedback, onShareTerminal });
    await reachPreview(view);

    fireEvent.press(view.getByRole('button', { name: '分享饮食海报' }));
    fireEvent.press(view.getByRole('button', { name: '关闭饮食分享编辑器' }));
    await waitFor(() => expect(view.onClose).toHaveBeenCalledTimes(1));
    await act(async () => {
      pendingShare.resolve(undefined);
      await pendingShare.promise;
    });

    expect(onShareFeedback).not.toHaveBeenCalled();
    expect(onShareTerminal).not.toHaveBeenCalled();
  });

  it('blocks new share work while close cleanup is still pending', async () => {
    const pendingCleanup = deferred<void>();
    mockEditedCleanup.mockReturnValueOnce(pendingCleanup.promise);
    const view = renderComposer();
    await reachPreview(view);
    const shareButton = view.getByRole('button', { name: '分享饮食海报' });

    fireEvent.press(view.getByRole('button', { name: '关闭饮食分享编辑器' }));
    fireEvent.press(shareButton);

    expect(Share.share).not.toHaveBeenCalled();
    expect(mockShareAsync).not.toHaveBeenCalled();
    await act(async () => {
      pendingCleanup.resolve();
      await pendingCleanup.promise;
    });
    await waitFor(() => expect(view.onClose).toHaveBeenCalledTimes(1));
  });

  it('discards a late edit result while close cleanup is still pending', async () => {
    const pendingCleanup = deferred<void>();
    const lateEditedCleanup = jest.fn().mockResolvedValue(undefined);
    mockMaterializedCleanup.mockReturnValueOnce(pendingCleanup.promise);
    const view = renderComposer();
    await waitFor(() => expect(view.getByTestId('mock-diet-share-editor')).toBeTruthy());

    fireEvent.press(view.getByRole('button', { name: '关闭饮食分享编辑器' }));
    act(() => currentEditorProps.onComplete({
      editedUri: 'file:///cache/late-edited-meal.jpg',
      crop: { x: 0, y: 0, width: 1, height: 1 },
      rotation: 0,
      redactions: [],
      cleanup: lateEditedCleanup,
    }));

    await waitFor(() => expect(lateEditedCleanup).toHaveBeenCalledTimes(1));
    expect(view.queryByTestId('mock-diet-share-poster')).toBeNull();
    await act(async () => {
      pendingCleanup.resolve();
      await pendingCleanup.promise;
    });
    await waitFor(() => expect(view.onClose).toHaveBeenCalledTimes(1));
  });

  it('does not reopen a closing session when authenticated headers change', async () => {
    const pendingCleanup = deferred<void>();
    mockMaterializedCleanup.mockReturnValueOnce(pendingCleanup.promise);
    const view = renderComposer();
    await waitFor(() => expect(view.getByTestId('mock-diet-share-editor')).toBeTruthy());

    fireEvent.press(view.getByRole('button', { name: '关闭饮食分享编辑器' }));
    view.rerender(
      <DietShareComposer
        visible
        record={record}
        dateLabel="8月1日 · 午餐"
        photoSource={{ ...photoSource, headers: { Authorization: 'Bearer refreshed-token' } }}
        onClose={view.onClose}
      />,
    );

    await act(async () => { await Promise.resolve(); });
    expect(mockMaterializeImageForLocalUse).toHaveBeenCalledTimes(1);
    await act(async () => {
      pendingCleanup.resolve();
      await pendingCleanup.promise;
    });
    await waitFor(() => expect(view.onClose).toHaveBeenCalledTimes(1));
    expect(mockMaterializeImageForLocalUse).toHaveBeenCalledTimes(1);
  });

  it('releases a capture that resolves after the poster photo fails', async () => {
    const pendingCapture = deferred<string>();
    mockCaptureRef.mockReturnValueOnce(pendingCapture.promise);
    const view = renderComposer();
    await completeEditing(view);

    fireEvent.press(view.getByTestId('mock-poster-photo-load'));
    await waitFor(() => expect(mockCaptureRef).toHaveBeenCalledTimes(1));
    fireEvent.press(view.getByTestId('mock-poster-photo-error'));
    await waitFor(() => expect(view.getByText('分享图生成失败')).toBeTruthy());
    await act(async () => {
      pendingCapture.resolve('file:///cache/late-poster.png');
      await pendingCapture.promise;
    });

    await waitFor(() => expect(mockReleaseCapture).toHaveBeenCalledWith('file:///cache/late-poster.png'));
    expect(view.getByText('分享图生成失败')).toBeTruthy();
    expect(view.queryByTestId('diet-share-captured-preview')).toBeNull();
  });

  it('treats a rejected native cancellation as cancellation without an error', async () => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'android' });
    mockShareAsync.mockRejectedValueOnce({ code: 'ERR_CANCELED' });
    const onShareTerminal = jest.fn();
    const view = renderComposer({ onShareTerminal });
    await reachPreview(view);

    fireEvent.press(view.getByRole('button', { name: '分享饮食海报' }));

    await waitFor(() => expect(mockShareAsync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(view.queryByText('分享中…')).toBeNull());
    expect(Alert.alert).not.toHaveBeenCalledWith('分享失败', expect.anything());
    expect(onShareTerminal).not.toHaveBeenCalled();
  });

  it('releases captured, edited, and materialized resources exactly once on close', async () => {
    const view = renderComposer();
    await reachPreview(view);

    fireEvent.press(view.getByRole('button', { name: '关闭饮食分享编辑器' }));
    await waitFor(() => expect(view.onClose).toHaveBeenCalledTimes(1));
    view.unmount();

    await waitFor(() => {
      expect(mockReleaseCapture).toHaveBeenCalledTimes(1);
      expect(mockReleaseCapture).toHaveBeenCalledWith('file:///cache/meal-poster.png');
      expect(mockEditedCleanup).toHaveBeenCalledTimes(1);
      expect(mockMaterializedCleanup).toHaveBeenCalledTimes(1);
    });
  });
});
