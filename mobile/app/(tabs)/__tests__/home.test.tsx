/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { RefreshControl, StyleSheet } from 'react-native';
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

function findEvidenceIndex(textFlow: string[]): number {
  return textFlow.findIndex(text => /^依据 ·/.test(text));
}

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
    expect(getByText('今日判断')).toBeTruthy();
    expect(getByText('补齐今天记录后，Agent 会重新排序干预。')).toBeTruthy();
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(getByText('现在只做')).toBeTruthy();
    expect(getByText('补齐今天记录，Agent 再排干预')).toBeTruthy();
    expect(getByText(/依据 ·/)).toBeTruthy();
    expect(getByText(/下次看/)).toBeTruthy();
    expect(queryByText('先处理一件，再看余下计划')).toBeNull();
  });

  it('uses one visible Agent identity and keeps validation inside the top diagnosis card', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());
    const targetIndex = textFlow.findIndex(text => /看结果/.test(text));

    expect(screen.getAllByText('健康 Agent')).toHaveLength(1);
    expect(screen.queryByText('Agent 观测中')).toBeNull();
    expect(screen.getByLabelText('问 Agent')).toBeTruthy();
    expect(targetIndex).toBeGreaterThan(textFlow.indexOf('今日判断'));
    expect(targetIndex).toBeLessThan(textFlow.indexOf('现在只做'));
  });

  it('uses a user-facing why-now-result chain instead of internal workflow labels', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('今日判断')).toBeTruthy();
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(getByText('现在只做 · 记录')).toBeTruthy();
    expect(queryByText('Agent 判断')).toBeNull();
    expect(queryByText(/验证目标 ·/)).toBeNull();
    expect(queryByText('记录实验')).toBeNull();
  });

  it('renders the main judgment as a distinct decision panel instead of floating copy', () => {
    const { getByTestId } = render(<TodayScreen />);
    const decisionStyle = StyleSheet.flatten(getByTestId('home-command-decision-card').props.style);

    expect(decisionStyle.backgroundColor).not.toBe('transparent');
    expect(decisionStyle.borderColor).not.toBe('transparent');
    expect(decisionStyle.borderWidth).toBeGreaterThan(0);
  });

  it('keeps top evidence and target lines short enough to scan', () => {
    mockGeneticStats = { hits: 65, total: 90 };
    mockTwinData = {
      physiological: {
        spo2_avg: 95,
        sleep_score_latest: 91,
        hrv_latest: 63,
      },
    };

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('依据 · 血氧95 · 睡眠91 · HRV63 · 基因65 · 表观 · 体检')).toBeTruthy();
    expect(getByText(/看结果 · 睡眠分90\+ · HRV回升 · 血氧≥95%/)).toBeTruthy();
    expect(queryByText(/已看 ·/)).toBeNull();
    expect(queryByText(/看结果 · .* \/ /)).toBeNull();
  });

  it('keeps only one visible running state on the first screen', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('后台监测中')).toBeTruthy();
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(queryByText('运行中')).toBeNull();
  });

  it('keeps background sync out of the pull-to-refresh spinner', () => {
    mockRefetchingKeys = new Set(['twin:me']);

    const screen = render(<TodayScreen />);
    const refreshControl = screen.UNSAFE_getByType(RefreshControl);

    expect(screen.getByText('正在同步新数据')).toBeTruthy();
    expect(refreshControl.props.refreshing).toBe(false);
  });

  it('keeps background review copy scannable and user-facing', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('Agent 后台运行')).toBeTruthy();
    expect(getByText(/下次看 ·/)).toBeTruthy();
    expect(queryByText('正在观察')).toBeNull();
    expect(queryByText('后台观察')).toBeNull();
    expect(queryByText('长期复盘')).toBeNull();
    expect(queryByText(/下次复盘 ·/)).toBeNull();
    expect(queryByText(/当前先完成上方行动/)).toBeNull();
  });

  it('frames background work as an agent runner instead of generic observation', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('Agent 后台运行')).toBeTruthy();
    expect(getByText('长期画像 · 基因 表观 体检 穿戴 GPS')).toBeTruthy();
    expect(getByText('影响结果')).toBeTruthy();
    expect(queryByText('后台观察')).toBeNull();
    expect(queryByText('穿戴 · GPS · 体检')).toBeNull();
    expect(queryByText('长期画像 · 基因/表观/体检/穿戴/GPS')).toBeNull();
    expect(queryByText('结果追踪')).toBeNull();
  });

  it('surfaces epigenetic context in the compact personal evidence line', () => {
    mockGeneticStats = { hits: 65, total: 90 };
    mockTwinData = {
      physiological: {
        spo2_avg: 95,
        sleep_score_latest: 91,
        hrv_latest: 63,
      },
    };

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('依据 · 血氧95 · 睡眠91 · HRV63 · 基因65 · 表观 · 体检')).toBeTruthy();
    expect(queryByText('依据 · 血氧95 · 睡眠91 · HRV63 · 基因65 · GPS · 体检')).toBeNull();
  });

  it('grounds the top diagnosis in personal data sources instead of a generic signal line', () => {
    mockGeneticStats = { hits: 65, total: 90 };
    mockTwinData = {
      physiological: {
        spo2_avg: 95,
        sleep_score_latest: 91,
        hrv_latest: 63,
      },
    };

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('依据 · 血氧95 · 睡眠91 · HRV63 · 基因65 · 表观 · 体检')).toBeTruthy();
    expect(queryByText(/信号 ·/)).toBeNull();
  });

  it('keeps the no-plan home feed focused on the top next step instead of adding a duplicate execution card', () => {
    const { getByLabelText, getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('现在只做')).toBeTruthy();
    expect(getByLabelText('打开下一步')).toBeTruthy();
    expect(queryByText('现在只做一件')).toBeNull();
    expect(queryByText('现在先做')).toBeNull();
    expect(queryByText('没有硬性任务时，先补齐今天会影响建议的数据')).toBeNull();
  });

  it('renders the primary action as a quiet health experiment strip instead of a large CTA', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('现在只做 · 记录')).toBeTruthy();
    expect(getByText('晨起记录体重和腰围')).toBeTruthy();
    expect(queryByText('今日实验')).toBeNull();
    expect(queryByText('下一步')).toBeNull();
  });

  it('names the active lifestyle intervention experiment by strategy domain', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('现在只做 · 饮食')).toBeTruthy();
    expect(getByText('提高早餐蛋白')).toBeTruthy();
    expect(queryByText('今日实验')).toBeNull();
  });

  it('groups the home feed into agent diagnosis, action, health outcomes, evidence, and follow-up sections', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康 Agent')).toBeGreaterThanOrEqual(0);
    expect(textFlow.some(text => /干预/.test(text))).toBe(true);
    expect(textFlow.some(text => /看结果/.test(text))).toBe(true);
    expect(textFlow.indexOf('健康指标')).toBe(-1);
    expect(textFlow.indexOf('身体反馈')).toBe(-1);
    expect(textFlow.indexOf('Agent 观测中')).toBe(-1);
    const targetIndex = textFlow.findIndex(text => /看结果/.test(text));
    expect(targetIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('验证指标')).toBe(-1);
    const evidenceIndex = findEvidenceIndex(textFlow);
    expect(evidenceIndex).toBeGreaterThanOrEqual(0);
    const reviewIndex = textFlow.findIndex(text => /下次看/.test(text));
    expect(reviewIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('健康 Agent')).toBeLessThan(textFlow.indexOf('今日判断'));
    expect(textFlow.indexOf('今日判断')).toBeLessThan(targetIndex);
    expect(evidenceIndex).toBeLessThan(targetIndex);
    expect(targetIndex).toBeLessThan(textFlow.indexOf('现在只做'));
    expect(targetIndex).toBeLessThan(reviewIndex);
  });

  it('frames the home feed as a background health agent workspace', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('健康 Agent')).toBeTruthy();
    expect(getByText('后台监测中')).toBeTruthy();
    expect(queryByText(/已接入/)).toBeNull();
    expect(getByText(/依据 · .*表观.*体检/)).toBeTruthy();
    expect(queryByText(/源画像/)).toBeNull();
    expect(queryByText('后台任务与长期干预')).toBeNull();
    expect(queryByText('持续监测 → 诊断推理 → 干预执行')).toBeNull();
    expect(queryByText('Agent 正在把你的长期画像、检查和结果追踪合并成饮食、睡眠、运动和恢复策略。')).toBeNull();
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

    const { getAllByText, getByText, queryByText } = render(<TodayScreen />);

    expect(getAllByText('23:00 上床').length).toBeGreaterThan(0);
    expect(getByText('今日判断')).toBeTruthy();
    expect(getByText('今天先 23:00 上床，观察血氧、睡眠分、HRV。')).toBeTruthy();
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(getByText(/血氧≥95%.*睡眠分90\+/)).toBeTruthy();
    expect(queryByText('表观遗传、穿戴已接入')).toBeNull();
    expect(getByText(/依据 · .*表观.*体检/)).toBeTruthy();
    expect(queryByText('Agent 观测中')).toBeNull();
    expect(queryByText('验证指标')).toBeNull();
  });

  it('turns critical risk into a concrete next step instead of only a status badge', () => {
    mockSafetyAlerts = [
      { severity: 'high', title: '夜间血氧持续偏低' },
    ];

    const { getByLabelText, getByText } = render(<TodayScreen />);

    expect(getByText('今日判断')).toBeTruthy();
    expect(getByText('夜间血氧持续偏低，先查看风险原因并调整今晚策略。')).toBeTruthy();
    expect(getByText('现在只做')).toBeTruthy();
    expect(getByText('查看风险原因，调整今晚策略')).toBeTruthy();
    expect(getByLabelText('打开下一步')).toBeTruthy();
    expect(getByLabelText('问 Agent')).toBeTruthy();
  });

  it('keeps critical risk action copy short enough for the hero card', () => {
    mockSafetyAlerts = [
      { severity: 'high', title: '夜间血氧过低' },
    ];
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('夜间血氧过低，先记录体重和腰围。')).toBeTruthy();
    expect(queryByText('夜间血氧过低，今天先 晨起记录体重和腰围。')).toBeNull();
  });

  it('grounds the top diagnosis with a calm personal evidence line', () => {
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

    expect(getByText('夜间血氧过低，先查看风险原因并调整今晚策略。')).toBeTruthy();
    expect(getByText('依据 · 血氧93 · 睡眠89 · HRV62 · 基因待同步 · 表观 · 体检')).toBeTruthy();
    expect(queryByText(/信号 ·/)).toBeNull();
    expect(queryByText('93%')).toBeNull();
    expect(queryByText(/夜间血氧过低.*血氧93.*睡眠89.*HRV62/)).toBeNull();
  });

  it('presents the top card as diagnosis and next action while runtime carries the improvement target', () => {
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

    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(getByText(/BMI\/体脂.*睡眠分90\+/)).toBeTruthy();
    expect(queryByText(/饮食\/睡眠/)).toBeNull();
    expect(getByText('现在只做 · 饮食')).toBeTruthy();
    expect(queryByText('今日实验')).toBeNull();
    expect(queryByText('干预闭环')).toBeNull();
    expect(queryByText(/观察目标 ·/)).toBeNull();
  });

  it('opens the home card with a plain Agent judgment instead of status-first task wording', () => {
    mockDailyPlanActions = [
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

    expect(getByText('今日判断')).toBeTruthy();
    expect(getByText('今天先 23:00 上床，观察血氧、睡眠分、HRV。')).toBeTruthy();
    expect(queryByText('今日优先 · 1 项干预')).toBeNull();
  });

  it('moves improvement targets out of the hero and into the runtime verification line', () => {
    mockDailyPlanActions = [
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(queryByText(/观察目标 ·/)).toBeNull();
    expect(getByText(/看结果 · 血氧≥95%.*睡眠分90\+.*HRV回升/)).toBeTruthy();
    expect(queryByText('改善目标')).toBeNull();
  });

  it('leads the background panel with health outcome improvement instead of backend task framing', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康指标')).toBe(-1);
    expect(textFlow.indexOf('身体反馈')).toBe(-1);
    expect(textFlow.indexOf('Agent 观测中')).toBe(-1);
    const targetIndex = textFlow.findIndex(text => /看结果/.test(text));
    expect(targetIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('验证指标')).toBe(-1);
    expect(screen.queryByText('结果校准')).toBeNull();
    const reviewIndex = textFlow.findIndex(text => /下次看/.test(text));
    expect(reviewIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('今日判断')).toBeLessThan(targetIndex);
    expect(targetIndex).toBeLessThan(reviewIndex);
    expect(screen.queryByText('Agent 后台任务')).toBeNull();
  });

  it('keeps lifestyle intervention status inside the agent workspace instead of a standalone task card', () => {
    const { getAllByText, queryByText } = render(<TodayScreen />);

    expect(getAllByText(/干预/).length).toBeGreaterThan(0);
    expect(getAllByText(/看结果/).length).toBeGreaterThan(0);
    expect(queryByText('Agent 干预闭环')).toBeNull();
    expect(queryByText('饮食 / 睡眠 / 运动 / 补剂 / 情绪')).toBeNull();
    expect(queryByText('长期任务')).toBeNull();
  });

  it('summarizes lifestyle intervention domains as a compact status rail', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.some(text => /干预/.test(text))).toBe(true);
    const targetIndex = textFlow.findIndex(text => /看结果/.test(text));
    expect(targetIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.findIndex(text => /干预/.test(text))).toBeLessThan(targetIndex);
    expect(screen.getAllByText(/干预/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/看结果/).length).toBeGreaterThan(0);
  });

  it('surfaces lifestyle strategy coverage without adding another task panel', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
      { action_key: 'movement.zone2', domain: 'movement', title: 'Zone 2 快走' },
      { action_key: 'supplement.magnesium', domain: 'supplement', title: '睡前镁' },
      { action_key: 'emotion.breathing', domain: 'emotion', title: '睡前呼吸 5 分钟' },
    ];

    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(screen.queryByTestId('home-strategy-coverage-rail')).toBeNull();
    expect(screen.queryByText('策略覆盖')).toBeNull();
    expect(screen.getByText('长期干预 · 饮食 · 睡眠 · 运动 · 补剂 · 情绪')).toBeTruthy();
    expect(screen.queryByText('饮食')).toBeNull();
    expect(screen.queryByText('睡眠')).toBeNull();
    expect(screen.queryByText('运动')).toBeNull();
    expect(screen.queryByText('补剂')).toBeNull();
    expect(screen.queryByText('情绪')).toBeNull();
    expect(screen.queryByText('干预策略')).toBeNull();
    expect(textFlow.indexOf('现在只做 · 饮食')).toBeLessThan(
      textFlow.indexOf('长期干预 · 饮食 · 睡眠 · 运动 · 补剂 · 情绪'),
    );
  });

  it('shows strategy calibration copy when the current action is only a record task', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(queryByText('策略校准')).toBeNull();
    expect(getByText('记录后校准 5 类策略 · 饮食 睡眠 运动 补剂 情绪')).toBeTruthy();
    expect(getByText('现在只做 · 记录')).toBeTruthy();
    expect(queryByText('策略覆盖')).toBeNull();
    expect(queryByText('饮食 · 睡眠 · 运动 · 补剂 · 情绪')).toBeNull();
    expect(queryByText('记录后校准饮食/睡眠/运动/补剂/情绪')).toBeNull();
    expect(queryByText('记录后校准饮食 · 睡眠 · 运动')).toBeNull();
  });

  it('connects record actions to the body outcome they update', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByLabelText, queryByLabelText, getByText } = render(<TodayScreen />);

    expect(getByText('现在只做 · 记录')).toBeTruthy();
    expect(getByLabelText('BMI/体脂 记录后更新')).toBeTruthy();
    expect(queryByLabelText('BMI/体脂 待记录')).toBeNull();
  });

  it('keeps strategy calibration attached to the primary action instead of a standalone rail', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByTestId, queryByText } = render(<TodayScreen />);

    expect(queryByTestId('home-strategy-coverage-rail')).toBeNull();
    expect(queryByText('策略校准')).toBeNull();
    expect(getByText('记录后校准 5 类策略 · 饮食 睡眠 运动 补剂 情绪')).toBeTruthy();
    expect(queryByText('记录后校准饮食/睡眠/运动/补剂/情绪')).toBeNull();
    expect(queryByText('记录后校准饮食 · 睡眠 · 运动')).toBeNull();
    expect(getByText('现在只做 · 记录')).toBeTruthy();
  });

  it('describes multiple intervention domains in user language instead of plus-count shorthand', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
      { action_key: 'movement.zone2', domain: 'movement', title: 'Zone 2 快走' },
      { action_key: 'supplement.magnesium', domain: 'supplement', title: '睡前镁' },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('今日判断')).toBeTruthy();
    expect(getByText('今天先 提高早餐蛋白，观察BMI/体脂、睡眠分、HRV。')).toBeTruthy();
    expect(getByText(/4 个干预/)).toBeTruthy();
    expect(queryByText(/饮食\/睡眠\/运动 \+1/)).toBeNull();
    expect(queryByText(/饮食\/睡眠\/运动等 4 项干预/)).toBeNull();
    expect(queryByText(/干预域/)).toBeNull();
  });

  it('uses one compact improvement target instead of visible workflow tiles', () => {
    mockDailyPlanActions = [
      { action_key: 'nutrition.protein_target', domain: 'nutrition', title: '提高早餐蛋白' },
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
    ];

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(queryByText(/饮食\/睡眠/)).toBeNull();
    expect(queryByText('干预闭环')).toBeNull();
    expect(queryByText(/观察目标 ·/)).toBeNull();
    expect(queryByText('干预策略')).toBeNull();
    expect(queryByText('验证是否变好')).toBeNull();
  });

  it('puts the agent workspace before action and outcome feedback sections', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康 Agent')).toBeGreaterThanOrEqual(0);
    const targetIndex = textFlow.findIndex(text => /看结果/.test(text));
    expect(targetIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.some(text => /干预/.test(text))).toBe(true);
    expect(textFlow.indexOf('健康 Agent')).toBeLessThan(textFlow.findIndex(text => /干预/.test(text)));
    expect(textFlow.findIndex(text => /干预/.test(text))).toBeLessThan(targetIndex);
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
    const evidenceIndex = findEvidenceIndex(textFlow);
    expect(evidenceIndex).toBeGreaterThanOrEqual(0);
    const reviewIndex = textFlow.findIndex(text => /下次看/.test(text));
    expect(reviewIndex).toBeGreaterThanOrEqual(0);
    expect(evidenceIndex).toBeLessThan(textFlow.findIndex(text => /看结果/.test(text)));
    expect(textFlow.findIndex(text => /看结果/.test(text))).toBeLessThan(reviewIndex);
  });

  it('uses compact environment and shortcut sections to reduce home card clutter', () => {
    const { getAllByText, getByText, queryByText } = render(<TodayScreen />);

    expect(queryByText('健康指标')).toBeNull();
    expect(getByText('Agent 后台运行')).toBeTruthy();
    expect(queryByText('运行中')).toBeNull();
    expect(queryByText('结果校准')).toBeNull();
    expect(queryByText('身体反馈')).toBeNull();
    expect(queryByText('Agent 观测中')).toBeNull();
    expect(queryByText('验证指标')).toBeNull();
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(getByText('问原因')).toBeTruthy();
    expect(getByText(/依据 ·/)).toBeTruthy();
    expect(queryByText('环境背景')).toBeNull();
    expect(queryByText('环境反馈')).toBeNull();
    expect(queryByText('基因/检查/趋势')).toBeNull();
    expect(getAllByText(/基因待同步/).length).toBeGreaterThan(0);
    expect(queryByText(/进展待校准/)).toBeNull();
    expect(queryByText(/运动\/饮食方案/)).toBeNull();
  });

  it('compresses evidence and follow-up into quiet runtime summary rows', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('健康 Agent')).toBeTruthy();
    expect(queryByText('Agent 观测中')).toBeNull();
    expect(queryByText('正在用体征反馈校准今天策略')).toBeNull();
    expect(queryByText('验证指标')).toBeNull();
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(getByText(/依据 · .*表观.*体检/)).toBeTruthy();
    expect(getByText(/下次看/)).toBeTruthy();
    expect(getByText('Agent 后台运行')).toBeTruthy();
    expect(queryByText('持续观察')).toBeNull();
    expect(queryByText('后台观察')).toBeNull();
    expect(queryByText('环境证据')).toBeNull();
    expect(queryByText('个人画像')).toBeNull();
    expect(queryByText('基因/检查/趋势')).toBeNull();
    expect(queryByText('后台巡检')).toBeNull();
  });

  it('keeps live feedback as a compact runtime strip instead of a dashboard grid', () => {
    const { getByTestId, queryByTestId } = render(<TodayScreen />);

    expect(getByTestId('home-runtime-feedback-strip')).toBeTruthy();
    expect(queryByTestId('home-body-feedback-board')).toBeNull();
  });

  it('frames realtime metrics and trajectory review as a background task queue', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(screen.getByText('Agent 后台运行')).toBeTruthy();
    expect(screen.getByText('影响结果')).toBeTruthy();
    expect(screen.queryByText('指标反馈')).toBeNull();
    expect(screen.queryByText('正在观察')).toBeNull();
    expect(screen.queryByText('后台观察')).toBeNull();
    expect(screen.queryByText('结果追踪')).toBeNull();
    expect(screen.getByText(/依据 ·/)).toBeTruthy();
    expect(screen.queryByText('后台校准')).toBeNull();
    expect(screen.queryByText('实时校准')).toBeNull();
    expect(screen.queryByText('证据链')).toBeNull();
    expect(textFlow.indexOf('Agent 后台运行')).toBeLessThan(textFlow.indexOf('影响结果'));
    expect(textFlow.indexOf('影响结果')).toBeLessThan(textFlow.findIndex(text => /本周建议等待复盘|轨迹暂无新增风险/.test(text)));
    expect(findEvidenceIndex(textFlow)).toBeLessThan(textFlow.indexOf('影响结果'));
  });

  it('folds verification targets into the top diagnosis card instead of a separate section title', () => {
    const { getByLabelText, getByText, queryByText } = render(<TodayScreen />);

    expect(getByText('健康 Agent')).toBeTruthy();
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(queryByText('Agent 观测中')).toBeNull();
    expect(queryByText('验证指标')).toBeNull();
    expect(getByLabelText('问 Agent')).toBeTruthy();
  });

  it('folds evidence and next review into one agent background queue strip', () => {
    const { getByTestId, getByText, queryByTestId } = render(<TodayScreen />);

    expect(getByTestId('home-runtime-task-strip')).toBeTruthy();
    expect(queryByTestId('home-runtime-evidence-strip')).toBeNull();
    expect(getByText(/依据 · .*表观.*体检/)).toBeTruthy();
    expect(getByText(/下次看/)).toBeTruthy();
  });

  it('keeps background diagnosis, feedback, environment, and archives in one operations panel', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康指标')).toBe(-1);
    expect(textFlow.indexOf('身体反馈')).toBe(-1);
    expect(textFlow.indexOf('Agent 观测中')).toBe(-1);
    expect(textFlow.indexOf('Agent 后台运行')).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('后台观察')).toBe(-1);
    expect(textFlow.indexOf('结果校准')).toBe(-1);
    const targetIndex = textFlow.findIndex(text => /看结果/.test(text));
    expect(targetIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('验证指标')).toBe(-1);
    const evidenceIndex = findEvidenceIndex(textFlow);
    expect(evidenceIndex).toBeGreaterThanOrEqual(0);
    const reviewIndex = textFlow.findIndex(text => /下次看/.test(text));
    expect(reviewIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('今日判断')).toBeLessThan(targetIndex);
    expect(evidenceIndex).toBeLessThan(targetIndex);
    expect(targetIndex).toBeLessThan(reviewIndex);
  });

  it('keeps background observation visually subordinate to the main decision card', () => {
    const { getByTestId, getByText, queryByText } = render(<TodayScreen />);
    const panelStyle = StyleSheet.flatten(getByTestId('home-background-runtime').props.style);

    expect(getByText('Agent 后台运行')).toBeTruthy();
    expect(queryByText('持续观察')).toBeNull();
    expect(queryByText('后台观察')).toBeNull();
    expect(panelStyle.backgroundColor).toBe('transparent');
    expect(panelStyle.borderWidth).toBe(0);
  });

  it('collapses background diagnosis, calibration, evidence, and review into one quiet runtime panel', () => {
    const screen = render(<TodayScreen />);
    const textFlow = flattenText(screen.toJSON());

    expect(textFlow.indexOf('健康指标')).toBe(-1);
    expect(textFlow.indexOf('身体反馈')).toBe(-1);
    expect(textFlow.indexOf('Agent 观测中')).toBe(-1);
    expect(textFlow.indexOf('结果校准')).toBe(-1);
    const targetIndex = textFlow.findIndex(text => /看结果/.test(text));
    expect(targetIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('验证指标')).toBe(-1);
    const evidenceIndex = findEvidenceIndex(textFlow);
    expect(evidenceIndex).toBeGreaterThanOrEqual(0);
    const reviewIndex = textFlow.findIndex(text => /下次看/.test(text));
    expect(reviewIndex).toBeGreaterThanOrEqual(0);
    expect(textFlow.indexOf('Agent 自动处理')).toBe(-1);
    expect(textFlow.indexOf('正在校准结果')).toBe(-1);
    expect(textFlow.indexOf('今日判断')).toBeLessThan(targetIndex);
    expect(evidenceIndex).toBeLessThan(targetIndex);
    expect(targetIndex).toBeLessThan(reviewIndex);
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
    expect(getByText('待补 2')).toBeTruthy();
    expect(queryByText('恢复轨迹数据不足')).toBeNull();
    expect(queryByText('还有 2 个数据缺口会影响判断')).toBeNull();
    expect(getByText('代谢健康轨迹需要关注')).toBeTruthy();
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

    expect(getByText('代谢健康轨迹需要关注')).toBeTruthy();
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

    const { getAllByText, getByText } = render(<TodayScreen />);

    expect(getAllByText(/BMI\/体脂/).length).toBeGreaterThan(0);
    expect(getByText(/BMI\/体脂下降/)).toBeTruthy();
    expect(getAllByText(/睡眠分/).length).toBeGreaterThan(0);
    expect(getByText(/睡眠分90\+/)).toBeTruthy();
    expect(getAllByText(/HRV/).length).toBeGreaterThan(0);
    expect(getByText(/HRV回升/)).toBeTruthy();
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
    expect(getByText(/看结果 ·/)).toBeTruthy();
    expect(getByText(/5 个干预/)).toBeTruthy();
  });

  it('opens outcome feedback surfaces from the agent summary', () => {
    mockDailyPlanActions = [
      { action_key: 'sleep.bedtime', domain: 'sleep', title: '23:00 上床' },
      { action_key: 'mood.breathing', domain: 'mental', title: '睡前呼吸练习' },
    ];

    const { getByLabelText } = render(<TodayScreen />);

    fireEvent.press(getByLabelText('BMI/体脂 待记录'));
    expect(mockPush).toHaveBeenCalledWith('/body-measurements?focus=morning');
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
    expect(getByText('今日判断')).toBeTruthy();
    expect(getByText(/看结果 ·/)).toBeTruthy();
  });

  it('explains today focus with concrete health outcomes instead of generic ordering copy', () => {
    mockDailyPlanActions = [
      {
        action_key: 'nutrition.protein_target',
        domain: 'nutrition',
        title: '提高早餐蛋白',
      },
    ];
    mockTwinData = {
      body_composition: {
        bmi: 24.1,
        body_fat_pct: 21.8,
      },
    };

    const { getByText, queryByText } = render(<TodayScreen />);

    expect(queryByText('Agent 已把今天任务排成执行顺序。')).toBeNull();
    expect(getByText('今天先 提高早餐蛋白，观察BMI/体脂、睡眠分、HRV。')).toBeTruthy();
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
        action_key: 'movement.walk_20',
        domain: 'movement',
        title: '步行 20 分钟',
      },
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
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByLabelText, queryByText } = render(<TodayScreen />);

    expect(getByText('现在只做 · 记录')).toBeTruthy();
    expect(getByText('晨起记录体重和腰围')).toBeTruthy();
    expect(queryByText('完成')).toBeNull();
    expect(queryByLabelText('完成当前行动')).toBeNull();
  });

  it('shows an inline failure when completing the next action fails', async () => {
    mockRecordDailyPlanActionEvent.mockRejectedValueOnce(new Error('network'));
    mockDailyPlanActions = [
      {
        action_key: 'movement.walk_20',
        domain: 'movement',
        title: '步行 20 分钟',
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
        action_key: 'movement.walk_20',
        domain: 'movement',
        title: '步行 20 分钟',
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
