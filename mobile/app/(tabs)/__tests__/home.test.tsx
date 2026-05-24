/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockPush = jest.fn();
const mockInvalidateQueries = jest.fn();
const mockRecordDailyPlanActionEvent = jest.fn();
const mockPushChatWithContext = jest.fn();
const mockTodayPlanPanel = jest.fn(({ title = '今日操作计划' }: { title?: string; compact?: boolean }) => {
  const { Text } = require('react-native');
  return <Text>{title}</Text>;
});
let mockDailyPlanActions: unknown[] = [];
let mockTwinData: Record<string, unknown> = {};
let mockTrajectoryData: any = null;
let mockWeeklyAdvice: any[] = [];

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    if (key.includes('safety')) {
      return { data: { alerts: [] }, isLoading: false, isRefetching: false };
    }
    if (key.includes('action-cards')) {
      return { data: [], isLoading: false, isRefetching: false };
    }
    if (key.includes('twin')) {
      return { data: mockTwinData, isLoading: false, isRefetching: false };
    }
    if (key.includes('daily-plan')) {
      return { data: { actions: mockDailyPlanActions }, isLoading: false, isRefetching: false };
    }
    if (key.includes('trajectory')) {
      return { data: mockTrajectoryData, isLoading: false, isRefetching: false };
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

jest.mock('../../../components/dashboard/TodayPlanPanel', () => {
  const MockTodayPlanPanel = (props: { title?: string; compact?: boolean }) => mockTodayPlanPanel(props);
  MockTodayPlanPanel.displayName = 'MockTodayPlanPanel';
  return MockTodayPlanPanel;
});
jest.mock('../../../components/dashboard/TrajectorySnapshotPanel', () => {
  const { Text } = require('react-native');
  const MockTrajectorySnapshotPanel = () => <Text>健康轨迹</Text>;
  MockTrajectorySnapshotPanel.displayName = 'MockTrajectorySnapshotPanel';
  return MockTrajectorySnapshotPanel;
});
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

jest.mock('../../../components/shared/EvidenceChip', () => 'EvidenceChip');
jest.mock('../../../components/knowledge', () => ({
  EvidenceRefsRow: () => null,
}));

import TodayScreen from '../index';

function flattenText(node: any): string[] {
  if (node == null || typeof node === 'boolean') return [];
  if (typeof node === 'string' || typeof node === 'number') return [String(node)];
  if (Array.isArray(node)) return node.flatMap(flattenText);
  return flattenText(node.children);
}

describe('TodayScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDailyPlanActions = [];
    mockTwinData = {};
    mockTrajectoryData = null;
    mockWeeklyAdvice = [];
  });

  it('does not show the low-value Agent data visibility panel on the home feed', () => {
    const { queryByText } = render(<TodayScreen />);

    expect(queryByText('Agent 数据视野')).toBeNull();
  });

  it('frames the home screen around today focus and uses compact quick entries', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(queryByText('今天先做 0 件事')).toBeNull();
    expect(queryByText('健康 Agent 正在运行')).toBeNull();
    expect(getByText('健康 Agent')).toBeTruthy();
    expect(getByText('后台监测中')).toBeTruthy();
    expect(getByText('当前重点 · 等待新任务')).toBeTruthy();
    expect(getByText('保持记录节奏')).toBeTruthy();
    expect(getByText('更多入口')).toBeTruthy();
    expect(queryByText('先处理一件，再看余下计划')).toBeNull();
  });

  it('places the remaining plan before shortcut entries in the home feed', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('余下计划')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('更多入口')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('余下计划')).toBeLessThan(textFlow.indexOf('更多入口'));
  });

  it('groups the home feed into agent diagnosis, action, follow-up, and entry sections', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康 Agent')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('判断')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('干预')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('验证')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('今日行动 · 现在先做')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('Agent 后续队列')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('更多入口')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('健康 Agent')).toBeLessThan(textFlow.indexOf('判断'));
    expect(textFlow.indexOf('判断')).toBeLessThan(textFlow.indexOf('今日行动 · 现在先做'));
    expect(textFlow.indexOf('今日行动 · 现在先做')).toBeLessThan(textFlow.indexOf('Agent 后续队列'));
    expect(textFlow.indexOf('Agent 后续队列')).toBeLessThan(textFlow.indexOf('更多入口'));
  });

  it('frames the home feed as a background health agent workspace', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('健康 Agent')).toBeTruthy();
    expect(getByText('后台监测中')).toBeTruthy();
    expect(getByText(/源画像/)).toBeTruthy();
    expect(queryByText('后台任务与长期干预')).toBeNull();
    expect(queryByText('持续监测 → 诊断推理 → 干预执行')).toBeNull();
    expect(queryByText('Agent 正在把你的长期画像、检查和实时反馈合并成饮食、睡眠、运动和恢复策略。')).toBeNull();
  });

  it('keeps lifestyle intervention status inside the agent workspace instead of a standalone task card', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('判断')).toBeTruthy();
    expect(getByText('干预')).toBeTruthy();
    expect(getByText('验证')).toBeTruthy();
    expect(queryByText('Agent 干预闭环')).toBeNull();
    expect(queryByText('饮食 / 睡眠 / 运动 / 补剂 / 情绪')).toBeNull();
    expect(queryByText('长期任务')).toBeNull();
  });

  it('summarizes lifestyle intervention domains as a compact status rail', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('判断')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('今日行动 · 现在先做')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('判断')).toBeLessThan(textFlow.indexOf('今日行动 · 现在先做'));
    expect(screen.getByText('判断')).toBeTruthy();
    expect(screen.getByText('干预')).toBeTruthy();
    expect(screen.getByText('验证')).toBeTruthy();
  });

  it('puts the agent workspace before action and outcome feedback sections', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康 Agent')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('今日行动 · 现在先做')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('判断')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('健康 Agent')).toBeLessThan(textFlow.indexOf('判断'));
    expect(textFlow.indexOf('判断')).toBeLessThan(textFlow.indexOf('今日行动 · 现在先做'));
  });

  it('prioritizes intervention feedback before the follow-up queue and environment details', () => {
    mockTwinData = {
      physiological: {
        sleep_score_latest: 89,
        hrv_latest: 62,
        spo2_avg: 93,
      },
      body_composition: {
        bmi: 24.1,
        body_fat_pct: 21.8,
      },
    };

    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('判断')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('本轮干预看这些结果')).toBe(-1);
    expect(textFlow.indexOf('今日行动影响的长期结果')).toBe(-1);
    expect(textFlow.indexOf('Agent 后续队列')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('环境反馈')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('判断')).toBeLessThan(textFlow.indexOf('Agent 后续队列'));
    expect(textFlow.indexOf('Agent 后续队列')).toBeLessThan(textFlow.indexOf('环境反馈'));
  });

  it('connects wearable and body composition values to the outcome feedback panel', () => {
    mockTwinData = {
      physiological: {
        sleep_score_latest: 89,
        hrv_latest: 62,
        spo2_avg: 93,
      },
      body_composition: {
        bmi: 24.1,
        body_fat_pct: 21.8,
      },
    };
    mockDailyPlanActions = [
      {
        action_key: 'nutrition.protein_target',
        domain: 'nutrition',
        title: '今天蛋白质目标',
        verification: { metric: 'body_fat', window_days: 14 },
      },
    ];

    const { getByText } = render(<TodayScreen />);

    expect(getByText('BMI/体脂')).toBeTruthy();
    expect(getByText('24.1 / 21.8%')).toBeTruthy();
    expect(getByText('睡眠分')).toBeTruthy();
    expect(getByText('89 分')).toBeTruthy();
    expect(getByText('HRV')).toBeTruthy();
    expect(getByText('62 ms')).toBeTruthy();
  });

  it('shows the lifestyle intervention loop across diet, sleep, movement, supplements, and emotion', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
      { action_key: 'movement.walk', domain: 'movement', title: '步行 20 分钟' },
      { action_key: 'supplement.magnesium', domain: 'nutrition', title: '晚间补剂' },
      { action_key: 'mood.breathing', domain: 'mental', title: '睡前呼吸练习' },
    ];

    const { getAllByText, getByText } = render(<TodayScreen />);

    expect(getByText('判断')).toBeTruthy();
    expect(getAllByText('饮食').length).toBeGreaterThan(0);
    expect(getAllByText('睡眠').length).toBeGreaterThan(0);
    expect(getAllByText('运动').length).toBeGreaterThan(0);
    expect(getByText('5项')).toBeTruthy();
  });

  it('opens the matching intervention surface from the lifestyle loop', () => {
    mockDailyPlanActions = [
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
      { action_key: 'mood.breathing', domain: 'mental', title: '睡前呼吸练习' },
    ];

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('打开睡眠干预'));
    expect(mockPush).toHaveBeenCalledWith('/sleep');

    fireEvent.press(getByLabelText('打开情绪干预'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/chat');
  });

  it('opens Agent explanation with workspace and intervention context', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('问 Agent'));

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

  it('keeps the primary action out of the remaining daily plan list', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
      {
        action_key: 'nutrition.protein_target',
        domain: 'nutrition',
        title: '今天蛋白质目标',
      },
    ];

    render(<TodayScreen />);

    expect(mockTodayPlanPanel).toHaveBeenCalledWith(expect.objectContaining({
      compact: true,
      title: '余下计划',
      excludeActionKey: 'measurement.weight_waist_morning',
    }));
  });

  it('uses a compact remaining-plan queue instead of a full task-management panel on home', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
      {
        action_key: 'nutrition.protein_target',
        domain: 'nutrition',
        title: '今天蛋白质目标',
      },
      {
        action_key: 'sleep.bedtime',
        domain: 'sleep',
        title: '23:00 上床',
      },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('余下计划')).toBeTruthy();
    expect(queryByText('今日操作计划')).toBeNull();
    expect(mockTodayPlanPanel).toHaveBeenCalledWith(expect.objectContaining({
      compact: true,
      title: '余下计划',
    }));
  });

  it('shows the active plan count when today has actions', () => {
    mockDailyPlanActions = [
      { id: '1', title: '晨间记录' },
      { id: '2', title: '步行 20 分钟' },
    ];

    const { getByText } = render(<TodayScreen />);

    expect(getByText('今天 2 件事')).toBeTruthy();
  });

  it('opens today plan when the focus header itself is tapped', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('打开今日重点'));

    expect(mockPush).toHaveBeenCalledWith('/body-measurements?focus=morning');
  });

  it('surfaces the next best action and lets the user start it directly', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
        why: '同一时间测量噪声更低。',
      },
    ];

    const { getByText } = render(<TodayScreen />);

    expect(getByText('今日行动 · 现在先做')).toBeTruthy();
    expect(getByText('晨起记录体重和腰围')).toBeTruthy();

    fireEvent.press(getByText('开始'));

    expect(mockPush).toHaveBeenCalledWith('/body-measurements?focus=morning');
  });

  it('connects the next best action to the outcome metrics it is meant to improve', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
        metric_key: 'bmi',
        why: '体重 + 腰围比单看 BMI 更能反映代谢改善。',
      },
    ];

    const { getByText } = render(<TodayScreen />);

    expect(getByText('影响指标')).toBeTruthy();
    expect(getByText('BMI')).toBeTruthy();
    expect(getByText('体脂')).toBeTruthy();
  });

  it('infers sleep intervention outcomes for sleep actions', () => {
    mockDailyPlanActions = [
      {
        action_key: 'sleep.bedtime',
        domain: 'sleep',
        title: '23:00 上床',
        why: '稳定入睡节律，减少夜间恢复波动。',
      },
    ];

    const { getAllByText } = render(<TodayScreen />);

    expect(getAllByText('睡眠分').length).toBeGreaterThan(1);
    expect(getAllByText('HRV').length).toBeGreaterThan(1);
    expect(getAllByText('血氧').length).toBeGreaterThan(1);
  });

  it('lets the user complete the next best action from the top card', async () => {
    mockRecordDailyPlanActionEvent.mockResolvedValueOnce({
      action_state: 'completed',
      payload: {},
    });
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(mockRecordDailyPlanActionEvent).toHaveBeenCalledWith(
        'measurement.weight_waist_morning',
        { event_type: 'completed', payload: { source: 'next_best_action' } },
      );
    });
  });

  it('shows an inline failure when completing the next action fails', async () => {
    mockRecordDailyPlanActionEvent.mockRejectedValueOnce(new Error('network'));
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(getByText('记录失败，请重试')).toBeTruthy();
    });
  });

  it('resets completion state when the next action changes', async () => {
    mockRecordDailyPlanActionEvent.mockResolvedValueOnce({
      action_state: 'completed',
      payload: {},
    });
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByText, rerender } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(getByText('已完成')).toBeTruthy();
    });

    mockDailyPlanActions = [
      {
        action_key: 'nutrition.log_lunch',
        domain: 'nutrition',
        title: '记录午餐',
      },
    ];
    rerender(<TodayScreen />);

    expect(queryByText('已完成')).toBeNull();
    expect(getByText('完成')).toBeTruthy();
  });
});
