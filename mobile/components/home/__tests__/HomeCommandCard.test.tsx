import React from 'react';
import { render } from '@testing-library/react-native';

import HomeCommandCard from '../HomeCommandCard';

describe('HomeCommandCard', () => {
  it('uses 阿衡 as the visible assistant persona', () => {
    const { getByLabelText, getByText, queryByText, queryByLabelText } = render(
      <HomeCommandCard
        agentJudgmentText="今天优先稳定血糖波动。"
        nextStepActionText="饭后散步 15 分钟"
        actionLeverLabel="现在只做"
        refreshing={false}
        hasCritical={false}
        canComplete
        completionState="idle"
        onPressJudgment={jest.fn()}
        onPressAction={jest.fn()}
        onPressAgent={jest.fn()}
        onPressComplete={jest.fn()}
      />,
    );

    expect(getByText('阿衡')).toBeTruthy();
    expect(getByLabelText('问阿衡原因')).toBeTruthy();
    expect(queryByText('健康 Agent')).toBeNull();
    expect(queryByLabelText('问 Agent 原因')).toBeNull();
  });
});
