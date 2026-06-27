import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import DailyArtifactCard from '../DailyArtifactCard';
import type { DailyArtifact } from '../../../services/dailyArtifact';

const artifact: DailyArtifact = {
  stateLabel: '今日状态',
  readiness: { score: 86, label: '可上强度', asOf: '2026-06-27' },
  topAction: {
    title: '喝 200ml 温水',
    subtitle: '起床后补水',
    scheduledFor: '08:00',
    source: 'timeline',
    canComplete: true,
    completeRef: { object_type: 'health_protocol', object_id: 12 },
    deepLink: null,
  },
  evidence: [
    { id: 'sleep', label: '睡眠', value: '7.2 h', tone: 'normal' },
    { id: 'hrv', label: 'HRV', value: '48 ms', tone: 'info' },
    { id: 'spo2', label: '血氧', value: '97%', tone: 'normal' },
  ],
  freshness: { label: '10 分钟前同步', tone: 'normal', lastSyncAt: 1 },
  safetyBoundary: { level: 'normal', label: '安全边界正常' },
  actions: { canComplete: true, canSkip: true, skipRequiresReason: true, canAskReva: true },
  tracking: {
    artifactId: '2026-06-27:timeline:hydration-1',
    weekIndex: 26,
    topActionSource: 'timeline',
  },
};

describe('DailyArtifactCard', () => {
  it('renders one top action, freshness, safety boundary, and up to three evidence chips', () => {
    const { getByText, queryByText } = render(<DailyArtifactCard artifact={artifact} />);

    expect(getByText('今日状态')).toBeTruthy();
    expect(getByText('喝 200ml 温水')).toBeTruthy();
    expect(getByText('起床后补水')).toBeTruthy();
    expect(getByText('10 分钟前同步')).toBeTruthy();
    expect(getByText('安全边界正常')).toBeTruthy();
    expect(getByText('睡眠')).toBeTruthy();
    expect(getByText('7.2 h')).toBeTruthy();
    expect(getByText('HRV')).toBeTruthy();
    expect(getByText('48 ms')).toBeTruthy();
    expect(getByText('血氧')).toBeTruthy();
    expect(queryByText('第四条证据')).toBeNull();
  });

  it('routes complete, skip, ask, and primary action through callbacks', () => {
    const onPressAction = jest.fn();
    const onComplete = jest.fn();
    const onSkip = jest.fn();
    const onAskReva = jest.fn();
    const { getByLabelText, getByText } = render(
      <DailyArtifactCard
        artifact={artifact}
        onPressAction={onPressAction}
        onComplete={onComplete}
        onSkip={onSkip}
        onAskReva={onAskReva}
      />,
    );

    fireEvent.press(getByLabelText('今日最重要行动:喝 200ml 温水'));
    fireEvent.press(getByText('完成'));
    fireEvent.press(getByText('跳过'));
    fireEvent.press(getByText('问 Reva'));

    expect(onPressAction).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onAskReva).toHaveBeenCalledTimes(1);
  });

  it('requires a concrete skip reason before calling the skip callback', () => {
    const onSkipReason = jest.fn();
    const { getByText, queryByText } = render(
      <DailyArtifactCard
        artifact={artifact}
        showSkipReasons
        skipReasons={[{ value: 'too_tired', label: '太累' }, { value: 'no_time', label: '没时间' }]}
        onSkipReason={onSkipReason}
      />,
    );

    expect(getByText('为什么跳过?')).toBeTruthy();
    expect(queryByText('太累')).toBeTruthy();

    fireEvent.press(getByText('太累'));

    expect(onSkipReason).toHaveBeenCalledWith('too_tired');
  });
});
