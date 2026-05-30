/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockPush = jest.fn();
const mockInvalidateQueries = jest.fn();
const mockRecordDailyPlanActionEvent = jest.fn();
const mockPushChatWithContext = jest.fn();
let mockDailyPlanActions: unknown[] = [];
let mockTwinData: Record<string, unknown> = {};
let mockTrajectoryData: any = null;
let mockWeeklyAdvice: any[] = [];
let mockSafetyAlerts: any[] = [];
let mockGeneticStats: { hits: number | null; total: number | null } = { hits: null, total: null };
let mockProgressStats: { improved: number | null; total: number | null } = { improved: null, total: null };
let mockRefetchingKeys = new Set<string>();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    const isRefetching = mockRefetchingKeys.has(key);
    if (key.includes('safety')) {
      return { data: { alerts: mockSafetyAlerts }, isLoading: false, isRefetching };
    }
    if (key.includes('action-cards')) {
      return { data: [], isLoading: false, isRefetching };
    }
    if (key.includes('twin')) {
      return { data: mockTwinData, isLoading: false, isRefetching };
    }
    if (key.includes('daily-plan')) {
      return { data: { actions: mockDailyPlanActions }, isLoading: false, isRefetching };
    }
    if (key.includes('trajectory')) {
      return { data: mockTrajectoryData, isLoading: false, isRefetching };
    }
    if (key.includes('genetic-stats')) {
      return { data: mockGeneticStats, isLoading: false, isRefetching };
    }
    if (key.includes('progress-stats')) {
      return { data: mockProgressStats, isLoading: false, isRefetching };
    }
    return { data: null, isLoading: false, isRefetching: false };
  },
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

jest.mock('../../../services/actionCards', () => ({
  getActiveCards: jest.fn(),
  pickWeeklySuggestionCards: jest.fn(() => mockWeeklyAdvice),
}));

jest.mock('../../../services/dailyPlan', () => ({
  getDailyOperatingPlan: jest.fn(),
  recordDailyPlanActionEvent: (...args: unknown[]) => mockRecordDailyPlanActionEvent(...args),
}));

jest.mock('../../../services/trajectory', () => ({
  getHealthTrajectory: jest.fn(),
  pickPrimaryTrajectoryRisks: jest.fn((risks = [], limit = 3) => risks.slice(0, limit)),
}));

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

jest.mock('../../../utils/agentContext', () => ({
  pushChatWithContext: (...args: unknown[]) => mockPushChatWithContext(...args),
}));

jest.mock('../../../components/dashboard/EnvironmentCard', () => {
  const { Text } = require('react-native');
  const MockEnvironmentCard = () => <Text>环境反馈</Text>;
  MockEnvironmentCard.displayName = 'MockEnvironmentCard';
  return MockEnvironmentCard;
});
jest.mock('../../../components/dashboard/DataFreshnessPanel', () => {
  const { Text } = require('react-native');
  const MockDataFreshnessPanel = () => <Text>Agent 数据视野</Text>;
  MockDataFreshnessPanel.displayName = 'MockDataFreshnessPanel';
  return MockDataFreshnessPanel;
});

import TodayScreen from '../index';

describe('TodayScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDailyPlanActions = [];
    mockTwinData = {};
    mockTrajectoryData = null;
    mockWeeklyAdvice = [];
    mockSafetyAlerts = [];
    mockGeneticStats = { hits: null, total: null };
    mockProgressStats = { improved: null, total: null };
    mockRefetchingKeys = new Set<string>();
  });

  // ── Agent command card: identity + status ──────────────────────────

  it('does not surface the low-value Agent data visibility panel on the home feed', () => {
    const { queryByText } = render(<TodayScreen />);
    expect(queryByText('Agent 数据视野')).toBeNull();
  });

  it('shows the health Agent identity with a calm background-monitoring status', () => {
    const { getByText } = render(<TodayScreen />);
    expect(getByText('健康 Agent')).toBeTruthy();
    expect(getByText(/后台监测中/)).toBeTruthy();
  });

  it('switches the status to syncing while a tracked query is refetching', () => {
    mockRefetchingKeys = new Set(['twin:me']);
    const { getByText, queryByText } = render(<TodayScreen />);
    expect(getByText(/同步中/)).toBeTruthy();
    expect(queryByText(/后台监测中/)).toBeNull();
  });

  it('keeps the pull-to-refresh spinner separate from background sync', () => {
    mockRefetchingKeys = new Set(['twin:me']);
    const { UNSAFE_getByType } = render(<TodayScreen />);
    const { RefreshControl } = require('react-native');
    const refreshControl = UNSAFE_getByType(RefreshControl);
    expect(refreshControl.props.refreshing).toBe(false);
  });

  it('exposes an ask-Agent shortcut on the command card', () => {
    const { getByText, getByLabelText } = render(<TodayScreen />);
    expect(getByText('问原因')).toBeTruthy();
    expect(getByLabelText('问 Agent 原因')).toBeTruthy();
  });

  it('renders both command rows: a judgment row and a next-action row', () => {
    const { getByTestId, getByText } = render(<TodayScreen />);
    expect(getByTestId('home-command-judgment')).toBeTruthy();
    expect(getByTestId('home-command-action')).toBeTruthy();
    expect(getByText('今日判断')).toBeTruthy();
  });

  // ── Agent judgment copy ────────────────────────────────────────────

  it('falls back to a record-prompting judgment when there is no plan or data', () => {
    const { getByText } = render(<TodayScreen />);
    expect(getByText('补齐今天记录后，Agent 会重新排序干预。')).toBeTruthy();
  });

  it('uses live wearable feedback for the judgment even when no plan is generated', () => {
    mockTwinData = {
      physiological: { sleep_score_latest: 82, hrv_latest: 48, spo2_avg: 93 },
    };
    const { getByText, queryByText } = render(<TodayScreen />);
    expect(getByText('已有睡眠分、HRV、血氧反馈，先稳住恢复并补齐关键记录。')).toBeTruthy();
    expect(queryByText('补齐今天记录后，Agent 会重新排序干预。')).toBeNull();
  });

  it('frames a sleep action judgment around the outcomes it should move', () => {
    mockDailyPlanActions = [
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];
    const { getByText } = render(<TodayScreen />);
    expect(getByText('今天先 23:00 上床，观察血氧、睡眠分、HRV。')).toBeTruthy();
  });

  it('turns a critical risk into a concrete judgment instead of only a badge', () => {
    mockSafetyAlerts = [{ severity: 'high', title: '夜间血氧持续偏低' }];
    const { getByText } = render(<TodayScreen />);
    expect(getByText('夜间血氧持续偏低，先查看风险原因并调整今晚策略。')).toBeTruthy();
  });

  // ── Next-action lever + copy ────────────────────────────────────────

  it('labels a measurement task as a record lever and shows its title', () => {
    mockDailyPlanActions = [
      { action_key: 'measurement.weight_waist_morning', domain: 'measurement', title: '晨起记录体重和腰围' },
    ];
    const { getByText } = render(<TodayScreen />);
    expect(getByText('现在只做 · 记录')).toBeTruthy();
    expect(getByText('晨起记录体重和腰围')).toBeTruthy();
  });

  it('names a lifestyle intervention lever by its strategy domain', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
    ];
    const { getByText } = render(<TodayScreen />);
    expect(getByText('现在只做 · 饮食')).toBeTruthy();
    expect(getByText('提高早餐蛋白')).toBeTruthy();
  });

  it('shows a risk lever and a concrete next step when a critical alert exists', () => {
    mockSafetyAlerts = [{ severity: 'high', title: '夜间血氧持续偏低' }];
    const { getByText } = render(<TodayScreen />);
    expect(getByText('现在只做 · 风险')).toBeTruthy();
    expect(getByText('查看风险原因，调整今晚策略')).toBeTruthy();
  });

  it('prompts to backfill records as the next step when nothing is scheduled', () => {
    const { getByText } = render(<TodayScreen />);
    expect(getByText('现在只做')).toBeTruthy();
    expect(getByText('补齐今天记录，Agent 再排干预')).toBeTruthy();
  });

  it('keeps the critical risk as the next step even when a record task exists', () => {
    mockSafetyAlerts = [{ severity: 'high', title: '夜间血氧过低' }];
    mockDailyPlanActions = [
      { action_key: 'measurement.weight_waist_morning', domain: 'measurement', title: '晨起记录体重和腰围' },
    ];
    const { getByLabelText, getByText, queryByText } = render(<TodayScreen />);
    expect(getByText('现在只做 · 风险')).toBeTruthy();
    expect(queryByText('现在只做 · 记录')).toBeNull();

    fireEvent.press(getByLabelText('打开下一步行动'));
    expect(mockPush).toHaveBeenCalledWith('/alerts');
  });

  // ── Command-card interactions / routing ────────────────────────────

  it('routes the next-action row to the record tab when there is no plan', () => {
    const { getByLabelText } = render(<TodayScreen />);
    fireEvent.press(getByLabelText('打开下一步行动'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/record');
  });

  it('opens a measurement task from the judgment row', () => {
    mockDailyPlanActions = [
      { action_key: 'measurement.weight_waist_morning', domain: 'measurement', title: '晨起记录体重和腰围' },
    ];
    const { getByLabelText } = render(<TodayScreen />);
    fireEvent.press(getByLabelText('打开今日判断'));
    expect(mockPush).toHaveBeenCalledWith('/body-measurements?focus=morning');
  });

  it('routes a nutrition intervention to the diet plan', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
    ];
    const { getByLabelText } = render(<TodayScreen />);
    fireEvent.press(getByLabelText('打开下一步行动'));
    expect(mockPush).toHaveBeenCalledWith('/diet-plan');
  });

  it('opens the Agent explanation with workspace and intervention context', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];
    const { getByLabelText } = render(<TodayScreen />);
    fireEvent.press(getByLabelText('问 Agent 原因'));

    expect(mockPushChatWithContext).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        badge: '首页工作台',
        context: expect.objectContaining({
          from: 'home/agent-workspace',
          intervention_domains: expect.arrayContaining([
            expect.objectContaining({ key: 'diet', active_count: 1 }),
            expect.objectContaining({ key: 'sleep', active_count: 1 }),
          ]),
          data_sources: expect.arrayContaining([
            expect.objectContaining({ key: 'genetic' }),
            expect.objectContaining({ key: 'wearable' }),
          ]),
        }),
      }),
    );
  });

  // ── Next-action completion flow ────────────────────────────────────

  it('lets the user complete the next best action from the top card', async () => {
    mockRecordDailyPlanActionEvent.mockResolvedValueOnce({ action_state: 'completed', payload: {} });
    mockDailyPlanActions = [
      { action_key: 'movement.walk_20', domain: 'movement', title: '步行 20 分钟' },
    ];
    const { getByText } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(mockRecordDailyPlanActionEvent).toHaveBeenCalledWith(
        'movement.walk_20',
        { event_type: 'completed', payload: { source: 'next_best_action' } },
      );
    });
  });

  it('opens record tasks without a separate complete button', () => {
    mockDailyPlanActions = [
      { action_key: 'measurement.weight_waist_morning', domain: 'measurement', title: '晨起记录体重和腰围' },
    ];
    const { getByText, queryByText, queryByLabelText } = render(<TodayScreen />);
    expect(getByText('现在只做 · 记录')).toBeTruthy();
    expect(getByText('晨起记录体重和腰围')).toBeTruthy();
    // record tasks expose no inline complete control — just the open chevron
    expect(queryByText('完成')).toBeNull();
    expect(queryByLabelText('标记完成')).toBeNull();
  });

  it('shows an inline failure when completing the next action fails', async () => {
    mockRecordDailyPlanActionEvent.mockRejectedValueOnce(new Error('network'));
    mockDailyPlanActions = [
      { action_key: 'movement.walk_20', domain: 'movement', title: '步行 20 分钟' },
    ];
    const { getByText } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(getByText('记录失败，请重试')).toBeTruthy();
    });
  });

  it('resets completion state when the next action changes', async () => {
    mockRecordDailyPlanActionEvent.mockResolvedValueOnce({ action_state: 'completed', payload: {} });
    mockDailyPlanActions = [
      { action_key: 'movement.walk_20', domain: 'movement', title: '步行 20 分钟' },
    ];
    const { getByText, queryByText, rerender } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(getByText('已完成')).toBeTruthy();
    });

    mockDailyPlanActions = [
      { action_key: 'nutrition.log_lunch', domain: 'nutrition', title: '记录午餐' },
    ];
    rerender(<TodayScreen />);

    expect(queryByText('已完成')).toBeNull();
    expect(getByText('完成')).toBeTruthy();
  });

  it('only completes intervention actions, never record tasks', () => {
    mockDailyPlanActions = [
      { action_key: 'measurement.weight_waist_morning', domain: 'measurement', title: '晨起记录体重和腰围' },
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '今天蛋白质目标' },
    ];
    const { queryByText, getAllByText } = render(<TodayScreen />);
    // primary action is the first one (record) → no 完成 button, and it appears once
    expect(queryByText('完成')).toBeNull();
    expect(getAllByText('晨起记录体重和腰围').length).toBe(1);
    expect(queryByText('今天蛋白质目标')).toBeNull();
  });

  // ── BodyStatsRow ───────────────────────────────────────────────────

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

  // ── AgentTopicsRow ─────────────────────────────────────────────────

  it('renders the background topics row with empty-state cards by default', () => {
    const { getByText } = render(<TodayScreen />);
    expect(getByText('今日话题')).toBeTruthy();
    expect(getByText('暂无新增风险')).toBeTruthy();
    expect(getByText('等待复盘')).toBeTruthy();
    expect(getByText('结果追踪')).toBeTruthy();
  });

  it('surfaces a trajectory risk as a topic card title', () => {
    mockTrajectoryData = {
      trajectory_risks: [
        {
          domain: 'metabolic_health',
          level: 'attention',
          title: '代谢健康轨迹需要关注',
          why: '围绕腰围、蛋白和睡眠节律继续执行。',
        },
      ],
      data_gaps: [],
    };
    const { getByText } = render(<TodayScreen />);
    expect(getByText('代谢健康轨迹需要关注')).toBeTruthy();
  });

  it('hints how many interventions are in progress in the topics header', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];
    const { getByText } = render(<TodayScreen />);
    expect(getByText(/2 个干预进行中/)).toBeTruthy();
  });

  it('opens the result-tracking route from its topic card', () => {
    const { getByLabelText } = render(<TodayScreen />);
    fireEvent.press(getByLabelText('结果追踪: 3 项关键指标'));
    expect(mockPush).toHaveBeenCalledWith('/body-measurements?focus=morning');
  });
});
