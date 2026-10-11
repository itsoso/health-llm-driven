import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { DietDraftCardView } from '../DietDraftCard';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(() => mockPush.mockClear());

it('opens the existing diet modal on the saved meal date', () => {
  const screen = render(<DietDraftCardView recorded record_date="2026-10-10" food_items="米饭" />);
  fireEvent.press(screen.getByRole('button', { name: '查看饮食记录' }));
  expect(mockPush).toHaveBeenCalledWith({ pathname: '/diet', params: { date: '2026-10-10' } });
});

it('offers the record link after manual confirmation completes', () => {
  const screen = render(<DietDraftCardView confirmActionState="done" food_items="米饭" />);
  fireEvent.press(screen.getByRole('button', { name: '查看饮食记录' }));
  expect(mockPush).toHaveBeenCalledWith('/diet');
});

it.each(['2026-02-30', '2026-13-01', '/diet?capture=photo', undefined])(
  'opens the ordinary record page without invalid date parameters: %s', (recordDate) => {
    const screen = render(<DietDraftCardView recorded record_date={recordDate} />);
    fireEvent.press(screen.getByRole('button', { name: '查看饮食记录' }));
    expect(mockPush).toHaveBeenCalledWith('/diet');
  },
);

it('does not show a saved-record link on an unconfirmed draft', () => {
  const screen = render(<DietDraftCardView record_date="2026-10-10" />);
  expect(screen.queryByRole('button', { name: '查看饮食记录' })).toBeNull();
  expect(mockPush).not.toHaveBeenCalled();
});
