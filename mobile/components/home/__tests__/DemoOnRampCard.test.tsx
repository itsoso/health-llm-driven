import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import DemoOnRampCard from '../DemoOnRampCard';
import { buildDemoOnRampRuntime } from '../../../services/demoOnRamp';

describe('DemoOnRampCard', () => {
  it('renders a clearly isolated 5-minute demo path and its expected milestones', () => {
    const runtime = buildDemoOnRampRuntime(new Date('2026-06-27T08:00:00+08:00').getTime());
    const onOpenDemo = jest.fn();
    const onConnectHealthKit = jest.fn();

    const { getByLabelText, getByText } = render(
      <DemoOnRampCard
        runtime={runtime}
        onOpenDemo={onOpenDemo}
        onConnectHealthKit={onConnectHealthKit}
      />,
    );

    expect(getByText('5 分钟示例体验')).toBeTruthy();
    expect(getByText('示例数据,不写入真实档案')).toBeTruthy();
    expect(getByText('安全脑拦截')).toBeTruthy();
    expect(getByText('证据卡')).toBeTruthy();
    expect(getByText('下一步行动')).toBeTruthy();

    fireEvent.press(getByLabelText('打开 Reva 示例体验'));
    expect(onOpenDemo).toHaveBeenCalledTimes(1);

    fireEvent.press(getByLabelText('连接 HealthKit'));
    expect(onConnectHealthKit).toHaveBeenCalledTimes(1);
  });
});
