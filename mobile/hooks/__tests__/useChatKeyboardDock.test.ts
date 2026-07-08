import { AppState, Dimensions, Keyboard, Platform } from 'react-native';
import { act, renderHook } from '@testing-library/react-native';

import { useChatKeyboardDock } from '../useChatKeyboardDock';

describe('useChatKeyboardDock', () => {
  const originalOS = Platform.OS;
  const originalMetrics = (Keyboard as any).metrics;
  let keyboardListeners: Record<string, (event?: any) => void>;
  let appStateHandler: ((state: string) => void) | null;

  beforeEach(() => {
    keyboardListeners = {};
    appStateHandler = null;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'ios' });
    jest.spyOn(Dimensions, 'get').mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 1 });
    jest.spyOn(Keyboard, 'addListener').mockImplementation((eventName: any, callback: any) => {
      keyboardListeners[String(eventName)] = callback;
      return { remove: jest.fn() } as any;
    });
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_type: string, callback: (state: string) => void) => {
      appStateHandler = callback;
      return { remove: jest.fn() };
    }) as never);
    (Keyboard as any).metrics = jest.fn(() => undefined);
  });

  afterEach(() => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: originalOS });
    (Keyboard as any).metrics = originalMetrics;
    jest.restoreAllMocks();
  });

  it('uses the resting inset while the keyboard is hidden', () => {
    const { result } = renderHook(() => useChatKeyboardDock({ bottomInset: 14, restingSpace: 28 }));

    expect(result.current.keyboardVisible).toBe(false);
    expect(result.current.keyboardHeight).toBe(0);
    expect(result.current.bottomSpacerHeight).toBe(42);
  });

  it('anchors the composer to the iOS keyboard overlap when the keyboard appears', () => {
    const { result } = renderHook(() => useChatKeyboardDock({ bottomInset: 0, restingSpace: 28 }));

    act(() => {
      keyboardListeners.keyboardDidShow?.({
        endCoordinates: { height: 336 },
      });
    });

    expect(result.current.keyboardVisible).toBe(true);
    expect(result.current.keyboardHeight).toBe(336);
    expect(result.current.bottomSpacerHeight).toBe(336);
  });

  it('derives keyboard overlap from frame screenY updates', () => {
    const { result } = renderHook(() => useChatKeyboardDock({ bottomInset: 0, restingSpace: 28 }));

    act(() => {
      keyboardListeners.keyboardDidChangeFrame?.({
        endCoordinates: { screenY: 540 },
      });
    });

    expect(result.current.keyboardHeight).toBe(304);
    expect(result.current.bottomSpacerHeight).toBe(304);
  });

  it('resyncs from Keyboard.metrics when the app returns active', () => {
    (Keyboard as any).metrics = jest.fn(() => ({ height: 336 }));
    const { result } = renderHook(() => useChatKeyboardDock({ bottomInset: 0, restingSpace: 28 }));

    act(() => {
      keyboardListeners.keyboardDidShow?.({ endCoordinates: { height: 336 } });
    });
    act(() => {
      keyboardListeners.keyboardDidHide?.();
    });
    expect(result.current.bottomSpacerHeight).toBe(28);

    act(() => {
      appStateHandler?.('active');
    });

    expect(result.current.keyboardVisible).toBe(true);
    expect(result.current.bottomSpacerHeight).toBe(336);
  });

  it('keeps Android from adding an extra keyboard spacer', () => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'android' });
    const { result } = renderHook(() => useChatKeyboardDock({ bottomInset: 0, restingSpace: 28 }));

    act(() => {
      keyboardListeners.keyboardDidShow?.({ endCoordinates: { height: 336 } });
    });

    expect(result.current.keyboardVisible).toBe(true);
    expect(result.current.bottomSpacerHeight).toBe(0);
  });
});
