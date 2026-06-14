// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mockSummary = {
  title: '执行复盘：80% 完成',
  subtitle: '过去 7 天完成 4/5 个行动。',
  href: '/my-progress',
  items: [
    { key: 'completion_rate', label: '完成率', value: '80%', accent: true },
    { key: 'completed', label: '已完成', value: '4', accent: true },
    { key: 'total', label: '总行动', value: '5', accent: false },
    { key: 'learnable', label: '可学习', value: '4', accent: false },
  ],
  highlight: {
    label: '最明显变化',
    value: '体重 -1.2 kg',
    detail: '时间关联，不等于因果。',
    positive: true,
  },
};

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: mockSummary, isLoading: false, isError: false }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href, className }: { children: React.ReactNode; href: string; className?: string }) =>
    React.createElement('a', { href, className }, children),
}));

import OperatingReviewSummaryCard from '../OperatingReviewSummaryCard';

describe('OperatingReviewSummaryCard', () => {
  it('renders execution review and links to my progress', () => {
    render(<OperatingReviewSummaryCard />);

    expect(screen.getByText('执行复盘：80% 完成')).toBeTruthy();
    expect(screen.getByText('过去 7 天完成 4/5 个行动。')).toBeTruthy();
    expect(screen.getByText('体重 -1.2 kg')).toBeTruthy();
    expect(screen.getByRole('link').getAttribute('href')).toBe('/my-progress');
  });
});
