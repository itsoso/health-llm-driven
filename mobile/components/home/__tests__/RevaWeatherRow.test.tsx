import React from 'react';
import { render } from '@testing-library/react-native';

import RevaWeatherRow from '../RevaWeatherRow';

const mockPush = jest.fn();
let mockWeather: any = { temperature: 25, weather: '多云', humidity: 62 };
let mockAqi: any = { aqi: 50, pm25: 20 };
let mockForecast: any[] | null = null;
let mockLocation: any = { city: '杭州', region: '浙江' };

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    if (key === 'env:weather') return { data: mockWeather };
    if (key === 'env:aqi') return { data: mockAqi };
    if (key === 'env:forecast') return { data: mockForecast };
    if (key === 'env:location') return { data: mockLocation };
    return { data: null };
  },
}));

describe('RevaWeatherRow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockWeather = { temperature: 25, weather: '多云', humidity: 62 };
    mockAqi = { aqi: 50, pm25: 20 };
    mockForecast = null;
    mockLocation = { city: '杭州', region: '浙江' };
  });

  it('does not render for indoor recovery or generic training with normal air', () => {
    const { toJSON } = render(
      <RevaWeatherRow relevanceText="今日训练:恢复/休息,暂停高强度;优先睡眠与轻活动" />,
    );

    expect(toJSON()).toBeNull();
  });

  it('renders when the current action explicitly depends on outdoor context', () => {
    const { getByText } = render(
      <RevaWeatherRow relevanceText="午饭后到户外步行 10 分钟,注意空气质量" />,
    );

    expect(getByText('杭州 · 25° · 多云')).toBeTruthy();
    expect(getByText('空气 优')).toBeTruthy();
  });

  it('renders when air quality needs attention even without an outdoor action', () => {
    mockAqi = { aqi: 135, pm25: 73 };

    const { getByText } = render(
      <RevaWeatherRow relevanceText="今天优先室内恢复和补水" />,
    );

    expect(getByText('杭州 · 25° · 多云')).toBeTruthy();
    expect(getByText('空气 轻度')).toBeTruthy();
  });
});
