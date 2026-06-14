// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mockSummary = {
  title: '个人证据：2 项已改善',
  subtitle: '已验证 4 项，2/4 对你有效。',
  href: '/my-progress',
  items: [
    { key: 'graded', label: '已验证', value: '4', accent: false },
    { key: 'improved', label: '已改善', value: '2', accent: true },
    { key: 'verifying', label: '验证中', value: '1', accent: false },
    { key: 'rate', label: '改善率', value: '50%', accent: true },
  ],
  highlight: { title: '提高早餐蛋白', detail: 'weight_kg 72.4 → 70.9' },
};

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: mockSummary, isLoading: false, isError: false }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href, className }: { children: React.ReactNode; href: string; className?: string }) =>
    React.createElement('a', { href, className }, children),
}));

import OutcomeProofSummaryCard from '../OutcomeProofSummaryCard';

describe('OutcomeProofSummaryCard', () => {
  it('renders personal proof and links to my progress', () => {
    render(<OutcomeProofSummaryCard />);

    expect(screen.getByText('个人证据：2 项已改善')).toBeTruthy();
    expect(screen.getByText('已验证 4 项，2/4 对你有效。')).toBeTruthy();
    expect(screen.getByText('weight_kg 72.4 → 70.9')).toBeTruthy();
    expect(screen.getByRole('link').getAttribute('href')).toBe('/my-progress');
  });
});
