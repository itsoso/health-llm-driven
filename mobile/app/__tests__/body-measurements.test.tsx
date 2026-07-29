/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockBack = jest.fn();
const mockPost = jest.fn();
const mockGet = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack }),
  useLocalSearchParams: () => ({ focus: 'morning' }),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success' },
}));

jest.mock('../../services/api', () => ({
  get: (...args: any[]) => mockGet(...args),
  post: (...args: any[]) => mockPost(...args),
}));

import BodyMeasurementsScreen from '../body-measurements';

jest.spyOn(console, 'error').mockImplementation(() => undefined);

function renderScreen() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <BodyMeasurementsScreen />
    </QueryClientProvider>,
  );
}

describe('BodyMeasurementsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/weight/records/me')) return Promise.resolve({ data: [{ weight: 78.2, record_date: '2026-05-14' }] });
      if (url === '/waist/records/me/latest') return Promise.resolve({ data: { waist_cm: 91.5, record_date: '2026-05-14' } });
      return Promise.resolve({ data: null });
    });
    mockPost.mockResolvedValue({ data: {} });
  });

  it('saves weight and waist from the morning plan entry', async () => {
    const { getByLabelText } = renderScreen();

    fireEvent.changeText(getByLabelText('体重 kg'), '77.8');
    fireEvent.changeText(getByLabelText('腰围 cm'), '90.5');
    fireEvent.press(getByLabelText('保存体重和腰围'));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/weight/records', expect.objectContaining({ weight: 77.8 }));
      expect(mockPost).toHaveBeenCalledWith('/waist/records', expect.objectContaining({ waist_cm: 90.5, source: 'manual' }));
    });
  });
});
