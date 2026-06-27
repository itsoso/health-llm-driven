import React from 'react';
import { render } from '@testing-library/react-native';
import { renderCard, renderServerCards } from '../registry';

describe('DiscoveryCard', () => {
  const descriptor = {
    type: 'discovery',
    data: {
      title: '最近睡眠连续性变好',
      level: 'hypothesis',
      summary: '过去 5 晚夜间醒来次数下降，可能和晚间咖啡减少有关。',
      evidence: [
        '夜间醒来次数 4 次 -> 1 次',
        '入睡前咖啡因记录减少',
        'HRV 7 日均值小幅回升',
        '这条不应展示',
      ],
      boundary: '观察性线索，不代表因果已经验证。',
    },
  };

  it('renders discovery evidence with a hedged level', () => {
    const element = renderCard(descriptor);
    expect(element).not.toBeNull();

    const screen = render(element!);
    expect(screen.getByText('最近睡眠连续性变好')).toBeTruthy();
    expect(screen.getByText('待验证')).toBeTruthy();
    expect(screen.getByText('过去 5 晚夜间醒来次数下降，可能和晚间咖啡减少有关。')).toBeTruthy();
    expect(screen.getByText('夜间醒来次数 4 次 -> 1 次')).toBeTruthy();
    expect(screen.getByText('入睡前咖啡因记录减少')).toBeTruthy();
    expect(screen.getByText('HRV 7 日均值小幅回升')).toBeTruthy();
    expect(screen.queryByText('这条不应展示')).toBeNull();
    expect(screen.getByText('观察性线索，不代表因果已经验证。')).toBeTruthy();
  });

  it('accepts backend discovery descriptors', () => {
    expect(renderServerCards([descriptor]).map((card) => card.type)).toEqual(['discovery']);
  });
});
