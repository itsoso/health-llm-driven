import { act, renderHook } from '@testing-library/react-native';
import { useChatCardReveal } from '../ChatCardRevealContext';

function fixture() {
  const scrollToOffset = jest.fn();
  const onReveal = jest.fn();
  const target = { current: { measureInWindow: jest.fn((cb) => cb(0, 760, 300, 900)) } };
  const options = {
    listRef: { current: { scrollToOffset } } as any,
    viewportRef: { current: { measureInWindow: jest.fn((cb) => cb(0, 100, 300, 600)) } } as any,
    offsetRef: { current: 400 },
    onReveal,
  };
  return { target: target as any, options, scrollToOffset, onReveal };
}

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

it('reveals the requested editor below the viewport, not the conversation end', () => {
  const f = fixture();
  const { result } = renderHook(() => useChatCardReveal(f.options));
  act(() => { result.current.reveal(f.target); });
  expect(f.onReveal).toHaveBeenCalledTimes(1);
  act(() => jest.runAllTimers());
  expect(f.scrollToOffset).toHaveBeenCalledTimes(1);
  expect(f.scrollToOffset).toHaveBeenCalledWith({ offset: 1048, animated: false });
});

it('waits for the newly expanded native view to mount', () => {
  const f = fixture();
  const node = f.target.current;
  f.target.current = null;
  const { result } = renderHook(() => useChatCardReveal(f.options));
  act(() => { result.current.reveal(f.target); jest.advanceTimersByTime(0); });
  expect(f.scrollToOffset).not.toHaveBeenCalled();
  f.target.current = node;
  act(() => jest.runAllTimers());
  expect(f.scrollToOffset).toHaveBeenCalledTimes(1);
});

it('does not move an editor that is already visible', () => {
  const f = fixture();
  f.target.current.measureInWindow.mockImplementation((cb: any) => cb(0, 200, 300, 250));
  const { result } = renderHook(() => useChatCardReveal(f.options));
  act(() => { result.current.reveal(f.target); jest.runAllTimers(); });
  expect(f.scrollToOffset).not.toHaveBeenCalled();
});

it.each(['drag', 'collapse', 'unmount', 'replacement'])('discards delayed native measurements after %s', (reason) => {
  const f = fixture();
  let measured: (x: number, y: number, width: number, height: number) => void = () => {};
  f.target.current.measureInWindow.mockImplementation((cb: typeof measured) => { measured = cb; });
  const { result, unmount } = renderHook(() => useChatCardReveal(f.options));
  let close = () => {};
  act(() => { close = result.current.reveal(f.target); jest.runAllTimers(); });
  expect(f.target.current.measureInWindow).toHaveBeenCalledTimes(1);
  act(() => {
    if (reason === 'drag') result.current.cancel();
    if (reason === 'collapse') close();
    if (reason === 'unmount') unmount();
    if (reason === 'replacement') f.target.current = null;
  });
  act(() => {
    measured(0, 760, 300, 900);
    jest.runAllTimers();
  });
  expect(f.scrollToOffset).not.toHaveBeenCalled();
});
