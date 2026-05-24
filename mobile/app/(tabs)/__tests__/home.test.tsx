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

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    if (key.includes('safety')) {
      return { data: { alerts: mockSafetyAlerts }, isLoading: false, isRefetching: false };
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

jest.mock('../../../components/dashboard/TrajectorySnapshotPanel', () => {
  const { Text } = require('react-native');
  const MockTrajectorySnapshotPanel = () => <Text>健康轨迹</Text>;
  MockTrajectorySnapshotPanel.displayName = 'MockTrajectorySnapshotPanel';
  return MockTrajectorySnapshotPanel;
});
jest.mock('../../../components/dashboard/EnvironmentCard', () => {
  const { Text } = require('react-native');
  const MockEnvironmentCard = ({ compact, mode }: { compact?: boolean; mode?: string }) => (
    <Text>{compact && mode === 'micro' ? '环境证据' : compact ? '环境背景' : '环境反馈'}</Text>
  );
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
    mockSafetyAlerts = [];
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
    expect(getByText('今日优先 · 观察中')).toBeTruthy();
    expect(getByText('保持记录节奏')).toBeTruthy();
    expect(getByText('改善目标')).toBeTruthy();
    expect(getByText('下一步')).toBeTruthy();
    expect(getByText('补齐今天记录，Agent 再排干预')).toBeTruthy();
    expect(getByText('个人画像')).toBeTruthy();
    expect(getByText('下次复盘')).toBeTruthy();
    expect(queryByText('先处理一件，再看余下计划')).toBeNull();
  });

  it('keeps the no-plan home feed focused on the top next step instead of adding a duplicate execution card', () => {
    const { getByLabelText, getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('下一步')).toBeTruthy();
    expect(getByLabelText('打开下一步')).toBeTruthy();
    expect(queryByText('现在只做一件')).toBeNull();
    expect(queryByText('现在先做')).toBeNull();
    expect(queryByText('没有硬性任务时，先补齐今天会影响建议的数据')).toBeNull();
  });

  it('groups the home feed into agent diagnosis, action, health outcomes, evidence, and follow-up sections', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康 Agent')).toBeGreaterThanOrEqual(0);
    expect(textFlow.some(text => /干预/.test(text))).toBe(true);
    expect(textFlow.some(text => /改善/.test(text))).toBe(true);
    expect(textFlow.indexOf('健康指标')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('后台巡检')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('个人画像')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('健康 Agent')).toBeLessThan(textFlow.findIndex(text => /干预/.test(text)));
    expect(textFlow.findIndex(text => /干预/.test(text))).toBeLessThan(textFlow.indexOf('健康指标'));
    expect(textFlow.indexOf('健康指标')).toBeLessThan(textFlow.indexOf('个人画像'));
    expect(textFlow.indexOf('个人画像')).toBeLessThan(textFlow.indexOf('后台巡检'));
  });

  it('frames the home feed as a background health agent workspace', () => {
    const { getAllByText, getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('健康 Agent')).toBeTruthy();
    expect(getByText('后台监测中')).toBeTruthy();
    expect(getAllByText(/已接入/).length).toBeGreaterThan(0);
    expect(queryByText(/源画像/)).toBeNull();
    expect(queryByText('后台任务与长期干预')).toBeNull();
    expect(queryByText('持续监测 → 诊断推理 → 干预执行')).toBeNull();
    expect(queryByText('Agent 正在把你的长期画像、检查和实时反馈合并成饮食、睡眠、运动和恢复策略。')).toBeNull();
  });

  it('states health improvement targets instead of only listing risks', () => {
    mockTwinData = {
      physiological: {
        sleep_score_latest: 91,
        hrv_latest: 63,
        spo2_avg: 93,
      },
    };
    mockDailyPlanActions = [
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];

    const { getAllByText, getByText } = render(<TodayScreen />);

    expect(getAllByText('23:00 上床').length).toBeGreaterThan(0);
    expect(getByText('今日优先 · 1 个计划')).toBeTruthy();
    expect(getByText('改善目标')).toBeTruthy();
    expect(getAllByText(/改善/).length).toBeGreaterThan(0);
    expect(getByText(/血氧 ≥95%.*睡眠分 90\+/)).toBeTruthy();
    expect(getAllByText('表观遗传、穿戴已接入').length).toBeGreaterThan(0);
    expect(getByText('结果校准')).toBeTruthy();
  });

  it('turns critical risk into a concrete next step instead of only a status badge', () => {
    mockSafetyAlerts = [
      { severity: 'high', title: '夜间血氧持续偏低' },
    ];

    const { getByLabelText, getByText } = render(<TodayScreen />);

    expect(getByText('今日优先 · 1 个风险')).toBeTruthy();
    expect(getByText('下一步')).toBeTruthy();
    expect(getByText('查看风险原因，调整今晚策略')).toBeTruthy();
    expect(getByLabelText('打开下一步')).toBeTruthy();
    expect(getByLabelText('问 Agent')).toBeTruthy();
  });

  it('grounds the top diagnosis with scannable personal signal chips', () => {
    mockSafetyAlerts = [
      { severity: 'high', title: '夜间血氧过低' },
    ];
    mockTwinData = {
      physiological: {
        spo2_avg: 93,
        sleep_score_latest: 89,
        hrv_latest: 62,
      },
    };

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('夜间血氧过低')).toBeTruthy();
    expect(getByText('血氧')).toBeTruthy();
    expect(getByText('93%')).toBeTruthy();
    expect(getByText('睡眠分')).toBeTruthy();
    expect(getByText('89')).toBeTruthy();
    expect(getByText('HRV')).toBeTruthy();
    expect(getByText('62ms')).toBeTruthy();
    expect(queryByText(/夜间血氧过低.*血氧 93%.*睡眠分 89.*HRV 62ms/)).toBeNull();
  });

  it('presents the top card as diagnosis, next action, and improvement target without visible loop jargon', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];
    mockTwinData = {
      physiological: {
        sleep_score_latest: 91,
        hrv_latest: 63,
        spo2_avg: 95,
      },
    };

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('改善目标')).toBeTruthy();
    expect(getByText(/BMI\/体脂.*睡眠分 90\+/)).toBeTruthy();
    expect(getByText(/饮食\/睡眠/)).toBeTruthy();
    expect(getByText('下一步')).toBeTruthy();
    expect(queryByText('干预闭环')).toBeNull();
    expect(queryByText('验证目标')).toBeNull();
  });

  it('leads the background panel with health outcome improvement instead of backend task framing', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康指标')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('后台巡检')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('健康指标')).toBeLessThan(textFlow.indexOf('后台巡检'));
    expect(screen.queryByText('Agent 后台任务')).toBeNull();
  });

  it('keeps lifestyle intervention status inside the agent workspace instead of a standalone task card', () => {
    const { getAllByText, queryByText } = render(<TodayScreen />);

    expect(getAllByText(/干预/).length).toBeGreaterThan(0);
    expect(getAllByText(/改善/).length).toBeGreaterThan(0);
    expect(queryByText('Agent 干预闭环')).toBeNull();
    expect(queryByText('饮食 / 睡眠 / 运动 / 补剂 / 情绪')).toBeNull();
    expect(queryByText('长期任务')).toBeNull();
  });

  it('summarizes lifestyle intervention domains as a compact status rail', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.some(text => /干预/.test(text))).toBe(true);
    expect(textFlow.indexOf('改善目标')).toBeGreaterThanOrEqual(0);
    expect(textFlow.findIndex(text => /干预/.test(text))).toBeLessThan(textFlow.indexOf('改善目标'));
    expect(screen.getAllByText(/干预/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/改善/).length).toBeGreaterThan(0);
  });

  it('uses one compact improvement target instead of visible workflow tiles', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('改善目标')).toBeTruthy();
    expect(getByText(/饮食\/睡眠/)).toBeTruthy();
    expect(queryByText('干预闭环')).toBeNull();
    expect(queryByText('验证目标')).toBeNull();
    expect(queryByText('干预策略')).toBeNull();
    expect(queryByText('验证是否变好')).toBeNull();
  });

  it('puts the agent workspace before action and outcome feedback sections', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康 Agent')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('改善目标')).toBeGreaterThanOrEqual(0);
    expect(textFlow.some(text => /干预/.test(text))).toBe(true);
    expect(textFlow.indexOf('健康 Agent')).toBeLessThan(textFlow.findIndex(text => /干预/.test(text)));
    expect(textFlow.findIndex(text => /干预/.test(text))).toBeLessThan(textFlow.indexOf('改善目标'));
  });

  it('prioritizes intervention feedback and personal evidence before the follow-up queue', () => {
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

    expect(textFlow.some(text => /干预/.test(text))).toBe(true);
    expect(textFlow.indexOf('结果反馈')).toBe(-1);
    expect(textFlow.indexOf('本轮干预看这些结果')).toBe(-1);
    expect(textFlow.indexOf('今日行动影响的长期结果')).toBe(-1);
    expect(textFlow.indexOf('后台巡检')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('环境证据')).toBeGreaterThanOrEqual(0);
    expect(textFlow.findIndex(text => /干预/.test(text))).toBeLessThan(textFlow.indexOf('后台巡检'));
    expect(textFlow.indexOf('身体反馈')).toBeLessThan(textFlow.indexOf('环境证据'));
    expect(textFlow.indexOf('环境证据')).toBeLessThan(textFlow.indexOf('后台巡检'));
  });

  it('uses compact environment and shortcut sections to reduce home card clutter', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('健康指标')).toBeTruthy();
    expect(queryByText('Agent 后台运行')).toBeNull();
    expect(getByText('后台运行')).toBeTruthy();
    expect(getByText('结果校准')).toBeTruthy();
    expect(getByText('问原因')).toBeTruthy();
    expect(getByText('环境证据')).toBeTruthy();
    expect(queryByText('环境背景')).toBeNull();
    expect(queryByText('环境反馈')).toBeNull();
    expect(getByText('基因/检查/趋势')).toBeTruthy();
    expect(getByText(/基因待同步/)).toBeTruthy();
    expect(getByText(/进展待校准/)).toBeTruthy();
    expect(getByText(/运动\/饮食方案/)).toBeTruthy();
  });

  it('keeps background diagnosis, feedback, environment, and archives in one operations panel', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康指标')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('Agent 后台运行')).toBe(-1);
    expect(textFlow.indexOf('后台巡检')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('结果校准')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('身体反馈')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('环境证据')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('个人画像')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('健康指标')).toBeLessThan(textFlow.indexOf('结果校准'));
    expect(textFlow.indexOf('结果校准')).toBeLessThan(textFlow.indexOf('身体反馈'));
    expect(textFlow.indexOf('身体反馈')).toBeLessThan(textFlow.indexOf('环境证据'));
    expect(textFlow.indexOf('环境证据')).toBeLessThan(textFlow.indexOf('个人画像'));
    expect(textFlow.indexOf('个人画像')).toBeLessThan(textFlow.indexOf('后台巡检'));
  });

  it('collapses background diagnosis, calibration, evidence, and review into one quiet runtime panel', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康指标')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('后台巡检')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('结果校准')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('环境证据')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('个人画像')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('下次复盘')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('Agent 自动处理')).toBe(-1);
    expect(textFlow.indexOf('正在校准结果')).toBe(-1);
    expect(textFlow.indexOf('健康指标')).toBeLessThan(textFlow.indexOf('结果校准'));
    expect(textFlow.indexOf('结果校准')).toBeLessThan(textFlow.indexOf('环境证据'));
    expect(textFlow.indexOf('环境证据')).toBeLessThan(textFlow.indexOf('个人画像'));
    expect(textFlow.indexOf('个人画像')).toBeLessThan(textFlow.indexOf('后台巡检'));
    expect(textFlow.indexOf('后台巡检')).toBeLessThan(textFlow.indexOf('下次复盘'));
  });

  it('keeps trajectory gaps as compact follow-up badges instead of full rows', () => {
    mockTrajectoryData = {
      trajectory_risks: [
        {
          domain: 'metabolic_health',
          level: 'attention',
          title: '代谢健康轨迹需要关注',
          why: '围绕腰围、蛋白和睡眠节律继续执行。',
        },
        {
          domain: 'recovery_capacity',
          level: 'unknown',
          title: '恢复轨迹数据不足',
          why: '需要更多 HRV 和睡眠窗口。',
        },
      ],
      data_gaps: [
        { code: 'labs', label: '血检缺口' },
        { code: 'waist', label: '腰围缺口' },
      ],
    };

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(queryByText('另 1 项')).toBeNull();
    expect(getByText('缺口 2')).toBeTruthy();
    expect(queryByText('恢复轨迹数据不足')).toBeNull();
    expect(queryByText('还有 2 个数据缺口会影响判断')).toBeNull();
    expect(getByText('后台巡检')).toBeTruthy();
  });

  it('keeps weekly suggestion pending state compact when trajectory risks already occupy the queue', () => {
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

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('后台巡检')).toBeTruthy();
    expect(queryByText('周建议排队')).toBeNull();
    expect(queryByText('本周建议待生成')).toBeNull();
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

    expect(getByText(/BMI\/体脂/)).toBeTruthy();
    expect(getByText(/BMI\/体脂 下降/)).toBeTruthy();
    expect(getByText(/睡眠分/)).toBeTruthy();
    expect(getByText(/睡眠分 90\+/)).toBeTruthy();
    expect(getByText(/HRV/)).toBeTruthy();
    expect(getByText(/HRV 回升/)).toBeTruthy();
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

    expect(getAllByText(/干预/).length).toBeGreaterThan(0);
    expect(getByText('改善目标')).toBeTruthy();
    expect(getByText(/饮食\/睡眠\/运动 \+2/)).toBeTruthy();
  });

  it('opens outcome feedback surfaces from the agent summary', () => {
    mockDailyPlanActions = [
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
      { action_key: 'mood.breathing', domain: 'mental', title: '睡前呼吸练习' },
    ];

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('血氧 待同步'));
    expect(mockPush).toHaveBeenCalledWith('/sleep-spo2-analysis');
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

  it('keeps the primary action out of the next queue list', () => {
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

    const { getAllByText, queryByText } = render(<TodayScreen />);

    expect(queryByText('后台排队')).toBeNull();
    expect(queryByText(/后台余/)).toBeNull();
    expect(getAllByText('晨起记录体重和腰围').length).toBe(1);
    expect(queryByText('今天蛋白质目标')).toBeNull();
    expect(queryByText('接下来')).toBeNull();
  });

  it('surfaces only one action instead of a task-management panel on home', () => {
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

    const { queryByText } = render(<TodayScreen />);

    expect(queryByText('后台排队')).toBeNull();
    expect(queryByText(/后台余/)).toBeNull();
    expect(queryByText('现在只做一件')).toBeNull();
    expect(queryByText('现在先做')).toBeNull();
    expect(queryByText('今日操作计划')).toBeNull();
    expect(queryByText('余下计划')).toBeNull();
    expect(queryByText('接下来')).toBeNull();
  });

  it('shows the active plan count when today has actions', () => {
    mockDailyPlanActions = [
      { id: '1', title: '晨间记录' },
      { id: '2', title: '步行 20 分钟' },
    ];

    const { getAllByText, getByText } = render(<TodayScreen />);

    expect(getAllByText('晨间记录').length).toBeGreaterThan(0);
    expect(getByText('今日优先 · 2 个计划')).toBeTruthy();
    expect(getByText('改善目标')).toBeTruthy();
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

    const { getByLabelText, getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('晨起记录体重和腰围')).toBeTruthy();
    expect(queryByText('现在先做')).toBeNull();

    fireEvent.press(getByLabelText('打开下一步'));

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

    const { getAllByText } = render(<TodayScreen />);

    expect(getAllByText(/BMI\/体脂/).length).toBeGreaterThan(0);
    expect(getAllByText(/VO2max/).length).toBeGreaterThan(0);
    expect(getAllByText(/HRV/).length).toBeGreaterThan(0);
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

    expect(getAllByText(/睡眠分/).length).toBeGreaterThan(0);
    expect(getAllByText(/HRV/).length).toBeGreaterThan(0);
    expect(getAllByText(/血氧/).length).toBeGreaterThan(0);
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
