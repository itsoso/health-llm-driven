import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import DailyJourneyScreen from '../daily-journey';
import { router } from 'expo-router';
const mockAuth = { user: { id: 1 }, token: 'synthetic-a' };
let mockGeneration = 1;
let mockNative = true;
let mockSnapshot: any = { status: 'idle', session: null, pendingCount: 0, offline: false, error: null };
const mockCapture = { initialize: jest.fn(), start: jest.fn(), pause: jest.fn(), resume: jest.fn(), end: jest.fn(), remove: jest.fn(), flush: jest.fn(), subscribe: jest.fn(() => () => {}), getSnapshot: () => mockSnapshot };
const mockAPI = { list: jest.fn(), review: jest.fn(), annotate: jest.fn() };
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => mockAuth }));
jest.mock('../../services/api', () => ({ getAuthSessionSnapshot: () => ({ generation: mockGeneration, token: mockAuth.token, initialized: true }) }));
jest.mock('../../config/releaseCapabilities', () => ({ hasDailyJourneyNativeCapability: () => mockNative }));
jest.mock('../../services/dailyJourneyCapture', () => ({ get dailyJourneyCapture() { return mockCapture; } }), { virtual: true });
jest.mock('../../services/dailyJourney', () => ({ get dailyJourneyAPI() { return mockAPI; } }), { virtual: true });
jest.mock('react-native-maps', () => { const MockView = require('react-native').View; return { __esModule: true, default: MockView, Polyline: MockView, Marker: MockView }; });
jest.mock('expo-router', () => ({ Stack: { Screen: () => null }, router: { back: jest.fn(), replace: jest.fn(), canGoBack: jest.fn(() => false) } }));
jest.mock('react-native-safe-area-context', () => ({ SafeAreaView: require('react-native').View }));

const session = { id: 's1', client_id: 'c1', status: 'ended', version: 2, segment: 1, started_at: '2026-10-18T01:00:00Z', deadline_at: '2026-10-18T16:00:00Z', ended_at: '2026-10-18T02:00:00Z', local_date: '2026-10-18', timezone: 'Asia/Shanghai', retention_days: 7, expires_at: '2026-10-25T02:00:00Z', point_count: 4 };
const review = { session, points: [{ id: 'p1', latitude: 31, longitude: 121 }, { id: 'p2', latitude: 31.01, longitude: 121.01 }, { id: 'p3', latitude: 31.02, longitude: 121.02 }, { id: 'p4', latitude: 31.03, longitude: 121.03 }], segments: [{ id: 'r1', point_ids: ['p1','p2'], mode: 'unknown', mode_source: 'estimated', distance_display: '1 千米' }, { id: 'r2', point_ids: ['p3','p4'], mode: 'walking', mode_source: 'estimated', distance_display: '1 千米' }], stops: [{ id: 't1', latitude: 31, longitude: 121, started_at: '2026-10-18T01:00:00Z', ended_at: '2026-10-18T01:05:00Z', duration_display: '5 分钟', label: null }], gaps: [{ started_at: '2026-10-18T01:10:00Z', ended_at: '2026-10-18T01:30:00Z', reason: 'signal_gap' }], summary: { distance_display: '2 千米', observed_display: '20 分钟', stop_count: 1, point_count: 4, note: '仅统计有效 GPS 观测，缺失区间未推断。' } };
beforeEach(() => {
  jest.clearAllMocks(); mockGeneration = 1; mockNative = true; mockAuth.user = { id: 1 }; mockAuth.token = 'synthetic-a';
  mockSnapshot = { status: 'idle', session: null, pendingCount: 0, offline: false, error: null };
  mockCapture.initialize.mockResolvedValue(undefined); mockCapture.start.mockResolvedValue(undefined); mockCapture.remove.mockResolvedValue(undefined);
  mockAPI.list.mockResolvedValue({ items: [] }); mockAPI.review.mockResolvedValue(review);
});

it('does not collect on open and requires explicit disclosure acceptance before starting', async () => {
  const view = render(<DailyJourneyScreen />);
  await waitFor(() => expect(mockAPI.list).toHaveBeenCalled());
  expect(mockCapture.start).not.toHaveBeenCalled();
  await waitFor(() => expect(view.getByLabelText('记录今天行程').props.accessibilityState.disabled).toBe(false));
  fireEvent.press(view.getByText('记录今天行程'));
  expect(mockCapture.start).not.toHaveBeenCalled();
  expect(view.getByText(/仅本人可见/)).toBeTruthy();
  fireEvent.press(view.getByText('同意并开始记录'));
  await waitFor(() => expect(mockCapture.start).toHaveBeenCalledWith({ retentionDays: 7, consent: true }));
});

it.each([[7, 1], [1, 7]] as const)('shows an unconfirmed %s-day request conflict and allows selecting the original term after %s-day retry', async (original, changed) => {
  mockSnapshot = { status: 'interrupted', session: null, pendingCount: 0, offline: true, error: null };
  const message = `上次保留 ${original} 天的开始请求尚未确认，请选择原来的 ${original} 天重试确认；确认后可在历史列表删除，再按新期限开启。`;
  const notify = () => (mockCapture.subscribe as jest.Mock).mock.calls[0][0]();
  mockCapture.start.mockImplementationOnce(async () => {
    mockSnapshot = { ...mockSnapshot, error: message }; notify(); throw new Error(message);
  }).mockImplementationOnce(async () => {
    mockSnapshot = { status: 'active', session: { ...session, status: 'active', retention_days: original }, pendingCount: 0, offline: false, error: null }; notify();
  });
  const view = render(<DailyJourneyScreen />);
  await waitFor(() => expect(view.getByLabelText('记录今天行程').props.accessibilityState.disabled).toBe(false));
  fireEvent.press(view.getByText('记录今天行程'));
  fireEvent.press(view.getByText(changed === 7 ? '7 天（默认）' : '1 天'));
  fireEvent.press(view.getByText('同意并开始记录'));
  expect(await view.findByText(message)).toBeTruthy();
  await waitFor(() => expect(view.getByLabelText('同意并开始记录').props.accessibilityState.disabled).toBe(false));
  fireEvent.press(view.getByText(original === 7 ? '7 天（默认）' : '1 天'));
  fireEvent.press(view.getByText('同意并开始记录'));
  await waitFor(() => expect(mockCapture.start).toHaveBeenNthCalledWith(2, { retentionDays: original, consent: true }));
  expect(await view.findByText('暂停记录')).toBeTruthy();
  expect(view.queryByText(message)).toBeNull();
});

it('keeps old native packages blocked while history remains readable', async () => {
  mockNative = false;
  const view = render(<DailyJourneyScreen />);
  await waitFor(() => expect(view.getByText(/安装支持后台定位的新版本/)).toBeTruthy());
  expect(view.queryByText('记录今天行程')).toBeNull();
  expect(mockCapture.start).not.toHaveBeenCalled();
});

it('renders separate route lines and a visible missing interval without connecting the gap', async () => {
  mockAPI.list.mockResolvedValue({ items: [session] });
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByText('查看复盘'));
  await waitFor(() => expect(view.getByTestId('journey-line-r1')).toBeTruthy());
  expect(view.getByTestId('journey-line-r1').props.coordinates).toHaveLength(2);
  expect(view.getByTestId('journey-line-r2').props.coordinates).toHaveLength(2);
  expect(view.getByText(/定位中断/)).toBeTruthy();
  expect(view.getByText('步行（估计）')).toBeTruthy();
});

it('discards a late review response after account switch', async () => {
  let resolve!: (value: any) => void;
  mockAPI.list.mockResolvedValue({ items: [session] });
  mockAPI.review.mockImplementation(() => new Promise(r => { resolve = r; }));
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByText('查看复盘'));
  await waitFor(() => expect(mockAPI.review).toHaveBeenCalled());
  mockGeneration += 1; mockAuth.user = { id: 2 }; mockAuth.token = 'synthetic-b';
  await act(async () => resolve(review));
  expect(view.queryByTestId('journey-line-r1')).toBeNull();
});

it('does not claim deletion succeeded when server deletion fails', async () => {
  const alert = jest.spyOn(Alert, 'alert');
  mockAPI.list.mockResolvedValue({ items: [session] });
  mockCapture.remove.mockRejectedValue(new Error('synthetic offline'));
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByLabelText('删除行程 s1'));
  const buttons = alert.mock.calls[0][2]!;
  await act(async () => { await buttons.find(b => b.style === 'destructive')!.onPress!(); });
  expect(await view.findByText(/删除未完成/)).toBeTruthy();
  expect(view.getByText('查看复盘')).toBeTruthy(); alert.mockRestore();
});

it('shows local pause with unsynced state and offers a retry', async () => {
  mockSnapshot = { status: 'paused', session: { ...session, status: 'active' }, pendingCount: 3, offline: true, error: '暂停状态尚未同步' };
  const view = render(<DailyJourneyScreen />);
  expect(await view.findByText('本机已暂停')).toBeTruthy();
  expect(view.getByText(/存在尚未同步的变更/)).toBeTruthy();
  fireEvent.press(view.getByText('重试同步'));
  await waitFor(() => expect(mockCapture.flush).toHaveBeenCalled());
});

it('returns to the main chat without a navigation stack', async () => {
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(view.getByLabelText('返回上一页'));
  expect(router.replace).toHaveBeenCalledWith('/(tabs)/chat');
  await waitFor(() => expect(mockAPI.list).toHaveBeenCalled());
});


it('synchronously locks repeated start taps while permission and server work is pending', async () => {
  let resolve!: () => void;
  mockCapture.start.mockImplementation(() => new Promise<void>(r => { resolve = r; }));
  const view = render(<DailyJourneyScreen />);
  await waitFor(() => expect(mockAPI.list).toHaveBeenCalled());
  await waitFor(() => expect(view.getByLabelText('记录今天行程').props.accessibilityState.disabled).toBe(false));
  fireEvent.press(view.getByText('记录今天行程'));
  fireEvent.press(view.getByText('同意并开始记录'));
  fireEvent.press(view.getByText('同意并开始记录'));
  expect(mockCapture.start).toHaveBeenCalledTimes(1);
  await act(async () => resolve());
});

it('saves a bounded manual correction using the selected session version and reads it back', async () => {
  mockAPI.list.mockResolvedValue({ items: [session] });
  mockAPI.annotate.mockResolvedValue({ ...session, version: 3 });
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByText('查看复盘'));
  fireEvent.press(await view.findByText('为停留地点命名'));
  const input = view.getByLabelText('地点或路线名称');
  expect(input.props.maxLength).toBe(80);
  fireEvent.changeText(input, '我确认的地点');
  fireEvent.press(view.getByText('保存更正'));
  await waitFor(() => expect(mockAPI.annotate).toHaveBeenCalledWith('s1', {
    expected_version: 2, annotations: [{ target_id: 't1', label: '我确认的地点' }],
  }, 'synthetic-a'));
  await waitFor(() => expect(mockAPI.review).toHaveBeenCalledTimes(2));
});

it('does not read back a correction under the next login session', async () => {
  let resolve!: (value: any) => void;
  mockAPI.list.mockResolvedValue({ items: [session] });
  mockAPI.annotate.mockImplementation(() => new Promise(r => { resolve = r; }));
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByText('查看复盘'));
  fireEvent.press(await view.findByText('为停留地点命名'));
  fireEvent.changeText(view.getByLabelText('地点或路线名称'), '地点');
  fireEvent.press(view.getByText('保存更正'));
  await waitFor(() => expect(mockAPI.annotate).toHaveBeenCalled());
  mockGeneration += 1; mockAuth.token = 'synthetic-b';
  await act(async () => resolve({ ...session, version: 3 }));
  expect(mockAPI.review).toHaveBeenCalledTimes(1);
});

it('does not bridge a segment when one referenced point is missing', async () => {
  mockAPI.list.mockResolvedValue({ items: [session] });
  mockAPI.review.mockResolvedValue({ ...review, segments: [{ ...review.segments[0], point_ids: ['p1', 'missing', 'p2'] }] });
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByText('查看复盘'));
  await view.findByText('这段路的复盘');
  expect(view.queryByTestId('journey-line-r1')).toBeNull();
});

it('does not claim current-session deletion when the service has only persisted a pending deletion', async () => {
  const alert = jest.spyOn(Alert, 'alert');
  mockAPI.list.mockResolvedValue({ items: [session] });
  mockCapture.remove.mockImplementation(async () => { mockSnapshot = { status: 'ended', session, pendingCount: 0, offline: true, error: '删除尚未同步' }; });
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByLabelText('删除行程 s1'));
  await act(async () => { await alert.mock.calls[0][2]!.find(b => b.style === 'destructive')!.onPress!(); });
  expect(await view.findByText(/删除未完成/)).toBeTruthy();
  expect(view.getByText('查看复盘')).toBeTruthy();
  alert.mockRestore();
});


it('offers explicit continuation for an interrupted saved session', async () => {
  mockSnapshot = { status: 'interrupted', session: { ...session, status: 'paused' }, pendingCount: 0, offline: false, error: '系统定位已停止' };
  const view = render(<DailyJourneyScreen />);
  fireEvent.press(await view.findByText('继续记录'));
  await waitFor(() => expect(mockCapture.resume).toHaveBeenCalledTimes(1));
});

it('can retry explicit start after interruption before a session was created', async () => {
  mockSnapshot = { status: 'interrupted', session: null, pendingCount: 0, offline: false, error: '开启未完成' };
  const view = render(<DailyJourneyScreen />);
  await waitFor(() => expect(view.getByLabelText('记录今天行程').props.accessibilityState.disabled).toBe(false));
  fireEvent.press(view.getByText('记录今天行程'));
  expect(view.getByText('同意并开始记录')).toBeTruthy();
});

it('shows the concrete interruption reason and unsynced count', async () => {
  mockSnapshot = { status: 'interrupted', session, pendingCount: 12, offline: true, error: '请允许始终定位后再开启当天行程' };
  const view = render(<DailyJourneyScreen />);
  expect(await view.findByText('请允许始终定位后再开启当天行程')).toBeTruthy();
  expect(view.getByText('本机待同步：12 个定位点')).toBeTruthy();
});
