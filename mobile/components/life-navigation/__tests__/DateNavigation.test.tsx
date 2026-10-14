import React from 'react';
import { Pressable, Text } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';
import DateNavigation from '../DateNavigation';

it('keeps manual input collapsed and rejects impossible dates before navigating', () => {
    const onDate = jest.fn();
    const view = render(<DateNavigation date="2026-10-14" onDate={onDate} />);
    expect(view.queryByLabelText('查看日期 YYYY-MM-DD')).toBeNull();
    fireEvent.press(view.getByLabelText('选择日期'));
    fireEvent.changeText(view.getByLabelText('查看日期 YYYY-MM-DD'), '2026-02-30');
    fireEvent.press(view.getByLabelText('查看该日期'));
    expect(view.getByText('请填写有效日期 YYYY-MM-DD。')).toBeTruthy();
    expect(onDate).not.toHaveBeenCalled();
    fireEvent.changeText(view.getByLabelText('查看日期 YYYY-MM-DD'), '2028-02-29');
    fireEvent.press(view.getByLabelText('查看该日期'));
    expect(onDate).toHaveBeenCalledWith('2028-02-29');
    expect(view.queryByLabelText('查看日期 YYYY-MM-DD')).toBeNull();
});
it('cancels a manual date and follows date changes from the calendar', () => {
    const onDate = jest.fn();
    const view = render(<DateNavigation date="2026-10-14" onDate={onDate} />);
    fireEvent.press(view.getByLabelText('选择日期'));
    fireEvent.changeText(view.getByLabelText('查看日期 YYYY-MM-DD'), '2030-01-01');
    fireEvent.press(view.getByLabelText('取消选择日期'));
    expect(onDate).not.toHaveBeenCalled();
    view.rerender(<DateNavigation date="2026-10-18" onDate={onDate} />);
    fireEvent.press(view.getByLabelText('选择日期'));
    expect(view.getByDisplayValue('2026-10-18')).toBeTruthy();
});
it('avoids duplicate day controls in weekly views and disables navigation when saving', () => {
    const onDate = jest.fn();
    const view = render(<DateNavigation date="2026-10-14" onDate={onDate} weekly />);
    expect(view.queryByLabelText('前一天')).toBeNull();
    expect(view.getByLabelText('选择日期')).toBeTruthy();
    view.rerender(<DateNavigation date="2026-10-14" onDate={onDate} disabled />);
    fireEvent.press(view.getByLabelText('前一天'));
    fireEvent.press(view.getByLabelText('后一天'));
    fireEvent.press(view.getByLabelText('选择日期'));
    expect(onDate).not.toHaveBeenCalled();
    expect(view.queryByLabelText('查看日期 YYYY-MM-DD')).toBeNull();
});

it('keeps the toolbar action independent from date navigation and exposes the draft status', () => {
    const onDate = jest.fn(), onSave = jest.fn();
    const view = render(<DateNavigation date="2026-10-14" onDate={onDate} status="有未保存草稿"
        trailing={<Pressable accessibilityRole="button" accessibilityLabel="保存个人安排" onPress={onSave}><Text>保存</Text></Pressable>} />);
    expect(view.getByLabelText('选择日期').props.accessibilityHint).toBe('有未保存草稿');
    fireEvent.press(view.getByLabelText('保存个人安排'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onDate).not.toHaveBeenCalled();
    expect(view.queryByLabelText('查看日期 YYYY-MM-DD')).toBeNull();
    fireEvent.press(view.getByLabelText('后一天'));
    expect(onDate).toHaveBeenCalledWith('2026-10-15');
    expect(onSave).toHaveBeenCalledTimes(1);
});

it('offers a direct return to today only away from today and outside weekly views', () => {
    const onDate = jest.fn();
    const view = render(<DateNavigation date="2026-10-12" today="2026-10-14" onDate={onDate} />);
    fireEvent.press(view.getByLabelText('回到今天'));
    expect(onDate).toHaveBeenCalledWith('2026-10-14');
    view.rerender(<DateNavigation date="2026-10-14" today="2026-10-14" onDate={onDate} />);
    expect(view.queryByLabelText('回到今天')).toBeNull();
    view.rerender(<DateNavigation date="2026-10-12" today="2026-10-14" onDate={onDate} weekly />);
    expect(view.queryByLabelText('回到今天')).toBeNull();
    onDate.mockClear();
    view.rerender(<DateNavigation date="2026-10-12" today="2026-10-14" onDate={onDate} disabled />);
    fireEvent.press(view.getByLabelText('回到今天'));
    expect(onDate).not.toHaveBeenCalled();
});
