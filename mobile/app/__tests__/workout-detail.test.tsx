import React from 'react';
import { render } from '@testing-library/react-native';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { extra: {} } } }));
jest.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: undefined }) }));
jest.mock('../../hooks/useWorkouts', () => ({ useWorkoutDetail: jest.fn() }));
jest.mock('../../hooks/useWorkoutAutoAnalysis', () => ({
  useWorkoutAutoAnalysis: () => ({ analysis: null, postAnalysis: null, fromCache: false }),
}));
jest.mock('../../services/workouts', () => ({}));
jest.mock('../../services/cloudTts', () => ({}));
jest.mock('../../services/voiceStyle', () => ({}));
jest.mock('../../utils/share', () => ({}));
jest.mock('../../utils/agentContext', () => ({}));
jest.mock('expo-audio', () => ({}));
jest.mock('react-native-maps', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: jest.fn((props: any) => React.createElement(View, { ...props, testID: 'native-map' })),
    Polyline: (props: any) => React.createElement(View, props),
    Marker: (props: any) => React.createElement(View, props),
  };
});

import MapView from 'react-native-maps';
import { useWorkoutDetail } from '../../hooks/useWorkouts';
import WorkoutDetailScreen from '../workout-detail';

const unavailableMessage = '当前设备暂不支持地图展示，其他运动数据仍可查看。';
const originalPlatform = Platform.OS;
const route = [{ lat: 30, lng: 104 }, { lat: 30.001, lng: 104.001 }];

describe('workout detail native Maps capability', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'android' });
    (Constants.expoConfig as any).extra = {};
    (useWorkoutDetail as jest.Mock).mockReturnValue({
      isLoading: false,
      data: { id: 1, workout_type: 'running', workout_name: '测试运动', calories: 123, route_data: JSON.stringify(route) },
    });
  });

  afterEach(() => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: originalPlatform });
  });

  it.each([undefined, false, 'true'])('does not mount Android Maps without explicit native configuration: %s', (value) => {
    (Constants.expoConfig as any).extra = { release: { capabilities: { androidGoogleMapsConfigured: value } } };
    const screen = render(<WorkoutDetailScreen />);
    expect(MapView).not.toHaveBeenCalled();
    expect(screen.getByText(unavailableMessage)).toBeTruthy();
    expect(screen.getByText('测试运动')).toBeTruthy();
    expect(screen.getByText('123')).toBeTruthy();
    expect(screen.getByText('详细指标')).toBeTruthy();
  });

  it('mounts Android Maps when native configuration is explicitly present', () => {
    (Constants.expoConfig as any).extra = { release: { capabilities: { androidGoogleMapsConfigured: true } } };
    const screen = render(<WorkoutDetailScreen />);
    expect(screen.getByTestId('native-map')).toBeTruthy();
    expect(screen.queryByText(unavailableMessage)).toBeNull();
  });

  it('preserves iOS Maps without an Android key', () => {
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'ios' });
    const screen = render(<WorkoutDetailScreen />);
    expect(screen.getByTestId('native-map')).toBeTruthy();
    expect(screen.queryByText(unavailableMessage)).toBeNull();
  });

  it('does not show a map or capability warning for fewer than two route points', () => {
    (useWorkoutDetail as jest.Mock).mockReturnValue({
      isLoading: false,
      data: { id: 1, workout_type: 'running', route_data: JSON.stringify(route.slice(0, 1)) },
    });
    const screen = render(<WorkoutDetailScreen />);
    expect(MapView).not.toHaveBeenCalled();
    expect(screen.queryByText(unavailableMessage)).toBeNull();
  });
});
