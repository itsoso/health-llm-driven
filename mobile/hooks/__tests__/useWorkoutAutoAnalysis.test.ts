import { act, renderHook, waitFor } from '@testing-library/react-native';
import { getPostWorkoutAnalysis } from '../../services/workouts';
import { useWorkoutAutoAnalysis } from '../useWorkoutAutoAnalysis';

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
        workout: { id: workoutId, ai_analysis: null },
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
