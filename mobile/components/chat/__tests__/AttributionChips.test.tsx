import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import AttributionChips from '../AttributionChips';

describe('AttributionChips', () => {
  it('renders only structured source metadata and deduplicates exact labels', () => {
    const { getByText, queryByText } = render(
      <AttributionChips
        sources={[
          'Garmin 数据 (14 天 HRV/睡眠/RHR)',
          '用户记忆',
          'Garmin 数据 (14 天 HRV/睡眠/RHR)',
        ]}
      />,
    );

    expect(getByText('Garmin 数据 (14 天 HRV/睡眠/RHR)')).toBeTruthy();
    expect(getByText('用户记忆')).toBeTruthy();
    expect(queryByText('+1')).toBeNull();
  });

  it('does not infer a source from assistant prose', () => {
    const { queryByLabelText } = render(
      <AttributionChips sources={[]} />,
    );

    expect(queryByLabelText('AI 用到了你的数据')).toBeNull();
  });

  it('routes a structured memory source to memory management', () => {
    const onOpenMemory = jest.fn();
    const { getByLabelText } = render(
      <AttributionChips sources={['用户记忆']} onOpenMemory={onOpenMemory} />,
    );

    fireEvent.press(getByLabelText('查看 AI 记忆来源'));
    expect(onOpenMemory).toHaveBeenCalledTimes(1);
  });
});
