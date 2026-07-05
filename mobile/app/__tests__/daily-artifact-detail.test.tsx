/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import type { DailyArtifact } from '../../services/dailyArtifact';
import { getDailyArtifactDetail } from '../../services/dailyArtifact';
import { buildDailyArtifactBasisRoute } from '../../utils/dailyArtifactNavigation';

const mockBack = jest.fn();
const mockPush = jest.fn();
let mockParams: Record<string, string | undefined> = {};

jest.mock('expo-router', () => ({
  useLocalSearchParams: () => mockParams,
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

jest.mock('expo-status-bar', () => ({
  StatusBar: () => null,
}));

jest.mock('@expo/vector-icons', () => ({
  Ionicons: 'Ionicons',
}));

jest.mock('../../services/dailyArtifact', () => ({
  getDailyArtifactDetail: jest.fn(),
}));

import DailyArtifactDetailScreen from '../daily-artifact/[date]';

const mockGetDailyArtifactDetail = getDailyArtifactDetail as jest.MockedFunction<typeof getDailyArtifactDetail>;

function makeArtifact(overrides: Partial<DailyArtifact> = {}): DailyArtifact {
  return {
    artifact_date: '2026-06-29',
    empty_state: false,
    state: { label: '今日最重要行动', tone: 'focused', summary: '先恢复。' },
    top_action: {
      id: 'today-recovery',
      title: '今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
      why_now: '睡眠和恢复不足,今天不应叠加强度。',
      do_now: '优先睡眠与轻活动。',
      confidence: 'high',
      priority_tier: 'P0',
      target_state_variable: 'waist_cm',
      verification_signal: 'sleep_score',
      actions: { complete: { enabled: false }, skip: { requires_reason: true } },
    },
    evidence: [
      { kind: 'why_now', label: 'Why now', summary: '恢复不足。' },
      { kind: 'verification', label: 'Verification', summary: '用睡眠和腰围验证。' },
    ],
    confidence: 'high',
    freshness: { status: 'fresh', sources: ['runtime'] },
    safety_boundary: '健康管理行动建议,不替代医生诊断。',
    ...overrides,
  };
}

describe('DailyArtifactDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockParams = {};
    mockGetDailyArtifactDetail.mockResolvedValue(null);
  });

  it('renders the decision basis, execution guidance, verification plan, and safety boundary', () => {
    const route = buildDailyArtifactBasisRoute(makeArtifact());
    mockParams = route.params as Record<string, string>;

    const { getByText } = render(<DailyArtifactDetailScreen />);

    expect(getByText('今日行动解读')).toBeTruthy();
    expect(getByText('恢复/休息:暂停高强度;优先睡眠与轻活动')).toBeTruthy();
    expect(getByText('为什么现在')).toBeTruthy();
    expect(getByText('睡眠和恢复不足,今天不应叠加强度。')).toBeTruthy();
    expect(getByText('现在怎么做')).toBeTruthy();
    expect(getByText('优先睡眠与轻活动。')).toBeTruthy();
    expect(getByText('后续验证')).toBeTruthy();
    expect(getByText('睡眠分')).toBeTruthy();
    expect(getByText('用睡眠和腰围验证。')).toBeTruthy();
    expect(getByText('健康管理行动建议,不替代医生诊断。')).toBeTruthy();
  });

  it('continues the detailed interpretation in Aheng with the same evidence context', () => {
    const route = buildDailyArtifactBasisRoute(makeArtifact());
    mockParams = route.params as Record<string, string>;

    const { getByLabelText } = render(<DailyArtifactDetailScreen />);

    fireEvent.press(getByLabelText('继续和小巴讨论今日行动'));
    const pushed = mockPush.mock.calls[mockPush.mock.calls.length - 1]?.[0] as any;
    expect(pushed.pathname).toBe('/(tabs)/chat');
    expect(pushed.params.prompt).toContain('决策依据');
    expect(pushed.params.context).toContain('"intent":"explain_basis"');
    expect(pushed.params.context).toContain('睡眠和恢复不足');
  });

  it('recovers the detail from date and action id when route payload is absent', async () => {
    mockParams = { date: '2026-06-29', actionId: 'today-recovery' };
    mockGetDailyArtifactDetail.mockResolvedValue(makeArtifact());

    const { getByText } = render(<DailyArtifactDetailScreen />);

    await waitFor(() => {
      expect(getByText('恢复/休息:暂停高强度;优先睡眠与轻活动')).toBeTruthy();
    });
    expect(mockGetDailyArtifactDetail).toHaveBeenCalledWith({
      date: '2026-06-29',
      actionId: 'today-recovery',
    });
  });
});
