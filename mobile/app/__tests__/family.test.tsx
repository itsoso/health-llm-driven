import React from 'react';
import { fireEvent, render, screen, waitFor, act } from '@testing-library/react-native';
import { Alert, Modal } from 'react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import FamilyScreen from '../family';
import { fetchFamilyDashboard, fetchFamilyMemberHealth, leaveFamily } from '../../services/family';
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 7 } }) }));
jest.mock('../../services/api', () => ({ __esModule: true, default: {} }));
jest.mock('../../services/family', () => ({ ...jest.requireActual('../../services/family'), fetchFamilyDashboard: jest.fn(), fetchFamilyMemberHealth: jest.fn(), leaveFamily: jest.fn() }));
const member = { id: 12, user_id: 42, name: '测试成员', nickname: '小禾', relationship_type: 'daughter', can_view: true, can_edit: false, is_managed: false, latest_weight: null, today_steps: null, sleep_score: null, resting_hr: null, today_water_ml: 0, unread_alerts: 0 };
function show() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FamilyScreen /></QueryClientProvider>);
}
beforeEach(() => jest.clearAllMocks());
it('opens the daughter card as read-only records and exposes owner relationship settings', async () => {
  (fetchFamilyDashboard as jest.Mock).mockResolvedValue({ group_name: '测试家庭', is_owner: true, members: [member] });
  (fetchFamilyMemberHealth as jest.Mock).mockResolvedValue({ member, reports: [], episodes: [], limit: 20 });
  show();
  fireEvent.press(await screen.findByLabelText('查看小禾的健康记录'));
  expect(await screen.findByText('测试成员（小禾）')).toBeTruthy();
  expect(fetchFamilyMemberHealth).toHaveBeenCalledWith(42);
  const recordsModal = screen.UNSAFE_getAllByType(Modal).find(modal => modal.props.visible)!;
  expect(recordsModal.findByType(SafeAreaProvider).findByType(SafeAreaView).props.edges).toEqual(['top', 'bottom']);
  fireEvent.press(screen.getByLabelText('关闭健康记录'));
  fireEvent.press(screen.getByText('设置关系与昵称'));
  expect(screen.getByText('这位家人是我的')).toBeTruthy();
});
it('does not open health records without sharing permission', async () => {
  (fetchFamilyDashboard as jest.Mock).mockResolvedValue({ group_name: '测试家庭', is_owner: false, members: [{ ...member, can_view: false }] });
  show();
  fireEvent.press(await screen.findByLabelText('查看小禾的健康记录'));
  expect(screen.getByText('尚未向你共享健康记录')).toBeTruthy();
  await waitFor(() => expect(fetchFamilyMemberHealth).not.toHaveBeenCalled());
  expect(screen.queryByText('设置关系与昵称')).toBeNull();
});

it('lets an owner revoke sharing in a different household', async () => {
  (fetchFamilyDashboard as jest.Mock).mockResolvedValue({
    group_name: '自己的家庭', is_owner: true, members: [],
    memberships: [
      { member_id: 21, group_id: 1, group_name: '自己的家庭', is_owner: true },
      { member_id: 22, group_id: 2, group_name: '另一家庭', is_owner: false },
    ],
  });
  (leaveFamily as jest.Mock).mockResolvedValue(undefined);
  const alert = jest.spyOn(Alert, 'alert');
  show();
  fireEvent.press(await screen.findByLabelText('退出另一家庭并停止共享'));
  expect(alert).toHaveBeenCalled();
  const buttons = alert.mock.calls[0][2]!;
  await act(async () => { await buttons.find(button => button.text === '退出并停止共享')!.onPress!(); });
  await waitFor(() => expect(leaveFamily).toHaveBeenCalledWith(22));
  expect(screen.queryByLabelText('退出自己的家庭并停止共享')).toBeNull();
  alert.mockRestore();
});

it('measures the create-family modal independently of the screen safe area', async () => {
  (fetchFamilyDashboard as jest.Mock).mockResolvedValue({ group_name: null, members: [] });
  show();
  fireEvent.press(await screen.findByText('创建并邀请'));
  const createModal = screen.UNSAFE_getAllByType(Modal).find(modal => modal.props.visible)!;
  expect(createModal.findByType(SafeAreaProvider).findByType(SafeAreaView).props.edges).toEqual(['top', 'bottom']);
});
