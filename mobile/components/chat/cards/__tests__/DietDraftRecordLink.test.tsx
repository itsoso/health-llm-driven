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


it('keeps saved meal actions together after the nutrition and estimate note', () => {
  const screen = render(<DietDraftCardView recorded source="photo" food_items="米饭" protein={10}
    adjust_record={{ record_id: 42, food_items: '米饭', meal_type: 'dinner' }} record_id={42} />);
  const tree = JSON.stringify(screen.toJSON());
  const note = tree.indexOf('营养为图片估算，如有偏差请继续修正。');
  const footer = tree.indexOf('diet-record-actions');
  expect(note).toBeGreaterThan(-1);
  expect(footer).toBeGreaterThan(note);
  const actions = screen.getByTestId('diet-record-actions');
  expect(actions.findAllByProps({ accessibilityRole: 'button' }).length).toBeGreaterThanOrEqual(2);
  fireEvent.press(screen.getByRole('button', { name: '继续修正本餐' }));
  expect(screen.getByTestId('diet-adjust-inline-editor')).toBeTruthy();
  fireEvent.press(screen.getByRole('button', { name: '收起本餐修正' }));
  expect(screen.queryByTestId('diet-adjust-inline-editor')).toBeNull();
});

it('renders an unavailable stored record as read-only instead of a confirmable draft', () => {
  const onConfirmAction = jest.fn();
  const view = render(<DietDraftCardView recorded={false} record_unavailable record_id={1175}
    food_items="旧餐食不应显示" calories={650} confirmActionState="done" onConfirmAction={onConfirmAction} />);
  expect(view.getByText('记录不可用，请到饮食页核对。')).toBeTruthy();
  expect(view.queryByText('旧餐食不应显示')).toBeNull();
  expect(view.queryByText(/确认记录/)).toBeNull();
  expect(view.queryByLabelText('继续修正本餐')).toBeNull();
});
