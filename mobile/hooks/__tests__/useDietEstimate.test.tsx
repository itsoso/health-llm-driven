/* eslint-disable import/first */
import { act, renderHook } from '@testing-library/react-native';

const mockEstimateNutrition = jest.fn();
const mockUpdateDietRecord = jest.fn();
const mockInvalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));
jest.mock('../../services/diet', () => ({
  estimateNutrition: (...args: unknown[]) => mockEstimateNutrition(...args),
  updateDietRecord: (...args: unknown[]) => mockUpdateDietRecord(...args),
}));

import { estimateSourceForRecord, useDietEstimate } from '../useDietEstimate';

describe('useDietEstimate', () => {
  beforeEach(() => jest.clearAllMocks());

  it('retries the persisted edited food, not the original photo or text source', () => {
    const cached = { source: { kind: 'photo' as const, imageBase64: 'old-image' }, foodItems: '一碗汤' };
    expect(estimateSourceForRecord('牛肉面约一碗', cached)).toEqual({
      kind: 'text', description: '牛肉面约一碗',
    });
    expect(estimateSourceForRecord('一碗汤', cached)).toEqual(cached.source);
  });

  it('does not write the old estimate after the meal has been edited', async () => {
    let resolveEstimate!: (value: unknown) => void;
    mockEstimateNutrition.mockReturnValueOnce(new Promise(resolve => { resolveEstimate = resolve; }));
    const { result } = renderHook(() => useDietEstimate());

    let pending!: Promise<void>;
    act(() => { pending = result.current.estimate(42, { kind: 'text', description: '一碗汤' }, '2026-09-20T12:00:00Z'); });
    act(() => { result.current.cancelEstimate(42); });
    await act(async () => {
      resolveEstimate({ success: true, total_calories: 100, total_protein: 3 });
      await pending;
    });

    expect(mockUpdateDietRecord).not.toHaveBeenCalled();
    expect(result.current.pendingIds.has(42)).toBe(false);
    expect(result.current.failedIds.has(42)).toBe(false);
  });

  it('only lets the newest estimate complete for the same record', async () => {
    let resolveOld!: (value: unknown) => void;
    mockEstimateNutrition.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }));
    mockEstimateNutrition.mockResolvedValueOnce({ success: true, total_calories: 620 });
    mockUpdateDietRecord.mockResolvedValue({ id: 42 });
    const { result } = renderHook(() => useDietEstimate());

    let oldPending!: Promise<void>;
    act(() => { oldPending = result.current.estimate(42, { kind: 'text', description: '一碗汤' }, '2026-09-20T12:00:00Z'); });
    await act(async () => {
      await result.current.estimate(42, { kind: 'text', description: '牛肉面约一碗' }, '2026-09-20T12:01:00Z');
    });
    await act(async () => {
      resolveOld({ success: true, total_calories: 100 });
      await oldPending;
    });

    expect(mockUpdateDietRecord).toHaveBeenCalledTimes(1);
    expect(mockUpdateDietRecord).toHaveBeenCalledWith(42, expect.objectContaining({
      calories: 620, expected_updated_at: '2026-09-20T12:01:00Z',
    }));
    expect(result.current.failedIds.has(42)).toBe(false);
  });

  it('joins a nutrition write already sent before allowing a correction', async () => {
    mockEstimateNutrition.mockResolvedValueOnce({ success: true, total_calories: 100 });
    let resolveWrite!: (value: unknown) => void;
    mockUpdateDietRecord.mockReturnValueOnce(new Promise(resolve => { resolveWrite = resolve; }));
    const { result } = renderHook(() => useDietEstimate());

    let pending!: Promise<void>;
    act(() => { pending = result.current.estimate(42, { kind: 'text', description: '一碗汤' }, '2026-09-20T12:00:00Z'); });
    await act(async () => { await Promise.resolve(); });
    expect(mockUpdateDietRecord).toHaveBeenCalledTimes(1);

    let joined!: Promise<unknown>;
    act(() => { joined = result.current.cancelEstimate(42); });
    let completed = false;
    void joined.then(() => { completed = true; });
    await act(async () => { await Promise.resolve(); });
    expect(completed).toBe(false);
    await act(async () => {
      resolveWrite({ id: 42, updated_at: '2026-09-20T14:00:00Z' });
      await pending;
    });
    await expect(joined).resolves.toEqual({ id: 42, updated_at: '2026-09-20T14:00:00Z' });
  });

  it('refreshes the corrected record when another device wins the revision race', async () => {
    mockEstimateNutrition.mockResolvedValueOnce({ success: true, total_calories: 100 });
    mockUpdateDietRecord.mockRejectedValueOnce({ response: { status: 409 } });
    const { result } = renderHook(() => useDietEstimate());

    await act(async () => {
      await result.current.estimate(
        42, { kind: 'text', description: '一碗汤' }, '2026-09-20T12:00:00Z',
      );
    });

    expect(mockUpdateDietRecord).toHaveBeenCalledWith(42, expect.objectContaining({
      calories: 100, expected_updated_at: '2026-09-20T12:00:00Z',
    }));
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['diet'] });
    expect(result.current.failedIds.has(42)).toBe(true);
  });
});
