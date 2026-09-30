import React from 'react';
import { fireEvent, render, screen, waitFor, act } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ getGroups: vi.fn(), getDashboard: vi.fn(), getMembers: vi.fn(), getProxyStatus: vi.fn(), removeMember: vi.fn(), switchToMember: vi.fn(), switchBack: vi.fn(), getMemberHealth: vi.fn() }));
vi.mock('@/services/api/family', () => ({ familyApi: api }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
import FamilyPage from './page';
const member = { id: 12, user_id: 42, name: '测试成员', nickname: '小禾', relationship_type: 'daughter', can_view: true, can_edit: false, is_managed: false, today_water_ml: 0, unread_alerts: 0 };
beforeEach(() => {
  vi.clearAllMocks();
  api.getGroups.mockResolvedValue({ data: { groups: [{ name: '测试家庭' }] } });
  api.getMembers.mockResolvedValue({ data: { members: [member] } });
  api.getProxyStatus.mockResolvedValue({ data: { is_proxy_mode: false } });
  api.getDashboard.mockResolvedValue({ data: { group_name: '测试家庭', is_owner: true, members: [member], memberships: [{ member_id: 21, group_id: 1, group_name: '测试家庭', is_owner: true }, { member_id: 22, group_id: 2, group_name: '另一家庭', is_owner: false }] } });
});
it('opens readonly records without proxy switch', async () => {
  api.getMemberHealth.mockResolvedValue({ data: { member, reports: [], episodes: [], limit: 20 } });
  render(<FamilyPage />);
  fireEvent.click(await screen.findByRole('button', { name: '查看小禾的检查报告与病程' }));
  expect(await screen.findByText('测试成员（小禾）')).toBeInTheDocument();
  expect(api.switchToMember).not.toHaveBeenCalled();
  expect(screen.queryByText('切换视角')).not.toBeInTheDocument();
});
it('lets an owner leave a different household', async () => {
  vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
  api.removeMember.mockResolvedValue({});
  render(<FamilyPage />);
  fireEvent.click(await screen.findByRole('button', { name: '退出另一家庭并停止共享' }));
  await waitFor(() => expect(api.removeMember).toHaveBeenCalledWith(22));
  expect(screen.queryByRole('button', { name: '退出测试家庭并停止共享' })).not.toBeInTheDocument();
});

it('keeps switch-back available when dashboard denies a managed proxy session', async () => {
  let resolveProxy!: (value: unknown) => void;
  api.getDashboard.mockRejectedValue({ response: { status: 403 } });
  api.getProxyStatus.mockReturnValue(new Promise(resolve => { resolveProxy = resolve; }));
  api.switchBack.mockReturnValue(new Promise(() => {}));
  render(<FamilyPage />);
  expect(await screen.findByRole('alert')).toHaveTextContent('家庭信息加载失败');
  await act(async () => { resolveProxy({ data: { is_proxy_mode: true, acting_as_name: '代管成员' } }); });
  fireEvent.click(await screen.findByRole('button', { name: '切回自己' }));
  await waitFor(() => expect(api.switchBack).toHaveBeenCalledOnce());
});
