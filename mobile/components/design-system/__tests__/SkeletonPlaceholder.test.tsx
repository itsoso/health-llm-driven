import React from 'react';
import { render } from '@testing-library/react-native';
import {
  HomeHeaderSkeleton,
  CardSkeleton,
  VitalsGridSkeleton,
  TrendChartSkeleton,
  ChatSkeleton,
} from '../SkeletonPlaceholder';

jest.useFakeTimers();

describe('SkeletonPlaceholder', () => {
  it('HomeHeaderSkeleton renders without crashing', () => {
    const { toJSON } = render(<HomeHeaderSkeleton />);
    expect(toJSON()).toBeTruthy();
  });

  it('CardSkeleton renders without crashing', () => {
    const { toJSON } = render(<CardSkeleton />);
    expect(toJSON()).toBeTruthy();
  });

  it('VitalsGridSkeleton renders 4 items', () => {
    const { toJSON } = render(<VitalsGridSkeleton />);
    const tree = toJSON() as any;
    expect(tree.children).toHaveLength(4);
  });

  it('TrendChartSkeleton has testID', () => {
    const { getByTestId } = render(<TrendChartSkeleton />);
    expect(getByTestId('trend-chart-skeleton')).toBeTruthy();
  });

  it('ChatSkeleton has testID', () => {
    const { getByTestId } = render(<ChatSkeleton />);
    expect(getByTestId('chat-skeleton')).toBeTruthy();
  });
});
