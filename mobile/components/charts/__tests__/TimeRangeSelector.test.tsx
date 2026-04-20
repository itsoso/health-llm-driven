import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import TimeRangeSelector from '../TimeRangeSelector';

describe('TimeRangeSelector', () => {
  const onChange = jest.fn();

  beforeEach(() => onChange.mockClear());

  it('renders all 5 range options', () => {
    const { getByTestId } = render(
      <TimeRangeSelector selected="1M" onChange={onChange} />,
    );
    expect(getByTestId('range-1W')).toBeTruthy();
    expect(getByTestId('range-1M')).toBeTruthy();
    expect(getByTestId('range-3M')).toBeTruthy();
    expect(getByTestId('range-6M')).toBeTruthy();
    expect(getByTestId('range-1Y')).toBeTruthy();
  });

  it('calls onChange when a range is pressed', () => {
    const { getByTestId } = render(
      <TimeRangeSelector selected="1M" onChange={onChange} />,
    );
    fireEvent.press(getByTestId('range-3M'));
    expect(onChange).toHaveBeenCalledWith('3M');
  });

  it('renders Chinese labels', () => {
    const { getByText } = render(
      <TimeRangeSelector selected="1M" onChange={onChange} />,
    );
    expect(getByText('1周')).toBeTruthy();
    expect(getByText('1月')).toBeTruthy();
    expect(getByText('1年')).toBeTruthy();
  });
});
