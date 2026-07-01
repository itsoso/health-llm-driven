/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockPush = jest.fn();
const mockInvalidateQueries = jest.fn();
const mockApiPost = jest.fn();
let mockDailyPlanActions: unknown[] = [];
let mockDailyArtifact: any = null;
let mockTodayDynamicView: any = null;
let mockTwinData: Record<string, unknown> = {};
let mockSafetyAlerts: any[] = [];
let mockActiveCycle: any = null;
let mockDashboardData: any = null;
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
    if (key.includes('daily-artifact')) {
      return { data: mockDailyArtifact, isLoading: false, isError: false, isRefetching };
    }
    if (key.includes('today-dynamic-view')) {
      return { data: mockTodayDynamicView, isLoading: false, isError: false, isRefetching };
    }
    if (key.includes('timeline')) {
      return { data: mockTimeline, isLoading: false, isError: false, isRefetching };
    }
    if (key.includes('intervention-cycle')) {
      return { data: mockActiveCycle, isLoading: false, isRefetching };
    }
    if (key === 'dashboard') {
      return { data: mockDashboardData, isLoading: false, isSuccess: true, isRefetching };
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
  default: { get: jest.fn(), post: (...args: any[]) => mockApiPost(...args) },
}));

jest.mock('expo-notifications', () => ({
  getAllScheduledNotificationsAsync: jest.fn().mockResolvedValue([]),
  cancelScheduledNotificationAsync: jest.fn().mockResolvedValue(undefined),
  getPermissionsAsync: jest.fn().mockResolvedValue({ status: 'denied' }),
  scheduleNotificationAsync: jest.fn().mockResolvedValue('notification-id'),
  SchedulableTriggerInputTypes: { DAILY: 'daily' },
}));

// Reva self-fetching strips read their own hooks (timeline / weather). Under the
// generic react-query mock they degrade to null/empty — that's fine for the home
// feed structure assertions. We only assert on the cards that take props from index.

import TodayScreen from '../index';

describe('TodayScreen (Reva 今日 timeline-first layout)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDailyPlanActions = [];
    mockDailyArtifact = null;
    mockTodayDynamicView = null;
    mockTwinData = {};
    mockSafetyAlerts = [];
    mockActiveCycle = null;
    mockDashboardData = null;
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

  it('promotes high-priority safety alerts into Today as a contextual safety card', () => {
    mockSafetyAlerts = [{
      rule_id: 'spo2_low',
      severity: 'high',
      title: '夜间血氧持续偏低',
      message: '昨晚最低血氧 88%,需要复核设备佩戴和症状。',
      action: '今天先复测并观察是否胸闷、气短。',
    }];

    const { getByLabelText, getByText } = render(<TodayScreen />);

    expect(getByText('安全提醒')).toBeTruthy();
    expect(getByText('夜间血氧持续偏低')).toBeTruthy();
    expect(getByText('昨晚最低血氧 88%,需要复核设备佩戴和症状。')).toBeTruthy();
    expect(getByText('今天先复测并观察是否胸闷、气短。')).toBeTruthy();

    fireEvent.press(getByLabelText('查看安全提醒详情'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/alerts');
  });

  it('does not pin medium or low safety hints on Today', () => {
    mockSafetyAlerts = [{
      rule_id: 'hydration_hint',
      severity: 'medium',
      title: '饮水偏少',
      message: '今天上午饮水记录较少。',
    }];

    const { queryByText } = render(<TodayScreen />);

    expect(queryByText('安全提醒')).toBeNull();
    expect(queryByText('饮水偏少')).toBeNull();
  });

  it('renders the graceful empty state and routes to record when there is no now-item', () => {
    // 无 timeline now → Hero 空态「今天的事都安排好了」+「补齐今天记录」入口。
    const { getByText, getByLabelText } = render(<TodayScreen />);
    expect(getByText('今天的事都安排好了')).toBeTruthy();
    fireEvent.press(getByLabelText('补齐今天记录'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/record');
  });

  it('promotes the Daily Artifact as the primary home action when available', () => {
    mockTimeline = makeTimeline({
      id: 'act-1',
      kind: 'action',
      time_window: 'noon',
      scheduled_for: '12:00',
      title: '旧 Hero 行动',
      subtitle: null,
      icon: 'restaurant-outline',
      color: '#1F8A5B',
      status: 'pending',
      priority: 1,
      can_complete: false,
      complete_ref: null,
      deep_link: null,
      severity: null,
      proof: null,
    });
    mockDailyArtifact = {
      artifact_date: '2026-06-27',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先处理餐后窗口。' },
      top_action: {
        id: 'walk-10m',
        title: '午饭后步行 10 分钟',
        do_now: '穿好鞋,从办公室楼下走一圈。',
        actions: { complete: { enabled: true }, skip: { requires_reason: true } },
      },
      evidence: [{ kind: 'why_now', label: 'Why now', summary: '餐后窗口' }],
      confidence: 'medium',
      freshness: { status: 'fresh', sources: ['health_protocol'] },
      safety_boundary: '这是健康管理行动建议。',
    };

    const { getByText, queryByLabelText } = render(<TodayScreen />);

    expect(getByText('今日焦点')).toBeTruthy();
    expect(getByText('午饭后步行 10 分钟')).toBeTruthy();
    expect(queryByLabelText('现在该做:旧 Hero 行动')).toBeNull();
  });

  it('routes Daily Artifact go-execute into the right action surface instead of the blank timeline', () => {
    mockDailyArtifact = {
      artifact_date: '2026-06-29',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先恢复。' },
      top_action: {
        id: 'today-recovery',
        title: '今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
        why_now: '近期恢复不足。',
        do_now: '先睡眠和轻活动。',
        source: { object_type: 'health_protocol', object_id: 7 },
        actions: {
          complete: { enabled: false },
          skip: { requires_reason: true },
          ask_reva: { target: '/voice-chat?intent=daily_artifact' },
        },
      },
      evidence: [{ kind: 'verification', label: 'Verification', summary: '用睡眠和腰围验证。' }],
      confidence: 'high',
      freshness: { status: 'fresh', sources: ['runtime'] },
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
    };

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('执行今日最重要行动'));
    expect(mockPush).toHaveBeenCalledWith('/movement-plan');
    expect(mockPush).not.toHaveBeenCalledWith('/timeline');
  });

  it('routes Daily Artifact ask into Aheng chat instead of the legacy voice chat page', () => {
    mockDailyArtifact = {
      artifact_date: '2026-06-29',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先处理餐后窗口。' },
      top_action: {
        id: 'walk-10m',
        title: '午饭后步行 10 分钟',
        do_now: '穿好鞋,从办公室楼下走一圈。',
        actions: {
          complete: { enabled: false },
          skip: { requires_reason: true },
          ask_reva: { target: '/voice-chat?intent=daily_artifact' },
        },
      },
      evidence: [{ kind: 'why_now', label: 'Why now', summary: '餐后窗口' }],
      confidence: 'medium',
      freshness: { status: 'fresh', sources: ['health_protocol'] },
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
    };

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('询问阿衡今日行动'));
    const route = mockPush.mock.calls[mockPush.mock.calls.length - 1]?.[0] as any;
    expect(route.pathname).toBe('/(tabs)/chat');
    expect(route.params.prompt).toContain('午饭后步行 10 分钟');
    expect(route.params.context).toContain('"intent":"ask_reva"');
    expect(mockPush).not.toHaveBeenCalledWith('/voice-chat?intent=daily_artifact');
  });

  it('routes Daily Artifact decision basis into the local interpretation page with evidence context', () => {
    mockDailyArtifact = {
      artifact_date: '2026-06-29',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先恢复。' },
      top_action: {
        id: 'today-recovery',
        title: '今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
        why_now: '睡眠和恢复不足,今天不应叠加强度。',
        do_now: '优先睡眠与轻活动。',
        actions: {
          complete: { enabled: false },
          skip: { requires_reason: true },
        },
      },
      evidence: [
        { kind: 'why_now', label: 'Why now', summary: '恢复不足。' },
        { kind: 'verification', label: 'Verification', summary: '用睡眠和腰围验证。' },
      ],
      confidence: 'high',
      freshness: { status: 'fresh', sources: ['runtime'] },
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
    };

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('查看今日行动决策依据'));
    const route = mockPush.mock.calls[mockPush.mock.calls.length - 1]?.[0] as any;
    expect(route.pathname).toBe('/daily-artifact/[date]');
    expect(route.params.date).toBe('2026-06-29');
    expect(route.params.artifact).toContain('"intent":"explain_basis"');
    expect(route.params.artifact).toContain('睡眠和恢复不足');
  });

  it('renders the Aheng-generated DynamicView when available', () => {
    mockTimeline = makeTimeline({
      id: 'act-1',
      kind: 'action',
      time_window: 'noon',
      scheduled_for: '12:00',
      title: '旧 Hero 行动',
      subtitle: null,
      icon: 'restaurant-outline',
      color: '#1F8A5B',
      status: 'pending',
      priority: 1,
      can_complete: false,
      complete_ref: null,
      deep_link: null,
      severity: null,
      proof: null,
    });
    mockTodayDynamicView = {
      view_id: 'today:2026-06-29:abc',
      surface: 'mobile.today',
      trigger: 'open',
      generated_by: 'aheng_today_view_v1',
      generated_at: '2026-06-29T08:00:00Z',
      expires_at: '2026-06-29T08:01:00Z',
      context_hash: 'abc',
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
      sections: [
        {
          slot: 'hero',
          priority: 100,
          cards: [
            {
              type: 'daily_artifact',
              data: {
                artifact_date: '2026-06-29',
                empty_state: false,
                state: { label: '今日最重要行动', tone: 'focused', summary: '阿衡已生成今日行动。' },
                top_action: {
                  id: 'dynamic-walk',
                  title: '阿衡动态生成的餐后步行',
                  why_now: '餐后窗口优先。',
                  actions: { complete: { enabled: false }, skip: { requires_reason: true } },
                },
                evidence: [],
                confidence: 'medium',
                freshness: { status: 'fresh', sources: ['agenda.runtime_range'] },
                safety_boundary: '健康管理行动建议,不替代医生诊断。',
              },
            },
          ],
        },
        {
          slot: 'runtime',
          priority: 80,
          cards: [
            {
              type: 'runtime_agenda',
              data: {
                generated_by: 'rolling_health_runtime_v1',
                horizon_days: 7,
                next_action: {
                  title: '晚餐后步行 15 分钟',
                  time_window: 'evening',
                  priority_tier: 'P1',
                  current_state_summary: '晚餐后是今天最短的代谢干预窗口。',
                  replan_reason: 'today_smart_rank',
                  verification_metrics: ['waist_cm'],
                  verification_window_days: 7,
                },
                days: [],
                safety_boundary: '健康管理行动建议,不替代医生诊断。',
              },
            },
          ],
        },
      ],
    };

    const { getByTestId, getByText, queryByLabelText, queryByText } = render(<TodayScreen />);

    expect(getByTestId('dynamic-today-view')).toBeTruthy();
    expect(getByText('阿衡动态生成的餐后步行')).toBeTruthy();
    expect(queryByText('7天验证节奏')).toBeNull();
    expect(queryByLabelText('现在该做:旧 Hero 行动')).toBeNull();
  });

  it('does not repeat the Aheng-promoted action in the following timeline strip', () => {
    mockTimeline = makeTimeline({
      id: 'dynamic-walk',
      kind: 'action',
      time_window: 'noon',
      scheduled_for: '12:30',
      title: '阿衡动态生成的餐后步行',
      subtitle: '餐后窗口优先。',
      icon: 'walk-outline',
      color: '#1F8A5B',
      status: 'pending',
      priority: 1,
      can_complete: false,
      complete_ref: null,
      deep_link: null,
      severity: null,
      proof: null,
    });
    mockTodayDynamicView = {
      view_id: 'today:2026-06-29:abc',
      surface: 'mobile.today',
      trigger: 'open',
      generated_by: 'aheng_today_view_v1',
      generated_at: '2026-06-29T08:00:00Z',
      expires_at: '2026-06-29T08:01:00Z',
      context_hash: 'abc',
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
      sections: [
        {
          slot: 'hero',
          priority: 100,
          cards: [
            {
              type: 'daily_artifact',
              data: {
                artifact_date: '2026-06-29',
                empty_state: false,
                state: { label: '今日最重要行动', tone: 'focused', summary: '阿衡已生成今日行动。' },
                top_action: {
                  id: 'dynamic-walk',
                  title: '阿衡动态生成的餐后步行',
                  why_now: '餐后窗口优先。',
                  actions: { complete: { enabled: false }, skip: { requires_reason: true } },
                },
                evidence: [],
                confidence: 'medium',
                freshness: { status: 'fresh', sources: ['agenda.runtime_range'] },
                safety_boundary: '健康管理行动建议,不替代医生诊断。',
              },
            },
          ],
        },
      ],
    };

    const { getAllByText } = render(<TodayScreen />);

    expect(getAllByText('阿衡动态生成的餐后步行')).toHaveLength(1);
  });

  it('does not repeat an Aheng-promoted generic atom in the following timeline strip', () => {
    mockTimeline = makeTimeline({
      id: 'dynamic-walk',
      kind: 'action',
      time_window: 'noon',
      scheduled_for: '12:30',
      title: '阿衡动态生成的餐后步行',
      subtitle: '餐后窗口优先。',
      icon: 'walk-outline',
      color: '#1F8A5B',
      status: 'pending',
      priority: 1,
      can_complete: false,
      complete_ref: null,
      deep_link: null,
      severity: null,
      proof: null,
    });
    mockTodayDynamicView = {
      view_id: 'today:2026-06-29:abc',
      surface: 'mobile.today',
      trigger: 'open',
      generated_by: 'aheng_today_view_v1',
      generated_at: '2026-06-29T08:00:00Z',
      expires_at: '2026-06-29T08:01:00Z',
      context_hash: 'abc',
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
      sections: [
        {
          slot: 'hero',
          priority: 100,
          cards: [
            {
              id: 'daily-artifact:2026-06-29:dynamic-walk',
              type: 'agent_atom',
              render: { atom: 'daily_artifact', reason: 'primary_today_action' },
              data: {
                artifact_date: '2026-06-29',
                empty_state: false,
                state: { label: '今日最重要行动', tone: 'focused', summary: '阿衡已生成今日行动。' },
                top_action: {
                  id: 'dynamic-walk',
                  title: '阿衡动态生成的餐后步行',
                  why_now: '餐后窗口优先。',
                  actions: { complete: { enabled: false }, skip: { requires_reason: true } },
                },
                evidence: [],
                confidence: 'medium',
                freshness: { status: 'fresh', sources: ['agenda.runtime_range'] },
                safety_boundary: '健康管理行动建议,不替代医生诊断。',
              },
            },
          ],
        },
      ],
    };

    const { getAllByText } = render(<TodayScreen />);

    expect(getAllByText('阿衡动态生成的餐后步行')).toHaveLength(1);
  });

  it('omits the noisy Twin freshness status row from the greeting header', () => {
    mockTwinData = {
      physiological: { training_readiness_score: 87, hrv_latest: 48 },
    };
    mockDailyArtifact = {
      artifact_date: '2026-06-27',
      empty_state: false,
      state: { label: '今日状态', tone: 'focused', summary: '数据已更新。' },
      top_action: null,
      evidence: [],
      confidence: 'medium',
      freshness: { status: 'fresh', sources: ['HealthKit', 'Garmin'] },
      safety_boundary: null,
    };

    const { queryByTestId, queryByText } = render(<TodayScreen />);

    expect(queryByTestId('reva-cockpit-status-row')).toBeNull();
    expect(queryByText('Twin 已更新')).toBeNull();
    expect(queryByText('2 个来源 · 新鲜')).toBeNull();
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

  it('hides the standalone 90-day cycle when Aheng has already generated the primary today action', () => {
    mockActiveCycle = {
      id: 7,
      status: 'active',
      start_date: new Date(Date.now() - 14 * 86400000).toISOString(),
      planned_end_date: new Date(Date.now() + 76 * 86400000).toISOString(),
      outcomes: [{ metric_code: 'LDL', display: 'LDL-C', unit: 'mmol/L', status: 'pending' }],
    };
    mockDailyArtifact = {
      artifact_date: '2026-06-29',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先处理今日行动。' },
      top_action: {
        id: 'walk',
        title: '午饭后步行 10 分钟',
        why_now: '餐后窗口优先。',
        verification_signal: 'waist_cm',
        actions: { complete: { enabled: false }, skip: { requires_reason: true } },
      },
      evidence: [],
      confidence: 'medium',
      freshness: { status: 'fresh', sources: ['runtime'] },
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
    };

    const { queryByTestId, getByText } = render(<TodayScreen />);

    expect(getByText('午饭后步行 10 分钟')).toBeTruthy();
    expect(queryByTestId('home-health-cycle-cockpit')).toBeNull();
  });

  it('hides the standalone 90-day cycle when the Hero already has a now-action', () => {
    mockActiveCycle = {
      id: 7,
      status: 'active',
      start_date: new Date(Date.now() - 14 * 86400000).toISOString(),
      planned_end_date: new Date(Date.now() + 76 * 86400000).toISOString(),
      outcomes: [{ metric_code: 'LDL', display: 'LDL-C', unit: 'mmol/L', status: 'pending' }],
    };
    mockTimeline = makeTimeline({
      id: 'protein-breakfast',
      kind: 'action',
      time_window: 'morning',
      scheduled_for: '08:30',
      title: '早餐补足 30g 蛋白',
      subtitle: '先完成当下这一餐,长期周期放到分析页复盘。',
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

    const { getByLabelText, queryByTestId, queryByText } = render(<TodayScreen />);

    expect(getByLabelText('现在该做:早餐补足 30g 蛋白')).toBeTruthy();
    expect(queryByTestId('home-health-cycle-cockpit')).toBeNull();
    expect(queryByText('90 天代谢周期')).toBeNull();
  });

  it('keeps the pull-to-refresh spinner separate from background sync', () => {
    mockRefetchingKeys = new Set(['twin:me']);
    const { UNSAFE_getByType } = render(<TodayScreen />);
    const { RefreshControl } = require('react-native');
    const refreshControl = UNSAFE_getByType(RefreshControl);
    expect(refreshControl.props.refreshing).toBe(false);
  });

  it('does not show completed-only medication and supplement summaries on Today', () => {
    mockDashboardData = {
      medicationToday: [
        {
          medication_id: 1,
          name: '二甲双胍',
          dosage: '0.5g',
          category: 'medication',
          total_count: 2,
          taken_count: 2,
          skipped_count: 0,
          last_taken_time: '08:00',
          reminder_times: ['08:00', '20:00'],
          logs: [],
        },
        {
          medication_id: 2,
          name: 'Magnesium',
          dosage: '100mg',
          category: 'supplement',
          total_count: 1,
          taken_count: 1,
          skipped_count: 0,
          last_taken_time: '09:00',
          reminder_times: ['09:00'],
          logs: [],
        },
      ],
    };

    const { queryByLabelText, queryByText } = render(<TodayScreen />);

    expect(queryByLabelText('今日用药补剂摘要')).toBeNull();
    expect(queryByText('用药 / 补剂')).toBeNull();
    expect(queryByText('今日已全部完成')).toBeNull();
    expect(queryByText('二甲双胍')).toBeNull();
    expect(queryByText('Magnesium')).toBeNull();
  });

  // ── 身体信号 (agent-selected compact signals) ──

  it('does not render placeholder-only body signals when there is no action context or data', () => {
    const { queryByText } = render(<TodayScreen />);
    expect(queryByText('身体信号')).toBeNull();
    expect(queryByText('/ 8,000')).toBeNull();
  });

  it('does not surface normal body signals without current action context', () => {
    mockTwinData = {
      physiological: { spo2_avg: 96, hrv_latest: 59, sleep_duration_h_latest: 8.3, body_battery_current: 98 },
      body_composition: { bmi: 22.4 },
      labs: { blood_pressure_systolic: 120, blood_pressure_diastolic: 78 },
    };
    const { queryByLabelText, queryByText } = render(<TodayScreen />);
    expect(queryByText('身体信号')).toBeNull();
    expect(queryByLabelText('睡眠 8.3h')).toBeNull();
    expect(queryByLabelText('HRV 59ms')).toBeNull();
    expect(queryByLabelText('电量 98')).toBeNull();
    expect(queryByLabelText('BMI 22.4')).toBeNull();
  });

  it('surfaces body signals when current action asks for verification', () => {
    mockTwinData = {
      physiological: { spo2_avg: 96, hrv_latest: 59, sleep_duration_h_latest: 8.3, body_battery_current: 98 },
      body_composition: { bmi: 22.4 },
      labs: { blood_pressure_systolic: 120, blood_pressure_diastolic: 78 },
    };
    mockDailyArtifact = {
      artifact_date: '2026-06-29',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先处理今日行动。' },
      top_action: {
        id: 'waist-check',
        title: '记录腰围和体重',
        why_now: '用代谢信号验证行动。',
        verification_signal: 'waist_cm',
        actions: { complete: { enabled: false }, skip: { requires_reason: true } },
      },
      evidence: [],
      confidence: 'medium',
      freshness: { status: 'fresh', sources: ['runtime'] },
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
    };
    const { getByLabelText } = render(<TodayScreen />);
    expect(getByLabelText('睡眠 8.3h')).toBeTruthy();
    expect(getByLabelText('HRV 59ms')).toBeTruthy();
    expect(getByLabelText('电量 98')).toBeTruthy();
    expect(getByLabelText('BMI 22.4')).toBeTruthy();
  });

  it('opens a body signal route on press', () => {
    mockDailyArtifact = {
      artifact_date: '2026-06-29',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先处理今日行动。' },
      top_action: {
        id: 'waist-check',
        title: '记录腰围和体重',
        why_now: '用代谢信号验证行动。',
        verification_signal: 'waist_cm',
        actions: { complete: { enabled: false }, skip: { requires_reason: true } },
      },
      evidence: [],
      confidence: 'medium',
      freshness: { status: 'fresh', sources: ['runtime'] },
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
    };
    const { getByLabelText, queryByLabelText } = render(<TodayScreen />);
    expect(queryByLabelText('睡眠 待同步')).toBeNull();
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

  it('does not show generic quick actions when the Hero already provides the empty-state record action', () => {
    const { getByLabelText, getByText, queryByLabelText, queryByText } = render(<TodayScreen />);

    expect(getByText('今天的事都安排好了')).toBeTruthy();
    expect(getByLabelText('补齐今天记录')).toBeTruthy();
    expect(queryByText('补今日记录')).toBeNull();
    expect(queryByLabelText('补今日记录')).toBeNull();
    expect(queryByLabelText('语音记录')).toBeNull();
    expect(queryByLabelText('记录')).toBeNull();
    expect(queryByText('开始跑步')).toBeNull();
    expect(queryByLabelText('试试阿衡')).toBeNull();

    fireEvent.press(getByLabelText('补齐今天记录'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/record');
  });

  it('does not show generic quick actions when the Hero already has a now-action', () => {
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

    const { getByLabelText, queryByLabelText, queryByText } = render(<TodayScreen />);

    expect(getByLabelText('现在该做:提高早餐蛋白')).toBeTruthy();
    expect(queryByText('补今日记录')).toBeNull();
    expect(queryByLabelText('补今日记录')).toBeNull();
    expect(queryByLabelText('语音记录')).toBeNull();
    expect(queryByLabelText('记录')).toBeNull();
  });

  it('hides generic quick actions when Aheng already provides primary action controls', () => {
    mockDailyArtifact = {
      artifact_date: '2026-06-29',
      empty_state: false,
      state: { label: '今日最重要行动', tone: 'focused', summary: '先处理今日行动。' },
      top_action: {
        id: 'walk-after-lunch',
        title: '午饭后步行 10 分钟',
        why_now: '餐后窗口优先,先用轻活动稳定血糖波动。',
        actions: { complete: { enabled: false }, skip: { requires_reason: true } },
      },
      evidence: [],
      confidence: 'medium',
      freshness: { status: 'fresh', sources: ['runtime'] },
      safety_boundary: '健康管理行动建议,不替代医生诊断。',
    };

    const { getByText, queryByLabelText, queryByText } = render(<TodayScreen />);

    expect(getByText('午饭后步行 10 分钟')).toBeTruthy();
    expect(queryByText('补今日记录')).toBeNull();
    expect(queryByLabelText('补今日记录')).toBeNull();
    expect(queryByLabelText('语音记录')).toBeNull();
    expect(queryByLabelText('记录')).toBeNull();
  });
});
