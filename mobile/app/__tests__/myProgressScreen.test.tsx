import React from 'react';
import { RefreshControl, StyleSheet } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';
import { colors } from '../../constants/theme';
import MyProgressScreen from '../my-progress';

const mockPush = jest.fn();
const mockRefresh = jest.fn();
const mockProgressRetry = jest.fn();
const mockReviewRetry = jest.fn();
const mockUseProgress = jest.fn();
let mockCanRead = true;
let mockProgress: any;
let mockReview: any;
jest.mock('expo-router', () => ({ Stack: { Screen: () => null }, useRouter: () => ({ push: mockPush }), useLocalSearchParams: () => ({}) }));
jest.mock('../../components/home/HealthWeekNavigation', () => () => null);
jest.mock('../../hooks/useMyProgress', () => ({ useMyProgress: (days: number) => {
  mockUseProgress(days); return { progress: mockProgress, review: mockReview, canRead: mockCanRead, refresh: mockRefresh, refreshing: false };
} }));

beforeEach(() => {
  jest.clearAllMocks(); mockCanRead = true;
  mockProgress = { isLoading: false, isRefetching: false, error: null, refetch: mockProgressRetry, data: {
    window: { since: '2026-10-03', until: '2026-11-01', days: 30 },
    stats: { total_surfaced: 20, accepted: 0, declined: 0, pending: 20, completed: 0, graded: 2,
      improved: 0, unchanged: 0, worsened: 1, inconclusive: 0, safe_closed: 0,
      acceptance_rate: null, verification_rate: null, improvement_rate: 0 },
    verifying_cards: [], closed_cards: [{ id: 11, title: '观察睡眠变化', status: 'closed', user_decision: null,
      outcome: null, effect_size: null, accuracy_score: null, metric_key: 'sleep_score', baseline_value: '0', actual_value: '0.5555',
      evidence_level: null, created_at: null, completed_at: null, graded_at: '2026-11-01' }],
  } };
  mockReview = { isLoading: false, isRefetching: false, error: null, refetch: mockReviewRetry, data: {
    window_days: 30, start_date: '2026-10-03', end_date: '2026-11-01',
    execution: { total_events: 0, completed_events: 0, completion_rate: 0, by_status: {}, by_domain: {} },
    completed_action_keys: [], metrics: {
      weight: { status: 'present', count: 2, first: 65, current: 65.7, delta: 0.70000001 },
      hrv: { status: 'present', count: 2, first: 40, current: 52, delta: 12 },
    },
  } };
});
it('replaces zero-denominator scores with empty action copy and independent counts', () => {
  const v = render(<MyProgressScreen />);
  expect(v.getByText('本期还没有行动记录')).toBeTruthy();
  expect(v.getByText('身体变化')).toBeTruthy(); expect(v.getByText('建议进展')).toBeTruthy();
  for (const text of ['Daily Plan 复盘', '0%', '0/0', '2/0']) expect(v.queryByText(text)).toBeNull();
  expect(v.queryByText(/你做完并改善|AI 让你变好/)).toBeNull();
  expect(v.getAllByText('待分类').length).toBeGreaterThan(0);
});
it('keeps a genuine zero completion rate when actions exist', () => {
  mockReview.data.execution.total_events = 5;
  const v = render(<MyProgressScreen />);
  expect(v.getByText('0%')).toBeTruthy(); expect(v.getByText('已完成 0 项，共 5 项')).toBeTruthy();
});
it('shows neutral rounded changes and preserves zero-valued comparisons', () => {
  const v = render(<MyProgressScreen />);
  expect(StyleSheet.flatten(v.getByText('+0.7 kg').props.style).color).toBe(colors.labelPrimary);
  expect(v.getByText('+12 ms')).toBeTruthy(); expect(v.getByText('睡眠评分 0 → 0.56')).toBeTruthy();
  expect(v.getByText('指标变化仅供回顾，不代表由某条建议造成。')).toBeTruthy();
});
it('does not infer changes from one measurement or non-finite deltas', () => {
  mockReview.data.metrics = { weight: { status: 'present', count: 1, current: 65, delta: 0 }, hrv: { status: 'present', count: 2, current: 52, delta: Infinity } };
  const v = render(<MyProgressScreen />);
  expect(v.getByText('还没有足够的前后记录')).toBeTruthy(); expect(v.queryByText(/Infinity|NaN/)).toBeNull();
});
it('keeps suggestions usable when the review fails and provides a safe retry', () => {
  mockReview = { ...mockReview, data: undefined, error: new Error('private-owner-token'), isError: true };
  const v = render(<MyProgressScreen />);
  expect(v.getByText('建议进展')).toBeTruthy(); expect(v.queryByText(/private-owner-token/)).toBeNull();
  fireEvent.press(v.getByRole('button', { name: '重新加载本期回顾' })); expect(mockReviewRetry).toHaveBeenCalledTimes(1);
});
it('keeps observations usable when suggestions fail', () => {
  mockProgress = { ...mockProgress, data: undefined, error: new Error('private-error'), isError: true };
  const v = render(<MyProgressScreen />);
  expect(v.getByText('身体变化')).toBeTruthy();
  fireEvent.press(v.getByRole('button', { name: '重新加载建议进展' })); expect(mockProgressRetry).toHaveBeenCalledTimes(1);
});
it('switches period, refreshes both sections, and opens the selected suggestion', () => {
  const v = render(<MyProgressScreen />);
  fireEvent.press(v.getByRole('button', { name: '最近7天' }));
  expect(mockUseProgress).toHaveBeenLastCalledWith(7);
  expect(v.getByRole('button', { name: '最近7天' }).props.accessibilityState.selected).toBe(true);
  fireEvent.press(v.getByRole('button', { name: '查看建议详情：观察睡眠变化' }));
  expect(mockPush).toHaveBeenCalledWith({ pathname: '/card/[id]', params: { id: '11' } });
  v.UNSAFE_getByType(RefreshControl).props.onRefresh(); expect(mockRefresh).toHaveBeenCalledTimes(1);
});
it('hides health data when the readable session disappears', () => {
  const v = render(<MyProgressScreen />); mockCanRead = false; v.rerender(<MyProgressScreen />);
  expect(v.queryByText('观察睡眠变化')).toBeNull(); expect(v.queryByText('+0.7 kg')).toBeNull();
});

it('does not show a percentage for contradictory action counts', () => {
  mockReview.data.execution = { total_events: 2, completed_events: 3, completion_rate: 1.5 };
  const v = render(<MyProgressScreen />);
  expect(v.queryByText(/150%/)).toBeNull();
});
it('requires both observations before presenting a change', () => {
  mockReview.data.metrics = { weight: { status: 'present', count: 2, first: null, current: 65, delta: 0.5 } };
  const v = render(<MyProgressScreen />);
  expect(v.getByText('还没有足够的前后记录')).toBeTruthy();
  expect(v.queryByText('+0.5 kg')).toBeNull();
});
it('keeps detailed evidence behind an accessible disclosure and rounds observations', () => {
  mockReview.data.prediction_backtest = { status: 'ready', ready_candidate_count: 1, summary: { met: 1, not_met: 0, inconclusive: 0 }, boundary: '观察不能证明因果', results: [
    { prediction_id: 1, metric: 'weight', verdict: 'met', observed_delta: 0.123456 },
  ] };
  const v = render(<MyProgressScreen />);
  expect(v.queryByText('观察不能证明因果')).toBeNull();
  fireEvent.press(v.getByRole('button', { name: '展开复盘依据' }));
  expect(v.getByText('观察不能证明因果')).toBeTruthy();
  expect(v.getByText(/体重 · 支持 · \+0.12/)).toBeTruthy();
  fireEvent.press(v.getByRole('button', { name: '收起复盘依据' }));
  expect(v.queryByText('观察不能证明因果')).toBeNull();
});

it('keeps clinician review boundaries visible before expanding evidence', () => {
  mockReview.data.prediction_backtest = { status: 'ready', ready_candidate_count: 1, results: [
    { prediction_id: 'clinical', metric: 'weight', verdict: 'inconclusive', requires_clinician: true },
  ] };
  const v = render(<MyProgressScreen />);
  expect(v.getByText('部分结果需要专业人员复核，请勿据此自行调整治疗。')).toBeTruthy();
});
