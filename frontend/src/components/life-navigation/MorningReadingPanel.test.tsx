import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getMorningReadings, getMorningReading } from '@/services/morningReadings';
import MorningReadingPanel from './MorningReadingPanel';
vi.mock('@/services/morningReadings', () => ({ getMorningReadings: vi.fn(), getMorningReading: vi.fn() }));
const item = { report_id: 'b3cbd442-0a47-454e-8fa7-c04050828c1a', title: '晨读 · 10月19日', generated_at: '2026-10-18T16:00:00Z', reading_date: '2026-10-19' };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getMorningReadings).mockResolvedValue({ items: [item], next_offset: null });
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: '有依据的思考 <script>bad()</script>' });
});
afterEach(cleanup);
it('loads the selected date and renders source text without executing HTML', async () => {
  const view = render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
  expect(view.container.querySelector('script')).toBeNull();
  expect(getMorningReading).toHaveBeenCalledWith(7, item.report_id, expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('button', { name: /晨读 · 10月19日/ }));
  expect(screen.getByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
});
it('does not present an older reading as today and allows opening history', async () => {
  render(<MorningReadingPanel owner={7} day="2026-10-21" />);
  expect(await screen.findByText('所选日期暂无晨读。')).toBeTruthy();
  expect(getMorningReading).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /晨读 · 10月19日/ }));
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
  expect(screen.getByText('历史晨读 · 2026-10-19')).toBeTruthy();
});
it('discards delayed prior-account content', async () => {
  let complete!: (value: { items: typeof item[]; next_offset: null }) => void;
  vi.mocked(getMorningReadings).mockReturnValueOnce(new Promise(resolve => { complete = resolve; })).mockResolvedValueOnce({ items: [], next_offset: null });
  const view = render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  view.rerender(<MorningReadingPanel owner={8} day="2026-10-19" />);
  await screen.findByText('所选日期暂无晨读。');
  complete({ items: [item], next_offset: null });
  await waitFor(() => expect(getMorningReading).not.toHaveBeenCalled());
  expect(screen.queryByText(item.title)).toBeNull();
});
it('exposes errors and retries rather than claiming no updates', async () => {
  vi.mocked(getMorningReadings).mockRejectedValueOnce(new Error('private secret'));
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('晨读加载失败');
  expect(screen.queryByText('所选日期暂无晨读。')).toBeNull();
  expect(screen.queryByText('private secret')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '刷新晨读' }));
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
});
it('shows history coverage and lets the user load an additional page', async () => {
  vi.mocked(getMorningReadings).mockResolvedValueOnce({ items: [], next_offset: 30 }).mockResolvedValueOnce({ items: [item], next_offset: null });
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  fireEvent.click(await screen.findByRole('button', { name: '加载更早晨读' }));
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
});
