/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';

import { renderWithProviders } from '../../test-utils';

jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn() },
  useLocalSearchParams: () => ({ focus: 'medical' }),
}));

jest.mock('../../components/medical/MedicalExamImportFlow', () => (
  function MockMedicalExamImportFlow(props: any) {
    const { Pressable, Text } = require('react-native');

    return (
      <Pressable accessibilityLabel="关闭统一体检导入" onPress={props.onClose}>
        <Text>统一体检导入流程</Text>
      </Pressable>
    );
  }
));

import ImportScreen from '../import';

describe('focused medical import route', () => {
  it('uses the same full-screen import flow as Chat', () => {
    const screen = renderWithProviders(<ImportScreen />);

    expect(screen.getByText('统一体检导入流程')).toBeTruthy();
  });
});
