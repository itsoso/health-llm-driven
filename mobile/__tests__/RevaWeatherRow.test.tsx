/**
 * RevaWeatherRow —— 单行天气 pill 收折行为测试。
 *
 * 默认一行(城市 · 温度 · 天气 + 空气 chip);湿度/AQI/PM2.5/明日藏在展开里,点箭头才露。
 */
import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(async (url: string) => {
      if (url === '/environment/weather') {
        return { data: { weather: { temperature: 24, weather: '多云', humidity: 58 } } };
      }
      if (url === '/environment/air-quality') {
        return { data: { aqi: 42, pm25: 11 } };
      }
      if (url === '/environment/weather/forecast') {
        return { data: { available: true, forecasts: [] } };
      }
      if (url === '/profile/me') {
        return { data: { detected_location: { city: '北京', region: '北京' } } };
      }
      return { data: null };
    }),
  },
}));

import RevaWeatherRow from '../components/home/RevaWeatherRow';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('RevaWeatherRow (one-line collapse)', () => {
  it('shows the compact one-line summary and hides detail by default', async () => {
    const { getByText, queryByText } = wrap(<RevaWeatherRow />);
    await waitFor(() => expect(getByText(/北京 · 24° · 多云/)).toBeTruthy());
    // 空气 chip 在主行
    expect(getByText('空气 优')).toBeTruthy();
    // 湿度 / PM2.5 默认折叠,不在屏
    expect(queryByText('湿度')).toBeNull();
    expect(queryByText('PM2.5')).toBeNull();
  });

  it('reveals humidity / AQI / PM2.5 after tapping expand', async () => {
    const { getByText, getByLabelText, queryByText } = wrap(<RevaWeatherRow />);
    await waitFor(() => expect(getByText(/北京 · 24°/)).toBeTruthy());
    expect(queryByText('湿度')).toBeNull();
    fireEvent.press(getByLabelText('展开天气详情'));
    await waitFor(() => expect(getByText('湿度')).toBeTruthy());
    expect(getByText('PM2.5')).toBeTruthy();
  });
});
