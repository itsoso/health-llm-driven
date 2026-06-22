import { act, renderHook, waitFor } from '@testing-library/react-native';

jest.mock('../../services/mealMonitoring', () => {
  const actual = jest.requireActual('../../services/mealMonitoring');
  return {
    __esModule: true,
    ...actual,
    startMealSession: jest.fn(),
    appendMealFrame: jest.fn(),
    finishMealSession: jest.fn(),
    confirmMealSession: jest.fn(),
    abortMealSession: jest.fn(),
  };
});

import {
  MEAL_SESSION_MAX_FRAMES,
  abortMealSession,
  appendMealFrame,
  confirmMealSession,
  finishMealSession,
  startMealSession,
} from '../../services/mealMonitoring';
import { useMealCapture, type MealCaptureResult } from '../useMealCapture';

const mockStart = startMealSession as jest.MockedFunction<typeof startMealSession>;
const mockAppend = appendMealFrame as jest.MockedFunction<typeof appendMealFrame>;
const mockFinish = finishMealSession as jest.MockedFunction<typeof finishMealSession>;
const mockConfirm = confirmMealSession as jest.MockedFunction<typeof confirmMealSession>;
const mockAbort = abortMealSession as jest.MockedFunction<typeof abortMealSession>;

function okFrame(): MealCaptureResult {
  return { frame: { imageBase64: 'AAAA', capturedAt: new Date().toISOString() } };
}

function rateLimitError() {
  return { response: { status: 429, data: { detail: '已达上限' } } };
}

describe('useMealCapture', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockStart.mockResolvedValue({ id: 7, status: 'active', frame_count: 0 } as never);
    mockAbort.mockResolvedValue({ session: { id: 7, status: 'aborted', frame_count: 0 } } as never);
  });

  it('blocks start without consent (consent gate)', async () => {
    const captureFrame = jest.fn(async () => okFrame());
    const { result } = renderHook(() => useMealCapture({ captureFrame, minIntervalMs: 0 }));

    await act(async () => {
      await result.current.startSession(false);
    });

    expect(mockStart).not.toHaveBeenCalled();
    expect(captureFrame).not.toHaveBeenCalled();
    expect(result.current.state.phase).toBe('error');
  });

  it('sequentially captures + posts frames and stops at the 30-frame cap', async () => {
    let serverCount = 0;
    const captureFrame = jest.fn(async () => okFrame());
    mockAppend.mockImplementation(async () => {
      serverCount += 1;
      return { frame_event_id: serverCount, session_id: 7, frame_count: serverCount, status: 'active' } as never;
    });

    const { result } = renderHook(() => useMealCapture({ captureFrame, minIntervalMs: 0 }));

    await act(async () => {
      await result.current.startSession(true);
    });

    await waitFor(() => {
      expect(result.current.state.reachedFrameCap).toBe(true);
    });

    // Client stops exactly at the cap; never asks the server for a 31st frame.
    expect(captureFrame).toHaveBeenCalledTimes(MEAL_SESSION_MAX_FRAMES);
    expect(mockAppend).toHaveBeenCalledTimes(MEAL_SESSION_MAX_FRAMES);
    expect(result.current.state.frameCount).toBe(MEAL_SESSION_MAX_FRAMES);
    // Sequential, not overlapping: each append resolved before the next capture.
    expect(serverCount).toBe(MEAL_SESSION_MAX_FRAMES);
  });

  it('stops without retry storm on a 429 from the server', async () => {
    const captureFrame = jest.fn(async () => okFrame());
    mockAppend.mockRejectedValueOnce(rateLimitError());

    const { result } = renderHook(() => useMealCapture({ captureFrame, minIntervalMs: 0 }));

    await act(async () => {
      await result.current.startSession(true);
    });

    await waitFor(() => {
      expect(result.current.state.reachedFrameCap).toBe(true);
    });

    expect(mockAppend).toHaveBeenCalledTimes(1);
    expect(captureFrame).toHaveBeenCalledTimes(1);
    expect(result.current.state.message).toContain('已达上限');
  });

  it('finish surfaces the draft summary (no DietRecord yet)', async () => {
    const captureFrame = jest.fn(async () => okFrame());
    mockAppend.mockResolvedValue({ frame_event_id: 1, session_id: 7, frame_count: 1, status: 'active' } as never);
    mockFinish.mockResolvedValue({
      session: { id: 7, status: 'needs_confirmation', frame_count: 3 },
      summary: {
        session_id: 7,
        status: 'needs_confirmation',
        target: 'diet_draft',
        frame_count: 3,
        foods: [{ name: '米饭', calories: 200 }],
        totals: { calories: 200 },
        observational_summary: '这餐以主食为主。',
        guidance_alerts: [],
        disclaimer: '仅供参考，非医疗建议。',
        draft_diet_record: { food_items: [] },
      },
    } as never);

    const { result } = renderHook(() => useMealCapture({ captureFrame, minIntervalMs: 0 }));

    await act(async () => {
      await result.current.startSession(true);
    });
    await waitFor(() => expect(result.current.state.frameCount).toBeGreaterThan(0));

    await act(async () => {
      await result.current.finish();
    });

    expect(mockFinish).toHaveBeenCalledWith(7);
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(result.current.state.phase).toBe('draft');
    expect(result.current.state.summary?.observational_summary).toBe('这餐以主食为主。');
  });

  it('confirm writes the DietRecord', async () => {
    const captureFrame = jest.fn(async () => okFrame());
    mockAppend.mockResolvedValue({ frame_event_id: 1, session_id: 7, frame_count: 1, status: 'active' } as never);
    mockConfirm.mockResolvedValue({ session: { id: 7, status: 'confirmed', frame_count: 1 }, diet_record_id: 42 } as never);

    const { result } = renderHook(() => useMealCapture({ captureFrame, minIntervalMs: 0 }));

    await act(async () => {
      await result.current.startSession(true);
    });
    await waitFor(() => expect(result.current.state.frameCount).toBeGreaterThan(0));

    await act(async () => {
      await result.current.confirm('lunch');
    });

    expect(mockConfirm).toHaveBeenCalledWith(7, { mealType: 'lunch' });
    expect(result.current.state.phase).toBe('confirmed');
    expect(result.current.state.dietRecordId).toBe(42);
  });

  it('aborts the active session on unmount to purge raw frames', async () => {
    const captureFrame = jest.fn(async () => okFrame());
    mockAppend.mockResolvedValue({ frame_event_id: 1, session_id: 7, frame_count: 1, status: 'active' } as never);

    const { result, unmount } = renderHook(() => useMealCapture({ captureFrame, minIntervalMs: 0 }));

    await act(async () => {
      await result.current.startSession(true);
    });
    await waitFor(() => expect(result.current.state.sessionId).toBe(7));

    await act(async () => {
      unmount();
    });

    expect(mockAbort).toHaveBeenCalledWith(7);
  });

  it('stops with the real reason when a capture is cancelled (no fake success)', async () => {
    const captureFrame = jest.fn(async (): Promise<MealCaptureResult> => ({ frame: null, reason: '已取消拍照，停止采样' }));

    const { result } = renderHook(() => useMealCapture({ captureFrame, minIntervalMs: 0 }));

    await act(async () => {
      await result.current.startSession(true);
    });

    await waitFor(() => expect(result.current.state.phase).toBe('error'));
    expect(mockAppend).not.toHaveBeenCalled();
    expect(result.current.state.message).toBe('已取消拍照，停止采样');
  });
});
