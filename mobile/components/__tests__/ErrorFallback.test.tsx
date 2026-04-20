import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import ErrorFallback from '../ErrorFallback';

describe('ErrorFallback', () => {
  it('shows server error message by default', () => {
    const { getByText } = render(
      <ErrorFallback error={new Error('500 Internal Server Error')} />,
    );
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('500 Internal Server Error')).toBeTruthy();
  });

  it('shows offline message when isOffline', () => {
    const { getByText } = render(
      <ErrorFallback error={new Error('Network Error')} isOffline />,
    );
    expect(getByText('无法连接网络')).toBeTruthy();
    expect(getByText('请检查网络连接后重试')).toBeTruthy();
  });

  it('shows retry button when onRetry is provided', () => {
    const onRetry = jest.fn();
    const { getByTestId } = render(
      <ErrorFallback error={new Error('fail')} onRetry={onRetry} />,
    );
    fireEvent.press(getByTestId('retry-button'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('hides retry button when no onRetry', () => {
    const { queryByTestId } = render(
      <ErrorFallback error={new Error('fail')} />,
    );
    expect(queryByTestId('retry-button')).toBeNull();
  });

  it('renders error-fallback testID', () => {
    const { getByTestId } = render(
      <ErrorFallback error={new Error('fail')} />,
    );
    expect(getByTestId('error-fallback')).toBeTruthy();
  });
});
