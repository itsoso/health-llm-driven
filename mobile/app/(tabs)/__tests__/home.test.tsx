/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockPush = jest.fn();
const mockInvalidateQueries = jest.fn();
let mockDailyPlanActions: unknown[] = [];
let mockTwinData: Record<string, unknown> = {};
let mockSafetyAlerts: any[] = [];
let mockActiveCycle: any = null;
let mockRefetchingKeys = new Set<string>();
// 时间线 now-item:Hero 现在读 /timeline/today 的 now(时间感知最相关项),不再读清晨第一项。
let mockTimeline: any = null;

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Reva fonts load async via expo-font; in tests force "loaded" so the screen
// renders deterministically (otherwise the first render hits the font gate).
jest.mock('../../../components/reva/useRevaFonts', () => ({
  useRevaFonts: () => true,
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    const isRefetching = mockRefetchingKeys.has(key);
    if (key.includes('safety')) {
      return { data: { alerts: mockSafetyAlerts }, isLoading: false, isRefetching };
    }
    if (key.includes('twin')) {
      return { data: mockTwinData, isLoading: false, isRefetching };
    }
    if (key.includes('daily-plan')) {
      return { data: { actions: mockDailyPlanActions }, isLoading: false, isRefetching };
    }
    if (key.includes('timeline')) {
      return { data: mockTimeline, isLoading: false, isError: false, isRefetching };
    }
    if (key.includes('intervention-cycle')) {
      return { data: mockActiveCycle, isLoading: false, isRefetching };
    }
    return { data: null, isLoading: false, isRefetching: false };
  },
  useMutation: () => ({ mutate: jest.fn(), isPending: false }),
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
  }),
}));

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#fff',
      fill: '#f5f5f5',
      labelPrimary: '#111',
      labelSecondary: '#555',
      labelTertiary: '#999',
      labelQuaternary: '#bbb',
      separator: '#eee',
      brand: '#0A8F8F',
      brandLight: '#E6F7F7',
      purple: '#7C3AED',
      pink: '#EC4899',
      blue: '#2563EB',
      teal: '#0F766E',
      orange: '#EA580C',
      green: '#16A34A',
      red: '#DC2626',
      amber: '#D97706',
      tintBlue: '#DBEAFE',
      tintGreen: '#DCFCE7',
      tintPurple: '#EDE9FE',
      tintPink: '#FCE7F3',
      tintOrange: '#FFEDD5',
      tintTeal: '#CCFBF1',
      tintRed: '#FEE2E2',
      tintAmber: '#FEF3C7',
    },
    isDark: false,
  }),
}));

jest.mock('../../../services/safety', () => ({
  getSafetyReport: jest.fn(),
}));

jest.mock('../../../services/dailyPlan', () => ({
  getDailyOperatingPlan: jest.fn(),
}));

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

// Reva self-fetching strips read their own hooks (timeline / weather). Under the
// generic react-query mock they degrade to null/empty — that's fine for the home
// feed structure assertions. We only assert on the cards that take props from index.

import TodayScreen from '../index';

describe('TodayScreen (Reva 今日 timeline-first layout)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDailyPlanActions = [];
    mockTwinData = {};
    mockSafetyAlerts = [];
    mockActiveCycle = null;
    mockRefetchingKeys = new Set<string>();
    mockTimeline = null;
  });

  // 构造一个最小的 /timeline/today 响应:now 指向给定 item。
  function makeTimeline(item: any) {
    return {
      date: '2026-06-23',
      current_window: 'noon',
      now: item.id,
      items: [item],
      past: { completed_count: 0, events: [] },
      counts: { actionable: 1, overdue: 0, info: 0 },
    };
  }

  // ── #1 Hero readiness uses the real Garmin Training Readiness, not body_battery ──

  it('uses Garmin training_readiness_score for the Hero readiness ring', () => {
    // readiness 93 is the truth; body_battery 36 must NOT be used as the readiness.
    mockTwinData = {
      physiological: { training_readiness_score: 93, body_battery_current: 36, sleep_score_latest: 70 },
    };
    const { getByText } = render(<TodayScreen />);
    // ReadinessRing renders the score as text inside the Hero (93, not 36).
    expect(getByText('93')).toBeTruthy();
    // 93 ≥ 80 → RevaHeroCard readinessTitle '可上强度'. If body_battery 36 had been
    // used, the title would have been '注意恢复' (< 60).
    expect(getByText('可上强度')).toBeTruthy();
  });

  it('shows the Hero "待同步" placeholder when training readiness is missing', () => {
    // No training_readiness_score → null → placeholder, never falling back to body_battery.
    mockTwinData = {
      physiological: { body_battery_current: 42, sleep_score_latest: 80 },
    };
    const { getAllByText } = render(<TodayScreen />);
    // Hero shows the 待同步 placeholder (ring placeholder + readinessTitle).
    expect(getAllByText('待同步').length).toBeGreaterThanOrEqual(1);
  });

  // ── Hero 时间感知 now-action (driven by /timeline/today now,不再是清晨第一项) ──

  it('renders the timeline now-item title / why / time in the Hero', () => {
    mockTimeline = makeTimeline({
      id: 'med-7',
      kind: 'action',
      time_window: 'noon',
      scheduled_for: '12:30',
      title: '服用二甲双胍',
      subtitle: '随午餐服用,减少肠胃反应',
      icon: 'medical-outline',
      color: '#1F8A5B',
      status: 'pending',
      priority: 1,
      can_complete: true,
      complete_ref: { object_type: 'health_protocol', object_id: 7 },
      deep_link: null,
      severity: null,
      proof: null,
    });
    const { getByText, getAllByText } = render(<TodayScreen />);
    // 同一 now-item 既高亮在 Hero,也仍留在下方时间线 strip(同一 query 喂两处)→ 标题出现两次。
    expect(getAllByText('服用二甲双胍').length).toBeGreaterThanOrEqual(1);
    expect(getAllByText('随午餐服用').length).toBeGreaterThanOrEqual(1); // shortSubtitle 取首分句
    // 时点 + lever 是 Hero 独有。
    expect(getByText('12:30')).toBeTruthy();
    expect(getByText('现在该做 · 中午')).toBeTruthy();
  });

  it('shows a risk lever when a critical alert exists', () => {
    mockSafetyAlerts = [{ severity: 'high', title: '夜间血氧持续偏低' }];
    mockTimeline = makeTimeline({
      id: 'act-1',
      kind: 'action',
      time_window: 'morning',
      scheduled_for: null,
      title: '复测夜间血氧',
      subtitle: null,
      icon: 'pulse-outline',
      color: '#D5503A',
      status: 'pending',
      priority: 1,
      can_complete: false,
      complete_ref: null,
      deep_link: null,
      severity: 'high',
      proof: null,
    });
    const { getByText } = render(<TodayScreen />);
    expect(getByText('现在该做 · 风险')).toBeTruthy();
  });

  it('renders the graceful empty state and routes to record when there is no now-item', () => {
    // 无 timeline now → Hero 空态「今天的事都安排好了」+「补齐今天记录」入口。
    const { getByText, getByLabelText } = render(<TodayScreen />);
    expect(getByText('今天的事都安排好了')).toBeTruthy();
    fireEvent.press(getByLabelText('补齐今天记录'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/record');
  });

  it('routes the Hero now-action to its deep link when present', () => {
    mockTimeline = makeTimeline({
      id: 'act-9',
      kind: 'action',
      time_window: 'noon',
      scheduled_for: '12:00',
      title: '提高早餐蛋白',
      subtitle: '目标 30g',
      icon: 'restaurant-outline',
      color: '#1F8A5B',
      status: 'pending',
      priority: 1,
      can_complete: false,
      complete_ref: null,
      deep_link: '/diet-plan',
      severity: null,
      proof: null,
    });
    const { getByLabelText } = render(<TodayScreen />);
    fireEvent.press(getByLabelText('现在该做:提高早餐蛋白'));
    expect(mockPush).toHaveBeenCalledWith('/diet-plan');
  });

  // ── 90-day metabolic cycle strip ──

  it('promotes an active 90-day health cycle as the home cockpit', () => {
    const today = Date.now();
    const start = new Date(today - 14 * 86400000).toISOString();
    const end = new Date(today + 76 * 86400000).toISOString();
    mockActiveCycle = {
      id: 7,
      status: 'active',
      start_date: start,
      planned_end_date: end,
      outcomes: [
        {
          metric_code: 'LDL',
          display: 'LDL-C',
          unit: 'mmol/L',
          baseline_value: 3.8,
          target_value: 2.6,
          latest_value: null,
          status: 'pending',
        },
      ],
    };

    const { getByTestId, getByText, getByLabelText } = render(<TodayScreen />);

    expect(getByTestId('home-health-cycle-cockpit')).toBeTruthy();
    expect(getByText('90 天代谢周期')).toBeTruthy();
    expect(getByText('第 15 / 90 天')).toBeTruthy();
    expect(getByText('LDL-C')).toBeTruthy();

    fireEvent.press(getByLabelText('查看 90 天健康周期'));
    expect(mockPush).toHaveBeenCalledWith('/intervention-cycle');
  });

  it('keeps the pull-to-refresh spinner separate from background sync', () => {
    mockRefetchingKeys = new Set(['twin:me']);
    const { UNSAFE_getByType } = render(<TodayScreen />);
    const { RefreshControl } = require('react-native');
    const refreshControl = UNSAFE_getByType(RefreshControl);
    expect(refreshControl.props.refreshing).toBe(false);
  });

  // ── 身体数据 (ActivityRing + Vitals + BodyStats) ──

  it('renders the basic vitals grid with pending placeholders when data is missing', () => {
    const { getByText, getByLabelText } = render(<TodayScreen />);
    expect(getByText('血压')).toBeTruthy();
    expect(getByText('SpO2')).toBeTruthy();
    expect(getByText('BMI')).toBeTruthy();
    expect(getByText('体脂')).toBeTruthy();
    expect(getByLabelText('血压 待记录')).toBeTruthy();
  });

  it('fills the vitals grid from the twin snapshot when values exist', () => {
    mockTwinData = {
      physiological: { spo2_avg: 96 },
      body_composition: { bmi: 22.4 },
      labs: { blood_pressure_systolic: 120, blood_pressure_diastolic: 78 },
    };
    const { getByLabelText } = render(<TodayScreen />);
    expect(getByLabelText('血压 120/78mmHg')).toBeTruthy();
    expect(getByLabelText('BMI 22.4')).toBeTruthy();
  });

  it('opens a vitals tile route on press', () => {
    const { getByLabelText } = render(<TodayScreen />);
    fireEvent.press(getByLabelText('BMI 待记录'));
    expect(mockPush).toHaveBeenCalledWith('/body-measurements?focus=morning');
  });

  // ── #4 deep-analysis cards moved off the home feed ──

  it('does not surface deep-analysis cards on the home feed (moved to 我 tab)', () => {
    // Even with rich data that would have populated the old 进展/工具 groups,
    // the home feed must not render the analysis cards or the agent command card.
    mockTwinData = {
      physiological: { sleep_score_latest: 82, hrv_latest: 48, spo2_avg: 93, training_readiness_score: 88 },
    };
    mockSafetyAlerts = [{ severity: 'high', title: '夜间血氧持续偏低' }];
    const { queryByText, queryByTestId } = render(<TodayScreen />);
    expect(queryByText('今日话题')).toBeNull();
    expect(queryByText('健康 Agent')).toBeNull();
    expect(queryByText('今日判断')).toBeNull();
    expect(queryByTestId('home-command-judgment')).toBeNull();
    expect(queryByTestId('home-streak-badge')).toBeNull();
    expect(queryByTestId('home-outcome-win-card')).toBeNull();
  });
});
