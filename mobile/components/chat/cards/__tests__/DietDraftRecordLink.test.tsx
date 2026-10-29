import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';
import { DietDraftCardView } from '../DietDraftCard';
import { revaColors as C } from '../../../../constants/revaTheme';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(() => mockPush.mockClear());

it.each(['text', 'chat_photo'])('uses the saved meal view and preserves personal cautions for %s', (source) => {
  const screen = render(<DietDraftCardView recorded source={source} meal_type="dinner"
    food_items="合成餐食" calories={50} protein={1.2}
    personal_cautions={['合成提醒一', '合成提醒二']}
    next_action="合成下一餐建议" record_id={42}
    adjust_record={{ record_id: 42, food_items: '合成餐食', meal_type: 'dinner' }} />);
  expect(screen.getByText('晚餐已记录')).toBeTruthy();
  expect(screen.getByText('合成提醒一')).toBeTruthy();
  expect(screen.getByText('合成提醒二')).toBeTruthy();
  expect(screen.getByText('合成下一餐建议')).toBeTruthy();
  expect(screen.getByText('1.2g')).toBeTruthy();
  expect(screen.getByRole('button', { name: '查看饮食记录' })).toBeTruthy();
  expect(screen.getByRole('button', { name: '继续修正本餐' })).toBeTruthy();
  expect(screen.queryByText('可截图分享')).toBeNull();
  expect(screen.queryByText('修正饮食草稿')).toBeNull();
});

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

it('uses a compact branded nutrition strip and human-readable record source', () => {
  const screen = render(<DietDraftCardView recorded source="agent_text" food_items="米饭"
    protein={10} carbs={32} fat={3} fiber={1.5} />);
  expect(screen.getByText('记录方式：对话文字')).toBeTruthy();
  expect(screen.queryByText('来源: agent_text')).toBeNull();
  expect(StyleSheet.flatten(screen.getByTestId('diet-record-nutrition-strip').props.style)).toEqual(
    expect.objectContaining({ backgroundColor: C.paper2, flexWrap: 'nowrap' }),
  );
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
