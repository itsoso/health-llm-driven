import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import AttributionChips from '../AttributionChips';

describe('AttributionChips', () => {
  it('renders only structured source metadata and keeps details collapsed by default', () => {
    const { getByLabelText, getByText, queryByText } = render(
      <AttributionChips
        sources={[
          'Garmin 数据 (14 天 HRV/睡眠/RHR)',
          '用户记忆',
          'Garmin 数据 (14 天 HRV/睡眠/RHR)',
        ]}
      />,
    );

    expect(getByText('使用数据 · 2 项')).toBeTruthy();
    expect(queryByText('Garmin 数据 (14 天 HRV/睡眠/RHR)')).toBeNull();
    expect(queryByText('用户记忆')).toBeNull();
    fireEvent.press(getByLabelText('展开使用数据'));
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
    const { getByLabelText, getByText } = render(
      <AttributionChips sources={['用户记忆']} onOpenMemory={onOpenMemory} />,
    );

    fireEvent.press(getByLabelText('展开使用数据'));
    const memorySource = getByLabelText('查看 AI 记忆来源：用户记忆');
    expect(memorySource).toHaveStyle({ minHeight: 44 });
    expect(getByText('用户记忆').props.numberOfLines).toBeUndefined();
    fireEvent.press(memorySource);
    expect(onOpenMemory).toHaveBeenCalledTimes(1);
  });
});
