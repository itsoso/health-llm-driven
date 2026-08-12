import React from 'react';
import { StyleSheet } from 'react-native';
import { render } from '@testing-library/react-native';
import { AppleHealthRow } from '../AppleHealthRow';

jest.mock('../../services/appleHealth', () => ({
  isHealthKitAvailable: () => true,
  requestPermissions: jest.fn(),
  syncRecentDays: jest.fn(),
  backfillAll: jest.fn(),
  getHealthKitAuthorized: jest.fn(async () => false),
  persistHealthKitAuthorized: jest.fn(),
  getHealthKitLastSync: jest.fn(async () => null),
  persistHealthKitLastSync: jest.fn(),
}));

jest.mock('../../services/dataConnections', () => ({
  ensureHealthKitServerConsent: jest.fn(),
}));

describe('AppleHealthRow', () => {
  it('exposes a named button with a full-size touch target', () => {
    const { getByRole } = render(<AppleHealthRow />);
    const row = getByRole('button', { name: 'Apple Health，未授权' });
    const style = StyleSheet.flatten(row.props.style);

    expect(style.minHeight).toBeGreaterThanOrEqual(48);
    expect(row.props.accessibilityState).toEqual({ disabled: false });
  });
});
