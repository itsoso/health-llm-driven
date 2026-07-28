/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock only the network I/O of the service; keep pure helpers (factSentence,
// findContradictionPairs, effectiveConfidence, splitByConfidence inputs) real so
// the screen's derivation logic is genuinely exercised.
jest.mock('../../services/memoryFacts', () => {
  const actual = jest.requireActual('../../services/memoryFacts');
  return {
    __esModule: true,
    ...actual,
    listMyFacts: jest.fn(),
    getMyStats: jest.fn(),
    dismissFact: jest.fn(),
    reinforceFact: jest.fn(),
    supersedeFact: jest.fn(),
  };
});

jest.mock('expo-haptics', () => ({
  notificationAsync: jest.fn(),
  impactAsync: jest.fn(),
  NotificationFeedbackType: { Success: 'success', Error: 'error', Warning: 'warning' },
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium', Heavy: 'heavy' },
}));

jest.mock('../../components/agent/AgentFeedbackLink', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const Mock = ({ label }: any) => <Text>{label}</Text>;
  Mock.displayName = 'MockAgentFeedbackLink';
  return Mock;
});

jest.mock('../../utils/agentContext', () => ({
  createMemoryAgentContext: jest.fn(() => ({})),
}));

import {
  listMyFacts, getMyStats, dismissFact, reinforceFact, supersedeFact,
  type MemoryFact,
} from '../../services/memoryFacts';
import MemoryScreen from '../memory';

const mockList = listMyFacts as jest.Mock;
const mockStats = getMyStats as jest.Mock;
const mockDismiss = dismissFact as jest.Mock;
const mockReinforce = reinforceFact as jest.Mock;
const mockSupersede = supersedeFact as jest.Mock;

function makeFact(partial: Partial<MemoryFact> & { id: number }): MemoryFact {
  return {
    tier: 'semantic',
    subject: '你的 LDL',
    predicate: 'is_above',
    object_value: '3.4',
    object_unit: 'mmol/L',
    confidence: 0.7,
    effective_confidence: 0.7,
    reinforcement_count: 1,
    decay_rate: 0.02,
    sources: [],
    tags: [],
    is_sensitive: false,
    last_reinforced_at: null,
    supersedes_id: null,
    superseded_by_id: null,
    superseded_at: null,
    created_at: null,
    ...partial,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => {
  jest.clearAllMocks();
  mockStats.mockResolvedValue({ by_tier: [{ tier: 'semantic', total: 2, avg_confidence: 0.7 }] });
  mockDismiss.mockResolvedValue(undefined);
  mockReinforce.mockResolvedValue(undefined);
  mockSupersede.mockResolvedValue(undefined);
});

describe('MemoryScreen — 记忆透明可纠', () => {
  it('renders high-confidence facts as human-readable sentences', async () => {
    mockList.mockResolvedValue([
      makeFact({ id: 1, subject: '你的 LDL', predicate: 'is_above', object_value: '3.4', object_unit: 'mmol/L', effective_confidence: 0.8 }),
      makeFact({ id: 2, subject: '你对鱼油', predicate: 'responds_to', object_value: 'ALT 下降', object_unit: null, effective_confidence: 0.6 }),
    ]);

    const { getByText, findByText } = render(<MemoryScreen />, { wrapper });

    expect(getByText('小巴对你的了解')).toBeTruthy();
    expect(await findByText('你的 LDL 高于 3.4 mmol/L')).toBeTruthy();
    expect(getByText('你对鱼油 对其响应良好 ALT 下降')).toBeTruthy();
  });

  it('optimistically removes a fact on dismiss (success)', async () => {
    // Backing store the refetch reads from, so optimistic removal + invalidate stays consistent.
    let store = [
      makeFact({ id: 10, subject: '你的空腹血糖', predicate: 'is_above', object_value: '6.1', object_unit: 'mmol/L', effective_confidence: 0.8 }),
      makeFact({ id: 11, subject: '你对咖啡因', predicate: 'responds_to', object_value: '心悸', object_unit: null, effective_confidence: 0.75 }),
    ];
    mockList.mockImplementation(async () => store);
    mockDismiss.mockImplementation(async (id: number) => { store = store.filter(f => f.id !== id); });

    const { findByText, getByText, getByTestId, queryByText } = render(<MemoryScreen />, { wrapper });
    await findByText('你的空腹血糖 高于 6.1 mmol/L');

    fireEvent.press(getByTestId('memory-dismiss-10'));

    await waitFor(() => expect(queryByText('你的空腹血糖 高于 6.1 mmol/L')).toBeNull());
    expect(getByText('你对咖啡因 对其响应良好 心悸')).toBeTruthy();
    expect(mockDismiss).toHaveBeenCalledWith(10);
  });

  it('rolls the fact back into view when dismiss fails', async () => {
    // Stable list; dismiss always rejects, so optimistic removal must be undone.
    mockList.mockResolvedValue([
      makeFact({ id: 12, subject: '你的血糖', predicate: 'is_above', object_value: '6.1', object_unit: 'mmol/L', effective_confidence: 0.8 }),
    ]);
    mockDismiss.mockRejectedValue(new Error('network down'));

    const { findByText, getByText, getByTestId } = render(<MemoryScreen />, { wrapper });
    await findByText('你的血糖 高于 6.1 mmol/L');

    fireEvent.press(getByTestId('memory-dismiss-12'));

    // mutation fired, then rolled back — the fact is still there after the failure settles.
    await waitFor(() => expect(mockDismiss).toHaveBeenCalledWith(12));
    await waitFor(() => expect(getByText('你的血糖 高于 6.1 mmol/L')).toBeTruthy());
  });

  it('collapses low-confidence facts behind a toggle', async () => {
    mockList.mockResolvedValue([
      makeFact({ id: 20, subject: '你的血压', predicate: 'is_above', object_value: '130/85', object_unit: 'mmHg', effective_confidence: 0.85 }),
      makeFact({ id: 21, subject: '你可能偏好', predicate: 'prefers', object_value: '低强度运动', object_unit: null, effective_confidence: 0.2 }),
    ]);

    const { getByText, queryByText } = render(<MemoryScreen />, { wrapper });

    await waitFor(() => expect(getByText('你的血压 高于 130/85 mmHg')).toBeTruthy());
    // low-confidence one hidden by default, behind the collapse toggle
    expect(queryByText('你可能偏好 偏好 低强度运动')).toBeNull();
    expect(getByText('低置信记忆 1 条')).toBeTruthy();

    fireEvent.press(getByText('低置信记忆 1 条'));
    await waitFor(() => expect(getByText('你可能偏好 偏好 低强度运动')).toBeTruthy());
  });

  it('surfaces a contradiction banner for directionally-opposed facts on the same subject', async () => {
    mockList.mockResolvedValue([
      makeFact({ id: 30, subject: '你对咖啡因', predicate: 'responds_to', object_value: '提神明显', object_unit: null, effective_confidence: 0.7 }),
      makeFact({ id: 31, subject: '你对咖啡因', predicate: 'does_not_respond_to', object_value: '无感', object_unit: null, effective_confidence: 0.65 }),
    ]);

    const { getByText, getAllByText, getByTestId } = render(<MemoryScreen />, { wrapper });

    await waitFor(() => expect(getByText('发现 1 处可能矛盾的记忆')).toBeTruthy());
    expect(getAllByText('保留这条').length).toBe(2);

    // Keep fact 30 → supersede drops fact 31.
    fireEvent.press(getByTestId('memory-keep-30'));
    await waitFor(() => expect(mockSupersede).toHaveBeenCalledWith(30, 31));
  });
});
