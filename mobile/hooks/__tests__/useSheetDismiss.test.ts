import { act, renderHook } from '@testing-library/react-native';
import { PanResponder } from 'react-native';
import { useSheetDismiss } from '../useSheetDismiss';

describe('sheet header dismissal', () => {
  afterEach(() => jest.restoreAllMocks());

  it('starts tracking a single header touch without capturing child buttons', () => {
    const create = jest.spyOn(PanResponder, 'create');
    renderHook(() => useSheetDismiss(jest.fn(), true));
    const config = create.mock.calls[0][0];
    expect(config.onStartShouldSetPanResponder!({ nativeEvent: { touches: [{}] } } as any, {} as any)).toBe(true);
    expect(config.onStartShouldSetPanResponder!({ nativeEvent: { touches: [{}, {}] } } as any, {} as any)).toBe(false);
    expect(config.onStartShouldSetPanResponderCapture).toBeUndefined();
  });
  it('only claims a deliberate single-finger downward drag', () => {
    const create = jest.spyOn(PanResponder, 'create');
    renderHook(() => useSheetDismiss(jest.fn(), true));
    const config = create.mock.calls[0][0];
    for (const [dx, dy, fingers, wanted] of [[0, 9, 1, true], [20, 10, 1, false], [0, -40, 1, false], [0, 60, 2, false], [0, 3, 1, false]]) {
      expect(config.onMoveShouldSetPanResponder!({} as any, { dx, dy, numberActiveTouches: fingers } as any)).toBe(wanted);
    }
    create.mockRestore();
  });

  it('cancels short pulls and interrupted gestures, dismisses a full pull once', () => {
    const create = jest.spyOn(PanResponder, 'create');
    const close = jest.fn();
    renderHook(() => useSheetDismiss(close, true));
    const config = create.mock.calls[0][0];
    act(() => config.onPanResponderRelease!({} as any, { dx: 0, dy: 12, vy: 0 } as any));
    act(() => config.onPanResponderTerminate!({} as any, {} as any));
    expect(close).not.toHaveBeenCalled();
    act(() => config.onPanResponderRelease!({} as any, { dx: 0, dy: 90, vy: 0 } as any));
    expect(close).toHaveBeenCalledTimes(1);
    create.mockRestore();
  });

  it('does not dismiss when a claimed drag turns horizontal or upward', () => {
    const create = jest.spyOn(PanResponder, 'create');
    const close = jest.fn();
    renderHook(() => useSheetDismiss(close, true));
    const config = create.mock.calls[0][0];
    act(() => config.onPanResponderRelease!({} as any, { dx: 120, dy: 80, vy: 1 } as any));
    act(() => config.onPanResponderRelease!({} as any, { dx: 0, dy: -20, vy: -1 } as any));
    expect(close).not.toHaveBeenCalled();
    create.mockRestore();
  });
});
