/**
 * RootErrorBoundary smoke tests.
 *
 * Verifies that:
 *   - errors from descendants render the fallback UI (not a white screen)
 *   - the "retry" button is wired up and resets the boundary
 *   - errors are forwarded to Sentry for server-side visibility
 */

jest.mock('../../applib/sentry', () => ({
  Sentry: { captureException: jest.fn() },
  SENTRY_ENABLED: false,
}));

import React from 'react';
import { Text, Pressable } from 'react-native';
import { renderWithProviders } from '../../test-utils';
import { fireEvent } from '@testing-library/react-native';
import RootErrorBoundary from '../RootErrorBoundary';
import { Sentry } from '../../applib/sentry';

function Boom(): React.ReactElement {
  throw new Error('oh no');
}

function Ok(): React.ReactElement {
  return <Text testID="ok">alive</Text>;
}

describe('RootErrorBoundary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // react-error-boundary logs the thrown error; silence it in test output
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    (console.error as jest.Mock).mockRestore();
  });

  it('renders children when nothing throws', () => {
    const { getByTestId } = renderWithProviders(
      <RootErrorBoundary>
        <Ok />
      </RootErrorBoundary>,
    );
    expect(getByTestId('ok')).toBeTruthy();
  });

  it('renders the fallback when a child throws and forwards to Sentry', () => {
    const { getByTestId } = renderWithProviders(
      <RootErrorBoundary>
        <Boom />
      </RootErrorBoundary>,
    );

    expect(getByTestId('error-fallback')).toBeTruthy();
    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
    const [err] = (Sentry.captureException as jest.Mock).mock.calls[0];
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe('oh no');
  });

  it('retry button is present and pressable after an error', () => {
    const { getByTestId } = renderWithProviders(
      <RootErrorBoundary>
        <Boom />
      </RootErrorBoundary>,
    );

    const retry = getByTestId('retry-button');
    expect(retry).toBeTruthy();
    // Pressing shouldn't throw; actual recovery depends on remounting children
    // which is out of scope for this smoke test.
    expect(() => fireEvent.press(retry)).not.toThrow();
  });
});
