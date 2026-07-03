import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import InterventionDraftSheet from '../InterventionDraftSheet';
import type { InterventionDraft } from '../../../services/interventionDraft';

const mockColors = {
  brand: '#0A8F8F',
  brandLight: '#E6F5F5',
  green: '#30D158',
  amber: '#FF9F0A',
  red: '#FF453A',
  purple: '#BF5AF2',
  blue: '#64D2FF',
  teal: '#5AC8FA',
  labelPrimary: '#1C1C1E',
  labelSecondary: '#636366',
  labelTertiary: '#AEAEB2',
  labelQuaternary: '#C7C7CC',
  separator: 'rgba(60,60,67,0.12)',
  bgPrimary: '#F2F2F7',
  bgCard: '#FFFFFF',
  bgElevated: '#FFFFFF',
  fill: '#E5E5EA',
  tintGreen: '#E8FAF0',
  tintAmber: '#FFF5E6',
  tintRed: '#FFE8E6',
  tintPurple: '#F5E6FF',
  tintPink: '#FFE6EE',
  tintOrange: '#FFF0E6',
  tintBlue: '#E6F5FF',
  tintTeal: '#E6F8FF',
};

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({ c: mockColors }),
}));

const draft: InterventionDraft = {
  title: '运动 30 分钟',
  content: '## 运动 30 分钟\n\n今天完成低强度运动，控制心率上限。\n\n复盘窗口：3 天后检查相关指标和主观感受。',
  card_type: 'plan',
  source_type: 'chat',
  source_id: 'msg-1',
  priority: 1,
  metric_key: 'rhr',
  verification_days: 3,
  checklist: [
    { item: '完成 30 分钟低强度运动', done: false },
    { item: '记录运动后主观感受', done: false },
  ],
};

describe('InterventionDraftSheet', () => {
  it('frames an AI suggestion as a cohesive today-plan confirmation card', () => {
    const { getByText, getByLabelText } = render(
      <InterventionDraftSheet
        visible
        draft={draft}
        onClose={jest.fn()}
        onSubmit={jest.fn()}
      />,
    );

    expect(getByText('加入今日计划')).toBeTruthy();
    expect(getByText('来自阿衡建议')).toBeTruthy();
    expect(getByText('今天执行')).toBeTruthy();
    expect(getByText('执行检查项')).toBeTruthy();
    expect(getByText('如何验证')).toBeTruthy();
    expect(getByText('确认加入今日计划')).toBeTruthy();
    expect(getByLabelText('今日计划标题')).toBeTruthy();
  });

  it('submits the edited today-plan draft', () => {
    const onSubmit = jest.fn();
    const { getByLabelText } = render(
      <InterventionDraftSheet
        visible
        draft={draft}
        onClose={jest.fn()}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.changeText(getByLabelText('今日计划标题'), '饭后散步 30 分钟');
    fireEvent.press(getByLabelText('确认加入今日计划'));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ title: '饭后散步 30 分钟' }),
    );
  });
});
