// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mockSummary = {
  attentionCount: 3,
  title: '健康守门 3 项待处理',
  subtitle: '先处理会影响建议可信度的健康维护项。',
  href: '/health-extras',
  items: [
    { key: 'data_integrity', label: '数据自检', value: '1 个问题', attention: true },
    { key: 'deprescribing', label: '用药梳理', value: '1 条候选', attention: true },
    { key: 'connection', label: '社会连接', value: '本周应自评', attention: true },
    { key: 'causal_links', label: '指标关联', value: '1 条可复盘', attention: false },
  ],
};

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: mockSummary, isLoading: false, isError: false }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href, className }: { children: React.ReactNode; href: string; className?: string }) =>
    React.createElement('a', { href, className }, children),
}));

import HealthGuardrailSummaryCard from '../HealthGuardrailSummaryCard';

describe('HealthGuardrailSummaryCard', () => {
  it('renders the dashboard guardrail summary and links to health extras', () => {
    render(<HealthGuardrailSummaryCard />);

    expect(screen.getByText('健康守门 3 项待处理')).toBeTruthy();
    expect(screen.getByText('数据自检')).toBeTruthy();
    expect(screen.getByText('1 个问题')).toBeTruthy();
    expect(screen.getByRole('link').getAttribute('href')).toBe('/health-extras');
  });
});
