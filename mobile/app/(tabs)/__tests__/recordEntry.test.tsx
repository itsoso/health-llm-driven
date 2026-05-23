/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium' },
}));

jest.mock('../../../services/dashboard', () => ({
  fetchDashboardData: jest.fn().mockResolvedValue({}),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    data: {},
    isLoading: false,
    isRefetching: false,
    refetch: jest.fn(),
  }),
  useQueryClient: () => ({
    invalidateQueries: jest.fn(),
  }),
}));

jest.mock('../../../hooks/useDashboardData', () => ({
  useLatestGarmin: () => null,
}));

jest.mock('../../../services/records', () => ({
  recordWater: jest.fn(),
  deleteWater: jest.fn(),
}));

jest.mock('../../../services/medicationFilters', () => ({
  filterMedicationRecordItems: () => [],
}));

jest.mock('../../../services/clientEvents', () => ({
  emitClientEvent: jest.fn(),
}));

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { post: jest.fn(), get: jest.fn() },
}));

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#fff',
      bgElevated: '#f8f8f8',
      labelPrimary: '#111',
      labelSecondary: '#555',
      labelTertiary: '#999',
      separator: '#eee',
      brand: '#0A8F8F',
      brandLight: '#E6F7F7',
      purple: '#7C3AED',
      pink: '#EC4899',
      blue: '#2563EB',
      teal: '#0F766E',
      orange: '#EA580C',
      green: '#16A34A',
      tintBlue: '#DBEAFE',
      tintGreen: '#DCFCE7',
      tintRed: '#FEE2E2',
      tintTeal: '#CCFBF1',
      tintPink: '#FCE7F3',
      tintPurple: '#EDE9FE',
      tintOrange: '#FFEDD5',
    },
  }),
}));

jest.mock('../../../components/dashboard/VitalsGrid', () => 'VitalsGrid');
jest.mock('../../../components/dashboard/ActivityRingBar', () => 'ActivityRingBar');
jest.mock('../../../components/dashboard/FitnessSnapshotCard', () => 'FitnessSnapshotCard');
jest.mock('../../../components/dashboard/SupplementCheckin', () => 'SupplementCheckin');
jest.mock('../../../components/dashboard/RhinitisCard', () => 'RhinitisCard');
jest.mock('../../../components/dashboard/StrengthCard', () => 'StrengthCard');
jest.mock('../../../components/dashboard/SymptomCard', () => 'SymptomCard');
jest.mock('../../../components/dashboard/WorkoutWeekCard', () => 'WorkoutWeekCard');
jest.mock('../../../components/design-system/HealthCard', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { View, Text } = require('react-native');
  const MockHealthCard = ({ title, children }: any) => (
    <View>
      <Text>{title}</Text>
      {children}
    </View>
  );
  MockHealthCard.displayName = 'MockHealthCard';
  return MockHealthCard;
});

import RecordScreen from '../record';

function renderScreen() {
  return render(<RecordScreen />);
}

describe('RecordScreen import shortcuts', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('keeps high-frequency record shortcuts focused and moves lower-frequency entries into more records', async () => {
    const { getByLabelText, getByText } = renderScreen();

    await waitFor(() => expect(getByText('高频记录')).toBeTruthy());
    expect(getByText('更多记录')).toBeTruthy();
    await waitFor(() => expect(getByText('化验记录')).toBeTruthy());
    expect(getByText('导入档案')).toBeTruthy();

    fireEvent.press(getByLabelText('化验记录'));
    expect(mockPush).toHaveBeenCalledWith('/medical-exams');

    fireEvent.press(getByLabelText('导入档案'));
    expect(mockPush).toHaveBeenCalledWith('/import');
  });
});
