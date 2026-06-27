/* eslint-disable import/first */
import React from 'react';
import { fireEvent } from '@testing-library/react-native';

import { renderWithProviders } from '../../test-utils';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockListMedicalExams = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush }),
  useFocusEffect: (cb: () => void | (() => void)) => cb(),
}));

jest.mock('../../services/medicalExams', () => {
  const actual = jest.requireActual('../../services/medicalExams');
  return {
    ...actual,
    listMedicalExams: (...args: any[]) => mockListMedicalExams(...args),
  };
});

import MedicalExamsScreen from '../medical-exams';

describe('MedicalExamsScreen import entry', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListMedicalExams.mockResolvedValue([]);
  });

  it('routes directly to the focused medical import flow', () => {
    const { getByLabelText } = renderWithProviders(<MedicalExamsScreen />);

    fireEvent.press(getByLabelText('导入体检报告'));

    expect(mockPush).toHaveBeenCalledWith({
      pathname: '/import',
      params: { focus: 'medical' },
    });
  });
});
