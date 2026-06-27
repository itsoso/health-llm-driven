import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn().mockResolvedValue(undefined),
}));

import RevaTryEntryCard from '../RevaTryEntryCard';

describe('RevaTryEntryCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('opens the isolated demo on-ramp before entering Reva', () => {
    const { getByLabelText } = render(<RevaTryEntryCard />);

    fireEvent.press(getByLabelText('试试新版复元'));

    expect(mockPush).toHaveBeenCalledWith('/reva-onboarding?mode=demo');
  });
});
