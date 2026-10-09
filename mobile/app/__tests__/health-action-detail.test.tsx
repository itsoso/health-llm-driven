import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { fetchHealthNavigationAction, recordHealthNavigationEvent } from '../../services/healthNavigation';
const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, back: jest.fn() }),
  useLocalSearchParams: () => ({ ref: 'opaque_ref_123' }),
  useFocusEffect: (callback: () => void) => { require('react').useEffect(callback, [callback]); },
  Stack: { Screen: () => null },
}));
jest.mock('../../services/healthNavigation', () => ({
  ...jest.requireActual('../../services/healthNavigation'),
  fetchHealthNavigationAction: jest.fn(), recordHealthNavigationEvent: jest.fn(),
}));
import Screen from '../health-action/[ref]';
const action = {
  action_ref: 'opaque_ref_123', action_revision: 'r1', title: '散步十分钟', completion_criterion: '完成散步',
  can_confirm: true, plan_date: '2026-10-09', safety_state: 'allowed', requires_health_review: false,
  scheduling_mode: 'flexible', execution_status: 'pending',
};
describe('opaque Health action confirmation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (fetchHealthNavigationAction as jest.Mock).mockResolvedValue(action);
    (recordHealthNavigationEvent as jest.Mock).mockResolvedValue({});
  });
  it('requires a second explicit confirmation and refreshes authority after saving', async () => {
    const screen = render(<Screen />);
    await waitFor(() => expect(screen.getByText('散步十分钟')).toBeTruthy());
    fireEvent.press(screen.getByText('记录完成'));
    expect(recordHealthNavigationEvent).not.toHaveBeenCalled();
    (fetchHealthNavigationAction as jest.Mock).mockResolvedValue({ ...action, execution_status: 'completed' });
    fireEvent.press(screen.getByText('确认记录'));
    await waitFor(() => expect(screen.getByText('已完成')).toBeTruthy());
    expect(recordHealthNavigationEvent).toHaveBeenCalledWith('opaque_ref_123', expect.objectContaining({ expected_revision: 'r1', event_type: 'completed' }));
    expect(fetchHealthNavigationAction).toHaveBeenCalledTimes(2);
  });
  it('retries an ambiguous write with the same operation id without reporting completion', async () => {
    (recordHealthNavigationEvent as jest.Mock).mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({});
    const screen = render(<Screen />);
    await waitFor(() => screen.getByText('记录完成'));
    fireEvent.press(screen.getByText('记录完成'));
    fireEvent.press(screen.getByText('确认记录'));
    await waitFor(() => screen.getByText('结果尚未确认。请使用相同操作重试，或重新查看状态。'));
    expect(screen.queryByText('已完成')).toBeNull();
    fireEvent.press(screen.getByText('确认记录'));
    await waitFor(() => expect(recordHealthNavigationEvent).toHaveBeenCalledTimes(2));
    expect((recordHealthNavigationEvent as jest.Mock).mock.calls[0][1]).toEqual((recordHealthNavigationEvent as jest.Mock).mock.calls[1][1]);
  });
  it('clears expired raw details and does not offer confirmation', async () => {
    (fetchHealthNavigationAction as jest.Mock).mockResolvedValue({ ...action, expires_at: '2000-01-01T00:00:00Z' });
    const screen = render(<Screen />);
    await waitFor(() => screen.getByText('行动详情已过期，请更新并重新核对。'));
    expect(screen.queryByText('散步十分钟')).toBeNull();
    expect(screen.queryByText('记录完成')).toBeNull();
  });
  it('does not show another account missing reference as a health detail', async () => {
    (fetchHealthNavigationAction as jest.Mock).mockRejectedValue({ response: { status: 404 } });
    const screen = render(<Screen />);
    await waitFor(() => screen.getByText('此行动引用已失效或不可访问。'));
    expect(screen.queryByText('散步十分钟')).toBeNull();
    expect(screen.queryByText('记录完成')).toBeNull();
  });
  it('allows本人 confirmation for a non-reorderable action when Health can_confirm permits it', async () => {
    (fetchHealthNavigationAction as jest.Mock).mockResolvedValue({ ...action, scheduling_mode: 'view_only' });
    const screen = render(<Screen />);
    await waitFor(() => screen.getByText('散步十分钟'));
    fireEvent.press(screen.getByText('记录完成'));
    fireEvent.press(screen.getByText('确认记录'));
    await waitFor(() => expect(recordHealthNavigationEvent).toHaveBeenCalledTimes(1));
  });
  it('does not allow confirmation when Health can_confirm denies it', async () => {
    (fetchHealthNavigationAction as jest.Mock).mockResolvedValue({ ...action, scheduling_mode: 'view_only', can_confirm: false });
    const screen = render(<Screen />);
    await waitFor(() => screen.getByText('散步十分钟'));
    expect(screen.queryByText('记录完成')).toBeNull();
  });
  it('does not offer confirmation for unknown safety', async () => {
    (fetchHealthNavigationAction as jest.Mock).mockResolvedValue({ ...action, safety_state: 'unknown' });
    const screen = render(<Screen />);
    await waitFor(() => expect(screen.getByText('散步十分钟')).toBeTruthy());
    expect(screen.queryByText('记录完成')).toBeNull();
  });
  it('refreshes stale revision and requires renewed user review', async () => {
    (recordHealthNavigationEvent as jest.Mock).mockRejectedValue({ response: { status: 409 } });
    const screen = render(<Screen />);
    await waitFor(() => screen.getByText('记录完成'));
    fireEvent.press(screen.getByText('记录完成'));
    fireEvent.press(screen.getByText('确认记录'));
    await waitFor(() => expect(screen.getByText('行动已发生变化，请重新核对最新内容。')).toBeTruthy());
    expect(screen.queryByText('确认记录')).toBeNull();
  });
});
