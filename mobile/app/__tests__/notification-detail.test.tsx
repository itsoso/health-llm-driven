/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockReplace = jest.fn();
let mockCanGoBack = true;
const mockDismissTo = jest.fn();
const mockGetDetail = jest.fn();
let mockId: unknown = '81';
let mockUserId: number | null = 7;
jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, dismissTo: mockDismissTo, replace: mockReplace, canGoBack: () => mockCanGoBack }),
  useLocalSearchParams: () => ({ id: mockId }),
}));
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: mockUserId ? { id: mockUserId } : null, isAuthenticated: Boolean(mockUserId) }) }));
jest.mock('../../services/notifications', () => ({ getNotificationDetail: (...args: unknown[]) => mockGetDetail(...args) }));

import NotificationDetailScreen from '../notification-detail';
import { renderWithProviders } from '../../test-utils';

const detail = {
  id: 81, notification_type: 'ai_advice', title: '睡眠质量明显下滑',
  content: '这是保存的完整推送正文，包括列表没有显示的后半段。',
  created_at: '2026-10-18T12:59:00+08:00', sent_at: '2026-10-18T13:01:00+08:00',
  content_source: 'saved_full_text',
};

beforeEach(() => {
  jest.clearAllMocks(); mockId = '81'; mockUserId = 7; mockCanGoBack = true;
  mockGetDetail.mockResolvedValue(detail);
});

it('shows saved full text and historical evidence limits; analysis only prefills an owned selector', async () => {
  const screen = renderWithProviders(<NotificationDetailScreen />);
  expect(await screen.findByText(detail.content)).toBeTruthy();
  expect(screen.getByText('2026-10-18 13:01（UTC+08:00）')).toBeTruthy();
  expect(screen.getByText(/未经本次重新核验/)).toBeTruthy();
  expect(mockDismissTo).not.toHaveBeenCalled();
  fireEvent.press(screen.getByRole('button', { name: '让小气候解读这条推送' }));
  expect(mockDismissTo).toHaveBeenCalledWith({
    pathname: '/(tabs)/chat', params: {
      prompt: '请解读这条历史推送，说明其中指标的含义、结论的局限和需要核实的问题。',
      context: JSON.stringify({ from: 'notification/81' }), badge: '推送解读', newChat: '1', contextEntry: '1',
    },
  });
  expect(screen.queryClient.getQueryData(['notificationDetail', 7, 81])).toEqual(detail);
  fireEvent.press(screen.getByLabelText('返回'));
  expect(mockBack).toHaveBeenCalledTimes(1);
});

it('labels older saved notification text as potentially incomplete', async () => {
  mockGetDetail.mockResolvedValue({ ...detail, content_source: 'saved_notification_text' });
  const screen = renderWithProviders(<NotificationDetailScreen />);
  expect(await screen.findByText(/可能仅保留了摘要/)).toBeTruthy();
});

it('shows loading then a retryable failure without an analysis action', async () => {
  let reject!: (error: Error) => void;
  mockGetDetail.mockReturnValueOnce(new Promise((_, fail) => { reject = fail; }));
  const screen = renderWithProviders(<NotificationDetailScreen />);
  expect(screen.getByLabelText('正在读取推送')).toBeTruthy();
  expect(screen.queryByText('让小气候解读这条推送')).toBeNull();
  await act(async () => { reject(new Error('network')); });
  fireEvent.press(await screen.findByRole('button', { name: '重试' }));
  expect(await screen.findByText(detail.content)).toBeTruthy();
  expect(mockGetDetail).toHaveBeenCalledTimes(2);
});

it.each(['0', '-1', '1.5', '81junk', '2147483648', ['81', '82'], undefined])('rejects malformed ids %p without a request', async value => {
  mockId = value;
  const screen = renderWithProviders(<NotificationDetailScreen />);
  expect(screen.getByText('这条推送链接无效，请返回推送历史重新打开')).toBeTruthy();
  expect(mockGetDetail).not.toHaveBeenCalled();
});

it('does not fetch or display private data when logged out', () => {
  mockUserId = null;
  const screen = renderWithProviders(<NotificationDetailScreen />);
  expect(screen.getByText('请先登录后查看推送详情')).toBeTruthy();
  expect(mockGetDetail).not.toHaveBeenCalled();
});

it('hides cached content and late responses from another owner', async () => {
  let resolveOld!: (data: typeof detail) => void;
  mockGetDetail.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }));
  const screen = renderWithProviders(<NotificationDetailScreen />);
  mockUserId = 8;
  mockGetDetail.mockReturnValueOnce(new Promise(() => {}));
  screen.rerender(<NotificationDetailScreen />);
  await act(async () => { resolveOld(detail); });
  expect(screen.queryByText(detail.content)).toBeNull();
  expect(screen.queryByText('让小气候解读这条推送')).toBeNull();
});

it('does not show previous owner cached content on account switch', async () => {
  const screen = renderWithProviders(<NotificationDetailScreen />);
  await screen.findByText(detail.content);
  mockUserId = 8;
  mockGetDetail.mockReturnValueOnce(new Promise(() => {}));
  screen.rerender(<NotificationDetailScreen />);
  expect(screen.queryByText(detail.content)).toBeNull();
});

it('provides an exit from a direct notification link without previous history', async () => {
  mockCanGoBack = false;
  const screen = renderWithProviders(<NotificationDetailScreen />);
  await screen.findByText(detail.content);
  fireEvent.press(screen.getByLabelText('返回'));
  expect(mockReplace).toHaveBeenCalledWith('/(tabs)/chat');
  expect(mockBack).not.toHaveBeenCalled();
});

it.each([
  ['2026-10-18T05:01:00Z', '2026-10-18 05:01（UTC）'],
  ['2026-10-18T05:01:00+00:00', '2026-10-18 05:01（UTC+00:00）'],
  ['2026-10-18T13:01:00', '2026-10-18 13:01（时区未保存）'],
])('preserves timestamp zone information for %s', async (sent_at, expected) => {
  mockGetDetail.mockResolvedValue({ ...detail, sent_at });
  const screen = renderWithProviders(<NotificationDetailScreen />);
  expect(await screen.findByText(expected)).toBeTruthy();
});
