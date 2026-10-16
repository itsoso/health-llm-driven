import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
const mockPush = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush, back: jest.fn() }) }));
import WorkoutListScreen from '../workout-list';

jest.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: jest.fn() }) }));
jest.mock('../../hooks/useWorkouts', () => ({
  useWorkoutList: () => ({ data: [{ id: 42, workout_name: '晨跑', workout_type: 'running', duration_seconds: 1200 }], isLoading: false, isRefetching: false, refetch: jest.fn() }),
  useWorkoutStats: () => ({ data: undefined }),
}));
jest.mock('../../services/workouts', () => ({ syncGarminWorkouts: jest.fn() }));
jest.mock('../../utils/agentContext', () => ({ createWorkoutAgentContext: jest.fn(), pushChatWithContext: jest.fn() }));

it('opens the same saved workout again after leaving the list', () => {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const view = render(<WorkoutListScreen />);
    fireEvent.press(view.getByRole('button', { name: '查看晨跑详情与总结' }));
    expect(mockPush).toHaveBeenLastCalledWith('/workout-detail?id=42');
    view.unmount();
  }
});
