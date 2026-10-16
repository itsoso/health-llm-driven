import { act, renderHook, waitFor } from '@testing-library/react-native';
import { getPostWorkoutAnalysis } from '../../services/workouts';
import { useWorkoutAutoAnalysis } from '../useWorkoutAutoAnalysis';

const mockAuth = { user: { id: 7 }, token: 'synthetic' };
jest.mock('../useAuth', () => ({ useAuth: () => mockAuth }));

jest.mock('../../services/workouts', () => ({
  getPostWorkoutAnalysis: jest.fn(),
}));

const mockedGetPostWorkoutAnalysis = getPostWorkoutAnalysis as jest.MockedFunction<
  typeof getPostWorkoutAnalysis
>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('useWorkoutAutoAnalysis', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('does not let a stale workout request overwrite the newly opened workout', async () => {
    const first = deferred<any>();
    const second = deferred<any>();
    mockedGetPostWorkoutAnalysis
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result, rerender } = renderHook<
      ReturnType<typeof useWorkoutAutoAnalysis>,
      { workoutId: number }
    >(
      ({ workoutId }) => useWorkoutAutoAnalysis({
        workoutId,
        workout: { id: workoutId, user_id: 7, ai_analysis: null, post_workout_analysis: null },
      }),
      { initialProps: { workoutId: 1 } },
    );

    rerender({ workoutId: 2 });
    await act(async () => {
      second.resolve({ success: true, workout_id: 2, summary: '训练 B' });
      await second.promise;
    });
    await waitFor(() => {
      expect((result.current.postAnalysis as any)?.workout_id).toBe(2);
    });

    await act(async () => {
      first.resolve({ success: true, workout_id: 1, summary: '训练 A' });
      await first.promise;
    });

    expect((result.current.postAnalysis as any)?.workout_id).toBe(2);
  });
});


beforeEach(() => { jest.clearAllMocks(); mockAuth.user = { id: 7 }; mockAuth.token = 'synthetic'; });

it('preserves stored post-workout report and exposes cache refresh failure', async () => {
  mockedGetPostWorkoutAnalysis.mockRejectedValue(new Error('offline'));
  const { result } = renderHook(() => useWorkoutAutoAnalysis({ workoutId: 1,
    workout: { id: 1, user_id: 7, ai_analysis: null, post_workout_analysis: JSON.stringify({ success: true, content: 'Stored report' }) } }));
  await waitFor(() => expect(result.current.cacheReadError).toBe(true));
  expect(result.current.postAnalysis?.content).toBe('Stored report');
  expect(mockedGetPostWorkoutAnalysis).toHaveBeenCalledWith(1, false, true);
});
it('rejects wrong workout and owner before reading or displaying stored reports', () => {
  const { result } = renderHook(() => useWorkoutAutoAnalysis({ workoutId: 1,
    workout: { id: 2, user_id: 8, ai_analysis: null, post_workout_analysis: JSON.stringify({ success: true, content: 'Foreign' }) } }));
  expect(result.current.postAnalysis).toBeNull();
  expect(mockedGetPostWorkoutAnalysis).not.toHaveBeenCalled();
});

it.each(['not json', '[]', 'null', '{"success":false,"content":"invalid"}'])('ignores malformed stored report: %s', async raw => {
  mockedGetPostWorkoutAnalysis.mockResolvedValue({ success: false, has_cache: false });
  const { result } = renderHook(() => useWorkoutAutoAnalysis({ workoutId: 1,
    workout: { id: 1, user_id: 7, ai_analysis: null, post_workout_analysis: raw } }));
  await waitFor(() => expect(mockedGetPostWorkoutAnalysis).toHaveBeenCalled());
  expect(result.current.postAnalysis).toBeNull();
});
it('reopening restores persisted producer response without generation', async () => {
  mockedGetPostWorkoutAnalysis.mockRejectedValue(new Error('offline'));
  const workout = { id: 1, user_id: 7, ai_analysis: null, post_workout_analysis: JSON.stringify({ success: true, overall_rating: { rating: 'synthetic', score: 5 }, workout_summary: {} }) };
  const first = renderHook(() => useWorkoutAutoAnalysis({ workoutId: 1, workout }));
  await waitFor(() => expect(first.result.current.cacheReadError).toBe(true));
  first.unmount();
  const second = renderHook(() => useWorkoutAutoAnalysis({ workoutId: 1, workout }));
  await waitFor(() => expect(second.result.current.cacheReadError).toBe(true));
  expect(second.result.current.postAnalysis?.overall_rating).toEqual({ rating: 'synthetic', score: 5 });
  expect(mockedGetPostWorkoutAnalysis.mock.calls.every(args => args[1] === false && args[2] === true)).toBe(true);
});

it('account change hides old stored data and discards its pending response', async () => {
  const pending = deferred<any>();
  mockedGetPostWorkoutAnalysis.mockReturnValue(pending.promise);
  const { result, rerender } = renderHook(() => useWorkoutAutoAnalysis({ workoutId: 1,
    workout: { id: 1, user_id: 7, ai_analysis: null, post_workout_analysis: JSON.stringify({ success: true, content: 'Owner seven' }) } }));
  expect(result.current.postAnalysis?.content).toBe('Owner seven');
  mockAuth.user = { id: 8 }; mockAuth.token = 'other-session'; rerender({});
  expect(result.current.postAnalysis).toBeNull();
  await act(async () => { pending.resolve({ success: true, content: 'Late owner seven' }); await pending.promise; });
  expect(result.current.postAnalysis).toBeNull();
  expect(mockedGetPostWorkoutAnalysis).toHaveBeenCalledTimes(1);
});
