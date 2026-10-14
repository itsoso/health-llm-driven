import React from 'react';
import { Text } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';
import TodayTaskList from '../TodayTaskList';
import { blankTask } from '../../../utils/lifeNavigationModel';
import type { LifeTask } from '../../../types/lifeNavigation';

const task = (title: string, status: LifeTask['status'], minutes: number | null, role: LifeTask['role'] = 'other') => ({ ...blankTask('2026-10-14', role), title, status, estimated_minutes: minutes });
const renderTask = (item: LifeTask) => <Text key={item.id}>{item.title}</Text>;
it('shows ongoing work first without changing stored order and keeps unknown estimates explicit', () => {
    const items = [task('普通任务', 'planned', null), task('结束任务', 'done', 50), task('主任务', 'planned', 30, 'main'), task('正在执行', 'doing', 20), task('跳过任务', 'skipped', 99)];
    const original = items.map(item => item.id);
    const view = render(<TodayTaskList tasks={items} expandedTaskId={null} onCollapseTask={jest.fn()} renderTask={renderTask} />);
    expect(view.getByText('待办 3 · 已估 50 分 · 1 项未估时')).toBeTruthy();
    const content = view.getAllByText(/^(普通任务|主任务|正在执行)$/).map(node => node.props.children);
    expect(content).toEqual(['正在执行', '主任务', '普通任务']);
    expect(view.queryByText('结束任务')).toBeNull();
    expect(view.queryByText('跳过任务')).toBeNull();
    expect(view.getByText('已完成 1 · 已跳过 1')).toBeTruthy();
    expect(items.map(item => item.id)).toEqual(original);
    fireEvent.press(view.getByLabelText('展开已结束任务'));
    expect(view.getByText('结束任务')).toBeTruthy();
    expect(view.getByText('跳过任务')).toBeTruthy();
});
it('distinguishes unestimated work from zero minutes and does not treat skipped work as completed', () => {
    const view = render(<TodayTaskList tasks={[task('未估时任务', 'planned', null)]} expandedTaskId={null} onCollapseTask={jest.fn()} renderTask={renderTask} />);
    expect(view.getByText('待办 1 · 1 项未估时')).toBeTruthy();
    view.rerender(<TodayTaskList tasks={[task('零分钟任务', 'planned', 0)]} expandedTaskId={null} onCollapseTask={jest.fn()} renderTask={renderTask} />);
    expect(view.getByText('待办 1 · 预计 0 分')).toBeTruthy();
    view.rerender(<TodayTaskList tasks={[task('跳过任务', 'skipped', null)]} expandedTaskId={null} onCollapseTask={jest.fn()} renderTask={renderTask} />);
    expect(view.getByText('当日暂无待办')).toBeTruthy();
    expect(view.getByText('已完成 0 · 已跳过 1')).toBeTruthy();
});
it('reveals a completed task opened from another view and closes its editor with the group', () => {
    const item = task('完成任务', 'done', 30), collapse = jest.fn();
    const view = render(<TodayTaskList tasks={[item]} expandedTaskId={item.id} onCollapseTask={collapse} renderTask={renderTask} />);
    expect(view.getByText('完成任务')).toBeTruthy();
    fireEvent.press(view.getByLabelText('收起已结束任务'));
    expect(collapse).toHaveBeenCalledTimes(1);
    view.rerender(<TodayTaskList tasks={[item]} expandedTaskId={null} onCollapseTask={collapse} renderTask={renderTask} />);
    expect(view.queryByText('完成任务')).toBeNull();
});

it('searches the current day across pending and folded finished records without changing the daily totals', () => {
    const items = [task('AI 项目', 'planned', 30), {...task('晨读归档', 'done', 20), result:'AI 产品动态'}, task('产品周会', 'planned', null)];
    const props = {tasks:items,expandedTaskId:null,onCollapseTask:jest.fn(),renderTask};
    const view = render(<TodayTaskList {...props} />);
    expect(view.queryByLabelText('搜索当日任务')).toBeNull();
    view.rerender(<TodayTaskList {...props} searchOpen />);
    fireEvent.changeText(view.getByLabelText('搜索当日任务'), ' ai ');
    expect(view.getByText('匹配 2 / 当日 3')).toBeTruthy();
    expect(view.getByText('AI 项目')).toBeTruthy();
    expect(view.getByText('晨读归档')).toBeTruthy();
    expect(view.queryByText('产品周会')).toBeNull();
    expect(view.getByText('待办 2 · 已估 30 分 · 1 项未估时')).toBeTruthy();
    view.rerender(<TodayTaskList {...props} searchOpen={false} />);
    expect(view.getByText('产品周会')).toBeTruthy();
    expect(view.queryByText('晨读归档')).toBeNull();
    view.rerender(<TodayTaskList {...props} searchOpen />);
    expect(view.getByLabelText('搜索当日任务').props.value).toBe('');
});
it('shows an honest no-match state and clears search without losing the completion display preference', () => {
    const items = [task('进行任务', 'planned', 10), task('完成记录', 'done', 15)];
    const props = {tasks:items,expandedTaskId:null,onCollapseTask:jest.fn(),renderTask};
    const view = render(<TodayTaskList {...props} searchOpen />);
    fireEvent.press(view.getByLabelText('展开已结束任务'));
    fireEvent.changeText(view.getByLabelText('搜索当日任务'), '[no match]');
    expect(view.getByText('当日没有匹配任务')).toBeTruthy();
    expect(view.getByText('匹配 0 / 当日 2')).toBeTruthy();
    expect(view.queryByText('进行任务')).toBeNull();
    fireEvent.press(view.getByLabelText('清空任务搜索'));
    expect(view.getByText('进行任务')).toBeTruthy();
    expect(view.getByText('完成记录')).toBeTruthy();
});
it('keeps the task being edited visible if its edited text stops matching the query', () => {
    const item = task('AI 任务', 'planned', 10), props = {expandedTaskId:item.id,onCollapseTask:jest.fn(),renderTask,searchOpen:true};
    const view = render(<TodayTaskList {...props} tasks={[item]} />);
    fireEvent.changeText(view.getByLabelText('搜索当日任务'), 'AI');
    view.rerender(<TodayTaskList {...props} tasks={[{...item,title:'新的标题'}]} />);
    expect(view.getByText('新的标题')).toBeTruthy();
    expect(view.getByText('匹配 0 / 当日 1')).toBeTruthy();
    expect(view.getByText('保留正在编辑的任务')).toBeTruthy();
    view.rerender(<TodayTaskList {...props} expandedTaskId={null} tasks={[{...item,title:'新的标题'}]} />);
    expect(view.getByText('当日没有匹配任务')).toBeTruthy();
});
