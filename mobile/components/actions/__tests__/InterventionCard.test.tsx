import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InterventionCard from '../InterventionCard';
import type { ActionCard } from '../../../services/actionCards';

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn() },
}));

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('InterventionCard', () => {
  const card: ActionCard = {
    id: 1,
    title: '连续记录晚餐时间',
    content: '今晚开始记录晚餐时间，并观察睡眠变化。',
    card_type: 'plan',
    status: 'active',
    priority: 10,
    created_at: '2026-04-26T08:00:00Z',
    expires_at: '2026-05-03T08:00:00Z',
    checklist: [
      { item: '记录晚餐', done: true },
      { item: '睡前不饮酒', done: false },
    ],
    latest_assessment: null,
  };

  it('renders intervention status and checklist progress', () => {
    const { getByText } = render(<InterventionCard card={card} onComplete={jest.fn()} />);

    expect(getByText('连续记录晚餐时间')).toBeTruthy();
    expect(getByText('1/2')).toBeTruthy();
    expect(getByText('待验证 2026-05-03')).toBeTruthy();
  });

  it('does not show empty checklist placeholders as progress or rows', () => {
    const malformedCard: ActionCard = {
      ...card,
      checklist: [
        { item: '', done: false },
        { item: '  ', done: false },
      ],
    };
    const { getByText, queryByText } = render(<InterventionCard card={malformedCard} onComplete={jest.fn()} />);

    fireEvent.press(getByText('连续记录晚餐时间'));

    expect(queryByText('0/2')).toBeNull();
  });

  it('calls onComplete from the expanded action button', () => {
    const onComplete = jest.fn();
    const immediateCard = { ...card, expires_at: null, latest_assessment: null };
    const { getByText } = render(<InterventionCard card={immediateCard} onComplete={onComplete} />);

    fireEvent.press(getByText('连续记录晚餐时间'));
    fireEvent.press(getByText('标记完成'));

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('opens outcome review for cards waiting verification', () => {
    const onReview = jest.fn();
    const { getByText } = render(<InterventionCard card={card} onComplete={jest.fn()} onReview={onReview} />);

    fireEvent.press(getByText('连续记录晚餐时间'));
    fireEvent.press(getByText('复盘结果'));

    expect(getByText('干预复盘')).toBeTruthy();
  });

  it('shows system knowledge evidence refs on expanded cards', () => {
    const withEvidence: ActionCard = {
      ...card,
      evidence_refs: ['claim:c_recovery_low_reduce_intensity'],
    };
    const { getByText } = renderWithQuery(
      <InterventionCard card={withEvidence} onComplete={jest.fn()} />,
    );

    fireEvent.press(getByText('连续记录晚餐时间'));

    expect(getByText('系统证据 1')).toBeTruthy();
  });
});
