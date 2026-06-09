import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import SectionHeader from '../SectionHeader';

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: { labelPrimary: '#111', labelSecondary: '#555', labelTertiary: '#999', brand: '#0A8F8F' },
    isDark: false,
  }),
}));

describe('SectionHeader', () => {
  it('renders the title', () => {
    const { getByText } = render(<SectionHeader title="本周建议" />);
    expect(getByText('本周建议')).toBeTruthy();
  });

  it('renders an action and fires onAction', () => {
    const onAction = jest.fn();
    const { getByText } = render(<SectionHeader title="计划" action="查看全部" onAction={onAction} />);
    fireEvent.press(getByText('查看全部 >'));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('omits the action when not provided', () => {
    const { queryByText } = render(<SectionHeader title="计划" />);
    expect(queryByText(/查看/)).toBeNull();
  });
});
