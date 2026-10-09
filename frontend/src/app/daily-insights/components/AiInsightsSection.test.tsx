import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AiInsightsSection } from './AiInsightsSection';
import { DailyRecommendation } from '../types';

afterEach(cleanup);
describe('Token Plan daily insights', () => {
  it('shows provider and generated analysis', () => {
    render(<AiInsightsSection currentData={{
      llm_analysis: { available: true, provider: 'tokenplan' },
      ai_insights: { health_summary: '测试摘要', key_insights: [], today_focus: '', encouragement: '', warnings: [] },
    } as unknown as DailyRecommendation} />);
    expect(screen.getByText('阿里云 Token Plan')).toBeTruthy();
    expect(screen.getByText('测试摘要')).toBeTruthy();
  });
  it('makes an unsuccessful analysis visible and hides stale model advice', () => {
    render(<AiInsightsSection currentData={{
      llm_analysis: { available: false, provider: 'tokenplan', error: 'unavailable' },
      ai_insights: { health_summary: 'stale advice', key_insights: [], today_focus: '', encouragement: '', warnings: [] },
      ai_advice: { sleep: 'stale sleep advice' },
    } as unknown as DailyRecommendation} />);
    expect(screen.getByRole('alert').textContent).toContain('Token Plan 分析暂不可用');
    expect(screen.queryByText('stale advice')).toBeNull();
    expect(screen.queryByText('stale sleep advice')).toBeNull();
  });
});
